"""Phase-5 R4: historical replay HTTP API tests.

Covers the additive ``/v2/races/{race_id}/replay/*`` family over a real
multi-race canonical slice (no model load except ONE live-engine parity
test): service init/laziness, timeline schema/pagination/determinism,
factual frame parity (ordinary/early/partial/red/stale/shared-T/SC/VSC),
checkpoint + cache-hit/miss/stale/corrupt semantics, the structural
no-generation guarantee, INDEPENDENT_BINARY preservation, the 2025
firewall, error bodies, route inventory, and performance smoke.

Real backfill cache is NEVER required: prediction artifacts are built in
tmpdir via the frozen R3 writers (synthetic snapshots, plus one frozen
engine snapshot for parity).
"""

from __future__ import annotations

import json
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pandas as pd
import pytest

from api.v2_replay_service import (
    NotPredictionCheckpointError,
    PredictionUnavailableError,
    ReplayFrameNotFoundError,
    V2ReplayService,
)
from raceintel.replay import replay as RP
from raceintel.race_state.race_state_reconstruction import RaceNotFoundError
from raceintel.replay.replay_predictions import (
    REPLAY_PREDICTION_CONTRACT_VERSION,
    cache_identity_inputs,
    canonical_data_identity,
    build_artifact,
    select_checkpoints,
    write_artifact,
)

ROOT = Path(__file__).resolve().parents[1]

D9 = ("data/v2/processed/driver_lap_state_d9/season={season}/"
      "driver_lap_state_d9__d9-{season}.parquet")
RESULTS = ("data/v2/processed/results/season={season}/"
           "results__{race}.parquet")

RACE_ORDINARY = "2023-r01-R"
RACE_PARTIAL = "2021-r12-R"
RACE_RED = "2022-r18-R"
RACE_STALE = "2022-r07-R"
RACE_SHARED_T = "2020-r09-R"
RACE_VSC = "2018-r01-R"
FIXTURES = [(2023, RACE_ORDINARY), (2021, RACE_PARTIAL),
            (2022, RACE_RED), (2022, RACE_STALE),
            (2020, RACE_SHARED_T), (2018, RACE_VSC)]

SYN_SCI = {
    "feature_set": "ALL_84",
    "feature_set_version": "v8",
    "serving_artifact_sha256": "test-sha",
    "model_specification_fingerprint": "test-fp",
    "phase2_content_hash": "test-phase2",
    "probability_semantics": "INDEPENDENT_BINARY",
}

MODEL_DICT = {
    "task": "winner", "target": "is_winner",
    "eligibility_mask": "eligible_is_winner", "feature_set": "ALL_84",
    "feature_set_version": "v8", "estimator": "LogisticRegression",
    "estimator_params": [["C", 0.01]], "calibration_method": "RAW",
    "probability_semantics": "INDEPENDENT_BINARY",
    "training_seasons": [2018, 2019, 2020, 2021, 2022, 2023, 2024],
    "transformed_dim": 106, "feature_count": 84,
    "artifact_sha256": "test-sha", "specification_fingerprint": "test-fp",
    "sklearn_version": "1.8.0",
}

_states = None
_results = None
_recon = None


def get_corpus():
    global _states, _results, _recon
    if _states is None:
        from raceintel.race_state.race_state_reconstruction import RaceStateReconstructor
        state_parts, result_parts = [], []
        for season, race in FIXTURES:
            df = pd.read_parquet(D9.format(season=season))
            state_parts.append(df[df["race_id"] == race].copy())
            result_parts.append(pd.read_parquet(
                RESULTS.format(season=season, race=race)))
        _states = pd.concat(state_parts, ignore_index=True)
        _results = pd.concat(result_parts, ignore_index=True)
        _recon = RaceStateReconstructor(_states, _results)
    return _states, _recon


def make_service(tmp_path, scientific=None):
    states, recon = get_corpus()
    return V2ReplayService(
        states, recon, [race for _, race in FIXTURES],
        checkpoints_dir=str(tmp_path),
        scientific_inputs=dict(scientific or SYN_SCI))


def race_states(race_id):
    states, _ = get_corpus()
    return states[states["race_id"] == race_id].copy()


@contextmanager
def replay_client(service):
    from fastapi.testclient import TestClient

    from api.main import app
    from api.v2_replay_service import get_v2_replay_service
    app.dependency_overrides[get_v2_replay_service] = lambda: service
    try:
        yield TestClient(app, raise_server_exceptions=False)
    finally:
        app.dependency_overrides.pop(get_v2_replay_service, None)


