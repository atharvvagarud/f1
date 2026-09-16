"""M5 tests: ExtraTrees/RandomForest fixed specs, adapters, runner, firewalls.

Focused safety/leakage coverage for the two fixed bagged-tree candidates.
Synthetic fixtures prove train-only fitting, transform-only validation,
positive-class resolution, INDEPENDENT_BINARY semantics, label/identity
firewalls, fold isolation, target firewalls and determinism. Full-data D1
integration tests prove the exact M2 canonical evaluator path on isolated
experiment roots. Suite-derivation tests prove the summary and report trace
to stored experiment/M3/M4/M2 artifacts. The 2025 holdout is never
evaluated.
"""

import numpy as np
import pandas as pd
import pytest

from model_lab_helpers import (
    load_canonical_or_skip,
    load_json_artifact_or_skip,
    require_matrix,
)
from v2.model_lab import bagged_candidates as BC
from v2.model_lab import bagged_runner as BR
from v2.model_lab import bagged_suite as BS
from v2.model_lab import data as D
from v2.model_lab import errors as E
from v2.model_lab import experiment as EX
from v2.model_lab import model_suite as MSUITE
from v2.model_lab import predictions as PR
from v2.model_lab import preprocessing as PRE
from v2.model_lab import results as RES
from v2.model_lab import run_bagged as BCLI
from v2.model_lab import splits as S


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
    if family == BC.EXTRA_TREES_FAMILY:
        return BC.ExtraTreesAdapter()
    if family == BC.RANDOM_FOREST_FAMILY:
        return BC.RandomForestAdapter()
    raise AssertionError(family)


# --- fixed specifications (chosen before observing validation) -----------------

def test_fixed_extra_trees_specification():
    spec = BC.extra_trees_model_parameters()
    assert spec["estimator"] == "ExtraTreesClassifier"
    assert spec["n_estimators"] == 300
    assert spec["criterion"] == "gini"
    assert spec["max_depth"] is None
    assert spec["min_samples_split"] == 2
    assert spec["min_samples_leaf"] == 1
    assert spec["max_features"] == "sqrt"
    assert spec["bootstrap"] is False
    assert spec["class_weight"] is None
    assert spec["n_jobs"] == 4
    assert spec["random_state"] == 42
    est = BC.build_extra_trees_estimator()
    assert est.bootstrap is False
    assert est.n_estimators == 300 and est.n_jobs == 4
    assert est.random_state == 42


def test_fixed_random_forest_specification():
    spec = BC.random_forest_model_parameters()
    assert spec["estimator"] == "RandomForestClassifier"
    assert spec["n_estimators"] == 300
    assert spec["criterion"] == "gini"
    assert spec["max_depth"] is None
    assert spec["min_samples_split"] == 2
    assert spec["min_samples_leaf"] == 1
    assert spec["max_features"] == "sqrt"
    assert spec["bootstrap"] is True
    assert spec["class_weight"] is None
    assert spec["n_jobs"] == 4
    assert spec["random_state"] == 42
    est = BC.build_random_forest_estimator()
    assert est.bootstrap is True
    assert est.n_estimators == 300 and est.n_jobs == 4
    assert est.random_state == 42


def test_no_rebalancing_or_resampling():
    for spec_fn in (BC.extra_trees_model_parameters,
                    BC.random_forest_model_parameters):
        spec = spec_fn()
        assert "balanced" not in str(spec)
        assert spec["class_weight"] is None
    assert BC.M5_TASK == "winner"
    assert BC.M5_FEATURE_SET == "ALL_84"
    assert BC.M5_SEED == EX.PROJECT_SEED


def test_only_two_candidate_families_registered():
    assert sorted(BC.ADAPTERS) == ["extra_trees", "random_forest"]
    assert BR.resolve_model("EXTRATREES") == "extra_trees"
    assert BR.resolve_model("ET") == "extra_trees"
    assert BR.resolve_model("RF") == "random_forest"
    assert BR.resolve_model("RANDOMFOREST") == "random_forest"
    assert BR.resolve_model("random_forest") == "random_forest"
    for bad in ("LOGREG", "logistic_regression", "HGB", "XGB",
                "LightGBM", "CatBoost", "MLP", ""):
        with pytest.raises(E.ExperimentConfigError):
            BR.resolve_model(bad)


