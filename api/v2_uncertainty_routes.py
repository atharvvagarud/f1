"""V3.9C uncertainty API routes (typed errors, no silent fallback)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from api.v2_consensus_service import (
    ConsensusArtifactUnavailableError,
    ConsensusUnknownStateError,
    ConsensusUnsupportedError,
)
from api.v2_uncertainty_service import (
    V2UncertaintyService,
    get_v2_uncertainty_service,
)
from raceintel.race_state.race_state_reconstruction import RaceNotFoundError

from api import v2_uncertainty_schemas as S

router = APIRouter(prefix="/v2", tags=["v2-uncertainty"])


def _unknown_race(race_id: str) -> dict:
    return {"error": "unknown_race",
            "detail": f"no served race {race_id!r}"}


def _unknown_state(race_id: str) -> dict:
    return {"error": "unknown_state",
            "detail": f"no exact anchor state for {race_id!r}"}


def _unsupported(exc: ConsensusUnsupportedError) -> dict:
    return {"error": "uncertainty_unsupported",
            "reason": exc.reason,
            "detail": exc.detail}


def _unavailable(exc: ConsensusArtifactUnavailableError) -> dict:
    return {"error": "parameter_unavailable", "detail": str(exc)}


def _internal() -> dict:
    return {"error": "internal", "detail": "unexpected uncertainty failure"}


def _anchor(race_id: str, anchor_lap_number: int,
            anchor_state_time_s: float | None) -> dict:
    return {"race_id": race_id,
            "anchor_lap_number": anchor_lap_number,
            "anchor_state_time_s": anchor_state_time_s}


@router.get("/uncertainty/availability")
def uncertainty_availability(
        race_id: str = Query(...),
        anchor_lap_number: int = Query(..., ge=1),
        anchor_state_time_s: float | None = Query(default=None),
        service: V2UncertaintyService = Depends(
            get_v2_uncertainty_service)):
    """Cheap availability only: never triggers expensive work."""
    try:
        return service.availability(
            _anchor(race_id, anchor_lap_number, anchor_state_time_s))
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(race_id))
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())


@router.post("/uncertainty/compare",
             response_model=S.UncertaintyCompareResponse)
def uncertainty_compare(payload: S.UncertaintyAnchor,
                        service: V2UncertaintyService = Depends(
                            get_v2_uncertainty_service)):
    """Strict typed uncertainty bundle (U1 + U2 + explicit U3 status)."""
    anchor = _anchor(payload.race_id, payload.anchor_lap_number,
                     payload.anchor_state_time_s)
    try:
        result = service.compare(anchor)
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(payload.race_id))
    except ConsensusUnknownStateError:
        return JSONResponse(status_code=422,
                            content=_unknown_state(payload.race_id))
    except ConsensusUnsupportedError as exc:
        return JSONResponse(status_code=422, content=_unsupported(exc))
    except ConsensusArtifactUnavailableError as exc:
        return JSONResponse(status_code=503, content=_unavailable(exc))
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())
    avail = result["availability"]
    return {
        "schema_version": result["schema_version"],
        "metric_implementation": result["metric_implementation"],
        "state": result["state"],
        "sources": result["sources"],
        "drivers": result["drivers"],
        "field": result["field"],
        "simulator_sensitivity": result["simulator_sensitivity"],
        "availability": {
            "race_id": avail["race_id"],
            "anchor_lap_number": avail["anchor_lap_number"],
            "anchor_state_time_s": avail["anchor_state_time_s"],
            "model": avail["model"],
            "model_reason": avail["model_reason"],
            "simulation": avail["simulation"],
            "simulation_reason": avail["simulation_reason"],
            "comparison": avail["comparison"],
            "simulator_sensitivity": avail["simulator_sensitivity"],
        },
        "provenance": result["provenance"],
    }
