"""D7 temporally-enriched state tests — synthetic, offline, no network.

Covers the D7 mission's mandatory temporal tests over deterministic fixtures:

- weather as-of: A (before attaches), B (exact state time attaches), C (after
  does NOT attach), D (no prior -> null), E (delete/mutate future obs ->
  earlier state identical), F (close future obs ignored by earlier state),
  G (source order shuffled -> same result) + observed_at_s <= state_time_s
  assert on every non-null real attachment;
- race-control: latest timestamped at/before; untimestamped messages never
  invented into history; future message cannot affect earlier state;
- pit history: as-of entries/exits; future pit event mutation/deletion/
  addition leaves earlier state unchanged; same-lap boundary; asymmetric
  in-only / out-only boundaries preserved; no future exposure;
- stint context: start-side facts only; mutating eventual stint end / future
  compound cannot affect earlier in-stint state; no tyre-age backfill;
- row-grain preservation + PK uniqueness on every enrichment;
- source ordering shuffles -> identical enriched output (determinism);
- a consolidated FUTURE-MUTATION leakage suite at a state cutoff T across
  weather / race-control / pit / stint / future-lap / final-result sources.

FastF1 is never imported. Fixtures reuse the verified D6 test builders
(``test_v2_d6``) so the D7 base rows are built through the real D6 canonical
construction boundary.
"""

import pandas as pd
import pytest

from raceintel import contracts as C
from raceintel.pipeline import d6schema as D6S
from raceintel.pipeline import d7
from raceintel.pipeline import d7schema as S
from raceintel.pipeline import d6
from raceintel.config import V2Paths
from raceintel.errors import ErrorCategory, IngestionError

# Reuse the verified D6 fixture builders (same construction boundary).
from test_v2_d6 import (  # noqa: E402
    LAP_COLS, RES_COLS, RACE_COLS, dl_row, res_row, races_frame,
    write_tiera_season, normal_race,
)

WX_COLS = [c.name for c in C.WEATHER.columns]
RC_COLS = [c.name for c in C.RACE_CONTROL.columns]
PIT_COLS = [c.name for c in C.PIT_STOPS.columns]
ST_COLS = [c.name for c in C.STINTS.columns]


def wx_row(race_id, observed_at_s, air=30.0, track=40.0, hum=20.0,
           press=1015.0, wind=1.0, wdir=180.0, rain=False):
    return {"race_id": race_id, "observed_at_s": observed_at_s,
            "air_temp_c": air, "track_temp_c": track, "humidity_pct": hum,
            "pressure_hpa": press, "wind_speed": wind,
            "wind_direction_deg": wdir, "rainfall": rain}


def rc_row(race_id, seq, observed_at_s, lap, category="Other", flag=None,
           message="M"):
    return {"race_id": race_id, "message_seq": seq,
            "observed_at_s": observed_at_s, "lap_number": lap,
            "category": category, "flag": flag, "status": None,
            "scope": None, "sector": None, "racing_number": None,
            "message_text": message}


def pit_row(race_id, driver, seq, lap, pit_in_s, pit_out_s):
    duration = (None if pit_in_s is None or pit_out_s is None
                else pit_out_s - pit_in_s)
    return {"race_id": race_id, "driver_id": driver,
            "stop_sequence": seq, "lap_number": lap, "pit_in_s": pit_in_s,
            "pit_out_s": pit_out_s, "duration_s": duration}


def stint_row(race_id, driver, stint_number, compound, fresh, start_lap,
              end_lap, age_at_start, pit_in_lap=None, pit_out_lap=None):
    return {"race_id": race_id, "driver_id": driver,
            "stint_number": stint_number, "compound": compound,
            "fresh_tyre": fresh, "start_lap": start_lap, "end_lap": end_lap,
            "tyre_age_at_start": age_at_start, "pit_in_lap": pit_in_lap,
            "pit_out_lap": pit_out_lap}


def _default_state_times():
    # normal_race uses lap_time 95.0 starting at 0 -> session end = lap*95.
    return {1: 95.0, 2: 190.0, 3: 285.0}


def _canonical_state(paths, season=2023):
    return d6.read_state_season(paths, season)


def _build_fixture(tmp_path, unit):
    paths = V2Paths.from_root(tmp_path)
    season = unit["season"]
    write_tiera_season(paths, season, [unit])
    stats = d6.build_season(paths, season)
    return paths, stats


def _state_subset_lte(st, t):
    return st[st["state_time_s"] <= t + 1e-6].reset_index(drop=True)


def _wx_block(st):
    cols = [c for c in st.columns if c.startswith("wx_") or c == "__d7_idx"]
    return st[cols]


