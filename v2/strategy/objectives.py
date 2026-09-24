"""Phase-7 S5 explicit objective semantics.

The user must explicitly select ONE of exactly three v1 objectives; there is no
default objective and no hidden weighted score. Objective evaluation is an
additive view over an existing ``StrategyComparisonResult``; it reruns no
simulation.

    MAXIMIZE_WIN_PROBABILITY    -> canonical paired delta WIN_PROBABILITY
    MAXIMIZE_PODIUM_PROBABILITY -> canonical paired delta PODIUM_PROBABILITY
    MINIMIZE_EXPECTED_FINISH    -> canonical paired delta EXPECTED_FINISH

All canonical deltas are already oriented so positive = improvement, so every
objective is simply "higher is better" on its one metric. Metrics are never
combined.

Two distinct questions are answered with two distinct rules:

A. Candidate vs baseline -- the candidate's own paired difference distribution
   against the shared baseline is classified IMPROVEMENT / DEGRADATION /
   INCONCLUSIVE from its 95% paired bootstrap interval, or
   UNCERTAINTY_UNAVAILABLE when the interval is withheld.

B. Candidate vs candidate -- a DIRECT paired difference
   ``d_AB_i = o_A_i - o_B_i`` over the A/B complete valid index set is built and
   classified the same way. Separate baseline-relative intervals are never
   compared by CI overlap; that heuristic is deliberately not implemented.

This is Monte Carlo sampling classification only, never a claim of real-world
superiority, and never a recommendation. ``leader_by_point_estimate`` names the
highest simulator point estimate under the selected objective, and
``indistinguishable_from_leader`` lists the candidates the sampling interval
cannot distinguish from it.

Dependency direction: ``v2.strategy`` -> ``v2.simulation`` (and Strategy-internal).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Optional

from v2.simulation.state import canonical_sha256
from v2.strategy.uncertainty import (
    UNCERTAINTY_AVAILABLE,
    UncertaintyResult,
    candidate_uncertainty,
    comparison_substrate_identity,
    pairwise_uncertainty,
    pairwise_validity_counts,
)
from v2.strategy.uncertainty import (
    DEFAULT_BOOTSTRAP_REPLICATES,
    DEFAULT_BOOTSTRAP_SEED,
    DEFAULT_CONFIDENCE_LEVEL,
)

__all__ = [
    "OBJECTIVE_DEGRADATION",
    "OBJECTIVE_IMPROVEMENT",
    "OBJECTIVE_INCONCLUSIVE",
    "OBJECTIVE_METRIC",
    "OBJECTIVE_SAMPLING_SEMANTICS",
    "OBJECTIVE_UNAVAILABLE",
    "OBJECTIVE_VERSION",
    "STRATEGY_OBJECTIVES",
    "CandidateObjectiveEvaluation",
    "PairwiseObjectiveComparison",
    "StrategyObjective",
    "StrategyObjectiveResult",
    "classify_uncertainty",
    "evaluate_objective",
    "objective_metric",
    "objective_value",
]

#: Structural version of the S5 objective contract. A bump is required if the
#: objective set, the objective-to-metric mapping, the classification rule, the
#: candidate-vs-candidate method or the leader semantics change.
OBJECTIVE_VERSION = "v1"

OBJECTIVE_SAMPLING_SEMANTICS = "MONTE_CARLO_SAMPLING_CLASSIFICATION_ONLY"

OBJECTIVE_IMPROVEMENT = "IMPROVEMENT"
OBJECTIVE_DEGRADATION = "DEGRADATION"
OBJECTIVE_INCONCLUSIVE = "INCONCLUSIVE"
OBJECTIVE_UNAVAILABLE = "UNCERTAINTY_UNAVAILABLE"

_OBJECTIVE_CLASSIFICATIONS = (
    OBJECTIVE_IMPROVEMENT,
    OBJECTIVE_DEGRADATION,
    OBJECTIVE_INCONCLUSIVE,
    OBJECTIVE_UNAVAILABLE,
)

_OBJECTIVE_LIMITATIONS = (
    "Sampling intervals are exploratory Monte Carlo diagnostics; the many "
    "pairwise intervals are not a family-wise inferential procedure and no "
    "multiple-comparison correction or p-value is applied.",
    "Classifications describe Monte Carlo sampling uncertainty only; they are "
    "not real-world causal or superiority claims.",
    "A candidate-vs-candidate distinction uses a direct paired difference over "
    "the candidate A/B complete valid set; baseline validity is not required "
    "for it.",
    "leader_by_point_estimate names only the highest simulator point estimate "
    "under the selected objective; it is not a recommendation. When the "
    "interval cannot distinguish a candidate from the leader it is listed in "
    "indistinguishable_from_leader.",
    "Execution context (applied / suppressed / superseded / inert rates) is "
    "carried unchanged; a near-zero delta for a frequently inert or superseded "
    "intervention is not equivalence evidence.",
    "A candidate may be worse than baseline; all candidates being INCONCLUSIVE "
    "or DEGRADATION is a valid result and no intervention is forced to be "
    "preferred.",
)


class StrategyObjective(str, Enum):
    """The only objectives v1 exposes. No default is assumed anywhere."""

    MAXIMIZE_WIN_PROBABILITY = "MAXIMIZE_WIN_PROBABILITY"
    MAXIMIZE_PODIUM_PROBABILITY = "MAXIMIZE_PODIUM_PROBABILITY"
    MINIMIZE_EXPECTED_FINISH = "MINIMIZE_EXPECTED_FINISH"


#: Each objective maps to exactly ONE canonical paired metric. Metrics are never
#: combined into a weighted score.
OBJECTIVE_METRIC = {
    StrategyObjective.MAXIMIZE_WIN_PROBABILITY.value: "WIN_PROBABILITY",
    StrategyObjective.MAXIMIZE_PODIUM_PROBABILITY.value: "PODIUM_PROBABILITY",
    StrategyObjective.MINIMIZE_EXPECTED_FINISH.value: "EXPECTED_FINISH",
}

STRATEGY_OBJECTIVES = tuple(OBJECTIVE_METRIC)


def objective_value(value) -> str:
    """Coerce a controlled objective value; reject anything else (no default)."""
    if isinstance(value, StrategyObjective):
        return value.value
    if isinstance(value, str) and value in OBJECTIVE_METRIC:
        return value
    raise ValueError(
        f"objective must be one of {list(OBJECTIVE_METRIC)}, got {value!r}")


def objective_metric(value) -> str:
    """The one canonical paired metric an objective selects."""
    return OBJECTIVE_METRIC[objective_value(value)]


def classify_uncertainty(uncertainty: UncertaintyResult) -> str:
    """Classify a paired difference from its 95% paired bootstrap interval.

    CI low > 0 -> IMPROVEMENT; CI high < 0 -> DEGRADATION; otherwise
    INCONCLUSIVE. A withheld interval is UNCERTAINTY_UNAVAILABLE rather than a
    significance claim. This is Monte Carlo sampling classification only.
    """
    if uncertainty.availability != UNCERTAINTY_AVAILABLE \
            or uncertainty.ci_low is None or uncertainty.ci_high is None:
        return OBJECTIVE_UNAVAILABLE
    if uncertainty.ci_low > 0.0:
        return OBJECTIVE_IMPROVEMENT
    if uncertainty.ci_high < 0.0:
        return OBJECTIVE_DEGRADATION
    return OBJECTIVE_INCONCLUSIVE


@dataclass(frozen=True)
class CandidateObjectiveEvaluation:
    """One candidate's objective evaluation vs the shared baseline reference."""

    candidate_key: str
    candidate_identity: str
    metric: str
    point_estimate: Optional[float]
    classification: str
    uncertainty: UncertaintyResult
    execution: Optional[object] = None

    def __post_init__(self) -> None:
        if self.classification not in _OBJECTIVE_CLASSIFICATIONS:
            raise ValueError(
                f"unknown classification {self.classification!r}")

    def identity(self) -> str:
        return canonical_sha256({
            "objective_version": OBJECTIVE_VERSION,
            "candidate_identity": self.candidate_identity,
            "metric": self.metric,
            "point_estimate": self.point_estimate,
            "classification": self.classification,
            "uncertainty_identity": self.uncertainty.identity(),
            "execution": (self.execution.to_dict()
                          if self.execution is not None else None),
        })

    def to_dict(self) -> dict:
        return {
            "candidate_key": self.candidate_key,
            "candidate_identity": self.candidate_identity,
            "metric": self.metric,
            "point_estimate": self.point_estimate,
            "classification": self.classification,
            "uncertainty": self.uncertainty.to_dict(),
            "execution": (self.execution.to_dict()
                          if self.execution is not None else None),
        }


