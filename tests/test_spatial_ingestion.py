"""P12-2 spatial ingestion tests (source-safe: fake sessions, tmp dirs).

No FastF1 cache, no network, no real telemetry. Corpus integration runs
outside CI via scripts/build_spatial_observations.py.
"""

import json
import sys
import types
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from raceintel.spatial import contracts as SC
from raceintel.spatial import ingestion as ING
from raceintel.spatial import manifest as SM
from raceintel.spatial import validation as V
from raceintel.spatial.io import (
    artifact_path,
    load_manifest,
    manifest_path,
    read_observations,
    save_manifest,
)

RACE = "2021-r05-R"


def _pos(rows):
    return pd.DataFrame(rows)


def _row(time_s, x, date, status="OnTrack", source="pos"):
    return {"Date": pd.Timestamp(date), "Status": status, "X": float(x),
            "Y": -9000.0, "Z": -100.0, "Source": source,
            "Time": pd.Timedelta(seconds=time_s),
            "SessionTime": pd.Timedelta(seconds=time_s)}


def _session(drivers, event_name="Monaco Grand Prix"):
    pos_data = {str(n): _pos(rows) for n, rows in drivers.items()}
    results = pd.DataFrame(
        [{"DriverNumber": n} for n in drivers])
    return types.SimpleNamespace(
        pos_data=pos_data, results=results,
        event={"EventName": event_name},
        t0_date=pd.Timestamp("2021-05-23T13:00:00"))


def _loader(session=None, error=None, calls=None):
    def load(season, round_no, cache_dir):
        if calls is not None:
            calls.append((season, round_no))
        if error is not None:
            raise error
        return session
    return load


def _ingest(tmp_path, session=None, error=None, race=RACE, season=2021,
            round_no=5, **kw):
    calls = []
    loader = _loader(session=session, error=error, calls=calls)
    result = ING.ingest_race(season, round_no, race, root=tmp_path,
                             cache_dir=tmp_path / "cache", loader=loader,
                             **kw)
    return result, calls


def _drivers(*numbers, per=3):
    out = {}
    for n in numbers:
        out[n] = [_row(4200.0 + i, -7000 - n * 10 - i,
                       f"2021-05-23T14:00:0{i}") for i in range(per)]
        # shift Date sub-second per driver for determinism
    return out


def test_session_time_conversion_deterministic():
    first = ING.session_time_s(pd.Timedelta(seconds=4207.125))
    second = ING.session_time_s(pd.Timedelta(seconds=4207.125))
    assert first == second == pytest.approx(4207.125)
    # pre-roll sentinels carry small negative Times: extraction passes
    # them through; P12-1 validation rules AFTER zero-fix exclusion.
    assert ING.session_time_s(pd.Timedelta(seconds=-7.47)) == \
        pytest.approx(-7.47)
    with pytest.raises(Exception):
        ING.session_time_s(pd.NaT)


def test_negative_time_sentinels_excluded_not_failed(tmp_path):
    # Corpus evidence (2018 streams): pre-roll (0,0,0) rows with small
    # negative Times are excluded by the sentinel rule, never persisted.
    pre = dict(_row(-7.47, 0, "2018-04-15T06:05:52.648"))
    pre.update({"Time": pd.Timedelta(seconds=-7.47),
                "SessionTime": pd.Timedelta(seconds=-7.47),
                "X": 0.0, "Y": 0.0, "Z": 0.0})
    rows = [pre] + [_row(1.0 + i, -7000 - i, f"2018-04-15T06:06:0{i}")
                    for i in range(2)]
    result, _ = _ingest(tmp_path, _session({44: rows}), season=2018,
                         round_no=3, race="2018-r03-R")
    assert result["status"] == SM.STATUS_COMPLETE
    assert result["stats"]["excluded_zero_fix_rows"] == 1
    frame = read_observations(artifact_path(tmp_path, "2018-r03-R"))
    assert (frame["observation_time_s"] >= 0).all()


