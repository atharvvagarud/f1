"""D8 telemetry-decision tests — synthetic, offline, no network, no cache.

Covers the offline-testable logic that underpins the D8 measurement and the
candidate lap-level summaries:

- lap-window selection on the session clock (half-open [lap_start, state_end),
  future telemetry excluded — future-telemetry mutation cannot leak);
- candidate summary formulas (deterministic; correct on known inputs);
- missing channel behaviour -> null for the dependent metrics only;
- empty telemetry and sparse telemetry;
- telemetry row-order shuffle -> identical summaries;
- no accidental dependence on whole-race/ future-race aggregates.

FastF1 / the FastF1 cache / D5-D7 canonical data are never touched here.
"""

import numpy as np
import pandas as pd
import pytest

from raceintel.pipeline import d8


def _tel(n=400, start=0.0, end=100.0, seed=0):
    rng = np.random.default_rng(seed)
    t = np.sort(rng.uniform(start, end, n))
    speed = rng.integers(0, 330, n)
    rpm = rng.integers(2000, 12500, n)
    gear = rng.integers(0, 8, n)
    throttle = rng.integers(0, 101, n)
    brake = rng.random(n) < 0.2
    drs = rng.choice([0, 0, 0, 0, 1, 1, 12], n)
    return pd.DataFrame({"Time": t, "RPM": rpm, "Speed": speed,
                         "nGear": gear, "Throttle": throttle,
                         "Brake": brake, "DRS": drs})


def test_window_selection_half_open_and_excludes_future():
    t = np.array([0.0, 50.0, 99.999, 100.0, 150.0, 9999.0])
    idx = d8.sample_indices_in_window(t, 0.0, 100.0)
    assert list(idx) == [0, 1, 2]  # 100.0 and later are the FUTURE -> excluded


def test_future_telemetry_mutation_cannot_change_lap_summary():
    # A lap window is [start, end): telemetry strictly AFTER the lap end is
    # excluded from the window, so mutating/appending it cannot change the
    # lap summary (only within-lap samples can).
    t1 = np.array([10.0, 20.0, 30.0, 40.0])
    frame1 = pd.DataFrame({"Time": t1, "Speed": [100.0, 200.0, 300.0, 400.0]})
    idx1 = d8.sample_indices_in_window(t1, 0.0, 50.0)
    before = d8.summarize_lap(frame1.iloc[idx1])
    # Append future samples (at/after lap end 50s) with absurd values and
    # mutate those future rows; the within-lap samples stay identical.
    t2 = np.array([10.0, 20.0, 30.0, 40.0, 50.0, 51.0, 10_000.0])
    frame2 = pd.DataFrame(
        {"Time": t2, "Speed": [100.0, 200.0, 300.0, 400.0, 999.0,
                               -999.0, 999.0]})
    idx2 = d8.sample_indices_in_window(t2, 0.0, 50.0)
    assert list(idx2) == [0, 1, 2, 3]
    after = d8.summarize_lap(frame2.iloc[idx2])
    assert before == after
    assert after["speed_max_kmh"] == 400.0


def test_summary_deterministic_under_shuffle():
    frame = _tel(seed=1)
    t = frame["Time"].to_numpy()
    idx = d8.sample_indices_in_window(t, 0.0, 100.0)
    win = frame.iloc[idx]
    a = d8.summarize_lap(win)
    b = d8.summarize_lap(win.sample(frac=1.0, random_state=7))
    assert a == b


def test_summary_on_known_inputs():
    frame = pd.DataFrame({
        "Time": [1.0, 2.0, 3.0, 4.0],
        "Speed": [100.0, 200.0, 300.0, 400.0],
        "RPM": [1000.0, 2000.0, 3000.0, 4000.0],
        "Throttle": [0.0, 100.0, 0.0, 100.0],
        "Brake": [False, False, True, False],
        "DRS": [0, 1, 0, 1],
        "nGear": [1, 2, 2, 3],
    })
    s = d8.summarize_lap(frame)
    assert s["sample_count"] == 4
    assert s["speed_max_kmh"] == 400.0
    assert s["speed_mean_kmh"] == 250.0
    assert s["speed_p95_kmh"] == pytest.approx(385.0)
    assert s["throttle_pressed_frac"] == 0.5
    assert s["brake_frac"] == 0.25
    assert s["drs_active_frac"] == 0.5  # DRS == 1
    assert s["rpm_mean"] == 2500.0
    assert s["gear_changes"] == 2  # 1->2 and 2->3


def test_missing_channel_only_nulls_dependent_metrics():
    frame = pd.DataFrame({"Time": [1.0, 2.0, 3.0], "Speed": [1.0, 2.0, 3.0]})
    s = d8.summarize_lap(frame)
    assert s["sample_count"] == 3
    assert s["speed_max_kmh"] == 3.0
    assert s["rpm_mean"] is None
    assert s["throttle_pressed_frac"] is None
    assert s["brake_frac"] is None
    assert s["drs_active_frac"] is None
    assert s["gear_changes"] is None


def test_empty_and_sparse_telemetry():
    empty = d8.summarize_lap(pd.DataFrame())
    assert all(v is None for v in empty.values())
    # sparse: two samples still yield honest (non-null) aggregate values.
    sparse = pd.DataFrame({"Time": [1.0, 2.0], "Speed": [100.0, 200.0],
                           "RPM": [1.0, 2.0]})
    s = d8.summarize_lap(sparse)
    assert s["sample_count"] == 2
    assert s["speed_max_kmh"] == 200.0


def test_summary_does_not_use_whole_race_aggregates():
    # gear-change / throttle metrics are computed only from window samples and
    # never reference race totals: trimming the window cannot increase values.
    frame = pd.DataFrame({
        "Time": [1.0, 2.0, 3.0, 4.0, 5.0],
        "Speed": [1.0, 2.0, 3.0, 4.0, 5.0],
        "RPM": [1.0, 1.0, 1.0, 1.0, 1.0],
        "Throttle": [100.0, 100.0, 100.0, 100.0, 100.0],
        "Brake": [False, False, False, False, False],
        "DRS": [0, 0, 0, 0, 0],
        "nGear": [1, 2, 3, 4, 5],
    })
    full = d8.summarize_lap(frame)
    first_two = d8.summarize_lap(frame.iloc[:2])
    assert full["gear_changes"] == 4
    assert first_two["gear_changes"] == 1  # only within the smaller window


def test_channel_inventory_documented_units():
    # The channel inventory is machine-readable and includes every raw channel
    # the cache car_data stream carries.
    assert "Speed" in d8.CAR_TELEMETRY_CHANNELS
    assert d8.CAR_TELEMETRY_CHANNELS["Speed"][1] == "km/h"
    assert "RPM" in d8.CAR_TELEMETRY_CHANNELS
    assert d8.POSITION_CHANNELS["X"][0] == "float"


def test_sample_defined_and_bounded():
    # The D8 sample is fixed and bounded (one race per plan bucket).
    seasons = [s for s, _r, _l in d8.D8_SAMPLE]
    assert len(d8.D8_SAMPLE) == 8
    assert 2018 in seasons and 2019 in seasons and 2021 in seasons
    assert 2022 in seasons and 2023 in seasons and 2024 in seasons
    assert 2025 in seasons
    race_ids = [r for _s, r, _l in d8.D8_SAMPLE]
    assert len(set(race_ids)) == 8
