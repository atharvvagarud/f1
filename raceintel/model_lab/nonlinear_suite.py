"""M4 nonlinear candidate suite: execution + disk-derived summary + report.

Chain of custody: stored model experiment results (``write_experiment``)
-> suite summary (read back from ``result.json`` on disk) -> human-readable
markdown (rendered from the summary file only). M3 comparison values are
loaded from the stored M3 suite summary (``logreg_reference_v1.json``) and
M2 floor values from the stored M2 suite summary
(``baseline_suite_v1.json``) — never retyped.

Runs exactly six experiments: HGB x winner x D1/D2/D3 + XGB x winner x
D1/D2/D3. No LOGREG rerun except the representative determinism refits
(HGB D1, XGB D1), which reuse the same experiment identity.
"""

from __future__ import annotations

import json
from pathlib import Path

from raceintel.model_lab import aggregation as AGG
from raceintel.model_lab import experiment as EX
from raceintel.model_lab import model_suite as MSUITE
from raceintel.model_lab import nonlinear_runner as NR
from raceintel.model_lab import results as RES
from raceintel.model_lab import runner as RUN
from raceintel.model_lab import suite as SUITE
from raceintel.model_lab import tree_candidates as TC
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
NONLINEAR_SUITE_FILENAME = "nonlinear_candidates_v1.json"

#: Model families executed by this suite, in execution order.
SUITE_MODELS = (TC.HGB_FAMILY, TC.XGB_FAMILY)

#: Metric -> (M2 baseline, direction) for the frozen baseline floor.
#: Direction "lower" means lower is better (BEATS when model < baseline).
BASELINE_FLOOR_REFERENCES = dict(MSUITE.COMPARISON_REFERENCES)

#: Metric -> direction for the M3 LOGREG reference comparison.
LOGREG_REFERENCE_DIRECTIONS = {
    "log_loss": "lower",
    "brier": "lower",
    "roc_auc": "higher",
    "pr_auc": "higher",
    "expected_calibration_error": "lower",
    "winner_top1": "higher",
}


def reports_dir(paths=None, root=None) -> Path:
    return SUITE.reports_dir(paths, root)


