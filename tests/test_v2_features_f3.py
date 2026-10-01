"""F3 tests: primitive temporal operators (offline; synthetic + spots).

Synthetic frames prove contract semantics; a small real-data section
(skipped when canonical data is absent) proves PARTIAL/red-flag support
on frozen D9 artifacts. No network.
"""

import numpy as np
import pandas as pd
import pytest

from raceintel.config import V2Paths
from raceintel.features import (
    FeatureRequest,
    RaceIndex,
    SyncState,
    TargetNotFoundError,
    TemporalError,
    driver_prefix,
    extract_roster,
    latest_at_or_before,
    observation_age_s,
    past_races_before,
    resolve_target,
    rolling_past_observations,
    synchronized_driver_state,
    synchronized_field_snapshot,
    within_stint_prefix,
)

ROOT = V2Paths.resolve().root
_HAS_D9 = (ROOT / "data/v2/processed/driver_lap_state_d9/season=2021").is_dir()


def _states(rows):
    return pd.DataFrame(rows, columns=[
        "race_id", "driver_id", "lap_number", "state_time_s", "position",
        "driver_number", "driver_abbreviation", "team"])


@pytest.fixture()
def race():
    return _states([
        ("R", "a", 1, 100.0, 2, 44, "HAM", "Mercedes"),
        ("R", "a", 2, 200.0, 2, 44, "HAM", "Mercedes"),
        ("R", "a", 3, 300.0, 1, 44, "HAM", "Mercedes"),
        ("R", "b", 1, 110.0, 1, 33, "VER", "Red Bull"),
        ("R", "b", 2, 205.0, 1, 33, "VER", "Red Bull"),
        ("R", "b", 3, 310.0, 2, 33, "VER", "Red Bull"),
    ])


# --- ordering / prefix ---

def test_prefix_inclusive_and_bounded(race):
    p = driver_prefix(race, "R", "a", 200.0)
    assert p["lap_number"].tolist() == [1, 2]
    assert (p["state_time_s"] <= 200.0).all()


def test_prefix_empty_when_unobserved(race):
    assert driver_prefix(race, "R", "a", 50.0).empty
    assert driver_prefix(race, "R", "zzz", 500.0).empty


def test_prefix_preserves_columns_and_source(race):
    before = race.copy(deep=True)
    p = driver_prefix(race, "R", "b", 205.0)
    assert list(p.columns) == list(race.columns)
    pd.testing.assert_frame_equal(race, before)


def test_prefix_shuffle_stable(race):
    p1 = driver_prefix(race, "R", "a", 300.0)
    sh = race.sample(frac=1.0, random_state=7)
    p2 = driver_prefix(sh, "R", "a", 300.0)
    pd.testing.assert_frame_equal(p1.reset_index(drop=True),
                                  p2.reset_index(drop=True))


def test_same_driver_tie_orders_by_lap():
    df = _states([
        ("R", "s", 4, 2349.136, 19, 18, "STR", "Aston"),
        ("R", "s", 5, 2349.136, 6, 18, "STR", "Aston"),
    ])
    p = driver_prefix(df, "R", "s", 2349.136)
    assert p["lap_number"].tolist() == [4, 5]


def test_missing_columns_rejected(race):
    with pytest.raises(TemporalError):
        driver_prefix(race.drop(columns=["state_time_s"]), "R", "a", 1.0)


# --- latest_at_or_before ---

def test_latest_rejects_near_future():
    df = pd.DataFrame({"t": [1.0, 2.0, 2.001], "v": [10, 20, 30]})
    row = latest_at_or_before(df, "t", 2.0)
    assert row["v"] == 20
    assert latest_at_or_before(df, "t", 0.5) is None


def test_latest_tie_deterministic():
    df = pd.DataFrame({"t": [5.0, 5.0], "lap_number": [3, 4],
                       "driver_id": ["a", "a"], "v": [1, 2]})
    assert latest_at_or_before(df, "t", 5.0)["v"] == 2
    # no nearest-time selection exists: only this selector; future rejected
    assert latest_at_or_before(df, "t", 4.999) is None


# --- synchronized_driver_state ---

def test_sync_selects_latest_le(race):
    s = synchronized_driver_state(race, "R", "b", 207.0)
    assert isinstance(s, SyncState)
    assert (s.observable, s.observed_lap, s.observed_time_s,
            s.observation_age_s) == (True, 2, 205.0, 2.0)
    assert s.values["position"] == 1


def test_sync_ignores_same_lap_future(race):
    # b lap 3 (t=310) shares no wait — target T=250: b lap2 (205) wins,
    # NOT b lap 3 (310) even though a's lap numbers also reach 3 later.
    s = synchronized_driver_state(race, "R", "b", 250.0)
    assert s.observed_lap == 2
    assert s.observation_age_s == pytest.approx(45.0)


