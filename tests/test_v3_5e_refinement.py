"""V3.5E controlled refinement + temporal calibration tests. No 2025."""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from raceintel.model_lab import outcomes as OC

ROOT = Path(__file__).resolve().parents[1]
RES = ROOT / "results/v3/v3_5e"
PROTO_ID = "4adf3da33b86e734e7b663c6702c64f9377c08ac4318fb5439eebd439aec38e6"
NAMES = ["is_top1", "is_top3", "is_top5", "is_top10"]
FOLDS = ("D1", "D2", "D3")


def load(name):
    return json.loads((RES / name).read_text())


def test_abcd_identities_exact():
    p = load("refinement_protocol.json")
    assert p["a_identity"] == \
        "15ca7c17146062edb5196a5de244fadd81d38562b2ca5714e58a21d4efb5efab"
    assert p["b_identity"] == \
        "e9ac34e5792a5aabba9038094a231a4a94789b481178739e46ece72457cc5289"
    assert p["c_identity"] == \
        "9dfee182215d6a56e4f19e2418b051883e9c75876418a6f4c92a05d799c7603a"
    assert p["d_protocol_identity"] == \
        "8d82448ea5888beb6dd8f54c35ebb08ba40c58bd66b652bab6f0d39dfdf78ba4"
    d = json.loads((ROOT / "results/v3/v3_5d_model_screening.json").read_text())
    assert d["advancing_candidates"] == ["xgb"]
    assert d["dispositions"]["hgb"] == "REJECT_NO_IMPROVEMENT"


