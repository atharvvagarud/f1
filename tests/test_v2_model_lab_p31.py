"""P3.1 tests: production handoff, holdout seal, fresh-clone skips, CORS.

- Serving artifact creation uses FINAL_FIT 2018-2024 development rows only
  (never 2025 targets); loading validates every frozen anchor before
  returning a predictor; reference/serving equivalence is checked on a
  deterministic DEVELOPMENT fixture.
- The protected 2025 holdout is never evaluated here: second-access,
  guard-ordering and immutability tests use temp paths and mocks.
"""

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import pytest

import model_lab_helpers as H
from model_lab_helpers import load_canonical_or_skip, require_generated_artifact
from v2.model_lab import errors as E
from v2.model_lab import final_fit as FF
from v2.model_lab import serving as S
from v2.model_lab import splits as SPLITS

ROOT = Path(__file__).resolve().parents[1]
FROZEN_HOLDOUT_SHA256 = (
    "2c3a166df1a1af1d20f24fafc6a17283de1cdd1eea2b5f67a26204ed174a7415")


@pytest.fixture(scope="module")
def canonical():
    return load_canonical_or_skip()


@pytest.fixture(scope="module")
def serving_predictor():
    path = require_generated_artifact(
        S.default_serving_artifact_path(),
        purpose="P3.1 production serving artifact")
    _ = path
    return S.load_frozen_winner_model()


# --- serving artifact creation (development only) -----------------------------


def test_serving_artifact_creation_uses_development_only(canonical, tmp_path,
                                                         monkeypatch):
    """Creation fits FINAL_FIT only; any holdout path would fail loudly."""
    monkeypatch.setattr(
        FF, "materialize_holdout",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("creation must not materialize the holdout")))
    monkeypatch.setattr(
        FF, "evaluate_protected_holdout",
        lambda *a, **k: (_ for _ in ()).throw(
            AssertionError("creation must not evaluate 2025")))
    out = tmp_path / "serving.joblib"
    record = S.materialize_serving_artifact(canonical, out=out)
    assert out.exists()
    assert record["feature_count"] == 84
    assert record["transformed_dim"] == 106
    assert record["estimator_class"] == "LogisticRegression"
    assert record["estimator_params"] == {
        "C": 0.01, "solver": "lbfgs", "max_iter": 1000,
        "class_weight": None, "random_state": 42}
    assert record["training_seasons"] == list(range(2018, 2025))
    assert record["training_counts"] == FF.FINAL_FIT_EXPECTED
    assert record["specification_fingerprint"] == \
        FF.specification_fingerprint()
    assert record["phase2_matrix_content_hash"] == \
        canonical.manifest.get("content_hash")
    assert record["sklearn_version"]
    assert len(record["sha256"]) == 64
    assert len(record["feature_names_hash"]) == 64
    gate = record["pre_materialization_gate"]
    assert gate["holdout_blocked_without_opt_in"] is True
    assert gate["development_runner_rejects_holdout"] is True


# --- serving artifact loading -------------------------------------------------


def test_serving_artifact_loads_and_validates(serving_predictor):
    predictor = serving_predictor
    assert isinstance(predictor, S.FrozenWinnerPredictor)
    assert len(predictor.feature_names) == 84
    assert predictor.transformed_dim == 106
    assert predictor.sklearn_version
    assert predictor.specification_fingerprint == \
        FF.specification_fingerprint()
    record = S.describe_serving_artifact()
    assert record["feature_count"] == 84
    assert record["transformed_dim"] == 106
    assert record["estimator_class"] == "LogisticRegression"
    assert record["estimator_params"]["C"] == 0.01
    assert record["training_seasons"] == list(range(2018, 2025))
    assert record["calibration_method"] == "RAW"
    assert record["probability_semantics"] == "INDEPENDENT_BINARY"


def test_missing_serving_artifact_fails_loudly(tmp_path):
    """The tracked artifact must exist; absence is failure, not skip."""
    with pytest.raises(E.ServingArtifactError):
        S.load_frozen_winner_model(tmp_path / "absent.joblib")


