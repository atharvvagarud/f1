"""
Train + evaluate HistGradientBoostingClassifier (WEATHER) with GroupKFold CV (group = race).

Run:
  python scripts/models_weather/train_hgb_classifier_weather.py
"""

from pathlib import Path
import numpy as np
import pandas as pd

from sklearn.model_selection import GroupKFold
from sklearn.preprocessing import OneHotEncoder
from sklearn.compose import ColumnTransformer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import HistGradientBoostingClassifier
from sklearn.metrics import log_loss
from sklearn.impute import SimpleImputer


def find_project_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists() and (p / "scripts").exists():
            return p
    raise RuntimeError("Could not locate project root (missing data/ and scripts/).")


NUM_FEATURES = [
    "position_x",
    "gap_to_leader_seconds",
    "lap_time_x_seconds",
    "tyre_life_x",
    "stint_x",
    "pit_in_time_present",
    "pit_out_time_present",
    "track_status_x",
    # weather
    "weather_airtemp",
    "weather_tracktemp",
    "weather_humidity",
    "weather_pressure",
    "weather_windspeed",
    "weather_winddirection",
    "weather_rainfall",
    "weather_is_raining",
]
CAT_FEATURES = ["compound_x"]


def topk_metrics_per_race(df_test: pd.DataFrame, prob_col: str) -> tuple[float, float, int]:
    hits_top1 = 0
    hits_top3 = 0
    race_count = 0

    for _, race_df in df_test.groupby(["year", "event_name"]):
        if int(race_df["is_winner"].sum()) != 1:
            continue
        race_count += 1
        ranked = race_df.sort_values(prob_col, ascending=False)
        hits_top1 += int(ranked.iloc[0]["is_winner"] == 1)
        hits_top3 += int(ranked.head(3)["is_winner"].max() == 1)

    top1 = hits_top1 / race_count if race_count else float("nan")
    top3 = hits_top3 / race_count if race_count else float("nan")
    return top1, top3, race_count


def main() -> None:
    ROOT = find_project_root(Path(__file__).resolve())

    DATASET = ROOT / "data" / "processed" / "lap10" / "weather" / "dataset_clean.csv"

    OUT_DIR = ROOT / "results" / "models" / "hgb_weather_lap10"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    METRICS_CV = OUT_DIR / "metrics_cv.csv"
    PREDS_CV = OUT_DIR / "race_predictions_cv.csv"

    df = pd.read_csv(DATASET)

    df[NUM_FEATURES] = df[NUM_FEATURES].apply(pd.to_numeric, errors="coerce")
    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    X = df[NUM_FEATURES + CAT_FEATURES]
    y = df["is_winner"].astype(int)

    groups = df["year"].astype(str) + "_" + df["event_name"].astype(str)
    gkf = GroupKFold(n_splits=5)

    # HGB can handle missing numerics, but we still need to handle categorical -> one-hot
    numeric_pipeline = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="median")),
    ])

    categorical_pipeline = Pipeline(steps=[
        ("imputer", SimpleImputer(strategy="most_frequent")),
        ("onehot", OneHotEncoder(handle_unknown="ignore")),
    ])

    preprocessor = ColumnTransformer(
        transformers=[
            ("num", numeric_pipeline, NUM_FEATURES),
            ("cat", categorical_pipeline, CAT_FEATURES),
        ]
    )

    model = HistGradientBoostingClassifier(
        random_state=42,
    )

    pipeline = Pipeline(steps=[
        ("preprocess", preprocessor),
        ("model", model),
    ])

    fold_rows = []
    race_pred_rows = []

    total_races = df[["year", "event_name"]].drop_duplicates().shape[0]
    n_splits = gkf.get_n_splits()

    for fold, (train_idx, test_idx) in enumerate(gkf.split(X, y, groups=groups), start=1):
        X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
        y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

        pipeline.fit(X_train, y_train)

        df_test = df.iloc[test_idx].copy()
        df_test["win_prob"] = pipeline.predict_proba(X_test)[:, 1]

        top1, top3, races_eval = topk_metrics_per_race(df_test, "win_prob")
        ll = log_loss(y_test, df_test["win_prob"])

        train_races = df.iloc[train_idx][["year", "event_name"]].drop_duplicates().shape[0]
        test_races = df.iloc[test_idx][["year", "event_name"]].drop_duplicates().shape[0]

        fold_rows.append({
            "model": "HistGradientBoosting_weather",
            "fold": fold,
            "n_splits": n_splits,
            "train_races": train_races,
            "test_races": test_races,
            "races_evaluated": races_eval,
            "top1_accuracy": top1,
            "top3_accuracy": top3,
            "log_loss": ll,
        })

        for (yr, ev), race_df in df_test.groupby(["year", "event_name"]):
            if int(race_df["is_winner"].sum()) != 1:
                continue
            ranked = race_df.sort_values("win_prob", ascending=False).reset_index(drop=True)
            winner_rank = int(ranked.index[ranked["is_winner"] == 1][0]) + 1
            race_pred_rows.append({
                "model": "HistGradientBoosting_weather",
                "fold": fold,
                "year": yr,
                "event_name": ev,
                "winner_driver": race_df.loc[race_df["is_winner"] == 1, "driver"].iloc[0],
                "winner_rank": winner_rank,
                "top1_hit": int(winner_rank == 1),
                "top3_hit": int(winner_rank <= 3),
            })

    metrics_df = pd.DataFrame(fold_rows)

    top1_mean = metrics_df["top1_accuracy"].mean()
    top1_std = metrics_df["top1_accuracy"].std(ddof=0)
    top3_mean = metrics_df["top3_accuracy"].mean()
    top3_std = metrics_df["top3_accuracy"].std(ddof=0)
    ll_mean = metrics_df["log_loss"].mean()
    ll_std = metrics_df["log_loss"].std(ddof=0)

    summary_row = {
        "model": "HistGradientBoosting_weather MEAN±STD",
        "fold": "",
        "n_splits": n_splits,
        "train_races": "",
        "test_races": "",
        "races_evaluated": total_races,
        "top1_accuracy": f"{top1_mean:.4f} ± {top1_std:.4f}",
        "top3_accuracy": f"{top3_mean:.4f} ± {top3_std:.4f}",
        "log_loss": f"{ll_mean:.4f} ± {ll_std:.4f}",
    }

    out_print = pd.concat([metrics_df, pd.DataFrame([summary_row])], ignore_index=True)

    print("\n=== HistGradientBoosting (WEATHER) GroupKFold CV Results ===")
    print(out_print.to_string(index=False))

    metrics_df.to_csv(METRICS_CV, index=False)
    pd.DataFrame(race_pred_rows).to_csv(PREDS_CV, index=False)

    print(f"\nSaved CV metrics to: {METRICS_CV}")
    print(f"Saved CV race predictions to: {PREDS_CV}")


if __name__ == "__main__":
    main()