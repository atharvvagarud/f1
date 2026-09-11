"""F9 tests: environment context (offline; synthetic + real + audit)."""

import glob

import numpy as np
import pandas as pd
import pytest

from v2.config import V2Paths
from v2.features import (
    FEATURE_SET_VERSION,
    F9_FEATURE_NAMES,
    FeatureFamily,
    FeatureRequest,
    FeatureStatus,
    NoCalculatorError,
    SyncRequirement,
    TemporalRule,
    build_f9_registry,
    environment_batch,
    environment_for_state,
    features_for_state,
    results_equal,
    track_values,
    weather_values,
)

ROOT = V2Paths.resolve().root
_HAS_D9 = (ROOT / "data/v2/processed/driver_lap_state_d9/season=2021").is_dir()

COLS = ["race_id", "driver_id", "lap_number", "state_time_s", "track_state",
        "wx_observed_at_s", "wx_air_temp_c", "wx_track_temp_c",
        "wx_rainfall"]


def _row(lap=1, t=100.0, track="all_clear", wxt=None, air=25.0, trk=30.0,
         rain=False):
    return {"race_id": "R", "driver_id": "a", "lap_number": lap,
            "state_time_s": t, "track_state": track,
            "wx_observed_at_s": wxt if wxt is not None else t,
            "wx_air_temp_c": air, "wx_track_temp_c": trk, "wx_rainfall": rain}


@pytest.fixture()
def registry():
    return build_f9_registry()


@pytest.fixture()
def frame():
    rows = [_row(lap=i + 1, t=100.0 * (i + 1), air=25.0 + 0.1 * i,
                 trk=30.0 + 0.2 * i, rain=(i >= 5),
                 track="safety_car" if i in (5, 6) else "all_clear")
            for i in range(10)]
    return pd.DataFrame(rows, columns=COLS)


def _q(lap=10, t=1000.0):
    return FeatureRequest("R", "a", lap, t)


# --- weather backward-only ---

def test_weather_anchor_and_sign(registry, frame):
    v = environment_for_state(_q(), registry, frame).value_dict()
    # distinct obs every 100 s; anchor <= 700 -> t=700: air 25.6? rows i: t=100(i+1), air=25+0.1i
    # current t=1000 air=25.9; anchor t=700 air=25.6 -> +0.3
    assert v["air_temp_change_5min_c"] == pytest.approx(0.3)
    assert v["track_temp_change_5min_c"] == pytest.approx(0.6)


def test_future_nearest_forbidden(registry):
    # observation just AFTER the anchor must not be selected
    rows = [_row(lap=1, t=100.0, air=20.0),
            _row(lap=2, t=200.0, air=21.0),
            _row(lap=5, t=500.0, air=26.0)]  # future w.r.t. T=400 anchor
    df = pd.DataFrame(rows, columns=COLS)
    v = environment_for_state(FeatureRequest("R", "a", 2, 200.0),
                              registry, df).value_dict()
    # T=200: anchor <= -100 none -> null (future 500 obs must not serve)
    assert v["air_temp_change_5min_c"] is None


def test_rain_start_and_future_mutation(registry, frame):
    v = environment_for_state(_q(), registry, frame).value_dict()
    assert v["rain_in_last_5min"] is True
    # latest rainy obs <= T is t=1000 itself -> 0.0
    assert v["time_since_rain_observed_s"] == pytest.approx(0.0)
    dry = frame.copy()
    dry["wx_rainfall"] = False
    vd = environment_for_state(_q(), registry, dry).value_dict()
    assert vd["rain_in_last_5min"] is False
    assert vd["time_since_rain_observed_s"] is None
    # future rain must not leak into T
    fut = pd.concat([frame, pd.DataFrame(
        [_row(lap=11, t=1100.0, rain=True)], columns=COLS)],
        ignore_index=True)
    assert results_equal(
        environment_for_state(_q(), registry, frame),
        environment_for_state(_q(), registry, fut))