def test_malformed_serving_artifacts_rejected(tmp_path, serving_predictor):
    del serving_predictor
    src = S.default_serving_artifact_path()
    payload = joblib.load(src)

    garbage = tmp_path / "garbage.joblib"
    garbage.write_bytes(b"\x00\x01not-a-payload")
    with pytest.raises(E.ServingArtifactError):
        S.load_frozen_winner_model(garbage)

    wrong_type = tmp_path / "list.joblib"
    joblib.dump(["not", "a", "mapping"], wrong_type)
    with pytest.raises(E.ServingArtifactError):
        S.load_frozen_winner_model(wrong_type)

    tampered_c = tmp_path / "tampered_c.joblib"
    payload_c = dict(payload)
    estimator_c = payload_c["estimator"]
    estimator_c.C = 1.0
    joblib.dump(payload_c, tampered_c)
    with pytest.raises(E.ServingArtifactError):
        S.load_frozen_winner_model(tampered_c)
    estimator_c.C = 0.01  # restore in-memory object for later cases

    tampered_features = tmp_path / "tampered_features.joblib"
    payload_f = dict(payload)
    payload_f["feature_names_ordered"] = \
        payload_f["feature_names_ordered"][:-1]
    joblib.dump(payload_f, tampered_features)
    with pytest.raises(E.ServingArtifactError):
        S.load_frozen_winner_model(tampered_features)

    tampered_format = tmp_path / "tampered_format.joblib"
    payload_v = dict(payload)
    payload_v["format_version"] = "v999"
    joblib.dump(payload_v, tampered_format)
    with pytest.raises(E.ServingArtifactError):
        S.load_frozen_winner_model(tampered_format)


# --- development-fixture equivalence ------------------------------------------


def test_serving_reference_equivalence_on_development_fixture(
        canonical, serving_predictor):
    """Loaded predictor == frozen reference final fit on D1 (2022) rows."""
    dataset, _ = FF.materialize_final_fit(canonical)
    reference = FF.fit_final_model(canonical, dataset)["model"]
    fixture = SPLITS.materialize(
        canonical, "winner", "D1", "ALL_84", assert_m0_counts=False)
    frame = fixture.X_validation
    assert int(fixture.validation_metadata["season"].astype(int).max()) < 2025
    expected = reference.predict_positive_probability(frame)
    observed = serving_predictor.predict_proba(frame)
    assert observed.shape == expected.shape
    assert len(observed) == len(frame) > 0
    assert np.all(np.isfinite(observed))
    assert np.all((observed >= 0.0) & (observed <= 1.0))
    max_diff = float(np.max(np.abs(observed - expected)))
    assert max_diff == 0.0, f"serving/reference drift: {max_diff}"


def test_serving_feature_order_enforced(serving_predictor, canonical):
    from v2.model_lab import data as DATA

    frame = DATA.feature_frame(canonical, "ALL_84").iloc[:8]
    ok = serving_predictor.predict_proba(frame)
    assert len(ok) == 8
    shuffled = frame[list(reversed(frame.columns))]
    with pytest.raises(E.ServingArtifactError):
        serving_predictor.predict_proba(shuffled)
    dropped = frame.iloc[:, :-1]
    with pytest.raises(E.ServingArtifactError):
        serving_predictor.predict_proba(dropped)
    with pytest.raises(E.ServingArtifactError):
        serving_predictor.predict_proba(frame.values)


def test_serving_source_guard():
    """Stricter successor guard for the serving exemption.

    The frozen inference boundary may reference the estimator class and
    call predict_proba, but it must never fit, tune, calibrate-select,
    or touch holdout machinery.
    """
    text = (ROOT / "v2" / "model_lab" / "serving.py").read_text()
    for token in (".fit(", "allow_protected_holdout", "materialize_holdout",
                  "evaluate_protected_holdout", "run_m9", "GridSearchCV",
                  "RandomizedSearchCV", "tuning_candidates",
                  "calibration_selection", "model_runner"):
        assert token not in text, f"serving.py: forbidden {token!r}"


