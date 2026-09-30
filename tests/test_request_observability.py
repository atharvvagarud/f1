"""P10-3 request observability contract (source-safe, no network).

Verifies the structured request log: method/path/status/duration present,
query strings and bodies absent, 4xx at INFO, 5xx at ERROR, log-level
behavior. Timing assertions are non-brittle (numeric, nonnegative).
"""

from __future__ import annotations

import json
import logging

import pytest

from api.config import ServingConfig
from api.observability import LOGGER_NAME, RequestLoggingMiddleware


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from api.main import create_app

    app = create_app(ServingConfig(
        allowed_origins=("http://localhost:3000",), log_level="INFO"))
    return TestClient(app, raise_server_exceptions=False)


def _records(caplog):
    return [r for r in caplog.records if r.name == LOGGER_NAME]


def _payloads(caplog):
    return [json.loads(r.getMessage()) for r in _records(caplog)]


def test_successful_request_log(client, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        resp = client.get("/health")
    assert resp.status_code == 200
    payloads = _payloads(caplog)
    assert payloads, "expected a request record"
    record = payloads[-1]
    assert record["event"] == "request_complete"
    assert record["method"] == "GET"
    assert record["path"] == "/health"
    assert record["status"] == 200
    assert isinstance(record["duration_ms"], (int, float))
    assert record["duration_ms"] >= 0
    assert set(record) == {
        "event", "method", "path", "status", "duration_ms"}


def test_query_string_never_logged(client, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        resp = client.get("/health?foo=bar&token=secret-value-xyz")
    assert resp.status_code == 200
    raw = "\n".join(r.getMessage() for r in _records(caplog))
    assert "foo=bar" not in raw
    assert "secret-value-xyz" not in raw
    assert _payloads(caplog)[-1]["path"] == "/health"


def test_request_body_never_logged(client, caplog):
    marker = "BODY-MARKER-9f8e7d6c5b4a"
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        resp = client.post(
            "/v2/predictions/winner-snapshot", json={"marker": marker})
    assert resp.status_code in (404, 422)
    raw = "\n".join(r.getMessage() for r in _records(caplog))
    assert marker not in raw
    assert _payloads(caplog)[-1]["status"] == resp.status_code


def test_response_body_never_logged(client, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        resp = client.get("/health")
    body = resp.text
    assert body  # sanity: the body is non-empty
    for payload in _payloads(caplog):
        assert set(payload) == {
            "event", "method", "path", "status", "duration_ms"}


def test_404_is_info_not_error(client, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        resp = client.get("/no-such-route-xyz")
    assert resp.status_code == 404
    payloads = _payloads(caplog)
    assert payloads[-1]["status"] == 404
    assert _records(caplog)[-1].levelname == "INFO"
    assert not [r for r in _records(caplog) if r.levelname == "ERROR"]


def test_422_is_info_not_error(client, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        resp = client.post("/v2/predictions/winner-snapshot", json={})
    assert resp.status_code == 422
    assert _payloads(caplog)[-1]["status"] == 422
    assert _records(caplog)[-1].levelname == "INFO"


def test_5xx_is_error(caplog):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.add_middleware(RequestLoggingMiddleware)

    @app.get("/boom")
    def boom():
        raise RuntimeError("unexpected-test-failure")

    test_client = TestClient(app, raise_server_exceptions=False)
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        resp = test_client.get("/boom")
    assert resp.status_code == 500
    errors = [r for r in _records(caplog) if r.levelname == "ERROR"]
    assert errors, "expected an ERROR record for the 5xx"
    payload = json.loads(errors[-1].getMessage())
    assert payload["status"] == 500
    assert payload["method"] == "GET"
    assert "unexpected-test-failure" not in errors[-1].getMessage()


def test_parametrized_route_prefers_template(client, caplog):
    with caplog.at_level(logging.INFO, logger=LOGGER_NAME):
        client.get("/v2/races/2023-r01-R/state",
                   params={"anchor_driver_id": "x",
                           "anchor_lap_number": 1,
                           "anchor_state_time_s": 1.0})
    last = _payloads(caplog)[-1]
    assert last["path"] == "/v2/races/{race_id}/state"
    assert "anchor_driver_id" not in json.dumps(last)


def test_log_level_suppresses_info(client, caplog):
    from api.observability import configure_logging

    configure_logging("ERROR")
    try:
        caplog.clear()
        client.get("/health")
        assert [r for r in _records(caplog)
                if r.levelname == "INFO"] == []
    finally:
        configure_logging("INFO")
