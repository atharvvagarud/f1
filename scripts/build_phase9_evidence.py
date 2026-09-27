"""P9-1 frozen evidence derivation (READ-ONLY).

Builds checked-in static evidence for /models and /about from frozen
Phase-2/3/8 artifacts. Never fits, predicts, evaluates, recalibrates,
or touches 2025 rows: the only 2025 model-performance source is the
frozen holdout REPORT (JSON), whose SHA is guarded. Fails closed on any
source-identity mismatch. Deterministic: sorted keys, fixed floats as
stored, no timestamps, no absolute paths, no machine identity.
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

MODEL_LAB_REPORTS = os.path.join("data", "v2", "model_lab", "reports")
OUT_MODELS = os.path.join("frontend", "data", "models.v1.json")
OUT_ABOUT = os.path.join("frontend", "data", "about.v1.json")

MODEL_EVIDENCE_CONTRACT_VERSION = "v1"
ABOUT_EVIDENCE_CONTRACT_VERSION = "v1"

EXPECTED = {
    "winner_serving_sha256":
        "1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4",
    "phase2_content_hash":
        "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db",
    "matrix_parquet_sha256":
        "b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3",
    "holdout_report_sha256":
        "2c3a166df1a1af1d20f24fafc6a17283de1cdd1eea2b5f67a26204ed174a7415",
    "e3_artifact_sha256":
        "bae84b614a6e9e176d5bb9c33b99dcaf4cba3f376333b0f075c828f73982939f",
    "e2_corpus_aggregate_sha256":
        "78a3c059888637fe83cc534d0eb7869b6d18e746724bb1ce0f03ee3b8ba96298",
    "phase8_freeze_commit":
        "7fa9bf970c4281b7c7d64fecf8b8e9b207a963d8",
    "phase8_freeze_tag":
        "v2-replay-intelligence-phase8",
    "protocol_semantic_hash":
        "0168f1d7fea584cd8a1e4dfe8267bb54dbec16aae60c92663c31115cb3ef53ce",
    "model_spec_fingerprint":
        "3164de9e61ca94ab958e26590608824ca6c7b05de29c5398d3d204a8c329c24d",
}

SERVING_REL = os.path.join(
    "results", "v2_model_lab", "winner_logreg_raw_v1_serving.joblib")
E3_REL = os.path.join(
    "results", "v2_explainability", "global_winner_logreg_v1.json")
HOLDOUT_REL = os.path.join(MODEL_LAB_REPORTS, "final_holdout_2025_v1.json")


class EvidenceError(ValueError):
    """Source identity or evidence derivation failure (fail closed)."""


def _path(rel: str) -> str:
    return os.path.join(REPO_ROOT, rel)


def _read_json(rel: str) -> dict:
    with open(_path(rel), encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise EvidenceError(f"{rel} is not a JSON object")
    return data


def _sha256_file(rel: str) -> str:
    digest = hashlib.sha256()
    with open(_path(rel), "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _guard_file_sha(rel: str, expected: str, label: str) -> None:
    actual = _sha256_file(rel)
    if actual != expected:
        raise EvidenceError(
            f"{label} identity mismatch for {rel}: "
            f"expected {expected}, observed {actual}")


def _guard_value(actual, expected, label: str):
    if actual != expected:
        raise EvidenceError(
            f"{label} mismatch: expected {expected!r}, observed {actual!r}")
    return actual


def _agg_logloss(report: dict, *route: str) -> dict:
    node: object = report
    for key in route:
        if not isinstance(node, dict) or key not in node:
            raise EvidenceError(
                f"missing aggregate route {'/'.join(route)}")
        node = node[key]
    if not isinstance(node, dict) or "log_loss" not in node:
        raise EvidenceError("aggregate missing race-macro log_loss")
    entry = node["log_loss"]
    for key in ("mean", "per_fold"):
        if key not in entry:
            raise EvidenceError("log_loss aggregate missing " + key)
    folds = entry["per_fold"]
    if sorted(folds) != ["D1", "D2", "D3"]:
        raise EvidenceError("log_loss per_fold is not D1/D2/D3")
    return {"mean": entry["mean"],
            "per_fold": {"D1": folds["D1"],
                         "D2": folds["D2"],
                         "D3": folds["D3"]}}


def _load_reports() -> dict:
    names = ["final_holdout_2025_v1", "logreg_reference_v1",
             "nonlinear_candidates_v1", "bagged_candidates_v1",
             "tuning_selection_v1", "logreg_boundary_resolution_v1",
             "calibration_selection_v1", "baseline_suite_v1"]
    reports = {}
    for name in names:
        reports[name] = _read_json(os.path.join(MODEL_LAB_REPORTS,
                                                name + ".json"))
    return reports


def _check_reports(reports: dict) -> None:
    tagged = [("M3", "logreg_reference_v1"), ("M4", "nonlinear_candidates_v1"),
              ("M5", "bagged_candidates_v1"), ("M6", "tuning_selection_v1"),
              ("M7", "logreg_boundary_resolution_v1"),
              ("M8", "calibration_selection_v1"),
              ("M2", "baseline_suite_v1")]
    for label, key in tagged:
        rep = reports[key]
        _guard_value(rep.get("task"), "winner", label + " task")
        _guard_value(rep.get("feature_set"), "ALL_84", label + " features")
        if rep.get("holdout_accessed", False):
            raise EvidenceError(label + " accessed the holdout")


def _sources() -> dict:
    def rep(name: str) -> str:
        return os.path.join(MODEL_LAB_REPORTS, name + ".json")

    return {
        "MODEL_CARD": {
            "path": "docs/MODEL_LAB_FINAL_MODEL_CARD.md",
            "note": "Frozen serving identity and holdout headline.",
        },
        "MODEL_LAB_FREEZE": {
            "path": "docs/MODEL_LAB_FREEZE_MANIFEST.json",
            "note": "Frozen spec, fingerprints, holdout artifact SHA.",
        },
        "FINAL_HOLDOUT_2025": {
            "path": HOLDOUT_REL,
            "sha256": EXPECTED["holdout_report_sha256"],
            "note": "One-shot 2025 holdout at stored precision. READ ONLY.",
        },
        "M2_BASELINES": {
            "path": rep("baseline_suite_v1"),
            "note": "Non-ML development floor, D1-D3.",
        },
        "M3_LOGREG": {
            "path": rep("logreg_reference_v1"),
            "note": "LogReg C=1.0 reference, D1-D3.",
        },
        "M4_NONLINEAR": {
            "path": rep("nonlinear_candidates_v1"),
            "note": "HGB/XGB fixed specs, D1-D3.",
        },
        "M5_BAGGED": {
            "path": rep("bagged_candidates_v1"),
            "note": "ExtraTrees/RandomForest fixed specs, D1-D3.",
        },
        "M6_TUNING": {
            "path": rep("tuning_selection_v1"),
            "note": "Nested temporal tuning, LogReg + ExtraTrees.",
        },
        "M7_BOUNDARY": {
            "path": rep("logreg_boundary_resolution_v1"),
            "note": "C boundary resolution; global freeze rule C=0.01.",
        },
        "M8_CALIBRATION": {
            "path": rep("calibration_selection_v1"),
            "note": "RAW/Platt/Isotonic development comparison.",
        },
        "FEATURE_REGISTRY": {
            "path": "docs/generated/phase2_freeze_manifest.json",
            "note": "ALL_84 v8 registry authority.",
        },
        "E3_GLOBAL_EXPLANATION": {
            "path": E3_REL,
            "sha256": EXPECTED["e3_artifact_sha256"],
            "note": "Coefficients plus in-sample permutation evidence.",
        },
        "PHASE8_FREEZE": {
            "path": os.path.join("results", "v2_validation",
                                 "phase8_freeze_manifest.json"),
            "note": "Replay corpus counts, contracts, E7 summary.",
        },
    }


def _candidates(reports: dict) -> list:
    base = reports["baseline_suite_v1"]
    m3 = reports["logreg_reference_v1"]
    m4 = reports["nonlinear_candidates_v1"]
    m5 = reports["bagged_candidates_v1"]
    m6 = reports["tuning_selection_v1"]
    m7 = reports["logreg_boundary_resolution_v1"]
    return [
        {"family": "CLASS_PRIOR",
         "variant": "non-ML baseline (positive-rate prior)",
         "source_ids": ["M2_BASELINES"],
         "development_log_loss": _agg_logloss(
             base, "aggregates", "CLASS_PRIOR"),
         "limitation": "Empirical floor, not a contender."},
        {"family": "LogisticRegression",
         "variant": "C=1.0 fixed reference (M3)",
         "source_ids": ["M3_LOGREG"],
         "development_log_loss": _agg_logloss(m3, "aggregates"),
         "limitation": "Untuned reference point."},
        {"family": "HistGradientBoosting",
         "variant": "fixed spec, lr=0.1, 100 iter (M4)",
         "source_ids": ["M4_NONLINEAR"],
         "development_log_loss": _agg_logloss(
             m4, "per_model", "hist_gradient_boosting", "aggregates"),
         "limitation": "One fixed spec; worse development log loss."},
        {"family": "XGBoost",
         "variant": "fixed spec, depth=4, 200 rounds (M4)",
         "source_ids": ["M4_NONLINEAR"],
         "development_log_loss": _agg_logloss(
             m4, "per_model", "xgboost", "aggregates"),
         "limitation": "One fixed spec; worse development log loss."},
        {"family": "ExtraTrees",
         "variant": "fixed spec, 300 trees (M5)",
         "source_ids": ["M5_BAGGED"],
         "development_log_loss": _agg_logloss(
             m5, "per_model", "extra_trees", "aggregates"),
         "limitation": "Fixed spec; tuned further in M6."},
        {"family": "RandomForest",
         "variant": "fixed spec, 300 trees (M5)",
         "source_ids": ["M5_BAGGED"],
         "development_log_loss": _agg_logloss(
             m5, "per_model", "random_forest", "aggregates"),
         "limitation": "Fixed spec; not carried into tuning."},
        {"family": "LogisticRegression",
         "variant": "nested-tuned outer procedure (M6)",
         "source_ids": ["M6_TUNING"],
         "development_log_loss": _agg_logloss(
             m6, "per_candidate", "logistic_regression", "aggregates"),
         "limitation": "Estimates the tuning procedure, not one vector."},
        {"family": "ExtraTrees",
         "variant": "nested-tuned outer procedure (M6)",
         "source_ids": ["M6_TUNING"],
         "development_log_loss": _agg_logloss(
             m6, "per_candidate", "extra_trees", "aggregates"),
         "limitation": "Estimates the tuning procedure, not one vector."},
        {"family": "LogisticRegression",
         "variant": "frozen-global C=0.01 outer (M7)",
         "source_ids": ["M7_BOUNDARY"],
         "development_log_loss": _agg_logloss(m7, "aggregate"),
         "limitation": "Outer refit per fold with frozen C."},
    ]


def _calibration(reports: dict) -> dict:
    m8 = reports["calibration_selection_v1"]
    _guard_value(
        m8["method_comparison"]["selected_method"], "RAW", "M8 selection")
    methods = {}
    for method in ("RAW", "PLATT", "ISOTONIC"):
        agg = m8["aggregate"][method]["race_macro_log_loss"]
        if sorted(agg["per_fold"]) != ["D1", "D2", "D3"]:
            raise EvidenceError("M8 per_fold is not D1/D2/D3")
        methods[method] = {
            "mean": agg["mean"],
            "per_fold": {"D1": agg["per_fold"]["D1"],
                         "D2": agg["per_fold"]["D2"],
                         "D3": agg["per_fold"]["D3"]},
        }
    return {
        "evaluation_class": "FROZEN_DEVELOPMENT_CALIBRATION",
        "population": "D1-D3 outer validation; calibration fit on last "
                      "train season only; 2025 never touched",
        "metric": "race_macro_log_loss",
        "selection_rule": "mean_log_loss_primary_with_brier_and_"
                          "regression_guards",
        "selected_method": "RAW",
        "methods": methods,
        "source_ids": ["M8_CALIBRATION"],
    }


def _holdout_metrics(holdout: dict) -> dict:
    return holdout["development_comparison"]["holdout"]


def _metric(
    metric_id: str, display: str, value: float, direction: str,
    role: str, aggregation: str, description: str,
    limitation: str, source_ids: list,
) -> dict:
    return {
        "id": metric_id,
        "display_name": display,
        "value": value,
        "direction": direction,
        "role": role,
        "aggregation": aggregation,
        "population": "2025 one-shot holdout, 24 races, 26692 states",
        "description": description,
        "limitation": limitation,
        "source_ids": source_ids,
    }


def build_models() -> dict:
    freeze = _read_json("docs/MODEL_LAB_FREEZE_MANIFEST.json")
    spec = freeze["final_model_specification"]
    _guard_value(freeze["holdout_artifact"]["sha256"],
                 EXPECTED["holdout_report_sha256"], "holdout artifact SHA")
    _guard_value(spec["estimator"], "LogisticRegression", "spec estimator")
    _guard_value(spec["C"], 0.01, "spec C")
    _guard_value(spec["feature_set"], "ALL_84", "spec feature set")
    _guard_value(spec["calibration_method"], "RAW", "spec calibration")
    _guard_value(list(spec["final_fit_seasons"]),
                 [2018, 2019, 2020, 2021, 2022, 2023, 2024],
                 "spec final-fit seasons")
    _guard_value(spec["holdout_season"], 2025, "spec holdout season")

    reports = _load_reports()
    _check_reports(reports)
    holdout = reports["final_holdout_2025_v1"]
    det = holdout["determinism"]["final_fit_counts"]
    _guard_value(det["eligible"], 162728, "FINAL_FIT eligible")
    _guard_value(det["races"], 149, "FINAL_FIT races")
    hov = _holdout_metrics(holdout)
    stage = holdout["development_comparison"]["stage_log_loss"]["holdout"]
    for key in ("EARLY", "MID", "LATE"):
        if key not in stage:
            raise EvidenceError("holdout stage evidence missing " + key)
    e3 = _read_json(E3_REL)
    perm = e3["permutation_importance"]
    _guard_value(perm["protocol"]["population"]["evidence_class"].split(" (")[0],
                 "PRE_2025_FINAL_FIT_IN_SAMPLE", "E3 evidence class")
    perm_top = sorted(perm["results"], key=lambda r: r["mean_delta"],
                      reverse=True)[:10]
    coef_top = sorted(e3["numeric_coefficients"],
                      key=lambda r: abs(r["coefficient"]),
                      reverse=True)[:10]

    metrics = [
        _metric("race_macro_log_loss", "Race-macro log loss",
                hov["race_macro_log_loss"], "lower_is_better", "PRIMARY",
                "race_macro",
                "Mean per-race mean surprisal of each driver's P(win).",
                "Sensitive to tail miscalibration; pair with Brier.",
                ["FINAL_HOLDOUT_2025"]),
        _metric("race_macro_brier", "Race-macro Brier score",
                hov["race_macro_brier"], "lower_is_better", "SECONDARY",
                "race_macro",
                "Mean per-race squared error of P(win).",
                "Less tail-sensitive than log loss.",
                ["FINAL_HOLDOUT_2025"]),
        _metric("race_macro_pr_auc", "PR AUC",
                hov["race_macro_pr_auc"], "higher_is_better", "SECONDARY",
                "race_macro",
                "Precision-recall area at ~5.5% winner prevalence.",
                "More informative than ROC under imbalance.",
                ["FINAL_HOLDOUT_2025"]),
        _metric("winner_top1", "Synchronized top-1",
                hov["winner_top1"], "higher_is_better", "SECONDARY",
                "race_macro",
                "Fraction of holdout races where the actual winner was "
                "the model's top-ranked driver.",
                "Rank hit-rate, not probabilistic quality.",
                ["FINAL_HOLDOUT_2025"]),
        _metric("winner_top3", "Synchronized top-3",
                hov["winner_top3"], "higher_is_better", "SECONDARY",
                "race_macro",
                "Fraction of holdout races with the winner in the "
                "model's top-3 ranked drivers.",
                "Lenient rank hit-rate.",
                ["FINAL_HOLDOUT_2025"]),
        _metric("race_macro_roc_auc", "ROC AUC",
                hov["race_macro_roc_auc"], "higher_is_better", "TECHNICAL",
                "race_macro",
                "Rank discrimination over pooled states.",
                "Reads high under imbalance; never a headline alone.",
                ["FINAL_HOLDOUT_2025"]),
        _metric("expected_calibration_error", "ECE (10 bins)",
                hov["expected_calibration_error"], "lower_is_better",
                "TECHNICAL", "state_pooled",
                "Mean |accuracy minus confidence| over equal-width bins.",
                "Small-sample bins are noisy.",
                ["FINAL_HOLDOUT_2025"]),
        _metric("state_pooled_log_loss", "State-pooled log loss",
                hov["state_pooled_log_loss"], "lower_is_better", "TECHNICAL",
                "state_pooled",
                "Diagnostic twin of the headline; large races dominate.",
                "Never a headline.",
                ["FINAL_HOLDOUT_2025"]),
        _metric("state_pooled_brier", "State-pooled Brier",
                hov["state_pooled_brier"], "lower_is_better", "TECHNICAL",
                "state_pooled",
                "Diagnostic twin of the headline Brier.",
                "Never a headline.",
                ["FINAL_HOLDOUT_2025"]),
    ]

    return {
        "contract_version": MODEL_EVIDENCE_CONTRACT_VERSION,
        "sources": _sources(),
        "provenance": {
            "phase8_freeze_commit": EXPECTED["phase8_freeze_commit"],
            "phase8_freeze_tag": EXPECTED["phase8_freeze_tag"],
            "winner_serving_sha256": EXPECTED["winner_serving_sha256"],
            "phase2_content_hash": EXPECTED["phase2_content_hash"],
            "matrix_parquet_sha256": EXPECTED["matrix_parquet_sha256"],
            "holdout_report_sha256": EXPECTED["holdout_report_sha256"],
            "e3_artifact_sha256": EXPECTED["e3_artifact_sha256"],
            "protocol_semantic_hash": EXPECTED["protocol_semantic_hash"],
            "model_spec_fingerprint":
                EXPECTED["model_spec_fingerprint"],
        },
        "model_spec": {
            "task": "winner",
            "target": "is_winner",
            "eligibility": "eligible_is_winner",
            "estimator": spec["estimator"],
            "C": spec["C"],
            "penalty": spec["penalty"],
            "solver": spec["solver"],
            "max_iter": spec["max_iter"],
            "class_weight": spec["class_weight"],
            "random_state": 42,
            "feature_set": spec["feature_set"],
            "feature_version": "v8",
            "canonical_feature_count": 84,
            "transformed_feature_count": 106,
            "calibration": spec["calibration_method"],
            "probability_semantics": "INDEPENDENT_BINARY",
            "final_fit_seasons": "2018-2024",
            "holdout_season": 2025,
            "source_ids": ["MODEL_CARD", "MODEL_LAB_FREEZE"],
        },
        "holdout_evidence": {
            "evaluation_class": "FROZEN_ONE_SHOT_2025_HOLDOUT",
            "population": {
                "seasons": [2025],
                "races": 24,
                "eligible_states": 26692,
                "positives": 1444,
                "eligibility_mask": "eligible_is_winner",
            },
            "aggregation": "race_macro (equal weight per race, "
                           "then row metric)",
            "metrics": metrics,
            "stages": [
                {"stage": "EARLY", "race_macro_log_loss": stage["EARLY"],
                 "definition": "first third of race_progress_frac"},
                {"stage": "MID", "race_macro_log_loss": stage["MID"],
                 "definition": "middle third of race_progress_frac"},
                {"stage": "LATE", "race_macro_log_loss": stage["LATE"],
                 "definition": "final third of race_progress_frac"},
            ],
            "source_ids": ["FINAL_HOLDOUT_2025"],
        },
        "temporal_evaluation": {
            "protocol": "v1",
            "development_folds": [
                {"fold": "D1", "train": "2018-2021", "validate": 2022,
                 "train_states": 88123, "val_states": 23577},
                {"fold": "D2", "train": "2018-2022", "validate": 2023,
                 "train_states": 111700, "val_states": 24422},
                {"fold": "D3", "train": "2018-2023", "validate": 2024,
                 "train_states": 136122, "val_states": 26606},
            ],
            "final_fit": "2018-2024",
            "holdout": 2025,
            "guards": ["train strictly before validation",
                       "2025 unreachable from development paths",
                       "M0 count audits pinned per fold and task"],
            "source_ids": ["MODEL_LAB_FREEZE"],
        },
        "development_evidence": {
            "evaluation_class": "FROZEN_DEVELOPMENT_FOLDS",
            "protocol": "v1",
            "aggregation": "race_macro",
            "metric": "race_macro_log_loss",
            "candidates": _candidates(reports),
            "warning": "Development-only; never ranked against holdout.",
            "source_ids": ["M2_BASELINES", "M3_LOGREG", "M4_NONLINEAR",
                           "M5_BAGGED", "M6_TUNING", "M7_BOUNDARY"],
        },
        "model_selection": {
            "serving_choice": "LogisticRegression C=0.01 RAW",
            "selection_rule": "M7 global rule: aggregate inner log-loss "
                              "fallback (lowest aggregate inner mean "
                              "0.0827198539; no strict per-fold majority: "
                              "D1 0.003, D2 0.01, D3 0.03).",
            "measured_evidence": [
                "LogReg competitive development quality at lowest "
                "complexity class (M4/M5/M6).",
                "C=0.01 from the predeclared M7 global rule.",
                "RAW from the predeclared M8 rule.",
            ],
            "engineering_context": "Single linear model; exact log-odds "
                                   "decomposition enables explanations; no "
                                   "calibration layer to maintain.",
            "limitations": "Development hyperparameter uncertainty "
                           "documented in M7; not a universality claim.",
            "source_ids": ["M7_BOUNDARY", "M8_CALIBRATION"],
        },
        "calibration_evidence": _calibration(reports),
        "feature_system": {
            "canonical_total": 84,
            "transformed_dim": 106,
            "families": [
                {"family": "STATE", "count": 23,
                 "meaning": "Position, laps and session state."},
                {"family": "PACE", "count": 12,
                 "meaning": "Lap-time pace levels and trends."},
                {"family": "GAPS", "count": 8,
                 "meaning": "Time gaps to leader and cars ahead."},
                {"family": "FIELD_CONTEXT", "count": 12,
                 "meaning": "Field spread and cars-around context."},
                {"family": "RATES_MOMENTUM", "count": 4,
                 "meaning": "Rates of change and momentum."},
                {"family": "ENVIRONMENT_HISTORY", "count": 9,
                 "meaning": "Weather and track-state history."},
                {"family": "PRE_RACE_PRIORS", "count": 13,
                 "meaning": "Qualifying and historical priors."},
                {"family": "INTERACTIONS", "count": 3,
                 "meaning": "Engineered feature interactions."},
            ],
            "feature_names_by_family": {
                family: sorted(group)
                for family, group in
                e3["canonical_groups"]["groups"].items()
            },
            "preprocessing": "median plus StandardScaler numerics; "
                             "most-frequent booleans; MISSING sentinel "
                             "plus train-vocabulary one-hot "
                             "categoricals; fit on TRAIN only",
            "source_ids": ["FEATURE_REGISTRY", "E3_GLOBAL_EXPLANATION"],
        },
        "coefficient_evidence": {
            "explanation_space": "LOG_ODDS",
            "intercept": e3["intercept"],
            "reading": "Standardized log-odds scale; negative values "
                       "are associated with lower model log-odds.",
            "top_by_abs": [
                {"transformed": row["transformed_name"],
                 "canonical": row["canonical_feature"],
                 "family": row["feature_family"],
                 "coefficient": row["coefficient"]}
                for row in coef_top
            ],
            "source_ids": ["E3_GLOBAL_EXPLANATION"],
        },
        "permutation_evidence": {
            "evidence_class": "PRE_2025_FINAL_FIT_IN_SAMPLE",
            "evidence_class_note": "2018-2024 rows the production "
                                   "artifact was final-fit on; explicitly "
                                   "NOT temporally out-of-sample.",
            "metric": "race_macro_log_loss",
            "permutation_unit": "state_within_race",
            "repeats": 5,
            "base_seed": 42,
            "baseline_metric": perm["baseline_metric"],
            "entries": [
                {"canonical": row["canonical_feature"],
                 "family": row["feature_family"],
                 "mean_delta": row["mean_delta"],
                 "min_delta": row["min_delta"],
                 "max_delta": row["max_delta"]}
                for row in perm_top
            ],
            "limitations": "In-sample sensitivity, not causal and not "
                           "out-of-sample importance.",
            "source_ids": ["E3_GLOBAL_EXPLANATION"],
        },
        "temporal_safeguards": {
            "statement": "No temporal leakage was detected under the "
                         "implemented adversarial test suite.",
            "items": [
                {"id": "SYNC",
                 "title": "Race-wide synchronized observation",
                 "description": "Every state observes the field at the "
                                "same race time T.",
                 "source_ids": ["FEATURE_REGISTRY"]},
                {"id": "NO_FUTURE",
                 "title": "state_time_s <= T",
                 "description": "No observation dated after the state "
                                "time enters features.",
                 "source_ids": ["FEATURE_REGISTRY"]},
                {"id": "NO_FALL_FORWARD",
                 "title": "No fall-forward enrichment",
                 "description": "Weather, race-control and pit context "
                                "attach prior-or-equal rows only.",
                 "source_ids": ["FEATURE_REGISTRY"]},
                {"id": "EXACT_IDENTITY",
                 "title": "Exact matrix identity",
                 "description": "Replay resolves frozen rows by exact "
                                "identity; no tolerance joins.",
                 "source_ids": ["PHASE8_FREEZE"]},
                {"id": "LABEL_SEPARATION",
                 "title": "Labels structurally separated",
                 "description": "Labels and masks never enter the "
                                "design matrix.",
                 "source_ids": ["MODEL_LAB_FREEZE"]},
                {"id": "HOLDOUT_FIREWALL",
                 "title": "2025 serving firewall",
                 "description": "2025 unreachable from development and "
                                "serving paths; one-shot M9 opt-in.",
                 "source_ids": ["MODEL_LAB_FREEZE"]},
                {"id": "POST_T_MUTATION",
                 "title": "Post-T mutation tests",
                 "description": "Mutating post-T inputs must not change "
                                "at-T features or predictions.",
                 "source_ids": ["FEATURE_REGISTRY"]},
            ],
        },
        "performance": {
            "MODEL_INFERENCE": [
                {"metric": "batch_throughput_states_per_s",
                 "value": 478741.84,
                 "scope": "M9 holdout transform plus predict",
                 "limitation": "Evaluation harness, not an API SLA.",
                 "source_ids": ["MODEL_CARD"]},
                {"metric": "single_state_latency_s_mean",
                 "value": 0.008571,
                 "scope": "M9 harness single-state",
                 "limitation": "Harness timing, not serving latency.",
                 "source_ids": ["MODEL_CARD"]},
            ],
            "OFFLINE_CACHE_BUILD": [
                {"metric": "seconds_per_checkpoint",
                 "value": 11.8,
                 "scope": "E1 serial baseline, single core",
                 "limitation": "Offline only; E1.6 matrix backend "
                               "is the fast path.",
                 "source_ids": ["PHASE8_FREEZE"]},
            ],
            "LOCAL_EXPLANATION_API": [
                {"metric": "warm_p50_ms",
                 "value": 24.5,
                 "scope": "E7 TestClient, full API with services",
                 "limitation": "Not pure inference latency.",
                 "source_ids": ["PHASE8_FREEZE"]},
            ],
            "CHANGE_EXPLANATION_API": [
                {"metric": "warm_p50_ms",
                 "value": 41.8,
                 "scope": "E7 TestClient, full API with services",
                 "limitation": "Not pure inference latency.",
                 "source_ids": ["PHASE8_FREEZE"]},
            ],
        },
        "limitations": [
            {"id": "INDEPENDENT_BINARY",
             "text": "Winner estimates are independent binary "
                     "probabilities, not a normalized race distribution."},
            {"id": "HOLDOUT_ONE_SEASON",
             "text": "The holdout is one season (24 races); no "
                     "post-holdout tuning."},
            {"id": "PERMUTATION_IN_SAMPLE",
             "text": "Global permutation evidence is "
                     "PRE_2025_FINAL_FIT_IN_SAMPLE, not out-of-sample."},
            {"id": "NON_CAUSAL",
             "text": "Explanations are associational and model-internal, "
                     "not causal."},
            {"id": "LOG_ODDS_ONLY",
             "text": "Contributions are additive in log-odds, never "
                     "probability-point attributions."},
            {"id": "NO_SHAP",
             "text": "SHAP is not part of v1."},
            {"id": "CHECKPOINT_GRANULARITY",
             "text": "Timelines operate at prediction checkpoints, not "
                     "every replay frame."},
            {"id": "HYPERPARAMETER_UNCERTAINTY",
             "text": "Development hyperparameter uncertainty is "
                     "documented in M7."},
        ],
    }


def build_about() -> dict:
    p8 = _read_json(os.path.join(
        "results", "v2_validation", "phase8_freeze_manifest.json"))
    _guard_value(p8["corpus_counts"]["races"], 149, "replay races")
    _guard_value(p8["corpus_counts"]["checkpoints"], 9644,
                 "replay checkpoints")
    return {
        "contract_version": ABOUT_EVIDENCE_CONTRACT_VERSION,
        "sources": _sources(),
        "provenance": {
            "phase8_freeze_commit": EXPECTED["phase8_freeze_commit"],
            "phase8_freeze_tag": EXPECTED["phase8_freeze_tag"],
            "e2_corpus_aggregate_sha256":
                EXPECTED["e2_corpus_aggregate_sha256"],
        },
        "capabilities": [
            {"id": "DATA_PLATFORM", "name": "Historical Data Platform",
             "phase": 1, "status": "FROZEN",
             "does": "Canonical 1950-2025 results plus 2018-2025 FastF1 "
                     "states, manifests and contracts.",
             "does_not": "Serve live feeds.",
             "semantics": "FACT",
             "source_ids": ["PHASE8_FREEZE"]},
            {"id": "FEATURE_ENGINE", "name": "Temporal Feature Engine",
             "phase": 2, "status": "FROZEN",
             "does": "ALL_84 temporal-safe model matrix, 189420 by 106.",
             "does_not": "Model telemetry.",
             "semantics": "FACT",
             "source_ids": ["FEATURE_REGISTRY"]},
            {"id": "MODEL_LAB", "name": "Model Lab",
             "phase": 3, "status": "FROZEN",
             "does": "Temporal protocol plus frozen LogReg winner.",
             "does_not": "Retrain or serve experiments.",
             "semantics": "PREDICTION",
             "source_ids": ["MODEL_CARD", "MODEL_LAB_FREEZE"]},
            {"id": "RACE_STATE", "name": "Race State plus Prediction",
             "phase": 4, "status": "FROZEN",
             "does": "Exact at-T state plus independent-binary inference.",
             "does_not": "Emit normalized distributions.",
             "semantics": "FACT plus PREDICTION",
             "source_ids": ["MODEL_CARD"]},
            {"id": "REPLAY", "name": "Historical Replay",
             "phase": 5, "status": "FROZEN",
             "does": "Factual frames and checkpoints for 149 races.",
             "does_not": "Serve 2025.",
             "semantics": "FACT",
             "source_ids": ["PHASE8_FREEZE"]},
            {"id": "MONTE_CARLO", "name": "Monte Carlo Engine",
             "phase": 6, "status": "FROZEN",
             "does": "Stochastic mutually exclusive race outcomes.",
             "does_not": "Predict a single winner.",
             "semantics": "SIMULATION",
             "source_ids": ["PHASE8_FREEZE"]},
            {"id": "STRATEGY", "name": "Strategy Engine",
             "phase": 7, "status": "FROZEN",
             "does": "Paired CRN counterfactual comparisons.",
             "does_not": "Optimize strategy automatically.",
             "semantics": "STRATEGY",
             "source_ids": ["PHASE8_FREEZE"]},
            {"id": "REPLAY_INTELLIGENCE", "name": "Replay Intelligence",
             "phase": 8, "status": "FROZEN",
             "does": "Cached predictions, timelines, global, local and "
                     "change explanations.",
             "does_not": "Claim causality or use SHAP.",
             "semantics": "PREDICTION plus explanations",
             "source_ids": ["PHASE8_FREEZE", "E3_GLOBAL_EXPLANATION"]},
        ],
        "system_semantics": [
            {"id": "FACT", "display_name": "Historical fact",
             "definition": "Observed or reconstructed information known "
                           "at replay time T.",
             "not_to_confuse_with": ["PREDICTION", "SIMULATION",
                                     "STRATEGY"]},
            {"id": "PREDICTION", "display_name": "Model prediction",
             "definition": "Frozen LogisticRegression independent-binary "
                           "winner estimate per driver.",
             "probability_semantics": "INDEPENDENT_BINARY",
             "not_to_confuse_with": ["FACT", "SIMULATION", "STRATEGY"]},
            {"id": "SIMULATION", "display_name": "Stochastic simulation",
             "definition": "Monte Carlo frequency from mutually exclusive "
                           "simulated race outcomes.",
             "probability_semantics": "MUTUALLY_EXCLUSIVE_FREQUENCY",
             "not_to_confuse_with": ["FACT", "PREDICTION", "STRATEGY"]},
            {"id": "STRATEGY", "display_name": "Strategy comparison",
             "definition": "Paired intervention comparison using common "
                           "random numbers.",
             "not_to_confuse_with": ["FACT", "PREDICTION", "SIMULATION"]},
        ],
        "architecture": {
            "implemented": [
                "Next.js frontend",
                "FastAPI backend",
                "Canonical Parquet data",
                "Phase-2 model matrix",
                "Frozen sklearn serving artifact",
                "Offline replay cache",
                "Monte Carlo engine",
                "Strategy engine",
            ],
            "not_used": [
                "Postgres", "Timescale", "Redis", "WebSockets",
                "Celery/RQ", "MLflow", "Kubernetes", "Kafka",
                "live F1 feeds",
            ],
        },
        "dataset_statistics": {
            "tier_a": {
                "seasons": "2018-2025",
                "terminal_sessions": 173,
                "complete": 171,
                "partial": 2,
                "driver_laps": 189420,
                "results": 3458,
                "pit_stops": 6336,
                "stints": 9324,
                "weather_rows": 25779,
                "race_control_rows": 14992,
            },
            "tier_b": {"seasons": "1950-2025", "seasons_count": 76,
                       "races": 1149, "results": 25784},
            "phase2": {"states": 189420, "predictive_features": 84},
            "replay": {"served_races": 149, "checkpoints": 9644,
                       "observable_predictions": 189610},
            "serving_scope_note": "2025 is available to the historical "
                                  "data platform and is the frozen model "
                                  "holdout; it is NOT served by the "
                                  "frozen replay and prediction product.",
        },
        "reproducibility": {
            "freeze_tags": [
                "v2-data-platform-phase1",
                "v2-temporal-feature-engine-phase2",
                "v2-model-lab-phase3",
                "v2-race-state-prediction-phase4",
                "v2-historical-replay-phase5",
                "v2-monte-carlo-phase6",
                "v2-strategy-engine-phase7",
                "v2-replay-intelligence-phase8",
            ],
            "artifact_hashes": {
                "winner_serving_sha256":
                    EXPECTED["winner_serving_sha256"],
                "phase2_content_hash": EXPECTED["phase2_content_hash"],
                "matrix_parquet_sha256":
                    EXPECTED["matrix_parquet_sha256"],
                "holdout_report_sha256":
                    EXPECTED["holdout_report_sha256"],
                "e3_artifact_sha256": EXPECTED["e3_artifact_sha256"],
            },
            "deterministic_seeds": [42],
            "manifests": [
                "docs/generated/phase2_freeze_manifest.json",
                "docs/MODEL_LAB_FREEZE_MANIFEST.json",
                "docs/PHASE5_FREEZE_MANIFEST.json",
                "docs/PHASE6_FREEZE_MANIFEST.json",
                "results/v2_validation/phase8_freeze_manifest.json",
            ],
            "make_targets": ["test-python", "test-frontend", "typecheck",
                             "lint", "build", "verify"],
            "note": "Per-phase validation reports document reproduction; "
                    "no single-command full reproduction is claimed.",
        },
        "limitations": [
            {"id": "INDEPENDENT_BINARY",
             "text": "Winner estimates are independent binary "
                     "probabilities, not a normalized race distribution."},
            {"id": "HOLDOUT_UNSERVED",
             "text": "2025 is the frozen holdout and is not served by "
                     "replay or prediction."},
            {"id": "PERMUTATION_IN_SAMPLE",
             "text": "Global permutation evidence is in-sample, not "
                     "out-of-sample."},
            {"id": "NON_CAUSAL",
             "text": "Explanations are associational and model-internal, "
                     "not causal."},
            {"id": "NO_SHAP",
             "text": "SHAP is not part of v1."},
            {"id": "CHECKPOINT_GRANULARITY",
             "text": "Timelines operate at prediction checkpoints, not "
                     "every replay frame."},
            {"id": "TRACK_VIZ_DEFERRED",
             "text": "Track visualization remains deferred."},
            {"id": "NO_EXPLANATION_CACHE",
             "text": "No explanation cache; on-demand latency is "
                     "interactive."},
            {"id": "UNKNOWN_CATEGORY_SYNTHETIC",
             "text": "No natural historical UNKNOWN_CATEGORY example was "
                     "found; behavior is synthetically tested."},
        ],
    }


def _write_json(rel: str, payload: dict) -> str:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    with open(_path(rel), "w", encoding="utf-8") as handle:
        handle.write(text)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> None:
    _guard_file_sha(SERVING_REL, EXPECTED["winner_serving_sha256"],
                    "winner serving artifact")
    phase2 = _read_json("docs/generated/phase2_freeze_manifest.json")
    _guard_value(phase2["matrix"]["content_hash"],
                 EXPECTED["phase2_content_hash"], "Phase-2 content hash")
    _guard_value(phase2["matrix"]["parquet_sha256"],
                 EXPECTED["matrix_parquet_sha256"], "matrix parquet SHA")
    _guard_file_sha(E3_REL, EXPECTED["e3_artifact_sha256"], "E3 artifact")
    models = build_models()
    about = build_about()
    os.makedirs(os.path.join(REPO_ROOT, "frontend", "data"), exist_ok=True)
    models_sha = _write_json(OUT_MODELS, models)
    about_sha = _write_json(OUT_ABOUT, about)
    print(f"models: {OUT_MODELS} sha256={models_sha}")
    print(f"about: {OUT_ABOUT} sha256={about_sha}")


if __name__ == "__main__":
    main()