def test_serving_import_excludes_evaluation_stack():
    """Loading the serving boundary must not need runners/holdout code."""
    code = ("import sys, v2.model_lab.serving; "
            "banned = ('v2.model_lab.runner', 'v2.model_lab.tuning', "
            "'v2.model_lab.final_fit', 'v2.model_lab.run_final', "
            "'v2.model_lab.calibration_selection', "
            "'v2.model_lab.model_runner'); "
            "hit = [m for m in sys.modules if m in banned]; "
            "assert not hit, hit; print('serving import clean')")
    proc = subprocess.run(
        [sys.executable, "-B", "-c", code], cwd=str(ROOT),
        capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    assert "serving import clean" in proc.stdout


# --- protected holdout mechanical seal ----------------------------------------


def _write_fake_consumed_marker(root: Path) -> Path:
    dest = FF.default_out(root=root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps({"consumed": True}))
    return dest


def test_second_protected_evaluation_refused(tmp_path):
    _write_fake_consumed_marker(tmp_path)
    with pytest.raises(E.ProtectedHoldoutAlreadyConsumed):
        FF.run_m9(root=tmp_path, allow_protected_holdout=True)
    with pytest.raises(E.ProtectedHoldoutAlreadyConsumed):
        FF.evaluate_protected_holdout(
            None, None, allow_protected_holdout=True, root=tmp_path)
    # The dedicated error subclasses the ordinary firewall error.
    assert issubclass(E.ProtectedHoldoutAlreadyConsumed,
                      E.ProtectedHoldoutError)


def test_second_evaluation_refuses_before_target_materialization(
        tmp_path, monkeypatch):
    _write_fake_consumed_marker(tmp_path)
    calls: list = []
    monkeypatch.setattr(
        FF.DATA, "load_canonical",
        lambda *a, **k: calls.append("load_canonical"))
    with pytest.raises(E.ProtectedHoldoutAlreadyConsumed):
        FF.run_m9(root=tmp_path, allow_protected_holdout=True)
    assert calls == [], "refusal must precede canonical/target loading"


def test_consumed_out_path_also_refused(tmp_path):
    custom = tmp_path / "custom_holdout.json"
    custom.write_text(json.dumps({"consumed": True}))
    with pytest.raises(E.ProtectedHoldoutAlreadyConsumed):
        FF.run_m9(root=tmp_path, allow_protected_holdout=True, out=custom)
    assert json.loads(custom.read_text()) == {"consumed": True}


def test_holdout_artifact_byte_identical():
    path = FF.default_out()
    assert path.exists()
    before = hashlib.sha256(path.read_bytes()).hexdigest()
    assert before == FROZEN_HOLDOUT_SHA256
    with pytest.raises(E.ProtectedHoldoutAlreadyConsumed):
        FF.run_m9(allow_protected_holdout=True)
    after = hashlib.sha256(path.read_bytes()).hexdigest()
    assert after == before == FROZEN_HOLDOUT_SHA256


def test_ordinary_holdout_firewall_intact(canonical):
    from v2.model_lab import runner as RUN

    with pytest.raises(E.ProtectedHoldoutError):
        SPLITS.get_split(SPLITS.HOLDOUT_ID)
    with pytest.raises(E.ProtectedHoldoutError):
        RUN.resolve_development_fold(SPLITS.HOLDOUT_ID)
    with pytest.raises(E.ProtectedHoldoutError):
        FF.materialize_holdout(canonical)
    with pytest.raises(E.ProtectedHoldoutError):
        FF.evaluate_protected_holdout(None, canonical)


# --- fresh-clone skip behavior -------------------------------------------------


def test_missing_generated_artifact_skips(tmp_path):
    try:
        require_generated_artifact(
            tmp_path / "absent.json", purpose="P3.1 unit probe")
    except BaseException as exc:  # pytest.skip raises Skipped
        assert "fresh-clone skip" in str(exc)
    else:
        raise AssertionError("missing generated artifact must skip")


def test_missing_matrix_prerequisite_skips(monkeypatch):
    monkeypatch.setattr(H, "matrix_available", lambda root=None: False)
    try:
        H.require_matrix()
    except BaseException as exc:
        assert "not materialized" in str(exc)
    else:
        raise AssertionError("missing matrix must skip")
    try:
        H.load_canonical_or_skip()
    except BaseException as exc:
        assert "not materialized" in str(exc)
    else:
        raise AssertionError("missing matrix must skip")


def test_present_artifacts_do_not_skip():
    assert H.matrix_available() is True
    path = S.default_serving_artifact_path()
    assert H.require_generated_artifact(
        path, purpose="P3.1 unit probe") == path


# --- API CORS safety (P10-3: explicit origins, never wildcard by default) ----


def test_api_cors_disallows_credentialed_wildcard():
    from api.config import get_serving_config
    from api.main import create_app

    app = create_app(get_serving_config(env={}))
    cors = [m for m in app.user_middleware
            if m.cls.__name__ == "CORSMiddleware"]
    assert cors, "CORSMiddleware must remain configured"
    options = cors[0].kwargs
    assert options.get("allow_origins") == ["http://localhost:3000"]
    assert options.get("allow_credentials") is False


# --- serving artifact identity (recorded for the handoff report) --------------


def test_serving_artifact_identity_matches_frozen_spec():
    record = S.describe_serving_artifact()
    assert record["format"] == "v2-serving-winner-logreg-raw"
    assert record["format_version"] == "v1"
    assert record["specification_fingerprint"] == \
        FF.specification_fingerprint()
    assert record["specification"]["C"] == 0.01
    assert record["specification"]["feature_set"] == "ALL_84"
    assert record["specification"]["calibration_method"] == "RAW"
    assert record["training_counts"]["positives"] == 8926
    assert record["training_counts"]["negatives"] == 153802
