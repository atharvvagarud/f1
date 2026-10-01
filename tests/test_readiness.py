"""P10-3 readiness contract (source-safe; canonical data never mutated).

Healthy-tree tests build synthetic roots in tmp dirs (dependency injection
via ``V2_PROJECT_ROOT`` + cache reset). The single live test against the
real tree is skip-guarded for source checkouts without the bundle.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from api import readiness as RD

REPO_ROOT = Path(__file__).resolve().parents[1]


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _build_healthy_tree(root: Path, model_bytes: bytes = b"frozen-model") -> str:
    """Create a synthetic deployable tree; return the model SHA."""
    model_sha = _sha(model_bytes)
    (root / "results" / "v2_model_lab").mkdir(parents=True)
    (root / "results" / "v2_model_lab"
     / "winner_logreg_raw_v1_serving.joblib").write_bytes(model_bytes)

    replay_dir = root / "results" / "v2_replay" / "checkpoints"
    replay_dir.mkdir(parents=True)
    (root / "results" / "v2_replay"
     / "phase8_e2_cache_manifest_v1.json").write_text(json.dumps({
        "manifest_version": "phase8-e2-cache-manifest-v1",
        "race_count": 149,
        "checkpoint_count": 9644,
        "model_identity": {"artifact_sha256": model_sha},
    }))

    explain_dir = root / "results" / "v2_explainability"
    explain_dir.mkdir(parents=True)
    payload = b'{"explanation": "frozen"}'
    (explain_dir / "global_winner_logreg_v1.json").write_bytes(payload)
    (explain_dir / "global_winner_logreg_v1.sha256").write_text(
        _sha(payload) + "\n")

    from raceintel.simulation import parameter_storage_dir
    sim_dir = parameter_storage_dir(root, 2024)
    sim_dir.mkdir(parents=True)
    (sim_dir / "manifest.json").write_text(json.dumps({
        "parameter_set_id": "phase6-r3-empirical",
        "through_season": 2024,
    }))

    for entity in ("driver_lap_state_d9", "results", "races"):
        for season in range(2018, 2025):
            part = root / "data" / "v2" / "processed" / entity / f"season={season}"
            part.mkdir(parents=True)
            (part / "part-0.parquet").write_bytes(b"parquet-sentinel")
    return model_sha


@pytest.fixture
def p10_root(tmp_path, monkeypatch):
    """Synthetic healthy tree, injected via V2_PROJECT_ROOT + cache reset."""
    model_sha = _build_healthy_tree(tmp_path)
    monkeypatch.setattr(RD, "EXPECTED_SERVING_MODEL_SHA", model_sha)
    monkeypatch.setenv("V2_PROJECT_ROOT", str(tmp_path))
    monkeypatch.delenv("V2_ALLOW_NETWORK", raising=False)
    RD.reset_readiness_cache()
    yield tmp_path
    RD.reset_readiness_cache()


@pytest.fixture
def client():
    from fastapi.testclient import TestClient

    from api.main import app

    return TestClient(app, raise_server_exceptions=False)


def _live_sentinels_present() -> bool:
    return (
        (REPO_ROOT / "results" / "v2_model_lab"
         / "winner_logreg_raw_v1_serving.joblib").is_file()
        and (REPO_ROOT / "results" / "v2_replay"
             / "phase8_e2_cache_manifest_v1.json").is_file()
        and (REPO_ROOT / "results" / "v2_explainability"
             / "global_winner_logreg_v1.json").is_file()
        and (REPO_ROOT / "data" / "v2" / "simulation" / "params"
             / "r3-v1__through-2024" / "manifest.json").is_file()
    )


def test_healthy_readiness_is_ready(p10_root):
    payload = RD.get_readiness()
    assert payload["status"] == "ready"
    assert payload["checks"] == {
        "serving_model": "ok",
        "replay": "ok",
        "explainability": "ok",
        "simulation": "ok",
        "processed_data": "ok",
        "network_policy": "ok",
    }
    assert payload["service"] == "f1-intelligence-v2"
    assert payload["winner_semantics"] == "INDEPENDENT_BINARY"
    assert payload["serving_years"] == "2018-2024"


def test_health_stays_200_while_readiness_503(tmp_path, monkeypatch, client):
    monkeypatch.setenv("V2_PROJECT_ROOT", str(tmp_path))  # empty root
    monkeypatch.delenv("V2_ALLOW_NETWORK", raising=False)
    RD.reset_readiness_cache()
    try:
        assert client.get("/health").status_code == 200
        resp = client.get("/ready")
        assert resp.status_code == 503
        assert resp.json()["status"] == "not_ready"
    finally:
        RD.reset_readiness_cache()


def test_ready_route_200_when_healthy(p10_root, client):
    resp = client.get("/ready")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ready"


def test_missing_serving_artifact(p10_root):
    (p10_root / "results" / "v2_model_lab"
     / "winner_logreg_raw_v1_serving.joblib").unlink()
    RD.reset_readiness_cache()
    payload = RD.get_readiness()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["serving_model"] == "missing_artifact"


def test_wrong_serving_sha(p10_root, monkeypatch):
    (p10_root / "results" / "v2_model_lab"
     / "winner_logreg_raw_v1_serving.joblib").write_bytes(b"tampered")
    RD.reset_readiness_cache()
    payload = RD.get_readiness()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["serving_model"] == "sha_mismatch"


def test_missing_replay_manifest(p10_root):
    (p10_root / "results" / "v2_replay"
     / "phase8_e2_cache_manifest_v1.json").unlink()
    RD.reset_readiness_cache()
    payload = RD.get_readiness()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["replay"] == "missing_manifest"


def test_missing_explainability_artifact(p10_root):
    (p10_root / "results" / "v2_explainability"
     / "global_winner_logreg_v1.json").unlink()
    RD.reset_readiness_cache()
    payload = RD.get_readiness()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["explainability"] == "missing_artifact"


def test_missing_simulation_params(p10_root):
    from raceintel.simulation import parameter_storage_dir
    (parameter_storage_dir(p10_root, 2024) / "manifest.json").unlink()
    RD.reset_readiness_cache()
    payload = RD.get_readiness()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["simulation"] == "missing_manifest"


def test_missing_processed_partition(p10_root):
    (p10_root / "data" / "v2" / "processed" / "races"
     / "season=2020" / "part-0.parquet").unlink()
    RD.reset_readiness_cache()
    payload = RD.get_readiness()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["processed_data"] == "missing_partition"


def test_network_on_rejected(p10_root, monkeypatch):
    monkeypatch.setenv("V2_ALLOW_NETWORK", "1")
    RD.reset_readiness_cache()
    payload = RD.get_readiness()
    assert payload["status"] == "not_ready"
    assert payload["checks"]["network_policy"] == "network_ingestion_enabled"


def test_response_bounded_no_paths_or_secrets(p10_root, client):
    resp = client.get("/ready")
    body = resp.text
    assert str(p10_root) not in body
    assert "traceback" not in body.lower()
    payload = resp.json()
    assert set(payload) <= {
        "status", "service", "model_sha_short", "winner_semantics",
        "serving_years", "checks"}
    assert all(value in ("ok",) or not value.startswith("/")
               for value in payload["checks"].values())


def test_readiness_cached_per_process(p10_root):
    first = RD.get_readiness()
    assert first["status"] == "ready"
    (p10_root / "results" / "v2_model_lab"
     / "winner_logreg_raw_v1_serving.joblib").unlink()
    assert RD.get_readiness()["status"] == "ready"  # cached
    RD.reset_readiness_cache()
    assert RD.get_readiness()["status"] == "not_ready"


def test_expected_sha_matches_source_preflight():
    """The serving-layer constant must equal the preflight pin (no drift)."""
    import re
    text = (REPO_ROOT / "scripts"
            / "check_runtime_environment.py").read_text()
    match = re.search(r"EXPECTED_SERVING_MODEL_SHA = \(\s*\"([0-9a-f]{64})\"",
                      text)
    assert match, "preflight pin not found"
    assert RD.EXPECTED_SERVING_MODEL_SHA == match.group(1)


@pytest.mark.skipif(not _live_sentinels_present(),
                    reason="needs the validated runtime bundle")
def test_live_tree_readiness_is_ready(monkeypatch):
    monkeypatch.delenv("V2_PROJECT_ROOT", raising=False)
    monkeypatch.delenv("V2_ALLOW_NETWORK", raising=False)
    RD.reset_readiness_cache()
    try:
        payload = RD.get_readiness()
        assert payload["status"] == "ready", payload["checks"]
    finally:
        RD.reset_readiness_cache()
