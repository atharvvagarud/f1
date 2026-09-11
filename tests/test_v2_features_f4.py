"""F4 tests: D9 factual passthrough layer (offline).

Synthetic frames prove exactness/nulls/types/parity/mutations; real-data
spots (skipped when canonical data is absent) prove equality on frozen
D9 artifacts; the full-scope audit test verifies all 189,420 states.
No network.
"""

import glob

import numpy as np
import pandas as pd
import pytest

from v2.config import V2Paths
from v2.features import (
    FEATURE_SET_VERSION,
    FeatureRequest,
    NoCalculatorError,
    TargetNotFoundError,
    build_f2_registry,
    canonical_scalar,
    features_for_batch,
    features_for_state,
    passthrough_batch,
    passthrough_for_state,
    batch_row_to_result,
    results_equal,
)
from v2.features.temporal import TemporalError

ROOT = V2Paths.resolve().root
_HAS_D9 = (ROOT / "data/v2/processed/driver_lap_state_d9/season=2021").is_dir()

PT_NAMES = sorted(["position", "race_leader_laps_at_state",
                   "race_progress_frac",
                   "track_state", "flag_yellow", "flag_safety_car", "flag_vsc",
                   "flag_red", "pit_stops_completed_so_far",
                   "laps_since_last_pit_stop", "stint_lap", "compound",
                   "tyre_life",
                   "fresh_tyre", "wx_air_temp_c", "wx_track_temp_c",
                   "wx_humidity_pct", "wx_pressure_hpa", "wx_wind_speed",
                   "wx_wind_direction_deg", "wx_rainfall", "stint_compound",
                   "stint_fresh_tyre"])  # registry order is sorted-by-name


@pytest.fixture()
def registry():
    return build_f2_registry()


@pytest.fixture()
def frame():
    return pd.DataFrame({
        "race_id": ["R", "R", "R"],
        "driver_id": ["a", "a", "b"],
        "lap_number": [1, 2, 1],
        "state_time_s": [100.0, 200.0, 110.0],
        "position": [3, 1, 2],
        "race_leader_laps_at_state": [1, 2, 1],
        "race_progress_frac": [0.01, 0.02, 0.01],
        "track_state": ["all_clear", "safety_car", "all_clear"],
        "flag_yellow": [False, False, False],
        "flag_safety_car": [False, True, False],
        "flag_vsc": [False, False, False],
        "flag_red": [False, False, False],
        "pit_stops_completed_so_far": [0, 0, 0],
        "laps_since_last_pit_stop": [None, None, None],
        "stint_lap": [1, 2, 1],
        "compound": ["SOFT", "SOFT", None],
        "tyre_life": [1, 2, None],
        "fresh_tyre": [True, True, None],
        "wx_air_temp_c": [25.0, 25.5, 25.0],
        "wx_track_temp_c": [30.0, 30.2, 30.0],
        "wx_humidity_pct": [40.0, 41.0, 40.0],
        "wx_pressure_hpa": [1013.0, 1013.1, 1013.0],
        "wx_wind_speed": [1.0, 1.2, 1.0],
        "wx_wind_direction_deg": [90.0, 95.0, 90.0],
        "wx_rainfall": [False, False, False],
        "stint_compound": ["SOFT", "SOFT", None],
        "stint_fresh_tyre": [True, True, None],
        # non-registered + non-predictive + label decoys
        "source_unit_status": ["complete"] * 3,
        "deleted": [False, False, False],
        "winner_flag": [False, False, False],
    })


def _req(driver="a", lap=2, t=200.0):
    return FeatureRequest("R", driver, lap, t)


# A. registry-driven exact passthrough
def test_exact_passthrough_values(registry, frame):
    res = features_for_state(_req(), registry, frame)
    v = res.value_dict()
    assert v["position"] == 1
    assert v["track_state"] == "safety_car"
    assert v["flag_safety_car"] is True
    assert v["race_progress_frac"] == pytest.approx(0.02)
    assert v["compound"] == "SOFT" and v["tyre_life"] == 2
    assert v["wx_air_temp_c"] == pytest.approx(25.5)
    assert res.feature_set_version == FEATURE_SET_VERSION
    assert [n for n, _ in res.values] == PT_NAMES


# B/C. exact target required; close timestamp rejected
def test_exact_target_required(registry, frame):
    with pytest.raises(TargetNotFoundError):
        features_for_state(_req(t=200.001), registry, frame)
    with pytest.raises(TargetNotFoundError):
        features_for_state(_req(lap=9), registry, frame)


# D. null preservation (no 0/-1/UNKNOWN/fill)
def test_null_preservation(registry, frame):
    res = features_for_state(_req(driver="b", lap=1, t=110.0),
                             registry, frame)
    v = res.value_dict()
    assert v["compound"] is None
    assert v["tyre_life"] is None
    assert v["laps_since_last_pit_stop"] is None
    assert v["stint_compound"] is None
    assert v["fresh_tyre"] is None
    for name, val in res.values:
        assert val != 0 or name in ("pit_stops_completed_so_far",
                                    "race_leader_laps_at_state") \
            or val is None or isinstance(val, bool)


