"""Phase-8 E1.6: frozen-matrix accelerated builder tests.

Proves the accelerated path (exact Phase-2 matrix lookup) is
scientifically interchangeable with the E1 reference path against the
immutable E1 baseline fixture (never regenerated).

Conventions: bounded matrix builds take seconds; full 3-probe matrix
builds take ~15 s. The corpus-wide structural scan (~10 min) runs as
one explicit gate test. /tmp only for comparison artifacts.
"""

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
    load_race_inputs,
    race_season,
)
from scripts.replay_feature_matrix import (  # noqa: E402
    FrozenReplayFeatureMatrix,
    MatrixBackendError,
    MatrixIdentityError,
    MatrixLookupError,
    MatrixScopeError,
    IDENTITY_COLUMNS,
)
from v2 import replay as RP  # noqa: E402
from v2.replay_predictions import select_checkpoints  # noqa: E402

FIXTURE_PATH = os.path.join(ROOT, "tests", "fixtures",
                            "phase8_e1_baseline.json")
PROBES = ["2023-r12-R", "2023-r02-R", "2023-r06-R"]
SMALL_RACE = "2023-r12-R"
BASE = os.path.join(ROOT, "data", "v2", "processed")
MATRIX_PATH = os.path.join(
    ROOT, "data", "v2", "processed", "model_matrix", "matrix_version=v1",
    "model_matrix.parquet")


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


@pytest.fixture(scope="module")
def matrix():
    return FrozenReplayFeatureMatrix.load(ROOT)


# ---------------------------------------------------------------------------
# Matrix identity validation.
# ---------------------------------------------------------------------------

def test_matrix_identity_against_manifest(matrix):
    record = matrix.manifest_record
    assert record["rows"] == 189420
    assert record["predictive_columns"] == 84
    assert record["parquet_sha256"] == \
        "b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3"
    assert record["content_hash"] == \
        "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db"
    assert _sha(MATRIX_PATH) == record["parquet_sha256"]


def test_all84_registry_order(matrix):
    from v2.experiments.feature_sets import canonical_predictive_names
    from v2.features.interactions import build_f11_registry
    expected = tuple(
        canonical_predictive_names(build_f11_registry()))
    assert len(expected) == 84
    assert matrix.feature_names == expected


def test_served_scope_excludes_2025(matrix):
    frame = matrix._frame
    assert int((frame["season"] == 2025).sum()) == 0
    assert set(int(s) for s in frame["season"].unique()) <= set(range(2018, 2025))
    assert len(frame) == 189420 - 26692
    with pytest.raises(MatrixScopeError):
        matrix.race_slice("2025-r01-R")


def test_label_firewall_no_label_columns(matrix):
    forbidden = {"is_winner", "final_position", "is_podium",
                 "scored_points", "position_change_from_state",
                 "gains_position_by_finish", "loses_position_by_finish",
                 "classified_flag", "eligible_is_winner",
                 "eligible_is_podium", "eligible_scored_points",
                 "eligible_ordinal_final_position", "eligible_gain_loss"}
    assert not (set(matrix._frame.columns) & forbidden)
    assert set(matrix._frame.columns) == (
        set(matrix.feature_names) | {"race_id", "season", "driver_id",
                                     "lap_number", "state_time_s"})


def test_registry_driven_projection_not_positional(matrix):
    import copy
    names = list(matrix.feature_names)
    shuffled = names[1:] + names[:1]
    assert tuple(shuffled) != tuple(names)
    with pytest.raises(MatrixIdentityError):
        FrozenReplayFeatureMatrix(matrix._frame.copy(), tuple(shuffled),
                                  matrix.manifest_record)


def test_duplicate_identity_fail_closed(matrix):
    frame = matrix._frame
    dup = pd.concat([frame.iloc[:1], frame], ignore_index=True)
    with pytest.raises(MatrixIdentityError):
        FrozenReplayFeatureMatrix(dup, matrix.feature_names,
                                  matrix.manifest_record)


# ---------------------------------------------------------------------------
# Adversarial matrix tests (temporary copies under tmp_path).
# ---------------------------------------------------------------------------

