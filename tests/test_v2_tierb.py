"""D4 Tier-B tests: normalisation, integrity, D3 integration — all offline.

Tiny Ergast-shaped fixtures exercise every contract table; a scripted fake
transport drives the season adapter through ``run_unit`` (COMPLETE /
PARTIAL / SKIPPED / resume). No live network anywhere.
"""

import json
import urllib.parse

import pandas as pd
import pytest

from raceintel import contracts as C
from raceintel.cli import main as cli_main
from raceintel.config import V2Paths
from raceintel.errors import ErrorCategory
from raceintel.data.ingestion import run_unit
from raceintel.data.jolpica import HttpResponse, JolpicaClient, JolpicaConfig
from raceintel.manifests import Manifest, UnitStatus
from raceintel.retry import RetryPolicy
from raceintel.runs import start_run
from raceintel.data.tierb import (TIERB_ENTITIES, check_integrity,
                      make_tierb_season_adapter, normalize_circuits,
                      normalize_constructors, normalize_drivers,
                      normalize_races, normalize_results, normalize_seasons,
                      normalize_standings, tierb_unit_id, to_float_or_null,
                      to_int_or_null)


# --------------------------------------------------------------------------
# Fixtures (source-shaped)
# --------------------------------------------------------------------------

def circuit_dict(cid="albert_park", name="Albert Park", locality="Melbourne",
                 country="Australia", lat="37.8497", long="144.968"):
    return {"circuitId": cid, "circuitName": name,
            "Location": {"lat": lat, "long": long, "locality": locality,
                         "country": country}}


def driver_dict(did="max_verstappen", code="VER", number="33",
                given="Max", family="Verstappen", dob="1997-09-30",
                nat="Dutch"):
    d = {"driverId": did, "givenName": given, "familyName": family,
         "dateOfBirth": dob, "nationality": nat}
    if code is not None:
        d["code"] = code
    if number is not None:
        d["permanentNumber"] = number
    return d


def constructor_dict(cid="red_bull", name="Red Bull", nat="Austrian"):
    return {"constructorId": cid, "name": name, "nationality": nat}


def schedule_race(season="2023", round_no="1", name="Bahrain Grand Prix",
                  cid="bahrain", date="2023-03-05"):
    return {"season": season, "round": round_no, "raceName": name,
            "Circuit": circuit_dict(cid, f"{name} Circuit"),
            "date": date}


def result_dict(did, cid, grid="1", position="1", position_text="1",
                points="25", laps="57", status="Finished"):
    return {"number": "1", "position": position, "positionText": position_text,
            "points": points,
            "Driver": driver_dict(did), "Constructor": constructor_dict(cid),
            "grid": grid, "laps": laps, "status": status}


def standings_env(entries, key, season="2023", round_no="2"):
    return {"MRData": {"xmlns": "", "series": "f1", "limit": "100",
                       "offset": "0", "total": "1",
                       "StandingsTable": {
                           "season": season,
                           "StandingsLists": [
                               {"season": season, "round": round_no,
                                key: entries}]}}}


def driver_standing(did, pos="1", points="575", wins="19"):
    return {"position": pos, "points": points, "wins": wins,
            "Driver": driver_dict(did),
            "Constructors": [constructor_dict("red_bull")]}


def constructor_standing(cid, pos="1", points="860", wins="21"):
    return {"position": pos, "points": points, "wins": wins,
            "Constructor": constructor_dict(cid)}


# --------------------------------------------------------------------------
# Scalar coercion
# --------------------------------------------------------------------------

def test_int_coercion_honest_nulls():
    assert to_int_or_null("1") == 1
    assert to_int_or_null(4) == 4
    assert to_int_or_null("0") == 0  # pit-lane-start grid is a real fact
    assert to_int_or_null("-1") is None  # Ergast missing-int sentinel
    assert to_int_or_null(-1) is None
    assert to_int_or_null("") is None
    assert to_int_or_null(None) is None
    assert to_int_or_null("R") is None  # classification codes are not ints
    assert to_int_or_null("abc") is None  # malformed -> null, never zero
    assert to_int_or_null(True) is None


def test_float_coercion():
    assert to_float_or_null("25") == 25.0
    assert to_float_or_null("7.5") == 7.5
    assert to_float_or_null("") is None
    assert to_float_or_null(None) is None
    assert to_float_or_null("N/A") is None


