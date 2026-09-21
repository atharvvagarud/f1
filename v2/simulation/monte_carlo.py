"""Phase-6 R5 stochastic Monte Carlo race-simulation engine.

R5 is the first *stochastic* stage. It runs many independent, deterministically
seeded trajectories of the validated R4 deterministic evolution and aggregates
their valid finishing classifications into empirical
``MONTE_CARLO_FREQUENCY`` probabilities. It owns residual sampling,
per-simulation RNG streams, scalar and chunked/vectorized execution, exact
finishing-order parity, integer-count aggregation, win/podium probabilities,
per-driver finish-position distributions, expected finish, and the probability
invariants.

Stochastic pace equation (R5-C)
-------------------------------
For driver ``i`` on its next simulated lap ``l``::

    lap_time_i(l) = mu_i(l) + epsilon

where ``mu_i(l)`` is the *unchanged* R4 deterministic expected pace
(``engine.expected_lap_time_s``: circuit|era base + constructor offset +
race-progress delta + clamped tyre-age degradation delta) and ``epsilon`` is
an R3 empirical residual draw (R5-D). Nothing else in the R4 kernel changes.

Empirical quantile sampling (R5-D)
----------------------------------
The adopted R3 ``lap_residual_distribution_s`` stores a zero-median empirical
quantile function as ``(probabilities, quantile_values)`` plus the observed
support ``[observed_min, observed_max]``. R5 samples ``u ~ Uniform(0, 1)``
and linearly interpolates the empirical quantile function through the grid::

    (0, observed_min), (p_1, q_1), ..., (p_m, q_m), (1, observed_max)

so the draw is finite, transparent, deterministic for a fixed ``u``, and
bounded by the artifact's observed support. No Gaussian/uniform replacement
noise and no hardcoded seconds are used.

Residual centering (R5-E)
-------------------------
The artifact residual is centered at the empirical *median*, not the mean, and
its heavy positive tail means the sample mean is slightly positive. R5 does
NOT rescale or recenter to force a zero mean; the diagnostics are reported and
the distribution is used as stored.

Independence assumption (R5-F, prominent v1 limitation)
-------------------------------------------------------
R3 measured a positive lag-1 residual autocorrelation (~0.264) but
deliberately deferred a correlation model. **R5 v1 therefore assumes
independent per-lap residual draws.** This is a documented approximation: real
lap residuals are not independent, so simulated trajectories understate
lap-to-lap persistence. No AR(1)/covariance model is invented here.

RNG / draw-order contract (R5-G/H)
----------------------------------
Each trajectory ``i`` uses the R1 stream
``rng_for_simulation(master_seed, i, contract_version)``. Within a
trajectory, draws are consumed in deterministic *event order*: the
globally-earliest next-lap completion first; drivers sharing that exact
completion advance in canonical ``driver_id`` order; each advancing driver
that is rescheduled consumes exactly one uniform. Chunking is therefore
operational only — it never changes which draw belongs to which driver/event.

Vectorization architecture (R5-L/N)
-----------------------------------
The batch path evolves a chunk of trajectories together as ``(chunk, drivers)``
arrays but preserves each trajectory's own next-completion event semantics
(the earliest driver per trajectory is advanced, never a synchronous lap).
Each trajectory's uniforms are pre-drawn once from its own stream (a bounded
pool) and consumed sequentially in event order; the scalar oracle consumes
the same pool in the same order, so scalar and batch are bit-identical.

Dependency direction / firewalls (R5-AJ/AK)
-------------------------------------------
This module imports numpy and the Phase-6 simulation contracts only. It reads
no canonical D9/results/labels, no replay/replay-prediction cache, no feature
engine, and no winner model (``v2.prediction``/``v2.model_lab``); structural
tests enforce this. Monte Carlo frequencies come solely from simulated
outcomes and are never a normalization of ``INDEPENDENT_BINARY`` scores.

R6 pit dynamics (opt-in via ``SimulationConfig.pit_dynamics_enabled``)
----------------------------------------------------------------------
R6 adds historically plausible pit behaviour, never strategy optimisation:
a per-stint ``targetage`` is drawn from the R3 ``stint_length_laps``
distribution for the current compound; when the completed lap's tyre age
reaches that target the driver pits, a next compound is drawn from the R3
``compound_transition_probability`` frequencies (dry-filtered), an R3
``pit_effective_loss_s`` race-time loss is added exactly once, ``pit_count``
and ``stint_number`` increment, and the tyre age resets so the first lap on
the new tyre is age 1 (the pinned Phase-1 RaceState convention: an out-lap
row carries ``tyre_life == 1``). The initial target is drawn *conditional*
on exceeding the driver's factual tyre age (R6-E), so no retroactive or
negative remaining stint is fabricated.

All R6 random draws use domain-separated streams (``rng_for_domain``) so
enabling pits can never shift the frozen R5 pace/residual stream. With
``pit_dynamics_enabled=False`` and ``reliability_enabled=False`` the module
is byte-equivalent to R5 (R6-L).

Traffic/overtaking and reliability are deliberately DEFERRED (R6-P/Q/R):
R3 contains no calibrated overtaking/traffic penalty and no reliability
hazard family, so free-air ordering is retained and ``reliability_enabled``
is still rejected rather than faked.
"""

from __future__ import annotations

import math
import time
from bisect import bisect_right
from collections import Counter
from dataclasses import dataclass
from typing import List, Mapping, Optional

import numpy as np

from v2.simulation.config import (
    Assumptions,
    SimulationConfig,
    simulation_request_identity,
)
from v2.simulation.engine import (
    ExecutionPolicy,
    REASON_ITERATION_LIMIT,
    REASON_MISSING_PACE_PARAMETER,
    REASON_NONFINITE_LAP_TIME,
    REASON_NONFINITE_RACE_TIME,
    REASON_NONPOSITIVE_LAP_TIME,
    SimulationUnsupportedError,
    _validate_start_state,
    _validate_temporal,
    expected_lap_time_s,
    max_lap_events,
    select_pace_parameters,
)
from v2.simulation.errors import (
    SimulationContractError,
    SimulationValidationError,
)
from v2.simulation.params import DRY_COMPOUNDS, SimulationParameterSet
from v2.simulation.results import (
    DriverFinish,
    DriverSimulationSummary,
    FinishOrder,
    MonteCarloResult,
    PositionFrequency,
    SimulationRunResult,
)
from v2.simulation.rng import rng_for_domain, rng_for_simulation
from v2.simulation.state import SIMULATION_CONTRACT_VERSION, SimulationState

__all__ = [
    "MONTE_CARLO_VERSION",
    "RESIDUAL_FAMILY",
    "RESIDUAL_INDEPENDENCE_ASSUMPTION",
    "RESIDUAL_INDEPENDENCE_NOTE",
    "DEFAULT_CHUNK_SIZE",
    "PODIUM_POSITIONS",
    "PROBABILITY_TOLERANCE",
    "PIT_DYNAMICS_VERSION",
    "STINT_LENGTH_FAMILY",
    "COMPOUND_TRANSITION_FAMILY",
    "PIT_LOSS_FAMILY",
    "GLOBAL_COMPOUND_KEY",
    "TRAFFIC_DEFERRED_NOTE",
    "RELIABILITY_DEFERRED_NOTE",
    "PIT_INVALID_REASONS",
    "ResidualSampler",
    "select_residual_sampler",
    "max_residual_draws",
    "PitParameterSet",
    "select_pit_parameters",
    "MonteCarloDiagnostics",
    "run_trajectory_scalar",
    "MonteCarloEngine",
]

#: Monte Carlo engine logic version (structural identity of R5 semantics).
MONTE_CARLO_VERSION = "r5-monte-carlo-v1"

#: R3 parameter family carrying the empirical residual quantiles.
RESIDUAL_FAMILY = "lap_residual_distribution_s"

#: Documented v1 independence approximation (R5-F).
RESIDUAL_INDEPENDENCE_ASSUMPTION = "independent_per_lap_v1"
RESIDUAL_INDEPENDENCE_NOTE = (
    "R5 v1 assumes independent per-lap residual draws. R3 measured positive "
    "lag-1 residual autocorrelation (~0.264) but a correlation model was "
    "deferred, so simulated trajectories are known not to reproduce lap-to-lap "
    "persistence. No AR(1)/covariance model is invented in R5."
)

#: Default trajectories per vectorized chunk (operational; never scientific).
DEFAULT_CHUNK_SIZE = 512

#: Positions that score a podium.
PODIUM_POSITIONS = 3

#: Tolerance for probability-sum invariants.
PROBABILITY_TOLERANCE = 1e-9

#: R6 pit-dynamics logic version (structural identity of R6 semantics).
PIT_DYNAMICS_VERSION = "r6-pit-dynamics-v1"

#: R3 parameter families consumed by R6 (read-only; nothing is re-estimated).
STINT_LENGTH_FAMILY = "stint_length_laps"
COMPOUND_TRANSITION_FAMILY = "compound_transition_probability"
PIT_LOSS_FAMILY = "pit_effective_loss_s"

