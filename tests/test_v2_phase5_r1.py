"""Phase-5 R1 replay timeline + frame domain tests (factual only).

No RaceState reconstruction, no features, no predictions, no HTTP.
Canonical fixtures: 2023-r01-R (ordinary), 2021-r12-R (partial),
2022-r18-R (red flag), 2022-r07-R (stale), 2020-r09-R (shared-T
track_state divergence at T=2974.257).
"""

from __future__ import annotations

import glob
import json
import math
import time

import pandas as pd
import pytest

from v2 import replay as RP
from v2.race_state import AnchorObservation

D9 = "data/v2/processed/driver_lap_state_d9/season={season}/" \
     "driver_lap_state_d9__d9-{season}.parquet"

# Real shared-T divergence: 2020-r09-R, four drivers share T=2974.257;
# latifi (lap 7, safety_car) vs giovinazzi/kevin_magnussen/sainz (lap 6,
# yellow). Representative rule -> giovinazzi, lap 6.
DIVERGENT_RACE = "2020-r09-R"
DIVERGENT_T = 2974.257
DIVERGENT_REPRESENTATIVE = ("giovinazzi", 6)


def load_race(season: int, race_id: str) -> pd.DataFrame:
    df = pd.read_parquet(D9.format(season=season))
    return df[df["race_id"] == race_id].copy()


def load_served_corpus() -> pd.DataFrame:
    frames = []
    for season in range(2018, 2025):
        frames.append(pd.read_parquet(D9.format(season=season)))
    return pd.concat(frames, ignore_index=True)


def tiny_frame(rows: list[tuple]) -> pd.DataFrame:
    return pd.DataFrame(
        [{"race_id": r, "driver_id": d, "lap_number": lap,
          "state_time_s": t} for r, d, lap, t in rows])


# ---------------------------------------------------------------------------
# Contract version + frame validation.
# ---------------------------------------------------------------------------

def test_contract_version_is_v1():
    assert RP.REPLAY_CONTRACT_VERSION == "v1"


def test_frame_defaults_to_current_version():
    frame = RP.ReplayFrame(
        race_id="2023-r01-R", frame_index=0, anchor_driver_id="alonso",
        anchor_lap_number=28, anchor_state_time_s=1234.5)
    assert frame.replay_contract_version == "v1"


def test_frame_rejects_foreign_version():
    with pytest.raises(RP.ReplayTimelineError):
        RP.ReplayFrame(
            race_id="2023-r01-R", frame_index=0, anchor_driver_id="alonso",
            anchor_lap_number=1, anchor_state_time_s=10.0,
            replay_contract_version="v99")


@pytest.mark.parametrize("field,value", [
    ("race_id", ""), ("race_id", None),
    ("anchor_driver_id", ""), ("anchor_driver_id", None),
])
def test_frame_rejects_empty_identity(field, value):
    kwargs = {"race_id": "2023-r01-R", "frame_index": 0,
              "anchor_driver_id": "alonso", "anchor_lap_number": 1,
              "anchor_state_time_s": 10.0, field: value}
    with pytest.raises(RP.ReplayTimelineError):
        RP.ReplayFrame(**kwargs)


@pytest.mark.parametrize("index", [-1, 1.0, "0", None])
def test_frame_rejects_bad_index(index):
    with pytest.raises(RP.ReplayTimelineError):
        RP.ReplayFrame(
            race_id="r", frame_index=index, anchor_driver_id="d",
            anchor_lap_number=1, anchor_state_time_s=10.0)


@pytest.mark.parametrize("lap", [0, -3, 1.5, "2", None])
def test_frame_rejects_bad_lap(lap):
    with pytest.raises(RP.ReplayTimelineError):
        RP.ReplayFrame(
            race_id="r", frame_index=0, anchor_driver_id="d",
            anchor_lap_number=lap, anchor_state_time_s=10.0)


@pytest.mark.parametrize("time_s", [float("nan"), float("inf"),
                                    float("-inf"), None, "10"])
def test_frame_rejects_bad_time(time_s):
    with pytest.raises(RP.ReplayTimelineError):
        RP.ReplayFrame(
            race_id="r", frame_index=0, anchor_driver_id="d",
            anchor_lap_number=1, anchor_state_time_s=time_s)


