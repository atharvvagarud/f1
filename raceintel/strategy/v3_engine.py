"""V3.6C Strategy 2.0 paired MC2 engine (thin orchestration layer).

ORCHESTRATE + AGGREGATE + COMPARE only. This module builds no simulator,
duplicates no Phase-7 machinery, and rewrites no MC2:

- execution (reference once, one arm per valid candidate, CRN pairing,
  complete-pair accounting, execution diagnostics): Phase-7 S3/S4
  ``compare_strategies`` reused verbatim;
- WIN/PODIUM/EXPECTED_FINISH uncertainty: Phase-7 S5
  ``candidate_uncertainty`` reused verbatim;
- TOP5/TOP10/DOWNSIDE uncertainty: identical paired algorithm
  (proven bit-identical to S5 on shared metrics by test);
- widened arm aggregates over the complete-pair set (Part N choice,
  documented; S4 own-denom aggregates untouched);
- ``StrategyComparisonKey`` + 12-field provenance per alternative.

No API route, no frontend import, no serving registration, no V3.5
dependency (verified by test: no ``v3_5``/``outcome`` model import).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

import numpy as np

from raceintel.simulation.config import Assumptions, SimulationConfig
from raceintel.simulation.engine import ExecutionPolicy
from raceintel.simulation.state import canonical_sha256
from raceintel.strategy.candidates import (
    CANONICAL_CANDIDATE_SPECS,
    candidate_key,
)
from raceintel.strategy.comparison import (
    CandidateComparison,
    StrategyComparisonResult,
    compare_strategies,
)
from raceintel.strategy.contracts import StrategyAction
from raceintel.strategy.uncertainty import (
    DEFAULT_BOOTSTRAP_REPLICATES,
    DEFAULT_BOOTSTRAP_SEED,
    DEFAULT_CONFIDENCE_LEVEL,
    MIN_VALID_PAIRS_FOR_CI,
    UNCERTAINTY_AVAILABLE,
    UNCERTAINTY_INSUFFICIENT_PAIRS,
    UNCERTAINTY_NO_VALID_PAIRS,
    UNCERTAINTY_SEMANTICS,
    candidate_uncertainty,
    comparison_substrate_identity,
    derive_bootstrap_seed,
)
from raceintel.strategy.v3_contracts import (
    OUTCOME_SCHEMA_VERSION,
    PROVENANCE_FIELDS,
    REFERENCE_KIND,
    SIMULATOR_IDENTITY,
    TRADE_OFF_FIELDS,
    V3B_EXECUTION_CONTRACT_VERSION,
    StrategyComparisonKey,
    build_unsupported_result,
)

__all__ = [
    "V3_ENGINE_VERSION",
    "V3AlternativeResult",
    "V3ArmAggregate",
    "V3Delta",
    "V3StrategyResult",
    "compare_v3_strategies",
    "compare_v3_strategy",
]

#: Structural version of this thin engine layer.
V3_ENGINE_VERSION = "v3.6c-engine-v1"

#: User-facing interval label (frozen wording).
MC_INTERVAL_LABEL = "95% MC interval"

#: Extended paired metrics (beyond the three S5 canonical metrics).
V3_TOP5_METRIC = "TOP5_FREQUENCY"
V3_TOP10_METRIC = "TOP10_FREQUENCY"
V3_DOWNSIDE_METRIC = "DOWNSIDE_PROBABILITY"

#: S5 canonical metrics reused verbatim through candidate_uncertainty.
_S5_METRIC_FOR_DELTA = {
    "delta_win_frequency": "WIN_PROBABILITY",
    "delta_podium_frequency": "PODIUM_PROBABILITY",
    "delta_expected_finish": "EXPECTED_FINISH",
}

#: Leader rule per trade-off field: max point estimate wins in every field
#: because all deltas use the positive-improvement orientation (B, Part Y).
_LEADER_FIELDS = (
    "delta_win_frequency",
    "delta_podium_frequency",
    "delta_top5_frequency",
    "delta_top10_frequency",
    "delta_expected_finish",
)

#: Comparison-level zero-pair reason (B, Part L/Z).
NO_VALID_PAIRS = "NO_VALID_PAIRS"


def _require_nonneg_int(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(
            f"{name} must be a non-negative plain int, got {value!r}")
    return value


@dataclass(frozen=True)
class V3ArmAggregate:
    """Target-driver outcome aggregate over ONE complete-pair set."""

    valid_pairs: int
    win_frequency: float
    podium_frequency: float
    top5_frequency: float
    top10_frequency: float
    expected_finish: float
    median_finish: float
    finish_q25: float
    finish_q75: float
    finish_position_distribution: tuple
    roster_size: int

    def to_dict(self) -> dict:
        return {
            "valid_pairs": self.valid_pairs,
            "win_frequency": self.win_frequency,
            "podium_frequency": self.podium_frequency,
            "top5_frequency": self.top5_frequency,
            "top10_frequency": self.top10_frequency,
            "expected_finish": self.expected_finish,
            "median_finish": self.median_finish,
            "finish_q25": self.finish_q25,
            "finish_q75": self.finish_q75,
            "finish_position_distribution": [
                {"position": p, "frequency": f}
                for p, f in self.finish_position_distribution],
            "roster_size": self.roster_size,
        }


@dataclass(frozen=True)
class V3Delta:
    """One paired trade-off delta with MC sampling uncertainty."""

    metric: str
    point_estimate: Optional[float]
    paired_se: Optional[float]
    ci_low: Optional[float]
    ci_high: Optional[float]
    availability: str
    valid_pairs: int
    uncertainty_semantics: str = UNCERTAINTY_SEMANTICS
    interval_label: str = MC_INTERVAL_LABEL

    def to_dict(self) -> dict:
        return {
            "metric": self.metric,
            "point_estimate": self.point_estimate,
            "paired_se": self.paired_se,
            "ci_low": self.ci_low,
            "ci_high": self.ci_high,
            "availability": self.availability,
            "valid_pairs": self.valid_pairs,
            "uncertainty_semantics": self.uncertainty_semantics,
            "interval_label": self.interval_label,
        }


@dataclass(frozen=True)
class V3AlternativeResult:
    """One alternative's complete Strategy 2.0 comparison payload."""

    candidate_key: str
    candidate_identity: str
    action: str
    requested_compound: Optional[str]
    evaluated: bool
    reason: Optional[str]
    reference_aggregate: Optional[V3ArmAggregate]
    alternative_aggregate: Optional[V3ArmAggregate]
    deltas: tuple
    execution: Optional[dict]
    requested_pairs: int
    complete_pairs: int
    excluded_pairs: int
    comparison_key: Optional[StrategyComparisonKey] = field(
        default=None, compare=False)
    comparison_identity: Optional[str] = field(default=None, compare=False)

    def to_dict(self) -> dict:
        return {
            "candidate_key": self.candidate_key,
            "candidate_identity": self.candidate_identity,
            "action": self.action,
            "requested_compound": self.requested_compound,
            "evaluated": self.evaluated,
            "reason": self.reason,
            "reference_aggregate": (
                self.reference_aggregate.to_dict()
                if self.reference_aggregate is not None else None),
            "alternative_aggregate": (
                self.alternative_aggregate.to_dict()
                if self.alternative_aggregate is not None else None),
            "deltas": [d.to_dict() for d in self.deltas],
            "execution": self.execution,
            "requested_pairs": self.requested_pairs,
            "complete_pairs": self.complete_pairs,
            "excluded_pairs": self.excluded_pairs,
            "comparison_key": (
                self.comparison_key.to_dict()
                if self.comparison_key is not None else None),
            "comparison_identity": self.comparison_identity,
        }


