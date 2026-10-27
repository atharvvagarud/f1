"""F1 Race Winner Predictor API — application assembly (R4 refactor).

App construction and middleware only. Legacy routes live in ``api.routes``
(request contracts in ``api.schemas``, orchestration in
``api.services.prediction_service``, computation in ``ml.inference``);
V2 routes live in ``api.v2_routes`` (added R5, additive only).

P10-3 production surface: explicit serving configuration (``api.config``),
deployability readiness (``GET /ready`` in ``api.routes``), and lightweight
request logging (``api.observability``). ``GET /health`` remains cheap
liveness only.

C2 composition authority (post-V3, architectural only): ``create_app``
assembles the production application in three explicit seams —
``_register_exception_handlers``, ``_register_middleware``, and the public
``register_routers`` route-family composition point below. Inclusion order
is preserved exactly; no route, schema, or dependency semantic changed.
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
from api.v2_counterfactual_routes import (
    router as v2_counterfactual_router,
)
from api.v2_consensus_routes import router as v2_consensus_router
from api.v2_uncertainty_routes import router as v2_uncertainty_router
from api.v2_explanation_routes import router as v2_explanation_router
from api.v2_replay_routes import router as v2_replay_router
from api.v2_telemetry_routes import router as v2_telemetry_router
from api.v2_routes import router as v2_router
from api.v2_simulation_routes import router as v2_simulation_router
from api.v2_simulation_service import SimulationParameterUnavailableError
from api.v2_spatial_routes import router as v2_spatial_router
from api.v2_strategy_routes import router as v2_strategy_router
from api.v2_strategy_v3_routes import router as v2_strategy_v3_router
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


def _register_exception_handlers(app: FastAPI) -> FastAPI:
    """Production exception handlers (stable 503 mapping, unchanged)."""

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
    return app


def _register_middleware(
        app: FastAPI, serving_config: ServingConfig) -> FastAPI:
    """Production middleware (order preserved: logging runs outermost)."""
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
    return app


def register_routers(app: FastAPI) -> FastAPI:
    """Canonical API registration seam (C2, post-V3 architectural only).

    Single composition point for every production route family.
    Inclusion order is the historical order and must be preserved:
    routing behaviour today does not depend on it (no overlapping
    static/dynamic paths, no catch-alls), but reordering is not
    covered by contract, so this sequence is authoritative.

    Ownership (C4 owns any future retirement; nothing retires here):

    - CANONICAL_KEEP: legacy product surface (``/health``, ``/ready``,
      ``/races``, ``/predict/*``) plus every v2 family below.
    - LEGACY_COMPAT_KEEP: first-generation strategy compare family,
      intentionally mounted alongside strategy-v3.
    """
    # CANONICAL_KEEP — legacy product surface (unprefixed).
    app.include_router(router)
    # CANONICAL_KEEP — v2 core (race state + winner snapshot).
    app.include_router(v2_router)
    # CANONICAL_KEEP — replay family.
    app.include_router(v2_replay_router)
    # CANONICAL_KEEP — telemetry family (read-only projection).
    app.include_router(v2_telemetry_router)
    # CANONICAL_KEEP — local-explanation family.
    app.include_router(v2_explanation_router)
    # CANONICAL_KEEP — timeline-explanation family (change endpoint).
    app.include_router(v2_timeline_explanation_router)
    # CANONICAL_KEEP — simulation family.
    app.include_router(v2_simulation_router)
    # CANONICAL_KEEP — spatial family.
    app.include_router(v2_spatial_router)
    # LEGACY_COMPAT_KEEP — first-generation strategy compare family
    # (retained alongside strategy-v3; C4 decides retirement).
    app.include_router(v2_strategy_router)
    # CANONICAL_KEEP — strategy-v3 family.
    app.include_router(v2_strategy_v3_router)
    # CANONICAL_KEEP — counterfactual family.
    app.include_router(v2_counterfactual_router)
    # CANONICAL_KEEP — consensus family.
    app.include_router(v2_consensus_router)
    # CANONICAL_KEEP — uncertainty family.
    app.include_router(v2_uncertainty_router)
    return app


def create_app(config: ServingConfig | None = None) -> FastAPI:
    """Build the application (explicit config for tests; env by default)."""
    serving_config = config if config is not None else get_serving_config()
    configure_logging(serving_config.log_level)

    app = FastAPI(title="F1 Race Winner Predictor API", lifespan=_lifespan)
    app.state.serving_config = serving_config

    _register_exception_handlers(app)
    _register_middleware(app, serving_config)
    register_routers(app)
    return app


app = create_app()
