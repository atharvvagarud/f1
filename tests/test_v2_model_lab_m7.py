"""M7 tests: LogReg regularization boundary resolution + configuration freeze.

Focused coverage for the one-time boundary study:

- the exact predeclared C grid {0.003, 0.01, 0.03, 0.1} with no expansion;
- the exact M6 inner folds / outer folds / ALL_84 / preprocessing semantics;
- preprocessing fit once per inner fold, a fresh LogReg per C, only C varies;
- outer validation cannot influence selection or inner preprocessing;
- inner validation never enters preprocessing/estimator fitting;
- rejected C values never reach the outer evaluator;
- the frozen development-only global configuration-freeze rule;
- the stored M7 artifact and report trace to stored experiment results.

The protected 2025 holdout is never evaluated.
"""

import inspect
import json

import numpy as np
import pytest

from model_lab_helpers import load_canonical_or_skip, load_json_artifact_or_skip
from raceintel.model_lab import data as D
from raceintel.model_lab import errors as E
from raceintel.model_lab import inner_splits as IS
from raceintel.model_lab import logreg_boundary as B
from raceintel.model_lab import preprocessing as PRE
from raceintel.model_lab import predictions as PR
from raceintel.model_lab import results as RES
from raceintel.model_lab import run_boundary as RB
from raceintel.model_lab import runner as RUN
from raceintel.model_lab import tuning as TUNE
from raceintel.model_lab import tuning_candidates as TC
from raceintel.model_lab import tuning_runner as TR
from raceintel.model_lab.protocol import PROTECTED_HOLDOUT_SEASON


@pytest.fixture(scope="module")
def canonical():
    return load_canonical_or_skip()


@pytest.fixture(scope="module")
def d1_tuning(canonical):
    return B.tune_logreg_boundary(canonical, "D1")


# --- exact grid contract -------------------------------------------------------


def test_boundary_grid_exact():
    assert B.BOUNDARY_C_GRID == (0.003, 0.01, 0.03, 0.1)
    assert [c["C"] for c in B.BOUNDARY_GRID] == list(B.BOUNDARY_C_GRID)
    for config in B.BOUNDARY_GRID:
        assert set(config) == {"C"}
    for forbidden in (0.001, 0.005, 0.02, 0.05, 0.2):
        assert forbidden not in B.BOUNDARY_C_GRID


def test_m6_grid_unchanged_by_m7():
    assert TUNE.LOGREG_C_GRID == (0.03, 0.1, 0.3, 1.0, 3.0, 10.0)
    assert set(B.BOUNDARY_C_GRID) | set(TUNE.LOGREG_C_GRID) == {
        0.003, 0.01, 0.03, 0.1, 0.3, 1.0, 3.0, 10.0}


def test_planned_fit_count_exact():
    planned = B.planned_fit_count(("D1", "D2", "D3"))
    assert planned["inner_estimator_fits"] == 4 * (1 + 2 + 3) == 24
    assert planned["inner_preprocessor_fits"] == 6
    assert planned["outer_selected_refits"] == 3
    assert planned["determinism_refits"] == 2
    assert planned["total_estimator_fits"] == 24 + 3 + 2 == 29
    assert planned["adaptive_search"] is False


def test_no_adaptive_search_apis_present():
    for module in (B, RB):
        text = inspect.getsource(module)
        for token in ("GridSearchCV", "RandomizedSearchCV", "BayesSearchCV",
                      "ParameterSampler", "optuna", "hyperopt",
                      "CalibratedClassifierCV", "IsotonicRegression",
                      "SigmoidCalibration", "SMOTE", "smote"):
            assert token not in text, f"{module.__name__}: forbidden {token!r}"


def test_static_guard_m7_modules_train_only_logreg():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "raceintel" / "model_lab"
    forbidden = ("ExtraTreesClassifier", "RandomForestClassifier",
                 "HistGradientBoostingClassifier", "XGBClassifier",
                 "LGBMClassifier", "CatBoost", "MLPClassifier",
                 "import torch", "from torch", "GridSearchCV",
                 "RandomizedSearchCV", "BayesSearchCV", "Optuna", "optuna",
                 "hyperopt", "MLflow", "mlflow", "SMOTE", "imbalanced",
                 "CalibratedClassifierCV", "TabPFN", "tabpfn")
    for name in ("logreg_boundary.py", "run_boundary.py"):
        text = (root / name).read_text()
        for token in forbidden:
            assert token not in text, f"{name}: forbidden {token!r}"
        assert "eval_set=" not in text, f"{name}: eval set supplied"
    assert "LogisticRegression" in B.__doc__ or "Logistic Regression" in \
        B.__doc__


