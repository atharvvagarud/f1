"""M9 tests: final development fit + one-shot protected 2025 holdout.

Focused coverage for the Model Lab freeze stage:

- the exact frozen specification (C=0.01, lbfgs, max_iter=1000, ALL_84, RAW,
  INDEPENDENT_BINARY, FINAL_FIT 2018-2024, HOLDOUT 2025) and deterministic
  fingerprint;
- the pre-unlock gate and immutable declaration;
- train-only final fitting (no validation, no tuning, no calibration,
  no thresholding);
- the holdout firewall (explicit opt-in; development runners still reject
  2025; no post-holdout selection API);
- the stored protected artifact + canonical protected experiment;
- deterministic document rendering and freeze-manifest validation.

The protected 2025 holdout is NOT evaluated by these tests; the stored
one-shot M9 artifact is validated by reading it.
"""

import inspect
import json
import types
from pathlib import Path

import numpy as np
import pytest

from model_lab_helpers import load_canonical_or_skip, require_generated_artifact
from v2.model_lab import errors as E
from v2.model_lab import final_fit as FF
from v2.model_lab import inner_splits as IS
from v2.model_lab import preprocessing as PRE
from v2.model_lab import predictions as PR
from v2.model_lab import results as RES
from v2.model_lab import runner as RUN
from v2.model_lab import splits as SPLITS
from v2.model_lab import tuning_candidates as TC
from v2.model_lab import winner as WINNER
from v2.model_lab.protocol import (
    EXPECTED_ABLATION_CONFIG_SHA256,
    EXPECTED_MANIFEST_SHA256,
    EXPECTED_MATRIX_CONTENT_HASH,
    EXPECTED_MATRIX_PARQUET_SHA256,
    MODEL_LAB_PROTOCOL_VERSION,
    PROTECTED_HOLDOUT_SEASON,
)

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def canonical():
    return load_canonical_or_skip()


@pytest.fixture(scope="module")
def artifact():
    path = FF.default_out()
    if not path.exists():
        pytest.skip(f"M9 holdout artifact missing at {path}; run M9 first")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


# --- frozen contract ----------------------------------------------------------


def test_frozen_constants_exact():
    assert FF.M9_TASK == "winner"
    assert FF.M9_FEATURE_SET == "ALL_84"
    assert FF.M9_SEED == 42
    assert FF.FROZEN_C == 0.01
    assert FF.SOLVER == "lbfgs"
    assert FF.MAX_ITER == 1000
    assert FF.CLASS_WEIGHT is None
    assert FF.RANDOM_STATE == 42


def test_temporal_contract_exact():
    assert FF.FINAL_FIT_SEASONS == tuple(range(2018, 2025))
    assert FF.HOLDOUT_SEASON == PROTECTED_HOLDOUT_SEASON == 2025
    assert PROTECTED_HOLDOUT_SEASON not in FF.FINAL_FIT_SEASONS


def test_count_anchors_exact():
    assert FF.FINAL_FIT_EXPECTED == {
        "races": 149, "states": 162728, "eligible": 162728,
        "positives": 8926, "negatives": 153802}
    assert FF.HOLDOUT_EXPECTED == {
        "races": 24, "states": 26692, "eligible": 26692,
        "positives": 1444, "negatives": 25248}


def test_specification_fingerprint_deterministic():
    first = FF.specification_fingerprint()
    second = FF.specification_fingerprint()
    assert first == second
    assert len(first) == 64
    assert first != ""
    spec = FF.frozen_specification()
    assert spec["C"] == 0.01
    assert spec["calibration_method"] == "RAW"
    assert spec["feature_set"] == "ALL_84"
    assert spec["probability_kind"] == "BINARY_PROBABILITY"
    assert spec["probability_semantics"] == "INDEPENDENT_BINARY"
    assert spec["weighting"] == "state_equal"
    assert spec["holdout_season"] == 2025
    assert spec["final_fit_seasons"] == list(range(2018, 2025))


def test_frozen_estimator_construction_exact():
    estimator = FF.build_frozen_estimator()
    params = FF._estimator_parameters(estimator)
    assert params["class_name"] == "LogisticRegression"
    assert params["C"] == 0.01
    assert params["solver"] == "lbfgs"
    assert params["max_iter"] == 1000
    assert params["class_weight"] is None
    assert params["random_state"] == 42


