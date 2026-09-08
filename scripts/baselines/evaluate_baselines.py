"""
Evaluate simple baselines for lap-10 race winner prediction (NON-WEATHER).

Baselines:
1) Leader at lap 10 (lowest position_x)
2) Fastest lap at lap 10 (lowest lap_time_x_seconds)
3) Lowest driver_number (sanity)

Input:
- data/processed/lap10/base/dataset_clean.csv

Output:
- results/baselines/lap10_baseline_results.csv
"""

from pathlib import Path
import numpy as np
import pandas as pd


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


def main() -> None:
    ROOT = find_project_root(Path(__file__).resolve())
    DATASET = ROOT / "data" / "processed" / "lap10" / "base" / "dataset_clean.csv"

    OUT_DIR = ROOT / "results" / "baselines"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_CSV = OUT_DIR / "lap10_baseline_results.csv"

    df = pd.read_csv(DATASET)

    for c in ["position_x", "lap_time_x_seconds", "driver_number"]:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    races_total = df[["year", "event_name"]].drop_duplicates().shape[0]

    rows = [
        {
            "baseline": "Leader at lap 10 (position_x)",
            "races": races_total,
            "top1_accuracy": topk_hit_per_race(df, "position_x", k=1, ascending=True),
            "top3_accuracy": topk_hit_per_race(df, "position_x", k=3, ascending=True),
        },
        {
            "baseline": "Fastest lap at lap 10 (lap_time_x_seconds)",
            "races": races_total,
            "top1_accuracy": topk_hit_per_race(df, "lap_time_x_seconds", k=1, ascending=True),
            "top3_accuracy": topk_hit_per_race(df, "lap_time_x_seconds", k=3, ascending=True),
        },
        {
            "baseline": "Lowest driver_number (sanity baseline)",
            "races": races_total,
            "top1_accuracy": topk_hit_per_race(df, "driver_number", k=1, ascending=True),
            "top3_accuracy": topk_hit_per_race(df, "driver_number", k=3, ascending=True),
        },
    ]

    out = pd.DataFrame(rows)
    print(out.to_string(index=False))
    out.to_csv(OUT_CSV, index=False)
    print(f"\nSaved baseline results to: {OUT_CSV}")


if __name__ == "__main__":
    main()