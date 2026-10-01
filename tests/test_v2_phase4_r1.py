"""Phase-4 R1: canonical RaceState domain model (synthetic, no 2025, no matrix).

Covers the R1-M checklist: anchor validation, construction invariants,
ordering, staleness, roster/observability, serialization, firewalls,
import guards. Nothing here touches frozen Phase-1/2/3 code paths.
"""

import dataclasses
import json
import math
import subprocess
import sys
from pathlib import Path

import pytest

from raceintel.race_state import race_state as rs


# ---------------------------------------------------------------------------
# Helpers: small synthetic snapshot builders (no data loading).
# ---------------------------------------------------------------------------

def _anchor_entry(driver="alonso", lap=10, t=1234.5):
    return rs.DriverRaceState(
        driver_id=driver, observable=True,
        observed_lap_number=lap, observed_time_s=t, observation_age_s=0.0,
        position=3, gap_to_leader_s=4.5, gap_to_leader_valid=True,
        gap_to_leader_laps=0, gap_to_ahead_s=1.2, gap_to_ahead_valid=True,
        gap_to_ahead_laps=0, compound="SOFT", tyre_life=10, fresh_tyre=False,
        stint_number=2, stint_lap=10, pit_stops_completed_so_far=1,
        laps_since_last_pit_stop=9, constructor_id="aston_martin",
        driver_number=14)


def _stale_entry(driver="hamilton", t=1234.5, age=48.2):
    return rs.DriverRaceState(
        driver_id=driver, observable=True,
        observed_lap_number=9, observed_time_s=t - age,
        observation_age_s=age, position=7, compound="MEDIUM",
        constructor_id="mercedes")


def _snapshot(anchor=None, extras=("hamilton", "norris"), t=1234.5,
              lap=10, anchor_driver="alonso"):
    anchor = anchor or _anchor_entry(driver=anchor_driver, lap=lap, t=t)
    drivers = [anchor]
    drivers += [rs.DriverRaceState.unobserved(d) for d in extras]
    return rs.RaceState(
        race_id="2024-r01-R", anchor_driver_id=anchor_driver,
        anchor_lap_number=lap, state_time_s=t, drivers=tuple(drivers),
        race_context=rs.RaceContext(
            race_leader_laps_at_state=10, race_progress_frac=10 / 57,
            scheduled_laps=57, season=2024, round_no=1,
            circuit_id="bahrain"),
        weather=rs.WeatherState(air_temp_c=28.0, rainfall=False,
                                observed_at_s=t - 60.0,
                                observation_age_s=60.0),
        race_control=rs.RaceControlState(
            track_state="all_clear", flag_yellow=False,
            flag_safety_car=False, flag_red=False, flag_vsc=False,
            last_message_category="Flag", last_message_flag="GREEN",
            last_message_age_s=120.0))


# ---------------------------------------------------------------------------
# 1-2. AnchorObservation.
# ---------------------------------------------------------------------------

def test_anchor_valid():
    anchor = rs.AnchorObservation(
        race_id="2024-r01-R", anchor_driver_id="alonso",
        anchor_lap_number=10, anchor_state_time_s=1234.5)
    assert anchor.to_dict() == {
        "race_id": "2024-r01-R", "anchor_driver_id": "alonso",
        "anchor_lap_number": 10, "anchor_state_time_s": 1234.5}


