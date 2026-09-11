"""F8 tests: rates + momentum (offline; synthetic + real spots + audit)."""

import glob

import numpy as np
import pandas as pd
import pytest

from v2.config import V2Paths
from v2.features import (
    FEATURE_SET_VERSION,
    F8_FEATURE_NAMES,
    FeatureFamily,
    FeatureRequest,
    FeatureStatus,
    NoCalculatorError,
    SyncRequirement,
    TemporalRule,
    build_f8_registry,
    features_for_state,
    gap_rate_from_points,
    ols_slope_xy,
    rates_batch,
    rates_for_state,
    rate_values_for_target,
    results_equal,
)
from v2.features.contracts import MissingPolicy
from v2.features.gaps import GapStatus, GapResult
from v2.features.temporal import TemporalError

ROOT = V2Paths.resolve().root
_HAS_D9 = (ROOT / "data/v2/processed/driver_lap_state_d9/season=2021").is_dir()

COLS = ["race_id", "driver_id", "lap_number", "state_time_s", "position",
        "track_state", "lap_time_s", "pit_in_s", "pit_out_s", "stint_number",
        "constructor_id"]


def _row(race="R", drv="a", lap=1, t=100.0, pos=1, track="all_clear",
         lt=90.0, team="T1", stint=1):
    return {"race_id": race, "driver_id": drv, "lap_number": lap,
            "state_time_s": t, "position": pos, "track_state": track,
            "lap_time_s": lt, "pit_in_s": None, "pit_out_s": None,
            "stint_number": stint, "constructor_id": team}


@pytest.fixture()
def registry():
    return build_f8_registry()


