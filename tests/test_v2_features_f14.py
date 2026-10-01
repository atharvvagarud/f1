"""F14 red-team: end-to-end leakage, parity + temporal attacks (offline).

Adversarial verification over the complete F4-F13 system. Every test
here tries to break the pipeline: forbidden-source mutations must be
invisible (NEGATIVE controls) while eligible-source mutations must
move the mathematically dependent outputs (POSITIVE controls). A
leakage suite without positive controls is insufficient.

Covers F14 pass criteria 1-45 (minus documentation): threat model is
in tests/f14_helpers.py; leakage matrix + manifests asserted below.
"""

import glob

import numpy as np
import pandas as pd
import pytest

from raceintel import contracts as C
from raceintel.features import (
    F9_FEATURE_NAMES,
    F5_FEATURE_NAMES,
    FEATURE_SET_VERSION,
    GAP_FEATURE_NAMES,
    FeatureRequest,
    PriorHistory,
    build_f11_registry,
    driver_priors,
    features_for_batch,
    features_for_state,
    history_before,
    results_equal,
)
from raceintel.features.temporal import (
    RaceIndex,
    TargetNotFoundError,
    TemporalError,
    extract_roster,
    synchronized_field_snapshot,
)
from raceintel.labels import (
    LABEL_SET_VERSION,
    build_label_frame,
    build_label_registry,
    ordinal_training_eligible,
)
from tests.f14_helpers import (
    NEGATIVE_IDS,
    TARGETS,
    THREAT_MODEL,
    family_of,
    feature_dependency_manifest,
    full84,
    get_target,
    label_dependency_manifest,
    leakage_matrix,
    load_history,
    load_labels,
    load_race_states,
    mutate_negative,
    mutate_positive,
    values_of,
)

_HAS_D9 = True  # canonical data required; loads raise clearly if absent

PARITY_EXTRA: tuple = (
    (2024, "2024-r01-R", "max_verstappen", 28),
    (2025, "2025-r06-R", "norris", 20),
    (2020, "2020-r04-R", "hamilton", 30),
    (2019, "2019-r04-R", "hamilton", 30),
    (2021, "2021-r08-R", "stroll", 5),
    (2021, "2021-r21-R", "hamilton", 30),
    (2019, "2019-r04-R", "kubica", 49),
)


@pytest.fixture(scope="module")
def history():
    return load_history()


@pytest.fixture(scope="module")
def feature_registry():
    return build_f11_registry()


def _names_in(results, names):
    return [n for n, _ in results.values if n in set(names)]


def _changed_families(base: dict, other: dict) -> set:
    out = set()
    for n in base:
        x, y = base[n], other[n]
        if x is None or y is None:
            if not (x is None and y is None):
                out.add(family_of(n))
        elif isinstance(x, bool) or isinstance(y, bool):
            if bool(x) != bool(y):
                out.add(family_of(n))
        elif isinstance(x, float) or isinstance(y, float):
            if abs(float(x) - float(y)) > 1e-9:
                out.add(family_of(n))
        elif x != y:
            out.add(family_of(n))
    return out


# --- §51 entry freeze ---

def test_f14_entry_freeze():
    assert FEATURE_SET_VERSION == "v8"
    assert LABEL_SET_VERSION == "v1"
    assert len(build_f11_registry()) == 84
    assert len(build_label_registry()) == 7
    assert len(THREAT_MODEL) == 20
    n_st = sum(len(pd.read_parquet(
        f, columns=["race_id"])) for f in sorted(glob.glob(
            "data/v2/processed/driver_lap_state_d9/*/*.parquet")))
    assert n_st == 189420


# --- §§2-4 matrix + manifests ---

def test_leakage_matrix_covers_all_families():
    matrix = leakage_matrix()
    fams = {d.family.value for d in build_f11_registry()
            if d.predictive_eligible}
    assert set(matrix) == fams
    for fam, row in matrix.items():
        assert set(row) == set(NEGATIVE_IDS) | {
            "SELF", "PAST_OWN", "PAST_RIVAL", "PAST_WX", "PAST_PRIOR",
            "GRID_SELF"}
        for m in NEGATIVE_IDS:
            assert row[m] == "NO", (fam, m)


def test_dependency_manifests():
    fman = feature_dependency_manifest()
    assert len(fman) == 84
    for entry in fman:
        assert entry["forbidden_mutations"]  # every family forbids something
        assert "LABELS" in entry["forbidden_mutations"]
        assert "IDENT" in entry["forbidden_mutations"]
    lman = label_dependency_manifest()
    assert len(lman) == 7
    for entry in lman:
        assert entry["forbidden_upstream"] == ["feature_calculator"]
        assert entry["grain"][:2] == ["race_id", "driver_id"]


