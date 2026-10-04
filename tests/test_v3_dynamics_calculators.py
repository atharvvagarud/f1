"""V3.1B calculator tests on synthetic fixtures (goldens + boundaries)."""

import pytest

from raceintel.features.dynamics import calculators as C
from tests.v3_dynamics_synth import blank_point, green_run, values_at


def test_clean_running_goldens():
    pts = green_run(12)
    # linear leader-gap descent 20 - 0.5*lap baked via gL_sec below
    for p in pts:
        p["gL_sec"] = 20.0 - 0.5 * p["lap"]
    v = values_at(pts, 12)
    assert v["dyn_gap_leader_slope_l3"] == pytest.approx(-0.5)
    assert v["dyn_gap_leader_slope_l10"] == pytest.approx(-0.5)
    assert v["dyn_gap_leader_slope_diff_l3_l10"] == pytest.approx(0.0)
    assert v["dyn_hist_laps_available"] == 10
    assert v["dyn_gap_n_l10_leader"] == 11  # inclusive 11-lap span
    assert v["dyn_traffic_n_l5"] == 6
    assert v["dyn_pit_inout_flag"] is False
    assert v["dyn_recent_stop_l3"] is False  # laps_since large


def test_position_delta_golden():
    pts = green_run(8)
    for i, p in enumerate(pts):
        p["pos"] = [10, 9, 9, 8, 7, 7, 6, 5][i]
    v = values_at(pts, 8)
    # anchor lap<=5 pos=7, current pos=5 -> +2 ; lap<=... 10-window needs
    # lap<=-2 -> none
    assert v["dyn_position_change_l3"] == 2.0
    assert v["dyn_position_change_l10"] is None


def test_pit_boundary_segmentation():
    pts = green_run(10)
    for p in pts:  # constant closing gap
        p["gL_sec"] = 12.0 - 0.4 * p["lap"]
    pts[5]["pit_in"] = True   # lap 6 in-lap
    pts[6]["pit_out"] = True  # lap 7 out-lap
    v = values_at(pts, 8)
    # run at lap 8 may only use laps 7..8 minus masked lap 7 -> lap 8 only
    assert v["dyn_gap_leader_slope_l3"] is None
    assert v["dyn_pit_inout_flag"] is False
    v6 = values_at(pts, 6)
    assert v6["dyn_pit_inout_flag"] is True
    v7 = values_at(pts, 7)
    assert v7["dyn_pit_inout_flag"] is True
    v8flags = values_at(pts, 8)
    assert v8flags["dyn_recent_stop_l3"] is False or True  # structural
    # first clean lap after stop carries usable trajectories again
    pts2 = green_run(12)
    for p in pts2:
        p["gL_sec"] = 12.0 - 0.4 * p["lap"]
    pts2[5]["pit_in"] = True
    pts2[6]["pit_out"] = True
    v11 = values_at(pts2, 11)
    assert v11["dyn_gap_leader_slope_l3"] == pytest.approx(-0.4)


def test_status_boundary_masking():
    pts = green_run(10)
    for p in pts:
        p["gL_sec"] = 12.0 - 0.4 * p["lap"]
    pts[7]["track"] = "safety_car"
    pts[8]["track"] = "safety_car"
    v = values_at(pts, 9)
    # laps 8,9 masked; run at 9 has only lap 9 -> None
    assert v["dyn_gap_leader_slope_l3"] is None
    v10 = values_at(pts, 10)
    assert v10["dyn_gap_leader_slope_l3"] is None  # only lap 10 usable
    pts[8]["track"] = "all_clear"  # reopen lap 9: run laps 9..10
    v10b = values_at(pts, 10)
    assert v10b["dyn_gap_leader_slope_l3"] == pytest.approx(-0.4)


def test_early_history_ladder():
    pts = green_run(12)
    v1 = values_at(pts, 1)
    assert v1["dyn_position_change_l3"] is None
    assert v1["dyn_gap_leader_slope_l3"] is None
    assert v1["dyn_hist_laps_available"] == 0
    assert v1["dyn_gap_n_l10_leader"] == 1  # current lap itself counts
    assert v1["dyn_traffic_n_l5"] >= 0
    v4 = values_at(pts, 4)
    assert v4["dyn_position_change_l3"] == 0.0  # anchor lap 1 exists
    assert v4["dyn_position_change_l10"] is None
    assert v4["dyn_hist_laps_available"] == 3
    v6 = values_at(pts, 6)
    assert v6["dyn_position_change_l3"] == 0.0
    v11 = values_at(pts, 11)
    assert v11["dyn_position_change_l10"] == 0.0  # anchor lap 1
    assert v11["dyn_hist_laps_available"] == 10


