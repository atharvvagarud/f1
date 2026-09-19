"""Phase-4 R3: RaceState -> frozen ALL_84 bridge.

Structural/request tests run on tiny synthetic frames (no engine data
needed); functional, parity, mutation, and matrix tests run on
canonical DEVELOPMENT data only (2019-2023 anchors; priors read strictly
H < R rows via the frozen firewall, so no 2025 influence). The bridge
never loads or runs the model.
"""

import math
import re
import subprocess
import sys
import time
from pathlib import Path

import pandas as pd
import pytest

from v2 import race_state as RS
from v2.config import V2Paths
from v2.experiments.feature_sets import EXPECTED_PREDICTIVE_FEATURE_COUNT
from v2.features.contracts import FeatureRequest
from v2.features.engine import features_for_batch, results_equal
from v2.features.interactions import build_f11_registry
from v2.features.registry import FEATURE_SET_VERSION
from v2.race_state_features import (
    FeatureBatch,
    FeatureIdentity,
    RaceStateFeatureBridge,
    RaceStateFeatureError,
    RaceStateFeatureMismatchError,
)
from v2.race_state_reconstruction import RaceStateReconstructor

ROOT = V2Paths.resolve().root
_HAS_CANON = (ROOT / "data/v2/processed/driver_lap_state_d9/season=2022"
              ).is_dir()


# ---------------------------------------------------------------------------
# Tiny synthetic frames: request mapping + mismatch paths (no engine data).
# ---------------------------------------------------------------------------

def _tiny():
    return pd.DataFrame([
        ("R", "a", 1, 100.0),
        ("R", "a", 2, 200.0),
        ("R", "b", 1, 110.0),
        ("R", "b", 2, 205.0),
    ], columns=["race_id", "driver_id", "lap_number", "state_time_s"])


def _tiny_state():
    return RS.RaceState(
        race_id="R", anchor_driver_id="a", anchor_lap_number=2,
        state_time_s=200.0,
        drivers=(
            RS.DriverRaceState(
                driver_id="a", observable=True, observed_lap_number=2,
                observed_time_s=200.0, observation_age_s=0.0, position=1),
            RS.DriverRaceState(
                driver_id="b", observable=True, observed_lap_number=1,
                observed_time_s=110.0, observation_age_s=90.0, position=2),
            RS.DriverRaceState.unobserved("c"),
        ),
        race_context=RS.RaceContext(), weather=RS.WeatherState(),
        race_control=RS.RaceControlState())


@pytest.fixture(scope="module")
def tiny_bridge():
    from v2.features.priors import PriorHistory
    empty = pd.DataFrame()
    history = PriorHistory(empty, empty, empty, empty, empty)
    return RaceStateFeatureBridge(_tiny(), history)


def test_bridge_construction_and_authority(tiny_bridge):
    assert len(tiny_bridge.feature_names) == 84
    assert EXPECTED_PREDICTIVE_FEATURE_COUNT == 84
    assert FEATURE_SET_VERSION == "v8"
    assert tuple(tiny_bridge.feature_names) == tuple(
        d.name for d in build_f11_registry() if d.predictive_eligible)
    assert len(set(tiny_bridge.feature_names)) == 84


def test_bridge_rejects_bad_inputs():
    from v2.features.priors import PriorHistory
    empty = pd.DataFrame()
    history = PriorHistory(empty, empty, empty, empty, empty)
    with pytest.raises(RaceStateFeatureError):
        RaceStateFeatureBridge("not-a-frame", history)
    with pytest.raises(RaceStateFeatureError):
        RaceStateFeatureBridge(_tiny(), None)
    with pytest.raises(RaceStateFeatureError):
        RaceStateFeatureBridge(_tiny(), history).requests_for("nope")


def test_requests_use_own_observed_lap_time(tiny_bridge):
    requests = tiny_bridge.requests_for(_tiny_state())
    assert [r.key() for r in requests] == [
        ("R", "a", 2, 200.0), ("R", "b", 1, 110.0)]
    # Stale rival keeps its own observation, never (anchor_lap, T).
    stale = requests[1]
    assert (stale.lap_number, stale.state_time_s) == (1, 110.0)
    assert isinstance(stale, FeatureRequest)


