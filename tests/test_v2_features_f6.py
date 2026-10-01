"""F6 tests: gap engine semantics, validity, mutations, parity,
registry, real-data spots, full-scope audit. Offline.
"""

import glob

import numpy as np
import pandas as pd
import pytest

from raceintel.config import V2Paths
from raceintel.features import (
    FEATURE_SET_VERSION,
    GAP_FEATURE_NAMES,
    FeatureFamily,
    FeatureRequest,
    FeatureStatus,
    GapStatus,
    NoCalculatorError,
    SyncRequirement,
    TemporalRule,
    build_f6_registry,
    features_for_state,
    gap_batch,
    gap_for_state,
    gaps_for_snapshot,
    results_equal,
)
from raceintel.features.contracts import MissingPolicy
from raceintel.features.temporal import TargetNotFoundError, synchronized_field_snapshot

ROOT = V2Paths.resolve().root
_HAS_D9 = (ROOT / "data/v2/processed/driver_lap_state_d9/season=2021").is_dir()

COLS = ["race_id", "driver_id", "lap_number", "state_time_s", "position",
        "track_state"]


def _row(race="R", drv="a", lap=1, t=100.0, pos=1, track="all_clear"):
    return {"race_id": race, "driver_id": drv, "lap_number": lap,
            "state_time_s": t, "position": pos, "track_state": track}


@pytest.fixture()
def registry():
    return build_f6_registry()


@pytest.fixture()
def race():
    # a leads throughout; b trails by 5 s; c a lap down from lap 3.
    return pd.DataFrame([
        _row(drv="a", lap=1, t=100.0, pos=1),
        _row(drv="b", lap=1, t=105.0, pos=2),
        _row(drv="c", lap=1, t=108.0, pos=3),
        _row(drv="a", lap=2, t=200.0, pos=1),
        _row(drv="b", lap=2, t=205.0, pos=2),
        _row(drv="c", lap=2, t=290.0, pos=3),
        _row(drv="a", lap=3, t=300.0, pos=1),
        _row(drv="b", lap=3, t=305.0, pos=2),
    ], columns=COLS)


def _q(drv="b", lap=2, t=205.0):
    return FeatureRequest("R", drv, lap, t)


# --- leader identity / zero gap ---

def test_leader_valid_zero_gap(registry, race):
    res = gap_for_state(FeatureRequest("R", "a", 2, 200.0), registry, race)
    v = res.value_dict()
    assert v["gap_to_leader_laps"] == 0
    assert v["gap_to_leader_seconds"] == pytest.approx(0.0)
    assert v["gap_to_leader_seconds_valid"] is True
    assert v["leader_observation_age_s"] == pytest.approx(0.0)


def test_same_lap_valid_seconds(registry, race):
    res = gap_for_state(_q(), registry, race)
    v = res.value_dict()
    assert v["gap_to_leader_laps"] == 0
    assert v["gap_to_leader_seconds"] == pytest.approx(5.0)  # 205-200
    assert v["gap_to_leader_seconds_valid"] is True
    assert v["leader_observation_age_s"] == pytest.approx(5.0)
    # car ahead of b is a (unique P1)
    assert v["gap_to_ahead_seconds"] == pytest.approx(5.0)
    assert v["gap_to_ahead_seconds_valid"] is True
    assert v["ahead_observation_age_s"] == pytest.approx(5.0)


def test_sign_convention_positive_means_trailing(registry, race):
    # c lap 2 (t=290) vs leader a lap 3 (t=300)? a lap3 after T -> sync a lap2 (200)
    res = gap_for_state(FeatureRequest("R", "c", 2, 290.0), registry, race)
    v = res.value_dict()
    assert v["gap_to_leader_laps"] == 0
    assert v["gap_to_leader_seconds"] == pytest.approx(90.0)
    assert v["gap_to_leader_seconds"] >= 0


def test_laps_apart_no_seconds(registry):
    df = pd.DataFrame([
        _row(drv="a", lap=5, t=500.0, pos=1),
        _row(drv="b", lap=4, t=490.0, pos=2),
    ], columns=COLS)
    res = gap_for_state(FeatureRequest("R", "b", 4, 490.0), registry, df)
    v = res.value_dict()
    # a's only row (lap 5, t=500) is after T=490 -> leader unobserved
    assert v["gap_to_leader_laps"] is None
    assert v["gap_to_leader_seconds"] is None
    assert v["gap_to_leader_seconds_valid"] is None
    assert v["leader_observation_age_s"] is None


