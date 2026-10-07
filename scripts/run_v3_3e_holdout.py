"""V3.3E one-shot holdout execution (Parts D-H).

Loads the frozen manifest + D recipe artifact DIRECTLY (no
transcription), audits exact equality, verifies the V3.1B 2025
reference, resolves the holdout contract, fits XGB ONCE on 2018-2024,
predicts 2025 ONCE, persists predictions BEFORE any metric analysis,
and writes HOLDOUT_REVEALED. Refuses to overwrite (no-retry gate).
Analysis lives in scripts/analyze_v3_3e.py (frozen predictions only).
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import warnings
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from raceintel.model_lab import data as DATA  # noqa: E402
from raceintel.model_lab import preprocessing as PRE  # noqa: E402
from raceintel.model_lab import splits as SPLITS  # noqa: E402
from raceintel.model_lab import v3_3b_harness as H  # noqa: E402
from raceintel.model_lab import v3_dynamics_experiment as V3C  # noqa: E402
from raceintel.model_lab.errors import (  # noqa: E402
    ExperimentConfigError,
    InvalidPredictionError,
)

OUT = Path("results/v3/v3_3e")
DATA_OUT = Path("data/v3/v3_3e")
PRED_PATH = DATA_OUT / "pred_xgb_final_2025.parquet"
MODEL_PATH = DATA_OUT / "final_xgb_arm_b.joblib"
REVEALED_PATH = OUT / "holdout_revealed.json"
BASELINE_PRED = Path(
    "data/v3/v3_1d/pred_final_ALL_84_PLUS_V3_1_DYNAMICS_CORE_2025.parquet")
EXPECTED_BASELINE_LL = 0.0634166678


def write(name: str, payload: dict) -> Path:
    dest = OUT / name
    dest.write_text(json.dumps(payload, indent=1, sort_keys=True,
                               default=str) + "\n")
    return dest


def main() -> None:
    if PRED_PATH.exists() or REVEALED_PATH.exists():
        raise RuntimeError(
            "V3.3E no-retry gate: holdout prediction artifact or reveal "
            "marker already exists; refusing regeneration")
    manifest = json.loads((OUT / "execution_manifest.json").read_text())
    payload = {k: v for k, v in manifest.items() if k != "manifest_identity"}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        manifest["manifest_identity"], "manifest hash mismatch"
    contracts = H.verify_contracts()
    assert manifest["a_contract_sha"] == contracts["contract_sha"]
    assert manifest["b_prereg_sha"] == contracts["prereg_sha"]

    # -- Part D: pre-reveal recipe audit (artifact-driven) ---------------
    recipes = json.loads(Path(
        "results/v3/v3_3d/finalist_recipes.json").read_text())
    recipe_blob = json.dumps(recipes["recipes"], sort_keys=True,
                             separators=(",", ":"))
    assert hashlib.sha256(recipe_blob.encode()).hexdigest() == \
        recipes["recipe_hash"] == manifest["d_finalist_recipe_sha"], \
        "finalist recipe mismatch"
    assert sorted(recipes["recipes"]) == ["v3_1b_baseline", "xgboost"]
    recipe = recipes["recipes"]["xgboost"]
    assert recipe["model_family"] == "xgboost"
    assert recipe["training_years"] == list(range(2018, 2025))
    assert recipe["calibration_method"] == "RAW"
    assert recipe["random_seed"] == 42
    assert recipe["thread_policy"]["n_jobs"] == 4
    assert recipe["prediction_semantics"] in (
        "RAW", "RAW INDEPENDENT_BINARY; never normalized")
    assert "model_lab.preprocessing" in recipe["preprocessing"]
    assert manifest["task_identity"]["semantics"] == "INDEPENDENT_BINARY"
    assert manifest["task_identity"]["probabilities"] == \
        "RAW, never field-normalized"
    hyp = dict(recipe["hyperparameters"])
    assert hyp["learning_rate"] == 0.03 and hyp["max_depth"] == 3 \
        and hyp["min_child_weight"] == 5
    fixed = H.candidate_registry()["xgboost"]["fixed_parameters"]
    assert fixed["n_estimators"] == 300
    assert H.library_versions() == manifest["library_versions"], \
        "library drift since D"
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_84 = tuple(canonical_predictive_names())
    names_110 = H.feature_names_110(names_84)
    fc = H.check_feature_contract(names_84, names_110)
    assert fc["feature_hash"] == manifest["feature_identity"]["hash"]
    assert fc["feature_hash"] == recipe["feature_identity"]["hash"]
    audit = {"recipe_sha": recipes["recipe_hash"],
             "checks": "family/seasons/hyperparameters/preprocessing/"
                       "calibration/seed/threads/semantics/features/"
                       "libraries all exact",
             "estimator_spec": {**{k: fixed[k] for k in
                                   ("objective", "eval_metric",
                                    "n_estimators", "subsample",
                                    "colsample_bytree", "reg_alpha",
                                    "reg_lambda", "tree_method", "n_jobs",
                                    "random_state")},
                                **{k: hyp[k] for k in
                                   ("learning_rate", "max_depth",
                                    "min_child_weight")}}}
    write("recipe_audit.json", {**contracts, **audit})
    print("recipe audit: EXACT match with D artifact.", flush=True)

    # -- holdout contract (one-shot explicit access) ----------------------
    augmented, plain = V3C.load_joined_frame()
    hold_ds = V3C.materialize_v3_holdout(
        augmented, allow_protected_holdout=True)
    hold_frame = augmented.frame.loc[hold_ds.y_validation.index].copy()
    seasons = set(int(s) for s in hold_frame["season"].astype(int).unique())
    assert seasons == {2025}, f"holdout seasons {seasons}"
    assert hold_frame["state_id"].is_unique
    missing = [c for c in names_110 if c not in hold_frame.columns]
    assert not missing, f"missing CORE/features: {missing[:5]}"
    X_hold = hold_frame.loc[:, list(names_110)].copy()
    holdout_identity = {
        "season": 2025, "n_states": int(len(hold_frame)),
        "n_eligible": int(hold_ds.validation_counts["eligible"]),
        "n_races": int(hold_ds.validation_metadata["race_id"].nunique()),
        "state_hash": hashlib.sha256(
            "\n".join(sorted(hold_frame["state_id"])).encode()).hexdigest(),
        "feature_hash": fc["feature_hash"]}
    assert holdout_identity["n_eligible"] == \
        manifest["holdout_expectation"]["eligible"] == 26692
    assert holdout_identity["n_races"] == \
        manifest["holdout_expectation"]["races"] == 24
    write("holdout_identity.json", {**contracts, **holdout_identity})
    print(f"holdout identity: {holdout_identity['n_eligible']} states, "
          f"{holdout_identity['n_races']} races.", flush=True)

    # -- Part E: baseline 2025 reference (recover, never retrain) ---------
    base = pd.read_parquet(BASELINE_PRED)
    assert sorted(base["season"].astype(int).unique()) == [2025]
    assert len(base) == 26692 and base["state_id"].is_unique
    assert set(base["state_id"]) == set(hold_frame["state_id"]), \
        "baseline/XGB holdout row-set mismatch"
    from raceintel.model_lab import aggregation as AGG
    yb = base["y_true"].to_numpy(dtype=float)
    pb = base["y_pred"].to_numpy(dtype=float)
    rb = base["race_id"].astype(str).to_numpy()
    base_ll = AGG.race_macro(yb, pb, rb, "log_loss")["value"]
    assert abs(base_ll - EXPECTED_BASELINE_LL) <= 1e-9, \
        f"baseline identity failure: {base_ll}"
    assert abs(base_ll - manifest["holdout_expectation"][
        "baseline_race_macro_ll"]) <= 1e-9
    write("baseline_holdout_identity.json",
          {**contracts, "n_states": len(base), "n_races": 24,
           "race_macro_ll": base_ll, "source": str(BASELINE_PRED),
           "note": "recovered canonical V3.1B predictions; not retrained"})
    print(f"baseline 2025 reference: LL={base_ll:.10f} verified.",
          flush=True)

    # -- Part G: final XGB fit (2018-2024 ONLY) -----------------------------
    train_ds = V3C.materialize_v3_final_fit(
        augmented, V3C.ARM_B, names_110)
    assert 2025 not in set(int(s) for s in
                           train_ds.train_metadata["season"].astype(int))
    schema = DATA.feature_schema(augmented.frame, list(names_110))
    fit_record: dict = {"training_seasons": list(range(2018, 2025))}
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        t0 = time.perf_counter()
        fitted = PRE.fit_preprocessor(train_ds.X_train, schema)
        prep_s = time.perf_counter() - t0
        Z_train = fitted.transform(train_ds.X_train)
        t0 = time.perf_counter()
        estimator = H.build_estimator("xgboost", {
            "learning_rate": hyp["learning_rate"],
            "max_depth": hyp["max_depth"],
            "min_child_weight": hyp["min_child_weight"]})
        y_tr = np.asarray(train_ds.y_train.astype(float)).ravel()
        estimator.fit(Z_train, y_tr)
        fit_s = time.perf_counter() - t0
    assert 1 in list(estimator.classes_)
    fit_record.update({
        "training_rows": int(train_ds.train_counts["eligible"]),
        "training_races": int(train_ds.train_metadata["race_id"].nunique()),
        "transformed_dim": int(fitted.output_dim),
        "preprocessing_fit_seconds": round(prep_s, 3),
        "estimator_fit_seconds": round(fit_s, 3),
        "hyperparameters": audit["estimator_spec"],
        "library_versions": H.library_versions(),
        "seed": 42, "thread_policy": dict(H.THREAD_POLICY),
        "feature_hash": fc["feature_hash"],
        "no_2025_in_train": True})
    DATA_OUT.mkdir(parents=True, exist_ok=True)
    joblib.dump({"estimator": estimator, "preprocessor": fitted,
                 "recipe_sha": recipes["recipe_hash"],
                 "manifest_identity": manifest["manifest_identity"],
                 "feature_names": list(names_110)}, MODEL_PATH)
    model_sha = hashlib.sha256(MODEL_PATH.read_bytes()).hexdigest()
    fit_record["model_artifact"] = str(MODEL_PATH)
    fit_record["model_artifact_sha256"] = model_sha
    write("final_fit_record.json", {**contracts, **fit_record})
    print(f"final fit: {fit_record['training_rows']} rows, "
          f"{fit_s:.1f}s.", flush=True)

    # -- Part H: predict ONCE, validate, persist BEFORE analysis ------------
    Z_hold = fitted.transform(X_hold)
    proba = np.asarray(estimator.predict_proba(Z_hold))[
        :, H._positive_index(estimator)]
    if not np.all(np.isfinite(proba)):
        raise InvalidPredictionError("non-finite holdout probabilities")
    if np.any((proba < 0.0) | (proba > 1.0)):
        raise InvalidPredictionError("holdout probabilities outside [0, 1]")
    if len(proba) != len(hold_frame):
        raise InvalidPredictionError("holdout row count mismatch")
    pred = pd.DataFrame({
        "state_id": list(hold_frame["state_id"]),
        "season": hold_frame["season"].astype(int).to_numpy(),
        "race_id": hold_frame["race_id"].astype(str).to_numpy(),
        "driver_id": hold_frame["driver_id"].astype(str).to_numpy(),
        "target": np.asarray(
            hold_ds.y_validation.astype(float).to_numpy()),
        "fold": ["HOLDOUT"] * len(hold_frame),
        "feature_arm": [H.ARM_PRIMARY] * len(hold_frame),
        "model_family": ["xgboost"] * len(hold_frame),
        "model_config_id": ["FINAL lr=0.03;max_depth=3;min_child_weight=5"]
        * len(hold_frame),
        "probability": np.asarray(proba, dtype=float)})
    assert pred["state_id"].is_unique
    assert list(pred["state_id"]) == list(hold_frame["state_id"])
    pred.to_parquet(PRED_PATH, index=False)
    pred_sha = hashlib.sha256(PRED_PATH.read_bytes()).hexdigest()
    write("prediction_identity.json",
          {**contracts, "path": str(PRED_PATH), "sha256": pred_sha,
           "n_rows": len(pred),
           "note": "immutable V3.3 XGB holdout result; persisted "
                   "before metric analysis"})

    # -- Part I: no-retry gate -------------------------------------------------
    import datetime
    revealed = {"HOLDOUT_REVEALED": True,
                "revealed_at_utc": datetime.datetime.now(
                    datetime.timezone.utc).isoformat(),
                "prediction_sha256": pred_sha,
                "model_sha256": model_sha,
                "recipe_sha": recipes["recipe_hash"],
                "manifest_identity": manifest["manifest_identity"],
                "attestation": "no recipe change or regeneration from a "
                               "different configuration after this point; "
                               "the prediction hash above is authoritative"}
    REVEALED_PATH.write_text(json.dumps(revealed, indent=1,
                                        sort_keys=True) + "\n")
    print(f"HOLDOUT_REVEALED = TRUE; prediction sha {pred_sha[:16]}…",
          flush=True)


if __name__ == "__main__":
    main()
