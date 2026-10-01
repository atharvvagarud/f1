"""F10 tests: pre-race grid + past-race priors (offline).

Synthetic history frames prove the H<R firewall, constancy, and
formulas; real-data tests run on frozen Tier-B/D5 artifacts (skipped
when absent). No network.
"""

import glob

import numpy as np
import pandas as pd
import pytest

from raceintel.config import V2Paths
from raceintel.features import (
    FEATURE_SET_VERSION,
    F10_FEATURE_NAMES,
    FeatureFamily,
    FeatureRequest,
    FeatureStatus,
    NoCalculatorError,
    PriorHistory,
    SyncRequirement,
    TemporalRule,
    build_f10_registry,
    constructor_priors,
    circuit_priors,
    driver_priors,
    features_for_state,
    history_before,
    priors_batch,
    priors_for_state,
    resolve_grid,
    results_equal,
)
from raceintel.features.contracts import MissingPolicy
from raceintel.features.registry import FeatureRegistry
from raceintel.features.temporal import TemporalError

ROOT = V2Paths.resolve().root
_HAS = (ROOT / "data/v2/processed/hist_results/season=2020").is_dir()


def _hrow(season, rnd, drv, team="T1", grid=5, pos="3", pts=15.0,
          circ="c1"):
    # mirrors Tier-B semantics: numeric position iff classified, else None
    numeric = None
    try:
        numeric = int(pos)
    except (TypeError, ValueError):
        numeric = None
    return {"season": season, "round_no": rnd, "driver_id": drv,
            "constructor_id": team, "grid": grid, "position": numeric,
            "position_text": pos, "points": pts, "circuit_id": circ}


@pytest.fixture()
def hist():
    rows = [
        _hrow(2022, 1, "a", grid=2, pos="1", pts=25.0),
        _hrow(2022, 2, "a", grid=3, pos="2", pts=18.0),
        _hrow(2022, 3, "a", grid=1, pos="R", pts=0.0),
        _hrow(2022, 1, "b", grid=5, pos="4", pts=12.0),
        _hrow(2023, 1, "a", grid=2, pos="1", pts=25.0),
    ]
    return pd.DataFrame(rows)


@pytest.fixture()
def registry():
    return build_f10_registry()


# --- chronology firewall ---

def test_history_before_excludes_current_and_future(hist):
    out = history_before(hist, "season", "round_no", 2023, 1)
    assert set(zip(out["season"], out["round_no"])) == \
        {(2022, 1), (2022, 2), (2022, 3)}
    assert history_before(hist, "season", "round_no", 2022, 1).empty
    nxt = history_before(hist, "season", "round_no", 2024, 1)
    assert (2023, 1) in set(zip(nxt["season"], nxt["round_no"]))


def test_season_boundary(hist):
    out = history_before(hist, "season", "round_no", 2023, 1)
    assert (out["season"] < 2023).all()


# --- grid ---

def test_grid_factual_and_missing():
    res = pd.DataFrame([
        {"race_id": "R", "driver_id": "a", "grid_position": 3},
        {"race_id": "R", "driver_id": "b", "grid_position": None},
        {"race_id": "R", "driver_id": "c", "grid_position": 0},
    ])
    assert resolve_grid(res, "R", "a") == 3
    assert resolve_grid(res, "R", "b") is None
    assert resolve_grid(res, "R", "c") == 0  # pit-lane code preserved
    assert resolve_grid(res, "R", "zzz") is None


# --- driver priors ---

def test_driver_zero_history(hist):
    d = driver_priors(hist, "rookie", 2023, 2)
    assert d["prior_driver_starts"] == 0
    assert d["prior_driver_mean_finish"] is None
    assert d["prior_driver_points_per_start"] is None
    assert d["prior_driver_mean_grid"] is None
    assert d["recent_driver_mean_finish_5"] is None