#: Special key used by the R3 compound-transition family.
GLOBAL_COMPOUND_KEY = "GLOBAL"

#: Deferred-mechanic notes (R6-P/Q/R). Traffic and reliability are NOT
#: implemented because no defensible evidence-backed parameter exists.
TRAFFIC_DEFERRED_NOTE = (
    "Traffic/overtaking is DEFERRED (R6-P/Q): R3 deliberately did not "
    "estimate a calibrated overtaking or following-delay parameter because "
    "position changes are confounded by pit cycles/retirements/SC. R6 "
    "retains free-air deterministic ordering rather than inventing a "
    "passing threshold or dirty-air constant."
)
RELIABILITY_DEFERRED_NOTE = (
    "Reliability/DNF is DEFERRED (R6-R/S): R3 deliberately did not estimate "
    "a retirement hazard, and R6 chose not to add an unvalidated additive "
    "hazard artifact. Reliability stays off and reliability_enabled=True is "
    "rejected rather than fabricating a no-DNF result."
)

# Stable per-trajectory invalid reasons introduced by R6 (R6-AC).
REASON_MISSING_PIT_LENGTH_SUPPORT = "missing_pit_length_support"
REASON_MISSING_COMPOUND_TRANSITION = "missing_compound_transition"
REASON_UNSUPPORTED_WET_TRANSITION = "unsupported_wet_transition"
REASON_INVALID_PIT_LOSS = "invalid_pit_loss"
REASON_PIT_LOOP = "pit_loop_non_progress"

PIT_INVALID_REASONS = (
    REASON_MISSING_PIT_LENGTH_SUPPORT,
    REASON_MISSING_COMPOUND_TRANSITION,
    REASON_UNSUPPORTED_WET_TRANSITION,
    REASON_INVALID_PIT_LOSS,
    REASON_PIT_LOOP,
)


class _TrajectoryFailure(Exception):
    """Internal control-flow signal for one invalid stochastic trajectory."""

    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


# ---------------------------------------------------------------------------
# Empirical residual sampler (R5-D).
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ResidualSampler:
    """A bounded empirical quantile function for one R3 residual group.

    The grid is ``(0, observed_min), (p_1, q_1), ..., (p_m, q_m),
    (1, observed_max)``; sampling is a deterministic linear interpolation of
    ``u ~ Uniform(0, 1)`` over that grid.
    """

    era: str
    key: str
    probabilities: tuple
    quantile_values: tuple
    observed_min: float
    observed_max: float
    sample_count: int
    support_level: str
    fallback_level: str
    _xp: tuple = ()
    _fp: tuple = ()

    def __post_init__(self) -> None:
        probs = tuple(float(p) for p in self.probabilities)
        quants = tuple(float(q) for q in self.quantile_values)
        if not probs:
            raise SimulationContractError(
                f"residual sampler {self.key!r} has no probabilities")
        if len(probs) != len(quants):
            raise SimulationValidationError(
                "residual probabilities and quantile_values must have equal "
                f"length: {len(probs)} != {len(quants)}")
        previous = 0.0
        for p in probs:
            if not 0.0 < p < 1.0 or p <= previous:
                raise SimulationValidationError(
                    "residual probabilities must be strictly ascending in "
                    f"(0, 1), got {probs!r}")
            previous = p
        for q in quants:
            if not math.isfinite(q):
                raise SimulationValidationError(
                    f"residual quantile must be finite, got {q!r}")
        lo = float(self.observed_min)
        hi = float(self.observed_max)
        if not (math.isfinite(lo) and math.isfinite(hi)) or lo > hi:
            raise SimulationValidationError(
                f"residual support must be finite with min <= max, got "
                f"[{lo!r}, {hi!r}]")
        if quants[0] < lo or quants[-1] > hi:
            raise SimulationValidationError(
                "residual quantile values must lie inside the observed "
                f"support [{lo!r}, {hi!r}], got endpoints "
                f"{quants[0]!r}/{quants[-1]!r}")
        xp = (0.0,) + probs + (1.0,)
        fp = (lo,) + quants + (hi,)
        object.__setattr__(self, "probabilities", probs)
        object.__setattr__(self, "quantile_values", quants)
        object.__setattr__(self, "observed_min", lo)
        object.__setattr__(self, "observed_max", hi)
        object.__setattr__(self, "_xp", xp)
        object.__setattr__(self, "_fp", fp)

    @property
    def support(self) -> tuple:
        """Observed residual support ``(min, max)`` in seconds."""
        return (self.observed_min, self.observed_max)

    def sample(self, uniform):
        """Vectorized interpolation over an array of uniforms."""
        u = np.asarray(uniform, dtype=np.float64)
        return np.interp(u, np.asarray(self._xp), np.asarray(self._fp))

    def sample_unit(self, uniform: float) -> float:
        """Scalar interpolation for one uniform in ``[0, 1]``."""
        return float(np.interp(float(uniform),
                               np.asarray(self._xp), np.asarray(self._fp)))

    def to_dict(self) -> dict:
        return {
            "era": self.era,
            "key": self.key,
            "probabilities": list(self.probabilities),
            "quantile_values": list(self.quantile_values),
            "observed_min": self.observed_min,
            "observed_max": self.observed_max,
            "sample_count": self.sample_count,
            "support_level": self.support_level,
            "fallback_level": self.fallback_level,
        }


def select_residual_sampler(parameters: SimulationParameterSet,
                            era: str) -> ResidualSampler:
    """Select the R3 residual distribution for ``era`` (era then global).

    Raises ``SimulationUnsupportedError`` when the artifact carries no usable
    empirical residual distribution (never invents Gaussian/uniform noise).
    """
    if not isinstance(parameters, SimulationParameterSet):
        raise SimulationContractError(
            "parameters must be a SimulationParameterSet, got "
            f"{parameters!r}")
    family = parameters.family(RESIDUAL_FAMILY)
    for key in (era, "global"):
        entry = family.entries.get(key)
        if entry is not None and entry.is_distribution:
            return ResidualSampler(
                era=era,
                key=key,
                probabilities=tuple(entry.probabilities),
                quantile_values=tuple(entry.quantile_values),
                observed_min=float(entry.observed_min)
                if entry.observed_min is not None else
                float(entry.quantile_values[0]),
                observed_max=float(entry.observed_max)
                if entry.observed_max is not None else
                float(entry.quantile_values[-1]),
                sample_count=int(entry.sample_count),
                support_level=entry.support_level,
                fallback_level=entry.fallback_level,
            )
    raise SimulationUnsupportedError(
        REASON_MISSING_PACE_PARAMETER,
        f"no empirical residual distribution for era {era!r} or global in "
        f"family {RESIDUAL_FAMILY!r}")


def max_residual_draws(initial_state: SimulationState) -> int:
    """Structural upper bound on residual draws for one trajectory.

    A driver can complete at most ``scheduled_laps - lap_number`` more laps
    and consumes exactly one uniform per scheduled next lap, so the total is
    bounded by the field's remaining laps. This bound is independent of the
    simulation count and chunk size, which is what keeps the pool (and hence
    every trajectory's stream) chunking-invariant.
    """
    scheduled = initial_state.scheduled_laps
    return sum(max(0, scheduled - d.lap_number)
               for d in initial_state.drivers)


# ---------------------------------------------------------------------------
# R6 pit model: empirical quantile grids + parameter selection (R6-C..I).
# ---------------------------------------------------------------------------

def _lerp(value: float, xs, ys) -> float:
    """Deterministic piecewise-linear interpolation (matches ``np.interp``).

    Both the scalar oracle and the vectorized batch use this identical
    function so scalar/batch pit draws are bit-identical (R6-N).
    """
    x = np.asarray(xs, dtype=np.float64)
    y = np.asarray(ys, dtype=np.float64)
    return float(np.interp(float(value), x, y))


