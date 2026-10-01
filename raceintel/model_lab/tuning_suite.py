"""M6 tuning suite: execution, machine-readable artifact, report rendering.

Chain of custody: inner tuning records -> selected configuration -> fresh outer
refit -> stored outer experiment result (``write_experiment``) -> tuning
artifact (``tuning_selection_v1.json``) -> human-readable report. Comparisons
against the untuned references are loaded from the stored M3/M5 artifacts:
``logreg_reference_v1.json`` and ``bagged_candidates_v1.json``. No reference
model is rerun. The protected 2025 holdout is never touched.

Runs exactly six tuning units: {LogReg, ExtraTrees} x {D1, D2, D3}. A
representative selected configuration per candidate is refit twice on D1 to
measure determinism.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from raceintel.model_lab import aggregation as AGG
from raceintel.model_lab import data as DATA
from raceintel.model_lab import experiment as EX
from raceintel.model_lab import model_suite as MSUITE
from raceintel.model_lab import results as RES
from raceintel.model_lab import runner as RUN
from raceintel.model_lab import suite as SUITE
from raceintel.model_lab import timing as TIMING
from raceintel.model_lab import tuning as TUNE
from raceintel.model_lab import tuning_candidates as TC
from raceintel.model_lab import tuning_runner as TR
from raceintel.model_lab.errors import ExperimentConfigError
from raceintel.model_lab.protocol import (
    EXPECTED_ABLATION_CONFIG_SHA256,
    EXPECTED_MATRIX_CONTENT_HASH,
    MODEL_LAB_PROTOCOL_VERSION,
    REQUIRED_ABLATION_CONFIG_VERSION,
    REQUIRED_FEATURE_SET_VERSION,
    REQUIRED_LABEL_SET_VERSION,
    REQUIRED_MATRIX_VERSION,
    protocol_semantic_hash,
)

SUITE_SCHEMA_VERSION = "v1"
TUNING_SUITE_FILENAME = "tuning_selection_v1.json"

#: Execution order (linear first, then the closest nonlinear reference).
SUITE_FAMILIES = (TC.LOGREG_FAMILY, TC.EXTRA_TREES_FAMILY)

#: Frozen untuned reference configuration inside each grid.
REFERENCE_CONFIG = {
    TC.LOGREG_FAMILY: {"C": 1.0},
    TC.EXTRA_TREES_FAMILY: {"max_features": "sqrt", "min_samples_leaf": 1,
                            "max_depth": None},
}

#: Outer metric comparison directions.
COMPARISON_DIRECTIONS = {
    "log_loss": "lower",
    "brier": "lower",
    "roc_auc": "higher",
    "pr_auc": "higher",
    "expected_calibration_error": "lower",
    "winner_top1": "higher",
}

#: Aggregate equivalence tolerance for the development selection hierarchy
#: (predeclared; smallest difference treated as "effectively equal").
OUTER_EQUIVALENCE_TOL = 1e-4


def reports_dir(paths=None, root=None) -> Path:
    return SUITE.reports_dir(paths, root)


def default_out(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / TUNING_SUITE_FILENAME


def logreg_suite_path(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / MSUITE.MODEL_SUITE_FILENAME


def bagged_suite_path(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / "bagged_candidates_v1.json"


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (bool, str)) or value is None:
        return value
    if isinstance(value, int):
        return int(value)
    if isinstance(value, float):
        return None if not math.isfinite(value) else float(value)
    try:
        import numpy as np
        if isinstance(value, np.generic):
            return _jsonable(value.item())
        if isinstance(value, np.ndarray):
            return _jsonable(value.tolist())
    except ImportError:  # pragma: no cover
        pass
    return value


def _load_json(path: Path, label: str) -> dict:
    if not path.exists():
        raise ExperimentConfigError(
            f"{label} is missing at {path}; M6 comparison requires stored "
            "artifacts")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_logreg_reference(paths=None, root=None) -> dict:
    return _load_json(logreg_suite_path(paths, root), "M3 LOGREG reference")


def load_bagged_reference(paths=None, root=None) -> dict:
    return _load_json(bagged_suite_path(paths, root), "M5 bagged reference")


def _extract_outer(config, result, dest: str) -> dict:
    calibration_ece = (
        result.calibration["expected_calibration_error"]
        if result.calibration else None)
    return {
        "experiment_id": config.experiment_id,
        "dest": str(dest),
        "status": result.status.value,
        "model_family": config.model_family,
        "model_parameters": config.model_parameters,
        "preprocessing_config": config.preprocessing_config,
        "calibration_config": config.calibration_config,
        "seed": config.seed,
        "train_prevalence": result.metrics.get(
            "train_prevalence", {}).get("value"),
        "training_rows": config.training_rows,
        "training_races": config.training_races,
        "validation_rows": config.validation_rows,
        "validation_races": config.validation_races,
        "n_features_in": result.artifact_refs.get("n_features_in"),
        "transformed_dim": result.artifact_refs.get("transformed_dim"),
        "training_sanity": result.artifact_refs.get("training_sanity"),
        "fit_warnings": result.artifact_refs.get("fit_warnings", []),
        "sklearn_version": result.artifact_refs.get("sklearn_version"),
        "metrics": {k: v for k, v in result.metrics.items()
                    if k != "train_prevalence"},
        "calibration_ece": calibration_ece,
        "calibration": result.calibration,
        "stage_metrics": result.stage_metrics,
        "race_metrics": result.race_metrics,
        "latency": result.latency,
        "fit_seconds": result.fit_seconds,
        "prediction_seconds": result.prediction_seconds,
        "peak_rss_bytes": result.artifact_refs.get("peak_rss_bytes"),
        "warnings": result.warnings,
    }


def _outer(entry: dict) -> dict:
    """Accept either the per-fold node or its outer-result entry."""
    if isinstance(entry, dict) and "outer" in entry and "experiment_id" not in entry:
        return entry["outer"]
    return entry


def _race_macro_value(entry: dict, metric: str):
    entry = _outer(entry)
    payload = entry["metrics"].get(metric, {})
    if payload.get("status") != "OK":
        return None
    return payload.get("race_macro", {}).get("value")


def _state_pooled_value(entry: dict, metric: str):
    entry = _outer(entry)
    payload = entry["metrics"].get(metric, {})
    if payload.get("status") != "OK":
        return None
    return payload.get("state_pooled", {}).get("value")


def _value_for_metric(entry: dict, metric: str):
    entry = _outer(entry)
    if metric == "winner_top1":
        payload = entry["race_metrics"].get("winner_top_k", {})
        if payload.get("status") != "OK":
            return None
        return (payload.get("accuracy") or {}).get("top1")
    if metric == "expected_calibration_error":
        return entry["calibration_ece"]
    return _race_macro_value(entry, metric)


def _aggregate_candidate(per_fold: dict, folds: tuple) -> dict:
    aggregates: dict = {}
    for metric in ("log_loss", "brier", "roc_auc", "pr_auc"):
        aggregates[metric] = _jsonable(AGG.aggregate_folds(
            {fold: _race_macro_value(per_fold[fold], metric)
             for fold in folds}))
        aggregates[f"state_pooled_{metric}"] = _jsonable(AGG.aggregate_folds(
            {fold: _state_pooled_value(per_fold[fold], metric)
             for fold in folds}))
    aggregates["expected_calibration_error"] = _jsonable(AGG.aggregate_folds(
        {fold: _outer(per_fold[fold])["calibration_ece"] for fold in folds}))
    aggregates["winner_top_k"] = {}
    for key, acc_key in (("top1", "top1"), ("top3", "top3")):
        vals = {}
        for fold in folds:
            payload = _outer(per_fold[fold])["race_metrics"].get(
                "winner_top_k", {})
            acc = (payload.get("accuracy") or {}).get(acc_key) \
                if payload.get("status") == "OK" else None
            vals[fold] = acc
        aggregates["winner_top_k"][key] = _jsonable(AGG.aggregate_folds(vals))
    return aggregates


def _aggregate_mean(aggregates: dict, metric: str):
    if metric == "winner_top1":
        return aggregates.get("winner_top_k", {}).get("top1", {}).get("mean")
    return aggregates.get(metric, {}).get("mean")


def _verdict(direction: str, a, b) -> str:
    if a is None or b is None:
        return "NOT_COMPARABLE"
    if abs(a - b) <= OUTER_EQUIVALENCE_TOL:
        return "MATCHES"
    if direction == "lower":
        return "BEATS" if a < b else "DOES NOT BEAT"
    return "BEATS" if a > b else "DOES NOT BEAT"


def _reference_value(ref_per_fold: dict, fold: str, metric: str):
    entry = ref_per_fold.get(fold, {})
    if metric == "winner_top1":
        payload = entry.get("race_metrics", {}).get("winner_top_k", {})
        if payload.get("status") != "OK":
            return None
        return (payload.get("accuracy") or {}).get("top1")
    if metric == "expected_calibration_error":
        return entry.get("calibration_ece")
    payload = entry.get("metrics", {}).get(metric, {})
    if payload.get("status") != "OK":
        return None
    return payload.get("race_macro", {}).get("value")


def _compare_against_reference(*, per_candidate: dict, folds: tuple,
                               ref_per_fold: dict, ref_aggregates: dict,
                               ref_label: str) -> dict:
    out: dict = {}
    for metric, direction in COMPARISON_DIRECTIONS.items():
        node = {"reference": ref_label, "direction": direction,
                "per_fold": {}, "aggregate": {}}
        for fold in folds:
            ref_value = _reference_value(ref_per_fold, fold, metric)
            fold_node = {}
            for family in SUITE_FAMILIES:
                value = _value_for_metric(
                    per_candidate[family]["per_fold"][fold], metric)
                fold_node[family] = {
                    "tuned_value": value,
                    "reference_value": ref_value,
                    "difference": (value - ref_value
                                   if value is not None and ref_value is not None
                                   else None),
                    "verdict": _verdict(direction, value, ref_value),
                }
            node["per_fold"][fold] = fold_node
        agg_node = {}
        for family in SUITE_FAMILIES:
            value = _aggregate_mean(
                per_candidate[family]["aggregates"], metric)
            ref_mean = (ref_aggregates.get("winner_top_k", {}).get(
                "top1", {}).get("mean") if metric == "winner_top1"
                else ref_aggregates.get(metric, {}).get("mean"))
            agg_node[family] = {
                "tuned_mean": value,
                "reference_mean": ref_mean,
                "difference": (value - ref_mean
                               if value is not None and ref_mean is not None
                               else None),
                "verdict": _verdict(direction, value, ref_mean),
            }
        node["aggregate"] = agg_node
        out[metric] = node
    return out


def _head_to_head(*, per_candidate: dict, folds: tuple) -> dict:
    out: dict = {}
    for metric, direction in COMPARISON_DIRECTIONS.items():
        node = {"direction": direction, "per_fold": {}, "aggregate": {}}
        for fold in folds:
            lr = _value_for_metric(
                per_candidate[TC.LOGREG_FAMILY]["per_fold"][fold], metric)
            et = _value_for_metric(
                per_candidate[TC.EXTRA_TREES_FAMILY]["per_fold"][fold], metric)
            node["per_fold"][fold] = {
                "logistic_regression": lr,
                "extra_trees": et,
                "difference": (lr - et if lr is not None and et is not None
                               else None),
                "verdict": _verdict(direction, lr, et),
            }
        lr_mean = _aggregate_mean(
            per_candidate[TC.LOGREG_FAMILY]["aggregates"], metric)
        et_mean = _aggregate_mean(
            per_candidate[TC.EXTRA_TREES_FAMILY]["aggregates"], metric)
        node["aggregate"] = {
            "logistic_regression_mean": lr_mean,
            "extra_trees_mean": et_mean,
            "difference": (lr_mean - et_mean
                           if lr_mean is not None and et_mean is not None
                           else None),
            "verdict": _verdict(direction, lr_mean, et_mean),
        }
        out[metric] = node
    return out


def _winner_counts(node: dict, folds: tuple, left: str, right: str) -> dict:
    counts = {"BEATS": 0, "MATCHES": 0, "DOES NOT BEAT": 0,
              "NOT_COMPARABLE": 0}
    for fold in folds:
        verdict = node["per_fold"][fold]["verdict"]
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts


def _parameter_stability(per_candidate: dict, folds: tuple) -> dict:
    out: dict = {}
    for family in SUITE_FAMILIES:
        selected = {fold: per_candidate[family]["per_fold"][fold][
            "selection"]["selected_config"] for fold in folds}
        keys = {fold: per_candidate[family]["per_fold"][fold][
            "selection"]["selected_key"] for fold in folds}
        boundary = {}
        if family == TC.LOGREG_FAMILY:
            for fold in folds:
                c = selected[fold]["C"]
                boundary[fold] = bool(
                    c == TUNE.LOGREG_C_GRID[0]
                    or c == TUNE.LOGREG_C_GRID[-1])
        else:
            for fold in folds:
                cfg = selected[fold]
                boundary[fold] = bool(
                    cfg["min_samples_leaf"] == TUNE.EXTRA_TREES_MIN_SAMPLES_LEAF[-1]
                    or cfg["max_features"] == 0.5)
        out[family] = {
            "selected_config": selected,
            "selected_key": keys,
            "same_configuration_every_fold": len(set(keys.values())) == 1,
            "distinct_configurations": sorted(set(keys.values())),
            "boundary_selection": boundary,
            "any_boundary_selection": any(boundary.values()),
        }
    return out


def _inner_outer_translation(*, per_candidate: dict, folds: tuple,
                             vs_reference: dict) -> dict:
    """Did inner selection correspond to an outer improvement?"""
    out: dict = {}
    for family in SUITE_FAMILIES:
        ref_key = TUNE.config_key(family, REFERENCE_CONFIG[family])
        rows = []
        for fold in folds:
            node = per_candidate[family]["per_fold"][fold]
            agg = node["selection"].get("config_aggregates", {}).get(ref_key)
            ref_inner = None
            if agg is not None:
                ref_inner = agg.get("mean")
            selected_inner = node["selection"]["selected_mean"]
            inner_delta = (selected_inner - ref_inner
                           if selected_inner is not None and ref_inner is not None
                           else None)
            verified = node.get("reference_outer_log_loss")
            outer_delta = None
            if verified is not None:
                outer_delta = node["outer_log_loss"] - verified
            rows.append({
                "fold": fold,
                "reference_inner_mean": ref_inner,
                "selected_inner_mean": selected_inner,
                "inner_delta": inner_delta,
                "outer_tuned_log_loss": node["outer_log_loss"],
                "outer_reference_log_loss": verified,
                "outer_delta": outer_delta,
                "inner_improved": (inner_delta is not None
                                   and inner_delta < -TUNE.TIE_TOLERANCE),
                "outer_improved": (outer_delta is not None
                                   and outer_delta < -OUTER_EQUIVALENCE_TOL),
            })
        out[family] = rows
    return out


def _decide_recommendation(*, head_to_head: dict,
                           translation: dict, folds: tuple) -> dict:
    """Frozen development hierarchy; no combined weighted score."""
    agg = head_to_head
    lr_ll = agg["log_loss"]["aggregate"]["logistic_regression_mean"]
    et_ll = agg["log_loss"]["aggregate"]["extra_trees_mean"]
    lr_br = agg["brier"]["aggregate"]["logistic_regression_mean"]
    et_br = agg["brier"]["aggregate"]["extra_trees_mean"]
    if None in (lr_ll, et_ll, lr_br, et_br):
        return {"decision": "NO CANDIDATE READY",
                "reason": "primary aggregate metrics incomplete"}
    ll_v = _verdict("lower", lr_ll, et_ll)
    br_v = _verdict("lower", lr_br, et_br)

    if ll_v == "BEATS" and br_v in ("BEATS", "MATCHES"):
        decision, reason = "PROMOTE LOGREG TO M7", (
            "LogReg has the lower aggregate race-macro log loss and is not "
            "worse on Brier")
    elif ll_v == "MATCHES" and br_v == "BEATS":
        decision, reason = "PROMOTE LOGREG TO M7", (
            "primary metrics effectively equal; Brier favors the simpler "
            "LogReg")
    elif ll_v in ("BEATS", "MATCHES") and br_v == "MATCHES":
        decision, reason = "PROMOTE LOGREG TO M7", (
            "primary probability metrics effectively equal; prefer the "
            "simpler model (LogReg)")
    elif ll_v == "DOES NOT BEAT" and br_v == "DOES NOT BEAT":
        decision, reason = "PROMOTE EXTRATREES TO M7", (
            "ExtraTrees has the lower aggregate race-macro log loss and "
            "Brier")
    else:
        # Mixed primary evidence: fall back to fold consistency on log loss.
        lr_beats = sum(
            1 for fold in folds
            if agg["log_loss"]["per_fold"][fold]["verdict"] == "BEATS")
        et_beats = sum(
            1 for fold in folds
            if agg["log_loss"]["per_fold"][fold]["verdict"]
            == "DOES NOT BEAT")
        if lr_beats > et_beats:
            decision, reason = "PROMOTE LOGREG TO M7", (
                "mixed primary aggregates; LogReg wins more folds on "
                "race-macro log loss")
        elif et_beats > lr_beats:
            decision, reason = "PROMOTE EXTRATREES TO M7", (
                "mixed primary aggregates; ExtraTrees wins more folds on "
                "race-macro log loss")
        else:
            decision, reason = "PROMOTE BOTH TO M7", (
                "primary evidence genuinely too close/mixed to justify a "
                "single development candidate")
    return {
        "decision": decision,
        "reason": reason,
        "hierarchy": [
            "race_macro_log_loss", "race_macro_brier", "fold_consistency",
            "calibration", "discrimination", "stage_robustness",
            "synchronized_ranking", "latency_memory", "complexity"],
        "aggregate": {
            "logistic_regression": {"log_loss": lr_ll, "brier": lr_br},
            "extra_trees": {"log_loss": et_ll, "brier": et_br},
        },
        "log_loss_verdict": ll_v,
        "brier_verdict": br_v,
        "evidence_note": (
            "three outer development folds are limited evidence; this is a "
            "selected development candidate under the frozen protocol, not a "
            "final holdout claim"),
    }


def _build_summary(*, task: str, folds: tuple, feature_set: str, seed: int,
                   planned: dict, actual_fits: dict, per_candidate: dict,
                   logreg_reference: dict, bagged_reference: dict,
                   determinism: dict, timings: dict, git_commit) -> dict:
    vs_logreg = _compare_against_reference(
        per_candidate=per_candidate, folds=folds,
        ref_per_fold=logreg_reference.get("per_fold", {}),
        ref_aggregates=logreg_reference.get("aggregates", {}),
        ref_label="logistic_regression (M3 stored artifacts, C=1.0)")
    et_ref_per_fold = bagged_reference.get("per_model", {}).get(
        TC.EXTRA_TREES_FAMILY, {}).get("per_fold", {})
    et_ref_aggregates = bagged_reference.get("per_model", {}).get(
        TC.EXTRA_TREES_FAMILY, {}).get("aggregates", {})
    vs_extratrees = _compare_against_reference(
        per_candidate=per_candidate, folds=folds, ref_per_fold=et_ref_per_fold,
        ref_aggregates=et_ref_aggregates,
        ref_label="extra_trees (M5 stored artifacts, reference config)")
    head_to_head = _head_to_head(per_candidate=per_candidate, folds=folds)
    stability = _parameter_stability(per_candidate, folds)
    translation = _inner_outer_translation(
        per_candidate=per_candidate, folds=folds, vs_reference=vs_logreg)
    recommendation = _decide_recommendation(
        head_to_head=head_to_head, translation=translation, folds=folds)

    candidate_aggregate = {
        family: per_candidate[family]["aggregates"]
        for family in SUITE_FAMILIES}
    return {
        "schema_version": SUITE_SCHEMA_VERSION,
        "task": task,
        "feature_set": feature_set,
        "seed": seed,
        "families": list(SUITE_FAMILIES),
        "folds": list(folds),
        "tuning_objective": "race_macro_log_loss (simple mean over inner folds)",
        "search_spaces": {
            TC.LOGREG_FAMILY: {
                "C": list(TUNE.LOGREG_C_GRID),
                "fixed": dict(TC.LOGREG_FIXED),
                "reference_config": REFERENCE_CONFIG[TC.LOGREG_FAMILY],
            },
            TC.EXTRA_TREES_FAMILY: {
                "max_features": list(TUNE.EXTRA_TREES_MAX_FEATURES),
                "min_samples_leaf": list(TUNE.EXTRA_TREES_MIN_SAMPLES_LEAF),
                "max_depth": list(TUNE.EXTRA_TREES_MAX_DEPTH),
                "fixed": dict(TC.EXTRA_TREES_FIXED),
                "config_count": len(TUNE.EXTRA_TREES_GRID),
                "reference_config": REFERENCE_CONFIG[TC.EXTRA_TREES_FAMILY],
            },
        },
        "tie_break": TUNE.TIE_BREAK_RULE,
        "outer_equivalence_tolerance": OUTER_EQUIVALENCE_TOL,
        "inner_folds": {
            fold: [s.to_dict() for s in TUNE.resolve_inner_splits(fold)]
            for fold in folds},
        "planned_fit_count": planned,
        "actual_fit_count": actual_fits,
        "protocol_version": MODEL_LAB_PROTOCOL_VERSION,
        "protocol_semantic_hash": protocol_semantic_hash(),
        "matrix_version": REQUIRED_MATRIX_VERSION,
        "matrix_content_hash": EXPECTED_MATRIX_CONTENT_HASH,
        "feature_set_version": REQUIRED_FEATURE_SET_VERSION,
        "label_set_version": REQUIRED_LABEL_SET_VERSION,
        "ablation_config_version": REQUIRED_ABLATION_CONFIG_VERSION,
        "ablation_config_sha256": EXPECTED_ABLATION_CONFIG_SHA256,
        "git_commit": git_commit,
        "holdout_accessed": False,
        "holdout_note": "2025 protected final holdout — not evaluated",
        "per_candidate": per_candidate,
        "candidate_aggregate": candidate_aggregate,
        "tuned_vs_logreg_reference": vs_logreg,
        "tuned_vs_extratrees_reference": vs_extratrees,
        "head_to_head_logreg_vs_extratrees": head_to_head,
        "parameter_stability": stability,
        "inner_vs_outer_translation": translation,
        "recommendation": recommendation,
        "determinism": determinism,
        "runtime": timings,
        "peak_rss_bytes": SUITE._peak_rss_bytes(),
        "warnings": [w for family in SUITE_FAMILIES for fold in folds
                     for w in per_candidate[family]["per_fold"][fold][
                         "outer"]["warnings"]],
    }


def run_tuning_suite(*, task: str = TUNE.M6_TASK,
                     families=SUITE_FAMILIES,
                     folds=("D1", "D2", "D3"),
                     feature_set: str = TUNE.M6_FEATURE_SET,
                     seed: int = TUNE.M6_SEED, paths=None, root=None,
                     out=None) -> dict:
    """Execute the M6 tuning suite {(LogReg, ExtraTrees) x D1/D2/D3}."""
    if task != TUNE.M6_TASK:
        raise ExperimentConfigError(
            f"M6 tunes task {TUNE.M6_TASK!r} only; got {task!r}")
    resolved_families = []
    for family in families:
        if family not in SUITE_FAMILIES:
            raise ExperimentConfigError(
                f"M6 tunes {list(SUITE_FAMILIES)} only; got {family!r}")
        resolved_families.append(family)
    if sorted(resolved_families) != sorted(SUITE_FAMILIES):
        raise ExperimentConfigError(
            f"M6 must tune exactly {list(SUITE_FAMILIES)}; got "
            f"{resolved_families!r}")
    folds = SUITE.parse_folds(",".join(folds))
    for fold in folds:
        RUN.resolve_development_fold(fold)

    planned = TUNE.planned_fit_count(folds)
    logreg_reference = load_logreg_reference(paths, root)
    bagged_reference = load_bagged_reference(paths, root)
    canonical = DATA.load_canonical(paths)

    timings: dict = {}
    with TIMING.Timer() as total:
        per_candidate: dict = {}
        actual_fits = {family: {"inner_estimator_fits": 0,
                                "preprocessor_fits": 0,
                                "outer_selected_refits": 0}
                       for family in resolved_families}
        phase_seconds: dict = {}
        for family in resolved_families:
            per_fold: dict = {}
            for fold in folds:
                result = TR.run_tuning_and_outer(
                    family=family, fold=fold, feature_set=feature_set,
                    seed=seed, paths=paths, root=root, canonical=canonical)
                tuning = result["tuning"]
                outer = result["outer"]
                actual_fits[family]["inner_estimator_fits"] += \
                    tuning["estimator_fits"]
                actual_fits[family]["preprocessor_fits"] += \
                    tuning["preprocessor_fits"]
                actual_fits[family]["outer_selected_refits"] += 1
                for phase, seconds in outer["timings"].items():
                    if isinstance(seconds, (int, float)):
                        phase_seconds[phase] = phase_seconds.get(phase, 0.0) \
                            + seconds
                config, stored = RES.read_experiment(outer["dest"])
                outer_entry = _extract_outer(config, stored, outer["dest"])
                ref_key = TUNE.config_key(family, REFERENCE_CONFIG[family])
                reference_outer = None
                if family == TC.LOGREG_FAMILY:
                    reference_outer = _reference_value(
                        logreg_reference.get("per_fold", {}), fold, "log_loss")
                else:
                    reference_outer = _race_macro_value(
                        bagged_reference.get("per_model", {}).get(
                            TC.EXTRA_TREES_FAMILY, {}).get(
                                "per_fold", {}).get(fold, {}), "log_loss")
                per_fold[fold] = {
                    "selection": {**tuning["selection"],
                                  "config_aggregates":
                                      tuning["config_aggregates"]},
                    "inner_folds": tuning["inner_folds"],
                    "outer": outer_entry,
                    "outer_log_loss": _race_macro_value(outer_entry, "log_loss"),
                    "reference_outer_log_loss": reference_outer,
                    "reference_config_key": ref_key,
                    "tuning_seconds": sum(
                        record["estimator_fit_seconds"]
                        + record["preprocessing_fit_seconds"]
                        + record["transform_seconds"]
                        + record["predict_seconds"]
                        + record["evaluation_seconds"]
                        for record in tuning["inner_folds"]),
                }
            per_candidate[family] = {
                "per_fold": per_fold,
                "aggregates": _aggregate_candidate(per_fold, folds),
                "experiments": [
                    {"family": family, "fold": fold,
                     "experiment_id": per_fold[fold]["outer"]["experiment_id"],
                     "dest": per_fold[fold]["outer"]["dest"]}
                    for fold in folds],
            }
        timings["tuning_and_outer_phase_seconds"] = phase_seconds

        with TIMING.Timer() as t:
            determinism = {}
            for family in resolved_families:
                selected = per_candidate[family]["per_fold"][folds[0]][
                    "selection"]["selected_config"]
                first = TR.run_outer_selected(
                    family=family, fold=folds[0],
                    selected_config=selected, feature_set=feature_set,
                    seed=seed, paths=paths, root=root, canonical=canonical,
                    return_predictions=True)
                second = TR.run_outer_selected(
                    family=family, fold=folds[0],
                    selected_config=selected, feature_set=feature_set,
                    seed=seed, paths=paths, root=root, canonical=canonical,
                    return_predictions=True)
                import numpy as _np
                first_metrics = RES.read_experiment(first["dest"])[1].metrics
                second_metrics = RES.read_experiment(second["dest"])[1].metrics
                determinism[family] = {
                    "fold": folds[0],
                    "experiment_id": first["config"].experiment_id,
                    "refit_experiment_id": second["config"].experiment_id,
                    "same_experiment_id": (
                        first["config"].experiment_id
                        == second["config"].experiment_id),
                    "metrics_identical": first_metrics == second_metrics,
                    "max_abs_probability_difference": float(_np.max(_np.abs(
                        first["predictions"] - second["predictions"]))),
                }
        timings["determinism_check_seconds"] = t.seconds
    timings["total_seconds"] = total.seconds

    if paths is not None:
        env = RES.environment_metadata(paths.root)
    elif root is not None:
        env = RES.environment_metadata(root)
    else:
        env = RES.environment_metadata()
    summary = _build_summary(
        task=task, folds=folds, feature_set=feature_set, seed=seed,
        planned=planned, actual_fits=actual_fits, per_candidate=per_candidate,
        logreg_reference=logreg_reference, bagged_reference=bagged_reference,
        determinism=determinism, timings=timings,
        git_commit=env.get("git_commit"))
    summary = _jsonable(summary)
    dest = Path(out) if out is not None else default_out(paths, root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    RES.atomic_write_json(dest, summary)
    summary["_summary_path"] = str(dest)
    return summary


def _fmt(value, digits: int = 6):
    if value is None:
        return "N/A"
    if isinstance(value, float) and not math.isfinite(value):
        return "N/A"
    return f"{value:.{digits}f}"


def render_tuning_report(summary: dict) -> str:
    """Render the human-readable M6 report from the stored summary only."""
    folds = summary["folds"]
    recommendation = summary["recommendation"]
    lines = []
    add = lines.append
    add("# Model Lab Tuning Selection Report (M6)")
    add("")
    add("## DEVELOPMENT MODEL SELECTION")
    add("## OUTER EVALUATION: 2022 / 2023 / 2024")
    add("")
    add("## 2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED")
    add("")
    add("M6 is a controlled, nested temporal tuning stage. It tunes ONLY "
        "Logistic Regression and ExtraTrees using chronology-preserving inner "
        "folds contained entirely inside each outer training history, selects "
        "one configuration per outer fold, refits it on the complete outer "
        "TRAIN history, and evaluates the outer validation season exactly "
        "once through the frozen M2 evaluator. This is NOT final holdout "
        "evaluation.")
    add("")
    add("## 1. Methodology and frozen nested temporal design")
    add("")
    add(f"- objective: {summary['tuning_objective']}; lower is better")
    add(f"- outer folds: {', '.join(folds)} (development only)")
    add(f"- task: `{summary['task']}`; feature set: `{summary['feature_set']}` "
        f"(full 84-feature surface); seed: {summary['seed']}")
    add("- outer validation is NEVER used for scoring, selection, "
        "preprocessing, early stopping, calibration or threshold choice; "
        "rejected configurations never reach the outer evaluator")
    add("- parameter vectors are selected independently per outer fold; the "
        "outer result estimates the tuning PROCEDURE, not one global vector")
    add(f"- protocol {summary['protocol_version']}; matrix content hash "
        f"`{summary['matrix_content_hash'][:12]}…`")
    add("")
    add("## 2. Exact inner folds")
    add("")
    add("| outer fold | inner fold | inner TRAIN | inner VALIDATE |")
    add("| --- | --- | --- | --- |")
    for fold in folds:
        for split in summary["inner_folds"][fold]:
            add(f"| {fold} | {split['inner_fold_id']} | "
                f"{split['train_seasons'][0]}–{split['train_seasons'][-1]} | "
                f"{split['validation_seasons'][0]} |")
    add("")
    add("## 3. Exact search spaces (frozen before results)")
    add("")
    lr = summary["search_spaces"][TC.LOGREG_FAMILY]
    add(f"- Logistic Regression: C in {lr['C']}; fixed "
        f"solver={lr['fixed']['solver']}, max_iter={lr['fixed']['max_iter']}, "
        f"class_weight={lr['fixed']['class_weight']}, "
        f"random_state={lr['fixed']['random_state']}; M3 C=1.0 included")
    et = summary["search_spaces"][TC.EXTRA_TREES_FAMILY]
    add(f"- ExtraTrees: max_features in {et['max_features']}, "
        f"min_samples_leaf in {et['min_samples_leaf']}, max_depth in "
        f"{et['max_depth']} ({et['config_count']} configurations); fixed "
        f"n_estimators={et['fixed']['n_estimators']}, "
        f"criterion={et['fixed']['criterion']}, "
        f"bootstrap={et['fixed']['bootstrap']}, "
        f"class_weight={et['fixed']['class_weight']}, "
        f"n_jobs={et['fixed']['n_jobs']}, "
        f"random_state={et['fixed']['random_state']}; M5 reference "
        "configuration included")
    add("- no adaptive/Bayesian/random search; every configuration is fit on "
        "every inner fold")
    add("")
    add("## 4. Tie-break rule (declared before execution)")
    add("")
    add(f"- tolerance: {TUNE.TIE_BREAK_RULE['tolerance_abs']:.0e} absolute on "
        "mean inner race-macro log loss")
    add(f"- {TUNE.TIE_BREAK_RULE['rule']}")
    add(f"- LogReg: {TUNE.TIE_BREAK_RULE['logistic_regression']}")
    add(f"- ExtraTrees: {TUNE.TIE_BREAK_RULE['extra_trees']}")
    add("")
    add("## 5. Exact fit budget")
    add("")
    add(f"- planned estimator fits: "
        f"{summary['planned_fit_count']['total_estimator_fits']} "
        f"(inner {summary['planned_fit_count']['inner_estimator_fits']}, "
        f"outer selected {summary['planned_fit_count']['outer_selected_refits']}, "
        f"determinism {summary['planned_fit_count']['determinism_refits']})")
    for family in summary["families"]:
        add(f"- actual {family}: inner estimator fits = "
            f"{summary['actual_fit_count'][family]['inner_estimator_fits']}, "
            f"inner preprocessor fits = "
            f"{summary['actual_fit_count'][family]['preprocessor_fits']}, "
            f"outer selected refits = "
            f"{summary['actual_fit_count'][family]['outer_selected_refits']}")
    add("")
    for family in summary["families"]:
        add(f"## 6.{summary['families'].index(family) + 1} Inner tuning "
            f"results — {family}")
        add("")
        for fold in folds:
            node = summary["per_candidate"][family]["per_fold"][fold]
            add(f"### {family} / {fold}: selected "
                f"`{node['selection']['selected_key']}` "
                f"(mean inner log loss "
                f"{_fmt(node['selection']['selected_mean'])}; tie-break "
                f"applied={node['selection']['tie_break_applied']})")
            add("")
            add("| configuration | inner mean | std | min | max | range |")
            add("| --- | --- | --- | --- | --- | --- |")
            for key, agg in node["selection"]["config_aggregates"].items():
                add(f"| {key} | {_fmt(agg['mean'])} | {_fmt(agg['std'])} | "
                    f"{_fmt(agg['min'])} | {_fmt(agg['max'])} | "
                    f"{_fmt(agg['range'])} |")
            add("")
    add("## 7. Parameter stability across outer folds")
    add("")
    for family in summary["families"]:
        node = summary["parameter_stability"][family]
        add(f"- {family}: same configuration every fold = "
            f"{node['same_configuration_every_fold']}; distinct = "
            f"{node['distinct_configurations']}; boundary selection = "
            f"{node['boundary_selection']}; any boundary = "
            f"{node['any_boundary_selection']}")
    add("")
    add("## 8. DEVELOPMENT OUTER RESULTS")
    add("")
    add("**OUTER EVALUATION: 2022 / 2023 / 2024**")
    add("")
    add("**2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED**")
    add("")
    for family in summary["families"]:
        add(f"## 8.{summary['families'].index(family) + 1} {family}")
        add("")
        add("| fold | selected config | log loss | Brier | state-pooled "
            "log loss | state-pooled Brier | ROC-AUC | PR-AUC | ECE | "
            "top-1 | top-3 |")
        add("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
        for fold in folds:
            entry = summary["per_candidate"][family]["per_fold"][fold]
            outer = entry["outer"]
            metrics = outer["metrics"]
            topk = outer["race_metrics"].get("winner_top_k", {})
            acc = topk.get("accuracy", {}) if topk.get("status") == "OK" else {}
            add(f"| {fold} | `{entry['selection']['selected_key']}` | "
                f"{_fmt(_race_macro_value(outer, 'log_loss'))} | "
                f"{_fmt(_race_macro_value(outer, 'brier'))} | "
                f"{_fmt(_state_pooled_value(outer, 'log_loss'))} | "
                f"{_fmt(_state_pooled_value(outer, 'brier'))} | "
                f"{_fmt(_race_macro_value(outer, 'roc_auc'))} | "
                f"{_fmt(_race_macro_value(outer, 'pr_auc'))} | "
                f"{_fmt(outer['calibration_ece'])} | "
                f"{_fmt(acc.get('top1'))} | {_fmt(acc.get('top3'))} |")
            del metrics
        agg = summary["candidate_aggregate"][family]
        add(f"| mean | — | {_fmt(agg['log_loss']['mean'])} | "
            f"{_fmt(agg['brier']['mean'])} | "
            f"{_fmt(agg['state_pooled_log_loss']['mean'])} | "
            f"{_fmt(agg['state_pooled_brier']['mean'])} | "
            f"{_fmt(agg['roc_auc']['mean'])} | {_fmt(agg['pr_auc']['mean'])} | "
            f"{_fmt(agg['expected_calibration_error']['mean'])} | "
            f"{_fmt(agg['winner_top_k']['top1']['mean'])} | "
            f"{_fmt(agg['winner_top_k']['top3']['mean'])} |")
        add("")
        add("Stage race-macro log loss (EARLY / MID / LATE) and synchronized "
            "top-k detail:")
        add("")
        for fold in folds:
            outer = summary["per_candidate"][family]["per_fold"][fold]["outer"]
            stage = outer["stage_metrics"].get("log_loss", {})
            if stage.get("status") == "OK":
                cells = [ _fmt(stage.get(s, {}).get("race_macro", {}).get(
                    "value")) for s in ("EARLY", "MID", "LATE")]
                add(f"- {family}/{fold}: EARLY={cells[0]} MID={cells[1]} "
                    f"LATE={cells[2]}")
        add("")
    add("## 9. Tuned vs untuned (stored M3/M5 references)")
    add("")
    for title, node in (
            ("9.1 tuned LogReg vs M3 fixed LogReg (C=1.0)",
             summary["tuned_vs_logreg_reference"]),
            ("9.2 tuned ExtraTrees vs M5 fixed ExtraTrees",
             summary["tuned_vs_extratrees_reference"])):
        add(f"### {title}")
        add("")
        add("| metric | fold | tuned | reference | diff | verdict |")
        add("| --- | --- | --- | --- | --- | --- |")
        target = TC.LOGREG_FAMILY if "LogReg" in title \
            else TC.EXTRA_TREES_FAMILY
        for metric, metric_node in node.items():
            for fold in folds:
                row = metric_node["per_fold"][fold][target]
                add(f"| {metric} | {fold} | {_fmt(row['tuned_value'])} | "
                    f"{_fmt(row['reference_value'])} | "
                    f"{_fmt(row['difference'])} | {row['verdict']} |")
            agg = metric_node["aggregate"][target]
            add(f"| {metric} | mean | {_fmt(agg['tuned_mean'])} | "
                f"{_fmt(agg['reference_mean'])} | {_fmt(agg['difference'])} | "
                f"{agg['verdict']} |")
        add("")
    add("## 10. Head-to-head: tuned LogReg vs tuned ExtraTrees (frozen "
        "hierarchy)")
    add("")
    add("| metric | fold | LogReg | ExtraTrees | diff | verdict |")
    add("| --- | --- | --- | --- | --- | --- |")
    h2h = summary["head_to_head_logreg_vs_extratrees"]
    for metric, metric_node in h2h.items():
        for fold in folds:
            row = metric_node["per_fold"][fold]
            add(f"| {metric} | {fold} | "
                f"{_fmt(row['logistic_regression'])} | "
                f"{_fmt(row['extra_trees'])} | {_fmt(row['difference'])} | "
                f"{row['verdict']} |")
        agg = metric_node["aggregate"]
        add(f"| {metric} | mean | "
            f"{_fmt(agg['logistic_regression_mean'])} | "
            f"{_fmt(agg['extra_trees_mean'])} | {_fmt(agg['difference'])} | "
            f"{agg['verdict']} |")
    add("")
    add("- no combined weighted score is constructed; no significance is "
        "claimed")
    add("")
    add("## 11. Inner-vs-outer translation")
    add("")
    add("| candidate | fold | ref inner mean | selected inner mean | inner "
        "delta | outer tuned | outer reference | outer delta |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for family, rows in summary["inner_vs_outer_translation"].items():
        for row in rows:
            add(f"| {family} | {row['fold']} | "
                f"{_fmt(row['reference_inner_mean'])} | "
                f"{_fmt(row['selected_inner_mean'])} | "
                f"{_fmt(row['inner_delta'])} | "
                f"{_fmt(row['outer_tuned_log_loss'])} | "
                f"{_fmt(row['outer_reference_log_loss'])} | "
                f"{_fmt(row['outer_delta'])} |")
    add("")
    add("## 12. Determinism")
    add("")
    for family, det in summary["determinism"].items():
        add(f"- {family}: same experiment id = {det['same_experiment_id']}; "
            f"metrics identical = {det['metrics_identical']}; max abs "
            f"probability difference = "
            f"{det['max_abs_probability_difference']:.3e}")
    add("")
    add("## 13. Runtime, memory, artifacts")
    add("")
    add(f"- suite wall time: "
        f"{summary['runtime'].get('total_seconds', 0):.1f} s")
    add(f"- determinism refit time: "
        f"{summary['runtime'].get('determinism_check_seconds', 0):.1f} s")
    rss = summary.get("peak_rss_bytes")
    add(f"- peak RSS: {rss / 1e9:.2f} GB" if rss
        else "- peak RSS: NOT MEASURED")
    add("")
    for family in summary["families"]:
        for entry in summary["per_candidate"][family]["experiments"]:
            add(f"- {entry['family']}/{entry['fold']}: "
                f"`{entry['experiment_id']}`")
    add("")
    add(f"- tuning artifact: "
        f"`data/v2/model_lab/reports/{TUNING_SUITE_FILENAME}`"
        " (machine-readable; this document was rendered from it)")
    add(f"- M3 reference used for 9.1; M5 reference used for 9.2; neither was "
        "rerun")
    add("")
    add("## 14. Limitations")
    add("")
    add("- three outer development folds are limited evidence; inner folds "
        "are nested and not independent")
    add("- state rows are not independent; headline metrics use race-macro "
        "aggregation")
    add("- tuning is a small predeclared grid, not exhaustive optimization")
    add("- raw probabilities only; no calibration was fitted in M6")
    add("- 2025 was not evaluated and remains the protected final holdout")
    add("")
    add("## 15. Development candidate selection")
    add("")
    add(f"**{recommendation['decision']}**")
    add("")
    add(f"- reason: {recommendation['reason']}")
    add(f"- log loss verdict: {recommendation['log_loss_verdict']}; Brier "
        f"verdict: {recommendation['brier_verdict']}")
    add(f"- evidence note: {recommendation['evidence_note']}")
    add("")
    return "\n".join(lines) + "\n"