def test_frame_carries_no_state_or_predictions():
    frame = RP.ReplayFrame(
        race_id="r", frame_index=0, anchor_driver_id="d",
        anchor_lap_number=1, anchor_state_time_s=10.0)
    payload = frame.to_dict()
    forbidden = {"RaceState", "DriverRaceState", "features",
                 "PredictionSnapshot", "winner_probability", "ModelIdentity",
                 "is_winner", "final_position", "classified"}
    blob = json.dumps(payload)
    assert not any(token in blob for token in forbidden)
    assert set(payload) == {"race_id", "frame_index", "anchor_driver_id",
                            "anchor_lap_number", "anchor_state_time_s",
                            "replay_contract_version"}


# ---------------------------------------------------------------------------
# Exact AnchorObservation conversion.
# ---------------------------------------------------------------------------

def test_frame_to_anchor_exact():
    frame = RP.ReplayFrame(
        race_id="2023-r01-R", frame_index=41, anchor_driver_id="alonso",
        anchor_lap_number=28, anchor_state_time_s=2197.123)
    anchor = frame.to_anchor()
    assert isinstance(anchor, AnchorObservation)
    assert anchor.race_id == "2023-r01-R"
    assert anchor.anchor_driver_id == "alonso"
    assert anchor.anchor_lap_number == 28
    assert anchor.anchor_state_time_s == 2197.123
    assert anchor.anchor_state_time_s == frame.anchor_state_time_s


# ---------------------------------------------------------------------------
# Timeline validation.
# ---------------------------------------------------------------------------

def _frames(race="r", times=(10.0, 20.0, 30.0), driver="d"):
    return tuple(
        RP.ReplayFrame(race_id=race, frame_index=i, anchor_driver_id=driver,
                       anchor_lap_number=i + 1, anchor_state_time_s=t)
        for i, t in enumerate(times))


def test_timeline_exposes_count_first_last():
    timeline = RP.ReplayTimeline(
        race_id="r", replay_contract_version="v1",
        frames=_frames())
    assert timeline.frame_count == 3
    assert timeline.first.frame_index == 0
    assert timeline.last.frame_index == 2


def test_timeline_rejects_empty():
    with pytest.raises(RP.ReplayTimelineError):
        RP.ReplayTimeline(race_id="r", replay_contract_version="v1",
                          frames=())


def test_timeline_rejects_non_dense_indices():
    frames = _frames()
    shifted = tuple(
        RP.ReplayFrame(race_id=f.race_id, frame_index=f.frame_index + 1,
                       anchor_driver_id=f.anchor_driver_id,
                       anchor_lap_number=f.anchor_lap_number,
                       anchor_state_time_s=f.anchor_state_time_s)
        for f in frames)
    with pytest.raises(RP.ReplayTimelineError):
        RP.ReplayTimeline(race_id="r", replay_contract_version="v1",
                          frames=shifted)


def test_timeline_rejects_unordered_construction():
    frames = _frames()
    with pytest.raises(RP.ReplayTimelineError):
        RP.ReplayTimeline(race_id="r", replay_contract_version="v1",
                          frames=tuple(reversed(frames)))


def test_timeline_rejects_non_increasing_time():
    frames = (
        RP.ReplayFrame(race_id="r", frame_index=0, anchor_driver_id="d",
                       anchor_lap_number=1, anchor_state_time_s=20.0),
        RP.ReplayFrame(race_id="r", frame_index=1, anchor_driver_id="d",
                       anchor_lap_number=2, anchor_state_time_s=20.0),
    )
    with pytest.raises(RP.ReplayTimelineError):
        RP.ReplayTimeline(race_id="r", replay_contract_version="v1",
                          frames=frames)


def test_timeline_rejects_mixed_races():
    frames = _frames(race="a") + _frames(race="b")
    fixed = tuple(
        RP.ReplayFrame(race_id=f.race_id, frame_index=i,
                       anchor_driver_id=f.anchor_driver_id,
                       anchor_lap_number=f.anchor_lap_number,
                       anchor_state_time_s=f.anchor_state_time_s + i * 100.0)
        for i, f in enumerate(frames))
    with pytest.raises(RP.ReplayTimelineError):
        RP.ReplayTimeline(race_id="a", replay_contract_version="v1",
                          frames=fixed)


