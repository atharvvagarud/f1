"""Phase-5 R8 freeze seal: cross-layer frozen invariants.

Compact seal suite for the Historical Replay subsystem. It does NOT
duplicate every R1-R7 test: it pins the frozen public contract, the
deterministic identities, the API/route surface, the corpus facts, the
read-only cache boundary, the probability grain, and the freeze manifest.

No production prediction cache is required (tests use synthetic or
absent caches). No model inference is performed. No 2025 evaluation
target is read.
"""

from __future__ import annotations

import ast
import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "docs" / "PHASE5_FREEZE_MANIFEST.json"
API_CONTRACT = ROOT / "docs" / "PHASE5_REPLAY_API_CONTRACT.json"
PHASE4_MANIFEST = ROOT / "docs" / "PHASE4_FREEZE_MANIFEST.json"
PHASE2_MANIFEST = ROOT / "docs" / "generated" / "phase2_freeze_manifest.json"

D9 = ("data/v2/processed/driver_lap_state_d9/season={season}/"
      "driver_lap_state_d9__d9-{season}.parquet")
RESULTS = ("data/v2/processed/results/season={season}/"
           "results__{race}.parquet")

RACE_SHARED_T = "2020-r09-R"
SHARED_T = 2974.257
SHARED_T_REPRESENTATIVE = ("giovinazzi", 6)

PHASE4_SEAL_COMMIT = "4f26801ffb0bb1a10725d6c78fba11c5547cb432"
PHASE4_TAG = "v2-race-state-prediction-phase4"
PHASE5_TAG = "v2-historical-replay-phase5"
SERVING_ARTIFACT = "results/v2_model_lab/winner_logreg_raw_v1_serving.joblib"

REPLAY_ROUTES = [
    "get /v2/races/{race_id}/replay/frames/{frame_index}",
    "get /v2/races/{race_id}/replay/predictions/{frame_index}",
    "get /v2/races/{race_id}/replay/probability-timeline",
    "get /v2/races/{race_id}/replay/timeline",
]

PHASE4_ROUTES = [
    "get /v2/races",
    "get /v2/races/{race_id}/state",
    "get /v2/races/{race_id}/states",
    "post /v2/predictions/winner-snapshot",
]

LEGACY_ROUTES = ["/health", "/races", "/predict/ensemble",
                 "/predict/single-model"]


def _sha(path) -> str:
    return hashlib.sha256((ROOT / path).read_bytes()).hexdigest()


def _load(path):
    with open(path) as handle:
        return json.load(handle)


# ---------------------------------------------------------------------------
# Contract versions + route inventory.
# ---------------------------------------------------------------------------

def test_contract_versions_frozen():
    from v2 import replay as RP
    from v2.replay_predictions import (
        PHASE4_CONTRACT_VERSION,
        REPLAY_PREDICTION_CONTRACT_VERSION,
    )
    from v2.replay_probability_timeline import (
        PROBABILITY_SEMANTICS,
        PROBABILITY_TIMELINE_CONTRACT_VERSION,
    )
    assert RP.REPLAY_CONTRACT_VERSION == "v1"
    assert REPLAY_PREDICTION_CONTRACT_VERSION == "v1"
    assert PROBABILITY_TIMELINE_CONTRACT_VERSION == "v1"
    assert PHASE4_CONTRACT_VERSION == "v1"
    assert PROBABILITY_SEMANTICS == "INDEPENDENT_BINARY"


def test_replay_route_inventory_exact():
    from api.v2_replay_routes import router
    live = sorted(f"{sorted(r.methods)[0].lower()} {r.path}"
                  for r in router.routes)
    assert live == REPLAY_ROUTES


def test_phase4_and_legacy_routes_preserved():
    from api.main import app
    paths = app.openapi()["paths"]
    for legacy in LEGACY_ROUTES:
        assert legacy in paths, legacy
    for route in PHASE4_ROUTES:
        method, path = route.split(" ", 1)
        assert path in paths and method in paths[path], route


