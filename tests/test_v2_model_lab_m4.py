"""M4 tests: HGB/XGB fixed specs, adapters, runner, firewalls, suite derivation.

Focused safety/leakage coverage for the two fixed nonlinear candidates.
Synthetic fixtures prove train-only fitting, transform-only validation,
positive-class resolution, INDEPENDENT_BINARY semantics, label/identity
firewalls, fold isolation, target firewalls and determinism. Full-data D1
integration tests prove the exact M2 canonical evaluator path on isolated
experiment roots. Suite-derivation tests prove the summary and report trace
to stored experiment/M3/M2 artifacts. The 2025 holdout is never evaluated.
"""

import numpy as np
import pandas as pd
import pytest

from model_lab_helpers import (
    load_canonical_or_skip,
    load_json_artifact_or_skip,
    require_matrix,
)
from raceintel.model_lab import data as D
from raceintel.model_lab import errors as E
from raceintel.model_lab import experiment as EX
from raceintel.model_lab import model_suite as MSUITE
from raceintel.model_lab import nonlinear_runner as NR
from raceintel.model_lab import nonlinear_suite as NSUITE
from raceintel.model_lab import preprocessing as PRE
from raceintel.model_lab import predictions as PR
from raceintel.model_lab import results as RES
from raceintel.model_lab import run_nonlinear as NLCLI
from raceintel.model_lab import runner as RUN
from raceintel.model_lab import splits as S
from raceintel.model_lab import tree_candidates as TC


@pytest.fixture(scope="module")
def canonical():
    return load_canonical_or_skip()


@pytest.fixture(scope="module")
def schema(canonical):
    return canonical.schema


def _synthetic_frame(n: int = 200, seed: int = 7) -> pd.DataFrame:
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


def _fresh_adapter(family: str):
    if family == TC.HGB_FAMILY:
        return TC.HistGradientBoostingAdapter()
    if family == TC.XGB_FAMILY:
        return TC.XGBoostAdapter()
    raise AssertionError(family)


# --- fixed specifications (chosen before observing validation) -----------------

def test_fixed_hgb_specification():
    spec = TC.hgb_model_parameters()
    assert spec["estimator"] == "HistGradientBoostingClassifier"
    assert spec["loss"] == "log_loss"
    assert spec["learning_rate"] == 0.1
    assert spec["max_iter"] == 100
    assert spec["max_leaf_nodes"] == 31
    assert spec["max_depth"] is None
    assert spec["min_samples_leaf"] == 20
    assert spec["l2_regularization"] == 0.0
    assert spec["max_bins"] == 255
    # The single justified non-default: default "auto" would hold out 10%
    # of training rows for early stopping (validation-driven training).
    assert spec["early_stopping"] is False
    assert spec["class_weight"] is None
    assert spec["random_state"] == 42
    est = TC.build_hgb_estimator()
    assert est.early_stopping is False
    assert est.max_iter == 100 and est.random_state == 42


def test_fixed_xgb_specification():
    spec = TC.xgb_model_parameters()
    assert spec["estimator"] == "XGBClassifier"
    assert spec["objective"] == "binary:logistic"
    assert spec["n_estimators"] == 200
    assert spec["max_depth"] == 4
    assert spec["learning_rate"] == 0.1
    assert spec["subsample"] == 1.0
    assert spec["colsample_bytree"] == 1.0
    assert spec["min_child_weight"] == 1
    assert spec["reg_lambda"] == 1.0
    assert spec["reg_alpha"] == 0.0
    assert spec["tree_method"] == "hist"
    assert spec["eval_metric"] == "logloss"
    assert spec["scale_pos_weight"] == 1
    assert spec["random_state"] == 42
    assert spec["n_jobs"] == 4
    est = TC.build_xgb_estimator()
    assert est.max_depth == 4 and est.n_estimators == 200
    assert est.random_state == 42


