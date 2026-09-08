import pandas as pd
from pathlib import Path

def find_first(patterns):
    for pat in patterns:
        hits = list(Path(".").glob(pat))
        if hits:
            # prefer the most recent if multiple exist
            hits.sort(key=lambda p: p.stat().st_mtime, reverse=True)
            return hits[0]
    return None

# Try a few common locations used in your project
base_candidates = [
    "**/processed/**/base/**/dataset_clean.csv",
    "**/processed/**/base/**/dataset*.csv",
    "**/processed/**/base*.csv",
    "**/data/processed/**/base/**/dataset_clean.csv",
    "**/data/processed/**/base/**/dataset*.csv",
]

weather_candidates = [
    "**/processed/**/weather/**/dataset_clean.csv",
    "**/processed/**/weather/**/dataset*.csv",
    "**/processed/**/weather*.csv",
    "**/data/processed/**/weather/**/dataset_clean.csv",
    "**/data/processed/**/weather/**/dataset*.csv",
]

BASE_PATH = find_first(base_candidates)
WEATHER_PATH = find_first(weather_candidates)

if BASE_PATH is None:
    raise FileNotFoundError(
        "Couldn't find base dataset. Tried patterns:\n- " + "\n- ".join(base_candidates)
    )
if WEATHER_PATH is None:
    raise FileNotFoundError(
        "Couldn't find weather dataset. Tried patterns:\n- " + "\n- ".join(weather_candidates)
    )

print(f"Using BASE:   {BASE_PATH}")
print(f"Using WEATHER:{WEATHER_PATH}")

base = pd.read_csv(BASE_PATH)
wthr = pd.read_csv(WEATHER_PATH)

def race_key(df: pd.DataFrame) -> pd.Series:
    if {"year", "event_name"}.issubset(df.columns):
        return df["year"].astype(str) + " " + df["event_name"].astype(str)
    if {"year", "race_name"}.issubset(df.columns):
        return df["year"].astype(str) + " " + df["race_name"].astype(str)
    if "year_event_name" in df.columns:
        return df["year_event_name"].astype(str)
    if {"season", "event"}.issubset(df.columns):
        return df["season"].astype(str) + " " + df["event"].astype(str)
    raise ValueError(
        "Could not infer race key columns. "
        "Expected (year,event_name) or (year,race_name) or year_event_name."
    )

base_races = set(race_key(base).unique())
wthr_races = set(race_key(wthr).unique())

missing_in_base = sorted(list(wthr_races - base_races))
missing_in_weather = sorted(list(base_races - wthr_races))

print(f"\nBase races: {len(base_races)} | Weather races: {len(wthr_races)}")

print("\nMissing in BASE (present in weather):")
for r in missing_in_base:
    print(" -", r)

print("\nMissing in WEATHER (present in base):")
for r in missing_in_weather:
    print(" -", r)

if not missing_in_base and not missing_in_weather:
    print("\n✅ Race sets match perfectly.")
else:
    print("\n⚠️ Race sets do not match yet.")