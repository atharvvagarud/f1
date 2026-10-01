"""V2 strategy application service (Phase-7 S7).

Narrow product orchestration over the frozen Phase-4 race-state authority,
the frozen Phase-6 Monte Carlo runtime/parameters, and the frozen S1–S6
Strategy layer:

    exact anchor -> RaceState (Phase-4) -> SimulationState (R2 adapter)
    -> frozen through-2024 parameters -> S4 compare_strategies
    -> S5 objective/uncertainty analysis -> compact API projection

Design rules (S7):
- No Strategy science lives here: no candidate semantics, no CRN policy, no
  delta estimand, no bootstrap, no objective semantics, no simulation
  dynamics. This module only validates product controls, composes frozen
  contracts, and projects the result.
- The exact historical anchor is authoritative (no nearest/interpolation).
- ``master_seed=None`` resolves to the deterministic R7 validation seed; the
  resolved seed is echoed in the response.
- ``candidates=None`` resolves to the neutral ≤4 product set (coverage, not
  performance). An explicit list is validated for duplicates and bounded
  against the S6 latency policy.
- Per-index outcomes never leave this process: the projection carries
  aggregates, paired deltas and selected-objective uncertainty only.
"""

from __future__ import annotations

import functools
import time
from pathlib import Path

import pandas as pd

from raceintel.race_state import race_state as RS
from raceintel.simulation import (
    Assumptions,
    ExecutionPolicy,
    SimulationConfig,
    SimulationParameterSet,
)
from raceintel.simulation.adapter import from_race_state
from raceintel.simulation.config import MAX_MASTER_SEED
from raceintel.simulation.monte_carlo import DEFAULT_CHUNK_SIZE
from raceintel.simulation.results import PROBABILITY_SEMANTICS
from raceintel.strategy.candidates import CANONICAL_CANDIDATE_SPECS
from raceintel.strategy.comparison import (
    COMPARISON_VERSION,
    COUNTERFACTUAL_SEMANTICS,
    CRN_POLICY,
    compare_strategies,
)
from raceintel.strategy.contracts import (
    INTERVENTION_VERSION,
    STRATEGY_CONTRACT_VERSION,
)
from raceintel.strategy.objectives import (
    OBJECTIVE_VERSION,
    STRATEGY_OBJECTIVES,
    evaluate_objective,
    objective_metric,
)
from raceintel.strategy.uncertainty import UNCERTAINTY_VERSION, candidate_uncertainty
from raceintel.race_state.race_state_reconstruction import RaceNotFoundError

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: Product strategy simulation-count policy. The Phase-6 simulator allows
#: 1..10000, but S6 measured full 9-candidate/1k comparisons at ~10–35 s and
#: 10k/3-candidate at ~35–142 s, so S7 narrows the product floor to keep the
#: default path practical while preserving the Phase-6 ceiling.
MIN_SIMULATION_COUNT = 100
DEFAULT_SIMULATION_COUNT = 1000
MAX_SYNCHRONOUS_SIMULATIONS = 10000

#: Deterministic default seed (the R7 validation seed). Requests may override
#: it; the resolved seed is echoed in every response.
DEFAULT_MASTER_SEED = 20240101

#: Production parameter artifact is the frozen R3 through-2024 estimation.
PRODUCTION_PARAMETER_SEASON = 2024

#: Neutral default candidate set (product coverage, never performance): stay
#: out, immediate pit with sampled compound, immediate pit with an explicit
#: compound example, delayed pit with sampled compound. ``None`` = sampled
#: (baseline-drawn) compound.
DEFAULT_STRATEGY_CANDIDATES: tuple = (
    ("STAY_OUT", None),
    ("PIT_NOW", None),
    ("PIT_NOW", "MEDIUM"),
    ("PIT_NEXT_LAP", None),
)

#: Visible UI initial objective value. The request schema still requires an
#: explicit objective; this constant only documents which value the frontend
#: preselects (visible, editable, explicitly submitted).
DEFAULT_OBJECTIVE = "MAXIMIZE_WIN_PROBABILITY"

#: Synchronous safety caps from the S6 latency evidence (finding F2): 10k is
#: explicit advanced/manual with a small candidate set; 1k may run the full
#: canonical 9 only when explicitly requested.
MAX_CANDIDATES_AT_10K = 3
MAX_CANDIDATES_SYNCHRONOUS = len(CANONICAL_CANDIDATE_SPECS)

