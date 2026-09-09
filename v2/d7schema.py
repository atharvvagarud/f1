"""D7 temporally-enriched driver-lap state schema (D7 — Supporting Race Data).

Machine-readable, stdlib-only (dataclasses + enum). Defines the D7 canonical
output table ``driver_lap_state_d7``: every D6 ``driver_lap_state`` column
(verbatim, unchanged order) followed by the D7 temporal-context extension
columns. Each D7 column carries: name, dtype (parquet logical type), unit,
nullability, temporal availability (reuse of the D2 ``contracts.Availability``
vocabulary), owner, upstream ``source`` lineage token, predictive-eligibility,
a ``lineage_kind`` classification and a description.

Lineage kinds (D7 distinguishes these; D7 contains the first two ONLY):

- ``source_observation``        — a value copied from a source observation /
  canonical supporting entity that is legitimate at (at-or-before) the state
  clock: as-of weather sample values, the latest issued race-control message's
  raw attributes, pit entry/exit event times/laps, current-stint start-side
  facts. NOT an engineered feature.
- ``derived_temporal_lineage``  — the audit anchors of a temporal as-of join:
  which observation/message was selected, its observed time and its staleness.
- ``model_feature``             — reserved. D7 NEVER writes model features;
  D9 owns features with definitions + leakage tests.

Temporal rules encoded here (see ``v2/d7.py`` + docs/DATA_PLATFORM_ARCHITECTURE
§D7): every attachment satisfies ``source_observed_time <= state_time_s``.
Weather is a strict backward as-of (latest observation at/before the state
clock; empty left side -> null). Race control attaches ONLY the latest
timestamped message at/before the clock; untimestamped messages (2018-r02)
never attach and are never invented into history. Pit context exposes only pit
events whose entry/exit session time is at/before the clock (asymmetric
in-only / out-only source boundaries preserved; no missing half manufactured;
no counts / next-pit / eventual-stop exposure). Stint context exposes ONLY the
start side of the CURRENT stint (start lap, fitted compound, fresh flag,
tyre age at start) matched by the row's own stint number — the stint's eventual
END is future information at earlier in-stint states and is NEVER attached.

``state_time_s`` (the D6 lap-end clock) remains authoritative and unchanged.
D7 preserves the D6 canonical grain exactly: one row per (race_id, driver_id,
lap_number); the enrichment is many-to-one / as-of only.
"""

from __future__ import annotations

from dataclasses import dataclass

from v2 import contracts as C
from v2 import d6schema as D6

# Independent D7 dataset-schema version (bump rules mirror D2 §17: breaking =
# rename/remove/retype a column, change a key or tighten nullability; additive
# = new nullable column/table). Dataset files stamp this value.
D7_SCHEMA_VERSION = 1

# D7 canonical enriched-state entity + unit id (one unit = one season, exactly
# like D6). D6 outputs are never modified; D7 is a separate artifact.
STATE_ENTITY = "driver_lap_state_d7"


def d7_unit_id(season: int) -> str:
    return f"d7-{int(season)}"


# Lineage-kind vocabulary (see module docstring).
SOURCE_OBSERVATION = "source_observation"
DERIVED_LINEAGE = "derived_temporal_lineage"
MODEL_FEATURE = "model_feature"


@dataclass(frozen=True)
class ExtensionField:
    """One canonical D7 extension column (machine-readable spec entry)."""

    name: str
    dtype: str            # parquet logical type token: string|int64|float64|bool
    unit: str             # physical unit; "none"/"n/a" for keys/flags/metadata
    nullable: bool
    availability: C.Availability
    owner: str            # canonical owning upstream source
    source: str           # lineage token: upstream entity/field or derived rule
    predictive_eligible: bool
    lineage_kind: str     # source_observation | derived_temporal_lineage
    description: str = ""

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "dtype": self.dtype,
            "unit": self.unit,
            "nullable": self.nullable,
            "availability": self.availability.value,
            "owner": self.owner,
            "source": self.source,
            "predictive_eligible": self.predictive_eligible,
            "lineage_kind": self.lineage_kind,
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# WEATHER as-of block (source entity: D5 weather; strict backward join).
# wx_* value fields are source_observation state samples -> predictive-
# eligible (candidate state, like any D6 IN_LAP observation). The observed
# time and the staleness are derived_temporal_lineage audit anchors.
# ---------------------------------------------------------------------------

