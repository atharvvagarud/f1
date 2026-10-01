"""M6 tests: inner temporal splits, bounded tuning, firewalls, artifact.

Focused coverage for the controlled nested temporal tuning stage:

- deterministic expanding-window inner splits (whole-season/whole-race,
  strict chronology, contained in outer TRAIN, outer validation + 2025 absent);
- exact predeclared search spaces and the frozen tie-break;
- only LogReg + ExtraTrees may be trained;
- outer VALIDATION cannot influence selection or inner preprocessing;
- inner validation never enters preprocessing/estimator fitting;
- rejected configurations never reach the outer evaluator;
- the stored tuning artifact and report trace to stored experiment results.

The protected 2025 holdout is never evaluated.
"""

import numpy as np
import pytest

from model_lab_helpers import load_canonical_or_skip, load_json_artifact_or_skip
from raceintel.model_lab import data as D
from raceintel.model_lab import errors as E
from raceintel.model_lab import inner_splits as IS
from raceintel.model_lab import preprocessing as PRE
from raceintel.model_lab import predictions as PR
from raceintel.model_lab import tuning as TUNE
from raceintel.model_lab import tuning_candidates as TC
from raceintel.model_lab import tuning_runner as TR
from raceintel.model_lab import tuning_suite as TS
from raceintel.model_lab import run_tuning as RT
from raceintel.model_lab import results as RES
from raceintel.model_lab import splits as S
from raceintel.model_lab.protocol import PROTECTED_HOLDOUT_SEASON


@pytest.fixture(scope="module")
def canonical():
    return load_canonical_or_skip()


# --- inner split contract ------------------------------------------------------

EXPECTED_INNER = {
    "D1": [((2018, 2019, 2020), (2021,))],
    "D2": [((2018, 2019, 2020), (2021,)),
           ((2018, 2019, 2020, 2021), (2022,))],
    "D3": [((2018, 2019, 2020), (2021,)),
           ((2018, 2019, 2020, 2021), (2022,)),
           ((2018, 2019, 2020, 2021, 2022), (2023,))],
}


@pytest.mark.parametrize("outer_fold", ["D1", "D2", "D3"])
def test_inner_splits_exact_season_sets(outer_fold):
    splits = IS.resolve_inner_splits(outer_fold)
    observed = [(s.train_seasons, s.validation_seasons) for s in splits]
    assert observed == EXPECTED_INNER[outer_fold]


@pytest.mark.parametrize("outer_fold", ["D1", "D2", "D3"])
def test_inner_split_chronology_and_containment(outer_fold):
    outer = S.get_split(outer_fold)
    for split in IS.resolve_inner_splits(outer_fold):
        assert max(split.train_seasons) < min(split.validation_seasons)
        assert set(split.train_seasons) <= set(outer.train_seasons)
        assert set(split.validation_seasons) <= set(outer.train_seasons)
        assert not (set(split.validation_seasons)
                    & set(outer.validation_seasons))
        assert PROTECTED_HOLDOUT_SEASON not in (
            *split.train_seasons, *split.validation_seasons)


def test_inner_splits_deterministic():
    for outer_fold in ("D1", "D2", "D3"):
        first = IS.resolve_inner_splits(outer_fold)
        second = IS.resolve_inner_splits(outer_fold)
        assert first == second


def test_inner_folds_reject_non_development():
    for bad in ("HOLDOUT", "2025", "FINAL_FIT", "D4"):
        with pytest.raises((E.ExperimentConfigError, E.UnknownFoldError,
                            E.ProtectedHoldoutError)):
            IS.resolve_inner_splits(bad)


def test_inner_splits_are_whole_races(canonical):
    for outer_fold in ("D1", "D2", "D3"):
        for split in IS.resolve_inner_splits(outer_fold):
            IS.assert_whole_races(canonical, split)
            IS.assert_no_holdout_seasons(
                (*split.train_seasons, *split.validation_seasons))


