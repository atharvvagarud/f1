#!/usr/bin/env python3
"""V3.2N Parts P/Q/R/S: final validation corpus + 5000-run + determinism.

- Corpus frozen BEFORE scoring (deterministic stratified pick).
- MC2-E arm E at frozen 5000 runs; invariant checks per checkpoint.
- Determinism: --rerun subset in fresh process, compare hashes.
- Convergence: 100/500/1000/5000 TV confirmation on subset.
No 2025. No network. Deterministic.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

OUT = ROOT / "results" / "v3" / "v3_2n"
N_RUNS = 5000
MASTER_SEED = 20240101
N_WORKERS = 8
CORPUS_SIZE = 21  # 7 seasons x 3 stages; relief mixed deterministically


def _hash(obj) -> str:
    return hashlib.sha256(json.dumps(
        obj, sort_keys=True, separators=(",", ":"),
        allow_nan=False, default=str).encode()).hexdigest()


def select_corpus(eligible: list) -> list:
    by_key: dict = {}
    for c in eligible:
        by_key.setdefault((c["season"], c["stage"]), []).append(c)
    # Relief-alternating merge; starting side alternates by bucket index
    # so first-picks mix pre-J and J-relieved deterministically.
    for i, k in enumerate(sorted(by_key)):
        rel = sorted([x for x in by_key[k] if x["status_excluded"]],
                     key=lambda x: (x["race_id"], x["frame_index"]))
        pre = sorted([x for x in by_key[k] if not x["status_excluded"]],
                     key=lambda x: (x["race_id"], x["frame_index"]))
        merged, turn = [], i % 2
        while rel or pre:
            box = rel if turn % 2 == 0 else pre
            other = pre if turn % 2 == 0 else rel
            if box:
                merged.append(box.pop(0))
            elif other:
                merged.append(other.pop(0))
            turn += 1
        by_key[k] = merged
    corpus = []
    for season in range(2018, 2025):
        for stage in ("EARLY", "MID", "LATE"):
            bucket = by_key.get((season, stage), [])
            if bucket:
                corpus.append(bucket[0])
    corpus.sort(key=lambda x: (x["season"], x["race_id"], x["frame_index"]))
    assert len(corpus) == CORPUS_SIZE, f"corpus={len(corpus)}"
    return [{"race_id": c["race_id"], "season": c["season"],
             "frame_index": c["frame_index"], "stage": c["stage"],
             "relieved": bool(c["status_excluded"]),
             "roster": sorted(list(
                 {d for d in c.get("roster", [])} or [])) or None}
            for c in corpus]


def run_one(payload: dict) -> dict:
    import run_v3_2e_backtest as E2
    from raceintel.simulation.mc2.kernel import run_mc2
    from raceintel.simulation.mc2.variance import (
        RegimeStat,
        select_variance,
    )
    from raceintel.simulation.monte_carlo import select_residual_sampler
    from raceintel.simulation.params import (
        load_simulation_parameters,
        parameter_storage_dir,
    )
    from dataclasses import replace

    n_runs = payload["n_runs"]
    seed = payload.get("seed", MASTER_SEED)
    params = load_simulation_parameters(
        parameter_storage_dir(ROOT, 2024))
    sim_state, selection, sampler, mechanisms, _ = \
        E2._prepare_state_and_mechanisms(
            payload["race_id"], payload["frame_index"], params,
            _grid_for(payload["race_id"], payload["season"]))
    roster = sorted(d.driver_id for d in sim_state.drivers)
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
                  arm="E_AR1_RESIDUAL", master_seed=seed,
                  simulation_count=n_runs, empirical_std_s=emp_std)
    return {"race_id": payload["race_id"], "season": payload["season"],
            "frame_index": payload["frame_index"], "n_runs": n_runs,
            "seed": seed, "roster": roster, "valid": res["valid"],
            "invalid": res["invalid"],
            "winner_counts": res["winner_counts"],
            "winner_frequency": res["winner_frequency"],
            "expected_finish": res["expected_finish"],
            "position_counts": res["position_counts"],
            "position_distribution": res["position_distribution"],
            "podium_frequency": res["podium_frequency"],
            "sample_order": res["sample_order"],
            "kernel": res["kernel"], "arm": res["arm"]}


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
        return {"ok": True, "result": run_one(payload)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "race_id": payload.get("race_id"),
                "frame_index": payload.get("frame_index"),
                "error": f"{type(exc).__name__}: {exc}"}


def check_invariants(r: dict) -> list:
    import math
    bad = []
    n = r["n_runs"]
    if r["valid"] != n or r["invalid"] != 0:
        bad.append(f"valid={r['valid']} invalid={r['invalid']} n={n}")
    if sum(r["winner_counts"].values()) != r["valid"]:
        bad.append("winner mass != valid")
    for did, ef in r["expected_finish"].items():
        if not math.isfinite(ef):
            bad.append(f"expected_finish non-finite {did}")
    for did, dist in r["position_distribution"].items():
        s = sum(dist.values())
        if abs(s - 1.0) > 1e-9:
            bad.append(f"position dist unnormalized {did} sum={s}")
        for p, v in dist.items():
            if not (0.0 <= v <= 1.0) or not math.isfinite(v):
                bad.append(f"bad prob {did}@{p}={v}")
    for did, v in r["podium_frequency"].items():
        if not (0.0 <= v <= 1.0) or not math.isfinite(v):
            bad.append(f"bad podium {did}={v}")
    if sorted(r["roster"]) != sorted(r["position_counts"].keys()):
        bad.append("field identity drift")
    return bad


def tv(a: dict, b: dict) -> float:
    keys = set(a) | set(b)
    return 0.5 * sum(abs(a.get(k, 0.0) - b.get(k, 0.0)) for k in keys)


def main() -> int:
    import concurrent.futures
    mode = sys.argv[1] if len(sys.argv) > 1 else "full"
    OUT.mkdir(parents=True, exist_ok=True)
    cat = json.load(open(OUT / "final_eligibility_catalogue.json",
                         encoding="utf-8"))
    elig = [c for c in cat["checkpoints"]
            if c["verdict"] == "SIMULATION_CAPABLE"]
    assert len(elig) == 3678, len(elig)
    corpus = select_corpus(elig)
    json.dump({"schema_version": "v3.2n-final-validation-corpus-v1",
               "corpus_hash": _hash(corpus),
               "size": len(corpus),
               "n_runs_frozen": N_RUNS, "master_seed": MASTER_SEED,
               "rule": "per (season, stage) first of relief-alternating "
                       "sorted list; covers 2018-2024 x EARLY/MID/LATE; "
                       "relieved and pre-J mixed; frozen BEFORE scoring",
               "relieved_count": sum(1 for c in corpus if c["relieved"]),
               "members": corpus},
              open(OUT / "final_validation_corpus.json", "w"), indent=1)
    print(f"corpus={len(corpus)} relieved="
          f"{sum(1 for c in corpus if c['relieved'])}", flush=True)

    if mode == "rerun":
        prev = json.load(open(OUT / "simulation_5000_validation.json",
                              encoding="utf-8"))
        prev_by_key = {(r["race_id"], r["frame_index"]): r
                       for r in prev["results"]}
        sub = corpus[:4]
        outs = [run_one({**c, "n_runs": N_RUNS, "seed": MASTER_SEED})
                for c in sub]
        det = {"schema_version": "v3.2n-determinism-v1", "rows": []}
        ok = True
        for r in outs:
            ref = prev_by_key[(r["race_id"], r["frame_index"])]
            # JSON round-trip both sides: int dict keys serialize as
            # strings on disk; compare in the stored representation so
            # the gate checks science, not serialization (same norm as
            # the F parity test).
            same = _hash(json.loads(json.dumps(r))) == _hash(ref)
            ok &= same
            det["rows"].append(
                {"race_id": r["race_id"], "frame_index": r["frame_index"],
                 "identical": same})
        det["rerun_identical"] = bool(ok)
        json.dump(det, open(OUT / "determinism.json", "w"), indent=1)
        print(f"determinism rerun identical={ok}", flush=True)
        return 0 if ok else 1

    t0 = time.perf_counter()
    jobs = [{**c, "n_runs": N_RUNS, "seed": MASTER_SEED} for c in corpus]
    with concurrent.futures.ProcessPoolExecutor(
            max_workers=N_WORKERS) as pool:
        outs = list(pool.map(_worker, jobs))
    wall = time.perf_counter() - t0
    fails = [o for o in outs if not o.get("ok")]
    if fails:
        raise SystemExit(f"STOP: sim failures: {fails[:3]}")
    results = [o["result"] for o in outs]
    inv = {}
    for r in results:
        bad = check_invariants(r)
        if bad:
            inv[f"{r['race_id']}@{r['frame_index']}"] = bad
    total_runs = sum(r["n_runs"] for r in results)
    json.dump({"schema_version": "v3.2n-simulation-5000-validation-v1",
               "n_runs": N_RUNS, "master_seed": MASTER_SEED,
               "n_checkpoints": len(results),
               "wall_clock_s": round(wall, 1),
               "runs_per_sec": round(total_runs / wall, 1),
               "invariant_violations": inv,
               "all_invariants_pass": not inv,
               "results": sorted(results, key=lambda r: (
                   r["season"], r["race_id"], r["frame_index"]))},
              open(OUT / "simulation_5000_validation.json", "w"))
    print(f"5000-run done n={len(results)} wall={wall:.0f}s "
          f"violations={len(inv)}", flush=True)
    if inv:
        raise SystemExit(f"STOP: invariant violations: {list(inv)[:3]}")

    # ---- convergence confirmation (subset, 100/500/1000/5000) ----
    sub = corpus[:6]
    conv = {"schema_version": "v3.2n-convergence-confirmation-v1",
            "note": "confirmation only; 5000 frozen; no tuning", "rows": []}
    for c in sub:
        dists = {}
        for n in (100, 500, 1000, 5000):
            r = run_one({**{k: c[k] for k in (
                "race_id", "season", "frame_index")},
                "n_runs": n, "seed": MASTER_SEED})
            dists[n] = r["winner_frequency"]
        conv["rows"].append(
            {"race_id": c["race_id"], "frame_index": c["frame_index"],
             "tv_100_vs_5000": round(tv(dists[100], dists[5000]), 4),
             "tv_500_vs_5000": round(tv(dists[500], dists[5000]), 4),
             "tv_1000_vs_5000": round(tv(dists[1000], dists[5000]), 4)})
    json.dump(conv, open(OUT / "convergence_confirmation.json", "w"), indent=1)
    print("convergence: " + str([
        (r["race_id"], r["tv_1000_vs_5000"]) for r in conv["rows"]]),
        flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