# ==========================================================================
# Weather as-of (mission §5) — A/B/C/D + G over the canonical fixture.
# ==========================================================================

@pytest.fixture
def weather_unit(tmp_path):
    """A canonical normal race plus one deterministic weather observation at
    observed_at_s=140.0 (before lap-2 state time 190, after lap-1 95)."""
    unit = normal_race(total_laps=3)
    unit["weather"] = pd.DataFrame(
        [wx_row(unit["race_id"], 140.0)], columns=WX_COLS)
    paths, stats = _build_fixture(tmp_path, unit)
    st = _canonical_state(paths, 2023)
    return {"unit": unit, "paths": paths, "state": st}


def test_weather_A_observation_before_state_attaches(weather_unit):
    st = weather_unit["state"]
    out, _ = d7.attach_weather_asof(st.copy(), weather_unit["unit"]["weather"])
    # state time 95 (lap1): obs 140 is in the FUTURE -> no attach.
    assert out.loc[out["state_time_s"] == 95.0,
                   "wx_observed_at_s"].isna().all()
    # state time 190/285: obs 140 <= state -> attaches.
    attached = out[out["state_time_s"] >= 190.0]
    assert (attached["wx_observed_at_s"] == 140.0).all()
    assert (attached["wx_air_temp_c"] == 30.0).all()


def test_weather_B_observation_exactly_at_state_attaches(tmp_path):
    unit = normal_race(total_laps=3)
    unit["weather"] = pd.DataFrame([wx_row(unit["race_id"], 95.0)],
                                   columns=WX_COLS)
    paths, _ = _build_fixture(tmp_path, unit)
    st = _canonical_state(paths)
    out, _ = d7.attach_weather_asof(st.copy(), unit["weather"])
    row = out[out["state_time_s"] == 95.0].iloc[0]
    assert row["wx_observed_at_s"] == 95.0  # exact match attaches
    assert row["wx_age_s"] == 0.0


def test_weather_C_observation_after_state_does_not_attach(tmp_path):
    unit = normal_race(total_laps=3)
    unit["weather"] = pd.DataFrame([wx_row(unit["race_id"], 96.0)],
                                   columns=WX_COLS)
    paths, _ = _build_fixture(tmp_path, unit)
    st = _canonical_state(paths)
    out, _ = d7.attach_weather_asof(st.copy(), unit["weather"])
    # state time 95 < 96: no prior observation -> null on every lap-1 row.
    assert out.loc[out["state_time_s"] == 95.0,
                   "wx_observed_at_s"].isna().all()
    # later states attach the 96.0 obs.
    assert (out.loc[out["state_time_s"] >= 190.0,
                    "wx_observed_at_s"] == 96.0).all()


def test_weather_D_no_prior_observation_is_null(tmp_path):
    unit = normal_race(total_laps=3)
    unit["weather"] = pd.DataFrame([], columns=WX_COLS)
    paths, _ = _build_fixture(tmp_path, unit)
    st = _canonical_state(paths)
    out, _ = d7.attach_weather_asof(st.copy(), unit["weather"])
    assert out["wx_observed_at_s"].isna().all()
    assert out["wx_air_temp_c"].isna().all()
    assert out["wx_rainfall"].isna().all()


def test_weather_E_delete_mutate_future_obs_earlier_state_identical(
        weather_unit):
    st = weather_unit["state"]
    base_wx = weather_unit["unit"]["weather"]
    before, _ = d7.attach_weather_asof(st.copy(), base_wx)
    # Add an extreme future observation, then delete every future observation
    # strictly after T=190. Earlier state (<=190) must be unchanged.
    future = pd.concat([
        base_wx,
        pd.DataFrame([wx_row(weather_unit["unit"]["race_id"], 1e6, air=-99.0,
                             track=-99.0, rain=True)], columns=WX_COLS)],
        ignore_index=True)
    mutated, _ = d7.attach_weather_asof(st.copy(), future)
    mutated_drop, _ = d7.attach_weather_asof(
        st.copy(), future[future["observed_at_s"] <= 190.0])
    pd.testing.assert_frame_equal(
        _state_subset_lte(before, 190.0).reset_index(drop=True),
        _state_subset_lte(mutated, 190.0).reset_index(drop=True))
    pd.testing.assert_frame_equal(
        _state_subset_lte(mutated_drop, 190.0).reset_index(drop=True),
        _state_subset_lte(before, 190.0).reset_index(drop=True))


