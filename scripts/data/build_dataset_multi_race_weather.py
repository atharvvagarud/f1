"""
Build a multi-race dataset for in-race winner prediction at lap X,
with weather snapshot features added at the lap-X checkpoint.

Leakage-safe rule:
- Weather features are taken from session.weather_data at (or before)
  the lap-X reference time (we use leader's session time at lap X).
- Winner label comes from final results and is used ONLY as target.

Output:
- data/processed/lap10_2019_2023_dataset_weather.csv
- failures logs in results/debug/

Run:
  python scripts/data/build_dataset_multi_race_weather.py
"""

from __future__ import annotations

from pathlib import Path
import time
import fastf1
import pandas as pd
import numpy as np


def find_project_root(start: Path) -> Path:
    """
    Find repo root by walking upwards until we see BOTH:
    - data/ folder
    - scripts/ folder
    """
    for p in [start] + list(start.parents):
        if (p / "data").exists() and (p / "scripts").exists():
            return p
    raise RuntimeError("Could not locate project root (missing data/ and scripts/).")


START_YEAR = 2019
END_YEAR = 2023
SESSION = "R"
LAP_X = 10


def get_schedule_with_retry(year: int, retries: int = 1, delay_sec: int = 3) -> pd.DataFrame:
    last_err = None
    for attempt in range(retries + 1):
        try:
            return fastf1.get_event_schedule(year)
        except Exception as e:
            last_err = e
            if attempt < retries:
                print(f"!! Schedule fetch failed for {year} (attempt {attempt+1}/{retries+1}): {e}")
                time.sleep(delay_sec)
            else:
                raise last_err


def weather_at_time_seconds(s, t_sec: float) -> dict:
    """
    Return latest weather row at or before t_sec (seconds since session start),
    using FastF1 session.weather_data.

    If weather_data missing/empty, returns NaNs.
    """
    cols_wanted = ["AirTemp", "TrackTemp", "Humidity", "Pressure", "WindSpeed", "WindDirection", "Rainfall"]

    try:
        w = s.weather_data.copy()
        if w is None or w.empty:
            return {f"weather_{c.lower()}": np.nan for c in cols_wanted}

        # weather_data typically has a Timedelta column called 'Time'
        if "Time" not in w.columns:
            return {f"weather_{c.lower()}": np.nan for c in cols_wanted}

        w["time_seconds"] = w["Time"].dt.total_seconds()
        w = w.sort_values("time_seconds")

        # take last row with time_seconds <= t_sec
        w_sub = w[w["time_seconds"] <= t_sec]
        if w_sub.empty:
            # if all weather rows are after t_sec, take earliest as best-effort
            row = w.iloc[0]
        else:
            row = w_sub.iloc[-1]

        out = {}
        for c in cols_wanted:
            key = f"weather_{c.lower()}"
            out[key] = row[c] if c in w.columns else np.nan

        # Helpful derived flag (still leak-free)
        out["weather_is_raining"] = 1 if (pd.notna(out["weather_rainfall"]) and float(out["weather_rainfall"]) > 0) else 0
        return out

    except Exception:
        return {f"weather_{c.lower()}": np.nan for c in cols_wanted} | {"weather_is_raining": np.nan}


