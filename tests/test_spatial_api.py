"""P12-5 spatial API tests (source-safe: synthetic only).

Stub replay service + tmp-dir spatial corpus exercise the HTTP
boundary: eligibility reuse, one-clock binding, universe binding,
DTO shape, error mapping, determinism, payload bounds, cache reuse,
and both firewalls. No observation corpus, no Tier-A tables, no
FastF1; real-corpus validation runs outside CI via measurement
scripts, and the governed CI pin covers this file's collection count.
"""

import json
import math
import sys
from contextlib import contextmanager
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.v2_replay_service import ReplayFrameNotFoundError
from api.v2_spatial_service import (
    MAX_HISTORY_S,
    build_v2_spatial_service,
    get_v2_spatial_service,
)
from raceintel.race_state.race_state_reconstruction import RaceNotFoundError
from raceintel.spatial import contracts as SC
from raceintel.spatial import geometry as G
from raceintel.spatial import manifest as SM
from raceintel.spatial import validation as V
from raceintel.spatial.errors import (
    SpatialArtifactUnavailableError,
    SpatialGeometryMismatchError,
)
from raceintel.spatial.io import (
    artifact_path,
    geometry_manifest_path,
    geometry_path,
    manifest_path,
    save_geometry_manifest,
    save_manifest,
    write_geometry_atomic,
    write_observations_atomic,
)

RACE_OK = "2023-r01-R"
RACE_PARTIAL = "2021-r12-R"
RACE_FAILED = "2024-r09-R"
RACE_NOGEOM = "2023-r02-R"
RACE_MISMATCH = "2023-r03-R"
RACE_2025 = "2025-r01-R"


# ---------------------------------------------------------------------------
# Synthetic spatial corpus
# ---------------------------------------------------------------------------

def _canonical_frame(race_id, rows):
    raw = [{
        "race_id": race_id, "driver_number": drv,
        "observation_time_s": float(t), "x": int(x), "y": int(y),
        "z": 5, "source": "pos", "status": "OnTrack",
        "source_observed_at": float(t),
    } for drv, t, x, y in rows]
    return V.canonicalize_observations(pd.DataFrame(raw))


def _geometry_record(race_id, source_hash):
    theta = np.linspace(0.0, 2 * math.pi, 64, endpoint=False)
    raw = np.stack([10000.0 + 5000.0 * np.cos(theta),
                    10000.0 + 5000.0 * np.sin(theta)], 1)
    transform = G.compute_transform(raw)
    rendered = G.apply_transform(raw, transform)
    record = {
        "schema_version": SC.SPATIAL_GEOMETRY_SCHEMA_VERSION,
        "race_id": race_id, "season": int(race_id[:4]),
        "layout_scope": "per-race",
        "algorithm_version": G.GEOMETRY_ALGORITHM_VERSION,
        "source": {"observation_content_sha256": source_hash},
        "main_track": {
            "points": [[float(v[0]), float(v[1])] for v in rendered],
            "raw_points": [[float(v[0]), float(v[1])] for v in raw],
            "n_points": 64, "closed_loop": True, "length_u": 31400.0,
        },
        "pit_lane": None, "pit_status": G.PIT_DEFERRED,
        "pit_defer_reason": "synthetic p12-5 fixture",
        "transform": transform, "quality": {}, "content_sha256": "",
    }
    record["content_sha256"] = G.geometry_content_hash(record)
    return record


