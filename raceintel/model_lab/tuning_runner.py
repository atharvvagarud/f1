"""M6 outer refit + canonical evaluation + tuning orchestration.

After the deterministic inner search selects a configuration for an outer
fold, this module:

1. fits a FRESH preprocessor on the COMPLETE outer TRAIN history;
2. fits a FRESH estimator with the selected parameters on that history;
3. predicts the outer VALIDATION season exactly ONCE;
4. evaluates through the exact canonical M2 evaluator path used by M3/M4/M5
   (``RUN.evaluate_row_metrics`` / ``evaluate_stages`` /
   ``evaluate_calibration`` / ``evaluate_winner_top_k`` -> ``ExperimentResult``
   -> ``RES.write_experiment``).

Rejected tuning configurations never touch the outer evaluator. Outer
validation labels are used only for evaluation, never for fitting, selection
or early stopping. The protected 2025 holdout has no code path here.
"""

from __future__ import annotations

import hashlib

import numpy as np

from raceintel.model_lab import data as DATA
from raceintel.model_lab import experiment as EX
from raceintel.model_lab import preprocessing as PRE
from raceintel.model_lab import results as RES
from raceintel.model_lab import runner as RUN
from raceintel.model_lab import splits as SPLITS
from raceintel.model_lab import stages as STAGES
from raceintel.model_lab import tasks as TASKS
from raceintel.model_lab import timing as TIMING
from raceintel.model_lab import tuning as TUNE
from raceintel.model_lab import tuning_candidates as TC
from raceintel.model_lab.errors import ExperimentConfigError, InvalidPredictionError
from raceintel.model_lab.predictions import PredictionKind
from raceintel.model_lab.protocol import EXPECTED_MATRIX_CONTENT_HASH

#: Batch latency repeats (real measured samples, never derived).
BATCH_LATENCY_REPEATS = 5
#: Single-state latency sample size (real per-row measurements).
SINGLE_STATE_SAMPLE = 200

#: Append-only log proving how many outer evaluations ran (firewall tests).
_OUTER_EVALUATION_LOG: list = []


def outer_evaluation_log() -> tuple:
    return tuple(_OUTER_EVALUATION_LOG)


def reset_outer_evaluation_log() -> None:
    _OUTER_EVALUATION_LOG.clear()


def _peak_rss_bytes():
    try:
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (ImportError, OSError, AttributeError):
        return None


def tuned_family_name(family: str) -> str:
    if family not in TC.TUNED_FAMILY_NAMES:
        raise ExperimentConfigError(f"unknown M6 family {family!r}")
    return TC.TUNED_FAMILY_NAMES[family]