def test_age_vs_gap_differ(registry):
    # laps-apart with large age: age is provenance, gap is null.
    df = pd.DataFrame([
        _row(drv="a", lap=3, t=300.0, pos=1),
        _row(drv="b", lap=2, t=490.0, pos=2),
    ], columns=COLS)
    res = gap_for_state(FeatureRequest("R", "b", 2, 490.0), registry, df)
    v = res.value_dict()
    assert v["gap_to_leader_laps"] == -1
    assert v["gap_to_leader_seconds"] is None
    assert v["leader_observation_age_s"] == pytest.approx(190.0)
    assert v["leader_observation_age_s"] != v["gap_to_leader_seconds"]


def test_unobserved_reference(registry, race):
    res = gap_for_state(FeatureRequest("R", "a", 1, 100.0), registry, race)
    v = res.value_dict()
    # leader is a itself (unique P1 at lap 1 among observable {a})
    assert v["gap_to_leader_seconds"] == pytest.approx(0.0)
    # b/c unobserved at T=100 -> ahead: a leads -> NO_CAR_AHEAD
    assert v["gap_to_ahead_seconds"] is None
    assert v["gap_to_ahead_laps"] is None


def test_stale_reference_kept_not_retired(registry):
    df = pd.DataFrame([
        _row(drv="a", lap=1, t=100.0, pos=1),
        _row(drv="a", lap=2, t=200.0, pos=1),
        _row(drv="b", lap=1, t=110.0, pos=2),
    ], columns=COLS)
    res = gap_for_state(FeatureRequest("R", "a", 2, 200.0), registry, df)
    v = res.value_dict()
    # b stale (90 s) but observable; a is leader -> ahead none
    assert v["gap_to_ahead_seconds"] is None
    assert v["gap_to_ahead_laps"] is None
    res2 = gap_for_state(FeatureRequest("R", "b", 1, 110.0), registry, df)
    v2 = res2.value_dict()
    assert v2["gap_to_leader_seconds"] == pytest.approx(10.0)


def test_missing_timing_null():
    df = pd.DataFrame([
        _row(drv="a", lap=1, t=100.0, pos=1),
        _row(drv="b", lap=1, t=110.0, pos=2),
    ], columns=COLS)
    df.loc[df["driver_id"] == "a", "state_time_s"] = np.nan
    snap = synchronized_field_snapshot(df, "R", "b", 1, 110.0, ["a", "b"])
    entries = dict(snap.entries)
    assert entries["a"].observable is False
    lg, _ = gaps_for_snapshot(df[(df["driver_id"] == "b")].iloc[0], entries)
    assert lg.status == GapStatus.REFERENCE_UNOBSERVED


def test_red_flag_invalid(registry):
    df = pd.DataFrame([
        _row(drv="a", lap=2, t=4061.0, pos=1, track="red_flag"),
        _row(drv="b", lap=2, t=4068.0, pos=2, track="red_flag"),
    ], columns=COLS)
    res = gap_for_state(FeatureRequest("R", "b", 2, 4068.0), registry, df)
    v = res.value_dict()
    assert v["gap_to_leader_laps"] == 0
    assert v["gap_to_leader_seconds"] is None
    assert v["gap_to_leader_seconds_valid"] is False
    assert v["leader_observation_age_s"] == pytest.approx(7.0)


def test_sc_vsc_retained(registry):
    df = pd.DataFrame([
        _row(drv="a", lap=2, t=800.0, pos=1, track="safety_car"),
        _row(drv="b", lap=2, t=835.0, pos=2, track="safety_car"),
        _row(drv="a", lap=3, t=9341.0, pos=1, track="vsc"),
        _row(drv="b", lap=3, t=9343.0, pos=2, track="vsc"),
    ], columns=COLS)
    sc = gap_for_state(FeatureRequest("R", "b", 2, 835.0), registry, df)
    assert sc.value_dict()["gap_to_leader_seconds"] == pytest.approx(35.0)
    vsc = gap_for_state(FeatureRequest("R", "b", 3, 9343.0), registry, df)
    assert vsc.value_dict()["gap_to_leader_seconds"] == pytest.approx(2.0)