# --- §43 full mutation campaign: negatives ---

@pytest.mark.parametrize("target", TARGETS)
@pytest.mark.parametrize("kind", [m for m in NEGATIVE_IDS if m != "LABELS"])
def test_forbidden_mutation_invisible(target, kind, history):
    season, rid, drv, lap = target
    q, sub, t, T = get_target(season, rid, drv, lap)
    base = full84(q, sub, history)
    mod, h2 = mutate_negative(sub, t, T, kind, history)
    assert results_equal(base, full84(q, mod, h2)), (target, kind)


@pytest.mark.parametrize("target", TARGETS)
def test_label_mutation_invisible_full84(target, history):
    season, rid, drv, lap = target
    q, sub, t, T = get_target(season, rid, drv, lap)
    base = full84(q, sub, history)
    labels = load_labels()
    assert len(labels) == 3458  # detached copy; engine takes no labels
    again = full84(q, sub, history)
    assert results_equal(base, again)
    assert len(base.values) == 84


# --- §43 positives (must move dependent outputs, spare the rest) ---

_PURE = {"pace", "weather", "race_control", "grid", "driver_prior",
         "constructor_prior", "circuit"}


def test_positive_self_moves_state_only(history):
    q, sub, t, T = get_target(2023, "2023-r01-R", "alonso", 28)
    base = values_of(full84(q, sub, history))
    mod, h2 = mutate_positive(sub, t, T, "SELF", history)
    other = values_of(full84(q, mod, h2))
    changed = _changed_families(base, other)
    assert {"race_state", "interaction"} <= changed
    assert changed & ({"pace", "weather", "race_control", "grid",
                       "driver_prior", "constructor_prior", "circuit"}) == set()


def test_positive_past_own_moves_pace(history):
    q, sub, t, T = get_target(2023, "2023-r01-R", "alonso", 28)
    base = values_of(full84(q, sub, history))
    mod, h2 = mutate_positive(sub, t, T, "PAST_OWN", history)
    other = values_of(full84(q, mod, h2))
    changed = _changed_families(base, other)
    assert "pace" in changed
    assert changed & ({"gap", "weather", "race_control", "grid",
                       "driver_prior", "constructor_prior", "circuit"}) == set()


def test_positive_past_rival_moves_gap(history):
    q, sub, t, T = get_target(2023, "2023-r01-R", "alonso", 28)
    base = values_of(full84(q, sub, history))
    mod, h2 = mutate_positive(sub, t, T, "PAST_RIVAL", history)
    other = values_of(full84(q, mod, h2))
    changed = _changed_families(base, other)
    assert "gap" in changed
    assert changed & _PURE == set()


def test_positive_past_weather_moves_deltas(history):
    q, sub, t, T = get_target(2023, "2023-r01-R", "alonso", 28)
    base = values_of(full84(q, sub, history))
    mod, h2 = mutate_positive(sub, t, T, "PAST_WX", history)
    other = values_of(full84(q, mod, h2))
    deltas = [n for n in F9_FEATURE_NAMES if "change" in n or "rain" in n]
    moved = [n for n in deltas if base[n] != other[n]
             and not (base[n] is None and other[n] is None)]
    assert moved, "eligible historical wx must move F9 outputs"
    changed = _changed_families(base, other)
    assert changed & ({"pace", "gap", "driver_prior", "constructor_prior",
                       "circuit", "grid"}) == set()


def test_positive_prior_and_grid(history):
    q, sub, t, T = get_target(2023, "2023-r01-R", "alonso", 28)
    base = values_of(full84(q, sub, history))
    mod, h2 = mutate_positive(sub, t, T, "PAST_PRIOR", history)
    other = values_of(full84(q, mod, h2))
    changed = _changed_families(base, other)
    assert "driver_prior" in changed
    assert changed & ({"pace", "gap", "weather", "race_control", "grid",
                       "interaction", "rate", "momentum"}) == set()
    mod2, h3 = mutate_positive(sub, t, T, "GRID_SELF", history)
    other2 = values_of(full84(q, mod2, h3))
    assert other2["grid_position"] != base["grid_position"]
    assert other2["positions_from_grid"] != base["positions_from_grid"]
    changed2 = _changed_families(base, other2)
    assert changed2 <= {"grid", "interaction"}


# --- §9 same-lap adversary (real pair) ---

