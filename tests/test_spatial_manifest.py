"""P12-1 spatial provenance + manifest contract tests."""

import pytest

from raceintel.spatial import contracts as SC
from raceintel.spatial import manifest as M
from raceintel.spatial.errors import (
    SpatialManifestError,
    SpatialProvenanceError,
)

DRIVERS = [3, 44]


def _provenance(**over):
    base = {
        "season": 2021,
        "race_id": "2021-r05-R",
        "session": "R",
        "source_input_ref": "fastf1_cache/2021/event/Race/position_data",
        "fastf1_version": "3.7.0",
        "raw_row_count": 100,
        "kept_row_count": 90,
        "excluded_zero_fix_rows": 8,
        "excluded_exact_duplicate_rows": 2,
        "driver_numbers": list(DRIVERS),
        "expected_driver_numbers": list(DRIVERS),
        "time_min_s": 1.6,
        "time_max_s": 8100.0,
        "observed_source_values": ["pos"],
        "observed_status_values": ["OnTrack"],
        "content_sha256": "a" * 64,
    }
    base.update(over)
    return M.build_provenance(**base)


def test_build_provenance_minimal_valid():
    record = _provenance()
    assert record["schema_version"] == SC.SPATIAL_SCHEMA_VERSION
    assert record["source_stream"] == SC.SOURCE_STREAM
    assert record["driver_count"] == 2
    assert set(record) >= M.PROVENANCE_REQUIRED_KEYS


def test_provenance_rejects_bad_epoch_and_session():
    with pytest.raises(SpatialProvenanceError):
        _provenance(season=2017)
    with pytest.raises(SpatialProvenanceError):
        _provenance(season=2026)
    _provenance(season=2025)
    with pytest.raises(SpatialProvenanceError):
        _provenance(session="Q")


def test_provenance_rejects_absolute_ref_and_bad_counts():
    with pytest.raises(SpatialProvenanceError):
        _provenance(source_input_ref="/abs/path/position_data")
    with pytest.raises(SpatialProvenanceError):
        _provenance(kept_row_count=101)
    with pytest.raises(SpatialProvenanceError):
        _provenance(content_sha256="xyz")
    with pytest.raises(SpatialProvenanceError):
        _provenance(time_min_s=8100.0, time_max_s=1.6)


def test_provenance_rejects_unknown_keys():
    with pytest.raises(SpatialProvenanceError):
        _provenance(writer="someone")


def test_validate_provenance_round_trip():
    record = _provenance()
    assert M.validate_provenance(record) == record
    assert M.validate_provenance(dict(record)) == record


def test_validate_provenance_failures():
    record = _provenance()
    missing = dict(record)
    del missing["content_sha256"]
    with pytest.raises(SpatialProvenanceError):
        M.validate_provenance(missing)
    extra = dict(record, surprise=1)
    with pytest.raises(SpatialProvenanceError):
        M.validate_provenance(extra)
    mismatch = dict(record, driver_count=5)
    with pytest.raises(SpatialProvenanceError):
        M.validate_provenance(mismatch)
    with pytest.raises(SpatialProvenanceError):
        M.validate_provenance([record])


def test_new_manifest_empty():
    manifest = M.new_manifest()
    assert manifest["manifest_schema_version"] == \
        SC.SPATIAL_MANIFEST_SCHEMA_VERSION
    assert manifest["races"] == {}


def test_manifest_complete_row():
    manifest = M.new_manifest()
    updated = M.set_race_row(manifest, "2021-r05-R", status="COMPLETE",
                             provenance=_provenance())
    assert updated["races"]["2021-r05-R"]["status"] == "COMPLETE"
    assert manifest["races"] == {}
    M.validate_manifest(updated)


def test_manifest_complete_requires_full_driver_set():
    partial = _provenance(expected_driver_numbers=[3, 44, 77])
    with pytest.raises(SpatialManifestError):
        M.set_race_row(M.new_manifest(), "2021-r05-R", status="COMPLETE",
                       provenance=partial)


def test_manifest_partial_and_failed_rows():
    manifest = M.new_manifest()
    manifest = M.set_race_row(manifest, "2021-r05-R", status="PARTIAL",
                              provenance=_provenance(),
                              reason="driver 77 truncated")
    manifest = M.set_race_row(manifest, "2019-r11-R", status="FAILED",
                              reason="source fetch error")
    manifest = M.set_race_row(manifest, "2020-r01-R", status="UNAVAILABLE",
                              reason="no position stream in source")
    M.validate_manifest(manifest)
    assert set(manifest["races"]) == {"2021-r05-R", "2019-r11-R",
                                     "2020-r01-R"}


def test_manifest_row_rules():
    manifest = M.new_manifest()
    with pytest.raises(SpatialManifestError):
        M.set_race_row(manifest, "2021-r05-R", status="PARTIAL",
                       provenance=_provenance())
    with pytest.raises(SpatialManifestError):
        M.set_race_row(manifest, "2021-r05-R", status="FAILED",
                       provenance=_provenance(), reason="x")
    with pytest.raises(SpatialManifestError):
        M.set_race_row(manifest, "2021-r05-R", status="COMPLETE",
                       provenance=_provenance(), reason="extra")
    with pytest.raises(SpatialManifestError):
        M.set_race_row(manifest, "2021-r05-R", status="DONE",
                       reason="x")
    with pytest.raises(SpatialManifestError):
        M.set_race_row(manifest, "2021-r05-R", status="COMPLETE",
                       provenance=_provenance(race_id="2023-r01-R"))


def test_validate_manifest_failures():
    with pytest.raises(SpatialManifestError):
        M.validate_manifest({"races": {}})
    bad = M.new_manifest()
    bad["races"]["2021-r05-R"] = {"status": "COMPLETE"}
    with pytest.raises(SpatialManifestError):
        M.validate_manifest(bad)
    unknown = M.new_manifest()
    unknown["races"]["2021-r05-R"] = {"status": "FAILED",
                                     "reason": "x", "extra": 1}
    with pytest.raises(SpatialManifestError):
        M.validate_manifest(unknown)


def test_manifest_statuses_match_contract():
    assert M.MANIFEST_STATUSES == {"COMPLETE", "PARTIAL", "FAILED",
                                  "UNAVAILABLE"}
