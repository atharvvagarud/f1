"""M8 tests: calibration evaluation & selection (development-only).

Focused coverage for the chronological calibration contract:

- exact base / calibration / evaluation seasons and strict chronology;
- the frozen M7 LogReg C=0.01 base model (no retuning, ALL_84);
- calibration-only scalar fit (no original feature, no hidden CV);
- calibration firewalls (calibration labels, outer labels, outer features,
  2025) and the fair-comparison same-raw-vector rule;
- the predeclared selection rule (unit-tested on synthetic metrics);
- the stored M8 artifact and report trace to stored experiments.

The protected 2025 holdout is never evaluated.
"""

import inspect

import numpy as np
import pytest

from model_lab_helpers import load_canonical_or_skip, load_json_artifact_or_skip
from raceintel.model_lab import calibration_selection as CS
from raceintel.model_lab import data as D
from raceintel.model_lab import errors as E
from raceintel.model_lab import preprocessing as PRE
from raceintel.model_lab import runner as RUN
from raceintel.model_lab import tuning_candidates as TC
from raceintel.model_lab.inner_splits import materialize_seasons
from raceintel.model_lab.protocol import PROTECTED_HOLDOUT_SEASON

METHODS = CS.METHODS

EXPECTED_SPLIT = {
    "D1": (((2018, 2019, 2020), (2021,), (2022,))),
    "D2": (((2018, 2019, 2020, 2021), (2022,), (2023,))),
    "D3": (((2018, 2019, 2020, 2021, 2022), (2023,), (2024,))),
}


@pytest.fixture(scope="module")
def canonical():
    return load_canonical_or_skip()


@pytest.fixture(scope="module")
def d1(canonical, tmp_path_factory):
    root = tmp_path_factory.mktemp("m8_d1")
    return CS.run_calibration_fold(canonical, "D1", root=root,
                                   return_predictions=True)


# --- temporal contract ---------------------------------------------------------


@pytest.mark.parametrize("fold", ["D1", "D2", "D3"])
def test_calibration_split_exact_seasons(fold):
    split = CS.resolve_calibration_split(fold)
    assert (split.base_seasons, split.calibration_seasons,
            split.evaluation_seasons) == EXPECTED_SPLIT[fold]


@pytest.mark.parametrize("fold", ["D1", "D2", "D3"])
def test_calibration_split_strict_chronology(fold):
    split = CS.resolve_calibration_split(fold)
    assert max(split.base_seasons) < min(split.calibration_seasons)
    assert max(split.calibration_seasons) < min(split.evaluation_seasons)
    assert PROTECTED_HOLDOUT_SEASON not in (
        *split.base_seasons, *split.calibration_seasons,
        *split.evaluation_seasons)


def test_calibration_split_rejects_holdout_and_other_folds():
    for bad in ("HOLDOUT", "2025", "FINAL_FIT", "D4"):
        with pytest.raises((E.ProtectedHoldoutError, E.ExperimentConfigError,
                            E.UnknownFoldError)):
            CS.resolve_calibration_split(bad)


def test_calibration_split_whole_seasons(canonical):
    for fold in ("D1", "D2", "D3"):
        split = CS.resolve_calibration_split(fold)
        for seasons in (split.base_seasons, split.calibration_seasons,
                        split.evaluation_seasons):
            frame = canonical.select_seasons(seasons)
            assert frame["season"].astype(int).nunique() == len(seasons)


# --- frozen base-model contract ------------------------------------------------


def test_base_model_spec_is_m7_frozen():
    spec = CS.BASE_MODEL_SPEC
    assert spec["estimator"] == "LogisticRegression"
    assert spec["C"] == 0.01
    assert spec["solver"] == "lbfgs"
    assert spec["max_iter"] == 1000
    assert spec["class_weight"] is None
    assert spec["random_state"] == 42
    assert spec["feature_set"] == "ALL_84"
    assert spec["probability_semantics"] == "INDEPENDENT_BINARY"


def test_m8_uses_frozen_c_only():
    assert CS.FROZEN_C == 0.01
    assert CS.M8_TASK == "winner"
    assert CS.M8_FEATURE_SET == "ALL_84"
    assert CS.M8_SEED == 42


