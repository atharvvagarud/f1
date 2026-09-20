"""Phase-5 R2 factual replay reconstruction tests.

Frame -> to_anchor() -> frozen RaceStateReconstructor -> RaceState.
No features, no predictions, no HTTP. Fixtures: 2023-r01-R (ordinary /
early / lapped), 2022-r07-R norris-30 (stale), 2021-r12-R hamilton-2
(partial), 2022-r18-R ocon-2 (red), 2020-r09-R @2974.257 (shared-T
divergence -> giovinazzi), 2020-r09-R SC, 2018-r01-R alonso-26 (VSC).
"""

from __future__ import annotations

import json
import sys
import time

import pandas as pd
import pytest

from v2 import replay as RP
from v2.race_state import RaceState
from v2.race_state_reconstruction import RaceStateReconstructor
from v2.replay_reconstruction import (
    ReplayReconstructionError,
    ReplayReconstructor,
)

D9 = ("data/v2/processed/driver_lap_state_d9/season={season}/"
      "driver_lap_state_d9__d9-{season}.parquet")
RESULTS = ("data/v2/processed/results/season={season}/"
           "results__{race}.parquet")
RACES = ("data/v2/processed/races/season={season}/"
         "races__{race}.parquet")


def load_race(season: int, race_id: str):
    states = pd.read_parquet(D9.format(season=season))
    states = states[states["race_id"] == race_id].copy()
    results = pd.read_parquet(RESULTS.format(season=season, race=race_id))
    meta = {}
    try:
        races = pd.read_parquet(RACES.format(season=season, race=race_id))
        for row in races.itertuples():
            scheduled = getattr(row, "total_laps_scheduled", None)
            meta[str(row.race_id)] = {
                "scheduled_laps": (None if pd.isna(scheduled)
                                   else int(scheduled))}
    except FileNotFoundError:
        pass
    return states, results, meta


def make_service(season: int, race_id: str) -> ReplayReconstructor:
    states, results, meta = load_race(season, race_id)
    timeline = RP.build_replay_timeline(states)
    reconstructor = RaceStateReconstructor(states, results,
                                           race_meta=meta or None)
    return ReplayReconstructor(timeline, reconstructor)


def frame_index_for(service: ReplayReconstructor, driver: str,
                    lap: int) -> int:
    for frame in service.timeline.frames:
        if (frame.anchor_driver_id == driver
                and frame.anchor_lap_number == lap):
            return frame.frame_index
    raise AssertionError(f"anchor {(driver, lap)} not found")


def blob(state: RaceState) -> str:
    return json.dumps(state.to_dict(), sort_keys=True)


# ---------------------------------------------------------------------------
# Construction + laziness.
# ---------------------------------------------------------------------------

def test_service_rejects_bad_inputs():
    states, results, _ = load_race(2023, "2023-r01-R")
    timeline = RP.build_replay_timeline(states)
    reconstructor = RaceStateReconstructor(states, results)
    with pytest.raises(ReplayReconstructionError):
        ReplayReconstructor("nope", reconstructor)
    with pytest.raises(ReplayReconstructionError):
        ReplayReconstructor(timeline, "nope")
    other_states, other_results, _ = load_race(2022, "2022-r07-R")
    other_timeline = RP.build_replay_timeline(other_states)
    with pytest.raises(ReplayReconstructionError):
        ReplayReconstructor(other_timeline, reconstructor)


def test_service_creation_reconstructs_nothing():
    states, results, _ = load_race(2023, "2023-r01-R")
    calls = []
    timeline = RP.build_replay_timeline(states)
    assert isinstance(timeline, RP.ReplayTimeline)
    reconstructor = RaceStateReconstructor(states, results)
    original = reconstructor.reconstruct
    reconstructor.reconstruct = lambda anchor: (
        calls.append(anchor), original(anchor))[1]
    service = ReplayReconstructor(timeline, reconstructor)
    assert calls == []
    service.state_at(0)
    assert len(calls) == 1
    service.state_at(10)
    assert len(calls) == 2
    # No factual cache: repeated resolution re-invokes frozen reconstruction.
    service.state_at(0)
    assert len(calls) == 3