def test_no_rebalancing_or_resampling():
    for spec_fn in (TC.hgb_model_parameters, TC.xgb_model_parameters):
        spec = spec_fn()
        assert "balanced" not in str(spec)
    assert TC.XGB_SPEC["scale_pos_weight"] == 1
    assert TC.HGB_SPEC["class_weight"] is None
    assert TC.M4_TASK == "winner"
    assert TC.M4_FEATURE_SET == "ALL_84"
    assert TC.M4_SEED == EX.PROJECT_SEED


def test_only_two_candidate_families_registered():
    assert sorted(TC.ADAPTERS) == ["hist_gradient_boosting", "xgboost"]
    assert NR.resolve_model("HGB") == "hist_gradient_boosting"
    assert NR.resolve_model("hist_gradient_boosting") == \
        "hist_gradient_boosting"
    assert NR.resolve_model("XGB") == "xgboost"
    assert NR.resolve_model("XGBOOST") == "xgboost"
    assert NR.resolve_model("xgboost") == "xgboost"
    for bad in ("LOGREG", "logistic_regression", "RandomForest",
                "LightGBM", "CatBoost", "MLP", ""):
        with pytest.raises(E.ExperimentConfigError):
            NR.resolve_model(bad)


@pytest.mark.parametrize("family", [TC.HGB_FAMILY, TC.XGB_FAMILY])
def test_adapters_satisfy_model_adapter_contract(family):
    assert isinstance(_fresh_adapter(family), EX.ModelAdapter)


# --- positive class / prediction semantics -------------------------------------

@pytest.mark.parametrize("family", [TC.HGB_FAMILY, TC.XGB_FAMILY])
def test_positive_class_probability_resolution(family):
    frame = _synthetic_frame(200, seed=21)
    y = _synthetic_target(200, seed=22)
    adapter = _fresh_adapter(family)
    adapter.fit(frame, y)
    assert adapter._positive_index == \
        int(list(adapter._estimator.classes_).index(1))
    raw = np.asarray(
        adapter._estimator.predict_proba(adapter._matrix_for(frame)))
    np.testing.assert_allclose(
        adapter.predict_positive_probability(frame), raw[:, 1])


@pytest.mark.parametrize("family", [TC.HGB_FAMILY, TC.XGB_FAMILY])
def test_binary_probability_independent_semantics_no_normalization(family):
    frame = _synthetic_frame(120, seed=23)
    y = _synthetic_target(120, seed=24)
    adapter = _fresh_adapter(family)
    adapter.fit(frame, y)
    result = adapter.predict_result(
        frame, [f"state-{i}" for i in range(len(frame))])
    assert result.kind is PR.PredictionKind.BINARY_PROBABILITY
    assert result.semantics is PR.ProbabilitySemantics.INDEPENDENT_BINARY
    assert result.positive_class == 1
    # No post-processing: PredictionResult values are the raw probabilities.
    np.testing.assert_allclose(
        np.asarray(result.values), adapter.predict(frame))
    # Independent per-driver probabilities do not form a race distribution:
    # a full frame treated as one field must not sum to 1 in general.
    assert abs(float(np.sum(result.values)) - 1.0) > 1e-6


# --- preprocessing: train-only fitting ----------------------------------------

@pytest.mark.parametrize("family", [TC.HGB_FAMILY, TC.XGB_FAMILY])
def test_preprocessor_fits_train_statistics_only(family, schema):
    train = _synthetic_frame(200, seed=31)
    col_name = schema.numeric[0]
    train.loc[train.index[::2], col_name] = np.nan
    expected_median = float(np.nanmedian(train[col_name].to_numpy()))
    adapter = _fresh_adapter(family)
    adapter.fit(train, _synthetic_target(len(train), seed=32))
    num_pipe = adapter._preprocessor.transformer.named_transformers_["num"]
    medians = num_pipe.named_steps["impute"].statistics_
    col = list(adapter._preprocessor.numeric_columns).index(col_name)
    assert float(medians[col]) == pytest.approx(expected_median)