def test_no_parameter_tuning_apis_present():
    for module in (CS,):
        text = inspect.getsource(module)
        for token in ("GridSearchCV", "RandomizedSearchCV", "BayesSearchCV",
                      "Optuna", "optuna", "hyperopt", "CalibratedClassifierCV",
                      "ExtraTreesClassifier", "RandomForestClassifier",
                      "HistGradientBoostingClassifier", "XGBClassifier",
                      "LGBMClassifier", "CatBoost", "MLPClassifier",
                      "import torch", "from torch", "TabPFN", "tabpfn",
                      "MLflow", "mlflow", "SMOTE", "imbalanced"):
            assert token not in text, f"forbidden {token!r} in {module}"


def test_static_guard_m8_modules():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "raceintel" / "model_lab"
    forbidden = ("ExtraTreesClassifier", "RandomForestClassifier",
                 "HistGradientBoostingClassifier", "XGBClassifier",
                 "LGBMClassifier", "CatBoost", "MLPClassifier",
                 "import torch", "from torch", "GridSearchCV",
                 "RandomizedSearchCV", "BayesSearchCV", "Optuna", "optuna",
                 "hyperopt", "MLflow", "mlflow", "SMOTE", "imbalanced",
                 "CalibratedClassifierCV", "TabPFN", "tabpfn")
    for name in ("calibration_selection.py", "run_calibration.py"):
        text = (root / name).read_text()
        for token in forbidden:
            assert token not in text, f"{name}: forbidden {token!r}"
    base = (root / "calibration_selection.py").read_text()
    assert "LogisticRegression" in base
    assert "IsotonicRegression" in base


def test_no_new_dependencies_declared():
    from pathlib import Path
    for name in ("requirements.txt", "requirements-test.txt"):
        text = (Path(__file__).resolve().parents[1] / name).read_text().lower()
        for dep in ("lightgbm", "catboost", "optuna", "mlflow", "torch",
                    "tabpfn", "imbalanced", "statsmodels"):
            assert dep not in text, f"{name}: new dependency {dep!r}"


# --- calibrator properties -----------------------------------------------------


def _synthetic(n=2000, seed=0):
    rng = np.random.default_rng(seed)
    p = rng.beta(1.0, 8.0, size=n)
    y = (rng.random(n) < p).astype(float)
    return p, y


def test_platt_is_scalar_calibration_only_and_finite():
    p, y = _synthetic()
    cal = CS.fit_platt(p, y)
    diag = cal.diagnostics()
    assert diag["n_input_features"] == 1
    assert diag["finite"] is True
    assert diag["epsilon"] == CS.PLATT_EPSILON
    assert int(cal._model.n_features_in_) == 1
    out = cal.transform(np.array([0.0, 0.01, 0.5, 1.0]))
    assert np.all(np.isfinite(out))
    assert np.all((out >= 0.0) & (out <= 1.0))


def test_platt_epsilon_clip_handles_extremes():
    p, y = _synthetic()
    cal = CS.fit_platt(p, y)
    out = cal.transform(np.array([0.0, 1.0, 1e-12, 1 - 1e-12]))
    assert np.all(np.isfinite(out))
    assert np.all((out >= 0.0) & (out <= 1.0))


def test_platt_positive_coefficient_preserves_ranking():
    p, y = _synthetic()
    cal = CS.fit_platt(p, y)
    assert cal.coefficient > 0
    sample = np.linspace(0.0, 1.0, 101)
    out = cal.transform(sample)
    assert np.all(np.diff(out) >= -1e-12)


def test_isotonic_is_monotone_and_bounded():
    p, y = _synthetic()
    cal = CS.fit_isotonic(p, y)
    sample = np.linspace(0.0, 1.0, 201)
    out = cal.transform(sample)
    assert np.all(np.diff(out) >= -1e-12)
    assert np.all((out >= 0.0) & (out <= 1.0))
    assert cal.diagnostics()["n_input_features"] == 1
    assert len(cal._model.X_thresholds_) == cal.n_thresholds


def test_calibrator_fit_rejects_feature_matrix():
    # Calibrators consume scalar probabilities only; a 2-D 84-feature matrix
    # must not be silently accepted as a single score.
    matrix = np.ones((10, 84), dtype=float)
    y = np.zeros(10, dtype=float)
    with pytest.raises(E.InvalidPredictionError):
        CS.fit_platt(matrix, y)