def test_negative_time_track_position_fails_closed(tmp_path):
    # A negative Time on a NON-sentinel row still fails P12-1 validation.
    bad = _row(-7.47, -7000, "2018-04-15T06:05:52.648")
    bad.update({"Time": pd.Timedelta(seconds=-7.47),
                "SessionTime": pd.Timedelta(seconds=-7.47)})
    result, _ = _ingest(tmp_path, _session({44: [bad]}), season=2018,
                         round_no=3, race="2018-r03-R")
    assert result["status"] == SM.STATUS_FAILED


def test_driver_identity_from_string_keys(tmp_path):
    result, _ = _ingest(tmp_path, _session(_drivers(44, 33)))
    assert result["status"] == SM.STATUS_COMPLETE
    assert result["provenance"]["driver_numbers"] == [33, 44]


def test_non_numeric_driver_key_fails_closed(tmp_path):
    session = _session(_drivers(44))
    session.pos_data["VER"] = session.pos_data["44"]
    del session.pos_data["44"]
    result, _ = _ingest(tmp_path, session)
    assert result["status"] == SM.STATUS_FAILED


def test_duplicate_same_time_resolved_by_source_order(tmp_path):
    rows = [_row(4200.0, -7000, "2021-05-23T14:00:00.100"),
            _row(4200.0, -7001, "2021-05-23T14:00:00.900")]
    result, _ = _ingest(tmp_path, _session({44: rows}))
    assert result["status"] == SM.STATUS_COMPLETE
    frame = read_observations(artifact_path(tmp_path, RACE))
    assert len(frame) == 1
    assert int(frame.iloc[0]["x"]) == -7001
    assert result["stats"]["excluded_exact_duplicate_rows"] == 1


def test_exact_duplicate_rows_collapse(tmp_path):
    rows = [_row(4200.0, -7000, "2021-05-23T14:00:00.100"),
            _row(4200.0, -7000, "2021-05-23T14:00:00.100")]
    result, _ = _ingest(tmp_path, _session({44: rows}))
    assert result["status"] == SM.STATUS_COMPLETE
    assert result["stats"]["excluded_exact_duplicate_rows"] == 1


def test_conflicting_duplicate_fails_closed(tmp_path):
    rows = [_row(4200.0, -7000, "2021-05-23T14:00:00.100"),
            _row(4200.0, -7777, "2021-05-23T14:00:00.100")]
    result, _ = _ingest(tmp_path, _session({44: rows}))
    assert result["status"] == SM.STATUS_FAILED
    assert not artifact_path(tmp_path, RACE).exists()


def test_zero_sentinel_excluded_but_axis_zero_kept(tmp_path):
    rows = [_row(4200.0, 0, "2021-05-23T14:00:00.100"),  # x==0 kept
            _row(4201.0, -7000, "2021-05-23T14:00:00.200")]
    sentinel = dict(_row(4199.0, 0, "2021-05-23T14:00:00.050"))
    sentinel.update({"X": 0.0, "Y": 0.0, "Z": 0.0})
    result, _ = _ingest(tmp_path, _session({44: [sentinel] + rows}))
    assert result["status"] == SM.STATUS_COMPLETE
    assert result["stats"]["excluded_zero_fix_rows"] == 1
    frame = read_observations(artifact_path(tmp_path, RACE))
    assert len(frame) == 2
    assert ((frame["x"] == 0) & (frame["y"] == 0)
            & (frame["z"] == 0)).sum() == 0


def test_all_sentinel_race_fails_without_artifact(tmp_path):
    sentinel = dict(_row(4200.0, 0, "2021-05-23T14:00:00.100"))
    sentinel.update({"X": 0.0, "Y": 0.0, "Z": 0.0})
    result, _ = _ingest(tmp_path, _session({44: [sentinel]}))
    assert result["status"] == SM.STATUS_FAILED
    assert not artifact_path(tmp_path, RACE).exists()


def test_partial_when_driver_missing(tmp_path):
    session = _session(_drivers(44, 33))
    session.results = pd.DataFrame([{"DriverNumber": 44},
                                    {"DriverNumber": 33},
                                    {"DriverNumber": 77}])
    result, _ = _ingest(tmp_path, session)
    assert result["status"] == SM.STATUS_PARTIAL
    assert "77" in result["reason"]
    assert artifact_path(tmp_path, RACE).exists()
    manifest = SM.set_race_row(SM.new_manifest(), RACE, status="PARTIAL",
                               provenance=result["provenance"],
                               reason=result["reason"])
    SM.validate_manifest(manifest)


