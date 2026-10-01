"""D9 derived temporal state + outcome-label schemas (D9 — Derived Features & Labels).

Machine-readable, stdlib-only. Defines the two D9 canonical outputs:

- ``driver_lap_state_d9`` — the D7 temporally-enriched canonical driver-lap
  state (all D7 columns verbatim) PLUS the D9 derived temporal-state columns.
  Grain is unchanged: one row per (driver x race x lap) == D6/D7 == 189,420
  whole scope. Every derived field is deterministic and computable from
  information observable at or before ``state_time_s`` (the D6 lap-end clock;
  NEVER reinterpreted). ZERO LABEL_ONLY / POST_RACE outcome columns live here.
- ``race_driver_labels`` — the physically separate outcome-label layer, one
  row per (race x driver) == the official 2018–2025 result population
  (3,458 whole scope). All outcome fields are LABEL_ONLY / POST_RACE and
  ``predictive_eligible=False``. State and labels NEVER share a canonical
  table; a training dataset later joins them explicitly.

Lineage kinds (D9 vocabulary):
- ``identity``       — canonical keys / provenance attributes (non-predictive);
- ``derived_state``  — deterministic transformation of source facts observable
  at or before the state clock (candidate predictive state material, with a
  definition + leakage test);
- ``outcome_fact``   — verbatim factual outcome copied from official results;
- ``outcome_derived_fact`` — deterministic flag derived from official result
  facts (winner/podium/classified/points-finisher) — factual, never a task
  target;
- ``model_feature``  — reserved (Phase 2). D9 writes none.

DNF decision (D9): the binary modelling target is DEFERRED. ``classified_flag``
(official classification) is preserved as a fact; ``dnf_flag`` in the D5
``results`` entity remains provisional classification evidence (unclassified),
NOT a reliability target. Phase 2/3 must define any task-specific DNF policy.

Race-control state reconstruction decision (D9): NO message-text state machine
is built. FastF1 3.7.0 already broadcasts an authoritative per-lap
``TrackStatus`` code channel (documented in ``fastf1.api.track_status_data``:
'1' Track clear, '2' Yellow, '3' never seen, '4' Safety Car, '5' Red Flag,
'6' VSC deployed, '7' VSC ending), carried verbatim into D6/D7 as
``track_status`` (IN_LAP availability). D9 converts the code in effect at the
lap boundary (the LAST code character of the per-lap string, which FastF1
appends in chronological order as status changes overlap the lap) into
deterministic contemporaneous flags. This is a deterministic transformation
with tests, avoids guessing ambiguous message semantics (SC/red-flag end
timing, sector-local yellows), and keeps the untimestamped 2018-r02 messages
irrelevant (they are never used to reconstruct state).
"""

from __future__ import annotations

from dataclasses import dataclass

from raceintel import contracts as C
from raceintel.pipeline import d7schema as D7

# Independent D9 dataset-schema version (additive rules mirror D2 §17).
D9_SCHEMA_VERSION = 1

STATE_ENTITY = "driver_lap_state_d9"
LABEL_ENTITY = "race_driver_labels"

# Lineage-kind vocabulary.
IDENTITY = "identity"
DERIVED_STATE = "derived_state"
OUTCOME_FACT = "outcome_fact"
OUTCOME_DERIVED_FACT = "outcome_derived_fact"
MODEL_FEATURE = "model_feature"  # reserved; never written by D9


def d9_unit_id(season: int) -> str:
    return f"d9-{int(season)}"


@dataclass(frozen=True)
class Field:
    """One canonical D9 column (machine-readable spec entry)."""

    name: str
    dtype: str            # string|int64|float64|bool
    unit: str             # "none"/"n/a"/physical unit
    nullable: bool
    availability: C.Availability
    owner: str            # canonical owning upstream source
    source: str           # lineage token: upstream field or derived rule
    predictive_eligible: bool
    lineage_kind: str
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


# Track-status code -> state token (authoritative FastF1 3.7.0 mapping).
# The state at the lap boundary = the LAST code character of the per-lap
# TrackStatus string (codes are appended chronologically as the status
# changes overlap the lap).
TRACK_STATE_CODES = {
    "1": "all_clear",
    "2": "yellow",
    "4": "safety_car",
    "5": "red_flag",
    "6": "vsc",
    "7": "vsc_ending",
}
TRACK_STATE_TOKENS = tuple(sorted(set(TRACK_STATE_CODES.values())))
UNKNOWN_CODE = None  # unknown/empty/null/out-of-set code -> null token

