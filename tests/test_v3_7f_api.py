"""V3.7F API/runtime/cache integration tests (real states).

Uses the V3.6F-validated dry-green anchor (2022-r01-R / perez / lap 30)
at the frozen production configuration (5000 futures, seed 20240101).
Covers: availability contract, compare validation, production locking,
cache-first/live policy, direct/live/cache parity (7 families),
N=1/N=2 V3.6 overlap, unsupported/2025/error semantics, temporal
safety, D artifact boundary, and Phase-7/V3.6 compatibility.
"""

from __future__ import annotations

import ast
import json
import sys
import time
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.v2_counterfactual_service import (
    build_counterfactual_service,
    get_counterfactual_service,
)
from api.v2_service import load_v2_service
from raceintel.counterfactual import contracts as C
from raceintel.counterfactual import engine as E
from raceintel.counterfactual import runtime as R
from raceintel.simulation import Assumptions, SimulationConfig
from raceintel.simulation.adapter import from_race_state

ROOT = Path(__file__).resolve().parents[1]

ANCHOR = dict(race_id="2022-r01-R", anchor_driver_id="perez",
              anchor_lap_number=30, anchor_state_time_s=6745.686)
TARGET = "perez"
RIVAL = "max_verstappen"


def _plan_body(targets, specs):
    return {
        "target_driver_ids": list(targets),
        "interventions": [
            {"target_driver_id": t, "kind": "PIT_IN_N_LAPS",
             "lap_offset_n": n, "requested_compound": c}
            for (t, n, c) in specs],
    }


def _body(**overrides):
    body = dict(ANCHOR)
    body.update(comparison_form="REFERENCE_VS_PLAN",
                alternative_plan=_plan_body([TARGET],
                                            [(TARGET, 2, "MEDIUM")]))
    body.update(overrides)
    return body


@pytest.fixture(scope="module")
def v2_service():
    return load_v2_service()


@pytest.fixture(scope="module")
def live_service(v2_service, tmp_path_factory):
    return build_counterfactual_service(
        v2_service,
        cache_dir=tmp_path_factory.mktemp("v3_7cf_cache"),
        allow_live=True)


@pytest.fixture(scope="function")
def client(live_service):
    from api.main import app
    app.dependency_overrides[get_counterfactual_service] = (
        lambda: live_service)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_counterfactual_service, None)


@pytest.fixture(scope="function")
def dead_service_client(v2_service, tmp_path_factory):
    """Cache-only service over an empty dir (live disabled)."""
    service = build_counterfactual_service(
        v2_service,
        cache_dir=tmp_path_factory.mktemp("v3_7cf_empty"),
        allow_live=False)
    assert service.allow_live is False
    from api.main import app
    app.dependency_overrides[get_counterfactual_service] = (
        lambda: service)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_counterfactual_service, None)


# ===========================================================================
# Availability.
# ===========================================================================

def test_availability_supported_and_factual(client):
    response = client.get("/v2/counterfactuals/availability", params=ANCHOR)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["supported"] is True
    assert payload["api_schema"] == "v3.7f-counterfactual-api-v1"
    assert payload["race_id"] == "2022-r01-R"
    assert payload["season"] == 2022
    by_id = {d["driver_id"]: d for d in payload["drivers"]}
    assert by_id["perez"]["decision_lap"] == 30
    assert by_id["perez"]["remaining_laps"] == 27
    assert by_id["perez"]["eligible_n_min"] == 1
    assert by_id["perez"]["eligible_n_max"] == 26
    assert TARGET in payload["eligible_targets"]
    assert payload["supported_compounds"] == ["SOFT", "MEDIUM", "HARD",
                                              "SAMPLED"]
    assert payload["comparison_forms"] == ["REFERENCE_VS_PLAN",
                                           "PLAN_VS_PLAN"]
    assert payload["multi_stop_capable"] is True
    assert payload["multi_driver_capable"] is True
    assert RIVAL in payload["rival_candidates"]
    assert payload["provenance"]["v37a_contract_identity"] == \
        R.A_CONTRACT_IDENTITY
    assert payload["provenance"]["v37b_contract_identity"] == \
        R.B_CONTRACT_IDENTITY
    assert payload["provenance"]["v37c_engine_identity"] == \
        "v3.7c-counterfactual-engine-v1"
    blob = json.dumps(payload, sort_keys=True)
    for token in ("future", "result", "winner"):
        assert token not in blob