def test_weather_F_close_future_obs_ignored_by_earlier_state(weather_unit):
    st = weather_unit["state"]
    base_wx = weather_unit["unit"]["weather"]  # obs at 140
    before, _ = d7.attach_weather_asof(st.copy(), base_wx)
    close_future = pd.concat([
        base_wx,
        pd.DataFrame([wx_row(weather_unit["unit"]["race_id"], 190.5,
                             air=-1.0, track=-1.0, rain=True)],
                     columns=WX_COLS)],
        ignore_index=True)
    after, _ = d7.attach_weather_asof(st.copy(), close_future)
    # state time 190 still uses the older past obs (140), not the close
    # future obs 190.5 (which only attaches from the next state onward).
    earlier = _state_subset_lte(after, 190.0)
    at190 = earlier[earlier["state_time_s"] == 190.0]
    assert (at190["wx_observed_at_s"] == 140.0).all()
    assert (at190["wx_air_temp_c"] == 30.0).all()
    pd.testing.assert_frame_equal(
        _state_subset_lte(before, 190.0).reset_index(drop=True),
        earlier.reset_index(drop=True))


def test_weather_G_shuffled_source_same_result(weather_unit):
    st = weather_unit["state"]
    base = weather_unit["unit"]["weather"]
    many = pd.concat([base, pd.DataFrame(
        [wx_row(weather_unit["unit"]["race_id"], 50.0, air=35.0),
         wx_row(weather_unit["unit"]["race_id"], 200.0, air=20.0,
                track=30.0, rain=True)],
        columns=WX_COLS)], ignore_index=True)
    out1, _ = d7.attach_weather_asof(st.copy(), many)
    shuffled = many.sample(frac=1.0, random_state=0).reset_index(drop=True)
    out2, _ = d7.attach_weather_asof(st.copy(), shuffled)
    pd.testing.assert_frame_equal(
        out1.sort_values("__d7_idx").reset_index(drop=True),
        out2.sort_values("__d7_idx").reset_index(drop=True))


def test_weather_real_attachment_time_bound_holds(weather_unit):
    """Every non-null attachment must satisfy observed_at_s <= state_time_s."""
    st = weather_unit["state"]
    out, _ = d7.attach_weather_asof(st.copy(), weather_unit["unit"]["weather"])
    both = out[out["wx_observed_at_s"].notna()]
    assert (both["wx_observed_at_s"] <= both["state_time_s"] + 1e-6).all()
    assert (both["wx_age_s"] >= -1e-6).all()
    assert len(out) == len(st)


# ==========================================================================
# Weather row-grain preservation + duplicate weather PK is loud.
# ==========================================================================

def test_weather_attach_preserves_row_count_and_pk(tmp_path):
    unit = normal_race(total_laps=3)
    unit["weather"] = pd.DataFrame(
        [wx_row(unit["race_id"], 50.0), wx_row(unit["race_id"], 140.0)],
        columns=WX_COLS)
    paths, _ = _build_fixture(tmp_path, unit)
    st = _canonical_state(paths)
    out, _ = d7.attach_weather_asof(st.copy(), unit["weather"])
    assert len(out) == len(st)
    assert out.duplicated(subset=["__d7_idx"]).sum() == 0


def test_duplicate_weather_timestamp_is_loud(tmp_path):
    unit = normal_race(total_laps=3)
    unit["weather"] = pd.DataFrame(
        [wx_row(unit["race_id"], 50.0), wx_row(unit["race_id"], 50.0)],
        columns=WX_COLS)
    paths, _ = _build_fixture(tmp_path, unit)
    st = _canonical_state(paths)
    with pytest.raises(IngestionError) as excinfo:
        d7.attach_weather_asof(st.copy(), unit["weather"])
    assert excinfo.value.category is ErrorCategory.VALIDATION


# ==========================================================================
# Race control (mission §6/§7).
# ==========================================================================

def _rc_unit(tmp_path, with_untimed=True):
    unit = normal_race(total_laps=3)
    rows = [rc_row(unit["race_id"], 0, 50.0, 1, category="Flag",
                   flag="GREEN", message="TRACK CLEAR")]
    if with_untimed:
        rows.append(rc_row(unit["race_id"], 1, None, 1, category="Flag",
                           flag="YELLOW", message="NO SOURCE TIME"))
    unit["race_control"] = pd.DataFrame(rows, columns=RC_COLS)
    paths, _ = _build_fixture(tmp_path, unit)
    return unit, paths


def test_rc_latest_timestamped_message_attaches(tmp_path):
    unit, paths = _rc_unit(tmp_path)
    st = _canonical_state(paths)
    out, notes = d7.attach_race_control_asof(st.copy(), unit["race_control"])
    # seq0 at 50s attaches to every state (all > 50).
    assert (out["rc_last_message_seq"] == 0).all()
    assert (out["rc_last_message_category"] == "Flag").all()
    assert (out["rc_last_message_observed_at_s"] <=
            out["state_time_s"] + 1e-6).all()
    assert any("untimestamped" in n for n in notes)


