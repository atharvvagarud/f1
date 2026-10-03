"""P12-3 circuit geometry tests (source-safe: synthetic fixtures only).

No observation corpus, no Tier-A tables, no FastF1: synthetic loops
with stationary clusters, spikes, and excursions exercise the full
pipeline at small scale. Corpus integration runs outside CI via
scripts/build_spatial_geometry.py.
"""

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from raceintel.spatial import contracts as SC
from raceintel.spatial import geometry as G
from raceintel.spatial.io import (
    geometry_manifest_path,
    geometry_path,
    load_geometry_manifest,
    save_geometry_manifest,
    write_geometry_atomic,
)

RACE = "2021-r05-R"


def _loop_frame(n_laps=6, per_lap=300, radius=8000.0, noise=8.0,
                driver=44, seed=7):
    """Synthetic circular circuit: laps + garage cluster + spike."""
    rng = np.random.default_rng(seed)
    rows = []
    t = 1000.0
    for lap in range(n_laps):
        for i in range(per_lap):
            a = 2 * np.pi * (i / per_lap)
            off = rng.normal(0, noise, 2)
            rows.append({
                "race_id": RACE, "driver_number": driver,
                "observation_time_s": t,
                "x": int(radius * np.cos(a) + off[0]),
                "y": int(radius * np.sin(a) + off[1]),
                "z": 0, "source": "pos", "status": "OnTrack"})
            t += 90.0 / per_lap
    frame = pd.DataFrame(rows)
    frame["driver_number"] = frame["driver_number"].astype("int64")
    frame["observation_time_s"] = frame["observation_time_s"].astype(
        "float64")
    for c in ("x", "y", "z"):
        frame[c] = frame[c].astype("int64")
    return frame


def _with_dirt(frame):
    """Add garage cluster (stationary), a teleport spike, an excursion."""
    extra = []
    t0 = frame.observation_time_s.max() + 10
    for i in range(50):  # garage: same cell, stationary
        extra.append({"race_id": RACE, "driver_number": 44,
                      "observation_time_s": t0 + i,
                      "x": 0, "y": 0, "z": 0, "source": "pos",
                      "status": "OnTrack"})
    spike = frame.iloc[len(frame) // 2].copy()
    spike["observation_time_s"] += 0.25
    spike["x"] = 50000  # teleport, caught by spike rule
    extra.append(spike.to_dict())
    out = pd.concat([frame, pd.DataFrame(extra)], ignore_index=True)
    return out.sort_values(["driver_number",
                            "observation_time_s"]).reset_index(drop=True)


def test_contract_versions_declared():
    assert SC.SPATIAL_GEOMETRY_SCHEMA_VERSION == "spatial-geometry-v1"
    assert G.GEOMETRY_ALGORITHM_VERSION.startswith("p12-3-")
    assert G.GEOMETRY_MANIFEST_SCHEMA_VERSION.startswith(
        "spatial-geometry-manifest-")


def test_motion_steps_and_headings():
    frame = _loop_frame(n_laps=1, per_lap=60)
    work = G.add_motion(frame)
    assert (work.step.iloc[1:] > 0).all()
    assert np.isfinite(work[["hx", "hy"]].iloc[1:].to_numpy()).all()


def test_selection_excludes_stationary_and_spikes():
    frame = _with_dirt(_loop_frame(n_laps=2, per_lap=120))
    eligible, stats = G.select_eligible(frame)
    assert stats["source_rows"] == len(frame)
    assert stats["excluded_stationary"] >= 49  # garage cluster
    assert stats["excluded_spikes"] >= 1  # teleport + neighbors
    assert stats["eligible_rows"] == len(eligible)
    assert len(eligible) > 0


def test_reference_lap_found_on_synthetic_loop():
    frame = _with_dirt(_loop_frame())
    eligible, _ = G.select_eligible(frame)
    ref = G.find_reference_lap(frame, eligible)
    assert ref["driver_number"] == 44
    assert 60.0 <= ref["duration_s"] <= 300.0
    assert 20000.0 <= ref["path_units"] <= 90000.0
    assert len(ref["trace"]) > 100


def test_anchor_support_rejects_shortcut():
    # faithful loop scores ~1; a chord across empty space scores low
    rng = np.random.default_rng(11)
    a = np.linspace(0, 2 * np.pi, 400)
    loop = np.stack([8000 * np.cos(a), 8000 * np.sin(a)], 1)
    P = np.vstack([loop + rng.normal(0, 8, loop.shape)
                   for _ in range(6)])
    assert G.anchor_support_frac(loop, P) > 0.97
    shortcut = np.vstack([loop[:100],
                          np.linspace(loop[100], loop[300], 30)[1:-1],
                          loop[300:]])
    assert G.anchor_support_frac(shortcut, P) < 0.97


def test_reference_fails_closed_without_loops():
    rows = [{"race_id": RACE, "driver_number": 44,
             "observation_time_s": float(i),
             "x": i * 100, "y": 0, "z": 0, "source": "pos",
             "status": "OnTrack"} for i in range(200)]
    frame = pd.DataFrame(rows)
    eligible, _ = G.select_eligible(frame)
    with pytest.raises(G.GeometryError):
        G.find_reference_lap(frame, eligible)


def test_resample_arc_closed_and_deterministic():
    xy = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 5.0], [0.0, 5.0]])
    first, total = G.resample_arc(xy, 8)
    second, _ = G.resample_arc(xy, 8)
    assert first.shape == (8, 2)
    assert np.array_equal(first, second)
    assert total == pytest.approx(30.0)


