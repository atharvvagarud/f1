"""Phase-7 S5 paired Monte Carlo sampling uncertainty.

S5 answers ONE narrow question: *given Monte Carlo sampling noise, how precisely
has the paired simulation delta between a candidate and the baseline been
estimated?* It consumes the compact terminal per-index outcomes S4 already
produced and never reruns a simulation.

What this uncertainty IS
------------------------
``MONTE_CARLO_SAMPLING_UNCERTAINTY_ONLY``: the sampling variability of the mean
paired difference over complete valid simulation pairs, with a deterministic
paired percentile bootstrap interval.

What this uncertainty is NOT
----------------------------
It is not parameter, model-form, pit-loss, pace, traffic, compound-effect,
future-weather, or real-world counterfactual uncertainty. The interval is a
Monte Carlo resampling interval, not a confidence interval for the true
real-world causal effect of a pit strategy. Historical data cannot validate the
counterfactual level.

Canonical estimand (frozen, matches S4)
---------------------------------------
For candidate ``c`` and metric ``m`` over the complete-valid-pair set::

    d_i = o_candidate_i - o_baseline_i

with per-metric ``o`` oriented so positive always means *improvement*::

    WIN_PROBABILITY    o = I(driver wins)
    PODIUM_PROBABILITY o = I(driver podiums)
    EXPECTED_FINISH    o = -finish_position

``point_estimate = mean(d_i)`` therefore reproduces the S4 canonical candidate
delta bit-for-bit for every metric and every ``n > 0``.

Paired standard error: ``sample_std(d_i, ddof=1) / sqrt(n)``.

Optional diagnostic (NOT canonical): an unpaired standard error built from the
two arms independently, plus ``se_ratio = paired_se / unpaired_se``. S3 adopted
CRN only WITH limitations, so the ratio is reported per candidate/metric and is
never used to choose "the smaller SE".

Bootstrap
---------
The bootstrap unit is the complete simulation PAIR. Baseline and candidate are
never resampled independently. ``B = 2000`` paired percentile replicates at a
95% level, using a Strategy-owned statistical RNG stream derived deterministically
from the candidate-set-independent comparison substrate plus the subject
identity and metric. It never touches the simulation / pit / pace / compound RNG.

Dependency direction: ``v2.strategy`` -> ``v2.simulation``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np

from v2.simulation.state import canonical_sha256

__all__ = [
    "BOOTSTRAP_CI_METHOD",
    "DEFAULT_BOOTSTRAP_REPLICATES",
    "DEFAULT_BOOTSTRAP_SEED",
    "DEFAULT_CONFIDENCE_LEVEL",
    "MIN_VALID_PAIRS_FOR_CI",
    "QUANTILE_METHOD",
    "UNCERTAINTY_AVAILABLE",
    "UNCERTAINTY_INSUFFICIENT_PAIRS",
    "UNCERTAINTY_METRICS",
    "UNCERTAINTY_NO_VALID_PAIRS",
    "UNCERTAINTY_REASONS",
    "UNCERTAINTY_SEMANTICS",
    "UNCERTAINTY_VERSION",
    "UncertaintyResult",
    "candidate_uncertainty",
    "comparison_substrate_identity",
    "compute_uncertainty",
    "metric_value",
    "pairwise_uncertainty",
    "pairwise_validity_counts",
]

#: Structural version of the S5 uncertainty contract. A bump is required if the
#: estimand, the pair unit, the SE formula, the bootstrap algorithm/unit, the
#: default replicate count, the default confidence level, the quantile method or
#: the small-n policy changes.
UNCERTAINTY_VERSION = "v1"

#: The only uncertainty this layer represents.
UNCERTAINTY_SEMANTICS = "MONTE_CARLO_SAMPLING_UNCERTAINTY_ONLY"

#: The three canonical paired metrics (shared vocabulary with objectives.py).
UNCERTAINTY_METRICS = (
    "WIN_PROBABILITY",
    "PODIUM_PROBABILITY",
    "EXPECTED_FINISH",
)

#: Small-n policy. Default production count is 1 000 trajectories; the lower
#: bound is only reached when simulations are invalid. A percentile bootstrap
#: interval below this many complete pairs is unstable, so it is withheld
#: instead of reported. Point estimates and the paired SE (when ``n >= 2``) are
#: still reported with a structured reason.
MIN_VALID_PAIRS_FOR_CI = 30

DEFAULT_BOOTSTRAP_REPLICATES = 2000
DEFAULT_CONFIDENCE_LEVEL = 0.95

#: Strategy statistical-analysis seed root. This is NOT a simulation seed and
#: changing it never changes simulated outcomes.
DEFAULT_BOOTSTRAP_SEED = 20240101

#: Pinned NumPy percentile method (linear interpolation, the NumPy default).
QUANTILE_METHOD = "linear"

BOOTSTRAP_CI_METHOD = "paired_percentile_bootstrap"

UNCERTAINTY_AVAILABLE = "AVAILABLE"
UNCERTAINTY_INSUFFICIENT_PAIRS = "INSUFFICIENT_PAIRS"
UNCERTAINTY_NO_VALID_PAIRS = "NO_VALID_PAIRS"

UNAVAILABLE_NO_VALID_PAIRS = "no_valid_pairs"
UNAVAILABLE_INSUFFICIENT_PAIRS = "insufficient_complete_pairs"

UNCERTAINTY_REASONS = (
    UNAVAILABLE_NO_VALID_PAIRS,
    UNAVAILABLE_INSUFFICIENT_PAIRS,
)


def metric_value(outcome, metric: str) -> float:
    """Per-index objective outcome, oriented so positive = improvement.

    ``outcome`` is a valid ``PerIndexOutcome``. ``EXPECTED_FINISH`` returns the
    negated finish position so that higher is always better; the resulting
    paired difference is then exactly the frozen S4
    ``baseline_finish - candidate_finish``.
    """
    if metric == "WIN_PROBABILITY":
        return float(outcome.target_won)
    if metric == "PODIUM_PROBABILITY":
        return float(outcome.target_podium)
    if metric == "EXPECTED_FINISH":
        return -float(outcome.target_finish_position)
    raise ValueError(f"unknown uncertainty metric {metric!r}")


def comparison_substrate_identity(comparison) -> str:
    """Candidate-set-independent identity of the shared comparison substrate.

    Deliberately excludes the candidate payloads, so the uncertainty identity of
    candidate A is identical whether A is evaluated alone or among nine
    candidates (subset consistency).
    """
    return canonical_sha256({
        "state_identity": comparison.state_identity,
        "parameter_identity": comparison.parameter_identity,
        "config_identity": comparison.config_identity,
        "master_seed": comparison.master_seed,
        "simulation_count": comparison.simulation_count,
        "target_driver_id": comparison.target_driver_id,
    })


def derive_bootstrap_seed(*, bootstrap_seed_root: int, substrate_identity: str,
                          subject_identity: str, metric: str) -> int:
    """Deterministic per-(substrate, subject, metric) bootstrap seed.

    Independent streams are derived per candidate/metric (and per candidate
    pair/metric) so no mutable RNG is shared across candidate iteration; a
    candidate's stream cannot change because a sibling candidate exists.
    """
    return int(canonical_sha256({
        "bootstrap_seed_root": bootstrap_seed_root,
        "substrate_identity": substrate_identity,
        "subject_identity": subject_identity,
        "metric": metric,
        "uncertainty_version": UNCERTAINTY_VERSION,
    })[:16], 16)


@dataclass(frozen=True)
class UncertaintyResult:
    """Immutable S5 sampling-uncertainty result for one metric and subject.

    ``availability`` describes the sampling INTERVAL: ``AVAILABLE`` when the
    bootstrap CI was computed, ``INSUFFICIENT_PAIRS`` when there are complete
    pairs but fewer than ``MIN_VALID_PAIRS_FOR_CI``, and ``NO_VALID_PAIRS`` when
    there are none. A field is ``None`` only when it is genuinely undefined
    (never a NaN).
    """

    metric: str
    substrate_identity: str
    subject_identity: str
    availability: str
    unavailable_reason: Optional[str]
    point_estimate: Optional[float]
    paired_se: Optional[float]
    unpaired_se: Optional[float]
    se_ratio: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    valid_pairs: int
    confidence_level: float
    bootstrap_replicates: int
    bootstrap_seed: int
    uncertainty_semantics: str = UNCERTAINTY_SEMANTICS
    quantile_method: str = QUANTILE_METHOD
    ci_method: str = BOOTSTRAP_CI_METHOD
    uncertainty_version: str = UNCERTAINTY_VERSION
    unpaired_semantics: Optional[str] = None

    def __post_init__(self) -> None:
        if self.metric not in UNCERTAINTY_METRICS:
            raise ValueError(f"unknown metric {self.metric!r}")
        if self.availability not in (UNCERTAINTY_AVAILABLE,
                                     UNCERTAINTY_INSUFFICIENT_PAIRS,
                                     UNCERTAINTY_NO_VALID_PAIRS):
            raise ValueError(f"unknown availability {self.availability!r}")
        if self.unavailable_reason is not None \
                and self.unavailable_reason not in UNCERTAINTY_REASONS:
            raise ValueError(
                f"unknown unavailable_reason {self.unavailable_reason!r}")
        if not 0.0 < self.confidence_level < 1.0:
            raise ValueError("confidence_level must be in (0, 1)")
        if self.bootstrap_replicates <= 0:
            raise ValueError("bootstrap_replicates must be positive")

    def identity(self) -> str:
        return canonical_sha256({
            "uncertainty_version": self.uncertainty_version,
            "uncertainty_semantics": self.uncertainty_semantics,
            "ci_method": self.ci_method,
            "quantile_method": self.quantile_method,
            "metric": self.metric,
            "substrate_identity": self.substrate_identity,
            "subject_identity": self.subject_identity,
            "availability": self.availability,
            "unavailable_reason": self.unavailable_reason,
            "valid_pairs": self.valid_pairs,
            "confidence_level": self.confidence_level,
            "bootstrap_replicates": self.bootstrap_replicates,
            "bootstrap_seed": self.bootstrap_seed,
            "point_estimate": self.point_estimate,
            "paired_se": self.paired_se,
            "unpaired_se": self.unpaired_se,
            "se_ratio": self.se_ratio,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
        })

    def to_dict(self) -> dict:
        return {
            "uncertainty_version": self.uncertainty_version,
            "uncertainty_identity": self.identity(),
            "metric": self.metric,
            "substrate_identity": self.substrate_identity,
            "subject_identity": self.subject_identity,
            "availability": self.availability,
            "unavailable_reason": self.unavailable_reason,
            "point_estimate": self.point_estimate,
            "paired_se": self.paired_se,
            "unpaired_se": self.unpaired_se,
            "se_ratio": self.se_ratio,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "valid_pairs": self.valid_pairs,
            "confidence_level": self.confidence_level,
            "bootstrap_replicates": self.bootstrap_replicates,
            "bootstrap_seed": self.bootstrap_seed,
            "ci_method": self.ci_method,
            "quantile_method": self.quantile_method,
            "uncertainty_semantics": self.uncertainty_semantics,
            "unpaired_semantics": self.unpaired_semantics,
        }


def _paired_series(baseline_outcomes, candidate_outcomes, metric):
    """Values of ``o_cand - o_base`` over complete valid pairs.

    Aligned explicitly by ``simulation_index`` (every arm is generated from the
    same config and index substrate), never by list position alone.
    """
    base_by_index = {outcome.simulation_index: outcome
                     for outcome in baseline_outcomes}
    values = []
    for candidate in candidate_outcomes:
        base = base_by_index.get(candidate.simulation_index)
        if base is None or not (base.valid and candidate.valid):
            continue
        values.append(metric_value(candidate, metric) - metric_value(base, metric))
    return values


def _sample_variance(values) -> Optional[float]:
    n = len(values)
    if n < 2:
        return None
    mean = sum(values) / n
    return sum((value - mean) ** 2 for value in values) / (n - 1)


def _arm_values(outcomes, metric):
    """Arm's own valid per-index metric values (unpaired diagnostic basis)."""
    if metric == "EXPECTED_FINISH":
        return [float(o.target_finish_position) for o in outcomes if o.valid]
    if metric == "WIN_PROBABILITY":
        return [float(o.target_won) for o in outcomes if o.valid]
    return [float(o.target_podium) for o in outcomes if o.valid]


