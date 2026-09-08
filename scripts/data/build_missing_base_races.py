import time
from pathlib import Path
import pandas as pd
import fastf1

fastf1.Cache.enable_cache("data/raw/fastf1_cache")

MISSING = [
    (2023, "Abu Dhabi Grand Prix"),
    (2023, "Japanese Grand Prix"),
    (2023, "Las Vegas Grand Prix"),
    (2023, "Mexico City Grand Prix"),
    (2023, "Qatar Grand Prix"),
    (2023, "São Paulo Grand Prix"),
    (2023, "United States Grand Prix"),
]

OUT = Path("data/interim/lap10/lap10_base_missing.csv")

COLUMNS = [
    "year", "event_name", "lap_x", "driver", "driver_number",
    "position_x", "session_time_x_seconds", "gap_to_leader_seconds",
    "lap_time_x_seconds", "compound_x", "tyre_life_x", "stint_x",
    "fresh_tyre_x", "pit_in_time_present", "pit_out_time_present",
    "track_status_x", "is_winner"
]

def build_snapshot(session):
    results = session.results.copy()
    laps = session.laps.pick_lap(10).copy()
    if laps.empty:
        raise ValueError("No lap 10 data")

    df = pd.DataFrame({
        "driver": laps["Driver"].astype(str),
        "driver_number": pd.to_numeric(laps["DriverNumber"], errors="coerce"),
        "position_x": pd.to_numeric(laps["Position"], errors="coerce"),
        "session_time_x_seconds": pd.to_timedelta(laps["Time"], errors="coerce").dt.total_seconds(),
        "lap_time_x_seconds": pd.to_timedelta(laps["LapTime"], errors="coerce").dt.total_seconds(),
        "compound_x": laps.get("Compound"),
        "tyre_life_x": pd.to_numeric(laps.get("TyreLife"), errors="coerce"),
        "stint_x": pd.to_numeric(laps.get("Stint"), errors="coerce"),
        "fresh_tyre_x": laps.get("FreshTyre"),
        "pit_in_time_present": (laps["PitInTime"].notna() if "PitInTime" in laps.columns else False).astype(int),
        "pit_out_time_present": (laps["PitOutTime"].notna() if "PitOutTime" in laps.columns else False).astype(int),
        "track_status_x": pd.to_numeric(laps.get("TrackStatus"), errors="coerce"),
    })

    leader_time = df.loc[df["position_x"] == 1, "session_time_x_seconds"]
    leader_value = leader_time.iloc[0] if len(leader_time) else df["session_time_x_seconds"].min()
    df["gap_to_leader_seconds"] = df["session_time_x_seconds"] - leader_value

    winner_abbr = None
    if "Position" in results.columns and "Abbreviation" in results.columns:
        w = results.loc[results["Position"] == 1]
        if not w.empty:
            winner_abbr = str(w["Abbreviation"].iloc[0])

    df["is_winner"] = (df["driver"] == winner_abbr).astype(int) if winner_abbr else 0
    df["year"] = int(session.event.year)
    df["event_name"] = str(session.event["EventName"])
    df["lap_x"] = 10

    for col in COLUMNS:
        if col not in df.columns:
            df[col] = pd.NA

    return df[COLUMNS]

def load_with_retry(session, retries=3, sleep=2.0):
    last = None
    for i in range(1, retries + 1):
        try:
            session.load()
            return
        except Exception as e:
            last = e
            print(f"[WARN] load attempt {i}/{retries} failed: {e}")
            time.sleep(sleep)
    raise last

def main():
    OUT.parent.mkdir(parents=True, exist_ok=True)

    all_rows = []
    failures = []

    for year, event in MISSING:
        try:
            print(f"\n=== {year} {event} ===")
            session = fastf1.get_session(year, event, "R")
            load_with_retry(session)

            df_race = build_snapshot(session)

            if int(df_race["is_winner"].sum()) != 1:
                raise ValueError("Winner rows != 1")

            all_rows.append(df_race)
            print(f"✅ OK rows={len(df_race)}")

        except Exception as e:
            print(f"❌ FAIL: {e}")
            failures.append((year, event, str(e)))

    if all_rows:
        df_all = pd.concat(all_rows, ignore_index=True)
        df_all.to_csv(OUT, index=False)
        print(f"\n✅ Saved: {OUT}")
        print("Rows:", len(df_all))
        print("Races:", df_all[["year", "event_name"]].drop_duplicates().shape[0])
        print("Winner rows:", int(df_all["is_winner"].sum()))

    if failures:
        fail_path = OUT.with_name("lap10_base_missing_failures.csv")
        pd.DataFrame(failures, columns=["year", "event_name", "error"]).to_csv(fail_path, index=False)
        print(f"\n⚠️ Failures saved to: {fail_path}")
        print("Failures:", len(failures))

if __name__ == "__main__":
    main()
