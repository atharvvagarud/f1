"""
Inspect available FastF1 lap fields at a given lap checkpoint X.

Purpose:
- Helps validate which columns exist at lap X (feature selection evidence).

How to run:
  python scripts/inspect_lapX_fields.py
"""

from pathlib import Path
import fastf1
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "raw" / "fastf1_cache"

YEAR = 2023
GP = "Bahrain"
SESSION = "R"
LAP_X = 10

def main() -> None:
    fastf1.Cache.enable_cache(str(CACHE_DIR))

    print(f"Loading session: {YEAR} {GP} {SESSION}")
    s = fastf1.get_session(YEAR, GP, SESSION)
    s.load()

    laps = s.laps.copy()
    laps_x = laps[laps["LapNumber"] <= LAP_X].copy()

    latest = (
        laps_x.sort_values(["Driver", "LapNumber"])
             .groupby("Driver", as_index=False)
             .tail(1)
    )

    print("\n--- Snapshot summary ---")
    print(f"Lap checkpoint X = {LAP_X}")
    print(f"Drivers in snapshot: {latest['Driver'].nunique()}")
    print("Snapshot columns (count):", len(latest.columns))

    candidate_cols = [
        "Driver", "DriverNumber", "LapNumber", "Position",
        "Time", "LapTime", "Stint", "Compound", "TyreLife",
        "FreshTyre", "PitInTime", "PitOutTime", "TrackStatus"
    ]

    present = [c for c in candidate_cols if c in latest.columns]
    missing = [c for c in candidate_cols if c not in latest.columns]

    print("\nCandidate columns PRESENT:", present)
    print("Candidate columns MISSING:", missing)

    show_cols = ["Driver", "LapNumber", "Position", "Time"]
    for c in ["LapTime", "Compound", "TyreLife", "Stint", "PitInTime", "PitOutTime"]:
        if c in latest.columns:
            show_cols.append(c)

    print("\n--- Sample snapshot (sorted by Position, top 12) ---")
    print(latest[show_cols].sort_values("Position").head(12).to_string(index=False))

    key_fields = [c for c in ["Position", "Time", "LapTime", "Compound"] if c in latest.columns]
    print("\n--- Missing values in key fields ---")
    print(latest[key_fields].isna().sum())

if __name__ == "__main__":
    main()