@pytest.mark.parametrize("family", [TC.HGB_FAMILY, TC.XGB_FAMILY])
def test_validation_extremes_do_not_alter_train_preprocessing(family, schema):
    train = _synthetic_frame(200, seed=33)
    adapter = _fresh_adapter(family)
    adapter.fit(train, _synthetic_target(len(train), seed=34))
    num_pipe = adapter._preprocessor.transformer.named_transformers_["num"]
    before = np.asarray(
        num_pipe.named_steps["impute"].statistics_, dtype=float).copy()
    val = _synthetic_frame(50, seed=35)
    val.loc[:, schema.numeric[0]] = 1e9  # extreme validation values
    out = adapter._preprocessor.transform(val)
    assert np.all(np.isfinite(out))
    after = np.asarray(
        num_pipe.named_steps["impute"].statistics_, dtype=float)
    np.testing.assert_array_equal(before, after)


@pytest.mark.parametrize("family", [TC.HGB_FAMILY, TC.XGB_FAMILY])
def test_unseen_validation_categories_do_not_refit(family):
    train = _synthetic_frame(200, seed=36)
    adapter = _fresh_adapter(family)
    adapter.fit(train, _synthetic_target(len(train), seed=37))
    dim = adapter._preprocessor.output_dim
    val = _synthetic_frame(40, seed=38)
    val.loc[:, "compound"] = "NEVER_SEEN_COMPOUND"
    out = adapter.predict_positive_probability(val)
    assert out.shape == (40,)
    assert np.all(np.isfinite(out))
    assert adapter._preprocessor.output_dim == dim


@pytest.mark.parametrize("family", [TC.HGB_FAMILY, TC.XGB_FAMILY])
def test_no_labels_masks_or_identity_in_X(family):
    frame = _synthetic_frame(100, seed=39)
    frame["is_winner"] = 0
    with pytest.raises(E.ExperimentConfigError):
        _fresh_adapter(family).fit(frame, _synthetic_target(100, seed=40))
    frame2 = _synthetic_frame(100, seed=41)
    frame2["race_id"] = "2019-r01-R"
    with pytest.raises(E.ExperimentConfigError):
        _fresh_adapter(family).fit(frame2, _synthetic_target(100, seed=42))


# --- fit firewalls --------------------------------------------------------------

@pytest.mark.parametrize("family", [TC.HGB_FAMILY, TC.XGB_FAMILY])
def test_fresh_adapter_per_fold(family):
    frame = _synthetic_frame(120, seed=43)
    y = _synthetic_target(120, seed=44)
    adapter = _fresh_adapter(family)
    adapter.fit(frame, y)
    with pytest.raises(E.ExperimentConfigError):
        adapter.fit(frame, y)


@pytest.mark.parametrize("family", [TC.HGB_FAMILY, TC.XGB_FAMILY])
def test_estimator_fit_receives_train_only(family):
    train = _synthetic_frame(160, seed=45)
    y_train = _synthetic_target(160, seed=46)
    val = _synthetic_frame(40, seed=47)
    seen: dict = {}
    adapter = _fresh_adapter(family)
    estimator = adapter._build_estimator()
    original_fit = estimator.fit

    def recording_fit(X, y, **kwargs):
        seen["n"] = int(np.asarray(y).shape[0])
        seen["y_sum"] = float(np.asarray(y).sum())
        seen["eval_set"] = kwargs.get("eval_set", None)
        return original_fit(X, y)

    estimator.fit = recording_fit
    adapter._build_estimator = lambda: estimator
    adapter.fit(train, y_train)
    # Validation targets (length 40) never reach the estimator.
    assert seen["n"] == len(y_train) == 160
    assert seen["y_sum"] == pytest.approx(float(y_train.sum()))
    assert seen["eval_set"] is None
    assert len(val) == 40  # validation exists; it was never fitted on


@pytest.mark.parametrize("family", [TC.HGB_FAMILY, TC.XGB_FAMILY])
def test_y_val_mutation_does_not_alter_predictions(family):
    train = _synthetic_frame(160, seed=48)
    val = _synthetic_frame(40, seed=49)
    y_val = _synthetic_target(40, seed=50)
    adapter = _fresh_adapter(family)
    adapter.fit(train, _synthetic_target(160, seed=51))
    before = adapter.predict_positive_probability(val)
    y_val[:] = 1.0 - y_val  # mutate the validation labels after fitting
    y_val[:] = 0.0
    after = adapter.predict_positive_probability(val)
    np.testing.assert_array_equal(before, after)