@dataclass(frozen=True)
class V3StrategyResult:
    """Immutable Strategy 2.0 multi-action result (no ranking, no score)."""

    state_identity: str
    parameter_identity: str
    config_identity: str
    master_seed: int
    simulation_count: int
    target_driver_id: str
    supported: bool
    unsupported_reason: Optional[str]
    reference_kind: str = REFERENCE_KIND
    alternatives: tuple = ()
    leaders: dict = field(default_factory=dict)
    engine_version: str = V3_ENGINE_VERSION
    execution_contract_version: str = V3B_EXECUTION_CONTRACT_VERSION
    outcome_schema_version: str = OUTCOME_SCHEMA_VERSION
    provenance: dict = field(default_factory=dict)

    def identity(self) -> str:
        return canonical_sha256({
            "engine_version": self.engine_version,
            "execution_contract_version": self.execution_contract_version,
            "outcome_schema_version": self.outcome_schema_version,
            "state_identity": self.state_identity,
            "parameter_identity": self.parameter_identity,
            "config_identity": self.config_identity,
            "master_seed": self.master_seed,
            "simulation_count": self.simulation_count,
            "target_driver_id": self.target_driver_id,
            "supported": self.supported,
            "unsupported_reason": self.unsupported_reason,
            "alternatives": [a.to_dict() for a in self.alternatives],
            "leaders": self.leaders,
        })

    def to_dict(self) -> dict:
        payload = {
            "engine_version": self.engine_version,
            "execution_contract_version": self.execution_contract_version,
            "outcome_schema_version": self.outcome_schema_version,
            "strategy_identity": self.identity(),
            "state_identity": self.state_identity,
            "parameter_identity": self.parameter_identity,
            "config_identity": self.config_identity,
            "master_seed": self.master_seed,
            "simulation_count": self.simulation_count,
            "target_driver_id": self.target_driver_id,
            "supported": self.supported,
            "unsupported_reason": self.unsupported_reason,
            "reference_kind": self.reference_kind,
            "alternatives": [a.to_dict() for a in self.alternatives],
            "leaders": self.leaders,
            "provenance": self.provenance,
        }
        return payload