def test_unobservable_excluded(tiny_bridge):
    requests = tiny_bridge.requests_for(_tiny_state())
    assert [r.driver_id for r in requests] == ["a", "b"]


def test_unknown_race_rejected(tiny_bridge):
    state = _tiny_state()
    bad = RS.RaceState(
        race_id="NOPE", anchor_driver_id="a", anchor_lap_number=2,
        state_time_s=200.0, drivers=state.drivers,
        race_context=state.race_context, weather=state.weather,
        race_control=state.race_control)
    with pytest.raises(RaceStateFeatureMismatchError):
        tiny_bridge.requests_for(bad)


@pytest.mark.parametrize("lap,t", [(3, 200.0), (2, 200.0001), (2, 199.9999)])
def test_no_nearest_substitution(tiny_bridge, lap, t):
    anchor_entry = RS.DriverRaceState(
        driver_id="a", observable=True, observed_lap_number=lap,
        observed_time_s=t, observation_age_s=0.0, position=1)
    rival = RS.DriverRaceState(
        driver_id="b", observable=True, observed_lap_number=1,
        observed_time_s=110.0, observation_age_s=t - 110.0, position=2)
    state = RS.RaceState(
        race_id="R", anchor_driver_id="a", anchor_lap_number=lap,
        state_time_s=t,
        drivers=(anchor_entry, rival, RS.DriverRaceState.unobserved("c")),
        race_context=RS.RaceContext(), weather=RS.WeatherState(),
        race_control=RS.RaceControlState())
    with pytest.raises(RaceStateFeatureMismatchError):
        tiny_bridge.requests_for(state)


def test_stale_request_miss_rejected(tiny_bridge):
    state = _tiny_state()
    ghost = RS.DriverRaceState(
        driver_id="b", observable=True, observed_lap_number=9,
        observed_time_s=150.0, observation_age_s=50.0)
    bad = RS.RaceState(
        race_id="R", anchor_driver_id="a", anchor_lap_number=2,
        state_time_s=200.0,
        drivers=(state.drivers[0], ghost, state.drivers[2]),
        race_context=state.race_context, weather=state.weather,
        race_control=state.race_control)
    with pytest.raises(RaceStateFeatureMismatchError):
        tiny_bridge.requests_for(bad)


def test_error_taxonomy():
    assert issubclass(RaceStateFeatureMismatchError, RaceStateFeatureError)
    assert issubclass(RaceStateFeatureError, RS.RaceStateError)
    for cls in (RaceStateFeatureError, RaceStateFeatureMismatchError):
        assert "status_code" not in cls.__dict__


# ---------------------------------------------------------------------------
# Canonical dev fixtures (functional + parity + mutation + matrix).
# ---------------------------------------------------------------------------

def _season_frame(season, entity):
    import glob as _g
    files = sorted(_g.glob(str(ROOT / "data/v2/processed" / entity
                               / f"season={season}/*.parquet")))
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


@pytest.fixture(scope="module")
def history():
    if not _HAS_CANON:
        pytest.skip("canonical data absent")
    from v2.features.build_matrix import load_history
    return load_history(V2Paths.resolve())


@pytest.fixture(scope="module")
def matrix():
    if not _HAS_CANON:
        pytest.skip("canonical data absent")
    from v2.features.build_matrix import load_matrix
    frame, manifest = load_matrix(V2Paths.resolve())
    return frame, manifest


def _is_na(value) -> bool:
    return value is None or value is pd.NA or (
        isinstance(value, float) and math.isnan(value))


