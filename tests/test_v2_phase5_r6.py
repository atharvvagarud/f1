"""Phase-5 R6: probability timeline projection + HTTP tests.

Covers the read-only R3-artifact -> ProbabilityTimeline projection and the
``GET /v2/races/{race_id}/replay/probability-timeline`` endpoint over a real
canonical slice with synthetic R3 artifacts (no model load, no backfill).
Scientific grain, null preservation, roster completeness, no-normalization,
deterministic identity, tampered-identity rejection, cache state mapping,
HTTP parity, the read-only/no-generation firewall, payload and performance
smoke.

The real production cache is NEVER required: artifacts are built in tmpdir
via the frozen R3 writers with synthetic snapshots.
"""

from __future__ import annotations

import ast
import copy
import json
import subprocess
import sys
import time
from contextlib import contextmanager
from pathlib import Path

import pytest

from api.v2_replay_service import (
    PredictionUnavailableError,
    V2ReplayService,
)
from v2 import replay as RP
from v2.race_state_reconstruction import RaceNotFoundError
from v2.replay_predictions import (
    REPLAY_PREDICTION_CONTRACT_VERSION,
    build_artifact as _build_artifact,
    cache_identity_inputs,
    canonical_data_identity,
    write_artifact,
)
from v2.replay_probability_timeline import (
    PROBABILITY_TIMELINE_CONTRACT_VERSION,
    ProbabilityTimelineError,
    InconsistentTimelineError,
    build_probability_timeline,
    canonical_timeline_json,
    timeline_identity,
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
        import pandas as pd

        from v2.race_state_reconstruction import RaceStateReconstructor
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


def build_artifact(service, race_id=RACE_PARTIAL, null_drivers=(),
                   scale=1.0, model=None, prefix=None):
    states, _ = get_corpus()
    series = service.get_series(race_id)
    roster = sorted(set(
        states[states["race_id"] == race_id]["driver_id"]))
    snapshots = {}
    generated = series.checkpoints if prefix is None \
        else series.checkpoints[:prefix]
    for order, checkpoint in enumerate(generated):
        probs = {d: (0.09 + 0.001 * ((order + i) % 7)) * scale
                 for i, d in enumerate(roster)}
        snapshots[checkpoint.frame_index] = synth_snapshot(
            checkpoint, roster, probs, null_drivers=null_drivers)
        if model is not None:
            snapshots[checkpoint.frame_index]["model"] = dict(model)
    artifact = _build_artifact(series, snapshots, dict(model or MODEL_DICT),
                               synth_inputs(service, series, race_id))
    return artifact, series


def write_cached(service, tmp_path, race_id=RACE_PARTIAL, **kwargs):
    artifact, series = build_artifact(service, race_id, **kwargs)
    write_artifact(str(tmp_path / f"{race_id}.json"), artifact)
    return artifact, series


# ---------------------------------------------------------------------------
# Domain projection: grain, ordering, metadata, roster, nulls.
# ---------------------------------------------------------------------------

def test_contract_versions(tmp_path):
    series = make_service(tmp_path).get_series(RACE_PARTIAL)
    assert REPLAY_PREDICTION_CONTRACT_VERSION == "v1"
    assert PROBABILITY_TIMELINE_CONTRACT_VERSION == "v1"
    assert series.prediction_contract_version == "v1"


def test_projection_basic_shape(tmp_path):
    service = make_service(tmp_path)
    artifact, series = build_artifact(service)
    timeline = build_probability_timeline(artifact)
    assert timeline["race_id"] == RACE_PARTIAL
    assert timeline["replay_contract_version"] == "v1"
    assert timeline["prediction_contract_version"] == "v1"
    assert timeline["probability_timeline_contract_version"] == "v1"
    assert timeline["probability_semantics"] == "INDEPENDENT_BINARY"
    assert timeline["model"] == MODEL_DICT
    assert len(timeline["checkpoints"]) == series.checkpoint_count
    assert len(timeline["driver_series"]) == len(
        set(race_states(RACE_PARTIAL)["driver_id"]))


def test_series_grain_is_driver_by_checkpoint(tmp_path):
    service = make_service(tmp_path)
    artifact, series = build_artifact(service)
    timeline = build_probability_timeline(artifact)
    expected = [c.frame_index for c in series.checkpoints]
    for entry in timeline["driver_series"]:
        assert [p["frame_index"] for p in entry["points"]] == expected


def test_no_frame_expansion(tmp_path):
    service = make_service(tmp_path)
    artifact, series = build_artifact(service)
    timeline = build_probability_timeline(artifact)
    frames = {p["frame_index"] for entry in timeline["driver_series"]
              for p in entry["points"]}
    assert frames == {c.frame_index for c in series.checkpoints}
    # No interpolated frames between actual checkpoints.
    assert len(frames) == series.checkpoint_count


def test_driver_ordering_deterministic_ascending(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    timeline = build_probability_timeline(artifact)
    ids = [entry["driver_id"] for entry in timeline["driver_series"]]
    assert ids == sorted(ids)
    for entry in timeline["driver_series"]:
        assert [p["frame_index"] for p in entry["points"]] == sorted(
            p["frame_index"] for p in entry["points"])


def test_checkpoint_metadata_preserved(tmp_path):
    service = make_service(tmp_path)
    artifact, series = build_artifact(service)
    timeline = build_probability_timeline(artifact)
    for meta, checkpoint in zip(timeline["checkpoints"],
                                series.checkpoints):
        assert meta["frame_index"] == checkpoint.frame_index
        assert meta["state_time_s"] == checkpoint.anchor_state_time_s
        assert meta["leader_lap"] == checkpoint.leader_lap
        assert meta["reasons"] == list(checkpoint.reasons)


def test_complete_roster_preserved(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    timeline = build_probability_timeline(artifact)
    roster = sorted(set(race_states(RACE_PARTIAL)["driver_id"]))
    assert [e["driver_id"] for e in timeline["driver_series"]] == roster


def test_null_probability_preserved_never_zero(tmp_path):
    service = make_service(tmp_path)
    roster = sorted(set(race_states(RACE_PARTIAL)["driver_id"]))
    artifact, series = build_artifact(service, null_drivers=(roster[0],))
    timeline = build_probability_timeline(artifact)
    target = next(e for e in timeline["driver_series"]
                  if e["driver_id"] == roster[0])
    assert target["points"], "null driver must still appear"
    assert all(p["winner_probability"] is None for p in target["points"])
    assert series.checkpoint_count == len(target["points"])


def test_model_identity_once_at_top_level(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    timeline = build_probability_timeline(artifact)
    assert timeline["model"] == MODEL_DICT
    # Points and checkpoints carry no model identity of their own.
    for entry in timeline["driver_series"]:
        for point in entry["points"]:
            assert "model" not in point
    for meta in timeline["checkpoints"]:
        assert "model" not in meta


# ---------------------------------------------------------------------------
# INDEPENDENT_BINARY preservation.
# ---------------------------------------------------------------------------

def test_sum_greater_than_one_preserved(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service, scale=3.0)
    timeline = build_probability_timeline(artifact)
    idx = len(timeline["checkpoints"]) // 2
    total = sum(
        entry["points"][idx]["winner_probability"]
        for entry in timeline["driver_series"]
        if entry["points"][idx]["winner_probability"] is not None)
    assert total > 1.0
    # Values pass through verbatim (no scaling toward 1.0).
    stored = artifact["checkpoints"][idx]["prediction"]["predictions"]
    assert total == pytest.approx(sum(
        p["winner_probability"] for p in stored
        if p["winner_probability"] is not None), rel=0, abs=0)


def test_sum_less_than_one_preserved(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service, scale=0.5)
    timeline = build_probability_timeline(artifact)
    idx = len(timeline["checkpoints"]) // 2
    total = sum(
        entry["points"][idx]["winner_probability"]
        for entry in timeline["driver_series"]
        if entry["points"][idx]["winner_probability"] is not None)
    assert total < 1.0
    blob = canonical_timeline_json(timeline)
    assert "probability_share" not in blob
    assert "normaliz" not in blob.lower()


def test_no_normalization_field_anywhere(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service, scale=1.7)
    timeline = build_probability_timeline(artifact)
    blob = canonical_timeline_json(timeline)
    assert "share" not in blob
    assert "renormal" not in blob.lower()


# ---------------------------------------------------------------------------
# Determinism / identity.
# ---------------------------------------------------------------------------

def test_repeated_projection_byte_identical(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    first = canonical_timeline_json(build_probability_timeline(artifact))
    second = canonical_timeline_json(build_probability_timeline(
        copy.deepcopy(artifact)))
    assert first == second


def test_timeline_identity_deterministic(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    first = build_probability_timeline(artifact)
    second = build_probability_timeline(copy.deepcopy(artifact))
    assert first["timeline_identity"] == second["timeline_identity"]
    assert first["timeline_identity"] == timeline_identity(first)
    assert len(first["timeline_identity"]) == 64


def test_identity_ignores_unrelated_artifact_fields(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    baseline = build_probability_timeline(artifact)
    mutated = copy.deepcopy(artifact)
    # Unrelated metadata R6 does not consume must not move the identity.
    mutated["cache_identity"]["serving_artifact_sha256"] = "different"
    mutated["cache_key"] = "different"
    mutated["series"] = {"unused": True}
    after = build_probability_timeline(mutated)
    assert after["timeline_identity"] == baseline["timeline_identity"]
    assert canonical_timeline_json(after) == canonical_timeline_json(baseline)


# ---------------------------------------------------------------------------
# Tampered / inconsistent artifact rejection.
# ---------------------------------------------------------------------------

def test_incomplete_artifact_rejected(tmp_path):
    service = make_service(tmp_path)
    artifact, series = build_artifact(service, prefix=1)
    assert artifact["complete"] is False
    with pytest.raises(ProbabilityTimelineError):
        build_probability_timeline(artifact)


def test_unknown_format_rejected(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    artifact["artifact_format"] = "something-else"
    with pytest.raises(ProbabilityTimelineError):
        build_probability_timeline(artifact)


def test_per_entry_model_drift_rejected(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    tampered = copy.deepcopy(artifact)
    tampered["checkpoints"][1]["prediction"]["model"] = dict(
        MODEL_DICT, artifact_sha256="tampered")
    with pytest.raises(InconsistentTimelineError):
        build_probability_timeline(tampered)


def test_non_independent_binary_model_rejected(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    tampered = copy.deepcopy(artifact)
    tampered["model"] = dict(MODEL_DICT,
                             probability_semantics="NORMALIZED_SHARE")
    with pytest.raises(InconsistentTimelineError):
        build_probability_timeline(tampered)


def test_non_increasing_frame_rejected(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    tampered = copy.deepcopy(artifact)
    tampered["checkpoints"][1]["checkpoint"]["frame_index"] = \
        tampered["checkpoints"][0]["checkpoint"]["frame_index"]
    with pytest.raises(ProbabilityTimelineError):
        build_probability_timeline(tampered)


def test_anchor_mismatch_rejected(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    tampered = copy.deepcopy(artifact)
    tampered["checkpoints"][0]["prediction"]["anchor_driver_id"] = "mismatch"
    with pytest.raises(InconsistentTimelineError):
        build_probability_timeline(tampered)


def test_roster_drift_rejected(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    tampered = copy.deepcopy(artifact)
    tampered["checkpoints"][1]["prediction"]["predictions"].pop()
    with pytest.raises(InconsistentTimelineError):
        build_probability_timeline(tampered)


def test_duplicate_driver_rejected(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    tampered = copy.deepcopy(artifact)
    drivers = tampered["checkpoints"][0]["prediction"]["predictions"]
    drivers[1]["driver_id"] = drivers[0]["driver_id"]
    with pytest.raises(ProbabilityTimelineError):
        build_probability_timeline(tampered)


def test_unsorted_reasons_rejected(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    tampered = copy.deepcopy(artifact)
    tampered["checkpoints"][0]["checkpoint"]["reasons"] = \
        ["LEADER_LAP", "FLAG_TRANSITION"]
    with pytest.raises(ProbabilityTimelineError):
        build_probability_timeline(tampered)


def test_non_finite_probability_rejected(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    tampered = copy.deepcopy(artifact)
    tampered["checkpoints"][0]["prediction"]["predictions"][0][
        "winner_probability"] = float("inf")
    with pytest.raises(ProbabilityTimelineError):
        build_probability_timeline(tampered)


def test_projection_does_not_mutate_artifact(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    before = json.dumps(artifact, sort_keys=True)
    build_probability_timeline(artifact)
    assert json.dumps(artifact, sort_keys=True) == before


# ---------------------------------------------------------------------------
# Adversarial: no inferred observations, future-data resistance.
# ---------------------------------------------------------------------------

def test_no_new_inferred_probability_observations(tmp_path):
    service = make_service(tmp_path)
    artifact, series = build_artifact(service)
    timeline = build_probability_timeline(artifact)
    projected = {
        p["frame_index"] for entry in timeline["driver_series"]
        for p in entry["points"]}
    stored = {e["checkpoint"]["frame_index"]
              for e in artifact["checkpoints"]}
    assert projected == stored
    assert projected.issubset(
        {c.frame_index for c in service.get_series(RACE_PARTIAL).checkpoints})
    # No point sits between real checkpoints (no frame interpolation).
    ordered = sorted(projected)
    assert all(b - a >= 1 for a, b in zip(ordered, ordered[1:]))


def test_unrelated_future_data_mutation_invariant(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    baseline = canonical_timeline_json(build_probability_timeline(artifact))
    mutated = copy.deepcopy(artifact)
    # R6 must not consume these fields; changing them cannot alter output.
    mutated["checkpoints"][0]["prediction"]["predictions"][0][
        "observed_position"] = 999
    mutated["checkpoints"][0]["prediction"]["predictions"][0][
        "observed_lap_number"] = 999
    mutated["checkpoints"][0]["prediction"]["observable_count"] = 999
    mutated["checkpoints"][0]["prediction"]["probability_semantics_note"] = \
        "changed note R6 does not consume"
    after = canonical_timeline_json(build_probability_timeline(mutated))
    assert after == baseline


# ---------------------------------------------------------------------------
# Cache-state mapping (service).
# ---------------------------------------------------------------------------

def test_service_missing_cache(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(PredictionUnavailableError) as exc:
        service.get_probability_timeline(RACE_PARTIAL)
    assert exc.value.reason == "cache_missing"


def test_service_incomplete_cache(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service, prefix=1)
    write_artifact(str(tmp_path / f"{RACE_PARTIAL}.json"), artifact)
    with pytest.raises(PredictionUnavailableError) as exc:
        service.get_probability_timeline(RACE_PARTIAL)
    assert exc.value.reason == "cache_incomplete"


def test_service_stale_cache(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    artifact["cache_identity"]["feature_set"] = "MUTATED"
    write_artifact(str(tmp_path / f"{RACE_PARTIAL}.json"), artifact)
    with pytest.raises(PredictionUnavailableError) as exc:
        service.get_probability_timeline(RACE_PARTIAL)
    assert exc.value.reason == "cache_stale"


def test_service_corrupt_cache(tmp_path):
    service = make_service(tmp_path)
    with open(tmp_path / f"{RACE_PARTIAL}.json", "w") as handle:
        handle.write("{ not json")
    with pytest.raises(PredictionUnavailableError) as exc:
        service.get_probability_timeline(RACE_PARTIAL)
    assert exc.value.reason == "cache_corrupt"


def test_service_tampered_model_is_corrupt(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    artifact["checkpoints"][1]["prediction"]["model"] = "not-a-dict"
    write_artifact(str(tmp_path / f"{RACE_PARTIAL}.json"), artifact)
    with pytest.raises(PredictionUnavailableError) as exc:
        service.get_probability_timeline(RACE_PARTIAL)
    assert exc.value.reason == "cache_corrupt"


def test_service_unknown_race(tmp_path):
    service = make_service(tmp_path)
    with pytest.raises(RaceNotFoundError):
        service.get_probability_timeline("nope-not-a-race")


def test_service_projection_lazy_and_cached(tmp_path):
    service = make_service(tmp_path)
    write_cached(service, tmp_path)
    first = service.get_probability_timeline(RACE_PARTIAL)
    assert service.get_probability_timeline(RACE_PARTIAL) is first


# ---------------------------------------------------------------------------
# HTTP endpoint.
# ---------------------------------------------------------------------------

def test_http_endpoint_shape(tmp_path):
    service = make_service(tmp_path)
    artifact, series = build_artifact(service)
    write_artifact(str(tmp_path / f"{RACE_PARTIAL}.json"), artifact)
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/probability-timeline")
    assert resp.status_code == 200
    body = resp.json()
    assert set(body) == {
        "race_id", "replay_contract_version", "prediction_contract_version",
        "probability_timeline_contract_version", "probability_semantics",
        "model", "timeline_identity", "checkpoints", "driver_series"}
    assert body["race_id"] == RACE_PARTIAL
    assert body["probability_semantics"] == "INDEPENDENT_BINARY"
    assert body["model"] == MODEL_DICT
    assert len(body["checkpoints"]) == series.checkpoint_count
    assert set(body["checkpoints"][0]) == {
        "frame_index", "state_time_s", "leader_lap", "reasons"}
    assert set(body["driver_series"][0]) == {"driver_id", "points"}
    assert set(body["driver_series"][0]["points"][0]) == {
        "frame_index", "state_time_s", "leader_lap", "winner_probability"}


def test_http_missing_cache_503(tmp_path):
    service = make_service(tmp_path)
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/probability-timeline")
    assert resp.status_code == 503
    body = resp.json()
    assert body["error"] == "prediction_unavailable"
    assert body["reason"] == "cache_missing"


def test_http_stale_cache_503(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    artifact["cache_identity"]["feature_set"] = "MUTATED"
    write_artifact(str(tmp_path / f"{RACE_PARTIAL}.json"), artifact)
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/probability-timeline")
    assert resp.status_code == 503
    assert resp.json()["reason"] == "cache_stale"


def test_http_corrupt_cache_503(tmp_path):
    service = make_service(tmp_path)
    with open(tmp_path / f"{RACE_PARTIAL}.json", "w") as handle:
        handle.write("{ not json")
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/probability-timeline")
    assert resp.status_code == 503
    assert resp.json()["reason"] == "cache_corrupt"


def test_http_incomplete_cache_503(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service, prefix=1)
    write_artifact(str(tmp_path / f"{RACE_PARTIAL}.json"), artifact)
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/probability-timeline")
    assert resp.status_code == 503
    assert resp.json()["reason"] == "cache_incomplete"


def test_http_unknown_race_404(tmp_path):
    service = make_service(tmp_path)
    with replay_client(service) as client:
        resp = client.get(
            "/v2/races/nope-not-a-race/replay/probability-timeline")
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_race"


def test_http_2025_404(tmp_path):
    service = make_service(tmp_path)
    with replay_client(service) as client:
        resp = client.get(
            "/v2/races/2025-r01-R/replay/probability-timeline")
    assert resp.status_code == 404
    assert resp.json()["error"] == "unknown_race"


def test_http_never_generates_no_cache(tmp_path):
    service = make_service(tmp_path)
    started = time.perf_counter()
    with replay_client(service) as client:
        client.get(f"/v2/races/{RACE_PARTIAL}/replay/probability-timeline")
    # Missing cache resolves immediately (no ~12 s model run possible).
    assert time.perf_counter() - started < 2.0


# ---------------------------------------------------------------------------
# Backend parity artifact -> domain -> HTTP.
# ---------------------------------------------------------------------------

def test_http_parity_with_domain(tmp_path):
    service = make_service(tmp_path)
    artifact, series = build_artifact(service, null_drivers=("mazepin",),
                                      scale=1.7)
    write_artifact(str(tmp_path / f"{RACE_PARTIAL}.json"), artifact)
    domain = build_probability_timeline(artifact)
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/probability-timeline").json()
    assert body["checkpoints"] == [
        {k: (v if k != "reasons" else list(v))
         for k, v in meta.items()} for meta in domain["checkpoints"]]
    assert body["driver_series"] == [
        {"driver_id": s["driver_id"],
         "points": [dict(p) for p in s["points"]]}
        for s in domain["driver_series"]]
    assert body["model"] == domain["model"]
    assert body["timeline_identity"] == domain["timeline_identity"]
    # Raw stored probability values cross the HTTP boundary verbatim.
    stored = artifact["checkpoints"][2]["prediction"][
        "predictions"]
    stored_by_driver = {p["driver_id"]: p["winner_probability"]
                        for p in stored}
    driver = body["driver_series"][0]["driver_id"]
    assert body["driver_series"][0]["points"][2]["winner_probability"] == \
        stored_by_driver[driver]


def test_http_independent_binary_preserved(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service, scale=3.0)
    write_artifact(str(tmp_path / f"{RACE_PARTIAL}.json"), artifact)
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/probability-timeline").json()
    idx = len(body["checkpoints"]) // 2
    total = sum(
        s["points"][idx]["winner_probability"]
        for s in body["driver_series"]
        if s["points"][idx]["winner_probability"] is not None)
    assert total > 1.0
    assert "probability_share" not in json.dumps(body)


def test_http_null_preserved(tmp_path):
    service = make_service(tmp_path)
    roster = sorted(set(race_states(RACE_PARTIAL)["driver_id"]))
    artifact, _ = build_artifact(service, null_drivers=(roster[0],))
    write_artifact(str(tmp_path / f"{RACE_PARTIAL}.json"), artifact)
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_PARTIAL}/replay/probability-timeline").json()
    target = next(s for s in body["driver_series"]
                  if s["driver_id"] == roster[0])
    assert all(p["winner_probability"] is None for p in target["points"])


def test_http_other_race_resolves_independently(tmp_path):
    service = make_service(tmp_path)
    artifact, series = build_artifact(service, race_id=RACE_ORDINARY)
    write_artifact(str(tmp_path / f"{RACE_ORDINARY}.json"), artifact)
    with replay_client(service) as client:
        body = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/probability-timeline").json()
    assert body["race_id"] == RACE_ORDINARY
    assert len(body["checkpoints"]) == series.checkpoint_count


# ---------------------------------------------------------------------------
# Read-only / no-generation firewall.
# ---------------------------------------------------------------------------

FORBIDDEN_TOKENS = ["RacePredictionEngine", "FrozenWinnerPredictor",
                    "RaceStateFeatureBridge", "generate_race_artifact",
                    "ensure_race_artifact", "generate_checkpoint",
                    "load_frozen_winner_model",
                    "load_production_prediction_engine", "predict_snapshot"]


def test_projection_module_has_no_generation_tokens():
    tree = ast.parse(
        (ROOT / "v2/replay_probability_timeline.py").read_text())
    used = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            used.update(a.asname or a.name for a in node.names)
            used.add(f"{node.module}.{a.name}" for a in node.names)
        elif isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, ast.Attribute):
            used.add(node.attr)
    for token in FORBIDDEN_TOKENS:
        assert token not in used, f"projection references {token}"


def test_projection_import_hermetic_no_model_stack():
    script = ("import sys; "
              "import v2.replay_probability_timeline; "
              "banned = [m for m in sys.modules if m.startswith("
              "('v2.prediction', 'v2.race_state_features', 'v2.model_lab', "
              "'api.v2_service', 'sklearn'))]; "
              "assert not banned, banned; print('hermetic ok')")
    completed = subprocess.run(
        [sys.executable, "-c", script], cwd=str(ROOT), capture_output=True,
        text=True, timeout=120)
    assert completed.returncode == 0, completed.stderr
    assert "hermetic ok" in completed.stdout


def test_projection_read_does_not_modify_artifact_bytes(tmp_path):
    service = make_service(tmp_path)
    artifact, _ = build_artifact(service)
    path = tmp_path / f"{RACE_PARTIAL}.json"
    write_artifact(str(path), artifact)
    before = path.read_bytes()
    service.get_probability_timeline(RACE_PARTIAL)
    with replay_client(service) as client:
        client.get(f"/v2/races/{RACE_PARTIAL}/replay/probability-timeline")
    assert path.read_bytes() == before


def test_route_inventory_includes_probability_timeline(tmp_path):
    service = make_service(tmp_path)
    with replay_client(service) as client:
        paths = client.get("/openapi.json").json()["paths"]
    assert "/v2/races/{race_id}/replay/probability-timeline" in paths


# ---------------------------------------------------------------------------
# Payload + performance smoke (actuals recorded in the plan).
# ---------------------------------------------------------------------------

def test_payload_size_smoke(tmp_path, capsys):
    service = make_service(tmp_path)
    artifact, series = build_artifact(service, race_id=RACE_ORDINARY)
    write_artifact(str(tmp_path / f"{RACE_ORDINARY}.json"), artifact)
    with replay_client(service) as client:
        resp = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/probability-timeline")
    size = len(resp.content)
    roster = len(set(race_states(RACE_ORDINARY)["driver_id"]))
    with capsys.disabled():
        print(f"\n[R6-payload] {RACE_ORDINARY}: {series.checkpoint_count} "
              f"checkpoints x {roster} drivers = {size} bytes")
    # One-response design stays comfortably small.
    assert size < 2_000_000


def test_performance_smoke(tmp_path, capsys):
    service = make_service(tmp_path)
    artifact, series = build_artifact(service, race_id=RACE_ORDINARY)
    write_artifact(str(tmp_path / f"{RACE_ORDINARY}.json"), artifact)
    started = time.perf_counter()
    domain = service.get_probability_timeline(RACE_ORDINARY)
    project_s = time.perf_counter() - started
    started = time.perf_counter()
    service.get_probability_timeline(RACE_ORDINARY)
    warm_s = time.perf_counter() - started
    with replay_client(service) as client:
        started = time.perf_counter()
        resp = client.get(
            f"/v2/races/{RACE_ORDINARY}/replay/probability-timeline")
        http_s = time.perf_counter() - started
    assert resp.status_code == 200
    with capsys.disabled():
        print(f"\n[R6-perf] project={project_s:.4f}s warm={warm_s:.6f}s "
              f"http={http_s:.4f}s checkpoints={len(domain['checkpoints'])}")
    assert project_s < 1.0
    assert warm_s < 0.2
    assert http_s < 1.0
