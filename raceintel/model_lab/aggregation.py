"""Metric aggregation: race-macro (headline) vs state-pooled, and folds.

Race-macro gives every race equal weight regardless of how many state rows
it contributes; state-pooled is the diagnostic that weights states directly.
They are reported as explicitly different scopes. Fold aggregation reports
each fold plus mean/dispersion — never a single pooled validation number.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from raceintel.model_lab.errors import UnsupportedMetricError
from raceintel.model_lab.metrics import METRIC_FUNCTIONS


def _metric_fn(metric):
    if callable(metric):
        return metric
    if metric in METRIC_FUNCTIONS:
        return METRIC_FUNCTIONS[metric]
    raise UnsupportedMetricError(
        f"metric {metric!r} is not a row-level Model-Lab metric; known: "
        f"{sorted(METRIC_FUNCTIONS)}")


def _is_defined(value) -> bool:
    return value is not None and not (
        isinstance(value, float) and math.isnan(value))


def _as_frame(y_true, y_pred, race_ids) -> pd.DataFrame:
    y = np.asarray(y_true, dtype=float)
    p = np.asarray(y_pred, dtype=float)
    r = np.asarray(race_ids)
    if not (len(y) == len(p) == len(r)):
        raise ValueError("y_true / y_pred / race_ids length mismatch")
    return pd.DataFrame({"y": y, "p": p, "race_id": r})


def race_macro(y_true, y_pred, race_ids, metric) -> dict:
    """Equal-per-race mean of a row metric (headline scope)."""
    fn = _metric_fn(metric)
    frame = _as_frame(y_true, y_pred, race_ids)
    per_race = {}
    defined = []
    for race_id, group in frame.groupby("race_id", sort=False):
        value = fn(group["y"].to_numpy(), group["p"].to_numpy())
        if _is_defined(value):
            per_race[str(race_id)] = float(value)
            defined.append(float(value))
        else:
            per_race[str(race_id)] = None
    name = metric if isinstance(metric, str) else "custom"
    return {
        "scope": "race_macro", "metric": name,
        "value": float(np.mean(defined)) if defined else float("nan"),
        "n_races": int(len(per_race)), "n_races_defined": int(len(defined)),
        "n_states": int(len(frame)), "per_race": per_race,
    }


def state_pooled(y_true, y_pred, race_ids, metric) -> dict:
    """Diagnostic row-level metric over all states (state-weighted)."""
    fn = _metric_fn(metric)
    frame = _as_frame(y_true, y_pred, race_ids)
    value = fn(frame["y"].to_numpy(), frame["p"].to_numpy())
    name = metric if isinstance(metric, str) else "custom"
    return {
        "scope": "state_pooled", "metric": name,
        "value": float(value) if _is_defined(value) else float("nan"),
        "n_states": int(len(frame)),
    }


def scoped_metric(y_true, y_pred, race_ids, metric) -> dict:
    """Both scopes for one metric (race_macro is the headline)."""
    return {
        "metric": metric if isinstance(metric, str) else "custom",
        "race_macro": race_macro(y_true, y_pred, race_ids, metric),
        "state_pooled": state_pooled(y_true, y_pred, race_ids, metric),
    }


def aggregate_folds(per_fold: dict) -> dict:
    """Summarize a metric across folds: per-fold + mean/std/min/max."""
    values = [v for v in per_fold.values() if _is_defined(v)]
    arr = np.asarray(values, dtype=float)
    return {
        "per_fold": dict(per_fold),
        "n_folds": int(len(per_fold)),
        "n_defined": int(len(values)),
        "mean": float(arr.mean()) if len(arr) else float("nan"),
        "std": float(arr.std(ddof=1)) if len(arr) > 1 else 0.0,
        "min": float(arr.min()) if len(arr) else float("nan"),
        "max": float(arr.max()) if len(arr) else float("nan"),
        "range": (float(arr.max() - arr.min()) if len(arr) else float("nan")),
    }


def stage_scoped_metrics(stages, y_true, y_pred, race_ids, metric,
                         *, stage_order=("EARLY", "MID", "LATE")) -> dict:
    """Race-macro metric separately for each race stage."""
    stages = np.asarray(stages)
    race_ids = np.asarray(race_ids)
    out = {}
    for stage in stage_order:
        mask = stages == stage
        if not mask.any():
            out[stage] = {"metric": metric, "n_states": 0, "race_macro": {
                "scope": "race_macro", "metric": metric, "value": float("nan"),
                "n_races": 0, "n_races_defined": 0, "n_states": 0,
                "per_race": {}}}
            continue
        out[stage] = {
            "metric": metric,
            "n_states": int(mask.sum()),
            "race_macro": race_macro(
                np.asarray(y_true)[mask], np.asarray(y_pred)[mask],
                race_ids[mask], metric),
        }
    return out