def test_resample_open_no_closure_chord():
    xy = np.array([[0.0, 0.0], [10.0, 0.0], [10.0, 10.0]])
    out = G.resample_open(xy, 5)
    assert out.shape == (5, 2)
    assert np.allclose(out[0], [0, 0]) and np.allclose(out[-1], [10, 10])
    with pytest.raises(G.GeometryError):
        G.resample_open(np.zeros((4, 2)), 4)


def test_heading_gated_assignment_separates_arms():
    # two parallel opposite-direction arms 200u apart
    ahead = np.stack([np.linspace(0, 1000, 50), np.zeros(50)], 1)
    back = np.stack([np.linspace(1000, 0, 50), np.full(50, 200.0)], 1)
    anchors = np.vstack([ahead[::5], back[::5]])
    P = np.vstack([ahead, back])
    H = np.vstack([np.tile([1.0, 0.0], (50, 1)),
                   np.tile([-1.0, 0.0], (50, 1))])
    lab = G.assign_bins(P, H, anchors)
    # forward arm points land on forward anchors (first half) and back
    # arm points on back anchors (second half)
    assert (lab[:50] < 10).all()
    assert (lab[50:] >= 10).all()


def test_bin_median_resists_minority():
    rng = np.random.default_rng(3)
    P = np.vstack([rng.normal([0, 0], 5, (90, 2)),
                   np.array([[500.0, 500.0]] * 10)])
    med, cov = G.bin_centerline(P, np.zeros(len(P), dtype=int), 4)
    assert abs(med[0, 0]) < 50 and abs(med[0, 1]) < 50
    assert cov[0] == 100


def test_interpolate_closed_wraps():
    xy = np.array([[0.0, 0.0], [np.nan, np.nan], [10.0, 0.0],
                   [np.nan, np.nan]])
    out = G.interpolate_closed(xy)
    assert np.isfinite(out).all()
    assert out[1, 0] == pytest.approx(5.0)
    with pytest.raises(G.GeometryError):
        G.interpolate_closed(np.full((4, 2), np.nan))


def test_extract_main_trace_validates():
    frame = _with_dirt(_loop_frame())
    trace, info = G.extract_main_trace(frame)
    assert trace["raw_centerline"].shape == (G.N_RENDER, 2)
    assert info["eligible_rows"] > 0
    C = trace["raw_centerline"]
    segs = np.hypot(*np.diff(np.vstack([C, C[:1]]), axis=0).T)
    assert segs[-1] < 5 * np.median(segs[:-1])


def test_transform_aspect_and_bounds():
    raw = np.array([[0.0, 0.0], [2000.0, 0.0], [2000.0, 1000.0],
                    [0.0, 1000.0]])
    tr = G.compute_transform(raw)
    assert tr["rotation_deg"] == 0.0 and tr["y_down"] is True
    out = G.apply_transform(raw, tr)
    assert ((out >= 0).all() and (out <= 1).all())
    # aspect preserved: 2:1 rectangle stays 2:1 in render space
    w = out[:, 0].max() - out[:, 0].min()
    h = out[:, 1].max() - out[:, 1].min()
    assert w / h == pytest.approx(2.0)
    back = G.invert_transform(out, tr)
    assert np.allclose(back, raw, atol=1e-9)
    with pytest.raises(G.GeometryError):
        G.compute_transform(np.zeros((4, 2)))


