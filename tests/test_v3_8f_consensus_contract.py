"""V3.8F product-contract tests: provenance, semantics, prohibitions, card.

No MC2 execution, no model inference, no ground truth. Fixture-backed and
synthetic providers only.
"""

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from raceintel.consensus import contracts as C
from raceintel.consensus import metrics as M
from raceintel.consensus import product as P

F = ROOT / "results" / "v3" / "v3_8f"


def _load(name):
    return json.loads((F / name).read_text())


def _contract():
    return _load("product_contract.json")


# --- provenance ---

def test_abc_identities_exact():
    c = _contract()["provenance"]
    assert c["a_contract"] == \
        "d0b8785a01347580125b38b311984c793c012352ce3ff175cfa3504379b9a67b"
    assert c["b_contract"] == \
        "d212803f7ed7e8a8563abdd5b7686326e7094d810f415fa1468117541dfbfde7"
    assert c["c_contract"] == \
        "07cf1ddd9708eaea2280b1d46492d972234f68c77cf3a59cbf412f638e3a74a8"
    assert c["d_protocol"] == \
        "9cbe85de7c8f0553a098a9a03d016beed80159c785b566c312502d3bf10f2ed1"


def test_corrected_d_identities_no_superseded_fallback():
    c = _contract()["provenance"]
    assert c["d_card_corrected"] == \
        "67f97c185ca8cc687b59b376bc5a48776e9290d6463a05653fa1a6e18a298985"
    assert c["d_gate_corrected"] == "FUSION_RESEARCH_WARRANTED"
    blob = json.dumps(_contract())
    assert "523898b3" not in blob  # original D card never referenced
    assert "-0.15065782073566983" not in blob  # superseded bootstrap absent


def test_corrected_e_identities_negative_gate_honored():
    c = _contract()["provenance"]
    assert c["e_card_corrected"] == \
        "ec6578de410f1ec8f6975e1cf4a2575aa4984967804b22a0b583fe2740948357"
    assert c["e_gate"] == "FUSION_IMPROVEMENT_NOT_SUPPORTED"
    assert c["e_protocol"] == \
        "dbe6a565d5a6fa688dbb8e0b3a1be05bad71457777cd2e312f9c164219b128dd"


# --- source registry / exclusions ---

def test_exact_source_registry():
    assert _contract()["admitted_runtime_sources"] == [
        "V3_1B_LOGISTIC", "MC2_E"]
    assert list(P.PRODUCT_SOURCES) == [
        C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E]
    assert P.PRODUCT_TARGET == C.Target.WIN


def test_v34_excluded():
    blob = json.dumps(_contract())
    assert "V3_4" in blob  # named only on the exclusion list
    assert _contract()["excluded_sources"]
    for mod in ("raceintel/consensus/product.py",
                "api/v2_consensus_service.py",
                "api/v2_consensus_routes.py",
                "api/v2_consensus_schemas.py"):
        text = (ROOT / mod).read_text()
        assert "V3_4" not in text and "v3_4" not in text


def test_v35_p_win_excluded_as_vote():
    assert any("V3_5_P_WIN" in s
               for s in _contract()["excluded_sources"])
    for mod in ("raceintel/consensus/product.py",
                "api/v2_consensus_service.py"):
        text = (ROOT / mod).read_text()
        assert "p_v35" not in text and "V3_5_P_WIN" not in text


# --- probability semantics ---

def test_probability_families_distinct():
    fams = _contract()["probability_families"]
    assert "INDEPENDENT_BINARY" in fams["V3_1B_LOGISTIC"]
    assert "MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY" in fams["MC2_E"]
    assert C.SOURCE_FAMILIES[C.SourceId.V3_1B_LOGISTIC] == \
        C.SourceFamily.INDEPENDENT_BINARY
    assert C.SOURCE_FAMILIES[C.SourceId.MC2_E] == \
        C.SourceFamily.MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY


def test_logistic_passthrough_no_normalization():
    probs = {"a": 0.6, "b": 0.5, "c": 0.4}  # sums to 1.5: must survive
    sim = {"a": 0.5, "b": 0.3, "c": 0.2}
    out = P.compose(race_id="2022-r03-R", lap_number=2,
                    state_time_s=None, stage="EARLY", season=2022,
                    model_probs=dict(probs), simulation_probs=dict(sim),
                    valid_trials=5000)
    got = {d["driver_id"]: d["p_model"]
           for d in out["disagreement"]["drivers"]}
    assert got == probs


