"""D9 derived temporal state + outcome label tests — synthetic, offline.

Covers (D9 mission §19/§20/§22 + §7):

- track-state code mapping (last-code semantics; null/unknown honesty);
- flag derivation consistency;
- race leader-laps at state (past-only; ties get the same value);
- race progress fraction;
- pit-history derivations (completed stops so far, laps since last stop),
  including: future stop mutation has zero effect on earlier rows; in-only /
  out-only stops are never counted; exit-lap resolution;
- stint_lap (start-side only; leak guard);
- outcome-label construction (official results facts + derived-fact flags;
  no DNF target);
- label/state physical separation and the final-result mutation boundary
  (state unchanged, labels change appropriately);
- end-to-end D9 season build over the real D6/D7 boundaries (schema/PK/
  label-separation) and a future-mutation leakage suite at a state cutoff.

No network, no FastF1, no telemetry.
"""

import pandas as pd
import pytest

from raceintel import contracts as C
from raceintel.pipeline import d6schema as D6S
from raceintel.pipeline import d7schema as D7S
from raceintel.pipeline import d9
from raceintel.pipeline import d9schema as S
from raceintel.pipeline import d6
from raceintel.pipeline import d7
from raceintel.config import V2Paths
from raceintel.errors import IngestionError

from test_v2_d6 import (  # noqa: E402
    dl_row, res_row, races_frame, write_tiera_season,
)
from test_v2_d7 import (  # noqa: E402
    WX_COLS, RC_COLS, PIT_COLS, ST_COLS, wx_row, rc_row, pit_row, stint_row,
    _pit_unit,
)

RES_COLS = [c.name for c in C.RESULTS.columns]


# ---------------------------------------------------------------------------
# Small synthetic state helpers for the pure derived functions.
# ---------------------------------------------------------------------------

def mk_state(rows):
    """rows: list of dicts with keys driver_id/lap_number/state_time_s and
    optional stint_start_lap / track_status / pit_out_s."""
    base = pd.DataFrame(rows)
    if "track_status" not in base.columns:
        base["track_status"] = None
    if "stint_start_lap" not in base.columns:
        base["stint_start_lap"] = None
    return base


# ---------------------------------------------------------------------------
# Track-state mapping (FastF1 3.7.0 code semantics).
# ---------------------------------------------------------------------------

def test_track_state_code_mapping():
    assert d9.track_state_from_status("1") == "all_clear"
    assert d9.track_state_from_status("2") == "yellow"
    assert d9.track_state_from_status("4") == "safety_car"
    assert d9.track_state_from_status("5") == "red_flag"
    assert d9.track_state_from_status("6") == "vsc"
    assert d9.track_state_from_status("7") == "vsc_ending"
    # Last-character semantics: FastF1 appends statuses chronologically.
    assert d9.last_track_status_code("124") == "4"   # SC in effect at lap end
    assert d9.last_track_status_code("41") == "1"    # cleared by lap end
    assert d9.last_track_status_code("671") == "1"
    assert d9.last_track_status_code("4") == "4"


def test_track_state_unknown_and_null_honest():
    for bad in (None, float("nan"), "", "x", "0"):
        assert d9.track_state_from_status(bad) is None
    out = d9.derive_track_state(mk_state([
        {"driver_id": "a", "lap_number": 1, "state_time_s": 100.0,
         "track_status": None},
        {"driver_id": "a", "lap_number": 2, "state_time_s": 200.0,
         "track_status": "4"},
        {"driver_id": "a", "lap_number": 3, "state_time_s": 300.0,
         "track_status": "671"},
    ]))
    # Unknown stays UNKNOWN (null), never invented as false.
    assert pd.isna(out.loc[0, "track_state"])
    assert pd.isna(out.loc[0, "flag_safety_car"])
    row_sc = out.loc[1]
    assert row_sc["track_state"] == "safety_car"
    assert row_sc["flag_safety_car"] == True  # noqa: E712
    assert row_sc["flag_yellow"] == False  # noqa: E712
    # '671' = vsc_ending then clear by the lap boundary -> all_clear.
    assert out.loc[2, "track_state"] == "all_clear"
    assert out.loc[2, "flag_vsc"] == False  # noqa: E712