def test_pit_deferred_without_windows():
    pit, info = G.pit_centerline([], np.zeros((8, 2)))
    assert pit is None
    assert info["pit_status"] == G.PIT_DEFERRED


def test_pit_supported_on_synthetic_branch():
    main = np.stack([np.linspace(-2000, 10000, 240),
                     np.zeros(240)], 1)
    rng = np.random.default_rng(5)
    # production windows include margin seconds on the main line before
    # entry and after exit; the median path therefore starts/ends on it
    paths = []
    for _ in range(4):
        lane = (np.stack([np.linspace(0, 2000, 40),
                          np.full(40, 400.0)], 1)
                + rng.normal(0, 5, (40, 2)))
        lead = np.stack([np.linspace(-800, 0, 12), np.zeros(12)], 1)
        tail = np.stack([np.linspace(2000, 2800, 12), np.zeros(12)], 1)
        paths.append(np.vstack([lead, lane, tail]))
    pit, info = G.pit_centerline(paths, main)
    assert pit is not None
    assert info["pit_status"] == G.PIT_SUPPORTED
    assert pit["raw_path"].shape == (128, 2)


def test_pit_deferred_on_bad_connection():
    main = np.stack([np.linspace(0, 10000, 200),
                     np.zeros(200)], 1)
    paths = [np.stack([np.linspace(0, 2000, 40),
                       np.full(40, 9000.0)], 1) for _ in range(4)]
    pit, info = G.pit_centerline(paths, main)
    assert pit is None
    assert info["pit_status"] == G.PIT_DEFERRED


def test_pit_windows_ignore_frozen_fallback():
    # Corpus evidence (2019-r20-R): while boxed under GPS-denying
    # structures the feed parks on one fallback cell shared across all
    # stops, then teleports on reacquire. Window collection must keep
    # moving samples only so the median stays on the lane.
    import pandas as pd

    rows = []
    for drv in (44, 33, 77):
        t = 5000.0
        for i in range(60):  # entry + lane, moving
            rows.append({"race_id": RACE, "driver_number": drv,
                         "observation_time_s": t,
                         "x": -800 + i * 30, "y": 400, "z": 0,
                         "source": "pos", "status": "OnTrack"})
            t += 0.3
        for _ in range(60):  # boxed: shared fallback freeze
            rows.append({"race_id": RACE, "driver_number": drv,
                         "observation_time_s": t,
                         "x": -7917, "y": -6103, "z": 0,
                         "source": "pos", "status": "OnTrack"})
            t += 0.3
        for i in range(20):  # exit, moving
            rows.append({"race_id": RACE, "driver_number": drv,
                         "observation_time_s": t,
                         "x": 1000 + i * 30, "y": 350, "z": 0,
                         "source": "pos", "status": "OnTrack"})
            t += 0.3
    frame = pd.DataFrame(rows)
    stops = pd.DataFrame([{
        "race_id": RACE, "driver_id": f"d{drv}", "stop_sequence": 1,
        "lap_number": 10, "pit_in_s": 5000.0, "pit_out_s": 5036.0}
        for drv in (44, 33, 77)])
    results = pd.DataFrame([{
        "race_id": RACE, "driver_id": f"d{drv}",
        "driver_number": drv} for drv in (44, 33, 77)])
    import tempfile

    with tempfile.TemporaryDirectory() as tmp:
        base = (Path(tmp) / "data" / "v2" / "processed")
        (base / "pit_stops" / "season=2021").mkdir(parents=True)
        (base / "results" / "season=2021").mkdir(parents=True)
        stops.to_parquet(base / "pit_stops" / "season=2021"
                         / f"pit_stops__{RACE}.parquet")
        results.to_parquet(base / "results" / "season=2021"
                           / f"results__{RACE}.parquet")
        paths, info = G.collect_pit_windows(RACE, frame, tmp)
    assert info["windows"] == 3
    for p in paths:
        assert not ((p[:, 0] == -7917) & (p[:, 1] == -6103)).any()


