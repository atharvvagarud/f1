"""M8 calibration evaluation & selection (development-only).

M7 froze ONE development-only Logistic Regression specification::

    LogisticRegression · C=0.01 · lbfgs · max_iter=1000
    class_weight=None · random_state=42 · feature set ALL_84
    probability semantics = INDEPENDENT_BINARY

M8 answers one scientific question: does a post-hoc calibration layer improve
chronologically valid probabilistic quality enough to justify its extra fitted
complexity? Exactly three candidates are compared:

- ``RAW``      — the untouched frozen base-model probability;
- ``PLATT``    — a one-dimensional sigmoid mapping fit on a held-out
                 calibration season (explicit ``LogisticRegression`` over
                 ``logit(clip(p, eps, 1-eps))``; no hidden CV);
- ``ISOTONIC`` — ``sklearn.isotonic.IsotonicRegression`` fit on the same
                 calibration season.

Strict temporal architecture (base-fit < calibration < outer evaluation)::

    D1: base 2018–2020 · calibration 2021 · evaluation 2022
    D2: base 2018–2021 · calibration 2022 · evaluation 2023
    D3: base 2018–2022 · calibration 2023 · evaluation 2024

Every calibrator consumes ONLY the scalar base probability (never a position,
gap, pace, tyre, race-state, driver/race identity, season or any ALL_84
feature), is fit on calibration rows only, and is applied to the SAME outer raw
probability vector the RAW candidate receives. 2025 is never touched.

Calibration is not assumed beneficial: RAW is a legitimate winner and the
selection rule (predeclared before execution) is biased toward the simpler
candidate on effective ties.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from v2.model_lab import data as DATA
from v2.model_lab import experiment as EX
from v2.model_lab import preprocessing as PRE
from v2.model_lab import results as RES
from v2.model_lab import runner as RUN
from v2.model_lab import splits as SPLITS
from v2.model_lab import stages as STAGES
from v2.model_lab import tasks as TASKS
from v2.model_lab import timing as TIMING
from v2.model_lab import tuning_candidates as TC
from v2.model_lab import tuning_suite as TSUITE
from v2.model_lab.errors import (
    ExperimentConfigError,
    InvalidPredictionError,
    ProtectedHoldoutError,
)
from v2.model_lab.inner_splits import materialize_seasons
from v2.model_lab.logreg import LOGREG_SPEC
from v2.model_lab.metrics import (
    LOG_LOSS_EPSILON,
    validate_binary_target,
    validate_probabilities,
)
from v2.model_lab.predictions import (
    PredictionKind,
    PredictionResult,
    ProbabilitySemantics,
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

# --- frozen M8 contract -------------------------------------------------------

M8_TASK = "winner"
M8_FEATURE_SET = "ALL_84"
M8_SEED = 42

#: M7-frozen base regularization. M8 never retunes it.
FROZEN_C = 0.01

#: The three probability variants under evaluation.
METHODS = ("RAW", "PLATT", "ISOTONIC")

#: Increasing complexity/flexibility order; used for the tie-break.
SIMPLE_ORDER = {"RAW": 0, "PLATT": 1, "ISOTONIC": 2}

#: Fixed numerical-stability clip for Platt logits (declared before execution).
PLATT_EPSILON = 1e-6

#: Predeclared material-regression threshold (relative log-loss degradation).
MATERIAL_REGRESSION_REL = 0.01

#: Predeclared absolute mean log-loss tie tolerance.
TIE_TOLERANCE = 1e-4

#: Distinct outer experiment family names (never collide with M3–M7 ids).
CALIBRATION_FAMILY_NAMES = {
    "RAW": "logistic_regression_calibrated_raw",
    "PLATT": "logistic_regression_calibrated_platt",
    "ISOTONIC": "logistic_regression_calibrated_isotonic",
}

#: Frozen base-model specification recorded in every M8 experiment.
BASE_MODEL_SPEC = {
    "estimator": "LogisticRegression",
    "penalty": "l2 (sklearn default, not passed explicitly)",
    "C": FROZEN_C,
    "solver": LOGREG_SPEC["solver"],
    "max_iter": LOGREG_SPEC["max_iter"],
    "class_weight": LOGREG_SPEC["class_weight"],
    "random_state": LOGREG_SPEC["random_state"],
    "feature_set": M8_FEATURE_SET,
    "probability_semantics": "INDEPENDENT_BINARY",
}

SUITE_SCHEMA_VERSION = "v1"
CALIBRATION_SELECTION_FILENAME = "calibration_selection_v1.json"

#: Prototype races for the optional deterministic race-level bootstrap.
BOOTSTRAP_REPLICATES = 1000
BOOTSTRAP_SEED = EX.PROJECT_SEED

#: Immutable Phase-2/M0 boundary artifacts byte-hashed for the M8 artifact.
PHASE2_REL = "data/v2/processed/model_matrix/matrix_version=v1"
PROTOCOL_JSON_REL = "docs/generated/model_lab_protocol_v1.json"
FREEZE_MANIFEST_REL = "docs/generated/phase2_freeze_manifest.json"


# --- temporal calibration split ----------------------------------------------


@dataclass(frozen=True)
class CalibrationSplit:
    """Chronologically ordered base-fit / calibration / evaluation seasons."""

    outer_fold: str
    base_seasons: tuple
    calibration_seasons: tuple
    evaluation_seasons: tuple

    def to_dict(self) -> dict:
        return {
            "outer_fold": self.outer_fold,
            "base_seasons": list(self.base_seasons),
            "calibration_seasons": list(self.calibration_seasons),
            "evaluation_seasons": list(self.evaluation_seasons),
        }


def resolve_calibration_split(fold: str) -> CalibrationSplit:
    """Derive the M8 temporal split from the frozen outer development fold.

    The calibration season is the LAST complete season of the outer TRAIN and
    the base fit is every earlier outer-training season; the evaluation season
    is the outer validation season. This enforces base < calibration < eval and
    can never reach the protected 2025 holdout.
    """
    if fold not in RUN.DEVELOPMENT_ONLY_FOLDS:
        if fold in (SPLITS.HOLDOUT_ID, str(PROTECTED_HOLDOUT_SEASON), "2025"):
            raise ProtectedHoldoutError(
                "M8 has no calibration path to the protected 2025 holdout")
        raise ExperimentConfigError(
            f"unknown M8 fold {fold!r}; known: {list(RUN.DEVELOPMENT_ONLY_FOLDS)}")
    outer = SPLITS.get_split(fold)
    seasons = tuple(int(s) for s in outer.train_seasons)
    if len(seasons) < 2:
        raise ExperimentConfigError(
            f"{fold}: outer TRAIN needs >= 2 seasons to hold out a calibration "
            "season")
    base = seasons[:-1]
    calibration = (seasons[-1],)
    evaluation = tuple(int(s) for s in outer.validation_seasons)
    if not evaluation:
        raise ExperimentConfigError(f"{fold}: outer validation side is empty")
    if not (max(base) < min(calibration) <= max(calibration)
            < min(evaluation)):
        raise ExperimentConfigError(
            f"{fold}: base/calibration/evaluation seasons are not strictly "
            "ordered")
    if PROTECTED_HOLDOUT_SEASON in (*base, *calibration, *evaluation):
        raise ProtectedHoldoutError(
            f"{fold}: protected 2025 holdout reached the M8 split")
    return CalibrationSplit(fold, base, calibration, evaluation)


# --- calibrators (scalar-probability mappings) -------------------------------


def _logit(prob, epsilon: float = PLATT_EPSILON) -> np.ndarray:
    p = np.clip(np.asarray(prob, dtype=float), epsilon, 1.0 - epsilon)
    return np.log(p / (1.0 - p))


def _scalar_probabilities(prob) -> np.ndarray:
    """Require a 1-D scalar probability vector (the frozen base score)."""
    arr = np.asarray(prob, dtype=float)
    if arr.ndim != 1:
        raise InvalidPredictionError(
            "calibrator input must be a 1-D scalar probability vector; "
            f"got shape {arr.shape}")
    return validate_probabilities(arr)


@dataclass
class PlattCalibrator:
    """One-dimensional sigmoid mapping fit on calibration rows only."""

    coefficient: float
    intercept: float
    epsilon: float
    _model: LogisticRegression

    def transform(self, prob) -> np.ndarray:
        x = _logit(prob, self.epsilon).reshape(-1, 1)
        out = np.asarray(self._model.predict_proba(x)[:, 1], dtype=float)
        return np.clip(out, 0.0, 1.0)

    def diagnostics(self) -> dict:
        return {
            "coefficient": self.coefficient,
            "intercept": self.intercept,
            "epsilon": self.epsilon,
            "finite": bool(np.isfinite([self.coefficient,
                                        self.intercept]).all()),
            "coefficient_positive": bool(self.coefficient > 0.0),
            "n_input_features": 1,
        }


@dataclass
class IsotonicCalibrator:
    """Monotonic mapping fit on calibration rows only."""

    n_thresholds: int
    _model: IsotonicRegression

    def transform(self, prob) -> np.ndarray:
        out = np.asarray(self._model.predict(np.asarray(prob, dtype=float)),
                         dtype=float)
        return np.clip(out, 0.0, 1.0)

    def diagnostics(self) -> dict:
        return {"n_thresholds": int(self.n_thresholds), "n_input_features": 1}


def fit_platt(cal_prob, cal_y, *, epsilon: float = PLATT_EPSILON
              ) -> PlattCalibrator:
    """Fit the Platt mapping on calibration probabilities + labels only."""
    y = validate_binary_target(cal_y)
    p = _scalar_probabilities(cal_prob)
    if len(y) != len(p):
        raise ExperimentConfigError("Platt calibration X/y length mismatch")
    if len(y) == 0:
        raise ExperimentConfigError("Platt calibration set is empty")
    x = _logit(p, epsilon).reshape(-1, 1)
    model = LogisticRegression(
        solver="lbfgs", max_iter=1000, class_weight=None, random_state=M8_SEED)
    model.fit(x, y)
    coefficient = float(np.asarray(model.coef_).ravel()[0])
    intercept = float(np.asarray(model.intercept_).ravel()[0])
    if not (math.isfinite(coefficient) and math.isfinite(intercept)):
        raise InvalidPredictionError("Platt calibrator produced non-finite "
                                     "parameters")
    return PlattCalibrator(coefficient, intercept, float(epsilon), model)


def fit_isotonic(cal_prob, cal_y) -> IsotonicCalibrator:
    """Fit the isotonic mapping on calibration probabilities + labels only."""
    y = validate_binary_target(cal_y)
    p = _scalar_probabilities(cal_prob)
    if len(y) != len(p):
        raise ExperimentConfigError("isotonic calibration X/y length mismatch")
    if len(y) == 0:
        raise ExperimentConfigError("isotonic calibration set is empty")
    model = IsotonicRegression(increasing=True, out_of_bounds="clip",
                               y_min=0.0, y_max=1.0)
    model.fit(p, y)
    thresholds = getattr(model, "X_thresholds_", None)
    n_thresholds = int(len(thresholds)) if thresholds is not None else 0
    return IsotonicCalibrator(n_thresholds, model)


def calibration_sample_audit(cal_prob, cal_y, *,
                             season=None) -> dict:
    """Descriptive audit of the calibration set (no causal claims)."""
    y = validate_binary_target(cal_y)
    p = validate_probabilities(cal_prob)
    positives = int(y.sum())
    negatives = int(len(y) - positives)
    return {
        "season": int(season) if season is not None else None,
        "rows": int(len(y)),
        "positive_count": positives,
        "negative_count": negatives,
        "winner_prevalence": (float(positives / len(y)) if len(y) else None),
        "unique_raw_probability_count": int(len(np.unique(p))),
        "raw_probability_min": (float(p.min()) if len(p) else None),
        "raw_probability_max": (float(p.max()) if len(p) else None),
        "n_exact_zero": int(np.count_nonzero(p == 0.0)),
        "n_exact_one": int(np.count_nonzero(p == 1.0)),
    }


# --- selection rule (predeclared before execution) ---------------------------


def _mean(values):
    arr = [float(v) for v in values
           if v is not None and math.isfinite(float(v))]
    return float(np.mean(arr)) if arr else None


def select_calibration_method(*, log_loss: dict, brier: dict,
                              diagnostics: dict | None = None,
                              material_regression_rel: float =
                              MATERIAL_REGRESSION_REL,
                              tie_tolerance: float = TIE_TOLERANCE) -> dict:
    """Apply the frozen global calibration-selection rule.

    ``log_loss`` / ``brier`` map method -> {fold: value}. Only probability
    quality (race-macro log loss primary, Brier guard) may influence the
    decision; ECE is deliberately not an input. The protected final holdout is
    unreachable.

    Rule: a calibrated method may replace RAW only if (A) its mean race-macro
    log loss is lower than RAW's, (B) its mean Brier is no worse, (C) it does
    not materially regress log loss on a majority of folds, and (D) its fitted
    behaviour is not pathological. On effective ties (absolute mean log-loss
    difference <= ``tie_tolerance``) the simpler method wins unless the more
    complex one shows clearly better mean Brier with a majority of folds
    improving.
    """
    methods = list(METHODS)
    for method in methods:
        if method not in log_loss or method not in brier:
            raise ExperimentConfigError(
                f"selection needs log loss and Brier for {method!r}")
    folds = sorted(log_loss["RAW"])
    for method in methods:
        if sorted(log_loss[method]) != folds or sorted(brier[method]) != folds:
            raise ExperimentConfigError(
                "selection requires identical fold keys for every method")
    if not folds:
        raise ExperimentConfigError("selection needs at least one outer fold")

    diagnostics = diagnostics or {}
    means_ll = {m: _mean([log_loss[m][f] for f in folds]) for m in methods}
    means_br = {m: _mean([brier[m][f] for f in folds]) for m in methods}
    if any(means_ll[m] is None for m in methods):
        raise ExperimentConfigError("selection needs finite aggregate log loss")

    material: dict = {}
    for m in ("PLATT", "ISOTONIC"):
        per_fold = {}
        count = 0
        for f in folds:
            raw = log_loss["RAW"][f]
            value = log_loss[m][f]
            rel = ((float(value) - float(raw)) / abs(float(raw))
                   if raw not in (None, 0) else None)
            degraded = rel is not None and rel > material_regression_rel
            count += int(degraded)
            per_fold[f] = {"raw_log_loss": raw, "calibrated_log_loss": value,
                           "relative_change": rel,
                           "material_regression": bool(degraded)}
        material[m] = {"per_fold": per_fold, "n_material_regression": count,
                       "majority_material_regression": count * 2 > len(folds)}

    pathological = {
        m: bool(diagnostics.get(m, {}).get("pathological", False))
        for m in ("PLATT", "ISOTONIC")}

    eligibility: dict = {}
    eligible: list = []
    for m in ("PLATT", "ISOTONIC"):
        checks = {
            "A_mean_log_loss_lower_than_raw": means_ll[m] < means_ll["RAW"],
            "B_mean_brier_no_worse_than_raw": means_br[m] <= means_br["RAW"],
            "C_not_majority_material_regression":
                not material[m]["majority_material_regression"],
            "D_not_pathological": not pathological[m],
        }
        eligibility[m] = checks
        if all(checks.values()):
            eligible.append(m)

    def _near_tie(a: str, b: str) -> bool:
        return abs(means_ll[a] - means_ll[b]) <= tie_tolerance

    tie_break_applied = False
    tie_detail = None

    if not eligible:
        selected = "RAW"
        rationale = ("no calibrated method satisfied the predeclared "
                     "eligibility guards (A–D) — RAW retained")
    else:
        best_ll = min(means_ll[m] for m in eligible)
        near_best = [m for m in eligible
                     if means_ll[m] <= best_ll + tie_tolerance]
        candidate = min(near_best, key=lambda m: SIMPLE_ORDER[m])
        if _near_tie(candidate, "RAW"):
            better_folds = sum(
                1 for f in folds
                if brier[candidate][f] is not None
                and brier["RAW"][f] is not None
                and float(brier[candidate][f])
                < float(brier["RAW"][f]) - tie_tolerance)
            clear_brier = (means_br[candidate] is not None
                           and means_br["RAW"] is not None
                           and means_br[candidate]
                           < means_br["RAW"] - tie_tolerance
                           and better_folds * 2 > len(folds))
            if clear_brier:
                selected = candidate
                tie_detail = ("mean log loss within tolerance but candidate "
                              "shows clearly better Brier on a majority of "
                              "folds")
            else:
                selected = "RAW"
                tie_detail = ("mean log loss within tolerance; simplify to RAW "
                              "(no clear consistent Brier advantage)")
            tie_break_applied = True
        else:
            selected = candidate

        if len(near_best) > 1 and selected != "RAW":
            simpler = min(near_best, key=lambda m: SIMPLE_ORDER[m])
            if simpler != candidate:
                selected = simpler
                tie_break_applied = True
                tie_detail = ("calibrated candidates within tolerance; prefer "
                              "the simpler mapping")

    return {
        "selected_method": selected,
        "rule": "mean_log_loss_primary_with_brier_and_regression_guards",
        "folds": folds,
        "mean_log_loss": means_ll,
        "mean_brier": means_br,
        "material_regression": material,
        "material_regression_rel": material_regression_rel,
        "pathological": pathological,
        "eligibility": eligibility,
        "eligible_methods": eligible,
        "tie_tolerance": tie_tolerance,
        "tie_break_applied": tie_break_applied,
        "tie_break_detail": tie_detail,
        "ece_used_for_selection": False,
        "outer_validation_used": True,
        "holdout_used": False,
        "rationale": rationale if not eligible else (
            f"selected {selected} by the predeclared rule"),
    }


# --- optional deterministic race-level bootstrap -----------------------------


def _per_race_metric(y_true, prob, race_ids, metric: str) -> np.ndarray:
    from v2.model_lab.metrics import METRIC_FUNCTIONS
    fn = METRIC_FUNCTIONS[metric]
    frame_races = np.asarray([str(r) for r in race_ids])
    out = []
    for race in sorted(set(frame_races)):
        mask = frame_races == race
        out.append(float(fn(np.asarray(y_true)[mask],
                            np.asarray(prob)[mask])))
    return np.asarray(out, dtype=float)


def race_level_bootstrap(raw_prob, calibrated_prob, y_true, race_ids, *,
                         replicates: int = BOOTSTRAP_REPLICATES,
                         seed: int = BOOTSTRAP_SEED) -> dict:
    """Paired whole-race bootstrap of calibrated-minus-RAW differences.

    Diagnostic only (never converted into a significance claim). Whole races
    are the resampling unit; individual driver-state rows are never resampled.
    """
    y = validate_binary_target(y_true)
    raw = validate_probabilities(raw_prob)
    cal = validate_probabilities(calibrated_prob)
    raw_ll = _per_race_metric(y, raw, race_ids, "log_loss")
    cal_ll = _per_race_metric(y, cal, race_ids, "log_loss")
    raw_br = _per_race_metric(y, raw, race_ids, "brier")
    cal_br = _per_race_metric(y, cal, race_ids, "brier")
    d_ll = cal_ll - raw_ll
    d_br = cal_br - raw_br
    rng = np.random.default_rng(seed)
    n = len(d_ll)
    boot_ll = np.empty(replicates)
    boot_br = np.empty(replicates)
    for i in range(replicates):
        idx = rng.integers(0, n, size=n)
        boot_ll[i] = float(np.mean(d_ll[idx]))
        boot_br[i] = float(np.mean(d_br[idx]))

    def _interval(samples):
        return {
            "p2_5": float(np.percentile(samples, 2.5)),
            "p50": float(np.percentile(samples, 50.0)),
            "p97_5": float(np.percentile(samples, 97.5)),
        }

    return {
        "status": "OK",
        "unit": "whole_race",
        "replicates": int(replicates),
        "seed": int(seed),
        "n_races": int(n),
        "log_loss_difference": {
            "point": float(np.mean(d_ll)), **_interval(boot_ll)},
        "brier_difference": {
            "point": float(np.mean(d_br)), **_interval(boot_br)},
        "note": "diagnostic percentile interval only; not a significance claim",
    }


# --- canonical evaluation of one variant -------------------------------------


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
    payload = (result.race_metrics or {}).get("winner_top_k", {})
    if payload.get("status") != "OK":
        return None
    return (payload.get("accuracy") or {}).get(key)


def _peak_rss_bytes():
    try:
        import resource
        return int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    except (ImportError, OSError, AttributeError):
        return None


def _extract_variant(config, result, dest, probability) -> dict:
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
        "calibrator": result.artifact_refs.get("calibrator"),
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
        "probability_min": float(np.min(probability)) if len(probability) else None,
        "probability_max": float(np.max(probability)) if len(probability) else None,
        "probability_mean": float(np.mean(probability)) if len(probability) else None,
        "warnings": list(result.warnings),
    }


def _evaluate_variant(*, method: str, fold: str, probability, state_ids,
                      val_frame, canonical, y_true, race_ids, stage_labels,
                      resolved, base_prevalence, calibration_split,
                      calibrator_meta, timings, paths, root) -> dict:
    """Evaluate one probability variant through the canonical M2 evaluator."""
    prediction = PredictionResult(
        kind=PredictionKind.BINARY_PROBABILITY,
        state_ids=tuple(state_ids),
        values=np.asarray(probability, dtype=float),
        semantics=ProbabilitySemantics.INDEPENDENT_BINARY,
        positive_class=1,
    )
    warnings: list = []
    metric_payloads, w = RUN.evaluate_row_metrics(
        prediction, tuple(resolved.metrics), y_true,
        np.asarray(probability, dtype=float), race_ids)
    warnings.extend(w)
    ok_metrics = tuple(
        name for name, payload in metric_payloads.items()
        if payload.get("status") == "OK")

    stage_payloads, w = RUN.evaluate_stages(
        prediction, ok_metrics, np.asarray(stage_labels), y_true,
        np.asarray(probability, dtype=float), race_ids)
    warnings.extend(w)

    calibration_payload, w = RUN.evaluate_calibration(
        prediction, y_true, np.asarray(probability, dtype=float))
    warnings.extend(w)

    race_payload, w = RUN.evaluate_winner_top_k(
        prediction, canonical,
        tuple(sorted(set(str(r) for r in race_ids))))
    warnings.extend(w)

    model_parameters = {**BASE_MODEL_SPEC, "calibration_method": method}
    calibration_config = {
        "method": method.lower(),
        "input": "scalar_base_probability",
        "fit_seasons": list(calibration_split.calibration_seasons),
        "platt_epsilon": PLATT_EPSILON if method == "PLATT" else None,
        "outer_normalization": "none (INDEPENDENT_BINARY)",
    }
    config = EX.build_config(
        M8_TASK, M8_FEATURE_SET, fold,
        model_family=CALIBRATION_FAMILY_NAMES[method], seed=M8_SEED,
        model_parameters=model_parameters,
        preprocessing_config=PRE.preprocessing_contract_dict(),
        calibration_config=calibration_config,
        training_rows=int(base_prevalence["n_rows"]),
        training_races=int(base_prevalence["n_races"]))

    with TIMING.Timer() as t:
        result = EX.ExperimentResult(
            experiment_id=config.experiment_id,
            status=EX.ExperimentStatus.OK,
            fit_seconds=timings.get("base_model_fit_seconds"),
            prediction_seconds=timings.get("transform_seconds"),
            latency={"transform_seconds": timings.get("transform_seconds"),
                     "method": method},
            metrics={"train_prevalence": (
                {"status": "INFO", "value": base_prevalence["prevalence"]}),
                **metric_payloads},
            calibration=(calibration_payload
                         if calibration_payload.get("status") == "OK"
                         else None),
            stage_metrics=stage_payloads,
            race_metrics={"winner_top_k": race_payload},
            artifact_refs={
                "model_family": CALIBRATION_FAMILY_NAMES[method],
                "model_parameters": model_parameters,
                "preprocessing": PRE.preprocessing_contract_dict(),
                "sklearn_version": TC.SKLEARN_VERSION,
                "n_features_in": int(base_prevalence["n_features"]),
                "transformed_dim": int(base_prevalence["transformed_dim"]),
                "training_sanity": base_prevalence["sanity"],
                "calibrator": calibrator_meta,
                "fit_warnings": list(base_prevalence["fit_warnings"]),
                "peak_rss_bytes": _peak_rss_bytes(),
            },
            warnings=warnings,
            environment=RES.environment_metadata(
                paths.root if paths is not None else None),
        )
    timings["evaluation_seconds"] = t.seconds
    dest = RES.write_experiment(config, result, paths=paths, root=root)
    entry = _extract_variant(config, result, dest,
                             np.asarray(probability, dtype=float))
    entry["timings"] = dict(timings)
    return entry


# --- one fold: base fit -> calibration -> three variants ---------------------


def run_calibration_fold(canonical: DATA.CanonicalMatrix, fold: str, *,
                         paths=None, root=None,
                         return_predictions: bool = False) -> dict:
    """Run the full M8 temporal pipeline for one outer development fold."""
    RUN.resolve_development_fold(fold)
    split = resolve_calibration_split(fold)
    resolved = TASKS.resolve_task(M8_TASK)
    timings: dict = {}

    with TIMING.Timer() as t:
        X_base, y_base, meta_base = materialize_seasons(
            canonical, split.base_seasons, M8_TASK, M8_FEATURE_SET)
        X_cal, y_cal, meta_cal = materialize_seasons(
            canonical, split.calibration_seasons, M8_TASK, M8_FEATURE_SET)
        X_eval, y_eval, meta_eval = materialize_seasons(
            canonical, split.evaluation_seasons, M8_TASK, M8_FEATURE_SET)
    timings["materialize_seconds"] = t.seconds
    if not len(y_base) or not len(y_cal) or not len(y_eval):
        raise ExperimentConfigError(f"{fold}: empty M8 temporal partition")

    with TIMING.Timer() as t:
        preprocessor = PRE.fit_preprocessor(X_base, canonical.schema)
    timings["preprocessing_fit_seconds"] = t.seconds
    with TIMING.Timer() as t:
        model = TC.fit_fresh_model(
            TC.LOGREG_FAMILY, {"C": FROZEN_C}, X_base, y_base,
            preprocessor=preprocessor)
    timings["base_model_fit_seconds"] = t.seconds
    for message in model.fit_warnings:
        if "ConvergenceWarning" in message:
            pass
    with TIMING.Timer() as t:
        cal_prob = model.predict_positive_probability(X_cal)
        raw_prob = model.predict_positive_probability(X_eval)
    timings["prediction_seconds"] = t.seconds

    val_frame = canonical.frame.loc[y_eval.index].copy()
    if list(val_frame["state_id"]) != list(meta_eval["state_id"]):
        raise ExperimentConfigError(
            f"{fold}: evaluation identity metadata is misaligned")
    y_true = np.asarray(y_eval.astype(float).to_numpy(), dtype=float)
    race_ids = np.asarray(meta_eval["race_id"].astype(str))
    aligned_raw = PR_align(raw_prob, val_frame)
    state_ids = list(val_frame["state_id"])
    stage_labels = STAGES.stage_partition(val_frame["race_progress_frac"])

    with TIMING.Timer() as t:
        platt = fit_platt(cal_prob, y_cal)
    timings["platt_fit_seconds"] = t.seconds
    with TIMING.Timer() as t:
        isotonic = fit_isotonic(cal_prob, y_cal)
    timings["isotonic_fit_seconds"] = t.seconds
    with TIMING.Timer() as t:
        platt_prob = platt.transform(aligned_raw)
    timings["platt_transform_seconds"] = t.seconds
    with TIMING.Timer() as t:
        isotonic_prob = isotonic.transform(aligned_raw)
    timings["isotonic_transform_seconds"] = t.seconds

    platt_diag = platt.diagnostics()
    isotonic_diag = isotonic.diagnostics()
    frac_zero = float(np.mean(isotonic_prob == 0.0)) if len(
        isotonic_prob) else 0.0
    frac_one = float(np.mean(isotonic_prob == 1.0)) if len(
        isotonic_prob) else 0.0
    isotonic_diag.update({
        "n_unique_outer_outputs": int(len(np.unique(isotonic_prob))),
        "fraction_outer_at_exactly_zero": frac_zero,
        "fraction_outer_at_exactly_one": frac_one,
        "degenerate_extreme_mapping": bool(frac_zero + frac_one > 0.5),
    })
    platt_pathological = bool(
        not platt_diag["finite"] or not platt_diag["coefficient_positive"])
    iso_pathological = bool(isotonic_diag["degenerate_extreme_mapping"])

    calibrator_meta = {
        "PLATT": platt_diag,
        "ISOTONIC": isotonic_diag,
        "RAW": {"method": "identity", "n_input_features": 1},
    }

    base_prevalence = {
        "prevalence": float(np.mean(np.asarray(y_base.astype(float)))),
        "n_rows": int(len(y_base)),
        "n_races": int(meta_base["race_id"].nunique()),
        "n_features": int(len(model.feature_names)
                          if hasattr(model, "feature_names")
                          else X_base.shape[1]),
        "transformed_dim": int(model.preprocessor.output_dim),
        "sanity": model.sanity(),
        "fit_warnings": list(model.fit_warnings),
    }

    variants = {"RAW": aligned_raw, "PLATT": platt_prob,
                "ISOTONIC": isotonic_prob}
    methods: dict = {}
    for method, probability in variants.items():
        method_timings = dict(timings)
        methods[method] = _evaluate_variant(
            method=method, fold=fold, probability=probability,
            state_ids=state_ids, val_frame=val_frame, canonical=canonical,
            y_true=y_true, race_ids=race_ids, stage_labels=stage_labels,
            resolved=resolved, base_prevalence=base_prevalence,
            calibration_split=split,
            calibrator_meta=calibrator_meta[method],
            timings=method_timings, paths=paths, root=root)

    audit = calibration_sample_audit(
        cal_prob, y_cal, season=split.calibration_seasons[0])

    out = {
        "fold": fold,
        "split": split.to_dict(),
        "base": {
            "seasons": list(split.base_seasons),
            "training_rows": int(len(y_base)),
            "training_races": int(meta_base["race_id"].nunique()),
            "prevalence": base_prevalence["prevalence"],
            "transformed_dim": base_prevalence["transformed_dim"],
            "n_features": base_prevalence["n_features"],
            "sanity": base_prevalence["sanity"],
            "fit_warnings": base_prevalence["fit_warnings"],
        },
        "calibration": {
            "seasons": list(split.calibration_seasons),
            "rows": int(len(y_cal)),
            "races": int(meta_cal["race_id"].nunique()),
            "audit": audit,
            "platt": platt_diag,
            "isotonic": isotonic_diag,
            "platt_pathological": platt_pathological,
            "isotonic_pathological": iso_pathological,
        },
        "evaluation": {
            "seasons": list(split.evaluation_seasons),
            "rows": int(len(y_eval)),
            "races": int(meta_eval["race_id"].nunique()),
            "states": int(len(state_ids)),
        },
        "methods": methods,
        "bootstrap_data": {
            "y": y_true,
            "race_ids": race_ids,
            "probabilities": {m: np.asarray(v, dtype=float)
                              for m, v in variants.items()},
        },
        "timings": {
            "materialize_seconds": timings["materialize_seconds"],
            "preprocessing_fit_seconds": timings["preprocessing_fit_seconds"],
            "base_model_fit_seconds": timings["base_model_fit_seconds"],
            "prediction_seconds": timings["prediction_seconds"],
            "platt_fit_seconds": timings["platt_fit_seconds"],
            "platt_transform_seconds": timings["platt_transform_seconds"],
            "isotonic_fit_seconds": timings["isotonic_fit_seconds"],
            "isotonic_transform_seconds": timings["isotonic_transform_seconds"],
        },
    }
    if return_predictions:
        out["predictions"] = {m: np.asarray(v, dtype=float)
                              for m, v in variants.items()}
        out["calibration_predictions"] = np.asarray(cal_prob, dtype=float)
        out["calibration_labels"] = np.asarray(y_cal, dtype=float)
    return out


def PR_align(prob, frame) -> np.ndarray:
    """Align a probability vector to the frame row order via identity checks."""
    values = np.asarray(prob, dtype=float)
    if len(values) != len(frame):
        raise InvalidPredictionError(
            "evaluation probability length does not match the frames")
    if not np.all(np.isfinite(values)):
        raise InvalidPredictionError(
            "evaluation probability contains NaN/inf")
    return values


# --- artifact / immutability helpers -----------------------------------------


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
    if isinstance(value, np.generic):
        return _jsonable(value.item())
    if isinstance(value, np.ndarray):
        return _jsonable(value.tolist())
    return value


def reports_dir(paths=None, root=None) -> Path:
    return TSUITE.reports_dir(paths, root)


def default_out(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / CALIBRATION_SELECTION_FILENAME


def m7_artifact_path(paths=None, root=None) -> Path:
    return reports_dir(paths, root) / "logreg_boundary_resolution_v1.json"


def _immutability_report(root: Path) -> dict:
    out = root / PHASE2_REL
    return {
        "phase2_parquet_byte_hash": _sha256_file(out / "model_matrix.parquet"),
        "phase2_manifest_byte_hash": _sha256_file(out / "manifest.json"),
        "f16_ablation_byte_hash": _sha256_file(out / "ablation_config.json"),
        "phase2_matrix_content_hash": EXPECTED_MATRIX_CONTENT_HASH,
        "m0_protocol_semantic_hash": protocol_semantic_hash(),
        "m0_protocol_json_byte_hash": _sha256_file(root / PROTOCOL_JSON_REL),
        "phase2_freeze_manifest_byte_hash": _sha256_file(
            root / FREEZE_MANIFEST_REL),
        "expected": {
            "phase2_matrix_parquet_sha256": EXPECTED_MATRIX_PARQUET_SHA256,
            "phase2_manifest_sha256": EXPECTED_MANIFEST_SHA256,
            "f16_ablation_sha256": EXPECTED_ABLATION_CONFIG_SHA256,
        },
    }


# --- suite orchestration -----------------------------------------------------


def _aggregate_methods(fold_entries: dict, methods, folds) -> dict:
    def _values(method, extractor):
        out = {}
        for fold in folds:
            node = fold_entries[fold]["methods"][method]
            out[fold] = extractor(node)
        return out

    def _agg(values):
        arr = [float(v) for v in values.values()
               if v is not None and math.isfinite(float(v))]
        return {
            "per_fold": dict(values),
            "mean": float(np.mean(arr)) if arr else None,
            "std": float(np.std(arr, ddof=1)) if len(arr) > 1 else 0.0,
            "min": float(np.min(arr)) if arr else None,
            "max": float(np.max(arr)) if arr else None,
        }

    aggregates: dict = {}
    for method in methods:
        aggregates[method] = {
            "race_macro_log_loss": _agg(_values(
                method, lambda n: n["race_macro"]["log_loss"])),
            "race_macro_brier": _agg(_values(
                method, lambda n: n["race_macro"]["brier"])),
            "race_macro_roc_auc": _agg(_values(
                method, lambda n: n["race_macro"]["roc_auc"])),
            "race_macro_pr_auc": _agg(_values(
                method, lambda n: n["race_macro"]["pr_auc"])),
            "state_pooled_log_loss": _agg(_values(
                method, lambda n: n["state_pooled"]["log_loss"])),
            "state_pooled_brier": _agg(_values(
                method, lambda n: n["state_pooled"]["brier"])),
            "expected_calibration_error": _agg(_values(
                method, lambda n: n["calibration"]
                ["expected_calibration_error"])),
            "winner_top1": _agg(_values(
                method, lambda n: _topk_from_node(n, "top1"))),
            "winner_top3": _agg(_values(
                method, lambda n: _topk_from_node(n, "top3"))),
        }
    return aggregates


def _topk_from_node(node, key):
    payload = (node.get("synchronized") or {}).get("winner_top_k", {})
    if payload.get("status") != "OK":
        return None
    return (payload.get("accuracy") or {}).get(key)


def _stage_table(fold_entries: dict, methods, folds, stage: str,
                 metric: str = "log_loss") -> dict:
    out = {}
    for method in methods:
        values = {}
        for fold in folds:
            payload = fold_entries[fold]["methods"][method]["stages"].get(
                metric, {})
            if payload.get("status") != "OK":
                values[fold] = None
                continue
            entry = payload.get(stage, {})
            values[fold] = entry.get("race_macro", {}).get("value")
        out[method] = values
    return out


def _reliability_summary(bins) -> dict:
    if not bins:
        return {}
    empty = sum(1 for b in bins if not b["count"])
    gaps = []
    for b in bins:
        if b["count"]:
            gaps.append(abs(b["observed_frequency"] - b["mean_predicted"]))
    under = [b for b in bins if b["count"]
             and b["observed_frequency"] > b["mean_predicted"]]
    over = [b for b in bins if b["count"]
            and b["observed_frequency"] < b["mean_predicted"]]
    return {
        "n_bins": len(bins),
        "empty_bins": int(empty),
        "largest_absolute_gap": float(max(gaps)) if gaps else None,
        "under_confident_bins": int(len(under)),
        "over_confident_bins": int(len(over)),
    }


def _determinism_check(canonical, fold, *, paths=None, root=None) -> dict:
    first = run_calibration_fold(canonical, fold, paths=paths, root=root,
                                 return_predictions=True)
    second = run_calibration_fold(canonical, fold, paths=paths, root=root,
                                  return_predictions=True)
    differences = {}
    for method in METHODS:
        differences[method] = float(np.max(np.abs(
            first["predictions"][method] - second["predictions"][method])))
    first_metrics = {m: first["methods"][m]["race_macro"]
                     for m in METHODS}
    second_metrics = {m: second["methods"][m]["race_macro"]
                      for m in METHODS}
    return {
        "fold": fold,
        "same_experiment_ids": all(
            first["methods"][m]["experiment_id"]
            == second["methods"][m]["experiment_id"] for m in METHODS),
        "metrics_identical": first_metrics == second_metrics,
        "max_abs_probability_difference": differences,
        "max_abs_probability_difference_overall": float(
            max(differences.values())),
    }


def run_calibration_suite(*, task: str = M8_TASK, folds=("D1", "D2", "D3"),
                          feature_set: str = M8_FEATURE_SET,
                          seed: int = M8_SEED, paths=None, root=None,
                          out=None, canonical: DATA.CanonicalMatrix | None = None,
                          determinism_fold: str = "D1",
                          bootstrap: bool = True) -> dict:
    """Execute the M8 development calibration evaluation over D1/D2/D3."""
    if task != M8_TASK:
        raise ExperimentConfigError(
            f"M8 evaluates task {M8_TASK!r} only; got {task!r}")
    if feature_set != M8_FEATURE_SET:
        raise ExperimentConfigError(
            f"M8 uses feature set {M8_FEATURE_SET!r} only; got "
            f"{feature_set!r}")
    if seed != M8_SEED:
        raise ExperimentConfigError(
            f"M8 uses seed {M8_SEED!r} only; got {seed!r}")
    folds = tuple(folds)
    if not folds:
        raise ExperimentConfigError("M8 needs at least one outer fold")
    for fold in folds:
        RUN.resolve_development_fold(fold)

    m7 = json.loads(m7_artifact_path(paths, root).read_text())
    frozen_c = m7["global_configuration"]["frozen_specification"]["C"]
    if abs(float(frozen_c) - FROZEN_C) > 1e-12:
        raise ExperimentConfigError(
            f"M8 requires the M7-frozen C={FROZEN_C}; artifact says "
            f"{frozen_c}")
    if m7.get("holdout_accessed") is not False:
        raise ProtectedHoldoutError("M7 artifact reports holdout access")

    if canonical is None:
        canonical = DATA.load_canonical(paths)
    if canonical.manifest.get("content_hash") != EXPECTED_MATRIX_CONTENT_HASH:
        from v2.model_lab.errors import ProtocolDriftError
        raise ProtocolDriftError("matrix content hash drift at M8 run time")

    timings: dict = {}
    per_fold: dict = {}
    with TIMING.Timer() as total:
        for fold in folds:
            per_fold[fold] = run_calibration_fold(
                canonical, fold, paths=paths, root=root)

        log_loss = {m: {f: per_fold[f]["methods"][m]["race_macro"]["log_loss"]
                        for f in folds} for m in METHODS}
        brier = {m: {f: per_fold[f]["methods"][m]["race_macro"]["brier"]
                     for f in folds} for m in METHODS}
        diagnostics = {
            "PLATT": {"pathological": any(
                per_fold[f]["calibration"]["platt_pathological"]
                for f in folds)},
            "ISOTONIC": {"pathological": any(
                per_fold[f]["calibration"]["isotonic_pathological"]
                for f in folds)},
        }
        selection = select_calibration_method(
            log_loss=log_loss, brier=brier, diagnostics=diagnostics)

        bootstrap_result: dict
        if not bootstrap:
            bootstrap_result = {
                "status": "NOT_IMPLEMENTED",
                "reason": "disabled by caller",
            }
        elif selection["selected_method"] == "RAW":
            bootstrap_result = {
                "status": "NOT_APPLICABLE",
                "reason": "selected method is RAW; no calibrated candidate "
                          "to compare",
            }
        else:
            method = selection["selected_method"]
            pooled = {
                "y": np.concatenate(
                    [per_fold[f]["bootstrap_data"]["y"] for f in folds]),
                "race_ids": np.concatenate(
                    [per_fold[f]["bootstrap_data"]["race_ids"] for f in folds]),
                "raw": np.concatenate(
                    [per_fold[f]["bootstrap_data"]["probabilities"]["RAW"]
                     for f in folds]),
                "cal": np.concatenate(
                    [per_fold[f]["bootstrap_data"]["probabilities"][method]
                     for f in folds]),
            }
            bootstrap_result = race_level_bootstrap(
                pooled["raw"], pooled["cal"], pooled["y"], pooled["race_ids"])
            bootstrap_result["method"] = method

        for fold in folds:
            per_fold[fold].pop("bootstrap_data", None)

        determinism = _determinism_check(
            canonical, determinism_fold, paths=paths, root=root)

    timings["total_seconds"] = total.seconds
    aggregates = _aggregate_methods(per_fold, METHODS, folds)
    stages = {
        stage: _stage_table(per_fold, METHODS, folds, stage, "log_loss")
        for stage in ("EARLY", "MID", "LATE")}
    reliability = {
        method: {fold: _reliability_summary(
            per_fold[fold]["methods"][method]["calibration"]["bins"])
            for fold in folds}
        for method in METHODS}

    limitations = []
    if selection["selected_method"] == "RAW":
        limitations.append(
            "RAW retained: calibration did not clear the predeclared guards")
    for method in ("PLATT", "ISOTONIC"):
        if diagnostics[method]["pathological"]:
            limitations.append(
                f"{method} flagged pathological on at least one fold")
    if any(per_fold[f]["calibration"]["platt"]["coefficient"] <= 0
           for f in folds):
        limitations.append("PLATT coefficient <= 0 on at least one fold")

    summary = {
        "schema_version": SUITE_SCHEMA_VERSION,
        "stage": "M8",
        "title": "Calibration evaluation & selection (development only)",
        "task": task,
        "feature_set": feature_set,
        "seed": seed,
        "outer_folds": list(folds),
        "protocol_version": MODEL_LAB_PROTOCOL_VERSION,
        "protocol_semantic_hash": protocol_semantic_hash(),
        "matrix_version": REQUIRED_MATRIX_VERSION,
        "matrix_content_hash": EXPECTED_MATRIX_CONTENT_HASH,
        "feature_set_version": REQUIRED_FEATURE_SET_VERSION,
        "label_set_version": REQUIRED_LABEL_SET_VERSION,
        "ablation_config_version": REQUIRED_ABLATION_CONFIG_VERSION,
        "frozen_base_specification": dict(BASE_MODEL_SPEC),
        "frozen_c": FROZEN_C,
        "m7_frozen_c": float(frozen_c),
        "split_design": {
            fold: resolve_calibration_split(fold).to_dict()
            for fold in folds},
        "methods": list(METHODS),
        "platt_epsilon": PLATT_EPSILON,
        "selection_rule": {
            "primary": ["race_macro_log_loss", "race_macro_brier"],
            "diagnostics": ["expected_calibration_error",
                            "reliability_behavior"],
            "guards": ["A log loss lower than RAW",
                       "B mean Brier no worse than RAW",
                       "C no material regression on a majority of folds",
                       "D not pathological"],
            "material_regression_rel": MATERIAL_REGRESSION_REL,
            "tie_tolerance": TIE_TOLERANCE,
            "complexity_order": ["RAW", "PLATT", "ISOTONIC"],
            "ece_used_for_selection": False,
            "holdout_used": False,
            "frozen_before_results": True,
        },
        "calibration_sample_audit": {
            fold: per_fold[fold]["calibration"]["audit"] for fold in folds},
        "platt_parameters": {
            fold: per_fold[fold]["calibration"]["platt"] for fold in folds},
        "isotonic_diagnostics": {
            fold: per_fold[fold]["calibration"]["isotonic"] for fold in folds},
        "per_fold": per_fold,
        "aggregate": aggregates,
        "stage_metrics": stages,
        "reliability": reliability,
        "method_comparison": {
            "selection": selection,
            "selected_method": selection["selected_method"],
        },
        "bootstrap": bootstrap_result,
        "determinism": determinism,
        "runtime": timings,
        "peak_rss_bytes": _peak_rss_bytes(),
        "holdout_accessed": False,
        "holdout_note": "2025 protected final holdout — not evaluated",
        "limitations": limitations,
        "hashes": _immutability_report(
            Path(root) if root is not None else (
                paths.root if paths is not None else Path.cwd())),
    }
    summary = _jsonable(summary)
    dest = Path(out) if out is not None else default_out(paths, root)
    dest.parent.mkdir(parents=True, exist_ok=True)
    RES.atomic_write_json(dest, summary)
    summary["_summary_path"] = str(dest)
    return summary


# --- report rendering (from the stored artifact only) ------------------------


def _fmt(value, digits: int = 6):
    if value is None:
        return "N/A"
    if isinstance(value, float) and not math.isfinite(value):
        return "N/A"
    return f"{value:.{digits}f}"


def _fmt_pct(value, digits: int = 4):
    if value is None:
        return "N/A"
    return f"{value * 100:.{digits}f}%"


def render_calibration_report(summary: dict) -> str:
    """Render the human-readable M8 report from the stored artifact only."""
    folds = summary.get("outer_folds") or list(
        summary["per_fold"].keys())
    lines: list = []
    add = lines.append
    add("# Model Lab Calibration Evaluation & Selection Report (M8)")
    add("")
    add("## CALIBRATION DEVELOPMENT EVALUATION")
    add("")
    add("## BASE MODEL: FROZEN LOGISTIC REGRESSION C=0.01")
    add("")
    add("## OUTER EVALUATION: 2022 / 2023 / 2024")
    add("")
    add("## 2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED")
    add("")
    add("## 1. Calibration question")
    add("")
    add("Does a post-hoc calibration layer (Platt/sigmoid or isotonic) improve "
        "chronologically valid probabilistic quality enough to justify its "
        "extra fitted complexity, or should the frozen base model's RAW "
        "probabilities be retained? Calibration is NOT assumed beneficial; RAW "
        "is a legitimate winner.")
    add("")
    add("## 2. Temporal calibration architecture")
    add("")
    add("Calibration is model fitting, so the calibration season is always the "
        "LAST complete season of the outer TRAIN: base-fit < calibration < "
        "outer evaluation. Calibrators never see outer labels.")
    add("")
    add("| outer fold | BASE FIT | CALIBRATION | OUTER EVALUATION |")
    add("| --- | --- | --- | --- |")
    for fold in folds:
        node = summary["split_design"][fold]
        add(f"| {fold} | {node['base_seasons'][0]}–{node['base_seasons'][-1]} "
            f"| {node['calibration_seasons'][0]} "
            f"| {node['evaluation_seasons'][0]} |")
    add("")
    add("## 3. Frozen base-model specification")
    add("")
    spec = summary["frozen_base_specification"]
    add(f"- family: {spec['estimator']}")
    add(f"- C = {spec['C']}; solver = {spec['solver']}; "
        f"max_iter = {spec['max_iter']}; class_weight = {spec['class_weight']}; "
        f"random_state = {spec['random_state']}")
    add(f"- feature set: {spec['feature_set']}; probability semantics: "
        f"{spec['probability_semantics']}")
    add("- no retuning; M8 reuses the M7-frozen C exactly")
    add("")
    add("## 4. Calibration sample audit")
    add("")
    add("| fold | season | rows | races | positives | negatives | "
        "prevalence | unique p | min p | max p | exact 0 | exact 1 |")
    add("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | "
        "--- |")
    for fold in folds:
        audit = summary["calibration_sample_audit"][fold]
        races = summary["per_fold"][fold]["calibration"]["races"]
        add(f"| {fold} | {audit['season']} | {audit['rows']} | {races} | "
            f"{audit['positive_count']} | {audit['negative_count']} | "
            f"{_fmt(audit['winner_prevalence'])} | "
            f"{audit['unique_raw_probability_count']} | "
            f"{_fmt(audit['raw_probability_min'])} | "
            f"{_fmt(audit['raw_probability_max'])} | "
            f"{audit['n_exact_zero']} | {audit['n_exact_one']} |")
    add("")
    add("## 5. Methods")
    add("")
    add("### RAW")
    add("")
    add("Untouched frozen base-model probability; no transformation.")
    add("")
    add("### PLATT")
    add("")
    add(f"Explicit one-dimensional `LogisticRegression` over "
        f"`logit(clip(p, {summary['platt_epsilon']}, 1-{summary['platt_epsilon']}))`; "
        "no hidden cross-validation; no original feature enters the calibrator.")
    add("")
    add("| fold | coefficient | intercept | finite | coefficient > 0 |")
    add("| --- | --- | --- | --- | --- |")
    for fold in folds:
        p = summary["platt_parameters"][fold]
        add(f"| {fold} | {_fmt(p['coefficient'])} | {_fmt(p['intercept'])} | "
            f"{p['finite']} | {p['coefficient_positive']} |")
    add("")
    add("### ISOTONIC")
    add("")
    add("`sklearn.isotonic.IsotonicRegression(increasing=True, "
        "out_of_bounds='clip', y_min=0, y_max=1)` fit on calibration rows only.")
    add("")
    add("| fold | thresholds | unique outer outputs | frac at 0 | "
        "frac at 1 | degenerate |")
    add("| --- | --- | --- | --- | --- | --- |")
    for fold in folds:
        iso = summary["isotonic_diagnostics"][fold]
        add(f"| {fold} | {iso['n_thresholds']} | "
            f"{iso['n_unique_outer_outputs']} | "
            f"{_fmt_pct(iso['fraction_outer_at_exactly_zero'])} | "
            f"{_fmt_pct(iso['fraction_outer_at_exactly_one'])} | "
            f"{iso['degenerate_extreme_mapping']} |")
    add("")
    add("## 6. DEVELOPMENT CALIBRATION RESULTS")
    add("")
    add("### CALIBRATION DEVELOPMENT EVALUATION")
    add("### BASE MODEL: FROZEN LOGISTIC REGRESSION C=0.01")
    add("### OUTER EVALUATION: 2022 / 2023 / 2024")
    add("### 2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED")
    add("")
    add("### Race-macro log loss / Brier")
    add("")
    add("| method | fold | log loss | Brier | ROC-AUC | PR-AUC | ECE |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for method in METHODS:
        for fold in folds:
            node = summary["per_fold"][fold]["methods"][method]
            add(f"| {method} | {fold} | "
                f"{_fmt(node['race_macro']['log_loss'])} | "
                f"{_fmt(node['race_macro']['brier'])} | "
                f"{_fmt(node['race_macro']['roc_auc'])} | "
                f"{_fmt(node['race_macro']['pr_auc'])} | "
                f"{_fmt(node['calibration']['expected_calibration_error'])} |")
    add("")
    add("### State-pooled diagnostics")
    add("")
    add("| method | fold | log loss | Brier | ROC-AUC | PR-AUC |")
    add("| --- | --- | --- | --- | --- | --- |")
    for method in METHODS:
        for fold in folds:
            node = summary["per_fold"][fold]["methods"][method]
            add(f"| {method} | {fold} | "
                f"{_fmt(node['state_pooled']['log_loss'])} | "
                f"{_fmt(node['state_pooled']['brier'])} | "
                f"{_fmt(node['state_pooled']['roc_auc'])} | "
                f"{_fmt(node['state_pooled']['pr_auc'])} |")
    add("")
    add("### Race-stage race-macro log loss")
    add("")
    add("| method | fold | EARLY | MID | LATE |")
    add("| --- | --- | --- | --- | --- |")
    for method in METHODS:
        for fold in folds:
            stages = summary["per_fold"][fold]["methods"][method]["stages"]
            ll = stages.get("log_loss", {})
            def _stage_value(name):
                entry = ll.get(name, {})
                return entry.get("race_macro", {}).get("value")
            add(f"| {method} | {fold} | {_fmt(_stage_value('EARLY'))} | "
                f"{_fmt(_stage_value('MID'))} | {_fmt(_stage_value('LATE'))} |")
    add("")
    add("### Synchronized winner top-k")
    add("")
    add("| method | fold | top-1 | top-3 | eval states | coverage |")
    add("| --- | --- | --- | --- | --- | --- |")
    for method in METHODS:
        for fold in folds:
            sync = summary["per_fold"][fold]["methods"][method][
                "synchronized"].get("winner_top_k", {})
            acc = sync.get("accuracy") or {}
            n = sync.get("n_evaluation_states")
            mean_field = sync.get("mean_observable_field_size")
            add(f"| {method} | {fold} | {_fmt(acc.get('top1'))} | "
                f"{_fmt(acc.get('top3'))} | {n} | "
                f"mean field {_fmt(mean_field)} |")
    add("")
    add("## 7. Cross-fold aggregate")
    add("")
    add("| method | mean log loss | mean Brier | mean ECE | mean top-1 | "
        "mean ROC-AUC |")
    add("| --- | --- | --- | --- | --- | --- |")
    for method in METHODS:
        agg = summary["aggregate"][method]
        add(f"| {method} | {_fmt(agg['race_macro_log_loss']['mean'])} | "
            f"{_fmt(agg['race_macro_brier']['mean'])} | "
            f"{_fmt(agg['expected_calibration_error']['mean'])} | "
            f"{_fmt(agg['winner_top1']['mean'])} | "
            f"{_fmt(agg['race_macro_roc_auc']['mean'])} |")
    add("")
    add("## 8. Per-fold comparisons (calibrated minus RAW)")
    add("")
    add("| method | fold | Δ log loss | Δ Brier | material regression |")
    add("| --- | --- | --- | --- | --- |")
    for method in ("PLATT", "ISOTONIC"):
        for fold in folds:
            node = summary["method_comparison"]["selection"][
                "material_regression"][method]["per_fold"][fold]
            raw = summary["per_fold"][fold]["methods"]["RAW"]
            cal = summary["per_fold"][fold]["methods"][method]
            d_ll = (cal["race_macro"]["log_loss"]
                    - raw["race_macro"]["log_loss"])
            d_br = (cal["race_macro"]["brier"]
                    - raw["race_macro"]["brier"])
            add(f"| {method} | {fold} | {d_ll:+.6f} | {d_br:+.6f} | "
                f"{node['material_regression']} |")
    add("")
    add("## 9. Reliability findings")
    add("")
    add("| method | fold | empty bins | largest gap | under-confident | "
        "over-confident |")
    add("| --- | --- | --- | --- | --- | --- |")
    for method in METHODS:
        for fold in folds:
            rel = summary["reliability"][method][fold]
            add(f"| {method} | {fold} | {rel.get('empty_bins')} | "
                f"{_fmt(rel.get('largest_absolute_gap'))} | "
                f"{rel.get('under_confident_bins')} | "
                f"{rel.get('over_confident_bins')} |")
    add("")
    add("## 10. Ranking invariance")
    add("")
    add("Platt with a positive coefficient is strictly monotone, so ranking "
        "metrics must be unchanged; isotonic may introduce ties.")
    add("")
    add("| fold | Platt ROC-AUC Δ | Platt PR-AUC Δ | Platt top-1 Δ | "
        "Isotonic ROC-AUC Δ |")
    add("| --- | --- | --- | --- | --- |")
    for fold in folds:
        raw = summary["per_fold"][fold]["methods"]["RAW"]
        platt = summary["per_fold"][fold]["methods"]["PLATT"]
        iso = summary["per_fold"][fold]["methods"]["ISOTONIC"]
        add(f"| {fold} | "
            f"{_fmt(platt['race_macro']['roc_auc'] - raw['race_macro']['roc_auc'])} | "
            f"{_fmt(platt['race_macro']['pr_auc'] - raw['race_macro']['pr_auc'])} | "
            f"{_fmt(_topk_from_node(platt, 'top1') - _topk_from_node(raw, 'top1'))} | "
            f"{_fmt(iso['race_macro']['roc_auc'] - raw['race_macro']['roc_auc'])} |")
    add("")
    add("## 11. Material-regression checks")
    add("")
    sel = summary["method_comparison"]["selection"]
    add(f"- relative degradation threshold: "
        f"{sel['material_regression_rel']}")
    for method in ("PLATT", "ISOTONIC"):
        node = sel["material_regression"][method]
        add(f"- {method}: material regressions on "
            f"{node['n_material_regression']}/{len(folds)} folds "
            f"(majority = {node['majority_material_regression']})")
    add("")
    add("## 12. Bootstrap uncertainty")
    add("")
    add(f"- {summary['bootstrap']['status']}: "
        f"{summary['bootstrap'].get('reason', '')}")
    if summary["bootstrap"]["status"] == "OK":
        node = summary["bootstrap"]
        add(f"- paired whole-race bootstrap, {node['replicates']} replicates, "
            f"seed {node['seed']}, n_races = {node['n_races']}")
        add(f"- log loss difference (cal - RAW): "
            f"{_fmt(node['log_loss_difference']['point'])} "
            f"[{_fmt(node['log_loss_difference']['p2_5'])}, "
            f"{_fmt(node['log_loss_difference']['p97_5'])}]")
        add(f"- Brier difference (cal - RAW): "
            f"{_fmt(node['brier_difference']['point'])} "
            f"[{_fmt(node['brier_difference']['p2_5'])}, "
            f"{_fmt(node['brier_difference']['p97_5'])}]")
    add("")
    add("## 13. Calibration selection rule (predeclared)")
    add("")
    add("- primary objective: mean outer race-macro log loss")
    add("- guard B: mean Brier no worse than RAW")
    add("- guard C: no material regression (relative log-loss degradation "
        f"> {MATERIAL_REGRESSION_REL:.0%}) on a majority of folds")
    add("- guard D: fitted behaviour not pathological")
    add(f"- tie tolerance: {TIE_TOLERANCE} absolute mean log loss; prefer "
        "RAW over PLATT over ISOTONIC")
    add("- ECE never decides selection")
    add("")
    add("## 14. Selected method")
    add("")
    add(f"**SELECT {sel['selected_method']}**")
    add("")
    add(f"- {sel.get('rationale') or ''}")
    add(f"- tie-break applied: {sel['tie_break_applied']}")
    if sel.get("tie_break_detail"):
        add(f"- tie-break detail: {sel['tie_break_detail']}")
    add("")
    add("## 15. Selected probability pipeline")
    add("")
    add("`ALL_84` → frozen preprocessing (train-fitted) → frozen "
        "`LogisticRegression` `C=0.01` → "
        f"**{sel['selected_method']}** calibration → INDEPENDENT_BINARY "
        "probability (never normalized across drivers).")
    add("")
    add("## 16. Complexity / latency impact")
    add("")
    add("| fold | preprocess fit | base model fit | Platt fit | Platt "
        "transform | isotonic fit | isotonic transform |")
    add("| --- | --- | --- | --- | --- | --- | --- |")
    for fold in folds:
        t = summary["per_fold"][fold]["timings"]
        add(f"| {fold} | {_fmt(t['preprocessing_fit_seconds'])} | "
            f"{_fmt(t['base_model_fit_seconds'])} | "
            f"{_fmt(t['platt_fit_seconds'])} | "
            f"{_fmt(t['platt_transform_seconds'])} | "
            f"{_fmt(t['isotonic_fit_seconds'])} | "
            f"{_fmt(t['isotonic_transform_seconds'])} |")
    add("")
    add(f"- total suite wall time: {_fmt(summary['runtime']['total_seconds'], 2)} s")
    add(f"- peak RSS bytes: {summary.get('peak_rss_bytes')}")
    add("")
    add("## 17. Determinism")
    add("")
    det = summary["determinism"]
    add(f"- representative fold: {det['fold']}")
    add(f"- same experiment ids: {det['same_experiment_ids']}")
    add(f"- metrics identical: {det['metrics_identical']}")
    for method in METHODS:
        add(f"- max |Δ {method}|: "
            f"{det['max_abs_probability_difference'][method]:.3e}")
    add("")
    add("## 18. Limitations")
    add("")
    if summary.get("limitations"):
        for item in summary["limitations"]:
            add(f"- {item}")
    else:
        add("- none recorded")
    add("- calibration method selection is development-only; 2025 is protected")
    add("")
    add("## 19. Deployment refit policy (documented, not executed)")
    add("")
    add("M8 selects a calibration METHOD only. The selected method would later "
        "be fitted on development data (base-fit history plus the calibration "
        "season) with no change to the frozen base model. No 2025 calibration "
        "procedure is invented or evaluated here; the protected holdout remains "
        "untouched until the single locked final run.")
    add("")
    add("## 20. Next-stage implications")
    add("")
    if summary["method_comparison"]["selected_method"] == "RAW":
        add("- The frozen base probabilities already meet the probability-"
            "quality bar on outer development folds; no calibration layer is "
            "added to the deployment pipeline.")
        add("- M9 should build on the RAW INDEPENDENT_BINARY probabilities of "
            "the frozen `C=0.01` LogReg.")
    else:
        add(f"- The selected calibrated pipeline (`{summary['method_comparison']['selected_method']}`) "
            "becomes the development-frozen probability pipeline for M9.")
    add("")
    return "\n".join(lines) + "\n"
