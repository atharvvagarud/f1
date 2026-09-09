"""Tier-A rich Race-session normalisation + FastF1 adapter (D5).

Pure normalisation (FastF1-shaped frames -> exact D2 Tier-A frames) is
pandas-only and fully offline-testable: every ``normalize_*`` function takes
small source-shaped DataFrames, never a live session. The thin loader
(``load_race_session``) owns FastF1 access (lazy import so module import and
unit tests never touch fastf1 or the network); the season adapter
(``make_tiera_race_adapter`` / ``tiera_race_adapter``) is the D3 ``AdapterFn``
that loads one Race session and returns the seven Tier-A frames for
``run_unit`` to validate, write and manifest.

Source semantics (FastF1 3.7.0, MEASURED on cached sessions):
- Identity is in-session: laps carry Driver (code) + DriverNumber; results
  carry DriverNumber + DriverId + TeamId. Laps join results on DriverNumber
  (unique per session). FastF1 DriverId/TeamId ARE Ergast-vocabulary slugs
  (verified 20/20 drivers, 10/10 teams vs D4 Tier-B), so no fuzzy matching:
  unmapped rows are anomalies, never guesses. D4 tables are a cross-check
  (§27), never an overwrite.
- Classification evidence is ``ClassifiedPosition`` (numeric = classified,
  letter = unclassified). ``Position`` is always populated (ordered
  retirements included) and ``Status`` text is not a DNF signal (D4:
  lapped '+N Laps' finishers are classified). ``dnf_flag`` therefore
  derives from the classification token only, per the corrected D2 note.
- Sessions are looked up by ROUND NUMBER from the schedule, never by
  display name (names fuzzy-match: 'Australian' resolved to Austria).
- Pit entry/exit observations pair per driver in session-time order (FIFO;
  each exit mates with the latest preceding entry). Consecutive stops can
  share a lap number, so lap adjacency is never the pairing rule. Stints
  group observed laps by the source Stint number.
- Weather ``Time`` is session-relative; race-control ``Time`` is absolute
  (observed_at_s via session t0). Both stay timestamped observations with
  past-only consumption (contract notes); D5 attaches no future rows.
- FastF1 warnings (stint fixes, incomplete position data) are source facts,
  never failures. WindSpeed is metres per second: FastF1 3.7.0
  ``_api.weather_data`` documents "Wind speed [m/s]" and passes the value
  through ``float()`` unconverted; observed 0.0-4.6 ranges are consistent.
- PARTIAL semantics (D5 adjudication): pit entry/exit mismatches (pit-lane
  starts, retirements in pits, red-flag procedures), stint-boundary nulls,
  verbatim unknown compounds and D4 cross-check mismatches are
  source/domain anomalies — the unit is COMPLETE with a persisted quality
  note. Only material incompleteness (shortened races, dropped source
  laps) is PARTIAL.
"""

from __future__ import annotations

import datetime as _datetime
from dataclasses import dataclass

import pandas as pd

from v2 import contracts as C
from v2.config import configure_fastf1_cache
from v2.errors import ErrorCategory, IngestionError
from v2.ingestion import AdapterResult, UnitContext
from v2.tierb import clean_str, to_float_or_null, to_int_or_null

TIERA_ENTITIES = ("races", "results", "driver_laps", "pit_stops", "stints",
                  "weather", "race_control")

# Explicit opt-in for FastF1 network I/O (mirrors the Jolpica gate): a load
# may fetch missing blobs, so live ingestion is an explicit act. Cached
# content itself never needs the network; unit tests never set this.
NETWORK_ENV_VAR = "V2_ALLOW_NETWORK"

# Sprint-weekend formats still stage a full Grand Prix Race session.
SPRINT_FORMATS = frozenset({"sprint", "sprint_shootout", "sprint_qualifying"})

# Non-championship schedule rows never become ingestion units.
NON_CHAMPIONSHIP_FORMATS = frozenset({"testing", "test"})


# --------------------------------------------------------------------------
# Scalar coercion (reuses Tier-B honest-null semantics).
# --------------------------------------------------------------------------