def run_outer_selected(*, family: str, fold: str, selected_config: dict,
                       feature_set: str = TUNE.M6_FEATURE_SET,
                       seed: int = EX.PROJECT_SEED, paths=None, root=None,
                       canonical: DATA.CanonicalMatrix | None = None,
                       return_predictions: bool = False,
                       topk_kwargs: dict | None = None) -> dict:
    """Refit the selected configuration on outer TRAIN and evaluate once."""
    if family not in TUNE.SUPPORTED_FAMILIES:
        raise ExperimentConfigError(
            f"M6 evaluates {list(TUNE.SUPPORTED_FAMILIES)} only; got "
            f"{family!r}")
    if feature_set != TUNE.M6_FEATURE_SET:
        raise ExperimentConfigError(
            f"M6 uses feature set {TUNE.M6_FEATURE_SET!r} only; got "
            f"{feature_set!r}")
    if seed != TUNE.M6_SEED:
        raise ExperimentConfigError(
            f"M6 uses seed {TUNE.M6_SEED!r} only; got {seed!r}")
    family_name = tuned_family_name(family)
    model_parameters = TC.resolved_model_parameters(family, selected_config)

    timings: dict = {}
    warnings: list = []

    with TIMING.Timer() as total:
        RUN.resolve_development_fold(fold)
        if canonical is None:
            with TIMING.Timer() as t:
                canonical = DATA.load_canonical(paths)
            timings["matrix_load_seconds"] = t.seconds
        if canonical.manifest.get("content_hash") != \
                EXPECTED_MATRIX_CONTENT_HASH:
            from raceintel.model_lab.errors import ProtocolDriftError
            raise ProtocolDriftError("matrix content hash drift at run time")

        with TIMING.Timer() as t:
            dataset = SPLITS.materialize(canonical, TUNE.M6_TASK, fold,
                                         feature_set)
        timings["materialize_seconds"] = t.seconds
        RUN._check_no_holdout_rows(dataset.validation_metadata, fold)

        with TIMING.Timer() as t:
            config = EX.build_config(
                TUNE.M6_TASK, feature_set, fold,
                model_family=family_name, seed=seed,
                model_parameters=model_parameters,
                preprocessing_config=PRE.preprocessing_contract_dict(),
                calibration_config={"method": "none"},
                training_rows=int(dataset.train_counts["eligible"]),
                training_races=int(
                    dataset.train_metadata["race_id"].nunique()),
                validation_rows=int(dataset.validation_counts["eligible"]),
                validation_races=int(
                    dataset.validation_metadata["race_id"].nunique()))
        timings["config_seconds"] = t.seconds

        if dataset.X_train.shape[0] == 0:
            raise ExperimentConfigError(f"{fold}: training side is empty")

        with TIMING.Timer() as t:
            model = TC.fit_fresh_model(
                family, selected_config, dataset.X_train, dataset.y_train)
        timings["fit_seconds"] = t.seconds
        timings["preprocessing_fit_seconds"] = model.timing.get(
            "preprocessing_fit_seconds")
        timings["estimator_fit_seconds"] = model.timing.get(
            "estimator_fit_seconds")
        for message in model.fit_warnings:
            warnings.append(f"fit: {message}")
        sanity = model.sanity()
        if sanity["classes"] != [0, 1]:
            raise InvalidPredictionError(
                f"{fold}: estimator classes are not binary 0/1: {sanity}")

        validation_frame = canonical.frame.loc[
            dataset.y_validation.index].copy()
        if list(validation_frame.index) != list(dataset.y_validation.index):
            raise ExperimentConfigError(
                "validation frame rows do not match the materialized "
                "validation target index")

        with TIMING.Timer() as t:
            validation_prediction = model.predict_result(
                dataset.X_validation,
                list(validation_frame["state_id"]))
        timings["transform_predict_seconds"] = t.seconds
        if validation_prediction.kind is not \
                PredictionKind.BINARY_PROBABILITY:
            raise InvalidPredictionError(
                f"{family_name} must emit BINARY_PROBABILITY")

        with TIMING.Timer() as t:
            aligned = RUN._align_validation(validation_prediction,
                                            validation_frame)
        timings["align_seconds"] = t.seconds

        y_true = np.asarray(
            dataset.y_validation.astype(float).to_numpy(), dtype=float)
        race_ids = np.asarray(
            dataset.validation_metadata["race_id"].astype(str))
        finite = RUN._finite_mask(aligned)
        n_missing = int((~finite).sum())
        if n_missing:
            raise InvalidPredictionError(
                f"{fold}: {n_missing} non-finite {family_name} probabilities")

        resolved = TASKS.resolve_task(TUNE.M6_TASK)
        with TIMING.Timer() as t:
            metric_payloads, w = RUN.evaluate_row_metrics(
                validation_prediction, tuple(resolved.metrics), y_true,
                aligned, race_ids)
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
            race_payload, w = RUN.evaluate_winner_top_k(
                validation_prediction, canonical,
                tuple(sorted(set(
                    dataset.validation_metadata["race_id"].astype(str)))),
                **(topk_kwargs or {}))
            warnings.extend(w)
            race_metrics = {"winner_top_k": race_payload}
        timings["topk_seconds"] = t.seconds

        prevalence = float(np.mean(np.asarray(
            dataset.y_train.astype(float))))

        with TIMING.Timer() as t:
            _, batch_samples = TIMING.timed_call(
                model.predict_positive_probability,
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
                return model.predict_positive_probability(
                    single_frame.iloc[[row_index]])
            single_samples = []
            for row_index in range(len(single_frame)):
                _, samples = TIMING.timed_call(_single, row_index,
                                               repeats=1, warmup=0)
                single_samples.extend(samples)
            single_summary = TIMING.latency_summary(single_samples)
        timings["latency_probe_seconds"] = t.seconds
        latency = {
            "batch": batch_summary, "single_state": single_summary,
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
                "model_family": family_name,
                "model_parameters": model_parameters,
                "preprocessing": PRE.preprocessing_contract_dict(),
                "sklearn_version": TC.SKLEARN_VERSION,
                "feature_names_hash": hashlib.sha256(
                    "\n".join(dataset.feature_names).encode()).hexdigest(),
                "n_features_in": int(len(dataset.feature_names)),
                "transformed_dim": int(sanity["transformed_dim"]),
                "training_sanity": sanity,
                "fit_warnings": list(model.fit_warnings),
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

    _OUTER_EVALUATION_LOG.append(
        {"family": family, "fold": fold,
         "experiment_id": config.experiment_id})
    timings["total_seconds"] = total.seconds
    out = {"config": config, "result": result, "dest": str(dest),
           "timings": timings, "model": model}
    if return_predictions:
        out["predictions"] = np.asarray(aligned, dtype=float)
    return out


def run_tuning_and_outer(*, family: str, fold: str,
                         feature_set: str = TUNE.M6_FEATURE_SET,
                         seed: int = TUNE.M6_SEED, paths=None, root=None,
                         canonical: DATA.CanonicalMatrix | None = None,
                         return_predictions: bool = False,
                         topk_kwargs: dict | None = None) -> dict:
    """Full M6 unit for one (family, outer fold): tune, select, refit, eval."""
    if canonical is None:
        canonical = DATA.load_canonical(paths)
    tuning = TUNE.tune_family(canonical, family, fold,
                              task=TUNE.M6_TASK, feature_set=feature_set)
    selected = tuning["selection"]["selected_config"]
    outer = run_outer_selected(
        family=family, fold=fold, selected_config=selected,
        feature_set=feature_set, seed=seed, paths=paths, root=root,
        canonical=canonical, return_predictions=return_predictions,
        topk_kwargs=topk_kwargs)
    return {"tuning": tuning, "outer": outer}
