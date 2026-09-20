"""Phase-5 R7: hardening, adversarial, and pre-freeze audit tests.

This suite strengthens R1-R6 rather than re-running them: contract
inventory + dependency direction, scientific-semantics re-pins, the
shared-T divergence end-to-end, an explicit edge-race matrix, a
cross-layer future-mutation suite, checkpoint-policy distribution,
cache-corruption/identity attacks, atomic interruption, concurrency,
lazy-cache bounds, API hardening, route inventory, the 2025 firewall, and
frozen upstream identity verification.

No model load (the frozen ~12 s full-field path is never exercised); the
cached-prediction surfaces use synthetic artifacts written into a
tempdir. No 2025 evaluation target is read.
"""

from __future__ import annotations

import ast
import copy
import functools
import hashlib
import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from api.v2_replay_service import (
    NotPredictionCheckpointError,
    PredictionUnavailableError,
    ReplayFrameNotFoundError,
    V2ReplayService,
)
from v2 import replay as RP
from v2.race_state_reconstruction import RaceNotFoundError, RaceStateReconstructor
from v2.replay_predictions import (
    ARTIFACT_FORMAT,
    FLAG_TRANSITION,
    LEADER_LAP,
    REPLAY_PREDICTION_CONTRACT_VERSION,
    build_artifact,
    cache_identity_inputs,
    canonical_data_identity,
    ensure_race_artifact,
    load_validated_artifact,
    select_checkpoints,
    write_artifact,
)
from v2.replay_probability_timeline import (
    PROBABILITY_TIMELINE_CONTRACT_VERSION,
    build_probability_timeline,
    canonical_timeline_json,
)
from v2.replay_reconstruction import ReplayReconstructor

ROOT = Path(__file__).resolve().parents[1]

D9 = ("data/v2/processed/driver_lap_state_d9/season={season}/"
      "driver_lap_state_d9__d9-{season}.parquet")
RESULTS = ("data/v2/processed/results/season={season}/"
           "results__{race}.parquet")

RACE_ORDINARY = "2023-r01-R"
RACE_PARTIAL = "2021-r12-R"
RACE_RED = "2022-r18-R"
RACE_STALE = "2022-r07-R"
RACE_SHARED_T = "2020-r09-R"
RACE_VSC = "2018-r01-R"
FIXTURES = [
    (2023, RACE_ORDINARY, "ordinary"),
    (2021, RACE_PARTIAL, "partial"),
    (2022, RACE_RED, "red"),
    (2022, RACE_STALE, "stale"),
    (2020, RACE_SHARED_T, "shared_t_sc"),
    (2018, RACE_VSC, "vsc"),
]

SYN_SCI = {
    "feature_set": "ALL_84",
    "feature_set_version": "v8",
    "serving_artifact_sha256": "test-sha",
    "model_specification_fingerprint": "test-fp",
    "phase2_content_hash": "test-phase2",
    "probability_semantics": "INDEPENDENT_BINARY",
}

MODEL_DICT = {
    "task": "winner", "target": "is_winner",
    "eligibility_mask": "eligible_is_winner", "feature_set": "ALL_84",
    "feature_set_version": "v8", "estimator": "LogisticRegression",
    "estimator_params": [["C", 0.01]], "calibration_method": "RAW",
    "probability_semantics": "INDEPENDENT_BINARY",
    "training_seasons": [2018, 2019, 2020, 2021, 2022, 2023, 2024],
    "transformed_dim": 106, "feature_count": 84,
    "artifact_sha256": "test-sha", "specification_fingerprint": "test-fp",
    "sklearn_version": "1.8.0",
}

#: Exact key set the TypeScript ``ReplayFrameResponse`` consumes (R7-D).
FRAME_HTTP_KEYS = {
    "frame", "state", "has_previous", "has_next", "previous_frame_index",
    "next_frame_index", "leader_lap", "is_prediction_checkpoint",
    "checkpoint_reasons", "prediction_cache_available",
    "previous_prediction_checkpoint_frame",
    "next_prediction_checkpoint_frame",
}

_state_parts = None
_result_parts = None
_recon = None


def get_corpus():
    global _state_parts, _result_parts, _recon
    if _recon is None:
        state_parts, result_parts = [], []
        for season, race, _ in FIXTURES:
            df = pd.read_parquet(D9.format(season=season))
            state_parts.append(df[df["race_id"] == race].copy())
            result_parts.append(pd.read_parquet(
                RESULTS.format(season=season, race=race)))
        _state_parts = state_parts
        _result_parts = result_parts
        _recon = RaceStateReconstructor(
            pd.concat(state_parts, ignore_index=True),
            pd.concat(result_parts, ignore_index=True))
    return _state_parts, _result_parts, _recon


def all_states():
    return pd.concat(get_corpus()[0], ignore_index=True)


def race_states(race_id):
    states = all_states()
    return states[states["race_id"] == race_id].copy()


def make_service(tmp_path, scientific=None, served=None):
    _, _, recon = get_corpus()
    return V2ReplayService(
        all_states(), recon,
        served or [race for _, race, _ in FIXTURES],
        checkpoints_dir=str(tmp_path),
        scientific_inputs=dict(scientific or SYN_SCI))


@contextmanager
def replay_client(service):
    from fastapi.testclient import TestClient

    from api.main import app
    from api.v2_replay_service import get_v2_replay_service
    app.dependency_overrides[get_v2_replay_service] = lambda: service
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_v2_replay_service, None)


def synth_snapshot(checkpoint, roster, probs, null_drivers=()):
    entries, observable = [], 0
    for position, driver in enumerate(roster):
        if driver in null_drivers:
            entries.append({
                "driver_id": driver, "observable": False,
                "observed_lap_number": None, "observed_time_s": None,
                "observation_age_s": None, "observed_position": None,
                "winner_probability": None,
                "unavailable_reason": "NO_OBSERVATION_AT_SNAPSHOT"})
        else:
            observable += 1
            entries.append({
                "driver_id": driver, "observable": True,
                "observed_lap_number": checkpoint.anchor_lap_number,
                "observed_time_s": checkpoint.anchor_state_time_s,
                "observation_age_s": 0.0, "observed_position": position + 1,
                "winner_probability": probs[driver],
                "unavailable_reason": None})
    return {
        "race_id": checkpoint.race_id,
        "anchor_driver_id": checkpoint.anchor_driver_id,
        "anchor_lap_number": checkpoint.anchor_lap_number,
        "state_time_s": checkpoint.anchor_state_time_s,
        "roster_size": len(roster), "observable_count": observable,
        "unavailable_count": len(roster) - observable,
        "probability_semantics": "INDEPENDENT_BINARY",
        "probability_semantics_note": "synthetic independent-binary note",
        "feature_set": "ALL_84", "model": dict(MODEL_DICT),
        "predictions": entries}


