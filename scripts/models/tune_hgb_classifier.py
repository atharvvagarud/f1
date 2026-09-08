"""
Tune HistGradientBoostingClassifier (NON-WEATHER) using GroupKFold CV.

Input:
- data/processed/lap10/base/dataset_clean.csv

Outputs:
- results/models/hgb_lap10/tuning/grid_results.csv
- results/models/hgb_lap10/tuning/best_params.txt
- results/models/hgb_lap10/tuning/best_summary.txt
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

    OUT_DIR = ROOT / "results" / "models" / "hgb_lap10" / "tuning"
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    GRID_CSV = OUT_DIR / "grid_results.csv"
    BEST_PARAMS_TXT = OUT_DIR / "best_params.txt"
    BEST_SUMMARY_TXT = OUT_DIR / "best_summary.txt"

    df = pd.read_csv(DATASET)
    df[NUM_FEATURES] = df[NUM_FEATURES].apply(pd.to_numeric, errors="coerce")
    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    X = df[NUM_FEATURES + CAT_FEATURES]
    y = df["is_winner"].astype(int)
    groups = df["year"].astype(str) + "_" + df["event_name"].astype(str)

    numeric_pipeline = Pipeline(steps=[("imputer", SimpleImputer(strategy="median"))])
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

    gkf = GroupKFold(n_splits=5)

    param_grid = {
        "max_depth": [2, 3, 4],
        "learning_rate": [0.05, 0.1],
        "max_iter": [200, 400],
        "min_samples_leaf": [20, 50],
    }

    combos = list(itertools.product(*param_grid.values()))
    keys = list(param_grid.keys())

    total_races = df[["year", "event_name"]].drop_duplicates().shape[0]
    print("\n=== HGB Tuning (GroupKFold CV) ===")
    print(f"Total races: {total_races}")
    print(f"Total grid combos: {len(combos)}")
    print(f"Grid: {param_grid}")

    results = []
    best = None

    for i, values in enumerate(combos, start=1):
        params = dict(zip(keys, values))

        fold_top1 = []
        fold_top3 = []
        fold_ll = []

        for train_idx, test_idx in gkf.split(X, y, groups=groups):
            X_train, X_test = X.iloc[train_idx], X.iloc[test_idx]
            y_train, y_test = y.iloc[train_idx], y.iloc[test_idx]

            model = HistGradientBoostingClassifier(random_state=42, **params)
            pipe = Pipeline(steps=[("preprocess", preprocessor), ("model", model)])
            pipe.fit(X_train, y_train)

            df_test = df.iloc[test_idx].copy()
            df_test["win_prob"] = pipe.predict_proba(X_test)[:, 1]

            hits1 = 0
            hits3 = 0
            races_eval = 0
            for _, race_df in df_test.groupby(["year", "event_name"]):
                if int(race_df["is_winner"].sum()) != 1:
                    continue
                races_eval += 1
                hits1 += race_level_topk(race_df, "win_prob", 1)
                hits3 += race_level_topk(race_df, "win_prob", 3)

            fold_top1.append(hits1 / races_eval if races_eval else float("nan"))
            fold_top3.append(hits3 / races_eval if races_eval else float("nan"))
            fold_ll.append(log_loss(y_test, df_test["win_prob"]))

        top1_mean, top1_std = float(np.mean(fold_top1)), float(np.std(fold_top1, ddof=1))
        top3_mean, top3_std = float(np.mean(fold_top3)), float(np.std(fold_top3, ddof=1))
        ll_mean, ll_std = float(np.mean(fold_ll)), float(np.std(fold_ll, ddof=1))

        row = {
            **params,
            "top1_mean": top1_mean,
            "top1_std": top1_std,
            "top3_mean": top3_mean,
            "top3_std": top3_std,
            "log_loss_mean": ll_mean,
            "log_loss_std": ll_std,
        }
        results.append(row)

        if best is None or row["log_loss_mean"] < best["log_loss_mean"]:
            best = row

        print(
            f"[{i:02d}/{len(combos)}] params={params} | "
            f"Top1={top1_mean:.4f}±{top1_std:.4f} | "
            f"Top3={top3_mean:.4f}±{top3_std:.4f} | "
            f"LogLoss={ll_mean:.4f}±{ll_std:.4f}"
        )

    out = pd.DataFrame(results).sort_values(["log_loss_mean", "top1_mean"], ascending=[True, False])
    out.to_csv(GRID_CSV, index=False)

    best_params = {k: best[k] for k in keys}
    BEST_PARAMS_TXT.write_text(str(best_params))
    BEST_SUMMARY_TXT.write_text(
        "Best HGB CV performance (MEAN ± STD across folds):\n"
        f"Top-1 accuracy: {best['top1_mean']:.4f} ± {best['top1_std']:.4f}\n"
        f"Top-3 accuracy: {best['top3_mean']:.4f} ± {best['top3_std']:.4f}\n"
        f"Log loss:       {best['log_loss_mean']:.4f} ± {best['log_loss_std']:.4f}\n"
    )

    print("\n=== Saved tuning outputs ===")
    print(f"Grid results:   {GRID_CSV}")
    print(f"Best params:    {BEST_PARAMS_TXT}")
    print(f"Best summary:   {BEST_SUMMARY_TXT}")
    print("\n=== Best combo summary ===")
    print(best)


if __name__ == "__main__":
    main()