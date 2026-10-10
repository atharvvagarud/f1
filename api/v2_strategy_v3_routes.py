"""V2 Strategy 2.0 HTTP routes (V3.6F runtime integration).

Additive Strategy 2.0 family over ``V3StrategyService``. Thin routing only:
request parsing via ``api.v2_strategy_v3_schemas``, orchestration via
``api.v2_strategy_v3_service``, domain-error → HTTP mapping below. The
Phase-7 ``POST /v2/strategies/compare`` route, service and schemas are
untouched and unimported here.

Error mapping (mirrors frozen conventions):
- unknown race (2018–2024 registry miss, incl. any 2025 race) → 404
  ``unknown_race``
- exact-anchor miss / malformed anchor / invalid reconstructed state → 422
  ``unknown_state``
- malformed Strategy 2.0 request (unknown action/compound, duplicate or
  empty alternatives, unknown mode, extra production-forbidden fields
  such as simulation counts) → 422 ``strategy_v3_request_invalid`` with
  the stable machine-readable ``reason``
- a well-formed but un-simulatable factual state → 200 with
  ``supported=false`` and the canonical ``unsupported_reason``. No
  fallback, no fabricated results, no partial table, no zero-filled
  metrics.
- cache miss in cached mode → 404 ``cache_miss`` (explicit; never a
  silent fallback to fabricated numbers)
- corrupt/stale/mismatched cache artifact → 503 ``cache_invalid``
- live mode disabled in this runtime → 503 ``live_engine_disabled``
- frozen parameter artifact missing/corrupt → 503 ``parameter_unavailable``
- anything else → 500 ``internal`` (never disguised as a client error)

Error bodies never carry stack traces, filesystem paths, or model internals.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from api import v2_strategy_v3_schemas as S
from api.v2_strategy_v3_service import (
    V3CacheInvalidError,
    V3CacheMissError,
    V3LiveDisabledError,
    V3RequestError,
    V3StrategyService,
    get_v3_strategy_service,
)
from api.v2_strategy_service import StrategyParameterUnavailableError
from raceintel.race_state.race_state import InvalidRaceStateError
from raceintel.race_state.race_state_reconstruction import (
    AnchorNotFoundError,
    RaceNotFoundError,
    RaceStateReconstructionError,
)
from raceintel.simulation.adapter import SimulationUnavailableError
from raceintel.simulation.engine import SimulationUnsupportedError

router = APIRouter(prefix="/v2", tags=["v2-strategy-v3"])


def _unknown_race(race_id: str) -> dict:
    return {"error": "unknown_race",
            "detail": f"no served race {race_id!r}"}


def _unknown_state(race_id: str) -> dict:
    return {"error": "unknown_state",
            "detail": f"no exact anchor state for {race_id!r}; "
                      f"list exact anchors via /v2/races/{race_id}/states"}


def _invalid(exc: V3RequestError) -> dict:
    return {"error": "strategy_v3_request_invalid",
            "reason": exc.reason, "detail": exc.detail}


def _unavailable() -> dict:
    return {"error": "parameter_unavailable",
            "detail": "frozen production parameters unavailable"}


def _internal() -> dict:
    return {"error": "internal", "detail": "unexpected strategy failure"}


@router.post("/strategies/compare-v3",
             response_model=S.V3CompareResponse)
def compare_strategies_v3(payload: S.V3CompareRequest,
                          service: V3StrategyService = Depends(
                              get_v3_strategy_service)):
    """Strategy 2.0 comparison for one exact historical state.

    ``mode="live"`` executes the validated Strategy 2.0 engine (a
    production 5000-run comparison takes on the order of a minute on real
    states; cache-first deployment avoids blocking on it).
    ``mode="cached"`` serves a deterministic artifact previously generated
    by the same engine. Compare only: paired simulations, simulated
    differences, 95% MC intervals.
    """
    try:
        return service.run_comparison(
            race_id=payload.race_id,
            anchor_driver_id=payload.anchor_driver_id,
            anchor_lap_number=payload.anchor_lap_number,
            anchor_state_time_s=payload.anchor_state_time_s,
            target_driver_id=payload.target_driver_id,
            alternatives=(
                [entry.model_dump() for entry in payload.alternatives]
                if payload.alternatives is not None else None),
            master_seed=payload.master_seed,
            mode=payload.mode)
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(payload.race_id))
    except (AnchorNotFoundError, InvalidRaceStateError,
            RaceStateReconstructionError):
        return JSONResponse(status_code=422,
                            content=_unknown_state(payload.race_id))
    except V3RequestError as exc:
        return JSONResponse(status_code=422, content=_invalid(exc))
    except V3CacheMissError as exc:
        return JSONResponse(
            status_code=404,
            content={"error": "cache_miss", "detail": str(exc)})
    except V3CacheInvalidError as exc:
        return JSONResponse(
            status_code=503,
            content={"error": "cache_invalid", "detail": str(exc)})
    except V3LiveDisabledError as exc:
        return JSONResponse(
            status_code=503,
            content={"error": "live_engine_disabled", "detail": str(exc)})
    except (SimulationUnsupportedError, SimulationUnavailableError):
        return JSONResponse(status_code=500, content=_internal())
    except StrategyParameterUnavailableError:
        return JSONResponse(status_code=503, content=_unavailable())
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())


@router.get("/strategies/v3/availability",
            response_model=S.V3AvailabilityResponse)
def strategy_v3_availability(
        race_id: str | None = Query(default=None, min_length=1),
        service: V3StrategyService = Depends(get_v3_strategy_service)):
    """Deterministic catalogue of cached Strategy 2.0 comparisons.

    Lets future clients know which races, checkpoints and target drivers
    have Strategy 2.0 support without submitting failed simulation
    requests. Optional ``race_id`` narrows to one served race.
    """
    try:
        catalogue = service.describe_availability()
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())
    if race_id is not None:
        catalogue = dict(catalogue)
        catalogue["entries"] = [e for e in catalogue["entries"]
                                if e["race_id"] == race_id]
        catalogue["entry_count"] = len(catalogue["entries"])
    return catalogue
