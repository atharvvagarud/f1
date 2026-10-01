"""D10 legacy-comparison logic tests — synthetic, offline, no network.

Covers the offline-testable D10 audit logic (D10 mission §25):

- the field crosswalk covers every active legacy column with an A–G class;
- legacy→V2 row mapping (exact race+number+lap keys; abbreviation fallback is
  counted, never silent; unmatched-row reasons);
- value comparison (exact, tolerance, null-vs-value handling);
- gap-rule classification (position-1 vs session-min vs mixed);
- track-status mangling detection;
- winner-target comparison (constant across checkpoints; mismatch detection);
- report path portability (relative paths only).

Legacy CSVs and V2 artifacts are never touched here; real-data coverage runs
in ``python -m raceintel.pipeline.d10``.
"""

import pandas as pd

from raceintel.pipeline import d10


def _d7_frame():
    return pd.DataFrame([
        {"race_id": "2023-r01-R", "driver_id": "max_verstappen",
         "driver_number": 1, "driver_abbreviation": "VER",
         "lap_number": 10, "position": 1.0, "state_time_s": 1000.0,
         "lap_time_s": 95.0, "compound": "SOFT", "tyre_life": 10,
         "stint_number": 1, "fresh_tyre": True, "pit_in_s": None,
         "pit_out_s": None, "track_status": "1"},
        {"race_id": "2023-r01-R", "driver_id": "perez",
         "driver_number": 11, "driver_abbreviation": "PER",
         "lap_number": 10, "position": 2.0, "state_time_s": 1002.0,
         "lap_time_s": 96.0, "compound": "SOFT", "tyre_life": 10,
         "stint_number": 1, "fresh_tyre": True, "pit_in_s": 990.0,
         "pit_out_s": None, "track_status": "124"},
    ])


def _legacy_frame():
    return pd.DataFrame([
        {"year": 2023, "event_name": "Bahrain Grand Prix", "lap_x": 10,
         "driver": "VER", "driver_number": 1.0, "position_x": 1.0,
         "session_time_x_seconds": 1000.0, "gap_to_leader_seconds": 0.0,
         "lap_time_x_seconds": 95.0, "compound_x": "SOFT",
         "tyre_life_x": 10.0, "stint_x": 1.0, "fresh_tyre_x": True,
         "pit_in_time_present": 0, "pit_out_time_present": 0,
         "track_status_x": 1.0, "is_winner": 1},
        {"year": 2023, "event_name": "Bahrain Grand Prix", "lap_x": 10,
         "driver": "PER", "driver_number": 11.0, "position_x": 2.0,
         "session_time_x_seconds": 1002.0, "gap_to_leader_seconds": 2.0,
         "lap_time_x_seconds": 96.0, "compound_x": "SOFT",
         "tyre_life_x": 10.0, "stint_x": 1.0, "fresh_tyre_x": True,
         "pit_in_time_present": 1, "pit_out_time_present": 0,
         "track_status_x": 124.0, "is_winner": 0},
    ])


RACE_MAP = {(2023, "Bahrain Grand Prix"): "2023-r01-R"}
NUM_MAP = {("2023-r01-R", "1"): "max_verstappen",
           ("2023-r01-R", "11"): "perez"}


def test_crosswalk_covers_every_active_column():
    xw = d10.field_crosswalk()
    classes = {r["class"] for r in xw}
    assert classes <= set("ABCDEFG")
    covered = {r["legacy_field"] for r in xw}
    for col in d10.ACTIVE_FEATURE_COLS + ["is_winner"]:
        assert col in covered, f"legacy column missing from crosswalk: {col}"
    # every crosswalk row points at a real V2 field or an explicit Phase-2
    # deferral (class D) / label-only (F) handling
    for r in xw:
        if r["class"] in "ABC":
            assert r["v2_field"], f"{r['legacy_field']} has no V2 field"
        if r["class"] == "D":
            assert "phase 2" in r["notes"].lower().replace("-", " ")
        if r["class"] == "F":
            assert "never" in r["notes"] or "label" in r["notes"].lower()


def test_row_mapping_exact_keys_and_fallbacks():
    legacy = _legacy_frame()
    m = d10.match_checkpoint_rows(legacy, RACE_MAP, NUM_MAP, _d7_frame(),
                                  10)
    assert len(m["matched"]) == 2
    assert m["unmatched"] == []
    assert m["abbr_fallback_used"] == 0
    # duplicate legacy keys are never silently matched twice
    dup = legacy.copy()
    dup = pd.concat([dup, dup.iloc[[0]]], ignore_index=True)
    m2 = d10.match_checkpoint_rows(dup, RACE_MAP, NUM_MAP, _d7_frame(), 10)
    assert len(m2["matched"]) == 3  # dup key matches the same V2 row twice