def test_rc_future_message_does_not_attach(tmp_path):
    unit = normal_race(total_laps=3)
    unit["race_control"] = pd.DataFrame(
        [rc_row(unit["race_id"], 0, 50.0, 1, message="EARLY"),
         rc_row(unit["race_id"], 1, 100.0, 2, category="SafetyCar",
                flag="SC", message="SC DEPLOYED")], columns=RC_COLS)
    paths, _ = _build_fixture(tmp_path, unit)
    st = _canonical_state(paths)
    out, _ = d7.attach_race_control_asof(st.copy(), unit["race_control"])
    # lap-1 rows (t=95) see only seq0; lap-2/3 (t>=190) see seq1.
    lap1 = out[out["state_time_s"] == 95.0]
    assert (lap1["rc_last_message_seq"] == 0).all()
    later = out[out["state_time_s"] >= 190.0]
    assert (later["rc_last_message_seq"] == 1).all()


def test_rc_untimed_messages_never_invented_into_history(tmp_path):
    unit, paths = _rc_unit(tmp_path)  # seq1 has observed_at_s=None
    st = _canonical_state(paths)
    out, notes = d7.attach_race_control_asof(st.copy(), unit["race_control"])
    assert set(out["rc_last_message_seq"].dropna().unique()) == {0}
    assert set(out["rc_last_message_flag"].dropna().unique()) == {"GREEN"}
    assert "YELLOW" not in set(out["rc_last_message_flag"].dropna())
    # The untimed source message remains present and untouched in the source.
    rc_src = pd.read_parquet(d7.dest_for_unit(
        paths.processed_dir, "race_control", 2023, unit["race_id"]))
    assert int(rc_src["observed_at_s"].isna().sum()) == 1


def test_rc_mutating_untimed_message_text_does_not_change_state(tmp_path):
    unit, paths = _rc_unit(tmp_path)
    st = _canonical_state(paths)
    before, _ = d7.attach_race_control_asof(st.copy(), unit["race_control"])
    unit["race_control"].loc[1, "message_text"] = "FABRICATED"
    unit["race_control"].loc[1, "category"] = "SafetyCar"
    after, _ = d7.attach_race_control_asof(st.copy(),
                                           unit["race_control"])
    pd.testing.assert_frame_equal(before, after)


def test_rc_ties_broken_deterministically_by_source_order(tmp_path):
    unit = normal_race(total_laps=3)
    unit["race_control"] = pd.DataFrame(
        [rc_row(unit["race_id"], 0, 50.0, 1, message="first"),
         rc_row(unit["race_id"], 1, 50.0, 1, message="second")],
        columns=RC_COLS)
    paths, _ = _build_fixture(tmp_path, unit)
    st = _canonical_state(paths)
    out, _ = d7.attach_race_control_asof(st.copy(), unit["race_control"])
    # Both messages share observed_at_s=50; the latest source order (seq1)
    # wins deterministically regardless of input row order.
    assert (out["rc_last_message_seq"] == 1).all()
    assert (out["rc_last_message_text"] == "second").all()


# ==========================================================================
# Pit history (mission §9 / §11).
# ==========================================================================

def _pit_unit(tmp_path):
    """VER pits on lap 2 (in 150.0, out 175.0); PER never pits."""
    unit = normal_race(total_laps=3)
    race_id = unit["race_id"]
    laps = unit["driver_laps"].copy()
    mask = (laps["driver_id"] == "max_verstappen") & (laps["lap_number"] == 2)
    laps.loc[mask, "pit_in_s"] = 150.0
    laps.loc[mask, "pit_out_s"] = 175.0
    # stop_sequence for stint change: VER stint1 laps1-2, stint2 lap3.
    m2 = (laps["driver_id"] == "max_verstappen") & (laps["lap_number"] == 3)
    laps.loc[m2, "stint_number"] = 2.0
    laps.loc[m2, "compound"] = "HARD"
    unit["driver_laps"] = laps
    unit["pit_stops"] = pd.DataFrame(
        [pit_row(race_id, "max_verstappen", 1, 2, 150.0, 175.0)],
        columns=PIT_COLS)
    unit["stints"] = pd.DataFrame([
        stint_row(race_id, "max_verstappen", 1, "SOFT", False, 1, 2, 0,
                  pit_out_lap=2),
        stint_row(race_id, "max_verstappen", 2, "HARD", False, 3, 3, 1,
                  pit_in_lap=2),
        stint_row(race_id, "perez", 1, "SOFT", False, 1, 3, 0),
    ], columns=ST_COLS)
    paths, _ = _build_fixture(tmp_path, unit)
    return unit, paths


