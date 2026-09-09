"""D5 Tier-A tests: normalisation, identity, eligibility, failures — offline.

Every test uses small source-shaped DataFrames or fake sessions; FastF1 is
never loaded and the network is never touched (the loader gate refuses
without V2_ALLOW_NETWORK, and fakes bypass it). Real exception classes are
imported for failure-mapping tests (import is offline-safe).
"""

import sys
import types

import pandas as pd
import pytest

from v2 import contracts as C
from v2.cli import main as cli_main
from v2.config import V2Paths
from v2.errors import ErrorCategory
from v2.ingestion import run_unit
from v2.manifests import Manifest, UnitStatus
from v2.retry import RetryPolicy
from v2.runs import start_run
from v2.tiera import (
    LoadedRace,
    TIERA_ENTITIES,
    _ordered_stops,
    build_driver_index,
    code_str,
    discover_race_scope,
    load_race_session,
    make_tiera_race_adapter,
    normalize_driver_laps,
    normalize_race_control,
    normalize_results,
    normalize_weather,
    seconds_or_null,
)


TD = pd.Timedelta
NAT = pd.NaT

# --------------------------------------------------------------------------
# Fixture builders (FastF1-shaped).
# --------------------------------------------------------------------------

LAP_COLS = ["Time", "Driver", "DriverNumber", "LapTime", "LapNumber",
            "Stint", "PitOutTime", "PitInTime", "Sector1Time", "Sector2Time",
            "Sector3Time", "Sector1SessionTime", "Sector2SessionTime",
            "Sector3SessionTime", "SpeedI1", "SpeedI2", "SpeedFL",
            "SpeedST", "Compound", "TyreLife", "FreshTyre", "Team",
            "LapStartTime", "TrackStatus", "Position", "Deleted",
            "DeletedReason", "IsAccurate", "FastF1Generated"]


def lap_row(driver="VER", number="1", lap=1.0, team="Red Bull Racing",
            compound="SOFT", tyre_life=4.0, stint=1.0, position=1.0,
            lap_time_s=95.0, start_s=0.0, pit_in=False, pit_out=False,
            sector_s=30.0, speed=300.0, track="1", deleted=False,
            accurate=True, generated=False):
    base = start_s
    return {
        "Time": TD(seconds=base + lap_time_s), "Driver": driver,
        "DriverNumber": number, "LapTime": TD(seconds=lap_time_s),
        "LapNumber": float(lap), "Stint": float(stint),
        "PitOutTime": TD(seconds=base + 20) if pit_out else NAT,
        "PitInTime": TD(seconds=base + 10) if pit_in else NAT,
        "Sector1Time": TD(seconds=sector_s), "Sector2Time": TD(seconds=32.0),
        "Sector3Time": TD(seconds=33.0),
        "Sector1SessionTime": TD(seconds=base + sector_s),
        "Sector2SessionTime": TD(seconds=base + 62.0),
        "Sector3SessionTime": TD(seconds=base + lap_time_s),
        "SpeedI1": float(speed), "SpeedI2": 310.0, "SpeedFL": 320.0,
        "SpeedST": 330.0, "Compound": compound, "TyreLife": tyre_life,
        "FreshTyre": True, "Team": team,
        "LapStartTime": TD(seconds=base), "TrackStatus": track,
        "Position": position, "Deleted": deleted,
        "DeletedReason": "" if not deleted else "TRACK LIMITS",
        "IsAccurate": accurate, "FastF1Generated": generated,
    }


def laps_df(rows):
    full = [{c: r.get(c) for c in LAP_COLS} for r in rows]
    return pd.DataFrame(full)


RES_COLS = ["DriverNumber", "Abbreviation", "DriverId", "TeamName", "TeamId",
            "Position", "ClassifiedPosition", "GridPosition", "Q1", "Q2",
            "Q3", "Time", "Status", "Points", "Laps"]


def result_row(number="1", code="VER", slug="max_verstappen",
               team="red_bull", position=1.0, class_pos="1", grid=1.0,
               status="Finished", points=25.0, laps=57.0):
    return {"DriverNumber": number, "Abbreviation": code, "DriverId": slug,
            "TeamName": "Red Bull Racing", "TeamId": team,
            "Position": position, "ClassifiedPosition": class_pos,
            "GridPosition": grid, "Q1": TD(seconds=90.0),
            "Q2": TD(seconds=89.0), "Q3": TD(seconds=88.0),
            "Time": TD(seconds=5400.0), "Status": status, "Points": points,
            "Laps": laps}


def results_df(rows):
    return pd.DataFrame([{c: r.get(c) for c in RES_COLS} for r in rows])


