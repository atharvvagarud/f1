"""Phase-4 R4: frozen batch prediction engine.

Synthetic contract tests use a fake bridge + fake predictor (no data,
no model). Canonical smoke/parity/mutation/performance tests use
DEVELOPMENT data only (2019-2023 anchors) and the real P3.1 serving
artifact; they never read targets and never report quality metrics.
"""

import json
import math
import re
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import pandas as pd
import pytest

from v2 import race_state as RS
from v2.config import V2Paths
from v2.model_lab import serving as SERVING
from v2.prediction import (
    NO_OBSERVATION_AT_SNAPSHOT,
    PROBABILITY_SEMANTICS,
    PROBABILITY_SEMANTICS_NOTE,
    DriverPrediction,
    ModelIdentity,
    PredictionAlignmentError,
    PredictionEngineError,
    PredictionFeatureMismatchError,
    PredictionOutputError,
    PredictionSnapshot,
    ProductionModelUnavailableError,
    RacePredictionEngine,
    load_production_prediction_engine,
)
from v2.race_state_features import FeatureIdentity
from v2.race_state_reconstruction import RaceStateReconstructor

ROOT = V2Paths.resolve().root
SOURCE = ROOT / "v2/prediction.py"
_HAS_CANON = (ROOT / "data/v2/processed/driver_lap_state_d9/season=2022"
              ).is_dir()

FAKE_NAMES = ("f1", "f2", "f3")


def _identity(**over):
    params = {"task": "winner", "target": "is_winner",
              "eligibility_mask": "eligible_is_winner",
              "feature_set": "ALL_84", "feature_set_version": "v8",
              "estimator": "LogisticRegression",
              "estimator_params": (("C", 0.01),),
              "calibration_method": "RAW",
              "probability_semantics": "INDEPENDENT_BINARY",
              "training_seasons": (2018, 2019),
              "transformed_dim": 2, "feature_count": 3,
              "artifact_sha256": "test-sha",
              "specification_fingerprint": "test-fp",
              "sklearn_version": "1.8.0"}
    params.update(over)
    return ModelIdentity(**params)


class FakePredictor:
    """Stub serving predictor with call counting."""

    def __init__(self, names=FAKE_NAMES, values=(0.5, 0.25)):
        self.feature_names = tuple(names)
        self._values = list(values)
        self.calls = 0

    def predict_proba(self, frame):
        self.calls += 1
        assert tuple(frame.columns) == self.feature_names
        return np.array(self._values, dtype=float)


class FakeBridge:
    """Stub feature bridge building batches from the RaceState roster."""

    def __init__(self, names=FAKE_NAMES, drop=(), extra=(), duplicate=False):
        self.feature_names = tuple(names)
        self.calls = 0
        self._drop = set(drop)
        self._extra = tuple(extra)
        self._duplicate = duplicate

    def features_for_state(self, race_state):
        self.calls += 1
        rows, identities = [], []
        for entry in race_state.observable_drivers:
            if entry.driver_id in self._drop:
                continue
            rows.append([1.0] * len(self.feature_names))
            identities.append(FeatureIdentity(
                race_id=race_state.race_id, driver_id=entry.driver_id,
                observed_lap_number=entry.observed_lap_number,
                observed_time_s=entry.observed_time_s))
        for driver_id in self._extra:
            rows.append([1.0] * len(self.feature_names))
            identities.append(FeatureIdentity(
                race_id=race_state.race_id, driver_id=driver_id,
                observed_lap_number=1, observed_time_s=10.0))
        if self._duplicate and identities:
            identities.append(identities[0])
            rows.append(rows[0])
        frame = pd.DataFrame(rows, columns=list(self.feature_names))
        return SimpleNamespace(
            race_id=race_state.race_id, identities=tuple(identities),
            features=frame, feature_names=tuple(self.feature_names))


def _driver(driver_id, lap, t, age, position=1):
    return RS.DriverRaceState(
        driver_id=driver_id, observable=True, observed_lap_number=lap,
        observed_time_s=t, observation_age_s=age, position=position)


