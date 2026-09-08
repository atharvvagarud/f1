"""
Build a full NON-WEATHER lap-X dataset for all races in a year range.

Purpose:
- Clean standalone builder for multilap experiments
- Builds the full interim dataset for a chosen lap checkpoint
- Does NOT use the old missing-race repair workflow

Outputs:
- data/interim/lap{lap}/lap{lap}_base.csv
- results/debug/lap{lap}_{start}_{end}_dataset_failures.csv
- results/debug/lap{lap}_{start}_{end}_dataset_year_failures.csv

Example:
    python scripts/data/build_dataset_multi_race_multilap.py --lap 5
    python scripts/data/build_dataset_multi_race_multilap.py --lap 15
"""

from pathlib import Path
import argparse
import time
import numpy as np
import pandas as pd
import fastf1


COLUMNS = [
    "year",
    "event_name",
    "lap_x",
    "driver",
    "driver_number",
    "position_x",
    "session_time_x_seconds",
    "gap_to_leader_seconds",
    "lap_time_x_seconds",
    "compound_x",
    "tyre_life_x",
    "stint_x",
    "fresh_tyre_x",
    "pit_in_time_present",
    "pit_out_time_present",
    "track_status_x",
    "is_winner",
]


def find_project_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists() and (p / "scripts").exists():
            return p
    raise RuntimeError("Could not locate project root (missing data/ and scripts/).")


def safe_total_seconds(series: pd.Series) -> pd.Series:
    return pd.to_timedelta(series, errors="coerce").dt.total_seconds()


def get_schedule_with_retry(year: int, retries: int = 3, sleep_s: float = 2.0) -> pd.DataFrame:
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            sched = fastf1.get_event_schedule(year, include_testing=False)
            if sched is None or sched.empty:
                raise RuntimeError(f"Empty schedule for year {year}")
            return sched
        except Exception as e:
            last_err = e
            print(f"[WARN] schedule load failed for {year} ({attempt}/{retries}): {e}")
            time.sleep(sleep_s)
    raise RuntimeError(f"Failed to load schedule for {year}") from last_err


def load_session_with_retry(session, retries: int = 3, sleep_s: float = 2.0) -> None:
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            session.load()
            return
        except Exception as e:
            last_err = e
            print(f"[WARN] session load failed ({attempt}/{retries}): {e}")
            time.sleep(sleep_s)
    raise last_err