def test_timeline_rejects_mixed_versions():
    good = _frames()
    with pytest.raises(RP.ReplayTimelineError):
        RP.ReplayTimeline(race_id="r", replay_contract_version="v99",
                          frames=good)


# ---------------------------------------------------------------------------
# Builder: one frame per exact unique T, representative rule.
# ---------------------------------------------------------------------------

def test_builder_one_frame_per_unique_time():
    df = tiny_frame([
        ("r", "b", 1, 10.0), ("r", "a", 1, 20.0), ("r", "c", 2, 30.0)])
    timeline = RP.build_replay_timeline(df)
    assert timeline.frame_count == 3
    assert [f.frame_index for f in timeline.frames] == [0, 1, 2]
    assert [f.anchor_state_time_s for f in timeline.frames] == [10.0, 20.0,
                                                                30.0]


def test_builder_shared_exact_time_is_one_frame():
    df = tiny_frame([
        ("r", "b", 3, 50.0), ("r", "a", 2, 50.0), ("r", "c", 2, 60.0)])
    timeline = RP.build_replay_timeline(df)
    assert timeline.frame_count == 2
    # Lower lap_number wins: "a" lap 2 beats "b" lap 3.
    assert timeline.first.anchor_driver_id == "a"
    assert timeline.first.anchor_lap_number == 2


def test_builder_near_but_unequal_times_are_distinct():
    df = tiny_frame([
        ("r", "a", 1, 50.0), ("r", "b", 1, 50.0001)])
    timeline = RP.build_replay_timeline(df)
    assert timeline.frame_count == 2


def test_builder_equal_lap_uses_driver_id_ascending():
    df = tiny_frame([
        ("r", "sainz", 6, 100.0), ("r", "giovinazzi", 6, 100.0),
        ("r", "kevin_magnussen", 6, 100.0)])
    timeline = RP.build_replay_timeline(df)
    assert timeline.frame_count == 1
    assert timeline.first.anchor_driver_id == "giovinazzi"


def test_builder_representative_ignores_input_order():
    rows = [("r", "sainz", 6, 100.0), ("r", "giovinazzi", 6, 100.0),
            ("r", "kevin_magnussen", 6, 100.0), ("r", "latifi", 7, 100.0)]
    first = RP.build_replay_timeline(tiny_frame(rows)).to_dict()
    reversed_timeline = RP.build_replay_timeline(
        tiny_frame(list(reversed(rows)))).to_dict()
    assert first == reversed_timeline
    assert first["frames"][0]["anchor_driver_id"] == "giovinazzi"


def test_builder_rejects_duplicate_identity():
    df = tiny_frame([("r", "a", 1, 10.0), ("r", "a", 1, 10.0)])
    with pytest.raises(RP.ReplayTimelineError):
        RP.build_replay_timeline(df)


@pytest.mark.parametrize("bad", [
    pd.DataFrame(columns=["race_id", "driver_id", "lap_number"]),
    pd.DataFrame(columns=["driver_id", "lap_number", "state_time_s"]),
])
def test_builder_rejects_missing_column(bad):
    with pytest.raises(RP.ReplayTimelineError):
        RP.build_replay_timeline(bad)


def test_builder_rejects_empty_input():
    df = pd.DataFrame(columns=["race_id", "driver_id", "lap_number",
                               "state_time_s"])
    with pytest.raises(RP.ReplayTimelineError):
        RP.build_replay_timeline(df)


def test_builder_rejects_multiple_races():
    df = tiny_frame([("a", "x", 1, 10.0), ("b", "y", 1, 20.0)])
    with pytest.raises(RP.ReplayTimelineError):
        RP.build_replay_timeline(df)


@pytest.mark.parametrize("rows", [
    [(None, "d", 1, 10.0)], [("", "d", 1, 10.0)],
    [("r", None, 1, 10.0)], [("r", "", 1, 10.0)],
    [("r", "d", 0, 10.0)], [("r", "d", None, 10.0)],
    [("r", "d", 1, float("nan"))], [("r", "d", 1, float("inf"))],
    [("r", "d", 1, float("-inf"))], [("r", "d", 1, None)],
])
def test_builder_rejects_malformed_values(rows):
    with pytest.raises(RP.ReplayTimelineError):
        RP.build_replay_timeline(tiny_frame(rows))