def weather_df(n=3, rain=False):
    return pd.DataFrame([{
        "Time": TD(seconds=45 + 60 * i), "AirTemp": 29.8, "Humidity": 19.0,
        "Pressure": 1016.5, "Rainfall": bool(rain and i > 0),
        "TrackTemp": 35.1, "WindDirection": 176, "WindSpeed": 1.2,
    } for i in range(n)])


def rc_df():
    return pd.DataFrame([
        {"Time": pd.Timestamp("2023-03-05 14:04:34"), "Category": "Other",
         "Message": "PINK HEAD PADDING", "Status": None, "Flag": None,
         "Scope": None, "Sector": float("nan"), "RacingNumber": None,
         "Lap": 1},
        {"Time": pd.Timestamp("2023-03-05 14:20:00"), "Category": "Flag",
         "Message": "GREEN LIGHT", "Status": None, "Flag": "GREEN",
         "Scope": "Track", "Sector": 18.0, "RacingNumber": "44", "Lap": 5},
    ])


def scope_entry(fmt="conventional"):
    return {"season": 2023, "round_no": 1,
            "event_name": "Bahrain Grand Prix",
            "official_event_name": "Bahrain Grand Prix", "country": "Bahrain",
            "location": "Sakhir", "event_format": fmt, "f1_api_support": True}


def fake_loaded(laps, results, season=2023, round_no=1, total_laps=57,
                weather=None, rc=None, fmt="conventional"):
    return LoadedRace(
        season=season, round_no=round_no,
        scope_entry=scope_entry(fmt), laps=laps, results=results,
        weather=weather if weather is not None else weather_df(),
        race_control=rc if rc is not None else rc_df(),
        total_laps=total_laps, f1_api_support=True,
        t0_date=pd.Timestamp("2023-03-05 14:01:01"))


def write_d4(tmp_path, season=2023, drivers=("max_verstappen", "perez"),
             constructors=("red_bull",), circuit="bahrain"):
    base = V2Paths.from_root(tmp_path).processed_dir
    (base / "hist_drivers" / f"season={season}").mkdir(parents=True,
                                                      exist_ok=True)
    pd.DataFrame([{"driver_id": d} for d in drivers]).to_parquet(
        base / "hist_drivers" / f"season={season}" /
        f"hist_drivers__tierb-{season}.parquet")
    (base / "hist_constructors" / f"season={season}").mkdir(parents=True,
                                                           exist_ok=True)
    pd.DataFrame([{"constructor_id": c} for c in constructors]).to_parquet(
        base / "hist_constructors" / f"season={season}" /
        f"hist_constructors__tierb-{season}.parquet")
    (base / "hist_races" / f"season={season}").mkdir(parents=True,
                                                    exist_ok=True)
    pd.DataFrame([{"season": season, "round_no": 1,
                   "circuit_id": circuit}]).to_parquet(
        base / "hist_races" / f"season={season}" /
        f"hist_races__tierb-{season}.parquet")


def run_tiera(tmp_path, loaded, season=2023, round_no=1,
              max_attempts=2):
    paths = V2Paths.from_root(tmp_path)
    manifest = Manifest()
    manifest.plan_race_scope(season, [round_no],
                             schema_version=C.SCHEMA_VERSION)
    run = start_run(source="fastf1", source_lib_version="fastf1-3.7.0",
                    schema_version=C.SCHEMA_VERSION, scope={},
                    config_snapshot={"v2_root": "data/v2"})
    policy = RetryPolicy(max_attempts=max_attempts,
                         sleep_fn=lambda s: None)
    unit_id = C.make_race_id(season, round_no)
    outcome = run_unit(
        manifest, unit_id,
        make_tiera_race_adapter(lambda s, r, c: loaded, season, round_no),
        paths, run, policy)
    return outcome, manifest, paths


# --------------------------------------------------------------------------
# Normal race + sprint weekend.
# --------------------------------------------------------------------------

def test_normal_race_complete(tmp_path):
    laps = laps_df([lap_row(lap=1.0), lap_row(lap=2.0),
                    lap_row(driver="PER", number="11", lap=1.0,
                            position=2.0)])
    results = results_df([result_row(), result_row(
        number="11", code="PER", slug="perez", position=2.0, class_pos="2",
        grid=2.0, points=18.0)])
    write_d4(tmp_path)
    outcome, manifest, paths = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=2))
    assert outcome.status == UnitStatus.COMPLETE, outcome.message
    files = sorted(paths.processed_dir.rglob("*.parquet"))
    # write_d4 helper files share the tmp root: count Tier-A outputs only.
    tiera_files = [f for f in files if f.parent.parent.name in TIERA_ENTITIES]
    assert len(tiera_files) == 7  # all Tier-A entities, no telemetry shell
    assert {f.parent.parent.name for f in tiera_files} == set(TIERA_ENTITIES)
    laps_out = pd.read_parquet(paths.processed_dir / "driver_laps" /
                               "season=2023" /
                               "driver_laps__2023-r01-R.parquet")
    assert len(laps_out) == 3
    # Quali columns + total Time are out of contract scope: dropped.
    res_out = pd.read_parquet(paths.processed_dir / "results" /
                              "season=2023" / "results__2023-r01-R.parquet")
    assert len(res_out) == 2
    assert set(res_out.columns) == set(C.get_table("results").column_names())


