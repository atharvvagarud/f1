"""M3 Logistic Regression reference suite: execution + disk-derived summary.

Chain of custody: stored model experiment results (``write_experiment``)
-> suite summary (read back from ``result.json`` on disk) ->
human-readable markdown (rendered from the summary file only). Baseline
comparison values are loaded from the stored M2 suite summary
(``baseline_suite_v1.json``), never retyped.
"""

from __future__ import annotations

import json
from pathlib import Path

from raceintel.config import V2Paths
from raceintel.model_lab import aggregation as AGG
from raceintel.model_lab import experiment as EX
from raceintel.model_lab import logreg as LR
from raceintel.model_lab import model_runner as MR
from raceintel.model_lab import results as RES
from raceintel.model_lab import runner as RUN
from raceintel.model_lab import suite as SUITE
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
MODEL_SUITE_FILENAME = "logreg_reference_v1.json"

#: Frozen M2 comparison references: metric -> (baseline, direction).
#: Direction "lower" means lower is better (BEATS when logreg < baseline).
COMPARISON_REFERENCES = {
    "log_loss": ("CLASS_PRIOR", "lower"),
    "brier": ("CURRENT_LEADER", "lower"),
    "roc_auc": ("CURRENT_LEADER", "higher"),
    "pr_auc": ("CURRENT_LEADER", "higher"),
    "expected_calibration_error": ("CLASS_PRIOR", "lower"),
    "winner_top1": ("CURRENT_LEADER", "higher"),
}


def reports_dir(paths=None, root=None) -> Path:
    return SUITE.reports_dir(paths, root)


