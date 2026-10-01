"""Phase-7 S1 strategy-domain contracts (immutable, versioned).

Only the intervention contract is implemented at S1: the action vocabulary,
the supported requested compounds, an immutable, canonically serializable
``StrategyIntervention`` with a stable identity, and strict contract-level
validation. State-dependent validity (driver in roster, room for the action,
simulation eligibility) and all mechanics belong to later stages and are
deliberately absent.

The seam error ``StrategyInterventionNotImplemented`` is owned by the neutral
simulation boundary (``v2.simulation.monte_carlo``) and re-exported here so a
strategy caller can catch a single type. This keeps the dependency direction
one-way: ``v2.strategy`` -> ``v2.simulation``.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from raceintel.simulation.monte_carlo import StrategyInterventionNotImplemented
from raceintel.simulation.state import Provenance, canonical_sha256

__all__ = [
    "INTERVENTION_VERSION",
    "STRATEGY_CONTRACT_VERSION",
    "SUPPORTED_REQUESTED_COMPOUNDS",
    "StrategyAction",
    "StrategyContractError",
    "StrategyIntervention",
    "StrategyInterventionNotImplemented",
    "strategy_action_value",
]

#: Structural version of the Phase-7 strategy contract surface.
STRATEGY_CONTRACT_VERSION = "s1"

#: Version of the intervention semantics. S1 defines transport/validation
#: only; S2 implements the behaviour under this same version unless the
#: action-resolution semantics change (then it must be bumped).
INTERVENTION_VERSION = "v1"

#: Compounds a v1 intervention may explicitly request. Deliberately narrower
#: than ``params.DRY_COMPOUNDS``: SUPERSOFT/ULTRASOFT are legal dry compounds
#: in Phase-6 but are not exposed by strategy v1. ``None`` means
#: "baseline-drawn compound".
SUPPORTED_REQUESTED_COMPOUNDS = ("SOFT", "MEDIUM", "HARD")


class StrategyContractError(ValueError):
    """A Phase-7 strategy contract object is structurally malformed.

    This is a strategy-layer error (it is not a Phase-6 simulation error) so
    later strategy services can map it without pulling in simulation
    internals.
    """


class StrategyAction(str, Enum):
    """The only strategy actions v1 exposes."""

    STAY_OUT = "STAY_OUT"
    PIT_NOW = "PIT_NOW"
    PIT_NEXT_LAP = "PIT_NEXT_LAP"


def strategy_action_value(value: object) -> StrategyAction:
    """Coerce a controlled action value; reject anything else."""
    if isinstance(value, StrategyAction):
        return value
    if isinstance(value, str):
        try:
            return StrategyAction(value)
        except ValueError:
            pass
    raise StrategyContractError(
        "action must be one of "
        f"{[member.value for member in StrategyAction]}, got {value!r}")


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise StrategyContractError(
            f"{name} must be a non-empty canonical identity string, "
            f"got {value!r}")
    return value


def _require_nonneg_int(value: object, name: str) -> int:
    # Exact-type check: numpy/pandas integer scalars and bools are rejected.
    if type(value) is not int or value < 0:
        raise StrategyContractError(
            f"{name} must be a non-negative plain Python int, got {value!r}")
    return value


def _require_compound(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value in SUPPORTED_REQUESTED_COMPOUNDS:
        return value
    raise StrategyContractError(
        "requested_compound must be None or one of "
        f"{list(SUPPORTED_REQUESTED_COMPOUNDS)}, got {value!r}")


def _require_user_assumption(value: object) -> Provenance:
    resolved: Provenance | None = None
    if isinstance(value, Provenance):
        resolved = value
    elif isinstance(value, str):
        try:
            resolved = Provenance(value)
        except ValueError:
            resolved = None
    if resolved is not Provenance.USER_ASSUMPTION:
        raise StrategyContractError(
            "provenance must be USER_ASSUMPTION: an intervention is a user "
            "assumption and can never be labelled factual state, got "
            f"{value!r}")
    return resolved


@dataclass(frozen=True)
class StrategyIntervention:
    """One immutable, versioned strategy intervention at the anchor T.

    This is a pure value: it holds no ``SimulationState``, no parameters and
    no engine, so creating it can never mutate factual state. It is
    canonically serializable and has a stable ``identity()``. It carries no
    pace/compound effect in S1 (and none in v1: Phase-6 has no identified
    per-compound pace delta).

    ``decision_lap`` is the target driver's OWN completed-lap count at T and
    ``decision_state_identity`` is ``SimulationState.identity()`` at T; their
    agreement with a live state is state-dependent validity and belongs to
    later intervention mechanics, not to this contract.
    """

    target_driver_id: str
    action: StrategyAction
    requested_compound: str | None
    decision_lap: int
    decision_state_identity: str
    strategy_contract_version: str = STRATEGY_CONTRACT_VERSION
    intervention_version: str = INTERVENTION_VERSION
    provenance: Provenance = Provenance.USER_ASSUMPTION

    def __post_init__(self) -> None:
        if self.strategy_contract_version != STRATEGY_CONTRACT_VERSION:
            raise StrategyContractError(
                "unsupported strategy_contract_version "
                f"{self.strategy_contract_version!r} (this contract supports "
                f"{STRATEGY_CONTRACT_VERSION!r})")
        if self.intervention_version != INTERVENTION_VERSION:
            raise StrategyContractError(
                "unsupported intervention_version "
                f"{self.intervention_version!r} (this contract supports "
                f"{INTERVENTION_VERSION!r})")
        object.__setattr__(self, "target_driver_id",
                           _require_text(self.target_driver_id,
                                         "target_driver_id"))
        action = strategy_action_value(self.action)
        object.__setattr__(self, "action", action)
        compound = _require_compound(self.requested_compound)
        if action is StrategyAction.STAY_OUT and compound is not None:
            raise StrategyContractError(
                "STAY_OUT must not request a compound (requested_compound "
                f"must be None), got {compound!r}")
        object.__setattr__(self, "requested_compound", compound)
        object.__setattr__(self, "decision_lap",
                           _require_nonneg_int(self.decision_lap,
                                               "decision_lap"))
        object.__setattr__(self, "decision_state_identity",
                           _require_text(self.decision_state_identity,
                                         "decision_state_identity"))
        object.__setattr__(self, "provenance",
                           _require_user_assumption(self.provenance))

    @classmethod
    def from_dict(cls, payload) -> "StrategyIntervention":
        """Build from a mapping; the mapping is copied, never retained."""
        if not isinstance(payload, dict):
            raise StrategyContractError(
                f"payload must be a mapping, got {payload!r}")
        required = ("target_driver_id", "action", "requested_compound",
                    "decision_lap", "decision_state_identity")
        missing = [key for key in required if key not in payload]
        if missing:
            raise StrategyContractError(
                f"payload is missing required keys: {missing}")
        return cls(
            target_driver_id=payload["target_driver_id"],
            action=payload["action"],
            requested_compound=payload["requested_compound"],
            decision_lap=payload["decision_lap"],
            decision_state_identity=payload["decision_state_identity"],
            strategy_contract_version=payload.get(
                "strategy_contract_version", STRATEGY_CONTRACT_VERSION),
            intervention_version=payload.get(
                "intervention_version", INTERVENTION_VERSION),
            provenance=payload.get("provenance", Provenance.USER_ASSUMPTION),
        )

    def identity(self) -> str:
        """Stable canonical identity of this intervention."""
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict:
        return {
            "strategy_contract_version": self.strategy_contract_version,
            "intervention_version": self.intervention_version,
            "target_driver_id": self.target_driver_id,
            "action": self.action.value,
            "requested_compound": self.requested_compound,
            "decision_lap": self.decision_lap,
            "decision_state_identity": self.decision_state_identity,
            "provenance": self.provenance.value,
        }