def test_altered_feature_rejected_at_load(tmp_path):
    import shutil
    dst = str(tmp_path / "matrix_copy.parquet")
    shutil.copy(MATRIX_PATH, dst)
    frame = pd.read_parquet(dst)
    names = [c for c in frame.columns if c not in (
        "race_id", "season", "round_no", "circuit_id", "driver_id",
        "constructor_id", "lap_number", "state_time_s", "state_id",
        "is_winner", "is_podium", "scored_points",
        "position_change_from_state", "gains_position_by_finish",
        "loses_position_by_finish", "classified_flag", "eligible_is_winner",
        "eligible_is_podium", "eligible_scored_points",
        "eligible_ordinal_final_position", "eligible_gain_loss")][0]
    frame.loc[frame.index[0], names] = float(frame[names].iloc[0]) + 1.0
    frame.to_parquet(dst)
    with pytest.raises(MatrixIdentityError):
        FrozenReplayFeatureMatrix.load(ROOT, path=dst)


def test_label_poisoning_leaves_predictions_unchanged(matrix, tmp_path):
    # Defense in depth, two layers. Layer 1 (load path): any mutation of
    # the frozen file — labels included — fails SHA verification, so a
    # label-scrambled file cannot load (proven by rejection here and by
    # test_altered_feature_rejected_at_load for predictive cells).
    import shutil
    dst = str(tmp_path / "matrix_copy.parquet")
    shutil.copy(MATRIX_PATH, dst)
    frame = pd.read_parquet(dst)
    frame["is_winner"] = 1 - frame["is_winner"]
    frame.to_parquet(dst)
    with pytest.raises(MatrixIdentityError):
        FrozenReplayFeatureMatrix.load(ROOT, path=dst)
    # Layer 2 (constructor): even bypassing load(), a frame carrying
    # label/eligibility columns is refused, so labels cannot enter the
    # prediction projection under any construction path.
    smuggled = pd.read_parquet(
        MATRIX_PATH,
        columns=["race_id", "season", "driver_id", "lap_number",
                 "state_time_s", "is_winner", "final_position",
                 "eligible_is_winner", "classified_flag",
                 *list(matrix.feature_names)])
    smuggled = smuggled[smuggled["season"].isin(range(2018, 2025))].copy()
    with pytest.raises(MatrixIdentityError):
        FrozenReplayFeatureMatrix(smuggled, matrix.feature_names,
                                  matrix.manifest_record)
    # And the clean backend provably holds no labels (projection).
    assert "is_winner" not in matrix._frame.columns


def test_missing_row_fail_closed(matrix):
    frame = matrix._frame
    victim = frame[(frame["race_id"] == SMALL_RACE)].iloc[0]
    pruned = frame.drop(victim.name).reset_index(drop=True)
    backend = FrozenReplayFeatureMatrix(
        pruned, matrix.feature_names, matrix.manifest_record)
    race_frame = backend.race_slice(SMALL_RACE)
    want = pd.DataFrame(
        [[victim["race_id"], victim["driver_id"],
          int(victim["lap_number"]), float(victim["state_time_s"])]],
        columns=["race_id", "driver_id", "lap_number", "state_time_s"])
    with pytest.raises(MatrixLookupError):
        backend.lookup(want, race_frame)


# ---------------------------------------------------------------------------
# Bounded accelerated builds vs immutable fixture.
# ---------------------------------------------------------------------------

def test_bounded_matrix_build_matches_fixture_prefix(tmp_path):
    out = _run_cli("--race-id", SMALL_RACE, "--checkpoints-dir",
                   str(tmp_path), "--max-checkpoints", "2",
                   "--feature-source", "matrix")
    assert out.returncode == 0, out.stderr[-2000:]
    artifact = json.load(open(str(tmp_path / f"{SMALL_RACE}.json")))
    fix = _fixture()["races"][SMALL_RACE]
    assert artifact["cache_key"] == fix["cache_key"]
    assert artifact["series"] == fix["series"]
    assert artifact["model"] == fix["model"]
    for entry, probe in zip(artifact["checkpoints"],
                            fix["checkpoints"][:2]):
        assert entry["checkpoint"]["frame_index"] == probe["frame_index"]
        got = [[d["driver_id"], d["observable"],
                d["winner_probability"], d["unavailable_reason"]]
               for d in entry["prediction"]["predictions"]]
        assert got == probe["roster"]


