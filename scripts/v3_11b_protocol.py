#!/usr/bin/env python3
"""V3.11B step 2 -- reconstruction protocol (PRE-DECLARED, before results).

Emits reconstruction_protocol.json with one protocol per candidate rule:
hypothesis, exact candidate subset (from the R2 registry), runtime vs
prohibited inputs, validity/invalidation, evaluation labels, metrics, and
acceptance/rejection criteria derived from frozen tolerances -- frozen
BEFORE any validation metric is computed (V3.11B §22).

No production import. Deterministic. Read-only (reads only the registry).

Usage:
    .venv/bin/python scripts/v3_11b_protocol.py
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_11b"


def main() -> int:
    t0 = time.perf_counter()
    registry = json.loads(
        (OUT / "r2_candidate_registry.json").read_text(encoding="utf-8"))
    reg_hash = registry["registry_sha256"]
    by_subtype: dict[str, list[str]] = {}
    for c in registry["candidates"]:
        by_subtype.setdefault(c["r2_subtype"], []).append(c["state_id"])
    for v in by_subtype.values():
        v.sort()

    protocols = [
        {
            "protocol_id": "V3.11B-PROTOCOL-T1",
            "rule_id": "TIMING_GAP_RECONSTRUCTION",
            "hypothesis": (
                "H-T1: a stale driver's last <=T D9 row (lap_number, "
                "race_time_s, position, gaps) remains a valid MC2 start "
                "state when the gap is a pure observation delay with the "
                "field otherwise unevolved."),
            "candidate_subset": by_subtype.get("TIMING_GAP", []),
            "runtime_inputs": [
                "stale driver's last <=T D9 row only",
                "current T (anchor_state_time_s)",
                "regime/track context at T from <=T evidence (for "
                "exclusion checks)",
            ],
            "prohibited_inputs": [
                "next observation", "final lap data", "eventual "
                "classification", "later track status", "future timing row",
                "reappearance knowledge (TIMING_GAP shape is an offline "
                "label, never a runtime input)",
            ],
            "validity_interval": (
                "none pre-granted; validity must be earned per state by "
                "passing every exclusion condition below"),
            "invalidation_conditions": [
                "pit entry/exit during (obs_time, T]",
                "retirement signal during (obs_time, T]",
                "SC/VSC/red-flag/restart during (obs_time, T]",
                "lap-boundary incoherence (persisted lap vs leader "
                "progress)",
                "driver disappearance with unknown cause",
                "track-status ambiguity during (obs_time, T]",
                "compound change during (obs_time, T]",
                "terminal state",
            ],
            "evaluation_labels": (
                "next native D9 row per offender (lap_number, race_time_s, "
                "position) -- OFFLINE ONLY, never runtime inputs"),
            "metrics": [
                "persisted-vs-next lap_number exact agreement (rate)",
                "persisted-vs-next position exact agreement (rate)",
                "persisted-vs-next race_time_s absolute error "
                "(median/p90/max)",
                "states surviving all exclusion conditions (count)",
                "leader laps advanced during gap (median/max)",
            ],
            "acceptance_criteria": {
                "T1_lap": "51/51 persisted lap_number == next native "
                          "lap_number (V3.2K lap gate 0.99 lifted to "
                          "unanimity: no post-hoc subsetting)",
                "T2_position": "51/51 persisted position == next native "
                               "position (V3.2K position gate 0.99 lifted "
                               "to unanimity)",
                "T3_exclusions": "51/51 states survive every exclusion "
                                 "condition above",
                "T4_poison": "runtime procedure provably reads only "
                             "<=T rows (poison-pinned)",
            },
            "rejection_criteria": [
                "any state fails T1, T2, or T3",
                "T4 poison failure",
                "rule requires reappearance knowledge at runtime",
            ],
            "accepted_coverage_effect": [0, 51],
            "frozen_tolerances_basis": (
                "V3.2K gates (position 0.99, lap 0.99, pit 0.95, poison "
                "100%); MC2 anchors trajectories on (lap_number, "
                "race_time_s); staleness is real-world per V3.2K "
                "RAW_SOURCE_STALE 2866"),
        },
        {
            "protocol_id": "V3.11B-PROTOCOL-Y1",
            "rule_id": "TYRE_WITHIN_STINT_PERSISTENCE",
            "hypothesis": (
                "H-Y1: a prior observed compound may persist within a "
                "causally established same stint using information <= T "
                "only."),
            "candidate_subset": by_subtype.get("TYRE_STINT", []),
            "runtime_inputs": [
                "prior <=T D9 row (compound, stint_number, stint_lap, "
                "pit_last_in_s, pit_last_out_s, state_time_s)",
                "current T (anchor_state_time_s)",
            ],
            "prohibited_inputs": [
                "future stint table", "eventual pit stop",
                "final strategy", "next compound", "later lap row",
                "default/inferred/strategy-based compound",
            ],
            "validity_interval": (
                "[prior_obs_time, T] only if no pit event falls in "
                "(prior_obs_time, T]; single-state evaluation, no forward "
                "projection"),
            "invalidation_conditions": [
                "a pit event in (prior_obs_time, T] from any <=T source",
                "stint_number null or discontinuous in <=T evidence",
                "next-compound leak at runtime (poison failure)",
                "any accepted-state transition lacking stint proof",
            ],
            "evaluation_labels": (
                "next native D9 compound per missing-tyre driver "
                "-- OFFLINE ONLY"),
            "metrics": [
                "same-stint provable <=T (boolean per state)",
                "pit-boundary unambiguous (boolean per state)",
                "runtime poison invariance (boolean)",
                "offline prior-vs-next compound agreement (rate, "
                "informative only)",
            ],
            "acceptance_criteria": {
                "Y1_stint": "4/4 states prove same-stint <=T (non-null "
                            "stint_number, no pit event in "
                            "(prior_obs_time, T])",
                "Y2_boundary": "4/4 states have unambiguous pit "
                               "boundaries (fail closed otherwise)",
                "Y3_poison": "runtime procedure reads only <=T rows "
                             "(poison-pinned)",
            },
            "rejection_criteria": [
                "any state fails Y1 or Y2",
                "Y3 poison failure",
                "old compound carried across an ambiguous pit boundary",
            ],
            "accepted_coverage_effect": [0, 4],
            "note_track_coblock": (
                "All 4 TYRE_STINT states co-carry null-TRACK; tyre "
                "acceptance alone yields 0 eligible transitions in B "
                "unless the track rule is separately accepted. "
                "Implementation then defers to the stage resolving "
                "null-track semantics."),
            "frozen_tolerances_basis": (
                "adapter missing_tyre_age refusal (no fabrication); "
                "V3.2F lap-1 all-null finding; V3.2K pit-boundary risk "
                "(pit gate 0.9412 < 0.95)"),
        },
        {
            "protocol_id": "V3.11B-PROTOCOL-K1",
            "rule_id": "NULL_TRACK_SEMANTICS",
            "hypothesis": (
                "H-K1: a pre-first-message null track token implies "
                "all_clear (message feed live from race start)."),
            "candidate_subset": by_subtype.get("NULL_TRACK", []),
            "runtime_inputs": ["null token at T", "message-feed liveness"],
            "prohibited_inputs": [
                "invented status", "later first message (as runtime "
                "evidence)", "assumed green without feed-liveness proof",
            ],
            "validity_interval": "none established",
            "invalidation_conditions": [
                "no prior known status in 0/64 null states (V3.11A)",
                "feed liveness from race start unproven",
                "source interpretation is a later-stage question (V3.11B "
                "§4/§18)",
            ],
            "evaluation_labels": "none collected in B",
            "metrics": ["null states with known prior status <=T: 0/64"],
            "acceptance_criteria": {
                "K1": "NOT PURSUED in B: requires source-interpretation "
                      "validation owned by the later track-source stage.",
            },
            "rejection_criteria": [
                "H-K1 cannot be tested without inventing status in B.",
            ],
            "accepted_coverage_effect": [0, 0],
            "predeclared_verdict": (
                "REJECTED for B (DEFERRED to track-source stage); the "
                "registry confirms all 59 are pre-first-message nulls "
                "with no causal prior, i.e. no otherwise-proof per §18."),
            "frozen_tolerances_basis": (
                "engine refuses null track_state explicitly; V3.2F keeps "
                "the refusal; V3.11A hypothetical persistence 0/64"),
        },
    ]

    doc = {
        "schema_version": "v3.11b-reconstruction-protocol-v1",
        "declared_before_results": True,
        "registry_sha256": reg_hash,
        "rule_classes": [
            "TIMING_GAP_RECONSTRUCTION",
            "TYRE_WITHIN_STINT_PERSISTENCE",
            "NULL_TRACK_SEMANTICS (deferred, no B validation)",
        ],
        "no_generic_carry_forward": True,
        "protocols": protocols,
    }
    text = json.dumps(doc, indent=1, sort_keys=True)
    doc["protocol_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    with open(OUT / "reconstruction_protocol.json", "w",
              encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(json.dumps({
        "status": "OK",
        "protocol_sha256": doc["protocol_sha256"],
        "wall_s": round(time.perf_counter() - t0, 1),
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
