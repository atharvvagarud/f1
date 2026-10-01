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
from raceintel.replay import replay as RP
from raceintel.config import V2Paths
from raceintel.features.build_matrix import load_history
from raceintel.model_lab import serving as SERVING
from raceintel.prediction import RacePredictionEngine
from raceintel.race_state.race_state_features import RaceStateFeatureBridge
from raceintel.race_state.race_state_reconstruction import RaceStateReconstructor
from raceintel.replay.replay_predictions import (
    DEFAULT_CHECKPOINTS_DIR,
    REPLAY_PREDICTION_CONTRACT_VERSION,
    CheckpointCacheError,
    CheckpointError,
    artifact_path,
    build_artifact,
    cache_identity_inputs,
    cache_key,
    canonical_data_identity,
    ensure_race_artifact,
    load_validated_artifact,
    select_checkpoints,
    write_artifact,
)
from raceintel.replay.replay_reconstruction import ReplayReconstructor


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


def _season_d9_path(base: str, season: int) -> str:
    return os.path.join(
        base, "driver_lap_state_d9", f"season={season}",
        f"driver_lap_state_d9__d9-{season}.parquet")


class SeasonStatesCache:
    """E1 Class-A reuse: read-once per-season D9 frame (read-only).

    The season frame is NEVER mutated: per-race slices are ``.copy()``s
    with identical rows, order, dtypes and values as a fresh per-race
    parquet read (verified by E1 equivalence test). No cross-season
    contamination: frames are keyed by season and only same-season
    race_ids are sliced from them. Scientific operators see exactly the
    rows the baseline path provided.
    """

    def __init__(self, base: str):
        self._base = base
        self._frames: dict = {}

    def season_frame(self, season: int) -> pd.DataFrame:
        frame = self._frames.get(season)
        if frame is None:
            frame = pd.read_parquet(_season_d9_path(self._base, season))
            self._frames[season] = frame
        return frame

    def race_states(self, season: int, race_id: str) -> pd.DataFrame:
        states = self.season_frame(season)
        sliced = states[states["race_id"] == race_id].copy()
        if len(sliced) == 0:
            raise CheckpointError(f"no canonical rows for race {race_id!r}")
        return sliced


def load_race_inputs(season: int, race_id: str, season_cache=None):
    base = os.path.join(REPO_ROOT, "data", "v2", "processed")
    if season_cache is not None:
        states = season_cache.race_states(season, race_id)
    else:
        states = pd.read_parquet(_season_d9_path(base, season))
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
                         help="explicit resume marker: valid-complete "
                              "artifacts are skipped by default with or "
                              "without this flag; it changes nothing")
    parser.add_argument("--workers", type=int, default=1,
                        help="E1 race-granularity parallelism: number of "
                             "worker processes, each owning complete races "
                             "(default 1 = serial baseline path)")
    parser.add_argument("--progress-manifest", default=None,
                        help="E1 additive builder-only audit manifest path "
                             "(operational metadata; never read by serving)")
    parser.add_argument("--max-checkpoints", type=int, default=None,
                        help="validation-only deterministic subset: first N "
                             "checkpoints (artifact incomplete by design)")
    parser.add_argument("--feature-source", default="matrix",
                        choices=("matrix", "recompute"),
                        help="E1.6 feature origin: 'matrix' exact frozen "
                             "Phase-2 lookup (default, E1.5-proven "
                             "identical) or 'recompute' original frozen "
                             "engine reference path")
    return parser