def test_pit_asof_last_events_attach(tmp_path):
    unit, paths = _pit_unit(tmp_path)
    st = _canonical_state(paths)
    out, _ = d7.attach_pit_history_asof(st.copy(), unit["pit_stops"])
    ver = out[out["driver_id"] == "max_verstappen"]
    lap1 = ver[ver["lap_number"] == 1].iloc[0]
    assert pd.isna(lap1["pit_last_in_s"]) and pd.isna(lap1["pit_last_out_s"])
    lap2 = ver[ver["lap_number"] == 2].iloc[0]
    assert lap2["pit_last_in_s"] == 150.0
    assert lap2["pit_last_in_lap"] == 2
    assert lap2["pit_last_out_s"] == 175.0
    assert lap2["pit_last_out_lap"] == 2  # exit lap resolved from the marker
    # PER has no pit events at all -> null context.
    per = out[out["driver_id"] == "perez"]
    assert per["pit_last_in_s"].isna().all()
    assert per["pit_last_out_s"].isna().all()
    # Row grain preserved.
    assert len(out) == len(st)


def test_pit_mutate_future_event_earlier_state_unchanged(tmp_path):
    unit, paths = _pit_unit(tmp_path)
    st = _canonical_state(paths)
    base_pits = unit["pit_stops"]
    before, _ = d7.attach_pit_history_asof(st.copy(), base_pits)
    # Mutate the (single) stop time into the future beyond every state.
    mutated = pd.concat([base_pits, pd.DataFrame([pit_row(
        unit["race_id"], "max_verstappen", 9, 3, 1e6, 1e6 + 30.0)],
        columns=PIT_COLS)], ignore_index=True)
    after, _ = d7.attach_pit_history_asof(st.copy(), mutated)
    pd.testing.assert_frame_equal(before, after)
    # Delete every future pit event (> 190): identical.
    deleted, _ = d7.attach_pit_history_asof(st.copy(), mutated)
    pd.testing.assert_frame_equal(deleted, before)


def test_pit_future_entry_cannot_affect_earlier_state(tmp_path):
    unit, paths = _pit_unit(tmp_path)
    st = _canonical_state(paths)
    before, _ = d7.attach_pit_history_asof(st.copy(), unit["pit_stops"])
    # Add a future pit ENTRY (lap 3, time 300) and a future exit (time 330).
    future = pd.concat([
        unit["pit_stops"],
        pd.DataFrame([pit_row(unit["race_id"], "max_verstappen", 2, 3,
                              300.0, 330.0)], columns=PIT_COLS)],
        ignore_index=True)
    after, _ = d7.attach_pit_history_asof(st.copy(), future)
    # All earlier laps (<=2) identical; the lap-3 row must NOT show the
    # future entry as its last-in (its state time is 285 < 300).
    earlier = _state_subset_lte(after, 190.0)
    pd.testing.assert_frame_equal(
        _state_subset_lte(before, 190.0).reset_index(drop=True),
        earlier.reset_index(drop=True))
    lap3 = after[(after["driver_id"] == "max_verstappen")
                 & (after["lap_number"] == 3)].iloc[0]
    assert lap3["pit_last_in_s"] == 150.0  # still the lap-2 entry


def test_pit_same_lap_boundary_cases(tmp_path):
    # Same-lap stop (in and out within lap 2) must attach on the lap-2 row
    # itself (entry + exit both at/before its state time).
    unit, paths = _pit_unit(tmp_path)
    st = _canonical_state(paths)
    pits = unit["pit_stops"]
    out, _ = d7.attach_pit_history_asof(st.copy(), pits)
    row = out[(out["driver_id"] == "max_verstappen")
              & (out["lap_number"] == 2)].iloc[0]
    assert row["pit_last_in_s"] <= row["state_time_s"]
    assert row["pit_last_out_s"] <= row["state_time_s"]
    assert row["pit_last_out_s"] >= row["pit_last_in_s"]


def test_pit_asymmetric_in_only_preserved(tmp_path):
    # pit_in-only (entry, no exit): the entry attaches but no exit is
    # manufactured; a later state must NOT fabricate pit_last_out.
    unit = normal_race(total_laps=3)
    race_id = unit["race_id"]
    laps = unit["driver_laps"].copy()
    mask = (laps["driver_id"] == "max_verstappen") & (laps["lap_number"] == 2)
    laps.loc[mask, "pit_in_s"] = 150.0
    unit["driver_laps"] = laps
    unit["pit_stops"] = pd.DataFrame(
        [pit_row(race_id, "max_verstappen", 1, 2, 150.0, None)],
        columns=PIT_COLS)
    paths, _ = _build_fixture(tmp_path, unit)
    st = _canonical_state(paths)
    out, _ = d7.attach_pit_history_asof(st.copy(), unit["pit_stops"])
    ver = out[out["driver_id"] == "max_verstappen"]
    lap2 = ver[ver["lap_number"] == 2].iloc[0]
    lap3 = ver[ver["lap_number"] == 3].iloc[0]
    assert lap2["pit_last_in_s"] == 150.0
    assert pd.isna(lap2["pit_last_out_s"])
    assert lap3["pit_last_in_s"] == 150.0
    assert pd.isna(lap3["pit_last_out_s"])