def _unpaired_se(baseline_outcomes, candidate_outcomes, metric
                 ) -> tuple[Optional[float], Optional[str]]:
    """Unpaired standard error from the two arms independently (diagnostic)."""
    base = _arm_values(baseline_outcomes, metric)
    cand = _arm_values(candidate_outcomes, metric)
    base_var = _sample_variance(base)
    cand_var = _sample_variance(cand)
    if base_var is None or cand_var is None:
        return None, "arm_variance_undefined"
    if len(base) == 0 or len(cand) == 0:
        return None, "arm_has_no_valid_simulations"
    return ((base_var / len(base) + cand_var / len(cand)) ** 0.5), None


def _bootstrap_ci(values, *, replicates: int, confidence_level: float,
                  seed: int) -> tuple[float, float]:
    """Deterministic paired percentile bootstrap of the mean difference.

    Each replicate resamples ``n`` pair indices with replacement from the SAME
    ``values`` vector (the pair is the unit); baseline and candidate are never
    resampled independently. The loop bounds peak memory at ``O(n)`` rather than
    ``O(B * n)``.
    """
    arr = np.asarray(values, dtype="<f8")
    n = arr.shape[0]
    rng = np.random.default_rng(seed)
    means = np.empty(replicates, dtype="<f8")
    for replicate in range(replicates):
        indices = rng.integers(0, n, size=n)
        means[replicate] = arr[indices].mean()
    alpha = (1.0 - confidence_level) / 2.0
    low = float(np.quantile(means, alpha, method=QUANTILE_METHOD))
    high = float(np.quantile(means, 1.0 - alpha, method=QUANTILE_METHOD))
    return low, high


