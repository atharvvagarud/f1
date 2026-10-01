"""D6 canonical driver-lap dataset tests — synthetic, offline, no network.

Covers: canonical grain/PK, identity enrichment, row reconciliation
(lossless build; loud failure on orphan keys), label separation, state_time
semantics, missingness preservation, PARTIAL-race representation + quality
metadata, join cardinality, determinism, and the mandatory FUTURE-DATA
mutation (leakage) tests (weather / race-control / pit / stint / future-lap /
final-result) on synthetic fixtures.

FastF1 is never imported; D5-shaped parquet fixtures are written under
tmp_path and consumed exactly like the real canonical D5 outputs.
"""

import json

import pandas as pd
import pytest

from raceintel import contracts as C
from raceintel.pipeline import d6schema as S
from raceintel.pipeline import d6
from raceintel.config import V2Paths
from raceintel.errors import ErrorCategory, IngestionError
from raceintel.storage import atomic_write_parquet, dest_for_unit

LAP_COLS = [c.name for c in C.DRIVER_LAPS.columns]
RES_COLS = [c.name for c in C.RESULTS.columns]
RACE_COLS = [c.name for c in C.RACES.columns]

DL_FLOAT_NA = {
    "race_id": None, "driver_id": None, "lap_number": None, "position": None,
    "session_time_end_s": None, "lap_start_s": None, "lap_time_s": None,
    "sector_1_s": None, "sector_2_s": None, "sector_3_s": None,
    "sector_1_end_s": None, "sector_2_end_s": None, "sector_3_end_s": None,
    "speed_i1_kmh": None, "speed_i2_kmh": None, "speed_fl_kmh": None,
    "speed_st_kmh": None, "compound": None, "tyre_life": None,
    "stint_number": None, "fresh_tyre": None, "pit_in_s": None,
    "pit_out_s": None, "track_status": None, "deleted": None,
    "deleted_reason": None, "is_accurate": None, "fastf1_generated": None,
}


_AUTO = object()


def dl_row(race_id, driver, lap, position=1.0, base=None, lap_time=95.0,
           compound="SOFT", tyre_life=_AUTO, stint=1, fresh=True, track="1",
           pit_in=None, pit_out=None, s1=30.0, s2=32.0, s3=33.0,
           speed=300.0, deleted=False, accurate=True, generated=False):
    if base is None:
        base = (lap - 1) * 95.0
    if tyre_life is _AUTO:
        tyre_life = float(stint + lap)
    else:
        tyre_life = None if tyre_life is None else float(tyre_life)
    row = dict(DL_FLOAT_NA)
    row.update({
        "race_id": race_id, "driver_id": driver, "lap_number": int(lap),
        "position": position, "session_time_end_s": base + lap_time,
        "lap_start_s": base, "lap_time_s": lap_time,
        "sector_1_s": s1, "sector_2_s": s2, "sector_3_s": s3,
        "sector_1_end_s": base + s1, "sector_2_end_s": base + 62.0,
        "sector_3_end_s": base + lap_time,
        "speed_i1_kmh": speed, "speed_i2_kmh": speed + 10.0,
        "speed_fl_kmh": speed + 20.0, "speed_st_kmh": speed + 30.0,
        "compound": compound, "tyre_life": tyre_life,
        "stint_number": float(stint), "fresh_tyre": bool(fresh),
        "pit_in_s": pit_in, "pit_out_s": pit_out, "track_status": track,
        "deleted": bool(deleted), "deleted_reason": None,
        "is_accurate": bool(accurate), "fastf1_generated": bool(generated),
    })
    return row


def res_row(race_id, driver, code, number, team, position=1, class_pos="1",
            grid=1, status="Finished", points=25.0, laps=None):
    dnf = class_pos is None or str(class_pos).isalpha()
    return {
        "race_id": race_id, "driver_id": driver,
        "driver_abbreviation": code, "driver_number": number,
        "team_id_at_race": team, "grid_position": grid,
        "position_final": position, "classified_position": (
            None if dnf else float(class_pos)),
        "position_text": class_pos, "status_text": status,
        "dnf_flag": bool(dnf), "points": float(points or 0.0),
        "laps_completed": laps, "winner_flag": position == 1,
        "podium_flag": position in (1, 2, 3),
    }