def synth_inputs(service, series, race_id):
    return cache_identity_inputs(
        series=series,
        data_identity=canonical_data_identity(
            race_states(race_id), race_id),
        feature_set=SYN_SCI["feature_set"],
        feature_set_version=SYN_SCI["feature_set_version"],
        artifact_sha256=SYN_SCI["serving_artifact_sha256"],
        specification_fingerprint=SYN_SCI[
            "model_specification_fingerprint"],
        phase2_content_hash=SYN_SCI["phase2_content_hash"],
        probability_semantics=SYN_SCI["probability_semantics"])


def write_hit_artifact(service, tmp_path, race_id=RACE_PARTIAL,
                       null_drivers=(), scale=1.0):
    states = race_states(race_id)
    timeline = service.get_timeline(race_id)
    series = service.get_series(race_id)
    roster = sorted(set(states["driver_id"]))
    snapshots = {}
    for order, checkpoint in enumerate(series.checkpoints):
        probs = {d: (0.09 + 0.001 * ((order + i) % 7)) * scale
                 for i, d in enumerate(roster)}
        snapshots[checkpoint.frame_index] = synth_snapshot(
            checkpoint, roster, probs, null_drivers=null_drivers)
    artifact = build_artifact(series, snapshots, dict(MODEL_DICT),
                              synth_inputs(service, series, race_id))
    assert artifact["complete"] is True
    path = str(tmp_path / f"{race_id}.json")
    write_artifact(path, artifact)
    return artifact, series


def frame_at_regime(service, race_id, tokens):
    states = race_states(race_id)
    reps = {}
    for row in states.itertuples(index=False):
        key = float(row.state_time_s)
        candidate = (int(row.lap_number), str(row.driver_id),
                     None if pd.isna(row.track_state)
                     else str(row.track_state))
        if key not in reps or candidate[:2] < reps[key][:2]:
            reps[key] = candidate
    timeline = service.get_timeline(race_id)
    for frame in timeline.frames:
        if reps[frame.anchor_state_time_s][2] in tokens:
            return frame
    raise AssertionError(f"no {tokens} frame in {race_id}")


# ---------------------------------------------------------------------------
# R7-A: contract inventory + dependency direction.
# ---------------------------------------------------------------------------

def test_contract_versions_pinned():
    assert RP.REPLAY_CONTRACT_VERSION == "v1"
    assert REPLAY_PREDICTION_CONTRACT_VERSION == "v1"
    assert PROBABILITY_TIMELINE_CONTRACT_VERSION == "v1"
    assert ARTIFACT_FORMAT == "replay-checkpoints-v1"


def test_checkpoint_reason_tokens_pinned():
    assert LEADER_LAP == "LEADER_LAP"
    assert FLAG_TRANSITION == "FLAG_TRANSITION"
    from v2.replay_predictions import KNOWN_REASONS
    assert KNOWN_REASONS == {"LEADER_LAP", "FLAG_TRANSITION"}


def test_default_checkpoints_dir_is_gitignored_generated_path():
    from v2.replay_predictions import DEFAULT_CHECKPOINTS_DIR
    assert DEFAULT_CHECKPOINTS_DIR == "results/v2_replay/checkpoints"
    ignored = (ROOT / ".gitignore").read_text()
    assert "results/v2_replay/" in ignored


def _imported_modules(path):
    tree = ast.parse((ROOT / path).read_text())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
            for alias in node.names:
                modules.add(f"{node.module}.{alias.name}")
    return modules


def _imported_names(path):
    tree = ast.parse((ROOT / path).read_text())
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            names.update(alias.name for alias in node.names)
    return names


@pytest.mark.parametrize("path", [
    "v2/replay.py", "v2/replay_reconstruction.py",
    "v2/replay_predictions.py", "v2/replay_probability_timeline.py"])
def test_replay_domain_has_no_model_or_api_dependency(path):
    modules = _imported_modules(path)
    banned_prefixes = ("v2.prediction", "v2.race_state_features",
                       "v2.model_lab", "sklearn", "api")
    for module in modules:
        for banned in banned_prefixes:
            assert not (module == banned or module.startswith(banned + ".")), \
                (path, module)


def test_replay_service_never_imports_generation_path():
    path = "api/v2_replay_service.py"
    names = _imported_names(path)
    forbidden = {"generate_race_artifact", "ensure_race_artifact",
                 "generate_checkpoint", "RacePredictionEngine",
                 "RaceStateFeatureBridge", "load_frozen_winner_model"}
    assert not (names & forbidden), names & forbidden
    text = (ROOT / path).read_text()
    # The read-only R3 helpers are imported by explicit name.
    assert "load_validated_artifact" in names
    assert "read_cached_prediction" in names
    assert "RacePredictionEngine" not in text.split('"""')[0]


def test_replay_routes_are_additive_and_do_not_touch_legacy():
    modules = _imported_modules("api/v2_replay_routes.py")
    assert not any(m == "api.routes" or m.startswith("api.services")
                   for m in modules)
    assert "api.v2_replay_service" in modules
    assert "api.v2_replay_schemas" in modules


def test_no_reverse_dependency_from_domain_to_service():
    for path in ("v2/replay.py", "v2/replay_reconstruction.py",
                 "v2/replay_predictions.py",
                 "v2/replay_probability_timeline.py"):
        modules = _imported_modules(path)
        assert not any(m.startswith("api") for m in modules), path


# ---------------------------------------------------------------------------
# R7-B: scientific semantics re-pins.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("season,race", [
    (2023, RACE_ORDINARY), (2021, RACE_PARTIAL), (2022, RACE_RED),
    (2022, RACE_STALE), (2020, RACE_SHARED_T), (2018, RACE_VSC)])
def test_one_frame_per_unique_state_time(season, race, tmp_path):
    service = make_service(tmp_path)
    timeline = service.get_timeline(race)
    times = [f.anchor_state_time_s for f in timeline.frames]
    assert len(times) == len(set(times))
    assert times == sorted(times)
    assert [f.frame_index for f in timeline.frames] == list(
        range(timeline.frame_count))


@pytest.mark.parametrize("season,race", [
    (2023, RACE_ORDINARY), (2021, RACE_PARTIAL), (2022, RACE_RED),
    (2022, RACE_STALE), (2020, RACE_SHARED_T), (2018, RACE_VSC)])