def test_rejected_method_cannot_alter_another_method():
    # Each calibrator is an independent mapping of the same calibration data:
    # fitting the hypothetical loser in between never changes the other one.
    p, y = _synthetic()
    platt_before = CS.fit_platt(p, y).transform(p)
    CS.fit_isotonic(p, y)  # fit the other candidate in between
    platt_after = CS.fit_platt(p, y).transform(p)
    assert np.array_equal(platt_before, platt_after)

    iso_before = CS.fit_isotonic(p, y).transform(p)
    CS.fit_platt(p, y)  # fit the other candidate in between
    iso_after = CS.fit_isotonic(p, y).transform(p)
    assert np.array_equal(iso_before, iso_after)


def test_calibration_sample_audit_fields():
    p = np.array([0.0, 0.1, 0.1, 0.9, 1.0])
    y = np.array([0.0, 0.0, 1.0, 1.0, 1.0])
    audit = CS.calibration_sample_audit(p, y, season=2021)
    assert audit["season"] == 2021
    assert audit["rows"] == 5
    assert audit["positive_count"] == 3
    assert audit["negative_count"] == 2
    assert audit["unique_raw_probability_count"] == 4
    assert audit["n_exact_zero"] == 1
    assert audit["n_exact_one"] == 1


# --- firewall + fairness -------------------------------------------------------


def test_preprocessing_and_base_fit_use_base_seasons_only(canonical, monkeypatch):
    seen_pre: list = []
    seen_fit_rows: list = []
    original_pre = PRE.fit_preprocessor
    original_build = TC.build_estimator

    def recording_pre(frame, schema):
        seen_pre.append(set(frame.index))
        return original_pre(frame, schema)

    def recording_build(family, parameters):
        estimator = original_build(family, parameters)
        original_fit = estimator.fit

        def recording_fit(X, y, **kwargs):
            seen_fit_rows.append(int(np.asarray(y).shape[0]))
            return original_fit(X, y, **kwargs)

        estimator.fit = recording_fit
        return estimator

    monkeypatch.setattr(PRE, "fit_preprocessor", recording_pre)
    monkeypatch.setattr(TC, "build_estimator", recording_build)
    split = CS.resolve_calibration_split("D1")
    X_base, y_base, _ = materialize_seasons(
        canonical, split.base_seasons, "winner", "ALL_84")
    import tempfile
    out = CS.run_calibration_fold(canonical, "D1",
                                  root=tempfile.mkdtemp(prefix="m8fw_"))
    assert len(seen_pre) == 1
    assert seen_pre[0] == set(X_base.index)
    assert seen_fit_rows == [len(y_base)]
    assert out["base"]["training_rows"] == len(y_base)


def test_calibration_labels_cannot_change_base_fit(canonical):
    # Calibration labels are never used for the base model: mutating them must
    # leave the base-fit outer raw probabilities untouched. (Platt/isotonic are
    # fit on calibration labels, so they MAY legitimately move.)
    reference = _fold_signature(canonical)
    frame = canonical.frame.copy()
    is_cal = frame["season"].astype(int) == 2021
    frame.loc[is_cal, "is_winner"] = (
        1 - frame.loc[is_cal, "is_winner"].astype(int))
    mutated = D.CanonicalMatrix(canonical.paths, frame, canonical.manifest)
    changed = _fold_signature(mutated)
    assert np.max(np.abs(changed["raw"] - reference["raw"])) == 0.0


def test_outer_labels_cannot_change_any_fit(canonical):
    reference = _fold_signature(canonical)
    frame = canonical.frame.copy()
    is_eval = frame["season"].astype(int) == 2022
    frame.loc[is_eval, "is_winner"] = (
        1 - frame.loc[is_eval, "is_winner"].astype(int))
    mutated = D.CanonicalMatrix(canonical.paths, frame, canonical.manifest)
    changed = _fold_signature(mutated)
    assert np.max(np.abs(changed["raw"] - reference["raw"])) == 0.0
    assert changed["platt_coefficient"] == pytest.approx(
        reference["platt_coefficient"])
    assert changed["n_isotonic_thresholds"] == \
        reference["n_isotonic_thresholds"]


