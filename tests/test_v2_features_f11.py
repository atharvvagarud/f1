"""F11 tests: domain-justified interactions (offline)."""

import glob

import numpy as np
import pandas as pd
import pytest

from raceintel.config import V2Paths
from raceintel.features import (
    FEATURE_SET_VERSION,
    INTERACTION_NAMES,
    FeatureFamily,
    FeatureRequest,
    FeatureStatus,
    NoCalculatorError,
    SyncRequirement,
    TemporalRule,
    build_f11_registry,
    conditional_on_traffic,
    features_for_state,
    interaction_values,
    interactions_batch,
    interactions_for_state,
    positions_from_grid_value,
    results_equal,
)

ROOT = V2Paths.resolve().root
_HAS_D9 = (ROOT / "data/v2/processed/driver_lap_state_d9/season=2021").is_dir()


@pytest.fixture()
def registry():
    return build_f11_registry()


# --- selection guards ---

def test_no_automatic_generation():
    import raceintel.features.interactions as ix
    src = open(ix.__file__).read()
    assert "PolynomialFeatures" not in src
    assert "sklearn" not in src
    assert "itertools" not in src or "combinations" not in src
    assert len(INTERACTION_NAMES) == 3


def test_no_projection_or_scores(registry):
    names = " ".join(registry.names())
    for token in ("catch", "project", "overtake", "attack",
                  "pressure_score", "racecraft", "strategy_quality",
                  "polynomial", "degradation", "clean_air", "win_probability",
                  "expected_finish"):
        assert token not in names, token


def test_trend_x_stint_rejected(registry):
    assert "stint_pace_change_implied" not in registry.names()
    assert "tyre_age_x_trend" not in registry.names()
    assert "trend_x_stint" not in registry.names()
    assert len(registry) == 84  # 81 + exactly 3 retained


# --- positions_from_grid ---

def test_positions_from_grid_sign():
    assert positions_from_grid_value(5, 3) == 2   # gained
    assert positions_from_grid_value(3, 5) == -2  # lost
    assert positions_from_grid_value(1, 1) == 0
    assert positions_from_grid_value(0, 5) is None  # pit-lane code
    assert positions_from_grid_value(None, 5) is None
    assert positions_from_grid_value(5, None) is None


# --- traffic conditional tri-state ---

def test_conditional_traffic_tristate():
    assert conditional_on_traffic(0.5, True) == 0.5
    assert conditional_on_traffic(0.0, True) == 0.0  # legit zero preserved
    assert conditional_on_traffic(0.5, False) is None
    assert conditional_on_traffic(0.5, None) is None  # Unknown != False
    assert conditional_on_traffic(None, True) is None


# --- missingness propagation ---

def test_missingness_never_broadens():
    assert interaction_values({
        "grid_position": None, "position": 3,
        "relative_pace_to_car_ahead_s_per_lap": 0.5,
        "in_traffic_2s": True,
        "recent_gap_to_ahead_change_s_per_lap": 0.1,
    })["positions_from_grid"] is None
    assert interaction_values({
        "grid_position": 5, "position": 3,
        "relative_pace_to_car_ahead_s_per_lap": None,
        "in_traffic_2s": True,
        "recent_gap_to_ahead_change_s_per_lap": 0.1,
    })["relative_pace_to_ahead_in_traffic_s_per_lap"] is None
    full = interaction_values({
        "grid_position": 5, "position": 3,
        "relative_pace_to_car_ahead_s_per_lap": 0.5,
        "in_traffic_2s": True,
        "recent_gap_to_ahead_change_s_per_lap": -0.2,
    })
    assert full == {"positions_from_grid": 2,
                    "relative_pace_to_ahead_in_traffic_s_per_lap": 0.5,
                    "recent_gap_to_ahead_change_in_traffic_s_per_lap": -0.2}


# --- metadata inheritance ---

def test_metadata_inheritance(registry):
    pfg = registry.get("positions_from_grid")
    assert pfg.family is FeatureFamily.INTERACTION
    assert pfg.temporal_rule.value == "target_state"
    assert pfg.sync.value == "none"
    assert pfg.dtype == "int64" and pfg.unit == "positions"
    rel = registry.get("relative_pace_to_ahead_in_traffic_s_per_lap")
    assert rel.temporal_rule.value == "synchronized_field"
    assert rel.sync.value == "synchronized_field"
    assert rel.unit == "seconds_per_lap"
    rate = registry.get("recent_gap_to_ahead_change_in_traffic_s_per_lap")
    assert rate.sync.value == "synchronized_field"
    for n in INTERACTION_NAMES:
        d = registry.get(n)
        assert d.version == 1 and d.predictive_eligible
        assert d.status is FeatureStatus.CANDIDATE


def test_registry_counts_and_version(registry):
    assert len(registry) == 84
    assert FEATURE_SET_VERSION == "v8"


def test_engine_f11_resolution(registry):
    import pandas as pd
    df = pd.DataFrame([{
        "race_id": "R", "driver_id": "a", "lap_number": 1,
        "state_time_s": 100.0}])
    with pytest.raises(NoCalculatorError):
        from raceintel.features import interactions_for_state
        interactions_for_state(
            FeatureRequest("R", "a", 1, 100.0), registry, df,
            names=["grid_position"])


