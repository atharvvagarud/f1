"""
Clean + validate the lap-X WEATHER dataset and save a reproducible cleaned CSV.

Inputs:
- data/processed/lap10_2019_2023_dataset_weather.csv

Outputs:
- data/processed/lap10_2019_2023_dataset_weather_clean.csv
- results/data_quality/weather_lap10_data_quality_report.csv
- results/data_quality/weather_lap10_race_integrity_report.csv

Run:
  python scripts/cleaning/clean_dataset_weather.py
"""

from pathlib import Path
import numpy as np
import pandas as pd


def find_project_root(start: Path) -> Path:
    """Find repo root by walking upwards until we see BOTH data/ and scripts/."""
    for p in [start] + list(start.parents):
        if (p / "data").exists() and (p / "scripts").exists():
            return p
    raise RuntimeError("Could not locate project root (missing data/ and scripts/).")


RACE_KEYS = ["year", "event_name"]

BASE_NUM_COLS = [
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

WEATHER_NUM_COLS = [
    "weather_airtemp",
    "weather_tracktemp",
    "weather_humidity",
    "weather_pressure",
    "weather_windspeed",
    "weather_winddirection",
    "weather_rainfall",
]

WEATHER_BIN_COLS = [
    "weather_is_raining",
]

CAT_COLS = [
    "compound_x",
    "driver",
]


def main() -> None:
    ROOT = find_project_root(Path(__file__).resolve())

    RAW = ROOT / "data" / "processed" / "lap10_2019_2023_dataset_weather.csv"
    CLEAN = ROOT / "data" / "processed" / "lap10_2019_2023_dataset_weather_clean.csv"

    REPORT_DIR = ROOT / "results" / "data_quality"
    REPORT_DIR.mkdir(parents=True, exist_ok=True)

    QUALITY_REPORT = REPORT_DIR / "weather_lap10_data_quality_report.csv"
    RACE_REPORT = REPORT_DIR / "weather_lap10_race_integrity_report.csv"

    if not RAW.exists():
        raise FileNotFoundError(f"Weather dataset not found: {RAW}")

    df = pd.read_csv(RAW)

    required = set(
        RACE_KEYS
        + ["lap_x", "is_winner", "driver_number"]
        + BASE_NUM_COLS
        + WEATHER_NUM_COLS
        + WEATHER_BIN_COLS
        + CAT_COLS
    )
    missing_required = sorted([c for c in required if c not in df.columns])
    if missing_required:
        raise ValueError(f"Dataset missing required columns: {missing_required}")

    # Coerce numeric
    for c in BASE_NUM_COLS + WEATHER_NUM_COLS + WEATHER_BIN_COLS:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    # Replace inf/-inf
    df.replace([np.inf, -np.inf], np.nan, inplace=True)

    # Conservative clipping (broad, defensible)
    df["gap_to_leader_seconds"] = df["gap_to_leader_seconds"].clip(lower=0, upper=300)  # 0..5 min
    df["lap_time_x_seconds"] = df["lap_time_x_seconds"].clip(lower=30, upper=300)      # 30s..5 min
    df["tyre_life_x"] = df["tyre_life_x"].clip(lower=0, upper=60)
    df["position_x"] = df["position_x"].clip(lower=1, upper=30)

    # Weather clipping (broad ranges so we don't distort data)
    df["weather_airtemp"] = df["weather_airtemp"].clip(lower=-10, upper=60)
    df["weather_tracktemp"] = df["weather_tracktemp"].clip(lower=-10, upper=80)
    df["weather_humidity"] = df["weather_humidity"].clip(lower=0, upper=100)
    df["weather_pressure"] = df["weather_pressure"].clip(lower=800, upper=1100)
    df["weather_windspeed"] = df["weather_windspeed"].clip(lower=0, upper=60)
    df["weather_winddirection"] = df["weather_winddirection"].clip(lower=0, upper=360)
    df["weather_rainfall"] = df["weather_rainfall"].clip(lower=0, upper=50)
    df["weather_is_raining"] = df["weather_is_raining"].clip(lower=0, upper=1)

    # Race integrity report
    race_rows = []
    for (year, event), g in df.groupby(RACE_KEYS):
        race_rows.append(
            {
                "year": year,
                "event_name": event,
                "rows": len(g),
                "unique_drivers": g["driver"].nunique(),
                "winner_rows": int(g["is_winner"].sum()),
                "missing_position_x": int(g["position_x"].isna().sum()),
                "missing_lap_time_x_seconds": int(g["lap_time_x_seconds"].isna().sum()),
                "missing_weather_any": int(g[WEATHER_NUM_COLS + WEATHER_BIN_COLS].isna().any(axis=1).sum()),
            }
        )
    race_report = pd.DataFrame(race_rows).sort_values(["year", "event_name"])
    race_report.to_csv(RACE_REPORT, index=False)

    # Global missingness report
    all_report_cols = BASE_NUM_COLS + WEATHER_NUM_COLS + WEATHER_BIN_COLS + CAT_COLS
    quality = []
    for c in all_report_cols:
        quality.append(
            {
                "column": c,
                "missing_count": int(df[c].isna().sum()),
                "missing_pct": float(df[c].isna().mean() * 100.0),
            }
        )
    quality_report = pd.DataFrame(quality).sort_values("missing_count", ascending=False)
    quality_report.to_csv(QUALITY_REPORT, index=False)

    # Save cleaned dataset (no dropping)
    df.to_csv(CLEAN, index=False)

    print("\n=== Weather clean dataset saved ===")
    print(CLEAN)
    print("\n=== Reports saved ===")
    print(QUALITY_REPORT)
    print(RACE_REPORT)

    bad = race_report[race_report["winner_rows"] != 1]
    print(f"\nRaces total: {race_report.shape[0]}")
    print(f"Races with winner_rows != 1: {bad.shape[0]}")
    print("\nTop missing columns:")
    print(quality_report.head(10).to_string(index=False))


if __name__ == "__main__":
    main()