def test_collect_pit_windows_missing_tables_defers(tmp_path):
    frame = _loop_frame(n_laps=1, per_lap=60)
    paths, info = G.collect_pit_windows(RACE, frame, tmp_path)
    assert paths == []
    assert "deferred" in info["note"]


def _built_record(**over):
    frame = _with_dirt(_loop_frame())
    record = G.build_geometry(RACE, frame, data_root=None)
    record["source"]["observation_content_sha256"] = "a" * 64
    record["content_sha256"] = G.geometry_content_hash(record)
    record.update(over)
    return record, frame


def test_build_geometry_validates_and_hashes():
    record, _ = _built_record()
    report = G.validate_geometry(record)
    assert report["race_id"] == RACE
    assert report["n_points"] == G.N_RENDER
    assert record["pit_status"] == G.PIT_DEFERRED  # no Tier-A tables
    assert record["pit_defer_reason"] != ""
    assert G.geometry_content_hash(record) == record["content_sha256"]


def test_content_hash_stable_and_sensitive():
    record, _ = _built_record()
    first = G.geometry_content_hash(record)
    clone = json.loads(json.dumps(record))
    assert G.geometry_content_hash(clone) == first
    clone["main_track"]["points"][0][0] += 0.5
    assert G.geometry_content_hash(clone) != first


def test_validate_geometry_failures():
    record, _ = _built_record()
    bad = json.loads(json.dumps(record))
    bad["schema_version"] = "nope"
    with pytest.raises(G.GeometryError):
        G.validate_geometry(bad)
    bad = json.loads(json.dumps(record))
    bad["main_track"]["points"] = bad["main_track"]["points"][:10]
    bad["main_track"]["raw_points"] = bad["main_track"]["raw_points"][:10]
    with pytest.raises(G.GeometryError):
        G.validate_geometry(bad)
    bad = json.loads(json.dumps(record))
    bad["transform"]["scale"] = -1.0
    with pytest.raises(G.GeometryError):
        G.validate_geometry(bad)
    bad = json.loads(json.dumps(record))
    bad["transform"]["rotation_deg"] = 15.0
    with pytest.raises(G.GeometryError):
        G.validate_geometry(bad)
    bad = json.loads(json.dumps(record))
    bad["main_track"]["points"][0] = [9.9, 9.9]
    with pytest.raises(G.GeometryError):
        G.validate_geometry(bad)
    bad = json.loads(json.dumps(record))
    bad["content_sha256"] = "0" * 64
    with pytest.raises(G.GeometryError):
        G.validate_geometry(bad)


def test_atomic_write_and_manifest_roundtrip(tmp_path):
    record, _ = _built_record()
    dest = geometry_path(tmp_path, RACE)
    file_hash = write_geometry_atomic(record, dest)
    assert dest.is_file()
    assert not list(dest.parent.glob("*.tmp-*"))
    reread = json.loads(dest.read_text())
    assert G.validate_geometry(reread)["race_id"] == RACE
    manifest = load_geometry_manifest(geometry_manifest_path(tmp_path))
    manifest = G.set_geometry_row(
        manifest, RACE, status=G.GEOMETRY_STATUS_COMPLETE,
        source_content_sha256="a" * 64,
        geometry_sha256=record["content_sha256"],
        n_points=record["main_track"]["n_points"],
        pit_status=record["pit_status"])
    identity = save_geometry_manifest(manifest,
                                      geometry_manifest_path(tmp_path))
    reloaded = load_geometry_manifest(geometry_manifest_path(tmp_path))
    assert reloaded["races"][RACE]["status"] == "COMPLETE"
    assert save_geometry_manifest(reloaded,
                                 geometry_manifest_path(tmp_path)) == identity
    assert G.verify_geometry_artifact(
        dest.parent, RACE, reloaded["races"][RACE], "a" * 64) is True
    again = write_geometry_atomic(record, dest)
    assert again == file_hash  # deterministic bytes
    # tampered coordinates detected (content hash mismatch)
    tampered = json.loads(dest.read_text())
    tampered["main_track"]["points"][0][0] += 1.0
    dest.write_text(json.dumps(tampered, sort_keys=True, indent=2) + "\n")
    assert G.verify_geometry_artifact(
        dest.parent, RACE, reloaded["races"][RACE], "a" * 64) is False