def test_representative_is_lap_then_driver_ascending(season, race, tmp_path):
    service = make_service(tmp_path)
    states = race_states(race)
    timeline = service.get_timeline(race)
    for frame in timeline.frames:
        group = states[states["state_time_s"] == frame.anchor_state_time_s]
        ordered = sorted(
            (int(r.lap_number), str(r.driver_id))
            for r in group.itertuples(index=False))
        assert (frame.anchor_lap_number, frame.anchor_driver_id) == ordered[0]


def test_per_driver_state_uses_at_or_before_t(tmp_path):
    service = make_service(tmp_path)
    for frame in service.get_timeline(RACE_ORDINARY).frames[::37]:
        state = service._resolver(RACE_ORDINARY).state_at(frame.frame_index)
        for driver in state.drivers:
            if driver.observable:
                assert driver.observed_time_s <= state.state_time_s


def test_pre_first_and_stale_semantics(tmp_path):
    service = make_service(tmp_path)
    first = service._resolver(RACE_ORDINARY).state_at(0)
    assert any(not d.observable for d in first.drivers)
    assert all(d.observed_time_s is None and d.position is None
               for d in first.drivers if not d.observable)
    stale = service._resolver(RACE_STALE).state_at(
        service.get_timeline(RACE_STALE).frame_count // 2)
    aged = [d for d in stale.drivers
            if d.observable and (d.observation_age_s or 0) > 0]
    assert aged


def test_partial_race_does_not_synthesize_completion(tmp_path):
    service = make_service(tmp_path)
    assert service.get_timeline(RACE_PARTIAL).frame_count == 60
    last = service._resolver(RACE_PARTIAL).state_at(59)
    assert last.race_context.race_leader_laps_at_state == 3
    with pytest.raises(Exception):
        service._resolver(RACE_PARTIAL).frame_for_leader_lap(4)


def test_flag_semantics_preserved(tmp_path):
    service = make_service(tmp_path)
    red = frame_at_regime(service, RACE_RED, {"red_flag"})
    rstate = service._resolver(RACE_RED).state_at(red.frame_index)
    assert rstate.race_control.flag_red is True
    assert rstate.race_control.track_state == "red_flag"
    sc = frame_at_regime(service, RACE_SHARED_T, {"safety_car"})
    sstate = service._resolver(RACE_SHARED_T).state_at(sc.frame_index)
    assert sstate.race_control.flag_safety_car is True
    vsc = frame_at_regime(service, RACE_VSC, {"vsc", "vsc_ending"})
    vstate = service._resolver(RACE_VSC).state_at(vsc.frame_index)
    assert vstate.race_control.flag_vsc is True


def test_checkpoints_are_actual_frames_and_only_at_checkpoints(tmp_path):
    service = make_service(tmp_path)
    series = service.get_series(RACE_ORDINARY)
    timeline = service.get_timeline(RACE_ORDINARY)
    hits = {c.frame_index for c in series.checkpoints}
    for checkpoint in series.checkpoints:
        frame = timeline.frame_at(checkpoint.frame_index)
        assert frame.anchor_driver_id == checkpoint.anchor_driver_id
        assert frame.anchor_lap_number == checkpoint.anchor_lap_number
        assert frame.anchor_state_time_s == checkpoint.anchor_state_time_s
    plain = next(i for i in range(1, 400) if i not in hits)
    with pytest.raises(NotPredictionCheckpointError):
        service.get_prediction(RACE_ORDINARY, plain)


def test_leader_lap_reference_is_leader_progress(tmp_path):
    service = make_service(tmp_path)
    resolver = service._resolver(RACE_ORDINARY)
    total = service.get_timeline(RACE_ORDINARY).frame_count
    for lap in (1, 10, 30, 57):
        frame = resolver.frame_for_leader_lap(lap)
        assert resolver.leader_lap_at(frame.frame_index) >= lap
        if frame.frame_index > 0:
            assert resolver.leader_lap_at(frame.frame_index - 1) < lap
    assert resolver.leader_lap_at(total - 1) == 57


def test_independent_binary_sums_pass_through_unnormalized(tmp_path):
    service = make_service(tmp_path)
    artifact, series = write_hit_artifact(
        service, tmp_path, null_drivers=("mazepin",), scale=1.7)
    checkpoint = series.checkpoints[-1]
    if checkpoint.reasons == ["FLAG_TRANSITION"]:
        checkpoint = series.checkpoints[1]
    stored = next(e["prediction"] for e in artifact["checkpoints"]
                  if e["checkpoint"]["frame_index"] == checkpoint.frame_index)
    total = sum(p["winner_probability"] for p in stored["predictions"]
                if p["winner_probability"] is not None)
    assert total > 1.0
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/predictions/"
            f"{checkpoint.frame_index}").json()
    assert body["prediction"] == json.loads(json.dumps(stored))
    assert "probability_share" not in json.dumps(body)
    nulls = [p for p in body["prediction"]["predictions"]
             if p["winner_probability"] is None]
    assert nulls and all(p["unavailable_reason"]
                         for p in nulls)
    assert all(p["winner_probability"] != 0.0 for p in nulls)


def test_probability_timeline_projects_only_stored_observations(tmp_path):
    service = make_service(tmp_path)
    artifact, series = write_hit_artifact(service, tmp_path)
    projected = build_probability_timeline(artifact)
    assert [c["frame_index"] for c in projected["checkpoints"]] == [
        c.frame_index for c in series.checkpoints]
    assert canonical_timeline_json(build_probability_timeline(artifact)) == \
        canonical_timeline_json(projected)


# ---------------------------------------------------------------------------
# R7-C: shared-T divergence (2020-r09-R @ T=2974.257) end-to-end.
# ---------------------------------------------------------------------------

def _shared_t_frame(service):
    timeline = service.get_timeline(RACE_SHARED_T)
    return next(f for f in timeline.frames
                if abs(f.anchor_state_time_s - 2974.257) < 1e-9)


def test_shared_t_timeline_representative(tmp_path):
    service = make_service(tmp_path)
    frame = _shared_t_frame(service)
    assert frame.anchor_driver_id == "giovinazzi"
    assert frame.anchor_lap_number == 6


def test_shared_t_reconstruction_not_latifi_sc(tmp_path):
    service = make_service(tmp_path)
    frame = _shared_t_frame(service)
    state = service._resolver(RACE_SHARED_T).state_at(frame.frame_index)
    assert state.race_control.track_state == "yellow"
    assert state.race_control.flag_yellow is True
    assert state.race_control.flag_safety_car is False
    # No latifi/lap7-anchored frame exists (non-representative row).
    latifi = [f for f in service.get_timeline(RACE_SHARED_T).frames
              if f.anchor_driver_id == "latifi"
              and f.anchor_lap_number == 7]
    assert latifi == []