def test_availability_deterministic_and_cheap(client):
    t0 = time.perf_counter()
    first = client.get("/v2/counterfactuals/availability",
                       params=ANCHOR).json()
    mid = time.perf_counter()
    second = client.get("/v2/counterfactuals/availability",
                        params=ANCHOR).json()
    assert first == second
    assert mid - t0 < 10


def test_availability_unknown_race_and_2025(client):
    for race in ("9999-r99-R", "2025-r01-R"):
        response = client.get("/v2/counterfactuals/availability",
                              params={**ANCHOR, "race_id": race})
        assert response.status_code == 404, response.text
        assert response.json()["error"] == "unknown_race"


def test_availability_bad_anchor(client):
    response = client.get("/v2/counterfactuals/availability",
                          params={**ANCHOR, "anchor_lap_number": 9999})
    assert response.status_code == 422, response.text


# ===========================================================================
# Request validation (malformed -> 422; unsupported -> 200 supported=false).
# ===========================================================================

def test_n_zero_rejected(client):
    body = _body()
    body["alternative_plan"]["interventions"][0]["lap_offset_n"] = 0
    assert client.post("/v2/counterfactuals/compare",
                       json=body).status_code == 422


def test_rejected_kind_rejected(client):
    body = _body()
    body["alternative_plan"]["interventions"][0]["kind"] = "WEATHER"
    assert client.post("/v2/counterfactuals/compare",
                       json=body).status_code == 422


def test_bad_compound_rejected(client):
    body = _body()
    body["alternative_plan"]["interventions"][0][
        "requested_compound"] = "WET"
    assert client.post("/v2/counterfactuals/compare",
                       json=body).status_code == 422


def test_production_override_fields_impossible(client):
    for poison in ({"master_seed": 1}, {"simulation_count": 100},
                   {"num_simulations": 100}, {"mode": "live"},
                   {"live": True}, {"seed": 1}, {"count": 10}):
        body = _body()
        body.update(poison)
        assert client.post("/v2/counterfactuals/compare",
                           json=body).status_code == 422, poison
    body = _body()
    body["alternative_plan"]["interventions"][0]["future_result"] = "win"
    assert client.post("/v2/counterfactuals/compare",
                       json=body).status_code == 422


def test_plan_form_mismatch_rejected(client):
    assert client.post("/v2/counterfactuals/compare",
                       json=_body(
                           comparison_form="PLAN_VS_PLAN")).status_code == 422
    body = _body(base_plan=_plan_body([TARGET], [(TARGET, 1, "MEDIUM")]))
    assert client.post("/v2/counterfactuals/compare",
                       json=body).status_code == 422


def test_unknown_and_conflicting_targets_rejected(client):
    body = _body()
    body["alternative_plan"]["target_driver_ids"] = ["nobody"]
    body["alternative_plan"]["interventions"][0]["target_driver_id"] = \
        "nobody"
    assert client.post("/v2/counterfactuals/compare",
                       json=body).status_code == 422
    body = _body()
    body["alternative_plan"]["target_driver_ids"] = [TARGET, TARGET]
    assert client.post("/v2/counterfactuals/compare",
                       json=body).status_code == 422


