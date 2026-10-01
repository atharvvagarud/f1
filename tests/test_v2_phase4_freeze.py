"""Phase-4 R7 freeze seal: cross-layer frozen invariants.

Compact seal suite; does NOT duplicate R1-R6 behavior. Verifies the
freeze manifest, code identities, serving artifact identity, route
inventory, normalized OpenAPI, contract representation, 2025 exclusion,
no-fallback, no-training-entry, and legacy presence. No model inference,
no target access, no evaluation.
"""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "PHASE4_FREEZE_MANIFEST.json"
CONTRACT = ROOT / "docs" / "PHASE4_V2_API_CONTRACT.json"


def _manifest():
    with open(MANIFEST) as fh:
        return json.load(fh)


def _sha(path):
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def test_manifest_parses_and_freezes_phase4():
    data = _manifest()
    assert data["phase"] == 4
    assert data["status"] == "FROZEN"
    assert data["contract_version"] == "v1"


def test_contract_constants_frozen():
    data = _manifest()["contracts"]
    assert data["feature_set"] == "ALL_84"
    assert data["feature_set_version"] == "v8"
    assert data["probability_semantics"] == "INDEPENDENT_BINARY"
    assert data["normalization"] is False
    assert data["serving_seasons"] == [2018, 2019, 2020, 2021, 2022,
                                       2023, 2024]
    assert data["model_task"] == "winner"
    assert data["target"] == "is_winner"
    assert data["eligibility"] == "eligible_is_winner"
    assert data["unavailable_reason"] == "NO_OBSERVATION_AT_SNAPSHOT"


def test_frozen_module_hashes_match():
    # P11-1 REPLACE_WITH_CURRENT_CONTRACT (was: exact hash match of every
    # Phase-4-manifest file). OLD CONTRACT: all recorded files byte-identical
    # to the Phase-4 seal. CURRENT CONTRACT: every recorded file EXCEPT
    # api/main.py is still byte-identical (later phases never touched them);
    # api/main.py evolved additively through authorized stages (Phase-5
    # replay, Phase-6 simulation, Phase-7 strategy/explainability routers,
    # P10-3 serving config), with each stage's drift pinned in its own
    # freeze manifest. The replacement keeps exact pins where files are
    # frozen and asserts authorized evolution where the manifest is a
    # superseded time capsule — strictly stronger than skipping the file.
    data = _manifest()
    # C2 structural migration (v2/ -> raceintel/, import-prefix rewrite
    # only): listed files changed bytes and/or paths. Old paths must be
    # gone, new paths must exist with acknowledged-different bytes; new
    # hashes are pinned in the C2 migration record. Everything else stays
    # byte-exact against the frozen manifest.
    C2_MIGRATED = {
        "api/v2_routes.py": "api/v2_routes.py",
        "api/v2_service.py": "api/v2_service.py",
        "v2/prediction.py": "raceintel/prediction.py",
        "v2/race_state.py": "raceintel/race_state/race_state.py",
        "v2/race_state_features.py":
            "raceintel/race_state/race_state_features.py",
        "v2/race_state_reconstruction.py":
            "raceintel/race_state/race_state_reconstruction.py",
        "scripts/benchmark_phase4.py": "scripts/benchmark_phase4.py",
        "tests/test_v2_phase4_r1.py": "tests/test_v2_phase4_r1.py",
        "tests/test_v2_phase4_r2.py": "tests/test_v2_phase4_r2.py",
        "tests/test_v2_phase4_r3.py": "tests/test_v2_phase4_r3.py",
        "tests/test_v2_phase4_r4.py": "tests/test_v2_phase4_r4.py",
        "tests/test_v2_phase4_r5.py": "tests/test_v2_phase4_r5.py",
        "tests/test_v2_phase4_r6.py": "tests/test_v2_phase4_r6.py",
    }
    for section in ("phase4_modules", "phase4_tests",
                    "benchmark", "api_contract"):
        for path, recorded in data[section].items():
            if path in ("api/main.py",
                        "tests/test_v2_phase4_freeze.py"):
                continue
            if path in C2_MIGRATED:
                new = C2_MIGRATED[path]
                if new != path:
                    assert not (ROOT / path).exists(), path
                assert (ROOT / new).is_file(), new
                assert _sha(new) != recorded, new
                continue
            assert _sha(path) == recorded, path
    # Self-pin: this test file is itself recorded in phase4_tests, so an
    # exact self-match cannot survive any authorized correction of this
    # very test (including P11-1). Structural presence replaces the
    # impossible byte pin; tamper-evidence for the file is git history.
    assert "def test_frozen_module_hashes_match" in (
        ROOT / "tests" / "test_v2_phase4_freeze.py").read_text()
    assert data["phase4_modules"]["api/main.py"] == \
        "455910f5ab8d4e82cb2a881cba6be97cb69fa785569df82dcba61bf77671e959"
    assert _sha("api/main.py") != \
        data["phase4_modules"]["api/main.py"]
    text = (ROOT / "api" / "main.py").read_text()
    for marker in ("v2_replay_router", "v2_simulation_router",
                   "v2_strategy_router", "ServingConfig",
                   "RequestLoggingMiddleware"):
        assert marker in text, marker