def test_e_protocol_frozen_pre_fit():
    p = load("refinement_protocol.json")
    blob = json.dumps({k: v for k, v in p.items() if k != "protocol_identity"},
                      sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        p["protocol_identity"] == PROTO_ID


def test_closed_refinement_set_lte4_with_anchor():
    p = load("refinement_protocol.json")
    cfgs = p["refinement_configurations"]
    assert len(cfgs) == 4
    assert [c["id"] for c in cfgs] == ["X0", "X1", "X2", "X3"]
    assert {k: cfgs[0][k] for k in ("learning_rate", "max_depth",
                                    "min_child_weight")} == \
        {"learning_rate": 0.03, "max_depth": 3, "min_child_weight": 10}
    assert all(c["max_depth"] == 3 for c in cfgs)
    assert len({c["id"] for c in cfgs}) == 4


def test_no_broad_grid_no_other_families():
    src = (ROOT / "scripts/run_v3_5e_refinement.py").read_text()
    assert "extra_trees" not in src and "ExtraTrees" not in src
    assert "HistGradient" not in src and '"hgb"' not in src and "'hgb'" not in src
    assert "blend" not in src.lower()
    assert "Stacking" not in src and "stacking" not in src
    p = load("refinement_protocol.json")
    assert p["closed"]["hist_gradient_boosting"].endswith("closed")


def test_logistic_control_unchanged():
    p = load("refinement_protocol.json")
    assert p["control"] == {"family": "logistic_regression", "C": 0.01,
                            "penalty": "L2", "solver": "lbfgs",
                            "max_iter": 1000, "class_weight": None,
                            "random_state": 42,
                            "scope": p["control"]["scope"]}


def test_feature_threshold_projection_unchanged():
    p = load("refinement_protocol.json")
    assert p["feature_identity"]["hash"] == \
        "e054c6fb08c0832970165bcfc0e84f54b70787491af1d545b96a13977fc4c89e"
    assert p["feature_identity"]["n"] == 110
    assert p["threshold_order"] == [1, 3, 5, 10]
    assert p["projection_identity"] == "v3.5b-projection-v1"
    assert list(OC.TARGET_NAMES) == NAMES
    assert list(OC.THRESHOLD_ORDER) == [1, 3, 5, 10]


def test_shared_config_history_only_selection():
    p = load("refinement_protocol.json")
    assert "ONE XGB configuration shared" in \
        p["temporal_selection"]["shared_config"]
    assert p["temporal_selection"]["outer_validation_selects"] == "nothing"
    sel = load("selection_results.json")["inner_selection"]
    for fid in FOLDS:
        assert sel[fid]["chosen"] in ("X0", "X1", "X2", "X3")
        assert set(sel[fid]["inner_scores"]) == {"X0", "X1", "X2", "X3"}


def test_anchor_reproduction_exact():
    r = load("anchor_reproduction.json")
    assert all(r[f]["match_1e12"] for f in FOLDS)


def test_calibration_methods_exact_and_order():
    p = load("refinement_protocol.json")
    assert p["calibration_candidates"] == ["RAW", "SIGMOID", "ISOTONIC"]
    assert p["transformation_order"].startswith(
        "RAW model probabilities -> optional threshold calibration -> PAVA")
    sup = load("calibration_support.json")
    assert sup["D1"]["is_top1"]["status"] == "CALIBRATION_NOT_EVALUABLE"
    assert sup["D1"]["is_top1"]["method"] == "RAW"
    outer = load("outer_results.json")
    for fid in FOLDS:
        for n in NAMES:
            assert outer[fid]["calibration"][n]["method"] in \
                ("RAW", "SIGMOID", "ISOTONIC")


def test_calibration_admission_and_gates():
    outer = load("outer_results.json")
    for fid in ("D2", "D3"):
        for n in NAMES:
            h = outer[fid]["calibration"][n]["history_eval"]
            m = outer[fid]["calibration"][n]["method"]
            if m != "RAW":
                assert h["candidates"][m]["dll"] < -1e-4
                assert h["candidates"][m]["dbr"] <= 1e-12
                assert h["candidates"][m]["pathological"] is False


def test_top1_audit_complete():
    t = load("top1_audit.json")
    for fid in FOLDS:
        d = t["per_fold"][fid]
        assert {"delta_vs_logistic_raw", "delta_vs_logistic_proj",
                "race_counts_vs_logistic"} <= set(d)
        assert d["delta_vs_logistic_proj"] != 0.0


def test_twelve_cells_and_bootstrap():
    t = load("threshold_results.json")
    assert len(t["deltas"]["vs_logistic"]) == 12
    assert len(t["deltas"]["vs_anchor"]) == 12
    b = load("bootstrap_results.json")
    for fid in FOLDS:
        for key in ("vs_logistic", "vs_anchor"):
            assert b["per_fold"][fid][key]["replicates"] == 2000
            assert b["per_fold"][fid][key]["seed"] == 42
    assert b["pooled"]["vs_logistic"]["n_races"] == 68


def test_stage_non_selective_and_coherence():
    s = load("stage_results.json")
    assert set(s["D3"]) == {"EARLY", "MID", "LATE"}
    c = load("coherence_diagnostics.json")
    for fid in FOLDS:
        for tag in ("control", "anchor", "refined"):
            assert c[fid][tag]["n_violated_before"] >= 0


def test_single_finalist_and_recipe_manifest_immutable():
    d = load("candidate_dispositions.json")
    assert d["xgb_e"]["disposition"] in ("KEEP_PERFORMANCE_CANDIDATE",
                                         "KEEP_DIVERSITY_CANDIDATE")
    assert d["xgb_e"]["disposition"] == "KEEP_DIVERSITY_CANDIDATE"
    assert "top1" in d["xgb_e"]["top1_statement"].lower()
    r = load("final_fit_recipe.json")
    blob = json.dumps({k: v for k, v in r.items() if k != "recipe_identity"},
                      sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == r["recipe_identity"]
    assert r["training_seasons"] == [2018, 2019, 2020, 2021, 2022, 2023, 2024]
    m = load("v3_5f_execution_manifest.json")
    blob = json.dumps({k: v for k, v in m.items() if k != "manifest_identity"},
                      sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == m["manifest_identity"]
    assert m["final_recipe_identity"] == r["recipe_identity"]
    assert m["no_reselection_rule"]


def test_firewall_none():
    fw = load("firewall_audit.json")
    assert fw["2025_CONTACT"] == "NONE"
    assert 2025 not in fw["seasons_touched"]
    s = json.loads((ROOT / "results/v3/v3_5e_refinement.json").read_text())
    assert s["status_2025"] == "NONE"


def test_independent_recompute_matches():
    ir = load("independent_recompute.json")
    assert ir["all_match"] is True


def test_oof_schema_and_no_serving_changes():
    for fid in FOLDS:
        oof = pd.read_parquet(
            ROOT / f"data/v3/v3_5e/oof_xgb_e__{fid}.parquet")
        for n in NAMES:
            assert oof["target_" + n].isin([0, 1]).all()
            for col in ("raw_", "cal_", "proj_"):
                assert ((oof[col + n] >= 0.0) & (oof[col + n] <= 1.0)).all()
        assert (oof["season"] != 2025).all()
