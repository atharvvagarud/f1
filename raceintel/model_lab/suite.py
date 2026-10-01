"""M2 baseline suite: development execution, disk-derived summary, report.

Chain of custody: experiment results (``write_experiment``) -> suite
summary (read back from ``result.json`` on disk, never from drum memory
of the run) -> human-readable markdown (rendered from the summary file
only). No number in the report bypasses a stored artifact.
"""

from __future__ import annotations

import json
from pathlib import Path

from raceintel.config import V2Paths
from raceintel.model_lab import aggregation as AGG
from raceintel.model_lab import baselines as BASE
from raceintel.model_lab import data as DATA
from raceintel.model_lab import experiment as EX
from raceintel.model_lab import results as RES
from raceintel.model_lab import runner as RUN
from raceintel.model_lab import splits as SPLITS
from raceintel.model_lab import timing as TIMING
from raceintel.model_lab import winner as WINNER
from raceintel.model_lab.errors import (
    ExperimentConfigError,
    ProtectedHoldoutError,
    UnknownFoldError,
)
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
SUITE_FILENAME = "baseline_suite_v1.json"
REPORTS_REL = "data/v2/model_lab/reports"


def reports_dir(paths=None, root=None) -> Path:
    base = Path(root) if root is not None else (
        paths.root if paths is not None else V2Paths.resolve().root)
    return base / REPORTS_REL


def baselines_for_task(task: str) -> list:
    """Frozen baseline names supporting ``task`` (registry order)."""
    return [b.name for b in BASE.BASELINES if task in b.supported_tasks]


def parse_folds(raw: str) -> tuple:
    folds = tuple(s.strip() for s in str(raw).split(",") if s.strip())
    if not folds:
        raise ExperimentConfigError("no folds selected")
    for fold in folds:
        if fold in (SPLITS.HOLDOUT_ID, "2025"):
            raise ProtectedHoldoutError(
                f"suite cannot select {fold!r}: 2025 holdout is protected")
        if fold not in RUN.DEVELOPMENT_ONLY_FOLDS:
            raise UnknownFoldError(
                f"suite accepts D1/D2/D3 only; got {fold!r}")
    if len(set(folds)) != len(folds):
        raise ExperimentConfigError(f"duplicate folds selected: {folds!r}")
    return folds


def parse_baselines(raw: str | None, task: str) -> tuple:
    valid = baselines_for_task(task)
    if raw is None:
        return tuple(valid)
    names = tuple(s.strip() for s in str(raw).split(",") if s.strip())
    for name in names:
        if name not in valid:
            raise ExperimentConfigError(
                f"baseline {name!r} is not valid for task {task!r}; "
                f"valid: {valid}")
    if len(set(names)) != len(names):
        raise ExperimentConfigError(f"duplicate baselines: {names!r}")
    return names


def benchmark_topk_subset(*, task: str = "winner",
                          baseline: str = "CURRENT_LEADER",
                          fold: str = "D1", n_races: int = 2,
                          paths=None) -> dict:
    """Time synchronized top-k on a small development subset first.

    Real measurement on the first ``n_races`` validation races; semantics
    untouched (same evaluator, same eligibility). Informs whether the full
    run is affordable before committing to it.
    """
    canonical = DATA.load_canonical(paths)
    dataset = SPLITS.materialize(canonical, task, fold, "ALL_84")
    races = sorted(set(
        dataset.validation_metadata["race_id"].astype(str)))[:n_races]
    idx = dataset.validation_metadata[
        dataset.validation_metadata["race_id"].astype(str).isin(
            set(races))].index
    frame = canonical.frame.loc[dataset.y_validation.index].copy()
    _, prediction = BASE.run_baseline(
        baseline, task,
        canonical.frame.loc[dataset.y_train.index].copy(), frame,
        train_y=None)
    with TIMING.Timer() as t:
        out = WINNER.synchronized_winner_top_k(
            prediction, canonical, race_ids=races)
    return {"baseline": baseline, "fold": fold, "n_races": len(races),
            "race_ids": races, "seconds": t.seconds,
            "n_evaluation_states": out["n_evaluation_states"]}


def _peak_rss_bytes():
    try:
        import resource
        rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
        return int(rss)  # bytes on macOS/Linux
    except (ImportError, OSError, AttributeError):
        return None


def _read_result(dest: str) -> tuple:
    return RES.read_experiment(dest)


