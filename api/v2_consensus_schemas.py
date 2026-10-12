"""V2 consensus HTTP schemas (V3.8F).

Pydantic representations of the MODEL / SIMULATION / DISAGREEMENT product
comparison for the versioned API boundary. There is no fourth-probability
field anywhere in this module. Sampling context is labelled
finite-MC-only; top-k is WIN-ranking overlap, never P(finish<=k).
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ConsensusAnchor(BaseModel):
    """Exact factual RaceState(T) reference (no interpolation, no future)."""

    race_id: str = Field(..., description="e.g. 2022-r03-R")
    anchor_lap_number: int = Field(..., ge=1)
    anchor_state_time_s: float | None = Field(
        default=None,
        description="exact anchor time; null only for fixture states")


class ConsensusAvailabilityResponse(BaseModel):
    race_id: str
    anchor_lap_number: int
    anchor_state_time_s: float | None
    model: str
    model_reason: str | None
    simulation: str
    simulation_reason: str | None
    comparison: str


class ConsensusDriverComparison(BaseModel):
    driver_id: str
    p_model: float | None
    p_simulation: float | None
    signed_gap: float | None
    absolute_gap: float | None
    model_inside_simulation_interval: bool | None
    valid_trials: int | None
    sampling_se: float | None
    wilson_95: list[float] | None


class ConsensusDisagreement(BaseModel):
    signed_gap_definition: str
    drivers: list[ConsensusDriverComparison]
    rank: dict
    leader: dict
    top_k: dict


class ConsensusModelBlock(BaseModel):
    source: str
    probability_family: str
    target: str
    drivers: list[dict]


class ConsensusSimulationBlock(BaseModel):
    source: str
    probability_family: str
    target: str
    drivers: list[dict]


class ConsensusProvenance(BaseModel):
    a_contract: str
    b_contract: str
    c_contract: str
    d_protocol: str
    d_card_corrected: str
    d_gate_corrected: str
    e_protocol: str
    e_card_corrected: str
    e_gate: str
    evidence_note: str


class ConsensusCompareResponse(BaseModel):
    state: dict
    availability: ConsensusAvailabilityResponse
    model: ConsensusModelBlock
    simulation: ConsensusSimulationBlock
    disagreement: ConsensusDisagreement
    provenance: ConsensusProvenance