# --------------------------------------------------------------------------
# Entity normalisation
# --------------------------------------------------------------------------

def test_normalize_seasons():
    frame, dupes = normalize_seasons([2023, "2023"])
    assert len(frame) == 1 and dupes == 1
    assert frame.columns.tolist() == C.HIST_SEASONS.column_names()


def test_circuit_identity_is_slug_not_name():
    frame, dupes = normalize_circuits([
        circuit_dict("nurburgring", "Nürburgring"),
        circuit_dict("nurburgring", "Nurburgring GP-Strecke"),  # rename
        circuit_dict("spa", "Spa-Francorchamps"),
    ])
    assert len(frame) == 1 + 1 and dupes == 1  # rename forks no identity
    assert set(frame["circuit_id"]) == {"nurburgring", "spa"}
    assert frame["latitude"].iloc[0] == pytest.approx(37.8497)


def test_driver_identity_and_historical_gaps():
    frame, _ = normalize_drivers([
        driver_dict("fangio", code=None, number=None,  # pre-number era
                    dob=None),
        driver_dict("max_verstappen"),
    ])
    fangio = frame.set_index("driver_id").loc["fangio"]
    assert pd.isna(fangio["driver_code"])
    assert pd.isna(fangio["permanent_number"])
    assert pd.isna(fangio["date_of_birth"])
    assert frame.columns.tolist() == C.HIST_DRIVERS.column_names()


def test_constructors_season_scoped_no_name_merge():
    frame, _ = normalize_constructors(
        [constructor_dict("toro_rosso", "Toro Rosso"),
         constructor_dict("alphatauri", "AlphaTauri"),
         constructor_dict("team_lotus", "Team Lotus")], 2019)
    frame2, _ = normalize_constructors(
        [constructor_dict("toro_rosso", "Toro Rosso")], 2018)
    assert len(frame) == 3  # similar names never merged
    assert set(frame["constructor_id"]) == {"toro_rosso", "alphatauri",
                                            "team_lotus"}
    # Same slug across seasons = distinct rows (season in PK).
    assert frame2.iloc[0]["season"] == 2018


def test_race_normalization_missing_fields():
    frame, _ = normalize_races([
        schedule_race(),
        {"season": "2023", "round": "2", "raceName": None,
         "Circuit": {"circuitId": "jeddah"}, "date": None},
    ])
    assert len(frame) == 2
    assert pd.isna(frame.set_index("round_no").loc[2]["race_date"])
    assert frame.columns.tolist() == C.HIST_RACES.column_names()


def test_result_normalization_classification_semantics():
    races = [{"season": "2023", "round": "1", "Results": [
        result_dict("max_verstappen", "red_bull"),
        # Retired but classified: numeric position, non-Finished status.
        result_dict("perez", "red_bull", grid="2", position="18",
                    position_text="18", points="0", laps="40",
                    status="+2 Laps"),
        # Unclassified retirement: letter code, null position.
        result_dict("leclerc", "ferrari", grid="3", position="R",
                    position_text="R", points="0", laps="20",
                    status="Collision"),
        # Disqualified: classified nowhere, verbatim status kept.
        result_dict("hamilton", "mercedes", grid="0", position="D",
                    position_text="D", points="0", laps="57",
                    status="Disqualified"),
        # Historical sentinel grid + malformed value: nulls, never zero.
        result_dict("alonso", "aston_martin", grid="-1", position="4",
                    position_text="4", points="12", laps="57",
                    status="Finished"),
    ]}]
    frame, dupes = normalize_results(races)
    assert dupes == 0
    by_driver = frame.set_index("driver_id")
    assert by_driver.loc["perez"]["status"] == "+2 Laps"
    assert by_driver.loc["perez"]["position"] == 18
    assert pd.isna(by_driver.loc["leclerc"]["position"])
    assert by_driver.loc["leclerc"]["position_text"] == "R"
    assert by_driver.loc["hamilton"]["status"] == "Disqualified"
    assert by_driver.loc["hamilton"]["grid"] == 0  # pit-lane start kept
    assert pd.isna(by_driver.loc["alonso"]["grid"])  # sentinel -> null
    # Tier-B carries NO derived dnf boolean: verbatim only, by contract.
    assert "dnf_flag" not in frame.columns
    assert frame.columns.tolist() == C.HIST_RESULTS.column_names()