def test_driver_summary(hist):
    # a before 2023-r02: starts 2022r1,r2,r3 + 2023r1 = 4
    d = driver_priors(hist, "a", 2023, 2)
    assert d["prior_driver_starts"] == 4
    # classified: 1,2,1 -> mean 4/3
    assert d["prior_driver_mean_finish"] == pytest.approx(4 / 3)
    # points 25+18+0+25=68 / 4
    assert d["prior_driver_points_per_start"] == pytest.approx(17.0)
    # grids 2,3,1,2 -> mean 2 (all > 0)
    assert d["prior_driver_mean_grid"] == pytest.approx(2.0)
    # trailing 5 = all 4, classified 3 -> same as long here
    assert d["recent_driver_mean_finish_5"] == pytest.approx(4 / 3)


def test_driver_min_history(hist):
    # b has 1 start before 2023-r02
    d = driver_priors(hist, "b", 2023, 2)
    assert d["prior_driver_starts"] == 1
    assert d["prior_driver_mean_finish"] is None
    assert d["prior_driver_points_per_start"] is None
    assert d["recent_driver_mean_finish_5"] is None


def test_driver_excludes_w_and_r_from_means():
    hb = pd.DataFrame([
        _hrow(2022, 1, "a", pos="R", pts=0.0),
        _hrow(2022, 2, "a", pos="W", pts=0.0),
        _hrow(2022, 3, "a", pos="4", pts=12.0),
        _hrow(2022, 4, "a", pos="5", pts=10.0),
        _hrow(2022, 5, "a", pos="6", pts=8.0),
    ])
    d = driver_priors(hb, "a", 2023, 1)
    # starts: R + 3 classified (W excluded) = 4
    assert d["prior_driver_starts"] == 4
    assert d["prior_driver_mean_finish"] == pytest.approx(5.0)
    assert d["prior_driver_points_per_start"] == pytest.approx(30 / 4)


# --- constructor priors ---

def test_constructor_identity_and_denominator(hist):
    c = constructor_priors(hist, "T1", 2023, 2)
    # team-races: 2022r1,r2,r3,2023r1 = 4
    assert c["prior_constructor_races"] == 4
    # entries: a(4) + b(1) = 5; points 68+12=80 -> 16/entry
    assert c["prior_constructor_points_per_entry"] == pytest.approx(16.0)
    # classified entries: a(1,2,1) + b(4) -> mean 8/4
    assert c["prior_constructor_mean_finish"] == pytest.approx(2.0)
    assert c["recent_constructor_points_per_entry_5"] == pytest.approx(16.0)


def test_constructor_zero_and_null_identity(hist):
    c = constructor_priors(hist, "NEW", 2023, 2)
    assert c["prior_constructor_races"] == 0
    assert c["prior_constructor_points_per_entry"] is None
    n = constructor_priors(hist, None, 2023, 2)
    assert n["prior_constructor_races"] is None


def test_constructor_no_merge_across_slugs():
    hb = pd.DataFrame([
        _hrow(2022, 1, "a", team="force_india", pos="7", pts=6.0),
        _hrow(2022, 2, "a", team="racing_point", pos="8", pts=4.0),
    ])
    c1 = constructor_priors(hb, "force_india", 2023, 1)
    c2 = constructor_priors(hb, "racing_point", 2023, 1)
    assert c1["prior_constructor_races"] == 1
    assert c2["prior_constructor_races"] == 1


# --- circuit priors ---

def _circuit_frames():
    races = pd.DataFrame([
        {"race_id": "2022-r01-R", "season": 2022, "round_no": 1,
         "circuit_id": "cc"},
        {"race_id": "2023-r01-R", "season": 2023, "round_no": 1,
         "circuit_id": "cc"},
        {"race_id": "2023-r05-R", "season": 2023, "round_no": 5,
         "circuit_id": "dd"},
    ])
    results = pd.DataFrame([
        {"race_id": "2022-r01-R", "driver_id": "a", "grid_position": 2,
         "position_final": 1},
        {"race_id": "2022-r01-R", "driver_id": "b", "grid_position": 1,
         "position_final": 2},
    ])
    pits = pd.DataFrame([
        {"race_id": "2022-r01-R", "driver_id": "a"},
        {"race_id": "2022-r01-R", "driver_id": "b"},
        {"race_id": "2022-r01-R", "driver_id": "a"},
    ])
    return races, results, pits