def _build_corpus(root):
    # One manifest must cover all races: write rows incrementally.
    manifest = SM.new_manifest()
    geometry_manifest = G.new_geometry_manifest()

    def add(race_id, rows, status="COMPLETE", reason=None,
            with_geometry=True, geometry_source_hash=None):
        nonlocal manifest, geometry_manifest
        frame = _canonical_frame(race_id, rows)
        content = V.logical_content_hash(frame)
        numbers = sorted(int(v) for v in frame["driver_number"].unique())
        expected = (list(numbers) if status == "COMPLETE"
                    else numbers + [99])
        provenance = SM.build_provenance(
            season=int(race_id[:4]), race_id=race_id, session="R",
            source_input_ref="synthetic/p12-5", fastf1_version="3.7.0",
            raw_row_count=len(frame), kept_row_count=len(frame),
            excluded_zero_fix_rows=0, excluded_exact_duplicate_rows=0,
            driver_numbers=numbers, expected_driver_numbers=expected,
            time_min_s=float(frame["observation_time_s"].min()),
            time_max_s=float(frame["observation_time_s"].max()),
            observed_source_values=["pos"],
            observed_status_values=["OnTrack"],
            content_sha256=content)
        manifest = SM.set_race_row(manifest, race_id, status=status,
                                   provenance=provenance, reason=reason)
        write_observations_atomic(frame, artifact_path(root, race_id))
        if with_geometry:
            record = _geometry_record(race_id,
                                      geometry_source_hash or content)
            write_geometry_atomic(record, geometry_path(root, race_id))
            geometry_manifest = G.set_geometry_row(
                geometry_manifest, race_id,
                status=G.GEOMETRY_STATUS_COMPLETE,
                source_content_sha256=(geometry_source_hash or content),
                geometry_sha256=record["content_sha256"], n_points=64,
                pit_status=G.PIT_DEFERRED)
        return content

    add(RACE_OK, [
        (44, 10.0, 100, 50), (44, 11.0, 200, 60), (44, 12.0, 300, 70),
        (1, 10.5, 110, 51), (1, 11.5, 210, 61), (1, 12.01, 999, 999),
        (16, 0.0, 120, 52),
    ])
    add(RACE_PARTIAL, [(44, 10.0, 100, 50), (44, 11.0, 200, 60)],
        status="PARTIAL", reason="synthetic partial")
    manifest = SM.set_race_row(
        manifest, RACE_FAILED,
        status=getattr(SM, "STATUS_FAILED", "FAILED"),
        reason="synthetic failed ingestion")
    add(RACE_NOGEOM, [(44, 10.0, 100, 50)], with_geometry=False)
    add(RACE_MISMATCH, [(44, 10.0, 100, 50)],
        geometry_source_hash="0" * 64)
    save_manifest(manifest, manifest_path(root))
    save_geometry_manifest(geometry_manifest,
                           geometry_manifest_path(root))


# ---------------------------------------------------------------------------
# Stub replay service (canonical eligibility + clock, no corpus)
# ---------------------------------------------------------------------------

class _StubDriver:
    def __init__(self, driver_id, driver_number):
        self.driver_id = driver_id
        self.driver_number = driver_number


class _StubState:
    def __init__(self, drivers, state_time_s):
        self.drivers = tuple(drivers)
        self.state_time_s = state_time_s


def _ok_state(anchor_t):
    return _StubState([
        _StubDriver("hamilton", 44), _StubDriver("verstappen", 1),
        _StubDriver("leclerc", 16), _StubDriver("sainz", 55),
        _StubDriver("rookie", None),
    ], anchor_t)


class _StubReplayService:
    """Eligibility set + per-frame (T, state); 2025 never served."""

    def __init__(self):
        self.frames = {
            RACE_OK: {0: (12.0, _ok_state(12.0)),
                      1: (100.0, _ok_state(100.0))},
            RACE_PARTIAL: {0: (11.0, _StubState(
                [_StubDriver("hamilton", 44),
                 _StubDriver("norris", 4)], 11.0))},
            RACE_FAILED: {0: (11.0, _ok_state(11.0))},
            RACE_NOGEOM: {0: (11.0, _ok_state(11.0))},
            RACE_MISMATCH: {0: (11.0, _ok_state(11.0))},
        }

    def get_timeline(self, race_id):
        if race_id not in self.frames:
            raise RaceNotFoundError(race_id)
        return {"race_id": race_id}

    def get_frame(self, race_id, frame_index):
        if race_id not in self.frames:
            raise RaceNotFoundError(race_id)
        try:
            anchor_t, state = self.frames[race_id][frame_index]
        except KeyError:
            raise ReplayFrameNotFoundError(
                race_id, frame_index) from None
        return {
            "frame": {
                "race_id": race_id, "frame_index": frame_index,
                "anchor_driver_id": "hamilton",
                "anchor_lap_number": 5,
                "anchor_state_time_s": anchor_t,
                "replay_contract_version": "replay-v1",
            },
            "state": state,
        }


@pytest.fixture()
def service(tmp_path):
    _build_corpus(tmp_path)
    return build_v2_spatial_service(_StubReplayService(),
                                    spatial_root=str(tmp_path))


@contextmanager
def spatial_client(service):
    from fastapi.testclient import TestClient

    from api.main import app
    app.dependency_overrides[get_v2_spatial_service] = lambda: service
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_v2_spatial_service, None)


# ---------------------------------------------------------------------------
# Geometry endpoint
# ---------------------------------------------------------------------------