def _synth_state(obs=("a", "b")):
    entries = []
    if "a" in obs:
        entries.append(_driver("a", 2, 200.0, 0.0, position=1))
    if "b" in obs:
        entries.append(_driver("b", 1, 110.0, 90.0, position=2))
    if "d" in obs:
        entries.append(_driver("d", 2, 198.0, 2.0, position=3))
    entries.append(RS.DriverRaceState.unobserved("c"))
    return RS.RaceState(
        race_id="R", anchor_driver_id="a", anchor_lap_number=2,
        state_time_s=200.0, drivers=tuple(entries),
        race_context=RS.RaceContext(), weather=RS.WeatherState(),
        race_control=RS.RaceControlState())


def _engine(bridge=None, predictor=None, values=(0.5, 0.25)):
    return RacePredictionEngine(
        bridge or FakeBridge(), predictor or FakePredictor(values=values),
        _identity())


# --- domain types ------------------------------------------------------------


def test_model_identity_serialization():
    identity = _identity()
    payload = identity.to_dict()
    assert payload["task"] == "winner"
    assert payload["target"] == "is_winner"
    assert payload["probability_semantics"] == "INDEPENDENT_BINARY"
    assert payload["feature_set"] == "ALL_84"
    assert json.loads(json.dumps(payload)) == payload
    assert identity.probability_semantics == PROBABILITY_SEMANTICS
    with pytest.raises(PredictionEngineError):
        _identity(probability_semantics="CATEGORICAL")


def test_driver_prediction_observable():
    entry = DriverPrediction(
        driver_id="a", observable=True, observed_lap_number=2,
        observed_time_s=200.0, observation_age_s=0.0, observed_position=1,
        winner_probability=0.42, unavailable_reason=None)
    assert entry.winner_probability == 0.42
    assert entry.unavailable_reason is None
    assert entry.to_dict()["winner_probability"] == 0.42


def test_driver_prediction_unavailable():
    entry = DriverPrediction(
        driver_id="c", observable=False,
        unavailable_reason=NO_OBSERVATION_AT_SNAPSHOT)
    assert entry.winner_probability is None
    assert entry.unavailable_reason == NO_OBSERVATION_AT_SNAPSHOT
    with pytest.raises(PredictionEngineError):
        DriverPrediction(driver_id="c", observable=False,
                         winner_probability=0.0,
                         unavailable_reason=NO_OBSERVATION_AT_SNAPSHOT)
    with pytest.raises(PredictionEngineError):
        DriverPrediction(driver_id="c", observable=False,
                         unavailable_reason=None)


def test_snapshot_deterministic_ordering():
    snap = _engine().predict(_synth_state())
    assert [e.driver_id for e in snap.predictions] == ["a", "b", "c"]
    shuffled = PredictionSnapshot(
        race_id=snap.race_id, anchor_driver_id=snap.anchor_driver_id,
        anchor_lap_number=snap.anchor_lap_number,
        state_time_s=snap.state_time_s, model=snap.model,
        predictions=tuple(reversed(snap.predictions)))
    assert [e.driver_id for e in shuffled.predictions] == ["a", "b", "c"]
    assert shuffled.to_dict() == snap.to_dict()


def test_complete_roster_merge():
    state = _synth_state()
    snap = _engine().predict(state)
    assert snap.roster_size == 3 == state.roster_size
    assert [e.driver_id for e in snap.predictions] == list(
        state.roster_driver_ids)
    assert snap.observable_count == 2
    assert snap.unavailable_count == 1


def test_unobservable_none_and_reason():
    snap = _engine().predict(_synth_state())
    entry = next(e for e in snap.predictions if e.driver_id == "c")
    assert entry.observable is False
    assert entry.winner_probability is None
    assert entry.unavailable_reason == NO_OBSERVATION_AT_SNAPSHOT


# --- batch execution ---------------------------------------------------------


def test_exactly_one_bridge_and_predictor_call():
    bridge, predictor = FakeBridge(), FakePredictor(values=(0.5, 0.25))
    snap = RacePredictionEngine(bridge, predictor, _identity()).predict(
        _synth_state())
    assert bridge.calls == 1
    assert predictor.calls == 1
    assert snap.observable_count == 2


def test_exact_feature_order_accepted():
    snap = _engine().predict(_synth_state())
    assert snap.probability_by_driver() == {"a": 0.5, "b": 0.25}


def test_feature_order_mismatch_rejected():
    bridge = FakeBridge(names=("f3", "f2", "f1"))
    engine = RacePredictionEngine(bridge, FakePredictor(), _identity())
    with pytest.raises(PredictionFeatureMismatchError):
        engine.predict(_synth_state())