def test_flag_consistency_mutual_exclusivity():
    st = pd.DataFrame({
        "track_status": ["1", "2", "4", "5", "6", "7", None]})
    out = d9.derive_track_state(st)
    known = out[out["track_state"].notna()]
    flags = known[["flag_yellow", "flag_safety_car", "flag_red",
                   "flag_vsc"]].sum(axis=1)
    expected = (known["track_state"] != "all_clear").astype(int)
    assert (flags == expected).all()


# ---------------------------------------------------------------------------
# Race progress.
# ---------------------------------------------------------------------------

def test_race_leader_laps_at_state_past_only_and_ties():
    st = pd.DataFrame({
        "driver_id": ["a", "a", "b", "b", "a"],
        "lap_number": [1, 2, 1, 2, 3],
        "state_time_s": [100.0, 205.0, 100.0, 205.0, 310.0],
    })
    out = d9.derive_race_progress(st, scheduled_laps=57)
    ll = out["race_leader_laps_at_state"]
    assert list(ll) == [1, 2, 1, 2, 3]
    # ties at the same state time receive the same leader lap value.
    assert out["race_progress_frac"].iloc[0] == pytest.approx(1 / 57)
    assert (out["race_progress_frac"] <= 1.0 + 1e-6).all()


def test_race_progress_lapped_leader_ge_driver_lap():
    # A car completing its own lap N at time t cannot have the leader at < N.
    st = pd.DataFrame({
        "driver_id": ["lead", "lapped"],
        "lap_number": [3, 2],
        "state_time_s": [100.0, 120.0],
    })
    out = d9.derive_race_progress(st, scheduled_laps=58)
    # At t=120 the leader has completed 3 laps -> lapped row sees 3 >= 2.
    assert out.loc[1, "race_leader_laps_at_state"] == 3
    assert (out["race_leader_laps_at_state"] >= out["lap_number"]).all()


def test_race_progress_null_scheduled():
    st = pd.DataFrame({"driver_id": ["a"], "lap_number": [1],
                       "state_time_s": [100.0]})
    out = d9.derive_race_progress(st, scheduled_laps=None)
    assert out.loc[0, "race_leader_laps_at_state"] == 1
    assert pd.isna(out.loc[0, "race_progress_frac"])


# ---------------------------------------------------------------------------
# Pit-history derivations (already-observed only).
# ---------------------------------------------------------------------------

def _state_with_pit_markers():
    return pd.DataFrame([
        {"driver_id": "a", "lap_number": 1, "state_time_s": 100.0,
         "pit_out_s": None},
        {"driver_id": "a", "lap_number": 2, "state_time_s": 200.0,
         "pit_out_s": 195.0},   # full-stop exit marker on lap 2
        {"driver_id": "a", "lap_number": 3, "state_time_s": 300.0,
         "pit_out_s": None},
        {"driver_id": "b", "lap_number": 1, "state_time_s": 105.0,
         "pit_out_s": None},
    ])


def _full_pits():
    return pd.DataFrame([
        {"race_id": "r", "driver_id": "a", "stop_sequence": 1,
         "lap_number": 2, "pit_in_s": 150.0, "pit_out_s": 195.0,
         "duration_s": 45.0},
    ])


def test_pit_completed_so_far_and_laps_since():
    st = _state_with_pit_markers()
    out = d9.derive_pit_history_state(st, _full_pits())
    a = out[out["driver_id"] == "a"]
    assert list(a["pit_stops_completed_so_far"]) == [0, 1, 1]
    # laps since the exit lap (lap 2): lap2 -> 0, lap3 -> 1.
    assert a["laps_since_last_pit_stop"].iloc[0] is pd.NA
    assert a["laps_since_last_pit_stop"].iloc[1] == 0
    assert a["laps_since_last_pit_stop"].iloc[2] == 1
    b = out[out["driver_id"] == "b"]
    assert b["pit_stops_completed_so_far"].iloc[0] == 0
    assert b["laps_since_last_pit_stop"].iloc[0] is pd.NA


