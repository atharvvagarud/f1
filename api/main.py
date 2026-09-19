"""F1 Race Winner Predictor API — application assembly (R4 refactor).

App construction and middleware only. Legacy routes live in ``api.routes``
(request contracts in ``api.schemas``, orchestration in
``api.services.prediction_service``, computation in ``ml.inference``);
V2 routes live in ``api.v2_routes`` (added R5, additive only).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router
from api.v2_routes import router as v2_router

app = FastAPI(title="F1 Race Winner Predictor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
app.include_router(v2_router)
