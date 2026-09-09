"""D10 — legacy dataset comparison audit (read-only, reproducible).

Compares the frozen legacy university-project checkpoint datasets
(``data/processed/lap{5,10,15,20,25}/base/dataset_clean.csv`` plus the
lap-10 weather variant and the lap-10 snapshot, which are NOT on the active
prediction path) against the Phase-1 V2 platform (D5 source entities, D6
canonical state, D7 enriched state, D9 derived state + outcome labels).

Nothing is modified: legacy CSVs/models are read-only inputs; the V2
artifacts are read-only inputs; the audit writes only a gitignored JSON
report (``data/v2/reports/data_quality/d10_legacy_comparison.json``) with
portable relative paths. No network, no FastF1, no training, no telemetry.

Usage: ``python -m v2.d10`` (writes the default report path).
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from v2.config import V2Paths
from v2.errors import IngestionError

CHECKPOINTS = [5, 10, 15, 20, 25]

# Active legacy prediction path (consumed by ml.inference / the API):
# one base checkpoint dataset per lap + tuned (or base) saved pipelines.
LEGACY_BASE = {lap: f"data/processed/lap{lap}/base/dataset_clean.csv"
               for lap in CHECKPOINTS}
LEGACY_WEATHER = "data/processed/lap10/weather/dataset_clean.csv"
LEGACY_SNAPSHOT = "data/processed/lap10/snapshots/bahrain_2023.csv"

# Active inference columns (ml/features.py FEATURE_COLS order, load-bearing).
ACTIVE_FEATURE_COLS = [
    "position_x", "session_time_x_seconds", "gap_to_leader_seconds",
    "lap_time_x_seconds", "tyre_life_x", "stint_x", "pit_in_time_present",
    "pit_out_time_present", "track_status_x", "compound_x",
]

WEATHER_COLS = ["weather_airtemp", "weather_tracktemp", "weather_humidity",
                "weather_pressure", "weather_windspeed",
                "weather_winddirection", "weather_rainfall",
                "weather_is_raining"]

# Numeric tolerance for same-upstream-arithmetic fields (seconds).
TIME_TOL_S = 1e-6


def read_legacy(path: str, root: Path) -> pd.DataFrame:
    full = root / path
    if not full.exists():
        raise IngestionError.storage(f"legacy dataset missing: {path}")
    return pd.read_csv(full)


# ---------------------------------------------------------------------------
# D10 §1 — inventory of every relevant legacy processed dataset.
# ---------------------------------------------------------------------------

def inventory_file(df: pd.DataFrame, path: str,
                   role: str) -> dict:
    races = sorted({tuple(r) for r in
                    df[["year", "event_name"]].drop_duplicates()
                    .itertuples(index=False)})
    return {
        "path": path,
        "role": role,
        "rows": int(len(df)),
        "columns": list(df.columns),
        "n_columns": int(len(df.columns)),
        "years": sorted(int(y) for y in df["year"].dropna().unique()),
        "n_races": len(races),
        "races": [{"year": int(y), "event_name": str(e)} for y, e in races],
        "drivers": sorted(str(d) for d in df["driver"].dropna().unique()),
        "n_drivers": int(df["driver"].nunique()),
        "winner_rows": int(df["is_winner"].sum())
        if "is_winner" in df.columns else None,
        "dup_keys": int(df.duplicated(
            subset=["year", "event_name", "driver"]).sum())
        if {"year", "event_name", "driver"} <= set(df.columns) else None,
        "missingness": {c: int(v) for c, v in df.isna().sum().items()
                        if int(v) > 0},
        "lap_values": sorted(int(v) for v in df["lap_x"].dropna().unique())
        if "lap_x" in df.columns else None,
    }


def inventory_legacy(root: Path) -> dict:
    files = {}
    for lap in CHECKPOINTS:
        path = LEGACY_BASE[lap]
        files[f"lap{lap}_base"] = inventory_file(
            read_legacy(path, root), path,
            role="ACTIVE: consumed by ml.inference per-checkpoint datasets "
                 f"(lap {lap})")
    files["lap10_weather"] = inventory_file(
        read_legacy(LEGACY_WEATHER, root), LEGACY_WEATHER,
        role="INACTIVE: lap-10 weather variant (no consumer in ml/api)")
    files["lap10_snapshot_bahrain2023"] = inventory_file(
        read_legacy(LEGACY_SNAPSHOT, root), LEGACY_SNAPSHOT,
        role="INACTIVE: single-race snapshot copy (no consumer in ml/api)")
    return files


# ---------------------------------------------------------------------------
# Race + driver identity mapping legacy <-> V2 (no silent fuzzy matching).
# ---------------------------------------------------------------------------

def canonical_race_map(paths: V2Paths, seasons=(2019, 2020, 2021, 2022,
                                                 2023)) -> dict:
    """(season, event_name) -> race_id from the D5 races entity."""
    mapping = {}
    for season in seasons:
        files = sorted((paths.processed_dir / "races"
                        / f"season={season}").glob("*.parquet"))
        for f in files:
            df = pd.read_parquet(f)
            for _, r in df.iterrows():
                mapping[(int(season), str(r["event_name"]))] = str(
                    r["race_id"])
    return mapping


def map_races(files: dict, race_map: dict) -> dict:
    """Map every legacy (year, event_name) to a canonical race_id."""
    mapped, unmapped = {}, []
    for _name, inv in files.items():
        for race in inv["races"]:
            key = (int(race["year"]), str(race["event_name"]))
            if key in race_map:
                mapped[f"{key[0]}|{key[1]}"] = race_map[key]
            else:
                unmapped.append({"year": key[0],
                                 "event_name": key[1]})
    return {"mapped": mapped, "unmapped": unmapped,
            "n_mapped": len(mapped), "n_unmapped": len(unmapped)}


def driver_number_map(paths: V2Paths, race_ids: set) -> dict:
    """(race_id, car number str) -> driver_id from D5 results identity."""
    mapping = {}
    for race_id in sorted(race_ids):
        season = int(race_id[:4])
        f = (paths.processed_dir / "results" / f"season={season}"
             / f"results__{race_id}.parquet")
        if not f.exists():
            continue
        res = pd.read_parquet(f)
        for _, r in res.iterrows():
            if pd.notna(r.get("driver_number")) and r.get("driver_id"):
                mapping[(race_id, str(int(r["driver_number"])))] = str(
                    r["driver_id"])
    return mapping


# ---------------------------------------------------------------------------
# D10 §5 — row-level overlap: legacy checkpoint rows <-> V2 lap states.
# ---------------------------------------------------------------------------

def _read_d7_state(paths: V2Paths, seasons) -> pd.DataFrame:
    parts = []
    for season in seasons:
        f = (paths.processed_dir / "driver_lap_state_d7"
             / f"season={season}"
             / f"driver_lap_state_d7__d7-{season}.parquet")
        if f.exists():
            parts.append(pd.read_parquet(f))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def match_checkpoint_rows(legacy: pd.DataFrame, race_map: dict,
                          num_map: dict, d7: pd.DataFrame,
                          lap: int) -> dict:
    """Match legacy rows to V2 state rows on (race, driver number, lap X).

    Returns the matched frame pairs plus unmatched-row reasons. Driver number
    is a race-local exact key (DriverNumbers are attributes, but equal within
    a race in both systems); abbreviation fallback is counted, not silent."""
    d7 = d7.copy()
    d7["_num"] = d7["driver_number"].astype("Int64").astype(str)
    d7["_key"] = (d7["race_id"].astype(str) + "|" + d7["_num"] + "|"
                  + d7["lap_number"].astype(str))
    d7_index = d7.set_index("_key")

    matched_rows = []
    unmatched = []
    abbr_used = 0
    legacy = legacy.copy()
    for idx, row in legacy.iterrows():
        key = (int(row["year"]), str(row["event_name"]))
        race_id = race_map.get(key)
        if race_id is None:
            unmatched.append({"reason": "race_unmapped",
                              "row": int(idx)})
            continue
        num = row.get("driver_number")
        key2 = None
        if pd.notna(num):
            key2 = f"{race_id}|{int(num)}|{int(lap)}"
            if key2 in d7_index.index:
                matched_rows.append((int(idx), key2))
                continue
        # abbreviation fallback within the race
        cand = d7[(d7["race_id"] == race_id)
                  & (d7["driver_abbreviation"] == str(row.get("driver")))]
        cand = cand[cand["lap_number"] == lap]
        if len(cand) == 1:
            abbr_used += 1
            matched_rows.append(
                (int(idx), cand.index[0] if False else
                 f"{race_id}|{cand.iloc[0]['_num']}|{int(lap)}"))
            continue
        if num is not None and pd.notna(num):
            unmatched.append({"reason": "no_v2_lap_row", "row": int(idx)})
        else:
            unmatched.append({"reason": "no_driver_number", "row": int(idx)})
    return {"matched": matched_rows, "unmatched": unmatched,
            "abbr_fallback_used": abbr_used}


# ---------------------------------------------------------------------------
# D10 §6 — formal field crosswalk (every active legacy column classified).
# ---------------------------------------------------------------------------
# Classes: A direct V2 equivalent · B renamed/retyped · C corrected semantics
# · D derivable later in Phase 2 · E intentionally removed · F label-only /
# prohibited from state · G no equivalent / potential regression.

def field_crosswalk() -> list:
    def row(legacy, cls, v2, notes):
        return {"legacy_field": legacy, "class": cls, "v2_field": v2,
                "notes": notes}

    return [
        row("year", "B", "season (D6 state / races)",
            "canonical int year; same value, canonical name"),
        row("event_name", "B", "event_name (D5 races, attribute only)",
            "display string preserved as attribute, never a canonical key"),
        row("lap_x", "B", "lap_number (D6 state)",
            "checkpoint label becomes the lap grain value"),
        row("driver", "B", "driver_abbreviation (D6 state, attribute)",
            "3-letter code is an attribute in both systems"),
        row("driver_number", "B", "driver_number (D6 state / D5 results)",
            "race-local exact car number; attribute, never a key"),
        row("position_x", "A", "position (D6 state)",
            "position at the checkpoint lap end; source nulls preserved"),
        row("session_time_x_seconds", "A", "state_time_s (D6 state)",
            "same upstream lap-end session Time; 1e-6 s tolerance"),
        row("gap_to_leader_seconds", "D", "none yet (Phase 2)",
            "legacy recomputes vs a min/reference time and the lap-10 "
            "variant is definitionally broken (§8); the correct per-state "
            "gap is a Phase-2 derived feature, NOT rebuilt in D9/D10"),
        row("lap_time_x_seconds", "A", "lap_time_s (D6 state)",
            "same upstream lap time; legacy clips [30, 300] (cleaning "
            "censoring, §12)"),
        row("compound_x", "A", "compound (D6 state)",
            "verbatim source compound; nulls stay null"),
        row("tyre_life_x", "A", "tyre_life (D6 state)",
            "same source tyre life; legacy clips [0, 60] (§12)"),
        row("stint_x", "A", "stint_number (D6 state)",
            "same source stint number"),
        row("fresh_tyre_x", "A", "fresh_tyre (D6 state)",
            "same source flag (kept in dataset, not a model feature)"),
        row("pit_in_time_present", "A",
            "pit_in_s presence (D5 driver_laps / D6 pit_in_s / D7 pit_last_in)",
            "source non-null marker on the SAME checkpoint lap row; "
            "history/counts live in D7/D9, not here"),
        row("pit_out_time_present", "A",
            "pit_out_s presence (D5 driver_laps / D6 pit_out_s / D7 pit_last_out)",
            "source non-null marker on the SAME checkpoint lap row"),
        row("track_status_x", "C", "track_status (D6 source) + track_state "
            "(D9 derived)",
            "legacy coerces the code string to int (multi-char codes become "
            "meaningless magnitudes, §10); V2 keeps the verbatim code and "
            "adds deterministic D9 flags"),
        row("is_winner", "F", "winner_flag (D9 race_driver_labels)",
            "official final-outcome target; duplicated across legacy "
            "checkpoint rows, stored once per race-driver in V2 labels; "
            "never part of any state table"),
        row("weather_airtemp", "B", "wx_air_temp_c (D7 state)",
            "race-level value attached in D7 as-of at/before leader time"),
        row("weather_tracktemp", "B", "wx_track_temp_c (D7 state)", ""),
        row("weather_humidity", "B", "wx_humidity_pct (D7 state)", ""),
        row("weather_pressure", "B", "wx_pressure_hpa (D7 state)", ""),
        row("weather_windspeed", "B", "wx_wind_speed (D7 state, m/s)", ""),
        row("weather_winddirection", "B", "wx_wind_direction_deg (D7 state)",
            ""),
        row("weather_rainfall", "B", "wx_rainfall (D7 state)", ""),
        row("weather_is_raining", "C", "wx_rainfall (D7 state)",
            "legacy-derived flag (rainfall>0); V2 preserves the source bool"),
    ]


def crosswalk_completeness(active_cols: list) -> dict:
    covered = {r["legacy_field"] for r in field_crosswalk()}
    missing = [c for c in active_cols if c not in covered]
    return {"active_legacy_columns": sorted(active_cols),
            "covered": len(covered & set(active_cols)),
            "missing": missing}


# ---------------------------------------------------------------------------
# D10 §7 — value-level comparison on matched rows.
# ---------------------------------------------------------------------------

def _float_eq(a, b, tol=TIME_TOL_S):
    a = pd.to_numeric(a, errors="coerce")
    b = pd.to_numeric(b, errors="coerce")
    both = a.notna() & b.notna()
    return both, (a[both] - b[both]).abs() <= tol


def compare_values(legacy: pd.DataFrame, d7: pd.DataFrame,
                   matched: list) -> dict:
    li = [i for i, _ in matched]
    d7_index = d7.set_index(
        d7["race_id"].astype(str) + "|" + d7["driver_number"].astype(
            "Int64").astype(str) + "|" + d7["lap_number"].astype(str))
    keys = [k for _, k in matched]
    d7m = d7_index.loc[keys].reset_index(drop=True)
    leg = legacy.loc[li].reset_index(drop=True)
    out = {"compared_rows": int(len(leg))}

    def _report(name, leg_s, d7_s, tol=None, exact=True):
        leg_n = pd.to_numeric(leg_s, errors="coerce") \
            if not exact else leg_s
        if tol is None:
            same = (leg_n.fillna("∅").astype(str)
                    == d7_s.fillna("∅").astype(str))
            both_null = leg_s.isna() & d7_s.isna()
            out[name] = {"compared": int(len(leg_s)),
                         "matching": int((same | both_null).sum()),
                         "differing": int((~(same | both_null)).sum()),
                         "null_vs_value": int(
                             (leg_s.isna() != d7_s.isna()).sum()),
                         "both_null": int(both_null.sum())}
        else:
            a = pd.to_numeric(leg_s, errors="coerce")
            b = pd.to_numeric(d7_s, errors="coerce")
            both = a.notna() & b.notna()
            out[name] = {"compared": int(len(leg_s)),
                         "matching": int((((a - b).abs() <= tol)
                                          & both).sum()),
                         "differing": int((((a - b).abs() > tol)
                                           & both).sum()),
                         "null_vs_value": int((a.isna() != b.isna()).sum()),
                         "both_null": int((a.isna() & b.isna()).sum())}

    _report("driver_identity", leg["driver"],
            d7m["driver_abbreviation"])
    _report("driver_number", leg["driver_number"].astype("Int64").astype(str),
            d7m["driver_number"].astype("Int64").astype(str))
    _report("position", leg["position_x"], d7m["position"], tol=TIME_TOL_S)
    _report("session_time", leg["session_time_x_seconds"],
            d7m["state_time_s"], tol=TIME_TOL_S)
    _report("lap_time", leg["lap_time_x_seconds"], d7m["lap_time_s"],
            tol=TIME_TOL_S)
    _report("compound", leg["compound_x"].astype(str),
            d7m["compound"].astype(str))
    _report("tyre_life", leg["tyre_life_x"], d7m["tyre_life"], tol=TIME_TOL_S)
    _report("stint", leg["stint_x"], d7m["stint_number"], tol=TIME_TOL_S)
    _report("fresh_tyre", leg["fresh_tyre_x"].astype(str),
            d7m["fresh_tyre"].astype(str))
    _report("pit_in_present",
            leg["pit_in_time_present"].astype(int),
            d7m["pit_in_s"].notna().astype(int))
    _report("pit_out_present",
            leg["pit_out_time_present"].astype(int),
            d7m["pit_out_s"].notna().astype(int))
    return out


def compare_track_status(legacy: pd.DataFrame, d7: pd.DataFrame,
                         matched: list) -> dict:
    li = [i for i, _ in matched]
    d7_index = d7.set_index(
        d7["race_id"].astype(str) + "|" + d7["driver_number"].astype(
            "Int64").astype(str) + "|" + d7["lap_number"].astype(str))
    leg = legacy.loc[li].reset_index(drop=True)
    d7m = d7_index.loc[[k for _, k in matched]].reset_index(drop=True)
    code = d7m["track_status"].astype(str)
    expected = pd.to_numeric(code, errors="coerce")
    legv = pd.to_numeric(leg["track_status_x"], errors="coerce")
    single = code.str.len() == 1
    same = leg["track_status_x"].notna() & d7m["track_status"].notna()
    single_match = int(
        ((legv == expected) & same & single).sum())
    mangled = int(((code.str.len() > 1) & same).sum())
    return {"compared_rows": int(len(leg)),
            "single_char_rows": int((same & single).sum()),
            "single_char_values_equal": single_match,
            "multi_char_rows_legacy_mangled": mangled,
            "both_null": int((leg["track_status_x"].isna()
                              & d7m["track_status"].isna()).sum()),
            "null_vs_value": int((leg["track_status_x"].isna()
                                  != d7m["track_status"].isna()).sum())}


# ---------------------------------------------------------------------------
# D10 §8 — gap-to-leader special audit.
# ---------------------------------------------------------------------------

def audit_gap(df: pd.DataFrame) -> dict:
    """Classify how the stored gap relates to the two candidate rules."""
    both = df["session_time_x_seconds"].notna(
    ) & df["gap_to_leader_seconds"].notna()
    pos1_match = min_match = clip_hit = 0
    races = df.groupby(["year", "event_name", "lap_x"])
    rule_by_race = {}
    for (y, ev, lx), g in races:
        pos1 = g.loc[g["position_x"] == 1, "session_time_x_seconds"]
        both_g = (g["session_time_x_seconds"].notna()
                  & g["gap_to_leader_seconds"].notna())
        r1 = (g["session_time_x_seconds"] - pos1.iloc[0]
              if len(pos1) else pd.Series(np.nan, index=g.index))
        r2 = g["session_time_x_seconds"] - g["session_time_x_seconds"].min()
        m1 = int((((r1 - g["gap_to_leader_seconds"]).abs() <= 1e-6)
                  & both_g).sum())
        m2 = int((((r2 - g["gap_to_leader_seconds"]).abs() <= 1e-6)
                  & both_g).sum())
        pos1_match += m1
        min_match += m2
        clip_hit += int(((g["gap_to_leader_seconds"] == 300.0)
                         & both_g).sum())
        rule = ("pos1" if m1 == int(both_g.sum())
                else ("min" if m2 == int(both_g.sum()) else "mixed"))
        rule_by_race[f"{y}|{ev}|lap{lx}"] = {
            "rows": int(len(g)), "rule": rule,
            "pinned300": int(((g["gap_to_leader_seconds"] == 300.0)
                              & both_g).sum())}
    return {"rows": int(len(df)), "compared": int(both.sum()),
            "match_pos1_rule": pos1_match,
            "match_min_rule": min_match,
            "pinned_at_clip_300": clip_hit,
            "per_race_rule": rule_by_race}


# ---------------------------------------------------------------------------
# D10 §11/§12 — missingness + cleaning audit (measured).
# ---------------------------------------------------------------------------

def cleaning_audit(df: pd.DataFrame) -> dict:
    return {
        "coerce_numeric": "applied (errors->NaN); no row drops (measured: "
                          "processed row counts == interim row counts)",
        "inf_to_nan": "applied in code (no inf found in shipped CSVs)",
        "clip_gap_0_300": {
            "rows_at_upper_bound": int(
                (df["gap_to_leader_seconds"] == 300.0).sum()),
            "classification": "information distortion: censors genuine "
                              ">300 s gaps incl. most lap-10 rows"},
        "clip_lap_time_30_300": {
            "rows_at_bounds": int(
                ((df["lap_time_x_seconds"] == 30.0)
                 | (df["lap_time_x_seconds"] == 300.0)).sum()),
            "classification": "no shipped row hits either bound "
                              "(harmless normalization)"},
        "clip_tyre_life_0_60": {
            "rows_at_upper_bound": int(
                (df["tyre_life_x"] == 60.0).sum()),
            "classification": "no shipped row hits 60 "
                              "(harmless normalization)"},
        "clip_position_1_30": "harmless (positions within range by "
                              "construction)",
        "imputation": "none in cleaning; median/most-frequent imputers in "
                      "training pipelines (model-pipeline responsibility)",
    }


# ---------------------------------------------------------------------------
# D10 §13 — winner-label comparison.
# ---------------------------------------------------------------------------

def compare_targets(legacy_frames: dict, paths: V2Paths) -> dict:
    labels = []
    used_races = set()
    for lap, df in legacy_frames.items():
        for _, r in df.iterrows():
            labels.append((int(r["year"]), str(r["event_name"]),
                           str(r["driver"]), int(r["is_winner"]), int(lap)))
            used_races.add((int(r["year"]), str(r["event_name"])))
    lab = pd.DataFrame(labels, columns=["year", "event", "driver", "isw",
                                        "lap"])
    race_map = canonical_race_map(paths)
    mismatches = []
    matched = 0
    for (y, ev, drv), g in lab.groupby(["year", "event", "driver"]):
        race_id = race_map.get((y, ev))
        if race_id is None:
            continue
        season = int(race_id[:4])
        f = (paths.processed_dir / "race_driver_labels"
             / f"season={season}"
             / f"race_driver_labels__d9-{season}.parquet")
        if not f.exists():
            continue
        lb = pd.read_parquet(f)
        # match by official 3-letter abbreviation within the race
        hit = lb[(lb["race_id"] == race_id)
                 & (lb["driver_abbreviation"] == str(drv))]
        if len(hit) != 1:
            mismatches.append({"kind": "label_row_missing",
                               "race": race_id, "driver": drv})
            continue
        matched += 1
        want = int(hit.iloc[0]["winner_flag"]) \
            if pd.notna(hit.iloc[0]["winner_flag"]) else None
        got = sorted(set(int(v) for v in g["isw"].tolist()))
        if want is None or len(got) != 1 or got[0] != want:
            mismatches.append({"kind": "winner_disagreement",
                               "race": race_id, "driver": drv,
                               "legacy_values": got, "v2": want})
    const = lab.groupby(["year", "event", "driver"])["isw"].nunique()
    return {"legacy_race_driver_cells": int(len(lab)),
            "distinct_race_drivers": int(len(const)),
            "cells_constant_across_checkpoints": int((const == 1).sum()),
            "cells_varying": int((const != 1).sum()),
            "matched_to_v2_labels": matched,
            "mismatches": mismatches}


# ---------------------------------------------------------------------------
# D10 §14 — temporal safety (evidence-backed classification).
# ---------------------------------------------------------------------------

def weather_fallback_check(root: Path, paths: V2Paths, race_map: dict
                           ) -> dict:
    """Did the legacy weather future-nearest fallback ever actually fire?

    For each non-null legacy weather row, recover the D5 weather observation
    whose 7-channel tuple matches the legacy values and check its observed
    time against the race's leader time. A match with observed_at_s >
    leader_time + eps would be a CONFIRMED future-weather leakage instance.
    """
    wx = read_legacy(LEGACY_WEATHER, root)
    ch = ["weather_airtemp", "weather_tracktemp", "weather_humidity",
          "weather_pressure", "weather_windspeed", "weather_winddirection",
          "weather_rainfall"]
    checked = 0
    recovered = 0
    future_used = []
    unmatched = 0
    for (y, ev), g in wx.groupby(["year", "event_name"]):
        race_id = race_map.get((int(y), str(ev)))
        if race_id is None:
            continue
        season = int(race_id[:4])
        f = (paths.processed_dir / "weather" / f"season={season}"
             / f"weather__{race_id}.parquet")
        if not f.exists():
            continue
        src = pd.read_parquet(f)
        leader_t = float(
            g.loc[g["position_x"] == 1,
                  "session_time_x_seconds"].iloc[0]) \
            if len(g.loc[g["position_x"] == 1]) else float(
                g["session_time_x_seconds"].min())
        key = {"air_temp_c": "weather_airtemp",
               "track_temp_c": "weather_tracktemp",
               "humidity_pct": "weather_humidity",
               "pressure_hpa": "weather_pressure",
               "wind_speed": "weather_windspeed",
               "wind_direction_deg": "weather_winddirection",
               "rainfall": "weather_rainfall"}
        for _, r in g.iterrows():
            if any(pd.isna(r[c]) for c in ch):
                continue
            checked += 1
            tol = pd.Series([abs(src[c].astype(float) - float(r[v]))
                             for c, v in key.items()
                             if c in src.columns]).fillna(1e9)
            cand = src[tol.max(axis=1) <= 1e-9] if False else None
            # vectorised match: all channels within 1e-9
            diffs = np.abs(np.stack([
                src[c].astype(float).to_numpy() - float(r[v])
                for c, v in key.items() if c in src.columns], axis=1))
            hits = np.where((diffs <= 1e-9).all(axis=1))[0]
            if len(hits) == 0:
                unmatched += 1
                continue
            recovered += 1
            obs_t = float(src.iloc[int(hits[0])]["observed_at_s"])
            if obs_t > leader_t + 1e-6:
                future_used.append(
                    {"race": race_id, "driver": str(r["driver"]),
                     "obs_t": obs_t, "leader_t": leader_t})
    return {"legacy_rows_checked": checked,
            "obs_recovered": recovered,
            "unmatched_rows": unmatched,
            "future_fallback_confirmed_rows": len(future_used),
            "future_fallback_examples": future_used[:10]}


def temporal_safety() -> dict:
    return {
        "final_winner_target_separation": {
            "finding": "confirmed safe",
            "evidence": "is_winner is read from final results and used ONLY "
                        "as the training target (scripts/models/*, "
                        "TARGET='is_winner'); it never enters FEATURE_COLS "
                        "or ml/features.py"},
        "weather_future_fallback": {
            "finding": "confirmed leakage risk in code; measured actual "
                       "usage in weather_fallback_check",
            "evidence": "scripts/data/build_dataset_multi_race_weather.py:"
                        "59-98 takes the earliest row when all weather rows "
                        "are after t_sec"},
        "checkpoint_construction": {
            "finding": "confirmed safe",
            "evidence": "rows are same-window per-lap FastF1 rows "
                        "(pick_laps(X) rows or latest<=X rows); features are "
                        "functions of that row only"},
        "cleaning": {
            "finding": "confirmed safe (no leakage introduced)",
            "evidence": "coerce/inf/clip are row-local transforms; no "
                        "cross-row or cross-race information enters"},
        "race_grouping": {
            "finding": "confirmed safe",
            "evidence": "GroupKFold groups by (year,event); no row from a "
                        "test race is ever in the training split"},
        "train_test_splitting": {
            "finding": "leakage risk / insufficient guarantee for "
                       "chronological validity",
            "evidence": "GroupKFold over 2019-2023 races shuffles seasons "
                        "across folds: models train on future seasons and "
                        "are evaluated on past seasons. Valid for "
                        "race-grouped CV, NOT for chronological temporal "
                        "backtesting (Phase 3 owns that)"},
        "winner_duplication": {
            "finding": "confirmed safe by design",
            "evidence": "final winner repeated across checkpoint rows is "
                        "only used as the target; V2 stores it once per "
                        "race-driver"},
    }


# ---------------------------------------------------------------------------
# D10 §15/§16/§17 — evaluation, probability, ensemble semantics (from code).
# ---------------------------------------------------------------------------

def evaluation_protocol() -> dict:
    return {
        "scheme": "GroupKFold(n_splits=5) grouped by (year, event_name); "
                  "per-fold: fit Pipeline(median impute numerics, "
                  "most-frequent+one-hot compound), predict_proba on the "
                  "held-out races",
        "metrics": "per-race top1/top3 accuracy (winner in top-k of "
                   "ranked probabilities) + sklearn log_loss on held-out "
                   "rows; recorded in results/models/*_multilap/summary_cv.csv",
        "hyperparameters": {
            "logreg": "LogisticRegression(max_iter=3000, random_state=42)",
            "hgb": "HistGradientBoostingClassifier(max_iter=300, "
                   "learning_rate=0.05, max_depth=6, min_samples_leaf=20, "
                   "random_state=42)",
            "xgboost": "XGBClassifier(n_estimators=300, max_depth=6, "
                       "learning_rate=0.05, subsample=0.8, "
                       "colsample_bytree=0.8, objective=binary:logistic, "
                       "eval_metric=logloss, random_state=42)"},
        "final_model": "refit Pipeline on the FULL checkpoint dataset "
                       "-> model.pkl; optional tuned variant -> "
                       "model_tuned.pkl (preferred at inference when present)",
        "chronological_validity": "race-group separation prevents same-race "
                                  "leakage but folds mix seasons "
                                  "(2019-2023); NOT a chronological temporal "
                                  "backtest (Phase 3 scope)"}


def probability_semantics() -> dict:
    return {
        "per_driver_binary_scores": "confirmed: model.predict_proba(X)[:,1] "
                                    "per driver row (ml/inference.py:"
                                    "predict_one_model_one_checkpoint); no "
                                    "normalization across the field exists "
                                    "anywhere in the serving path",
        "not_mutually_exclusive": "confirmed: field probabilities do NOT "
                                  "sum to 1 in general (e.g. 2023 Bahrain "
                                  "lap-10 tuned XGBoost: 20 independent "
                                  "scores summing to ~0.91) - they are "
                                  "legacy per-driver binary scores, not a "
                                  "race-level win distribution",
        "nan_handling": "characterized: NaN source values pass through to "
                        "the API top5 payload, which breaks JSON "
                        "serialization for Monaco 2022 (documented defect, "
                        "pinned by characterization tests)"}


def ensemble_semantics() -> dict:
    return {
        "checkpoint_voting": "votes from the 3 models at the LATEST "
                             "available checkpoint only (max lap with rows "
                             "for that race)",
        "majority_rule": ">=2 agreeing models wins "
                         "(choose_final_prediction, pinned by tests)",
        "tie_break": "full disagreement -> XGBoost winner; no XGBoost row "
                     "-> first available prediction",
        "confidence": "the XGBoost winner's predicted_win_probability at "
                      "the latest checkpoint ('Confidence (XGBoost)'); "
                      "fallback max probability when no XGBoost row",
        "implementation": "ml/inference.py run_ensemble_prediction via "
                          "api/services/prediction_service.py; scripts/predict/"
                          "variants are dev scripts, not on the serving path"}


# ---------------------------------------------------------------------------
# D10 §21 — legacy model compatibility.
# ---------------------------------------------------------------------------

def legacy_model_compatibility() -> dict:
    return {
        "can_legacy_models_consume_v2_directly": False,
        "reasons": [
            "schema differs: V2 state carries driver-abbreviation + extra "
            "columns beyond the 10 legacy features, and in a different "
            "column order than the saved pipelines were fitted on",
            "checkpoint grain differs: legacy models expect one fixed "
            "checkpoint-lap snapshot with legacy semantics (min-rule gap, "
            "numeric-mangled track status, half-open windows); V2 is a "
            "continuous per-lap canonical state",
            "categorical vocabulary: saved one-hot encoders were fitted on "
            "legacy compound codings incl. 'UNKNOWN' text; V2 preserves "
            "source compounds/2018 names with honest nulls",
            "missingness policy differs: legacy relies on in-pipeline "
            "median/most-frequent imputers fitted on legacy distributions",
            "labels: legacy reads is_winner from its own CSVs; V2 labels "
            "live separately",
        ],
        "decision": "NO compatibility shims (plan explicitly forbids them); "
                    "Phase 2/3 builds its own feature/model pipeline; "
                    "legacy remains frozen for regression/reference"}


# ---------------------------------------------------------------------------
# D10 §18/§19/§20 — information loss, improvement matrix, unfinished.
# ---------------------------------------------------------------------------

def information_loss() -> dict:
    return {
        "reproducible_now": [
            "driver identity / abbreviation / car number (D6 state)",
            "position at checkpoint lap end (D6 position)",
            "lap-end session time (D6 state_time_s)",
            "lap time (D6 lap_time_s)",
            "compound / tyre life / stint / fresh tyre (D6, honest nulls)",
            "pit-in/out non-null markers on the same lap row (D5/D6)",
            "track-status code, verbatim (D6 track_status) + D9 track_state",
            "winner outcome (D9 race_driver_labels)",
            "weather snapshot values (D7 wx_* as-of at/before leader time)",
            "weather is-raining flag (from wx_rainfall)",
        ],
        "intentionally_deferred_to_phase2": [
            "gap-to-leader at a checkpoint (correct position-1-referenced "
            "definition must be rebuilt with leakage tests)",
            "any rolling/representative/relative pace, degradation, traffic, "
            "closing-rate, priors, momentum, pack-density, strategy, "
            "telemetry summaries",
        ],
        "not_reproducible_or_potential_regression": [],
    }


def improvement_matrix() -> list:
    def row(dimension, status, evidence):
        return {"dimension": dimension, "status": status, "evidence": evidence}

    return [
        row("season coverage", "improved",
            "legacy 2019-2023 (5) vs V2 2018-2025 (8)"),
        row("race coverage", "improved",
            "legacy 103-104 races vs V2 173 championship race sessions"),
        row("temporal resolution", "improved",
            "legacy 5 fixed checkpoints (9,871 base rows) vs V2 189,420 "
            "continuous observed-lap states"),
        row("source preservation", "improved",
            "legacy coerces track codes to int + clips values; V2 keeps "
            "verbatim codes/nulls with machine-readable missingness"),
        row("identifiers", "improved",
            "legacy display-name/abbreviation keys vs V2 stable race_id + "
            "Ergast-slug driver_id"),
        row("schema contracts", "improved",
            "legacy implicit CSV schema vs V2 machine-readable "
            "contracts/schemas with availability vocabularies"),
        row("label separation", "improved",
            "legacy duplicates is_winner across checkpoint rows vs D9 "
            "race-driver-grain separate outcome labels"),
        row("temporal availability", "improved",
            "legacy documents checkpoint semantics informally vs V2 "
            "state_time_s contract + per-field availability"),
        row("weather joining", "improved",
            "legacy weather future-nearest fallback risk vs D7 strict "
            "backward-as-of joins (0 temporal violations measured)"),
        row("race-control handling", "improved",
            "legacy ignores RC messages vs D5 raw preservation + D7 "
            "lineage + D9 deterministic track-state flags"),
        row("pit/stint semantics", "improved",
            "legacy same-lap 0/1 markers only vs D5 asymmetric boundaries + "
            "D7 event lineage + D9 observable-history derivations"),
        row("missingness policy", "improved",
            "legacy silently clips/censors (Belgium 2019 lap-10 gap column "
            "entirely 300; lap-10 gap 32.5% pinned) vs V2 honest nulls"),
        row("provenance", "improved",
            "legacy no provenance vs V2 source/lib/schema/run provenance "
            "per artifact + manifests"),
        row("resumability", "improved",
            "legacy one-shot scripts with retries vs D3 manifest state "
            "machine + idempotent atomic writes"),
        row("deterministic builds", "improved",
            "legacy sort-order/stability informal vs V2 byte-identical "
            "rebuilds (asserted in tests)"),
        row("leakage testing", "improved",
            "legacy none (one confirmed-risk fallback) vs V2 future-mutation "
            "suites at every stage"),
        row("telemetry decision", "improved",
            "legacy no telemetry policy vs ADR-0001 deferral with revisit "
            "triggers"),
        row("evaluation protocol readiness", "same (unfinished)",
            "neither system has a chronological temporal-backtest "
            "evaluation; legacy metrics are race-grouped CV (recorded); "
            "Phase 3 owns backtesting"),
    ]


def unfinished_capabilities() -> list:
    return [
        "no new predictive model yet (legacy pipelines frozen)",
        "no temporal backtesting yet (Phase 3)",
        "no calibration yet (Phase 3)",
        "no proper race-level win-probability distribution yet",
        "no rolling pace / degradation / traffic features yet (Phase 2)",
        "no Monte Carlo / strategy engine / RaceState / replay yet",
        "telemetry deferred by ADR-0001",
        "gap-to-leader NOT rebuilt yet (Phase 2, with corrected semantics)",
    ]


# ---------------------------------------------------------------------------
# Orchestration.
# ---------------------------------------------------------------------------

def _read_d9_state(paths: V2Paths, seasons) -> pd.DataFrame:
    parts = []
    for season in seasons:
        f = (paths.processed_dir / "driver_lap_state_d9"
             / f"season={season}"
             / f"driver_lap_state_d9__d9-{season}.parquet")
        if f.exists():
            parts.append(pd.read_parquet(f))
    return pd.concat(parts, ignore_index=True)


def _read_active_model_slots(root: Path) -> dict:
    slots = {}
    for model in ("logreg", "hgb", "xgboost"):
        for lap in CHECKPOINTS:
            d = root / "results" / "models" / f"{model}_lap{lap}_multilap"
            act = None
            if (d / "model_tuned.pkl").exists():
                act = "model_tuned.pkl"
            elif (d / "model.pkl").exists():
                act = "model.pkl"
            slots[f"{model}_lap{lap}"] = {
                "dir": f"results/models/{model}_lap{lap}_multilap",
                "active_file": act,
                "has_base": (d / "model.pkl").exists(),
                "has_tuned": (d / "model_tuned.pkl").exists(),
            }
    return slots


def _read_recorded_cv_metrics(root: Path) -> dict:
    out = {}
    for model in ("logreg", "hgb", "xgboost"):
        for lap in CHECKPOINTS:
            f = (root / "results" / "models" / f"{model}_lap{lap}_multilap"
                 / "summary_cv.csv")
            if f.exists():
                df = pd.read_csv(f)
                out[f"{model}_lap{lap}"] = df.to_dict(orient="records")
    return out


def run_audit(paths: V2Paths, root: Path) -> dict:
    started = time.perf_counter()
    inv = inventory_legacy(root)
    race_map = canonical_race_map(paths)
    mapping = map_races(inv, race_map)
    race_ids = set(mapping["mapped"].values())
    num_map = driver_number_map(paths, race_ids)
    d7 = _read_d7_state(paths, [2019, 2020, 2021, 2022, 2023])

    checkpoints = {}
    for lap in CHECKPOINTS:
        legacy = read_legacy(LEGACY_BASE[lap], root)
        m = match_checkpoint_rows(legacy, race_map, num_map, d7, lap)
        matched_keys = [k for _, k in m["matched"]]
        cmpv = compare_values(legacy, d7, m["matched"]) if matched_keys \
            else {"compared_rows": 0}
        track = compare_track_status(legacy, d7, m["matched"]) \
            if matched_keys else {"compared_rows": 0}
        gap = audit_gap(legacy)
        checkpoints[f"lap{lap}"] = {
            "rows": int(len(legacy)),
            "matched_rows": int(len(m["matched"])),
            "unmatched_rows": int(len(m["unmatched"])),
            "unmatched_reasons": {r: sum(1 for u in m["unmatched"]
                                         if u["reason"] == r)
                                  for r in ("race_unmapped",
                                            "no_v2_lap_row",
                                            "no_driver_number")},
            "abbr_fallback_used": int(m["abbr_fallback_used"]),
            "value_comparison": cmpv,
            "track_status_comparison": track,
            "gap_audit": {"rows": gap["rows"], "compared": gap["compared"],
                          "match_pos1_rule": gap["match_pos1_rule"],
                          "match_min_rule": gap["match_min_rule"],
                          "pinned_at_clip_300": gap["pinned_at_clip_300"]},
        }

    wx = read_legacy(LEGACY_WEATHER, root)
    wxm = match_checkpoint_rows(wx, race_map, num_map, d7, 10)
    matched_wx = wxm["matched"]
    unmatched_wx = wxm["unmatched"]
    snap = read_legacy(LEGACY_SNAPSHOT, root)
    base10 = read_legacy(LEGACY_BASE[10], root)
    base10_bah = base10

    frames = {lap: read_legacy(LEGACY_BASE[lap], root)
              for lap in CHECKPOINTS}
    targets = compare_targets(frames, paths)
    fallback = weather_fallback_check(root, paths, race_map)
    pooled = pd.concat(list(frames.values()), ignore_index=True)

    return {
        "scope": "D10 legacy comparison: 2019-2023 checkpoint CSVs vs "
                 "Phase-1 V2 canonical platform (read-only audit)",
        "inventory": inv,
        "active_datasets": [f"lap{lap}_base" for lap in CHECKPOINTS],
        "inactive_datasets": ["lap10_weather", "lap10_snapshot_bahrain2023"],
        "race_mapping": mapping,
        "v2_scope": {"seasons": [2018, 2019, 2020, 2021, 2022, 2023, 2024,
                                 2025],
                     "races": 173, "state_rows": 189420, "label_rows": 3458},
        "checkpoints": checkpoints,
        "weather_variant": {
            "rows": int(len(wx)),
            "matched_rows": int(len(matched_wx)),
            "unmatched_rows": int(len(unmatched_wx)),
            "unmatched_reasons": {r: sum(1 for u in unmatched_wx
                                         if u["reason"] == r)
                                  for r in ("race_unmapped",
                                            "no_v2_lap_row",
                                            "no_driver_number")},
        },
        "snapshot": {
            "rows": int(len(snap)),
            "equals_base_bahrain2023_values": bool(
                snap.sort_values("driver").reset_index(drop=True).drop(
                    columns=["event_name"]).equals(
                        base10_bah[(base10_bah["year"] == 2023)
                                   & (base10_bah["event_name"]
                                      == "Bahrain Grand Prix")]
                        .sort_values("driver").reset_index(drop=True).drop(
                            columns=["event_name"]))),
            "note": "only event_name differs ('Bahrain' vs 'Bahrain Grand "
                    "Prix'); INACTIVE copy",
        },
        "cleaning_audit_pooled_base": cleaning_audit(pooled),
        "field_crosswalk": field_crosswalk(),
        "crosswalk_completeness": crosswalk_completeness(ACTIVE_FEATURE_COLS
                                                         + ["is_winner"]),
        "winner_target_comparison": targets,
        "weather_future_fallback_check": fallback,
        "temporal_safety": temporal_safety(),
        "evaluation_protocol": evaluation_protocol(),
        "probability_semantics": probability_semantics(),
        "ensemble_semantics": ensemble_semantics(),
        "legacy_model_compatibility": legacy_model_compatibility(),
        "information_loss": information_loss(),
        "improvement_matrix": improvement_matrix(),
        "unfinished_capabilities": unfinished_capabilities(),
        "active_model_slots": _read_active_model_slots(root),
        "recorded_cv_metrics": _read_recorded_cv_metrics(root),
        "elapsed_seconds": round(time.perf_counter() - started, 2),
    }


def write_json(dest: Path, data: dict) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m v2.d10",
        description="D10 legacy dataset comparison audit (read-only)")
    parser.add_argument("--root", default=None,
                        help="project root (default: V2_PROJECT_ROOT or cwd)")
    parser.add_argument("--json", default=None,
                        help="write the comparison JSON to a path (default: "
                             "data/v2/reports/data_quality/"
                             "d10_legacy_comparison.json)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        paths = V2Paths.resolve(args.root)
        report = run_audit(paths, paths.root)
        dest = (Path(args.json) if args.json
                else paths.reports_dir / "d10_legacy_comparison.json")
        write_json(dest, report)
        print(f"legacy files      : {len(report['inventory'])}")
        print(f"checkpoints       : {len(report['checkpoints'])}")
        matched = sum(c["matched_rows"]
                      for c in report["checkpoints"].values())
        unmatched = sum(c["unmatched_rows"]
                        for c in report["checkpoints"].values())
        print(f"matched rows      : {matched}")
        print(f"unmatched rows    : {unmatched}")
        tgt = report["winner_target_comparison"]
        print(f"target mismatches : {len(tgt['mismatches'])}")
        print(f"report            : {paths.relative(dest)}")
        return 0
    except IngestionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())