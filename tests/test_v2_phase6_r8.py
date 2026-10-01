"""Phase-6 R8 product integration tests.

Covers the production simulation service, the ``POST /v2/simulations/race``
endpoint, request/response semantics, the replay → simulation seam, the
unsupported-state contract (including the R7.1 non-contemporaneous
regression), probability invariants, determinism/concurrency, the 2025
firewall, and a performance smoke. The scientific runtime
(``raceintel/simulation/*``) is exercised, never modified.
"""

from __future__ import annotations

import ast
import concurrent.futures
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.v2_service import load_v2_service
from api.v2_simulation_routes import router as simulation_router
from api.v2_simulation_schemas import V2SimulationRequest
from api.v2_simulation_service import (
    DEFAULT_MASTER_SEED,
    DEFAULT_SIMULATION_COUNT,
    MAX_SYNCHRONOUS_SIMULATIONS,
    MIN_SIMULATION_COUNT,
    PRODUCTION_PARAMETER_SEASON,
    V2SimulationService,
    build_v2_simulation_service,
    get_v2_simulation_service,
)
from raceintel.race_state.race_state import AnchorObservation
from raceintel.race_state.race_state_reconstruction import AnchorNotFoundError
from raceintel.simulation.adapter import SimulationUnavailableError, from_race_state
from raceintel.simulation.engine import ENGINE_UNSUPPORTED_REASONS, SimulationUnsupportedError
from raceintel.simulation.results import PROBABILITY_SEMANTICS

REPO_ROOT = Path(__file__).resolve().parents[1]

# Discovered exact-anchor fixtures (all within the served 2018–2024 range).
ORDINARY = dict(race_id="2022-r01-R", anchor_driver_id="perez",
                anchor_lap_number=30, anchor_state_time_s=6745.686)
LATE = dict(race_id="2022-r01-R", anchor_driver_id="russell",
            anchor_lap_number=38, anchor_state_time_s=7577.904)
PATHOLOGICAL = dict(race_id="2020-r07-R", anchor_driver_id="hamilton",
                    anchor_lap_number=22, anchor_state_time_s=4679.013)
WET = dict(race_id="2018-r11-R", anchor_driver_id="alonso",
           anchor_lap_number=44, anchor_state_time_s=4004.408)
NEUTRALIZED = dict(race_id="2018-r05-R", anchor_driver_id="raikkonen",
                   anchor_lap_number=5, anchor_state_time_s=1083.892)
UNOBSERVED = dict(race_id="2022-r01-R", anchor_driver_id="leclerc",
                  anchor_lap_number=1, anchor_state_time_s=3854.174)
# Shared-T: two different anchors at the same absolute T adapt identically.
SHARED_T_RACE = "2018-r10-R"
SHARED_T_TIME = 4209.110
SHARED_T_ANCHORS = (("grosjean", 38), ("sainz", 38))

EXPECTED_PARAMETER_HASH = (
    "4c2f85f08f1ce66cc6477982b2d5c97e9547f70927224b8e949ebe123ff3f140")
EXPECTED_PARAMETER_VERSION = "r3-v1.2024.4c2f85f08f1c"

NEW_API_FILES = (
    REPO_ROOT / "api" / "v2_simulation_service.py",
    REPO_ROOT / "api" / "v2_simulation_routes.py",
    REPO_ROOT / "api" / "v2_simulation_schemas.py",
)
RUNTIME_FILES = (
    REPO_ROOT / "raceintel" / "simulation" / "engine.py",
    REPO_ROOT / "raceintel" / "simulation" / "monte_carlo.py",
    REPO_ROOT / "raceintel" / "simulation" / "adapter.py",
    REPO_ROOT / "raceintel" / "simulation" / "state.py",
    REPO_ROOT / "raceintel" / "simulation" / "results.py",
)


# ---------------------------------------------------------------------------
# Fixtures.
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def v2_service():
    return load_v2_service()


@pytest.fixture(scope="module")
def sim_service(v2_service):
    return build_v2_simulation_service(v2_service)