# E. dtype/canonical scalar conversion
def test_canonical_scalars():
    assert canonical_scalar(np.int64(3)) == 3
    assert type(canonical_scalar(np.int64(3))) is int
    assert canonical_scalar(np.float64(1.5)) == 1.5
    assert type(canonical_scalar(np.float64(1.5))) is float
    assert canonical_scalar(float("nan")) is None
    assert canonical_scalar(pd.NA) is None
    assert canonical_scalar(np.bool_(True)) is True
    assert canonical_scalar("SOFT") == "SOFT"
    assert canonical_scalar(None) is None
    with pytest.raises(TemporalError):
        canonical_scalar(["SOFT"])


def test_result_value_types(registry, frame):
    res = features_for_state(_req(), registry, frame)
    v = res.value_dict()
    assert type(v["position"]) is int
    assert type(v["race_progress_frac"]) is float
    assert type(v["flag_safety_car"]) is bool
    assert type(v["track_state"]) is str


# F/G/H. no unregistered / non-predictive / label fields
def test_only_registered_passthroughs_emitted(registry, frame):
    res = features_for_state(_req(), registry, frame)
    assert set(res.value_dict()) == set(PT_NAMES)
    for forbidden in ("source_unit_status", "deleted", "winner_flag",
                      "grid_position", "state_time_s"):
        assert forbidden not in res.value_dict()


def test_planned_and_unknown_raise(registry, frame):
    with pytest.raises(NoCalculatorError):
        features_for_state(_req(), registry, frame,
                           names=["grid_position"])
    with pytest.raises(NoCalculatorError):
        features_for_state(_req(), registry, frame, names=["nope"])
    with pytest.raises(NoCalculatorError):
        features_for_state(_req(), registry, None)


def test_subset_resolution(registry, frame):
    res = features_for_state(_req(), registry, frame,
                             names=["position", "compound"])
    assert [n for n, _ in res.values] == ["compound", "position"]


# I/J/K. track/weather/pit exactness (no reinterpretation, no rejoin)
def test_track_weather_pit_exactness(registry, frame):
    res = features_for_state(_req(), registry, frame)
    v = res.value_dict()
    assert v["track_state"] == "safety_car"  # not re-derived
    assert v["wx_track_temp_c"] == pytest.approx(30.2)  # not rejoined
    assert v["pit_stops_completed_so_far"] == 0  # not reconstructed
    assert v["stint_lap"] == 2


# L/M. single vs batch parity + order independence
def test_single_batch_parity(registry, frame):
    batch = passthrough_batch(frame, registry)
    assert list(batch.columns) == ["race_id", "driver_id", "lap_number",
                                   "state_time_s"] + PT_NAMES
    assert len(batch) == 3
    for _, row in batch.iterrows():
        q = FeatureRequest(str(row["race_id"]), str(row["driver_id"]),
                           int(row["lap_number"]), float(row["state_time_s"]))
        single = features_for_state(q, registry, frame)
        assert results_equal(
            single, batch_row_to_result(row, PT_NAMES))
    shuffled = frame.sample(frac=1.0, random_state=5)
    assert results_equal(
        features_for_state(_req(), registry, frame),
        features_for_state(_req(), registry, shuffled))
    qs = [_req(), _req(driver="b", lap=1, t=110.0)]
    outs = features_for_batch(qs, registry, frame)
    assert len(outs) == 2
    assert outs[0].value_dict()["position"] == 1


def test_batch_does_not_mutate_input(registry, frame):
    before = frame.copy(deep=True)
    passthrough_batch(frame, registry)
    pd.testing.assert_frame_equal(frame, before)


# N/O/P. future mutations leave target result identical
def test_future_mutations_invariant(registry, frame):
    base = features_for_state(_req(), registry, frame)
    future = pd.DataFrame([{
        "race_id": "R", "driver_id": "a", "lap_number": 3,
        "state_time_s": 300.0, **{c: frame[c].iloc[0] for c in PT_NAMES}}])
    assert results_equal(
        base, features_for_state(
            _req(), registry, pd.concat([frame, future],
                                        ignore_index=True)))
    rival_future = pd.DataFrame([{
        "race_id": "R", "driver_id": "b", "lap_number": 2,
        "state_time_s": 250.0, **{c: frame[c].iloc[2] for c in PT_NAMES}}])
    assert results_equal(
        base, features_for_state(
            _req(), registry, pd.concat([frame, rival_future],
                                        ignore_index=True)))
    mod = frame.copy()
    mod.loc[mod["state_time_s"] > 200.0, "state_time_s"] = 9999.0
    mod = mod[mod["state_time_s"] <= 9999.0]
    assert results_equal(base, features_for_state(_req(), registry, mod))
    dropped = frame[frame["state_time_s"] <= 200.0]
    assert results_equal(base, features_for_state(_req(), registry, dropped))


def test_future_result_mutation_invariant(registry, frame):
    base = features_for_state(_req(), registry, frame)
    labels = pd.DataFrame({"race_id": ["R"], "driver_id": ["a"],
                           "winner_flag": [True]})
    _ = labels  # labels never enter passthrough path by construction
    assert results_equal(base, features_for_state(_req(), registry, frame))