def build_race_snapshot_with_weather(year: int, event_name: str) -> pd.DataFrame:
    s = fastf1.get_session(year, event_name, SESSION)
    s.load()

    laps = s.laps.copy()
    if laps.empty:
        raise ValueError("Loaded laps are empty (0 drivers/laps).")

    laps_x = laps[laps["LapNumber"] <= LAP_X].copy()
    if laps_x.empty:
        raise ValueError(f"No laps at or before lap {LAP_X}.")

    latest = (
        laps_x.sort_values(["Driver", "LapNumber"])
             .groupby("Driver", as_index=False)
             .tail(1)
             .copy()
    )

    if latest["Driver"].nunique() == 0:
        raise ValueError("No drivers in latest snapshot (data load incomplete).")

    # Convert times to seconds
    latest["session_time_x_seconds"] = latest["Time"].dt.total_seconds()
    latest["lap_time_x_seconds"] = latest["LapTime"].dt.total_seconds()

    # Gap-to-leader at lap X
    leader_time = float(latest["session_time_x_seconds"].min())
    latest["gap_to_leader_seconds"] = latest["session_time_x_seconds"] - leader_time

    # Pit indicators (binary)
    latest["pit_in_time_present"] = latest["PitInTime"].notna().astype(int)
    latest["pit_out_time_present"] = latest["PitOutTime"].notna().astype(int)

    # Winner label from official results
    results = s.results.copy()
    if results.empty:
        raise ValueError("Results table is empty; cannot label winner.")
    winner_code = results.sort_values("Position").iloc[0]["Abbreviation"]
    latest["is_winner"] = (latest["Driver"] == winner_code).astype(int)

    # Weather snapshot at lap-X reference time (leader_time)
    wfeat = weather_at_time_seconds(s, leader_time)

    df = pd.DataFrame({
        "year": year,
        "event_name": event_name,
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
        # weather features (race-level, repeated for all drivers)
        **{k: [v] * len(latest) for k, v in wfeat.items()},
    })

    return df


def main() -> None:
    ROOT = find_project_root(Path(__file__).resolve())
    CACHE_DIR = ROOT / "data" / "raw" / "fastf1_cache"
    OUT_CSV = ROOT / "data" / "processed" / "lap10_2019_2023_dataset_weather.csv"

    DEBUG_DIR = ROOT / "results" / "debug"
    DEBUG_DIR.mkdir(parents=True, exist_ok=True)

    fastf1.Cache.enable_cache(str(CACHE_DIR))
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)

    all_rows = []
    failures = []
    year_failures = []

    for year in range(START_YEAR, END_YEAR + 1):
        try:
            schedule = get_schedule_with_retry(year, retries=1, delay_sec=3)
        except Exception as e:
            year_failures.append((year, str(e)))
            print(f"\n=== {year}: SKIPPED (schedule failed) ===\nReason: {e}\n")
            continue

        races = schedule.copy()
        if "EventFormat" in races.columns:
            races = races[races["EventFormat"] != "testing"].copy()

        print(f"\n=== {year}: {len(races)} events ===")

        for _, row in races.iterrows():
            event_name = row.get("EventName", None)
            if not event_name or pd.isna(event_name):
                continue

            rnd = row.get("RoundNumber", None)
            tag = f"{year} | {event_name}" + (f" | Round {rnd}" if pd.notna(rnd) else "")

            try:
                print(f"-> Building snapshot+weather: {tag}")
                df_race = build_race_snapshot_with_weather(year, event_name)

                win_count = int(df_race["is_winner"].sum())
                if win_count != 1:
                    raise ValueError(f"Winner rows != 1 (got {win_count})")

                all_rows.append(df_race)

            except Exception as e:
                failures.append((year, event_name, str(e)))
                print(f"!! Skipped {tag} due to error: {e}")

    if not all_rows:
        raise RuntimeError("No races processed successfully. Check errors above.")

    df_all = pd.concat(all_rows, ignore_index=True)
    df_all = df_all.sort_values(["year", "event_name", "position_x"]).reset_index(drop=True)
    df_all.to_csv(OUT_CSV, index=False)

    print(f"\nSaved dataset: {OUT_CSV}")
    print(f"Total rows: {len(df_all)}")
    print(f"Total races included: {df_all[['year','event_name']].drop_duplicates().shape[0]}")
    print(f"Total winner rows: {int(df_all['is_winner'].sum())}")

    if failures:
        fail_df = pd.DataFrame(failures, columns=["year", "event_name", "error"])
        fail_path = DEBUG_DIR / "lap10_2019_2023_dataset_weather_failures.csv"
        fail_df.to_csv(fail_path, index=False)
        print(f"\nRace-level failures saved to: {fail_path}")
        print(f"Race failures: {len(failures)}")

    if year_failures:
        yfail_df = pd.DataFrame(year_failures, columns=["year", "error"])
        yfail_path = DEBUG_DIR / "lap10_2019_2023_dataset_weather_year_failures.csv"
        yfail_df.to_csv(yfail_path, index=False)
        print(f"\nYear-level failures saved to: {yfail_path}")
        print(f"Year failures: {len(year_failures)}")


if __name__ == "__main__":
    main()