def test_empty_position_stream_unavailable(tmp_path):
    session = _session({})
    result, _ = _ingest(tmp_path, session)
    assert result["status"] == SM.STATUS_UNAVAILABLE
    assert not artifact_path(tmp_path, RACE).exists()


def test_missing_position_stream_unavailable(tmp_path):
    class _Missing:
        results = pd.DataFrame([{"DriverNumber": 44}])

        @property
        def pos_data(self):
            raise FakeDataNotLoaded("not loaded")

    class FakeDataNotLoaded(Exception):
        pass
    # FastF1 names the real error DataNotLoadedError; match by name.
    FakeDataNotLoaded.__name__ = "DataNotLoadedError"
    result, _ = _ingest(tmp_path, _Missing())
    assert result["status"] == SM.STATUS_UNAVAILABLE


def test_loader_error_failed_and_source_unavailable_mapped(tmp_path):
    result, _ = _ingest(tmp_path, error=RuntimeError("boom"))
    assert result["status"] == SM.STATUS_FAILED
    result, _ = _ingest(tmp_path,
                        error=ING.SourceUnavailable("no local source"))
    assert result["status"] == SM.STATUS_UNAVAILABLE


def test_wrapped_network_block_maps_to_unavailable(tmp_path):
    # HTTP clients wrap socket errors; the cause chain must still map
    # to UNAVAILABLE under cache-only (never FAILED, never downloaded).
    def wrapped_loader(season, round_no, cache_dir):
        try:
            raise ING._NetworkBlockedError("blocked")
        except ING._NetworkBlockedError as blocked:
            raise ConnectionError("fetch failed") from blocked

    with pytest.raises(ING.SourceUnavailable):
        ING.load_session(2021, 5, tmp_path, ING.SOURCE_MODE_CACHE_ONLY,
                         loader=wrapped_loader)


def test_cache_only_blocks_network_inside_loader(tmp_path):
    import socket

    def net_loader(season, round_no, cache_dir):
        socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        raise AssertionError("unreachable")

    with pytest.raises(ING.SourceUnavailable):
        ING.load_session(2021, 5, tmp_path, ING.SOURCE_MODE_CACHE_ONLY,
                         loader=net_loader)


def test_ingestion_import_does_not_require_fastf1():
    assert ING.SOURCE_MODE_CACHE_ONLY == "cache-only"
    assert ING.INGESTION_VERSION.startswith("p12-2-")


def test_logical_hash_stable_to_reordering_and_sensitive(tmp_path):
    result, _ = _ingest(tmp_path, _session(_drivers(44, 33)))
    frame = read_observations(artifact_path(tmp_path, RACE))
    first = V.logical_content_hash(frame)
    assert first == result["provenance"]["content_sha256"]
    assert V.logical_content_hash(frame.iloc[::-1]) == first
    changed = frame.copy()
    changed.loc[changed.index[0], "x"] = int(changed.iloc[0]["x"]) + 1
    assert V.logical_content_hash(changed) != first


def test_provenance_validates_and_has_no_absolute_paths(tmp_path):
    result, _ = _ingest(tmp_path, _session(_drivers(44, 33)))
    record = SM.validate_provenance(result["provenance"])
    assert record["schema_version"] == SC.SPATIAL_SCHEMA_VERSION
    assert record["season"] == 2021
    assert not record["source_input_ref"].startswith("/")
    assert record["round_no"] == 5
    assert record["event_name"] == "Monaco Grand Prix"
    assert "source_session_start_utc" in record


