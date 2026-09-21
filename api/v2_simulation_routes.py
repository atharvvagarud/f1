"""V2 simulation HTTP routes (Phase-6 R8).

Additive simulation family over the read-only ``V2SimulationService``. Thin
routing only: request parsing via ``api.v2_simulation_schemas``, orchestration
via ``api.v2_simulation_service``, domain-error → HTTP mapping below. The
Phase-4 ``api/v2_routes.py`` and Phase-5 ``api/v2_replay_routes.py`` families
are untouched and unimported here.

Error mapping (mirrors frozen Phase-4/5 conventions):
- unknown race (2018–2024 registry miss, incl. any 2025 race) → 404
  ``unknown_race``
- exact-anchor miss / malformed anchor / invalid reconstructed state → 422
  ``unknown_state``
- a well-formed but un-simulatable factual state (wet/neutralized/red,
  missing tyre age, unobserved or non-contemporaneous roster member, missing
  parameter support, temporal incompatibility) → 422 ``simulation_unsupported``
  with the stable machine-readable ``reason`` plus a concise detail. No
  fallback, no driver dropping, no retirement inference, no nearest state.
- frozen parameter artifact missing/corrupt → 503 ``parameter_unavailable``
  (never a runtime estimation)
- anything else → 500 ``internal`` (never disguised as a client error)

Error bodies never carry stack traces, filesystem paths, or model internals.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api import v2_simulation_schemas as S
from api.v2_simulation_service import (
    V2SimulationService,
    get_v2_simulation_service,
)
from v2.race_state import InvalidRaceStateError
from v2.race_state_reconstruction import (
    AnchorNotFoundError,
    RaceNotFoundError,
    RaceStateReconstructionError,
)
from v2.simulation.adapter import SimulationUnavailableError
from v2.simulation.engine import SimulationUnsupportedError

router = APIRouter(prefix="/v2", tags=["v2-simulation"])


def _unknown_race(race_id: str) -> dict:
    return {"error": "unknown_race",
            "detail": f"no served race {race_id!r}"}


def _unknown_state(race_id: str) -> dict:
    return {"error": "unknown_state",
            "detail": f"no exact anchor state for {race_id!r}; "
                      f"list exact anchors via /v2/races/{race_id}/states"}


def _unsupported(exc) -> dict:
    return {"error": "simulation_unsupported",
            "reason": exc.reason,
            "detail": getattr(exc, "detail", str(exc))}


def _internal() -> dict:
    return {"error": "internal", "detail": "unexpected simulation failure"}


@router.post("/simulations/race", response_model=S.V2SimulationResponse)
def simulate_race(payload: S.V2SimulationRequest,
                  service: V2SimulationService = Depends(
                      get_v2_simulation_service)):
    """Aggregate Monte Carlo outcome frequencies for one exact historical state."""
    try:
        return service.run_simulation(
            race_id=payload.race_id,
            anchor_driver_id=payload.anchor_driver_id,
            anchor_lap_number=payload.anchor_lap_number,
            anchor_state_time_s=payload.anchor_state_time_s,
            simulation_count=payload.simulation_count,
            master_seed=payload.master_seed)
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(payload.race_id))
    except (AnchorNotFoundError, InvalidRaceStateError,
            RaceStateReconstructionError):
        return JSONResponse(status_code=422,
                            content=_unknown_state(payload.race_id))
    except (SimulationUnsupportedError, SimulationUnavailableError) as exc:
        return JSONResponse(status_code=422, content=_unsupported(exc))
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())
