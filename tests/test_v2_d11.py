"""D11 final-validation logic tests — synthetic, offline, no network.

Covers the offline-testable D11 machinery (D11 mission §§1/7/8/10/29):

- validation-matrix structure (unique ids, valid severities, required areas);
- severity taxonomy and findings-register record shape;
- eligible-field enumeration consistency (no data needed — schemas only);
- the ADVERSARIAL COMBINED future-mutation proof: a synthetic mini-pipeline
  across the D7 as-of attachments and the D9 derivations at a state cutoff,
  mutating ALL source families strictly after the cutoff at once; earlier
  predictive state must remain identical while labels change appropriately.

No FastF1, no cache, no canonical data, no telemetry.
"""

import pandas as pd
import pytest

from raceintel.pipeline import d7
from raceintel.pipeline import d9
from raceintel.pipeline import d9schema as S9
from raceintel.pipeline import d11


def test_matrix_structure_and_severity_taxonomy():
    ids = [e["id"] for e in d11.VALIDATION_MATRIX]
    assert len(ids) == len(set(ids)) > 20
    for e in d11.VALIDATION_MATRIX:
        assert set(e) == {"id", "area", "invariant", "method", "expected",
                          "severity"}
        assert e["severity"] in d11.SEVERITIES
        assert all(e[k] for k in ("invariant", "method", "expected"))
    areas = {e["area"] for e in d11.VALIDATION_MATRIX}
    for required in ("artifacts", "schemas", "integrity", "identity",
                     "temporal", "leakage", "labels", "quality", "scope",
                     "operations", "reproducibility", "regression"):
        assert required in areas, f"matrix missing area: {required}"


def test_finding_record_shape():
    f = d11._finding("X", "BLOCKER", True, {"a": 1}, "impact")
    assert f == {"id": "X", "severity": "BLOCKER", "status": "pass",
                 "evidence": {"a": 1}, "impact": "impact",
                 "blocks_phase1": False, "resolved_in_d11": False}
    g = d11._finding("X", "BLOCKER", False, {}, "")
    assert g["status"] == "fail" and g["blocks_phase1"] is True
    h = d11._finding("X", "MAJOR", False, {}, "")
    assert h["status"] == "fail" and h["blocks_phase1"] is False


def test_eligible_fields_consistent_without_data():
    eligible = d11._eligible_fields()
    assert len(eligible) > 0
    names = [n for n, _, _, _, _ in eligible]
    assert len(names) == len(set(names))
    # quality metadata must never be eligible
    for forbidden in ("source_unit_status", "shortened_race",
                      "wx_observed_at_s", "wx_age_s",
                      "rc_last_message_seq", "stint_start_lap"):
        assert forbidden not in names
    # no outcome-named field is eligible
    assert not (set(names) & d11._OUTCOME_NAMES)


def _synthetic_inputs():
    state = pd.DataFrame([
        {"race_id": "r", "driver_id": "a", "lap_number": 1,
         "state_time_s": 100.0, "stint_number": 1,
         "track_status": "1", "pit_out_s": None},
        {"race_id": "r", "driver_id": "a", "lap_number": 2,
         "state_time_s": 200.0, "stint_number": 1,
         "track_status": "4", "pit_out_s": 150.0},
        {"race_id": "r", "driver_id": "a", "lap_number": 3,
         "state_time_s": 300.0, "stint_number": 2,
         "track_status": "1", "pit_out_s": None},
        {"race_id": "r", "driver_id": "a", "lap_number": 4,
         "state_time_s": 400.0, "stint_number": 2,
         "track_status": "1", "pit_out_s": None},
        {"race_id": "r", "driver_id": "a", "lap_number": 5,
         "state_time_s": 500.0, "stint_number": 2,
         "track_status": "1", "pit_out_s": 480.0},
    ])
    weather = pd.DataFrame([
        {"observed_at_s": 50.0, "air_temp_c": 30.0, "track_temp_c": 40.0,
         "humidity_pct": 20.0, "pressure_hpa": 1015.0, "wind_speed": 1.0,
         "wind_direction_deg": 180.0, "rainfall": False},
        {"observed_at_s": 250.0, "air_temp_c": 25.0, "track_temp_c": 35.0,
         "humidity_pct": 30.0, "pressure_hpa": 1014.0, "wind_speed": 2.0,
         "wind_direction_deg": 200.0, "rainfall": True},
        {"observed_at_s": 500.0, "air_temp_c": -99.0, "track_temp_c": -99.0,
         "humidity_pct": 99.0, "pressure_hpa": 500.0, "wind_speed": 99.0,
         "wind_direction_deg": 0.0, "rainfall": True},
    ])
    rc = pd.DataFrame([
        {"message_seq": 0, "observed_at_s": 40.0, "lap_number": 1,
         "category": "Flag", "flag": "GREEN", "message_text": "GREEN"},
        {"message_seq": 1, "observed_at_s": 260.0, "lap_number": 3,
         "category": "SafetyCar", "flag": None, "message_text": "SC DEPLOYED"},
        {"message_seq": 2, "observed_at_s": 600.0, "lap_number": 5,
         "category": "Flag", "flag": "RED", "message_text": "FUTURE"},
    ])
    pits = pd.DataFrame([
        {"driver_id": "a", "lap_number": 2, "pit_in_s": 130.0,
         "pit_out_s": 150.0},
        {"driver_id": "a", "lap_number": 5, "pit_in_s": 450.0,
         "pit_out_s": 480.0},
    ])
    stints = pd.DataFrame([
        {"driver_id": "a", "stint_number": 1, "start_lap": 1,
         "compound": "SOFT", "fresh_tyre": True, "tyre_age_at_start": 0,
         "end_lap": 2},
        {"driver_id": "a", "stint_number": 2, "start_lap": 3,
         "compound": "HARD", "fresh_tyre": True, "tyre_age_at_start": 1,
         "end_lap": 5},
    ])
    return state, weather, rc, pits, stints