def test_geometry_response_shape(service):
    payload = service.get_geometry(RACE_OK)
    assert payload["race_id"] == RACE_OK
    assert payload["schema_version"] == SC.SPATIAL_GEOMETRY_SCHEMA_VERSION
    assert payload["algorithm_version"] == G.GEOMETRY_ALGORITHM_VERSION
    assert len(payload["geometry_sha256"]) == 64
    main = payload["main_track"]
    assert main["n_points"] == 64 and main["closed_loop"] is True
    assert len(main["points"]) == 64
    assert all(len(point) == 2 for point in main["points"])
    assert payload["pit_lane"] is None
    assert payload["pit_status"] == G.PIT_DEFERRED
    assert payload["render_bounds"] == {"u_min": 0.0, "v_min": 0.0,
                                        "u_max": 1.0, "v_max": 1.0}
    assert set(payload) == {"race_id", "schema_version",
                            "algorithm_version", "geometry_sha256",
                            "main_track", "pit_lane", "pit_status",
                            "render_bounds"}


def test_geometry_http_exact_serialization(service):
    with spatial_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_OK}/spatial/geometry").json()
    assert body["race_id"] == RACE_OK
    assert body["main_track"]["n_points"] == len(
        body["main_track"]["points"])
    for token in ("raw_points", "raw_bounds", "transform", "quality",
                  "source", ".parquet", ".json", "/tmp"):
        assert token not in json.dumps(body), f"leak: {token}"


def test_geometry_unknown_race_is_404(service):
    with spatial_client(service) as client:
        resp = client.get("/v2/races/1999-r99-R/spatial/geometry")
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_race"


def test_geometry_missing_geometry_is_unavailable(service):
    with pytest.raises(SpatialArtifactUnavailableError):
        service.get_geometry(RACE_NOGEOM)
    with spatial_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_NOGEOM}/spatial/geometry")
    assert resp.status_code == 404
    assert resp.json()["error"] == "spatial_unavailable"


def test_geometry_mismatch_fails_closed(service):
    with pytest.raises(SpatialGeometryMismatchError):
        service.get_geometry(RACE_MISMATCH)
    with spatial_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_MISMATCH}/spatial/geometry")
    assert resp.status_code == 500
    assert resp.json()["error"] == "spatial_integrity_error"


# ---------------------------------------------------------------------------
# Frame endpoint: one clock, one universe
# ---------------------------------------------------------------------------

def test_frame_binds_replay_clock_and_universe(service):
    payload = service.get_frame(RACE_OK, 0)
    assert payload["frame_index"] == 0
    assert payload["query_time_s"] == 12.0  # anchor_state_time_s
    assert payload["source_status"] == "COMPLETE"
    assert payload["resolver_contract_version"] == \
        "spatial-resolver-v1"
    by_number = {entry["driver_number"]: entry
                 for entry in payload["drivers"]}
    assert [entry["driver_id"] for entry in payload["drivers"]] == [
        "hamilton", "verstappen", "leclerc", "sainz", "rookie"]
    assert by_number[44]["availability"] == "FRESH"
    assert by_number[44]["observation_time_s"] == 12.0
    assert by_number[44]["age_s"] == pytest.approx(0.0)
    # Future-poison sample at 12.01 s is never selected.
    assert by_number[1]["observation_time_s"] == 11.5
    assert by_number[1]["availability"] == "FRESH"
    assert by_number[16]["availability"] == "STALE"
    assert by_number[55]["availability"] == "UNAVAILABLE"
    assert by_number[55]["observation_time_s"] is None
    assert by_number[55]["render_x"] is None
    assert by_number[55]["render_y"] is None
    rookie = [entry for entry in payload["drivers"]
              if entry["driver_id"] == "rookie"][0]
    assert rookie["driver_number"] is None
    assert rookie["availability"] == "UNAVAILABLE"
    assert (payload["fresh_count"], payload["stale_count"],
            payload["unavailable_count"]) == (2, 1, 2)


def test_frame_aged_out_keeps_provenance_without_coords(service):
    payload = service.get_frame(RACE_OK, 1)
    assert payload["query_time_s"] == 100.0
    by_number = {entry["driver_number"]: entry
                 for entry in payload["drivers"]}
    assert by_number[44]["availability"] == "UNAVAILABLE"
    assert by_number[44]["observation_time_s"] == 12.0
    assert by_number[44]["age_s"] == pytest.approx(88.0)
    assert by_number[44]["render_x"] is None
    assert all(entry["observation_time_s"] is None
               or entry["observation_time_s"] <= 100.0
               for entry in payload["drivers"])