def test_manifest_row_rules():
    manifest = G.new_geometry_manifest()
    with pytest.raises(Exception):
        G.set_geometry_row(manifest, RACE,
                           status=G.GEOMETRY_STATUS_COMPLETE)
    failed = G.set_geometry_row(manifest, RACE,
                                status=G.GEOMETRY_STATUS_FAILED,
                                reason="no reference")
    assert failed["races"][RACE]["status"] == "FAILED"
    skipped = G.set_geometry_row(manifest, RACE,
                                 status=G.GEOMETRY_STATUS_SKIPPED,
                                 reason="source FAILED")
    assert skipped["races"][RACE]["status"] == "SKIPPED"
    with pytest.raises(Exception):
        G.validate_geometry_manifest({"nope": True})


def test_stale_source_detected(tmp_path):
    record, _ = _built_record()
    write_geometry_atomic(record, geometry_path(tmp_path, RACE))
    row = {"status": "COMPLETE", "source_content_sha256": "b" * 64,
           "geometry_sha256": record["content_sha256"]}
    assert G.verify_geometry_artifact(
        geometry_path(tmp_path, RACE).parent, RACE, row, "a" * 64) is False


def test_cli_list_and_skipped(tmp_path, capsys):
    from scripts.build_spatial_geometry import main as cli_main

    obs_dir = tmp_path / "data" / "spatial" / "observations"
    obs_dir.mkdir(parents=True)
    obs_manifest = {"manifest_schema_version": "spatial-manifest-v1",
                    "spatial_schema_version": "spatial-observation-v1",
                    "races": {
                        RACE: {"status": "COMPLETE", "provenance": {
                            "schema_version": "spatial-observation-v1",
                            "fastf1_version": "3.7.0",
                            "source_stream": "position", "season": 2021,
                            "race_id": RACE, "session": "R",
                            "source_input_ref": "x",
                            "raw_row_count": 10, "kept_row_count": 10,
                            "excluded_zero_fix_rows": 0,
                            "excluded_exact_duplicate_rows": 0,
                            "driver_count": 1, "driver_numbers": [44],
                            "expected_driver_numbers": [44],
                            "time_min_s": 1.0, "time_max_s": 9.0,
                            "observed_source_values": ["pos"],
                            "observed_status_values": ["OnTrack"],
                            "content_sha256": "c" * 64}}}}
    man_dir = tmp_path / "data" / "spatial" / "manifests"
    man_dir.mkdir(parents=True, exist_ok=True)
    (man_dir / "spatial_manifest.json").write_text(
        json.dumps(obs_manifest))
    assert cli_main(["--root", str(tmp_path), "--list"]) == 0
    assert RACE in capsys.readouterr().out
    # source FAILED -> geometry SKIPPED, never fabricated
    obs_manifest["races"][RACE] = {"status": "FAILED",
                                   "reason": "no stream"}
    (man_dir / "spatial_manifest.json").write_text(
        json.dumps(obs_manifest))
    assert cli_main(["--root", str(tmp_path)]) == 0
    geo = load_geometry_manifest(geometry_manifest_path(tmp_path))
    assert geo["races"][RACE]["status"] == "SKIPPED"


def test_geometry_scope_per_race_and_2025():
    from raceintel.spatial import contracts as SC

    record, _ = _built_record()
    assert record["layout_scope"] == "per-race"
    assert SC.is_data_ingestible(2025) is True
    assert SC.is_product_servable(2025) is False
    import api.v2_service as svc

    assert 2025 not in tuple(svc.SERVED_SEASONS)


def test_new_module_keeps_firewalls():
    root = ROOT / "raceintel" / "spatial" / "geometry.py"
    text = root.read_text()
    for token in ("raceintel.features", "raceintel.labels",
                  "raceintel.model_lab", "raceintel.simulation",
                  "raceintel.strategy", "raceintel.explainability",
                  "raceintel.prediction", "api.", "fastapi", "fastf1"):
        assert f"import {token}" not in text
        assert f"from {token}" not in text
    # Tier-A table access is a local-file read, never a fastf1 import
    assert "import fastf1" not in text
