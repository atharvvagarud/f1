"""V3.1B adversarial future-poison suite (synthetic, no corpus).

Principle: mutating information strictly after T must not change
feature(T). Cross-driver and result poisons have dedicated coverage.
"""

import copy

import pytest

from raceintel.features.dynamics import calculators as C
from tests.v3_dynamics_synth import green_run, sweep_row, values_at


def _race_points(n_laps=10):
    """Two-driver synthetic race point sets keyed by driver."""
    return {"A": green_run(n_laps), "B": green_run(n_laps)}


def _all_values(point_sets, lap):
    return {d: values_at(pts, lap) for d, pts in point_sets.items()}


def test_future_row_poison():
    ps = _race_points()
    before = _all_values(ps, 6)
    for p in ps["A"][6:] + ps["B"][6:]:  # laps 7..10 strictly after T
        p["pos"] = 20
        p["gL_sec"] = 999.0
        p["pace_m5"] = 999.0
        p["rel_field"] = 99.0
    assert _all_values(ps, 6) == before


def test_future_lap_poison():
    ps = _race_points()
    before = _all_values(ps, 6)
    for d in ps:  # append laps 11..14 with extreme values
        base_t = ps[d][-1]["t"]
        for k in range(11, 15):
            p = dict(ps[d][-1])
            p.update(lap=k, t=base_t + (k - 10) * 90.0, pos=1,
                     gL_sec=-50.0, pace_m5=50.0)
            ps[d].append(p)
    assert _all_values(ps, 6) == before


def test_future_comparator_change():
    ps = _race_points()
    for p in ps["A"]:
        p["gA_ref"] = "B"
    before = _all_values(ps, 6)
    for p in ps["A"][6:]:
        p["gA_ref"] = "C"  # future ahead-identity change
        p["rel_ahead"] = 42.0
    assert _all_values(ps, 6) == before


def test_future_pit_outcome():
    ps = _race_points()
    before = _all_values(ps, 6)
    for p in ps["A"][6:]:
        p["pit_in"] = True
        p["pit_out"] = True
        p["laps_since"] = 0
    assert _all_values(ps, 6) == before


def test_future_status_change():
    ps = _race_points()
    before = _all_values(ps, 6)
    for p in ps["A"][6:] + ps["B"][6:]:
        p["track"] = "red_flag"
    assert _all_values(ps, 6) == before


def test_future_field_membership():
    ps = _race_points()
    before = _all_values(ps, 6)
    rookies = green_run(4)
    for p in rookies:  # drivers appearing only after T
        p["t"] += 540.0
    ps["R"] = green_run(6) + rookies
    assert _all_values({d: ps[d] for d in ("A", "B")}, 6) == before


def test_future_result_poison_architectural():
    ps = _race_points()
    before = _all_values(ps, 6)
    for pts in ps.values():
        for p in pts[6:]:
            p["is_winner"] = True
            p["final_position"] = 1
            p["classified_flag"] = True
            p["scored_points"] = True
    assert _all_values(ps, 6) == before


def test_window_boundary_exactness():
    ps = _race_points(12)
    for p in ps["A"]:
        p["gL_sec"] = 20.0 - 0.5 * p["lap"]
    before = values_at(ps["A"], 10)
    # lap 4 is outside the H5 window [5,10] for the slope run... anchor
    # lap<=5 may read lap 5 only; mutating lap 4 must not change slopes
    # but mutating lap 5 (anchor/delta endpoint) may change deltas.
    for p in ps["A"]:
        if p["lap"] == 4:
            p["gL_sec"] = 555.0
            p["pos"] = 20
    assert values_at(ps["A"], 10)["dyn_gap_leader_slope_l3"] == \
        before["dyn_gap_leader_slope_l3"]
    for p in ps["A"]:
        if p["lap"] == 7:  # inside the l3 window [7,10]
            p["gL_sec"] = 555.0
    assert values_at(ps["A"], 10)["dyn_gap_leader_slope_l3"] != \
        before["dyn_gap_leader_slope_l3"]


def test_same_time_ordering_deterministic():
    rows = [sweep_row("A", lap=5, t=1000.0, pos=2),
            sweep_row("B", lap=5, t=1000.0, pos=1),
            sweep_row("A", lap=6, t=1090.0, pos=2),
            sweep_row("B", lap=6, t=1090.0, pos=1)]
    keyed = {(r["driver"], r["lap"]): s
             for r, s in zip(rows, C.sweep_race(rows))}
    rev = list(reversed(rows))
    keyed_rev = {(r["driver"], r["lap"]): s
                 for r, s in zip(rev, C.sweep_race(rev))}
    assert keyed == keyed_rev  # input order never affects per-state output


