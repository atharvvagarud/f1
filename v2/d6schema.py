"""D6 canonical driver-lap dataset schema (D6 — Canonical Driver-Lap Dataset).

Machine-readable, stdlib-only (dataclasses + enum). Defines the two D6
canonical outputs and every column with: name, dtype (parquet logical type),
unit, nullability, temporal availability (leakage contract, reuse of the D2
``contracts.Availability`` vocabulary), owner, upstream ``source`` token,
predictive-state eligibility and a description.

Entities:

- ``driver_lap_state``  — one canonical state row per (driver x race x lap).
  This is the dataset later phases consume. It carries ZERO LABEL_ONLY
  columns by construction (asserted in tests) and no POST_RACE column is
  predictive-eligible: the final-outcome labels never leave the ``results``
  entity (D7/label stage owns joining them into training/evaluation sets).
- ``race_quality``      — race-grain source-quality / eligibility metadata
  (one row per race). D6 owns source truth + data-quality metadata here; it
  does NOT make universal model-eligibility decisions.

Column-level temporal semantics (D2 ``Availability``):
- identifiers / attributes / provenance-quality metadata are SOURCE_METADATA
  (non-predictive; may identify or qualify, never a feature);
- ``season``/``round_no`` are PRE_RACE;
- ``lap_number``/``lap_start_s`` are LAP_START (knowable when the lap starts);
- sub-lap events (sector ends, tyre fields, pits, track status) are IN_LAP;
- lap-completion facts (position, lap time, sectors, speeds) are LAP_END;
- ``state_time_s`` is the row's canonical availability clock: LAP_END of the
  source lap (the lap's ``Time``). At ``state_time_s`` every predictive-
  eligible field of the row is observable at or before that time.
- ``deleted`` / ``deleted_reason`` / ``is_accurate`` are POST_RACE quality
  flags (conservative, per D2.4): present for provenance, never predictive.

``predictive_eligible`` is the machine-readable Phase-2 gate: a field may be
consumed as candidate predictive state iff True. Keys/attributes, clocks and
quality metadata are all False.
"""

from __future__ import annotations

from dataclasses import dataclass

from v2 import contracts as C

# Independent D6 dataset-schema version (bump rules mirror D2 §17: breaking =
# rename/remove/retype a column, change a key or tighten nullability; additive
# = new nullable column/table). Dataset files stamp this value.
D6_SCHEMA_VERSION = 1

STATE_ENTITY = "driver_lap_state"
QUALITY_ENTITY = "race_quality"
STATE_ENTITY_LAYOUT_ENTITY = "driver_lap_state"

# One D6 canonical build unit = one season (whole-scope dataset is partitioned
# by season; a season is the atomic written unit).
def d6_unit_id(season: int) -> str:
    return f"d6-{int(season)}"


@dataclass(frozen=True)
class Field:
    """One canonical D6 column (machine-readable spec entry)."""

    name: str
    dtype: str            # parquet logical type token: string|int64|float64|bool
    unit: str             # physical unit; "none"/"n/a" for keys/flags/metadata
    nullable: bool
    availability: C.Availability
    owner: str            # canonical owning upstream source
    source: str           # lineage token: upstream entity/field or derived rule
    predictive_eligible: bool
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
            "description": self.description,
        }


# ---------------------------------------------------------------------------
# driver_lap_state: one canonical state row per driver x race x lap.
# Observation/flag columns mirror the D2 DRIVER_LAPS contract (owner, unit,
# availability, nullability identical) so the two cannot drift.
# ---------------------------------------------------------------------------

