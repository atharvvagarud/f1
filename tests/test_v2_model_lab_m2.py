"""M2 tests: development runner, suite, firewalls, determinism.

Covers the config-driven runner on development folds only, M1.1 metric
applicability integration, CLASS_PRIOR train-only provenance, target /
train-label / holdout firewalls, race-macro + state-pooled + stage +
calibration + synchronized top-k evaluation, serialization and
deterministic reruns. No candidate estimator is used and the 2025
holdout is never evaluated.
"""

import json

import numpy as np
import pandas as pd
import pytest

from model_lab_helpers import load_canonical_or_skip
from v2.model_lab import baselines as B
from v2.model_lab import errors as E
from v2.model_lab import experiment as EX
from v2.model_lab import metrics as M
from v2.model_lab import predictions as PR
from v2.model_lab import results as RES
from v2.model_lab import run as RUNCLI
from v2.model_lab import run_baselines as SUITECLI
from v2.model_lab import runner as RUN
from v2.model_lab import splits as S
from v2.model_lab import suite as SUITE

ROOT_TMP_NOTE = "M2 tests write experiments under tmp_path only"


@pytest.fixture(scope="module")
def canonical():
    return load_canonical_or_skip()


@pytest.fixture(scope="module")
def dataset_d1(canonical):
    return S.materialize(canonical, "winner", "D1", "ALL_84")


# --- development fold guard -------------------------------------------------

@pytest.mark.parametrize("fold", ["D1", "D2", "D3"])
def test_development_folds_resolve(fold):
    assert RUN.resolve_development_fold(fold).fold_id == fold


@pytest.mark.parametrize("fold", ["HOLDOUT", "2025", "HOLDOUT_2025"])
def test_holdout_folds_rejected(fold):
    with pytest.raises(E.ProtectedHoldoutError):
        RUN.resolve_development_fold(fold)


def test_final_fit_rejected_from_development_runner():
    with pytest.raises(E.ExperimentConfigError):
        RUN.resolve_development_fold("FINAL_FIT")


@pytest.mark.parametrize("fold", ["D4", "2022", "", "d1"])
def test_unknown_folds_rejected(fold):
    with pytest.raises(E.UnknownFoldError):
        RUN.resolve_development_fold(fold)


def test_suite_fold_parser_rejects_holdout_and_duplicates():
    with pytest.raises(E.ProtectedHoldoutError):
        SUITE.parse_folds("D1,HOLDOUT")
    with pytest.raises(E.ProtectedHoldoutError):
        SUITE.parse_folds("2025")
    with pytest.raises(E.UnknownFoldError):
        SUITE.parse_folds("D1,D4")
    with pytest.raises(E.ExperimentConfigError):
        SUITE.parse_folds("D1,D1")
    assert SUITE.parse_folds("D1,D2,D3") == ("D1", "D2", "D3")


def test_suite_baseline_parser():
    assert set(SUITE.parse_baselines(None, "winner")) == set(B.BASELINE_NAMES)
    with pytest.raises(E.ExperimentConfigError):
        SUITE.parse_baselines("NOPE", "winner")
    with pytest.raises(E.ExperimentConfigError):
        SUITE.parse_baselines("CURRENT_LEADER,CURRENT_LEADER", "winner")


def test_cli_rejects_holdout_folding():
    with pytest.raises(E.ProtectedHoldoutError):
        SUITECLI.main(["--folds", "D1,HOLDOUT"])
    with pytest.raises(E.ProtectedHoldoutError):
        RUNCLI.main(["--baseline", "CURRENT_LEADER", "--task", "winner",
                     "--fold", "HOLDOUT"])


# --- single experiment on an isolated root ----------------------------------

@pytest.fixture(scope="module")
def leader_d1(tmp_path_factory, canonical):
    root = tmp_path_factory.mktemp("m2exp")
    return RUN.run_experiment(task="winner", baseline="CURRENT_LEADER",
                              fold="D1", root=root)


def test_experiment_writes_and_round_trips(leader_d1):
    dest = leader_d1["dest"]
    assert "m2exp" in dest, ROOT_TMP_NOTE
    config, result = RES.read_experiment(dest)
    assert config.experiment_id == result.experiment_id
    assert result.status is EX.ExperimentStatus.OK
    assert config.holdout_accessed is False
    assert config.task == "winner" and config.fold == "D1"