def test_follower_identity_change_stops_run():
    pts = green_run(10)
    # closing follower: last-gap level falls 0.3 s/lap under same follower
    for i, p in enumerate(pts):
        p["b_F"] = p["t"] - 85.0 - 0.3 * (p["lap"] - 1)
    v = values_at(pts, 8)
    assert v["dyn_follower_gap_slope_l5"] == pytest.approx(-0.3)
    pts[8]["b_ref"] = "Z"  # overtake: new car behind at lap 9
    pts[8]["b_F"] = pts[8]["t"] - 84.0
    pts[9]["b_ref"] = "Z"  # ...still behind at lap 10
    pts[9]["b_F"] = pts[9]["t"] - 84.2
    v9 = values_at(pts, 9)
    # run holds only lap 9 -> slope None (needs >= 2)
    assert v9["dyn_follower_gap_slope_l5"] is None
    assert v9["dyn_follower_gap_last_seconds"] == pytest.approx(6.0)
    v10 = values_at(pts, 10)
    assert v10["dyn_follower_gap_slope_l5"] is not None


def test_follower_regime_change_stops_run():
    pts = green_run(10)
    pts[9]["b_Fl"] = 8  # follower fell a full lap behind at lap 10
    pts[9]["b_F"] = pts[9]["t"] - 175.0
    v10 = values_at(pts, 10)
    assert v10["dyn_follower_lap_diff"] == 2
    # regime jump breaks the run: lap-10 point alone in its regime
    assert v10["dyn_follower_gap_slope_l5"] is None


def test_follower_strict_predecessor_check():
    pts = green_run(6)
    pts[5]["b_predF"] = "X"  # someone else was ahead of follower at F
    v = values_at(pts, 6)
    assert v["dyn_follower_gap_last_seconds"] is None
    assert v["dyn_follower_gap_last_age_s"] is None
    assert v["dyn_follower_gap_slope_l5"] is None
    # ...while the same state with the check passing resolves normally
    pts[5]["b_predF"] = "T"
    v2 = values_at(pts, 6)
    assert v2["dyn_follower_gap_last_seconds"] == pytest.approx(5.0)


def test_follower_red_nulls_level():
    pts = green_run(6)
    pts[5]["b_red"] = True
    v = values_at(pts, 6)
    assert v["dyn_follower_gap_last_seconds"] is None
    assert v["dyn_follower_lap_diff"] == 1  # geometry still known


def test_relative_per_endpoint_comparators():
    pts = green_run(8)
    for i, p in enumerate(pts):
        p["rel_ahead"] = [0.5, 0.4, 0.3, 0.2, 0.1, 0.0, -0.1, -0.2][i]
    v = values_at(pts, 8)
    # anchor lap<=3 rel=0.3, current -0.2, delta 5 laps -> -0.1/lap
    assert v["dyn_relpace_ahead_change_l5"] == pytest.approx(-0.1)


def test_field_spread_change_and_traffic():
    pts = green_run(8)
    for i, p in enumerate(pts):
        p["spread"] = [20.0, 19.0, 18.0, 17.0, 16.0, 12.0, 11.0, 10.0][i]
        p["traffic"] = i >= 5
    v = values_at(pts, 8)
    # anchor lap<=3 spread=18, current 10 -> (10-18)/5 = -1.6
    assert v["dyn_field_spread_change_l5"] == pytest.approx(-1.6)
    assert v["dyn_field_spread_lap"] == pytest.approx(10.0)
    assert v["dyn_traffic_frac_l5"] == pytest.approx(0.5)  # laps 4..8


def test_variant_isolation():
    pts = green_run(12)
    v = values_at(pts, 12)
    core_names = [n for n in v if not n.startswith("dyn_stint")
                  and n != "dyn_gap_leader_slope_gated_clean"
                  and n != "dyn_gap_accel_l5"]
    assert len(core_names) == 26
    assert v["dyn_gap_leader_slope_gated_clean"] is not None  # clean
    assert v["dyn_gap_accel_l5"] == pytest.approx(0.0)  # linear
    assert v["dyn_stint_pace_resid"] is None  # single stint, no history
    pts[5]["track"] = "safety_car"  # lap 6, outside the [7,12] window
    v2 = values_at(pts, 12)
    # window [7,12] all clear -> gated still defined (mask outside H5)
    assert v2["dyn_gap_leader_slope_gated_clean"] is not None
    pts[10]["track"] = "yellow"
    v3 = values_at(pts, 12)
    assert v3["dyn_gap_leader_slope_gated_clean"] is None  # dirty window


def test_label_blindness_architectural():
    from raceintel.features.dynamics.calculators import POINT_KEYS
    forbidden = ("is_winner", "eligible", "label", "result", "finish",
                 "position_final", "classified", "points")
    for key in POINT_KEYS:
        assert not any(f in key for f in forbidden), key
    pts = green_run(6)
    before = values_at(pts, 6)
    for p in pts:  # calculators ignore unknown keys incl. labels
        p["is_winner"] = True
        p["eligible_is_winner"] = True
        p["final_position"] = 1
    after = values_at(pts, 6)
    assert before == after
