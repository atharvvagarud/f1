"""
Clean + validate the lap-X BASE dataset and save a reproducible "cleaned" CSV.

Why this exists:
- Training scripts can handle missing values via imputers,
  but we also need a clean dataset artifact + quality report for coursework evidence.

Inputs:
- data/interim/lap10/lap10_base.csv  (raw extracted snapshot dataset)

Outputs:
- data/processed/lap10/base/dataset_clean.csv
- results/data_quality/lap10_base_data_quality_report.csv
- results/data_quality/lap10_base_race_integrity_report.csv

How to run:
  python scripts/cleaning/clean_dataset.py
"""

from pathlib import Path
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]

# ✅ Updated paths to match your current repo structure
RAW_DATASET = ROOT / "data" / "interim" / "lap10" / "lap10_base.csv"
CLEAN_DATASET = ROOT / "data" / "processed" / "lap10" / "base" / "dataset_clean.csv"

REPORT_DIR = ROOT / "results" / "data_quality"
QUALITY_REPORT = REPORT_DIR / "lap10_base_data_quality_report.csv"
RACE_REPORT = REPORT_DIR / "lap10_base_race_integrity_report.csv"

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
    "driver",  # keep as string
]

def main() -> None:
    if not RAW_DATASET.exists():
        raise FileNotFoundError(f"Raw dataset not found: {RAW_DATASET}")

    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    CLEAN_DATASET.parent.mkdir(parents=True, exist_ok=True)

    df = pd.read_csv(RAW_DATASET)

    # --- Basic schema guardrails ---
    required = set(RACE_KEYS + ["lap_x", "is_winner", "driver_number"] + NUM_COLS + CAT_COLS)
    missing_required = sorted([c for c in required if c not in df.columns])
    if missing_required:
        raise ValueError(f"Dataset missing required columns: {missing_required}")

    # --- Coerce numeric columns safely ---
    for c in NUM_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Replace inf/-inf (can cause model overflow / warnings)
    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    # --- Conservative clipping (winsorize-like) to prevent numeric blow-ups ---
    # Broad, defensible bounds (keeps artifacts stable; models still impute missing).
    if "gap_to_leader_seconds" in df.columns:
        df["gap_to_leader_seconds"] = df["gap_to_leader_seconds"].clip(lower=0, upper=300)  # 0..5 min
    if "lap_time_x_seconds" in df.columns:
        df["lap_time_x_seconds"] = df["lap_time_x_seconds"].clip(lower=30, upper=300)      # 30s..5 min
    if "tyre_life_x" in df.columns:
        df["tyre_life_x"] = df["tyre_life_x"].clip(lower=0, upper=60)
    if "position_x" in df.columns:
        df["position_x"] = df["position_x"].clip(lower=1, upper=30)

    # --- Race integrity report ---
    race_rows = []
    for (year, event), g in df.groupby(RACE_KEYS):
        race_rows.append({
            "year": year,
            "event_name": event,
            "rows": len(g),
            "unique_drivers": g["driver"].nunique(),
            "winner_rows": int(g["is_winner"].sum()),
            "missing_position_x": int(g["position_x"].isna().sum()),
            "missing_lap_time_x_seconds": int(g["lap_time_x_seconds"].isna().sum()),
        })
    race_report = pd.DataFrame(race_rows).sort_values(["year", "event_name"])
    race_report.to_csv(RACE_REPORT, index=False)

    # --- Global quality report (missingness) ---
    quality = []
    for c in NUM_COLS + CAT_COLS:
        quality.append({
            "column": c,
            "missing_count": int(df[c].isna().sum()),
            "missing_pct": float(df[c].isna().mean() * 100.0),
        })
    quality_report = pd.DataFrame(quality).sort_values("missing_count", ascending=False)
    quality_report.to_csv(QUALITY_REPORT, index=False)

    # --- Save cleaned dataset (we do NOT drop rows; models + imputers handle missing) ---
    df.to_csv(CLEAN_DATASET, index=False)

    print("\n=== Clean dataset saved ===")
    print(CLEAN_DATASET)
    print("\n=== Reports saved ===")
    print(QUALITY_REPORT)
    print(RACE_REPORT)

    # Helpful console summary:
    bad_races = race_report[race_report["winner_rows"] != 1]
    print(f"\nRaces total: {race_report.shape[0]}")
    print(f"Races with winner_rows != 1: {bad_races.shape[0]}")
    print("\nTop missing columns:")
    print(quality_report.head(8).to_string(index=False))

if __name__ == "__main__":
    main()