def test_experiment_counts_match_m0(leader_d1):
    config = leader_d1["config"]
    assert (config.training_rows, config.validation_rows) == (88123, 23577)
    assert config.model_family == "baseline:CURRENT_LEADER"


def test_headline_and_diagnostic_scopes(leader_d1):
    metrics = leader_d1["result"].metrics
    for name in ("log_loss", "brier", "roc_auc", "pr_auc"):
        payload = metrics[name]
        assert payload["status"] == "OK"
        assert payload["race_macro"]["scope"] == "race_macro"
        assert payload["state_pooled"]["scope"] == "state_pooled"
        assert payload["race_macro"]["n_races"] == 22
        assert payload["race_macro"]["n_races_defined"] == 22


def test_corrected_pr_auc_path(leader_d1, canonical, dataset_d1):
    stored = leader_d1["result"].metrics["pr_auc"]["state_pooled"]["value"]
    frame = canonical.frame.loc[dataset_d1.y_validation.index].copy()
    _, pred = B.run_baseline(
        "CURRENT_LEADER", "winner",
        canonical.frame.loc[dataset_d1.y_train.index].copy(),
        frame, train_y=None)
    y = dataset_d1.y_validation.astype(float).to_numpy()
    p = PR.align(pred, list(frame["state_id"]))
    assert stored == pytest.approx(M.pr_auc(y, p))


def test_stage_and_calibration_present(leader_d1):
    result = leader_d1["result"]
    assert set(result.stage_metrics) == {"log_loss", "brier", "roc_auc",
                                         "pr_auc"}
    assert result.stage_metrics["brier"]["status"] == "OK"
    assert result.calibration["expected_calibration_error"] is not None
    assert len(result.calibration["bins"]) == 10


def test_topk_skip_and_coverage_metadata(leader_d1):
    topk = leader_d1["result"].race_metrics["winner_top_k"]
    assert topk["status"] == "OK"
    for key in ("n_skipped_no_predictions",
                "n_skipped_winner_unobservable", "n_skipped_degenerate",
                "min_observable_field_size", "mean_observable_field_size",
                "per_race"):
        assert key in topk, key
    assert topk["min_observable_field_size"] == 2  # insufficient top-3 field


def test_no_2025_in_validation(canonical, dataset_d1):
    assert int(dataset_d1.validation_metadata["season"].max()) == 2022


# --- M1.1 applicability integration ------------------------------------------

@pytest.fixture(scope="module")
def pace_d1(tmp_path_factory):
    root = tmp_path_factory.mktemp("m2pace")
    return RUN.run_experiment(task="winner", baseline="RECENT_PACE",
                              fold="D1", root=root)


def test_ranking_metrics_recorded_not_applicable(pace_d1):
    metrics = pace_d1["result"].metrics
    for name in ("log_loss", "brier"):
        payload = metrics[name]
        assert payload["status"] == "NOT_APPLICABLE"
        assert "reason" in payload
    for name in ("roc_auc", "pr_auc"):
        assert metrics[name]["status"] == "OK"
    assert pace_d1["result"].calibration is None
    topk = pace_d1["result"].race_metrics["winner_top_k"]
    assert topk["status"] == "NOT_APPLICABLE"
    assert pace_d1["result"].warnings, "N/A reasons must be recorded"


def test_ranking_missing_predictions_explicit(pace_d1):
    assert any("legitimate missing" in w
               for w in pace_d1["result"].warnings)


# --- CLASS_PRIOR provenance ----------------------------------------------------

@pytest.fixture(scope="module")
def prior_d1(tmp_path_factory, dataset_d1):
    root = tmp_path_factory.mktemp("m2prior")
    out = RUN.run_experiment(task="winner", baseline="CLASS_PRIOR",
                             fold="D1", root=root)
    return out, dataset_d1


def test_class_prior_uses_train_prevalence_only(prior_d1):
    out, dataset = prior_d1
    expected = float(dataset.y_train.astype(float).mean())
    assert out["result"].metrics["train_prevalence"]["value"] == \
        pytest.approx(expected)
    assert expected != pytest.approx(
        float(dataset.y_validation.astype(float).mean()))


