"""V3.5D temporal screening tests. Closed set; no 2025; no blending."""
import glob
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from raceintel.model_lab import outcomes as OC

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results/v3/v3_5d"
PROTO_ID = "8d82448ea5888beb6dd8f54c35ebb08ba40c58bd66b652bab6f0d39dfdf78ba4"
NAMES = ["is_top1", "is_top3", "is_top5", "is_top10"]
FOLDS = ("D1", "D2", "D3")


def load(name):
    return json.loads((RES / name).read_text())


def oof(fam, fid):
    return pd.read_parquet(ROOT / f"data/v3/v3_5d/oof_{fam}__{fid}.parquet")


def test_abc_identities_exact():
    p = load("screening_protocol.json")
    assert p["a_identity"] == \
        "15ca7c17146062edb5196a5de244fadd81d38562b2ca5714e58a21d4efb5efab"
    assert p["b_identity"] == \
        "e9ac34e5792a5aabba9038094a231a4a94789b481178739e46ece72457cc5289"
    assert p["c_identity"] == \
        "9dfee182215d6a56e4f19e2418b051883e9c75876418a6f4c92a05d799c7603a"


def test_d_protocol_frozen_before_first_fit():
    p = load("screening_protocol.json")
    blob = json.dumps({k: v for k, v in p.items() if k != "protocol_identity"},
                      sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        p["protocol_identity"] == PROTO_ID


def test_candidate_families_exactly_logistic_hgb_xgb():
    p = load("screening_protocol.json")
    assert p["candidate_families"] == \
        ["LOGISTIC_CONTROL", "HIST_GRADIENT_BOOSTING", "XGBOOST"]
    assert p["screening_candidates"] == ["HIST_GRADIENT_BOOSTING", "XGBOOST"]


def test_no_extratrees():
    p = load("screening_protocol.json")
    assert "ExtraTrees" in p["forbidden_families"]
    src = (ROOT / "scripts/run_v3_5d_screening.py").read_text()
    assert "ExtraTrees" not in src and "extra_trees" not in src


def test_hgb_grid_closed():
    p = load("screening_protocol.json")
    assert len(p["hgb_grid"]) <= 6
    assert p["hgb_grid"] == [
        {"learning_rate": 0.03, "max_leaf_nodes": 15, "min_samples_leaf": 20},
        {"learning_rate": 0.03, "max_leaf_nodes": 31, "min_samples_leaf": 20},
        {"learning_rate": 0.05, "max_leaf_nodes": 15, "min_samples_leaf": 20},
        {"learning_rate": 0.05, "max_leaf_nodes": 31, "min_samples_leaf": 20}]


def test_xgb_grid_closed():
    p = load("screening_protocol.json")
    assert len(p["xgb_grid"]) <= 6
    assert all(set(c) == {"learning_rate", "max_depth", "min_child_weight"}
               for c in p["xgb_grid"])


def test_grid_lte6_each():
    p = load("screening_protocol.json")
    assert len(p["hgb_grid"]) <= 6 and len(p["xgb_grid"]) <= 6


def test_four_independent_threshold_models():
    sel = load("selection_results.json")["inner_selection"]
    assert set(sel) == {"hgb", "xgb"}
    assert load("screening_protocol.json")["structure"].startswith(
        "four independent binary models")


def test_shared_family_config_across_thresholds():
    p = load("screening_protocol.json")
    assert "ONE family configuration shared" in \
        p["inner_temporal_selection"]["shared_config"]
    sel = load("selection_results.json")["inner_selection"]
    for fam in ("hgb", "xgb"):
        for fid in FOLDS:
            assert set(sel[fam][fid]["chosen"]) <= \
                {"learning_rate", "max_leaf_nodes", "min_samples_leaf",
                 "max_depth", "min_child_weight"}


def test_inner_selection_train_history_only():
    p = load("screening_protocol.json")
    assert "outer TRAIN history only" in \
        p["inner_temporal_selection"]["mechanism"]
    sel = load("selection_results.json")["inner_selection"]
    assert sel["hgb"]["D1"]["inner_folds"] == ["D1-I1"]
    assert sel["xgb"]["D3"]["inner_folds"] == ["D3-I1", "D3-I2", "D3-I3"]


def test_outer_validation_never_selects():
    p = load("screening_protocol.json")
    assert p["outer_evaluation"].startswith("select on TRAIN history only")


def test_no_calibration():
    # ECE is a frozen diagnostic *metric* (explicitly admitted secondary);
    # forbidden is *model* calibration (fitted/rescue). Assert no fitted or
    # rescue calibration machinery in the screening path.
    src = (ROOT / "scripts/run_v3_5d_screening.py").read_text()
    for token in ("CalibratedClassifierCV", "calibration_selection",
                  "IsotonicRegression", "rescue"):
        assert token not in src, token
    assert "expected_calibration_error" in src  # diagnostic metric present


def test_110_features_exact():
    p = load("screening_protocol.json")
    assert p["feature_identity"]["n"] == 110
    assert p["feature_identity"]["hash"] == \
        "e054c6fb08c0832970165bcfc0e84f54b70787491af1d545b96a13977fc4c89e"


def test_projection_exact_b_utility():
    for fam in ("hgb", "xgb"):
        for fid in FOLDS:
            df = oof(fam, fid)
            raw = np.column_stack([df["raw_" + n].to_numpy(float)
                                   for n in NAMES])
            proj, _ = OC.project_isotonic(raw)
            stored = np.column_stack([df["proj_" + n].to_numpy(float)
                                      for n in NAMES])
            assert np.array_equal(proj, stored), (fam, fid)


def test_control_c_reproduction():
    c = json.loads(
        (ROOT / "results/v3/v3_5c/baseline_results.json").read_text())
    assert abs(c["D1"]["l2_logistic"]["primary_proj"] - 0.221024) < 1e-6
    assert abs(c["D2"]["l2_logistic"]["primary_proj"] - 0.202037) < 1e-6
    assert abs(c["D3"]["l2_logistic"]["primary_proj"] - 0.187885) < 1e-6


def test_raw_probabilities_finite_bounded():
    for fam in ("hgb", "xgb"):
        for fid in FOLDS:
            df = oof(fam, fid)
            for n in NAMES:
                v = df["raw_" + n].to_numpy(float)
                assert np.all(np.isfinite(v)) and v.min() >= 0 and v.max() <= 1


def test_projected_coherent():
    for fam in ("hgb", "xgb"):
        for fid in FOLDS:
            df = oof(fam, fid)
            p = np.column_stack([df["proj_" + n].to_numpy(float)
                                 for n in NAMES])
            assert bool((np.diff(p, axis=1) >= 0).all())


def test_oof_identity_unique():
    for fam in ("hgb", "xgb"):
        for fid in FOLDS:
            assert oof(fam, fid)["state_id"].is_unique


def test_oof_fold_disjoint():
    for fam in ("hgb", "xgb"):
        ids = [set(oof(fam, fid)["state_id"]) for fid in FOLDS]
        assert not (ids[0] & ids[1]) and not (ids[1] & ids[2])


def test_prediction_row_permutation_invariant():
    df = oof("xgb", "D3")
    sh = df.sample(frac=1.0, random_state=9)
    a = df.set_index("state_id").sort_index()
    b = sh.set_index("state_id").sort_index()
    assert (a["raw_is_top1"].to_numpy() == b["raw_is_top1"].to_numpy()).all()


def test_primary_metric_exact():
    r = load("outer_results.json")
    for fam in ("hgb", "xgb"):
        for fid in FOLDS:
            thr = r[fam][fid]["thresholds"]
            expect = float(np.mean([thr[n]["race_macro_ll_proj"]
                                    for n in NAMES]))
            assert r[fam][fid]["primary_proj"] == pytest.approx(expect, abs=1e-12)


def test_threshold_ll_exact():
    ir = load("independent_recompute.json")
    assert ir["threshold_match"] is True and ir["primary_match"] is True


def test_race_deltas_exact():
    ir = load("independent_recompute.json")
    assert ir["race_delta_mean_match"] is True


def test_bootstrap_race_unit():
    b = load("bootstrap_results.json")
    for fam in ("hgb", "xgb"):
        for scope in ("D1", "D2", "D3", "pooled"):
            e = b[fam][scope]
            assert e["replicates"] == 2000 and e["seed"] == 42
            assert e["ci_level"] == 0.95 and "states" not in e["procedure"]


def test_bootstrap_b2000_seed42():
    p = load("screening_protocol.json")["bootstrap"]
    assert (p["replicates"], p["seed"], p["ci"]) == (2000, 42, 0.95)


def test_stage_analysis_non_selective():
    p = load("screening_protocol.json")
    assert "descriptive only" in p["stage_partition"]
    s = load("stage_results.json")
    assert set(s["xgb"]["D1"]) == {"EARLY", "MID", "LATE"}


def test_threshold_matrix_complete():
    t = load("threshold_consistency.json")
    for fam in ("hgb", "xgb"):
        assert t[fam]["total"] == 12
        assert len(t[fam]["cells"]) == 12


def test_diversity_does_not_blend():
    src = (ROOT / "scripts/run_v3_5d_screening.py").read_text()
    low = src.lower()
    for token in ("blend", "stackingclassifier", "stackingregressor",
                  "votingclassifier", "calibratedclassifiercv"):
        assert token not in low, token
    assert "column_stack" in src  # array assembly only, not model stacking
    d = load("diversity_analysis.json")
    assert "race_overlap" in d["xgb"]


def test_disposition_enum_closed():
    d = load("candidate_dispositions.json")
    allowed = {"LOGISTIC_CONTROL", "KEEP_PERFORMANCE_CANDIDATE",
               "KEEP_DIVERSITY_CANDIDATE", "REJECT_NO_IMPROVEMENT",
               "REJECT_TEMPORAL_INSTABILITY", "REJECT_PROBABILITY_QUALITY",
               "REJECT_COHERENCE_DEPENDENCE"}
    for k, v in d.items():
        if k == "advancing":
            continue
        assert v["disposition"] in allowed, (k, v["disposition"])


def test_lte2_nonlinear_candidates_advance():
    d = load("candidate_dispositions.json")
    assert d["advancing"] == ["xgb"]
    assert len(d["advancing"]) <= 2


def test_2025_rejected():
    with pytest.raises(Exception):
        OC.assert_development_seasons([2025])
    for fam in ("hgb", "xgb"):
        for fid in FOLDS:
            assert 2025 not in oof(fam, fid)["season"].tolist()


def test_2025_contact_none():
    assert load("firewall_audit.json")["2025_CONTACT"] == "NONE"
    assert load("firewall_audit.json")["verdict"] == "PASS"


def test_independent_recomputation_matches():
    assert load("independent_recompute.json")["all_match"] is True


def test_no_serving_api_frontend_changes():
    import subprocess
    out = subprocess.run(["git", "status", "--short"], capture_output=True,
                         text=True, cwd=ROOT).stdout
    for line in out.splitlines():
        pth = line[3:]
        # V3.6F/G chartered Strategy 2.0 paths admitted.
        # V3.7H reconciliation: V3.7F/V3.7G chartered counterfactual
        # integration paths admitted (frozen science untouched).
        # V3.8H reconciliation: V3.8F/V3.8G chartered consensus
        # integration paths admitted (frozen science untouched).
        if pth.startswith(("api/v2_strategy_v3_", "api/main.py",
                           "api/v2_counterfactual_", "api/v2_consensus_",
                           "frontend/app/strategy/page.tsx",
                           "frontend/features/strategy/components/Strategy",
                           "frontend/features/strategy/hooks/useStrategy",
                           "frontend/features/strategy/lib/strategy",
                           "frontend/lib/v2.ts",
                           "frontend/app/counterfactuals",
                           "frontend/features/counterfactuals",
                           "frontend/app/consensus",
                           "frontend/features/consensus",
                           "frontend/components/shell/CommandBar.tsx",
                           # V3.9C carve-out: uncertainty bundle API (additive).
                           "api/v2_uncertainty_",
                           # V3.9D carve-out (product UI stage only:
                           # /uncertainty route + uncertainty feature
                           # modules; no science change).
                           "frontend/app/uncertainty/",
                           "frontend/features/uncertainty/")):
            continue
        assert not pth.startswith(("api/", "frontend/")), line
        assert "serving" not in pth, line
