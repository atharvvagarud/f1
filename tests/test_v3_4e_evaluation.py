"""V3.4E out-of-time evaluation tests. No fitting, no reselection."""
import hashlib
import json
from pathlib import Path

import pandas as pd

OUT = Path("results/v3/v3_4e")
PRED = Path("data/v3/v3_4e/ensemble_predictions_2025.parquet")
A_SHA = "d6b12074db9895844c28c05c78baf56c113d63c33d685c5913c92ebb5036b352"
B_SHA = "64ca2d2911e63b1487334ca72fc024f47d59868f168b60d7d391d31df82b5b26"
P_SHA = "d0af402c550879dac7c2f85761d4d4a1f433bb2a2e4dba1bfd000282b8a37891"
C_SHA = "98b315970408000936aa9970224234436e9cd13c2573a823fec859650b41ed87"
R_SHA = "d715dcfb19db35f01cbf369bbcba52994ff99d366364f607779d3ec07539af68"
M_SHA = "9a6752b6cff97a6bf9d080dab5ac56bfaf1336e4503383ba4d14366000d368a1"


def load(name, directory=OUT):
    return json.loads((directory / name).read_text())


def canon(doc, skip):
    return json.dumps({k: v for k, v in doc.items() if k != skip},
                      sort_keys=True, separators=(",", ":"))


def test_a_identity():
    a = load("experiment_contract.json", Path("results/v3/v3_4a"))
    assert hashlib.sha256(canon(a, "contract_hash").encode()).hexdigest() \
        == a["contract_hash"] == A_SHA


def test_b_identity():
    b = load("preregistration.json", Path("results/v3/v3_4b"))
    assert hashlib.sha256(
        canon(b, "preregistration_identity").encode()).hexdigest() == \
        b["preregistration_identity"] == B_SHA


def test_c_identity():
    c = load("selected_development_candidate.json", Path("results/v3/v3_4c"))
    assert hashlib.sha256(
        canon(c, "candidate_identity").encode()).hexdigest() == \
        c["candidate_identity"] == C_SHA


def test_d_recipe_identity():
    r = load("final_ensemble_recipe.json", Path("results/v3/v3_4d"))
    assert hashlib.sha256(canon(r, "recipe_identity").encode()
                          ).hexdigest() == r["recipe_identity"] == R_SHA


def test_e_manifest_identity():
    m = load("v3_4e_execution_manifest.json", Path("results/v3/v3_4d"))
    assert hashlib.sha256(canon(m, "manifest_identity").encode()
                          ).hexdigest() == m["manifest_identity"] == M_SHA


def test_execution_record_immutable():
    rec = load("execution_record.json")
    assert hashlib.sha256(canon(rec, "record_identity").encode()
                          ).hexdigest() == rec["record_identity"]
    assert rec["d_recipe_identity"] == R_SHA
    assert rec["e_manifest_identity"] == M_SHA


def test_exact_allowed_input_sources():
    rec = load("execution_record.json")
    assert rec["allowed_inputs"]["logistic_2025"]["path"] == \
        "data/v3/v3_1d/pred_final_ALL_84_PLUS_V3_1_DYNAMICS_CORE_2025.parquet"
    assert rec["allowed_inputs"]["xgboost_2025"]["path"] == \
        "data/v3/v3_3e/pred_xgb_final_2025.parquet"


def test_input_hashes():
    audit = load("input_alignment_audit.json")
    assert audit["xgboost_sha256"] == \
        "71b9bb807a8a845ec787109a5671d7014cc49b6873a674a50a6b434053b3e5d3"
    assert len(audit["logistic_sha256"]) == 64


def test_season_exactly_2025():
    audit = load("input_alignment_audit.json")
    assert audit["season"] == [2025]


def test_26692_rows():
    assert load("input_alignment_audit.json")["n_states"] == 26692
    assert len(pd.read_parquet(PRED)) == 26692


def test_24_races():
    assert load("input_alignment_audit.json")["n_races"] == 24
    assert pd.read_parquet(PRED)["race_id"].nunique() == 24