_HEAVY_COUNT_THRESHOLD = 1000


class StrategyParameterUnavailableError(RuntimeError):
    """The frozen production parameter artifact is missing or corrupt."""


class StrategyRequestError(ValueError):
    """A product-level request validation failure (maps to 422)."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail or reason


def resolve_candidate_specs(
        candidates: list | tuple | None) -> list[tuple[str, str | None]]:
    """Normalize the request candidate list to ``(action, compound)`` specs."""
    if candidates is None:
        return list(DEFAULT_STRATEGY_CANDIDATES)
    specs = []
    for entry in candidates:
        if isinstance(entry, dict):
            specs.append((entry["action"], entry.get("requested_compound")))
        else:
            specs.append((getattr(entry, "action"),
                          getattr(entry, "requested_compound")))
    return specs


def validate_strategy_request(*, simulation_count: int,
                              candidate_specs: list,
                              objective: str,
                              master_seed: int | None) -> None:
    """Product-bound validation before any expensive execution."""
    if objective not in STRATEGY_OBJECTIVES:
        raise StrategyRequestError(
            "unknown_objective",
            f"objective must be one of {list(STRATEGY_OBJECTIVES)}, "
            f"got {objective!r}")
    if master_seed is not None and not 0 <= master_seed <= MAX_MASTER_SEED:
        raise StrategyRequestError(
            "seed_out_of_bounds",
            f"master_seed must be within 0..{MAX_MASTER_SEED}")
    keys = [f"{action}:{compound or 'SAMPLED'}"
            for action, compound in candidate_specs]
    if len(set(keys)) != len(keys):
        raise StrategyRequestError(
            "duplicate_candidates",
            "candidate selection contains duplicates; "
            "each (action, compound) may appear once")
    if len(candidate_specs) > MAX_CANDIDATES_SYNCHRONOUS:
        raise StrategyRequestError(
            "too_many_candidates",
            f"at most {MAX_CANDIDATES_SYNCHRONOUS} candidates synchronously")
    if not candidate_specs:
        raise StrategyRequestError(
            "no_candidates", "select at least one candidate")
    if (simulation_count >= MAX_SYNCHRONOUS_SIMULATIONS
            and len(candidate_specs) > MAX_CANDIDATES_AT_10K):
        raise StrategyRequestError(
            "candidate_count_limit",
            f"{MAX_SYNCHRONOUS_SIMULATIONS}-trial comparisons allow at most "
            f"{MAX_CANDIDATES_AT_10K} candidates synchronously")
    if (simulation_count > _HEAVY_COUNT_THRESHOLD
            and simulation_count < MAX_SYNCHRONOUS_SIMULATIONS
            and len(candidate_specs) > MAX_CANDIDATES_AT_10K):
        raise StrategyRequestError(
            "candidate_count_limit",
            f"comparisons above {_HEAVY_COUNT_THRESHOLD} trials allow at most "
            f"{MAX_CANDIDATES_AT_10K} candidates synchronously")


class V2StrategyService:
    """Reusable, read-only Phase-7 product strategy orchestration."""

    def __init__(self, states: pd.DataFrame, reconstructor,
                 served_race_ids, parameters: SimulationParameterSet, *,
                 chunk_size: int = DEFAULT_CHUNK_SIZE):
        if not isinstance(states, pd.DataFrame):
            raise ValueError(f"states must be a DataFrame, got {type(states)}")
        if not isinstance(parameters, SimulationParameterSet):
            raise TypeError(
                "parameters must be a SimulationParameterSet, "
                f"got {type(parameters)}")
        self._states = states
        self._reconstructor = reconstructor
        self._served = tuple(served_race_ids)
        self._parameters = parameters
        self._chunk_size = int(chunk_size)

    @property
    def race_ids(self) -> tuple:
        return self._served

    @property
    def parameters(self) -> SimulationParameterSet:
        return self._parameters

    def _require_race(self, race_id: str) -> None:
        if race_id not in self._served:
            raise RaceNotFoundError(race_id)

    def run_comparison(
            self, *, race_id: str, anchor_driver_id: str,
            anchor_lap_number: int, anchor_state_time_s: float,
            target_driver_id: str, objective: str,
            candidates: list | tuple | None = None,
            simulation_count: int = DEFAULT_SIMULATION_COUNT,
            master_seed: int | None = None) -> dict:
        """Reconstruct the exact anchor and run one strategy comparison."""
        self._require_race(race_id)
        count = (DEFAULT_SIMULATION_COUNT if simulation_count is None
                 else int(simulation_count))
        seed = (DEFAULT_MASTER_SEED if master_seed is None
                else int(master_seed))
        specs = resolve_candidate_specs(candidates)
        validate_strategy_request(
            simulation_count=count, candidate_specs=specs,
            objective=objective, master_seed=master_seed)

        total_started = time.perf_counter()

        anchor = RS.AnchorObservation(
            race_id=race_id, anchor_driver_id=anchor_driver_id,
            anchor_lap_number=anchor_lap_number,
            anchor_state_time_s=anchor_state_time_s)
        race_state = self._reconstructor.reconstruct(anchor)
        reconstructed = time.perf_counter()

        sim_state = from_race_state(race_state)
        adapted = time.perf_counter()

        config = SimulationConfig(
            simulation_count=count, master_seed=seed,
            pit_dynamics_enabled=True)
        comparison = compare_strategies(
            sim_state, self._parameters, config, Assumptions(),
            target_driver_id, candidate_specs=specs,
            execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT,
            chunk_size=self._chunk_size)
        simulated = time.perf_counter()

        objective_result = evaluate_objective(comparison, objective)
        analyzed = time.perf_counter()

        return _response_payload(
            race_id=race_id, anchor_driver_id=anchor_driver_id,
            anchor_lap_number=anchor_lap_number,
            anchor_state_time_s=anchor_state_time_s,
            target_driver_id=target_driver_id, objective=objective,
            comparison=comparison, objective_result=objective_result,
            runtime={
                "reconstruction_s": reconstructed - total_started,
                "adaptation_s": adapted - reconstructed,
                "simulation_s": simulated - adapted,
                "analysis_s": analyzed - simulated,
                "total_s": analyzed - total_started,
            })


def _distribution_payload(distribution) -> list[dict]:
    return [
        {"position": position, "frequency": frequency}
        for position, frequency in distribution
    ]


def _candidate_payload(candidate_comparison, uncertainty) -> dict:
    candidate = candidate_comparison.candidate
    aggregate = candidate_comparison.aggregate
    execution = candidate_comparison.execution
    payload = {
        "candidate_key": candidate.key,
        "candidate_identity": candidate.identity(),
        "action": (candidate.action.value
                   if hasattr(candidate.action, "value")
                   else str(candidate.action)),
        "requested_compound": candidate.requested_compound,
        "valid": candidate_comparison.valid,
        "reason": candidate_comparison.reason,
        "evaluated": candidate_comparison.evaluated,
    }
    if aggregate is not None:
        payload.update({
            "win_probability": aggregate.win_probability,
            "podium_probability": aggregate.podium_probability,
            "expected_finish": aggregate.expected_finish,
            "finish_position_distribution": _distribution_payload(
                aggregate.finish_position_distribution),
        })
    if candidate_comparison.evaluated:
        payload.update({
            "delta_win_probability":
                candidate_comparison.delta_win_probability,
            "delta_podium_probability":
                candidate_comparison.delta_podium_probability,
            "delta_expected_finish":
                candidate_comparison.delta_expected_finish,
        })
    if uncertainty is not None:
        from raceintel.strategy.objectives import classify_uncertainty
        payload["uncertainty"] = {
            "point_estimate": uncertainty.point_estimate,
            "paired_se": uncertainty.paired_se,
            "ci_low": uncertainty.ci_low,
            "ci_high": uncertainty.ci_high,
            "classification": classify_uncertainty(uncertainty),
            "availability": uncertainty.availability,
            "valid_pairs": uncertainty.valid_pairs,
        }
    if execution is not None:
        payload["execution"] = {
            "applied_rate": execution.applied_rate,
            "suppressed_rate": execution.suppressed_rate,
            "superseded_rate": execution.superseded_rate,
            "inert_rate": execution.inert_rate,
            "race_end_cancelled_rate": execution.race_end_cancelled_rate,
        }
    return payload


def _response_payload(*, race_id: str, anchor_driver_id: str,
                      anchor_lap_number: int, anchor_state_time_s: float,
                      target_driver_id: str, objective: str,
                      comparison, objective_result, runtime: dict) -> dict:
    from raceintel.strategy.uncertainty import candidate_uncertainty
    metric = objective_metric(objective)
    baseline = comparison.baseline
    candidates = []
    for candidate_comparison in comparison.candidates:
        uncertainty = None
        if candidate_comparison.evaluated:
            uncertainty = candidate_uncertainty(
                comparison, candidate_comparison, metric)
        candidates.append(
            _candidate_payload(candidate_comparison, uncertainty))
    limitations = list(comparison.limitations) + list(
        objective_result.limitations)
    objective_analysis = {
        "objective": objective_result.objective,
        "metric": objective_result.metric,
        "leader_by_point_estimate":
            objective_result.leader_by_point_estimate,
        "indistinguishable_from_leader": list(
            objective_result.indistinguishable_from_leader),
        "distinguishable_from_leader": list(
            objective_result.distinguishable_from_leader),
        "point_estimate_order": list(objective_result.point_estimate_order),
    }
    return {
        "strategy_contract_version": STRATEGY_CONTRACT_VERSION,
        "intervention_version": INTERVENTION_VERSION,
        "comparison_version": COMPARISON_VERSION,
        "objective_version": OBJECTIVE_VERSION,
        "uncertainty_version": UNCERTAINTY_VERSION,
        "race_id": race_id,
        "anchor_driver_id": anchor_driver_id,
        "anchor_lap_number": anchor_lap_number,
        "anchor_state_time_s": anchor_state_time_s,
        "target_driver_id": target_driver_id,
        "simulation_count": comparison.simulation_count,
        "master_seed": comparison.master_seed,
        "objective": objective,
        "metric": metric,
        "probability_semantics": PROBABILITY_SEMANTICS,
        "counterfactual_semantics": comparison.counterfactual_semantics,
        "crn_policy": comparison.pairing_policy,
        "comparison_identity": comparison.identity(),
        "baseline": ({
            "valid_simulations": baseline.valid_simulations,
            "invalid_simulations": baseline.invalid_simulations,
            "win_probability": baseline.win_probability,
            "podium_probability": baseline.podium_probability,
            "expected_finish": baseline.expected_finish,
            "finish_position_distribution": _distribution_payload(
                baseline.finish_position_distribution),
        } if baseline is not None else None),
        "supported": comparison.supported,
        "unsupported_reason": comparison.unsupported_reason,
        "candidates": candidates,
        "objective_analysis": objective_analysis,
        "limitations": limitations,
        "runtime": runtime,
    }


def load_production_parameters(
        project_root: Path | None = None) -> SimulationParameterSet:
    """Load the frozen through-2024 R3 artifact once (read-only, verified)."""
    from api.v2_simulation_service import load_production_parameters as _load
    from api.v2_simulation_service import SimulationParameterUnavailableError
    try:
        return _load(project_root)
    except SimulationParameterUnavailableError as exc:
        raise StrategyParameterUnavailableError(str(exc)) from exc


def build_v2_strategy_service(
        v2_service, *, parameters: SimulationParameterSet | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE) -> V2StrategyService:
    """Share the loaded corpus/reconstructor read-only; build no model."""
    from api.v2_service import V2Service as _V2Service
    if not isinstance(v2_service, _V2Service):
        raise ValueError(
            f"v2_service must be a V2Service, got {type(v2_service)}")
    if parameters is None:
        parameters = load_production_parameters()
    return V2StrategyService(
        v2_service._states,  # noqa: SLF001 - shared read-only corpus
        v2_service._reconstructor,  # noqa: SLF001 - shared read-only index
        v2_service.race_ids, parameters, chunk_size=chunk_size)


@functools.lru_cache(maxsize=1)
def _cached_strategy_service() -> V2StrategyService:
    from api.v2_service import get_v2_service
    return build_v2_strategy_service(get_v2_service())


def get_v2_strategy_service() -> V2StrategyService:
    """FastAPI dependency: process-local lazy singleton (override in tests)."""
    return _cached_strategy_service()