# ---------------------------------------------------------------------------
# D9 derived temporal-state columns (appended after the D7 columns).
# ---------------------------------------------------------------------------

STATE_EXTENSION_FIELDS: tuple[Field, ...] = (
    Field("track_state", "string", "n/a", True, C.Availability.IN_LAP,
          "derived-dataset",
          "driver_lap_state.track_status last code char -> "
          f"state token ({TRACK_STATE_TOKENS})", True, DERIVED_STATE,
          "contemporaneous track state at the lap boundary, derived "
          "deterministically from the source per-lap TrackStatus code channel "
          "(FastF1 3.7.0 mapping: '1' all_clear, '2' yellow, '4' safety_car, "
          "'5' red_flag, '6' vsc, '7' vsc_ending). Null when the source "
          "track_status is null/empty/unknown. No message-text state machine; "
          "no future information."),
    Field("flag_yellow", "bool", "none", True, C.Availability.IN_LAP,
          "derived-dataset", "track_state == 'yellow'", True, DERIVED_STATE,
          "true when track_state is yellow at the lap boundary; false when "
          "another state; null when track_state unknown."),
    Field("flag_safety_car", "bool", "none", True, C.Availability.IN_LAP,
          "derived-dataset", "track_state == 'safety_car'", True,
          DERIVED_STATE, "true when track_state is safety car at the lap "
          "boundary."),
    Field("flag_red", "bool", "none", True, C.Availability.IN_LAP,
          "derived-dataset", "track_state == 'red_flag'", True,
          DERIVED_STATE, "true when track_state is red flag at the lap "
          "boundary."),
    Field("flag_vsc", "bool", "none", True, C.Availability.IN_LAP,
          "derived-dataset", "track_state in ('vsc', 'vsc_ending')", True,
          DERIVED_STATE, "true when a virtual safety car is deployed or "
          "ending at the lap boundary."),
    Field("race_leader_laps_at_state", "int64", "laps", True,
          C.Availability.LAP_END, "derived-dataset",
          "max(lap_number) over all drivers' state rows with state_time_s "
          "<= this row's state_time_s", True, DERIVED_STATE,
          "number of laps the race leader has completed at/ before this "
          "state's clock (the racing-lap index at the lap boundary). "
          "Past-only by construction."),
    Field("race_progress_frac", "float64", "fraction", True,
          C.Availability.LAP_END, "derived-dataset",
          "race_leader_laps_at_state / total_laps_scheduled", True,
          DERIVED_STATE, "fraction of the SCHEDULED race distance completed "
          "by the leader at this state (PRE_RACE scheduled reference; does "
          "NOT assume observed == scheduled). Null when scheduled distance "
          "is unknown."),
    Field("pit_stops_completed_so_far", "int64", "stops", True,
          C.Availability.LAP_END, "derived-dataset",
          "count of source pit_stops rows with pit_in_s AND pit_out_s "
          "present and pit_out_s <= state_time_s", True, DERIVED_STATE,
          "number of FULLY OBSERVED pit stops (entry+exit both present in "
          "source) completed at/ before this state. Asymmetric in-only/"
          "out-only stops are never counted as completed; future stops have "
          "zero effect."),
    Field("laps_since_last_pit_stop", "int64", "laps", True,
          C.Availability.LAP_END, "derived-dataset",
          "lap_number - (exit lap of the latest completed stop with "
          "pit_out_s <= state_time_s)", True, DERIVED_STATE,
          "full laps completed since the latest fully-observed pit stop "
          "(0 on the stop's exit lap). Null when no completed stop is "
          "observable yet."),
    Field("stint_lap", "int64", "laps", True, C.Availability.LAP_END,
          "derived-dataset",
          "lap_number - stint_start_lap + 1 (current stint start side)",
          True, DERIVED_STATE,
          "1-based number of laps completed on the driver's CURRENT stint "
          "(from the D7 current-stint start lap; start side only). Null when "
          "no current-stint start fact exists. Never uses the eventual stint "
          "end."),
)

