"""Phase-4 R2: historical RaceState reconstruction.

Synthetic fixtures (fake race ids, no 2025) prove exactness, sync,
projection, coercion, past-only context, mutation invariance, and
F6 parity; a small canonical dev-data smoke section (2021/2022 only,
skipped when data is absent) proves real-frame behavior. No model, no
ALL_84, no 2025 targets anywhere.
"""

import json
import subprocess
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from raceintel.race_state import race_state as RS
from raceintel.config import V2Paths
from raceintel.features.gaps import build_f6_registry, gap_batch, gap_for_state
from raceintel.race_state.race_state_reconstruction import (
    AnchorNotFoundError,
    RaceNotFoundError,
    RaceStateReconstructor,
    RaceStateReconstructionError,
    reconstruct_race_state,
)

ROOT = V2Paths.resolve().root
_HAS_D9 = (ROOT / "data/v2/processed/driver_lap_state_d9/season=2021").is_dir()
_HAS_RESULTS = (ROOT / "data/v2/processed/results/season=2021").is_dir()


# ---------------------------------------------------------------------------
# Synthetic D9-shaped fixtures.
# ---------------------------------------------------------------------------

def _base(race="R1", season=2021, round_no=12, circuit="spa", sched=44):
    row = {c: None for c in [
        "position", "compound", "tyre_life", "fresh_tyre", "stint_number",
        "stint_lap", "pit_stops_completed_so_far",
        "laps_since_last_pit_stop", "constructor_id", "driver_number",
        "track_state", "flag_yellow", "flag_safety_car", "flag_red",
        "flag_vsc", "rc_last_message_category", "rc_last_message_flag",
        "rc_last_message_age_s", "race_leader_laps_at_state",
        "race_progress_frac", "wx_air_temp_c", "wx_track_temp_c",
        "wx_humidity_pct", "wx_pressure_hpa", "wx_wind_speed",
        "wx_wind_direction_deg", "wx_rainfall", "wx_observed_at_s",
        "wx_age_s"]}
    row.update({"race_id": race, "season": season, "round_no": round_no,
                "circuit_id": circuit, "total_laps_scheduled": sched})
    return row


def _row(driver, lap, t, _base_=None, **over):
    row = dict(_base_ or _base())
    row.update({"driver_id": driver, "lap_number": lap, "state_time_s": t})
    row.update(over)
    return row


def _frame(rows):
    frame = pd.DataFrame(rows)
    for col in ["race_id", "driver_id", "lap_number", "state_time_s",
                "season", "round_no", "circuit_id",
                "total_laps_scheduled", "position", "compound",
                "tyre_life", "fresh_tyre", "stint_number", "stint_lap",
                "pit_stops_completed_so_far", "laps_since_last_pit_stop",
                "constructor_id", "driver_number", "track_state",
                "flag_yellow", "flag_safety_car", "flag_red", "flag_vsc",
                "rc_last_message_category", "rc_last_message_flag",
                "rc_last_message_age_s", "race_leader_laps_at_state",
                "race_progress_frac", "wx_air_temp_c", "wx_track_temp_c",
                "wx_humidity_pct", "wx_pressure_hpa", "wx_wind_speed",
                "wx_wind_direction_deg", "wx_rainfall", "wx_observed_at_s",
                "wx_age_s"]:
        if col not in frame.columns:
            frame[col] = None
    return frame


_ANCHOR_CTX = {
    "position": 1, "compound": "SOFT", "tyre_life": 8, "fresh_tyre": False,
    "stint_number": 2, "stint_lap": 5, "pit_stops_completed_so_far": 1,
    "laps_since_last_pit_stop": 4, "constructor_id": "mclaren",
    "driver_number": 4, "track_state": "all_clear", "flag_yellow": False,
    "flag_safety_car": False, "flag_red": False, "flag_vsc": False,
    "rc_last_message_category": "Flag", "rc_last_message_flag": "GREEN",
    "rc_last_message_age_s": 120.0, "race_leader_laps_at_state": 2,
    "race_progress_frac": 2 / 44, "wx_air_temp_c": 28.0,
    "wx_track_temp_c": 35.0, "wx_humidity_pct": 40.0,
    "wx_pressure_hpa": 1013.0, "wx_wind_speed": 3.5,
    "wx_wind_direction_deg": 180.0, "wx_rainfall": False,
    "wx_observed_at_s": 150.0, "wx_age_s": 50.0,
}


