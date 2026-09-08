"""Shared runtime configuration (R3 foundation refactor).

Single source of truth for checkpoint/model registries, display labels and
dataset/model artifact paths. Values moved verbatim from
``api/services/predictor.py`` — do not reorder or rename without updating
the R2 golden fixtures and saved-pipeline expectations.
"""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

CHECKPOINTS = [5, 10, 15, 20, 25]
MODELS = ["logreg", "hgb", "xgboost"]

MODEL_LABELS = {
    "logreg": "Logistic Regression",
    "hgb": "HistGradientBoosting",
    "xgboost": "XGBoost",
}


def get_dataset_path(lap: int) -> Path:
    return ROOT / "data" / "processed" / f"lap{lap}" / "base" / "dataset_clean.csv"


def get_model_dir(model_name: str, lap: int) -> Path:
    return ROOT / "results" / "models" / f"{model_name}_lap{lap}_multilap"