_WEATHER_FIELDS: tuple[ExtensionField, ...] = (
    ExtensionField(
        "wx_observed_at_s", "float64", "seconds", True,
        C.Availability.SOURCE_METADATA, "fastf1-weather",
        "weather:observed_at_s (latest <= state_time_s)", False,
        DERIVED_LINEAGE,
        "observed_at_s of the latest weather observation at/before "
        "state_time_s (as-of join anchor; null = no prior observation)"),
    ExtensionField(
        "wx_age_s", "float64", "seconds", True,
        C.Availability.SOURCE_METADATA, "derived-dataset",
        "state_time_s - wx_observed_at_s", False, DERIVED_LINEAGE,
        "weather staleness = state_time_s - wx_observed_at_s (>= 0); "
        "null when no prior observation. Audit, never a feature."),
    ExtensionField(
        "wx_air_temp_c", "float64", "°C", True, C.Availability.IN_LAP,
        "fastf1-weather", "weather:air_temp_c (as-of)", True,
        SOURCE_OBSERVATION, "air temperature of the latest observation "
        "at/before state_time_s"),
    ExtensionField(
        "wx_track_temp_c", "float64", "°C", True, C.Availability.IN_LAP,
        "fastf1-weather", "weather:track_temp_c (as-of)", True,
        SOURCE_OBSERVATION, "track temperature of the latest observation "
        "at/before state_time_s"),
    ExtensionField(
        "wx_humidity_pct", "float64", "%", True, C.Availability.IN_LAP,
        "fastf1-weather", "weather:humidity_pct (as-of)", True,
        SOURCE_OBSERVATION, "humidity of the latest observation at/before "
        "state_time_s"),
    ExtensionField(
        "wx_pressure_hpa", "float64", "hPa", True, C.Availability.IN_LAP,
        "fastf1-weather", "weather:pressure_hpa (as-of)", True,
        SOURCE_OBSERVATION, "atmospheric pressure of the latest observation "
        "at/before state_time_s"),
    ExtensionField(
        "wx_wind_speed", "float64", "m/s", True, C.Availability.IN_LAP,
        "fastf1-weather", "weather:wind_speed (as-of)", True,
        SOURCE_OBSERVATION, "wind speed (m/s, D5-resolved unit) of the "
        "latest observation at/before state_time_s"),
    ExtensionField(
        "wx_wind_direction_deg", "float64", "degrees", True,
        C.Availability.IN_LAP, "fastf1-weather",
        "weather:wind_direction_deg (as-of)", True, SOURCE_OBSERVATION,
        "wind direction of the latest observation at/before state_time_s"),
    ExtensionField(
        "wx_rainfall", "bool", "none", True, C.Availability.IN_LAP,
        "fastf1-weather", "weather:rainfall (as-of)", True,
        SOURCE_OBSERVATION, "rainfall source-bool of the latest observation "
        "at/before state_time_s"),
)


# ---------------------------------------------------------------------------
# RACE-CONTROL block (source entity: D5 race_control). ONLY the latest
# timestamped message at/before state_time_s attaches. Untimestamped messages
# (observed_at_s null, e.g. 69 in 2018-r02) never attach. NO counts, NO
# active-state interpretation (SC intensity, yellow severity, ...): converting
# raw messages to state features is D9. Latest-message raw attributes are
# attached as source context/lineage and are predictive_eligible=False.
# ---------------------------------------------------------------------------

_RACE_CONTROL_FIELDS: tuple[ExtensionField, ...] = (
    ExtensionField(
        "rc_last_message_seq", "int64", "none", True,
        C.Availability.SOURCE_METADATA, "fastf1-race-control",
        "race_control:message_seq (latest timed message <= state_time_s)",
        False, DERIVED_LINEAGE,
        "message_seq of the latest timestamped race-control message "
        "at/before state_time_s (lineage anchor; null = none yet)"),
    ExtensionField(
        "rc_last_message_observed_at_s", "float64", "seconds", True,
        C.Availability.SOURCE_METADATA, "fastf1-race-control",
        "race_control:observed_at_s (latest timed message)", False,
        DERIVED_LINEAGE,
        "observed_at_s of the latest timestamped message at/before "
        "state_time_s"),
    ExtensionField(
        "rc_last_message_age_s", "float64", "seconds", True,
        C.Availability.SOURCE_METADATA, "derived-dataset",
        "state_time_s - rc_last_message_observed_at_s", False,
        DERIVED_LINEAGE,
        "race-control message staleness (>= 0); null when none yet. Audit."),
    ExtensionField(
        "rc_last_message_lap_number", "int64", "laps", True,
        C.Availability.SOURCE_METADATA, "fastf1-race-control",
        "race_control:lap_number (verbatim source Lap)", False,
        DERIVED_LINEAGE,
        "verbatim source Lap column of the latest timestamped message"),
    ExtensionField(
        "rc_last_message_category", "string", "n/a", True,
        C.Availability.IN_LAP, "fastf1-race-control",
        "race_control:category (verbatim)", False, SOURCE_OBSERVATION,
        "raw category (Flag|Other|SafetyCar|Drs|CarEvent|...) of the latest "
        "timestamped message. ATTRIBUTE of a past message, NOT an "
        "interpretation of current track state."),
    ExtensionField(
        "rc_last_message_flag", "string", "n/a", True,
        C.Availability.IN_LAP, "fastf1-race-control",
        "race_control:flag (verbatim)", False, SOURCE_OBSERVATION,
        "raw flag string of the latest timestamped message (sparse; verbatim)."),
    ExtensionField(
        "rc_last_message_text", "string", "n/a", True,
        C.Availability.IN_LAP, "fastf1-race-control",
        "race_control:message_text (verbatim)", False, SOURCE_OBSERVATION,
        "raw message text of the latest timestamped message (lineage/audit)."),
)


