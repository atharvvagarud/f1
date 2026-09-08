"""Application/prediction service (R4 foundation refactor).

Orchestrates the existing use cases — health, race listing, ensemble and
single-model prediction — by delegating all computation to ``ml.inference``.
This layer owns HTTP-agnostic application behaviour only: no FastAPI types,
no routing, no response shaping beyond what ``ml.inference`` returns, so
serialized output stays byte-identical to the pre-R4 backend (including the
known Monaco-2022 NaN passthrough, which is intentionally not handled here).
"""

from ml.inference import (
    get_available_races,
    run_ensemble_prediction,
    run_single_model_prediction,
)


def get_health_status():
    return {"status": "ok"}


def list_available_races():
    return {"races": get_available_races()}


def run_ensemble(year: int, event: str):
    return run_ensemble_prediction(year, event)


def run_single_model(year: int, event: str, model: str):
    return run_single_model_prediction(year, event, model)