STATE_EXTENSION_COLUMNS: list[str] = [f.name for f in STATE_EXTENSION_FIELDS]

# The D9 derived-state table = D7 enriched columns verbatim + D9 derived
# columns appended.
STATE_COLUMNS: list[str] = list(D7.ENRICHED_COLUMNS) + STATE_EXTENSION_COLUMNS


def state_primary_key() -> tuple[str, ...]:
    return ("race_id", "driver_id", "lap_number")


# ---------------------------------------------------------------------------
# Outcome-label columns (one row per race x driver; POST_RACE / LABEL_ONLY).
# ---------------------------------------------------------------------------

LABEL_FIELDS: tuple[Field, ...] = (
    Field("race_id", "string", "n/a", False, C.Availability.SOURCE_METADATA,
          "derived", "race_id", False, IDENTITY, "canonical race identity"),
    Field("season", "int64", "none", False, C.Availability.SOURCE_METADATA,
          "fastf1-schedule", "season", False, IDENTITY, "championship year"),
    Field("driver_id", "string", "n/a", False, C.Availability.SOURCE_METADATA,
          "fastf1-results", "driver_id", False, IDENTITY,
          "permanent Ergast slug"),
    Field("driver_abbreviation", "string", "n/a", True,
          C.Availability.SOURCE_METADATA, "fastf1-results",
          "driver_abbreviation", False, IDENTITY, "ATTRIBUTE ONLY"),
    Field("position_final", "int64", "position", True,
          C.Availability.LABEL_ONLY, "fastf1-results", "results:position_final",
          False, OUTCOME_FACT, "official final position (FastF1); null for "
          "DNS/withdrawn rows it does not order"),
    Field("classified_position", "int64", "position", True,
          C.Availability.LABEL_ONLY, "fastf1-results",
          "results:classified_position", False, OUTCOME_FACT,
          "official classified position; null = not classified (R/W/D)"),
    Field("position_text", "string", "n/a", True,
          C.Availability.LABEL_ONLY, "fastf1-results", "results:position_text",
          False, OUTCOME_FACT, "official classification token, verbatim"),
    Field("status_text", "string", "n/a", True,
          C.Availability.LABEL_ONLY, "fastf1-results", "results:status_text",
          False, OUTCOME_FACT, "official result status text, verbatim"),
    Field("points", "float64", "points", True, C.Availability.LABEL_ONLY,
          "fastf1-results", "results:points", False, OUTCOME_FACT,
          "championship points from this race"),
    Field("laps_completed", "int64", "laps", True,
          C.Availability.LABEL_ONLY, "fastf1-results", "results:laps_completed",
          False, OUTCOME_FACT, "official completed-lap count"),
    Field("classified_flag", "bool", "none", False,
          C.Availability.LABEL_ONLY, "derived-dataset",
          "classified_position is not null", False, OUTCOME_DERIVED_FACT,
          "official classification fact (true = classified). NOT a DNF target: "
          "binary reliability policy is deferred (D9 DNF decision)."),
    Field("winner_flag", "bool", "none", True, C.Availability.LABEL_ONLY,
          "derived-dataset", "position_final == 1", False,
          OUTCOME_DERIVED_FACT, "factual winner (official final position 1)"),
    Field("podium_flag", "bool", "none", True, C.Availability.LABEL_ONLY,
          "derived-dataset", "position_final in (1, 2, 3)", False,
          OUTCOME_DERIVED_FACT, "factual podium (official final position "
          "<= 3 under classification semantics)"),
    Field("points_finish_flag", "bool", "none", False,
          C.Availability.LABEL_ONLY, "derived-dataset", "points > 0", False,
          OUTCOME_DERIVED_FACT, "factual points-scoring finish (points > 0, "
          "including half-points shortened races)"),
)
LABEL_COLUMNS: list[str] = [f.name for f in LABEL_FIELDS]


def label_primary_key() -> tuple[str, ...]:
    return ("race_id", "driver_id")


def _state_field(name: str) -> Field:
    for f in STATE_EXTENSION_FIELDS:
        if f.name == name:
            return f
    raise KeyError(f"unknown D9 state field: {name}")