@pytest.mark.parametrize("family", [TC.HGB_FAMILY, TC.XGB_FAMILY])
def test_probabilities_finite_bounded_and_non_degenerate(family):
    frame = _synthetic_frame(200, seed=52)
    adapter = _fresh_adapter(family)
    adapter.fit(frame, _synthetic_target(200, seed=53))
    values = adapter.predict_positive_probability(frame)
    assert np.all(np.isfinite(values))
    assert np.all(values >= 0.0) and np.all(values <= 1.0)
    assert float(np.std(values)) > 0.0
    sanity = adapter.training_sanity()
    assert sanity["transformed_dim"] > 0
    assert sanity["classes"] == [0, 1]


@pytest.mark.parametrize("family", [TC.HGB_FAMILY, TC.XGB_FAMILY])
def test_synthetic_refit_is_deterministic(family):
    frame = _synthetic_frame(200, seed=54)
    y = _synthetic_target(200, seed=55)
    first = _fresh_adapter(family).fit(frame, y)
    second = _fresh_adapter(family).fit(frame, y)
    diff = float(np.max(np.abs(
        first.predict_positive_probability(frame)
        - second.predict_positive_probability(frame))))
    assert diff == 0.0


# --- runner scope / holdout firewall --------------------------------------------

@pytest.mark.parametrize("fold", ["HOLDOUT", "2025", "FINAL_FIT", "D4"])
def test_development_folds_only(fold, tmp_path):
    with pytest.raises((E.ProtectedHoldoutError, E.ExperimentConfigError,
                        E.UnknownFoldError)):
        NR.run_nonlinear_experiment(task="winner", model="HGB", fold=fold,
                                    root=tmp_path)
    with pytest.raises((E.ProtectedHoldoutError, E.ExperimentConfigError,
                        E.UnknownFoldError)):
        NR.run_nonlinear_experiment(task="winner", model="XGB", fold=fold,
                                    root=tmp_path)


def test_task_and_seed_locked(tmp_path):
    with pytest.raises(E.ExperimentConfigError):
        NR.run_nonlinear_experiment(task="podium", model="HGB", fold="D1",
                                    root=tmp_path)
    with pytest.raises(E.ExperimentConfigError):
        NR.run_nonlinear_experiment(task="winner", model="HGB", fold="D1",
                                    seed=7, root=tmp_path)
    with pytest.raises(E.ExperimentConfigError):
        NR.run_nonlinear_experiment(task="winner", model="XGB", fold="D1",
                                    seed=7, root=tmp_path)


def test_cli_rejects_unknown_model_task_and_holdout():
    with pytest.raises(E.ExperimentConfigError):
        NLCLI.main(["--model", "LOGREG", "--dry-run"])
    with pytest.raises(E.ExperimentConfigError):
        NLCLI.main(["--model", "RandomForest", "--dry-run"])
    with pytest.raises(E.ExperimentConfigError):
        NLCLI.main(["--model", "ALL", "--task", "podium", "--dry-run"])
    with pytest.raises(E.ProtectedHoldoutError):
        NLCLI.main(["--model", "ALL", "--folds", "D1,HOLDOUT", "--dry-run"])
    with pytest.raises(E.ExperimentConfigError):
        NLCLI.main(["--model", "HGB", "--folds", "D1,D2,D3"])


def test_no_2025_in_development_materialization(canonical):
    for fold in ("D1", "D2", "D3"):
        dataset = S.materialize(canonical, "winner", fold, "ALL_84")
        seasons = set(dataset.validation_metadata["season"].astype(int))
        assert 2025 not in seasons
        assert max(dataset.train_metadata["season"].astype(int)) < min(
            seasons)


# --- exact M2/M3 evaluator reuse (no duplicate metric implementation) -----------