def test_preprocessing_specification_frozen():
    contract = PRE.preprocessing_contract_dict()
    assert contract["numeric_imputation"].startswith("median")
    assert contract["numeric_scaling"].startswith("StandardScaler")
    assert contract["categorical_encoding"].startswith("one-hot")
    assert contract["fit_scope"] == "training only"
    assert FF.frozen_specification()["preprocessing"] == contract


# --- static guard / no new dependencies ---------------------------------------


def test_static_guard_m9_modules_train_only_logreg():
    forbidden = ("ExtraTreesClassifier", "RandomForestClassifier",
                 "HistGradientBoostingClassifier", "XGBClassifier",
                 "LGBMClassifier", "CatBoost", "MLPClassifier",
                 "import torch", "from torch", "GridSearchCV",
                 "RandomizedSearchCV", "BayesSearchCV", "Optuna", "optuna",
                 "hyperopt", "MLflow", "mlflow", "SMOTE", "imbalanced",
                 "CalibratedClassifierCV", "TabPFN", "tabpfn",
                 "IsotonicRegression", "SigmoidCalibration")
    for name in ("final_fit.py", "run_final.py"):
        text = (ROOT / "v2" / "model_lab" / name).read_text()
        for token in forbidden:
            assert token not in text, f"{name}: forbidden {token!r}"
    assert "LogisticRegression" in (
        ROOT / "v2" / "model_lab" / "final_fit.py").read_text()


def test_no_new_dependencies_declared():
    for name in ("requirements.txt", "requirements-test.txt"):
        text = (ROOT / name).read_text().lower()
        for dep in ("lightgbm", "catboost", "optuna", "mlflow", "torch",
                    "tabpfn", "imbalanced", "statsmodels"):
            assert dep not in text, f"{name}: new dependency {dep!r}"


def test_no_post_holdout_selection_api_exists():
    for name, obj in vars(FF).items():
        if callable(obj) and getattr(obj, "__module__", "") == FF.__name__:
            lowered = name.lower()
            for token in ("select", "tune", "ablat", "calibrate", "refit"):
                assert token not in lowered, (
                    f"unexpected post-holdout-selection-like API {name!r}")


# --- pre-unlock gate + declaration -------------------------------------------


def test_immutability_report_matches_expected_constants():
    report = FF.immutability_report()
    assert report["phase2_matrix_content_hash"] == EXPECTED_MATRIX_CONTENT_HASH
    assert report["phase2_parquet_byte_hash"] == \
        EXPECTED_MATRIX_PARQUET_SHA256
    assert report["phase2_manifest_byte_hash"] == EXPECTED_MANIFEST_SHA256
    assert report["f16_ablation_byte_hash"] == \
        EXPECTED_ABLATION_CONFIG_SHA256


def test_preunlock_gate_passes(canonical):
    checks = FF.run_preunlock_gate(canonical, verify_hashes=False)
    assert checks["passed"] is True
    assert checks["m7_frozen_c"] == 0.01
    assert checks["m7_boundary_status"] == "RESOLVED"
    assert checks["m7_holdout_accessed"] is False
    assert checks["m8_selected_method"] == "RAW"
    assert checks["m8_frozen_c"] == 0.01
    assert checks["m8_holdout_accessed"] is False
    assert checks["holdout_blocked_without_opt_in"] is True
    assert checks["development_runner_rejects_holdout"] is True
    assert checks["specification_fingerprint"] == \
        FF.specification_fingerprint()
    assert checks["estimator_parameters"]["C"] == 0.01


def test_preunlock_declaration_is_frozen_and_unevaluated():
    path = require_generated_artifact(
        FF.preunlock_path(), purpose="M9 pre-unlock declaration")
    declaration = json.loads(path.read_text())
    assert declaration["stage"] == "M9"
    assert declaration["holdout_target_metrics_evaluated_by_m9"] is False
    assert declaration["frozen_before_holdout"] is True
    assert declaration["specification_fingerprint"] == \
        FF.specification_fingerprint()
    assert declaration["C"] == 0.01
    assert declaration["calibration_method"] == "RAW"
    assert declaration["feature_set"] == "ALL_84"
    assert declaration["final_fit_seasons"] == list(range(2018, 2025))
    assert declaration["holdout_season"] == 2025


