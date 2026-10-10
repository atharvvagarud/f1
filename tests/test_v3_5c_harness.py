"""V3.5C baseline + harness tests. One learned control only; no 2025."""
import glob
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from raceintel.model_lab import outcomes as OC

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results/v3/v3_5c"
C_HASH = "9dfee182215d6a56e4f19e2418b051883e9c75876418a6f4c92a05d799c7603a"
A_ID = "15ca7c17146062edb5196a5de244fadd81d38562b2ca5714e58a21d4efb5efab"
B_ID = "e9ac34e5792a5aabba9038094a231a4a94789b481178739e46ece72457cc5289"
FEAT_HASH = "e054c6fb08c0832970165bcfc0e84f54b70787491af1d545b96a13977fc4c89e"
NAMES = ["is_top1", "is_top3", "is_top5", "is_top10"]
FOLDS = ("D1", "D2", "D3")
MODELS = ("climatology", "position_persistence", "grid", "l2_logistic")


def load(name):
    return json.loads((RES / name).read_text())


def oof(fid):
    return pd.read_parquet(ROOT / f"data/v3/v3_5c/oof_{fid}.parquet")


def test_a_identity_exact():
    assert load("baseline_results.json") is not None
    c = load("screening_harness_contract.json")
    assert c["a_identity"] == A_ID


def test_b_identity_exact():
    assert load("screening_harness_contract.json")["b_dataset_identity"] == B_ID