def synth_snapshot(checkpoint, roster, probs, null_drivers=()):
    entries, observable = [], 0
    for position, driver in enumerate(roster):
        if driver in null_drivers:
            entries.append({
                "driver_id": driver, "observable": False,
                "observed_lap_number": None, "observed_time_s": None,
                "observation_age_s": None, "observed_position": None,
                "winner_probability": None,
                "unavailable_reason": "NO_OBSERVATION_AT_SNAPSHOT"})
        else:
            observable += 1
            entries.append({
                "driver_id": driver, "observable": True,
                "observed_lap_number": checkpoint.anchor_lap_number,
                "observed_time_s": checkpoint.anchor_state_time_s,
                "observation_age_s": 0.0, "observed_position": position + 1,
                "winner_probability": probs[driver],
                "unavailable_reason": None})
    return {
        "race_id": checkpoint.race_id,
        "anchor_driver_id": checkpoint.anchor_driver_id,
        "anchor_lap_number": checkpoint.anchor_lap_number,
        "state_time_s": checkpoint.anchor_state_time_s,
        "roster_size": len(roster), "observable_count": observable,
        "unavailable_count": len(roster) - observable,
        "probability_semantics": "INDEPENDENT_BINARY",
        "probability_semantics_note": "synthetic independent-binary note",
        "feature_set": "ALL_84", "model": dict(MODEL_DICT),
        "predictions": entries}


def synth_inputs(service, series, race_id):
    return cache_identity_inputs(
        series=series,
        data_identity=canonical_data_identity(
            race_states(race_id), race_id),
        feature_set=SYN_SCI["feature_set"],
        feature_set_version=SYN_SCI["feature_set_version"],
        artifact_sha256=SYN_SCI["serving_artifact_sha256"],
        specification_fingerprint=SYN_SCI[
            "model_specification_fingerprint"],
        phase2_content_hash=SYN_SCI["phase2_content_hash"],
        probability_semantics=SYN_SCI["probability_semantics"])


def write_hit_artifact(service, tmp_path, race_id=RACE_PARTIAL,
                       null_drivers=(), scale=1.0):
    """Complete synthetic artifact; probs sum > 1 (no-normalization probe)."""
    states, _ = get_corpus()
    timeline = service.get_timeline(race_id)
    series = service.get_series(race_id)
    roster = sorted(set(
        states[states["race_id"] == race_id]["driver_id"]))
    snapshots = {}
    for order, checkpoint in enumerate(series.checkpoints):
        probs = {d: (0.09 + 0.001 * ((order + i) % 7)) * scale
                 for i, d in enumerate(roster)}
        snapshots[checkpoint.frame_index] = synth_snapshot(
            checkpoint, roster, probs, null_drivers=null_drivers)
    artifact = build_artifact(series, snapshots, dict(MODEL_DICT),
                              synth_inputs(service, series, race_id))
    assert artifact["complete"] is True
    path = str(tmp_path / f"{race_id}.json")
    write_artifact(path, artifact)
    return artifact, series


def frame_at_regime(service, race_id, tokens):
    """First frame whose representative row carries a track_state token."""
    states = race_states(race_id)
    reps = {}
    for row in states.itertuples(index=False):
        key = float(row.state_time_s)
        candidate = (int(row.lap_number), str(row.driver_id),
                     None if pd.isna(row.track_state)
                     else str(row.track_state))
        if key not in reps or candidate[:2] < reps[key][:2]:
            reps[key] = candidate
    timeline = service.get_timeline(race_id)
    for frame in timeline.frames:
        token = reps[frame.anchor_state_time_s][2]
        if token in tokens:
            return frame
    raise AssertionError(f"no {tokens} frame in {race_id}")


# ---------------------------------------------------------------------------
# Service init / laziness / lookup.
# ---------------------------------------------------------------------------

def test_contract_versions(tmp_path):
    service = make_service(tmp_path)
    timeline = service.get_timeline(RACE_ORDINARY)
    assert timeline.replay_contract_version == "v1"
    assert RP.REPLAY_CONTRACT_VERSION == "v1"
    assert REPLAY_PREDICTION_CONTRACT_VERSION == "v1"
    assert service.get_series(RACE_ORDINARY).prediction_contract_version == "v1"


def test_service_builds_nothing_eagerly(tmp_path):
    service = make_service(tmp_path)
    assert service._timelines == {}
    assert service._series == {}
    assert service._resolvers == {}
    assert service.race_ids == tuple(race for _, race in FIXTURES)


def test_timeline_lazy_and_cached(tmp_path):
    service = make_service(tmp_path)
    first = service.get_timeline(RACE_ORDINARY)
    assert set(service._timelines) == {RACE_ORDINARY}
    assert service.get_timeline(RACE_ORDINARY) is first


def test_series_lazy_and_cached(tmp_path):
    service = make_service(tmp_path)
    first = service.get_series(RACE_ORDINARY)
    assert set(service._series) == {RACE_ORDINARY}
    assert first.checkpoint_count == 61  # R3-measured Bahrain count
    assert service.get_series(RACE_ORDINARY) is first


def test_service_holds_no_model_stack(tmp_path):
    service = make_service(tmp_path)
    for attr in ("_engine", "engine", "_bridge", "_predictor", "_model"):
        assert not hasattr(service, attr), attr
    assert "raceintel.prediction" not in str(type(service._reconstructor))


@pytest.mark.parametrize("method", ["list_frames", "get_frame",
                                    "get_prediction"])