def test_sync_unobservable(race):
    s = synchronized_driver_state(race, "R", "b", 50.0)
    assert s.observable is False
    assert s.observed_lap is None and s.values is None
    assert s.observation_age_s is None


def test_sync_age_nonnegative_pinned(race):
    for T in (100.0, 205.0, 310.0, 10_000.0):
        s = synchronized_driver_state(race, "R", "b", T)
        if s.observable:
            assert s.observation_age_s >= 0
    # huge age stays observable provenance, never retirement
    s = synchronized_driver_state(race, "R", "b", 100_000.0)
    assert s.observable is True and s.observation_age_s > 90_000


def test_observation_age_rejects_future():
    with pytest.raises(TemporalError):
        observation_age_s(10.0, 10.5)
    assert observation_age_s(10.0, 10.0) == 0.0


def test_no_retirement_inference_surface():
    import raceintel.features.temporal as tmod
    for name in ("is_running", "is_retired", "active_driver",
                 "retired", "is_active"):
        assert not hasattr(tmod, name), name


# --- field snapshot ---

def test_snapshot_exact_target_and_unobservable(race):
    snap = synchronized_field_snapshot(race, "R", "a", 2, 200.0,
                                       ["a", "b", "c"])
    assert [d for d, _ in snap.entries] == ["a", "b", "c"]
    by_id = dict(snap.entries)
    assert by_id["a"].observable and by_id["a"].observation_age_s == 0.0
    assert by_id["a"].values["position"] == 2
    assert by_id["b"].observed_lap == 1  # b lap2 at 205 > 200 rejected
    assert by_id["c"].observable is False  # six-roster-style member kept
    assert len(snap.entries) == 3


def test_snapshot_target_exactness(race):
    with pytest.raises(TargetNotFoundError):
        synchronized_field_snapshot(race, "R", "a", 2, 200.001,
                                    ["a", "b"])
    with pytest.raises(TargetNotFoundError):
        synchronized_field_snapshot(race, "R", "a", 9, 200.0, ["a"])
    with pytest.raises(TargetNotFoundError):
        resolve_target(race, "R", "zzz", 1, 100.0)


def test_snapshot_not_ordered_by_position(race):
    snap = synchronized_field_snapshot(race, "R", "b", 1, 110.0, ["b", "a"])
    assert [d for d, _ in snap.entries] == ["a", "b"]


# --- roster ---

def test_roster_identity_only():
    res = pd.DataFrame({
        "race_id": ["R", "R"], "driver_id": ["a", "b"],
        "grid_position": [1, 2], "position_final": [2, 1],
        "points": [18.0, 25.0], "winner_flag": [False, True]})
    roster = extract_roster(res)
    assert roster == {"R": ["a", "b"]}
    mutated = res.assign(position_final=[1, 2], points=[25.0, 18.0],
                         winner_flag=[True, False])
    assert extract_roster(mutated) == roster


# --- within-stint prefix ---

def _stint_frame():
    return pd.DataFrame([
        ("R", "a", 1, 100.0, 1, 5), ("R", "a", 2, 200.0, 1, 5),
        ("R", "a", 3, 300.0, 2, 0), ("R", "a", 4, 400.0, 2, 1),
        ("R", "a", 5, 500.0, 2, 2),
    ], columns=["race_id", "driver_id", "lap_number", "state_time_s",
                "stint_number", "tyre_life"])


def test_within_stint_current_only():
    w = within_stint_prefix(_stint_frame(), "R", "a", 500.0)
    assert w["lap_number"].tolist() == [3, 4, 5]


def test_within_stint_ignores_future_end():
    df = _stint_frame()
    df["end_lap"] = [2, 2, 99, 99, 99]  # fabricated future ends
    w = within_stint_prefix(df, "R", "a", 300.0)
    assert w["lap_number"].tolist() == [3]
    w2 = within_stint_prefix(df, "R", "a", 200.0)
    assert w2["lap_number"].tolist() == [1, 2]


def test_within_stint_null_stint_empty():
    df = _stint_frame()
    df.loc[df["lap_number"] == 5, "stint_number"] = np.nan
    assert within_stint_prefix(df, "R", "a", 500.0).empty


def test_within_stint_shuffle_and_pit_invariance():
    df = _stint_frame()
    w1 = within_stint_prefix(df, "R", "a", 400.0)
    w2 = within_stint_prefix(df.sample(frac=1.0, random_state=3),
                             "R", "a", 400.0)
    pd.testing.assert_frame_equal(w1.reset_index(drop=True),
                                  w2.reset_index(drop=True))


# --- past races ---

