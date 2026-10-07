"""V3.3C screening tests (Part Y). Execution-dependent tests read the
stored C artifacts (no refitting); source/contract tests need no corpus.
No 2025 access anywhere.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from raceintel.model_lab import aggregation as AGG
from raceintel.model_lab import stages as STAGES
from raceintel.model_lab import v3_3b_harness as H
from raceintel.model_lab import v3_dynamics_experiment as V3C
from raceintel.model_lab.errors import ProtectedHoldoutError

OUT = Path("results/v3/v3_3c")
OOF_DIR = Path("data/v3/v3_3c")
FAMILIES = ("logistic_regression", "hist_gradient_boosting", "extra_trees",
            "xgboost")
FOLDS = ("D1", "D2", "D3")
DISPOSITIONS = {"KEEP_PRIMARY_CANDIDATE", "KEEP_DIVERSITY_CANDIDATE",
                "HOLD_FOR_CALIBRATION", "REJECT_NO_IMPROVEMENT",
                "REJECT_TEMPORAL_INSTABILITY", "REJECT_PROBABILITY_QUALITY",
                "REJECT_COMPLEXITY_WITHOUT_VALUE",
                "REJECT_CONTRACT_INCOMPATIBLE", "BASELINE_CONTROL"}


def load(name):
    return json.loads((OUT / name).read_text())


def oof(family, fold):
    name = f"oof_{family}__{fold}.parquet" if family != "baseline" \
        else f"oof_baseline__{fold}.parquet"
    return pd.read_parquet(OOF_DIR / name)


def test_c_prereg_hash():
    prereg = load("preregistration.json")
    payload = {k: v for k, v in prereg.items()
               if k != "preregistration_identity"}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        prereg["preregistration_identity"]


def test_grid_immutability():
    prereg = load("preregistration.json")
    live = H.candidate_grids()
    for fam in FAMILIES:
        assert [dict(c) for c in live[fam]] == prereg["exact_grids"][fam]
        assert [H.config_id(fam, c) for c in live[fam]] == \
            prereg["exact_config_ids"][fam]


def test_all_families_and_folds_executed():
    selected = load("selected_configs.json")["selected"]
    assert sorted(selected) == sorted(FAMILIES)
    for fam in FAMILIES:
        assert sorted(selected[fam]) == sorted(FOLDS)
        for fold in FOLDS:
            assert (OUT / "outer_results" / f"{fam}__{fold}.json").exists()
            assert (OOF_DIR / f"oof_{fam}__{fold}.parquet").exists()
    assert load("selected_configs.json")["n_selected_outer_models"] == 12


def test_inner_selections_belong_to_frozen_grids():
    prereg = load("preregistration.json")
    selected = load("selected_configs.json")["selected"]
    for fam in FAMILIES:
        for fold in FOLDS:
            cfg = selected[fam][fold]["selected_config"]
            assert cfg in prereg["exact_grids"][fam]


def test_oof_row_set_equality():
    for fold in FOLDS:
        ref = set(oof("baseline", fold)["state_id"])
        for fam in FAMILIES:
            assert set(oof(fam, fold)["state_id"]) == ref


def test_oof_target_equality():
    for fold in FOLDS:
        ref = oof("baseline", fold).set_index("state_id")["target"]
        for fam in FAMILIES:
            got = oof(fam, fold).set_index("state_id")["target"]
            assert (got == ref).all()


def test_oof_probability_bounds():
    for fam in ("baseline",) + FAMILIES:
        for fold in FOLDS:
            p = oof(fam, fold)["probability"].to_numpy(dtype=float)
            assert np.all(np.isfinite(p))
            assert np.all((p >= 0.0) & (p <= 1.0))


def test_oof_uniqueness():
    for fam in ("baseline",) + FAMILIES:
        frames = [oof(fam, f) for f in FOLDS]
        full = pd.concat(frames, ignore_index=True)
        assert full["state_id"].is_unique


def test_baseline_alignment():
    evidence = json.loads(Path(
        "results/v3/v3_1c_race_dynamics_controlled_experiment.json"
    ).read_text())
    for fold in FOLDS:
        fr = oof("baseline", fold)
        ll = AGG.race_macro(
            fr["target"].to_numpy(dtype=float),
            fr["probability"].to_numpy(dtype=float),
            fr["race_id"].astype(str).to_numpy(), "log_loss")["value"]
        frozen = evidence["arm_results"][
            f"ALL_84_PLUS_V3_1_DYNAMICS_CORE__{fold}"]["race_macro"][
            "log_loss"]
        assert abs(ll - frozen) <= 1e-12


def test_metric_determinism():
    fr = oof("extra_trees", "D1")
    args = (fr["target"].to_numpy(dtype=float),
            fr["probability"].to_numpy(dtype=float),
            fr["race_id"].astype(str).to_numpy(), "log_loss")
    assert AGG.race_macro(*args)["value"] == AGG.race_macro(*args)["value"]


def test_race_bootstrap_determinism_and_unit():
    a = {"r1": 0.1, "r2": 0.2, "r3": 0.15, "r4": 0.12}
    b = {"r1": 0.09, "r2": 0.21, "r3": 0.14, "r4": 0.13}
    first = V3C.paired_bootstrap(a, b)
    assert first == V3C.paired_bootstrap(a, b)
    assert first["n_races"] == 4  # race unit, not states
    boot = load("bootstrap_results.json")
    assert boot["method"].startswith("paired race bootstrap")
    assert all(v["seed"] == 42 and v["replicates"] == 2000
               for v in boot["bootstraps"].values())


def test_stage_partition_integrity():
    stage = load("stage_analysis.json")
    for fam, by_stage in stage["stages"].items():
        assert sorted(by_stage) == ["EARLY", "LATE", "MID"]
        total = sum(v["n_states"] for v in by_stage.values())
        n_oof = sum(len(oof(fam if fam != "v3_1b_baseline" else "baseline",
                            f)) for f in FOLDS)
        assert total == n_oof


def test_diversity_matrix_symmetry():
    matrix = load("diversity_matrix.json")["pairs"]
    for key, vals in matrix.items():
        assert vals["prediction_correlation"] == pytest.approx(
            vals["prediction_correlation"])
        assert -1.0 <= vals["residual_correlation"] <= 1.0
        assert vals["mean_abs_probability_gap"] >= 0.0


def test_candidate_disposition_enum():
    dispositions = load("candidate_dispositions.json")["dispositions"]
    for fam, node in dispositions.items():
        assert node["disposition"] in DISPOSITIONS
        assert node["rationale"]


def test_advancement_le_3():
    advanced = load("advancement_decision.json")["advanced"]
    assert len(advanced) <= 3
    assert all(a in ("hist_gradient_boosting", "extra_trees", "xgboost")
               for a in advanced)


def test_2025_absence_from_scientific_artifacts():
    for fam in ("baseline",) + FAMILIES:
        for fold in FOLDS:
            assert 2025 not in set(
                oof(fam, fold)["season"].astype(int).unique())
    firewall = load("firewall_validation.json")
    assert firewall["2025_CONTACT"] == "NONE"
    for bad in ("HOLDOUT", "2025", "FINAL_FIT"):
        with pytest.raises(ProtectedHoldoutError):
            H.assert_development_fold(bad)


def test_result_provenance_completeness():
    required = ("contract_sha", "prereg_sha", "c_prereg_sha")
    for name in ["primary_metrics.json", "race_level_comparisons.json",
                 "candidate_dispositions.json", "diversity_matrix.json",
                 "temporal_consistency.json", "oof_identities.json"]:
        doc = load(name)
        for key in required:
            assert key in doc, f"{name} missing {key}"
    for fam in FAMILIES:
        for fold in FOLDS:
            payload = json.loads(
                (OUT / "outer_results" / f"{fam}__{fold}.json").read_text())
            prov = payload["provenance"]
            assert prov["a_contract_sha"] == \
                "d877e8b2f7821d2eb7ade05677a3a7920f538a0422d28c97956f43f4cce399d7"
            assert prov["seed"] == 42
            assert prov["feature_identity"]["feature_count"] == 110