def test_pit_asymmetric_out_only_preserved(tmp_path):
    # pit_out-only (exit without entry, e.g. pit-lane start): the exit is an
    # observable event but no entry is manufactured.
    unit = normal_race(total_laps=3)
    race_id = unit["race_id"]
    laps = unit["driver_laps"].copy()
    mask = (laps["driver_id"] == "max_verstappen") & (laps["lap_number"] == 1)
    laps.loc[mask, "pit_out_s"] = 80.0
    unit["driver_laps"] = laps
    unit["pit_stops"] = pd.DataFrame(
        [pit_row(race_id, "max_verstappen", 1, None, None, 80.0)],
        columns=PIT_COLS)
    paths, _ = _build_fixture(tmp_path, unit)
    st = _canonical_state(paths)
    out, notes = d7.attach_pit_history_asof(st.copy(), unit["pit_stops"])
    ver = out[out["driver_id"] == "max_verstappen"]
    lap1 = ver[ver["lap_number"] == 1].iloc[0]
    assert pd.isna(lap1["pit_last_in_s"])
    assert lap1["pit_last_out_s"] == 80.0
    assert lap1["pit_last_out_lap"] == 1


# ==========================================================================
# Stint context (mission §10 / §11).
# ==========================================================================

def test_stint_current_start_side_facts_only(tmp_path):
    unit, paths = _pit_unit(tmp_path)  # VER stint1 (SOFT, 1-2), stint2
    st = _canonical_state(paths)
    out, _ = d7.attach_stint_context(st.copy(), unit["stints"])
    ver = out[out["driver_id"] == "max_verstappen"]
    s1 = ver[ver["lap_number"] == 1].iloc[0]
    assert s1["stint_compound"] == "SOFT"
    assert s1["stint_start_lap"] == 1
    assert s1["stint_tyre_age_at_start"] == 0
    s3 = ver[ver["lap_number"] == 3].iloc[0]
    assert s3["stint_compound"] == "HARD"
    assert s3["stint_start_lap"] == 3
    # The eventual stint END is NEVER exposed as a column anywhere.
    assert not {"end_lap", "pit_out_lap"}.intersection(out.columns)
    assert len(out) == len(st)


def test_stint_mutate_eventual_end_earlier_in_stint_unchanged(tmp_path):
    unit, paths = _pit_unit(tmp_path)
    st = _canonical_state(paths)
    base_stints = unit["stints"]
    before, _ = d7.attach_stint_context(st.copy(), base_stints)
    mutated = base_stints.copy()
    mutated.loc[0, "end_lap"] = 99  # eventual end of stint 1 changed
    mutated.loc[0, "pit_out_lap"] = 99
    after, _ = d7.attach_stint_context(st.copy(), mutated)
    pd.testing.assert_frame_equal(before, after)


def test_stint_mutate_future_compound_earlier_state_unchanged(tmp_path):
    unit, paths = _pit_unit(tmp_path)
    st = _canonical_state(paths)
    base_stints = unit["stints"]
    before, _ = d7.attach_stint_context(st.copy(), base_stints)
    mutated = base_stints.copy()
    # Flip the compound of VER's FUTURE stint (stint 2) to WET.
    mutated.loc[(mutated["driver_id"] == "max_verstappen")
                & (mutated["stint_number"] == 2), "compound"] = "WET"
    after, _ = d7.attach_stint_context(st.copy(), mutated)
    # Earlier in-stint state (stint 1, laps <= 2) unchanged.
    pd.testing.assert_frame_equal(
        _state_subset_lte(before, 190.0).reset_index(drop=True),
        _state_subset_lte(after, 190.0).reset_index(drop=True))
    # lap 3 (stint 2) reflects the mutation (it IS current by then).
    s3 = after[(after["driver_id"] == "max_verstappen")
               & (after["lap_number"] == 3)].iloc[0]
    assert s3["stint_compound"] == "WET"


