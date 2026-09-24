"""Phase-7 S1: StrategyIntervention contract tests (no mechanics)."""

from __future__ import annotations

import dataclasses

import pytest

from v2.strategy import (
    INTERVENTION_VERSION,
    STRATEGY_CONTRACT_VERSION,
    SUPPORTED_REQUESTED_COMPOUNDS,
    StrategyAction,
    StrategyContractError,
    StrategyIntervention,
    StrategyInterventionNotImplemented,
    strategy_action_value,
)
from v2.simulation import monte_carlo as mc
from v2.simulation.state import Provenance, canonical_sha256


def _intervention(**overrides) -> StrategyIntervention:
    payload = {
        "target_driver_id": "driver_a",
        "action": StrategyAction.PIT_NOW,
        "requested_compound": None,
        "decision_lap": 3,
        "decision_state_identity": "state-identity-abc",
    }
    payload.update(overrides)
    return StrategyIntervention(**payload)


# ---------------------------------------------------------------------------
# Versions and vocabulary.
# ---------------------------------------------------------------------------

def test_versions_are_explicit():
    assert STRATEGY_CONTRACT_VERSION == "s1"
    assert INTERVENTION_VERSION == "v1"


def test_action_enum_is_exactly_three_actions():
    assert [action.value for action in StrategyAction] == \
        ["STAY_OUT", "PIT_NOW", "PIT_NEXT_LAP"]


def test_action_coercion_accepts_enum_and_exact_string_only():
    assert strategy_action_value("PIT_NOW") is StrategyAction.PIT_NOW
    assert strategy_action_value(StrategyAction.STAY_OUT) is \
        StrategyAction.STAY_OUT
    for bad in ("pit_now", "PIT", "", None, 3):
        with pytest.raises(StrategyContractError):
            strategy_action_value(bad)


def test_supported_compounds_are_the_v1_dry_triple():
    assert SUPPORTED_REQUESTED_COMPOUNDS == ("SOFT", "MEDIUM", "HARD")


# ---------------------------------------------------------------------------
# Immutability and identity.
# ---------------------------------------------------------------------------

def test_intervention_is_immutable():
    intervention = _intervention()
    with pytest.raises(dataclasses.FrozenInstanceError):
        intervention.requested_compound = "SOFT"
    with pytest.raises(dataclasses.FrozenInstanceError):
        intervention.target_driver_id = "driver_b"


def test_identical_fields_have_identical_identity():
    assert _intervention().identity() == _intervention().identity()


def test_identity_changes_with_any_field():
    base = _intervention().identity()
    variants = (
        _intervention(action=StrategyAction.STAY_OUT),
        _intervention(target_driver_id="driver_b"),
        _intervention(requested_compound="SOFT"),
        _intervention(decision_lap=4),
        _intervention(decision_state_identity="state-identity-xyz"),
    )
    assert all(variant.identity() != base for variant in variants)


def test_identity_is_key_order_invariant():
    payload = _intervention().to_dict()
    reordered = {key: payload[key] for key in reversed(list(payload))}
    assert canonical_sha256(payload) == canonical_sha256(reordered)
    assert _intervention().identity() == canonical_sha256(reordered)


def test_serialization_roundtrip_is_lossless():
    intervention = _intervention(action=StrategyAction.PIT_NEXT_LAP,
                                 requested_compound="MEDIUM")
    rebuilt = StrategyIntervention.from_dict(intervention.to_dict())
    assert rebuilt == intervention
    assert rebuilt.identity() == intervention.identity()


def test_from_dict_copies_and_cannot_be_mutated_afterwards():
    payload = _intervention().to_dict()
    intervention = StrategyIntervention.from_dict(payload)
    snapshot = intervention.to_dict()
    payload["target_driver_id"] = "poisoned"
    payload["decision_lap"] = 999
    assert intervention.to_dict() == snapshot


def test_from_dict_rejects_missing_keys_and_non_mapping():
    with pytest.raises(StrategyContractError):
        StrategyIntervention.from_dict({"target_driver_id": "a"})
    for bad in ("not-a-mapping", None, 3):
        with pytest.raises(StrategyContractError):
            StrategyIntervention.from_dict(bad)