def compute_uncertainty(baseline_outcomes, candidate_outcomes, *, metric,
                        substrate_identity: str, subject_identity: str,
                        bootstrap_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
                        confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
                        bootstrap_seed_root: int = DEFAULT_BOOTSTRAP_SEED,
                        include_unpaired: bool = True) -> UncertaintyResult:
    """Compute S5 sampling uncertainty for one metric and one paired subject.

    ``baseline_outcomes`` / ``candidate_outcomes`` are aligned per-index outcome
    tuples (``PerIndexOutcome``). For a candidate-vs-baseline contrast the
    candidate-vs-baseline set is the complete valid pair set. For a direct
    candidate-vs-candidate contrast the same function is called with candidate B
    as the "baseline" over the candidate A/B complete valid set.
    """
    seed = derive_bootstrap_seed(
        bootstrap_seed_root=bootstrap_seed_root,
        substrate_identity=substrate_identity,
        subject_identity=subject_identity,
        metric=metric)
    values = _paired_series(baseline_outcomes, candidate_outcomes, metric)
    n = len(values)

    unpaired_se = None
    unpaired_reason = None
    if include_unpaired:
        unpaired_se, unpaired_reason = _unpaired_se(
            baseline_outcomes, candidate_outcomes, metric)

    if n == 0:
        return UncertaintyResult(
            metric=metric, substrate_identity=substrate_identity,
            subject_identity=subject_identity,
            availability=UNCERTAINTY_NO_VALID_PAIRS,
            unavailable_reason=UNAVAILABLE_NO_VALID_PAIRS,
            point_estimate=None, paired_se=None, unpaired_se=unpaired_se,
            se_ratio=None, ci_low=None, ci_high=None, valid_pairs=0,
            confidence_level=confidence_level,
            bootstrap_replicates=bootstrap_replicates, bootstrap_seed=seed,
            unpaired_semantics=unpaired_reason)

    point_estimate = sum(values) / n
    variance = _sample_variance(values)
    # n == 1 -> the sample variance (ddof=1) is undefined; no NaN is emitted.
    paired_se = (variance ** 0.5 / (n ** 0.5)) if variance is not None else None
    se_ratio = None
    if paired_se is not None and unpaired_se not in (None, 0.0):
        se_ratio = paired_se / unpaired_se

    if n < MIN_VALID_PAIRS_FOR_CI:
        return UncertaintyResult(
            metric=metric, substrate_identity=substrate_identity,
            subject_identity=subject_identity,
            availability=UNCERTAINTY_INSUFFICIENT_PAIRS,
            unavailable_reason=UNAVAILABLE_INSUFFICIENT_PAIRS,
            point_estimate=point_estimate, paired_se=paired_se,
            unpaired_se=unpaired_se, se_ratio=se_ratio, ci_low=None,
            ci_high=None, valid_pairs=n, confidence_level=confidence_level,
            bootstrap_replicates=bootstrap_replicates, bootstrap_seed=seed,
            unpaired_semantics=unpaired_reason)

    ci_low, ci_high = _bootstrap_ci(
        values, replicates=bootstrap_replicates,
        confidence_level=confidence_level, seed=seed)
    return UncertaintyResult(
        metric=metric, substrate_identity=substrate_identity,
        subject_identity=subject_identity, availability=UNCERTAINTY_AVAILABLE,
        unavailable_reason=None, point_estimate=point_estimate,
        paired_se=paired_se, unpaired_se=unpaired_se, se_ratio=se_ratio,
        ci_low=ci_low, ci_high=ci_high, valid_pairs=n,
        confidence_level=confidence_level,
        bootstrap_replicates=bootstrap_replicates, bootstrap_seed=seed,
        unpaired_semantics=unpaired_reason)


