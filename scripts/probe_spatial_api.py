"""P12-5 real-corpus spatial API validation (measurement only, not CI).

Builds a real V2ReplayService from the local canonical corpus for a
small served set, then exercises V2SpatialService end to end:
geometry/frame validity, replay-clock agreement, universe agreement,
P12-4 render agreement, PARTIAL/unsupported/2025 behavior, payload
sizes, and cold/warm performance. Prints one JSON summary to stdout.
"""

import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.v2_replay_service import V2ReplayService
from api.v2_spatial_service import build_v2_spatial_service
from raceintel.race_state.race_state_reconstruction import (
    RaceNotFoundError,
    RaceStateReconstructor,
)
from raceintel.spatial.errors import SpatialArtifactUnavailableError
from raceintel.spatial.resolver import (
    SpatialStoreCache,
    resolve_frame,
    universe_from_race_state,
)

D9 = ("data/v2/processed/driver_lap_state_d9/season={season}/"
      "driver_lap_state_d9__d9-{season}.parquet")
RESULTS = ("data/v2/processed/results/season={season}/"
           "results__{race}.parquet")

GOLDEN = ["2023-r01-R", "2021-r05-R", "2024-r04-R", "2023-r03-R"]
PARTIAL_RACE = "2023-r15-R"
UNSUPPORTED_RACE = "2024-r09-R"
REJECTED_RACE = "2025-r01-R"

SYN_SCI = {
    "feature_set": "ALL_84",
    "feature_set_version": "v8",
    "serving_artifact_sha256": "probe",
    "model_specification_fingerprint": "probe",
    "phase2_content_hash": "probe",
    "probability_semantics": "INDEPENDENT_BINARY",
}


def load_replay(races):
    state_parts, result_parts = [], []
    for race in races:
        season = race[:4]
        df = pd.read_parquet(D9.format(season=season))
        state_parts.append(df[df["race_id"] == race].copy())
        result_parts.append(pd.read_parquet(
            RESULTS.format(season=season, race=race)))
    states = pd.concat(state_parts, ignore_index=True)
    results = pd.concat(result_parts, ignore_index=True)
    recon = RaceStateReconstructor(states, results)
    return V2ReplayService(states, recon, list(races),
                           checkpoints_dir="/tmp/probe-ckpt",
                           scientific_inputs=dict(SYN_SCI))


def main():
    out = {"golden": {}, "partial": {}, "unsupported": {},
           "rejected_2025": {}, "payload_bytes": {}, "perf": {}}
    replay = load_replay(GOLDEN + [PARTIAL_RACE, UNSUPPORTED_RACE])
    service = build_v2_spatial_service(replay, spatial_root=str(ROOT))

    for race in GOLDEN:
        timeline = replay.get_timeline(race)
        frame_index = timeline.frame_count // 2
        replay_result = replay.get_frame(race, frame_index)
        anchor_t = float(
            replay_result["frame"]["anchor_state_time_s"])
        universe = universe_from_race_state(replay_result["state"])
        geometry = service.get_geometry(race)
        payload = service.get_frame(race, frame_index)
        # Independent P12-4 reference through a fresh cache.
        fresh = SpatialStoreCache(max_races=4)
        store = fresh.get(str(ROOT), race)
        reference = resolve_frame(store, anchor_t, universe)
        ref = {s.driver_number: (s.render_x, s.render_y)
               for s in reference.drivers}
        worst = 0.0
        for entry in payload["drivers"]:
            if entry["availability"] == "UNAVAILABLE":
                assert entry["render_x"] is None
                continue
            assert entry["observation_time_s"] <= anchor_t
            got = (entry["render_x"], entry["render_y"])
            want = ref[entry["driver_number"]]
            worst = max(worst, abs(got[0] - want[0]),
                        abs(got[1] - want[1]))
        assert payload["query_time_s"] == anchor_t
        assert len(payload["drivers"]) == len(universe)
        assert payload["geometry_sha256"] == geometry["geometry_sha256"]
        json.dumps(payload, allow_nan=False)
        json.dumps(geometry, allow_nan=False)
        out["golden"][race] = {
            "frame_index": frame_index, "query_time_s": anchor_t,
            "drivers": len(payload["drivers"]),
            "fresh": payload["fresh_count"],
            "stale": payload["stale_count"],
            "unavailable": payload["unavailable_count"],
            "max_render_delta_vs_p12_4": worst,
            "main_points": geometry["main_track"]["n_points"],
            "pit_status": geometry["pit_status"],
        }

    timeline = replay.get_timeline(PARTIAL_RACE)
    frame_index = timeline.frame_count // 2
    payload = service.get_frame(PARTIAL_RACE, frame_index)
    assert payload["source_status"] == "PARTIAL"
    assert payload["unavailable_count"] >= 1
    out["partial"] = {
        "frame_index": frame_index,
        "query_time_s": payload["query_time_s"],
        "drivers": len(payload["drivers"]),
        "unavailable": payload["unavailable_count"],
        "source_status": payload["source_status"],
    }

    # 2024-r09-R: non-spatial replay works, spatial fails closed.
    replay_result = replay.get_frame(UNSUPPORTED_RACE, 0)
    assert float(
        replay_result["frame"]["anchor_state_time_s"]) >= 0.0
    try:
        service.get_frame(UNSUPPORTED_RACE, 0)
        out["unsupported"] = {"spatial": "UNEXPECTED_SUCCESS"}
    except SpatialArtifactUnavailableError:
        out["unsupported"] = {"replay": "ok", "spatial": "unavailable"}

    try:
        service.get_frame(REJECTED_RACE, 0)
        out["rejected_2025"] = {"spatial": "UNEXPECTED_SUCCESS"}
    except RaceNotFoundError:
        out["rejected_2025"] = {"spatial": "rejected_unknown_race"}

    race = GOLDEN[0]
    timeline = replay.get_timeline(race)
    frame_index = timeline.frame_count // 2
    geometry = service.get_geometry(race)
    frame = service.get_frame(race, frame_index)
    window = service.get_window(race, frame_index, 44, 5.0)
    out["payload_bytes"] = {
        "geometry": len(json.dumps(geometry).encode()),
        "frame": len(json.dumps(frame).encode()),
        "window_5s": len(json.dumps(window).encode()),
        "window_samples": window["sample_count"],
    }

    service.spatial_cache.invalidate()
    cold_start = time.perf_counter()
    service.get_frame(race, frame_index)
    cold_s = time.perf_counter() - cold_start
    warm_start = time.perf_counter()
    service.get_frame(race, frame_index)
    warm_s = time.perf_counter() - warm_start
    many_start = time.perf_counter()
    for _ in range(100):
        service.get_frame(race, frame_index)
    many_s = time.perf_counter() - many_start
    from fastapi.testclient import TestClient

    from api.main import app
    from api.v2_spatial_service import get_v2_spatial_service
    app.dependency_overrides[get_v2_spatial_service] = lambda: service
    try:
        client = TestClient(app, raise_server_exceptions=False)
        http_start = time.perf_counter()
        resp = client.get(f"/v2/races/{race}/spatial/frame/{frame_index}")
        http_s = time.perf_counter() - http_start
        assert resp.status_code == 200, resp.text[:300]
    finally:
        app.dependency_overrides.pop(get_v2_spatial_service, None)
    out["perf"] = {
        "frame_cold_s": cold_s,
        "frame_warm_s": warm_s,
        "hundred_warm_frames_s": many_s,
        "http_frame_warm_s": http_s,
    }
    print(json.dumps(out, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
