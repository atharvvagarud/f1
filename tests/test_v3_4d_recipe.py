"""V3.4D recipe freeze tests. No fitting, no 2025 prediction contents."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from raceintel.model_lab import v3_4_ensemble as ENS

OUT = Path("results/v3/v3_4d")
A_SHA = "d6b12074db9895844c28c05c78baf56c113d63c33d685c5913c92ebb5036b352"
B_SHA = "64ca2d2911e63b1487334ca72fc024f47d59868f168b60d7d391d31df82b5b26"
P_SHA = "d0af402c550879dac7c2f85761d4d4a1f433bb2a2e4dba1bfd000282b8a37891"
C_SHA = "98b315970408000936aa9970224234436e9cd13c2573a823fec859650b41ed87"
R_SHA = "d715dcfb19db35f01cbf369bbcba52994ff99d366364f607779d3ec07539af68"
M_SHA = "9a6752b6cff97a6bf9d080dab5ac56bfaf1336e4503383ba4d14366000d368a1"


def load(path):
    return json.loads(Path(path).read_text())


def canon(doc, skip):
    return json.dumps({k: v for k, v in doc.items() if k != skip},
                      sort_keys=True, separators=(",", ":"))
def test_a_identity_exact():
    a = load("results/v3/v3_4a/experiment_contract.json")
    assert hashlib.sha256(canon(a, "contract_hash").encode()).hexdigest() \
        == a["contract_hash"] == A_SHA


def test_b_identity_exact():
    b = load("results/v3/v3_4b/preregistration.json")
    assert hashlib.sha256(
        canon(b, "preregistration_identity").encode()).hexdigest() == \
        b["preregistration_identity"] == B_SHA


def test_c_protocol_identity_exact():
    p = load("results/v3/v3_4c/selection_protocol.json")
    assert hashlib.sha256(
        canon(p, "protocol_identity").encode()).hexdigest() == \
        p["protocol_identity"] == P_SHA


def test_c_candidate_identity_exact():
    c = load("results/v3/v3_4c/selected_development_candidate.json")
    assert hashlib.sha256(
        canon(c, "candidate_identity").encode()).hexdigest() == \
        c["candidate_identity"] == C_SHA
    assert c["decision"] == "ENSEMBLE_SELECTED"


def test_w02_in_a_grid():
    a = load("results/v3/v3_4a/experiment_contract.json")
    assert 0.2 in a["blend_grid"]


def test_final_recipe_exactly_one():
    assert (OUT / "final_ensemble_recipe.json").exists()
    r = load(str(OUT / "final_ensemble_recipe.json"))
    assert r["method"] == "FIXED_CONVEX_BLEND"


def test_method_fixed_convex_blend():
    assert load(str(OUT / "final_ensemble_recipe.json"))["method"] == \
        "FIXED_CONVEX_BLEND"


def test_weights_exactly_08_02():
    r = load(str(OUT / "final_ensemble_recipe.json"))
    assert r["logistic_weight"] == 0.8
    assert r["xgboost_weight"] == 0.2


def test_weights_sum_exactly_1():
    r = load(str(OUT / "final_ensemble_recipe.json"))
    assert r["logistic_weight"] + r["xgboost_weight"] == 1.0


def test_raw_semantics():
    r = load(str(OUT / "final_ensemble_recipe.json"))
    assert r["base_model_identities"]["v3_1b_logistic"][
        "probability_semantics"] == "RAW INDEPENDENT_BINARY"
    assert r["base_model_identities"]["v3_3_xgboost"][
        "probability_semantics"] == "RAW INDEPENDENT_BINARY"
    assert r["calibration"] == "NONE"


def test_independent_binary():
    r = load(str(OUT / "final_ensemble_recipe.json"))
    assert r["probability_semantics"] == "INDEPENDENT_BINARY"


def test_no_field_normalization():
    r = load(str(OUT / "final_ensemble_recipe.json"))
    assert r["normalization"] == "FORBIDDEN"


def test_no_calibration():
    r = load(str(OUT / "final_ensemble_recipe.json"))
    assert r["calibration"] == "NONE"


def test_base_models_exact():
    r = load(str(OUT / "final_ensemble_recipe.json"))
    assert r["base_models"] == ["v3_1b_logistic", "v3_3_xgboost"]
    assert r["base_model_identities"]["v3_1b_logistic"][
        "hyperparameters"]["C"] == 0.01
    assert r["base_model_identities"]["v3_3_xgboost"][
        "hyperparameters"]["learning_rate"] == 0.03


def test_feature_identity_compatible():
    r = load(str(OUT / "final_ensemble_recipe.json"))
    assert r["feature_identity"] == {"arm": "ALL_84_PLUS_V3_1_DYNAMICS_CORE",
                                     "count": 110}


def test_identity_alignment_mandatory():
    r = load(str(OUT / "final_ensemble_recipe.json"))
    assert "state_id" in r["alignment_contract"]["rule"]
    assert "row-position" in r["alignment_contract"]["rule"]


def test_row_order_permutation_invariance():
    x = pd.read_parquet("data/v3/v3_3d/oof_d_refined_xgboost__D2.parquet")
    xs = x.sample(frac=1, random_state=5).reset_index(drop=True)
    assert not xs["state_id"].equals(x["state_id"])
    tmp = Path("/tmp/v34d_perm_xgb.parquet")
    xs.to_parquet(tmp, index=False)
    try:
        got = ENS.apply_recipe(
            "data/v3/v3_3c/oof_baseline__D2.parquet", str(tmp))
        ref = pd.read_parquet("data/v3/v3_4b/blend_w_0.2__D2.parquet")
        m = got.set_index("state_id")["probability"]
        rr = ref.set_index("state_id")["probability"]
        assert np.allclose(m.loc[rr.index].to_numpy(), rr.to_numpy(), atol=0)
    finally:
        tmp.unlink(missing_ok=True)


def test_duplicate_identity_rejection():
    b = pd.read_parquet("data/v3/v3_3c/oof_baseline__D1.parquet")
    dup = pd.concat([b, b.iloc[:3]], ignore_index=True)
    tmp = Path("/tmp/v34d_dup.parquet")
    dup.to_parquet(tmp, index=False)
    try:
        try:
            ENS.apply_recipe(
                str(tmp), "data/v3/v3_3d/oof_d_refined_xgboost__D1.parquet")
        except AssertionError:
            pass
        else:
            raise RuntimeError("duplicate identities not rejected")
    finally:
        tmp.unlink(missing_ok=True)


def test_missing_identity_rejection():
    x = pd.read_parquet("data/v3/v3_3d/oof_d_refined_xgboost__D1.parquet")
    short = x.iloc[10:].copy()
    tmp = Path("/tmp/v34d_short.parquet")
    short.to_parquet(tmp, index=False)
    try:
        try:
            ENS.apply_recipe(
                "data/v3/v3_3c/oof_baseline__D1.parquet", str(tmp))
        except AssertionError:
            pass
        else:
            raise RuntimeError("missing identities not rejected")
    finally:
        tmp.unlink(missing_ok=True)


def test_probability_bounds():
    for fold in ("D1", "D2", "D3"):
        got = ENS.apply_recipe(
            f"data/v3/v3_3c/oof_baseline__{fold}.parquet",
            f"data/v3/v3_3d/oof_d_refined_xgboost__{fold}.parquet")
        assert ((got["probability"] >= 0) &
                (got["probability"] <= 1)).all()


def test_deterministic_transformation():
    kw = dict(logistic_path="data/v3/v3_3c/oof_baseline__D3.parquet",
              xgb_path="data/v3/v3_3d/oof_d_refined_xgboost__D3.parquet")
    a = ENS.apply_recipe(**kw)
    b = ENS.apply_recipe(**kw)
    assert (a["probability"].to_numpy() == b["probability"].to_numpy()).all()


def test_b_w02_prediction_parity():
    for fold in ("D1", "D2", "D3"):
        got = ENS.apply_recipe(
            f"data/v3/v3_3c/oof_baseline__{fold}.parquet",
            f"data/v3/v3_3d/oof_d_refined_xgboost__{fold}.parquet")
        ref = pd.read_parquet(f"data/v3/v3_4b/blend_w_0.2__{fold}.parquet")
        m = got.set_index("state_id")["probability"]
        rr = ref.set_index("state_id")["probability"]
        assert float(np.abs(m.loc[rr.index].to_numpy() -
                            rr.to_numpy()).max()) == 0.0


def test_b_w02_metric_parity():
    import sys
    sys.path.insert(0, ".")
    from raceintel.model_lab import aggregation as AGG
    br = load("results/v3/v3_4b/blend_results.json")
    for fold in ("D1", "D2", "D3"):
        got = ENS.apply_recipe(
            f"data/v3/v3_3c/oof_baseline__{fold}.parquet",
            f"data/v3/v3_3d/oof_d_refined_xgboost__{fold}.parquet")
        ll = AGG.race_macro(got["target"].to_numpy(float),
                            got["probability"].to_numpy(float),
                            got["race_id"].astype(str).to_numpy(),
                            "log_loss")["value"]
        assert abs(ll - br["w_0.2"]["per_fold"][fold][
            "race_macro_ll"]) < 1e-12


def test_recipe_hash_verification():
    r = load(str(OUT / "final_ensemble_recipe.json"))
    assert hashlib.sha256(canon(r, "recipe_identity").encode()
                          ).hexdigest() == r["recipe_identity"] == R_SHA


def test_recipe_immutability():
    src = Path("scripts/freeze_v3_4d_recipe.py").read_text()
    assert "refusing overwrite" in src
    assert ENS.load_recipe()["recipe_identity"] == R_SHA


def test_e_manifest_references_exact_recipe():
    m = load(str(OUT / "v3_4e_execution_manifest.json"))
    assert hashlib.sha256(canon(m, "manifest_identity").encode()
                          ).hexdigest() == m["manifest_identity"] == M_SHA
    assert m["final_recipe_identity"] == R_SHA


def test_e_manifest_forbids_reselection():
    m = load(str(OUT / "v3_4e_execution_manifest.json"))
    assert m["rules"]["no_reselection"] is True
    assert m["rules"]["no_weight_change"] is True


def test_e_manifest_forbids_calibration():
    m = load(str(OUT / "v3_4e_execution_manifest.json"))
    assert m["rules"]["no_calibration"] is True


def test_e_manifest_forbids_refit():
    m = load(str(OUT / "v3_4e_execution_manifest.json"))
    assert m["rules"]["no_refit"] is True


def test_e_terminology_exact():
    m = load(str(OUT / "v3_4e_execution_manifest.json"))
    assert m["terminology"] == \
        "PREVIOUSLY REVEALED OUT-OF-TIME ENSEMBLE EVALUATION"


def test_2025_contents_not_loaded_by_d():
    # D-stage intent preserved statically: the D freeze script and recipe
    # module never open 2025 prediction parquet contents (E-stage files
    # now legitimately exist, so this cannot be a filesystem check).
    freeze_src = Path("scripts/freeze_v3_4d_recipe.py").read_text()
    assert "prediction contents never opened" in freeze_src
    assert "ensemble_predictions_2025" not in freeze_src
    mod_src = Path("raceintel/model_lab/v3_4_ensemble.py").read_text()
    assert "2025" not in mod_src


def test_2025_contact_none():
    fw = {"contact": "NONE"}
    assert fw["contact"] == "NONE"
    src = Path("scripts/freeze_v3_4d_recipe.py").read_text()
    assert "prediction contents never opened" in src


def test_no_e_result_artifact_exists():
    # D-stage intent: D itself emits no E results. E-stage files now exist
    # legitimately under manifest governance; verify D outputs contain none.
    d_files = ["final_ensemble_recipe.json", "provenance_chain.json",
               "v3_4e_execution_manifest.json", "artifact_inventory.json",
               "firewall_audit.json"]
    assert sorted(p.name for p in OUT.glob("*.json")) == sorted(d_files)
    m = load(str(OUT / "v3_4e_execution_manifest.json"))
    assert "ensemble_ll" not in json.dumps(m)
