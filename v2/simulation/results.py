"""Phase-6 R1 structural result contracts (no aggregation implemented).

These types define only the *shape* of a single simulated outcome, a
per-driver summary, and a Monte Carlo aggregate so R5 can populate them
without redefining contracts. R1 computes none of the values: no engine,
no aggregation, no points table, no probabilities estimated.

Probability semantic (R1-Y): Phase-6 probabilities are
``MONTE_CARLO_FREQUENCY`` — empirical frequencies over *valid* simulated
outcomes. This is NOT the frozen Phase-4/5 ``INDEPENDENT_BINARY``
per-driver probability and must never be derived by normalizing it.
"""

from __future__ import annotations

from dataclasses import dataclass

from v2.simulation.errors import (
    SimulationContractError,
    SimulationValidationError,
)
from v2.simulation.state import (
    SIMULATION_CONTRACT_VERSION,
    _opt_float,
    _opt_int,
    _req_bool,
    _req_contract_version,
    _req_float,
    _req_id,
    _req_int,
    canonical_sha256,
)

#: Phase-6 probability semantic: empirical frequency over valid trials.
PROBABILITY_SEMANTICS = "MONTE_CARLO_FREQUENCY"

#: Human-readable contract note shipped with every aggregate.
PROBABILITY_SEMANTICS_NOTE = (
    "Phase-6 probabilities are empirical frequencies over valid simulated "
    "outcomes (one winner per trial). They are not INDEPENDENT_BINARY "
    "per-driver model probabilities and were not produced by renormalizing "
    "any Phase-4/5 output."
)

#: DNF bucket representation for a finish-position distribution.
DNF_POSITION = None


# ---------------------------------------------------------------------------
# Per-run classification (R1-V, R1-AA).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DriverFinish:
    """One driver's structural outcome inside a classification.

    ``retired`` is explicit; a retired driver is never classified and never
    receives a finish position. A non-classified, non-retired entry is
    structurally representable (e.g. did not take the start).
    """

    driver_id: str
    classified: bool
    retired: bool
    laps_completed: int
    race_time_s: float
    finish_position: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "driver_id",
                            _req_id(self.driver_id, "driver_id"))
        object.__setattr__(self, "classified",
                            _req_bool(self.classified, "classified"))
        object.__setattr__(self, "retired",
                            _req_bool(self.retired, "retired"))
        if self.classified and self.retired:
            raise SimulationValidationError(
                f"driver {self.driver_id!r} cannot be both classified and "
                f"retired")
        object.__setattr__(self, "laps_completed",
                            _req_int(self.laps_completed, "laps_completed",
                                     minimum=0))
        object.__setattr__(self, "race_time_s",
                            _req_float(self.race_time_s, "race_time_s",
                                       minimum=0.0))
        object.__setattr__(self, "finish_position",
                            _opt_int(self.finish_position,
                                     "finish_position", minimum=1))
        if self.classified and self.finish_position is None:
            raise SimulationValidationError(
                f"classified driver {self.driver_id!r} requires a "
                f"finish_position")
        if not self.classified and self.finish_position is not None:
            raise SimulationValidationError(
                f"unclassified driver {self.driver_id!r} must not carry a "
                f"finish_position, got {self.finish_position!r}")

    def to_dict(self) -> dict:
        return {
            "driver_id": self.driver_id,
            "classified": self.classified,
            "retired": self.retired,
            "laps_completed": self.laps_completed,
            "race_time_s": self.race_time_s,
            "finish_position": self.finish_position,
        }


