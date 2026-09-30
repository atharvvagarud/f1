"""P10-1D frontend-container contract (static; no Docker engine required).

Verifies Dockerfile.frontend + .dockerignore + next.config.ts against the
frozen P10-1B contracts without building an image. The real docker build +
served smoke evidence is authoritative; these tests guard the static surface.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile.frontend"
BACKEND_DOCKERFILE = REPO_ROOT / "Dockerfile.backend"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"
NEXT_CONFIG = REPO_ROOT / "frontend" / "next.config.ts"


@pytest.fixture(scope="module")
def dockerfile() -> str:
    return DOCKERFILE.read_text()


@pytest.fixture(scope="module")
def code_lines(dockerfile) -> list:
    """Non-comment, non-blank Dockerfile lines (comments may name things)."""
    out = []
    for ln in dockerfile.splitlines():
        stripped = ln.split("#", 1)[0].rstrip()
        if stripped.strip():
            out.append(stripped)
    return out


@pytest.fixture(scope="module")
def dockerignore() -> str:
    return DOCKERIGNORE.read_text()


def test_files_exist():
    assert DOCKERFILE.is_file()
    assert NEXT_CONFIG.is_file()


def test_node_22_base(code_lines):
    stages = re.findall(r"^FROM\s+(\S+)", "\n".join(code_lines), re.M)
    assert len(stages) >= 2, stages  # multi-stage: deps/builder/runner
    for image in stages:
        assert image.startswith("node:22"), image


def test_npm_ci_no_install(code_lines):
    code = "\n".join(code_lines)
    assert "npm ci" in code
    for ln in code_lines:
        if "npm install" in ln:
            assert "npm ci" in ln, ln
    assert "package-lock.json" in code
    assert "npm update" not in code and "npm upgrade" not in code


def test_only_frontend_manifests_copied(code_lines):
    code = "\n".join(code_lines)
    assert "frontend/package.json" in code
    assert "frontend/package-lock.json" in code
    assert "COPY package.json" not in code


def test_explicit_api_base_arg(code_lines):
    code = "\n".join(code_lines)
    assert re.search(r"^ARG\s+NEXT_PUBLIC_API_BASE\s*$", code, re.M), \
        "explicit build arg required"
    assert "ENV NEXT_PUBLIC_API_BASE" in code
    assert re.search(
        r'test -n "\$NEXT_PUBLIC_API_BASE"', code), \
        "missing-arg guard required"


def test_port_and_start(code_lines):
    code = "\n".join(code_lines)
    assert "EXPOSE 3000" in code
    assert "PORT=3000" in code
    assert "HOSTNAME=0.0.0.0" in code
    m = re.search(r"^CMD\s+(\[.*\])", code, re.M)
    assert m, "no exec-form CMD"
    assert "nginx" not in code.lower()


def test_non_root_runtime(code_lines):
    code = "\n".join(code_lines)
    m = re.search(r"^USER\s+(\S+)", code, re.M)
    assert m, "no USER directive"
    assert m.group(1) != "root"
    assert "chmod -R 777" not in code


def test_no_backend_science_copied(code_lines):
    code = "\n".join(code_lines)
    for token in ("COPY api/", "COPY ml/", "COPY v2/",
                  "COPY data/", "COPY results/",
                  "COPY runtime_artifacts", "requirements.txt"):
        assert token not in code, token


def test_no_local_env_copied(code_lines, dockerignore):
    code = "\n".join(code_lines)
    assert ".env.local" not in code
    assert "frontend/.env.local" in dockerignore


def test_dockerignore_keeps_frontend_source(dockerignore):
    lines = [ln.strip() for ln in dockerignore.splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    assert "frontend/" not in lines, "blanket frontend/ exclusion breaks build"
    assert "frontend/node_modules/" in dockerignore
    assert "frontend/.next/" in dockerignore
    # P10-1C backend contract intact (patterns, not comments).
    assert "data/*" in dockerignore
    assert ".fastf1_cache" in dockerignore
    assert not any(ln.strip() == "runtime_artifacts"
                   or ln.strip() == "runtime_artifacts/"
                   for ln in lines)


def test_standalone_contract(code_lines):
    code = "\n".join(code_lines)
    config = NEXT_CONFIG.read_text()
    if 'output: "standalone"' in config or "output: 'standalone'" in config:
        assert ".next/standalone" in code
        assert ".next/static" in code
        assert "server.js" in code


def test_backend_dockerfile_unchanged():
    blob = BACKEND_DOCKERFILE.read_text()
    assert "FROM python:3.11-slim" in blob
    assert "uvicorn" in blob and "api.main:app" in blob
    assert "COPY frontend" not in blob
    assert "NEXT_PUBLIC_API_BASE" not in blob


def test_scientific_firewall():
    blob = DOCKERFILE.read_text()
    for token in ("FastF1", "fastf1", "python", "pip install", ".joblib",
                  ".parquet", "2025"):
        assert token not in blob, token
