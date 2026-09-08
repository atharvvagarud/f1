"""
Train Logistic Regression for a chosen lap checkpoint using GroupKFold CV.

Multilap version:
- accepts --lap
- reads from data/processed/lap{lap}/base/dataset_clean.csv
- writes to results/models/logreg_lap{lap}_multilap/
- uses StandardScaler on numeric columns
- increases max_iter to reduce convergence warnings

Example:
    python scripts/models/train_logistic_regression_multilap.py --lap 5
    python scripts/models/train_logistic_regression_multilap.py --lap 10
"""

from pathlib import Path
import argparse
import pandas as pd
import joblib

from sklearn.model_selection import GroupKFold
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss


def find_project_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists() and (p / "results").exists() and (p / "scripts").exists():
            return p
    raise RuntimeError("Project root not found")


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
RACE_KEYS = ["year", "event_name"]


def topk_accuracy(df: pd.DataFrame, k: int) -> float:
    hits = 0
    races = 0

    for _, g in df.groupby(RACE_KEYS):
        races += 1
        topk = g.sort_values("pred_proba", ascending=False).head(k)
        if topk[TARGET].sum() > 0:
            hits += 1

    return hits / races if races else float("nan")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lap", type=int, required=True)
    args = parser.parse_args()

    lap = args.lap
    lap_tag = f"lap{lap}"

    ROOT = find_project_root(Path(__file__).resolve())
    DATA_PATH = ROOT / "data" / "processed" / lap_tag / "base" / "dataset_clean.csv"
    RESULTS_DIR = ROOT / "results" / "models" / f"logreg_{lap_tag}_multilap"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")

    df = pd.read_csv(DATA_PATH)

    required_cols = set(NUM_COLS + CAT_COLS + [TARGET] + RACE_KEYS)
    missing = sorted(c for c in required_cols if c not in df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    X = df[NUM_COLS + CAT_COLS].copy()
    y = df[TARGET].copy()
    groups = df[RACE_KEYS].astype(str).agg("_".join, axis=1)

    numeric_transformer = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])

    categorical_transformer = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OneHotEncoder(handle_unknown="ignore")),
    ])

    preprocessor = ColumnTransformer([
        ("num", numeric_transformer, NUM_COLS),
        ("cat", categorical_transformer, CAT_COLS),
    ])

    model = LogisticRegression(
        max_iter=3000,
        random_state=42,
    )

    pipeline = Pipeline([
        ("prep", preprocessor),
        ("model", model),
    ])

    gkf = GroupKFold(n_splits=5)

    rows = []
    predictions = []

    for fold, (train_idx, test_idx) in enumerate(gkf.split(X, y, groups), start=1):
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
            "model": "LogisticRegression",
            "lap": lap,
            "fold": fold,
            "n_splits": 5,
            "train_races": len(set(groups.iloc[train_idx])),
            "test_races": len(set(groups.iloc[test_idx])),
            "races_evaluated": len(fold_df[RACE_KEYS].drop_duplicates()),
            "top1_accuracy": top1,
            "top3_accuracy": top3,
            "log_loss": loss,
        })

        predictions.append(fold_df)

    metrics = pd.DataFrame(rows)

    summary = pd.DataFrame([{
        "model": "LogisticRegression",
        "lap": lap,
        "top1_mean±std": f"{metrics['top1_accuracy'].mean():.4f} ± {metrics['top1_accuracy'].std():.4f}",
        "top3_mean±std": f"{metrics['top3_accuracy'].mean():.4f} ± {metrics['top3_accuracy'].std():.4f}",
        "log_loss_mean±std": f"{metrics['log_loss'].mean():.4f} ± {metrics['log_loss'].std():.4f}",
        "total_races": int(df[RACE_KEYS].drop_duplicates().shape[0]),
    }])

    print(f"\n=== Logistic Regression ({lap_tag.upper()}, MULTILAP) GroupKFold CV Results ===")
    print(metrics.to_string(index=False))

    print(f"\n=== Logistic Regression ({lap_tag.upper()}, MULTILAP) Summary ===")
    print(summary.to_string(index=False))

    metrics.to_csv(RESULTS_DIR / "metrics_cv.csv", index=False)
    pd.concat(predictions, ignore_index=True).to_csv(RESULTS_DIR / "race_predictions_cv.csv", index=False)
    summary.to_csv(RESULTS_DIR / "summary_cv.csv", index=False)

    # Train final model on full dataset and save it
    print("\nTraining final model on full dataset...")
    pipeline.fit(X, y)

    model_path = RESULTS_DIR / "model.pkl"
    joblib.dump(pipeline, model_path)

    print(f"Saved trained model to: {model_path}")

    print("\nSaved:")
    print(RESULTS_DIR / "metrics_cv.csv")
    print(RESULTS_DIR / "race_predictions_cv.csv")
    print(RESULTS_DIR / "summary_cv.csv")



if __name__ == "__main__":
    main()