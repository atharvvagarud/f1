"""Phase-6 R8 freeze seal: cross-layer frozen invariants.

Compact seal over the frozen Monte Carlo subsystem. It pins the scientific
runtime hashes (proving integration did not drift them), the contract
versions, the R3 production parameter identity, the R7 protocol and accepted
metrics, the R7.1 contemporaneity contract, the API contract, the served
range, the count policy, and the probability semantics. It does NOT re-run
the simulator.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

from v2.simulation import (
    CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES,
    ENGINE_UNSUPPORTED_REASONS,
    SIMULATION_CONTRACT_VERSION,
)
from v2.simulation.adapter import SimulationUnavailableError
from v2.simulation.engine import (
    ENGINE_VERSION,
    REASON_NON_CONTEMPORANEOUS_ROSTER_MEMBER,
)
from v2.simulation.monte_carlo import MONTE_CARLO_VERSION, PIT_DYNAMICS_VERSION
from v2.simulation.params import PARAMETER_CONTRACT_VERSION
from v2.simulation.results import PROBABILITY_SEMANTICS

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "PHASE6_FREEZE_MANIFEST.json"
API_CONTRACT = ROOT / "docs" / "PHASE6_SIMULATION_API_CONTRACT.json"
PHASE4_MANIFEST = ROOT / "docs" / "PHASE4_FREEZE_MANIFEST.json"
PHASE5_MANIFEST = ROOT / "docs" / "PHASE5_FREEZE_MANIFEST.json"
R7_PROTOCOL = (ROOT / "data" / "v2" / "simulation" / "validation"
               / "r7_protocol_v1.json")

PHASE6_ROUTE = "post /v2/simulations/race"
SIMULATION_FILES = (
    "state.py", "config.py", "adapter.py", "params.py", "engine.py",
    "monte_carlo.py", "rng.py", "results.py", "errors.py", "validation.py",
    "estimator.py", "__init__.py",
)


def _load(path: Path) -> dict:
    return json.loads(path.read_text())


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _manifest() -> dict:
    return _load(MANIFEST)


# ---------------------------------------------------------------------------
# Scientific runtime hash seal (R8-AC).
# ---------------------------------------------------------------------------

def test_manifest_exists_and_is_machine_readable():
    manifest = _manifest()
    assert manifest["phase"] == "phase-6"
    assert manifest["status"] == "FROZEN"
    assert manifest["scientific_runtime_unchanged_during_integration"] is True


def test_scientific_runtime_files_match_frozen_hashes():
    recorded = _manifest()["scientific_file_hashes"]
    assert set(recorded) == set(SIMULATION_FILES)
    for name in SIMULATION_FILES:
        actual = _sha256(ROOT / "v2" / "simulation" / name)
        assert actual == recorded[name], f"scientific drift in {name}"


def test_scientific_runtime_imports_no_model_or_truth():
    banned = ("v2.prediction", "v2.model_lab", "sklearn", "joblib",
              "v2.simulation.validation")
    for name in ("engine.py", "monte_carlo.py", "adapter.py"):
        tree = ast.parse((ROOT / "v2" / "simulation" / name).read_text())
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        for module in imported:
            assert not module.startswith(banned), f"{name} imports {module}"


# ---------------------------------------------------------------------------
# Contract versions.
# ---------------------------------------------------------------------------

def test_contract_versions_are_frozen():
    contracts = _manifest()["contracts"]
    assert SIMULATION_CONTRACT_VERSION == contracts["simulation_contract_version"] == "v1"
    assert ENGINE_VERSION == contracts["engine_version"] == "r4-engine-v1"
    assert MONTE_CARLO_VERSION == contracts["monte_carlo_version"] == "r5-monte-carlo-v1"
    assert PIT_DYNAMICS_VERSION == contracts["pit_dynamics_version"] == "r6-pit-dynamics-v1"
    assert PARAMETER_CONTRACT_VERSION == contracts["parameter_contract_version"] == "r3-v1"
    assert contracts["probability_semantics"] == PROBABILITY_SEMANTICS


def test_contemporaneity_contract_is_frozen():
    contract = _manifest()["r71_contemporaneity_contract"]
    assert REASON_NON_CONTEMPORANEOUS_ROSTER_MEMBER == \
        contract["reason"] == "non_contemporaneous_roster_member"
    assert REASON_NON_CONTEMPORANEOUS_ROSTER_MEMBER in ENGINE_UNSUPPORTED_REASONS
    assert CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES == \
        contract["max_observation_lap_times"] == 3.0
    assert contract["whole_state_rejection"] is True
    assert contract["drops_drivers"] is False
    assert contract["infers_retirement"] is False
    assert contract["reads_future_information"] is False


# ---------------------------------------------------------------------------
# Parameter / validation provenance.
# ---------------------------------------------------------------------------

def test_production_parameter_identity_is_frozen():
    recorded = _manifest()["r3_production_parameter"]
    manifest_path = (ROOT / "data" / "v2" / "simulation" / "params"
                     / "r3-v1__through-2024" / "manifest.json")
    live = _load(manifest_path)
    assert recorded["scientific_hash"] == live["scientific_hash"]
    assert recorded["parameter_version"] == \
        f'{live["parameter_contract_version"]}.{live["through_season"]}.' \
        f'{live["scientific_hash"][:12]}'
    assert recorded["through_season"] == 2024
    assert recorded["runtime_estimation"] is False


def test_r7_protocol_and_metrics_are_recorded():
    recorded = _manifest()["r7_protocol"]
    protocol = _load(R7_PROTOCOL)
    assert recorded["protocol_identity"] == protocol["protocol_identity"]
    assert recorded["excluded_seasons"] == [2018, 2019, 2025]
    assert recorded["master_seed"] == 20240101
    metrics = _manifest()["r7_final_accepted_validation"]
    assert metrics["supported_states"] == 42
    assert metrics["races"] == 23
    assert metrics["winner_log_loss"] == pytest.approx(1.2237, abs=1e-3)
    assert metrics["brier"] == pytest.approx(0.02669, abs=1e-4)
    assert metrics["expected_finish_mae"] == pytest.approx(2.4452, abs=1e-3)
    assert metrics["rps"] == pytest.approx(0.09280, abs=1e-4)
    assert metrics["ece"] == pytest.approx(0.01899, abs=1e-4)


# ---------------------------------------------------------------------------
# API contract + routes + policy.
# ---------------------------------------------------------------------------

def test_api_contract_hash_matches_freeze_manifest():
    recorded = _manifest()["api_contract"]["sha256"]
    assert _sha256(API_CONTRACT) == recorded


def test_api_contract_declares_the_single_core_endpoint():
    contract = _load(API_CONTRACT)
    assert contract["endpoint"]["method"] == "POST"
    assert contract["endpoint"]["path"] == "/v2/simulations/race"
    assert contract["endpoint"]["served_seasons"] == list(range(2018, 2025))
    assert contract["count_policy"]["default"] == 1000
    assert contract["count_policy"]["maximum_synchronous"] == 10000
    assert contract["probability_semantics"]["value"] == "MONTE_CARLO_FREQUENCY"


def test_app_exposes_the_simulation_route_and_keeps_prior_routes():
    from api.main import app
    routes = {f"{method.lower()} {route.path}"
              for route in app.routes
              for method in getattr(route, "methods", set())}
    assert PHASE6_ROUTE in routes
    # Frozen Phase-4/5 routes remain present.
    for path in ("get /v2/races", "get /v2/races/{race_id}/state",
                 "post /v2/predictions/winner-snapshot",
                 "get /v2/races/{race_id}/replay/timeline"):
        assert path in routes


def test_served_range_excludes_2025():
    manifest = _manifest()
    assert manifest["served_seasons"] == list(range(2018, 2025))
    assert manifest["firewall_2025"] is True
    assert 2025 not in manifest["served_seasons"]


def test_phase4_and_phase5_manifests_remain_present():
    assert PHASE4_MANIFEST.exists()
    assert PHASE5_MANIFEST.exists()


def test_probability_semantics_non_normalization_is_declared():
    semantics = _manifest()["probability_semantics"]
    assert semantics["value"] == "MONTE_CARLO_FREQUENCY"
    assert semantics["normalization"] == "none (service, schema, route, frontend)"
    assert semantics["dnf"] == "null (reliability deferred)"


def test_frontend_simulator_route_exists():
    assert (ROOT / "frontend" / "app" / "simulator" / "page.tsx").exists()
    assert (ROOT / "frontend" / "features" / "simulator"
            / "components" / "SimulatorView.tsx").exists()
    client = (ROOT / "frontend" / "lib" / "v2.ts").read_text()
    assert "/v2/simulations/race" in client


def test_adapter_unavailable_reason_type_is_importable():
    assert issubclass(SimulationUnavailableError, ValueError)