def test_no_new_dependencies_declared():
    from pathlib import Path
    for name in ("requirements.txt", "requirements-test.txt"):
        text = (Path(__file__).resolve().parents[1] / name).read_text().lower()
        for dep in ("lightgbm", "catboost", "optuna", "mlflow", "torch",
                    "tabpfn", "imbalanced"):
            assert dep not in text, f"{name}: new dependency {dep!r}"


# --- reuse contract ------------------------------------------------------------


@pytest.mark.parametrize("outer_fold", ["D1", "D2", "D3"])
def test_inner_folds_reuse_exact_m6_resolver(outer_fold):
    observed = [s.to_dict() for s in IS.resolve_inner_splits(outer_fold)]
    assert observed == [{"outer_fold": s.outer_fold,
                         "inner_fold_id": s.inner_fold_id,
                         "train_seasons": list(s.train_seasons),
                         "validation_seasons": list(s.validation_seasons)}
                        for s in IS.resolve_inner_splits(outer_fold)]
    assert B.M7_TASK == "winner"
    assert B.M7_FEATURE_SET == "ALL_84"
    assert B.M7_SEED == 42


def test_outer_folds_match_frozen_development_folds():
    default_folds = inspect.signature(
        B.run_boundary_suite).parameters["folds"].default
    assert tuple(default_folds) == RUN.DEVELOPMENT_ONLY_FOLDS == \
        ("D1", "D2", "D3")
    assert "family" not in inspect.signature(
        B.run_boundary_and_outer).parameters


def test_inner_records_use_all_84_and_m6_folds(d1_tuning):
    assert d1_tuning["feature_set"] == "ALL_84"
    assert d1_tuning["family"] == TC.LOGREG_FAMILY
    expected = IS.resolve_inner_splits("D1")
    assert [r["inner_fold_id"] for r in d1_tuning["inner_folds"]] == \
        [s.inner_fold_id for s in expected]
    for record, split in zip(d1_tuning["inner_folds"], expected):
        assert record["train_seasons"] == list(split.train_seasons)
        assert record["validation_seasons"] == list(split.validation_seasons)


def test_inner_features_exclude_labels_masks_identity(canonical):
    split = IS.resolve_inner_splits("D1")[0]
    X_train, y_train, _, X_val, y_val, _ = IS.inner_split_frame(
        canonical, split, "winner", "ALL_84")
    assert tuple(X_train.columns) == D.resolve_features("ALL_84", canonical)
    forbidden = (set(PRE.FORBIDDEN_LABEL_COLUMNS)
                 | set(PRE.FORBIDDEN_MASK_COLUMNS)
                 | set(PRE.FORBIDDEN_IDENTITY_COLUMNS))
    assert not (set(X_train.columns) & forbidden)
    assert not (set(X_val.columns) & forbidden)
    assert len(y_train) == len(X_train)
    assert len(y_val) == len(X_val)


def test_preprocessing_fit_once_per_inner_fold(canonical, monkeypatch):
    splits = IS.resolve_inner_splits("D2")
    expected = []
    for split in splits:
        X_train, _, _, _, _, _ = IS.inner_split_frame(
            canonical, split, "winner", "ALL_84")
        expected.append(set(X_train.index))
    seen: list = []
    original = PRE.fit_preprocessor

    def recording(frame, schema):
        seen.append(set(frame.index))
        return original(frame, schema)

    monkeypatch.setattr(PRE, "fit_preprocessor", recording)
    result = B.tune_logreg_boundary(canonical, "D2")
    assert len(seen) == len(splits)
    assert seen == expected
    assert result["preprocessor_fits"] == len(splits)
    assert result["estimator_fits"] == len(splits) * len(B.BOUNDARY_GRID)


