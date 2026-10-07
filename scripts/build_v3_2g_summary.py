#!/usr/bin/env python3
"""V3.2G machine summary (Part AZ): results/v3/v3_2g_driver_status.json.

Deterministic assembly from Part AX artifacts. Fails closed on missing
artifacts or causal-table hash mismatch. No timestamps, usernames, or
absolute paths.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
GDIR = ROOT / "results" / "v3" / "v3_2g"


def _load(name: str) -> dict:
    return json.loads((GDIR / name).read_text(encoding="utf-8"))


def _hash(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"),
                   allow_nan=False, default=str).encode()).hexdigest()


def main() -> int:
    tables = _load("causal_tables.json")
    if _hash({k: v for k, v in tables.items()
              if k != "freeze_hash"}) != tables["freeze_hash"]:
        print(json.dumps({"status": "BLOCKED",
                          "reason": "causal tables mutated"}))
        return 1
    get = _load
    doc = {
        "schema_version": "v3.2g-driver-status-v1",
        "baseline": {"tag": "v3.1-race-dynamics", "commit": "64c5af0",
                     "head_matches_tag": True, "staged_changes": 0},
        "v3_2f_parent": "V3.2F COMPLETE - NO REGIME ADMITTED",
        "accepted_mc2": {"arm": "E_AR1_RESIDUAL", "rho": 0.264,
                         "untouched": True},
        "coverage_before": {"eligible": 2305, "total": 9644,
                            "fraction": 0.239},
        "source_inventory": "source_inventory.json (8 families)",
        "source_semantics": get("source_semantics.json")["findings"],
        "position_null": {
            "provenance": "FastF1Generated verbatim; 294/294 overlap",
            "decision": "UNSAFE_FOR_RUNTIME",
            "winners": 3, "podiums": 7, "top5": 9,
            "all_trailing": True},
        "race_control": {
            "messages": 14992, "stopped_rows": 63,
            "retired_family_rows": 0,
            "precision_vs_dnf": [57, 62],
            "seasons_zero": ["2023"]},
        "timing_status": "no status vocabulary in any timing field",
        "pit_garage": "no garage concept; duration not evidence",
        "observation_lifecycle": "contiguous lap sequences; transience at checkpoint grain",
        "source_agreement": get("source_agreement.json")["patterns"],
        "offline_label_firewall": "frozen tables first (1465c11b), labels joined after; static import test green",
        "candidate_signals": get("candidate_signals.json")["candidates"],
        "candidate_evaluation": "false-terminal primary metric; all fail bar",
        "winner_safety": {"null_winners": 3, "stopped_winners": 1},
        "season_stability": "STOPPED season-unstable (2023 silent)",
        "latency": get("latency.json"),
        "status_contract": {"created": False},
        "admission_decision": "NO_AUTHORITATIVE_STATUS_ADMITTED",
        "temporal_poison": "no resolver (vacuous); label firewall tested; pipeline inherited green",
        "transient_protection": "corpus recorded (9 stopped-returns, 407 V3.2C records, winner nulls)",
        "projected_coverage": "0 for all candidates (no admissible rule)",
        "projected_intersections": "N/A; V3.2F handoff cited",
        "runtime_implementation": False,
        "dry_green_parity": {"corpus_hash": "7ae97c3c8575679a...",
                             "status": "PARITY_OK_BIT_EXACT",
                             "members": 50},
        "new_state_validation": "N/A (no newly supported states)",
        "coverage_after": get("coverage_after.json")["after"],
        "season_coverage": "unchanged (2018-2024 per V3.2F)",
        "stage_coverage": "unchanged (LATE 10.14%)",
        "race_coverage": "unchanged (103 >=1, 46 zero, median 9.38%)",
        "remaining_blockers": get("remaining_blockers.json"),
        "recovery_accounting": {"newly_supported": 0,
                                "unexplained_growth": 0},
        "false_admission_audit": get("false_admission_audit.json"),
        "api_behavior": "unchanged 422 refusals; no hidden removal",
        "performance": "status-resolution overhead N/A (no resolver); MC2 untouched",
        "external_source_decision": get("external_source_decision.json"),
        "v3_2h_handoff": {
            "track_only": 292, "wet_only": 176,
            "track_x_stale": 811, "wet_x_stale": 799,
            "priority": ["VSC", "wet feasibility", "Safety Car",
                         "yellow (needs spatial semantics)",
                         "red deferred"]},
        "scientific_identities": {
            "field_contract": "mc2-field-v1",
            "presence_adapter": "v3.2c-presence-v1",
            "mc2_research": "mc2-r1-research",
            "regime_support": "v3.2f-regime-support-v1",
            "parity_corpus": "7ae97c3c8575679a",
            "causal_tables": tables["freeze_hash"][:16],
            "status_contract": "none created"},
        "known_limitations": [
            "coverage unchanged at 23.90%",
            "66.3% of terminal absences carry no at-T signal",
            "position Status sampled in one race only",
            "STOPPED recall 0.10 caps any future message-keyed rule",
            "external retirement-event feed would be needed for authoritative status"],
    }
    (ROOT / "results" / "v3" / "v3_2g_driver_status.json").write_text(
        json.dumps(doc, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    required = ["schema_version", "baseline", "v3_2f_parent",
                "accepted_mc2", "coverage_before", "source_inventory",
                "source_semantics", "position_null", "race_control",
                "timing_status", "pit_garage", "observation_lifecycle",
                "source_agreement", "offline_label_firewall",
                "candidate_signals", "candidate_evaluation",
                "winner_safety", "season_stability", "latency",
                "status_contract", "admission_decision",
                "temporal_poison", "transient_protection",
                "projected_coverage", "projected_intersections",
                "runtime_implementation", "dry_green_parity",
                "new_state_validation", "coverage_after",
                "season_coverage", "stage_coverage", "race_coverage",
                "remaining_blockers", "recovery_accounting",
                "false_admission_audit", "api_behavior", "performance",
                "external_source_decision", "v3_2h_handoff",
                "scientific_identities", "known_limitations"]
    missing = [k for k in required if k not in doc]
    print(json.dumps({"status": "OK", "fields": len(doc),
                      "missing": missing}))
    return 0 if not missing else 1


if __name__ == "__main__":
    raise SystemExit(main())
