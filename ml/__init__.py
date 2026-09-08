"""F1 in-race winner prediction — shared ML library (R3 foundation refactor).

Behaviour-preserving home for the constants, dataset/model path helpers and
runtime inference logic previously duplicated across ``api/services``,
``app.py`` and ``scripts/``. No methodology, feature, or prediction change:
this package only gives the existing logic a single importable address.
"""

from ml.config import (
    CHECKPOINTS,
    MODEL_LABELS,
    MODELS,
    ROOT,
    get_dataset_path,
    get_model_dir,
)
from ml.features import FEATURE_COLS

__all__ = [
    "ROOT",
    "CHECKPOINTS",
    "MODELS",
    "MODEL_LABELS",
    "FEATURE_COLS",
    "get_dataset_path",
    "get_model_dir",
]
