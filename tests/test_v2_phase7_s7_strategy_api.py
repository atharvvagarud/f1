"""Phase-7 S7 strategy product API tests.

Covers ``POST /v2/strategies/compare``: request validation, exact-state
authority, served-season firewall, unsupported-state projection, determinism,
subset consistency, objective semantics, compact-response bounds (no
per-index leakage), and that the existing simulation API is unchanged. The
S1–S6 scientific layer is exercised, never modified.
"""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.v2_service import load_v2_service
from api.v2_strategy_schemas import V2StrategyCompareRequest
from api.v2_strategy_service import (
    DEFAULT_MASTER_SEED,
    DEFAULT_SIMULATION_COUNT,
    DEFAULT_STRATEGY_CANDIDATES,
    MAX_CANDIDATES_AT_10K,
    MAX_SYNCHRONOUS_SIMULATIONS,
    MIN_SIMULATION_COUNT,
    V2StrategyService,
    build_v2_strategy_service,
    get_v2_strategy_service,
    validate_strategy_request,
)
from v2.strategy.objectives import STRATEGY_OBJECTIVES

ORDINARY = dict(race_id="2022-r01-R", anchor_driver_id="perez",
                anchor_lap_number=30, anchor_state_time_s=6745.686)
WET = dict(race_id="2018-r11-R", anchor_driver_id="alonso",
           anchor_lap_number=44, anchor_state_time_s=4004.408)

FORBIDDEN_KEYS = ("intervention_outcomes", "baseline_outcomes", "per_index",
                  "PerIndexOutcome", "finishing_order", "winner_driver_id")
FORBIDDEN_WORDS = ("best strategy", "optimal strategy",
                   "recommended strategy", "would have won",
                   "would finish", "guaranteed")


@pytest.fixture(scope="module")
def v2_service():
    return load_v2_service()


@pytest.fixture(scope="module")
def strategy_service(v2_service):
    return build_v2_strategy_service(v2_service)


@pytest.fixture(scope="module")
def client(strategy_service):
    from api.main import app
    app.dependency_overrides[get_v2_strategy_service] = (
        lambda: strategy_service)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_v2_strategy_service, None)


def _body(**overrides):
    body = dict(ORDINARY)
    body.update(
        target_driver_id="perez",
        objective="MAXIMIZE_WIN_PROBABILITY",
        simulation_count=100,
        candidates=[{"action": "STAY_OUT"}],
    )
    body.update(overrides)
    return body


def _post(client, **overrides):
    return client.post("/v2/strategies/compare", json=_body(**overrides))


def _assert_no_per_index_leak(payload: dict) -> None:
    text = json.dumps(payload)
    for key in FORBIDDEN_KEYS:
        assert key not in text, f"per-index leak: {key}"


# ===========================================================================
# Request limits / validation (no execution).
# ===========================================================================

def test_request_bounds_constants():
    assert MIN_SIMULATION_COUNT == 100
    assert DEFAULT_SIMULATION_COUNT == 1000
    assert MAX_SYNCHRONOUS_SIMULATIONS == 10000
    assert len(DEFAULT_STRATEGY_CANDIDATES) <= 4


def test_default_candidate_set_is_neutral():
    assert ("STAY_OUT", None) in DEFAULT_STRATEGY_CANDIDATES
    assert ("PIT_NOW", None) in DEFAULT_STRATEGY_CANDIDATES
    assert ("PIT_NEXT_LAP", None) in DEFAULT_STRATEGY_CANDIDATES


def test_service_initializes_with_shared_authority(strategy_service):
    assert isinstance(strategy_service, V2StrategyService)
    assert len(strategy_service.race_ids) == 149
    assert strategy_service.parameters.through_season == 2024


def test_duplicate_candidates_rejected():
    with pytest.raises(Exception) as excinfo:
        validate_strategy_request(
            simulation_count=1000,
            candidate_specs=[("PIT_NOW", None), ("PIT_NOW", None)],
            objective="MAXIMIZE_WIN_PROBABILITY", master_seed=None)
    assert getattr(excinfo.value, "reason", "") == "duplicate_candidates"


