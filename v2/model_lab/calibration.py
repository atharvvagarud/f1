"""Calibration *evaluation* utilities (reliability bins, ECE).

Reliability bins and expected calibration error under the frozen M0 policy:
10 equal-width bins over [0, 1]. Calibrator *fitting* (M8 Platt/isotonic lives
in :mod:`v2.model_lab.calibration_selection`) is deliberately separate from
these read-only evaluation helpers.
"""

from __future__ import annotations

import numpy as np

from v2.model_lab.metrics import validate_binary_target, validate_probabilities
from v2.model_lab.protocol import ECE_N_BINS


def _bin_indices(prob: np.ndarray, n_bins: int) -> np.ndarray:
    idx = np.floor(prob * n_bins).astype(int)
    return np.clip(idx, 0, n_bins - 1)


def reliability_bins(y_true, prob, *, n_bins: int = ECE_N_BINS) -> tuple:
    y = validate_binary_target(y_true)
    p = validate_probabilities(prob)
    if len(y) != len(p):
        raise ValueError("target/prediction length mismatch")
    if n_bins < 1:
        raise ValueError("n_bins must be >= 1")
    idx = _bin_indices(p, n_bins)
    edges = np.linspace(0.0, 1.0, n_bins + 1)
    bins = []
    for b in range(n_bins):
        mask = idx == b
        count = int(mask.sum())
        if count:
            mean_pred = float(p[mask].mean())
            observed = float(y[mask].mean())
        else:
            mean_pred = None
            observed = None
        bins.append({
            "bin": b, "lo": float(edges[b]), "hi": float(edges[b + 1]),
            "count": count, "mean_predicted": mean_pred,
            "observed_frequency": observed,
            "weight": count / len(y) if len(y) else 0.0,
        })
    return tuple(bins)


def expected_calibration_error(y_true, prob, *,
                               n_bins: int = ECE_N_BINS) -> float:
    y = validate_binary_target(y_true)
    p = validate_probabilities(prob)
    if len(y) == 0:
        return float("nan")
    bins = reliability_bins(y, p, n_bins=n_bins)
    total = len(y)
    ece = 0.0
    for entry in bins:
        if entry["count"]:
            ece += (entry["count"] / total) * abs(
                entry["observed_frequency"] - entry["mean_predicted"])
    return float(ece)


def calibration_report(y_true, prob, *, n_bins: int = ECE_N_BINS) -> dict:
    from v2.model_lab.metrics import brier
    return {
        "n": int(len(validate_probabilities(prob))),
        "n_bins": n_bins,
        "binning": "equal_width",
        "brier": brier(y_true, prob),
        "expected_calibration_error": expected_calibration_error(
            y_true, prob, n_bins=n_bins),
        "bins": list(reliability_bins(y_true, prob, n_bins=n_bins)),
    }
