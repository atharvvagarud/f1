"""D7 — temporally-enriched canonical driver-lap state (Supporting Race Data).

Consumes the D6 canonical driver-lap state (``data/v2/processed/
driver_lap_state``) plus the D5 canonical supporting entities (weather /
race_control / pit_stops / stints) and produces the D7 enriched canonical
state dataset:

    data/v2/processed/driver_lap_state_d7/season=<Y>/driver_lap_state_d7__d7-<Y>.parquet
    data/v2/raw/manifests/d7-canonical.json           (dataset manifest)
    data/v2/reports/data_quality/d7_schema.json       (machine-readable schema)
    data/v2/reports/data_quality/d7_validation.json   (measured validation)
    data/v2/reports/data_quality/d7_coverage.json     (measured coverage)

Scope mapping (D7 mission §1) — every D7 output column set:

    D7 block           -> D5 source entity   -> join key / as-of rule
    weather (wx_*)     -> weather            -> race_id; latest obs with
                                                weather.observed_at_s
                                                <= state_time_s (backward-only)
    race-control       -> race_control       -> race_id; latest message with
    (rc_last_message_*)                        observed_at_s <= state_time_s
                                                (untimed messages never attach)
    pit (pit_last_*)   -> pit_stops          -> (race_id, driver_id); latest
                                                entry/exit event with event
                                                time <= state_time_s
    stint (stint_*)    -> stints             -> (race_id, driver_id) current
                                                stint_number == row
                                                stint_number; START-side facts
                                                only (guard start_lap <=
                                                lap_number); eventual end never
    Expected cardinality: every join is many-to-one/as-of onto the canonical
    state row -> enriched rows == state rows (189,420 whole scope), duplicate
    canonical PKs == 0.
    Availability class: IN_LAP / SOURCE_METADATA source facts and derived
    temporal lineage; NO LABEL_ONLY and NO model features.

Rules enforced (see v2/d7schema.py + docs/DATA_PLATFORM_ARCHITECTURE §D7):
- D6 canonical grain preserved exactly; ``state_time_s`` stays authoritative
  and is never reinterpreted.
- Every temporal attachment satisfies source_observed_time <= state_time_s.
- Weather uses strict backward/as-of joins ONLY (no future-nearest, no
  interpolation, no smoothing, no wetness derivation, no trends).
- Race control attaches the latest TIMESTAMPED message at/before the clock.
  Untimestamped messages (2018-r02, 69) stay in the source race_control table
  and are never invented into history nor attached to laps.
- Pit history is as-of: future pit events cannot affect earlier state.
  Asymmetric pit boundaries (pit_in-only / pit_out-only) are preserved; the
  missing side is never manufactured. No counts / next-pit / eventual stops.
- Stint context exposes only current-stint start-side facts; a source stint's
  eventual end is FUTURE information at earlier in-stint states and is never
  attached (no backfill of an earlier compound from a later stint, no
  future tyre-age fill).
- Missingness is preserved: no zero-filling, no future inference, no repair
  of Monaco 2022 / Belgium 2021 / 2018 etc.
- Determinism: same D5+D6 inputs -> logically identical enriched rows. The
  enrichment functions are pure and reusable for a full build, one race, or a
  state cutoff (training/serving parity; RaceState itself is NOT implemented).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import sys
import time
from pathlib import Path

import pandas as pd

from raceintel import contracts as C
from raceintel.pipeline import d6schema as D6S
from raceintel.pipeline import d7schema as S
from raceintel.config import V2Paths
from raceintel.errors import IngestionError
from raceintel.storage import atomic_write_parquet, dest_for_unit

# D5 supporting entities D7 integrates + the D6 canonical state source.
SUPPORT_ENTITIES = ("weather", "race_control", "pit_stops", "stints")
STATE_SOURCE_ENTITY = D6S.STATE_ENTITY

# Whole dataset scope = 2018..2025 (locked D5 Tier-A scope, mirrors D6).
DEFAULT_SCOPE = tuple(range(2018, 2026))

# Tolerated clock epsilon (seconds) for the <= state_time_s temporal check on
# real/synthetic floats (exact equality is the contract; the epsilon only
# absorbs float rounding, never a real future attachment).
_CLOCK_EPS = 1e-6

# --- source column subsets + renames per family -----------------------------

WX_SOURCE_COLS = ("observed_at_s", "air_temp_c", "track_temp_c",
                  "humidity_pct", "pressure_hpa", "wind_speed",
                  "wind_direction_deg", "rainfall")
WX_RENAME = {
    "observed_at_s": "wx_observed_at_s",
    "air_temp_c": "wx_air_temp_c",
    "track_temp_c": "wx_track_temp_c",
    "humidity_pct": "wx_humidity_pct",
    "pressure_hpa": "wx_pressure_hpa",
    "wind_speed": "wx_wind_speed",
    "wind_direction_deg": "wx_wind_direction_deg",
    "rainfall": "wx_rainfall",
}

RC_SOURCE_COLS = ("message_seq", "observed_at_s", "lap_number", "category",
                  "flag", "message_text")
RC_RENAME = {
    "message_seq": "rc_last_message_seq",
    "observed_at_s": "rc_last_message_observed_at_s",
    "lap_number": "rc_last_message_lap_number",
    "category": "rc_last_message_category",
    "flag": "rc_last_message_flag",
    "message_text": "rc_last_message_text",
}

PIT_SOURCE_COLS = ("driver_id", "lap_number", "pit_in_s", "pit_out_s")

STINT_SOURCE_COLS = ("driver_id", "stint_number", "start_lap", "compound",
                     "fresh_tyre", "tyre_age_at_start")
STINT_RENAME = {
    "start_lap": "stint_start_lap",
    "compound": "stint_compound",
    "fresh_tyre": "stint_fresh_tyre",
    "tyre_age_at_start": "stint_tyre_age_at_start",
}


def _column_block(prefix: str) -> list[str]:
    return [f.name for f in S.EXTENSION_FIELDS if f.name.startswith(prefix)]


def _require_columns(frame: pd.DataFrame, cols, entity: str) -> list[str]:
    missing = [c for c in cols if c not in frame.columns]
    if missing:
        raise IngestionError.validation(
            f"{entity} frame missing required columns: {sorted(missing)}")
    return list(cols)


# ---------------------------------------------------------------------------
# Reading canonical inputs (D6 state + D5 supporting entities).
# ---------------------------------------------------------------------------

def _read_entity(paths: V2Paths, entity: str, season: int, race_id: str
                 ) -> pd.DataFrame:
    dest = dest_for_unit(paths.processed_dir, entity, season, race_id)
    if not dest.exists():
        raise IngestionError.storage(
            f"D5/D6 source missing for {entity} {race_id}: "
            f"{paths.relative(dest)}")
    return pd.read_parquet(dest, engine="pyarrow")


def read_state_season(paths: V2Paths, season: int) -> pd.DataFrame:
    """The D6 canonical driver-lap state for one season (D7's base rows)."""
    return _read_entity(paths, D6S.STATE_ENTITY, int(season),
                        D6S.d6_unit_id(int(season)))


# ---------------------------------------------------------------------------
# As-of helpers (pure, deterministic; operate on ONE race's frames).
# ---------------------------------------------------------------------------

def _indexed(state: pd.DataFrame) -> pd.DataFrame:
    """Attach a deterministic row-identity column for as-of joins."""
    state = state.reset_index(drop=True).copy()
    state["__d7_idx"] = pd.Series(range(len(state)), dtype="int64")
    return state


def _extras_to_state(state: pd.DataFrame, extras: pd.DataFrame,
                     cols: list[str]) -> pd.DataFrame:
    """Merge per-row as-of extras (keyed by __d7_idx) back onto state rows.

    Many-to-one: extras carry one row per __d7_idx at most. Row count must be
    unchanged and __d7_idx must stay unique (a violation means an accidental
    row multiplication -> hard failure)."""
    extras = extras[["__d7_idx"] + cols].copy()
    dupes = int(extras["__d7_idx"].duplicated().sum())
    if dupes:
        raise IngestionError.validation(
            f"as-of extras produced {dupes} duplicate __d7_idx rows "
            f"(row multiplication); refusing")
    before = len(state)
    merged = state.merge(extras, on="__d7_idx", how="left")
    if len(merged) != before:
        raise IngestionError.validation(
            f"as-of attach changed row count ({before} -> {len(merged)})")
    return merged


def attach_weather_asof(state: pd.DataFrame, weather: pd.DataFrame
                        ) -> tuple[pd.DataFrame, list[str]]:
    """STRICT BACKWARD as-of weather attachment for one race.

    Attaches the latest weather observation with observed_at_s <=
    state_time_s. No prior observation -> weather fields null. Never uses a
    future observation (no nearest-in-both-directions, no future fallback)."""
    notes: list[str] = []
    state = _indexed(state)
    wx_cols = _column_block("wx_")
    base = state[["__d7_idx", "state_time_s"]].copy()

    present = [c for c in WX_SOURCE_COLS if c in weather.columns]
    missing = [c for c in WX_SOURCE_COLS if c not in present]
    if missing:
        notes.append(f"weather: source columns absent "
                     f"{sorted(missing)}; attached as null")

    extras = pd.DataFrame({"__d7_idx": pd.Series(dtype="int64")})
    if "observed_at_s" in present and len(weather):
        right = weather[present].copy()
        right = right[right["observed_at_s"].notna()]
        dup = int(right["observed_at_s"].duplicated().sum())
        if dup:
            # Weather PK is (race_id, observed_at_s): a duplicate timestamp in
            # canonical D5 weather is a source-integrity failure (the D5
            # normaliser dedupes; duplicates here mean the source was edited).
            raise IngestionError.validation(
                f"weather: {dup} duplicate observed_at_s rows (canonical "
                f"weather PK violated); as-of would be ambiguous")
        if len(right):
            right = right.rename(columns=WX_RENAME)
            right = right.sort_values("wx_observed_at_s", kind="mergesort")
            timed = base[base["state_time_s"].notna()].sort_values(
                "state_time_s", kind="mergesort")
            merged = pd.merge_asof(
                timed, right, left_on="state_time_s",
                right_on="wx_observed_at_s", direction="backward",
                allow_exact_matches=True)
            merged["wx_age_s"] = merged["state_time_s"] - merged[
                "wx_observed_at_s"]
            extras = merged.drop(columns=["state_time_s"])
    if extras.empty or "__d7_idx" not in extras.columns:
        extras = pd.DataFrame({"__d7_idx": base["__d7_idx"]})
    for col in wx_cols:
        if col not in extras.columns:
            extras[col] = None
    state = _extras_to_state(state, extras, wx_cols)
    return state, notes


def attach_race_control_asof(state: pd.DataFrame, race_control: pd.DataFrame
                             ) -> tuple[pd.DataFrame, list[str]]:
    """Latest TIMESTAMPED race-control message at/before state_time_s.

    Untimestamped messages (observed_at_s null) are NEVER attached and never
    invented into history. When multiple messages share an observed_at_s the
    later source-order message wins (deterministic)."""
    notes: list[str] = []
    state = _indexed(state)
    rc_cols = _column_block("rc_")
    base = state[["__d7_idx", "state_time_s"]].copy()

    present = [c for c in RC_SOURCE_COLS if c in race_control.columns]
    extras = pd.DataFrame({"__d7_idx": pd.Series(dtype="int64")})
    if "observed_at_s" in present and len(race_control):
        right = race_control[present].copy()
        total = len(right)
        right = right[right["observed_at_s"].notna()]
        untimed = int(total - len(right))
        if untimed:
            notes.append(
                f"race_control: {untimed} untimestamped messages excluded "
                f"from as-of attachment (never invented into history)")
        if len(right):
            right = right.rename(columns=RC_RENAME)
            # Deterministic tie-break for identical observed_at_s: the latest
            # source-order (highest message_seq) message is 'latest'.
            right = right.sort_values(
                ["rc_last_message_observed_at_s", "rc_last_message_seq"],
                kind="mergesort").drop_duplicates(
                    subset=["rc_last_message_observed_at_s"], keep="last")
            right = right.sort_values("rc_last_message_observed_at_s",
                                      kind="mergesort")
            timed = base[base["state_time_s"].notna()].sort_values(
                "state_time_s", kind="mergesort")
            merged = pd.merge_asof(
                timed, right, left_on="state_time_s",
                right_on="rc_last_message_observed_at_s",
                direction="backward", allow_exact_matches=True)
            merged["rc_last_message_age_s"] = merged["state_time_s"] - merged[
                "rc_last_message_observed_at_s"]
            extras = merged.drop(columns=["state_time_s"])
    if extras.empty or "__d7_idx" not in extras.columns:
        extras = pd.DataFrame({"__d7_idx": base["__d7_idx"]})
    for col in rc_cols:
        if col not in extras.columns:
            extras[col] = None
    state = _extras_to_state(state, extras, rc_cols)
    return state, notes


def _pit_events(pit_stops: pd.DataFrame, state: pd.DataFrame
                ) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Entry and exit event frames (driver_id, event_s, event_lap).

    Entry events come from pit_stops rows with pit_in_s (lap = entry lap).
    Exit events come from pit_stops rows with pit_out_s; the exit LAP is
    resolved 1:1 from the canonical state lap carrying that exact pit_out_s
    (pit_stops.lap_number is the ENTRY lap, and out-only rows have it null;
    the source exit marker always lives on a canonical lap)."""
    notes: list[str] = []
    entries = pit_stops[pit_stops["pit_in_s"].notna()][
        ["driver_id", "lap_number", "pit_in_s"]].rename(
        columns={"pit_in_s": "event_s", "lap_number": "event_lap"})
    if len(entries):
        entries["event_s"] = entries["event_s"].astype("float64")

    markers = state[state["pit_out_s"].notna()][
        ["driver_id", "pit_out_s", "lap_number"]].sort_values(
        "lap_number", kind="mergesort").drop_duplicates(
        subset=["driver_id", "pit_out_s"], keep="first")
    markers["pit_out_s"] = markers["pit_out_s"].astype("float64")
    raw_exits = pit_stops[pit_stops["pit_out_s"].notna()][
        ["driver_id", "pit_out_s"]].copy()
    raw_exits["pit_out_s"] = raw_exits["pit_out_s"].astype("float64")
    exits = raw_exits.merge(markers, on=["driver_id", "pit_out_s"],
                            how="left")
    if len(exits) != len(raw_exits):
        raise IngestionError.validation(
            "pit: exit-event lap resolution changed row count "
            f"({len(raw_exits)} -> {len(exits)}); refusing")
    unresolved = int(exits["lap_number"].isna().sum())
    if unresolved:
        notes.append(
            f"pit: {unresolved} exit events without a canonical lap marker "
            f"(out lap stays null)")
    exits = exits.rename(columns={"pit_out_s": "event_s",
                                  "lap_number": "event_lap"})
    return entries, exits, notes


def _asof_last_events(state: pd.DataFrame, events: pd.DataFrame,
                      prefix: str) -> pd.DataFrame:
    """Per-driver backward as-of of the latest prior event for each state row.

    Returns an extras frame (__d7_idx, <prefix>_lap, <prefix>_s) with one row
    per state row (null when the driver has no observable prior event).
    merge_asof with a 'by' is not used (keys must be globally sorted);
    per-driver merges are exact and deterministic on the small per-race driver
    population."""
    lap_col = f"{prefix}_lap"
    s_col = f"{prefix}_s"
    base = state[["__d7_idx", "driver_id", "state_time_s"]].copy()
    extras = pd.DataFrame({"__d7_idx": base["__d7_idx"]})
    extras[lap_col] = None
    extras[s_col] = None
    if len(events) == 0:
        return extras
    extras_parts: list[pd.DataFrame] = []
    for driver_id, ev in events.groupby("driver_id", sort=True):
        st = base[base["driver_id"] == driver_id].copy()
        ev = ev.sort_values("event_s", kind="mergesort")
        timed = st[st["state_time_s"].notna()].sort_values(
            "state_time_s", kind="mergesort")
        if ev.empty or timed.empty:
            continue
        matched = pd.merge_asof(
            timed, ev, left_on="state_time_s", right_on="event_s",
            direction="backward", allow_exact_matches=True)
        extras_parts.append(
            matched[["__d7_idx", "event_lap", "event_s"]].rename(
                columns={"event_lap": lap_col, "event_s": s_col}))
    if extras_parts:
        parts = pd.concat(extras_parts, ignore_index=True)
        extras = extras.merge(parts, on="__d7_idx", how="left",
                              suffixes=("", "_y"))
        for col in (lap_col, s_col):
            if f"{col}_y" in extras.columns:
                extras[col] = extras[col].where(
                    extras[col].notna(), extras[f"{col}_y"])
                extras = extras.drop(columns=[f"{col}_y"])
    extras = extras.sort_values("__d7_idx", kind="mergesort")
    return extras


def attach_pit_history_asof(state: pd.DataFrame, pit_stops: pd.DataFrame
                            ) -> tuple[pd.DataFrame, list[str]]:
    """Latest observable pit ENTRY and EXIT at/before state_time_s.

    Only pit events whose source session time is at/before state_time_s can
    attach; future pit events have zero effect on earlier state. Asymmetric
    boundaries are preserved: a pit_in-only stop contributes an entry but no
    exit; a pit_out-only stop contributes an exit but no entry. The missing
    side is never manufactured."""
    notes: list[str] = []
    state = _indexed(state)
    out_cols = ["pit_last_in_lap", "pit_last_in_s", "pit_last_out_lap",
                "pit_last_out_s"]
    if pit_stops is not None and len(pit_stops):
        entries, exits, ev_notes = _pit_events(pit_stops, state)
        notes.extend(ev_notes)
    else:
        entries = pd.DataFrame(columns=["driver_id", "event_s", "event_lap"])
        exits = entries.copy()
    in_extras = _asof_last_events(state, entries, "pit_last_in")
    out_extras = _asof_last_events(state, exits, "pit_last_out")
    extras = in_extras.merge(
        out_extras[["__d7_idx", "pit_last_out_lap", "pit_last_out_s"]],
        on="__d7_idx", how="left")
    state = _extras_to_state(state, extras, out_cols)
    return state, notes


def attach_stint_context(state: pd.DataFrame, stints: pd.DataFrame
                         ) -> tuple[pd.DataFrame, list[str]]:
    """Current-stint START-side context for one race.

    Matches each state row's own stint_number to the source stint record and
    attaches ONLY start-side facts (start_lap, fitted compound, fresh flag,
    tyre age at start). The source stint's eventual end_lap / exit boundary is
    FUTURE information at earlier in-stint states and is never attached.
    Guard: a stint whose start_lap > lap_number can never attach."""
    notes: list[str] = []
    state = _indexed(state)
    stint_cols = _column_block("stint_")
    extras = pd.DataFrame({"__d7_idx": state["__d7_idx"]})
    for col in stint_cols:
        extras[col] = None
    if len(stints) and "stint_number" in state.columns:
        _require_columns(stints, ["driver_id", "stint_number", "start_lap",
                                  "compound", "fresh_tyre",
                                  "tyre_age_at_start"], "stints")
        if int(stints["stint_number"].isna().sum()):
            raise IngestionError.validation(
                "stints: null stint_number present; merge key would be "
                "ambiguous")
        if int(stints.duplicated(subset=["driver_id",
                                         "stint_number"]).sum()):
            raise IngestionError.validation(
                "stints: duplicate (driver_id, stint_number) within a race; "
                "current-stint mapping would multiply rows")
        left = state[["__d7_idx", "driver_id", "stint_number",
                      "lap_number"]].copy()
        right = stints[["driver_id", "stint_number", "start_lap", "compound",
                        "fresh_tyre", "tyre_age_at_start"]].rename(
            columns=STINT_RENAME)
        # stints PK (race_id, driver_id, stint_number) is unique: many-to-one.
        matched = left.merge(right, on=["driver_id", "stint_number"],
                             how="left")
        if len(matched) != len(left):
            raise IngestionError.validation(
                f"stint: current-stint merge changed row count "
                f"({len(left)} -> {len(matched)}); refusing")
        guard = (matched["stint_start_lap"].notna()
                 & (matched["lap_number"] < matched["stint_start_lap"]))
        n_guard = int(guard.sum())
        if n_guard:
            notes.append(
                f"stint: {n_guard} rows where source stint start_lap > "
                f"lap_number (leak guard); stint context left null")
            for col in stint_cols:
                matched.loc[guard, col] = None
        extras = matched[["__d7_idx"] + stint_cols]
    state = _extras_to_state(state, extras, stint_cols)
    return state, notes


# ---------------------------------------------------------------------------
# Canonical D7 enrichment boundary (pure; THE reusable construction path).
# ---------------------------------------------------------------------------

def _canonical_cast(df: pd.DataFrame, cast: dict) -> pd.DataFrame:
    df = df.copy()
    for col, dtype in cast.items():
        if col not in df.columns:
            continue
        if dtype == "Int64":
            df[col] = df[col].astype("Int64")
        elif dtype == "float64":
            df[col] = df[col].astype("float64")
        elif dtype == "boolean":
            df[col] = df[col].astype("boolean")
        elif dtype == "bool":
            df[col] = df[col].astype("bool")
    return df


def enrich_race_state(state: pd.DataFrame, weather: pd.DataFrame | None,
                      race_control: pd.DataFrame | None,
                      pit_stops: pd.DataFrame | None,
                      stints: pd.DataFrame | None,
                      race_id: str) -> tuple[pd.DataFrame, list[str]]:
    """Deterministic D7 temporal enrichment for ONE race's canonical state.

    Pure function (no I/O, no clocks): attaches weather / race-control / pit /
    stint temporal context onto the D6 canonical state rows for one race. This
    is the single D7 enrichment path — reusable for the full historical build,
    one race, or a state-time cutoff (training/serving parity; RaceState is
    NOT implemented). Row count is preserved exactly; every join is
    many-to-one/as-of.
    """
    if len(state) == 0:
        raise IngestionError.validation(f"{race_id}: empty state to enrich")
    bad = {c for c in ("race_id", "driver_id", "lap_number", "state_time_s")
           } - set(state.columns)
    if bad:
        raise IngestionError.validation(
            f"{race_id}: state missing required columns: {sorted(bad)}")
    if set(state["race_id"].astype(str).unique()) != {race_id}:
        raise IngestionError.validation(
            f"{race_id}: enrich_race_state got state for other races "
            f"({sorted(set(state['race_id'].astype(str).unique()))})")
    before = len(state)
    notes: list[str] = []
    state, wx_notes = attach_weather_asof(
        state, weather if weather is not None
        else pd.DataFrame(columns=list(WX_SOURCE_COLS)))
    notes.extend(wx_notes)
    state, rc_notes = attach_race_control_asof(
        state, race_control if race_control is not None
        else pd.DataFrame(columns=list(RC_SOURCE_COLS)))
    notes.extend(rc_notes)
    state, pit_notes = attach_pit_history_asof(
        state, pit_stops if pit_stops is not None
        else pd.DataFrame(columns=list(PIT_SOURCE_COLS)))
    notes.extend(pit_notes)
    state, stint_notes = attach_stint_context(
        state, stints if stints is not None
        else pd.DataFrame(columns=list(STINT_SOURCE_COLS)))
    notes.extend(stint_notes)

    state = state.drop(columns=["__d7_idx"])
    if len(state) != before:
        raise IngestionError.validation(
            f"{race_id}: enrichment changed row count "
            f"({before} -> {len(state)}); grain violated")
    state = _canonical_cast(state, S.enriched_cast_dtypes())
    state = state[S.ENRICHED_COLUMNS]
    state = state.sort_values(["race_id", "driver_id", "lap_number"],
                              kind="mergesort").reset_index(drop=True)
    return state, notes


# ---------------------------------------------------------------------------
# Season / whole-dataset orchestration.
# ---------------------------------------------------------------------------

def _season_state_by_race(paths: V2Paths, season: int
                          ) -> tuple[pd.DataFrame, list[str]]:
    """Read the D6 season state and the D5 supporting entities per race, then
    enrich every race deterministically. Returns (enriched, race_id order)."""
    state = read_state_season(paths, int(season))
    race_ids = sorted(state["race_id"].astype(str).unique())
    parts: list[pd.DataFrame] = []
    notes_by_race: dict[str, list[str]] = {}
    total = 0
    for race_id in race_ids:
        race_state = state[state["race_id"] == race_id].reset_index(drop=True)
        support = {}
        for entity in SUPPORT_ENTITIES:
            try:
                support[entity] = _read_entity(paths, entity, int(season),
                                               race_id)
            except IngestionError as exc:
                if "source missing" in exc.message:
                    raise IngestionError.storage(
                        f"D7 requires D5 {entity} for {race_id} "
                        f"(missing: {exc.message}); refusing to enrich a "
                        f"season without its supporting source") from None
                raise
        enriched, notes = enrich_race_state(
            race_state, support["weather"], support["race_control"],
            support["pit_stops"], support["stints"], race_id)
        parts.append(enriched)
        notes_by_race[race_id] = notes
        total += len(enriched)
    season_enriched = pd.concat(parts, ignore_index=True)
    season_enriched = season_enriched.sort_values(
        ["race_id", "driver_id", "lap_number"],
        kind="mergesort").reset_index(drop=True)
    return season_enriched, notes_by_race


def build_season(paths: V2Paths, season: int) -> dict:
    """Deterministic D7 build for one season. Returns measured stats."""
    started = time.perf_counter()
    enriched, notes_by_race = _season_state_by_race(paths, int(season))
    dest = dest_for_unit(paths.processed_dir, S.STATE_ENTITY, int(season),
                         S.d7_unit_id(int(season)))
    atomic_write_parquet(enriched, dest)
    return {
        "season": int(season),
        "enriched_rows": int(len(enriched)),
        "races": int(enriched["race_id"].nunique()),
        "race_notes": {rid: sorted(n) for rid, n in
                       sorted(notes_by_race.items()) if n},
        "file": paths.relative(dest),
        "build_seconds": round(time.perf_counter() - started, 4),
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(dest: Path, data: dict) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _read_state_files(paths: V2Paths, seasons=DEFAULT_SCOPE) -> pd.DataFrame:
    parts = []
    for season in seasons:
        dest = dest_for_unit(paths.processed_dir, S.STATE_ENTITY,
                             int(season), S.d7_unit_id(int(season)))
        if not dest.exists():
            raise IngestionError.storage(f"D7 state file missing: {dest}")
        parts.append(pd.read_parquet(dest, engine="pyarrow"))
    return pd.concat(parts, ignore_index=True)


def build_dataset(paths: V2Paths, seasons=DEFAULT_SCOPE,
                  write_artifacts: bool = True) -> dict:
    """Build temporally-enriched canonical state for the requested seasons.

    Returns a measured build record (rows, files, checksums). When
    ``write_artifacts`` the dataset manifest + schema JSON are written under
    ``data/v2`` (gitignored)."""
    started = time.perf_counter()
    per_season: list[dict] = []
    files: list[Path] = []
    for season in seasons:
        stats = build_season(paths, int(season))
        per_season.append(stats)
        files.append(paths.processed_dir / S.STATE_ENTITY
                     / f"season={int(season)}"
                     / f"{S.STATE_ENTITY}__{S.d7_unit_id(int(season))}.parquet")
    total_rows = sum(s["enriched_rows"] for s in per_season)
    file_stats = {}
    for f in sorted(files):
        if f.exists():
            file_stats[paths.relative(f)] = {
                "bytes": f.stat().st_size,
                "sha256": _sha256(f),
            }
    total_bytes = sum(v["bytes"] for v in file_stats.values())
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    elapsed = time.perf_counter() - started
    report = {
        "dataset": "f1-intelligence-v2-driver-lap-state-d7",
        "deliverable": "D7 temporally-enriched canonical driver-lap state "
                       "(supporting race data)",
        "d7_schema_version": S.D7_SCHEMA_VERSION,
        "base_d6_schema_version": D6S.D6_SCHEMA_VERSION,
        "contracts_schema_version": C.SCHEMA_VERSION,
        "source": ("D6 driver_lap_state + D5 weather/race_control/"
                   "pit_stops/stints"),
        "scope_seasons": [int(s) for s in seasons],
        "enriched_rows": total_rows,
        "races": sum(s["races"] for s in per_season),
        "per_season": per_season,
        "files": file_stats,
        "storage_bytes": total_bytes,
        "peak_rss_bytes": rss,
        "total_build_seconds": round(elapsed, 4),
        "temporal_contract": (
            "every D7 attachment satisfies source_observed_time <= "
            "state_time_s (weather/race-control/pit by session time; stint by "
            "start_lap <= lap_number); weather is strict backward as-of; "
            "untimestamped race-control never attaches; future pit/stint "
            "facts never leak"),
        "grain": "D6 canonical grain preserved exactly (1 row per driver x "
                 "race x lap; row count reconciled against D6 in validation)",
    }
    if write_artifacts:
        manifest = dict(report)
        manifest["schema_json"] = S.schema_json()
        write_json(paths.manifest_path("d7-canonical.json"), manifest)
        write_json(paths.reports_dir / "d7_schema.json", S.schema_json())
    return report


# ---------------------------------------------------------------------------
# Validation (measured; used on the real dataset + synthetic tests).
# ---------------------------------------------------------------------------

def read_enriched_season(paths: V2Paths, season: int) -> pd.DataFrame:
    dest = dest_for_unit(paths.processed_dir, S.STATE_ENTITY, int(season),
                         S.d7_unit_id(int(season)))
    if not dest.exists():
        raise IngestionError.storage(f"D7 state file missing: {dest}")
    return pd.read_parquet(dest, engine="pyarrow")


def validate_dataset(paths: V2Paths, seasons=DEFAULT_SCOPE) -> dict:
    """Measure D7 integrity against the written parquet (all MEASURED).

    - row reconciliation vs the D6 canonical state (grain preservation)
    - PK uniqueness / null keys (unchanged canonical PK)
    - column conformance to the machine-readable enriched schema
    - label separation (no LABEL_ONLY columns)
    - temporal violations == 0 (wx/rc/pit observed time <= state_time_s;
      stint start_lap <= lap_number; non-negative staleness)
    - FK / race-set identity vs the D6 state.
    """
    findings: list[dict] = []
    all_d7 = _read_state_files(paths, seasons)
    total_rows = int(len(all_d7))
    dup_pks = int(all_d7.duplicated(subset=list(S.enriched_primary_key())).sum())
    pk0, pk1, pk2 = S.enriched_primary_key()
    null_pks = int((all_d7[pk0].isna() | all_d7[pk1].isna()
                    | all_d7[pk2].isna()).sum())

    # D6 base rows reconciliation (D6 state files are the input population).
    d6_parts = []
    for season in seasons:
        d6_parts.append(d6_state_for_season(paths, int(season)))
    d6 = pd.concat(d6_parts, ignore_index=True)
    if list(all_d7.columns) != S.ENRICHED_COLUMNS:
        findings.append({"check": "column-order",
                         "detail": f"enriched columns differ from schema"})

    # Temporal violation checks.
    t = all_d7
    viol = {}
    for col, clock_col, label in (
            ("wx_observed_at_s", "state_time_s", "weather"),
            ("rc_last_message_observed_at_s", "state_time_s", "race-control"),
            ("pit_last_in_s", "state_time_s", "pit-entry"),
            ("pit_last_out_s", "state_time_s", "pit-exit")):
        both = t[col].notna() & t[clock_col].notna()
        viol[label] = int(
            (t.loc[both, col] > t.loc[both, clock_col] + _CLOCK_EPS).sum())
    stint_both = t["stint_start_lap"].notna()
    viol["stint-start-lap"] = int(
        (t.loc[stint_both, "stint_start_lap"]
         > t.loc[stint_both, "lap_number"]).sum())
    for age_col, label in (("wx_age_s", "wx-age"),
                           ("rc_last_message_age_s", "rc-age")):
        both = t[age_col].notna()
        viol[label] = int((t.loc[both, age_col] < -_CLOCK_EPS).sum())
    temporal_ok = all(v == 0 for v in viol.values())
    if not temporal_ok:
        findings.append({"check": "temporal",
                         "detail": f"temporal violations: {viol}"})

    # Race-set identity vs D6 (no added/removed races).
    d7_races = set(all_d7["race_id"])
    d6_races = set(d6["race_id"])
    if d7_races != d6_races:
        findings.append({"check": "race-set",
                         "detail": f"races differ vs D6: added "
                                   f"{sorted(d7_races - d6_races)}, removed "
                                   f"{sorted(d6_races - d7_races)}"})

    # Label separation (inherited D6 guarantee, re-asserted on D7 output).
    labels = set(C.RESULTS.label_columns())
    present = set(all_d7.columns) & labels
    if present:
        findings.append({"check": "label-separation",
                         "detail": f"LABEL_ONLY columns present: "
                                   f"{sorted(present)}"})

    # Per-season missingness for the extension columns.
    extension_missingness = {}
    for season in seasons:
        st = read_enriched_season(paths, int(season))
        extension_missingness[int(season)] = {
            c: int(st[c].isna().sum()) for c in S.EXTENSION_COLUMNS
        }

    return {
        "d6_base_rows": int(len(d6)),
        "enriched_rows": total_rows,
        "row_delta": total_rows - int(len(d6)),
        "duplicate_pks": dup_pks,
        "null_pks": null_pks,
        "temporal_violations": viol,
        "temporal_ok": temporal_ok,
        "d7_races": len(d7_races),
        "d6_races": len(d6_races),
        "label_columns_present": sorted(present),
        "findings": findings,
        "extension_missingness": extension_missingness,
        "integrity_ok": (dup_pks == 0 and null_pks == 0
                         and total_rows == int(len(d6))
                         and temporal_ok and not present
                         and not findings),
    }


def d6_state_for_season(paths: V2Paths, season: int) -> pd.DataFrame:
    return read_state_season(paths, int(season))


# ---------------------------------------------------------------------------
# Coverage measurement (weather / race-control / pit / stint).
# ---------------------------------------------------------------------------

def _source_messages(paths: V2Paths, season: int, race_id: str
                     ) -> tuple[int, int]:
    rc = _read_entity(paths, "race_control", int(season), race_id)
    return int(len(rc)), int(rc["observed_at_s"].notna().sum())


def coverage_report(paths: V2Paths, seasons=DEFAULT_SCOPE) -> dict:
    """Actual attachment coverage per D7 source family (MEASURED).

    None of these are model-performance metrics: they measure how many
    canonical states carry observable context and how stale it is."""
    enriched_parts = []
    for season in seasons:
        enriched_parts.append(read_enriched_season(paths, int(season)))
    t = pd.concat(enriched_parts, ignore_index=True)
    t["season"] = t["race_id"].str[:4].astype(int)

    # --- weather -----------------------------------------------------------
    wx_present = t["wx_observed_at_s"].notna()
    weather = {
        "states_total": int(len(t)),
        "states_with_prior_weather": int(wx_present.sum()),
        "states_without_prior_weather": int((~wx_present).sum()),
        "age_seconds": {
            "min": float(t.loc[wx_present, "wx_age_s"].min())
            if wx_present.any() else None,
            "p50": float(t.loc[wx_present, "wx_age_s"].median())
            if wx_present.any() else None,
            "mean": float(t.loc[wx_present, "wx_age_s"].mean())
            if wx_present.any() else None,
            "p95": float(t.loc[wx_present, "wx_age_s"].quantile(0.95))
            if wx_present.any() else None,
            "max_staleness_s": float(t.loc[wx_present, "wx_age_s"].max())
            if wx_present.any() else None,
        },
        "per_season": {},
    }
    for season, g in t.groupby("season"):
        p = g["wx_observed_at_s"].notna()
        weather["per_season"][int(season)] = {
            "states": int(len(g)),
            "with_prior_weather": int(p.sum()),
            "coverage_frac": round(float(p.mean()), 6),
        }
    per_race_wx = t.groupby("race_id")["wx_observed_at_s"].agg(
        ["count", lambda s: int(s.notna().sum())])
    per_race_wx.columns = ["states", "with_wx"]
    no_wx_races = sorted(
        race_id for race_id, row in per_race_wx.iterrows()
        if row["states"] > 0 and row["with_wx"] == 0)
    weather["races_with_no_prior_weather_states"] = no_wx_races

    # --- race control ------------------------------------------------------
    rc_total = 0
    rc_timed = 0
    rc_distinct_attached = 0
    rc_states_attached = 0
    races_with_attached_rc = set()
    rc_sources = {}
    for season in seasons:
        st = read_enriched_season(paths, int(season))
        for race_id in sorted(st["race_id"].astype(str).unique()):
            total, timed = _source_messages(paths, int(season), race_id)
            rc_total += total
            rc_timed += timed
            rc_sources[race_id] = {"total": total, "timed": timed}
            seqs = st.loc[st["race_id"] == race_id,
                          "rc_last_message_seq"].dropna().astype(int)
            rc_distinct_attached += int(seqs.nunique())
            rc_states_attached += int(len(seqs))
            if len(seqs):
                races_with_attached_rc.add(race_id)
    race_control = {
        "messages_total_source": rc_total,
        "messages_timestamped": rc_timed,
        "messages_untimestamped": rc_total - rc_timed,
        "distinct_messages_attached_at_least_once": rc_distinct_attached,
        "races_with_attached_rc_context": len(races_with_attached_rc),
        "states_with_rc_lineage": rc_states_attached,
        "temporal_violations": 0,  # filled by validation; kept for the report
        "per_race_source": rc_sources,
    }

    # --- pit / stint --------------------------------------------------------
    pit_any = (t["pit_last_in_s"].notna() | t["pit_last_out_s"].notna())
    stint_any = t["stint_start_lap"].notna()
    entry_last = t["pit_last_in_s"].notna() & t["pit_last_out_s"].notna() \
        & (t["pit_last_in_s"] > t["pit_last_out_s"])
    source_pit = {"in_only": 0, "out_only": 0, "full": 0}
    source_stint_compound_null = 0
    for season in seasons:
        st = read_enriched_season(paths, int(season))
        for race_id in sorted(st["race_id"].astype(str).unique()):
            pits = _read_entity(paths, "pit_stops", int(season), race_id)
            source_pit["in_only"] += int(
                (pits["pit_in_s"].notna() & pits["pit_out_s"].isna()).sum())
            source_pit["out_only"] += int(
                (pits["pit_out_s"].notna() & pits["pit_in_s"].isna()).sum())
            source_pit["full"] += int(
                (pits["pit_in_s"].notna() & pits["pit_out_s"].notna()).sum())
            stints = _read_entity(paths, "stints", int(season), race_id)
            source_stint_compound_null += int(stints["compound"].isna().sum())
    pit_stint = {
        "states_with_observable_pit_context": int(pit_any.sum()),
        "states_with_pit_in_context": int(t["pit_last_in_s"].notna().sum()),
        "states_with_pit_out_context": int(t["pit_last_out_s"].notna().sum()),
        "states_with_current_stint_context": int(stint_any.sum()),
        "states_without_current_stint_context": int((~stint_any).sum()),
        "states_whose_last_observable_event_is_an_entry": int(
            entry_last.sum()),
        "source_pit_stops_in_only": source_pit["in_only"],
        "source_pit_stops_out_only": source_pit["out_only"],
        "source_pit_stops_full": source_pit["full"],
        "source_stint_compound_null": source_stint_compound_null,
    }

    return {
        "states_total": int(len(t)),
        "weather": weather,
        "race_control": race_control,
        "pit_stint": pit_stint,
    }


# ---------------------------------------------------------------------------
# CLI (python -m raceintel.pipeline.d7). Explicit scope; --all for the locked full build.
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m raceintel.pipeline.d7",
        description="D7 temporally-enriched canonical state build")
    parser.add_argument("--root", default=None,
                        help="project root (default: V2_PROJECT_ROOT or cwd)")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--season", type=int, action="append", default=[],
                       help="build one season (repeatable)")
    scope.add_argument("--all", action="store_true",
                       help="build the locked 2018-2025 scope")
    parser.add_argument("--validate", action="store_true",
                        help="run validation after building")
    parser.add_argument("--coverage", action="store_true",
                        help="measure and write the coverage report")
    parser.add_argument("--json", default=None,
                        help="write the measured build record JSON to a path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        paths = V2Paths.resolve(args.root)
        seasons = DEFAULT_SCOPE if args.all else args.season
        report = build_dataset(paths, seasons=seasons, write_artifacts=True)
        print(f"enriched rows       : {report['enriched_rows']}")
        print(f"races               : {report['races']}")
        print(f"storage bytes       : {report['storage_bytes']}")
        print(f"peak rss bytes      : {report['peak_rss_bytes']}")
        print(f"total build seconds : {report['total_build_seconds']}")
        for ps in report["per_season"]:
            print(f"  season {ps['season']}: rows={ps['enriched_rows']} "
                  f"races={ps['races']} ({ps['build_seconds']}s)")
        val = None
        cov = None
        if args.validate:
            val = validate_dataset(paths, seasons=seasons)
            write_json(paths.reports_dir / "d7_validation.json",
                       {"build": report, "validation": val})
            print(f"validation: rows={val['enriched_rows']} "
                  f"d6_base={val['d6_base_rows']} "
                  f"delta={val['row_delta']} dup_pks={val['duplicate_pks']} "
                  f"null_pks={val['null_pks']} "
                  f"temporal_ok={val['temporal_ok']} "
                  f"viol={val['temporal_violations']} "
                  f"findings={len(val['findings'])}")
        if args.coverage:
            cov = coverage_report(paths, seasons=seasons)
            write_json(paths.reports_dir / "d7_coverage.json", cov)
            print(f"coverage: states={cov['states_total']} "
                  f"weather_with_prior="
                  f"{cov['weather']['states_with_prior_weather']} "
                  f"rc_states={cov['race_control']['states_with_rc_lineage']} "
                  f"pit_states="
                  f"{cov['pit_stint']['states_with_observable_pit_context']} "
                  f"stint_states="
                  f"{cov['pit_stint']['states_with_current_stint_context']}")
        if args.json:
            payload = {"build": report}
            if val is not None:
                payload["validation"] = val
            if cov is not None:
                payload["coverage"] = cov
            write_json(Path(args.json), payload)
        return 0
    except IngestionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