# ---------------------------------------------------------------------------
# Exact lookup + consistency.
# ---------------------------------------------------------------------------

def test_state_at_returns_exact_racestate():
    service = make_service(2023, "2023-r01-R")
    state = service.state_at(100)
    assert isinstance(state, RaceState)
    frame = service.timeline.frame_at(100)
    assert state.race_id == frame.race_id
    assert state.anchor_driver_id == frame.anchor_driver_id
    assert state.anchor_lap_number == frame.anchor_lap_number
    assert state.state_time_s == frame.anchor_state_time_s
    assert [d.driver_id for d in state.drivers] == sorted(
        d.driver_id for d in state.drivers)


def test_state_at_out_of_range():
    service = make_service(2023, "2023-r01-R")
    with pytest.raises(RP.ReplayTimelineError):
        service.state_at(service.timeline.frame_count)
    with pytest.raises(RP.ReplayTimelineError):
        service.state_at(-1)


def test_first_last_previous_next():
    service = make_service(2023, "2023-r01-R")
    assert service.first_state().state_time_s == \
        service.timeline.first.anchor_state_time_s
    assert service.last_state().state_time_s == \
        service.timeline.last.anchor_state_time_s
    assert service.previous_state(0) is None
    assert service.next_state(service.timeline.frame_count - 1) is None
    assert service.next_state(0).state_time_s > \
        service.first_state().state_time_s
    assert service.previous_state(5).state_time_s == \
        service.state_at(4).state_time_s


# ---------------------------------------------------------------------------
# Shared-T divergence fixture.
# ---------------------------------------------------------------------------

def test_divergent_frame_uses_representative_anchor():
    service = make_service(2020, "2020-r09-R")
    matches = [f for f in service.timeline.frames
               if f.anchor_state_time_s == 2974.257]
    assert len(matches) == 1
    frame = matches[0]
    assert (frame.anchor_driver_id, frame.anchor_lap_number) == \
        ("giovinazzi", 6)
    state = service.state_at(frame.frame_index)
    assert state.anchor_driver_id == "giovinazzi"
    assert state.anchor_lap_number == 6
    assert state.state_time_s == 2974.257
    # Representative-derived context (yellow group), not latifi's SC row.
    assert state.race_control.track_state == "yellow"
    assert state.race_control.flag_yellow is True
    assert blob(service.state_at(frame.frame_index)) == blob(state)


def test_divergent_frame_shuffle_stable():
    states, results, meta = load_race(2020, "2020-r09-R")
    reference = make_service(2020, "2020-r09-R")
    idx = next(i for i, f in enumerate(reference.timeline.frames)
               if f.anchor_state_time_s == 2974.257)
    expected = blob(reference.state_at(idx))
    shuffled = states.sample(frac=1.0, random_state=42)
    timeline = RP.build_replay_timeline(shuffled)
    service = ReplayReconstructor(
        timeline, RaceStateReconstructor(states, results,
                                         race_meta=meta or None))
    idx2 = next(i for i, f in enumerate(timeline.frames)
                if f.anchor_state_time_s == 2974.257)
    assert idx2 == idx
    assert timeline.frames[idx2] == reference.timeline.frames[idx]
    assert service.timeline.frames[idx2].anchor_driver_id == "giovinazzi"
    assert blob(service.state_at(idx2)) == expected


# ---------------------------------------------------------------------------
# Leader-lap jump semantics.
# ---------------------------------------------------------------------------

def test_leader_lap_matches_linear_oracle():
    service = make_service(2023, "2023-r01-R")
    oracle = [s.race_context.race_leader_laps_at_state
              for s in (service.state_at(i)
                        for i in range(0, service.timeline.frame_count,
                                       25))]
    assert oracle == sorted(oracle)
    for lap in (1, 10, 30, 57):
        frame = service.frame_for_leader_lap(lap)
        assert service.leader_lap_at(frame.frame_index) >= lap
        if frame.frame_index > 0:
            assert service.leader_lap_at(frame.frame_index - 1) < lap