def test_sprint_weekend_gp_race_unaffected(tmp_path):
    laps = laps_df([lap_row(lap=1.0)])
    results = results_df([result_row()])
    write_d4(tmp_path)
    outcome, _, paths = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=1, fmt="sprint"))
    assert outcome.status == UnitStatus.COMPLETE, outcome.message
    races = pd.read_parquet(paths.processed_dir / "races" / "season=2023" /
                            "races__2023-r01-R.parquet")
    assert races.iloc[0]["event_format"] == "sprint"  # format preserved


# --------------------------------------------------------------------------
# Missingness stays honest (Monaco-style).
# --------------------------------------------------------------------------

def test_missing_tyre_life_sector_trap_stay_null(tmp_path):
    row = lap_row()
    row["TyreLife"] = float("nan")
    row["Sector1Time"] = NAT
    row["Sector1SessionTime"] = NAT
    row["SpeedI1"] = float("nan")
    row["Compound"] = None
    laps = laps_df([row])
    results = results_df([result_row()])
    write_d4(tmp_path)
    outcome, _, paths = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=1))
    assert outcome.status == UnitStatus.COMPLETE, outcome.message
    out = pd.read_parquet(paths.processed_dir / "driver_laps" /
                          "season=2023" /
                          "driver_laps__2023-r01-R.parquet")
    assert out.iloc[0]["tyre_life"] is None or pd.isna(out.iloc[0][
        "tyre_life"])
    assert pd.isna(out.iloc[0]["sector_1_s"])
    assert pd.isna(out.iloc[0]["speed_i1_kmh"])
    assert out.iloc[0]["compound"] is None or pd.isna(
        out.iloc[0]["compound"])


def test_unknown_compound_preserved_with_note(tmp_path):
    row = lap_row(compound="SUPERSOFT")
    laps = laps_df([row])
    results = results_df([result_row()])
    write_d4(tmp_path)
    outcome, manifest, paths = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=1))
    # Unexpected source value stays visible and verbatim (never coerced);
    # output is otherwise complete, so the unit is COMPLETE with the note
    # persisted as quality provenance.
    assert outcome.status == UnitStatus.COMPLETE
    assert "SUPERSOFT" in outcome.message
    assert "SUPERSOFT" in manifest.get("2023-r01-R").quality_note
    out = pd.read_parquet(paths.processed_dir / "driver_laps" /
                          "season=2023" /
                          "driver_laps__2023-r01-R.parquet")
    assert out.iloc[0]["compound"] == "SUPERSOFT"  # never coerced


# --------------------------------------------------------------------------
# Retirements, pits, stints.
# --------------------------------------------------------------------------

def test_retired_driver_dnf_from_token_only(tmp_path):
    laps = laps_df([lap_row(lap=1.0), lap_row(driver="LEC", number="16",
                                             lap=1.0, position=20.0)])
    results = results_df([
        result_row(),
        result_row(number="16", code="LEC", slug="leclerc", position=20.0,
                   class_pos="R", grid=12.0, status="Engine", points=0.0,
                   laps=1.0),
        result_row(number="11", code="PER", slug="perez", position=12.0,
                   class_pos="12", grid=5.0, status="+1 Lap", points=0.0),
    ])
    write_d4(tmp_path, drivers=("max_verstappen", "perez", "leclerc"))
    outcome, _, paths = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=1))
    assert outcome.status == UnitStatus.COMPLETE, outcome.message
    out = pd.read_parquet(paths.processed_dir / "results" / "season=2023" /
                          "results__2023-r01-R.parquet")
    by_id = {r["driver_id"]: r for _, r in out.iterrows()}
    # Retired: official token R -> unclassified -> dnf True, number kept.
    assert by_id["leclerc"]["dnf_flag"] == True
    assert by_id["leclerc"]["classified_position"] is None or pd.isna(
        by_id["leclerc"]["classified_position"])
    assert by_id["leclerc"]["position_final"] == 20
    # Lapped finisher: classified -> dnf False (anti status-rule).
    assert by_id["perez"]["dnf_flag"] == False
    assert by_id["perez"]["classified_position"] == 12


