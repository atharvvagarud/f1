"""
Low-effort, defensible tuning for HGB (WEATHER) using GroupKFold CV.

Grid:
- max_depth
- learning_rate
- max_iter
- min_samples_leaf

Run:
  python scripts/models_weather/tune_hgb_classifier_weather.py
"""

from pathlib import Path
import itertools
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

    OUT_DIR = ROOT / "results" / "models" / "hgb_weather_lap10" / "tuning"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    GRID_RESULTS = OUT_DIR / "grid_results.csv"
    BEST_PARAMS = OUT_DIR / "best_params.txt"
    BEST_SUMMARY = OUT_DIR / "best_summary.txt"

    df = pd.read_csv(DATASET)
    df[NUM_FEATURES] = df[NUM_FEATURES].apply(pd.to_numeric, errors="coerce")
    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    X = df[NUM_FEATURES + CAT_FEATURES]
    y = df["is_winner"].astype(int)

    groups = df["year"].astype(str) + "_" + df["event_name"].astype(str)
    gkf = GroupKFold(n_splits=5)

    total_races = df[["year", "event_name"]].drop_duplicates().shape[0]
    print("\n=== HGB WEATHER Tuning (GroupKFold CV) ===")
    print(f"Total races: {total_races}")

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

    grid = {
        "max_depth": [2, 3, 4],
        "learning_rate": [0.05, 0.1],
        "max_iter": [200, 400],
        "min_samples_leaf": [20, 50],
    }

    keys = list(grid.keys())
    combos = list(itertools.product(*[grid[k] for k in keys]))
    print(f"Total grid combos: {len(combos)}")
    print(f"Grid: {grid}")

    all_rows = []
    best = None  # store dict with metrics

    for i, values in enumerate(combos, start=1):
        params = dict(zip(keys, values))

        fold_top1 = []
        fold_top3 = []
        fold_ll = []

        for train_idx, test_idx in gkf.split(X, y, groups=groups):
            X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

            model = HistGradientBoostingClassifier(
                random_state=42,
                **params
            )

            pipe = Pipeline(steps=[
                ("preprocess", preprocessor),
                ("model", model),
            ])

            pipe.fit(X_train, y_train)

            df_test = df.iloc[test_idx].copy()
            df_test["win_prob"] = pipe.predict_proba(X_test)[:, 1]

            top1, top3, _ = topk_metrics_per_race(df_test, "win_prob")
            ll = log_loss(y_test, df_test["win_prob"])

            fold_top1.append(top1)
            fold_top3.append(top3)
            fold_ll.append(ll)

        top1_mean = float(np.mean(fold_top1))
        top1_std = float(np.std(fold_top1, ddof=0))
        top3_mean = float(np.mean(fold_top3))
        top3_std = float(np.std(fold_top3, ddof=0))
        ll_mean = float(np.mean(fold_ll))
        ll_std = float(np.std(fold_ll, ddof=0))

        row = {
            **params,
            "top1_mean": top1_mean,
            "top1_std": top1_std,
            "top3_mean": top3_mean,
            "top3_std": top3_std,
            "log_loss_mean": ll_mean,
            "log_loss_std": ll_std,
        }
        all_rows.append(row)

        print(
            f"[{i:02d}/{len(combos):02d}] params={params} | "
            f"Top1={top1_mean:.4f}±{top1_std:.4f} | "
            f"Top3={top3_mean:.4f}±{top3_std:.4f} | "
            f"LogLoss={ll_mean:.4f}±{ll_std:.4f}"
        )

        # Selection rule: primarily minimise log loss, break ties with top1, then top3
        score_tuple = (ll_mean, -top1_mean, -top3_mean)
        if best is None or score_tuple < best["score_tuple"]:
            best = {
                "params": params,
                "top1_mean": top1_mean,
                "top1_std": top1_std,
                "top3_mean": top3_mean,
                "top3_std": top3_std,
                "log_loss_mean": ll_mean,
                "log_loss_std": ll_std,
                "score_tuple": score_tuple,
            }

    grid_df = pd.DataFrame(all_rows).sort_values(
        ["log_loss_mean", "top1_mean", "top3_mean"],
        ascending=[True, False, False]
    )
    grid_df.to_csv(GRID_RESULTS, index=False)

    # Write best results
    with open(BEST_PARAMS, "w", encoding="utf-8") as f:
        f.write(str(best["params"]))

    with open(BEST_SUMMARY, "w", encoding="utf-8") as f:
        f.write("Best HGB WEATHER CV performance (MEAN ± STD across folds):\n")
        f.write(f"Top-1 accuracy: {best['top1_mean']:.4f} ± {best['top1_std']:.4f}\n")
        f.write(f"Top-3 accuracy: {best['top3_mean']:.4f} ± {best['top3_std']:.4f}\n")
        f.write(f"Log loss:       {best['log_loss_mean']:.4f} ± {best['log_loss_std']:.4f}\n")
        f.write(f"Params:         {best['params']}\n")

    print("\n=== Saved tuning outputs ===")
    print(f"Grid results:   {GRID_RESULTS}")
    print(f"Best params:    {BEST_PARAMS}")
    print(f"Best summary:   {BEST_SUMMARY}")

    print("\n=== Best combo summary ===")
    print({
        **best["params"],
        "top1_mean": best["top1_mean"],
        "top1_std": best["top1_std"],
        "top3_mean": best["top3_mean"],
        "top3_std": best["top3_std"],
        "log_loss_mean": best["log_loss_mean"],
        "log_loss_std": best["log_loss_std"],
    })


if __name__ == "__main__":
    main()