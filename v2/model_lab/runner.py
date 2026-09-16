"""M2 development execution runner (baselines now, model adapters later).

One canonical evaluation path: ``ExperimentConfig`` -> ``materialize`` ->
baseline generator / future model adapter -> ``PredictionResult`` ->
identity alignment -> M1.1 semantic metric applicability -> metric
evaluation -> race/stage/calibration aggregation -> ``ExperimentResult`` ->
``write_experiment``.

Nothing here reimplements splitting, masking, feature resolution,
prediction identity, metrics, calibration math, race aggregation, stage
partitioning, serialization or experiment identity: every step delegates
to the approved M1/M1.1 APIs. No estimator is constructed or trained;
only development folds (D1/D2/D3) are accepted.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from v2.model_lab import aggregation as AGG
from v2.model_lab import baselines as BASE
from v2.model_lab import calibration as CAL
from v2.model_lab import data as DATA
from v2.model_lab import experiment as EX
from v2.model_lab import metrics as MET
from v2.model_lab import predictions as PR
from v2.model_lab import results as RES
from v2.model_lab import splits as SPLITS
from v2.model_lab import stages as STAGES
from v2.model_lab import tasks as TASKS
from v2.model_lab import timing as TIMING
from v2.model_lab import winner as WINNER
from v2.model_lab.errors import (
    ExperimentConfigError,
    InvalidPredictionError,
    ProtectedHoldoutError,
    UnknownBaselineError,
    UnknownFoldError,
    UnsupportedMetricError,
)
from v2.model_lab.protocol import (
    EXPECTED_MATRIX_CONTENT_HASH,
    PROTECTED_HOLDOUT_SEASON,
)

#: The only folds the development runner accepts. HOLDOUT, FINAL_FIT,
#: season ids and anything else fail loudly (see resolve_development_fold).
DEVELOPMENT_ONLY_FOLDS = ("D1", "D2", "D3")

#: Calibration metric names evaluated for genuine probability predictions.
CALIBRATION_METRIC_NAMES = ("expected_calibration_error",
                            "calibration_report")


def resolve_development_fold(fold_id: str):
    """Return the SplitSpec for a development fold; reject everything else.

    HOLDOUT/2025 raise ProtectedHoldoutError; FINAL_FIT, season ids and
    unknown ids raise UnknownFoldError/ExperimentConfigError. There is no
    opt-in flag: the development runner cannot evaluate the holdout.
    """
    if fold_id in DEVELOPMENT_ONLY_FOLDS:
        return SPLITS.get_split(fold_id)
    if fold_id in (SPLITS.HOLDOUT_ID, str(PROTECTED_HOLDOUT_SEASON),
                   "2025", "HOLDOUT_2025"):
        raise ProtectedHoldoutError(
            f"development runner cannot evaluate {fold_id!r}: the 2025 "
            "holdout is protected; use D1/D2/D3")
    if fold_id == SPLITS.FINAL_FIT_ID:
        raise ExperimentConfigError(
            "development runner accepts D1/D2/D3 only; FINAL_FIT is not a "
            "development evaluation fold")
    raise UnknownFoldError(
        f"unknown development fold {fold_id!r}; known: "
        f"{list(DEVELOPMENT_ONLY_FOLDS)}")


def _json_safe(value):
    """Map NaN floats to None so result documents stay strict JSON."""
    if isinstance(value, float) and not math.isfinite(value):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def _not_applicable(reason: str) -> dict:
    return {"status": "NOT_APPLICABLE", "reason": reason}


def _check_no_holdout_rows(validation_metadata: pd.DataFrame,
                           fold_id: str) -> None:
    seasons = validation_metadata["season"].astype(int)
    if (seasons == PROTECTED_HOLDOUT_SEASON).any():
        raise ProtectedHoldoutError(
            f"{fold_id}: validation metadata reaches the protected "
            f"{PROTECTED_HOLDOUT_SEASON} holdout")
    if len(validation_metadata) == 0:
        raise ExperimentConfigError(
            f"{fold_id}: development validation side is empty")


def _align_validation(prediction: PR.PredictionResult,
                      validation_frame: pd.DataFrame) -> np.ndarray:
    """Identity-align validation predictions; fail on any id mismatch."""
    expected = list(validation_frame["state_id"])
    return PR.align(prediction, expected)


def _finite_mask(values: np.ndarray) -> np.ndarray:
    return np.isfinite(np.asarray(values, dtype=float))


def evaluate_row_metrics(prediction: PR.PredictionResult,
                         metric_names: tuple,
                         y_true: np.ndarray, y_pred: np.ndarray,
                         race_ids: np.ndarray) -> tuple:
    """Evaluate row metrics through the M1.1 applicability guard.

    Applicable metrics produce ``scoped_metric`` (race-macro headline +
    state-pooled diagnostic). Unsupported kind/metric combinations are
    recorded as NOT_APPLICABLE with a reason — never computed, never
    silently dropped. Returns (payloads, warnings).
    """
    payloads: dict = {}
    warnings: list = []
    for name in metric_names:
        try:
            MET.require_metric_applicability(prediction.kind, name)
        except UnsupportedMetricError as exc:
            payloads[name] = _not_applicable(str(exc))
            warnings.append(f"{name}: NOT_APPLICABLE ({exc})")
            continue
        payload = AGG.scoped_metric(y_true, y_pred, race_ids, name)
        payloads[name] = {"status": "OK", **_json_safe(payload)}
    return payloads, warnings


def evaluate_stages(prediction: PR.PredictionResult,
                    ok_metric_names: tuple,
                    stages: np.ndarray, y_true: np.ndarray,
                    y_pred: np.ndarray, race_ids: np.ndarray) -> tuple:
    """Stage-partitioned race-macro metrics for applicable row metrics."""
    payloads: dict = {}
    warnings: list = []
    for name in ok_metric_names:
        try:
            MET.require_metric_applicability(prediction.kind, name)
        except UnsupportedMetricError as exc:
            payloads[name] = _not_applicable(str(exc))
            continue
        payloads[name] = {"status": "OK", **_json_safe(
            AGG.stage_scoped_metrics(stages, y_true, y_pred, race_ids,
                                     name))}
        for stage, entry in payloads[name].items():
            if stage in ("status",):
                continue
            if entry["race_macro"]["value"] is None:
                warnings.append(
                    f"{name} {stage}: N/A "
                    f"(n_states={entry['n_states']}, "
                    "n_races_defined="
                    f"{entry['race_macro']['n_races_defined']})")
    return payloads, warnings


def evaluate_calibration(
        prediction: PR.PredictionResult, y_true: np.ndarray,
        y_pred: np.ndarray) -> tuple:
    """ECE + reliability data for probability predictions only."""
    try:
        MET.require_metric_applicability(
            prediction.kind, "expected_calibration_error")
    except UnsupportedMetricError as exc:
        return (_not_applicable(str(exc)),
                [f"calibration: NOT_APPLICABLE ({exc})"])
    report = CAL.calibration_report(y_true, y_pred)
    return ({"status": "OK", **_json_safe(report)}, [])


def evaluate_winner_top_k(prediction: PR.PredictionResult,
                          canonical: DATA.CanonicalMatrix,
                          race_ids: tuple, **kwargs) -> tuple:
    """Synchronized winner top-k via the canonical M1.1 evaluator."""
    try:
        out = WINNER.synchronized_winner_top_k(
            prediction, canonical, race_ids=list(race_ids), **kwargs)
    except (InvalidPredictionError, UnsupportedMetricError) as exc:
        return (_not_applicable(str(exc)),
                [f"winner_top_k: NOT_APPLICABLE ({exc})"])
    return ({"status": "OK", **_json_safe(out)}, [])


def run_experiment(*, task: str, baseline: str, fold: str,
                   feature_set: str = "ALL_84",
                   seed: int = EX.PROJECT_SEED,
                   paths=None, root=None,
                   topk_kwargs: dict | None = None) -> dict:
    """Execute one baseline experiment on a development fold.

    Returns {"config", "result", "dest", "timings"}. Every numeric
    performance value is persisted via ``write_experiment``; failures of
    contract checks raise loudly before anything is written.
    """
    timings: dict = {}
    warnings: list = []

    with TIMING.Timer() as total:
        split = resolve_development_fold(fold)
        try:
            baseline_spec = BASE.get_baseline(baseline)
        except UnknownBaselineError:
            raise
        if task not in baseline_spec.supported_tasks:
            raise ExperimentConfigError(
                f"baseline {baseline!r} does not support task {task!r}; "
                f"supported: {list(baseline_spec.supported_tasks)}")

        with TIMING.Timer() as t:
            canonical = DATA.load_canonical(paths)
        timings["matrix_load_seconds"] = t.seconds
        if canonical.manifest.get("content_hash") != \
                EXPECTED_MATRIX_CONTENT_HASH:
            from v2.model_lab.errors import ProtocolDriftError
            raise ProtocolDriftError("matrix content hash drift at run time")

        with TIMING.Timer() as t:
            dataset = SPLITS.materialize(canonical, task, fold, feature_set)
        timings["materialize_seconds"] = t.seconds
        _check_no_holdout_rows(dataset.validation_metadata, fold)

        with TIMING.Timer() as t:
            config = EX.build_config(
                task, feature_set, fold,
                model_family=f"baseline:{baseline}", seed=seed,
                training_rows=int(dataset.train_counts["eligible"]),
                training_races=int(
                    dataset.train_metadata["race_id"].nunique()),
                validation_rows=int(dataset.validation_counts["eligible"]),
                validation_races=int(
                    dataset.validation_metadata["race_id"].nunique()))
        timings["config_seconds"] = t.seconds

        resolved = TASKS.resolve_task(task)
        train_frame = canonical.frame.loc[dataset.y_train.index].copy()
        validation_frame = canonical.frame.loc[
            dataset.y_validation.index].copy()

        with TIMING.Timer() as t:
            train_y = (dataset.y_train
                       if baseline_spec.train_dependence else None)
            if baseline == "CLASS_PRIOR" and train_y is not dataset.y_train:
                raise ExperimentConfigError(
                    "CLASS_PRIOR must receive ExperimentDataset.y_train")
            _, validation_prediction = BASE.run_baseline(
                baseline, task, train_frame, validation_frame,
                train_y=train_y)
        timings["generation_seconds"] = t.seconds

        with TIMING.Timer() as t:
            if list(validation_frame.index) != \
                    list(dataset.y_validation.index):
                raise ExperimentConfigError(
                    "validation frame rows do not match the materialized "
                    "validation target index")
            y_aligned_target = dataset.y_validation
            aligned = _align_validation(validation_prediction,
                                        validation_frame)
        timings["align_seconds"] = t.seconds

        y_true = np.asarray(
            y_aligned_target.astype(float).to_numpy(), dtype=float)
        race_ids = np.asarray(
            dataset.validation_metadata["race_id"].astype(str))
        kind = validation_prediction.kind

        finite = _finite_mask(aligned)
        n_missing = int((~finite).sum())
        if n_missing and kind is PR.PredictionKind.BINARY_PROBABILITY:
            raise InvalidPredictionError(
                f"{baseline}/{fold}: {n_missing} non-finite probability "
                "predictions")
        if n_missing:
            warnings.append(
                f"{n_missing}/{len(aligned)} {kind.value} predictions are "
                "NaN (legitimate missing); ranking metrics use the finite "
                "subset only")
            y_true = y_true[finite]
            race_ids = race_ids[finite]
            aligned = aligned[finite]

        with TIMING.Timer() as t:
            metric_names = tuple(resolved.metrics)
            metric_payloads, w = evaluate_row_metrics(
                validation_prediction, metric_names, y_true, aligned,
                race_ids)
            warnings.extend(w)
        timings["metric_seconds"] = t.seconds

        ok_metrics = tuple(
            name for name, payload in metric_payloads.items()
            if payload.get("status") == "OK")

        with TIMING.Timer() as t:
            stage_index = dataset.y_validation.index
            if n_missing:
                stage_index = stage_index[finite]
            stage_labels = STAGES.stage_partition(
                validation_frame.loc[stage_index, "race_progress_frac"])
            stage_payloads, w = evaluate_stages(
                validation_prediction, ok_metrics,
                np.asarray(stage_labels), y_true, aligned, race_ids)
            warnings.extend(w)
        timings["stage_seconds"] = t.seconds

        with TIMING.Timer() as t:
            calibration_payload, w = evaluate_calibration(
                validation_prediction, y_true, aligned)
            warnings.extend(w)
        timings["calibration_seconds"] = t.seconds

        with TIMING.Timer() as t:
            if task == "winner":
                race_payload, w = evaluate_winner_top_k(
                    validation_prediction, canonical,
                    tuple(sorted(set(
                        dataset.validation_metadata["race_id"].astype(
                            str)))),
                    **(topk_kwargs or {}))
                warnings.extend(w)
                race_metrics = {"winner_top_k": race_payload}
            else:
                race_metrics = {"winner_top_k": _not_applicable(
                    "synchronized winner top-k applies to the winner task "
                    "only")}
        timings["topk_seconds"] = t.seconds

        prevalence = (float(np.mean(np.asarray(
            dataset.y_train.astype(float)))) if resolved.is_binary else None)

        if baseline == "CLASS_PRIOR":
            all_equal = bool(np.all(aligned == aligned[0])) if len(
                aligned) else False
            if not all_equal or not math.isclose(
                    float(aligned[0]), float(prevalence), rel_tol=0,
                    abs_tol=1e-12):
                raise ExperimentConfigError(
                    "CLASS_PRIOR validation predictions != train prevalence")

        result = EX.ExperimentResult(
            experiment_id=config.experiment_id,
            status=EX.ExperimentStatus.OK,
            prediction_seconds=(timings["generation_seconds"]
                                + timings["metric_seconds"]
                                + timings["stage_seconds"]
                                + timings["calibration_seconds"]
                                + timings["topk_seconds"]),
            metrics={"train_prevalence": (
                {"status": "INFO", "value": prevalence}
                if prevalence is not None else {"status": "NOT_APPLICABLE",
                                                "reason": "non-binary task"}),
                     **metric_payloads},
            calibration=(calibration_payload
                         if calibration_payload.get("status") == "OK"
                         else None),
            stage_metrics=stage_payloads,
            race_metrics=race_metrics,
            warnings=warnings,
            environment=RES.environment_metadata(
                paths.root if paths is not None else None),
        )
        with TIMING.Timer() as t:
            dest = RES.write_experiment(config, result, paths=paths,
                                        root=root)
        timings["serialize_seconds"] = t.seconds

    timings["total_seconds"] = total.seconds
    return {"config": config, "result": result, "dest": str(dest),
            "timings": timings}