def test_atomic_write_replaces_only_after_validation(tmp_path):
    dest = artifact_path(tmp_path, RACE)
    result, _ = _ingest(tmp_path, _session(_drivers(44)))
    assert result["status"] == SM.STATUS_COMPLETE
    before = dest.read_bytes()
    leftovers = list(dest.parent.glob("*.tmp-*"))
    assert leftovers == []
    # failed rebuild keeps the known-good artifact byte-identical
    failed, _ = _ingest(tmp_path, error=RuntimeError("boom"))
    assert failed["status"] == SM.STATUS_FAILED
    assert dest.read_bytes() == before


def test_cli_resume_skips_rebuilds_and_recovers(tmp_path, monkeypatch,
                                                capsys):
    from scripts.build_spatial_observations import main as cli_main

    _fake_tiera_manifest(tmp_path, 2021, [5])
    for season in (2018, 2019, 2020, 2022, 2023, 2024, 2025):
        _fake_tiera_manifest(tmp_path, season, [1])
    calls: list = []

    def fake_loader(season, round_no, cache_dir):
        calls.append((season, round_no))
        return _session(_drivers(44, 33))

    monkeypatch.setattr(ING, "_default_loader", fake_loader)
    root = str(tmp_path)
    assert cli_main(["--root", root, "--race", RACE]) == 0
    assert len(calls) == 1
    # second run: verified COMPLETE is skipped without loading
    assert cli_main(["--root", root, "--race", RACE]) == 0
    assert len(calls) == 1
    out = capsys.readouterr().out
    assert "SKIP 2021-r05-R" in out
    # corrupt artifact: detected and rebuilt deterministically
    manifest = load_manifest(manifest_path(tmp_path))
    before = manifest["races"][RACE]["provenance"]["content_sha256"]
    artifact_path(tmp_path, RACE).write_bytes(b"corrupt-bytes")
    assert cli_main(["--root", root, "--race", RACE]) == 0
    assert len(calls) == 2
    manifest = load_manifest(manifest_path(tmp_path))
    assert manifest["races"][RACE]["provenance"]["content_sha256"] == before
    # stale manifest entry (bogus hash): rebuilt, same logical content
    row = dict(manifest["races"][RACE])
    prov = dict(row["provenance"])
    prov["content_sha256"] = "0" * 64
    row["provenance"] = prov
    manifest["races"][RACE] = row
    save_manifest(manifest, manifest_path(tmp_path))
    assert cli_main(["--root", root, "--race", RACE]) == 0
    assert len(calls) == 3
    manifest = load_manifest(manifest_path(tmp_path))
    assert manifest["races"][RACE]["provenance"]["content_sha256"] == before
    # explicit force rebuilds even when verified
    assert cli_main(["--root", root, "--race", RACE, "--force"]) == 0
    assert len(calls) == 4


def test_corrupt_artifact_detected_and_rebuilt(tmp_path):
    result, _ = _ingest(tmp_path, _session(_drivers(44, 33)))
    assert result["status"] == SM.STATUS_COMPLETE
    dest = artifact_path(tmp_path, RACE)
    dest.write_bytes(b"corrupt-bytes")
    assert ING.verify_complete_artifact(
        tmp_path, RACE, result["provenance"]) is False
    rebuilt, _ = _ingest(tmp_path, _session(_drivers(44, 33)))
    assert rebuilt["status"] == SM.STATUS_COMPLETE
    assert rebuilt["provenance"]["content_sha256"] == \
        result["provenance"]["content_sha256"]
    assert ING.verify_complete_artifact(
        tmp_path, RACE, rebuilt["provenance"]) is True


def test_hash_mismatch_detected(tmp_path):
    result, _ = _ingest(tmp_path, _session(_drivers(44, 33)))
    other, _ = _ingest(tmp_path, _session(_drivers(44, 77)),
                       race=RACE, season=2021, round_no=5)
    assert other["status"] == SM.STATUS_COMPLETE
    # provenance from a different dataset must not verify this artifact
    assert ING.verify_complete_artifact(
        tmp_path, RACE, result["provenance"]) is False