def test_outer_features_cannot_change_any_fit(canonical):
    reference = _fold_signature(canonical)
    frame = canonical.frame.copy()
    is_eval = frame["season"].astype(int) == 2022
    feature = canonical.schema.numeric[0]
    frame.loc[is_eval, feature] = 1e12
    mutated = D.CanonicalMatrix(canonical.paths, frame, canonical.manifest)
    changed = _fold_signature(mutated)
    # fitting is base/calibration-only, so fitted parameters are unchanged;
    # only the outer raw probabilities (evaluation inputs) may move.
    assert changed["platt_coefficient"] == pytest.approx(
        reference["platt_coefficient"])
    assert changed["n_isotonic_thresholds"] == \
        reference["n_isotonic_thresholds"]
    assert np.max(np.abs(changed["raw"] - reference["raw"])) > 0.0


def test_2025_never_reaches_calibration_suite(canonical):
    for fold in ("D1", "D2", "D3"):
        split = CS.resolve_calibration_split(fold)
        for season in (*split.base_seasons, *split.calibration_seasons,
                       *split.evaluation_seasons):
            assert int(season) != PROTECTED_HOLDOUT_SEASON
    with pytest.raises((E.ProtectedHoldoutError, E.ExperimentConfigError)):
        CS.run_calibration_suite(folds=("D1", "2025"), canonical=canonical)


def test_fair_comparison_same_raw_outer_vector(canonical, monkeypatch):
    captured: dict = {}
    original = CS._evaluate_variant

    def recording(**kwargs):
        captured[kwargs["method"]] = np.asarray(
            kwargs["probability"], dtype=float)
        return original(**kwargs)

    monkeypatch.setattr(CS, "_evaluate_variant", recording)
    import tempfile
    out = CS.run_calibration_fold(canonical, "D1",
                                  root=tempfile.mkdtemp(prefix="m8fair_"),
                                  return_predictions=True)
    assert set(captured) == set(METHODS)
    assert np.array_equal(captured["RAW"], out["predictions"]["RAW"])
    assert np.array_equal(captured["PLATT"], out["predictions"]["PLATT"])
    assert np.array_equal(captured["ISOTONIC"], out["predictions"]["ISOTONIC"])
    # RAW is untouched; Platt and isotonic are monotone maps of the SAME raw
    # vector (isotonic may introduce ties, so rank correlation can drop).
    from raceintel.model_lab.metrics import spearman
    assert spearman(captured["RAW"], captured["PLATT"]) == pytest.approx(1.0)
    order = np.argsort(captured["RAW"], kind="mergesort")
    assert np.all(np.diff(captured["PLATT"][order]) >= -1e-12)
    assert np.all(np.diff(captured["ISOTONIC"][order]) >= -1e-12)
    assert np.max(captured["RAW"]) <= 1.0 and np.min(captured["RAW"]) >= 0.0


def test_methods_have_distinct_experiment_identities(d1):
    ids = {m: d1["methods"][m]["experiment_id"] for m in METHODS}
    assert len(set(ids.values())) == 3
    for method, node in d1["methods"].items():
        assert node["model_parameters"]["C"] == 0.01
        assert node["model_parameters"]["calibration_method"] == method


def test_selected_method_probabilities_are_independent_binary(d1):
    for method in METHODS:
        node = d1["methods"][method]
        assert node["probability_min"] >= 0.0
        assert node["probability_max"] <= 1.0
        sync = node["synchronized"]["winner_top_k"]
        assert sync["status"] == "OK"


# --- selection rule unit tests -------------------------------------------------


def _per_fold(raw_ll, plat_ll, iso_ll, raw_br, plat_br, iso_br,
              folds=("D1", "D2", "D3")):
    def _d(values):
        if isinstance(values, (int, float)):
            return {f: float(values) for f in folds}
        return {f: float(v) for f, v in zip(folds, values)}
    return (_d(raw_ll), _d(plat_ll), _d(iso_ll),
            _d(raw_br), _d(plat_br), _d(iso_br))