@pytest.fixture(scope="module")
def client(sim_service):
    from api.main import app
    app.dependency_overrides[get_v2_simulation_service] = lambda: sim_service
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.pop(get_v2_simulation_service, None)


def _post(client, anchor: dict, count: int = 64, seed: int | None = None):
    body = dict(anchor)
    body["simulation_count"] = count
    if seed is not None:
        body["master_seed"] = seed
    return client.post("/v2/simulations/race", json=body)


# ===========================================================================
# Service initialization / production parameter artifact.
# ===========================================================================

def test_service_initializes_with_shared_phase4_authority(sim_service):
    assert isinstance(sim_service, V2SimulationService)
    assert len(sim_service.race_ids) == 149
    assert sim_service.served_seasons == tuple(range(2018, 2025))


def test_production_parameter_artifact_identity_is_frozen(sim_service):
    params = sim_service.parameters
    assert params.parameter_set_id == "phase6-r3-empirical"
    assert params.through_season == PRODUCTION_PARAMETER_SEASON == 2024
    assert params.scientific_hash() == EXPECTED_PARAMETER_HASH
    assert params.parameter_version == EXPECTED_PARAMETER_VERSION


def test_service_loads_no_backtest_artifact(sim_service):
    # Product requests always use the through-2024 set; no season-specific
    # backtest artifact is selected anywhere in the service.
    assert sim_service.parameters.estimation_seasons == tuple(range(2018, 2025))


# ===========================================================================
# Exact-anchor reconstruction and the replay → simulation seam.
# ===========================================================================

def test_exact_anchor_reconstruction(sim_service):
    race_state = sim_service._reconstructor.reconstruct(
        AnchorObservation(**ORDINARY))  # noqa: SLF001 - factual authority
    assert race_state.race_id == ORDINARY["race_id"]
    assert race_state.state_time_s == ORDINARY["anchor_state_time_s"]


def test_anchor_miss_is_not_nearest_matched(sim_service):
    off = dict(ORDINARY)
    off["anchor_state_time_s"] = ORDINARY["anchor_state_time_s"] + 0.5
    with pytest.raises(AnchorNotFoundError):
        sim_service._reconstructor.reconstruct(  # noqa: SLF001
            AnchorObservation(**off))


def test_replay_frame_seam_reconstructs_identical_factual_state(
        v2_service, sim_service):
    from api.v2_replay_service import build_v2_replay_service
    replay = build_v2_replay_service(v2_service)
    result = replay.get_frame(ORDINARY["race_id"], second_frame_index(replay,
                                                                     ORDINARY))
    frame = result["frame"]
    race_state = sim_service._reconstructor.reconstruct(  # noqa: SLF001
        AnchorObservation(
            race_id=frame["race_id"],
            anchor_driver_id=frame["anchor_driver_id"],
            anchor_lap_number=frame["anchor_lap_number"],
            anchor_state_time_s=frame["anchor_state_time_s"]))
    assert race_state.to_dict() == result["state"].to_dict()


def second_frame_index(replay, anchor: dict) -> int:
    """Find the replay frame whose exact anchor matches ``anchor``."""
    timeline = replay.get_timeline(anchor["race_id"])
    for frame in timeline.frames:
        if (frame.anchor_driver_id == anchor["anchor_driver_id"]
                and frame.anchor_lap_number == anchor["anchor_lap_number"]
                and frame.anchor_state_time_s == anchor["anchor_state_time_s"]):
            return frame.frame_index
    raise AssertionError(f"no replay frame for {anchor!r}")


def test_shared_t_anchors_adapt_to_identical_simulation_state(sim_service):
    identities = set()
    for driver, lap in SHARED_T_ANCHORS:
        race_state = sim_service._reconstructor.reconstruct(  # noqa: SLF001
            AnchorObservation(
                race_id=SHARED_T_RACE, anchor_driver_id=driver,
                anchor_lap_number=lap,
                anchor_state_time_s=SHARED_T_TIME))
        identities.add(from_race_state(race_state).identity())
    assert len(identities) == 1


# ===========================================================================
# Request validation (schema-level).
# ===========================================================================

