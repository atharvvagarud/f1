"""Phase-7 S5: paired Monte Carlo sampling uncertainty.

Covers the canonical paired point estimate (must reproduce S4), the paired
standard error, the unpaired diagnostic and SE ratio, the n=0 / n=1 /
insufficient-pairs / constant-difference policies, the deterministic paired
percentile bootstrap (unit = the complete pair) including an exact pinned
result and seed isolation, CI classification, identity stability/sensitivity,
and the sampling-only semantics firewall.
"""

from __future__ import annotations

import ast
from pathlib import Path

import numpy as np
import pytest

from raceintel.strategy import (
    MIN_VALID_PAIRS_FOR_CI,
    UNCERTAINTY_AVAILABLE,
    UNCERTAINTY_INSUFFICIENT_PAIRS,
    UNCERTAINTY_NO_VALID_PAIRS,
    UNCERTAINTY_SEMANTICS,
    UNCERTAINTY_VERSION,
    classify_uncertainty,
    compute_uncertainty,
)
from raceintel.strategy.objectives import (
    OBJECTIVE_DEGRADATION,
    OBJECTIVE_IMPROVEMENT,
    OBJECTIVE_INCONCLUSIVE,
    OBJECTIVE_UNAVAILABLE,
)
from raceintel.strategy.paired import PerIndexOutcome
from raceintel.strategy.uncertainty import (
    DEFAULT_BOOTSTRAP_REPLICATES,
    QUANTILE_METHOD,
    pairwise_validity_counts,
)

ROOT = Path(__file__).resolve().parents[1]


def oc(index, finish, *, valid=True):
    if valid:
        return PerIndexOutcome(
            simulation_index=index, valid=True, winner_driver_id="w",
            finishing_order=("w",), target_finish_position=finish,
            target_won=finish == 1, target_podium=finish <= 3,
            intervention_status=None, intervention_reason=None)
    return PerIndexOutcome(
        simulation_index=index, valid=False, winner_driver_id=None,
        finishing_order=(), target_finish_position=None, target_won=None,
        target_podium=None, intervention_status=None, intervention_reason=None)


def finish_pair(baseline_finishes, candidate_finishes):
    base = tuple(oc(i, finish) for i, finish in enumerate(baseline_finishes))
    cand = tuple(oc(i, finish) for i, finish in enumerate(candidate_finishes))
    return base, cand


def uncertainty(baseline_finishes, candidate_finishes, *, metric,
                substrate="SUB", subject="SUBJ", **kwargs):
    base, cand = finish_pair(baseline_finishes, candidate_finishes)
    return compute_uncertainty(
        base, cand, metric=metric, substrate_identity=substrate,
        subject_identity=subject, **kwargs)


# ---------------------------------------------------------------------------
# Point estimate / standard errors.
# ---------------------------------------------------------------------------

def test_paired_point_estimate_and_se_match_manual_values():
    # d_finish = base - cand = [1, 2, 3]
    result = uncertainty([5, 5, 5], [4, 3, 2], metric="EXPECTED_FINISH")
    assert result.valid_pairs == 3
    assert result.point_estimate == pytest.approx(2.0)
    # sample std (ddof=1) = 1.0, SE = 1 / sqrt(3)
    assert result.paired_se == pytest.approx(1.0 / np.sqrt(3.0))


def test_win_and_podium_metrics_are_indicator_differences():
    win = uncertainty([2, 2, 1, 3], [1, 2, 2, 1], metric="WIN_PROBABILITY")
    # candidate wins at indices 0 and 3; baseline at index 2.
    assert win.point_estimate == pytest.approx((1 + 0 + (-1) + 1) / 4)
    podium = uncertainty([4, 2, 1, 5], [3, 2, 4, 5], metric="PODIUM_PROBABILITY")
    assert podium.point_estimate == pytest.approx((1 + 0 + (-1) + 0) / 4)