@pytest.fixture()
def race_r1():
    return _frame([
        _row("a", 1, 100.0, position=1, compound="SOFT", tyre_life=0,
             fresh_tyre=True, stint_number=1, stint_lap=1,
             pit_stops_completed_so_far=0, constructor_id="mclaren",
             driver_number=4, track_state="all_clear"),
        _row("a", 2, 200.0, **_ANCHOR_CTX),
        _row("b", 1, 110.0, position=2, compound="MEDIUM", tyre_life=0,
             fresh_tyre=True, stint_number=1, stint_lap=1,
             pit_stops_completed_so_far=0, constructor_id="mercedes",
             driver_number=44, track_state="all_clear"),
        _row("b", 2, 205.0, position=2, compound="MEDIUM",
             track_state="all_clear"),
        _row("b", 3, 310.0, position=2, compound="HARD",
             track_state="all_clear"),
        _row("c", 1, 250.0, position=3, compound="SOFT",
             track_state="all_clear"),
    ])


@pytest.fixture()
def roster_r1():
    return {"R1": ["a", "b", "c", "z"]}


@pytest.fixture()
def recon(race_r1, roster_r1):
    return RaceStateReconstructor(race_r1, roster_r1)


_ANCHOR = RS.AnchorObservation(race_id="R1", anchor_driver_id="a",
                               anchor_lap_number=2,
                               anchor_state_time_s=200.0)


# ---------------------------------------------------------------------------
# Exact anchor resolution.
# ---------------------------------------------------------------------------

def test_exact_anchor_success(recon):
    snap = recon.reconstruct(_ANCHOR)
    assert isinstance(snap, RS.RaceState)
    assert (snap.race_id, snap.anchor_driver_id, snap.anchor_lap_number,
            snap.state_time_s) == ("R1", "a", 2, 200.0)
    by_id = {d.driver_id: d for d in snap.drivers}
    anchor = by_id["a"]
    assert anchor.observable is True
    assert anchor.observation_age_s == 0.0
    assert anchor.position == 1
    assert anchor.compound == "SOFT"
    assert anchor.tyre_life == 8
    assert anchor.fresh_tyre is False
    assert anchor.stint_number == 2
    assert anchor.stint_lap == 5
    assert anchor.pit_stops_completed_so_far == 1
    assert anchor.laps_since_last_pit_stop == 4
    assert anchor.constructor_id == "mclaren"
    assert anchor.driver_number == 4
    assert snap.race_context.to_dict() == {
        "race_leader_laps_at_state": 2, "race_progress_frac": 2 / 44,
        "scheduled_laps": 44, "season": 2021, "round_no": 12,
        "circuit_id": "spa"}
    assert snap.weather.air_temp_c == 28.0
    assert snap.weather.observation_age_s == 50.0
    assert snap.race_control.track_state == "all_clear"
    assert snap.race_control.flag_red is False


def test_unknown_race(recon):
    with pytest.raises(RaceNotFoundError) as exc:
        recon.reconstruct(RS.AnchorObservation(
            race_id="NOPE", anchor_driver_id="a", anchor_lap_number=1,
            anchor_state_time_s=100.0))
    assert exc.value.race_id == "NOPE"


@pytest.mark.parametrize("lap,t", [(3, 200.0), (2, 200.0001), (1, 200.0),
                                   (2, 199.9999)])
def test_missing_anchor_no_substitution(recon, lap, t):
    with pytest.raises(AnchorNotFoundError) as exc:
        recon.reconstruct(RS.AnchorObservation(
            race_id="R1", anchor_driver_id="a", anchor_lap_number=lap,
            anchor_state_time_s=t))
    assert (exc.value.race_id, exc.value.driver_id, exc.value.lap_number,
            exc.value.state_time_s) == ("R1", "a", lap, t)