def test_result_label_availability_encoded_in_contract():
    table = C.get_table("hist_results")
    assert table.columns_with_availability(C.Availability.LABEL_ONLY) == [
        "position", "position_text", "points", "laps", "status"]
    assert "grid" in table.columns_with_availability(C.Availability.PRE_RACE)
    assert C.get_table("hist_standings").label_columns() != []


def test_standings_season_final_grain():
    frame, dupes = normalize_standings(
        [{"season": "2023", "round": "2",
          "DriverStandings": [driver_standing("max_verstappen")]}],
        [{"season": "2023", "round": "2",
          "ConstructorStandings": [constructor_standing("red_bull")]}],
        2023, 22)
    assert dupes == 0
    assert set(frame["standing_type"]) == {"driver", "constructor"}
    assert set(frame["round_no"]) == {22}  # season-final snapshot only
    row = frame.set_index("entrant_id").loc["max_verstappen"]
    assert row["standing_points"] == 575.0 and row["wins"] == 19
    assert frame.columns.tolist() == C.HIST_STANDINGS.column_names()


def test_all_frames_match_contract_columns_exactly():
    frames = {
        "hist_seasons": normalize_seasons([2023])[0],
        "hist_circuits": normalize_circuits([circuit_dict()])[0],
        "hist_drivers": normalize_drivers([driver_dict()])[0],
        "hist_constructors": normalize_constructors(
            [constructor_dict()], 2023)[0],
        "hist_races": normalize_races([schedule_race()])[0],
        "hist_results": normalize_results(
            [{"season": "2023", "round": "1",
              "Results": [result_dict("a", "b")]}])[0],
        "hist_standings": normalize_standings(
            [{"DriverStandings": [driver_standing("a")]}],
            [{"ConstructorStandings": [constructor_standing("b")]}],
            2023, 1)[0],
    }
    assert set(frames) == set(TIERB_ENTITIES)
    for entity, frame in frames.items():
        assert frame.columns.tolist() == C.get_table(entity).column_names(), \
            entity


# --------------------------------------------------------------------------
# Integrity: measured, never repaired
# --------------------------------------------------------------------------

def _clean_frames():
    return {
        "hist_seasons": normalize_seasons([2023])[0],
        "hist_circuits": normalize_circuits([circuit_dict("bahrain")])[0],
        "hist_drivers": normalize_drivers([driver_dict("a")])[0],
        "hist_constructors": normalize_constructors(
            [constructor_dict("b")], 2023)[0],
        "hist_races": normalize_races([schedule_race(cid="bahrain")])[0],
        "hist_results": normalize_results(
            [{"season": "2023", "round": "1",
              "Results": [result_dict("a", "b")]}])[0],
        "hist_standings": normalize_standings(
            [{"DriverStandings": [driver_standing("a", wins="1")]}],
            [{"ConstructorStandings": [constructor_standing("b",
                                                             wins="1")]}],
            2023, 1)[0],
    }


def test_integrity_clean_has_no_violations():
    report = check_integrity(_clean_frames())
    assert not report.has_violations()
    assert report.counts["hist_results"] == 1


def test_integrity_reports_orphans_without_manufacturing():
    frames = _clean_frames()
    ghost = pd.DataFrame([{"season": 2023, "round_no": 1,
                           "driver_id": "ghost_driver",
                           "constructor_id": "ghost_team",
                           "grid": 20, "position": None,
                           "position_text": "R", "points": 0.0,
                           "laps": 5, "status": "Accident"}])
    frames["hist_results"] = pd.concat([frames["hist_results"], ghost],
                                       ignore_index=True)
    before = len(frames["hist_drivers"])
    report = check_integrity(frames)
    assert report.has_violations()
    checks = {v["check"] for v in report.fk_violations}
    assert "results.driver_id -> drivers" in checks
    assert "results.constructor_id -> constructors(season)" in checks
    assert len(frames["hist_drivers"]) == before  # no parents manufactured


def test_integrity_reports_race_and_standings_orphans():
    frames = _clean_frames()
    frames["hist_races"] = pd.concat(
        [frames["hist_races"],
         pd.DataFrame([{"season": 2023, "round_no": 9,
                        "race_name": "X", "circuit_id": "ghost_circuit",
                        "race_date": None}])], ignore_index=True)
    report = check_integrity(frames)
    assert any(v["check"] == "races.circuit_id -> circuits"
               for v in report.fk_violations)