@dataclass(frozen=True)
class _QuantileGrid:
    """An empirical quantile grid plus its observed support.

    ``xp = (0, p_1, ..., p_m, 1)`` and ``fp = (observed_min, q_1, ..., q_m,
    observed_max)`` so sampling is a bounded linear interpolation of
    ``u ~ Uniform(0,1)`` and the support endpoints are the observed min/max
    (same construction as the R5 residual sampler).
    """

    key: str
    unit: str
    probabilities: tuple
    quantile_values: tuple
    observed_min: float
    observed_max: float
    support_level: str = "strong"
    fallback_level: str = "global"
    xp: tuple = ()
    fp: tuple = ()

    def __post_init__(self) -> None:
        probs = tuple(float(p) for p in self.probabilities)
        quants = tuple(float(q) for q in self.quantile_values)
        if not probs or len(probs) != len(quants):
            raise SimulationValidationError(
                f"pit grid {self.key!r} requires equal-length, non-empty "
                f"probabilities/quantile_values")
        previous = 0.0
        for p in probs:
            if not 0.0 < p < 1.0 or p <= previous:
                raise SimulationValidationError(
                    f"pit grid {self.key!r} probabilities must ascend in "
                    f"(0,1), got {probs!r}")
            previous = p
        for q in quants:
            if not math.isfinite(q):
                raise SimulationValidationError(
                    f"pit grid {self.key!r} quantiles must be finite")
        lo = float(self.observed_min)
        hi = float(self.observed_max)
        if not (math.isfinite(lo) and math.isfinite(hi)) or lo > hi:
            raise SimulationValidationError(
                f"pit grid {self.key!r} support must be finite with min<=max")
        object.__setattr__(self, "probabilities", probs)
        object.__setattr__(self, "quantile_values", quants)
        object.__setattr__(self, "observed_min", lo)
        object.__setattr__(self, "observed_max", hi)
        object.__setattr__(self, "xp", (0.0,) + probs + (1.0,))
        object.__setattr__(self, "fp", (lo,) + quants + (hi,))

    @classmethod
    def from_entry(cls, key: str, entry) -> "_QuantileGrid":
        return cls(
            key=key,
            unit="empirical",
            probabilities=tuple(entry.probabilities),
            quantile_values=tuple(entry.quantile_values),
            observed_min=float(entry.observed_min)
            if entry.observed_min is not None
            else float(entry.quantile_values[0]),
            observed_max=float(entry.observed_max)
            if entry.observed_max is not None
            else float(entry.quantile_values[-1]),
            support_level=entry.support_level,
            fallback_level=entry.fallback_level,
        )

    def sample_unit(self, uniform: float) -> float:
        return _lerp(uniform, self.xp, self.fp)

    def cdf(self, value: float) -> float:
        """Empirical CDF at ``value`` (inverse of the piecewise-linear Q)."""
        if value <= self.fp[0]:
            return 0.0
        if value >= self.fp[-1]:
            return 1.0
        return _lerp(value, self.fp, self.xp)

    def conditional_sample_unit(self, uniform: float, floor: float) -> float:
        """Quantile draw conditioned on exceeding ``floor`` (R6-E)."""
        base = self.cdf(floor)
        return self.sample_unit(base + uniform * (1.0 - base))

    def to_dict(self) -> dict:
        return {
            "key": self.key,
            "probabilities": list(self.probabilities),
            "quantile_values": list(self.quantile_values),
            "observed_min": self.observed_min,
            "observed_max": self.observed_max,
            "support_level": self.support_level,
            "fallback_level": self.fallback_level,
        }


def _pit_target_int(raw: float, minimum: int, maximum: int) -> int:
    """Round a drawn stint target to a valid integer lap count.

    ``minimum``/``maximum`` are applied as ``clamp(round(raw), max) then
    max(., min)`` so a floor (e.g. current age + 1) is never violated even
    when it exceeds the observed support; that is the documented R6-E
    fallback when no empirical support exists above the current age.
    """
    value = int(math.floor(float(raw) + 0.5))
    if value > maximum:
        value = maximum
    if value < minimum:
        value = minimum
    return value


def _pit_target_int_array(raw: np.ndarray, minimum: int,
                          maximum: int) -> np.ndarray:
    """Vectorized ``_pit_target_int`` (bit-identical integer results)."""
    values = np.floor(raw + 0.5).astype(np.int64)
    values = np.minimum(values, maximum)
    values = np.maximum(values, minimum)
    return values


def _select_stint_grid(parameters: SimulationParameterSet, era: str,
                       circuit: Optional[str],
                       compound: Optional[str]) -> Optional[_QuantileGrid]:
    """R3 ``stint_length_laps`` hierarchy: era|circuit|compound -> ... global."""
    family = parameters.family(STINT_LENGTH_FAMILY)
    candidates = []
    if compound is not None:
        if circuit is not None:
            candidates.append(f"{era}|{circuit}|{compound}")
        candidates.append(f"{era}|{compound}")
        candidates.append(compound)
    candidates.append("global")
    for key in candidates:
        entry = family.entries.get(key)
        if entry is not None and entry.is_distribution:
            return _QuantileGrid.from_entry(key, entry)
    return None


def _dry_transition_distribution(parameters: SimulationParameterSet,
                                 current: str
                                 ) -> Optional[tuple]:
    """Dry-filtered ``current -> next`` transition distribution (R6-G).

    R6 has no wet pace model, so wet targets are removed and the remaining
    dry mass is renormalized. Returns ``(targets, cumulative)`` or None when
    no dry target exists for ``current``.
    """
    family = parameters.family(COMPOUND_TRANSITION_FAMILY)
    prefix = f"{current}->"
    targets: List[str] = []
    weights: List[float] = []
    for key, entry in family.entries.items():
        if not key.startswith(prefix) or entry.value is None:
            continue
        target = key.split("->", 1)[1]
        if target not in DRY_COMPOUNDS:
            continue
        targets.append(target)
        weights.append(float(entry.value))
    total = sum(weights)
    if total <= 0.0:
        return None
    cumulative = []
    running = 0.0
    for weight in weights:
        running += weight / total
        cumulative.append(min(running, 1.0))
    cumulative[-1] = 1.0
    return tuple(targets), tuple(cumulative)


@dataclass(frozen=True)
class PitParameterSet:
    """Selected R3 pit artefacts for one starting state (read-only, R6-C).

    Contains only values copied from the R3 empirical artifact: stint-length
    grids per compound, dry-filtered compound-transition distributions, and
    the circuit-conditioned effective pit-loss grid. No parameter is
    estimated or invented at runtime.
    """

    era: str
    circuit: Optional[str]
    stint_grids: Mapping[str, _QuantileGrid]
    compound_fallback_grid: _QuantileGrid
    transitions: Mapping[str, tuple]
    pit_loss: _QuantileGrid
    pit_loss_key: str
    notes: tuple = ()

    def grid_for(self, compound: Optional[str]) -> _QuantileGrid:
        if compound is not None and compound in self.stint_grids:
            return self.stint_grids[compound]
        return self.compound_fallback_grid

    def transition_for(self, current: Optional[str]) -> tuple:
        if current is not None and current in self.transitions:
            return self.transitions[current]
        return self.transitions[GLOBAL_COMPOUND_KEY]


def select_pit_parameters(initial_state: SimulationState, selection,
                          parameters: SimulationParameterSet
                          ) -> PitParameterSet:
    """Select the R6 pit artefacts from the R3 hierarchy (R6-C).

    Raises ``SimulationUnsupportedError`` (missing pace parameter reason)
    when the artifact carries no usable stint-length or pit-loss distribution;
    never invents a value.
    """
    if not isinstance(parameters, SimulationParameterSet):
        raise SimulationContractError(
            f"parameters must be a SimulationParameterSet, got {parameters!r}")
    era = selection.era
    circuit = initial_state.circuit_id

    fallback_grid = _select_stint_grid(parameters, era, circuit, None)
    if fallback_grid is None:
        raise SimulationUnsupportedError(
            REASON_MISSING_PACE_PARAMETER,
            f"no {STINT_LENGTH_FAMILY!r} distribution (not even global)")

    grids: dict = {}
    for compound in DRY_COMPOUNDS:
        grid = _select_stint_grid(parameters, era, circuit, compound)
        if grid is not None:
            grids[compound] = grid

    transitions: dict = {}
    for current in tuple(DRY_COMPOUNDS) + (GLOBAL_COMPOUND_KEY,):
        distribution = _dry_transition_distribution(parameters, current)
        if distribution is not None:
            transitions[current] = distribution
    if GLOBAL_COMPOUND_KEY not in transitions:
        raise SimulationUnsupportedError(
            REASON_MISSING_PACE_PARAMETER,
            f"no dry-filtered {COMPOUND_TRANSITION_FAMILY!r} distribution")

    loss_family = parameters.family(PIT_LOSS_FAMILY)
    loss_key = None
    if circuit is not None and circuit in loss_family.entries \
            and loss_family.entries[circuit].is_distribution:
        loss_key = circuit
    elif "global" in loss_family.entries \
            and loss_family.entries["global"].is_distribution:
        loss_key = "global"
    if loss_key is None:
        raise SimulationUnsupportedError(
            REASON_MISSING_PACE_PARAMETER,
            f"no {PIT_LOSS_FAMILY!r} distribution (not even global)")
    pit_loss = _QuantileGrid.from_entry(loss_key,
                                        loss_family.entries[loss_key])

    return PitParameterSet(
        era=era,
        circuit=circuit,
        stint_grids=grids,
        compound_fallback_grid=fallback_grid,
        transitions=transitions,
        pit_loss=pit_loss,
        pit_loss_key=loss_key,
        notes=(TRAFFIC_DEFERRED_NOTE, RELIABILITY_DEFERRED_NOTE),
    )


# ---------------------------------------------------------------------------
# R6 diagnostics (R6-AE): descriptive simulation only, never a claim.
# ---------------------------------------------------------------------------

