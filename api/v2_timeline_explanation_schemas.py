"""V2 prediction-change HTTP schemas (Phase-8 E5).

Pydantic representation of the compact public timeline-change payload
(PART J). The full 84 canonical delta evidence stays domain-internal/offline;
the wire response carries identity, the exact logit change, the overall
probability delta, the top positive/negative contribution-change deltas and
the omitted-delta accounting.

Semantics: contribution deltas are additive model log-odds changes, never
win-probability increments, and the overall probability delta is never
decomposed per feature. Independent per-driver binary probabilities are never
normalized.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from api.v2_explanation_schemas import V2LocalModelIdentity


class V2ChangeCheckpointIdentity(BaseModel):
    frame_index: int
    state_time_s: float
    leader_lap: int | None = None
    reasons: list[str] = Field(default_factory=list)
    anchor_driver_id: str | None = None
    anchor_lap_number: int | None = None
    anchor_state_time_s: float | None = None
    observed_lap_number: int | None = None
    observed_time_s: float | None = None
    observed_position: int | None = None
    observation_age_s: float | None = None


class V2ChangeIdentity(BaseModel):
    race_id: str
    driver_id: str
    from_frame_index: int | None = None
    to_frame_index: int
    from_checkpoint: V2ChangeCheckpointIdentity | None = None
    to_checkpoint: V2ChangeCheckpointIdentity


class V2ChangeReconstruction(BaseModel):
    from_logit: float
    to_logit: float
    logit_delta: float
    canonical_delta_sum: float
    residual: float
    logit_abs_tolerance: float
    probability_abs_tolerance: float
    intercept_cancels: bool
    full_decomposition_reconstructs_change: bool


class V2ChangeContribution(BaseModel):
    canonical_feature: str
    feature_family: str
    feature_type: str
    from_raw_value: Any | None = None
    to_raw_value: Any | None = None
    from_input_state: str
    to_input_state: str
    from_active_category: str | None = None
    to_active_category: str | None = None
    from_contribution: float
    to_contribution: float
    contribution_delta: float
    transition: str


class V2ChangeAccounting(BaseModel):
    top_n: int
    total_positive_log_odds_delta: float
    total_negative_log_odds_delta: float
    shown_positive_log_odds_delta: float
    shown_negative_log_odds_delta: float
    omitted_positive_log_odds_delta: float
    omitted_negative_log_odds_delta: float
    positive_feature_count: int
    negative_feature_count: int
    full_decomposition_reconstructs_change: bool
    top_n_reconstructs_change: bool
    note: str


class V2TimelineChangeResponse(BaseModel):
    contract_version: str
    format: str
    status: str
    identity: V2ChangeIdentity
    model_identity: V2LocalModelIdentity | None = None
    probability_semantics: str
    explanation_space: str
    reason: str | None = None
    from_probability: float | None = None
    to_probability: float | None = None
    probability_delta: float | None = None
    from_logit: float | None = None
    to_logit: float | None = None
    logit_delta: float | None = None
    cached_from_probability: float | None = None
    cached_to_probability: float | None = None
    reconstruction: V2ChangeReconstruction | None = None
    canonical_feature_count: int | None = None
    top_positive: list[V2ChangeContribution] = Field(default_factory=list)
    top_negative: list[V2ChangeContribution] = Field(default_factory=list)
    accounting: V2ChangeAccounting | None = None
    limitations: list[str] = Field(default_factory=list)
    cache_status: str = "HIT"