def test_unknown_race_service(tmp_path, method):
    service = make_service(tmp_path)
    with pytest.raises(RaceNotFoundError):
        if method == "list_frames":
            service.list_frames("nope-not-a-race")
        elif method == "get_frame":
            service.get_frame("nope-not-a-race", 0)
        else:
            service.get_prediction("nope-not-a-race", 0)


# ---------------------------------------------------------------------------
# Timeline endpoint: schema + pagination + determinism.
# ---------------------------------------------------------------------------

def test_timeline_first_page_shape(tmp_path):
    service = make_service(tmp_path)
    with replay_client(service) as client:
        resp = client.get(f"/v2/races/{RACE_ORDINARY}/replay/timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert body["race_id"] == RACE_ORDINARY
    assert body["replay_contract_version"] == "v1"
    assert body["offset"] == 0 and body["limit"] == 100
    assert body["returned_count"] == 100
    assert body["total_frames"] == service.get_timeline(
        RACE_ORDINARY).frame_count > 500
    assert set(body["frames"][0]) == {
        "race_id", "frame_index", "anchor_driver_id", "anchor_lap_number",
        "anchor_state_time_s", "replay_contract_version"}
    assert [f["frame_index"] for f in body["frames"]] == list(range(100))


def test_timeline_pagination_middle_last_empty(tmp_path):
    service = make_service(tmp_path)
    total = service.get_timeline(RACE_ORDINARY).frame_count
    with replay_client(service) as client:
        mid = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/timeline",
            params={"offset": 250, "limit": 50}).json()
        assert [f["frame_index"] for f in mid["frames"]] == list(
            range(250, 300))
        last = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/timeline",
            params={"offset": total - 7, "limit": 100}).json()
        assert [f["frame_index"] for f in last["frames"]] == list(
            range(total - 7, total))
        assert last["returned_count"] == 7
        at_end = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/timeline",
            params={"offset": total}).json()
        assert at_end["returned_count"] == 0 and at_end["frames"] == []
        past_end = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/timeline",
            params={"offset": total + 40, "limit": 10}).json()
        assert past_end["returned_count"] == 0 and past_end["frames"] == []
        one = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/timeline",
            params={"limit": 1}).json()
        assert one["returned_count"] == 1
        capped = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/timeline",
            params={"limit": 500}).json()
        assert capped["returned_count"] == 500


@pytest.mark.parametrize("params", [{"limit": 0}, {"limit": 501},
                                    {"offset": -1}])
def test_timeline_bad_pagination_422(tmp_path, params):
    service = make_service(tmp_path)
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/timeline", params=params)
    assert resp.status_code == 422


def test_timeline_concatenated_pages_match_domain(tmp_path):
    service = make_service(tmp_path)
    domain = [f.to_dict()
              for f in service.get_timeline(RACE_ORDINARY).frames]
    seen = []
    with replay_client(service) as client:
        offset, step = 0, 137
        while True:
            page = client.get(
                f"/v2/races/{RACE_ORDINARY}/replay/timeline",
                params={"offset": offset, "limit": step}).json()
            seen.extend(page["frames"])
            if len(page["frames"]) < step:
                break
            offset += step
    assert seen == domain


def test_timeline_listing_never_reconstructs(tmp_path):
    service = make_service(tmp_path)
    with replay_client(service) as client:
        client.get(f"/v2/races/{RACE_ORDINARY}/replay/timeline",
                   params={"limit": 500})
    assert service._resolvers == {}


def test_timeline_unknown_race_404(tmp_path):
    service = make_service(tmp_path)
    with replay_client(service) as client:
        resp = client.get("/v2/races/nope-not-a-race/replay/timeline")
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_race"


# ---------------------------------------------------------------------------
# Frame endpoint: shape, navigation, parity.
# ---------------------------------------------------------------------------

def test_frame_zero_shape_and_nav(tmp_path):
    service = make_service(tmp_path)
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/frames/0")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "frame", "state", "has_previous", "has_next",
        "previous_frame_index", "next_frame_index", "leader_lap",
        "is_prediction_checkpoint", "checkpoint_reasons",
        "prediction_cache_available",
        "previous_prediction_checkpoint_frame",
        "next_prediction_checkpoint_frame"}
    assert body["frame"]["frame_index"] == 0
    assert body["has_previous"] is False and body["has_next"] is True
    assert body["previous_frame_index"] is None
    assert body["next_frame_index"] == 1
    assert body["leader_lap"] == 1
    assert body["state"]["race_id"] == RACE_ORDINARY
    assert body["state"]["anchor_driver_id"] == body["frame"][
        "anchor_driver_id"]
    assert body["state"]["state_time_s"] == body["frame"][
        "anchor_state_time_s"]
    assert body["is_prediction_checkpoint"] is True
    assert body["checkpoint_reasons"] == ["LEADER_LAP"]
    assert body["prediction_cache_available"] is False  # empty tmpdir


