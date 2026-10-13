"""V3.9C uncertainty API schemas (typed, no confidence scalar anywhere)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class UncertaintyAnchor(BaseModel):
    race_id: str
    anchor_lap_number: int = Field(ge=1)
    anchor_state_time_s: float | None = None


class UncertaintyAvailabilityResponse(BaseModel):
    race_id: str
    anchor_lap_number: int
    anchor_state_time_s: float | None = None
    model: str
    model_reason: str | None = None
    simulation: str
    simulation_reason: str | None = None
    comparison: str
    simulator_sensitivity: str


class UncertaintyDisagreement(BaseModel):
    status: str
    p_model: float
    p_model_family: str
    p_simulation: float
    p_simulation_family: str
    signed_gap: float
    absolute_gap: float
    model_rank: float
    simulation_rank: float
    model_inside_simulation_wilson: bool


class UncertaintySampling(BaseModel):
    status: str
    success_count_k: int
    valid_futures_n: int
    p_hat: float
    standard_error: float
    wilson_95_lower: float
    wilson_95_upper: float
    precision_label: str


class UncertaintyDiagnostic(BaseModel):
    gap_to_sampling_ratio: float | None = None
    label: str


class UncertaintyDriver(BaseModel):
    driver_id: str
    status: str
    missing_arm: str | None = None
    disagreement: UncertaintyDisagreement | None = None
    monte_carlo_sampling: UncertaintySampling | None = None
    diagnostic: UncertaintyDiagnostic | None = None


class UncertaintyField(BaseModel):
    n_common_drivers: int
    rank_correlation_spearman: float | None = None
    leader_model: str | None = None
    leader_simulation: str | None = None
    leader_agree: bool | None = None
    top3_jaccard: float | None = None


class UncertaintySensitivity(BaseModel):
    status: str
    executable: bool
    reason: str
    gate: str
    gate_version: str


class UncertaintyState(BaseModel):
    state_id: str
    race_id: str
    lap_number: int
    state_time_s: float | None = None
    stage: str | None = None
    season: int


class UncertaintySourceBlock(BaseModel):
    source: str
    probability_family: str


class UncertaintySources(BaseModel):
    model: UncertaintySourceBlock
    simulation: UncertaintySourceBlock


class UncertaintyCompareResponse(BaseModel):
    schema_version: str
    metric_implementation: str
    state: UncertaintyState
    sources: UncertaintySources
    drivers: list[UncertaintyDriver]
    field: UncertaintyField
    simulator_sensitivity: UncertaintySensitivity
    availability: UncertaintyAvailabilityResponse
    provenance: dict