def _json_safe_number(value):
    import math
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _json_safe_number(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe_number(v) for v in value]
    return value


def build_summary(*, task: str, folds: tuple, baselines: tuple,
                  feature_set: str, seed: int,
                  experiments: list, timings: dict,
                  determinism: dict, topk_benchmark: dict,
                  secondary_smoke: dict | None,
                  git_commit: str | None) -> dict:
    """Derive the suite summary by re-reading stored result documents."""
    from raceintel.model_lab.protocol import (
        EXPECTED_MANIFEST_SHA256,
        EXPECTED_MATRIX_PARQUET_SHA256,
    )
    per_fold: dict = {}
    for entry in experiments:
        config, result = _read_result(entry["dest"])
        fold = config.fold
        per_fold.setdefault(fold, {})[entry["baseline"]] = {
            "experiment_id": config.experiment_id,
            "dest": entry["dest"],
            "status": result.status.value,
            "train_prevalence": result.metrics.get(
                "train_prevalence", {}).get("value"),
            "training_rows": config.training_rows,
            "training_races": config.training_races,
            "validation_rows": config.validation_rows,
            "validation_races": config.validation_races,
            "metrics": {k: v for k, v in result.metrics.items()
                        if k != "train_prevalence"},
            "calibration_ece": (
                result.calibration["expected_calibration_error"]
                if result.calibration else None),
            "stage_metrics": result.stage_metrics,
            "race_metrics": result.race_metrics,
            "warnings": result.warnings,
        }

    aggregates: dict = {}
    for baseline in baselines:
        aggregates[baseline] = {}
        for metric in ("log_loss", "brier", "roc_auc", "pr_auc"):
            per_fold_values = {}
            for fold in folds:
                payload = per_fold[fold][baseline]["metrics"].get(metric, {})
                per_fold_values[fold] = (
                    payload.get("race_macro", {}).get("value")
                    if payload.get("status") == "OK" else None)
            aggregates[baseline][metric] = _json_safe_number(
                AGG.aggregate_folds(per_fold_values))
        topk_values = {}
        for fold in folds:
            payload = per_fold[fold][baseline]["race_metrics"].get(
                "winner_top_k", {})
            for key in ("top1", "top3"):
                acc = (payload.get("accuracy") or {}).get(key) \
                    if payload.get("status") == "OK" else None
                topk_values.setdefault(key, {})[fold] = acc
        aggregates[baseline]["winner_top_k"] = {
            key: _json_safe_number(AGG.aggregate_folds(vals))
            for key, vals in topk_values.items()}

    applicability: dict = {}
    for baseline in baselines:
        applicability[baseline] = {}
        for metric in ("log_loss", "brier", "roc_auc", "pr_auc"):
            seen = {per_fold[fold][baseline]["metrics"].get(metric, {}).get(
                "status") for fold in folds}
            if seen == {"OK"}:
                applicability[baseline][metric] = "OK"
            elif seen == {"NOT_APPLICABLE"}:
                applicability[baseline][metric] = "NOT_APPLICABLE"
            else:
                applicability[baseline][metric] = (
                    f"MIXED: {sorted(seen, key=str)}")
        ece_seen = {per_fold[fold][baseline]["calibration_ece"] is not None
                    for fold in folds}
        applicability[baseline]["expected_calibration_error"] = (
            "OK" if ece_seen == {True} else (
                "NOT_APPLICABLE" if ece_seen == {False}
                else "MIXED: calibration present in some folds"))
        topk_seen = {per_fold[fold][baseline]["race_metrics"].get(
            "winner_top_k", {}).get("status") for fold in folds}
        applicability[baseline]["winner_top_k"] = (
            next(iter(topk_seen)) if len(topk_seen) == 1
            else f"MIXED: {sorted(topk_seen)}")

    summary = {
        "schema_version": SUITE_SCHEMA_VERSION,
        "task": task,
        "folds": list(folds),
        "baselines": list(baselines),
        "feature_set": feature_set,
        "seed": seed,
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
        "baseline_semantics": {
            b.name: {"supported_tasks": list(b.supported_tasks),
                     "required_columns": list(b.required_columns),
                     "train_dependence": b.train_dependence,
                     "output": b.output,
                     "description": b.description}
            for b in BASE.BASELINES if b.name in set(baselines)},
        "experiments": [
            {"baseline": e["baseline"], "fold": e["fold"],
             "experiment_id": e["experiment_id"], "dest": e["dest"]}
            for e in experiments],
        "per_fold": per_fold,
        "aggregates": aggregates,
        "applicability": applicability,
        "topk_benchmark_subset": topk_benchmark,
        "determinism_check": determinism,
        "secondary_smoke": secondary_smoke,
        "runtime": timings,
        "peak_rss_bytes": _peak_rss_bytes(),
        "warnings": [w for fold in folds for baseline in baselines
                     for w in per_fold[fold][baseline]["warnings"]],
    }
    return summary