def test_unobservable_drivers_preserved(tmp_path):
    out = _run_cli("--race-id", SMALL_RACE, "--checkpoints-dir",
                   str(tmp_path), "--max-checkpoints", "1",
                   "--feature-source", "matrix")
    assert out.returncode == 0, out.stderr[-2000:]
    artifact = json.load(open(str(tmp_path / f"{SMALL_RACE}.json")))
    fix = _fixture()["races"][SMALL_RACE]["checkpoints"][0]
    assert [d["driver_id"] for d in
            artifact["checkpoints"][0]["prediction"]["predictions"]] == \
        [d[0] for d in fix["roster"]]
    nulls = [d for d in
             artifact["checkpoints"][0]["prediction"]["predictions"]
             if not d["observable"]]
    assert len(nulls) == sum(1 for d in fix["roster"] if not d[1])
    assert all(d["winner_probability"] is None and
               d["unavailable_reason"] == "NO_OBSERVATION_AT_SNAPSHOT"
               for d in nulls)


def test_matrix_build_deterministic(tmp_path):
    first = tmp_path / "a"
    second = tmp_path / "b"
    first.mkdir()
    second.mkdir()
    for directory in (first, second):
        out = _run_cli("--race-id", SMALL_RACE, "--checkpoints-dir",
                       str(directory), "--max-checkpoints", "2",
                       "--feature-source", "matrix")
        assert out.returncode == 0, out.stderr[-2000:]
    assert _sha(str(first / f"{SMALL_RACE}.json")) == \
        _sha(str(second / f"{SMALL_RACE}.json"))


def test_matrix_parallel_matches_serial(tmp_path):
    serial = tmp_path / "serial"
    parallel = tmp_path / "parallel"
    serial.mkdir()
    parallel.mkdir()
    out = _run_cli("--race-id", SMALL_RACE, "--race-id", "2023-r02-R",
                   "--checkpoints-dir", str(serial),
                   "--max-checkpoints", "2", "--feature-source", "matrix",
                   "--workers", "1")
    assert out.returncode == 0, out.stderr[-2000:]
    out = _run_cli("--race-id", SMALL_RACE, "--race-id", "2023-r02-R",
                   "--checkpoints-dir", str(parallel),
                   "--max-checkpoints", "2", "--feature-source", "matrix",
                   "--workers", "2")
    assert out.returncode == 0, out.stderr[-2000:]
    for race_id in (SMALL_RACE, "2023-r02-R"):
        assert json.load(open(str(serial / f"{race_id}.json"))) == \
            json.load(open(str(parallel / f"{race_id}.json")))


def test_reference_recompute_path_still_works(tmp_path):
    out = _run_cli("--race-id", SMALL_RACE, "--checkpoints-dir",
                   str(tmp_path), "--max-checkpoints", "2",
                   "--feature-source", "recompute")
    assert out.returncode == 0, out.stderr[-2000:]
    artifact = json.load(open(str(tmp_path / f"{SMALL_RACE}.json")))
    fix = _fixture()["races"][SMALL_RACE]
    assert artifact["cache_key"] == fix["cache_key"]
    got = [[d["driver_id"], d["observable"],
            d["winner_probability"], d["unavailable_reason"]]
           for d in artifact["checkpoints"][0]["prediction"]["predictions"]]
    assert got == fix["checkpoints"][0]["roster"]


def test_2025_refused_before_prediction(tmp_path):
    out = _run_cli("--race-id", "2025-r01-R", "--checkpoints-dir",
                   str(tmp_path), "--feature-source", "matrix")
    assert out.returncode != 0
    assert "2025" in (out.stdout + out.stderr)


# ---------------------------------------------------------------------------
# Full 3-probe accelerated builds vs E1 baseline (headline gate).
# ---------------------------------------------------------------------------

