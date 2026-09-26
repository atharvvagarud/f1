"""V2 local-explanation HTTP schemas (Phase-8 E4).

Pydantic representation of the compact public local-explanation payload
(PART K). Full 84/106 evidence stays domain-internal/offline; the wire
response carries identity, exact reconstruction, top canonical
contributions and the omitted-contribution accounting.

Language semantics: contributions are additive model log-odds, never
win-probability increments, and independent per-driver binary
probabilities are never normalized.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class V2LocalFeatureIdentity(BaseModel):
    race_id: str
    driver_id: str
    lap_number: int
    state_time_s: float


class V2LocalObservation(BaseModel):
    observed_lap_number: int
    observed_time_s: float
    observation_age_s: float | None = None
    observed_position: int | None = None


class V2LocalExplanationIdentity(BaseModel):
    race_id: str
    frame_index: int
    driver_id: str
    checkpoint_reasons: list[str] = Field(default_factory=list)
    leader_lap: int | None = None
    state_time_s: float
    anchor_driver_id: str
    anchor_lap_number: int
    anchor_state_time_s: float
    feature_identity: V2LocalFeatureIdentity
    observation: V2LocalObservation


class V2LocalModelIdentity(BaseModel):
    feature_set: str
    feature_set_version: str
    estimator_class: str
    specification_fingerprint: str
    transformed_dim: int
    canonical_feature_count: int
    calibration_method: str
    probability_kind: str
    probability_semantics: str
    training_seasons: list[int]
    sklearn_version: str


class V2LocalReconstruction(BaseModel):
    estimator_decision_function: float
    residual: float
    logit_abs_tolerance: float
    probability_abs_tolerance: float
    transformed_contribution_sum: float
    canonical_contribution_sum: float


class V2LocalCanonicalContribution(BaseModel):
    canonical_feature: str
    feature_family: str
    feature_type: str
    raw_value: Any | None = None
    input_state: str
    imputed_value: Any | None = None
    active_category: str | None = None
    log_odds_contribution: float
    direction: str


class V2LocalAccounting(BaseModel):
    top_n: int
    total_positive_log_odds: float
    total_negative_log_odds: float
    shown_positive_log_odds: float
    shown_negative_log_odds: float
    omitted_positive_log_odds: float
    omitted_negative_log_odds: float
    positive_feature_count: int
    negative_feature_count: int
    full_decomposition_reconstructs_prediction: bool
    top_n_reconstructs_prediction: bool
    note: str


class V2LocalExplanationResponse(BaseModel):
    contract_version: str
    format: str
    identity: V2LocalExplanationIdentity
    model_identity: V2LocalModelIdentity
    probability_semantics: str
    explanation_space: str
    intercept: float
    logit: float
    probability: float
    model_probability: float
    cached_probability: float | None = None
    reconstruction: V2LocalReconstruction
    transformed_feature_count: int
    canonical_feature_count: int
    top_positive: list[V2LocalCanonicalContribution]
    top_negative: list[V2LocalCanonicalContribution]
    accounting: V2LocalAccounting
    limitations: list[str]
    cache_status: str = "HIT"


class V2ExplanationErrorResponse(BaseModel):
    """Documented error shape; routes return these as plain JSON bodies."""

    error: str
    detail: str = ""
    reason: str | None = None
    driver_id: str | None = None
    previous_prediction_checkpoint_frame: int | None = None
    next_prediction_checkpoint_frame: int | None = None