@dataclass(frozen=True)
class FinishOrder:
    """A structural classification accounting for every starting driver.

    Contract (R1-AA), validated structurally and never by a ranking
    library:
    - exactly one entry per starting driver (``roster_size``);
    - unique driver ids;
    - classified finish positions are unique and form ``1..K`` with no
      gaps;
    - retired drivers are explicit and carry no position;
    - lapped drivers are permitted (their ``laps_completed`` may differ).

    The engine's ordering algorithm is DEFERRED; entries are stored in a
    canonical structural order for deterministic serialization:
    classified first by ``finish_position``, then the remainder by
    ``driver_id``.
    """

    roster_size: int
    entries: tuple

    def __post_init__(self) -> None:
        object.__setattr__(self, "roster_size",
                            _req_int(self.roster_size, "roster_size",
                                     minimum=1))
        entries = list(self.entries) if self.entries is not None else []
        if not entries:
            raise SimulationContractError(
                "FinishOrder requires a non-empty entry collection")
        for entry in entries:
            if not isinstance(entry, DriverFinish):
                raise SimulationContractError(
                    f"FinishOrder.entries must contain only DriverFinish, "
                    f"got {entry!r}")
        ids = [entry.driver_id for entry in entries]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise SimulationContractError(
                f"duplicate driver entries: {duplicates}")
        if len(entries) != self.roster_size:
            raise SimulationValidationError(
                f"classification must account for every starting driver "
                f"exactly once: {len(entries)} entries for roster_size "
                f"{self.roster_size}")

        classified = [entry for entry in entries if entry.classified]
        positions = sorted(entry.finish_position for entry in classified)
        if positions != list(range(1, len(classified) + 1)):
            raise SimulationValidationError(
                "classified finish positions must be unique and form "
                f"1..K with no gaps, got {positions!r}")

        ordered = sorted(
            entries,
            key=lambda entry: (
                0 if entry.classified else 1,
                entry.finish_position if entry.classified else 0,
                entry.driver_id,
            ),
        )
        object.__setattr__(self, "entries", tuple(ordered))

    @property
    def classified_count(self) -> int:
        return sum(1 for entry in self.entries if entry.classified)

    @property
    def retired_count(self) -> int:
        return sum(1 for entry in self.entries if entry.retired)

    @property
    def finishing_order(self) -> tuple:
        """Classified driver ids in finish-position order."""
        return tuple(entry.driver_id for entry in self.entries
                     if entry.classified)

    def to_dict(self) -> dict:
        return {
            "roster_size": self.roster_size,
            "classified_count": self.classified_count,
            "retired_count": self.retired_count,
            "entries": [entry.to_dict() for entry in self.entries],
        }


@dataclass(frozen=True)
class SimulationRunResult:
    """Structural result of exactly one simulated trial (R1-V).

    ``simulation_id`` is the deterministic per-trial identity supplied by
    the engine; ``simulation_index`` is the RNG stream id. A valid trial
    must carry a complete classification; an invalid trial must carry a
    non-empty reason and is excluded from frequencies but always counted.
    """

    race_id: str
    simulation_id: str
    simulation_index: int
    valid: bool
    classification: FinishOrder | None = None
    invalid_reason: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "race_id",
                            _req_id(self.race_id, "race_id"))
        object.__setattr__(self, "simulation_id",
                            _req_id(self.simulation_id, "simulation_id"))
        object.__setattr__(self, "simulation_index",
                            _req_int(self.simulation_index,
                                     "simulation_index", minimum=0))
        object.__setattr__(self, "valid",
                            _req_bool(self.valid, "valid"))
        if self.classification is not None \
                and not isinstance(self.classification, FinishOrder):
            raise SimulationContractError(
                "classification must be a FinishOrder or None, "
                f"got {self.classification!r}")
        if self.valid:
            if self.classification is None:
                raise SimulationValidationError(
                    "a valid run requires a complete classification")
            if self.invalid_reason is not None:
                raise SimulationValidationError(
                    "a valid run must not carry an invalid_reason")
        else:
            object.__setattr__(self, "invalid_reason",
                                _req_id(self.invalid_reason,
                                        "invalid_reason"))

    def to_dict(self) -> dict:
        return {
            "race_id": self.race_id,
            "simulation_id": self.simulation_id,
            "simulation_index": self.simulation_index,
            "valid": self.valid,
            "classification": None if self.classification is None
            else self.classification.to_dict(),
            "invalid_reason": self.invalid_reason,
        }


