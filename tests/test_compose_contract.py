"""P10-1E compose contract (static; no Docker engine required).

Parses compose.yaml with stdlib-only line scanning (no YAML dependency).
The live `docker compose config/up` evidence is authoritative; these tests
guard the static surface.
"""

from __future__ import annotations

from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
COMPOSE = REPO_ROOT / "compose.yaml"
BACKEND_DOCKERFILE = REPO_ROOT / "Dockerfile.backend"
FRONTEND_DOCKERFILE = REPO_ROOT / "Dockerfile.frontend"


@pytest.fixture(scope="module")
def text() -> str:
    """Non-comment compose content (comments document intent, incl.
    forbidden words like database/readiness/backend-DNS)."""
    out = []
    for ln in COMPOSE.read_text().splitlines():
        stripped = ln.split("#", 1)[0].rstrip()
        if stripped.strip():
            out.append(stripped)
    return "\n".join(out) + "\n"


@pytest.fixture(scope="module")
def lines(text) -> list:
    return [ln.rstrip() for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith("#")]


def test_compose_file_exists():
    assert COMPOSE.is_file()


def test_exactly_two_services(lines):
    svc = [ln for ln in lines if ln.startswith("  ")
           and not ln.startswith("   ") and ln.rstrip().endswith(":")]
    body = "\n".join(lines)
    assert "services:" in body
    names = [ln.strip().rstrip(":") for ln in svc]
    assert sorted(names) == ["backend", "frontend"], names


def test_no_extra_services(text):
    for token in ("postgres", "redis", "kafka", "celery", "worker",
                  "nginx", "traefik", "prometheus", "grafana",
                  "otel", "mlflow", "db:", "database"):
        assert token not in text.lower(), token


def test_correct_dockerfiles(text):
    assert "dockerfile: Dockerfile.backend" in text
    assert "dockerfile: Dockerfile.frontend" in text


def test_ports(text):
    assert '"8000:8000"' in text or "'8000:8000'" in text or "8000:8000" in text
    assert "3000:3000" in text


def test_frontend_api_base(text):
    assert "NEXT_PUBLIC_API_BASE: http://localhost:8000" in text
    assert "http://backend:8000" not in text


def test_network_ingestion_off(text):
    assert "V2_ALLOW_NETWORK" not in text
    assert "V2_PROJECT_ROOT: /app" in text or "V2_PROJECT_ROOT=/app" in text


def test_no_volumes_or_mounts(text):
    low = text.lower()
    assert "volumes:" not in low
    assert "bind" not in low
    assert "mount" not in low


def test_read_only_tmpfs(text):
    assert text.count("read_only: true") == 2, "both services read-only"
    assert text.count("- /tmp") >= 2, "both services need /tmp tmpfs"


def test_commands_dockerfile_owned(text):
    assert "command:" not in text.lower()


def test_healthcheck_is_deployability_readiness(text):
    assert "/ready" in text
    assert "service_healthy" in text


def test_backend_serving_config_explicit(text):
    assert "F1_ALLOWED_ORIGINS: http://localhost:3000" in text
    assert "F1_LOG_LEVEL: INFO" in text


def test_dockerfiles_intact():
    backend = BACKEND_DOCKERFILE.read_text()
    frontend = FRONTEND_DOCKERFILE.read_text()
    assert "FROM python:3.11-slim" in backend
    assert 'api.main:app' in backend
    assert "node:22" in frontend
    assert "ARG NEXT_PUBLIC_API_BASE" in frontend
    assert "server.js" in frontend


def test_scientific_firewall():
    blob = COMPOSE.read_text()
    for token in ("fastf1", "FastF1", "training", "materialize",
                  "backfill", "2025", "retrain", "fit "):
        assert token not in blob, token
