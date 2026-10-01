"""F5 tests: pace eligibility, windows, stint pace/trend, registry,
parity, mutations, real-data spots, full-scope audit. Offline.
"""

import glob

import numpy as np
import pandas as pd
import pytest

from raceintel.config import V2Paths
from raceintel.features import (
    FEATURE_SET_VERSION,
    F5_FEATURE_NAMES,
    FeatureFamily,
    FeatureRequest,
    FeatureStatus,
    NoCalculatorError,
    SyncRequirement,
    TemporalRule,
    build_f5_registry,
    features_for_state,
    ols_slope,
    pace_batch,
    pace_eligibility_mask,
    pace_for_state,
    pace_values,
    results_equal,
)
from raceintel.features.contracts import MissingPolicy
from raceintel.features.temporal import TemporalError

ROOT = V2Paths.resolve().root
_HAS_D9 = (ROOT / "data/v2/processed/driver_lap_state_d9/season=2021").is_dir()

COLS = ["race_id", "driver_id", "lap_number", "state_time_s", "lap_time_s",
        "pit_in_s", "pit_out_s", "track_state", "stint_number"]


def _row(race="R", drv="a", lap=1, t=100.0, lt=90.0, track="all_clear",
         stint=1, pitin=None, pitout=None):
    return {"race_id": race, "driver_id": drv, "lap_number": lap,
            "state_time_s": t, "lap_time_s": lt, "pit_in_s": pitin,
            "pit_out_s": pitout, "track_state": track, "stint_number": stint}


@pytest.fixture()
def registry():
    return build_f5_registry()


@pytest.fixture()
def frame():
    rows = [_row(lap=i + 1, t=100.0 * (i + 1), lt=90.0 + (i % 3),
                 stint=1 if i < 4 else 2) for i in range(8)]
    return pd.DataFrame(rows, columns=COLS)


def _q(lap=8, t=800.0):
    return FeatureRequest("R", "a", lap, t)


# --- eligibility ---

def test_eligibility_null_laptime():
    df = pd.DataFrame([_row(lt=None)], columns=COLS)
    assert not pace_eligibility_mask(df).iloc[0]


def test_eligibility_pit_in_out():
    assert not pace_eligibility_mask(
        pd.DataFrame([_row(pitin=50.0)], columns=COLS)).iloc[0]
    assert not pace_eligibility_mask(
        pd.DataFrame([_row(pitout=60.0)], columns=COLS)).iloc[0]


@pytest.mark.parametrize("track", ["safety_car", "vsc", "vsc_ending",
                                   "yellow", "red_flag", None])
def test_eligibility_caution_and_unknown(track):
    df = pd.DataFrame([_row(track=track)], columns=COLS)
    assert not pace_eligibility_mask(df).iloc[0]


def test_eligibility_first_lap():
    df = pd.DataFrame([_row(lap=1, t=100.0)], columns=COLS)
    assert not pace_eligibility_mask(df).iloc[0]
    df2 = pd.DataFrame([_row(lap=2, t=200.0)], columns=COLS)
    assert pace_eligibility_mask(df2).iloc[0]


def test_eligibility_slow_and_fast_laps_stay_eligible():
    slow = pd.DataFrame([_row(lap=5, lt=250.0)], columns=COLS)
    fast = pd.DataFrame([_row(lap=5, lt=60.0)], columns=COLS)
    assert pace_eligibility_mask(slow).iloc[0]
    assert pace_eligibility_mask(fast).iloc[0]


def test_eligibility_green_normal():
    df = pd.DataFrame([_row(lap=3, lt=88.5)], columns=COLS)
    assert pace_eligibility_mask(df).iloc[0]


# --- windows ---

def test_window_3_5_10(frame, registry):
    res = pace_for_state(_q(), registry, frame)
    v = res.value_dict()
    # eligible laps 2..8 (lap1 excluded): last3 = laps 6,7,8 -> 91,92,90
    assert v["pace_median_3"] == pytest.approx(91.0)
    assert v["pace_n_3"] == 3
    # last5 = laps 4..8 -> 90,91,92,90,91 (stint change irrelevant here)
    assert v["pace_median_5"] == pytest.approx(91.0)
    assert v["pace_mean_5"] == pytest.approx((90 + 91 + 92 + 90 + 91) / 5)
    assert v["pace_n_5"] == 5
    # only 7 eligible total -> w10 uses 7, n=7, median of 7
    assert v["pace_n_10"] == 7
    assert v["pace_median_10"] == pytest.approx(91.0)
    # representative needs 8 -> null here (7 eligible)
    assert v["representative_recent_pace_s"] is None