# ---------------------------------------------------------------------------
# Provenance is pinned to USER_ASSUMPTION.
# ---------------------------------------------------------------------------

def test_default_provenance_is_user_assumption():
    assert _intervention().provenance is Provenance.USER_ASSUMPTION


@pytest.mark.parametrize("bad", [
    Provenance.FACTUAL_AT_T,
    Provenance.HISTORICALLY_ESTIMATED,
    Provenance.STOCHASTIC_DRAW,
    Provenance.ORACLE_EVALUATION_ONLY,
    "FACTUAL_AT_T",
    "factual_at_t",
    "USER_ASSUMPTION ",
])
def test_mislabelled_provenance_is_refused(bad):
    with pytest.raises(StrategyContractError):
        _intervention(provenance=bad)


# ---------------------------------------------------------------------------
# Action / compound validation.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("action", [StrategyAction.STAY_OUT, "STAY_OUT"])
def test_stay_out_rejects_a_requested_compound(action):
    with pytest.raises(StrategyContractError):
        _intervention(action=action, requested_compound="SOFT")


@pytest.mark.parametrize("action", [
    StrategyAction.PIT_NOW, StrategyAction.PIT_NEXT_LAP,
    "PIT_NOW", "PIT_NEXT_LAP"])
def test_pit_actions_accept_null_compound(action):
    assert _intervention(action=action, requested_compound=None) \
        .requested_compound is None


@pytest.mark.parametrize("compound", ["SOFT", "MEDIUM", "HARD"])
@pytest.mark.parametrize("action", [StrategyAction.PIT_NOW,
                                    StrategyAction.PIT_NEXT_LAP])
def test_pit_actions_accept_v1_dry_compounds(action, compound):
    assert _intervention(action=action, requested_compound=compound) \
        .requested_compound == compound


@pytest.mark.parametrize("compound", [
    "SUPERSOFT", "ULTRASOFT", "INTERMEDIATE", "WET", "soft", "", "BANANA"])
def test_unknown_or_out_of_scope_compounds_are_refused(compound):
    with pytest.raises(StrategyContractError):
        _intervention(action=StrategyAction.PIT_NOW,
                      requested_compound=compound)


def test_stay_out_accepts_null_compound():
    intervention = _intervention(action=StrategyAction.STAY_OUT,
                                 requested_compound=None)
    assert intervention.requested_compound is None


# ---------------------------------------------------------------------------
# Version and structural validation.
# ---------------------------------------------------------------------------

def test_wrong_contract_version_is_refused():
    with pytest.raises(StrategyContractError):
        _intervention(strategy_contract_version="s2")


def test_wrong_intervention_version_is_refused():
    with pytest.raises(StrategyContractError):
        _intervention(intervention_version="v2")


@pytest.mark.parametrize("bad", ["", "   ", None, 7])
def test_malformed_target_driver_is_refused(bad):
    with pytest.raises(StrategyContractError):
        _intervention(target_driver_id=bad)


@pytest.mark.parametrize("bad", ["", None, 7])
def test_malformed_state_identity_is_refused(bad):
    with pytest.raises(StrategyContractError):
        _intervention(decision_state_identity=bad)


@pytest.mark.parametrize("bad", [-1, 1.5, True, "3", None])
def test_invalid_decision_lap_is_refused(bad):
    with pytest.raises(StrategyContractError):
        _intervention(decision_lap=bad)


def test_unknown_action_is_refused():
    with pytest.raises(StrategyContractError):
        _intervention(action="PIT_SOMETIME")


# ---------------------------------------------------------------------------
# Dependency / layering.
# ---------------------------------------------------------------------------

def test_seam_error_is_re_exported_from_the_strategy_package():
    assert StrategyInterventionNotImplemented is \
        mc.StrategyInterventionNotImplemented
    assert issubclass(StrategyInterventionNotImplemented, ValueError)


def test_intervention_holds_no_simulation_state_or_parameters():
    fields = {field.name for field in dataclasses.fields(StrategyIntervention)}
    assert "state" not in fields
    assert "parameters" not in fields
    assert "config" not in fields
