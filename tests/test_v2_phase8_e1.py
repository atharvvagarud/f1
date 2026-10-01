"""Phase-8 E1: cache-pipeline optimization equivalence + safety tests.

The E1 optimization is builder-only (SeasonStatesCache, build_one_race
refactor, opt-in --workers, additive --progress-manifest). No frozen
scientific module is touched. These tests prove transparent equivalence
against the immutable baseline fixture
(tests/fixtures/phase8_e1_baseline.json, captured from the unmodified
path at commit 17c04b30b124c087c51243a53d2f55bb3d9feeae).

Bounded generation uses --max-checkpoints 2 on 2023-r12-R (first two
checkpoints, seconds of compute) unless noted. Full-race byte
equivalence is proven out-of-band (E1 report) and pinned here via the
fixture's artifact SHAs for the serial path.
"""

import copy
import hashlib
import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd
import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from scripts.build_replay_prediction_cache import (  # noqa: E402
    SeasonStatesCache,
    load_race_inputs,
    race_season,
)
from raceintel.replay import replay as RP  # noqa: E402
from raceintel.replay.replay_predictions import (  # noqa: E402
    cache_key,
    canonical_data_identity,
    load_validated_artifact,
    select_checkpoints,
)

FIXTURE_PATH = os.path.join(ROOT, "tests", "fixtures",
                            "phase8_e1_baseline.json")
PROBE_RACES = ["2023-r12-R", "2023-r02-R", "2023-r06-R"]
SMALL_RACE = "2023-r12-R"
# Rain-shortened 2021 Spa: 60 frames, 3 checkpoints — full generation in
# seconds, used for resume/interruption/rebuild mechanics (not science).
TINY_RACE = "2021-r12-R"
BASE = os.path.join(ROOT, "data", "v2", "processed")


def _fixture():
    with open(FIXTURE_PATH) as handle:
        return json.load(handle)


def _run_cli(*argv):
    return subprocess.run(
        [sys.executable, "scripts/build_replay_prediction_cache.py",
         *argv],
        capture_output=True, text=True, cwd=ROOT)


def _sha(path):
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Baseline fixture immutability.
# ---------------------------------------------------------------------------

def test_baseline_fixture_environment_anchors():
    fix = _fixture()
    env = fix["environment"]
    assert env["commit"] == "17c04b30b124c087c51243a53d2f55bb3d9feeae"
    assert env["serving_artifact_sha256"] == \
        "1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4"
    assert env["phase2_content_hash"] == \
        "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db"
    assert env["specification_fingerprint"] == \
        "3164de9e61ca94ab958e26590608824ca6c7b05de29c5398d3d204a8c329c24d"
    assert env["python"].startswith("3.11.")
    assert fix["races"]["2023-r12-R"]["model"] == \
        fix["races"]["2023-r02-R"]["model"]


def test_baseline_probe_checkpoint_counts():
    fix = _fixture()
    assert len(fix["races"]["2023-r12-R"]["checkpoints"]) == 45
    assert len(fix["races"]["2023-r02-R"]["checkpoints"]) == 51
    assert len(fix["races"]["2023-r06-R"]["checkpoints"]) == 95
    total = sum(len(r["checkpoints"]) for r in fix["races"].values())
    assert total == 191


# ---------------------------------------------------------------------------
# Class-A: season-cache slice identity (no science change possible).
# ---------------------------------------------------------------------------

def test_season_cache_slice_identical_to_fresh_read():
    cache = SeasonStatesCache(BASE)
    for race_id in PROBE_RACES:
        season = race_season(race_id)
        fresh, _, _ = load_race_inputs(season, race_id, season_cache=None)
        cached, _, _ = load_race_inputs(
            season, race_id, season_cache=cache)
        pd.testing.assert_frame_equal(
            cached.reset_index(drop=True), fresh.reset_index(drop=True),
            check_exact=True)
        # Cache reuse: second call hits the stored season frame.
        assert season in cache._frames
        again, _, _ = load_race_inputs(
            season, race_id, season_cache=cache)
        pd.testing.assert_frame_equal(again, cached, check_exact=True)


