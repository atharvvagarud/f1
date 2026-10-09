"""Freeze V3.5F execution record (before ANY 2025 outcome contact).

References frozen E recipe + F manifest identities without altering them.
Freezes transfer/disposition/stage/calibration/top1 classification
definitions before seeing 2025 numbers. Immutable after first 2025 access.
Reads development artifacts only; touches no 2025 content.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

OUT = Path("results/v3/v3_5f")
E_PROTO = "4adf3da33b86e734e7b663c6702c64f9377c08ac4318fb5439eebd439aec38e6"
RECIPE_ID = "b1d8ce5e43059477a5e57fe5b4d301cbd7b9975864d1ad964d613d1124044c09"
MANIFEST_ID = "eab0da304dbb46b6de58ccb00c676e6a64761cf6473cc1361659ff8658b3d8e1"


def sha(payload: dict) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> None:
    recipe = json.loads(
        Path("results/v3/v3_5e/final_fit_recipe.json").read_text())
    assert sha({k: v for k, v in recipe.items()
                if k != "recipe_identity"}) == \
        recipe["recipe_identity"] == RECIPE_ID
    manifest = json.loads(
        Path("results/v3/v3_5e/v3_5f_execution_manifest.json").read_text())
    assert sha({k: v for k, v in manifest.items()
                if k != "manifest_identity"}) == \
        manifest["manifest_identity"] == MANIFEST_ID
    eproto = json.loads(
        Path("results/v3/v3_5e/refinement_protocol.json").read_text())
    assert eproto["protocol_identity"] == E_PROTO
    top1 = json.loads(Path("results/v3/v3_5e/top1_audit.json").read_text())
    dev_top1 = {f: top1["per_fold"][f]["delta_vs_logistic_proj"]
                for f in ("D1", "D2", "D3")}
    dev_worst = max(v for v in dev_top1.values() if v > 0)

    record = {
        "schema_version": "v3.5f-execution-record-v1",
        "parent": {"commit": "3cbd28470ffa211bd754d4262eb10d66d149bf00",
                   "tag": "v3.4-ensemble"},
        "e_protocol_identity": E_PROTO,
        "final_recipe_identity": RECIPE_ID,
        "f_manifest_identity": MANIFEST_ID,
        "feature_identity": dict(recipe["feature_identity"]),
        "projection_identity": recipe["projection_identity"],
        "control_identity": {
            "c_identity": manifest["control_identity"],
            "config": {"C": 0.01, "penalty": "L2", "solver": "lbfgs",
                       "max_iter": 1000, "class_weight": None,
                       "random_state": 42}},
        "task": "ordered_cumulative_finish_thresholds",
        "threshold_order": [1, 3, 5, 10],
        "allowed_season": 2025,
        "allowed_operation": "evaluation only: fit frozen recipes on "
                             "2018-2024 once, predict 2025 once, report "
                             "frozen metrics; no tuning, selection, or "
                             "repair",
        "evaluation_terminology": "PREVIOUSLY REVEALED OUT-OF-TIME OUTCOME "
                                  "EVALUATION",
        "primary_metric": "mean_race_macro_log_loss_over_4_thresholds; "
                          "XGB FINAL PROJECTED minus LOGISTIC PROJECTED",
        "secondary_metrics": ["brier", "ece", "state_pooled_ll"],
        "bootstrap": {"unit": "race", "replicates": 2000, "seed": 42,
                      "ci": 0.95},
        "stage_analysis": "frozen EARLY/MID/LATE via stages.stage_partition",
        "top1_audit": "required; development deltas embedded for transfer "
                      "classification",
        "dev_top1_deltas_vs_logistic": dev_top1,
        "transfer_definitions": {
            "evaluation_order": ["REVERSED", "STRONG_TRANSFER",
                                 "PARTIAL_TRANSFER", "MIXED_TRANSFER",
                                 "NO_TRANSFER"],
            "REVERSED": "primary delta > 0 with bootstrap CI entirely "
                        "above zero",
            "STRONG_TRANSFER": "primary delta < 0, CI entirely below zero, "
                               ">=3/4 thresholds improve, top1 delta <= 0",
            "PARTIAL_TRANSFER": "primary delta < 0, CI entirely below zero, "
                                "but fewer than 3/4 thresholds improve or "
                                "top1 regresses",
            "MIXED_TRANSFER": "primary delta < 0 with CI spanning zero, or "
                              "non-positive primary delta with CI spanning "
                              "zero and >=2/4 thresholds improving",
            "NO_TRANSFER": "otherwise (primary delta >= 0 with CI spanning "
                           "zero and <=1/4 thresholds improving, or any "
                           "residual case)"},
        "top1_transfer_definitions": {
            "dev_reference": dict(dev_top1),
            "attenuation_bound": dev_worst,
            "evaluation_order": ["MIXED", "WEAKNESS_REVERSES",
                                 "WEAKNESS_ATTENUATES", "WEAKNESS_PERSISTS"],
            "MIXED": "2025 top1 delta == 0 within 1e-12",
            "WEAKNESS_REVERSES": "2025 top1 delta < 0",
            "WEAKNESS_ATTENUATES": "0 < 2025 top1 delta < dev attenuation "
                                   "bound (largest positive development "
                                   "regression)",
            "WEAKNESS_PERSISTS": "2025 top1 delta >= dev attenuation bound"},
        "calibration_transfer_definitions": {
            "CALIBRATION_TRANSFERS": "2025 top5 calibrated LL < RAW LL",
            "CALIBRATION_NEUTRAL": "equal within 1e-12",
            "CALIBRATION_REGRESSES": "2025 top5 calibrated LL > RAW LL; "
                                     "recipe stays frozen regardless"},
        "stage_transfer_definitions": {
            "evaluation_order": ["LATE_ADVANTAGE_TRANSFERS",
                                 "LATE_ADVANTAGE_FAILS",
                                 "LATE_ADVANTAGE_ATTENUATES", "MIXED"],
            "LATE_ADVANTAGE_TRANSFERS": "2025 LATE primary delta < 0",
            "LATE_ADVANTAGE_FAILS": "2025 LATE delta > 0 and no other "
                                    "stage improves",
            "LATE_ADVANTAGE_ATTENUATES": "2025 LATE delta > 0 but another "
                                         "stage improves",
            "MIXED": "2025 LATE delta == 0 within 1e-12"},
        "disposition_enum": ["OUTCOME_XGB_GENERALIZES",
                             "OUTCOME_XGB_MIXED_OUT_OF_TIME",
                             "OUTCOME_XGB_FAILS_OUT_OF_TIME"],
        "disposition_definitions": {
            "evaluation_order": ["OUTCOME_XGB_FAILS_OUT_OF_TIME",
                                 "OUTCOME_XGB_GENERALIZES",
                                 "OUTCOME_XGB_MIXED_OUT_OF_TIME"],
            "OUTCOME_XGB_FAILS_OUT_OF_TIME": "primary delta > 0; no "
                "secondary metric rescues into GENERALIZES",
            "OUTCOME_XGB_GENERALIZES": "primary delta < 0 with CI entirely "
                "below zero, >=3/4 thresholds improve, top1 delta <= 0, no "
                "material Brier/ECE degradation, coherence comparable",
            "OUTCOME_XGB_MIXED_OUT_OF_TIME": "all other cases; in "
                "particular primary improvement with CI spanning zero, or "
                "primary improvement with material top1 regression"},
        "champion_policy": "Logistic stays conservative SCIENTIFIC CHAMPION "
                           "unless GENERALIZES is met; XGB documented as "
                           "NONLINEAR RESEARCH CANDIDATE otherwise; no "
                           "serving promotion in F",
        "no_reselection_rule": "after 2025 contact: no config, calibration, "
                               "projection, feature, or family change; poor "
                               "2025 is a scientific result",
        "immutability": "frozen before first 2025 outcome access",
    }
    record["execution_record_identity"] = sha(
        {k: v for k, v in record.items()
         if k != "execution_record_identity"})
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "execution_record.json").write_text(json.dumps(
        record, indent=1, sort_keys=True) + "\n")
    print("execution record:",
          record["execution_record_identity"])
    print("dev top1 deltas:", dev_top1, "attenuation bound:", dev_worst)


if __name__ == "__main__":
    main()
