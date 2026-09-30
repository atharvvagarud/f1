"""Focused P10-1B tests for scripts/check_runtime_environment.py.

Synthetic fixtures only (tmp dirs), except one cheap SHA read of the real
tracked serving model to guard the frozen identity constant. Never loads
the model, never runs inference, never touches datasets or builders.
"""

from __future__ import annotations

import hashlib
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / \
    "check_runtime_environment.py"
REPO_ROOT = Path(__file__).resolve().parents[1]

# Keep in sync with scripts/check_runtime_environment.py by reading it, not
# by duplicating the value here (except the real-SHA guard below, which is
# the point of that test).
BANNED_IMPORT_ROOTS = {
    "fastf1", "sklearn", "pandas", "numpy", "joblib", "v2", "api", "ml",
}
PY311 = (3, 11, 0, "final", 0)


def load_module():
    spec = importlib.util.spec_from_file_location(
        "check_runtime_environment", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mod():
    return load_module()


def _write(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture()
def source_root(mod, tmp_path, monkeypatch):
    """Minimal synthetic tree that passes SOURCE checks."""
    root = tmp_path / "proj"
    (root / "v2").mkdir(parents=True)
    (root / "data").mkdir(parents=True)
    model = _write(root / str(mod.SERVING_MODEL_REL), b"synthetic-model")
    monkeypatch.setattr(mod, "EXPECTED_SERVING_MODEL_SHA",
                        hashlib.sha256(b"synthetic-model").hexdigest())
    for rel in mod.PHASE9_EVIDENCE_RELS:
        _write(root / str(rel), b"{}")
    for rel in mod.V1_RESOURCE_RELS:
        (root / rel).mkdir(parents=True, exist_ok=True)
    for rel in mod.FRONTEND_MANIFEST_RELS:
        _write(root / str(rel), b"{}")
    return root


# --- Python version contract -------------------------------------------

def test_supported_python_311(mod):
    assert mod.check_python_version((3, 11, 0, "final", 0)) == []
    assert mod.check_python_version((3, 11, 15, "final", 0)) == []


def test_unsupported_python_rejected(mod):
    for version in [(3, 10, 0, "final", 0), (3, 12, 0, "final", 0),
                    (3, 14, 0, "final", 0), (2, 7, 0, "final", 0)]:
        errors = mod.check_python_version(version)
        assert len(errors) == 1
        assert "3.11" in errors[0]


def test_repo_python_declaration_pins_311():
    assert (REPO_ROOT / ".python-version").read_text().strip() == "3.11"


# --- SOURCE checks ------------------------------------------------------

def test_source_tree_passes_on_valid_fixture(mod, source_root):
    assert mod.check_source_tree(source_root) == []


def test_missing_model(mod, source_root):
    (source_root / str(mod.SERVING_MODEL_REL)).unlink()
    errors = mod.check_source_tree(source_root)
    assert any("serving model" in e for e in errors)


def test_wrong_model_sha(mod, source_root):
    (source_root / str(mod.SERVING_MODEL_REL)).write_bytes(b"tampered")
    errors = mod.check_source_tree(source_root)
    assert any("SHA mismatch" in e for e in errors)


def test_missing_phase9_evidence(mod, source_root):
    (source_root / str(mod.PHASE9_EVIDENCE_RELS[0])).unlink()
    errors = mod.check_source_tree(source_root)
    assert any("Phase-9" in e for e in errors)


def test_missing_v1_resource(mod, source_root):
    (source_root / str(mod.V1_RESOURCE_RELS[0])).rmdir()
    errors = mod.check_source_tree(source_root)
    assert any("V1 runtime resource" in e for e in errors)


def test_missing_frontend_manifest(mod, source_root):
    (source_root / str(mod.FRONTEND_MANIFEST_RELS[1])).unlink()
    errors = mod.check_source_tree(source_root)
    assert any("frontend manifest" in e for e in errors)


def test_frozen_model_sha_matches_real_artifact(mod):
    real = REPO_ROOT / str(mod.SERVING_MODEL_REL)
    assert real.is_file()
    assert hashlib.sha256(real.read_bytes()).hexdigest() == \
        mod.EXPECTED_SERVING_MODEL_SHA == \
        "1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4"


# --- SOURCE vs DEPLOYABLE distinction -----------------------------------

def test_source_passes_without_runtime_artifacts(mod, source_root):
    assert mod.check_source_tree(source_root) == []
    errors = mod.check_deployable_tree(source_root)
    assert any("runtime_artifacts" in e for e in errors)


def test_deployable_rejects_unknown_manifest_version(mod, source_root):
    staging = source_root / str(mod.RUNTIME_STAGING_REL)
    _write(staging / "manifest.json", b'{"manifest_version": "bogus"}')
    errors = mod.check_deployable_tree(source_root)
    assert any("manifest_version" in e for e in errors)


def test_validator_failure_propagates(mod, source_root):
    """Real P10-1A validator runs against the synthetic root and must fail
    there (empty staging), proving failures propagate instead of passing."""
    scripts = source_root / "scripts"
    scripts.mkdir(parents=True, exist_ok=True)
    (scripts / "prepare_runtime_artifacts.py").write_bytes(SCRIPT.with_name(
        "prepare_runtime_artifacts.py").read_bytes())
    errors = mod.run_artifact_validator(source_root)
    assert len(errors) == 1
    assert "validation failed" in errors[0]


def test_validator_missing_packager(mod, tmp_path):
    root = tmp_path / "empty"
    root.mkdir()
    errors = mod.run_artifact_validator(root)
    assert any("packager" in e for e in errors)


# --- Network-off serving contract ---------------------------------------

def test_network_posture_off_by_default(mod, monkeypatch):
    monkeypatch.delenv("V2_ALLOW_NETWORK", raising=False)
    assert mod.check_network_posture() == []


def test_network_posture_fails_deployable_when_enabled(
        mod, source_root, monkeypatch):
    monkeypatch.setenv("V2_ALLOW_NETWORK", "1")
    assert any("network-off" in e for e in mod.check_deployable_tree(
        source_root))
    # SOURCE mode does not gate on the env var (offline-CLI opt-in remains).
    assert mod.check_source_tree(source_root) == []


# --- main() entry --------------------------------------------------------

def test_main_source_ok(mod, source_root, monkeypatch, capsys):
    monkeypatch.setattr(sys, "version_info", PY311)
    assert mod.main(["--source", "--root", str(source_root)]) == 0
    assert "SOURCE OK" in capsys.readouterr().out


def test_main_source_fail(mod, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(sys, "version_info", PY311)
    root = tmp_path / "bare"
    root.mkdir()
    assert mod.main(["--source", "--root", str(root)]) == 1
    assert "SOURCE FAIL" in capsys.readouterr().out


def test_main_deployable_requires_staging(
        mod, source_root, monkeypatch, capsys):
    monkeypatch.setattr(sys, "version_info", PY311)
    monkeypatch.delenv("V2_ALLOW_NETWORK", raising=False)
    assert mod.main(["--root", str(source_root)]) == 1
    assert "DEPLOYABLE FAIL" in capsys.readouterr().out


def test_main_portable_across_cwd(mod, source_root, monkeypatch):
    """--root keeps checks independent of the caller's cwd."""
    monkeypatch.setattr(sys, "version_info", PY311)
    monkeypatch.chdir("/tmp")
    assert mod.main(["--source", "--root", str(source_root)]) == 0
    assert mod.default_root() == REPO_ROOT


# --- Node declarations ---------------------------------------------------

def test_node_declarations_pin_22():
    assert (REPO_ROOT / "frontend" / ".nvmrc").read_text().strip() == "22"
    import json
    manifest = json.loads(
        (REPO_ROOT / "frontend" / "package.json").read_text())
    node_range = manifest.get("engines", {}).get("node", "")
    assert node_range == ">=22 <23"


# --- Scientific firewall --------------------------------------------------

def test_preflight_imports_stdlib_only():
    allowed = {"argparse", "hashlib", "json", "os", "subprocess", "sys",
               "pathlib", "__future__"}
    for line in SCRIPT.read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith("import "):
            roots = [p.split(".")[0]
                     for p in stripped[len("import "):].split(",")]
            for name in roots:
                assert name.strip() in allowed, name
        elif stripped.startswith("from "):
            assert stripped.split()[1].split(".")[0] in allowed, stripped
    source = SCRIPT.read_text()
    for banned in BANNED_IMPORT_ROOTS:
        assert f"import {banned}" not in source