# ---------------------------------------------------------------------------
# PIT block (source entity: D5 pit_stops). Only pit events whose entry/exit
# session time is at/before state_time_s attach. Asymmetric boundaries
# (pit_in-only 246 / pit_out-only 159 whole scope) are preserved: the missing
# side is never manufactured and simply yields null for that side. Future pit
# events cannot affect earlier state. No counts / no next-pit / no eventual
# stops: pit-stop-count & laps-since features are D9.
# ---------------------------------------------------------------------------

_PIT_FIELDS: tuple[ExtensionField, ...] = (
    ExtensionField(
        "pit_last_in_lap", "int64", "laps", True, C.Availability.IN_LAP,
        "fastf1-livetiming", "pit_stops entry lap (latest pit_in_s "
        "<= state_time_s)", False, SOURCE_OBSERVATION,
        "lap of the most recent pit ENTRY observable at/before state_time_s; "
        "null when the driver has no observable pit entry yet"),
    ExtensionField(
        "pit_last_in_s", "float64", "seconds", True, C.Availability.IN_LAP,
        "fastf1-livetiming", "pit_stops:pit_in_s (latest <= state_time_s)",
        False, SOURCE_OBSERVATION,
        "session time of the most recent pit ENTRY observable at/before "
        "state_time_s"),
    ExtensionField(
        "pit_last_out_lap", "int64", "laps", True, C.Availability.IN_LAP,
        "fastf1-livetiming", "exit-event lap (latest pit_out_s "
        "<= state_time_s)", False, SOURCE_OBSERVATION,
        "lap on which the most recent pit EXIT occurred, observable "
        "at/before state_time_s (resolved 1:1 from the canonical lap that "
        "carries that pit_out_s); null when none observable yet"),
    ExtensionField(
        "pit_last_out_s", "float64", "seconds", True, C.Availability.IN_LAP,
        "fastf1-livetiming", "pit_stops:pit_out_s (latest <= state_time_s)",
        False, SOURCE_OBSERVATION,
        "session time of the most recent pit EXIT observable at/before "
        "state_time_s"),
)


# ---------------------------------------------------------------------------
# STINT block (source entity: D5 stints). Current-stint START-side facts only,
# matched by the state row's own stint_number (start_lap guard enforced: a
# source stint whose start_lap > lap_number can never attach). The stint's
# eventual end_lap / pit_out_lap are FUTURE information at earlier in-stint
# states and are NEVER exposed here (D9 owns end-aware features/labels with
# leakage tests). stint_compound / stint_fresh_tyre describe the current
# fitted state (candidate state); start_lap / tyre_age_at_start are
# boundary-lineage anchors.
# ---------------------------------------------------------------------------

_STINT_FIELDS: tuple[ExtensionField, ...] = (
    ExtensionField(
        "stint_start_lap", "int64", "laps", True, C.Availability.IN_LAP,
        "fastf1-livetiming", "stints:start_lap (current stint, <= lap_number)",
        False, SOURCE_OBSERVATION,
        "start lap of the driver's CURRENT stint (the stint whose number "
        "matches this row's stint_number); null when stint_number is null or "
        "the source stint record is absent"),
    ExtensionField(
        "stint_compound", "string", "n/a", True, C.Availability.IN_LAP,
        "fastf1-livetiming", "stints:compound (current stint)", True,
        SOURCE_OBSERVATION,
        "compound of the current stint (source record; null stays null)"),
    ExtensionField(
        "stint_fresh_tyre", "bool", "none", True, C.Availability.IN_LAP,
        "fastf1-livetiming", "stints:fresh_tyre (current stint)", True,
        SOURCE_OBSERVATION, "fresh-tyre flag of the current stint"),
    ExtensionField(
        "stint_tyre_age_at_start", "int64", "laps", True,
        C.Availability.IN_LAP, "fastf1-livetiming",
        "stints:tyre_age_at_start (current stint)", False,
        SOURCE_OBSERVATION,
        "source TyreLife at the current stint's first lap (source quirk "
        "includes other sessions; null stays null)"),
)