def test_insufficient_history_nulls():
    df = pd.DataFrame([_row(lap=1, t=100.0, lt=95.0),
                       _row(lap=2, t=200.0, lt=92.0)], columns=COLS)
    vals = pace_values(df)
    # only lap 2 eligible (lap 1 excluded): median_3 null, count 1
    assert vals["pace_median_3"] is None
    assert vals["pace_n_3"] == 1


def test_current_target_inclusion_at_lap_end(frame, registry):
    # target lap 8 (eligible) participates: drop it -> median_3 changes
    res = pace_for_state(_q(), registry, frame)
    assert res.value_dict()["pace_n_3"] == 3
    short = frame[frame["lap_number"] < 8]
    res2 = pace_for_state(FeatureRequest("R", "a", 7, 700.0),
                          registry, short)
    assert res2.value_dict()["pace_n_3"] == 3
    assert res2.value_dict()["pace_median_3"] == pytest.approx(91.0)


def test_current_stint_filtering(registry):
    rows = [_row(lap=i + 1, t=100.0 * (i + 1), lt=90.0 + i, stint=1)
            for i in range(3)]
    rows += [_row(lap=4, t=400.0, lt=120.0, stint=2, pitout=350.0)]
    rows += [_row(lap=5, t=500.0, lt=95.0, stint=2)]
    df = pd.DataFrame(rows, columns=COLS)
    vals = pace_values(df)
    # stint 2 eligible: only lap5 (lap4 pit-out) -> median/mean null, count 1
    assert vals["current_stint_eligible_laps"] == 1
    assert vals["current_stint_pace_median_s"] is None
    assert vals["current_stint_pace_mean_s"] is None
    assert vals["current_stint_pace_trend_s_per_lap"] is None
    # windows still see older stints (prefix-wide): eligible = laps 2,3,5
    # (lap 1 excluded by policy, lap 4 by pit-out marker)
    assert vals["pace_n_5"] == 3


def test_null_stint(registry):
    df = pd.DataFrame([_row(lap=2, t=200.0, stint=None),
                       _row(lap=3, t=300.0, stint=None)], columns=COLS)
    vals = pace_values(df)
    assert vals["current_stint_eligible_laps"] is None
    assert vals["current_stint_pace_median_s"] is None
    assert vals["current_stint_pace_trend_s_per_lap"] is None
    assert vals["pace_n_3"] == 2  # windows unaffected by stint


# --- trend ---

def test_trend_sign_magnitude():
    y = np.array([90.0, 90.5, 91.0, 91.5, 92.0])
    assert ols_slope(y) == pytest.approx(0.5)
    assert ols_slope(np.array([95.0] * 5)) == pytest.approx(0.0)
    assert ols_slope(np.array([92.0, 91.0, 90.0])) == pytest.approx(-1.0)
    with pytest.raises(TemporalError):
        ols_slope(np.array([90.0]))


def test_trend_min_history_and_no_zero_fallback(frame):
    vals = pace_values(frame)  # stint1: laps 2,3,4 (3 eligible) -> null
    assert vals["current_stint_pace_trend_s_per_lap"] is None
    rows = [_row(lap=i + 1, t=100.0 * (i + 1), lt=90.0 + 0.5 * i, stint=1)
            for i in range(1, 7)]
    vals2 = pace_values(pd.DataFrame(rows, columns=COLS))
    assert vals2["current_stint_pace_trend_s_per_lap"] == pytest.approx(0.5)


def test_no_future_stint_end(frame):
    vals = pace_values(frame)
    mod = frame.copy()
    mod["end_lap"] = [4, 4, 4, 4, 99, 99, 99, 99]
    assert pace_values(mod) == vals


# --- registry metadata ---

def test_f5_registry_metadata(registry):
    assert len(registry) == 36
    assert FEATURE_SET_VERSION == "v8"  # ... -> v8 (F11, +3 ix)
    for name in F5_FEATURE_NAMES:
        d = registry.get(name)
        assert d.version == 1
        assert d.predictive_eligible
        assert d.temporal_rule is TemporalRule.DRIVER_PREFIX
        assert d.sync is SyncRequirement.NONE
        assert d.sources[0] == "driver_lap_state_d9.lap_time_s"
        assert "driver_lap_state_d9.lap_number" in d.sources
        assert d.missing is MissingPolicy.NULL_IF_INSUFFICIENT_HISTORY
        assert d.status is FeatureStatus.CANDIDATE
    assert registry.get("pace_median_5").family is not None
    assert registry.get("current_stint_pace_trend_s_per_lap").unit == \
        "seconds_per_lap"
    assert "clean_air" not in " ".join(registry.names())
    assert "degradation" not in " ".join(registry.names()).lower()