def default_out(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / NONLINEAR_SUITE_FILENAME


def logreg_suite_path(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / MSUITE.MODEL_SUITE_FILENAME


def load_logreg_suite(paths=None, root=None) -> dict:
    path = logreg_suite_path(paths, root)
    if not path.exists():
        raise ExperimentConfigError(
            f"M3 LOGREG suite summary is missing at {path}; "
            "M4 comparison requires stored M3 artifacts")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _read_result(dest: str) -> tuple:
    return RES.read_experiment(dest)


def _extract_per_fold(config, result) -> dict:
    calibration_ece = (
        result.calibration["expected_calibration_error"]
        if result.calibration else None)
    topk = result.race_metrics.get("winner_top_k", {})
    entry = {
        "experiment_id": config.experiment_id,
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
        "runtime_versions": {
            key: result.artifact_refs.get(key)
            for key in ("sklearn_version", "xgboost_version")
            if result.artifact_refs.get(key) is not None
        },
        "fit_warnings": result.artifact_refs.get("fit_warnings", []),
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
    return entry


def _race_macro_value(per_fold_entry: dict, metric: str):
    payload = per_fold_entry["metrics"].get(metric, {})
    if payload.get("status") != "OK":
        return None
    return payload.get("race_macro", {}).get("value")


def _aggregate_folds(per_fold: dict, folds: tuple) -> dict:
    aggregates: dict = {}
    for metric in ("log_loss", "brier", "roc_auc", "pr_auc"):
        values = {fold: _race_macro_value(per_fold[fold], metric)
                  for fold in folds}
        aggregates[metric] = SUITE._json_safe_number(
            AGG.aggregate_folds(values))
    ece_values = {fold: per_fold[fold]["calibration_ece"] for fold in folds}
    aggregates["expected_calibration_error"] = SUITE._json_safe_number(
        AGG.aggregate_folds(ece_values))
    aggregates["winner_top_k"] = {}
    for key, acc_key in (("top1", "top1"), ("top3", "top3")):
        vals = {}
        for fold in folds:
            payload = per_fold[fold]["race_metrics"].get("winner_top_k", {})
            acc = (payload.get("accuracy") or {}).get(acc_key) \
                if payload.get("status") == "OK" else None
            vals[fold] = acc
        aggregates["winner_top_k"][key] = SUITE._json_safe_number(
            AGG.aggregate_folds(vals))
    return aggregates


def _model_value_for_metric(per_fold_entry: dict, metric: str):
    if metric == "winner_top1":
        payload = per_fold_entry["race_metrics"].get("winner_top_k", {})
        if payload.get("status") != "OK":
            return None
        return (payload.get("accuracy") or {}).get("top1")
    if metric == "expected_calibration_error":
        return per_fold_entry["calibration_ece"]
    return _race_macro_value(per_fold_entry, metric)


def _baseline_value_for_metric(baseline_per_fold: dict, fold: str,
                               baseline: str, metric: str):
    if metric == "winner_top1":
        payload = baseline_per_fold.get(fold, {}).get(
            baseline, {}).get("race_metrics", {}).get("winner_top_k", {})
        if payload.get("status") != "OK":
            return None
        return (payload.get("accuracy") or {}).get("top1")
    if metric == "expected_calibration_error":
        return baseline_per_fold.get(fold, {}).get(
            baseline, {}).get("calibration_ece")
    payload = baseline_per_fold.get(fold, {}).get(
        baseline, {}).get("metrics", {}).get(metric, {})
    if payload.get("status") != "OK":
        return None
    return payload.get("race_macro", {}).get("value")


def _compare_pair(direction: str, model_value, ref_value,
                  model_mean, ref_mean) -> dict:
    difference = (model_value - ref_value
                  if model_value is not None and ref_value is not None
                  else None)
    mean_difference = (model_mean - ref_mean
                       if model_mean is not None and ref_mean is not None
                       else None)
    return {
        "model_value": model_value,
        "reference_value": ref_value,
        "difference": difference,
        "verdict": MSUITE._verdict(direction, model_value, ref_value),
        "model_mean": model_mean,
        "reference_mean": ref_mean,
        "mean_difference": mean_difference,
        "mean_verdict": MSUITE._verdict(direction, model_mean, ref_mean),
    }


def build_nonlinear_summary(*, task: str, folds: tuple, feature_set: str,
                            seed: int, experiments: list, timings: dict,
                            determinism: dict, baseline_suite: dict,
                            logreg_suite: dict, m5_recommendation: str | None,
                            git_commit: str | None) -> dict:
    """Derive the M4 summary by re-reading stored result documents."""
    from raceintel.model_lab.protocol import (
        EXPECTED_MANIFEST_SHA256,
        EXPECTED_MATRIX_PARQUET_SHA256,
    )
    per_model: dict = {}
    for family in SUITE_MODELS:
        per_fold: dict = {}
        for entry in experiments:
            if entry["model"] != family:
                continue
            config, result = _read_result(entry["dest"])
            per_fold[config.fold] = _extract_per_fold(config, result)
        # Model spec / preprocessing are fold-invariant by construction.
        first_fold = folds[0]
        per_model[family] = {
            "model_spec": per_fold[first_fold]["model_parameters"],
            "preprocessing_spec": per_fold[first_fold][
                "preprocessing_config"],
            "runtime_versions": per_fold[first_fold]["runtime_versions"],
            "per_fold": per_fold,
            "aggregates": _aggregate_folds(per_fold, folds),
            "experiments": [
                {"model": e["model"], "fold": e["fold"],
                 "experiment_id": e["experiment_id"], "dest": e["dest"]}
                for e in experiments if e["model"] == family],
            "determinism_check": determinism[family],
        }

    logreg_per_fold = logreg_suite.get("per_fold", {})
    logreg_agg = logreg_suite.get("aggregates", {})

    def _logreg_fold_value(fold: str, metric: str):
        entry = logreg_per_fold.get(fold, {})
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

    def _logreg_mean(metric: str):
        if metric == "winner_top1":
            return logreg_agg.get("winner_top_k", {}).get("top1", {}).get(
                "mean")
        return logreg_agg.get(metric, {}).get("mean")

    # --- comparison vs stored M3 LOGREG reference ---
    vs_logreg: dict = {}
    for metric, direction in LOGREG_REFERENCE_DIRECTIONS.items():
        node = {"reference": "logistic_regression (M3 stored artifacts)",
                "direction": direction, "per_fold": {}, "aggregate": {}}
        for fold in folds:
            ref_value = _logreg_fold_value(fold, metric)
            ref_mean = _logreg_mean(metric)
            fold_node = {}
            for family in SUITE_MODELS:
                model_value = _model_value_for_metric(
                    per_model[family]["per_fold"][fold], metric)
                model_agg = per_model[family]["aggregates"]
                if metric == "winner_top1":
                    mean_value = model_agg["winner_top_k"]["top1"]["mean"]
                else:
                    mean_value = model_agg[metric]["mean"]
                fold_node[family] = _compare_pair(
                    direction, model_value, ref_value, mean_value, ref_mean)
            node["per_fold"][fold] = fold_node
        agg_node = {}
        for family in SUITE_MODELS:
            model_agg = per_model[family]["aggregates"]
            if metric == "winner_top1":
                mean_value = model_agg["winner_top_k"]["top1"]["mean"]
            else:
                mean_value = model_agg[metric]["mean"]
            agg_node[family] = {
                "model_mean": mean_value,
                "reference_mean": _logreg_mean(metric),
                "mean_difference": (
                    mean_value - _logreg_mean(metric)
                    if mean_value is not None
                    and _logreg_mean(metric) is not None else None),
                "mean_verdict": MSUITE._verdict(
                    direction, mean_value, _logreg_mean(metric)),
            }
        node["aggregate"] = agg_node
        vs_logreg[metric] = node

    # --- comparison vs stored M2 baseline floor ---
    base_per_fold = baseline_suite.get("per_fold", {})
    base_agg = baseline_suite.get("aggregates", {})
    vs_floor: dict = {}
    for metric, (baseline, direction) in BASELINE_FLOOR_REFERENCES.items():
        node = {"baseline": baseline, "direction": direction,
                "per_fold": {}, "aggregate": {}}
        for fold in folds:
            base_value = _baseline_value_for_metric(
                base_per_fold, fold, baseline, metric)
            fold_node = {}
            for family in SUITE_MODELS:
                model_value = _model_value_for_metric(
                    per_model[family]["per_fold"][fold], metric)
                model_agg = per_model[family]["aggregates"]
                if metric == "winner_top1":
                    mean_value = model_agg["winner_top_k"]["top1"]["mean"]
                else:
                    mean_value = model_agg[metric]["mean"]
                fold_node[family] = {
                    "model_value": model_value,
                    "baseline_value": base_value,
                    "difference": (
                        model_value - base_value
                        if model_value is not None
                        and base_value is not None else None),
                    "verdict": MSUITE._verdict(
                        direction, model_value, base_value),
                }
            node["per_fold"][fold] = fold_node
        agg_node = {}
        for family in SUITE_MODELS:
            model_agg = per_model[family]["aggregates"]
            if metric == "winner_top1":
                mean_value = model_agg["winner_top_k"]["top1"]["mean"]
                base_mean = (base_agg.get(baseline, {}).get(
                    "winner_top_k", {}).get("top1", {}).get("mean"))
            elif metric == "expected_calibration_error":
                mean_value = model_agg[metric]["mean"]
                defined = [
                    node["per_fold"][f][family]["baseline_value"]
                    for f in folds]
                defined = [v for v in defined if v is not None]
                base_mean = (sum(defined) / len(defined)) if defined else None
            else:
                mean_value = model_agg[metric]["mean"]
                base_mean = base_agg.get(baseline, {}).get(
                    metric, {}).get("mean")
            agg_node[family] = {
                "model_mean": mean_value,
                "baseline_mean": base_mean,
                "mean_difference": (
                    mean_value - base_mean
                    if mean_value is not None and base_mean is not None
                    else None),
                "mean_verdict": MSUITE._verdict(
                    direction, mean_value, base_mean),
            }
        node["aggregate"] = agg_node
        vs_floor[metric] = node

    summary = {
        "schema_version": SUITE_SCHEMA_VERSION,
        "task": task,
        "models": list(SUITE_MODELS),
        "hgb_spec": TC.hgb_model_parameters(),
        "xgb_spec": TC.xgb_model_parameters(),
        "preprocessing_note": (
            "both candidates reuse the exact M3 train-fitted preprocessing "
            "(median + StandardScaler numerics, most-frequent booleans, "
            "MISSING-sentinel + train-vocabulary one-hot categoricals); "
            "same 84 source features; HGB native categorical support "
            "inspected and deliberately not used to preserve comparable "
            "feature semantics"),
        "sklearn_version": TC.SKLEARN_VERSION,
        "xgboost_version": TC.XGBOOST_VERSION,
        "folds": list(folds),
        "feature_set": feature_set,
        "seed": seed,
        "tuning": "none (one fixed specification per family, chosen before "
                  "observing validation)",
        "calibration_fitted": "none (raw probabilities evaluated)",
        "probability_semantics": "INDEPENDENT_BINARY",
        "protocol_version": MODEL_LAB_PROTOCOL_VERSION,
        "protocol_semantic_hash": protocol_semantic_hash(),
        "matrix_version": REQUIRED_MATRIX_VERSION,
        "matrix_content_hash": EXPECTED_MATRIX_CONTENT_HASH,
        "matrix_parquet_sha256": EXPECTED_MATRIX_PARQUET_SHA256,
        "manifest_sha256": EXPECTED_MANIFEST_SHA256,
        "feature_set_version": REQUIRED_FEATURE_SET_VERSION,
        "label_set_version": REQUIRED_LABEL_SET_VERSION,
        "ablation_config_version": REQUIRED_ABLATION_CONFIG_VERSION,
        "ablation_config_sha256": EXPECTED_ABLATION_CONFIG_SHA256,
        "git_commit": git_commit,
        "holdout_accessed": False,
        "holdout_note": "2025 protected final holdout — not evaluated",
        "baseline_suite_schema": baseline_suite.get("schema_version"),
        "logreg_suite_schema": logreg_suite.get("schema_version"),
        "per_model": per_model,
        "vs_logreg_reference": vs_logreg,
        "vs_baseline_floor": vs_floor,
        "runtime": timings,
        "peak_rss_bytes": SUITE._peak_rss_bytes(),
        "warnings": [w for family in SUITE_MODELS
                     for fold in folds
                     for w in per_model[family]["per_fold"][fold][
                         "warnings"]],
        "m5_recommendation": m5_recommendation,
    }
    return summary


def run_nonlinear_suite(*, task: str = "winner", models=("hist_gradient_boosting",
                          "xgboost"), folds=("D1", "D2", "D3"),
                         feature_set: str = "ALL_84",
                         seed: int = EX.PROJECT_SEED, paths=None, root=None,
                         out=None,
                         m5_recommendation: str | None = None) -> dict:
    """Execute the M4 suite (HGB + XGB) x winner x D1/D2/D3."""
    if task != NR.M4_TASK:
        raise ExperimentConfigError(
            f"M4 evaluates task {NR.M4_TASK!r} only; got {task!r}")
    families = [NR.resolve_model(m) for m in models]
    if sorted(families) != sorted(SUITE_MODELS):
        raise ExperimentConfigError(
            f"M4 runs exactly {list(SUITE_MODELS)}; got {families!r}")
    folds = SUITE.parse_folds(",".join(folds))
    for fold in folds:
        RUN.resolve_development_fold(fold)
    baseline_suite = MSUITE.load_baseline_suite(paths, root)
    logreg_suite = load_logreg_suite(paths, root)

    timings: dict = {}
    with _TimingScope() as total:
        experiments: list = []
        phase_seconds: dict = {}
        per_model_seconds: dict = {}
        for family in families:
            for fold in folds:
                out_exp = NR.run_nonlinear_experiment(
                    task=task, model=family, fold=fold,
                    feature_set=feature_set, seed=seed, paths=paths,
                    root=root)
                experiments.append({
                    "model": family, "fold": fold,
                    "experiment_id": out_exp["config"].experiment_id,
                    "dest": out_exp["dest"]})
                for phase, seconds in out_exp["timings"].items():
                    if isinstance(seconds, (int, float)):
                        phase_seconds[phase] = phase_seconds.get(phase, 0.0) \
                            + seconds
                        key = f"{family}/{phase}"
                        per_model_seconds[key] = per_model_seconds.get(
                            key, 0.0) + seconds
        timings["experiment_phases_total_seconds"] = phase_seconds
        timings["per_model_phase_seconds"] = per_model_seconds

        with _TimerBlock(timings, "determinism_check_seconds"):
            import numpy as _np
            determinism = {}
            for family in families:
                first = NR.run_nonlinear_experiment(
                    task=task, model=family, fold=folds[0],
                    feature_set=feature_set, seed=seed, paths=paths,
                    root=root, return_predictions=True)
                second = NR.run_nonlinear_experiment(
                    task=task, model=family, fold=folds[0],
                    feature_set=feature_set, seed=seed, paths=paths,
                    root=root, return_predictions=True)
                diff = float(_np.max(_np.abs(
                    first["predictions"] - second["predictions"])))
                first_metrics = _read_result(first["dest"])[1].metrics
                second_metrics = _read_result(second["dest"])[1].metrics
                determinism[family] = {
                    "fold": folds[0],
                    "experiment_id": first["config"].experiment_id,
                    "refit_experiment_id": second["config"].experiment_id,
                    "same_experiment_id": (
                        first["config"].experiment_id
                        == second["config"].experiment_id),
                    "metrics_identical": first_metrics == second_metrics,
                    "max_abs_probability_difference": diff,
                }
    timings["total_seconds"] = total.seconds

    from raceintel.model_lab.results import environment_metadata
    from raceintel.model_lab import timing as TIMING
    with TIMING.Timer() as t:
        env = environment_metadata(
            paths.root if paths is not None else None)
    summary = build_nonlinear_summary(
        task=task, folds=folds, feature_set=feature_set,
        seed=seed, experiments=experiments,
        timings={**timings, "environment_probe_seconds": t.seconds},
        determinism=determinism, baseline_suite=baseline_suite,
        logreg_suite=logreg_suite, m5_recommendation=m5_recommendation,
        git_commit=env.get("git_commit"))

    dest = Path(out) if out is not None else default_out(paths, root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    RES.atomic_write_json(dest, summary)
    summary["_summary_path"] = str(dest)
    return summary


class _TimingScope:
    """Context manager alias kept local so suite timing stays explicit."""

    def __enter__(self):
        from raceintel.model_lab import timing as TIMING
        self._timer = TIMING.Timer()
        return self._timer.__enter__()

    def __exit__(self, *exc):
        return self._timer.__exit__(*exc)


class _TimerBlock:
    def __init__(self, timings: dict, key: str):
        self._timings = timings
        self._key = key

    def __enter__(self):
        from raceintel.model_lab import timing as TIMING
        self._timer = TIMING.Timer()
        return self._timer.__enter__()

    def __exit__(self, *exc):
        self._timer.__exit__(*exc)
        self._timings[self._key] = self._timer.seconds
        return False


def _fmt(value, digits: int = 6):
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_nonlinear_report(summary: dict) -> str:
    """Render the human-readable M4 report from the stored summary only."""
    folds = summary["folds"]
    models = summary["models"]
    per_model = summary["per_model"]
    agg_of = {m: per_model[m]["aggregates"] for m in models}
    vs_lr = summary["vs_logreg_reference"]
    vs_floor = summary["vs_baseline_floor"]
    lines = []
    add = lines.append
    add("# Model Lab Nonlinear Candidates Report (M4)")
    add("")
    add("**DEVELOPMENT RESULTS — 2022 / 2023 / 2024**")
    add("")
    add("**2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED**")
    add("")
    add("M4 evaluates exactly two stronger nonlinear candidate families "
        "(sklearn HistGradientBoostingClassifier, XGBoost XGBClassifier) for "
        "the PRIMARY winner task on D1/D2/D3, extending the frozen M3 path. "
        "One fixed, untuned specification per family; no resampling, no "
        "post-hoc calibration, no threshold tuning, no 2025 access. Every "
        "value below traces to a stored experiment result (task "
        f"`{summary['task']}`, protocol {summary['protocol_version']}, "
        f"matrix {summary['matrix_content_hash'][:12]}…).")
    add("")
    add("## 1. Fixed candidate specifications (chosen before validation)")
    add("")
    hgb = summary["hgb_spec"]
    add(f"- HGB ({hgb['estimator']}): loss={hgb['loss']}, "
        f"learning_rate={hgb['learning_rate']}, max_iter={hgb['max_iter']}, "
        f"max_leaf_nodes={hgb['max_leaf_nodes']}, "
        f"max_depth={hgb['max_depth']}, "
        f"min_samples_leaf={hgb['min_samples_leaf']}, "
        f"l2_regularization={hgb['l2_regularization']}, "
        f"max_bins={hgb['max_bins']}, "
        f"early_stopping={hgb['early_stopping']} "
        "(single justified non-default: sklearn default 'auto' would hold "
        "out 10% of training rows for early stopping; M4 forbids "
        "validation-driven training), "
        f"class_weight={hgb['class_weight']}, "
        f"random_state={hgb['random_state']}; sklearn "
        f"{summary['sklearn_version']}")
    xgb = summary["xgb_spec"]
    add(f"- XGB ({xgb['estimator']}): objective={xgb['objective']}, "
        f"n_estimators={xgb['n_estimators']}, max_depth={xgb['max_depth']} "
        "(conservative vs library default 6 for the rare ~5.5% winner "
        "class), learning_rate=0.1, subsample=1.0/colsample=1.0 "
        "(deterministic full-data boosting), "
        f"min_child_weight={xgb['min_child_weight']}, "
        f"reg_lambda={xgb['reg_lambda']}, reg_alpha={xgb['reg_alpha']}, "
        f"gamma={xgb['gamma']}, tree_method={xgb['tree_method']} "
        "(CPU only, no GPU), eval_metric=logloss recorded with NO eval set "
        "supplied (no early stopping), scale_pos_weight=1 (natural "
        "prevalence), "
        f"random_state={xgb['random_state']}, n_jobs={xgb['n_jobs']} "
        "(controlled local CPU); xgboost "
        f"{summary['xgboost_version']}")
    add(f"- task: {summary['task']}; feature set: {summary['feature_set']} "
        f"(frozen full 84-feature surface); seed: {summary['seed']}")
    add(f"- training weighting: state_equal; tuning: {summary['tuning']}")
    add(f"- probability semantic: {summary['probability_semantics']} "
        "(per-driver P(win); never normalized across drivers)")
    add(f"- calibration fitted: {summary['calibration_fitted']}")
    add("")
    add("## 2. Preprocessing (fitted on TRAIN only)")
    add("")
    add(f"- {summary['preprocessing_note']}")
    add("")
    add("| model | fold | train rows | train races | train prevalence | "
        "val rows | val races | features in | transformed dim |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for model in models:
        for fold in folds:
            entry = per_model[model]["per_fold"][fold]
            add(f"| {model} | {fold} | {entry['training_rows']} | "
                f"{entry['training_races']} | "
                f"{_fmt(entry['train_prevalence'])} | "
                f"{entry['validation_rows']} | {entry['validation_races']} | "
                f"{entry['n_features_in']} | {entry['transformed_dim']} |")
    add("")
    add("Fit warnings: " + "; ".join(
        f"{m}/{f}=" + ("; ".join(
            per_model[m]['per_fold'][f]['fit_warnings']) or "none")
        for m in models for f in folds))
    add("")
    for section, metrics in (
            ("3. Headline probability quality (race-macro)",
             ("log_loss", "brier")),
            ("4. Discrimination (race-macro ROC-AUC / PR-AUC)",
             ("roc_auc", "pr_auc"))):
        add(f"## {section}")
        add("")
        for metric in metrics:
            better = "lower is better" if metric in (
                "log_loss", "brier") else "higher is better"
            add(f"### {metric} (race-macro; {better})")
            add("")
            add("| model | " + " | ".join(folds)
                + " | mean | std | min | max | range |")
            add("| --- | " + " | ".join(["---"] * len(folds))
                + " | --- | --- | --- | --- | --- |")
            for model in models:
                cells = [_fmt(_model_value_for_metric(
                    per_model[model]["per_fold"][f], metric))
                    for f in folds]
                node = agg_of[model][metric]
                spread = (node["max"] - node["min"]
                          if node["max"] is not None
                          and node["min"] is not None else None)
                cells += [_fmt(node["mean"]), _fmt(node["std"]),
                          _fmt(node["min"]), _fmt(node["max"]),
                          _fmt(spread)]
                add(f"| {model} | " + " | ".join(cells) + " |")
            add("")
            for scope in ("state_pooled",):
                add(f"_{scope} (diagnostic):_ "
                    + "; ".join(
                        f"{m}=" + "/".join(
                            _fmt(per_model[m]["per_fold"][f]["metrics"]
                                 .get(metric, {}).get(scope, {})
                                 .get("value"))
                            for f in folds)
                        for m in models))
            add("")
    add("## 5. Calibration (ECE, 10 equal-width bins; raw probabilities)")
    add("")
    add("| model | " + " | ".join(folds) + " | mean |")
    add("| --- | " + " | ".join(["---"] * len(folds)) + " | --- |")
    for model in models:
        add("| " + model + " | " + " | ".join(
            _fmt(per_model[model]["per_fold"][f]["calibration_ece"])
            for f in folds)
            + f" | {_fmt(agg_of[model]['expected_calibration_error']['mean'])} |")
    add("")
    add("Reliability-bin detail is stored per experiment result; "
        "no calibrator was fitted.")
    add("")
    add("## 6. Race-stage performance (race-macro)")
    add("")
    for metric in ("log_loss", "brier"):
        add(f"### {metric} by stage")
        add("")
        for model in models:
            for fold in folds:
                stage_payload = per_model[model]["per_fold"][fold][
                    "stage_metrics"].get(metric, {})
                if stage_payload.get("status") != "OK":
                    add(f"- {model}/{fold}: N/A")
                    continue
                cells = [_fmt(stage_payload.get(stage, {}).get(
                    "race_macro", {}).get("value"))
                    for stage in ("EARLY", "MID", "LATE")]
                add(f"- {model}/{fold}: EARLY={cells[0]} MID={cells[1]} "
                    f"LATE={cells[2]}")
        add("")
    add("## 7. Synchronized winner top-k (coverage-qualified)")
    add("")
    add("| model | fold | top-1 | top-3 | eval states | skipped "
        "(none/winner-unobs/degen) | min field |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for model in models:
        for fold in folds:
            payload = per_model[model]["per_fold"][fold][
                "race_metrics"].get("winner_top_k", {})
            if payload.get("status") != "OK":
                add(f"| {model} | {fold} | N/A | N/A | N/A | N/A | N/A |")
                continue
            acc = payload.get("accuracy", {})
            skipped = (f"{payload.get('n_skipped_no_predictions')}/"
                       f"{payload.get('n_skipped_winner_unobservable')}/"
                       f"{payload.get('n_skipped_degenerate')}")
            add(f"| {model} | {fold} | {_fmt(acc.get('top1'))} | "
                f"{_fmt(acc.get('top3'))} | "
                f"{payload.get('n_evaluation_states')} | {skipped} | "
                f"{payload.get('min_observable_field_size')} |")
    add("")
    add("Top-3 on fields smaller than 3 is reported for completeness but is "
        "NOT genuine three-way discrimination (min observable field = 2).")
    add("")
    add("## 8. Comparison vs M3 Logistic Regression (stored M3 artifacts)")
    add("")
    for metric, node in vs_lr.items():
        add(f"### {metric} ({node['direction']} is better; "
            f"reference: {node['reference']})")
        add("")
        add("| fold | model | model | logreg | diff | verdict |")
        add("| --- | --- | --- | --- | --- | --- |")
        for fold in folds:
            for model in models:
                row = node["per_fold"][fold][model]
                add(f"| {fold} | {model} | {_fmt(row['model_value'])} | "
                    f"{_fmt(row['reference_value'])} | "
                    f"{_fmt(row['difference'])} | {row['verdict']} |")
        for model in models:
            row = node["aggregate"][model]
            add(f"| mean | {model} | {_fmt(row['model_mean'])} | "
                f"{_fmt(row['reference_mean'])} | "
                f"{_fmt(row['mean_difference'])} | {row['mean_verdict']} |")
        add("")
    add("No combined score is constructed; no significance is claimed.")
    add("")
    add("## 9. Comparison vs M2 baseline floor (stored M2 artifacts)")
    add("")
    for metric, node in vs_floor.items():
        add(f"### {metric} ({node['direction']} is better; "
            f"baseline: {node['baseline']})")
        add("")
        add("| fold | model | model | baseline | diff | verdict |")
        add("| --- | --- | --- | --- | --- | --- |")
        for fold in folds:
            for model in models:
                row = node["per_fold"][fold][model]
                add(f"| {fold} | {model} | {_fmt(row['model_value'])} | "
                    f"{_fmt(row['baseline_value'])} | "
                    f"{_fmt(row['difference'])} | {row['verdict']} |")
        for model in models:
            row = node["aggregate"][model]
            add(f"| mean | {model} | {_fmt(row['model_mean'])} | "
                f"{_fmt(row['baseline_mean'])} | "
                f"{_fmt(row['mean_difference'])} | "
                f"{row['mean_verdict']} |")
        add("")
    add("## 10. Determinism, runtime, latency, memory")
    add("")
    for model in models:
        det = per_model[model]["determinism_check"]
        add(f"- determinism refit ({model}/{det['fold']}): same experiment "
            f"id = {det['same_experiment_id']}; metrics identical = "
            f"{det['metrics_identical']}; max abs probability difference = "
            f"{det['max_abs_probability_difference']:.3e}")
    add("- per-fold fit/predict wall time:")
    for model in models:
        for fold in folds:
            entry = per_model[model]["per_fold"][fold]
            lat = entry["latency"] or {}
            batch = (lat.get("batch") or {})
            add(f"  - {model}/{fold}: fit={_fmt(entry['fit_seconds'], 2)} s "
                f"predict_total={_fmt(entry['prediction_seconds'], 2)} s "
                f"batch_mean={_fmt(batch.get('mean'), 4)} s "
                f"throughput={_fmt(batch.get('states_per_second'), 1)} "
                "states/s")
    add(f"- full suite wall time: "
        f"{summary['runtime'].get('total_seconds', 0):.1f} s")
    rss = summary.get("peak_rss_bytes")
    add(f"- peak RSS: {rss / 1e9:.2f} GB" if rss
        else "- peak RSS: NOT MEASURED")
    add("")
    add("## 11. Artifacts")
    add("")
    for model in models:
        for entry in per_model[model]["experiments"]:
            add(f"- {entry['model']}/{entry['fold']}: "
                f"`{entry['experiment_id']}`")
    add("")
    add(f"Suite summary: `{summary.get('_summary_path', NONLINEAR_SUITE_FILENAME)}` "
        "(machine-readable; this document was rendered from it).")
    add(f"M3 LOGREG suite: schema {summary.get('logreg_suite_schema')} "
        "(values in §8 loaded from stored M3 artifacts).")
    add(f"M2 baseline suite: schema {summary.get('baseline_suite_schema')} "
        "(values in §9 loaded from stored M2 artifacts).")
    add("")
    add("## 12. Limitations and M5 outlook")
    add("")
    add("- Three development folds is a coarse robustness signal; fold "
        "dispersion is reported, not hidden.")
    add("- State rows are not independent observations; headline conclusions "
        "use race-macro aggregation.")
    add("- No tuning was performed: these are representative fixed "
        "specifications, not optimized models. M5/M6 may tune inside "
        "training history only.")
    add("- Raw probabilities only; calibration decisions belong later.")
    add("- 2025 was not evaluated and must remain protected until the final "
        "locked holdout.")
    rec = summary.get("m5_recommendation")
    add(f"- M5 recommendation: {rec if rec else 'PENDING'}")
    add("")
    return "\n".join(lines) + "\n"
