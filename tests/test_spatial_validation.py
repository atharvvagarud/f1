"""P12-1 spatial observation validation + canonicalization tests."""

import pandas as pd
import pytest

from raceintel.spatial import contracts as SC
from raceintel.spatial import validation as V
from raceintel.spatial.errors import (
    SpatialDuplicateConflictError,
    SpatialIdentityError,
    SpatialSchemaError,
)

COLS = list(SC.OBSERVATION_COLUMNS)


def _row(**over):
    base = {
        "race_id": "2021-r05-R",
        "driver_number": 44,
        "observation_time_s": 4207.0,
        "x": -7000,
        "y": -9000,
        "z": -100,
        "source": "pos",
        "status": "OnTrack",
    }
    base.update(over)
    return base


def _frame(rows):
    return pd.DataFrame(rows, columns=COLS)


def _raw(rows):
    frame = pd.DataFrame(rows)
    frame["source_observed_at"] = [
        f"2021-05-23T14:00:{i:02d}" for i in range(len(frame))]
    return frame


def test_valid_frame_report():
    frame = _frame([_row(driver_number=33, observation_time_s=4206.0,
                         x=100),
                    _row()])
    report = V.validate_observations(frame, race_id="2021-r05-R")
    assert report["schema_version"] == SC.SPATIAL_SCHEMA_VERSION
    assert report["row_count"] == 2
    assert report["driver_count"] == 2
    assert report["driver_numbers"] == [33, 44]
    assert report["time_min_s"] == 4206.0
    assert report["time_max_s"] == 4207.0
    assert report["is_canonically_sorted"] is True
    assert report["observed_source_values"] == ["pos"]
    assert report["observed_status_values"] == ["OnTrack"]


def test_column_order_matters():
    frame = _frame([_row()])[COLS[::-1]]
    with pytest.raises(SpatialSchemaError):
        V.validate_observations(frame)


def test_empty_rejected():
    with pytest.raises(SpatialSchemaError):
        V.validate_observations(_frame([]))


def test_non_frame_rejected():
    with pytest.raises(SpatialSchemaError):
        V.validate_observations([_row()])


def test_race_id_filter():
    frame = _frame([_row()])
    with pytest.raises(SpatialIdentityError):
        V.validate_observations(frame, race_id="2023-r01-R")
    with pytest.raises(SpatialIdentityError):
        V.validate_observations(_frame([_row(race_id="")]))


def test_driver_number_bounds():
    for bad in (0, 100, -5, 1.5, "44", None, True):
        with pytest.raises(SpatialIdentityError):
            V.validate_observations(_frame([_row(driver_number=bad)]))


def test_time_domain():
    for bad in (-1.0, float("nan"), float("inf"), "4207", None):
        with pytest.raises(SpatialSchemaError):
            V.validate_observations(
                _frame([_row(observation_time_s=bad)]))
    V.validate_observations(_frame([_row(observation_time_s=0.0)]))


def test_coordinates_must_be_integral_metres():
    for bad in (1.5, float("nan"), "x", None):
        with pytest.raises(SpatialSchemaError):
            V.validate_observations(_frame([_row(x=bad)]))
    V.validate_observations(
        _frame([_row(x=-5, y=-5, z=-5)]))


def test_zero_fix_rejected():
    with pytest.raises(SpatialSchemaError):
        V.validate_observations(_frame([_row(x=0, y=0, z=0)]))


def test_persisted_duplicates_fail_closed():
    frame = _frame([_row(), _row()])
    with pytest.raises(SpatialDuplicateConflictError):
        V.validate_observations(frame)


def test_strict_vocabularies():
    with pytest.raises(SpatialSchemaError):
        V.validate_observations(_frame([_row(source="telemetry")]))
    with pytest.raises(SpatialSchemaError):
        V.validate_observations(_frame([_row(status="InPit")]))
    report = V.validate_observations(_frame([_row(status="OffTrack")]),
                                     strict=False)
    assert report["observed_status_values"] == ["OffTrack"]
    report = V.validate_observations(_frame([_row(source="telemetry")]),
                                     strict=False)
    assert report["observed_source_values"] == ["telemetry"]


def test_unsorted_flagged_not_rejected():
    frame = _frame([_row(driver_number=44, observation_time_s=4208.0),
                    _row(driver_number=33, observation_time_s=4207.0)])
    report = V.validate_observations(frame)
    assert report["is_canonically_sorted"] is False


def test_canonicalize_dedupes_keep_last_and_sorts():
    raw = _raw([
        {**_row(observation_time_s=4207.0, x=-7000), },
        {**_row(observation_time_s=4207.0, x=-7001), },
        {**_row(driver_number=33, observation_time_s=4207.0,
                x=100, y=200, z=-50), },
    ])
    out = V.canonicalize_observations(raw)
    assert list(out.columns) == COLS
    assert len(out) == 2
    assert out.iloc[0]["driver_number"] == 33
    assert out.iloc[1]["x"] == -7001
    assert str(out["driver_number"].dtype) == "int64"
    assert str(out["observation_time_s"].dtype) == "float64"
    assert out.attrs["raw_row_count"] == 3
    assert out.attrs["excluded_zero_fix_rows"] == 0


def test_canonicalize_excludes_zero_fix():
    raw = _raw([_row(x=0, y=0, z=0),
                _row(observation_time_s=4208.0, x=5)])
    out = V.canonicalize_observations(raw)
    assert len(out) == 1
    assert out.attrs["excluded_zero_fix_rows"] == 1


def test_canonicalize_all_zero_fix_rejected():
    with pytest.raises(SpatialSchemaError):
        V.canonicalize_observations(_raw([_row(x=0, y=0, z=0)]))


def test_canonicalize_requires_transient_key():
    raw = pd.DataFrame([_row(), _row(observation_time_s=4208.0)])
    with pytest.raises(SpatialSchemaError):
        V.canonicalize_observations(raw)
    bad = _raw([_row()])
    bad.loc[0, V.TRANSIENT_SOURCE_TIME_COLUMN] = None
    with pytest.raises(SpatialSchemaError):
        V.canonicalize_observations(bad)


def test_canonicalize_conflict_fails_closed():
    raw = _raw([_row(x=1), _row(x=2)])
    raw[V.TRANSIENT_SOURCE_TIME_COLUMN] = "2021-05-23T14:00:00"
    with pytest.raises(SpatialDuplicateConflictError):
        V.canonicalize_observations(raw)


def test_content_hash_stable_and_sensitive():
    frame = _frame([_row(), _row(driver_number=33,
                                 observation_time_s=4208.0, x=1)])
    first = V.logical_content_hash(frame)
    assert first == V.logical_content_hash(frame.copy())
    assert len(first) == 64
    moved = frame.copy()
    moved.loc[0, "x"] = -7001
    assert V.logical_content_hash(moved) != first
    reordered = frame.sort_values("observation_time_s",
                                  ascending=False)
    assert V.logical_content_hash(reordered) == first


def test_content_hash_rejects_wrong_columns():
    frame = _frame([_row()])[COLS[::-1]]
    with pytest.raises(SpatialSchemaError):
        V.logical_content_hash(frame)


def test_content_hash_rejects_nonfinite():
    frame = _frame([_row()])
    frame["observation_time_s"] = float("nan")
    with pytest.raises(SpatialSchemaError):
        V.logical_content_hash(frame)