def test_api_contract_artifact_matches_live_routes():
    pinned = _load(API_CONTRACT)
    assert pinned["contract_version"] == "v1"
    assert pinned["phase"] == 5
    assert pinned["status"] == "FROZEN"
    assert pinned["served_seasons"] == list(range(2018, 2025))
    assert pinned["probability_semantics"] == "INDEPENDENT_BINARY"
    assert pinned["replay_contract_version"] == "v1"
    assert pinned["prediction_contract_version"] == "v1"
    assert pinned["probability_timeline_contract_version"] == "v1"

    from api.main import app
    live = app.openapi()["paths"]
    seen = []
    for entry in pinned["endpoints"]:
        assert entry["path"] in live, entry["path"]
        assert entry["method"] in live[entry["path"]], entry
        ref = live[entry["path"]][entry["method"]]["responses"]["200"][
            "content"]["application/json"]["schema"]["$ref"]
        assert ref.endswith("/" + entry["response_model"]), entry
        seen.append(f"{entry['method']} {entry['path']}")
    assert sorted(seen) == REPLAY_ROUTES


def test_api_contract_pagination_pins():
    pinned = _load(API_CONTRACT)["pagination"]
    assert pinned == {"offset": {"minimum": 0, "default": 0},
                      "limit": {"minimum": 1, "maximum": 500,
                                "default": 100}}
    timeline = next(e for e in _load(API_CONTRACT)["endpoints"]
                    if e["path"].endswith("/replay/timeline"))
    params = {p["name"]: p for p in timeline["parameters"]}
    assert params["offset"]["schema"]["minimum"] == 0
    assert params["limit"]["schema"] == {"default": 100, "maximum": 500,
                                         "minimum": 1, "type": "integer"}


# ---------------------------------------------------------------------------
# Timeline representative rule + shared-T critical fixture.
# ---------------------------------------------------------------------------

def test_timeline_representative_rule_is_lap_then_driver():
    from v2 import replay as RP
    df = pd.DataFrame([
        {"race_id": "r", "driver_id": "zeta", "lap_number": 3,
         "state_time_s": 10.0},
        {"race_id": "r", "driver_id": "alpha", "lap_number": 4,
         "state_time_s": 20.0},
        {"race_id": "r", "driver_id": "beta", "lap_number": 3,
         "state_time_s": 10.0},
    ])
    timeline = RP.build_replay_timeline(df)
    assert timeline.frame_count == 2
    assert (timeline.frame_at(0).anchor_driver_id,
            timeline.frame_at(0).anchor_lap_number) == ("beta", 3)
    indices = [f.frame_index for f in timeline.frames]
    assert indices == [0, 1]
    times = [f.anchor_state_time_s for f in timeline.frames]
    assert times == sorted(times) and len(set(times)) == len(times)


def test_shared_t_critical_fixture():
    from v2 import replay as RP
    from v2.race_state_reconstruction import RaceStateReconstructor

    states = pd.read_parquet(D9.format(season=2020))
    race_states = states[states["race_id"] == RACE_SHARED_T].copy()
    results = pd.read_parquet(
        RESULTS.format(season=2020, race=RACE_SHARED_T))
    timeline = RP.build_replay_timeline(race_states)
    match = [f for f in timeline.frames
             if f.anchor_state_time_s == SHARED_T]
    assert len(match) == 1
    frame = match[0]
    assert (frame.anchor_driver_id,
            frame.anchor_lap_number) == SHARED_T_REPRESENTATIVE
    reconstructor = RaceStateReconstructor(race_states, results)
    state = reconstructor.reconstruct(frame.to_anchor())
    assert state.race_control.track_state == "yellow"
    assert state.race_control.flag_yellow is True
    assert state.race_control.flag_safety_car is False
    # The non-representative latifi/lap7 row owns no frame.
    assert all(f.anchor_driver_id != "latifi" or f.anchor_lap_number != 7
               for f in timeline.frames)


# ---------------------------------------------------------------------------
# Served scope + 2025 firewall.
# ---------------------------------------------------------------------------

def test_served_scope_and_2025_exclusion():
    from api import v2_service as VS
    assert tuple(VS.SERVED_SEASONS) == tuple(range(2018, 2025))
    assert VS.MAX_SERVED_SEASON == 2024
    assert 2025 not in VS.SERVED_SEASONS

    from v2 import replay as RP
    # Builder is season-agnostic by design; scope is a serving concern.
    df = pd.DataFrame([
        {"race_id": "2025-r01-R", "driver_id": "a", "lap_number": 1,
         "state_time_s": 10.0}])
    assert RP.build_replay_timeline(df).race_id == "2025-r01-R"