# ---------------------------------------------------------------------------
# Per-driver summary (R1-W).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PositionFrequency:
    """One ``finish_position_distribution`` key: a position or the DNF bucket.

    ``position is None`` is the DNF bucket. Frequencies are bounded to
    ``[0, 1]``; R1 deliberately does NOT enforce sum-to-one (a partially
    populated or test summary is legal, and reliability may be off).
    """

    position: int | None
    frequency: float

    def __post_init__(self) -> None:
        if self.position is not None:
            object.__setattr__(self, "position",
                                _req_int(self.position, "position",
                                         minimum=1))
        freq = _req_float(self.frequency, "frequency", minimum=0.0)
        if freq > 1.0:
            raise SimulationValidationError(
                f"frequency must be <= 1.0, got {freq!r}")
        object.__setattr__(self, "frequency", freq)

    def to_dict(self) -> dict:
        return {"position": self.position, "frequency": self.frequency}


@dataclass(frozen=True)
class DriverSimulationSummary:
    """Structural per-driver aggregate (values are populated in R5).

    Every probability/expected value is optional and, when supplied, must
    be finite and in range. ``dnf_probability`` is meaningful only when
    reliability semantics are active; R1 does not invent or fabricate it.
    """

    driver_id: str
    win_probability: float | None = None
    podium_probability: float | None = None
    points_probability: float | None = None
    expected_finish: float | None = None
    expected_points: float | None = None
    dnf_probability: float | None = None
    finish_position_distribution: tuple = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "driver_id",
                            _req_id(self.driver_id, "driver_id"))
        for field_name in ("win_probability", "podium_probability",
                           "points_probability", "dnf_probability"):
            object.__setattr__(self, field_name,
                               _probability(getattr(self, field_name),
                                            field_name))
        expected_finish = _opt_float(self.expected_finish,
                                     "expected_finish", minimum=1.0)
        object.__setattr__(self, "expected_finish", expected_finish)
        object.__setattr__(self, "expected_points",
                            _opt_float(self.expected_points,
                                       "expected_points", minimum=0.0))

        entries = list(self.finish_position_distribution) \
            if self.finish_position_distribution is not None else []
        for entry in entries:
            if not isinstance(entry, PositionFrequency):
                raise SimulationContractError(
                    "finish_position_distribution must contain only "
                    f"PositionFrequency, got {entry!r}")
        positions = [entry.position for entry in entries]
        duplicates = sorted(
            {str(p) for p in positions if positions.count(p) > 1})
        if duplicates:
            raise SimulationValidationError(
                f"duplicate position-distribution keys: {duplicates}")
        object.__setattr__(self, "finish_position_distribution",
                            tuple(entries))

    def to_dict(self) -> dict:
        return {
            "driver_id": self.driver_id,
            "win_probability": self.win_probability,
            "podium_probability": self.podium_probability,
            "points_probability": self.points_probability,
            "expected_finish": self.expected_finish,
            "expected_points": self.expected_points,
            "dnf_probability": self.dnf_probability,
            "finish_position_distribution": [
                entry.to_dict()
                for entry in self.finish_position_distribution],
        }


def _probability(value: object, name: str) -> float | None:
    if value is None:
        return None
    result = _req_float(value, name)
    if result < 0.0 or result > 1.0:
        raise SimulationValidationError(
            f"{name} must be in [0, 1], got {result!r}")
    return result


