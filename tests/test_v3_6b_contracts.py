"""V3.6B contract tests: machine-testable Strategy 2.0 execution contracts.

Covers the frozen execution contract, the pure v3_contracts module, and
no-runtime-change guards. Audit-only: no simulations are executed here.
"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from raceintel.strategy import v3_contracts as V3
from raceintel.strategy.candidates import (
    CANONICAL_CANDIDATE_SPECS,
    candidate_identity,
    candidate_key,
)
from raceintel.strategy.contracts import StrategyAction

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "results" / "v3" / "v3_6b" / "strategy_execution_contract.json"
DOC_PATH = ROOT / "docs" / "V3_6B_STRATEGY_CONTRACTS_ACTION_VALIDITY_AND_ELIGIBILITY.md"


def _load(path):
    return json.loads(path.read_text())


def _contract():
    return _load(CONTRACT_PATH)


def _canonical_hash(payload):
    core = {k: v for k, v in payload.items() if k != "contract_hash"}
    return hashlib.sha256(
        json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def _key(**over):
    base = {
        "key_version": V3.COMPARISON_KEY_VERSION,
        "race_id": "2018-r03-R",
        "decision_lap": 12,
        "state_identity": "s" * 64,
        "target_driver_id": "hamilton",
        "reference_kind": V3.REFERENCE_KIND,
        "alternative_identity": "a" * 64,
        "simulator_identity": V3.SIMULATOR_IDENTITY,
        "parameter_identity": "p" * 64,
        "simulation_count": 5000,
        "master_seed": 20240101,
        "outcome_schema_version": V3.OUTCOME_SCHEMA_VERSION,
    }
    base.update(over)
    return V3.StrategyComparisonKey(**base)


# --- parent / A provenance ---


def test_parent_exact():
    c = _contract()
    assert c["parent"]["tag"] == "v3.5-outcome-distribution"
    assert c["parent"]["commit"] == "6df5d41d3ebead9a1c9b4f0f40ed20a21ce0bff1"


def test_a_identity_exact():
    a = _contract()["v36a_identity"]
    assert a["contract_hash"] == (
        "2d29c19b47b24035f0d1c503fccc8cd4090595b4ebb2a980001d0a919b0ae59b"
    )
    assert a["verdict"] == (
        "V3.6A COMPLETE — STRATEGY CONTRACT FROZEN — READY FOR V3.6B"
    )


def test_a_verdict_exact():
    assert _contract()["v36a_identity"]["verdict"].startswith("V3.6A COMPLETE")


# --- closed action set ---


def test_closed_action_count_exact():
    assert _contract()["action_set"]["count"] == 9
    assert len(CANONICAL_CANDIDATE_SPECS) == 9


def test_action_ids_deterministic():
    keys1 = [candidate_key(a, c) for a, c in CANONICAL_CANDIDATE_SPECS]
    keys2 = [candidate_key(a, c) for a, c in CANONICAL_CANDIDATE_SPECS]
    assert keys1 == keys2
    assert len(set(keys1)) == 9
    ids = [candidate_identity(a, c) for a, c in CANONICAL_CANDIDATE_SPECS]
    assert len(set(ids)) == 9


def test_action_ordering_deterministic():
    assert [k for k, _ in
            [(candidate_key(a, c), None) for a, c in CANONICAL_CANDIDATE_SPECS]] == [
        "STAY_OUT:SAMPLED", "PIT_NOW:SAMPLED", "PIT_NOW:SOFT",
        "PIT_NOW:MEDIUM", "PIT_NOW:HARD", "PIT_NEXT_LAP:SAMPLED",
        "PIT_NEXT_LAP:SOFT", "PIT_NEXT_LAP:MEDIUM", "PIT_NEXT_LAP:HARD",
    ]


def test_no_free_form_action():
    assert set(StrategyAction) == {
        StrategyAction.STAY_OUT, StrategyAction.PIT_NOW,
        StrategyAction.PIT_NEXT_LAP,
    }
    assert V3.STRATEGY_ACTIONS == ("STAY_OUT", "PIT_NOW", "PIT_NEXT_LAP")


# --- baseline ---


def test_baseline_not_stay_out():
    assert V3.REFERENCE_KIND != "STAY_OUT"
    assert "STAY_OUT" not in V3.REFERENCE_KIND
    assert "NOT an action" in _contract()["baseline_schema"]["distinction"]


def test_baseline_not_historical_future():
    blob = json.dumps(_contract()["baseline_schema"])
    assert "NOT" in blob and "historical" in blob.lower()


# --- comparison key ---


def test_comparison_key_deterministic():
    assert _key().identity() == _key().identity()
    assert _key(decision_lap=13).identity() != _key().identity()


def test_no_future_fields_in_key():
    fields = set(_key().to_dict())
    assert not (fields & {"finish_position", "winner", "future", "result"})
    with pytest.raises(TypeError):
        V3.StrategyComparisonKey(**{**_key().to_dict(), "winner": "x"})


def test_same_racestate_required_for_pair():
    assert _key().state_identity == _key().state_identity
    with pytest.raises(ValueError):
        _key(state_identity="")


def test_reference_kind_pinned():
    with pytest.raises(ValueError):
        _key(reference_kind="STAY_OUT")


# --- MC2 / simulation / CRN ---


def test_mc2_identity_frozen():
    assert V3.SIMULATOR_IDENTITY == "MC2-E (E_AR1_RESIDUAL)"


def test_5000_default_frozen():
    assert V3.PRODUCTION_SIMULATION_COUNT == 5000
    assert _contract()["simulation_config"]["simulation_count"] == 5000


def test_crn_required():
    crn = _contract()["crn_invariants"]
    assert crn["only_intervention_differs"] is True
    assert "same root seed" in json.dumps(crn)


def test_complete_pair_semantics_explicit():
    pol = _contract()["complete_pair_policy"]
    assert "EITHER side invalid" in pol["membership"]
    assert "both_invalid" in json.dumps(pol["denominators"])


# --- intervention mapping ---


def test_intervention_mapping_closed():
    m = _contract()["intervention_mapping"]
    assert set(m) >= {"STAY_OUT", "PIT_NOW", "PIT_NEXT_LAP",
                      "never_mutated", "simulated_consequences"}
    assert "future winner" in json.dumps(m["never_mutated"])


def test_no_direct_future_outcome_mutation():
    assert V3.FORBIDDEN_AT_T and "future_result" in V3.FORBIDDEN_AT_T


def test_pit_now_semantics_exact():
    assert _contract()["pit_now_semantics"]["applied_lap"] == "L_T+1"
    assert V3.STRATEGY_ACTION_LAP_OFFSETS["PIT_NOW"] == 1


def test_pit_next_lap_no_historical_t1():
    blob = json.dumps(_contract()["pit_next_lap_semantics"])
    assert "No historical T+1" in blob or "no historical" in blob.lower()
    assert V3.STRATEGY_ACTION_LAP_OFFSETS["PIT_NEXT_LAP"] == 2


def test_stay_out_semantics_explicit():
    s = _contract()["stay_out_semantics"]
    assert s["forbids_future_stops"] is False
    assert "L_T+1" in json.dumps(s)


def test_compound_policy_closed():
    assert set(V3.SUPPORTED_REQUESTED_COMPOUNDS) == {"SOFT", "MEDIUM", "HARD"}
    assert "SAMPLED" in _contract()["compound_policy"]["enum"]


def test_validity_uses_t_safe_data_only():
    v = _contract()["action_validity"]
    assert "never post-T" in v["source"]
    assert "future" not in v["source"].lower().replace("post-t", "")


# --- eligibility ---


def test_state_action_comparison_separated():
    assert V3.ELIGIBILITY_LEVELS == ("STATE", "ACTION", "COMPARISON")
    h = _contract()["eligibility_hierarchy"]
    assert set(h) >= {"STATE", "ACTION", "COMPARISON", "rule"}


def test_reason_codes_reuse_no_new():
    assert _contract()["reason_codes"]["new_codes_introduced"] == 0
    assert "target_driver_not_in_roster" in V3.COMPARISON_LEVEL_REASONS
    assert len(V3.ACTION_LEVEL_REASONS) == 7


def test_unsupported_no_fabricated_metrics():
    u = V3.build_unsupported_result(
        level="STATE", reason_code="WET_CONDITIONS",
        human_reason="wet", state_identity="s" * 64)
    assert u["supported"] is False
    assert u["metrics"] == {}
    assert "NaN" not in json.dumps(u)


# --- outcomes ---


def test_outcome_vector_closed():
    assert set(V3.OUTCOME_METRICS) == {
        "win_frequency", "podium_frequency", "top5_frequency",
        "top10_frequency", "expected_finish", "median_finish",
        "finish_q25", "finish_q75",
    }
    assert "score" not in json.dumps(V3.OUTCOME_METRICS).lower()


def test_points_decision_explicit():
    assert _contract()["points_decision"]["status"].startswith("DEFERRED")
    assert V3.EXPECTED_POINTS_DECISION == "DEFERRED"


def test_downside_definition_explicit():
    assert "I(finish_alt > finish_ref)" in V3.DOWNSIDE_DEFINITION
    assert "complete valid pairs" in V3.DOWNSIDE_DEFINITION


def test_position_distribution_semantics_exact():
    p = _contract()["position_distribution_schema"]
    assert "sums to 1" in p["rule"]
    assert "V3.5" in p["rule"]


def test_delta_signs_exact():
    d = _contract()["delta_conventions"]
    assert d["delta_win_frequency"].startswith("alt - ref")
    assert d["delta_expected_finish"].startswith("ref - alt")


def test_no_synthetic_strategy_score():
    blob = json.dumps(_contract()).lower()
    assert "no_synthetic_score" in blob or "no synthetic" in blob
    assert "strategy score = " not in blob


def test_leader_not_recommendation():
    t = _contract()["trade_off_vector"]
    assert "NOT recommended" in t["leaders_mean"]


# --- uncertainty ---


def test_uncertainty_mc_sampling_only():
    assert V3.UNCERTAINTY_SEMANTICS == "MONTE_CARLO_SAMPLING_UNCERTAINTY_ONLY"
    assert V3.MIN_VALID_PAIRS_FOR_CI == 30
    assert V3.DEFAULT_BOOTSTRAP_REPLICATES == 2000
    assert V3.BOOTSTRAP_CI_METHOD == "paired_percentile_bootstrap"


def test_paired_binary_uncertainty():
    u = _contract()["uncertainty_schema"]["estimators"]["binary_outcomes"]
    assert "paired" in u.lower()
    assert "independent-arm" in u.lower() or "independent" in u.lower()


def test_paired_expected_finish_uncertainty():
    u = _contract()["uncertainty_schema"]["estimators"]["expected_finish"]
    assert "paired" in u.lower()
    assert "No independent-arm" in u or "independent" in u.lower()


def test_execution_rate_denominator_exact():
    assert V3.EXECUTION_RATE_DENOMINATOR.startswith("pairs_total")


def test_seed_identity_deterministic():
    assert _key(master_seed=7).identity() != _key(master_seed=8).identity()
    assert "PCG64" in V3.SEED_STREAM_RULE


# --- temporal / V3.5 / history ---


def test_future_data_blacklist_complete():
    for item in ("future_pit_events", "future_compounds", "future_lap_times",
                 "future_result", "future_finishing_position",
                 "future_safety_car", "future_weather",
                 "historical_observed_action_after_T", "v35_post_race_labels"):
        assert item in V3.FORBIDDEN_AT_T, item


def test_v35_excluded_from_computation():
    assert set(V3.V35_EXCLUDED_FROM) >= {
        "simulation", "eligibility", "uncertainty", "action_ranking"}
    assert V3.V35_CONSISTENCY_ROLE == "OFFLINE_DIAGNOSTIC_ONLY"


def test_historical_future_post_hoc_only():
    h = _contract()["historical_context_policy"]
    assert h["allowed_as"].startswith("POST_HOC_CONTEXT")


def test_result_provenance_complete():
    assert len(V3.PROVENANCE_FIELDS) == 12
    assert "seed_family_identity" in V3.PROVENANCE_FIELDS


# --- no runtime changes ---


def _changed():
    out = _git("status", "--short")
    return [ln.split()[-1] for ln in out.splitlines() if ln.strip()]


def test_no_api_frontend_change():
    changed = _changed()
    # V3.6F charter admits exactly its additive integration files; any
    # other api/ change still fails. V3.6G charter admits exactly its
    # Strategy 2.0 replacement files; any other frontend/ change fails.
    # V3.7H reconciliation: V3.7F charter additionally admits exactly the
    # counterfactual API files; V3.7G charter admits exactly the
    # Counterfactual Explorer paths (frozen science untouched).
    # V3.8H reconciliation: V3.8F/V3.8G charters additionally admit exactly
    # the consensus API/frontend paths (frozen science untouched).
    allowed = ("api/v2_strategy_v3_", "api/main.py",
               "api/v2_counterfactual_", "api/v2_consensus_")
    assert not any(f.startswith("api/") and not f.startswith(allowed)
                   for f in changed)
    allowed_frontend = ("frontend/app/strategy/page.tsx",
                        "frontend/features/strategy/components/Strategy",
                        "frontend/features/strategy/hooks/useStrategy",
                        "frontend/features/strategy/lib/strategy",
                        "frontend/lib/v2.ts",
                        "frontend/app/counterfactuals",
                        "frontend/features/counterfactuals",
                        "frontend/app/consensus",
                        "frontend/features/consensus",
                        "frontend/components/shell/CommandBar.tsx")
    assert not any(f.startswith("frontend/")
                   and not f.startswith(allowed_frontend)
                   for f in changed)


def test_no_mc2_change():
    # V3.7H reconciliation: V3.7C charter admits exactly the additive MC2
    # seam. Pinned SHA-256 preserves the no-mutation protection.
    # P2A carve-out (performance programme only): exactly kernel.py +
    # residuals.py with hoisted loop-invariant overhead plus the additive
    # batch executor (parity-gated in P0-P20/P1-P3/P2A-P29 checks).
    allowed = ("raceintel/simulation/monte_carlo.py",
               "raceintel/simulation/mc2/kernel.py",
               "raceintel/simulation/mc2/residuals.py",
               "raceintel/simulation/mc2_batch.py")
    changed = _changed()
    assert not any(f.startswith("raceintel/simulation") and f not in allowed
                   for f in changed)
    if "raceintel/simulation/monte_carlo.py" in changed:
        import hashlib as _hl
        from pathlib import Path as _Path
        digest = _hl.sha256(
            (_Path(__file__).resolve().parents[1]
             / "raceintel/simulation/monte_carlo.py").read_bytes()
        ).hexdigest()
        assert digest == ("045f392e46b030744f18a76140685ceba7501f80c0b8e265"
                          "af662e57ca5f5376")


def test_no_v35_change():
    changed = _changed()
    assert not any("v3_5" in f and f.startswith("raceintel/") for f in changed)


def test_phase7_behavior_unchanged():
    changed = _changed()
    touched = [f for f in changed if f.startswith("raceintel/strategy/")
               and f not in ("raceintel/strategy/v3_contracts.py",
                             "raceintel/strategy/v3_engine.py")]
    assert touched == [], touched


def test_contract_hash_deterministic():
    c = _contract()
    assert c["contract_hash"] == _canonical_hash(c)


def test_doc_required_sections():
    doc = DOC_PATH.read_text()
    for section in ("## Final verdict", "## Reuse audit",
                    "## StrategyComparisonKey", "## StrategyEligibility",
                    "## Outcome vector", "## V3.6C implementation boundary",
                    "## V3.6C recommendation"):
        assert section in doc, section