@pytest.mark.parametrize("family", [BC.EXTRA_TREES_FAMILY,
                                    BC.RANDOM_FOREST_FAMILY])
def test_adapters_satisfy_model_adapter_contract(family):
    assert isinstance(_fresh_adapter(family), EX.ModelAdapter)


# --- positive class / prediction semantics -------------------------------------

@pytest.mark.parametrize("family", [BC.EXTRA_TREES_FAMILY,
                                    BC.RANDOM_FOREST_FAMILY])
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
        adapter.predict_positive_probability(frame),
        raw[:, adapter._positive_index])


@pytest.mark.parametrize("family", [BC.EXTRA_TREES_FAMILY,
                                    BC.RANDOM_FOREST_FAMILY])
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
    np.testing.assert_allclose(
        np.asarray(result.values), adapter.predict(frame))
    assert abs(float(np.sum(result.values)) - 1.0) > 1e-6


@pytest.mark.parametrize("family", [BC.EXTRA_TREES_FAMILY,
                                    BC.RANDOM_FOREST_FAMILY])
def test_configured_tree_count_is_fitted(family):
    frame = _synthetic_frame(160, seed=25)
    adapter = _fresh_adapter(family)
    adapter.fit(frame, _synthetic_target(160, seed=26))
    sanity = adapter.training_sanity()
    assert sanity["n_estimators_configured"] == 300
    assert sanity["fitted_tree_count"] == 300
    assert len(adapter._estimator.estimators_) == 300
    assert sanity["classes"] == [0, 1]


# --- preprocessing: train-only fitting ----------------------------------------

@pytest.mark.parametrize("family", [BC.EXTRA_TREES_FAMILY,
                                    BC.RANDOM_FOREST_FAMILY])
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


@pytest.mark.parametrize("family", [BC.EXTRA_TREES_FAMILY,
                                    BC.RANDOM_FOREST_FAMILY])
def test_validation_extremes_do_not_alter_train_preprocessing(family, schema):
    train = _synthetic_frame(200, seed=33)
    adapter = _fresh_adapter(family)
    adapter.fit(train, _synthetic_target(len(train), seed=34))
    num_pipe = adapter._preprocessor.transformer.named_transformers_["num"]
    before = np.asarray(
        num_pipe.named_steps["impute"].statistics_, dtype=float).copy()
    val = _synthetic_frame(50, seed=35)
    val.loc[:, schema.numeric[0]] = 1e9
    out = adapter._preprocessor.transform(val)
    assert np.all(np.isfinite(out))
    after = np.asarray(
        num_pipe.named_steps["impute"].statistics_, dtype=float)
    np.testing.assert_array_equal(before, after)


@pytest.mark.parametrize("family", [BC.EXTRA_TREES_FAMILY,
                                    BC.RANDOM_FOREST_FAMILY])
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


@pytest.mark.parametrize("family", [BC.EXTRA_TREES_FAMILY,
                                    BC.RANDOM_FOREST_FAMILY])
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

@pytest.mark.parametrize("family", [BC.EXTRA_TREES_FAMILY,
                                    BC.RANDOM_FOREST_FAMILY])
def test_fresh_adapter_per_fold(family):
    frame = _synthetic_frame(120, seed=43)
    y = _synthetic_target(120, seed=44)
    adapter = _fresh_adapter(family)
    adapter.fit(frame, y)
    with pytest.raises(E.ExperimentConfigError):
        adapter.fit(frame, y)


@pytest.mark.parametrize("family", [BC.EXTRA_TREES_FAMILY,
                                    BC.RANDOM_FOREST_FAMILY])
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
    assert seen["n"] == len(y_train) == 160
    assert seen["y_sum"] == pytest.approx(float(y_train.sum()))
    assert seen["eval_set"] is None
    assert len(val) == 40


@pytest.mark.parametrize("family", [BC.EXTRA_TREES_FAMILY,
                                    BC.RANDOM_FOREST_FAMILY])