def _sample_summary(values: List[float]) -> Optional[dict]:
    if not values:
        return None
    array = np.asarray(values, dtype=np.float64)
    return {
        "count": int(array.size),
        "mean": float(array.mean()),
        "min": float(array.min()),
        "max": float(array.max()),
        "p50": float(np.quantile(array, 0.5)),
        "p90": float(np.quantile(array, 0.9)),
    }


@dataclass(frozen=True)
class MonteCarloDiagnostics:
    """Descriptive R6 pit diagnostics (R6-AE). NOT a probability contract."""

    mechanics: tuple
    valid_trajectories: int
    field_size: int
    total_pit_events: int
    mean_pits_per_driver: float
    pit_count_distribution: tuple
    fraction_zero_pits: float
    fraction_ge2_pits: float
    compound_transition_counts: tuple
    pit_loss_sample: Optional[dict]
    stint_target_sample: Optional[dict]

    def to_dict(self) -> dict:
        return {
            "mechanics": list(self.mechanics),
            "valid_trajectories": self.valid_trajectories,
            "field_size": self.field_size,
            "total_pit_events": self.total_pit_events,
            "mean_pits_per_driver": self.mean_pits_per_driver,
            "pit_count_distribution": [
                {"pit_count": count, "driver_trajectories": n}
                for count, n in self.pit_count_distribution],
            "fraction_zero_pits": self.fraction_zero_pits,
            "fraction_ge2_pits": self.fraction_ge2_pits,
            "compound_transition_counts": [
                {"transition": key, "count": n}
                for key, n in self.compound_transition_counts],
            "pit_loss_sample": self.pit_loss_sample,
            "stint_target_sample": self.stint_target_sample,
        }


# ---------------------------------------------------------------------------
# Scalar stochastic oracle (R5-J).
# ---------------------------------------------------------------------------

@dataclass
class _ScalarDriver:
    driver_id: str
    lap_number: int
    race_time_s: float
    tyre_age: int
    anchor_tyre_age: int
    base_pace_s: float
    compound: Optional[str] = None
    stint_number: int = 1
    pit_count: int = 0
    target_age: int = 0
    next_lap: int = 0
    next_age: int = 0
    next_time_s: float = 0.0
    finished: bool = False


def _classify_scalar(drivers: List[_ScalarDriver]) -> FinishOrder:
    ordered = sorted(
        drivers,
        key=lambda d: (-d.lap_number, d.race_time_s, d.driver_id),
    )
    entries = tuple(
        DriverFinish(
            driver_id=driver.driver_id,
            classified=True,
            retired=False,
            laps_completed=int(driver.lap_number),
            race_time_s=float(driver.race_time_s),
            finish_position=position,
        )
        for position, driver in enumerate(ordered, start=1)
    )
    return FinishOrder(roster_size=len(drivers), entries=entries)


def _draw_domain_pool(master_seed: int, simulation_index: int, domain: str,
                      size: int, contract_version: str) -> np.ndarray:
    """Pre-drawn domain-separated uniform pool (R6-K)."""
    if size <= 0:
        return np.empty(0, dtype=np.float64)
    generator = rng_for_domain(master_seed, simulation_index, domain,
                               contract_version=contract_version)
    return generator.random(size)


class _ScalarPitRuntime:
    """Per-trajectory R6 pit draws over domain-separated pre-drawn pools.

    Draw order at a pit is fixed and documented (R6-J): compound, then pit
    loss, then the next stint target. Initial targets consume the first
    ``roster_size`` timing uniforms in canonical driver order (R6-E). Every
    pool is pre-drawn from its own deterministic stream, exactly as the
    batch path does, so scalar and batch consume identical draws.
    """

    def __init__(self, pit_params: PitParameterSet, master_seed: int,
                 simulation_index: int, field_size: int, remaining: int,
                 contract_version: str, collect: bool):
        self.params = pit_params
        self.collect = collect
        self.timing = _draw_domain_pool(
            master_seed, simulation_index, "pit_timing",
            field_size + remaining, contract_version)
        self.compound = _draw_domain_pool(
            master_seed, simulation_index, "compound", remaining,
            contract_version)
        self.loss = _draw_domain_pool(
            master_seed, simulation_index, "pit_loss", remaining,
            contract_version)
        self.timing_cursor = 0
        self.compound_cursor = 0
        self.loss_cursor = 0
        self.transition_counts: Counter = Counter()
        self.loss_values: List[float] = []
        self.target_values: List[int] = []

    def _next_timing(self) -> float:
        if self.timing_cursor >= len(self.timing):
            raise _TrajectoryFailure(
                REASON_PIT_LOOP, "pit timing draw pool exhausted")
        value = float(self.timing[self.timing_cursor])
        self.timing_cursor += 1
        return value

    def initial_target(self, age: int, compound: Optional[str]) -> int:
        grid = self.params.grid_for(compound)
        raw = grid.conditional_sample_unit(self._next_timing(), float(age))
        return _pit_target_int(raw, age + 1, int(grid.observed_max))

    def _draw_next_compound(self, current: Optional[str]) -> str:
        targets, cumulative = self.params.transition_for(current)
        if self.compound_cursor >= len(self.compound):
            raise _TrajectoryFailure(
                REASON_PIT_LOOP, "compound draw pool exhausted")
        uniform = float(self.compound[self.compound_cursor])
        self.compound_cursor += 1
        index = bisect_right(cumulative, uniform)
        if index >= len(targets):
            index = len(targets) - 1
        target = targets[index]
        if self.collect:
            self.transition_counts[f"{current}->{target}"] += 1
        return target

    def _draw_loss(self) -> float:
        if self.loss_cursor >= len(self.loss):
            raise _TrajectoryFailure(
                REASON_PIT_LOOP, "pit loss draw pool exhausted")
        uniform = float(self.loss[self.loss_cursor])
        self.loss_cursor += 1
        value = self.params.pit_loss.sample_unit(uniform)
        if not math.isfinite(value):
            raise _TrajectoryFailure(
                REASON_INVALID_PIT_LOSS,
                f"sampled pit loss is not finite: {value!r}")
        if self.collect:
            self.loss_values.append(value)
        return value

    def _fresh_target(self, compound: str) -> int:
        grid = self.params.grid_for(compound)
        raw = grid.sample_unit(self._next_timing())
        return _pit_target_int(raw, 1, int(grid.observed_max))

    def perform(self, driver: _ScalarDriver) -> dict:
        """Apply one pit and return a descriptive event (never affects draws)."""
        before = driver.compound
        next_compound = self._draw_next_compound(driver.compound)
        loss = self._draw_loss()
        driver.compound = next_compound
        driver.pit_count += 1
        driver.stint_number = driver.pit_count + 1
        driver.race_time_s += loss
        driver.tyre_age = 0
        driver.target_age = self._fresh_target(next_compound)
        if self.collect:
            self.target_values.append(driver.target_age)
        return {
            "driver_id": driver.driver_id,
            "lap": int(driver.lap_number),
            "compound_before": before,
            "compound_after": next_compound,
            "pit_count": int(driver.pit_count),
            "stint_number": int(driver.stint_number),
            "pit_loss_s": float(loss),
            "tyre_age_after_pit": int(driver.tyre_age),
            # The first lap on the new tyre (the out-lap) has tyre age 1:
            # the pinned Phase-1 RaceState convention (out-lap tyre_life==1).
            "out_lap_tyre_age": int(driver.tyre_age) + 1,
            "target_age": int(driver.target_age),
            "race_time_s": float(driver.race_time_s),
        }


