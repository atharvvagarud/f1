"""F1 Race Winner Predictor API — application assembly (R4 refactor).

App construction and middleware only. Legacy routes live in ``api.routes``
(request contracts in ``api.schemas``, orchestration in
``api.services.prediction_service``, computation in ``ml.inference``);
V2 routes live in ``api.v2_routes`` (added R5, additive only).
"""

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from api.routes import router
from api.v2_replay_routes import router as v2_replay_router
from api.v2_routes import router as v2_router
from api.v2_simulation_routes import router as v2_simulation_router
from api.v2_simulation_service import SimulationParameterUnavailableError
from api.v2_strategy_routes import router as v2_strategy_router
from api.v2_strategy_service import StrategyParameterUnavailableError

app = FastAPI(title="F1 Race Winner Predictor API")


@app.exception_handler(SimulationParameterUnavailableError)
async def _parameter_unavailable(request: Request,
                                 exc: SimulationParameterUnavailableError):
    return JSONResponse(
        status_code=503,
        content={"error": "parameter_unavailable", "detail": str(exc)})


@app.exception_handler(StrategyParameterUnavailableError)
async def _strategy_parameter_unavailable(
        request: Request, exc: StrategyParameterUnavailableError):
    return JSONResponse(
        status_code=503,
        content={"error": "parameter_unavailable", "detail": str(exc)})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(v2_router)
app.include_router(v2_replay_router)
app.include_router(v2_simulation_router)
app.include_router(v2_strategy_router)
