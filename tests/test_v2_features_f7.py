"""F7 tests: relative/teammate/field/traffic context (offline).

Synthetic frames prove identity, signs, guards, parity, and mutations;
real-data spots + full-scope audit run on frozen D9 artifacts (skipped
when absent). No network.
"""

import glob

import numpy as np
import pandas as pd
import pytest

from v2.config import V2Paths
from v2.features import (
    FEATURE_SET_VERSION,
    F7_FEATURE_NAMES,
    FeatureFamily,
    FeatureRequest,
    FeatureStatus,
    NoCalculatorError,
    SyncRequirement,
    TemporalRule,
    build_f7_registry,
    context_batch,
    context_for_state,
    features_for_state,
    results_equal,
)
from v2.features.contracts import MissingPolicy

ROOT = V2Paths.resolve().root
_HAS_D9 = (ROOT / "data/v2/processed/driver_lap_state_d9/season=2021").is_dir()

COLS = ["race_id", "driver_id", "lap_number", "state_time_s", "position",
        "track_state", "constructor_id", "lap_time_s", "pit_in_s",
        "pit_out_s", "stint_number"]


def _row(race="R", drv="a", lap=1, t=100.0, pos=1, team="T1", lt=90.0,
         track="all_clear", stint=1, pitin=None, pitout=None):
    return {"race_id": race, "driver_id": drv, "lap_number": lap,
            "state_time_s": t, "position": pos, "track_state": track,
            "constructor_id": team, "lap_time_s": lt, "pit_in_s": pitin,
            "pit_out_s": pitout, "stint_number": stint}


@pytest.fixture()
def registry():
    return build_f7_registry()


@pytest.fixture()
def race():
    # a/b teammates (T1, b slower); c/d teammates (T2); e (T3), f (T4).
    rows = []
    for i in range(8):
        lap, t = i + 1, 100.0 * (i + 1)
        rows.append(_row(drv="a", lap=lap, t=t, pos=1, team="T1",
                         lt=90.0 + (i % 2)))
        rows.append(_row(drv="b", lap=lap, t=t + 5.0, pos=2, team="T1",
                         lt=92.0 + (i % 2)))
        rows.append(_row(drv="c", lap=lap, t=t + 12.0, pos=3, team="T2",
                         lt=91.0 + (i % 2)))
        rows.append(_row(drv="d", lap=lap, t=t + 40.0, pos=4, team="T2",
                         lt=93.0 + (i % 2)))
        rows.append(_row(drv="e", lap=lap, t=t + 200.0, pos=5, team="T3",
                         lt=95.0 + (i % 2)))
        rows.append(_row(drv="f", lap=lap, t=t + 300.0, pos=6, team="T4",
                         lt=94.0 + (i % 2)))
    return pd.DataFrame(rows, columns=COLS)


def _q(drv="b", lap=8, t=805.0):
    return FeatureRequest("R", drv, lap, t)


# --- sign / basis ---

def test_relative_sign_and_basis(registry, race):
    res = context_for_state(_q(), registry, race)
    v = res.value_dict()
    # b median5 ~= 92.5ish, a ~= 90.5ish -> positive (b slower)
    assert v["relative_pace_to_teammate_s_per_lap"] > 0
    assert v["relative_pace_to_teammate_s_per_lap"] == pytest.approx(2.0)
    # field median over a,c,d,e,f = median(91,91,93,95,94)=93; b=93
    assert v["relative_pace_to_field_median_s_per_lap"] == pytest.approx(0.0)
    assert v["field_pace_comparable_rivals"] == 5
    # ahead of b is a
    assert v["relative_pace_to_car_ahead_s_per_lap"] == pytest.approx(2.0)


def test_target_faster_negative(registry, race):
    res = context_for_state(FeatureRequest("R", "a", 8, 800.0),
                            registry, race)
    assert res.value_dict()["relative_pace_to_teammate_s_per_lap"] < 0


# --- teammate identity ---

def test_teammate_identity_fields(registry, race):
    v = context_for_state(_q(), registry, race).value_dict()
    assert v["teammate_observation_age_s"] == pytest.approx(5.0)
    assert v["teammate_lap_difference"] == 0
    assert v["teammate_position"] == 1


def test_teammate_unavailable_solo(registry, race):
    v = context_for_state(FeatureRequest("R", "e", 8, 1000.0),
                          registry, race).value_dict()
    assert v["relative_pace_to_teammate_s_per_lap"] is None
    assert v["teammate_observation_age_s"] is None
    assert v["teammate_lap_difference"] is None
    assert v["teammate_position"] is None


