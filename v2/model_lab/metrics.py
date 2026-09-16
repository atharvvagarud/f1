"""Frozen metric implementations (probability + ordinal/regression).

Dependency-light, hand-verified implementations of the M0 metric set. Log
loss uses a documented fixed epsilon for numerical safety only; the original
probabilities are preserved for every other metric. Slices with a single
class return ``None`` for the rank metrics rather than a fabricated number.
"""

from __future__ import annotations

import numpy as np

from v2.model_lab.errors import (
    InvalidPredictionError,
    UnsupportedMetricError,
)

#: Documented fixed clipping epsilon for log loss (not result-dependent).
LOG_LOSS_EPSILON = 1e-15


def _as_float(values) -> np.ndarray:
    return np.asarray(values, dtype=float)


def validate_binary_target(y_true) -> np.ndarray:
    y = np.asarray(y_true)
    if y.dtype == object or str(y.dtype).startswith("boolean"):
        y = y.astype("boolean")
        if y.isna().any():
            raise InvalidPredictionError("binary target contains nulls")
        y = y.astype(float)
    y = _as_float(y)
    if not np.all(np.isfinite(y)):
        raise InvalidPredictionError("binary target contains NaN/inf")
    if not np.all((y == 0.0) | (y == 1.0)):
        raise InvalidPredictionError("binary target must be exactly 0/1")
    return y


def validate_probabilities(prob) -> np.ndarray:
    p = _as_float(prob)
    if not np.all(np.isfinite(p)):
        raise InvalidPredictionError("probability contains NaN/inf")
    if np.any(p < 0.0) or np.any(p > 1.0):
        raise InvalidPredictionError("probability outside [0, 1]")
    return p


def _binary(y_true, prob) -> tuple:
    y = validate_binary_target(y_true)
    p = validate_probabilities(prob)
    if len(y) != len(p):
        raise InvalidPredictionError("target/prediction length mismatch")
    return y, p


def _binary_score(y_true, score) -> tuple:
    """Binary target + finite ranking score (no [0, 1] requirement)."""
    y = validate_binary_target(y_true)
    s = _as_float(score)
    if not np.all(np.isfinite(s)):
        raise InvalidPredictionError("ranking score contains NaN/inf")
    if len(y) != len(s):
        raise InvalidPredictionError("target/prediction length mismatch")
    return y, s


def binary_logloss(y_true, prob, *, epsilon: float = LOG_LOSS_EPSILON) -> float:
    """Log loss with a fixed epsilon clip; original probabilities untouched."""
    y, p = _binary(y_true, prob)
    if len(y) == 0:
        return float("nan")
    clipped = np.clip(p, epsilon, 1.0 - epsilon)
    return float(-np.mean(y * np.log(clipped)
                          + (1.0 - y) * np.log(1.0 - clipped)))


def brier(y_true, prob) -> float:
    y, p = _binary(y_true, prob)
    if len(y) == 0:
        return float("nan")
    return float(np.mean((p - y) ** 2))


def _average_ranks(values: np.ndarray) -> np.ndarray:
    order = np.argsort(values, kind="mergesort")
    ranks = np.empty(len(values), dtype=float)
    i = 0
    while i < len(values):
        j = i
        while j + 1 < len(values) and values[order[j + 1]] == values[order[i]]:
            j += 1
        avg = (i + j) / 2.0 + 1.0
        for k in range(i, j + 1):
            ranks[order[k]] = avg
        i = j + 1
    return ranks


def roc_auc(y_true, prob):
    """Rank-based ROC-AUC; ``None`` when only one class is present."""
    y, p = _binary_score(y_true, prob)
    n_pos = int(y.sum())
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return None
    ranks = _average_ranks(p)
    return float((ranks[y == 1].sum() - n_pos * (n_pos + 1) / 2.0)
                 / (n_pos * n_neg))


def pr_auc(y_true, prob):
    """Average precision with standard distinct-threshold tie semantics.

    Scores are grouped by distinct value (ties share one threshold step):
    at each group with >= 1 positive, ``(recall - prev_recall) * precision``
    is accumulated from whole-group counts, so the result never depends on
    input order within ties (all-tied scores yield the positive prevalence,
    e.g. 0.5). Parity with ``sklearn.metrics.average_precision_score`` is
    covered by tests; sklearn is deliberately NOT imported here (frozen M0
    non-modeling guard forbids sklearn sources in the Model Lab).
    ``None`` when there are no positives (frozen M1 one-class contract).
    """
    y, p = _binary_score(y_true, prob)
    n_pos = int(y.sum())
    if n_pos == 0:
        return None
    order = np.argsort(-p, kind="mergesort")
    y_sorted = y[order]
    p_sorted = p[order]
    ap = 0.0
    tp = 0.0
    fp = 0.0
    prev_recall = 0.0
    i, n = 0, len(y_sorted)
    while i < n:
        j = i
        while j + 1 < n and p_sorted[j + 1] == p_sorted[i]:
            j += 1
        positives = float(y_sorted[i:j + 1].sum())
        tp += positives
        fp += float(j - i + 1) - positives
        if positives > 0.0:
            recall = tp / n_pos
            ap += (recall - prev_recall) * (tp / (tp + fp))
            prev_recall = recall
        i = j + 1
    return float(ap)


def _finite_pair(y_true, y_pred) -> tuple:
    """Ordinal/regression inputs; fail loudly on NaN/inf (never skip)."""
    y, p = _as_float(y_true), _as_float(y_pred)
    if len(y) != len(p):
        raise InvalidPredictionError("target/prediction length mismatch")
    if not np.all(np.isfinite(y)):
        raise InvalidPredictionError("regression target contains NaN/inf")
    if not np.all(np.isfinite(p)):
        raise InvalidPredictionError("regression prediction contains NaN/inf")
    return y, p


