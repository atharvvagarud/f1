"""Phase-6 R1 execution configuration, assumptions, and identity seams.

R1 owns the *execution semantics* (how many trials, which seed, whether
reliability is active) and the *identity seams* that make a future run
reproducible. It deliberately does NOT own empirical parameter values:
``ParameterIdentity`` is a contract-only placeholder until R3 supplies a
validated, versioned artifact, and ``Assumptions`` is an intentionally
minimal versioned object with zero speculative controls.

No parameter estimation, no fake parameter set, no current production
parameter version is invented here.
"""

from __future__ import annotations

from dataclasses import dataclass

from raceintel.simulation.errors import SimulationContractError
from raceintel.simulation.state import (
    SIMULATION_CONTRACT_VERSION,
    Provenance,
    canonical_sha256,
    provenance_value,
)
from raceintel.simulation.state import (
    _req_bool,
    _req_contract_version,
    _req_id,
    _req_int,
)

__all__ = [
    "ASSUMPTIONS_VERSION",
    "MAX_MASTER_SEED",
    "Assumptions",
    "ParameterIdentity",
    "SimulationConfig",
    "simulation_request_identity",
]

#: Assumptions contract version. R1 defines no controls; future typed
#: overrides must bump this version and keep the same controlled shape.
ASSUMPTIONS_VERSION = "v1"

#: Inclusive upper bound for ``master_seed`` (fits an unsigned 64-bit
#: integer; NumPy SeedSequence accepts any non-negative Python int, but a
#: bounded type keeps the contract portable and JSON-safe).
MAX_MASTER_SEED = 2**64 - 1


@dataclass(frozen=True)
class SimulationConfig:
    """Execution semantics for a simulation request (R1-L).

    - ``simulation_count``: trials to run, strictly positive. No arbitrary
      production maximum is invented; a runtime/API cap belongs to a later
      benchmark-backed stage.
    - ``master_seed``: explicit, bounded, never implicit/time-based.
    - ``sample_orders``: how many full classifications to retain (0 by
      default); non-negative and never more than ``simulation_count``.
    - ``reliability_enabled``: execution switch only; the hazard itself is
      R6, but R6 deliberately DEFERS the reliability model (no R3 hazard
      family exists), so the engine still rejects ``True`` rather than
      fabricating a no-DNF result.
    - ``pit_dynamics_enabled``: R6 switch for historically plausible pit
      timing, pit loss, compound transitions, and tyre-age resets. Defaults
      OFF: with it off (and reliability off) the engine is byte-equivalent
      to R5. This is the explicit R5-compatible mode required by R6-B; the
      production default is only reconsidered after R7 validation. No
      traffic/overtaking knob is exposed because that model is deferred.
    """

    simulation_count: int
    master_seed: int
    sample_orders: int = 0
    reliability_enabled: bool = False
    pit_dynamics_enabled: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "simulation_count",
                            _req_int(self.simulation_count,
                                     "simulation_count", minimum=1))
        seed = _req_int(self.master_seed, "master_seed", minimum=0)
        if seed > MAX_MASTER_SEED:
            raise SimulationContractError(
                f"master_seed must be <= {MAX_MASTER_SEED}, got {seed!r}")
        object.__setattr__(self, "master_seed", seed)
        sample = _req_int(self.sample_orders, "sample_orders", minimum=0)
        if sample > self.simulation_count:
            raise SimulationContractError(
                "sample_orders must not exceed simulation_count, "
                f"got {sample!r} > {self.simulation_count!r}")
        object.__setattr__(self, "sample_orders", sample)
        object.__setattr__(self, "reliability_enabled",
                            _req_bool(self.reliability_enabled,
                                      "reliability_enabled"))
        object.__setattr__(self, "pit_dynamics_enabled",
                            _req_bool(self.pit_dynamics_enabled,
                                      "pit_dynamics_enabled"))

    def identity(self) -> str:
        """Deterministic identity of the execution configuration.

        Includes the seed because a run is a pure function of
        ``(seed, i, inputs, params, contract version)``.
        """
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict:
        payload = {
            "simulation_count": self.simulation_count,
            "master_seed": self.master_seed,
            "sample_orders": self.sample_orders,
            "reliability_enabled": self.reliability_enabled,
        }
        # R5-compat identity policy (R6-L): the R6 pit switch is omitted from
        # the serialized identity at its R5-equivalent default (False), so an
        # R5-compatible run keeps a byte-identical request identity. It is
        # recorded explicitly (and changes identity) once enabled.
        if self.pit_dynamics_enabled:
            payload["pit_dynamics_enabled"] = True
        return payload


