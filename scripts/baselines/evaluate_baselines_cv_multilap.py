from pathlib import Path
import argparse
import numpy as np
import pandas as pd
from sklearn.model_selection import GroupKFold


def find_project_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists() and (p / "scripts").exists():
            return p
    raise RuntimeError("Could not locate project root")


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


def fmt(mean, std):
    return f"{mean:.4f} ± {std:.4f}"


def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--lap", type=int, required=True)
    args = parser.parse_args()

    lap = args.lap
    lap_tag = f"lap{lap}"

    ROOT = find_project_root(Path(__file__).resolve())

    dataset = ROOT / f"data/processed/{lap_tag}/base/dataset_clean.csv"

    if not dataset.exists():
        raise FileNotFoundError(dataset)

    out_dir = ROOT / "results/baselines"
    out_dir.mkdir(parents=True, exist_ok=True)

    out_cv = out_dir / f"{lap_tag}_baseline_results_cv.csv"
    out_summary = out_dir / f"{lap_tag}_baseline_results_cv_summary.csv"

    df = pd.read_csv(dataset)

    groups = df["year"].astype(str) + "_" + df["event_name"].astype(str)

    gkf = GroupKFold(n_splits=5)

    baselines = [

        (f"Leader at lap {lap} (position_x)", "position_x", True),

        (f"Fastest lap at lap {lap} (lap_time_x_seconds)", "lap_time_x_seconds", True),

        ("Lowest driver_number (sanity baseline)", "driver_number", True),

    ]

    rows = []

    for fold, (_, test_idx) in enumerate(gkf.split(df, df["is_winner"], groups), start=1):

        df_test = df.iloc[test_idx]

        test_races = df_test[["year", "event_name"]].drop_duplicates().shape[0]

        for name, col, ascending in baselines:

            rows.append({

                "lap": lap,

                "baseline": name,

                "fold": fold,

                "n_splits": gkf.n_splits,

                "test_races": test_races,

                "races_evaluated": test_races,

                "top1_accuracy": topk_hit_per_race(df_test, col, 1, ascending),

                "top3_accuracy": topk_hit_per_race(df_test, col, 3, ascending),

            })

    cv = pd.DataFrame(rows)

    print(f"\n=== Baselines (NON-WEATHER, {lap_tag.upper()}) GroupKFold CV Results ===")

    print(cv.to_string(index=False))

    summary = (

        cv.groupby(["lap", "baseline"])

        .agg(

            top1_mean=("top1_accuracy", "mean"),

            top1_std=("top1_accuracy", "std"),

            top3_mean=("top3_accuracy", "mean"),

            top3_std=("top3_accuracy", "std"),

            total_races_evaluated=("races_evaluated", "sum"),

        )

        .reset_index()

    )

    summary["top1_mean±std"] = summary.apply(lambda r: fmt(r["top1_mean"], r["top1_std"]), axis=1)

    summary["top3_mean±std"] = summary.apply(lambda r: fmt(r["top3_mean"], r["top3_std"]), axis=1)

    summary = summary[["lap", "baseline", "top1_mean±std", "top3_mean±std", "total_races_evaluated"]]

    print(f"\n=== Baselines (NON-WEATHER, {lap_tag.upper()}) CV Summary ===")

    print(summary.to_string(index=False))

    cv.to_csv(out_cv, index=False)

    summary.to_csv(out_summary, index=False)

    print("\nSaved:")

    print(out_cv)

    print(out_summary)


if __name__ == "__main__":
    main()