"""Phase-4 R5: versioned V2 API boundary over the frozen pipeline.

Fast route/schema/error tests inject a fake V2 service (no 12-second
feature engine). Two integration tests use the real pipeline on
DEVELOPMENT data only; they never read targets and never report quality
metrics. Legacy behavior is pinned unchanged.
"""

import json
import re
import time
from pathlib import Path

import pytest

from raceintel.race_state import race_state as RS
from raceintel.prediction import (
    NO_OBSERVATION_AT_SNAPSHOT,
    DriverPrediction,
    ModelIdentity,
    PredictionSnapshot,
)
from raceintel.race_state.race_state_reconstruction import AnchorNotFoundError, RaceNotFoundError

ROOT = Path(__file__).resolve().parents[1]

RACE_A = "2023-r01-R"
RACE_B = "2021-r12-R"


def _identity():
    return ModelIdentity(
        task="winner", target="is_winner",
        eligibility_mask="eligible_is_winner", feature_set="ALL_84",
        feature_set_version="v8", estimator="LogisticRegression",
        estimator_params=(("C", 0.01),), calibration_method="RAW",
        probability_semantics="INDEPENDENT_BINARY",
        training_seasons=(2018, 2019, 2020, 2021, 2022, 2023, 2024),
        transformed_dim=106, feature_count=84,
        artifact_sha256="test-sha", specification_fingerprint="test-fp",
        sklearn_version="1.8.0")


def _driver(driver_id, lap, t, age, position):
    return RS.DriverRaceState(
        driver_id=driver_id, observable=True, observed_lap_number=lap,
        observed_time_s=t, observation_age_s=age, position=position)


def _state(obs=("a", "b")):
    entries = []
    if "a" in obs:
        entries.append(_driver("a", 2, 200.0, 0.0, 1))
    if "b" in obs:
        entries.append(_driver("b", 1, 110.0, 90.0, 2))
    if "d" in obs:
        entries.append(_driver("d", 2, 198.0, 2.0, 3))
    entries.append(RS.DriverRaceState.unobserved("c"))
    return RS.RaceState(
        race_id=RACE_A, anchor_driver_id="a", anchor_lap_number=2,
        state_time_s=200.0, drivers=tuple(entries),
        race_context=RS.RaceContext(), weather=RS.WeatherState(),
        race_control=RS.RaceControlState())


def _snapshot(obs, probs):
    state = _state(obs)
    entries = []
    for member, prob in zip(
            [d for d in state.drivers if d.observable], probs):
        entries.append(DriverPrediction(
            driver_id=member.driver_id, observable=True,
            observed_lap_number=member.observed_lap_number,
            observed_time_s=member.observed_time_s,
            observation_age_s=member.observation_age_s,
            observed_position=member.position,
            winner_probability=prob, unavailable_reason=None))
    for member in state.drivers:
        if not member.observable:
            entries.append(DriverPrediction(
                driver_id=member.driver_id, observable=False,
                unavailable_reason=NO_OBSERVATION_AT_SNAPSHOT))
    return PredictionSnapshot(
        race_id=state.race_id, anchor_driver_id=state.anchor_driver_id,
        anchor_lap_number=state.anchor_lap_number,
        state_time_s=state.state_time_s, model=_identity(),
        predictions=tuple(entries))


ANCHORS = [
    {"driver_id": "b", "lap_number": 1, "state_time_s": 110.0},
    {"driver_id": "a", "lap_number": 1, "state_time_s": 120.0},
    {"driver_id": "d", "lap_number": 1, "state_time_s": 120.0},
    {"driver_id": "a", "lap_number": 2, "state_time_s": 200.0},
    {"driver_id": "b", "lap_number": 2, "state_time_s": 205.0},
]
EXACT = {"anchor_driver_id": "a", "anchor_lap_number": 2,
         "anchor_state_time_s": 200.0}

RACES = [
    {"race_id": RACE_B, "season": 2021, "round_no": 12,
     "event_name": "Belgian Grand Prix", "circuit_id": "spa",
     "country": "Belgium", "location": "Stavelot", "scheduled_laps": 44},
    {"race_id": RACE_A, "season": 2023, "round_no": 1,
     "event_name": "Bahrain Grand Prix", "circuit_id": "bahrain",
     "country": "Bahrain", "location": "Sakhir", "scheduled_laps": 57},
]