def test_inner_features_exclude_labels_masks_identity(canonical):
    split = IS.resolve_inner_splits("D1")[0]
    X_train, y_train, meta_train, X_val, y_val, meta_val = \
        IS.inner_split_frame(canonical, split, "winner", "ALL_84")
    assert tuple(X_train.columns) == D.resolve_features("ALL_84", canonical)
    forbidden = (set(PRE.FORBIDDEN_LABEL_COLUMNS)
                 | set(PRE.FORBIDDEN_MASK_COLUMNS)
                 | set(PRE.FORBIDDEN_IDENTITY_COLUMNS))
    assert not (set(X_train.columns) & forbidden)
    assert not (set(X_val.columns) & forbidden)
    assert len(y_train) == len(X_train)
    assert len(y_val) == len(X_val)


def test_no_random_split_policy():
    import inspect
    text = inspect.getsource(IS)
    for token in ("train_test_split", "KFold", "ShuffleSplit", "shuffle",
                  "np.random", "random_state"):
        assert token not in text


# --- search space contract -----------------------------------------------------

def test_logreg_search_space_exact():
    assert TUNE.LOGREG_C_GRID == (0.03, 0.1, 0.3, 1.0, 3.0, 10.0)
    assert [c["C"] for c in TUNE.LOGREG_GRID] == list(TUNE.LOGREG_C_GRID)
    for config in TUNE.LOGREG_GRID:
        assert set(config) == {"C"}
    assert any(c["C"] == 1.0 for c in TUNE.LOGREG_GRID)


def test_extratrees_search_space_exact():
    assert len(TUNE.EXTRA_TREES_GRID) == 12
    combos = {
        (c["max_features"], c["min_samples_leaf"], c["max_depth"])
        for c in TUNE.EXTRA_TREES_GRID}
    expected = {
        (mf, msl, md)
        for mf in ("sqrt", 0.5)
        for msl in (1, 3, 10)
        for md in (None, 20)}
    assert combos == expected
    for config in TUNE.EXTRA_TREES_GRID:
        assert set(config) == {"max_features", "min_samples_leaf", "max_depth"}
    reference = TS.REFERENCE_CONFIG[TC.EXTRA_TREES_FAMILY]
    assert reference in [dict(c) for c in TUNE.EXTRA_TREES_GRID]


def test_no_adaptive_search_apis_present():
    import inspect
    for module in (TUNE, TC, TR, TS, RT):
        text = inspect.getsource(module)
        for token in ("GridSearchCV", "RandomizedSearchCV", "BayesSearchCV",
                      "ParameterSampler", "optuna", "hyperopt",
                      "CalibratedClassifierCV", "IsotonicRegression",
                      "SigmoidCalibration", "SMOTE", "smote"):
            assert token not in text, f"{module.__name__}: forbidden {token!r}"


def test_only_logreg_and_extratrees_trainable():
    logreg = TC.build_estimator(TC.LOGREG_FAMILY, {"C": 0.3})
    assert type(logreg).__name__ == "LogisticRegression"
    et = TC.build_estimator(TC.EXTRA_TREES_FAMILY, {
        "max_features": "sqrt", "min_samples_leaf": 1, "max_depth": None})
    assert type(et).__name__ == "ExtraTreesClassifier"
    for bad in ("hist_gradient_boosting", "xgboost", "random_forest",
                "lightgbm", "catboost", "mlp"):
        with pytest.raises(E.ExperimentConfigError):
            TC.build_estimator(bad, {})


def test_static_guard_m6_modules_train_only_two_families():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "raceintel" / "model_lab"
    modules = ("tuning.py", "tuning_candidates.py", "tuning_runner.py",
               "tuning_suite.py", "run_tuning.py", "inner_splits.py")
    forbidden = ("HistGradientBoostingClassifier", "XGBClassifier",
                 "RandomForestClassifier", "LGBMClassifier", "CatBoost",
                 "MLPClassifier", "import torch", "from torch",
                 "GridSearchCV", "RandomizedSearchCV", "BayesSearchCV",
                 "Optuna", "optuna", "hyperopt", "MLflow", "mlflow",
                 "SMOTE", "imbalanced", "CalibratedClassifierCV",
                 "TabPFN", "tabpfn")
    for name in modules:
        text = (root / name).read_text()
        for token in forbidden:
            assert token not in text, f"{name}: forbidden {token!r}"
        assert "eval_set=" not in text, f"{name}: eval set supplied"
    candidates = (root / "tuning_candidates.py").read_text()
    assert "LogisticRegression" in candidates
    assert "ExtraTreesClassifier" in candidates


