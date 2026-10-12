"""V3.7D analysis: aggregates, sentinels, stability, pathology, gate, card."""

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "tests"))

from api.v2_service import load_v2_service  # noqa: E402
from api.v2_simulation_service import build_v2_simulation_service  # noqa: E402
from raceintel.counterfactual import contracts as C  # noqa: E402
from raceintel.counterfactual import engine as E  # noqa: E402
from raceintel.race_state.race_state import AnchorObservation  # noqa: E402
from raceintel.simulation import monte_carlo as mc  # noqa: E402
from raceintel.simulation.adapter import from_race_state  # noqa: E402
from raceintel.simulation.config import Assumptions, SimulationConfig  # noqa: E402
from raceintel.strategy.contracts import StrategyAction  # noqa: E402

D = ROOT / "results" / "v3" / "v3_7d"
RUN = json.loads((D / "run_results.json").read_text())
PROTO = json.loads((D / "evaluation_protocol.json").read_text())
SEED = 20240101


def _cfg(n=5000, seed=SEED):
    return SimulationConfig(simulation_count=n, master_seed=seed,
                            pit_dynamics_enabled=True)


def desc(vals):
    v = np.asarray([x for x in vals if x is not None], dtype=float)
    if v.size == 0:
        return {"n": 0}
    return {"n": int(v.size), "median": float(np.median(v)),
            "q25": float(np.quantile(v, 0.25)),
            "q75": float(np.quantile(v, 0.75)),
            "min": float(v.min()), "max": float(v.max()),
            "frac_positive": float((v > 1e-9).mean()),
            "frac_negative": float((v < -1e-9).mean()),
            "frac_zero": float((np.abs(v) <= 1e-9).mean())}