def test_pit_in_out_pairing_and_stints(tmp_path):
    # VER-like 2-stop: in 14/out 15, in 36/out 37; stints 1/2/3. Session
    # times increase with lap so chronological pairing is unambiguous.
    def t0(lap):
        return (lap - 1.0) * 90.0

    rows = []
    for lap in (13.0, 14.0):
        rows.append(lap_row(lap=lap, start_s=t0(lap), stint=1.0,
                            tyre_life=4.0 + lap, pit_in=(lap == 14.0)))
    for lap in (15.0, 36.0):
        rows.append(lap_row(lap=lap, start_s=t0(lap), stint=2.0,
                            tyre_life=1.0, compound="SOFT",
                            pit_out=(lap == 15.0), pit_in=(lap == 36.0)))
    rows.append(lap_row(lap=37.0, start_s=t0(37.0), stint=3.0,
                        compound="HARD", tyre_life=1.0, pit_out=True))
    laps = laps_df(rows)
    results = results_df([result_row()])
    write_d4(tmp_path)
    outcome, _, paths = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=37))
    assert outcome.status == UnitStatus.COMPLETE, outcome.message
    pits = pd.read_parquet(paths.processed_dir / "pit_stops" /
                           "season=2023" / "pit_stops__2023-r01-R.parquet")
    assert len(pits) == 2
    assert pits.iloc[0]["lap_number"] == 14  # entry lap, not exit lap
    assert pits.iloc[0]["duration_s"] is not None
    assert (pits["duration_s"] > 0).all()  # chronological -> positive
    stints = pd.read_parquet(paths.processed_dir / "stints" /
                             "season=2023" / "stints__2023-r01-R.parquet")
    assert len(stints) == 3
    by_stint = {r["stint_number"]: r for _, r in stints.iterrows()}
    assert by_stint[1]["pit_in_lap"] is None or pd.isna(
        by_stint[1]["pit_in_lap"])
    assert by_stint[1]["pit_out_lap"] == 15
    assert by_stint[2]["pit_in_lap"] == 14
    assert by_stint[3]["pit_out_lap"] is None or pd.isna(
        by_stint[3]["pit_out_lap"])  # final stint per contract
    assert by_stint[3]["end_lap"] == 37
    assert by_stint[1]["tyre_age_at_start"] == 17  # source TyreLife kept


def test_stop_pairing_chronological_no_shift(tmp_path):
    # Mid-sequence missing exit: later pairs must not shift.
    def t0(lap):
        return (lap - 1.0) * 90.0

    rows = [lap_row(lap=10.0, start_s=t0(10.0), pit_in=True),
            lap_row(lap=11.0, start_s=t0(11.0), pit_out=True),
            lap_row(lap=20.0, start_s=t0(20.0), pit_in=True),  # exit missing
            lap_row(lap=30.0, start_s=t0(30.0), pit_in=True),
            lap_row(lap=31.0, start_s=t0(31.0), pit_out=True)]
    laps = laps_df(rows)
    index = {"1": {"driver_id": "max_verstappen", "team_id": "red_bull",
                   "code": "VER"}}
    stops, notes = _ordered_stops(laps, "2023-r01-R", index)
    paired = stops["max_verstappen"]
    assert [(p["in_lap"], p["out_lap"]) for p in paired] == [
        (10, 11), (20, None), (30, 31)]
    assert any("entries vs" in n for n in notes)  # mismatch stays visible


def test_stop_pairing_back_to_back_same_lap_stops(tmp_path):
    # Real-world consecutive stops can share an out/in lap number (a car
    # leaves the pits early in a lap and re-enters later in the same lap
    # before completing it, e.g. BOR 2025-r01). Lap-adjacency pairing
    # mis-mates these and manufactures negative durations; chronological
    # pairing must produce correct, positive-duration stops.
    def pit(time):
        return None if time is None else TD(seconds=time)

    rows = [
        lap_row(lap=2.0, pit_in=True),                  # entry stop1 4563
        lap_row(lap=3.0, pit_out=True, pit_in=True),    # exit s1 4577 + entry s2 4725
        lap_row(lap=4.0, pit_out=True, pit_in=True),    # exit s2 4741 + entry s3 4883
        lap_row(lap=5.0, pit_out=True),                 # exit s3 4897
    ]
    laps = laps_df(rows)
    laps.loc[0, "PitInTime"] = pit(4563.0)
    laps.loc[1, "PitOutTime"] = pit(4577.0)
    laps.loc[1, "PitInTime"] = pit(4725.0)
    laps.loc[2, "PitOutTime"] = pit(4741.0)
    laps.loc[2, "PitInTime"] = pit(4883.0)
    laps.loc[3, "PitOutTime"] = pit(4897.0)
    index = {"1": {"driver_id": "max_verstappen", "team_id": "red_bull",
                   "code": "VER"}}
    stops, notes = _ordered_stops(laps, "2023-r01-R", index)
    paired = stops["max_verstappen"]
    assert [(p["in_lap"], p["out_lap"]) for p in paired] == [
        (2, 3), (3, 4), (4, 5)]
    for p in paired:
        assert p["in_s"] is not None and p["out_s"] is not None
        assert p["out_s"] > p["in_s"]  # no negative/absurd durations
    assert not any("entries vs" in n for n in notes)