def test_estimator_fresh_per_c_and_only_c_varies(canonical, monkeypatch):
    recorded: list = []
    original_build = TC.build_estimator

    def recording_build(family, parameters):
        estimator = original_build(family, parameters)
        recorded.append((family, dict(parameters), id(estimator)))
        return estimator

    monkeypatch.setattr(TC, "build_estimator", recording_build)
    result = B.tune_logreg_boundary(canonical, "D1")
    assert result["estimator_fits"] == len(B.BOUNDARY_GRID)
    families = {family for family, _, _ in recorded}
    assert families == {TC.LOGREG_FAMILY}
    assert {params["C"] for _, params, _ in recorded} == set(
        B.BOUNDARY_C_GRID)
    assert all(set(params) == {"C"} for _, params, _ in recorded)
    assert len({identity for _, _, identity in recorded}) == \
        len(B.BOUNDARY_GRID)


def test_inner_validation_never_enters_preprocessing_fit(canonical,
                                                         monkeypatch):
    split = IS.resolve_inner_splits("D1")[0]
    X_train, _, _, X_val, _, _ = IS.inner_split_frame(
        canonical, split, "winner", "ALL_84")
    seen: list = []
    original = PRE.fit_preprocessor

    def recording(frame, schema):
        seen.append(set(frame.index))
        return original(frame, schema)

    monkeypatch.setattr(PRE, "fit_preprocessor", recording)
    B.tune_logreg_boundary(canonical, "D1")
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
    _, y_train, _, _, _, _ = IS.inner_split_frame(
        canonical, split, "winner", "ALL_84")
    result = B.tune_logreg_boundary(canonical, "D1")
    assert seen and set(seen) == {len(y_train)}
    assert len(seen) == len(B.BOUNDARY_GRID)
    assert result["estimator_fits"] == len(B.BOUNDARY_GRID)


def test_task_and_feature_set_guarded(canonical):
    with pytest.raises(E.ExperimentConfigError):
        B.tune_logreg_boundary(canonical, "D1", task="podium")
    with pytest.raises(E.ExperimentConfigError):
        B.tune_logreg_boundary(canonical, "D1", feature_set="CORE")


# --- firewalls -----------------------------------------------------------------


def test_outer_validation_labels_cannot_change_selection(canonical):
    reference = B.tune_logreg_boundary(canonical, "D1")
    frame = canonical.frame.copy()
    is_val = frame["season"].astype(int) == 2022
    frame.loc[is_val, "is_winner"] = (
        1 - frame.loc[is_val, "is_winner"].astype(int))
    mutated = D.CanonicalMatrix(canonical.paths, frame, canonical.manifest)
    changed = B.tune_logreg_boundary(mutated, "D1")
    assert changed["selection"]["selected_key"] == \
        reference["selection"]["selected_key"]
    assert changed["config_aggregates"] == reference["config_aggregates"]


def test_outer_validation_features_cannot_change_inner_preprocessing(canonical):
    reference = B.tune_logreg_boundary(canonical, "D1")
    frame = canonical.frame.copy()
    is_val = frame["season"].astype(int) == 2022
    feature = canonical.schema.numeric[0]
    frame.loc[is_val, feature] = 1e12
    mutated = D.CanonicalMatrix(canonical.paths, frame, canonical.manifest)
    changed = B.tune_logreg_boundary(mutated, "D1")
    assert changed["config_aggregates"] == reference["config_aggregates"]
    assert changed["selection"]["selected_key"] == \
        reference["selection"]["selected_key"]


def test_only_selected_configuration_reaches_outer_evaluator(canonical,
                                                             tmp_path):
    TR.reset_outer_evaluation_log()
    out = B.run_boundary_and_outer(
        fold="D1", root=tmp_path, canonical=canonical)
    log = TR.outer_evaluation_log()
    assert len(log) == 1
    assert log[0]["experiment_id"] == out["outer"]["config"].experiment_id
    config, result = RES.read_experiment(out["outer"]["dest"])
    assert config.model_parameters["C"] == \
        out["tuning"]["selection"]["selected_config"]["C"]
    assert result.status.value == "OK"