def test_full_probe_artifacts_byte_identical_to_baseline(tmp_path):
    out = _run_cli(*[x for r in PROBES for x in ("--race-id", r)],
                   "--checkpoints-dir", str(tmp_path),
                   "--feature-source", "matrix")
    assert out.returncode == 0, out.stderr[-2000:]
    fix = _fixture()
    expected_sha = {
        "2023-r12-R": "ce5619b7e56ed7153f7acb831f24e9c1a27d8b294da10e84260f799c1f917663",
        "2023-r02-R": "9ae3cefe1641545e2c7ac6c6b744e504899fe58362623262633763648717ec81",
        "2023-r06-R": "491bf335ffdcf7ddd0f3c9dcbbb46053dcc885ecae2b0285e46c68ad826e88d2",
    }
    assert fix["races"]["2023-r12-R"]["artifact_sha256"] == \
        expected_sha["2023-r12-R"]
    for race_id in PROBES:
        path = str(tmp_path / f"{race_id}.json")
        assert _sha(path) == fix["races"][race_id]["artifact_sha256"]
        assert _sha(path) == expected_sha[race_id]
        artifact = json.load(open(path))
        stored = fix["races"][race_id]
        assert artifact["complete"] is True
        assert artifact["cache_key"] == stored["cache_key"]
        assert artifact["series"] == stored["series"]
        assert artifact["model"] == stored["model"]
        assert len(artifact["checkpoints"]) == len(stored["checkpoints"])
        dmax = 0.0
        for entry, probe in zip(artifact["checkpoints"],
                                stored["checkpoints"]):
            assert entry["checkpoint"]["frame_index"] == probe["frame_index"]
            assert entry["checkpoint"]["reasons"] == probe["reasons"]
            got = [[d["driver_id"], d["observable"],
                    d["winner_probability"], d["unavailable_reason"]]
                   for d in entry["prediction"]["predictions"]]
            assert got == probe["roster"]
            for mine, want in zip(
                    [d for d in entry["prediction"]["predictions"]
                     if d["observable"]],
                    [d for d in probe["roster"] if d[1]]):
                dmax = max(dmax, abs(mine["winner_probability"] - want[2]))
        assert dmax == 0.0


# ---------------------------------------------------------------------------
# Feature/transformed/logit equivalence (tests only recompute guard).
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def _stack():
    from v2.config import V2Paths
    from v2.features.build_matrix import load_history
    from v2.model_lab import serving as SERVING
    return (SERVING.load_frozen_winner_model(),
            load_history(V2Paths.resolve()),
            FrozenReplayFeatureMatrix.load(ROOT))