def test_runner_delegates_to_canonical_evaluators():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "raceintel" / "model_lab"
            / "nonlinear_runner.py").read_text()
    for token in ("RUN.evaluate_row_metrics", "RUN.evaluate_stages",
                  "RUN.evaluate_calibration", "RUN.evaluate_winner_top_k",
                  "RUN._align_validation", "RUN._finite_mask",
                  "RES.write_experiment", "EX.build_config",
                  "SPLITS.materialize", "RUN.resolve_development_fold",
                  "RUN._check_no_holdout_rows"):
        assert token in text, f"nonlinear_runner must delegate via {token}"
    for token in ("def log_loss", "def brier", "def roc_auc", "def pr_auc",
                  "def expected_calibration", "def evaluate_top",
                  "GridSearchCV", "RandomizedSearchCV", "optuna",
                  "CalibratedClassifierCV", "SMOTE"):
        assert token not in text, f"nonlinear_runner: forbidden {token!r}"


# --- full-data D1 integration through the M2 canonical path ---------------------

@pytest.fixture(scope="module")
def hgb_d1(tmp_path_factory):
    root = tmp_path_factory.mktemp("m4hgb")
    return NR.run_nonlinear_experiment(task="winner", model="HGB", fold="D1",
                                       root=root, return_predictions=True)


@pytest.fixture(scope="module")
def xgb_d1(tmp_path_factory):
    root = tmp_path_factory.mktemp("m4xgb")
    return NR.run_nonlinear_experiment(task="winner", model="XGB", fold="D1",
                                       root=root, return_predictions=True)


@pytest.mark.parametrize("fixture_name,family",
                         [("hgb_d1", "hist_gradient_boosting"),
                          ("xgb_d1", "xgboost")])
def test_d1_experiment_round_trips(fixture_name, family, request):
    out = request.getfixturevalue(fixture_name)
    config, result = RES.read_experiment(out["dest"])
    assert config.experiment_id == result.experiment_id
    assert result.status is EX.ExperimentStatus.OK
    assert config.model_family == family
    assert config.holdout_accessed is False
    assert (config.training_rows, config.validation_rows) == (88123, 23577)
    assert result.artifact_refs["transformed_dim"] > 0
    assert result.artifact_refs["n_features_in"] == 84


@pytest.mark.parametrize("fixture_name", ["hgb_d1", "xgb_d1"])
def test_d1_canonical_metrics_present(fixture_name, request):
    out = request.getfixturevalue(fixture_name)
    metrics = out["result"].metrics
    for name in ("log_loss", "brier", "roc_auc", "pr_auc"):
        payload = metrics[name]
        assert payload["status"] == "OK"
        assert payload["race_macro"]["scope"] == "race_macro"
        assert payload["state_pooled"]["scope"] == "state_pooled"
    assert out["result"].calibration is not None
    assert len(out["result"].calibration["bins"]) == 10
    assert set(out["result"].stage_metrics) == {
        "log_loss", "brier", "roc_auc", "pr_auc"}
    topk = out["result"].race_metrics["winner_top_k"]
    assert topk["status"] == "OK"
    assert topk["min_observable_field_size"] == 2


@pytest.mark.parametrize("fixture_name", ["hgb_d1", "xgb_d1"])
def test_d1_predictions_finite_bounded_and_aligned(fixture_name, request):
    out = request.getfixturevalue(fixture_name)
    values = np.asarray(out["predictions"], dtype=float)
    assert len(values) == 23577
    assert np.all(np.isfinite(values))
    assert np.all(values >= 0.0) and np.all(values <= 1.0)


def test_d1_experiment_identity_deterministic(hgb_d1, xgb_d1):
    for out, spec_fn in ((hgb_d1, TC.hgb_model_parameters),
                         (xgb_d1, TC.xgb_model_parameters)):
        first_id = out["config"].experiment_id
        config = EX.build_config(
            "winner", "ALL_84", "D1",
            model_family=out["config"].model_family,
            seed=EX.PROJECT_SEED, model_parameters=spec_fn(),
            preprocessing_config=PRE.preprocessing_contract_dict(),
            calibration_config={"method": "none"},
            training_rows=88123, training_races=81,
            validation_rows=23577, validation_races=22)
        assert config.experiment_id == first_id