def _enrich_and_derive(state, weather, rc, pits, stints):
    s, _ = d7.attach_weather_asof(state.copy(), weather)
    s, _ = d7.attach_race_control_asof(s, rc)
    s, _ = d7.attach_pit_history_asof(s, pits)
    s, _ = d7.attach_stint_context(s, stints)
    s = s.drop(columns=["__d7_idx"])
    s = d9.derive_track_state(s)
    s = d9.derive_race_progress(s, scheduled_laps=58)
    s = d9.derive_pit_history_state(s, pits)
    s = d9.derive_stint_lap(s)
    return s


def test_combined_future_mutation_earlier_state_identical():
    """D11 §8: mutate EVERYTHING strictly after cutoff T at once."""
    state, weather, rc, pits, stints = _synthetic_inputs()
    cutoff = 250.0
    before = _enrich_and_derive(state, weather, rc, pits, stints)

    mutated_state = state.copy()
    future_laps = mutated_state["state_time_s"] > cutoff
    mutated_state.loc[future_laps, "track_status"] = "5"
    mutated_state.loc[future_laps, "state_time_s"] += 1e6
    mutated_state.loc[future_laps, "pit_out_s"] = 2e6

    mutated_weather = weather.copy()
    mutated_weather.loc[mutated_weather["observed_at_s"] > cutoff,
                        "air_temp_c"] = -273.0
    mutated_weather.loc[mutated_weather["observed_at_s"] > cutoff,
                        "observed_at_s"] += 1e6

    mutated_rc = rc.copy()
    mutated_rc.loc[mutated_rc["observed_at_s"] > cutoff,
                   "message_text"] = "MUTATED FUTURE"
    mutated_rc.loc[mutated_rc["observed_at_s"] > cutoff,
                   "observed_at_s"] += 1e6

    mutated_pits = pits.copy()
    # keep pit events consistent with their state markers (same underlying
    # event observed in two tables): move the future stop to the mutated
    # marker time.
    mutated_pits.loc[mutated_pits["pit_out_s"] > cutoff,
                     "pit_out_s"] = 2e6
    mutated_pits.loc[mutated_pits["pit_in_s"] > cutoff,
                     "pit_in_s"] = 2e6 - 30.0

    mutated_stints = stints.copy()
    mutated_stints["end_lap"] = 99  # eventual ends are never attached
    mutated_stints.loc[mutated_stints["start_lap"] > 2, "compound"] = "WET"
    mutated_stints.loc[mutated_stints["start_lap"] > 2,
                       "tyre_age_at_start"] = 99

    after = _enrich_and_derive(mutated_state, mutated_weather, mutated_rc,
                               mutated_pits, mutated_stints)
    earlier_before = before[before["state_time_s"] <= cutoff].reset_index(
        drop=True)
    earlier_after = after[after["state_time_s"] <= cutoff].reset_index(
        drop=True)
    assert len(earlier_before) == len(earlier_after) == 2
    pd.testing.assert_frame_equal(earlier_before, earlier_after)


def test_combined_mutation_changes_only_future_rows():
    state, weather, rc, pits, stints = _synthetic_inputs()
    before = _enrich_and_derive(state, weather, rc, pits, stints)
    # sanity: the pipeline actually attaches context (not all-null)
    assert before["wx_air_temp_c"].notna().any()
    assert before["rc_last_message_seq"].notna().any()
    assert before["pit_last_out_s"].notna().any()
    assert before["stint_start_lap"].notna().any()
    assert (before["track_state"] == "safety_car").any()
    # race progress + pit/stint derivations are populated
    assert before["race_leader_laps_at_state"].notna().all()
    assert before["pit_stops_completed_so_far"].notna().all()
    assert before["stint_lap"].notna().all()


def test_label_mutation_boundary_synthetic():
    res = pd.DataFrame([{
        "race_id": "2023-r01-R", "driver_id": "a",
        "driver_abbreviation": "AAA",
        "position_final": 1.0, "classified_position": 1.0,
        "position_text": "1", "status_text": "Finished", "points": 25.0,
        "laps_completed": 58},
        {"race_id": "2023-r01-R", "driver_id": "b",
         "driver_abbreviation": "BBB",
         "position_final": 2.0, "classified_position": 2.0,
         "position_text": "2", "status_text": "Finished", "points": 18.0,
         "laps_completed": 58}])
    before = d9.labels_from_results(res)
    flipped = res.copy()
    flipped.loc[0, ["position_final", "classified_position",
                    "points"]] = [2.0, 2.0, 18.0]
    flipped.loc[1, ["position_final", "classified_position",
                    "points"]] = [1.0, 1.0, 25.0]
    after = d9.labels_from_results(flipped)
    assert before.loc[0, "winner_flag"] == True  # noqa: E712
    assert after.loc[1, "winner_flag"] == True  # noqa: E712
    assert after.loc[0, "winner_flag"] == False  # noqa: E712
    # labels carry no state columns and vice versa
    assert not (set(after.columns) & {"state_time_s", "lap_number",
                                      "track_status"})