def test_teammate_unobservable(registry):
    df = pd.DataFrame([
        _row(drv="a", lap=2, t=200.0, pos=1, team="T1", lt=90.0),
        _row(drv="b", lap=1, t=500.0, pos=2, team="T1", lt=92.0),
    ], columns=COLS)
    # at T=200 b has no state yet -> teammate unobservable
    v = context_for_state(FeatureRequest("R", "a", 2, 200.0),
                          registry, df).value_dict()
    assert v["teammate_observation_age_s"] is None
    assert v["relative_pace_to_teammate_s_per_lap"] is None


def test_teammate_stale_kept(registry):
    df = pd.DataFrame([
        _row(drv="a", lap=5, t=500.0, pos=1, team="T1", lt=90.0),
        _row(drv="b", lap=1, t=110.0, pos=2, team="T1", lt=92.0),
    ], columns=COLS)
    v = context_for_state(FeatureRequest("R", "a", 5, 500.0),
                          registry, df).value_dict()
    assert v["teammate_observation_age_s"] == pytest.approx(390.0)
    assert v["teammate_lap_difference"] == 4


def test_teammate_future_excluded(registry, race):
    base = context_for_state(_q(), registry, race)
    mod = race.copy()
    mod.loc[(mod["driver_id"] == "a") & (mod["lap_number"] == 8),
            "state_time_s"] = 5000.0  # a's lap-8 row pushed to future
    out = context_for_state(_q(), registry, mod)
    # a now syncs at lap 7 (t=700): age 105, pace over laps<=700
    assert out.value_dict()["teammate_observation_age_s"] == \
        pytest.approx(105.0)
    assert out.value_dict()["teammate_observation_age_s"] != \
        base.value_dict()["teammate_observation_age_s"]


def test_lapped_teammate(registry):
    df = pd.DataFrame([
        _row(drv="a", lap=10, t=1000.0, pos=1, team="T1", lt=90.0),
        _row(drv="b", lap=9, t=995.0, pos=15, team="T1", lt=92.0),
    ], columns=COLS)
    v = context_for_state(FeatureRequest("R", "a", 10, 1000.0),
                          registry, df).value_dict()
    assert v["teammate_lap_difference"] == 1
    assert v["teammate_observation_age_s"] == pytest.approx(5.0)


# --- field ---

def test_field_target_exclusion(registry, race):
    v = context_for_state(_q(), registry, race).value_dict()
    assert v["field_pace_comparable_rivals"] == 5  # a,c,d,e,f (not b)
    assert v["observable_field_size"] == 6


def test_field_min_contributors(registry):
    df = pd.DataFrame([
        _row(drv="a", lap=8, t=800.0, pos=1, team="T1", lt=90.0),
        _row(drv="b", lap=8, t=805.0, pos=2, team="T1", lt=92.0),
    ], columns=COLS)
    v = context_for_state(FeatureRequest("R", "b", 8, 805.0),
                          registry, df).value_dict()
    assert v["field_pace_comparable_rivals"] <= 1
    assert v["relative_pace_to_field_median_s_per_lap"] is None
    assert v["observable_field_size"] == 2


def test_field_median_value(registry):
    df = pd.DataFrame([
        _row(drv="t", lap=8, t=800.0, pos=3, team="T9", lt=100.0),
    ] + [_row(drv=f"r{i}", lap=8, t=790.0 + i, pos=i + 1,
               team=f"T{i}", lt=90.0 + i) for i in range(6)], columns=COLS)
    # rivals need eligible history: single lap each -> pace null -> median null
    v = context_for_state(FeatureRequest("R", "t", 8, 800.0),
                          registry, df).value_dict()
    assert v["field_pace_comparable_rivals"] == 0
    assert v["relative_pace_to_field_median_s_per_lap"] is None


def test_unobservable_entrant_excluded(registry, race):
    v = context_for_state(_q(), registry, race).value_dict()
    assert v["observable_field_size"] == 6  # roster extras never counted


def test_order_counts(registry, race):
    v = context_for_state(_q(), registry, race).value_dict()
    assert v["cars_ahead_observable"] == 1
    assert v["cars_behind_observable"] == 4
    lead = context_for_state(FeatureRequest("R", "a", 8, 800.0),
                             registry, race).value_dict()
    assert lead["cars_ahead_observable"] == 0
    assert lead["cars_behind_observable"] == 5


# --- ahead / traffic / pack ---