def _races():
    return pd.DataFrame([
        ("2023-r01-R", 2023, 1), ("2023-r02-R", 2023, 2),
        ("2023-r10-R", 2023, 10), ("2024-r01-R", 2024, 1),
    ], columns=["race_id", "season", "round_no"])


def test_past_races_excludes_current_and_future():
    out = past_races_before(_races(), 2023, 10)
    assert out["race_id"].tolist() == ["2023-r01-R", "2023-r02-R"]
    assert past_races_before(_races(), 2023, 1).empty
    assert "2024-r01-R" in past_races_before(_races(), 2024, 2)["race_id"].tolist()


def test_past_races_not_lexical():
    df = pd.DataFrame([
        ("zz-9", 2023, 9), ("aa-10", 2023, 10),
    ], columns=["race_id", "season", "round_no"])
    out = past_races_before(df, 2023, 10)
    assert out["race_id"].tolist() == ["zz-9"]


def test_past_races_future_results_mutation_invariant():
    df = _races().assign(points=[25, 18, 15, 25], winner=["a", "b", "c", "d"])
    assert past_races_before(
        df, 2023, 10)["race_id"].tolist() == ["2023-r01-R", "2023-r02-R"]


# --- rolling selector ---

def test_rolling_latest_n_and_target_inclusion(race):
    p = driver_prefix(race, "R", "a", 300.0)
    mask = np.array([True, True, True])
    w = rolling_past_observations(p, 300.0, mask, 2)
    assert w["lap_number"].tolist() == [2, 3]
    w1 = rolling_past_observations(p, 300.0, mask, 1)
    assert w1["lap_number"].tolist() == [3]  # target included at LAP_END


def test_rolling_respects_mask_nulls_and_past_only(race):
    p = driver_prefix(race, "R", "a", 300.0).copy()
    p.loc[p["lap_number"] == 2, "position"] = np.nan
    mask = np.array([True, False, True])
    w = rolling_past_observations(p, 300.0, mask, 5)
    assert w["lap_number"].tolist() == [1, 3]
    assert w["position"].isna().sum() == 0  # masked row gone, nulls preserved
    w_all_null = rolling_past_observations(p, 300.0,
                                           np.array([False, False, False]), 3)
    assert w_all_null.empty


def test_rolling_rejects_future_rows():
    p = _states([("R", "a", 1, 100.0, 1, 1, "X", "T"),
                 ("R", "a", 2, 999.0, 1, 1, "X", "T")])
    w = rolling_past_observations(p, 100.0, np.array([True, True]), 5)
    assert w["lap_number"].tolist() == [1]
    with pytest.raises(TemporalError):
        rolling_past_observations(p, 100.0, np.array([True, True]), 0)


# --- future-mutation suite (F1 §19 A–M) ---

@pytest.fixture()
def mut_race():
    return _states([
        ("R", "t", 1, 100.0, 3, 1, "T", "T1"),
        ("R", "t", 2, 200.0, 2, 1, "T", "T1"),
        ("R", "r", 1, 110.0, 2, 2, "R", "T2"),
        ("R", "r", 2, 190.0, 1, 2, "R", "T2"),
    ])


def _sync_at(df):
    return synchronized_driver_state(df, "R", "r", 200.0)


def test_mutation_future_same_lap_ignored(mut_race):
    base = _sync_at(mut_race)
    extra = _states([("R", "r", 2, 260.0, 1, 2, "R", "T2")])
    assert _sync_at(pd.concat([mut_race, extra],
                              ignore_index=True)) == base


def test_mutation_future_later_lap_ignored(mut_race):
    base = _sync_at(mut_race)
    extra = _states([("R", "r", 3, 290.0, 1, 2, "R", "T2")])
    assert _sync_at(pd.concat([mut_race, extra],
                              ignore_index=True)) == base


def test_mutation_future_timing_values_ignored(mut_race):
    base = _sync_at(mut_race)
    mod = mut_race.copy()
    mod.loc[(mod["driver_id"] == "r") & (mod["lap_number"] == 2),
            "state_time_s"] = 9_999.0
    # the mutated row is now future -> selection falls back to lap 1
    out = _sync_at(mod)
    assert out.observed_lap == 1
    assert out.observation_age_s == pytest.approx(90.0)
    assert out != base  # documents correct fallback, not invariance here
    # value-only mutation of a future row cannot leak either
    mod2 = pd.concat([mut_race, _states(
        [("R", "r", 9, 9_999.0, 1, 2, "R", "T2")])], ignore_index=True)
    assert _sync_at(mod2) == base