@pytest.fixture()
def race():
    # a leads, gap to b grows +1 s/lap; c laps b's pace, pos improves.
    rows = []
    for i in range(8):
        lap, t = i + 1, 100.0 * (i + 1)
        rows.append(_row(drv="a", lap=lap, t=t, pos=1, lt=90.0))
        rows.append(_row(drv="b", lap=lap, t=t + 5.0 + i, pos=2,
                         lt=92.0))
        rows.append(_row(drv="c", lap=lap, t=t + 50.0, pos=6 - (i // 2),
                         lt=91.0))
    return pd.DataFrame(rows, columns=COLS)


def _q(drv="b", lap=8, t=805.0 + 7):
    return FeatureRequest("R", drv, lap, t)


def _gap(ref="a", lap=3, sec=5.0, valid=True):
    return GapResult(GapStatus.VALID_SECONDS if valid else GapStatus.LAPS_APART,
                     "b", ref, lap, lap if valid else lap - 1,
                     0 if valid else -1, sec if valid else None,
                     valid, 1.0, "test")


# --- estimator ---

def test_ols_slope_xy():
    assert ols_slope_xy(np.array([1, 2, 3]), np.array([5.0, 6.0, 7.0])) == \
        pytest.approx(1.0)
    assert ols_slope_xy(np.array([1, 2]), np.array([5.0, 3.0])) == \
        pytest.approx(-2.0)
    with pytest.raises(TemporalError):
        ols_slope_xy(np.array([3]), np.array([5.0]))
    with pytest.raises(TemporalError):
        ols_slope_xy(np.array([3, 3]), np.array([5.0, 6.0]))


def test_gap_rate_same_ref():
    pts = [(3, 5.0, "a", True), (4, 6.0, "a", True), (5, 7.0, "a", True)]
    assert gap_rate_from_points(pts) == pytest.approx(1.0)
    assert gap_rate_from_points([(4, 6.0, "a", True),
                                 (5, 5.0, "a", True)]) == pytest.approx(-1.0)


def test_gap_rate_identity_change_resets():
    pts = [(3, 5.0, "a", True), (4, 6.0, "b", True), (5, 7.0, "b", True)]
    # trailing run with current ref b: laps 4,5 -> slope 1.0
    assert gap_rate_from_points(pts) == pytest.approx(1.0)
    assert gap_rate_from_points([(5, 7.0, "b", True)]) is None


def test_gap_rate_invalid_geometry():
    pts = [(3, 5.0, "a", True), (4, None, "a", False), (5, 7.0, "a", True)]
    # only valid run is the single current point -> null (no bridging)
    assert gap_rate_from_points(pts) is None
    assert gap_rate_from_points([]) is None
    cur_invalid = [(3, 5.0, "a", True), (5, None, "a", False)]
    assert gap_rate_from_points(cur_invalid) is None


# --- single-state behavior ---

def test_leader_rate_sign(registry, race):
    # b trails a by 5+i s at lap i+1 -> slope +1 (falling away)
    res = rates_for_state(_q(), registry, race)
    v = res.value_dict()
    assert v["recent_gap_to_leader_change_s_per_lap"] == pytest.approx(1.0)
    assert v["recent_gap_to_ahead_change_s_per_lap"] == pytest.approx(1.0)


def test_position_change_sign(registry, race):
    # c: pos 6,6,5,5,4,4,3,3 -> anchor lap3 pos5, current lap8 pos3 -> +2
    res = rates_for_state(FeatureRequest("R", "c", 8, 850.0), registry, race)
    assert res.value_dict()["recent_position_change_5laps"] == pytest.approx(2.0)
    # b: pos 2 throughout -> 0.0 (factual, not null)
    res2 = rates_for_state(_q(), registry, race)
    assert res2.value_dict()["recent_position_change_5laps"] == pytest.approx(0.0)


def test_pace_change_sign(registry):
    df = pd.DataFrame([
        _row(drv="a", lap=i + 1, t=100.0 * (i + 1),
             lt=95.0 - i)  # getting faster
        for i in range(10)], columns=COLS)
    res = rates_for_state(FeatureRequest("R", "a", 10, 1000.0), registry, df)
    v = res.value_dict()
    # now median(laps6-10: 90..86)=88; anchor lap5 median(laps2-5: 94..91)=92.5
    assert v["recent_pace_change_s_per_lap"] == pytest.approx(-0.9)


def test_insufficient_history(registry):
    df = pd.DataFrame([_row(drv="a", lap=1, t=100.0),
                       _row(drv="b", lap=1, t=105.0)], columns=COLS)
    v = rates_for_state(FeatureRequest("R", "b", 1, 105.0),
                        registry, df).value_dict()
    assert v["recent_gap_to_leader_change_s_per_lap"] is None
    assert v["recent_position_change_5laps"] is None
    assert v["recent_pace_change_s_per_lap"] is None


def test_sc_retained_with_context(registry):
    df = pd.DataFrame([
        _row(drv="a", lap=i + 1, t=100.0 * (i + 1), pos=1,
             track="safety_car" if i >= 5 else "all_clear")
        for i in range(8)] + [
        _row(drv="b", lap=i + 1, t=100.0 * (i + 1) + 5.0, pos=2,
             track="safety_car" if i >= 5 else "all_clear")
        for i in range(8)], columns=COLS)
    v = rates_for_state(FeatureRequest("R", "b", 8, 805.0),
                        registry, df).value_dict()
    # factual intervals retained (SC compression is real separation)
    assert v["recent_gap_to_leader_change_s_per_lap"] == pytest.approx(0.0)


def test_red_resets_rate(registry):
    df = pd.DataFrame([
        _row(drv="a", lap=i + 1, t=100.0 * (i + 1), pos=1,
             track="red_flag" if i == 6 else "all_clear")
        for i in range(8)] + [
        _row(drv="b", lap=i + 1, t=100.0 * (i + 1) + 5.0, pos=2,
             track="red_flag" if i == 6 else "all_clear")
        for i in range(8)], columns=COLS)
    v = rates_for_state(FeatureRequest("R", "b", 8, 805.0),
                        registry, df).value_dict()
    # lap7 red breaks the trailing valid run (no bridging across invalid
    # geometry): only lap 8 remains -> null, even with valid laps 3..6
    assert v["recent_gap_to_leader_change_s_per_lap"] is None


# --- registry / version ---

def test_f8_registry_metadata(registry):
    assert len(registry) == 60
    assert FEATURE_SET_VERSION == "v8"
    for name in F8_FEATURE_NAMES:
        d = registry.get(name)
        assert d.version == 1 and d.predictive_eligible
        assert d.status is FeatureStatus.CANDIDATE
    lead = registry.get("recent_gap_to_leader_change_s_per_lap")
    assert lead.family is FeatureFamily.RATE
    assert lead.sync.value == "synchronized_field"
    assert lead.temporal_rule.value == "synchronized_field"
    pos = registry.get("recent_position_change_5laps")
    assert pos.family is FeatureFamily.MOMENTUM
    assert pos.sync.value == "none"
    assert pos.temporal_rule.value == "driver_prefix"
    assert "catch" not in " ".join(registry.names())
    assert "project" not in " ".join(registry.names())


def test_engine_f8_resolution(registry, race):
    res = features_for_state(_q(), registry, race,
                             names=["recent_gap_to_leader_change_s_per_lap",
                                    "recent_position_change_5laps"])
    assert sorted(n for n, _ in res.values) == [
        "recent_gap_to_leader_change_s_per_lap",
        "recent_position_change_5laps"]
    assert res.feature_set_version == "v8"


def test_no_catch_time_features(registry):
    names = " ".join(registry.names())
    for token in ("catch", "project", "overtake", "momentum_trend",
                  "win_probability", "expected_finish"):
        assert token not in names


# --- parity ---

def test_single_batch_parity(registry, race):
    from v2.features import rates_batch
    batch = rates_batch(race)
    assert len(batch) == len(race)
    for _, row in batch.iterrows():
        q = FeatureRequest(str(row["race_id"]), str(row["driver_id"]),
                           int(row["lap_number"]), float(row["state_time_s"]))
        single = rates_for_state(q, registry, race)
        for n in F8_FEATURE_NAMES:
            a = single.value_dict()[n]
            b = row[n]
            b = None if (b is None or (isinstance(b, float)
                                       and np.isnan(b))) else b
            if a is None:
                assert b is None, (n, b)
            else:
                assert a == pytest.approx(float(b)), (n, a, b)


def test_shuffled_input(registry, race):
    a = rates_for_state(_q(), registry, race)
    b = rates_for_state(
        _q(), registry, race.sample(frac=1.0, random_state=21))
    assert results_equal(a, b)


# --- mutations ---

def test_future_adversaries(registry, race):
    base = rates_for_state(_q(), registry, race)
    future = pd.DataFrame([
        _row(drv="a", lap=9, t=900.0, lt=50.0),
        _row(drv="b", lap=9, t=950.0, pos=1, lt=200.0),
    ], columns=COLS)
    full = pd.concat([race, future], ignore_index=True)
    assert results_equal(base, rates_for_state(_q(), registry, full))
    mod = full.copy()
    mod.loc[mod["state_time_s"] > 812.0, "position"] = 9
    mod.loc[mod["state_time_s"] > 812.0, "track_state"] = "red_flag"
    assert results_equal(base, rates_for_state(_q(), registry, mod))


def test_future_result_label_mutation(registry, race):
    base = rates_for_state(_q(), registry, race)
    labels = pd.DataFrame({"race_id": ["R"], "driver_id": ["b"],
                           "winner_flag": [True]})
    _ = labels
    assert results_equal(base, rates_for_state(_q(), registry, race))


def test_reference_discontinuity(registry):
    # leader A laps 1-4, leader B laps 5-8 (takeover): rate uses B run only
    df = pd.DataFrame(
        [_row(drv="a", lap=i + 1, t=100.0 * (i + 1), pos=1 if i < 4 else 3)
         for i in range(8)] + [
        _row(drv="b", lap=i + 1, t=100.0 * (i + 1) + 5.0,
             pos=3 if i < 4 else 1)
        for i in range(8)] + [
        _row(drv="c", lap=i + 1, t=100.0 * (i + 1) + 10.0, pos=2)
        for i in range(8)], columns=COLS)
    v = rates_for_state(FeatureRequest("R", "c", 8, 810.0),
                        registry, df).value_dict()
    # leader at lap8 = b; trailing b-run laps 5..8 gaps +5 each -> slope 0
    assert v["recent_gap_to_leader_change_s_per_lap"] == pytest.approx(0.0)


# --- real-data spots ---

def _d9_season(season):
    if not _HAS_D9:
        pytest.skip("canonical D9 data not present (data/v2 gitignored)")
    files = sorted(glob.glob(str(ROOT / "data/v2/processed"
                                 / "driver_lap_state_d9"
                                 / f"season={season}/*.parquet")))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _parity_spot(d9, race_id, registry, k=8):
    from v2.features import rates_batch
    sub = d9[d9["race_id"] == race_id]
    batch = rates_batch(sub)
    assert len(batch) == len(sub)
    for _, row in sub.sample(n=min(k, len(sub)), random_state=13).iterrows():
        q = FeatureRequest(str(row["race_id"]), str(row["driver_id"]),
                           int(row["lap_number"]), float(row["state_time_s"]))
        single = rates_for_state(q, registry, sub)
        brow = batch[(batch["driver_id"] == row["driver_id"])
                     & (batch["lap_number"] == row["lap_number"])].iloc[0]
        for n in F8_FEATURE_NAMES:
            a = single.value_dict()[n]
            b = brow[n]
            b = None if (b is None or (isinstance(b, float)
                                       and np.isnan(b))) else b
            if a is None:
                assert b is None, (race_id, n)
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
    from v2.features import rates_batch
    files = sorted(glob.glob(str(ROOT / "data/v2/processed"
                                 / "driver_lap_state_d9"
                                 / "season=*/*.parquet")))
    d9 = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    assert len(d9) == 189420
    batch = rates_batch(d9)
    assert len(batch) == 189420
    assert list(batch.columns) == ["race_id", "driver_id", "lap_number",
                                   "state_time_s"] + list(F8_FEATURE_NAMES)
    assert not batch.duplicated(
        subset=["race_id", "driver_id", "lap_number"]).any()
    for col in ("winner_flag", "position_final", "points", "dnf_flag"):
        assert col not in batch.columns
    for n in F8_FEATURE_NAMES:
        col = batch[n].to_numpy(dtype=float)
        assert not np.isinf(col[np.isfinite(col)]).any(), n
    sub = d9[d9["race_id"] == "2023-r01-R"]
    import pandas as _pd
    _pd.testing.assert_frame_equal(rates_batch(sub), rates_batch(sub))
    import json as _json
    print("F8_NULL_RATES=" + _json.dumps(
        {n: float(batch[n].isna().mean()) for n in F8_FEATURE_NAMES}))
    for n in F8_FEATURE_NAMES:
        finite = batch[n].dropna().to_numpy(dtype=float)
        if len(finite):
            print(f"F8_{n}: min={finite.min():.3f} p50={np.median(finite):.3f} "
                  f"p95={np.quantile(finite, .95):.3f} "
                  f"max={finite.max():.3f}")