def test_circuit_first_edition_and_history():
    races, results, pits = _circuit_frames()
    c0 = circuit_priors(races, results, pits, "cc", 2022, 1)
    assert c0["prior_circuit_races"] == 0
    assert c0["prior_circuit_mean_pit_stops_per_entry"] is None
    assert c0["prior_circuit_mean_position_change"] is None
    c1 = circuit_priors(races, results, pits, "cc", 2023, 1)
    assert c1["prior_circuit_races"] == 1  # below min-2 editions
    assert c1["prior_circuit_mean_pit_stops_per_entry"] is None
    c2 = circuit_priors(races, results, pits, "cc", 2024, 1)
    assert c2["prior_circuit_races"] == 2
    # 2022-r01: 3 stops / 2 entries = 1.5; 2023-r01 has no result
    # coverage -> excluded (not zeroed)
    assert c2["prior_circuit_mean_pit_stops_per_entry"] == \
        pytest.approx(1.5)
    # edition mean change: (2-1)+(1-2) = +1,-1 -> 0.0
    assert c2["prior_circuit_mean_position_change"] == pytest.approx(0.0)


def test_circuit_future_edition_excluded():
    races, results, pits = _circuit_frames()
    c = circuit_priors(races, results, pits, "dd", 2023, 5)
    assert c["prior_circuit_races"] == 0
    # dd's only edition IS the target -> excluded


# --- firewall mutations ---

def _bundle(hist):
    races = pd.DataFrame([
        {"race_id": "2023-r02-R", "season": 2023, "round_no": 2,
         "circuit_id": "cc"},
    ])
    results = pd.DataFrame([
        {"race_id": "2023-r02-R", "driver_id": "a", "grid_position": 2,
         "position_final": 1, "classified_position": 1,
         "position_text": "1", "status_text": "Finished", "points": 25.0,
         "laps_completed": 57, "dnf_flag": False, "winner_flag": True,
         "podium_flag": True},
        {"race_id": "2023-r02-R", "driver_id": "b", "grid_position": 5,
         "position_final": 4, "classified_position": 4,
         "position_text": "4", "status_text": "+1 Lap", "points": 12.0,
         "laps_completed": 57, "dnf_flag": False, "winner_flag": False,
         "podium_flag": False},
    ])
    from raceintel.features import PriorHistory
    return PriorHistory(hist_results=hist,
                        hist_races=pd.DataFrame(
                            [{"season": 2022, "round_no": 1},
                             {"season": 2023, "round_no": 2}]),
                        results_tiera=results,
                        races_tiera=races,
                        pit_stops=pd.DataFrame(
                            [{"race_id": "2023-r02-R",
                              "driver_id": "a"}]))


def _states():
    return pd.DataFrame([
        {"race_id": "2023-r02-R", "driver_id": "a", "lap_number": 10,
         "state_time_s": 1000.0, "season": 2023, "round_no": 2,
         "circuit_id": "cc", "constructor_id": "T1"},
        {"race_id": "2023-r02-R", "driver_id": "b", "lap_number": 10,
         "state_time_s": 1010.0, "season": 2023, "round_no": 2,
         "circuit_id": "cc", "constructor_id": "T1"},
    ])


def _req10(drv="a", t=1000.0):
    return FeatureRequest("2023-r02-R", drv, 10, t)