def test_frame_no_future_observation_possible(service):
    payload = service.get_frame(RACE_OK, 0)
    for entry in payload["drivers"]:
        obs = entry["observation_time_s"]
        if obs is not None:
            assert obs <= payload["query_time_s"]
            assert entry["age_s"] == pytest.approx(
                payload["query_time_s"] - obs)


def test_frame_http_shape_and_no_raw_leak(service):
    with spatial_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_OK}/spatial/frame/0").json()
    assert body["race_id"] == RACE_OK
    assert body["query_time_s"] == 12.0
    assert len(body["drivers"]) == 5
    text = json.dumps(body)
    for token in ('"raw_x"', '"raw_y"', '"source":', '"status":',
                  ".parquet", "/tmp"):
        assert token not in text, f"leak: {token}"


def test_frame_unknown_frame_is_404(service):
    with spatial_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_OK}/spatial/frame/999")
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_frame"


def test_frame_negative_index_is_422(service):
    with spatial_client(service) as client:
        resp = client.get(f"/v2/races/{RACE_OK}/spatial/frame/-1")
    assert resp.status_code == 422


def test_geometry_frame_identity_consistent(service):
    geometry = service.get_geometry(RACE_OK)
    frame = service.get_frame(RACE_OK, 0)
    assert frame["geometry_sha256"] == geometry["geometry_sha256"]


# ---------------------------------------------------------------------------
# Partial / unsupported races
# ---------------------------------------------------------------------------

def test_partial_race_serves_valid_frame(service):
    payload = service.get_frame(RACE_PARTIAL, 0)
    assert payload["source_status"] == "PARTIAL"
    assert payload["query_time_s"] == 11.0
    by_id = {entry["driver_id"]: entry
             for entry in payload["drivers"]}
    assert by_id["hamilton"]["availability"] == "FRESH"
    assert by_id["norris"]["availability"] == "UNAVAILABLE"
    assert by_id["norris"]["render_x"] is None


def test_unsupported_spatial_race_is_unavailable_only(service):
    with pytest.raises(SpatialArtifactUnavailableError):
        service.get_frame(RACE_FAILED, 0)
    with spatial_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_FAILED}/spatial/frame/0")
        assert resp.status_code == 404
        assert resp.json()["error"] == "spatial_unavailable"
        geom = client.get(
            f"/v2/races/{RACE_FAILED}/spatial/geometry")
        assert geom.status_code == 404
        assert geom.json()["error"] == "spatial_unavailable"


# ---------------------------------------------------------------------------
# Product eligibility: 2025 rejected at HTTP, never duplicated
# ---------------------------------------------------------------------------

def test_2025_rejected_with_served_semantics(service):
    with pytest.raises(RaceNotFoundError):
        service.get_frame(RACE_2025, 0)
    with pytest.raises(RaceNotFoundError):
        service.get_geometry(RACE_2025)
    with spatial_client(service) as client:
        assert client.get(
            f"/v2/races/{RACE_2025}/spatial/frame/0").status_code == 404
        body = client.get(
            f"/v2/races/{RACE_2025}/spatial/geometry").json()
        assert body["error"] == "unknown_race"


def test_no_duplicated_season_policy():
    for name in ("v2_spatial_service.py", "v2_spatial_routes.py",
                 "v2_spatial_schemas.py"):
        text = (ROOT / "api" / name).read_text()
        for token in ("SERVED_SEASONS", "range(", "2025"):
            assert token not in text, f"policy duplicated in {name}"


def test_path_traversal_never_reaches_filesystem(service):
    with pytest.raises(RaceNotFoundError):
        service.get_frame("../../etc", 0)
    with pytest.raises(RaceNotFoundError):
        service.get_geometry("../observations/2023-r01-R")


# ---------------------------------------------------------------------------
# Window endpoint: causal, bounded
# ---------------------------------------------------------------------------

def test_window_returns_causal_samples_only(service):
    payload = service.get_window(RACE_OK, 0, 44, 5.0)
    assert payload["query_time_s"] == 12.0
    assert payload["history_s"] == 5.0
    times = [sample["observation_time_s"]
             for sample in payload["samples"]]
    assert times == [10.0, 11.0, 12.0]
    assert payload["sample_count"] == 3
    assert all(time <= 12.0 for time in times)


def test_window_zero_history_only_exact_hits(service):
    payload = service.get_window(RACE_OK, 0, 44, 0.0)
    assert [sample["observation_time_s"]
            for sample in payload["samples"]] == [12.0]


