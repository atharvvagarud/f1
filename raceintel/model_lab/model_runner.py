"""M3 model execution runner (Logistic Regression reference only).

Reuses the exact M2 canonical evaluation path: ``ExperimentConfig`` ->
``materialize`` -> LogReg adapter -> ``PredictionResult`` -> identity
alignment -> M1.1 semantic metric applicability -> metric evaluation ->
race/stage/calibration aggregation -> ``ExperimentResult`` ->
``write_experiment``. No metric, aggregation, calibration, top-k,
serialization or identity logic is reimplemented here; every step delegates
to the approved M1/M1.1/M2 APIs.

Only development folds (D1/D2/D3) are accepted; the 2025 holdout, FINAL_FIT
and any other model family fail loudly. Only ``y_train`` reaches the
adapter; validation targets are used for evaluation only.
"""

from __future__ import annotations

import numpy as np

from raceintel.model_lab import data as DATA
from raceintel.model_lab import experiment as EX
from raceintel.model_lab import logreg as LR
from raceintel.model_lab import results as RES
from raceintel.model_lab import runner as RUN
from raceintel.model_lab import splits as SPLITS
from raceintel.model_lab import stages as STAGES
from raceintel.model_lab import tasks as TASKS
from raceintel.model_lab import timing as TIMING
from raceintel.model_lab.errors import ExperimentConfigError, InvalidPredictionError
from raceintel.model_lab.predictions import PredictionKind
from raceintel.model_lab.protocol import EXPECTED_MATRIX_CONTENT_HASH

#: The only candidate model M3 exposes.
MODEL_ALIASES = (LR.LOGREG_ALIAS, LR.LOGREG_FAMILY)

#: M3 scope: exactly this task / feature set / seed.
M3_TASK = LR.LOGREG_TASK
M3_FEATURE_SET = LR.LOGREG_FEATURE_SET
M3_SEED = LR.LOGREG_SEED

#: Batch latency repeats (real measured samples, never derived).
BATCH_LATENCY_REPEATS = 5
#: Single-state latency sample size (real per-row measurements).
SINGLE_STATE_SAMPLE = 200


def resolve_model(model: str) -> str:
    """Accept only the M3 reference model; reject every other family."""
    if model in MODEL_ALIASES:
        return LR.LOGREG_FAMILY
    raise ExperimentConfigError(
        f"M3 trains {list(MODEL_ALIASES)} only; got {model!r}")


def _peak_rss_bytes():
    try:
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (ImportError, OSError, AttributeError):
        return None