def test_pit_lane_start_exit_without_entry(tmp_path):
    # Red-flag/pit-lane-start style: exit with no entry. The exit stays in
    # pit_stops (lap_number null); the opening stint keeps pit_in null per
    # contract. Source-faithful anomaly -> COMPLETE with persisted quality
    # note (D5 adjudication: unusual facts alone never imply PARTIAL).
    rows = [lap_row(lap=1.0, pit_out=True), lap_row(lap=2.0)]
    laps = laps_df(rows)
    results = results_df([result_row()])
    write_d4(tmp_path)
    outcome, manifest, paths = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=2))
    assert outcome.status == UnitStatus.COMPLETE
    assert "entries vs" in manifest.get("2023-r01-R").quality_note
    pits = pd.read_parquet(paths.processed_dir / "pit_stops" /
                           "season=2023" / "pit_stops__2023-r01-R.parquet")
    assert len(pits) == 1
    assert pd.isna(pits.iloc[0]["lap_number"])
    assert pits.iloc[0]["pit_out_s"] is not None
    stints = pd.read_parquet(paths.processed_dir / "stints" /
                             "season=2023" / "stints__2023-r01-R.parquet")
    assert pd.isna(stints.iloc[0]["pit_in_lap"])


def test_pit_entry_without_exit_keeps_nulls(tmp_path):
    row = lap_row(pit_in=True)
    laps = laps_df([row])
    results = results_df([result_row()])
    write_d4(tmp_path)
    outcome, manifest, paths = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=1))
    # In-pit retirement: single entry with no exit is a real race fact kept
    # with nulls + quality note; unit is COMPLETE, never fabricated.
    assert outcome.status == UnitStatus.COMPLETE
    assert "entries vs" in manifest.get("2023-r01-R").quality_note
    pits = pd.read_parquet(paths.processed_dir / "pit_stops" /
                           "season=2023" / "pit_stops__2023-r01-R.parquet")
    assert len(pits) == 1
    assert pd.isna(pits.iloc[0]["pit_out_s"])
    assert pd.isna(pits.iloc[0]["duration_s"])


# --------------------------------------------------------------------------
# Weather, race control, shortened races.
# --------------------------------------------------------------------------

def test_weather_and_race_control(tmp_path):
    laps = laps_df([lap_row(lap=1.0)])
    results = results_df([result_row()])
    write_d4(tmp_path)
    outcome, _, paths = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=1,
                              weather=weather_df(3, rain=True)))
    assert outcome.status == UnitStatus.COMPLETE, outcome.message
    wx = pd.read_parquet(paths.processed_dir / "weather" / "season=2023" /
                         "weather__2023-r01-R.parquet")
    assert len(wx) == 3
    assert wx.iloc[0]["observed_at_s"] == 45.0  # session-relative kept
    assert bool(wx.iloc[2]["rainfall"]) is True  # source bool preserved
    assert wx.iloc[0]["wind_speed"] == 1.2  # stored verbatim (m/s per fastf1)
    rc = pd.read_parquet(paths.processed_dir / "race_control" /
                         "season=2023" / "race_control__2023-r01-R.parquet")
    assert list(rc["message_seq"]) == [0, 1]  # 0-based source order
    assert rc.iloc[1]["flag"] == "GREEN"
    assert rc.iloc[1]["sector"] == "18"  # int-like float rendered plain
    assert rc.iloc[1]["racing_number"] == 44
    assert rc.iloc[1]["observed_at_s"] == pytest.approx(
        (pd.Timestamp("2023-03-05 14:20:00")
         - pd.Timestamp("2023-03-05 14:01:01")).total_seconds())


def test_wet_race_compounds_and_rainfall(tmp_path):
    rows = [lap_row(lap=1.0, compound="WET"),
            lap_row(lap=2.0, compound="INTERMEDIATE")]
    laps = laps_df(rows)
    results = results_df([result_row()])
    write_d4(tmp_path)
    outcome, _, paths = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=2,
                              weather=weather_df(2, rain=True)))
    assert outcome.status == UnitStatus.COMPLETE, outcome.message
    out = pd.read_parquet(paths.processed_dir / "driver_laps" /
                          "season=2023" /
                          "driver_laps__2023-r01-R.parquet")
    assert sorted(out["compound"].tolist()) == ["INTERMEDIATE", "WET"]
    wx = pd.read_parquet(paths.processed_dir / "weather" / "season=2023" /
                         "weather__2023-r01-R.parquet")
    assert bool(wx.iloc[1]["rainfall"]) is True


