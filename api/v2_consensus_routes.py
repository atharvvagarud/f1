"""V2 consensus HTTP routes (V3.8F).

MODEL / SIMULATION / DISAGREEMENT product comparison over an exact
historical state. Thin routing only: request parsing via
``api.v2_consensus_schemas``, orchestration via
``api.v2_consensus_service``, domain-error → HTTP mapping below.

Error mapping (mirrors frozen Phase-4/5/6 conventions):
- unknown race (registry miss, incl. any 2025 race) → 404 ``unknown_race``
- well-formed race but no exact anchor state → 422 ``unknown_state``
- well-formed exact state a source cannot serve (incl. explicit 2025
  PRODUCT_EXCLUDED refusal) → 422 ``consensus_unsupported`` with the
  stable machine-readable ``reason`` plus a concise detail. No fallback,
  no driver dropping, no nearest state.
- fixture/cache artifact missing/corrupt → 503 ``parameter_unavailable``
  (never disguised as unsupported, never a silent fallback)
- anything else → 500 ``internal`` (never disguised as a client error)

Error bodies never carry stack traces, filesystem paths, or model
internals. No fourth probability exists on any path in this module.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from api import v2_consensus_schemas as S
from api.v2_consensus_service import (
    ConsensusArtifactUnavailableError,
    ConsensusUnknownStateError,
    ConsensusUnsupportedError,
    V2ConsensusService,
    get_v2_consensus_service,
)
from raceintel.race_state.race_state_reconstruction import RaceNotFoundError

router = APIRouter(prefix="/v2", tags=["v2-consensus"])


def _unknown_race(race_id: str) -> dict:
    return {"error": "unknown_race",
            "detail": f"no served race {race_id!r}"}


def _unknown_state(race_id: str) -> dict:
    return {"error": "unknown_state",
            "detail": f"no exact anchor state for {race_id!r}"}


def _unsupported(exc: ConsensusUnsupportedError) -> dict:
    return {"error": "consensus_unsupported",
            "reason": exc.reason,
            "detail": exc.detail}


def _unavailable(exc: ConsensusArtifactUnavailableError) -> dict:
    return {"error": "parameter_unavailable", "detail": str(exc)}


def _internal() -> dict:
    return {"error": "internal", "detail": "unexpected consensus failure"}


def _anchor(race_id: str, anchor_lap_number: int,
            anchor_state_time_s: float | None) -> dict:
    return {"race_id": race_id,
            "anchor_lap_number": anchor_lap_number,
            "anchor_state_time_s": anchor_state_time_s}


@router.get("/consensus/availability")
def consensus_availability(
        race_id: str = Query(...),
        anchor_lap_number: int = Query(..., ge=1),
        anchor_state_time_s: float | None = Query(default=None),
        service: V2ConsensusService = Depends(
            get_v2_consensus_service)):
    """Cheap availability only: never triggers expensive work."""
    try:
        return service.availability(
            _anchor(race_id, anchor_lap_number, anchor_state_time_s))
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(race_id))
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())


@router.post("/consensus/compare", response_model=S.ConsensusCompareResponse)
def consensus_compare(payload: S.ConsensusAnchor,
                      service: V2ConsensusService = Depends(
                          get_v2_consensus_service)):
    """Strict typed MODEL / SIMULATION / DISAGREEMENT comparison."""
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
        "state": result["state"],
        "availability": {
            "race_id": avail["race_id"],
            "anchor_lap_number": avail["anchor_lap_number"],
            "anchor_state_time_s": avail["anchor_state_time_s"],
            "model": avail["model"],
            "model_reason": avail["model_reason"],
            "simulation": avail["simulation"],
            "simulation_reason": avail["simulation_reason"],
            "comparison": avail["comparison"],
        },
        "model": {"source": result["model"]["source"],
                  "probability_family":
                      result["model"]["probability_family"],
                  "target": result["model"]["target"],
                  "drivers": [
                      {"driver_id": d["driver_id"],
                       "p_model": d["p_model"]}
                      for d in result["disagreement"]["drivers"]]},
        "simulation": {"source": result["simulation"]["source"],
                       "probability_family":
                           result["simulation"]["probability_family"],
                       "target": result["simulation"]["target"],
                       "drivers": [
                           {"driver_id": d["driver_id"],
                            "p_simulation": d["p_simulation"],
                            "valid_trials": d["sampling"]["valid_trials"]}
                           for d in result["disagreement"]["drivers"]]},
        "disagreement": {
            "signed_gap_definition":
                result["disagreement"]["signed_gap_definition"],
            "drivers": [
                {"driver_id": d["driver_id"],
                 "p_model": d["p_model"],
                 "p_simulation": d["p_simulation"],
                 "signed_gap": d["signed_gap"],
                 "absolute_gap": d["absolute_gap"],
                 "model_inside_simulation_interval":
                     d["model_inside_simulation_interval"],
                 "valid_trials": d["sampling"]["valid_trials"],
                 "sampling_se": d["sampling"]["sampling_se"],
                 "wilson_95": d["sampling"]["wilson_95"]}
                for d in result["disagreement"]["drivers"]],
            "rank": result["disagreement"]["rank"],
            "leader": result["disagreement"]["leader"],
            "top_k": result["disagreement"]["top_k"],
        },
        "provenance": result["provenance"],
    }