def run_model_experiment(*, task: str, model: str, fold: str,
                         feature_set: str = M3_FEATURE_SET,
                         seed: int = EX.PROJECT_SEED,
                         paths=None, root=None,
                         return_predictions: bool = False,
                         topk_kwargs: dict | None = None) -> dict:
    """Execute one LogReg experiment on a development fold.

    Returns {"config", "result", "dest", "timings"[, "predictions"]}.
    """
    family = resolve_model(model)
    if task != M3_TASK:
        raise ExperimentConfigError(
            f"M3 evaluates task {M3_TASK!r} only; got {task!r}")
    if feature_set != M3_FEATURE_SET:
        raise ExperimentConfigError(
            f"M3 uses feature set {M3_FEATURE_SET!r} only; got {feature_set!r}")
    if seed != M3_SEED:
        raise ExperimentConfigError(
            f"M3 uses seed {M3_SEED!r} only; got {seed!r}")

    timings: dict = {}
    warnings: list = []

    with TIMING.Timer() as total:
        split = RUN.resolve_development_fold(fold)

        with TIMING.Timer() as t:
            canonical = DATA.load_canonical(paths)
        timings["matrix_load_seconds"] = t.seconds
        if canonical.manifest.get("content_hash") != \
                EXPECTED_MATRIX_CONTENT_HASH:
            from raceintel.model_lab.errors import ProtocolDriftError
            raise ProtocolDriftError("matrix content hash drift at run time")

        with TIMING.Timer() as t:
            dataset = SPLITS.materialize(canonical, task, fold, feature_set)
        timings["materialize_seconds"] = t.seconds
        RUN._check_no_holdout_rows(dataset.validation_metadata, fold)

        with TIMING.Timer() as t:
            config = EX.build_config(
                task, feature_set, fold,
                model_family=family, seed=seed,
                model_parameters=LR.logreg_model_parameters(),
                preprocessing_config=LR.PRE.preprocessing_contract_dict(),
                calibration_config={"method": "none"},
                training_rows=int(dataset.train_counts["eligible"]),
                training_races=int(
                    dataset.train_metadata["race_id"].nunique()),
                validation_rows=int(dataset.validation_counts["eligible"]),
                validation_races=int(
                    dataset.validation_metadata["race_id"].nunique()))
        timings["config_seconds"] = t.seconds

        resolved = TASKS.resolve_task(task)
        if dataset.X_train.shape[0] == 0:
            raise ExperimentConfigError(f"{fold}: training side is empty")

        adapter = LR.LogisticRegressionAdapter()
        with TIMING.Timer() as t:
            # TRAIN ONLY: y_validation is never passed to the fit path.
            adapter.fit(dataset.X_train, dataset.y_train)
        timings["fit_seconds"] = t.seconds
        timings["preprocessing_fit_seconds"] = adapter.timing.get(
            "preprocessing_fit_seconds")
        timings["estimator_fit_seconds"] = adapter.timing.get(
            "estimator_fit_seconds")
        for message in adapter.convergence_warnings:
            warnings.append(f"convergence: {message}")
        sanity = adapter.coefficient_sanity()
        if sanity["all_zero"] or sanity["any_nan"] \
                or not sanity["intercept_finite"]:
            raise InvalidPredictionError(
                f"{fold}: coefficient sanity failed: {sanity}")

        validation_frame = canonical.frame.loc[
            dataset.y_validation.index].copy()
        if list(validation_frame.index) != list(dataset.y_validation.index):
            raise ExperimentConfigError(
                "validation frame rows do not match the materialized "
                "validation target index")

        with TIMING.Timer() as t:
            validation_prediction = adapter.predict_result(
                dataset.X_validation,
                list(validation_frame["state_id"]))
        timings["transform_predict_seconds"] = t.seconds
        if validation_prediction.kind is not \
                PredictionKind.BINARY_PROBABILITY:
            raise InvalidPredictionError("LogReg must emit BINARY_PROBABILITY")

        with TIMING.Timer() as t:
            y_aligned_target = dataset.y_validation
            aligned = RUN._align_validation(validation_prediction,
                                            validation_frame)
        timings["align_seconds"] = t.seconds

        y_true = np.asarray(
            y_aligned_target.astype(float).to_numpy(), dtype=float)
        race_ids = np.asarray(
            dataset.validation_metadata["race_id"].astype(str))
        finite = RUN._finite_mask(aligned)
        n_missing = int((~finite).sum())
        if n_missing:
            raise InvalidPredictionError(
                f"{fold}: {n_missing} non-finite LogReg probability predictions")

        with TIMING.Timer() as t:
            metric_names = tuple(resolved.metrics)
            metric_payloads, w = RUN.evaluate_row_metrics(
                validation_prediction, metric_names, y_true, aligned,
                race_ids)
            warnings.extend(w)
        timings["metric_seconds"] = t.seconds

        ok_metrics = tuple(
            name for name, payload in metric_payloads.items()
            if payload.get("status") == "OK")

        with TIMING.Timer() as t:
            stage_labels = STAGES.stage_partition(
                validation_frame["race_progress_frac"])
            stage_payloads, w = RUN.evaluate_stages(
                validation_prediction, ok_metrics,
                np.asarray(stage_labels), y_true, aligned, race_ids)
            warnings.extend(w)
        timings["stage_seconds"] = t.seconds

        with TIMING.Timer() as t:
            calibration_payload, w = RUN.evaluate_calibration(
                validation_prediction, y_true, aligned)
            warnings.extend(w)
        timings["calibration_seconds"] = t.seconds

        with TIMING.Timer() as t:
            if task == "winner":
                race_payload, w = RUN.evaluate_winner_top_k(
                    validation_prediction, canonical,
                    tuple(sorted(set(
                        dataset.validation_metadata["race_id"].astype(
                            str)))),
                    **(topk_kwargs or {}))
                warnings.extend(w)
                race_metrics = {"winner_top_k": race_payload}
            else:  # pragma: no cover - M3 evaluates winner only
                race_metrics = {"winner_top_k": RUN._not_applicable(
                    "synchronized winner top-k applies to the winner task "
                    "only")}
        timings["topk_seconds"] = t.seconds

        prevalence = float(np.mean(np.asarray(
            dataset.y_train.astype(float))))

        # --- honest inference latency (real measured samples only) ---
        with TIMING.Timer() as t:
            _, batch_samples = TIMING.timed_call(
                adapter.predict_positive_probability,
                dataset.X_validation,
                repeats=BATCH_LATENCY_REPEATS, warmup=1)
            batch_summary = TIMING.latency_summary(batch_samples)
            n_states = int(dataset.X_validation.shape[0])
            batch_summary["states_per_batch"] = n_states
            batch_summary["states_per_second"] = (
                n_states / batch_summary["mean"]
                if batch_summary["mean"] else None)
            single_frame = dataset.X_validation.iloc[: min(
                SINGLE_STATE_SAMPLE, n_states)]

            def _single(row_index: int):
                return adapter.predict_positive_probability(
                    single_frame.iloc[[row_index]])
            single_samples = []
            for row_index in range(len(single_frame)):
                _, samples = TIMING.timed_call(_single, row_index,
                                               repeats=1, warmup=0)
                single_samples.extend(samples)
            single_summary = TIMING.latency_summary(single_samples)
        timings["latency_probe_seconds"] = t.seconds
        latency = {"batch": batch_summary, "single_state": single_summary,
                   "method": "batch: 1 warm-up + "
                   f"{BATCH_LATENCY_REPEATS} timed full-validation predicts; "
                   "single-state: one timed predict per state over "
                   f"{len(single_frame)} states (no derived percentiles)"}

        result = EX.ExperimentResult(
            experiment_id=config.experiment_id,
            status=EX.ExperimentStatus.OK,
            fit_seconds=(timings["fit_seconds"]),
            prediction_seconds=(timings["transform_predict_seconds"]
                                + timings["metric_seconds"]
                                + timings["stage_seconds"]
                                + timings["calibration_seconds"]
                                + timings["topk_seconds"]),
            latency=latency,
            metrics={"train_prevalence": (
                {"status": "INFO", "value": prevalence}),
                **metric_payloads},
            calibration=(calibration_payload
                         if calibration_payload.get("status") == "OK"
                         else None),
            stage_metrics=stage_payloads,
            race_metrics=race_metrics,
            artifact_refs={
                "model_family": family,
                "model_parameters": LR.logreg_model_parameters(),
                "preprocessing": LR.PRE.preprocessing_contract_dict(),
                "sklearn_version": LR.SKLEARN_VERSION,
                "feature_names_hash": __import__("hashlib").sha256(
                    "\n".join(dataset.feature_names).encode()
                ).hexdigest(),
                "n_features_in": int(len(dataset.feature_names)),
                "transformed_dim": int(sanity["transformed_dim"]),
                "coefficient_sanity": sanity,
                "convergence_warnings": list(adapter.convergence_warnings),
                "peak_rss_bytes": _peak_rss_bytes(),
            },
            warnings=warnings,
            environment=RES.environment_metadata(
                paths.root if paths is not None else None),
        )
        with TIMING.Timer() as t:
            dest = RES.write_experiment(config, result, paths=paths,
                                        root=root)
        timings["serialize_seconds"] = t.seconds

    timings["total_seconds"] = total.seconds
    out = {"config": config, "result": result, "dest": str(dest),
           "timings": timings}
    if return_predictions:
        out["predictions"] = np.asarray(aligned, dtype=float)
    return out
