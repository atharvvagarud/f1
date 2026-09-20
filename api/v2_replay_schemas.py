"""V2 replay HTTP schemas (Phase-5 R4).

Pydantic representations of the R1/R2 factual replay domain and the R3
cached-prediction domain for the versioned API boundary. The ``v2/*``
domain stays HTTP-independent: routes convert domain ``to_dict()``
payloads into these models, never the reverse.

Frame payloads never embed probabilities; prediction payloads carry the
frozen ``PredictionSnapshot`` verbatim (independent binary, never
renormalized). Error bodies are ``{error, detail}`` plus optional
machine-readable extras, mirroring the Phase-4 ``api/v2_routes.py``
convention.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from api.v2_schemas import (
    V2ModelIdentityResponse,
    V2PredictionSnapshotResponse,
    V2RaceStateResponse,
)


class V2ReplayFrameMeta(BaseModel):
    """Factual replay identity only — no RaceState, no probabilities."""

    race_id: str
    frame_index: int
    anchor_driver_id: str
    anchor_lap_number: int
    anchor_state_time_s: float
    replay_contract_version: str


class V2ReplayTimelineResponse(BaseModel):
    race_id: str
    replay_contract_version: str
    total_frames: int
    offset: int
    limit: int
    returned_count: int
    frames: list[V2ReplayFrameMeta]


class V2CheckpointMeta(BaseModel):
    """WHERE a cached prediction lives — never the values."""

    frame_index: int
    reasons: list[str]
    leader_lap: int | None = None
    replay_contract_version: str
    prediction_contract_version: str


class V2ReplayFrameResponse(BaseModel):
    frame: V2ReplayFrameMeta
    state: V2RaceStateResponse
    has_previous: bool
    has_next: bool
    previous_frame_index: int | None = None
    next_frame_index: int | None = None
    leader_lap: int | None = None
    is_prediction_checkpoint: bool = False
    checkpoint_reasons: list[str] = Field(default_factory=list)
    prediction_cache_available: bool = False
    previous_prediction_checkpoint_frame: int | None = None
    next_prediction_checkpoint_frame: int | None = None


class V2ReplayPredictionResponse(BaseModel):
    frame: V2ReplayFrameMeta
    checkpoint: V2CheckpointMeta
    prediction: V2PredictionSnapshotResponse
    cache_status: Literal["HIT"] = "HIT"


class V2ProbabilityCheckpointResponse(BaseModel):
    """One actual model-evaluation point (never interpolated)."""

    frame_index: int
    state_time_s: float
    leader_lap: int | None = None
    reasons: list[str]


class V2DriverProbabilityPointResponse(BaseModel):
    frame_index: int
    state_time_s: float
    leader_lap: int | None = None
    winner_probability: float | None = None


class V2DriverProbabilitySeriesResponse(BaseModel):
    driver_id: str
    points: list[V2DriverProbabilityPointResponse]


class V2ProbabilityTimelineResponse(BaseModel):
    """Complete cached probability series for one race (one response)."""

    race_id: str
    replay_contract_version: str
    prediction_contract_version: str
    probability_timeline_contract_version: str
    probability_semantics: str
    model: V2ModelIdentityResponse
    timeline_identity: str
    checkpoints: list[V2ProbabilityCheckpointResponse]
    driver_series: list[V2DriverProbabilitySeriesResponse]


class V2ReplayErrorResponse(BaseModel):
    """Documented error shape; routes return these as plain JSON bodies."""

    error: str
    detail: str = ""
    reason: str | None = None
    previous_prediction_checkpoint_frame: int | None = None
    next_prediction_checkpoint_frame: int | None = None
