"""
Smoke test for FastF1.

Purpose:
- Confirms FastF1 can download and cache session data on this machine.

Outputs:
- Prints basic info about the loaded session and laps dataframe.

How to run:
  python scripts/smoke_test_fastf1.py
"""

from pathlib import Path
import fastf1

# Project root = parent folder of /scripts
ROOT = Path(__file__).resolve().parents[1]
CACHE_DIR = ROOT / "data" / "raw" / "fastf1_cache"

def main() -> None:
    fastf1.Cache.enable_cache(str(CACHE_DIR))

    year = 2023
    gp = "Bahrain"
    session = "R"

    print(f"Loading {year} {gp} {session} ...")
    s = fastf1.get_session(year, gp, session)
    s.load()

    laps = s.laps
    print("Loaded!")
    print("Rows in laps:", len(laps))
    print("Columns sample:", list(laps.columns)[:15])
    print(laps[["Driver", "LapNumber", "Position", "Time"]].head(10))

if __name__ == "__main__":
    main()