def test_horizon_violation_is_unsupported(client):
    body = _body()
    body["alternative_plan"]["interventions"][0]["lap_offset_n"] = 99
    response = client.post("/v2/counterfactuals/compare", json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["supported"] is False
    assert payload["reason_code"] == "INVALID_TRIGGER"
    assert payload["base_aggregate"] is None
    assert payload["deltas"] == {}


def test_rival_is_target_is_unsupported(client):
    response = client.post(
        "/v2/counterfactuals/compare",
        json=_body(rival_driver_id=TARGET))
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["supported"] is False
    assert payload["reason_code"] == "RIVAL_NOT_PRESENT"
    assert payload["deltas"] == {}


def test_plan_vs_plan_primary_mismatch_unsupported(client):
    body = _body(comparison_form="PLAN_VS_PLAN",
                 base_plan=_plan_body(["alonso"], [("alonso", 2,
                                                    "MEDIUM")]))
    response = client.post("/v2/counterfactuals/compare", json=body)
    assert response.status_code == 200, response.text
    assert response.json()["supported"] is False


# ===========================================================================
# Cache-first policy / live opt-in.
# ===========================================================================

def test_live_disabled_cache_miss_is_404(dead_service_client):
    response = dead_service_client.post("/v2/counterfactuals/compare",
                                        json=_body())
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "cache_miss"


def test_production_config_locked(client):
    from api.v2_counterfactual_schemas import CounterfactualCompareRequest
    assert "master_seed" not in CounterfactualCompareRequest.model_fields
    assert "simulation_count" not in CounterfactualCompareRequest.model_fields
    assert "mode" not in CounterfactualCompareRequest.model_fields


# ===========================================================================
# Live/cache/direct parity helpers.
# ===========================================================================

def _scientific(payload: dict) -> dict:
    return {k: payload[k] for k in (
        "supported", "comparison_form", "comparison_identity",
        "base_identity", "alternative_identity", "state_identity",
        "master_seed", "simulation_count", "primary_target_driver_id",
        "rival_driver_id", "base_aggregate", "alternative_aggregate",
        "deltas", "complete_pairs", "requested_pairs", "excluded_pairs",
        "lifecycle_summary")}


def _direct(v2_service, *, form, base_specs, alt_specs,
            targets, rival=None):
    race_state = v2_service.get_state(**ANCHOR)
    sim_state = from_race_state(race_state)
    params = build_counterfactual_service_param(v2_service)
    config = SimulationConfig(simulation_count=5000, master_seed=20240101,
                              pit_dynamics_enabled=True)

    def _mk(specs):
        return R.build_plan(
            sim_state, target_driver_ids=list(targets),
            interventions=[{"target_driver_id": t,
                            "kind": "PIT_IN_N_LAPS", "lap_offset_n": n,
                            "requested_compound": c}
                           for (t, n, c) in specs])
    alt = _mk(alt_specs)
    if form == "REFERENCE_VS_PLAN":
        res = E.compare_reference_vs_plan(
            state=sim_state, parameters=params, config=config,
            assumptions=Assumptions(), plan=alt, rival_driver_id=rival)
    else:
        res = E.compare_plan_vs_plan(
            state=sim_state, parameters=params, config=config,
            assumptions=Assumptions(), plan_a=_mk(base_specs), plan_b=alt,
            rival_driver_id=rival)
    d = res.to_dict() if hasattr(res, "to_dict") else dict(res)
    d["lifecycle_summary"] = R.summarize_lifecycle(
        d.get("schedule_outcomes"))
    # Mirror the service projection: identities live in provenance on
    # the raw engine dict, top-level on the API payload.
    d["state_identity"] = (d.get("provenance") or {}).get("state_identity")
    d["master_seed"] = (d.get("provenance") or {}).get("master_seed")
    d["simulation_count"] = (d.get("provenance") or {}).get(
        "simulation_count")
    d["primary_target_driver_id"] = d.get("target_driver_id")
    return d


def build_counterfactual_service_param(v2_service):
    from api.v2_counterfactual_service import load_production_parameters
    return load_production_parameters()


CASES = [
    ("reference-vs-N1", "REFERENCE_VS_PLAN", None,
     [(TARGET, 1, "MEDIUM")], [TARGET], None),
    ("reference-vs-N2", "REFERENCE_VS_PLAN", None,
     [(TARGET, 2, "MEDIUM")], [TARGET], None),
    ("reference-vs-N5", "REFERENCE_VS_PLAN", None,
     [(TARGET, 5, "MEDIUM")], [TARGET], None),
    ("multi-stop", "REFERENCE_VS_PLAN", None,
     [(TARGET, 2, "MEDIUM"), (TARGET, 8, "HARD")], [TARGET], None),
    ("plan-vs-plan", "PLAN_VS_PLAN", [(TARGET, 2, "MEDIUM")],
     [(TARGET, 5, "MEDIUM")], [TARGET], None),
    ("rival-outcome", "REFERENCE_VS_PLAN", None,
     [(TARGET, 2, "MEDIUM")], [TARGET], RIVAL),
    ("multi-driver", "REFERENCE_VS_PLAN", None,
     [(TARGET, 2, "MEDIUM"), (RIVAL, 2, "MEDIUM")],
     [TARGET, RIVAL], None),
]


@pytest.mark.parametrize(
    "name,form,base_specs,alt_specs,targets,rival",
    [pytest.param(*c, id=c[0]) for c in CASES])
def test_direct_live_cache_parity(client, v2_service, name, form,
                                  base_specs, alt_specs, targets, rival):
    body = _body(comparison_form=form,
                 alternative_plan=_plan_body(targets, alt_specs),
                 rival_driver_id=rival)
    if base_specs is not None:
        body["base_plan"] = _plan_body(targets, base_specs)
    live = client.post("/v2/counterfactuals/compare",
                       json=body).json()
    assert live["supported"] is True, live
    assert live["execution_source"] == "live_engine"
    assert live["simulation_count"] == 5000
    assert live["master_seed"] == 20240101
    cached = client.post("/v2/counterfactuals/compare",
                         json=body).json()
    assert cached["execution_source"] == "cache"
    assert _scientific(cached) == _scientific(live)
    direct = _direct(v2_service, form=form, base_specs=base_specs,
                     alt_specs=alt_specs, targets=sorted(targets),
                     rival=rival)
    for key in ("base_aggregate", "alternative_aggregate", "deltas",
                "complete_pairs", "requested_pairs", "excluded_pairs",
                "lifecycle_summary", "comparison_identity",
                "base_identity", "alternative_identity"):
        assert cached[key] == direct[key], key
    # Orientation spot checks on every parity case.
    deltas = cached["deltas"]
    assert (deltas["delta_expected_finish"]["point_estimate"]
            == pytest.approx(
                cached["base_aggregate"]["expected_finish"]
                - cached["alternative_aggregate"]["expected_finish"]))
    assert (deltas["delta_position_gain_loss"]["point_estimate"]
            == pytest.approx(
                cached["alternative_aggregate"]
                ["expected_position_gain"]
                - cached["base_aggregate"]["expected_position_gain"]))
    if rival is not None:
        assert cached["alternative_aggregate"]["p_ahead_of_rival"] \
            is not None


def test_n1_n2_overlap_with_v36(client, v2_service, tmp_path):
    from api.v2_strategy_v3_service import build_v3_strategy_service
    v3 = build_v3_strategy_service(v2_service, cache_dir=tmp_path,
                                   allow_live=True)
    by_action = {}
    for action in ("PIT_NOW", "PIT_NEXT_LAP"):
        payload = v3.run_comparison(
            race_id=ANCHOR["race_id"],
            anchor_driver_id=ANCHOR["anchor_driver_id"],
            anchor_lap_number=ANCHOR["anchor_lap_number"],
            anchor_state_time_s=ANCHOR["anchor_state_time_s"],
            target_driver_id=TARGET,
            alternatives=[{"action": action,
                           "requested_compound": None}],
            mode="live")
        alts = [a for a in payload["alternatives"] if a["evaluated"]]
        assert len(alts) == 1
        by_action[action] = alts[0]["alternative_aggregate"]
    for action, n in (("PIT_NOW", 1), ("PIT_NEXT_LAP", 2)):
        body = _body(alternative_plan=_plan_body(
            [TARGET], [(TARGET, n, "SAMPLED")]))
        payload = client.post("/v2/counterfactuals/compare",
                              json=body).json()
        assert payload["supported"] is True, payload
        alt = payload["alternative_aggregate"]
        ref = by_action[action]
        assert alt["expected_finish"] == pytest.approx(
            ref["expected_finish"])
        assert alt["win_frequency"] == pytest.approx(ref["win_frequency"])
        # (V3.6 carries no pit-count outcome; pit counts are covered by
        # the engine-level C parity and the F direct/live/cache parity.)


# ===========================================================================
# Corrupt cache, 2025, compatibility, boundaries.
# ===========================================================================

def test_corrupt_cache_fails_closed(v2_service, tmp_path):
    service = build_counterfactual_service(
        v2_service, cache_dir=tmp_path, allow_live=True)
    first = service.run_comparison(
        **{k: ANCHOR[k] for k in (
            "race_id", "anchor_driver_id", "anchor_lap_number",
            "anchor_state_time_s")},
        comparison_form="REFERENCE_VS_PLAN", base_plan=None,
        alternative_plan=_plan_body([TARGET], [(TARGET, 2, "MEDIUM")]),
        rival_driver_id=None)
    assert first["supported"] is True
    path = tmp_path / f"v3_7cf_{first['cache_key']}.json"
    path.write_bytes(b'{"cache_schema_version": "v3.7f-counterfactual-'
                     b'cache-v1", "broken": true}')
    cold = build_counterfactual_service(
        v2_service, cache_dir=tmp_path, allow_live=False)
    from raceintel.counterfactual.runtime import CacheInvalidError
    with pytest.raises(CacheInvalidError):
        cold.run_comparison(
            **{k: ANCHOR[k] for k in (
                "race_id", "anchor_driver_id", "anchor_lap_number",
                "anchor_state_time_s")},
            comparison_form="REFERENCE_VS_PLAN", base_plan=None,
            alternative_plan=_plan_body([TARGET], [(TARGET, 2, "MEDIUM")]),
            rival_driver_id=None)
    # With live enabled the service falls through to a live run.
    hot = build_counterfactual_service(
        v2_service, cache_dir=tmp_path, allow_live=True)
    second = hot.run_comparison(
        **{k: ANCHOR[k] for k in (
            "race_id", "anchor_driver_id", "anchor_lap_number",
            "anchor_state_time_s")},
        comparison_form="REFERENCE_VS_PLAN", base_plan=None,
        alternative_plan=_plan_body([TARGET], [(TARGET, 2, "MEDIUM")]),
        rival_driver_id=None)
    assert second["supported"] is True
    assert second["execution_source"] == "live_engine"


def test_compare_2025_unsupported(client):
    response = client.post("/v2/counterfactuals/compare",
                           json=_body(race_id="2025-r01-R"))
    assert response.status_code == 404, response.text
    assert response.json()["error"] == "unknown_race"


def test_phase7_and_v36_routes_intact(client):
    from api.main import app
    paths = {r.path for r in app.routes if hasattr(r, "path")}
    assert "/v2/strategies/compare" in paths
    assert "/v2/strategies/compare-v3" in paths
    assert "/v2/strategies/v3/availability" in paths
    baseline = json.loads(
        (ROOT / "results/v3/v3_6f/phase7_compat_baseline.json").read_text())
    assert baseline["response_semantics"]["supported"] is True


def test_no_d_evaluation_imports_in_f_stack():
    for mod in ("api.v2_counterfactual_service",
                "api.v2_counterfactual_routes",
                "api.v2_counterfactual_schemas",
                "raceintel.counterfactual.runtime"):
        tree = ast.parse(Path(ROOT, *mod.split(".")).with_suffix(
            ".py").read_text())
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module)
        blob = "\n".join(sorted(imported))
        assert "v3_7d" not in blob, (mod, blob)
        assert "evaluation" not in blob, (mod, blob)
    assert "v3_7d" not in set(sys.modules)


def test_temporal_poison_blocked_end_to_end(client, monkeypatch):
    import pandas as pd
    monkeypatch.setattr(
        pd, "read_parquet",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("historical read attempted")))
    first = client.get("/v2/counterfactuals/availability",
                       params=ANCHOR).json()
    second = client.get("/v2/counterfactuals/availability",
                        params=ANCHOR).json()
    assert first == second
    assert first["supported"] is True