def test_outer_selected_rejects_holdout_and_other_folds(canonical, tmp_path):
    for bad_fold in ("HOLDOUT", "2025", "FINAL_FIT", "D4"):
        with pytest.raises((E.ProtectedHoldoutError, E.ExperimentConfigError,
                            E.UnknownFoldError)):
            TR.run_outer_selected(
                family=TC.LOGREG_FAMILY, fold=bad_fold,
                selected_config={"C": 0.01}, root=tmp_path,
                canonical=canonical)


def test_2025_cannot_reach_search(canonical):
    for outer_fold in ("D1", "D2", "D3"):
        for split in IS.resolve_inner_splits(outer_fold):
            for season in (*split.train_seasons, *split.validation_seasons):
                assert int(season) != PROTECTED_HOLDOUT_SEASON
    with pytest.raises(E.ExperimentConfigError):
        B.tune_logreg_boundary(canonical, "HOLDOUT")
    with pytest.raises((E.ProtectedHoldoutError, E.ExperimentConfigError)):
        B.run_boundary_suite(folds=("D1", "2025"))


def test_selected_outer_probabilities_are_independent_binary(canonical,
                                                             tmp_path):
    out = TR.run_outer_selected(
        family=TC.LOGREG_FAMILY, fold="D1", selected_config={"C": 0.01},
        root=tmp_path, canonical=canonical, return_predictions=True)
    predictions = np.asarray(out["predictions"], dtype=float)
    assert np.all(np.isfinite(predictions))
    assert np.all((predictions >= 0.0) & (predictions <= 1.0))
    assert abs(float(predictions.sum()) - 1.0) > 1e-6
    config, result = RES.read_experiment(out["dest"])
    assert config.model_family == TC.TUNED_FAMILY_NAMES[TC.LOGREG_FAMILY]
    assert config.holdout_accessed is False
    assert result.race_metrics["winner_top_k"]["status"] == "OK"


# --- boundary classification + global freeze rule ------------------------------


def test_classify_boundary_c_labels():
    assert B.classify_boundary_c(0.003) == "LOWER_BOUNDARY"
    assert B.classify_boundary_c(0.01) == "INTERIOR"
    assert B.classify_boundary_c(0.03) == "INTERIOR_PREVIOUS_BOUNDARY"
    assert B.classify_boundary_c(0.1) == "UPPER_CONTROL"
    with pytest.raises(E.ExperimentConfigError):
        B.classify_boundary_c(0.002)


def test_boundary_status_rule():
    assert B.boundary_status(
        {"D1": 0.003, "D2": 0.003, "D3": 0.1})["status"] == "REMAINS ACTIVE"
    assert B.boundary_status(
        {"D1": 0.01, "D2": 0.01, "D3": 0.003})["status"] == "RESOLVED"
    assert B.boundary_status(
        {"D1": 0.03, "D2": 0.1, "D3": 0.003})["status"] == "RESOLVED"


def _agg(mean, c):
    return {"config": {"C": c}, "mean": mean, "std": 0.0, "min": mean,
            "max": mean, "range": 0.0}


def test_global_rule_unanimous():
    out = B.resolve_global_c(
        selected_configs={"D1": 0.01, "D2": 0.01, "D3": 0.01},
        inner_aggregates={})
    assert out["global_c"] == 0.01
    assert out["rule"] == "strict_majority_of_outer_folds"


def test_global_rule_two_vs_one_majority():
    out = B.resolve_global_c(
        selected_configs={"D1": 0.003, "D2": 0.003, "D3": 0.1},
        inner_aggregates={})
    assert out["global_c"] == 0.003
    assert out["rule"] == "strict_majority_of_outer_folds"


def test_global_rule_three_way_disagreement_uses_inner_fallback():
    out = B.resolve_global_c(
        selected_configs={"D1": 0.003, "D2": 0.01, "D3": 0.1},
        inner_aggregates={"C=0.003": _agg(0.15, 0.003),
                          "C=0.01": _agg(0.10, 0.01),
                          "C=0.1": _agg(0.12, 0.1)})
    assert out["global_c"] == 0.01
    assert out["rule"] == "aggregate_inner_log_loss_fallback"