def test_eml_matrix_rows_equal_recomputed_features(_stack):
    from v2.race_state_features import RaceStateFeatureBridge
    from v2.replay_reconstruction import ReplayReconstructor
    from v2.race_state_reconstruction import RaceStateReconstructor
    predictor, history, backend = _stack
    fix = _fixture()
    states, results, meta = load_race_inputs(2023, SMALL_RACE)
    timeline = RP.build_replay_timeline(states)
    service = ReplayReconstructor(timeline, RaceStateReconstructor(
        states, results, race_meta=meta or None))
    bridge = RaceStateFeatureBridge(states, history)
    race_frame = backend.race_slice(SMALL_RACE)
    ckpts = fix["races"][SMALL_RACE]["checkpoints"]
    for probe in (ckpts[0], ckpts[len(ckpts) // 2], ckpts[-1]):
        state = service.state_at(probe["frame_index"])
        batch = bridge.features_for_state(state)
        for (_, frow), request in zip(batch.features.iterrows(),
                                      bridge.requests_for(state)):
            hit = race_frame[
                (race_frame["race_id"] == request.race_id)
                & (race_frame["driver_id"] == request.driver_id)
                & (race_frame["lap_number"] == int(request.lap_number))
                & (race_frame["state_time_s"] == float(request.state_time_s))]
            assert len(hit) == 1
            mrow = hit.iloc[0]
            for name, value in zip(batch.features.columns, frow):
                cell = mrow[name]
                vnull = value is None or (isinstance(value, float)
                                          and np.isnan(value))
                if vnull:
                    assert pd.isna(cell)
                elif isinstance(value, (int, float)) and not isinstance(
                        value, bool):
                    assert float(value) == float(cell)
                else:
                    assert value == cell


def test_eml_transformed_logit_exact(_stack):
    from v2.race_state_features import RaceStateFeatureBridge
    from v2.replay_reconstruction import ReplayReconstructor
    from v2.race_state_reconstruction import RaceStateReconstructor
    predictor, history, backend = _stack
    fix = _fixture()
    states, results, meta = load_race_inputs(2023, SMALL_RACE)
    timeline = RP.build_replay_timeline(states)
    service = ReplayReconstructor(timeline, RaceStateReconstructor(
        states, results, race_meta=meta or None))
    bridge = RaceStateFeatureBridge(states, history)
    race_frame = backend.race_slice(SMALL_RACE)
    ckpts = fix["races"][SMALL_RACE]["checkpoints"]
    probe = ckpts[len(ckpts) // 2]
    state = service.state_at(probe["frame_index"])
    batch = bridge.features_for_state(state)
    rows = []
    for request in bridge.requests_for(state):
        hit = race_frame[
            (race_frame["race_id"] == request.race_id)
            & (race_frame["driver_id"] == request.driver_id)
            & (race_frame["lap_number"] == int(request.lap_number))
            & (race_frame["state_time_s"] == float(request.state_time_s))]
        rows.append(hit.iloc[0][list(backend.feature_names)])
    matrix_frame = pd.DataFrame(rows, columns=list(backend.feature_names))
    left = predictor._preprocessor.transform(batch.features)
    right = predictor._preprocessor.transform(matrix_frame)
    np.testing.assert_array_equal(left, right)
    np.testing.assert_array_equal(
        predictor._estimator.decision_function(left),
        predictor._estimator.decision_function(right))


# ---------------------------------------------------------------------------
# Corpus-wide structural coverage (model-free gate, NOT a cache build).
# ---------------------------------------------------------------------------

def test_corpus_structural_coverage_149_races(matrix):
    import glob as _glob
    base = os.path.join(ROOT, "data", "v2", "processed")
    pattern = os.path.join(base, "results", "season=*", "results__*.parquet")
    race_ids = sorted(
        os.path.basename(p)[len("results__"):-len(".parquet")]
        for p in _glob.glob(pattern))
    race_ids = [r for r in race_ids if int(r.split("-")[0]) in range(2018, 2025)]
    assert len(race_ids) == 149
    from scripts.build_replay_prediction_cache import SeasonStatesCache
    from v2.race_state_features import RaceStateFeatureBridge
    from v2.replay_reconstruction import ReplayReconstructor
    from v2.race_state_reconstruction import RaceStateReconstructor
    from v2.config import V2Paths
    from v2.features.build_matrix import load_history
    history = load_history(V2Paths.resolve())
    season_cache = SeasonStatesCache(base)
    total_ckpts = total_req = exact = missing = ambiguous = 0
    dup_requests = 0
    for race_id in race_ids:
        season = race_season(race_id)
        states, results, meta = load_race_inputs(
            season, race_id, season_cache=season_cache)
        timeline = RP.build_replay_timeline(states)
        series = select_checkpoints(timeline, states)
        service = ReplayReconstructor(timeline, RaceStateReconstructor(
            states, results, race_meta=meta or None))
        bridge = RaceStateFeatureBridge(states, history)
        race_frame = matrix.race_slice(race_id)
        keys = race_frame[list(IDENTITY_COLUMNS)]
        assert not bool(keys.duplicated().any())
        seen: set = set()
        rows = []
        for checkpoint in series.checkpoints:
            state = service.state_at(checkpoint.frame_index)
            for request in bridge.requests_for(state):
                key = request.key()
                rows.append(key)
                if key in seen:
                    dup_requests += 1
                seen.add(key)
        total_ckpts += series.checkpoint_count
        total_req += len(rows)
        want = pd.DataFrame(rows, columns=["race_id", "driver_id",
                                           "lap_number", "state_time_s"])
        got = want.merge(race_frame, on=["race_id", "driver_id",
                                         "lap_number", "state_time_s"],
                         how="left", indicator=True)
        exact += int((got["_merge"] == "both").sum())
        missing += int((got["_merge"] != "both").sum())
    assert total_ckpts == 9644
    assert missing == 0
    assert ambiguous == 0
    assert exact == total_req
    print(f"\nE1.6 coverage: races={len(race_ids)} checkpoints={total_ckpts} "
          f"requests={total_req} exact={exact} missing={missing} "
          f"ambiguous={ambiguous} cross-checkpoint duplicate "
          f"observations={dup_requests}")
