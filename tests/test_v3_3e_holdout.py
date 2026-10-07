"""V3.3E one-shot holdout tests (Part Y). Analysis tests read frozen
artifacts (no fitting, no 2025 refit). Manifest/recipe/audit tests need
no holdout contact. 2025 predictions are READ (frozen evidence), never
regenerated here.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from raceintel.model_lab import v3_3b_harness as H
from raceintel.model_lab import v3_dynamics_experiment as V3C
from raceintel.model_lab.errors import ProtectedHoldoutError

OUT = Path("results/v3/v3_3e")
PRED = Path("data/v3/v3_3e/pred_xgb_final_2025.parquet")
BASELINE_PRED = Path(
    "data/v3/v3_1d/pred_final_ALL_84_PLUS_V3_1_DYNAMICS_CORE_2025.parquet")
FINAL_DISPOSITIONS = {"KEEP_PRIMARY_CANDIDATE", "KEEP_DIVERSITY_CANDIDATE",
                      "REJECT_NO_IMPROVEMENT", "REJECT_TEMPORAL_INSTABILITY",
                      "REJECT_PROBABILITY_QUALITY",
                      "REJECT_COMPLEXITY_WITHOUT_VALUE"}


def load(name):
    return json.loads((OUT / name).read_text())


def test_execution_manifest_frozen_before_holdout_artifact():
    manifest = load("execution_manifest.json")
    payload = {k: v for k, v in manifest.items()
               if k != "manifest_identity"}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        manifest["manifest_identity"]
    assert manifest["manifest_identity"] == \
        "34188a8598db8c308ba288d2fc9ed8f8ec7db00c555869962affb1b77cb51c50"


def test_recipe_equality_with_d():
    recipes = json.loads(Path(
        "results/v3/v3_3d/finalist_recipes.json").read_text())
    blob = json.dumps(recipes["recipes"], sort_keys=True,
                      separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        recipes["recipe_hash"] == \
        load("execution_manifest.json")["d_finalist_recipe_sha"]
    audit = load("recipe_audit.json")
    assert audit["recipe_sha"] == recipes["recipe_hash"]
    spec = audit["estimator_spec"]
    assert spec["learning_rate"] == 0.03 and spec["max_depth"] == 3 \
        and spec["min_child_weight"] == 5
    assert spec["n_estimators"] == 300 and spec["random_state"] == 42


def test_training_seasons_exclude_2025():
    fit = load("final_fit_record.json")
    assert 2025 not in fit["training_seasons"]
    assert fit["training_seasons"] == list(range(2018, 2025))
    assert fit["no_2025_in_train"] is True


def test_holdout_exactly_2025():
    holdout = load("holdout_identity.json")
    assert holdout["season"] == 2025
    assert holdout["n_eligible"] == 26692 and holdout["n_races"] == 24


def test_110_feature_identity():
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_110 = H.feature_names_110(tuple(canonical_predictive_names()))
    assert len(names_110) == 110
    assert H.check_feature_contract(
        tuple(canonical_predictive_names()),
        names_110)["feature_hash"] == \
        load("execution_manifest.json")["feature_identity"]["hash"]
    fit = load("final_fit_record.json")
    assert fit["feature_hash"] == \
        load("execution_manifest.json")["feature_identity"]["hash"]


def test_baseline_row_alignment():
    base = pd.read_parquet(BASELINE_PRED)
    holdout = load("holdout_identity.json")
    assert len(base) == holdout["n_eligible"] and base["state_id"].is_unique
    assert set(base["state_id"]) == set(
        pd.read_parquet(PRED)["state_id"])


def test_xgb_row_alignment():
    xgb = pd.read_parquet(PRED)
    assert len(xgb) == 26692 and xgb["state_id"].is_unique
    assert xgb["race_id"].nunique() == 24
    assert sorted(xgb["season"].astype(int).unique()) == [2025]


def test_probability_bounds():
    xp = pd.read_parquet(PRED, columns=["probability"])[
        "probability"].to_numpy(float)
    bp = pd.read_parquet(BASELINE_PRED, columns=["y_pred"])[
        "y_pred"].to_numpy(float)
    for p in (xp, bp):
        assert np.all(np.isfinite(p)) and np.all((p >= 0) & (p <= 1))


def test_prediction_artifact_hash():
    identity = load("prediction_identity.json")
    assert hashlib.sha256(PRED.read_bytes()).hexdigest() == \
        identity["sha256"] == \
        load("holdout_revealed.json")["prediction_sha256"]


def test_holdout_result_deterministic_analysis():
    result = load("holdout_result.json")
    payload = {k: v for k, v in result.items() if k != "result_hash"}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == result["result_hash"]
    assert abs(result["primary_metrics"]["baseline_ll"]
               - 0.0634166678) <= 1e-9


def test_race_bootstrap_race_unit():
    a = {"r1": 0.1, "r2": 0.2, "r3": 0.15}
    b = {"r1": 0.09, "r2": 0.21, "r3": 0.14}
    assert V3C.paired_bootstrap(a, b) == V3C.paired_bootstrap(a, b)
    boot = load("holdout_result.json")["bootstrap"]
    assert boot["seed"] == 42 and boot["replicates"] == 2000
    assert len(load("holdout_result.json")["race_comparison"][
        "per_race_delta"]) == 24


def test_stage_partition():
    stage = load("holdout_result.json")["stage_analysis"]
    assert sorted(stage["stages"]) == ["EARLY", "LATE", "MID"]
    total = sum(v["n_states"] for v in stage["stages"].values())
    assert total == 26692


def test_no_calibration_fit():
    recipe = json.loads(Path(
        "results/v3/v3_3d/finalist_recipes.json").read_text())[
        "recipes"]["xgboost"]
    assert recipe["calibration_method"] == "RAW"
    result = load("holdout_result.json")
    assert result["calibration"]["xgboost"]["ece"] is not None
    # RAW only: no calibrator metadata may exist
    fit = load("final_fit_record.json")
    assert "calibrator" not in json.dumps(fit).lower()


def test_no_field_normalization():
    xgb = pd.read_parquet(PRED)
    sums = xgb.groupby("race_id")["probability"].sum()
    assert not np.allclose(sums.to_numpy(), 1.0), \
        "probabilities must not sum to 1 per race"
    assert (sums > 5.0).all(), \
        "independent binary sums (~50) must be far from 1.0"


def test_final_disposition_enum():
    result = load("holdout_result.json")
    assert result["final_disposition"] in FINAL_DISPOSITIONS


def test_standalone_decision_enum():
    assert load("holdout_result.json")["standalone_decision"] in ("YES",
                                                                  "NO")


def test_v3_4_eligibility_enum():
    assert load("holdout_result.json")["v3_4_eligibility"] in ("YES", "NO")


def test_no_retry_attestation():
    revealed = load("holdout_revealed.json")
    assert revealed["HOLDOUT_REVEALED"] is True
    assert "no recipe change" in revealed["attestation"]
    result = load("holdout_result.json")
    assert result["holdout_revealed"] is True
    assert "no_retry" in result["no_retry_attestation"] or \
        "no regeneration" in result["no_retry_attestation"]


def test_provenance_completeness():
    for name in ["holdout_result.json", "v3_3_scientific_card.json",
                 "prediction_identity.json", "final_fit_record.json",
                 "holdout_identity.json", "baseline_holdout_identity.json"]:
        doc = load(name)
        assert "contract_sha" in doc, f"{name} missing contract_sha"
    assert load("holdout_result.json")["finalist_recipe_identity"] == \
        load("execution_manifest.json")["d_finalist_recipe_sha"]


def test_development_resolvers_still_sealed():
    for bad in ("HOLDOUT", "2025"):
        with pytest.raises(ProtectedHoldoutError):
            H.assert_development_fold(bad)
