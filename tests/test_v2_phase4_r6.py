"""Phase-4 R6: performance/adversarial/integration hardening.

Focused R6 coverage only (R1-R5 suites are rerun unchanged):

- OPT-1/OPT-2 serving optimization parity: per-race slice (+contiguous
  index) inside RaceStateFeatureBridge reproduces the full-frame frozen
  engine output exactly (names/order/nulls/identities, max abs diff 0.0).
- Slice-cache mechanics on tiny synthetic frames (complete-key reuse,
  unknown-race rejection, contiguous index structural guard).
- Post-optimization frozen model-matrix parity (F15 idiom, red-flag
  fixture) and pre/post PredictionSnapshot parity (same frozen artifact,
  INDEPENDENT_BINARY, never normalized).
- End-to-end same-lap future hazard invariance through the optimized
  path (RaceState + FeatureBatch + PredictionSnapshot unchanged).
- Shared-state/reentrancy: interleaved anchors, repeated calls, and
  threaded read-only access leave shared wiring unmutated and results
  identical.
- 2025 firewall: dev-era constants, summary filtering, unknown-race
  rejection (canonical service behavior is covered by the R5 rerun).
- Import boundary: the optimized bridge still defines no feature
  formula and touches no model/sklearn machinery.

Canonical tests use DEVELOPMENT data only (2018-2024, never 2025),
never read targets, and never report quality metrics. No timing
assertions anywhere in this module (benchmarks live in
scripts/benchmark_phase4.py).
"""

import math
import threading

import pandas as pd
import pytest

from v2 import race_state as RS
from v2.config import V2Paths
from v2.race_state_features import (
    RaceStateFeatureBridge,
    RaceStateFeatureError,
    RaceStateFeatureMismatchError,
)

ROOT = V2Paths.resolve().root
_HAS_CANON = (ROOT / "data/v2/processed/driver_lap_state_d9/season=2022"
              ).is_dir()
_HAS_MATRIX = (
    ROOT / "data/v2/processed/model_matrix/matrix_version=v1"
    / "model_matrix.parquet").exists()

# Red-flag edge fixture (small enough for oracle + matrix parity at gate
# cost, sensitive enough: suspension geometry + validity companions).
RED = (2022, "2022-r18-R", "ocon", 2)


# ---------------------------------------------------------------------------
# Tiny synthetic frames: slice-cache mechanics (no engine data needed).
# ---------------------------------------------------------------------------

def _tiny_multi():
    return pd.DataFrame([
        ("R1", "a", 1, 100.0),
        ("R1", "a", 2, 200.0),
        ("R1", "b", 1, 110.0),
        ("R1", "b", 2, 205.0),
        ("R2", "a", 1, 130.0),
        ("R2", "c", 1, 140.0),
    ], columns=["race_id", "driver_id", "lap_number", "state_time_s"])


@pytest.fixture(scope="module")
def tiny_bridge():
    from v2.features.priors import PriorHistory

    empty = pd.DataFrame()
    history = PriorHistory(empty, empty, empty, empty, empty)
    return RaceStateFeatureBridge(_tiny_multi(), history)


def test_slice_contains_exact_race_rows(tiny_bridge):
    full = _tiny_multi()
    sliced = tiny_bridge._race_slice("R1")
    expected = full[full["race_id"] == "R1"]
    assert len(sliced) == len(expected) == 4
    assert sliced.reset_index(drop=True).equals(
        expected.reset_index(drop=True))
    assert set(sliced["driver_id"].unique()) == {"a", "b"}


def test_slice_cache_reuse_complete_key(tiny_bridge):
    first = tiny_bridge._race_slice("R1")
    assert tiny_bridge._race_slice("R1") is first
    other = tiny_bridge._race_slice("R2")
    assert other is not first
    assert len(other) == 2
    # Only requested races are cached (bounded, complete-key entries).
    assert set(tiny_bridge._slices) == {"R1", "R2"}


def test_slice_unknown_race_rejected(tiny_bridge):
    with pytest.raises(RaceStateFeatureMismatchError):
        tiny_bridge._race_slice("NOPE")
    assert "NOPE" not in tiny_bridge._slices


def test_slice_index_contiguous(tiny_bridge):
    sliced = tiny_bridge._race_slice("R1")
    assert list(sliced.index) == list(range(len(sliced)))


