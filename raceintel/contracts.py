"""V2 canonical data contracts (D2 — Schema & Data Contracts).

Design-only module: deterministic key builders, table/column contracts,
temporal-availability vocabulary, units, provenance and layout rules for the
F1 Intelligence v2 Historical Data Platform.

STDLIB ONLY (dataclasses, enum, typing). No pandas/pyarrow/fastf1 imports:
contracts must be evaluable anywhere, including CI without data
dependencies. D3 ingestion and D11 validation implement against these
contracts; they do not live here.

Conventions honouring D0/D1 evidence:
- No ``_x``/``_y`` suffixes; physical units are explicit in names.
- Display names, abbreviations and driver numbers are ATTRIBUTES, never keys
  (D1: DriverNumber mutates across seasons; TeamId renames; event names vary).
- Final outcomes live in ``results`` only — ``driver_laps`` carries zero
  LABEL_ONLY columns (asserted in ``tests/test_v2_contracts.py``).
- Parquet-native nulls only; no sentinel values (Ergast ``-1`` becomes null
  at Tier-B normalisation).
"""

from dataclasses import dataclass, field
from enum import Enum

# Initial V2 schema version. Bump rules (documented in
# docs/DATA_PLATFORM_ARCHITECTURE.md §17): breaking = remove/rename/retype a
# column, change a key, or tighten nullability; additive = new nullable
# column or new table. Old partitions stay readable (Parquet is
# self-describing; readers select known columns).
SCHEMA_VERSION = 1

# Canonical V2 data root (proposal; no real data lives there during D2).
V2_DATA_ROOT = "data/v2"

# Recommended Parquet engine pin (validated D2 in a scratch env on
# Python 3.11 + pandas 2.3.3 + numpy 2.4.2: full nullable/type round-trip
# green). The requirements.txt addition itself belongs to D3 env setup,
# which re-verifies on its own runner.
RECOMMENDED_PYARROW_PIN = "pyarrow==25.0.1"

# Session codes for session identity. Canonical scope is Race ("R");
# other codes exist so identity stays total if scope ever widens.
SESSION_CODES = ("R", "S", "Q", "SS", "FP1", "FP2", "FP3")

# Closed compound set per FastF1 docs; UNKNOWN/TEST_UNKNOWN are legitimate
# source values (test/unknown sets), never to be coerced into a real compound.
COMPOUNDS = ("SOFT", "MEDIUM", "HARD", "INTERMEDIATE", "WET",
             "UNKNOWN", "TEST_UNKNOWN")

# Units confirmed in D5 from authoritative source metadata (fastf1 3.7.0
# ``_api.weather_data``: "Wind speed [m/s]", value passed through float()
# unconverted) — no longer "to confirm". Wind direction is degrees (0-359).
WIND_SPEED_UNIT = "m/s"


class Availability(str, Enum):
    """When could a value have been known? Answers Phase 2's
    'could this have been known at prediction time?' per field."""

    PRE_RACE = "PRE_RACE"            # knowable before the race (schedule, grid)
    LAP_START = "LAP_START"          # knowable when the lap begins
    IN_LAP = "IN_LAP"               # knowable once the in-race event completes
    LAP_END = "LAP_END"             # knowable when the lap completes
    POST_RACE = "POST_RACE"         # computed/declared after the race
    LABEL_ONLY = "LABEL_ONLY"       # final outcome; never a feature
    SOURCE_METADATA = "SOURCE_METADATA"  # identity/provenance, not a signal


@dataclass(frozen=True)
class Column:
    """One canonical column. ``dtype`` is a canonical logical type token
    (parquet logical types: string, int64, float64, bool, timestamp_utc);
    nullability is explicit; ``availability`` is the leakage contract."""

    name: str
    dtype: str
    unit: str  # physical unit, "none" for keys/flags/text, "n/a" for metadata
    nullable: bool
    availability: Availability
    owner: str  # canonical owning source, e.g. "fastf1-livetiming"
    description: str = ""