def _assert_state_has_no_outcomes() -> None:
    """The derived STATE table must carry ZERO LABEL_ONLY / POST_RACE
    outcome columns (asserted against written parquet in tests too)."""
    for f in STATE_EXTENSION_FIELDS:
        assert f.availability not in (C.Availability.LABEL_ONLY,
                                      C.Availability.POST_RACE), (
            f"outcome leaked into derived state: {f.name}")
    # D7 already guarantees no LABEL_ONLY columns; assert the cumulative table
    # names none of the results outcome columns.
    result_labels = set(C.RESULTS.label_columns())
    assert not (set(STATE_COLUMNS) & result_labels), (
        f"label columns present in derived state: "
        f"{sorted(set(STATE_COLUMNS) & result_labels)}")


_assert_state_has_no_outcomes()


def _label_cast() -> dict:
    cast = {}
    for f in LABEL_FIELDS:
        if f.dtype == "int64":
            cast[f.name] = "Int64"
        elif f.dtype == "float64":
            cast[f.name] = "float64"
        elif f.dtype == "bool":
            cast[f.name] = "boolean"
        elif f.dtype == "string":
            cast[f.name] = "object"
        else:  # pragma: no cover - defensive
            raise AssertionError(f"unknown dtype {f.dtype} for {f.name}")
    return cast


def state_cast_dtypes() -> dict:
    """Deterministic pandas casts for the cumulative derived-state table."""
    cast = {}
    for name in STATE_COLUMNS:
        if name in D7.ENRICHED_COLUMNS:
            cast[name] = D7.enriched_cast_dtypes()[name]
            continue
        f = _state_field(name)
        if f.dtype == "int64":
            cast[name] = "Int64"
        elif f.dtype == "float64":
            cast[name] = "float64"
        elif f.dtype == "bool":
            cast[name] = "boolean"
        elif f.dtype == "string":
            cast[name] = "object"
        else:  # pragma: no cover - defensive
            raise AssertionError(f"unknown dtype {f.dtype} for {name}")
    return cast


def label_cast_dtypes() -> dict:
    return _label_cast()


def schema_json() -> dict:
    """Whole machine-readable D9 schema (state + labels) as JSON-able dicts."""
    return {
        "dataset": "f1-intelligence-v2-phase1-d9",
        "phase_1_deliverable": ("D9 derived temporal state + outcome labels "
                                "(foundational, deterministic)"),
        "d9_schema_version": D9_SCHEMA_VERSION,
        "base_d7_schema_version": D7.D7_SCHEMA_VERSION,
        "contracts_schema_version": C.SCHEMA_VERSION,
        "lineage": {
            "state": "D5 -> D6 canonical lap state -> D7 enriched state -> "
                     "D9 derived temporal state (one table per stage; D9 "
                     "cumulative)",
            "labels": "D5/D4 official results -> D9 outcome labels "
                      "(separate artifact; never merged into state)",
        },
        "state_time_semantics": (
            "state_time_s = D6 lap-end clock, UNCHANGED. Every D9 derived "
            "field is computed from information observable at or before "
            "state_time_s."),
        "dnf_decision": (
            "binary DNF modelling target DEFERRED. Labels preserve factual "
            "classification (classified_flag); results.dnf_flag remains "
            "provisional unclassified evidence, not a task target."),
        "race_control_decision": (
            "no message-text state machine. Deterministic per-lap track-state "
            "flags derived from the source TrackStatus code channel "
            "(FastF1 3.7.0 mapping). Untimestamped messages are never used."),
        "telemetry_decision": "ADR-0001: telemetry deferred; D9 uses no "
                              "telemetry.",
        "tables": {
            STATE_ENTITY: {
                "partition_keys": ["season"],
                "primary_key": list(state_primary_key()),
                "column_count": len(STATE_COLUMNS),
                "base_columns": list(D7.ENRICHED_COLUMNS),
                "derived_columns": [
                    f.to_dict() for f in STATE_EXTENSION_FIELDS
                ],
            },
            LABEL_ENTITY: {
                "partition_keys": ["season"],
                "primary_key": list(label_primary_key()),
                "column_count": len(LABEL_COLUMNS),
                "columns": [f.to_dict() for f in LABEL_FIELDS],
            },
        },
    }