def test_pit_future_stop_mutation_does_not_change_earlier_state():
    # state includes a future lap-4 marker so a future FULL stop is resolvable.
    st = pd.DataFrame([
        {"driver_id": "a", "lap_number": 1, "state_time_s": 100.0,
         "pit_out_s": None},
        {"driver_id": "a", "lap_number": 2, "state_time_s": 200.0,
         "pit_out_s": 195.0},
        {"driver_id": "a", "lap_number": 3, "state_time_s": 300.0,
         "pit_out_s": None},
        {"driver_id": "a", "lap_number": 4, "state_time_s": 550.0,
         "pit_out_s": 545.0},  # future full-stop exit marker
    ])
    base_stops = pd.DataFrame([pit_row("r", "a", 1, 2, 150.0, 195.0)],
                              columns=["race_id", "driver_id",
                                       "stop_sequence", "lap_number",
                                       "pit_in_s", "pit_out_s", "duration_s"])
    base = d9.derive_pit_history_state(st.copy(), base_stops)
    future = pd.concat([base_stops, pd.DataFrame(
        [pit_row("r", "a", 2, 4, 480.0, 545.0)], columns=[
            "race_id", "driver_id", "stop_sequence", "lap_number",
            "pit_in_s", "pit_out_s", "duration_s"])], ignore_index=True)
    mutated = d9.derive_pit_history_state(st.copy(), future)
    # rows with state_time <= 300 unchanged (future stop at 545 cannot leak).
    for col in ("pit_stops_completed_so_far", "laps_since_last_pit_stop"):
        pd.testing.assert_series_equal(
            base[base["state_time_s"] <= 300.0][col].reset_index(drop=True),
            mutated[mutated["state_time_s"] <= 300.0][col].reset_index(drop=True))
    # ... while the future lap-4 row itself reflects the added stop.
    assert mutated.loc[mutated["lap_number"] == 4,
                       "pit_stops_completed_so_far"].iloc[0] == 2


def test_pit_asymmetric_stops_never_counted_as_completed():
    # in-only (entry, no exit) and out-only (exit, no entry) must not count.
    st = pd.DataFrame([
        {"driver_id": "a", "lap_number": 1, "state_time_s": 100.0,
         "pit_out_s": None},
        {"driver_id": "a", "lap_number": 2, "state_time_s": 200.0,
         "pit_out_s": None},
    ])
    pits = pd.DataFrame([
        {"race_id": "r", "driver_id": "a", "stop_sequence": 1,
         "lap_number": 1, "pit_in_s": 90.0, "pit_out_s": None,
         "duration_s": None},  # in-only (retired in pits)
        {"race_id": "r", "driver_id": "a", "stop_sequence": 2,
         "lap_number": None, "pit_in_s": None, "pit_out_s": 60.0,
         "duration_s": None},  # out-only (pit-lane start)
    ])
    out = d9.derive_pit_history_state(st, pits)
    assert (out["pit_stops_completed_so_far"] == 0).all()
    assert out["laps_since_last_pit_stop"].isna().all()


def test_pit_unresolvable_full_exit_is_loud():
    # A full stop whose exit time has no canonical exit-lap marker must fail
    # loudly rather than guess an exit lap.
    st = pd.DataFrame([
        {"driver_id": "a", "lap_number": 1, "state_time_s": 100.0,
         "pit_out_s": None},
    ])
    pits = pd.DataFrame([
        {"race_id": "r", "driver_id": "a", "stop_sequence": 1,
         "lap_number": 1, "pit_in_s": 50.0, "pit_out_s": 70.0,
         "duration_s": 20.0},
    ])
    with pytest.raises(IngestionError):
        d9.derive_pit_history_state(st, pits)


# ---------------------------------------------------------------------------
# Stint lap (start side only; guard).
# ---------------------------------------------------------------------------

def test_stint_lap_start_side_only():
    st = pd.DataFrame([
        {"driver_id": "a", "lap_number": 1, "state_time_s": 100.0,
         "stint_start_lap": 1},
        {"driver_id": "a", "lap_number": 2, "state_time_s": 200.0,
         "stint_start_lap": 1},
        {"driver_id": "a", "lap_number": 3, "state_time_s": 300.0,
         "stint_start_lap": 3},
    ])
    out = d9.derive_stint_lap(st)
    assert list(out["stint_lap"]) == [1, 2, 1]


def test_stint_lap_guard_start_after_lap_null():
    st = pd.DataFrame([
        {"driver_id": "a", "lap_number": 1, "state_time_s": 100.0,
         "stint_start_lap": 5},  # impossible: stint starts in the future
    ])
    out = d9.derive_stint_lap(st)
    assert out["stint_lap"].iloc[0] is pd.NA


# ---------------------------------------------------------------------------
# Outcome labels (official result evidence; no DNF target).
# ---------------------------------------------------------------------------