def test_gate_rejects_m8_calibration_drift(tmp_path, canonical):
    # A rigged M8 artifact selecting a calibrator must fail the gate.
    reports = tmp_path / "reports"
    reports.mkdir(parents=True)
    (reports / FF.M7_ARTIFACT_FILENAME).write_text(json.dumps(
        json.loads(FF.m7_artifact_path().read_text())))
    m8 = json.loads(FF.m8_artifact_path().read_text())
    m8["method_comparison"]["selected_method"] = "PLATT"
    (reports / FF.M8_ARTIFACT_FILENAME).write_text(json.dumps(m8))
    with pytest.raises(E.ExperimentConfigError):
        FF.run_preunlock_gate(canonical, root=tmp_path, verify_hashes=False)


def test_write_declaration_refuses_to_overwrite(tmp_path):
    reports = tmp_path / "data/v2/model_lab/reports"
    reports.mkdir(parents=True)
    (reports / FF.PREUNLOCK_FILENAME).write_text("{}")
    with pytest.raises(E.ExperimentConfigError):
        FF.write_preunlock_declaration(root=tmp_path)


# --- final fit ----------------------------------------------------------------


def test_materialize_final_fit_counts(canonical):
    dataset, counts = FF.materialize_final_fit(canonical)
    assert counts == FF.FINAL_FIT_EXPECTED
    assert dataset.split.validation_seasons == ()
    assert dataset.split.train_seasons == FF.FINAL_FIT_SEASONS
    seasons = set(dataset.train_metadata["season"].astype(int))
    assert PROTECTED_HOLDOUT_SEASON not in seasons


def test_final_fit_is_train_only(canonical, monkeypatch):
    dataset, _ = FF.materialize_final_fit(canonical)
    small = types.SimpleNamespace(
        X_train=dataset.X_train.iloc[:3000].copy(),
        y_train=dataset.y_train.iloc[:3000].copy())
    seen_pre: list = []
    seen_rows: list = []
    original_pre = PRE.fit_preprocessor
    original_fit = TC.fit_fresh_model

    def recording_pre(frame, schema):
        seen_pre.append(len(frame))
        return original_pre(frame, schema)

    def recording_fit(family, parameters, X, y, **kwargs):
        seen_rows.append(len(X))
        assert set(np.unique(np.asarray(y))) <= {0.0, 1.0}
        return original_fit(family, parameters, X, y, **kwargs)

    monkeypatch.setattr(PRE, "fit_preprocessor", recording_pre)
    monkeypatch.setattr(TC, "fit_fresh_model", recording_fit)
    out = FF.fit_final_model(canonical, small)
    assert seen_pre == [3000]
    assert seen_rows == [3000]
    assert out["model"].parameters == {"C": 0.01}
    assert out["model"].family == "logistic_regression"


def test_final_fit_determinism_on_small_fixture(canonical):
    # Focused determinism check on a small DEVELOPMENT fixture (no 2025).
    dataset, _ = FF.materialize_final_fit(canonical)
    small = types.SimpleNamespace(
        X_train=dataset.X_train.iloc[:2000].copy(),
        y_train=dataset.y_train.iloc[:2000].copy())
    first = FF.fit_final_model(canonical, small)
    second = FF.fit_final_model(canonical, small)
    p1 = first["model"].predict_positive_probability(small.X_train)
    p2 = second["model"].predict_positive_probability(small.X_train)
    assert np.max(np.abs(p1 - p2)) <= 1e-12


# --- holdout firewall ---------------------------------------------------------


def test_holdout_requires_explicit_opt_in(canonical):
    with pytest.raises(E.ProtectedHoldoutError):
        SPLITS.get_split(SPLITS.HOLDOUT_ID)
    with pytest.raises(E.ProtectedHoldoutError):
        RUN.resolve_development_fold("HOLDOUT")
    with pytest.raises(E.ProtectedHoldoutError):
        FF.materialize_holdout(canonical)
    with pytest.raises(E.ProtectedHoldoutError):
        FF.evaluate_protected_holdout(None, canonical)
    with pytest.raises(E.ProtectedHoldoutError):
        FF.run_m9(allow_protected_holdout=False)