def test_frame_last_nav_and_checkpoint_pointers(tmp_path):
    service = make_service(tmp_path)
    total = service.get_timeline(RACE_ORDINARY).frame_count
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/frames/{total - 1}").json()
    assert body["has_previous"] is True and body["has_next"] is False
    assert body["previous_frame_index"] == total - 2
    assert body["next_frame_index"] is None
    assert body["leader_lap"] == 57  # Bahrain full distance


def test_frame_non_checkpoint_pointers_no_cache(tmp_path):
    service = make_service(tmp_path)
    series = service.get_series(RACE_ORDINARY)
    hits = {c.frame_index for c in series.checkpoints}
    plain = next(i for i in range(1, 400) if i not in hits)
    ordered = sorted(hits)
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/frames/{plain}").json()
    assert body["is_prediction_checkpoint"] is False
    assert body["checkpoint_reasons"] == []
    assert body["prediction_cache_available"] is False
    assert body["previous_prediction_checkpoint_frame"] == max(
        v for v in ordered if v < plain)
    assert body["next_prediction_checkpoint_frame"] == min(
        v for v in ordered if v > plain)


def _http_state_equals_direct(service, race_id, frame_index):
    from api.v2_schemas import V2RaceStateResponse
    from raceintel.replay.replay_reconstruction import ReplayReconstructor
    states, recon = get_corpus()
    direct = ReplayReconstructor(
        service.get_timeline(race_id), recon).state_at(frame_index)
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{race_id}/replay/frames/{frame_index}").json()
    # The frozen Phase-4 response schema projects to_dict(); parity means
    # the API projection is identical to the direct projection.
    assert body["state"] == json.loads(json.dumps(
        V2RaceStateResponse(**direct.to_dict()).model_dump()))


def test_frame_parity_ordinary_mid(tmp_path):
    service = make_service(tmp_path)
    total = service.get_timeline(RACE_ORDINARY).frame_count
    _http_state_equals_direct(service, RACE_ORDINARY, total // 2)


def test_frame_parity_early_prefirst(tmp_path):
    service = make_service(tmp_path)
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/frames/0").json()
    nulls = [d for d in body["state"]["drivers"] if not d["observable"]]
    assert nulls, "frame 0 must carry pre-first-observation null members"
    assert all(d["position"] is None for d in nulls)
    _http_state_equals_direct(service, RACE_ORDINARY, 0)


def test_frame_parity_partial(tmp_path):
    service = make_service(tmp_path)
    total = service.get_timeline(RACE_PARTIAL).frame_count
    assert total == 60  # thin Spa 2021 history, R1-pinned shape
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/frames/{total - 1}").json()
    assert body["has_next"] is False
    assert body["leader_lap"] == 3
    _http_state_equals_direct(service, RACE_PARTIAL, total - 1)


def test_frame_parity_red(tmp_path):
    service = make_service(tmp_path)
    frame = frame_at_regime(service, RACE_RED, {"red_flag"})
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_RED}/replay/frames/"
            f"{frame.frame_index}").json()
    assert body["state"]["race_control"]["flag_red"] is True
    assert body["state"]["race_control"]["track_state"] == "red_flag"
    _http_state_equals_direct(service, RACE_RED, frame.frame_index)


def test_frame_parity_stale(tmp_path):
    service = make_service(tmp_path)
    states = race_states(RACE_STALE)
    target = states[(states["driver_id"] == "norris") &
                    (states["lap_number"] == 30)].iloc[0]
    timeline = service.get_timeline(RACE_STALE)
    frame = next(f for f in timeline.frames
                 if f.anchor_state_time_s == float(target["state_time_s"]))
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_STALE}/replay/frames/"
            f"{frame.frame_index}").json()
    aged = [d for d in body["state"]["drivers"]
            if d["observable"] and (d["observation_age_s"] or 0) > 0]
    assert aged, "stale race must expose members with positive age"
    _http_state_equals_direct(service, RACE_STALE, frame.frame_index)


def test_frame_parity_shared_t_divergence(tmp_path):
    service = make_service(tmp_path)
    timeline = service.get_timeline(RACE_SHARED_T)
    frame = next(f for f in timeline.frames
                 if abs(f.anchor_state_time_s - 2974.257) < 1e-9)
    # Canonical R1/R2 anchor: giovinazzi / lap 6 (never latifi SC row).
    assert frame.anchor_driver_id == "giovinazzi"
    assert frame.anchor_lap_number == 6
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_SHARED_T}/replay/frames/"
            f"{frame.frame_index}").json()
    assert body["state"]["race_control"]["track_state"] == "yellow"
    _http_state_equals_direct(service, RACE_SHARED_T, frame.frame_index)


def test_frame_parity_safety_car(tmp_path):
    service = make_service(tmp_path)
    frame = frame_at_regime(service, RACE_SHARED_T, {"safety_car"})
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_SHARED_T}/replay/frames/"
            f"{frame.frame_index}").json()
    assert body["state"]["race_control"]["flag_safety_car"] is True
    _http_state_equals_direct(service, RACE_SHARED_T, frame.frame_index)