def test_selection_calibrated_clearly_improves():
    ll = {"RAW": {"D1": 0.10, "D2": 0.10, "D3": 0.10},
          "PLATT": {"D1": 0.08, "D2": 0.08, "D3": 0.08},
          "ISOTONIC": {"D1": 0.09, "D2": 0.09, "D3": 0.09}}
    br = {"RAW": {"D1": 0.02, "D2": 0.02, "D3": 0.02},
          "PLATT": {"D1": 0.015, "D2": 0.015, "D3": 0.015},
          "ISOTONIC": {"D1": 0.018, "D2": 0.018, "D3": 0.018}}
    out = CS.select_calibration_method(log_loss=ll, brier=br)
    assert out["selected_method"] == "PLATT"


def test_selection_ll_improves_brier_worsens():
    ll = {"RAW": {"D1": 0.10, "D2": 0.10, "D3": 0.10},
          "PLATT": {"D1": 0.08, "D2": 0.08, "D3": 0.08},
          "ISOTONIC": {"D1": 0.09, "D2": 0.09, "D3": 0.09}}
    br = {"RAW": {"D1": 0.02, "D2": 0.02, "D3": 0.02},
          "PLATT": {"D1": 0.03, "D2": 0.03, "D3": 0.03},
          "ISOTONIC": {"D1": 0.025, "D2": 0.025, "D3": 0.025}}
    out = CS.select_calibration_method(log_loss=ll, brier=br)
    assert out["selected_method"] == "RAW"
    assert out["eligibility"]["PLATT"]["B_mean_brier_no_worse_than_raw"] \
        is False


def test_selection_two_of_three_material_regression_blocks():
    # Aggregate mean would improve, but D1/D2 materially regress (>1%).
    ll = {"RAW": {"D1": 0.100, "D2": 0.100, "D3": 0.100},
          "PLATT": {"D1": 0.104, "D2": 0.104, "D3": 0.080},
          "ISOTONIC": {"D1": 0.200, "D2": 0.200, "D3": 0.200}}
    br = {"RAW": {"D1": 0.02, "D2": 0.02, "D3": 0.02},
          "PLATT": {"D1": 0.02, "D2": 0.02, "D3": 0.02},
          "ISOTONIC": {"D1": 0.05, "D2": 0.05, "D3": 0.05}}
    out = CS.select_calibration_method(log_loss=ll, brier=br)
    assert out["material_regression"]["PLATT"]["n_material_regression"] == 2
    assert out["eligibility"]["PLATT"][
        "C_not_majority_material_regression"] is False
    assert out["selected_method"] == "RAW"


def test_selection_raw_wins_when_nothing_eligible():
    ll = {"RAW": {"D1": 0.10, "D2": 0.10, "D3": 0.10},
          "PLATT": {"D1": 0.11, "D2": 0.11, "D3": 0.11},
          "ISOTONIC": {"D1": 0.12, "D2": 0.12, "D3": 0.12}}
    br = {"RAW": {"D1": 0.02, "D2": 0.02, "D3": 0.02},
          "PLATT": {"D1": 0.03, "D2": 0.03, "D3": 0.03},
          "ISOTONIC": {"D1": 0.04, "D2": 0.04, "D3": 0.04}}
    out = CS.select_calibration_method(log_loss=ll, brier=br)
    assert out["selected_method"] == "RAW"
    assert out["eligible_methods"] == []


def test_selection_isotonic_wins():
    ll = {"RAW": {"D1": 0.10, "D2": 0.10, "D3": 0.10},
          "PLATT": {"D1": 0.095, "D2": 0.095, "D3": 0.095},
          "ISOTONIC": {"D1": 0.090, "D2": 0.090, "D3": 0.090}}
    br = {"RAW": {"D1": 0.020, "D2": 0.020, "D3": 0.020},
          "PLATT": {"D1": 0.019, "D2": 0.019, "D3": 0.019},
          "ISOTONIC": {"D1": 0.018, "D2": 0.018, "D3": 0.018}}
    out = CS.select_calibration_method(log_loss=ll, brier=br)
    assert out["selected_method"] == "ISOTONIC"


def test_selection_raw_platt_near_tie_prefers_raw():
    ll = {"RAW": {"D1": 0.10000, "D2": 0.10000, "D3": 0.10000},
          "PLATT": {"D1": 0.09995, "D2": 0.09995, "D3": 0.09995},
          "ISOTONIC": {"D1": 0.12, "D2": 0.12, "D3": 0.12}}
    br = {"RAW": {"D1": 0.0200, "D2": 0.0200, "D3": 0.0200},
          "PLATT": {"D1": 0.0199, "D2": 0.0199, "D3": 0.0199},
          "ISOTONIC": {"D1": 0.03, "D2": 0.03, "D3": 0.03}}
    out = CS.select_calibration_method(log_loss=ll, brier=br)
    assert out["selected_method"] == "RAW"
    assert out["tie_break_applied"] is True