def test_model_metrics_route_through_applicability_guard(hgb_d1, xgb_d1):
    from raceintel.model_lab import metrics as M
    M.require_metric_applicability(
        PR.PredictionKind.BINARY_PROBABILITY, "log_loss")
    M.require_metric_applicability(
        PR.PredictionKind.BINARY_PROBABILITY,
        "expected_calibration_error")
    for out in (hgb_d1, xgb_d1):
        assert out["result"].metrics["log_loss"]["status"] == "OK"
        assert out["result"].calibration[
            "expected_calibration_error"] is not None


# --- static candidate guard -------------------------------------------------------

def test_only_hgb_and_xgb_may_train_in_m4():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "raceintel" / "model_lab"
    allowed = {
        "tree_candidates.py": ("HistGradientBoostingClassifier",
                               "XGBClassifier"),
        "nonlinear_runner.py": ("tree_candidates", "TC.ADAPTERS",
                                "BINARY_PROBABILITY"),
        "nonlinear_suite.py": ("hist_gradient_boosting", "xgboost"),
        "run_nonlinear.py": ("HGB", "XGB"),
    }
    forbidden = ("LGBMClassifier", "LightGBM", "CatBoost",
                 "ExtraTreesClassifier", "RandomForestClassifier",
                 "MLPClassifier", "import torch", "from torch",
                 "GridSearchCV", "RandomizedSearchCV", "BayesSearchCV",
                 "Optuna", "optuna", "hyperopt", "MLflow", "mlflow",
                 "SMOTE", "imbalanced_learn", "CalibratedClassifierCV",
                 "TabPFN", "tabpfn", "LogisticRegression")
    for name, allowed_tokens in allowed.items():
        text = (root / name).read_text()
        for token in forbidden:
            assert token not in text, f"{name}: forbidden {token!r}"
        for token in allowed_tokens:
            assert token in text, f"{name}: missing {token!r}"
    for name in ("tree_candidates.py", "nonlinear_runner.py"):
        text = (root / name).read_text()
        # No estimator fit may receive a validation eval set (which would
        # enable validation-driven early stopping).
        assert "eval_set=" not in text, f"{name}: eval set supplied to fit"


def test_no_tuning_or_calibration_apis_in_m4():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "raceintel" / "model_lab"
    forbidden = ("GridSearchCV", "RandomizedSearchCV", "BayesSearchCV",
                 "ParameterSampler", "optuna", "hyperopt",
                 "CalibratedClassifierCV", "IsotonicRegression",
                 "SigmoidCalibration", "temperature_scale")
    # Note: scale_pos_weight / class_weight appear in tree_candidates.py with
    # neutral values only (1 / None); their VALUES are pinned by
    # test_no_rebalancing_or_resampling, not by token absence.
    for name in ("tree_candidates.py", "nonlinear_runner.py",
                 "nonlinear_suite.py", "run_nonlinear.py"):
        text = (root / name).read_text()
        for token in forbidden:
            assert token not in text, f"{name}: forbidden {token!r}"


def test_no_new_dependencies_declared():
    from pathlib import Path
    for name in ("requirements.txt", "requirements-test.txt"):
        text = (Path(__file__).resolve().parents[1] / name).read_text()
        lowered = text.lower()
        for dep in ("lightgbm", "catboost", "optuna", "mlflow", "torch",
                    "tabpfn", "imbalanced"):
            assert dep not in lowered, f"{name}: new dependency {dep!r}"


def test_m3_and_m2_files_untouched_by_m4():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "raceintel" / "model_lab"
    for name in ("model_runner.py", "model_suite.py", "run_models.py",
                 "logreg.py", "runner.py", "run.py", "suite.py",
                 "run_baselines.py"):
        text = (root / name).read_text()
        assert "HistGradientBoosting" not in text, f"{name}: M4 leakage"
        assert "XGBClassifier" not in text, f"{name}: M4 leakage"
        assert "tree_candidates" not in text, f"{name}: M4 leakage"


# --- suite summary + report derivation --------------------------------------------