# Full extension column order (weather, race-control, pit, stint).
EXTENSION_FIELDS: tuple[ExtensionField, ...] = (
    _WEATHER_FIELDS + _RACE_CONTROL_FIELDS + _PIT_FIELDS + _STINT_FIELDS
)
EXTENSION_COLUMNS: list[str] = [f.name for f in EXTENSION_FIELDS]

# The D7 enriched table = D6 canonical state columns (verbatim, in order)
# followed by the D7 extension columns.
ENRICHED_COLUMNS: list[str] = list(D6.STATE_COLUMNS) + EXTENSION_COLUMNS


def enriched_primary_key() -> tuple[str, ...]:
    return D6.state_primary_key()


def _extension_field(name: str) -> ExtensionField:
    for f in EXTENSION_FIELDS:
        if f.name == name:
            return f
    raise KeyError(f"unknown driver_lap_state_d7 extension field: {name}")


def extension_field(name: str) -> ExtensionField:
    return _extension_field(name)


# Deterministic pandas dtype casts when writing the enriched parquet. Nullable
# ints use pandas Int64 (parquet logical int64 regardless of season
# missingness); nullable bools use pandas 'boolean' (parquet bool + nulls).
def enriched_cast_dtypes() -> dict:
    cast = {}
    for name in ENRICHED_COLUMNS:
        if name in D6.STATE_COLUMNS:
            d6_cast = D6.state_cast_dtypes()
            cast[name] = d6_cast[name]
            continue
        f = _extension_field(name)
        if f.dtype == "int64":
            cast[name] = "Int64"
        elif f.dtype == "float64":
            cast[name] = "float64"
        elif f.dtype == "bool":
            # D7 context bools are nullable (null = no prior/current context),
            # so the pandas nullable 'boolean' dtype is required (D6 'bool'
            # cannot hold nulls).
            cast[name] = "boolean"
        elif f.dtype == "string":
            cast[name] = "object"
        else:  # pragma: no cover - defensive
            raise AssertionError(f"unknown dtype {f.dtype} for {name}")
    return cast


def schema_json() -> dict:
    """Whole machine-readable D7 schema as JSON-able dicts."""
    return {
        "dataset": "f1-intelligence-v2-driver-lap-state-d7",
        "phase_1_deliverable": "D7 temporally-enriched canonical driver-lap "
                               "state (supporting race data)",
        "d7_schema_version": D7_SCHEMA_VERSION,
        "base_d6_schema_version": D6.D6_SCHEMA_VERSION,
        "canonical_contracts_version": C.SCHEMA_VERSION,
        "grain": ("one canonical state row per driver x race x lap; D6 grain "
                  "preserved exactly (189,420 rows whole scope)"),
        "primary_key": list(enriched_primary_key()),
        "state_time_semantics": (
            "state_time_s is the D6 canonical lap-end clock; UNCHANGED by D7. "
            "Every temporal attachment satisfies source_observed_time <= "
            "state_time_s (weather/race-control/pit by session time; stint "
            "by start_lap <= lap_number). Weather uses strict backward-only "
            "as-of joins. No future information is ever attached."),
        "lineage_kinds": {
            "source_observation": (
                "value copied from a source observation / canonical "
                "supporting entity, legitimate at/at-before the state clock"),
            "derived_temporal_lineage": (
                "audit anchors of a temporal as-of join (selected id, "
                "observed time, staleness)"),
            "model_feature": (
                "reserved. D7 writes NO model features; D9 owns features "
                "with definitions + leakage tests."),
        },
        "predictive_eligibility_policy": (
            "predictive_eligible=True only for source_observation fields that "
            "are current condition / measurement state samples (wx physical "
            "quantities, current-stint compound/fresh flag). Event attributes "
            "(race-control message fields, pit event times/laps, stint "
            "start-boundary lineage) are predictive_eligible=False: converting "
            "events to state features is D9 work with leakage tests."),
        "label_separation": (
            "the enriched table carries ZERO LABEL_ONLY columns (inherited "
            "from D6; asserted). Final outcomes remain only in results."),
        "tables": {
            STATE_ENTITY: {
                "partition_keys": ["season"],
                "primary_key": list(enriched_primary_key()),
                "base_columns": list(D6.STATE_COLUMNS),
                "extension_columns": [
                    f.to_dict() for f in EXTENSION_FIELDS
                ],
                "column_count": len(ENRICHED_COLUMNS),
            },
        },
    }