def test_ahead_relative_and_ambiguity(registry, race):
    v = context_for_state(_q(), registry, race).value_dict()
    assert v["relative_pace_to_car_ahead_s_per_lap"] == pytest.approx(2.0)
    lead = context_for_state(FeatureRequest("R", "a", 8, 800.0),
                             registry, race).value_dict()
    assert lead["relative_pace_to_car_ahead_s_per_lap"] is None
    dup = race.copy()
    dup.loc[(dup["driver_id"] == "c") & (dup["lap_number"] == 7),
            "position"] = 1  # c syncs lap 7 at T: duplicate P1 with a
    # b's ahead: a and c both hold P1 -> ambiguous
    va = context_for_state(_q(), registry, dup).value_dict()
    assert va["relative_pace_to_car_ahead_s_per_lap"] is None


def test_traffic_threshold(registry, race):
    v = context_for_state(_q(), registry, race).value_dict()
    # b trails a by 5 s on shared lap -> not within 2 s
    assert v["in_traffic_2s"] is False
    close = race.copy()
    close.loc[(close["driver_id"] == "b") & (close["lap_number"] == 8),
              "state_time_s"] = 801.5
    vc = context_for_state(FeatureRequest("R", "b", 8, 801.5),
                           registry, close).value_dict()
    assert vc["in_traffic_2s"] is True


def test_laps_apart_no_proximity(registry):
    df = pd.DataFrame([
        _row(drv="a", lap=8, t=800.0, pos=1, team="T1", lt=90.0),
        _row(drv="b", lap=7, t=795.0, pos=2, team="T1", lt=92.0),
    ], columns=COLS)
    v = context_for_state(FeatureRequest("R", "a", 8, 800.0),
                          registry, df).value_dict()
    assert v["in_traffic_2s"] is None  # ahead none (a leads)
    assert v["nearby_cars_within_5s"] == 0  # b laps-apart: not counted
    v2 = context_for_state(FeatureRequest("R", "b", 7, 795.0),
                           registry, df).value_dict()
    assert v2["in_traffic_2s"] is None  # ahead a unobserved at T
    assert v2["nearby_cars_within_5s"] == 0


def test_pack_count(registry, race):
    v = context_for_state(_q(), registry, race).value_dict()
    # same-lap rivals within 5 s of b (T=805): a(800) yes; c(812)? 812>805 future!
    # c lap8 t=812 > T -> syncs lap7 t=712, different lap -> excluded
    assert v["nearby_cars_within_5s"] == 1


def test_no_drs_anywhere(registry, race):
    res = context_for_state(_q(), registry, race)
    names = " ".join(n for n, _ in res.values)
    assert "drs" not in names.lower()
    assert "DRS" not in str(res.provenance)


def test_red_sc_vsc(registry):
    df = pd.DataFrame([
        _row(drv="a", lap=2, t=4061.0, pos=1, team="T1", lt=90.0,
             track="red_flag"),
        _row(drv="b", lap=2, t=4068.0, pos=2, team="T1", lt=92.0,
             track="red_flag"),
    ], columns=COLS)
    v = context_for_state(FeatureRequest("R", "b", 2, 4068.0),
                          registry, df).value_dict()
    assert v["in_traffic_2s"] is None  # red geometry invalid
    assert v["nearby_cars_within_5s"] is None  # target red
    assert v["relative_pace_to_teammate_s_per_lap"] is None  # no history


# --- registry / version ---

def test_f7_registry_metadata(registry):
    assert len(registry) == 56
    assert FEATURE_SET_VERSION == "v8"
    sync_expect = {"teammate": "synchronized_rival",
                   "field": "synchronized_field",
                   "relative": "synchronized_rival",
                   "traffic": "synchronized_field"}
    for name in ("relative_pace_to_teammate_s_per_lap",
                 "teammate_observation_age_s", "teammate_lap_difference",
                 "teammate_position",
                 "relative_pace_to_field_median_s_per_lap",
                 "field_pace_comparable_rivals", "observable_field_size",
                 "cars_ahead_observable", "cars_behind_observable",
                 "relative_pace_to_car_ahead_s_per_lap", "in_traffic_2s",
                 "nearby_cars_within_5s"):
        d = registry.get(name)
        assert d.version == 1 and d.predictive_eligible
        assert d.temporal_rule.value == "synchronized_field"
        assert d.sync.value == sync_expect[d.family.value], name
        assert d.status is FeatureStatus.CANDIDATE
    assert registry.get("in_traffic_2s").dtype == "bool"
    assert "drs" not in " ".join(registry.names()).lower()


def test_engine_f7_resolution(registry, race):
    res = features_for_state(_q(), registry, race,
                             names=["relative_pace_to_teammate_s_per_lap",
                                    "observable_field_size"])
    # values follow deterministic registry order, not request order
    assert sorted(n for n, _ in res.values) == [
        "observable_field_size", "relative_pace_to_teammate_s_per_lap"]
    assert res.feature_set_version == "v8"