def main():
    t0 = time.perf_counter()
    fams = {}
    life = {}
    horizon = {}
    for rec in RUN:
        for name, comp in rec["comparisons"].items():
            f = fams.setdefault(name, {"n": 0, "supported": 0,
                                       "unsupported": {}, "pairs": [],
                                       "deltas": {}})
            f["n"] += 1
            if isinstance(comp, dict) and comp.get("supported") is False:
                f["unsupported"][comp.get("reason_code", "?")] = \
                    f["unsupported"].get(comp.get("reason_code", "?"), 0) + 1
                continue
            f["supported"] += 1
            f["pairs"].append(comp["complete_pairs"])
            for k, d in comp["deltas"].items():
                f["deltas"].setdefault(k, []).append(d["point_estimate"])
            for sk, c in comp.get("schedule_outcomes", {}).items():
                life[(name, sk)] = life.get((name, sk), 0) + c
            if name.startswith("N") and name[1].isdigit():
                h = horizon.setdefault(int(name[1]), {"pairs": [], "exec": 0,
                                                      "total": 0, "sup": 0})
                h["pairs"].append(comp["complete_pairs"])
    hist = {
        "anchors": len(RUN),
        "adapted": sum(1 for r in RUN if r["meta"].get("state_identity")),
        "adapter_unsupported": {
            r["meta"].get("unsupported", "?"): 1 for r in RUN
            if not r["meta"].get("state_identity")},
        "adapter_unsupported_count": sum(
            1 for r in RUN if not r["meta"].get("state_identity")),
        "families": {k: {"n": v["n"], "supported": v["supported"],
                         "unsupported": v["unsupported"],
                         "pair_rate": float(np.mean(v["pairs"])) if v["pairs"] else 0.0,
                         "deltas": {k2: desc(v2) for k2, v2 in v["deltas"].items()}}
                     for k, v in fams.items()},
        "lifecycle": {f"{a}/{s}": c for (a, s), c in life.items()},
        "horizon": {str(k): {"pair_rate": float(np.mean(v["pairs"])) if v["pairs"] else 0.0}
                    for k, v in horizon.items()},
    }
    (D / "historical_evaluation.json").write_text(
        json.dumps(hist, sort_keys=True, indent=2) + "\n")

    # --- live sentinel/stability subset ---
    svc = build_v2_simulation_service(load_v2_service())
    params = svc.parameters
    subset = RUN[:12]
    gain_ok = pit_ok = ahead_ok = 0
    gain_tot = pit_tot = ahead_tot = 0
    count_rows, seed_rows, repro_ok = [], [], 0
    parity_ok = 0
    pair_viol = 0
    for rec in subset:
        m = rec["meta"]
        rs = svc._reconstructor.reconstruct(  # noqa: SLF001
            AnchorObservation(race_id=m["race_id"],
                              anchor_driver_id=m["target"],
                              anchor_lap_number=m["decision_lap"],
                              anchor_state_time_s=_t(m)))
        state = from_race_state(rs)
        target = m["target"]
        lap = m["decision_lap"]
        rival = m["rival"]
        plan = _mkplan(state, target, [(target, 2, "MEDIUM")], lap)
        res = E.compare_reference_vs_plan(
            state=state, parameters=params, config=_cfg(),
            assumptions=Assumptions(), plan=plan,
            rival_driver_id=rival)
        # independent recomputation from raw arms
        _, alt_idx, _ = E.run_arm(state, params, _cfg(), Assumptions(), plan)
        _, ref_idx, _ = E.run_arm(state, params, _cfg(), Assumptions(), None)
        mask = (np.asarray(ref_idx["valid"]) & np.asarray(alt_idx["valid"]))
        tcol = list(state.roster_driver_ids).index(target)
        ap = np.asarray(alt_idx["finish_position"])[mask][:, tcol]
        bp = np.asarray(ref_idx["finish_position"])[mask][:, tcol]
        fpos = next(e.position for e in state.drivers if e.driver_id == target)
        gain_tot += 1
        if fpos is not None and abs(float(np.mean(
                [C.position_gain(fpos, int(v)) for v in ap]))
                - res.alternative_aggregate["expected_position_gain"]) < 1e-9:
            gain_ok += 1
        pit_tot += 1
        if abs(float(np.asarray(alt_idx["pit_count"])[mask][:, tcol].mean())
               - res.alternative_aggregate["expected_pit_count"]) < 1e-9:
            pit_ok += 1
        if rival is not None and rival in state.roster_driver_ids:
            ahead_tot += 1
            rcol = list(state.roster_driver_ids).index(rival)
            ar = np.asarray(alt_idx["finish_position"])[mask][:, rcol]
            if abs(float((ap < ar).mean())
                   - res.alternative_aggregate["p_ahead_of_rival"]) < 1e-9:
                ahead_ok += 1
        if res.complete_pairs + res.excluded_pairs != 5000:
            pair_viol += 1
        # count stability on N=2 via run_arm (keys stay 5000-fixed;
        # research counts pair manually by (seed, index) streams)
        row = {"anchor": m["race_id"]}
        for n in (1000, 2500, 5000):
            rb, _ = _arm_pair(state, params, plan, n, SEED)
            row[f"expfinish_{n}"] = rb
        count_rows.append(row)
        # seed stability (independent estimates per seed)
        srow = {"anchor": m["race_id"]}
        for s in (20240101, 7, 99):
            rb, _ = _arm_pair(state, params, plan, 5000, s)
            srow[f"expfinish_{s}"] = rb
        seed_rows.append(srow)
    # reproducibility: first 4 double-run
    for rec in RUN[:4]:
        m = rec["meta"]
        rs = svc._reconstructor.reconstruct(  # noqa: SLF001
            AnchorObservation(race_id=m["race_id"],
                              anchor_driver_id=m["target"],
                              anchor_lap_number=m["decision_lap"],
                              anchor_state_time_s=_t(m)))
        state = from_race_state(rs)
        plan = _mkplan(state, m["target"], [(m["target"], 2, "MEDIUM")],
                       m["decision_lap"])
        a = E.compare_reference_vs_plan(
            state=state, parameters=params, config=_cfg(),
            assumptions=Assumptions(), plan=plan).identity()
        b = E.compare_reference_vs_plan(
            state=state, parameters=params, config=_cfg(),
            assumptions=Assumptions(), plan=plan).identity()
        repro_ok += (a == b)
    # parity on first 8 anchors (engine level, legacy vs schedule)
    from test_v2_phase7_s2_mechanics import intervention as _leg
    for rec in RUN[:8]:
        m = rec["meta"]
        rs = svc._reconstructor.reconstruct(  # noqa: SLF001
            AnchorObservation(race_id=m["race_id"],
                              anchor_driver_id=m["target"],
                              anchor_lap_number=m["decision_lap"],
                              anchor_state_time_s=_t(m)))
        state = from_race_state(rs)
        from raceintel.strategy.contracts import StrategyIntervention
        for action, n in ((StrategyAction.PIT_NOW, 1),
                          (StrategyAction.PIT_NEXT_LAP, 2)):
            e1 = mc.MonteCarloEngine()
            e1.run(state, params, _cfg(), Assumptions(), intervention=StrategyIntervention(
                target_driver_id=m["target"], action=action,
                requested_compound=None, decision_lap=m["decision_lap"],
                decision_state_identity=state.identity()),
                collect_index_outcomes=True)
            e2 = mc.MonteCarloEngine()
            plan = _mkplan(state, m["target"], [(m["target"], n, None)],
                           m["decision_lap"])
            e2.run(state, params, _cfg(), Assumptions(),
                   intervention=E._to_seam(plan), collect_index_outcomes=True)
            parity_ok += bool(np.array_equal(
                e1.last_index_outcomes["finish_position"],
                e2.last_index_outcomes["finish_position"]))
    # --- CRN diagnostic: paired vs independent-stream CI width ---
    crn_rows = []
    for rec in subset[:6]:
        m = rec["meta"]
        if not m.get("state_identity"):
            continue
        rs = svc._reconstructor.reconstruct(  # noqa: SLF001
            AnchorObservation(race_id=m["race_id"],
                              anchor_driver_id=m["target"],
                              anchor_lap_number=m["decision_lap"],
                              anchor_state_time_s=_t(m)))
        state = from_race_state(rs)
        plan = _mkplan(state, m["target"], [(m["target"], 2, "MEDIUM")],
                       m["decision_lap"])
        tcol = list(state.roster_driver_ids).index(m["target"])
        _, ref_p, _ = E.run_arm(state, params, _cfg(), Assumptions(), None)
        _, alt_p, _ = E.run_arm(state, params, _cfg(), Assumptions(), plan)
        mask = np.asarray(ref_p["valid"]) & np.asarray(alt_p["valid"])
        d = (np.asarray(ref_p["finish_position"])[mask][:, tcol].astype(float)
             - np.asarray(alt_p["finish_position"])[mask][:, tcol].astype(float))
        lo, hi = E.paired_percentile_ci(d, seed=1)
        paired_w = (hi - lo) if lo is not None else None
        _, ref_i, _ = E.run_arm(state, params, _cfg(seed=7), Assumptions(), None)
        _, alt_i, _ = E.run_arm(state, params, _cfg(seed=99), Assumptions(), plan)
        mi = np.asarray(ref_i["valid"]) & np.asarray(alt_i["valid"])
        bi = np.asarray(ref_i["finish_position"])[mi][:, tcol].astype(float)
        ai = np.asarray(alt_i["finish_position"])[mi][:, tcol].astype(float)
        indep_w = 2 * 1.96 * float(
            np.sqrt(bi.var(ddof=1) / bi.size + ai.var(ddof=1) / ai.size))
        crn_rows.append({"anchor": m["race_id"], "paired_ci_width": paired_w,
                         "independent_ci_width": indep_w,
                         "ratio": (paired_w / indep_w
                                   if paired_w and indep_w else None)})
    stability = {
        "crn_diagnostic": crn_rows,
        "gain_recompute": [gain_ok, gain_tot],
        "pit_recompute": [pit_ok, pit_tot],
        "ahead_recompute": [ahead_ok, ahead_tot],
        "pair_violations": pair_viol,
        "count_stability": count_rows,
        "seed_stability": seed_rows,
        "reproducibility": [repro_ok, 4],
        "parity": [parity_ok, 16],
    }
    (D / "stability_analysis.json").write_text(
        json.dumps(stability, sort_keys=True, indent=2) + "\n")

    # --- pathology + gate ---
    path = {f"P{i}": 0 for i in range(1, 18)}
    notes = []
    if repro_ok != 4:
        path["P1"] += 1
        notes.append("reproducibility shortfall")
    if pair_viol:
        path["P3"] += pair_viol
    if gain_ok != gain_tot:
        path["P4"] += (gain_tot - gain_ok)
    if ahead_ok != ahead_tot:
        path["P5"] += (ahead_tot - ahead_ok)
    if pit_ok != pit_tot:
        path["P6"] += (pit_tot - pit_ok)
    if parity_ok != 16:
        path["P17"] += (16 - parity_ok)
    # finite/probability/distribution/orientation/reference scans
    for rec in RUN:
        for name, comp in rec["comparisons"].items():
            if isinstance(comp, dict) and comp.get("supported") is False:
                continue
            for k, d in comp["deltas"].items():
                v = d["point_estimate"]
                # None = legitimately unavailable (e.g. rival-less
                # comparison); only true NaN/inf floats are P11.
                if v is not None and not np.isfinite(v):
                    path["P11"] += 1
            for agg in (comp["base_aggregate"], comp["alternative_aggregate"]):
                for f in ("win_frequency", "podium_frequency",
                          "top5_frequency", "top10_frequency"):
                    if not (0.0 <= agg[f] <= 1.0):
                        path["P12"] += 1
                if abs(sum(x["frequency"] for x in
                           agg["finish_position_distribution"]) - 1.0) > 1e-6:
                    path["P13"] += 1
            if comp["provenance"].get("reference_kind") != \
                    "SIMULATED_NO_INTERVENTION_REFERENCE" and \
                    comp["comparison_form"] == "REFERENCE_VS_PLAN":
                path["P15"] += 1
    blocking = path["P1"] + path["P3"] + path["P4"] + path["P11"] + \
        path["P12"] + path["P13"] + path["P17"]
    support_total = sum(v["supported"] for v in
                        [f for f in
                         json.loads((D / "historical_evaluation.json").read_text())["families"].values()])
    if blocking == 0 and repro_ok == 4 and parity_ok == 16 and support_total > 0:
        gate = "REFINEMENT_NOT_WARRANTED"
    elif blocking > 0:
        gate = "BLOCKING_DEFECT"
    else:
        gate = "REFINEMENT_WARRANTED"
    (D / "pathology_report.json").write_text(
        json.dumps({"counts": path, "notes": notes}, sort_keys=True,
                   indent=2) + "\n")
    (D / "refinement_gate.json").write_text(
        json.dumps({"decision": gate, "blocking_invariants": blocking,
                    "support_comparisons": support_total},
                   sort_keys=True, indent=2) + "\n")

    card = {
        "schema": "v3.7d-evaluation-card-v1",
        "a_identity": "1735954212ec31286fede041639875610003a09cf817177e22cc908e3fcb0a12",
        "b_identity": "1865537503136ed3d8603e53741902c320df9387222655b38eef51640294e970",
        "c_engine_identity": "v3.7c-counterfactual-engine-v1",
        "d_protocol_identity": PROTO["protocol_hash"],
        "seam_sha256": hashlib.sha256(
            (ROOT / "raceintel/simulation/monte_carlo.py").read_bytes()
        ).hexdigest(),
        "anchors": len(RUN),
        "gate": gate,
        "matrix_wall_s": 9631,
    }
    blob = json.dumps(card, sort_keys=True, separators=(",", ":")).encode()
    card["card_identity"] = hashlib.sha256(blob).hexdigest()
    (D / "evaluation_card.json").write_text(
        json.dumps(card, sort_keys=True, indent=2) + "\n")
    top = {"protocol_hash": PROTO["protocol_hash"], "gate": gate,
           "anchors": len(RUN), "card_identity": card["card_identity"]}
    (ROOT / "results/v3/v3_7d_historical_evaluation.json").write_text(
        json.dumps(top, sort_keys=True, indent=2) + "\n")
    print(f"gate={gate} wall_s={time.perf_counter() - t0:.0f}")