def _pair_positions(baseline_outcomes, intervention_outcomes):
    """Aligned (ref_pos, alt_pos) over complete valid pairs by index."""
    base_by_index = {o.simulation_index: o for o in baseline_outcomes}
    pairs = []
    for alt in intervention_outcomes:
        base = base_by_index.get(alt.simulation_index)
        if base is None or not (base.valid and alt.valid):
            continue
        pairs.append((int(base.target_finish_position),
                      int(alt.target_finish_position)))
    return pairs


def _aggregate_from_positions(positions, roster_size) -> V3ArmAggregate:
    """Pure arm aggregate over one complete-pair position vector."""
    n = len(positions)
    arr = np.asarray(positions, dtype="<f8")
    dist = []
    for position in sorted(set(int(p) for p in positions)):
        dist.append((position, float(sum(1 for p in positions if int(p) == position) / n)))
    return V3ArmAggregate(
        valid_pairs=n,
        win_frequency=float((arr == 1).sum() / n),
        podium_frequency=float((arr <= 3).sum() / n),
        top5_frequency=float((arr <= 5).sum() / n),
        top10_frequency=float((arr <= 10).sum() / n),
        expected_finish=float(arr.mean()),
        median_finish=float(np.quantile(arr, 0.5, method="linear")),
        finish_q25=float(np.quantile(arr, 0.25, method="linear")),
        finish_q75=float(np.quantile(arr, 0.75, method="linear")),
        finish_position_distribution=tuple(dist),
        roster_size=roster_size,
    )


def _paired_stats(values, *, seed: int,
                  replicates: int = DEFAULT_BOOTSTRAP_REPLICATES,
                  confidence_level: float = DEFAULT_CONFIDENCE_LEVEL):
    """Paired mean / SE / deterministic percentile bootstrap of a values vector.

    Algorithm-identical to S5 ``_bootstrap_ci`` + ``compute_uncertainty``
    scalar path (proven bit-identical by test on shared metrics).
    """
    n = len(values)
    if n == 0:
        return None, None, None, None, UNCERTAINTY_NO_VALID_PAIRS
    point = float(sum(values) / n)
    se = None
    if n >= 2:
        mean = point
        var = sum((v - mean) ** 2 for v in values) / (n - 1)
        se = float(var ** 0.5 / (n ** 0.5))
    if n < MIN_VALID_PAIRS_FOR_CI:
        return point, se, None, None, UNCERTAINTY_INSUFFICIENT_PAIRS
    arr = np.asarray(values, dtype="<f8")
    rng = np.random.default_rng(seed)
    means = np.empty(replicates, dtype="<f8")
    for replicate in range(replicates):
        means[replicate] = arr[rng.integers(0, n, size=n)].mean()
    alpha = (1.0 - confidence_level) / 2.0
    low = float(np.quantile(means, alpha, method="linear"))
    high = float(np.quantile(means, 1.0 - alpha, method="linear"))
    return point, se, low, high, UNCERTAINTY_AVAILABLE