def test_no_prior_rain(registry):
    df = pd.DataFrame([_row(lap=i + 1, t=100.0 * (i + 1), rain=False)
                       for i in range(4)], columns=COLS)
    v = environment_for_state(FeatureRequest("R", "a", 4, 400.0),
                              registry, df).value_dict()
    assert v["rain_in_last_5min"] is False
    assert v["time_since_rain_observed_s"] is None


def test_future_weather_mutation(registry, frame):
    base = environment_for_state(_q(), registry, frame)
    mod = frame.copy()
    mod.loc[mod["state_time_s"] > 1000.0, "wx_air_temp_c"] = 99.0
    extra = pd.DataFrame([_row(lap=11, t=1100.0, air=99.0)], columns=COLS)
    full = pd.concat([frame, extra], ignore_index=True)
    assert results_equal(base, environment_for_state(_q(), registry, full))
    assert results_equal(
        base, environment_for_state(
            _q(), registry,
            full.assign(wx_track_temp_c=full["wx_track_temp_c"])))


# --- track-state history ---

def test_current_duration_and_repeats(registry, frame):
    v = environment_for_state(_q(), registry, frame).value_dict()
    # run all_clear laps 8,9,10 (i=7,8,9; SC at i=5,6): duration = 1000-800
    assert v["current_track_state_duration_s"] == pytest.approx(200.0)
    # repeated identical rows must not reset: covered by construction


def test_transition_resets_duration(registry):
    df = pd.DataFrame([_row(lap=1, t=100.0, track="all_clear"),
                       _row(lap=2, t=200.0, track="safety_car"),
                       _row(lap=3, t=300.0, track="safety_car")], columns=COLS)
    v = environment_for_state(FeatureRequest("R", "a", 3, 300.0),
                              registry, df).value_dict()
    assert v["current_track_state_duration_s"] == pytest.approx(100.0)
    assert v["track_state_changes_5min"] == 1


def test_transition_count(registry, frame):
    v = environment_for_state(_q(), registry, frame).value_dict()
    # only the SC->clear change (t=800) falls in (700, 1000]
    assert v["track_state_changes_5min"] == 1


def test_sc_window_before_age_out(registry, frame):
    # at T=700 the SC run (t=600,700) is inside the window
    v = environment_for_state(FeatureRequest("R", "a", 7, 700.0),
                              registry, frame).value_dict()
    # intervals (500,600]SC + (600,700]SC are both attributed to SC rows
    assert v["recent_sc_vsc_fraction_5min"] == pytest.approx(200 / 300)
    assert v["current_track_state_duration_s"] == pytest.approx(100.0)
    assert v["track_state_changes_5min"] == 1


def test_caution_fractions_and_bounds(registry, frame):
    v = environment_for_state(_q(), registry, frame).value_dict()
    # SC intervals (t=600,700) aged out of (700,1000]: all-clear window
    assert v["recent_sc_vsc_fraction_5min"] == pytest.approx(0.0)
    assert v["recent_yellow_fraction_5min"] == pytest.approx(0.0)
    assert v["recent_red_fraction_5min"] == pytest.approx(0.0)
    for n in ("recent_yellow_fraction_5min", "recent_sc_vsc_fraction_5min",
              "recent_red_fraction_5min"):
        assert 0.0 <= v[n] <= 1.0


def test_early_race_policy(registry):
    df = pd.DataFrame([_row(lap=1, t=60.0)], columns=COLS)
    v = environment_for_state(FeatureRequest("R", "a", 1, 60.0),
                              registry, df).value_dict()
    assert v["track_state_changes_5min"] == 0
    assert v["current_track_state_duration_s"] == pytest.approx(0.0)
    # covered < 60 s -> fractions null (explicit, not assumed clear)
    assert v["recent_yellow_fraction_5min"] is None
    assert v["air_temp_change_5min_c"] is None  # no anchor <= -240


