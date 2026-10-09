"""V3.5F out-of-time evaluation tests. Frozen recipe; no reselection."""
import hashlib
import json
from pathlib import Path

import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results/v3/v3_5f"
EXEC_ID = "a94ee34d63e843be37b41737fba4b2d141cf57409e6960094bf158c42921a1b3"
RECIPE_ID = "b1d8ce5e43059477a5e57fe5b4d301cbd7b9975864d1ad964d613d1124044c09"
MANIFEST_ID = "eab0da304dbb46b6de58ccb00c676e6a64761cf6473cc1361659ff8658b3d8e1"
NAMES = ["is_top1", "is_top3", "is_top5", "is_top10"]


def load(name):
    return json.loads((RES / name).read_text())


def blob(payload, exc):
    return hashlib.sha256(json.dumps(
        {k: v for k, v in payload.items() if k != exc},
        sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_abcde_identities_exact():
    s = json.loads((ROOT / "results/v3/v3_5e_refinement.json").read_text())
    assert s["a_identity"] == \
        "15ca7c17146062edb5196a5de244fadd81d38562b2ca5714e58a21d4efb5efab"
    assert s["b_identity"] == \
        "e9ac34e5792a5aabba9038094a231a4a94789b481178739e46ece72457cc5289"
    assert s["c_identity"] == \
        "9dfee182215d6a56e4f19e2418b051883e9c75876418a6f4c92a05d799c7603a"
    assert s["d_protocol_identity"] == \
        "8d82448ea5888beb6dd8f54c35ebb08ba40c58bd66b652bab6f0d39dfdf78ba4"
    assert s["e_protocol_identity"] == \
        "4adf3da33b86e734e7b663c6702c64f9377c08ac4318fb5439eebd439aec38e6"


def test_recipe_manifest_sha_exact():
    r = json.loads(
        (ROOT / "results/v3/v3_5e/final_fit_recipe.json").read_text())
    assert blob(r, "recipe_identity") == r["recipe_identity"] == RECIPE_ID
    m = json.loads(
        (ROOT / "results/v3/v3_5e/v3_5f_execution_manifest.json").read_text())
    assert blob(m, "manifest_identity") == \
        m["manifest_identity"] == MANIFEST_ID


def test_execution_record_frozen():
    rec = load("execution_record.json")
    assert blob(rec, "execution_record_identity") == \
        rec["execution_record_identity"] == EXEC_ID
    assert rec["allowed_season"] == 2025
    assert "evaluation only" in rec["allowed_operation"]
    assert rec["evaluation_terminology"] == \
        "PREVIOUSLY REVEALED OUT-OF-TIME OUTCOME EVALUATION"


def test_evaluation_season_2025_and_training_excludes_2025():
    da = load("dataset_audit.json")
    assert da["evaluation_season"] == 2025
    ta = load("training_audit.json")
    assert ta["training_seasons"] == [2018, 2019, 2020, 2021, 2022, 2023, 2024]
    assert ta["forbidden_in_fit"] == [2025]
    cal = load("calibration_transfer.json")["calibrator"]
    assert 2025 not in cal["training_seasons"]


def test_target_semantics_exactly_b():
    da = load("dataset_audit.json")
    assert da["target_contract"] == "v3.5b-target-v1"
    assert da["status_policy"] == "v3.5b-status-v1"
    assert da["population_policy"] == "v3.5b-population-v1"
    for n in NAMES:
        assert n in da["threshold_prevalence_states"]


def test_110_features_exact_order():
    pa = load("provenance_audit.json")
    assert pa["feature_hash"] == \
        "e054c6fb08c0832970165bcfc0e84f54b70787491af1d545b96a13977fc4c89e"


def test_identity_alignment_exact():
    x = pd.read_parquet(ROOT / "data/v3/v3_5f/xgb_predictions_2025.parquet")
    l = pd.read_parquet(
        ROOT / "data/v3/v3_5f/logistic_predictions_2025.parquet")
    assert len(x) == len(l) == 26692
    assert x["state_id"].is_unique and l["state_id"].is_unique
    assert (x["state_id"] == l["state_id"]).all()
    assert (x["season"] == 2025).all()
    assert (x["race_id"] == l["race_id"]).all()
    assert (x["driver_id"] == l["driver_id"]).all()
    for n in NAMES:
        assert (x["target_" + n] == l["target_" + n]).all()


def test_logistic_config_frozen():
    pa = load("provenance_audit.json")
    assert pa["logistic_config"] == {"C": 0.01}


def test_xgb_config_frozen_four_models():
    pa = load("provenance_audit.json")
    assert pa["xgb_config"] == {"learning_rate": 0.03, "max_depth": 3,
                                "min_child_weight": 15, "n_estimators": 300}
    r = json.loads(
        (ROOT / "results/v3/v3_5e/final_fit_recipe.json").read_text())
    assert r["four_threshold_structure"].startswith(
        "four independent binary models")


def test_top5_sigmoid_only():
    r = json.loads(
        (ROOT / "results/v3/v3_5e/final_fit_recipe.json").read_text())
    assert r["calibration_method"] == {"is_top1": "RAW", "is_top3": "RAW",
                                       "is_top5": "SIGMOID",
                                       "is_top10": "RAW"}
    cal = load("calibration_transfer.json")["calibrator"]
    assert cal["method"] == "SIGMOID" and cal["threshold"] == "is_top5"
    assert cal["coefficient"] > 0.0


def test_raw_cal_pava_order_and_projection():
    rec = load("execution_record.json")
    assert rec["allowed_operation"]
    src = (ROOT / "scripts/run_v3_5f_evaluation.py").read_text()
    assert "project_isotonic(mat_cal)" in src
    assert rec["projection_identity"] == "v3.5b-projection-v1"


def test_probabilities_bounded_and_coherent():
    for f in ("xgb_predictions_2025.parquet",
              "logistic_predictions_2025.parquet"):
        oof = pd.read_parquet(ROOT / "data/v3/v3_5f" / f)
        for n in NAMES:
            for col in ("raw_", "cal_", "proj_"):
                assert ((oof[col + n] >= 0.0)
                        & (oof[col + n] <= 1.0)).all()
        mat = oof[["proj_" + n for n in NAMES]].to_numpy()
        assert not (mat[:, :-1] > mat[:, 1:] + 1e-12).any()


def test_primary_and_threshold_metrics_exact():
    p = load("primary_results.json")
    assert abs(p["delta_proj"] - (p["xgb_proj"] - p["logistic_proj"])) < 1e-12
    t = load("threshold_results.json")
    assert set(t) == set(NAMES)
    for n in NAMES:
        assert abs(t[n]["delta_proj"]
                   - (t[n]["xgb_proj"] - t[n]["logistic_proj"])) < 1e-12


def test_top1_audit_present():
    t = load("top1_audit.json")
    assert {"logistic_top1", "xgb_top1", "delta", "improved",
            "worsened"} <= set(t)
    assert t["improved"] + t["worsened"] + t["ties"] == 24


def test_calibration_and_coherence_transfer_present():
    c = load("calibration_transfer.json")
    assert {"top5_raw_ll", "top5_cal_ll", "delta"} <= set(c)
    h = load("coherence_transfer.json")
    assert h["xgb_projected_violation_rate"] == 0.0
    assert {"logistic", "xgb_raw", "xgb_pre_pava"} <= set(h)


def test_race_unit_and_bootstrap():
    b = load("bootstrap_results.json")
    assert (b["unit"], b["replicates"], b["seed"],
            b["ci_level"]) == ("race", 2000, 42, 0.95)
    r = load("race_level_results.json")
    assert r["n_races"] == 24


def test_stage_partition_frozen():
    s = load("stage_results.json")
    assert set(s) == {"EARLY", "MID", "LATE"}


def test_transfer_classification_present():
    t = load("development_to_2025_transfer.json")
    assert t["overall_transfer"] in ("STRONG_TRANSFER", "PARTIAL_TRANSFER",
                                     "MIXED_TRANSFER", "NO_TRANSFER",
                                     "REVERSED")
    assert t["top1_transfer"] in ("WEAKNESS_PERSISTS", "WEAKNESS_ATTENUATES",
                                  "WEAKNESS_REVERSES", "MIXED")


def test_disposition_enum_closed():
    d = load("disposition.json")
    assert d["final_disposition"] in ("OUTCOME_XGB_GENERALIZES",
                                      "OUTCOME_XGB_MIXED_OUT_OF_TIME",
                                      "OUTCOME_XGB_FAILS_OUT_OF_TIME")
    assert "no config" in d["no_reselection"]


def test_no_reselection_in_source():
    src = (ROOT / "scripts/run_v3_5f_evaluation.py").read_text() \
        + (ROOT / "scripts/analyze_v3_5f_transfer.py").read_text()
    for bad in ('"X0"', '"X1"', '"X3"'):
        assert bad not in src
    assert "fit_isotonic" not in src and "IsotonicRegression" not in src
    low = src.lower().replace("column_stack", "")
    assert "blend" not in low and "stacking" not in low \
        and "ensemble" not in low


def test_firewall_evaluation_only():
    fw = load("firewall_audit.json")
    assert fw["2025_CONTACT"] == "EVALUATION_ONLY"
    assert fw["evaluation_season"] == 2025


def test_independent_recompute_exact():
    assert load("independent_recompute.json")["all_match"] is True


def test_prediction_determinism():
    d = load("determinism_audit.json")
    assert d["logical_identity_match"] is True
    assert d["max_abs_probability_difference"] == 0.0


def test_no_hgb_no_serving_changes():
    src = (ROOT / "scripts/run_v3_5f_evaluation.py").read_text()
    assert "HistGradient" not in src and "extra_trees" not in src
    assert "fastapi" not in src and "serving" not in src