# --- single/batch parity on synthetic primitives ---

def _prims(n=6):
    return pd.DataFrame([{
        "race_id": "R", "driver_id": "a", "lap_number": i + 1,
        "state_time_s": 100.0 * (i + 1),
        "grid_position": 5 if i else 0,
        "position": 3,
        "relative_pace_to_car_ahead_s_per_lap": 0.5,
        "in_traffic_2s": True if i % 2 == 0 else (False if i % 4 == 1 else None),
        "recent_gap_to_ahead_change_s_per_lap": -0.1,
    } for i in range(n)])


def test_single_batch_parity(registry):
    from raceintel.features import interactions_batch
    prims = _prims()
    batch = interactions_batch(prims)
    assert len(batch) == len(prims)
    assert list(batch.columns) == ["race_id", "driver_id", "lap_number",
                                   "state_time_s"] + list(INTERACTION_NAMES)
    # single-state path needs full states+history; parity of the pure
    # core is asserted row-wise against interaction_values
    for _, prow in prims.iterrows():
        brow = batch[batch["lap_number"] == prow["lap_number"]].iloc[0]
        expect = interaction_values({c: (None if pd.isna(prow[c]) else prow[c])
                                     for c in
                                     ("grid_position", "position",
                                      "relative_pace_to_car_ahead_s_per_lap",
                                      "in_traffic_2s",
                                      "recent_gap_to_ahead_change_s_per_lap")})
        for n in INTERACTION_NAMES:
            a, b = expect[n], brow[n]
            b = None if (b is None or (isinstance(b, float)
                                       and np.isnan(b))) else b
            if a is None:
                assert b is None, (n, b)
            else:
                assert a == pytest.approx(float(b)), (n, a, b)
    # grid=0 row -> null positions_from_grid
    assert pd.isna(batch.iloc[0]["positions_from_grid"])
    assert batch.iloc[1]["positions_from_grid"] == pytest.approx(2.0)


def test_shuffled_input(registry):
    from raceintel.features import interactions_batch
    a = interactions_batch(_prims())
    b = interactions_batch(_prims().sample(frac=1.0, random_state=23))
    _pd = pd
    _pd.testing.assert_frame_equal(
        a.sort_values(["lap_number"]).reset_index(drop=True),
        b.sort_values(["lap_number"]).reset_index(drop=True))


# --- mutations via real engine paths ---

def test_future_source_mutation_real(registry):
    if not _HAS_D9:
        pytest.skip("canonical D9 data not present (data/v2 gitignored)")
    from raceintel.features import PriorHistory
    d9 = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/driver_lap_state_d9"
             "/season=2023/*.parquet")))], ignore_index=True)
    hb = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/hist_results/season=*/*.parquet")))],
        ignore_index=True)
    hr = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/hist_races/season=*/*.parquet")))],
        ignore_index=True)
    ta = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/results/season=*/*.parquet")))],
        ignore_index=True)
    tr = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/races/season=*/*.parquet")))],
        ignore_index=True)
    ps = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/pit_stops/season=*/*.parquet")))],
        ignore_index=True)
    h = PriorHistory(hb, hr, ta, tr, ps)
    sub = d9[d9["race_id"] == "2023-r01-R"]
    t = sub.iloc[500]
    q = FeatureRequest(str(t["race_id"]), str(t["driver_id"]),
                       int(t["lap_number"]), float(t["state_time_s"]))
    base = features_for_state(q, registry, sub, history=h,
                              names=list(INTERACTION_NAMES))
    # future lap-time mutation (drives all downstream primitives)
    mod = sub.copy()
    mod.loc[mod["lap_number"] > int(t["lap_number"]), "lap_time_s"] = 60.0
    assert results_equal(
        base, features_for_state(q, registry, mod, history=h,
                                 names=list(INTERACTION_NAMES)))
    # current position mutation moves only positions_from_grid
    mod2 = sub.copy()
    cur_pos = t["position"]
    new_pos = 20 if (cur_pos is not None and int(cur_pos) != 20) else 1
    mod2.loc[(mod2["driver_id"] == t["driver_id"])
             & (mod2["lap_number"] == int(t["lap_number"])),
             "position"] = new_pos
    out = features_for_state(q, registry, mod2, history=h,
                             names=list(INTERACTION_NAMES)).value_dict()
    assert out["positions_from_grid"] != base.value_dict()["positions_from_grid"]


def test_unrelated_input_isolation(registry):
    if not _HAS_D9:
        pytest.skip("canonical D9 data not present (data/v2 gitignored)")
    from raceintel.features import PriorHistory
    d9 = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/driver_lap_state_d9"
             "/season=2023/*.parquet")))], ignore_index=True)
    hb = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/hist_results/season=*/*.parquet")))],
        ignore_index=True)
    hr = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/hist_races/season=*/*.parquet")))],
        ignore_index=True)
    ta = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/results/season=*/*.parquet")))],
        ignore_index=True)
    tr = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/races/season=*/*.parquet")))],
        ignore_index=True)
    ps = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/pit_stops/season=*/*.parquet")))],
        ignore_index=True)
    h = PriorHistory(hb, hr, ta, tr, ps)
    sub = d9[d9["race_id"] == "2023-r01-R"]
    t = sub.iloc[500]
    q = FeatureRequest(str(t["race_id"]), str(t["driver_id"]),
                       int(t["lap_number"]), float(t["state_time_s"]))
    base = features_for_state(q, registry, sub, history=h,
                              names=list(INTERACTION_NAMES))
    # mutating an unrelated primitive (tyre compound past) changes nothing
    mod = sub.copy()
    mod.loc[mod["state_time_s"] <= float(t["state_time_s"]),
            "compound"] = "HARD"
    assert results_equal(
        base, features_for_state(q, registry, mod, history=h,
                                 names=list(INTERACTION_NAMES)))


