"""Phase-6 R7 historical validation, calibration and freeze utilities.

EVALUATION ONLY. Everything in this module measures the already-frozen R6
candidate; it never feeds back into a simulated trajectory and never enters
``SimulationState``, the kernel, or a parameter artifact.

Scientific firewalls (pinned by ``tests/test_v2_phase6_r7.py``):
- imports only the stdlib, ``numpy``, and the Phase-6 simulation contracts
  (``state``/``params``/``results``/``engine``/``monte_carlo``);
- imports NO pandas, NO ``v2.prediction``/``v2.model_lab``, NO replay, NO
  canonical data, NO API/frontend;
- historical truth is passed in as plain values and is never written back to
  a simulated input.

Contents:
- a frozen, hashed validation protocol (:class:`R7Protocol`);
- deterministic race and stage-checkpoint selection;
- historical-truth projection from canonical result rows;
- winner / rank / position-distribution / calibration metrics;
- Monte Carlo standard error and race-level bootstrap;
- pit-behaviour comparison metrics;
- residual-sampler audit + variance-matched diagnostic parameter set.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, replace
from typing import Callable, Iterable, Mapping, Optional, Sequence

import numpy as np

from v2.simulation.errors import (
    SimulationContractError,
    SimulationValidationError,
)
from v2.simulation.engine import CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES
from v2.simulation.params import SimulationParameterSet, SupportEntry
from v2.simulation.results import MonteCarloResult
from v2.simulation.state import (
    SimulationState,
    canonical_sha256,
)

__all__ = [
    "R7_VALIDATION_VERSION",
    "R7_EVALUATION_SEASONS",
    "R7_EXCLUDED_SEASONS",
    "R7_STAGE_FRACTIONS",
    "R7_BROAD_COUNT",
    "R7_CALIBRATION_COUNT",
    "R7_MASTER_SEED",
    "R7_BOOTSTRAP_SEED",
    "R7_BOOTSTRAP_REPLICATES",
    "R7_WINNER_LOG_EPSILON",
    "R7_POSITION_LOG_EPSILON",
    "R7_CALIBRATION_BINS",
    "R7_BASELINES",
    "R7_UNSUPPORTED_REASONS",
    "R7_MAX_OBSERVATION_LAP_TIMES",
    "R7_CHECKPOINT_RADIUS_FRACTION",
    "R7_CHECKPOINT_RADIUS_MIN_LAPS",
    "is_contemporaneous",
    "checkpoint_radius_laps",
    "R7Protocol",
    "default_protocol",
    "winner_log_loss",
    "brier_score",
    "top_k_winner_accuracy",
    "ranked_probability_score",
    "position_log_score",
    "expected_finish_mae",
    "spearman_rank_correlation",
    "calibration_bins",
    "expected_calibration_error",
    "monte_carlo_standard_error",
    "race_level_bootstrap",
    "pit_behaviour_metrics",
    "piecewise_linear_variance",
    "residual_sampler_audit",
    "variance_matched_parameter_set",
    "systematic_race_selection",
    "stage_target_laps",
    "checkpoint_search_order",
    "select_checkpoint",
    "historical_truth",
    "current_order",
    "result_win_probabilities",
    "result_expected_finish",
    "result_position_distributions",
    "aggregate_race_macro",
]

# ---------------------------------------------------------------------------
# Frozen protocol identity (R7-B).
# ---------------------------------------------------------------------------

R7_VALIDATION_VERSION = "r7-validation-v1"

#: Seasons actually evaluated. 2018/2019 are excluded: the expanding-window
#: rule leaves <=1 estimation season before them, which cannot support the
#: era-pooled residual/degradation families honestly (R7-C). 2025 is never
#: eligible for any purpose.
R7_EVALUATION_SEASONS = (2020, 2021, 2022, 2023, 2024)
R7_EXCLUDED_SEASONS = (2018, 2019, 2025)

#: Deterministic checkpoints by leader race progress.
R7_STAGE_FRACTIONS = (("EARLY", 0.25), ("MID", 0.50), ("LATE", 0.75))

#: Broad validation and smaller calibration counts (product target).
R7_BROAD_COUNT = 1000
R7_CALIBRATION_COUNT = 10000

R7_MASTER_SEED = 20240101
R7_BOOTSTRAP_SEED = 42
R7_BOOTSTRAP_REPLICATES = 1000

#: Frozen nearest-supported checkpoint search radius (R7-G). A stage is
#: excluded rather than silently substituted by a far-away frame.
R7_CHECKPOINT_RADIUS_FRACTION = 0.10
R7_CHECKPOINT_RADIUS_MIN_LAPS = 3

#: Predeclared clipping for log scores of impossible outcomes.
R7_WINNER_LOG_EPSILON = 1e-6
R7_POSITION_LOG_EPSILON = 1e-6

#: Predeclared calibration bin edges for winner probability.
R7_CALIBRATION_BINS = (
    0.0, 0.01, 0.02, 0.05, 0.10, 0.20, 0.30, 0.40, 0.50, 0.60, 0.70, 0.80,
    0.90, 0.95, 0.99, 1.0,
)

#: Baselines the simulator is compared against (R7-J).
R7_BASELINES = (
    "CURRENT_ORDER",
    "CURRENT_LEADER",
    "GRID_ORDER",
    "R4_DETERMINISTIC",
    "R5_NO_PIT",
)

#: Reasons a (race, stage) is not evaluated (R7-G).
R7_UNSUPPORTED_REASONS = (
    "no_supported_state",
    "missing_scheduled_laps",
    "race_load_error",
    "no_truth_winner",
    "parameter_support_missing",
    "non_contemporaneous_roster_member",
    "no_supported_state_within_radius",
)

#: R7-BUG-2 / R7.1: the frozen R4/R5/R6 kernel evolves every adapted driver as
#: ACTIVE, so a driver whose latest observation is far older than the anchor
#: T (a factual retirement / stopped car) would be simulated from its stale
#: clock and can "finish" ahead of the field. A contemporaneous snapshot is
#: one where every driver was observed within this many expected lap times of
#: T; that is the predeclared R7 support criterion for an honest start state.
#: R7.1 promotes this from an evaluation-side support check to the runtime
#: engine contract, so the single authority is now
#: ``engine.CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES``.
R7_MAX_OBSERVATION_LAP_TIMES = CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES


def is_contemporaneous(state: SimulationState, base_pace_s: float,
                       lap_budget: float = R7_MAX_OBSERVATION_LAP_TIMES
                       ) -> dict:
    """Whether every driver was observed within ``lap_budget`` lap times.

    Returns ``{"contemporaneous": bool, "bound_s": float, "offenders": [...]}``
    where offenders are ``(driver_id, observation_age_s)`` tuples. ``None``
    observation ages are treated as not verifiably stale (the frozen adapter
    always supplies an age, so this is defensive only).
    """
    if not isinstance(state, SimulationState):
        raise SimulationContractError(
            f"state must be a SimulationState, got {state!r}")
    bound = float(base_pace_s) * float(lap_budget)
    if bound <= 0.0 or not math.isfinite(bound):
        raise SimulationValidationError(
            f"base_pace_s must be finite and positive, got {base_pace_s!r}")
    offenders = tuple(
        (driver.driver_id, float(driver.observation_age_s))
        for driver in state.drivers
        if driver.observation_age_s is not None
        and float(driver.observation_age_s) > bound)
    return {"contemporaneous": not offenders, "bound_s": bound,
            "offenders": offenders}


@dataclass(frozen=True)
class R7Protocol:
    """Frozen, machine-readable validation specification (R7-B)."""

    protocol_version: str
    evaluation_seasons: tuple
    excluded_seasons: tuple
    parameter_cutoff_rule: str
    stage_fractions: tuple
    state_selection_rule: str
    simulation_count_broad: int
    simulation_count_calibration: int
    master_seed: int
    checkpoint_radius_fraction: float
    checkpoint_radius_min_laps: int
    calibration_subset_rule: str
    calibration_bins: tuple
    winner_log_epsilon: float
    position_log_epsilon: float
    bootstrap_replicates: int
    bootstrap_seed: int
    baselines: tuple
    unsupported_state_policy: str
    no_2025: bool = True

    def to_dict(self) -> dict:
        return {
            "protocol_version": self.protocol_version,
            "evaluation_seasons": list(self.evaluation_seasons),
            "excluded_seasons": list(self.excluded_seasons),
            "parameter_cutoff_rule": self.parameter_cutoff_rule,
            "stage_fractions": [[name, float(frac)]
                                for name, frac in self.stage_fractions],
            "state_selection_rule": self.state_selection_rule,
            "simulation_count_broad": self.simulation_count_broad,
            "simulation_count_calibration": self.simulation_count_calibration,
            "master_seed": self.master_seed,
            "checkpoint_radius_fraction": self.checkpoint_radius_fraction,
            "checkpoint_radius_min_laps": self.checkpoint_radius_min_laps,
            "calibration_subset_rule": self.calibration_subset_rule,
            "calibration_bins": list(self.calibration_bins),
            "winner_log_epsilon": self.winner_log_epsilon,
            "position_log_epsilon": self.position_log_epsilon,
            "bootstrap_replicates": self.bootstrap_replicates,
            "bootstrap_seed": self.bootstrap_seed,
            "baselines": list(self.baselines),
            "unsupported_state_policy": self.unsupported_state_policy,
            "no_2025": self.no_2025,
        }

    def identity(self) -> str:
        return canonical_sha256(self.to_dict())


def default_protocol() -> R7Protocol:
    """The predeclared R7 protocol used by the validation script."""
    return R7Protocol(
        protocol_version=R7_VALIDATION_VERSION,
        evaluation_seasons=R7_EVALUATION_SEASONS,
        excluded_seasons=R7_EXCLUDED_SEASONS,
        parameter_cutoff_rule="through_season = evaluation_season - 1",
        stage_fractions=R7_STAGE_FRACTIONS,
        state_selection_rule="nearest_supported_frame_by_leader_lap",
        simulation_count_broad=R7_BROAD_COUNT,
        simulation_count_calibration=R7_CALIBRATION_COUNT,
        master_seed=R7_MASTER_SEED,
        checkpoint_radius_fraction=R7_CHECKPOINT_RADIUS_FRACTION,
        checkpoint_radius_min_laps=R7_CHECKPOINT_RADIUS_MIN_LAPS,
        calibration_subset_rule=(
            "per evaluation season, lexicographically-first selected race at "
            "the MID stage"),
        calibration_bins=R7_CALIBRATION_BINS,
        winner_log_epsilon=R7_WINNER_LOG_EPSILON,
        position_log_epsilon=R7_POSITION_LOG_EPSILON,
        bootstrap_replicates=R7_BOOTSTRAP_REPLICATES,
        bootstrap_seed=R7_BOOTSTRAP_SEED,
        baselines=R7_BASELINES,
        unsupported_state_policy=(
            "exclude (race, stage) with a reported reason; never substitute "
            "a more convenient state"),
        no_2025=True,
    )


# ---------------------------------------------------------------------------
# Deterministic race / stage / checkpoint selection (R7-E/F/G).
# ---------------------------------------------------------------------------

def systematic_race_selection(race_ids: Iterable[str],
                              per_season_target: int = 6) -> tuple:
    """Deterministic systematic sample of one season's race ids.

    Sorted lexicographically, then every ``step``-th id is taken so the
    sample spreads across the calendar without inspecting simulator output.
    ``step = max(1, len(ids) // per_season_target)``.
    """
    ordered = sorted(race_ids)
    if not ordered:
        return ()
    if per_season_target < 1:
        raise SimulationValidationError(
            f"per_season_target must be >= 1, got {per_season_target!r}")
    step = max(1, len(ordered) // per_season_target)
    return tuple(ordered[::step])


def stage_target_laps(scheduled_laps: int,
                      protocol: R7Protocol = None) -> dict:
    """Predeclared target leader lap for each stage."""
    protocol = protocol or default_protocol()
    if type(scheduled_laps) is not int or scheduled_laps < 1:
        raise SimulationValidationError(
            f"scheduled_laps must be a positive int, got {scheduled_laps!r}")
    return {
        name: max(1, int(round(fraction * scheduled_laps)))
        for name, fraction in protocol.stage_fractions
    }


def checkpoint_radius_laps(scheduled_laps: int,
                           protocol: R7Protocol = None) -> int:
    """Frozen maximum leader-lap distance for a stage checkpoint (R7-G)."""
    protocol = protocol or default_protocol()
    if type(scheduled_laps) is not int or scheduled_laps < 1:
        raise SimulationValidationError(
            f"scheduled_laps must be a positive int, got {scheduled_laps!r}")
    return max(protocol.checkpoint_radius_min_laps,
               int(round(protocol.checkpoint_radius_fraction
                         * scheduled_laps)))


def checkpoint_search_order(frames_meta: Iterable[tuple],
                            target_lap: int,
                            radius_laps: int | None = None) -> tuple:
    """Order ``(frame_index, leader_lap)`` by distance from the target.

    Frozen tie-break: ``(|leader_lap - target|, leader_lap, frame_index)``.
    When ``radius_laps`` is given, frames outside the radius are dropped so a
    stage is excluded rather than substituted by a far-away frame.
    """
    if type(target_lap) is not int or target_lap < 1:
        raise SimulationValidationError(
            f"target_lap must be a positive int, got {target_lap!r}")
    candidates = ((int(index), int(lap)) for index, lap in frames_meta)
    if radius_laps is not None:
        if type(radius_laps) is not int or radius_laps < 0:
            raise SimulationValidationError(
                f"radius_laps must be a non-negative int, got {radius_laps!r}")
        candidates = (item for item in candidates
                      if abs(item[1] - target_lap) <= radius_laps)
    return tuple(sorted(
        candidates,
        key=lambda item: (abs(item[1] - target_lap), item[1], item[0])))


def select_checkpoint(candidates: Sequence[Mapping], target_lap: int):
    """First supported candidate in the frozen distance order.

    ``candidates`` is an already-ordered sequence of mappings with
    ``frame_index``, ``leader_lap`` and ``supported``. Returns
    ``(chosen, reason)`` where ``chosen`` is the successful mapping or None
    and ``reason`` is ``None`` or a :data:`R7_UNSUPPORTED_REASONS` token.
    This function never rebuilds or substitutes a state.
    """
    if type(target_lap) is not int or target_lap < 1:
        raise SimulationValidationError(
            f"target_lap must be a positive int, got {target_lap!r}")
    for candidate in candidates:
        if candidate.get("supported"):
            return candidate, None
    return None, "no_supported_state"


# ---------------------------------------------------------------------------
# Historical truth (R7-I). Evaluation-only; never a simulation input.
# ---------------------------------------------------------------------------

def historical_truth(rows: Iterable[Mapping], roster_driver_ids: Sequence[str]
                     ) -> dict:
    """Project canonical post-race result rows into an evaluation truth.

    ``rows`` are plain mappings (e.g. ``DataFrame.to_dict("records")``) with
    ``driver_id``, ``position_final``, ``dnf_flag``, ``winner_flag`` and
    ``grid_position``. Only the requested roster is retained. DNF drivers get
    ``position=None`` and are excluded from the classified set.

    Raises when the roster cannot produce exactly one winner.
    """
    roster = tuple(roster_driver_ids)
    if not roster:
        raise SimulationContractError("roster_driver_ids must be non-empty")
    by_driver = {}
    for row in rows:
        driver_id = row.get("driver_id")
        if driver_id is None:
            continue
        by_driver[str(driver_id)] = row
    missing = [driver for driver in roster if driver not in by_driver]
    if missing:
        raise SimulationValidationError(
            f"historical results missing roster drivers: {missing}")

    positions: dict = {}
    dnf: dict = {}
    grid: dict = {}
    winners = []
    for driver in roster:
        row = by_driver[driver]
        raw_dnf = row.get("dnf_flag")
        is_dnf = bool(raw_dnf) if raw_dnf is not None else False
        dnf[driver] = is_dnf
        position = row.get("position_final")
        position = None if position is None or _is_nan(position) \
            else int(position)
        positions[driver] = position
        raw_grid = row.get("grid_position")
        grid[driver] = None if raw_grid is None or _is_nan(raw_grid) \
            else int(raw_grid)
        if bool(row.get("winner_flag")) or position == 1:
            winners.append(driver)
    winners = sorted(set(winners))
    if len(winners) != 1:
        raise SimulationValidationError(
            f"historical truth must contain exactly one winner, got "
            f"{winners!r}")
    classified = tuple(
        driver for driver in roster
        if not dnf[driver] and positions[driver] is not None)
    classified_positions = [positions[d] for d in classified]
    if len(set(classified_positions)) != len(classified_positions):
        raise SimulationValidationError(
            "historical classified positions must be unique, got "
            f"{sorted(classified_positions)!r}")
    if any(position < 1 for position in classified_positions):
        raise SimulationValidationError(
            "historical classified positions must be >= 1, got "
            f"{sorted(classified_positions)!r}")
    return {
        "winner_driver_id": winners[0],
        "position_by_driver": positions,
        "dnf_by_driver": dnf,
        "grid_by_driver": grid,
        "classified_driver_ids": classified,
    }


def _is_nan(value: object) -> bool:
    try:
        return bool(np.isnan(value))
    except (TypeError, ValueError):
        return False


# ---------------------------------------------------------------------------
# Baseline / result projections.
# ---------------------------------------------------------------------------

def current_order(state: SimulationState) -> tuple:
    """Free-air factual running order at T: (laps DESC, time ASC, id)."""
    if not isinstance(state, SimulationState):
        raise SimulationContractError(
            f"state must be a SimulationState, got {state!r}")
    ordered = sorted(
        state.drivers,
        key=lambda entry: (-entry.lap_number, entry.race_time_s,
                           entry.driver_id))
    return tuple(entry.driver_id for entry in ordered)


def result_win_probabilities(result: MonteCarloResult) -> dict:
    """Per-driver win probability from a Monte Carlo aggregate."""
    if not isinstance(result, MonteCarloResult):
        raise SimulationContractError(
            f"result must be a MonteCarloResult, got {result!r}")
    return {summary.driver_id: float(summary.win_probability)
            for summary in result.driver_summaries}


def result_expected_finish(result: MonteCarloResult) -> dict:
    return {summary.driver_id: float(summary.expected_finish)
            for summary in result.driver_summaries}


def result_position_distributions(result: MonteCarloResult) -> dict:
    """``driver_id -> {position: probability}`` from the aggregate."""
    out = {}
    for summary in result.driver_summaries:
        out[summary.driver_id] = {
            int(freq.position): float(freq.frequency)
            for freq in summary.finish_position_distribution
            if freq.position is not None}
    return out


def one_hot_win_probabilities(state: SimulationState,
                              winner_driver_id: str) -> dict:
    """Deterministic baseline winner distribution (one-hot)."""
    ids = current_order(state)
    if winner_driver_id not in ids:
        raise SimulationValidationError(
            f"baseline winner {winner_driver_id!r} not in roster")
    return {driver: (1.0 if driver == winner_driver_id else 0.0)
            for driver in ids}


# ---------------------------------------------------------------------------
# Winner metrics (R7-K).
# ---------------------------------------------------------------------------

def winner_log_loss(win_probability_by_driver: Mapping[str, float],
                    actual_winner_id: str,
                    epsilon: float = R7_WINNER_LOG_EPSILON) -> float:
    """``-log(p_actual)`` with the predeclared epsilon clip (R7-M/N)."""
    if actual_winner_id not in win_probability_by_driver:
        raise SimulationValidationError(
            f"actual winner {actual_winner_id!r} is not in the field")
    p = float(win_probability_by_driver[actual_winner_id])
    p = min(max(p, epsilon), 1.0)
    return float(-math.log(p))


def brier_score(win_probability_by_driver: Mapping[str, float],
                actual_winner_id: str) -> float:
    """Mean multiclass Brier over the field (R7-K)."""
    if actual_winner_id not in win_probability_by_driver:
        raise SimulationValidationError(
            f"actual winner {actual_winner_id!r} is not in the field")
    drivers = list(win_probability_by_driver)
    if not drivers:
        raise SimulationValidationError("field must be non-empty")
    total = 0.0
    for driver in drivers:
        y = 1.0 if driver == actual_winner_id else 0.0
        p = float(win_probability_by_driver[driver])
        total += (p - y) ** 2
    return total / len(drivers)


def top_k_winner_accuracy(win_probability_by_driver: Mapping[str, float],
                          actual_winner_id: str, k: int = 1) -> bool:
    if k < 1:
        raise SimulationValidationError(f"k must be >= 1, got {k!r}")
    ranked = sorted(win_probability_by_driver,
                    key=lambda d: (-win_probability_by_driver[d], d))
    return actual_winner_id in ranked[:k]


# ---------------------------------------------------------------------------
# Position-distribution / rank metrics (R7-L/M).
# ---------------------------------------------------------------------------

def ranked_probability_score(position_distribution: Mapping[int, float],
                             actual_position: int) -> float:
    """Normalized RPS over positions ``1..K`` (R7-L)."""
    if not position_distribution:
        raise SimulationValidationError("position distribution is empty")
    positions = sorted(position_distribution)
    if positions != list(range(1, len(positions) + 1)):
        raise SimulationValidationError(
            f"position distribution must cover 1..K, got {positions!r}")
    if actual_position not in range(1, len(positions) + 1):
        raise SimulationValidationError(
            f"actual position {actual_position!r} outside 1..K")
    total = sum(float(position_distribution[p]) for p in positions)
    if total <= 0.0:
        raise SimulationValidationError(
            "position distribution probabilities must be positive")
    k = len(positions)
    if k == 1:
        return 0.0
    cumulative_pred = 0.0
    score = 0.0
    for p in positions[:-1]:
        cumulative_pred += float(position_distribution[p]) / total
        cumulative_actual = 1.0 if p >= actual_position else 0.0
        score += (cumulative_pred - cumulative_actual) ** 2
    return score / (k - 1)


def position_log_score(position_distribution: Mapping[int, float],
                       actual_position: int,
                       epsilon: float = R7_POSITION_LOG_EPSILON) -> float:
    if actual_position not in position_distribution:
        raise SimulationValidationError(
            f"actual position {actual_position!r} not in distribution")
    total = sum(float(v) for v in position_distribution.values())
    if total <= 0.0:
        raise SimulationValidationError(
            "position distribution probabilities must be positive")
    p = float(position_distribution[actual_position]) / total
    return float(-math.log(min(max(p, epsilon), 1.0)))


def expected_finish_mae(expected_finish_by_driver: Mapping[str, float],
                        actual_position_by_driver: Mapping[str, int],
                        classified_driver_ids: Sequence[str]) -> float:
    """Mean absolute expected-finish error over classified truth drivers."""
    drivers = list(classified_driver_ids)
    if not drivers:
        raise SimulationValidationError("no classified drivers to evaluate")
    errors = []
    for driver in drivers:
        if driver not in expected_finish_by_driver:
            raise SimulationValidationError(
                f"expected finish missing for classified driver {driver!r}")
        errors.append(abs(float(expected_finish_by_driver[driver])
                          - int(actual_position_by_driver[driver])))
    return float(np.mean(errors))


def _average_ranks(values: Sequence[float]) -> np.ndarray:
    """Average ranks (1-based) with ties, deterministic."""
    order = sorted(range(len(values)), key=lambda i: (values[i], i))
    ranks = np.empty(len(values), dtype=np.float64)
    index = 0
    while index < len(order):
        end = index
        while (end + 1 < len(order)
               and values[order[end + 1]] == values[order[index]]):
            end += 1
        average = (index + end) / 2.0 + 1.0
        for position in range(index, end + 1):
            ranks[order[position]] = average
        index = end + 1
    return ranks


def spearman_rank_correlation(predicted_by_driver: Mapping[str, float],
                              actual_position_by_driver: Mapping[str, int],
                              classified_driver_ids: Sequence[str]) -> float:
    """Spearman correlation between predicted and actual finishing order."""
    drivers = list(classified_driver_ids)
    if len(drivers) < 2:
        return float("nan")
    predicted = [float(predicted_by_driver[d]) for d in drivers]
    actual = [int(actual_position_by_driver[d]) for d in drivers]
    rank_pred = _average_ranks(predicted)
    rank_actual = _average_ranks(actual)
    if rank_pred.std() == 0.0 or rank_actual.std() == 0.0:
        return float("nan")
    return float(np.corrcoef(rank_pred, rank_actual)[0, 1])


# ---------------------------------------------------------------------------
# Calibration (R7-N).
# ---------------------------------------------------------------------------

def calibration_bins(probabilities: Sequence[float],
                     outcomes: Sequence[int],
                     edges: Sequence[float] = R7_CALIBRATION_BINS) -> tuple:
    """Reliability bins; returns per-bin counts and means (R7-N)."""
    if len(probabilities) != len(outcomes):
        raise SimulationValidationError(
            "probabilities and outcomes must have equal length")
    bins = []
    for lower, upper in zip(edges, edges[1:]):
        bins.append({"lo": float(lower), "hi": float(upper),
                     "count": 0, "sum_p": 0.0, "sum_y": 0.0})
    for p_raw, y_raw in zip(probabilities, outcomes):
        p = float(p_raw)
        if not 0.0 <= p <= 1.0:
            raise SimulationValidationError(
                f"probability outside [0,1]: {p!r}")
        y = 1 if y_raw else 0
        index = int(np.searchsorted(edges, p, side="right")) - 1
        if index < 0:
            index = 0
        if index >= len(bins):
            index = len(bins) - 1
        bins[index]["count"] += 1
        bins[index]["sum_p"] += p
        bins[index]["sum_y"] += y
    out = []
    for entry in bins:
        count = entry["count"]
        out.append({
            "lo": entry["lo"],
            "hi": entry["hi"],
            "count": count,
            "mean_probability": (entry["sum_p"] / count) if count else None,
            "empirical_rate": (entry["sum_y"] / count) if count else None,
        })
    return tuple(out)


def expected_calibration_error(bins: Sequence[Mapping]) -> float:
    """Count-weighted ECE over precomputed calibration bins."""
    total = sum(int(b["count"]) for b in bins)
    if total == 0:
        return 0.0
    error = 0.0
    for b in bins:
        count = int(b["count"])
        if count == 0:
            continue
        if b["mean_probability"] is None or b["empirical_rate"] is None:
            continue
        error += (count / total) * abs(
            float(b["empirical_rate"]) - float(b["mean_probability"]))
    return float(error)


# ---------------------------------------------------------------------------
# Monte Carlo uncertainty (R7-O) and bootstrap (R7-W).
# ---------------------------------------------------------------------------

def monte_carlo_standard_error(probability: float, count: int) -> float:
    if count <= 0:
        raise SimulationValidationError(f"count must be > 0, got {count!r}")
    p = float(probability)
    return float(math.sqrt(max(p * (1.0 - p), 0.0) / count))


def race_level_bootstrap(values: Sequence[float], *,
                         replicates: int = R7_BOOTSTRAP_REPLICATES,
                         seed: int = R7_BOOTSTRAP_SEED) -> dict:
    """Percentile CI over race-level metric values (never driver rows)."""
    samples = [float(v) for v in values if v is not None
               and math.isfinite(float(v))]
    if not samples:
        return {"count": 0, "mean": None, "ci95_low": None, "ci95_high": None}
    generator = random.Random(seed)
    n = len(samples)
    means = []
    for _ in range(int(replicates)):
        draw = [samples[generator.randrange(n)] for _ in range(n)]
        means.append(sum(draw) / n)
    means.sort()
    low_index = int(0.025 * (len(means) - 1))
    high_index = int(0.975 * (len(means) - 1))
    return {
        "count": n,
        "mean": float(sum(samples) / n),
        "ci95_low": float(means[low_index]),
        "ci95_high": float(means[high_index]),
    }


# ---------------------------------------------------------------------------
# Pit-behaviour validation (R7-Q/R).
# ---------------------------------------------------------------------------

def pit_behaviour_metrics(simulated_counts: Sequence[int],
                          historical_counts: Sequence[int]) -> dict:
    """Compare stop-count samples (simulated vs factual, same definition)."""
    sim = [int(v) for v in simulated_counts]
    hist = [int(v) for v in historical_counts]
    if not sim or not hist:
        raise SimulationValidationError("no stop counts to compare")

    def fractions(values):
        n = len(values)
        return {
            "zero": sum(1 for v in values if v == 0) / n,
            "one": sum(1 for v in values if v == 1) / n,
            "ge2": sum(1 for v in values if v >= 2) / n,
        }

    bins = sorted(set(sim) | set(hist))
    total_variation = 0.5 * sum(
        abs(sum(1 for v in sim if v == b) / len(sim)
            - sum(1 for v in hist if v == b) / len(hist))
        for b in bins)
    return {
        "sample_count": len(sim),
        "simulated_mean": float(np.mean(sim)),
        "historical_mean": float(np.mean(hist)),
        "mean_difference": float(np.mean(sim) - np.mean(hist)),
        "simulated_fractions": fractions(sim),
        "historical_fractions": fractions(hist),
        "stop_count_total_variation": float(total_variation),
    }


# ---------------------------------------------------------------------------
# Residual sampler audit + diagnostic alternative (R7-S/T).
# ---------------------------------------------------------------------------

def piecewise_linear_variance(xp: Sequence[float],
                              fp: Sequence[float]) -> float:
    """Exact variance of a piecewise-linear quantile function on U(0,1).

    ``Var = ∫0^1 (Q(u) - mean)^2 du`` evaluated segment-wise: for a segment
    ``(u0,q0)-(u1,q1)``, ``∫Q = Δu(q0+q1)/2`` and
    ``∫Q² = Δu(q0²+q0q1+q1²)/3``.
    """
    if len(xp) != len(fp) or len(xp) < 2:
        raise SimulationValidationError("xp/fp must be equal length >= 2")
    mean = 0.0
    second = 0.0
    for u0, u1, q0, q1 in zip(xp, xp[1:], fp, fp[1:]):
        delta = float(u1) - float(u0)
        if delta < 0.0:
            raise SimulationValidationError("xp must be non-decreasing")
        mean += delta * (q0 + q1) / 2.0
        second += delta * (q0 * q0 + q0 * q1 + q1 * q1) / 3.0
    return float(second - mean * mean)


def residual_sampler_audit(parameters: SimulationParameterSet, era: str
                           ) -> dict:
    """Compare the artifact's stored residual std to the sampler grid std.

    Returns the artifact ``std`` (raw-sample diagnostic), the grid-implied
    std (piecewise-linear quantile function), and a dense Monte Carlo sample
    std of the actual sampler, plus endpoint/ratio diagnostics.
    """
    from v2.simulation.monte_carlo import select_residual_sampler

    sampler = select_residual_sampler(parameters, era)
    entry = parameters.family("lap_residual_distribution_s").entries[sampler.key]
    grid_variance = piecewise_linear_variance(sampler._xp, sampler._fp)
    grid_std = math.sqrt(max(grid_variance, 0.0))
    generator = np.random.default_rng(0)
    draws = sampler.sample(generator.random(2_000_000))
    sampled_std = float(np.std(draws))
    artifact_std = float(entry.std) if entry.std is not None else None
    return {
        "era": era,
        "key": sampler.key,
        "sample_count": int(sampler.sample_count),
        "support_level": sampler.support_level,
        "fallback_level": sampler.fallback_level,
        "observed_min": sampler.observed_min,
        "observed_max": sampler.observed_max,
        "endpoint_gap_lower": float(sampler.quantile_values[0]
                                    - sampler.observed_min),
        "endpoint_gap_upper": float(sampler.observed_max
                                    - sampler.quantile_values[-1]),
        "artifact_std": artifact_std,
        "grid_std": grid_std,
        "sampled_std": sampled_std,
        "sampled_to_artifact_ratio": (
            sampled_std / artifact_std if artifact_std else None),
    }


def variance_matched_parameter_set(
        parameters: SimulationParameterSet) -> SimulationParameterSet:
    """Diagnostic copy whose residual grids match their stored std.

    R7-T only: each ``lap_residual_distribution_s`` entry is linearly scaled
    so the piecewise-linear quantile function's variance equals the artifact's
    stored sample variance. Used to bound the materiality of the R7-S
    discrepancy; it NEVER replaces the production artifact.
    """
    if not isinstance(parameters, SimulationParameterSet):
        raise SimulationContractError(
            "parameters must be a SimulationParameterSet")
    family = parameters.family("lap_residual_distribution_s")
    new_entries = {}
    for key, entry in family.entries.items():
        if not entry.is_distribution or entry.std is None \
                or entry.std <= 0.0:
            new_entries[key] = entry
            continue
        lower = (float(entry.observed_min) if entry.observed_min is not None
                 else float(entry.quantile_values[0]))
        upper = (float(entry.observed_max) if entry.observed_max is not None
                 else float(entry.quantile_values[-1]))
        grid_std = math.sqrt(max(piecewise_linear_variance(
            (0.0,) + tuple(entry.probabilities) + (1.0,),
            (lower,) + tuple(float(q) for q in entry.quantile_values)
            + (upper,)), 0.0))
        if grid_std <= 0.0:
            new_entries[key] = entry
            continue
        scale = float(entry.std) / grid_std
        new_entries[key] = replace(
            entry,
            quantile_values=tuple(float(q) * scale
                                  for q in entry.quantile_values),
            observed_min=(None if entry.observed_min is None
                          else float(entry.observed_min) * scale),
            observed_max=(None if entry.observed_max is None
                          else float(entry.observed_max) * scale),
        )
    new_family = replace(family, entries=new_entries)
    families = dict(parameters.families)
    families["lap_residual_distribution_s"] = new_family
    return replace(parameters, families=families)


# ---------------------------------------------------------------------------
# Aggregation (R7-K/P).
# ---------------------------------------------------------------------------

def aggregate_race_macro(records: Sequence[Mapping],
                         metric: str,
                         group_key: Optional[str] = None) -> dict:
    """Mean of a per-state metric, optionally stratified by ``group_key``.

    Race-macro means treat each evaluated (race, stage) as one observation, so
    pooled driver rows never dominate the headline.
    """
    def collect(items):
        values = [float(item[metric]) for item in items
                  if item.get(metric) is not None
                  and math.isfinite(float(item[metric]))]
        if not values:
            return {"count": 0, "mean": None}
        return {"count": len(values),
                "mean": float(sum(values) / len(values))}

    if group_key is None:
        return collect(records)
    groups: dict = {}
    for record in records:
        groups.setdefault(str(record.get(group_key)), []).append(record)
    return {key: collect(items) for key, items in sorted(groups.items())}