def test_current_result_mutation_invisible(hist, registry):
    from raceintel.features import priors_for_state, F10_FEATURE_NAMES
    h = _bundle(hist)
    st = _states()
    base = priors_for_state(_req10(), registry, st, h)
    # mutate every current-race outcome column
    h2 = PriorHistory(hist_results=h.hist_results, hist_races=h.hist_races,
                      results_tiera=h.results_tiera.assign(
                          position_final=[20, 20], points=[0.0, 0.0],
                          winner_flag=[False, False]),
                      races_tiera=h.races_tiera, pit_stops=h.pit_stops)
    assert results_equal(
        base, priors_for_state(_req10(), registry, st, h2))


def test_future_result_mutation_invisible(hist, registry):
    from raceintel.features import priors_for_state
    h = _bundle(hist)
    st = _states()
    base = priors_for_state(_req10(), registry, st, h)
    future = pd.DataFrame([_hrow(2024, 1, "a", pos="1", pts=25.0)])
    h2 = PriorHistory(hist_results=pd.concat([h.hist_results, future],
                                            ignore_index=True),
                      hist_races=h.hist_races, results_tiera=h.results_tiera,
                      races_tiera=h.races_tiera, pit_stops=h.pit_stops)
    assert results_equal(
        base, priors_for_state(_req10(), registry, st, h2))


def test_eligible_prior_mutation_visible(hist, registry):
    from raceintel.features import priors_for_state
    h = _bundle(hist)
    st = _states()
    base = priors_for_state(_req10(), registry, st, h).value_dict()
    mod = h.hist_results.copy()
    mod.loc[(mod["season"] == 2022) & (mod["round_no"] == 1)
            & (mod["driver_id"] == "a"), "position"] = 20
    mod.loc[(mod["season"] == 2022) & (mod["round_no"] == 1)
            & (mod["driver_id"] == "a"), "position_text"] = "20"
    h2 = PriorHistory(hist_results=mod, hist_races=h.hist_races,
                      results_tiera=h.results_tiera,
                      races_tiera=h.races_tiera, pit_stops=h.pit_stops)
    out = priors_for_state(_req10(), registry, st, h2).value_dict()
    assert out["prior_driver_mean_finish"] != base["prior_driver_mean_finish"]
    # grid feature untouched by result mutation
    assert out["grid_position"] == base["grid_position"]


def test_grid_mutation_isolation(hist, registry):
    from raceintel.features import priors_for_state
    h = _bundle(hist)
    st = _states()
    base = priors_for_state(_req10(), registry, st, h).value_dict()
    h2 = PriorHistory(hist_results=h.hist_results, hist_races=h.hist_races,
                      results_tiera=h.results_tiera.assign(grid_position=20),
                      races_tiera=h.races_tiera, pit_stops=h.pit_stops)
    out = priors_for_state(_req10(), registry, st, h2).value_dict()
    assert out["grid_position"] == 20
    assert out["prior_driver_mean_finish"] == base["prior_driver_mean_finish"]


def test_rookie_future_career_adversary(registry):
    hb = pd.DataFrame([
        _hrow(2023, 5 + i, "rookie", pos="1", pts=25.0) for i in range(5)
    ])
    from raceintel.features import priors_for_state
    h = _bundle(hb)
    st = pd.DataFrame([
        {"race_id": "2023-r02-R", "driver_id": "rookie", "lap_number": 3,
         "state_time_s": 300.0, "season": 2023, "round_no": 2,
         "circuit_id": "cc", "constructor_id": "T9"},
    ])
    v = priors_for_state(FeatureRequest("2023-r02-R", "rookie", 3, 300.0),
                         registry, st, h).value_dict()
    assert v["prior_driver_starts"] == 0
    assert v["prior_driver_mean_finish"] is None
    # later 5-win career (rounds 5-9, all future) invisible
    assert v["prior_driver_points_per_start"] is None


