"""M7 Logistic Regression regularization boundary resolution + config freeze.

M6 selected Logistic Regression with ``C=0.03`` on D1/D2/D3, and 0.03 was the
LOWER boundary of the M6 grid. M7 exists only to resolve that one boundary
condition and to freeze a single development-only Logistic Regression
configuration policy. It does NOT reopen candidate selection, does not touch
ExtraTrees, does not start calibration and never touches the protected 2025
holdout.

It searches exactly one predeclared grid:

    C in {0.003, 0.01, 0.03, 0.1}

with race-macro log loss as the ONLY objective, using the EXACT M6 inner
folds, the EXACT M6 train-fitted preprocessing (fit once per inner fold and
reused across the four C values) and the frozen LogReg semantics (only ``C``
varies). The outer validation season never participates in C selection: for
each outer fold a single C is selected from inner folds only, then fresh outer
preprocessing + a fresh LogReg are fit on the complete outer TRAIN history and
the selected C is evaluated exactly once through the canonical M2 evaluator.

After the three outer folds, a single global development-frozen ``C`` is
derived from development information ONLY (per-fold selected C majority, else
the aggregate inner log loss, with the predeclared smaller-C tie-break). Outer
validation metrics are used to evaluate the tuning PROCEDURE, never to pick the
final C. No recursive grid expansion is permitted.
"""

from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path

import numpy as np

from v2.model_lab import aggregation as AGG
from v2.model_lab import data as DATA
from v2.model_lab import preprocessing as PRE
from v2.model_lab import results as RES
from v2.model_lab import runner as RUN
from v2.model_lab import timing as TIMING
from v2.model_lab import tuning as TUNE
from v2.model_lab import tuning_candidates as TC
from v2.model_lab import tuning_runner as TR
from v2.model_lab import tuning_suite as TSUITE
from v2.model_lab.errors import ExperimentConfigError, ProtectedHoldoutError
from v2.model_lab.inner_splits import (
    inner_split_frame,
    resolve_inner_splits,
)
from v2.model_lab.protocol import (
    EXPECTED_ABLATION_CONFIG_SHA256,
    EXPECTED_MATRIX_CONTENT_HASH,
    EXPECTED_MATRIX_PARQUET_SHA256,
    EXPECTED_MANIFEST_SHA256,
    MODEL_LAB_PROTOCOL_VERSION,
    PROTECTED_HOLDOUT_SEASON,
    REQUIRED_ABLATION_CONFIG_VERSION,
    REQUIRED_FEATURE_SET_VERSION,
    REQUIRED_LABEL_SET_VERSION,
    REQUIRED_MATRIX_VERSION,
    protocol_semantic_hash,
)

#: One-time declared boundary-resolution grid. Frozen before execution.
BOUNDARY_C_GRID = (0.003, 0.01, 0.03, 0.1)
BOUNDARY_GRID = tuple({"C": c} for c in BOUNDARY_C_GRID)

#: The M6 selected boundary value that triggered M7 (control inside the grid).
M6_LOWER_BOUNDARY_C = 0.03

#: The new lower boundary introduced by this one-time extension.
NEW_LOWER_BOUNDARY_C = 0.003

#: Development task/feature/seed contract (identical to M3/M6).
M7_TASK = "winner"
M7_FEATURE_SET = "ALL_84"
M7_SEED = 42

#: Absolute numerical tolerance for "effectively equal" mean inner log loss.
BOUNDARY_TIE_TOLERANCE = 1e-6

#: Reliability diagnostics bin count (canonical evaluator default).
RELIABILITY_BINS = 10

#: Frozen outer comparison equivalence tolerance (same as M6).
OUTER_EQUIVALENCE_TOL = 1e-4

#: Frozen objective (declared before execution).
BOUNDARY_OBJECTIVE = "race_macro_log_loss (simple mean over inner folds)"

#: Frozen tie-break (declared before execution).
BOUNDARY_TIE_BREAK = {
    "tolerance_abs": BOUNDARY_TIE_TOLERANCE,
    "objective": BOUNDARY_OBJECTIVE + " (lower is better)",
    "rule": "among configurations whose mean is within tolerance of the best "
            "mean, prefer the smaller C (stronger L2 regularization / simpler "
            "configuration)",
    "frozen_before_results": True,
}

#: Frozen boundary classification labels.
BOUNDARY_LABELS = {
    0.003: "LOWER_BOUNDARY",
    0.01: "INTERIOR",
    0.03: "INTERIOR_PREVIOUS_BOUNDARY",
    0.1: "UPPER_CONTROL",
}

#: Frozen boundary-status rule (declared before execution): the M6 boundary
#: issue remains active iff the new lower boundary is selected by a strict
#: majority of outer folds.
BOUNDARY_ACTIVE_MIN_FOLDS = 2

#: Frozen global development configuration-freeze rule (declared before
#: execution). It may consume ONLY per-fold selected C values and inner tuning
#: aggregates; outer validation metrics and 2025 are forbidden inputs.
GLOBAL_FREEZE_RULE = {
    "step_1": "consider the C selected independently in D1/D2/D3",
    "step_2": "choose the value selected by a strict majority of outer folds",
    "step_3": "otherwise choose the C with the lowest mean inner tuning log "
              "loss aggregating all eligible inner evaluations across "
              "D1/D2/D3",
    "step_4": "if effectively tied within 1e-06, choose the smaller C",
    "outer_validation_used": False,
    "holdout_used": False,
    "frozen_before_results": True,
}

SUITE_SCHEMA_VERSION = "v1"
BOUNDARY_SUITE_FILENAME = "logreg_boundary_resolution_v1.json"

#: Immutable Phase-2/M0 boundary artifacts byte-hashed for the artifact.
PHASE2_REL = "data/v2/processed/model_matrix/matrix_version=v1"
PROTOCOL_JSON_REL = "docs/generated/model_lab_protocol_v1.json"
FREEZE_MANIFEST_REL = "docs/generated/phase2_freeze_manifest.json"


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


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
        if isinstance(value, np.generic):
            return _jsonable(value.item())
        if isinstance(value, np.ndarray):
            return _jsonable(value.tolist())
    except ImportError:  # pragma: no cover
        pass
    return value


def _peak_rss_bytes():
    return TR._peak_rss_bytes()


def reports_dir(paths=None, root=None) -> Path:
    return TSUITE.reports_dir(paths, root)


