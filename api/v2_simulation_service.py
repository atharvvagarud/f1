"""V2 simulation application service (Phase-6 R8).

Narrow product orchestration over the frozen Phase-4 race-state authority and
the frozen Phase-6 Monte Carlo runtime:

    exact anchor -> RaceState (Phase-4) -> SimulationState (R2 adapter)
    -> runtime eligibility -> MonteCarloEngine (R5/R6) -> aggregate response

Design rules (R8):
- The scientific runtime (``raceintel/simulation/*``) is untouched. This module only
  composes already-frozen contracts.
- The exact historical anchor (``race_id``, ``anchor_driver_id``,
  ``anchor_lap_number``, ``anchor_state_time_s``) is authoritative. There is
  no nearest-state behaviour and no independently reconstructed anchor logic;
  the frontend, when it starts from a replay frame, sends that frame's exact
  anchor mapping.
- ``MonteCarloEngine`` is never asked to import replay: the service owns the
  seam. ``from_race_state`` is the only bridge.
- The production parameter artifact is the frozen R3 through-2024 set
  (``ExecutionPolicy.RETROSPECTIVE_PRODUCT``). It is loaded once, read-only,
  validated, and cached. No runtime estimation. Historical-backtest artifacts
  are never selected for a normal product request.
- No normalization ever happens here: the engine's winner mass over valid
  trajectories is passed through verbatim.
- Uncertain / unsupported states surface as the stable domain reason, never a
  fallback, a dropped driver, or an inferred retirement.

No FastAPI types here; routes map domain errors to HTTP status codes.
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
    MonteCarloEngine,
    SimulationConfig,
    SimulationParameterSet,
    load_simulation_parameters,
    parameter_storage_dir,
)
from raceintel.simulation.adapter import SimulationUnavailableError, from_race_state
from raceintel.simulation.engine import ENGINE_VERSION
from raceintel.simulation.monte_carlo import (
    DEFAULT_CHUNK_SIZE,
    MONTE_CARLO_VERSION,
    PIT_DYNAMICS_VERSION,
)
from raceintel.simulation.results import PROBABILITY_SEMANTICS, PROBABILITY_SEMANTICS_NOTE
from raceintel.simulation.state import SIMULATION_CONTRACT_VERSION
from raceintel.race_state.race_state_reconstruction import RaceNotFoundError

_REPO_ROOT = Path(__file__).resolve().parents[1]

#: Product simulation-count policy (R8-G/H), derived from the measured R7
#: engine benchmark: 1 000 trials cost ~2.4 s (early) to ~0.7 s (late);
#: 10 000 cost ~24.6 s (early) to ~7.3 s (late). A synchronous request must
#: not casually occupy a worker for minutes, so 10 000 is the explicit
#: high-quality ceiling and 1 000 the default.
MIN_SIMULATION_COUNT = 1
DEFAULT_SIMULATION_COUNT = 1000
MAX_SYNCHRONOUS_SIMULATIONS = 10000

#: Deterministic default seed (the R7 validation seed). Product requests may
#: override it; every run is a pure function of (seed, inputs, params).
DEFAULT_MASTER_SEED = 20240101

#: Production parameter artifact is the frozen R3 through-2024 estimation.
PRODUCTION_PARAMETER_SEASON = 2024


class SimulationParameterUnavailableError(RuntimeError):
    """The frozen production parameter artifact is missing or corrupt.

    Raised at service construction (never per request); the API maps it to a
    ``503 parameter_unavailable`` response.
    """


class V2SimulationService:
    """Reusable, read-only Phase-6 product simulation orchestration.

    Holds the shared canonical corpus reference, the shared Phase-4
    ``RaceStateReconstructor``, the served race registry, and the frozen
    through-2024 parameter set. It constructs a fresh ``MonteCarloEngine`` per
    request so no mutable engine/RNG/trajectory state is shared across
    concurrent requests.
    """

    def __init__(self, states: pd.DataFrame, reconstructor,
                 served_race_ids, parameters: SimulationParameterSet, *,
                 chunk_size: int = DEFAULT_CHUNK_SIZE):
        if not isinstance(states, pd.DataFrame):
            raise ValueError(f"states must be a DataFrame, got {type(states)}")
        if not isinstance(parameters, SimulationParameterSet):
            raise TypeError(
                f"parameters must be a SimulationParameterSet, got "
                f"{type(parameters)}")
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

    @property
    def served_seasons(self) -> tuple:
        return tuple(sorted({int(race_id.split("-", 1)[0])
                             for race_id in self._served}))

    def _require_race(self, race_id: str) -> None:
        if race_id not in self._served:
            raise RaceNotFoundError(race_id)

    def run_simulation(
            self, *, race_id: str, anchor_driver_id: str,
            anchor_lap_number: int, anchor_state_time_s: float,
            simulation_count: int = DEFAULT_SIMULATION_COUNT,
            master_seed: int | None = None) -> dict:
        """Reconstruct the exact anchor and run one aggregate simulation.

        Returns the aggregate payload (no raw trajectories, no per-event
        traces). Raises the frozen domain errors unchanged so the route can
        map them to stable HTTP responses.
        """
        self._require_race(race_id)
        count = (DEFAULT_SIMULATION_COUNT if simulation_count is None
                 else int(simulation_count))
        seed = (DEFAULT_MASTER_SEED if master_seed is None
                else int(master_seed))

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
        result = MonteCarloEngine(chunk_size=self._chunk_size).run(
            sim_state, self._parameters, config, Assumptions(),
            execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
        simulated = time.perf_counter()

        payload = _response_payload(
            race_id=race_id, anchor_driver_id=anchor_driver_id,
            anchor_lap_number=anchor_lap_number,
            anchor_state_time_s=anchor_state_time_s,
            parameters=self._parameters, result=result,
            runtime={
                "reconstruction_s": reconstructed - total_started,
                "adaptation_s": adapted - reconstructed,
                "simulation_s": simulated - adapted,
                "total_s": simulated - total_started,
            })
        return payload


def _driver_payload(summary) -> dict:
    """Verbatim per-driver aggregate; never normalized or fabricated."""
    return {
        "driver_id": summary.driver_id,
        "win_probability": summary.win_probability,
        "podium_probability": summary.podium_probability,
        "expected_finish": summary.expected_finish,
        "finish_position_distribution": [
            {"position": entry.position, "frequency": entry.frequency}
            for entry in summary.finish_position_distribution],
        # Reliability is DEFERRED (no DNF hazard exists), so DNF is null.
        "dnf_probability": summary.dnf_probability,
        # Points regulation is not modelled; never fabricated.
        "points_probability": summary.points_probability,
        "expected_points": summary.expected_points,
    }


def _response_payload(*, race_id: str, anchor_driver_id: str,
                      anchor_lap_number: int, anchor_state_time_s: float,
                      parameters: SimulationParameterSet, result,
                      runtime: dict) -> dict:
    return {
        "race_id": race_id,
        "anchor_driver_id": anchor_driver_id,
        "anchor_lap_number": anchor_lap_number,
        "anchor_state_time_s": anchor_state_time_s,
        "simulation_contract_version": SIMULATION_CONTRACT_VERSION,
        "engine_version": ENGINE_VERSION,
        "monte_carlo_version": MONTE_CARLO_VERSION,
        "pit_dynamics_version": PIT_DYNAMICS_VERSION,
        "mechanics": ["pit_dynamics"],
        "probability_semantics": PROBABILITY_SEMANTICS,
        "probability_semantics_note": PROBABILITY_SEMANTICS_NOTE,
        "parameter_set_id": parameters.parameter_set_id,
        "parameter_version": parameters.parameter_version,
        "parameter_hash": parameters.scientific_hash(),
        "simulation_request_identity": result.simulation_request_identity,
        "scientific_result_identity": result.identity(),
        "requested_simulation_count": result.requested_simulation_count,
        "valid_simulations": result.valid_simulation_count,
        "invalid_simulations": result.invalid_simulation_count,
        "master_seed": result.master_seed,
        "engine_runtime_s": float(result.runtime_s),
        "runtime": runtime,
        "drivers": [_driver_payload(summary)
                    for summary in result.driver_summaries],
    }


def load_production_parameters(
        project_root: Path | None = None) -> SimulationParameterSet:
    """Load the frozen through-2024 R3 artifact once (read-only, verified)."""
    root = _REPO_ROOT if project_root is None else Path(project_root)
    try:
        return load_simulation_parameters(
            parameter_storage_dir(root, PRODUCTION_PARAMETER_SEASON))
    except Exception as exc:  # noqa: BLE001 - stable 503, never a traceback
        raise SimulationParameterUnavailableError(
            "frozen through-2024 simulation parameters unavailable: "
            f"{exc}") from exc


def build_v2_simulation_service(
        v2_service, *, parameters: SimulationParameterSet | None = None,
        chunk_size: int = DEFAULT_CHUNK_SIZE) -> V2SimulationService:
    """Share the loaded corpus/reconstructor read-only; build no model.

    ``v2_service`` is touched only for its already-loaded canonical ``states``
    frame, its reusable ``RaceStateReconstructor``, and its served race
    registry. The frozen ``api/v2_service.py`` module is unchanged and the
    Phase-3 winner model is never read here.
    """
    from api.v2_service import V2Service as _V2Service
    if not isinstance(v2_service, _V2Service):
        raise ValueError(
            f"v2_service must be a V2Service, got {type(v2_service)}")
    if parameters is None:
        parameters = load_production_parameters()
    return V2SimulationService(
        v2_service._states,  # noqa: SLF001 - shared read-only corpus
        v2_service._reconstructor,  # noqa: SLF001 - shared read-only index
        v2_service.race_ids, parameters, chunk_size=chunk_size)


@functools.lru_cache(maxsize=1)
def _cached_simulation_service() -> V2SimulationService:
    from api.v2_service import get_v2_service
    return build_v2_simulation_service(get_v2_service())


def get_v2_simulation_service() -> V2SimulationService:
    """FastAPI dependency: process-local lazy singleton (override in tests)."""
    return _cached_simulation_service()
