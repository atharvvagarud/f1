"""V2 HTTP routes (Phase-4 R5).

Versioned boundary over the frozen Phase-4 pipeline. Thin routing only:
request parsing via ``api.v2_schemas``, pipeline via ``api.v2_service``,
domain-error → HTTP mapping below. The legacy universe (legacy routes
plus the legacy inference module) is untouched and unimported here.

Error mapping:
- unknown race → 404 ``unknown_race``
- exact-anchor miss / malformed anchor → 422 ``unknown_state``
- corpus/feature/prediction contract violation on the serving path
  (cannot happen on valid anchors; indicates freeze drift or server
  corruption) → 500 ``internal``
- serving artifact missing/invalid → 503 ``model_unavailable``
  (no fallback, no legacy route, no fake probabilities)
- anything else → 500 ``internal`` (never disguised as client error)

Error bodies never carry stack traces, filesystem paths, or model
internals.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from api import v2_schemas as S
from api.v2_service import V2Service, get_v2_service
from v2.model_lab.errors import ServingArtifactError
from v2.prediction import (
    PredictionAlignmentError,
    PredictionEngineError,
    PredictionFeatureMismatchError,
    PredictionOutputError,
    ProductionModelUnavailableError,
)
from v2.race_state import InvalidRaceStateError
from v2.race_state_features import RaceStateFeatureMismatchError
from v2.race_state_reconstruction import (
    AnchorNotFoundError,
    RaceNotFoundError,
    RaceStateReconstructionError,
)

router = APIRouter(prefix="/v2", tags=["v2"])

STATES_DEFAULT_LIMIT = 100
STATES_MAX_LIMIT = 500


def _unknown_race(race_id: str) -> dict:
    return {"error": "unknown_race",
            "detail": f"no served race {race_id!r}"}


def _unknown_state(race_id: str) -> dict:
    return {"error": "unknown_state",
            "detail": f"no exact anchor state for {race_id!r}; "
                      f"list exact anchors via /v2/races/{race_id}/states"}


def _internal() -> dict:
    return {"error": "internal", "detail": "unexpected serving failure"}


def _unavailable() -> dict:
    return {"error": "model_unavailable",
            "detail": "frozen production model unavailable"}


def _state_response(payload: dict) -> S.V2RaceStateResponse:
    return S.V2RaceStateResponse(**payload)


def _snapshot_response(payload: dict) -> S.V2PredictionSnapshotResponse:
    # Independent binary probabilities pass through verbatim: the domain
    # already validated them and this layer never renormalizes.
    return S.V2PredictionSnapshotResponse(**payload)


@router.get("/races", response_model=S.V2RaceListResponse)
def list_races(service: V2Service = Depends(get_v2_service)):
    races = service.list_races()
    return {"races": races, "count": len(races)}


@router.get("/races/{race_id}/states",
            response_model=S.V2StateListResponse)
def list_states(race_id: str,
                offset: int = Query(default=0, ge=0),
                limit: int = Query(default=STATES_DEFAULT_LIMIT, ge=1,
                                   le=STATES_MAX_LIMIT),
                service: V2Service = Depends(get_v2_service)):
    try:
        return service.list_anchors(race_id, offset=offset, limit=limit)
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(race_id))
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())


@router.get("/races/{race_id}/state",
            response_model=S.V2RaceStateResponse)
def get_state(race_id: str,
              anchor_driver_id: str,
              anchor_lap_number: int = Query(ge=1),
              anchor_state_time_s: float = Query(allow_inf_nan=False),
              service: V2Service = Depends(get_v2_service)):
    try:
        state = service.get_state(race_id, anchor_driver_id,
                                  anchor_lap_number, anchor_state_time_s)
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(race_id))
    except (AnchorNotFoundError, InvalidRaceStateError,
            RaceStateReconstructionError):
        return JSONResponse(status_code=422,
                            content=_unknown_state(race_id))
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())
    return _state_response(state.to_dict())


@router.post("/predictions/winner-snapshot",
             response_model=S.V2PredictionSnapshotResponse)
def predict_winner_snapshot(payload: S.V2AnchorRequest,
                            service: V2Service = Depends(get_v2_service)):
    """Frozen winner snapshot for one exact anchor (server owns features)."""
    try:
        snapshot = service.predict_snapshot(
            payload.race_id, payload.anchor_driver_id,
            payload.anchor_lap_number, payload.anchor_state_time_s)
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(payload.race_id))
    except (AnchorNotFoundError, InvalidRaceStateError,
            RaceStateReconstructionError):
        return JSONResponse(status_code=422,
                            content=_unknown_state(payload.race_id))
    except (ProductionModelUnavailableError, ServingArtifactError):
        return JSONResponse(status_code=503, content=_unavailable())
    except (PredictionFeatureMismatchError, PredictionAlignmentError,
            PredictionOutputError, RaceStateFeatureMismatchError,
            PredictionEngineError):
        return JSONResponse(status_code=500, content=_internal())
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())
    return _snapshot_response(snapshot.to_dict())