def test_missing_anchor_driver(recon):
    with pytest.raises(AnchorNotFoundError):
        recon.reconstruct(RS.AnchorObservation(
            race_id="R1", anchor_driver_id="zz", anchor_lap_number=1,
            anchor_state_time_s=100.0))


def test_errors_carry_no_http():
    assert issubclass(AnchorNotFoundError, RaceStateReconstructionError)
    assert issubclass(RaceNotFoundError, RaceStateReconstructionError)
    assert issubclass(RaceStateReconstructionError, RS.RaceStateError)
    for cls in (AnchorNotFoundError, RaceNotFoundError,
                RaceStateReconstructionError):
        assert "status_code" not in cls.__dict__


def test_roster_frame_accepted(race_r1):
    roster_frame = pd.DataFrame([{"race_id": "R1", "driver_id": d,
                                  "position_final": 1 if d == "a" else 2,
                                  "points": 25.0 if d == "a" else 18.0}
                                 for d in ["a", "b", "c", "z"]])
    snap = reconstruct_race_state(_ANCHOR, race_r1, roster_frame)
    assert snap.roster_driver_ids == ("a", "b", "c", "z")


# ---------------------------------------------------------------------------
# Synchronization / roster / staleness.
# ---------------------------------------------------------------------------

def test_synchronized_field_and_staleness(recon):
    snap = recon.reconstruct(_ANCHOR)
    by_id = {d.driver_id: d for d in snap.drivers}
    rival = by_id["b"]
    assert rival.observable is True
    assert rival.observed_lap_number == 1  # lap-2 row at t=205 excluded
    assert rival.observed_time_s == 110.0
    assert rival.observation_age_s == pytest.approx(90.0)
    # Stale is observable, never retired-by-inference.
    assert rival.position == 2
    assert snap.roster_driver_ids == ("a", "b", "c", "z")
    assert snap.observable_driver_ids == ("a", "b")
    assert snap.unobservable_driver_ids == ("c", "z")


def test_zero_state_and_pre_observation(recon):
    snap = recon.reconstruct(_ANCHOR)
    by_id = {d.driver_id: d for d in snap.drivers}
    for driver in ("c", "z"):
        entry = by_id[driver]
        assert entry.observable is False
        payload = entry.to_dict()
        assert {k: v for k, v in payload.items()
                if k not in ("driver_id", "observable")} == \
            {k: None for k in payload if k not in ("driver_id",
                                                   "observable")}


def test_deterministic_and_shuffle_stable(recon, race_r1, roster_r1):
    first = recon.reconstruct(_ANCHOR).to_dict()
    again = RaceStateReconstructor(race_r1, roster_r1) \
        .reconstruct(_ANCHOR).to_dict()
    assert first == again
    shuffled = race_r1.sample(frac=1.0, random_state=11).reset_index(
        drop=True)
    assert RaceStateReconstructor(shuffled, roster_r1) \
        .reconstruct(_ANCHOR).to_dict() == first
    text = json.dumps(first, allow_nan=False, sort_keys=True)
    assert json.loads(text)["anchor_driver_id"] == "a"


# ---------------------------------------------------------------------------
# Coercion boundary.
# ---------------------------------------------------------------------------

def test_numpy_pandas_coercion():
    frame = _frame([
        _row("a", 1, np.float64(100.0), position=np.int64(1),
             compound="SOFT", tyre_life=np.int64(3),
             fresh_tyre=np.bool_(True), stint_number=np.int64(1),
             constructor_id="mclaren", driver_number=np.int64(4),
             track_state="all_clear", flag_red=np.bool_(False),
             wx_air_temp_c=np.float64(28.0), wx_rainfall=np.bool_(False),
             race_leader_laps_at_state=np.int64(1),
             race_progress_frac=np.float64(0.5)),
    ])
    snap = reconstruct_race_state(
        RS.AnchorObservation(race_id="R1", anchor_driver_id="a",
                             anchor_lap_number=1,
                             anchor_state_time_s=100.0),
        frame, {"R1": ["a"]})
    entry = snap.drivers[0]
    assert type(entry.observed_time_s) is float
    assert type(entry.position) is int
    assert type(entry.fresh_tyre) is bool
    assert type(entry.driver_number) is int
    assert type(snap.weather.air_temp_c) is float
    assert type(snap.race_control.flag_red) is bool
    json.dumps(snap.to_dict(), allow_nan=False)


