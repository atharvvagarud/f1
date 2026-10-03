"""Phase-12 spatial observation validation + canonicalization (P12-1).

Pure DataFrame functions (pandas only, already a core dependency):

- :func:`canonicalize_observations`: raw FastF1-shaped rows (persisted
  columns plus transient ``source_observed_at`` ordering key) into the
  exact persisted contract: zero-fix rows excluded, duplicates resolved
  deterministically (keep last by source time), sorted, cast, validated.
- :func:`validate_observations`: fail-closed schema/identity/time/
  coordinate validation of a persisted-shape frame.
- :func:`logical_content_hash`: stable content identity over logical
  values (schema version, column order, row ordering, values), excluding
  filesystem metadata and write timestamps.

Allowed P12-2 cleaning (and nothing else): exact-duplicate removal per
the keep-last rule and zero-fix sentinel exclusion. No downsampling, no
smoothing, no interpolation, no geometry normalization, no pit removal.
"""

from __future__ import annotations

import hashlib
import json
import math

import numpy as np
import pandas as pd

from raceintel.spatial import contracts as SC
from raceintel.spatial.errors import (
    SpatialDuplicateConflictError,
    SpatialIdentityError,
    SpatialSchemaError,
)

#: Transient ordering key accepted by canonicalization (absolute FastF1
#: Date per raw sample). Never persisted.
TRANSIENT_SOURCE_TIME_COLUMN = "source_observed_at"


def _req_frame(value: object) -> pd.DataFrame:
    if not isinstance(value, pd.DataFrame):
        raise SpatialSchemaError(
            f"observations must be a DataFrame, got {type(value).__name__}")
    return value


def _check_race_id(value: object) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpatialIdentityError(
            f"race_id must be a non-empty string, got {value!r}")
    return value


def _check_driver_number(value: object) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpatialIdentityError(
            f"driver_number must be numeric, got {value!r}")
    if isinstance(value, float) and not value.is_integer():
        raise SpatialIdentityError(
            f"driver_number must be integral, got {value!r}")
    number = int(value)
    if not SC.DRIVER_NUMBER_MIN <= number <= SC.DRIVER_NUMBER_MAX:
        raise SpatialIdentityError(
            f"driver_number must be in "
            f"[{SC.DRIVER_NUMBER_MIN}, {SC.DRIVER_NUMBER_MAX}], "
            f"got {number!r}")
    return number


def _check_time(value: object) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpatialSchemaError(
            f"observation_time_s must be numeric, got {value!r}")
    result = float(value)
    if not math.isfinite(result) or result < 0:
        raise SpatialSchemaError(
            f"observation_time_s must be finite and >= 0 (session clock), "
            f"got {value!r}")
    return result