@dataclass(frozen=True)
class PairwiseObjectiveComparison:
    """Direct candidate-A-vs-candidate-B comparison (positive = A better)."""

    candidate_a_key: str
    candidate_b_key: str
    metric: str
    both_valid: int
    a_only_valid: int
    b_only_valid: int
    both_invalid: int
    point_estimate: Optional[float]
    classification: str
    uncertainty: UncertaintyResult

    def __post_init__(self) -> None:
        if self.classification not in _OBJECTIVE_CLASSIFICATIONS:
            raise ValueError(
                f"unknown classification {self.classification!r}")

    def identity(self) -> str:
        # The uncertainty identity already encodes the ordered A|B subject and
        # the metric, so it carries the orientation unambiguously.
        return canonical_sha256({
            "objective_version": OBJECTIVE_VERSION,
            "metric": self.metric,
            "both_valid": self.both_valid,
            "a_only_valid": self.a_only_valid,
            "b_only_valid": self.b_only_valid,
            "both_invalid": self.both_invalid,
            "point_estimate": self.point_estimate,
            "classification": self.classification,
            "uncertainty_identity": self.uncertainty.identity(),
        })

    def to_dict(self) -> dict:
        return {
            "candidate_a_key": self.candidate_a_key,
            "candidate_b_key": self.candidate_b_key,
            "metric": self.metric,
            "both_valid": self.both_valid,
            "a_only_valid": self.a_only_valid,
            "b_only_valid": self.b_only_valid,
            "both_invalid": self.both_invalid,
            "point_estimate": self.point_estimate,
            "classification": self.classification,
            "uncertainty": self.uncertainty.to_dict(),
        }