def _results_frame():
    return pd.DataFrame([
        res_row("2023-r01-R", "max_verstappen", "VER", 1, "red_bull",
                position=1, points=25.0, laps=57),
        res_row("2023-r01-R", "perez", "PER", 11, "red_bull", position=2,
                class_pos="2", points=18.0, laps=57),
        res_row("2023-r01-R", "leclerc", "LEC", 16, "ferrari", position=3,
                class_pos="3", points=15.0, laps=57),
        res_row("2023-r01-R", "zho_guanyu", "ZHO", 24, "sauber", position=20,
                class_pos="20", points=0.0, laps=56),
        res_row("2023-r01-R", "bottas", "BOT", 77, "alfa", position=None,
                class_pos="R", status="Retired", points=0.0, laps=20),
    ], columns=RES_COLS)


def test_labels_from_results_facts_and_flags():
    out = d9.labels_from_results(_results_frame())
    assert len(out) == 5
    assert out.duplicated(subset=["race_id", "driver_id"]).sum() == 0
    # factual outcomes verbatim from official results.
    row = out[out["driver_id"] == "max_verstappen"].iloc[0]
    assert row["position_final"] == 1
    assert row["winner_flag"] == True
    assert row["podium_flag"] == True
    assert row["points_finish_flag"] == True
    assert row["classified_flag"] == True
    pod = out[out["driver_id"] == "perez"].iloc[0]
    assert pod["podium_flag"] == True
    # unclassified retirement: classified fact false, position null.
    bot = out[out["driver_id"] == "bottas"].iloc[0]
    assert pd.isna(bot["position_final"])
    assert bot["classified_flag"] == False
    assert pd.isna(bot["winner_flag"]) and pd.isna(bot["podium_flag"])
    assert bot["points_finish_flag"] == False
    # NO binary DNF target column exists (deferred decision).
    assert "dnf_flag" not in out.columns
    assert "dnf" not in [c for c in out.columns if "dnf" in c]
    # Official results only — never derived from the final observed lap.
    assert "position_final" in out.columns
    assert not any("lap" in c for c in out.columns if c != "laps_completed")


def test_labels_final_result_mutation_changes_labels_not_state():
    # Label artifact is derived from official results: mutate results and the
    # label outcome follows; the derived state never sees outcome columns.
    labels = d9.labels_from_results(_results_frame())
    flipped = _results_frame().copy()
    idx = flipped["driver_id"] == "perez"
    flipped.loc[idx, ["position_final", "classified_position", "points"]] = \
        [3, 3.0, 15.0]
    labels2 = d9.labels_from_results(flipped)
    assert (labels2.loc[labels2["driver_id"] == "perez", "winner_flag"]
            .iloc[0] == False)
    assert labels["position_final"].dtype == labels2["position_final"].dtype
    # State table columns contain none of the label outcome columns.
    assert not (set(S.STATE_COLUMNS) & set(labels.columns) - {
        "race_id", "season", "driver_id", "driver_abbreviation"})


# ---------------------------------------------------------------------------
# End-to-end D9 build over the D6 -> D7 boundaries + leakage suite.
# ---------------------------------------------------------------------------

def _build_d9_unit(tmp_path, unit):
    paths = V2Paths.from_root(tmp_path)
    season = unit["season"]
    write_tiera_season(paths, season, [unit])
    d6.build_season(paths, season)
    d7.build_dataset(paths, seasons=[season], write_artifacts=True)
    report = d9.build_dataset(paths, seasons=[season], write_artifacts=True)
    return paths, report