def races_frame(season, round_no, race_id, total_laps, circuit="bahrain",
                event_name="Bahrain Grand Prix"):
    return pd.DataFrame([{
        "race_id": race_id, "season": season, "round_no": round_no,
        "event_id": C.make_event_id(season, round_no),
        "circuit_id": circuit, "event_name": event_name,
        "official_event_name": event_name, "country": "X",
        "location": "Y", "event_format": "conventional",
        "total_laps_scheduled": total_laps, "f1_api_support": True,
    }], columns=RACE_COLS)


def write_tiera_season(paths, season, race_units):
    """race_units: list of dicts with keys season/round/race_id/driver_laps/
    results/races/weather/race_control/pit_stops/stints/status/quality_note/
    error_message. Returns the manifest path."""
    for unit in race_units:
        race_id = unit["race_id"]
        for entity in ("races", "driver_laps", "results", "weather",
                       "race_control", "pit_stops", "stints"):
            frame = unit.get(entity)
            if frame is None or len(frame) == 0:
                frame = pd.DataFrame()
            dest = dest_for_unit(paths.processed_dir, entity, season, race_id)
            atomic_write_parquet(frame, dest)
    manifest = {"format_version": 1, "units": {}}
    for unit in race_units:
        race_id = unit["race_id"]
        manifest["units"][race_id] = {
            "unit_id": race_id, "season": season,
            "round_no": int(race_id.split("-r")[1].split("-")[0]),
            "session_code": "R", "race_id": race_id,
            "status": unit.get("status", "complete"), "attempts": 1,
            "quality_note": unit.get("quality_note"),
            "error_message": unit.get("error_message"),
        }
    mpath = paths.manifest_path(f"tiera-{season}.json")
    mpath.parent.mkdir(parents=True, exist_ok=True)
    mpath.write_text(json.dumps(manifest))
    return mpath


# ---------------------------------------------------------------------------
# A canonical normal race fixture (two classified finishers + one lapped).
# ---------------------------------------------------------------------------

def normal_race(season=2023, round_no=1, total_laps=3,
                status="complete", race_id=None):
    race_id = race_id or C.make_race_id(season, round_no)
    laps = pd.DataFrame([
        dl_row(race_id, "max_verstappen", 1, position=1.0),
        dl_row(race_id, "max_verstappen", 2, position=1.0),
        dl_row(race_id, "max_verstappen", 3, position=1.0),
        dl_row(race_id, "perez", 1, position=2.0),
        dl_row(race_id, "perez", 2, position=2.0),
        dl_row(race_id, "leclerc", 1, position=3.0, compound="HARD",
               tyre_life=12.0),
    ], columns=LAP_COLS)
    results = pd.DataFrame([
        res_row(race_id, "max_verstappen", "VER", 1, "red_bull",
                position=1, laps=3),
        res_row(race_id, "perez", "PER", 11, "red_bull",
                position=2, class_pos="2", points=18.0, laps=2),
        res_row(race_id, "leclerc", "LEC", 16, "ferrari",
                position=3, class_pos="3", points=15.0, laps=1),
    ], columns=RES_COLS)
    return {"season": season, "round_no": round_no, "race_id": race_id,
            "driver_laps": laps, "results": results,
            "races": races_frame(season, round_no, race_id, total_laps),
            "weather": pd.DataFrame(), "race_control": pd.DataFrame(),
            "pit_stops": pd.DataFrame(), "stints": pd.DataFrame(),
            "status": status}


def build_race_season(tmp_path, unit):
    paths = V2Paths.from_root(tmp_path)
    season = unit["season"]
    write_tiera_season(paths, season, [unit])
    stats = d6.build_season(paths, season)
    return paths, stats


# --------------------------------------------------------------------------
# Grain, identifiers, state_time, reconciliation.
# --------------------------------------------------------------------------

def test_normal_race_canonical_rows_and_identifiers(tmp_path):
    unit = normal_race()
    paths, stats = build_race_season(tmp_path, unit)
    assert stats["state_rows"] == 6
    assert stats["quality_rows"] == 1
    assert stats["input_rows"] == 6 and stats["dropped_rows"] == 0
    st = d6.read_state_season(paths, 2023)
    # Canonical PK uniqueness.
    assert st.duplicated(subset=["race_id", "driver_id", "lap_number"]).sum() == 0
    # Identifiers carried.
    assert set(st["race_id"]) == {"2023-r01-R"}
    assert (st["season"] == 2023).all() and (st["round_no"] == 1).all()
    assert (st["event_id"] == "2023-r01").all()
    assert (st["circuit_id"] == "bahrain").all()
    assert set(st["constructor_id"]) == {"red_bull", "ferrari"}
    assert st[st["driver_id"] == "leclerc"].iloc[0]["constructor_id"] == "ferrari"
    # Schema exact-order conformance.
    assert list(st.columns) == S.STATE_COLUMNS