def _evolve_scalar(initial_state: SimulationState, selection,
                   sampler: Optional[ResidualSampler], pool,
                   zero_noise: bool,
                   pit: Optional[_ScalarPitRuntime] = None,
                   trace: Optional[List[dict]] = None):
    """Simple per-trajectory event loop: R4 semantics + residual + R6 pits.

    Returns ``(classification, pit_counts)`` so the caller can report R6
    diagnostics without a second traversal. ``trace`` (optional) records
    descriptive pit events for oracle tests and never affects draws.
    """
    scheduled = initial_state.scheduled_laps
    drivers = [
        _ScalarDriver(
            driver_id=entry.driver_id,
            lap_number=entry.lap_number,
            race_time_s=float(entry.race_time_s),
            tyre_age=int(entry.tyre_age),
            anchor_tyre_age=int(entry.tyre_age),
            base_pace_s=(selection.base.value
                         + selection.offset_for(entry.constructor_id).value),
            compound=entry.compound,
            stint_number=(entry.stint_number
                          if entry.stint_number is not None
                          else entry.pit_count + 1),
            pit_count=entry.pit_count,
        )
        for entry in initial_state.drivers
    ]

    if max(driver.lap_number for driver in drivers) >= scheduled:
        return _classify_scalar(drivers), [d.pit_count for d in drivers]

    if pit is not None:
        for driver in drivers:
            driver.target_age = pit.initial_target(driver.tyre_age,
                                                   driver.compound)

    cursor = [0]

    def draw_epsilon() -> float:
        if zero_noise:
            return 0.0
        position = cursor[0]
        if position >= len(pool):
            raise _TrajectoryFailure(
                REASON_ITERATION_LIMIT,
                "residual draw pool exhausted")
        cursor[0] = position + 1
        return sampler.sample_unit(pool[position])

    def schedule(driver: _ScalarDriver) -> None:
        next_lap = driver.lap_number + 1
        next_age = driver.tyre_age + 1
        mu, _, _ = expected_lap_time_s(
            selection, driver.base_pace_s, next_lap, next_age,
            driver.anchor_tyre_age)
        if not math.isfinite(mu):
            raise _TrajectoryFailure(
                REASON_NONFINITE_LAP_TIME,
                f"driver {driver.driver_id!r} lap {next_lap} expected lap "
                f"time is not finite: {mu!r}")
        lap_time = mu + draw_epsilon()
        if not math.isfinite(lap_time):
            raise _TrajectoryFailure(
                REASON_NONFINITE_LAP_TIME,
                f"driver {driver.driver_id!r} lap {next_lap} stochastic lap "
                f"time is not finite: {lap_time!r}")
        if lap_time <= 0.0:
            raise _TrajectoryFailure(
                REASON_NONPOSITIVE_LAP_TIME,
                f"driver {driver.driver_id!r} lap {next_lap} stochastic lap "
                f"time is not positive: {lap_time!r}")
        next_time = driver.race_time_s + lap_time
        if not math.isfinite(next_time) or next_time < 0.0:
            raise _TrajectoryFailure(
                REASON_NONFINITE_RACE_TIME,
                f"driver {driver.driver_id!r} next race time is invalid: "
                f"{next_time!r}")
        driver.next_lap = next_lap
        driver.next_age = next_age
        driver.next_time_s = next_time

    for driver in drivers:
        schedule(driver)

    bound = max_lap_events(len(drivers), scheduled)
    for _ in range(bound):
        active = [driver for driver in drivers if not driver.finished]
        if not active:
            break
        event_time = min(driver.next_time_s for driver in active)
        batch = sorted(
            (driver for driver in active
             if driver.next_time_s == event_time),
            key=lambda driver: driver.driver_id,
        )
        # Pass 1: apply lap completion for the whole batch. (Pace draw order
        # is unchanged from R5 because pass 2 schedules in the same order.)
        for driver in batch:
            driver.lap_number = driver.next_lap
            driver.tyre_age = driver.next_age
            driver.race_time_s = event_time
            if driver.lap_number >= scheduled:
                driver.finished = True
        race_over = any(driver.finished for driver in drivers)
        # Pass 2: pit (if enabled and the race is still running), then
        # reschedule. A pit at the race-end instant is suppressed (R6-AB).
        for driver in batch:
            if driver.finished:
                continue
            if pit is not None and not race_over \
                    and driver.tyre_age >= driver.target_age:
                event = pit.perform(driver)
                if trace is not None:
                    trace.append(event)
            schedule(driver)
        if race_over:
            break
    else:
        raise _TrajectoryFailure(
            REASON_ITERATION_LIMIT,
            f"race did not complete within {bound} lap events")

    return _classify_scalar(drivers), [d.pit_count for d in drivers]


def _simulation_id(initial_state: SimulationState,
                   parameters: SimulationParameterSet,
                   simulation_index: int) -> str:
    return (f"{initial_state.race_id}:{parameters.parameter_version}:"
            f"{initial_state.identity()[:16]}:{simulation_index}")


def _draw_pool(master_seed: int, simulation_index: int, size: int,
               contract_version: str) -> np.ndarray:
    if size <= 0:
        return np.empty(0, dtype=np.float64)
    generator = rng_for_simulation(
        master_seed, simulation_index, contract_version=contract_version)
    return generator.random(size)


def _scalar_trajectory(initial_state: SimulationState,
                       parameters: SimulationParameterSet, selection,
                       sampler: Optional[ResidualSampler], max_draws: int,
                       master_seed: int, simulation_index: int,
                       zero_noise: bool, contract_version: str,
                       pit_params: Optional[PitParameterSet] = None,
                       collect_diagnostics: bool = False,
                       trace: Optional[List[dict]] = None):
    """Run one scalar trajectory; return ``(result, diagnostics_fragment)``."""
    simulation_id = _simulation_id(initial_state, parameters, simulation_index)
    pool = None
    if not zero_noise:
        pool = _draw_pool(master_seed, simulation_index, max_draws,
                          contract_version)
    pit = None
    if pit_params is not None:
        pit = _ScalarPitRuntime(
            pit_params, master_seed, simulation_index,
            initial_state.roster_size, max_draws, contract_version,
            collect_diagnostics)
    try:
        classification, pit_counts = _evolve_scalar(
            initial_state, selection, sampler, pool, zero_noise, pit, trace)
    except _TrajectoryFailure as failure:
        return SimulationRunResult(
            race_id=initial_state.race_id,
            simulation_id=simulation_id,
            simulation_index=simulation_index,
            valid=False,
            invalid_reason=failure.reason,
        ), None
    result = SimulationRunResult(
        race_id=initial_state.race_id,
        simulation_id=simulation_id,
        simulation_index=simulation_index,
        valid=True,
        classification=classification,
    )
    fragment = None
    if pit is not None and collect_diagnostics:
        fragment = {
            "pit_counts": pit_counts,
            "transition_counts": pit.transition_counts,
            "loss_values": pit.loss_values,
            "target_values": pit.target_values,
        }
    return result, fragment


def run_trajectory_scalar(initial_state: SimulationState,
                          parameters: SimulationParameterSet,
                          master_seed: int, simulation_index: int, *,
                          execution_policy: ExecutionPolicy = (
                              ExecutionPolicy.RETROSPECTIVE_PRODUCT),
                          zero_noise: bool = False,
                          pit_dynamics: bool = False,
                          trace: Optional[List[dict]] = None,
                          contract_version: str = SIMULATION_CONTRACT_VERSION
                          ) -> SimulationRunResult:
    """Scalar stochastic oracle for one trajectory (R5-J/K, R6-M).

    Follows R4 event semantics exactly plus the R3 empirical residual draw.
    With ``zero_noise=True`` the residual effect is removed and the
    classification is byte-identical to ``DeterministicRaceEngine``.
    ``pit_dynamics=True`` adds the R6 pit model (R6-M scalar oracle).
    ``trace`` records descriptive pit events for oracle tests.
    """
    selection, sampler = _prepare(initial_state, parameters,
                                  execution_policy, zero_noise)
    pit_params = None
    if pit_dynamics:
        pit_params = select_pit_parameters(initial_state, selection,
                                           parameters)
    max_draws = max_residual_draws(initial_state)
    result, _ = _scalar_trajectory(
        initial_state, parameters, selection, sampler, max_draws, master_seed,
        simulation_index, zero_noise, contract_version, pit_params, False,
        trace)
    return result


# ---------------------------------------------------------------------------
# Chunked / vectorized batch evolution (R5-L/M/N).
# ---------------------------------------------------------------------------

def _clamp_age_array(ages: np.ndarray,
                     support_max: Optional[float]) -> np.ndarray:
    clamped = np.maximum(ages, 0.0)
    if support_max is not None:
        clamped = np.minimum(clamped, float(support_max))
    return clamped