# ---------------------------------------------------------------------------
# Navigation.
# ---------------------------------------------------------------------------

def test_navigation_first_last_frame_at():
    timeline = RP.ReplayTimeline(
        race_id="r", replay_contract_version="v1", frames=_frames())
    assert timeline.frame_at(0) == timeline.first
    assert timeline.frame_at(2) == timeline.last
    with pytest.raises(RP.ReplayTimelineError):
        timeline.frame_at(3)
    with pytest.raises(RP.ReplayTimelineError):
        timeline.frame_at(-1)


def test_navigation_previous_next_no_wraparound():
    timeline = RP.ReplayTimeline(
        race_id="r", replay_contract_version="v1", frames=_frames())
    assert timeline.previous(0) is None
    assert timeline.next(2) is None
    assert timeline.next(0).frame_index == 1
    assert timeline.previous(2).frame_index == 1
    assert timeline.previous(1).frame_index == 0


# ---------------------------------------------------------------------------
# Serialization.
# ---------------------------------------------------------------------------

def test_serialization_round_trip_and_bytes():
    df = load_race(2023, "2023-r01-R")
    timeline = RP.build_replay_timeline(df)
    blob_a = json.dumps(timeline.to_dict(), sort_keys=True)
    blob_b = json.dumps(timeline.to_dict(), sort_keys=True)
    assert blob_a == blob_b
    payload = json.loads(blob_a)
    assert payload["race_id"] == "2023-r01-R"
    assert payload["replay_contract_version"] == "v1"
    assert payload["frame_count"] == len(payload["frames"])
    assert all(math.isfinite(f["anchor_state_time_s"])
               for f in payload["frames"])
    # No pandas/numpy leakage: every value is a JSON primitive.
    assert isinstance(blob_a, str)


# ---------------------------------------------------------------------------
# Label / future firewall.
# ---------------------------------------------------------------------------

def test_firewall_ignores_label_and_future_columns():
    df = load_race(2023, "2023-r01-R")
    reference = RP.build_replay_timeline(df).to_dict()
    poisoned = df.copy()
    poisoned["is_winner"] = 1
    poisoned["final_position"] = 20
    poisoned["points"] = 99.0
    poisoned["classified_flag"] = "X"
    poisoned["future_state_time_s"] = poisoned["state_time_s"] + 5000.0
    poisoned["model_probability"] = 0.5
    assert RP.build_replay_timeline(poisoned).to_dict() == reference


# ---------------------------------------------------------------------------
# Canonical fixtures + determinism.
# ---------------------------------------------------------------------------

FIXTURES = [
    (2023, "2023-r01-R"),  # ordinary full race
    (2021, "2021-r12-R"),  # partial race
    (2022, "2022-r18-R"),  # red-flag race
    (2022, "2022-r07-R"),  # stale-driver race
    (2020, DIVERGENT_RACE),  # shared-T divergence race
]


@pytest.mark.parametrize("season,race_id", FIXTURES)
def test_fixture_frame_count_matches_unique_times(season, race_id):
    df = load_race(season, race_id)
    timeline = RP.build_replay_timeline(df)
    assert timeline.frame_count == int(df["state_time_s"].nunique())
    times = [f.anchor_state_time_s for f in timeline.frames]
    assert times == sorted(times)
    assert len(set(times)) == len(times)


@pytest.mark.parametrize("season,race_id", FIXTURES)
def test_fixture_shuffled_input_identical(season, race_id):
    df = load_race(season, race_id)
    reference = json.dumps(RP.build_replay_timeline(df).to_dict(),
                           sort_keys=True)
    for seed in (7, 42):
        shuffled = df.sample(frac=1.0, random_state=seed)
        rebuilt = json.dumps(RP.build_replay_timeline(shuffled).to_dict(),
                             sort_keys=True)
        assert rebuilt == reference