def candidate_uncertainty(comparison, candidate_comparison, metric, *,
                          bootstrap_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
                          confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
                          bootstrap_seed_root: int = DEFAULT_BOOTSTRAP_SEED
                          ) -> UncertaintyResult:
    """Candidate-vs-baseline uncertainty over the S4 complete valid pair set."""
    return compute_uncertainty(
        comparison.baseline_outcomes,
        candidate_comparison.intervention_outcomes,
        metric=metric,
        substrate_identity=comparison_substrate_identity(comparison),
        subject_identity=candidate_comparison.candidate.identity(),
        bootstrap_replicates=bootstrap_replicates,
        confidence_level=confidence_level,
        bootstrap_seed_root=bootstrap_seed_root)


def pairwise_uncertainty(comparison, candidate_a, candidate_b, metric, *,
                         bootstrap_replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
                         confidence_level: float = DEFAULT_CONFIDENCE_LEVEL,
                         bootstrap_seed_root: int = DEFAULT_BOOTSTRAP_SEED
                         ) -> UncertaintyResult:
    """Direct candidate-A-vs-candidate-B uncertainty.

    Uses only indices where BOTH candidate trajectories are valid (baseline
    validity is not required). Positive point estimate = A improves over B.
    """
    return compute_uncertainty(
        candidate_b.intervention_outcomes,
        candidate_a.intervention_outcomes,
        metric=metric,
        substrate_identity=comparison_substrate_identity(comparison),
        subject_identity=(f"{candidate_a.candidate.identity()}"
                          f"|{candidate_b.candidate.identity()}"),
        bootstrap_replicates=bootstrap_replicates,
        confidence_level=confidence_level,
        bootstrap_seed_root=bootstrap_seed_root,
        include_unpaired=False)


def pairwise_validity_counts(candidate_a, candidate_b) -> dict:
    """Explicit A/B validity buckets over the aligned candidate index set."""
    both = a_only = b_only = neither = 0
    b_by_index = {outcome.simulation_index: outcome
                  for outcome in candidate_b.intervention_outcomes}
    for out_a in candidate_a.intervention_outcomes:
        out_b = b_by_index.get(out_a.simulation_index)
        if out_b is None:
            continue
        if out_a.valid and out_b.valid:
            both += 1
        elif out_a.valid:
            a_only += 1
        elif out_b.valid:
            b_only += 1
        else:
            neither += 1
    return {
        "both_valid": both,
        "a_only_valid": a_only,
        "b_only_valid": b_only,
        "both_invalid": neither,
    }