class _ChunkEvolution:
    """Vectorized evolution of one chunk of independent trajectories."""

    def __init__(self, initial_state: SimulationState, selection,
                 sampler: Optional[ResidualSampler], max_draws: int,
                 master_seed: int, indices: List[int], zero_noise: bool,
                 contract_version: str,
                 pit_params: Optional[PitParameterSet] = None,
                 collect_diagnostics: bool = False):
        self.state = initial_state
        self.scheduled = int(initial_state.scheduled_laps)
        self.drivers = initial_state.drivers
        self.D = len(self.drivers)
        self.B = len(indices)
        self.zero_noise = zero_noise
        self.progress_slope = float(selection.progress.value)
        self.degradation_slope = float(selection.degradation.value)
        self.reference_lap = int(selection.reference_lap)
        self.support_max = selection.age_support_max_laps
        self.xp = np.asarray(sampler._xp) if sampler is not None else None
        self.fp = np.asarray(sampler._fp) if sampler is not None else None
        self.pit_params = pit_params
        self.collect = collect_diagnostics
        self.transition_counts: Counter = Counter()
        self.loss_values: List[float] = []
        self.target_values: List[int] = []

        self.base = np.array(
            [selection.base.value
             + selection.offset_for(entry.constructor_id).value
             for entry in self.drivers], dtype=np.float64)
        anchor_age = np.array(
            [float(entry.tyre_age) for entry in self.drivers],
            dtype=np.float64)
        self.anchor_clamped = _clamp_age_array(anchor_age, self.support_max)

        lap0 = np.array([entry.lap_number for entry in self.drivers],
                        dtype=np.int64)
        age0 = np.array([entry.tyre_age for entry in self.drivers],
                        dtype=np.int64)
        rtime0 = np.array([float(entry.race_time_s) for entry in self.drivers],
                          dtype=np.float64)
        self.lap = np.broadcast_to(lap0, (self.B, self.D)).copy()
        self.age = np.broadcast_to(age0, (self.B, self.D)).copy()
        self.rtime = np.broadcast_to(rtime0, (self.B, self.D)).copy()
        self.finished = np.zeros((self.B, self.D), dtype=bool)
        self.initial_done = self.lap.max(axis=1) >= self.scheduled
        self.traj_done = self.initial_done.copy()
        self.invalid = np.zeros(self.B, dtype=bool)
        self.invalid_reason = np.array([""] * self.B, dtype=object)
        self.next_lap = np.zeros((self.B, self.D), dtype=np.int64)
        self.next_age = np.zeros((self.B, self.D), dtype=np.int64)
        self.next_time = np.full((self.B, self.D), np.inf, dtype=np.float64)
        self.max_draws = int(max_draws)

        if zero_noise or self.max_draws <= 0:
            self.pool = None
            self.cursor = None
        else:
            pool = np.empty((self.B, self.max_draws), dtype=np.float64)
            for row, index in enumerate(indices):
                pool[row] = _draw_pool(master_seed, index, self.max_draws,
                                       contract_version)
            self.pool = pool
            self.cursor = np.zeros(self.B, dtype=np.int64)

        # --- R6 pit state (only when pit dynamics is enabled) --------------
        # R7-BUG-1: seed the per-driver pit counter from the factual start
        # count (the scalar oracle already does this at ``_ScalarDriver``).
        # Both counters are descriptive only (never read by scheduling), so
        # the scientific result identity is unchanged; the batch diagnostics
        # now report *total* stops and ``stint_number`` no longer resets on a
        # mid-race start (scalar/batch diagnostic parity).
        pit0 = np.array([entry.pit_count for entry in self.drivers],
                        dtype=np.int64)
        self.pit_count = np.broadcast_to(pit0, (self.B, self.D)).copy()
        stint0 = np.array(
            [entry.stint_number if entry.stint_number is not None
             else entry.pit_count + 1 for entry in self.drivers],
            dtype=np.int64)
        self.stint_number = np.broadcast_to(stint0, (self.B, self.D)).copy()
        compound0 = np.array([entry.compound for entry in self.drivers],
                             dtype=object)
        self.compound = np.broadcast_to(compound0, (self.B, self.D)).copy()
        self.target_age = np.zeros((self.B, self.D), dtype=np.int64)
        if pit_params is not None:
            remaining = self.max_draws
            self.timing_capacity = self.D + remaining
            self.compound_capacity = remaining
            self.loss_capacity = remaining
            self.timing_pool = np.empty((self.B, self.timing_capacity),
                                        dtype=np.float64)
            self.compound_pool = np.empty((self.B, self.compound_capacity),
                                          dtype=np.float64)
            self.loss_pool = np.empty((self.B, self.loss_capacity),
                                      dtype=np.float64)
            for row, index in enumerate(indices):
                self.timing_pool[row] = _draw_domain_pool(
                    master_seed, index, "pit_timing", self.timing_capacity,
                    contract_version)
                self.compound_pool[row] = _draw_domain_pool(
                    master_seed, index, "compound", self.compound_capacity,
                    contract_version)
                self.loss_pool[row] = _draw_domain_pool(
                    master_seed, index, "pit_loss", self.loss_capacity,
                    contract_version)
            self.timing_cursor = np.full(self.B, self.D, dtype=np.int64)
            self.compound_cursor = np.zeros(self.B, dtype=np.int64)
            self.loss_cursor = np.zeros(self.B, dtype=np.int64)
            self.loss_xp = np.asarray(pit_params.pit_loss.xp)
            self.loss_fp = np.asarray(pit_params.pit_loss.fp)
            # Initial conditional stint targets (R6-E): one per driver,
            # canonical order, using each driver's factual tyre age as floor.
            grids = [pit_params.grid_for(entry.compound)
                     for entry in self.drivers]
            base = np.array([grid.cdf(float(entry.tyre_age))
                             for grid, entry in zip(grids, self.drivers)],
                            dtype=np.float64)
            uniforms = self.timing_pool[:, :self.D]
            conditional = base[None, :] + uniforms * (1.0 - base[None, :])
            target = np.empty((self.B, self.D), dtype=np.int64)
            for column, (grid, entry) in enumerate(zip(grids, self.drivers)):
                raw = np.interp(conditional[:, column],
                                np.asarray(grid.xp), np.asarray(grid.fp))
                target[:, column] = _pit_target_int_array(
                    raw, int(entry.tyre_age) + 1, int(grid.observed_max))
            self.target_age = target

    def _invalidate_rows(self, rows, reason: str) -> None:
        for row in rows:
            if not self.invalid[row]:
                self.invalid[row] = True
                self.invalid_reason[row] = reason
            self.traj_done[row] = True

    def _maybe_pit(self, candidate: np.ndarray) -> None:
        """Apply R6 pit events for ``candidate`` drivers (R6-H/I/J)."""
        if self.pit_params is None:
            return
        mask = candidate & (self.age >= self.target_age)
        if not mask.any():
            return
        counts = mask.sum(axis=1)
        overflow = ((self.compound_cursor + counts > self.compound_capacity)
                    | (self.loss_cursor + counts > self.loss_capacity)
                    | (self.timing_cursor + counts > self.timing_capacity))
        if overflow.any():
            self._invalidate_rows(np.where(overflow)[0], REASON_PIT_LOOP)
            mask = mask & ~overflow[:, None]
            if not mask.any():
                return
            counts = mask.sum(axis=1)

        rank = np.cumsum(mask, axis=1) - 1
        safe_compound = np.where(mask, self.compound_cursor[:, None] + rank, 0)
        safe_loss = np.where(mask, self.loss_cursor[:, None] + rank, 0)
        safe_target = np.where(mask, self.timing_cursor[:, None] + rank, 0)
        compound_uniforms = np.take_along_axis(
            self.compound_pool, safe_compound, axis=1)
        loss_uniforms = np.take_along_axis(self.loss_pool, safe_loss, axis=1)
        target_uniforms = np.take_along_axis(
            self.timing_pool, safe_target, axis=1)

        next_compound = self.compound.copy()
        currents = sorted({value for value in self.compound[mask].tolist()},
                          key=lambda value: (value is None, value))
        for current in currents:
            targets, cumulative = self.pit_params.transition_for(current)
            subset = mask & (self.compound == current)
            uniforms = compound_uniforms[subset]
            index = np.searchsorted(np.asarray(cumulative), uniforms,
                                    side="right")
            index = np.clip(index, 0, len(targets) - 1)
            next_compound[subset] = np.asarray(targets, dtype=object)[index]

        loss = np.interp(loss_uniforms, self.loss_xp, self.loss_fp)

        new_target = self.target_age.copy()
        compounds = sorted({value for value in next_compound[mask].tolist()},
                           key=lambda value: (value is None, value))
        for compound in compounds:
            grid = self.pit_params.grid_for(compound)
            subset = mask & (next_compound == compound)
            raw = np.interp(target_uniforms[subset],
                            np.asarray(grid.xp), np.asarray(grid.fp))
            new_target[subset] = _pit_target_int_array(
                raw, 1, int(grid.observed_max))

        if self.collect:
            old_compounds = self.compound[mask].tolist()
            new_compounds = next_compound[mask].tolist()
            loss_samples = loss[mask].tolist()
            target_samples = new_target[mask].tolist()

        self.rtime = np.where(mask, self.rtime + loss, self.rtime)
        self.compound = np.where(mask, next_compound, self.compound)
        self.age = np.where(mask, 0, self.age)
        self.target_age = np.where(mask, new_target, self.target_age)
        self.pit_count = self.pit_count + mask.astype(np.int64)
        self.stint_number = np.where(mask, self.pit_count + 1,
                                     self.stint_number)
        self.compound_cursor = self.compound_cursor + counts
        self.loss_cursor = self.loss_cursor + counts
        self.timing_cursor = self.timing_cursor + counts

        if self.collect:
            for current, target in zip(old_compounds, new_compounds):
                self.transition_counts[f"{current}->{target}"] += 1
            self.loss_values.extend(loss_samples)
            self.target_values.extend(target_samples)

    def _schedule(self, mask: np.ndarray) -> None:
        if not mask.any():
            return
        next_lap = self.lap + 1
        next_age = self.age + 1
        progress_adjustment = self.progress_slope * (
            next_lap - self.reference_lap)
        age_clamped = _clamp_age_array(next_age.astype(np.float64),
                                       self.support_max)
        degradation_adjustment = self.degradation_slope * (
            age_clamped - self.anchor_clamped[None, :])
        mu = (self.base[None, :] + progress_adjustment
              + degradation_adjustment)

        if self.pool is None:
            epsilon = 0.0
        else:
            counts = mask.sum(axis=1)
            if np.any(self.cursor + counts > self.max_draws):
                raise SimulationValidationError(
                    "residual draw pool exhausted; bound "
                    f"{self.max_draws} was insufficient")
            rank = np.cumsum(mask, axis=1) - 1
            draw_index = self.cursor[:, None] + rank
            safe_index = np.where(mask, draw_index, 0)
            uniforms = np.take_along_axis(self.pool, safe_index, axis=1)
            epsilon = np.interp(uniforms, self.xp, self.fp)
            self.cursor = self.cursor + counts

        lap_time = mu + epsilon
        next_time = self.rtime + lap_time

        nonfinite = mask & ~np.isfinite(lap_time)
        nonpositive = mask & np.isfinite(lap_time) & (lap_time <= 0.0)
        bad_clock = (mask & np.isfinite(lap_time) & (lap_time > 0.0)
                     & ~np.isfinite(next_time))
        bad = nonfinite | nonpositive | bad_clock
        if bad.any():
            for row in np.where(bad.any(axis=1))[0]:
                columns = np.where(bad[row])[0]
                first = int(columns[0])
                if (not np.isfinite(mu[row, first])
                        or not np.isfinite(lap_time[row, first])):
                    reason = REASON_NONFINITE_LAP_TIME
                elif lap_time[row, first] <= 0.0:
                    reason = REASON_NONPOSITIVE_LAP_TIME
                else:
                    reason = REASON_NONFINITE_RACE_TIME
                if not self.invalid[row]:
                    self.invalid[row] = True
                    self.invalid_reason[row] = reason
                self.traj_done[row] = True

        good = mask & ~bad
        self.next_lap = np.where(good, next_lap, self.next_lap)
        self.next_age = np.where(good, next_age, self.next_age)
        self.next_time = np.where(good, next_time, self.next_time)

    def run(self) -> None:
        if not self.initial_done.all():
            mask = np.broadcast_to(~self.initial_done[:, None],
                                   (self.B, self.D))
            self._schedule(mask.copy())

        bound = max_lap_events(self.D, self.scheduled)
        for _ in range(bound):
            active = ((~self.finished) & (~self.traj_done[:, None])
                      & (~self.invalid[:, None]))
            if not active.any():
                return
            masked = np.where(active, self.next_time, np.inf)
            event_time = masked.min(axis=1)
            advance = active & (self.next_time == event_time[:, None])
            if not advance.any():
                return
            # Pass 1: apply lap completion for the whole batch. Pace draw
            # order is unchanged from R5 because pass 2 schedules in the
            # same canonical order.
            self.lap = np.where(advance, self.next_lap, self.lap)
            self.age = np.where(advance, self.next_age, self.age)
            self.rtime = np.where(advance, event_time[:, None], self.rtime)
            newly_finished = advance & (self.lap >= self.scheduled)
            self.finished = self.finished | newly_finished
            race_over_rows = newly_finished.any(axis=1)
            # Pass 2: R6 pit events (suppressed when the race just ended in
            # that row, R6-AB), then reschedule. With pits disabled this is
            # exactly the R5 sequence.
            if self.pit_params is not None:
                self._maybe_pit(
                    advance & ~newly_finished & ~race_over_rows[:, None])
            need = advance & ~newly_finished
            self._schedule(need)
            self.traj_done = self.traj_done | race_over_rows

        remaining = ((~self.finished) & (~self.traj_done[:, None])
                     & (~self.invalid[:, None]))
        for row in np.where(remaining.any(axis=1))[0]:
            self.invalid[row] = True
            self.invalid_reason[row] = REASON_ITERATION_LIMIT
            self.traj_done[row] = True