def _load_m4_summary():
    return load_json_artifact_or_skip(
        NSUITE.default_out(), purpose="M4 suite summary")


def test_m4_summary_covers_six_experiments():
    summary = _load_m4_summary()
    assert summary["schema_version"] == "v1"
    assert summary["models"] == ["hist_gradient_boosting", "xgboost"]
    assert summary["folds"] == ["D1", "D2", "D3"]
    assert summary["task"] == "winner"
    assert summary["feature_set"] == "ALL_84"
    assert summary["seed"] == 42
    assert summary["holdout_accessed"] is False
    assert summary["tuning"].startswith("none ")
    assert summary["calibration_fitted"].startswith("none ")
    assert summary["probability_semantics"] == "INDEPENDENT_BINARY"
    for family in ("hist_gradient_boosting", "xgboost"):
        node = summary["per_model"][family]
        assert sorted(node["per_fold"]) == ["D1", "D2", "D3"]
        assert len(node["experiments"]) == 3


def test_m4_summary_derived_from_stored_results():
    summary = _load_m4_summary()
    for family in ("hist_gradient_boosting", "xgboost"):
        for fold in ("D1", "D2", "D3"):
            entry = summary["per_model"][family]["per_fold"][fold]
            matches = [
                e for e in summary["per_model"][family]["experiments"]
                if e["fold"] == fold]
            assert len(matches) == 1
            config, result = RES.read_experiment(matches[0]["dest"])
            assert entry["experiment_id"] == config.experiment_id
            stored_ll = result.metrics["log_loss"]["race_macro"]["value"]
            assert entry["metrics"]["log_loss"]["race_macro"]["value"] == \
                pytest.approx(stored_ll)


def test_m4_logreg_comparison_uses_stored_m3_artifacts():
    import json
    summary = _load_m4_summary()
    with open(NSUITE.logreg_suite_path(), encoding="utf-8") as fh:
        logreg = json.load(fh)
    node = summary["vs_logreg_reference"]["log_loss"]["per_fold"]["D1"][
        "hist_gradient_boosting"]
    assert node["reference_value"] == pytest.approx(
        logreg["per_fold"]["D1"]["metrics"]["log_loss"]["race_macro"][
            "value"])
    assert node["model_value"] == pytest.approx(
        summary["per_model"]["hist_gradient_boosting"]["per_fold"]["D1"][
            "metrics"]["log_loss"]["race_macro"]["value"])
    assert node["difference"] == pytest.approx(
        node["model_value"] - node["reference_value"])
    assert node["verdict"] in ("BEATS", "MATCHES", "DOES NOT BEAT")


def test_m4_floor_comparison_uses_stored_m2_artifacts():
    summary = _load_m4_summary()
    stored = MSUITE.load_baseline_suite()
    assert stored["task"] == "winner"
    node = summary["vs_baseline_floor"]["log_loss"]["per_fold"]["D1"][
        "xgboost"]
    assert node["baseline_value"] == pytest.approx(
        stored["per_fold"]["D1"]["CLASS_PRIOR"]["metrics"]["log_loss"][
            "race_macro"]["value"])
    assert node["verdict"] in ("BEATS", "MATCHES", "DOES NOT BEAT")


def test_m4_determinism_checks_recorded():
    summary = _load_m4_summary()
    for family in ("hist_gradient_boosting", "xgboost"):
        det = summary["per_model"][family]["determinism_check"]
        assert det["fold"] == "D1"
        assert det["same_experiment_id"] is True
        assert det["metrics_identical"] is True
        assert det["max_abs_probability_difference"] == 0.0


def test_m4_report_renders_from_summary_only():
    summary = _load_m4_summary()
    report = NSUITE.render_nonlinear_report(summary)
    assert "2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED" in report
    assert "DEVELOPMENT RESULTS — 2022 / 2023 / 2024" in report
    # Stored values render verbatim, not recomputed.
    probe = summary["per_model"]["hist_gradient_boosting"]["per_fold"][
        "D1"]["metrics"]["log_loss"]["race_macro"]["value"]
    assert f"{probe:.6f}" in report
