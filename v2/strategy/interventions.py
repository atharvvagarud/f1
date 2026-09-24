"""Phase-7 S2 strategy intervention runtime (strategy-owned layer).

The deterministic intervention mechanics live in the frozen simulator at its
neutral boundary (``v2.simulation.monte_carlo``): the action resolution rule,
the forced/suppressed pit application, and the per-simulation execution status.
This module owns the strategy-facing projection of that runtime:

- ``InterventionOutcome``: an immutable, canonically serializable view of what
  actually happened to one simulated trajectory's intervention;
- ``intervention_result_identity``: a strategy-layer identity (baseline state /
  parameter / config / intervention / MonteCarloResult), deliberately separate
  from the frozen Phase-6 ``MonteCarloResult`` identity;
- ``run_intervention``: a thin, validated convenience wrapper that routes the
  typed intervention through the engine and parses the runtime metadata.

Dependency direction: this module depends on ``v2.simulation``; the simulation
package never imports ``v2.strategy``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from v2.simulation.monte_carlo import (
    INTERVENTION_APPLIED,
    INTERVENTION_PENDING,
    INTERVENTION_RACE_END_CANCELLED,
    INTERVENTION_SUPERSEDED,
    INTERVENTION_SUPPRESSED,
    STRATEGY_ACTIONS,
    STRATEGY_INTERVENTION_REASONS,
    MonteCarloEngine,
    StrategyInterventionError,
)
from v2.simulation.state import canonical_sha256
from v2.strategy.contracts import StrategyIntervention

__all__ = [
    "INTERVENTION_OUTCOME_STATUSES",
    "STRATEGY_INTERVENTION_REASONS",
    "InterventionOutcome",
    "StrategyInterventionError",
    "intervention_result_identity",
    "parse_intervention_outcomes",
    "run_intervention",
]

#: Every status a per-simulation intervention can finish in.
INTERVENTION_OUTCOME_STATUSES = (
    INTERVENTION_PENDING,
    INTERVENTION_APPLIED,
    INTERVENTION_SUPPRESSED,
    INTERVENTION_SUPERSEDED,
    INTERVENTION_RACE_END_CANCELLED,
)


@dataclass(frozen=True)
class InterventionOutcome:
    """What actually happened to one simulated intervention.

    ``status`` is one of ``INTERVENTION_OUTCOME_STATUSES`` and ``reason`` is a
    structured reason (e.g. ``forced_pit``, ``baseline_pit_suppressed``,
    ``intervention_superseded_by_baseline_pit``, ``race_end_suppressed``).
    This is execution metadata, not a scientific result and never part of a
    frozen Phase-6 result identity.
    """

    action: str
    target_driver_id: str
    decision_lap: int
    requested_compound: Optional[str]
    status: str
    reason: Optional[str]
    applied_lap: Optional[int]
    compound_used: Optional[str]
    baseline_pit_suppressed: bool

    def __post_init__(self) -> None:
        if self.action not in STRATEGY_ACTIONS:
            raise ValueError(f"unknown intervention action {self.action!r}")
        if self.status not in INTERVENTION_OUTCOME_STATUSES:
            raise ValueError(f"unknown intervention status {self.status!r}")

    @property
    def executed(self) -> bool:
        """True when the intervention changed simulated behaviour."""
        return self.status in (INTERVENTION_APPLIED, INTERVENTION_SUPPRESSED)

    @classmethod
    def from_dict(cls, payload: dict) -> "InterventionOutcome":
        if not isinstance(payload, dict):
            raise ValueError(f"outcome payload must be a mapping, got {payload!r}")
        return cls(
            action=payload["action"],
            target_driver_id=payload["target_driver_id"],
            decision_lap=payload["decision_lap"],
            requested_compound=payload["requested_compound"],
            status=payload["status"],
            reason=payload["reason"],
            applied_lap=payload["applied_lap"],
            compound_used=payload["compound_used"],
            baseline_pit_suppressed=payload["baseline_pit_suppressed"],
        )

    def to_dict(self) -> dict:
        return {
            "action": self.action,
            "target_driver_id": self.target_driver_id,
            "decision_lap": self.decision_lap,
            "requested_compound": self.requested_compound,
            "status": self.status,
            "reason": self.reason,
            "applied_lap": self.applied_lap,
            "compound_used": self.compound_used,
            "baseline_pit_suppressed": self.baseline_pit_suppressed,
        }


def parse_intervention_outcomes(raw) -> Optional[tuple]:
    """Wrap the engine's per-simulation runtime metadata as typed outcomes.

    ``None`` (no intervention supplied) stays ``None``.
    """
    if raw is None:
        return None
    return tuple(InterventionOutcome.from_dict(entry) for entry in raw)


def intervention_result_identity(*, state, parameters, config, intervention,
                                 result, outcomes) -> str:
    """Deterministic strategy-layer identity of one intervention run.

    Explicitly separate from the frozen Phase-6 ``MonteCarloResult`` identity:
    it composes the baseline state / parameter / config identities, the
    user-assumption intervention identity, the frozen result identity, and the
    per-simulation execution outcome. S3 may refine paired-run identity; this
    is a stable S2 definition.
    """
    if outcomes is None:
        outcome_payload = None
    else:
        outcome_payload = [outcome.to_dict() for outcome in outcomes]
    return canonical_sha256({
        "strategy_contract_version": intervention.strategy_contract_version,
        "intervention_version": intervention.intervention_version,
        "state_identity": state.identity(),
        "parameter_identity": parameters.parameter_identity().identity(),
        "config_identity": config.identity(),
        "intervention_identity": intervention.identity(),
        "simulation_request_identity": result.simulation_request_identity,
        "result_identity": result.identity(),
        "intervention_outcomes": outcome_payload,
    })


def run_intervention(engine: MonteCarloEngine, initial_state, parameters,
                     config, assumptions, intervention: StrategyIntervention,
                     *, parse: bool = True, **kwargs):
    """Run one selected trajectory with ``intervention`` applied.

    Returns ``(result, outcomes)`` where ``outcomes`` is the tuple of
    per-simulation ``InterventionOutcome`` (or raw dicts when ``parse=False``).
    The engine validates the intervention against ``initial_state`` and raises
    the structured ``StrategyInterventionError`` before any RNG draw.
    """
    result = engine.run(initial_state, parameters, config, assumptions,
                        intervention=intervention, **kwargs)
    raw: Optional[Sequence[dict]] = engine.last_intervention_outcome
    outcomes = parse_intervention_outcomes(raw) if parse else raw
    return result, outcomes