@dataclass(frozen=True)
class StrategyObjectiveResult:
    """Immutable additive objective view over one S4 comparison result."""

    objective: str
    metric: str
    comparison_supported: bool
    substrate_identity: str
    candidate_evaluations: tuple
    point_estimate_order: tuple
    baseline_relative_counts: tuple
    pairwise_comparisons: tuple
    leader_by_point_estimate: Optional[str]
    indistinguishable_from_leader: tuple
    distinguishable_from_leader: tuple
    baseline_reference_value: float = 0.0
    sampling_semantics: str = OBJECTIVE_SAMPLING_SEMANTICS
    limitations: tuple = _OBJECTIVE_LIMITATIONS
    objective_version: str = OBJECTIVE_VERSION

    def identity(self) -> str:
        return canonical_sha256({
            "objective_version": self.objective_version,
            "objective": self.objective,
            "metric": self.metric,
            "comparison_supported": self.comparison_supported,
            "substrate_identity": self.substrate_identity,
            "sampling_semantics": self.sampling_semantics,
            "candidate_evaluations": [
                evaluation.identity()
                for evaluation in self.candidate_evaluations],
            "point_estimate_order": list(self.point_estimate_order),
            "baseline_relative_counts": dict(self.baseline_relative_counts),
            "pairwise_comparisons": [
                comparison.identity()
                for comparison in self.pairwise_comparisons],
            "leader_by_point_estimate": self.leader_by_point_estimate,
            "indistinguishable_from_leader": list(
                self.indistinguishable_from_leader),
            "distinguishable_from_leader": list(
                self.distinguishable_from_leader),
            "baseline_reference_value": self.baseline_reference_value,
        })

    def to_dict(self) -> dict:
        return {
            "objective_version": self.objective_version,
            "objective_identity": self.identity(),
            "objective": self.objective,
            "metric": self.metric,
            "comparison_supported": self.comparison_supported,
            "substrate_identity": self.substrate_identity,
            "baseline_reference_value": self.baseline_reference_value,
            "sampling_semantics": self.sampling_semantics,
            "point_estimate_order": list(self.point_estimate_order),
            "baseline_relative_counts": dict(self.baseline_relative_counts),
            "leader_by_point_estimate": self.leader_by_point_estimate,
            "indistinguishable_from_leader": list(
                self.indistinguishable_from_leader),
            "distinguishable_from_leader": list(
                self.distinguishable_from_leader),
            "candidate_evaluations": [
                evaluation.to_dict()
                for evaluation in self.candidate_evaluations],
            "pairwise_comparisons": [
                comparison.to_dict()
                for comparison in self.pairwise_comparisons],
            "limitations": list(self.limitations),
        }


def _empty_result(objective: str, metric: str, comparison_supported: bool,
                  substrate_identity: str) -> StrategyObjectiveResult:
    return StrategyObjectiveResult(
        objective=objective, metric=metric,
        comparison_supported=comparison_supported,
        substrate_identity=substrate_identity,
        candidate_evaluations=(), point_estimate_order=(),
        baseline_relative_counts=tuple(
            (classification, 0)
            for classification in _OBJECTIVE_CLASSIFICATIONS),
        pairwise_comparisons=(), leader_by_point_estimate=None,
        indistinguishable_from_leader=(),
        distinguishable_from_leader=())


