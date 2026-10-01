"""M1.1 correctness patch tests (pre-M2 remediation, no training, no 2025).

Covers the four audit findings: PR-AUC tie handling (sklearn parity),
prediction-semantic <-> metric applicability guard, finite-input validation
for ordinal/regression metrics, and synchronized winner top-k eligibility.
All fixtures are synthetic; no Phase-2 artifact or holdout data is touched.
"""

import numpy as np
import pandas as pd
import pytest
from scipy.stats import spearmanr
from sklearn.metrics import (
    average_precision_score,
    mean_absolute_error,
    root_mean_squared_error,
)

from raceintel.model_lab import data as D
from raceintel.model_lab import errors as E
from raceintel.model_lab import metrics as M
from raceintel.model_lab import predictions as PR
from raceintel.model_lab.winner import synchronized_winner_top_k


# --- helpers ---------------------------------------------------------------

def _binary_pred(values, kind=PR.PredictionKind.BINARY_PROBABILITY,
                 semantics=PR.ProbabilitySemantics.INDEPENDENT_BINARY):
    ids = tuple(f"s{i}" for i in range(len(values)))
    return PR.PredictionResult(kind=kind, state_ids=ids,
                               values=np.array(values, dtype=float),
                               semantics=semantics)


def _ranking_pred(values):
    ids = tuple(f"s{i}" for i in range(len(values)))
    return PR.PredictionResult(kind=PR.PredictionKind.RANKING_SCORE,
                               state_ids=ids,
                               values=np.array(values, dtype=float))


def _continuous_pred(values):
    ids = tuple(f"s{i}" for i in range(len(values)))
    return PR.PredictionResult(
        kind=PR.PredictionKind.CONTINUOUS_PREDICTION, state_ids=ids,
        values=np.array(values, dtype=float))


def _ordinal_pred(values):
    ids = tuple(f"s{i}" for i in range(len(values)))
    return PR.PredictionResult(
        kind=PR.PredictionKind.ORDINAL_PREDICTION, state_ids=ids,
        values=np.array(values, dtype=float))


def _race_distribution_pred(values):
    n = len(values)
    ids = tuple(f"s{i}" for i in range(n))
    return PR.PredictionResult(
        kind=PR.PredictionKind.MUTUALLY_EXCLUSIVE_RACE_DISTRIBUTION,
        state_ids=ids, values=np.array(values, dtype=float),
        semantics=PR.ProbabilitySemantics.MUTUALLY_EXCLUSIVE_RACE,
        race_ids=tuple(["r"] * n))


def _winner_frame(rows):
    return D.CanonicalMatrix(None, pd.DataFrame(rows), {})


def _winner_pred(canonical, values):
    return PR.PredictionResult(
        kind=PR.PredictionKind.BINARY_PROBABILITY,
        state_ids=tuple(canonical.frame["state_id"]),
        values=np.array(values, dtype=float),
        semantics=PR.ProbabilitySemantics.INDEPENDENT_BINARY)


# --- FIX 1: PR-AUC tie handling ---------------------------------------------

def test_pr_auc_all_tied_matches_sklearn():
    y = [1, 0, 1, 0, 1, 0]
    s = [0.5] * 6
    assert M.pr_auc(y, s) == pytest.approx(0.5)
    assert M.pr_auc(y, s) == pytest.approx(average_precision_score(y, s))


def test_pr_auc_grouped_ties_match_sklearn():
    cases = [
        ([1, 0, 1, 0], [0.9, 0.9, 0.1, 0.1]),
        ([1, 1, 0, 0], [0.7, 0.7, 0.7, 0.1]),
        ([0, 1, 0, 1, 0, 1], [0.2, 0.8, 0.2, 0.8, 0.5, 0.5]),
        ([1, 0, 0, 1, 0, 1, 0, 0], [0.4] * 8),
    ]
    for y, s in cases:
        assert M.pr_auc(y, s) == pytest.approx(
            average_precision_score(y, s)), (y, s)


