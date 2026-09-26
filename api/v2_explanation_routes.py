"""V2 local-explanation HTTP route (Phase-8 E4).

Additive read-only endpoint over ``V2ExplanationService``. Thin routing
only: the explanation mathematics lives in ``v2.local_explainability`` and
orchestration in ``api.v2_explanation_service``; nothing is computed here.

Error mapping (mirrors the R4 replay family):
- unknown race (2018-2024 registry miss, incl. any 2025 race) -> 404
  ``unknown_race``
- valid race, unknown frame index -> 404 ``unknown_frame``
- frame is not a prediction checkpoint -> 404
  ``not_prediction_checkpoint`` (+ nearest-checkpoint pointers; never snapped)
- checkpoint cache missing/stale/incomplete/corrupt -> 503
  ``prediction_unavailable`` (never generated on this path)
- driver not in the checkpoint roster -> 404 ``unknown_driver``
- roster driver with no observation at T -> 422 ``driver_not_observable``
- exact frozen feature row unavailable / reconstruction failure -> 500
  ``internal`` (fail closed; never a fabricated explanation)
- anything else -> 500 ``internal``

Error bodies never carry stack traces, filesystem paths, or model internals.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Path

from fastapi.responses import JSONResponse

from api import v2_explanation_schemas as S
from api.v2_explanation_service import (
    DriverNotObservableError,
    ExplanationFeatureUnavailableError,
    UnknownDriverError,
    V2ExplanationService,
    get_v2_explanation_service,
)
from api.v2_replay_service import (
    NotPredictionCheckpointError,
    PredictionUnavailableError,
    ReplayFrameNotFoundError,
)
from v2.local_explainability import LocalExplanationError
from v2.race_state_reconstruction import RaceNotFoundError
from v2.replay import ReplayTimelineError

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
                      f"carries no cached model checkpoint; explanations are "
                      f"served only for exact checkpoints",
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


def _not_observable(exc: DriverNotObservableError) -> dict:
    return {"error": "driver_not_observable",
            "detail": f"driver {exc.driver_id!r} carries no observable state "
                      f"at race {exc.race_id!r} frame {exc.frame_index}",
            "reason": exc.reason,
            "driver_id": exc.driver_id}


def _internal() -> dict:
    return {"error": "internal", "detail": "unexpected explanation failure"}


@router.get(
    "/replay/{race_id}/frames/{frame_index}/predictions/"
    "{driver_id}/explanation",
    response_model=S.V2LocalExplanationResponse)
def replay_prediction_explanation(
        race_id: str,
        frame_index: int = Path(ge=0),
        driver_id: str = Path(min_length=1),
        service: V2ExplanationService = Depends(
            get_v2_explanation_service)):
    """Exact local log-odds explanation of one cached checkpoint prediction."""
    try:
        payload = service.get_explanation(race_id, frame_index, driver_id)
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
    except DriverNotObservableError as exc:
        return JSONResponse(status_code=422, content=_not_observable(exc))
    except (ExplanationFeatureUnavailableError, LocalExplanationError):
        return JSONResponse(status_code=500, content=_internal())
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())
    return S.V2LocalExplanationResponse(**payload)