def test_y_val_mutation_does_not_alter_predictions(family):
    train = _synthetic_frame(160, seed=48)
    val = _synthetic_frame(40, seed=49)
    y_val = _synthetic_target(40, seed=50)
    adapter = _fresh_adapter(family)
    adapter.fit(train, _synthetic_target(160, seed=51))
    before = adapter.predict_positive_probability(val)
    y_val[:] = 1.0 - y_val
    y_val[:] = 0.0
    after = adapter.predict_positive_probability(val)
    np.testing.assert_array_equal(before, after)


@pytest.mark.parametrize("family", [BC.EXTRA_TREES_FAMILY,
                                    BC.RANDOM_FOREST_FAMILY])
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


@pytest.mark.parametrize("family", [BC.EXTRA_TREES_FAMILY,
                                    BC.RANDOM_FOREST_FAMILY])
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
        BR.run_bagged_experiment(task="winner", model="ET", fold=fold,
                                 root=tmp_path)
    with pytest.raises((E.ProtectedHoldoutError, E.ExperimentConfigError,
                        E.UnknownFoldError)):
        BR.run_bagged_experiment(task="winner", model="RF", fold=fold,
                                 root=tmp_path)


def test_task_and_seed_locked(tmp_path):
    with pytest.raises(E.ExperimentConfigError):
        BR.run_bagged_experiment(task="podium", model="ET", fold="D1",
                                 root=tmp_path)
    with pytest.raises(E.ExperimentConfigError):
        BR.run_bagged_experiment(task="winner", model="ET", fold="D1",
                                 seed=7, root=tmp_path)
    with pytest.raises(E.ExperimentConfigError):
        BR.run_bagged_experiment(task="winner", model="RF", fold="D1",
                                 seed=7, root=tmp_path)


def test_cli_rejects_unknown_model_task_and_holdout():
    with pytest.raises(E.ExperimentConfigError):
        BCLI.main(["--model", "LOGREG", "--dry-run"])
    with pytest.raises(E.ExperimentConfigError):
        BCLI.main(["--model", "HGB", "--dry-run"])
    with pytest.raises(E.ExperimentConfigError):
        BCLI.main(["--model", "ALL", "--task", "podium", "--dry-run"])
    with pytest.raises(E.ProtectedHoldoutError):
        BCLI.main(["--model", "ALL", "--folds", "D1,HOLDOUT", "--dry-run"])
    with pytest.raises(E.ExperimentConfigError):
        BCLI.main(["--model", "ET", "--folds", "D1,D2,D3"])


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
    text = (Path(__file__).resolve().parents[1] / "v2" / "model_lab"
            / "bagged_runner.py").read_text()
    for token in ("RUN.evaluate_row_metrics", "RUN.evaluate_stages",
                  "RUN.evaluate_calibration", "RUN.evaluate_winner_top_k",
                  "RUN._align_validation", "RUN._finite_mask",
                  "RES.write_experiment", "EX.build_config",
                  "SPLITS.materialize", "RUN.resolve_development_fold",
                  "RUN._check_no_holdout_rows"):
        assert token in text, f"bagged_runner must delegate via {token}"
    for token in ("def log_loss", "def brier", "def roc_auc", "def pr_auc",
                  "def expected_calibration", "def evaluate_top",
                  "GridSearchCV", "RandomizedSearchCV", "optuna",
                  "CalibratedClassifierCV", "SMOTE"):
        assert token not in text, f"bagged_runner: forbidden {token!r}"


def test_suite_reads_stored_references_never_reruns_other_models():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "v2" / "model_lab"
            / "bagged_suite.py").read_text()
    for token in ("load_baseline_suite", "load_logreg_suite",
                  "load_nonlinear_suite"):
        assert token in text, f"bagged_suite must load {token}"
    for token in ("run_model_experiment", "run_nonlinear_experiment",
                  "run_experiment("):
        assert token not in text, f"bagged_suite must not rerun {token!r}"


# --- full-data D1 integration through the M2 canonical path ---------------------

@pytest.fixture(scope="module")
def et_d1(tmp_path_factory):
    root = tmp_path_factory.mktemp("m5et")
    return BR.run_bagged_experiment(task="winner", model="ET", fold="D1",
                                    root=root, return_predictions=True)