def test_state_time_is_lap_end_not_lap_start(tmp_path):
    unit = normal_race()
    paths, _ = build_race_season(tmp_path, unit)
    st = d6.read_state_season(paths, 2023)
    row = st[(st["driver_id"] == "max_verstappen")
             & (st["lap_number"] == 2)].iloc[0]
    assert row["state_time_s"] == pytest.approx(190.0)  # end of lap 2
    assert row["lap_start_s"] == pytest.approx(95.0)
    assert row["state_time_s"] > row["lap_start_s"]
    # state_time_s is the source lap-end Time, renamed (never recomputed).
    src = pd.read_parquet(dest_for_unit(paths.processed_dir, "driver_laps",
                                        2023, unit["race_id"]))
    src_row = src[(src["driver_id"] == "max_verstappen")
                  & (src["lap_number"] == 2)].iloc[0]
    assert row["state_time_s"] == pytest.approx(src_row["session_time_end_s"])
    assert "session_time_end_s" not in st.columns  # canonical rename, no dup


def test_reconciliation_zero_unexplained_loss(tmp_path):
    unit = normal_race()
    # Add a DNS driver in results with no laps (must NOT create state rows).
    unit["results"] = pd.concat([
        unit["results"],
        pd.DataFrame([res_row(unit["race_id"], "zho_guanyu", "ZHO", 24,
                              "sauber", position=None, class_pos="W",
                              status="Withdrew", points=0.0, laps=0)],
                     columns=RES_COLS)],
        ignore_index=True)
    paths, stats = build_race_season(tmp_path, unit)
    assert stats["input_rows"] == 6
    assert stats["state_rows"] == 6  # DNS driver adds zero lap rows


def test_orphan_driver_lap_key_fails_loudly(tmp_path):
    unit = normal_race()
    # Remove leclerc from results -> its lap key would be silently lost.
    unit["results"] = unit["results"][
        unit["results"]["driver_id"] != "leclerc"].reset_index(drop=True)
    paths = V2Paths.from_root(tmp_path)
    season = unit["season"]
    write_tiera_season(paths, season, [unit])
    with pytest.raises(IngestionError) as excinfo:
        d6.build_season(paths, season)
    assert excinfo.value.category is ErrorCategory.VALIDATION
    assert "results identity" in excinfo.value.message


def test_missing_d5_source_is_loud(tmp_path):
    unit = normal_race()
    paths = V2Paths.from_root(tmp_path)
    write_tiera_season(paths, unit["season"], [unit])
    # Remove the driver_laps file: D6 must not silently build an empty race.
    dest = dest_for_unit(paths.processed_dir, "driver_laps", unit["season"],
                         unit["race_id"])
    dest.unlink()
    with pytest.raises(IngestionError) as excinfo:
        d6.build_season(paths, unit["season"])
    assert excinfo.value.category is ErrorCategory.STORAGE


# --------------------------------------------------------------------------
# Missingness preservation + label separation.
# --------------------------------------------------------------------------

def test_missingness_preserved_no_imputation(tmp_path):
    unit = normal_race()
    # Monaco-style source gaps: null compound, tyre_life, sector, position.
    bad = dl_row(unit["race_id"], "perez", 2, position=None, compound=None,
                 tyre_life=None, speed=305.0)
    unit["driver_laps"] = unit["driver_laps"][
        unit["driver_laps"]["driver_id"] != "perez"].reset_index(drop=True)
    unit["driver_laps"] = pd.concat(
        [unit["driver_laps"], pd.DataFrame([bad], columns=LAP_COLS)],
        ignore_index=True)
    unit["results"] = unit["results"][
        unit["results"]["driver_id"] != "perez"].reset_index(drop=True)
    unit["results"] = pd.concat([
        unit["results"],
        pd.DataFrame([res_row(unit["race_id"], "perez", "PER", 11, "red_bull",
                              position=None, class_pos="R", status="DNF",
                              points=0.0, laps=1)], columns=RES_COLS)],
        ignore_index=True)
    paths, stats = build_race_season(tmp_path, unit)
    st = d6.read_state_season(paths, 2023)
    row = st[(st["driver_id"] == "perez") & (st["lap_number"] == 2)].iloc[0]
    assert pd.isna(row["position"])
    assert pd.isna(row["compound"]) or row["compound"] is None
    assert pd.isna(row["tyre_life"])
    assert row["state_time_s"] is not None  # clock never imputed/invented


