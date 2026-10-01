"""V2 prediction-change HTTP route (Phase-8 E5).

Additive read-only endpoint over ``V2TimelineExplanationService``. Thin
routing only: the change mathematics lives in
``raceintel.explainability.timeline_explainability`` and orchestration in
``api.v2_timeline_explanation_service``; nothing is computed here.

The endpoint compares the SELECTED prediction checkpoint with the driver's
PREVIOUS prediction checkpoint in the same race. It never snaps an arbitrary
frame to a nearest checkpoint.

Product states (HTTP 200):
- ``AVAILABLE`` — exact A -> B change explanation present
- ``NO_PREVIOUS_CHECKPOINT`` — selected checkpoint is the first one
- ``COMPARISON_UNAVAILABLE`` — driver not observable / null probability at
  an endpoint (explicit reason)

Error mapping (mirrors the R4 / E4 replay family):
- unknown race (2018-2024 registry miss, incl. any 2025 race) -> 404
  ``unknown_race``
- valid race, unknown frame index -> 404 ``unknown_frame``
- frame is not a prediction checkpoint -> 404
  ``not_prediction_checkpoint`` (+ nearest-checkpoint pointers; never snapped)
- checkpoint cache missing/stale/incomplete/corrupt -> 503
  ``prediction_unavailable`` (never generated on this path)
- driver not in the checkpoint roster -> 404 ``unknown_driver``
- exact frozen feature row unavailable / reconstruction failure -> 500
  ``internal`` (fail closed; never a fabricated explanation)
- anything else -> 500 ``internal``

Error bodies never carry stack traces, filesystem paths, or model internals.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path
from fastapi.responses import JSONResponse

from api import v2_timeline_explanation_schemas as S
from api.v2_explanation_service import (
    ExplanationFeatureUnavailableError,
    UnknownDriverError,
)
from api.v2_replay_service import (
    NotPredictionCheckpointError,
    PredictionUnavailableError,
    ReplayFrameNotFoundError,
)
from api.v2_timeline_explanation_service import (
    V2TimelineExplanationService,
    get_v2_timeline_explanation_service,
)
from raceintel.explainability.local_explainability import LocalExplanationError
from raceintel.race_state.race_state_reconstruction import RaceNotFoundError
from raceintel.replay.replay import ReplayTimelineError
from raceintel.explainability.timeline_explainability import TimelineExplanationError

router = APIRouter(prefix="/v2", tags=["v2-explainability"])


def _unknown_race(race_id: str) -> dict:
    return {"error": "unknown_race",
            "detail": f"no served replay race {race_id!r}"}


def _unknown_frame(race_id: str, frame_index: int) -> dict:
    return {"error": "unknown_frame",
            "detail": f"no replay frame {frame_index!r} for race {race_id!r}"}


def _not_checkpoint(exc: NotPredictionCheckpointError) -> dict:
    return {"error": "not_prediction_checkpoint",
            "detail": f"frame {exc.frame_index} in race {exc.race_id!r} "
                      f"carries no cached model checkpoint; change "
                      f"explanations are served only for exact checkpoints",
            "previous_prediction_checkpoint_frame": exc.previous_frame,
            "next_prediction_checkpoint_frame": exc.next_frame}


def _unavailable(exc: PredictionUnavailableError) -> dict:
    return {"error": "prediction_unavailable",
            "detail": f"cached prediction unavailable for frame "
                      f"{exc.frame_index} in race {exc.race_id!r}; "
                      f"checkpoints are generated offline only",
            "reason": exc.reason}


def _unknown_driver(exc: UnknownDriverError) -> dict:
    return {"error": "unknown_driver",
            "detail": f"driver {exc.driver_id!r} is not in race "
                      f"{exc.race_id!r} frame {exc.frame_index}",
            "driver_id": exc.driver_id}


def _internal() -> dict:
    return {"error": "internal", "detail": "unexpected change failure"}


@router.get(
    "/replay/{race_id}/frames/{frame_index}/predictions/"
    "{driver_id}/change",
    response_model=S.V2TimelineChangeResponse)
def replay_prediction_change(
        race_id: str,
        frame_index: int = Path(ge=0),
        driver_id: str = Path(min_length=1),
        service: V2TimelineExplanationService = Depends(
            get_v2_timeline_explanation_service)):
    """Exact change in the frozen model score since the previous checkpoint."""
    try:
        payload = service.get_change(race_id, frame_index, driver_id)
    except RaceNotFoundError:
        return JSONResponse(status_code=404, content=_unknown_race(race_id))
    except (ReplayFrameNotFoundError, ReplayTimelineError):
        return JSONResponse(status_code=404,
                            content=_unknown_frame(race_id, frame_index))
    except NotPredictionCheckpointError as exc:
        return JSONResponse(status_code=404, content=_not_checkpoint(exc))
    except PredictionUnavailableError as exc:
        return JSONResponse(status_code=503, content=_unavailable(exc))
    except UnknownDriverError as exc:
        return JSONResponse(status_code=404, content=_unknown_driver(exc))
    except (ExplanationFeatureUnavailableError, LocalExplanationError,
            TimelineExplanationError):
        return JSONResponse(status_code=500, content=_internal())
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())
    return S.V2TimelineChangeResponse(**payload)
