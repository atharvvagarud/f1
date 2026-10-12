"""V3.7F runtime adapter tests (no API, no cache transport, no frontend).

Fast synthetic-state suite at the frozen production configuration
(5000 futures; ~0.1 s/arm synthetic). Covers: A/B/C/D/E provenance,
C seam hash, runtime identity, plan canonicalization, request
validation, production locking, orientation sentinels, pit-count
descriptiveness, lifecycle preservation, unsupported emptiness,
temporal safety, cost bounds, and D/V3.5 separation.
"""

from __future__ import annotations

import hashlib
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

ROOT = Path(__file__).resolve().parents[1]
SID = "s" * 64
COUNT = 5000
SEED = 20240101


def _state(n=2, scheduled=12, start_lap=1):
    return pit_field(n, scheduled=scheduled, start_lap=start_lap, age=1)


def _params():
    return one_driver_params(stint=5.0, pit_loss=20.0)


def _cfg():
    return SimulationConfig(simulation_count=COUNT, master_seed=SEED,
                            pit_dynamics_enabled=True)


def _iv(target="a", n=3, compound="MEDIUM"):
    return {"target_driver_id": target, "kind": "PIT_IN_N_LAPS",
            "lap_offset_n": n, "requested_compound": compound}


def _plan(state, targets=("a",), specs=(("a", 3, "MEDIUM"),)):
    return R.build_plan(
        state, target_driver_ids=list(targets),
        interventions=[_iv(t, n, c) for (t, n, c) in specs])


def _run(state, plan, *, rival=None):
    return E.compare_reference_vs_plan(
        state=state, parameters=_params(), config=_cfg(),
        assumptions=Assumptions(), plan=plan, rival_driver_id=rival)


# ===========================================================================
# Provenance (A/B/C/D/E) + C seam.
# ===========================================================================

def test_a_identity_exact():
    a = json.loads((ROOT / "results/v3/v3_7a/counterfactual_contract.json"
                    ).read_text())
    assert a["schema"] == "v3.7a-counterfactual-contract-v1"
    assert a["contract_hash"] == R.A_CONTRACT_IDENTITY == \
        "1735954212ec31286fede041639875610003a09cf817177e22cc908e3fcb0a12"


def test_v36_card_identity_authoritative():
    # The repository-authoritative full V3.6 card identity (artifact
    # value governs; the charter prompt carries a shortened display
    # form that must not be constructed from an ellipsis).
    card = json.loads(
        (ROOT / "results/v3/v3_6_final_scientific_card.json").read_text())
    assert card["scientific_card_identity"] == \
        "102079ab81101f442d380c109a32b71a3b6850f0106e021f0fc4b05a64c80aeb"
    a = json.loads((ROOT / "results/v3/v3_7a/counterfactual_contract.json"
                    ).read_text())
    assert a["v36_scientific_card_identity"] == \
        card["scientific_card_identity"]


def test_corrected_b_identity_exact():
    b = json.loads((ROOT / "results/v3/v3_7b/counterfactual_execution_"
                            "contract.json").read_text())
    assert b["schema"] == "v3.7b-counterfactual-execution-contract-v1"
    assert b["contract_hash"] == R.B_CONTRACT_IDENTITY == \
        "1865537503136ed3d8603e53741902c320df9387222655b38eef51640294e970"


def test_c_engine_identity_exact():
    assert E.ENGINE_IDENTITY == "v3.7c-counterfactual-engine-v1"
    v = json.loads((ROOT / "results/v3/v3_7c/counterfactual_engine_"
                            "validation.json").read_text())
    assert v["engine_identity"] == E.ENGINE_IDENTITY
    assert v["a_identity"] == R.A_CONTRACT_IDENTITY
    assert v["b_identity"] == R.B_CONTRACT_IDENTITY


def test_d_card_gate_and_protocol_exact():
    card = json.loads(
        (ROOT / "results/v3/v3_7d/evaluation_card.json").read_text())
    assert card["schema"] == "v3.7d-evaluation-card-v1"
    assert card["card_identity"] == R.D_CARD_IDENTITY == \
        "96debc6392c79019abedc3a51c7c26fb1536e97cabb3fed3136c43ed7c2b19c3"
    assert card["d_protocol_identity"] == R.D_PROTOCOL_IDENTITY == \
        "e4a6101c7267f2db9f85c76bcc07c17ed01c7f85de4a6481f94ab0941634c570"
    assert card["gate"] == R.D_GATE == "REFINEMENT_NOT_WARRANTED"
    gate = json.loads(
        (ROOT / "results/v3/v3_7d/refinement_gate.json").read_text())
    assert gate["decision"] == "REFINEMENT_NOT_WARRANTED"
    assert card["a_identity"] == R.A_CONTRACT_IDENTITY
    assert card["b_identity"] == R.B_CONTRACT_IDENTITY
    assert card["c_engine_identity"] == E.ENGINE_IDENTITY


