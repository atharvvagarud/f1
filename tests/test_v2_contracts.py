"""V2 contract semantics tests (D2). Synthetic only: no downloaded data,
no parquet, no network. Tests the contract module, not the dataset."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from v2 import contracts as C


def test_key_formats_are_deterministic():
    assert C.make_event_id(2023, 1) == "2023-r01"
    assert C.make_event_id(2020, 21) == "2020-r21"
    assert C.make_race_id(2023, 1) == "2023-r01-R"
    assert C.make_session_id("2023-r01", "S") == "2023-r01-S"
    assert C.make_driver_lap_key("2023-r01-R", "max_verstappen", 25) == (
        "2023-r01-R", "max_verstappen", 25)
    assert C.make_pit_stop_key("2023-r01-R", "max_verstappen", 2) == (
        "2023-r01-R", "max_verstappen", 2)
    assert C.make_stint_key("2023-r01-R", "max_verstappen", 1) == (
        "2023-r01-R", "max_verstappen", 1)


def test_keys_carry_no_display_names():
    eid = C.make_event_id(2021, 14)
    rid = C.make_race_id(2021, 14)
    for key in (eid, rid):
        assert " " not in key
        for ban in ("Paulo", "Prix", "Grand", "VER", "ver"):
            assert ban not in key


def test_session_codes_reject_unknown():
    try:
        C.make_session_id("2023-r01", "XX")
    except ValueError:
        return
    raise AssertionError("unknown session code accepted")


def test_driver_laps_has_no_label_columns():
    labels = C.DRIVER_LAPS.label_columns()
    assert labels == [], f"leakage: LABEL_ONLY in driver_laps: {labels}"


def test_results_owns_outcomes():
    labels = set(C.RESULTS.label_columns())
    for expected in ("position_final", "classified_position", "points",
                     "dnf_flag", "winner_flag", "status_text"):
        assert expected in labels
    # grid is knowable pre-race even though it lives in the results table
    avail = {c.name: c.availability for c in C.RESULTS.columns}
    assert avail["grid_position"] is C.Availability.PRE_RACE


def test_dnf_flag_is_classification_evidence_not_status_rule():
    """D4 rejection, pinned: dnf must come from the official classification
    token (null classified_position), never from status text or null
    position — retirements carry classified numbers, lapped finishers are
    classified. The final ML binary-target policy stays deferred."""
    cols = {c.name: c for c in C.RESULTS.columns}
    dnf = cols["dnf_flag"]
    assert dnf.availability is C.Availability.LABEL_ONLY
    assert dnf.nullable
    assert "classified" in dnf.description
    assert "status text" in dnf.description
    assert "deferred" in dnf.description
    assert "label stage" in C.RESULTS.notes


def test_every_table_has_grain_keys_and_source():
    for t in C.ALL_TABLES:
        assert t.grain, t.entity
        assert len(t.primary_key) >= 1, t.entity
        assert t.source_of_truth, t.entity
        for col in t.columns:
            assert isinstance(col.availability, C.Availability), (t.entity, col.name)
            assert col.owner, (t.entity, col.name)


def test_no_legacy_suffixes_and_explicit_units():
    for t in C.ALL_TABLES:
        for col in t.columns:
            assert "_x" not in col.name and not col.name.endswith("_y"), col.name
            assert col.unit, col.name


def test_partition_layout_defaults_to_season():
    assert C.partition_path("driver_laps", 2023) == \
        "data/v2/processed/driver_laps/season=2023"
    assert C.partition_path("driver_laps", 2023, 1) == \
        "data/v2/processed/driver_laps/season=2023/round=01"


def test_schema_version_and_registry():
    assert C.SCHEMA_VERSION == 1
    assert C.get_table("driver_laps") is C.DRIVER_LAPS
    try:
        C.get_table("telemetry_raw_everything")
    except KeyError:
        return
    raise AssertionError("unknown entity accepted")


def test_telemetry_summary_is_explicitly_unresolved():
    cols = C.TELEMETRY_SUMMARY.column_names()
    assert "telemetry_sample_count" in cols
    assert "mean_throttle" not in cols  # D8 candidates must NOT be pre-fixed
    assert "D8" in C.TELEMETRY_SUMMARY.notes