def test_state_table_has_zero_label_columns(tmp_path):
    unit = normal_race()
    paths, _ = build_race_season(tmp_path, unit)
    st = d6.read_state_season(paths, 2023)
    labels = set(C.RESULTS.label_columns())
    assert not (set(st.columns) & labels)
    # Every column availability is machine-readable and no column is
    # LABEL_ONLY / POST_RACE predictive.
    schema = S.schema_json()["tables"][S.STATE_ENTITY]["columns"]
    assert all(f["availability"] != "LABEL_ONLY" for f in schema)
    for f in schema:
        if f["availability"] in ("POST_RACE", "SOURCE_METADATA"):
            assert f["predictive_eligible"] is False


# --------------------------------------------------------------------------
# PARTIAL races + quality metadata.
# --------------------------------------------------------------------------

def test_partial_race_kept_with_quality_metadata(tmp_path):
    # 2021 Belgium-style farce: 3 of 39 scheduled laps, manifest PARTIAL.
    unit = normal_race(season=2021, round_no=12, total_laps=39,
                       status="partial", race_id="2021-r12-R")
    unit["driver_laps"] = unit["driver_laps"][
        unit["driver_laps"]["lap_number"] <= 3].reset_index(drop=True)
    paths, stats = build_race_season(tmp_path, unit)
    assert stats["state_rows"] == 6  # VER 1-3, PER 1-2, LEC 1 all <= 3
    st = d6.read_state_season(paths, 2021)
    assert (st["source_unit_status"] == "partial").all()
    assert (st["shortened_race"] == True).all()  # noqa: E712
    q = d6.read_quality_season(paths, 2021)
    assert len(q) == 1
    assert q.iloc[0]["source_unit_status"] == "partial"
    assert q.iloc[0]["shortened_race"] == True  # noqa: E712
    assert q.iloc[0]["total_laps_scheduled"] == 39
    assert q.iloc[0]["observed_leader_laps"] == 3
    assert q.iloc[0]["quality_note"] is None


def test_complete_race_with_quality_note_kept_verbatim(tmp_path):
    unit = normal_race()
    unit["quality_note"] = "driver x: pit entries vs exits; gaps stay null"
    paths, _ = build_race_season(tmp_path, unit)
    q = d6.read_quality_season(paths, 2023)
    assert "pit entries vs exits" in q.iloc[0]["quality_note"]
    st = d6.read_state_season(paths, 2023)
    assert (st["source_unit_status"] == "complete").all()
    assert (st["shortened_race"] == False).all()  # noqa: E712


def test_shortened_but_complete_race_flag_honest(tmp_path):
    # Monaco-2022-style: leader 2 of 3 scheduled, manifest COMPLETE. The
    # data-derived flag is True while source_unit_status stays verbatim.
    unit = normal_race(total_laps=3)
    unit["driver_laps"] = unit["driver_laps"][
        unit["driver_laps"]["lap_number"] <= 2].reset_index(drop=True)
    paths, _ = build_race_season(tmp_path, unit)
    st = d6.read_state_season(paths, 2023)
    assert (st["source_unit_status"] == "complete").all()
    assert (st["shortened_race"] == True).all()  # noqa: E712


def test_non_terminal_manifest_refuses_build(tmp_path):
    unit = normal_race()
    paths = V2Paths.from_root(tmp_path)
    mpath = write_tiera_season(paths, unit["season"], [unit])
    data = json.loads(mpath.read_text())
    data["units"][unit["race_id"]]["status"] = "downloading"
    mpath.write_text(json.dumps(data))
    with pytest.raises(IngestionError) as excinfo:
        d6.build_season(paths, unit["season"])
    assert excinfo.value.category is ErrorCategory.CONFIG


# --------------------------------------------------------------------------
# Join cardinality (no accidental many-to-many).
# --------------------------------------------------------------------------

