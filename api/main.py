"""F1 Race Winner Predictor API — application assembly (R4 refactor).

App construction and middleware only. Routes live in ``api.routes``,
request contracts in ``api.schemas``, orchestration in
``api.services.prediction_service``, and computation in ``ml.inference``.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api.routes import router

app = FastAPI(title="F1 Race Winner Predictor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(router)