def _fresh_scenario_unit():
    """VER: 4 laps; full pit stop lap 2 (in 150/out 175), a second full stop
    on lap 4 (in 340/out 360); track-status variety; PER/LEC non-stoppers.
    Official results with a winner and a classified retiree."""
    from test_v2_d6 import normal_race
    unit = normal_race(total_laps=4)
    race_id = unit["race_id"]
    laps = unit["driver_laps"].copy()
    # give VER a lap 4 row
    lap_cols = [c.name for c in C.DRIVER_LAPS.columns]
    laps = pd.concat([laps, pd.DataFrame(
        [dl_row(race_id, "max_verstappen", 4, position=1.0, stint=2,
                tyre_life=2.0)], columns=lap_cols)], ignore_index=True)
    v = laps["driver_id"] == "max_verstappen"
    laps.loc[v & (laps["lap_number"] == 2), "track_status"] = "4"  # SC
    laps.loc[v & (laps["lap_number"] == 2), "pit_in_s"] = 150.0
    laps.loc[v & (laps["lap_number"] == 2), "pit_out_s"] = 175.0
    laps.loc[v & (laps["lap_number"] == 3), "track_status"] = "5"  # red flag
    laps.loc[v & (laps["lap_number"] == 3), "stint_number"] = 2.0
    laps.loc[v & (laps["lap_number"] == 3), "compound"] = "HARD"
    laps.loc[v & (laps["lap_number"] == 4), "stint_number"] = 2.0
    laps.loc[v & (laps["lap_number"] == 4), "compound"] = "HARD"
    laps.loc[v & (laps["lap_number"] == 4), "pit_in_s"] = 340.0
    laps.loc[v & (laps["lap_number"] == 4), "pit_out_s"] = 360.0
    unit["driver_laps"] = laps
    pit_cols = ["race_id", "driver_id", "stop_sequence", "lap_number",
                "pit_in_s", "pit_out_s", "duration_s"]
    unit["pit_stops"] = pd.DataFrame([
        pit_row(race_id, "max_verstappen", 1, 2, 150.0, 175.0),
        pit_row(race_id, "max_verstappen", 2, 4, 340.0, 360.0),
    ], columns=pit_cols)
    stint_cols = ["race_id", "driver_id", "stint_number", "compound",
                  "fresh_tyre", "start_lap", "end_lap", "tyre_age_at_start",
                  "pit_in_lap", "pit_out_lap"]
    unit["stints"] = pd.DataFrame([
        stint_row(race_id, "max_verstappen", 1, "SOFT", False, 1, 2, 0,
                  pit_out_lap=2),
        stint_row(race_id, "max_verstappen", 2, "HARD", False, 3, 4, 1,
                  pit_in_lap=2),
        stint_row(race_id, "perez", 1, "SOFT", False, 1, 2, 0),
    ], columns=stint_cols)
    unit["weather"] = pd.DataFrame([], columns=WX_COLS)
    unit["race_control"] = pd.DataFrame([], columns=RC_COLS)
    return unit


def test_e2e_d9_build_reconciliation_schema_and_separation(tmp_path):
    unit = _fresh_scenario_unit()
    paths, report = _build_d9_unit(tmp_path, unit)
    base_d7 = d7.read_enriched_season(paths, 2023)
    st = d9.read_d9_state_season(paths, 2023)
    assert report["state_rows"] == len(base_d7) == len(st)
    assert list(st.columns) == S.STATE_COLUMNS
    # first 61 columns == D7 enriched columns verbatim
    assert list(st.columns[:len(D7S.ENRICHED_COLUMNS)]) == D7S.ENRICHED_COLUMNS
    assert st.duplicated(subset=["race_id", "driver_id",
                                 "lap_number"]).sum() == 0
    # label artifact separate, correct grain.
    lb = d9.read_d9_label_season(paths, 2023)
    assert list(lb.columns) == S.LABEL_COLUMNS
    assert lb.duplicated(subset=["race_id", "driver_id"]).sum() == 0
    assert len(lb) == len(unit["results"])
    # label separation: no outcome column in state.
    labels = set(S.LABEL_COLUMNS)
    assert not (set(st.columns) & labels - {"race_id", "season", "driver_id",
                                            "driver_abbreviation"})
    # track flags present in the cumulative state.
    ver = st[st["driver_id"] == "max_verstappen"]
    assert ver.loc[ver["lap_number"] == 2, "track_state"].iloc[0] \
        == "safety_car"
    assert ver.loc[ver["lap_number"] == 3, "track_state"].iloc[0] == "red_flag"
    # derived fields
    row2 = ver[ver["lap_number"] == 2].iloc[0]
    assert row2["pit_stops_completed_so_far"] == 1
    assert row2["laps_since_last_pit_stop"] == 0
    val = d9.validate_dataset(paths, seasons=[2023])
    assert val["integrity_ok"] == True
    assert val["label_columns_in_state"] == []