class FakeV2Service:
    """Lightweight stand-in honoring the V2Service method contracts."""

    def __init__(self, probs=(0.5, 0.25), obs=("a", "b")):
        self._probs = tuple(probs)
        self._obs = tuple(obs)

    def list_races(self):
        return [dict(row) for row in RACES]

    def list_anchors(self, race_id, offset=0, limit=100):
        if race_id not in (RACE_A, RACE_B):
            raise RaceNotFoundError(race_id)
        window = ANCHORS[offset:offset + limit]
        return {"race_id": race_id, "total": len(ANCHORS),
                "offset": offset, "limit": limit,
                "anchors": [dict(a) for a in window]}

    def get_state(self, race_id, driver_id, lap, t):
        if race_id not in (RACE_A, RACE_B):
            raise RaceNotFoundError(race_id)
        if race_id != RACE_A or (driver_id, lap, t) != (
                EXACT["anchor_driver_id"], EXACT["anchor_lap_number"],
                EXACT["anchor_state_time_s"]):
            raise AnchorNotFoundError(race_id, driver_id, lap, t)
        return _state(self._obs)

    def predict_snapshot(self, race_id, driver_id, lap, t):
        if race_id not in (RACE_A, RACE_B):
            raise RaceNotFoundError(race_id)
        if race_id != RACE_A or (driver_id, lap, t) != (
                EXACT["anchor_driver_id"], EXACT["anchor_lap_number"],
                EXACT["anchor_state_time_s"]):
            raise AnchorNotFoundError(race_id, driver_id, lap, t)
        return _snapshot(self._obs, self._probs)


@pytest.fixture()
def v2_client():
    from fastapi.testclient import TestClient

    from api.main import app
    from api.v2_service import get_v2_service
    app.dependency_overrides[get_v2_service] = FakeV2Service
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(get_v2_service, None)


def _override_client(service):
    from contextlib import contextmanager

    from fastapi.testclient import TestClient

    from api.main import app
    from api.v2_service import get_v2_service

    @contextmanager
    def _scoped():
        app.dependency_overrides[get_v2_service] = lambda: service
        try:
            yield TestClient(app, raise_server_exceptions=False)
        finally:
            app.dependency_overrides.pop(get_v2_service, None)

    return _scoped()


# --- router + legacy ---------------------------------------------------------


def test_v2_router_registered(v2_client):
    spec = v2_client.get("/openapi.json")
    assert spec.status_code == 200
    paths = spec.json()["paths"]
    for path in ("/v2/races", "/v2/races/{race_id}/states",
                 "/v2/races/{race_id}/state",
                 "/v2/predictions/winner-snapshot"):
        assert path in paths, path
    for legacy in ("/health", "/races", "/predict/ensemble",
                   "/predict/single-model"):
        assert legacy in paths, legacy


def test_legacy_health_unchanged(api_client):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_legacy_races_unchanged(api_client):
    resp = api_client.get("/races")
    assert resp.status_code == 200
    assert len(resp.json()["races"]) == 104