def test_request_defaults_and_bounds():
    request = V2SimulationRequest(**ORDINARY)
    assert request.simulation_count == DEFAULT_SIMULATION_COUNT
    assert request.master_seed is None
    assert V2SimulationRequest(**{**ORDINARY, "simulation_count": MIN_SIMULATION_COUNT})
    assert V2SimulationRequest(**{**ORDINARY,
                                  "simulation_count": MAX_SYNCHRONOUS_SIMULATIONS})


@pytest.mark.parametrize("count", [0, -1, MAX_SYNCHRONOUS_SIMULATIONS + 1])
def test_request_rejects_out_of_range_count(count):
    with pytest.raises(Exception):
        V2SimulationRequest(**{**ORDINARY, "simulation_count": count})


@pytest.mark.parametrize("seed", [-1, 2**64])
def test_request_rejects_out_of_range_seed(seed):
    with pytest.raises(Exception):
        V2SimulationRequest(**{**ORDINARY, "master_seed": seed})


def test_request_rejects_malformed_fields():
    with pytest.raises(Exception):
        V2SimulationRequest(**{**ORDINARY, "anchor_lap_number": 0})
    with pytest.raises(Exception):
        V2SimulationRequest(**{**ORDINARY, "race_id": ""})


def test_http_validation_returns_422(client):
    bad = client.post("/v2/simulations/race",
                      json={**ORDINARY, "simulation_count": 0})
    assert bad.status_code == 422
    assert client.post("/v2/simulations/race",
                       json={**ORDINARY, "simulation_count": "many"}
                       ).status_code == 422


# ===========================================================================
# 2018–2024 served range and the 2025 firewall.
# ===========================================================================

def test_served_seasons_are_2018_through_2024(sim_service):
    assert set(sim_service.served_seasons) == set(range(2018, 2025))
    assert any(r.startswith("2018-") for r in sim_service.race_ids)
    assert any(r.startswith("2024-") for r in sim_service.race_ids)


def test_2025_request_is_404(client):
    response = client.post("/v2/simulations/race", json={
        "race_id": "2025-r01-R", "anchor_driver_id": "verstappen",
        "anchor_lap_number": 1, "anchor_state_time_s": 1.0,
        "simulation_count": 10})
    assert response.status_code == 404
    assert response.json()["error"] == "unknown_race"


# ===========================================================================
# Ordinary simulation: response semantics and probability invariants.
# ===========================================================================

@pytest.fixture(scope="module")
def ordinary(client):
    response = _post(client, ORDINARY, count=128, seed=20240101)
    assert response.status_code == 200
    return response.json()


def test_response_identifies_anchor_and_contract(ordinary):
    for key in ("race_id", "anchor_driver_id", "anchor_lap_number",
                "anchor_state_time_s", "simulation_contract_version",
                "engine_version", "monte_carlo_version", "pit_dynamics_version",
                "mechanics", "probability_semantics",
                "probability_semantics_note", "parameter_set_id",
                "parameter_version", "parameter_hash",
                "simulation_request_identity", "scientific_result_identity",
                "requested_simulation_count", "valid_simulations",
                "invalid_simulations", "master_seed", "engine_runtime_s",
                "runtime", "drivers"):
        assert key in ordinary, key
    assert ordinary["race_id"] == ORDINARY["race_id"]
    assert ordinary["anchor_driver_id"] == ORDINARY["anchor_driver_id"]
    assert ordinary["anchor_lap_number"] == ORDINARY["anchor_lap_number"]
    assert ordinary["requested_simulation_count"] == 128
    assert ordinary["valid_simulations"] + ordinary["invalid_simulations"] == 128
    assert ordinary["mechanics"] == ["pit_dynamics"]


def test_probability_semantics_is_monte_carlo_frequency(ordinary):
    assert ordinary["probability_semantics"] == PROBABILITY_SEMANTICS
    assert "INDEPENDENT_BINARY" in ordinary["probability_semantics_note"]


def test_winner_mass_is_one_without_normalization(ordinary):
    total = sum(d["win_probability"] for d in ordinary["drivers"])
    assert total == pytest.approx(1.0, abs=1e-9)