def test_mc2_passthrough_no_renormalization():
    probs = {"a": 0.7, "b": 0.2, "c": 0.1}
    sim = {"a": 0.0, "b": 0.0, "c": 1.0}
    out = P.compose(race_id="2022-r03-R", lap_number=2,
                    state_time_s=None, stage="EARLY", season=2022,
                    model_probs=dict(probs), simulation_probs=dict(sim),
                    valid_trials=5000)
    got = {d["driver_id"]: d["p_simulation"]
           for d in out["disagreement"]["drivers"]}
    assert got == sim


def test_supported_mc2_zero_remains_numeric_zero():
    out = P.compose(race_id="2022-r03-R", lap_number=2,
                    state_time_s=None, stage="EARLY", season=2022,
                    model_probs={"a": 0.02, "b": 0.01},
                    simulation_probs={"a": 0.0, "b": 0.5},
                    valid_trials=5000)
    row = next(d for d in out["disagreement"]["drivers"]
               if d["driver_id"] == "a")
    assert row["p_simulation"] == 0.0
    assert isinstance(row["p_simulation"], float)


def test_unsupported_remains_unavailable_not_zero():
    avail = P.assess_availability(
        season=2022, model_status=C.SupportStatus.AVAILABLE,
        simulation_status=C.SupportStatus.UNAVAILABLE,
        simulation_reason=C.ReasonCode.MC2_STATE_INELIGIBLE)
    assert avail["simulation"] == "UNAVAILABLE"
    assert avail["comparison"] == "NOT_COMPARABLE"
    # composer only sees aligned natives: no null-filling happens here
    out = P.compose(race_id="2022-r03-R", lap_number=2,
                    state_time_s=None, stage="EARLY", season=2022,
                    model_probs={"a": 0.02, "b": 0.01},
                    simulation_probs={"a": 0.0},  # b unsupported: absent
                    valid_trials=5000)
    assert [d["driver_id"] for d in out["disagreement"]["drivers"]] == ["a"]


# --- disagreement semantics ---

def test_signed_gap_sign():
    out = P.compose(race_id="2022-r03-R", lap_number=2,
                    state_time_s=None, stage="EARLY", season=2022,
                    model_probs={"a": 0.2, "b": 0.1},
                    simulation_probs={"a": 0.8, "b": 0.05},
                    valid_trials=5000)
    rows = {d["driver_id"]: d for d in out["disagreement"]["drivers"]}
    assert abs(rows["a"]["signed_gap"] - 0.6) < 1e-12  # simulation_minus_model
    assert abs(rows["b"]["signed_gap"] - (-0.05)) < 1e-12
    assert abs(rows["a"]["absolute_gap"] - 0.6) < 1e-12
    assert out["disagreement"]["signed_gap_definition"] == \
        "simulation_minus_model"


def test_rank_tie_semantics_average_no_break():
    out = P.compose(race_id="2022-r03-R", lap_number=2,
                    state_time_s=None, stage="EARLY", season=2022,
                    model_probs={"a": 0.5, "b": 0.5, "c": 0.1},
                    simulation_probs={"a": 0.4, "b": 0.4, "c": 0.2},
                    valid_trials=5000)
    assert out["disagreement"]["rank"]["model_rank"] == \
        {"a": 1.5, "b": 1.5, "c": 3.0}
    assert out["disagreement"]["leader"]["model_leader"] == ["a", "b"]
    assert out["disagreement"]["leader"]["exact_leader_match"] is True


def test_leader_mismatch_and_displacement():
    out = P.compose(race_id="2022-r03-R", lap_number=2,
                    state_time_s=None, stage="EARLY", season=2022,
                    model_probs={"a": 0.7, "b": 0.2, "c": 0.1},
                    simulation_probs={"a": 0.1, "b": 0.8, "c": 0.1},
                    valid_trials=5000)
    leader = out["disagreement"]["leader"]
    assert leader["model_leader"] == ["a"]
    assert leader["simulation_leader"] == ["b"]
    assert leader["exact_leader_match"] is False
    disp = out["disagreement"]["rank"]["rank_displacement"]
    assert disp["b"] == 1.0 - 2.0  # sim rank 1 minus model rank 2


def test_topk_tie_boundary_and_note():
    out = P.compose(race_id="2022-r03-R", lap_number=2,
                    state_time_s=None, stage="EARLY", season=2022,
                    model_probs={"a": 0.5, "b": 0.3, "c": 0.3, "d": 0.1},
                    simulation_probs={"a": 0.4, "b": 0.4, "c": 0.1,
                                      "d": 0.1},
                    valid_trials=5000, top_k=2)
    top = out["disagreement"]["top_k"]["top_2"]
    assert top["model"] == ["a", "b", "c"]  # boundary tie admitted
    assert "NOT P(finish<=k)" in top["note"]


