"""V2 spatial HTTP schemas (Phase-12 P12-5).

Pydantic representations of the renderer-ready spatial surface. These
public DTOs are intentionally narrower than the internal P12-2/P12-3
artifacts: the internal geometry record may evolve without silently
changing the API. Routes convert resolver/artifact payloads into these
models, never the reverse.

No raw observation corpus, no absolute paths, no provenance clutter.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class V2SpatialTrackResponse(BaseModel):
    """One SVG-ready polyline (already in normalized render space)."""

    points: list[list[float]]
    n_points: int
    closed_loop: bool = False


class V2SpatialGeometryResponse(BaseModel):
    """Renderer-ready circuit geometry for one race."""

    race_id: str
    schema_version: str
    algorithm_version: str
    geometry_sha256: str
    main_track: V2SpatialTrackResponse
    pit_lane: V2SpatialTrackResponse | None = None
    pit_status: str
    render_bounds: dict[str, float]


class V2SpatialDriverResponse(BaseModel):
    """One driver's resolved spatial state at the replay query time."""

    driver_id: str | None = None
    driver_number: int | None = None
    availability: str
    observation_time_s: float | None = None
    age_s: float | None = None
    render_x: float | None = None
    render_y: float | None = None
    outside_viewport: bool = False


class V2SpatialFrameResponse(BaseModel):
    """Replay-synchronized spatial frame (one clock, one universe)."""

    race_id: str
    frame_index: int
    query_time_s: float
    source_status: str
    geometry_sha256: str | None = None
    observation_content_sha256: str
    resolver_contract_version: str
    fresh_count: int = Field(ge=0)
    stale_count: int = Field(ge=0)
    unavailable_count: int = Field(ge=0)
    drivers: list[V2SpatialDriverResponse]


class V2SpatialWindowSampleResponse(BaseModel):
    """One causal trail sample (always ``sample_time <= T``)."""

    observation_time_s: float
    render_x: float | None = None
    render_y: float | None = None


class V2SpatialWindowResponse(BaseModel):
    """Bounded causal trail for one driver at one replay frame."""

    race_id: str
    frame_index: int
    driver_number: int
    query_time_s: float
    history_s: float
    sample_count: int = Field(ge=0)
    samples: list[V2SpatialWindowSampleResponse]


class V2SpatialErrorResponse(BaseModel):
    """Documented error shape; routes return these as plain JSON bodies."""

    error: str
    detail: str = ""