def test_podium_mass_equals_places(ordinary):
    total = sum(d["podium_probability"] for d in ordinary["drivers"])
    assert total == pytest.approx(3.0, abs=1e-9)


def test_position_distributions_are_complete_and_normalized(ordinary):
    field = len(ordinary["drivers"])
    for driver in ordinary["drivers"]:
        distribution = driver["finish_position_distribution"]
        positions = [entry["position"] for entry in distribution]
        assert positions == list(range(1, field + 1))
        total = sum(entry["frequency"] for entry in distribution)
        assert total == pytest.approx(1.0, abs=1e-9)


def test_expected_finish_is_bounded_by_field(ordinary):
    field = len(ordinary["drivers"])
    for driver in ordinary["drivers"]:
        assert 1.0 <= driver["expected_finish"] <= float(field)


def test_dnf_and_points_are_null_never_fabricated(ordinary):
    for driver in ordinary["drivers"]:
        assert driver["dnf_probability"] is None
        assert driver["points_probability"] is None
        assert driver["expected_points"] is None


def test_response_carries_no_raw_trajectories(ordinary):
    assert "sample_orders" not in ordinary
    assert "trajectories" not in ordinary
    assert "trace" not in ordinary


# ===========================================================================
# Unsupported-state behavior (stable reasons, no fallback).
# ===========================================================================

@pytest.mark.parametrize("anchor,reason", [
    (WET, "wet_compound_state"),
    (NEUTRALIZED, "neutralized_track_state"),
    (UNOBSERVED, "unobserved_roster_member"),
    (PATHOLOGICAL, "non_contemporaneous_roster_member"),
])
def test_unsupported_state_returns_stable_reason(client, anchor, reason):
    response = _post(client, anchor, count=16)
    assert response.status_code == 422, response.text
    body = response.json()
    assert body["error"] == "simulation_unsupported"
    assert body["reason"] == reason
    assert reason in ENGINE_UNSUPPORTED_REASONS or reason in (
        "unobserved_roster_member",)
    assert body["detail"]


def test_non_contemporaneous_state_returns_no_probabilities(client):
    response = _post(client, PATHOLOGICAL, count=16)
    assert response.status_code == 422
    assert "drivers" not in response.json()


def test_pathological_state_offender_is_named_not_dropped(client):
    body = _post(client, PATHOLOGICAL, count=16).json()
    assert "giovinazzi" in body["detail"]


def test_anchor_miss_returns_unknown_state(client):
    off = dict(ORDINARY, anchor_state_time_s=ORDINARY["anchor_state_time_s"] + 0.5)
    response = _post(client, off, count=16)
    assert response.status_code == 422
    assert response.json()["error"] == "unknown_state"


def test_unsupported_reason_is_deterministic(client):
    first = _post(client, WET, count=8).json()
    second = _post(client, WET, count=8).json()
    assert first["reason"] == second["reason"] == "wet_compound_state"


def test_service_never_silently_falls_back(sim_service):
    # The engine's unsupported taxonomy is surfaced, never replaced by a
    # nearby state or a fabricated probability vector.
    with pytest.raises(SimulationUnsupportedError) as excinfo:
        sim_service.run_simulation(**WET, simulation_count=8)
    assert excinfo.value.reason == "wet_compound_state"


def test_adapter_unobserved_reason_is_surfaced(sim_service):
    with pytest.raises(SimulationUnavailableError) as excinfo:
        sim_service.run_simulation(**UNOBSERVED, simulation_count=8)
    assert excinfo.value.reason == "unobserved_roster_member"


# ===========================================================================
# Determinism and concurrency.
# ===========================================================================

def test_same_request_is_deterministic(sim_service):
    first = sim_service.run_simulation(**ORDINARY, simulation_count=64,
                                       master_seed=11)
    second = sim_service.run_simulation(**ORDINARY, simulation_count=64,
                                        master_seed=11)
    assert first["scientific_result_identity"] == \
        second["scientific_result_identity"]
    assert first["drivers"] == second["drivers"]