def _tiny_state(race_id="R1"):
    return RS.RaceState(
        race_id=race_id, anchor_driver_id="a", anchor_lap_number=2,
        state_time_s=200.0,
        drivers=(
            RS.DriverRaceState(
                driver_id="a", observable=True, observed_lap_number=2,
                observed_time_s=200.0, observation_age_s=0.0, position=1),
            RS.DriverRaceState(
                driver_id="b", observable=True, observed_lap_number=1,
                observed_time_s=110.0, observation_age_s=90.0, position=2),
        ),
        race_context=RS.RaceContext(), weather=RS.WeatherState(),
        race_control=RS.RaceControlState())


def test_requests_resolve_through_slice(tiny_bridge):
    requests = tiny_bridge.requests_for(_tiny_state())
    assert [r.key() for r in requests] == [
        ("R1", "a", 2, 200.0), ("R1", "b", 1, 110.0)]


def test_interleaved_anchors_stable(tiny_bridge):
    first = [r.key() for r in tiny_bridge.requests_for(_tiny_state("R1"))]
    second = [r.key() for r in tiny_bridge.requests_for(_tiny_state("R1"))]
    assert first == second
    assert set(tiny_bridge._slices) == {"R1", "R2"}


def test_threaded_read_only_access(tiny_bridge):
    errors = []

    def work():
        try:
            for _ in range(10):
                keys = [r.key() for r in
                        tiny_bridge.requests_for(_tiny_state("R1"))]
                assert keys == [("R1", "a", 2, 200.0),
                                ("R1", "b", 1, 110.0)]
                assert tiny_bridge._race_slice("R2") is not None
        except Exception as exc:  # noqa: BLE001 - collected, then raised
            errors.append(exc)

    threads = [threading.Thread(target=work) for _ in range(8)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    assert not errors
    assert set(tiny_bridge._slices) == {"R1", "R2"}


def test_no_model_or_formula_coupling():
    import ast
    import inspect

    import v2.race_state_features as bridge_mod

    tree = ast.parse(inspect.getsource(bridge_mod))
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imported.add(node.module.split(".")[0])
        elif isinstance(node, ast.Call):
            func = node.func
            name = ""
            if isinstance(func, ast.Attribute):
                name = func.attr
            elif isinstance(func, ast.Name):
                name = func.id
            assert name != "predict_proba", "bridge must never infer"
    for token in ("sklearn", "scipy", "fastapi", "ml", "model_lab"):
        assert token not in imported, token
    # Reuse, not reimplementation: the frozen engine does the math.
    assert "features_for_batch" in imported or any(
        isinstance(n, ast.ImportFrom) and "features_for_batch" in
        [a.name for a in n.names] for n in ast.walk(tree))


# ---------------------------------------------------------------------------
# 2025 firewall (synthetic + constants; canonical service rerun in R6-U).
# ---------------------------------------------------------------------------

def test_served_seasons_exclude_holdout():
    from api import v2_service as svc

    assert svc.SERVED_SEASONS == tuple(range(2018, 2025))
    assert svc.MAX_SERVED_SEASON == 2024
    assert 2025 not in svc.SERVED_SEASONS


def test_race_summaries_drop_future_season():
    import pandas as pd

    from api.v2_service import _race_summaries

    races = pd.DataFrame([
        ("2023-r01-R", 2023, 1, "Bahrain Grand Prix", "bahrain",
         "Bahrain", "Sakhir", 57),
        ("2025-r01-R", 2025, 1, "Future Grand Prix", "future",
         "Nowhere", "Null Island", 60),
    ], columns=["race_id", "season", "round_no", "event_name",
                "circuit_id", "country", "location",
                "total_laps_scheduled"])
    summaries = _race_summaries(races)
    assert [s["race_id"] for s in summaries] == ["2023-r01-R"]


def test_require_race_rejects_holdout_shape():
    from api.v2_service import V2Service
    from v2.race_state_reconstruction import RaceNotFoundError

    service = V2Service.__new__(V2Service)
    service._races = ({"race_id": "2023-r01-R", "season": 2023,
                       "round_no": 1, "event_name": "Bahrain Grand Prix",
                       "circuit_id": "bahrain", "country": "Bahrain",
                       "location": "Sakhir", "scheduled_laps": 57},)
    service._require_race("2023-r01-R")
    with pytest.raises(RaceNotFoundError):
        service._require_race("2025-r01-R")


# ---------------------------------------------------------------------------
# Canonical parity + adversarial gates (dev data only, no timing asserts).
# ---------------------------------------------------------------------------

def _load_entity(entity, seasons):
    import glob as _glob

    frames = []
    for season in seasons:
        pattern = str(ROOT / "data/v2/processed" / entity
                      / f"season={season}/*.parquet")
        for path in sorted(_glob.glob(pattern)):
            frames.append(pd.read_parquet(path))
    return pd.concat(frames, ignore_index=True)


@pytest.fixture(scope="module")
def canon():
    if not _HAS_CANON:
        pytest.skip("canonical data absent")
    from v2.features.build_matrix import load_history
    from v2.model_lab.serving import load_frozen_winner_model
    from v2.race_state_reconstruction import RaceStateReconstructor

    season, race_id, driver, lap = RED
    states = _load_entity("driver_lap_state_d9", range(2018, 2025))
    history = load_history(V2Paths.resolve())
    sub = states[states["race_id"] == race_id]
    hit = sub[(sub["driver_id"] == driver)
              & (sub["lap_number"] == lap)].iloc[0]
    roster = {race_id: sorted(sub["driver_id"].astype(str).unique())}
    recon = RaceStateReconstructor(states, roster)
    anchor = RS.AnchorObservation(
        race_id=race_id, anchor_driver_id=str(hit["driver_id"]),
        anchor_lap_number=int(hit["lap_number"]),
        anchor_state_time_s=float(hit["state_time_s"]))
    snap = recon.reconstruct(anchor)
    bridge = RaceStateFeatureBridge(states, history)
    batch = bridge.features_for_state(snap)
    predictor = load_frozen_winner_model()
    return {"states": states, "history": history, "snap": snap,
            "bridge": bridge, "batch": batch, "predictor": predictor,
            "anchor": anchor}


def _is_na(value):
    return value is None or value is pd.NA or (
        isinstance(value, float) and math.isnan(value))


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
def test_slice_vs_full_frame_oracle_parity(canon):
    """OPT-1/OPT-2 gate: sliced bridge == full-frame engine (ALL_84)."""
    from v2.features.engine import features_for_batch

    bridge, snap, batch = (canon["bridge"], canon["snap"], canon["batch"])
    assert tuple(batch.features.columns) == tuple(batch.feature_names)
    assert len(batch.feature_names) == 84
    oracle = features_for_batch(
        bridge.requests_for(snap), bridge._registry, canon["states"],
        names=list(bridge.feature_names), history=canon["history"])
    assert [i.driver_id for i in batch.identities] == [
        r.driver_id for r in oracle]
    max_abs = 0.0
    cells = 0
    null_mismatch = 0
    for identity, result, (_, row) in zip(
            batch.identities, oracle, batch.features.iterrows()):
        assert (result.race_id, result.driver_id, result.lap_number,
                result.state_time_s) == (
                    identity.race_id, identity.driver_id,
                    identity.observed_lap_number,
                    identity.observed_time_s)
        values = result.value_dict()
        assert set(values) == set(batch.feature_names)
        for name in batch.feature_names:
            expected, actual = values[name], row[name]
            cells += 1
            if _is_na(expected) or _is_na(actual):
                if _is_na(expected) != _is_na(actual):
                    null_mismatch += 1
                continue
            if isinstance(expected, bool) or isinstance(actual, bool):
                assert bool(actual) is bool(expected), name
            elif isinstance(expected, (int, float)) and isinstance(
                    actual, (int, float)):
                assert float(actual) == float(expected), name
                max_abs = max(max_abs,
                              abs(float(actual) - float(expected)))
            else:
                assert actual == expected, name
    print(f"\nR6_SLICE_PARITY: rows={len(batch)} cells={cells} "
          f"null_mismatch={null_mismatch} max_abs_diff={max_abs!r}")
    assert null_mismatch == 0
    assert max_abs == 0.0


@pytest.mark.skipif(not _HAS_CANON or not _HAS_MATRIX,
                    reason="canonical data or matrix absent")
def test_post_opt_matrix_parity(canon):
    """Post-optimization bridge rows == frozen F15 matrix rows (F15 idiom)."""
    from v2.features.build_matrix import load_matrix

    frame, manifest = load_matrix(V2Paths.resolve())
    batch = canon["batch"]
    assert list(manifest["predictive_columns"]) == list(batch.feature_names)
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
    print(f"\nR6_MATRIX_PARITY: cells={compared} "
          f"max_abs_diff={max_abs:.3e}")
    assert max_abs == 0.0


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
def test_prediction_pre_post_parity_and_determinism(canon):
    """R6-K: pre-opt oracle frame vs post-opt snapshot, same artifact."""
    from v2.features.engine import features_for_batch
    from v2.prediction import (
        PROBABILITY_SEMANTICS_NOTE,
        RacePredictionEngine,
    )

    bridge, snap, batch, predictor = (
        canon["bridge"], canon["snap"], canon["batch"],
        canon["predictor"])
    engine = RacePredictionEngine(bridge, predictor)
    post = engine.predict(snap)
    # Pre-optimization path: full-frame oracle -> same frozen predictor.
    oracle = features_for_batch(
        bridge.requests_for(snap), bridge._registry, canon["states"],
        names=list(bridge.feature_names), history=canon["history"])
    rows = [[result.value_dict()[name] for name in bridge.feature_names]
            for result in oracle]
    import pandas as _pd  # noqa: N812 - local alias, test only

    pre_frame = _pd.DataFrame(rows, columns=list(bridge.feature_names))
    pre_proba = list(predictor.predict_proba(pre_frame))
    post_proba = post.probability_by_driver()
    assert len(pre_proba) == len(post_proba) == len(batch)
    max_abs = 0.0
    for identity, raw in zip(batch.identities, pre_proba):
        assert identity.driver_id in post_proba
        diff = abs(float(raw) - float(post_proba[identity.driver_id]))
        assert diff == 0.0, identity.driver_id
        max_abs = max(max_abs, diff)
    assert post.roster_size == snap.roster_size
    assert post.observable_count == len(snap.observable_driver_ids)
    assert post.probability_semantics == "INDEPENDENT_BINARY"
    assert post.probability_semantics_note == PROBABILITY_SEMANTICS_NOTE
    assert "Do not renormalize" in post.to_dict()[
        "probability_semantics_note"]
    for entry in post.predictions:
        if entry.observable:
            assert 0.0 <= entry.winner_probability <= 1.0
        else:
            assert entry.winner_probability is None
    # Determinism / reentrancy through shared wiring.
    assert engine.predict(snap).to_dict() == post.to_dict()
    print(f"\nR6_PRED_PARITY: rows={len(batch)} max_abs_diff={max_abs!r}")


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
def test_end_to_end_same_lap_future_hazard(canon):
    """R6-L: same-lap future rival row leaves state/batch/snapshot fixed."""
    import pandas as pd

    from v2.prediction import RacePredictionEngine
    from v2.race_state_reconstruction import RaceStateReconstructor

    snap, bridge, batch, predictor = (
        canon["snap"], canon["bridge"], canon["batch"],
        canon["predictor"])
    engine = RacePredictionEngine(bridge, predictor)
    before = engine.predict(snap).to_dict()

    states = canon["states"]
    race_id = snap.race_id
    rival = snap.observable_driver_ids[0]
    rival_rows = states[(states["race_id"] == race_id)
                        & (states["driver_id"] == rival)]
    latest = rival_rows.sort_values(
        ["state_time_s", "lap_number"]).iloc[-1]
    poison = latest.copy()
    # Same-lap future observation: strictly after snapshot T.
    poison["state_time_s"] = float(snap.state_time_s) + 1.0
    mutated = pd.concat([states, poison.to_frame().T],
                        ignore_index=True)
    roster = {race_id: sorted(
        states[states["race_id"] == race_id]["driver_id"]
        .astype(str).unique().tolist())}
    recon = RaceStateReconstructor(mutated, roster)
    mutated_snap = recon.reconstruct(canon["anchor"])
    assert mutated_snap.to_dict() == snap.to_dict()
    mutated_bridge = RaceStateFeatureBridge(mutated, canon["history"])
    mutated_batch = mutated_bridge.features_for_state(mutated_snap)
    pd.testing.assert_frame_equal(mutated_batch.features, batch.features)
    assert [i.to_dict() for i in mutated_batch.identities] == [
        i.to_dict() for i in batch.identities]
    mutated_engine = RacePredictionEngine(mutated_bridge, predictor)
    assert mutated_engine.predict(mutated_snap).to_dict() == before