def test_early_history_boundary():
    ps = _race_points(4)
    v1 = values_at(ps["A"], 1)
    null_expected = [n for n in v1 if n not in (
        "dyn_traffic_n_l5", "dyn_hist_laps_available",
        "dyn_gap_n_l10_leader", "dyn_gap_n_l10_ahead",
        "dyn_pit_inout_flag", "dyn_recent_stop_l3",
        "dyn_follower_lap_diff", "dyn_field_spread_lap",
        "dyn_traffic_frac_l5")]
    assert all(v1[n] is None for n in null_expected)
    # levels still defined at lap 1
    assert v1["dyn_follower_gap_last_seconds"] is None  # no own history
    assert v1["dyn_follower_gap_last_age_s"] is None
    assert v1["dyn_follower_lap_diff"] == 1  # successor geometry known
    assert v1["dyn_follower_gap_slope_l5"] is None
    assert v1["dyn_field_spread_lap"] == 8.0
    assert v1["dyn_traffic_frac_l5"] == 0.0
    assert v1["dyn_hist_laps_available"] == 0
    assert v1["dyn_pit_inout_flag"] is False


def test_pit_boundary_exact():
    ps = _race_points(8)
    ps["A"][3]["pit_in"] = True   # lap 4 in-lap
    ps["A"][4]["pit_out"] = True  # lap 5 out-lap
    v4 = values_at(ps["A"], 4)
    v5 = values_at(ps["A"], 5)
    v6 = values_at(ps["A"], 6)
    assert v4["dyn_pit_inout_flag"] is True
    assert v5["dyn_pit_inout_flag"] is True
    assert v6["dyn_pit_inout_flag"] is False
    # slope at lap 6 (window [3,6]) breaks at masked laps 4,5 -> lap 6 alone
    assert v6["dyn_gap_leader_slope_l3"] is None


def test_status_boundary_exact():
    ps = _race_points(8)
    ps["A"][4]["track"] = "red_flag"  # lap 5 red
    v = values_at(ps["A"], 6)
    # window [3,6] run breaks at lap 5 -> laps 6 alone -> None
    assert v["dyn_gap_leader_slope_l3"] is None
    ps["A"][4]["track"] = "all_clear"
    assert values_at(ps["A"], 6)["dyn_gap_leader_slope_l3"] is not None


def test_cross_driver_future_poison():
    ps = _race_points()
    before = values_at(ps["A"], 6)
    for p in ps["B"][6:]:  # B strictly after T: positions, gaps, pace
        p["pos"] = 1
        p["gL_sec"] = 0.0
        p["pace_m5"] = 80.0
        p["pit_in"] = True
        p["rel_field"] = -99.0
    assert values_at(ps["A"], 6) == before

def test_cross_driver_identity_change_history():
    # overtake at lap 5 (before T=8): A's ahead ref changes causally
    ps = _race_points(10)
    for p in ps["A"][:4]:
        p["gA_ref"] = "B"
    for p in ps["A"][4:]:
        p["gA_ref"] = "C"
    v = values_at(ps["A"], 8)
    # run holds only the C segment (laps 5..8) -> slope defined
    assert v["dyn_gap_ahead_slope_l3"] is not None
    # ...while a same-ref poison after T cannot leak back
    before = dict(v)
    for p in ps["A"][8:]:
        p["gA_ref"] = "B"
    assert values_at(ps["A"], 8) == before


def test_sweep_future_poison():
    rows = [sweep_row("A", lap=k, t=100.0 * k, pos=2) for k in range(1, 7)]
    rows += [sweep_row("B", lap=k, t=105.0 * k, pos=1) for k in range(1, 7)]
    before = C.sweep_race(rows)
    poisoned = copy.deepcopy(rows)
    for r in poisoned:
        if r["t"] > 600.0:  # strictly after A's lap-6 T
            r["pos"] = 20
            r["gL_sec"] = 777.0
    after = C.sweep_race(poisoned)
    # rows at-or-before T unchanged (compare per input index)
    for b, a, r in zip(before, after, rows):
        if r["t"] <= 600.0:
            assert b == a