# --- firewalls ------------------------------------------------------------------

def test_target_firewall(canonical, dataset_d1):
    train_frame = canonical.frame.loc[dataset_d1.y_train.index].copy()
    val_frame = canonical.frame.loc[dataset_d1.y_validation.index].copy()
    mutated = val_frame.copy()
    for col in ("is_winner", "final_position", "is_podium",
                "scored_points", "position_change_from_state",
                "gains_position_by_finish", "loses_position_by_finish"):
        if col not in mutated.columns:
            continue
        if col == "final_position":
            mutated[col] = 20.0
        else:
            mutated[col] = (~mutated[col].astype("boolean").fillna(
                False)).astype(int)
    for name in ("CURRENT_LEADER", "CURRENT_ORDER", "GRID_POLE",
                 "RECENT_PACE"):
        _, before = B.run_baseline(name, "winner", train_frame, val_frame,
                                   train_y=None)
        _, after = B.run_baseline(name, "winner", train_frame, mutated,
                                  train_y=None)
        assert np.array_equal(np.asarray(before.values, dtype=float),
                              np.asarray(after.values, dtype=float),
                              equal_nan=True), name


def test_train_label_firewall(canonical, dataset_d1):
    train_frame = canonical.frame.loc[dataset_d1.y_train.index].copy()
    val_frame = canonical.frame.loc[dataset_d1.y_validation.index].copy()
    y = dataset_d1.y_train
    flipped = ((~y.astype("boolean")).astype(int)).copy()
    _, changed = B.run_baseline("CLASS_PRIOR", "winner", train_frame,
                                val_frame, train_y=flipped)
    _, original = B.run_baseline("CLASS_PRIOR", "winner", train_frame,
                                 val_frame, train_y=y)
    assert not np.array_equal(np.asarray(changed.values),
                              np.asarray(original.values))
    for name in ("CURRENT_LEADER", "CURRENT_ORDER", "GRID_POLE",
                 "RECENT_PACE"):
        _, a = B.run_baseline(name, "winner", train_frame, val_frame,
                              train_y=y)
        _, b = B.run_baseline(name, "winner", train_frame, val_frame,
                              train_y=flipped)
        assert np.array_equal(np.asarray(a.values, dtype=float),
                              np.asarray(b.values, dtype=float),
                              equal_nan=True), name


def test_holdout_materialization_guarded(canonical):
    with pytest.raises(E.ProtectedHoldoutError):
        S.get_split("HOLDOUT")
    with pytest.raises(E.ProtectedHoldoutError):
        S.materialize(canonical, "winner", "HOLDOUT", "ALL_84")


# --- determinism ------------------------------------------------------------------

def test_deterministic_rerun(tmp_path_factory, leader_d1):
    root = tmp_path_factory.mktemp("m2rerun")
    first = leader_d1["dest"]
    with open(f"{first}/result.json", encoding="utf-8") as fh:
        first_bytes = fh.read()
    out = RUN.run_experiment(task="winner", baseline="CURRENT_LEADER",
                             fold="D1", root=root)
    assert out["config"].experiment_id == leader_d1["config"].experiment_id
    second = json.loads(open(f"{out['dest']}/result.json",
                             encoding="utf-8").read())
    assert second["metrics"] == json.loads(first_bytes)["metrics"]


# --- static no-ML guard ---------------------------------------------------------------

def test_no_candidate_estimator_use():
    from pathlib import Path
    root = Path(__file__).resolve().parents[1] / "v2" / "model_lab"
    forbidden = ("LogisticReg" + "ression", "HistGradient" + "Boosting",
                 "XGB" + "Classifier", "LGBM" + "Classifier",
                 "CatBoost" + "Classifier", "RandomForest" + "Classifier",
                 "ExtraTrees" + "Classifier", "MLP" + "Classifier",
                 "import " + "torch", "from " + "torch", ".fi" + "t(",
                 "from sk" + "learn", "import sk" + "learn")
    for path in (root / "runner.py", root / "run.py", root / "suite.py",
                 root / "run_baselines.py"):
        text = path.read_text()
        for token in forbidden:
            assert token not in text, f"{path.name}: forbidden {token!r}"
