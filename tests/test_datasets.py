"""D. Dataset / race discovery — schema assumptions the app relies on.

Pins the R0 inventory: per-checkpoint datasets load, carry the columns the
predictor selects, cover seasons 2019-2023, and expose the race list the
/races endpoint serves (lap-10 based, 104 races, sorted).
"""

import pytest

from ml.config import CHECKPOINTS
from ml.features import FEATURE_COLS
from ml.inference import get_available_races, load_dataset

REQUIRED_COLUMNS = {
    "year",
    "event_name",
    "driver",
    "driver_number",
    "is_winner",
} | set(FEATURE_COLS)


@pytest.mark.parametrize("lap", CHECKPOINTS)
def test_checkpoint_dataset_schema(lap):
    df = load_dataset(lap)
    assert len(df) > 1000  # thousands of driver-snapshot rows per checkpoint
    missing = REQUIRED_COLUMNS - set(df.columns)
    assert not missing, f"lap {lap} missing columns: {missing}"
    assert set(df["year"].unique()) == {2019, 2020, 2021, 2022, 2023}


def test_lap10_race_inventory():
    df = load_dataset(10)
    races = df[["year", "event_name"]].drop_duplicates()
    assert len(races) == 104
    assert (df.groupby(["year", "event_name"])["is_winner"].sum() == 1).all(), (
        "baseline integrity rule: exactly one winner row per race"
    )


def test_available_races_matches_baseline():
    races = get_available_races()
    assert len(races) == 104
    assert all(set(r) == {"year", "event_name"} for r in races)
    keys = [(r["year"], r["event_name"]) for r in races]
    assert keys == sorted(keys)