def test_nullable_missing_becomes_none():
    frame = _frame([
        _row("a", 1, 100.0, position=pd.NA, compound=None,
             tyre_life=float("nan"), fresh_tyre=pd.NA,
             track_state="all_clear"),
    ])
    snap = reconstruct_race_state(
        RS.AnchorObservation(race_id="R1", anchor_driver_id="a",
                             anchor_lap_number=1,
                             anchor_state_time_s=100.0),
        frame, {"R1": ["a"]})
    entry = snap.drivers[0]
    assert entry.position is None
    assert entry.compound is None
    assert entry.tyre_life is None
    assert entry.fresh_tyre is None
    assert snap.weather.air_temp_c is None


def test_inf_rejected_not_nulled(race_r1, roster_r1):
    bad = race_r1.copy()
    bad.loc[(bad["driver_id"] == "a") & (bad["lap_number"] == 2),
            "wx_air_temp_c"] = float("inf")
    with pytest.raises(RaceStateReconstructionError):
        RaceStateReconstructor(bad, roster_r1).reconstruct(_ANCHOR)


def test_missing_required_column_rejected(race_r1, roster_r1):
    with pytest.raises(RaceStateReconstructionError):
        RaceStateReconstructor(race_r1.drop(columns=["position"]),
                               roster_r1)


# ---------------------------------------------------------------------------
# Gap parity with frozen F6 (independent paths as oracle).
# ---------------------------------------------------------------------------

def test_gap_parity_with_gap_for_state(recon, race_r1):
    from raceintel.features.contracts import FeatureRequest
    registry = build_f6_registry()
    snap = recon.reconstruct(_ANCHOR)
    by_id = {d.driver_id: d for d in snap.drivers}
    cases = [("a", 2, 200.0), ("b", 1, 110.0)]
    for driver, lap, t in cases:
        result = gap_for_state(
            FeatureRequest(race_id="R1", driver_id=driver, lap_number=lap,
                           state_time_s=t), registry, race_r1)
        values = {k: (None if v is None or
                      (isinstance(v, float) and pd.isna(v)) else v)
                  for k, v in dict(result.values).items()}
        entry = by_id[driver]
        for domain, feature in (
                ("gap_to_leader_s", "gap_to_leader_seconds"),
                ("gap_to_leader_valid", "gap_to_leader_seconds_valid"),
                ("gap_to_leader_laps", "gap_to_leader_laps"),
                ("gap_to_ahead_s", "gap_to_ahead_seconds"),
                ("gap_to_ahead_valid", "gap_to_ahead_seconds_valid"),
                ("gap_to_ahead_laps", "gap_to_ahead_laps")):
            expected, actual = values[feature], getattr(entry, domain)
            if expected is None:
                assert actual is None, (domain, expected, actual)
            elif isinstance(expected, float):
                assert actual == pytest.approx(expected), domain
            else:
                assert actual == expected, domain
    anchor = by_id["a"]
    assert anchor.gap_to_leader_s == 0.0
    assert anchor.gap_to_leader_valid is True
    assert anchor.gap_to_leader_laps == 0
    # Leader has no car ahead: null seconds, False validity (frozen tri).
    assert anchor.gap_to_ahead_s is None
    assert anchor.gap_to_ahead_valid is False
    assert anchor.gap_to_ahead_laps is None
    rival = by_id["b"]
    assert rival.gap_to_leader_s == pytest.approx(10.0)
    assert rival.gap_to_leader_valid is True
    assert rival.gap_to_ahead_s == pytest.approx(10.0)
    assert rival.gap_to_ahead_valid is True