# ---------------------------------------------------------------------------
# Monte Carlo aggregate (R1-X, R1-Z).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MonteCarloResult:
    """Structural aggregate over many trials (populated by R5).

    ``runtime_s`` is operational metadata and is explicitly EXCLUDED from
    ``identity()``: wall-clock timing must never participate in scientific
    reproducibility. ``sample_orders`` reuses ``FinishOrder`` so a retained
    sample is guaranteed complete and free of duplicate/missing drivers.
    """

    simulation_request_identity: str
    race_id: str
    requested_simulation_count: int
    valid_simulation_count: int
    invalid_simulation_count: int
    master_seed: int
    parameter_identity: str
    assumptions_identity: str
    driver_summaries: tuple
    sample_orders: tuple = ()
    runtime_s: float | None = None
    simulation_contract_version: str = SIMULATION_CONTRACT_VERSION
    probability_semantics: str = PROBABILITY_SEMANTICS
    probability_semantics_note: str = PROBABILITY_SEMANTICS_NOTE

    def __post_init__(self) -> None:
        object.__setattr__(self, "simulation_request_identity",
                            _req_id(self.simulation_request_identity,
                                    "simulation_request_identity"))
        object.__setattr__(self, "race_id",
                            _req_id(self.race_id, "race_id"))
        requested = _req_int(self.requested_simulation_count,
                             "requested_simulation_count", minimum=1)
        valid = _req_int(self.valid_simulation_count,
                         "valid_simulation_count", minimum=0)
        invalid = _req_int(self.invalid_simulation_count,
                           "invalid_simulation_count", minimum=0)
        if valid + invalid != requested:
            raise SimulationValidationError(
                "valid + invalid simulation counts must equal the requested "
                f"count: {valid} + {invalid} != {requested}")
        object.__setattr__(self, "requested_simulation_count", requested)
        object.__setattr__(self, "valid_simulation_count", valid)
        object.__setattr__(self, "invalid_simulation_count", invalid)
        object.__setattr__(self, "master_seed",
                            _req_int(self.master_seed, "master_seed",
                                     minimum=0))
        object.__setattr__(self, "parameter_identity",
                            _req_id(self.parameter_identity,
                                    "parameter_identity"))
        object.__setattr__(self, "assumptions_identity",
                            _req_id(self.assumptions_identity,
                                    "assumptions_identity"))

        summaries = list(self.driver_summaries) \
            if self.driver_summaries is not None else []
        if not summaries:
            raise SimulationContractError(
                "MonteCarloResult requires at least one driver summary")
        for summary in summaries:
            if not isinstance(summary, DriverSimulationSummary):
                raise SimulationContractError(
                    "driver_summaries must contain only "
                    f"DriverSimulationSummary, got {summary!r}")
        ids = [summary.driver_id for summary in summaries]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise SimulationContractError(
                f"duplicate driver summaries: {duplicates}")
        summaries = sorted(summaries, key=lambda s: s.driver_id)
        object.__setattr__(self, "driver_summaries", tuple(summaries))

        orders = list(self.sample_orders) \
            if self.sample_orders is not None else []
        for order in orders:
            if not isinstance(order, FinishOrder):
                raise SimulationContractError(
                    "sample_orders must contain only FinishOrder, "
                    f"got {order!r}")
            if order.roster_size != len(summaries):
                raise SimulationValidationError(
                    "sample-order roster_size must match the summary "
                    f"roster: {order.roster_size} != {len(summaries)}")
        object.__setattr__(self, "sample_orders", tuple(orders))

        object.__setattr__(self, "runtime_s",
                            _opt_float(self.runtime_s, "runtime_s",
                                       minimum=0.0))
        object.__setattr__(self, "simulation_contract_version",
                            _req_contract_version(
                                self.simulation_contract_version))
        if self.probability_semantics != PROBABILITY_SEMANTICS:
            raise SimulationContractError(
                "probability_semantics must stay "
                f"{PROBABILITY_SEMANTICS!r}, "
                f"got {self.probability_semantics!r}")

    @property
    def driver_summary_by_id(self) -> dict:
        return {summary.driver_id: summary
                for summary in self.driver_summaries}

    def identity(self) -> str:
        """Scientific identity: identical for different wall-clock runtime."""
        payload = self.to_dict()
        payload.pop("runtime_s", None)
        return canonical_sha256(payload)

    def to_dict(self) -> dict:
        return {
            "simulation_request_identity": self.simulation_request_identity,
            "race_id": self.race_id,
            "simulation_contract_version": self.simulation_contract_version,
            "requested_simulation_count": self.requested_simulation_count,
            "valid_simulation_count": self.valid_simulation_count,
            "invalid_simulation_count": self.invalid_simulation_count,
            "master_seed": self.master_seed,
            "parameter_identity": self.parameter_identity,
            "assumptions_identity": self.assumptions_identity,
            "probability_semantics": self.probability_semantics,
            "probability_semantics_note": self.probability_semantics_note,
            "driver_summaries": [summary.to_dict()
                                 for summary in self.driver_summaries],
            "sample_orders": [order.to_dict() for order in self.sample_orders],
            "runtime_s": self.runtime_s,
        }
