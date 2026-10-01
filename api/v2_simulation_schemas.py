"""V2 simulation HTTP schemas (Phase-6 R8).

Pydantic representations of the Phase-6 aggregate simulation result for the
versioned API boundary. The ``v2/*`` domain stays HTTP-independent: the route
converts the service's plain payload into these models.

Probability semantics are ``MONTE_CARLO_FREQUENCY`` — empirical outcome
frequencies over valid trials. They are passed through verbatim: no share, no
sum-to-one field, and no normalization anywhere in this layer. DNF/points
fields stay null because those models are deferred.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from raceintel.simulation.config import MAX_MASTER_SEED

from api.v2_simulation_service import (
    DEFAULT_SIMULATION_COUNT,
    MAX_SYNCHRONOUS_SIMULATIONS,
    MIN_SIMULATION_COUNT,
)


class V2SimulationRequest(BaseModel):
    """Exact-anchor historical-state simulation request.

    The server reconstructs the factual state from the exact
    ``(race_id, anchor_driver_id, anchor_lap_number, anchor_state_time_s)``
    key. Arbitrary user-created ``SimulationState`` JSON is never accepted.
    """

    race_id: str = Field(min_length=1)
    anchor_driver_id: str = Field(min_length=1)
    anchor_lap_number: int = Field(ge=1)
    anchor_state_time_s: float = Field(allow_inf_nan=False)
    simulation_count: int = Field(
        default=DEFAULT_SIMULATION_COUNT,
        ge=MIN_SIMULATION_COUNT, le=MAX_SYNCHRONOUS_SIMULATIONS)
    master_seed: int | None = Field(default=None, ge=0, le=MAX_MASTER_SEED)


class V2PositionFrequencyResponse(BaseModel):
    """One finish-position bucket frequency (DNF bucket is never emitted)."""

    position: int | None = None
    frequency: float


class V2DriverSimulationResponse(BaseModel):
    driver_id: str
    win_probability: float
    podium_probability: float
    expected_finish: float
    finish_position_distribution: list[V2PositionFrequencyResponse]
    dnf_probability: float | None = None
    points_probability: float | None = None
    expected_points: float | None = None


class V2SimulationRuntimeResponse(BaseModel):
    reconstruction_s: float
    adaptation_s: float
    simulation_s: float
    total_s: float


class V2SimulationResponse(BaseModel):
    race_id: str
    anchor_driver_id: str
    anchor_lap_number: int
    anchor_state_time_s: float
    simulation_contract_version: str
    engine_version: str
    monte_carlo_version: str
    pit_dynamics_version: str
    mechanics: list[str]
    probability_semantics: str
    probability_semantics_note: str
    parameter_set_id: str
    parameter_version: str
    parameter_hash: str
    simulation_request_identity: str
    scientific_result_identity: str
    requested_simulation_count: int
    valid_simulations: int
    invalid_simulations: int
    master_seed: int
    engine_runtime_s: float
    runtime: V2SimulationRuntimeResponse
    drivers: list[V2DriverSimulationResponse]


class V2SimulationErrorResponse(BaseModel):
    error: str
    detail: str = ""
    reason: str | None = None