@pytest.fixture(scope="module")
def rf_d1(tmp_path_factory):
    root = tmp_path_factory.mktemp("m5rf")
    return BR.run_bagged_experiment(task="winner", model="RF", fold="D1",
                                    root=root, return_predictions=True)


@pytest.mark.parametrize("fixture_name,family",
                         [("et_d1", "extra_trees"),
                          ("rf_d1", "random_forest")])
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
    assert result.artifact_refs["training_sanity"]["fitted_tree_count"] == 300


@pytest.mark.parametrize("fixture_name", ["et_d1", "rf_d1"])
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


@pytest.mark.parametrize("fixture_name", ["et_d1", "rf_d1"])
def test_d1_predictions_finite_bounded_and_aligned(fixture_name, request):
    out = request.getfixturevalue(fixture_name)
    values = np.asarray(out["predictions"], dtype=float)
    assert len(values) == 23577
    assert np.all(np.isfinite(values))
    assert np.all(values >= 0.0) and np.all(values <= 1.0)


def test_d1_experiment_identity_deterministic(et_d1, rf_d1):
    for out, spec_fn in ((et_d1, BC.extra_trees_model_parameters),
                         (rf_d1, BC.random_forest_model_parameters)):
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


def test_model_metrics_route_through_applicability_guard(et_d1, rf_d1):
    from v2.model_lab import metrics as M
    M.require_metric_applicability(
        PR.PredictionKind.BINARY_PROBABILITY, "log_loss")
    M.require_metric_applicability(
        PR.PredictionKind.BINARY_PROBABILITY,
        "expected_calibration_error")
    for out in (et_d1, rf_d1):
        assert out["result"].metrics["log_loss"]["status"] == "OK"
        assert out["result"].calibration[
            "expected_calibration_error"] is not None


# --- static candidate guard -------------------------------------------------------

