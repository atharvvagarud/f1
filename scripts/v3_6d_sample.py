"""V3.6D Phase 1: deterministic historical sampling + eligibility screen.

Enumerates K=2 anchors per served race at canonical fractions {1/3, 2/3},
reconstructs the exact causal RaceState(T), and screens MC2 eligibility via
the frozen ``prepare_initial_state`` (no status resolver: matches the
strategy product path conservatism, documented in protocol).

Output: results/v3/v3_6d/sample.json — candidate states with eligibility
outcome. No strategy simulations are executed here.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.v2_service import load_v2_service
from api.v2_strategy_service import load_production_parameters
from raceintel.race_state import race_state as RS
from raceintel.simulation.engine import ExecutionPolicy
from raceintel.simulation.presence import prepare_initial_state

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_6d" / "sample.json"
FRACTIONS = (1 / 3, 2 / 3)


def main() -> None:
    t0 = time.perf_counter()
    svc = load_v2_service()
    params = load_production_parameters()
    races = [r["race_id"] for r in svc.list_races()]
    candidates = []
    for race_id in races:
        total = svc.list_anchors(race_id, limit=1)["total"]
        if total == 0:
            continue
        indices = sorted({min(total - 1, int((total - 1) * f))
                          for f in FRACTIONS})
        anchors = svc.list_anchors(race_id, limit=total)["anchors"]
        grid = svc.grid_slots(race_id)
        for idx in indices:
            a = anchors[idx]
            anchor = RS.AnchorObservation(
                race_id=race_id, anchor_driver_id=a["driver_id"],
                anchor_lap_number=a["lap_number"],
                anchor_state_time_s=a["state_time_s"])
            try:
                race_state = svc._reconstructor.reconstruct(anchor)
            except Exception as exc:  # fail-closed: record, never guess
                candidates.append({
                    "race_id": race_id, "anchor": a, "target_driver_id":
                    a["driver_id"], "eligible": False,
                    "reason": f"reconstruction_failure:{type(exc).__name__}",
                    "stage": None, "decision_lap": None,
                    "state_identity": None})
                continue
            relief = prepare_initial_state(
                race_state, grid_by_driver=grid, parameters=params,
                execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
            entry = {
                "race_id": race_id, "anchor": a,
                "target_driver_id": a["driver_id"],
                "eligible": bool(relief.eligible),
                "reason": relief.reason,
                "stage": None, "decision_lap": None,
                "state_identity": None}
            if relief.eligible and relief.state is not None:
                st = relief.state
                drv = st.driver_by_id.get(a["driver_id"])
                frac = (st.leader_laps_done / st.scheduled_laps
                        if st.scheduled_laps else 0.0)
                entry["stage"] = ("EARLY" if frac < 1 / 3 else
                                  "MID" if frac < 2 / 3 else "LATE")
                entry["decision_lap"] = drv.lap_number if drv else None
                entry["state_identity"] = st.identity()
                entry["leader_laps_done"] = st.leader_laps_done
                entry["scheduled_laps"] = st.scheduled_laps
                entry["roster_size"] = st.roster_size
            candidates.append(entry)
    eligible = sum(1 for c in candidates if c["eligible"])
    payload = {
        "fractions": list(FRACTIONS),
        "races_screened": len(races),
        "candidates": len(candidates),
        "eligible": eligible,
        "screen_runtime_s": round(time.perf_counter() - t0, 1),
        "states": candidates,
    }
    OUT.write_text(json.dumps(payload, indent=1))
    print(f"candidates={len(candidates)} eligible={eligible} "
          f"runtime={payload['screen_runtime_s']}s -> {OUT}")


if __name__ == "__main__":
    main()
