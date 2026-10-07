"""V3.2E post-analysis verification: determinism, convergence, performance.

Runs AFTER analyze_v3_2e_results.py (needs the proposed verdict arm for
convergence). Writes determinism.json, convergence.json,
performance.json, run_count_decision.json.
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

OUT = ROOT / "results" / "v3" / "v3_2e"
CONVERGENCE_COUNTS = (100, 500, 1000, 5000)
CONVERGENCE_SEASONS = (2020, 2022, 2024)


def _save(name: str, obj: dict) -> None:
    (OUT / name).write_text(
        json.dumps(obj, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _canon(obj: dict) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=str)


def _json_norm(obj: dict) -> dict:
    """Normalize through a JSON round-trip (int dict keys become strings).

    fold_results.json persists through JSON, so a fresh in-memory result
    must be normalized the same way before comparison; otherwise identical
    values with int-vs-str keys compare unequal. Python floats round-trip
    exactly, so normalization cannot mask a real numeric difference.
    """
    return json.loads(json.dumps(obj, sort_keys=True, allow_nan=False,
                                 default=str))


def main() -> None:
    pop = json.loads((OUT / "population.json").read_text(encoding="utf-8"))
    fold = json.loads((OUT / "fold_results.json").read_text(encoding="utf-8"))
    verdict = json.loads(
        (OUT / "scientific_verdict.json").read_text(encoding="utf-8"))
    arm = {"KEEP_MC2_E": "E_AR1_RESIDUAL",
           "KEEP_SIMPLER_ARM_B": "B_DRIVER_ANCHOR",
           "KEEP_SIMPLER_ARM_C": "C_DRIVER_ANCHOR_PLUS_DYNAMICS",
           "KEEP_SIMPLER_ARM_D": "D_CONDITIONED_VARIANCE",
           "RETAIN_R3": "A_R3_BASELINE"}[verdict["proposed"]]
    n_runs, seed = fold["n_runs"], fold["master_seed"]

    from run_v3_2e_backtest import _worker_task

    # --- determinism: first evaluated checkpoint of each fold ---
    seen, det_picks = set(), []
    for e in sorted(pop["evaluated"],
                    key=lambda x: (x["season"], x["race_id"],
                                   x["frame_index"])):
        f = ("D1" if e["season"] in (2020, 2021)
             else "D2" if e["season"] in (2022, 2023) else "D3")
        if f not in seen:
            seen.add(f)
            det_picks.append(e)
    det_rows = []
    for e in det_picks:
        job = {"race_id": e["race_id"], "frame_index": e["frame_index"],
               "fold_through": e["fold_through"], "n_runs": n_runs,
               "master_seed": seed, "roster": e["roster"]}
        rerun = _worker_task(job)
        orig = next(c for c in fold["checkpoints"]
                    if c["race_id"] == e["race_id"]
                    and c["frame_index"] == e["frame_index"])
        match = True
        for a in ("A_R3_BASELINE", "B_DRIVER_ANCHOR",
                  "C_DRIVER_ANCHOR_PLUS_DYNAMICS", "D_CONDITIONED_VARIANCE",
                  "E_AR1_RESIDUAL"):
            ro, rn = dict(orig[a]), dict(rerun[a])
            ro.pop("seconds", None)
            rn.pop("seconds", None)
            if _canon(ro) != _canon(_json_norm(rn)):
                match = False
        det_rows.append({"race_id": e["race_id"],
                         "frame_index": e["frame_index"], "match": match})
    _save("determinism.json", {
        "schema_version": "v3.2e-determinism-v1",
        "population_hash": pop["population_hash"],
        "n_runs": n_runs, "master_seed": seed,
        "checks": det_rows,
        "all_match": all(r["match"] for r in det_rows)})
    print("determinism:", all(r["match"] for r in det_rows), flush=True)

    # --- convergence on verdict arm: 3 seasons x stages ---
    import pandas as pd
    from dataclasses import replace

    from raceintel.simulation.config import Assumptions, SimulationConfig
    from raceintel.simulation.engine import ExecutionPolicy
    from raceintel.simulation.mc2.kernel import run_mc2
    from raceintel.simulation.monte_carlo import MonteCarloEngine
    from raceintel.simulation.params import (
        load_simulation_parameters,
        parameter_storage_dir,
    )
    from run_v3_2e_backtest import (
        _grid_map,
        _prepare_state_and_mechanisms,
    )

    conv_picks = []
    for season in CONVERGENCE_SEASONS:
        for stage in ("EARLY", "MID", "LATE"):
            cands = sorted(
                [e for e in pop["evaluated"]
                 if e["season"] == season and e["stage"] == stage],
                key=lambda x: (x["race_id"], x["frame_index"]))
            if cands:
                conv_picks.append(cands[0])
    conv_rows = []
    for e in conv_picks:
        params = load_simulation_parameters(
            parameter_storage_dir(ROOT, e["fold_through"]))
        results_df = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "results" /
            f"season={e['season']}/results__{e['race_id']}.parquet")
        sim_state, selection, sampler, mechanisms, _ = \
            _prepare_state_and_mechanisms(
                e["race_id"], e["frame_index"], params,
                _grid_map(results_df))
        freqs, secs = [], []
        counts = list(CONVERGENCE_COUNTS)
        if e["stage"] == "MID":
            counts = counts + [10000]
        for n in counts:
            t0 = time.perf_counter()
            if arm == "A_R3_BASELINE":
                res = MonteCarloEngine(chunk_size=512).run(
                    sim_state, params,
                    SimulationConfig(simulation_count=n, master_seed=seed,
                                     pit_dynamics_enabled=False),
                    Assumptions(),
                    execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
                freq = {s.driver_id: s.win_probability
                        for s in res.driver_summaries}
            else:
                mechs = {}
                for did, m in mechanisms.items():
                    rho, ar1 = (0.264, True) if arm == "E_AR1_RESIDUAL" \
                        else (0.0, False)
                    mechs[did] = replace(m, rho=rho, ar1_enabled=ar1)
                out = run_mc2(sim_state, selection, sampler, mechs, arm=arm,
                              master_seed=seed, simulation_count=n)
                freq = out["winner_frequency"]
            secs.append(time.perf_counter() - t0)
            freqs.append(freq)
        ref = freqs[-1]
        tvs = [0.5 * sum(abs(f.get(d, 0.0) - ref.get(d, 0.0))
                         for d in set(f) | set(ref)) for f in freqs]
        conv_rows.append({"race_id": e["race_id"], "season": e["season"],
                          "stage": e["stage"], "frame_index": e["frame_index"],
                          "counts": counts, "winner_tv_vs_max": tvs,
                          "seconds": secs})
        print(f"converged {e['race_id']}@{e['frame_index']}", flush=True)
    _save("convergence.json", {
        "schema_version": "v3.2e-convergence-v1",
        "population_hash": pop["population_hash"],
        "arm": arm, "master_seed": seed, "rows": conv_rows})

    # --- run-count decision (TV<=0.005 at some n, else DEFER) ---
    decision, evidence = "DEFER", {}
    for target in (1000, 5000, 10000):
        vals = []
        for r in conv_rows:
            if target in r["counts"]:
                vals.append(r["winner_tv_vs_max"][r["counts"].index(target)])
        if vals:
            evidence[str(target)] = {
                "mean_tv": sum(vals) / len(vals), "max_tv": max(vals),
                "n_checkpoints": len(vals)}
    for target in ("1000", "5000", "10000"):
        if target in evidence and evidence[target]["max_tv"] <= 0.005:
            decision = target
            break
    _save("run_count_decision.json", {
        "schema_version": "v3.2e-runcount-v1",
        "population_hash": pop["population_hash"],
        "criterion": "TV<=0.005 max over convergence checkpoints",
        "evidence": evidence, "decision": decision})

    # --- performance from backtest timings + catalogue cost ---
    perf = {}
    for a in ("A_R3_BASELINE", "B_DRIVER_ANCHOR",
              "C_DRIVER_ANCHOR_PLUS_DYNAMICS", "D_CONDITIONED_VARIANCE",
              "E_AR1_RESIDUAL"):
        secs = sum(c[a]["seconds"] for c in fold["checkpoints"])
        runs = fold["n_runs"] * len(fold["checkpoints"])
        perf[a] = {"checkpoints": len(fold["checkpoints"]),
                   "seconds_total": secs,
                   "runs_per_sec": runs / secs if secs else 0}
    rps = perf[arm]["runs_per_sec"]
    catalogue = {}
    if rps:
        for n in (1000, 5000, 10000):
            serial_h = 2305 * n / rps / 3600
            catalogue[f"n{n}"] = {
                "serial_hours": serial_h,
                "parallel_4w_hours": serial_h / (4 * 0.7),
                "parallel_8w_hours": serial_h / (8 * 0.7),
                "basis": "MEASURED runs/sec, EXTRAPOLATED to 2305 states at 0.7 parallel efficiency"}
    _save("performance.json", {
        "schema_version": "v3.2e-performance-v1",
        "population_hash": pop["population_hash"],
        "arms": perf, "verdict_arm": arm,
        "catalogue_estimate": catalogue})
    print("verification complete; run-count:", decision, flush=True)


if __name__ == "__main__":
    main()
