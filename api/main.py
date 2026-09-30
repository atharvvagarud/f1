"""F1 Race Winner Predictor API — application assembly (R4 refactor).

App construction and middleware only. Legacy routes live in ``api.routes``
(request contracts in ``api.schemas``, orchestration in
``api.services.prediction_service``, computation in ``ml.inference``);
V2 routes live in ``api.v2_routes`` (added R5, additive only).

P10-3 production surface: explicit serving configuration (``api.config``),
deployability readiness (``GET /ready`` in ``api.routes``), and lightweight
request logging (``api.observability``). ``GET /health`` remains cheap
liveness only.
"""

import json
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.config import ServingConfig, get_serving_config
from api.observability import (
    LOGGER_NAME,
    RequestLoggingMiddleware,
    configure_logging,
)
from api.routes import router
from api.v2_explanation_routes import router as v2_explanation_router
from api.v2_replay_routes import router as v2_replay_router
from api.v2_routes import router as v2_router
from api.v2_simulation_routes import router as v2_simulation_router
from api.v2_simulation_service import SimulationParameterUnavailableError
from api.v2_strategy_routes import router as v2_strategy_router
from api.v2_timeline_explanation_routes import (
    router as v2_timeline_explanation_router,
)
from api.v2_strategy_service import StrategyParameterUnavailableError


@asynccontextmanager
async def _lifespan(app: FastAPI):
    config: ServingConfig = app.state.serving_config
    logging.getLogger(LOGGER_NAME).info(json.dumps({
        "event": "startup",
        "service": "f1-intelligence-v2",
        "log_level": config.log_level,
        "allowed_origin_count": len(config.allowed_origins),
        "network_ingestion_enabled":
            os.environ.get("V2_ALLOW_NETWORK") == "1",
    }))
    yield


def create_app(config: ServingConfig | None = None) -> FastAPI:
    """Build the application (explicit config for tests; env by default)."""
    serving_config = config if config is not None else get_serving_config()
    configure_logging(serving_config.log_level)

    app = FastAPI(title="F1 Race Winner Predictor API", lifespan=_lifespan)
    app.state.serving_config = serving_config

    @app.exception_handler(SimulationParameterUnavailableError)
    async def _parameter_unavailable(
            request: Request, exc: SimulationParameterUnavailableError):
        return JSONResponse(
            status_code=503,
            content={"error": "parameter_unavailable", "detail": str(exc)})

    @app.exception_handler(StrategyParameterUnavailableError)
    async def _strategy_parameter_unavailable(
            request: Request, exc: StrategyParameterUnavailableError):
        return JSONResponse(
            status_code=503,
            content={"error": "parameter_unavailable", "detail": str(exc)})

    # Exact production CORS policy: explicit origins only (no wildcard by
    # default), no credentialed browser sessions, open methods/headers.
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(serving_config.allowed_origins),
        allow_credentials=False,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)

    app.include_router(router)
    app.include_router(v2_router)
    app.include_router(v2_replay_router)
    app.include_router(v2_explanation_router)
    app.include_router(v2_timeline_explanation_router)
    app.include_router(v2_simulation_router)
    app.include_router(v2_strategy_router)
    return app


app = create_app()