def test_no_new_dependencies_declared():
    from pathlib import Path
    for name in ("requirements.txt", "requirements-test.txt"):
        text = (Path(__file__).resolve().parents[1] / name).read_text().lower()
        for dep in ("lightgbm", "catboost", "optuna", "mlflow", "torch",
                    "tabpfn", "imbalanced"):
            assert dep not in text, f"{name}: new dependency {dep!r}"


def test_tuned_families_do_not_collide_with_references():
    assert TC.TUNED_FAMILY_NAMES[TC.LOGREG_FAMILY] != \
        "logistic_regression"
    assert TC.TUNED_FAMILY_NAMES[TC.EXTRA_TREES_FAMILY] != "extra_trees"


def test_runner_delegates_to_canonical_evaluators():
    from pathlib import Path
    text = (Path(__file__).resolve().parents[1] / "raceintel" / "model_lab"
            / "tuning_runner.py").read_text()
    for token in ("RUN.evaluate_row_metrics", "RUN.evaluate_stages",
                  "RUN.evaluate_calibration", "RUN.evaluate_winner_top_k",
                  "RUN._align_validation", "RUN._finite_mask",
                  "RES.write_experiment", "EX.build_config",
                  "SPLITS.materialize", "RUN.resolve_development_fold",
                  "RUN._check_no_holdout_rows"):
        assert token in text, f"tuning_runner must delegate via {token}"
    for token in ("def log_loss", "def brier", "def roc_auc", "def pr_auc",
                  "GridSearchCV", "RandomizedSearchCV", "CalibratedClassifierCV"):
        assert token not in text, f"tuning_runner: forbidden {token!r}"


def test_planned_fit_count_matches_grids():
    planned = TUNE.planned_fit_count(("D1", "D2", "D3"))
    # LogReg 6 configs x (1+2+3 inner folds)
    assert planned["families"][TC.LOGREG_FAMILY]["inner_estimator_fits"] == 36
    # ExtraTrees 12 configs x (1+2+3 inner folds)
    assert planned["families"][TC.EXTRA_TREES_FAMILY]["inner_estimator_fits"] \
        == 72
    assert planned["outer_selected_refits"] == 6
    assert planned["total_estimator_fits"] == 36 + 72 + 6 + 2


# --- firewalls -----------------------------------------------------------------

@pytest.fixture(scope="module")
def logreg_d1_tuning(canonical):
    return TUNE.tune_family(canonical, TC.LOGREG_FAMILY, "D1")


def test_tie_break_rule_predeclared():
    rule = TUNE.TIE_BREAK_RULE
    assert rule["frozen_before_results"] is True
    assert rule["tolerance_abs"] == TUNE.TIE_TOLERANCE
    assert "smaller C" in rule["logistic_regression"]
    assert "min_samples_leaf" in rule["extra_trees"]


def test_tie_break_prefers_more_regularized():
    aggregates = {
        "C=0.3": {"config": {"C": 0.3}, "mean": 0.10},
        "C=1": {"config": {"C": 1.0}, "mean": 0.10},
        "C=3": {"config": {"C": 3.0}, "mean": 0.10},
    }
    out = TUNE.select_configuration(TC.LOGREG_FAMILY, aggregates)
    assert out["selected_config"]["C"] == 0.3
    assert out["tie_break_applied"] is True


def test_outer_validation_labels_cannot_change_selection(canonical):
    reference = TUNE.tune_family(canonical, TC.LOGREG_FAMILY, "D1")
    frame = canonical.frame.copy()
    is_val = frame["season"].astype(int) == 2022
    frame.loc[is_val, "is_winner"] = (
        1 - frame.loc[is_val, "is_winner"].astype(int))
    mutated = D.CanonicalMatrix(canonical.paths, frame, canonical.manifest)
    changed = TUNE.tune_family(mutated, TC.LOGREG_FAMILY, "D1")
    assert changed["selection"]["selected_key"] == \
        reference["selection"]["selected_key"]
    assert changed["config_aggregates"] == reference["config_aggregates"]