def test_frame_parity_vsc(tmp_path):
    service = make_service(tmp_path)
    frame = frame_at_regime(service, RACE_VSC, {"vsc", "vsc_ending"})
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_VSC}/replay/frames/"
            f"{frame.frame_index}").json()
    assert body["state"]["race_control"]["flag_vsc"] is True
    _http_state_equals_direct(service, RACE_VSC, frame.frame_index)


def test_frame_unknown_and_malformed(tmp_path):
    service = make_service(tmp_path)
    total = service.get_timeline(RACE_ORDINARY).frame_count
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/frames/{total}")
        assert resp.status_code == 404
        assert resp.json()["error"] == "unknown_frame"
        assert client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/frames/{total + 500}"
        ).status_code == 404
        assert client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/frames/-1"
        ).status_code == 422
        assert client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/frames/notanint"
        ).status_code == 422
        assert client.get(
            "/v2/races/nope-not-a-race/replay/frames/0").json()[
                "error"] == "unknown_race"


def test_frame_repeated_requests_deterministic(tmp_path):
    service = make_service(tmp_path)
    with replay_client(service) as client:
        first = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/frames/5").json()
        second = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/frames/5").json()
    assert first == second


def test_frame_unknown_race_service_error(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(ReplayFrameNotFoundError):
        service.get_frame(RACE_ORDINARY, 10 ** 9)


# ---------------------------------------------------------------------------
# Prediction endpoint: hit / miss / stale / corrupt / not-checkpoint.
# ---------------------------------------------------------------------------

def test_prediction_not_checkpoint_404_with_pointers(tmp_path):
    service = make_service(tmp_path)
    series = service.get_series(RACE_ORDINARY)
    hits = {c.frame_index for c in series.checkpoints}
    plain = next(i for i in range(1, 400) if i not in hits)
    with pytest.raises(NotPredictionCheckpointError) as exc:
        service.get_prediction(RACE_ORDINARY, plain)
    assert exc.value.previous_frame is not None
    assert exc.value.next_frame is not None
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/predictions/{plain}")
    assert resp.status_code == 404
    body = resp.json()
    assert body["error"] == "not_prediction_checkpoint"
    assert body["previous_prediction_checkpoint_frame"] == \
        exc.value.previous_frame
    assert body["next_prediction_checkpoint_frame"] == exc.value.next_frame


def test_prediction_cache_miss_503_no_generation(tmp_path):
    service = make_service(tmp_path)
    checkpoint = service.get_series(RACE_PARTIAL).checkpoints[0]
    started = time.perf_counter()
    with pytest.raises(PredictionUnavailableError) as exc:
        service.get_prediction(RACE_PARTIAL, checkpoint.frame_index)
    elapsed = time.perf_counter() - started
    assert exc.value.reason == "cache_missing"
    assert elapsed < 2.0  # immediate: no 12 s model run possible
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/predictions/"
            f"{checkpoint.frame_index}")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "prediction_unavailable"
    assert body["reason"] == "cache_missing"


def test_prediction_stale_cache_503(tmp_path):
    service = make_service(tmp_path)
    artifact, series = write_hit_artifact(service, tmp_path)
    path = str(tmp_path / f"{RACE_PARTIAL}.json")
    with open(path) as handle:
        payload = json.load(handle)
    payload["cache_identity"]["feature_set"] = "MUTATED_SET"
    with open(path, "w") as handle:
        json.dump(payload, handle)
    checkpoint = series.checkpoints[0]
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/predictions/"
            f"{checkpoint.frame_index}")
    assert resp.status_code == 503
    assert resp.json()["reason"] == "cache_stale"


def test_prediction_corrupt_cache_503(tmp_path):
    service = make_service(tmp_path)
    with open(tmp_path / f"{RACE_PARTIAL}.json", "w") as handle:
        handle.write("{not valid json!!!")
    checkpoint = service.get_series(RACE_PARTIAL).checkpoints[0]
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/predictions/"
            f"{checkpoint.frame_index}")
    assert resp.status_code == 503
    assert resp.json()["reason"] == "cache_corrupt"


def test_prediction_incomplete_cache_503(tmp_path):
    service = make_service(tmp_path)
    series = service.get_series(RACE_PARTIAL)
    assert series.checkpoint_count > 1
    states = race_states(RACE_PARTIAL)
    roster = sorted(set(states["driver_id"]))
    first = series.checkpoints[0]
    probs = {d: 0.05 for d in roster}
    snapshots = {first.frame_index: synth_snapshot(first, roster, probs)}
    artifact = build_artifact(series, snapshots, dict(MODEL_DICT),
                              synth_inputs(service, series, RACE_PARTIAL))
    assert artifact["complete"] is False
    write_artifact(str(tmp_path / f"{RACE_PARTIAL}.json"), artifact)
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/predictions/"
            f"{first.frame_index}")
    assert resp.status_code == 503
    assert resp.json()["reason"] == "cache_incomplete"