def _dev_snapshot(season, race_id, driver, lap):
    d9 = _season_frame(season, "driver_lap_state_d9")
    results = _season_frame(season, "results")
    races = _season_frame(season, "races")
    race_meta = {
        str(row["race_id"]): {
            "scheduled_laps": (None if pd.isna(
                row["total_laps_scheduled"]) else int(
                row["total_laps_scheduled"]))}
        for _, row in races.iterrows()
    }
    sub = d9[d9["race_id"] == race_id].reset_index(drop=True)
    hit = sub[(sub["driver_id"] == driver)
              & (sub["lap_number"] == lap)].iloc[0]
    anchor = RS.AnchorObservation(
        race_id=race_id, anchor_driver_id=str(hit["driver_id"]),
        anchor_lap_number=int(hit["lap_number"]),
        anchor_state_time_s=float(hit["state_time_s"]))
    snap = RaceStateReconstructor(sub, results,
                                  race_meta=race_meta).reconstruct(anchor)
    return snap, sub


def _dev_bridge(sub, history):
    return RaceStateFeatureBridge(sub, history)


# Representative dev anchors: ordinary/stale, partial, red, full field.
ANCHORS = [
    (2022, "2022-r07-R", "norris", 30),
    (2021, "2021-r12-R", "hamilton", 2),
    (2022, "2022-r18-R", "ocon", 2),
    (2023, "2023-r01-R", "alonso", 28),
]


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
@pytest.mark.parametrize("season,race_id,driver,lap", ANCHORS)
def test_batch_shape_order_alignment(season, race_id, driver, lap,
                                     history):
    snap, sub = _dev_snapshot(season, race_id, driver, lap)
    batch = _dev_bridge(sub, history).features_for_state(snap)
    assert isinstance(batch, FeatureBatch)
    assert tuple(batch.features.columns) == tuple(batch.feature_names)
    assert len(batch.feature_names) == 84
    assert len(batch) == len(snap.observable_drivers) > 0
    assert batch.driver_ids == snap.observable_driver_ids
    assert all(isinstance(i, FeatureIdentity) for i in batch.identities)
    # Positional alignment contract: default RangeIndex, identities[i]
    # describes features.iloc[i].
    assert list(batch.features.index) == list(range(len(batch)))
    assert [i.to_dict() for i in batch.identities] == [
        {"race_id": snap.race_id, "driver_id": d.driver_id,
         "observed_lap_number": d.observed_lap_number,
         "observed_time_s": d.observed_time_s}
        for d in snap.observable_drivers]
    # No identity/label/metadata columns inside the feature frame.
    assert set(batch.features.columns) == set(batch.feature_names)
    for col in ("race_id", "driver_id", "lap_number", "state_time_s",
                "is_winner", "final_position"):
        assert col not in batch.features.columns


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
@pytest.mark.parametrize("season,race_id,driver,lap", ANCHORS)
def test_direct_engine_parity(season, race_id, driver, lap, history):
    """Bridge frame == direct features_for_batch oracle (all 84)."""
    from v2.features.engine import PARITY_ABS_TOL, PARITY_REL_TOL
    snap, sub = _dev_snapshot(season, race_id, driver, lap)
    bridge = _dev_bridge(sub, history)
    batch = bridge.features_for_state(snap)
    requests = bridge.requests_for(snap)
    oracle = features_for_batch(requests, bridge._registry, sub,
                                names=list(bridge.feature_names),
                                history=history)
    assert len(oracle) == len(batch)
    max_abs = 0.0
    for identity, result, (_, row) in zip(batch.identities, oracle,
                                          batch.features.iterrows()):
        assert (result.race_id, result.driver_id) == \
            (identity.race_id, identity.driver_id)
        values = result.value_dict()
        assert set(values) == set(batch.feature_names)
        for name in batch.feature_names:
            expected, actual = values[name], row[name]
            if expected is None or (
                    isinstance(expected, float) and math.isnan(expected)):
                assert actual is None or (
                    isinstance(actual, float) and math.isnan(actual)), name
            elif isinstance(expected, bool) or isinstance(actual, bool):
                assert bool(actual) is bool(expected), name
            elif isinstance(expected, (int, float)) and isinstance(
                    actual, (int, float)):
                assert math.isclose(float(actual), float(expected),
                                    rel_tol=PARITY_REL_TOL,
                                    abs_tol=PARITY_ABS_TOL), name
                max_abs = max(max_abs, abs(float(actual)
                                           - float(expected)))
            else:
                assert actual == expected, name
    print(f"\nPARITY {race_id} {driver} lap{lap}: rows={len(batch)} "
          f"max_abs_diff={max_abs:.3e}")


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
def test_family_grouped_parity(history):
    """Per-family column subsets (pace/gap/context/rate/env/prior/inter)."""
    season, race_id, driver, lap = ANCHORS[0]
    snap, sub = _dev_snapshot(season, race_id, driver, lap)
    bridge = _dev_bridge(sub, history)
    batch = bridge.features_for_state(snap)
    requests = bridge.requests_for(snap)
    oracle = features_for_batch(requests, bridge._registry, sub,
                                names=list(bridge.feature_names),
                                history=history)
    families: dict = {}
    for definition in bridge._registry:
        if definition.predictive_eligible:
            families.setdefault(definition.family.value, []).append(
                definition.name)
    assert len(families) >= 7
    oracle_rows = [result.value_dict() for result in oracle]
    for family, names in sorted(families.items()):
        for row, orow in zip(batch.features.itertuples(index=False),
                             oracle_rows):
            actual = dict(zip(batch.feature_names, row))
            for name in names:
                expected = orow[name]
                value = actual[name]
                if expected is None:
                    assert value is None or (
                        isinstance(value, float)
                        and math.isnan(value)), (family, name)
                elif isinstance(expected, float):
                    assert math.isclose(float(value), expected,
                                        rel_tol=1e-9,
                                        abs_tol=1e-12), (family, name)
                else:
                    assert (value == expected or
                            (isinstance(value, float)
                             and value == expected)), (family, name)


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
@pytest.mark.parametrize("season,race_id,driver,lap", ANCHORS)
def test_matrix_parity(season, race_id, driver, lap, history, matrix):
    """Bridge ALL_84 == frozen model-matrix rows (F15 parity idiom)."""
    frame, manifest = matrix
    snap, sub = _dev_snapshot(season, race_id, driver, lap)
    batch = _dev_bridge(sub, history).features_for_state(snap)
    assert list(manifest["predictive_columns"]) == list(
        batch.feature_names)
    max_abs = 0.0
    compared = 0
    for identity in batch.identities:
        hit = frame[(frame["race_id"] == identity.race_id)
                    & (frame["driver_id"] == identity.driver_id)
                    & (frame["lap_number"]
                       == identity.observed_lap_number)]
        hit = hit[hit["state_time_s"] == identity.observed_time_s]
        assert len(hit) == 1, (identity, "matrix identity missing/dup")
        row = batch.features.iloc[
            batch.driver_ids.index(identity.driver_id)]
        for name in batch.feature_names:
            expected, actual = hit.iloc[0][name], row[name]
            if _is_na(expected):
                assert _is_na(actual), (identity.driver_id, name)
            elif isinstance(expected, bool):
                assert bool(actual) is bool(expected), name
            elif isinstance(expected, (int, float)) and isinstance(
                    actual, (int, float)):
                assert math.isclose(float(actual), float(expected),
                                    rel_tol=1e-9, abs_tol=1e-12), \
                    (identity.driver_id, name, expected, actual)
                max_abs = max(max_abs, abs(float(actual)
                                           - float(expected)))
            else:
                assert actual == expected, (identity.driver_id, name)
            compared += 1
    print(f"\nMATRIX {race_id} {driver} lap{lap}: cells={compared} "
          f"max_abs_diff={max_abs:.3e}")


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
def test_stale_driver_own_identity(history):
    """Stale rival requested at its own (lap, time); T-use would fail."""
    season, race_id, driver, lap = ANCHORS[0]
    snap, sub = _dev_snapshot(season, race_id, driver, lap)
    stale = [d for d in snap.observable_drivers
             if d.observation_age_s and d.observation_age_s > 0]
    assert stale, "fixture has no stale rival"
    bridge = _dev_bridge(sub, history)
    keys = {r.driver_id: r.key() for r in bridge.requests_for(snap)}
    for entry in stale:
        assert keys[entry.driver_id] == (
            race_id, entry.driver_id, entry.observed_lap_number,
            entry.observed_time_s)
        assert (entry.observed_lap_number, entry.observed_time_s) != (
            snap.anchor_lap_number, snap.state_time_s)
        # Same row as direct Phase-2 evaluation at the own identity.
        direct = features_for_batch(
            [FeatureRequest(race_id, entry.driver_id,
                            entry.observed_lap_number,
                            entry.observed_time_s)],
            bridge._registry, sub, names=list(bridge.feature_names),
            history=history)[0]
        batch = bridge.features_for_state(snap)
        row = batch.features.iloc[
            batch.driver_ids.index(entry.driver_id)]
        for name in batch.feature_names:
            expected, actual = direct.value_dict()[name], row[name]
            if expected is None:
                assert actual is None or (
                    isinstance(actual, float)
                    and math.isnan(actual)), name
            elif isinstance(expected, float):
                assert math.isclose(float(actual), expected,
                                    rel_tol=1e-9, abs_tol=1e-12), name
            else:
                assert actual == expected or float(actual) == expected, \
                    name


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
def test_same_lap_future_hazard(history):
    """Same-lap later rival row must not reach any feature."""
    season, race_id, driver, lap = ANCHORS[0]
    snap, sub = _dev_snapshot(season, race_id, driver, lap)
    bridge = _dev_bridge(sub, history)
    before = bridge.features_for_state(snap).features
    # Hazard injection: duplicate a rival's synced row one second later
    # with the SAME lap number (Bahrain-style same-lap spread).
    rival_id = next(d.driver_id for d in snap.observable_drivers
                    if d.driver_id != snap.anchor_driver_id)
    synced = next(d for d in snap.observable_drivers
                  if d.driver_id == rival_id)
    donor = sub[(sub["driver_id"] == rival_id)
                & (sub["lap_number"] == synced.observed_lap_number)
                & (sub["state_time_s"] == synced.observed_time_s)].iloc[0]
    hazard = donor.copy()
    hazard["state_time_s"] = float(snap.state_time_s) + 1.0
    poisoned = pd.concat([sub, pd.DataFrame([hazard])], ignore_index=True)
    after = RaceStateFeatureBridge(
        poisoned, history).features_for_state(snap).features
    pd.testing.assert_frame_equal(before, after)


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
@pytest.mark.parametrize("mutate", [
    "future_driver", "future_weather", "future_race_control", "future_pit",
    "label_columns", "status_columns", "unrelated_race",
])
def test_future_mutation_invariance(history, mutate):
    season, race_id, driver, lap = ANCHORS[0]
    snap, sub = _dev_snapshot(season, race_id, driver, lap)
    bridge = _dev_bridge(sub, history)
    before = bridge.features_for_state(snap).features
    mutated = sub.copy()
    future = mutated["state_time_s"] > snap.state_time_s
    if mutate == "future_driver":
        mutated.loc[future, "position"] = 1
    elif mutate == "future_weather":
        mutated.loc[future, "wx_air_temp_c"] = -99.0
    elif mutate == "future_race_control":
        mutated.loc[future, "rc_last_message_category"] = "RedFlag"
    elif mutate == "future_pit":
        mutated.loc[future, "pit_stops_completed_so_far"] = 9
    elif mutate == "label_columns":
        mutated["is_winner"] = mutated["driver_id"] == driver
        mutated["final_position"] = 1
    elif mutate == "status_columns":
        mutated["status_text"] = "Finished"
        mutated["classified_position"] = 1
    elif mutate == "unrelated_race":
        other = mutated[mutated["race_id"] != race_id].head(5).copy()
        other["race_id"] = "RX-999"
        mutated = pd.concat([mutated, other], ignore_index=True)
    after = RaceStateFeatureBridge(
        mutated, history).features_for_state(snap).features
    pd.testing.assert_frame_equal(before, after)


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
def test_determinism_and_shuffle(history):
    season, race_id, driver, lap = ANCHORS[0]
    snap, sub = _dev_snapshot(season, race_id, driver, lap)
    bridge = _dev_bridge(sub, history)
    first = bridge.features_for_state(snap)
    again = bridge.features_for_state(snap)
    pd.testing.assert_frame_equal(first.features, again.features)
    assert first.identities == again.identities
    shuffled = sub.sample(frac=1.0, random_state=7).reset_index(drop=True)
    third = RaceStateFeatureBridge(
        shuffled, history).features_for_state(snap)
    pd.testing.assert_frame_equal(first.features, third.features)
    assert [i.to_dict() for i in first.identities] == [
        i.to_dict() for i in third.identities]


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
def test_feature_firewall(history):
    season, race_id, driver, lap = ANCHORS[0]
    snap, sub = _dev_snapshot(season, race_id, driver, lap)
    batch = _dev_bridge(sub, history).features_for_state(snap)
    assert set(batch.features.columns) == set(batch.feature_names)
    assert set(batch.features.columns) & RS.label_outcome_fields() == set()


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
def test_performance_observation(history):
    season, race_id, driver, lap = (2023, "2023-r01-R", "alonso", 28)
    snap, sub = _dev_snapshot(season, race_id, driver, lap)
    bridge = _dev_bridge(sub, history)
    started = time.perf_counter()
    requests = bridge.requests_for(snap)
    t_requests = (time.perf_counter() - started) * 1000.0
    started = time.perf_counter()
    batch = bridge.features_for_state(snap)
    t_total = (time.perf_counter() - started) * 1000.0
    print(f"\nPERF {race_id}: drivers={len(batch)} "
          f"requests_ms={t_requests:.1f} total_ms={t_total:.1f}")
    assert len(batch) > 0


