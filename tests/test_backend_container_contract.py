"""P10-1C backend-container contract (static; no Docker engine required).

Verifies Dockerfile.backend + .dockerignore against the frozen P10-1B
contracts without building an image. The real docker build + in-container
smoke evidence is authoritative; these tests guard the static surface.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
DOCKERFILE = REPO_ROOT / "Dockerfile.backend"
DOCKERIGNORE = REPO_ROOT / ".dockerignore"


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
    assert DOCKERIGNORE.is_file()


def test_base_python_family(dockerfile):
    m = re.search(r"^FROM\s+(\S+)", dockerfile, re.M)
    assert m, "no FROM line"
    assert m.group(1).startswith("python:3.11"), m.group(1)


def test_production_requirements_only(dockerfile, code_lines):
    code = "\n".join(code_lines)
    assert "requirements.txt" in code
    assert "requirements-test.txt" not in code
    assert "python -m pip install" in code
    for ln in code_lines:
        if "pip install" in ln:
            assert "python -m pip install" in ln, ln


def test_no_reload_correct_port_cmd(dockerfile, code_lines):
    code = "\n".join(code_lines)
    m = re.search(r"^CMD\s+(\[.*\])", code, re.M)
    assert m, "no exec-form CMD"
    assert "--reload" not in code
    for token in ("api.main:app", "--host", "0.0.0.0", "--port", "8000"):
        assert token in m.group(1), token


def test_runtime_env(code_lines):
    code = "\n".join(code_lines)
    assert "PYTHONDONTWRITEBYTECODE=1" in code
    assert "PYTHONUNBUFFERED=1" in code
    assert "V2_PROJECT_ROOT=/app" in code
    assert "V2_ALLOW_NETWORK" not in code


def test_non_root_user(code_lines):
    code = "\n".join(code_lines)
    assert re.search(r"^USER\s+\S+", code, re.M), "no USER directive"
    assert "root" not in re.search(
        r"^USER\s+(.+)$", code, re.M).group(1).lower()


def test_runtime_bundle_merged_no_staging_copy(code_lines):
    code = "\n".join(code_lines)
    assert "runtime_artifacts/data/" in code
    assert "runtime_artifacts/results/" in code
    assert "COPY runtime_artifacts " not in code.replace(
        "COPY runtime_artifacts/data/", "").replace(
        "COPY runtime_artifacts/results/", "")


def test_no_broad_repo_copy_before_deps(code_lines):
    lines = [ln.strip() for ln in code_lines if ln.strip().startswith("COPY")]
    copies = " ".join(lines)
    assert "COPY . " not in copies and "COPY ./ " not in copies
    assert lines.index(next(
        ln for ln in lines if "requirements.txt" in ln)) < lines.index(next(
        ln for ln in lines if ln.startswith("COPY api/")))


def test_serving_model_copied_once(code_lines):
    target = "results/v2_model_lab/winner_logreg_raw_v1_serving.joblib"
    assert target in "\n".join(code_lines)
    copies = [ln for ln in code_lines
              if ln.strip().startswith("COPY")
              and "winner_logreg_raw_v1_serving.joblib" in ln]
    assert len(copies) == 1


def test_dockerignore_keeps_bundle(dockerignore):
    for line in dockerignore.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#") \
                and not stripped.startswith("!"):
            assert "runtime_artifacts" not in stripped, stripped


def test_dockerignore_protects_raw_env_tooling(dockerignore):
    for pattern in ("data/*", ".fastf1_cache", "frontend/",
                    ".git/", ".env", "package-lock.json"):
        assert pattern in dockerignore, pattern
    assert "!data/processed/" in dockerignore
    assert "!data/interim/" in dockerignore
    assert "!results/models/" in dockerignore
    assert "!results/v2_model_lab/winner_logreg_raw_v1_serving.joblib" \
        in dockerignore
    assert "!docs/PHASE4_FREEZE_MANIFEST.json" in dockerignore
    assert "!docs/generated/phase2_freeze_manifest.json" in dockerignore
    assert "!scripts/replay_feature_matrix.py" in dockerignore


def test_scientific_firewall():
    sources = [DOCKERFILE.read_text()]
    makefile = (REPO_ROOT / "Makefile").read_text()
    docker_targets = "\n".join(
        ln for ln in makefile.splitlines()
        if "docker-backend" in ln or "docker build" in ln or "docker run" in ln)
    sources.append(docker_targets)
    blob = "\n".join(sources)
    for token in ("v2.d6", "v2.d7", "v2.d9", "build_matrix",
                  "materialize_serving_artifact",
                  "build_replay_prediction_cache",
                  "build_simulation_parameters", "FastF1", "fastf1",
                  "2025"):
        assert token not in blob, token
