"""Phase-12 spatial provenance + ingestion manifest contracts (P12-1).

Pure data functions (stdlib + contract constants only):

- artifact provenance: every spatial artifact traceable to schema,
  source, event, input identity, counts, time range, and content hash.
  No absolute paths, usernames, or write timestamps — rows carry source
  times only, so identical inputs always validate identically.
- ingestion manifest: per-race status supporting P12-2 resume and
  partial-failure accounting. P12-1 defines the schema and pure
  constructors/validators; it creates NO bulk manifest rows pretending
  data has been processed.

Row statuses (evidence-justified):
- COMPLETE: expected driver set (from session driver_info) fully
  present and artifact validation green.
- PARTIAL: source present with >= 1 driver but the expected set is
  incomplete or a driver series is truncated, with a reason string.
- FAILED: ingestion error recorded; no artifact.
- UNAVAILABLE: no position stream in source for this race.
"""

from __future__ import annotations

import math

from raceintel.spatial import contracts as SC
from raceintel.spatial.errors import (
    SpatialManifestError,
    SpatialProvenanceError,
)

STATUS_COMPLETE = "COMPLETE"
STATUS_PARTIAL = "PARTIAL"
STATUS_FAILED = "FAILED"
STATUS_UNAVAILABLE = "UNAVAILABLE"

MANIFEST_STATUSES = frozenset({
    STATUS_COMPLETE, STATUS_PARTIAL, STATUS_FAILED, STATUS_UNAVAILABLE,
})

#: Required provenance keys. `source_input_ref` is a repo-relative input
#: reference (e.g. a cache-relative session path), never absolute.
PROVENANCE_REQUIRED_KEYS = frozenset({
    "schema_version",
    "fastf1_version",
    "source_stream",
    "season",
    "race_id",
    "session",
    "source_input_ref",
    "raw_row_count",
    "kept_row_count",
    "excluded_zero_fix_rows",
    "excluded_exact_duplicate_rows",
    "driver_count",
    "driver_numbers",
    "expected_driver_numbers",
    "time_min_s",
    "time_max_s",
    "observed_source_values",
    "observed_status_values",
    "content_sha256",
})

#: Documented optional provenance keys; anything else is rejected so new
#: provenance meaning forces a deliberate schema extension.
PROVENANCE_OPTIONAL_KEYS = frozenset({
    "round_no",
    "event_name",
    "source_session_start_utc",
})

#: Required manifest row keys.
MANIFEST_ROW_REQUIRED_KEYS = frozenset({
    "status",
    "provenance",
})

#: Optional manifest row keys (reason required for non-COMPLETE states).
MANIFEST_ROW_OPTIONAL_KEYS = frozenset({
    "reason",
})