def test_stint_no_tyre_age_backfill_from_future_laps(tmp_path):
    unit, paths = _pit_unit(tmp_path)
    st = _canonical_state(paths)
    # Null tyre-age at stint start must stay null (no backfill from later).
    stints = unit["stints"].copy()
    stints.loc[0, "tyre_age_at_start"] = None
    out, _ = d7.attach_stint_context(st.copy(), stints)
    s1 = out[(out["driver_id"] == "max_verstappen")
             & (out["lap_number"] == 1)].iloc[0]
    assert pd.isna(s1["stint_tyre_age_at_start"])


def test_stint_source_shuffle_same_result(tmp_path):
    unit, paths = _pit_unit(tmp_path)
    st = _canonical_state(paths)
    base = unit["stints"]
    out1, _ = d7.attach_stint_context(st.copy(), base)
    out2, _ = d7.attach_stint_context(
        st.copy(), base.sample(frac=1.0, random_state=1).reset_index(drop=True))
    pd.testing.assert_frame_equal(
        out1.sort_values("__d7_idx").reset_index(drop=True),
        out2.sort_values("__d7_idx").reset_index(drop=True))


def test_stint_preserves_missing_stint_number(tmp_path):
    unit = normal_race(total_laps=3)
    race_id = unit["race_id"]
    laps = unit["driver_laps"].copy()
    laps.loc[laps["driver_id"] == "perez", "stint_number"] = None
    laps.loc[laps["driver_id"] == "perez", "tyre_life"] = None
    unit["driver_laps"] = laps
    unit["stints"] = pd.DataFrame(
        [stint_row(race_id, "max_verstappen", 1, "SOFT", False, 1, 3, 0)],
        columns=ST_COLS)
    paths, _ = _build_fixture(tmp_path, unit)
    st = _canonical_state(paths)
    out, _ = d7.attach_stint_context(st.copy(), unit["stints"])
    per = out[out["driver_id"] == "perez"]
    assert per["stint_compound"].isna().all()  # no stint_number to map by


# ==========================================================================
# Consolidated future-mutation leakage suite (mission §17).
# ==========================================================================

def test_leakage_future_mutation_suite_at_cutoff(tmp_path):
    """For state at cutoff T, mutate everything strictly after T across all
    D7 source families + future laps + final results: earlier state identical.

    The fixture is the pit unit (VER pits lap2, stint change lap3) with a
    weather observation and race-control messages so all four families are
    exercised."""
    unit, paths = _pit_unit(tmp_path)
    race_id = unit["race_id"]
    unit["weather"] = pd.DataFrame(
        [wx_row(race_id, 50.0), wx_row(race_id, 140.0),
         wx_row(race_id, 250.0, rain=True)],
        columns=WX_COLS)
    unit["race_control"] = pd.DataFrame(
        [rc_row(race_id, 0, 50.0, 1, message="EARLY"),
         rc_row(race_id, 1, 200.0, 2, category="SafetyCar", flag="SC",
                message="SC DEPLOYED")], columns=RC_COLS)
    # Rebuild D6/D7 sources with the richer frames.
    write_tiera_season(paths, 2023, [unit])
    d6.build_season(paths, 2023)
    st = _canonical_state(paths)

    cutoff = 190.0
    enriched_base, _ = d7.enrich_race_state(
        st.copy(), unit["weather"], unit["race_control"], unit["pit_stops"],
        unit["stints"], race_id)

    # Everything strictly after T is mutated to extreme/absurd values.
    wx_mut = pd.concat([
        unit["weather"][unit["weather"]["observed_at_s"] <= cutoff],
        pd.DataFrame([wx_row(race_id, 1e6, air=-99.0, track=-99.0,
                             hum=99.0, press=1.0, wind=99.0, wdir=0.0,
                             rain=True)], columns=WX_COLS)], ignore_index=True)
    rc_mut = pd.concat([
        unit["race_control"][unit["race_control"]["observed_at_s"] <= cutoff],
        pd.DataFrame([rc_row(race_id, 9, 1e6, 99, category="SafetyCar",
                             flag="RED", message="FUTURE")],
                     columns=RC_COLS)], ignore_index=True)
    pit_mut = pd.concat([
        unit["pit_stops"],  # the real lap-2 stop (<= cutoff) stays untouched
        pd.DataFrame(
            [pit_row(race_id, "max_verstappen", 9, 99, 1e6, 1e6 + 30.0)],
            columns=PIT_COLS)], ignore_index=True)
    stint_mut = unit["stints"].copy()
    stint_mut["end_lap"] = 99  # eventual ends are NEVER attached anywhere
    stint_mut.loc[stint_mut["driver_id"] == "max_verstappen", "end_lap"] = 99
    fut = (stint_mut["driver_id"] == "max_verstappen") \
        & (stint_mut["stint_number"] == 2)
    stint_mut.loc[fut, "compound"] = "WET"
    stint_mut.loc[fut, "tyre_age_at_start"] = 99
    # future laps in the D6 state itself (the base rows past T get absurd
    # state times / pit markers) + final results mutated.
    st_mut = st.copy()
    future_laps = st_mut["state_time_s"] > cutoff
    st_mut.loc[future_laps, "state_time_s"] += 1e6
    st_mut.loc[future_laps, "pit_in_s"] = 2e6
    st_mut.loc[future_laps, "pit_out_s"] = 2e6 + 30.0

    enriched_mutated, _ = d7.enrich_race_state(
        st_mut.copy(), wx_mut, rc_mut, pit_mut, stint_mut, race_id)

    before = enriched_base[enriched_base["state_time_s"] <= cutoff]
    after = enriched_mutated[enriched_mutated["state_time_s"] <= cutoff]
    assert len(before) == len(after) > 0
    pd.testing.assert_frame_equal(
        before.sort_values(["race_id", "driver_id", "lap_number"],
                           kind="mergesort").reset_index(drop=True),
        after.sort_values(["race_id", "driver_id", "lap_number"],
                          kind="mergesort").reset_index(drop=True))