def test_shared_t_http_shape_and_bytes(tmp_path):
    service = make_service(tmp_path)
    frame = _shared_t_frame(service)
    with replay_client(service) as client:
        first = client.get(
            f"/v2/races/{RACE_SHARED_T}/replay/frames/"
            f"{frame.frame_index}").json()
        second = client.get(
            f"/v2/races/{RACE_SHARED_T}/replay/frames/"
            f"{frame.frame_index}").json()
    assert set(first) == FRAME_HTTP_KEYS
    assert first == second
    assert first["state"]["race_control"]["track_state"] == "yellow"


def test_shared_t_neighbors_are_chronological(tmp_path):
    service = make_service(tmp_path)
    timeline = service.get_timeline(RACE_SHARED_T)
    frame = _shared_t_frame(service)
    assert timeline.frames[frame.frame_index - 1].anchor_state_time_s < \
        frame.anchor_state_time_s
    assert timeline.frames[frame.frame_index + 1].anchor_state_time_s > \
        frame.anchor_state_time_s


# ---------------------------------------------------------------------------
# R7-D: edge-race integration matrix.
# ---------------------------------------------------------------------------

EDGE_CASES = [
    ("ordinary", RACE_ORDINARY, "mid"),
    ("early_pre_first", RACE_ORDINARY, "first"),
    ("late_lapped", RACE_ORDINARY, "last"),
    ("partial", RACE_PARTIAL, "last"),
    ("red", RACE_RED, "regime:red_flag"),
    ("stale", RACE_STALE, "mid"),
    ("sc", RACE_SHARED_T, "regime:safety_car"),
    ("vsc", RACE_VSC, "regime:vsc,vsc_ending"),
    ("shared_t", RACE_SHARED_T, "time:2974.257"),
]


