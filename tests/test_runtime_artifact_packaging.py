"""Focused P10-1A tests for scripts/prepare_runtime_artifacts.py.

Synthetic fixtures only (tmp dirs). Never touches the real 56 MB replay
cache, real corpus, or any scientific builder.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / \
    "prepare_runtime_artifacts.py"


def load_module():
    spec = importlib.util.spec_from_file_location(
        "prepare_runtime_artifacts", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture()
def mod():
    return load_module()


def _sha_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write(path: Path, data: bytes) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture()
def fixture_root(tmp_path, monkeypatch):
    """Minimal valid source tree with synthetic identities patched in."""
    mod = load_module()
    root = tmp_path / "proj"
    (root / "v2").mkdir(parents=True)
    (root / "data").mkdir(parents=True)

    model_bytes = b"frozen-model-bytes"
    _write(root / mod.SERVING_MODEL_REL, model_bytes)
    monkeypatch.setattr(mod, "SERVING_MODEL_SHA256", _sha_bytes(model_bytes))

    explain_doc = {
        "canonical_feature_count": 84,
        "transformed_feature_count": 106,
        "probability_semantics": "INDEPENDENT_BINARY",
        "model_identity": {
            "serving_artifact_sha256": _sha_bytes(model_bytes),
        },
    }
    explain_bytes = json.dumps(explain_doc).encode()
    _write(root / mod.EXPLAIN_REL, explain_bytes)
    monkeypatch.setattr(mod, "EXPLAIN_SHA256", _sha_bytes(explain_bytes))
    _write(root / mod.EXPLAIN_SIDECAR_REL,
           (_sha_bytes(explain_bytes) + "\n").encode())

    races = [
        {"race_id": "2018-r01-R", "checkpoint_count": 2},
        {"race_id": "2018-r02-R", "checkpoint_count": 1},
    ]
    replay_doc = {
        "manifest_version": "phase8-e2-cache-manifest-v1",
        "race_count": 2,
        "checkpoint_count": 3,
        "aggregate_corpus_sha256": "agg",
        "matrix_sha256": "mat",
        "phase2_content_hash": "ph2",
        "model_identity": {
            "artifact_sha256": _sha_bytes(model_bytes),
            "feature_count": 84,
            "transformed_dim": 106,
            "probability_semantics": "INDEPENDENT_BINARY",
        },
        "races": races,
    }
    replay_bytes = json.dumps(replay_doc).encode()
    _write(root / mod.REPLAY_MANIFEST_REL, replay_bytes)
    for race in races:
        _write(root / mod.REPLAY_CHECKPOINTS_REL /
               f"{race['race_id']}.json", b'{"frames": []}')
    monkeypatch.setattr(mod, "REPLAY_RACE_COUNT", 2)
    monkeypatch.setattr(mod, "REPLAY_CHECKPOINT_COUNT", 3)
    monkeypatch.setattr(mod, "REPLAY_AGGREGATE_CORPUS_SHA256", "agg")
    monkeypatch.setattr(mod, "REPLAY_MATRIX_SHA256", "mat")
    monkeypatch.setattr(mod, "REPLAY_PHASE2_CONTENT_HASH", "ph2")

    sim_doc = {
        "parameter_contract_version": "r3-v1",
        "through_season": 2024,
        "scientific_hash": "simhash",
        "parameter_set_id": "phase6-r3-empirical",
        "estimation_seasons": list(range(2018, 2025)),
    }
    sim_bytes = json.dumps(sim_doc).encode()
    _write(root / mod.SIM_MANIFEST_REL, sim_bytes)
    monkeypatch.setattr(mod, "SIM_SCIENTIFIC_HASH", "simhash")

    for entity in mod.REQUIRED_PROCESSED_ENTITIES:
        _write(root / "data" / "v2" / "processed" / entity /
               "season=2024" / "part.parquet", b"PAR1-fake")
    matrix_doc = {"content_hash": "mx",
                  "label_join": {"feature_rows": 7}}
    _write(root / mod.MATRIX_MANIFEST_REL, json.dumps(matrix_doc).encode())
    monkeypatch.setattr(mod, "MATRIX_CONTENT_HASH", "mx")
    monkeypatch.setattr(mod, "MATRIX_FEATURE_ROWS", 7)
    return root, mod


def _stage(root: Path, mod, name="runtime_artifacts") -> Path:
    staging = root / name
    result = mod.package(root, mod.resolve_staging(root, str(staging)))
    assert result["manifest_version"] == mod.MANIFEST_VERSION
    return staging


def test_valid_bundle_packages_and_validates(fixture_root):
    root, mod = fixture_root
    staging = _stage(root, mod)
    manifest = mod.validate_staged(root, staging)
    assert manifest["file_count"] > 0
    assert manifest["serving_scope"]["served_races"] == 2


def test_missing_required_artifact_fails(fixture_root):
    root, mod = fixture_root
    (root / mod.REPLAY_CHECKPOINTS_REL / "2018-r02-R.json").unlink()
    with pytest.raises(mod.ArtifactContractError):
        mod.package(root, mod.resolve_staging(root, str(root / "out")))


def test_wrong_serving_model_identity_fails(fixture_root):
    root, mod = fixture_root
    _write(root / mod.SERVING_MODEL_REL, b"tampered")
    with pytest.raises(mod.ArtifactContractError):
        mod.package(root, mod.resolve_staging(root, str(root / "out")))


def test_wrong_replay_scope_fails(fixture_root):
    root, mod = fixture_root
    doc = json.loads((root / mod.REPLAY_MANIFEST_REL).read_text())
    doc["race_count"] = 99
    (root / mod.REPLAY_MANIFEST_REL).write_text(json.dumps(doc))
    with pytest.raises(mod.ArtifactContractError):
        mod.package(root, mod.resolve_staging(root, str(root / "out")))


def test_wrong_explainability_sha_fails(fixture_root):
    root, mod = fixture_root
    with (root / mod.EXPLAIN_REL).open("ab") as handle:
        handle.write(b" ")
    with pytest.raises(mod.ArtifactContractError):
        mod.package(root, mod.resolve_staging(root, str(root / "out")))


def test_forbidden_and_absolute_paths_fail(fixture_root):
    root, mod = fixture_root
    with pytest.raises(mod.ArtifactContractError):
        mod._assert_safe_rel("data/raw/fastf1_cache/x.parquet")
    with pytest.raises(mod.ArtifactContractError):
        mod._assert_safe_rel("/Users/someone/abs.parquet")
    with pytest.raises(mod.ArtifactContractError):
        mod._assert_safe_rel("../escape.parquet")
    staging = _stage(root, mod)
    manifest_path = staging / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    manifest["files"].append(
        {"path": "/abs/evil.parquet", "sha256": "0" * 64, "size": 1})
    manifest_path.write_text(json.dumps(manifest))
    with pytest.raises(mod.ArtifactContractError):
        mod.validate_staged(root, staging)


def test_symlink_escape_fails(fixture_root):
    root, mod = fixture_root
    outside = root.parent / "outside.txt"
    outside.write_text("secret")
    link = (root / "data" / "v2" / "processed" / "results" /
            "season=2024" / "evil.parquet")
    link.symlink_to(outside)
    with pytest.raises(mod.ArtifactContractError):
        mod.collect_staged_paths(root)
    link.unlink()
    staging = _stage(root, mod)
    (staging / "data" / "v2" / "processed" / "results" /
     "season=2024" / "link.parquet").symlink_to(outside)
    with pytest.raises(mod.ArtifactContractError):
        mod.validate_staged(root, staging)


def test_manifest_deterministic(fixture_root):
    root, mod = fixture_root
    first = _stage(root, mod, name="bundle_a")
    second = _stage(root, mod, name="bundle_b")
    assert (first / "manifest.json").read_bytes() == \
        (second / "manifest.json").read_bytes()


def test_safe_staging_replacement(fixture_root):
    root, mod = fixture_root
    staging = root / "runtime_artifacts"
    staging.mkdir()
    (staging / "stale-marker.txt").write_text("stale")
    canonical = root / mod.EXPLAIN_REL
    before = hashlib.sha256(canonical.read_bytes()).hexdigest()
    _stage(root, mod)
    assert not (staging / "stale-marker.txt").exists()
    assert (staging / "manifest.json").is_file()
    assert hashlib.sha256(canonical.read_bytes()).hexdigest() == before
    assert not (root / "runtime_artifacts.tmp").exists()


def test_staging_guards(fixture_root):
    root, mod = fixture_root
    with pytest.raises(mod.ArtifactContractError):
        mod.resolve_staging(root, str(root))
    with pytest.raises(mod.ArtifactContractError):
        mod.resolve_staging(root, str(root.parent / "elsewhere"))
    with pytest.raises(mod.ArtifactContractError):
        mod.resolve_staging(root, str(root / "data" / "nested"))


def test_validate_only_mode(fixture_root):
    root, mod = fixture_root
    staging = _stage(root, mod)
    assert mod.main(["--root", str(root), "--staging", str(staging),
                     "--validate"]) == 0
    assert mod.main(["--root", str(root), "--staging",
                     str(root / "missing"), "--validate"]) == 2


def test_no_science_or_network_capability(mod):
    source = SCRIPT.read_text(encoding="utf-8")
    import_lines = [line.strip() for line in source.splitlines()
                    if line.strip().startswith(("import ", "from "))]
    joined_imports = "\n".join(import_lines)
    for forbidden in ("socket", "urllib", "subprocess", "requests",
                      "sklearn", "pandas", "numpy", "joblib", "fastapi",
                      "uvicorn", "fastf1", " v2", " api", " ml",
                      "urlopen", "urlretrieve"):
        assert forbidden not in joined_imports, (forbidden, import_lines)
    allowed = {"argparse", "hashlib", "json", "os", "shutil", "sys",
               "pathlib", "__future__"}
    imported = set()
    for line in import_lines:
        if line.startswith("import "):
            imported.add(line.split("import ")[1].split()[0].split(".")[0])
        else:
            imported.add(line.split("from ")[1].split()[0].split(".")[0])
    assert imported <= allowed, imported - allowed