def evaluate_objective(comparison, objective, *,
                       bootstrap_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
                       confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
                       bootstrap_seed_root: int = DEFAULT_BOOTSTRAP_SEED
                       ) -> StrategyObjectiveResult:
    """Additive objective view over an S4 ``StrategyComparisonResult``.

    ``objective`` has no default: the caller must select it explicitly. No
    simulation is rerun; every quantity is derived from the retained per-index
    outcomes of the existing comparison.
    """
    objective = objective_value(objective)
    metric = OBJECTIVE_METRIC[objective]
    substrate = comparison_substrate_identity(comparison)

    if not comparison.supported:
        return _empty_result(objective, metric, False, substrate)

    evaluated = [candidate for candidate in comparison.candidates
                 if candidate.evaluated]
    canonical_position = {
        candidate.candidate.key: index
        for index, candidate in enumerate(comparison.candidates)}

    evaluations = []
    for candidate in evaluated:
        uncertainty = candidate_uncertainty(
            comparison, candidate, metric,
            bootstrap_replicates=bootstrap_replicates,
            confidence_level=confidence_level,
            bootstrap_seed_root=bootstrap_seed_root)
        evaluations.append(CandidateObjectiveEvaluation(
            candidate_key=candidate.candidate.key,
            candidate_identity=candidate.candidate.identity(),
            metric=metric,
            point_estimate=uncertainty.point_estimate,
            classification=classify_uncertainty(uncertainty),
            uncertainty=uncertainty,
            execution=candidate.execution))

    order = sorted(
        (evaluation for evaluation in evaluations
         if evaluation.point_estimate is not None),
        key=lambda evaluation: (-evaluation.point_estimate,
                                canonical_position[evaluation.candidate_key]))
    point_estimate_order = tuple(
        evaluation.candidate_key for evaluation in order)

    pairwise = []
    for first in range(len(evaluated)):
        for second in range(first + 1, len(evaluated)):
            a = evaluated[first]
            b = evaluated[second]
            uncertainty = pairwise_uncertainty(
                comparison, a, b, metric,
                bootstrap_replicates=bootstrap_replicates,
                confidence_level=confidence_level,
                bootstrap_seed_root=bootstrap_seed_root)
            counts = pairwise_validity_counts(a, b)
            pairwise.append(PairwiseObjectiveComparison(
                candidate_a_key=a.candidate.key,
                candidate_b_key=b.candidate.key,
                metric=metric,
                both_valid=counts["both_valid"],
                a_only_valid=counts["a_only_valid"],
                b_only_valid=counts["b_only_valid"],
                both_invalid=counts["both_invalid"],
                point_estimate=uncertainty.point_estimate,
                classification=classify_uncertainty(uncertainty),
                uncertainty=uncertainty))

    leader = point_estimate_order[0] if point_estimate_order else None
    distinguishable = []
    indistinguishable = []
    if leader is not None:
        for comparison_entry in pairwise:
            if leader not in (comparison_entry.candidate_a_key,
                              comparison_entry.candidate_b_key):
                continue
            other = (comparison_entry.candidate_b_key
                     if comparison_entry.candidate_a_key == leader
                     else comparison_entry.candidate_a_key)
            if comparison_entry.classification in (OBJECTIVE_IMPROVEMENT,
                                                   OBJECTIVE_DEGRADATION):
                distinguishable.append(other)
            else:
                indistinguishable.append(other)
        distinguishable.sort(key=lambda key: canonical_position[key])
        indistinguishable.sort(key=lambda key: canonical_position[key])

    counts = {
        classification: sum(
            1 for evaluation in evaluations
            if evaluation.classification == classification)
        for classification in _OBJECTIVE_CLASSIFICATIONS}

    return StrategyObjectiveResult(
        objective=objective, metric=metric, comparison_supported=True,
        substrate_identity=substrate,
        candidate_evaluations=tuple(evaluations),
        point_estimate_order=point_estimate_order,
        baseline_relative_counts=tuple(
            (classification, counts[classification])
            for classification in _OBJECTIVE_CLASSIFICATIONS),
        pairwise_comparisons=tuple(pairwise),
        leader_by_point_estimate=leader,
        indistinguishable_from_leader=tuple(indistinguishable),
        distinguishable_from_leader=tuple(distinguishable))