def seconds_or_null(value: object) -> float | None:
    """Timedelta / session-seconds -> float seconds | None (missing stays)."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (_datetime.timedelta, pd.Timedelta)):
        return float(value.total_seconds())
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def code_str(value: object) -> str | None:
    """Verbatim source code (track status, sector): int-like floats render
    without '.0' (18.0 -> '18'); empties -> None; never invented."""
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    text = str(value).strip()
    return text if text else None


def bool_or_null(value: object) -> bool | None:
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in ("true", "1", "yes"):
        return True
    if text in ("false", "0", "no"):
        return False
    return None


def _frame(rows: list[dict], entity: str) -> pd.DataFrame:
    contract = C.get_table(entity)
    return pd.DataFrame(rows, columns=contract.column_names())


def _dedupe_on_pk(rows: list[dict], key: tuple[str, ...],
                  entity: str) -> tuple[list[dict], str | None]:
    """First-occurrence-wins dedupe for timestamp-granularity artifacts
    (weather/race-control). Real entity dupes (laps/results/...) are never
    deduped: they fail loudly at the D3 boundary instead."""
    seen: set = set()
    unique: list[dict] = []
    dupes = 0
    for row in rows:
        k = tuple(row.get(col) for col in key)
        if k in seen:
            dupes += 1
            continue
        seen.add(k)
        unique.append(row)
    if dupes:
        return unique, (f"{entity}: {dupes} duplicate source timestamps "
                        f"deduped (first wins)")
    return unique, None


# --------------------------------------------------------------------------
# Event discovery / eligibility (pure over schedule-shaped frames).
# --------------------------------------------------------------------------

def discover_race_scope(schedule_df: pd.DataFrame, season: int) -> list[dict]:
    """Deterministic championship Race scope from a schedule frame.

    Keeps every championship round (conventional + sprint weekends: the
    Grand Prix Race is unaffected by sprint format). Drops pre-season
    testing / non-championship rows. Cancelled events never appear (the
    schedule omits them); a listed event with no usable date is flagged,
    never silently kept or dropped.
    """
    scope = []
    for _, row in schedule_df.iterrows():
        rnd = to_int_or_null(row.get("RoundNumber"))
        if rnd is None or rnd < 1:
            continue
        fmt = clean_str(row.get("EventFormat")) or "conventional"
        if fmt.lower() in NON_CHAMPIONSHIP_FORMATS:
            continue
        entry = {
            "season": int(season),
            "round_no": int(rnd),
            "event_name": clean_str(row.get("EventName")),
            "official_event_name": clean_str(row.get("OfficialEventName")),
            "country": clean_str(row.get("Country")),
            "location": clean_str(row.get("Location")),
            "event_format": fmt,
            "f1_api_support": bool_or_null(row.get("F1ApiSupport")),
        }
        scope.append(entry)
    scope.sort(key=lambda e: e["round_no"])
    return scope


# --------------------------------------------------------------------------
# Identity (in-session evidence; D4 cross-check, never overwrite).
# --------------------------------------------------------------------------

def build_driver_index(results_df: pd.DataFrame) -> dict:
    """DriverNumber (str) -> {driver_id, team_id, code}. Rows without a
    usable DriverId cannot be keyed: callers fail loudly, never guess."""
    index = {}
    for _, row in results_df.iterrows():
        num = code_str(row.get("DriverNumber"))
        driver_id = clean_str(row.get("DriverId"))
        if num is None or driver_id is None:
            raise IngestionError.validation(
                "results row without DriverNumber/DriverId cannot be keyed")
        index[num] = {
            "driver_id": driver_id,
            "team_id": clean_str(row.get("TeamId")),
            "code": clean_str(row.get("Abbreviation")),
        }
    return index


def cross_check_identity(season: int, index: dict, circuit_id: str | None,
                         processed_dir) -> list[str]:
    """Cross-check session identity against D4 Tier-B tables (§27).

    Mismatches are REPORTED (PARTIAL downstream), never applied: FastF1
    owns rich fields. Missing D4 files skip the check with a note (D4
    covers 2018+; absence is unexpected but not fatal).
    """
    from pathlib import Path

    notes = []
    base = Path(processed_dir)
    try:
        drivers = pd.read_parquet(
            base / "hist_drivers" / f"season={season}" /
            f"hist_drivers__tierb-{season}.parquet")
        known_drivers = set(drivers["driver_id"].dropna().tolist())
        unknown = sorted(set(v["driver_id"] for v in index.values())
                         - known_drivers)
        if unknown:
            notes.append(f"D4 driver cross-check: {len(unknown)} session "
                         f"drivers absent from Tier-B (e.g. {unknown[:3]!r})")
    except Exception:
        notes.append(f"D4 driver cross-check skipped (season={season} "
                     f"Tier-B drivers unavailable)")
    try:
        cons = pd.read_parquet(
            base / "hist_constructors" / f"season={season}" /
            f"hist_constructors__tierb-{season}.parquet")
        known_cons = set(cons["constructor_id"].dropna().tolist())
        session_cons = {v["team_id"] for v in index.values()
                        if v["team_id"] is not None}
        unknown_c = sorted(session_cons - known_cons)
        if unknown_c:
            notes.append(f"D4 constructor cross-check: {len(unknown_c)} "
                         f"session teams absent from Tier-B "
                         f"(e.g. {unknown_c[:3]!r})")
    except Exception:
        notes.append(f"D4 constructor cross-check skipped (season={season} "
                     f"Tier-B constructors unavailable)")
    if circuit_id is None:
        notes.append("circuit identity unresolved: no D4 (season, round) "
                     "mapping and no schedule slug; refusing to guess")
    return notes


def resolve_circuit_id(season: int, round_no: int,
                       processed_dir) -> str | None:
    """Circuit slug via D4 (season, round) key. Round-keyed, never fuzzy."""
    from pathlib import Path

    try:
        races = pd.read_parquet(
            Path(processed_dir) / "hist_races" / f"season={season}" /
            f"hist_races__tierb-{season}.parquet")
        hit = races[(races["season"] == season)
                    & (races["round_no"] == round_no)]
        if len(hit) == 1:
            return clean_str(hit.iloc[0]["circuit_id"])
    except Exception:
        pass
    return None


# --------------------------------------------------------------------------
# Entity normalisation (pure; source-shaped frames in -> DataFrames out).
# --------------------------------------------------------------------------

def normalize_races_row(season: int, round_no: int, scope_entry: dict,
                        total_laps, f1_api_support,
                        circuit_id: str | None) -> pd.DataFrame:
    race_id = C.make_race_id(season, round_no)
    row = {
        "race_id": race_id,
        "season": int(season),
        "round_no": int(round_no),
        "event_id": C.make_event_id(season, round_no),
        "circuit_id": circuit_id,
        "event_name": scope_entry.get("event_name"),
        "official_event_name": scope_entry.get("official_event_name"),
        "country": scope_entry.get("country"),
        "location": scope_entry.get("location"),
        "event_format": scope_entry.get("event_format"),
        "total_laps_scheduled": to_int_or_null(total_laps),
        "f1_api_support": bool_or_null(f1_api_support),
    }
    return _frame([row], "races")


def normalize_results(results_df: pd.DataFrame,
                      race_id: str) -> pd.DataFrame:
    """Official post-race outcomes. Classification evidence is
    ClassifiedPosition (numeric = classified, letter = unclassified);
    dnf_flag derives from that token ONLY (corrected D2 note). Quali
    columns (Q1/Q2/Q3) and total Time are out of contract scope: dropped."""
    rows = []
    for _, row in results_df.iterrows():
        driver_id = clean_str(row.get("DriverId"))
        if driver_id is None:
            raise IngestionError.validation(
                "results row without DriverId cannot be keyed")
        pos_final = to_int_or_null(row.get("Position"))
        class_token = code_str(row.get("ClassifiedPosition"))
        class_pos = (to_int_or_null(class_token)
                     if class_token is not None else None)
        # Numeric token = classified (even with 0 points / lapped status);
        # letter token (R/D/...) = officially unclassified. No other rule.
        dnf = True if class_pos is None else False
        rows.append({
            "race_id": race_id,
            "driver_id": driver_id,
            "driver_abbreviation": clean_str(row.get("Abbreviation")),
            "driver_number": to_int_or_null(code_str(
                row.get("DriverNumber"))),
            "team_id_at_race": clean_str(row.get("TeamId")),
            "grid_position": to_int_or_null(row.get("GridPosition")),
            "position_final": pos_final,
            "classified_position": class_pos,
            "position_text": class_token,
            "status_text": clean_str(row.get("Status")),
            "dnf_flag": dnf,
            "points": to_float_or_null(row.get("Points")),
            "laps_completed": to_int_or_null(row.get("Laps")),
            "winner_flag": (None if pos_final is None
                            else bool(pos_final == 1)),
            "podium_flag": (None if pos_final is None
                            else bool(pos_final in (1, 2, 3))),
        })
    return _frame(rows, "results")


def normalize_driver_laps(laps_df: pd.DataFrame, race_id: str,
                          index: dict) -> tuple[pd.DataFrame, list[str],
                                                list[str]]:
    """One row per observed lap. Unmapped DriverNumbers are dropped with an
    explicit partial reason (never guessed) — dropped source laps are
    materially incomplete output; NaN lap numbers likewise. Missing
    timing/sectors/traps stay null (quality notes only). Unexpected compound
    strings are preserved verbatim as quality notes, never coerced.

    Returns (frame, quality_notes, partial_reasons)."""
    quality: list[str] = []
    partial: list[str] = []
    unmapped: set = set()
    bad_lap = 0
    unexpected_compounds: dict = {}  # driver -> {compound: count}
    rows = []
    for _, row in laps_df.iterrows():
        num = code_str(row.get("DriverNumber"))
        hit = index.get(num) if num is not None else None
        if hit is None:
            if num is not None:
                unmapped.add(num)
            bad_lap += 1
            continue
        lap_no = to_int_or_null(row.get("LapNumber"))
        if lap_no is None:
            bad_lap += 1
            continue
        compound = clean_str(row.get("Compound"))
        if compound is not None and compound.strip().lower() in (
                "nan", "none", "null", ""):
            # Textual missingness artefacts (e.g. source 'nan'/'None') are
            # not compounds: stored as null, never as a verbatim token.
            compound = None
        if compound is not None and compound not in C.COMPOUNDS:
            by_c = unexpected_compounds.setdefault(hit["driver_id"], {})
            by_c[compound] = by_c.get(compound, 0) + 1
        rows.append({
            "race_id": race_id,
            "driver_id": hit["driver_id"],
            "lap_number": lap_no,
            "position": to_int_or_null(row.get("Position")),
            "session_time_end_s": seconds_or_null(row.get("Time")),
            "lap_start_s": seconds_or_null(row.get("LapStartTime")),
            "lap_time_s": seconds_or_null(row.get("LapTime")),
            "sector_1_s": seconds_or_null(row.get("Sector1Time")),
            "sector_2_s": seconds_or_null(row.get("Sector2Time")),
            "sector_3_s": seconds_or_null(row.get("Sector3Time")),
            "sector_1_end_s": seconds_or_null(row.get("Sector1SessionTime")),
            "sector_2_end_s": seconds_or_null(row.get("Sector2SessionTime")),
            "sector_3_end_s": seconds_or_null(row.get("Sector3SessionTime")),
            "speed_i1_kmh": to_float_or_null(row.get("SpeedI1")),
            "speed_i2_kmh": to_float_or_null(row.get("SpeedI2")),
            "speed_fl_kmh": to_float_or_null(row.get("SpeedFL")),
            "speed_st_kmh": to_float_or_null(row.get("SpeedST")),
            "compound": compound,
            "tyre_life": to_int_or_null(row.get("TyreLife")),
            "stint_number": to_int_or_null(row.get("Stint")),
            "fresh_tyre": bool_or_null(row.get("FreshTyre")),
            "pit_in_s": seconds_or_null(row.get("PitInTime")),
            "pit_out_s": seconds_or_null(row.get("PitOutTime")),
            "track_status": code_str(row.get("TrackStatus")),
            "deleted": bool_or_null(row.get("Deleted")),
            "deleted_reason": clean_str(row.get("DeletedReason")),
            "is_accurate": bool_or_null(row.get("IsAccurate")),
            "fastf1_generated": bool_or_null(row.get("FastF1Generated")),
        })
    for driver_id, by_c in unexpected_compounds.items():
        for compound, count in by_c.items():
            quality.append(f"driver {driver_id}: {count} laps compound "
                           f"{compound!r} preserved verbatim (outside the "
                           f"closed set)")
    if unmapped:
        partial.append(f"{len(unmapped)} DriverNumbers unmapped to DriverId, "
                       f"laps dropped (e.g. {sorted(unmapped)[:3]!r})")
    if bad_lap and not unmapped:
        partial.append(f"{bad_lap} lap rows unkeyable (NaN lap number), "
                       f"dropped")
    return _frame(rows, "driver_laps"), quality, partial


def _ordered_stops(laps_df: pd.DataFrame, race_id: str,
                   index: dict) -> tuple[dict, list[str]]:
    """Per-driver chronological (in_lap, out_lap, in_s, out_s) stop list.

    Stops are FIFO per driver: each exit pairs with the latest still-unpaired
    ENTRY whose session time precedes it (chronological pairing). Lap-number
    adjacency is NOT used as the pairing rule because consecutive stops can
    share a lap number (a car can leave the pits and re-enter on the same
    lap before crossing start/finish), which mis-pairs lap-adjacent entries
    and manufactures impossible negative durations. Session time is monotonic
    within a race, so the latest entry before an exit is its true mate; a
    red-flag lap renumbering never breaks chronological order.

    Leftover entries (retirement in pits) or exits keep nulls with an
    explicit note — reported, never silently merged.
    """
    notes = []
    stops: dict[str, list] = {}
    for num, hit in index.items():
        drv = laps_df[laps_df["DriverNumber"].astype(str) == str(num)]
        if drv.empty:
            continue
        ins = sorted(
            (lap, t) for lap, t in (
                (to_int_or_null(r.get("LapNumber")),
                 seconds_or_null(r.get("PitInTime")))
                for _, r in drv[drv["PitInTime"].notna()].iterrows())
            if lap is not None and t is not None)
        outs = sorted(
            (lap, t) for lap, t in (
                (to_int_or_null(r.get("LapNumber")),
                 seconds_or_null(r.get("PitOutTime")))
                for _, r in drv[drv["PitOutTime"].notna()].iterrows())
            if lap is not None and t is not None)
        # ins sorted by time (physical order); outs consumed in time order.
        paired = []
        for out_lap, out_s in sorted(outs, key=lambda p: p[1]):
            mate = None
            for in_lap, in_s in ins:
                if in_s < out_s:
                    mate = (in_lap, in_s)
                else:
                    break  # ins are time-sorted: no later entry precedes
            if mate is not None:
                ins.remove(mate)
                paired.append({"in_lap": mate[0], "out_lap": out_lap,
                               "in_s": mate[1], "out_s": out_s})
            else:
                paired.append({"in_lap": None, "out_lap": out_lap,
                               "in_s": None, "out_s": out_s})
        for in_lap, in_s in ins:
            paired.append({"in_lap": in_lap, "out_lap": None,
                           "in_s": in_s, "out_s": None})
        paired.sort(key=lambda p: (p["in_lap"] is None, p["in_lap"],
                                   p["out_lap"] is None, p["out_lap"]))
        n_ins = len([p for p in paired if p["in_lap"] is not None])
        n_outs = len([p for p in paired if p["out_lap"] is not None])
        if n_ins != n_outs:
            notes.append(f"driver {hit['driver_id']}: {n_ins} pit "
                         f"entries vs {n_outs} exits; paired "
                         f"chronologically, gaps stay null")
        if paired:
            stops[hit["driver_id"]] = paired
    return stops, notes


def normalize_pit_stops(laps_df: pd.DataFrame, race_id: str,
                        index: dict, stops: dict) -> pd.DataFrame:
    """Event log from precomputed stop pairs (see _ordered_stops)."""
    rows = []
    for driver_id, paired in stops.items():
        for seq, stop in enumerate(paired, start=1):
            duration = (None if stop["in_s"] is None or stop["out_s"] is None
                        else stop["out_s"] - stop["in_s"])
            rows.append({
                "race_id": race_id,
                "driver_id": driver_id,
                "stop_sequence": seq,
                "lap_number": stop["in_lap"],
                "pit_in_s": stop["in_s"],
                "pit_out_s": stop["out_s"],
                "duration_s": duration,
            })
    return _frame(rows, "pit_stops")


def normalize_stints(laps_df: pd.DataFrame, race_id: str,
                     index: dict, stops: dict) -> tuple[pd.DataFrame, list[str]]:
    """Stints group observed laps by source Stint number. Tyre age is the
    source TyreLife at the stint's first observed lap (includes laps in
    other sessions per source quirk — documented, not adjusted). Unknown
    tyre age is never inferred from later laps. Retired drivers keep
    end_lap = last observed lap (contract permits null for open stints)."""
    notes = []
    rows = []
    for num, hit in index.items():
        drv = laps_df[laps_df["DriverNumber"].astype(str) == str(num)]
        drv = drv[drv["Stint"].notna()]
        if drv.empty:
            continue
        stints = sorted({to_int_or_null(v) for v in drv["Stint"].tolist()
                         if to_int_or_null(v) is not None})
        paired = stops.get(hit["driver_id"], [])
        bounds = []
        for stint_no in stints:
            group = drv[drv["Stint"].astype(float) == float(stint_no)]
            laps_sorted = sorted(to_int_or_null(v)
                                 for v in group["LapNumber"].tolist()
                                 if to_int_or_null(v) is not None)
            if laps_sorted:
                bounds.append((stint_no, laps_sorted[0], laps_sorted[-1],
                               group))
        for pos, (stint_no, start_lap, end_lap, group) in enumerate(bounds):
            first = group[group["LapNumber"].astype(float)
                          == float(start_lap)].iloc[0]
            compound = clean_str(first.get("Compound"))
            # Lap-overlap boundaries (robust to red-flag stop insertions):
            # the stop that starts stint k>1 exits onto its first lap, so
            # pit_in_lap is that stop's ENTRY lap; the stop that ends stint
            # k<n enters on its last lap, so pit_out_lap is that stop's
            # EXIT lap. Contract keeps pit_in null for the opening stint
            # and pit_out null for the final stint regardless.
            pit_in = None
            if pos > 0:
                starts = [p for p in paired if p["out_lap"] == start_lap]
                if len(starts) > 1:
                    notes.append(f"driver {hit['driver_id']}: stint "
                                 f"{stint_no} matches {len(starts)} stops; "
                                 f"first wins")
                pit_in = starts[0]["in_lap"] if starts else None
                if pit_in is None and paired:
                    notes.append(f"driver {hit['driver_id']}: stint "
                                 f"{stint_no} starts lap {start_lap} with no "
                                 f"paired stop exit; boundary stays null")
            pit_out = None
            if pos < len(bounds) - 1:
                ends = [p for p in paired if p["in_lap"] == end_lap]
                if len(ends) > 1:
                    notes.append(f"driver {hit['driver_id']}: stint "
                                 f"{stint_no} matches {len(ends)} stops; "
                                 f"first wins")
                pit_out = ends[0]["out_lap"] if ends else None
                if pit_out is None and paired:
                    notes.append(f"driver {hit['driver_id']}: stint "
                                 f"{stint_no} ends lap {end_lap} with no "
                                 f"paired stop entry; boundary stays null")
            rows.append({
                "race_id": race_id,
                "driver_id": hit["driver_id"],
                "stint_number": stint_no,
                "compound": compound,
                "fresh_tyre": bool_or_null(first.get("FreshTyre")),
                "start_lap": start_lap,
                "end_lap": end_lap,
                "tyre_age_at_start": to_int_or_null(first.get("TyreLife")),
                "pit_in_lap": pit_in,
                "pit_out_lap": pit_out,
            })
    return _frame(rows, "stints"), notes


def normalize_weather(wx_df: pd.DataFrame,
                      race_id: str) -> tuple[pd.DataFrame, list[str]]:
    """Independent timestamped observations. ``Time`` is already
    session-relative; consumption rule (observed_at_s <= t) lives in the
    contract note, enforced by consumers, not stored here."""
    rows = []
    for _, row in wx_df.iterrows():
        rows.append({
            "race_id": race_id,
            "observed_at_s": seconds_or_null(row.get("Time")),
            "air_temp_c": to_float_or_null(row.get("AirTemp")),
            "track_temp_c": to_float_or_null(row.get("TrackTemp")),
            "humidity_pct": to_float_or_null(row.get("Humidity")),
            "pressure_hpa": to_float_or_null(row.get("Pressure")),
            "wind_speed": to_float_or_null(row.get("WindSpeed")),
            "wind_direction_deg": to_float_or_null(row.get("WindDirection")),
            "rainfall": bool_or_null(row.get("Rainfall")),
        })
    rows = [r for r in rows if r["observed_at_s"] is not None]
    contract = C.get_table("weather")
    rows, note = _dedupe_on_pk(rows, contract.primary_key, "weather")
    return _frame(rows, "weather"), ([note] if note else [])


def normalize_race_control(rc_df: pd.DataFrame, race_id: str,
                           t0_date) -> tuple[pd.DataFrame, list[str]]:
    """Raw messages, no interpretation: no SC/VSC derivation, no meaning
    inference. message_seq is 0-based source order, deterministic."""
    try:
        t0 = pd.Timestamp(t0_date)
    except (TypeError, ValueError):
        t0 = None
    rows = []
    for seq, (_, row) in enumerate(rc_df.iterrows()):
        when = row.get("Time")
        observed = None
        if t0 is not None and when is not None:
            try:
                stamp = pd.Timestamp(when)
                if (stamp.tzinfo is None) != (t0.tzinfo is None):
                    # Mixed tz-awareness: drop tz to stay comparable,
                    # documented; source is naive in practice.
                    if stamp.tzinfo is not None:
                        stamp = stamp.tz_localize(None)
                    else:
                        t0 = t0.tz_localize(None)
                observed = (stamp - t0).total_seconds()
            except (TypeError, ValueError):
                observed = None
        rows.append({
            "race_id": race_id,
            "message_seq": seq,
            "observed_at_s": observed,
            "lap_number": to_int_or_null(row.get("Lap")),
            "category": clean_str(row.get("Category")),
            "flag": clean_str(row.get("Flag")),
            "status": clean_str(row.get("Status")),
            "scope": clean_str(row.get("Scope")),
            "sector": code_str(row.get("Sector")),
            "racing_number": to_int_or_null(code_str(
                row.get("RacingNumber"))),
            "message_text": clean_str(row.get("Message")),
        })
    contract = C.get_table("race_control")
    rows, note = _dedupe_on_pk(rows, contract.primary_key, "race_control")
    return _frame(rows, "race_control"), ([note] if note else [])


# --------------------------------------------------------------------------
# Loader (thin FastF1 access; lazy import keeps module import offline).
# --------------------------------------------------------------------------

@dataclass
class LoadedRace:
    season: int
    round_no: int
    scope_entry: dict
    laps: pd.DataFrame
    results: pd.DataFrame
    weather: pd.DataFrame
    race_control: pd.DataFrame
    total_laps: int | None
    f1_api_support: bool | None
    t0_date: object = None


def fetch_schedule(season: int):
    """One schedule fetch (FastF1 caches it). Network only on cache miss."""
    import fastf1

    return fastf1.get_event_schedule(int(season))


def load_race_session(season: int, round_no: int,
                      cache_dir) -> LoadedRace:
    """Load one championship Race session by ROUND NUMBER (never by display
    name: names fuzzy-match across events). Errors map to the D3 taxonomy;
    FastF1 warnings are source facts, never failures. Single attempt: the
    D3 orchestration owns retries."""
    import os

    import fastf1
    from fastf1.req import RateLimitExceededError

    if os.environ.get(NETWORK_ENV_VAR) != "1":
        raise IngestionError.config(
            f"fastf1 loads may fetch missing blobs: set {NETWORK_ENV_VAR}=1 "
            f"for explicit live ingestion (tests inject fake sessions)")
    configure_fastf1_cache(cache_dir)
    try:
        schedule = fetch_schedule(int(season))
    except (RateLimitExceededError, TimeoutError, OSError) as exc:
        raise IngestionError.transient(
            f"schedule fetch failed for {season}: {type(exc).__name__}"
        ) from None
    rows = schedule[schedule["RoundNumber"] == int(round_no)]
    if rows.empty:
        raise IngestionError.missing(
            f"season {season} round {round_no}: not on the schedule "
            f"(cancelled or non-championship)")
    row = rows.iloc[0]
    fmt = clean_str(row.get("EventFormat")) or "conventional"
    if fmt.lower() in NON_CHAMPIONSHIP_FORMATS:
        raise IngestionError.config(
            f"season {season} round {round_no}: non-championship format "
            f"{fmt!r} is not a Tier-A unit")
    scope_candidates = discover_race_scope(
        schedule[schedule["RoundNumber"] == int(round_no)], int(season))
    if not scope_candidates:
        raise IngestionError.missing(
            f"season {season} round {round_no}: no eligible championship "
            f"event")
    scope_entry = scope_candidates[0]
    try:
        session = fastf1.get_session(int(season), int(round_no), "R")
        # Full default load (laps + telemetry + weather + messages): FastF1
        # derives Session.t0_date ONLY from telemetry/position data streams,
        # and race-control observed_at_s needs t0_date to convert the source's
        # absolute Utc timestamps to the session-relative clock. Telemetry is
        # cached (never promoted to canonical storage: telemetry_summary stays
        # an unmaterialised shell; D8 owns any retention decision).
        session.load()
    except RateLimitExceededError as exc:
        raise IngestionError.transient(
            f"FastF1 rate-limited for {season} R{round_no}") from None
    except (TimeoutError, OSError) as exc:
        raise IngestionError.transient(
            f"FastF1 load failed for {season} R{round_no}: "
            f"{type(exc).__name__}") from None
    except Exception as exc:
        from fastf1.core import DataNotLoadedError, InvalidSessionError, \
            NoLapDataError

        if isinstance(exc, (InvalidSessionError, NoLapDataError)):
            raise IngestionError.missing(
                f"season {season} round {round_no}: session unavailable "
                f"({type(exc).__name__})") from None
        if isinstance(exc, DataNotLoadedError):
            # FastF1 wraps per-endpoint fetch failures (e.g. upstream 429)
            # with @soft_exceptions: load() returns and the failed attribute
            # stays unset, so a later access raises DataNotLoadedError. This
            # is a transient fetch symptom (cached blobs are reused on the
            # retry), not a missing session: bounded D3 retry owns it.
            raise IngestionError.transient(
                f"season {season} round {round_no}: incomplete load "
                f"({exc})") from None
        if isinstance(exc, IngestionError):
            raise
        raise IngestionError(
            ErrorCategory.UNEXPECTED,
            f"{type(exc).__name__} loading {season} R{round_no}") from exc
    laps = session.laps
    if laps is None or len(laps) == 0:
        raise IngestionError.missing(
            f"season {season} round {round_no}: no usable laps")
    return LoadedRace(
        season=int(season), round_no=int(round_no), scope_entry=scope_entry,
        laps=laps, results=session.results, weather=session.weather_data,
        race_control=session.race_control_messages,
        total_laps=(to_int_or_null(getattr(session, "total_laps", None))),
        f1_api_support=bool_or_null(getattr(session, "f1_api_support", None)),
        t0_date=getattr(session, "t0_date", None))


# --------------------------------------------------------------------------
# Season adapter (D3 AdapterFn): one manifest unit = one Race session.
# --------------------------------------------------------------------------

def make_tiera_race_adapter(loader, season: int, round_no: int):
    """Build the D3 adapter for one Tier-A race unit.

    ``loader(season, round_no, cache_dir) -> LoadedRace`` keeps every test
    offline (fake sessions); the default live loader hits FastF1 sessions.
    """
    def adapter(ctx: UnitContext) -> AdapterResult:
        unit_season = ctx.entry.season
        unit_round = ctx.entry.round_no
        if (unit_season is None or int(unit_season) != int(season)
                or unit_round is None or int(unit_round) != int(round_no)):
            raise IngestionError.config(
                f"tiera adapter for {season} R{round_no} got unit "
                f"{ctx.entry.unit_id} (season={unit_season}, "
                f"round={unit_round})")
        race_id = C.make_race_id(int(season), int(round_no))
        loaded = loader(int(season), int(round_no), ctx.paths.cache_dir)
        index = build_driver_index(loaded.results)
        circuit_id = resolve_circuit_id(int(season), int(round_no),
                                        ctx.paths.processed_dir)
        if circuit_id is None:
            raise IngestionError.validation(
                f"unit {ctx.entry.unit_id}: circuit identity unresolved; "
                f"refusing to guess")
        # PARTIAL semantics (D5 adjudication): source/domain anomalies with
        # complete contract-required outputs stay COMPLETE with a persisted
        # quality note; only material incompleteness (shortened races,
        # dropped source laps) is PARTIAL. Unusual F1 facts alone never
        # imply PARTIAL.
        quality = cross_check_identity(int(season), index, circuit_id,
                                       ctx.paths.processed_dir)
        partial: list[str] = []
        races_frame = normalize_races_row(
            int(season), int(round_no), loaded.scope_entry,
            loaded.total_laps, loaded.f1_api_support, circuit_id)
        results_frame = normalize_results(loaded.results, race_id)
        laps_frame, lap_quality, lap_partial = normalize_driver_laps(
            loaded.laps, race_id, index)
        quality.extend(lap_quality)
        partial.extend(lap_partial)
        if len(laps_frame) == 0 and len(loaded.laps) > 0:
            raise IngestionError.validation(
                f"unit {ctx.entry.unit_id}: {len(loaded.laps)} source laps "
                f"but zero normalized rows")
        stops, stop_notes = _ordered_stops(loaded.laps, race_id, index)
        quality.extend(stop_notes)
        pits_frame = normalize_pit_stops(loaded.laps, race_id, index, stops)
        stints_frame, stint_notes = normalize_stints(
            loaded.laps, race_id, index, stops)
        quality.extend(stint_notes)
        weather_frame, wx_notes = normalize_weather(loaded.weather, race_id)
        quality.extend(wx_notes)
        rc_frame, rc_notes = normalize_race_control(
            loaded.race_control, race_id, loaded.t0_date)
        quality.extend(rc_notes)
        if (loaded.t0_date is None and len(rc_frame) > 0
                and rc_frame["observed_at_s"].notna().sum() == 0):
            quality.append("race-control observed_at_s unavailable: no "
                           "session t0 (source telemetry/position data "
                           "absent); lap_number preserved verbatim")
        # Shortened/red-flagged representation (D1 §6: ingest, then flag):
        # the winner must complete the scheduled distance; anything less
        # is a legitimate unusual race (PARTIAL), never silent.
        if (loaded.total_laps and len(laps_frame)
                and "lap_number" in laps_frame.columns):
            winner_laps = int(laps_frame["lap_number"].max())
            if winner_laps < loaded.total_laps and (
                    winner_laps < 0.75 * loaded.total_laps):
                partial.append(f"shortened race: {winner_laps}/"
                               f"{loaded.total_laps} laps observed")
        frames = {
            "races": races_frame,
            "results": results_frame,
            "driver_laps": laps_frame,
            "pit_stops": pits_frame,
            "stints": stints_frame,
            "weather": weather_frame,
            "race_control": rc_frame,
        }
        quality_note = "; ".join(n for n in quality if n) or None
        if quality_note is not None:
            quality_note = quality_note[:2000]
        partial_reason = "; ".join(n for n in partial if n) or None
        if partial_reason is not None:
            partial_reason = partial_reason[:2000]
        return AdapterResult(frames=frames, anomaly_note=quality_note,
                             partial_reason=partial_reason)

    return adapter


def tiera_race_adapter(ctx: UnitContext) -> AdapterResult:
    """Default live adapter for the CLI (explicit network opt-in inside)."""
    season = ctx.entry.season
    round_no = ctx.entry.round_no
    if season is None or round_no is None or not ctx.entry.race_id:
        raise IngestionError.config(
            f"fastf1 adapter needs a race unit, got '{ctx.entry.unit_id}'; "
            f"plan it with 'plan --season YYYY --rounds ...' first")

    def live_loader(s, r, cache_dir):
        return load_race_session(s, r, cache_dir)

    return make_tiera_race_adapter(
        live_loader, int(season), int(round_no))(ctx)
