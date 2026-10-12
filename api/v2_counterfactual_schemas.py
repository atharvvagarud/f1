"""V2 counterfactual HTTP schemas (V3.7F runtime integration).

Pydantic boundary for the frozen V3.7C engine
(``raceintel.counterfactual.engine``) via the F runtime adapter
(``raceintel.counterfactual.runtime``). Strict schemas (``extra="forbid"``)
are the first fail-closed layer: production-forbidden fields (simulation
counts, seeds), rejected intervention kinds (weather/safety-car/...),
historical-future smuggling fields, and recommendation language cannot be
expressed and are rejected with 422 before any science runs.

Language policy (V3.7A/B): SIMULATOR-CONDITIONAL / COMPARE / PLAN /
SIMULATED DIFFERENCE / PAIRED SIMULATIONS. Never BEST / OPTIMAL /
RECOMMENDED / SHOULD PIT / CORRECT STRATEGY / GUARANTEED / WOULD HAVE.

The public compare schema carries NO execution-mode field and NO
simulation-count/seed fields. Cache-first with server-side live opt-in is
a runtime policy (see the service module), never a client parameter, so a
browser cannot authorize expensive scientific execution.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

CounterfactualKindValue = Literal["PIT_IN_N_LAPS"]
CounterfactualCompoundValue = Literal["SOFT", "MEDIUM", "HARD", "SAMPLED"]
CounterfactualFormValue = Literal["REFERENCE_VS_PLAN", "PLAN_VS_PLAN"]


class CounterfactualInterventionRequest(BaseModel):
    """One admitted scheduled intervention (PIT_IN_N_LAPS only).

    ``lap_offset_n`` is the simulation-relative future lap offset from
    factual T (NOT a historical lap lookup). ``requested_compound``
    defaults to SAMPLED (sampled transition, matching seam semantics).
    """

    model_config = ConfigDict(extra="forbid")

    target_driver_id: str = Field(min_length=1)
    kind: CounterfactualKindValue = "PIT_IN_N_LAPS"
    lap_offset_n: int = Field(ge=1)
    requested_compound: CounterfactualCompoundValue = "SAMPLED"


class CounterfactualPlanRequest(BaseModel):
    """One declarative counterfactual plan.

    ``target_driver_ids[0]`` is NOT orientational: the runtime
    canonicalizes targets (sorted) so input order never affects plan
    identity, cache identity, or science; the primary outcome target is
    the canonically first target. Every target must own at least one
    intervention; every intervention target must be listed.
    """

    model_config = ConfigDict(extra="forbid")

    target_driver_ids: list[str] = Field(min_length=1)
    interventions: list[CounterfactualInterventionRequest] = Field(
        min_length=1, max_length=8)


class CounterfactualCompareRequest(BaseModel):
    """Counterfactual comparison for one exact historical state.

    The server reconstructs the factual RaceState(T) from the exact
    ``(race_id, anchor_driver_id, anchor_lap_number, anchor_state_time_s)``
    key. ``base_plan`` is required if and only if ``comparison_form`` is
    PLAN_VS_PLAN. ``rival_driver_id`` is the optional admitted rival
    (factual presence validated; must differ from plan targets).
    """

    model_config = ConfigDict(extra="forbid")

    race_id: str = Field(min_length=1)
    anchor_driver_id: str = Field(min_length=1)
    anchor_lap_number: int = Field(ge=1)
    anchor_state_time_s: float = Field(allow_inf_nan=False)
    comparison_form: CounterfactualFormValue = "REFERENCE_VS_PLAN"
    base_plan: CounterfactualPlanRequest | None = None
    alternative_plan: CounterfactualPlanRequest
    rival_driver_id: str | None = Field(default=None, min_length=1)


class CounterfactualAvailabilityDriver(BaseModel):
    model_config = ConfigDict(extra="forbid")

    driver_id: str
    position: int | None = None
    decision_lap: int
    remaining_laps: int
    eligible_n_min: int | None = None
    eligible_n_max: int | None = None
    eligible: bool
    compound: str | None = None
    status: str


class CounterfactualAvailabilityResponse(BaseModel):
    """Cheap factual availability (never simulates)."""

    model_config = ConfigDict(extra="forbid")

    api_schema: str
    supported: bool
    level: str | None = None
    reason_code: str | None = None
    human_reason: str | None = None
    state_identity: str | None = None
    race_id: str
    anchor_driver_id: str
    anchor_lap_number: int
    anchor_state_time_s: float
    season: int | None = None
    scheduled_laps: int | None = None
    leader_laps_done: int | None = None
    drivers: list[CounterfactualAvailabilityDriver] = []
    eligible_targets: list[str] = []
    supported_compounds: list[str] = []
    comparison_forms: list[str] = []
    multi_stop_capable: bool = False
    multi_driver_capable: bool = False
    rival_candidates: list[str] = []
    cached_comparison_identities: list[str] = []
    live_enabled: bool = False
    provenance: dict = {}
    limitations: str = ""


class CounterfactualAggregateResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_driver_id: str
    n: int
    win_frequency: float
    podium_frequency: float
    top5_frequency: float
    top10_frequency: float
    expected_finish: float
    median_finish: float
    finish_q25: float
    finish_q75: float
    finish_position_distribution: list[dict] = []
    downside_vs_other: float | None = None
    p_ahead_of_rival: float | None = None
    expected_pit_count: float
    expected_position_gain: float | None = None


class CounterfactualDeltaResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    metric: str
    point_estimate: float | None = None
    paired_se: float | None = None
    ci_low: float | None = None
    ci_high: float | None = None


class CounterfactualRuntimeResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reconstruction_s: float
    adaptation_s: float = 0.0
    simulation_s: float
    analysis_s: float = 0.0
    total_s: float


class CounterfactualCompareResponse(BaseModel):
    """Counterfactual comparison payload (simulated differences only)."""

    model_config = ConfigDict(extra="forbid")

    api_schema: str
    supported: bool
    level: str | None = None
    reason_code: str | None = None
    human_reason: str | None = None
    comparison_form: str | None = None
    comparison_identity: str | None = None
    base_identity: str | None = None
    alternative_identity: str | None = None
    state_identity: str | None = None
    parameter_identity: str | None = None
    config_identity: str | None = None
    master_seed: int | None = None
    simulation_count: int | None = None
    race_id: str
    anchor_driver_id: str
    anchor_lap_number: int
    anchor_state_time_s: float
    target_driver_ids: list[str] = []
    primary_target_driver_id: str | None = None
    rival_driver_id: str | None = None
    base_aggregate: CounterfactualAggregateResponse | None = None
    alternative_aggregate: CounterfactualAggregateResponse | None = None
    deltas: dict[str, CounterfactualDeltaResponse] = {}
    complete_pairs: int | None = None
    requested_pairs: int | None = None
    excluded_pairs: int | None = None
    lifecycle_summary: dict = {}
    provenance: dict = {}
    limitations: str = ""
    execution_source: Literal["live_engine", "cache"] | None = None
    cache_key: str | None = None
    runtime: CounterfactualRuntimeResponse | None = None


class CounterfactualErrorResponse(BaseModel):
    error: str
    detail: str = ""
    reason: str | None = None