def _check_finite_number(value: object, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpatialProvenanceError(
            f"provenance {name} must be numeric, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise SpatialProvenanceError(
            f"provenance {name} must be finite, got {value!r}")
    return result


def build_provenance(*, season: int, race_id: str, session: str,
                     source_input_ref: str, fastf1_version: str,
                     raw_row_count: int, kept_row_count: int,
                     excluded_zero_fix_rows: int,
                     excluded_exact_duplicate_rows: int,
                     driver_numbers: list, expected_driver_numbers: list,
                     time_min_s: float, time_max_s: float,
                     observed_source_values: list,
                     observed_status_values: list,
                     content_sha256: str, **optional: object) -> dict:
    """Build a validated artifact provenance record (pure, deterministic)."""
    if not SC.is_data_ingestible(season):
        raise SpatialProvenanceError(
            f"season {season!r} outside spatial data epoch "
            f"[{SC.SPATIAL_DATA_MIN_SEASON}, "
            f"{SC.SPATIAL_DATA_MAX_SEASON}]")
    if not isinstance(race_id, str) or not race_id.strip():
        raise SpatialProvenanceError(f"race_id must be non-empty")
    if session != "R":
        raise SpatialProvenanceError(
            f"session must be 'R' (race), got {session!r}")
    if not isinstance(source_input_ref, str) or not source_input_ref.strip():
        raise SpatialProvenanceError("source_input_ref must be non-empty")
    if source_input_ref.startswith("/"):
        raise SpatialProvenanceError(
            "source_input_ref must be repo-relative, never absolute")
    for name, value in (("raw_row_count", raw_row_count),
                       ("kept_row_count", kept_row_count),
                       ("excluded_zero_fix_rows", excluded_zero_fix_rows),
                       ("excluded_exact_duplicate_rows",
                        excluded_exact_duplicate_rows)):
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise SpatialProvenanceError(
                f"provenance {name} must be a non-negative int")
    if kept_row_count > raw_row_count:
        raise SpatialProvenanceError("kept_row_count exceeds raw_row_count")
    if sorted(set(driver_numbers)) != sorted(driver_numbers) or not all(
            isinstance(n, int) and not isinstance(n, bool)
            for n in driver_numbers):
        raise SpatialProvenanceError(
            "driver_numbers must be a sorted unique int list")
    if sorted(set(expected_driver_numbers)) != sorted(
            expected_driver_numbers) or not all(
            isinstance(n, int) and not isinstance(n, bool)
            for n in expected_driver_numbers):
        raise SpatialProvenanceError(
            "expected_driver_numbers must be a sorted unique int list")
    time_min = _check_finite_number(time_min_s, "time_min_s")
    time_max = _check_finite_number(time_max_s, "time_max_s")
    if time_max < time_min:
        raise SpatialProvenanceError("time_max_s precedes time_min_s")
    if (not isinstance(content_sha256, str) or len(content_sha256) != 64
            or any(c not in "0123456789abcdef"
                   for c in content_sha256)):
        raise SpatialProvenanceError("content_sha256 must be a hex digest")
    unknown_optional = set(optional) - PROVENANCE_OPTIONAL_KEYS
    if unknown_optional:
        raise SpatialProvenanceError(
            f"unknown provenance keys {sorted(unknown_optional)}")
    record = {
        "schema_version": SC.SPATIAL_SCHEMA_VERSION,
        "fastf1_version": fastf1_version,
        "source_stream": SC.SOURCE_STREAM,
        "season": season,
        "race_id": race_id,
        "session": session,
        "source_input_ref": source_input_ref,
        "raw_row_count": raw_row_count,
        "kept_row_count": kept_row_count,
        "excluded_zero_fix_rows": excluded_zero_fix_rows,
        "excluded_exact_duplicate_rows": excluded_exact_duplicate_rows,
        "driver_count": len(driver_numbers),
        "driver_numbers": sorted(driver_numbers),
        "expected_driver_numbers": sorted(expected_driver_numbers),
        "time_min_s": time_min,
        "time_max_s": time_max,
        "observed_source_values": sorted(set(observed_source_values)),
        "observed_status_values": sorted(set(observed_status_values)),
        "content_sha256": content_sha256,
    }
    record.update(optional)
    return record


def validate_provenance(record: object) -> dict:
    """Fail-closed provenance validation; returns a normalized copy."""
    if not isinstance(record, dict):
        raise SpatialProvenanceError(
            f"provenance must be a mapping, got {type(record).__name__}")
    keys = set(record)
    missing = PROVENANCE_REQUIRED_KEYS - keys
    if missing:
        raise SpatialProvenanceError(
            f"provenance missing keys {sorted(missing)}")
    unknown = keys - PROVENANCE_REQUIRED_KEYS - PROVENANCE_OPTIONAL_KEYS
    if unknown:
        raise SpatialProvenanceError(
            f"provenance unknown keys {sorted(unknown)}")
    if record["schema_version"] != SC.SPATIAL_SCHEMA_VERSION:
        raise SpatialProvenanceError(
            f"unsupported schema_version {record['schema_version']!r}")
    if record["driver_count"] != len(record["driver_numbers"]):
        raise SpatialProvenanceError(
            "driver_count does not match driver_numbers length")
    rebuilt = build_provenance(
        season=record["season"],
        race_id=record["race_id"],
        session=record["session"],
        source_input_ref=record["source_input_ref"],
        fastf1_version=record["fastf1_version"],
        raw_row_count=record["raw_row_count"],
        kept_row_count=record["kept_row_count"],
        excluded_zero_fix_rows=record["excluded_zero_fix_rows"],
        excluded_exact_duplicate_rows=record[
            "excluded_exact_duplicate_rows"],
        driver_numbers=list(record["driver_numbers"]),
        expected_driver_numbers=list(
            record["expected_driver_numbers"]),
        time_min_s=record["time_min_s"],
        time_max_s=record["time_max_s"],
        observed_source_values=list(record["observed_source_values"]),
        observed_status_values=list(record["observed_status_values"]),
        content_sha256=record["content_sha256"],
        **{k: record[k] for k in PROVENANCE_OPTIONAL_KEYS if k in record},
    )
    return rebuilt


def new_manifest() -> dict:
    """Empty ingestion manifest (P12-1 creates no bulk rows)."""
    return {
        "manifest_schema_version": SC.SPATIAL_MANIFEST_SCHEMA_VERSION,
        "spatial_schema_version": SC.SPATIAL_SCHEMA_VERSION,
        "races": {},
    }


def set_race_row(manifest: object, race_id: str, *, status: str,
                 provenance: dict | None = None,
                 reason: str | None = None) -> dict:
    """Pure manifest row upsert; returns a new manifest (no mutation)."""
    if not isinstance(manifest, dict) or not isinstance(
            manifest.get("races"), dict):
        raise SpatialManifestError("manifest must carry a races mapping")
    if manifest.get("manifest_schema_version") != \
            SC.SPATIAL_MANIFEST_SCHEMA_VERSION:
        raise SpatialManifestError("unsupported manifest_schema_version")
    if not isinstance(race_id, str) or not race_id.strip():
        raise SpatialManifestError("race_id must be a non-empty string")
    if status not in MANIFEST_STATUSES:
        raise SpatialManifestError(
            f"status must be one of {sorted(MANIFEST_STATUSES)}, "
            f"got {status!r}")
    if status in (STATUS_COMPLETE, STATUS_PARTIAL):
        if provenance is None:
            raise SpatialManifestError(
                f"{status} rows require provenance")
        validated = validate_provenance(provenance)
        if validated["race_id"] != race_id:
            raise SpatialManifestError(
                "provenance race_id does not match manifest row")
        if status == STATUS_COMPLETE and (
                validated["driver_count"]
                != len(validated["expected_driver_numbers"])):
            raise SpatialManifestError(
                "COMPLETE requires the full expected driver set; use "
                "PARTIAL with a reason otherwise")
    else:
        validated = None
        if provenance is not None:
            raise SpatialManifestError(
                f"{status} rows must not carry provenance")
    if status != STATUS_COMPLETE and not (reason and reason.strip()):
        raise SpatialManifestError(f"{status} rows require a reason")
    if status == STATUS_COMPLETE and reason is not None:
        raise SpatialManifestError("COMPLETE rows must not carry a reason")
    row: dict = {"status": status}
    if validated is not None:
        row["provenance"] = validated
    if reason is not None:
        row["reason"] = reason
    updated = dict(manifest)
    races = dict(manifest["races"])
    races[race_id] = row
    updated["races"] = races
    return updated


def validate_manifest(manifest: object) -> dict:
    """Fail-closed manifest validation; returns the manifest unchanged."""
    if not isinstance(manifest, dict):
        raise SpatialManifestError("manifest must be a mapping")
    if manifest.get("manifest_schema_version") != \
            SC.SPATIAL_MANIFEST_SCHEMA_VERSION:
        raise SpatialManifestError("unsupported manifest_schema_version")
    if manifest.get("spatial_schema_version") != SC.SPATIAL_SCHEMA_VERSION:
        raise SpatialManifestError("unsupported spatial_schema_version")
    races = manifest.get("races")
    if not isinstance(races, dict):
        raise SpatialManifestError("manifest races must be a mapping")
    for race_id, row in races.items():
        if not isinstance(row, dict):
            raise SpatialManifestError(
                f"row for {race_id!r} must be a mapping")
        unknown = set(row) - MANIFEST_ROW_REQUIRED_KEYS - \
            MANIFEST_ROW_OPTIONAL_KEYS
        if unknown:
            raise SpatialManifestError(
                f"row for {race_id!r} has unknown keys {sorted(unknown)}")
        rebuilt = set_race_row(
            {"manifest_schema_version":
             SC.SPATIAL_MANIFEST_SCHEMA_VERSION,
             "spatial_schema_version": SC.SPATIAL_SCHEMA_VERSION,
             "races": {}},
            race_id,
            status=row.get("status", ""),
            provenance=row.get("provenance"),
            reason=row.get("reason"),
        )
        if rebuilt["races"][race_id] != row:
            raise SpatialManifestError(
                f"row for {race_id!r} does not round-trip validation")
    return manifest