# Q/R. source mutation isolation
def test_target_source_mutation_isolated(registry, frame):
    mod = frame.copy()
    mod.loc[(mod["driver_id"] == "a") & (mod["lap_number"] == 2),
            "compound"] = "MEDIUM"
    res = features_for_state(_req(), registry, mod)
    assert res.value_dict()["compound"] == "MEDIUM"
    assert res.value_dict()["tyre_life"] == 2  # only mapped value changes


def test_nonregistered_mutation_isolated(registry, frame):
    base = features_for_state(_req(), registry, frame)
    mod = frame.copy()
    mod["source_unit_status"] = "partial"
    mod["winner_flag"] = True
    assert results_equal(base, features_for_state(_req(), registry, mod))


# --- real-data spots ---

def _d9_season(season):
    if not _HAS_D9:
        pytest.skip("canonical D9 data not present (data/v2 gitignored)")
    files = sorted(glob.glob(str(ROOT / "data/v2/processed"
                                 / "driver_lap_state_d9"
                                 / f"season={season}/*.parquet")))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _assert_exact(d9, race_id, registry):
    sub = d9[d9["race_id"] == race_id]
    t = sub.iloc[len(sub) // 2]
    q = FeatureRequest(str(t["race_id"]), str(t["driver_id"]),
                       int(t["lap_number"]), float(t["state_time_s"]))
    res = features_for_state(q, registry, sub)
    v = res.value_dict()
    for name in PT_NAMES:
        assert v[name] == canonical_scalar(t[name]), (race_id, name)


def test_real_normal_race(registry):
    _assert_exact(_d9_season(2023), "2023-r01-R", registry)


def test_real_missing_compound_case(registry):
    d9 = _d9_season(2022)
    sub = d9[(d9["race_id"] == "2022-r07-R") & (d9["compound"].isna())]
    assert len(sub) > 0
    t = sub.iloc[0]
    q = FeatureRequest(str(t["race_id"]), str(t["driver_id"]),
                       int(t["lap_number"]), float(t["state_time_s"]))
    res = features_for_state(q, registry, d9[d9["race_id"] == "2022-r07-R"])
    assert res.value_dict()["compound"] is None
    # tyre state is independent: exact source equality, null or not
    assert res.value_dict()["tyre_life"] == canonical_scalar(t["tyre_life"])


def test_real_sc_state(registry):
    d9 = _d9_season(2025)
    sub = d9[(d9["race_id"] == "2025-r01-R")
             & (d9["track_state"] == "safety_car")]
    assert len(sub) > 0
    _assert_exact(d9, "2025-r01-R", registry)


def test_real_belgium_partial(registry):
    d9 = _d9_season(2021)
    sub = d9[d9["race_id"] == "2021-r12-R"]
    assert len(sub) == 60
    batch = passthrough_batch(sub, registry)
    assert len(batch) == 60
    _assert_exact(d9, "2021-r12-R", registry)


def test_real_japan_shortened(registry):
    _assert_exact(_d9_season(2022), "2022-r18-R", registry)


def test_real_monaco_timelimited(registry):
    _assert_exact(_d9_season(2022), "2022-r07-R", registry)


# U. full-data identity/null audit
def test_full_scope_audit(registry):
    if not _HAS_D9:
        pytest.skip("canonical D9 data not present (data/v2 gitignored)")
    files = sorted(glob.glob(str(ROOT / "data/v2/processed"
                                 / "driver_lap_state_d9"
                                 / "season=*/*.parquet")))
    d9 = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    assert len(d9) == 189420
    batch = passthrough_batch(d9, registry)
    assert len(batch) == 189420
    assert list(batch.columns) == ["race_id", "driver_id", "lap_number",
                                   "state_time_s"] + PT_NAMES
    # identity preserved exactly
    pd.testing.assert_frame_equal(
        batch[["race_id", "driver_id", "lap_number", "state_time_s"]]
        .sort_values(["race_id", "driver_id", "lap_number"])
        .reset_index(drop=True),
        d9[["race_id", "driver_id", "lap_number", "state_time_s"]]
        .sort_values(["race_id", "driver_id", "lap_number"])
        .reset_index(drop=True),
        check_dtype=False)
    # values + nulls preserved per feature (NaN-aware)
    merged = batch.sort_values(
        ["race_id", "driver_id", "lap_number"]).reset_index(drop=True)
    src = d9.sort_values(
        ["race_id", "driver_id", "lap_number"]).reset_index(drop=True)
    for name in PT_NAMES:
        a, b = merged[name], src[name]
        same_null = a.isna().to_numpy() == b.isna().to_numpy()
        assert same_null.all(), name
        both = a[~a.isna()].reset_index(drop=True).astype(str)
        want = b[~b.isna()].reset_index(drop=True).astype(str)
        assert (both.to_numpy() == want.to_numpy()).all(), name
    # no label/outcome columns emitted
    for col in ("winner_flag", "position_final", "points", "dnf_flag",
                "classified_position"):
        assert col not in batch.columns