def test_future_circuit_edition_excluded(registry):
    races = pd.DataFrame([
        {"race_id": "R1", "season": 2022, "round_no": 1, "circuit_id": "cc"},
        {"race_id": "R9", "season": 2022, "round_no": 9, "circuit_id": "cc"},
    ])
    results = pd.DataFrame([
        {"race_id": "R1", "driver_id": "a", "grid_position": 2,
         "position_final": 1},
        {"race_id": "R9", "driver_id": "a", "grid_position": 20,
         "position_final": 20},
    ])
    pits = pd.DataFrame([{"race_id": "R1", "driver_id": "a"}])
    c = circuit_priors(races, results, pits, "cc", 2022, 2)
    assert c["prior_circuit_races"] == 1  # R9 (future) excluded


# --- constancy / parity / identity ---

def test_same_race_constancy(hist, registry):
    from raceintel.features import priors_batch
    h = _bundle(hist)
    st = pd.DataFrame([
        {"race_id": "2023-r02-R", "driver_id": d, "lap_number": lap,
         "state_time_s": 100.0 * lap, "season": 2023, "round_no": 2,
         "circuit_id": "cc", "constructor_id": "T1"}
        for d in ("a", "b") for lap in (1, 5, 10)
    ])
    batch = priors_batch(st, h)
    assert len(batch) == 6
    from raceintel.features import F10_FEATURE_NAMES
    for n in list(F10_FEATURE_NAMES):
        assert batch.groupby(["race_id", "driver_id"])[n].nunique(
            dropna=False).max() == 1, n
    # single/batch parity
    from raceintel.features import priors_for_state
    for _, row in batch.iterrows():
        q = FeatureRequest(str(row["race_id"]), str(row["driver_id"]),
                           int(row["lap_number"]), float(row["state_time_s"]))
        single = priors_for_state(q, registry, st, h)
        for n in F10_FEATURE_NAMES:
            a = single.value_dict()[n]
            b = row[n]
            b = None if (b is None or (isinstance(b, float)
                                       and np.isnan(b))) else b
            if a is None:
                assert b is None, (n, b)
            else:
                assert a == pytest.approx(float(b)), (n, a, b)


def test_presentation_identity_mutation(hist, registry):
    from raceintel.features import priors_for_state
    h = _bundle(hist)
    st = _states()
    base = priors_for_state(_req10(), registry, st, h)
    # display-level columns are ignored by slug-keyed joins: add and
    # mutate them aggressively; selection must not move
    h2 = PriorHistory(
        hist_results=h.hist_results.assign(
            driver_code="XXX", driver_number=99,
            constructor_name="Renamed Team Display"),
        hist_races=h.hist_races, results_tiera=h.results_tiera,
        races_tiera=h.races_tiera, pit_stops=h.pit_stops)
    assert results_equal(
        base, priors_for_state(_req10(), registry, st, h2))


def test_shuffled_input(hist, registry):
    from raceintel.features import priors_for_state
    h = _bundle(hist)
    st = _states()
    a = priors_for_state(_req10(), registry, st, h)
    b = priors_for_state(_req10(), registry,
                         st.sample(frac=1.0, random_state=3), h)
    assert results_equal(a, b)


# --- registry / version / absence guards ---

def test_f10_registry_metadata(registry):
    assert len(registry) == 81
    assert FEATURE_SET_VERSION == "v8"
    from raceintel.features import F10_FEATURE_NAMES as _names
    for name in _names:
        d = registry.get(name)
        assert d.version >= 1 and d.predictive_eligible
        assert d.sync.value == "none"
        assert d.status is FeatureStatus.CANDIDATE
    assert registry.get("grid_position").version == 2
    assert registry.get("prior_driver_mean_finish").temporal_rule.value == \
        "past_races"
    names = " ".join(registry.names())
    for token in ("dnf", "reliability", "win_probability", "championship",
                  "qualifying", "q1", "talent", "rating", "difficulty",
                  "overtaking_score"):
        assert token not in names.lower(), token


