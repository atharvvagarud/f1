"""M3 tests: LogReg reference preprocessing, adapter, runner, firewalls.

Focused safety/leakage coverage for the single fixed Logistic Regression
reference model. Synthetic fixtures prove train-only fitting,
transform-only validation, missingness/unknown-category handling, label /
identity firewalls, fold isolation, target firewalls and determinism. One
full-data D1 integration test proves the exact M2 canonical evaluator path
on an isolated experiment root. The 2025 holdout is never evaluated.
"""

import numpy as np
import pandas as pd
import pytest

from model_lab_helpers import load_canonical_or_skip, require_matrix
from raceintel.model_lab import data as D
from raceintel.model_lab import errors as E
from raceintel.model_lab import experiment as EX
from raceintel.model_lab import logreg as LR
from raceintel.model_lab import model_runner as MR
from raceintel.model_lab import model_suite as MSUITE
from raceintel.model_lab import preprocessing as PRE
from raceintel.model_lab import predictions as PR
from raceintel.model_lab import results as RES
from raceintel.model_lab import run as RUNCLI
from raceintel.model_lab import run_models as MODELSCLI
from raceintel.model_lab import runner as RUN
from raceintel.model_lab import splits as S


@pytest.fixture(scope="module")
def canonical():
    return load_canonical_or_skip()


@pytest.fixture(scope="module")
def schema(canonical):
    return canonical.schema


def _synthetic_frame(n: int = 60, seed: int = 7) -> pd.DataFrame:
    require_matrix()
    rng = np.random.default_rng(seed)
    frame = pd.DataFrame({
        name: rng.normal(size=n)
        for name in D.load_canonical().schema.numeric
    })
    for name in D.load_canonical().schema.boolean:
        frame[name] = rng.integers(0, 2, size=n).astype(bool)
    cats = {
        "compound": ["SOFT", "MEDIUM", "HARD"],
        "stint_compound": ["SOFT", "MEDIUM"],
        "track_state": ["all_clear", "safety_car"],
    }
    for name, values in cats.items():
        frame[name] = rng.choice(values, size=n)
    return frame