def test_unpaired_se_and_se_ratio_are_diagnostics():
    # baseline - candidate finish = [1, 0, 1].
    result = uncertainty([4, 5, 6], [3, 5, 5], metric="EXPECTED_FINISH")
    assert result.point_estimate == pytest.approx(2.0 / 3.0)
    # paired sample var = 1/3; SE = sqrt(1/3)/sqrt(3) = 1/3.
    assert result.paired_se == pytest.approx(1.0 / 3.0)
    # base [4,5,6] var = 1.0; candidate [3,5,5] var = 4/3; n = 3 each.
    expected_unpaired = np.sqrt(1.0 / 3.0 + (4.0 / 3.0) / 3.0)
    assert result.unpaired_se == pytest.approx(expected_unpaired)
    assert result.se_ratio == pytest.approx((1.0 / 3.0) / expected_unpaired)


def test_se_ratio_is_none_when_unpaired_is_undefined():
    result = uncertainty([5, 5, 5], [4, 4, 4], metric="EXPECTED_FINISH")
    assert result.unpaired_se == pytest.approx(0.0)
    assert result.se_ratio is None


# ---------------------------------------------------------------------------
# Small-n / degenerate policies.
# ---------------------------------------------------------------------------

def test_no_valid_pairs_is_unavailable_not_nan():
    result = uncertainty([], [], metric="EXPECTED_FINISH")
    assert result.valid_pairs == 0
    assert result.availability == UNCERTAINTY_NO_VALID_PAIRS
    assert result.unavailable_reason == "no_valid_pairs"
    assert result.point_estimate is None
    assert result.paired_se is None
    assert result.ci_low is None and result.ci_high is None


def test_single_pair_has_point_estimate_but_no_se_or_interval():
    result = uncertainty([5], [4], metric="EXPECTED_FINISH")
    assert result.valid_pairs == 1
    assert result.point_estimate == pytest.approx(1.0)
    assert result.paired_se is None
    assert result.availability == UNCERTAINTY_INSUFFICIENT_PAIRS
    assert result.unavailable_reason == "insufficient_complete_pairs"
    assert result.ci_low is None and result.ci_high is None


def test_below_min_pairs_withholds_interval_but_keeps_se():
    n = MIN_VALID_PAIRS_FOR_CI - 1
    result = uncertainty([5] * n, [4] * n, metric="EXPECTED_FINISH")
    assert result.valid_pairs == n
    assert result.availability == UNCERTAINTY_INSUFFICIENT_PAIRS
    assert result.point_estimate == pytest.approx(1.0)
    assert result.paired_se == pytest.approx(0.0)
    assert result.ci_low is None and result.ci_high is None


def test_invalid_pairs_are_excluded_from_the_complete_pair_set():
    base, cand = finish_pair([5, 5, 5], [4, 9, 4])
    base = list(base)
    base[1] = oc(1, 5, valid=False)
    result = compute_uncertainty(
        tuple(base), cand, metric="EXPECTED_FINISH",
        substrate_identity="SUB", subject_identity="SUBJ",
        bootstrap_seed_root=1)
    assert result.valid_pairs == 2
    assert result.point_estimate == pytest.approx(1.0)


def test_constant_positive_difference_has_zero_se_and_collapsed_ci():
    result = uncertainty([5] * 40, [4] * 40, metric="EXPECTED_FINISH")
    assert result.availability == UNCERTAINTY_AVAILABLE
    assert result.point_estimate == pytest.approx(1.0)
    assert result.paired_se == pytest.approx(0.0)
    assert result.ci_low == pytest.approx(1.0)
    assert result.ci_high == pytest.approx(1.0)
    assert result.uncertainty_semantics == UNCERTAINTY_SEMANTICS


def test_constant_negative_difference_classifies_as_degradation():
    result = uncertainty([4] * 40, [5] * 40, metric="EXPECTED_FINISH")
    assert result.point_estimate == pytest.approx(-1.0)
    assert classify_uncertainty(result) == OBJECTIVE_DEGRADATION


def test_constant_zero_difference_is_inconclusive_not_equivalence():
    result = uncertainty([5] * 40, [5] * 40, metric="EXPECTED_FINISH")
    assert result.point_estimate == pytest.approx(0.0)
    assert result.paired_se == pytest.approx(0.0)
    assert result.ci_low == 0.0 and result.ci_high == 0.0
    assert classify_uncertainty(result) == OBJECTIVE_INCONCLUSIVE


