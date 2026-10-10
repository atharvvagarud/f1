"""V3.6F cache tests: key, validation, parity, robustness, catalogue."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from api.v2_service import load_v2_service
from api.v2_strategy_v3_service import (
    CACHE_SCHEMA_VERSION,
    V3CacheInvalidError,
    V3CacheMissError,
    artifact_bytes,
    artifact_hash,
    build_cache_artifact,
    build_cache_key,
    build_manifest,
    build_v3_strategy_service,
    cache_filename,
    get_v3_strategy_service,
    read_cache_artifact,
    validate_cached_artifact,
    write_cache_artifact,
)

ORDINARY = dict(race_id="2022-r01-R", anchor_driver_id="perez",
                anchor_lap_number=30, anchor_state_time_s=6745.686)
WET = dict(race_id="2018-r11-R", anchor_driver_id="alonso",
           anchor_lap_number=44, anchor_state_time_s=4004.408)

SCIENTIFIC_FIELDS = (
    "engine_version", "execution_contract_version",
    "outcome_schema_version", "strategy_identity", "state_identity",
    "parameter_identity", "config_identity", "master_seed",
    "simulation_count", "target_driver_id", "supported",
    "unsupported_reason", "reference_kind", "alternatives", "leaders",
    "provenance",
)


def _scientific(payload: dict) -> dict:
    return {k: payload[k] for k in SCIENTIFIC_FIELDS}


@pytest.fixture(scope="module")
def v2_service():
    return load_v2_service()


@pytest.fixture(scope="module")
def service(v2_service, tmp_path_factory):
    return build_v3_strategy_service(
        v2_service,
        cache_dir=tmp_path_factory.mktemp("v3cache"),
        simulation_count=200)


@pytest.fixture(scope="module")
def full_live(service):
    return service.run_comparison(
        **ORDINARY, target_driver_id="perez",
        alternatives=None, mode="live")


@pytest.fixture(scope="module")
def cached_service(service, full_live, tmp_path_factory):
    payload = full_live
    scientific = _scientific(payload)
    artifact = build_cache_artifact(
        cache_key=payload["cache_key"], result_dict=scientific,
        request_meta={
            "race_id": ORDINARY["race_id"],
            "anchor_driver_id": ORDINARY["anchor_driver_id"],
            "anchor_lap_number": ORDINARY["anchor_lap_number"],
            "anchor_state_time_s": ORDINARY["anchor_state_time_s"],
            "target_driver_id": "perez",
            "master_seed": payload["master_seed"],
        })
    write_cache_artifact(service.cache_dir, artifact)
    return service


# ===========================================================================
# Cache key.
# ===========================================================================

def test_cache_key_deterministic(full_live):
    kwargs = dict(state_identity=full_live["state_identity"],
                  parameter_identity=full_live["parameter_identity"],
                  config_identity=full_live["config_identity"],
                  simulation_count=full_live["simulation_count"],
                  master_seed=full_live["master_seed"],
                  target_driver_id="perez")
    assert build_cache_key(**kwargs) == full_live["cache_key"]
    assert build_cache_key(**kwargs) == build_cache_key(**kwargs)


def test_cache_key_scientific_identity_sensitive(full_live):
    base = dict(state_identity=full_live["state_identity"],
                parameter_identity=full_live["parameter_identity"],
                config_identity=full_live["config_identity"],
                simulation_count=full_live["simulation_count"],
                master_seed=full_live["master_seed"],
                target_driver_id="perez")
    original = build_cache_key(**base)
    for field, other in (("master_seed", 7),
                         ("target_driver_id", "verstappen"),
                         ("simulation_count", 201),
                         ("state_identity", "0" * 64)):
        mutated = dict(base)
        mutated[field] = other
        assert build_cache_key(**mutated) != original, field


def test_cache_filename_hex_only():
    name = cache_filename("a" * 64)
    assert name == f"v3strat_{'a' * 64}.json"
    with pytest.raises(V3CacheInvalidError):
        cache_filename("../../etc/passwd")
    with pytest.raises(V3CacheInvalidError):
        cache_filename("not-a-key")


# ===========================================================================
# Roundtrip + live/cache parity.
# ===========================================================================

def test_cache_roundtrip_exact(service, full_live):
    scientific = _scientific(full_live)
    artifact = build_cache_artifact(
        cache_key=full_live["cache_key"], result_dict=scientific,
        request_meta={"race_id": "2022-r01-R"})
    raw = artifact_bytes(artifact)
    assert artifact_bytes(json.loads(raw.decode())) == raw
    write_cache_artifact(service.cache_dir, artifact)
    loaded = read_cache_artifact(service.cache_dir,
                                 full_live["cache_key"])
    assert artifact_hash(loaded) == artifact_hash(artifact)
    stored = validate_cached_artifact(
        loaded, cache_key=full_live["cache_key"],
        state_identity=scientific["state_identity"],
        parameter_identity=scientific["parameter_identity"],
        config_identity=scientific["config_identity"],
        simulation_count=scientific["simulation_count"],
        master_seed=scientific["master_seed"],
        target_driver_id="perez")
    assert json.dumps(stored, sort_keys=True) == json.dumps(
        scientific, sort_keys=True)


def test_api_cached_equals_api_live(cached_service):
    kw = dict(ORDINARY)
    for sub in ([{"action": "STAY_OUT"}],
                [{"action": "PIT_NOW", "requested_compound": "MEDIUM"},
                 {"action": "STAY_OUT"}],
                None):
        live = cached_service.run_comparison(
            **kw, target_driver_id="perez", alternatives=sub, mode="live")
        cached = cached_service.run_comparison(
            **kw, target_driver_id="perez", alternatives=sub, mode="cached")
        assert cached["execution_source"] == "cache"
        assert cached["strategy_identity"] == live["strategy_identity"]
        strip = lambda p: {k: v for k, v in p.items()
                           if k not in ("runtime", "execution_source")}
        assert json.dumps(strip(cached), sort_keys=True) == json.dumps(
            strip(live), sort_keys=True)


def test_cached_subset_identity_matches_direct_subset(service,
                                                      cached_service):
    # Request order must not matter: canonical engine order is served.
    first = cached_service.run_comparison(
        **ORDINARY, target_driver_id="perez",
        alternatives=[{"action": "STAY_OUT"},
                      {"action": "PIT_NOW"}], mode="cached")
    second = cached_service.run_comparison(
        **ORDINARY, target_driver_id="perez",
        alternatives=[{"action": "PIT_NOW"},
                      {"action": "STAY_OUT"}], mode="cached")
    assert first["strategy_identity"] == second["strategy_identity"]


# ===========================================================================
# Validation failures fail closed.
# ===========================================================================

def test_cache_miss_explicit(cached_service):
    with pytest.raises(V3CacheMissError):
        cached_service.run_comparison(
            **ORDINARY, target_driver_id="verstappen",
            alternatives=[{"action": "STAY_OUT"}], mode="cached")


def test_corrupt_cache_rejected(service, full_live, tmp_path):
    scientific = _scientific(full_live)
    artifact = build_cache_artifact(
        cache_key=full_live["cache_key"], result_dict=scientific,
        request_meta={})
    path = write_cache_artifact(tmp_path, artifact)
    path.write_bytes(b"{not valid json")
    with pytest.raises(V3CacheInvalidError):
        read_cache_artifact(tmp_path, full_live["cache_key"])


def test_provenance_mismatch_rejected(service, full_live, tmp_path):
    scientific = _scientific(full_live)
    tampered = dict(scientific)
    tampered["engine_version"] = "v3.6c-engine-evil"
    artifact = {"cache_schema_version": CACHE_SCHEMA_VERSION,
                "cache_key_version": "x",
                "cache_key": full_live["cache_key"],
                "result": tampered, "request": {}}
    with pytest.raises(V3CacheInvalidError):
        validate_cached_artifact(
            artifact, cache_key=full_live["cache_key"],
            state_identity=scientific["state_identity"],
            parameter_identity=scientific["parameter_identity"],
            config_identity=scientific["config_identity"],
            simulation_count=scientific["simulation_count"],
            master_seed=scientific["master_seed"],
            target_driver_id="perez")


def test_stale_schema_rejected(service, full_live):
    scientific = _scientific(full_live)
    artifact = {"cache_schema_version": "v0-ancient",
                "cache_key": full_live["cache_key"],
                "result": scientific, "request": {}}
    with pytest.raises(V3CacheInvalidError):
        validate_cached_artifact(
            artifact, cache_key=full_live["cache_key"],
            state_identity=scientific["state_identity"],
            parameter_identity=scientific["parameter_identity"],
            config_identity=scientific["config_identity"],
            simulation_count=scientific["simulation_count"],
            master_seed=scientific["master_seed"],
            target_driver_id="perez")


# ===========================================================================
# Robustness: traversal, malformed payloads, live-disabled, unsupported.
# ===========================================================================

def test_no_arbitrary_cache_file_selection(cached_service, tmp_path):
    evil = tmp_path / "evil.json"
    evil.write_text("{}")
    with pytest.raises(V3CacheInvalidError):
        cache_filename(str(evil))
    with pytest.raises(V3CacheInvalidError):
        read_cache_artifact(tmp_path, "evil.json")
    leftovers = [p.name for p in cached_service.cache_dir.iterdir()]
    assert all(n.startswith("v3strat_") and n.endswith(".json")
               for n in leftovers)


def test_route_cache_miss_and_invalid_are_explicit(cached_service):
    from api.main import app
    app.dependency_overrides[get_v3_strategy_service] = (
        lambda: cached_service)
    try:
        with TestClient(app) as test_client:
            body = dict(ORDINARY)
            body.update(target_driver_id="verstappen", mode="cached",
                        alternatives=[{"action": "STAY_OUT"}])
            response = test_client.post("/v2/strategies/compare-v3",
                                        json=body)
            assert response.status_code == 404
            assert response.json()["error"] == "cache_miss"
    finally:
        app.dependency_overrides.pop(get_v3_strategy_service, None)


def test_live_disabled_cache_only(v2_service, cached_service):
    frozen = build_v3_strategy_service(
        v2_service, cache_dir=cached_service.cache_dir,
        allow_live=False, simulation_count=200)
    from api.main import app
    app.dependency_overrides[get_v3_strategy_service] = lambda: frozen
    try:
        with TestClient(app) as test_client:
            live_body = dict(ORDINARY)
            live_body.update(target_driver_id="perez", mode="live",
                             alternatives=[{"action": "STAY_OUT"}])
            response = test_client.post("/v2/strategies/compare-v3",
                                        json=live_body)
            assert response.status_code == 503
            assert response.json()["error"] == "live_engine_disabled"
            cached_body = dict(live_body)
            cached_body["mode"] = "cached"
            response = test_client.post("/v2/strategies/compare-v3",
                                        json=cached_body)
            assert response.status_code == 200
            assert response.json()["execution_source"] == "cache"
    finally:
        app.dependency_overrides.pop(get_v3_strategy_service, None)


def test_unsupported_cached_explicit(service):
    payload = service.run_comparison(
        **WET, target_driver_id="alonso",
        alternatives=[{"action": "STAY_OUT"}], mode="live")
    assert payload["supported"] is False
    scientific = _scientific(payload)
    artifact = build_cache_artifact(
        cache_key=payload["cache_key"], result_dict=scientific,
        request_meta={"race_id": WET["race_id"]})
    write_cache_artifact(service.cache_dir, artifact)
    served = service.run_comparison(
        **WET, target_driver_id="alonso",
        alternatives=[{"action": "STAY_OUT"}], mode="cached")
    assert served["supported"] is False
    assert served["unsupported_reason"] == payload["unsupported_reason"]
    assert all(a["evaluated"] is False
               for a in served["alternatives"])


# ===========================================================================
# Manifest + catalogue determinism.
# ===========================================================================

def test_manifest_deterministic():
    entries = [
        {"race_id": "2022-r01-R", "anchor_lap_number": 30,
         "anchor_state_time_s": 6745.686, "target_driver_id": "perez",
         "cache_key": "b" * 64},
        {"race_id": "2018-r11-R", "anchor_lap_number": 44,
         "anchor_state_time_s": 4004.408, "target_driver_id": "alonso",
         "cache_key": "a" * 64},
    ]
    first = json.dumps(build_manifest(entries), sort_keys=True)
    second = json.dumps(build_manifest(list(reversed(entries))),
                        sort_keys=True)
    assert first == second
    manifest = json.loads(first)
    assert manifest["entry_count"] == 2
    assert manifest["entries"][0]["race_id"] == "2018-r11-R"


def test_catalogue_deterministic_and_served(cached_service):
    first = cached_service.describe_availability()
    second = cached_service.describe_availability()
    assert json.dumps(first, sort_keys=True) == json.dumps(
        second, sort_keys=True)
    assert first["entry_count"] >= 1
    assert first["engine_version"] == "v3.6c-engine-v1"
    from api.main import app
    app.dependency_overrides[get_v3_strategy_service] = (
        lambda: cached_service)
    try:
        with TestClient(app) as test_client:
            response = test_client.get(
                "/v2/strategies/v3/availability")
            assert response.status_code == 200, response.text
            payload = response.json()
            assert payload["entry_count"] == first["entry_count"]
            narrowed = test_client.get(
                "/v2/strategies/v3/availability",
                params={"race_id": "2022-r01-R"})
            assert all(e["race_id"] == "2022-r01-R"
                       for e in narrowed.json()["entries"])
    finally:
        app.dependency_overrides.pop(get_v3_strategy_service, None)