def _synthetic_target(n: int, seed: int = 11) -> np.ndarray:
    rng = np.random.default_rng(seed)
    y = np.zeros(n)
    y[rng.choice(n, size=max(2, n // 10), replace=False)] = 1.0
    return y


# --- fixed specification -----------------------------------------------------

def test_fixed_logreg_specification():
    spec = LR.logreg_model_parameters()
    assert spec["estimator"] == "LogisticRegression"
    assert spec["C"] == 1.0
    assert spec["solver"] == "lbfgs"
    assert spec["max_iter"] == 1000
    assert spec["class_weight"] is None
    assert spec["random_state"] == 42
    est = LR.build_estimator()
    assert est.C == 1.0 and est.solver == "lbfgs"
    assert est.max_iter == 1000 and est.class_weight is None


def test_no_rebalancing_or_resampling():
    assert LR.LOGREG_SPEC["class_weight"] is None
    assert "balanced" not in str(LR.logreg_model_parameters())
    assert LR.LOGREG_TASK == "winner"
    assert LR.LOGREG_FEATURE_SET == "ALL_84"
    assert LR.LOGREG_SEED == EX.PROJECT_SEED


def test_adapter_exposes_model_adapter_contract():
    assert isinstance(LR.LogisticRegressionAdapter(), EX.ModelAdapter)


# --- preprocessing: train-only fitting ----------------------------------------

def test_preprocessor_fits_train_statistics_only(schema):
    train = _synthetic_frame(80, seed=1)
    col_name = schema.numeric[0]
    train.loc[train.index[::2], col_name] = np.nan
    expected_median = float(np.nanmedian(train[col_name].to_numpy()))
    fitted = PRE.fit_preprocessor(train, schema)
    num_pipe = fitted.transformer.named_transformers_["num"]
    medians = num_pipe.named_steps["impute"].statistics_
    col = list(fitted.numeric_columns).index(col_name)
    assert float(medians[col]) == pytest.approx(expected_median)
    assert fitted.output_dim > 0


def test_validation_is_transform_only(schema):
    train = _synthetic_frame(60, seed=2)
    fitted = PRE.fit_preprocessor(train, schema)
    assert not hasattr(fitted, "fit")
    assert not hasattr(fitted, "fit_transform")
    val = _synthetic_frame(20, seed=3)
    out = fitted.transform(val)
    assert np.all(np.isfinite(out))
    assert out.shape == (20, fitted.output_dim)


def test_numeric_missingness_produces_finite_output(schema):
    train = _synthetic_frame(60, seed=4)
    train.iloc[::3, 0] = np.nan
    fitted = PRE.fit_preprocessor(train, schema)
    val = _synthetic_frame(10, seed=5)
    val.iloc[:, 0] = np.nan
    out = fitted.transform(val)
    assert np.all(np.isfinite(out))


def test_categorical_missingness_uses_explicit_sentinel(schema):
    train = _synthetic_frame(60, seed=6)
    train.loc[train.index[:10], "compound"] = None
    fitted = PRE.fit_preprocessor(train, schema)
    encoder = fitted.transformer.named_transformers_["cat"].named_steps[
        "encode"]
    compound_cats = list(encoder.categories_[0])
    assert PRE.MISSING_CATEGORY in compound_cats
    val = _synthetic_frame(5, seed=7)
    val.loc[:, "compound"] = None
    out = fitted.transform(val)
    assert np.all(np.isfinite(out))


def test_unseen_validation_category_is_safe(schema):
    train = _synthetic_frame(60, seed=8)
    fitted = PRE.fit_preprocessor(train, schema)
    before_cats = [tuple(c) for c in fitted.transformer.named_transformers_[
        "cat"].named_steps["encode"].categories_]
    val = _synthetic_frame(10, seed=9)
    val.loc[:, "compound"] = "NEVER_SEEN_COMPOUND"
    out = fitted.transform(val)
    assert np.all(np.isfinite(out))
    after_cats = [tuple(c) for c in fitted.transformer.named_transformers_[
        "cat"].named_steps["encode"].categories_]
    assert before_cats == after_cats


def test_preprocessing_leakage_fixture(schema):
    train = _synthetic_frame(80, seed=10)
    fitted = PRE.fit_preprocessor(train, schema)
    stats_before = fitted.transformer.named_transformers_[
        "num"].named_steps["impute"].statistics_.copy()
    cats_before = [tuple(c) for c in fitted.transformer.named_transformers_[
        "cat"].named_steps["encode"].categories_]
    val = _synthetic_frame(30, seed=11)
    val.iloc[:, :5] = 1e9  # extreme numeric values
    val.loc[:, "compound"] = "UNSEEN_VALUE"
    val.iloc[::2, 0] = np.nan  # different missingness distribution
    out = fitted.transform(val)
    assert np.all(np.isfinite(out))
    stats_after = fitted.transformer.named_transformers_[
        "num"].named_steps["impute"].statistics_
    cats_after = [tuple(c) for c in fitted.transformer.named_transformers_[
        "cat"].named_steps["encode"].categories_]
    np.testing.assert_equal(stats_before, stats_after)
    assert cats_before == cats_after


# --- feature firewall ----------------------------------------------------------

@pytest.mark.parametrize("column", list(PRE.FORBIDDEN_LABEL_COLUMNS)
                         + list(PRE.FORBIDDEN_MASK_COLUMNS)
                         + ["state_id", "race_id", "driver_id"])
def test_forbidden_columns_rejected(schema, column):
    frame = _synthetic_frame(20, seed=12)
    frame[column] = 0
    with pytest.raises(E.ExperimentConfigError):
        PRE.fit_preprocessor(frame, schema)


def test_materialized_features_contain_no_forbidden(canonical):
    dataset = S.materialize(canonical, "winner", "D1", "ALL_84")
    forbidden = set(PRE.FORBIDDEN_LABEL_COLUMNS) | set(
        PRE.FORBIDDEN_MASK_COLUMNS) | set(PRE.FORBIDDEN_IDENTITY_COLUMNS)
    assert not (set(dataset.feature_names) & forbidden)
    assert len(dataset.feature_names) == 84


# --- adapter behaviour ----------------------------------------------------------

def test_positive_class_resolution_and_semantics():
    frame = _synthetic_frame(120, seed=13)
    y = _synthetic_target(120, seed=14)
    adapter = LR.LogisticRegressionAdapter()
    adapter.fit(frame, y)
    assert adapter._positive_index == list(
        adapter._estimator.classes_).index(1)
    pred = adapter.predict_result(frame, [f"s{i}" for i in range(120)])
    assert pred.kind is PR.PredictionKind.BINARY_PROBABILITY
    assert pred.semantics is PR.ProbabilitySemantics.INDEPENDENT_BINARY
    assert pred.positive_class == 1
    manual = adapter._estimator.predict_proba(adapter._matrix_for(frame))[:, 1]
    np.testing.assert_allclose(np.asarray(pred.values), manual, rtol=0, atol=0)


def test_single_class_fit_fails_loudly():
    frame = _synthetic_frame(40, seed=15)
    adapter = LR.LogisticRegressionAdapter()
    with pytest.raises((E.InvalidPredictionError, ValueError)):
        adapter.fit(frame, np.zeros(40))


def test_no_race_normalization():
    frame = _synthetic_frame(60, seed=16)
    y = _synthetic_target(60, seed=17)
    adapter = LR.LogisticRegressionAdapter()
    adapter.fit(frame, y)
    values = adapter.predict_positive_probability(frame)
    assert not np.allclose(values.sum(), 1.0)
    assert np.all(values >= 0.0) and np.all(values <= 1.0)


def test_validation_target_mutation_leaves_predictions_unchanged():
    frame = _synthetic_frame(100, seed=18)
    y_train = _synthetic_target(100, seed=19)
    adapter = LR.LogisticRegressionAdapter()
    adapter.fit(frame, y_train)
    before = adapter.predict_positive_probability(frame)
    y_mutated = 1.0 - y_train  # adversarial: flip every validation target
    after = adapter.predict_positive_probability(frame)
    assert y_mutated.tolist() != y_train.tolist()
    np.testing.assert_array_equal(before, after)


def test_deterministic_representative_refit():
    frame = _synthetic_frame(200, seed=20)
    y = _synthetic_target(200, seed=21)
    first = LR.LogisticRegressionAdapter().fit(frame, y)
    second = LR.LogisticRegressionAdapter().fit(frame, y)
    p1 = first.predict_positive_probability(frame)
    p2 = second.predict_positive_probability(frame)
    assert float(np.max(np.abs(p1 - p2))) == pytest.approx(0.0, abs=1e-12)


def test_fresh_pipeline_per_fold(canonical):
    d1 = S.materialize(canonical, "winner", "D1", "ALL_84")
    d2 = S.materialize(canonical, "winner", "D2", "ALL_84")
    a1 = LR.LogisticRegressionAdapter().fit(
        d1.X_train.iloc[:2000], d1.y_train.iloc[:2000])
    a2 = LR.LogisticRegressionAdapter().fit(
        d2.X_train.iloc[:2000], d2.y_train.iloc[:2000])
    assert a1._preprocessor is not a2._preprocessor
    assert a1._estimator is not a2._estimator
    with pytest.raises(E.ExperimentConfigError):
        a1.fit(d1.X_train.iloc[:100], d1.y_train.iloc[:100])


def test_coefficient_sanity_flags_failures():
    frame = _synthetic_frame(100, seed=22)
    adapter = LR.LogisticRegressionAdapter().fit(
        frame, _synthetic_target(100, seed=23))
    sanity = adapter.coefficient_sanity()
    assert sanity["transformed_dim"] == sanity["n_coefficients"]
    assert sanity["all_zero"] is False
    assert sanity["any_nan"] is False
    assert sanity["intercept_finite"] is True


# --- runner scope / holdout firewall ----------------------------------------------

def test_model_scope_enforced():
    with pytest.raises(E.ExperimentConfigError):
        MR.resolve_model("HGB")
    with pytest.raises(E.ExperimentConfigError):
        MR.resolve_model("XGBOOST")
    assert MR.resolve_model("LOGREG") == "logistic_regression"
    assert MR.resolve_model("logistic_regression") == "logistic_regression"


@pytest.mark.parametrize("fold", ["HOLDOUT", "2025", "FINAL_FIT", "D4"])
def test_development_folds_only(fold, tmp_path):
    with pytest.raises((E.ProtectedHoldoutError, E.ExperimentConfigError,
                        E.UnknownFoldError)):
        MR.run_model_experiment(task="winner", model="LOGREG", fold=fold,
                                root=tmp_path)


def test_task_and_seed_locked(tmp_path):
    with pytest.raises(E.ExperimentConfigError):
        MR.run_model_experiment(task="podium", model="LOGREG", fold="D1",
                                root=tmp_path)
    with pytest.raises(E.ExperimentConfigError):
        MR.run_model_experiment(task="winner", model="LOGREG", fold="D1",
                                seed=7, root=tmp_path)


def test_cli_rejects_unknown_model_task_and_holdout():
    with pytest.raises(E.ExperimentConfigError):
        MODELSCLI.main(["--model", "HGB", "--dry-run"])
    with pytest.raises(E.ExperimentConfigError):
        MODELSCLI.main(["--task", "podium", "--dry-run"])
    with pytest.raises(E.ProtectedHoldoutError):
        MODELSCLI.main(["--folds", "D1,HOLDOUT"])
    with pytest.raises(E.ProtectedHoldoutError):
        RUNCLI.main(["--model", "LOGREG", "--task", "winner",
                     "--fold", "HOLDOUT"])
    with pytest.raises(SystemExit):
        RUNCLI.main(["--model", "LOGREG", "--baseline", "CURRENT_LEADER",
                     "--task", "winner", "--fold", "D1"])


# --- full-data D1 integration through the M2 canonical path ------------------------

@pytest.fixture(scope="module")
def logreg_d1(tmp_path_factory):
    root = tmp_path_factory.mktemp("m3exp")
    return MR.run_model_experiment(task="winner", model="LOGREG", fold="D1",
                                   root=root, return_predictions=True)


def test_d1_experiment_round_trips(logreg_d1):
    config, result = RES.read_experiment(logreg_d1["dest"])
    assert config.experiment_id == result.experiment_id
    assert result.status is EX.ExperimentStatus.OK
    assert config.model_family == "logistic_regression"
    assert config.model_parameters == LR.logreg_model_parameters()
    assert config.holdout_accessed is False
    assert (config.training_rows, config.validation_rows) == (88123, 23577)
    assert result.artifact_refs["transformed_dim"] > 0
    assert result.artifact_refs["n_features_in"] == 84
    assert result.artifact_refs["sklearn_version"] == LR.SKLEARN_VERSION


def test_d1_canonical_metrics_present(logreg_d1):
    metrics = logreg_d1["result"].metrics
    for name in ("log_loss", "brier", "roc_auc", "pr_auc"):
        payload = metrics[name]
        assert payload["status"] == "OK"
        assert payload["race_macro"]["scope"] == "race_macro"
        assert payload["state_pooled"]["scope"] == "state_pooled"
    assert logreg_d1["result"].calibration is not None
    assert len(logreg_d1["result"].calibration["bins"]) == 10
    assert set(logreg_d1["result"].stage_metrics) == {
        "log_loss", "brier", "roc_auc", "pr_auc"}
    topk = logreg_d1["result"].race_metrics["winner_top_k"]
    assert topk["status"] == "OK"
    assert topk["min_observable_field_size"] == 2


def test_d1_predictions_finite_bounded_and_aligned(logreg_d1):
    values = np.asarray(logreg_d1["predictions"], dtype=float)
    assert len(values) == 23577
    assert np.all(np.isfinite(values))
    assert np.all(values >= 0.0) and np.all(values <= 1.0)


def test_d1_no_convergence_warnings(logreg_d1):
    assert logreg_d1["result"].artifact_refs["convergence_warnings"] == []


def test_d1_experiment_identity_deterministic(logreg_d1):
    first_id = logreg_d1["config"].experiment_id
    config = EX.build_config(
        "winner", "ALL_84", "D1", model_family="logistic_regression",
        seed=EX.PROJECT_SEED,
        model_parameters=LR.logreg_model_parameters(),
        preprocessing_config=PRE.preprocessing_contract_dict(),
        calibration_config={"method": "none"},
        training_rows=88123, training_races=81,
        validation_rows=23577, validation_races=22)
    assert config.experiment_id == first_id


# --- suite / comparison / report -----------------------------------------------------

def test_baseline_comparison_loaded_from_m2_artifacts():
    stored = MSUITE.load_baseline_suite()
    assert stored["task"] == "winner"
    assert stored["folds"] == ["D1", "D2", "D3"]
    assert stored["aggregates"]["CLASS_PRIOR"]["log_loss"]["mean"] == \
        pytest.approx(0.212238, abs=1e-6)
    assert stored["aggregates"]["CURRENT_LEADER"]["brier"]["mean"] == \
        pytest.approx(0.024165, abs=1e-6)
    assert stored["aggregates"]["CURRENT_LEADER"]["roc_auc"]["mean"] == \
        pytest.approx(0.882478, abs=1e-6)
    assert stored["aggregates"]["CURRENT_LEADER"]["pr_auc"]["mean"] == \
        pytest.approx(0.671751, abs=1e-6)


def test_verdict_semantics():
    assert MSUITE._verdict("lower", 0.2, 0.3) == "BEATS"
    assert MSUITE._verdict("lower", 0.4, 0.3) == "DOES NOT BEAT"
    assert MSUITE._verdict("higher", 0.9, 0.8) == "BEATS"
    assert MSUITE._verdict("higher", 0.7, 0.8) == "DOES NOT BEAT"
    assert MSUITE._verdict("lower", 0.25, 0.25) == "MATCHES"
    assert MSUITE._verdict("higher", None, 0.8) == "NOT_COMPARABLE"


def test_report_renders_from_summary_only():
    summary = {
        "task": "winner", "protocol_version": "v1",
        "matrix_content_hash": "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db",
        "model_spec": dict(LR.LOGREG_SPEC),
        "preprocessing_spec": PRE.preprocessing_contract_dict(),
        "sklearn_version": LR.SKLEARN_VERSION,
        "folds": ["D1"], "feature_set": "ALL_84", "seed": 42,
        "tuning": "none (fixed reference specification)",
        "calibration_fitted": "none (raw probabilities evaluated)",
        "probability_semantics": "INDEPENDENT_BINARY",
        "per_fold": {"D1": {
            "training_rows": 1, "training_races": 1, "train_prevalence": 0.05,
            "validation_rows": 2, "validation_races": 1, "n_features_in": 84,
            "transformed_dim": 90, "convergence_warnings": [],
            "metrics": {"log_loss": {
                "status": "OK",
                "race_macro": {"value": 0.123456},
                "state_pooled": {"value": 0.111111}},
                "brier": {
                "status": "OK",
                "race_macro": {"value": 0.02},
                "state_pooled": {"value": 0.019}},
                "roc_auc": {
                "status": "OK", "race_macro": {"value": 0.9},
                "state_pooled": {"value": 0.91}},
                "pr_auc": {
                "status": "OK", "race_macro": {"value": 0.6},
                "state_pooled": {"value": 0.61}}},
            "calibration_ece": 0.001, "calibration": {"bins": []},
            "stage_metrics": {"log_loss": {"status": "NOT_APPLICABLE"},
                              "brier": {"status": "NOT_APPLICABLE"}},
            "race_metrics": {"winner_top_k": {
                "status": "OK",
                "accuracy": {"top1": 0.7, "top3": 0.75},
                "n_evaluation_states": 10,
                "n_skipped_no_predictions": 0,
                "n_skipped_winner_unobservable": 1,
                "n_skipped_degenerate": 0,
                "min_observable_field_size": 2}},
            "latency": {"batch": {"mean": 0.5, "states_per_second": 4.0}},
            "fit_seconds": 1.0, "prediction_seconds": 2.0,
            "warnings": []}},
        "aggregates": {
            "log_loss": {"mean": 0.123456, "std": 0.0, "min": 0.123456,
                         "max": 0.123456},
            "brier": {"mean": 0.02, "std": 0.0, "min": 0.02, "max": 0.02},
            "roc_auc": {"mean": 0.9, "std": 0.0, "min": 0.9, "max": 0.9},
            "pr_auc": {"mean": 0.6, "std": 0.0, "min": 0.6, "max": 0.6},
            "expected_calibration_error": {"mean": 0.001},
            "winner_top_k": {"top1": {"mean": 0.7}, "top3": {"mean": 0.75}}},
        "baseline_comparison": {"log_loss": {
            "baseline": "CLASS_PRIOR", "per_fold": {"D1": {
                "model_value": 0.123456, "baseline_value": 0.214068,
                "difference": -0.090612, "verdict": "BEATS"}},
            "aggregate": {"model_mean": 0.123456,
                          "baseline_mean": 0.212238,
                          "difference": -0.088782, "verdict": "BEATS"}}},
        "determinism_check": {
            "fold": "D1", "same_experiment_id": True,
            "metrics_identical": True,
            "max_abs_probability_difference": 0.0},
        "runtime": {"total_seconds": 3.0},
        "peak_rss_bytes": None,
        "experiments": [{"model": "logistic_regression", "fold": "D1",
                         "experiment_id": "abc"}],
        "baseline_suite_schema": "v1",
    }
    report = MSUITE.render_logreg_report(summary)
    assert "2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED" in report
    assert "0.123456" in report  # stored value rendered verbatim, not recomputed
    assert "BEATS" in report


# --- static candidate guard ------------------------------------------------------------

def test_only_logreg_may_train():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "raceintel" / "model_lab"
    allowed_files = {
        "preprocessing.py": (),
        "logreg.py": ("LogisticRegression",),
        "model_runner.py": ("LogisticRegressionAdapter", "logreg"),
        "model_suite.py": ("logreg", "LogisticRegressionAdapter"),
        "run_models.py": ("LOGREG", "logistic_regression"),
    }
    forbidden = ("HistGradientBoosting", "XGBClassifier", "LGBMClassifier",
                 "LightGBM", "CatBoost", "ExtraTreesClassifier",
                 "RandomForestClassifier", "MLPClassifier", "import torch",
                 "from torch", "GridSearchCV", "RandomizedSearchCV", "Optuna",
                 "optuna", "MLflow", "mlflow", "SMOTE", "imbalanced_learn")
    for name, allowed_tokens in allowed_files.items():
        text = (root / name).read_text()
        for token in forbidden:
            assert token not in text, f"{name}: forbidden {token!r}"
        if name == "logreg.py":
            for token in allowed_tokens:
                assert token in text
    for name in ("runner.py", "run.py", "suite.py", "run_baselines.py"):
        text = (root / name).read_text()
        assert "LogisticRegression" not in text, f"{name}: M2 files stay non-ML"


def test_no_new_dependencies_declared():
    from pathlib import Path
    for name in ("requirements.txt", "requirements-test.txt"):
        text = (Path(__file__).resolve().parents[1] / name).read_text()
        lowered = text.lower()
        for dep in ("lightgbm", "catboost", "optuna", "mlflow", "torch",
                    "tabpfn", "imbalanced"):
            assert dep not in lowered, f"{name}: new dependency {dep!r}"


def test_m2_files_do_not_train_models():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "raceintel" / "model_lab"
    for name in ("runner.py", "run.py", "suite.py", "run_baselines.py"):
        text = (root / name).read_text()
        assert "from sklearn" not in text and "import sklearn" not in text


# --- M1.1 applicability through the model path ----------------------------------------------

def test_model_metrics_route_through_applicability_guard(logreg_d1):
    from raceintel.model_lab import metrics as M
    M.require_metric_applicability(
        PR.PredictionKind.BINARY_PROBABILITY, "log_loss")
    M.require_metric_applicability(
        PR.PredictionKind.BINARY_PROBABILITY,
        "expected_calibration_error")
    metrics = logreg_d1["result"].metrics
    assert metrics["log_loss"]["status"] == "OK"
    assert logreg_d1["result"].calibration["expected_calibration_error"] \
        is not None