def test_synchronized_topk_blocks_holdout_without_opt_in(canonical):
    prediction = PR.PredictionResult(
        kind=PR.PredictionKind.BINARY_PROBABILITY,
        state_ids=(), values=np.asarray([], dtype=float),
        semantics=PR.ProbabilitySemantics.INDEPENDENT_BINARY)
    with pytest.raises(E.ProtectedHoldoutError):
        WINNER.synchronized_winner_top_k(prediction, canonical)
    with pytest.raises(E.ProtectedHoldoutError):
        WINNER.synchronized_winner_top_k(
            prediction, canonical, allow_protected_holdout=False)


def test_2025_absent_from_all_development_paths(canonical):
    for fold in ("D1", "D2", "D3", "FINAL_FIT"):
        split = SPLITS.get_split(fold)
        assert PROTECTED_HOLDOUT_SEASON not in {
            int(s) for s in (*split.train_seasons,
                             *split.validation_seasons)}
    for outer in ("D1", "D2", "D3"):
        for split in IS.resolve_inner_splits(outer):
            assert PROTECTED_HOLDOUT_SEASON not in {
                int(s) for s in (*split.train_seasons,
                                 *split.validation_seasons)}


# --- stored artifacts ---------------------------------------------------------


def test_final_holdout_artifact_contract(artifact):
    assert artifact["schema_version"] == "v1"
    assert artifact["stage"] == "M9"
    assert artifact["final_fit"]["specification_fingerprint"] == \
        FF.specification_fingerprint()
    assert artifact["final_fit"]["model_parameters"]["C"] == 0.01
    assert artifact["final_fit"]["counts"] == FF.FINAL_FIT_EXPECTED
    assert artifact["holdout"]["season"] == 2025
    assert artifact["holdout"]["counts"] == FF.HOLDOUT_EXPECTED
    for metric in ("log_loss", "brier", "roc_auc", "pr_auc"):
        assert artifact["metrics"]["race_macro"][metric] is not None
        assert artifact["metrics"]["state_pooled"][metric] is not None
    assert artifact["holdout_access"]["explicit_opt_in"] is True
    assert artifact["holdout_access"]["materialization_access_count"] == 1
    assert artifact["holdout_access"]["target_evaluation_count"] == 1
    assert len(artifact["per_race"]) == 24
    assert artifact["protected_experiment"]["C"] == 0.01
    assert artifact["protected_experiment"]["calibration_method"] == "RAW"
    assert artifact["protected_experiment"]["evaluation_split"] == "HOLDOUT"
    assert "no_post_holdout_tuning" in json.dumps(artifact).lower() or \
        "no post-holdout" in artifact["no_post_holdout_tuning_statement"]


def test_probability_semantics_preserved(artifact):
    assert "INDEPENDENT_BINARY" in artifact["probability_semantics_statement"]
    assert "NOT normalized" in artifact["probability_semantics_statement"]
    topk = artifact["synchronized"]["winner_top_k"]
    assert set(topk["top_k"]) == {1, 3}
    assert topk["accuracy"]["top1"] is not None
    assert topk["accuracy"]["top3"] is not None
    assert topk["min_observable_field_size"] is not None
    assert topk["mean_observable_field_size"] is not None


def test_uncertainty_whole_race_bootstrap(artifact):
    uncertainty = artifact["uncertainty"]
    assert set(uncertainty) == {"race_macro_log_loss", "race_macro_brier"}
    for node in uncertainty.values():
        assert node["status"] == "OK"
        assert node["unit"] == "whole_race"
        assert node["replicates"] == 1000
        assert node["seed"] == 42
        assert node["n_races"] == 24


def test_per_race_breakdown_covers_all_2025_races(artifact):
    rounds = sorted(entry["round"] for entry in artifact["per_race"])
    assert len(rounds) == 24
    assert len(set(rounds)) == 24
    for entry in artifact["per_race"]:
        assert entry["eligible_states"] > 0
        assert entry["coverage_status"] in ("OK", "SKIPPED")
        assert entry["race_macro_log_loss"] is not None