@pytest.mark.parametrize("kwargs", [
    {"race_id": "2024-r01-R", "anchor_driver_id": "alonso",
     "anchor_lap_number": 10, "anchor_state_time_s": float("nan")},
    {"race_id": "2024-r01-R", "anchor_driver_id": "alonso",
     "anchor_lap_number": 10, "anchor_state_time_s": float("inf")},
    {"race_id": "2024-r01-R", "anchor_driver_id": "alonso",
     "anchor_lap_number": 10, "anchor_state_time_s": float("-inf")},
    {"race_id": "", "anchor_driver_id": "alonso",
     "anchor_lap_number": 10, "anchor_state_time_s": 1.0},
    {"race_id": "2024-r01-R", "anchor_driver_id": "  ",
     "anchor_lap_number": 10, "anchor_state_time_s": 1.0},
    {"race_id": "2024-r01-R", "anchor_driver_id": "alonso",
     "anchor_lap_number": 0, "anchor_state_time_s": 1.0},
    {"race_id": "2024-r01-R", "anchor_driver_id": "alonso",
     "anchor_lap_number": True, "anchor_state_time_s": 1.0},
    {"race_id": "2024-r01-R", "anchor_driver_id": "alonso",
     "anchor_lap_number": 10, "anchor_state_time_s": True},
    {"race_id": "2024-r01-R", "anchor_driver_id": "alonso",
     "anchor_lap_number": "10", "anchor_state_time_s": 1.0},
    {"race_id": 202401, "anchor_driver_id": "alonso",
     "anchor_lap_number": 10, "anchor_state_time_s": 1.0},
])
def test_anchor_invalid(kwargs):
    with pytest.raises(rs.InvalidRaceStateError):
        rs.AnchorObservation(**kwargs)


# ---------------------------------------------------------------------------
# 3-6. RaceState construction, ordering, duplicates, future observation.
# ---------------------------------------------------------------------------

def test_race_state_construction():
    snap = _snapshot()
    assert snap.roster_size == 3
    assert snap.roster_driver_ids == ("alonso", "hamilton", "norris")
    assert snap.observable_driver_ids == ("alonso",)
    assert snap.unobservable_driver_ids == ("hamilton", "norris")


def test_deterministic_driver_ordering():
    snap = _snapshot(extras=("norris", "hamilton"))
    assert snap.roster_driver_ids == ("alonso", "hamilton", "norris")
    assert [d["driver_id"] for d in snap.to_dict()["drivers"]] == [
        "alonso", "hamilton", "norris"]
    assert _snapshot().to_dict() == _snapshot().to_dict()


def test_duplicate_driver_rejected():
    with pytest.raises(rs.InvalidRaceStateError):
        _snapshot(extras=("hamilton", "hamilton"))


def test_observed_time_cannot_exceed_snapshot_t():
    bad = rs.DriverRaceState(
        driver_id="hamilton", observable=True, observed_lap_number=11,
        observed_time_s=1300.0, observation_age_s=0.0)
    with pytest.raises(rs.InvalidRaceStateError):
        rs.RaceState(
            race_id="2024-r01-R", anchor_driver_id="alonso",
            anchor_lap_number=10, state_time_s=1234.5,
            drivers=(_anchor_entry(), bad),
            race_context=rs.RaceContext(), weather=rs.WeatherState(),
            race_control=rs.RaceControlState())


# ---------------------------------------------------------------------------
# 7. Observation-age semantics.
# ---------------------------------------------------------------------------

def test_observation_age_semantics():
    t = 1234.5
    stale = _stale_entry(t=t)
    assert stale.observation_age_s == pytest.approx(t - stale.observed_time_s)
    snap = rs.RaceState(
        race_id="2024-r01-R", anchor_driver_id="alonso",
        anchor_lap_number=10, state_time_s=t,
        drivers=(_anchor_entry(t=t), stale),
        race_context=rs.RaceContext(), weather=rs.WeatherState(),
        race_control=rs.RaceControlState())
    assert snap.observable_driver_ids == ("alonso", "hamilton")
    by_id = {d.driver_id: d for d in snap.drivers}
    assert by_id["alonso"].observation_age_s == 0.0
    assert by_id["hamilton"].observation_age_s == pytest.approx(48.2)
    # Unobservable members carry null age, not zero.
    null_age = rs.DriverRaceState.unobserved("norris")
    assert null_age.observation_age_s is None
    with pytest.raises(rs.InvalidRaceStateError):
        rs.DriverRaceState(driver_id="x", observable=True,
                           observed_lap_number=1, observed_time_s=5.0,
                           observation_age_s=-0.5)
    # Age inconsistent with T - observed is a snapshot-level violation.
    inconsistent = rs.DriverRaceState(
        driver_id="alonso", observable=True, observed_lap_number=10,
        observed_time_s=1234.5, observation_age_s=999.0)
    with pytest.raises(rs.InvalidRaceStateError):
        rs.RaceState(
            race_id="2024-r01-R", anchor_driver_id="alonso",
            anchor_lap_number=10, state_time_s=1234.5,
            drivers=(inconsistent,),
            race_context=rs.RaceContext(), weather=rs.WeatherState(),
            race_control=rs.RaceControlState())


