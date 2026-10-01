"""Phase-7 S3 paired Monte Carlo / common-random-numbers substrate.

This module owns the scientific pairing layer required to compare ONE frozen
Phase-6 baseline against ONE strategy intervention for the same simulation
identity. It deliberately contains **no** candidate generation, ranking,
objective, uncertainty policy, API or frontend.

What pairing means here (and does not)
--------------------------------------
``run_pair`` executes the baseline (``intervention=None``) and the intervention
through the *same* engine path with the *same* ``SimulationState``,
``SimulationParameterSet`` and ``SimulationConfig`` (including ``master_seed``
and ``simulation_count``). Simulation ``i`` in each arm therefore consumes the
same per-``(master_seed, simulation_index)`` RNG stream identities. That is
common random numbers at the *stream* level.

It does **not** mean the two arms share a trajectory: an intervention changes
race time, and therefore future event ordering, residual-to-event assignment,
pit sequences, event counts and finishing order. Paired identity is the shared
stochastic *environment*, never "the same future except the pit decision".

Per-index outcomes are collected from the SAME terminal batch state used for
aggregation (``MonteCarloEngine.run(..., collect_index_outcomes=True)``); no
second simulation path, no scalar replay of every trajectory, no full
trajectory history. Only the compact terminal classification per index is
retained.

Dependency direction: ``v2.strategy`` -> ``v2.simulation``. The simulation
package never imports ``v2.strategy``.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Optional, Sequence

import numpy as np

from raceintel.simulation.config import Assumptions, SimulationConfig
from raceintel.simulation.engine import ExecutionPolicy
from raceintel.simulation.monte_carlo import (
    DEFAULT_CHUNK_SIZE,
    INTERVENTION_APPLIED,
    INTERVENTION_RACE_END_CANCELLED,
    INTERVENTION_SUPERSEDED,
    INTERVENTION_SUPPRESSED,
    MonteCarloEngine,
)
from raceintel.simulation.results import MonteCarloResult
from raceintel.simulation.state import canonical_sha256
from raceintel.strategy.contracts import StrategyIntervention
from raceintel.strategy.interventions import (
    INTERVENTION_OUTCOME_STATUSES,
    parse_intervention_outcomes,
)

__all__ = [
    "PAIRED_CONTRACT_VERSION",
    "BaselineArm",
    "InterventionArm",
    "PairingDiagnostics",
    "PairedDifferences",
    "PerIndexOutcome",
    "StrategyPairedResult",
    "pair_arms",
    "paired_differences",
    "paired_result_identity",
    "run_baseline",
    "run_intervention_arm",
    "run_pair",
]

#: Structural version of the S3 pairing/CRN substrate.
PAIRED_CONTRACT_VERSION = "s3-paired-v1"


@dataclass(frozen=True)
class PerIndexOutcome:
    """Compact terminal outcome of one simulated trajectory.

    Only values genuinely available from the frozen simulation are retained.
    For an invalid trajectory every derived field is ``None``/empty: no
    imputation and no fabricated outcome. ``intervention_status`` /
    ``intervention_reason`` are ``None`` for the baseline arm.
    """

    simulation_index: int
    valid: bool
    winner_driver_id: Optional[str]
    finishing_order: tuple
    target_finish_position: Optional[int]
    target_won: Optional[bool]
    target_podium: Optional[bool]
    intervention_status: Optional[str]
    intervention_reason: Optional[str]

    def __post_init__(self) -> None:
        if type(self.simulation_index) is not int or self.simulation_index < 0:
            raise ValueError(
                "simulation_index must be a non-negative plain int, got "
                f"{self.simulation_index!r}")
        if type(self.valid) is not bool:
            raise ValueError(f"valid must be a bool, got {self.valid!r}")
        if self.intervention_status is not None \
                and self.intervention_status not in INTERVENTION_OUTCOME_STATUSES:
            raise ValueError(
                f"unknown intervention status {self.intervention_status!r}")

    def to_dict(self) -> dict:
        return {
            "simulation_index": self.simulation_index,
            "valid": self.valid,
            "winner_driver_id": self.winner_driver_id,
            "finishing_order": list(self.finishing_order),
            "target_finish_position": self.target_finish_position,
            "target_won": self.target_won,
            "target_podium": self.target_podium,
            "intervention_status": self.intervention_status,
            "intervention_reason": self.intervention_reason,
        }


@dataclass(frozen=True)
class PairingDiagnostics:
    """Pair validity accounting and intervention execution frequencies.

    Invalid simulations are never silently dropped or imputed: every index
    falls in exactly one validity bucket. ``intervention_inert`` counts
    STAY_OUT realizations that reached their decision event when the baseline
    would not have pitted (nothing was actually suppressed).
    """

    pairs_total: int
    pairs_both_valid: int
    baseline_only_valid: int
    intervention_only_valid: int
    both_invalid: int
    intervention_applied: int
    intervention_suppressed: int
    intervention_superseded: int
    intervention_inert: int
    race_end_cancelled: int

    def to_dict(self) -> dict:
        return {
            "pairs_total": self.pairs_total,
            "pairs_both_valid": self.pairs_both_valid,
            "baseline_only_valid": self.baseline_only_valid,
            "intervention_only_valid": self.intervention_only_valid,
            "both_invalid": self.both_invalid,
            "intervention_applied": self.intervention_applied,
            "intervention_suppressed": self.intervention_suppressed,
            "intervention_superseded": self.intervention_superseded,
            "intervention_inert": self.intervention_inert,
            "race_end_cancelled": self.race_end_cancelled,
        }


@dataclass(frozen=True)
class PairedDifferences:
    """Raw paired observations over COMPLETE VALID pairs only.

    Sign semantics (explicit):

    - ``d_win_i = I(intervention wins) - I(baseline wins)``: positive means
      the intervention improved the win outcome.
    - ``d_podium_i`` the same for podium.
    - ``d_finish_i = baseline_finish_position - intervention_finish_position``:
      positive means the intervention improved (lowered) the finishing
      position; negative means it worsened it.

    These are raw observations, not a recommendation and not a frozen
    uncertainty contract.
    """

    indices: tuple
    d_win: tuple
    d_podium: tuple
    d_finish: tuple
    valid_pairs: int
    mean_d_win: float
    mean_d_podium: float
    mean_d_finish: float
    var_d_win: float
    var_d_podium: float
    var_d_finish: float

    def to_dict(self) -> dict:
        return {
            "valid_pairs": self.valid_pairs,
            "mean_d_win": self.mean_d_win,
            "mean_d_podium": self.mean_d_podium,
            "mean_d_finish": self.mean_d_finish,
            "var_d_win": self.var_d_win,
            "var_d_podium": self.var_d_podium,
            "var_d_finish": self.var_d_finish,
        }


@dataclass(frozen=True)
class StrategyPairedResult:
    """Immutable result of one paired baseline/intervention run.

    Stable scientific identity (see ``identity``); no timestamps, no runtime
    and no unordered dictionaries.
    """

    state_identity: str
    parameter_identity: str
    config_identity: str
    master_seed: int
    simulation_count: int
    target_driver_id: str
    intervention_identity: str
    strategy_contract_version: str
    intervention_version: str
    baseline_result: MonteCarloResult
    intervention_result: MonteCarloResult
    baseline_outcomes: tuple
    intervention_outcomes: tuple
    diagnostics: PairingDiagnostics
    baseline_outcome_digest: str
    intervention_outcome_digest: str
    paired_contract_version: str = PAIRED_CONTRACT_VERSION

    def identity(self) -> str:
        return paired_result_identity(
            paired_contract_version=self.paired_contract_version,
            state_identity=self.state_identity,
            parameter_identity=self.parameter_identity,
            config_identity=self.config_identity,
            master_seed=self.master_seed,
            simulation_count=self.simulation_count,
            target_driver_id=self.target_driver_id,
            strategy_contract_version=self.strategy_contract_version,
            intervention_version=self.intervention_version,
            intervention_identity=self.intervention_identity,
            baseline_result_identity=self.baseline_result.identity(),
            intervention_result_identity=self.intervention_result.identity(),
            baseline_outcome_digest=self.baseline_outcome_digest,
            intervention_outcome_digest=self.intervention_outcome_digest,
            diagnostics=self.diagnostics.to_dict())

    def to_dict(self) -> dict:
        return {
            "paired_contract_version": self.paired_contract_version,
            "strategy_contract_version": self.strategy_contract_version,
            "intervention_version": self.intervention_version,
            "state_identity": self.state_identity,
            "parameter_identity": self.parameter_identity,
            "config_identity": self.config_identity,
            "master_seed": self.master_seed,
            "simulation_count": self.simulation_count,
            "target_driver_id": self.target_driver_id,
            "intervention_identity": self.intervention_identity,
            "pairing_identity": self.identity(),
            "baseline_result": self.baseline_result.to_dict(),
            "intervention_result": self.intervention_result.to_dict(),
            "baseline_outcomes": [o.to_dict() for o in self.baseline_outcomes],
            "intervention_outcomes": [o.to_dict()
                                      for o in self.intervention_outcomes],
            "diagnostics": self.diagnostics.to_dict(),
        }


def paired_result_identity(*, paired_contract_version, state_identity,
                           parameter_identity, config_identity, master_seed,
                           simulation_count, target_driver_id,
                           strategy_contract_version, intervention_version,
                           intervention_identity, baseline_result_identity,
                           intervention_result_identity,
                           baseline_outcome_digest,
                           intervention_outcome_digest, diagnostics) -> str:
    """Deterministic, strategy-owned identity of a paired run.

    Composes the scientific inputs (state/parameter/config/seed/index
    identities, intervention identity) with the stable arm identities and the
    per-index outcome digests. Contains no runtime, timestamp or unordered
    container.
    """
    return canonical_sha256({
        "paired_contract_version": paired_contract_version,
        "strategy_contract_version": strategy_contract_version,
        "intervention_version": intervention_version,
        "state_identity": state_identity,
        "parameter_identity": parameter_identity,
        "config_identity": config_identity,
        "master_seed": master_seed,
        "simulation_count": simulation_count,
        "target_driver_id": target_driver_id,
        "intervention_identity": intervention_identity,
        "baseline_result_identity": baseline_result_identity,
        "intervention_result_identity": intervention_result_identity,
        "baseline_outcome_digest": baseline_outcome_digest,
        "intervention_outcome_digest": intervention_outcome_digest,
        "diagnostics": diagnostics,
    })


def _raw_outcome_digest(raw: dict) -> str:
    """Stable digest of the compact terminal per-index arrays.

    Uses explicit little-endian int64 bytes so the digest is portable, plus
    the invalid-reason sequence. Fast (C-level) and independent of the
    in-memory numpy dtype/byte order.
    """
    digest = hashlib.sha256()
    digest.update(np.asarray(raw["finish_position"],
                             dtype="<i8").tobytes())
    digest.update(np.asarray(raw["valid"], dtype="<i1").tobytes())
    digest.update("\n".join(str(reason)
                            for reason in raw["invalid_reason"]).encode("utf-8"))
    return digest.hexdigest()


def _build_outcomes(raw: dict, roster: tuple, target_index: int,
                    iv_outcomes: Optional[Sequence]) -> tuple:
    """Project compact raw arrays into immutable per-index outcomes."""
    positions = np.asarray(raw["finish_position"], dtype=np.int64)
    valid = np.asarray(raw["valid"], dtype=bool)
    count = positions.shape[0]
    field_size = positions.shape[1]
    big = field_size + 1

    masked = np.where(valid[:, None], positions, big)
    winner_columns = np.argmin(masked, axis=1)
    order_columns = np.argsort(masked, axis=1)
    target_positions = positions[:, target_index]

    outcomes = []
    for index in range(count):
        if bool(valid[index]):
            order = tuple(roster[int(column)]
                          for column in order_columns[index])
            winner = roster[int(winner_columns[index])]
            target_finish: Optional[int] = int(target_positions[index])
            won: Optional[bool] = target_finish == 1
            podium: Optional[bool] = target_finish is not None \
                and target_finish <= 3
            status = None
            reason = None
            if iv_outcomes is not None:
                status = iv_outcomes[index].status
                reason = iv_outcomes[index].reason
        else:
            order = ()
            winner = None
            target_finish = None
            won = None
            podium = None
            status = (iv_outcomes[index].status
                      if iv_outcomes is not None else None)
            reason = (iv_outcomes[index].reason
                      if iv_outcomes is not None else None)
        outcomes.append(PerIndexOutcome(
            simulation_index=index,
            valid=bool(valid[index]),
            winner_driver_id=winner,
            finishing_order=order,
            target_finish_position=target_finish,
            target_won=won,
            target_podium=podium,
            intervention_status=status,
            intervention_reason=reason,
        ))
    return tuple(outcomes)


def _pairing_diagnostics(baseline: tuple, intervention: tuple
                         ) -> PairingDiagnostics:
    both = base_only = iv_only = neither = 0
    applied = suppressed = superseded = inert = cancelled = 0
    for base, iv in zip(baseline, intervention):
        if base.valid and iv.valid:
            both += 1
        elif base.valid:
            base_only += 1
        elif iv.valid:
            iv_only += 1
        else:
            neither += 1
        if iv.intervention_status == INTERVENTION_APPLIED:
            applied += 1
        elif iv.intervention_status == INTERVENTION_SUPPRESSED:
            suppressed += 1
            if iv.intervention_reason is None:
                inert += 1
        elif iv.intervention_status == INTERVENTION_SUPERSEDED:
            superseded += 1
        elif iv.intervention_status == INTERVENTION_RACE_END_CANCELLED:
            cancelled += 1
    return PairingDiagnostics(
        pairs_total=len(baseline),
        pairs_both_valid=both,
        baseline_only_valid=base_only,
        intervention_only_valid=iv_only,
        both_invalid=neither,
        intervention_applied=applied,
        intervention_suppressed=suppressed,
        intervention_superseded=superseded,
        intervention_inert=inert,
        race_end_cancelled=cancelled,
    )


def paired_differences(result: StrategyPairedResult) -> PairedDifferences:
    """Raw paired differences over COMPLETE VALID pairs.

    ``d_finish`` is oriented so positive = intervention improved (lowered)
    finishing position. Returns empty tuples and zero statistics when there is
    no complete valid pair (never a fabricated value).
    """
    indices = []
    d_win = []
    d_podium = []
    d_finish = []
    for base, iv in zip(result.baseline_outcomes,
                        result.intervention_outcomes):
        if not (base.valid and iv.valid):
            continue
        indices.append(base.simulation_index)
        d_win.append(int(iv.target_won) - int(base.target_won))
        d_podium.append(int(iv.target_podium) - int(base.target_podium))
        d_finish.append(int(base.target_finish_position)
                        - int(iv.target_finish_position))

    def stats(values):
        if not values:
            return 0.0, 0.0
        mean = sum(values) / len(values)
        if len(values) < 2:
            return float(mean), 0.0
        var = sum((value - mean) ** 2 for value in values) / (len(values) - 1)
        return float(mean), float(var)

    mean_win, var_win = stats(d_win)
    mean_podium, var_podium = stats(d_podium)
    mean_finish, var_finish = stats(d_finish)
    return PairedDifferences(
        indices=tuple(indices),
        d_win=tuple(d_win),
        d_podium=tuple(d_podium),
        d_finish=tuple(d_finish),
        valid_pairs=len(indices),
        mean_d_win=mean_win,
        mean_d_podium=mean_podium,
        mean_d_finish=mean_finish,
        var_d_win=var_win,
        var_d_podium=var_podium,
        var_d_finish=var_finish,
    )


@dataclass(frozen=True)
class BaselineArm:
    """Reusable baseline arm: one executed baseline and its per-index outcomes.

    S4 computes the baseline ONCE for a whole comparison and pairs every
    candidate against this same arm. Every field is a pure function of
    ``(state, parameters, config, assumptions, target_driver_id)``; the arm
    carries no engine, no RNG and no mutable container, so reuse against many
    candidates cannot perturb the baseline.
    """

    state_identity: str
    parameter_identity: str
    config_identity: str
    master_seed: int
    simulation_count: int
    target_driver_id: str
    result: MonteCarloResult
    outcomes: tuple
    outcome_digest: str

    def __post_init__(self) -> None:
        if self.target_driver_id not in self.result.driver_summary_by_id:
            raise ValueError(
                f"baseline target {self.target_driver_id!r} is not in the "
                "baseline result roster")


@dataclass(frozen=True)
class InterventionArm:
    """One executed intervention arm and its per-index outcomes."""

    target_driver_id: str
    target_index: int
    strategy_contract_version: str
    intervention_version: str
    intervention_identity: str
    result: MonteCarloResult
    outcomes: tuple
    outcome_digest: str
    execution_outcomes: tuple


def run_baseline(state, parameters, config: SimulationConfig,
                 assumptions: Assumptions, target_driver_id: str, *,
                 execution_policy: ExecutionPolicy = (
                     ExecutionPolicy.RETROSPECTIVE_PRODUCT),
                 zero_noise: bool = False,
                 chunk_size: int = DEFAULT_CHUNK_SIZE) -> BaselineArm:
    """Execute the frozen Phase-6 baseline ONCE for ``target_driver_id``.

    Collects compact per-index terminal outcomes for the target driver so S4
    can pair many interventions against this single arm. The baseline is the
    ordinary Phase-6 path (``intervention=None``); no draw, seed or aggregation
    semantics change.
    """
    if not isinstance(config, SimulationConfig):
        raise TypeError(f"config must be a SimulationConfig, got {config!r}")
    if not isinstance(assumptions, Assumptions):
        raise TypeError(f"assumptions must be an Assumptions, got {assumptions!r}")
    roster = state.roster_driver_ids
    if target_driver_id not in roster:
        raise ValueError(
            f"target driver {target_driver_id!r} is not in the state roster "
            f"{list(roster)}")
    target_index = roster.index(target_driver_id)

    engine = MonteCarloEngine(chunk_size=chunk_size)
    result = engine.run(
        state, parameters, config, assumptions,
        execution_policy=execution_policy, zero_noise=zero_noise,
        collect_index_outcomes=True)
    raw = engine.last_index_outcomes
    outcomes = _build_outcomes(raw, roster, target_index, None)
    return BaselineArm(
        state_identity=state.identity(),
        parameter_identity=parameters.parameter_identity().identity(),
        config_identity=config.identity(),
        master_seed=config.master_seed,
        simulation_count=config.simulation_count,
        target_driver_id=target_driver_id,
        result=result,
        outcomes=outcomes,
        outcome_digest=_raw_outcome_digest(raw),
    )


def run_intervention_arm(state, parameters, config: SimulationConfig,
                         assumptions: Assumptions,
                         intervention: StrategyIntervention, *,
                         execution_policy: ExecutionPolicy = (
                             ExecutionPolicy.RETROSPECTIVE_PRODUCT),
                         zero_noise: bool = False,
                         chunk_size: int = DEFAULT_CHUNK_SIZE
                         ) -> InterventionArm:
    """Execute ONE strategy intervention arm under the shared simulation identity.

    The engine validates the intervention against ``state`` (raising the
    structured ``StrategyInterventionError`` before any draw) and collects the
    same compact per-index outcomes the baseline arm collects.
    """
    if not isinstance(config, SimulationConfig):
        raise TypeError(f"config must be a SimulationConfig, got {config!r}")
    if not isinstance(assumptions, Assumptions):
        raise TypeError(f"assumptions must be an Assumptions, got {assumptions!r}")
    if not isinstance(intervention, StrategyIntervention):
        raise TypeError(
            "intervention must be a StrategyIntervention, got "
            f"{intervention!r}")

    engine = MonteCarloEngine(chunk_size=chunk_size)
    result = engine.run(
        state, parameters, config, assumptions,
        execution_policy=execution_policy, zero_noise=zero_noise,
        collect_index_outcomes=True, intervention=intervention)
    raw = engine.last_index_outcomes
    iv_outcomes = parse_intervention_outcomes(
        engine.last_intervention_outcome)

    roster = state.roster_driver_ids
    target_index = roster.index(intervention.target_driver_id)
    outcomes = _build_outcomes(raw, roster, target_index, iv_outcomes)
    return InterventionArm(
        target_driver_id=intervention.target_driver_id,
        target_index=target_index,
        strategy_contract_version=intervention.strategy_contract_version,
        intervention_version=intervention.intervention_version,
        intervention_identity=intervention.identity(),
        result=result,
        outcomes=outcomes,
        outcome_digest=_raw_outcome_digest(raw),
        execution_outcomes=iv_outcomes,
    )


def pair_arms(baseline: BaselineArm, intervention_arm: InterventionArm
              ) -> StrategyPairedResult:
    """Pair a reusable baseline arm with one intervention arm.

    Scientifically identical to the arm construction inside ``run_pair``:
    the same baseline / intervention aggregates, the same per-index outcomes,
    the same diagnostics and the same paired identity.
    """
    if baseline.target_driver_id != intervention_arm.target_driver_id:
        raise ValueError(
            "baseline and intervention arms must target the same driver, got "
            f"{baseline.target_driver_id!r} and "
            f"{intervention_arm.target_driver_id!r}")
    diagnostics = _pairing_diagnostics(baseline.outcomes,
                                       intervention_arm.outcomes)
    return StrategyPairedResult(
        state_identity=baseline.state_identity,
        parameter_identity=baseline.parameter_identity,
        config_identity=baseline.config_identity,
        master_seed=baseline.master_seed,
        simulation_count=baseline.simulation_count,
        target_driver_id=baseline.target_driver_id,
        intervention_identity=intervention_arm.intervention_identity,
        strategy_contract_version=(
            intervention_arm.strategy_contract_version),
        intervention_version=intervention_arm.intervention_version,
        baseline_result=baseline.result,
        intervention_result=intervention_arm.result,
        baseline_outcomes=baseline.outcomes,
        intervention_outcomes=intervention_arm.outcomes,
        diagnostics=diagnostics,
        baseline_outcome_digest=baseline.outcome_digest,
        intervention_outcome_digest=intervention_arm.outcome_digest,
    )


def run_pair(state, parameters, config: SimulationConfig,
             assumptions: Assumptions, intervention: StrategyIntervention, *,
             execution_policy: ExecutionPolicy = (
                 ExecutionPolicy.RETROSPECTIVE_PRODUCT),
             zero_noise: bool = False,
             chunk_size: int = DEFAULT_CHUNK_SIZE) -> StrategyPairedResult:
    """Run ONE baseline and ONE intervention under shared simulation identities.

    The only intentional scientific difference between the two arms is the
    supplied ``StrategyIntervention``. Both arms collect compact per-index
    terminal outcomes from their own executed batch trajectories. S4 baseline
    reuse factors this into ``run_baseline`` + ``run_intervention_arm`` +
    ``pair_arms`` without changing any result or identity.
    """
    if not isinstance(config, SimulationConfig):
        raise TypeError(f"config must be a SimulationConfig, got {config!r}")
    if not isinstance(assumptions, Assumptions):
        raise TypeError(f"assumptions must be an Assumptions, got {assumptions!r}")
    if not isinstance(intervention, StrategyIntervention):
        raise TypeError(
            "intervention must be a StrategyIntervention, got "
            f"{intervention!r}")

    # The intervention arm is materialised first so an invalid intervention is
    # rejected with the structured StrategyInterventionError before any
    # baseline work, exactly as the S2/S3 contract promises. Both arms are
    # independent per-(seed, index) streams, so arm order cannot change either.
    intervention_arm = run_intervention_arm(
        state, parameters, config, assumptions, intervention,
        execution_policy=execution_policy, zero_noise=zero_noise,
        chunk_size=chunk_size)
    baseline = run_baseline(
        state, parameters, config, assumptions, intervention.target_driver_id,
        execution_policy=execution_policy, zero_noise=zero_noise,
        chunk_size=chunk_size)
    return pair_arms(baseline, intervention_arm)