def test_frame_for_leader_lap_rejects():
    service = make_service(2021, "2021-r12-R")  # partial, leader max 3
    assert service.frame_for_leader_lap(1).frame_index == 0
    with pytest.raises(ReplayReconstructionError):
        service.frame_for_leader_lap(0)
    with pytest.raises(ReplayReconstructionError):
        service.frame_for_leader_lap(4)
    with pytest.raises(ReplayReconstructionError):
        service.frame_for_leader_lap(57)


# ---------------------------------------------------------------------------
# Early / zero-state / stale / partial / red / SC / VSC / lapped.
# ---------------------------------------------------------------------------

def test_early_frame_pre_first_observation():
    service = make_service(2023, "2023-r01-R")
    state = service.first_state()
    unobs = [d for d in state.drivers if not d.observable]
    assert len(unobs) > 0  # not everyone observed at the first timestamp
    for driver in unobs:
        assert driver.observed_lap_number is None
        assert driver.observed_time_s is None
        assert driver.position is None
    anchor = next(d for d in state.drivers
                  if d.driver_id == state.anchor_driver_id)
    assert anchor.observable


def test_stale_driver_preserved():
    service = make_service(2022, "2022-r07-R")
    index = frame_index_for(service, "norris", 30)
    state = service.state_at(index)
    stale = [d for d in state.observable_drivers
             if d.observation_age_s and d.observation_age_s > 0]
    assert len(stale) > 0
    assert len(state.drivers) == state.roster_size
    by_id = {d.driver_id: d for d in state.drivers}
    for driver in stale:
        assert driver.observed_lap_number is not None
        assert driver.observed_time_s is not None
        assert driver.observed_time_s <= state.state_time_s
    assert set(by_id) == set(state.roster_driver_ids)


def test_partial_race_ends_at_factual_end():
    service = make_service(2021, "2021-r12-R")
    last = service.last_state()
    assert service.next_state(service.timeline.frame_count - 1) is None
    assert len(last.drivers) == last.roster_size
    assert last.state_time_s == service.timeline.last.anchor_state_time_s


def test_red_flag_preserved():
    service = make_service(2022, "2022-r18-R")
    index = frame_index_for(service, "ocon", 2)
    state = service.state_at(index)
    assert state.race_control.flag_red is True
    assert state.race_control.track_state == "red_flag"
    assert state.state_time_s == \
        service.timeline.frame_at(index).anchor_state_time_s
    # Neighboring navigation stays deterministic.
    assert service.next_state(index).state_time_s > state.state_time_s


def test_safety_car_preserved():
    service = make_service(2020, "2020-r09-R")
    index = frame_index_for(service, "bottas", 1)
    state = service.state_at(index)
    assert state.race_control.flag_safety_car is True
    assert state.race_control.track_state == "safety_car"


def test_vsc_preserved():
    service = make_service(2018, "2018-r01-R")
    index = frame_index_for(service, "alonso", 26)
    state = service.state_at(index)
    assert state.race_control.flag_vsc is True
    assert state.race_control.track_state in ("vsc", "vsc_ending")


def test_lapped_drivers_keep_own_laps():
    service = make_service(2023, "2023-r01-R")
    state = service.last_state()
    laps = {d.observed_lap_number for d in state.observable_drivers}
    assert len(laps) > 1  # field spread across lap numbers
    anchor_lap = state.anchor_lap_number
    assert any(lap != anchor_lap for lap in laps
               if lap is not None)


# ---------------------------------------------------------------------------
# Temporal adversarial: future factual mutation leaves T bytes identical.
# ---------------------------------------------------------------------------

def test_future_mutation_leaves_snapshot_identical():
    states, results, meta = load_race(2023, "2023-r01-R")
    service = ReplayReconstructor(
        RP.build_replay_timeline(states),
        RaceStateReconstructor(states, results, race_meta=meta or None))
    index = frame_index_for(service, "alonso", 28)
    T = service.timeline.frame_at(index).anchor_state_time_s
    expected = blob(service.state_at(index))
    mutated = states.copy()
    future = mutated["state_time_s"] > T
    assert future.any()
    for column in ("position", "compound", "tyre_life", "stint_number",
                   "track_state", "wx_air_temp_c", "rc_last_message_flag",
                   "pit_stops_completed_so_far", "race_leader_laps_at_state"):
        if column in mutated.columns:
            sample = mutated.loc[~future, column].dropna()
            fill = sample.iloc[0] if len(sample) else 0
            mutated.loc[future, column] = fill
    rebuilt = ReplayReconstructor(
        RP.build_replay_timeline(mutated),
        RaceStateReconstructor(mutated, results, race_meta=meta or None))
    assert blob(rebuilt.state_at(index)) == expected