def test_pr_auc_no_ties_matches_sklearn():
    rng = np.random.RandomState(0)
    y = [1, 0, 1, 0, 0, 1, 0, 1, 0, 0]
    s = list(rng.rand(len(y)))
    assert M.pr_auc(y, s) == pytest.approx(average_precision_score(y, s))


def test_pr_auc_perfect_and_reversed_match_sklearn():
    assert M.pr_auc([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == pytest.approx(1.0)
    assert M.pr_auc([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]) == pytest.approx(
        average_precision_score([1, 1, 0, 0], [0.9, 0.8, 0.2, 0.1]))
    y, s = [1, 1, 0, 0], [0.1, 0.2, 0.8, 0.9]
    assert M.pr_auc(y, s) == pytest.approx(average_precision_score(y, s))


def test_pr_auc_class_imbalance_matches_sklearn():
    y = [1] + [0] * 9
    s = [0.9, 0.8, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1, 0.1]
    assert M.pr_auc(y, s) == pytest.approx(average_precision_score(y, s))
    y = [1] + [0] * 9
    s = [0.05] + [0.9] * 9
    assert M.pr_auc(y, s) == pytest.approx(average_precision_score(y, s))


def test_pr_auc_one_class_frozen_contract():
    assert M.pr_auc([0, 0], [0.5, 0.6]) is None
    assert M.pr_auc([1, 1], [0.5, 0.6]) == pytest.approx(
        average_precision_score([1, 1], [0.5, 0.6]))


# --- FIX 2: semantic <-> metric applicability guard --------------------------

def test_ranking_scores_rejected_from_probability_metrics():
    ranking = _ranking_pred([0.9, 0.1])
    for metric in ("log_loss", "brier"):
        with pytest.raises(E.UnsupportedMetricError):
            M.require_metric_applicability(ranking.kind, metric)
        with pytest.raises(E.UnsupportedMetricError):
            M.evaluate_metric(ranking, metric, [1, 0], [0.9, 0.1])
    # also by raw string kind: in-[0, 1] range must not smuggle it through
    with pytest.raises(E.UnsupportedMetricError):
        M.require_metric_applicability("RANKING_SCORE", "brier")
    with pytest.raises(E.UnsupportedMetricError):
        M.evaluate_metric(ranking, "expected_calibration_error",
                          [1, 0], [0.9, 0.1])


def test_binary_probabilities_still_evaluate():
    binary = _binary_pred([0.9, 0.1])
    assert M.evaluate_metric(binary, "brier", [1, 0], [0.9, 0.1]) == \
        pytest.approx(0.01)
    assert M.evaluate_metric(binary, "log_loss", [1, 0],
                             [0.9, 0.1]) == pytest.approx(M.binary_logloss(
                                 [1, 0], [0.9, 0.1]))
    assert M.evaluate_metric(binary, "roc_auc", [1, 0],
                             [0.9, 0.1]) == pytest.approx(1.0)
    assert M.evaluate_metric(binary, "pr_auc", [1, 0],
                             [0.9, 0.1]) == pytest.approx(1.0)


def test_ranking_scores_keep_rank_metrics():
    ranking = _ranking_pred([5.0, -3.0, 0.0])
    assert M.evaluate_metric(ranking, "roc_auc", [1, 0, 0],
                             [5.0, -3.0, 0.0]) == pytest.approx(1.0)
    assert M.evaluate_metric(ranking, "pr_auc", [1, 0, 0],
                             [5.0, -3.0, 0.0]) == pytest.approx(
                                 average_precision_score([1, 0, 0],
                                                         [5.0, -3.0, 0.0]))


def test_continuous_ordinal_reject_probability_metrics():
    for pred in (_continuous_pred([1.5, 2.5]), _ordinal_pred([1.0, 2.0])):
        for metric in ("log_loss", "brier", "roc_auc", "pr_auc"):
            with pytest.raises(E.UnsupportedMetricError):
                M.evaluate_metric(pred, metric, [1, 2], [1.5, 2.5])
    assert M.evaluate_metric(_continuous_pred([1.5, 2.5]), "mae", [1, 2],
                             [1.5, 2.5]) == pytest.approx(0.5)
    assert M.evaluate_metric(_ordinal_pred([1.0, 2.0]), "spearman",
                             [1, 2], [1.0, 2.0]) == pytest.approx(1.0)
    with pytest.raises(E.UnsupportedMetricError):
        M.evaluate_metric(_binary_pred([0.9, 0.1]), "mae", [1, 0],
                          [0.9, 0.1])


def test_race_distribution_kept_distinct():
    dist = _race_distribution_pred([0.7, 0.3])
    for metric in ("log_loss", "brier", "roc_auc", "pr_auc", "mae"):
        with pytest.raises(E.UnsupportedMetricError):
            M.evaluate_metric(dist, metric, [1, 0], [0.7, 0.3])
    # no race-distribution metric is invented in M1.1: fail loudly, not silent
    with pytest.raises(E.UnsupportedMetricError):
        M.evaluate_metric(dist, "race_level_log_loss", [1, 0], [0.7, 0.3])
    with pytest.raises(E.UnsupportedMetricError):
        M.require_metric_applicability(dist.kind, "nope")
    with pytest.raises(E.UnsupportedMetricError):
        M.require_metric_applicability("NOT_A_KIND", "brier")


# --- FIX 3: non-finite ordinal/regression inputs ------------------------------

_NON_FINITE = [float("nan"), float("inf"), float("-inf")]


@pytest.mark.parametrize("bad", _NON_FINITE)
def test_mae_rejects_non_finite(bad):
    with pytest.raises(E.InvalidPredictionError):
        M.mae([1.0, 2.0, 3.0], [1.0, bad, 3.0])
    with pytest.raises(E.InvalidPredictionError):
        M.mae([1.0, bad, 3.0], [1.0, 2.0, 3.0])


@pytest.mark.parametrize("bad", _NON_FINITE)
def test_rmse_rejects_non_finite(bad):
    with pytest.raises(E.InvalidPredictionError):
        M.rmse([1.0, 2.0, 3.0], [1.0, bad, 3.0])
    with pytest.raises(E.InvalidPredictionError):
        M.rmse([1.0, bad, 3.0], [1.0, 2.0, 3.0])


@pytest.mark.parametrize("bad", _NON_FINITE)
def test_spearman_rejects_non_finite(bad):
    with pytest.raises(E.InvalidPredictionError):
        M.spearman([1.0, 2.0, 3.0], [1.0, bad, 3.0])
    with pytest.raises(E.InvalidPredictionError):
        M.spearman([1.0, bad, 3.0], [1.0, 2.0, 3.0])


def test_finite_regression_matches_sklearn_scipy():
    y = [1.0, 2.0, 3.0, 4.0]
    p = [1.5, 1.8, 3.2, 3.9]
    assert M.mae(y, p) == pytest.approx(mean_absolute_error(y, p))
    assert M.rmse(y, p) == pytest.approx(root_mean_squared_error(y, p))
    assert M.spearman([1, 2, 3, 4], [1, 3, 2, 4]) == pytest.approx(
        spearmanr([1, 2, 3, 4], [1, 3, 2, 4]).statistic)
    assert M.compute_metric("mae", y, p) == pytest.approx(
        mean_absolute_error(y, p))
    with pytest.raises(E.InvalidPredictionError):
        M.compute_metric("rmse", y, [1.0, float("nan"), 3.0, 4.0])


# --- FIX 4: synchronized winner top-k eligibility -----------------------------

def _row(race, driver, lap, t, winner):
    return {"state_id": f"{race}|{driver}|{lap}|{t}", "race_id": race,
            "season": 2020, "driver_id": driver, "lap_number": lap,
            "state_time_s": t, "is_winner": winner}


def test_single_driver_roster_not_scored():
    rows = [_row("r", "a", 1, 10.0, True), _row("r", "a", 2, 20.0, True)]
    canonical = _winner_frame(rows)
    out = synchronized_winner_top_k(_winner_pred(canonical, [0.9, 0.8]),
                                    canonical, top_k=(1, 3))
    assert out["n_evaluation_states"] == 0
    assert out["n_skipped_degenerate"] == 2
    assert out["accuracy"]["top1"] is None
    assert out["accuracy"]["top3"] is None
    assert out["min_observable_field_size"] is None


def test_rival_unobservable_early_snapshots_skipped_then_field_scored():
    rows = [_row("r", "a", 1, 10.0, True), _row("r", "a", 2, 20.0, True),
            _row("r", "b", 5, 100.0, False)]
    canonical = _winner_frame(rows)
    out = synchronized_winner_top_k(
        _winner_pred(canonical, [0.9, 0.8, 0.1]), canonical,
        top_k=(1, 3))
    # T=10,20: only the winner observable -> degenerate, not top-1 hits
    assert out["n_skipped_degenerate"] == 2
    assert out["n_evaluation_states"] == 1
    assert out["accuracy"]["top1"] == pytest.approx(1.0)
    assert out["per_race"]["r"]["roster_size"] == 2


def test_two_driver_field_reports_insufficient_top3_coverage():
    rows = [_row("r", "a", 1, 10.0, True), _row("r", "b", 1, 10.0, False),
            _row("r", "a", 2, 20.0, True), _row("r", "b", 2, 20.0, False)]
    canonical = _winner_frame(rows)
    out = synchronized_winner_top_k(
        _winner_pred(canonical, [0.9, 0.1, 0.8, 0.2]), canonical,
        top_k=(1, 3))
    assert out["n_evaluation_states"] == 4
    assert out["accuracy"]["top1"] == pytest.approx(1.0)
    # explicit coverage signal: a 2-driver field cannot discriminate top-3
    assert out["min_observable_field_size"] == 2
    assert out["mean_observable_field_size"] == pytest.approx(2.0)
    assert out["per_race"]["r"]["roster_size"] == 2
    assert out["n_skipped_degenerate"] == 0


def test_full_field_scored_with_stale_rival_and_future_protection():
    rows = [_row("r", "c", 1, 5.0, False),
            _row("r", "a", 1, 10.0, True), _row("r", "b", 1, 12.0, False),
            _row("r", "a", 2, 20.0, True), _row("r", "b", 2, 25.0, False)]
    canonical = _winner_frame(rows)
    # b@lap2 (future at T=20) is ranked 0.99: only time-sync (b@lap1=0.01)
    # keeps top-1 a hit at T=20. c is stale-but-observable throughout.
    preds = {"r|c|1|5.0": 0.02, "r|a|1|10.0": 0.5, "r|b|1|12.0": 0.01,
             "r|a|2|20.0": 0.5, "r|b|2|25.0": 0.99}
    values = [preds[s] for s in canonical.frame["state_id"]]
    out = synchronized_winner_top_k(_winner_pred(canonical, values),
                                    canonical, top_k=(1, 3))
    assert out["n_skipped_winner_unobservable"] == 1  # T=5, winner not there
    assert out["n_evaluation_states"] == 4
    assert out["accuracy"]["top1"] == pytest.approx(3 / 4)
    assert out["accuracy"]["top3"] == pytest.approx(1.0)
    assert out["min_observable_field_size"] == 2


def test_same_timestamp_boundary_observable():
    rows = [_row("r", "a", 1, 10.0, True), _row("r", "b", 1, 10.0, False)]
    canonical = _winner_frame(rows)
    out = synchronized_winner_top_k(
        _winner_pred(canonical, [0.9, 0.1]), canonical, top_k=(1,))
    assert out["n_evaluation_states"] == 2
    assert out["accuracy"]["top1"] == pytest.approx(1.0)


def test_winner_top_k_rejects_non_probability_predictions():
    rows = [_row("r", "a", 1, 10.0, True), _row("r", "b", 1, 10.0, False)]
    canonical = _winner_frame(rows)
    ranking = PR.PredictionResult(
        kind=PR.PredictionKind.RANKING_SCORE,
        state_ids=tuple(canonical.frame["state_id"]),
        values=np.array([-90.0, -89.0]))
    with pytest.raises(E.InvalidPredictionError):
        synchronized_winner_top_k(ranking, canonical)