def test_prediction_cache_hit_exact_values(tmp_path):
    service = make_service(tmp_path)
    artifact, series = write_hit_artifact(
        service, tmp_path, null_drivers=("mazepin",), scale=1.7)
    checkpoint = series.checkpoints[2]
    stored = next(e["prediction"] for e in artifact["checkpoints"]
                  if e["checkpoint"]["frame_index"] == checkpoint.frame_index)
    assert sum(p["winner_probability"] for p in stored["predictions"]
               if p["winner_probability"] is not None) > 1.0
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/predictions/"
            f"{checkpoint.frame_index}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["cache_status"] == "HIT"
    assert body["frame"]["frame_index"] == checkpoint.frame_index
    assert body["checkpoint"]["reasons"] == list(checkpoint.reasons)
    assert body["checkpoint"]["leader_lap"] == checkpoint.leader_lap
    assert body["checkpoint"]["prediction_contract_version"] == "v1"
    assert body["prediction"] == json.loads(json.dumps(stored))
    assert [p["driver_id"] for p in body["prediction"]["predictions"]] == [
        p["driver_id"] for p in stored["predictions"]]
    assert body["prediction"]["probability_semantics"] == \
        "INDEPENDENT_BINARY"
    assert "probability_share" not in json.dumps(body)
    nulls = [p for p in body["prediction"]["predictions"]
             if p["winner_probability"] is None]
    assert {p["driver_id"] for p in nulls} == {"mazepin"}
    assert all(p["unavailable_reason"] == "NO_OBSERVATION_AT_SNAPSHOT"
               for p in nulls)
    assert body["prediction"]["model"] == MODEL_DICT


def test_prediction_hit_marks_frame_available(tmp_path):
    service = make_service(tmp_path)
    _, series = write_hit_artifact(service, tmp_path)
    checkpoint = series.checkpoints[0]
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/frames/"
            f"{checkpoint.frame_index}").json()
    assert body["is_prediction_checkpoint"] is True
    assert body["prediction_cache_available"] is True


def test_prediction_unknown_frame_404(tmp_path):
    service = make_service(tmp_path)
    total = service.get_timeline(RACE_PARTIAL).frame_count
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/predictions/{total}")
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_frame"


_live = {}


def get_live_engine_stack():
    if "engine" not in _live:
        from raceintel.config import V2Paths
        from raceintel.features.build_matrix import load_history
        from raceintel.model_lab import serving as SERVING
        from raceintel.prediction import RacePredictionEngine
        from raceintel.race_state.race_state_features import RaceStateFeatureBridge
        from raceintel.race_state.race_state_reconstruction import RaceStateReconstructor
        from raceintel.replay.replay_reconstruction import ReplayReconstructor
        states = race_states(RACE_ORDINARY)
        results = pd.read_parquet(RESULTS.format(season=2023,
                                                 race=RACE_ORDINARY))
        predictor = SERVING.load_frozen_winner_model()
        history = load_history(V2Paths.resolve())
        engine = RacePredictionEngine(
            RaceStateFeatureBridge(states, history), predictor)
        timeline = RP.build_replay_timeline(states)
        _live.update(engine=engine, states=states,
                     timeline=timeline,
                     replay=ReplayReconstructor(
                         timeline, RaceStateReconstructor(states, results)))
    return _live


def test_prediction_live_snapshot_parity(tmp_path):
    from api.v2_replay_service import live_scientific_inputs
    from raceintel.replay.replay_predictions import generate_checkpoint, read_cached_prediction
    stack = get_live_engine_stack()
    engine = stack["engine"]
    series = select_checkpoints(stack["timeline"], stack["states"])
    checkpoint = series.checkpoints[0]  # early frame: sub-second generation
    snapshot = generate_checkpoint(engine, stack["replay"], checkpoint)
    assert snapshot["probability_semantics"] == "INDEPENDENT_BINARY"
    scientific = live_scientific_inputs(engine)
    service = make_service(tmp_path, scientific=scientific)
    assert service.get_series(RACE_ORDINARY).to_dict() == series.to_dict()
    inputs = cache_identity_inputs(
        series=series,
        data_identity=canonical_data_identity(
            stack["states"], RACE_ORDINARY),
        feature_set=scientific["feature_set"],
        feature_set_version=scientific["feature_set_version"],
        artifact_sha256=scientific["serving_artifact_sha256"],
        specification_fingerprint=scientific[
            "model_specification_fingerprint"],
        phase2_content_hash=scientific["phase2_content_hash"],
        probability_semantics=scientific["probability_semantics"])
    artifact = build_artifact(series, {checkpoint.frame_index: snapshot},
                              engine.model_identity.to_dict(), inputs)
    assert artifact["complete"] is False  # single-checkpoint prefix probe
    # R3 storage preserves the live snapshot bit-for-bit (sums included).
    assert read_cached_prediction(
        artifact, checkpoint.frame_index) == snapshot
    live_total = sum(p["winner_probability"]
                     for p in snapshot["predictions"]
                     if p["winner_probability"] is not None)
    stored_total = sum(p["winner_probability"] for p in
                       read_cached_prediction(
                           artifact, checkpoint.frame_index)["predictions"]
                       if p["winner_probability"] is not None)
    assert stored_total == live_total
    write_artifact(str(tmp_path / f"{RACE_ORDINARY}.json"), artifact)
    # A prefix artifact is incomplete by design; the API must refuse it
    # explicitly (never serve partial cache as complete).
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/predictions/"
            f"{checkpoint.frame_index}")
    assert resp.status_code == 503
    assert resp.json()["reason"] == "cache_incomplete"