# ---------------------------------------------------------------------------
# Checkpoint policy identity.
# ---------------------------------------------------------------------------

def test_checkpoint_policy_identity_synthetic():
    from v2 import replay as RP
    from v2.replay_predictions import FLAG_TRANSITION, LEADER_LAP, \
        select_checkpoints
    df = pd.DataFrame([
        {"race_id": "r", "driver_id": "a", "lap_number": 1,
         "state_time_s": 10.0, "race_leader_laps_at_state": 1,
         "track_state": "all_clear"},
        {"race_id": "r", "driver_id": "a", "lap_number": 2,
         "state_time_s": 20.0, "race_leader_laps_at_state": 2,
         "track_state": "all_clear"},
        {"race_id": "r", "driver_id": "a", "lap_number": 3,
         "state_time_s": 30.0, "race_leader_laps_at_state": 3,
         "track_state": "safety_car"},
    ])
    timeline = RP.build_replay_timeline(df)
    series = select_checkpoints(timeline, df)
    by_frame = {c.frame_index: c for c in series.checkpoints}
    assert by_frame[0].reasons == (LEADER_LAP,)
    assert by_frame[1].reasons == (LEADER_LAP,)
    assert by_frame[2].reasons == (FLAG_TRANSITION, LEADER_LAP)
    assert by_frame[2].leader_lap == 3


# ---------------------------------------------------------------------------
# Corpus facts (model-free).
# ---------------------------------------------------------------------------

def test_corpus_checkpoint_count_model_free():
    """Full 2018-2024 model-free corpus facts (R1/R3/R7 agreement)."""
    from v2 import replay as RP
    from v2.replay_predictions import select_checkpoints
    parts = [pd.read_parquet(D9.format(season=s))
             for s in range(2018, 2025)]
    corpus = pd.concat(parts, ignore_index=True)
    races = sorted(corpus["race_id"].unique())
    frames = 0
    checkpoints = 0
    for race_id in races:
        sub = corpus[corpus["race_id"] == race_id]
        timeline = RP.build_replay_timeline(sub)
        frames += timeline.frame_count
        checkpoints += select_checkpoints(timeline, sub).checkpoint_count
    assert len(races) == 149
    assert len(corpus) == 162728
    assert frames == 162639
    assert checkpoints == 9644


# ---------------------------------------------------------------------------
# Probability semantics + no normalization.
# ---------------------------------------------------------------------------

def test_independent_binary_and_no_normalization_tokens():
    for path in ("v2/replay.py", "v2/replay_predictions.py",
                 "v2/replay_probability_timeline.py",
                 "api/v2_replay_service.py", "api/v2_replay_routes.py",
                 "api/v2_replay_schemas.py"):
        text = (ROOT / path).read_text()
        for banned in ("probability_share", "sum_to_one", "softmax"):
            assert banned not in text, (path, banned)
        # No normalization function may be called or imported.
        for name in _called_and_imported_names(path):
            lowered = name.lower()
            assert "normaliz" not in lowered, (path, name)
            assert "softmax" not in lowered, (path, name)
    from v2.replay_probability_timeline import PROBABILITY_SEMANTICS
    assert PROBABILITY_SEMANTICS == "INDEPENDENT_BINARY"


def test_validate_snapshot_allows_sum_above_one():
    from v2.replay_predictions import validate_snapshot
    roster = ["a", "b"]
    snapshot = {
        "roster_size": 2,
        "predictions": [
            {"driver_id": "a", "winner_probability": 0.9,
             "unavailable_reason": None},
            {"driver_id": "b", "winner_probability": 0.6,
             "unavailable_reason": None},
        ],
    }
    validate_snapshot(snapshot)  # 1.5 is legal under INDEPENDENT_BINARY
    assert roster == ["a", "b"]


# ---------------------------------------------------------------------------
# Cache read path: read-only, no generation anywhere.
# ---------------------------------------------------------------------------

def _called_and_imported_names(path) -> set:
    """Names actually imported or invoked in a module (docstrings excluded)."""
    tree = ast.parse((ROOT / path).read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            for alias in node.names:
                names.add(alias.name)
                if alias.asname:
                    names.add(alias.asname)
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name):
                names.add(func.id)
            elif isinstance(func, ast.Attribute):
                names.add(func.attr)
        elif isinstance(node, ast.Attribute):
            names.add(node.attr)
    return names