def _sha256_file(path: str) -> str:
    import hashlib
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def build_one_race(race_id: str, *, checkpoints_dir: str, predictor,
                   history, phase2_hash: str, force: bool,
                   max_checkpoints, season_cache=None,
                   feature_source: str = "matrix", matrix=None) -> dict:
    """One complete race build (shared serial/parallel body).

    ``feature_source="recompute"`` is the E1 scientifically authoritative
    reference path (frozen engine per checkpoint).
    ``feature_source="matrix"`` (default) resolves ALL_84 via exact
    frozen Phase-2 matrix lookup (E1.5-proven identical). Both produce
    the same scientific artifact and cache key. Returns an operational
    record (never part of prediction science).
    """
    if feature_source not in ("matrix", "recompute"):
        raise CheckpointError(
            f"feature_source must be 'matrix' or 'recompute', got "
            f"{feature_source!r}")
    if feature_source == "matrix" and matrix is None:
        raise CheckpointError(
            "feature_source='matrix' requires a FrozenReplayFeatureMatrix")
    season = race_season(race_id)
    start = time.perf_counter()
    states, results, meta = load_race_inputs(
        season, race_id, season_cache=season_cache)
    timeline = RP.build_replay_timeline(states)
    series = select_checkpoints(timeline, states)
    data_identity = canonical_data_identity(states, race_id)
    bridge = RaceStateFeatureBridge(states, history)
    engine = RacePredictionEngine(bridge, predictor)
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
    if max_checkpoints is not None:
        only = frozenset(c.frame_index for c in
                         series.checkpoints[:max_checkpoints])
    service = ReplayReconstructor(
        timeline, RaceStateReconstructor(states, results,
                                         race_meta=meta or None))
    path = artifact_path(checkpoints_dir, race_id)
    if feature_source == "matrix":
        from scripts.replay_feature_matrix import (
            AcceleratedReplayPredictionBuilder)
        status = None
        if not force and only is None and os.path.exists(path):
            try:
                load_validated_artifact(
                    path, expected_inputs=inputs, series=series)
                status = "skipped"
            except CheckpointCacheError:
                pass
            except (json.JSONDecodeError, UnicodeDecodeError,
                    OSError) as exc:
                print(f"{race_id}: unreadable artifact ({exc}); "
                      f"regenerating")
                try:
                    os.unlink(path)
                except OSError:
                    pass
        if status is None:
            accelerated = AcceleratedReplayPredictionBuilder(
                matrix, predictor, identity)
            snapshots = accelerated.build_snapshots(
                series, service, bridge)
            if only is not None:
                snapshots = {k: v for k, v in snapshots.items()
                             if k in only}
            artifact = build_artifact(
                series, snapshots, identity.to_dict(), inputs)
            write_artifact(path, artifact)
            status = "generated"
    else:
        try:
            status, _ = ensure_race_artifact(
                path=path, series=series, replay_service=service,
                engine=engine, model_identity=identity.to_dict(),
                identity_inputs=inputs, force=force, only_frames=only)
        except (json.JSONDecodeError, UnicodeDecodeError, OSError) as exc:
            # E1 resume hardening (builder-only): the frozen validator
            # raises raw decode/IO errors on a truncated or unreadable file
            # instead of a CheckpointCacheError. Such a file is by
            # definition not a valid-complete artifact: remove and
            # regenerate loudly (generation errors still propagate from
            # the forced retry below).
            print(f"{race_id}: unreadable artifact ({exc}); regenerating")
            try:
                os.unlink(path)
            except OSError:
                pass
            status, _ = ensure_race_artifact(
                path=path, series=series, replay_service=service,
                engine=engine, model_identity=identity.to_dict(),
                identity_inputs=inputs, force=True, only_frames=only)
    elapsed = time.perf_counter() - start
    record = {
        "race_id": race_id,
        "frames": timeline.frame_count,
        "checkpoint_count": series.checkpoint_count,
        "cache_key": cache_key(inputs),
        "artifact_path": path,
        "artifact_sha256": _sha256_file(path),
        "runtime_s": elapsed,
        "status": status,
    }
    return record


_WORKER_STATE: dict = {}


def _worker_init(checkpoints_dir: str, force: bool, max_checkpoints,
                 feature_source: str = "matrix") -> None:
    """Load model/history/matrix once per worker process (read-only)."""
    _WORKER_STATE["checkpoints_dir"] = checkpoints_dir
    _WORKER_STATE["force"] = force
    _WORKER_STATE["max_checkpoints"] = max_checkpoints
    _WORKER_STATE["feature_source"] = feature_source
    _WORKER_STATE["predictor"] = SERVING.load_frozen_winner_model()
    _WORKER_STATE["history"] = load_history(V2Paths.resolve())
    _WORKER_STATE["phase2_hash"] = phase2_content_hash()
    _WORKER_STATE["season_cache"] = SeasonStatesCache(
        os.path.join(REPO_ROOT, "data", "v2", "processed"))
    if feature_source == "matrix":
        from scripts.replay_feature_matrix import FrozenReplayFeatureMatrix
        _WORKER_STATE["matrix"] = FrozenReplayFeatureMatrix.load(REPO_ROOT)
    else:
        _WORKER_STATE["matrix"] = None


def _worker_build(race_id: str) -> dict:
    """Worker entry: build one complete race (owns the race exclusively)."""
    return build_one_race(
        race_id, checkpoints_dir=_WORKER_STATE["checkpoints_dir"],
        predictor=_WORKER_STATE["predictor"],
        history=_WORKER_STATE["history"],
        phase2_hash=_WORKER_STATE["phase2_hash"],
        force=_WORKER_STATE["force"],
        max_checkpoints=_WORKER_STATE["max_checkpoints"],
        season_cache=_WORKER_STATE["season_cache"],
        feature_source=_WORKER_STATE["feature_source"],
        matrix=_WORKER_STATE["matrix"])