# column name -> source driver_laps column this state column is copied from.
_SOURCE_MAP: dict[str, str] = {
    "position": "driver_laps:position",
    "lap_start_s": "driver_laps:lap_start_s",
    "lap_time_s": "driver_laps:lap_time_s",
    "sector_1_s": "driver_laps:sector_1_s",
    "sector_2_s": "driver_laps:sector_2_s",
    "sector_3_s": "driver_laps:sector_3_s",
    "sector_1_end_s": "driver_laps:sector_1_end_s",
    "sector_2_end_s": "driver_laps:sector_2_end_s",
    "sector_3_end_s": "driver_laps:sector_3_end_s",
    "speed_i1_kmh": "driver_laps:speed_i1_kmh",
    "speed_i2_kmh": "driver_laps:speed_i2_kmh",
    "speed_fl_kmh": "driver_laps:speed_fl_kmh",
    "speed_st_kmh": "driver_laps:speed_st_kmh",
    "compound": "driver_laps:compound",
    "tyre_life": "driver_laps:tyre_life",
    "stint_number": "driver_laps:stint_number",
    "fresh_tyre": "driver_laps:fresh_tyre",
    "pit_in_s": "driver_laps:pit_in_s",
    "pit_out_s": "driver_laps:pit_out_s",
    "track_status": "driver_laps:track_status",
    "deleted": "driver_laps:deleted",
    "deleted_reason": "driver_laps:deleted_reason",
    "is_accurate": "driver_laps:is_accurate",
    "fastf1_generated": "driver_laps:fastf1_generated",
}


_PREDICTIVE_AVAILABILITY = (C.Availability.LAP_START, C.Availability.IN_LAP,
                            C.Availability.LAP_END)


def _dl_field(dl: dict, name: str) -> Field:
    c = dl[name]
    eligible = c.availability in _PREDICTIVE_AVAILABILITY
    return Field(name, c.dtype, c.unit, c.nullable, c.availability, c.owner,
                 _SOURCE_MAP[name], eligible, c.description)


# Explicit physical column order (readable canonical layout).
_ORDER = [
    "race_id", "season", "round_no", "event_id", "circuit_id", "driver_id",
    "constructor_id", "lap_number", "driver_number", "driver_abbreviation",
    "state_time_s", "position", "lap_start_s", "lap_time_s", "sector_1_s",
    "sector_2_s", "sector_3_s", "sector_1_end_s", "sector_2_end_s",
    "sector_3_end_s", "speed_i1_kmh", "speed_i2_kmh", "speed_fl_kmh",
    "speed_st_kmh", "compound", "tyre_life", "stint_number", "fresh_tyre",
    "pit_in_s", "pit_out_s", "track_status", "deleted", "deleted_reason",
    "is_accurate", "fastf1_generated",
]