def test_pit_target_and_reference(registry):
    # reference pitted on the shared lap: interval includes pit time factually
    df = pd.DataFrame([
        _row(drv="a", lap=2, t=230.0, pos=2),  # slow lap-2 (pitted)
        _row(drv="b", lap=2, t=205.0, pos=1),
    ], columns=COLS)
    res = gap_for_state(FeatureRequest("R", "b", 2, 205.0), registry, df)
    v = res.value_dict()
    # b is leader (unique P1 among observable {b} at T=205; a unobserved)
    assert v["gap_to_leader_seconds"] == pytest.approx(0.0)
    res2 = gap_for_state(FeatureRequest("R", "a", 2, 230.0), registry, df)
    v2 = res2.value_dict()
    assert v2["gap_to_leader_seconds"] == pytest.approx(25.0)  # factual


def test_ahead_ambiguity_null(registry):
    df = pd.DataFrame([
        _row(drv="a", lap=2, t=200.0, pos=2),
        _row(drv="b", lap=2, t=201.0, pos=2),  # duplicate position
        _row(drv="c", lap=2, t=205.0, pos=3),
    ], columns=COLS)
    res = gap_for_state(FeatureRequest("R", "c", 2, 205.0), registry, df)
    v = res.value_dict()
    assert v["gap_to_ahead_seconds"] is None
    assert v["gap_to_ahead_laps"] is None


def test_leader_fallback_maxlap(registry):
    # two P1 holders (pit-cycle skew) -> max-lap earliest fallback
    df = pd.DataFrame([
        _row(drv="a", lap=5, t=500.0, pos=1),
        _row(drv="b", lap=5, t=505.0, pos=1),
        _row(drv="c", lap=4, t=510.0, pos=3),
    ], columns=COLS)
    res = gap_for_state(FeatureRequest("R", "c", 4, 510.0), registry, df)
    v = res.value_dict()
    assert v["gap_to_leader_laps"] == -1  # both refs on lap 5
    assert v["gap_to_leader_seconds"] is None


# --- future-crossing leakage ---

def test_future_rival_crossing_unavailable(registry, race):
    base = gap_for_state(_q(), registry, race)
    # rival future lap-2 crossing AFTER T must not create/change seconds
    mod = race.copy()
    mod.loc[(mod["driver_id"] == "a") & (mod["lap_number"] == 2),
            "state_time_s"] = 204.0  # still <= T: changes value (correct)
    changed = gap_for_state(_q(), registry, mod)
    assert changed.value_dict()["gap_to_leader_seconds"] == pytest.approx(1.0)
    mod2 = race.copy()
    extra = pd.DataFrame([_row(drv="a", lap=3, t=290.0, pos=1)], columns=COLS)
    full = pd.concat([mod2, extra], ignore_index=True)
    assert results_equal(
        base, gap_for_state(_q(), registry, full))


def test_future_mutations_invariant(registry, race):
    base = gap_for_state(_q(), registry, race)
    future = pd.DataFrame([
        _row(drv="a", lap=4, t=400.0, pos=1),
        _row(drv="b", lap=4, t=405.0, pos=1),
    ], columns=COLS)
    full = pd.concat([race, future], ignore_index=True)
    assert results_equal(base, gap_for_state(_q(), registry, full))
    mod = full.copy()
    mod.loc[mod["state_time_s"] > 205.0, "position"] = 5
    assert results_equal(base, gap_for_state(_q(), registry, mod))
    sh = full.sample(frac=1.0, random_state=4)
    assert results_equal(base, gap_for_state(_q(), registry, sh))


def test_identifier_mutation_invisible(registry, race):
    base = gap_for_state(_q(), registry, race)
    mod = race.copy()
    mod["position"] = mod["position"]  # positions are data, keep
    # presentation identifiers live outside gap inputs; emulate via extra cols
    mod = mod.assign(driver_number=[44, 44, 44, 1, 1, 1, 2, 2],
                     team=["M", "M", "M", "R", "R", "R", "F", "F"])
    assert results_equal(base, gap_for_state(_q(), registry, mod))


# --- registry / version ---

def test_gap_registry_metadata(registry):
    assert len(registry) == 44
    assert FEATURE_SET_VERSION == "v8"
    for name in GAP_FEATURE_NAMES:
        d = registry.get(name)
        assert d.family is FeatureFamily.GAP
        assert d.version == 1
        assert d.sync.value == "synchronized_field"
        assert d.temporal_rule.value == "synchronized_field"
        assert d.predictive_eligible
        assert d.status is FeatureStatus.CANDIDATE
        assert "driver_lap_state_d9.state_time_s" in d.sources