def test_e_skipped_no_implementation():
    assert R.E_STATUS == "SKIPPED_BY_V3.7D_GATE"
    assert not list(ROOT.glob("**/*v3_7e*"))
    assert not list(ROOT.glob("**/*V3_7E*"))


def test_c_seam_hash_unchanged():
    card = json.loads(
        (ROOT / "results/v3/v3_7d/evaluation_card.json").read_text())
    raw = (ROOT / "raceintel/simulation/monte_carlo.py").read_bytes()
    assert hashlib.sha256(raw).hexdigest() == card["seam_sha256"] == \
        "045f392e46b030744f18a76140685ceba7501f80c0b8e265af662e57ca5f5376"


def test_runtime_api_cache_identities_exact():
    assert R.RUNTIME_IDENTITY == "v3.7f-counterfactual-runtime-v1"
    assert R.API_SCHEMA_VERSION == "v3.7f-counterfactual-api-v1"
    assert R.CACHE_KEY_VERSION == "v3.7f-counterfactual-cache-key-v1"
    assert R.CACHE_SCHEMA_VERSION == "v3.7f-counterfactual-cache-v1"


# ===========================================================================
# Availability description (cheap, factual-only, deterministic).
# ===========================================================================

def test_describe_state_factual_only_and_deterministic():
    state = _state()
    first, second = R.describe_state(state), R.describe_state(state)
    assert first == second
    assert first["state_identity"] == state.identity()
    assert first["race_id"] == state.race_id
    assert [d["driver_id"] for d in first["drivers"]] == ["a", "b"]
    by_id = {d["driver_id"]: d for d in first["drivers"]}
    # start_lap=1, scheduled=12 -> remaining=11, N in 1..10.
    assert by_id["a"]["decision_lap"] == 1
    assert by_id["a"]["remaining_laps"] == 11
    assert by_id["a"]["eligible_n_min"] == 1
    assert by_id["a"]["eligible_n_max"] == 10
    assert by_id["a"]["eligible"] is True
    assert first["eligible_targets"] == ["a", "b"]
    assert first["supported_compounds"] == ["SOFT", "MEDIUM", "HARD",
                                            "SAMPLED"]
    assert first["comparison_forms"] == ["REFERENCE_VS_PLAN",
                                         "PLAN_VS_PLAN"]
    assert first["multi_stop_capable"] is True
    assert first["multi_driver_capable"] is True
    blob = json.dumps(first, sort_keys=True)
    for token in ("future", "result", "winner", "recommendation"):
        assert token not in blob


def test_describe_state_no_eligible_targets():
    state = pit_field(1, scheduled=3, start_lap=2)  # remaining=1 -> N empty
    desc = R.describe_state(state)
    assert desc["eligible_targets"] == []
    assert desc["drivers"][0]["eligible"] is False
    assert desc["multi_stop_capable"] is False


# ===========================================================================
# Request validation (fail closed, never coerced).
# ===========================================================================

def test_n_zero_rejected():
    with pytest.raises(R.RuntimeRequestError):
        R.build_plan(_state(), target_driver_ids=["a"],
                     interventions=[_iv("a", 0)])


def test_bad_compound_rejected():
    with pytest.raises(R.RuntimeRequestError):
        R.build_plan(_state(), target_driver_ids=["a"],
                     interventions=[_iv("a", 2, "WET")])


def test_bad_target_rejected():
    with pytest.raises(R.RuntimeRequestError):
        R.build_plan(_state(), target_driver_ids=["zzz"],
                     interventions=[_iv("zzz", 2)])


def test_conflicting_targets_rejected():
    state = _state()
    with pytest.raises(R.RuntimeRequestError):  # duplicates
        R.build_plan(state, target_driver_ids=["a", "a"],
                     interventions=[_iv("a", 2)])
    with pytest.raises(R.RuntimeRequestError):  # intervention off-target
        R.build_plan(state, target_driver_ids=["a"],
                     interventions=[_iv("b", 2)])
    with pytest.raises(R.RuntimeRequestError):  # target without events
        R.build_plan(state, target_driver_ids=["a", "b"],
                     interventions=[_iv("a", 2)])