@dataclass(frozen=True)
class TableContract:
    entity: str
    grain: str
    primary_key: tuple
    foreign_keys: tuple = ()
    source_of_truth: str = ""
    partition_keys: tuple = ("season",)
    columns: tuple = ()
    notes: str = ""

    def column_names(self):
        return [c.name for c in self.columns]

    def columns_with_availability(self, availability):
        return [c.name for c in self.columns
                if c.availability is availability]

    def label_columns(self):
        return self.columns_with_availability(Availability.LABEL_ONLY)


# --------------------------------------------------------------------------
# Deterministic canonical key builders (pure functions, no I/O).
# Composite strings: reproducible across runs/machines, no UUIDs.
# --------------------------------------------------------------------------

def make_event_id(season: int, round_no: int) -> str:
    """Championship event identity. Round disambiguates multi-event venues
    (Austria/Styria, Bahrain/Sakhir 2020). Display names never participate."""
    return f"{season}-r{round_no:02d}"


def make_session_id(event_id: str, session_code: str) -> str:
    if session_code not in SESSION_CODES:
        raise ValueError(f"unknown session code: {session_code}")
    return f"{event_id}-{session_code}"


def make_race_id(season: int, round_no: int) -> str:
    """Race identity IS the Race-session identity (kept as one constructor
    so EVENT vs SESSION vs RACE-SESSION stay distinguishable in prose)."""
    return make_session_id(make_event_id(season, round_no), "R")


def make_driver_lap_key(race_id: str, driver_id: str, lap_number: int) -> tuple:
    return (race_id, driver_id, int(lap_number))


def make_pit_stop_key(race_id: str, driver_id: str, stop_sequence: int) -> tuple:
    return (race_id, driver_id, int(stop_sequence))


def make_stint_key(race_id: str, driver_id: str, stint_number: int) -> tuple:
    return (race_id, driver_id, int(stint_number))


def partition_path(entity: str, season: int, round_no: int | None = None) -> str:
    """Season-level partitioning by default (avoids thousands of tiny
    per-race files at ~1K rows each). Round-level is opt-in per entity."""
    base = f"{V2_DATA_ROOT}/processed/{entity}/season={season}"
    if round_no is None:
        return base
    return f"{base}/round={round_no:02d}"


# --------------------------------------------------------------------------
# Tier-A table contracts (rich 2018+ layer; sources: D1 capability audit).
# --------------------------------------------------------------------------