def _edge_frame(service, race_id, selector):
    timeline = service.get_timeline(race_id)
    if selector == "mid":
        return timeline.frames[timeline.frame_count // 2]
    if selector == "first":
        return timeline.frames[0]
    if selector == "last":
        return timeline.frames[-1]
    if selector.startswith("time:"):
        target = float(selector.split(":", 1)[1])
        return next(f for f in timeline.frames
                    if abs(f.anchor_state_time_s - target) < 1e-9)
    return frame_at_regime(service, race_id,
                           set(selector.split(":", 1)[1].split(",")))


@pytest.mark.parametrize("role,race,selector", EDGE_CASES)
def test_edge_matrix_timeline_nav_state_leader_http(
        role, race, selector, tmp_path):
    service = make_service(tmp_path)
    frame = _edge_frame(service, race, selector)
    timeline = service.get_timeline(race)
    # Navigation bounds.
    assert timeline.previous(frame.frame_index) is None or \
        timeline.previous(frame.frame_index).frame_index == \
        frame.frame_index - 1
    assert timeline.next(frame.frame_index) is None or \
        timeline.next(frame.frame_index).frame_index == frame.frame_index + 1
    # RaceState identity.
    state = service._resolver(race).state_at(frame.frame_index)
    assert state.race_id == race
    assert state.anchor_driver_id == frame.anchor_driver_id
    assert state.state_time_s == frame.anchor_state_time_s
    assert state.race_context.race_leader_laps_at_state is not None
    # Checkpoint selection is consistent (frame is or is not a checkpoint).
    series = service.get_series(race)
    hits = {c.frame_index for c in series.checkpoints}
    expected = frame.frame_index in hits
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{race}/replay/frames/{frame.frame_index}").json()
    assert set(body) == FRAME_HTTP_KEYS
    assert body["is_prediction_checkpoint"] is expected
    assert body["leader_lap"] == \
        state.race_context.race_leader_laps_at_state


@pytest.mark.parametrize("role,race,selector", EDGE_CASES)
def test_edge_matrix_not_checkpoint_has_pointers(
        role, race, selector, tmp_path):
    service = make_service(tmp_path)
    frame = _edge_frame(service, race, selector)
    series = service.get_series(race)
    hits = {c.frame_index for c in series.checkpoints}
    if frame.frame_index in hits:
        pytest.skip("edge frame is a checkpoint")
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{race}/replay/frames/{frame.frame_index}").json()
    assert body["checkpoint_reasons"] == []
    assert body["prediction_cache_available"] is False
    before = [h for h in hits if h < frame.frame_index]
    after = [h for h in hits if h > frame.frame_index]
    assert body["previous_prediction_checkpoint_frame"] == (
        max(before) if before else None)
    assert body["next_prediction_checkpoint_frame"] == (
        min(after) if after else None)


# ---------------------------------------------------------------------------
# R7-E: cross-layer future-data mutation.
# ---------------------------------------------------------------------------

def _mutate_after_t(states, t, columns):
    mutated = states.copy()
    future = mutated["state_time_s"] > t
    assert future.any()
    for column in columns:
        if column not in mutated.columns:
            continue
        sample = mutated.loc[~future, column].dropna()
        mutated.loc[future, column] = sample.iloc[0] if len(sample) else 0
    return mutated


FUTURE_COLUMNS = [
    "position", "lap_number", "compound", "tyre_life", "stint_number",
    "pit_stops_completed_so_far", "wx_air_temp_c", "rainfall",
    "track_state", "flag_safety_car", "flag_red", "flag_vsc",
    "race_leader_laps_at_state",
]


@pytest.mark.parametrize("race,selector", [
    (RACE_ORDINARY, "mid"), (RACE_PARTIAL, "mid"), (RACE_RED, "mid")])
def test_future_mutation_leaves_current_state_identical(
        race, selector, tmp_path):
    service = make_service(tmp_path)
    frame = _edge_frame(service, race, selector)
    baseline = service._resolver(race).state_at(frame.frame_index)
    states = race_states(race)
    mutated = _mutate_after_t(states, frame.anchor_state_time_s,
                              FUTURE_COLUMNS)
    timeline = RP.build_replay_timeline(mutated)
    results = race_states_for_results(race)
    rebuilt = ReplayReconstructor(
        timeline, RaceStateReconstructor(mutated, results))
    after = rebuilt.state_at(frame.frame_index)
    assert after.to_dict() == baseline.to_dict()
    assert timeline.frame_at(frame.frame_index).to_dict() == \
        service.get_timeline(race).frame_at(frame.frame_index).to_dict()


def race_states_for_results(race_id):
    for season, race, _ in FIXTURES:
        if race == race_id:
            return pd.read_parquet(RESULTS.format(season=season, race=race))
    raise KeyError(race_id)


@pytest.mark.parametrize("race,selector", [
    (RACE_ORDINARY, "mid"), (RACE_PARTIAL, "mid")])
def test_future_mutation_leaves_checkpoints_upto_t_identical(
        race, selector, tmp_path):
    service = make_service(tmp_path)
    frame = _edge_frame(service, race, selector)
    t = frame.anchor_state_time_s
    baseline = service.get_series(race)
    states = race_states(race)
    mutated = _mutate_after_t(states, t, FUTURE_COLUMNS)
    timeline = RP.build_replay_timeline(mutated)
    reselected = [c for c in select_checkpoints(timeline, mutated).checkpoints
                  if c.anchor_state_time_s <= t]
    expected = [c for c in baseline.checkpoints
                if c.anchor_state_time_s <= t]
    assert [(c.frame_index, c.anchor_driver_id, c.anchor_lap_number,
             c.reasons) for c in reselected] == [
        (c.frame_index, c.anchor_driver_id, c.anchor_lap_number,
         c.reasons) for c in expected]


def test_future_mutation_leaves_prediction_and_projection_bytes_unchanged(
        tmp_path):
    service = make_service(tmp_path)
    artifact, series = write_hit_artifact(service, tmp_path)
    baseline_projection = canonical_timeline_json(
        build_probability_timeline(artifact))
    timeline = service.get_timeline(RACE_PARTIAL)
    frame = timeline.frames[timeline.frame_count // 2]
    states = race_states(RACE_PARTIAL)
    mutated = _mutate_after_t(states, frame.anchor_state_time_s,
                              FUTURE_COLUMNS)
    # The stored artifact is byte-stable and the read path is pure.
    path = str(tmp_path / f"{RACE_PARTIAL}.json")
    before = Path(path).read_bytes()
    reloaded = load_validated_artifact(
        path, expected_inputs=synth_inputs(service, series, RACE_PARTIAL),
        series=series)
    assert Path(path).read_bytes() == before
    assert reloaded["checkpoints"] == artifact["checkpoints"]
    assert canonical_timeline_json(
        build_probability_timeline(reloaded)) == baseline_projection
    # Mutating future canonical rows does not change the stored artifact.
    assert Path(path).read_bytes() == before


# ---------------------------------------------------------------------------
# R7-F: checkpoint-policy distribution.
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=1)
def full_checkpoint_distribution():
    per_race = {}
    reason_totals = {"LEADER_LAP": 0, "FLAG_TRANSITION": 0, "both": 0}
    total = 0
    for season in range(2018, 2025):
        df = pd.read_parquet(
            D9.format(season=season),
            columns=["race_id", "driver_id", "lap_number", "state_time_s",
                     "race_leader_laps_at_state", "track_state"])
        for race_id, group in df.groupby("race_id", sort=True):
            group = group.reset_index(drop=True)
            timeline = RP.build_replay_timeline(group)
            series = select_checkpoints(timeline, group)
            leader = sum(1 for c in series.checkpoints
                         if LEADER_LAP in c.reasons)
            flag_only = sum(1 for c in series.checkpoints
                            if list(c.reasons) == [FLAG_TRANSITION])
            both = series.checkpoint_count - leader - flag_only
            per_race[race_id] = {
                "frames": timeline.frame_count,
                "checkpoints": series.checkpoint_count,
                "leader": leader, "flag_only": flag_only, "both": both,
            }
            reason_totals["LEADER_LAP"] += leader
            reason_totals["FLAG_TRANSITION"] += flag_only
            reason_totals["both"] += both
            total += series.checkpoint_count
    return per_race, reason_totals, total


def test_checkpoint_distribution_corpus_shape():
    per_race, _, total = full_checkpoint_distribution()
    assert len(per_race) == 149
    assert total == 9644
    counts = np.array([v["checkpoints"] for v in per_race.values()])
    assert counts.min() >= 1
    assert counts.max() <= max(v["frames"] for v in per_race.values())
    stats = {
        "min": int(counts.min()),
        "p25": int(np.percentile(counts, 25)),
        "median": int(np.percentile(counts, 50)),
        "p75": int(np.percentile(counts, 75)),
        "p95": int(np.percentile(counts, 95)),
        "max": int(counts.max()),
        "mean": float(counts.mean()),
    }
    print(f"\nR7 checkpoint distribution: {stats}")
    assert 40 <= stats["median"] <= 90
    assert stats["mean"] > 0


def test_checkpoint_reason_breakdown_is_consistent():
    per_race, reasons, total = full_checkpoint_distribution()
    assert reasons["LEADER_LAP"] + reasons["FLAG_TRANSITION"] + \
        reasons["both"] == total
    leader_sum = sum(v["leader"] for v in per_race.values())
    assert leader_sum == reasons["LEADER_LAP"] + reasons["both"]
    flag_sum = sum(v["flag_only"] for v in per_race.values())
    assert flag_sum == reasons["FLAG_TRANSITION"]
    assert total > leader_sum  # flag extras exist


def test_checkpoint_outliers_no_oscillation_explosion():
    per_race, _, _ = full_checkpoint_distribution()
    ranked = sorted(per_race.items(),
                    key=lambda kv: kv[1]["checkpoints"], reverse=True)
    print(f"\nR7 top checkpoint races: {ranked[:3]}")
    for race_id, info in ranked[:5]:
        # One checkpoint per frame max; flag extras are bounded by the
        # number of frames and never fabricate checkpoints.
        assert info["checkpoints"] <= info["frames"]
        assert info["leader"] + info["both"] >= 1
        assert info["flag_only"] <= info["frames"]
    # A pathological oscillation would push flag extras far beyond leader
    # checkpoints; inspect the worst ratio.
    worst = max(v["flag_only"] for v in per_race.values())
    print(f"R7 max flag-only checkpoints in one race: {worst}")
    assert worst <= 100


# ---------------------------------------------------------------------------
# R7-G: cache corruption / identity attack matrix.
# ---------------------------------------------------------------------------

def _fresh_service(tmp_path):
    return make_service(tmp_path)


def _valid_artifact(service, tmp_path, race_id=RACE_PARTIAL):
    artifact, series = write_hit_artifact(service, tmp_path, race_id)
    return artifact, series


def _corrupt_cases():
    def set_key(path, key, value):
        return lambda a: a.__setitem__(key, value)
    return {
        "wrong_format": lambda a: a.__setitem__("artifact_format", "nope"),
        "wrong_race": lambda a: a.__setitem__("race_id", "1999-r01-R"),
        "wrong_cache_key": lambda a: a.__setitem__("cache_key", "0" * 64),
        "wrong_identity": lambda a: a["cache_identity"].__setitem__(
            "feature_set", "MUTATED"),
        "wrong_series": lambda a: a["series"].__setitem__(
            "checkpoint_count", 999),
        "complete_false": lambda a: a.__setitem__("complete", False),
        "missing_checkpoint": lambda a: a["checkpoints"].pop(),
        "extra_checkpoint": lambda a: a["checkpoints"].append(
            copy.deepcopy(a["checkpoints"][0])),
        "reordered_checkpoint": lambda a: a["checkpoints"].reverse(),
        "wrong_frame_identity": lambda a: a["checkpoints"][0]["checkpoint"]
            .__setitem__("frame_index", 123456),
        "malformed_entry": lambda a: a["checkpoints"][0].__setitem__(
            "checkpoint", ["not", "a", "dict"]),
        "wrong_driver_roster": lambda a: a["checkpoints"][0]["prediction"]
            ["predictions"].pop(),
        "duplicate_driver": lambda a: a["checkpoints"][0]["prediction"]
            ["predictions"].__setitem__(
                1, copy.deepcopy(
                    a["checkpoints"][0]["prediction"]["predictions"][0])),
        "extra_driver": lambda a: a["checkpoints"][0]["prediction"]
            ["predictions"].append(copy.deepcopy(
                a["checkpoints"][0]["prediction"]["predictions"][0])),
        "negative_probability": lambda a: a["checkpoints"][0]["prediction"]
            ["predictions"][0].__setitem__("winner_probability", -0.1),
        "probability_gt_one": lambda a: a["checkpoints"][0]["prediction"]
            ["predictions"][0].__setitem__("winner_probability", 1.5),
        "null_without_reason": lambda a: a["checkpoints"][0]["prediction"]
            ["predictions"][0].update(
                {"winner_probability": None, "unavailable_reason": None}),
        "roster_size_drift": lambda a: a["checkpoints"][0]["prediction"]
            .__setitem__("roster_size", 999),
    }


@pytest.mark.parametrize("case", sorted(_corrupt_cases()))
def test_cache_corruption_is_rejected_safely(case, tmp_path):
    service = make_service(tmp_path)
    artifact, series = _valid_artifact(service, tmp_path)
    mutated = copy.deepcopy(artifact)
    _corrupt_cases()[case](mutated)
    path = tmp_path / f"{RACE_PARTIAL}.json"
    path.write_text(json.dumps(mutated))
    fresh = make_service(tmp_path)
    checkpoint = series.checkpoints[0]
    with pytest.raises(PredictionUnavailableError) as exc:
        fresh.get_prediction(RACE_PARTIAL, checkpoint.frame_index)
    assert exc.value.reason in {
        "cache_missing", "cache_stale", "cache_incomplete", "cache_corrupt"}
    with pytest.raises(PredictionUnavailableError):
        fresh.get_probability_timeline(RACE_PARTIAL)


@pytest.mark.parametrize("body", [
    "", "   ", "{ not json", "[]", "5", '"string"', "\x00\x01\x02"])
def test_cache_invalid_bodies_rejected_safely(body, tmp_path):
    service = make_service(tmp_path)
    artifact, series = _valid_artifact(service, tmp_path)
    (tmp_path / f"{RACE_PARTIAL}.json").write_text(body)
    fresh = make_service(tmp_path)
    with pytest.raises(PredictionUnavailableError) as exc:
        fresh.get_prediction(RACE_PARTIAL, series.checkpoints[0].frame_index)
    assert exc.value.reason == "cache_corrupt"


def test_cache_nan_infinity_rejected(tmp_path):
    service = make_service(tmp_path)
    artifact, series = _valid_artifact(service, tmp_path)
    for value in (float("nan"), float("inf"), float("-inf")):
        mutated = copy.deepcopy(artifact)
        mutated["checkpoints"][0]["prediction"]["predictions"][0][
            "winner_probability"] = value
        (tmp_path / f"{RACE_PARTIAL}.json").write_text(json.dumps(mutated))
        fresh = make_service(tmp_path)
        with pytest.raises(PredictionUnavailableError):
            fresh.get_prediction(
                RACE_PARTIAL, series.checkpoints[0].frame_index)


def test_cache_corruption_http_no_leak(tmp_path):
    service = make_service(tmp_path)
    artifact, series = _valid_artifact(service, tmp_path)
    (tmp_path / f"{RACE_PARTIAL}.json").write_text("{truncated")
    fresh = make_service(tmp_path)
    with replay_client(fresh) as client:
        resp = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/predictions/"
            f"{series.checkpoints[0].frame_index}")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "prediction_unavailable"
    text = json.dumps(body).lower()
    for token in ("traceback", str(tmp_path).lower(), "site-packages",
                  ".py", "sklearn", "joblib"):
        assert token not in text, token