def test_output_length_mismatch():
    engine = _engine(predictor=FakePredictor(values=(0.5, 0.25, 0.9)))
    with pytest.raises(PredictionAlignmentError):
        engine.predict(_synth_state())


def test_duplicate_identity_rejected():
    engine = _engine(bridge=FakeBridge(duplicate=True))
    with pytest.raises(PredictionAlignmentError):
        engine.predict(_synth_state())


def test_unknown_driver_identity_rejected():
    engine = _engine(bridge=FakeBridge(extra=("zzz",)))
    with pytest.raises(PredictionAlignmentError):
        engine.predict(_synth_state())


def test_missing_observable_driver_rejected():
    engine = _engine(bridge=FakeBridge(drop=("b",)))
    with pytest.raises(PredictionAlignmentError):
        engine.predict(_synth_state())


def test_unobservable_feature_row_rejected():
    engine = _engine(bridge=FakeBridge(extra=("c",)))
    with pytest.raises(PredictionAlignmentError):
        engine.predict(_synth_state())


@pytest.mark.parametrize("values", [
    (float("nan"), 0.25), (float("inf"), 0.25), (float("-inf"), 0.25),
    (-0.01, 0.25), (1.01, 0.25), (0.5, -0.5), (0.5, 2.0)])
def test_invalid_probabilities_rejected(values):
    engine = _engine(predictor=FakePredictor(values=values))
    with pytest.raises((PredictionOutputError, PredictionAlignmentError)):
        engine.predict(_synth_state())


def test_no_normalization_sum_above_one():
    # Spec example: [0.60, 0.35, 0.20], sum = 1.15, preserved exactly.
    engine = _engine(predictor=FakePredictor(values=(0.60, 0.35, 0.20)))
    snap = engine.predict(_synth_state(obs=("a", "b", "d")))
    probs = snap.probability_by_driver()
    assert probs == {"a": 0.60, "b": 0.35, "d": 0.20}
    assert abs(sum(probs.values()) - 1.15) < 1e-12


def test_no_normalization_sum_below_one():
    engine = _engine(predictor=FakePredictor(values=(0.10, 0.05, 0.02)))
    snap = engine.predict(_synth_state(obs=("a", "b", "d")))
    probs = snap.probability_by_driver()
    assert probs == {"a": 0.10, "b": 0.05, "d": 0.02}
    assert sum(probs.values()) < 1.0


def test_independent_binary_semantics_pinned():
    assert PROBABILITY_SEMANTICS == "INDEPENDENT_BINARY"
    assert "do not sum to 1" in PROBABILITY_SEMANTICS_NOTE.lower() \
        or "do not sum to 1" in PROBABILITY_SEMANTICS_NOTE
    snap = _engine().predict(_synth_state())
    assert snap.probability_semantics == "INDEPENDENT_BINARY"
    assert snap.model.probability_semantics == "INDEPENDENT_BINARY"
    assert snap.to_dict()["probability_semantics"] == "INDEPENDENT_BINARY"
    assert SERVING.describe_serving_artifact()[  # artifact anchor
        "probability_semantics"] == "INDEPENDENT_BINARY"


def test_repeated_inference_deterministic():
    engine = _engine()
    state = _synth_state()
    assert engine.predict(state).to_dict() == \
        engine.predict(state).to_dict()


def test_deterministic_serialization():
    snap = _engine().predict(_synth_state())
    first = json.dumps(snap.to_dict(), sort_keys=True)
    again = json.dumps(snap.to_dict(), sort_keys=True)
    assert first == again
    assert "NaN" not in first and "Infinity" not in first


def test_no_model_features_in_domain_result():
    snap = _engine().predict(_synth_state())
    text = json.dumps(snap.to_dict())
    for name in FAKE_NAMES:
        assert f'"{name}"' not in text
    assert "coef" not in text and "preprocessor" not in text


def test_no_labels_in_domain_result():
    snap = _engine().predict(_synth_state())
    payload = snap.to_dict()

    def _keys(node, acc):
        if isinstance(node, dict):
            for key, value in node.items():
                acc.add(key)
                _keys(value, acc)
        elif isinstance(node, list):
            for value in node:
                _keys(value, acc)
        return acc

    assert _keys(payload, set()) & RS.label_outcome_fields() == set()


