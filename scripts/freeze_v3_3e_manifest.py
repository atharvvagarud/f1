"""Freeze V3.3E execution manifest BEFORE revealing challenger results.

Pins A/B/C/D + recipe identities, task/feature/dataset identities,
seasons, exact XGB hyperparameters (loaded from the D artifact, never
transcribed), preprocessing, calibration, seed/threads, metric +
bootstrap + stage contracts, prediction artifact location, analysis
plan, test policy. Hashes + timestamps. No recipe changes after.

Reads only frozen contracts/recipes and V3.1D count evidence (no 2025
challenger predictions exist yet; baseline headline is accepted V3.1
evidence, already public in-repo).
"""

from __future__ import annotations

import datetime
import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from raceintel.model_lab import v3_3b_harness as H  # noqa: E402
from raceintel.model_lab import v3_dynamics_experiment as V3C  # noqa: E402


def file_hash(payload: dict, skip: str) -> str:
    inner = {k: v for k, v in payload.items() if k != skip}
    blob = json.dumps(inner, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(blob.encode()).hexdigest()


def main() -> None:
    contracts = H.verify_contracts()
    a_sha, b_sha = contracts["contract_sha"], contracts["prereg_sha"]
    c_doc = json.loads(Path(
        "results/v3/v3_3c/preregistration.json").read_text())
    d_doc = json.loads(Path(
        "results/v3/v3_3d/preregistration.json").read_text())
    assert file_hash(c_doc, "preregistration_identity") == \
        c_doc["preregistration_identity"] == \
        "a8a3d8be330013c38da2ba063ba47785467b0f96d67c004555f6fee9a4eb29a8"
    assert file_hash(d_doc, "preregistration_identity") == \
        d_doc["preregistration_identity"] == \
        "b74a9a7cb20b502bca2f05c2a071e9ed2f46312ac785194124b234d8ff94bca2"
    recipes = json.loads(Path(
        "results/v3/v3_3d/finalist_recipes.json").read_text())
    recipe_blob = json.dumps(recipes["recipes"], sort_keys=True,
                             separators=(",", ":"))
    recipe_sha = hashlib.sha256(recipe_blob.encode()).hexdigest()
    assert recipe_sha == recipes["recipe_hash"] == \
        "ca0cd5d5f7c95e5446ae66111eff85232441023ad7be15d04a8f35e05fea332d"
    assert sorted(recipes["recipes"]) == ["v3_1b_baseline", "xgboost"], \
        "finalist set is not exactly XGB (+baseline)"
    xgb = recipes["recipes"]["xgboost"]
    assert xgb["calibration_method"] == "RAW"
    assert xgb["training_years"] == list(range(2018, 2025))
    assert xgb["hyperparameters"]["learning_rate"] == 0.03
    assert xgb["hyperparameters"]["max_depth"] == 3
    assert xgb["hyperparameters"]["min_child_weight"] == 5

    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_84 = tuple(canonical_predictive_names())
    names_110 = H.feature_names_110(names_84)
    feature_contract = H.check_feature_contract(names_84, names_110)

    v3_1d = json.loads(Path(
        "results/v3/v3_1d_race_dynamics_holdout_and_freeze.json").read_text())
    manifest = {
        "schema_version": "v3.3e-execution-manifest-v1",
        "frozen_at_utc": datetime.datetime.now(
            datetime.timezone.utc).isoformat(),
        "a_contract_sha": a_sha,
        "b_prereg_sha": b_sha,
        "c_prereg_sha": c_doc["preregistration_identity"],
        "d_prereg_sha": d_doc["preregistration_identity"],
        "d_finalist_recipe_sha": recipe_sha,
        "parent_commit": "197979d40af0c9dbf90667781d9c83e41613b047",
        "task_identity": {"task": "winner", "label": "is_winner",
                          "semantics": "INDEPENDENT_BINARY",
                          "probabilities": "RAW, never field-normalized"},
        "feature_identity": {"arm": H.ARM_PRIMARY, "count": 110,
                             "hash": feature_contract["feature_hash"]},
        "dataset_identity": {
            "matrix_content_hash": "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db",
            "dynamics_content_sha": V3C.V3_DYNAMICS_LOGICAL_SHA},
        "training_seasons": list(range(2018, 2025)),
        "holdout_season": 2025,
        "holdout_expectation": {
            "eligible": v3_1d["arm_b"]["n_eligible"],
            "races": v3_1d["arm_b"]["n_races"],
            "baseline_race_macro_ll": v3_1d["arm_b"]["race_macro"][
                "log_loss"]},
        "model_family": "xgboost",
        "exact_hyperparameters": dict(xgb["hyperparameters"]),
        "preprocessing_identity": xgb["preprocessing"],
        "calibration_method": "RAW",
        "random_seed": H.SEED,
        "thread_policy": dict(H.THREAD_POLICY),
        "library_versions": H.library_versions(),
        "metric_contract": {"primary": "race_macro_log_loss",
                            "secondary": ["brier", "roc_auc", "pr_auc",
                                          "ece", "top_1", "top_3",
                                          "state_pooled_ll"]},
        "bootstrap_policy": {"unit": "race", "replicates": 2000,
                             "seed": 42, "ci": 0.95},
        "stage_contract": "race_progress_frac thirds EARLY/MID/LATE",
        "prediction_artifact_location": "data/v3/v3_3e/"
                                        "pred_xgb_final_2025.parquet "
                                        "(ignored)",
        "model_artifact_location": "data/v3/v3_3e/final_xgb_arm_b.joblib "
                                   "(ignored, research evidence only)",
        "analysis_plan": "rebuild from frozen prediction artifact; "
                         "baseline vs XGB race-macro LL + secondaries + "
                         "paired race bootstrap + stage/calibration/top-k/"
                         "diversity transfer; final disposition + "
                         "standalone + V3.4 eligibility",
        "test_policy": "tests/test_v3_3e_holdout.py + A/B/C/D tests; "
                       "FULL_TIER1 = NOT_REQUIRED_HOLDOUT_EVALUATION_ONLY",
        "no_retry": "after HOLDOUT_REVEALED, no recipe change or "
                    "regeneration from a different configuration",
    }
    blob = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest["manifest_identity"] = hashlib.sha256(
        blob.encode()).hexdigest()
    dest = Path("results/v3/v3_3e/execution_manifest.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        raise RuntimeError(
            "execution manifest already frozen; refusing overwrite")
    dest.write_text(json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print(f"manifest_identity: {manifest['manifest_identity']}")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