def test_global_rule_tie_within_tolerance_prefers_smaller_c():
    out = B.resolve_global_c(
        selected_configs={"D1": 0.003, "D2": 0.01, "D3": 0.1},
        inner_aggregates={"C=0.003": _agg(0.1000000, 0.003),
                          "C=0.01": _agg(0.1000005, 0.01),
                          "C=0.1": _agg(0.2, 0.1)})
    assert out["global_c"] == 0.003
    assert out["tie_break_applied"] is True


def test_global_rule_cannot_inspect_outer_metrics_or_2025():
    params = set(inspect.signature(B.resolve_global_c).parameters)
    assert params == {"selected_configs", "inner_aggregates"}
    with pytest.raises(TypeError):
        B.resolve_global_c(selected_configs={"D1": 0.01},
                           inner_aggregates={},
                           outer_metrics={"log_loss": 0.0})
    text = inspect.getsource(B.resolve_global_c)
    for token in ("outer_metrics", "outer_log_loss", "outer_brier",
                  "outer_result", "race_macro", "2025",
                  "PROTECTED_HOLDOUT", "holdout_season"):
        assert token not in text, f"global rule references {token!r}"


def test_m6_boundary_value_was_lower_boundary_of_m6_grid():
    assert TUNE.LOGREG_C_GRID[0] == B.M6_LOWER_BOUNDARY_C == 0.03
    assert B.NEW_LOWER_BOUNDARY_C == 0.003


# --- stored M7 artifact + report ------------------------------------------------


def _load_summary():
    path = B.default_out()
    summary = load_json_artifact_or_skip(path, purpose="M7 artifact")
    return summary, path


def test_artifact_contract():
    summary, _ = _load_summary()
    assert summary["schema_version"] == "v1"
    assert summary["stage"] == "M7"
    assert summary["model_family"] == TC.LOGREG_FAMILY
    assert summary["outer_folds"] == ["D1", "D2", "D3"]
    assert summary["c_grid"] == [0.003, 0.01, 0.03, 0.1]
    assert summary["holdout_accessed"] is False
    assert summary["task"] == "winner"
    assert summary["feature_set"] == "ALL_84"
    assert sorted(summary["per_fold"]) == ["D1", "D2", "D3"]
    assert sorted(summary["selected_c_per_fold"]) == ["D1", "D2", "D3"]
    assert summary["boundary_status"]["status"] in ("RESOLVED",
                                                     "REMAINS ACTIVE")
    assert summary["boundary_status"]["recursive_search"] is False
    for fold in summary["outer_folds"]:
        assert summary["boundary_classification"][fold] in (
            "LOWER_BOUNDARY", "INTERIOR", "INTERIOR_PREVIOUS_BOUNDARY",
            "UPPER_CONTROL")


def test_artifact_traces_selected_config_to_outer_result():
    summary, _ = _load_summary()
    for fold in summary["outer_folds"]:
        outer = summary["per_fold"][fold]["outer"]
        config, result = RES.read_experiment(outer["dest"])
        assert config.experiment_id == outer["experiment_id"]
        assert config.model_family == TC.TUNED_FAMILY_NAMES[TC.LOGREG_FAMILY]
        assert config.model_parameters["C"] == \
            pytest.approx(summary["selected_c_per_fold"][fold])
        stored = result.metrics["log_loss"]["race_macro"]["value"]
        assert outer["race_macro"]["log_loss"] == pytest.approx(stored)
        assert config.holdout_accessed is False


def test_actual_fit_count_matches_plan():
    summary, _ = _load_summary()
    planned = summary["planned_fit_count"]
    actual = summary["actual_fit_count"]
    assert actual["inner_estimator_fits"] == planned["inner_estimator_fits"]
    assert actual["outer_selected_refits"] == planned["outer_selected_refits"]
    assert actual["determinism_refits"] == planned["determinism_refits"]
    assert actual["preprocessor_fits"] == planned["inner_preprocessor_fits"]