def test_only_extra_trees_and_random_forest_may_train_in_m5():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "v2" / "model_lab"
    allowed = {
        "bagged_candidates.py": ("ExtraTreesClassifier",
                                 "RandomForestClassifier",
                                 "EXTRA_TREES_FAMILY",
                                 "RANDOM_FOREST_FAMILY"),
        "bagged_runner.py": ("bagged_candidates", "BC.ADAPTERS",
                             "BINARY_PROBABILITY"),
        "bagged_suite.py": ("extra_trees", "random_forest"),
        "run_bagged.py": ("EXTRATREES", "RF"),
    }
    forbidden = ("LGBMClassifier", "LightGBM", "CatBoost",
                 "HistGradientBoostingClassifier", "XGBClassifier",
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
    for name in ("bagged_candidates.py", "bagged_runner.py"):
        text = (root / name).read_text()
        assert "eval_set=" not in text, f"{name}: eval set supplied to fit"


def test_no_tuning_or_calibration_apis_in_m5():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "v2" / "model_lab"
    forbidden = ("GridSearchCV", "RandomizedSearchCV", "BayesSearchCV",
                 "ParameterSampler", "optuna", "hyperopt",
                 "CalibratedClassifierCV", "IsotonicRegression",
                 "SigmoidCalibration", "temperature_scale")
    for name in ("bagged_candidates.py", "bagged_runner.py",
                 "bagged_suite.py", "run_bagged.py"):
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


def test_m3_and_m4_files_untouched_by_m5():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "v2" / "model_lab"
    for name in ("model_runner.py", "model_suite.py", "run_models.py",
                 "logreg.py", "nonlinear_runner.py", "nonlinear_suite.py",
                 "run_nonlinear.py", "tree_candidates.py"):
        text = (root / name).read_text()
        assert "ExtraTreesClassifier" not in text, f"{name}: M5 leakage"
        assert "RandomForestClassifier" not in text, f"{name}: M5 leakage"
        assert "bagged_candidates" not in text, f"{name}: M5 leakage"


# --- suite summary + report derivation --------------------------------------------

def _load_m5_summary():
    return load_json_artifact_or_skip(
        BS.default_out(), purpose="M5 suite summary")


def test_m5_summary_covers_six_experiments():
    summary = _load_m5_summary()
    assert summary["schema_version"] == "v1"
    assert summary["models"] == ["extra_trees", "random_forest"]
    assert summary["folds"] == ["D1", "D2", "D3"]
    assert summary["task"] == "winner"
    assert summary["feature_set"] == "ALL_84"
    assert summary["seed"] == 42
    assert summary["holdout_accessed"] is False
    assert summary["tuning"].startswith("none ")
    assert summary["calibration_fitted"].startswith("none ")
    assert summary["probability_semantics"] == "INDEPENDENT_BINARY"
    for family in ("extra_trees", "random_forest"):
        node = summary["per_model"][family]
        assert sorted(node["per_fold"]) == ["D1", "D2", "D3"]
        assert len(node["experiments"]) == 3
        assert node["model_spec"]["n_estimators"] == 300


def test_m5_summary_derived_from_stored_results():
    summary = _load_m5_summary()
    for family in ("extra_trees", "random_forest"):
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


def test_m5_logreg_comparison_uses_stored_m3_artifacts():
    import json
    summary = _load_m5_summary()
    with open(BS.logreg_suite_path(), encoding="utf-8") as fh:
        logreg = json.load(fh)
    node = summary["vs_logreg_reference"]["log_loss"]["per_fold"]["D1"][
        "extra_trees"]
    assert node["reference_value"] == pytest.approx(
        logreg["per_fold"]["D1"]["metrics"]["log_loss"]["race_macro"][
            "value"])
    assert node["model_value"] == pytest.approx(
        summary["per_model"]["extra_trees"]["per_fold"]["D1"][
            "metrics"]["log_loss"]["race_macro"]["value"])
    assert node["difference"] == pytest.approx(
        node["model_value"] - node["reference_value"])
    assert node["verdict"] in ("BEATS", "MATCHES", "DOES NOT BEAT")


def test_m5_m4_comparison_uses_stored_m4_artifacts():
    summary = _load_m5_summary()
    m4 = BS.load_nonlinear_suite()
    node = summary["vs_m4_reference"]["xgboost"]["brier"]["per_fold"]["D2"][
        "random_forest"]
    assert node["reference_value"] == pytest.approx(
        m4["per_model"]["xgboost"]["per_fold"]["D2"]["metrics"]["brier"][
            "race_macro"]["value"])
    assert node["verdict"] in ("BEATS", "MATCHES", "DOES NOT BEAT")


def test_m5_floor_comparison_uses_stored_m2_artifacts():
    summary = _load_m5_summary()
    stored = MSUITE.load_baseline_suite()
    assert stored["task"] == "winner"
    node = summary["vs_baseline_floor"]["log_loss"]["per_fold"]["D1"][
        "extra_trees"]
    assert node["baseline_value"] == pytest.approx(
        stored["per_fold"]["D1"]["CLASS_PRIOR"]["metrics"]["log_loss"][
            "race_macro"]["value"])
    assert node["verdict"] in ("BEATS", "MATCHES", "DOES NOT BEAT")


def test_m5_determinism_checks_recorded():
    summary = _load_m5_summary()
    for family in ("extra_trees", "random_forest"):
        det = summary["per_model"][family]["determinism_check"]
        assert det["fold"] == "D1"
        assert det["same_experiment_id"] is True
        assert det["metrics_identical"] is True
        assert det["max_abs_probability_difference"] == 0.0


def test_m5_family_finding_is_derived():
    summary = _load_m5_summary()
    finding = summary["family_finding"]
    assert finding["comparisons_per_metric"] == 6
    assert set(finding["logreg_beats_counts"]) == {
        "log_loss", "brier", "roc_auc", "pr_auc",
        "expected_calibration_error", "winner_top1"}
    assert isinstance(finding["changes_m4_conclusion"], bool)


def test_m5_report_renders_from_summary_only():
    summary = _load_m5_summary()
    report = BS.render_bagged_report(summary)
    assert "2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED" in report
    assert "DEVELOPMENT RESULTS — 2022 / 2023 / 2024" in report
    probe = summary["per_model"]["extra_trees"]["per_fold"][
        "D1"]["metrics"]["log_loss"]["race_macro"]["value"]
    assert f"{probe:.6f}" in report
