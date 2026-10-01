"""V2 replay HTTP routes (Phase-5 R4).

Additive replay family over the read-only ``V2ReplayService``. Thin
routing only: request parsing via ``api.v2_replay_schemas``, replay via
``api.v2_replay_service``, domain-error → HTTP mapping below. The
Phase-4 ``api/v2_routes.py`` family and the legacy universe are
untouched and unimported here.

Error mapping (mirrors Phase-4 conventions where they exist):
- unknown race (2018–2024 registry miss, incl. any 2025 race) → 404
  ``unknown_race``
- valid race, unknown frame index → 404 ``unknown_frame``
- malformed index/pagination (negative frame, bad offset/limit) → 422
  via FastAPI validation
- frame exists but is not a prediction checkpoint → 404
  ``not_prediction_checkpoint`` (+ nearest-checkpoint pointers; the
  past prediction is NEVER substituted for the frame)
- checkpoint exists but its cache is missing/stale/incomplete/corrupt
  → 503 ``prediction_unavailable`` (never generated on this path)
- factual reconstruction contract violation on a valid frame → 500
  ``internal``
- anything else → 500 ``internal`` (never disguised as client error)

Error bodies never carry stack traces, filesystem paths, or model
internals.

CACHE RULE: no route here can generate a prediction — the service holds
no engine and misses surface as 503, never a synchronous model run.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse

from api import v2_replay_schemas as S
from api.v2_replay_service import (
    NotPredictionCheckpointError,
    PredictionUnavailableError,
    ReplayFrameNotFoundError,
    V2ReplayService,
    get_v2_replay_service,
)
from raceintel.race_state.race_state_reconstruction import RaceNotFoundError
from raceintel.replay.replay import ReplayTimelineError

router = APIRouter(prefix="/v2", tags=["v2-replay"])

REPLAY_DEFAULT_LIMIT = 100
REPLAY_MAX_LIMIT = 500


def _unknown_race(race_id: str) -> dict:
    return {"error": "unknown_race",
            "detail": f"no served replay race {race_id!r}"}


def _unknown_frame(race_id: str, frame_index: int) -> dict:
    return {"error": "unknown_frame",
            "detail": f"no replay frame {frame_index!r} "
                      f"for race {race_id!r}"}


def _not_checkpoint(exc: NotPredictionCheckpointError) -> dict:
    return {"error": "not_prediction_checkpoint",
            "detail": f"frame {exc.frame_index} in race "
                      f"{exc.race_id!r} carries no cached model checkpoint; "
                      f"use the nearest checkpoint pointer explicitly",
            "previous_prediction_checkpoint_frame": exc.previous_frame,
            "next_prediction_checkpoint_frame": exc.next_frame}


def _unavailable(exc: PredictionUnavailableError) -> dict:
    return {"error": "prediction_unavailable",
            "detail": f"cached prediction unavailable for frame "
                      f"{exc.frame_index} in race {exc.race_id!r}; "
                      f"checkpoints are generated offline only",
            "reason": exc.reason}


def _internal() -> dict:
    return {"error": "internal", "detail": "unexpected replay failure"}


@router.get("/races/{race_id}/replay/timeline",
            response_model=S.V2ReplayTimelineResponse)
def replay_timeline(race_id: str,
                    offset: int = Query(default=0, ge=0),
                    limit: int = Query(default=REPLAY_DEFAULT_LIMIT, ge=1,
                                       le=REPLAY_MAX_LIMIT),
                    service: V2ReplayService = Depends(
                        get_v2_replay_service)):
    """Deterministic paginated ReplayFrame metadata (reconstruction-free)."""
    try:
        payload = service.list_frames(race_id, offset=offset, limit=limit)
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(race_id))
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())
    return S.V2ReplayTimelineResponse(
        race_id=payload["race_id"],
        replay_contract_version=payload["replay_contract_version"],
        total_frames=payload["total_frames"],
        offset=payload["offset"],
        limit=payload["limit"],
        returned_count=payload["returned_count"],
        frames=[S.V2ReplayFrameMeta(**frame)
                for frame in payload["frames"]])


@router.get("/races/{race_id}/replay/frames/{frame_index}",
            response_model=S.V2ReplayFrameResponse)
def replay_frame(race_id: str,
                 frame_index: int = Path(ge=0),
                 service: V2ReplayService = Depends(
                     get_v2_replay_service)):
    """Factual frame: ReplayFrame identity + exact R2 RaceState + nav."""
    try:
        result = service.get_frame(race_id, frame_index)
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(race_id))
    except (ReplayFrameNotFoundError, ReplayTimelineError):
        return JSONResponse(status_code=404,
                            content=_unknown_frame(race_id, frame_index))
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())
    return S.V2ReplayFrameResponse(
        frame=S.V2ReplayFrameMeta(**result["frame"]),
        state=S.V2RaceStateResponse(**result["state"].to_dict()),
        has_previous=result["has_previous"],
        has_next=result["has_next"],
        previous_frame_index=result["previous_frame_index"],
        next_frame_index=result["next_frame_index"],
        leader_lap=result["leader_lap"],
        is_prediction_checkpoint=result["is_prediction_checkpoint"],
        checkpoint_reasons=result["checkpoint_reasons"],
        prediction_cache_available=result["prediction_cache_available"],
        previous_prediction_checkpoint_frame=result[
            "previous_prediction_checkpoint_frame"],
        next_prediction_checkpoint_frame=result[
            "next_prediction_checkpoint_frame"])


@router.get("/races/{race_id}/replay/predictions/{frame_index}",
            response_model=S.V2ReplayPredictionResponse)
def replay_prediction(race_id: str,
                      frame_index: int = Path(ge=0),
                      service: V2ReplayService = Depends(
                          get_v2_replay_service)):
    """Cached checkpoint prediction only — NEVER generated on this path."""
    try:
        result = service.get_prediction(race_id, frame_index)
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(race_id))
    except (ReplayFrameNotFoundError, ReplayTimelineError):
        return JSONResponse(status_code=404,
                            content=_unknown_frame(race_id, frame_index))
    except NotPredictionCheckpointError as exc:
        return JSONResponse(status_code=404, content=_not_checkpoint(exc))
    except PredictionUnavailableError as exc:
        return JSONResponse(status_code=503, content=_unavailable(exc))
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())
    return S.V2ReplayPredictionResponse(
        frame=S.V2ReplayFrameMeta(**result["frame"]),
        checkpoint=S.V2CheckpointMeta(
            frame_index=result["checkpoint"]["frame_index"],
            reasons=list(result["checkpoint"]["reasons"]),
            leader_lap=result["checkpoint"]["leader_lap"],
            replay_contract_version=result["checkpoint"][
                "replay_contract_version"],
            prediction_contract_version=result["checkpoint"][
                "prediction_contract_version"]),
        prediction=S.V2PredictionSnapshotResponse(**result["prediction"]),
        cache_status="HIT")


@router.get("/races/{race_id}/replay/probability-timeline",
            response_model=S.V2ProbabilityTimelineResponse)
def replay_probability_timeline(
        race_id: str,
        service: V2ReplayService = Depends(get_v2_replay_service)):
    """Cached probability series only — NEVER generated on this path."""
    try:
        result = service.get_probability_timeline(race_id)
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(race_id))
    except PredictionUnavailableError as exc:
        return JSONResponse(status_code=503, content=_unavailable(exc))
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())
    return S.V2ProbabilityTimelineResponse(
        race_id=result["race_id"],
        replay_contract_version=result["replay_contract_version"],
        prediction_contract_version=result["prediction_contract_version"],
        probability_timeline_contract_version=result[
            "probability_timeline_contract_version"],
        probability_semantics=result["probability_semantics"],
        model=result["model"],
        timeline_identity=result["timeline_identity"],
        checkpoints=[S.V2ProbabilityCheckpointResponse(**entry)
                     for entry in result["checkpoints"]],
        driver_series=[
            S.V2DriverProbabilitySeriesResponse(
                driver_id=series["driver_id"],
                points=[S.V2DriverProbabilityPointResponse(**point)
                        for point in series["points"]])
            for series in result["driver_series"]])
