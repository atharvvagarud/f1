#!/usr/bin/env python3
"""V3.11B step 1 -- R2 candidate registry (diagnostic, read-only).

Reads the frozen V3.11A ledger and emits the exact 114 R2 candidate states
with per-state diagnostic context (last observation <=T, next observation
>T as OFFLINE label only, subtype, provenance, known risk).

No production import. No eligibility mutation. Deterministic.

Usage:
    .venv/bin/python scripts/v3_11b_r2_registry.py
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_11b"
A = ROOT / "results" / "v3" / "v3_11a"


def _load(path: Path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def main() -> int:
    t0 = time.perf_counter()
    ledger = _load(A / "unsupported_state_ledger.json")["states"]
    r2 = [r for r in ledger if r.get("recovery_class")
          == "R2_DOMAIN_RULE_REQUIRED"]
    r2 = sorted(r2, key=lambda r: (r["race_id"], r["frame_index"]))
    assert len(r2) == 114, f"R2 registry mismatch: {len(r2)} != 114"
    assert len({r["state_id"] for r in r2}) == 114, "duplicate R2 identities"

    subtype_of = {
        "STALE_TIMING_GAP_RECONSTRUCTION": "TIMING_GAP",
        "TRACK_NULL_INTERVAL_RECONSTRUCTION": "NULL_TRACK",
        "MISSING_TYRE_STINT_PERSISTENCE": "TYRE_STINT",
    }
    records = []
    for r in r2:
        offenders = []
        for o in r.get("offenders", []):
            probe = next(
                (p for p in r.get("offender_probes", [])
                 if p["driver_id"] == o["driver_id"]), {})
            offenders.append({
                "driver_id": o["driver_id"],
                "frozen_age_s": o["age_s"],
                "last_observation_le_T_s": probe.get("obs_time"),
                "next_observation_gt_T_exists": probe.get("later_exists"),
            })
        records.append({
            "state_id": r["state_id"],
            "race_id": r["race_id"],
            "season": r["season"],
            "frame_index": r["frame_index"],
            "leader_lap": r.get("leader_lap"),
            "stage": r.get("stage"),
            "T_s": r["T_s"],
            "original_frozen_reason": r["original_reason"],
            "blocking_conditions": r["blocking_conditions"],
            "r2_subtype": subtype_of[r["recovery_sublabel"]],
            "r2_sublabel": r["recovery_sublabel"],
            "required_fields": (
                ["driver_row_timing"] if subtype_of[r["recovery_sublabel"]]
                == "TIMING_GAP" else
                ["track_status"] if subtype_of[r["recovery_sublabel"]]
                == "NULL_TRACK" else ["tyre_compound", "track_status"]),
            "freshness_threshold_s": r.get("freshness_threshold_s"),
            "offenders": offenders,
            "track_state": r.get("track_state"),
            "rainfall": r.get("rainfall"),
            "missing_tyre_drivers": r.get("missing_tyre_drivers", []),
            "observation_provenance": "D9 driver_lap_state <= T (V3.11A probe)",
            "next_observation_note": ("OFFLINE label only; must never enter "
                                      "a runtime rule"),
            "why_plausible_per_A": (
                "all stale offenders causally reappear later"
                if subtype_of[r["recovery_sublabel"]] == "TIMING_GAP" else
                "pre-first-message null token; race demonstrably underway"
                if subtype_of[r["recovery_sublabel"]] == "NULL_TRACK" else
                "prior <=T compound exists within known stint"),
            "known_scientific_risk": (
                "inherits V3.2K failed gates; reappearance known only via "
                "future; dynamic state frozen across gap"
                if subtype_of[r["recovery_sublabel"]] == "TIMING_GAP" else
                "no prior known status (0/64); null semantics unvalidated; "
                "source interpretation deferred"
                if subtype_of[r["recovery_sublabel"]] == "NULL_TRACK" else
                "stint-boundary ambiguity; track co-block"),
        })

    by_subtype = Counter(r["r2_subtype"] for r in records)
    registry = {
        "schema_version": "v3.11b-r2-candidate-registry-v1",
        "provenance": "results/v3/v3_11a/unsupported_state_ledger.json "
                      "(read-only; V3.11A artifacts untouched)",
        "n": len(records),
        "by_subtype": dict(sorted(by_subtype.items())),
        "expected": {"TIMING_GAP": 51, "NULL_TRACK": 59, "TYRE_STINT": 4},
        "exact": (len(records) == 114 and by_subtype["TIMING_GAP"] == 51
                  and by_subtype["NULL_TRACK"] == 59
                  and by_subtype["TYRE_STINT"] == 4),
        "candidates": records,
    }
    text = json.dumps(registry, indent=1, sort_keys=True)
    registry["registry_sha256"] = hashlib.sha256(
        text.encode("utf-8")).hexdigest()
    OUT.mkdir(parents=True, exist_ok=True)
    with open(OUT / "r2_candidate_registry.json", "w",
              encoding="utf-8") as fh:
        fh.write(json.dumps(registry, indent=1, sort_keys=True) + "\n")

    # Reconciliation: decomposition + arithmetic ceiling (§28).
    machine = {
        "schema_version": "v3.11b-candidate-reconciliation-v1",
        "registry": "results/v3/v3_11b/r2_candidate_registry.json",
        "registry_sha256": registry["registry_sha256"],
        "r2_unique_states": 114,
        "decomposition": dict(sorted(by_subtype.items())),
        "decomposition_exact_per_A": registry["exact"],
        "ceiling": {"eligible": 3678 + 114, "total": 9644,
                    "fraction": round((3678 + 114) / 9644, 4)},
        "prose_discrepancy": {
            "v3_11a_prose_claim": 0.3991,
            "machine_authoritative": round((3678 + 114) / 9644, 4),
            "explanation": ("39.91% corresponds to 3849 = 3678+171, an "
                            "intermediate V3.11A run predating the "
                            "mass-clock-reset refinement (r2_alone was 171 "
                            "before the 196 MASS_CLOCK_RESET states were "
                            "moved R2->R4). Final machine artifacts "
                            "(recovery_classification.json, "
                            "recovery_ceilings.json) say 114 -> 3792/9644 "
                            "= 39.32%. Machine-readable unique-state "
                            "arithmetic governs."),
            "v3_11a_artifacts_rewritten": False,
        },
    }
    with open(OUT / "candidate_reconciliation.json", "w",
              encoding="utf-8") as fh:
        fh.write(json.dumps(machine, indent=1, sort_keys=True) + "\n")

    print(json.dumps({
        "status": "OK" if registry["exact"] else "MISMATCH",
        "n": len(records), "by_subtype": dict(sorted(by_subtype.items())),
        "ceiling_fraction": machine["ceiling"]["fraction"],
        "wall_s": round(time.perf_counter() - t0, 1),
    }, sort_keys=True), flush=True)
    return 0 if registry["exact"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
