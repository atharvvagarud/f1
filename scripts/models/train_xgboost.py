"""
Train XGBoost model for lap-10 winner prediction
Using GroupKFold CV identical to other models.
"""

from pathlib import Path
import pandas as pd
import numpy as np

from sklearn.model_selection import GroupKFold
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.metrics import log_loss

from xgboost import XGBClassifier

ROOT = Path(__file__).resolve().parents[2]

DATA_PATH = ROOT / "data/processed/lap10/base/dataset_clean.csv"
RESULTS_DIR = ROOT / "results/models/xgboost_lap10"

RESULTS_DIR.mkdir(parents=True, exist_ok=True)

RACE_KEYS = ["year", "event_name"]

NUM_COLS = [
    "position_x",
    "session_time_x_seconds",
    "gap_to_leader_seconds",
    "lap_time_x_seconds",
    "tyre_life_x",
    "stint_x",
    "pit_in_time_present",
    "pit_out_time_present",
    "track_status_x",
]

CAT_COLS = [
    "compound_x",
]

TARGET = "is_winner"

def topk_accuracy(df, k=3):
    correct = 0
    races = 0

    for (_, _), g in df.groupby(RACE_KEYS):
        races += 1
        topk = g.sort_values("pred_proba", ascending=False).head(k)
        if topk[TARGET].sum() > 0:
            correct += 1

    return correct / races


def main():

    df = pd.read_csv(DATA_PATH)

    X = df[NUM_COLS + CAT_COLS]
    y = df[TARGET]
    groups = df[RACE_KEYS].astype(str).agg("_".join, axis=1)

    numeric_transformer = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
    ])

    categorical_transformer = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OneHotEncoder(handle_unknown="ignore"))
    ])

    preprocessor = ColumnTransformer([
        ("num", numeric_transformer, NUM_COLS),
        ("cat", categorical_transformer, CAT_COLS)
    ])

    model = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42
    )

    pipeline = Pipeline([
        ("prep", preprocessor),
        ("model", model)
    ])

    gkf = GroupKFold(n_splits=5)

    rows = []
    predictions = []

    for fold, (train_idx, test_idx) in enumerate(gkf.split(X, y, groups), 1):

        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        pipeline.fit(X_train, y_train)

        probs = pipeline.predict_proba(X_test)[:, 1]

        fold_df = df.iloc[test_idx].copy()
        fold_df["pred_proba"] = probs

        top1 = topk_accuracy(fold_df, k=1)
        top3 = topk_accuracy(fold_df, k=3)

        loss = log_loss(y_test, probs)

        rows.append({
            "model": "XGBoost",
            "fold": fold,
            "top1_accuracy": top1,
            "top3_accuracy": top3,
            "log_loss": loss
        })

        predictions.append(fold_df)

    metrics = pd.DataFrame(rows)

    summary = {
        "model": "XGBoost",
        "top1_accuracy": f"{metrics.top1_accuracy.mean():.4f} ± {metrics.top1_accuracy.std():.4f}",
        "top3_accuracy": f"{metrics.top3_accuracy.mean():.4f} ± {metrics.top3_accuracy.std():.4f}",
        "log_loss": f"{metrics.log_loss.mean():.4f} ± {metrics.log_loss.std():.4f}",
    }

    print("\n=== XGBoost (GroupKFold CV) Results ===")
    print(metrics)

    print("\n=== XGBoost MEAN±STD ===")
    print(summary)

    metrics.to_csv(RESULTS_DIR / "metrics_cv.csv", index=False)

    preds = pd.concat(predictions)
    preds.to_csv(RESULTS_DIR / "race_predictions_cv.csv", index=False)

    print("\nSaved CV metrics to:", RESULTS_DIR / "metrics_cv.csv")
    print("Saved CV race predictions to:", RESULTS_DIR / "race_predictions_cv.csv")


if __name__ == "__main__":
    main()