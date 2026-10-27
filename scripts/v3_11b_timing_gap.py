#!/usr/bin/env python3
"""V3.11B step 3 -- timing-gap analysis + validation (offline, read-only).

For each of the 51 TIMING_GAP registry states:
  - gap anatomy from D9 (last row <=T, next row >T as OFFLINE label only)
  - persisted-vs-next comparison (lap/position exact, race_time error)
  - race-level evolution during the gap (leader laps, regime tokens,
    field pit stops) from <=T evidence where the window is (obs, T],
    and as offline labels where the window extends past T
  - per-protocol verdicts T1/T2/T3/T4 (protocol sha pinned; criteria
    pre-declared in reconstruction_protocol.json)

No production import. No eligibility mutation. Deterministic.

Usage:
    .venv/bin/python scripts/v3_11b_timing_gap.py
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_11b"


def _norm(val):
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if type(val).__module__ == "numpy":
        try:
            return val.item()
        except (ValueError, AttributeError):
            return None
    return val


def main() -> int:
    t0 = time.perf_counter()
    protocol = json.loads(
        (OUT / "reconstruction_protocol.json").read_text(encoding="utf-8"))
    proto_hash = protocol["protocol_sha256"]
    registry = json.loads(
        (OUT / "r2_candidate_registry.json").read_text(encoding="utf-8"))
    tg = [c for c in registry["candidates"]
          if c["r2_subtype"] == "TIMING_GAP"]
    assert len(tg) == 51, len(tg)

    d9_by_race: dict[str, pd.DataFrame] = {}
    for season in (2018, 2019, 2020, 2021, 2022, 2023, 2024):
        df = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9"
            / f"season={season}"
            / f"driver_lap_state_d9__d9-{season}.parquet")
        for race_id, rdf in df.groupby("race_id"):
            d9_by_race[str(race_id)] = rdf

    per_state = []
    for c in tg:
        T = float(c["T_s"])
        rdf = d9_by_race[c["race_id"]]
        race_times = rdf["state_time_s"].to_numpy(dtype=float)
        offender_rows = []
        for o in c["offenders"]:
            sub = rdf[rdf["driver_id"] == o["driver_id"]]
            st = sub["state_time_s"].to_numpy(dtype=float)
            order = np.argsort(st, kind="stable")
            s = st[order]
            idx = int(np.searchsorted(s, T, side="right")) - 1
            assert idx >= 0, "TIMING_GAP offender must have a prior row"
            last = sub.iloc[order[idx]]
            nxt = sub.iloc[order[idx + 1]] if idx + 1 < len(order) else None
            last_obs = float(last["state_time_s"])
            # Persisted values = last <=T row (the H-T1 runtime procedure).
            persisted = {
                "lap_number": _norm(last.get("lap_number")),
                "race_time_s": _norm(last.get("state_time_s")),
                "position": _norm(last.get("position")),
                "compound": _norm(last.get("compound")),
                "pit_stops": _norm(last.get("pit_stops_completed_so_far")),
            }
            if nxt is not None:  # OFFLINE label only.
                nxt_t = float(nxt["state_time_s"])
                label = {
                    "lap_number": _norm(nxt.get("lap_number")),
                    "race_time_s": nxt_t,
                    "position": _norm(nxt.get("position")),
                    "compound": _norm(nxt.get("compound")),
                    "pit_stops": _norm(nxt.get("pit_stops_completed_so_far")),
                    "dt_after_T_s": nxt_t - T,
                }
            else:
                label = None
            # Race-level evolution during (last_obs, T] -- causal evidence.
            win = rdf[(rdf["state_time_s"] > last_obs)
                      & (rdf["state_time_s"] <= T)]
            lead = sorted({_norm(v) for v in
                           win["race_leader_laps_at_state"].tolist()
                           if _norm(v) is not None})
            toks = sorted({str(_norm(v)) for v in
                           win["track_state"].tolist()
                           if _norm(v) is not None})
            gap_leader_laps = (lead[-1] - lead[0]) if len(lead) >= 2 else 0
            t1 = (label is not None
                  and persisted["lap_number"] == label["lap_number"])
            t2 = (label is not None
                  and persisted["position"] is not None
                  and persisted["position"] == label["position"])
            t3_time_err = (abs(persisted["race_time_s"] - label["race_time_s"])
                           if label is not None else None)
            pit_during = (label is not None and persisted["pit_stops"]
                          is not None and label["pit_stops"] is not None
                          and label["pit_stops"] != persisted["pit_stops"])
            compound_change = (label is not None
                               and persisted["compound"] !=
                               label["compound"])
            regime_during = [t for t in toks if t != "all_clear"]
            exclusions = {
                "pit_during_gap_label": bool(pit_during),
                "compound_change_label": bool(compound_change),
                "regime_tokens_during_gap": regime_during,
                "regime_during_gap": bool(regime_during),
                "leader_laps_advanced": int(gap_leader_laps),
            }
            offender_rows.append({
                "driver_id": o["driver_id"],
                "frozen_age_s": o["frozen_age_s"],
                "gap_s": T - last_obs,
                "persisted": persisted,
                "next_native_label": label,
                "T1_lap_exact": bool(t1),
                "T2_position_exact": bool(t2),
                "T3_race_time_abs_err_s": t3_time_err,
                "exclusions": exclusions,
                "survives_exclusions": not (
                    pit_during or compound_change or regime_during),
            })
        per_state.append({
            "state_id": c["state_id"],
            "race_id": c["race_id"],
            "frame_index": c["frame_index"],
            "leader_lap": c["leader_lap"],
            "T_s": T,
            "freshness_threshold_s": c["freshness_threshold_s"],
            "offenders": offender_rows,
            "state_passes_T1_T2_T3": all(
                r["T1_lap_exact"] and r["T2_position_exact"]
                and r["survives_exclusions"] for r in offender_rows),
        })

    n_off = sum(len(s["offenders"]) for s in per_state)
    lap_pass = sum(1 for s in per_state for r in s["offenders"]
                   if r["T1_lap_exact"])
    pos_pass = sum(1 for s in per_state for r in s["offenders"]
                   if r["T2_position_exact"])
    surv = sum(1 for s in per_state for r in s["offenders"]
               if r["survives_exclusions"])
    errs = sorted(r["T3_race_time_abs_err_s"] for s in per_state
                  for r in s["offenders"]
                  if r["T3_race_time_abs_err_s"] is not None)
    gap_vals = sorted(r["gap_s"] for s in per_state for r in s["offenders"])
    adv = sorted(r["exclusions"]["leader_laps_advanced"] for s in per_state
                 for r in s["offenders"])
    pit_n = sum(1 for s in per_state for r in s["offenders"]
                if r["exclusions"]["pit_during_gap_label"])
    cmp_n = sum(1 for s in per_state for r in s["offenders"]
                if r["exclusions"]["compound_change_label"])
    reg_n = sum(1 for s in per_state for r in s["offenders"]
                if r["exclusions"]["regime_during_gap"])

    def _q(xs):
        s = sorted(xs)
        n = len(s)
        if n == 0:
            return {"count": 0}
        med = s[n // 2]
        return {"count": n, "min": round(s[0], 1), "median": round(med, 1),
                "p90": round(s[int(0.9 * (n - 1))], 1),
                "max": round(s[-1], 1)}

    analysis = {
        "schema_version": "v3.11b-timing-gap-analysis-v1",
        "protocol_sha256": proto_hash,
        "n_states": len(per_state),
        "n_offenders": n_off,
        "gap_s": _q(gap_vals),
        "leader_laps_advanced_during_gap": _q(adv),
        "persisted_vs_next": {
            "lap_exact": lap_pass, "lap_total": n_off,
            "position_exact": pos_pass, "position_total": n_off,
            "race_time_abs_err_s": _q(errs),
        },
        "exclusion_hits": {
            "pit_during_gap_offenders": pit_n,
            "compound_change_offenders": cmp_n,
            "regime_during_gap_offenders": reg_n,
            "surviving_offenders": surv,
        },
        "per_state": per_state,
    }
    text = json.dumps(analysis, indent=1, sort_keys=True)
    with open(OUT / "timing_gap_analysis.json", "w",
              encoding="utf-8") as fh:
        fh.write(text + "\n")

    states_pass = sum(1 for s in per_state if s["state_passes_T1_T2_T3"])
    validation = {
        "schema_version": "v3.11b-timing-gap-validation-v1",
        "protocol_sha256": proto_hash,
        "T1_lap_unanimity": f"{lap_pass}/{n_off}",
        "T2_position_unanimity": f"{pos_pass}/{n_off}",
        "T3_exclusion_survival_states": f"{states_pass}/{len(per_state)}",
        "T4_runtime_causality": (
            "runtime procedure (persist last <=T row) reads only "
            "state_time_s <= T via searchsorted side=right; next-native "
            "rows used as offline labels only (this script); poison-pinned "
            "in tests/test_v3_11b_reconstruction.py"),
        "criteria_met": {
            "T1": lap_pass == n_off, "T2": pos_pass == n_off,
            "T3": states_pass == len(per_state), "T4": True,
        },
        "verdict": ("ACCEPTED" if (lap_pass == n_off and pos_pass == n_off
                                   and states_pass == len(per_state))
                    else "REJECTED"),
    }
    with open(OUT / "timing_gap_validation.json", "w",
              encoding="utf-8") as fh:
        fh.write(json.dumps(validation, indent=1, sort_keys=True) + "\n")
    print(json.dumps({
        "status": "OK", "states": len(per_state),
        "lap_exact": f"{lap_pass}/{n_off}",
        "position_exact": f"{pos_pass}/{n_off}",
        "surviving_states": f"{states_pass}/{len(per_state)}",
        "verdict": validation["verdict"],
        "wall_s": round(time.perf_counter() - t0, 1),
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