def test_outer_validation_features_cannot_change_inner_preprocessing(canonical):
    reference = TUNE.tune_family(canonical, TC.LOGREG_FAMILY, "D1")
    frame = canonical.frame.copy()
    is_val = frame["season"].astype(int) == 2022
    feature = canonical.schema.numeric[0]
    frame.loc[is_val, feature] = 1e12
    mutated = D.CanonicalMatrix(canonical.paths, frame, canonical.manifest)
    changed = TUNE.tune_family(mutated, TC.LOGREG_FAMILY, "D1")
    assert changed["config_aggregates"] == reference["config_aggregates"]
    assert changed["selection"]["selected_key"] == \
        reference["selection"]["selected_key"]


def test_inner_validation_never_enters_preprocessing_fit(canonical, monkeypatch):
    split = IS.resolve_inner_splits("D1")[0]
    X_train, _, _, X_val, _, _ = IS.inner_split_frame(
        canonical, split, "winner", "ALL_84")
    seen: list = []
    original = PRE.fit_preprocessor

    def recording(frame, schema):
        seen.append(set(frame.index))
        return original(frame, schema)

    monkeypatch.setattr(PRE, "fit_preprocessor", recording)
    TUNE.tune_family(canonical, TC.LOGREG_FAMILY, "D1")
    assert len(seen) == 1
    assert seen[0] == set(X_train.index)
    assert not (seen[0] & set(X_val.index))


def test_inner_validation_never_enters_estimator_fit(canonical, monkeypatch):
    seen: list = []
    original_build = TC.build_estimator

    def recording_build(family, parameters):
        estimator = original_build(family, parameters)
        original_fit = estimator.fit

        def recording_fit(X, y, **kwargs):
            seen.append(int(np.asarray(y).shape[0]))
            return original_fit(X, y, **kwargs)

        estimator.fit = recording_fit
        return estimator

    monkeypatch.setattr(TC, "build_estimator", recording_build)
    split = IS.resolve_inner_splits("D1")[0]
    X_train, y_train, _, X_val, _, _ = IS.inner_split_frame(
        canonical, split, "winner", "ALL_84")
    result = TUNE.tune_family(canonical, TC.LOGREG_FAMILY, "D1")
    assert seen and set(seen) == {len(y_train)}
    assert result["estimator_fits"] == len(TUNE.LOGREG_GRID)


def test_only_selected_configuration_reaches_outer_evaluator(canonical,
                                                             tmp_path):
    TR.reset_outer_evaluation_log()
    out = TR.run_tuning_and_outer(
        family=TC.LOGREG_FAMILY, fold="D1", root=tmp_path, canonical=canonical)
    log = TR.outer_evaluation_log()
    assert len(log) == 1
    assert log[0]["experiment_id"] == out["outer"]["config"].experiment_id
    config, result = RES.read_experiment(out["outer"]["dest"])
    assert config.model_parameters["C"] == \
        out["tuning"]["selection"]["selected_config"]["C"]
    assert result.status.value == "OK"


def test_outer_selected_rejects_holdout_and_other_families(canonical, tmp_path):
    for bad_fold in ("HOLDOUT", "2025", "FINAL_FIT"):
        with pytest.raises((E.ProtectedHoldoutError, E.ExperimentConfigError,
                            E.UnknownFoldError)):
            TR.run_outer_selected(
                family=TC.LOGREG_FAMILY, fold=bad_fold,
                selected_config={"C": 1.0}, root=tmp_path, canonical=canonical)
    for bad_family in ("random_forest", "xgboost", "hist_gradient_boosting"):
        with pytest.raises(E.ExperimentConfigError):
            TR.run_outer_selected(
                family=bad_family, fold="D1", selected_config={"C": 1.0},
                root=tmp_path, canonical=canonical)


def test_2025_cannot_reach_search(canonical):
    for outer_fold in ("D1", "D2", "D3"):
        for split in IS.resolve_inner_splits(outer_fold):
            for season in (*split.train_seasons, *split.validation_seasons):
                assert int(season) != PROTECTED_HOLDOUT_SEASON
    with pytest.raises(E.ExperimentConfigError):
        TUNE.tune_family(canonical, TC.LOGREG_FAMILY, "HOLDOUT")


