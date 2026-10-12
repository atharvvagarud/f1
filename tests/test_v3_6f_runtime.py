"""V3.6F runtime/API integration tests (no cache design here).

Covers: A/B/C/D provenance + V3.6E absence, Phase-7 backwards
compatibility (frozen pre-change fixture), Strategy 2.0 request
validation, fixed-5000 production config, unsupported/2025/firewall
semantics, execution-source + provenance exposure, API language policy,
direct-engine vs API-live parity (one 5000-run fixture), V3.5/D
separation, and no-frontend-changes.
"""

from __future__ import annotations

import ast
import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.v2_service import load_v2_service
from api.v2_strategy_service import (
    DEFAULT_SIMULATION_COUNT as P7_DEFAULT_COUNT,
    MAX_SYNCHRONOUS_SIMULATIONS as P7_MAX_COUNT,
    MIN_SIMULATION_COUNT as P7_MIN_COUNT,
    build_v2_strategy_service,
    get_v2_strategy_service,
)
from api.v2_strategy_v3_service import (
    DEFAULT_MASTER_SEED,
    PRODUCTION_SIMULATION_COUNT,
    V3_ENGINE_VERSION,
    build_v3_strategy_service,
    get_v3_strategy_service,
)

ROOT = Path(__file__).resolve().parents[1]

ORDINARY = dict(race_id="2022-r01-R", anchor_driver_id="perez",
                anchor_lap_number=30, anchor_state_time_s=6745.686)
WET = dict(race_id="2018-r11-R", anchor_driver_id="alonso",
           anchor_lap_number=44, anchor_state_time_s=4004.408)

FORBIDDEN_WORDS = ("best", "optimal", "recommended", "should pit",
                   "correct strategy", "guaranteed", "would have won")


def _v3body(**overrides):
    body = dict(ORDINARY)
    body.update(target_driver_id="perez", mode="live",
                alternatives=[{"action": "STAY_OUT"}])
    body.update(overrides)
    return body


@pytest.fixture(scope="module")
def v2_service():
    return load_v2_service()


@pytest.fixture(scope="module")
def small_service(v2_service, tmp_path_factory):
    return build_v3_strategy_service(
        v2_service,
        cache_dir=tmp_path_factory.mktemp("v3cache"),
        simulation_count=200)


@pytest.fixture(scope="function")
def client(small_service):
    from api.main import app
    app.dependency_overrides[get_v3_strategy_service] = (
        lambda: small_service)
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_v3_strategy_service, None)


# ===========================================================================
# Provenance (A/B/C/D) + V3.6E absence.
# ===========================================================================

def test_a_identity_exact():
    d = json.loads(
        (ROOT / "results/v3/v3_6b_readiness.json").read_text())
    assert d["a_identity"]["contract_hash"] == (
        "2d29c19b47b24035f0d1c503fccc8cd4090595b4ebb2a980001d0a919b0ae59b")


def test_b_identity_exact():
    d = json.loads(
        (ROOT / "results/v3/v3_6b_readiness.json").read_text())
    assert d["contract_identity"]["contract_hash"] == (
        "df821fe13ed587d7a086e93b8ee53a1670130299ca92c5a668608add443e3644")


def test_c_engine_identity():
    assert V3_ENGINE_VERSION == "v3.6c-engine-v1"
    d = json.loads(
        (ROOT / "results/v3/v3_6c_paired_engine.json").read_text())
    assert d["engine_identity"].startswith("v3.6c-engine-v1")


def test_d_protocol_identity_and_verdict():
    d = json.loads((ROOT / "results/v3/v3_6d_historical_strategy_"
                           "evaluation.json").read_text())
    assert d["protocol_hash"] == (
        "0c2bf7fb6e46a948d811587a64aac89cb10cfe0bf67485ed9ff3b457d64088fc")
    assert d["refinement_decision"] == "REFINEMENT_NOT_WARRANTED"


def test_v3_6e_absent():
    assert not list(ROOT.glob("**/*v3_6e*"))
    assert not list(ROOT.glob("**/*V3_6E*"))


# ===========================================================================
# Phase-7 backwards compatibility (frozen pre-change fixture).
# ===========================================================================

def test_phase7_frozen_baseline_exists():
    baseline = json.loads(
        (ROOT / "results/v3/v3_6f/phase7_compat_baseline.json").read_text())
    assert baseline["response_semantics"]["supported"] is True
    assert baseline["response_semantics"][
        "strategy_contract_version"] == "s1"


