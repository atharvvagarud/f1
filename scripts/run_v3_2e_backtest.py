"""V3.2E controlled temporal backtest (development of the scientific verdict).

Phase order (preregistration gate FIRST):
  0. verify V3.2D + V3.2E preregistration hashes, abort on mismatch
  1. population: V3.2C-eligible eval-season checkpoints, re-verified under
     fold parameters + truth availability; hash population identity
  2. blind precision pilot (no truth): arm E repeat-TV gate on n_runs
  3. backtest: all 5 frozen arms on identical states (8 workers)
  4. scoring: R7 metrics, race-macro aggregation, paired bootstrap
  5. determinism rerun, convergence, performance, verdict proposal

Temporal policy: fold evaluating Y uses through-(Y-1) parameters only.
2025 is never read (firewalled + asserted). Truth is joined AFTER
simulation outputs are frozen per checkpoint.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import random
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
OUT.mkdir(parents=True, exist_ok=True)

V3_2D_PREREG_HASH = "dc0ae2dbade08514ed3b7cbf5e4be965edccf40b60d7bcad86c99f245854ee16"
EVAL_SEASONS = (2020, 2021, 2022, 2023, 2024)
FOLD_THROUGH = {2020: 2019, 2021: 2019, 2022: 2021, 2023: 2021, 2024: 2023}
ARMS = ("A_R3_BASELINE", "B_DRIVER_ANCHOR", "C_DRIVER_ANCHOR_PLUS_DYNAMICS",
        "D_CONDITIONED_VARIANCE", "E_AR1_RESIDUAL")
N_WORKERS = 8


def _hash(obj: dict) -> str:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def verify_preregs() -> dict:
    d2 = json.loads(
        (ROOT / "results" / "v3" / "v3_2d" / "preregistration.json")
        .read_text(encoding="utf-8"))
    h2 = _hash({k: v for k, v in d2.items() if k != "prereg_hash"})
    if h2 != V3_2D_PREREG_HASH or d2.get("prereg_hash") != V3_2D_PREREG_HASH:
        raise SystemExit("V3.2D preregistration mismatch: BLOCKED")
    e = json.loads((OUT / "preregistration.json").read_text(encoding="utf-8"))
    he = _hash({k: v for k, v in e.items() if k != "prereg_hash"})
    if he != e.get("prereg_hash"):
        raise SystemExit("V3.2E preregistration mismatch: BLOCKED")
    return e


# ---------------------------------------------------------------------------
# Phase 1: population.
# ---------------------------------------------------------------------------

def _grid_map(results):
    out = {}
    for row in results.itertuples():
        grid = getattr(row, "grid_position", None)
        out[str(row.driver_id)] = (
            None if grid is None or (isinstance(grid, float)
                                     and grid != grid) else float(grid))
    return out


def build_population() -> tuple:
    import pandas as pd

    from raceintel.race_state.race_state_reconstruction import (
        RaceStateReconstructor,
    )
    from raceintel.replay import replay as RP
    from raceintel.replay.replay_reconstruction import ReplayReconstructor
    from raceintel.simulation.engine import ExecutionPolicy
    from raceintel.simulation.params import (
        load_simulation_parameters,
        parameter_storage_dir,
    )
    from raceintel.simulation.presence import prepare_initial_state

    coverage = json.loads(
        (ROOT / "results" / "v3" / "v3_2c_coverage.json").read_text())
    cand = [c for c in coverage["checkpoints"]
            if c.get("verdict") == "SIMULATION_CAPABLE"
            and c.get("season") in EVAL_SEASONS]
    by_race: dict[str, list] = {}
    for c in cand:
        by_race.setdefault(c["race_id"], []).append(c)

    params_cache = {}
    evaluated, excluded = [], []
    for race_id in sorted(by_race):
        season = int(race_id[:4])
        if season == 2025 or "2025" in race_id:
            raise SystemExit("2025 firewall violation in population")
        through = FOLD_THROUGH[season]
        if through not in params_cache:
            params_cache[through] = load_simulation_parameters(
                parameter_storage_dir(ROOT, through))
        params = params_cache[through]
        base = ROOT / "data" / "v2" / "processed"
        try:
            results = pd.read_parquet(
                base / f"results/season={season}/results__{race_id}.parquet")
        except FileNotFoundError:
            for c in by_race[race_id]:
                excluded.append({**c, "exclude_reason": "truth_unavailable"})
            continue
        winners = results[results["winner_flag"] == True]  # noqa: E712
        if len(winners) != 1:
            for c in by_race[race_id]:
                excluded.append({**c, "exclude_reason": "truth_no_winner"})
            continue
        winner = str(winners.iloc[0]["driver_id"])
        podium = sorted(str(d) for d in
                        results[results["podium_flag"] == True]["driver_id"])  # noqa: E712
        order = {}
        for row in results.itertuples():
            cp = getattr(row, "classified_position", None)
            if cp is not None and pd.notna(cp):
                order[str(row.driver_id)] = int(cp)
        states = pd.read_parquet(
            base / f"driver_lap_state_d9/season={season}/"
            f"driver_lap_state_d9__d9-{season}.parquet")
        states = states[states["race_id"] == race_id].copy()
        meta = {}
        rp = base / f"races/season={season}/races__{race_id}.parquet"
        if rp.exists():
            for row in pd.read_parquet(rp).itertuples():
                meta[str(row.race_id)] = {
                    "scheduled_laps":
                        (None if pd.isna(row.total_laps_scheduled)
                         else int(row.total_laps_scheduled))}
        timeline = RP.build_replay_timeline(states)
        service = ReplayReconstructor(
            timeline, RaceStateReconstructor(states, results,
                                             race_meta=meta or None))
        grid = _grid_map(results)
        for c in sorted(by_race[race_id], key=lambda x: x["frame_index"]):
            try:
                race_state = service.state_at(c["frame_index"])
            except Exception as exc:  # noqa: BLE001 - recorded exclusion
                excluded.append(
                    {**c, "exclude_reason": f"reconstruction:{type(exc).__name__}"})
                continue
            verdict = prepare_initial_state(
                race_state, grid_by_driver=grid, parameters=params,
                execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
            if not verdict.eligible:
                excluded.append(
                    {**c, "exclude_reason": f"fold_param:{verdict.reason}"})
                continue
            roster = list(verdict.active_driver_ids)
            if winner not in roster:
                excluded.append(
                    {**c, "exclude_reason": "winner_not_in_roster"})
                continue
            evaluated.append({
                "race_id": race_id, "season": season,
                "frame_index": c["frame_index"], "stage": c.get("stage"),
                "fraction": c.get("fraction"),
                "fold_through": through, "roster": roster,
                "dns_excluded": list(verdict.excluded_dns_driver_ids),
                "truth_winner": winner, "truth_podium": podium,
                "truth_order": {d: order[d] for d in roster if d in order},
            })
    pop = {
        "schema_version": "v3.2e-population-v1",
        "rule": "V3.2C-eligible + fold-param eligible + truth available",
        "candidate_checkpoints": len(cand),
        "evaluated_checkpoints": len(evaluated),
        "excluded_checkpoints": len(excluded),
        "races": sorted(set(e["race_id"] for e in evaluated)),
        "evaluated": evaluated,
        "excluded": [{"race_id": x["race_id"], "season": x.get("season"),
                      "frame_index": x["frame_index"],
                      "reason": x["exclude_reason"]} for x in excluded],
    }
    pop["population_hash"] = _hash(
        {k: v for k, v in pop.items() if k != "population_hash"})
    return pop, params_cache


# ---------------------------------------------------------------------------
# Worker: all 5 arms on one checkpoint (frozen science, deterministic).
# ---------------------------------------------------------------------------

_WORKER_SEASON_CACHE: dict = {}


def _prepare_state_and_mechanisms(race_id: str, frame_index: int,
                                  params, grid: dict):
    """Prepared SimulationState + frozen-E mechanisms (V3.2D science).

    Uses the frozen V3.2C presence path (DNS exclusion, then the unchanged
    R2 adapter), then the exact V3.2D mechanism computation. Never calls
    the winner model; all history inputs are <= T.
    """
    import dataclasses

    import run_v3_2d_diagnostics as D2
    from raceintel.simulation.adapter import from_race_state
    from raceintel.simulation.engine import (
        expected_lap_time_s,
        select_pace_parameters,
    )
    from raceintel.simulation.mc2.anchor import PastLap, compute_anchor
    from raceintel.simulation.mc2.kernel import DriverMechanism
    from raceintel.simulation.monte_carlo import select_residual_sampler
    from raceintel.simulation.presence import (
        dns_exclusions,
        without_drivers,
    )

    svc, states = D2._service_for(race_id)
    race_state = svc.state_at(frame_index)
    # Frozen V3.2C DNS exclusion (same function prepare_initial_state
    # uses internally): unobserved AND no pre-race grid slot.
    dns = dns_exclusions(race_state, grid)
    active = without_drivers(race_state, dns) if dns else race_state
    sim_state = from_race_state(active)
    selection = select_pace_parameters(sim_state, params)
    sampler = select_residual_sampler(params, selection.era)
    t_s = float(race_state.state_time_s)
    df = states[states["race_id"] == race_id]
    clean = D2._clean_history(df, t_s)
    timeline = df.sort_values("state_time_s")
    timeline = timeline.assign(
        _ref=timeline["lap_number"].fillna(0).astype(int).cummax())
    ref_by_time = dict(zip(timeline["state_time_s"].astype(float).tolist(),
                           timeline["_ref"].tolist()))
    anchor_age = {d.driver_id: int(d.tyre_age) for d in sim_state.drivers}
    mechanisms: dict[str, DriverMechanism] = {}
    diag = {"n_clean": {}, "fallback": {}, "slope_l3": {}, "slope_l10": {}}
    for d in sim_state.drivers:
        g = clean[clean["driver_id"] == d.driver_id]
        laps, devs = [], []
        base = (selection.base.value
                + selection.offset_for(d.constructor_id).value)
        for row in g.itertuples():
            row_ref = int(ref_by_time.get(float(row.state_time_s),
                                          selection.reference_lap))
            sel = dataclasses.replace(selection, reference_lap=row_ref)
            mu, _, _ = expected_lap_time_s(
                sel, base, int(row.lap_number), float(row.tyre_life),
                anchor_age[d.driver_id])
            laps.append(int(row.lap_number))
            devs.append(float(row.lap_time_s) - mu)
        past = [PastLap(lap_time_s=dev + 0.0, expected_s=0.0,
                        lap_number=lp)
                for dev, lp in zip(devs[-8:], laps[-8:])]
        anchor = compute_anchor(past)
        s3 = D2._slope_endpoint(devs, laps, 3, 3)
        s10 = D2._slope_endpoint(devs, laps, 10, 5)
        mechanisms[d.driver_id] = DriverMechanism(
            anchor_offset_s=anchor.offset_s, slope_l3=s3, slope_l10=s10)
        diag["n_clean"][d.driver_id] = anchor.n_clean
        diag["fallback"][d.driver_id] = anchor.fallback
        diag["slope_l3"][d.driver_id] = s3
        diag["slope_l10"][d.driver_id] = s10
    return sim_state, selection, sampler, mechanisms, diag


def _worker_task(job: dict) -> dict:
    """All 5 frozen arms on one checkpoint (never raises: typed errors).

    R3/MC2 share the exact prepared state; the roster is cross-checked
    against the population record. Any failure returns {"__error__": ...}
    so a worker crash can never lose the pool or poison the comparison.
    """
    from dataclasses import replace

    try:
        import pandas as pd

        from raceintel.simulation.config import Assumptions, SimulationConfig
        from raceintel.simulation.engine import ExecutionPolicy
        from raceintel.simulation.mc2.kernel import run_mc2
        from raceintel.simulation.mc2.variance import (
            RegimeStat,
            select_variance,
        )
        from raceintel.simulation.monte_carlo import MonteCarloEngine
        from raceintel.simulation.params import (
            load_simulation_parameters,
            parameter_storage_dir,
        )

        race_id, frame = job["race_id"], job["frame_index"]
        through, n_runs, seed = (job["fold_through"], job["n_runs"],
                                 job["master_seed"])
        key = (through,)
        if key not in _WORKER_SEASON_CACHE:
            _WORKER_SEASON_CACHE[key] = load_simulation_parameters(
                parameter_storage_dir(ROOT, through))
        params = _WORKER_SEASON_CACHE[key]
        season = int(race_id[:4])
        results = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "results" /
            f"season={season}/results__{race_id}.parquet")
        grid = _grid_map(results)

        sim_state, selection, sampler, mechanisms, diag = \
            _prepare_state_and_mechanisms(race_id, frame, params, grid)
        roster = sorted(d.driver_id for d in sim_state.drivers)
        if roster != sorted(job["roster"]):
            return {"race_id": race_id, "frame_index": frame,
                    "__error__": "roster_mismatch_vs_population"}
    except Exception as exc:  # noqa: BLE001 - typed worker error
        return {"race_id": job.get("race_id"),
                "frame_index": job.get("frame_index"),
                "__error__": f"{type(exc).__name__}: {exc}"}

    try:
        t0 = time.perf_counter()
        arm_a = MonteCarloEngine(chunk_size=512).run(
            sim_state, params,
            SimulationConfig(simulation_count=n_runs, master_seed=seed,
                             pit_dynamics_enabled=False),
            Assumptions(),
            execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
        t_a = time.perf_counter() - t0
        a_summaries = {}
        for s in arm_a.driver_summaries:
            a_summaries[s.driver_id] = {
                "win": s.win_probability, "podium": s.podium_probability,
                "exp": s.expected_finish,
                "posdist": {int(p.position): float(p.frequency)
                            for p in s.finish_position_distribution},
            }
        out = {"race_id": race_id, "frame_index": frame,
               "A_R3_BASELINE": {
                   "valid": arm_a.valid_simulation_count,
                   "invalid": arm_a.invalid_simulation_count,
                   "summaries": a_summaries, "seconds": t_a},
               "anchor_diag": {"n_clean": diag["n_clean"],
                               "fallback": diag["fallback"]}}

        resid = params.family("lap_residual_distribution_s")
        era = selection.era
        emp_std = next(
            (float(resid.entries[k].std)
             for k in (era, "global")
             if resid.entries.get(k) and resid.entries[k].std), 1.5)
        for arm in ("B_DRIVER_ANCHOR", "C_DRIVER_ANCHOR_PLUS_DYNAMICS",
                    "D_CONDITIONED_VARIANCE", "E_AR1_RESIDUAL"):
            mechs = {}
            for did, m in mechanisms.items():
                std, rho, ar1 = m.regime_std_s, 0.0, False
                if arm in ("D_CONDITIONED_VARIANCE", "E_AR1_RESIDUAL"):
                    era_e = resid.entries.get(era)
                    g_e = resid.entries.get("global")
                    sel = select_variance({
                        "era": RegimeStat(float(era_e.std or 1.5),
                                          era_e.sample_count)
                        if era_e and era_e.std else None,
                        "global": RegimeStat(float(g_e.std or 1.5),
                                             g_e.sample_count)
                        if g_e and g_e.std else None})
                    std = sel.std_s
                if arm == "E_AR1_RESIDUAL":
                    rho, ar1 = 0.264, True
                mechs[did] = replace(m, regime_std_s=std, rho=rho,
                                     ar1_enabled=ar1)
            t0 = time.perf_counter()
            res = run_mc2(sim_state, selection, sampler, mechs, arm=arm,
                          master_seed=seed, simulation_count=n_runs,
                          empirical_std_s=emp_std)
            dt = time.perf_counter() - t0
            out[arm] = {
                "valid": res["valid"], "invalid": res["invalid"],
                "winner_frequency": res["winner_frequency"],
                "podium_frequency": res["podium_frequency"],
                "expected_finish": res["expected_finish"],
                "position_distribution": res["position_distribution"],
                "seconds": dt}
        return out
    except Exception as exc:  # noqa: BLE001 - typed worker error
        return {"race_id": race_id, "frame_index": frame,
                "__error__": f"{type(exc).__name__}: {exc}"}


def _summaries_for_entry(entry: dict, arm: str) -> dict:
    if arm == "A_R3_BASELINE":
        s = entry[arm]["summaries"]
        return {"win": {d: v["win"] for d, v in s.items()},
                "podium": {d: v["podium"] for d, v in s.items()},
                "exp": {d: v["exp"] for d, v in s.items()},
                "posdist": {d: v["posdist"] for d, v in s.items()}}
    e = entry[arm]
    return {"win": e["winner_frequency"], "podium": e["podium_frequency"],
            "exp": e["expected_finish"],
            "posdist": e["position_distribution"]}


# ---------------------------------------------------------------------------
# Phase 2: blind precision pilot (no truth).
# ---------------------------------------------------------------------------

def blind_pilot(pop: dict, seed: int) -> tuple:
    import pandas as pd
    from dataclasses import replace

    from raceintel.simulation.mc2.kernel import run_mc2
    from raceintel.simulation.params import (
        load_simulation_parameters,
        parameter_storage_dir,
    )

    picks = []
    for stage in ("EARLY", "MID", "LATE"):
        cands = sorted(
            [e for e in pop["evaluated"] if e["stage"] == stage],
            key=lambda x: (x["season"], x["race_id"], x["frame_index"]))
        picks.extend(cands[:2])
    tvs = []
    params_cache = {}
    for entry in picks:
        through = entry["fold_through"]
        if through not in params_cache:
            params_cache[through] = load_simulation_parameters(
                parameter_storage_dir(ROOT, through))
        params = params_cache[through]
        season = entry["season"]
        results = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "results" /
            f"season={season}/results__{entry['race_id']}.parquet")
        grid = _grid_map(results)
        sim_state, selection, sampler, mechanisms, _ = \
            _prepare_state_and_mechanisms(
                entry["race_id"], entry["frame_index"], params, grid)
        mechs = {did: replace(m, rho=0.264, ar1_enabled=True)
                 for did, m in mechanisms.items()}
        outs = [run_mc2(sim_state, selection, sampler, mechs,
                        arm="E_AR1_RESIDUAL", master_seed=seed + k,
                        simulation_count=1000)
                for k in (0, 1)]
        roster = entry["roster"]
        tv = 0.5 * sum(abs(outs[0]["winner_frequency"].get(d, 0.0)
                           - outs[1]["winner_frequency"].get(d, 0.0))
                       for d in roster)
        tvs.append(tv)
    return picks, tvs


# ---------------------------------------------------------------------------
# Phase 4: scoring with R7 metrics.
# ---------------------------------------------------------------------------

def score_backtest(fold_results: list, pop_lookup: dict) -> dict:
    from raceintel.simulation import validation as V7

    cp_rows = []
    for entry, res in fold_results:
        pop = pop_lookup[(entry["race_id"], entry["frame_index"])]
        winner, podium = pop["truth_winner"], set(pop["truth_podium"])
        order = pop["truth_order"]
        classified = [d for d in entry_roster(entry) if d in order]
        row = {"race_id": entry["race_id"], "season": entry["season"],
               "stage": entry["stage"], "frame_index": entry["frame_index"],
               "arms": {}}
        for arm in ARMS:
            s = _summaries_for_entry(res, arm)
            win = {d: float(s["win"].get(d, 0.0))
                   for d in entry_roster(entry)}
            tot = sum(win.values())
            win = {d: v / tot for d, v in win.items()} if tot > 0 else win
            wll = V7.winner_log_loss(win, winner)
            br = V7.brier_score(win, winner)
            pod = {d: float(s["podium"].get(d, 0.0))
                   for d in entry_roster(entry)}
            pod_br = sum((pod[d] - (1.0 if d in podium else 0.0)) ** 2
                         for d in pod) / len(pod)
            exp = {d: float(s["exp"][d]) for d in entry_roster(entry)}
            mae = V7.expected_finish_mae(
                exp, order, classified) if classified else None
            rps_vals = []
            for d in classified:
                dist = {int(k): float(v)
                        for k, v in s["posdist"][d].items()}
                try:
                    rps_vals.append(V7.ranked_probability_score(dist, order[d]))
                except Exception:  # noqa: BLE001 - recorded as None
                    rps_vals.append(None)
            rps_vals = [v for v in rps_vals if v is not None]
            rps = sum(rps_vals) / len(rps_vals) if rps_vals else None
            top1 = V7.top_k_winner_accuracy(win, winner, k=1)
            top3 = V7.top_k_winner_accuracy(win, winner, k=3)
            top_p = max(win.values())
            row["arms"][arm] = {
                "valid": res[arm]["valid"], "invalid": res[arm]["invalid"],
                "winner_logloss": wll, "winner_brier": br,
                "podium_brier": pod_br, "exp_mae": mae, "rps": rps,
                "top1": bool(top1), "top3": bool(top3),
                "top_prob": top_p,
                "top_is_winner": bool(max(win, key=lambda d: (win[d], d))
                                      == winner),
            }
        cp_rows.append(row)
    return cp_rows


def entry_roster(entry: dict) -> list:
    if "roster" in entry:
        return list(entry["roster"])
    return sorted(entry["A_R3_BASELINE"]["summaries"])


def race_macro(cp_rows: list) -> dict:
    by_race: dict[str, list] = {}
    for row in cp_rows:
        by_race.setdefault(row["race_id"], []).append(row)
    races = {}
    for race_id, rows in by_race.items():
        agg: dict = {"n_checkpoints": len(rows),
                     "season": rows[0]["season"],
                     "stages": sorted(set(r["stage"] for r in rows)),
                     "arms": {}}
        for arm in ARMS:
            vals = {}
            for m in ("winner_logloss", "winner_brier", "podium_brier",
                      "exp_mae", "rps", "top_prob"):
                vs = [r["arms"][arm][m] for r in rows
                      if r["arms"][arm][m] is not None]
                vals[m] = sum(vs) / len(vs) if vs else None
            for m in ("top1", "top3"):
                vs = [r["arms"][arm][m] for r in rows]
                vals[m] = sum(1 for v in vs if v) / len(vs)
            vals["valid"] = sum(r["arms"][arm]["valid"] for r in rows)
            vals["invalid"] = sum(r["arms"][arm]["invalid"] for r in rows)
            agg["arms"][arm] = vals
        races[race_id] = agg
    return races


def paired_bootstrap(diffs: list, seed: int = 42,
                     replicates: int = 2000) -> dict:
    from raceintel.simulation import validation as V7

    out = V7.race_level_bootstrap(diffs, replicates=replicates, seed=seed)
    out["seed"] = seed
    out["replicates"] = replicates
    return out


def main() -> None:
    prereg = verify_preregs()
    print("preregistrations verified", flush=True)
    master_seed = prereg["seeds"]["master_seed"]

    pop, _ = build_population()
    (OUT / "population.json").write_text(
        json.dumps(pop, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"population: {pop['evaluated_checkpoints']} evaluated / "
          f"{pop['excluded_checkpoints']} excluded / "
          f"{len(pop['races'])} races [{pop['population_hash'][:12]}]",
          flush=True)

    picks, pilot_tvs = blind_pilot(pop, master_seed)
    mean_tv = sum(pilot_tvs) / len(pilot_tvs)
    n_runs = prereg["n_runs"]["primary"]
    if mean_tv >= 0.05:
        n_runs = prereg["n_runs"]["escalation"]
    (OUT / "pilot.json").write_text(json.dumps({
        "schema_version": "v3.2e-pilot-v1",
        "checkpoints": [(e["race_id"], e["frame_index"]) for e in picks],
        "repeat_tvs": pilot_tvs, "mean_tv": mean_tv,
        "n_runs_selected": n_runs, "truth_inspected": False,
    }, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"pilot mean repeat-TV={mean_tv:.4f} -> n_runs={n_runs}", flush=True)

    jobs = [{"race_id": e["race_id"], "frame_index": e["frame_index"],
             "fold_through": e["fold_through"], "n_runs": n_runs,
             "master_seed": master_seed, "roster": e["roster"]}
            for e in pop["evaluated"]]
    partial_path = OUT / "fold_results_partial.json"
    done: dict = {}
    if partial_path.exists():
        partial = json.loads(partial_path.read_text(encoding="utf-8"))
        if (partial.get("population_hash") == pop["population_hash"]
                and partial.get("n_runs") == n_runs
                and partial.get("master_seed") == master_seed):
            for r in partial.get("completed", []):
                done[(r["race_id"], r["frame_index"])] = r
            print(f"resumed {len(done)} completed checkpoints", flush=True)
    pending = [j for j in jobs
               if (j["race_id"], j["frame_index"]) not in done]
    results = list(done.values())
    with concurrent.futures.ProcessPoolExecutor(
            max_workers=N_WORKERS) as pool:
        for i, res in enumerate(pool.map(_worker_task, pending)):
            results.append(res)
            if len(results) % 100 == 0:
                partial_path.write_text(json.dumps({
                    "population_hash": pop["population_hash"],
                    "n_runs": n_runs, "master_seed": master_seed,
                    "completed": results,
                }, sort_keys=True) + "\n", encoding="utf-8")
                print(f"backtest {len(results)}/{len(jobs)}", flush=True)
    errors = [r for r in results if "__error__" in r]
    if errors:
        print(f"BLOCKED: {len(errors)} worker errors, e.g. "
              f"{errors[0]}", flush=True)
        raise SystemExit("V3.2E BLOCKED — EVALUATION FAILURE")
    by_key = {(r["race_id"], r["frame_index"]): r for r in results}
    ordered = [by_key[(e["race_id"], e["frame_index"])]
               for e in pop["evaluated"]]
    (OUT / "fold_results.json").write_text(json.dumps({
        "schema_version": "v3.2e-fold-results-v1",
        "population_hash": pop["population_hash"],
        "n_runs": n_runs, "master_seed": master_seed,
        "checkpoints": ordered,
    }, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("fold_results written", flush=True)

    pop_lookup = {(e["race_id"], e["frame_index"]): e
                  for e in pop["evaluated"]}
    entries = [(e, by_key[(e["race_id"], e["frame_index"])])
               for e in pop["evaluated"]]
    cp_rows = score_backtest(entries, pop_lookup)
    (OUT / "checkpoint_scores.json").write_text(json.dumps({
        "schema_version": "v3.2e-checkpoint-scores-v1",
        "population_hash": pop["population_hash"],
        "rows": cp_rows,
    }, indent=1, sort_keys=True) + "\n", encoding="utf-8")

    races = race_macro(cp_rows)
    (OUT / "race_results.json").write_text(json.dumps({
        "schema_version": "v3.2e-race-results-v1",
        "population_hash": pop["population_hash"],
        "races": races,
    }, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print("scoring written", flush=True)


if __name__ == "__main__":
    main()
