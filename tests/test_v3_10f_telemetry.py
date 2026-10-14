"""V3.10F driver-telemetry backend tests (offline, no model, no network).

The telemetry service is a verbatim read-only projection over the frozen
D9 corpus + stints entity: NaN -> None, no aggregation, no reference, no
validity filtering. Causal (<=T) slicing is client-side (frontend selector
tests); these tests pin the server contract: shape, observation boundary
carriage, stint joins, unknown-race mapping, and the import firewall.
"""

from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import pytest

from api.v2_telemetry_service import (
    TELEMETRY_CONTRACT_VERSION,
    V2TelemetryService,
)
from raceintel.race_state.race_state_reconstruction import RaceNotFoundError

ROOT = Path(__file__).resolve().parents[1]
RACE = "2021-r01-R"


def _states() -> pd.DataFrame:
    df = pd.read_parquet(
        ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9"
        / "season=2021" / "driver_lap_state_d9__d9-2021.parquet")
    return df[df["race_id"] == RACE].copy()


def _stints() -> pd.DataFrame:
    import glob as _glob

    parts = []
    for path in sorted(_glob.glob(str(
            ROOT / "data" / "v2" / "processed" / "stints"
            / "season=2021" / "*.parquet"))):
        part = pd.read_parquet(path)
        parts.append(part[part["race_id"] == RACE].copy())
    return pd.concat(parts, ignore_index=True)


_states_cache = None
_stints_cache = None


def corpus():
    global _states_cache, _stints_cache
    if _states_cache is None:
        _states_cache = _states()
        _stints_cache = _stints()
    return _states_cache, _stints_cache


def make_service():
    states, stints = corpus()
    return V2TelemetryService(states, stints, [RACE])


@contextmanager
def telemetry_client(service):
    from fastapi.testclient import TestClient

    from api.main import app
    from api.v2_telemetry_service import get_v2_telemetry_service
    app.dependency_overrides[get_v2_telemetry_service] = lambda: service
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_v2_telemetry_service, None)


def test_projection_shape_and_counts():
    states, stints = corpus()
    payload = make_service().get_telemetry(RACE)
    assert payload["race_id"] == RACE
    assert payload["telemetry_contract_version"] == \
        TELEMETRY_CONTRACT_VERSION
    assert payload["lap_count"] == len(states)
    assert payload["stint_count"] == len(stints)
    assert payload["lap_count"] == len(payload["laps"])
    assert payload["stint_count"] == len(payload["stints"])


def test_observation_boundary_carried_verbatim():
    states, _ = corpus()
    payload = make_service().get_telemetry(RACE)
    ham_rows = states[states["driver_id"] == "hamilton"].sort_values(
        "lap_number")
    ham_laps = [lap for lap in payload["laps"]
                if lap["driver_id"] == "hamilton"]
    assert len(ham_laps) == len(ham_rows)
    for lap, (_, row) in zip(
            sorted(ham_laps, key=lambda entry: entry["lap_number"]),
            ham_rows.iterrows()):
        assert lap["observed_at_s"] == pytest.approx(
            float(row["state_time_s"]))


def test_nan_projects_to_none_never_zero():
    payload = make_service().get_telemetry(RACE)
    # Lap 1 has a null sector_1 (standing start); lap 3 (2021-r01 Hamilton)
    # has a null lap_time with present sectors.
    lap1 = next(lap for lap in payload["laps"]
                if lap["driver_id"] == "hamilton" and lap["lap_number"] == 1)
    assert lap1["sector_1_s"] is None
    assert lap1["lap_time_s"] is not None
    null_times = [lap for lap in payload["laps"]
                  if lap["lap_time_s"] is None]
    assert len(null_times) > 0
    for lap in payload["laps"]:
        for key in ("lap_time_s", "sector_1_s", "sector_2_s",
                    "sector_3_s"):
            assert lap[key] is None or lap[key] != 0 or True
            if lap[key] is not None:
                assert lap[key] > 0


def test_stint_end_observed_joins_lap_grid():
    payload = make_service().get_telemetry(RACE)
    ham1 = next(s for s in payload["stints"]
                if s["driver_id"] == "hamilton" and s["stint_number"] == 1)
    assert ham1["compound"] == "MEDIUM"
    assert ham1["start_lap"] == 1
    assert ham1["end_lap"] == 13
    lap13 = next(lap for lap in payload["laps"]
                 if lap["driver_id"] == "hamilton" and lap["lap_number"] == 13)
    assert ham1["end_observed_at_s"] == pytest.approx(
        lap13["observed_at_s"])


def test_unknown_race_raises_and_routes_404():
    service = make_service()
    with pytest.raises(RaceNotFoundError):
        service.get_telemetry("2025-r01-R")
    with telemetry_client(service) as client:
        response = client.get("/v2/races/2025-r01-R/replay/telemetry")
        assert response.status_code == 404
        assert response.json()["error"] == "unknown_race"


def test_route_serves_full_race_payload():
    with telemetry_client(make_service()) as client:
        response = client.get(f"/v2/races/{RACE}/replay/telemetry")
        assert response.status_code == 200
        body = response.json()
        assert body["race_id"] == RACE
        assert body["lap_count"] == len(body["laps"])
        assert body["stint_count"] == len(body["stints"])
        required = {"driver_id", "lap_number", "observed_at_s",
                    "lap_time_s", "sector_1_s", "sector_2_s", "sector_3_s",
                    "compound", "stint_number"}
        assert required <= set(body["laps"][0])


def test_import_firewall_no_science_engine():
    source = (ROOT / "api" / "v2_telemetry_service.py").read_text()
    # Skip the module docstring (design notes name the forbidden zones);
    # the executable code must never touch them.
    _, _, code = source.partition('"""V3.10F')
    _, _, code = code.partition('"""')
    assert "def build_v2_telemetry_service" in code
    top, _, _ = code.partition("def build_v2_telemetry_service")
    for forbidden in ("prediction_engine", "RacePredictionEngine",
                      "feature_bridge", "generate_race_artifact",
                      "generate_checkpoint", "simulation", "strategy",
                      "consensus", "mc2"):
        assert forbidden not in code, forbidden
    assert "v2_service" not in top
    assert "get_v2_service" not in top
    routes = (ROOT / "api" / "v2_telemetry_routes.py").read_text()
    assert "v2_telemetry_service" in routes
    assert "get_v2_telemetry_service" in routes
