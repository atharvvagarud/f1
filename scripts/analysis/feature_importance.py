"""
Cross-validated feature importance analysis for lap-10 winner prediction.

What this does:
- Uses the cleaned NON-WEATHER lap-10 dataset
- Rebuilds the same style of pipelines used for HGB and XGBoost
- Computes permutation importance on each GroupKFold test fold
- Averages feature importance across folds
- Saves CSV outputs + a plot for the dissertation

How to run:
    python scripts/analysis/feature_importance.py
"""

from pathlib import Path
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.model_selection import GroupKFold
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from sklearn.impute import SimpleImputer
from sklearn.inspection import permutation_importance
from sklearn.ensemble import HistGradientBoostingClassifier

from xgboost import XGBClassifier


ROOT = Path(__file__).resolve().parents[2]

DATA_PATH = ROOT / "data" / "processed" / "lap10" / "base" / "dataset_clean.csv"
RESULTS_DIR = ROOT / "results" / "analysis"

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


def make_preprocessor():
    numeric_transformer = Pipeline([
        ("imputer", SimpleImputer(strategy="median")),
    ])

    categorical_transformer = Pipeline([
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("encoder", OneHotEncoder(handle_unknown="ignore")),
    ])

    return ColumnTransformer([
        ("num", numeric_transformer, NUM_COLS),
        ("cat", categorical_transformer, CAT_COLS),
    ])


def make_hgb_pipeline():
    model = HistGradientBoostingClassifier(
        random_state=42,
        max_iter=300,
        learning_rate=0.05,
        max_depth=6,
        min_samples_leaf=20,
    )

    return Pipeline([
        ("prep", make_preprocessor()),
        ("model", model),
    ])


def make_xgb_pipeline():
    model = XGBClassifier(
        n_estimators=300,
        max_depth=6,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        objective="binary:logistic",
        eval_metric="logloss",
        random_state=42,
    )

    return Pipeline([
        ("prep", make_preprocessor()),
        ("model", model),
    ])


def compute_cv_permutation_importance(model_name: str, pipeline: Pipeline, X: pd.DataFrame, y: pd.Series, groups: pd.Series):
    gkf = GroupKFold(n_splits=5)
    fold_rows = []

    for fold, (train_idx, test_idx) in enumerate(gkf.split(X, y, groups), start=1):
        X_train, X_test = X.iloc[train_idx].copy(), X.iloc[test_idx].copy()
        y_train, y_test = y.iloc[train_idx].copy(), y.iloc[test_idx].copy()

        pipeline.fit(X_train, y_train)

        # Permutation importance on held-out fold
        result = permutation_importance(
            pipeline,
            X_test,
            y_test,
            scoring="neg_log_loss",
            n_repeats=10,
            random_state=42,
            n_jobs=1,
        )

        for feature, mean_imp, std_imp in zip(X.columns, result.importances_mean, result.importances_std):
            fold_rows.append({
                "model": model_name,
                "fold": fold,
                "feature": feature,
                "importance_mean": mean_imp,
                "importance_std": std_imp,
            })

        print(f"✅ {model_name} fold {fold} importance done")

    fold_df = pd.DataFrame(fold_rows)

    summary_df = (
        fold_df.groupby(["model", "feature"], as_index=False)
        .agg(
            importance_mean=("importance_mean", "mean"),
            importance_std=("importance_mean", "std"),
        )
        .sort_values("importance_mean", ascending=False)
        .reset_index(drop=True)
    )

    return fold_df, summary_df


def plot_top_features(summary_df: pd.DataFrame, title: str, out_path: Path, top_n: int = 10):
    plot_df = summary_df.head(top_n).copy()
    plot_df = plot_df.sort_values("importance_mean", ascending=True)

    plt.figure(figsize=(10, 6))
    plt.barh(plot_df["feature"], plot_df["importance_mean"], xerr=plot_df["importance_std"])
    plt.xlabel("Mean permutation importance (neg_log_loss decrease)")
    plt.ylabel("Feature")
    plt.title(title)
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()