def test_none_string_compound_is_missing(tmp_path):
    row = lap_row(compound="None")
    laps = laps_df([row])
    results = results_df([result_row()])
    write_d4(tmp_path)
    outcome, _, paths = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=1))
    # Monaco-style: source 'None' string is missingness, not a compound.
    assert outcome.status == UnitStatus.COMPLETE, outcome.message
    out = pd.read_parquet(paths.processed_dir / "driver_laps" /
                          "season=2023" /
                          "driver_laps__2023-r01-R.parquet")
    assert out.iloc[0]["compound"] is None or pd.isna(
        out.iloc[0]["compound"])


def test_shortened_race_is_partial_not_silent(tmp_path):
    laps = laps_df([lap_row(lap=1.0), lap_row(lap=2.0), lap_row(lap=3.0)])
    results = results_df([result_row(laps=3.0)])
    write_d4(tmp_path)
    outcome, _, _ = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=39))
    assert outcome.status == UnitStatus.PARTIAL
    assert "shortened race" in outcome.message


# --------------------------------------------------------------------------
# Identity: numbers don't identify; unresolved identity fails loudly.
# --------------------------------------------------------------------------

def test_driver_number_change_does_not_affect_identity(tmp_path):
    # Same slug, unusual number: identity follows DriverId, never number.
    laps = laps_df([lap_row(driver="VER", number="33", lap=1.0)])
    results = results_df([result_row(number="33")])
    write_d4(tmp_path)
    outcome, _, paths = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=1))
    assert outcome.status == UnitStatus.COMPLETE, outcome.message
    out = pd.read_parquet(paths.processed_dir / "driver_laps" /
                          "season=2023" /
                          "driver_laps__2023-r01-R.parquet")
    assert out.iloc[0]["driver_id"] == "max_verstappen"


def test_unresolved_driver_identity_is_flagged(tmp_path):
    laps = laps_df([lap_row(lap=1.0),
                    lap_row(driver="XXX", number="99", lap=1.0)])
    results = results_df([result_row()])
    write_d4(tmp_path)
    outcome, _, paths = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=2))
    assert outcome.status == UnitStatus.PARTIAL  # dropped + visible
    assert "99" in outcome.message
    out = pd.read_parquet(paths.processed_dir / "driver_laps" /
                          "season=2023" /
                          "driver_laps__2023-r01-R.parquet")
    assert len(out) == 1  # no guessed keys


def test_all_laps_unmapped_fails_validation(tmp_path):
    laps = laps_df([lap_row(driver="XXX", number="99", lap=1.0)])
    results = results_df([result_row()])
    write_d4(tmp_path)
    outcome, _, _ = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=1))
    assert outcome.status == UnitStatus.FAILED


def test_constructor_conflict_stays_visible(tmp_path):
    laps = laps_df([lap_row(lap=1.0)])
    results = results_df([result_row(team="red_bull")])
    # D4 knows only a different team: session keeps FastF1's, flags it as a
    # cross-source note. Output is complete -> COMPLETE + quality note.
    write_d4(tmp_path, constructors=("ferrari",))
    outcome, manifest, paths = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=1))
    assert outcome.status == UnitStatus.COMPLETE
    assert "constructor cross-check" in manifest.get("2023-r01-R").quality_note
    out = pd.read_parquet(paths.processed_dir / "results" / "season=2023" /
                          "results__2023-r01-R.parquet")
    assert out.iloc[0]["team_id_at_race"] == "red_bull"  # never overwritten


def test_unresolved_circuit_fails(tmp_path):
    laps = laps_df([lap_row(lap=1.0)])
    results = results_df([result_row()])
    # No D4 files at all: circuit unresolvable -> loud failure, no guess.
    outcome, _, _ = run_tiera(
        tmp_path, fake_loaded(laps, results, total_laps=1))
    assert outcome.status == UnitStatus.FAILED
    assert "circuit" in outcome.message


# --------------------------------------------------------------------------
# Discovery / eligibility.
# --------------------------------------------------------------------------

def _schedule_df(rows):
    cols = ["RoundNumber", "EventName", "EventFormat", "OfficialEventName",
            "Country", "Location", "F1ApiSupport"]
    return pd.DataFrame(rows, columns=cols)


