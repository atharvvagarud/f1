from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from api.services.predictor import (
    get_available_races,
    run_ensemble_prediction,
    run_single_model_prediction,
)

app = FastAPI(title="F1 Race Winner Predictor API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class RaceRequest(BaseModel):
    year: int
    event: str


class SingleModelRequest(BaseModel):
    year: int
    event: str
    model: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/races")
def races():
    return {"races": get_available_races()}


@app.post("/predict/ensemble")
def predict_ensemble(payload: RaceRequest):
    return run_ensemble_prediction(payload.year, payload.event)


@app.post("/predict/single-model")
def predict_single_model(payload: SingleModelRequest):
    return run_single_model_prediction(payload.year, payload.event, payload.model)