# --------------------------------------------------------------------------
# Adapter + D3 orchestration (fake transport, tmp roots)
# --------------------------------------------------------------------------

class FakeJolpica:
    """Scripted per-endpoint pages; records every URL (scope audit)."""

    def __init__(self, season="2023"):
        self.season = season
        self.calls: list[str] = []
        self.pages: dict[str, list] = {}

    def __call__(self, url, headers, timeout_s):
        self.calls.append(url)
        query = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)
        offset = int(query.get("offset", ["0"])[0])
        limit = int(query.get("limit", ["100"])[0] or 100)
        for key, page_list in self.pages.items():
            if key in url:
                idx = offset // limit if limit else 0
                return HttpResponse(
                    status=200,
                    body=json.dumps(page_list[min(idx, len(page_list) - 1)]
                                    ).encode(), headers={})
        return HttpResponse(status=404, body=b"{}", headers={})


def season_envelope(table_key, table_value, total, offset=0):
    return {"MRData": {"xmlns": "", "series": "f1", "limit": "100",
                       "offset": str(offset), "total": str(total),
                       table_key: table_value}}


def make_season_fake(results_pages=1, orphan_driver=False):
    fake = FakeJolpica()
    s = fake.season
    races = [schedule_race(s, "1", "Bahrain Grand Prix", "bahrain",
                           f"{s}-03-05"),
             schedule_race(s, "2", "Saudi Arabian Grand Prix", "jeddah",
                           f"{s}-03-19")]
    fake.pages[f"/{s}.json"] = [
        season_envelope("RaceTable", {"season": s, "Races": races}, total=2)]
    fake.pages["/drivers"] = [
        season_envelope("DriverTable",
                        {"season": s, "Drivers": [
                            driver_dict("max_verstappen"),
                            driver_dict("perez"),
                            driver_dict("leclerc")]}, total=3)]
    fake.pages["/constructors"] = [
        season_envelope("ConstructorTable",
                        {"season": s, "Constructors": [
                            constructor_dict("red_bull"),
                            constructor_dict("ferrari")]}, total=2)]
    r1 = [{"season": s, "round": "1", "Results": [
        result_dict("max_verstappen", "red_bull"),
        result_dict("perez", "red_bull", grid="2", position="2",
                    position_text="2", points="18", laps="57",
                    status="Finished"),
        result_dict("leclerc", "ferrari", grid="3", position="R",
                    position_text="R", points="0", laps="20",
                    status="Collision")]},
        {"season": s, "round": "2", "Results": [
            result_dict("max_verstappen", "red_bull"),
            result_dict("leclerc", "ferrari", grid="2", position="2",
                        position_text="2", points="18", laps="50",
                        status="Finished")]}]
    if orphan_driver:
        r1[0]["Results"].append(
            result_dict("ghost_driver", "ghost_team", grid="20",
                        position="R", position_text="R", points="0",
                        laps="5", status="Accident"))
    pages = [season_envelope("RaceTable", {"season": s, "Races": r1},
                             total=len(r1))]
    if results_pages > 1:  # overlapping second page: PK dedupe must hold
        pages.append(season_envelope(
            "RaceTable", {"season": s, "Races": [r1[1]]}, total=len(r1),
            offset=100))
    fake.pages["/results"] = pages
    fake.pages["/driverStandings"] = [standings_env(
        [driver_standing("max_verstappen"), driver_standing("perez", "2",
                                                            "285", "2"),
         driver_standing("leclerc", "3", "206", "0")],
        "DriverStandings", season=s, round_no="2")]
    fake.pages["/constructorStandings"] = [standings_env(
        [constructor_standing("red_bull"),
         constructor_standing("ferrari", "2", "406", "1")],
        "ConstructorStandings", season=s, round_no="2")]
    return fake


def make_unit_paths(tmp_path, seasons=(2023,)):
    paths = V2Paths.from_root(tmp_path)
    manifest = Manifest()
    manifest.plan_tierb_scope(list(seasons), schema_version=C.SCHEMA_VERSION)
    run = start_run(source="jolpica", source_lib_version="jolpica-client-1",
                    schema_version=C.SCHEMA_VERSION,
                    scope={"seasons": list(seasons)},
                    config_snapshot={"v2_root": "data/v2"})
    policy = RetryPolicy(max_attempts=2, sleep_fn=lambda s: None)
    return paths, manifest, run, policy