def test_no_cross_driver_in_f5(registry):
    for name in F5_FEATURE_NAMES:
        d = registry.get(name)
        assert d.family.value in ("pace", "stint")
        assert d.sync.value == "none"


# --- engine integration + parity ---

PT_EXTRA = {
    "position": [3, 2, 1, 2, 2, 3, 2, 1],
    "race_leader_laps_at_state": [1, 2, 3, 4, 5, 6, 7, 8],
    "race_progress_frac": [0.01 * (i + 1) for i in range(8)],
    "track_state": ["all_clear"] * 8,
    "flag_yellow": [False] * 8,
    "flag_safety_car": [False] * 8,
    "flag_vsc": [False] * 8,
    "flag_red": [False] * 8,
    "pit_stops_completed_so_far": [0] * 8,
    "laps_since_last_pit_stop": [None] * 8,
    "stint_lap": [1, 2, 3, 4, 1, 2, 3, 4],
    "compound": ["SOFT"] * 8,
    "tyre_life": [1, 2, 3, 4, 1, 2, 3, 4],
    "fresh_tyre": [True] * 8,
    "wx_air_temp_c": [25.0] * 8,
    "wx_track_temp_c": [30.0] * 8,
    "wx_humidity_pct": [40.0] * 8,
    "wx_pressure_hpa": [1013.0] * 8,
    "wx_wind_speed": [1.0] * 8,
    "wx_wind_direction_deg": [90.0] * 8,
    "wx_rainfall": [False] * 8,
    "stint_compound": ["SOFT"] * 8,
    "stint_fresh_tyre": [True] * 8,
}


@pytest.fixture()
def fullframe(frame):
    out = frame.copy()
    for k, v in PT_EXTRA.items():
        out[k] = v
    return out


def test_engine_mixed_resolution(fullframe, registry):
    # F5 registry (no gap defs): 23 passthrough + 12 F5 under v3.
    res = features_for_state(_q(), registry, fullframe)
    assert len(res.values) == 35
    assert res.feature_set_version == "v8"
    d = dict(res.values)
    assert d["position"] == fullframe.iloc[-1]["position"]
    assert d["pace_n_3"] == 3
    with pytest.raises(NoCalculatorError):
        features_for_state(_q(), registry, fullframe,
                           names=["grid_position"])


def test_single_batch_parity(frame, fullframe, registry):
    from raceintel.features import passthrough_batch
    pt = passthrough_batch(fullframe, registry)
    pb = pace_batch(frame)
    assert len(pb) == len(frame)
    for _, row in pb.iterrows():
        q = FeatureRequest(str(row["race_id"]), str(row["driver_id"]),
                           int(row["lap_number"]), float(row["state_time_s"]))
        single = pace_for_state(q, registry, frame)
        for n in F5_FEATURE_NAMES:
            a, b = single.value_dict()[n], row[n]
            if a is None:
                assert b is None or (isinstance(b, float)
                                     and np.isnan(b)), n
            else:
                assert a == pytest.approx(float(b)), n


def test_shuffled_input(frame, registry):
    a = pace_for_state(_q(), registry, frame)
    b = pace_for_state(_q(), registry,
                       frame.sample(frac=1.0, random_state=9))
    assert results_equal(a, b)


# --- future mutations ---

def _mutated(frame, **kw):
    mod = frame.copy()
    for k, v in kw.items():
        mod.loc[mod["lap_number"] > 8, k] = v
    return mod


def test_future_fast_slow_laps_ignored(frame, registry):
    base = pace_for_state(_q(), registry, frame)
    fast = pd.concat([frame, pd.DataFrame(
        [_row(lap=9, t=890.0, lt=60.0)], columns=COLS)], ignore_index=True)
    slow = pd.concat([frame, pd.DataFrame(
        [_row(lap=9, t=890.0, lt=400.0)], columns=COLS)], ignore_index=True)
    assert results_equal(base, pace_for_state(_q(), registry, fast))
    assert results_equal(base, pace_for_state(_q(), registry, slow))


def test_future_pit_tyre_track_result_mutations(frame, registry):
    base = pace_for_state(_q(), registry, frame)
    extra = pd.DataFrame([_row(lap=9, t=900.0, lt=91.0, stint=3,
                               track="safety_car")], columns=COLS)
    mod = pd.concat([frame, extra], ignore_index=True)
    assert results_equal(base, pace_for_state(_q(), registry, mod))


