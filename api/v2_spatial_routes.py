"""V2 spatial HTTP routes (Phase-12 P12-5).

Replay-bound spatial surface over ``V2SpatialService``. Thin routing
only: request parsing via ``api.v2_spatial_schemas``, orchestration via
``api.v2_spatial_service``, domain-error → HTTP mapping below. The
replay family (``api/v2_replay_routes.py``) and the P12-4 resolver are
untouched and unimported here beyond the service boundary.

Canonical replay-facing frame identity is the path ``frame_index``
(resolved to the authoritative ``anchor_state_time_s`` inside the
service): no direct ``time_s`` query exists, so frontend rounding can
never change scientific state.

Error mapping (mirrors replay conventions where they exist):
- unknown race (served-registry miss, incl. any unserved-season race)
  → 404 ``unknown_race``
- valid race, unknown frame index → 404 ``unknown_frame``
- malformed index/query (negative frame, bad driver/history bounds) →
  422 via FastAPI validation
- valid race with no resolvable observations or no renderable
  geometry (incl. the unsupported 2024-r09-R) → 404
  ``spatial_unavailable`` (non-spatial replay keeps working)
- geometry source-identity mismatch → 500 ``spatial_integrity_error``
  (fail closed, never a fake empty success)
- anything else → 500 ``internal`` (never disguised as client error)

Error bodies never carry stack traces, filesystem paths, or model
internals.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse

from api import v2_spatial_schemas as S
from api.v2_spatial_service import (
    MAX_HISTORY_S,
    V2SpatialService,
    get_v2_spatial_service,
)
from raceintel.race_state.race_state_reconstruction import RaceNotFoundError
from raceintel.replay.replay import ReplayTimelineError
from raceintel.spatial.errors import (
    SpatialArtifactUnavailableError,
    SpatialGeometryMismatchError,
)
from api.v2_replay_service import ReplayFrameNotFoundError

router = APIRouter(prefix="/v2", tags=["v2-spatial"])


def _unknown_race(race_id: str) -> dict:
    return {"error": "unknown_race",
            "detail": f"no served replay race {race_id!r}"}


def _unknown_frame(race_id: str, frame_index: int) -> dict:
    return {"error": "unknown_frame",
            "detail": f"no replay frame {frame_index!r} "
                      f"for race {race_id!r}"}


def _unavailable(race_id: str) -> dict:
    return {"error": "spatial_unavailable",
            "detail": f"no servable spatial state for race {race_id!r}"}


def _integrity() -> dict:
    return {"error": "spatial_integrity_error",
            "detail": "spatial geometry identity does not match "
                      "observations"}


def _internal() -> dict:
    return {"error": "internal", "detail": "unexpected spatial failure"}


@router.get("/races/{race_id}/spatial/geometry",
            response_model=S.V2SpatialGeometryResponse)
def spatial_geometry(
        race_id: str,
        service: V2SpatialService = Depends(get_v2_spatial_service)):
    """Renderer-ready circuit geometry (bounded, deterministic)."""
    try:
        payload = service.get_geometry(race_id)
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(race_id))
    except SpatialGeometryMismatchError:
        return JSONResponse(status_code=500, content=_integrity())
    except SpatialArtifactUnavailableError:
        return JSONResponse(status_code=404,
                            content=_unavailable(race_id))
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())
    return S.V2SpatialGeometryResponse(
        race_id=payload["race_id"],
        schema_version=payload["schema_version"],
        algorithm_version=payload["algorithm_version"],
        geometry_sha256=payload["geometry_sha256"],
        main_track=S.V2SpatialTrackResponse(**payload["main_track"]),
        pit_lane=(None if payload["pit_lane"] is None
                  else S.V2SpatialTrackResponse(**payload["pit_lane"])),
        pit_status=payload["pit_status"],
        render_bounds=dict(payload["render_bounds"]))


@router.get("/races/{race_id}/spatial/frame/{frame_index}",
            response_model=S.V2SpatialFrameResponse)
def spatial_frame(
        race_id: str,
        frame_index: int = Path(ge=0),
        service: V2SpatialService = Depends(get_v2_spatial_service)):
    """Spatial state at the authoritative replay time of one frame."""
    try:
        payload = service.get_frame(race_id, frame_index)
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(race_id))
    except (ReplayFrameNotFoundError, ReplayTimelineError):
        return JSONResponse(status_code=404,
                            content=_unknown_frame(race_id, frame_index))
    except SpatialGeometryMismatchError:
        return JSONResponse(status_code=500, content=_integrity())
    except SpatialArtifactUnavailableError:
        return JSONResponse(status_code=404,
                            content=_unavailable(race_id))
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())
    return S.V2SpatialFrameResponse(
        race_id=payload["race_id"],
        frame_index=payload["frame_index"],
        query_time_s=payload["query_time_s"],
        source_status=payload["source_status"],
        geometry_sha256=payload["geometry_sha256"],
        observation_content_sha256=payload[
            "observation_content_sha256"],
        resolver_contract_version=payload["resolver_contract_version"],
        fresh_count=payload["fresh_count"],
        stale_count=payload["stale_count"],
        unavailable_count=payload["unavailable_count"],
        drivers=[S.V2SpatialDriverResponse(**entry)
                 for entry in payload["drivers"]])


@router.get("/races/{race_id}/spatial/window/{frame_index}",
            response_model=S.V2SpatialWindowResponse)
def spatial_window(
        race_id: str,
        frame_index: int = Path(ge=0),
        driver_number: int = Query(ge=1, le=99),
        history_s: float = Query(default=5.0, ge=0.0,
                                 le=MAX_HISTORY_S),
        service: V2SpatialService = Depends(get_v2_spatial_service)):
    """Bounded causal trail for one driver at one replay frame."""
    try:
        payload = service.get_window(race_id, frame_index,
                                     driver_number, history_s)
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(race_id))
    except (ReplayFrameNotFoundError, ReplayTimelineError):
        return JSONResponse(status_code=404,
                            content=_unknown_frame(race_id, frame_index))
    except SpatialGeometryMismatchError:
        return JSONResponse(status_code=500, content=_integrity())
    except SpatialArtifactUnavailableError:
        return JSONResponse(status_code=404,
                            content=_unavailable(race_id))
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())
    return S.V2SpatialWindowResponse(
        race_id=payload["race_id"],
        frame_index=payload["frame_index"],
        driver_number=payload["driver_number"],
        query_time_s=payload["query_time_s"],
        history_s=payload["history_s"],
        sample_count=payload["sample_count"],
        samples=[S.V2SpatialWindowSampleResponse(**entry)
                 for entry in payload["samples"]])
