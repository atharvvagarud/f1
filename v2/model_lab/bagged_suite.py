"""M5 bagged-tree candidate suite: execution + disk-derived summary + report.

Chain of custody: stored model experiment results (``write_experiment``)
-> suite summary (read back from ``result.json`` on disk) -> human-readable
markdown (rendered from the summary file only). Comparison values are loaded
from the stored artifacts only:

- M3 LogReg reference: ``logreg_reference_v1.json``
- M4 boosted references: ``nonlinear_candidates_v1.json`` (HGB + XGB)
- M2 baseline floor: ``baseline_suite_v1.json``

Runs exactly six experiments: ExtraTrees x winner x D1/D2/D3 + RandomForest
x winner x D1/D2/D3. No LOGREG/HGB/XGB rerun. Determinism refits reuse the
same experiment identity for ExtraTrees D1 and RandomForest D1.
"""

from __future__ import annotations

import json
from pathlib import Path

from v2.model_lab import aggregation as AGG
from v2.model_lab import bagged_candidates as BC
from v2.model_lab import bagged_runner as BR
from v2.model_lab import experiment as EX
from v2.model_lab import model_suite as MSUITE
from v2.model_lab import nonlinear_suite as NSUITE
from v2.model_lab import results as RES
from v2.model_lab import runner as RUN
from v2.model_lab import suite as SUITE
from v2.model_lab import tree_candidates as TC
from v2.model_lab.errors import ExperimentConfigError
from v2.model_lab.protocol import (
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
BAGGED_SUITE_FILENAME = "bagged_candidates_v1.json"

#: Model families executed by this suite, in execution order.
SUITE_MODELS = (BC.EXTRA_TREES_FAMILY, BC.RANDOM_FOREST_FAMILY)
#: M4 boosted reference families (loaded from stored artifacts; never rerun).
M4_REFERENCE_MODELS = (TC.HGB_FAMILY, TC.XGB_FAMILY)

#: Metric -> direction for every reference comparison.
COMPARISON_DIRECTIONS = {
    "log_loss": "lower",
    "brier": "lower",
    "roc_auc": "higher",
    "pr_auc": "higher",
    "expected_calibration_error": "lower",
    "winner_top1": "higher",
}

#: Metric -> (M2 baseline, direction) for the frozen baseline floor.
BASELINE_FLOOR_REFERENCES = dict(MSUITE.COMPARISON_REFERENCES)


def reports_dir(paths=None, root=None) -> Path:
    return SUITE.reports_dir(paths, root)


def default_out(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / BAGGED_SUITE_FILENAME


def logreg_suite_path(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / MSUITE.MODEL_SUITE_FILENAME


def nonlinear_suite_path(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / NSUITE.NONLINEAR_SUITE_FILENAME


def _load_json_or_fail(path: Path, label: str) -> dict:
    if not path.exists():
        raise ExperimentConfigError(
            f"{label} suite summary is missing at {path}; "
            "M5 comparison requires stored artifacts")
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def load_logreg_suite(paths=None, root=None) -> dict:
    return _load_json_or_fail(logreg_suite_path(paths, root),
                              "M3 LOGREG")


def load_nonlinear_suite(paths=None, root=None) -> dict:
    return _load_json_or_fail(nonlinear_suite_path(paths, root),
                              "M4 nonlinear")


_read_result = NSUITE._read_result
_extract_per_fold = NSUITE._extract_per_fold
_aggregate_folds = NSUITE._aggregate_folds
_model_value_for_metric = NSUITE._model_value_for_metric
_baseline_value_for_metric = NSUITE._baseline_value_for_metric
_compare_pair = NSUITE._compare_pair


def _mean_for(aggregates: dict, metric: str):
    if metric == "winner_top1":
        return aggregates.get("winner_top_k", {}).get("top1", {}).get("mean")
    return aggregates.get(metric, {}).get("mean")


def _compare_reference(*, per_model: dict, folds: tuple,
                       ref_per_fold: dict, ref_agg: dict,
                       ref_label: str) -> dict:
    """Per-fold + aggregate comparison against one stored reference."""
    comparison: dict = {}
    for metric, direction in COMPARISON_DIRECTIONS.items():
        node = {"reference": ref_label, "direction": direction,
                "per_fold": {}, "aggregate": {}}
        for fold in folds:
            ref_value = _model_value_for_metric(ref_per_fold[fold], metric)
            ref_mean = _mean_for(ref_agg, metric)
            fold_node = {}
            for family in SUITE_MODELS:
                model_value = _model_value_for_metric(
                    per_model[family]["per_fold"][fold], metric)
                model_mean = _mean_for(
                    per_model[family]["aggregates"], metric)
                fold_node[family] = _compare_pair(
                    direction, model_value, ref_value, model_mean, ref_mean)
            node["per_fold"][fold] = fold_node
        agg_node = {}
        for family in SUITE_MODELS:
            mean_value = _mean_for(per_model[family]["aggregates"], metric)
            agg_node[family] = {
                "model_mean": mean_value,
                "reference_mean": ref_mean,
                "mean_difference": (
                    mean_value - ref_mean
                    if mean_value is not None and ref_mean is not None
                    else None),
                "mean_verdict": MSUITE._verdict(direction, mean_value, ref_mean),
            }
        node["aggregate"] = agg_node
        comparison[metric] = node
    return comparison


def _baseline_floor_comparison(*, per_model: dict, folds: tuple,
                               baseline_suite: dict) -> dict:
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
    return vs_floor


def _beat_counts(node: dict, family: str, folds: tuple) -> dict:
    counts = {"BEATS": 0, "MATCHES": 0, "DOES NOT BEAT": 0,
              "NOT_COMPARABLE": 0}
    for fold in folds:
        verdict = node["per_fold"][fold][family]["verdict"]
        counts[verdict] = counts.get(verdict, 0) + 1
    return counts


def _family_finding(*, per_model: dict, folds: tuple,
                    vs_logreg: dict, vs_m4: dict) -> dict:
    """Data-only summary: how bagged models compare to linear vs boosted."""
    total = len(SUITE_MODELS) * len(folds)
    logreg_beats = {metric: sum(
        _beat_counts(vs_logreg[metric], family, folds)["BEATS"]
        for family in SUITE_MODELS) for metric in COMPARISON_DIRECTIONS}
    vs_m4_beats: dict = {}
    for ref_family, comparison in vs_m4.items():
        vs_m4_beats[ref_family] = {
            metric: {
                family: _beat_counts(comparison[metric], family, folds)[
                    "BEATS"]
                for family in SUITE_MODELS}
            for metric in COMPARISON_DIRECTIONS}
    # Bagged ensembles change the M4 conclusion only if they beat the linear
    # reference on BOTH primary probability metrics in EVERY comparison.
    changes_conclusion = (
        logreg_beats["log_loss"] == total
        and logreg_beats["brier"] == total)
    return {
        "comparisons_per_metric": total,
        "logreg_beats_counts": logreg_beats,
        "vs_m4_family_beats_counts": vs_m4_beats,
        "changes_m4_conclusion": bool(changes_conclusion),
    }


def build_bagged_summary(*, task: str, folds: tuple, feature_set: str,
                         seed: int, experiments: list, timings: dict,
                         determinism: dict, baseline_suite: dict,
                         logreg_suite: dict, nonlinear_suite: dict,
                         m6_recommendation: str | None,
                         git_commit: str | None) -> dict:
    """Derive the M5 summary by re-reading stored result documents."""
    from v2.model_lab.protocol import (
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
    vs_logreg = _compare_reference(
        per_model=per_model, folds=folds, ref_per_fold=logreg_per_fold,
        ref_agg=logreg_agg,
        ref_label="logistic_regression (M3 stored artifacts)")

    vs_m4: dict = {}
    m4_per_model = nonlinear_suite.get("per_model", {})
    for ref_family in M4_REFERENCE_MODELS:
        if ref_family not in m4_per_model:
            raise ExperimentConfigError(
                f"M4 stored suite is missing reference family {ref_family!r}")
        vs_m4[ref_family] = _compare_reference(
            per_model=per_model, folds=folds,
            ref_per_fold=m4_per_model[ref_family]["per_fold"],
            ref_agg=m4_per_model[ref_family]["aggregates"],
            ref_label=f"{ref_family} (M4 stored artifacts)")

    vs_floor = _baseline_floor_comparison(
        per_model=per_model, folds=folds, baseline_suite=baseline_suite)

    summary = {
        "schema_version": SUITE_SCHEMA_VERSION,
        "task": task,
        "models": list(SUITE_MODELS),
        "extra_trees_spec": BC.extra_trees_model_parameters(),
        "random_forest_spec": BC.random_forest_model_parameters(),
        "preprocessing_note": (
            "both candidates reuse the exact M3/M4 train-fitted preprocessing "
            "(median + StandardScaler numerics, most-frequent booleans, "
            "MISSING-sentinel + train-vocabulary one-hot categoricals); "
            "same 84 source features; densified ~106-dim representation"),
        "sklearn_version": BC.SKLEARN_VERSION,
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
        "nonlinear_suite_schema": nonlinear_suite.get("schema_version"),
        "per_model": per_model,
        "vs_logreg_reference": vs_logreg,
        "vs_m4_reference": vs_m4,
        "vs_baseline_floor": vs_floor,
        "family_finding": _family_finding(
            per_model=per_model, folds=folds, vs_logreg=vs_logreg,
            vs_m4=vs_m4),
        "runtime": timings,
        "peak_rss_bytes": SUITE._peak_rss_bytes(),
        "warnings": [w for family in SUITE_MODELS
                     for fold in folds
                     for w in per_model[family]["per_fold"][fold][
                         "warnings"]],
        "m6_recommendation": m6_recommendation,
    }
    return summary


def run_bagged_suite(*, task: str = "winner",
                     models=("extra_trees", "random_forest"),
                     folds=("D1", "D2", "D3"),
                     feature_set: str = "ALL_84",
                     seed: int = EX.PROJECT_SEED, paths=None, root=None,
                     out=None, m6_recommendation: str | None = None) -> dict:
    """Execute the M5 suite (ExtraTrees + RandomForest) x winner x D1/D2/D3."""
    if task != BR.M5_TASK:
        raise ExperimentConfigError(
            f"M5 evaluates task {BR.M5_TASK!r} only; got {task!r}")
    families = [BR.resolve_model(m) for m in models]
    if sorted(families) != sorted(SUITE_MODELS):
        raise ExperimentConfigError(
            f"M5 runs exactly {list(SUITE_MODELS)}; got {families!r}")
    folds = SUITE.parse_folds(",".join(folds))
    for fold in folds:
        RUN.resolve_development_fold(fold)
    baseline_suite = MSUITE.load_baseline_suite(paths, root)
    logreg_suite = load_logreg_suite(paths, root)
    nonlinear_suite = load_nonlinear_suite(paths, root)

    timings: dict = {}
    with NSUITE._TimingScope() as total:
        experiments: list = []
        phase_seconds: dict = {}
        per_model_seconds: dict = {}
        for family in families:
            for fold in folds:
                out_exp = BR.run_bagged_experiment(
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

        with NSUITE._TimerBlock(timings, "determinism_check_seconds"):
            import numpy as _np
            determinism = {}
            for family in families:
                first = BR.run_bagged_experiment(
                    task=task, model=family, fold=folds[0],
                    feature_set=feature_set, seed=seed, paths=paths,
                    root=root, return_predictions=True)
                second = BR.run_bagged_experiment(
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

    from v2.model_lab.results import environment_metadata
    from v2.model_lab import timing as TIMING
    with TIMING.Timer() as t:
        env = environment_metadata(
            paths.root if paths is not None else None)
    summary = build_bagged_summary(
        task=task, folds=folds, feature_set=feature_set,
        seed=seed, experiments=experiments,
        timings={**timings, "environment_probe_seconds": t.seconds},
        determinism=determinism, baseline_suite=baseline_suite,
        logreg_suite=logreg_suite, nonlinear_suite=nonlinear_suite,
        m6_recommendation=m6_recommendation,
        git_commit=env.get("git_commit"))

    dest = Path(out) if out is not None else default_out(paths, root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    RES.atomic_write_json(dest, summary)
    summary["_summary_path"] = str(dest)
    return summary


def _fmt(value, digits: int = 6):
    return NSUITE._fmt(value, digits)


def _render_reference(add, *, title: str, node: dict, folds: tuple,
                      models: tuple) -> None:
    add(f"## {title}")
    add("")
    for metric, metric_node in node.items():
        add(f"### {metric} ({metric_node['direction']} is better; "
            f"reference: {metric_node['reference']})")
        add("")
        add("| fold | model | model | reference | diff | verdict |")
        add("| --- | --- | --- | --- | --- | --- |")
        for fold in folds:
            for model in models:
                row = metric_node["per_fold"][fold][model]
                add(f"| {fold} | {model} | {_fmt(row['model_value'])} | "
                    f"{_fmt(row['reference_value'])} | "
                    f"{_fmt(row['difference'])} | {row['verdict']} |")
        for model in models:
            row = metric_node["aggregate"][model]
            add(f"| mean | {model} | {_fmt(row['model_mean'])} | "
                f"{_fmt(row['reference_mean'])} | "
                f"{_fmt(row['mean_difference'])} | {row['mean_verdict']} |")
        add("")


def render_bagged_report(summary: dict) -> str:
    """Render the human-readable M5 report from the stored summary only."""
    folds = summary["folds"]
    models = summary["models"]
    per_model = summary["per_model"]
    agg_of = {m: per_model[m]["aggregates"] for m in models}
    vs_lr = summary["vs_logreg_reference"]
    vs_m4 = summary["vs_m4_reference"]
    vs_floor = summary["vs_baseline_floor"]
    lines = []
    add = lines.append
    add("# Model Lab Bagged Trees Report (M5)")
    add("")
    add("**DEVELOPMENT RESULTS — 2022 / 2023 / 2024**")
    add("")
    add("**2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED**")
    add("")
    add("M5 evaluates exactly two bagged/randomized tree candidate families "
        "(sklearn ExtraTreesClassifier, RandomForestClassifier) for the "
        "PRIMARY winner task on D1/D2/D3, extending the frozen M3/M4 path. "
        "One fixed, untuned specification per family; no resampling, no "
        "class rebalancing, no post-hoc calibration, no threshold tuning, no "
        "2025 access. Every value below traces to a stored experiment result "
        f"(task `{summary['task']}`, protocol {summary['protocol_version']}, "
        f"matrix {summary['matrix_content_hash'][:12]}…).")
    add("")
    add("## 1. Fixed candidate specifications (chosen before validation)")
    add("")
    et = summary["extra_trees_spec"]
    add(f"- ExtraTrees ({et['estimator']}): n_estimators={et['n_estimators']}, "
        f"criterion={et['criterion']}, max_depth={et['max_depth']}, "
        f"min_samples_split={et['min_samples_split']}, "
        f"min_samples_leaf={et['min_samples_leaf']}, "
        f"max_features={et['max_features']}, bootstrap={et['bootstrap']}, "
        f"class_weight={et['class_weight']}, n_jobs={et['n_jobs']} "
        f"(controlled local CPU), random_state={et['random_state']}; "
        f"sklearn {summary['sklearn_version']}")
    rf = summary["random_forest_spec"]
    add(f"- RandomForest ({rf['estimator']}): n_estimators={rf['n_estimators']}, "
        f"criterion={rf['criterion']}, max_depth={rf['max_depth']}, "
        f"min_samples_split={rf['min_samples_split']}, "
        f"min_samples_leaf={rf['min_samples_leaf']}, "
        f"max_features={rf['max_features']}, bootstrap={rf['bootstrap']}, "
        f"class_weight={rf['class_weight']}, n_jobs={rf['n_jobs']} "
        f"(controlled local CPU), random_state={rf['random_state']}; "
        f"sklearn {summary['sklearn_version']}")
    add("- family contrast kept at library defaults: ExtraTrees grows fully "
        "randomized trees on the full sample (bootstrap=False); "
        "RandomForest baggs samples and searches for the best split "
        "(bootstrap=True)")
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
            add("_state_pooled (diagnostic):_ "
                + "; ".join(
                    f"{m}=" + "/".join(
                        _fmt(per_model[m]["per_fold"][f]["metrics"]
                             .get(metric, {}).get("state_pooled", {})
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
    _render_reference(add, title="8. Comparison vs M3 Logistic Regression "
                      "(stored M3 artifacts)", node=vs_lr, folds=folds,
                      models=models)
    for index, (ref_family, comparison) in enumerate(vs_m4.items(), start=1):
        _render_reference(
            add, title=f"9.{index} Comparison vs M4 {ref_family} "
            "(stored M4 artifacts)",
            node=comparison, folds=folds, models=models)
    add("## 10. Comparison vs M2 baseline floor (stored M2 artifacts)")
    add("")
    for metric, metric_node in vs_floor.items():
        add(f"### {metric} ({metric_node['direction']} is better; "
            f"baseline: {metric_node['baseline']})")
        add("")
        add("| fold | model | model | baseline | diff | verdict |")
        add("| --- | --- | --- | --- | --- | --- |")
        for fold in folds:
            for model in models:
                row = metric_node["per_fold"][fold][model]
                add(f"| {fold} | {model} | {_fmt(row['model_value'])} | "
                    f"{_fmt(row['baseline_value'])} | "
                    f"{_fmt(row['difference'])} | {row['verdict']} |")
        for model in models:
            row = metric_node["aggregate"][model]
            add(f"| mean | {model} | {_fmt(row['model_mean'])} | "
                f"{_fmt(row['baseline_mean'])} | "
                f"{_fmt(row['mean_difference'])} | {row['mean_verdict']} |")
        add("")
    add("## 11. Bagged-vs-linear / bagged-vs-boosted family finding")
    add("")
    finding = summary["family_finding"]
    total = finding["comparisons_per_metric"]
    lr_counts = finding["logreg_beats_counts"]
    add(f"- model-fold comparisons per metric: {total}")
    add("- comparisons that BEAT the M3 Logistic Regression reference "
        "(higher is better for ROC-AUC/PR-AUC/top-1; lower is better for "
        "log-loss/Brier/ECE):")
    for metric in vs_lr:
        add(f"  - {metric}: {lr_counts[metric]}/{total}")
    add(f"- changes the M4 conclusion (bagged beats the linear reference on "
        f"BOTH primary probability metrics in EVERY comparison): "
        f"**{finding['changes_m4_conclusion']}**")
    add("- no combined score is constructed; no significance is claimed.")
    add("")
    add("## 12. Determinism, runtime, latency, memory")
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
    add("## 13. Artifacts")
    add("")
    for model in models:
        for entry in per_model[model]["experiments"]:
            add(f"- {entry['model']}/{entry['fold']}: "
                f"`{entry['experiment_id']}`")
    add("")
    add(f"Suite summary: `{summary.get('_summary_path', BAGGED_SUITE_FILENAME)}` "
        "(machine-readable; this document was rendered from it).")
    add(f"M3 LOGREG suite: schema {summary.get('logreg_suite_schema')} "
        "(values in §8 loaded from stored M3 artifacts).")
    add(f"M4 nonlinear suite: schema {summary.get('nonlinear_suite_schema')} "
        "(values in §9 loaded from stored M4 artifacts).")
    add(f"M2 baseline suite: schema {summary.get('baseline_suite_schema')} "
        "(values in §10 loaded from stored M2 artifacts).")
    add("")
    add("## 14. Limitations and M6 implications")
    add("")
    add("- Three development folds is a coarse robustness signal; fold "
        "dispersion is reported, not hidden.")
    add("- State rows are not independent observations; headline conclusions "
        "use race-macro aggregation.")
    add("- No tuning was performed: these are representative fixed "
        "specifications, not optimized models. M6 may tune inside training "
        "history only.")
    add("- Raw probabilities only; calibration decisions belong to M7.")
    add("- 2025 was not evaluated and must remain protected until the final "
        "locked holdout (M17).")
    add("- No additional gradient-boosting library was available in this "
        "environment and none was added; M5 is scoped to ExtraTrees + "
        "RandomForest only.")
    rec = summary.get("m6_recommendation")
    add(f"- M6 recommendation: {rec if rec else 'PENDING'}")
    add("")
    return "\n".join(lines) + "\n"
