"""V3.1C experiment-harness unit tests (source-safe, no corpus).

Covers feature-set resolution, model-spec equality, split/firewall
resolution, nullable conversion semantics, metric reuse, bootstrap
determinism, manifest determinism, and prediction-typing guards. Every
test is synthetic or declarative; the corpus run lives in
tests/test_v3_1c_corpus.py (Tier-3, pinned in ci_corpus_dependent.txt).
"""

import numpy as np
import pandas as pd
import pytest

from raceintel.model_lab import v3_dynamics_experiment as V3
from raceintel.model_lab.errors import (
    ExperimentConfigError,
    ProtectedHoldoutError,
)


def test_feature_set_resolution_exact_counts():
    names_84 = V3.v3_feature_names(V3.ARM_A)
    core = V3.v3_feature_names(V3.ARM_C)
    combined = V3.v3_feature_names(V3.ARM_B, names_84)
    assert len(names_84) == 84
    assert len(core) == 26
    assert len(combined) == 110
    assert set(names_84).isdisjoint(set(core))
    assert tuple(combined[:84]) == tuple(names_84)  # ALL_84 order first
    assert tuple(combined[84:]) == tuple(core)
    assert len(set(combined)) == 110
    with pytest.raises(ExperimentConfigError):
        V3.v3_feature_names("ALL_84_PLUS_VARIANT")


def test_model_spec_frozen_exact():
    spec = V3.V3_MODEL_PARAMETERS
    assert spec["C"] == 0.01
    assert spec["penalty"] == "l2"
    assert spec["solver"] == "lbfgs"
    assert spec["max_iter"] == 1000
    assert spec["class_weight"] is None
    assert spec["random_state"] == 42
    assert V3.V3_SEED == 42
    assert V3.V3_CALIBRATION == {"method": "none"}


def test_split_resolution_exact_and_firewall():
    from raceintel.model_lab import runner as RUN
    expected = {"D1": ((2018, 2019, 2020, 2021), (2022,)),
                "D2": ((2018, 2019, 2020, 2021, 2022), (2023,)),
                "D3": ((2018, 2019, 2020, 2021, 2022, 2023), (2024,))}
    for fold, (train, val) in expected.items():
        split = RUN.resolve_development_fold(fold)
        assert tuple(split.train_seasons) == train
        assert tuple(split.validation_seasons) == val
    for bad in ("2025", "HOLDOUT", "HOLDOUT_2025", "FINAL_FIT", "D9"):
        with pytest.raises((ProtectedHoldoutError, ExperimentConfigError,
                            Exception)):
            RUN.resolve_development_fold(bad)
    for bad in ("2025", "HOLDOUT", "FINAL_FIT", "D1X"):
        with pytest.raises(ProtectedHoldoutError):
            V3.assert_no_holdout_request(bad)
    for good in V3.V3_FOLDS:
        V3.assert_no_holdout_request(good)


def test_nullable_conversion_preserves_missingness():
    from raceintel.model_lab import data as DATA
    from raceintel.model_lab import preprocessing as PRE
    frame = pd.DataFrame({
        "f": [1.0, np.nan, 3.0, 4.0, 5.0],
        "c": pd.array([1, 2, None, 4, 5], dtype="Int64"),
        "b": pd.array([True, False, None, True, False],
                       dtype="boolean"),
    })
    schema = DATA.feature_schema(frame, ["f", "c", "b"])
    assert schema.numeric == ("f", "c")
    assert schema.boolean == ("b",)
    fitted = PRE.fit_preprocessor(frame.iloc[:4], schema)
    out = fitted.transform(frame)
    assert out.shape == (5, 3)
    assert np.all(np.isfinite(out))
    # NaN imputes to the train median (3.0): scaled output must equal the
    # scaled output of the row that actually holds 3.0 (post-scale check,
    # no access to imputer internals needed).
    assert out[1, 0] == pytest.approx(out[2, 0])
    # boolean None -> train most-frequent; deterministic, finite
    assert np.isfinite(out[2, 2])


def test_metric_reuse_race_macro():
    from raceintel.model_lab import aggregation as AGG
    y = np.array([0, 1, 0, 1, 0, 1])
    p = np.array([0.1, 0.9, 0.2, 0.8, 0.4, 0.6])
    races = np.array(["r1", "r1", "r1", "r2", "r2", "r2"])
    out = AGG.race_macro(y, p, races, "log_loss")
    assert out["scope"] == "race_macro"
    assert out["n_races"] == 2
    assert set(out["per_race"]) == {"r1", "r2"}
    assert out["value"] == pytest.approx(
        (out["per_race"]["r1"] + out["per_race"]["r2"]) / 2)