def run_suite(*, task: str = "winner", folds=("D1", "D2", "D3"),
              baselines=None, feature_set: str = "ALL_84",
              seed: int = EX.PROJECT_SEED, paths=None, root=None,
              out=None, secondary_smoke: bool = False) -> dict:
    """Execute the development baseline suite; return the disk summary."""
    folds = tuple(folds)
    for fold in folds:
        RUN.resolve_development_fold(fold)
    baselines = tuple(baselines) if baselines is not None \
        else tuple(baselines_for_task(task))
    for name in baselines:
        if name not in baselines_for_task(task):
            raise ExperimentConfigError(
                f"baseline {name!r} invalid for task {task!r}")

    timings: dict = {}
    with TIMING.Timer() as total:
        with TIMING.Timer() as t:
            topk_benchmark = benchmark_topk_subset(paths=paths)
        timings["topk_benchmark_seconds"] = t.seconds

        experiments: list = []
        phase_seconds: dict = {}
        for fold in folds:
            for name in baselines:
                out_exp = RUN.run_experiment(
                    task=task, baseline=name, fold=fold,
                    feature_set=feature_set, seed=seed, paths=paths,
                    root=root)
                experiments.append({
                    "baseline": name, "fold": fold,
                    "experiment_id": out_exp["config"].experiment_id,
                    "dest": out_exp["dest"]})
                for phase, seconds in out_exp["timings"].items():
                    key = f"{phase}"
                    phase_seconds[key] = phase_seconds.get(key, 0.0) \
                        + seconds
        timings["experiment_phases_total_seconds"] = phase_seconds

        with TIMING.Timer() as t:
            rerun = RUN.run_experiment(
                task=task, baseline="CLASS_PRIOR", fold=folds[0],
                feature_set=feature_set, seed=seed, paths=paths,
                root=root)
            first_dest = next(
                e["dest"] for e in experiments
                if e["baseline"] == "CLASS_PRIOR" and e["fold"] == folds[0])
            with open(f"{first_dest}/result.json", encoding="utf-8") as fh:
                first_bytes = fh.read()
            with open(f"{rerun['dest']}/result.json",
                       encoding="utf-8") as fh:
                second_bytes = fh.read()
            determinism = {
                "baseline": "CLASS_PRIOR", "fold": folds[0],
                "experiment_id": rerun["config"].experiment_id,
                "rerun_bytes_identical": first_bytes == second_bytes,
            }
        timings["determinism_check_seconds"] = t.seconds

        smoke = None
        if secondary_smoke:
            with TIMING.Timer() as t:
                smoke_out = RUN.run_experiment(
                    task="final_position", baseline="GRID_POLE",
                    fold="D1", feature_set=feature_set, seed=seed,
                    paths=paths, root=root)
            timings["secondary_smoke_seconds"] = t.seconds
            _, smoke_result = _read_result(smoke_out["dest"])
            mae_payload = smoke_result.metrics.get("mae", {})
            smoke = {
                "task": "final_position", "baseline": "GRID_POLE",
                "fold": "D1",
                "experiment_id": smoke_out["config"].experiment_id,
                "dest": smoke_out["dest"],
                "mae_race_macro": (mae_payload.get("race_macro", {})
                                   .get("value")),
                "note": "infrastructure smoke only; not a leaderboard",
            }

    timings["total_seconds"] = total.seconds

    with TIMING.Timer() as t:
        from raceintel.model_lab.results import environment_metadata
        env = environment_metadata(
            paths.root if paths is not None else None)
    summary = build_summary(
        task=task, folds=folds, baselines=baselines,
        feature_set=feature_set, seed=seed, experiments=experiments,
        timings={**timings, "environment_probe_seconds": t.seconds},
        determinism=determinism, topk_benchmark=topk_benchmark,
        secondary_smoke=smoke, git_commit=env.get("git_commit"))

    dest = Path(out) if out is not None else reports_dir(
        paths, root) / SUITE_FILENAME
    dest.parent.mkdir(parents=True, exist_ok=True)
    RES.atomic_write_json(dest, summary)
    summary["_summary_path"] = str(dest)
    return summary