def test_read_path_has_no_generation_tokens():
    banned = ("generate_race_artifact", "ensure_race_artifact",
              "generate_checkpoint", "load_production_prediction",
              "predict_proba", "fit", "predict")
    for path in ("api/v2_replay_service.py", "api/v2_replay_routes.py"):
        called = _called_and_imported_names(path)
        for token in banned:
            assert token not in called, (path, token)
    # Projection module must never touch the engine/model stack.
    forbidden = ("generate_", "engine", "predict", "sklearn", "joblib")
    called = _called_and_imported_names("v2/replay_probability_timeline.py")
    for token in forbidden:
        assert token not in called, token


def test_replay_service_import_is_model_free():
    code = (
        "import sys; import api.v2_replay_service as m; "
        "forbidden={'v2.prediction','v2.race_state_features',"
        "'v2.model_lab','api.v2_service','sklearn'}; "
        "bad=sorted(forbidden.intersection(sys.modules)); "
        "print('BAD='+','.join(bad) if bad else 'CLEAN')")
    result = subprocess.run(
        [sys.executable, "-c", code], cwd=str(ROOT),
        capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert "CLEAN" in result.stdout, result.stdout


# ---------------------------------------------------------------------------
# Probability projection: actual checkpoints only, null != zero.
# ---------------------------------------------------------------------------

def _synthetic_artifact():
    model = {
        "task": "winner", "target": "is_winner",
        "eligibility_mask": "eligible_is_winner", "feature_set": "ALL_84",
        "feature_set_version": "v8", "probability_semantics":
        "INDEPENDENT_BINARY",
    }

    def prediction(frame_index, state_time, probs):
        return {
            "race_id": "r", "model": model,
            "probability_semantics": "INDEPENDENT_BINARY",
            "state_time_s": state_time,
            "anchor_driver_id": "a", "anchor_lap_number": frame_index + 1,
            "predictions": [
                {"driver_id": d, "winner_probability": p,
                 "unavailable_reason": None if p is not None else "X"}
                for d, p in probs.items()],
        }

    def checkpoint(frame_index, state_time, reasons, leader_lap):
        return {
            "frame_index": frame_index, "reasons": reasons,
            "leader_lap": leader_lap, "anchor_driver_id": "a",
            "anchor_lap_number": frame_index + 1,
            "anchor_state_time_s": state_time,
        }

    return {
        "artifact_format": "replay-checkpoints-v1", "race_id": "r",
        "replay_contract_version": "v1",
        "prediction_contract_version": "v1", "complete": True,
        "model": model,
        "checkpoints": [
            {"checkpoint": checkpoint(0, 10.0, ["LEADER_LAP"], 1),
             "prediction": prediction(0, 10.0, {"a": 0.9, "b": 0.3})},
            {"checkpoint": checkpoint(5, 40.0, ["FLAG_TRANSITION"], 1),
             "prediction": prediction(5, 40.0, {"a": None, "b": 1.4})},
        ],
    }


def test_probability_projection_actual_checkpoints_only():
    from v2.replay_probability_timeline import build_probability_timeline
    timeline = build_probability_timeline(_synthetic_artifact())
    projected = {c["frame_index"] for c in timeline["checkpoints"]}
    assert projected == {0, 5}
    for series in timeline["driver_series"]:
        assert {p["frame_index"] for p in series["points"]} == projected
    assert timeline["probability_semantics"] == "INDEPENDENT_BINARY"
    blob = json.dumps(timeline).lower()
    for banned in ("interpolat", "resampl", "forward_fill", "backfill",
                   "probability_share"):
        assert banned not in blob, banned


def test_null_probability_is_never_zero():
    from v2.replay_probability_timeline import build_probability_timeline
    timeline = build_probability_timeline(_synthetic_artifact())
    by_driver = {s["driver_id"]: s for s in timeline["driver_series"]}
    points_a = {p["frame_index"]: p["winner_probability"]
                for p in by_driver["a"]["points"]}
    assert points_a[0] == 0.9
    assert points_a[5] is None
    # >1 passes through verbatim (no normalization).
    points_b = {p["frame_index"]: p["winner_probability"]
                for p in by_driver["b"]["points"]}
    assert points_b[5] == 1.4


# ---------------------------------------------------------------------------
# Frontend / backend contract field compatibility (token presence).
# ---------------------------------------------------------------------------

def test_frontend_backend_contract_field_compatibility():
    backend = (ROOT / "api" / "v2_replay_schemas.py").read_text() + \
        (ROOT / "api" / "v2_schemas.py").read_text()
    frontend = (ROOT / "frontend" / "lib" / "v2.ts").read_text()
    shared_fields = {
        "race_id", "frame_index", "anchor_driver_id",
        "anchor_lap_number", "anchor_state_time_s",
        "replay_contract_version", "total_frames", "returned_count",
        "has_previous", "has_next", "previous_frame_index",
        "next_frame_index", "leader_lap", "is_prediction_checkpoint",
        "checkpoint_reasons", "prediction_cache_available",
        "previous_prediction_checkpoint_frame",
        "next_prediction_checkpoint_frame", "driver_id",
        "winner_probability", "unavailable_reason", "timeline_identity",
        "driver_series", "probability_timeline_contract_version",
        "cache_status",
    }
    for field in shared_fields:
        assert field in backend, ("backend", field)
        assert field in frontend, ("frontend", field)


# ---------------------------------------------------------------------------
# Freeze manifest (created by R8 before this test runs).
# ---------------------------------------------------------------------------

HASH_SECTIONS = ("domain_modules", "api_modules", "frontend_files",
                 "test_files", "benchmark_files", "doc_files",
                 "repository_files")


def test_freeze_manifest_parses_and_has_sections():
    data = _load(MANIFEST)
    assert data["phase"] == 5
    assert data["status"] == "FROZEN"
    assert data["freeze_contract_version"] == "v1"
    assert data["created_by_stage"] == "R8"
    for section in HASH_SECTIONS + ("upstream", "phase5_contracts",
                                    "corpus", "scientific_identity",
                                    "performance", "verification",
                                    "known_debt", "git"):
        assert section in data, section


def test_freeze_manifest_file_hashes_match():
    # P11-1 REPLACE_WITH_CURRENT_CONTRACT (was: exact hash match of every
    # Phase-5-manifest file). OLD CONTRACT: all recorded files byte-identical
    # to the Phase-5 seal. CURRENT CONTRACT: every recorded file EXCEPT
    # api/main.py is still byte-identical; api/main.py evolved additively
    # through authorized stages (Phase-6 simulation router per the Phase-6
    # drift record, Phase-7 routers, P10-3 serving config).
    data = _load(MANIFEST)
    # Files with authorized post-Phase-5 evolution (exact evolved set):
    # - api/main.py: Phase-6/7 routers + P10-3 serving config.
    # - 14 frontend files: Phase-9 workspace/evidence frontend.
    # - scripts/build_replay_prediction_cache.py: Phase-8 matrix backend.
    # - .gitignore: P10-1A runtime_artifacts boundary.
    # - the two self-pinned test files (a byte self-pin cannot survive an
    #   authorized correction of the test itself).
    evolved = {"api/main.py",
               "tests/test_v2_phase5_freeze.py",
               "tests/test_v2_phase5_r7.py",
               "scripts/build_replay_prediction_cache.py",
               ".gitignore",
               "frontend/app/page.tsx",
               "frontend/app/replay/page.tsx",
               "frontend/features/replay/components/ContextBar.tsx",
               "frontend/features/replay/components/PlaybackControls.tsx",
               "frontend/features/replay/components/PredictionPanel.tsx",
               "frontend/features/replay/components/"
               "ProbabilityTimelineChart.tsx",
               "frontend/features/replay/components/RaceSelector.tsx",
               "frontend/features/replay/components/ReplayView.tsx",
               "frontend/features/replay/components/StandingsTable.tsx",
               "frontend/features/replay/components/TimelineScrubber.tsx",
               "frontend/features/replay/hooks/useReplay.ts",
               "frontend/features/replay/lib/probabilityTimeline.test.ts",
               "frontend/features/replay/lib/probabilityTimeline.ts",
               "frontend/lib/v2.ts"}
    diverged = set()
    for section in HASH_SECTIONS:
        assert data[section], section
        for path, recorded in data[section].items():
            assert (ROOT / path).exists(), path
            if path in evolved:
                if _sha(path) != recorded:
                    diverged.add(path)
                continue
            assert _sha(path) == recorded, path
    assert diverged == evolved, diverged ^ evolved
    # Authorized-evolution evidence per family (stronger than skipping).
    text = (ROOT / "api" / "main.py").read_text()
    for marker in ("v2_replay_router", "v2_simulation_router",
                   "v2_strategy_router", "ServingConfig",
                   "RequestLoggingMiddleware"):
        assert marker in text, marker
    assert (ROOT / "docs" / "PHASE9_FINAL_FREEZE_REPORT.md").is_file()
    cache_script = (ROOT / "scripts" /
                    "build_replay_prediction_cache.py").read_text()
    assert "--feature-source" in cache_script and "matrix" in cache_script
    assert (ROOT / "docs" /
            "PHASE8_E2_REPLAY_CACHE_BACKFILL_REPORT.md").is_file()
    assert "/runtime_artifacts/" in (ROOT / ".gitignore").read_text()
    for self_test, node in (
            ("tests/test_v2_phase5_freeze.py",
             "def test_freeze_manifest_file_hashes_match"),
            ("tests/test_v2_phase5_r7.py",
             "def test_head_and_phase4_tag_intact")):
        assert node in (ROOT / self_test).read_text()
    assert data["api_modules"]["api/main.py"] == \
        "2840271a49ced72720e9fc0fa3028a206ff4b9d8c1178fd6a1eab7ebe118549a"
    assert _sha("api/main.py") != data["api_modules"]["api/main.py"]
    assert _sha("docs/PHASE5_REPLAY_API_CONTRACT.json") == \
        data["api_contract"]["sha256"]


def test_freeze_manifest_has_no_self_hash():
    data = _load(MANIFEST)
    listed = set()
    for section in HASH_SECTIONS:
        listed.update(data[section])
    listed.add(data["api_contract"]["path"])
    assert "docs/PHASE5_FREEZE_MANIFEST.json" not in listed
    assert data["git"]["manifest_self_hash"] is None


def test_freeze_manifest_upstream_identities():
    data = _load(MANIFEST)
    upstream = data["upstream"]
    assert upstream["phase4"]["seal_commit"] == PHASE4_SEAL_COMMIT
    assert upstream["phase4"]["tag"] == PHASE4_TAG
    assert upstream["phase3"]["serving_artifact_sha256"] == \
        "1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4"
    assert upstream["phase2"]["content_hash"] == \
        "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db"
    assert upstream["phase3"]["specification_fingerprint"] == \
        "3164de9e61ca94ab958e26590608824ca6c7b05de29c5398d3d204a8c329c24d"


def test_freeze_manifest_contracts_and_corpus():
    data = _load(MANIFEST)
    contracts = data["phase5_contracts"]
    assert contracts["replay_contract_version"] == "v1"
    assert contracts["prediction_contract_version"] == "v1"
    assert contracts["probability_timeline_contract_version"] == "v1"
    assert contracts["probability_semantics"] == "INDEPENDENT_BINARY"
    assert contracts["normalization"] is False
    assert contracts["serving_seasons"] == list(range(2018, 2025))
    assert sorted(contracts["replay_routes"]) == REPLAY_ROUTES
    corpus = data["corpus"]
    assert corpus["served_races"] == 149
    assert corpus["served_observations"] == 162728
    assert corpus["replay_frames"] == 162639
    assert corpus["prediction_checkpoints"] == 9644


def test_generated_cache_required_in_bundle_era():
    # P11-1 UPDATE_STALE_EXPECTATION (was:
    # test_freeze_manifest_generated_cache_not_required, asserting
    # results/v2_replay absent). The Phase-5 manifest predates the Phase-8
    # E2 backfill; in the bundle era the served replay cache is a REQUIRED
    # generated artifact (149 races / 9644 checkpoints). The test now pins
    # the current contract: cache present, E2 manifest present, corpus
    # counts and aggregate/model identities exact. Corpus-dependent: needs
    # the ignored generated cache (Tier 3, not Tier 1).
    cache = ROOT / "results" / "v2_replay"
    assert cache.is_dir()
    checkpoints = sorted((cache / "checkpoints").glob("*.json"))
    assert len(checkpoints) == 149
    with open(cache / "phase8_e2_cache_manifest_v1.json") as handle:
        manifest = json.load(handle)
    assert manifest["race_count"] == 149
    assert manifest["checkpoint_count"] == 9644
    assert manifest["aggregate_corpus_sha256"] == \
        "78a3c059888637fe83cc534d0eb7869b6d18e746724bb1ce0f03ee3b8ba96298"
    assert manifest["model_identity"]["artifact_sha256"] == \
        "1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4"


def test_freeze_manifest_documents_authorized_api_main_drift():
    # P11-1 UPDATE_STALE_EXPECTATION. The Phase-5 drift record is history
    # (phase4 455910f5… -> phase5 2840271a…); the file has since evolved
    # through further authorized stages: Phase-6 simulation router
    # (phase6 5a0ec439… per docs/PHASE6_FREEZE_MANIFEST.json), Phase-7
    # routers, P10-3 serving config. The test now asserts chain continuity
    # across manifests plus authorized markers in the current file, instead
    # of pinning the superseded Phase-5 SHA as current.
    data = _load(MANIFEST)
    drift = data["api"]["authorized_api_main_drift"]
    phase4_sha = _load(PHASE4_MANIFEST)["phase4_modules"]["api/main.py"]
    assert drift["phase4_frozen_sha256"] == phase4_sha
    phase6_drift = _load(ROOT / "docs" / "PHASE6_FREEZE_MANIFEST.json")[
        "api_main_drift"]
    assert phase6_drift["phase4_frozen_sha256"] == phase4_sha
    assert phase6_drift["phase5_final_sha256"] == \
        drift["phase5_final_sha256"]
    assert phase6_drift["phase6_final_sha256"] == \
        "5a0ec4396e8fb5f7c4d1e7efd3882d53f1a786ca146e795760cc40e1aa0fed9a"
    current = _sha("api/main.py")
    assert current != drift["phase4_frozen_sha256"]
    assert current != drift["phase5_final_sha256"]
    assert current != phase6_drift["phase6_final_sha256"]
    text = (ROOT / "api" / "main.py").read_text()
    for marker in ("v2_replay_router", "v2_simulation_router",
                   "v2_strategy_router", "ServingConfig",
                   "RequestLoggingMiddleware"):
        assert marker in text, marker


# ---------------------------------------------------------------------------
# Upstream frozen identities recomputed from repository reality.
# ---------------------------------------------------------------------------

def test_phase4_upstream_module_hashes_except_authorized_drift():
    phase4 = _load(PHASE4_MANIFEST)["phase4_modules"]
    for path, recorded in phase4.items():
        if path == "api/main.py":
            assert _sha(path) != recorded  # authorized additive drift
        else:
            assert _sha(path) == recorded, path


def test_upstream_scientific_identity_recomputed():
    phase4 = _load(PHASE4_MANIFEST)
    # Serving artifact bytes.
    assert _sha(SERVING_ARTIFACT) == \
        phase4["phase3"]["serving_artifact_sha256"]
    # Phase-2 semantic identity from the generated Phase-2 freeze manifest.
    phase2 = _load(PHASE2_MANIFEST)["matrix"]
    assert phase2["content_hash"] == phase4["phase2"]["content_hash"]
    assert phase2["parquet_sha256"] == phase4["phase2"]["parquet_sha256"]
    # F16 matrix manifest bytes.
    assert _sha("data/v2/processed/model_matrix/matrix_version=v1/"
                "manifest.json") == phase4["phase2"]["manifest_sha256"]
    # Spec fingerprint from the live serving artifact metadata.
    from v2.model_lab import serving as S
    record = S.describe_serving_artifact()
    assert record["sha256"] == phase4["phase3"]["serving_artifact_sha256"]
    assert record["specification_fingerprint"] == \
        phase4["phase3"]["specification_fingerprint"]


def test_phase4_seal_commit_and_tag_present():
    head_ok = subprocess.run(
        ["git", "merge-base", "--is-ancestor", PHASE4_SEAL_COMMIT, "HEAD"],
        cwd=str(ROOT), capture_output=True)
    assert head_ok.returncode == 0
    tag = subprocess.run(
        ["git", "rev-parse", f"{PHASE4_TAG}^{{commit}}"],
        cwd=str(ROOT), capture_output=True, text=True)
    assert tag.stdout.strip() == PHASE4_SEAL_COMMIT


def test_phase5_expected_tag_recorded():
    data = _load(MANIFEST)
    assert data["git"]["expected_tag"] == PHASE5_TAG
    assert data["git"]["upstream_base_commit"] == PHASE4_SEAL_COMMIT