def test_follower_crossing_boundary_invariant():
    """V3.1A-C1 regression: follower crossing at T+eps never leaks into T.

    Target T crosses lap 6 at t=540 while the follower has not yet
    crossed lap 6 (latest: lap 5 at t=455). Adding the follower's lap-6
    crossing at T+eps must leave feature(T) bit-identical; only a later
    target state may consume it.
    """
    from tests.v3_dynamics_synth import blank_point
    ahead = [blank_point(lap=k, t=90.0 * k, driver="T", b_ref="F",
                         b_F=90.0 * k - 85.0, b_Fl=k - 1, b_predF="T",
                         b_red=False) for k in range(1, 7)]
    before = values_at(ahead, 6)
    assert before["dyn_follower_gap_last_seconds"] == pytest.approx(5.0)
    # follower crosses lap 6 at T + eps (strictly after target state)
    late = blank_point(lap=7, t=540.0 + 2.0, driver="T", b_ref="F",
                       b_F=540.0 + 0.5, b_Fl=6, b_predF="T",
                       b_red=False)
    assert values_at(ahead + [late], 6) == before
    # ...but the later state honestly consumes the new observation
    v7 = values_at(ahead + [late], 7)
    assert v7["dyn_follower_gap_last_seconds"] == pytest.approx(0.5)
    assert v7["dyn_follower_gap_last_age_s"] == pytest.approx(1.5)


def test_future_follower_crossing_poison():
    """Mutating the follower's future crossings/times never moves T."""
    ps = _race_points()
    before = values_at(ps["A"], 6)
    for p in ps["A"][6:]:  # follower provenance strictly after T
        p["b_ref"] = "Z"
        p["b_F"] = 1.0
        p["b_Fl"] = 99
        p["b_predF"] = "Q"
        p["b_red"] = True
    assert values_at(ps["A"], 6) == before


def test_follower_overtake_uses_historical_relationship():
    """Successor resolved per historical state; no T-identity retrojection.

    A leads laps 1..4 with B behind; B takes the lead at lap 5 (A now
    follows B). A's lap-4 last-gap must still reference B-as-follower
    while A's lap-6 last-gap references the new follower C.
    """
    from tests.v3_dynamics_synth import blank_point
    pts = [blank_point(lap=k, t=90.0 * k, driver="A", b_ref="B",
                       b_F=90.0 * k - 85.0, b_Fl=k - 1, b_predF="A",
                       b_red=False) for k in range(1, 5)]
    pts += [blank_point(lap=k, t=90.0 * k, driver="A", b_ref="C",
                        b_F=90.0 * k - 83.0, b_Fl=k - 1, b_predF="A",
                        b_red=False) for k in range(5, 9)]
    v4 = values_at(pts, 4)
    assert v4["dyn_follower_gap_last_seconds"] == pytest.approx(5.0)
    assert v4["dyn_follower_gap_slope_l5"] == pytest.approx(0.0)  # B run
    v6 = values_at(pts, 6)
    assert v6["dyn_follower_gap_last_seconds"] == pytest.approx(7.0)
    # slope at lap 6 spans only the C regime (laps 5..6); B history excluded
    assert v6["dyn_follower_gap_slope_l5"] == pytest.approx(0.0)
    # mutating later laps (the T-identity change) must not leak back into 4
    pts[5]["b_ref"] = "B"
    pts[5]["b_F"] = 1.0
    assert values_at(pts, 4) == v4


def test_sweep_follower_provenance_future_poison():
    """Future follower rows never move another row's sweep provenance."""
    rows = [sweep_row("A", lap=k, t=100.0 * k, pos=2) for k in range(1, 7)]
    rows += [sweep_row("B", lap=k, t=100.0 * k + 5.0, pos=1)
             for k in range(1, 7)]
    rows += [sweep_row("C", lap=k, t=100.0 * k + 8.0, pos=3)
             for k in range(1, 7)]
    before = C.sweep_race(rows)
    poisoned = copy.deepcopy(rows)
    for r in poisoned:
        if r["driver"] == "C" and r["t"] > 608.0:  # C's lap-7+ future
            r["pos"] = 1
            r["t"] += 500.0
    after = C.sweep_race(poisoned)
    for b, a, r in zip(before, after, rows):
        if r["t"] <= 600.0:
            assert b == a