def build_snapshot(session, lap_x: int) -> pd.DataFrame:
    results = session.results.copy()

    # FastF1 warning says use pick_laps instead of pick_lap
    laps = session.laps.pick_laps(lap_x).copy()
    if laps.empty:
        raise ValueError(f"No lap {lap_x} data available")

    df = pd.DataFrame({
        "driver": laps["Driver"].astype(str),
        "driver_number": pd.to_numeric(laps["DriverNumber"], errors="coerce"),
        "position_x": pd.to_numeric(laps["Position"], errors="coerce"),
        "session_time_x_seconds": safe_total_seconds(laps["Time"]),
        "lap_time_x_seconds": safe_total_seconds(laps["LapTime"]),
        "compound_x": laps["Compound"] if "Compound" in laps.columns else pd.NA,
        "tyre_life_x": pd.to_numeric(laps["TyreLife"], errors="coerce") if "TyreLife" in laps.columns else pd.NA,
        "stint_x": pd.to_numeric(laps["Stint"], errors="coerce") if "Stint" in laps.columns else pd.NA,
        "fresh_tyre_x": laps["FreshTyre"] if "FreshTyre" in laps.columns else pd.NA,
        "pit_in_time_present": (
            laps["PitInTime"].notna().astype(int) if "PitInTime" in laps.columns else 0
        ),
        "pit_out_time_present": (
            laps["PitOutTime"].notna().astype(int) if "PitOutTime" in laps.columns else 0
        ),
        "track_status_x": pd.to_numeric(laps["TrackStatus"], errors="coerce") if "TrackStatus" in laps.columns else pd.NA,
    })

    # Gap to leader from session time at lap X
    leader_time = df.loc[df["position_x"] == 1, "session_time_x_seconds"]
    leader_value = leader_time.iloc[0] if len(leader_time) else df["session_time_x_seconds"].min()
    df["gap_to_leader_seconds"] = df["session_time_x_seconds"] - leader_value

    # Winner label from official race results
    winner_abbr = None
    if "Position" in results.columns and "Abbreviation" in results.columns:
        winner_row = results.loc[results["Position"] == 1]
        if not winner_row.empty:
            winner_abbr = str(winner_row["Abbreviation"].iloc[0])

    df["is_winner"] = (df["driver"] == winner_abbr).astype(int) if winner_abbr else 0
    df["year"] = int(session.event.year)
    df["event_name"] = str(session.event["EventName"])
    df["lap_x"] = int(lap_x)

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    return df[COLUMNS].copy()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--lap", type=int, required=True, help="Lap checkpoint, e.g. 5, 10, 15, 20, 25")
    parser.add_argument("--start-year", type=int, default=2019)
    parser.add_argument("--end-year", type=int, default=2023)
    parser.add_argument("--cache-dir", type=str, default="data/raw/fastf1_cache")
    parser.add_argument("--retries", type=int, default=3)
    parser.add_argument("--sleep", type=float, default=2.0)
    args = parser.parse_args()

    if args.start_year > args.end_year:
        raise ValueError("start-year must be <= end-year")

    root = find_project_root(Path(__file__).resolve())

    cache_dir = root / args.cache_dir
    cache_dir.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(cache_dir))

    lap_tag = f"lap{args.lap}"

    out_dir = root / "data" / "interim" / lap_tag
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / f"{lap_tag}_base.csv"

    debug_dir = root / "results" / "debug"
    debug_dir.mkdir(parents=True, exist_ok=True)
    fail_csv = debug_dir / f"{lap_tag}_{args.start_year}_{args.end_year}_dataset_failures.csv"
    year_fail_csv = debug_dir / f"{lap_tag}_{args.start_year}_{args.end_year}_dataset_year_failures.csv"

    all_rows = []
    failures = []
    year_failures = []

    for year in range(args.start_year, args.end_year + 1):
        print(f"\n========== YEAR {year} ==========")
        try:
            schedule = get_schedule_with_retry(year, retries=args.retries, sleep_s=args.sleep)
        except Exception as e:
            print(f"❌ Failed to load schedule for year {year}: {e}")
            year_failures.append({"year": year, "error": str(e)})
            continue

        # Use EventName from the official schedule
        event_names = schedule["EventName"].dropna().astype(str).tolist()

        for event_name in event_names:
            print(f"\n=== {year} {event_name} ===")
            try:
                session = fastf1.get_session(year, event_name, "R")
                load_session_with_retry(session, retries=args.retries, sleep_s=args.sleep)

                df_race = build_snapshot(session, lap_x=args.lap)

                # basic sanity: exactly one winner row
                win_count = int(df_race["is_winner"].sum())
                if win_count != 1:
                    raise ValueError(f"Winner rows != 1 (got {win_count})")

                all_rows.append(df_race)
                print(f"✅ OK rows: {len(df_race)}")

            except Exception as e:
                print(f"❌ FAIL: {e}")
                failures.append({
                    "year": year,
                    "event_name": event_name,
                    "lap_x": args.lap,
                    "error": str(e),
                })

    if not all_rows:
        raise RuntimeError("No races were built successfully.")

    df_all = pd.concat(all_rows, ignore_index=True)

    # Stable sort
    sort_cols = [c for c in ["year", "event_name", "position_x", "driver_number"] if c in df_all.columns]
    if sort_cols:
        df_all = df_all.sort_values(sort_cols).reset_index(drop=True)

    # Replace inf just in case
    df_all.replace([np.inf, -np.inf], np.nan, inplace=True)

    df_all.to_csv(out_csv, index=False)
    print(f"\n✅ Saved: {out_csv}")
    print(f"Rows: {len(df_all)}")
    print(f"Races: {df_all[['year', 'event_name']].drop_duplicates().shape[0]}")
    print(f"Winner rows: {int(df_all['is_winner'].sum())}")

    if failures:
        pd.DataFrame(failures).to_csv(fail_csv, index=False)
        print(f"\n⚠️ Race-level failures saved to: {fail_csv}")
        print(f"Failures: {len(failures)}")

    if year_failures:
        pd.DataFrame(year_failures).to_csv(year_fail_csv, index=False)
        print(f"\n⚠️ Year-level failures saved to: {year_fail_csv}")
        print(f"Year failures: {len(year_failures)}")


if __name__ == "__main__":
    main()