def test_rejected_kinds_rejected():
    state = _state()
    for kind in ("WEATHER", "SAFETY_CAR", "VSC", "RED_FLAG", "RETIREMENT",
                 "RELIABILITY", "ARBITRARY_POSITION", "ARBITRARY_GAP",
                 "ARBITRARY_PACE", "ARBITRARY_TYRE_AGE", "UNDERCUT",
                 "OVERCUT"):
        with pytest.raises(R.RuntimeRequestError):
            R.reject_kind(kind)
        raw = _iv("a", 2)
        raw["kind"] = kind
        with pytest.raises(R.RuntimeRequestError):
            R.build_plan(state, target_driver_ids=["a"],
                         interventions=[raw])
    R.reject_kind("PIT_IN_N_LAPS")


def test_poison_fields_rejected():
    state = _state()
    for poison in ("observed_future_pit_lap", "future_weather",
                   "future_safety_car", "future_finish",
                   "historical_outcome", "recommendation_score",
                   "future_result", "winner", "future", "result",
                   "simulation_count", "master_seed", "seed", "live",
                   "mode", "num_simulations"):
        raw = _iv("a", 2)
        raw[poison] = 1
        with pytest.raises(R.RuntimeRequestError):
            R.build_plan(state, target_driver_ids=["a"],
                         interventions=[raw])


def test_cost_bounds():
    state = _state()
    with pytest.raises(R.RuntimeRequestError):
        R.build_plan(state, target_driver_ids=["a"],
                     interventions=[_iv("a", n + 1) for n in range(9)])


def test_horizon_violation_is_unsupported_not_coerced():
    state = _state()  # remaining=11 -> N=11 exceeds (N <= remaining-1)
    plan = R.build_plan(state, target_driver_ids=["a"],
                        interventions=[_iv("a", 11)])
    eligible, level, reason, _ = R.check_request_eligibility(state, plan)
    assert eligible is False
    assert level == "INTERVENTION"
    assert reason == "INVALID_TRIGGER"


def test_rival_conflict_is_unsupported():
    state = _state()
    plan = _plan(state)
    eligible, level, reason, _ = R.check_request_eligibility(
        state, plan, rival_driver_id="a")
    assert eligible is False
    assert level == "COMPARISON"


# ===========================================================================
# Canonicalization (order must not affect identity/cache/science).
# ===========================================================================

def test_target_permutation_invariant():
    state = pit_field(3, scheduled=12, start_lap=1, age=1)
    p1 = R.build_plan(state, target_driver_ids=["a", "c"],
                      interventions=[_iv("a", 2), _iv("c", 4, "HARD")])
    p2 = R.build_plan(state, target_driver_ids=["c", "a"],
                      interventions=[_iv("c", 4, "HARD"), _iv("a", 2)])
    assert p1.identity() == p2.identity()
    assert p1.target_driver_ids == p2.target_driver_ids == ("a", "c")


def test_duplicate_interventions_deduplicated():
    state = _state()
    plan = R.build_plan(state, target_driver_ids=["a"],
                        interventions=[_iv("a", 2), _iv("a", 2)])
    assert len(plan.interventions) == 1


def test_production_locked():
    assert R.PRODUCTION_SIMULATION_COUNT == 5000
    assert R.PRODUCTION_MASTER_SEED == 20240101
    with pytest.raises(R.CacheInvalidError):
        R.build_cache_key(
            state_identity="x" * 64, comparison_form="REFERENCE_VS_PLAN",
            base_identity="ref", alternative_identity="y" * 64,
            primary_target_driver_id="a", rival_driver_id=None,
            parameter_identity="p" * 64, config_identity="c" * 64,
            simulation_count=100, master_seed=SEED)
    with pytest.raises(R.CacheInvalidError):
        R.build_cache_key(
            state_identity="x" * 64, comparison_form="REFERENCE_VS_PLAN",
            base_identity="ref", alternative_identity="y" * 64,
            primary_target_driver_id="a", rival_driver_id=None,
            parameter_identity="p" * 64, config_identity="c" * 64,
            simulation_count=COUNT, master_seed=1)


# ===========================================================================
# Direct engine vs runtime adapter parity (no reorientation).
# ===========================================================================

def _ids(state):
    from raceintel.simulation.state import canonical_sha256 as _h
    return {"p": "p" * 64, "c": "c" * 64}


def test_adapter_matches_direct_engine():
    state = _state()
    plan = _plan(state)
    direct = E.compare_reference_vs_plan(
        state=state, parameters=_params(), config=_cfg(),
        assumptions=Assumptions(), plan=plan)
    via_adapter = R.run_reference_vs_plan(
        state=state, parameters=_params(), config=_cfg(),
        assumptions=Assumptions(), plan=plan)
    assert R.result_to_dict(via_adapter) == direct.to_dict()


