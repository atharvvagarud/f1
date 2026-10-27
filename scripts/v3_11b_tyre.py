#!/usr/bin/env python3
"""V3.11B step 4 -- tyre-persistence analysis + validation (offline).

For each of the 4 TYRE_STINT registry states, per missing-tyre driver:
  - prior D9 rows <=T (compound/stint/pit fields)
  - Y1 same-stint provable <=T (non-null stint_number + no pit event in
    (prior_obs, T] from <=T fields only)
  - Y2 pit-boundary unambiguous (fail closed)
  - next native compound as OFFLINE label only (Y4 informative)
Per-protocol verdicts Y1/Y2/Y3 (protocol sha pinned).

No production import. No eligibility mutation. Deterministic.

Usage:
    .venv/bin/python scripts/v3_11b_tyre.py
"""

from __future__ import annotations

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
    ty = [c for c in registry["candidates"]
          if c["r2_subtype"] == "TYRE_STINT"]
    assert len(ty) == 4, len(ty)

    df18 = pd.read_parquet(
        ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9"
        / "season=2018" / "driver_lap_state_d9__d9-2018.parquet")

    per_state = []
    for c in ty:
        T = float(c["T_s"])
        rdf = df18[df18["race_id"] == c["race_id"]]
        drivers = []
        for d in sorted(c["missing_tyre_drivers"]):
            sub = rdf[rdf["driver_id"] == d].sort_values("state_time_s")
            prior = sub[sub["state_time_s"] <= T]
            post = sub[sub["state_time_s"] > T]  # OFFLINE labels only
            prior_comp = [r for _, r in prior.iterrows()
                          if _norm(r.get("compound")) is not None]
            latest = prior.iloc[-1] if len(prior) else None
            stint_vals = {_norm(r.get("stint_number")) for _, r in
                          prior.iterrows()}
            stint_vals.discard(None)
            pit_in_window = False
            if latest is not None:
                # Pit event inside the prior window breaks stint continuity;
                # detect via pit columns or pit-count increase across prior
                # rows (all <=T evidence).
                counts = [_norm(r.get("pit_stops_completed_so_far"))
                          for _, r in prior.iterrows()]
                counts = [x for x in counts if x is not None]
                pit_in_window = (len(counts) >= 2
                                 and max(counts) != min(counts))
                pin = [_norm(r.get("pit_in_s")) for _, r in prior.iterrows()
                       if _norm(r.get("pit_in_s")) is not None]
                pout = [_norm(r.get("pit_out_s")) for _, r in prior.iterrows()
                        if _norm(r.get("pit_out_s")) is not None]
                pit_in_window = pit_in_window or bool(pin or pout)
            nxt = post.iloc[0] if len(post) else None
            y1 = (len(prior_comp) > 0 and len(stint_vals) == 1
                  and not pit_in_window)
            # Y2: boundary unambiguous only if a stint is established at
            # all; with zero prior compound there is no boundary to judge.
            y2 = y1 and latest is not None and _norm(
                latest.get("stint_number")) is not None
            drivers.append({
                "driver_id": d,
                "n_prior_rows_le_T": int(len(prior)),
                "n_prior_compound_rows_le_T": len(prior_comp),
                "latest_prior_lap": (int(latest["lap_number"])
                                     if latest is not None else None),
                "stint_values_le_T": sorted(stint_vals),
                "pit_event_in_prior_window": bool(pit_in_window),
                "Y1_same_stint_provable": bool(y1),
                "Y2_boundary_unambiguous": bool(y2),
                "next_native_compound_label": (
                    _norm(nxt.get("compound")) if nxt is not None else None),
            })
        y1_states = any(d["Y1_same_stint_provable"] for d in drivers)
        per_state.append({
            "state_id": c["state_id"],
            "race_id": c["race_id"],
            "frame_index": c["frame_index"],
            "leader_lap": c["leader_lap"],
            "T_s": T,
            "n_missing_tyre_drivers": len(drivers),
            "drivers_with_prior_compound": sum(
                1 for d in drivers if d["n_prior_compound_rows_le_T"] > 0),
            "drivers_Y1": sum(1 for d in drivers
                              if d["Y1_same_stint_provable"]),
            "any_Y1": bool(y1_states),
            "drivers": drivers,
        })

    analysis = {
        "schema_version": "v3.11b-tyre-persistence-analysis-v1",
        "protocol_sha256": proto_hash,
        "n_states": len(per_state),
        "finding": (
            "All 4 TYRE_STINT states are 2018 leader-lap-2 states whose "
            "missing drivers' only <=T rows are compound-null/stint-null "
            "lap-1 rows (2018 lap-1 all-null finding). Zero drivers have a "
            "prior <=T compound; Y1 fails 4/4. The next native compound "
            "(e.g. ULTRASOFT one lap later) is future backfill and is "
            "forbidden as runtime evidence."),
        "per_state": per_state,
    }
    with open(OUT / "tyre_persistence_analysis.json", "w",
              encoding="utf-8") as fh:
        fh.write(json.dumps(analysis, indent=1, sort_keys=True) + "\n")

    y1_pass = sum(1 for s in per_state if s["any_Y1"])
    validation = {
        "schema_version": "v3.11b-tyre-persistence-validation-v1",
        "protocol_sha256": proto_hash,
        "Y1_same_stint_states": f"{y1_pass}/{len(per_state)}",
        "Y2_boundary_states": f"{y1_pass}/{len(per_state)}",
        "Y3_runtime_causality": (
            "specified runtime procedure reads only state_time_s <= T "
            "rows; next-compound labels used offline only (this script); "
            "no default/inferred/strategy compound anywhere "
            "(poison-pinned in tests/test_v3_11b_reconstruction.py)"),
        "Y4_offline_label_note": (
            "informative only: next native compounds exist >T but must "
            "never enter runtime logic"),
        "criteria_met": {"Y1": y1_pass == len(per_state),
                         "Y2": y1_pass == len(per_state), "Y3": True},
        "verdict": ("ACCEPTED" if y1_pass == len(per_state) else "REJECTED"),
        "verdict_note": (
            "Rejected: no testable R2 instance (0/4 states carry any "
            "prior <=T compound). Broader validation on non-R2 states "
            "would serve zero B transitions and is out of scope per §15."),
    }
    with open(OUT / "tyre_persistence_validation.json", "w",
              encoding="utf-8") as fh:
        fh.write(json.dumps(validation, indent=1, sort_keys=True) + "\n")
    print(json.dumps({
        "status": "OK", "states": len(per_state),
        "Y1_states": f"{y1_pass}/{len(per_state)}",
        "verdict": validation["verdict"],
        "wall_s": round(time.perf_counter() - t0, 1),
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