def test_sparse_and_constant_binary_metrics_do_not_fail():
    # Every candidate always wins, baseline never does.
    always = uncertainty([2] * 40, [1] * 40, metric="WIN_PROBABILITY")
    assert always.point_estimate == pytest.approx(1.0)
    assert always.ci_low == pytest.approx(1.0)
    assert classify_uncertainty(always) == OBJECTIVE_IMPROVEMENT
    # All-zero win difference.
    never = uncertainty([2] * 40, [2] * 40, metric="WIN_PROBABILITY")
    assert never.point_estimate == 0.0
    assert classify_uncertainty(never) == OBJECTIVE_INCONCLUSIVE


# ---------------------------------------------------------------------------
# Bootstrap.
# ---------------------------------------------------------------------------

PINNED_VECTOR_BASELINE = [5] * 30
PINNED_VECTOR_CANDIDATE = [4] * 15 + [5] * 15
PINNED_SEED = 17267596991454761751
PINNED_CI_LOW = 0.3333333333333333
PINNED_CI_HIGH = 0.7


def test_bootstrap_exact_pinned_result_under_frozen_algorithm():
    result = uncertainty(PINNED_VECTOR_BASELINE, PINNED_VECTOR_CANDIDATE,
                         metric="EXPECTED_FINISH", substrate="PINSUB",
                         subject="PINSUBJ")
    assert result.bootstrap_seed == PINNED_SEED
    assert result.point_estimate == pytest.approx(0.5)
    assert result.paired_se == pytest.approx(0.09284766908852593)
    assert result.ci_low == PINNED_CI_LOW
    assert result.ci_high == PINNED_CI_HIGH
    assert result.bootstrap_replicates == DEFAULT_BOOTSTRAP_REPLICATES
    assert result.quantile_method == QUANTILE_METHOD
    assert result.confidence_level == 0.95


def test_bootstrap_independent_reimplementation_matches():
    # Independently re-derive the paired percentile bootstrap in the test.
    result = uncertainty(PINNED_VECTOR_BASELINE, PINNED_VECTOR_CANDIDATE,
                         metric="EXPECTED_FINISH", substrate="PINSUB",
                         subject="PINSUBJ")
    values = np.asarray([1.0] * 15 + [0.0] * 15)
    n = values.shape[0]
    rng = np.random.default_rng(PINNED_SEED)
    means = np.empty(DEFAULT_BOOTSTRAP_REPLICATES)
    for replicate in range(DEFAULT_BOOTSTRAP_REPLICATES):
        indices = rng.integers(0, n, size=n)
        means[replicate] = values[indices].mean()
    assert result.ci_low == float(np.quantile(means, 0.025, method="linear"))
    assert result.ci_high == float(np.quantile(means, 0.975, method="linear"))


def test_bootstrap_is_deterministic():
    first = uncertainty([5] * 40, [4] * 20 + [5] * 20,
                        metric="EXPECTED_FINISH")
    second = uncertainty([5] * 40, [4] * 20 + [5] * 20,
                         metric="EXPECTED_FINISH")
    assert first.identity() == second.identity()
    assert first.ci_low == second.ci_low
    assert first.ci_high == second.ci_high


def test_bootstrap_seed_is_isolated_per_metric_and_subject():
    win = uncertainty([5] * 40, [4] * 40, metric="WIN_PROBABILITY")
    finish = uncertainty([5] * 40, [4] * 40, metric="EXPECTED_FINISH")
    other = uncertainty([5] * 40, [4] * 40, metric="EXPECTED_FINISH",
                        subject="OTHER")
    assert win.bootstrap_seed != finish.bootstrap_seed
    assert finish.bootstrap_seed != other.bootstrap_seed


def test_bootstrap_seed_root_changes_only_uncertainty_not_observations():
    first = uncertainty([5] * 40, [4] * 20 + [5] * 20,
                        metric="EXPECTED_FINISH", bootstrap_seed_root=1)
    second = uncertainty([5] * 40, [4] * 20 + [5] * 20,
                         metric="EXPECTED_FINISH", bootstrap_seed_root=2)
    assert first.point_estimate == second.point_estimate
    assert first.paired_se == second.paired_se
    assert first.bootstrap_seed != second.bootstrap_seed


