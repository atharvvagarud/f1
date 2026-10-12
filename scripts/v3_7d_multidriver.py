"""V3.7D supplement: MULTIDRIVER comparisons without rival kwarg.

B contract (frozen) requires rival != targets; the main runner passed the
co-target as rival, yielding contract-faithful RIVAL_NOT_PRESENT. This
supplement evaluates multi-driver execution/order/pairs with rival=None
(P(ahead) remains covered by single-target runs). Same template, seeds,
counts as protocol.
"""

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import v3_7d_run as R
from raceintel.counterfactual import engine as E
from raceintel.simulation.adapter import from_race_state
from raceintel.simulation.config import Assumptions

MOD = sys.modules["v3_7d_run"]


def main():
    svc = R.build_v2_simulation_service(R.load_v2_service())
    params = svc.parameters
    dest = ROOT / "results" / "v3" / "v3_7d" / "run_results.json"
    out = json.loads(dest.read_text())
    t0 = time.perf_counter()
    n = 0
    for rec in out:
        m = rec["meta"]
        if not m.get("state_identity"):
            continue
        if rec["comparisons"].get("MULTIDRIVER", {}).get("supported") is True:
            continue
        from raceintel.race_state.race_state import AnchorObservation
        rs = svc._reconstructor.reconstruct(  # noqa: SLF001
            AnchorObservation(race_id=m["race_id"],
                              anchor_driver_id=m["target"],
                              anchor_lap_number=m["decision_lap"],
                              anchor_state_time_s=_t(m)))
        state = from_race_state(rs)
        target, rival = m["target"], m["rival"]
        plan = R._plan(state, target, [(target, 2, "MEDIUM"),
                                       (rival, 2, "MEDIUM")])
        res = E.compare_reference_vs_plan(
            state=state, parameters=params, config=R._cfg(),
            assumptions=Assumptions(), plan=plan, rival_driver_id=None)
        rec["comparisons"]["MULTIDRIVER"] = R._slim(res)
        n += 1
        dest.write_text(json.dumps(out) + "\n")
        print(f"multidriver {n} {m['race_id']} {target} "
              f"{time.perf_counter() - t0:.0f}s", flush=True)
    print(f"supplemented {n}")


def _t(m):
    for s in json.loads(
            (ROOT / "results/v3/v3_6d/sample.json").read_text())["states"]:
        if s["race_id"] == m["race_id"] and s["target_driver_id"] == m["target"]:
            return s["anchor"]["state_time_s"]
    raise KeyError(m)


if __name__ == "__main__":
    main()