def test_gap_parity_with_gap_batch(recon, race_r1):
    batch = gap_batch(race_r1[race_r1["race_id"] == "R1"])
    snap = recon.reconstruct(_ANCHOR)
    by_id = {d.driver_id: d for d in snap.drivers}
    for (driver, lap, t) in [("a", 2, 200.0), ("b", 1, 110.0)]:
        row = batch[(batch["driver_id"] == driver)
                    & (batch["lap_number"] == lap)].iloc[0]
        entry = by_id[driver]
        for domain, batch_col in (
                ("gap_to_leader_s", "gap_to_leader_seconds"),
                ("gap_to_leader_valid", "gap_to_leader_seconds_valid"),
                ("gap_to_leader_laps", "gap_to_leader_laps"),
                ("gap_to_ahead_s", "gap_to_ahead_seconds"),
                ("gap_to_ahead_valid", "gap_to_ahead_seconds_valid"),
                ("gap_to_ahead_laps", "gap_to_ahead_laps")):
            expected = row[batch_col]
            actual = getattr(entry, domain)
            if expected is None or (isinstance(expected, float)
                                    and pd.isna(expected)):
                assert actual is None, (domain, expected, actual)
            elif isinstance(expected, float):
                assert actual == pytest.approx(expected), domain
            else:
                assert actual == expected, domain


# ---------------------------------------------------------------------------
# Red-flag / partial races.
# ---------------------------------------------------------------------------

@pytest.fixture()
def race_red():
    base = _base(race="R2")
    return _frame([
        _row("a", 1, 100.0, _base_=base, position=1, compound="SOFT",
             track_state="all_clear"),
        _row("a", 2, 200.0, _base_=base, position=2, compound="SOFT",
             track_state="red_flag", flag_red=True,
             race_leader_laps_at_state=2, race_progress_frac=2 / 44),
        _row("b", 1, 110.0, _base_=base, position=2, compound="MEDIUM",
             track_state="all_clear"),
        _row("b", 2, 205.0, _base_=base, position=1, compound="MEDIUM",
             track_state="red_flag", flag_red=True),
    ])


def test_red_flag_gaps_invalid_not_zero(race_red):
    snap = reconstruct_race_state(
        RS.AnchorObservation(race_id="R2", anchor_driver_id="a",
                             anchor_lap_number=2,
                             anchor_state_time_s=200.0),
        race_red, {"R2": ["a", "b"]})
    assert snap.race_control.track_state == "red_flag"
    assert snap.race_control.flag_red is True
    entry = {d.driver_id: d for d in snap.drivers}["a"]
    assert entry.gap_to_leader_s is None
    assert entry.gap_to_leader_valid is False
    assert entry.gap_to_leader_laps == 1  # lap difference preserved
    assert entry.position == 2  # running order carried verbatim


def test_partial_race_minimal():
    frame = _frame([
        _row("a", 1, 100.0, position=1, track_state="all_clear"),
        _row("b", 1, 112.0, position=2, track_state="all_clear"),
    ])
    snap = reconstruct_race_state(
        RS.AnchorObservation(race_id="R1", anchor_driver_id="a",
                             anchor_lap_number=1,
                             anchor_state_time_s=100.0),
        frame, {"R1": ["a", "b"]})
    assert snap.roster_size == 2
    assert snap.weather.to_dict() == {k: None for k in
                                      snap.weather.to_dict()}
    assert snap.race_control.track_state == "all_clear"


# ---------------------------------------------------------------------------
# Past-only context: pit/stint, weather, race control.
# ---------------------------------------------------------------------------

def test_pit_stint_past_only(recon, race_r1, roster_r1):
    before = recon.reconstruct(_ANCHOR).to_dict()
    extra = pd.DataFrame([_row(
        "a", 3, 300.0, position=1, compound="HARD", stint_number=3,
        stint_lap=1, pit_stops_completed_so_far=2,
        laps_since_last_pit_stop=0, track_state="all_clear",
        end_lap=99, next_compound="SOFT")])
    mutated = pd.concat([race_r1, extra], ignore_index=True)
    after = RaceStateReconstructor(mutated, roster_r1) \
        .reconstruct(_ANCHOR).to_dict()
    assert after == before  # future stop + unknown columns change nothing


