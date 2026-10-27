#!/usr/bin/env python3
"""V3.11B step 5 -- failure review, deferred analysis, rule registry.

Emits (deterministic, read-only; frozen evidence + B validation outputs):
  - v32k_failure_review.json
  - deferred_rule_analysis.json
  - rule_registry.json (three-way verdicts per rule)

No production import. No eligibility mutation.

Usage:
    .venv/bin/python scripts/v3_11b_reviews.py
"""

from __future__ import annotations

import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_11b"


def _write(name: str, doc: dict) -> None:
    with open(OUT / name, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")


def main() -> int:
    t0 = time.perf_counter()
    protocol = json.loads(
        (OUT / "reconstruction_protocol.json").read_text(encoding="utf-8"))
    proto_hash = protocol["protocol_sha256"]
    timing = json.loads(
        (OUT / "timing_gap_validation.json").read_text(encoding="utf-8"))
    tyre = json.loads(
        (OUT / "tyre_persistence_validation.json").read_text(encoding="utf-8"))
    tdet = json.loads(
        (OUT / "timing_gap_analysis.json").read_text(encoding="utf-8"))

    _write("v32k_failure_review.json", {
        "schema_version": "v3.11b-v32k-failure-review-v1",
        "source": "docs/V3_2K_RAW_TIMING_STATE_RECONSTRUCTION.md + "
                  "results/v3/v3_2k_raw_timing_state_reconstruction.json "
                  "(frozen, read-only)",
        "intended_rule": (
            "Keep stale drivers in the field by reconstructing a complete "
            "causal contemporaneous state from raw live timing "
            "(TimingData/TimingAppData/Position/CarData deltas, latest "
            "t <= T via bisect_right)."),
        "validation_protocol": (
            "Preregistered (sha 567260af...) target 3294 STALE states + 420 "
            "trusted controls; admission gates position>=0.99, lap>=0.99, "
            "pit>=0.95, poison 100%, determinism, season consistency, "
            "lapped/tyre/pace safety, winner firewall."),
        "failed_gates": {
            "position": "0.8551 < 0.99 (raw FRESHER than canonical, median "
                        "7.5s: tower shuffles vs lap-crossing -- different "
                        "observation events, not reconstructor error)",
            "lap": "0.9485 < 0.99 (all diffs -1; raw NumberOfLaps lags D9 "
                   "LAP_END by median 88.2s; cannot supply anything fresher "
                   "than D9)",
            "pit": "0.9412 < 0.95 (raw-ahead-by-one boundary; "
                   "NumberOfPitStops absent 2020/2022/2023)",
            "tyre": "FAIL (TimingData carries no compound/age; 2019-2023 "
                    "TimingAppData not local)",
        },
        "reason_for_rejection": (
            "Zero FULL candidates under the frozen required-state "
            "definition; residual decomposition RAW_SOURCE_STALE 2866: raw "
            "TimingData is equally stale for stale drivers -- staleness is "
            "real-world (driver not crossing), not a processed-data "
            "artifact. Hypothesis rejected; "
            "REJECT_DIRECT_RAW_STATE_RECONSTRUCTION."),
        "b_comparison": (
            "V3.11B H-T1 is NOT the revived K rule: K sought FRESHER raw "
            "observations to replace stale D9 rows; H-T1 sought to persist "
            "the stale D9 row itself across the gap. Different mechanism, "
            "same underlying objection (no contemporaneous evidence "
            "exists), tested independently against pre-declared unanimity "
            "criteria on the 51-state subset."),
        "b_evidence_against_h_t1": {
            "persisted_vs_next_lap_exact": "0/54",
            "persisted_vs_next_position_exact": "0/54",
            "states_surviving_exclusions": "0/51",
            "gap_s_median": tdet["gap_s"]["median"],
            "leader_laps_advanced_median": tdet[
                "leader_laps_advanced_during_gap"]["median"],
            "regime_during_gap_offenders": tdet["exclusion_hits"][
                "regime_during_gap_offenders"],
            "race_time_abs_err_s_median": tdet["persisted_vs_next"][
                "race_time_abs_err_s"]["median"],
        },
        "k_objection_resolved": False,
        "conclusion": (
            "K's objection stands unanswered and B adds an independent "
            "rejection: freezing dynamic timing fields across 4-29 leader "
            "laps (median 16) with 48/54 gaps containing yellow regimes "
            "fabricates race state. TIMING_GAP_RECONSTRUCTION = REJECTED."),
    })

    _write("deferred_rule_analysis.json", {
        "schema_version": "v3.11b-deferred-rule-analysis-v1",
        "protocol_sha256": proto_hash,
        "rules": {
            "NULL_TRACK_SEMANTICS": {
                "states": 59,
                "assessment": (
                    "All 59 are pre-first-message null tokens (leader laps "
                    "2-8); 0/64 null-track states carry any known prior "
                    "status <=T (V3.11A). H-K1 (null implies all_clear) "
                    "requires message-feed-liveness proof -- source "
                    "interpretation owned by the later track-source stage. "
                    "No status invented in B."),
                "verdict": "REJECTED for B / DEFERRED to track-source stage",
            },
            "MASS_CLOCK_RESET": {
                "states": 196,
                "assessment": (
                    "None in the R2 registry (all R4). Red-flag/restart "
                    "timing semantics are high-risk; no timestamp shifting "
                    "or normalization performed in B."),
                "verdict": "DEFERRED (restart science stage)",
            },
            "INDIVIDUAL_DISAPPEARANCE": {
                "states": 3047,
                "assessment": (
                    "Not the B target. No generic last-observation "
                    "persistence; disappearance cause unknowable <=T."),
                "verdict": "DEFERRED (bounded domain rule, future evidence)",
            },
            "DRIVER_IDENTITY": {
                "states": 0,
                "assessment": (
                    "No R2 candidate requires identity carry-forward "
                    "(R2 sublabels contain no driver rule); MISSING_DRIVER "
                    "is genuine absence (149 boundary + 205 gaps). No "
                    "alias mapping in B, as expected."),
                "verdict": "NO-OP (nothing proposed, nothing implemented)",
            },
            "WET_AND_NEUTRALIZED_REGIMES": {
                "states": "862 R3 + 1042 R4-wet (out of B scope)",
                "assessment": (
                    "Simulator-capability/scientific issues per V3.11A; no "
                    "yellow/SC/VSC/red/wet pace, evolution, or transition "
                    "modelling in B."),
                "verdict": "OUT OF SCOPE (later scientific gates)",
            },
        },
    })

    _write("rule_registry.json", {
        "schema_version": "v3.11b-rule-registry-v1",
        "protocol_sha256": proto_hash,
        "rules": [
            {"rule_id": "TIMING_GAP_RECONSTRUCTION",
             "protocol_id": "V3.11B-PROTOCOL-T1",
             "candidates": 51,
             "verdict": timing["verdict"],
             "evidence": "results/v3/v3_11b/timing_gap_validation.json",
             "production_implementation": False},
            {"rule_id": "TYRE_WITHIN_STINT_PERSISTENCE",
             "protocol_id": "V3.11B-PROTOCOL-Y1",
             "candidates": 4,
             "verdict": tyre["verdict"],
             "evidence": "results/v3/v3_11b/tyre_persistence_validation.json",
             "production_implementation": False},
            {"rule_id": "NULL_TRACK_SEMANTICS",
             "protocol_id": "V3.11B-PROTOCOL-K1",
             "candidates": 59,
             "verdict": "REJECTED",
             "evidence": "results/v3/v3_11b/deferred_rule_analysis.json",
             "production_implementation": False,
             "deferred_to": "track-source reconstruction stage"},
        ],
        "accepted_rules": [],
        "rejected_rules": ["TIMING_GAP_RECONSTRUCTION",
                           "TYRE_WITHIN_STINT_PERSISTENCE",
                           "NULL_TRACK_SEMANTICS"],
        "insufficient_evidence_rules": [],
        "forced_acceptance": False,
    })
    print(json.dumps({
        "status": "OK",
        "verdicts": {"TIMING_GAP_RECONSTRUCTION": timing["verdict"],
                     "TYRE_WITHIN_STINT_PERSISTENCE": tyre["verdict"],
                     "NULL_TRACK_SEMANTICS": "REJECTED"},
        "wall_s": round(time.perf_counter() - t0, 1),
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