def test_different_seed_changes_result_identity(sim_service):
    first = sim_service.run_simulation(**ORDINARY, simulation_count=64,
                                       master_seed=11)
    second = sim_service.run_simulation(**ORDINARY, simulation_count=64,
                                        master_seed=12)
    assert first["scientific_result_identity"] != \
        second["scientific_result_identity"]


def test_default_seed_is_used_when_unspecified(sim_service):
    result = sim_service.run_simulation(**ORDINARY, simulation_count=16)
    assert result["master_seed"] == DEFAULT_MASTER_SEED


def test_concurrent_same_request_is_deterministic(sim_service):
    reference = sim_service.run_simulation(**ORDINARY, simulation_count=64,
                                           master_seed=99)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures = [pool.submit(
            sim_service.run_simulation, **ORDINARY, simulation_count=64,
            master_seed=99) for _ in range(4)]
        results = [future.result() for future in futures]
    for result in results:
        assert result["scientific_result_identity"] == \
            reference["scientific_result_identity"]
        assert result["drivers"] == reference["drivers"]


def test_concurrent_distinct_requests_do_not_cross_contaminate(sim_service):
    mid = sim_service.run_simulation(**ORDINARY, simulation_count=64,
                                     master_seed=5)
    late = sim_service.run_simulation(**LATE, simulation_count=64, master_seed=5)
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        mixed = [
            pool.submit(sim_service.run_simulation, **ORDINARY,
                        simulation_count=64, master_seed=5),
            pool.submit(sim_service.run_simulation, **LATE,
                        simulation_count=64, master_seed=5),
        ]
        got_mid, got_late = [future.result() for future in mixed]
    assert got_mid["scientific_result_identity"] == \
        mid["scientific_result_identity"]
    assert got_late["scientific_result_identity"] == \
        late["scientific_result_identity"]
    assert got_mid["scientific_result_identity"] != \
        got_late["scientific_result_identity"]


# ===========================================================================
# Runtime firewalls (no winner model, no validation truth, no 2025).
# ===========================================================================

_FORBIDDEN_SERVICE_TOKENS = (
    "raceintel.prediction", "raceintel.model_lab", "sklearn", "joblib",
    "raceintel.simulation.validation", "read_parquet", "race_driver_labels",
    "classified_position", "dnf_flag", "winner_flag", "serving",
)


def test_new_api_modules_import_no_model_or_truth():
    for path in NEW_API_FILES:
        source = path.read_text()
        for token in _FORBIDDEN_SERVICE_TOKENS:
            assert token not in source, f"{path.name} references {token}"


def test_runtime_modules_import_no_winner_model_or_labels():
    banned_prefixes = ("raceintel.prediction", "raceintel.model_lab", "sklearn", "joblib",
                       "pandas", "fastapi")
    for path in RUNTIME_FILES:
        tree = ast.parse(path.read_text())
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        for name in imported:
            assert not name.startswith(banned_prefixes), \
                f"{path.name} imports {name}"
        source = path.read_text()
        for token in ("race_driver_labels", "classified_position",
                      "winner_flag", "read_parquet"):
            assert token not in source, f"{path.name} references {token}"


def test_service_module_imports_no_api_engine_into_runtime():
    tree = ast.parse((REPO_ROOT / "raceintel" / "simulation" / "monte_carlo.py")
                     .read_text())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    assert not any(name.startswith("api") for name in imported)


def test_route_surface_has_exactly_one_core_endpoint():
    paths = {(route.path, tuple(sorted(route.methods)))
             for route in simulation_router.routes}
    assert ("/v2/simulations/race", ("POST",)) in paths
    assert len(paths) == 1


# ===========================================================================
# Performance smoke.
# ===========================================================================

def test_performance_smoke_late_1000(client):
    response = _post(client, LATE, count=1000, seed=20240101)
    assert response.status_code == 200
    body = response.json()
    assert body["valid_simulations"] == 1000
    assert body["invalid_simulations"] == 0
    assert body["engine_runtime_s"] < 60.0
    assert body["runtime"]["total_s"] < 90.0
