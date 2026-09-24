"""V2 strategy HTTP routes (Phase-7 S7).

Additive strategy family over the read-only ``V2StrategyService``. Thin
routing only: request parsing via ``api.v2_strategy_schemas``, orchestration
via ``api.v2_strategy_service``, domain-error → HTTP mapping below. The
Phase-4/5/6 families are untouched and unimported here.

Error mapping (mirrors frozen conventions):
- unknown race (2018–2024 registry miss, incl. any 2025 race) → 404
  ``unknown_race``
- exact-anchor miss / malformed anchor / invalid reconstructed state → 422
  ``unknown_state``
- malformed strategy request, duplicate candidates, candidate-count/count
  combination violations, unknown objective → 422 ``strategy_request_invalid``
  with the stable machine-readable ``reason``
- a well-formed but un-simulatable factual state (wet/neutralized/red,
  missing tyre age, non-contemporaneous roster member, missing parameter
  support, temporal incompatibility) → 200 with ``supported=false`` and the
  canonical ``unsupported_reason``; a target outside the roster is refused the
  same way. No fallback, no fabricated results, no partial table.
- frozen parameter artifact missing/corrupt → 503 ``parameter_unavailable``
- anything else → 500 ``internal`` (never disguised as a client error)

Error bodies never carry stack traces, filesystem paths, or model internals.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api import v2_strategy_schemas as S
from api.v2_strategy_service import (
    StrategyParameterUnavailableError,
    StrategyRequestError,
    V2StrategyService,
    get_v2_strategy_service,
)
from v2.race_state import InvalidRaceStateError
from v2.race_state_reconstruction import (
    AnchorNotFoundError,
    RaceNotFoundError,
    RaceStateReconstructionError,
)
from v2.simulation.adapter import SimulationUnavailableError
from v2.simulation.engine import SimulationUnsupportedError

router = APIRouter(prefix="/v2", tags=["v2-strategy"])


def _unknown_race(race_id: str) -> dict:
    return {"error": "unknown_race",
            "detail": f"no served race {race_id!r}"}


def _unknown_state(race_id: str) -> dict:
    return {"error": "unknown_state",
            "detail": f"no exact anchor state for {race_id!r}; "
                      f"list exact anchors via /v2/races/{race_id}/states"}


def _invalid(exc: StrategyRequestError) -> dict:
    return {"error": "strategy_request_invalid",
            "reason": exc.reason, "detail": exc.detail}


def _unavailable() -> dict:
    return {"error": "parameter_unavailable",
            "detail": "frozen production parameters unavailable"}


def _internal() -> dict:
    return {"error": "internal", "detail": "unexpected strategy failure"}


@router.post("/strategies/compare",
             response_model=S.V2StrategyCompareResponse)
def compare_strategies(payload: S.V2StrategyCompareRequest,
                       service: V2StrategyService = Depends(
                           get_v2_strategy_service)):
    """Simulated strategy comparison for one exact historical state."""
    try:
        return service.run_comparison(
            race_id=payload.race_id,
            anchor_driver_id=payload.anchor_driver_id,
            anchor_lap_number=payload.anchor_lap_number,
            anchor_state_time_s=payload.anchor_state_time_s,
            target_driver_id=payload.target_driver_id,
            objective=payload.objective,
            candidates=(
                [entry.model_dump() for entry in payload.candidates]
                if payload.candidates is not None else None),
            simulation_count=payload.simulation_count,
            master_seed=payload.master_seed)
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(payload.race_id))
    except (AnchorNotFoundError, InvalidRaceStateError,
            RaceStateReconstructionError):
        return JSONResponse(status_code=422,
                            content=_unknown_state(payload.race_id))
    except StrategyRequestError as exc:
        return JSONResponse(status_code=422, content=_invalid(exc))
    except (SimulationUnsupportedError, SimulationUnavailableError):
        # Defense in depth: compare_strategies already projects these into a
        # structured supported=false payload; only unexpected escapees land
        # here and are never disguised as client errors.
        return JSONResponse(status_code=500, content=_internal())
    except StrategyParameterUnavailableError:
        return JSONResponse(status_code=503, content=_unavailable())
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())