def test_10k_candidate_cap():
    with pytest.raises(Exception) as excinfo:
        validate_strategy_request(
            simulation_count=10000,
            candidate_specs=[("STAY_OUT", None), ("PIT_NOW", None),
                             ("PIT_NOW", "SOFT"), ("PIT_NOW", "MEDIUM")],
            objective="MAXIMIZE_WIN_PROBABILITY", master_seed=None)
    assert getattr(excinfo.value, "reason", "") == "candidate_count_limit"
    validate_strategy_request(
        simulation_count=10000,
        candidate_specs=[("STAY_OUT", None), ("PIT_NOW", None),
                         ("PIT_NEXT_LAP", None)][:MAX_CANDIDATES_AT_10K],
        objective="MAXIMIZE_WIN_PROBABILITY", master_seed=None)


def test_unknown_objective_rejected():
    with pytest.raises(Exception):
        validate_strategy_request(
            simulation_count=100, candidate_specs=[("STAY_OUT", None)],
            objective="MAXIMIZE_EXPECTED", master_seed=None)


def test_count_below_min_rejected_by_schema():
    with pytest.raises(Exception):
        V2StrategyCompareRequest(**_body(simulation_count=99))


def test_malformed_action_rejected_by_schema():
    with pytest.raises(Exception):
        V2StrategyCompareRequest(
            **_body(candidates=[{"action": "TELEPORT"}]))


def test_malformed_compound_rejected_by_schema():
    with pytest.raises(Exception):
        V2StrategyCompareRequest(
            **_body(candidates=[{"action": "PIT_NOW",
                                 "requested_compound": "PLASMA"}]))


def test_duplicate_candidates_rejected_at_route(client):
    response = _post(
        client, candidates=[{"action": "STAY_OUT"},
                            {"action": "STAY_OUT"}])
    assert response.status_code == 422
    assert response.json()["reason"] == "duplicate_candidates"


def test_10k_cap_rejected_at_route(client):
    response = _post(
        client, simulation_count=10000,
        candidates=[{"action": "STAY_OUT"}, {"action": "PIT_NOW"},
                    {"action": "PIT_NOW", "requested_compound": "SOFT"},
                    {"action": "PIT_NOW", "requested_compound": "MEDIUM"}])
    assert response.status_code == 422
    assert response.json()["reason"] == "candidate_count_limit"


def test_unknown_objective_rejected_at_route(client):
    body = _body()
    body["objective"] = "MAXIMIZE_EXPECTED"
    response = client.post("/v2/strategies/compare", json=body)
    assert response.status_code == 422


def test_served_season_firewall(client):
    body = _body(race_id="2025-r01-R")
    response = client.post("/v2/strategies/compare", json=body)
    assert response.status_code == 404
    assert response.json()["error"] == "unknown_race"


def test_anchor_miss_is_422(client):
    body = _body(anchor_state_time_s=ORDINARY["anchor_state_time_s"] + 0.5)
    response = client.post("/v2/strategies/compare", json=body)
    assert response.status_code == 422
    assert response.json()["error"] == "unknown_state"


# ===========================================================================
# Live comparison (small counts; real backend).
# ===========================================================================

def test_valid_request_returns_compact_response(client):
    response = _post(client)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["supported"] is True
    assert payload["race_id"] == ORDINARY["race_id"]
    assert payload["target_driver_id"] == "perez"
    assert payload["simulation_count"] == 100
    assert payload["master_seed"] == DEFAULT_MASTER_SEED
    assert payload["objective"] == "MAXIMIZE_WIN_PROBABILITY"
    assert payload["probability_semantics"] == "MONTE_CARLO_FREQUENCY"
    assert payload["baseline"]["valid_simulations"] > 0
    assert len(payload["candidates"]) == 1
    candidate = payload["candidates"][0]
    assert candidate["evaluated"] is True
    assert candidate["uncertainty"]["classification"] in (
        "IMPROVEMENT", "DEGRADATION", "INCONCLUSIVE",
        "UNCERTAINTY_UNAVAILABLE")
    assert candidate["execution"]["applied_rate"] >= 0.0
    assert payload["objective_analysis"]["leader_by_point_estimate"] \
        == candidate["candidate_key"]
    _assert_no_per_index_leak(payload)