def test_season_adapter_complete_writes_seven_entities(tmp_path):
    fake = make_season_fake()
    config = JolpicaConfig(sleep_fn=lambda s: None, politeness_s=0.0)
    client = JolpicaClient(config=config, transport=fake)
    paths, manifest, run, policy = make_unit_paths(tmp_path)
    outcome = run_unit(manifest, "tierb-2023",
                       make_tierb_season_adapter(client, 2023),
                       paths, run, policy)
    assert outcome.status == UnitStatus.COMPLETE, outcome.message
    files = sorted(paths.processed_dir.rglob("*.parquet"))
    assert len(files) == 7  # one file per Tier-B entity
    assert all("season=2023" in str(f) for f in files)
    results = pd.read_parquet(
        paths.processed_dir / "hist_results" / "season=2023" /
        "hist_results__tierb-2023.parquet")
    assert len(results) == 5  # 3 + 2 rows across the two races
    assert manifest.get("tierb-2023").run_id == run.run_id


def test_overlapping_result_pages_dedupe_by_pk(tmp_path):
    fake = make_season_fake(results_pages=2)
    config = JolpicaConfig(sleep_fn=lambda s: None, politeness_s=0.0)
    client = JolpicaClient(config=config, transport=fake)
    paths, manifest, run, policy = make_unit_paths(tmp_path)
    outcome = run_unit(manifest, "tierb-2023",
                       make_tierb_season_adapter(client, 2023),
                       paths, run, policy)
    assert outcome.status == UnitStatus.COMPLETE, outcome.message
    results = pd.read_parquet(
        paths.processed_dir / "hist_results" / "season=2023" /
        "hist_results__tierb-2023.parquet")
    assert len(results) == 5  # no duplicate PK rows across pages


def test_source_anomaly_becomes_partial_with_output(tmp_path):
    fake = make_season_fake(orphan_driver=True)
    config = JolpicaConfig(sleep_fn=lambda s: None, politeness_s=0.0)
    client = JolpicaClient(config=config, transport=fake)
    paths, manifest, run, policy = make_unit_paths(tmp_path)
    outcome = run_unit(manifest, "tierb-2023",
                       make_tierb_season_adapter(client, 2023),
                       paths, run, policy)
    assert outcome.status == UnitStatus.PARTIAL
    assert "ghost_driver" in outcome.message
    assert len(sorted(paths.processed_dir.rglob("*.parquet"))) == 7


def test_empty_schedule_becomes_skipped(tmp_path):
    fake = FakeJolpica()
    fake.pages["/2023.json"] = [
        season_envelope("RaceTable", {"season": "2023", "Races": []},
                        total=0)]
    config = JolpicaConfig(sleep_fn=lambda s: None, politeness_s=0.0)
    client = JolpicaClient(config=config, transport=fake)
    paths, manifest, run, policy = make_unit_paths(tmp_path)
    outcome = run_unit(manifest, "tierb-2023",
                       make_tierb_season_adapter(client, 2023),
                       paths, run, policy)
    assert outcome.status == UnitStatus.SKIPPED
    assert list(paths.processed_dir.rglob("*.parquet")) == []


def test_complete_skip_idempotency(tmp_path):
    fake = make_season_fake()
    config = JolpicaConfig(sleep_fn=lambda s: None, politeness_s=0.0)
    client = JolpicaClient(config=config, transport=fake)
    paths, manifest, run, policy = make_unit_paths(tmp_path)
    adapter = make_tierb_season_adapter(client, 2023)
    first = run_unit(manifest, "tierb-2023", adapter, paths, run, policy)
    assert first.status == UnitStatus.COMPLETE
    calls_after_first = len(fake.calls)
    second = run_unit(manifest, "tierb-2023", adapter, paths, run, policy)
    assert second.status == UnitStatus.COMPLETE
    assert second.message.startswith("skip")
    assert len(fake.calls) == calls_after_first  # no new source traffic