# ---------------------------------------------------------------------------
# Architecture guards.
# ---------------------------------------------------------------------------

def test_no_model_coupling_in_source():
    source = Path(__file__).resolve().parent.parent \
        / "v2/race_state_features.py"
    text = source.read_text()
    imported = set()
    for line in text.splitlines():
        match = re.match(r"\s*(?:from|import)\s+([\w.]+)", line)
        if match:
            imported.add(match.group(1))
    for module in sorted(imported):
        for banned in ("v2.model_lab", "ml", "api", "v2.labels", "sklearn",
                       "scipy", "fastapi", "pydantic"):
            assert not (module == banned
                        or module.startswith(banned + ".")), \
                f"banned import: {module}"
    for banned in ("predict_proba(", "load_frozen_winner_model(",
                   "HTTPException", "2025"):
        assert banned not in text, banned
    # ALL_84 must come from frozen authority, never a hand list.
    assert 'resolve_feature_set("ALL_84"' in text


def test_no_model_imports_at_runtime():
    probe = ("import sys, v2.race_state_features as B; "
             "banned = [m for m in sys.modules if m.split('.')[0] in "
             "('sklearn', 'scipy', 'fastapi', 'pydantic', 'torch') or "
             "m.startswith(('v2.model_lab', 'ml.', 'api.'))]; "
             "print(','.join(sorted(banned))); "
             "builder = sys.modules.get('v2.labels.builder'); "
             "refs = [k for k, v in vars(B).items() "
             "if getattr(v, '__module__', None) == 'v2.labels.builder']; "
             "print('BUILDER_REFS:' + ','.join(sorted(refs)))")
    out = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True,
        cwd=str(Path(__file__).resolve().parent.parent), timeout=180)
    assert out.returncode == 0, out.stderr
    lines = out.stdout.splitlines()
    assert lines[0] == "", f"heavy imports: {lines[0]}"
    # v2.labels package __init__ (frozen) imports builder as a side
    # effect of the contracts name-guard; the bridge itself must hold
    # no reference to label values.
    assert lines[1] == "BUILDER_REFS:", f"label value refs: {lines[1]}"