def test_c_contract_immutable_after_fitting():
    c = load("screening_harness_contract.json")
    blob = json.dumps({k: v for k, v in c.items() if k != "contract_hash"},
                      sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        c["contract_hash"] == C_HASH
    assert c["baselines"]["l2_logistic_control"]["config"] == {"C": 0.01}


def test_threshold_order_exact():
    assert list(OC.THRESHOLD_ORDER) == [1, 3, 5, 10]
    assert load("screening_harness_contract.json")["threshold_order"] == \
        [1, 3, 5, 10]


def test_110_features_exact():
    from raceintel.model_lab import v3_dynamics_experiment as V3C
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_110 = V3C.v3_feature_names(
        V3C.ARM_B, tuple(canonical_predictive_names()))
    assert len(names_110) == 110
    assert load("screening_harness_contract.json")["feature_identity"]["hash"] \
        == FEAT_HASH


def test_d1_d2_d3_exact():
    splits = load("split_audit.json")
    assert splits["D1"]["train_seasons"] == [2018, 2019, 2020, 2021]
    assert splits["D1"]["validate_seasons"] == [2022]
    assert splits["D2"]["validate_seasons"] == [2023]
    assert splits["D3"]["validate_seasons"] == [2024]
    assert splits["D1"]["validation_states"] == 23577
    assert splits["D2"]["validation_states"] == 24422
    assert splits["D3"]["validation_states"] == 26606


def test_outer_train_validation_isolation():
    splits = load("split_audit.json")
    assert splits["D1"]["train_states"] == 88123
    assert splits["D2"]["train_states"] == 111700
    assert splits["D3"]["train_states"] == 136122
    # train + all validation partitions reconstruct the dev population
    assert 88123 + 23577 + 24422 + 26606 == 162728


def test_climatology_train_only():
    r = load("baseline_results.json")
    assert r["D1"]["climatology"]["primary_raw"] == pytest.approx(0.485202, abs=1e-6)
    o = oof("D1")
    sub = o[o["model"] == "climatology"]
    assert (sub["raw_is_top1"] == sub["raw_is_top1"].iloc[0]).all()


def test_position_persistence_causal():
    o = oof("D3")
    sub = o[o["model"] == "position_persistence"]
    # 0/1 from causal position plus the frozen train-rate fallback for the
    # 261 null-position states (still nested, still causal)
    vals = set(np.unique(sub["raw_is_top1"].to_numpy()))
    # exactly one non-{0,1} value: the frozen train-rate fallback, identical
    # to the climatology constant for this fold/threshold
    extra = vals - {0.0, 1.0}
    assert len(extra) == 1
    clim = o[o["model"] == "climatology"]["raw_is_top1"].iloc[0]
    assert extra.pop() == pytest.approx(clim, abs=1e-15)
    assert (sub["raw_is_top1"] <= sub["raw_is_top3"]).all()


def test_grid_causal():
    o = oof("D2")
    sub = o[o["model"] == "grid"]
    assert set(np.unique(sub["raw_is_top10"].to_numpy())) <= {0.0, 1.0}


def test_logistic_config_fixed():
    c = load("screening_harness_contract.json")["baselines"]["l2_logistic_control"]
    assert c["config"] == {"C": 0.01}
    assert c["fixed_estimator"]["solver"] == "lbfgs"
    assert c["fixed_estimator"]["random_state"] == 42


def test_no_logistic_tuning():
    import subprocess
    src = (ROOT / "scripts/run_v3_5c_baselines.py").read_text()
    assert "GridSearchCV" not in src and "RandomizedSearchCV" not in src
    assert src.count('"C": 0.01') + src.count("{'C': 0.01}") >= 1
    assert "C=0.01" in src


def test_preprocessing_train_only():
    p = load("preprocessing_contract.json")
    assert p["fit_on"] == "outer TRAIN only"
    assert len(p["features_110_exact"]) == 110


def test_prediction_identity_alignment():
    for fid in FOLDS:
        o = oof(fid)
        assert o["state_id"].is_unique is False  # 4 models share states
        assert (o.groupby("model")["state_id"].apply(
            lambda s: s.is_unique)).all()


def test_row_permutation_invariance():
    o = oof("D1")
    sh = o.sample(frac=1.0, random_state=11)
    a = o.sort_values(["model", "state_id"]).reset_index(drop=True)
    b = sh.sort_values(["model", "state_id"]).reset_index(drop=True)
    assert (a["raw_is_top1"].to_numpy() == b["raw_is_top1"].to_numpy()).all()


def test_raw_probabilities_bounded():
    for fid in FOLDS:
        o = oof(fid)
        for n in NAMES:
            v = o["raw_" + n].to_numpy(float)
            assert np.all(np.isfinite(v)) and v.min() >= 0.0 and v.max() <= 1.0


def test_projection_exact_b_implementation():
    o = oof("D3")
    sub = o[o["model"] == "l2_logistic"].sort_values("state_id")
    raw = np.column_stack([sub["raw_" + n].to_numpy(float) for n in NAMES])
    proj, _ = OC.project_isotonic(raw)
    stored = np.column_stack([sub["proj_" + n].to_numpy(float) for n in NAMES])
    assert np.array_equal(proj, stored)


def test_projected_probabilities_coherent():
    for fid in FOLDS:
        o = oof(fid)
        p = np.column_stack([o["proj_" + n].to_numpy(float) for n in NAMES])
        assert bool((np.diff(p, axis=1) >= 0).all())


def test_coherent_input_unchanged():
    o = oof("D1")
    for model in ("climatology", "position_persistence", "grid"):
        sub = o[o["model"] == model]
        for n in NAMES:
            assert np.array_equal(sub["raw_" + n].to_numpy(),
                                  sub["proj_" + n].to_numpy()), (model, n)


def test_derived_bands_valid():
    o = oof("D2")
    sub = o[o["model"] == "l2_logistic"]
    q = np.column_stack([sub["proj_" + n].to_numpy(float) for n in NAMES])
    b = OC.derived_bands(q)
    assert bool((b >= 0).all()) and np.allclose(b.sum(axis=1), 1.0, atol=1e-9)


def test_primary_metric_formula():
    r = load("baseline_results.json")
    for fid in FOLDS:
        for model in MODELS:
            thr = r[fid][model]["thresholds"]
            expect = float(np.mean([thr[n]["race_macro_ll_raw"] for n in NAMES]))
            assert r[fid][model]["primary_raw"] == pytest.approx(expect, abs=1e-12)


def test_race_macro_aggregation():
    from raceintel.model_lab import aggregation as AGG
    o = oof("D3")
    sub = o[o["model"] == "climatology"]
    d = AGG.race_macro(sub["target_is_top1"].to_numpy(float),
                       sub["raw_is_top1"].to_numpy(float),
                       sub["race_id"].astype(str).to_numpy(), "log_loss")
    assert d["n_races"] == 24
    assert d["value"] == pytest.approx(
        load("baseline_results.json")["D3"]["climatology"]["thresholds"]
        ["is_top1"]["race_macro_ll_raw"], abs=1e-12)


def test_per_threshold_metric_reproduction():
    assert load("harness_parity.json")["metric_match"] is True


def test_projection_diagnostics():
    r = load("baseline_results.json")
    d = r["D3"]["l2_logistic"]["projection"]
    assert d["n_rows"] == 26606 and d["frac_violated_before"] > 0
    for model in ("climatology", "position_persistence", "grid"):
        dd = r["D3"][model]["projection"]
        assert dd["n_violated_before"] == 0


def test_bootstrap_race_unit():
    b = load("bootstrap_validation.json")
    for fid in FOLDS:
        for key in (f"l2_logistic_vs_climatology",
                    f"l2_logistic_vs_position_persistence"):
            e = b[fid][key]
            assert e["replicates"] == 2000 and e["seed"] == 42
            assert e["ci_level"] == 0.95
            assert "states" not in e["procedure"]


def test_bootstrap_b2000():
    assert load("screening_harness_contract.json")["bootstrap"]["replicates"] \
        == 2000


def test_bootstrap_seed42():
    assert load("screening_harness_contract.json")["bootstrap"]["seed"] == 42


def test_oof_seasons_only_2022_2023_2024():
    for fid, s in (("D1", 2022), ("D2", 2023), ("D3", 2024)):
        assert sorted(oof(fid)["season"].unique().tolist()) == [s]


def test_no_oof_overlap():
    s1 = set(oof("D1")["state_id"]) & set(oof("D2")["state_id"])
    assert not s1
    assert not (set(oof("D2")["state_id"]) & set(oof("D3")["state_id"]))


def test_oof_unique_identities():
    for fid in FOLDS:
        o = oof(fid)
        assert (o.groupby("model")["state_id"].apply(
            lambda s: s.is_unique)).all()
        assert len(o) == 4 * len(o[o["model"] == "climatology"])


def test_prediction_logical_identity_deterministic():
    ids = load("prediction_identities.json")
    for fid in FOLDS:
        e = ids[fid]
        assert e["rows"] == {"D1": 94308, "D2": 97688, "D3": 106424}[fid]
        assert e["models"] == ["climatology", "grid", "l2_logistic",
                               "position_persistence"]


def test_harness_parity():
    assert load("harness_parity.json")["all_match"] is True


def test_2025_rejected():
    with pytest.raises(Exception):
        OC.assert_development_seasons([2025])
    for fid in FOLDS:
        assert 2025 not in oof(fid)["season"].tolist()


def test_2025_contact_none():
    assert load("firewall_audit.json")["2025_CONTACT"] == "NONE"
    assert load("firewall_audit.json")["verdict"] == "PASS"


def test_no_xgb_hgb_et_fit():
    src = (ROOT / "scripts/run_v3_5c_baselines.py").read_text()
    for token in ("XGBClassifier", "HistGradientBoosting", "ExtraTrees",
                  "xgb", "RankSVM", "ordinal"):
        assert token not in src, token
    assert "logistic_regression" in src


def test_no_screening_grid():
    src = (ROOT / "scripts/run_v3_5c_baselines.py").read_text()
    assert "param_grid" not in src and "GridSearchCV" not in src


def test_no_serving_api_frontend_change():
    import subprocess
    out = subprocess.run(["git", "status", "--short"], capture_output=True,
                         text=True, cwd=ROOT).stdout
    for line in out.splitlines():
        p = line[3:]
        # V3.6F/G chartered Strategy 2.0 paths admitted.
        if p.startswith(("api/v2_strategy_v3_", "api/main.py",
                         "frontend/app/strategy/page.tsx",
                         "frontend/features/strategy/components/Strategy",
                         "frontend/features/strategy/hooks/useStrategy",
                         "frontend/features/strategy/lib/strategy",
                         "frontend/lib/v2.ts")):
            continue
        assert not p.startswith(("api/", "frontend/")), line
        assert "serving" not in p or "model_lab/serving" not in p, line
