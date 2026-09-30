"""P10-1F production-reproducibility contract (static; no engine needed).

Pins cross-stage invariants no earlier P10 test covers: version
declarations agree, Make build chains gate correctly, and the compose
image references resolve to present Dockerfiles.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]


def _non_comment(path: Path) -> str:
    out = []
    for ln in path.read_text().splitlines():
        stripped = ln.split("#", 1)[0].rstrip()
        if stripped.strip():
            out.append(stripped)
    return "\n".join(out) + "\n"


@pytest.fixture(scope="module")
def makefile() -> str:
    return _non_comment(REPO_ROOT / "Makefile")


def test_python_versions_agree():
    declared = (REPO_ROOT / ".python-version").read_text().strip()
    assert declared.startswith("3.11"), declared
    backend = _non_comment(REPO_ROOT / "Dockerfile.backend")
    m = re.search(r"^FROM\s+python:(\d+\.\d+)", backend, re.M)
    assert m and m.group(1) == "3.11", m


def test_node_versions_agree():
    nvmrc = (REPO_ROOT / "frontend" / ".nvmrc").read_text().strip()
    assert nvmrc == "22", nvmrc
    frontend = _non_comment(REPO_ROOT / "Dockerfile.frontend")
    stages = re.findall(r"^FROM\s+node:(\d+)", frontend, re.M)
    assert stages and all(v == "22" for v in stages), stages


def test_compose_build_targets_gate_preflight(makefile):
    backend = re.search(
        r"^docker-backend-build:(.*?)(?=^\S|\Z)", makefile, re.M | re.S)
    compose = re.search(
        r"^docker-compose-build:(.*?)(?=^\S|\Z)", makefile, re.M | re.S)
    assert backend and "preflight" in backend.group(1).splitlines()[0]
    assert compose and "preflight" in compose.group(1).splitlines()[0]


def test_frontend_build_target_requires_api_base(makefile):
    block = re.search(
        r"^docker-frontend-build:(.*?)(?=^\S|\Z)", makefile, re.M | re.S)
    assert block, "missing docker-frontend-build"
    assert "NEXT_PUBLIC_API_BASE" in block.group(1)


def test_compose_dockerfiles_exist():
    compose = _non_comment(REPO_ROOT / "compose.yaml")
    files = re.findall(r"dockerfile:\s+(\S+)", compose)
    assert sorted(files) == ["Dockerfile.backend", "Dockerfile.frontend"]
    for f in files:
        assert (REPO_ROOT / f).is_file()


def test_runtime_bundle_survives_ignore():
    import subprocess
    res = subprocess.run(
        ["git", "check-ignore", "runtime_artifacts/manifest.json"],
        capture_output=True, text=True, cwd=REPO_ROOT)
    assert res.returncode == 0, "bundle must stay ignored (uncommitted)"
    dockerignore = _non_comment(REPO_ROOT / ".dockerignore")
    assert not any(
        ln.strip() in ("runtime_artifacts", "runtime_artifacts/")
        for ln in dockerignore.splitlines())
