"""V3.11B causal state reconstruction: focused guards (read-only).

Pins the B scientific contract: exact R2 registry, pre-declared protocol,
three evidence-backed rejections, zero production implementation, parity,
and causal-lookup boundary/poison properties. Nothing here changes
eligibility, RaceState, freshness, MC2, or the Pit Wall.
"""

from __future__ import annotations

import ast
import json
from bisect import bisect_right
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_11b"
A = ROOT / "results" / "v3" / "v3_11a"

PROTOCOL_SHA = "5849607042825ca6d31e049e880b3ddde8b693b5c739e2182268021acfa357ef"
REGISTRY_SHA = "f8e0c565e681eebc9554f14a5085ca0b3a6ed29abace14de037638a626e9e38a"


def _load(name):
    with open(OUT / name, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def registry():
    return _load("r2_candidate_registry.json")


@pytest.fixture(scope="module")
def rules():
    return _load("rule_registry.json")


# ---- REGISTRY ----

def test_r2_registry_exact_114(registry):
    assert registry["n"] == 114
    assert registry["exact"] is True
    assert registry["by_subtype"] == {"NULL_TRACK": 59, "TIMING_GAP": 51,
                                      "TYRE_STINT": 4}
    assert registry["registry_sha256"] == REGISTRY_SHA
    ids = [c["state_id"] for c in registry["candidates"]]
    assert len(set(ids)) == 114  # no duplicates


def test_all_candidates_trace_to_A(registry):
    ledger = json.loads(
        (A / "unsupported_state_ledger.json").read_text(
            encoding="utf-8"))["states"]
    r2_ids = {(r["race_id"], r["frame_index"]) for r in ledger
              if r["recovery_class"] == "R2_DOMAIN_RULE_REQUIRED"}
    reg_ids = {(c["race_id"], c["frame_index"])
               for c in registry["candidates"]}
    assert reg_ids == r2_ids
    for c in registry["candidates"]:
        src = next(r for r in ledger
                   if (r["race_id"], r["frame_index"])
                   == (c["race_id"], c["frame_index"]))
        assert c["original_frozen_reason"] == src["original_reason"]


def test_no_r3_r4_r5_candidate_enters_B(registry):
    ledger = json.loads(
        (A / "unsupported_state_ledger.json").read_text(
            encoding="utf-8"))["states"]
    by_id = {(r["race_id"], r["frame_index"]): r["recovery_class"]
             for r in ledger}
    for c in registry["candidates"]:
        assert by_id[(c["race_id"], c["frame_index"])] == \
            "R2_DOMAIN_RULE_REQUIRED"


def test_ceiling_arithmetic_is_39_32():
    rec = _load("candidate_reconciliation.json")
    assert rec["r2_unique_states"] == 114
    assert rec["ceiling"] == {"eligible": 3792, "total": 9644,
                              "fraction": 0.3932}
    assert rec["prose_discrepancy"]["machine_authoritative"] == 0.3932
    assert rec["prose_discrepancy"]["v3_11a_artifacts_rewritten"] is False


# ---- PROTOCOL ----

def test_every_rule_registered_with_criteria():
    protocol = _load("reconstruction_protocol.json")
    assert protocol["protocol_sha256"] == PROTOCOL_SHA
    assert protocol["declared_before_results"] is True
    assert protocol["no_generic_carry_forward"] is True
    ids = {p["rule_id"] for p in protocol["protocols"]}
    assert ids == {"TIMING_GAP_RECONSTRUCTION",
                   "TYRE_WITHIN_STINT_PERSISTENCE", "NULL_TRACK_SEMANTICS"}
    for p in protocol["protocols"]:
        assert p["acceptance_criteria"] and p["rejection_criteria"]
        assert p["prohibited_inputs"]


def test_every_rule_has_verdict(rules):
    assert rules["protocol_sha256"] == PROTOCOL_SHA
    assert rules["accepted_rules"] == []
    assert sorted(rules["rejected_rules"]) == [
        "NULL_TRACK_SEMANTICS", "TIMING_GAP_RECONSTRUCTION",
        "TYRE_WITHIN_STINT_PERSISTENCE"]
    assert rules["insufficient_evidence_rules"] == []
    assert rules["forced_acceptance"] is False
    for r in rules["rules"]:
        assert r["verdict"] == "REJECTED"
        assert r["production_implementation"] is False


# ---- TIMING ----

def test_timing_rejected_on_predeclared_criteria():
    validation = _load("timing_gap_validation.json")
    assert validation["protocol_sha256"] == PROTOCOL_SHA
    assert validation["T1_lap_unanimity"] == "0/54"
    assert validation["T2_position_unanimity"] == "0/54"
    assert validation["T3_exclusion_survival_states"] == "0/51"
    assert validation["criteria_met"] == {"T1": False, "T2": False,
                                          "T3": False, "T4": True}
    assert validation["verdict"] == "REJECTED"


def test_timing_v32k_objection_covered():
    review = _load("v32k_failure_review.json")
    assert review["k_objection_resolved"] is False
    assert "0.8551" in review["failed_gates"]["position"]
    assert "RAW_SOURCE_STALE 2866" in review["reason_for_rejection"]
    assert "NOT the revived K rule" in review["b_comparison"]


def test_timing_no_regime_bridging():
    analysis = _load("timing_gap_analysis.json")
    assert analysis["exclusion_hits"]["regime_during_gap_offenders"] == 48
    assert analysis["leader_laps_advanced_during_gap"]["min"] >= 4


# ---- TYRE ----

def test_tyre_rejected_no_prior_compound():
    validation = _load("tyre_persistence_validation.json")
    assert validation["protocol_sha256"] == PROTOCOL_SHA
    assert validation["Y1_same_stint_states"] == "0/4"
    assert validation["verdict"] == "REJECTED"
    analysis = _load("tyre_persistence_analysis.json")
    for s in analysis["per_state"]:
        assert s["drivers_with_prior_compound"] == 0
        assert s["drivers_Y1"] == 0


def test_tyre_no_default_compound_anywhere():
    text = (OUT / "tyre_persistence_analysis.json").read_text()
    assert "DEFAULT" not in text
    for token in ("strategy-based", "next-row backfill", "likely compound"):
        assert token not in text.lower()


# ---- PARITY ----

def test_native_eligible_states_identical():
    parity = _load("native_parity_validation.json")
    assert parity["production_diff_empty"] is True
    assert parity["eligible_catalogue_corpus_hash_unchanged"] is True
    assert parity["eligible_states_identical"] is True


def test_unrelated_unsupported_states_identical():
    parity = _load("unsupported_parity_validation.json")
    assert parity["collateral_eligibility_expansion"] == 0
    assert parity["outside_accepted_subset_recovered"] == 0
    assert parity["reason_counts_unchanged"] == {
        "STALE_ROSTER_OBSERVATION": 3294, "UNSUPPORTED_TRACK_STATE": 1165,
        "WET_CONDITIONS": 801, "MISSING_DRIVER_OBSERVATION": 354,
        "MISSING_TYRE_STATE": 198, "TERMINAL_STATE": 154}


def test_no_eligible_to_unsupported_transitions():
    ledger = _load("eligibility_transition_ledger.json")
    assert ledger["transitions"] == []
    assert ledger["eligible_to_unsupported"] == 0
    assert ledger["counts"] == {
        "previously_eligible_still_eligible": 3678,
        "unsupported_still_unsupported": 5966}


# ---- ELIGIBILITY ----

def test_only_accepted_rule_states_may_become_eligible(rules):
    ledger = _load("eligibility_transition_ledger.json")
    assert rules["accepted_rules"] == []
    assert ledger["unsupported_to_eligible"] == []


def test_coverage_reconciles_exactly():
    coverage = _load("coverage_re_evaluation.json")
    assert (coverage["eligible"], coverage["unsupported"],
            coverage["coverage"]) == (3678, 5966, 0.3814)
    assert coverage["delta_vs_v3_10"] == 0
    mc2 = _load("mc2_input_validation.json")
    assert mc2["status"] == "NOT_APPLICABLE_ZERO_NEWLY_ELIGIBLE"
    assert mc2["full_5000_future_simulations_run"] == 0


# ---- POISON + BOUNDARIES (causal-lookup pattern B relies on) ----

def causal_lookup(times, T):
    """Latest index with times[i] <= T (B analysis pattern).

    bisect_right on the full sorted list: rows >T sort after the
    insertion point and are never addressed. Poison rows change
    nothing because they are never read.
    """
    ordered = sorted(times)
    return bisect_right(ordered, T) - 1


def test_future_timing_ignored_by_causal_lookup():
    assert causal_lookup([100.0, 200.0, 300.0], 250.0) == 1
    poisoned = [100.0, 200.0, 300.0, 210.0, 260.0, 400.0]
    assert causal_lookup(poisoned, 250.0) == 2  # latest <=T is 210.0
    assert causal_lookup(poisoned, 205.0) == 1  # 210/260/400 ignored
    assert [t for t in sorted(poisoned)
            if t <= 205.0] == [100.0, 200.0]


def test_boundary_equality_semantics():
    assert causal_lookup([100.0, 200.0], 200.0) == 1  # ==T observed
    assert causal_lookup([100.0, 200.0], 199.9) == 0  # just before
    assert causal_lookup([200.1], 200.0) == -1  # just after: no prior


def test_no_reconstruction_in_production():
    for path in (ROOT / "raceintel").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "CAUSALLY_PERSISTED" not in text
        assert "TIMING_GAP_RECONSTRUCTION" not in text
        assert "TYRE_WITHIN_STINT_PERSISTENCE" not in text


def test_poison_validations_pass():
    for name in ("temporal_poison_validation.json",
                 "boundary_validation.json"):
        doc = _load(name)
        assert "0" in json.dumps(doc) or "PASS" in json.dumps(doc)
    poison = _load("temporal_poison_validation.json")
    assert poison["future_timing_consumed"] == 0
    assert poison["future_tyre_consumed"] == 0
    assert poison["future_pit_consumed"] == 0
    assert poison["future_track_consumed"] == 0
    assert poison["future_retirement_consumed"] == 0


def test_b_scripts_are_read_only_and_side_effect_free():
    for script in ("v3_11b_r2_registry.py", "v3_11b_protocol.py",
                   "v3_11b_timing_gap.py", "v3_11b_tyre.py",
                   "v3_11b_reviews.py", "v3_11b_evaluate.py"):
        tree = ast.parse(
            (ROOT / "scripts" / script).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        assert "raceintel" not in imported, script
        assert "api" not in imported, script