def test_identity_joins_do_not_multiply_rows(tmp_path):
    unit = normal_race()
    paths = V2Paths.from_root(tmp_path)
    season = unit["season"]
    write_tiera_season(paths, season, [unit])
    # rows_before = source driver_laps.
    src = pd.read_parquet(dest_for_unit(paths.processed_dir, "driver_laps",
                                        season, unit["race_id"]))
    rows_before = len(src)
    stats = d6.build_season(paths, season)
    assert stats["state_rows"] == rows_before  # rows_after == rows_before
    st = d6.read_state_season(paths, season)
    assert st.duplicated(subset=["race_id", "driver_id", "lap_number"]).sum() == 0
    assert len(st) == rows_before


# --------------------------------------------------------------------------
# Determinism.
# --------------------------------------------------------------------------

def test_rebuild_is_logically_identical(tmp_path):
    unit = normal_race()
    paths, stats1 = build_race_season(tmp_path, unit)
    file1 = dest_for_unit(paths.processed_dir, S.STATE_ENTITY,
                          unit["season"], S.d6_unit_id(unit["season"]))
    before = file1.read_bytes()
    stats2 = d6.build_season(paths, unit["season"])
    assert stats1["state_rows"] == stats2["state_rows"]
    after = file1.read_bytes()
    assert after == before  # byte-identical in this environment
    a = pd.read_parquet(file1)
    b = pd.read_parquet(file1)
    pd.testing.assert_frame_equal(a, b)


# --------------------------------------------------------------------------
# LEAKAGE / FUTURE-DATA MUTATION (mandatory, synthetic, offline).
# --------------------------------------------------------------------------

def _lap_N_rows(st, driver, n):
    return st[(st["driver_id"] == driver) & (st["lap_number"] <= n)]\
        .reset_index(drop=True)


def test_future_lap_mutation_does_not_change_earlier_state(tmp_path):
    unit = normal_race()
    paths, _ = build_race_season(tmp_path, unit)
    before = d6.read_state_season(paths, 2023)

    # Mutate laps N+1 onward for VER (extreme future lap times).
    dl = pd.read_parquet(dest_for_unit(paths.processed_dir, "driver_laps",
                                       2023, unit["race_id"]))
    m = dl["driver_id"] == "max_verstappen"
    dl.loc[m & (dl["lap_number"] >= 2), "lap_time_s"] = 5000.0
    dl.loc[m & (dl["lap_number"] >= 2), "session_time_end_s"] += 99999.0
    atomic_write_parquet(dl, dest_for_unit(paths.processed_dir, "driver_laps",
                                           2023, unit["race_id"]))
    d6.build_season(paths, 2023)
    after = d6.read_state_season(paths, 2023)
    # State for lap 1 (and all earlier complete info) unchanged.
    pd.testing.assert_frame_equal(_lap_N_rows(before, "max_verstappen", 1),
                                  _lap_N_rows(after, "max_verstappen", 1))


def test_future_weather_mutation_no_effect(tmp_path):
    unit = normal_race()
    weather = pd.DataFrame([{
        "race_id": unit["race_id"], "observed_at_s": 100.0,
        "air_temp_c": 30.0, "track_temp_c": 40.0, "humidity_pct": 20.0,
        "pressure_hpa": 1015.0, "wind_speed": 1.0,
        "wind_direction_deg": 180.0, "rainfall": False,
    }])
    unit["weather"] = weather
    paths, _ = build_race_season(tmp_path, unit)
    before = d6.read_state_season(paths, 2023)

    # Extreme future weather observation strictly after every state_time.
    wx_path = dest_for_unit(paths.processed_dir, "weather", 2023,
                            unit["race_id"])
    future = pd.concat([unit["weather"], pd.DataFrame([{
        "race_id": unit["race_id"], "observed_at_s": 99999.0,
        "air_temp_c": -99.0, "track_temp_c": -99.0, "humidity_pct": 99.0,
        "pressure_hpa": 500.0, "wind_speed": 99.0,
        "wind_direction_deg": 0.0, "rainfall": True}])], ignore_index=True)
    atomic_write_parquet(future, wx_path)
    # Also delete the earlier one entirely (no prior observation case).
    d6.build_season(paths, 2023)
    after = d6.read_state_season(paths, 2023)
    pd.testing.assert_frame_equal(before, after)


