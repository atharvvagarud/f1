"""V3.7D matrix execution: deterministic historical evaluation.

Reads: V3.6D sample.json anchors + frozen protocol. Writes raw comparison
records (lifecycle collapsed to counts; full evidence re-derived live for
sentinel subsets). All comparisons go through the validated V3.7 engine.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.v2_service import load_v2_service  # noqa: E402
from api.v2_simulation_service import build_v2_simulation_service  # noqa: E402
from raceintel.counterfactual import contracts as C  # noqa: E402
from raceintel.counterfactual import engine as E  # noqa: E402
from raceintel.race_state.race_state import AnchorObservation  # noqa: E402
from raceintel.simulation.adapter import from_race_state  # noqa: E402
from raceintel.simulation.config import Assumptions, SimulationConfig  # noqa: E402

PROTO = json.loads((ROOT / "results/v3/v3_7d/evaluation_protocol.json").read_text())
SAMPLE = json.loads((ROOT / "results/v3/v3_6d/sample.json").read_text())
SEED = 20240101
COUNT = 5000


def _cfg(n=COUNT, seed=SEED):
    return SimulationConfig(simulation_count=n, master_seed=seed,
                            pit_dynamics_enabled=True)


def _rival_id(state, target):
    tpos = next(e.position for e in state.drivers if e.driver_id == target)
    best, best_key = None, None
    for e in state.drivers:
        if e.driver_id == target or e.position is None or tpos is None:
            continue
        key = (abs(e.position - tpos), e.driver_id)
        if best_key is None or key < best_key:
            best_key, best = key, e.driver_id
    return best


def _plan(state, target, specs, rival=None):
    lap = next(e.lap_number for e in state.drivers if e.driver_id == target)
    items = []
    for t, n, c in specs:
        tl = lap if t == target else next(
            e.lap_number for e in state.drivers if e.driver_id == t)
        items.append(C.ScheduledIntervention(
            target_driver_id=t, kind="PIT_IN_N_LAPS", lap_offset_n=n,
            requested_compound=c, decision_lap=tl,
            decision_state_identity=state.identity()))
    return C.CounterfactualPlan(
        target_driver_ids=tuple(sorted({t for t, _, _ in specs})),
        interventions=tuple(items), rival_driver_id=rival)


def _slim(result):
    """Collapse schedule evidence to lifecycle counts (raw re-derived live)."""
    d = result.to_dict() if hasattr(result, "to_dict") else result
    if isinstance(d, dict) and d.get("supported") is False:
        return d
    counts = {}
    for arm in ("base", "alternative"):
        for sim in d["schedule_outcomes"].get(arm, []):
            for e in sim.get("events", []):
                counts[(arm, e["status"])] = counts.get((arm, e["status"]), 0) + 1
    d = dict(d)
    d["schedule_outcomes"] = {f"{a}/{s}": c for (a, s), c in counts.items()}
    return d


def main():
    svc = build_v2_simulation_service(load_v2_service())
    params = svc.parameters
    anchors = [s for s in SAMPLE["states"] if s["eligible"]]
    print(f"anchors={len(anchors)}", flush=True)
    dest = ROOT / "results/v3/v3_7d/run_results.json"
    done = {}
    if dest.exists():
        try:
            for rec in json.loads(dest.read_text()):
                done[rec["meta"]["race_id"], rec["meta"]["target"],
                     rec["meta"]["decision_lap"]] = rec
        except (OSError, ValueError):
            pass
    out = []
    t0 = time.perf_counter()
    for i, a in enumerate(anchors):
        key = (a["race_id"], a["target_driver_id"], a["decision_lap"])
        if key in done:
            out.append(done[key])
            continue
        try:
            rec = _run_anchor(svc, params, a)
        except Exception as exc:  # noqa: BLE001 - record, never crash batch
            rec = {"meta": {"race_id": a["race_id"],
                            "target": a["target_driver_id"],
                            "decision_lap": a["decision_lap"],
                            "state_identity": None,
                            "unsupported": f"{type(exc).__name__}: {exc}"},
                   "comparisons": {}}
        out.append(rec)
        dest.write_text(json.dumps(out) + "\n")
        print(f"done {i + 1}/{len(anchors)} {a['race_id']} "
              f"{a['target_driver_id']} {time.perf_counter() - t0:.0f}s",
              flush=True)
    print(f"wrote {dest} wall_s={time.perf_counter() - t0:.0f}")


def _run_anchor(svc, params, a):
        race_state = svc._reconstructor.reconstruct(  # noqa: SLF001
            AnchorObservation(race_id=a["race_id"],
                              anchor_driver_id=a["target_driver_id"],
                              anchor_lap_number=a["decision_lap"],
                              anchor_state_time_s=a["anchor"]["state_time_s"]))
        from raceintel.simulation.adapter import from_race_state as _frs
        state = _frs(race_state)
        target = a["target_driver_id"]
        remaining = state.scheduled_laps - a["decision_lap"]
        rival = _rival_id(state, target)
        tpos = next(e.position for e in state.drivers if e.driver_id == target)
        tage = next(e.tyre_age for e in state.drivers if e.driver_id == target)
        meta = {"race_id": a["race_id"], "target": target,
                "decision_lap": a["decision_lap"],
                "state_identity": state.identity(),
                "stage": a["stage"], "factual_position": tpos,
                "tyre_age": tage, "remaining": remaining,
                "scheduled": state.scheduled_laps,
                "roster": len(state.roster_driver_ids), "rival": rival}
        rec = {"meta": meta, "comparisons": {}}
        horizons = [n for n in PROTO["horizons"] if n <= remaining - 1]
        if 8 <= remaining - 1:
            horizons.append(8)
        for n in horizons:
            plan = _plan(state, target, [(target, n, "MEDIUM")])
            res = E.compare_reference_vs_plan(
                state=state, parameters=params, config=_cfg(),
                assumptions=Assumptions(), plan=plan,
                rival_driver_id=rival)
            rec["comparisons"][f"N{n}"] = _slim(res)
        plan = _plan(state, target, [(target, 2, "SOFT")])
        rec["comparisons"]["N2_SOFT"] = _slim(E.compare_reference_vs_plan(
            state=state, parameters=params, config=_cfg(),
            assumptions=Assumptions(), plan=plan, rival_driver_id=rival))
        ms = PROTO["multi_stop_template"]
        if ms["second"]["n"] <= remaining - 1:
            plan = _plan(state, target, [
                (target, ms["first"]["n"], ms["first"]["compound"]),
                (target, ms["second"]["n"], ms["second"]["compound"])])
            rec["comparisons"]["MULTISTOP"] = _slim(
                E.compare_reference_vs_plan(
                    state=state, parameters=params, config=_cfg(),
                    assumptions=Assumptions(), plan=plan,
                    rival_driver_id=rival))
        if rival is not None:
            plan = _plan(state, target, [(target, 2, "MEDIUM"),
                                         (rival, 2, "MEDIUM")])
            rec["comparisons"]["MULTIDRIVER"] = _slim(
                E.compare_reference_vs_plan(
                    state=state, parameters=params, config=_cfg(),
                    assumptions=Assumptions(), plan=plan,
                    rival_driver_id=rival))
            base = _plan(state, target, [(target, 2, "MEDIUM")])
            alt = _plan(state, target, [(target, 5, "MEDIUM")])
            if 5 <= remaining - 1:
                rec["comparisons"]["PVP_N2_N5"] = _slim(
                    E.compare_plan_vs_plan(
                        state=state, parameters=params, config=_cfg(),
                        assumptions=Assumptions(), plan_a=base, plan_b=alt,
                        rival_driver_id=rival))
            if "MULTISTOP" in rec["comparisons"]:
                alt2 = _plan(state, target, [
                    (target, ms["first"]["n"], ms["first"]["compound"]),
                    (target, ms["second"]["n"], ms["second"]["compound"])])
                rec["comparisons"]["PVP_SINGLE_MULTI"] = _slim(
                    E.compare_plan_vs_plan(
                        state=state, parameters=params, config=_cfg(),
                        assumptions=Assumptions(), plan_a=base, plan_b=alt2,
                        rival_driver_id=rival))
        return rec


if __name__ == "__main__":
    main()