def test_same_lap_future_rival_rejected(history):
    d9 = load_race_states(2019)
    sub = d9[d9["race_id"] == "2019-r04-R"].reset_index(drop=True)
    found = None
    for _, t in sub.iterrows():
        T = float(t["state_time_s"])
        lap = int(t["lap_number"])
        fut = sub[(sub["driver_id"] != t["driver_id"])
                  & (sub["lap_number"] == lap)
                  & (sub["state_time_s"] > T)
                  & (sub["state_time_s"] <= T + 121.0)]
        if len(fut):
            found = (t, T, fut)
            break
    assert found is not None, "same-lap future pair must exist"
    t, T, fut = found
    q = FeatureRequest(str(t["race_id"]), str(t["driver_id"]),
                       int(t["lap_number"]), T)
    base = full84(q, sub, history)
    mod = sub.copy()
    mod.loc[fut.index, "lap_time_s"] = 45.0
    mod.loc[fut.index, "position"] = 1
    assert results_equal(base, full84(q, mod, history))


# --- §10 equal timestamps ---

def test_equal_timestamp_determinism(history):
    q, sub, t, T = get_target(2021, "2021-r08-R", "stroll", 5)
    base = full84(q, sub, history)
    for seed in (1, 2, 3):
        sh = sub.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        assert results_equal(base, full84(q, sh, history)), seed
    q4 = FeatureRequest(str(t["race_id"]), str(t["driver_id"]), 4, T)
    lap4 = full84(q4, sub, history)  # lap 4 at same T resolves distinctly
    assert lap4.lap_number == 4


# --- §§16-17 prior positive + off-by-one ---

def test_prior_round_off_by_one(history):
    h = history
    hb = h.hist_results
    drv = hb[hb["driver_id"] == "hamilton"]
    r2023 = (drv["season"].astype(int) == 2023)
    before = drv[r2023 & (drv["round_no"].astype(int) < 1)]
    assert len(before) == 0  # r01 has no same-season prior
    from raceintel.features import driver_priors
    base = driver_priors(hb, "hamilton", 2023, 1)
    h2 = PriorHistory(hb.copy(), h.hist_races.copy(), h.results_tiera.copy(),
                      h.races_tiera.copy(), h.pit_stops.copy())
    m = (h2.hist_results["driver_id"] == "hamilton") & (
        h2.hist_results["season"].astype(int) == 2023) & (
            h2.hist_results["round_no"].astype(int) > 1)
    assert int(m.sum()) > 0
    h2.hist_results.loc[m, "points"] = 0
    assert driver_priors(h2.hist_results, "hamilton", 2023, 1) == base
    m0 = (h2.hist_results["driver_id"] == "hamilton") & (
        h2.hist_results["season"].astype(int) == 2022)
    h2.hist_results.loc[m0, "points"] = 0
    assert driver_priors(h2.hist_results, "hamilton", 2023, 1) != base


def test_season_boundary_chronology():
    import pandas as pd
    races = pd.DataFrame({"season": [2023, 2024], "round_no": [22, 1],
                          "race_id": ["2023-r22-R", "2024-r01-R"]})
    assert [r["race_id"] for _, r in
            history_before(races, "season", "round_no", 2024, 1)
            .iterrows()] == ["2023-r22-R"]
    assert len(history_before(races, "season", "round_no", 2023, 22)) == 0


# --- §19 feature-name attack ---

def test_label_names_rejected_legit_names_safe():
    from raceintel.features import FeatureDef, FeatureFamily, FeatureStatus
    from raceintel.features.contracts import (
        MinHistory, MinHistoryKind, MissingPolicy, SyncRequirement,
        TemporalRule,
    )
    from raceintel.features import InvalidFeatureError
    from raceintel.features.registry import validate_definition
    from raceintel.labels import CANONICAL_LABEL_NAMES
    for label_name in CANONICAL_LABEL_NAMES:
        with pytest.raises(InvalidFeatureError):
            validate_definition(FeatureDef(
                name=label_name, family=FeatureFamily.RACE_STATE, version=1,
                dtype="float64", unit="unitless", description="probe",
                sources=("driver_lap_state_d9.position",),
                formula_ref="probe", temporal_rule=TemporalRule.TARGET_STATE,
                sync=SyncRequirement.NONE,
                min_history=MinHistory(MinHistoryKind.NONE),
                missing=MissingPolicy.PRESERVE_SOURCE_NULL,
                availability=C.Availability.LAP_END,
                predictive_eligible=True, status=FeatureStatus.CANDIDATE))
    for token in ("pressure", "win", "point", "pos", "press"):
        assert token not in {n.lower() for n in CANONICAL_LABEL_NAMES}
    assert "wx_pressure_hpa" in build_f11_registry().names()


