"""V3.3D refinement/calibration tests (Part AA). Execution-dependent
tests read stored D artifacts (no refitting); gate tests need no corpus.
HGB can never execute in D. No 2025 access anywhere.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from raceintel.model_lab import aggregation as AGG
from raceintel.model_lab import v3_3b_harness as H
from raceintel.model_lab import v3_3d_refinement as D
from raceintel.model_lab import v3_dynamics_experiment as V3C
from raceintel.model_lab.errors import (
    ExperimentConfigError,
    ProtectedHoldoutError,
)

OUT = Path("results/v3/v3_3d")
OOF_DIR = Path("data/v3/v3_3d")
C_OOF = Path("data/v3/v3_3c")
FOLDS = ("D1", "D2", "D3")
FINAL_DISPOSITIONS = {"KEEP_PRIMARY_CANDIDATE", "KEEP_DIVERSITY_CANDIDATE",
                      "REJECT_NO_IMPROVEMENT", "REJECT_TEMPORAL_INSTABILITY",
                      "REJECT_PROBABILITY_QUALITY",
                      "REJECT_COMPLEXITY_WITHOUT_VALUE"}


def load(name):
    return json.loads((OUT / name).read_text())


def test_d_prereg_hash():
    prereg = load("preregistration.json")
    payload = {k: v for k, v in prereg.items()
               if k != "preregistration_identity"}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        prereg["preregistration_identity"]


def test_candidate_set_exactly_et_xgb():
    assert sorted(D.D_FAMILIES) == ["extra_trees", "xgboost"]
    assert load("preregistration.json")["candidate_set"] == [
        "extra_trees", "xgboost"]


def test_hgb_cannot_execute():
    with pytest.raises(ExperimentConfigError):
        D.require_d_family("hist_gradient_boosting")
    with pytest.raises(ExperimentConfigError):
        D.require_d_family("logistic_regression")
    with pytest.raises(ExperimentConfigError):
        D.build_d_estimator("hist_gradient_boosting", {})


def test_refinement_grid_le_6_new_configs_per_family():
    grids = D.d_grids()
    c_grids = H.candidate_grids()
    for fam in D.D_FAMILIES:
        assert len(grids[fam]) <= 6
        d_ids = [D.d_config_id(fam, c) for c in grids[fam]]
        c_ids = [H.config_id(fam, c) for c in c_grids[fam]]
        assert not (set(d_ids) & set(c_ids))


def test_grid_immutability():
    frozen = load("preregistration.json")["refinement_grids"]
    for fam in D.D_FAMILIES:
        assert [D.d_config_id(fam, c) for c in D.d_grids()[fam]] == \
            [g["id"] for g in frozen[fam]]


def test_refinement_selection_inner_only():
    # selection keys belong to frozen D grids; outer LL stored separately
    selected = load("selected_refinements.json")["selected"]
    frozen = load("preregistration.json")["refinement_grids"]
    for fam in D.D_FAMILIES:
        for fold in FOLDS:
            key = selected[fam][fold]["selected_key"]
            assert key in [g["id"] for g in frozen[fam]]


def test_calibration_training_excludes_outer_validation():
    # calibration frames derive from inner splits inside outer TRAIN only
    import inspect
    src = inspect.getsource(D.calibration_frames)
    assert "resolve_inner_splits" in src
    assert "validation_metadata" not in src
    for fam in D.D_FAMILIES:
        for fold in FOLDS:
            node = load(f"d_result_{fam}__{fold}.json")
            assert node["fold"] == fold
            prov = node["provenance"]
            assert list(prov["fold_identity"]["validation_seasons"]) == \
                {"D1": [2022], "D2": [2023], "D3": [2024]}[fold]


def test_calibration_uses_temporal_predictions():
    src = __import__("inspect").getsource(D.select_calibration)
    assert "_split_calfit_select" in src
    for fam in D.D_FAMILIES:
        for fold in FOLDS:
            node = load(f"d_result_{fam}__{fold}.json")["calibration"]
            assert node["calfit_races"] >= 1 and node["calselect_races"] >= 1


def test_isotonic_and_sigmoid_support_gates():
    tiny = pd.DataFrame({"probability": [0.1, 0.2, 0.3],
                         "target": [0.0, 1.0, 0.0]})
    assert D.support_audit(tiny, "isotonic")["status"] == \
        "NOT_RUN_INSUFFICIENT_SUPPORT"
    assert D.support_audit(tiny, "sigmoid")["status"] == \
        "NOT_RUN_INSUFFICIENT_SUPPORT"


def test_calibration_selection_rule():
    # winners need >1e-4 LL gain and no Brier harm; tested on real nodes
    for fam in D.D_FAMILIES:
        for fold in FOLDS:
            node = load(f"d_result_{fam}__{fold}.json")
            method = node["calibration_method"]
            assert method in ("RAW", "sigmoid", "isotonic")
            outcome = node["calibration"]["outcome"]
            if method != "RAW":
                assert outcome[method]["ll_gain_vs_raw"] > 1e-4
                assert outcome[method]["brier_gap_vs_raw"] <= 1e-12


def test_oof_alignment():
    for fam in D.D_FAMILIES:
        for fold in FOLDS:
            for kind in ("refined", "calibrated"):
                fr = pd.read_parquet(
                    OOF_DIR / f"oof_d_{kind}_{fam}__{fold}.parquet")
                base = pd.read_parquet(
                    C_OOF / f"oof_baseline__{fold}.parquet")
                assert set(fr["state_id"]) == set(base["state_id"])
                assert (fr.set_index("state_id")["target"]
                        == base.set_index("state_id")["target"]).all()


def test_raw_vs_calibrated_identity():
    for fam in D.D_FAMILIES:
        for fold in FOLDS:
            raw = pd.read_parquet(
                OOF_DIR / f"oof_d_refined_{fam}__{fold}.parquet")
            cal = pd.read_parquet(
                OOF_DIR / f"oof_d_calibrated_{fam}__{fold}.parquet")
            method = load(f"d_result_{fam}__{fold}.json")[
                "calibration_method"]
            assert raw["probability"].equals(cal["probability"]) == \
                (method == "RAW")


def test_probability_bounds():
    for fam in D.D_FAMILIES:
        for fold in FOLDS:
            for kind in ("refined", "calibrated"):
                p = pd.read_parquet(
                    OOF_DIR / f"oof_d_{kind}_{fam}__{fold}.parquet")[
                    "probability"].to_numpy(float)
                assert np.all(np.isfinite(p))
                assert np.all((p >= 0.0) & (p <= 1.0))


def test_race_bootstrap_race_unit():
    a = {"r1": 0.1, "r2": 0.2, "r3": 0.15}
    b = {"r1": 0.09, "r2": 0.21, "r3": 0.14}
    assert V3C.paired_bootstrap(a, b) == V3C.paired_bootstrap(a, b)
    boot = load("bootstrap_results.json")
    assert boot["method"].startswith("paired race bootstrap")
    assert all(v["seed"] == 42 and v["replicates"] == 2000
               for v in boot["bootstraps"].values())


def test_diversity_alignment():
    pairs = load("diversity_matrix.json")["pairs"]
    assert "baseline__vs__extra_trees" in pairs
    assert "baseline__vs__xgboost" in pairs
    assert "extra_trees__vs__xgboost" in pairs
    for v in pairs.values():
        assert -1.0 <= v["residual_correlation"] <= 1.0


def test_final_disposition_enum():
    dispositions = load("final_dispositions.json")["dispositions"]
    assert sorted(dispositions) == ["extra_trees", "xgboost"]
    for node in dispositions.values():
        assert node["disposition"] in FINAL_DISPOSITIONS
        assert "HOLD_FOR_CALIBRATION" != node["disposition"]


def test_finalists_le_2():
    finalists = load("advancement_decision.json")["finalists"]
    assert len(finalists) <= 2
    assert set(finalists) <= {"extra_trees", "xgboost"}


def test_finalist_recipe_completeness_and_hash():
    doc = load("finalist_recipes.json")
    required = ("model_family", "hyperparameters", "preprocessing",
                "feature_identity", "training_years", "random_seed",
                "thread_policy", "calibration_method",
                "prediction_semantics")
    for fam in doc["recipes"]:
        if fam == "v3_1b_baseline":
            continue
        for key in required:
            assert key in doc["recipes"][fam], f"{fam} missing {key}"
        if doc["recipes"][fam]["calibration_method"] != "RAW":
            assert "calibration_training_procedure" in doc["recipes"][fam]
    blob = json.dumps(doc["recipes"], sort_keys=True,
                      separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == doc["recipe_hash"]


def test_2025_absence():
    for fam in D.D_FAMILIES:
        for fold in FOLDS:
            for kind in ("refined", "calibrated"):
                fr = pd.read_parquet(
                    OOF_DIR / f"oof_d_{kind}_{fam}__{fold}.parquet")
                assert 2025 not in set(fr["season"].astype(int).unique())
    assert load("firewall_validation.json")["2025_CONTACT"] == "NONE"
    for bad in ("HOLDOUT", "2025", "FINAL_FIT"):
        with pytest.raises(ProtectedHoldoutError):
            H.assert_development_fold(bad)


def test_result_provenance():
    for name in ["primary_metrics.json", "race_comparisons.json",
                 "final_dispositions.json", "diversity_matrix.json",
                 "oof_identities.json", "finalist_recipes.json"]:
        doc = load(name)
        for key in ("contract_sha", "prereg_sha", "c_prereg_sha",
                    "d_prereg_sha"):
            assert key in doc, f"{name} missing {key}"