def test_selection_platt_isotonic_near_tie_prefers_platt():
    ll = {"RAW": {"D1": 0.20, "D2": 0.20, "D3": 0.20},
          "PLATT": {"D1": 0.10000, "D2": 0.10000, "D3": 0.10000},
          "ISOTONIC": {"D1": 0.10005, "D2": 0.10005, "D3": 0.10005}}
    br = {"RAW": {"D1": 0.05, "D2": 0.05, "D3": 0.05},
          "PLATT": {"D1": 0.02, "D2": 0.02, "D3": 0.02},
          "ISOTONIC": {"D1": 0.02, "D2": 0.02, "D3": 0.02}}
    out = CS.select_calibration_method(log_loss=ll, brier=br)
    assert out["selected_method"] == "PLATT"


def test_selection_pathological_blocks_candidate():
    ll = {"RAW": {"D1": 0.10, "D2": 0.10, "D3": 0.10},
          "PLATT": {"D1": 0.08, "D2": 0.08, "D3": 0.08},
          "ISOTONIC": {"D1": 0.09, "D2": 0.09, "D3": 0.09}}
    br = {"RAW": {"D1": 0.02, "D2": 0.02, "D3": 0.02},
          "PLATT": {"D1": 0.015, "D2": 0.015, "D3": 0.015},
          "ISOTONIC": {"D1": 0.018, "D2": 0.018, "D3": 0.018}}
    out = CS.select_calibration_method(
        log_loss=ll, brier=br,
        diagnostics={"PLATT": {"pathological": True},
                     "ISOTONIC": {"pathological": True}})
    assert out["selected_method"] == "RAW"


def test_selection_signature_cannot_inspect_holdout_or_other_metrics():
    params = set(inspect.signature(CS.select_calibration_method).parameters)
    assert params == {"log_loss", "brier", "diagnostics",
                      "material_regression_rel", "tie_tolerance"}
    text = inspect.getsource(CS.select_calibration_method)
    for token in ("2025", "PROTECTED_HOLDOUT", "holdout_season",
                  "expected_calibration_error", "top1", "top3", "roc_auc",
                  "pr_auc"):
        assert token not in text, f"selection references {token!r}"


def test_selection_rejects_missing_method():
    with pytest.raises(E.ExperimentConfigError):
        CS.select_calibration_method(
            log_loss={"RAW": {"D1": 0.1}},
            brier={"RAW": {"D1": 0.02}})


# --- stored artifact + report --------------------------------------------------


def _load_summary():
    path = CS.default_out()
    summary = load_json_artifact_or_skip(path, purpose="M8 artifact")
    return summary, path


def test_m7_artifact_entry_contract():
    m7 = load_json_artifact_or_skip(
        CS.m7_artifact_path(), purpose="M7 artifact")
    assert m7["global_configuration"]["frozen_specification"]["C"] == 0.01
    assert m7["boundary_status"]["status"] == "RESOLVED"
    assert m7["holdout_accessed"] is False


def test_artifact_contract():
    summary, _ = _load_summary()
    assert summary["schema_version"] == "v1"
    assert summary["stage"] == "M8"
    assert summary["outer_folds"] == ["D1", "D2", "D3"]
    assert summary["frozen_c"] == 0.01
    assert summary["holdout_accessed"] is False
    assert summary["methods"] == list(METHODS)
    assert summary["platt_epsilon"] == CS.PLATT_EPSILON
    assert sorted(summary["per_fold"]) == ["D1", "D2", "D3"]
    assert summary["method_comparison"]["selected_method"] in METHODS
    for fold in summary["outer_folds"]:
        assert set(summary["per_fold"][fold]["methods"]) == set(METHODS)
        node = summary["split_design"][fold]
        assert node["base_seasons"][-1] < node["calibration_seasons"][0]
        assert node["calibration_seasons"][0] < node["evaluation_seasons"][0]


