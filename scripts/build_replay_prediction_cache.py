"""Offline replay prediction checkpoint backfill (R3).

Generates frozen prediction checkpoints per race and persists validated
filesystem artifacts. Sequential, resumable (valid-complete artifacts are
skipped), offline-only. NEVER runs on the interaction path.

Scope is explicit: one of --race-id / --season / --all-served-races is
required; there is no default full-corpus run. --dry-run performs
model-free checkpoint selection only (no model load, no generation).

Example:
    python scripts/build_replay_prediction_cache.py --race-id 2023-r01-R
    python scripts/build_replay_prediction_cache.py --season 2023 --dry-run
    python scripts/build_replay_prediction_cache.py --all-served-races
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import sys
import time

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, REPO_ROOT)

import pandas as pd

from api.v2_service import SERVED_SEASONS
from v2 import replay as RP
from v2.config import V2Paths
from v2.features.build_matrix import load_history
from v2.model_lab import serving as SERVING
from v2.prediction import RacePredictionEngine
from v2.race_state_features import RaceStateFeatureBridge
from v2.race_state_reconstruction import RaceStateReconstructor
from v2.replay_predictions import (
    DEFAULT_CHECKPOINTS_DIR,
    REPLAY_PREDICTION_CONTRACT_VERSION,
    CheckpointError,
    artifact_path,
    cache_identity_inputs,
    canonical_data_identity,
    ensure_race_artifact,
    select_checkpoints,
)
from v2.replay_reconstruction import ReplayReconstructor


def race_season(race_id: str) -> int:
    try:
        return int(str(race_id).split("-")[0])
    except (ValueError, IndexError):
        raise CheckpointError(f"bad race_id {race_id!r}")


def require_served(race_id: str) -> None:
    if race_season(race_id) not in tuple(SERVED_SEASONS):
        raise CheckpointError(
            f"race {race_id!r} is outside the served replay scope "
            f"{list(SERVED_SEASONS)} (2025 excluded)")


def races_for_season(season: int) -> list:
    if season not in tuple(SERVED_SEASONS):
        raise CheckpointError(
            f"season {season} is outside served scope "
            f"{list(SERVED_SEASONS)}")
    pattern = os.path.join(
        REPO_ROOT, "data", "v2", "processed", "results",
        f"season={season}", "results__*.parquet")
    found = []
    for path in sorted(glob.glob(pattern)):
        base = os.path.basename(path)
        found.append(base[len("results__"):-len(".parquet")])
    return found


def load_race_inputs(season: int, race_id: str):
    base = os.path.join(REPO_ROOT, "data", "v2", "processed")
    states = pd.read_parquet(os.path.join(
        base, "driver_lap_state_d9", f"season={season}",
        f"driver_lap_state_d9__d9-{season}.parquet"))
    states = states[states["race_id"] == race_id].copy()
    if len(states) == 0:
        raise CheckpointError(f"no canonical rows for race {race_id!r}")
    results = pd.read_parquet(os.path.join(
        base, "results", f"season={season}", f"results__{race_id}.parquet"))
    meta: dict = {}
    races_path = os.path.join(base, "races", f"season={season}",
                              f"races__{race_id}.parquet")
    if os.path.exists(races_path):
        for row in pd.read_parquet(races_path).itertuples():
            scheduled = getattr(row, "total_laps_scheduled", None)
            meta[str(row.race_id)] = {
                "scheduled_laps": (None if pd.isna(scheduled)
                                   else int(scheduled))}
    return states, results, meta


def phase2_content_hash() -> str:
    manifest = os.path.join(REPO_ROOT, "docs",
                            "PHASE4_FREEZE_MANIFEST.json")
    with open(manifest) as handle:
        return json.load(handle)["phase2"]["content_hash"]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Offline replay prediction checkpoint backfill.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--race-id", action="append", default=None,
                       help="race to process (repeatable)")
    group.add_argument("--season", action="append", type=int, default=None,
                       help="served season to process (repeatable)")
    group.add_argument("--all-served-races", action="store_true",
                       help="explicit full 2018-2024 backfill")
    parser.add_argument("--checkpoints-dir", default=None,
                        help="artifact root (default: results/v2_replay/"
                             "checkpoints under the repo)")
    parser.add_argument("--dry-run", action="store_true",
                        help="model-free checkpoint selection only")
    parser.add_argument("--force", action="store_true",
                        help="regenerate even valid-complete artifacts")
    parser.add_argument("--resume", action="store_true",
                        help="explicit resume marker (default behavior: "
                             "skip valid-complete artifacts)")
    parser.add_argument("--max-checkpoints", type=int, default=None,
                        help="validation-only deterministic subset: first N "
                             "checkpoints (artifact incomplete by design)")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)
    checkpoints_dir = args.checkpoints_dir or os.path.join(
        REPO_ROOT, DEFAULT_CHECKPOINTS_DIR)
    if args.race_id:
        race_ids = list(args.race_id)
    elif args.season:
        race_ids = [r for season in args.season
                    for r in races_for_season(season)]
    else:
        race_ids = [r for season in SERVED_SEASONS
                    for r in races_for_season(season)]
    for race_id in race_ids:
        require_served(race_id)
    if args.max_checkpoints is not None and args.max_checkpoints < 1:
        raise CheckpointError("--max-checkpoints must be >= 1")

    predictor = history = phase2_hash = None
    if not args.dry_run:
        predictor = SERVING.load_frozen_winner_model()
        history = load_history(V2Paths.resolve())
        phase2_hash = phase2_content_hash()

    generated = skipped = 0
    total_checkpoints = 0
    start_all = time.perf_counter()
    for position, race_id in enumerate(race_ids):
        season = race_season(race_id)
        states, results, meta = load_race_inputs(season, race_id)
        timeline = RP.build_replay_timeline(states)
        series = select_checkpoints(timeline, states)
        leader = sum(1 for c in series.checkpoints
                     if "LEADER_LAP" in c.reasons)
        flag_only = sum(1 for c in series.checkpoints
                        if list(c.reasons) == ["FLAG_TRANSITION"])
        both = series.checkpoint_count - leader - flag_only
        total_checkpoints += series.checkpoint_count
        path = artifact_path(checkpoints_dir, race_id)
        if args.dry_run:
            print(f"{race_id}: frames={timeline.frame_count} "
                  f"checkpoints={series.checkpoint_count} "
                  f"(leader={leader} flag_only={flag_only} both={both}) "
                  f"-> {path} [dry-run]")
            continue
        data_identity = canonical_data_identity(states, race_id)
        start = time.perf_counter()
        engine = RacePredictionEngine(
            RaceStateFeatureBridge(states, history), predictor)
        identity = engine.model_identity
        inputs = cache_identity_inputs(
            series=series, data_identity=data_identity,
            feature_set=identity.feature_set,
            feature_set_version=identity.feature_set_version,
            artifact_sha256=identity.artifact_sha256,
            specification_fingerprint=identity.specification_fingerprint,
            phase2_content_hash=phase2_hash,
            probability_semantics=identity.probability_semantics)
        only = None
        if args.max_checkpoints is not None:
            only = frozenset(c.frame_index for c in
                             series.checkpoints[:args.max_checkpoints])
        service = ReplayReconstructor(
            timeline, RaceStateReconstructor(states, results,
                                             race_meta=meta or None))
        status, _ = ensure_race_artifact(
            path=path, series=series, replay_service=service, engine=engine,
            model_identity=identity.to_dict(), identity_inputs=inputs,
            force=args.force, only_frames=only)
        elapsed = time.perf_counter() - start
        size = os.path.getsize(path)
        if status == "skipped":
            skipped += 1
        else:
            generated += 1
        remaining = ""
        if len(race_ids) > 1 and position + 1 < len(race_ids):
            per_race = (time.perf_counter() - start_all) / (position + 1)
            eta_min = per_race * (len(race_ids) - position - 1) / 60
            remaining = f" eta~{eta_min:.1f} min"
        print(f"{race_id}: frames={timeline.frame_count} "
              f"checkpoints={series.checkpoint_count} {status} "
              f"{elapsed:.1f}s {size / 1024:.0f} KiB -> {path}{remaining}")
    elapsed_all = time.perf_counter() - start_all
    print(f"done: races={len(race_ids)} checkpoints={total_checkpoints} "
          f"generated={generated} skipped={skipped} "
          f"{elapsed_all:.1f}s total")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