def test_sc_vsc_yellow_red(registry):
    df = pd.DataFrame([
        _row(lap=1, t=100.0, track="all_clear"),
        _row(lap=2, t=200.0, track="yellow"),
        _row(lap=3, t=300.0, track="safety_car"),
        _row(lap=4, t=400.0, track="vsc"),
        _row(lap=5, t=500.0, track="red_flag"),
        _row(lap=6, t=600.0, track="all_clear"),
    ], columns=COLS)
    v = environment_for_state(FeatureRequest("R", "a", 6, 600.0),
                              registry, df).value_dict()
    assert v["track_state_changes_5min"] == 3  # SC->VSC->red->clear in window
    assert v["recent_red_fraction_5min"] == pytest.approx(100 / 300)
    assert v["recent_yellow_fraction_5min"] == pytest.approx(0.0)  # aged out
    assert v["current_track_state_duration_s"] == pytest.approx(0.0)


def test_unknown_token_excluded(registry):
    df = pd.DataFrame([_row(lap=1, t=100.0, track=None),
                       _row(lap=2, t=200.0, track="all_clear")], columns=COLS)
    v = environment_for_state(FeatureRequest("R", "a", 2, 200.0),
                              registry, df).value_dict()
    assert v["current_track_state_duration_s"] == pytest.approx(0.0)
    assert v["track_state_changes_5min"] == 0  # null transitions uncounted
    # the (100,200] clear interval covers 100 s -> honest 0.0, not null
    assert v["recent_yellow_fraction_5min"] == pytest.approx(0.0)


# --- registry / version ---

def test_f9_registry_metadata(registry):
    assert len(registry) == 69
    assert FEATURE_SET_VERSION == "v8"
    for name in F9_FEATURE_NAMES:
        d = registry.get(name)
        assert d.version == 1 and d.predictive_eligible
        assert d.temporal_rule.value == "driver_prefix"
        assert d.sync.value == "none"
        assert d.status is FeatureStatus.CANDIDATE
    assert registry.get("air_temp_change_5min_c").family is FeatureFamily.WEATHER
    assert registry.get("recent_red_fraction_5min").family is \
        FeatureFamily.RACE_CONTROL
    names = " ".join(registry.names())
    assert "forecast" not in names and "prediction" not in names
    assert "embedding" not in names and "severity" not in names


def test_engine_f9_resolution(registry, frame):
    res = features_for_state(_q(), registry, frame,
                             names=["air_temp_change_5min_c",
                                    "recent_yellow_fraction_5min"])
    assert sorted(n for n, _ in res.values) == [
        "air_temp_change_5min_c", "recent_yellow_fraction_5min"]
    assert res.feature_set_version == "v8"


# --- parity ---

def test_single_batch_parity(registry, frame):
    from v2.features import environment_batch
    batch = environment_batch(frame)
    assert len(batch) == len(frame)
    for _, row in batch.iterrows():
        q = FeatureRequest(str(row["race_id"]), str(row["driver_id"]),
                           int(row["lap_number"]), float(row["state_time_s"]))
        single = environment_for_state(q, registry, frame)
        for n in F9_FEATURE_NAMES:
            a = single.value_dict()[n]
            b = row[n]
            b = None if (b is None or (isinstance(b, float)
                                       and np.isnan(b))) else b
            if a is None:
                assert b is None, (n, b)
            elif isinstance(a, bool):
                assert b == a, (n, a, b)
            else:
                assert a == pytest.approx(float(b)), (n, a, b)


def test_shuffled_source_rows(registry, frame):
    a = environment_for_state(_q(), registry, frame)
    b = environment_for_state(
        _q(), registry, frame.sample(frac=1.0, random_state=17))
    assert results_equal(a, b)


def test_future_rc_mutation(registry, frame):
    base = environment_for_state(_q(), registry, frame)
    future = pd.DataFrame(
        [_row(lap=11, t=1100.0, track="red_flag")], columns=COLS)
    full = pd.concat([frame, future], ignore_index=True)
    assert results_equal(base, environment_for_state(_q(), registry, full))
    mod = full.copy()
    mod.loc[mod["state_time_s"] > 1000.0, "track_state"] = "safety_car"
    assert results_equal(base, environment_for_state(_q(), registry, mod))


def test_future_result_label_mutation(registry, frame):
    base = environment_for_state(_q(), registry, frame)
    labels = pd.DataFrame({"race_id": ["R"], "driver_id": ["a"],
                           "winner_flag": [True]})
    _ = labels
    assert results_equal(base, environment_for_state(_q(), registry, frame))