def mae(y_true, y_pred) -> float:
    y, p = _finite_pair(y_true, y_pred)
    if len(y) == 0:
        return float("nan")
    return float(np.mean(np.abs(y - p)))


def rmse(y_true, y_pred) -> float:
    y, p = _finite_pair(y_true, y_pred)
    if len(y) == 0:
        return float("nan")
    return float(np.sqrt(np.mean((y - p) ** 2)))


def spearman(y_true, y_pred):
    """Spearman rank correlation; ``None`` when undefined (constant ranks)."""
    y, p = _finite_pair(y_true, y_pred)
    if len(y) < 2:
        return None
    ry, rp = _average_ranks(y), _average_ranks(p)
    ry = ry - ry.mean()
    rp = rp - rp.mean()
    denom = np.sqrt((ry ** 2).sum() * (rp ** 2).sum())
    if denom == 0.0:
        return None
    return float((ry * rp).sum() / denom)


#: Row-level metric registry (probability + ordinal/regression).
METRIC_FUNCTIONS = {
    "log_loss": binary_logloss,
    "brier": brier,
    "roc_auc": roc_auc,
    "pr_auc": pr_auc,
    "mae": mae,
    "rmse": rmse,
    "spearman": spearman,
}


def compute_metric(name: str, y_true, y_pred):
    if name not in METRIC_FUNCTIONS:
        raise UnsupportedMetricError(
            f"metric {name!r} is not a row-level Model-Lab metric; known: "
            f"{sorted(METRIC_FUNCTIONS)}")
    return METRIC_FUNCTIONS[name](y_true, y_pred)


#: Metrics that require a mutually-exclusive race distribution. Independent
#: binary probabilities are not accepted here.
RACE_DISTRIBUTION_METRICS = ("race_level_log_loss",)

#: Canonical prediction-semantic -> applicable metric names (M1.1). This is
#: the ONE evaluation-boundary guard M2 must consume: raw mathematical
#: primitives (``brier`` etc.) cannot know a value's semantics, so callers
#: holding a ``PredictionResult`` must pass through
#: :func:`require_metric_applicability` (or :func:`evaluate_metric`) instead
#: of calling primitives/``compute_metric`` directly with raw arrays.
BINARY_PROBABILITY_METRICS = frozenset({
    "log_loss", "brier", "roc_auc", "pr_auc",
    "expected_calibration_error", "ece", "calibration_report",
    "reliability_bins",
})
RANKING_SCORE_METRICS = frozenset({"roc_auc", "pr_auc"})
CONTINUOUS_PREDICTION_METRICS = frozenset({"mae", "rmse", "spearman"})
ORDINAL_PREDICTION_METRICS = frozenset({"mae", "rmse", "spearman"})
RACE_DISTRIBUTION_ALLOWED_METRICS = frozenset(RACE_DISTRIBUTION_METRICS)


def require_metric_applicability(kind, metric_name: str) -> None:
    """Fail loudly when ``metric_name`` is invalid for a prediction semantic.

    ``kind`` is a ``PredictionKind`` (or its string value). Unsupported
    combinations raise :class:`UnsupportedMetricError` — they never silently
    compute. In particular a ``RANKING_SCORE`` inside [0, 1] is NOT a
    probability: ``brier``/``log_loss``/calibration are rejected even when
    the raw values would pass range checks.
    """
    from v2.model_lab.predictions import PredictionKind
    try:
        resolved = kind if isinstance(kind, PredictionKind) \
            else PredictionKind(str(kind))
    except ValueError:
        raise UnsupportedMetricError(
            f"unknown prediction kind {kind!r}") from None
    table = {
        PredictionKind.BINARY_PROBABILITY: BINARY_PROBABILITY_METRICS,
        PredictionKind.RANKING_SCORE: RANKING_SCORE_METRICS,
        PredictionKind.CONTINUOUS_PREDICTION:
            CONTINUOUS_PREDICTION_METRICS,
        PredictionKind.ORDINAL_PREDICTION: ORDINAL_PREDICTION_METRICS,
        PredictionKind.MUTUALLY_EXCLUSIVE_RACE_DISTRIBUTION:
            RACE_DISTRIBUTION_ALLOWED_METRICS,
    }
    allowed = table.get(resolved, frozenset())
    if metric_name not in allowed:
        raise UnsupportedMetricError(
            f"metric {metric_name!r} is not applicable to "
            f"{resolved.value}; allowed: {sorted(allowed)}")


def evaluate_metric(prediction, metric_name: str, y_true, y_pred):
    """Guarded evaluation: applicability check first, then dispatch.

    ``prediction`` is a ``PredictionResult`` whose ``kind`` governs which
    metrics may run. Row-level names dispatch to :data:`METRIC_FUNCTIONS`;
    calibration names dispatch to the calibration module; race-distribution
    names fail loudly (no such metric is implemented in M1/M1.1 — do not
    invent one here).
    """
    require_metric_applicability(prediction.kind, metric_name)
    if metric_name in METRIC_FUNCTIONS:
        return METRIC_FUNCTIONS[metric_name](y_true, y_pred)
    if metric_name in ("expected_calibration_error", "ece"):
        from v2.model_lab.calibration import expected_calibration_error
        return expected_calibration_error(y_true, y_pred)
    if metric_name == "calibration_report":
        from v2.model_lab.calibration import calibration_report
        return calibration_report(y_true, y_pred)
    if metric_name == "reliability_bins":
        from v2.model_lab.calibration import reliability_bins
        return reliability_bins(y_true, y_pred)
    raise UnsupportedMetricError(
        f"metric {metric_name!r} is applicable to "
        f"{prediction.kind.value} but is not implemented in M1/M1.1")