def _fmt(value, digits: int = 6):
    if value is None:
        return "N/A"
    if isinstance(value, float):
        return f"{value:.{digits}f}"
    return str(value)


def render_report(summary: dict) -> str:
    """Render the human-readable baseline report from the summary only."""
    task = summary["task"]
    folds = summary["folds"]
    baselines = summary["baselines"]
    per_fold = summary["per_fold"]
    agg = summary["aggregates"]
    lines = []
    add = lines.append
    add("# Model Lab Baseline Report — non-ML development benchmarks")
    add("")
    add("**DEVELOPMENT RESULTS — 2022 / 2023 / 2024**")
    add("")
    add("**2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED**")
    add("")
    add("All numbers below are development-fold results produced by the "
        "frozen non-ML baselines. They are the empirical floor later ML "
        "models must beat — not final test performance. No candidate ML "
        "model has been run. Every value traces to a stored experiment "
        f"result (task `{task}`, protocol "
        f"{summary['protocol_version']}, matrix "
        f"{summary['matrix_content_hash'][:12]}…).")
    add("")
    add("## 1. Headline probability quality (race-macro)")
    add("")
    for metric in ("log_loss", "brier"):
        add(f"### {metric} (race-macro; lower is better)")
        add("")
        add("| baseline | " + " | ".join(folds) + " | mean |")
        add("| --- | " + " | ".join(["---"] * len(folds)) + " | --- |")
        for name in baselines:
            cells = []
            for fold in folds:
                payload = per_fold[fold][name]["metrics"].get(metric, {})
                cells.append(_fmt(payload.get("race_macro", {}).get(
                    "value")) if payload.get("status") == "OK" else "N/A")
            cells.append(_fmt(agg[name][metric]["mean"]))
            add(f"| {name} | " + " | ".join(cells) + " |")
        add("")
    add("## 2. State-pooled diagnostics (not headline)")
    add("")
    for metric in ("log_loss", "brier"):
        add(f"### {metric} (state-pooled)")
        add("")
        add("| baseline | " + " | ".join(folds) + " | mean |")
        add("| --- | " + " | ".join(["---"] * len(folds)) + " | --- |")
        for name in baselines:
            cells = []
            for fold in folds:
                payload = per_fold[fold][name]["metrics"].get(metric, {})
                pool = payload.get("state_pooled", {}) \
                    if payload.get("status") == "OK" else {}
                cells.append(_fmt(pool.get("value")))
            pooled_means = [
                per_fold[fold][name]["metrics"].get(metric, {}).get(
                    "state_pooled", {}).get("value")
                if per_fold[fold][name]["metrics"].get(
                    metric, {}).get("status") == "OK" else None
                for fold in folds]
            defined = [v for v in pooled_means if v is not None]
            cells.append(_fmt(sum(defined) / len(defined)) if defined
                         else "N/A")
            add(f"| {name} | " + " | ".join(cells) + " |")
        add("")
    add("## 3. Discrimination (race-macro ROC-AUC / PR-AUC)")
    add("")
    for metric in ("roc_auc", "pr_auc"):
        add(f"### {metric} (race-macro; higher is better)")
        add("")
        add("| baseline | " + " | ".join(folds) + " | mean |")
        add("| --- | " + " | ".join(["---"] * len(folds)) + " | --- |")
        for name in baselines:
            cells = []
            for fold in folds:
                payload = per_fold[fold][name]["metrics"].get(metric, {})
                cells.append(_fmt(payload.get("race_macro", {}).get(
                    "value")) if payload.get("status") == "OK" else "N/A")
            cells.append(_fmt(agg[name][metric]["mean"]))
            add(f"| {name} | " + " | ".join(cells) + " |")
        add("")
    add("## 4. Calibration (ECE, 10 equal-width bins)")
    add("")
    add("| baseline | " + " | ".join(folds) + " |")
    add("| --- | " + " | ".join(["---"] * len(folds)) + " |")
    for name in baselines:
        cells = []
        for fold in folds:
            cells.append(_fmt(per_fold[fold][name]["calibration_ece"]))
        add(f"| {name} | " + " | ".join(cells) + " |")
    add("")
    add("Reliability-bin detail (counts, mean predicted, observed "
        "frequency, weight) is stored per experiment result; no calibrator "
        "was fitted.")
    add("")
    add("## 5. Race-stage performance (race-macro)")
    add("")
    for metric in ("log_loss", "brier"):
        add(f"### {metric} by stage")
        add("")
        for fold in folds:
            add(f"#### {fold}")
            add("")
            add("| baseline | EARLY | MID | LATE |")
            add("| --- | --- | --- | --- |")
            for name in baselines:
                stage_payload = per_fold[fold][name][
                    "stage_metrics"].get(metric, {})
                if stage_payload.get("status") != "OK":
                    add(f"| {name} | N/A | N/A | N/A |")
                    continue
                cells = [_fmt(stage_payload.get(stage, {}).get(
                    "race_macro", {}).get("value"))
                    for stage in ("EARLY", "MID", "LATE")]
                add(f"| {name} | " + " | ".join(cells) + " |")
            add("")
    add("## 6. Synchronized winner top-k (development races)")
    add("")
    add("| baseline | fold | top-1 | top-3 | eval states | skipped "
        "(none/winner-unobs/degen) | min field | top-3 coverage |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- |")
    for fold in folds:
        for name in baselines:
            payload = per_fold[fold][name]["race_metrics"].get(
                "winner_top_k", {})
            if payload.get("status") != "OK":
                add(f"| {name} | {fold} | N/A | N/A | N/A | N/A | N/A | "
                    f"{payload.get('reason', 'NOT_APPLICABLE')} |")
                continue
            acc = payload.get("accuracy", {})
            skipped = (f"{payload.get('n_skipped_no_predictions')}/"
                       f"{payload.get('n_skipped_winner_unobservable')}/"
                       f"{payload.get('n_skipped_degenerate')}")
            min_field = payload.get("min_observable_field_size")
            coverage = ("INSUFFICIENT for 3-way discrimination "
                        "(field < 3)" if isinstance(min_field, int)
                        and min_field < 3 else "sufficient")
            add(f"| {name} | {fold} | {_fmt(acc.get('top1'))} | "
                f"{_fmt(acc.get('top3'))} | "
                f"{payload.get('n_evaluation_states')} | {skipped} | "
                f"{min_field} | {coverage} |")
    add("")
    add("Top-3 values on fields smaller than 3 are reported for "
        "completeness but are NOT genuine three-way discrimination "
        "(see coverage column and M1.1 eligibility contract).")
    add("")
    add("## 7. Baseline semantics + metric applicability")
    add("")
    for name in baselines:
        sem = summary["baseline_semantics"][name]
        kind = ("BINARY_PROBABILITY" if name != "RECENT_PACE"
                else "RANKING_SCORE")
        add(f"- {name}: kind={kind}; "
            f"train_dependence={sem['train_dependence']}; "
            f"required_columns={sem['required_columns']}; "
            f"output={sem['output']}")
        reasons = []
        for metric in ("log_loss", "brier", "roc_auc", "pr_auc",
                       "expected_calibration_error"):
            status = summary["applicability"][name].get(metric)
            if status != "OK":
                reasons.append(f"{metric}: {status}")
        topk_status = summary["applicability"][name].get("winner_top_k")
        if topk_status != "OK":
            reasons.append(f"winner_top_k: {topk_status}")
        if reasons:
            add(f"  NOT_APPLICABLE: " + "; ".join(reasons))
    add("")
    add("## 8. Baseline comparison (development means, factual)")
    add("")
    prob = [n for n in baselines
            if summary["applicability"][n].get("log_loss") == "OK"]
    if prob:
        by_ll = sorted(prob, key=lambda n: agg[n]["log_loss"]["mean"])
        by_br = sorted(prob, key=lambda n: agg[n]["brier"]["mean"])
        add(f"- strongest probability baseline by mean race-macro log "
            f"loss: **{by_ll[0]}** ({_fmt(agg[by_ll[0]]['log_loss']['mean'])})")
        add(f"- strongest probability baseline by mean race-macro Brier: "
            f"**{by_br[0]}** ({_fmt(agg[by_br[0]]['brier']['mean'])})")
    rank = [n for n in baselines
            if summary["applicability"][n].get("roc_auc") == "OK"]
    if rank:
        by_roc = sorted(rank, key=lambda n: agg[n]["roc_auc"]["mean"],
                        reverse=True)
        add(f"- strongest ranking baseline by mean race-macro ROC-AUC: "
            f"**{by_roc[0]}** ({_fmt(agg[by_roc[0]]['roc_auc']['mean'])})")
    topk_ok = [n for n in baselines
               if summary["applicability"][n].get("winner_top_k") == "OK"]
    if topk_ok:
        by_top1 = sorted(
            topk_ok,
            key=lambda n: agg[n]["winner_top_k"]["top1"]["mean"] or -1,
            reverse=True)
        add(f"- strongest synchronized winner ranking by mean top-1: "
            f"**{by_top1[0]}** "
            f"({_fmt(agg[by_top1[0]]['winner_top_k']['top1']['mean'])})")
    add("- no combined score is constructed; no significance is claimed.")
    add("")
    _render_floor(summary, add)
    add("## 10. Firewalls, determinism, runtime")
    add("")
    add(f"- holdout_accessed: {summary['holdout_accessed']} "
        f"({summary['holdout_note']})")
    det = summary["determinism_check"]
    add(f"- determinism rerun ({det['baseline']}/{det['fold']}, "
        f"{det['experiment_id'][:12]}…): rerun result bytes identical = "
        f"{det['rerun_bytes_identical']}")
    bench = summary["topk_benchmark_subset"]
    add(f"- synchronized top-k subset benchmark "
        f"({bench['baseline']}/{bench['fold']}, {bench['n_races']} races, "
        f"{bench['n_evaluation_states']} states): "
        f"{bench['seconds']:.2f} s")
    add(f"- full suite wall time: "
        f"{summary['runtime'].get('total_seconds', 0):.1f} s")
    rss = summary.get("peak_rss_bytes")
    add(f"- peak RSS: "
        f"{rss / 1e9:.2f} GB" if rss else "- peak RSS: NOT MEASURED")
    if summary.get("secondary_smoke"):
        smoke = summary["secondary_smoke"]
        add(f"- secondary smoke ({smoke['baseline']}/{smoke['task']}/"
            f"{smoke['fold']}): mae race-macro = "
            f"{_fmt(smoke['mae_race_macro'])} "
            f"({smoke['experiment_id'][:12]}…; {smoke['note']})")
    add("")
    add("## 11. Artifacts")
    add("")
    for entry in summary["experiments"]:
        add(f"- {entry['baseline']}/{entry['fold']}: "
            f"`{entry['experiment_id']}`")
    add("")
    add(f"Suite summary: `{summary.get('_summary_path', REPORTS_REL + '/' + SUITE_FILENAME)}` "
        "(machine-readable; this document was rendered from it).")
    add("")
    return "\n".join(lines) + "\n"