def _build_state_fields() -> tuple[Field, ...]:
    dl = {c.name: c for c in C.DRIVER_LAPS.columns}

    explicit = {
        "race_id": Field("race_id", "string", "n/a", False,
                         C.Availability.SOURCE_METADATA, "derived",
                         "race_id (make_race_id)", False,
                         "canonical race identity = race-session id"),
        "season": Field("season", "int64", "none", False,
                        C.Availability.PRE_RACE, "fastf1-schedule",
                        "season", False, "championship year"),
        "round_no": Field("round_no", "int64", "none", False,
                          C.Availability.PRE_RACE, "fastf1-schedule",
                          "round_no", False,
                          "championship round; stable post-season"),
        "event_id": Field("event_id", "string", "n/a", False,
                          C.Availability.SOURCE_METADATA, "derived",
                          "event_id (make_event_id)", False,
                          "championship event identity"),
        "circuit_id": Field("circuit_id", "string", "n/a", False,
                            C.Availability.SOURCE_METADATA,
                            "jolpica-cross-check", "circuit_id", False,
                            "Ergast-vocabulary circuit slug (D4 cross-check)"),
        "driver_id": Field("driver_id", "string", "n/a", False,
                           C.Availability.SOURCE_METADATA,
                           "fastf1-livetiming", "driver_laps:driver_id",
                           False,
                           "permanent Ergast slug (identity, never number)"),
        "constructor_id": Field("constructor_id", "string", "n/a", True,
                                C.Availability.SOURCE_METADATA,
                                "fastf1-results", "results:team_id_at_race",
                                False,
                                "constructor slug valid for this race/season "
                                "(season-scoped identity)"),
        "lap_number": Field("lap_number", "int64", "laps", False,
                            C.Availability.LAP_START, "fastf1-livetiming",
                            "driver_laps:lap_number", False,
                            "known when the lap begins"),
        "driver_number": Field("driver_number", "int64", "none", True,
                               C.Availability.SOURCE_METADATA,
                               "fastf1-results", "results:driver_number",
                               False, "ATTRIBUTE ONLY: mutable, never a key"),
        "driver_abbreviation": Field(
            "driver_abbreviation", "string", "n/a", True,
            C.Availability.SOURCE_METADATA, "fastf1-results",
            "results:driver_abbreviation", False,
            "ATTRIBUTE ONLY (3-letter code)"),
        "state_time_s": Field(
            "state_time_s", "float64", "seconds", True,
            C.Availability.LAP_END, "fastf1-livetiming",
            "driver_laps:session_time_end_s (Time)", False,
            "CANONICAL state clock: session-relative time at the END of this "
            "lap. The row is available at state_time_s; every "
            "predictive-eligible field is observable at or before state_time_s."),
    }

    fields = []
    for name in _ORDER:
        if name in explicit:
            fields.append(explicit[name])
        elif name in dl:
            # Observation + POST_RACE/SOURCE_METADATA lap-quality flags.
            fields.append(_dl_field(dl, name))
        else:
            raise AssertionError(f"state order names unknown column: {name}")

    # Race-level source-quality metadata (denormalised per row for easy task
    # filtering; verbose notes live in race_quality, never here).
    fields.append(Field(
        "source_unit_status", "string", "n/a", False,
        C.Availability.SOURCE_METADATA, "manifest",
        "tiera-<season>.json entry.status", False,
        "verbatim D5 ingestion status: complete | partial"))
    fields.append(Field(
        "shortened_race", "bool", "none", False,
        C.Availability.SOURCE_METADATA, "derived-dataset",
        "observed_leader_laps < total_laps_scheduled", False,
        "data-derived: leader completed fewer laps than scheduled "
        "(time-limit/red-flag); independent of source_unit_status"))
    return tuple(fields)


STATE_FIELDS: tuple[Field, ...] = _build_state_fields()
STATE_COLUMNS: list[str] = [f.name for f in STATE_FIELDS]

# Extra columns the race-grain quality table carries beyond the shared keys.
QUALITY_FIELDS: tuple[Field, ...] = tuple([
    Field("race_id", "string", "n/a", False, C.Availability.SOURCE_METADATA,
          "derived", "race_id (make_race_id)", False, "canonical race identity"),
    Field("season", "int64", "none", False, C.Availability.PRE_RACE,
          "fastf1-schedule", "season", False, "championship year"),
    Field("round_no", "int64", "none", False, C.Availability.PRE_RACE,
          "fastf1-schedule", "round_no", False, "championship round"),
    Field("event_id", "string", "n/a", False, C.Availability.SOURCE_METADATA,
          "derived", "event_id (make_event_id)", False, "event identity"),
    Field("circuit_id", "string", "n/a", False, C.Availability.SOURCE_METADATA,
          "jolpica-cross-check", "circuit_id", False, "circuit slug"),
    Field("event_name", "string", "n/a", True,
          C.Availability.SOURCE_METADATA, "fastf1-schedule",
          "races:event_name", False, "ATTRIBUTE ONLY: display name"),
    Field("source_unit_status", "string", "n/a", False,
          C.Availability.SOURCE_METADATA, "manifest",
          "tiera-<season>.json entry.status", False,
          "verbatim D5 ingestion status: complete | partial"),
    Field("shortened_race", "bool", "none", False,
          C.Availability.SOURCE_METADATA, "derived-dataset",
          "observed_leader_laps < total_laps_scheduled", False,
          "leader completed fewer laps than scheduled"),
    Field("total_laps_scheduled", "int64", "laps", True,
          C.Availability.PRE_RACE, "fastf1-livetiming",
          "races:total_laps_scheduled", False, "scheduled race distance"),
    Field("observed_leader_laps", "int64", "laps", True,
          C.Availability.SOURCE_METADATA, "derived-dataset",
          "max(lap_number) over the race's driver_laps rows", False,
          "leader's completed-lap count observed in the canonical data"),
    Field("partial_reason", "string", "n/a", True,
          C.Availability.SOURCE_METADATA, "manifest",
          "tiera-<season>.json entry.error_message", False,
          "verbatim material-incompleteness reason (PARTIAL units only)"),
    Field("quality_note", "string", "n/a", True,
          C.Availability.SOURCE_METADATA, "manifest",
          "tiera-<season>.json entry.quality_note", False,
          "verbatim D5 source/domain anomaly notes (quality provenance)"),
])
QUALITY_COLUMNS: list[str] = [f.name for f in QUALITY_FIELDS]