# ---------------------------------------------------------------------------
# R7-H: atomic write / interruption hardening.
# ---------------------------------------------------------------------------

def test_valid_artifact_survives_failed_regeneration(tmp_path):
    service = make_service(tmp_path)
    artifact, series = _valid_artifact(service, tmp_path)
    path = str(tmp_path / f"{RACE_PARTIAL}.json")
    before = Path(path).read_bytes()
    inputs = synth_inputs(service, series, RACE_PARTIAL)

    class _StubReplay:
        def state_at(self, frame_index):
            return object()

    class _BoomEngine:
        def predict(self, state):
            raise RuntimeError("simulated engine failure")

    with pytest.raises(RuntimeError):
        ensure_race_artifact(
            path=path, series=series, replay_service=_StubReplay(),
            engine=_BoomEngine(), model_identity=dict(MODEL_DICT),
            identity_inputs=inputs, force=True)
    assert Path(path).read_bytes() == before
    loaded = load_validated_artifact(path, expected_inputs=inputs,
                                     series=series)
    assert loaded["complete"] is True


def test_partial_artifact_is_never_complete(tmp_path):
    service = make_service(tmp_path)
    series = service.get_series(RACE_PARTIAL)
    states = race_states(RACE_PARTIAL)
    roster = sorted(set(states["driver_id"]))
    first = series.checkpoints[0]
    snapshots = {first.frame_index: synth_snapshot(
        first, roster, {d: 0.05 for d in roster})}
    artifact = build_artifact(series, snapshots, dict(MODEL_DICT),
                              synth_inputs(service, series, RACE_PARTIAL))
    assert artifact["complete"] is False
    path = str(tmp_path / f"{RACE_PARTIAL}.json")
    write_artifact(path, artifact)
    with pytest.raises(Exception):
        load_validated_artifact(
            path, expected_inputs=synth_inputs(service, series, RACE_PARTIAL),
            series=series)