def test_mutation_delete_future_and_reorder(mut_race):
    base = _sync_at(mut_race)
    dropped = mut_race[~((mut_race["driver_id"] == "r")
                         & (mut_race["state_time_s"] > 200.0))]
    assert _sync_at(dropped) == base
    shuffled = mut_race.sample(frac=1.0, random_state=11)
    assert _sync_at(shuffled) == base
    dup = pd.concat([mut_race, mut_race[mut_race["state_time_s"] > 200.0]],
                    ignore_index=True)
    assert _sync_at(dup) == base


def _sel(s):
    return (s.observable, s.observed_lap, s.observed_time_s,
            s.observation_age_s)


def test_mutation_identifier_changes_invisible(mut_race):
    base = _sync_at(mut_race)
    mod = mut_race.copy()
    mod.loc[mod["driver_id"] == "r",
            ["driver_number", "driver_abbreviation", "team"]] = \
        [99, "ZZZ", "Renamed Team"]
    # temporal selection is identical; only presentation payload differs
    assert _sel(_sync_at(mod)) == _sel(base)
    p1 = driver_prefix(mut_race, "R", "r", 200.0)
    p2 = driver_prefix(mod, "R", "r", 200.0)
    assert p1[["race_id", "driver_id", "lap_number",
               "state_time_s"]].equals(
        p2[["race_id", "driver_id", "lap_number", "state_time_s"]])


# --- broad invariants ---

def test_invariants_synthetic(race):
    roster = ["a", "b"]
    for _, t in race.iterrows():
        T = float(t["state_time_s"])
        p = driver_prefix(race, "R", t["driver_id"], T)
        assert (p["state_time_s"] <= T).all()
        s = synchronized_driver_state(race, "R", "a" if t["driver_id"] == "b"
                                      else "b", T)
        if s.observable:
            assert s.observed_time_s <= T and s.observation_age_s >= 0
        snap = synchronized_field_snapshot(race, "R", t["driver_id"],
                                           int(t["lap_number"]), T, roster)
        assert len(snap.entries) == 2
        ages = [e.observation_age_s for _, e in snap.entries if e.observable]
        assert all(a >= 0 for a in ages)


def test_index_matches_frame_semantics(race):
    idx = RaceIndex(race)
    for _, t in race.iterrows():
        T = float(t["state_time_s"])
        for rival in ("a", "b"):
            a = synchronized_driver_state(race, "R", rival, T)
            b = idx.sync_lookup("R", rival, T)
            assert (a.observable, a.observed_lap, a.observed_time_s) == \
                   (b.observable, b.observed_lap, b.observed_time_s)
    snap = idx.field_snapshot("R", "a", 2, 200.0, ["a", "b", "c"])
    assert [d for d, _ in snap.entries] == ["a", "b", "c"]
    assert dict(snap.entries)["c"].observable is False


# --- real-data spots (PARTIAL / red flag; cheap season-file reads) ---

def _season_states(season):
    if not _HAS_D9:
        pytest.skip("canonical D9 data not present (data/v2 gitignored)")
    import glob as _g
    files = sorted(_g.glob(str(ROOT / "data/v2/processed/driver_lap_state_d9"
                               / f"season={season}/*.parquet")))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def test_real_belgium_partial_sync():
    d9 = _season_states(2021)
    sub = d9[d9["race_id"] == "2021-r12-R"]
    assert len(sub) == 60
    t = sub.iloc[0]
    snap = synchronized_field_snapshot(
        sub, "2021-r12-R", t["driver_id"], int(t["lap_number"]),
        float(t["state_time_s"]), sorted(sub["driver_id"].unique()))
    assert len(snap.entries) == sub["driver_id"].nunique()
    for _, e in snap.entries:
        if e.observable:
            assert e.observed_time_s <= float(t["state_time_s"])


def test_real_japan_red_flag_sync():
    d9 = _season_states(2022)
    red = d9[(d9["race_id"] == "2022-r18-R")
             & (d9["track_state"] == "red_flag")]
    assert len(red) > 0
    t = red.iloc[0]
    T = float(t["state_time_s"])
    snap = synchronized_field_snapshot(
        d9[d9["race_id"] == "2022-r18-R"], "2022-r18-R", t["driver_id"],
        int(t["lap_number"]), T, ["max_verstappen", t["driver_id"]])
    by_id = dict(snap.entries)
    assert by_id[t["driver_id"]].observation_age_s == 0.0


def test_real_monaco_stale_is_observable():
    d9 = _season_states(2022)
    sub = d9[d9["race_id"] == "2022-r07-R"]
    late = sub["state_time_s"].max()
    early_driver = sub.sort_values("state_time_s").iloc[0]["driver_id"]
    s = synchronized_driver_state(sub, "2022-r07-R", early_driver, late)
    assert s.observable is True  # stale, never retired-by-inference