def test_default_candidates_when_omitted(client):
    body = _body()
    del body["candidates"]
    response = client.post("/v2/strategies/compare", json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["candidates"]) == len(DEFAULT_STRATEGY_CANDIDATES)


def test_master_seed_recorded_and_defaulted(client):
    response = _post(client)
    assert response.json()["master_seed"] == DEFAULT_MASTER_SEED
    response = _post(client, master_seed=7)
    assert response.json()["master_seed"] == 7


def test_unknown_target_is_structured_unsupported(client):
    response = _post(client, target_driver_id="not_a_driver")
    assert response.status_code == 200
    payload = response.json()
    assert payload["supported"] is False
    assert payload["unsupported_reason"] == "target_driver_not_in_roster"
    assert payload["baseline"] is None
    assert all(c["evaluated"] is False for c in payload["candidates"])


def test_unsupported_state_is_structured(client):
    response = client.post(
        "/v2/strategies/compare",
        json=dict(WET, target_driver_id="alonso",
                  objective="MAXIMIZE_WIN_PROBABILITY",
                  simulation_count=100,
                  candidates=[{"action": "STAY_OUT"}]))
    assert response.status_code == 200
    payload = response.json()
    assert payload["supported"] is False
    assert payload["unsupported_reason"] in (
        "wet_track_conditions", "wet_compound_state",
        "neutralized_track_state", "red_flag_track_state",
        "unknown_track_state", "missing_tyre_age",
        "non_contemporaneous_roster_member")
    assert payload["baseline"] is None
    assert all(c["evaluated"] is False for c in payload["candidates"])


def test_determinism_same_request_same_identity(client):
    first = _post(client, master_seed=7).json()
    second = _post(client, master_seed=7).json()
    assert (first["comparison_identity"]
            == second["comparison_identity"])
    assert (first["candidates"][0]["delta_win_probability"]
            == second["candidates"][0]["delta_win_probability"])


def test_seed_changes_result_identity(client):
    base = _post(client, master_seed=7).json()
    other = _post(client, master_seed=8).json()
    assert (base["comparison_identity"]
            != other["comparison_identity"])


def test_candidate_subset_consistency(client):
    solo = _post(client,
                 candidates=[{"action": "PIT_NOW"}]).json()["candidates"][0]
    pair = _post(client, candidates=[{"action": "PIT_NOW"},
                                     {"action": "STAY_OUT"}]).json()
    twin = [c for c in pair["candidates"]
            if c["candidate_key"] == solo["candidate_key"]][0]
    assert (twin["delta_win_probability"]
            == solo["delta_win_probability"])
    assert (twin["delta_expected_finish"]
            == solo["delta_expected_finish"])


def test_objective_changes_analysis_not_simulation(client):
    win = _post(client, objective="MAXIMIZE_WIN_PROBABILITY").json()
    finish = _post(client, objective="MINIMIZE_EXPECTED_FINISH").json()
    assert win["comparison_identity"] == finish["comparison_identity"]
    assert (win["candidates"][0]["delta_win_probability"]
            == finish["candidates"][0]["delta_win_probability"])
    assert win["objective_analysis"]["metric"] != \
        finish["objective_analysis"]["metric"]
    assert set(STRATEGY_OBJECTIVES) == {
        "MAXIMIZE_WIN_PROBABILITY", "MAXIMIZE_PODIUM_PROBABILITY",
        "MINIMIZE_EXPECTED_FINISH"}


def test_response_carries_no_recommendation_language(client):
    payload = _post(client).json()
    text = json.dumps(payload).lower()
    for word in FORBIDDEN_WORDS:
        assert word not in text, f"recommendation language: {word}"
    assert payload["counterfactual_semantics"]


def test_existing_simulation_api_unchanged(client):
    response = client.get("/v2/races")
    assert response.status_code == 200
    assert response.json()["count"] == 149
