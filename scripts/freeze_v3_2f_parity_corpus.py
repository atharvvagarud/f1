#!/usr/bin/env python3
"""V3.2F DRY_GREEN MC2-E parity corpus freezer + verifier (Parts C/Y).

Freezes a deterministic 50-checkpoint corpus of accepted-MC2-E (arm
E_AR1_RESIDUAL) outputs BEFORE any V3.2F change, then re-verifies
bit-exact equality after V3.2F work.

Selection: deterministic spread over the frozen V3.2E evaluated
population (2020-2024 x EARLY/MID/LATE x race_id order), so every corpus
member is a proven MC2-E-runnable DRY_GREEN checkpoint.

Invocation reuses the exact frozen V3.2E path
(``run_v3_2e_backtest._prepare_state_and_mechanisms`` + ``run_mc2`` arm
E with rho=0.264, era/global variance selection, empirical scaling), the
same master seed and n_runs on freeze and verify. No simulator source,
parameter, artifact, or replay cache is modified. No model training.
Output carries no timestamps, usernames, or absolute paths.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

OUT_DIR = ROOT / "results" / "v3" / "v3_2f"
CORPUS_PATH = OUT_DIR / "dry_green_parity_corpus.json"

PARITY_SEED = 20240101
PARITY_RUNS = 500
CORPUS_SIZE = 50
N_WORKERS = 8


def _hash(obj) -> str:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def select_corpus(pop: dict, size: int = CORPUS_SIZE) -> list:
    """Deterministic season x stage stratified pick (race_id, frame order).

    Quota: 10 per eval season (2020-2024) -> 50; within a season take
    round-robin over stages (EARLY/MID/LATE) in (race_id, frame) order so
    circuits, field sizes, and anchor-history depths spread naturally.
    """
    by_key: dict = {}
    for e in pop["evaluated"]:
        by_key.setdefault((e["season"], e["stage"]), []).append(e)
    for k in by_key:
        by_key[k].sort(key=lambda x: (x["race_id"], x["frame_index"]))
    corpus = []
    seasons = sorted({e["season"] for e in pop["evaluated"]})
    per_season = size // len(seasons)
    for season in seasons:
        stages = ["EARLY", "MID", "LATE"]
        buckets = [by_key.get((season, s), []) for s in stages]
        idx = [0, 0, 0]
        taken = []
        while len(taken) < per_season and any(
                idx[i] < len(buckets[i]) for i in range(3)):
            for i in range(3):
                if len(taken) >= per_season:
                    break
                if idx[i] < len(buckets[i]):
                    taken.append(buckets[i][idx[i]])
                    idx[i] += 1
        corpus.extend(taken)
    corpus.sort(key=lambda x: (x["season"], x["race_id"], x["frame_index"]))
    assert len(corpus) == size, f"corpus={len(corpus)} != {size}"
    return corpus


def _run_arm_e(entry: dict) -> dict:
    import run_v3_2e_backtest as E2
    from raceintel.simulation.mc2.kernel import run_mc2
    from raceintel.simulation.mc2.variance import (
        RegimeStat,
        select_variance,
    )
    from raceintel.simulation.params import (
        load_simulation_parameters,
        parameter_storage_dir,
    )

    params = load_simulation_parameters(
        parameter_storage_dir(ROOT, entry["fold_through"]))
    sim_state, selection, sampler, mechanisms, _ = \
        E2._prepare_state_and_mechanisms(
            entry["race_id"], entry["frame_index"], params,
            _grid_for(entry["race_id"], entry["season"]))
    roster = sorted(d.driver_id for d in sim_state.drivers)
    assert roster == sorted(entry["roster"]), "roster drift vs population"
    resid = params.family("lap_residual_distribution_s")
    era = selection.era
    emp_std = next(
        (float(resid.entries[k].std)
         for k in (era, "global")
         if resid.entries.get(k) and resid.entries[k].std), 1.5)
    mechs = {}
    for did, m in mechanisms.items():
        era_e = resid.entries.get(era)
        g_e = resid.entries.get("global")
        sel = select_variance({
            "era": RegimeStat(float(era_e.std or 1.5), era_e.sample_count)
            if era_e and era_e.std else None,
            "global": RegimeStat(float(g_e.std or 1.5), g_e.sample_count)
            if g_e and g_e.std else None})
        mechs[did] = replace(m, regime_std_s=sel.std_s, rho=0.264,
                             ar1_enabled=True)
    res = run_mc2(sim_state, selection, sampler, mechs,
                  arm="E_AR1_RESIDUAL", master_seed=PARITY_SEED,
                  simulation_count=PARITY_RUNS,
                  empirical_std_s=emp_std)
    return {
        "race_id": entry["race_id"], "season": entry["season"],
        "frame_index": entry["frame_index"], "stage": entry["stage"],
        "fold_through": entry["fold_through"], "roster": roster,
        "valid": res["valid"], "invalid": res["invalid"],
        "winner_counts": res["winner_counts"],
        "winner_frequency": res["winner_frequency"],
        "expected_finish": res["expected_finish"],
        "position_counts": res["position_counts"],
        "sample_order": res["sample_order"],
        "kernel": res["kernel"], "arm": res["arm"],
    }


_GRID_CACHE: dict = {}


def _grid_for(race_id: str, season: int) -> dict:
    import pandas as pd

    if race_id not in _GRID_CACHE:
        results = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "results" /
            f"season={season}/results__{race_id}.parquet")
        grid = {}
        for row in results.itertuples():
            g = getattr(row, "grid_position", None)
            grid[str(row.driver_id)] = (
                None if g is None or (isinstance(g, float) and g != g)
                else float(g))
        _GRID_CACHE[race_id] = grid
    return _GRID_CACHE[race_id]


def _worker(payload: dict) -> dict:
    try:
        return {"ok": True, "result": _run_arm_e(payload)}
    except Exception as exc:  # noqa: BLE001 - typed worker error
        return {"ok": False, "race_id": payload.get("race_id"),
                "frame_index": payload.get("frame_index"),
                "error": f"{type(exc).__name__}: {exc}"}


def cmd_freeze() -> int:
    import concurrent.futures

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pop = json.loads(
        (ROOT / "results" / "v3" / "v3_2e" / "population.json")
        .read_text(encoding="utf-8"))
    corpus = select_corpus(pop)
    t0 = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(
            max_workers=N_WORKERS) as pool:
        outs = list(pool.map(_worker, corpus))
    failures = [o for o in outs if not o.get("ok")]
    if failures:
        print(json.dumps({"status": "FREEZE_FAILED",
                          "failures": failures}, indent=2))
        return 1
    results = [o["result"] for o in outs]
    results.sort(key=lambda r: (r["season"], r["race_id"],
                                r["frame_index"]))
    doc = {
        "schema_version": "v3.2f-parity-corpus-v1",
        "mc2_arm": "E_AR1_RESIDUAL",
        "master_seed": PARITY_SEED,
        "n_runs": PARITY_RUNS,
        "corpus_size": len(results),
        "member_keys": [[r["race_id"], r["frame_index"]] for r in results],
        "results": results,
        "wall_clock_s": round(time.perf_counter() - t0, 1),
    }
    doc["corpus_hash"] = _hash(
        {k: v for k, v in doc.items() if k != "corpus_hash"})
    CORPUS_PATH.write_text(json.dumps(doc, indent=2,
                                      sort_keys=True) + "\n",
                           encoding="utf-8")
    print(json.dumps({"status": "FROZEN",
                      "corpus_hash": doc["corpus_hash"],
                      "members": len(results),
                      "wall_clock_s": doc["wall_clock_s"]}))
    return 0


def _canon(obj):
    """Order-insensitive canonical form for identity comparison.

    V3.2G fix: the frozen corpus was written with sort_keys=True, so
    nested int-keyed count dicts were serialized in lexicographic
    string order while fresh runs build them in numeric insertion
    order. Values are identical; only serialization order differs.
    Canonicalization compares science, not key order. The frozen
    corpus bytes and hash are untouched.
    """
    if isinstance(obj, dict):
        return {str(k): _canon(obj[k]) for k in sorted(
            obj, key=lambda k: str(k))}
    if isinstance(obj, (list, tuple)):
        return [_canon(v) for v in obj]
    return obj


def cmd_verify() -> int:
    import concurrent.futures

    frozen = json.loads(CORPUS_PATH.read_text(encoding="utf-8"))
    corpus = [
        {"race_id": r["race_id"], "season": r["season"],
         "frame_index": r["frame_index"], "stage": r["stage"],
         "fold_through": r["fold_through"], "roster": r["roster"]}
        for r in frozen["results"]
    ]
    with concurrent.futures.ProcessPoolExecutor(
            max_workers=N_WORKERS) as pool:
        outs = list(pool.map(_worker, corpus))
    failures = [o for o in outs if not o.get("ok")]
    mismatches = []
    if not failures:
        by_key = {(r["race_id"], r["frame_index"]): r
                  for r in frozen["results"]}
        for o in outs:
            r = o["result"]
            ref = by_key[(r["race_id"], r["frame_index"])]
            a = {k: _canon(r[k]) for k in ("valid", "invalid",
                                           "winner_counts",
                                           "winner_frequency",
                                           "expected_finish",
                                           "position_counts",
                                           "sample_order")}
            b = {k: _canon(ref[k]) for k in a}
            if _hash(a) != _hash(b):
                mismatches.append(
                    {"race_id": r["race_id"],
                     "frame_index": r["frame_index"]})
    status = ("PARITY_OK" if not failures and not mismatches
              else "PARITY_FAILED")
    print(json.dumps({"status": status,
                      "members": len(corpus),
                      "failures": failures,
                      "mismatches": mismatches,
                      "corpus_hash": frozen["corpus_hash"]}, indent=2))
    return 0 if status == "PARITY_OK" else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=("freeze", "verify"))
    args = ap.parse_args()
    return cmd_freeze() if args.command == "freeze" else cmd_verify()


if __name__ == "__main__":
    raise SystemExit(main())