def test_e2e_final_result_mutation_changes_labels_but_not_state(tmp_path):
    unit = _fresh_scenario_unit()
    paths, report = _build_d9_unit(tmp_path, unit)
    st_before = d9.read_d9_state_season(paths, 2023)
    lb_before = d9.read_d9_label_season(paths, 2023)
    # Mutate the official final results: PER becomes the winner.
    res = unit["results"].copy()
    res.loc[res["driver_id"] == "max_verstappen",
            ["position_final", "classified_position", "points"]] = \
        [2, 2.0, 18.0]
    res.loc[res["driver_id"] == "perez",
            ["position_final", "classified_position", "points"]] = \
        [1, 1.0, 25.0]
    write_tiera_season(paths, 2023, [{**unit, "results": res}])
    # rebuild D6/D7/D9 with the mutated results
    d6.build_season(paths, 2023)
    d7.build_dataset(paths, seasons=[2023], write_artifacts=True)
    d9.build_dataset(paths, seasons=[2023], write_artifacts=True)
    st_after = d9.read_d9_state_season(paths, 2023)
    lb_after = d9.read_d9_label_season(paths, 2023)
    # STATE unchanged (official results never enter the state construction).
    pd.testing.assert_frame_equal(st_before, st_after)
    # LABELS changed appropriately.
    assert lb_before.loc[lb_before["driver_id"] == "max_verstappen",
                         "winner_flag"].iloc[0] == True
    assert lb_after.loc[lb_after["driver_id"] == "perez",
                        "winner_flag"].iloc[0] == True
    assert lb_after.loc[lb_after["driver_id"] == "max_verstappen",
                        "winner_flag"].iloc[0] == False


def test_e2e_future_mutation_suite_earlier_derived_state_identical(tmp_path):
    unit = _fresh_scenario_unit()
    paths, report = _build_d9_unit(tmp_path, unit)
    st_before = d9.read_d9_state_season(paths, 2023)
    # Mutate everything strictly after cutoff T=190s: future laps (track
    # state, stint start, clocks), the future pit stop, and final results.
    st_mut = d7.read_enriched_season(paths, 2023).copy()
    future = st_mut["state_time_s"] > 190.0
    st_mut.loc[future, "state_time_s"] += 1e6
    st_mut.loc[future, "track_status"] = "5"   # absurd future red flags
    st_mut.loc[future, "stint_start_lap"] = 99
    d7_dest = d9.dest_for_unit(paths.processed_dir, D7S.STATE_ENTITY, 2023,
                               D7S.d7_unit_id(2023))
    from raceintel.storage import atomic_write_parquet
    atomic_write_parquet(st_mut, d7_dest)
    # delete the future (lap-4) pit stop entirely
    pits = unit["pit_stops"][
        unit["pit_stops"]["stop_sequence"] != 2].reset_index(drop=True)
    atomic_write_parquet(pits, d9.dest_for_unit(paths.processed_dir,
                                                "pit_stops", 2023,
                                                unit["race_id"]))
    d9.build_dataset(paths, seasons=[2023], write_artifacts=True)
    st_after = d9.read_d9_state_season(paths, 2023)
    before = st_before[st_before["state_time_s"] <= 190.0]
    after = st_after[st_after["state_time_s"] <= 190.0]
    assert len(before) == len(after) > 0
    pd.testing.assert_frame_equal(
        before.sort_values(["race_id", "driver_id", "lap_number"],
                           kind="mergesort").reset_index(drop=True),
        after.sort_values(["race_id", "driver_id", "lap_number"],
                          kind="mergesort").reset_index(drop=True))


def test_e2e_determinism_shuffled_sources(tmp_path):
    unit = _fresh_scenario_unit()
    # shuffle source order before the D5-style write (must not matter)
    unit["stints"] = unit["stints"].sample(frac=1.0, random_state=2) \
        .reset_index(drop=True)
    unit["pit_stops"] = unit["pit_stops"].sample(frac=1.0, random_state=3) \
        .reset_index(drop=True)
    unit["results"] = unit["results"].sample(frac=1.0, random_state=4) \
        .reset_index(drop=True)
    paths, report = _build_d9_unit(tmp_path, unit)
    dest = d9.dest_for_unit(paths.processed_dir, S.STATE_ENTITY, 2023,
                            S.d9_unit_id(2023))
    b1 = dest.read_bytes()
    ldest = d9.dest_for_unit(paths.processed_dir, S.LABEL_ENTITY, 2023,
                             S.d9_unit_id(2023))
    lb1 = ldest.read_bytes()
    report2 = d9.build_dataset(paths, seasons=[2023], write_artifacts=True)
    assert report["state_rows"] == report2["state_rows"]
    assert report["label_rows"] == report2["label_rows"]
    assert dest.read_bytes() == b1
    assert ldest.read_bytes() == lb1
