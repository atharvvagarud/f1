"""HTTP routes (R4 foundation refactor).

Thin routing only: request parsing via ``api.schemas``, use-case dispatch to
``api.services.prediction_service``, and direct passthrough of service
results. Endpoint paths, methods, handler names, request fields, response
payloads and error propagation are unchanged from ``api/main.py`` — no
``response_model`` filtering is applied, so serialization behaviour
(including the known Monaco-2022 NaN failure) is preserved exactly.
"""

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from api.schemas import RaceRequest, SingleModelRequest
from api.services import prediction_service as service

router = APIRouter()


@router.get("/health")
def health():
    return service.get_health_status()


@router.get("/ready")
def readiness():
    """Deployability readiness (P10-3): 200 ready, 503 with bounded codes."""
    from api import readiness as readiness_module

    payload = readiness_module.get_readiness()
    if payload["status"] == "ready":
        return payload
    return JSONResponse(status_code=503, content=payload)


@router.get("/races")
def races():
    return service.list_available_races()


@router.post("/predict/ensemble")
def predict_ensemble(payload: RaceRequest):
    return service.run_ensemble(payload.year, payload.event)


@router.post("/predict/single-model")
def predict_single_model(payload: SingleModelRequest):
    return service.run_single_model(payload.year, payload.event, payload.model)