def test_checkpoint_selection_invariant_under_cache():
    fix = _fixture()
    cache = SeasonStatesCache(BASE)
    for race_id in PROBE_RACES:
        season = race_season(race_id)
        states, _, _ = load_race_inputs(
            season, race_id, season_cache=cache)
        timeline = RP.build_replay_timeline(states)
        series = select_checkpoints(timeline, states)
        assert series.to_dict() == fix["races"][race_id]["series"]
        assert series.checkpoint_count == \
            len(fix["races"][race_id]["checkpoints"])


def test_cache_key_invariance_from_fixture_series():
    fix = _fixture()
    for race_id in PROBE_RACES:
        stored = fix["races"][race_id]
        assert cache_key(stored["cache_identity"]) == stored["cache_key"]


# ---------------------------------------------------------------------------
# Feature / transformed / logit / probability equivalence (EARLY/MID/LATE).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _frozen_stack():
    from raceintel.config import V2Paths
    from raceintel.features.build_matrix import load_history
    from raceintel.model_lab import serving as SERVING
    predictor = SERVING.load_frozen_winner_model()
    history = load_history(V2Paths.resolve())
    return predictor, history


def _checkpoints_early_mid_late(fix, race_id):
    ckpts = fix["races"][race_id]["checkpoints"]
    return [ckpts[0], ckpts[len(ckpts) // 2], ckpts[-1]]


def test_all84_feature_equivalence_fresh_vs_cached(_frozen_stack):
    from raceintel.replay import replay as RP_MOD
    from raceintel.race_state.race_state_features import RaceStateFeatureBridge
    from raceintel.replay.replay_reconstruction import ReplayReconstructor
    from raceintel.race_state.race_state_reconstruction import RaceStateReconstructor
    predictor, history = _frozen_stack
    fix = _fixture()
    cache = SeasonStatesCache(BASE)
    for probe in _checkpoints_early_mid_late(fix, SMALL_RACE):
        batches = []
        for use_cache in (False, True):
            states, results, meta = load_race_inputs(
                2023, SMALL_RACE,
                season_cache=cache if use_cache else None)
            timeline = RP_MOD.build_replay_timeline(states)
            service = ReplayReconstructor(
                timeline, RaceStateReconstructor(
                    states, results, race_meta=meta or None))
            bridge = RaceStateFeatureBridge(states, history)
            state = service.state_at(probe["frame_index"])
            batches.append(bridge.features_for_state(state))
        fresh, cached = batches
        assert fresh.feature_names == cached.feature_names
        assert tuple(fresh.driver_ids) == tuple(cached.driver_ids)
        pd.testing.assert_frame_equal(
            cached.features.reset_index(drop=True),
            fresh.features.reset_index(drop=True), check_exact=True)


def test_transformed_logit_probability_equivalence(_frozen_stack):
    from raceintel.replay import replay as RP_MOD
    from raceintel.race_state.race_state_features import RaceStateFeatureBridge
    from raceintel.replay.replay_reconstruction import ReplayReconstructor
    from raceintel.race_state.race_state_reconstruction import RaceStateReconstructor
    predictor, history = _frozen_stack
    fix = _fixture()
    cache = SeasonStatesCache(BASE)
    for probe in _checkpoints_early_mid_late(fix, SMALL_RACE):
        frames = []
        for use_cache in (False, True):
            states, results, meta = load_race_inputs(
                2023, SMALL_RACE,
                season_cache=cache if use_cache else None)
            timeline = RP_MOD.build_replay_timeline(states)
            service = ReplayReconstructor(
                timeline, RaceStateReconstructor(
                    states, results, race_meta=meta or None))
            bridge = RaceStateFeatureBridge(states, history)
            state = service.state_at(probe["frame_index"])
            frames.append(bridge.features_for_state(state).features)
        fresh, cached = frames
        fresh_m = predictor._preprocessor.transform(fresh)
        cached_m = predictor._preprocessor.transform(cached)
        np.testing.assert_array_equal(cached_m, fresh_m)
        fresh_logit = predictor._estimator.decision_function(fresh_m)
        cached_logit = predictor._estimator.decision_function(cached_m)
        np.testing.assert_array_equal(cached_logit, fresh_logit)
        fresh_p = predictor.predict_proba(fresh)
        cached_p = predictor.predict_proba(cached)
        np.testing.assert_array_equal(cached_p, fresh_p)
        assert float(np.max(np.abs(cached_p - fresh_p))) == 0.0
        # And the frozen path reproduces the immutable fixture exactly.
        fixture_probs = [d[2] for d in probe["roster"] if d[1]]
        np.testing.assert_array_equal(
            np.asarray(fresh_p, dtype=float),
            np.asarray(fixture_probs, dtype=float))


# ---------------------------------------------------------------------------
# Bounded CLI generation vs fixture (checkpoint/roster/probability/keys).
# ---------------------------------------------------------------------------

def test_bounded_generation_matches_fixture_prefix(tmp_path):
    out = _run_cli("--race-id", SMALL_RACE, "--checkpoints-dir",
                   str(tmp_path), "--max-checkpoints", "2")
    assert out.returncode == 0, out.stderr[-2000:]
    path = str(tmp_path / f"{SMALL_RACE}.json")
    artifact = json.load(open(path))
    assert artifact["complete"] is False  # subset by design
    fix = _fixture()["races"][SMALL_RACE]
    # Identity inputs do not depend on the subset: same scientific key.
    assert artifact["cache_key"] == fix["cache_key"]
    assert artifact["series"] == fix["series"]
    assert artifact["model"] == fix["model"]
    for entry, probe in zip(artifact["checkpoints"],
                            fix["checkpoints"][:2]):
        assert entry["checkpoint"]["frame_index"] == probe["frame_index"]
        assert entry["checkpoint"]["reasons"] == probe["reasons"]
        got = [[d["driver_id"], d["observable"],
                d["winner_probability"], d["unavailable_reason"]]
               for d in entry["prediction"]["predictions"]]
        assert got == probe["roster"]


def test_bounded_generation_deterministic(tmp_path):
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    for directory in (first, second):
        out = _run_cli("--race-id", SMALL_RACE, "--checkpoints-dir",
                       str(directory), "--max-checkpoints", "2")
        assert out.returncode == 0, out.stderr[-2000:]
    assert _sha(str(first / f"{SMALL_RACE}.json")) == \
        _sha(str(second / f"{SMALL_RACE}.json"))


# ---------------------------------------------------------------------------
# Resume / interruption / rebuild semantics.
# ---------------------------------------------------------------------------

def _bounded(directory, *extra):
    out = _run_cli("--race-id", SMALL_RACE, "--checkpoints-dir",
                   str(directory), "--max-checkpoints", "2", *extra)
    assert out.returncode == 0, out.stderr[-2000:]
    return out


def test_valid_complete_subset_skipped_on_resume(tmp_path):
    out = _run_cli("--race-id", TINY_RACE, "--checkpoints-dir",
                   str(tmp_path))
    assert out.returncode == 0, out.stderr[-2000:]
    assert "generated" in out.stdout
    path = str(tmp_path / f"{TINY_RACE}.json")
    full_sha = _sha(path)
    assert json.load(open(path))["complete"] is True
    out = _run_cli("--race-id", TINY_RACE, "--checkpoints-dir",
                   str(tmp_path), "--resume")
    assert out.returncode == 0, out.stderr[-2000:]
    assert "skipped" in out.stdout
    assert _sha(path) == full_sha


def test_corrupt_artifact_regenerated(tmp_path):
    out = _run_cli("--race-id", TINY_RACE, "--checkpoints-dir",
                   str(tmp_path))
    assert out.returncode == 0, out.stderr[-2000:]
    path = str(tmp_path / f"{TINY_RACE}.json")
    with open(path, "w") as handle:
        handle.write("{truncated")
    out = _run_cli("--race-id", TINY_RACE, "--checkpoints-dir",
                   str(tmp_path))
    assert out.returncode == 0, out.stderr[-2000:]
    assert "generated" in out.stdout
    artifact = json.load(open(path))
    assert artifact["complete"] is True


def test_incomplete_artifact_never_served_and_regenerated(tmp_path):
    _bounded(tmp_path)
    path = str(tmp_path / f"{SMALL_RACE}.json")
    artifact = json.load(open(path))
    season = race_season(SMALL_RACE)
    states, _, _ = load_race_inputs(season, SMALL_RACE)
    series = select_checkpoints(RP.build_replay_timeline(states), states)
    with pytest.raises(Exception):
        load_validated_artifact(
            path, expected_inputs=artifact["cache_identity"],
            series=series)
    out = _run_cli("--race-id", SMALL_RACE, "--checkpoints-dir",
                   str(tmp_path), "--max-checkpoints", "2", "--force")
    assert out.returncode == 0, out.stderr[-2000:]
    assert json.load(open(path))["complete"] is False


def test_interruption_recovery_partial_prefix_regenerated(tmp_path):
    # Simulate interruption: a prefix-subset artifact left behind by a
    # killed bounded build must regenerate (never served as complete).
    _bounded(tmp_path)
    path = str(tmp_path / f"{SMALL_RACE}.json")
    assert json.load(open(path))["complete"] is False
    out = _run_cli("--race-id", TINY_RACE, "--checkpoints-dir",
                   str(tmp_path))
    assert out.returncode == 0, out.stderr[-2000:]
    tiny = json.load(open(str(tmp_path / f"{TINY_RACE}.json")))
    assert tiny["complete"] is True
    # The interrupted race is untouched by an unrelated race build.
    assert json.load(open(path))["complete"] is False


def test_single_race_rebuild(tmp_path):
    for race_id in (TINY_RACE, "2023-r02-R"):
        out = _run_cli("--race-id", race_id, "--checkpoints-dir",
                       str(tmp_path), "--max-checkpoints", "2")
        assert out.returncode == 0, out.stderr[-2000:]
    victim = str(tmp_path / f"{TINY_RACE}.json")
    keeper = str(tmp_path / "2023-r02-R.json")
    keeper_sha = _sha(keeper)
    os.unlink(victim)
    out = _run_cli("--race-id", TINY_RACE, "--race-id", "2023-r02-R",
                   "--checkpoints-dir", str(tmp_path),
                   "--max-checkpoints", "2")
    assert out.returncode == 0, out.stderr[-2000:]
    assert os.path.exists(victim)
    assert _sha(keeper) == keeper_sha  # untouched race skipped


# ---------------------------------------------------------------------------
# Parallelism: identical science, manifest additive.
# ---------------------------------------------------------------------------

def test_parallel_matches_serial_bounded(tmp_path):
    serial = tmp_path / "serial"
    parallel = tmp_path / "parallel"
    serial.mkdir()
    parallel.mkdir()
    out = _run_cli("--race-id", SMALL_RACE, "--race-id", "2023-r02-R",
                   "--checkpoints-dir", str(serial),
                   "--max-checkpoints", "2", "--workers", "1")
    assert out.returncode == 0, out.stderr[-2000:]
    out = _run_cli("--race-id", SMALL_RACE, "--race-id", "2023-r02-R",
                   "--checkpoints-dir", str(parallel),
                   "--max-checkpoints", "2", "--workers", "2")
    assert out.returncode == 0, out.stderr[-2000:]
    for race_id in (SMALL_RACE, "2023-r02-R"):
        a = json.load(open(str(serial / f"{race_id}.json")))
        b = json.load(open(str(parallel / f"{race_id}.json")))
        assert b == a


def test_progress_manifest_additive(tmp_path):
    manifest = str(tmp_path / "manifest.json")
    out = _run_cli("--race-id", SMALL_RACE, "--checkpoints-dir",
                   str(tmp_path), "--max-checkpoints", "2",
                   "--progress-manifest", manifest)
    assert out.returncode == 0, out.stderr[-2000:]
    assert f"manifest -> {manifest}" in out.stdout
    record = json.load(open(manifest))
    assert record["manifest_format"] == "replay-build-manifest-v1"
    assert record["race_count"] == 1
    assert record["races"][0]["race_id"] == SMALL_RACE
    assert record["races"][0]["checkpoint_count"] == 45
    assert "artifact_sha256" in record["races"][0]
    # Manifest is builder-only: artifact has no manifest reference.
    artifact = json.load(open(str(tmp_path / f"{SMALL_RACE}.json")))
    assert "manifest" not in json.dumps(artifact)


# ---------------------------------------------------------------------------
# Firewalls + counts.
# ---------------------------------------------------------------------------

def test_2025_rejected_serial_and_parallel(tmp_path):
    out = _run_cli("--race-id", "2025-r01-R", "--dry-run")
    assert out.returncode != 0
    assert "2025" in (out.stdout + out.stderr)
    out = _run_cli("--race-id", "2025-r01-R",
                   "--checkpoints-dir", str(tmp_path), "--workers", "2")
    assert out.returncode != 0
    assert "2025" in (out.stdout + out.stderr)


def test_probe_dry_run_counts_match_fixture():
    out = _run_cli("--race-id", "2023-r12-R", "--race-id", "2023-r02-R",
                   "--race-id", "2023-r06-R", "--dry-run")
    assert out.returncode == 0, out.stderr[-2000:]
    for race_id, count in (("2023-r12-R", 45), ("2023-r02-R", 51),
                           ("2023-r06-R", 95)):
        assert f"{race_id}: " in out.stdout
        line = next(line for line in out.stdout.splitlines()
                    if line.startswith(race_id))
        assert f"checkpoints={count}" in line


def test_frozen_modules_untouched_by_e1():
    # P11-1 REPLACE_WITH_CURRENT_CONTRACT (extends the api/main.py
    # exemption): tests/test_v2_phase4_freeze.py was corrected by P11-1
    # itself (drift-chain replacement for its own byte self-pin), so an
    # exact match here is impossible by construction. Structural presence
    # replaces the byte pin for that one file; every other recorded file
    # stays byte-exact. See test_v2_phase4_freeze.py for the rationale.
    import hashlib as _hl
    manifest = json.loads(
        open(os.path.join(ROOT, "docs",
                          "PHASE4_FREEZE_MANIFEST.json")).read())
    # C2 structural migration (v2/ -> raceintel/, import-prefix rewrite
    # only); same mapping as test_v2_phase4_freeze.py.
    C2_MIGRATED_P4 = {
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
    for section in ("phase4_modules", "phase4_tests", "benchmark",
                    "api_contract"):
        for path, recorded in manifest[section].items():
            if path == "api/main.py":
                continue
            if path == "tests/test_v2_phase4_freeze.py":
                continue  # authorized P11-1 stale-pin correction
            if path in C2_MIGRATED_P4:
                new = C2_MIGRATED_P4[path]
                if new != path:
                    assert not os.path.exists(os.path.join(ROOT, path)), path
                assert os.path.isfile(os.path.join(ROOT, new)), new
                digest = _hl.sha256(
                    open(os.path.join(ROOT, new), "rb").read()).hexdigest()
                assert digest != recorded, new
                continue
            digest = _hl.sha256(
                open(os.path.join(ROOT, path), "rb").read()).hexdigest()
            assert digest == recorded, path
    assert "def test_frozen_module_hashes_match" in open(
        os.path.join(ROOT, "tests",
                     "test_v2_phase4_freeze.py")).read()
    frozen = json.loads(
        open(os.path.join(ROOT, "docs",
                          "PHASE5_FREEZE_MANIFEST.json")).read())
    C2_MIGRATED_P5 = {
        "v2/replay.py": "raceintel/replay/replay.py",
        "v2/replay_predictions.py":
            "raceintel/replay/replay_predictions.py",
        "v2/replay_probability_timeline.py":
            "raceintel/replay/replay_probability_timeline.py",
        "v2/replay_reconstruction.py":
            "raceintel/replay/replay_reconstruction.py",
        "api/v2_replay_routes.py": "api/v2_replay_routes.py",
        "api/v2_replay_service.py": "api/v2_replay_service.py",
        "scripts/benchmark_phase5_replay.py":
            "scripts/benchmark_phase5_replay.py",
    }
    for path, recorded in {
            **frozen["domain_modules"],
            **frozen["benchmark_files"]}.items():
        if path == "scripts/build_replay_prediction_cache.py":
            continue  # the single authorized E1 optimization surface
        if path in C2_MIGRATED_P5:
            new = C2_MIGRATED_P5[path]
            if new != path:
                assert not os.path.exists(os.path.join(ROOT, path)), path
            assert os.path.isfile(os.path.join(ROOT, new)), new
            digest = _hl.sha256(
                open(os.path.join(ROOT, new), "rb").read()).hexdigest()
            assert digest != recorded, new
            continue
        digest = _hl.sha256(
            open(os.path.join(ROOT, path), "rb").read()).hexdigest()
        assert digest == recorded, path