def test_discover_skips_testing_keeps_sprint_sorted():
    sched = _schedule_df([
        {"RoundNumber": 0, "EventName": "Pre-Season Testing",
         "EventFormat": "testing", "OfficialEventName": "T",
         "Country": "Bahrain", "Location": "Sakhir", "F1ApiSupport": True},
        {"RoundNumber": 5, "EventName": "Miami Grand Prix",
         "EventFormat": "sprint", "OfficialEventName": "M",
         "Country": "USA", "Location": "Miami", "F1ApiSupport": True},
        {"RoundNumber": 1, "EventName": "Bahrain Grand Prix",
         "EventFormat": "conventional", "OfficialEventName": "B",
         "Country": "Bahrain", "Location": "Sakhir", "F1ApiSupport": True},
    ])
    scope = discover_race_scope(sched, 2023)
    assert [e["round_no"] for e in scope] == [1, 5]  # sorted, testing out
    assert scope[1]["event_format"] == "sprint"  # sprint race still ingested


# --------------------------------------------------------------------------
# Loader failure taxonomy (fake fastf1 module; offline).
# --------------------------------------------------------------------------

def _patch_fastf1(monkeypatch, get_session=None, schedule=None):
    import fastf1.core as real_core
    import fastf1.req as real_req

    fake = types.ModuleType("fastf1")
    if get_session is not None:
        fake.get_session = get_session
    monkeypatch.setitem(sys.modules, "fastf1", fake)
    # `from fastf1.req/core import ...` resolves via sys.modules without
    # touching the network; the fake parent is only attribute storage.
    monkeypatch.setitem(sys.modules, "fastf1.req", real_req)
    monkeypatch.setitem(sys.modules, "fastf1.core", real_core)
    import v2.tiera as tiera_mod

    monkeypatch.setattr(tiera_mod, "configure_fastf1_cache",
                        lambda directory: directory)
    if schedule is not None:
        monkeypatch.setattr(tiera_mod, "fetch_schedule",
                            lambda season: schedule)
    return fake


def _sched_one():
    return _schedule_df([{"RoundNumber": 1, "EventName": "Bahrain GP",
                          "EventFormat": "conventional",
                          "OfficialEventName": "B", "Country": "Bahrain",
                          "Location": "Sakhir", "F1ApiSupport": True}])


def test_loader_refuses_without_network_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv("V2_ALLOW_NETWORK", raising=False)
    with pytest.raises(Exception) as excinfo:
        load_race_session(2023, 1, tmp_path)
    assert getattr(excinfo.value, "category", None) is ErrorCategory.CONFIG


def test_loader_missing_round_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("V2_ALLOW_NETWORK", "1")
    _patch_fastf1(monkeypatch, schedule=_schedule_df([]))
    from v2.errors import IngestionError

    with pytest.raises(IngestionError) as excinfo:
        load_race_session(2023, 9, tmp_path)
    assert excinfo.value.category is ErrorCategory.MISSING_SESSION


def test_loader_empty_laps_is_skipped(tmp_path, monkeypatch):
    monkeypatch.setenv("V2_ALLOW_NETWORK", "1")
    _patch_fastf1(monkeypatch, schedule=_sched_one(),
                  get_session=lambda s, r, k: types.SimpleNamespace(
                      load=lambda **kw: None,
                      laps=pd.DataFrame(), results=results_df([]),
                      weather_data=weather_df(0),
                      race_control_messages=rc_df().iloc[0:0],
                      total_laps=57, f1_api_support=True,
                      t0_date=pd.Timestamp("2023-01-01")))
    from v2.errors import IngestionError

    with pytest.raises(IngestionError) as excinfo:
        load_race_session(2023, 1, tmp_path)
    assert excinfo.value.category is ErrorCategory.MISSING_SESSION


def test_loader_rejects_non_championship(tmp_path, monkeypatch):
    monkeypatch.setenv("V2_ALLOW_NETWORK", "1")
    _patch_fastf1(monkeypatch, schedule=_schedule_df(
        [{"RoundNumber": 1, "EventName": "Pre-Season Testing",
          "EventFormat": "testing", "OfficialEventName": "T",
          "Country": "X", "Location": "Y", "F1ApiSupport": True}]))
    from v2.errors import IngestionError

    with pytest.raises(IngestionError) as excinfo:
        load_race_session(2023, 1, tmp_path)
    assert excinfo.value.category is ErrorCategory.CONFIG