def test_global_configuration_frozen_spec():
    summary, _ = _load_summary()
    spec = summary["global_configuration"]["frozen_specification"]
    assert spec["model_family"] == TC.LOGREG_FAMILY
    assert spec["feature_set"] == "ALL_84"
    assert spec["solver"] == "lbfgs"
    assert spec["max_iter"] == 1000
    assert spec["class_weight"] is None
    assert spec["random_state"] == 42
    assert spec["C"] in summary["c_grid"]
    assert spec["probability_semantics"] == "INDEPENDENT_BINARY"
    decision = summary["global_configuration"]["decision"]
    assert decision["outer_validation_used"] is False
    assert decision["holdout_used"] is False
    # the frozen C is development-only: one of the per-fold selected C values
    assert decision["global_c"] in set(summary["selected_c_per_fold"].values())


def test_comparisons_present_and_directionally_correct():
    summary, _ = _load_summary()
    for key in ("comparison_vs_m6", "comparison_vs_m3"):
        assert key in summary
        for metric in ("log_loss", "brier", "roc_auc", "pr_auc",
                       "expected_calibration_error", "winner_top1"):
            node = summary[key]["metrics"][metric]
            assert node["aggregate"]["verdict"] in (
                "BEATS", "MATCHES", "DOES NOT BEAT", "NOT_COMPARABLE")
    assert "M6" in summary["comparison_vs_m6"]["reference"]
    assert "M3" in summary["comparison_vs_m3"]["reference"]


def test_artifact_records_determinism_and_hashes():
    summary, _ = _load_summary()
    det = summary["determinism"]
    assert det["same_experiment_id"] is True
    assert det["metrics_identical"] is True
    assert det["max_abs_probability_difference"] <= 1e-12
    hashes = summary["hashes"]
    assert hashes["phase2_matrix_content_hash"] == \
        "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db"
    assert hashes["phase2_parquet_byte_hash"] == \
        "b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3"
    assert hashes["phase2_manifest_byte_hash"] == \
        "b6a63f5eb0577906ee6496d05c4f7a20c3eb79f2f8048d4ff06acb764d6cbc62"
    assert hashes["f16_ablation_byte_hash"] == \
        "bb59d936b14552779a4ab192c4d3e9c9d1e2ff31e2ef8608b30c44ed86f2f5a7"


def test_report_renders_from_summary_only():
    summary, _ = _load_summary()
    report = B.render_boundary_report(summary)
    assert "LOGISTIC REGRESSION DEVELOPMENT CONFIGURATION FREEZE" in report
    assert "OUTER DEVELOPMENT EVALUATION: 2022 / 2023 / 2024" in report
    assert "2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED" in report
    probe = summary["per_fold"]["D1"]["outer"]["race_macro"]["log_loss"]
    assert f"{probe:.6f}" in report
    assert summary["boundary_status"]["status"] in report
    for metric in ("log_loss", "brier", "roc_auc", "pr_auc"):
        assert metric in report


def test_m6_and_m3_artifacts_unchanged_by_m7():
    # M7 must not overwrite the M6 tuning artifact or the M3 reference.
    m6 = load_json_artifact_or_skip(
        B.m6_artifact_path(), purpose="M6 tuning artifact")
    m3 = load_json_artifact_or_skip(
        B.m3_reference_path(), purpose="M3 reference artifact")
    assert m6["per_candidate"]["logistic_regression"]["per_fold"]["D1"][
        "selection"]["selected_config"]["C"] == 0.03
    assert m3["model_spec"]["C"] == 1.0
    assert m3["holdout_accessed"] is False


def test_prediction_semantics_preserved(canonical):
    split = IS.resolve_inner_splits("D1")[0]
    X_train, y_train, _, X_val, _, meta_val = IS.inner_split_frame(
        canonical, split, "winner", "ALL_84")
    pre = PRE.fit_preprocessor(X_train, canonical.schema)
    model = TC.fit_fresh_model(
        TC.LOGREG_FAMILY, {"C": 0.01}, X_train,
        np.asarray(y_train.astype(float)), preprocessor=pre)
    prediction = model.predict_result(X_val, list(meta_val["state_id"]))
    assert prediction.kind is PR.PredictionKind.BINARY_PROBABILITY
    assert prediction.semantics is PR.ProbabilitySemantics.INDEPENDENT_BINARY
    values = np.asarray(prediction.values, dtype=float)
    assert abs(float(values.sum()) - 1.0) > 1e-6
