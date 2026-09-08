"""C. Model loading — every artifact the API can reach must load and score.

Covers all 15 runtime combinations (3 families x 5 checkpoints) that
ml.config addresses as {model}_lap{lap}_multilap, plus the
tuned-artifact preference (model_tuned.pkl wins over model.pkl).
"""

import joblib
import pandas as pd
import pytest

from ml.config import CHECKPOINTS, MODELS, get_model_dir
from ml.features import FEATURE_COLS
from ml.inference import load_dataset, load_model

EXPECTED = [(m, lap) for m in ["logreg", "hgb", "xgboost"] for lap in [5, 10, 15, 20, 25]]


def test_expected_model_matrix():
    assert MODELS == ["logreg", "hgb", "xgboost"]
    assert CHECKPOINTS == [5, 10, 15, 20, 25]


@pytest.mark.parametrize("model,lap", EXPECTED)
def test_model_loads_and_scores(model, lap):
    estimator, filename = load_model(model, lap)
    assert filename == "model_tuned.pkl"  # tuned artifact preferred (baseline)
    assert hasattr(estimator, "predict_proba")
    df = load_dataset(lap)
    sample = df[FEATURE_COLS].head(3)
    proba = estimator.predict_proba(sample)
    assert proba.shape == (3, 2)
    assert ((proba[:, 1] >= 0.0) & (proba[:, 1] <= 1.0)).all()


def test_base_artifact_present_as_fallback():
    # The loader falls back to model.pkl; both files must exist so the
    # fallback path stays viable.
    for model, lap in EXPECTED:
        d = get_model_dir(model, lap)
        assert (d / "model_tuned.pkl").exists()
        assert (d / "model.pkl").exists()