def _extended_delta(metric: str, values, *, seed: int,
                    valid_pairs: int) -> V3Delta:
    point, se, low, high, availability = _paired_stats(values, seed=seed)
    return V3Delta(
        metric=metric, point_estimate=point, paired_se=se,
        ci_low=low, ci_high=high, availability=availability,
        valid_pairs=valid_pairs)


def _s5_delta(delta_name: str, s5_result) -> V3Delta:
    return V3Delta(
        metric=delta_name, point_estimate=s5_result.point_estimate,
        paired_se=s5_result.paired_se, ci_low=s5_result.ci_low,
        ci_high=s5_result.ci_high, availability=s5_result.availability,
        valid_pairs=s5_result.valid_pairs)


def _execution_summary(candidate: CandidateComparison) -> dict:
    execution = candidate.execution
    return {
        "total": execution.total,
        "applied": execution.applied,
        "suppressed": execution.suppressed,
        "superseded": execution.superseded,
        "inert": execution.inert,
        "race_end_cancelled": execution.race_end_cancelled,
        "baseline_pit_suppressed": execution.baseline_pit_suppressed,
        "applied_rate": execution.applied_rate,
        "suppressed_rate": execution.suppressed_rate,
        "superseded_rate": execution.superseded_rate,
        "inert_rate": execution.inert_rate,
        "race_end_cancelled_rate": execution.race_end_cancelled_rate,
    }


def _validate_specs(specs) -> None:
    """Fail closed on non-conforming public action specs (Part G)."""
    if specs is None:
        return
    items = list(specs)
    for item in items:
        if not isinstance(item, (tuple, list)) or len(item) != 2:
            raise ValueError(
                "candidate_specs must be (action, requested_compound) pairs, "
                f"got {item!r}")


def _not_evaluated_alt(candidate, requested: int) -> V3AlternativeResult:
    cand = candidate.candidate
    return V3AlternativeResult(
        candidate_key=candidate_key(cand.action, cand.requested_compound),
        candidate_identity=cand.identity(),
        action=cand.action,
        requested_compound=cand.requested_compound,
        evaluated=False, reason=candidate.reason,
        reference_aggregate=None, alternative_aggregate=None,
        deltas=(), execution=None,
        requested_pairs=requested, complete_pairs=0, excluded_pairs=0)


def _unsupported_v3(*, s4, target_driver_id: str,
                    reason: str) -> V3StrategyResult:
    void = build_unsupported_result(
        level="COMPARISON", reason_code=reason,
        human_reason=reason, state_identity=s4.state_identity,
        action_identity=None)
    return V3StrategyResult(
        state_identity=s4.state_identity,
        parameter_identity=s4.parameter_identity,
        config_identity=s4.config_identity,
        master_seed=s4.master_seed,
        simulation_count=s4.simulation_count,
        target_driver_id=target_driver_id,
        supported=False,
        unsupported_reason=reason,
        alternatives=tuple(
            _not_evaluated_alt(c, s4.simulation_count)
            for c in s4.candidates),
        provenance={
            "contract_version": V3B_EXECUTION_CONTRACT_VERSION,
            "comparison_identity": None,
            "racestate_identity": s4.state_identity,
            "mc2_identity": SIMULATOR_IDENTITY,
            "simulation_config_identity": s4.config_identity,
            "reference_identity": REFERENCE_KIND,
            "action_identity": None,
            "simulation_count": s4.simulation_count,
            "complete_pair_count": 0,
            "seed_family_identity": str(s4.master_seed),
            "outcome_schema_identity": OUTCOME_SCHEMA_VERSION,
            "eligibility_status": void,
        },
    )