def test_manifest_io_deterministic(tmp_path):
    manifest = SM.new_manifest()
    result, _ = _ingest(tmp_path, _session(_drivers(44, 33)))
    manifest = SM.set_race_row(manifest, RACE, status=result["status"],
                               provenance=result["provenance"])
    first = save_manifest(manifest, manifest_path(tmp_path))
    reloaded = load_manifest(manifest_path(tmp_path))
    second = save_manifest(reloaded, manifest_path(tmp_path))
    assert first == second
    assert reloaded["races"][RACE]["status"] == SM.STATUS_COMPLETE


def test_failed_without_previous_row_recorded(tmp_path):
    manifest = SM.new_manifest()
    result, _ = _ingest(tmp_path, error=RuntimeError("boom"))
    updated, disposition = ING.apply_result(manifest, result, None)
    assert updated["races"][RACE]["status"] == SM.STATUS_FAILED
    assert "provenance" not in updated["races"][RACE]
    assert disposition == "recorded"


def test_failed_with_verified_previous_row_keeps_known_good(tmp_path):
    manifest = SM.new_manifest()
    good, _ = _ingest(tmp_path, _session(_drivers(44, 33)))
    manifest, _ = ING.apply_result(manifest, good, None)
    bad, _ = _ingest(tmp_path, error=RuntimeError("boom"))
    kept, disposition = ING.apply_result(manifest, bad,
                                        manifest["races"][RACE], tmp_path)
    assert kept["races"][RACE]["status"] == SM.STATUS_COMPLETE
    assert disposition == "kept-previous"


def test_failed_with_stale_previous_row_records_fresh(tmp_path):
    manifest = SM.new_manifest()
    good, _ = _ingest(tmp_path, _session(_drivers(44, 33)))
    manifest, _ = ING.apply_result(manifest, good, None)
    # artifact lost: the stale COMPLETE row must not mask the failure
    artifact_path(tmp_path, RACE).unlink()
    bad, _ = _ingest(tmp_path, error=RuntimeError("boom"))
    updated, disposition = ING.apply_result(manifest, bad,
                                           manifest["races"][RACE],
                                           tmp_path)
    assert updated["races"][RACE]["status"] == SM.STATUS_FAILED
    assert disposition == "recorded"


def _fake_tiera_manifest(tmp_path, season, rounds):
    path = (tmp_path / "data" / "v2" / "raw" / "manifests"
            / f"tiera-{season}.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    from raceintel import contracts as C

    units = {}
    for rnd in rounds:
        race_id = C.make_race_id(season, rnd)
        units[race_id] = {"round_no": rnd, "status": "complete"}
    path.write_text(json.dumps({"units": units}))


def test_discover_universe_from_local_tiera(tmp_path):
    for season, rounds in ((2018, [1, 2]), (2025, [1])):
        _fake_tiera_manifest(tmp_path, season, rounds)
    for season in (2019, 2020, 2021, 2022, 2023, 2024):
        _fake_tiera_manifest(tmp_path, season, [1])
    universe = ING.discover_universe(tmp_path)
    assert universe[0] == {"season": 2018, "round_no": 1,
                           "race_id": "2018-r01-R"}
    assert {"season": 2025, "round_no": 1,
            "race_id": "2025-r01-R"} in universe
    assert len(universe) == 2 + 1 + 6


def test_discover_universe_missing_manifest_fails(tmp_path):
    with pytest.raises(Exception):
        ING.discover_universe(tmp_path)


def test_data_allowed_vs_product_servable_2025():
    assert SC.is_data_ingestible(2025) is True
    assert SC.is_product_servable(2025) is False
    assert SC.is_product_servable(2024) is True
    import api.v2_service as svc

    assert 2025 not in tuple(svc.SERVED_SEASONS)
    assert tuple(svc.SERVED_SEASONS) == tuple(range(2018, 2025))


def test_new_modules_keep_predictive_firewall():
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    forbidden = ("raceintel.features", "raceintel.labels",
                 "raceintel.model_lab", "raceintel.simulation",
                 "raceintel.strategy", "raceintel.explainability",
                 "raceintel.prediction", "api.", "fastapi")
    for name in ("ingestion.py", "io.py"):
        text = (root / "raceintel" / "spatial" / name).read_text()
        for token in forbidden:
            assert f"import {token}" not in text
            assert f"from {token}" not in text
