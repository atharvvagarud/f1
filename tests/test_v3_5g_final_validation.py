"""V3.5G final validation tests. No fitting, no 2025 regeneration, no reselection."""
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CARD = ROOT / "results/v3/v3_5_final_scientific_card.json"
FREEZE = ROOT / "results/v3/v3_5_freeze.json"
PROV = ROOT / "results/v3/v3_5g/provenance_audit.json"

A_ID = "15ca7c17146062edb5196a5de244fadd81d38562b2ca5714e58a21d4efb5efab"
B_ID = "e9ac34e5792a5aabba9038094a231a4a94789b481178739e46ece72457cc5289"
C_ID = "9dfee182215d6a56e4f19e2418b051883e9c75876418a6f4c92a05d799c7603a"
D_ID = "8d82448ea5888beb6dd8f54c35ebb08ba40c58bd66b652bab6f0d39dfdf78ba4"
E_PROTO = "4adf3da33b86e734e7b663c6702c64f9377c08ac4318fb5439eebd439aec38e6"
E_RECIPE = "b1d8ce5e43059477a5e57fe5b4d301cbd7b9975864d1ad964d613d1124044c09"
F_MAN = "eab0da304dbb46b6de58ccb00c676e6a64761cf6473cc1361659ff8658b3d8e1"
F_REC = "a94ee34d63e843be37b41737fba4b2d141cf57409e6960094bf158c42921a1b3"
FEAT = "e054c6fb08c0832970165bcfc0e84f54b70787491af1d545b96a13977fc4c89e"


def card():
    return json.loads(CARD.read_text())


def freeze():
    return json.loads(FREEZE.read_text())