def test_window_unknown_driver_is_empty(service):
    payload = service.get_window(RACE_OK, 0, 99, 5.0)
    assert payload["samples"] == [] and payload["sample_count"] == 0


def test_window_bounds_rejected_at_http(service):
    with spatial_client(service) as client:
        too_long = client.get(
            f"/v2/races/{RACE_OK}/spatial/window/0",
            params={"driver_number": 44,
                    "history_s": MAX_HISTORY_S + 1.0})
        assert too_long.status_code == 422
        bad_driver = client.get(
            f"/v2/races/{RACE_OK}/spatial/window/0",
            params={"driver_number": 0, "history_s": 5.0})
        assert bad_driver.status_code == 422
        missing = client.get(
            f"/v2/races/{RACE_OK}/spatial/window/0")
        assert missing.status_code == 422


def test_window_http_shape(service):
    with spatial_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_OK}/spatial/window/0",
            params={"driver_number": 1,
                    "history_s": 5.0}).json()
    assert body["driver_number"] == 1
    assert [sample["observation_time_s"]
            for sample in body["samples"]] == [10.5, 11.5]


# ---------------------------------------------------------------------------
# Determinism, bounds, cache
# ---------------------------------------------------------------------------

def test_responses_are_deterministic(service):
    first = json.dumps(service.get_frame(RACE_OK, 0), sort_keys=True)
    second = json.dumps(service.get_frame(RACE_OK, 0), sort_keys=True)
    assert first == second
    assert json.dumps(service.get_geometry(RACE_OK),
                      sort_keys=True) == json.dumps(
        service.get_geometry(RACE_OK), sort_keys=True)
    with spatial_client(service) as client:
        path = f"/v2/races/{RACE_OK}/spatial/frame/0"
        assert client.get(path).content == client.get(path).content


def test_payload_bounds(service):
    geometry = service.get_geometry(RACE_OK)
    assert len(geometry["main_track"]["points"]) <= 1024
    frame = service.get_frame(RACE_OK, 0)
    assert len(frame["drivers"]) == 5  # replay universe, not the corpus
    window = service.get_window(RACE_OK, 0, 44, MAX_HISTORY_S)
    assert window["sample_count"] <= 10000
    raw_geom = json.dumps(geometry).encode()
    raw_frame = json.dumps(frame).encode()
    assert len(raw_geom) < 200_000
    assert len(raw_frame) < 100_000


def test_race_level_cache_survives_across_requests(service):
    service.get_frame(RACE_OK, 0)
    service.get_frame(RACE_OK, 1)
    service.get_geometry(RACE_OK)
    assert len(service.spatial_cache) == 1
    first = service.spatial_cache.get(service.spatial_root, RACE_OK)
    service.get_window(RACE_OK, 0, 44, 1.0)
    assert service.spatial_cache.get(
        service.spatial_root, RACE_OK) is first


def test_no_science_duplication_in_adapter():
    for name in ("v2_spatial_service.py", "v2_spatial_routes.py"):
        text = (ROOT / "api" / name).read_text()
        for token in ("searchsorted", "classify_availability",
                      "apply_transform", "compute_transform",
                      "logical_content_hash", "canonicalize"):
            assert token not in text, f"science duplicated: {token}"


def test_spatial_never_imports_api():
    for path in (ROOT / "raceintel" / "spatial").glob("*.py"):
        text = path.read_text()
        assert "from api" not in text and "import api" not in text, \
            f"direction breach: {path.name}"


def test_api_adapter_has_no_predictive_imports():
    for name in ("v2_spatial_service.py", "v2_spatial_routes.py",
                 "v2_spatial_schemas.py"):
        text = (ROOT / "api" / name).read_text()
        for token in ("raceintel.features", "raceintel.labels",
                      "raceintel.model_lab", "raceintel.simulation",
                      "raceintel.strategy", "raceintel.explainability",
                      "raceintel.prediction"):
            assert token not in text, f"predictive breach: {token}"


def test_openapi_lists_spatial_contracts():
    from api.main import app

    spec = app.openapi()
    for path in ("/v2/races/{race_id}/spatial/geometry",
                 "/v2/races/{race_id}/spatial/frame/{frame_index}",
                 "/v2/races/{race_id}/spatial/window/{frame_index}"):
        assert path in spec["paths"], f"missing OpenAPI path: {path}"
    schemas = spec["components"]["schemas"]
    for name in ("V2SpatialGeometryResponse", "V2SpatialFrameResponse",
                 "V2SpatialWindowResponse"):
        assert name in schemas, f"missing OpenAPI schema: {name}"