def test_error_taxonomy():
    assert issubclass(PredictionFeatureMismatchError, PredictionEngineError)
    assert issubclass(PredictionAlignmentError, PredictionEngineError)
    assert issubclass(PredictionOutputError, PredictionEngineError)
    assert issubclass(ProductionModelUnavailableError, PredictionEngineError)
    assert issubclass(PredictionEngineError, RS.RaceStateError)
    for cls in (PredictionEngineError, PredictionFeatureMismatchError,
                PredictionAlignmentError, PredictionOutputError,
                ProductionModelUnavailableError):
        assert "status_code" not in cls.__dict__


# --- architecture guards -----------------------------------------------------


def test_architecture_import_guard():
    text = SOURCE.read_text()
    lines = [line.strip() for line in text.splitlines()
             if re.match(r"\s*(?:from|import)\s+([\w.]+)", line)]
    assert any("v2.model_lab" in line and "serving" in line for line in lines), \
        "must use the narrow v2.model_lab.serving production path"
    for line in lines:
        if "v2.model_lab" in line:
            assert line == "from v2.model_lab import serving as SERVING", \
                f"only the narrow serving import is allowed: {line}"
    for banned in ("final_fit", "tuning", "splits", "calibration_selection",
                   "evaluate", "holdout", "experiment", "M7", "M8", "M9",
                   "HTTPException", "fastapi", "pydantic", "ml.", "api.",
                   "LogisticRegression", "joblib.load", "2025"):
        assert banned not in text, banned


def test_no_fit_or_estimator_construction():
    text = SOURCE.read_text()
    assert ".fit(" not in text
    assert "LogisticRegression(" not in text


def test_no_training_path_at_runtime():
    # P3.1 precedent: the sanctioned serving import itself transitively
    # pulls frozen feature-resolution modules (data/splits/experiments);
    # the fitting/evaluation stack must stay out.
    probe = ("import sys, v2.prediction as P; "
             "banned = ('v2.model_lab.runner', 'v2.model_lab.tuning', "
             "'v2.model_lab.final_fit', 'v2.model_lab.run_final', "
             "'v2.model_lab.run_calibration', "
             "'v2.model_lab.calibration_selection', "
             "'v2.model_lab.model_runner'); "
             "hit = [m for m in sys.modules if m in banned]; "
             "extra = [m for m in sys.modules if m.startswith("
             "('ml.', 'api.'))]; "
             "print(','.join(sorted(hit + extra)))")
    out = subprocess.run(
        [sys.executable, "-c", probe], capture_output=True, text=True,
        cwd=str(ROOT), timeout=180)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "", f"training path: {out.stdout.strip()}"


# --- canonical production tests (development data only) ----------------------


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
def predictor():
    try:
        return SERVING.load_frozen_winner_model()
    except Exception as exc:
        pytest.skip(f"serving artifact unavailable: {exc}")


def _dev_engine(season, race_id, driver, lap, history, predictor):
    from v2.race_state_features import RaceStateFeatureBridge
    d9 = _season_frame(season, "driver_lap_state_d9")
    results = _season_frame(season, "results")
    races = _season_frame(season, "races")
    race_meta = {
        str(row["race_id"]): {
            "scheduled_laps": (None if pd.isna(
                row["total_laps_scheduled"]) else int(
                row["total_laps_scheduled"]))}
        for _, row in races.iterrows()}
    sub = d9[d9["race_id"] == race_id].reset_index(drop=True)
    hit = sub[(sub["driver_id"] == driver)
              & (sub["lap_number"] == lap)].iloc[0]
    anchor = RS.AnchorObservation(
        race_id=race_id, anchor_driver_id=str(hit["driver_id"]),
        anchor_lap_number=int(hit["lap_number"]),
        anchor_state_time_s=float(hit["state_time_s"]))
    snap = RaceStateReconstructor(sub, results,
                                  race_meta=race_meta).reconstruct(anchor)
    bridge = RaceStateFeatureBridge(sub, history)
    engine = RacePredictionEngine(bridge, predictor,
                                  ModelIdentity.from_production_predictor(
                                      predictor))
    return engine, snap, sub


