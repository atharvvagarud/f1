"""Freeze V3.5E refinement protocol (before ANY E fit).

Pins A/B/C/D identities, D XGB anchor, closed 4-config XGB neighborhood,
temporal history-only selection, calibration candidates + support gates +
admission rule, transformation order, metrics, dispositions, finalist rule,
2025 firewall, final-fit recipe schema, artifact layout, compute budget.
Hashes the document. Immutable after the first E fit.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

OUT = Path("results/v3/v3_5e")


def main() -> None:
    d_proto = json.loads(
        Path("results/v3/v3_5d/screening_protocol.json").read_text())
    assert d_proto["protocol_identity"] == \
        "8d82448ea5888beb6dd8f54c35ebb08ba40c58bd66b652bab6f0d39dfdf78ba4"
    d_sum = json.loads(
        Path("results/v3/v3_5d_model_screening.json").read_text())
    assert d_sum["advancing_candidates"] == ["xgb"]
    assert d_sum["dispositions"]["hgb"] == "REJECT_NO_IMPROVEMENT"
    assert d_sum["dispositions"]["xgb"] == "KEEP_DIVERSITY_CANDIDATE"

    spec = {
        "schema_version": "v3.5e-refinement-protocol-v1",
        "parent": {"commit": "3cbd28470ffa211bd754d4262eb10d66d149bf00",
                   "tag": "v3.4-ensemble"},
        "a_identity":
            "15ca7c17146062edb5196a5de244fadd81d38562b2ca5714e58a21d4efb5efab",
        "b_identity":
            "e9ac34e5792a5aabba9038094a231a4a94789b481178739e46ece72457cc5289",
        "c_identity":
            "9dfee182215d6a56e4f19e2418b051883e9c75876418a6f4c92a05d799c7603a",
        "d_protocol_identity":
            "8d82448ea5888beb6dd8f54c35ebb08ba40c58bd66b652bab6f0d39dfdf78ba4",
        "feature_identity": {
            "arm": "ALL_84_PLUS_V3_1_DYNAMICS_CORE", "n": 110,
            "hash": "e054c6fb08c0832970165bcfc0e84f54b70787491af1d545b96a13977fc4c89e"},
        "projection_identity": "v3.5b-projection-v1",
        "task": "ordered_cumulative_finish_thresholds",
        "threshold_order": [1, 3, 5, 10],
        "target_names": ["is_top1", "is_top3", "is_top5", "is_top10"],
        "control": {
            "family": "logistic_regression",
            "C": 0.01, "penalty": "L2", "solver": "lbfgs",
            "max_iter": 1000, "class_weight": None, "random_state": 42,
            "scope": "four independent binary models, one per threshold; "
                     "frozen, never tuned or retrained for selection"},
        "d_anchor": {
            "family": "xgboost",
            "id": "X0",
            "grid": {"learning_rate": 0.03, "max_depth": 3,
                     "min_child_weight": 10},
            "fixed": {"objective": "binary:logistic", "eval_metric": "logloss",
                      "n_estimators": 300, "subsample": 0.8,
                      "colsample_bytree": 0.8, "reg_alpha": 0.0,
                      "reg_lambda": 1.0, "tree_method": "hist", "n_jobs": 4,
                      "random_state": 42},
            "disposition": "KEEP_DIVERSITY_CANDIDATE",
            "note": "D-selected on every outer fold; HGB closed, never reopened"},
        "closed": {"hist_gradient_boosting": "D REJECT_NO_IMPROVEMENT; closed",
                   "logistic_regression": "frozen control, not refined"},
        "refinement_configurations": [
            {"id": "X0", "role": "ANCHOR",
             "learning_rate": 0.03, "max_depth": 3, "min_child_weight": 10,
             "n_estimators": 300},
            {"id": "X1", "role": "CAPACITY",
             "learning_rate": 0.03, "max_depth": 3, "min_child_weight": 10,
             "n_estimators": 500},
            {"id": "X2", "role": "REGULARIZED",
             "learning_rate": 0.03, "max_depth": 3, "min_child_weight": 15,
             "n_estimators": 300},
            {"id": "X3", "role": "SLOWER",
             "learning_rate": 0.02, "max_depth": 3, "min_child_weight": 10,
             "n_estimators": 500}],
        "refinement_fixed": {"objective": "binary:logistic",
                             "eval_metric": "logloss",
                             "subsample": 0.8, "colsample_bytree": 0.8,
                             "reg_alpha": 0.0, "reg_lambda": 1.0,
                             "tree_method": "hist", "n_jobs": 4,
                             "random_state": 42},
        "refinement_scope": "tree count / learning rate / regularization only; "
                            "no max_depth search; no new families; no blending",
        "temporal_selection": {
            "mechanism": "frozen M6 expanding-window inner splits "
                         "(inner_splits.resolve_inner_splits), outer TRAIN "
                         "history only",
            "score": "mean over inner folds of [mean over 4 thresholds of "
                     "race-macro LL], per outer fold",
            "shared_config": "ONE XGB configuration shared across all four "
                             "thresholds (no per-threshold selection)",
            "outer_validation_selects": "nothing",
            "top1_outer_selection": "forbidden",
            "tie_break": "differences <= 1e-6 prefer X0 anchor, then "
                         "lower-complexity (300-tree before 500-tree), then "
                         "preregistered order X0<X2<X1<X3"},
        "calibration_candidates": ["RAW", "SIGMOID", "ISOTONIC"],
        "calibration_scope": "per threshold; one common method preferred; "
                             "never mixed on outer-validation evidence",
        "calibration_fit": "outer TRAIN history only: inner-OOS predictions "
                           "of the selected config; earlier inner fold(s) fit "
                           "calibrator, later inner fold evaluates; final "
                           "calibrator refit on pooled inner-OOS; applied to "
                           "outer validation once; in-sample predictions "
                           "never used as OOS evidence",
        "calibration_layout": {
            "D1": "one inner fold only: no fit/select split possible, "
                  "CALIBRATION_NOT_EVALUABLE, RAW",
            "D2": "fit on D2-I1 OOS, select on D2-I2 OOS, refit pooled I1+I2",
            "D3": "fit on pooled D3-I1+I2 OOS, select on D3-I3 OOS, refit "
                  "pooled I1+I2+I3"},
        "calibration_support_gates": {
            "min_states": 1000, "min_races": 10, "min_positives": 20,
            "min_negatives": 20, "min_seasons": 1,
            "else": "CALIBRATION_NOT_EVALUABLE, RAW"},
        "calibration_admission_rule": {
            "ll_improvement": "> 1e-4 history-eval log-loss improvement",
            "brier": "no worse than 1e-12 tolerance",
            "pathology": "SIGMOID needs finite params and positive "
                         "coefficient; ISOTONIC needs outer exact-0/1 "
                         "fraction <= 0.5",
            "outer_validation_reversal": "forbidden",
            "note": "calibration replaces RAW for a fold only if all gates "
                    "pass on training history"},
        "transformation_order": "RAW model probabilities -> optional "
                                "threshold calibration -> PAVA coherence "
                                "projection -> PROJECTED_COHERENT output",
        "primary_metric": "mean_race_macro_log_loss_over_4_thresholds; "
                          "authoritative: candidate PROJECTED minus Logistic "
                          "PROJECTED; lower better",
        "secondary_metrics": ["brier", "ece", "state_pooled_ll"],
        "top1_guard": "top1 is a required safety/quality diagnostic reported "
                      "per fold and pooled; broad/material top1 regression "
                      "forbids KEEP_PERFORMANCE_CANDIDATE but may permit "
                      "KEEP_DIVERSITY_CANDIDATE with explicit statement; "
                      "top1 never overrides the primary metric",
        "bootstrap": {"unit": "race", "replicates": 2000, "seed": 42,
                      "ci": 0.95,
                      "estimands": ["refined-PROJECTED minus Logistic "
                                    "PROJECTED", "refined-PROJECTED minus D "
                                    "anchor PROJECTED"]},
        "stage_analysis": "frozen EARLY/MID/LATE via stages.stage_partition; "
                          "descriptive only; no stage-based tuning",
        "dispositions": ["LOGISTIC_CONTROL", "KEEP_PERFORMANCE_CANDIDATE",
                         "KEEP_DIVERSITY_CANDIDATE", "REJECT_NO_IMPROVEMENT",
                         "REJECT_TEMPORAL_INSTABILITY",
                         "REJECT_PROBABILITY_QUALITY", "REJECT_TOP1_WEAKNESS",
                         "REJECT_CALIBRATION_INSTABILITY"],
        "finalist_rule": "at most ONE nonlinear final recipe; no ensemble; "
                         "poor F never reselects (no-reselection rule)",
        "final_config_rule": "majority vote across D1/D2/D3 selected "
                             "configs; ties broken by preregistered order "
                             "X0<X2<X1<X3; an X0 win means refinement added "
                             "nothing over the anchor",
        "final_calibration_rule": "RAW unless the same non-RAW method is "
                                  "admitted on every evaluable fold for a "
                                  "threshold; per-threshold methods recorded "
                                  "in the recipe; MIXED/UNSTABLE stability "
                                  "forces RAW",
        "firewall_2025": "NONE (dev seasons 2018-2024 only + tripwire + "
                         "ProtectedHoldoutError; no 2025 targets, predictions, "
                         "prevalence, metrics, calibration, or selection)",
        "final_fit_recipe_schema": ["model_family", "four_threshold_structure",
                                    "xgb_hyperparameters", "feature_identity",
                                    "preprocessing", "training_seasons",
                                    "threshold_order", "calibration_method",
                                    "calibration_fitting_protocol",
                                    "projection_identity",
                                    "transformation_order", "seed", "threading",
                                    "library_versions", "prediction_schema",
                                    "eval_metrics_2025", "disposition_policy"],
        "immutability": "frozen before first E fit",
        "compute_budget": "96 inner + 12 outer binary fits; calibration is "
                          "transforms only; no search expansion",
        "fit_budget": {"inner": 96, "outer": 12, "thresholds": 4,
                       "configs": 4,
                       "note": "6 inner folds (1+2+3) x 4 cfg x 4 thr; "
                               "3 outer x 4 thr; calibration reuses inner OOS"},
    }
    assert len(spec["refinement_configurations"]) == 4
    assert spec["refinement_configurations"][0]["id"] == "X0"
    blob = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    digest = hashlib.sha256(blob.encode()).hexdigest()
    spec["protocol_identity"] = digest
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / "refinement_protocol.json"
    dest.write_text(json.dumps(spec, indent=1, sort_keys=True) + "\n")
    print("E protocol identity:", digest)


if __name__ == "__main__":
    main()