def default_out(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / MODEL_SUITE_FILENAME


def baseline_suite_path(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / SUITE.SUITE_FILENAME


def load_baseline_suite(paths=None, root=None) -> dict:
    path = baseline_suite_path(paths, root)
    if not path.exists():
        raise ExperimentConfigError(
            f"M2 baseline suite summary is missing at {path}; "
            "M3 comparison requires stored M2 artifacts")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _verdict(direction: str, model_value, baseline_value,
             tol: float = 1e-12) -> str:
    if model_value is None or baseline_value is None:
        return "NOT_COMPARABLE"
    if abs(model_value - baseline_value) <= tol:
        return "MATCHES"
    if direction == "lower":
        return "BEATS" if model_value < baseline_value else "DOES NOT BEAT"
    return "BEATS" if model_value > baseline_value else "DOES NOT BEAT"


def _read_result(dest: str) -> tuple:
    return RES.read_experiment(dest)


def build_model_summary(*, task: str, model: str, folds: tuple,
                        feature_set: str, seed: int,
                        experiments: list, timings: dict,
                        determinism: dict,
                        baseline_suite: dict,
                        git_commit: str | None) -> dict:
    """Derive the model summary by re-reading stored result documents."""
    from raceintel.model_lab.protocol import (
        EXPECTED_MANIFEST_SHA256,
        EXPECTED_MATRIX_PARQUET_SHA256,
    )
    per_fold: dict = {}
    for entry in experiments:
        config, result = _read_result(entry["dest"])
        fold = config.fold
        calibration_ece = (
            result.calibration["expected_calibration_error"]
            if result.calibration else None)
        topk = result.race_metrics.get("winner_top_k", {})
        topk_acc = topk.get("accuracy", {}) \
            if topk.get("status") == "OK" else {}
        per_fold[fold] = {
            "experiment_id": config.experiment_id,
            "dest": entry["dest"],
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
            "sklearn_version": result.artifact_refs.get("sklearn_version"),
            "convergence_warnings": result.artifact_refs.get(
                "convergence_warnings", []),
            "coefficient_sanity": result.artifact_refs.get(
                "coefficient_sanity"),
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

    aggregates: dict = {}
    for metric in ("log_loss", "brier", "roc_auc", "pr_auc"):
        per_fold_values = {}
        for fold in folds:
            payload = per_fold[fold]["metrics"].get(metric, {})
            per_fold_values[fold] = (
                payload.get("race_macro", {}).get("value")
                if payload.get("status") == "OK" else None)
        aggregates[metric] = SUITE._json_safe_number(
            AGG.aggregate_folds(per_fold_values))
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

    # --- comparison against stored M2 artifacts (per fold + aggregate) ---
    comparison: dict = {}
    base_per_fold = baseline_suite.get("per_fold", {})
    base_agg = baseline_suite.get("aggregates", {})
    for metric, (baseline, direction) in COMPARISON_REFERENCES.items():
        entry = {"baseline": baseline, "direction": direction,
                 "per_fold": {}, "aggregate": {}}
        for fold in folds:
            if metric == "winner_top1":
                payload = per_fold[fold]["race_metrics"].get(
                    "winner_top_k", {})
                model_value = (payload.get("accuracy") or {}).get("top1") \
                    if payload.get("status") == "OK" else None
                base_payload = base_per_fold.get(fold, {}).get(
                    baseline, {}).get("race_metrics", {}).get(
                    "winner_top_k", {})
                base_value = (base_payload.get("accuracy") or {}).get("top1") \
                    if base_payload.get("status") == "OK" else None
            elif metric == "expected_calibration_error":
                model_value = per_fold[fold]["calibration_ece"]
                base_value = base_per_fold.get(fold, {}).get(
                    baseline, {}).get("calibration_ece")
            else:
                payload = per_fold[fold]["metrics"].get(metric, {})
                model_value = payload.get("race_macro", {}).get("value") \
                    if payload.get("status") == "OK" else None
                base_payload = base_per_fold.get(fold, {}).get(
                    baseline, {}).get("metrics", {}).get(metric, {})
                base_value = base_payload.get("race_macro", {}).get("value") \
                    if base_payload.get("status") == "OK" else None
            difference = (model_value - base_value
                          if model_value is not None
                          and base_value is not None else None)
            entry["per_fold"][fold] = {
                "model_value": model_value,
                "baseline_value": base_value,
                "difference": difference,
                "verdict": _verdict(direction, model_value, base_value),
            }
        if metric == "winner_top1":
            model_mean = aggregates["winner_top_k"]["top1"]["mean"]
            base_mean = (base_agg.get(baseline, {}).get("winner_top_k", {})
                         .get("top1", {}).get("mean"))
        elif metric == "expected_calibration_error":
            # The M2 suite stores ECE per fold only (no cross-fold aggregate),
            # so the baseline mean is the simple mean of the stored per-fold
            # values — the same fold aggregation the M2 aggregates use.
            model_mean = aggregates[metric]["mean"]
            base_values = [
                entry["baseline_value"]
                for entry in entry["per_fold"].values()
            ]
            defined = [v for v in base_values if v is not None]
            base_mean = (sum(defined) / len(defined)) if defined else None
        else:
            model_mean = aggregates[metric]["mean"]
            base_agg_metric = base_agg.get(baseline, {}).get(metric, {})
            base_mean = base_agg_metric.get("mean")
        entry["aggregate"] = {
            "model_mean": model_mean,
            "baseline_mean": base_mean,
            "difference": (model_mean - base_mean
                           if model_mean is not None
                           and base_mean is not None else None),
            "verdict": _verdict(direction, model_mean, base_mean),
        }
        comparison[metric] = entry

    summary = {
        "schema_version": SUITE_SCHEMA_VERSION,
        "task": task,
        "model": model,
        "model_family": LR.LOGREG_FAMILY,
        "model_spec": LR.logreg_model_parameters(),
        "preprocessing_spec": LR.PRE.preprocessing_contract_dict(),
        "sklearn_version": LR.SKLEARN_VERSION,
        "folds": list(folds),
        "feature_set": feature_set,
        "seed": seed,
        "tuning": "none (fixed reference specification)",
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
        "experiments": [
            {"model": e["model"], "fold": e["fold"],
             "experiment_id": e["experiment_id"], "dest": e["dest"]}
            for e in experiments],
        "per_fold": per_fold,
        "aggregates": aggregates,
        "baseline_comparison": comparison,
        "determinism_check": determinism,
        "runtime": timings,
        "peak_rss_bytes": SUITE._peak_rss_bytes(),
        "warnings": [w for fold in folds
                     for w in per_fold[fold]["warnings"]],
    }
    return summary


def run_model_suite(*, task: str = "winner", model: str = "LOGREG",
                    folds=("D1", "D2", "D3"),
                    feature_set: str = "ALL_84",
                    seed: int = EX.PROJECT_SEED, paths=None, root=None,
                    out=None) -> dict:
    """Execute the M3 reference suite (LOGREG x winner x D1/D2/D3)."""
    family = MR.resolve_model(model)
    if task != MR.M3_TASK:
        raise ExperimentConfigError(
            f"M3 evaluates task {MR.M3_TASK!r} only; got {task!r}")
    folds = SUITE.parse_folds(",".join(folds))
    for fold in folds:
        RUN.resolve_development_fold(fold)
    baseline_suite = load_baseline_suite(paths, root)

    timings: dict = {}
    with TIMING_SCOPE() as total:
        experiments: list = []
        phase_seconds: dict = {}
        for fold in folds:
            out_exp = MR.run_model_experiment(
                task=task, model=model, fold=fold,
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
        timings["experiment_phases_total_seconds"] = phase_seconds

        with TimerBlock(timings, "determinism_check_seconds"):
            first = MR.run_model_experiment(
                task=task, model=model, fold=folds[0],
                feature_set=feature_set, seed=seed, paths=paths,
                root=root, return_predictions=True)
            second = MR.run_model_experiment(
                task=task, model=model, fold=folds[0],
                feature_set=feature_set, seed=seed, paths=paths,
                root=root, return_predictions=True)
            import numpy as _np
            diff = float(_np.max(_np.abs(
                first["predictions"] - second["predictions"])))
            first_metrics = _read_result(first["dest"])[1].metrics
            second_metrics = _read_result(second["dest"])[1].metrics
            determinism = {
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
    summary = build_model_summary(
        task=task, model=family, folds=folds, feature_set=feature_set,
        seed=seed, experiments=experiments,
        timings={**timings, "environment_probe_seconds": t.seconds},
        determinism=determinism, baseline_suite=baseline_suite,
        git_commit=env.get("git_commit"))

    dest = Path(out) if out is not None else default_out(paths, root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    RES.atomic_write_json(dest, summary)
    summary["_summary_path"] = str(dest)
    return summary


class TIMING_SCOPE:
    """Context manager alias kept local so suite timing stays explicit."""

    def __enter__(self):
        from raceintel.model_lab import timing as TIMING
        self._timer = TIMING.Timer()
        return self._timer.__enter__()

    def __exit__(self, *exc):
        return self._timer.__exit__(*exc)


class TimerBlock:
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


def render_logreg_report(summary: dict) -> str:
    """Render the human-readable M3 report from the stored summary only."""
    folds = summary["folds"]
    per_fold = summary["per_fold"]
    agg = summary["aggregates"]
    comp = summary["baseline_comparison"]
    spec = summary["model_spec"]
    pre = summary["preprocessing_spec"]
    lines = []
    add = lines.append
    add("# Model Lab LogReg Reference Report (M3)")
    add("")
    add("**DEVELOPMENT RESULTS — 2022 / 2023 / 2024**")
    add("")
    add("**2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED**")
    add("")
    add("The M3 Logistic Regression reference is the first candidate ML model: "
        "one fixed, untuned specification evaluated through the exact M2 "
        "canonical path. No tuning, no resampling, no post-hoc calibration, "
        "no 2025 access. Every value below traces to a stored experiment "
        f"result (task `{summary['task']}`, protocol "
        f"{summary['protocol_version']}, matrix "
        f"{summary['matrix_content_hash'][:12]}…).")
    add("")
    add("## 1. Fixed specification (chosen before observing validation)")
    add("")
    add(f"- estimator: {spec['estimator']} (penalty={spec['penalty']}, "
        f"C={spec['C']}, solver={spec['solver']}, "
        f"max_iter={spec['max_iter']}, class_weight={spec['class_weight']}, "
        f"random_state={spec['random_state']})")
    add(f"- task: {summary['task']}; feature set: {summary['feature_set']} "
        f"(frozen full 84-feature surface); seed: {summary['seed']}")
    add(f"- training weighting: state_equal (no resampling, no class "
        f"rebalancing); tuning: {summary['tuning']}")
    add(f"- probability semantic: {summary['probability_semantics']} "
        "(per-driver P(win); never normalized across drivers)")
    add(f"- calibration fitted: {summary['calibration_fitted']}; "
        f"sklearn: {summary['sklearn_version']}")
    add("")
    add("## 2. Preprocessing (fitted on TRAIN only)")
    add("")
    add(f"- numeric: {pre['numeric_imputation']}; {pre['numeric_scaling']}")
    add(f"- boolean: {pre['boolean_imputation']}")
    add(f"- categorical: {pre['categorical_imputation']}; "
        f"{pre['categorical_encoding']}")
    add(f"- native missing/categorical: {pre['native_missing']}/"
        f"{pre['native_categorical']}; fit scope: {pre['fit_scope']}")
    add("")
    add("| fold | train rows | train races | train prevalence | val rows | "
        "val races | features in | transformed dim |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for fold in folds:
        entry = per_fold[fold]
        add(f"| {fold} | {entry['training_rows']} | {entry['training_races']} | "
            f"{_fmt(entry['train_prevalence'])} | {entry['validation_rows']} | "
            f"{entry['validation_races']} | {entry['n_features_in']} | "
            f"{entry['transformed_dim']} |")
    add("")
    conv = {fold: (per_fold[fold]["convergence_warnings"] or ["none"])
            for fold in folds}
    add("Convergence warnings: " + "; ".join(
        f"{fold}={'; '.join(conv[fold])}" for fold in folds))
    add("")
    add("## 3. Headline probability quality (race-macro)")
    add("")
    for metric in ("log_loss", "brier"):
        add(f"### {metric} (race-macro; lower is better)")
        add("")
        add("| scope | " + " | ".join(folds) + " | mean | std | min | max |")
        add("| --- | " + " | ".join(["---"] * len(folds))
            + " | --- | --- | --- | --- |")
        for scope in ("race_macro", "state_pooled"):
            cells = []
            for fold in folds:
                payload = per_fold[fold]["metrics"].get(metric, {})
                value = (payload.get(scope, {}).get("value")
                         if payload.get("status") == "OK" else None)
                cells.append(_fmt(value))
            if scope == "race_macro":
                node = agg[metric]
                cells += [_fmt(node["mean"]), _fmt(node["std"]),
                          _fmt(node["min"]), _fmt(node["max"])]
            else:
                pooled = [
                    per_fold[fold]["metrics"].get(metric, {}).get(
                        "state_pooled", {}).get("value")
                    if per_fold[fold]["metrics"].get(
                        metric, {}).get("status") == "OK" else None
                    for fold in folds]
                defined = [v for v in pooled if v is not None]
                cells += [_fmt(sum(defined) / len(defined)) if defined
                          else "N/A", "N/A", "N/A", "N/A"]
            add(f"| {scope} | " + " | ".join(cells) + " |")
        add("")
    add("## 4. Discrimination (race-macro ROC-AUC / PR-AUC)")
    add("")
    for metric in ("roc_auc", "pr_auc"):
        add(f"### {metric} (race-macro; higher is better)")
        add("")
        add("| " + " | ".join(folds) + " | mean | std | min | max |")
        add("| " + " | ".join(["---"] * len(folds))
            + " | --- | --- | --- | --- |")
        cells = []
        for fold in folds:
            payload = per_fold[fold]["metrics"].get(metric, {})
            cells.append(_fmt(payload.get("race_macro", {}).get("value"))
                         if payload.get("status") == "OK" else "N/A")
        node = agg[metric]
        cells += [_fmt(node["mean"]), _fmt(node["std"]), _fmt(node["min"]),
                  _fmt(node["max"])]
        add("| " + " | ".join(cells) + " |")
        add("")
    add("## 5. Calibration (ECE, 10 equal-width bins; raw probabilities)")
    add("")
    add("| " + " | ".join(folds) + " | mean |")
    add("| " + " | ".join(["---"] * len(folds)) + " | --- |")
    add("| " + " | ".join(_fmt(per_fold[fold]["calibration_ece"])
                           for fold in folds)
        + f" | {_fmt(agg['expected_calibration_error']['mean'])} |")
    add("")
    add("Reliability-bin detail is stored per experiment result; "
        "no calibrator was fitted.")
    add("")
    add("## 6. Race-stage performance (race-macro)")
    add("")
    for metric in ("log_loss", "brier"):
        add(f"### {metric} by stage")
        add("")
        for fold in folds:
            stage_payload = per_fold[fold]["stage_metrics"].get(metric, {})
            if stage_payload.get("status") != "OK":
                add(f"- {fold}: N/A")
                continue
            cells = [_fmt(stage_payload.get(stage, {}).get(
                "race_macro", {}).get("value"))
                for stage in ("EARLY", "MID", "LATE")]
            add(f"- {fold}: EARLY={cells[0]} MID={cells[1]} LATE={cells[2]}")
        add("")
    add("## 7. Synchronized winner top-k (coverage-qualified)")
    add("")
    add("| fold | top-1 | top-3 | eval states | skipped "
        "(none/winner-unobs/degen) | min field |")
    add("| --- | --- | --- | --- | --- | --- |")
    for fold in folds:
        payload = per_fold[fold]["race_metrics"].get("winner_top_k", {})
        if payload.get("status") != "OK":
            add(f"| {fold} | N/A | N/A | N/A | N/A | N/A |")
            continue
        acc = payload.get("accuracy", {})
        skipped = (f"{payload.get('n_skipped_no_predictions')}/"
                   f"{payload.get('n_skipped_winner_unobservable')}/"
                   f"{payload.get('n_skipped_degenerate')}")
        add(f"| {fold} | {_fmt(acc.get('top1'))} | {_fmt(acc.get('top3'))} | "
            f"{payload.get('n_evaluation_states')} | {skipped} | "
            f"{payload.get('min_observable_field_size')} |")
    add("")
    add("Top-3 on fields smaller than 3 is reported for completeness but is "
        "NOT genuine three-way discrimination (min observable field = 2).")
    add("")
    add("## 8. M2 baseline comparison (from stored M2 artifacts)")
    add("")
    add("| metric | baseline | fold | logreg | baseline | diff | verdict |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for metric, entry in comp.items():
        for fold in folds:
            row = entry["per_fold"][fold]
            add(f"| {metric} | {entry['baseline']} | {fold} | "
                f"{_fmt(row['model_value'])} | {_fmt(row['baseline_value'])} | "
                f"{_fmt(row['difference'])} | {row['verdict']} |")
        row = entry["aggregate"]
        add(f"| {metric} | {entry['baseline']} | mean | "
            f"{_fmt(row['model_mean'])} | {_fmt(row['baseline_mean'])} | "
            f"{_fmt(row['difference'])} | {row['verdict']} |")
    add("")
    add("No combined score is constructed; no significance is claimed.")
    add("")
    add("## 9. Determinism, runtime, latency, memory")
    add("")
    det = summary["determinism_check"]
    add(f"- determinism refit ({det['fold']}): same experiment id = "
        f"{det['same_experiment_id']}; metrics identical = "
        f"{det['metrics_identical']}; max abs probability difference = "
        f"{det['max_abs_probability_difference']:.3e}")
    add("- per-fold fit/predict wall time:")
    for fold in folds:
        entry = per_fold[fold]
        lat = entry["latency"] or {}
        batch = (lat.get("batch") or {})
        add(f"  - {fold}: fit={_fmt(entry['fit_seconds'], 2)} s "
            f"predict_total={_fmt(entry['prediction_seconds'], 2)} s "
            f"batch_mean={_fmt(batch.get('mean'), 4)} s "
            f"throughput={_fmt(batch.get('states_per_second'), 1)} states/s")
    add(f"- full suite wall time: "
        f"{summary['runtime'].get('total_seconds', 0):.1f} s")
    rss = summary.get("peak_rss_bytes")
    add(f"- peak RSS: {rss / 1e9:.2f} GB" if rss else "- peak RSS: NOT MEASURED")
    add("")
    add("## 10. Artifacts")
    add("")
    for entry in summary["experiments"]:
        add(f"- {entry['model']}/{entry['fold']}: `{entry['experiment_id']}`")
    add("")
    add(f"Suite summary: `{summary.get('_summary_path', MODEL_SUITE_FILENAME)}` "
        "(machine-readable; this document was rendered from it).")
    add(f"M2 baseline suite: schema {summary.get('baseline_suite_schema')} "
        "(values in §8 loaded from stored M2 artifacts).")
    add("")
    return "\n".join(lines) + "\n"