# ---------------------------------------------------------------------------
# 8-9. Roster vs observable; zero-state entrants.
# ---------------------------------------------------------------------------

def test_roster_vs_observable_distinction():
    snap = _snapshot()
    assert set(snap.roster_driver_ids) == {"alonso", "hamilton", "norris"}
    assert len(snap.observable_drivers) == 1
    # Roster membership is structural, not inferred from observability.
    assert "hamilton" in snap.roster_driver_ids
    assert "hamilton" not in snap.observable_driver_ids


def test_zero_state_entrant_representation():
    zero = rs.DriverRaceState.unobserved("bruno_senna_test")
    assert zero.observable is False
    payload = zero.to_dict()
    state_fields = {k: v for k, v in payload.items()
                    if k not in ("driver_id", "observable")}
    assert set(state_fields.values()) == {None}
    # No zero-fill: position/probability-shaped fields stay null.
    assert zero.position is None
    assert "winner_probability" not in payload
    # Unobservable members may not smuggle state.
    with pytest.raises(rs.InvalidRaceStateError):
        rs.DriverRaceState(driver_id="x", observable=False, position=0)
    with pytest.raises(rs.InvalidRaceStateError):
        rs.DriverRaceState(driver_id="x", observable=False,
                           observed_lap_number=0, observed_time_s=0.0,
                           observation_age_s=0.0)


# ---------------------------------------------------------------------------
# 10-13. None handling + deterministic JSON-safe serialization.
# ---------------------------------------------------------------------------

def test_none_handling_and_partial_fields():
    thin = rs.DriverRaceState(
        driver_id="alonso", observable=True, observed_lap_number=1,
        observed_time_s=90.0, observation_age_s=0.0)
    assert thin.gap_to_leader_s is None
    assert thin.gap_to_leader_valid is None
    snap = rs.RaceState(
        race_id="2024-r01-R", anchor_driver_id="alonso",
        anchor_lap_number=1, state_time_s=90.0, drivers=(thin,),
        race_context=rs.RaceContext(), weather=rs.WeatherState(),
        race_control=rs.RaceControlState())
    assert snap.race_context.to_dict()["scheduled_laps"] is None
    assert snap.weather.to_dict()["air_temp_c"] is None
    assert snap.race_control.to_dict()["track_state"] is None


def test_deterministic_serialization():
    first = _snapshot().to_dict()
    second = _snapshot().to_dict()
    assert first == second
    assert list(first.keys()) == list(second.keys())
    assert [d["driver_id"] for d in first["drivers"]] == [
        "alonso", "hamilton", "norris"]
    assert first["roster_size"] == 3


def test_json_safe_serialization():
    payload = _snapshot().to_dict()
    text = json.dumps(payload, allow_nan=False, sort_keys=True)
    assert json.loads(text)["race_id"] == "2024-r01-R"
    # No pandas/numpy scalar leakage: exact primitive types only.
    def _check(node):
        if isinstance(node, dict):
            for value in node.values():
                _check(value)
        elif isinstance(node, list):
            for value in node:
                _check(value)
        elif node is None or isinstance(node, (str, bool)):
            return
        elif isinstance(node, int):
            return
        elif isinstance(node, float):
            assert math.isfinite(node)
            return
        else:  # pragma: no cover - must never happen
            raise AssertionError(f"non-primitive leaked: {node!r}")
    _check(payload)


def test_no_nan_infinity_survives_construction():
    with pytest.raises(rs.InvalidRaceStateError):
        rs.DriverRaceState(driver_id="x", observable=True,
                           observed_lap_number=1, observed_time_s=5.0,
                           observation_age_s=0.0, gap_to_leader_s=float("nan"))
    with pytest.raises(rs.InvalidRaceStateError):
        rs.WeatherState(air_temp_c=float("inf"))
    with pytest.raises(rs.InvalidRaceStateError):
        rs.RaceContext(race_progress_frac=float("-inf"))