def main():
    if not DATA_PATH.exists():
        raise FileNotFoundError(f"Dataset not found: {DATA_PATH}")

    df = pd.read_csv(DATA_PATH)

    required_cols = set(RACE_KEYS + NUM_COLS + CAT_COLS + [TARGET])
    missing = sorted(c for c in required_cols if c not in df.columns)
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    X = df[NUM_COLS + CAT_COLS].copy()
    y = df[TARGET].copy()
    groups = df[RACE_KEYS].astype(str).agg("_".join, axis=1)

    print("Running HGB feature importance...")
    hgb_fold, hgb_summary = compute_cv_permutation_importance(
        model_name="HistGradientBoosting",
        pipeline=make_hgb_pipeline(),
        X=X,
        y=y,
        groups=groups,
    )

    print("\nRunning XGBoost feature importance...")
    xgb_fold, xgb_summary = compute_cv_permutation_importance(
        model_name="XGBoost",
        pipeline=make_xgb_pipeline(),
        X=X,
        y=y,
        groups=groups,
    )

    combined_summary = pd.concat([hgb_summary, xgb_summary], ignore_index=True)

    hgb_fold.to_csv(RESULTS_DIR / "feature_importance_hgb_folds.csv", index=False)
    xgb_fold.to_csv(RESULTS_DIR / "feature_importance_xgboost_folds.csv", index=False)

    hgb_summary.to_csv(RESULTS_DIR / "feature_importance_hgb.csv", index=False)
    xgb_summary.to_csv(RESULTS_DIR / "feature_importance_xgboost.csv", index=False)
    combined_summary.to_csv(RESULTS_DIR / "feature_importance_summary.csv", index=False)

    plot_top_features(
        hgb_summary,
        "Feature Importance - HistGradientBoosting (Lap 10, Non-Weather)",
        RESULTS_DIR / "feature_importance_hgb.png",
        top_n=10,
    )

    plot_top_features(
        xgb_summary,
        "Feature Importance - XGBoost (Lap 10, Non-Weather)",
        RESULTS_DIR / "feature_importance_xgboost.png",
        top_n=10,
    )

    # Combined plot: top 8 per model
    top_hgb = hgb_summary.head(8).copy()
    top_xgb = xgb_summary.head(8).copy()
    top_hgb["label"] = "HGB | " + top_hgb["feature"]
    top_xgb["label"] = "XGB | " + top_xgb["feature"]
    combined_plot = pd.concat([top_hgb, top_xgb], ignore_index=True).sort_values("importance_mean", ascending=True)

    plt.figure(figsize=(12, 8))
    plt.barh(combined_plot["label"], combined_plot["importance_mean"], xerr=combined_plot["importance_std"])
    plt.xlabel("Mean permutation importance (neg_log_loss decrease)")
    plt.ylabel("Model | Feature")
    plt.title("Feature Importance Comparison - HGB vs XGBoost")
    plt.tight_layout()
    plt.savefig(RESULTS_DIR / "feature_importance_plot.png", dpi=300, bbox_inches="tight")
    plt.close()

    print("\n=== Top HGB Features ===")
    print(hgb_summary.head(10).to_string(index=False))

    print("\n=== Top XGBoost Features ===")
    print(xgb_summary.head(10).to_string(index=False))

    print("\nSaved:")
    print(RESULTS_DIR / "feature_importance_hgb.csv")
    print(RESULTS_DIR / "feature_importance_xgboost.csv")
    print(RESULTS_DIR / "feature_importance_summary.csv")
    print(RESULTS_DIR / "feature_importance_hgb.png")
    print(RESULTS_DIR / "feature_importance_xgboost.png")
    print(RESULTS_DIR / "feature_importance_plot.png")


if __name__ == "__main__":
    main()