def state_field(name: str) -> Field:
    for f in STATE_FIELDS:
        if f.name == name:
            return f
    raise KeyError(f"unknown driver_lap_state field: {name}")


def state_primary_key() -> tuple[str, ...]:
    return ("race_id", "driver_id", "lap_number")


def quality_primary_key() -> tuple[str, ...]:
    return ("race_id",)


def _assert_no_labels() -> None:
    """The canonical state table carries ZERO LABEL_ONLY columns (also
    asserted against written parquet in tests)."""
    bad = [f.name for f in STATE_FIELDS
           if f.availability is C.Availability.LABEL_ONLY]
    assert not bad, f"LABEL_ONLY leakage in driver_lap_state: {bad}"


_assert_no_labels()

# dtypes for deterministic cast when writing canonical parquet (pandas
# canonical representation; nullable ints use pandas Int64 extension so the
# parquet logical type is uniformly int64 regardless of season missingness).
def state_cast_dtypes() -> dict:
    """pandas dtype cast map keyed by canonical column name."""
    cast = {}
    for f in STATE_FIELDS:
        if f.dtype == "int64":
            cast[f.name] = "Int64"
        elif f.dtype == "float64":
            cast[f.name] = "float64"
        elif f.dtype == "bool":
            cast[f.name] = "bool"
        elif f.dtype == "string":
            cast[f.name] = "object"
        else:  # pragma: no cover - defensive
            raise AssertionError(f"unknown dtype {f.dtype} for {f.name}")
    return cast


def quality_cast_dtypes() -> dict:
    cast = {}
    for f in QUALITY_FIELDS:
        if f.dtype == "int64":
            cast[f.name] = "Int64"
        elif f.dtype == "string":
            cast[f.name] = "object"
        elif f.dtype == "bool":
            cast[f.name] = "bool"
    return cast


def schema_json() -> dict:
    """Whole machine-readable D6 schema (both tables) as JSON-able dicts."""
    return {
        "dataset": "f1-intelligence-v2-driver-lap-state",
        "phase_1_deliverable": "D6 canonical driver-lap dataset",
        "d6_schema_version": D6_SCHEMA_VERSION,
        "canonical_contracts_version": C.SCHEMA_VERSION,
        "grain": "one canonical state row per driver x race x lap",
        "state_primary_key": list(state_primary_key()),
        "state_time_semantics": (
            "state_time_s = source lap-end session time (driver_laps "
            "session_time_end_s). Row available at state_time_s; all "
            "predictive_eligible fields observable at or before state_time_s."),
        "label_separation": (
            "driver_lap_state carries ZERO LABEL_ONLY columns. Final "
            "outcomes remain in the results entity (joined into training/"
            "evaluation sets only by explicit later construction)."),
        "tables": {
            STATE_ENTITY: {
                "partition_keys": ["season"],
                "primary_key": list(state_primary_key()),
                "columns": [f.to_dict() for f in STATE_FIELDS],
            },
            QUALITY_ENTITY: {
                "partition_keys": ["season"],
                "primary_key": list(quality_primary_key()),
                "columns": [f.to_dict() for f in QUALITY_FIELDS],
            },
        },
    }