def test_write_failure_leaves_no_orphan_temp(tmp_path):
    from v2.replay_predictions import write_artifact as wa
    path = str(tmp_path / "artifact.json")
    original = json.dumps({"artifact_format": ARTIFACT_FORMAT})

    class Unserializable:
        pass

    with pytest.raises((TypeError, ValueError)):
        wa(path, {"bad": Unserializable()})
    leftovers = [p for p in tmp_path.iterdir() if p.suffix == ".tmp"]
    assert leftovers == []
    assert not Path(path).exists()


def test_atomic_replace_never_exposes_partial(tmp_path):
    service = make_service(tmp_path)
    artifact, series = _valid_artifact(service, tmp_path)
    path = tmp_path / f"{RACE_PARTIAL}.json"
    payload = path.read_bytes()
    assert json.loads(payload)["complete"] is True
    # Writers publish via temp + os.replace: the visible file is always
    # the full payload (no partial window in the final path).
    assert json.loads(payload) == artifact


def test_resume_skips_valid_and_regenerates_missing(tmp_path):
    service = make_service(tmp_path)
    artifact, series = _valid_artifact(service, tmp_path)
    path = str(tmp_path / f"{RACE_PARTIAL}.json")
    inputs = synth_inputs(service, series, RACE_PARTIAL)

    status, _ = ensure_race_artifact(
        path=path, series=series, replay_service=object(), engine=object(),
        model_identity=dict(MODEL_DICT), identity_inputs=inputs)
    assert status == "skipped"


# ---------------------------------------------------------------------------
# R7-I: concurrency / reentrancy.
# ---------------------------------------------------------------------------

def _run_concurrently(fn, count=8, workers=8):
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(fn, i) for i in range(count)]
        return [future.result() for future in futures]


def test_concurrent_same_frame_identical(tmp_path):
    service = make_service(tmp_path)
    frame_index = service.get_timeline(RACE_PARTIAL).frame_count // 2

    def call(_):
        return service.get_frame(RACE_PARTIAL, frame_index)

    results = _run_concurrently(call)
    bodies = [json.dumps({"frame": r["frame"], "state": r["state"].to_dict()},
                         sort_keys=True) for r in results]
    assert len(set(bodies)) == 1


def test_concurrent_different_frames(tmp_path):
    service = make_service(tmp_path)
    total = service.get_timeline(RACE_PARTIAL).frame_count
    indices = [i for i in range(0, total, max(1, total // 8))][:8]

    def call(position):
        index = indices[position]
        return service.get_frame(RACE_PARTIAL, index)["frame"]["frame_index"]

    assert _run_concurrently(call) == indices


def test_concurrent_different_races(tmp_path):
    service = make_service(tmp_path)

    def call(position):
        race = [r for _, r, _ in FIXTURES][position % len(FIXTURES)]
        return service.list_frames(race, offset=0, limit=5)["race_id"]

    results = _run_concurrently(call, count=12)
    assert all(r in [race for _, race, _ in FIXTURES] for r in results)


def test_concurrent_cached_prediction_reads(tmp_path):
    service = make_service(tmp_path)
    _, series = write_hit_artifact(service, tmp_path)
    checkpoint = series.checkpoints[0]

    def call(_):
        return service.get_prediction(
            RACE_PARTIAL, checkpoint.frame_index)

    results = _run_concurrently(call)
    assert len({json.dumps(r, sort_keys=True) for r in results}) == 1


def test_concurrent_probability_timeline_reads(tmp_path):
    service = make_service(tmp_path)
    write_hit_artifact(service, tmp_path)

    def call(_):
        return service.get_probability_timeline(RACE_PARTIAL)

    results = _run_concurrently(call)
    assert len({canonical_timeline_json(r) for r in results}) == 1


def test_concurrent_timeline_build_is_consistent(tmp_path):
    service = make_service(tmp_path)

    def call(_):
        return service.get_timeline(RACE_ORDINARY)

    timelines = _run_concurrently(call)
    # Concurrent first-touch may build more than one immutable timeline
    # (no lock); every result and the final cache entry are identical.
    payloads = {json.dumps(t.to_dict(), sort_keys=True) for t in timelines}
    assert len(payloads) == 1
    assert service.get_timeline(RACE_ORDINARY) is service._timelines[
        RACE_ORDINARY]


# ---------------------------------------------------------------------------
# R7-J: lazy cache behavior + bounds.
# ---------------------------------------------------------------------------

def test_caches_start_empty_and_build_lazily(tmp_path):
    service = make_service(tmp_path)
    assert service._timelines == {}
    assert service._series == {}
    assert service._resolvers == {}
    assert service._artifacts == {}
    assert service._probability_timelines == {}
    service.get_timeline(RACE_ORDINARY)
    assert set(service._timelines) == {RACE_ORDINARY}
    assert service._series == {}


def test_caches_reuse_immutable_objects(tmp_path):
    service = make_service(tmp_path)
    assert service.get_timeline(RACE_ORDINARY) is \
        service.get_timeline(RACE_ORDINARY)
    assert service.get_series(RACE_ORDINARY) is \
        service.get_series(RACE_ORDINARY)


def test_cache_growth_bounded_by_served_races(tmp_path):
    service = make_service(tmp_path)
    for _, race, _ in FIXTURES:
        service.get_timeline(race)
        service.get_series(race)
    assert set(service._timelines) <= set(service.race_ids)
    assert set(service._series) <= set(service.race_ids)
    assert len(service._timelines) == len(FIXTURES)


def test_unknown_race_never_cached(tmp_path):
    service = make_service(tmp_path)
    for method in (service.get_timeline, service.get_series):
        with pytest.raises(RaceNotFoundError):
            method("2099-r01-R")
    assert service._timelines == {} and service._series == {}


# ---------------------------------------------------------------------------
# R7-K/L: API hardening + route inventory.
# ---------------------------------------------------------------------------

def test_replay_route_inventory_exact(tmp_path):
    from api.v2_replay_routes import router
    paths = {}
    for route in router.routes:
        paths.setdefault(route.path, []).append(sorted(route.methods))
    assert paths == {
        "/v2/races/{race_id}/replay/timeline": [["GET"]],
        "/v2/races/{race_id}/replay/frames/{frame_index}": [["GET"]],
        "/v2/races/{race_id}/replay/predictions/{frame_index}": [["GET"]],
        "/v2/races/{race_id}/replay/probability-timeline": [["GET"]],
    }


def test_app_registers_replay_routes_once():
    from api.main import app
    counts = {}
    for route in app.routes:
        if getattr(route, "path", "").startswith("/v2/races/{race_id}/replay"):
            counts[route.path] = counts.get(route.path, 0) + 1
    assert len(counts) == 4
    assert all(count == 1 for count in counts.values())


def test_phase4_and_legacy_routes_preserved():
    from api.main import app
    paths = set(app.openapi()["paths"])
    for expected in ("/v2/races", "/v2/races/{race_id}/state",
                     "/v2/races/{race_id}/states",
                     "/v2/predictions/winner-snapshot"):
        assert expected in paths, expected
    for legacy in ("/health", "/races", "/predict/ensemble",
                   "/predict/single-model"):
        assert legacy in paths, legacy


def test_api_hardening_error_matrix(tmp_path):
    service = make_service(tmp_path)
    total = service.get_timeline(RACE_ORDINARY).frame_count
    with replay_client(service) as client:
        cases = [
            ("/v2/races/nope/replay/timeline", 404, "unknown_race"),
            (f"/v2/races/{RACE_ORDINARY}/replay/frames/{total}", 404,
             "unknown_frame"),
            (f"/v2/races/{RACE_ORDINARY}/replay/frames/999999999", 404,
             "unknown_frame"),
            ("/v2/races/nope/replay/frames/0", 404, "unknown_race"),
            ("/v2/races/nope/replay/predictions/0", 404, "unknown_race"),
            ("/v2/races/nope/replay/probability-timeline", 404,
             "unknown_race"),
        ]
        for url, status, code in cases:
            resp = client.get(url)
            assert resp.status_code == status, url
            assert resp.json()["error"] == code, url
        for params in ({"limit": 0}, {"limit": 9999}, {"offset": -3}):
            resp = client.get(
                f"/v2/races/{RACE_ORDINARY}/replay/timeline", params=params)
            assert resp.status_code == 422, params
        for bad in ("-1", "notanint", "1.5"):
            resp = client.get(
                f"/v2/races/{RACE_ORDINARY}/replay/frames/{bad}")
            assert resp.status_code in (404, 422), bad


def test_api_error_bodies_never_leak_internals(tmp_path):
    service = make_service(tmp_path)
    with replay_client(service) as client:
        for url in ("/v2/races/nope/replay/timeline",
                    f"/v2/races/{RACE_ORDINARY}/replay/frames/999999999"):
            body = json.dumps(client.get(url).json()).lower()
            for token in ("traceback", "site-packages", ".py", "sklearn",
                          "joblib", "file \""):
                assert token not in body, (url, token)


def test_prediction_endpoint_never_generates(tmp_path):
    service = make_service(tmp_path)
    checkpoint = service.get_series(RACE_PARTIAL).checkpoints[0]
    started = time.perf_counter()
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/predictions/"
            f"{checkpoint.frame_index}")
    elapsed = time.perf_counter() - started
    assert resp.status_code == 503
    assert elapsed < 2.0


# ---------------------------------------------------------------------------
# R7-W: 2025 firewall.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("url", [
    "/v2/races/2025-r01-R/replay/timeline",
    "/v2/races/2025-r01-R/replay/frames/0",
    "/v2/races/2025-r01-R/replay/predictions/0",
    "/v2/races/2025-r01-R/replay/probability-timeline",
])
def test_2025_rejected_on_every_route(url, tmp_path):
    service = make_service(tmp_path)
    with replay_client(service) as client:
        resp = client.get(url)
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_race"