def test_phase7_request_still_works(v2_service):
    from api.main import app
    service = build_v2_strategy_service(v2_service)
    app.dependency_overrides[get_v2_strategy_service] = lambda: service
    try:
        with TestClient(app) as test_client:
            body = dict(ORDINARY)
            body.update(
                target_driver_id="perez",
                objective="MAXIMIZE_WIN_PROBABILITY",
                simulation_count=100,
                candidates=[{"action": "STAY_OUT"}])
            response = test_client.post(
                "/v2/strategies/compare", json=body)
    finally:
        app.dependency_overrides.pop(get_v2_strategy_service, None)
    assert response.status_code == 200, response.text
    payload = response.json()
    baseline = json.loads(
        (ROOT / "results/v3/v3_6f/phase7_compat_baseline.json").read_text()
    )["response_semantics"]
    assert payload["supported"] is True
    assert payload["strategy_contract_version"] == baseline[
        "strategy_contract_version"]
    assert payload["comparison_version"] == baseline["comparison_version"]
    assert payload["metric"] == baseline["metric"]
    assert payload["probability_semantics"] == baseline[
        "probability_semantics"]
    assert payload["comparison_identity"] == baseline["comparison_identity"]
    assert payload["candidates"][0][
        "delta_win_probability"] == baseline["candidates"][0][
        "delta_win_probability"]
    # Phase-7 product bounds untouched.
    assert P7_MIN_COUNT == 100
    assert P7_DEFAULT_COUNT == 1000
    assert P7_MAX_COUNT == 10000


# ===========================================================================
# Strategy 2.0 request validation.
# ===========================================================================

def test_production_count_fixed_and_unexposed(client):
    from api.v2_strategy_v3_schemas import V3CompareRequest
    assert PRODUCTION_SIMULATION_COUNT == 5000
    assert "simulation_count" not in V3CompareRequest.model_fields
    with pytest.raises(Exception):
        V3CompareRequest(**_v3body(simulation_count=100))


def test_unknown_action_rejected(client):
    body = _v3body()
    body["alternatives"] = [{"action": "TELEPORT"}]
    assert client.post("/v2/strategies/compare-v3",
                       json=body).status_code == 422


def test_stay_out_with_compound_rejected(client):
    response = client.post(
        "/v2/strategies/compare-v3",
        json=_v3body(alternatives=[{"action": "STAY_OUT",
                                    "requested_compound": "SOFT"}]))
    assert response.status_code == 422
    assert response.json()["reason"] == "invalid_action"


def test_duplicate_alternatives_rejected(client):
    response = client.post(
        "/v2/strategies/compare-v3",
        json=_v3body(alternatives=[{"action": "STAY_OUT"},
                                   {"action": "STAY_OUT"}]))
    assert response.status_code == 422
    assert response.json()["reason"] == "duplicate_alternatives"


def test_empty_alternatives_rejected(client):
    response = client.post("/v2/strategies/compare-v3",
                           json=_v3body(alternatives=[]))
    assert response.status_code == 422


def test_unknown_mode_rejected(client):
    body = _v3body()
    body["mode"] = "turbo"
    assert client.post("/v2/strategies/compare-v3",
                       json=body).status_code == 422


def test_2025_firewall(v2_service):
    from api.main import app
    service = build_v3_strategy_service(
        v2_service, cache_dir=Path("/tmp/v3_6f_no_cache_here"),
        simulation_count=200)
    app.dependency_overrides[get_v3_strategy_service] = lambda: service
    try:
        with TestClient(app) as test_client:
            body = _v3body(race_id="2025-r01-R")
            response = test_client.post("/v2/strategies/compare-v3",
                                        json=body)
    finally:
        app.dependency_overrides.pop(get_v3_strategy_service, None)
    assert response.status_code == 404
    assert response.json()["error"] == "unknown_race"


def test_unsupported_state_explicit_no_zeros(client):
    body = dict(WET)
    body.update(target_driver_id="alonso", mode="live",
                alternatives=[{"action": "STAY_OUT"}])
    response = client.post("/v2/strategies/compare-v3", json=body)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["supported"] is False
    assert payload["unsupported_reason"]
    assert all(a["evaluated"] is False for a in payload["alternatives"])
    assert all(a["reference_aggregate"] is None
               for a in payload["alternatives"])
    assert all(a["alternative_aggregate"] is None
               for a in payload["alternatives"])
    assert all(a["deltas"] == [] for a in payload["alternatives"])


# ===========================================================================
# Live response contract: source, provenance, language.
# ===========================================================================

def test_live_response_contract(client):
    payload = client.post("/v2/strategies/compare-v3",
                          json=_v3body()).json()
    assert payload["execution_source"] == "live_engine"
    assert payload["simulation_count"] == 200  # small test service
    assert payload["master_seed"] == DEFAULT_MASTER_SEED
    assert payload["engine_version"] == "v3.6c-engine-v1"
    assert payload["reference_kind"] == "SIMULATED_NO_INTERVENTION_REFERENCE"
    assert payload["cache_key"] and len(payload["cache_key"]) == 64
    provenance = payload["provenance"]
    for key in ("contract_version", "racestate_identity", "mc2_identity",
                "simulation_config_identity", "reference_identity",
                "simulation_count", "complete_pair_count",
                "seed_family_identity", "outcome_schema_identity"):
        assert provenance[key] not in (None, ""), key
    assert provenance["mc2_identity"] == "MC2-E (E_AR1_RESIDUAL)"
    alt = payload["alternatives"][0]
    assert alt["comparison_identity"]
    assert alt["comparison_key"]["outcome_schema_version"] == (
        "v3.6b-outcome-vector-v1")
    assert alt["requested_pairs"] == 200
    assert alt["complete_pairs"] + alt["excluded_pairs"] == 200
    delta = alt["deltas"][0]
    assert delta["interval_label"] == "95% MC interval"
    assert delta["valid_pairs"] == alt["complete_pairs"]
    text = json.dumps(payload).lower()
    for word in FORBIDDEN_WORDS:
        assert word not in text, f"endorsement language: {word}"