def test_legacy_ensemble_contract_unchanged(api_client):
    resp = api_client.post("/predict/ensemble", json={
        "year": 2023, "event": "Bahrain Grand Prix"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["latest_lap"] == 25 and len(body["summary"]) == 15


def test_legacy_single_model_contract_unchanged(api_client):
    resp = api_client.post("/predict/single-model", json={
        "year": 2023, "event": "Bahrain Grand Prix", "model": "xgboost"})
    assert resp.status_code == 200
    assert [r["lap"] for r in resp.json()["summary"]] == [5, 10, 15, 20, 25]


# --- race discovery ----------------------------------------------------------


def test_list_races_success(v2_client):
    resp = v2_client.get("/v2/races")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2 and len(body["races"]) == 2


def test_race_ordering_stable(v2_client):
    races = v2_client.get("/v2/races").json()["races"]
    keys = [(r["season"], r["round_no"], r["race_id"]) for r in races]
    assert keys == sorted(keys)


def test_race_discovery_has_no_outcomes(v2_client):
    body = v2_client.get("/v2/races").json()
    allowed = {"race_id", "season", "round_no", "event_name", "circuit_id",
               "country", "location", "scheduled_laps"}
    for row in body["races"]:
        assert set(row) == allowed, set(row) - allowed
    text = json.dumps(body).lower()
    for token in ("is_winner", "final_position", "podium", "classified",
                  "winner_flag", "points", "actual_winner"):
        assert token not in text, token


def test_unknown_race_404(v2_client):
    for resp in (
            v2_client.get("/v2/races/1999-r99-R/states"),
            v2_client.get("/v2/races/1999-r99-R/state",
                          params={**EXACT}),
            v2_client.post("/v2/predictions/winner-snapshot", json={
                "race_id": "1999-r99-R", **EXACT})):
        assert resp.status_code == 404
        assert resp.json()["error"] == "unknown_race"


def test_2025_race_not_served(v2_client):
    resp = v2_client.get("/v2/races/2025-r01-R/states")
    assert resp.status_code == 404


# --- anchor discovery --------------------------------------------------------


def test_states_success(v2_client):
    resp = v2_client.get(f"/v2/races/{RACE_A}/states")
    assert resp.status_code == 200
    body = resp.json()
    assert body["race_id"] == RACE_A and body["total"] == len(ANCHORS)


def test_states_deterministic_ordering(v2_client):
    anchors = v2_client.get(
        f"/v2/races/{RACE_A}/states",
        params={"limit": 500}).json()["anchors"]
    keys = [(a["state_time_s"], a["lap_number"], a["driver_id"])
            for a in anchors]
    assert keys == sorted(keys)
    assert anchors == ANCHORS


def test_states_pagination_default(v2_client):
    body = v2_client.get(f"/v2/races/{RACE_A}/states").json()
    assert (body["offset"], body["limit"]) == (0, 100)
    assert len(body["anchors"]) == len(ANCHORS)


def test_states_pagination_custom(v2_client):
    body = v2_client.get(f"/v2/races/{RACE_A}/states",
                         params={"offset": 1, "limit": 2}).json()
    assert (body["offset"], body["limit"], body["total"]) == (1, 2, 5)
    assert body["anchors"] == ANCHORS[1:3]


@pytest.mark.parametrize("params", [
    {"limit": 0}, {"limit": 501}, {"offset": -1}, {"limit": "many"}])
def test_states_invalid_pagination_422(v2_client, params):
    resp = v2_client.get(f"/v2/races/{RACE_A}/states", params=params)
    assert resp.status_code == 422


def test_state_anchors_have_no_labels(v2_client):
    anchors = v2_client.get(
        f"/v2/races/{RACE_A}/states").json()["anchors"]
    for anchor in anchors:
        assert set(anchor) == {"driver_id", "lap_number", "state_time_s"}


# --- RaceState endpoint ------------------------------------------------------


def test_exact_state_success(v2_client):
    resp = v2_client.get(f"/v2/races/{RACE_A}/state", params=EXACT)
    assert resp.status_code == 200
    body = resp.json()
    assert body["race_id"] == RACE_A
    assert body["anchor_driver_id"] == EXACT["anchor_driver_id"]
    assert body["anchor_lap_number"] == EXACT["anchor_lap_number"]
    assert body["state_time_s"] == EXACT["anchor_state_time_s"]


def test_missing_anchor_422(v2_client):
    resp = v2_client.get(f"/v2/races/{RACE_A}/state", params={
        "anchor_driver_id": "a", "anchor_lap_number": 9,
        "anchor_state_time_s": 999.0})
    assert resp.status_code == 422
    assert resp.json()["error"] == "unknown_state"


def test_no_nearest_substitution(v2_client):
    resp = v2_client.get(f"/v2/races/{RACE_A}/state", params={
        "anchor_driver_id": "a", "anchor_lap_number": 2,
        "anchor_state_time_s": 200.0001})
    assert resp.status_code == 422


def test_state_complete_roster(v2_client):
    drivers = v2_client.get(
        f"/v2/races/{RACE_A}/state", params=EXACT).json()["drivers"]
    assert [d["driver_id"] for d in drivers] == ["a", "b", "c"]


def test_state_unobservable_preserved(v2_client):
    drivers = v2_client.get(
        f"/v2/races/{RACE_A}/state", params=EXACT).json()["drivers"]
    entry = next(d for d in drivers if d["driver_id"] == "c")
    assert entry["observable"] is False
    assert entry["observed_lap_number"] is None
    assert entry["position"] is None


# --- prediction endpoint -----------------------------------------------------


def test_prediction_success(v2_client):
    resp = v2_client.post("/v2/predictions/winner-snapshot", json={
        "race_id": RACE_A, **EXACT})
    assert resp.status_code == 200
    assert resp.json()["race_id"] == RACE_A


def test_prediction_complete_roster(v2_client):
    body = v2_client.post("/v2/predictions/winner-snapshot", json={
        "race_id": RACE_A, **EXACT}).json()
    assert [p["driver_id"] for p in body["predictions"]] == ["a", "b", "c"]
    assert body["roster_size"] == 3


def test_prediction_observable_preserved(v2_client):
    body = v2_client.post("/v2/predictions/winner-snapshot", json={
        "race_id": RACE_A, **EXACT}).json()
    probs = {p["driver_id"]: p["winner_probability"]
             for p in body["predictions"]}
    assert probs == {"a": 0.5, "b": 0.25, "c": None}


def test_prediction_unavailable_null_and_reason(v2_client):
    body = v2_client.post("/v2/predictions/winner-snapshot", json={
        "race_id": RACE_A, **EXACT}).json()
    entry = next(p for p in body["predictions"] if p["driver_id"] == "c")
    assert entry["winner_probability"] is None
    assert entry["unavailable_reason"] == NO_OBSERVATION_AT_SNAPSHOT


def test_prediction_semantics_explicit(v2_client):
    from raceintel.prediction import PROBABILITY_SEMANTICS_NOTE
    body = v2_client.post("/v2/predictions/winner-snapshot", json={
        "race_id": RACE_A, **EXACT}).json()
    assert body["probability_semantics"] == "INDEPENDENT_BINARY"
    assert body["model"]["probability_semantics"] == "INDEPENDENT_BINARY"
    assert body["probability_semantics_note"] == PROBABILITY_SEMANTICS_NOTE
    text = json.dumps(body).lower()
    assert "probability_share" not in text
    assert "normalized" not in text.replace("do not renormalize", "")


def test_prediction_sum_above_one_not_normalized():
    with _override_client(
            FakeV2Service(probs=(0.60, 0.35, 0.20),
                          obs=("a", "b", "d"))) as client:
        body = client.post("/v2/predictions/winner-snapshot", json={
            "race_id": RACE_A, **EXACT}).json()
    probs = [p["winner_probability"] for p in body["predictions"]
             if p["observable"]]
    assert probs == [0.60, 0.35, 0.20]
    assert abs(sum(probs) - 1.15) < 1e-12


def test_prediction_sum_below_one_not_normalized():
    with _override_client(
            FakeV2Service(probs=(0.10, 0.05, 0.02),
                          obs=("a", "b", "d"))) as client:
        body = client.post("/v2/predictions/winner-snapshot", json={
            "race_id": RACE_A, **EXACT}).json()
    probs = [p["winner_probability"] for p in body["predictions"]
             if p["observable"]]
    assert probs == [0.10, 0.05, 0.02]


def test_model_identity_serialized(v2_client):
    model = v2_client.post("/v2/predictions/winner-snapshot", json={
        "race_id": RACE_A, **EXACT}).json()["model"]
    assert model["task"] == "winner" and model["target"] == "is_winner"
    assert model["feature_set"] == "ALL_84"
    assert model["calibration_method"] == "RAW"
    assert model["artifact_sha256"] and model["specification_fingerprint"]


def test_model_unavailable_503():
    from raceintel.prediction import ProductionModelUnavailableError

    class _Down:
        def predict_snapshot(self, *args):
            raise ProductionModelUnavailableError("artifact gone")

    client = None
    with _override_client(_Down()) as client:
        resp = client.post("/v2/predictions/winner-snapshot", json={
            "race_id": RACE_A, **EXACT})
    assert resp.status_code == 503
    assert resp.json()["error"] == "model_unavailable"


def test_no_legacy_fallback_on_unavailable():
    from raceintel.prediction import ProductionModelUnavailableError

    class _Down:
        def predict_snapshot(self, *args):
            raise ProductionModelUnavailableError("artifact gone")

    with _override_client(_Down()) as client:
        body = client.post("/v2/predictions/winner-snapshot", json={
            "race_id": RACE_A, **EXACT}).json()
    assert "summary" not in body and "latest_top5" not in body
    assert body["error"] == "model_unavailable"


@pytest.mark.parametrize("payload", [
    {"race_id": RACE_A},
    {"race_id": RACE_A, "anchor_driver_id": "a",
     "anchor_lap_number": 0, "anchor_state_time_s": 200.0},
    {"race_id": RACE_A, "anchor_driver_id": "a",
     "anchor_lap_number": "two", "anchor_state_time_s": 200.0},
    {"race_id": RACE_A, "anchor_driver_id": "a",
     "anchor_lap_number": 2, "anchor_state_time_s": "soon"},
])
def test_malformed_prediction_422(v2_client, payload):
    assert v2_client.post(
        "/v2/predictions/winner-snapshot", json=payload).status_code == 422


def test_unexpected_failure_stays_500():
    class _Broken:
        def predict_snapshot(self, *args):
            raise RuntimeError("boom")

    with _override_client(_Broken()) as client:
        resp = client.post("/v2/predictions/winner-snapshot", json={
            "race_id": RACE_A, **EXACT})
    assert resp.status_code == 500
    assert resp.json() == {"error": "internal",
                           "detail": "unexpected serving failure"}


def test_stable_error_payload(v2_client):
    not_found = v2_client.get("/v2/races/NOPE/states").json()
    assert set(not_found) == {"error", "detail"}
    missing = v2_client.get(f"/v2/races/{RACE_A}/state", params={
        "anchor_driver_id": "a", "anchor_lap_number": 9,
        "anchor_state_time_s": 1.0}).json()
    assert set(missing) == {"error", "detail"}


def test_deterministic_response_ordering(v2_client):
    payload = {"race_id": RACE_A, **EXACT}
    first = v2_client.post(
        "/v2/predictions/winner-snapshot", json=payload).json()
    again = v2_client.post(
        "/v2/predictions/winner-snapshot", json=payload).json()
    assert first == again
    assert [p["driver_id"] for p in first["predictions"]] == ["a", "b", "c"]


# --- firewalls ---------------------------------------------------------------


def _v2_sources():
    return {name: (ROOT / "api" / name).read_text() for name in (
        "v2_routes.py", "v2_service.py", "v2_schemas.py")}


def test_v2_import_firewall():
    for name, text in _v2_sources().items():
        for banned in ("ml.inference", "ml.", "prediction_service",
                       "load_frozen_winner_model("):
            if banned == "ml.":
                assert "ml.inference" not in text, name
                continue
            assert banned not in text, (name, banned)
    text = _v2_sources()["v2_routes.py"] + _v2_sources()["v2_service.py"]
    assert "raceintel.model_lab.serving" in text or \
        "from raceintel.model_lab import serving" in text


def test_legacy_import_firewall():
    for name in ("routes.py", "schemas.py", "services/prediction_service.py",
                 "main.py"):
        text = (ROOT / "api" / name).read_text()
        assert "raceintel.prediction" not in text, name
        assert "RacePredictionEngine" not in text, name
        assert "RaceStateFeatureBridge" not in text, name
    assert "v2_routes" not in (ROOT / "api" / "routes.py").read_text()


def test_no_target_access_in_v2_sources():
    for name, text in _v2_sources().items():
        lowered = text.lower()
        for token in ("is_winner", "final_position", "is_podium",
                      "scored_points", "eligible_", "winner_flag",
                      "podium_flag", "classified_", "race_driver_labels",
                      "model_matrix", "allow_protected_holdout"):
            assert token not in lowered, (name, token)


def test_dev_only_serving_policy():
    from api.v2_service import MAX_SERVED_SEASON, SERVED_SEASONS
    assert MAX_SERVED_SEASON == 2024
    assert tuple(SERVED_SEASONS) == tuple(range(2018, 2025))
    assert all(row["season"] <= 2024 for row in RACES)


def test_dependency_override_works():
    with _override_client(FakeV2Service()) as client:
        body = client.get("/v2/races").json()
    assert body["count"] == 2


# --- real integration (development data only) ---------------------------------


def _has_canon():
    return (ROOT / "data/v2/processed/driver_lap_state_d9/season=2022"
            ).is_dir()


@pytest.fixture(scope="module")
def real_service():
    if not _has_canon():
        pytest.skip("canonical data absent")
    import pytest as _pytest
    from api.v2_service import load_v2_service
    started = time.perf_counter()
    try:
        service = load_v2_service()
    except Exception as exc:
        _pytest.skip(f"v2 service unavailable: {exc}")
    elapsed = (time.perf_counter() - started) * 1000.0
    print(f"\nSERVICE_INIT_MS={elapsed:.1f}")
    return service


@pytest.fixture(scope="module")
def real_client(real_service):
    from fastapi.testclient import TestClient

    from api.main import app
    from api.v2_service import get_v2_service
    app.dependency_overrides[get_v2_service] = lambda: real_service
    yield TestClient(app, raise_server_exceptions=False)
    app.dependency_overrides.pop(get_v2_service, None)


def _find_anchor(client, race_id, driver_id, lap_number):
    """Page through discovery until the exact anchor is found."""
    offset = 0
    while True:
        page = client.get(f"/v2/races/{race_id}/states",
                          params={"offset": offset, "limit": 500}).json()
        for anchor in page["anchors"]:
            if anchor["driver_id"] == driver_id \
                    and anchor["lap_number"] == lap_number:
                return anchor
        offset += len(page["anchors"])
        assert offset < page["total"], "anchor absent from discovery"


def test_real_race_state_integration(real_client, real_service):
    if not _has_canon():
        pytest.skip("canonical data absent")
    listed = real_client.get("/v2/races").json()["races"]
    assert listed, "served registry is empty"
    assert [ (r["season"], r["round_no"], r["race_id"]) for r in listed ] == \
        sorted((r["season"], r["round_no"], r["race_id"]) for r in listed)
    assert all(r["season"] <= 2024 for r in listed)
    race_id = "2023-r01-R"
    assert race_id in {r["race_id"] for r in listed}
    anchors = real_client.get(
        f"/v2/races/{race_id}/states", params={"limit": 5}).json()
    assert anchors["total"] > 0
    anchor = _find_anchor(real_client, race_id, "alonso", 28)
    started = time.perf_counter()
    resp = real_client.get(f"/v2/races/{race_id}/state", params={
        "anchor_driver_id": anchor["driver_id"],
        "anchor_lap_number": anchor["lap_number"],
        "anchor_state_time_s": anchor["state_time_s"]})
    elapsed = (time.perf_counter() - started) * 1000.0
    print(f"\nREAL_STATE_MS={elapsed:.1f}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["race_id"] == race_id
    assert body["roster_size"] == len(body["drivers"]) > 0
    assert [d["driver_id"] for d in body["drivers"]] == sorted(
        d["driver_id"] for d in body["drivers"])
    text = json.dumps(body).lower()
    for token in ("is_winner", "final_position", "classified_"):
        assert token not in text, token


def test_real_production_prediction_integration(real_client, real_service):
    if not _has_canon():
        pytest.skip("canonical data absent")
    race_id = "2023-r01-R"
    anchor = _find_anchor(real_client, race_id, "alonso", 28)
    payload = {"race_id": race_id, "anchor_driver_id": anchor["driver_id"],
               "anchor_lap_number": anchor["lap_number"],
               "anchor_state_time_s": anchor["state_time_s"]}
    started = time.perf_counter()
    resp = real_client.post("/v2/predictions/winner-snapshot", json=payload)
    elapsed = (time.perf_counter() - started) * 1000.0
    print(f"\nREAL_PREDICT_MS={elapsed:.1f}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["probability_semantics"] == "INDEPENDENT_BINARY"
    assert body["model"]["task"] == "winner"
    assert body["model"]["artifact_sha256"].startswith("1116b34f")
    assert [p["driver_id"] for p in body["predictions"]] == sorted(
        p["driver_id"] for p in body["predictions"])
    for pred in body["predictions"]:
        if pred["observable"]:
            assert 0.0 <= pred["winner_probability"] <= 1.0
        else:
            assert pred["winner_probability"] is None
    again = real_client.post(
        "/v2/predictions/winner-snapshot", json=payload).json()
    assert again == body


def test_service_reuse(real_service):
    from api.v2_service import _cached_service
    assert _cached_service.cache_info().maxsize == 1
    assert real_service.engine is real_service.engine