# ---------------------------------------------------------------------------
# Aggregation (R5-S..W, R5-AA).
# ---------------------------------------------------------------------------

def _check_invariants(position_counts: np.ndarray, valid_count: int,
                      field_size: int) -> None:
    if int(position_counts[:, 1].sum()) != valid_count:
        raise SimulationValidationError(
            "winner count total must equal the valid simulation count: "
            f"{int(position_counts[:, 1].sum())} != {valid_count}")
    win_probabilities = position_counts[:, 1] / valid_count
    if abs(float(win_probabilities.sum()) - 1.0) > PROBABILITY_TOLERANCE:
        raise SimulationValidationError(
            "win probabilities must sum to 1 within tolerance, got "
            f"{float(win_probabilities.sum())!r}")
    places = min(PODIUM_POSITIONS, field_size)
    podium_total = int(position_counts[:, 1:places + 1].sum())
    if podium_total != valid_count * places:
        raise SimulationValidationError(
            "podium count total must equal valid_count * podium places: "
            f"{podium_total} != {valid_count * places}")
    if not np.array_equal(position_counts.sum(axis=1),
                          np.full(field_size, valid_count, dtype=np.int64)):
        raise SimulationValidationError(
            "each driver's position counts must total the valid count")


def _build_result(*, initial_state: SimulationState, config: SimulationConfig,
                  assumptions: Assumptions, parameter_identity,
                  position_counts: np.ndarray, valid_count: int,
                  invalid_count: int, invalid_reasons: Counter,
                  samples: List[FinishOrder],
                  runtime_s: float) -> MonteCarloResult:
    field_size = len(initial_state.drivers)
    if valid_count <= 0:
        raise SimulationValidationError(
            "no valid simulation trajectories were produced; invalid "
            f"reasons: {dict(invalid_reasons)}")
    _check_invariants(position_counts, valid_count, field_size)

    summaries = []
    for index, entry in enumerate(initial_state.drivers):
        row = position_counts[index]
        distribution = tuple(
            PositionFrequency(position=position,
                              frequency=float(row[position]) / valid_count)
            for position in range(1, field_size + 1))
        podium_places = min(PODIUM_POSITIONS, field_size)
        podium_probability = float(
            row[1:podium_places + 1].sum()) / valid_count
        expected_finish = float(sum(
            position * (float(row[position]) / valid_count)
            for position in range(1, field_size + 1)))
        summaries.append(DriverSimulationSummary(
            driver_id=entry.driver_id,
            win_probability=float(row[1]) / valid_count,
            podium_probability=podium_probability,
            expected_finish=expected_finish,
            finish_position_distribution=distribution,
        ))

    return MonteCarloResult(
        simulation_request_identity=simulation_request_identity(
            initial_state, config, assumptions, parameter_identity),
        race_id=initial_state.race_id,
        requested_simulation_count=config.simulation_count,
        valid_simulation_count=int(valid_count),
        invalid_simulation_count=int(invalid_count),
        master_seed=config.master_seed,
        parameter_identity=parameter_identity.identity(),
        assumptions_identity=assumptions.identity(),
        driver_summaries=tuple(summaries),
        sample_orders=tuple(samples),
        runtime_s=float(runtime_s),
    )


# ---------------------------------------------------------------------------
# Public engine.
# ---------------------------------------------------------------------------

def _prepare(initial_state: SimulationState,
             parameters: SimulationParameterSet,
             execution_policy: ExecutionPolicy,
             zero_noise: bool):
    selection = select_pace_parameters(initial_state, parameters)
    _validate_start_state(initial_state, selection)
    _validate_temporal(initial_state, parameters, execution_policy, selection)
    sampler = None
    if not zero_noise:
        sampler = select_residual_sampler(parameters, selection.era)
    return selection, sampler


def _require_types(initial_state, parameters, config, assumptions) -> None:
    if not isinstance(initial_state, SimulationState):
        raise SimulationContractError(
            f"initial_state must be a SimulationState, got {initial_state!r}")
    if not isinstance(parameters, SimulationParameterSet):
        raise SimulationContractError(
            f"parameters must be a SimulationParameterSet, got {parameters!r}")
    if not isinstance(config, SimulationConfig):
        raise SimulationContractError(
            f"config must be a SimulationConfig, got {config!r}")
    if not isinstance(assumptions, Assumptions):
        raise SimulationContractError(
            f"assumptions must be an Assumptions, got {assumptions!r}")
    if config.reliability_enabled:
        raise SimulationContractError(
            "reliability/DNF simulation is DEFERRED (R6-R): no empirical "
            "hazard artifact exists. Refusing to fabricate a no-DNF result "
            "with reliability_enabled=True. " + RELIABILITY_DEFERRED_NOTE)