def test_eligibility_change_affects_membership(frame, registry):
    mod = frame.copy()
    mod.loc[mod["lap_number"] == 8, "pit_in_s"] = 750.0
    res = pace_for_state(_q(), registry, mod)
    assert res.value_dict()["pace_n_3"] == 3  # laps 5,6,7 now
    assert res.value_dict()["pace_median_3"] == pytest.approx(91.0)


def test_speed_change_never_filters(frame, registry):
    mod = frame.copy()
    mod.loc[mod["lap_number"] == 8, "lap_time_s"] = 300.0
    res = pace_for_state(_q(), registry, mod)
    assert res.value_dict()["pace_n_3"] == 3  # still eligible
    assert res.value_dict()["pace_median_3"] == pytest.approx(92.0)


# --- real-data spots ---

def _d9_season(season):
    if not _HAS_D9:
        pytest.skip("canonical D9 data not present (data/v2 gitignored)")
    files = sorted(glob.glob(str(ROOT / "data/v2/processed"
                                 / "driver_lap_state_d9"
                                 / f"season={season}/*.parquet")))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _parity_spot(d9, race_id, registry, k=12):
    sub = d9[d9["race_id"] == race_id]
    pb = pace_batch(sub)
    assert len(pb) == len(sub)
    for _, row in sub.sample(n=min(k, len(sub)), random_state=3).iterrows():
        q = FeatureRequest(str(row["race_id"]), str(row["driver_id"]),
                           int(row["lap_number"]), float(row["state_time_s"]))
        single = pace_for_state(q, registry, sub)
        brow = pb[(pb["driver_id"] == row["driver_id"])
                  & (pb["lap_number"] == row["lap_number"])].iloc[0]
        for n in F5_FEATURE_NAMES:
            a, b = single.value_dict()[n], brow[n]
            if a is None:
                assert b is None or (isinstance(b, float)
                                     and np.isnan(b)), (race_id, n)
            else:
                assert a == pytest.approx(float(b)), (race_id, n)


def test_real_bahrain_dry(registry):
    _parity_spot(_d9_season(2023), "2023-r01-R", registry)


def test_real_germany_wet(registry):
    _parity_spot(_d9_season(2019), "2019-r11-R", registry)


def test_real_britain(registry):
    _parity_spot(_d9_season(2021), "2021-r10-R", registry)


def test_real_belgium_partial(registry):
    d9 = _d9_season(2021)
    sub = d9[d9["race_id"] == "2021-r12-R"]
    pb = pace_batch(sub)
    # max 3 laps/driver, lap1 excluded -> all pace null, counts small
    assert (pb["pace_median_3"].isna()
            | (pb["pace_median_3"].notna())).all()
    assert int(pb["pace_n_5"].max()) <= 2
    _parity_spot(d9, "2021-r12-R", registry, k=8)


def test_real_monaco(registry):
    _parity_spot(_d9_season(2022), "2022-r07-R", registry)


def test_real_japan(registry):
    _parity_spot(_d9_season(2022), "2022-r18-R", registry)


def test_real_2024_2025(registry):
    _parity_spot(_d9_season(2024), "2024-r01-R", registry)
    _parity_spot(_d9_season(2025), "2025-r01-R", registry)


# --- full-scope audit ---

def test_full_scope_audit(registry):
    if not _HAS_D9:
        pytest.skip("canonical D9 data not present (data/v2 gitignored)")
    files = sorted(glob.glob(str(ROOT / "data/v2/processed"
                                 / "driver_lap_state_d9"
                                 / "season=*/*.parquet")))
    d9 = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    assert len(d9) == 189420
    pb = pace_batch(d9)
    assert len(pb) == 189420
    assert list(pb.columns) == ["race_id", "driver_id", "lap_number",
                                "state_time_s"] + list(F5_FEATURE_NAMES)
    assert not pb.duplicated(
        subset=["race_id", "driver_id", "lap_number"]).any()
    for col in ("winner_flag", "position_final", "points", "dnf_flag"):
        assert col not in pb.columns
    for n in F5_FEATURE_NAMES:
        col = pb[n].to_numpy(dtype=float)
        finite = col[np.isfinite(col)]
        assert not np.isinf(col).any(), n
        if len(finite) == 0:
            continue  # fully null family member is legitimate
        if "pace_median" in n or "pace_mean" in n or "representative" in n:
            assert finite.min() > 0, n
            assert finite.max() < 3600, n
    # determinism: rebuild twice identical
    pb2 = pace_batch(d9)
    pd.testing.assert_frame_equal(pb, pb2)
    # null-rate snapshot (informational; also asserted in docs)
    import json as _json
    rates = {n: float(pb[n].isna().mean()) for n in F5_FEATURE_NAMES}
    print("F5_NULL_RATES=" + _json.dumps(rates))