# ===========================================================================
# Direct-engine vs API-live parity (one 5000-run fixture).
# ===========================================================================

def test_direct_engine_vs_api_live_parity_5000(v2_service, tmp_path):
    from raceintel.simulation import Assumptions, SimulationConfig
    from raceintel.simulation.adapter import from_race_state
    from api.v2_strategy_service import load_production_parameters
    from raceintel.race_state import race_state as RS
    from raceintel.strategy.v3_engine import compare_v3_strategies

    params = load_production_parameters()
    anchor = RS.AnchorObservation(
        race_id=ORDINARY["race_id"],
        anchor_driver_id=ORDINARY["anchor_driver_id"],
        anchor_lap_number=ORDINARY["anchor_lap_number"],
        anchor_state_time_s=ORDINARY["anchor_state_time_s"])
    race_state = v2_service._reconstructor.reconstruct(anchor)  # noqa: SLF001
    sim_state = from_race_state(race_state)
    config = SimulationConfig(
        simulation_count=5000, master_seed=DEFAULT_MASTER_SEED,
        pit_dynamics_enabled=True)
    direct = compare_v3_strategies(
        sim_state, params, config, Assumptions(), "perez",
        candidate_specs=[("STAY_OUT", None)])

    service = build_v3_strategy_service(
        v2_service, cache_dir=tmp_path, simulation_count=5000)
    from api.main import app
    app.dependency_overrides[get_v3_strategy_service] = lambda: service
    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                "/v2/strategies/compare-v3", json=_v3body(mode="live"))
    finally:
        app.dependency_overrides.pop(get_v3_strategy_service, None)
    assert response.status_code == 200, response.text
    live = response.json()
    assert live["simulation_count"] == 5000
    assert live["strategy_identity"] == direct.identity()
    direct_alts = {a.candidate_key: a.to_dict()
                   for a in direct.alternatives}
    for alt in live["alternatives"]:
        assert json.dumps(alt, sort_keys=True) == json.dumps(
            direct_alts[alt["candidate_key"]], sort_keys=True)
    assert live["leaders"] == direct.leaders


# ===========================================================================
# Separation guards.
# ===========================================================================

def _assert_no_banned_imports(path: Path):
    tree = ast.parse(path.read_text())
    imports = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imports.append(node.module or "")
    text = "\n".join(imports)
    assert "v3_5" not in text and "outcome" not in text.replace(
        "outcome_schema", ""), f"V3.5 import in {path}"
    assert "v3_6d" not in text, f"D-evaluation import in {path}"
    assert "historical_evaluation" not in text, f"D-data import in {path}"
    assert "case_studies" not in text, f"D-data import in {path}"
    assert "refinement_decision" not in text, f"D-data import in {path}"


def test_no_v3_5_or_d_runtime_dependency():
    for path in [ROOT / "api/v2_strategy_v3_service.py",
                 ROOT / "api/v2_strategy_v3_schemas.py",
                 ROOT / "api/v2_strategy_v3_routes.py",
                 ROOT / "scripts/v3_6f_build_strategy_cache.py"]:
        _assert_no_banned_imports(path)


def test_no_frontend_changes():
    out = subprocess.run(
        ["git", "status", "--porcelain"], capture_output=True, text=True,
        cwd=str(ROOT), check=True).stdout
    touched = [line[3:] for line in out.splitlines() if line.strip()]
    # V3.6G charter admits exactly its Strategy 2.0 replacement files;
    # any other frontend/ change still fails.
    # V3.7H reconciliation: V3.7G charter additionally admits exactly the
    # Counterfactual Explorer paths (backend/science untouched).
    # V3.8H reconciliation: V3.8G charter additionally admits exactly the
    # consensus frontend paths (backend/science untouched).
    allowed = ("frontend/app/strategy/page.tsx",
               "frontend/features/strategy/components/Strategy",
               "frontend/features/strategy/hooks/useStrategy",
               "frontend/features/strategy/lib/strategy",
               "frontend/lib/v2.ts",
               "frontend/app/counterfactuals",
               "frontend/features/counterfactuals",
               "frontend/app/consensus", "frontend/features/consensus",
               "frontend/components/shell/CommandBar.tsx")
    assert not [f for f in touched if f.startswith("frontend/")
                and not f.startswith(allowed)], touched