RACES = TableContract(
    entity="races",
    grain="one row per championship race session",
    primary_key=("race_id",),
    foreign_keys=(("event_id", "events(logical)"), ("circuit_id", "circuits")),
    source_of_truth="fastf1-schedule",
    columns=(
        Column("race_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "derived", "canonical race identity"),
        Column("season", "int64", "none", False, Availability.PRE_RACE,
               "fastf1-schedule", "championship year"),
        Column("round_no", "int64", "none", False, Availability.PRE_RACE,
               "fastf1-schedule", "championship round; stable post-season"),
        Column("event_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "derived", "championship event identity"),
        Column("circuit_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "jolpica-cross-check", "Ergast-vocabulary circuit slug"),
        Column("event_name", "string", "n/a", False, Availability.SOURCE_METADATA,
               "fastf1-schedule", "ATTRIBUTE ONLY: display name, never a key"),
        Column("official_event_name", "string", "n/a", True, Availability.SOURCE_METADATA,
               "fastf1-schedule", "ATTRIBUTE ONLY"),
        Column("country", "string", "n/a", True, Availability.SOURCE_METADATA,
               "fastf1-schedule", "ATTRIBUTE ONLY"),
        Column("location", "string", "n/a", True, Availability.SOURCE_METADATA,
               "fastf1-schedule", "ATTRIBUTE ONLY"),
        Column("event_format", "string", "n/a", True, Availability.PRE_RACE,
               "fastf1-schedule", "conventional | sprint | ..."),
        Column("total_laps_scheduled", "int64", "laps", True, Availability.PRE_RACE,
               "fastf1-livetiming", "scheduled distance; null if unavailable"),
        Column("f1_api_support", "bool", "none", True, Availability.SOURCE_METADATA,
               "fastf1-livetiming", "livetiming support flag for the event"),
    ),
    notes="No outcome columns: winner/results live in `results`.",
)

RESULTS = TableContract(
    entity="results",
    grain="one row per driver per race (official post-race outcome)",
    primary_key=("race_id", "driver_id"),
    foreign_keys=(("race_id", "races"), ("driver_id", "drivers"),
                  ("team_id_at_race", "constructors")),
    source_of_truth="fastf1-results",
    columns=(
        Column("race_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "derived", ""),
        Column("driver_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "fastf1-results", "permanent Ergast-vocabulary slug"),
        Column("driver_abbreviation", "string", "n/a", True, Availability.SOURCE_METADATA,
               "fastf1-results", "ATTRIBUTE ONLY (3-letter code)"),
        Column("driver_number", "int64", "none", True, Availability.SOURCE_METADATA,
               "fastf1-results", "ATTRIBUTE ONLY: mutable across seasons"),
        Column("team_id_at_race", "string", "n/a", True, Availability.SOURCE_METADATA,
               "fastf1-results", "constructor slug valid for this season"),
        Column("grid_position", "int64", "position", True, Availability.PRE_RACE,
               "fastf1-results", "actual starting grid incl. sprint-weekend effect"),
        Column("position_final", "int64", "position", True, Availability.LABEL_ONLY,
               "fastf1-results", "official finishing position"),
        Column("classified_position", "int64", "position", True, Availability.LABEL_ONLY,
               "fastf1-results", "classified position; null = not classified"),
        Column("position_text", "string", "n/a", True, Availability.LABEL_ONLY,
               "fastf1-results", "raw classification token, preserved verbatim"),
        Column("status_text", "string", "n/a", True, Availability.LABEL_ONLY,
               "fastf1-results", "raw status (Finished/Lapped/Retired/...)"),
        Column("dnf_flag", "bool", "none", True, Availability.LABEL_ONLY,
               "derived", "true iff officially unclassified (classified_"
               "position IS NULL as derived from the official classification "
               "token, e.g. FastF1 ClassifiedPosition letter). Never inferred "
               "from status text (D4: lapped '+N Laps' finishers are "
               "classified) nor from null position (D4: retirements carry "
               "classified numbers). Final ML binary-target policy deferred "
               "to the label stage; scoring R/D edge rows stay verbatim."),
        Column("points", "float64", "points", True, Availability.LABEL_ONLY,
               "fastf1-results", "championship points from this race"),
        Column("laps_completed", "int64", "laps", True, Availability.LABEL_ONLY,
               "fastf1-results", ""),
        Column("winner_flag", "bool", "none", True, Availability.LABEL_ONLY,
               "derived", "true iff position_final == 1"),
        Column("podium_flag", "bool", "none", True, Availability.LABEL_ONLY,
               "derived", "true iff position_final in (1,2,3)"),
    ),
    notes=("Post-race corrections/penalties are a provenance/versioning event: "
           "re-ingestion bumps pipeline_version, never edits history silently. "
           "dnf_flag is provisional classification evidence, not the ML DNF "
           "target: the final binary policy is deferred to the label stage."),
)

DRIVER_LAPS = TableContract(
    entity="driver_laps",
    grain="one driver x one race session x one recorded lap",
    primary_key=("race_id", "driver_id", "lap_number"),
    foreign_keys=(("race_id", "races"), ("driver_id", "drivers")),
    source_of_truth="fastf1-livetiming",
    columns=(
        Column("race_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "derived", ""),
        Column("driver_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "fastf1-livetiming", ""),
        Column("lap_number", "int64", "laps", False, Availability.LAP_START,
               "fastf1-livetiming", "known when the lap begins"),
        Column("position", "int64", "position", True, Availability.LAP_END,
               "fastf1-livetiming", "position at lap end"),
        Column("session_time_end_s", "float64", "seconds", True, Availability.LAP_END,
               "fastf1-livetiming", "session time at lap end (Time)"),
        Column("lap_start_s", "float64", "seconds", True, Availability.LAP_START,
               "fastf1-livetiming", "session time at lap start (LapStartTime)"),
        Column("lap_time_s", "float64", "seconds", True, Availability.LAP_END,
               "fastf1-livetiming", "recorded lap duration"),
        Column("sector_1_s", "float64", "seconds", True, Availability.LAP_END,
               "fastf1-livetiming", ""),
        Column("sector_2_s", "float64", "seconds", True, Availability.LAP_END,
               "fastf1-livetiming", ""),
        Column("sector_3_s", "float64", "seconds", True, Availability.LAP_END,
               "fastf1-livetiming", ""),
        Column("sector_1_end_s", "float64", "seconds", True, Availability.IN_LAP,
               "fastf1-livetiming", "sub-lap alignment (Sector1SessionTime)"),
        Column("sector_2_end_s", "float64", "seconds", True, Availability.IN_LAP,
               "fastf1-livetiming", ""),
        Column("sector_3_end_s", "float64", "seconds", True, Availability.IN_LAP,
               "fastf1-livetiming", ""),
        Column("speed_i1_kmh", "float64", "km/h", True, Availability.LAP_END,
               "fastf1-livetiming", "trap coverage varies by circuit (D1)"),
        Column("speed_i2_kmh", "float64", "km/h", True, Availability.LAP_END,
               "fastf1-livetiming", ""),
        Column("speed_fl_kmh", "float64", "km/h", True, Availability.LAP_END,
               "fastf1-livetiming", ""),
        Column("speed_st_kmh", "float64", "km/h", True, Availability.LAP_END,
               "fastf1-livetiming", ""),
        Column("compound", "string", "n/a", True, Availability.IN_LAP,
               "fastf1-livetiming", f"closed set {COMPOUNDS}; null stays null"),
        Column("tyre_life", "int64", "laps", True, Availability.IN_LAP,
               "fastf1-livetiming", "includes laps in other sessions (source quirk)"),
        Column("stint_number", "int64", "none", True, Availability.IN_LAP,
               "fastf1-livetiming", ""),
        Column("fresh_tyre", "bool", "none", True, Availability.IN_LAP,
               "fastf1-livetiming", ""),
        Column("pit_in_s", "float64", "seconds", True, Availability.IN_LAP,
               "fastf1-livetiming", "null = no pit entry on this lap"),
        Column("pit_out_s", "float64", "seconds", True, Availability.IN_LAP,
               "fastf1-livetiming", "null = no pit exit on this lap"),
        Column("track_status", "string", "n/a", True, Availability.IN_LAP,
               "fastf1-livetiming", "source status-code string, verbatim"),
        Column("deleted", "bool", "none", True, Availability.POST_RACE,
               "fastf1-livetiming", "stewards deletion; conservative POST_RACE"),
        Column("deleted_reason", "string", "n/a", True, Availability.POST_RACE,
               "fastf1-livetiming", ""),
        Column("is_accurate", "bool", "none", True, Availability.POST_RACE,
               "fastf1-livetiming", "FastF1 accuracy check; flag, not filter"),
        Column("fastf1_generated", "bool", "none", True, Availability.SOURCE_METADATA,
               "fastf1-livetiming", "synthetic/interpolated lap marker"),
    ),
    notes=("No LABEL_ONLY columns by construction (tested). Missingness is "
           "preserved: no field is forced non-null for rectangularity."),
)

PIT_STOPS = TableContract(
    entity="pit_stops",
    grain="one completed pit stop (event log, not a state snapshot)",
    primary_key=("race_id", "driver_id", "stop_sequence"),
    foreign_keys=(("race_id", "driver_id"), "driver_laps"),
    source_of_truth="fastf1-livetiming",
    columns=(
        Column("race_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "derived", ""),
        Column("driver_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "fastf1-livetiming", ""),
        Column("stop_sequence", "int64", "none", False, Availability.IN_LAP,
               "derived", "1-based per driver per race"),
        Column("lap_number", "int64", "laps", True, Availability.IN_LAP,
               "fastf1-livetiming", "lap on which pit entry occurred"),
        Column("pit_in_s", "float64", "seconds", True, Availability.IN_LAP,
               "fastf1-livetiming", ""),
        Column("pit_out_s", "float64", "seconds", True, Availability.IN_LAP,
               "fastf1-livetiming", ""),
        Column("duration_s", "float64", "seconds", True, Availability.IN_LAP,
               "derived", "pit_out_s - pit_in_s where both present"),
    ),
    notes="Jolpica pitstops endpoint is cross-check only, never the source.",
)

STINTS = TableContract(
    entity="stints",
    grain="one tyre stint per driver per race",
    primary_key=("race_id", "driver_id", "stint_number"),
    foreign_keys=(("race_id", "driver_id"), "driver_laps"),
    source_of_truth="fastf1-livetiming",
    columns=(
        Column("race_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "derived", ""),
        Column("driver_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "fastf1-livetiming", ""),
        Column("stint_number", "int64", "none", False, Availability.IN_LAP,
               "fastf1-livetiming", ""),
        Column("compound", "string", "n/a", True, Availability.IN_LAP,
               "fastf1-livetiming", f"closed set {COMPOUNDS}"),
        Column("fresh_tyre", "bool", "none", True, Availability.IN_LAP,
               "fastf1-livetiming", ""),
        Column("start_lap", "int64", "laps", True, Availability.IN_LAP,
               "fastf1-livetiming", ""),
        Column("end_lap", "int64", "laps", True, Availability.IN_LAP,
               "fastf1-livetiming", "null if stint open at data end (DNF)"),
        Column("tyre_age_at_start", "int64", "laps", True, Availability.IN_LAP,
               "fastf1-livetiming", "source TyreLife semantics (incl. other sessions)"),
        Column("pit_in_lap", "int64", "laps", True, Availability.IN_LAP,
               "fastf1-livetiming", "null for opening stint"),
        Column("pit_out_lap", "int64", "laps", True, Availability.IN_LAP,
               "fastf1-livetiming", "null for final stint"),
    ),
    notes="Stints are derived groupings of observed laps, never hand-edited.",
)

WEATHER = TableContract(
    entity="weather",
    grain="one source weather observation per race session",
    primary_key=("race_id", "observed_at_s"),
    foreign_keys=(("race_id", "races"),),
    source_of_truth="fastf1-weather",
    columns=(
        Column("race_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "derived", ""),
        Column("observed_at_s", "float64", "seconds", False, Availability.SOURCE_METADATA,
               "fastf1-weather", "session-relative source time"),
        Column("air_temp_c", "float64", "°C", True, Availability.IN_LAP,
               "fastf1-weather", ""),
        Column("track_temp_c", "float64", "°C", True, Availability.IN_LAP,
               "fastf1-weather", ""),
        Column("humidity_pct", "float64", "%", True, Availability.IN_LAP,
               "fastf1-weather", ""),
        Column("pressure_hpa", "float64", "hPa", True, Availability.IN_LAP,
               "fastf1-weather", "hPa scale verified D1 (~1016-1017)"),
        Column("wind_speed", "float64", "m/s", True, Availability.IN_LAP,
               "fastf1-weather", "unit: m/s per fastf1 _api.weather_data docstring"),
        Column("wind_direction_deg", "float64", "degrees", True, Availability.IN_LAP,
               "fastf1-weather", ""),
        Column("rainfall", "bool", "none", True, Availability.IN_LAP,
               "fastf1-weather", "source bool encoding preserved"),
    ),
    notes=("Temporal join contract: observation may populate state(t) iff "
           "observed_at_s <= t. Empty left side -> null, never a future row."),
)

RACE_CONTROL = TableContract(
    entity="race_control",
    grain="one source race-control message (raw fact, no interpretation)",
    primary_key=("race_id", "message_seq"),
    foreign_keys=(("race_id", "races"),),
    source_of_truth="fastf1-race-control",
    columns=(
        Column("race_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "derived", ""),
        Column("message_seq", "int64", "none", False, Availability.SOURCE_METADATA,
               "derived", "source order, 0-based, deterministic"),
        Column("observed_at_s", "float64", "seconds", True, Availability.SOURCE_METADATA,
               "fastf1-race-control", "from absolute Time; null only if source lacks it"),
        Column("lap_number", "int64", "laps", True, Availability.SOURCE_METADATA,
               "fastf1-race-control", "source Lap column, verbatim"),
        Column("category", "string", "n/a", True, Availability.IN_LAP,
               "fastf1-race-control", "Flag | Other | SafetyCar | Drs | CarEvent | ..."),
        Column("flag", "string", "n/a", True, Availability.IN_LAP,
               "fastf1-race-control", "verbatim, sparse"),
        Column("status", "string", "n/a", True, Availability.IN_LAP,
               "fastf1-race-control", "verbatim, sparse"),
        Column("scope", "string", "n/a", True, Availability.IN_LAP,
               "fastf1-race-control", "verbatim, sparse"),
        Column("sector", "string", "n/a", True, Availability.IN_LAP,
               "fastf1-race-control", "verbatim, sparse"),
        Column("racing_number", "int64", "none", True, Availability.IN_LAP,
               "fastf1-race-control", "verbatim, sparse"),
        Column("message_text", "string", "n/a", True, Availability.IN_LAP,
               "fastf1-race-control", "raw message where storage policy permits"),
    ),
    notes=("Raw message and derived interpretation stay distinguishable: "
           "SC/VSC derivation is a future deterministic transform with tests, "
           "not a column here. Consumption rule: message visible at t iff "
           "observed_at_s <= t."),
)

TELEMETRY_SUMMARY = TableContract(
    entity="telemetry_summary",
    grain="one summary row per driver per lap (references driver_laps)",
    primary_key=("race_id", "driver_id", "lap_number"),
    foreign_keys=((("race_id", "driver_id", "lap_number"), "driver_laps"),),
    source_of_truth="fastf1-telemetry",
    partition_keys=("season",),
    columns=(
        Column("race_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "derived", ""),
        Column("driver_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "fastf1-telemetry", ""),
        Column("lap_number", "int64", "laps", False, Availability.LAP_END,
               "fastf1-telemetry", ""),
        Column("telemetry_sample_count", "int64", "samples", True,
               Availability.SOURCE_METADATA, "fastf1-telemetry",
               "provenance-grade count, always recorded when a summary exists"),
    ),
    notes=("OPTIONAL table; retention decided in D8. D8 (2026-09-08) DEFERRED "
           "telemetry from the canonical Phase-1 dataset (see "
           "docs/adr/ADR-0001-telemetry-retention.md): this table is "
           "EXPLICITLY INACTIVE, no canonical telemetry data is produced, "
           "the FastF1 cache remains the source layer, and D9 must not "
           "depend on telemetry. Boundary rules if ever activated: summaries "
           "reference driver_laps by key; construction uses only data with "
           "event time <= lap end (past-only); no summary columns are fixed "
           "here — activation selects from measured candidates only."),
)

# --------------------------------------------------------------------------
# Tier-B contracts (broad 1950+ historical layer; D4 finalises ingestion).
# No rich fields are forced onto historical records.
# --------------------------------------------------------------------------

HIST_SEASONS = TableContract(
    entity="hist_seasons", grain="one row per championship season",
    primary_key=("season",), source_of_truth="jolpica",
    columns=(
        Column("season", "int64", "none", False, Availability.SOURCE_METADATA,
               "jolpica", ""),
    ),
)

HIST_CIRCUITS = TableContract(
    entity="hist_circuits", grain="one row per circuit identity",
    primary_key=("circuit_id",), source_of_truth="jolpica",
    columns=(
        Column("circuit_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "jolpica", "stable slug, e.g. albert_park"),
        Column("circuit_name", "string", "n/a", True, Availability.SOURCE_METADATA,
               "jolpica", "ATTRIBUTE ONLY"),
        Column("locality", "string", "n/a", True, Availability.SOURCE_METADATA,
               "jolpica", ""),
        Column("country", "string", "n/a", True, Availability.SOURCE_METADATA,
               "jolpica", ""),
        Column("latitude", "float64", "degrees", True, Availability.SOURCE_METADATA,
               "jolpica", ""),
        Column("longitude", "float64", "degrees", True, Availability.SOURCE_METADATA,
               "jolpica", ""),
    ),
)

HIST_DRIVERS = TableContract(
    entity="hist_drivers", grain="one row per driver identity",
    primary_key=("driver_id",), source_of_truth="jolpica",
    columns=(
        Column("driver_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "jolpica", "permanent slug, shared with rich layer"),
        Column("driver_code", "string", "n/a", True, Availability.SOURCE_METADATA,
               "jolpica", "ATTRIBUTE ONLY"),
        Column("permanent_number", "int64", "none", True, Availability.SOURCE_METADATA,
               "jolpica", "ATTRIBUTE ONLY"),
        Column("given_name", "string", "n/a", True, Availability.SOURCE_METADATA,
               "jolpica", ""),
        Column("family_name", "string", "n/a", True, Availability.SOURCE_METADATA,
               "jolpica", ""),
        Column("date_of_birth", "string", "n/a", True, Availability.SOURCE_METADATA,
               "jolpica", "ISO date string; null where unavailable"),
        Column("nationality", "string", "n/a", True, Availability.SOURCE_METADATA,
               "jolpica", ""),
    ),
)

HIST_CONSTRUCTORS = TableContract(
    entity="hist_constructors",
    grain="one row per constructor per season (renames are new rows)",
    primary_key=("constructor_id", "season"),
    source_of_truth="jolpica",
    columns=(
        Column("constructor_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "jolpica", "season-scoped slug"),
        Column("season", "int64", "none", False, Availability.SOURCE_METADATA,
               "jolpica", ""),
        Column("constructor_name", "string", "n/a", True, Availability.SOURCE_METADATA,
               "jolpica", "ATTRIBUTE ONLY"),
        Column("nationality", "string", "n/a", True, Availability.SOURCE_METADATA,
               "jolpica", ""),
    ),
    notes="Team lineage mapping (toro_rosso -> alphatauri, ...) is D4's table.",
)

HIST_RACES = TableContract(
    entity="hist_races", grain="one row per historical race",
    primary_key=("season", "round_no"),
    foreign_keys=(("circuit_id", "hist_circuits"),),
    source_of_truth="jolpica",
    columns=(
        Column("season", "int64", "none", False, Availability.SOURCE_METADATA,
               "jolpica", ""),
        Column("round_no", "int64", "none", False, Availability.SOURCE_METADATA,
               "jolpica", ""),
        Column("race_name", "string", "n/a", True, Availability.SOURCE_METADATA,
               "jolpica", "ATTRIBUTE ONLY"),
        Column("circuit_id", "string", "n/a", True, Availability.SOURCE_METADATA,
               "jolpica", ""),
        Column("race_date", "string", "n/a", True, Availability.SOURCE_METADATA,
               "jolpica", "ISO date string"),
    ),
)

HIST_RESULTS = TableContract(
    entity="hist_results", grain="one row per driver per historical race",
    primary_key=("season", "round_no", "driver_id"),
    foreign_keys=(("season", "round_no"), "hist_races"),
    source_of_truth="jolpica",
    columns=(
        Column("season", "int64", "none", False, Availability.SOURCE_METADATA,
               "jolpica", ""),
        Column("round_no", "int64", "none", False, Availability.SOURCE_METADATA,
               "jolpica", ""),
        Column("driver_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "jolpica", ""),
        Column("constructor_id", "string", "n/a", True, Availability.SOURCE_METADATA,
               "jolpica", ""),
        Column("grid", "int64", "position", True, Availability.PRE_RACE,
               "jolpica", "Ergast -1 normalised to null"),
        Column("position", "int64", "position", True, Availability.LABEL_ONLY,
               "jolpica", "Ergast -1 normalised to null"),
        Column("position_text", "string", "n/a", True, Availability.LABEL_ONLY,
               "jolpica", "verbatim (R/D/F/... codes preserved)"),
        Column("points", "float64", "points", True, Availability.LABEL_ONLY,
               "jolpica", ""),
        Column("laps", "int64", "laps", True, Availability.LABEL_ONLY,
               "jolpica", ""),
        Column("status", "string", "n/a", True, Availability.LABEL_ONLY,
               "jolpica", "verbatim; D4 validates post-2024 completeness"),
    ),
    notes="Ergast auto_cast -1 (missing int) MUST become null at normalisation.",
)

HIST_STANDINGS = TableContract(
    entity="hist_standings",
    grain="one row per driver/constructor standing snapshot",
    primary_key=("season", "round_no", "standing_type", "entrant_id"),
    source_of_truth="jolpica",
    columns=(
        Column("season", "int64", "none", False, Availability.SOURCE_METADATA,
               "jolpica", ""),
        Column("round_no", "int64", "none", False, Availability.SOURCE_METADATA,
               "jolpica", ""),
        Column("standing_type", "string", "n/a", False, Availability.SOURCE_METADATA,
               "derived", "driver | constructor"),
        Column("entrant_id", "string", "n/a", False, Availability.SOURCE_METADATA,
               "jolpica", "driver_id or constructor_id"),
        Column("standing_position", "int64", "position", True, Availability.LABEL_ONLY,
               "jolpica", ""),
        Column("standing_points", "float64", "points", True, Availability.LABEL_ONLY,
               "jolpica", ""),
        Column("wins", "int64", "none", True, Availability.LABEL_ONLY,
               "jolpica", ""),
    ),
    notes="Optional-but-included: 'standings where useful' per plan.",
)

TIER_A_TABLES = (RACES, RESULTS, DRIVER_LAPS, PIT_STOPS, STINTS, WEATHER,
                 RACE_CONTROL, TELEMETRY_SUMMARY)
TIER_B_TABLES = (HIST_SEASONS, HIST_CIRCUITS, HIST_DRIVERS, HIST_CONSTRUCTORS,
                 HIST_RACES, HIST_RESULTS, HIST_STANDINGS)
ALL_TABLES = TIER_A_TABLES + TIER_B_TABLES


def get_table(entity: str) -> TableContract:
    for t in ALL_TABLES:
        if t.entity == entity:
            return t
    raise KeyError(f"unknown V2 entity: {entity}")


# --------------------------------------------------------------------------
# Validation severity vocabulary for D3/D11 implementation (design only).
# --------------------------------------------------------------------------

class Severity(str, Enum):
    ERROR = "ERROR"            # reject/quarantine the write unit
    WARNING = "WARNING"        # record in quality report, keep data
    SOURCE_ANOMALY = "SOURCE-ANOMALY"  # legitimate unusual race; flag, keep
