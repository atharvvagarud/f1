"""V2 HTTP schemas (Phase-4 R5).

Pydantic representations of the R1/R4 domain for the versioned API
boundary. The ``v2/*`` domain stays HTTP-independent: routes convert
domain ``to_dict()`` payloads into these models, never the reverse.
Independent binary probabilities are exposed verbatim — no share,
no sum-to-one field, no normalization anywhere in conversion.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class V2RaceSummary(BaseModel):
    """Factual PRE_RACE identity only — never outcomes or labels."""

    race_id: str
    season: int
    round_no: int
    event_name: str
    circuit_id: str | None = None
    country: str | None = None
    location: str | None = None
    scheduled_laps: int | None = None


class V2RaceListResponse(BaseModel):
    races: list[V2RaceSummary]
    count: int


class V2StateAnchor(BaseModel):
    """One exact anchor identity observable in the canonical corpus."""

    driver_id: str
    lap_number: int
    state_time_s: float


class V2StateListResponse(BaseModel):
    race_id: str
    total: int
    offset: int
    limit: int
    anchors: list[V2StateAnchor]


class V2AnchorRequest(BaseModel):
    """Exact Time-T key: all four parts required, never nearest-matched."""

    race_id: str = Field(min_length=1)
    anchor_driver_id: str = Field(min_length=1)
    anchor_lap_number: int = Field(ge=1)
    anchor_state_time_s: float = Field(allow_inf_nan=False)


class V2DriverRaceStateResponse(BaseModel):
    driver_id: str
    observable: bool
    observed_lap_number: int | None = None
    observed_time_s: float | None = None
    observation_age_s: float | None = None
    position: int | None = None
    gap_to_leader_s: float | None = None
    gap_to_leader_valid: bool | None = None
    gap_to_leader_laps: int | None = None
    gap_to_ahead_s: float | None = None
    gap_to_ahead_valid: bool | None = None
    gap_to_ahead_laps: int | None = None
    compound: str | None = None
    tyre_life: int | None = None
    fresh_tyre: bool | None = None
    stint_number: int | None = None
    stint_lap: int | None = None
    pit_stops_completed_so_far: int | None = None
    laps_since_last_pit_stop: int | None = None
    constructor_id: str | None = None
    driver_number: int | None = None


class V2RaceContextResponse(BaseModel):
    race_leader_laps_at_state: int | None = None
    race_progress_frac: float | None = None
    scheduled_laps: int | None = None
    season: int | None = None
    round_no: int | None = None
    circuit_id: str | None = None


class V2WeatherResponse(BaseModel):
    air_temp_c: float | None = None
    track_temp_c: float | None = None
    humidity_pct: float | None = None
    pressure_hpa: float | None = None
    wind_speed: float | None = None
    wind_direction_deg: float | None = None
    rainfall: bool | None = None
    observed_at_s: float | None = None
    observation_age_s: float | None = None


class V2RaceControlResponse(BaseModel):
    track_state: str | None = None
    flag_yellow: bool | None = None
    flag_safety_car: bool | None = None
    flag_red: bool | None = None
    flag_vsc: bool | None = None
    last_message_category: str | None = None
    last_message_flag: str | None = None
    last_message_age_s: float | None = None


class V2RaceStateResponse(BaseModel):
    race_id: str
    anchor_driver_id: str
    anchor_lap_number: int
    state_time_s: float
    roster_size: int
    drivers: list[V2DriverRaceStateResponse]
    race_context: V2RaceContextResponse
    weather: V2WeatherResponse
    race_control: V2RaceControlResponse


class V2ModelIdentityResponse(BaseModel):
    task: str
    target: str
    eligibility_mask: str
    feature_set: str
    feature_set_version: str
    estimator: str
    estimator_params: list
    calibration_method: str
    probability_semantics: str
    training_seasons: list[int]
    transformed_dim: int
    feature_count: int
    artifact_sha256: str
    specification_fingerprint: str
    sklearn_version: str


class V2DriverPredictionResponse(BaseModel):
    driver_id: str
    observable: bool
    observed_lap_number: int | None = None
    observed_time_s: float | None = None
    observation_age_s: float | None = None
    observed_position: int | None = None
    winner_probability: float | None = None
    unavailable_reason: str | None = None


class V2PredictionSnapshotResponse(BaseModel):
    race_id: str
    anchor_driver_id: str
    anchor_lap_number: int
    state_time_s: float
    roster_size: int
    observable_count: int
    unavailable_count: int
    probability_semantics: str
    probability_semantics_note: str
    feature_set: str
    model: V2ModelIdentityResponse
    predictions: list[V2DriverPredictionResponse]


class V2ErrorResponse(BaseModel):
    error: str
    detail: str = ""