def _check_coordinate(value: object, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise SpatialSchemaError(
            f"{name} must be numeric, got {value!r}")
    if isinstance(value, float):
        if not math.isfinite(value) or not value.is_integer():
            raise SpatialSchemaError(
                f"{name} must be an integral metre value, got {value!r}")
        value = int(value)
    return int(value)


def _check_token(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise SpatialSchemaError(
            f"{name} must be a non-empty string, got {value!r}")
    return value


def validate_observations(frame: pd.DataFrame, *, strict: bool = True,
                          race_id: str | None = None) -> dict:
    """Fail-closed validation of a persisted-shape observation frame.

    Returns a deterministic evidence report (row/driver counts, time
    range, observed vocabularies). Raises on any violation. ``strict``
    additionally rejects Source/Status values outside the documented
    known sets so new semantics force a contract extension.
    """
    frame = _req_frame(frame)
    if tuple(frame.columns) != SC.OBSERVATION_COLUMNS:
        raise SpatialSchemaError(
            f"columns must be exactly {list(SC.OBSERVATION_COLUMNS)}, "
            f"got {list(frame.columns)}")
    if frame.empty:
        raise SpatialSchemaError("observations must not be empty")
    if race_id is not None:
        _check_race_id(race_id)
        if set(frame["race_id"].unique().tolist()) != {race_id}:
            raise SpatialIdentityError(
                f"artifact must contain only race_id {race_id!r}")

    for value in frame["race_id"].tolist():
        _check_race_id(value)
    numbers = [_check_driver_number(v) for v in frame["driver_number"]]
    times = [_check_time(v) for v in frame["observation_time_s"]]
    for name in ("x", "y", "z"):
        [_check_coordinate(v, name) for v in frame[name]]
    sources = [_check_token(v, "source") for v in frame["source"]]
    statuses = [_check_token(v, "status") for v in frame["status"]]

    zero_fix = ((frame["x"] == 0) & (frame["y"] == 0)
                & (frame["z"] == 0)).sum()
    if int(zero_fix) > 0:
        raise SpatialSchemaError(
            f"{int(zero_fix)} zero-fix sentinel rows present; P12-2 must "
            f"exclude (0, 0, 0) rows before persisting")

    key = list(SC.OBSERVATION_UNIQUE_KEY)
    if frame.duplicated(subset=key).any():
        bad = frame[frame.duplicated(subset=key, keep=False)]
        example = bad.iloc[0]
        raise SpatialDuplicateConflictError(
            f"duplicate (driver_number, observation_time_s) persisted for "
            f"driver {example['driver_number']} at "
            f"t={example['observation_time_s']}; canonicalization must "
            f"resolve duplicates before persisting")

    observed_sources = sorted(set(sources))
    observed_statuses = sorted(set(statuses))
    if strict:
        unknown_sources = [s for s in observed_sources
                           if s not in SC.KNOWN_SOURCE_VALUES]
        if unknown_sources:
            raise SpatialSchemaError(
                f"unknown source values {unknown_sources}; extend "
                f"KNOWN_SOURCE_VALUES deliberately, never silently")
        unknown_statuses = [s for s in observed_statuses
                            if s not in SC.KNOWN_STATUS_VALUES]
        if unknown_statuses:
            raise SpatialSchemaError(
                f"unknown status values {unknown_statuses}; extend "
                f"KNOWN_STATUS_VALUES deliberately, never silently")

    ordered = frame.sort_values(list(SC.OBSERVATION_SORT_ORDER),
                                kind="mergesort").reset_index(drop=True)
    canonical = frame.reset_index(drop=True)
    return {
        "schema_version": SC.SPATIAL_SCHEMA_VERSION,
        "row_count": int(len(frame)),
        "driver_count": int(len(set(numbers))),
        "driver_numbers": sorted(set(numbers)),
        "time_min_s": min(times),
        "time_max_s": max(times),
        "is_canonically_sorted": bool(ordered.equals(canonical)),
        "observed_source_values": observed_sources,
        "observed_status_values": observed_statuses,
    }


def canonicalize_observations(raw: pd.DataFrame) -> pd.DataFrame:
    """Reduce raw FastF1-shaped rows to the exact persisted contract.

    Input columns: persisted columns plus transient
    ``source_observed_at`` (absolute per-sample timestamp, any
    orderable representation; never persisted). Steps: drop zero-fix
    sentinel rows; fail closed on same-(driver, Time, Date) coordinate
    conflicts; keep the last row per (driver, Time) ordered by source
    time; cast exact dtypes; sort canonically; validate.
    """
    raw = _req_frame(raw)
    expected = set(SC.OBSERVATION_COLUMNS) | {TRANSIENT_SOURCE_TIME_COLUMN}
    if set(raw.columns) != expected:
        raise SpatialSchemaError(
            f"raw input must carry persisted columns plus "
            f"{TRANSIENT_SOURCE_TIME_COLUMN!r}, got "
            f"{sorted(raw.columns)}")
    if raw[TRANSIENT_SOURCE_TIME_COLUMN].isna().any():
        raise SpatialSchemaError(
            f"{TRANSIENT_SOURCE_TIME_COLUMN} must be non-null (orders "
            f"sub-second duplicates deterministically)")

    work = raw.copy()
    zero_fix = ((work["x"] == 0) & (work["y"] == 0) & (work["z"] == 0))
    excluded_zero_fix = int(zero_fix.sum())
    work = work.loc[~zero_fix]
    if work.empty:
        raise SpatialSchemaError(
            "no observations remain after zero-fix exclusion")

    group_key = [TRANSIENT_SOURCE_TIME_COLUMN]
    key = list(SC.OBSERVATION_UNIQUE_KEY)
    coords = ["x", "y", "z", "source", "status"]
    conflicts = work.groupby(key + group_key)[coords].nunique(dropna=False)
    if (conflicts.max(axis=1) > 1).any():
        bad = conflicts[conflicts.max(axis=1) > 1].iloc[0]
        raise SpatialDuplicateConflictError(
            f"conflicting coordinates for one (driver, Time, Date): "
            f"{bad.to_dict()}")

    ordered = work.sort_values(key + group_key, kind="mergesort")
    deduped = ordered.drop_duplicates(subset=key, keep="last")
    out = deduped.loc[:, list(SC.OBSERVATION_COLUMNS)].copy()
    out["driver_number"] = out["driver_number"].astype("int64")
    out["observation_time_s"] = out["observation_time_s"].astype("float64")
    for name in ("x", "y", "z"):
        out[name] = out[name].astype("int64")
    out["race_id"] = out["race_id"].astype("str")
    out["source"] = out["source"].astype("str")
    out["status"] = out["status"].astype("str")
    out = out.sort_values(list(SC.OBSERVATION_SORT_ORDER),
                          kind="mergesort").reset_index(drop=True)
    validate_observations(out)
    out.attrs["excluded_zero_fix_rows"] = excluded_zero_fix
    out.attrs["raw_row_count"] = int(len(raw))
    return out


def logical_content_hash(frame: pd.DataFrame) -> str:
    """Stable content identity over logical values (not file bytes).

    Canonicalizes: schema version, column order, row ordering by the
    contract sort key, and JSON-normalized values. Excludes absolute
    paths and write timestamps by construction (no such inputs).
    Same logical dataset from any writer version hashes identically;
    byte-identical Parquet across library versions is NOT promised.
    """
    frame = _req_frame(frame)
    if tuple(frame.columns) != SC.OBSERVATION_COLUMNS:
        raise SpatialSchemaError(
            "content hash requires exact persisted column order")
    ordered = frame.sort_values(list(SC.OBSERVATION_SORT_ORDER),
                                kind="mergesort")
    rows = []
    for record in ordered.to_dict(orient="records"):
        rows.append({name: _json_scalar(record[name])
                     for name in SC.OBSERVATION_COLUMNS})
    payload = {
        "schema_version": SC.SPATIAL_SCHEMA_VERSION,
        "columns": list(SC.OBSERVATION_COLUMNS),
        "rows": rows,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                           allow_nan=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _json_scalar(value: object) -> object:
    if isinstance(value, bool):
        raise SpatialSchemaError(
            f"boolean not allowed in spatial values: {value!r}")
    if isinstance(value, (int,)):
        return int(value)
    if isinstance(value, float):
        if not math.isfinite(value):
            raise SpatialSchemaError(
                f"non-finite float not hashable: {value!r}")
        return value
    if isinstance(value, str):
        return value
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        result = float(value)
        if not math.isfinite(result):
            raise SpatialSchemaError(
                f"non-finite float not hashable: {value!r}")
        return result
    raise SpatialSchemaError(
        f"unhashable spatial value type {type(value).__name__}")
