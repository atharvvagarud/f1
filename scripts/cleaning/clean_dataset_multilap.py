from pathlib import Path
import pandas as pd
import numpy as np
import argparse

ROOT = Path(__file__).resolve().parents[2]

def main():

    parser = argparse.ArgumentParser()
    parser.add_argument("--lap", type=int, required=True)
    args = parser.parse_args()

    lap = args.lap
    lap_tag = f"lap{lap}"

    RAW_DATASET = ROOT / f"data/interim/{lap_tag}/{lap_tag}_base.csv"
    CLEAN_DATASET = ROOT / f"data/processed/{lap_tag}/base/dataset_clean.csv"

    REPORT_DIR = ROOT / "results/data_quality"
    QUALITY_REPORT = REPORT_DIR / f"{lap_tag}_data_quality_report.csv"
    RACE_REPORT = REPORT_DIR / f"{lap_tag}_race_integrity_report.csv"

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    CLEAN_DATASET.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(RAW_DATASET)

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

    CAT_COLS = ["compound_x", "driver"]

    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    # clipping
    df["gap_to_leader_seconds"] = df["gap_to_leader_seconds"].clip(0, 300)
    df["lap_time_x_seconds"] = df["lap_time_x_seconds"].clip(30, 300)
    df["tyre_life_x"] = df["tyre_life_x"].clip(0, 60)
    df["position_x"] = df["position_x"].clip(1, 30)

    # race integrity report
    race_rows = []

    for (year, event), g in df.groupby(["year", "event_name"]):
        race_rows.append({
            "year": year,
            "event_name": event,
            "rows": len(g),
            "unique_drivers": g["driver"].nunique(),
            "winner_rows": int(g["is_winner"].sum())
        })

    race_report = pd.DataFrame(race_rows)
    race_report.to_csv(RACE_REPORT, index=False)

    quality = []

    for c in NUM_COLS + CAT_COLS:
        quality.append({
            "column": c,
            "missing_count": int(df[c].isna().sum()),
            "missing_pct": float(df[c].isna().mean()*100)
        })

    quality_report = pd.DataFrame(quality)
    quality_report.to_csv(QUALITY_REPORT, index=False)

    df.to_csv(CLEAN_DATASET, index=False)

    print("\n=== Clean dataset saved ===")
    print(CLEAN_DATASET)

    print("\nRaces:", race_report.shape[0])
    print("Winner rows != 1:", (race_report["winner_rows"] != 1).sum())


if __name__ == "__main__":
    main()