def test_weather_race_control_past_only(recon, race_r1, roster_r1):
    before = recon.reconstruct(_ANCHOR).to_dict()
    mutated = race_r1.copy()
    future = mutated["state_time_s"] > 200.0
    mutated.loc[future, "wx_air_temp_c"] = -99.0
    mutated.loc[future, "wx_rainfall"] = True
    mutated.loc[future, "rc_last_message_category"] = "SafetyCar"
    mutated.loc[future, "track_state"] = "safety_car"
    after = RaceStateReconstructor(mutated, roster_r1) \
        .reconstruct(_ANCHOR).to_dict()
    assert after == before
    snap = recon.reconstruct(_ANCHOR)
    assert snap.weather.air_temp_c == 28.0
    assert snap.weather.rainfall is False
    assert snap.race_control.last_message_category == "Flag"


def test_label_and_status_firewall(recon, race_r1, roster_r1):
    before = recon.reconstruct(_ANCHOR).to_dict()
    poisoned = race_r1.copy()
    for col, val in [("position_final", 1), ("is_winner", True),
                     ("is_podium", True), ("scored_points", True),
                     ("position_change_from_state", 5),
                     ("classified_position", 1), ("status_text",
                                                 "Finished"),
                     ("points", 25.0), ("laps_completed", 57),
                     ("eligible_is_winner", True)]:
        poisoned[col] = val
    # Outcome mutation cannot change the roster extraction either.
    poisoned_results = pd.DataFrame(
        [{"race_id": "R1", "driver_id": d, "position_final": 99,
          "points": -1.0} for d in ["a", "b", "c", "z"]])
    after = RaceStateReconstructor(
        poisoned, poisoned_results).reconstruct(_ANCHOR).to_dict()
    assert after == before
    assert RS.domain_field_names() & RS.label_outcome_fields() == set()


@pytest.mark.parametrize("mutate", [
    "rival_future_value", "rival_future_row_add", "rival_future_row_drop",
    "same_lap_future_rival", "future_weather", "future_race_control",
    "future_pit", "label_join", "future_driver_append",
    "unrelated_race", "column_reorder",
])
def test_future_mutation_invariance(recon, race_r1, roster_r1, mutate):
    before = recon.reconstruct(_ANCHOR).to_dict()
    mutated = race_r1.copy()
    if mutate == "rival_future_value":
        mutated.loc[(mutated["driver_id"] == "b")
                    & (mutated["lap_number"] == 2), "position"] = 1
    elif mutate == "rival_future_row_add":
        mutated = pd.concat(
            [mutated, pd.DataFrame([_row("b", 4, 400.0, position=1)])],
            ignore_index=True)
    elif mutate == "rival_future_row_drop":
        mutated = mutated[~((mutated["driver_id"] == "b")
                            & (mutated["lap_number"] == 3))]
    elif mutate == "same_lap_future_rival":
        mutated.loc[(mutated["driver_id"] == "b")
                    & (mutated["lap_number"] == 2),
                    "state_time_s"] = 200.5
    elif mutate == "future_weather":
        mutated.loc[mutated["state_time_s"] > 200.0,
                    "wx_air_temp_c"] = -50.0
    elif mutate == "future_race_control":
        mutated.loc[mutated["state_time_s"] > 200.0,
                    "rc_last_message_category"] = "RedFlag"
    elif mutate == "future_pit":
        mutated = pd.concat(
            [mutated, pd.DataFrame([_row(
                "a", 3, 300.0,
                pit_stops_completed_so_far=9)])],
            ignore_index=True)
    elif mutate == "label_join":
        mutated["is_winner"] = mutated["driver_id"] == "a"
        mutated["final_position"] = 1
    elif mutate == "future_driver_append":
        mutated = pd.concat(
            [mutated, pd.DataFrame([_row("c", 2, 350.0, position=1)])],
            ignore_index=True)
    elif mutate == "unrelated_race":
        other = _base(race="RX")
        mutated = pd.concat(
            [mutated, pd.DataFrame([_row("q", 1, 10.0, _base_=other)])],
            ignore_index=True)
    elif mutate == "column_reorder":
        cols = list(mutated.columns)[::-1]
        mutated = mutated[cols]
    after = RaceStateReconstructor(mutated, roster_r1) \
        .reconstruct(_ANCHOR).to_dict()
    assert after == before, mutate