def test_engine_gap_resolution(registry, race):
    res = features_for_state(_q(), registry, race,
                             names=list(GAP_FEATURE_NAMES))
    assert len(res.values) == 8
    assert res.feature_set_version == "v8"
    only = features_for_state(_q(), registry, race,
                              names=["gap_to_leader_seconds"])
    assert [n for n, _ in only.values] == ["gap_to_leader_seconds"]
    with pytest.raises(NoCalculatorError):
        features_for_state(_q(), registry, race, names=["grid_position"])


# --- parity ---

def test_single_batch_parity(registry, race):
    from raceintel.features.gaps import gap_batch
    batch = gap_batch(race)
    assert len(batch) == len(race)
    for _, row in batch.iterrows():
        q = FeatureRequest(str(row["race_id"]), str(row["driver_id"]),
                           int(row["lap_number"]), float(row["state_time_s"]))
        single = gap_for_state(q, registry, race)
        for n in GAP_FEATURE_NAMES:
            a = single.value_dict()[n]
            b = row[n]
            b = None if (b is None or (isinstance(b, float)
                                       and np.isnan(b))
                         or (isinstance(b, float) and pd.isna(b))) else b
            if a is None:
                assert b is None, (n, b)
            elif isinstance(a, bool):
                assert b == a, (n, a, b)
            else:
                assert a == pytest.approx(float(b)), (n, a, b)


# --- real-data spots ---

def _d9_season(season):
    if not _HAS_D9:
        pytest.skip("canonical D9 data not present (data/v2 gitignored)")
    files = sorted(glob.glob(str(ROOT / "data/v2/processed"
                                 / "driver_lap_state_d9"
                                 / f"season={season}/*.parquet")))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _parity_spot(d9, race_id, registry, k=10):
    from raceintel.features.gaps import gap_batch
    sub = d9[d9["race_id"] == race_id]
    batch = gap_batch(sub)
    assert len(batch) == len(sub)
    for _, row in sub.sample(n=min(k, len(sub)), random_state=5).iterrows():
        q = FeatureRequest(str(row["race_id"]), str(row["driver_id"]),
                           int(row["lap_number"]), float(row["state_time_s"]))
        single = gap_for_state(q, registry, sub)
        brow = batch[(batch["driver_id"] == row["driver_id"])
                     & (batch["lap_number"] == row["lap_number"])].iloc[0]
        for n in GAP_FEATURE_NAMES:
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


def test_real_belgium_validity_mix(registry):
    d9 = _d9_season(2021)
    from raceintel.features.gaps import gap_batch
    batch = gap_batch(d9[d9["race_id"] == "2021-r12-R"])
    assert len(batch) == 60
    # short race: leader gaps computable (same 3-lap window), ahead valid
    assert batch["gap_to_leader_seconds"].notna().any()


# --- full-scope audit ---

def test_full_scope_audit(registry):
    if not _HAS_D9:
        pytest.skip("canonical D9 data not present (data/v2 gitignored)")
    from raceintel.features.gaps import gap_batch
    files = sorted(glob.glob(str(ROOT / "data/v2/processed"
                                 / "driver_lap_state_d9"
                                 / "season=*/*.parquet")))
    d9 = pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)
    assert len(d9) == 189420
    batch = gap_batch(d9)
    assert len(batch) == 189420
    assert list(batch.columns) == ["race_id", "driver_id", "lap_number",
                                   "state_time_s"] + list(GAP_FEATURE_NAMES)
    assert not batch.duplicated(
        subset=["race_id", "driver_id", "lap_number"]).any()
    for col in ("winner_flag", "position_final", "points", "dnf_flag"):
        assert col not in batch.columns
    secs = batch["gap_to_leader_seconds"].to_numpy(dtype=float)
    finite = secs[np.isfinite(secs)]
    assert (finite >= 0).all()
    assert not np.isinf(secs).any()
    assert (finite < 3600).all()
    laps = batch["gap_to_leader_laps"].dropna().to_numpy(dtype=float)
    # distribution reported (positive = target completed more than the
    # identified leader: rare pit/retirement transients, never clipped)
    print("LEADER_LAPDIFF_POS_SHARE=" + str(float((laps > 0).mean())))
    # determinism: race-level rebuild identical (full double-build would
    # double suite time; the full single build above is the audit)
    sub = d9[d9["race_id"] == "2023-r01-R"]
    pd.testing.assert_frame_equal(gap_batch(sub), gap_batch(sub))
    import json as _json
    print("GAP_NULL_RATES=" + _json.dumps(
        {n: float(batch[n].isna().mean()) for n in GAP_FEATURE_NAMES}))
    print("LEADER_VALID_SHARE=" + str(float(
        (batch["gap_to_leader_seconds_valid"] == True).mean())))
