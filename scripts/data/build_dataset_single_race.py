"""
Build a single-race lap-X snapshot dataset (debug/demo script).

Purpose:
- Builds a CSV snapshot for one selected race at lap X.
- Useful for validating feature logic and showing examples in meetings.

Outputs:
- data/processed/lap10_bahrain_2023_snapshot.csv (by default)

How to run:
  python scripts/build_dataset_single_race.py
"""

from pathlib import Path
import fastf1
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "raw" / "fastf1_cache"
OUT_CSV = ROOT / "data" / "processed" / "lap10_bahrain_2023_snapshot.csv"

YEAR = 2023
GP = "Bahrain"
SESSION = "R"
LAP_X = 10

def main() -> None:
    fastf1.Cache.enable_cache(str(CACHE_DIR))

    s = fastf1.get_session(YEAR, GP, SESSION)
    s.load()

    laps = s.laps.copy()
    laps_x = laps[laps["LapNumber"] <= LAP_X].copy()

    latest = (
        laps_x.sort_values(["Driver", "LapNumber"])
             .groupby("Driver", as_index=False)
             .tail(1)
             .copy()
    )

    latest["session_time_x_seconds"] = latest["Time"].dt.total_seconds()
    latest["lap_time_x_seconds"] = latest["LapTime"].dt.total_seconds()

    leader_time = latest["session_time_x_seconds"].min()
    latest["gap_to_leader_seconds"] = latest["session_time_x_seconds"] - leader_time

    latest["pit_in_time_present"] = latest["PitInTime"].notna().astype(int)
    latest["pit_out_time_present"] = latest["PitOutTime"].notna().astype(int)

    results = s.results.copy()
    winner_code = results.sort_values("Position").iloc[0]["Abbreviation"]
    latest["is_winner"] = (latest["Driver"] == winner_code).astype(int)

    df = pd.DataFrame({
        "year": YEAR,
        "event_name": GP,
        "lap_x": LAP_X,
        "driver": latest["Driver"],
        "driver_number": latest["DriverNumber"],
        "position_x": latest["Position"],
        "session_time_x_seconds": latest["session_time_x_seconds"],
        "gap_to_leader_seconds": latest["gap_to_leader_seconds"],
        "lap_time_x_seconds": latest["lap_time_x_seconds"],
        "compound_x": latest["Compound"],
        "tyre_life_x": latest["TyreLife"],
        "stint_x": latest["Stint"],
        "fresh_tyre_x": latest["FreshTyre"],
        "pit_in_time_present": latest["pit_in_time_present"],
        "pit_out_time_present": latest["pit_out_time_present"],
        "track_status_x": latest["TrackStatus"],
        "is_winner": latest["is_winner"],
    }).sort_values("position_x").reset_index(drop=True)

    print(df.head(10).to_string(index=False))
    print("\nWinner rows:", df["is_winner"].sum())

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(OUT_CSV, index=False)
    print("\nSaved:", OUT_CSV)

if __name__ == "__main__":
    main()