def default_out(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / BOUNDARY_SUITE_FILENAME


def m6_artifact_path(paths=None, root=None) -> Path:
    return TSUITE.default_out(paths, root)


def m3_reference_path(paths=None, root=None) -> Path:
    return TSUITE.logreg_suite_path(paths, root)


def config_key(config: dict) -> str:
    return TUNE.config_key(TC.LOGREG_FAMILY, config)


def planned_fit_count(folds=("D1", "D2", "D3")) -> dict:
    """Exact pre-execution estimator-fit budget (estimator fits only)."""
    per_fold: dict = {}
    inner_total = 0
    for fold in folds:
        inner = resolve_inner_splits(fold)
        fits = len(inner) * len(BOUNDARY_GRID)
        per_fold[fold] = {"inner_folds": len(inner),
                          "configs": len(BOUNDARY_GRID),
                          "estimator_fits": fits}
        inner_total += fits
    outer_fits = len(folds)
    determinism_fits = 2
    return {
        "per_fold": per_fold,
        "inner_estimator_fits": inner_total,
        "outer_selected_refits": outer_fits,
        "determinism_refits": determinism_fits,
        "total_estimator_fits": inner_total + outer_fits + determinism_fits,
        "inner_preprocessor_fits": sum(
            len(resolve_inner_splits(fold)) for fold in folds),
        "search_executes_every_config": True,
        "adaptive_search": False,
        "notes": "preprocessing fit once per inner fold and reused across the "
                 f"{len(BOUNDARY_GRID)} C values; estimator fresh per C",
    }


# ---------------------------------------------------------------------------
# inner boundary search (LogReg only; outer validation absent)
# ---------------------------------------------------------------------------


def _aggregate_config_scores(scores: dict) -> dict:
    out: dict = {}
    for config in BOUNDARY_GRID:
        key = config_key(config)
        values = {name: scores[name][key] for name in scores}
        out[key] = {"config": dict(config), **AGG.aggregate_folds(values)}
    return out


def tune_logreg_boundary(canonical: DATA.CanonicalMatrix, outer_fold: str, *,
                         task: str = M7_TASK,
                         feature_set: str = M7_FEATURE_SET) -> dict:
    """Search the one-time boundary grid on inner folds only."""
    if task != M7_TASK:
        raise ExperimentConfigError(
            f"M7 resolves task {M7_TASK!r} only; got {task!r}")
    if feature_set != M7_FEATURE_SET:
        raise ExperimentConfigError(
            f"M7 resolves feature set {M7_FEATURE_SET!r} only; got "
            f"{feature_set!r}")
    splits = resolve_inner_splits(outer_fold)
    scores: dict = {s.inner_fold_id: {} for s in splits}
    inner_records: list = []
    estimator_fits = 0
    preprocessor_fits = 0

    for split in splits:
        (X_train, y_train, _meta_train, X_val, y_val,
         meta_val) = inner_split_frame(canonical, split, task, feature_set)
        seasons = {int(s) for s in
                   (*split.train_seasons, *split.validation_seasons)}
        if PROTECTED_HOLDOUT_SEASON in seasons:
            raise ProtectedHoldoutError(
                f"{split.inner_fold_id}: protected holdout reached M7 tuning")

        with TIMING.Timer() as t_pre:
            preprocessor = PRE.fit_preprocessor(X_train, canonical.schema)
        preprocessor_fits += 1
        with TIMING.Timer() as t_tr:
            Z_train = preprocessor.transform(X_train)
            Z_val = preprocessor.transform(X_val)

        yv = np.asarray(y_val.astype(float), dtype=float)
        race_ids = np.asarray(meta_val["race_id"].astype(str))
        y_train_arr = np.asarray(y_train.astype(float), dtype=float)
        fold_configs: dict = {}
        fold_fit_seconds = 0.0
        fold_predict_seconds = 0.0
        fold_eval_seconds = 0.0
        fold_warnings: list = []

        for config in BOUNDARY_GRID:
            key = config_key(config)
            with TIMING.Timer() as t_fit:
                model = TC.fit_fresh_model(
                    TC.LOGREG_FAMILY, config, X_train, y_train_arr,
                    preprocessor=preprocessor,
                    precomputed_matrix=Z_train)
            estimator_fits += 1
            fold_fit_seconds += t_fit.seconds
            with TIMING.Timer() as t_pred:
                probabilities = model.predict_positive_probability(X_val)
            fold_predict_seconds += t_pred.seconds
            if not np.all(np.isfinite(probabilities)):
                raise ExperimentConfigError(
                    f"{split.inner_fold_id} {key}: non-finite probabilities")
            with TIMING.Timer() as t_eval:
                race_macro = AGG.race_macro(
                    yv, probabilities, race_ids, "log_loss")
            fold_eval_seconds += t_eval.seconds
            value = race_macro["value"]
            scores[split.inner_fold_id][key] = float(value)
            for message in model.fit_warnings:
                fold_warnings.append(f"{key}: {message}")
            fold_configs[key] = {
                "hyperparameters": dict(config),
                "race_macro_log_loss": float(value),
                "n_races": int(race_macro["n_races"]),
                "n_races_defined": int(race_macro["n_races_defined"]),
                "n_states": int(race_macro["n_states"]),
                "warnings": list(model.fit_warnings),
            }

        inner_records.append({
            "inner_fold_id": split.inner_fold_id,
            "train_seasons": list(split.train_seasons),
            "validation_seasons": list(split.validation_seasons),
            "train_rows": int(len(X_train)),
            "validation_rows": int(len(X_val)),
            "preprocessing_fit_seconds": t_pre.seconds,
            "transform_seconds": t_tr.seconds,
            "estimator_fit_seconds": fold_fit_seconds,
            "predict_seconds": fold_predict_seconds,
            "evaluation_seconds": fold_eval_seconds,
            "configs": fold_configs,
        })
        del Z_train, Z_val, preprocessor

    aggregates = _aggregate_config_scores(scores)
    selection = TUNE.select_configuration(TC.LOGREG_FAMILY, aggregates)
    selection.update({
        "family": TC.LOGREG_FAMILY,
        "outer_fold": outer_fold,
        "objective": BOUNDARY_OBJECTIVE,
        "estimator_fits": estimator_fits,
        "preprocessor_fits": preprocessor_fits,
        "boundary_label": classify_boundary_c(
            selection["selected_config"]["C"]),
    })
    return {
        "family": TC.LOGREG_FAMILY,
        "outer_fold": outer_fold,
        "feature_set": feature_set,
        "task": task,
        "inner_folds": inner_records,
        "config_aggregates": aggregates,
        "selection": selection,
        "estimator_fits": estimator_fits,
        "preprocessor_fits": preprocessor_fits,
    }


# ---------------------------------------------------------------------------
# boundary classification + frozen global configuration rule
# ---------------------------------------------------------------------------


def classify_boundary_c(c: float) -> str:
    for value, label in BOUNDARY_LABELS.items():
        if abs(float(c) - value) <= 1e-12:
            return label
    raise ExperimentConfigError(
        f"C={c!r} is not in the frozen M7 boundary grid {BOUNDARY_C_GRID}")


def boundary_status(selected_by_fold: dict) -> dict:
    """Frozen RESOLVED/REMAINS ACTIVE rule (declared before execution)."""
    lower = [fold for fold, c in selected_by_fold.items()
             if abs(float(c) - NEW_LOWER_BOUNDARY_C) <= 1e-12]
    active = len(lower) >= BOUNDARY_ACTIVE_MIN_FOLDS
    return {
        "status": "REMAINS ACTIVE" if active else "RESOLVED",
        "new_lower_boundary_c": NEW_LOWER_BOUNDARY_C,
        "folds_selecting_new_lower_boundary": sorted(lower),
        "rule": "REMAINS ACTIVE iff the new lower boundary is selected by at "
                f"least {BOUNDARY_ACTIVE_MIN_FOLDS} outer folds",
        "recursive_search": False,
    }


def resolve_global_c(*, selected_configs: dict, inner_aggregates: dict) -> dict:
    """Frozen development-only global configuration rule.

    ``selected_configs`` maps outer fold -> selected C (development
    information). ``inner_aggregates`` maps configuration key -> the
    ``TUNE.aggregate_scores``-shaped node for that configuration. Outer
    validation metrics and the protected final holdout are not parameters and
    cannot be inspected.
    """
    folds = sorted(selected_configs)
    if not folds:
        raise ExperimentConfigError("global freeze rule needs >= 1 outer fold")
    counts: dict = {}
    for fold in folds:
        c = selected_configs[fold]
        counts[c] = counts.get(c, 0) + 1
    n = len(folds)
    majority = sorted(
        [(c, cnt) for c, cnt in counts.items() if cnt * 2 > n],
        key=lambda item: item[0])
    if majority:
        c, cnt = majority[0]
        return {
            "global_c": c,
            "rule": "strict_majority_of_outer_folds",
            "selected_counts": counts,
            "detail": f"{cnt}/{n} outer folds selected C={c:g}",
            "outer_validation_used": False,
            "holdout_used": False,
        }

    defined = {k: v for k, v in inner_aggregates.items()
               if v.get("mean") is not None and math.isfinite(v["mean"])}
    if not defined:
        raise ExperimentConfigError(
            "global freeze fallback: no finite inner aggregate available")
    best_mean = min(v["mean"] for v in defined.values())
    within = [k for k, v in defined.items()
              if v["mean"] <= best_mean + BOUNDARY_TIE_TOLERANCE]
    chosen_key = min(
        within,
        key=lambda k: (defined[k]["config"]["C"]
                       if defined[k]["config"]["C"] > 0
                       else float("inf")))
    return {
        "global_c": defined[chosen_key]["config"]["C"],
        "rule": "aggregate_inner_log_loss_fallback",
        "selected_counts": counts,
        "detail": (f"no strict majority; lowest aggregate inner mean "
                   f"({best_mean:.10f}) at {chosen_key}"),
        "aggregate_inner_mean": best_mean,
        "within_tolerance": sorted(within),
        "tie_break_applied": len(within) > 1,
        "outer_validation_used": False,
        "holdout_used": False,
    }


# ---------------------------------------------------------------------------
# outer evaluation extraction + comparisons
# ---------------------------------------------------------------------------


def _race_macro(result, metric):
    payload = result.metrics.get(metric, {})
    if payload.get("status") != "OK":
        return None
    return payload.get("race_macro", {}).get("value")


def _state_pooled(result, metric):
    payload = result.metrics.get(metric, {})
    if payload.get("status") != "OK":
        return None
    return payload.get("state_pooled", {}).get("value")


def _topk(result, key):
    payload = result.race_metrics.get("winner_top_k", {}) \
        if result.race_metrics else {}
    if payload.get("status") != "OK":
        return None
    return (payload.get("accuracy") or {}).get(key)


def _extract_outer(config, result, dest) -> dict:
    calibration = result.calibration or {}
    return {
        "experiment_id": config.experiment_id,
        "dest": str(dest),
        "status": result.status.value,
        "model_family": config.model_family,
        "model_parameters": dict(config.model_parameters),
        "calibration_config": dict(config.calibration_config),
        "seed": config.seed,
        "training_rows": config.training_rows,
        "training_races": config.training_races,
        "validation_rows": config.validation_rows,
        "validation_races": config.validation_races,
        "train_prevalence": result.metrics.get(
            "train_prevalence", {}).get("value"),
        "n_features_in": result.artifact_refs.get("n_features_in"),
        "transformed_dim": result.artifact_refs.get("transformed_dim"),
        "sklearn_version": result.artifact_refs.get("sklearn_version"),
        "training_sanity": result.artifact_refs.get("training_sanity"),
        "fit_warnings": result.artifact_refs.get("fit_warnings", []),
        "race_macro": {
            metric: _race_macro(result, metric)
            for metric in ("log_loss", "brier", "roc_auc", "pr_auc")},
        "state_pooled": {
            metric: _state_pooled(result, metric)
            for metric in ("log_loss", "brier", "roc_auc", "pr_auc")},
        "calibration": {
            "expected_calibration_error": calibration.get(
                "expected_calibration_error"),
            "brier": calibration.get("brier"),
            "n": calibration.get("n"),
            "n_bins": calibration.get("n_bins"),
            "binning": calibration.get("binning"),
            "bins": calibration.get("bins"),
        },
        "stages": result.stage_metrics or {},
        "synchronized": result.race_metrics or {},
        "latency": result.latency,
        "fit_seconds": result.fit_seconds,
        "prediction_seconds": result.prediction_seconds,
        "peak_rss_bytes": result.artifact_refs.get("peak_rss_bytes"),
        "warnings": list(result.warnings),
    }


def _verdict(direction: str, a, b) -> str:
    if a is None or b is None:
        return "NOT_COMPARABLE"
    if abs(a - b) <= OUTER_EQUIVALENCE_TOL:
        return "MATCHES"
    if direction == "lower":
        return "BEATS" if a < b else "DOES NOT BEAT"
    return "BEATS" if a > b else "DOES NOT BEAT"


def _compare_metric(*, metric: str, direction: str,
                    m7_per_fold: dict, ref_per_fold: dict, folds,
                    m7_aggregate_mean, ref_aggregate_mean) -> dict:
    node = {"metric": metric, "direction": direction, "per_fold": {}}
    for fold in folds:
        a = m7_per_fold.get(fold)
        b = ref_per_fold.get(fold)
        node["per_fold"][fold] = {
            "m7_value": a,
            "reference_value": b,
            "difference": (a - b if a is not None and b is not None else None),
            "verdict": _verdict(direction, a, b),
        }
    node["aggregate"] = {
        "m7_mean": m7_aggregate_mean,
        "reference_mean": ref_aggregate_mean,
        "difference": (m7_aggregate_mean - ref_aggregate_mean
                       if m7_aggregate_mean is not None
                       and ref_aggregate_mean is not None else None),
        "verdict": _verdict(direction, m7_aggregate_mean, ref_aggregate_mean),
    }
    return node


def _per_fold_values(per_fold: dict, metric: str) -> dict:
    """Extract a metric value from M7 per-fold outer entries."""
    out = {}
    for fold, node in per_fold.items():
        outer = node["outer"]
        if metric == "log_loss":
            out[fold] = outer["race_macro"]["log_loss"]
        elif metric == "brier":
            out[fold] = outer["race_macro"]["brier"]
        elif metric == "roc_auc":
            out[fold] = outer["race_macro"]["roc_auc"]
        elif metric == "pr_auc":
            out[fold] = outer["race_macro"]["pr_auc"]
        elif metric == "expected_calibration_error":
            out[fold] = outer["calibration"]["expected_calibration_error"]
        elif metric == "winner_top1":
            out[fold] = _topk_from_node(outer, "top1")
        else:  # pragma: no cover - guarded by callers
            raise ExperimentConfigError(f"unknown comparison metric {metric!r}")
    return out


def _topk_from_node(outer: dict, key: str):
    payload = outer["synchronized"].get("winner_top_k", {})
    if payload.get("status") != "OK":
        return None
    return (payload.get("accuracy") or {}).get(key)


def _m6_reference_per_fold(m6_summary: dict, metric: str) -> dict:
    per_fold = m6_summary["per_candidate"][TC.LOGREG_FAMILY]["per_fold"]
    out = {}
    for fold, node in per_fold.items():
        outer = node["outer"]
        if metric == "expected_calibration_error":
            out[fold] = outer["calibration_ece"]
        elif metric == "winner_top1":
            payload = outer["race_metrics"].get("winner_top_k", {})
            out[fold] = ((payload.get("accuracy") or {}).get("top1")
                         if payload.get("status") == "OK" else None)
        else:
            payload = outer["metrics"].get(metric, {})
            out[fold] = (payload.get("race_macro", {}).get("value")
                         if payload.get("status") == "OK" else None)
    return out


def _m6_reference_aggregate(m6_summary: dict, metric: str):
    agg = m6_summary["candidate_aggregate"][TC.LOGREG_FAMILY]
    if metric == "log_loss":
        return agg["log_loss"]["mean"]
    if metric == "brier":
        return agg["brier"]["mean"]
    if metric == "roc_auc":
        return agg["roc_auc"]["mean"]
    if metric == "pr_auc":
        return agg["pr_auc"]["mean"]
    if metric == "expected_calibration_error":
        return agg["expected_calibration_error"]["mean"]
    if metric == "winner_top1":
        return agg["winner_top_k"]["top1"]["mean"]
    raise ExperimentConfigError(f"unknown M6 metric {metric!r}")


def _m3_reference_per_fold(m3_summary: dict, metric: str) -> dict:
    out = {}
    for fold, node in m3_summary["per_fold"].items():
        if metric == "expected_calibration_error":
            out[fold] = node["calibration_ece"]
        elif metric == "winner_top1":
            payload = node["race_metrics"].get("winner_top_k", {})
            out[fold] = ((payload.get("accuracy") or {}).get("top1")
                         if payload.get("status") == "OK" else None)
        else:
            payload = node["metrics"].get(metric, {})
            out[fold] = (payload.get("race_macro", {}).get("value")
                         if payload.get("status") == "OK" else None)
    return out


def _m3_reference_aggregate(m3_summary: dict, metric: str):
    agg = m3_summary["aggregates"]
    if metric == "expected_calibration_error":
        return agg["expected_calibration_error"]["mean"]
    if metric == "winner_top1":
        return agg["winner_top_k"]["top1"]["mean"]
    return agg[metric]["mean"]


COMPARISON_METRICS = (
    ("log_loss", "lower", "PRIMARY"),
    ("brier", "lower", "PRIMARY"),
    ("roc_auc", "higher", "SECONDARY"),
    ("pr_auc", "higher", "SECONDARY"),
    ("expected_calibration_error", "lower", "SECONDARY"),
    ("winner_top1", "higher", "SECONDARY"),
)


def _build_comparison(*, per_fold: dict, m7_aggregates: dict, folds,
                      reference_per_fold_getter, reference_aggregate_getter,
                      reference_label: str) -> dict:
    node: dict = {"reference": reference_label, "metrics": {}}
    for metric, direction, tier in COMPARISON_METRICS:
        m7_values = _per_fold_values(per_fold, metric)
        ref_values = reference_per_fold_getter(metric)
        m7_mean = _mean([m7_values[f] for f in folds])
        ref_mean = reference_aggregate_getter(metric)
        node["metrics"][metric] = {
            "tier": tier,
            **_compare_metric(
                metric=metric, direction=direction, m7_per_fold=m7_values,
                ref_per_fold=ref_values, folds=folds,
                m7_aggregate_mean=m7_mean, ref_aggregate_mean=ref_mean),
        }
    return node


def _mean(values):
    arr = [v for v in values if v is not None and math.isfinite(v)]
    return float(np.mean(arr)) if arr else None


def _aggregate_outer(per_fold: dict, folds) -> dict:
    race = {}
    for metric in ("log_loss", "brier", "roc_auc", "pr_auc"):
        race[metric] = _jsonable(AGG.aggregate_folds(
            {f: per_fold[f]["outer"]["race_macro"][metric] for f in folds}))
        race[f"state_pooled_{metric}"] = _jsonable(AGG.aggregate_folds(
            {f: per_fold[f]["outer"]["state_pooled"][metric]
             for f in folds}))
    race["expected_calibration_error"] = _jsonable(AGG.aggregate_folds(
        {f: per_fold[f]["outer"]["calibration"]["expected_calibration_error"]
         for f in folds}))
    race["winner_top_k"] = {
        key: _jsonable(AGG.aggregate_folds(
            {f: _topk_from_node(per_fold[f]["outer"], key) for f in folds}))
        for key in ("top1", "top3")}
    return race


def _immutability_report(root: Path) -> dict:
    out = root / PHASE2_REL
    return {
        "phase2_parquet_byte_hash": _sha256_file(
            out / "model_matrix.parquet"),
        "phase2_manifest_byte_hash": _sha256_file(out / "manifest.json"),
        "f16_ablation_byte_hash": _sha256_file(out / "ablation_config.json"),
        "phase2_matrix_content_hash": EXPECTED_MATRIX_CONTENT_HASH,
        "m0_protocol_semantic_hash": protocol_semantic_hash(),
        "m0_protocol_json_byte_hash": _sha256_file(
            root / PROTOCOL_JSON_REL),
        "phase2_freeze_manifest_byte_hash": _sha256_file(
            root / FREEZE_MANIFEST_REL),
        "expected": {
            "phase2_matrix_parquet_sha256": EXPECTED_MATRIX_PARQUET_SHA256,
            "phase2_manifest_sha256": EXPECTED_MANIFEST_SHA256,
            "f16_ablation_sha256": EXPECTED_ABLATION_CONFIG_SHA256,
        },
    }


# ---------------------------------------------------------------------------
# suite orchestration
# ---------------------------------------------------------------------------


def run_boundary_and_outer(*, fold: str, paths=None, root=None,
                           canonical: DATA.CanonicalMatrix | None = None,
                           return_predictions: bool = False) -> dict:
    """One M7 unit: inner boundary search -> select C -> fresh outer eval once."""
    RUN.resolve_development_fold(fold)
    if canonical is None:
        canonical = DATA.load_canonical(paths)
    tuning = tune_logreg_boundary(canonical, fold)
    selected = tuning["selection"]["selected_config"]
    outer = TR.run_outer_selected(
        family=TC.LOGREG_FAMILY, fold=fold, selected_config=selected,
        paths=paths, root=root, canonical=canonical,
        return_predictions=return_predictions)
    return {"tuning": tuning, "outer": outer}


def _frozen_configuration(global_c: float) -> dict:
    return {
        "model_family": TC.LOGREG_FAMILY,
        "estimator": "LogisticRegression",
        "feature_set": M7_FEATURE_SET,
        "task": M7_TASK,
        "preprocessing": PRE.preprocessing_contract_dict(),
        "solver": TC.LOGREG_FIXED["solver"],
        "max_iter": TC.LOGREG_FIXED["max_iter"],
        "class_weight": TC.LOGREG_FIXED["class_weight"],
        "random_state": TC.LOGREG_FIXED["random_state"],
        "penalty": "l2 (sklearn default, not passed explicitly)",
        "C": global_c,
        "probability_semantics": "INDEPENDENT_BINARY",
        "seed": M7_SEED,
    }


def run_boundary_suite(*, task: str = M7_TASK, folds=("D1", "D2", "D3"),
                       feature_set: str = M7_FEATURE_SET,
                       seed: int = M7_SEED, paths=None, root=None,
                       out=None) -> dict:
    """Execute the one-time M7 boundary resolution over D1/D2/D3."""
    if task != M7_TASK:
        raise ExperimentConfigError(
            f"M7 resolves task {M7_TASK!r} only; got {task!r}")
    if feature_set != M7_FEATURE_SET:
        raise ExperimentConfigError(
            f"M7 uses feature set {M7_FEATURE_SET!r} only; got "
            f"{feature_set!r}")
    if seed != M7_SEED:
        raise ExperimentConfigError(
            f"M7 uses seed {M7_SEED!r} only; got {seed!r}")
    folds = tuple(folds)
    if not folds:
        raise ExperimentConfigError("M7 needs at least one outer fold")
    for fold in folds:
        RUN.resolve_development_fold(fold)

    planned = planned_fit_count(folds)
    m6_summary = json.loads(m6_artifact_path(paths, root).read_text())
    m3_summary = json.loads(m3_reference_path(paths, root).read_text())
    canonical = DATA.load_canonical(paths)

    timings: dict = {}
    phase_seconds: dict = {}
    actual_fits = {"inner_estimator_fits": 0, "preprocessor_fits": 0,
                   "outer_selected_refits": 0, "determinism_refits": 0}
    per_fold: dict = {}
    with TIMING.Timer() as total:
        for fold in folds:
            unit = run_boundary_and_outer(
                fold=fold, paths=paths, root=root, canonical=canonical)
            tuning = unit["tuning"]
            outer = unit["outer"]
            actual_fits["inner_estimator_fits"] += tuning["estimator_fits"]
            actual_fits["preprocessor_fits"] += tuning["preprocessor_fits"]
            actual_fits["outer_selected_refits"] += 1
            for phase, seconds in outer["timings"].items():
                if isinstance(seconds, (int, float)):
                    phase_seconds[phase] = phase_seconds.get(phase, 0.0) \
                        + seconds
            config, stored = RES.read_experiment(outer["dest"])
            outer_entry = _extract_outer(config, stored, outer["dest"])
            per_fold[fold] = {
                "selection": {**tuning["selection"],
                              "config_aggregates":
                                  tuning["config_aggregates"]},
                "inner_folds": tuning["inner_folds"],
                "outer": outer_entry,
                "tuning_seconds": sum(
                    record["estimator_fit_seconds"]
                    + record["preprocessing_fit_seconds"]
                    + record["transform_seconds"]
                    + record["predict_seconds"]
                    + record["evaluation_seconds"]
                    for record in tuning["inner_folds"]),
            }
        timings["boundary_phase_seconds"] = phase_seconds

        # global development-only configuration freeze
        selected_configs = {
            fold: per_fold[fold]["selection"]["selected_config"]["C"]
            for fold in folds}
        inner_aggregates: dict = {}
        for fold in folds:
            for record in per_fold[fold]["inner_folds"]:
                for key, config_node in record["configs"].items():
                    inner_aggregates.setdefault(
                        key, {"config": dict(config_node["hyperparameters"]),
                              "values": []})
                    inner_aggregates[key]["values"].append(
                        config_node["race_macro_log_loss"])
        for key, node in inner_aggregates.items():
            node["mean"] = float(np.mean(node["values"]))
            node["n_inner_evaluations"] = len(node["values"])
            node.pop("values")
        freeze = resolve_global_c(
            selected_configs=selected_configs,
            inner_aggregates=inner_aggregates)

        # representative determinism refit (D1)
        with TIMING.Timer() as t_det:
            det_fold = folds[0]
            det_config = {"C": selected_configs[det_fold]}
            first = TR.run_outer_selected(
                family=TC.LOGREG_FAMILY, fold=det_fold,
                selected_config=det_config, paths=paths, root=root,
                canonical=canonical, return_predictions=True)
            second = TR.run_outer_selected(
                family=TC.LOGREG_FAMILY, fold=det_fold,
                selected_config=det_config, paths=paths, root=root,
                canonical=canonical, return_predictions=True)
            actual_fits["determinism_refits"] += 2
            first_metrics = RES.read_experiment(first["dest"])[1].metrics
            second_metrics = RES.read_experiment(second["dest"])[1].metrics
            determinism = {
                "fold": det_fold,
                "selected_c": det_config["C"],
                "experiment_id": first["config"].experiment_id,
                "refit_experiment_id": second["config"].experiment_id,
                "same_experiment_id": (first["config"].experiment_id
                                       == second["config"].experiment_id),
                "same_selected_c": True,
                "metrics_identical": first_metrics == second_metrics,
                "max_abs_probability_difference": float(np.max(np.abs(
                    first["predictions"] - second["predictions"]))),
            }
        timings["determinism_check_seconds"] = t_det.seconds
    timings["total_seconds"] = total.seconds

    outer_aggregate = _aggregate_outer(per_fold, folds)
    boundary = boundary_status(selected_configs)
    comparison_m6 = _build_comparison(
        per_fold=per_fold, m7_aggregates=outer_aggregate, folds=folds,
        reference_per_fold_getter=lambda m: _m6_reference_per_fold(
            m6_summary, m),
        reference_aggregate_getter=lambda m: _m6_reference_aggregate(
            m6_summary, m),
        reference_label="M6 tuned LogReg C=0.03 (stored procedure result)")
    comparison_m3 = _build_comparison(
        per_fold=per_fold, m7_aggregates=outer_aggregate, folds=folds,
        reference_per_fold_getter=lambda m: _m3_reference_per_fold(
            m3_summary, m),
        reference_aggregate_getter=lambda m: _m3_reference_aggregate(
            m3_summary, m),
        reference_label="M3 untuned LogReg C=1.0 (stored reference)")

    translation = []
    for fold in folds:
        selection = per_fold[fold]["selection"]
        selected_key = selection["selected_key"]
        m6_control_key = config_key({"C": M6_LOWER_BOUNDARY_C})
        selected_inner = selection["selected_mean"]
        control_node = selection["config_aggregates"].get(m6_control_key)
        control_inner = control_node["mean"] if control_node else None
        m6_outer = _m6_reference_per_fold(m6_summary, "log_loss")[fold]
        m7_outer = _per_fold_values(per_fold, "log_loss")[fold]
        inner_delta = (selected_inner - control_inner
                       if selected_inner is not None
                       and control_inner is not None else None)
        outer_delta = (m7_outer - m6_outer
                       if m7_outer is not None and m6_outer is not None
                       else None)
        translation.append({
            "fold": fold,
            "selected_c": selection["selected_config"]["C"],
            "selected_key": selected_key,
            "inner_control_mean": control_inner,
            "selected_inner_mean": selected_inner,
            "inner_delta_vs_c003": inner_delta,
            "outer_control_log_loss": m6_outer,
            "outer_selected_log_loss": m7_outer,
            "outer_delta_vs_m6_c003": outer_delta,
            "inner_improved": (inner_delta is not None
                               and inner_delta < -BOUNDARY_TIE_TOLERANCE),
            "outer_improved": (outer_delta is not None
                               and outer_delta < -OUTER_EQUIVALENCE_TOL),
            "inner_selection_translated": (inner_delta is not None
                                           and inner_delta
                                           < -BOUNDARY_TIE_TOLERANCE
                                           and outer_delta is not None
                                           and outer_delta
                                           < -OUTER_EQUIVALENCE_TOL),
        })

    env = RES.environment_metadata(root if root is not None else (
        paths.root if paths is not None else None))
    global_c = freeze["global_c"]
    limitation = None
    if abs(global_c - NEW_LOWER_BOUNDARY_C) <= 1e-12:
        limitation = ("REGULARIZATION LOWER-BOUNDARY SENSITIVITY REMAINS "
                      "ACTIVE (global C equals the new lower boundary; the "
                      "grid is NOT expanded again)")

    summary = {
        "schema_version": SUITE_SCHEMA_VERSION,
        "stage": "M7",
        "title": "Logistic Regression regularization boundary resolution + "
                 "development configuration freeze",
        "task": task,
        "feature_set": feature_set,
        "seed": seed,
        "model_family": TC.LOGREG_FAMILY,
        "outer_folds": list(folds),
        "inner_folds": {
            fold: [s.to_dict() for s in resolve_inner_splits(fold)]
            for fold in folds},
        "c_grid": list(BOUNDARY_C_GRID),
        "m6_lower_boundary_c": M6_LOWER_BOUNDARY_C,
        "new_lower_boundary_c": NEW_LOWER_BOUNDARY_C,
        "objective": BOUNDARY_OBJECTIVE,
        "tie_break": BOUNDARY_TIE_BREAK,
        "global_freeze_rule": GLOBAL_FREEZE_RULE,
        "boundary_classification": {
            fold: classify_boundary_c(selected_configs[fold])
            for fold in folds},
        "boundary_status": boundary,
        "boundary_limitation": limitation,
        "planned_fit_count": planned,
        "actual_fit_count": actual_fits,
        "protocol_version": MODEL_LAB_PROTOCOL_VERSION,
        "protocol_semantic_hash": protocol_semantic_hash(),
        "matrix_version": REQUIRED_MATRIX_VERSION,
        "matrix_content_hash": EXPECTED_MATRIX_CONTENT_HASH,
        "feature_set_version": REQUIRED_FEATURE_SET_VERSION,
        "label_set_version": REQUIRED_LABEL_SET_VERSION,
        "ablation_config_version": REQUIRED_ABLATION_CONFIG_VERSION,
        "git_commit": env.get("git_commit"),
        "holdout_accessed": False,
        "holdout_note": "2025 protected final holdout — not evaluated",
        "per_fold": per_fold,
        "aggregate": outer_aggregate,
        "selected_c_per_fold": selected_configs,
        "inner_aggregate_all_eligible": inner_aggregates,
        "global_configuration": {
            "decision": freeze,
            "frozen_specification": _frozen_configuration(global_c),
        },
        "comparison_vs_m6": comparison_m6,
        "comparison_vs_m3": comparison_m3,
        "inner_vs_outer_translation": translation,
        "determinism": determinism,
        "runtime": timings,
        "peak_rss_bytes": _peak_rss_bytes(),
        "hashes": _immutability_report(
            Path(root) if root is not None else (
                paths.root if paths is not None else Path.cwd())),
        "warnings": [w for fold in folds
                     for w in per_fold[fold]["outer"]["warnings"]],
    }
    summary = _jsonable(summary)
    dest = Path(out) if out is not None else default_out(paths, root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    RES.atomic_write_json(dest, summary)
    summary["_summary_path"] = str(dest)
    return summary


# ---------------------------------------------------------------------------
# report rendering (from the stored artifact only)
# ---------------------------------------------------------------------------


def _fmt(value, digits: int = 6):
    if value is None:
        return "N/A"
    if isinstance(value, float) and not math.isfinite(value):
        return "N/A"
    return f"{value:.{digits}f}"


def render_boundary_report(summary: dict) -> str:
    """Render the human-readable M7 report from the stored artifact only."""
    folds = summary["outer_folds"]
    lines: list = []
    add = lines.append
    add("# Model Lab Logistic Regression Boundary Resolution Report (M7)")
    add("")
    add("## LOGISTIC REGRESSION DEVELOPMENT CONFIGURATION FREEZE")
    add("")
    add("## OUTER DEVELOPMENT EVALUATION: 2022 / 2023 / 2024")
    add("")
    add("## 2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED")
    add("")
    add("## 1. Why M7 exists and the M6 boundary finding")
    add("")
    add("M6 nested chronological tuning selected Logistic Regression with the "
        f"LOWER grid-boundary value `C={summary['m6_lower_boundary_c']:g}` on "
        "all three outer folds (D1/D2/D3), so the regularization optimum could "
        "not be distinguished from the search boundary. M7 is a ONE-TIME, "
        "narrow boundary resolution: it searches exactly "
        f"`C in {summary['c_grid']}` with race-macro log loss only, reuses the "
        "exact M6 inner folds and preprocessing, and never reopens candidate "
        "selection, never tunes ExtraTrees, never starts calibration and never "
        "touches 2025.")
    add("")
    add("## 2. Exact outer development folds")
    add("")
    add("| fold | outer TRAIN | outer VALIDATE |")
    add("| --- | --- | --- |")
    for fold, train, validate in (("D1", "2018–2021", "2022"),
                                  ("D2", "2018–2022", "2023"),
                                  ("D3", "2018–2023", "2024")):
        add(f"| {fold} | {train} | {validate} |")
    add("")
    add("## 3. Exact inner folds (identical to M6)")
    add("")
    add("| outer fold | inner fold | inner TRAIN | inner VALIDATE |")
    add("| --- | --- | --- | --- |")
    for fold in folds:
        for split in summary["inner_folds"][fold]:
            add(f"| {fold} | {split['inner_fold_id']} | "
                f"{split['train_seasons'][0]}–{split['train_seasons'][-1]} | "
                f"{split['validation_seasons'][0]} |")
    add("")
    add("## 4. Exact C grid (one-time predeclared extension)")
    add("")
    add(f"- C in {summary['c_grid']}")
    add(f"- {summary['new_lower_boundary_c']:g} = LOWER_BOUNDARY (new); "
        "0.01 = INTERIOR; "
        f"{summary['m6_lower_boundary_c']:g} = INTERIOR / PREVIOUS_BOUNDARY "
        "(M6 control); 0.1 = UPPER_CONTROL")
    add("- no recursive expansion; no adaptive search; every C is fit on every "
        "inner fold")
    add("")
    add("## 5. Exact planned fit budget")
    add("")
    planned = summary["planned_fit_count"]
    add(f"- inner estimator fits: {planned['inner_estimator_fits']} "
        f"({len(summary['c_grid'])} C x 6 inner folds); inner preprocessor "
        f"fits: {planned['inner_preprocessor_fits']} (one per inner fold, "
        "reused across C)")
    add(f"- outer selected refits: {planned['outer_selected_refits']}; "
        f"determinism refits: {planned['determinism_refits']}")
    add(f"- total planned estimator fits: {planned['total_estimator_fits']}")
    actual = summary["actual_fit_count"]
    add(f"- actual: inner estimator fits = {actual['inner_estimator_fits']}, "
        f"inner preprocessor fits = {actual['preprocessor_fits']}, outer "
        f"selected refits = {actual['outer_selected_refits']}, determinism "
        f"refits = {actual['determinism_refits']}")
    add("")
    add("## 6. Tuning objective and tie-break (declared before execution)")
    add("")
    add(f"- objective: {summary['objective']}; lower is better")
    add(f"- tie-break tolerance: {summary['tie_break']['tolerance_abs']:.0e} "
        "absolute on mean inner race-macro log loss")
    add(f"- {summary['tie_break']['rule']}")
    add("")
    add("## 7. INNER RESULTS")
    add("")
    for fold in folds:
        selection = summary["per_fold"][fold]["selection"]
        add(f"### {fold}: selected `{selection['selected_key']}` "
            f"(boundary class "
            f"{summary['boundary_classification'][fold]}; tie-break "
            f"applied={selection['tie_break_applied']})")
        add("")
        add("| C | inner mean | std | min | max | range |")
        add("| --- | --- | --- | --- | --- | --- |")
        aggs = selection["config_aggregates"]
        for key in sorted(aggs, key=lambda k: float(k.split("=")[1])):
            agg = aggs[key]
            add(f"| {key} | {_fmt(agg['mean'])} | {_fmt(agg['std'])} | "
                f"{_fmt(agg['min'])} | {_fmt(agg['max'])} | "
                f"{_fmt(agg['range'])} |")
        add("")
    add("## 8. Selected C per outer fold and boundary classification")
    add("")
    add("| outer fold | selected C | boundary class | new lower boundary? |")
    add("| --- | --- | --- | --- |")
    for fold in folds:
        c = summary["selected_c_per_fold"][fold]
        is_lower = abs(c - summary["new_lower_boundary_c"]) <= 1e-12
        add(f"| {fold} | `{c:g}` | {summary['boundary_classification'][fold]} "
            f"| {'YES' if is_lower else 'no'} |")
    add("")
    status = summary["boundary_status"]
    add(f"**Boundary conclusion: {status['status']}**")
    add("")
    add(f"- {status['rule']}")
    add(f"- folds selecting the new lower boundary: "
        f"{status['folds_selecting_new_lower_boundary']}")
    add("- no further lower search was performed")
    add("")
    add("## 9. DEVELOPMENT OUTER RESULTS")
    add("")
    add("**OUTER DEVELOPMENT EVALUATION: 2022 / 2023 / 2024**")
    add("")
    add("**2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED**")
    add("")
    add("| fold | selected C | log loss | Brier | state-pooled log loss | "
        "state-pooled Brier | ROC-AUC | PR-AUC | ECE | top-1 | top-3 |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for fold in folds:
        outer = summary["per_fold"][fold]["outer"]
        c = summary["selected_c_per_fold"][fold]
        rm = outer["race_macro"]
        sp = outer["state_pooled"]
        cal = outer["calibration"]
        add(f"| {fold} | `{c:g}` | {_fmt(rm['log_loss'])} | "
            f"{_fmt(rm['brier'])} | {_fmt(sp['log_loss'])} | "
            f"{_fmt(sp['brier'])} | {_fmt(rm['roc_auc'])} | "
            f"{_fmt(rm['pr_auc'])} | "
            f"{_fmt(cal['expected_calibration_error'])} | "
            f"{_fmt(_topk_from_node(outer, 'top1'))} | "
            f"{_fmt(_topk_from_node(outer, 'top3'))} |")
    agg = summary["aggregate"]
    add(f"| mean | — | {_fmt(agg['log_loss']['mean'])} | "
        f"{_fmt(agg['brier']['mean'])} | "
        f"{_fmt(agg['state_pooled_log_loss']['mean'])} | "
        f"{_fmt(agg['state_pooled_brier']['mean'])} | "
        f"{_fmt(agg['roc_auc']['mean'])} | {_fmt(agg['pr_auc']['mean'])} | "
        f"{_fmt(agg['expected_calibration_error']['mean'])} | "
        f"{_fmt(agg['winner_top_k']['top1']['mean'])} | "
        f"{_fmt(agg['winner_top_k']['top3']['mean'])} |")
    add("")
    add("Stage race-macro diagnostics (EARLY / MID / LATE) and synchronized "
        "top-k detail:")
    add("")
    for fold in folds:
        outer = summary["per_fold"][fold]["outer"]
        stage = outer["stages"].get("log_loss", {})
        if stage.get("status") == "OK":
            cells = [_fmt(stage.get(s, {}).get("race_macro", {}).get("value"))
                     for s in ("EARLY", "MID", "LATE")]
            add(f"- {fold}: EARLY={cells[0]} MID={cells[1]} LATE={cells[2]}")
    add("")
    add("| fold | top-1 | top-3 | eval states | skipped (none/winner-unobs/"
        "degen) | min field | mean field |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for fold in folds:
        payload = summary["per_fold"][fold]["outer"][
            "synchronized"].get("winner_top_k", {})
        if payload.get("status") != "OK":
            add(f"| {fold} | N/A | N/A | N/A | N/A | N/A | N/A |")
            continue
        acc = payload.get("accuracy") or {}
        skips = (f"{payload.get('n_skipped_no_predictions', 0)}/"
                 f"{payload.get('n_skipped_winner_unobservable', 0)}/"
                 f"{payload.get('n_skipped_degenerate', 0)}")
        add(f"| {fold} | {_fmt(acc.get('top1'))} | {_fmt(acc.get('top3'))} | "
            f"{payload.get('n_evaluation_states')} | {skips} | "
            f"{payload.get('min_observable_field_size')} | "
            f"{_fmt(payload.get('mean_observable_field_size'), 2)} |")
    add("")
    add("## 10. Comparison vs M6 tuned LogReg C=0.03 (stored procedure result)")
    add("")
    for metric in ("log_loss", "brier", "roc_auc", "pr_auc",
                   "expected_calibration_error", "winner_top1"):
        node = summary["comparison_vs_m6"]["metrics"][metric]
        add(f"### {metric} ({node['tier']}, {node['direction']})")
        add("")
        add("| fold | M7 | M6 C=0.03 | diff | verdict |")
        add("| --- | --- | --- | --- | --- |")
        for fold in folds:
            row = node["per_fold"][fold]
            add(f"| {fold} | {_fmt(row['m7_value'])} | "
                f"{_fmt(row['reference_value'])} | {_fmt(row['difference'])} | "
                f"{row['verdict']} |")
        a = node["aggregate"]
        add(f"| mean | {_fmt(a['m7_mean'])} | {_fmt(a['reference_mean'])} | "
            f"{_fmt(a['difference'])} | {a['verdict']} |")
        add("")
    add("## 11. Comparison vs M3 untuned LogReg C=1.0 (stored reference)")
    add("")
    for metric in ("log_loss", "brier", "roc_auc", "pr_auc",
                   "expected_calibration_error", "winner_top1"):
        node = summary["comparison_vs_m3"]["metrics"][metric]
        add(f"### {metric} ({node['tier']}, {node['direction']})")
        add("")
        add("| fold | M7 | M3 C=1.0 | diff | verdict |")
        add("| --- | --- | --- | --- | --- |")
        for fold in folds:
            row = node["per_fold"][fold]
            add(f"| {fold} | {_fmt(row['m7_value'])} | "
                f"{_fmt(row['reference_value'])} | {_fmt(row['difference'])} | "
                f"{row['verdict']} |")
        a = node["aggregate"]
        add(f"| mean | {_fmt(a['m7_mean'])} | {_fmt(a['reference_mean'])} | "
            f"{_fmt(a['difference'])} | {a['verdict']} |")
        add("")
    add("- no combined weighted score is constructed; no significance is "
        "claimed")
    add("")
    add("## 12. Inner-vs-outer translation")
    add("")
    add("| fold | selected C | inner mean vs C=0.03 | outer log loss vs M6 "
        "C=0.03 | inner improved | outer improved | translated |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for row in summary["inner_vs_outer_translation"]:
        add(f"| {row['fold']} | `{row['selected_c']:g}` | "
            f"{_fmt(row['inner_delta_vs_c003'])} | "
            f"{_fmt(row['outer_delta_vs_m6_c003'])} | "
            f"{row['inner_improved']} | {row['outer_improved']} | "
            f"{row['inner_selection_translated']} |")
    add("")
    add("Negative deltas are improvements. Negative translation is not hidden.")
    add("")
    add("## 13. Global development configuration rule")
    add("")
    rule = summary["global_freeze_rule"]
    add(f"- {rule['step_1']}")
    add(f"- {rule['step_2']}")
    add(f"- {rule['step_3']}")
    add(f"- {rule['step_4']}")
    add(f"- outer validation used to choose the global C: "
        f"{rule['outer_validation_used']}")
    add(f"- 2025 used: {rule['holdout_used']}")
    decision = summary["global_configuration"]["decision"]
    add(f"- decision: global C = **{decision['global_c']:g}** "
        f"({decision['rule']}; {decision['detail']})")
    add("")
    add("## 14. FINAL DEVELOPMENT-FROZEN LOGISTIC REGRESSION SPECIFICATION")
    add("")
    spec = summary["global_configuration"]["frozen_specification"]
    add(f"- model family: `{spec['model_family']}` "
        f"({spec['estimator']})")
    add(f"- feature set: `{spec['feature_set']}` (task `{spec['task']}`)")
    add(f"- solver: `{spec['solver']}`; max_iter: {spec['max_iter']}; "
        f"class_weight: {spec['class_weight']}; random_state: "
        f"{spec['random_state']}")
    add(f"- penalty: {spec['penalty']}")
    add(f"- **C: {spec['C']:g}**")
    add(f"- probability semantics: `{spec['probability_semantics']}` "
        "(never normalized across drivers)")
    add("- preprocessing: existing frozen train-fitted pipeline (median/"
        "StandardScaler numeric, most-frequent boolean, one-hot categorical "
        "with explicit MISSING sentinel)")
    add("- no calibration fitted; no threshold optimization")
    add("")
    add("## 15. Boundary limitation")
    add("")
    if summary["boundary_limitation"]:
        add(f"**{summary['boundary_limitation']}**")
    else:
        add("The M6 lower-boundary issue is resolved within the tested range; "
            "no recursive search is performed.")
    add("")
    add("## 16. Determinism, runtime, memory")
    add("")
    det = summary["determinism"]
    add(f"- representative refit ({det['fold']}, C={det['selected_c']:g}): "
        f"same experiment id = {det['same_experiment_id']}; metrics identical "
        f"= {det['metrics_identical']}; max abs probability difference = "
        f"{det['max_abs_probability_difference']:.3e}")
    add(f"- suite wall time: {summary['runtime'].get('total_seconds', 0):.1f} s")
    add(f"- determinism refit time: "
        f"{summary['runtime'].get('determinism_check_seconds', 0):.1f} s")
    rss = summary.get("peak_rss_bytes")
    add(f"- peak RSS: {rss / 1e9:.2f} GB" if rss
        else "- peak RSS: NOT MEASURED")
    add(f"- total actual estimator fits: "
        f"{summary['actual_fit_count']['inner_estimator_fits'] + summary['actual_fit_count']['outer_selected_refits'] + summary['actual_fit_count']['determinism_refits']} (plus "
        f"{summary['actual_fit_count']['preprocessor_fits']} inner "
        "preprocessor fits)")
    add("")
    add("Inference (selected LogReg only; latency probed on every outer "
        "evaluation, never per C):")
    add("")
    for fold in folds:
        latency = summary["per_fold"][fold]["outer"]["latency"]
        batch = (latency or {}).get("batch") or {}
        single = (latency or {}).get("single_state") or {}
        add(f"- {fold}: batch mean={_fmt(batch.get('mean'))} s "
            f"({_fmt(batch.get('states_per_second'), 1)} states/s); "
            f"single-state mean={_fmt(single.get('mean'))} s")
    add("")
    add("## 17. Hashes (immutability boundary)")
    add("")
    hashes = summary["hashes"]
    for key in ("phase2_parquet_byte_hash", "phase2_manifest_byte_hash",
                "f16_ablation_byte_hash", "phase2_matrix_content_hash",
                "m0_protocol_semantic_hash", "m0_protocol_json_byte_hash",
                "phase2_freeze_manifest_byte_hash"):
        add(f"- {key}: `{hashes[key]}`")
    add("")
    add("## 18. Artifacts and limitations")
    add("")
    add(f"- M7 machine-readable artifact: "
        f"`{summary.get('_summary_path', BOUNDARY_SUITE_FILENAME)}` "
        "(this document was rendered from it)")
    add("- M6 artifact used for comparison: "
        "`data/v2/model_lab/reports/tuning_selection_v1.json` (not rerun)")
    add("- M3 reference used for comparison: "
        "`data/v2/model_lab/reports/logreg_reference_v1.json` (not rerun)")
    add("- three outer development folds are limited evidence; inner folds are "
        "nested and not independent")
    add("- state rows are not independent; headline metrics use race-macro "
        "aggregation")
    add("- raw probabilities only; no calibration was fitted in M7")
    add("- 2025 was not evaluated and remains the protected final holdout")
    add("")
    add("## 19. Recommendation")
    add("")
    if summary["boundary_limitation"]:
        add("The base Logistic Regression configuration is development-frozen, "
            "but lower-boundary sensitivity is still flagged. Calibration may "
            "proceed on the frozen configuration; the boundary limitation must "
            "be carried into the model card.")
    else:
        add("The base Logistic Regression configuration is development-frozen "
            "within the tested regularization range and is ready to advance.")
    add("")
    return "\n".join(lines) + "\n"


if __name__ == "__main__":  # pragma: no cover - manual smoke helper
    print(json.dumps(planned_fit_count(), indent=2, sort_keys=True))
