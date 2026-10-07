"""V3.3A: freeze the V3.3 multi-model experiment contract (one-shot writer)."""
import hashlib
import json
from pathlib import Path

CONTRACT = {
    "schema_version": "v3.3a-experiment-contract-v1",
    "parent": {
        "tag": "v3.2-monte-carlo-2",
        "commit": "197979d40af0c9dbf90667781d9c83e41613b047",
    },
    "task": {
        "name": "winner",
        "kind": "BINARY",
        "label_column": "is_winner",
        "eligibility_mask": "eligible_is_winner",
        "probability_semantics": "INDEPENDENT_BINARY",
        "rule": "binary per-driver P(is_winner | causal state at T); "
                "never normalized across the field; no field softmax",
    },
    "baseline": {
        "stage": "V3.1B",
        "estimator": "LogisticRegression",
        "hyperparameters": {"C": 0.01, "penalty": "l2", "solver": "lbfgs",
                             "max_iter": 1000, "class_weight": None,
                             "random_state": 42},
        "feature_set": "ALL_84_PLUS_V3_1_DYNAMICS_CORE",
        "feature_count": 110,
        "calibration": "RAW",
        "artifact": "data/v3/v3_1d/final_model_arm_b.joblib",
        "artifact_sha256": "9a1aac515d12c4e86ac369977392f74394cf7f6853b8e89d948bcdec28f58960",
        "reproduction": "load local artifact OR re-run frozen spec "
                        "(deterministic rerun proven max-abs-diff 0.0)",
    },
    "feature_arms": {
        "primary": "ALL_84_PLUS_V3_1_DYNAMICS_CORE",
        "primary_count": 110,
        "diagnostic_control": "ALL_84",
        "diagnostic_count": 84,
        "rule": "no model-specific feature sets except preprocessing "
                "mathematically required by the family, inside pipelines",
    },
    "candidate_families": [
        {"family": "logistic_regression",
         "role": "linear control (V3.1B is a member)",
         "implementation": "sklearn.linear_model.LogisticRegression",
         "new_dependency": False},
        {"family": "hist_gradient_boosting",
         "role": "stagewise additive trees; early_stopping forbidden "
                  "(M4 precedent: no validation-driven training)",
         "implementation": "sklearn.ensemble.HistGradientBoostingClassifier",
         "new_dependency": False},
        {"family": "extra_trees",
         "role": "fully-randomized bagging; diversity hypothesis",
         "implementation": "sklearn.ensemble.ExtraTreesClassifier",
         "new_dependency": False},
        {"family": "xgboost",
         "role": "regularized boosting, distinct loss behavior vs HGB "
                  "(M4: materially better raw LL); tests whether "
                  "regularized boosting closes the gap on the 110-col arm",
         "implementation": "xgboost.XGBClassifier==3.2.0",
         "new_dependency": False},
    ],
    "excluded_families": [
        {"family": "lightgbm", "reason": "new dependency; redundant third "
         "boosting family; unjustified"},
        {"family": "catboost", "reason": "new dependency; redundant boosting "
         "family; unjustified"},
        {"family": "random_forest",
         "reason": "redundant with extra_trees (M5: ET >= RF on LL all "
                    "folds but D2; M6 tuned-ET lineage exists)"},
        {"family": "neural_networks",
         "reason": "no scientific question requires them; dependency/compute "
                    "cost unjustified; portfolio-driven admission forbidden"},
        {"family": "ranking_listwise",
         "reason": "contract-incompatible without a preregistered "
                    "calibration bridge to INDEPENDENT_BINARY; deferred "
                    "research, not admitted to B/C screening"},
    ],
    "temporal_folds": {
        "D1": {"train": [2018, 2019, 2020, 2021], "validate": [2022],
               "train_eligible": 88123, "val_eligible": 23577},
        "D2": {"train": [2018, 2019, 2020, 2021, 2022], "validate": [2023],
               "train_eligible": 111700, "val_eligible": 24422},
        "D3": {"train": [2018, 2019, 2020, 2021, 2022, 2023],
               "validate": [2024],
               "train_eligible": 136122, "val_eligible": 26606},
        "inner": {"D1-I1": [[2018, 2019, 2020], [2021]],
                  "D2-I1": [[2018, 2019, 2020], [2021]],
                  "D2-I2": [[2018, 2019, 2020, 2021], [2022]],
                  "D3-I1": [[2018, 2019, 2020], [2021]],
                  "D3-I2": [[2018, 2019, 2020, 2021], [2022]],
                  "D3-I3": [[2018, 2019, 2020, 2021, 2022], [2023]]},
        "FINAL_FIT": {"train": [2018, 2019, 2020, 2021, 2022, 2023, 2024]},
        "resolver": "raceintel.model_lab.splits.get_split; M0 count audits "
                     "enforced on materialize",
    },
    "holdout_policy": {
        "season": 2025,
        "mechanism": "ProtectedHoldoutError; HOLDOUT/2025 resolvers raise "
                      "without allow_protected_holdout=True; "
                      "assert_no_holdout_request in experiment harnesses",
        "forbidden_before_holdout": ["training", "tuning", "selection",
                                     "calibration fitting", "elimination",
                                     "feature decisions",
                                     "exploratory candidate 2025 metrics"],
    },
    "metrics": {
        "primary": "race_macro_log_loss",
        "primary_rule": "simple mean of per-race log loss; lower is better; "
                         "race is the statistical unit",
        "secondary": ["brier", "roc_auc", "pr_auc", "ece", "top_1", "top_3"],
        "diagnostic_scopes": ["state_pooled", "EARLY_MID_LATE"],
        "selection_rule": "never on ROC AUC or accuracy alone; probability "
                           "quality required",
    },
    "aggregation": {
        "headline": "race_macro (equal-per-race mean)",
        "fold_summary": "per-fold values + mean/std/min/max/range "
                         "(aggregation.aggregate_folds)",
        "implementation": "raceintel.model_lab.aggregation",
    },
    "calibration_policy": {
        "primary": "RAW candidate probabilities",
        "allowed": ["none (RAW)", "sigmoid/Platt", "isotonic"],
        "fit_data": "inner-train or dedicated calibration split inside the "
                     "outer-train history ONLY; never outer-validation; "
                     "never 2025",
        "selection": "calibrated variant must beat RAW on mean inner "
                      "race-macro LL beyond 1e-4 tie tolerance AND not "
                      "worsen mean Brier (M-calibration precedent: RAW won)",
        "rule": "no calibration to rescue an otherwise weak model",
    },
    "preprocessing_policy": {
        "frozen": "median/mode imputation, StandardScaler numerics, "
                   "most-frequent booleans unscaled, MISSING-sentinel + "
                   "train-vocabulary one-hot categoricals; fit TRAIN only",
        "family_adjustments": "inside deterministic pipelines only "
                               "(e.g. tree families may skip scaling; "
                               "scaling must not change selection)",
        "forbidden": "fitting on validation/holdout; zero-fill; global "
                      "imputation",
    },
    "hyperparameter_policy": {
        "style": "small preregistered grids; no Optuna/unrestricted search",
        "max_configurations_per_family": 12,
        "objective": "mean inner race-macro log loss (simple mean over "
                      "inner folds)",
        "tie_tolerance": 1e-6,
        "tie_break": "simpler/more regularized wins (LogReg: smaller C; "
                      "trees: larger min_samples_leaf, bounded depth, "
                      "smaller max_features)",
        "selection_scope": "one configuration per outer fold "
                            "(procedure estimate, not a global vector)",
        "seeds": [42],
    },
    "compute_budget": {
        "matrix_states": 189420,
        "reference_fit_s_per_fold": {"logistic_regression": 1,
                                     "hist_gradient_boosting": 3,
                                     "xgboost": 2, "extra_trees": 14},
        "max_fits_per_family": 100,
        "max_wall_per_family_s": 3600,
        "max_total_wall_s": 7200,
        "hardware": "M4 MacBook Air 16GB, CPU only, n_jobs<=4",
        "rule": "no cloud compute for family screening",
    },
    "statistical_comparison": {
        "unit": "race",
        "delta": "per-race race-macro LL (candidate minus V3.1B)",
        "method": "paired race-level bootstrap, seed 42, B=2000, "
                   "95% percentile CI on mean delta",
        "report": ["mean delta", "95% CI", "races improved",
                    "races worsened", "ties"],
        "forbidden": "driver-state observations as independent bootstrap "
                      "units",
    },
    "temporal_consistency": {
        "report": "fold-wise D1/D2/D3 deltas vs baseline for every candidate",
        "classes": ["CONSISTENT_IMPROVEMENT", "MIXED",
                     "CONSISTENT_REGRESSION"],
        "rule": "no every-fold-must-improve veto; instability is material "
                 "evidence",
    },
    "diversity_contract": {
        "purpose": "prepare V3.4 ensemble; a non-winning model may still "
                    "be a diversity candidate",
        "inputs": "aligned out-of-fold predictions (D1/D2/D3 validation "
                   "seasons)",
        "analyses": ["prediction correlation", "residual/error correlation",
                      "per-race delta correlation", "top-1 disagreement",
                      "high-confidence disagreement",
                      "per-race/per-stage improvement attribution",
                      "probability spread differences"],
        "rule": "no ensembling in V3.3",
    },
    "oof_prediction_contract": {
        "identity_columns": ["state_id", "race_id", "season", "round_no",
                             "driver_id", "fold", "stage", "target",
                             "baseline_probability", "candidate_probability"],
        "types": "PredictionResult BINARY_PROBABILITY / INDEPENDENT_BINARY; "
                  "state_id-keyed frames (to_frame/from_frame); parquet "
                  "persistence under ignored data/v3/v3_3*/",
        "convention": "existing Model Lab identity columns + "
                       "synchronized top-k adapter; never normalized",
    },
    "candidate_dispositions": [
        "KEEP_PRIMARY_CANDIDATE", "KEEP_DIVERSITY_CANDIDATE",
        "HOLD_FOR_CALIBRATION", "REJECT_NO_IMPROVEMENT",
        "REJECT_TEMPORAL_INSTABILITY", "REJECT_PROBABILITY_QUALITY",
        "REJECT_COMPLEXITY_WITHOUT_VALUE", "REJECT_CONTRACT_INCOMPATIBLE",
    ],
    "advancement_policy": {
        "max_non_baseline_finalists": 3,
        "plus_baseline": True,
        "evidence": "pre-2025 ONLY (D1/D2/D3 + inner tuning)",
        "rule": "do not send every tested model to the holdout",
    },
    "artifact_contract": {
        "metadata": ["model family", "implementation/version", "task",
                      "feature contract/hash", "training seasons",
                      "fold policy", "hyperparameters", "preprocessing",
                      "calibration", "random seed", "code version",
                      "dataset identity", "artifact SHA256"],
        "note": "no final trained candidate artifacts in V3.3A",
    },
    "reproducibility": {
        "random_state": 42,
        "threads": "n_jobs<=4 where applicable; thread policy recorded",
        "ordering": "stable input + feature ordering (canonical registry "
                     "order + contract order)",
        "versions": "sklearn==1.8.0, xgboost==3.2.0 captured per artifact",
        "caveat": "exact binary reproducibility may differ across "
                   "library versions/platforms; rerun-identity asserted "
                   "within the frozen environment",
    },
    "explainability_compatibility": {
        "logistic_regression": "coefficients native; Phase-8 compatible",
        "hist_gradient_boosting": "permutation/native importance; adapter "
                                   "cost low",
        "extra_trees": "impurity/permutation importance; adapter cost low",
        "xgboost": "gain/cover importance + SHAP-optional (shap NOT a "
                    "dependency; no SHAP requirement)",
        "rule": "no rejection solely for explanation cost; cost recorded",
    },
    "serving_compatibility": {
        "status": "research-first; no promotion in V3.3",
        "implications": "joblib artifacts via FrozenWinnerPredictor pattern; "
                         "tree ensembles larger memory/latency than LogReg; "
                         "no new serving dependencies admitted in A "
                         "(sklearn + xgboost already in footprint)",
    },
    "firewall_2025": {
        "season": 2025,
        "status": "FINAL HOLDOUT, sealed during V3.3A-D",
        "enforcement": "ProtectedHoldoutError + development-only resolvers "
                        "+ output season scans in harnesses",
    },
    "known_limitations": [
        "single 24-race 2025 holdout at the end (CIs honest, not overstated)",
        "thin/medium history-bin descriptives persist from V3.1",
        "uncalibrated boosting raw LL historically weak (M4) — "
        "calibration policy is the remedy path, not feature changes",
        "listwise/ranking deferred (contract bridge required)",
    ],
}


def main() -> None:
    payload = dict(CONTRACT)
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["contract_hash"] = hashlib.sha256(blob.encode()).hexdigest()
    out = Path("results/v3/v3_3a/experiment_contract.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print("contract_hash:", payload["contract_hash"])


if __name__ == "__main__":
    main()
