"""
Tune Logistic Regression for a chosen lap checkpoint using GroupKFold CV.

Optimisation target:
- minimise mean log loss

Also records:
- top1 accuracy
- top3 accuracy

Outputs:
- results/models/logreg_lap{lap}_multilap/tuning_results.csv
- results/models/logreg_lap{lap}_multilap/best_params.json
- results/models/logreg_lap{lap}_multilap/model_tuned.pkl

Example:
    python scripts/models/tune_logreg_multilap.py --lap 10
"""

from pathlib import Path
import argparse
import json
import itertools
import joblib
import pandas as pd

from sklearn.model_selection import GroupKFold
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss


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

CAT_COLS = ["compound_x"]
TARGET = "is_winner"
RACE_KEYS = ["year", "event_name"]


def find_project_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists() and (p / "results").exists() and (p / "scripts").exists():
            return p
    raise RuntimeError("Project root not found")


def topk_accuracy(df: pd.DataFrame, k: int) -> float:
    hits = 0
    races = 0
    for _, g in df.groupby(RACE_KEYS):
        races += 1
        topk = g.sort_values("pred_proba", ascending=False).head(k)
        if topk[TARGET].sum() > 0:
            hits += 1
    return hits / races if races else float("nan")


def make_preprocessor():
    numeric_transformer = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
        ("scaler", StandardScaler()),
    ])

    categorical_transformer = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OneHotEncoder(handle_unknown="ignore")),
    ])

    return ColumnTransformer([
        ("num", numeric_transformer, NUM_COLS),
        ("cat", categorical_transformer, CAT_COLS),
    ])


def evaluate_params(X, y, df, groups, params: dict) -> dict:
    gkf = GroupKFold(n_splits=5)
    fold_log_losses = []
    fold_top1 = []
    fold_top3 = []

    for train_idx, test_idx in gkf.split(X, y, groups):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        model = LogisticRegression(
            max_iter=3000,
            random_state=42,
            **params
        )

        pipeline = Pipeline([
            ("prep", make_preprocessor()),
            ("model", model),
        ])

        pipeline.fit(X_train, y_train)
        probs = pipeline.predict_proba(X_test)[:, 1]

        fold_df = df.iloc[test_idx].copy()
        fold_df["pred_proba"] = probs

        fold_log_losses.append(log_loss(y_test, probs))
        fold_top1.append(topk_accuracy(fold_df, k=1))
        fold_top3.append(topk_accuracy(fold_df, k=3))

    return {
        **params,
        "mean_log_loss": sum(fold_log_losses) / len(fold_log_losses),
        "mean_top1_accuracy": sum(fold_top1) / len(fold_top1),
        "mean_top3_accuracy": sum(fold_top3) / len(fold_top3),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--lap", type=int, required=True)
    args = parser.parse_args()

    lap = args.lap
    lap_tag = f"lap{lap}"

    ROOT = find_project_root(Path(__file__).resolve())
    DATA_PATH = ROOT / "data" / "processed" / lap_tag / "base" / "dataset_clean.csv"
    RESULTS_DIR = ROOT / "results" / "models" / f"logreg_{lap_tag}_multilap"
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(DATA_PATH)
    X = df[NUM_COLS + CAT_COLS].copy()
    y = df[TARGET].copy()
    groups = df[RACE_KEYS].astype(str).agg("_".join, axis=1)

    param_grid = {
        "C": [0.01, 0.1, 1.0, 10.0],
        "solver": ["lbfgs", "liblinear"],
        "class_weight": [None, "balanced"],
    }

    keys = list(param_grid.keys())
    combinations = list(itertools.product(*param_grid.values()))

    results = []

    print(f"Tuning Logistic Regression for {lap_tag}...")
    print(f"Total combinations: {len(combinations)}")

    for i, combo in enumerate(combinations, start=1):
        params = dict(zip(keys, combo))
        print(f"[{i}/{len(combinations)}] Testing {params}")
        row = evaluate_params(X, y, df, groups, params)
        results.append(row)

    results_df = pd.DataFrame(results).sort_values(
        ["mean_log_loss", "mean_top1_accuracy", "mean_top3_accuracy"],
        ascending=[True, False, False]
    ).reset_index(drop=True)

    best = results_df.iloc[0].to_dict()
    best_params = {
        "C": float(best["C"]),
        "solver": str(best["solver"]),
        "class_weight": None if pd.isna(best["class_weight"]) else best["class_weight"],
    }

    results_df.to_csv(RESULTS_DIR / "tuning_results.csv", index=False)
    with open(RESULTS_DIR / "best_params.json", "w", encoding="utf-8") as f:
        json.dump(best_params, f, indent=2)

    print("\n=== Best Logistic Regression Params ===")
    print(best_params)
    print(f"Best mean log loss: {best['mean_log_loss']:.4f}")
    print(f"Best mean top1:     {best['mean_top1_accuracy']:.4f}")
    print(f"Best mean top3:     {best['mean_top3_accuracy']:.4f}")

    final_model = LogisticRegression(
        max_iter=3000,
        random_state=42,
        **best_params
    )

    final_pipeline = Pipeline([
        ("prep", make_preprocessor()),
        ("model", final_model),
    ])

    print("\nTraining final tuned Logistic Regression model on full dataset...")
    final_pipeline.fit(X, y)

    model_path = RESULTS_DIR / "model_tuned.pkl"
    joblib.dump(final_pipeline, model_path)

    print("\nSaved:")
    print(RESULTS_DIR / "tuning_results.csv")
    print(RESULTS_DIR / "best_params.json")
    print(model_path)


if __name__ == "__main__":
    main()