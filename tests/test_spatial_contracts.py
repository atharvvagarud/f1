"""P12-1 spatial contract constants (schema/identity/time/seasons)."""

import pytest

from raceintel.spatial import contracts as SC
from raceintel.spatial.errors import SpatialContractError


def test_schema_versions_pinned():
    assert SC.SPATIAL_SCHEMA_VERSION == "spatial-observation-v1"
    assert SC.SPATIAL_GEOMETRY_SCHEMA_VERSION == "spatial-geometry-v1"
    assert SC.SPATIAL_MANIFEST_SCHEMA_VERSION == "spatial-manifest-v1"
    assert SC.EVIDENCE_FASTF1_VERSION == "3.7.0"
    assert SC.SOURCE_STREAM == "position"


def test_observation_columns_exact_order():
    assert SC.OBSERVATION_COLUMNS == (
        "race_id", "driver_number", "observation_time_s",
        "x", "y", "z", "source", "status",
    )


def test_observation_dtypes_cover_all_columns():
    assert set(SC.OBSERVATION_DTYPES) == set(SC.OBSERVATION_COLUMNS)
    assert SC.OBSERVATION_DTYPES["driver_number"] == "int64"
    assert SC.OBSERVATION_DTYPES["observation_time_s"] == "float64"
    assert SC.OBSERVATION_DTYPES["x"] == "int64"
    assert SC.OBSERVATION_DTYPES["race_id"] == "str"


def test_uniqueness_key_and_sort_order():
    assert SC.OBSERVATION_UNIQUE_KEY == ("driver_number",
                                        "observation_time_s")
    assert SC.OBSERVATION_SORT_ORDER == ("driver_number",
                                        "observation_time_s")


def test_driver_number_bounds():
    assert (SC.DRIVER_NUMBER_MIN, SC.DRIVER_NUMBER_MAX) == (1, 99)


def test_known_vocabularies():
    assert SC.KNOWN_SOURCE_VALUES == frozenset({"pos"})
    assert SC.KNOWN_STATUS_VALUES == frozenset({"OnTrack", "OffTrack"})
    assert SC.ZERO_FIX_COORDINATES == (0, 0, 0)
    assert SC.DUPLICATE_RESOLUTION == "keep-last-by-source-time"


def test_availability_thresholds():
    assert SC.FRESH_MAX_AGE_S == 3.0
    assert SC.STALE_MAX_AGE_S == 15.0
    assert SC.classify_availability(0) == "FRESH"
    assert SC.classify_availability(3.0) == "FRESH"
    assert SC.classify_availability(3.0001) == "STALE"
    assert SC.classify_availability(15.0) == "STALE"
    assert SC.classify_availability(15.0001) == "UNAVAILABLE"
    assert SC.classify_availability(1e9) == "UNAVAILABLE"


def test_availability_rejects_future_and_nonnumeric():
    for bad in (-0.1, -1e9, float("nan"), float("inf"), "3", None):
        with pytest.raises(SpatialContractError):
            SC.classify_availability(bad)


def test_season_epoch_vs_product():
    assert SC.SPATIAL_DATA_MIN_SEASON == 2018
    assert SC.SPATIAL_DATA_MAX_SEASON == 2025
    assert SC.PRODUCT_SERVED_SEASONS == tuple(range(2018, 2025))
    assert SC.is_data_ingestible(2018)
    assert SC.is_data_ingestible(2025)
    assert not SC.is_data_ingestible(2017)
    assert not SC.is_data_ingestible(2026)
    assert not SC.is_data_ingestible("2024")
    assert SC.is_product_servable(2018)
    assert SC.is_product_servable(2024)
    assert not SC.is_product_servable(2025)
    assert not SC.is_product_servable(2017)


def test_artifact_filename():
    assert SC.observations_filename("2021-r05-R") == "2021-r05-R.parquet"
    for bad in ("", "  ", None, 42):
        with pytest.raises(SpatialContractError):
            SC.observations_filename(bad)


def test_serialization_and_layout_constants():
    assert SC.PARQUET_ENGINE == "pyarrow"
    assert SC.PARQUET_COMPRESSION == "snappy"
    assert SC.PARQUET_WRITE_INDEX is False
    assert SC.SPATIAL_ROOT_DIRNAME == "spatial"
    assert SC.OBSERVATIONS_SUBDIR == "observations"
    assert SC.MANIFESTS_SUBDIR == "manifests"
    assert SC.SCHEMA_SUBDIR == "schema"
    assert SC.GEOMETRY_SUBDIR == "geometry"
    assert SC.SPATIAL_MANIFEST_FILENAME == "spatial_manifest.json"
