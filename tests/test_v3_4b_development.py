"""V3.4B development-ensemble tests. No fitting, no 2025 contact."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

OUT = Path("results/v3/v3_4b")
PRED_OUT = Path("data/v3/v3_4b")
A_SHA = "d6b12074db9895844c28c05c78baf56c113d63c33d685c5913c92ebb5036b352"
GRID = [round(i / 10, 1) for i in range(11)]


def load(name):
    return json.loads((OUT / name).read_text())


def test_a_contract_hash():
    a = json.loads(
        Path("results/v3/v3_4a/experiment_contract.json").read_text())
    blob = json.dumps({k: v for k, v in a.items() if k != "contract_hash"},
                      sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        a["contract_hash"] == A_SHA


def test_b_prereg_immutable():
    pre = load("preregistration.json")
    blob = json.dumps(
        {k: v for k, v in pre.items() if k != "preregistration_identity"},
        sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        pre["preregistration_identity"]
    assert pre["a_contract_identity"] == A_SHA
    assert pre["selection"] == "NONE IN B (V3.4C owns selection)"


def test_exact_blend_grid():
    pre = load("preregistration.json")
    assert pre["blend_grid"] == GRID
    assert GRID[0] == 0.0 and GRID[-1] == 1.0
    assert all(0.0 <= w <= 1.0 for w in GRID)


def test_w0_logistic_identity():
    for fold in ("D1", "D2", "D3"):
        blend = pd.read_parquet(PRED_OUT / f"blend_w_0.0__{fold}.parquet")
        base = pd.read_parquet(
            f"data/v3/v3_3c/oof_baseline__{fold}.parquet")
        m = blend.set_index("state_id")["probability"]
        b = base.set_index("state_id")
        assert (m.loc[b.index].to_numpy() ==
                b["probability"].to_numpy()).all()


def test_w1_xgb_identity():
    for fold in ("D1", "D2", "D3"):
        blend = pd.read_parquet(PRED_OUT / f"blend_w_1.0__{fold}.parquet")
        xgb = pd.read_parquet(
            f"data/v3/v3_3d/oof_d_refined_xgboost__{fold}.parquet")
        m = blend.set_index("state_id")["probability"]
        x = xgb.set_index("state_id")
        assert (m.loc[x.index].to_numpy() ==
                x["probability"].to_numpy()).all()


def test_identity_joins_and_counts():
    audit = load("alignment_audit.json")
    assert audit["rows"] == {"D1": 23577, "D2": 24422, "D3": 26606}
    assert audit["total_rows"] == 74605
    assert audit["n_races"] == 68
    assert audit["mismatches"] == 0
    assert audit["join"] == "state_id only"


def test_row_order_permutation_invariance():
    b = pd.read_parquet("data/v3/v3_3c/oof_baseline__D2.parquet")
    x = pd.read_parquet(
        "data/v3/v3_3d/oof_d_refined_xgboost__D2.parquet")
    xs = x.sample(frac=1, random_state=11).reset_index(drop=True)
    assert not xs["state_id"].equals(x["state_id"])
    w = 0.4
    m = b.merge(xs[["state_id", "probability"]], on="state_id",
                suffixes=("_log", "_xgb"))
    p = (1 - w) * m["probability_log"] + w * m["probability_xgb"]
    ref = pd.read_parquet(PRED_OUT / "blend_w_0.4__D2.parquet")
    r = ref.set_index("state_id").loc[m["state_id"], "probability"]
    assert np.allclose(p.to_numpy(), r.to_numpy(), atol=0)


def test_probability_bounds():
    for p in sorted(PRED_OUT.glob("*.parquet")):
        d = pd.read_parquet(p, columns=["probability"])
        assert np.all(np.isfinite(d["probability"].to_numpy()))
        assert ((d["probability"] >= 0) &
                (d["probability"] <= 1)).all()


def test_no_field_normalization():
    for fold in ("D1", "D2", "D3"):
        d = pd.read_parquet(PRED_OUT / f"blend_w_0.4__{fold}.parquet")
        s = d.groupby("race_id")["probability"].sum()
        assert not np.allclose(s.to_numpy(), 1.0, atol=1e-6), \
            "field-normalized output forbidden"


def test_d1_stacker_fallback():
    coefs = load("stacker_coefficients.json")
    assert coefs["D1"]["status"].startswith("NOT_EVALUABLE")
    assert coefs["D1"]["n_train_rows"] == 0
    res = load("stacker_results.json")
    assert "fallback" in res["per_fold"]["D1"]["note"]
    assert res["bootstrap"]["D1"] is None


def test_d2_d3_temporal_safety():
    coefs = load("stacker_coefficients.json")
    assert coefs["D2"]["train_folds"] == ["D1"]
    assert coefs["D2"]["train_seasons"] == [2022]
    assert coefs["D3"]["train_folds"] == ["D1", "D2"]
    assert coefs["D3"]["train_seasons"] == [2022, 2023]


def test_no_target_fold_leakage():
    coefs = load("stacker_coefficients.json")
    for fold in ("D2", "D3"):
        assert fold not in coefs[fold]["train_folds"]
        assert int(fold[1]) + 2021 not in coefs[fold]["train_seasons"]


def test_fixed_stacker_c_no_search():
    pre = load("preregistration.json")
    assert pre["stacker"]["C"] == 1.0
    assert pre["stacker"]["solver"] == "lbfgs"
    assert pre["stacker"]["seed"] == 42


def test_race_macro_primary_and_bootstrap_policy():
    pre = load("preregistration.json")
    assert pre["metrics"]["primary"].startswith("race_macro_log_loss")
    assert pre["bootstrap"]["unit"].startswith("race")
    assert pre["bootstrap"]["replicates"] == 2000
    assert pre["bootstrap"]["seed"] == 42
    boot = load("blend_race_bootstrap.json")
    assert boot["w_0.4"]["pooled"]["replicates"] == 2000
    assert boot["w_0.4"]["pooled"]["seed"] == 42


def test_stage_partition():
    stage = load("blend_stage_results.json")
    assert set(stage["w_0.4"]["D1"]) == {"EARLY", "MID", "LATE"}
    assert stage["w_0.4"]["D1"]["EARLY"]["n_states"] > 0


def test_prediction_hashes():
    hashes = load("prediction_hashes.json")
    assert len(hashes) == 36
    for name, sha in hashes.items():
        fname = name if name.startswith("stacker") else f"blend_{name}"
        path = PRED_OUT / f"{fname}.parquet"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == sha


def test_forbidden_2025_paths_absent():
    for p in PRED_OUT.glob("*.parquet"):
        d = pd.read_parquet(p, columns=["season"])
        assert (d["season"] != 2025).all()
    audit = load("firewall_audit.json")
    assert audit["2025_CONTACT"] == "NONE"
    assert sorted(audit["seasons_seen"]) == [2022, 2023, 2024]


def test_2025_season_rejected_by_loader():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "v3_4b_mod", "scripts/run_v3_4b_experiments.py")
    assert spec is not None and spec.loader is not None
    # Fail closed: the experiment loader allowlists exactly the six
    # development OOF streams; anything else (2025 paths included) raises.
    src = Path("scripts/run_v3_4b_experiments.py").read_text()
    assert "2025" in src  # firewall assertions present
    assert "forbidden artifact path" in src
    assert "2025 row loaded" in src


def test_no_final_recipe_emitted():
    summary = json.loads(
        Path("results/v3/v3_4b_development_ensembles.json").read_text())
    assert summary["final_ensemble_recipe"] == \
        "NONE EMITTED IN B (V3.4C owns selection)"
    assert summary["2025_contact"] == "NONE"
    for name in ("blend_results", "weight_landscape", "stacker_results"):
        blob = json.dumps(load(f"{name}.json")).lower()
        assert "final_recipe" not in blob
        assert "selected_recipe" not in blob
        assert "selected_weight" not in blob
    wl = load("weight_landscape.json")
    assert all(r["status"] == "DESCRIPTIVE_ONLY_NOT_SELECTED" for r in wl)