def test_loader_full_load_provides_t0(tmp_path, monkeypatch):
    # D5 uses the full default load so FastF1 derives Session.t0_date from
    # telemetry streams; race-control observed_at_s depends on t0_date to
    # convert absolute Utc source timestamps. Canonical storage never
    # receives telemetry (telemetry_summary is an unmaterialised shell).
    captured = {}

    def get_session(s, r, k):
        captured["session"] = types.SimpleNamespace(
            load=lambda **kw: captured.update(load_kwargs=kw),
            laps=laps_df([lap_row(lap=1.0)]), results=results_df([result_row()]),
            weather_data=weather_df(1),
            race_control_messages=rc_df().iloc[0:0],
            total_laps=1, f1_api_support=True,
            t0_date=pd.Timestamp("2023-01-01"))
        return captured["session"]

    monkeypatch.setenv("V2_ALLOW_NETWORK", "1")
    _patch_fastf1(monkeypatch, schedule=_sched_one(),
                  get_session=get_session)
    loaded = load_race_session(2023, 1, tmp_path)
    assert loaded.laps is not None
    assert captured["load_kwargs"] == {}  # full default load (telemetry on)
    assert loaded.t0_date == pd.Timestamp("2023-01-01")


def test_loader_rate_limit_is_transient(tmp_path, monkeypatch):
    import fastf1.req as real_req

    monkeypatch.setenv("V2_ALLOW_NETWORK", "1")

    def boom(s, r, k):
        raise real_req.RateLimitExceededError("slow down")

    _patch_fastf1(monkeypatch, schedule=_sched_one(), get_session=boom)
    from v2.errors import IngestionError

    with pytest.raises(IngestionError) as excinfo:
        load_race_session(2023, 1, tmp_path)
    assert excinfo.value.category is ErrorCategory.TRANSIENT


def test_loader_incomplete_load_is_transient(tmp_path, monkeypatch):
    import fastf1.core as real_core

    monkeypatch.setenv("V2_ALLOW_NETWORK", "1")

    def boom(s, r, k):
        raise real_core.DataNotLoadedError(
            "The data you are trying to access has not been loaded yet. "
            "See `Session.load`")

    _patch_fastf1(monkeypatch, schedule=_sched_one(), get_session=boom)
    from v2.errors import IngestionError

    with pytest.raises(IngestionError) as excinfo:
        load_race_session(2023, 1, tmp_path)
    assert excinfo.value.category is ErrorCategory.TRANSIENT


def test_loader_invalid_session_is_missing(tmp_path, monkeypatch):
    import fastf1.core as real_core

    monkeypatch.setenv("V2_ALLOW_NETWORK", "1")

    def boom(s, r, k):
        raise real_core.InvalidSessionError("no data")

    _patch_fastf1(monkeypatch, schedule=_sched_one(), get_session=boom)
    from v2.errors import IngestionError

    with pytest.raises(IngestionError) as excinfo:
        load_race_session(2023, 1, tmp_path)
    assert excinfo.value.category is ErrorCategory.MISSING_SESSION


# --------------------------------------------------------------------------
# Separation + availability + CLI gates.
# --------------------------------------------------------------------------

def test_label_separation_and_availability():
    laps_cols = set(C.get_table("driver_laps").column_names())
    assert not (laps_cols & {"dnf_flag", "winner_flag", "position_final"})
    avail = {c.name: c.availability for c in C.DRIVER_LAPS.columns}
    assert avail["lap_time_s"] is C.Availability.LAP_END
    assert avail["lap_start_s"] is C.Availability.LAP_START
    assert avail["compound"] is C.Availability.IN_LAP
    res_avail = {c.name: c.availability for c in C.RESULTS.columns}
    assert res_avail["points"] is C.Availability.LABEL_ONLY
    assert res_avail["status_text"] is C.Availability.LABEL_ONLY


def test_cli_fastf1_needs_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv("V2_ALLOW_NETWORK", raising=False)
    root = str(tmp_path)
    assert cli_main(["--root", root, "plan", "--season", "2023",
                     "--rounds", "1"]) == 0
    assert cli_main(["--root", root, "run", "--adapter", "fastf1",
                     "--all-pending"]) == 2


def test_cli_fastf1_rejects_tierb_units(tmp_path, monkeypatch):
    monkeypatch.setenv("V2_ALLOW_NETWORK", "1")
    root = str(tmp_path)
    assert cli_main(["--root", root, "plan-tierb",
                     "--seasons", "2023"]) == 0
    assert cli_main(["--root", root, "run", "--adapter", "fastf1",
                     "--all-pending"]) == 2


def test_build_driver_index_rejects_unkeyable():
    bad = results_df([result_row()])
    bad.loc[0, "DriverId"] = None
    from v2.errors import IngestionError

    with pytest.raises(IngestionError) as excinfo:
        build_driver_index(bad)
    assert excinfo.value.category is ErrorCategory.VALIDATION


def test_helpers_scalar_semantics():
    assert seconds_or_null(TD(seconds=95.5)) == 95.5
    assert seconds_or_null(pd.NaT) is None
    assert code_str(18.0) == "18"
    assert code_str("  ") is None
    assert C.make_race_id(2023, 1) == "2023-r01-R"