def test_artifact_traces_methods_to_stored_experiments():
    from raceintel.model_lab import results as RES
    summary, _ = _load_summary()
    seen_ids = set()
    for fold in summary["outer_folds"]:
        for method in METHODS:
            node = summary["per_fold"][fold]["methods"][method]
            config, result = RES.read_experiment(node["dest"])
            assert config.experiment_id == node["experiment_id"]
            assert config.experiment_id not in seen_ids
            seen_ids.add(config.experiment_id)
            assert config.model_parameters["C"] == 0.01
            assert config.model_parameters["calibration_method"] == method
            assert config.holdout_accessed is False
            stored = result.metrics["log_loss"]["race_macro"]["value"]
            assert node["race_macro"]["log_loss"] == pytest.approx(stored)
    assert len(seen_ids) == 9


def test_artifact_records_hash_and_determinism():
    summary, _ = _load_summary()
    hashes = summary["hashes"]
    assert hashes["phase2_matrix_content_hash"] == \
        "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db"
    assert hashes["phase2_parquet_byte_hash"] == \
        "b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3"
    assert hashes["m0_protocol_semantic_hash"] == \
        "0168f1d7fea584cd8a1e4dfe8267bb54dbec16aae60c92663c31115cb3ef53ce"
    det = summary["determinism"]
    assert det["same_experiment_ids"] is True
    assert det["metrics_identical"] is True
    assert det["max_abs_probability_difference_overall"] <= 1e-12


def test_artifact_selection_rule_fields():
    summary, _ = _load_summary()
    rule = summary["selection_rule"]
    assert rule["material_regression_rel"] == 0.01
    assert rule["tie_tolerance"] == 1e-4
    assert rule["ece_used_for_selection"] is False
    assert rule["frozen_before_results"] is True
    assert summary["method_comparison"]["selection"][
        "ece_used_for_selection"] is False


def test_artifact_temporal_design():
    summary, _ = _load_summary()
    expected = {
        "D1": ([2018, 2019, 2020], [2021], [2022]),
        "D2": ([2018, 2019, 2020, 2021], [2022], [2023]),
        "D3": ([2018, 2019, 2020, 2021, 2022], [2023], [2024]),
    }
    for fold, (base, cal, ev) in expected.items():
        node = summary["split_design"][fold]
        assert node["base_seasons"] == base
        assert node["calibration_seasons"] == cal
        assert node["evaluation_seasons"] == ev


def test_report_renders_from_summary_only():
    summary, _ = _load_summary()
    report = CS.render_calibration_report(summary)
    assert "CALIBRATION DEVELOPMENT EVALUATION" in report
    assert "BASE MODEL: FROZEN LOGISTIC REGRESSION C=0.01" in report
    assert "OUTER EVALUATION: 2022 / 2023 / 2024" in report
    assert "2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED" in report
    selected = summary["method_comparison"]["selected_method"]
    assert f"SELECT {selected}" in report
    probe = summary["per_fold"]["D1"]["methods"]["RAW"]["race_macro"][
        "log_loss"]
    assert f"{probe:.6f}" in report


# --- helpers -------------------------------------------------------------------


def _fold_signature(canonical, fold="D1"):
    """Fit the frozen D1 pipeline and return fitted-parameter fingerprints."""
    split = CS.resolve_calibration_split(fold)
    X_base, y_base, _ = materialize_seasons(
        canonical, split.base_seasons, "winner", "ALL_84")
    X_cal, y_cal, _ = materialize_seasons(
        canonical, split.calibration_seasons, "winner", "ALL_84")
    X_eval, _, _ = materialize_seasons(
        canonical, split.evaluation_seasons, "winner", "ALL_84")
    pre = PRE.fit_preprocessor(X_base, canonical.schema)
    model = TC.fit_fresh_model(TC.LOGREG_FAMILY, {"C": CS.FROZEN_C},
                               X_base, y_base, preprocessor=pre)
    raw = model.predict_positive_probability(X_eval)
    cal = model.predict_positive_probability(X_cal)
    platt = CS.fit_platt(cal, y_cal)
    iso = CS.fit_isotonic(cal, y_cal)
    return {
        "raw": raw,
        "platt_coefficient": platt.coefficient,
        "n_isotonic_thresholds": iso.n_thresholds,
    }