def compare_v3_strategies(
        state, parameters, config: SimulationConfig,
        assumptions: Assumptions, target_driver_id: str, *,
        candidate_specs=None,
        execution_policy: ExecutionPolicy = (
            ExecutionPolicy.RETROSPECTIVE_PRODUCT),
        zero_noise: bool = False,
        chunk_size: Optional[int] = None) -> V3StrategyResult:
    """Strategy 2.0 paired comparison over the frozen 9-action contract.

    Executes Phase-7 S4 ``compare_strategies`` once (one shared reference,
    one arm per valid candidate, same seed family), then derives the widened
    V3 outcome vector, paired trade-off deltas, paired MC uncertainty and
    deterministic provenance. Pure orchestration: no simulator, model, API
    or frontend code paths are introduced.
    """
    if not isinstance(config, SimulationConfig):
        raise TypeError(f"config must be a SimulationConfig, got {config!r}")
    if not isinstance(assumptions, Assumptions):
        raise TypeError(
            f"assumptions must be an Assumptions, got {assumptions!r}")
    _validate_specs(candidate_specs)
    if not isinstance(target_driver_id, str) or not target_driver_id.strip():
        raise ValueError("target_driver_id must be a non-empty string")

    kwargs = {
        "execution_policy": execution_policy,
        "zero_noise": zero_noise,
    }
    if chunk_size is not None:
        kwargs["chunk_size"] = chunk_size
    s4: StrategyComparisonResult = compare_strategies(
        state, parameters, config, assumptions, target_driver_id,
        candidate_specs=candidate_specs, **kwargs)

    if not s4.supported:
        return _unsupported_v3(
            s4=s4, target_driver_id=target_driver_id,
            reason=s4.unsupported_reason or "UNKNOWN_STATE")
    ref_valid = sum(1 for o in s4.baseline_outcomes if o.valid)
    if ref_valid == 0:
        return _unsupported_v3(
            s4=s4, target_driver_id=target_driver_id,
            reason=NO_VALID_PAIRS)

    roster_size = len(state.roster_driver_ids)
    substrate = comparison_substrate_identity(s4)
    alternatives = []
    for comparison in s4.candidates:
        cand = comparison.candidate
        key = candidate_key(cand.action, cand.requested_compound)
        identity = cand.identity()
        if not comparison.evaluated:
            alternatives.append(V3AlternativeResult(
                candidate_key=key, candidate_identity=identity,
                action=cand.action,
                requested_compound=cand.requested_compound,
                evaluated=False, reason=comparison.reason,
                reference_aggregate=None, alternative_aggregate=None,
                deltas=(), execution=None,
                requested_pairs=config.simulation_count,
                complete_pairs=0, excluded_pairs=0))
            continue
        pairs = _pair_positions(
            s4.baseline_outcomes, comparison.intervention_outcomes)
        n = len(pairs)
        excluded = (comparison.baseline_only_valid
                    + comparison.intervention_only_valid
                    + comparison.both_invalid)
        if n == 0:
            alternatives.append(V3AlternativeResult(
                candidate_key=key, candidate_identity=identity,
                action=cand.action,
                requested_compound=cand.requested_compound,
                evaluated=False, reason=NO_VALID_PAIRS,
                reference_aggregate=None, alternative_aggregate=None,
                deltas=(), execution=_execution_summary(comparison),
                requested_pairs=config.simulation_count,
                complete_pairs=0, excluded_pairs=excluded))
            continue
        ref_pos = [p[0] for p in pairs]
        alt_pos = [p[1] for p in pairs]
        ref_agg = _aggregate_from_positions(ref_pos, roster_size)
        alt_agg = _aggregate_from_positions(alt_pos, roster_size)

        deltas = []
        for delta_name, s5_metric in _S5_METRIC_FOR_DELTA.items():
            s5 = candidate_uncertainty(s4, comparison, s5_metric)
            deltas.append(_s5_delta(delta_name, s5))
        d_top5 = [int(a <= 5) - int(r <= 5)
                  for r, a in zip(ref_pos, alt_pos)]
        d_top10 = [int(a <= 10) - int(r <= 10)
                   for r, a in zip(ref_pos, alt_pos)]
        d_down = [int(a > r) for r, a in zip(ref_pos, alt_pos)]
        for metric, values in ((V3_TOP5_METRIC, d_top5),
                               (V3_TOP10_METRIC, d_top10),
                               (V3_DOWNSIDE_METRIC, d_down)):
            seed = derive_bootstrap_seed(
                bootstrap_seed_root=DEFAULT_BOOTSTRAP_SEED,
                substrate_identity=substrate,
                subject_identity=identity, metric=metric)
            delta_name = {
                V3_TOP5_METRIC: "delta_top5_frequency",
                V3_TOP10_METRIC: "delta_top10_frequency",
                V3_DOWNSIDE_METRIC: "delta_downside_probability",
            }[metric]
            deltas.append(_extended_delta(
                delta_name, values, seed=seed, valid_pairs=n))

        order = {k: i for i, k in enumerate(TRADE_OFF_FIELDS)}
        deltas = tuple(sorted(deltas, key=lambda d: order[d.metric]))

        comp_key = StrategyComparisonKey(
            key_version="v3.6b-comparison-key-v1",
            race_id=state.race_id,
            decision_lap=state.driver_by_id[target_driver_id].lap_number,
            state_identity=s4.state_identity,
            target_driver_id=target_driver_id,
            reference_kind=REFERENCE_KIND,
            alternative_identity=identity,
            simulator_identity=SIMULATOR_IDENTITY,
            parameter_identity=s4.parameter_identity,
            simulation_count=config.simulation_count,
            master_seed=config.master_seed,
            outcome_schema_version=OUTCOME_SCHEMA_VERSION)
        alternatives.append(V3AlternativeResult(
            candidate_key=key, candidate_identity=identity,
            action=cand.action,
            requested_compound=cand.requested_compound,
            evaluated=True, reason=None,
            reference_aggregate=ref_agg, alternative_aggregate=alt_agg,
            deltas=deltas, execution=_execution_summary(comparison),
            requested_pairs=config.simulation_count,
            complete_pairs=n, excluded_pairs=excluded,
            comparison_key=comp_key,
            comparison_identity=comp_key.identity()))

    leaders = {}
    evaluated = [a for a in alternatives if a.evaluated]
    for fname in _LEADER_FIELDS:
        best = None
        for alt in evaluated:
            point = next(d.point_estimate for d in alt.deltas
                         if d.metric == fname)
            if best is None or point > best[1]:
                best = (alt.candidate_key, point)
        leaders["leader_for_" + fname.replace("delta_", "")] = (
            best[0] if best is not None else None)

    complete_total = sum(a.complete_pairs for a in evaluated)
    result = V3StrategyResult(
        state_identity=s4.state_identity,
        parameter_identity=s4.parameter_identity,
        config_identity=s4.config_identity,
        master_seed=s4.master_seed,
        simulation_count=s4.simulation_count,
        target_driver_id=target_driver_id,
        supported=True if evaluated else False,
        unsupported_reason=None if evaluated else NO_VALID_PAIRS,
        alternatives=tuple(alternatives),
        leaders=leaders,
        provenance={
            "contract_version": V3B_EXECUTION_CONTRACT_VERSION,
            "comparison_identity": None,  # per-alternative (see below)
            "racestate_identity": s4.state_identity,
            "mc2_identity": SIMULATOR_IDENTITY,
            "simulation_config_identity": s4.config_identity,
            "reference_identity": REFERENCE_KIND,
            "action_identity": [a.candidate_identity for a in alternatives
                                if a.evaluated],
            "simulation_count": s4.simulation_count,
            "complete_pair_count": complete_total,
            "seed_family_identity": str(s4.master_seed),
            "outcome_schema_identity": OUTCOME_SCHEMA_VERSION,
            "eligibility_status": {"supported": True},
        },
    )
    return result


def compare_v3_strategy(
        state, parameters, config: SimulationConfig,
        assumptions: Assumptions, target_driver_id: str, *,
        action, requested_compound=None,
        execution_policy: ExecutionPolicy = (
            ExecutionPolicy.RETROSPECTIVE_PRODUCT),
        zero_noise: bool = False,
        chunk_size: Optional[int] = None) -> V3StrategyResult:
    """Single-alternative convenience wrapper (one action vs reference)."""
    action_value = (action.value if isinstance(action, StrategyAction)
                    else action)
    return compare_v3_strategies(
        state, parameters, config, assumptions, target_driver_id,
        candidate_specs=[(action_value, requested_compound)],
        execution_policy=execution_policy, zero_noise=zero_noise,
        chunk_size=chunk_size)