@dataclass(frozen=True)
class Assumptions:
    """User/scenario assumptions, kept strictly separate from factual state.

    R1 version: a minimal, extensible, versioned object with NO speculative
    controls (R0's forced pit laps, compound overrides, injected track-state
    schedules, and weather scenarios are all DEFERRED). Its ``provenance``
    is pinned to ``USER_ASSUMPTION`` so it can never be confused with
    ``FACTUAL_AT_T`` or ``ORACLE_EVALUATION_ONLY`` data.

    Future stages add typed fields and bump ``assumptions_version``; an
    untyped dictionary must never become the primary contract.
    """

    assumptions_version: str = ASSUMPTIONS_VERSION
    provenance: Provenance = Provenance.USER_ASSUMPTION

    def __post_init__(self) -> None:
        object.__setattr__(self, "assumptions_version",
                            _req_id(self.assumptions_version,
                                    "assumptions_version"))
        resolved = provenance_value(self.provenance)
        if resolved is not Provenance.USER_ASSUMPTION:
            raise SimulationContractError(
                "Assumptions.provenance must be USER_ASSUMPTION, "
                f"got {resolved.value!r}")
        object.__setattr__(self, "provenance", resolved)

    def identity(self) -> str:
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict:
        return {
            "assumptions_version": self.assumptions_version,
            "provenance": self.provenance.value,
        }


@dataclass(frozen=True)
class ParameterIdentity:
    """Identity seam for the R3 empirical parameter artifact (R1-N).

    R1 does NOT create parameter files, estimate anything, or invent a
    current production parameter version. This object only carries the
    identity a future validated artifact must supply so a run stays
    reproducible. ``contract_only()`` is the explicit "not supplied"
    state before R3.
    """

    parameter_set_id: str | None = None
    parameter_version: str | None = None
    parameter_hash: str | None = None

    def __post_init__(self) -> None:
        values = (self.parameter_set_id, self.parameter_version,
                  self.parameter_hash)
        supplied = [value is not None for value in values]
        if any(supplied) and not all(supplied):
            raise SimulationContractError(
                "ParameterIdentity must be entirely contract-only (all "
                "None) or fully supplied (id/version/hash), got "
                f"{values!r}")
        if all(supplied):
            object.__setattr__(self, "parameter_set_id",
                                _req_id(self.parameter_set_id,
                                        "parameter_set_id"))
            object.__setattr__(self, "parameter_version",
                                _req_id(self.parameter_version,
                                        "parameter_version"))
            object.__setattr__(self, "parameter_hash",
                                _req_id(self.parameter_hash,
                                        "parameter_hash"))

    @classmethod
    def contract_only(cls) -> "ParameterIdentity":
        """Explicit 'no parameter artifact supplied yet' identity."""
        return cls()

    @property
    def supplied(self) -> bool:
        return self.parameter_set_id is not None

    def identity(self) -> str:
        return canonical_sha256(self.to_dict())

    def to_dict(self) -> dict:
        return {
            "parameter_set_id": self.parameter_set_id,
            "parameter_version": self.parameter_version,
            "parameter_hash": self.parameter_hash,
        }


def simulation_request_identity(state, config: SimulationConfig,
                                assumptions: Assumptions,
                                parameter_identity: ParameterIdentity | None
                                = None) -> str:
    """Deterministic identity of one simulation request/run (R1-R).

    Derived only from canonical scientific inputs: the simulation contract
    version, the starting-state identity, the execution config identity,
    the assumption identity, and (when present) the parameter identity.

    Never includes a timestamp, hostname, PID, random UUID, or memory
    address.
    """
    if not hasattr(state, "identity") or not callable(state.identity):
        raise SimulationContractError(
            "state must expose an identity() method (SimulationState)")
    if not isinstance(config, SimulationConfig):
        raise SimulationContractError(
            f"config must be a SimulationConfig, got {config!r}")
    if not isinstance(assumptions, Assumptions):
        raise SimulationContractError(
            f"assumptions must be an Assumptions, got {assumptions!r}")
    if parameter_identity is None:
        parameter_identity = ParameterIdentity.contract_only()
    if not isinstance(parameter_identity, ParameterIdentity):
        raise SimulationContractError(
            "parameter_identity must be a ParameterIdentity or None, "
            f"got {parameter_identity!r}")
    _req_contract_version(SIMULATION_CONTRACT_VERSION)
    payload = {
        "simulation_contract_version": SIMULATION_CONTRACT_VERSION,
        "state_identity": state.identity(),
        "config_identity": config.identity(),
        "assumptions_identity": assumptions.identity(),
        "parameter_identity": parameter_identity.identity(),
    }
    return canonical_sha256(payload)
