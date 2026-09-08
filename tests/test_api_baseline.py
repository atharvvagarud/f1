"""A. API baseline — the four-route contract the frontend depends on.

Covers: GET /health, GET /races, POST /predict/ensemble,
POST /predict/single-model, plus probability bounds on live responses.
Uses only races with no known serialization defect.
"""

import pytest

from conftest import HTTP_CLEAN_RACES


def test_health(api_client):
    resp = api_client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


def test_races_inventory(api_client):
    resp = api_client.get("/races")
    assert resp.status_code == 200
    races = resp.json()["races"]
    assert len(races) == 104  # R0 baseline: 104 races, 2019-2023
    for row in races:
        assert isinstance(row["year"], int)
        assert isinstance(row["event_name"], str) and row["event_name"]
    years = sorted({r["year"] for r in races})
    assert years == [2019, 2020, 2021, 2022, 2023]
    keys = [(r["year"], r["event_name"]) for r in races]
    assert keys == sorted(keys)  # sorted by (year, event_name)


@pytest.mark.parametrize("year,event", HTTP_CLEAN_RACES)
def test_ensemble_response_shape(api_client, year, event):
    resp = api_client.post("/predict/ensemble", json={"year": year, "event": event})
    assert resp.status_code == 200
    body = resp.json()
    for key in (
        "summary",
        "latest_lap",
        "final_winner",
        "decision_reason",
        "actual_winner",
        "agreement_count",
        "confidence_value",
        "confidence_label",
        "latest_top5",
    ):
        assert key in body, f"missing key {key}"
    assert body["latest_lap"] == 25
    assert len(body["summary"]) == 15  # 5 checkpoints x 3 models
    assert set(body["latest_top5"]) == {
        "Logistic Regression",
        "HistGradientBoosting",
        "XGBoost",
    }
    for row in body["summary"]:
        assert 0.0 <= row["win_probability"] <= 1.0
    assert 0.0 <= body["confidence_value"] <= 1.0


@pytest.mark.parametrize("model", ["logreg", "hgb", "xgboost"])
def test_single_model_response_shape(api_client, model):
    resp = api_client.post(
        "/predict/single-model",
        json={"year": 2023, "event": "Bahrain Grand Prix", "model": model},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "summary" in body and "latest" in body
    assert len(body["summary"]) == 5  # one row per checkpoint
    assert [r["lap"] for r in body["summary"]] == [5, 10, 15, 20, 25]
    assert body["latest"]["lap"] == 25
    for row in body["summary"]:
        assert 0.0 <= row["win_probability"] <= 1.0
    assert 0.0 <= body["latest"]["predicted_win_probability"] <= 1.0


def test_unknown_race_returns_error(api_client):
    # Characterises current behaviour for a race absent from the datasets:
    # the ValueError propagates unhandled, so both endpoints return 500.
    for payload in (
        {"year": 1999, "event": "No Such Prix"},
    ):
        resp = api_client.post("/predict/ensemble", json=payload)
        assert resp.status_code == 500
        resp = api_client.post(
            "/predict/single-model", json={**payload, "model": "xgboost"}
        )
        assert resp.status_code == 500
