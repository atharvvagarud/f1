"""V2 strategy HTTP schemas (Phase-7 S7).

Pydantic representations of the frozen S1–S6 Strategy comparison for the
versioned API boundary. The ``raceintel/strategy/*`` domain stays HTTP-independent:
the service projects its immutable result types into these models, never the
reverse. Per-index outcomes stay internal (S6-verified); only compact
aggregates, paired deltas and selected-objective uncertainty cross this
boundary.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from raceintel.simulation.config import MAX_MASTER_SEED

from api.v2_strategy_service import (
    DEFAULT_OBJECTIVE,
    DEFAULT_SIMULATION_COUNT,
    DEFAULT_STRATEGY_CANDIDATES,
    MAX_SYNCHRONOUS_SIMULATIONS,
    MIN_SIMULATION_COUNT,
)

StrategyActionValue = Literal["STAY_OUT", "PIT_NOW", "PIT_NEXT_LAP"]
StrategyCompoundValue = Literal["SOFT", "MEDIUM", "HARD"]
StrategyObjectiveValue = Literal[
    "MAXIMIZE_WIN_PROBABILITY",
    "MAXIMIZE_PODIUM_PROBABILITY",
    "MINIMIZE_EXPECTED_FINISH",
]


class V2StrategyCandidateRequest(BaseModel):
    """One requested intervention; ``requested_compound=None`` = sampled."""

    action: StrategyActionValue
    requested_compound: StrategyCompoundValue | None = None


class V2StrategyCompareRequest(BaseModel):
    """Exact-anchor strategy comparison request.

    The server reconstructs the factual state from the exact
    ``(race_id, anchor_driver_id, anchor_lap_number, anchor_state_time_s)``
    key. ``objective`` is required: the scientific layer defines no default.
    ``candidates`` defaults to the neutral ≤4 product set when omitted.
    """

    race_id: str = Field(min_length=1)
    anchor_driver_id: str = Field(min_length=1)
    anchor_lap_number: int = Field(ge=1)
    anchor_state_time_s: float = Field(allow_inf_nan=False)
    target_driver_id: str = Field(min_length=1)
    simulation_count: int = Field(
        default=DEFAULT_SIMULATION_COUNT,
        ge=MIN_SIMULATION_COUNT, le=MAX_SYNCHRONOUS_SIMULATIONS)
    master_seed: int | None = Field(default=None, ge=0, le=MAX_MASTER_SEED)
    objective: StrategyObjectiveValue
    candidates: list[V2StrategyCandidateRequest] | None = Field(default=None)


def default_candidate_payload() -> list[dict]:
    """Neutral default candidate set (product coverage, not performance)."""
    return [
        {"action": action, "requested_compound": compound}
        for action, compound in DEFAULT_STRATEGY_CANDIDATES
    ]


# Re-export the UI-facing default objective so the frontend can preselect the
# same visible, editable, explicitly-submitted value the service accepts.
UI_DEFAULT_OBJECTIVE: StrategyObjectiveValue = DEFAULT_OBJECTIVE


class V2StrategyPositionFrequencyResponse(BaseModel):
    position: int | None = None
    frequency: float


class V2StrategyBaselineResponse(BaseModel):
    valid_simulations: int
    invalid_simulations: int
    win_probability: float
    podium_probability: float
    expected_finish: float
    finish_position_distribution: list[V2StrategyPositionFrequencyResponse]


class V2StrategyUncertaintyResponse(BaseModel):
    point_estimate: float | None = None
    paired_se: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None
    classification: str
    availability: str
    valid_pairs: int


class V2StrategyExecutionResponse(BaseModel):
    applied_rate: float
    suppressed_rate: float
    superseded_rate: float
    inert_rate: float
    race_end_cancelled_rate: float


class V2StrategyCandidateResponse(BaseModel):
    candidate_key: str
    candidate_identity: str
    action: str
    requested_compound: str | None = None
    valid: bool
    reason: str | None = None
    evaluated: bool
    win_probability: float | None = None
    podium_probability: float | None = None
    expected_finish: float | None = None
    finish_position_distribution: list[V2StrategyPositionFrequencyResponse] = []
    delta_win_probability: float | None = None
    delta_podium_probability: float | None = None
    delta_expected_finish: float | None = None
    uncertainty: V2StrategyUncertaintyResponse | None = None
    execution: V2StrategyExecutionResponse | None = None


class V2StrategyObjectiveAnalysisResponse(BaseModel):
    objective: str
    metric: str
    leader_by_point_estimate: str | None = None
    indistinguishable_from_leader: list[str] = []
    distinguishable_from_leader: list[str] = []
    point_estimate_order: list[str] = []


class V2StrategyRuntimeResponse(BaseModel):
    reconstruction_s: float
    adaptation_s: float
    simulation_s: float
    analysis_s: float
    total_s: float


class V2StrategyCompareResponse(BaseModel):
    strategy_contract_version: str
    intervention_version: str
    comparison_version: str
    objective_version: str
    uncertainty_version: str
    race_id: str
    anchor_driver_id: str
    anchor_lap_number: int
    anchor_state_time_s: float
    target_driver_id: str
    simulation_count: int
    master_seed: int
    objective: str
    metric: str
    probability_semantics: str
    counterfactual_semantics: str
    crn_policy: str
    comparison_identity: str
    baseline: V2StrategyBaselineResponse | None = None
    supported: bool
    unsupported_reason: str | None = None
    candidates: list[V2StrategyCandidateResponse] = []
    objective_analysis: V2StrategyObjectiveAnalysisResponse | None = None
    limitations: list[str] = []
    runtime: V2StrategyRuntimeResponse


class V2StrategyErrorResponse(BaseModel):
    error: str
    detail: str = ""
    reason: str | None = None