def _arm_pair(state, params, plan, n, seed):
    """Reference-vs-plan delta of expected finish via run_arm pairing.

    Same (seed, index) streams pair across counts; seeds give independent
    estimates. Returns (delta_expected_finish, complete_pairs).
    """
    cfg = SimulationConfig(simulation_count=n, master_seed=seed,
                           pit_dynamics_enabled=True)
    _, ref_idx, _ = E.run_arm(state, params, cfg, Assumptions(), None)
    _, alt_idx, _ = E.run_arm(state, params, cfg, Assumptions(), plan)
    mask = np.asarray(ref_idx["valid"]) & np.asarray(alt_idx["valid"])
    tcol = list(state.roster_driver_ids).index(
        plan.target_driver_ids[0])
    bp = np.asarray(ref_idx["finish_position"])[mask][:, tcol].astype(float)
    ap = np.asarray(alt_idx["finish_position"])[mask][:, tcol].astype(float)
    if mask.sum() == 0:
        return (None, 0)
    return (float(bp.mean() - ap.mean()), int(mask.sum()))


def _t(m):
    for s in json.loads((ROOT / "results/v3/v3_6d/sample.json").read_text())["states"]:
        if s["race_id"] == m["race_id"] and s["target_driver_id"] == m["target"]:
            return s["anchor"]["state_time_s"]
    raise KeyError(m)


def _mkplan(state, target, specs, lap):
    items = tuple(C.ScheduledIntervention(
        target_driver_id=t, kind="PIT_IN_N_LAPS", lap_offset_n=n,
        requested_compound=c, decision_lap=lap,
        decision_state_identity=state.identity()) for t, n, c in specs)
    targets = tuple(sorted({t for t, _, _ in specs}))
    return C.CounterfactualPlan(target_driver_ids=targets,
                                interventions=items)


if __name__ == "__main__":
    main()
