"""Phase-7 S4 strategy candidate generation (factual, T-only).

The conceptual v1 candidate space is at most nine single-decision
interventions anchored at the target driver's factual lap at T:

    STAY_OUT
    PIT_NOW        x {sampled, SOFT, MEDIUM, HARD}
    PIT_NEXT_LAP   x {sampled, SOFT, MEDIUM, HARD}

``sampled`` (``requested_compound=None``) isolates the pit-timing effect;
an explicit compound changes only compound identity / stint grid / future
transitions. Phase-6 has no identified per-compound pace delta, so no
candidate here claims "SOFT is faster" or "HARD is slower".

Candidate generation depends ONLY on the factual state at T, the frozen
simulation config and the strategy contract. It never inspects the actual
future race, a final result or oracle material.

Static (pre-run) validity reuses the canonical simulator validator
(``v2.simulation.monte_carlo._resolve_intervention``); this module does not
re-implement eligibility. A valid candidate is guaranteed to be accepted by
the engine before any draw. An invalid candidate is reported with a stable
structured reason and never simulated.

Dependency direction: ``v2.strategy`` -> ``v2.simulation``; the simulation
package never imports ``v2.strategy``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable, Optional

from raceintel.simulation.monte_carlo import (
    REASON_STRATEGY_MALFORMED,
    REASON_STRATEGY_UNSUPPORTED_ACTION,
    REASON_STRATEGY_UNSUPPORTED_COMPOUND,
    STRATEGY_INTERVENTION_REASONS,
    StrategyInterventionError,
    _resolve_intervention,
)
from raceintel.simulation.state import canonical_sha256
from raceintel.strategy.contracts import (
    SUPPORTED_REQUESTED_COMPOUNDS,
    StrategyAction,
    StrategyContractError,
    StrategyIntervention,
    strategy_action_value,
)

__all__ = [
    "CANDIDATE_CONTRACT_VERSION",
    "CANDIDATE_INVALIDITY_REASONS",
    "CANONICAL_CANDIDATE_SPECS",
    "StrategyCandidate",
    "build_candidate",
    "candidate_identity",
    "candidate_key",
    "generate_candidates",
]

#: Structural version of the S4 candidate space / validity projection.
CANDIDATE_CONTRACT_VERSION = "s4-candidates-v1"

#: Stable reasons an S4 candidate can be statically invalid. These are exactly
#: the canonical S2 simulator rejection reasons (no invented vocabulary).
CANDIDATE_INVALIDITY_REASONS = STRATEGY_INTERVENTION_REASONS

#: Canonical candidate space and the canonical action ordering. Identity and
#: comparison results are normalised to this order, so caller order can never
#: change a scientific result. This order MUST NOT be read as a ranking.
CANONICAL_CANDIDATE_SPECS = (
    (StrategyAction.STAY_OUT, None),
    (StrategyAction.PIT_NOW, None),
    (StrategyAction.PIT_NOW, "SOFT"),
    (StrategyAction.PIT_NOW, "MEDIUM"),
    (StrategyAction.PIT_NOW, "HARD"),
    (StrategyAction.PIT_NEXT_LAP, None),
    (StrategyAction.PIT_NEXT_LAP, "SOFT"),
    (StrategyAction.PIT_NEXT_LAP, "MEDIUM"),
    (StrategyAction.PIT_NEXT_LAP, "HARD"),
)

_SAMPLED = "SAMPLED"


def candidate_key(action, requested_compound: Optional[str]) -> str:
    """Readable deterministic key distinguishing all candidates.

    ``PIT_NOW`` with ``requested_compound=None`` is the *sampled* compound and
    is deliberately distinct from an explicit compound identity.
    """
    action_value = action.value if hasattr(action, "value") else action
    return f"{action_value}:{requested_compound or _SAMPLED}"


def candidate_identity(action, requested_compound: Optional[str]) -> str:
    """Stable scientific identity of a candidate (action + compound only).

    Validity is a derived, state-dependent projection and is intentionally not
    part of the identity; the comparison identity carries the state identity.
    """
    action_value = action.value if hasattr(action, "value") else action
    return canonical_sha256({
        "candidate_contract_version": CANDIDATE_CONTRACT_VERSION,
        "action": action_value,
        "requested_compound": requested_compound,
    })


@dataclass(frozen=True)
class StrategyCandidate:
    """One candidate intervention plus its static (pre-run) validity.

    ``action`` is the canonical action value (or the raw rejected value when
    the action itself is unsupported). ``intervention`` is the constructed
    ``StrategyIntervention`` when one could be built; it is ``None`` only for a
    structurally impossible candidate (unknown action / compound outside the v1
    dry set). ``reason`` is one of ``CANDIDATE_INVALIDITY_REASONS`` for an
    invalid candidate and ``None`` for a valid one.
    """

    action: str
    requested_compound: Optional[str]
    valid: bool
    reason: Optional[str]
    intervention: Optional[StrategyIntervention]

    def __post_init__(self) -> None:
        if self.valid:
            if self.intervention is None:
                raise ValueError("a valid candidate must carry an intervention")
            if self.reason is not None:
                raise ValueError("a valid candidate must not carry a reason")
        else:
            if self.reason is None:
                raise ValueError("an invalid candidate must carry a reason")
            if self.reason not in CANDIDATE_INVALIDITY_REASONS:
                raise ValueError(f"unknown candidate reason {self.reason!r}")

    @property
    def key(self) -> str:
        return candidate_key(self.action, self.requested_compound)

    def identity(self) -> str:
        return candidate_identity(self.action, self.requested_compound)

    def to_dict(self) -> dict:
        return {
            "candidate_contract_version": CANDIDATE_CONTRACT_VERSION,
            "candidate_identity": self.identity(),
            "candidate_key": self.key,
            "action": self.action,
            "requested_compound": self.requested_compound,
            "valid": self.valid,
            "reason": self.reason,
            "intervention_identity": (
                self.intervention.identity()
                if self.intervention is not None else None),
        }


def _canonical_index(action: str, requested_compound: Optional[str]) -> int:
    for index, (canonical_action, canonical_compound) in enumerate(
            CANONICAL_CANDIDATE_SPECS):
        if canonical_action.value == action \
                and canonical_compound == requested_compound:
            return index
    return len(CANONICAL_CANDIDATE_SPECS)


def build_candidate(state, config, target_driver_id: str, action,
                    requested_compound: Optional[str], *,
                    decision_lap: Optional[int] = None,
                    decision_state_identity: Optional[str] = None
                    ) -> StrategyCandidate:
    """Validate ONE (action, compound) against the factual state at T.

    ``decision_lap`` / ``decision_state_identity`` default to the target
    driver's factual values at T; overriding them is only for direct/manual
    validation (e.g. proving that a mismatched anchor is rejected).
    """
    try:
        action_enum = strategy_action_value(action)
    except StrategyContractError:
        raw = action.value if hasattr(action, "value") else action
        raw = raw if isinstance(raw, str) else repr(raw)
        return StrategyCandidate(
            action=raw, requested_compound=requested_compound, valid=False,
            reason=REASON_STRATEGY_UNSUPPORTED_ACTION, intervention=None)

    if requested_compound is not None \
            and requested_compound not in SUPPORTED_REQUESTED_COMPOUNDS:
        return StrategyCandidate(
            action=action_enum.value, requested_compound=requested_compound,
            valid=False, reason=REASON_STRATEGY_UNSUPPORTED_COMPOUND,
            intervention=None)

    entry = state.driver_by_id.get(target_driver_id)
    if decision_lap is not None:
        lap = decision_lap
    elif entry is not None:
        lap = entry.lap_number
    else:
        lap = 0
    identity = (state.identity() if decision_state_identity is None
                else decision_state_identity)
    try:
        intervention = StrategyIntervention(
            target_driver_id=target_driver_id, action=action_enum,
            requested_compound=requested_compound, decision_lap=lap,
            decision_state_identity=identity)
    except StrategyContractError:
        return StrategyCandidate(
            action=action_enum.value, requested_compound=requested_compound,
            valid=False, reason=REASON_STRATEGY_MALFORMED, intervention=None)

    try:
        _resolve_intervention(intervention, state, config)
    except StrategyInterventionError as exc:
        return StrategyCandidate(
            action=action_enum.value, requested_compound=requested_compound,
            valid=False, reason=exc.reason, intervention=intervention)
    return StrategyCandidate(
        action=action_enum.value, requested_compound=requested_compound,
        valid=True, reason=None, intervention=intervention)


def generate_candidates(state, config, target_driver_id: str, *,
                        specs: Optional[Iterable] = None) -> tuple:
    """Generate the canonical candidate set (or a caller-supplied subset).

    Duplicate scientific candidates (same action and compound) are
    deterministic-deduplicated; the first occurrence wins. The result is always
    returned in canonical action order, so the caller's input order cannot
    affect any downstream identity or result.
    """
    if specs is None:
        specs = CANONICAL_CANDIDATE_SPECS
    unique: dict = {}
    for action, requested_compound in specs:
        candidate = build_candidate(state, config, target_driver_id, action,
                                    requested_compound)
        unique.setdefault(candidate.key, candidate)
    return tuple(sorted(
        unique.values(),
        key=lambda candidate: (_canonical_index(candidate.action,
                                                candidate.requested_compound),
                               candidate.key)))