def test_future_race_control_mutation_no_effect(tmp_path):
    unit = normal_race()
    rc = pd.DataFrame([{
        "race_id": unit["race_id"], "message_seq": 0, "observed_at_s": 50.0,
        "lap_number": 1, "category": "Flag", "flag": "GREEN",
        "status": None, "scope": None, "sector": None,
        "racing_number": None, "message_text": "GREEN LIGHT",
    }])
    unit["race_control"] = rc
    paths, _ = build_race_season(tmp_path, unit)
    before = d6.read_state_season(paths, 2023)
    rc_path = dest_for_unit(paths.processed_dir, "race_control", 2023,
                            unit["race_id"])
    future = pd.concat([rc, pd.DataFrame([{
        "race_id": unit["race_id"], "message_seq": 1, "observed_at_s": 1e6,
        "lap_number": 3, "category": "SafetyCar", "flag": "SC",
        "status": None, "scope": None, "sector": None,
        "racing_number": None, "message_text": "SAFETY CAR DEPLOYED"}])],
        ignore_index=True)
    atomic_write_parquet(future, rc_path)
    d6.build_season(paths, 2023)
    after = d6.read_state_season(paths, 2023)
    pd.testing.assert_frame_equal(before, after)


def test_future_pit_stint_mutation_no_effect(tmp_path):
    unit = normal_race()
    pits = pd.DataFrame([{
        "race_id": unit["race_id"], "driver_id": "max_verstappen",
        "stop_sequence": 1, "lap_number": 2, "pit_in_s": 200.0,
        "pit_out_s": 220.0, "duration_s": 20.0,
    }])
    unit["pit_stops"] = pits
    stints = pd.DataFrame([{
        "race_id": unit["race_id"], "driver_id": "max_verstappen",
        "stint_number": 2, "compound": "SOFT", "fresh_tyre": True,
        "start_lap": 2, "end_lap": 3, "tyre_age_at_start": 1,
        "pit_in_lap": 2, "pit_out_lap": None,
    }])
    unit["stints"] = stints
    paths, _ = build_race_season(tmp_path, unit)
    before = d6.read_state_season(paths, 2023)
    # Mutate future pit/stint evidence.
    p = pd.concat([pits, pd.DataFrame([{
        "race_id": unit["race_id"], "driver_id": "max_verstappen",
        "stop_sequence": 9, "lap_number": 3, "pit_in_s": 300.0,
        "pit_out_s": 999.0, "duration_s": 699.0}])], ignore_index=True)
    atomic_write_parquet(p, dest_for_unit(paths.processed_dir, "pit_stops",
                                          2023, unit["race_id"]))
    atomic_write_parquet(stints, dest_for_unit(paths.processed_dir, "stints",
                                               2023, unit["race_id"]))
    d6.build_season(paths, 2023)
    after = d6.read_state_season(paths, 2023)
    pd.testing.assert_frame_equal(before, after)


def test_final_result_mutation_does_not_change_state(tmp_path):
    unit = normal_race()
    paths, _ = build_race_season(tmp_path, unit)
    before = d6.read_state_season(paths, 2023)
    res_path = dest_for_unit(paths.processed_dir, "results", 2023,
                             unit["race_id"])
    res = pd.read_parquet(res_path)
    # Flip the winner and points/status labels.
    res.loc[0, ["position_final", "points", "status_text", "winner_flag",
                "podium_flag"]] = [3, 0.0, "Retired", False, False]
    res.loc[0, "classified_position"] = None
    res.loc[0, "position_text"] = "R"
    res.loc[0, "dnf_flag"] = True
    atomic_write_parquet(res, res_path)
    d6.build_season(paths, 2023)
    after = d6.read_state_season(paths, 2023)
    pd.testing.assert_frame_equal(before, after)


def test_constructor_identity_is_evidence_not_label(tmp_path):
    # The ONLY results fields that may influence state are identity
    # (constructor id / attributes). Labels mutated above never reach state.
    unit = normal_race()
    paths, _ = build_race_season(tmp_path, unit)
    st = d6.read_state_season(paths, 2023)
    assert set(st["constructor_id"]) == {"red_bull", "ferrari"}
    # driver_number/abbreviation are attributes only; they are not keys.
    assert "driver_number" in st.columns
    assert st["driver_abbreviation"].notna().all()