# ==========================================================================
# End-to-end D7 season build over the canonical D6 boundary.
# ==========================================================================

def test_d7_season_build_row_reconciliation_and_schema(tmp_path):
    unit, _ = _pit_unit(tmp_path)
    unit["weather"] = pd.DataFrame(
        [wx_row(unit["race_id"], 50.0), wx_row(unit["race_id"], 140.0)],
        columns=WX_COLS)
    unit["race_control"] = pd.DataFrame(
        [rc_row(unit["race_id"], 0, 50.0, 1, message="EARLY")],
        columns=RC_COLS)
    write_tiera_season(V2Paths.from_root(tmp_path), 2023, [unit])
    paths = V2Paths.from_root(tmp_path)
    d6.build_season(paths, 2023)
    report = d7.build_dataset(paths, seasons=[2023], write_artifacts=True)
    base_rows = len(d6.read_state_season(paths, 2023))
    assert report["enriched_rows"] == base_rows
    assert report["races"] == 1
    val = d7.validate_dataset(paths, seasons=[2023])
    assert val["enriched_rows"] == base_rows
    assert val["row_delta"] == 0
    assert val["duplicate_pks"] == 0 and val["null_pks"] == 0
    assert val["temporal_ok"] is True
    assert val["findings"] == []
    assert val["integrity_ok"] is True
    st = d7.read_enriched_season(paths, 2023)
    assert list(st.columns) == S.ENRICHED_COLUMNS
    assert list(st.columns[:len(D6S.STATE_COLUMNS)]) == D6S.STATE_COLUMNS
    assert not (set(st.columns) & set(C.RESULTS.label_columns()))


def test_d7_deterministic_rebuild_and_shuffled_sources(tmp_path):
    unit, _ = _pit_unit(tmp_path)
    unit["weather"] = pd.DataFrame(
        [wx_row(unit["race_id"], 50.0), wx_row(unit["race_id"], 140.0)],
        columns=WX_COLS)
    unit["race_control"] = pd.DataFrame(
        [rc_row(unit["race_id"], 0, 50.0, 1, message="EARLY")],
        columns=RC_COLS)
    # Shuffle the source rows before the D5-style write (order must not
    # matter: D5/D6/D7 are all deterministic over row content).
    unit["weather"] = unit["weather"].sample(
        frac=1.0, random_state=3).reset_index(drop=True)
    unit["stints"] = unit["stints"].sample(
        frac=1.0, random_state=4).reset_index(drop=True)
    unit["pit_stops"] = unit["pit_stops"].sample(
        frac=1.0, random_state=5).reset_index(drop=True)
    unit["race_control"] = unit["race_control"].sample(
        frac=1.0, random_state=6).reset_index(drop=True)
    write_tiera_season(V2Paths.from_root(tmp_path), 2023, [unit])
    paths = V2Paths.from_root(tmp_path)
    d6.build_season(paths, 2023)
    r1 = d7.build_dataset(paths, seasons=[2023], write_artifacts=True)
    dest = d7.dest_for_unit(paths.processed_dir, S.STATE_ENTITY, 2023,
                            S.d7_unit_id(2023))
    b1 = dest.read_bytes()
    r2 = d7.build_dataset(paths, seasons=[2023], write_artifacts=True)
    assert dest.read_bytes() == b1  # byte-identical rebuild
    assert r1["enriched_rows"] == r2["enriched_rows"]
    a = pd.read_parquet(dest)
    pd.testing.assert_frame_equal(a, pd.read_parquet(dest))
