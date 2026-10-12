"""V3.7F cache contract tests (deterministic; synthetic states).

Covers: cache identity determinism and permutation invariance, cache-hit
roundtrip through validation, and the full corrupt/mismatch battery
(wrong state/plan/comparison/engine/seed/count/schema, modified payload
without matching identity, truncated/malformed JSON, non-hex filenames).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
from test_v2_phase6_r6 import pit_field  # noqa: E402
from test_v2_phase7_s2_mechanics import one_driver_params  # noqa: E402

from raceintel.counterfactual import contracts as C  # noqa: E402
from raceintel.counterfactual import engine as E  # noqa: E402
from raceintel.counterfactual import runtime as R  # noqa: E402
from raceintel.simulation.config import (  # noqa: E402
    Assumptions,
    SimulationConfig,
)

COUNT = 5000
SEED = 20240101


def _state():
    return pit_field(2, scheduled=12, start_lap=1, age=1)


def _params():
    return one_driver_params(stint=5.0, pit_loss=20.0)


def _param_id():
    return _params().parameter_identity().identity()


def _cfg():
    return SimulationConfig(simulation_count=COUNT, master_seed=SEED,
                            pit_dynamics_enabled=True)


def _plan(state, specs=(("a", 2, "MEDIUM"),), targets=("a",)):
    return R.build_plan(
        state, target_driver_ids=list(targets),
        interventions=[{"target_driver_id": t, "kind": "PIT_IN_N_LAPS",
                        "lap_offset_n": n, "requested_compound": c}
                       for (t, n, c) in specs])


def _live_result(state, plan, *, rival=None):
    res = E.compare_reference_vs_plan(
        state=state, parameters=_params(), config=_cfg(),
        assumptions=Assumptions(), plan=plan, rival_driver_id=rival)
    assert res.supported is True
    return res.to_dict()


def _key_fields(state, plan, *, rival=None):
    key = R.build_comparison_key(
        state_identity=state.identity(),
        comparison_form="REFERENCE_VS_PLAN",
        base_identity=C.REFERENCE_KIND,
        alternative_identity=plan.identity(),
        rival_driver_id=rival,
        parameter_identity=_param_id(), config_identity="c" * 64)
    cache_key = R.build_cache_key(
        state_identity=state.identity(),
        comparison_form="REFERENCE_VS_PLAN",
        base_identity=C.REFERENCE_KIND,
        alternative_identity=plan.identity(),
        primary_target_driver_id=plan.target_driver_ids[0],
        rival_driver_id=rival,
        parameter_identity=_param_id(), config_identity="c" * 64,
        simulation_count=COUNT, master_seed=SEED)
    return key, cache_key


def _artifact(state, plan, *, rival=None):
    result = _live_result(state, plan, rival=rival)
    result["parameter_identity"] = _param_id()
    result["config_identity"] = "c" * 64
    key, cache_key = _key_fields(state, plan, rival=rival)
    return R.build_cache_artifact(
        cache_key=cache_key, comparison_key=key, result_dict=result,
        request_meta={"note": "test"}), key, cache_key, result


def _expected(state, plan, *, rival=None):
    _, cache_key = _key_fields(state, plan, rival=rival)
    return {"cache_key": cache_key,
            "state_identity": state.identity(),
            "comparison_form": "REFERENCE_VS_PLAN",
            "base_identity": C.REFERENCE_KIND,
            "alternative_identity": plan.identity(),
            "primary_target_driver_id": plan.target_driver_ids[0],
            "rival_driver_id": rival,
            "parameter_identity": _param_id(),
            "config_identity": "c" * 64,
            "simulation_count": COUNT, "master_seed": SEED}


# ===========================================================================
# Identity.
# ===========================================================================

def test_cache_identity_deterministic():
    state, plan = _state(), None
    plan = _plan(state)
    assert _key_fields(state, plan)[1] == _key_fields(state, plan)[1]


def test_plan_permutation_cache_identity_invariant():
    state = pit_field(3, scheduled=12, start_lap=1, age=1)
    p1 = _plan(state, specs=(("a", 2, "MEDIUM"), ("c", 4, "HARD")),
               targets=("a", "c"))
    p2 = _plan(state, specs=(("c", 4, "HARD"), ("a", 2, "MEDIUM")),
               targets=("c", "a"))
    assert _key_fields(state, p1)[1] == _key_fields(state, p2)[1]


def test_distinct_plans_distinct_keys():
    state = _state()
    k1 = _key_fields(state, _plan(state, specs=(("a", 2, "MEDIUM"),)))[1]
    k2 = _key_fields(state, _plan(state, specs=(("a", 3, "MEDIUM"),)))[1]
    assert k1 != k2


def test_cache_filename_traversal_safe():
    with pytest.raises(R.CacheInvalidError):
        R.cache_filename("../evil")
    with pytest.raises(R.CacheInvalidError):
        R.cache_filename("x" * 63)


# ===========================================================================
# Roundtrip.
# ===========================================================================

def test_write_read_validate_roundtrip(tmp_path):
    state, plan = _state(), None
    plan = _plan(state)
    artifact, _, cache_key, result = _artifact(state, plan)
    path = R.write_cache_artifact(tmp_path, artifact)
    assert path.exists()
    assert not list(tmp_path.glob("*.tmp"))  # atomic: no debris
    stored = R.validate_cached_artifact(
        R.read_cache_artifact(tmp_path, cache_key),
        **_expected(state, plan))
    assert stored["comparison_identity"] == result["comparison_identity"]
    assert (stored["served_result_identity"]
            == R.served_result_identity(result))


def test_cache_miss_explicit(tmp_path):
    with pytest.raises(R.CacheMissError):
        R.read_cache_artifact(tmp_path, "a" * 64)


def test_manifest_deterministic():
    entries = [{"race_id": "b", "anchor_lap_number": 1,
                "anchor_state_time_s": 2.0, "comparison_form": "X",
                "alternative_identity": "y"},
               {"race_id": "a", "anchor_lap_number": 1,
                "anchor_state_time_s": 2.0, "comparison_form": "X",
                "alternative_identity": "y"}]
    first = R.build_manifest(entries)
    second = R.build_manifest(list(reversed(entries)))
    assert first == second
    assert first["manifest_schema"] == "v3.7f-counterfactual-manifest-v1"
    assert first["simulation_count"] == 5000
    assert first["master_seed"] == 20240101


# ===========================================================================
# Corruption battery (never served as valid science).
# ===========================================================================

def _tampered(base, *path, value):
    import copy
    artifact = copy.deepcopy(base)
    node = artifact
    for step in path[:-1]:
        node = node[step]
    node[path[-1]] = value
    return artifact


def test_wrong_state_rejected(tmp_path):
    state, plan = _state(), None
    plan = _plan(state)
    artifact, _, _, _ = _artifact(state, plan)
    other = pit_field(2, scheduled=14, start_lap=1, age=1)
    with pytest.raises(R.CacheInvalidError):
        R.validate_cached_artifact(
            artifact, **{**_expected(state, plan),
                         "state_identity": other.identity()})


def test_wrong_plan_rejected():
    state = _state()
    artifact, _, _, _ = _artifact(state, _plan(state))
    other = _plan(state, specs=(("a", 4, "MEDIUM"),))
    with pytest.raises(R.CacheInvalidError):
        R.validate_cached_artifact(
            artifact, **{**_expected(state, other)})


def test_wrong_comparison_form_rejected():
    state, plan = _state(), None
    plan = _plan(state)
    artifact, _, _, _ = _artifact(state, plan)
    with pytest.raises(R.CacheInvalidError):
        R.validate_cached_artifact(
            artifact, **{**_expected(state, plan),
                         "comparison_form": "PLAN_VS_PLAN"})


def test_wrong_engine_identity_rejected():
    state, plan = _state(), None
    plan = _plan(state)
    artifact, _, _, _ = _artifact(state, plan)
    bad = _tampered(artifact, "result", "provenance", "engine_identity",
                    value="v9-fake")
    with pytest.raises(R.CacheInvalidError):
        R.validate_cached_artifact(bad, **_expected(state, plan))


def test_wrong_seed_rejected():
    state, plan = _state(), None
    plan = _plan(state)
    artifact, _, _, _ = _artifact(state, plan)
    with pytest.raises(R.CacheInvalidError):
        R.validate_cached_artifact(
            artifact, **{**_expected(state, plan), "master_seed": 7})


def test_wrong_count_rejected():
    state, plan = _state(), None
    plan = _plan(state)
    artifact, _, _, _ = _artifact(state, plan)
    with pytest.raises(R.CacheInvalidError):
        R.validate_cached_artifact(
            artifact, **{**_expected(state, plan),
                         "simulation_count": 100})


def test_wrong_schema_rejected():
    state, plan = _state(), None
    plan = _plan(state)
    artifact, _, _, _ = _artifact(state, plan)
    bad = _tampered(artifact, "cache_schema_version",
                    value="v9-fake")
    with pytest.raises(R.CacheInvalidError):
        R.validate_cached_artifact(bad, **_expected(state, plan))


def test_modified_payload_without_identity_rejected():
    state, plan = _state(), None
    plan = _plan(state)
    artifact, _, _, _ = _artifact(state, plan)
    bad = _tampered(
        artifact, "result", "alternative_aggregate", "expected_finish",
        value=-1000.0)
    with pytest.raises(R.CacheInvalidError):
        R.validate_cached_artifact(bad, **_expected(state, plan))


def test_malformed_and_truncated_rejected(tmp_path):
    state, plan = _state(), None
    plan = _plan(state)
    _, _, cache_key, _ = _artifact(state, plan)
    path = tmp_path / R.cache_filename(cache_key)
    path.write_bytes(b"{not json")
    with pytest.raises(R.CacheInvalidError):
        R.validate_cached_artifact(
            R.read_cache_artifact(tmp_path, cache_key),
            **_expected(state, plan))
    path.write_bytes(b'{"cache_schema_version":')
    with pytest.raises(R.CacheInvalidError):
        R.validate_cached_artifact(
            R.read_cache_artifact(tmp_path, cache_key),
            **_expected(state, plan))
    path.write_bytes(json.dumps({"cache_schema_version":
                                 R.CACHE_SCHEMA_VERSION}).encode())
    with pytest.raises(R.CacheInvalidError):
        R.validate_cached_artifact(
            R.read_cache_artifact(tmp_path, cache_key),
            **_expected(state, plan))