def write_progress_manifest(path: str, *, records: list, run_meta: dict,
                            total_checkpoints: int, total_s: float) -> None:
    """E1 additive builder-only audit manifest (atomic publish)."""
    payload = {
        "manifest_format": "replay-build-manifest-v1",
        "run": run_meta,
        "race_count": len(records),
        "checkpoint_count": total_checkpoints,
        "total_runtime_s": total_s,
        "races": sorted(records, key=lambda r: r["race_id"]),
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    import tempfile
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(text)
        json.loads(text)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


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

    if args.workers is not None and args.workers < 1:
        raise CheckpointError("--workers must be >= 1")

    predictor = history = phase2_hash = matrix = None
    if not args.dry_run:
        predictor = SERVING.load_frozen_winner_model()
        history = load_history(V2Paths.resolve())
        phase2_hash = phase2_content_hash()
        if args.feature_source == "matrix":
            from scripts.replay_feature_matrix import (
                FrozenReplayFeatureMatrix)
            matrix = FrozenReplayFeatureMatrix.load(REPO_ROOT)

    generated = skipped = 0
    total_checkpoints = 0
    start_all = time.perf_counter()
    records: list = []
    season_cache = SeasonStatesCache(
        os.path.join(REPO_ROOT, "data", "v2", "processed"))
    if args.dry_run:
        for race_id in race_ids:
            season = race_season(race_id)
            states, _, _ = load_race_inputs(
                season, race_id, season_cache=season_cache)
            timeline = RP.build_replay_timeline(states)
            series = select_checkpoints(timeline, states)
            leader = sum(1 for c in series.checkpoints
                         if "LEADER_LAP" in c.reasons)
            flag_only = sum(1 for c in series.checkpoints
                            if list(c.reasons) == ["FLAG_TRANSITION"])
            both = series.checkpoint_count - leader - flag_only
            total_checkpoints += series.checkpoint_count
            path = artifact_path(checkpoints_dir, race_id)
            print(f"{race_id}: frames={timeline.frame_count} "
                  f"checkpoints={series.checkpoint_count} "
                  f"(leader={leader} flag_only={flag_only} both={both}) "
                  f"-> {path} [dry-run]")
    elif args.workers > 1:
        from concurrent.futures import ProcessPoolExecutor
        with ProcessPoolExecutor(
                max_workers=args.workers,
                initializer=_worker_init,
                initargs=(checkpoints_dir, args.force,
                          args.max_checkpoints,
                          args.feature_source)) as pool:
            for position, record in enumerate(
                    pool.map(_worker_build, race_ids)):
                records.append(record)
                total_checkpoints += record["checkpoint_count"]
                if record["status"] == "skipped":
                    skipped += 1
                else:
                    generated += 1
                size = os.path.getsize(record["artifact_path"])
                remaining = ""
                if len(race_ids) > 1 and position + 1 < len(race_ids):
                    per_race = ((time.perf_counter() - start_all)
                                / (position + 1))
                    eta_min = (per_race
                               * (len(race_ids) - position - 1) / 60)
                    remaining = f" eta~{eta_min:.1f} min"
                print(f"{record['race_id']}: frames={record['frames']} "
                      f"checkpoints={record['checkpoint_count']} "
                      f"{record['status']} {record['runtime_s']:.1f}s "
                      f"{size / 1024:.0f} KiB "
                      f"-> {record['artifact_path']}{remaining}")
    else:
        for position, race_id in enumerate(race_ids):
            record = build_one_race(
                race_id, checkpoints_dir=checkpoints_dir,
                predictor=predictor, history=history,
                phase2_hash=phase2_hash, force=args.force,
                max_checkpoints=args.max_checkpoints,
                season_cache=season_cache,
                feature_source=args.feature_source, matrix=matrix)
            records.append(record)
            total_checkpoints += record["checkpoint_count"]
            size = os.path.getsize(record["artifact_path"])
            if record["status"] == "skipped":
                skipped += 1
            else:
                generated += 1
            remaining = ""
            if len(race_ids) > 1 and position + 1 < len(race_ids):
                per_race = (time.perf_counter() - start_all) / (position + 1)
                eta_min = per_race * (len(race_ids) - position - 1) / 60
                remaining = f" eta~{eta_min:.1f} min"
            print(f"{race_id}: frames={record['frames']} "
                  f"checkpoints={record['checkpoint_count']} "
                  f"{record['status']} "
                  f"{record['runtime_s']:.1f}s {size / 1024:.0f} KiB "
                  f"-> {record['artifact_path']}{remaining}")
    elapsed_all = time.perf_counter() - start_all
    print(f"done: races={len(race_ids)} checkpoints={total_checkpoints} "
          f"generated={generated} skipped={skipped} "
          f"{elapsed_all:.1f}s total")
    if args.progress_manifest is not None and not args.dry_run:
        import subprocess as _sp
        try:
            commit = _sp.run(
                ["git", "rev-parse", "HEAD"], capture_output=True,
                text=True, cwd=REPO_ROOT).stdout.strip()
        except Exception:  # noqa: BLE001 - metadata only
            commit = "unknown"
        write_progress_manifest(
            args.progress_manifest, records=records,
            run_meta={"workers": args.workers, "commit": commit,
                      "force": bool(args.force),
                      "max_checkpoints": args.max_checkpoints,
                      "feature_source": args.feature_source},
            total_checkpoints=total_checkpoints, total_s=elapsed_all)
        print(f"manifest -> {args.progress_manifest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
