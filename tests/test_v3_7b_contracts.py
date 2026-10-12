"""V3.7B contract tests: machine-testable counterfactual execution contract.

Pure contracts only (synthetic state/identities; no simulations). Covers
plan/schedule identity, trigger semantics, lifecycle, conflicts,
eligibility, comparison keys, outcome schemas, CRN/pair policy, temporal
guards, and frozen-tree isolation.
"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from raceintel.counterfactual import contracts as C

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "results" / "v3" / "v3_7b" / "counterfactual_execution_contract.json"
DOC_PATH = ROOT / "docs" / "V3_7B_PLAN_CONTRACTS_ELIGIBILITY_AND_TRANSITIONS.md"
SID = "s" * 64


def _load(path):
    return json.loads(path.read_text())


def _contract():
    return _load(CONTRACT_PATH)


def _iv(n=3, target="norris", compound="MEDIUM", lap=20):
    return C.ScheduledIntervention(
        target_driver_id=target, kind="PIT_IN_N_LAPS", lap_offset_n=n,
        requested_compound=compound, decision_lap=lap,
        decision_state_identity=SID)


def _plan(targets=("norris",), n=3, rival=None):
    return C.CounterfactualPlan(
        target_driver_ids=targets, interventions=(_iv(n, targets[0]),),
        rival_driver_id=rival)


def _key(form="REFERENCE_VS_PLAN", base="SIMULATED_NO_INTERVENTION_REFERENCE",
         alt="a" * 64, rival=None):
    return C.PlanComparisonKey(
        key_version=C.COMPARISON_KEY_VERSION, comparison_form=form,
        state_identity=SID, base_identity=base, alternative_identity=alt,
        simulator_identity="MC2-E (E_AR1_RESIDUAL)",
        parameter_identity="p" * 64,
        simulation_count=5000, master_seed=20240101,
        outcome_schema_version=C.OUTCOME_SCHEMA_VERSION,
        rival_driver_id=rival)


# --- A provenance ---


def test_a_identity_exact():
    assert _contract()["a_provenance"]["identity"] == \
        "1735954212ec31286fede041639875610003a09cf817177e22cc908e3fcb0a12"


# --- canonicalization / identity ---


def test_plan_canonicalization_deterministic():
    assert _plan().identity() == _plan().identity()


def test_plan_permutation_invariance():
    a = C.CounterfactualPlan(
        target_driver_ids=("norris", "piastri"),
        interventions=(_iv(5, "norris"), _iv(3, "piastri")))
    b = C.CounterfactualPlan(
        target_driver_ids=("piastri", "norris"),
        interventions=(_iv(3, "piastri"), _iv(5, "norris")))
    assert a.identity() == b.identity()


def test_plan_identity_changes_for_meaningful_changes():
    assert _plan(n=3).identity() != _plan(n=4).identity()
    assert _plan().identity() != _plan(rival="verstappen").identity()
    other = C.CounterfactualPlan(
        target_driver_ids=("norris",),
        interventions=(_iv(3, "norris", compound="SOFT"),))
    assert _plan().identity() != other.identity()


def test_canonical_json_stability():
    assert json.dumps(_plan().to_dict(), sort_keys=True) == \
        json.dumps(_plan().to_dict(), sort_keys=True)


def test_b_identity_deterministic():
    c = _contract()
    identity = c.pop("contract_hash")
    blob = json.dumps(c, sort_keys=True, separators=(",", ":")).encode()
    assert identity == hashlib.sha256(blob).hexdigest()
    assert identity == "1865537503136ed3d8603e53741902c320df9387222655b38eef51640294e970"


# --- N / horizon / trigger ---


def test_n_validation():
    with pytest.raises(C.CounterfactualPlanError):
        _iv(n=0)
    with pytest.raises(C.CounterfactualPlanError):
        _iv(n=-2)


def test_remaining_lap_validation():
    _iv(n=3).validate_horizon(60)
    with pytest.raises(C.CounterfactualPlanError):
        _iv(n=40, lap=20).validate_horizon(60)


def test_off_by_one_trigger_semantics():
    assert _iv(n=1, lap=20).scheduled_lap == 21
    assert _iv(n=2, lap=20).scheduled_lap == 22
    assert C.mechanical_equivalent_action(1) == "PIT_NOW"
    assert C.mechanical_equivalent_action(2) == "PIT_NEXT_LAP"
    assert C.mechanical_equivalent_action(3) is None


def test_compound_validation():
    with pytest.raises(C.CounterfactualPlanError):
        _iv(compound="INTERMEDIATE")
    with pytest.raises(C.CounterfactualPlanError):
        _iv(compound="WET")
    assert _iv(compound=None).requested_compound is None
    assert set(C.SUPPORTED_REQUESTED_COMPOUNDS) == {
        "SOFT", "MEDIUM", "HARD", "SAMPLED"}


# --- multi-stop / duplicates / conflicts ---


def test_multi_stop_ordering():
    plan = C.CounterfactualPlan(
        target_driver_ids=("norris",),
        interventions=(_iv(5, "norris"), _iv(2, "norris")))
    laps = [i["lap_offset_n"] for i in plan.to_dict()["interventions"]]
    assert laps == [2, 5]


def test_duplicate_handling():
    assert C.classify_conflict(_iv(3), _iv(3)) == "DEDUPLICATE"


def test_conflict_rejection():
    assert C.classify_conflict(_iv(3, compound="SOFT"), _iv(3, compound="HARD")) == "INVALID"
    assert C.classify_conflict(_iv(2), _iv(5)) == "RUNTIME_SUPERSESSION"
    assert C.classify_conflict(_iv(3, "norris"), _iv(3, "piastri")) == "VALID"


# --- targets / rival ---


def test_target_validation():
    with pytest.raises(C.CounterfactualPlanError):
        C.CounterfactualPlan(target_driver_ids=(), interventions=(_iv(),))
    with pytest.raises(C.CounterfactualPlanError):
        C.CounterfactualPlan(target_driver_ids=("norris",),
                             interventions=(_iv(target="piastri"),))


def test_rival_not_target():
    with pytest.raises(C.CounterfactualPlanError):
        _plan(rival="norris")
    assert _plan(rival="verstappen").rival_driver_id == "verstappen"


def test_rival_presence_requirements():
    with pytest.raises(C.CounterfactualPlanError):
        _plan(rival="")


# --- lifecycle / transitions ---


def test_lifecycle_enum_exact():
    assert C.LIFECYCLE_STATES == ("PLANNED", "ELIGIBLE", "EXECUTED", "INERT",
                                  "SUPERSEDED", "CANCELLED", "TERMINAL", "INVALID")
    assert C.LIFECYCLE_V36_MAPPING["EXECUTED"] == "INTERVENTION_APPLIED"
    assert C.LIFECYCLE_V36_MAPPING["SUPERSEDED"] == "INTERVENTION_SUPERSEDED"
    assert C.LIFECYCLE_V36_MAPPING["CANCELLED"] == "INTERVENTION_RACE_END_CANCELLED"
    assert C.LIFECYCLE_V36_MAPPING["PLANNED"] is None


def test_legal_transitions():
    assert C.transition_allowed("PLANNED", "ELIGIBLE")
    assert C.transition_allowed("ELIGIBLE", "EXECUTED")
    assert C.transition_allowed("ELIGIBLE", "SUPERSEDED")
    assert C.transition_allowed("PLANNED", "INVALID")


def test_illegal_transitions_fail_closed():
    assert not C.transition_allowed("EXECUTED", "ELIGIBLE")
    assert not C.transition_allowed("PLANNED", "EXECUTED")
    with pytest.raises(C.CounterfactualPlanError):
        C.transition_allowed("PLANNED", "NOPE")
    with pytest.raises(C.CounterfactualPlanError):
        C.transition_allowed("NOPE", "ELIGIBLE")


def test_supersession_classification():
    blob = json.dumps(_contract()["supersession"])
    assert "SUPERSEDED" in blob and "no_silent_reschedule" in blob


def test_terminal_classification():
    term = _contract()["terminal_semantics"]
    assert term["request_time_invalid"] == "INVALID"
    assert term["never_negative_result"] is True


# --- eligibility / unsupported ---


def test_eligibility_hierarchy():
    assert C.ELIGIBILITY_LEVELS == ("STATE", "INTERVENTION", "PLAN", "COMPARISON")
    assert len(C.V37_REASON_CODES) == 6
    assert "INVALID_TRIGGER" in C.V37_REASON_CODES


def test_unsupported_metrics_empty():
    u = C.build_unsupported_result(
        level="PLAN", reason_code="INVALID_TRIGGER", human_reason="bad N",
        state_identity=SID)
    assert u["supported"] is False
    assert u["metrics"] == {}
    assert "NaN" not in json.dumps(u)


# --- comparison keys / orientation ---


def test_reference_vs_plan_key_deterministic():
    assert _key().identity() == _key().identity()
    assert _key(alt="b" * 64).identity() != _key().identity()


def test_plan_vs_plan_key_deterministic():
    k = _key(form="PLAN_VS_PLAN", base="a" * 64, alt="b" * 64)
    assert k.identity() == _key(form="PLAN_VS_PLAN", base="a" * 64, alt="b" * 64).identity()
    with pytest.raises(C.CounterfactualPlanError):
        _key(form="PLAN_VS_PLAN", base="a" * 64, alt="a" * 64)


def test_plan_vs_plan_orientation_exact():
    d = _contract()["delta_orientation"]
    assert d["rule"].startswith("POSITIVE = IMPROVEMENT")
    assert d["delta_expected_finish"] == "base - alt"


def test_positive_delta_orientation():
    assert C.DELTA_ORIENTATION["delta_win_frequency"] == "alt - base"
    assert C.DELTA_ORIENTATION["delta_expected_finish"] == "base - alt"


def test_expected_finish_sign():
    assert _contract()["delta_orientation"]["delta_expected_finish"].startswith("base - alt")


# --- config / CRN / pairs ---


def test_5000_production_futures():
    assert C.PRODUCTION_SIMULATION_COUNT == 5000
    with pytest.raises(C.CounterfactualPlanError):
        _key().to_dict() and C.PlanComparisonKey(
            **{**_key().to_dict(), "simulation_count": 1000})


def test_seed_semantics_unchanged():
    assert C.DEFAULT_MASTER_SEED == 20240101
    assert "PCG64" in C.SEED_STREAM_RULE


def test_crn_identity():
    assert "same simulation index" in C.CRN_RULE
    assert "only the" in C.CRN_RULE and "schedule" in C.CRN_RULE


def test_complete_pair_policy():
    blob = json.dumps(_contract()["complete_pair_contract"])
    assert "complete valid pairs" in blob and "imputed" in blob


# --- outcome schemas ---


def test_ahead_of_rival_schema():
    assert "p_ahead_of_rival" in C.V37_OUTCOME_METRICS
    assert _contract()["ahead_of_rival_semantics"]["inputs"] == \
        "simulated finishing order only"


def test_pit_count_schema():
    assert "pit_count" in C.V37_OUTCOME_METRICS
    assert "forced pits counted" in _contract()["pit_count_semantics"]["representation"]


def test_position_gain_schema():
    assert "position_gain_loss" in C.V37_OUTCOME_METRICS
    assert "factual_position_T - simulated_final_position" in \
        _contract()["position_gain_semantics"]["per_future"]


def test_position_gain_examples():
    assert C.position_gain(5, 2) == 3
    assert C.position_gain(5, 5) == 0
    assert C.position_gain(5, 8) == -3


def test_position_gain_delta_examples():
    # REFERENCE_VS_PLAN: plan_gain - reference_gain.
    assert C.position_gain(5, 3) - C.position_gain(5, 4) == 1  # +2 vs +1
    # PLAN_A_VS_PLAN_B: B_gain - A_gain.
    assert C.position_gain(5, 6) - C.position_gain(5, 3) == -3  # -1 vs +2
    assert _contract()["position_gain_semantics"]["comparative_delta"].startswith(
        "plan_gain - reference_gain")


def test_position_gain_no_historical_final():
    blob = json.dumps(_contract()["position_gain_semantics"]).lower()
    assert "never historical final result" in blob
    assert "historical_position_gain" not in blob
    assert "actual positions gained" not in blob


# --- temporal / rejected ---


def test_post_t_fields_forbidden():
    assert "observed_future_pit_lap" in C.FORBIDDEN_PLAN_FIELDS
    assert "future_weather" in C.FORBIDDEN_PLAN_FIELDS
    assert "recommendation_score" in C.FORBIDDEN_PLAN_FIELDS


def test_weather_intervention_rejected():
    assert "WEATHER" in C.REJECTED_INTERVENTION_KINDS
    with pytest.raises(C.CounterfactualPlanError):
        C.ScheduledIntervention(
            target_driver_id="norris", kind="WEATHER", lap_offset_n=2,
            decision_lap=20, decision_state_identity=SID)


def test_sc_intervention_rejected():
    assert "SAFETY_CAR" in C.REJECTED_INTERVENTION_KINDS
    with pytest.raises(C.CounterfactualPlanError):
        C.ScheduledIntervention(
            target_driver_id="norris", kind="SAFETY_CAR", lap_offset_n=2,
            decision_lap=20, decision_state_identity=SID)


def test_retirement_intervention_rejected():
    assert "RETIREMENT" in C.REJECTED_INTERVENTION_KINDS
    with pytest.raises(C.CounterfactualPlanError):
        C.ScheduledIntervention(
            target_driver_id="norris", kind="RETIREMENT", lap_offset_n=2,
            decision_lap=20, decision_state_identity=SID)


def test_race_state_edits_rejected():
    for kind in ("ARBITRARY_POSITION", "ARBITRARY_GAP", "ARBITRARY_PACE",
                 "ARBITRARY_TYRE_AGE"):
        assert kind in C.REJECTED_INTERVENTION_KINDS
        with pytest.raises(C.CounterfactualPlanError):
            C.ScheduledIntervention(
                target_driver_id="norris", kind=kind, lap_offset_n=2,
                decision_lap=20, decision_state_identity=SID)


def test_undercut_primitive_rejected():
    assert "UNDERCUT" in C.REJECTED_INTERVENTION_KINDS
    with pytest.raises(C.CounterfactualPlanError):
        C.ScheduledIntervention(
            target_driver_id="norris", kind="UNDERCUT", lap_offset_n=2,
            decision_lap=20, decision_state_identity=SID)


def test_overcut_primitive_rejected():
    assert "OVERCUT" in C.REJECTED_INTERVENTION_KINDS


# --- isolation ---


def test_v35_absent():
    src = (ROOT / "raceintel" / "counterfactual" / "contracts.py").read_text()
    assert "v3_5" not in src and "V3_5" not in src


def test_no_api_import():
    src = (ROOT / "raceintel" / "counterfactual" / "contracts.py").read_text()
    assert "from api" not in src and "import api" not in src


def test_no_frontend_import():
    src = (ROOT / "raceintel" / "counterfactual" / "contracts.py").read_text()
    assert "from frontend" not in src and "import frontend" not in src


def test_no_execution_function():
    src = (ROOT / "raceintel" / "counterfactual" / "contracts.py").read_text()
    assert "def run_" not in src and "def execute" not in src
    assert "MonteCarloEngine" not in src


def test_doc_required_sections():
    doc = DOC_PATH.read_text()
    for section in ("## Final verdict", "## Reuse audit",
                    "## CounterfactualPlan", "## PIT_IN_N_LAPS semantics",
                    "## Transition table", "## C readiness"):
        assert section in doc, section
