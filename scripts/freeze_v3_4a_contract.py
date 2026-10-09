"""V3.4A: freeze the V3.4 ensemble experiment contract (one-shot writer).

No fitting, no weight search, no 2025 contact. Re-running must reproduce
the identical contract hash or fail loudly.
"""
import hashlib
import json
from pathlib import Path

CONTRACT = {
    "schema_version": "v3.4a-ensemble-experiment-contract-v1",
    "parent": {
        "tag": "v3.3-multi-model-lab",
        "commit": "563fff21f94f169097079b003816181c31227aa9",
    },
    "v3_3_freeze_identity": {
        "freeze_record_sha256": (
            "a051780776c2726ae9365c7002db80ecb1e6b17f071533dbca5a94ec3d12dc67"
        ),
        "scientific_card_sha256": (
            "1bc365efed16d6a3c2c445b595b44cbce224ae6591b3418524c654ff9ab41260"
        ),
        "conclusions": {
            "v3_1b_logistic": "STANDALONE_CHAMPION",
            "hist_gradient_boosting": "REJECT_NO_IMPROVEMENT",
            "extra_trees": "REJECT_NO_IMPROVEMENT",
            "xgboost": "KEEP_DIVERSITY_CANDIDATE (V3.4 eligible; "
                       "does NOT replace V3.1B standalone)",
        },
    },
    "scientific_question": (
        "Does XGBoost contain complementary predictive information that "
        "can be combined with the frozen V3.1B Logistic model to improve "
        "winner probability quality over Logistic alone? The burden of "
        "proof is on the ensemble. A null result is acceptable."
    ),
    "task": {
        "name": "winner",
        "label_column": "is_winner",
        "probability_semantics": "INDEPENDENT_BINARY",
        "probabilities": "RAW, never field-normalized",
    },
    "base_models": {
        "logistic": {
            "role": "frozen champion / ensemble baseline",
            "family": "logistic_regression",
            "hyperparameters": {"C": 0.01, "penalty": "l2",
                                "solver": "lbfgs", "max_iter": 1000,
                                "class_weight": None, "random_state": 42},
            "calibration": "RAW",
            "feature_arm": "ALL_84_PLUS_V3_1_DYNAMICS_CORE",
            "feature_count": 110,
            "feature_hash": ("e054c6fb08c0832970165bcfc0e84f54b70787491a"
                             "f1d545b96a13977fc4c89e"),
            "training_years": [2018, 2019, 2020, 2021, 2022, 2023, 2024],
            "v3_3_recipe_identity": (
                "ca0cd5d5f7c95e5446ae66111eff85232441023ad7be15d04a8f35e05f"
                "ea332d"
            ),
            "retraining_in_v3_4": "FORBIDDEN",
        },
        "xgboost": {
            "role": "frozen diversity candidate",
            "family": "xgboost",
            "hyperparameters": {"learning_rate": 0.03, "max_depth": 3,
                                "min_child_weight": 5, "n_estimators": 300,
                                "subsample": 0.8, "colsample_bytree": 0.8,
                                "reg_lambda": 1.0, "reg_alpha": 0.0,
                                "objective": "binary:logistic",
                                "tree_method": "hist",
                                "eval_metric": "logloss",
                                "random_state": 42, "n_jobs": 4},
            "calibration": "RAW",
            "feature_arm": "ALL_84_PLUS_V3_1_DYNAMICS_CORE",
            "feature_count": 110,
            "feature_hash": ("e054c6fb08c0832970165bcfc0e84f54b70787491a"
                             "f1d545b96a13977fc4c89e"),
            "training_years": [2018, 2019, 2020, 2021, 2022, 2023, 2024],
            "v3_3_recipe_identity": (
                "ca0cd5d5f7c95e5446ae66111eff85232441023ad7be15d04a8f35e05f"
                "ea332d"
            ),
            "retraining_in_v3_4": "FORBIDDEN",
        },
        "excluded": {
            "hist_gradient_boosting": "V3.3 REJECT_NO_IMPROVEMENT; reopening forbidden",
            "extra_trees": "V3.3 REJECT_NO_IMPROVEMENT; reopening forbidden",
        },
    },
    "base_prediction_contract": {
        "identity_join": "state_id only; row-position joins forbidden "
                         "(V3.3 row-order incident invariant)",
        "streams": {
            "logistic_oof": [
                "data/v3/v3_3c/oof_baseline__D1.parquet",
                "data/v3/v3_3c/oof_baseline__D2.parquet",
                "data/v3/v3_3c/oof_baseline__D3.parquet",
            ],
            "xgboost_oof": [
                "data/v3/v3_3d/oof_d_refined_xgboost__D1.parquet",
                "data/v3/v3_3d/oof_d_refined_xgboost__D2.parquet",
                "data/v3/v3_3d/oof_d_refined_xgboost__D3.parquet",
            ],
        },
        "aligned_development": {"n_rows": 74605, "n_races": 68,
                                "per_fold_rows": {"D1": 23577,
                                                  "D2": 24422,
                                                  "D3": 26606}},
        "semantics": "RAW INDEPENDENT_BINARY probabilities in [0, 1]; "
                     "same arm/hash for both streams",
    },
    "development_folds": {
        "D1": {"validate": [2022], "ensemble_training_history": [],
               "learned_params": "NOT_EVALUABLE (no prior OOF history); "
                                 "baseline-only fallback for stacker scoring"},
        "D2": {"validate": [2023], "ensemble_training_history": ["D1"]},
        "D3": {"validate": [2024],
               "ensemble_training_history": ["D1", "D2"]},
    },
    "alignment_contract": {
        "rule": "identity-based state_id joins only",
        "must_match": ["state_id", "target", "race_id", "driver_id",
                       "fold", "stage", "eligible row set",
                       "probability semantics"],
    },
    "admitted_methods": {
        "fixed_convex_blend": {
            "formula": "p_ensemble = (1 - w) * p_logistic + w * p_xgb",
            "bounds": [0.0, 1.0],
            "status": "ADMITTED",
        },
        "logistic_stacker": {
            "form": "logit(P(Y=1)) = b0 + b1 * logit_clip(p_logistic) "
                    "+ b2 * logit_clip(p_xgb)",
            "input_transformation": "logit with clip [1e-6, 1 - 1e-6] "
                                    "(extreme-probability mass ~0.8)",
            "estimator": "LogisticRegression",
            "regularization": "L2 fixed C=1.0 (no C search; 2-input, "
                              "large history sample; fixed beats searched "
                              "for leakage surface)",
            "solver": "lbfgs",
            "seed": 42,
            "calibration_behavior": "RAW output (no stacker calibration)",
            "status": "ADMITTED",
        },
        "calibrated_blend": {"status": "EXCLUDED (no distinct scientific "
                                       "justification; not a candidate slot)"},
    },
    "excluded_methods": {
        "large_meta_models": "overfitting risk; 2 base models",
        "neural_stackers": "no scientific need; dependency/scope cost",
        "boosted_meta_models": "no scientific need",
        "subgroup_weights": "race/driver/team/stage/track/season-specific "
                            "or per-race-optimized weights forbidden "
                            "(limited race-level sample; overfitting risk)",
        "informed_weights": "2025-informed and manual post-hoc weights forbidden",
        "mc2_fusion": "belongs to V3.8 (model x simulation consensus)",
    },
    "blend_grid": [0.0, 0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0],
    "blend_grid_policy": {
        "includes_pure_logistic": True,
        "includes_pure_xgb": True,
        "resolution": "0.1 (identify whether small XGB contribution helps; "
                      "not arbitrary weight optimization)",
        "adaptive_refinement": "FORBIDDEN (no finer grid after B results)",
    },
    "stacker_contract": {
        "training_data": "earlier-fold OOF prediction history only "
                         "(D2 stacker from D1; D3 stacker from D1+D2; "
                         "D1 NOT_EVALUABLE)",
        "forbidden": "outer-validation labels for coefficients; "
                     "2025 anywhere in training/selection",
    },
    "temporal_protocol": {
        "design": "evaluate whole preregistered fixed grid on D1/D2/D3 "
                  "(pure evaluation, no fitting: temporally safe); select "
                  "ONE final recipe only after all folds in V3.4C under "
                  "predeclared advancement rules",
        "outer_validation_selects": "NOTHING (no weights, coefficients, "
                                    "regularization, or calibration)",
        "d1_handling": "fixed blends evaluated descriptively; learned "
                       "stacker NOT_EVALUABLE, baseline-only fallback",
    },
    "metrics": {
        "primary": "race_macro_log_loss (lower better; frozen V3.1B baseline)",
        "secondary": ["brier", "roc_auc", "pr_auc", "ece", "top_1",
                      "top_3", "state_pooled_ll"],
        "diagnostics": ["EARLY_MID_LATE"],
        "selection_rule": "never on ROC/accuracy/top-1 alone",
    },
    "bootstrap": {
        "unit": "race (states never bootstrap units)",
        "replicates": 2000,
        "seed": 42,
        "ci": 0.95,
        "report": ["mean_delta", "median_delta", "improved", "worsened",
                   "ties"],
    },
    "calibration_policy": {
        "ensemble_output": "RAW (option A: simplicity; bases RAW and "
                           "near-baseline calibrated; no predeclared reason)",
        "temporal_calibration": "NOT ADMITTED in V3.4",
        "rescue_calibration": "FORBIDDEN",
    },
    "robustness_policy": {
        "neighbor_check": "winning w inspected at neighboring grid points "
                          "(+/-0.1); isolated spike = weak evidence vs "
                          "broad useful region",
        "adaptive_grid_refinement": "FORBIDDEN",
    },
    "advancement_rules": {
        "KEEP_ENSEMBLE_PRIMARY": "credible primary-LL gain + bootstrap "
                                 "support + temporal consistency + no "
                                 "probability-quality regression",
        "KEEP_ENSEMBLE_TIE_BREAK": "parity on primary with robustness/ "
                                   "simplicity justification",
        "REJECT_NO_IMPROVEMENT": "no credible pre-2025 gain over Logistic",
        "REJECT_TEMPORAL_INSTABILITY": "gains concentrated in one fold, "
                                       "absent elsewhere",
        "REJECT_PROBABILITY_QUALITY": "LL parity/gain via worse Brier/ECE",
        "REJECT_COMPLEXITY_WITHOUT_VALUE": "stacker adds nothing over best blend",
        "minimum_effect_size": "none invented; robustness + consistency decide",
    },
    "2025_status": "PREVIOUSLY REVEALED OUT-OF-TIME EVALUATION SET "
                   "(NOT an untouched holdout; individual-model results "
                   "observed in V3.3)",
    "2025_historical_context": {
        "logistic_race_macro_ll": 0.0634166678,
        "xgboost_race_macro_ll": 0.0672136469,
        "delta": 0.0037969791,
        "ci_95": [-0.003725, 0.011783],
        "usage": "static documentation ONLY; must not enter selection code",
    },
    "2025_firewall": {
        "forbidden_in_selection": ["2025 labels", "2025 Logistic predictions",
                                   "2025 XGB predictions", "2025 metrics",
                                   "2025 race outcomes",
                                   "known 2025 ensemble performance"],
        "forbidden_paths": ["data/v3/v3_1d/*2025*",
                            "data/v3/v3_3e/*"],
        "mechanism": "development-only resolver + season assertions + "
                     "ProtectedHoldoutError reuse + artifact scan + tests "
                     "proving 2025 inaccessible from selection functions",
        "final_evaluation": "frozen recipe ONLY, applied to frozen 2025 "
                            "base predictions; reported as PREVIOUSLY "
                            "REVEALED OUT-OF-TIME ENSEMBLE EVALUATION",
    },
    "final_recipe_policy": {
        "cardinality": "exactly one of NO_ENSEMBLE | one ensemble recipe",
        "recipe_spec": ["method", "base model identities",
                        "feature/prediction identities", "weight OR stacker "
                        "parameters/training procedure",
                        "probability transformation", "clipping",
                        "calibration", "seed", "semantics",
                        "development evidence", "artifact provenance"],
        "frozen_before_2025_ensemble_evaluation": True,
    },
    "null_result_policy": {
        "rule": "no credible pre-2025 improvement over Logistic -> "
                "NO_ENSEMBLE; V3.1B remains champion; no 2025 ensemble "
                "fishing; no forced V3.4E; proceed to V3.5",
    },
    "stage_plan": {
        "V3.4A": "Ensemble Landscape + Experiment Contract (this stage; "
                 "no fitting)",
        "V3.4B": "Development Ensemble Experiments (grid evaluation + "
                 "expanding-window stacker; stop: no 2025 contact)",
        "V3.4C": "Controlled Selection + Robustness (one recipe or "
                 "NO_ENSEMBLE; stop: recipe frozen before any 2025 use)",
        "V3.4D": "Final Recipe Freeze (machine-readable recipe; stop: "
                 "frozen recipe immutable)",
        "V3.4E": "Previously Revealed 2025 Ensemble Evaluation, ONLY if an "
                 "ensemble survives (stop: report as revealed, not holdout)",
        "V3.4F": "Final Validation + Freeze",
    },
    "compute_budget": {
        "development_experiment_s": 1800,
        "expectation": "minutes (base predictions exist; blends seconds; "
                       "2-input stacker cheap)",
        "retraining_base_models": "design error unless justified",
    },
    "dependency_policy": {
        "allowed": ["numpy", "pandas", "scikit-learn"],
        "new_dependencies": "none expected",
        "forbidden": ["Optuna", "LightGBM", "CatBoost", "SHAP",
                      "deep-learning frameworks"],
    },
    "seed_policy": {"seeds": [42], "bootstrap": {"replicates": 2000,
                                                 "seed": 42}},
    "test_policy": "tests/test_v3_4a_contract.py + V3.3F integrity + "
                   "relevant V3.3 alignment/metric tests; "
                   "FULL_TIER1 = NOT_REQUIRED_CONTRACT_ONLY",
    "known_limitations": [
        "2025 already revealed for base models; V3.4 cannot claim pristine holdout",
        "68-race development history; race-level sample still limited",
        "D1 has no prior OOF history: learned params NOT_EVALUABLE there",
        "two-model linear opinion pool cannot capture interactions",
        "single fixed stacker C: no regularization search by design",
        "no serving promotion in V3.4A",
    ],
}


def main() -> None:
    payload = dict(CONTRACT)
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    payload["contract_hash"] = hashlib.sha256(blob.encode()).hexdigest()
    out = Path("results/v3/v3_4a/experiment_contract.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n")
    print("contract_hash:", payload["contract_hash"])


if __name__ == "__main__":
    main()
