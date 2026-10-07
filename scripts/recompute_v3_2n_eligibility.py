#!/usr/bin/env python3
"""V3.2N Parts H/I/J/K: final eligibility catalogue (2 passes), blockers.

Recomputes all 9644 checkpoints with final accepted behavior
(prepare_initial_state + J status corpus/windows). Pass A and pass B run
in-process from fresh objects; catalogue written only if identical.
No 2025. No network. Deterministic.
"""

from __future__ import annotations

import glob
import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from raceintel.race_state.race_state_reconstruction import (  # noqa: E402
    RaceStateReconstructor,
)
from raceintel.replay import replay as RP  # noqa: E402
from raceintel.replay.replay_reconstruction import ReplayReconstructor  # noqa: E402
from raceintel.simulation.driver_status import (  # noqa: E402
    load_status_corpus,
    load_unreliable_windows,
)
from raceintel.simulation.engine import ExecutionPolicy  # noqa: E402
from raceintel.simulation.params import (  # noqa: E402
    load_simulation_parameters,
    parameter_storage_dir,
)
from raceintel.simulation.presence import (  # noqa: E402
    prepare_initial_state,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = PROJECT_ROOT / "data" / "v2" / "processed"
CHECKPOINTS_DIR = PROJECT_ROOT / "results" / "v2_replay" / "checkpoints"
JOUT = PROJECT_ROOT / "results" / "v3" / "v3_2j"
FOUT = PROJECT_ROOT / "results" / "v3" / "v3_2f"
OUT = PROJECT_ROOT / "results" / "v3" / "v3_2n"


def season_of(race_id: str) -> int:
    return int(race_id.split("-")[0])


def stage_for(fraction) -> str | None:
    if fraction is None:
        return None
    if fraction < 1.0 / 3.0:
        return "EARLY"
    if fraction < 2.0 / 3.0:
        return "MID"
    return "LATE"


def _grid_map(results: pd.DataFrame) -> dict:
    out = {}
    for row in results.itertuples():
        grid = getattr(row, "grid_position", None)
        if grid is None or (isinstance(grid, float) and grid != grid):
            out[str(row.driver_id)] = None
        else:
            out[str(row.driver_id)] = float(grid)
    return out


def one_pass(parameters, resolver, windows) -> list:
    out = []
    for path in sorted(glob.glob(str(CHECKPOINTS_DIR / "*.json"))):
        artifact = json.load(open(path, encoding="utf-8"))
        race_id = artifact["race_id"]
        season = season_of(race_id)
        assert season != 2025
        base = str(PROCESSED)
        frame = pd.read_parquet(
            f"{base}/driver_lap_state_d9/season={season}/"
            f"driver_lap_state_d9__d9-{season}.parquet")
        states = frame[frame["race_id"] == race_id].copy()
        results = pd.read_parquet(
            f"{base}/results/season={season}/results__{race_id}.parquet")
        meta: dict = {}
        try:
            for row in pd.read_parquet(
                    f"{base}/races/season={season}/races__{race_id}.parquet"
                    ).itertuples():
                scheduled = getattr(row, "total_laps_scheduled", None)
                meta[str(row.race_id)] = {
                    "scheduled_laps": (None if pd.isna(scheduled)
                                       else int(scheduled))}
        except FileNotFoundError:
            pass
        grid = _grid_map(results)
        timeline = RP.build_replay_timeline(states)
        service = ReplayReconstructor(
            timeline, RaceStateReconstructor(states, results,
                                             race_meta=meta or None))
        for entry in artifact["checkpoints"]:
            fi = entry["checkpoint"]["frame_index"]
            try:
                race_state = service.state_at(fi)
            except Exception as exc:  # noqa: BLE001
                out.append({
                    "race_id": race_id, "season": season,
                    "frame_index": fi, "verdict": "RECONSTRUCTION_FAILURE",
                    "reason": type(exc).__name__, "dns_excluded": [],
                    "status_excluded": [],
                    "stage": None, "leader_lap": None})
                continue
            result = prepare_initial_state(
                race_state, grid_by_driver=grid, parameters=parameters,
                execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT,
                status_resolver=resolver, status_windows=windows)
            scheduled_laps = race_state.race_context.scheduled_laps
            leader_done = race_state.race_context.race_leader_laps_at_state
            fraction = (leader_done / scheduled_laps
                        if scheduled_laps and leader_done is not None
                        else None)
            out.append({
                "race_id": race_id, "season": season, "frame_index": fi,
                "leader_lap": entry["checkpoint"].get("leader_lap"),
                "stage": stage_for(fraction),
                "fraction": (round(fraction, 4) if fraction is not None
                             else None),
                "verdict": ("SIMULATION_CAPABLE" if result.eligible
                            else result.reason),
                "reason": result.detail,
                "dns_excluded": list(result.excluded_dns_driver_ids),
                "status_excluded": list(result.excluded_status_driver_ids),
                "status_contract": result.status_contract_version,
            })
    return out


def corpus_hash(cps: list) -> str:
    text = json.dumps(sorted(
        (c["race_id"], c["frame_index"], c["verdict"], c["reason"],
         tuple(c["dns_excluded"]), tuple(c["status_excluded"]))
        for c in cps), separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(text.encode()).hexdigest()


def main() -> int:
    t0 = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)
    parameters = load_simulation_parameters(
        parameter_storage_dir(PROJECT_ROOT, 2024))
    resolver = load_status_corpus(JOUT / "status")
    windows = load_unreliable_windows(JOUT / "unreliable_windows.json")
    a = one_pass(parameters, resolver, windows)
    t1 = time.perf_counter()
    print(f"pass A: {len(a)} wall={t1-t0:.0f}s", flush=True)
    b = one_pass(parameters, resolver, windows)
    t2 = time.perf_counter()
    print(f"pass B: {len(b)} wall={t2-t1:.0f}s", flush=True)
    ha, hb = corpus_hash(a), corpus_hash(b)
    det = {"schema_version": "v3.2n-eligibility-determinism-v1",
           "n": len(a), "pass_a_hash": ha, "pass_b_hash": hb,
           "identical": ha == hb}
    json.dump(det, open(OUT / "eligibility_determinism.json", "w"), indent=1)
    if ha != hb:
        raise SystemExit("STOP: eligibility nondeterministic")
    total = len(a)
    elig = sum(1 for c in a if c["verdict"] == "SIMULATION_CAPABLE")
    json.dump({"schema_version": "v3.2n-final-eligibility-catalogue-v1",
               "corpus_hash": ha,
               "total": total, "eligible": elig,
               "ineligible": total - elig,
               "fraction": round(elig / total, 4),
               "expected": {"eligible": 3678, "total": 9644},
               "matches_expected": (elig == 3678 and total == 9644),
               "checkpoints": a},
              open(OUT / "final_eligibility_catalogue.json", "w"))
    print(f"total={total} eligible={elig} hash={ha[:12]}", flush=True)

    # ---- blockers (primary from recount; sets from F raw) ----
    raw = json.load(open(FOUT / "coverage_opportunity_raw.json",
                         encoding="utf-8"))
    raw_by_key = {(c["race_id"], c["frame_index"]): c
                  for c in raw["checkpoints"]}
    primary = Counter(c["verdict"] for c in a)
    refused = [c for c in a if c["verdict"] != "SIMULATION_CAPABLE"]
    inter = Counter()
    for c in refused:
        key = tuple(sorted(raw_by_key[(c["race_id"], c["frame_index"])]
                           ["all_blockers"]))
        inter[key] += 1
    json.dump({"schema_version": "v3.2n-final-blockers-v1",
               "primary": dict(sorted(primary.items())),
               "all_blocker_sets": {"+".join(k) if k else "NONE": v
                                    for k, v in sorted(inter.items())},
               "conservation": sum(primary.values()) == total,
               "refused_total": len(refused)},
              open(OUT / "final_blockers.json", "w"), indent=1)

    # ---- breakdowns ----
    def split(key):
        rows = [c for c in a if key(c) is not None]
        groups: dict = {}
        for c in rows:
            groups.setdefault(key(c), []).append(c)
        return {str(g): {"eligible": sum(1 for c in items if c["verdict"]
                                         == "SIMULATION_CAPABLE"),
                         "total": len(items)}
                for g, items in sorted(groups.items(), key=lambda x: str(x[0]))}
    json.dump({"schema_version": "v3.2n-coverage-final-v1",
               "total": total, "eligible": elig,
               "fraction": round(elig / total, 4)},
              open(OUT / "coverage_final.json", "w"), indent=1)
    json.dump({"schema_version": "v3.2n-coverage-by-season-v1",
               "by_season": split(lambda c: c["season"])},
              open(OUT / "coverage_by_season.json", "w"), indent=1)
    json.dump({"schema_version": "v3.2n-coverage-by-stage-v1",
               "by_stage": split(lambda c: c["stage"])},
              open(OUT / "coverage_by_stage.json", "w"), indent=1)
    races: dict = {}
    for c in a:
        races.setdefault(c["race_id"], []).append(c)
    race_rows = [{"race_id": rid, "season": items[0]["season"],
                  "eligible": sum(1 for c in items if c["verdict"]
                                  == "SIMULATION_CAPABLE"),
                  "total": len(items)} for rid, items in sorted(races.items())]
    covs = sorted(r["eligible"] / r["total"] for r in race_rows)
    json.dump({"schema_version": "v3.2n-coverage-by-race-v1",
               "races_with_ge1_supported": sum(1 for r in race_rows
                                               if r["eligible"] >= 1),
               "zero_support_races": sum(1 for r in race_rows
                                         if r["eligible"] == 0),
               "median_race_coverage": covs[len(covs) // 2],
               "ge50": sum(1 for r in race_rows
                           if r["eligible"] / r["total"] >= 0.5),
               "ge75": sum(1 for r in race_rows
                           if r["eligible"] / r["total"] >= 0.75),
               "ge95": sum(1 for r in race_rows
                           if r["eligible"] / r["total"] >= 0.95),
               "full": sum(1 for r in race_rows
                           if r["eligible"] == r["total"]),
               "races": race_rows},
              open(OUT / "coverage_by_race.json", "w"), indent=1)
    print(f"blockers={dict(sorted(primary.items()))} "
          f"wall={time.perf_counter()-t0:.0f}s", flush=True)
    if not (elig == 3678 and total == 9644):
        raise SystemExit("STOP: final eligibility differs from 3678/9644")
    return 0


if __name__ == "__main__":
    sys.exit(main())