# ---------------------------------------------------------------------------
# 14-16. Label/outcome firewall + no model-feature coupling.
# ---------------------------------------------------------------------------

def test_label_firewall_names():
    forbidden = rs.label_outcome_fields()
    for name in ("final_position", "is_winner", "is_podium",
                 "scored_points", "position_change_from_state",
                 "gains_position_by_finish", "loses_position_by_finish",
                 "classified_position", "classified_flag", "points",
                 "laps_completed", "winner_flag", "podium_flag",
                 "points_finish_flag",
                 "eligible_is_winner", "eligible_ordinal_final_position",
                 "end_lap"):
        assert name in forbidden, name
    assert rs.domain_field_names() & forbidden == set()


def test_firewall_matches_canonical_label_names():
    from raceintel.labels.contracts import CANONICAL_LABEL_NAMES
    assert rs._CANONICAL_TARGET_NAMES == set(CANONICAL_LABEL_NAMES)


def test_no_model_feature_coupling():
    names = rs.domain_field_names()
    for banned in ("winner_probability", "prediction", "predicted",
                   "ALL_84", "feature", "estimator", "probability",
                   "logreg", "model"):
        assert banned not in names, banned
    # Exact pinned allow-list: future additions must update this deliberately.
    assert names == frozenset({
        "race_id", "anchor_driver_id", "anchor_lap_number",
        "anchor_state_time_s", "state_time_s", "drivers", "driver_id",
        "observable", "observed_lap_number", "observed_time_s",
        "observation_age_s", "position", "gap_to_leader_s",
        "gap_to_leader_valid", "gap_to_leader_laps", "gap_to_ahead_s",
        "gap_to_ahead_valid", "gap_to_ahead_laps", "compound", "tyre_life",
        "fresh_tyre", "stint_number", "stint_lap",
        "pit_stops_completed_so_far", "laps_since_last_pit_stop",
        "constructor_id", "driver_number", "race_context",
        "race_leader_laps_at_state", "race_progress_frac",
        "scheduled_laps", "season", "round_no", "circuit_id", "weather",
        "air_temp_c", "track_temp_c", "humidity_pct", "pressure_hpa",
        "wind_speed", "wind_direction_deg", "rainfall", "observed_at_s",
        "race_control", "track_state", "flag_yellow", "flag_safety_car",
        "flag_red", "flag_vsc", "last_message_category",
        "last_message_flag", "last_message_age_s"})
    # Outcome kwargs are rejected structurally (frozen dataclasses).
    with pytest.raises(TypeError):
        rs.DriverRaceState(driver_id="x", observable=False,
                           is_winner=True)  # type: ignore[call-arg]
    with pytest.raises(dataclasses.FrozenInstanceError):
        anchor = rs.AnchorObservation(
            race_id="r", anchor_driver_id="d", anchor_lap_number=1,
            anchor_state_time_s=1.0)
        anchor.race_id = "other"  # type: ignore[misc]


def test_field_provenance_complete():
    for name in (f.name for f in dataclasses.fields(rs.DriverRaceState)):
        tag = rs.driver_field_provenance(name)
        assert tag in (rs.FACTUAL_OBSERVED, rs.DERIVED_PAST_ONLY)
    assert rs.driver_field_provenance("observation_age_s") == \
        rs.DERIVED_PAST_ONLY
    assert rs.driver_field_provenance("position") == rs.FACTUAL_OBSERVED
    assert rs.driver_field_provenance("compound") == rs.FACTUAL_OBSERVED
    with pytest.raises(rs.RaceStateError):
        rs.driver_field_provenance("is_winner")


# ---------------------------------------------------------------------------
# 17. No pandas/DataFrame (or ML/API) dependency in stored domain state.
# ---------------------------------------------------------------------------

def test_no_heavy_imports_in_isolated_interpreter():
    probe = ("import sys, raceintel.race_state.race_state; "
             "banned = [m for m in sys.modules if m.split('.')[0] in "
             "('pandas', 'numpy', 'sklearn', 'scipy', 'fastapi', "
             "'pydantic', 'torch') or m.startswith("
             "('raceintel.model_lab', 'ml.', 'api.', 'raceintel.labels'))]; "
             "print(','.join(sorted(banned)))")
    out = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parent.parent), timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", f"heavy imports: {out.stdout}"