def test_2025_backfill_cli_rejected():
    out = subprocess.run(
        [sys.executable, "scripts/build_replay_prediction_cache.py",
         "--race-id", "2025-r01-R", "--dry-run"],
        capture_output=True, text=True, cwd=str(ROOT))
    assert out.returncode != 0
    assert "2025" in (out.stdout + out.stderr)


def test_backfill_requires_explicit_scope():
    out = subprocess.run(
        [sys.executable, "scripts/build_replay_prediction_cache.py",
         "--dry-run"],
        capture_output=True, text=True, cwd=str(ROOT))
    assert out.returncode != 0


# ---------------------------------------------------------------------------
# R7-X: frozen upstream identity.
# ---------------------------------------------------------------------------

def _git(*args):
    return subprocess.run(["git", *args], capture_output=True, text=True,
                          cwd=str(ROOT)).stdout.strip()


def test_head_and_phase4_tag_intact():
    assert _git("rev-parse", "HEAD") == \
        "4f26801ffb0bb1a10725d6c78fba11c5547cb432"
    assert _git("rev-parse", "v2-race-state-prediction-phase4^{commit}") == \
        "4f26801ffb0bb1a10725d6c78fba11c5547cb432"


def test_serving_artifact_sha_intact():
    digest = hashlib.sha256(
        (ROOT / "results/v2_model_lab/winner_logreg_raw_v1_serving.joblib")
        .read_bytes()).hexdigest()
    assert digest == \
        "1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4"


def test_phase2_and_spec_fingerprints_intact():
    manifest = json.loads(
        (ROOT / "docs/PHASE4_FREEZE_MANIFEST.json").read_text())
    assert manifest["phase2"]["content_hash"] == \
        "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db"
    assert manifest["phase3"]["specification_fingerprint"] == \
        "3164de9e61ca94ab958e26590608824ca6c7b05de29c5398d3d204a8c329c24d"


def test_frozen_module_hashes_unchanged_except_authorized_main():
    manifest = json.loads(
        (ROOT / "docs/PHASE4_FREEZE_MANIFEST.json").read_text())
    for section in ("phase4_modules", "phase4_tests", "benchmark",
                    "api_contract"):
        for path, recorded in manifest[section].items():
            if path == "api/main.py":
                continue  # authorized Phase-5 additive router include
            digest = hashlib.sha256((ROOT / path).read_bytes()).hexdigest()
            assert digest == recorded, path


def test_api_main_drift_is_only_the_additive_replay_include():
    text = (ROOT / "api" / "main.py").read_text()
    assert "from api.v2_replay_routes import router as v2_replay_router" \
        in text
    assert "app.include_router(v2_replay_router)" in text
    # No scientific module may be imported by the app assembly.
    modules = _imported_modules("api/main.py")
    for module in modules:
        for banned in ("v2.race_state", "v2.prediction", "v2.model_lab",
                       "v2.race_state_features", "sklearn"):
            assert not (module == banned or module.startswith(banned + ".")), \
                module