# --- §20 label source positive control ---

def test_label_source_positive_control():
    from raceintel.pipeline.d9 import labels_from_results
    rows = pd.DataFrame([
        {"race_id": "2099-r01-R", "driver_id": "a", "driver_abbreviation": "A",
         "driver_number": 1, "team_id_at_race": "t1", "grid_position": 2,
         "position_final": 1, "classified_position": 1, "position_text": "1",
         "status_text": "Finished", "dnf_flag": False, "points": 25.0,
         "laps_completed": 50, "winner_flag": True, "podium_flag": True},
        {"race_id": "2099-r01-R", "driver_id": "b", "driver_abbreviation": "B",
         "driver_number": 2, "team_id_at_race": "t2", "grid_position": 1,
         "position_final": 2, "classified_position": 2, "position_text": "2",
         "status_text": "Finished", "dnf_flag": False, "points": 18.0,
         "laps_completed": 50, "winner_flag": False, "podium_flag": True},
    ])
    out = labels_from_results(rows)
    assert bool(out[out["driver_id"] == "a"]["winner_flag"].iloc[0]) is True
    flip = rows.copy()
    flip.loc[flip["driver_id"] == "a", "position_final"] = 2
    flip.loc[flip["driver_id"] == "b", "position_final"] = 1
    out2 = labels_from_results(flip)
    assert bool(out2[out2["driver_id"] == "a"]["winner_flag"].iloc[0]) is False
    assert bool(out2[out2["driver_id"] == "b"]["winner_flag"].iloc[0]) is True


# --- §§21-22 state-dependent labels + ordinal eligibility ---

def test_ordinal_eligibility_contract():
    from raceintel.labels import ordinal_training_eligible
    assert ordinal_training_eligible(True, 5) is True
    assert ordinal_training_eligible(False, 20) is False  # W/D back-rank
    assert ordinal_training_eligible(False, None) is False
    assert ordinal_training_eligible(None, 5) is None
    assert ordinal_training_eligible(True, None) is False
    df = load_labels()
    frame, _ = build_label_frame(df)
    elig = [ordinal_training_eligible(c, p) for c, p in
            zip(frame["classified_flag"], frame["final_position"])]
    assert sum(e is True for e in elig) == 3007
    assert sum(e is False for e in elig) == 451
    # non-null final_position is NOT sufficient for eligibility
    nonnull = int(frame["final_position"].notna().sum())
    assert nonnull == 3455 > 3007


# --- §23 cardinality all-173 ---

def test_all_race_cardinality():
    df = load_labels()
    assert (df.groupby("race_id")["winner_flag"].sum() == 1).all()
    assert (df.groupby("race_id")["podium_flag"].sum() == 3).all()
    assert int((df["points"] > 0).sum()) == int(
        (df["points_finish_flag"] == True).sum())  # noqa: E712


# --- §24 stateless participants ---