# ---------------------------------------------------------------------------
# Determinism.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("season,race_id,driver,lap", [
    (2023, "2023-r01-R", "alonso", 28),
    (2021, "2021-r12-R", "hamilton", 2),
    (2022, "2022-r18-R", "ocon", 2),
    (2022, "2022-r07-R", "norris", 30),
])
def test_repeated_and_shuffled_resolution_identical(
        season, race_id, driver, lap):
    states, results, meta = load_race(season, race_id)
    service = make_service(season, race_id)
    index = frame_index_for(service, driver, lap)
    first = blob(service.state_at(index))
    assert blob(service.state_at(index)) == first
    assert blob(service.state_at(index)) == first
    shuffled = states.sample(frac=1.0, random_state=11)
    rebuilt = ReplayReconstructor(
        RP.build_replay_timeline(shuffled),
        RaceStateReconstructor(states, results, race_meta=meta or None))
    index2 = next(i for i, f in enumerate(rebuilt.timeline.frames)
                  if (f.anchor_driver_id, f.anchor_lap_number) == (driver,
                                                                    lap))
    assert rebuilt.timeline.frames[index2].anchor_state_time_s == \
        service.timeline.frames[index].anchor_state_time_s
    assert blob(rebuilt.state_at(index2)) == first


# ---------------------------------------------------------------------------
# Import firewall + 2025 policy.
# ---------------------------------------------------------------------------

def test_no_model_feature_api_imports():
    source = open("v2/replay_reconstruction.py").read()
    for token in ("race_state_features", "v2.prediction", "v2.model_lab",
                  "FrozenWinnerPredictor", "fastapi", "from api",
                  "import api", "frontend", "predict_proba",
                  "features_for_batch"):
        assert token not in source
    # Hermetic: importing the R2 module must not pull model/feature/API
    # machinery (subprocess so earlier test imports cannot pollute).
    import subprocess
    probe = ("import sys, v2.replay_reconstruction; "
             "banned = [m for m in sys.modules if m.startswith("
             "('v2.race_state_features', 'v2.prediction', 'v2.model_lab',"
             " 'api', 'fastapi'))]; "
             "print(','.join(sorted(banned)))")
    out = subprocess.run([sys.executable, "-c", probe], capture_output=True,
                         text=True, cwd=".")
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", out.stdout


def test_2025_scope_enforced_at_serving_boundary():
    from api.v2_service import SERVED_SEASONS
    assert 2025 not in SERVED_SEASONS
    assert tuple(SERVED_SEASONS) == tuple(range(2018, 2025))


# ---------------------------------------------------------------------------
# Performance smoke (informational; generous bounds, no brittle asserts).
# ---------------------------------------------------------------------------

def test_reconstruction_performance_smoke():
    service = make_service(2023, "2023-r01-R")
    n = service.timeline.frame_count
    picks = [0, n // 4, n // 2, 3 * n // 4, n - 1,
             frame_index_for(service, "alonso", 28)]
    service.state_at(picks[0])  # warm
    samples = []
    for index in picks:
        start = time.perf_counter()
        service.state_at(index)
        samples.append(time.perf_counter() - start)
    samples.sort()
    p50 = samples[len(samples) // 2]
    p95 = samples[int(0.95 * (len(samples) - 1))]
    start = time.perf_counter()
    for index in range(0, 20):
        service.state_at(index)
    nav_s = time.perf_counter() - start
    print(f"\nR2 perf: single-frame min/p50/p95 "
          f"{min(samples)*1000:.1f}/{p50*1000:.1f}/{p95*1000:.1f} ms; "
          f"20-frame sequential nav {nav_s*1000:.0f} ms "
          f"({nav_s/20*1000:.1f} ms/frame)")
    assert p95 < 2.0
    assert nav_s < 60.0
