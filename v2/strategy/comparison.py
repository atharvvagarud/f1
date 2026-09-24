"""Phase-7 S4 strategy comparison layer.

Given ONE exact ``SimulationState`` at T, ONE target driver and ONE simulation
configuration, S4 executes a single common baseline and evaluates each
statically valid candidate against it under the S3 paired / CRN substrate.

S4 deliberately does NOT:

- decide which strategy is best (no ranking, no objective, no hidden score);
- freeze or expose production uncertainty (no CI / SE / significance);
- touch the API or frontend;
- import or combine the Phase-3 winner model.

Probability values are ``MONTE_CARLO_FREQUENCY`` estimates from the frozen
Phase-6 simulator. Baseline and intervention futures are simulated; the
alternative-strategy outcomes are counterfactual estimates, never observed
ground truth.

Delta sign convention (canonical, ``delta_source = "complete_valid_pairs"``):

- ``delta_win_probability``    = mean over complete valid pairs of
  ``I(candidate wins) - I(baseline wins)``; positive = candidate improves the
  estimated win probability.
- ``delta_podium_probability`` = the same for podium; positive = improves.
- ``delta_expected_finish``    = mean over complete valid pairs of
  ``baseline_finish_position - candidate_finish_position``; positive = the
  candidate improves (lowers) the expected finishing position.

Dependency direction: ``v2.strategy`` -> ``v2.simulation``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

from v2.simulation.config import Assumptions, SimulationConfig
from v2.simulation.engine import ExecutionPolicy, SimulationUnsupportedError
from v2.simulation.monte_carlo import (
    DEFAULT_CHUNK_SIZE,
    REASON_STRATEGY_TARGET_DRIVER_NOT_IN_ROSTER,
)
from v2.simulation.results import PROBABILITY_SEMANTICS
from v2.simulation.state import canonical_sha256
from v2.strategy.candidates import (
    CANDIDATE_CONTRACT_VERSION,
    StrategyCandidate,
    generate_candidates,
)
from v2.strategy.contracts import (
    INTERVENTION_VERSION,
    STRATEGY_CONTRACT_VERSION,
)
from v2.strategy.paired import (
    PAIRED_CONTRACT_VERSION,
    BaselineArm,
    PairingDiagnostics,
    StrategyPairedResult,
    pair_arms,
    paired_differences,
    run_baseline,
    run_intervention_arm,
)

__all__ = [
    "COMPARISON_VERSION",
    "CRN_POLICY",
    "COUNTERFACTUAL_SEMANTICS",
    "DELTA_POLICY",
    "CandidateComparison",
    "CandidateExecutionSummary",
    "StrategyComparisonResult",
    "TargetAggregate",
    "compare_strategies",
]

#: Structural version of the S4 comparison contract. A bump is required if the
#: candidate-space semantics, the delta definitions, the valid-pair policy, the
#: status aggregation, the baseline semantics or the comparison estimand change.
COMPARISON_VERSION = "v1"

#: CRN is adopted from S3 WITH its documented limitations; S4 never claims CRN
#: universally reduces variance.
CRN_POLICY = "CRN_ADOPTED_WITH_LIMITATIONS"

#: Canonical comparison delta estimand: the mean over COMPLETE VALID pairs.
DELTA_POLICY = "complete_valid_pairs"

COUNTERFACTUAL_SEMANTICS = (
    "The historical state at T is factual. Baseline and intervention futures "
    "are simulated; alternative strategy outcomes are counterfactual estimates "
    "and not observed ground truth. No historical future is used.")

_LIMITATIONS = (
    "No traffic/overtaking model: ordering is free-air "
    "(laps DESC, race_time ASC, driver_id); position changes are free-air "
    "rejoin estimates with no rejoin battle.",
    "Phase-6 has no identified per-compound pace delta: an explicit compound "
    "changes only compound identity / stint grid / future transitions.",
    "CRN shares per-(seed, index) stream identities, not trajectories; after "
    "divergence event ordering may differ, so CRN is not a universal variance "
    "reduction claim.",
    "Counterfactual levels are not observable truth; S4 validates machinery, "
    "not realised intervention outcomes.",
    "STAY_OUT is frequently behaviourally inert; a near-zero delta is not "
    "proof of strategic equivalence when the intervention rarely activated.",
    "PIT_NOW can coincide with a baseline pit the driver was already due to "
    "make; pairing status cannot always separate an aligned replacement from a "
    "new forced stop.",
    "S4 itself defines no sampling uncertainty; S5 exposes an additive, "
    "explicitly sampling-only paired SE / bootstrap interval over this "
    "result. It is not parameter, traffic, compound-effect or real-world "
    "counterfactual uncertainty.",
)


@dataclass(frozen=True)
class TargetAggregate:
    """Target-driver aggregate block for one arm (``MONTE_CARLO_FREQUENCY``)."""

    valid_simulations: int
    invalid_simulations: int
    win_probability: float
    podium_probability: float
    expected_finish: float
    finish_position_distribution: tuple

    @classmethod
    def from_result(cls, result, driver_id: str) -> "TargetAggregate":
        summary = result.driver_summary_by_id[driver_id]
        distribution = tuple(
            (entry.position, entry.frequency)
            for entry in summary.finish_position_distribution)
        return cls(
            valid_simulations=result.valid_simulation_count,
            invalid_simulations=result.invalid_simulation_count,
            win_probability=summary.win_probability,
            podium_probability=summary.podium_probability,
            expected_finish=summary.expected_finish,
            finish_position_distribution=distribution,
        )

    def to_dict(self) -> dict:
        return {
            "valid_simulations": self.valid_simulations,
            "invalid_simulations": self.invalid_simulations,
            "win_probability": self.win_probability,
            "podium_probability": self.podium_probability,
            "expected_finish": self.expected_finish,
            "finish_position_distribution": [
                {"position": position, "frequency": frequency}
                for position, frequency in self.finish_position_distribution],
        }


@dataclass(frozen=True)
class CandidateExecutionSummary:
    """Descriptive intervention execution rates for one candidate (no score)."""

    total: int
    applied: int
    suppressed: int
    superseded: int
    inert: int
    race_end_cancelled: int
    baseline_pit_suppressed: int
    applied_rate: float
    suppressed_rate: float
    superseded_rate: float
    inert_rate: float
    race_end_cancelled_rate: float

    @classmethod
    def from_diagnostics(cls, diag: PairingDiagnostics
                         ) -> "CandidateExecutionSummary":
        total = diag.pairs_total
        baseline_pit_suppressed = diag.intervention_suppressed \
            - diag.intervention_inert

        def rate(count: int) -> float:
            return (count / total) if total else 0.0

        return cls(
            total=total,
            applied=diag.intervention_applied,
            suppressed=diag.intervention_suppressed,
            superseded=diag.intervention_superseded,
            inert=diag.intervention_inert,
            race_end_cancelled=diag.race_end_cancelled,
            baseline_pit_suppressed=baseline_pit_suppressed,
            applied_rate=rate(diag.intervention_applied),
            suppressed_rate=rate(diag.intervention_suppressed),
            superseded_rate=rate(diag.intervention_superseded),
            inert_rate=rate(diag.intervention_inert),
            race_end_cancelled_rate=rate(diag.race_end_cancelled),
        )

    def to_dict(self) -> dict:
        return {
            "total": self.total,
            "applied": self.applied,
            "suppressed": self.suppressed,
            "superseded": self.superseded,
            "inert": self.inert,
            "race_end_cancelled": self.race_end_cancelled,
            "baseline_pit_suppressed": self.baseline_pit_suppressed,
            "applied_rate": self.applied_rate,
            "suppressed_rate": self.suppressed_rate,
            "superseded_rate": self.superseded_rate,
            "inert_rate": self.inert_rate,
            "race_end_cancelled_rate": self.race_end_cancelled_rate,
        }


@dataclass(frozen=True)
class CandidateComparison:
    """One candidate's static validity, execution summary and paired deltas.

    ``evaluated`` is ``False`` when the candidate was statically invalid, or
    when the comparison itself was unsupported, so no intervention was run.
    ``aggregate`` / ``execution`` / deltas are ``None`` in those cases.
    """

    candidate: StrategyCandidate
    valid: bool
    reason: Optional[str]
    evaluated: bool
    aggregate: Optional[TargetAggregate]
    execution: Optional[CandidateExecutionSummary]
    delta_source: Optional[str]
    delta_win_probability: Optional[float]
    delta_podium_probability: Optional[float]
    delta_expected_finish: Optional[float]
    valid_pairs: int
    baseline_only_valid: int
    intervention_only_valid: int
    both_invalid: int
    validity_sets_match: bool
    paired_identity: Optional[str]
    #: S5 data-lifetime retention: the candidate arm's compact terminal
    #: per-index outcomes (already generated by S4). It is deliberately NOT
    #: serialized and NOT part of the S4 comparison identity, so S4 results are
    #: unchanged; S5 reads it to build paired sampling uncertainty without
    #: rerunning any simulation.
    intervention_outcomes: tuple = field(default=(), repr=False, compare=False)

    @classmethod
    def not_evaluated(cls, candidate: StrategyCandidate
                      ) -> "CandidateComparison":
        return cls(
            candidate=candidate, valid=candidate.valid, reason=candidate.reason,
            evaluated=False, aggregate=None, execution=None,
            delta_source=None, delta_win_probability=None,
            delta_podium_probability=None, delta_expected_finish=None,
            valid_pairs=0, baseline_only_valid=0, intervention_only_valid=0,
            both_invalid=0, validity_sets_match=True, paired_identity=None)

    @classmethod
    def from_pair(cls, candidate: StrategyCandidate,
                  paired: StrategyPairedResult) -> "CandidateComparison":
        diffs = paired_differences(paired)
        diag = paired.diagnostics
        return cls(
            candidate=candidate, valid=True, reason=None, evaluated=True,
            aggregate=TargetAggregate.from_result(
                paired.intervention_result, paired.target_driver_id),
            execution=CandidateExecutionSummary.from_diagnostics(diag),
            delta_source=DELTA_POLICY,
            delta_win_probability=diffs.mean_d_win,
            delta_podium_probability=diffs.mean_d_podium,
            delta_expected_finish=diffs.mean_d_finish,
            valid_pairs=diffs.valid_pairs,
            baseline_only_valid=diag.baseline_only_valid,
            intervention_only_valid=diag.intervention_only_valid,
            both_invalid=diag.both_invalid,
            validity_sets_match=(diag.baseline_only_valid == 0
                                 and diag.intervention_only_valid == 0),
            paired_identity=paired.identity(),
            intervention_outcomes=paired.intervention_outcomes,
        )

    def to_dict(self) -> dict:
        return {
            "candidate": self.candidate.to_dict(),
            "valid": self.valid,
            "reason": self.reason,
            "evaluated": self.evaluated,
            "aggregate": (self.aggregate.to_dict()
                          if self.aggregate is not None else None),
            "execution": (self.execution.to_dict()
                          if self.execution is not None else None),
            "delta_source": self.delta_source,
            "delta_win_probability": self.delta_win_probability,
            "delta_podium_probability": self.delta_podium_probability,
            "delta_expected_finish": self.delta_expected_finish,
            "valid_pairs": self.valid_pairs,
            "baseline_only_valid": self.baseline_only_valid,
            "intervention_only_valid": self.intervention_only_valid,
            "both_invalid": self.both_invalid,
            "validity_sets_match": self.validity_sets_match,
            "paired_identity": self.paired_identity,
        }


@dataclass(frozen=True)
class StrategyComparisonResult:
    """Immutable S4 comparison result (no ranking, no objective, no CI)."""

    state_identity: str
    parameter_identity: str
    config_identity: str
    master_seed: int
    simulation_count: int
    target_driver_id: str
    supported: bool
    unsupported_reason: Optional[str]
    baseline: Optional[TargetAggregate]
    candidates: tuple
    comparison_version: str = COMPARISON_VERSION
    strategy_contract_version: str = STRATEGY_CONTRACT_VERSION
    intervention_version: str = INTERVENTION_VERSION
    candidate_contract_version: str = CANDIDATE_CONTRACT_VERSION
    paired_contract_version: str = PAIRED_CONTRACT_VERSION
    pairing_policy: str = CRN_POLICY
    delta_policy: str = DELTA_POLICY
    probability_semantics: str = PROBABILITY_SEMANTICS
    counterfactual_semantics: str = COUNTERFACTUAL_SEMANTICS
    limitations: tuple = _LIMITATIONS
    #: S5 data-lifetime retention: the ONE shared baseline's compact terminal
    #: per-index outcomes. Not serialized and not part of the S4 comparison
    #: identity; S5 reads it alongside each candidate arm's outcomes.
    baseline_outcomes: tuple = field(default=(), repr=False, compare=False)

    def identity(self) -> str:
        return canonical_sha256({
            "comparison_version": self.comparison_version,
            "strategy_contract_version": self.strategy_contract_version,
            "intervention_version": self.intervention_version,
            "candidate_contract_version": self.candidate_contract_version,
            "paired_contract_version": self.paired_contract_version,
            "state_identity": self.state_identity,
            "parameter_identity": self.parameter_identity,
            "config_identity": self.config_identity,
            "master_seed": self.master_seed,
            "simulation_count": self.simulation_count,
            "target_driver_id": self.target_driver_id,
            "supported": self.supported,
            "unsupported_reason": self.unsupported_reason,
            "pairing_policy": self.pairing_policy,
            "delta_policy": self.delta_policy,
            "probability_semantics": self.probability_semantics,
            "candidates": [candidate.to_dict()
                           for candidate in self.candidates],
        })

    def to_dict(self) -> dict:
        return {
            "comparison_version": self.comparison_version,
            "strategy_contract_version": self.strategy_contract_version,
            "intervention_version": self.intervention_version,
            "candidate_contract_version": self.candidate_contract_version,
            "paired_contract_version": self.paired_contract_version,
            "comparison_identity": self.identity(),
            "state_identity": self.state_identity,
            "parameter_identity": self.parameter_identity,
            "config_identity": self.config_identity,
            "master_seed": self.master_seed,
            "simulation_count": self.simulation_count,
            "target_driver_id": self.target_driver_id,
            "supported": self.supported,
            "unsupported_reason": self.unsupported_reason,
            "pairing_policy": self.pairing_policy,
            "delta_policy": self.delta_policy,
            "probability_semantics": self.probability_semantics,
            "counterfactual_semantics": self.counterfactual_semantics,
            "limitations": list(self.limitations),
            "baseline": (self.baseline.to_dict()
                         if self.baseline is not None else None),
            "candidates": [candidate.to_dict()
                           for candidate in self.candidates],
        }


def _unsupported(*, state, parameters, config, target_driver_id, candidates,
                 reason) -> StrategyComparisonResult:
    return StrategyComparisonResult(
        state_identity=state.identity(),
        parameter_identity=parameters.parameter_identity().identity(),
        config_identity=config.identity(),
        master_seed=config.master_seed,
        simulation_count=config.simulation_count,
        target_driver_id=target_driver_id,
        supported=False,
        unsupported_reason=reason,
        baseline=None,
        candidates=tuple(CandidateComparison.not_evaluated(candidate)
                         for candidate in candidates),
    )


def compare_strategies(state, parameters, config: SimulationConfig,
                       assumptions: Assumptions, target_driver_id: str, *,
                       candidate_specs=None,
                       execution_policy: ExecutionPolicy = (
                           ExecutionPolicy.RETROSPECTIVE_PRODUCT),
                       zero_noise: bool = False,
                       chunk_size: int = DEFAULT_CHUNK_SIZE
                       ) -> StrategyComparisonResult:
    """Compare the canonical (or supplied) candidates against ONE baseline.

    The baseline is executed exactly once; every statically valid candidate is
    then run as a single intervention arm and paired against that shared
    baseline. Returns a structured unsupported result (never a fabricated one)
    when the factual state cannot be evolved or the target is not in the
    contemporaneous roster.
    """
    if not isinstance(config, SimulationConfig):
        raise TypeError(f"config must be a SimulationConfig, got {config!r}")
    if not isinstance(assumptions, Assumptions):
        raise TypeError(f"assumptions must be an Assumptions, got {assumptions!r}")

    candidates = generate_candidates(state, config, target_driver_id,
                                     specs=candidate_specs)

    if target_driver_id not in state.roster_driver_ids:
        return _unsupported(
            state=state, parameters=parameters, config=config,
            target_driver_id=target_driver_id, candidates=candidates,
            reason=REASON_STRATEGY_TARGET_DRIVER_NOT_IN_ROSTER)

    try:
        baseline: BaselineArm = run_baseline(
            state, parameters, config, assumptions, target_driver_id,
            execution_policy=execution_policy, zero_noise=zero_noise,
            chunk_size=chunk_size)
    except SimulationUnsupportedError as exc:
        return _unsupported(state=state, parameters=parameters, config=config,
                            target_driver_id=target_driver_id,
                            candidates=candidates, reason=exc.reason)

    comparisons = []
    for candidate in candidates:
        if not candidate.valid:
            comparisons.append(CandidateComparison.not_evaluated(candidate))
            continue
        arm = run_intervention_arm(
            state, parameters, config, assumptions, candidate.intervention,
            execution_policy=execution_policy, zero_noise=zero_noise,
            chunk_size=chunk_size)
        comparisons.append(CandidateComparison.from_pair(
            candidate, pair_arms(baseline, arm)))

    return StrategyComparisonResult(
        state_identity=baseline.state_identity,
        parameter_identity=baseline.parameter_identity,
        config_identity=baseline.config_identity,
        master_seed=baseline.master_seed,
        simulation_count=baseline.simulation_count,
        target_driver_id=target_driver_id,
        supported=True,
        unsupported_reason=None,
        baseline=TargetAggregate.from_result(baseline.result,
                                             target_driver_id),
        candidates=tuple(comparisons),
        baseline_outcomes=baseline.outcomes,
    )