def test_numpy_scalars_rejected_structurally():
    numpy = pytest.importorskip("numpy")
    with pytest.raises(rs.InvalidRaceStateError):
        rs.DriverRaceState(
            driver_id="x", observable=True,
            observed_lap_number=numpy.int64(1),
            observed_time_s=5.0, observation_age_s=0.0)
    with pytest.raises(rs.InvalidRaceStateError):
        rs.AnchorObservation(
            race_id="r", anchor_driver_id="d", anchor_lap_number=1,
            anchor_state_time_s=numpy.float64(5.0))


# ---------------------------------------------------------------------------
# 18-20. Red-flag/gap nullables, bool/int strictness, anchor consistency.
# ---------------------------------------------------------------------------

def test_red_flag_gap_nullable_semantics():
    red = rs.RaceControlState(track_state="red_flag", flag_red=True,
                              flag_yellow=False, flag_safety_car=False,
                              flag_vsc=False)
    assert red.to_dict()["track_state"] == "red_flag"
    # Seconds gap invalid under suspension: null value, explicit invalid.
    entry = rs.DriverRaceState(
        driver_id="alonso", observable=True, observed_lap_number=10,
        observed_time_s=1234.5, observation_age_s=0.0, position=3,
        gap_to_leader_s=None, gap_to_leader_valid=False,
        gap_to_leader_laps=2)
    assert entry.gap_to_leader_s is None
    assert entry.gap_to_leader_valid is False
    with pytest.raises(rs.InvalidRaceStateError):
        rs.RaceControlState(track_state="CHEQUERED")


def test_bool_int_strictness():
    with pytest.raises(rs.InvalidRaceStateError):
        rs.DriverRaceState(driver_id="x", observable=1,  # type: ignore[arg-type]
                           observed_lap_number=1, observed_time_s=5.0,
                           observation_age_s=0.0)
    with pytest.raises(rs.InvalidRaceStateError):
        rs.WeatherState(rainfall=1)  # type: ignore[arg-type]
    with pytest.raises(rs.InvalidRaceStateError):
        rs.DriverRaceState(driver_id="x", observable=True,
                           observed_lap_number=1.5,  # type: ignore[arg-type]
                           observed_time_s=5.0, observation_age_s=0.0)


@pytest.mark.parametrize("mutate", [
    "anchor_missing", "anchor_unobservable", "anchor_lap_mismatch",
    "anchor_time_mismatch", "empty_drivers", "empty_race",
])
def test_anchor_identity_consistency(mutate):
    t, lap = 1234.5, 10
    anchor_id = "alonso"
    drivers = [_anchor_entry(t=t, lap=lap), _stale_entry(t=t)]
    kwargs = {"race_id": "2024-r01-R", "anchor_driver_id": anchor_id,
              "anchor_lap_number": lap, "state_time_s": t,
              "drivers": tuple(drivers), "race_context": rs.RaceContext(),
              "weather": rs.WeatherState(),
              "race_control": rs.RaceControlState()}
    if mutate == "anchor_missing":
        kwargs["anchor_driver_id"] = "vettel"
    elif mutate == "anchor_unobservable":
        kwargs["drivers"] = (rs.DriverRaceState.unobserved("alonso"),
                             _stale_entry(t=t))
    elif mutate == "anchor_lap_mismatch":
        kwargs["anchor_lap_number"] = 11
    elif mutate == "anchor_time_mismatch":
        kwargs["state_time_s"] = 1200.0
    elif mutate == "empty_drivers":
        kwargs["drivers"] = ()
    elif mutate == "empty_race":
        kwargs["race_id"] = ""
    with pytest.raises((rs.InvalidRaceStateError, rs.RaceStateError)):
        rs.RaceState(**kwargs)


def test_error_taxonomy():
    assert issubclass(rs.InvalidRaceStateError, rs.RaceStateError)
    assert issubclass(rs.RaceStateError, ValueError)
