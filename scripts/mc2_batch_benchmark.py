"""P1 benchmark: deterministic state-level multiprocessing proof (post-V3.8).

Builds a deterministic benchmark corpus from frozen D checkpoint states,
runs the batch executor at workers 1/2/4/6/8 on production 5000 futures,
proves exact parity (direct serial == executor w=1 == w=N == P0 fixtures),
and writes all results to results/v3/performance_mc2/p1/.

Writes NOTHING to frozen V3.8 locations. Read-only w.r.t. science inputs.
"""

from __future__ import annotations

import hashlib
import json
import platform
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from raceintel.simulation.mc2_batch import (  # noqa: E402
    EXECUTOR_VERSION,
    Mc2StateTask,
    default_workers,
    run_batch,
)

P1 = ROOT / "results" / "v3" / "performance_mc2" / "p1"
P0 = ROOT / "results" / "v3" / "performance_mc2" / "p0"
WORKER_MATRIX = (1, 2, 4, 6, 8)
PRODUCTION_SIMS = 5000


def canon_hash(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def build_corpus() -> list:
    """Deterministic rule (fixed BEFORE timing, outcome-blind): per race
    with stored D runs, the first 2 state_ids in sorted order."""
    import collections

    ckpt = json.loads(
        (ROOT / "results" / "v3" / "v3_8d"
         / "mc2_checkpoint.json").read_text())["mc2_out"]
    by_race: dict = collections.defaultdict(list)
    for sid, doc in ckpt.items():
        by_race[sid.split("|")[0]].append(
            (sid, doc["frame_index"], doc["fold_through"]))
    corpus = []
    for race in sorted(by_race):
        for sid, frame, through in sorted(by_race[race])[:2]:
            corpus.append({
                "race_id": race, "state_id": sid,
                "frame_index": frame, "fold_through": through,
            })
    return corpus


def direct_serial(tasks: list) -> dict:
    """Pre-P1 direct path (no executor): frozen prep + run_mc2 in-process."""
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "scripts"))
    from dataclasses import replace

    import run_v3_2e_backtest as B2E
    from raceintel.simulation.mc2.kernel import run_mc2
    from raceintel.simulation.mc2.variance import (
        RegimeStat,
        select_variance,
    )
    from raceintel.simulation.params import (
        load_simulation_parameters,
        parameter_storage_dir,
    )

    out = {}
    params_cache: dict = {}
    for t in tasks:
        through = t.fold_through
        if through not in params_cache:
            params_cache[through] = load_simulation_parameters(
                parameter_storage_dir(ROOT, through))
        params = params_cache[through]
        sys.path.insert(0, str(ROOT / "scripts"))
        import run_v3_2d_diagnostics as D2

        svc, _ = D2._service_for(t.race_id)
        del svc
        import pandas as pd

        season = int(t.race_id[:4])
        res = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "results"
            / f"season={season}" / f"results__{t.race_id}.parquet")
        grid = B2E._grid_map(res)
        sim_state, selection, sampler, mechanisms, _ = (
            B2E._prepare_state_and_mechanisms(
                t.race_id, t.frame_index, params, grid))
        resid = params.family("lap_residual_distribution_s")
        era_e = resid.entries.get(selection.era)
        g_e = resid.entries.get("global")
        sel = select_variance({
            "era": RegimeStat(float(era_e.std or 1.5), era_e.sample_count)
            if era_e and era_e.std else None,
            "global": RegimeStat(float(g_e.std or 1.5), g_e.sample_count)
            if g_e and g_e.std else None})
        mechs = {did: replace(m, regime_std_s=sel.std_s, rho=t.rho,
                              ar1_enabled=True)
                 for did, m in mechanisms.items()}
        res = run_mc2(sim_state, selection, sampler, mechs,
                      arm=t.arm, master_seed=t.master_seed,
                      simulation_count=t.simulation_count)
        out[f"{t.race_id}|{t.frame_index}"] = {
            "winner_counts": res["winner_counts"],
            "expected_finish": res["expected_finish"],
            "valid": res["valid"],
        }
    return out


def result_hashes(entries: list) -> dict:
    return {
        e["task"]["race_id"] + "|" + str(e["task"]["frame_index"]):
        canon_hash([e["winner_counts"], e["expected_finish"],
                    e["valid"], sorted(e["drivers"])])
        for e in entries if e["status"] == "complete"
    }