def test_selected_outer_probabilities_are_independent_binary(canonical,
                                                             tmp_path):
    out = TR.run_outer_selected(
        family=TC.LOGREG_FAMILY, fold="D1", selected_config={"C": 1.0},
        root=tmp_path, canonical=canonical, return_predictions=True)
    predictions = np.asarray(out["predictions"], dtype=float)
    assert np.all(np.isfinite(predictions))
    assert np.all((predictions >= 0.0) & (predictions <= 1.0))
    assert abs(float(predictions.sum()) - 1.0) > 1e-6
    config, result = RES.read_experiment(out["dest"])
    assert config.model_family == TC.TUNED_FAMILY_NAMES[TC.LOGREG_FAMILY]
    assert config.holdout_accessed is False
    assert result.race_metrics["winner_top_k"]["status"] == "OK"


# --- stored tuning artifact + report ------------------------------------------

def _load_tuning_summary():
    path = TS.default_out()
    summary = load_json_artifact_or_skip(path, purpose="M6 tuning artifact")
    return summary, path


def test_tuning_artifact_covers_both_candidates_and_folds():
    summary, _ = _load_tuning_summary()
    assert summary["schema_version"] == "v1"
    assert summary["families"] == ["logistic_regression", "extra_trees"]
    assert summary["folds"] == ["D1", "D2", "D3"]
    assert summary["holdout_accessed"] is False
    assert summary["task"] == "winner"
    assert summary["feature_set"] == "ALL_84"
    for family in summary["families"]:
        node = summary["per_candidate"][family]
        assert sorted(node["per_fold"]) == ["D1", "D2", "D3"]
        assert len(node["experiments"]) == 3


def test_tuning_artifact_traces_selected_config_to_outer_result():
    summary, _ = _load_tuning_summary()
    for family in summary["families"]:
        for entry in summary["per_candidate"][family]["experiments"]:
            config, result = RES.read_experiment(entry["dest"])
            assert config.experiment_id == entry["experiment_id"]
            fold = entry["fold"]
            selection = summary["per_candidate"][family]["per_fold"][fold][
                "selection"]["selected_config"]
            for key, value in selection.items():
                assert config.model_parameters[key] == value
            stored = result.metrics["log_loss"]["race_macro"]["value"]
            assert summary["per_candidate"][family]["per_fold"][fold][
                "outer"]["metrics"]["log_loss"]["race_macro"]["value"] == \
                pytest.approx(stored)


def test_actual_fit_count_matches_plan():
    summary, _ = _load_tuning_summary()
    planned = summary["planned_fit_count"]
    actual = summary["actual_fit_count"]
    assert sum(v["inner_estimator_fits"] for v in actual.values()) == \
        planned["inner_estimator_fits"]
    assert sum(v["outer_selected_refits"] for v in actual.values()) == \
        planned["outer_selected_refits"]


def test_recommendation_is_predeclared_decision():
    summary, _ = _load_tuning_summary()
    decision = summary["recommendation"]["decision"]
    assert decision in (
        "PROMOTE LOGREG TO M7", "PROMOTE EXTRATREES TO M7",
        "PROMOTE BOTH TO M7", "NO CANDIDATE READY")


def test_report_renders_from_summary_only():
    summary, _ = _load_tuning_summary()
    report = TS.render_tuning_report(summary)
    assert "DEVELOPMENT MODEL SELECTION" in report
    assert "OUTER EVALUATION: 2022 / 2023 / 2024" in report
    assert "2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED" in report
    probe = summary["per_candidate"]["logistic_regression"]["per_fold"]["D1"][
        "outer"]["metrics"]["log_loss"]["race_macro"]["value"]
    assert f"{probe:.6f}" in report
    assert summary["recommendation"]["decision"] in report


def test_determinism_recorded_in_artifact():
    summary, _ = _load_tuning_summary()
    for family in summary["families"]:
        det = summary["determinism"][family]
        assert det["same_experiment_id"] is True
        assert det["metrics_identical"] is True
        assert det["max_abs_probability_difference"] <= 1e-12
