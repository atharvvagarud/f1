"""
Train + evaluate Logistic Regression for lap-10 winner prediction (NON-WEATHER)
using GroupKFold CV (group = year_event_name).

Input:
- data/processed/lap10/base/dataset_clean.csv

Outputs:
- results/models/logreg_lap10/metrics_cv.csv
- results/models/logreg_lap10/race_predictions_cv.csv
"""

from pathlib import Path
import numpy as np
import pandas as pd

from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import log_loss
from sklearn.impute import SimpleImputer


NUM_FEATURES = [
    "position_x",
    "gap_to_leader_seconds",
    "lap_time_x_seconds",
    "tyre_life_x",
    "stint_x",
    "pit_in_time_present",
    "pit_out_time_present",
    "track_status_x",
]
CAT_FEATURES = ["compound_x"]


def find_project_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists() and (p / "scripts").exists():
            return p
    raise RuntimeError("Could not locate project root (missing data/ and scripts/).")


def race_level_topk(df_race: pd.DataFrame, prob_col: str, k: int) -> int:
    ranked = df_race.sort_values(prob_col, ascending=False)
    return int(ranked.head(k)["is_winner"].max() == 1)


def main() -> None:
    ROOT = find_project_root(Path(__file__).resolve())
    DATASET = ROOT / "data" / "processed" / "lap10" / "base" / "dataset_clean.csv"

    OUT_DIR = ROOT / "results" / "models" / "logreg_lap10"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_CV = OUT_DIR / "metrics_cv.csv"
    PREDS_CV = OUT_DIR / "race_predictions_cv.csv"

    df = pd.read_csv(DATASET)

    # Clean numeric coercion
    df[NUM_FEATURES] = df[NUM_FEATURES].apply(pd.to_numeric, errors="coerce")
    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    X = df[NUM_FEATURES + CAT_FEATURES]
    y = df["is_winner"].astype(int)
    groups = df["year"].astype(str) + "_" + df["event_name"].astype(str)

    numeric_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="median")),
            ("scaler", StandardScaler()),
        ]
    )
    categorical_pipeline = Pipeline(
        steps=[
            ("imputer", SimpleImputer(strategy="most_frequent")),
            ("onehot", OneHotEncoder(handle_unknown="ignore")),
        ]
    )
    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, NUM_FEATURES),
            ("cat", categorical_pipeline, CAT_FEATURES),
        ]
    )

    model = LogisticRegression(
        max_iter=2000,
        class_weight="balanced",
        solver="lbfgs",
    )

    pipeline = Pipeline(steps=[("preprocess", preprocessor), ("model", model)])

    gkf = GroupKFold(n_splits=5)

    metrics_rows = []
    race_pred_rows = []

    total_races = df[["year", "event_name"]].drop_duplicates().shape[0]

    for fold, (train_idx, test_idx) in enumerate(gkf.split(X, y, groups=groups), start=1):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        pipeline.fit(X_train, y_train)

        df_test = df.iloc[test_idx].copy()
        df_test["win_prob"] = pipeline.predict_proba(X_test)[:, 1]

        # Race-level metrics
        hits1 = 0
        hits3 = 0
        races_eval = 0

        for (yr, ev), race_df in df_test.groupby(["year", "event_name"]):
            if int(race_df["is_winner"].sum()) != 1:
                continue
            races_eval += 1
            hits1 += race_level_topk(race_df, "win_prob", 1)
            hits3 += race_level_topk(race_df, "win_prob", 3)

            ranked = race_df.sort_values("win_prob", ascending=False).reset_index(drop=True)
            top_pred_driver = ranked.loc[0, "driver"]
            true_winner = race_df.loc[race_df["is_winner"] == 1, "driver"].iloc[0]

            race_pred_rows.append(
                {
                    "model": "LogisticRegression",
                    "fold": fold,
                    "year": yr,
                    "event_name": ev,
                    "predicted_winner": top_pred_driver,
                    "true_winner": true_winner,
                    "hit_top1": int(top_pred_driver == true_winner),
                    "hit_top3": int(ranked.head(3)["is_winner"].max() == 1),
                }
            )

        top1 = hits1 / races_eval if races_eval else float("nan")
        top3 = hits3 / races_eval if races_eval else float("nan")
        ll = log_loss(y_test, df_test["win_prob"])

        train_races = df.iloc[train_idx][["year", "event_name"]].drop_duplicates().shape[0]
        test_races = df.iloc[test_idx][["year", "event_name"]].drop_duplicates().shape[0]

        metrics_rows.append(
            {
                "model": "LogisticRegression",
                "fold": fold,
                "n_splits": gkf.n_splits,
                "train_races": train_races,
                "test_races": test_races,
                "races_evaluated": races_eval,
                "top1_accuracy": top1,
                "top3_accuracy": top3,
                "log_loss": ll,
                "total_races": total_races,
            }
        )

    metrics = pd.DataFrame(metrics_rows)

    # Add MEAN±STD row (as text for easy reporting)
    top1_mean, top1_std = metrics["top1_accuracy"].mean(), metrics["top1_accuracy"].std()
    top3_mean, top3_std = metrics["top3_accuracy"].mean(), metrics["top3_accuracy"].std()
    ll_mean, ll_std = metrics["log_loss"].mean(), metrics["log_loss"].std()

    mean_row = {
        "model": "LogisticRegression MEAN±STD",
        "fold": "",
        "n_splits": gkf.n_splits,
        "train_races": "",
        "test_races": "",
        "races_evaluated": total_races,
        "top1_accuracy": f"{top1_mean:.4f} ± {top1_std:.4f}",
        "top3_accuracy": f"{top3_mean:.4f} ± {top3_std:.4f}",
        "log_loss": f"{ll_mean:.4f} ± {ll_std:.4f}",
        "total_races": total_races,
    }

    print("\n=== Logistic Regression (GroupKFold CV) Results ===")
    print(pd.concat([metrics, pd.DataFrame([mean_row])], ignore_index=True).to_string(index=False))

    metrics.to_csv(METRICS_CV, index=False)
    pd.DataFrame(race_pred_rows).to_csv(PREDS_CV, index=False)

    print(f"\nSaved CV metrics to: {METRICS_CV}")
    print(f"Saved CV race predictions to: {PREDS_CV}")


if __name__ == "__main__":
    main()