def test_engine_f10_resolution(hist, registry):
    from raceintel.features import priors_for_state
    h = _bundle(hist)
    st = _states()
    res = priors_for_state(_req10(), registry, st, h,
                           names=["grid_position",
                                  "prior_driver_starts"])
    assert sorted(n for n, _ in res.values) == [
        "grid_position", "prior_driver_starts"]
    assert res.feature_set_version == "v8"
    with pytest.raises(NoCalculatorError):
        priors_for_state(_req10(), registry, st, h, names=["nope"])
    # engine-level dispatch without history bundle must fail explicitly
    with pytest.raises(NoCalculatorError):
        features_for_state(_req10(), registry, st,
                           names=["prior_driver_starts"])


# --- real-data spots ---

def _real_frames():
    if not _HAS:
        pytest.skip("canonical data not present (data/v2 gitignored)")
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
    d9 = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/driver_lap_state_d9"
             "/season=*/*.parquet")))], ignore_index=True)
    from raceintel.features import PriorHistory
    return PriorHistory(hb, hr, ta, tr, ps), d9


def test_real_first_2018_race(registry):
    h, d9 = _real_frames()
    from raceintel.features import priors_for_state
    sub = d9[d9["race_id"] == "2018-r01-R"]
    t = sub.iloc[0]
    v = priors_for_state(FeatureRequest(
        str(t["race_id"]), str(t["driver_id"]), int(t["lap_number"]),
        float(t["state_time_s"])), registry, sub, h).value_dict()
    # deep Tier-B history: veterans have priors even at 2018-r01
    assert v["prior_driver_starts"] >= 0
    ham = sub[sub["driver_id"] == "hamilton"]
    if len(ham):
        t = ham.iloc[0]
        vh = priors_for_state(FeatureRequest(
            str(t["race_id"]), str(t["driver_id"]), int(t["lap_number"]),
            float(t["state_time_s"])), registry, sub, h).value_dict()
        assert vh["prior_driver_starts"] > 50
        assert vh["prior_circuit_races"] == 0  # debut Tier-A edition
        assert vh["prior_circuit_mean_pit_stops_per_entry"] is None


def test_real_grid_nulls_and_pitlane():
    if not _HAS:
        pytest.skip("canonical data not present (data/v2 gitignored)")
    ta = pd.concat([pd.read_parquet(f) for f in sorted(glob.glob(
        str(ROOT / "data/v2/processed/results/season=*/*.parquet")))],
        ignore_index=True)
    from raceintel.features import resolve_grid
    # the 3 known W/DNS rows resolve to null (never imputed)
    assert resolve_grid(ta, "2021-r22-R", "mazepin") is None
    assert resolve_grid(ta, "2022-r02-R", "mick_schumacher") is None
    assert resolve_grid(ta, "2023-r15-R", "stroll") is None
    # pit-lane code preserved, normal slot factual
    assert resolve_grid(ta, "2019-r04-R", "kubica") == 0
    assert resolve_grid(ta, "2023-r01-R", "max_verstappen") == 1


def test_real_midcareer_and_debut(registry):
    h, d9 = _real_frames()
    from raceintel.features import priors_for_state, priors_batch
    # debut venue: Miami 2022-r05 (first Tier-A edition)
    sub = d9[d9["race_id"] == "2022-r05-R"]
    t = sub.iloc[0]
    v = priors_for_state(FeatureRequest(
        str(t["race_id"]), str(t["driver_id"]), int(t["lap_number"]),
        float(t["state_time_s"])), registry, sub, h).value_dict()
    assert v["prior_circuit_races"] == 0
    # constancy over full scope via batch
    batch = priors_batch(d9, h)
    assert len(batch) == 189420
    from raceintel.features import F10_FEATURE_NAMES
    for n in list(F10_FEATURE_NAMES):
        assert batch.groupby(["race_id", "driver_id"])[n].nunique(
            dropna=False).max() == 1, n
    import json as _json
    print("F10_NULL_RATES=" + _json.dumps(
        {n: float(batch[n].isna().mean()) for n in F10_FEATURE_NAMES}))