def test_interrupted_ingestion_resumes(tmp_path):
    fake = make_season_fake()
    config = JolpicaConfig(sleep_fn=lambda s: None, politeness_s=0.0)
    client = JolpicaClient(config=config, transport=fake)
    paths, manifest, run, policy = make_unit_paths(tmp_path)
    manifest.transition("tierb-2023", UnitStatus.DOWNLOADING, run_id="dead")
    entry = manifest.get("tierb-2023")
    entry.claimed_at = "2020-01-01T00:00:00+00:00"  # crashed long ago
    assert manifest.recover_stale(max_age_s=60,
                                  now_iso="2026-09-08T00:00:00+00:00") == [
        "tierb-2023"]
    outcome = run_unit(manifest, "tierb-2023",
                       make_tierb_season_adapter(client, 2023),
                       paths, run, policy)
    assert outcome.status == UnitStatus.COMPLETE
    assert len(sorted(paths.processed_dir.rglob("*.parquet"))) == 7


def test_no_nested_retry_amplification(tmp_path):
    """Single retry budget: a configured 3-attempt operation must cost at
    most 3 HTTP requests, not 3 (client) x 3 (orchestration) = 9.

    The live Tier-B path uses the default single-attempt client; D3
    orchestration owns retries. Persistent 429s therefore surface as
    TRANSIENT once per orchestration attempt.
    """
    calls = []

    def always_429(url, headers, timeout_s):
        calls.append(url)
        return HttpResponse(status=429, body=b"{}", headers={})

    config = JolpicaConfig(sleep_fn=lambda s: None, politeness_s=0.0)
    client = JolpicaClient(config=config, transport=always_429)
    assert client.retry_policy.max_attempts == 1  # single-attempt default
    paths = V2Paths.from_root(tmp_path)
    manifest = Manifest()
    manifest.plan_tierb_scope([2023], schema_version=C.SCHEMA_VERSION)
    run = start_run(source="jolpica", source_lib_version="jolpica-client-1",
                    schema_version=C.SCHEMA_VERSION,
                    scope={"units": ["tierb-2023"]},
                    config_snapshot={"v2_root": "data/v2"})
    policy = RetryPolicy(max_attempts=3, sleep_fn=lambda s: None)
    outcome = run_unit(manifest, "tierb-2023",
                       make_tierb_season_adapter(client, 2023),
                       paths, run, policy)
    assert outcome.status == UnitStatus.FAILED
    assert len(calls) == 3  # one HTTP attempt per orchestration attempt


def test_tierb_unit_id_and_scope():
    assert tierb_unit_id(1950) == "tierb-1950"
    manifest = Manifest()
    assert manifest.plan_tierb_scope([1950, 2023],
                                     schema_version=1) == ["tierb-1950",
                                                           "tierb-2023"]
    assert manifest.get("tierb-1950").season == 1950


# --------------------------------------------------------------------------
# CLI: explicit scope, clear failures
# --------------------------------------------------------------------------

def test_plan_tierb_requires_explicit_seasons(tmp_path):
    assert cli_main(["--root", str(tmp_path), "plan-tierb"]) == 2
    assert cli_main(["--root", str(tmp_path), "plan-tierb",
                     "--seasons", "1949"]) == 2  # predates championship F1


def test_plan_tierb_then_status(tmp_path, capsys):
    root = str(tmp_path)
    assert cli_main(["--root", root, "plan-tierb",
                     "--seasons", "2023", "2024"]) == 0
    assert cli_main(["--root", root, "status"]) == 0
    assert "pending: 2" in capsys.readouterr().out


def test_run_jolpica_without_network_opt_in_fails_clearly(tmp_path,
                                                          monkeypatch):
    monkeypatch.delenv("V2_ALLOW_NETWORK", raising=False)
    root = str(tmp_path)
    assert cli_main(["--root", root, "plan-tierb",
                     "--seasons", "2023"]) == 0
    assert cli_main(["--root", root, "run", "--adapter", "jolpica",
                     "--all-pending"]) == 2  # CONFIG: network not opted in


def test_run_jolpica_rejects_non_tierb_units(tmp_path):
    root = str(tmp_path)
    assert cli_main(["--root", root, "plan", "--season", "2023",
                     "--rounds", "1"]) == 0
    assert cli_main(["--root", root, "run", "--adapter", "jolpica",
                     "--all-pending"]) == 2