def test_position_gain_orientation_preserved():
    assert C.position_gain(5, 2) == 3
    assert C.position_gain(5, 5) == 0
    assert C.position_gain(5, 8) == -3
    state = _state()
    res = _run(state, _plan(state))
    d = res.to_dict()
    base = d["base_aggregate"]["expected_position_gain"]
    alt = d["alternative_aggregate"]["expected_position_gain"]
    point = d["deltas"]["delta_position_gain_loss"]["point_estimate"]
    assert point == pytest.approx(alt - base)  # ALT - BASE, no flip


def test_expected_finish_orientation_preserved():
    state = _state()
    d = _run(state, _plan(state)).to_dict()
    base = d["base_aggregate"]["expected_finish"]
    alt = d["alternative_aggregate"]["expected_finish"]
    point = d["deltas"]["delta_expected_finish"]["point_estimate"]
    assert point == pytest.approx(base - alt)  # BASE - ALT (lower better)


def test_probability_orientation_preserved():
    state = _state()
    d = _run(state, _plan(state)).to_dict()
    for metric in ("delta_win_frequency", "delta_podium_frequency"):
        vals = d["deltas"][metric]
        base_m = metric.replace("delta_", "")
        assert vals["point_estimate"] == pytest.approx(
            d["alternative_aggregate"][base_m]
            - d["base_aggregate"][base_m])  # ALT - BASE


def test_pit_count_descriptive():
    state = _state()
    d = _run(state, _plan(state)).to_dict()
    assert d["base_aggregate"]["expected_pit_count"] >= 0.0
    assert d["alternative_aggregate"]["expected_pit_count"] >= 0.0
    blob = json.dumps(d)
    for token in ("optimal_pit", "best_pit", "pit_rank", "pit_score"):
        assert token not in blob


def test_pair_accounting_and_lifecycle_preserved():
    state = _state()
    d = _run(state, _plan(state)).to_dict()
    assert (d["complete_pairs"] + d["excluded_pairs"]
            == d["requested_pairs"] == COUNT)
    summary = R.summarize_lifecycle(d["schedule_outcomes"])
    assert set(summary) == {"base", "alternative"}
    allowed = {"PLANNED", "ELIGIBLE", "EXECUTED", "INERT", "SUPERSEDED",
               "CANCELLED", "TERMINAL", "INVALID"}
    seen = set()
    for arm_counts in summary.values():
        seen.update(arm_counts)
    assert seen <= allowed
    total = sum(summary["alternative"].values())
    assert total == COUNT  # one event x COUNT sims


def test_unsupported_metrics_empty():
    out = E.unsupported_for(level="STATE", reason_code="WET",
                            human_reason="wet", state=_state())
    assert out["supported"] is False
    assert out["metrics"] == {}


# ===========================================================================
# Temporal safety / separation.
# ===========================================================================

def test_temporal_poison_identical(monkeypatch):
    import pandas as pd
    def _blocked(*a, **k):
        raise AssertionError("historical read attempted")
    monkeypatch.setattr(pd, "read_parquet", _blocked)
    state = _state()
    d1 = _run(state, _plan(state)).to_dict()
    d2 = _run(state, _plan(state)).to_dict()
    assert d1 == d2


def test_no_d_evaluation_or_v35_dependency():
    import ast
    import raceintel.counterfactual.runtime as rt
    tree = ast.parse(Path(rt.__file__).read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    blob = "\n".join(sorted(imported))
    for token in ("v3_7d", "evaluation", "v3_5", "frontend"):
        assert token not in blob, blob
    assert "v3_7d" not in set(sys.modules)


def test_no_forbidden_claims_in_runtime():
    # Forbidden claims are allowed only as explicit prohibitions /
    # methodological qualifications ("no/never/not ...").
    import re
    import raceintel.counterfactual.runtime as rt
    text = Path(rt.__file__).read_text().lower()
    for phrase in ("optimal strategy", "recommended", "should pit",
                   "would have won", "guaranteed outcome",
                   "causal treatment effect", "best_plan",
                   "recommended_plan", "optimal_action"):
        for match in re.finditer(re.escape(phrase), text):
            window = text[max(0, match.start() - 120):match.start()]
            assert re.search(
                r"\b(no|never|not|nothing|without|against|forbids?)\b",
                window), \
                f"unqualified claim {phrase!r} near ...{window[-60:]}..."