# ---------------------------------------------------------------------------
# No-generation structural guarantee.
# ---------------------------------------------------------------------------

FORBIDDEN_TOKENS = ["RacePredictionEngine", "FrozenWinnerPredictor",
                    "RaceStateFeatureBridge", "generate_race_artifact",
                    "ensure_race_artifact", "generate_checkpoint",
                    "load_frozen_winner_model",
                    "load_production_prediction_engine", "predict_snapshot"]


def test_replay_modules_import_no_generation_tokens():
    import ast
    for name in ("api/v2_replay_service.py", "api/v2_replay_routes.py"):
        tree = ast.parse((ROOT / name).read_text())
        used = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                used.update(a.asname or a.name for a in node.names)
                used.add(f"{node.module}.{a.name}" for a in node.names)
            elif isinstance(node, ast.Import):
                used.update(a.asname or a.name for a in node.names)
            elif isinstance(node, ast.Name):
                used.add(node.id)
            elif isinstance(node, ast.Attribute):
                used.add(node.attr)
        for token in FORBIDDEN_TOKENS:
            assert token not in used, f"{name} references {token}"


def test_replay_import_hermetic_no_model_stack():
    # Banned: the R3 generation path (engine/bridge/predictor/model-lab)
    # and the Phase-4 prediction service. Allowed: raceintel.features.* (frozen
    # factual gap geometry owned by the reconstructor) and everything the
    # R1/R2/R3-read domains need.
    script = ("import sys; "
              "import api.v2_replay_service, api.v2_replay_routes; "
              "banned = [m for m in sys.modules if m.startswith("
              "('raceintel.prediction', 'raceintel.race_state.race_state_features', 'raceintel.model_lab', "
              "'api.v2_service'))]; "
              "assert not banned, banned; print('hermetic ok')")
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=str(ROOT), capture_output=True,
        text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr
    assert "hermetic ok" in completed.stdout


def test_stale_cache_never_regenerates(tmp_path):
    service = make_service(tmp_path)
    artifact, series = write_hit_artifact(service, tmp_path)
    before = (tmp_path / f"{RACE_PARTIAL}.json").read_bytes()
    path = str(tmp_path / f"{RACE_PARTIAL}.json")
    with open(path) as handle:
        payload = json.load(handle)
    payload["cache_identity"]["probability_semantics"] = "MUTATED"
    with open(path, "w") as handle:
        json.dump(payload, handle)
    checkpoint = series.checkpoints[1]
    started = time.perf_counter()
    with pytest.raises(PredictionUnavailableError) as exc:
        service.get_prediction(RACE_PARTIAL, checkpoint.frame_index)
    assert time.perf_counter() - started < 2.0
    assert exc.value.reason == "cache_stale"
    assert (tmp_path / f"{RACE_PARTIAL}.json").read_bytes() != before
    with open(path, "rb") as handle:
        assert b"MUTATED" in handle.read()  # artifact untouched by read path


# ---------------------------------------------------------------------------
# Error contract.
# ---------------------------------------------------------------------------

def test_error_bodies_pinned_no_leak(tmp_path):
    service = make_service(tmp_path)
    series = service.get_series(RACE_ORDINARY)
    hits = {c.frame_index for c in series.checkpoints}
    plain = next(i for i in range(1, 400) if i not in hits)
    checkpoint = service.get_series(RACE_PARTIAL).checkpoints[0]
    with replay_client(service) as client:
        bodies = [
            client.get(
                "/v2/races/nope-not-a-race/replay/timeline").json(),
            client.get(
                f"/v2/races/{RACE_ORDINARY}/replay/frames/999999").json(),
            client.get(
                f"/v2/races/{RACE_ORDINARY}/replay/predictions/"
                f"{plain}").json(),
            client.get(
                f"/v2/races/{RACE_PARTIAL}/replay/predictions/"
                f"{checkpoint.frame_index}").json(),
        ]
    assert [b["error"] for b in bodies] == [
        "unknown_race", "unknown_frame", "not_prediction_checkpoint",
        "prediction_unavailable"]
    for body in bodies:
        assert set(body) <= {"error", "detail", "reason",
                             "previous_prediction_checkpoint_frame",
                             "next_prediction_checkpoint_frame"}
        blob = json.dumps(body)
        assert "Traceback" not in blob and ".py" not in blob
        assert "/tmp" not in blob and "checkpoints/" not in blob