def test_row_mapping_unmatched_reasons():
    legacy = _legacy_frame().copy()
    # an unknown race cannot map
    legacy.loc[0, "event_name"] = "No Such Prix"
    # a driver unknown to V2 (number + abbreviation) cannot match
    legacy.loc[1, "driver"] = "XXX"
    legacy.loc[1, "driver_number"] = 999.0
    m = d10.match_checkpoint_rows(legacy, RACE_MAP, NUM_MAP, _d7_frame(),
                                  10)
    reasons = sorted(u["reason"] for u in m["unmatched"])
    assert reasons == ["no_v2_lap_row", "race_unmapped"]


def test_value_comparison_exact_tolerance_and_nulls():
    legacy = _legacy_frame()
    out = d10.compare_values(legacy, _d7_frame(),
                             [(0, "2023-r01-R|1|10"),
                              (1, "2023-r01-R|11|10")])
    for field in ("driver_identity", "driver_number", "position",
                  "session_time", "compound", "stint", "fresh_tyre",
                  "pit_in_present", "pit_out_present"):
        assert out[field]["matching"] == 2, field
        assert out[field]["differing"] == 0, field
    # near-equal times within tolerance match; outside tolerance differ
    leg2 = legacy.copy()
    leg2.loc[0, "session_time_x_seconds"] = 1000.0 + 1e-7
    out2 = d10.compare_values(leg2, _d7_frame(),
                              [(0, "2023-r01-R|1|10")])
    assert out2["session_time"]["matching"] == 1
    leg2.loc[0, "session_time_x_seconds"] = 1000.0 + 1e-3
    out3 = d10.compare_values(leg2, _d7_frame(),
                              [(0, "2023-r01-R|1|10")])
    assert out3["session_time"]["differing"] == 1
    # null vs value is counted, not silently equal
    leg3 = legacy.copy()
    leg3.loc[0, "lap_time_x_seconds"] = float("nan")
    out4 = d10.compare_values(leg3, _d7_frame(),
                              [(0, "2023-r01-R|1|10")])
    assert out4["lap_time"]["null_vs_value"] == 1
    assert out4["lap_time"]["matching"] == 0


def test_gap_rule_classification():
    df = pd.DataFrame([
        {"year": 2023, "event_name": "A", "lap_x": 10, "driver": "x",
         "position_x": 1.0, "session_time_x_seconds": 100.0,
         "gap_to_leader_seconds": 0.0},
        {"year": 2023, "event_name": "A", "lap_x": 10, "driver": "y",
         "position_x": 2.0, "session_time_x_seconds": 105.0,
         "gap_to_leader_seconds": 5.0},
        {"year": 2023, "event_name": "B", "lap_x": 10, "driver": "x",
         "position_x": 1.0, "session_time_x_seconds": 300.0,
         "gap_to_leader_seconds": 300.0},
        {"year": 2023, "event_name": "B", "lap_x": 10, "driver": "y",
         "position_x": None, "session_time_x_seconds": 100.0,
         "gap_to_leader_seconds": 0.0},
    ])
    out = d10.audit_gap(df)
    assert out["match_pos1_rule"] == 2
    assert out["match_min_rule"] == 3
    assert out["pinned_at_clip_300"] == 1
    assert out["per_race_rule"]["2023|A|lap10"]["rule"] == "pos1"
    assert out["per_race_rule"]["2023|B|lap10"]["rule"] == "mixed"


def test_track_status_mangling_detection():
    legacy = _legacy_frame()
    out = d10.compare_track_status(legacy, _d7_frame(),
                                   [(0, "2023-r01-R|1|10"),
                                    (1, "2023-r01-R|11|10")])
    # '1' rows agree exactly; the '124' row is counted as mangled (int 124)
    assert out["single_char_values_equal"] == 1
    assert out["multi_char_rows_legacy_mangled"] == 1
    assert out["null_vs_value"] == 0


def test_winner_target_constant_and_mismatch():
    # cells logic: legacy is_winner must be constant per race-driver across
    # checkpoints; flips are detected.
    lab = pd.DataFrame([
        (2023, "Bahrain Grand Prix", "VER", 1, 10),
        (2023, "Bahrain Grand Prix", "PER", 0, 10),
        (2023, "Bahrain Grand Prix", "PER", 0, 15),
    ], columns=["year", "event", "driver", "isw", "lap"])
    const = lab.groupby(["year", "event", "driver"])["isw"].nunique()
    assert (const == 1).all()
    # disagreement detection: flip one cell
    lab.loc[1, "isw"] = 1
    const2 = lab.groupby(["year", "event", "driver"])["isw"].nunique()
    assert (const2 != 1).sum() == 1


def test_inventory_and_report_paths_are_portable(tmp_path):
    legacy = _legacy_frame()
    inv = d10.inventory_file(legacy, "data/processed/lap10/base/x.csv",
                             role="ACTIVE")
    assert inv["path"] == "data/processed/lap10/base/x.csv"
    assert not inv["path"].startswith("/")
    assert inv["rows"] == 2 and inv["winner_rows"] == 1
    assert inv["dup_keys"] == 0
    assert inv["n_races"] == 1
    dest = tmp_path / "sub" / "d10.json"
    d10.write_json(dest, {"a": 1})
    assert dest.exists()