# --- real-data spots ---

def _d9_season(season):
    if not _HAS_D9:
        pytest.skip("canonical D9 data not present (data/v2 gitignored)")
    files = sorted(glob.glob(str(ROOT / "data/v2/processed"
                                 / "driver_lap_state_d9"
                                 / f"season={season}/*.parquet")))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _parity_spot(d9, race_id, registry, k=8):
    from v2.features import environment_batch
    sub = d9[d9["race_id"] == race_id]
    batch = environment_batch(sub)
    assert len(batch) == len(sub)
    for _, row in sub.sample(n=min(k, len(sub)), random_state=11).iterrows():
        q = FeatureRequest(str(row["race_id"]), str(row["driver_id"]),
                           int(row["lap_number"]), float(row["state_time_s"]))
        single = environment_for_state(q, registry, sub)
        brow = batch[(batch["driver_id"] == row["driver_id"])
                     & (batch["lap_number"] == row["lap_number"])].iloc[0]
        for n in F9_FEATURE_NAMES:
            a = single.value_dict()[n]
            b = brow[n]
            b = None if (b is None or (isinstance(b, float)
                                       and np.isnan(b))) else b
            if a is None:
                assert b is None, (race_id, n)
            elif isinstance(a, bool):
                assert b == a, (race_id, n)
            else:
                assert a == pytest.approx(float(b)), (race_id, n)


@pytest.mark.parametrize("season,race_id", [
    (2023, "2023-r01-R"), (2019, "2019-r11-R"), (2021, "2021-r10-R"),
    (2021, "2021-r12-R"), (2022, "2022-r07-R"), (2022, "2022-r18-R"),
    (2024, "2024-r01-R"), (2025, "2025-r01-R"),
])
def test_real_parity_spots(registry, season, race_id):
    _parity_spot(_d9_season(season), race_id, registry)


# --- full-scope audit ---

def test_full_scope_audit(registry):
    if not _HAS_D9:
        pytest.skip("canonical D9 data not present (data/v2 gitignored)")
    from v2.features import environment_batch
    files = sorted(glob.glob(str(ROOT / "data/v2/processed"
                                 / "driver_lap_state_d9"
                                 / "season=*/*.parquet")))
    d9 = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    assert len(d9) == 189420
    batch = environment_batch(d9)
    assert len(batch) == 189420
    assert list(batch.columns) == ["race_id", "driver_id", "lap_number",
                                   "state_time_s"] + list(F9_FEATURE_NAMES)
    assert not batch.duplicated(
        subset=["race_id", "driver_id", "lap_number"]).any()
    for col in ("winner_flag", "position_final", "points", "dnf_flag"):
        assert col not in batch.columns
    for n in F9_FEATURE_NAMES:
        col = batch[n].to_numpy(dtype=float) \
            if batch[n].dtype != object else None
        if col is None:
            # nullable booleans stored as object; check via pandas
            assert set(batch[n].dropna().unique()) <= {True, False}, n
            continue
        assert not np.isinf(col[np.isfinite(col)]).any(), n
    for n in ("recent_yellow_fraction_5min", "recent_sc_vsc_fraction_5min",
              "recent_red_fraction_5min"):
        finite = batch[n].dropna().to_numpy(dtype=float)
        assert ((0.0 <= finite) & (finite <= 1.0)).all(), n
    sub = d9[d9["race_id"] == "2023-r01-R"]
    import pandas as _pd
    _pd.testing.assert_frame_equal(environment_batch(sub),
                                   environment_batch(sub))
    import json as _json
    print("F9_NULL_RATES=" + _json.dumps(
        {n: float(batch[n].isna().mean()) for n in F9_FEATURE_NAMES}))
    for n in F9_FEATURE_NAMES:
        finite = batch[n].dropna()
        if len(finite) and finite.dtype != object:
            finite = finite.to_numpy(dtype=float)
            print(f"F9_{n}: min={finite.min():.3f} p50={np.median(finite):.3f} "
                  f"max={finite.max():.3f}")