# --- real-race spots ---

def _spot(registry, season, race_id):
    if not _HAS_D9:
        pytest.skip("canonical D9 data not present (data/v2 gitignored)")
    from raceintel.features import PriorHistory
    d9 = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/driver_lap_state_d9"
             f"/season={season}/*.parquet")))], ignore_index=True)
    mk = lambda pat: pd.concat([pd.read_parquet(f) for f in sorted(
        glob.glob(str(ROOT / f"data/v2/processed/{pat}/season=*/*.parquet")))],
        ignore_index=True)
    h = PriorHistory(mk("hist_results"), mk("hist_races"), mk("results"),
                     mk("races"), mk("pit_stops"))
    sub = d9[d9["race_id"] == race_id]
    t = sub.iloc[len(sub) // 2]
    q = FeatureRequest(str(t["race_id"]), str(t["driver_id"]),
                       int(t["lap_number"]), float(t["state_time_s"]))
    v = features_for_state(q, registry, sub, history=h,
                           names=list(INTERACTION_NAMES)).value_dict()
    return v


@pytest.mark.parametrize("season,race_id", [
    (2023, "2023-r01-R"), (2019, "2019-r11-R"), (2021, "2021-r12-R"),
    (2022, "2022-r07-R"), (2022, "2022-r18-R"), (2025, "2025-r01-R"),
])
def test_real_spots(registry, season, race_id):
    v = _spot(registry, season, race_id)
    assert set(v) == set(INTERACTION_NAMES)
    pfg = v["positions_from_grid"]
    assert pfg is None or isinstance(pfg, int)


# --- full-scope audit ---

def test_full_scope_audit(registry):
    if not _HAS_D9:
        pytest.skip("canonical D9 data not present (data/v2 gitignored)")
    from raceintel.features import (passthrough_batch, pace_batch, gap_batch,
                             context_batch, rates_batch, priors_batch,
                             PriorHistory, interactions_batch)
    d9 = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/driver_lap_state_d9"
             "/season=*/*.parquet")))], ignore_index=True)
    mk = lambda pat: pd.concat([pd.read_parquet(f) for f in sorted(
        glob.glob(str(ROOT / f"data/v2/processed/{pat}/season=*/*.parquet")))],
        ignore_index=True)
    h = PriorHistory(mk("hist_results"), mk("hist_races"), mk("results"),
                     mk("races"), mk("pit_stops"))
    key = ["race_id", "driver_id", "lap_number", "state_time_s"]
    M = passthrough_batch(d9, registry)
    M = M.merge(pace_batch(d9), on=key).merge(gap_batch(d9), on=key) \
        .merge(context_batch(d9), on=key).merge(rates_batch(d9), on=key) \
        .merge(priors_batch(d9, h), on=key)
    assert len(M) == 189420
    out = interactions_batch(M)
    assert len(out) == 189420
    assert list(out.columns) == key + list(INTERACTION_NAMES)
    assert not out.duplicated(subset=key[:-1]).any()
    for col in ("winner_flag", "position_final", "points"):
        assert col not in out.columns
    import json as _json
    print("F11_NULL_RATES=" + _json.dumps(
        {n: float(out[n].isna().mean()) for n in INTERACTION_NAMES}))
    for n in INTERACTION_NAMES:
        finite = out[n].dropna()
        if len(finite):
            print(f"F11_{n}: min={finite.min():.3f} "
                  f"p50={finite.median():.3f} max={finite.max():.3f}")
    # determinism
    import pandas as _pd
    _pd.testing.assert_frame_equal(out, interactions_batch(M))
    # redundancy snapshot (informational)
    for n, src in (("relative_pace_to_ahead_in_traffic_s_per_lap",
                    "relative_pace_to_car_ahead_s_per_lap"),
                   ("recent_gap_to_ahead_change_in_traffic_s_per_lap",
                    "recent_gap_to_ahead_change_s_per_lap"),
                   ("positions_from_grid", "position")):
        a, b = out[n].to_numpy(dtype=float), M[src].to_numpy(dtype=float)
        m = np.isfinite(a) & np.isfinite(b)
        print(f"CORR {n} vs {src}: {np.corrcoef(a[m], b[m])[0,1]:.4f}")
