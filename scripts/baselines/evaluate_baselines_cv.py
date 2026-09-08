"""
Evaluate baselines using GroupKFold CV (NON-WEATHER), grouped by race.

Input:
- data/processed/lap10/base/dataset_clean.csv

Outputs:
- results/baselines/lap10_baseline_results_cv.csv
- results/baselines/lap10_baseline_results_cv_summary.csv
"""

from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold


def find_project_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists() and (p / "scripts").exists():
            return p
    raise RuntimeError("Could not locate project root (missing data/ and scripts/).")


def topk_hit_per_race(df: pd.DataFrame, score_col: str, k: int, ascending: bool) -> float:
    hits = 0
    races = 0
    for _, race_df in df.groupby(["year", "event_name"]):
        if int(race_df["is_winner"].sum()) != 1:
            continue
        races += 1
        ranked = race_df.sort_values(score_col, ascending=ascending)
        hits += int(ranked.head(k)["is_winner"].max() == 1)
    return hits / races if races else float("nan")


def fmt_mean_std(mean: float, std: float) -> str:
    return f"{mean:.4f} ± {std:.4f}"


def main() -> None:
    ROOT = find_project_root(Path(__file__).resolve())
    DATASET = ROOT / "data" / "processed" / "lap10" / "base" / "dataset_clean.csv"

    OUT_DIR = ROOT / "results" / "baselines"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_CV = OUT_DIR / "lap10_baseline_results_cv.csv"
    OUT_SUM = OUT_DIR / "lap10_baseline_results_cv_summary.csv"

    df = pd.read_csv(DATASET)

    for c in ["position_x", "lap_time_x_seconds", "driver_number"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    groups = df["year"].astype(str) + "_" + df["event_name"].astype(str)
    gkf = GroupKFold(n_splits=5)

    baselines = [
        ("Leader at lap 10 (position_x)", "position_x", True),
        ("Fastest lap at lap 10 (lap_time_x_seconds)", "lap_time_x_seconds", True),
        ("Lowest driver_number (sanity baseline)", "driver_number", True),
    ]

    rows = []
    for fold, (_, test_idx) in enumerate(gkf.split(df, df["is_winner"], groups=groups), start=1):
        df_test = df.iloc[test_idx].copy()
        test_races = df_test[["year", "event_name"]].drop_duplicates().shape[0]

        for name, score_col, ascending in baselines:
            rows.append(
                {
                    "baseline": name,
                    "fold": fold,
                    "n_splits": gkf.n_splits,
                    "test_races": test_races,
                    "races_evaluated": test_races,
                    "top1_accuracy": topk_hit_per_race(df_test, score_col, k=1, ascending=ascending),
                    "top3_accuracy": topk_hit_per_race(df_test, score_col, k=3, ascending=ascending),
                }
            )

    cv = pd.DataFrame(rows)
    print("\n=== Baselines (NON-WEATHER) GroupKFold CV Results ===")
    print(cv.to_string(index=False))

    summary = (
        cv.groupby("baseline")
        .agg(
            top1_mean=("top1_accuracy", "mean"),
            top1_std=("top1_accuracy", "std"),
            top3_mean=("top3_accuracy", "mean"),
            top3_std=("top3_accuracy", "std"),
            total_races_evaluated=("races_evaluated", "sum"),
        )
        .reset_index()
    )
    summary["top1_mean±std"] = summary.apply(lambda r: fmt_mean_std(r["top1_mean"], r["top1_std"]), axis=1)
    summary["top3_mean±std"] = summary.apply(lambda r: fmt_mean_std(r["top3_mean"], r["top3_std"]), axis=1)
    summary = summary[["baseline", "top1_mean±std", "top3_mean±std", "total_races_evaluated"]]

    print("\n=== Baselines (NON-WEATHER) CV Summary (mean ± std) ===")
    print(summary.to_string(index=False))

    cv.to_csv(OUT_CV, index=False)
    summary.to_csv(OUT_SUM, index=False)
    print(f"\nSaved CV baseline results to: {OUT_CV}")
    print(f"Saved CV baseline summary to: {OUT_SUM}")


if __name__ == "__main__":
    main()