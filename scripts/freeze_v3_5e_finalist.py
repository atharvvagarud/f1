"""Freeze V3.5E finalist decision + final-fit recipe + F manifest (PRE-2025).

Applies the preregistered final_config_rule (majority vote, X0<X2<X1<X3
tie-break) and final_calibration_rule (same non-RAW method on every
evaluable fold, else RAW). Records the qualitative disposition with explicit
top1 statement. No 2025 contact. Immutable once written.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

RES = Path("results/v3/v3_5e")


def sha(payload: dict) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> None:
    sel = json.loads((RES / "selection_results.json").read_text())
    outer = json.loads((RES / "outer_results.json").read_text())
    boots = json.loads((RES / "bootstrap_results.json").read_text())
    proto = json.loads((RES / "refinement_protocol.json").read_text())
    cal_res = json.loads((RES / "calibration_results.json").read_text())

    chosen = [outer[f]["selected_config"] for f in ("D1", "D2", "D3")]
    assert chosen == [sel["inner_selection"][f]["chosen"] for f in
                      ("D1", "D2", "D3")]
    order = ["X0", "X2", "X1", "X3"]
    final_cfg = max(set(chosen),
                    key=lambda c: (chosen.count(c), -order.index(c)))
    assert final_cfg == "X2", chosen
    cfg = next(c for c in proto["refinement_configurations"]
               if c["id"] == final_cfg)

    evaluable = ["D2", "D3"]
    cal_method = {}
    for n in ("is_top1", "is_top3", "is_top5", "is_top10"):
        ms = [outer[f]["calibration"][n]["method"] for f in evaluable]
        cal_method[n] = ms[0] if ms[0] != "RAW" and ms[0] == ms[1] else "RAW"
    assert cal_method == {"is_top1": "RAW", "is_top3": "RAW",
                          "is_top5": "SIGMOID", "is_top10": "RAW"}, cal_method

    pooled_log = boots["pooled"]["vs_logistic"]
    pooled_anc = boots["pooled"]["vs_anchor"]
    assert pooled_log["ci_hi"] < 0 and pooled_anc["ci_hi"] < 0

    dispositions = {
        "LOGISTIC_CONTROL": {
            "disposition": "LOGISTIC_CONTROL",
            "role": "frozen control; V3.5 champion unless F overturns"},
        "xgb_anchor": {"disposition": "SUPERSEDED_BY_REFINEMENT",
                       "note": "D anchor X0 retained as reference only; "
                               "E refinement improves on it pooled "
                               f"({pooled_anc['mean_delta']:.6f}, CI "
                               f"[{pooled_anc['ci_lo']:.6f}, "
                               f"{pooled_anc['ci_hi']:.6f}])"},
        "xgb_e": {
            "disposition": "KEEP_DIVERSITY_CANDIDATE",
            "final_config": final_cfg,
            "calibration": dict(cal_method),
            "primary_evidence":
                f"pooled PROJECTED delta vs Logistic "
                f"{pooled_log['mean_delta']:.6f} CI "
                f"[{pooled_log['ci_lo']:.6f}, {pooled_log['ci_hi']:.6f}]",
            "top1_statement": "EXPLICIT WEAKNESS: top1 race-macro LL "
                              "regresses vs Logistic on D1 (+0.0031) and D3 "
                              "(+0.0031) while improving on D2 (-0.0036); "
                              "top1 race majorities are mixed (10/12, 13/9, "
                              "16/8). Broad/material top1 regression forbids "
                              "KEEP_PERFORMANCE_CANDIDATE; diversity "
                              "advancement only.",
            "why_not_performance": "top1 guard policy blocks "
                                   "KEEP_PERFORMANCE_CANDIDATE",
            "why_advance": "pooled primary CI excludes zero vs Logistic and "
                           "vs anchor; refinement never worsens any fold vs "
                           "anchor; LATE-stage strength preserved; "
                           "probability/coherence quality acceptable",
            "f_eligibility": True},
    }
    (RES / "candidate_dispositions.json").write_text(json.dumps(
        dispositions, indent=1, sort_keys=True) + "\n")

    import xgboost
    import sklearn
    import pandas as pd
    import numpy as np
    recipe = {
        "schema_version": "v3.5e-final-fit-recipe-v1",
        "model_family": "xgboost",
        "four_threshold_structure": "four independent binary models, one "
                                    "per threshold, order [top1, top3, top5, "
                                    "top10]",
        "xgb_hyperparameters": {
            "learning_rate": cfg["learning_rate"],
            "max_depth": cfg["max_depth"],
            "min_child_weight": cfg["min_child_weight"],
            "n_estimators": cfg["n_estimators"],
            **proto["refinement_fixed"]},
        "feature_identity": dict(proto["feature_identity"]),
        "preprocessing": "frozen TRAIN-only median/mode imputation + "
                         "StandardScaler (Model Lab PRE.fit_preprocessor)",
        "training_seasons": [2018, 2019, 2020, 2021, 2022, 2023, 2024],
        "threshold_order": [1, 3, 5, 10],
        "calibration_method": dict(cal_method),
        "calibration_fitting_protocol": "top5 SIGMOID (Platt logit eps 1e-6) "
            "refit on pooled D3-inner OOS (I1+I2+I3) X2 predictions from "
            "2018-2023 history only; all other thresholds RAW; history-only, "
            "no outer-validation or 2025 evidence",
        "projection_identity": "v3.5b-projection-v1",
        "transformation_order": proto["transformation_order"],
        "seed": 42, "threading": {"n_jobs": 4, "tree_method": "hist"},
        "library_versions": {"xgboost": xgboost.__version__,
                             "sklearn": sklearn.__version__,
                             "pandas": pd.__version__,
                             "numpy": np.__version__},
        "prediction_schema": ["state_id", "season", "race_id", "driver_id",
                              "raw_is_top1", "raw_is_top3", "raw_is_top5",
                              "raw_is_top10", "cal_is_top1", "cal_is_top3",
                              "cal_is_top5", "cal_is_top10", "proj_is_top1",
                              "proj_is_top3", "proj_is_top5",
                              "proj_is_top10"],
        "eval_metrics_2025": ["primary race-macro LL over 4 thresholds",
                              "per-threshold LL", "brier", "ece",
                              "projection diagnostics",
                              "race bootstrap B2000 seed42", "stage analysis",
                              "top1 audit"],
        "disposition_policy_2025": "no-reselection: poor F keeps Logistic "
                                   "champion; no retune, blend, or "
                                   "recalibration",
        "eval_terminology_2025": "PREVIOUSLY REVEALED "
            "OUT-OF-TIME OUTCOME EVALUATION",
    }
    recipe["recipe_identity"] = sha(
        {k: v for k, v in recipe.items() if k != "recipe_identity"})
    (RES / "final_fit_recipe.json").write_text(json.dumps(
        recipe, indent=1, sort_keys=True) + "\n")

    manifest = {
        "schema_version": "v3.5f-execution-manifest-v1",
        "final_recipe_identity": recipe["recipe_identity"],
        "control_identity": proto["c_identity"],
        "allowed_operation_2025": "fit frozen recipe on 2018-2024 once; "
                                  "predict 2025 once; report frozen metrics",
        "target_loader": "frozen D9 labels via outcomes.build_outcome_frame",
        "feature_loader": "frozen 110-arm via v3_dynamics_experiment",
        "identity_alignment": "state_id 1:1 join; 2025 population policy "
                              "unchanged from B",
        "primary_metric": proto["primary_metric"],
        "comparisons": ["final PROJECTED vs Logistic PROJECTED",
                        "final PROJECTED vs D anchor reference"],
        "bootstrap": {"unit": "race", "replicates": 2000, "seed": 42},
        "dispositions": proto["dispositions"],
        "no_reselection_rule": proto["finalist_rule"],
        "f_has_no_discretionary_tuning": True,
    }
    manifest["manifest_identity"] = sha(
        {k: v for k, v in manifest.items() if k != "manifest_identity"})
    (RES / "v3_5f_execution_manifest.json").write_text(json.dumps(
        manifest, indent=1, sort_keys=True) + "\n")
    print("final config:", final_cfg)
    print("calibration:", cal_method)
    print("recipe identity:", recipe["recipe_identity"])
    print("manifest identity:", manifest["manifest_identity"])


if __name__ == "__main__":
    main()