def main() -> int:
    P1.mkdir(parents=True, exist_ok=True)
    corpus = build_corpus()
    (P1 / "benchmark_corpus.json").write_text(json.dumps({
        "schema": "mc2-perf-p1-corpus-v1",
        "selection_rule": "first 2 sorted state_ids per race with stored "
                          "D runs (fixed before timing; outcome-blind)",
        "simulation_count": PRODUCTION_SIMS,
        "states": corpus,
    }, indent=1, sort_keys=True))
    print(f"corpus: {len(corpus)} states", flush=True)
    tasks = [Mc2StateTask(c["race_id"], c["frame_index"],
                          c["fold_through"],
                          simulation_count=PRODUCTION_SIMS)
             for c in corpus]

    # direct-serial reference on the 3 P0 fixture states (also in corpus?)
    p0fix = json.loads(
        (P0 / "baseline_fixtures.json").read_text())["fixtures"]
    ref_tasks = [Mc2StateTask(f["state"]["race_id"],
                              f["state"]["frame_index"],
                              f["state"]["fold_through"],
                              simulation_count=PRODUCTION_SIMS)
                 for f in p0fix]
    t0 = time.perf_counter()
    serial_ref = direct_serial(ref_tasks)
    serial_ref_s = time.perf_counter() - t0
    print(f"direct serial reference: {serial_ref_s:.1f}s", flush=True)

    matrix = []
    hashes_by_workers = {}
    for w in WORKER_MATRIX:
        t0 = time.perf_counter()
        summary = run_batch(
            tasks, workers=w,
            checkpoint_path=str(P1 / f"checkpoint_w{w}.json"))
        wall = time.perf_counter() - t0
        assert summary["n_complete"] == len(tasks), summary
        assert summary["n_failed"] == 0, summary
        hh = result_hashes(summary["results"])
        hashes_by_workers[str(w)] = hh
        prep_s = sum(e.get("prep_s", 0) for e in summary["results"]
                     if "prep_s" in e)
        run_s = sum(e.get("run_s", 0) for e in summary["results"]
                    if "run_s" in e)
        matrix.append({
            "workers": w, "wall_s": round(wall, 3),
            "executor_wall_s": round(summary["wall_s"], 3),
            "states": len(tasks), "futures_per_state": PRODUCTION_SIMS,
            "sum_prep_s": round(prep_s, 3), "sum_run_s": round(run_s, 3),
            "payload_bytes": summary["payload_bytes"],
        })
        print(f"workers={w} wall={wall:.1f}s", flush=True)

    # executor w=1 on the fixture states + parity vs P0 + direct serial
    exec1 = run_batch(ref_tasks, workers=1)
    exec1_h = result_hashes(exec1["results"])
    parity = {"direct_serial_s": round(serial_ref_s, 3)}
    # exact comparisons
    exec1_full = {f"{e['task']['race_id']}|{e['task']['frame_index']}": e
                  for e in exec1["results"]}
    ok_p0, ok_serial = True, True
    for f in p0fix:
        key = f"{f['state']['race_id']}|{f['state']['frame_index']}"
        e = exec1_full[key]
        if canon_hash(e["winner_counts"]) != f["hashes"]["winner_counts"]:
            ok_p0 = False
        s = serial_ref[key]
        if (e["winner_counts"] != s["winner_counts"]
                or e["expected_finish"] != s["expected_finish"]
                or e["valid"] != s["valid"]):
            ok_serial = False
        parity[key] = {
            "p0_match": canon_hash(e["winner_counts"])
            == f["hashes"]["winner_counts"],
            "direct_serial_match":
                e["winner_counts"] == s["winner_counts"]
                and e["expected_finish"] == s["expected_finish"]
                and e["valid"] == s["valid"],
        }
    parity["p0_fixtures_match"] = ok_p0
    parity["direct_serial_match"] = ok_serial

    # cross-worker invariance on the full corpus
    base = hashes_by_workers["1"]
    cross = {w: (h == base) for w, h in hashes_by_workers.items()}
    parity["cross_worker_identical"] = cross
    parity["all_identical"] = all(cross.values())

    w1 = matrix[0]["wall_s"]
    for row in matrix:
        row["speedup_vs_w1"] = round(w1 / row["wall_s"], 3)
        row["efficiency"] = round(w1 / row["wall_s"] / row["workers"], 3)
        row["states_per_s"] = round(len(tasks) / row["wall_s"], 4)
        row["futures_per_s"] = round(
            len(tasks) * PRODUCTION_SIMS / row["wall_s"], 1)

    (P1 / "worker_matrix.json").write_text(json.dumps({
        "schema": "mc2-perf-p1-matrix-v1",
        "machine": {
            "platform": platform.platform(),
            "cpu_count": __import__("os").cpu_count(),
            "default_workers_policy": f"min(8, cpu, tasks) -> "
            f"{default_workers(len(tasks))} for {len(tasks)} tasks",
        },
        "rows": matrix,
    }, indent=1, sort_keys=True))
    (P1 / "parity_results.json").write_text(json.dumps({
        "schema": "mc2-perf-p1-parity-v1",
        "executor_version": EXECUTOR_VERSION,
        "parity": parity,
    }, indent=1, sort_keys=True))
    (P1 / "benchmark_results.json").write_text(json.dumps({
        "schema": "mc2-perf-p1-benchmark-v1",
        "corpus_states": len(tasks),
        "futures_per_state": PRODUCTION_SIMS,
        "matrix": matrix,
    }, indent=1, sort_keys=True))
    print("parity p0:", ok_p0, "serial:", ok_serial,
          "cross:", all(cross.values()), flush=True)
    if not (ok_p0 and ok_serial and all(cross.values())):
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