def _render_floor(summary: dict, add) -> None:
    agg = summary["aggregates"]
    add("## 9. Baseline floor for M3+ (development)")
    add("")
    for metric in ("log_loss", "brier"):
        cells = [f"{n}={_fmt(agg[n][metric]['mean'])}"
                 for n in summary["baselines"]
                 if summary["applicability"][n].get(metric) == "OK"]
        add(f"- probability quality {metric} (mean race-macro): "
            + "; ".join(cells))
    cells = [f"{n}={_fmt(agg[n]['roc_auc']['mean'])}"
             for n in summary["baselines"]
             if summary["applicability"][n].get("roc_auc") == "OK"]
    add("- discrimination ROC-AUC (mean race-macro): " + "; ".join(cells))
    cells = [f"{n}={_fmt(agg[n]['pr_auc']['mean'])}"
             for n in summary["baselines"]
             if summary["applicability"][n].get("pr_auc") == "OK"]
    add("- discrimination PR-AUC (mean race-macro): " + "; ".join(cells))
    cells = []
    for fold in summary["folds"]:
        per = {n: summary["per_fold"][fold][n]["calibration_ece"]
               for n in summary["baselines"]}
        cells.append(f"{fold}=" + ", ".join(
            f"{n}={_fmt(v)}" for n, v in per.items()))
    add("- calibration ECE per fold: " + "; ".join(cells))
    add("- synchronized winner top-1/top-3: see §6 (coverage-qualified).")
    add("- stage performance: see §5 (per-fold EARLY/MID/LATE).")
    add("")
