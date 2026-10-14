"""V3.10F driver-telemetry HTTP routes.

Additive telemetry family over the read-only ``V2TelemetryService``. Thin
routing only: request parsing via ``api.v2_telemetry_schemas``, projection
via ``api.v2_telemetry_service``. The Phase-4 ``api/v2_routes.py`` family,
the R4 replay family, and every science family are untouched and
unimported here.

One race-scoped read-only request serves the whole race; the causal
(<=T) slicing happens client-side in the typed telemetry selector, so
driver switches re-slice locally with zero new requests.

Error mapping:
- unknown race (2018–2024 registry miss, incl. any 2025 race) → 404
  ``unknown_race``
- anything else → 500 ``internal`` (never disguised as client error)

Error bodies never carry stack traces, filesystem paths, or model
internals. This route can never generate a prediction: the service holds
no engine.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from api import v2_telemetry_schemas as S
from api.v2_telemetry_service import (
    V2TelemetryService,
    get_v2_telemetry_service,
)
from raceintel.race_state.race_state_reconstruction import RaceNotFoundError

router = APIRouter(prefix="/v2", tags=["v2-telemetry"])


def _unknown_race(race_id: str) -> dict:
    return {"error": "unknown_race",
            "detail": f"no served telemetry race {race_id!r}"}


def _internal() -> dict:
    return {"error": "internal", "detail": "unexpected telemetry failure"}


@router.get("/races/{race_id}/replay/telemetry",
            response_model=S.V2TelemetryResponse)
def replay_telemetry(race_id: str,
                     service: V2TelemetryService = Depends(
                         get_v2_telemetry_service)):
    """Historical lap + stint evidence for one race (causally sliced client-side)."""
    try:
        payload = service.get_telemetry(race_id)
    except RaceNotFoundError:
        return JSONResponse(status_code=404,
                            content=_unknown_race(race_id))
    except Exception:  # noqa: BLE001 - stable 500, never a client error
        return JSONResponse(status_code=500, content=_internal())
    return S.V2TelemetryResponse(
        race_id=payload["race_id"],
        telemetry_contract_version=payload["telemetry_contract_version"],
        lap_count=payload["lap_count"],
        stint_count=payload["stint_count"],
        laps=[S.V2TelemetryLap(**lap) for lap in payload["laps"]],
        stints=[S.V2TelemetryStint(**stint)
                for stint in payload["stints"]])
