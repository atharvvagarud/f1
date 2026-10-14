"""V3.10F driver-telemetry HTTP schemas.

Race-scoped historical lap/stint evidence over the frozen D9 corpus.
Every value is verbatim source evidence with its observation boundary;
the causal (<=T) slicing happens client-side in the typed selector
(frontend/features/pit-wall/lib/telemetry.ts), never here.
"""

from __future__ import annotations

from pydantic import BaseModel


class V2TelemetryLap(BaseModel):
    driver_id: str
    lap_number: int
    observed_at_s: float
    lap_time_s: float | None = None
    sector_1_s: float | None = None
    sector_2_s: float | None = None
    sector_3_s: float | None = None
    compound: str | None = None
    tyre_life: int | None = None
    stint_number: int | None = None
    stint_lap: int | None = None
    fresh_tyre: bool | None = None
    pit_entry: bool | None = None
    pit_exit: bool | None = None
    track_status: str | None = None
    deleted: bool | None = None
    is_accurate: bool | None = None
    fastf1_generated: bool | None = None


class V2TelemetryStint(BaseModel):
    driver_id: str
    stint_number: int
    compound: str | None = None
    fresh_tyre: bool | None = None
    start_lap: int | None = None
    end_lap: int | None = None
    start_observed_at_s: float | None = None
    end_observed_at_s: float | None = None
    pit_in_lap: int | None = None
    pit_out_lap: int | None = None
    tyre_age_at_start: int | None = None


class V2TelemetryResponse(BaseModel):
    race_id: str
    telemetry_contract_version: str
    lap_count: int
    stint_count: int
    laps: list[V2TelemetryLap]
    stints: list[V2TelemetryStint]
