"""D3 atomic-storage tests: tiny synthetic frames, no bulk data."""

import pandas as pd
import pytest

from raceintel.errors import IngestionError
from raceintel.storage import atomic_write_parquet, dest_for_unit, read_parquet


def tiny_frame():
    return pd.DataFrame({
        "race_id": pd.array(["2023-r01-R", "2023-r01-R"], dtype="string"),
        "lap_number": pd.array([1, 2], dtype="Int64"),
        "position": pd.array([1, None], dtype="Int64"),
        "lap_time_s": pd.array([95.123, None], dtype="Float64"),
        "compound": pd.array(["SOFT", None], dtype="string"),
        "fresh_tyre": pd.array([True, None], dtype="boolean"),
        "lap_start_utc": pd.to_datetime(
            ["2023-03-05T15:00:00Z", None], utc=True),
    })


def test_atomic_write_and_readback(tmp_path):
    dest = (tmp_path / "processed" / "driver_laps" / "season=2023"
            / "driver_laps__2023-r01-R.parquet")
    out = atomic_write_parquet(tiny_frame(), dest)
    assert out == dest
    back = read_parquet(dest)
    assert len(back) == 2
    assert int(back["position"].isna().sum()) == 1
    assert int(back["compound"].isna().sum()) == 1
    assert str(back["lap_start_utc"].dtype) == "datetime64[ns, UTC]"


def test_destination_paths_are_deterministic(tmp_path):
    first = dest_for_unit(tmp_path, "driver_laps", 2023, "2023-r01-R")
    second = dest_for_unit(tmp_path, "driver_laps", 2023, "2023-r01-R")
    assert first == second
    assert str(first).endswith(
        "driver_laps/season=2023/driver_laps__2023-r01-R.parquet")
    assert ".." not in str(first)


def test_no_temp_files_left_behind(tmp_path):
    dest = tmp_path / "out.parquet"
    atomic_write_parquet(tiny_frame(), dest)
    leftovers = [p for p in dest.parent.iterdir()
                 if p.name.startswith(".tmp-")]
    assert leftovers == []


def test_failed_write_preserves_previous_valid_output(tmp_path, monkeypatch):
    dest = tmp_path / "out.parquet"
    atomic_write_parquet(tiny_frame(), dest)
    before = dest.read_bytes()

    def boom(self, *args, **kwargs):
        raise RuntimeError("disk on fire")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", boom)
    with pytest.raises(IngestionError):
        atomic_write_parquet(tiny_frame(), dest)
    assert dest.read_bytes() == before  # previous output intact
    assert [p for p in dest.parent.iterdir()
            if p.name.startswith(".tmp-")] == []


def test_read_missing_file_fails_clearly(tmp_path):
    with pytest.raises(IngestionError):
        read_parquet(tmp_path / "nope.parquet")