def test_protected_experiment_is_single_and_traced(artifact):
    config, result = RES.read_experiment(
        artifact["protected_experiment"]["dest"])
    assert config.experiment_id == \
        artifact["protected_experiment"]["experiment_id"]
    assert config.model_family == FF.PROTECTED_EXPERIMENT_FAMILY
    assert config.holdout_accessed is True
    assert config.fold == "FINAL_FIT"
    assert config.validation_races == 24
    assert config.validation_rows == 26692
    assert result.metrics["log_loss"]["race_macro"]["value"] == \
        pytest.approx(artifact["metrics"]["race_macro"]["log_loss"])

    experiments = RES.experiments_root()
    protected = []
    for config_path in experiments.glob("*/config.json"):
        payload = json.loads(config_path.read_text())
        if payload.get("model_family") == FF.PROTECTED_EXPERIMENT_FAMILY:
            protected.append(payload)
    assert len(protected) == 1
    assert protected[0]["holdout_accessed"] is True


def test_final_model_metadata_descriptor(artifact):
    path = FF.final_model_dir() / "metadata.json"
    assert path.exists(), (
        f"final model metadata missing at {path}; run M9 first")
    metadata = json.loads(path.read_text())
    assert metadata["persistence"] == \
        "metadata_only_no_estimator_serialization"
    assert metadata["specification_fingerprint"] == \
        FF.specification_fingerprint()
    assert metadata["model_fingerprint"] == \
        artifact["final_fit"]["model_fingerprint"]
    assert metadata["training_seasons"] == list(range(2018, 2025))
    assert metadata["training_counts"] == FF.FINAL_FIT_EXPECTED
    assert metadata["feature_names_ordered"] == \
        artifact["final_fit"]["feature_names_ordered"]


# --- deterministic rendering + freeze manifest --------------------------------


def test_documents_render_deterministically(artifact):
    card = (ROOT / FF.MODEL_CARD_REL).read_text()
    report = (ROOT / FF.FINAL_REPORT_REL).read_text()
    assert card == FF.render_model_card(artifact)
    assert report == FF.render_final_report(artifact)
    for text in (card, report):
        for token in ("PROTECTED", "2025", "RAW"):
            assert token in text or token.lower() in text.lower()
    assert "independent" in card.lower()
    assert "INDEPENDENT_BINARY" in report


def test_freeze_manifest_contract(artifact):
    path = ROOT / FF.FREEZE_MANIFEST_OUT_REL
    assert path.exists(), f"freeze manifest missing at {path}"
    manifest = json.loads(path.read_text())
    assert manifest["model_lab_status"] == "FROZEN"
    assert manifest["protocol_version"] == MODEL_LAB_PROTOCOL_VERSION
    assert manifest["final_model_specification_fingerprint"] == \
        FF.specification_fingerprint()
    assert manifest["preunlock_fingerprint"] == \
        FF.specification_fingerprint()
    assert manifest["phase2_frozen_hashes"]["phase2_matrix_content_hash"] == \
        EXPECTED_MATRIX_CONTENT_HASH
    assert manifest["preunlock_artifact_sha256"] == FF._sha256_file(
        FF.preunlock_path())
    assert manifest["holdout_artifact"]["sha256"] == FF._sha256_file(
        FF.default_out())
    assert manifest["stage_artifacts"]["M7_boundary_resolution"]["sha256"]
    assert manifest["final_model_fingerprint"] == \
        artifact["final_fit"]["model_fingerprint"]


def test_freeze_manifest_rebuild_is_structurally_stable(artifact):
    rebuilt = FF.build_freeze_manifest(
        artifact, paths=None, root=None, test_results={"status": "REBUILT"})
    stored = json.loads((ROOT / FF.FREEZE_MANIFEST_OUT_REL).read_text())
    for key in ("model_lab_status", "protocol_semantic_hash",
                "final_model_specification_fingerprint",
                "preunlock_fingerprint", "preunlock_artifact_sha256",
                "holdout_artifact", "stage_artifacts"):
        assert rebuilt[key] == stored[key]