def canon(doc, exc):
    return hashlib.sha256(json.dumps(
        {k: v for k, v in doc.items() if k != exc},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_abcd_identities_exact():
    assert card()["stage_identities"]["A"] == A_ID
    assert card()["stage_identities"]["B"] == B_ID
    assert card()["stage_identities"]["C"] == C_ID
    assert card()["stage_identities"]["D"] == D_ID
    assert card()["stage_identities"]["E_protocol"] == E_PROTO
    assert card()["stage_identities"]["E_recipe"] == E_RECIPE
    assert card()["stage_identities"]["F_manifest"] == F_MAN
    assert card()["stage_identities"]["F_record"] == F_REC


def test_provenance_audit_verdict():
    p = json.loads(PROV.read_text())
    assert p["verdict"] == "PROVENANCE_MATCH"
    for k in ("a_contract", "b_dataset", "c_harness", "d_protocol",
              "e_protocol", "e_recipe", "f_manifest", "f_record",
              "feature_hash", "logistic_pred", "xgb_pred", "projection"):
        assert p["recomputed"][k + "_match"] is True


def test_stage_ledger_2025_contact():
    p = json.loads(PROV.read_text())
    for s in ("A", "B", "C", "D", "E"):
        assert p["2025_contact"][s] == "NONE"
        assert p["stage_ledger"][s]["verdict"] == "COMPLETE"
    assert p["2025_contact"]["F"] == "EVALUATION_ONLY"


def test_card_schema_and_identity_deterministic():
    c = card()
    assert c["schema_version"] == "v3.5-final-scientific-card-v1"
    assert canon(c, "scientific_card_identity") == \
        c["scientific_card_identity"]


def test_task_thresholds_features_semantics():
    c = card()
    assert c["task"] == "ordered_cumulative_finish_thresholds"
    assert c["thresholds"] == [1, 3, 5, 10]
    assert c["feature_identity"] == {
        "arm": "ALL_84_PLUS_V3_1_DYNAMICS_CORE", "hash": FEAT, "n": 110}
    assert c["probability_semantics"].startswith("PER_DRIVER_MARGINAL")


def test_champion_candidate_serving():
    c = card()
    assert c["champion"] == "LOGISTIC_CONTROL"
    assert c["research_candidate"]["status"] == \
        "NONLINEAR_RESEARCH_CANDIDATE"
    assert c["serving"] == "NONE"


def test_disposition_mixed():
    c = card()
    assert c["final_disposition"] == "OUTCOME_XGB_MIXED_OUT_OF_TIME"
    assert c["transfer_classification"] == "MIXED_TRANSFER"


def test_primary_metrics_exact():
    e = card()["evaluation_2025"]
    assert e["logistic_projected_primary"] == 0.2050270403404582
    assert e["xgb_raw_primary"] == 0.2014019593892697
    assert e["xgb_calibrated_primary"] == 0.2018361232732994
    assert e["xgb_projected_primary"] == 0.2016424811805443
    assert e["primary_delta_xgb_minus_logistic"] == \
        -0.0033845591599139246


def test_threshold_metrics_exact():
    t = card()["evaluation_2025"]["threshold_results"]
    assert t["is_top1"]["delta"] == pytest.approx(0.0038032263712361736)
    assert t["is_top3"]["delta"] == pytest.approx(0.0015192383310356494)
    assert t["is_top5"]["delta"] == pytest.approx(-0.00826220067417590, abs=1e-12)
    assert t["is_top10"]["delta"] == pytest.approx(-0.010598500667751476)
    assert t["is_top1"]["verdict"] == "REGRESSES"
    assert t["is_top3"]["verdict"] == "REGRESSES"
    assert t["is_top5"]["verdict"] == "IMPROVES"
    assert t["is_top10"]["verdict"] == "IMPROVES"


def test_top1_weakness_present():
    a = card()["evaluation_2025"]["top1_audit"]
    assert a["verdict"] == "WEAKNESS_PERSISTS"
    assert (a["improved"], a["worsened"]) == (10, 14)


def test_bootstrap_spans_zero_and_races():
    e = card()["evaluation_2025"]
    assert e["bootstrap"]["ci_lo"] < 0 < e["bootstrap"]["ci_hi"]
    assert e["bootstrap"]["replicates"] == 2000
    assert e["bootstrap"]["seed"] == 42
    assert (e["race_counts"]["improved"], e["race_counts"]["worsened"]) == \
        (15, 9)


def test_calibration_regression_present():
    c = card()["calibration"]
    assert c["2025_transfer"] == "CALIBRATION_REGRESSES"
    assert c["ll_delta_top5_cal_minus_raw"] > 0
    assert c["frozen_before_2025"] is True


def test_stage_behavior():
    s = card()["evaluation_2025"]["stage_results"]
    assert s["LATE"] < 0
    assert s["EARLY"] > 0
    assert s["MID"] > 0


def test_projection_final_violations_zero():
    assert card()["coherence"]["final_violation_count"] == 0
    assert card()["coherence"]["final_violation_rate"] == 0.0


def test_v31b_non_replacement_and_mc2_separation():
    c = card()
    flat = " ".join(c["v31b_relationship"].split())
    assert "is NOT replaced by V3.5" in flat
    assert "V3.1B remains the established winner-prediction lineage" in flat
    assert c["mc2_relationship"].startswith("SEPARATE")


def test_no_blend_stack_reselection():
    blob = json.dumps(card(), sort_keys=True).lower()
    assert "blend" not in blob or "no blend" in blob or \
        "blending" in blob
    assert card()["transformation"] == "RAW -> CALIBRATION -> PAVA"


def test_2025_terminology_conservative():
    assert card()["evaluation_2025"]["terminology"] == \
        "PREVIOUSLY REVEALED OUT-OF-TIME OUTCOME EVALUATION"


def test_freeze_record_deterministic():
    f = freeze()
    assert f["schema_version"] == "v3.5-freeze-v1"
    assert f["tag_name"] == "v3.5-outcome-distribution"
    assert f["push_status"] == "NOT_PUSHED"
    assert "commit_sha" not in f
    assert canon(f, "freeze_identity") == f["freeze_identity"]
    assert f["scientific_card_identity"] == \
        card()["scientific_card_identity"]
