"""V3.4 frozen ensemble recipe execution (research-only, no serving use).

Implements exactly one transformation: the V3.4D final ensemble recipe
(fixed convex blend w=0.2 XGB over frozen V3.1B Logistic). Shared by D
parity verification and E evaluation so both execute identical code.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

RECIPE_PATH = Path("results/v3/v3_4d/final_ensemble_recipe.json")

REQUIRED_COLUMNS = ("state_id", "race_id", "season", "driver_id", "target",
                    "probability")


def load_recipe(path=RECIPE_PATH) -> dict:
    recipe = json.loads(Path(path).read_text())
    blob = json.dumps({k: v for k, v in recipe.items()
                       if k != "recipe_identity"},
                      sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        recipe["recipe_identity"], "final recipe identity failure"
    assert recipe["decision"] == "ENSEMBLE_SELECTED"
    assert recipe["method"] == "FIXED_CONVEX_BLEND"
    assert recipe["xgboost_weight"] == 0.2
    assert recipe["logistic_weight"] == 0.8
    assert recipe["probability_semantics"] == "INDEPENDENT_BINARY"
    assert recipe["calibration"] == "NONE"
    assert recipe["normalization"] == "FORBIDDEN"
    return recipe


def _frame(path, label) -> pd.DataFrame:
    frame = pd.read_parquet(path)
    missing = [c for c in REQUIRED_COLUMNS if c not in frame.columns]
    assert not missing, f"{label} missing columns: {missing}"
    assert frame["state_id"].is_unique, f"{label} duplicate state_id"
    p = frame["probability"].to_numpy(float)
    assert np.all(np.isfinite(p)), f"{label} non-finite probabilities"
    assert np.all((p >= 0) & (p <= 1)), f"{label} out-of-bounds probabilities"
    return frame


def apply_recipe(logistic_path, xgb_path, recipe=None) -> pd.DataFrame:
    """Identity-aligned convex blend. Never positional. Deterministic."""
    recipe = recipe or load_recipe()
    w = float(recipe["xgboost_weight"])
    log = _frame(logistic_path, "logistic")
    xgb = _frame(xgb_path, "xgboost")
    assert recipe["probability_semantics"] == "INDEPENDENT_BINARY"
    merged = log[["state_id", "race_id", "season", "driver_id", "target",
                  "probability"]].merge(
        xgb[["state_id", "race_id", "season", "driver_id", "target",
             "probability"]],
        on="state_id", suffixes=("_log", "_xgb"),
        validate="one_to_one")
    assert len(merged) == len(log) == len(xgb), \
        "missing/extra identities across inputs"
    for col in ("race_id", "season", "driver_id", "target"):
        left = merged[f"{col}_log"].astype(str).to_numpy()
        right = merged[f"{col}_xgb"].astype(str).to_numpy()
        assert (left == right).all(), f"mismatched {col}"
    p = (1.0 - w) * merged["probability_log"].to_numpy(float) + \
        w * merged["probability_xgb"].to_numpy(float)
    assert np.all(np.isfinite(p)) and np.all((p >= 0) & (p <= 1))
    return pd.DataFrame({
        "state_id": merged["state_id"],
        "race_id": merged["race_id_log"],
        "season": merged["season_log"],
        "driver_id": merged["driver_id_log"],
        "target": merged["target_log"].to_numpy(float),
        "probability": p,
    })