ORDINARY = (2023, "2023-r01-R", "alonso", 28)
EDGE = (2021, "2021-r12-R", "hamilton", 2)


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
@pytest.mark.parametrize("fixture", [ORDINARY, EDGE])
def test_production_artifact_smoke(fixture, history, predictor):
    season, race_id, driver, lap = fixture
    engine, snap, _ = _dev_engine(season, race_id, driver, lap, history,
                                  predictor)
    first = engine.predict(snap)
    assert [e.driver_id for e in first.predictions] == list(
        snap.roster_driver_ids)
    assert first.roster_size == snap.roster_size
    for entry, member in zip(first.predictions, snap.drivers):
        assert entry.observable is member.observable
        if member.observable:
            assert entry.winner_probability is not None
            assert 0.0 <= entry.winner_probability <= 1.0
            assert math.isfinite(entry.winner_probability)
            assert entry.unavailable_reason is None
            assert entry.observed_position == member.position
        else:
            assert entry.winner_probability is None
            assert entry.unavailable_reason == NO_OBSERVATION_AT_SNAPSHOT
    assert first.model.task == "winner"
    assert first.model.target == "is_winner"
    assert first.model.feature_set == "ALL_84"
    assert first.model.probability_semantics == "INDEPENDENT_BINARY"
    assert first.model.artifact_sha256.startswith("1116b34f")
    assert first.model.specification_fingerprint.startswith("3164de9e")
    assert engine.predict(snap).to_dict() == first.to_dict()
    json.dumps(first.to_dict())  # JSON-safe, no numpy leakage


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
def test_direct_serving_parity(history, predictor):
    season, race_id, driver, lap = ORDINARY
    engine, snap, _ = _dev_engine(season, race_id, driver, lap, history,
                                  predictor)
    batch = engine._bridge.features_for_state(snap)
    direct = SERVING.load_frozen_winner_model().predict_proba(batch.features)
    snap_probs = [engine.predict(snap).probability_by_driver()[i.driver_id]
                  for i in batch.identities]
    max_abs = max(abs(float(a) - float(b))
                  for a, b in zip(direct, snap_probs))
    print(f"\nSERVING PARITY {race_id}: rows={len(batch)} "
          f"max_abs_diff={max_abs:.3e}")
    assert max_abs == 0.0


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
def test_future_mutation_end_to_end_invariance(history, predictor):
    from v2.race_state_features import RaceStateFeatureBridge
    season, race_id, driver, lap = ORDINARY
    engine, snap, sub = _dev_engine(season, race_id, driver, lap, history,
                                    predictor)
    before = engine.predict(snap).to_dict()
    mutated = sub.copy()
    future = mutated["state_time_s"] > snap.state_time_s
    mutated.loc[future, "position"] = 1
    mutated.loc[future, "wx_air_temp_c"] = -99.0
    other = RacePredictionEngine(
        RaceStateFeatureBridge(mutated, history), predictor,
        engine.model_identity)
    assert other.predict(snap).to_dict() == before


@pytest.mark.skipif(not _HAS_CANON, reason="canonical data absent")
def test_performance_observation(history, predictor):
    season, race_id, driver, lap = ORDINARY
    engine, snap, _ = _dev_engine(season, race_id, driver, lap, history,
                                  predictor)
    started = time.perf_counter()
    batch = engine._bridge.features_for_state(snap)
    t_bridge = (time.perf_counter() - started) * 1000.0
    started = time.perf_counter()
    probs = predictor.predict_proba(batch.features)
    t_model = (time.perf_counter() - started) * 1000.0
    assert len(probs) == len(batch)
    started = time.perf_counter()
    snapshot = engine.predict(snap)
    t_full = (time.perf_counter() - started) * 1000.0
    started = time.perf_counter()
    engine.predict(snap)
    t_warm = (time.perf_counter() - started) * 1000.0
    print(f"\nPERF {race_id}: drivers={len(batch)} bridge_ms={t_bridge:.1f} "
          f"model_ms={t_model:.1f} full_ms={t_full:.1f} repeat_ms={t_warm:.1f}")
    assert snapshot.roster_size == snap.roster_size


def test_production_factory_smoke():
    if not _HAS_CANON:
        pytest.skip("canonical data absent")
    from v2.features.build_matrix import load_history
    sub = _season_frame(2023, "driver_lap_state_d9")
    sub = sub[sub["race_id"] == "2023-r01-R"].reset_index(drop=True)
    try:
        engine = load_production_prediction_engine(
            sub, load_history(V2Paths.resolve()))
    except Exception as exc:
        pytest.skip(f"production factory unavailable: {exc}")
    assert isinstance(engine._predictor, SERVING.FrozenWinnerPredictor)
    assert engine.model_identity.task == "winner"