# ---------------------------------------------------------------------------
# Architecture guards: no model/feature-batch/API coupling.
# ---------------------------------------------------------------------------

def test_no_model_coupling_in_source():
    import re
    source = Path(__file__).resolve().parent.parent \
        / "raceintel/race_state/race_state_reconstruction.py"
    text = source.read_text()
    imported = set()
    for line in text.splitlines():
        match = re.match(r"\s*(?:from|import)\s+([\w.]+)", line)
        if match:
            imported.add(match.group(1))
    for module in sorted(imported):
        for banned in ("raceintel.model_lab", "ml", "api", "raceintel.labels", "sklearn",
                       "scipy", "fastapi", "pydantic"):
            assert not (module == banned
                        or module.startswith(banned + ".")), \
                f"banned import: {module}"
    for banned in ("features_for_batch(", "features_for_state(",
                   "predict_proba(", "HTTPException", "resolve_feature_set",
                   "build_f11_registry", "2025"):
        assert banned not in text, banned


def test_no_model_imports_at_runtime():
    probe = ("import sys, raceintel.race_state.race_state_reconstruction; "
             "banned = [m for m in sys.modules if m.split('.')[0] in "
             "('sklearn', 'scipy', 'fastapi', 'pydantic', 'torch') or "
             "m.startswith(('raceintel.model_lab', 'ml.', 'api.', 'raceintel.labels'))]; "
             "print(','.join(sorted(banned)))")
    out = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parent.parent), timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", f"heavy imports: {out.stdout}"


# ---------------------------------------------------------------------------
# Canonical dev-data smoke test (read-only; 2021/2022 only).
# ---------------------------------------------------------------------------

def _season_frame(season, entity):
    import glob as _g
    files = sorted(_g.glob(str(ROOT / "data/v2/processed" / entity
                               / f"season={season}/*.parquet")))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


@pytest.mark.skipif(not (_HAS_D9 and _HAS_RESULTS),
                    reason="canonical data absent")
@pytest.mark.parametrize("season,race_id", [
    (2021, "2021-r12-R"),  # Belgium partial
    (2022, "2022-r18-R"),  # Japan red flag
    (2022, "2022-r07-R"),  # Monaco stale-heavy
])
def test_canonical_smoke(season, race_id):
    d9 = _season_frame(season, "driver_lap_state_d9")
    results = _season_frame(season, "results")
    races = _season_frame(season, "races")
    race_meta = {
        str(row["race_id"]): {
            "scheduled_laps": (None if pd.isna(
                row["total_laps_scheduled"]) else int(
                row["total_laps_scheduled"]))}
        for _, row in races.iterrows()
    }
    sub = d9[d9["race_id"] == race_id].reset_index(drop=True)
    assert len(sub) > 0
    first = sub.sort_values(["state_time_s", "lap_number", "driver_id"],
                            kind="mergesort").iloc[0]
    anchor = RS.AnchorObservation(
        race_id=race_id, anchor_driver_id=str(first["driver_id"]),
        anchor_lap_number=int(first["lap_number"]),
        anchor_state_time_s=float(first["state_time_s"]))
    started = time.perf_counter()
    snap = reconstruct_race_state(anchor, sub, results,
                                  race_meta=race_meta)
    elapsed_ms = (time.perf_counter() - started) * 1000.0
    assert snap.anchor_driver_id == anchor.anchor_driver_id
    assert snap.roster_size == len(
        results[results["race_id"] == race_id])
    assert snap.race_context.scheduled_laps is not None
    assert len(snap.observable_drivers) >= 1
    for entry in snap.observable_drivers:
        assert entry.observed_time_s <= snap.state_time_s
    payload = snap.to_dict()
    json.dumps(payload, allow_nan=False)
    print(f"\nSMOKE {race_id}: roster={snap.roster_size} "
          f"observable={len(snap.observable_drivers)} "
          f"reconstruct_ms={elapsed_ms:.1f}")