def test_mc_se_wilson_parity_with_c():
    out = P.compose(race_id="2022-r03-R", lap_number=2,
                    state_time_s=None, stage="EARLY", season=2022,
                    model_probs={"a": 0.2, "b": 0.1},
                    simulation_probs={"a": 0.8, "b": 0.0},
                    valid_trials=1000)
    rows = {d["driver_id"]: d for d in out["disagreement"]["drivers"]}
    assert rows["a"]["sampling"]["sampling_se"] == M.mc_sampling_se(0.8, 1000)  # noqa: E501
    assert rows["a"]["sampling"]["wilson_95"] == list(
        M.wilson_interval(0.8, 1000))
    assert rows["a"]["sampling"]["label"] == "FINITE_MC_SAMPLING_CONTEXT_ONLY"  # noqa: E501
    blob = json.dumps(out)
    assert "real-world" not in blob and "confidence" not in blob.lower()


def test_permutation_invariance():
    kw = dict(race_id="2022-r03-R", lap_number=2, state_time_s=None,
              stage="EARLY", season=2022, valid_trials=5000)
    m1 = {"a": 0.5, "b": 0.3, "c": 0.2}
    s1 = {"a": 0.4, "b": 0.4, "c": 0.2}
    m2 = {"c": 0.2, "a": 0.5, "b": 0.3}
    s2 = {"c": 0.2, "b": 0.4, "a": 0.4}
    o1 = P.compose(model_probs=m1, simulation_probs=s1, **kw)
    o2 = P.compose(model_probs=m2, simulation_probs=s2, **kw)
    assert o1 == o2


# --- prohibitions ---

def test_no_fusion_fields_or_paths():
    import re
    for mod in ("raceintel/consensus/product.py",
                "api/v2_consensus_service.py",
                "api/v2_consensus_routes.py",
                "api/v2_consensus_schemas.py"):
        text = (ROOT / mod).read_text().lower()
        for token in ("blend", "weighted_average", "ensemble",
                      "consensus_probability", "combined_probability",
                      "recommended_probability", "consensus_score",
                      "confidence_score"):
            assert token not in text, (mod, token)
        # word-boundary: catches fused_probability / fused paths but not
        # ordinary prose such as "refused"
        assert not re.search(r"\bfused\b", text), mod
    # 'alpha' only as a substring check with boundaries
    import re as _re
    for mod in ("raceintel/consensus/product.py",
                "api/v2_consensus_service.py"):
        text = (ROOT / mod).read_text()
        assert not _re.search(r"\balpha\b", text), mod


def test_no_source_winner_fields():
    for mod in ("raceintel/consensus/product.py",
                "api/v2_consensus_service.py",
                "api/v2_consensus_routes.py",
                "api/v2_consensus_schemas.py"):
        text = (ROOT / mod).read_text()
        for token in ("preferred_source", "winning_source",
                      "recommendation", "trust_model", "trust_simulation",
                      "source_quality_score"):
            assert token not in text, (mod, token)
    for name in ("product_contract.json",):
        blob = json.dumps(_load(name))
        for token in ("preferred_source", "winning_source",
                      "trust_model", "trust_simulation"):
            assert token not in blob or "forbidden" in blob.lower()


def test_no_public_science_controls():
    for mod in ("api/v2_consensus_service.py",
                "api/v2_consensus_routes.py",
                "api/v2_consensus_schemas.py"):
        text = (ROOT / mod).read_text()
        assert "master_seed" not in text
        assert "simulation_count" not in text
        assert "variance" not in text.lower()


def test_no_frontend_and_no_upward_science_dependency():
    # F runtime itself introduces no frontend surface: none of the F
    # modules live under frontend/ (G owns the UI layer separately).
    for mod in ("raceintel/consensus/product.py",
                "api/v2_consensus_service.py",
                "api/v2_consensus_routes.py",
                "api/v2_consensus_schemas.py"):
        assert not mod.startswith("frontend/")
    for mod in ("raceintel/consensus/product.py",):
        text = (ROOT / mod).read_text()
        assert "from api" not in text and "import api" not in text


def test_pathology_all_zero():
    path = _load("product_validation.json")["pathology"]
    assert set(path) == {f"F-P{i}" for i in range(1, 25)}
    assert all(v == 0 for v in path.values())


def test_product_card_identity_recomputes():
    c = _load("product_card.json")
    identity = c.pop("card_identity")
    blob = json.dumps(c, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(blob).hexdigest() == identity