def test_serving_artifact_identity_matches():
    from raceintel.model_lab import serving as S
    record = S.describe_serving_artifact()
    frozen = _manifest()["phase3"]
    assert record["sha256"] == frozen["serving_artifact_sha256"]
    assert len(record["sha256"]) == 64
    assert (record["specification_fingerprint"]
            == frozen["specification_fingerprint"])


def test_v2_route_inventory_matches():
    from api.v2_routes import router
    live = sorted({f"{sorted(r.methods)[0].lower()} {r.path}"
                   for r in router.routes})
    assert live == _manifest()["v2_routes"]


def test_normalized_openapi_matches_contract_artifact():
    from api.main import app
    with open(CONTRACT) as fh:
        pinned = json.load(fh)
    assert pinned["contract_version"] == "v1"
    live_paths = app.openapi()["paths"]
    seen = []
    for entry in pinned["endpoints"]:
        assert entry["path"] in live_paths, entry["path"]
        assert entry["method"] in live_paths[entry["path"]], entry
        seen.append(f"{entry['method']} {entry['path']}")
    assert sorted(seen) == _manifest()["v2_routes"]
    assert [e["path"] for e in pinned["endpoints"]] == [
        "/v2/races", "/v2/races/{race_id}/states",
        "/v2/races/{race_id}/state",
        "/v2/predictions/winner-snapshot"]


def test_anchor_and_roster_contracts_represented():
    from raceintel.race_state import race_state as RS
    from raceintel.prediction import (NO_OBSERVATION_AT_SNAPSHOT,
                               PROBABILITY_SEMANTICS)
    assert RS.AnchorObservation.__dataclass_fields__.keys() == {
        "race_id", "anchor_driver_id", "anchor_lap_number",
        "anchor_state_time_s"}
    assert PROBABILITY_SEMANTICS == "INDEPENDENT_BINARY"
    assert NO_OBSERVATION_AT_SNAPSHOT == "NO_OBSERVATION_AT_SNAPSHOT"
    with open(CONTRACT) as fh:
        pinned = json.load(fh)
    state = next(e for e in pinned["endpoints"]
                 if e["path"] == "/v2/races/{race_id}/state")
    assert {p["name"] for p in state["parameters"]} == {
        "race_id", "anchor_driver_id", "anchor_lap_number",
        "anchor_state_time_s"}


def test_2025_serving_exclusion_pinned():
    from api import v2_service as VS
    assert tuple(VS.SERVED_SEASONS) == tuple(range(2018, 2025))
    assert VS.MAX_SERVED_SEASON == 2024
    for name in ("v2_service.py", "v2_routes.py", "v2_schemas.py"):
        text = (ROOT / "api" / name).read_text()
        lowered = text.lower()
        for token in ("is_winner", "final_position", "is_podium",
                      "scored_points", "eligible_", "winner_flag",
                      "podium_flag", "classified_", "race_driver_labels",
                      "model_matrix", "allow_protected_holdout",
                      "2025-r"):
            assert token not in lowered, (name, token)


def test_no_model_fallback_path():
    text = (ROOT / "api" / "v2_routes.py").read_text()
    assert "model_unavailable" in text
    for banned in ("run_ensemble", "run_single_model",
                   "get_available_races", "ml.inference"):
        assert banned not in text, banned
    service = (ROOT / "api" / "v2_service.py").read_text()
    assert "load_production_prediction_engine" in service


def test_serving_path_has_no_training_entry():
    for path in ("raceintel/prediction.py", "raceintel/race_state/race_state_features.py",
                 "api/v2_service.py", "api/v2_routes.py"):
        text = (ROOT / path).read_text()
        for banned in (".fit(", "joblib", "ml.inference"):
            assert banned not in text, (path, banned)


def test_legacy_route_inventory_present():
    from api.main import app
    paths = app.openapi()["paths"]
    for legacy in ("/health", "/races", "/predict/ensemble",
                   "/predict/single-model"):
        assert legacy in paths, legacy
