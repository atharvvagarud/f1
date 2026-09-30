"""P10-3 serving configuration + CORS contract (source-safe, no network).

Covers config parsing (defaults, multi-origin, whitespace, malformed,
wildcard policy, log levels) and live CORS behavior against test-built
apps (no env reloads, no canonical data needed).
"""

from __future__ import annotations

import pytest

from api.config import (
    DEFAULT_ALLOWED_ORIGINS,
    ServingConfig,
    get_serving_config,
    parse_allowed_origins,
    parse_log_level,
)


def test_default_origin_is_localhost():
    assert parse_allowed_origins(None) == ("http://localhost:3000",)
    assert parse_allowed_origins("") == ("http://localhost:3000",)
    assert parse_allowed_origins("   ") == ("http://localhost:3000",)
    assert DEFAULT_ALLOWED_ORIGINS == ("http://localhost:3000",)


def test_single_origin():
    assert parse_allowed_origins("http://localhost:3000") == (
        "http://localhost:3000",)


def test_multiple_origins_whitespace_and_empties():
    parsed = parse_allowed_origins(
        " http://localhost:3000 , ,https://example.invalid ,, ")
    assert parsed == ("http://localhost:3000", "https://example.invalid")


def test_scheme_host_port_preserved_verbatim():
    parsed = parse_allowed_origins("https://example.invalid:8443/app")
    assert parsed == ("https://example.invalid:8443/app",)


def test_set_but_empty_config_fails_closed():
    with pytest.raises(ValueError):
        parse_allowed_origins(",,,")
    with pytest.raises(ValueError):
        parse_allowed_origins(" , ")


def test_wildcard_absent_by_default_but_explicitly_allowed():
    assert "*" not in parse_allowed_origins(None)
    assert parse_allowed_origins("*") == ("*",)
    assert parse_allowed_origins(
        "http://localhost:3000, *") == ("http://localhost:3000", "*")


def test_log_levels():
    assert parse_log_level(None) == "INFO"
    assert parse_log_level("") == "INFO"
    for level in ("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"):
        assert parse_log_level(level) == level
        assert parse_log_level(level.lower()) == level
        assert parse_log_level(f"  {level}  ") == level


def test_invalid_log_level_fails_fast():
    for bad in ("VERBOSE", "infoo", "1", "DEBUG INFO"):
        with pytest.raises(ValueError):
            parse_log_level(bad)


def test_from_env_mapping():
    config = ServingConfig.from_env({
        "F1_ALLOWED_ORIGINS":
            "http://localhost:3000,https://example.invalid",
        "F1_LOG_LEVEL": "warning",
    })
    assert config.allowed_origins == (
        "http://localhost:3000", "https://example.invalid")
    assert config.log_level == "WARNING"


def test_from_env_defaults_and_immutability():
    config = get_serving_config(env={})
    assert config.allowed_origins == DEFAULT_ALLOWED_ORIGINS
    assert config.log_level == "INFO"
    with pytest.raises(Exception):
        config.log_level = "DEBUG"  # frozen dataclass


# --- live CORS behavior (test-built apps; /health needs no data) ---

def _client_for(*origins, log_level="INFO"):
    from fastapi.testclient import TestClient

    from api.main import create_app

    app = create_app(ServingConfig(
        allowed_origins=tuple(origins), log_level=log_level))
    return TestClient(app, raise_server_exceptions=False)


def test_allowed_local_origin_succeeds():
    client = _client_for("http://localhost:3000")
    resp = client.get(
        "/health", headers={"Origin": "http://localhost:3000"})
    assert resp.status_code == 200
    assert (resp.headers.get("access-control-allow-origin")
            == "http://localhost:3000")


def test_unknown_origin_not_allowed():
    client = _client_for("http://localhost:3000")
    resp = client.get("/health", headers={"Origin": "http://evil.invalid"})
    assert resp.status_code == 200
    assert "access-control-allow-origin" not in resp.headers


def test_preflight_allows_configured_origin():
    client = _client_for("http://localhost:3000")
    resp = client.options(
        "/v2/predictions/winner-snapshot",
        headers={"Origin": "http://localhost:3000",
                 "Access-Control-Request-Method": "POST"})
    assert resp.status_code == 200
    assert (resp.headers.get("access-control-allow-origin")
            == "http://localhost:3000")


def test_multiple_configured_origins():
    client = _client_for("http://localhost:3000", "https://example.invalid")
    for origin in ("http://localhost:3000", "https://example.invalid"):
        resp = client.get("/health", headers={"Origin": origin})
        assert resp.headers.get("access-control-allow-origin") == origin
    resp = client.get("/health", headers={"Origin": "http://other.invalid"})
    assert "access-control-allow-origin" not in resp.headers


def test_no_credentialed_sessions():
    client = _client_for("http://localhost:3000")
    resp = client.options(
        "/v2/predictions/winner-snapshot",
        headers={"Origin": "http://localhost:3000",
                 "Access-Control-Request-Method": "POST"})
    assert resp.headers.get("access-control-allow-credentials") != "true"


def test_default_app_has_no_wildcard():
    from api.main import create_app

    config = get_serving_config(env={})
    app = create_app(config)
    cors = [m for m in app.user_middleware
            if m.cls.__name__ == "CORSMiddleware"]
    assert cors, "CORSMiddleware must remain configured"
    assert cors[0].kwargs.get("allow_origins") == ["http://localhost:3000"]
    assert cors[0].kwargs.get("allow_credentials") is False