@pytest.mark.parametrize("season,race_id", FIXTURES)
def test_fixture_all_anchors_are_exact_rows(season, race_id):
    df = load_race(season, race_id)
    timeline = RP.build_replay_timeline(df)
    keys = set(zip(df["driver_id"], df["lap_number"], df["state_time_s"]))
    for frame in timeline.frames:
        assert (frame.anchor_driver_id, frame.anchor_lap_number,
                frame.anchor_state_time_s) in keys
        anchor = frame.to_anchor()
        assert anchor.race_id == race_id


def test_known_divergent_group_selects_expected_representative():
    df = load_race(2020, DIVERGENT_RACE)
    group = df[df["state_time_s"] == DIVERGENT_T]
    assert len(group) == 4
    assert set(group["driver_id"]) == {"giovinazzi", "kevin_magnussen",
                                       "latifi", "sainz"}
    timeline = RP.build_replay_timeline(df)
    match = [f for f in timeline.frames
             if f.anchor_state_time_s == DIVERGENT_T]
    assert len(match) == 1
    assert (match[0].anchor_driver_id,
            match[0].anchor_lap_number) == DIVERGENT_REPRESENTATIVE


def test_divergent_group_still_reachable_via_navigation():
    df = load_race(2020, DIVERGENT_RACE)
    timeline = RP.build_replay_timeline(df)
    indices = [i for i, f in enumerate(timeline.frames)
               if f.anchor_state_time_s == DIVERGENT_T]
    assert len(indices) == 1
    index = indices[0]
    assert timeline.frame_at(index).anchor_driver_id == "giovinazzi"
    assert timeline.previous(index).anchor_state_time_s < DIVERGENT_T
    assert timeline.next(index).anchor_state_time_s > DIVERGENT_T


# ---------------------------------------------------------------------------
# 2025 policy: builder is season-agnostic by design; scope lives at service.
# ---------------------------------------------------------------------------

def test_builder_is_season_agnostic_single_race():
    df = tiny_frame([("2025-r01-R", "a", 1, 10.0),
                     ("2025-r01-R", "b", 1, 20.0)])
    timeline = RP.build_replay_timeline(df)
    assert timeline.race_id == "2025-r01-R"
    assert timeline.frame_count == 2
    # 2018–2024 scope is enforced by the serving boundary, not here:
    from api.v2_service import SERVED_SEASONS
    assert 2025 not in SERVED_SEASONS


# ---------------------------------------------------------------------------
# Corpus audit + performance (factual build only, no reconstruction).
# ---------------------------------------------------------------------------

def test_corpus_audit_matches_r0_evidence():
    corpus = load_served_corpus()
    races = sorted(corpus["race_id"].unique())
    assert len(races) == 149
    assert len(corpus) == 162728
    total_frames = 0
    shared_groups = 0
    collapsed = 0
    races_with_shared = 0
    for race_id in races:
        sub = corpus[corpus["race_id"] == race_id]
        timeline = RP.build_replay_timeline(sub)
        total_frames += timeline.frame_count
        sizes = sub.groupby("state_time_s").size()
        multi = sizes[sizes > 1]
        shared_groups += len(multi)
        collapsed += int((multi - 1).sum())
        races_with_shared += 1 if len(multi) else 0
    assert total_frames == 162639
    assert shared_groups == 58
    assert collapsed == 89
    assert races_with_shared == 52


def test_timeline_build_performance():
    corpus = load_served_corpus()
    # Largest served race by row count.
    largest = corpus.groupby("race_id").size().idxmax()
    normal = corpus[corpus["race_id"] == "2023-r01-R"]
    big = corpus[corpus["race_id"] == largest]
    start = time.perf_counter()
    RP.build_replay_timeline(normal)
    normal_s = time.perf_counter() - start
    start = time.perf_counter()
    RP.build_replay_timeline(big)
    big_s = time.perf_counter() - start
    start = time.perf_counter()
    for race_id in sorted(corpus["race_id"].unique()):
        RP.build_replay_timeline(corpus[corpus["race_id"] == race_id])
    corpus_s = time.perf_counter() - start
    print(f"\nR1 perf: normal 2023-r01-R {normal_s:.3f}s, "
          f"largest {largest} ({len(big)} rows) {big_s:.3f}s, "
          f"full 149-race corpus {corpus_s:.3f}s "
          f"({corpus_s / 149:.3f}s/race)")
    assert normal_s < 1.0
    assert big_s < 1.0