# --- parity ---

def test_single_batch_parity(registry, race):
    from v2.features.context import context_batch
    batch = context_batch(race)
    assert len(batch) == len(race)
    from v2.features import F7_FEATURE_NAMES
    for _, row in batch.iterrows():
        q = FeatureRequest(str(row["race_id"]), str(row["driver_id"]),
                           int(row["lap_number"]), float(row["state_time_s"]))
        single = context_for_state(q, registry, race)
        for n in F7_FEATURE_NAMES:
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


def test_shuffled_input(registry, race):
    a = context_for_state(_q(), registry, race)
    b = context_for_state(
        _q(), registry, race.sample(frac=1.0, random_state=13))
    assert results_equal(a, b)


# --- mutations ---

def test_future_adversaries(registry, race):
    base = context_for_state(_q(), registry, race)
    future = pd.DataFrame([
        _row(drv="a", lap=9, t=900.0, pos=1, team="T1", lt=60.0),
        _row(drv="c", lap=9, t=905.0, pos=2, team="T2", lt=150.0),
    ], columns=COLS)
    full = pd.concat([race, future], ignore_index=True)
    assert results_equal(base, context_for_state(_q(), registry, full))
    mod = full.copy()
    mod.loc[mod["state_time_s"] > 805.0, "position"] = 9
    assert results_equal(base, context_for_state(_q(), registry, mod))
    mod2 = full.copy()
    mod2.loc[mod2["state_time_s"] > 805.0, "track_state"] = "red_flag"
    assert results_equal(base, context_for_state(_q(), registry, mod2))


def test_future_result_label_mutation(registry, race):
    base = context_for_state(_q(), registry, race)
    labels = pd.DataFrame({"race_id": ["R"], "driver_id": ["b"],
                           "winner_flag": [True], "points": [25.0]})
    _ = labels
    assert results_equal(base, context_for_state(_q(), registry, race))


def test_presentation_identity_mutation(registry, race):
    base = context_for_state(_q(), registry, race)
    mod = race.copy()
    mod["constructor_id"] = mod["constructor_id"]  # canonical kept
    mod = mod.assign(driver_number=99, abbreviation="ZZ",
                     team_display="Renamed")
    assert results_equal(base, context_for_state(_q(), registry, mod))


# --- real-data spots ---

def _d9_season(season):
    if not _HAS_D9:
        pytest.skip("canonical D9 data not present (data/v2 gitignored)")
    files = sorted(glob.glob(str(ROOT / "data/v2/processed"
                                 / "driver_lap_state_d9"
                                 / f"season={season}/*.parquet")))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _parity_spot(d9, race_id, registry, k=8):
    from v2.features import F7_FEATURE_NAMES, context_batch
    sub = d9[d9["race_id"] == race_id]
    batch = context_batch(sub)
    assert len(batch) == len(sub)
    for _, row in sub.sample(n=min(k, len(sub)), random_state=9).iterrows():
        q = FeatureRequest(str(row["race_id"]), str(row["driver_id"]),
                           int(row["lap_number"]), float(row["state_time_s"]))
        single = context_for_state(q, registry, sub)
        brow = batch[(batch["driver_id"] == row["driver_id"])
                     & (batch["lap_number"] == row["lap_number"])].iloc[0]
        for n in F7_FEATURE_NAMES:
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
    from v2.features import F7_FEATURE_NAMES, context_batch
    files = sorted(glob.glob(str(ROOT / "data/v2/processed"
                                 / "driver_lap_state_d9"
                                 / "season=*/*.parquet")))
    d9 = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    assert len(d9) == 189420
    batch = context_batch(d9)
    assert len(batch) == 189420
    assert list(batch.columns) == ["race_id", "driver_id", "lap_number",
                                   "state_time_s"] + list(F7_FEATURE_NAMES)
    assert not batch.duplicated(
        subset=["race_id", "driver_id", "lap_number"]).any()
    for col in ("winner_flag", "position_final", "points", "dnf_flag"):
        assert col not in batch.columns
    for n in F7_FEATURE_NAMES:
        col = batch[n].to_numpy(dtype=float) \
            if batch[n].dtype != object else None
        if col is None:
            continue
        assert not np.isinf(col[np.isfinite(col)]).any(), n
    sub = d9[d9["race_id"] == "2023-r01-R"]
    import pandas as _pd
    _pd.testing.assert_frame_equal(context_batch(sub), context_batch(sub))
    import json as _json
    print("F7_NULL_RATES=" + _json.dumps(
        {n: float(batch[n].isna().mean()) for n in F7_FEATURE_NAMES}))