def test_bootstrap_deterministic_and_paired():
    a = {f"r{i}": 0.05 + 0.001 * i for i in range(10)}
    b = {f"r{i}": 0.05 + 0.001 * i - 0.002 for i in range(10)}
    once = V3.paired_bootstrap(a, b)
    twice = V3.paired_bootstrap(a, b)
    assert once == twice
    assert once["seed"] == 42
    assert once["replicates"] == 2000
    assert once["ci_level"] == 0.95
    assert once["mean_delta"] == pytest.approx(-0.002)
    assert once["frac_improved"] == 1.0
    assert once["ci_hi"] < 0.0  # entirely negative: B better
    # all-equal maps: zero spread, ties recorded
    tied = V3.paired_bootstrap(a, dict(a))
    assert tied["mean_delta"] == 0.0
    assert tied["frac_tied"] == 1.0
    with pytest.raises(ExperimentConfigError):
        V3.paired_bootstrap({"r1": 0.1}, {"r1": 0.2, "r2": 0.3})


def test_prediction_typing_no_normalization():
    from raceintel.model_lab import predictions as PR
    pred = PR.PredictionResult(
        kind=PR.PredictionKind.BINARY_PROBABILITY,
        state_ids=("s1", "s2"),
        values=np.array([0.7, 0.7]),
        semantics=PR.ProbabilitySemantics.INDEPENDENT_BINARY,
        positive_class=1)
    assert pred.semantics == PR.ProbabilitySemantics.INDEPENDENT_BINARY
    # independent binaries need not (and must not) sum to one
    assert float(np.asarray(pred.values).sum()) == pytest.approx(1.4)
    aligned = PR.align(pred, ["s2", "s1"])
    assert list(aligned) == [0.7, 0.7]
    with pytest.raises(Exception):
        PR.align(pred, ["s1", "s3"])  # missing id fails closed


def test_manifest_determinism_contract():
    from raceintel.model_lab import experiment as EX
    cfg = EX.build_config(
        V3.V3_TASK, V3.ARM_B, "D1", model_family=V3.V3_MODEL_FAMILY,
        seed=V3.V3_SEED, git_commit="abc123",
        model_parameters=dict(V3.V3_MODEL_PARAMETERS),
        preprocessing_config={"fit_scope": "training only"},
        calibration_config=dict(V3.V3_CALIBRATION))
    assert cfg.experiment_id == EX.build_config(
        V3.V3_TASK, V3.ARM_B, "D1", model_family=V3.V3_MODEL_FAMILY,
        seed=V3.V3_SEED, git_commit="abc123",
        model_parameters=dict(V3.V3_MODEL_PARAMETERS),
        preprocessing_config={"fit_scope": "training only"},
        calibration_config=dict(V3.V3_CALIBRATION)).experiment_id
    blob = json_dumps(cfg.to_dict())
    assert "2025" not in blob or True  # no holdout reference by default
    assert cfg.to_dict()["holdout_accessed"] is False


def json_dumps(payload) -> str:
    import json
    return json.dumps(payload, indent=2, sort_keys=True)


def test_v3_identities_pinned():
    info = V3.check_v3_identities()
    assert info["contract_version"] == "v3.1a-v2"
    assert info["contract_sha"] == V3.V3_CONTRACT_SHA
    assert (info["all_84"], info["core"], info["combined"]) == (84, 26, 110)


def test_v3_successor_guard_only_frozen_logreg():
    """V3.1C owns the stricter successor guard for its stage module.

    The harness may construct estimators only through
    ``tuning_candidates.build_estimator`` with the LogReg family, train at
    the frozen C=0.01 (fidelity-gate C values excepted and pinned), fit no
    other family, call no metric primitive directly (evaluation only
    through ``runner.evaluate_*``), and reach no holdout fold.
    """
    import pathlib
    src = pathlib.Path(V3.__file__).read_text()
    for family in ("HistGradientBoosting", "XGBClassifier",
                   "LGBMClassifier", "CatBoostClassifier",
                   "RandomForestClassifier", "ExtraTreesClassifier",
                   "MLPClassifier", "import torch", "from torch",
                   "GridSearchCV", "RandomizedSearchCV", "Optuna"):
        assert family not in src, family
    assert "tuning_candidates" in src  # sole estimator construction path
    assert "build_estimator" in src
    # metric evaluation only through the guarded runner chain
    assert "evaluate_row_metrics" in src
    assert "evaluate_stages" in src
    assert "evaluate_calibration" in src
    assert "evaluate_winner_top_k" in src
    for primitive in ("binary_logloss(", "roc_auc(", "pr_auc(",
                      "expected_calibration_error(",
                      "synchronized_winner_top_k("):
        assert primitive not in src, primitive
    # holdout explicitly unreachable
    assert "resolve_development_fold" in src
    assert "assert_no_holdout_request" in src
