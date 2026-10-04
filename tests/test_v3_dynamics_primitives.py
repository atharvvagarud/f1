"""V3.1B numerical primitive tests (hand-computed goldens, no corpus)."""

import math

import pytest

from raceintel.features.dynamics import calculators as C
from raceintel.features.rates import ols_slope_xy


def test_ols_exact_linear():
    assert C.ols_slope([1, 2, 3], [2.0, 4.0, 6.0]) == pytest.approx(2.0)
    assert C.ols_slope([7, 8, 9, 10, 11, 12],
                       [16.5, 16.0, 15.5, 15.0, 14.5, 14.0]
                       ) == pytest.approx(-0.5)


def test_ols_matches_frozen_f8_math():
    import numpy as np
    from raceintel.features.temporal import TemporalError
    good = [([1, 2, 3, 4, 5], [10.0, 9.5, 9.0, 8.5, 8.0]),
            ([7, 9, 12], [3.0, 2.0, 2.5])]
    for xs, ys in good:
        assert C.ols_slope(xs, ys) == pytest.approx(
            ols_slope_xy(np.array(xs, dtype=float),
                         np.array(ys, dtype=float)))
    # degenerate x: F8 raises, V3.1 returns None (fail-to-null contract)
    with pytest.raises(TemporalError):
        ols_slope_xy(np.array([3.0, 3.0, 3.0]),
                     np.array([1.0, 2.0, 1.5]))
    assert C.ols_slope([3, 3, 3], [1.0, 2.0, 1.5]) is None


def test_ols_degenerate_none():
    assert C.ols_slope([5], [1.0]) is None
    assert C.ols_slope([4, 4], [1.0, 2.0]) is None
    assert C.ols_slope([1, 2], [1.0, float("nan")]) is None
    assert C.ols_slope([], []) is None


def test_endpoint_rate_golden():
    assert C.endpoint_rate(10.0, 4.0, 3) == pytest.approx(2.0)
    assert C.endpoint_rate(4.0, 10.0, 3) == pytest.approx(-2.0)
    assert C.endpoint_rate(10.0, 4.0, 0) is None
    assert C.endpoint_rate(None, 4.0, 3) is None
    assert C.endpoint_rate(10.0, None, 3) is None


def test_iqr_golden():
    assert C.iqr([1.0, 2.0, 3.0, 4.0, 5.0]) == pytest.approx(2.0)
    assert C.iqr([5.0, 5.0, 5.0, 5.0]) == pytest.approx(0.0)
    assert C.iqr([1.0, 2.0]) is None
    assert C.iqr([]) is None


def test_pctl_range_golden():
    spread, n = C.pctl_range([float(i) for i in range(11)], min_n=5)
    assert spread == pytest.approx(8.0)
    assert n == 11
    spread, n = C.pctl_range([1.0, 2.0, 3.0], min_n=5)
    assert spread is None and n == 3


def test_window_anchor_collapse_unit():
    pts = [{"lap": 3, "t": 300.0}, {"lap": 1, "t": 100.0},
           {"lap": 2, "t": 200.0}, {"lap": 2, "t": 250.0}]
    collapsed = C.collapse_laps(pts)
    assert [p["lap"] for p in collapsed] == [1, 2, 3]
    assert collapsed[1]["t"] == 250.0  # latest wins
    w = C.window(collapsed, 3, 2)
    assert [p["lap"] for p in w] == [1, 2, 3]  # inclusive both ends
    a = C.anchor(collapsed, 3, 2)
    assert a["lap"] == 1
    assert C.anchor(collapsed, 1, 3) is None


def test_usable_masking_unit():
    base = {"pit_in": False, "pit_out": False, "track": "all_clear"}
    assert C.is_usable(dict(base)) is True
    assert C.is_usable(dict(base, pit_in=True)) is False
    assert C.is_usable(dict(base, pit_out=True)) is False
    for s in ("yellow", "safety_car", "vsc", "vsc_ending", "red_flag"):
        assert C.is_usable(dict(base, track=s)) is False
    assert C.is_usable(dict(base, track=None)) is False


def test_same_ref_run_breaks_on_identity_change():
    pts = [
        {"lap": 4, "t": 400.0, "pit_in": False, "pit_out": False,
         "track": "all_clear", "gL_sec": 8.0, "gL_valid": True,
         "gL_ref": "L"},
        {"lap": 5, "t": 500.0, "pit_in": False, "pit_out": False,
         "track": "all_clear", "gL_sec": 9.0, "gL_valid": True,
         "gL_ref": "M"},  # leader changed
        {"lap": 6, "t": 600.0, "pit_in": False, "pit_out": False,
         "track": "all_clear", "gL_sec": 9.5, "gL_valid": True,
         "gL_ref": "M"},
    ]
    xs, ys = C.same_ref_run(pts, "gL_sec", "gL_valid", "gL_ref")
    assert xs == [5, 6] and ys == [9.0, 9.5]