# ---------------------------------------------------------------------------
# 2025 firewall.
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("path", [
    "/v2/races/2025-r01-R/replay/timeline",
    "/v2/races/2025-r01-R/replay/frames/0",
    "/v2/races/2025-r01-R/replay/predictions/0",
])
def test_2025_excluded_from_replay(tmp_path, path):
    service = make_service(tmp_path)
    with replay_client(service) as client:
        resp = client.get(path)
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_race"


# ---------------------------------------------------------------------------
# Route inventory: additive integration, frozen families preserved.
# ---------------------------------------------------------------------------

def test_route_inventory_additive(tmp_path):
    service = make_service(tmp_path)
    with replay_client(service) as client:
        paths = client.get("/openapi.json").json()["paths"]
    for path in ("/v2/races/{race_id}/replay/timeline",
                 "/v2/races/{race_id}/replay/frames/{frame_index}",
                 "/v2/races/{race_id}/replay/predictions/{frame_index}"):
        assert path in paths, path
    for path in ("/v2/races", "/v2/races/{race_id}/states",
                 "/v2/races/{race_id}/state",
                 "/v2/predictions/winner-snapshot"):
        assert path in paths, path
    for legacy in ("/health", "/races", "/predict/ensemble",
                   "/predict/single-model"):
        assert legacy in paths, legacy


def test_legacy_health_untouched(api_client):
    assert api_client.get("/health").json() == {"status": "ok"}


# ---------------------------------------------------------------------------
# 2023 Bahrain integration sweep.
# ---------------------------------------------------------------------------

def test_bahrain_2023_integration(tmp_path):
    service = make_service(tmp_path)
    total = service.get_timeline(RACE_ORDINARY).frame_count
    with replay_client(service) as client:
        first = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/timeline",
            params={"limit": 3}).json()
        assert first["total_frames"] == total
        last = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/timeline",
            params={"offset": total - 1}).json()
        assert last["frames"][0]["frame_index"] == total - 1
        for index in (0, total // 2, total - 1):
            frame = client.get(
                f"/v2/races/{RACE_ORDINARY}/replay/frames/{index}").json()
            assert frame["frame"]["frame_index"] == index
            assert frame["leader_lap"] is not None
            assert frame["state"]["roster_size"] == len(
                frame["state"]["drivers"])
        zero = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/frames/0").json()
        assert zero["is_prediction_checkpoint"] is True
        assert zero["checkpoint_reasons"] == ["LEADER_LAP"]


# ---------------------------------------------------------------------------
# Performance + memory smoke (generous bounds; actuals recorded in plan).
# ---------------------------------------------------------------------------

def test_performance_smoke(tmp_path, capsys):
    states, recon = get_corpus()
    started = time.perf_counter()
    service = V2ReplayService(
        states, recon, [race for _, race in FIXTURES],
        checkpoints_dir=str(tmp_path), scientific_inputs=dict(SYN_SCI))
    init_s = time.perf_counter() - started
    started = time.perf_counter()
    service.get_timeline(RACE_ORDINARY)
    cold_s = time.perf_counter() - started
    started = time.perf_counter()
    service.get_timeline(RACE_ORDINARY)
    warm_s = time.perf_counter() - started
    total = service.get_timeline(RACE_ORDINARY).frame_count
    started = time.perf_counter()
    service.get_frame(RACE_ORDINARY, total // 2)
    frame_s = time.perf_counter() - started
    write_hit_artifact(service, tmp_path)
    checkpoint = service.get_series(RACE_PARTIAL).checkpoints[0]
    started = time.perf_counter()
    service.get_prediction(RACE_PARTIAL, checkpoint.frame_index)
    cached_s = time.perf_counter() - started
    with capsys.disabled():
        print(f"\n[R4-perf] init={init_s:.3f}s timeline_cold={cold_s:.3f}s "
              f"timeline_warm={warm_s:.4f}s frame={frame_s:.3f}s "
              f"cached_prediction={cached_s:.4f}s")
    assert init_s < 2.0
    assert cold_s < 1.0  # R0 target, ~ms in practice
    assert warm_s < 0.2
    assert frame_s < 5.0  # reports vs the ~150 ms R2 baseline in the plan
    assert cached_s < 2.0


def test_memory_bounded_reuse(tmp_path):
    service = make_service(tmp_path)
    states, _ = get_corpus()
    assert service._states is states  # shared corpus, no second load
    for race_id in [race for _, race in FIXTURES]:
        service.get_timeline(race_id)
    assert set(service._timelines) == {race for _, race in FIXTURES}
    before = (len(service._timelines), len(service._resolvers),
              len(service._series))
    service.get_frame(RACE_ORDINARY, 3)
    service.get_frame(RACE_ORDINARY, 4)
    assert (len(service._timelines), len(service._resolvers),
            len(service._series)) == (before[0], before[1] + 1, before[2] + 1)
    service.get_frame(RACE_ORDINARY, 5)
    assert (len(service._timelines), len(service._resolvers),
            len(service._series)) == (before[0], before[1] + 1, before[2] + 1)