def test_identity_alignment():
    audit = load("input_alignment_audit.json")
    assert audit["identity_sets_equal"] is True
    assert audit["join"] == "state_id only"
    assert pd.read_parquet(PRED)["state_id"].is_unique


def test_row_order_permutation_invariance():
    assert load("prediction_integrity.json")["permutation_invariant"] is True


def test_base_logistic_reproduction():
    rep = load("base_reproduction.json")
    assert rep["match"] is True
    assert abs(rep["logistic_ll"] - 0.0634166678) < 1e-9


def test_base_xgb_reproduction():
    rep = load("base_reproduction.json")
    assert abs(rep["xgboost_ll"] - 0.0672136469) < 1e-9
    assert abs(rep["delta"] - 0.0037969791) < 1e-9


def test_recipe_weight_exactly_02():
    r = load("final_ensemble_recipe.json", Path("results/v3/v3_4d"))
    assert r["xgboost_weight"] == 0.2
    assert r["logistic_weight"] == 0.8


def test_no_alternate_weight():
    audit = load("no_reselection_audit.json")
    assert audit["verdict"] == "NO-RESELECTION CONFIRMED"
    assert audit["only_w02_exists"] is True


def test_prediction_artifact_hash():
    ident = load("prediction_identity.json")
    assert hashlib.sha256(PRED.read_bytes()).hexdigest() == ident["sha256"]
    assert ident["recipe_identity"] == R_SHA


def test_prediction_artifact_immutability():
    ident = load("prediction_identity.json")
    assert ident["note"].startswith("immutable")
    assert ident["n_rows"] == 26692


def test_deterministic_prediction_reproduction():
    assert load("prediction_integrity.json")[
        "deterministic_recompute"] is True


def test_raw_semantics():
    pq = load("probability_quality.json")
    assert pq["raw"] is True


def test_independent_binary():
    r = load("final_ensemble_recipe.json", Path("results/v3/v3_4d"))
    assert r["probability_semantics"] == "INDEPENDENT_BINARY"


def test_no_normalization():
    pq = load("probability_quality.json")
    assert pq["field_normalized"] is False


def test_no_calibration():
    r = load("final_ensemble_recipe.json", Path("results/v3/v3_4d"))
    assert r["calibration"] == "NONE"


def test_race_macro_primary():
    pm = load("primary_metrics.json")
    assert pm["ensemble_minus_logistic"] < 0
    assert abs(pm["ensemble_ll"] - 0.0626596199) < 1e-9


def test_race_unit_bootstrap():
    boot = load("race_bootstrap.json")
    assert boot["replicates"] == 2000
    assert boot["seed"] == 42


def test_b2000():
    assert load("race_bootstrap.json")["replicates"] == 2000


def test_seed42():
    assert load("race_bootstrap.json")["seed"] == 42


def test_stage_partition():
    st = load("stage_results.json")
    assert set(st) == {"EARLY", "MID", "LATE"}
    assert all(st[s]["n_states"] > 0 for s in st)


def test_secondary_metrics():
    sm = load("secondary_metrics.json")
    assert set(sm) == {"logistic", "xgboost", "ensemble"}
    assert sm["ensemble"]["brier"] < sm["logistic"]["brier"]


def test_disposition_enum():
    disp = load("disposition.json")["disposition"]
    assert disp in ("ENSEMBLE_GENERALIZES", "ENSEMBLE_MIXED_OUT_OF_TIME",
                    "ENSEMBLE_FAILS_TO_GENERALIZE")


def test_no_reselection():
    assert load("no_reselection_audit.json")["verdict"] == \
        "NO-RESELECTION CONFIRMED"


def test_serving_promotion_none():
    assert load("disposition.json")["serving_promotion"] == "NONE"


def test_no_final_v34_freeze_tag_commit_yet():
    import subprocess
    tags = subprocess.run(["git", "tag", "-l", "v3.4*"],
                          capture_output=True, text=True).stdout
    assert "v3.4" not in tags