# ---------------------------------------------------------------------------
# Classification.
# ---------------------------------------------------------------------------

def test_ci_classification_improvement_degradation_inconclusive():
    improvement = uncertainty([5] * 40, [4] * 40, metric="EXPECTED_FINISH")
    degradation = uncertainty([4] * 40, [5] * 40, metric="EXPECTED_FINISH")
    inconclusive = uncertainty([5] * 40, [5] * 40, metric="EXPECTED_FINISH")
    assert classify_uncertainty(improvement) == OBJECTIVE_IMPROVEMENT
    assert classify_uncertainty(degradation) == OBJECTIVE_DEGRADATION
    assert classify_uncertainty(inconclusive) == OBJECTIVE_INCONCLUSIVE


def test_withheld_or_missing_interval_classifies_unavailable():
    insufficient = uncertainty([5] * 10, [4] * 10, metric="EXPECTED_FINISH")
    empty = uncertainty([], [], metric="EXPECTED_FINISH")
    assert classify_uncertainty(insufficient) == OBJECTIVE_UNAVAILABLE
    assert classify_uncertainty(empty) == OBJECTIVE_UNAVAILABLE


# ---------------------------------------------------------------------------
# Identity.
# ---------------------------------------------------------------------------

def test_uncertainty_identity_is_stable_and_sensitive():
    base = uncertainty([5] * 40, [4] * 40, metric="EXPECTED_FINISH")
    assert base.identity() == base.identity()
    assert base.identity() != uncertainty(
        [5] * 40, [4] * 40, metric="WIN_PROBABILITY").identity()
    assert base.identity() != uncertainty(
        [5] * 40, [4] * 40, metric="EXPECTED_FINISH", subject="X").identity()


def test_uncertainty_identity_changes_with_confidence_and_counts():
    base = uncertainty([5] * 40, [4] * 40, metric="EXPECTED_FINISH")
    wider = uncertainty([5] * 40, [4] * 40, metric="EXPECTED_FINISH",
                        confidence_level=0.9)
    assert base.identity() != wider.identity()


# ---------------------------------------------------------------------------
# Semantics / firewall.
# ---------------------------------------------------------------------------

def test_uncertainty_is_sampling_only_and_versioned():
    assert UNCERTAINTY_VERSION == "v1"
    assert UNCERTAINTY_SEMANTICS == "MONTE_CARLO_SAMPLING_UNCERTAINTY_ONLY"
    result = uncertainty([5] * 40, [4] * 40, metric="EXPECTED_FINISH")
    payload = result.to_dict()
    assert payload["uncertainty_semantics"] == UNCERTAINTY_SEMANTICS
    assert "confidence interval" not in str(payload).lower()
    assert result.to_dict()["valid_pairs"] == 40


def test_uncertainty_module_reads_no_future_oracle_or_phase3_material():
    banned = ("raceintel.simulation.validation", "raceintel.replay", "raceintel.prediction",
              "raceintel.model_lab", "pandas", "sklearn")
    tree = ast.parse((ROOT / "raceintel" / "strategy" / "uncertainty.py").read_text())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for module in imported:
        assert not module.startswith(banned), f"uncertainty.py imports {module}"


def test_pairwise_validity_counts_use_candidate_ab_sets():
    a = tuple(oc(i, 2) for i in range(5))
    b = list(oc(i, 2) for i in range(5))
    b[0] = oc(0, 2, valid=False)
    b[1] = oc(1, 2, valid=False)
    a_list = list(a)
    a_list[2] = oc(2, 2, valid=False)
    counts = pairwise_validity_counts(
        type("C", (), {"intervention_outcomes": tuple(a_list)})(),
        type("C", (), {"intervention_outcomes": tuple(b)})())
    # a valid at {0,1,3,4}; b valid at {2,3,4}; both at {3,4}.
    assert counts == {"both_valid": 2, "a_only_valid": 2,
                      "b_only_valid": 1, "both_invalid": 0}