def _finalize_diagnostics(flat_pit_counts: List[int], transition_counts: Counter,
                          loss_values: List[float],
                          target_values: List[int], valid_count: int,
                          field_size: int) -> MonteCarloDiagnostics:
    outcomes = len(flat_pit_counts)
    total = int(sum(flat_pit_counts))
    histogram = Counter(flat_pit_counts)
    if outcomes > 0:
        zero_fraction = histogram.get(0, 0) / outcomes
        ge2_fraction = sum(n for count, n in histogram.items()
                           if count >= 2) / outcomes
    else:
        zero_fraction = 0.0
        ge2_fraction = 0.0
    return MonteCarloDiagnostics(
        mechanics=("pit_dynamics",),
        valid_trajectories=int(valid_count),
        field_size=int(field_size),
        total_pit_events=total,
        mean_pits_per_driver=(total / outcomes) if outcomes else 0.0,
        pit_count_distribution=tuple(sorted(histogram.items())),
        fraction_zero_pits=float(zero_fraction),
        fraction_ge2_pits=float(ge2_fraction),
        compound_transition_counts=tuple(
            sorted(transition_counts.items())),
        pit_loss_sample=_sample_summary(loss_values),
        stint_target_sample=_sample_summary(
            [float(v) for v in target_values]),
    )


class MonteCarloEngine:
    """Stochastic Monte Carlo engine over the R4 deterministic kernel (R5/R6).

    ``run`` evolves trajectories in vectorized chunks; ``run_scalar`` runs the
    simple scalar oracle. Both produce an identical scientific
    ``MonteCarloResult`` for the same ``(state, parameters, config,
    assumptions, execution_policy)``; chunk size is operational only. With
    ``pit_dynamics_enabled`` the R6 pit model is added (R6). Pit diagnostics
    (R6-AE) are exposed via ``last_diagnostics`` when ``collect_diagnostics``
    is requested; they never enter the scientific result identity.
    """

    def __init__(self, *, chunk_size: int = DEFAULT_CHUNK_SIZE) -> None:
        if not isinstance(chunk_size, int) or isinstance(chunk_size, bool) \
                or chunk_size < 1:
            raise SimulationContractError(
                f"chunk_size must be a positive int, got {chunk_size!r}")
        self.chunk_size = chunk_size
        self.last_diagnostics: Optional[MonteCarloDiagnostics] = None

    # -- vectorized batch path ---------------------------------------------

    def run(self, initial_state: SimulationState,
            parameters: SimulationParameterSet, config: SimulationConfig,
            assumptions: Assumptions, *,
            execution_policy: ExecutionPolicy = (
                ExecutionPolicy.RETROSPECTIVE_PRODUCT),
            zero_noise: bool = False,
            collect_diagnostics: bool = False,
            contract_version: str = SIMULATION_CONTRACT_VERSION
            ) -> MonteCarloResult:
        _require_types(initial_state, parameters, config, assumptions)
        selection, sampler = _prepare(initial_state, parameters,
                                      execution_policy, zero_noise)
        pit_params = None
        if config.pit_dynamics_enabled:
            pit_params = select_pit_parameters(initial_state, selection,
                                               parameters)
        collect = bool(collect_diagnostics) and pit_params is not None
        self.last_diagnostics = None
        diagnostic_rows: List[int] = []
        diagnostic_transitions: Counter = Counter()
        diagnostic_losses: List[float] = []
        diagnostic_targets: List[int] = []
        max_draws = max_residual_draws(initial_state)
        parameter_identity = parameters.parameter_identity()
        field_size = initial_state.roster_size
        positions = np.arange(1, field_size + 1)

        position_counts = np.zeros((field_size, field_size + 1),
                                   dtype=np.int64)
        valid_count = 0
        invalid_count = 0
        invalid_reasons: Counter = Counter()
        samples: List[FinishOrder] = []
        sample_limit = config.sample_orders

        started = time.perf_counter()
        for start in range(0, config.simulation_count, self.chunk_size):
            indices = list(range(start, min(start + self.chunk_size,
                                            config.simulation_count)))
            evolution = _ChunkEvolution(
                initial_state, selection, sampler, max_draws,
                config.master_seed, indices, zero_noise, contract_version,
                pit_params, collect)
            evolution.run()

            if collect:
                valid_rows = np.where(~evolution.invalid)[0]
                if len(valid_rows):
                    diagnostic_rows.extend(
                        evolution.pit_count[valid_rows].ravel().tolist())
                diagnostic_transitions.update(evolution.transition_counts)
                diagnostic_losses.extend(evolution.loss_values)
                diagnostic_targets.extend(evolution.target_values)

            valid_rows = np.where(~evolution.invalid)[0]
            if len(valid_rows):
                sub_lap = evolution.lap[valid_rows]
                sub_time = evolution.rtime[valid_rows]
                driver_index = np.broadcast_to(
                    np.arange(field_size), sub_lap.shape)
                order = np.lexsort(
                    (driver_index, sub_time, -sub_lap), axis=1)
                np.add.at(
                    position_counts,
                    (order, np.broadcast_to(positions, order.shape)),
                    1)
                valid_count += len(valid_rows)
                if len(samples) < sample_limit:
                    for local, row in enumerate(valid_rows):
                        if len(samples) >= sample_limit:
                            break
                        ranked = order[local]
                        entries = tuple(
                            DriverFinish(
                                driver_id=initial_state.drivers[
                                    int(ranked[position])].driver_id,
                                classified=True,
                                retired=False,
                                laps_completed=int(
                                    evolution.lap[row, ranked[position]]),
                                race_time_s=float(
                                    evolution.rtime[row, ranked[position]]),
                                finish_position=position + 1,
                            )
                            for position in range(field_size))
                        samples.append(FinishOrder(
                            roster_size=field_size, entries=entries))
            invalid_rows = np.where(evolution.invalid)[0]
            for row in invalid_rows:
                invalid_count += 1
                invalid_reasons[str(evolution.invalid_reason[row])] += 1
        runtime_s = time.perf_counter() - started

        if collect:
            self.last_diagnostics = _finalize_diagnostics(
                diagnostic_rows, diagnostic_transitions, diagnostic_losses,
                diagnostic_targets, valid_count, field_size)

        return _build_result(
            initial_state=initial_state, config=config,
            assumptions=assumptions, parameter_identity=parameter_identity,
            position_counts=position_counts, valid_count=valid_count,
            invalid_count=invalid_count, invalid_reasons=invalid_reasons,
            samples=samples, runtime_s=runtime_s)

    # -- scalar oracle path -------------------------------------------------

    def run_scalar(self, initial_state: SimulationState,
                   parameters: SimulationParameterSet,
                   config: SimulationConfig, assumptions: Assumptions, *,
                   execution_policy: ExecutionPolicy = (
                       ExecutionPolicy.RETROSPECTIVE_PRODUCT),
                   zero_noise: bool = False,
                   collect_diagnostics: bool = False,
                   contract_version: str = SIMULATION_CONTRACT_VERSION
                   ) -> MonteCarloResult:
        _require_types(initial_state, parameters, config, assumptions)
        selection, sampler = _prepare(initial_state, parameters,
                                      execution_policy, zero_noise)
        pit_params = None
        if config.pit_dynamics_enabled:
            pit_params = select_pit_parameters(initial_state, selection,
                                               parameters)
        collect = bool(collect_diagnostics) and pit_params is not None
        self.last_diagnostics = None
        diagnostic_rows: List[int] = []
        diagnostic_transitions: Counter = Counter()
        diagnostic_losses: List[float] = []
        diagnostic_targets: List[int] = []
        max_draws = max_residual_draws(initial_state)
        parameter_identity = parameters.parameter_identity()
        field_size = initial_state.roster_size
        index_by_driver = {
            entry.driver_id: index
            for index, entry in enumerate(initial_state.drivers)}

        position_counts = np.zeros((field_size, field_size + 1),
                                   dtype=np.int64)
        valid_count = 0
        invalid_count = 0
        invalid_reasons: Counter = Counter()
        samples: List[FinishOrder] = []
        sample_limit = config.sample_orders

        started = time.perf_counter()
        for index in range(config.simulation_count):
            result, fragment = _scalar_trajectory(
                initial_state, parameters, selection, sampler, max_draws,
                config.master_seed, index, zero_noise, contract_version,
                pit_params, collect)
            if not result.valid:
                invalid_count += 1
                invalid_reasons[str(result.invalid_reason)] += 1
                continue
            valid_count += 1
            if fragment is not None:
                diagnostic_rows.extend(fragment["pit_counts"])
                diagnostic_transitions.update(fragment["transition_counts"])
                diagnostic_losses.extend(fragment["loss_values"])
                diagnostic_targets.extend(fragment["target_values"])
            for entry in result.classification.entries:
                position_counts[index_by_driver[entry.driver_id],
                                int(entry.finish_position)] += 1
            if len(samples) < sample_limit:
                samples.append(result.classification)
        runtime_s = time.perf_counter() - started

        if collect:
            self.last_diagnostics = _finalize_diagnostics(
                diagnostic_rows, diagnostic_transitions, diagnostic_losses,
                diagnostic_targets, valid_count, field_size)

        return _build_result(
            initial_state=initial_state, config=config,
            assumptions=assumptions, parameter_identity=parameter_identity,
            position_counts=position_counts, valid_count=valid_count,
            invalid_count=invalid_count, invalid_reasons=invalid_reasons,
            samples=samples, runtime_s=runtime_s)
