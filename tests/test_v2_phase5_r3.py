"""Phase-5 R3 prediction checkpoints + cache tests.

Model-free selection/identity/artifact tests are fast. Real generation is
a controlled subset (first 3 checkpoints of 2023-r01-R, ~12 s each);
the full backfill is NEVER launched here.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import time

import pandas as pd
import pytest

from raceintel.replay import replay as RP
from raceintel.replay.replay_predictions import (
    FLAG_TRANSITION,
    LEADER_LAP,
    PHASE4_CONTRACT_VERSION,
    REPLAY_PREDICTION_CONTRACT_VERSION,
    CheckpointCacheMissError,
    CheckpointError,
    CheckpointSeries,
    IncompleteCacheError,
    PredictionCheckpoint,
    StaleCacheError,
    artifact_path,
    build_artifact,
    cache_identity_inputs,
    cache_key,
    canonical_data_identity,
    canonical_json,
    ensure_race_artifact,
    generate_checkpoint,
    generate_race_artifact,
    load_validated_artifact,
    read_cached_prediction,
    select_checkpoints,
    series_identity,
    write_artifact,
)

D9 = ("data/v2/processed/driver_lap_state_d9/season={season}/"
      "driver_lap_state_d9__d9-{season}.parquet")
RESULTS = ("data/v2/processed/results/season={season}/"
           "results__{race}.parquet")
RACES = ("data/v2/processed/races/season={season}/"
         "races__{race}.parquet")

RACE = "2023-r01-R"
SEASON = 2023

_engine = None
_history = None
_service = None
_states = None
_series = None


def get_generation_stack():
    global _engine, _history, _service, _states, _series
    if _engine is None:
        from raceintel.config import V2Paths
        from raceintel.features.build_matrix import load_history
        from raceintel.model_lab import serving as SERVING
        from raceintel.prediction import RacePredictionEngine
        from raceintel.race_state.race_state_features import RaceStateFeatureBridge
        from raceintel.race_state.race_state_reconstruction import RaceStateReconstructor
        from raceintel.replay.replay_reconstruction import ReplayReconstructor
        states = pd.read_parquet(D9.format(season=SEASON))
        states = states[states["race_id"] == RACE].copy()
        results = pd.read_parquet(
            RESULTS.format(season=SEASON, race=RACE))
        _history = load_history(V2Paths.resolve())
        predictor = SERVING.load_frozen_winner_model()
        _engine = RacePredictionEngine(
            RaceStateFeatureBridge(states, _history), predictor)
        timeline = RP.build_replay_timeline(states)
        _service = ReplayReconstructor(
            timeline, RaceStateReconstructor(states, results))
        _states = states
        _series = select_checkpoints(timeline, states)
    return _engine, _service, _states, _series


def load_race(season: int, race_id: str) -> pd.DataFrame:
    df = pd.read_parquet(D9.format(season=season))
    return df[df["race_id"] == race_id].copy()


def tiny_states(rows: list) -> pd.DataFrame:
    return pd.DataFrame([{
        "race_id": r, "driver_id": d, "lap_number": lap,
        "state_time_s": t, "race_leader_laps_at_state": ll,
        "track_state": ts} for r, d, lap, t, ll, ts in rows])


def checkpoint(**over) -> PredictionCheckpoint:
    base = {"race_id": "r", "frame_index": 0, "anchor_driver_id": "a",
            "anchor_lap_number": 1, "anchor_state_time_s": 10.0,
            "reasons": (LEADER_LAP,), "leader_lap": 1}
    base.update(over)
    return PredictionCheckpoint(**base)


def live_inputs(series, states):
    engine, _, _, _ = get_generation_stack()
    identity = engine.model_identity
    with open("docs/PHASE4_FREEZE_MANIFEST.json") as handle:
        phase2 = json.load(handle)["phase2"]["content_hash"]
    return cache_identity_inputs(
        series=series,
        data_identity=canonical_data_identity(states, series.race_id),
        feature_set=identity.feature_set,
        feature_set_version=identity.feature_set_version,
        artifact_sha256=identity.artifact_sha256,
        specification_fingerprint=identity.specification_fingerprint,
        phase2_content_hash=phase2,
        probability_semantics=identity.probability_semantics)


# ---------------------------------------------------------------------------
# Contract versions + domain validation.
# ---------------------------------------------------------------------------

def test_contract_versions():
    assert RP.REPLAY_CONTRACT_VERSION == "v1"
    assert REPLAY_PREDICTION_CONTRACT_VERSION == "v1"
    assert PHASE4_CONTRACT_VERSION == "v1"


@pytest.mark.parametrize("reasons", [
    (), [], ("NOPE",), (LEADER_LAP, LEADER_LAP), "LEADER_LAP", None])
def test_checkpoint_rejects_bad_reasons(reasons):
    with pytest.raises(CheckpointError):
        checkpoint(reasons=reasons)


def test_checkpoint_rejects_bad_leader_lap():
    with pytest.raises(CheckpointError):
        checkpoint(leader_lap=0)
    with pytest.raises(CheckpointError):
        checkpoint(leader_lap="3")
    assert checkpoint(leader_lap=None).leader_lap is None


def test_checkpoint_frame_id_round_trip():
    frame = checkpoint().frame_id()
    assert isinstance(frame, RP.ReplayFrame)
    assert frame.anchor_driver_id == "a"
    assert frame.replay_contract_version == "v1"


def test_series_rejects_malformed():
    good = (checkpoint(), checkpoint(
        frame_index=1, anchor_driver_id="b", anchor_lap_number=2,
        anchor_state_time_s=20.0, reasons=(FLAG_TRANSITION,),
        leader_lap=1))
    with pytest.raises(CheckpointError):
        CheckpointSeries(race_id="r", replay_contract_version="v1",
                         prediction_contract_version="v1", checkpoints=())
    dup = (checkpoint(), checkpoint())
    with pytest.raises(CheckpointError):
        CheckpointSeries(race_id="r", replay_contract_version="v1",
                         prediction_contract_version="v1", checkpoints=dup)
    assert CheckpointSeries(
        race_id="r", replay_contract_version="v1",
        prediction_contract_version="v1",
        checkpoints=good).checkpoint_count == 2


# ---------------------------------------------------------------------------
# Selection: real races (model-free, fast).
# ---------------------------------------------------------------------------

def test_selection_ordinary_race_counts():
    states = load_race(2023, RACE)
    timeline = RP.build_replay_timeline(states)
    series = select_checkpoints(timeline, states)
    assert series.checkpoint_count == 61
    leader = [c for c in series.checkpoints if LEADER_LAP in c.reasons]
    flag_only = [c for c in series.checkpoints
                 if list(c.reasons) == [FLAG_TRANSITION]]
    assert len(leader) == 57
    assert len(flag_only) == 4
    assert series.checkpoints[0].frame_index == 0
    assert LEADER_LAP in series.checkpoints[0].reasons
    assert sorted(c.leader_lap for c in leader) == list(range(1, 58))


def test_selection_partial_race():
    states = load_race(2021, "2021-r12-R")
    timeline = RP.build_replay_timeline(states)
    series = select_checkpoints(timeline, states)
    laps = {c.leader_lap for c in series.checkpoints
            if LEADER_LAP in c.reasons}
    assert laps == {1, 2, 3}
    assert series.checkpoint_count < 10


def test_selection_flag_fixture_has_extras():
    states = load_race(2020, "2020-r09-R")
    timeline = RP.build_replay_timeline(states)
    series = select_checkpoints(timeline, states)
    flag_only = [c for c in series.checkpoints
                 if FLAG_TRANSITION in c.reasons]
    assert len(flag_only) > 0
    indices = [c.frame_index for c in series.checkpoints]
    assert indices == sorted(set(indices))
    for checkpoint in series.checkpoints:
        assert checkpoint.reasons == tuple(sorted(checkpoint.reasons))


def test_selection_overlapping_reasons_single_checkpoint():
    df = tiny_states([
        ("r", "a", 1, 10.0, 1, "all_clear"),
        ("r", "b", 1, 20.0, 2, "all_clear"),
        ("r", "a", 2, 30.0, 3, "safety_car"),
    ])
    series = select_checkpoints(RP.build_replay_timeline(df), df)
    assert series.checkpoint_count == 3
    last = series.checkpoints[-1]
    assert last.reasons == (FLAG_TRANSITION, LEADER_LAP)


def test_selection_needs_selector_columns():
    df = load_race(2023, RACE)[["race_id", "driver_id", "lap_number",
                                "state_time_s"]]
    with pytest.raises(CheckpointError):
        select_checkpoints(RP.build_replay_timeline(df), df)


def test_selector_is_model_free():
    probe = ("import sys, raceintel.replay.replay_predictions; "
             "banned = [m for m in sys.modules if m.startswith("
             "('sklearn', 'scipy', 'raceintel.model_lab', 'raceintel.prediction',"
             " 'raceintel.race_state.race_state_features'))]; "
             "print(','.join(sorted(banned)))")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                         text=True, cwd=".")
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", out.stdout


# ---------------------------------------------------------------------------
# Identity: determinism + invalidation via injected metadata.
# ---------------------------------------------------------------------------

def test_identity_deterministic_and_sensitive():
    states = load_race(2023, RACE)
    timeline = RP.build_replay_timeline(states)
    series = select_checkpoints(timeline, states)
    inputs = live_inputs(series, states)
    assert cache_key(inputs) == cache_key(dict(inputs))
    assert canonical_data_identity(states, RACE) == \
        canonical_data_identity(states.copy(), RACE)
    other = load_race(2023, "2023-r02-R")
    assert canonical_data_identity(
        other, "2023-r02-R") != canonical_data_identity(states, RACE)
    assert series_identity(series) == series_identity(
        select_checkpoints(timeline, states))


def test_invalidation_each_input_matters():
    states = load_race(2023, RACE)
    timeline = RP.build_replay_timeline(states)
    series = select_checkpoints(timeline, states)
    inputs = live_inputs(series, states)
    reference = cache_key(inputs)
    for field in ("replay_contract_version", "prediction_contract_version",
                  "race_id", "series_identity", "feature_set",
                  "feature_set_version", "serving_artifact_sha256",
                  "model_specification_fingerprint", "phase2_content_hash",
                  "canonical_data_identity", "probability_semantics"):
        mutated = dict(inputs)
        mutated[field] = str(mutated[field]) + "X"
        assert cache_key(mutated) != reference, field


# ---------------------------------------------------------------------------
# Artifact IO with synthetic snapshots (fast, no model).
# ---------------------------------------------------------------------------

def fake_snapshot(race="r", driver="a", lap=1, t=10.0, prob=0.4,
                  observable=True):
    entries = [{"driver_id": driver if observable else "z",
                "observable": observable,
                "winner_probability": prob if observable else None,
                "unavailable_reason": None if observable
                else "NO_OBSERVATION_AT_SNAPSHOT"}]
    return {"race_id": race, "anchor_driver_id": driver,
            "anchor_lap_number": lap, "state_time_s": t,
            "roster_size": 1, "predictions": entries}


def synthetic_series():
    return CheckpointSeries(
        race_id="r", replay_contract_version="v1",
        prediction_contract_version="v1",
        checkpoints=(checkpoint(), checkpoint(
            frame_index=1, anchor_driver_id="b", anchor_lap_number=2,
            anchor_state_time_s=20.0, reasons=(FLAG_TRANSITION,),
            leader_lap=1)))


def synthetic_inputs(series):
    return cache_identity_inputs(
        series=series, data_identity="data", feature_set="ALL_84",
        feature_set_version="v8", artifact_sha256="sha",
        specification_fingerprint="fp", phase2_content_hash="p2",
        probability_semantics="INDEPENDENT_BINARY")


def test_artifact_round_trip_and_read():
    series = synthetic_series()
    inputs = synthetic_inputs(series)
    snaps = {0: fake_snapshot(), 1: fake_snapshot(driver="b", lap=2,
                                                  t=20.0, prob=0.7)}
    artifact = build_artifact(series, snaps, {"artifact": "id"}, inputs)
    assert artifact["complete"] is True
    with tempfile.TemporaryDirectory() as tmp:
        path = artifact_path(tmp, "r")
        write_artifact(path, artifact)
        loaded = load_validated_artifact(path, expected_inputs=inputs,
                                         series=series)
        assert loaded["checkpoints"] == artifact["checkpoints"]
        assert read_cached_prediction(loaded, 1)["race_id"] == "r"
        with pytest.raises(CheckpointCacheMissError):
            read_cached_prediction(loaded, 5)


def test_subset_artifact_rejected_as_complete():
    series = synthetic_series()
    inputs = synthetic_inputs(series)
    artifact = build_artifact(series, {0: fake_snapshot()}, {"m": 1},
                              inputs)
    assert artifact["complete"] is False
    with tempfile.TemporaryDirectory() as tmp:
        path = artifact_path(tmp, "r")
        write_artifact(path, artifact)
        with pytest.raises(IncompleteCacheError):
            load_validated_artifact(path, expected_inputs=inputs,
                                    series=series)


def test_stale_and_miss_and_mismatch():
    series = synthetic_series()
    inputs = synthetic_inputs(series)
    with tempfile.TemporaryDirectory() as tmp:
        path = artifact_path(tmp, "r")
        with pytest.raises(CheckpointCacheMissError):
            load_validated_artifact(path, expected_inputs=inputs,
                                    series=series)
        artifact = build_artifact(series, {0: fake_snapshot(),
                                           1: fake_snapshot(
                                               driver="b", lap=2, t=20.0)},
                                  {"m": 1}, inputs)
        write_artifact(path, artifact)
        tampered = dict(inputs, serving_artifact_sha256="other")
        with pytest.raises(StaleCacheError):
            load_validated_artifact(path, expected_inputs=tampered,
                                    series=series)
        bad_snap = fake_snapshot(driver="WRONG")
        with pytest.raises(CheckpointError):
            build_artifact(series, {0: bad_snap}, {"m": 1}, inputs)


def test_skip_valid_existing_never_calls_engine():
    series = synthetic_series()
    inputs = synthetic_inputs(series)
    artifact = build_artifact(series, {0: fake_snapshot(),
                                       1: fake_snapshot(
                                           driver="b", lap=2, t=20.0)},
                              {"m": 1}, inputs)
    with tempfile.TemporaryDirectory() as tmp:
        path = artifact_path(tmp, "r")
        write_artifact(path, artifact)

        def boom(*a, **k):
            raise AssertionError("read path must not generate")

        status, _ = ensure_race_artifact(
            path=path, series=series, replay_service=boom, engine=boom,
            model_identity={"m": 1}, identity_inputs=inputs)
        assert status == "skipped"


def test_probability_sums_preserved_verbatim():
    # Synthetic >1 and <1 totals survive the artifact round trip exactly.
    series = synthetic_series()
    inputs = synthetic_inputs(series)
    over = fake_snapshot(prob=0.6)
    over["predictions"].append({"driver_id": "b", "observable": True,
                                "winner_probability": 0.55,
                                "unavailable_reason": None})
    over["roster_size"] = 2
    under = fake_snapshot(driver="b", lap=2, t=20.0, prob=0.02)
    under["predictions"].append({"driver_id": "a", "observable": True,
                                 "winner_probability": 0.05,
                                 "unavailable_reason": None})
    under["roster_size"] = 2
    artifact = build_artifact(series, {0: over, 1: under}, {"m": 1},
                              inputs)
    with tempfile.TemporaryDirectory() as tmp:
        path = artifact_path(tmp, "r")
        write_artifact(path, artifact)
        loaded = load_validated_artifact(path, expected_inputs=inputs,
                                         series=series)
    sums = [sum(p["winner_probability"]
                for p in e["prediction"]["predictions"])
            for e in loaded["checkpoints"]]
    assert sums[0] == pytest.approx(1.15)
    assert sums[1] == pytest.approx(0.07)
    assert "probability_share" not in canonical_json(loaded)


# ---------------------------------------------------------------------------
# Real controlled generation: first 3 checkpoints of 2023-r01-R.
# ---------------------------------------------------------------------------

def test_real_subset_generation_and_content():
    engine, service, states, series = get_generation_stack()
    subset = frozenset(c.frame_index for c in series.checkpoints[:3])
    inputs = live_inputs(series, states)
    start = time.perf_counter()
    artifact = generate_race_artifact(
        series=series, replay_service=service, engine=engine,
        model_identity=engine.model_identity.to_dict(),
        identity_inputs=inputs, only_frames=subset)
    elapsed = time.perf_counter() - start
    assert artifact["complete"] is False
    assert len(artifact["checkpoints"]) == 3
    model = artifact["model"]
    assert model["artifact_sha256"] == \
        "1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4"
    assert model["specification_fingerprint"] == \
        "3164de9e61ca94ab958e26590608824ca6c7b05de29c5398d3d204a8c329c24d"
    assert model["probability_semantics"] == "INDEPENDENT_BINARY"
    assert model["feature_set"] == "ALL_84"
    for entry in artifact["checkpoints"]:
        prediction = entry["prediction"]
        checkpoint = entry["checkpoint"]
        assert prediction["anchor_driver_id"] == \
            checkpoint["anchor_driver_id"]
        assert prediction["state_time_s"] == \
            checkpoint["anchor_state_time_s"]
        assert len(prediction["predictions"]) == prediction["roster_size"]
        for member in prediction["predictions"]:
            prob = member["winner_probability"]
            if member["observable"]:
                assert member["unavailable_reason"] is None
                assert 0.0 <= prob <= 1.0
            else:
                assert prob is None
                assert member["unavailable_reason"] == \
                    "NO_OBSERVATION_AT_SNAPSHOT"
                assert prob != 0.0
    test_real_subset_generation_and_content.elapsed = elapsed
    test_real_subset_generation_and_content.artifact = artifact


def test_real_subset_deterministic_regeneration():
    engine, service, states, series = get_generation_stack()
    subset = frozenset(c.frame_index for c in series.checkpoints[:3])
    inputs = live_inputs(series, states)
    first = generate_race_artifact(
        series=series, replay_service=service, engine=engine,
        model_identity=engine.model_identity.to_dict(),
        identity_inputs=inputs, only_frames=subset)
    second = generate_race_artifact(
        series=series, replay_service=service, engine=engine,
        model_identity=engine.model_identity.to_dict(),
        identity_inputs=inputs, only_frames=subset)
    assert canonical_json(first) == canonical_json(second)


def test_real_checkpoint_adversarial_future_mutation():
    engine, service, states, series = get_generation_stack()
    target = series.checkpoints[2]
    T = target.anchor_state_time_s
    expected = engine.predict(service.state_at(
        target.frame_index)).to_dict()
    mutated = states.copy()
    future = mutated["state_time_s"] > T
    assert future.any()
    for column in ("position", "compound", "tyre_life", "track_state",
                   "wx_air_temp_c", "rc_last_message_flag",
                   "pit_stops_completed_so_far",
                   "race_leader_laps_at_state"):
        sample = mutated.loc[~future, column].dropna()
        mutated.loc[future, column] = sample.iloc[0] if len(sample) else 0
    from raceintel.race_state.race_state_reconstruction import RaceStateReconstructor
    from raceintel.replay.replay_reconstruction import ReplayReconstructor
    results = pd.read_parquet(RESULTS.format(season=SEASON, race=RACE))
    rebuilt = ReplayReconstructor(
        RP.build_replay_timeline(mutated),
        RaceStateReconstructor(mutated, results))
    reselected = [c for c in
                  select_checkpoints(rebuilt.timeline, mutated).checkpoints
                  if c.anchor_state_time_s <= T]
    assert [(c.frame_index, c.anchor_driver_id, c.anchor_lap_number,
             c.reasons) for c in reselected] == [
                 (c.frame_index, c.anchor_driver_id, c.anchor_lap_number,
                  c.reasons) for c in series.checkpoints
                 if c.anchor_state_time_s <= T]
    assert engine.predict(
        rebuilt.state_at(target.frame_index)).to_dict() == expected


def test_real_midrace_sum_exceeds_one_stored_verbatim():
    # Real full-field checkpoint: total > 1 passes through unnormalized,
    # and the stored payload equals the live engine values exactly.
    engine, service, states, series = get_generation_stack()
    target = series.checkpoints[20]
    assert target.leader_lap == 20
    live = engine.predict(service.state_at(target.frame_index)).to_dict()
    stored = generate_checkpoint(engine, service, target)
    assert stored == live
    total = sum(p["winner_probability"] for p in live["predictions"]
                if p["winner_probability"] is not None)
    assert total > 1.0
    assert "probability_share" not in canonical_json(stored)


def test_real_subset_artifact_size_and_timing():
    # Self-sufficient single-checkpoint measurement (no cross-test state).
    engine, service, states, series = get_generation_stack()
    target = series.checkpoints[0]
    inputs = live_inputs(series, states)
    start = time.perf_counter()
    snapshot = engine.predict(
        service.state_at(target.frame_index)).to_dict()
    single_s = time.perf_counter() - start
    artifact = build_artifact(
        series, {target.frame_index: snapshot},
        engine.model_identity.to_dict(), inputs)
    size_kib = len(canonical_json(artifact)) / 1024
    print(f"\nR3 measured: single checkpoint {single_s:.1f}s; "
          f"1-checkpoint artifact {size_kib:.0f} KiB")
    assert single_s < 120.0


# ---------------------------------------------------------------------------
# 2025 firewall + CLI safety (fast subprocess, no model).
# ---------------------------------------------------------------------------

def test_cli_requires_explicit_scope():
    out = subprocess.run(
        [sys.executable, "scripts/build_replay_prediction_cache.py"],
        capture_output=True, text=True, cwd=".")
    assert out.returncode != 0  # argparse: one scope flag is required


def test_cli_rejects_2025_before_any_model_work():
    out = subprocess.run(
        [sys.executable, "scripts/build_replay_prediction_cache.py",
         "--race-id", "2025-r01-R", "--dry-run"],
        capture_output=True, text=True, cwd=".")
    assert out.returncode != 0
    assert "2025" in (out.stdout + out.stderr)


def test_cli_dry_run_reports_selection():
    out = subprocess.run(
        [sys.executable, "scripts/build_replay_prediction_cache.py",
         "--race-id", "2021-r12-R", "--dry-run"],
        capture_output=True, text=True, cwd=".")
    assert out.returncode == 0, out.stderr
    assert "2021-r12-R" in out.stdout and "checkpoints=" in out.stdout