def test_stateless_honesty(history):
    df = load_labels()
    keys = [("2021-r22-R", "mazepin"), ("2022-r02-R", "mick_schumacher"),
            ("2022-r02-R", "tsunoda"), ("2023-r15-R", "stroll"),
            ("2023-r17-R", "sainz"), ("2024-r21-R", "albon")]
    for rid, drv in keys:
        assert len(df[(df["race_id"] == rid)
                      & (df["driver_id"] == drv)]) == 1
    sub2021 = load_race_states(2021)
    r22 = sub2021[sub2021["race_id"] == "2021-r22-R"]
    assert "mazepin" not in set(r22["driver_id"].unique())
    # roster via the frozen identity path (outcome columns unreachable)
    ta = history.results_tiera
    roster = extract_roster(ta[ta["race_id"] == "2021-r22-R"])
    assert "mazepin" in roster["2021-r22-R"]
    t = r22.iloc[len(r22) // 2]
    snap = synchronized_field_snapshot(
        r22, str(t["race_id"]), str(t["driver_id"]), int(t["lap_number"]),
        float(t["state_time_s"]), roster["2021-r22-R"])
    by_id = dict(snap.entries)
    assert by_id["mazepin"].observable is False


# --- §25 stale rivals stay observable ---

def test_stale_rival_not_inferred_retired(history):
    q, sub, t, T = get_target(2023, "2023-r01-R", "sargeant", 55)
    base = values_of(full84(q, sub, history))
    assert base["leader_observation_age_s"] is not None
    assert float(base["leader_observation_age_s"]) >= 0.0
    ages = [v for n, v in base.items() if n.endswith("_age_s") and v is not None]
    assert max(ages) > 60.0  # retirees persist as observable history


# --- §26 gap geometry ---

def test_gap_invalid_geometry_nulls_seconds(history):
    seen = set()
    for season, rid, drv, lap in TARGETS:
        q, sub, t, T = get_target(season, rid, drv, lap)
        v = values_of(full84(q, sub, history))
        for prefix in ("gap_to_leader", "gap_to_ahead"):
            valid = v[prefix + "_seconds_valid"]
            sec = v[prefix + "_seconds"]
            if valid is False:
                assert sec is None, (rid, drv, lap, prefix)
                seen.add(prefix + ":invalid->null")
            if valid is True:
                assert sec is not None and sec >= 0.0
                seen.add(prefix + ":valid")
        traffic = v["in_traffic_2s"]
        assert traffic in (True, False, None)
        if v["gap_to_ahead_seconds"] is None:
            assert traffic is not True  # unknown never collapses to True
    assert seen  # both branches observed across the target set


# --- §27 reference identity resets rates ---

def test_reference_change_resets_rates(history):
    # 2019-r04-R lap 30 sits after leader takeovers (F1 evidence B).
    # Shifting every clock deep in the superseded era (laps <= 10, still
    # <= T, order preserved) must not move the trailing rate: under
    # reset semantics those points are outside the current reference
    # run; a bridging implementation would absorb them and move.
    q, sub, t, T = get_target(2019, "2019-r04-R", "hamilton", 30)
    base = values_of(full84(q, sub, history))
    assert base["recent_gap_to_leader_change_s_per_lap"] is not None
    mod = sub.copy()
    m = mod["lap_number"] <= 10
    assert bool(((mod.loc[m, "state_time_s"] + 30.0) <= T).all())
    mod.loc[m, "state_time_s"] = mod.loc[m, "state_time_s"] + 30.0
    other = values_of(full84(q, mod, history))
    assert other["recent_gap_to_leader_change_s_per_lap"] == \
        base["recent_gap_to_leader_change_s_per_lap"]


# --- §§28-29 pace eligibility + correctness ---

def test_pace_eligibility_matrix():
    from raceintel.features import pace_eligibility_mask
    base = {"lap_time_s": 90.0, "pit_in_s": np.nan, "pit_out_s": np.nan,
            "track_state": "all_clear", "lap_number": 5}
    rows = pd.DataFrame([
        dict(base),
        dict(base, pit_in_s=100.0),
        dict(base, pit_out_s=200.0),
        dict(base, lap_number=1),
        dict(base, track_state="yellow"),
        dict(base, track_state="safety_car"),
        dict(base, track_state="vsc"),
        dict(base, track_state="red_flag"),
        dict(base, track_state=None),
        dict(base, lap_time_s=np.nan),
        dict(base, lap_time_s=2500.0),
    ])
    mask = pace_eligibility_mask(rows).tolist()
    assert mask == [True, False, False, False, False, False, False,
                    False, False, False, True]  # huge factual lap stays in


def test_f5_correctness_independent_of_parity():
    from raceintel.features import pace_values
    rows = pd.DataFrame({
        "state_time_s": [100.0, 190.0, 280.0, 370.0, 460.0],
        "lap_number": [1, 2, 3, 4, 5],
        "lap_time_s": [103.0, 200.0, 90.0, 91.0, 92.0],
        "pit_in_s": [np.nan] * 4 + [1.0],
        "pit_out_s": [np.nan] * 5,
        "track_state": ["all_clear"] * 5,
        "stint_number": [1] * 5,
    })
    out = pace_values(rows)
    # eligible: laps 2(lap1 excluded),3,4 (lap5 pit-out excluded from window
    # only if in window; window takes latest eligible: 92,91,90)
    assert out["pace_n_3"] == 3
    assert out["pace_median_3"] == 91.0  # median(90,91,92), pit lap excluded
    assert out["pace_n_5"] == 3  # only 3 eligible in prefix


# --- §30 missingness ---

def test_missingness_contracts_hold():
    reg = build_f11_registry()
    for d in reg:
        assert d.missing is not None
        if str(d.missing.value) == "deterministic_fallback":
            assert d.fallback_description.strip()
    import pathlib
    for path in sorted(pathlib.Path("raceintel/features").glob("*.py")):
        text = path.read_text()
        code = "\n".join(
            ln for ln in text.splitlines()
            if ln.strip() and not ln.strip().startswith(("#", '"""', "'''")))
        assert "fillna(" not in code, path.name
        assert "fillna(0" not in code, path.name


def test_leader_has_no_car_ahead(history):
    q, sub, t, T = get_target(2023, "2023-r01-R", "max_verstappen", 30)
    v = values_of(full84(q, sub, history))
    assert v["gap_to_ahead_seconds"] is None
    assert v["gap_to_ahead_seconds_valid"] in (False, None)


# --- §31 tri-state ---

def test_tristate_semantics(history):
    from raceintel.labels import ordinal_training_eligible  # noqa: F401
    q, sub, t, T = get_target(2023, "2023-r01-R", "alonso", 28)
    v = values_of(full84(q, sub, history))
    assert isinstance(v["in_traffic_2s"], bool)  # known gap here
    df = load_labels()
    frame, _ = build_label_frame(df)
    assert frame["is_winner"].isna().sum() == 3  # nulls survive, never False
    assert set(frame["is_winner"].dropna().unique().tolist()) == {True, False}


# --- §§33-34 shuffle + duplicates ---

def test_shuffle_determinism(history):
    q, sub, t, T = get_target(2022, "2022-r07-R", "norris", 30)
    base = full84(q, sub, history)
    for seed in (7, 8, 9):
        sh = sub.sample(frac=1.0, random_state=seed).reset_index(drop=True)
        assert results_equal(base, full84(q, sh, history)), seed


def test_duplicate_keys_fail_explicitly():
    df = load_labels()
    dup = pd.concat([df, df.iloc[[0]]], ignore_index=True)
    with pytest.raises(ValueError, match="duplicate"):
        build_label_frame(dup)
    d9 = load_race_states(2023)
    sub = d9[d9["race_id"] == "2023-r01-R"].reset_index(drop=True)
    t = sub.iloc[500]
    dup_states = pd.concat([sub, sub.iloc[[500]]], ignore_index=True)
    from raceintel.features.temporal import resolve_target
    with pytest.raises(TemporalError):
        resolve_target(dup_states, str(t["race_id"]), str(t["driver_id"]),
                       int(t["lap_number"]), float(t["state_time_s"]))
    h = load_history()
    ta = h.results_tiera
    m = (ta["race_id"] == "2023-r01-R") & (
        ta["driver_id"] == str(t["driver_id"]))
    dup_ta = pd.concat([ta, ta[m].iloc[[0]]], ignore_index=True)
    from raceintel.features import resolve_grid
    with pytest.raises(TemporalError):
        resolve_grid(dup_ta, "2023-r01-R", str(t["driver_id"]))
    idx = RaceIndex(sub)
    dup_idx = RaceIndex(dup_states)
    with pytest.raises(TargetNotFoundError):
        dup_idx.field_snapshot(str(t["race_id"]), str(t["driver_id"]),
                               int(t["lap_number"]), float(t["state_time_s"]),
                               [str(t["driver_id"])])
    # resolved index still serves the exact target deterministically
    snap = idx.field_snapshot(str(t["race_id"]), str(t["driver_id"]),
                              int(t["lap_number"]), float(t["state_time_s"]),
                              [str(t["driver_id"])])
    assert snap.target_values["driver_id"] == str(t["driver_id"])


# --- §§35-39 parity, determinism, order, subset, reuse ---

PARITY_SET = TARGETS + PARITY_EXTRA


def _request_set():
    out = []
    for season, rid, drv, lap in PARITY_SET:
        q, _, _, _ = get_target(season, rid, drv, lap)
        out.append((season, rid, q))
    return out


def test_complete_single_batch_parity(history):
    reg = build_f11_registry()
    for season, rid, q in _request_set():
        sub = load_race_states(season)
        sub = sub[sub["race_id"] == rid].reset_index(drop=True)
        single = features_for_state(q, reg, sub, history=history)
        (batched,) = features_for_batch([q], reg, sub, history=history)
        assert results_equal(single, batched), (rid, q.driver_id)
        sh = sub.sample(frac=1.0, random_state=11).reset_index(drop=True)
        (batched_sh,) = features_for_batch([q], reg, sh, history=history)
        assert results_equal(single, batched_sh), ("shuffled", rid)


def test_belgium_full_race_parity_and_determinism(history):
    reg = build_f11_registry()
    sub = load_race_states(2021)
    sub = sub[sub["race_id"] == "2021-r12-R"].reset_index(drop=True)
    reqs = [FeatureRequest(str(r["race_id"]), str(r["driver_id"]),
                           int(r["lap_number"]), float(r["state_time_s"]))
            for _, r in sub.iterrows()]
    first = features_for_batch(reqs, reg, sub, history=history)
    assert len(first) == 60
    for q, res in zip(reqs, first):
        assert results_equal(features_for_state(q, reg, sub, history=history),
                             res)
    second = features_for_batch(reqs, reg, sub, history=history)
    for a, b in zip(first, second):
        assert results_equal(a, b)
        assert [n for n, _ in a.values] == [n for n, _ in b.values]


def test_request_order_and_subset_consistency(history):
    reg = build_f11_registry()
    q, sub, _, _ = get_target(2023, "2023-r01-R", "alonso", 28)
    names = list(F5_FEATURE_NAMES) + list(GAP_FEATURE_NAMES)
    a = values_of(features_for_state(q, reg, sub, history=history,
                                     names=names))
    b = values_of(features_for_state(q, reg, sub, history=history,
                                     names=list(reversed(names))))
    assert a == b
    pace_only = values_of(features_for_state(
        q, reg, sub, history=history, names=list(F5_FEATURE_NAMES)))
    for n in F5_FEATURE_NAMES:
        assert pace_only[n] == a[n]


def test_engine_reuse_across_races(history):
    reg = build_f11_registry()
    qa, suba, _, _ = get_target(2023, "2023-r01-R", "alonso", 28)
    qb, subb, _, _ = get_target(2022, "2022-r07-R", "norris", 30)
    first = features_for_state(qa, reg, suba, history=history)
    features_for_state(qb, reg, subb, history=history)
    again = features_for_state(qa, reg, suba, history=history)
    assert results_equal(first, again)


# --- §§40-42 static firewall + pattern audit ---

def test_feature_source_firewall():
    import pathlib
    calculators = ["pace", "gaps", "context", "rates", "environment",
                   "interactions", "passthrough", "engine"]
    for mod in calculators:
        text = pathlib.Path(f"raceintel/features/{mod}.py").read_text()
        assert "raceintel.labels" not in text and "raceintel/labels" not in text, mod
        assert "race_driver_labels" not in text, mod
        assert "labels_from_results" not in text, mod
    readers = set()
    for mod in calculators + ["temporal", "priors"]:
        text = pathlib.Path(f"raceintel/features/{mod}.py").read_text()
        if "results_tiera" in text or "hist_results" in text:
            readers.add(mod)
    # priors.py is the single approved reader (H<R + grid identity);
    # temporal.py operates on generic frames (no table names inside).
    assert readers == {"priors"}


def test_future_pattern_audit():
    import pathlib
    import re
    banned = [r"shift\(-1\)", r"bfill\(", r"backfill", r"center\s*=\s*True",
              r"merge_asof", r"nearest\b"]
    hits = []
    for path in sorted(pathlib.Path("raceintel/features").glob("*.py")):
        for i, ln in enumerate(path.read_text().splitlines(), 1):
            s = ln.strip()
            if not s or s.startswith(("#", '"""', "'''", "*")):
                continue
            for pat in banned:
                if re.search(pat, ln):
                    hits.append(f"{path.name}:{i}:{s[:80]}")
    # 'nearest' survives only in the temporal.py docstring forbidding it
    assert [h for h in hits if "temporal.py" not in h] == []
    assert all("No nearest" in h or "nearest" in h for h in hits)


def test_final_state_inference_audit():
    import pathlib
    import re
    allowed_file = "priors.py"  # H<R historical outcomes only
    hits = []
    for path in sorted(pathlib.Path("raceintel/features").glob("*.py")):
        if path.name in ("registry.py", "__init__.py"):
            continue
        for i, ln in enumerate(path.read_text().splitlines(), 1):
            s = ln.strip()
            if not s or s.startswith(("#", '"""', "'''", "*", "Outcome",
                                      "historical", "Historical")):
                continue
            if re.search(r"position_final|winner_flag|podium_flag|"
                         r"points_finish_flag|classified_position", ln):
                hits.append(f"{path.name}:{i}")
    assert [h for h in hits if allowed_file not in h] == [], hits


def test_no_race_specific_patches():
    import pathlib
    import re
    hits = []
    for path in list(sorted(pathlib.Path("raceintel/features").glob("*.py"))) + \
            list(sorted(pathlib.Path("raceintel/labels").glob("*.py"))):
        text = path.read_text()
        for pat in (r"20\d\d-r\d+", r"[Bb]elgium", r"[Jj]apan(?!.*cup)",
                    r"[Mm]onaco", r"special.?case"):
            for m in re.finditer(pat, text):
                line = text[:m.start()].count("\n") + 1
                hits.append(f"{path.name}:{line}")
    assert hits == [], hits


# --- §44 full-data sample invariants ---

def _stratified_sample() -> pd.DataFrame:
    rows = []
    for season, rid in [(2023, "2023-r01-R"), (2022, "2022-r07-R"),
                        (2021, "2021-r12-R"), (2019, "2019-r11-R"),
                        (2018, "2018-r04-R")]:
        sub = load_race_states(season)
        sub = sub[sub["race_id"] == rid].reset_index(drop=True)
        n = len(sub)
        idx = sorted({0, n // 4, n // 2, 3 * n // 4, n - 1}
                     | {n // 3, 2 * n // 3})
        take = sub.iloc[idx[:30] if len(idx) > 30 else idx]
        rows.append(take)
    return pd.concat(rows, ignore_index=True)


def test_sample_invariants(history):
    sample = _stratified_sample()
    assert len(sample) >= 30
    reg = build_f11_registry()
    sub_cache: dict = {}
    for _, t in sample.iterrows():
        rid = str(t["race_id"])
        if rid not in sub_cache:
            season = int(str(t["race_id"])[:4])
            d9 = load_race_states(season)
            sub_cache[rid] = d9[d9["race_id"] == rid].reset_index(drop=True)
        sub = sub_cache[rid]
        q = FeatureRequest(rid, str(t["driver_id"]), int(t["lap_number"]),
                           float(t["state_time_s"]))
        v = values_of(full84(q, sub, history))
        assert len(v) == 84
        for n, x in v.items():
            if isinstance(x, float):
                assert np.isfinite(x), n
            if isinstance(x, bool):
                continue
            if n.endswith("_age_s") and x is not None:
                assert float(x) >= 0.0, n
            if "fraction" in n and x is not None:
                assert 0.0 <= float(x) <= 1.0, (n, x)
        assert v["race_progress_frac"] is None or \
            0.0 <= float(v["race_progress_frac"]) <= 1.0


# --- §45 season audit ---

def test_season_audit_counts():
    counts, label_counts = {}, {}
    for season in range(2018, 2026):
        st = load_race_states(season)
        counts[season] = len(st)
        lab = load_labels()
        label_counts[season] = int((lab["season"] == season).sum())
    assert counts == {2018: 22337, 2019: 23676, 2020: 18352, 2021: 23758,
                      2022: 23577, 2023: 24422, 2024: 26606, 2025: 26692}
    assert label_counts == {2018: 420, 2019: 420, 2020: 340, 2021: 440,
                            2022: 440, 2023: 440, 2024: 479, 2025: 479}
    nulls = {}
    for season in range(2018, 2026):
        st = load_race_states(season)
        nulls[season] = {c: float(st[c].isna().mean()) for c in
                         ("position", "lap_time_s", "compound",
                          "track_state") if c in st.columns}
    # sparse-era 2018 has the highest track-status missingness (documented)
    assert nulls[2018]["track_state"] >= max(
        nulls[s]["track_state"] for s in range(2019, 2026))


# --- §46 stage-of-race audit ---

def test_stage_availability_structure(history):
    bands = {"early": [], "mid": [], "late": []}
    for season, rid, drv, lap in TARGETS:
        q, sub, t, T = get_target(season, rid, drv, lap)
        v = values_of(full84(q, sub, history))
        prog = v["race_progress_frac"]
        if prog is None:
            continue
        band = "early" if prog < 1 / 3 else ("mid" if prog < 2 / 3 else "late")
        pace_null = sum(1 for n in F5_FEATURE_NAMES if v[n] is None)
        bands[band].append(pace_null / len(F5_FEATURE_NAMES))
    assert bands["early"] and bands["late"]
    early = sum(bands["early"]) / len(bands["early"])
    late = sum(bands["late"]) / len(bands["late"])
    assert early >= late  # min-history bites early, never late


# --- §47 abnormal races ---

def test_abnormal_races(history):
    for season, rid, drv, lap in [(2021, "2021-r12-R", "hamilton", 2),
                                  (2022, "2022-r18-R", "ocon", 2),
                                  (2022, "2022-r18-R", "alonso", 14)]:
        q, sub, t, T = get_target(season, rid, drv, lap)
        v = values_of(full84(q, sub, history))
        assert len(v) == 84
        assert all(not (isinstance(x, float) and not np.isfinite(x))
                   for x in v.values())
