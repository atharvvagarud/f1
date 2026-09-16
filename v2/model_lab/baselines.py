"""M0 non-ML prediction baselines.

Baselines are deterministic prediction *generators*, not trained estimators.
Each declares supported tasks, required factual columns, train dependence and
output semantics. They never touch 2025 (callers pass development frames).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
import pandas as pd

from v2.model_lab.errors import (
    ExperimentConfigError,
    UnknownBaselineError,
)
from v2.model_lab.predictions import (
    PredictionKind,
    PredictionResult,
    ProbabilitySemantics,
)
from v2.model_lab.tasks import resolve_task

#: Factual points-paying cutoff for the frozen rich era (2018-2025): top 10.
FROZEN_ERA_POINTS_CUTOFF = 10


def _require_columns(baseline: str, frame: pd.DataFrame,
                     columns: tuple) -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise ExperimentConfigError(
            f"baseline {baseline!r} requires columns {list(columns)}; "
            f"missing {missing}")


def _as_float(series: pd.Series) -> np.ndarray:
    return series.astype(float).to_numpy()


def _binary_result(frame: pd.DataFrame, mask, task: str) -> PredictionResult:
    semantics = (ProbabilitySemantics.INDEPENDENT_BINARY
                 if task == "winner"
                 else ProbabilitySemantics.POSITIVE_CLASS_PROBABILITY)
    return PredictionResult(
        kind=PredictionKind.BINARY_PROBABILITY,
        state_ids=tuple(frame["state_id"]),
        values=np.asarray(mask, dtype=float),
        semantics=semantics, positive_class=1)


def _value_result(frame: pd.DataFrame, values,
                  kind: PredictionKind) -> PredictionResult:
    return PredictionResult(kind=kind, state_ids=tuple(frame["state_id"]),
                            values=np.asarray(values, dtype=float))


def _current_leader_gen(task, train_frame, validation_frame, train_y):
    def one(frame):
        _require_columns("CURRENT_LEADER", frame, ("position",))
        pos = _as_float(frame["position"])
        return _binary_result(frame, pos == 1.0, task)
    return one(train_frame), one(validation_frame)


def _current_order_gen(task, train_frame, validation_frame, train_y):
    resolved = resolve_task(task)

    def mask_for(frame):
        _require_columns("CURRENT_ORDER", frame, ("position",))
        pos = _as_float(frame["position"])
        if task == "winner":
            return pos == 1.0
        if task == "podium":
            return pos <= 3.0
        return pos <= FROZEN_ERA_POINTS_CUTOFF

    def one(frame):
        if resolved.is_binary:
            return _binary_result(frame, mask_for(frame), task)
        return _value_result(frame, _as_float(frame["position"]),
                             PredictionKind.ORDINAL_PREDICTION)
    return one(train_frame), one(validation_frame)


def _grid_pole_gen(task, train_frame, validation_frame, train_y):
    resolved = resolve_task(task)

    def one(frame):
        _require_columns("GRID_POLE", frame, ("grid_position",))
        grid = _as_float(frame["grid_position"])
        if resolved.is_binary:
            if task == "winner":
                mask = grid == 1.0
            elif task == "podium":
                mask = grid <= 3.0
            else:
                mask = grid <= FROZEN_ERA_POINTS_CUTOFF
            return _binary_result(frame, mask, task)
        return _value_result(frame, grid, PredictionKind.ORDINAL_PREDICTION)
    return one(train_frame), one(validation_frame)


def _recent_pace_gen(task, train_frame, validation_frame, train_y):
    def one(frame):
        _require_columns("RECENT_PACE", frame,
                         ("representative_recent_pace_s",))
        pace = _as_float(frame["representative_recent_pace_s"])
        return _value_result(frame, -pace, PredictionKind.RANKING_SCORE)
    return one(train_frame), one(validation_frame)


def _class_prior_gen(task, train_frame, validation_frame, train_y):
    """Constant train-prevalence probability (train-only).

    M2 HANDOFF CONTRACT: ``train_y`` MUST be ``ExperimentDataset.y_train``
    (the materialized training target for this fold/task) — never validation,
    holdout, or pooled targets. This factory cannot independently prove the
    provenance of the array it receives, so the M2 runner owns correct
    train/validation materialization and must pass only the training target.
    """
    if train_y is None:
        raise ExperimentConfigError(
            "CLASS_PRIOR requires the training target to derive prevalence")
    resolved = resolve_task(task)
    y = np.asarray(train_y, dtype=float)
    if len(y) == 0:
        raise ExperimentConfigError("CLASS_PRIOR needs non-empty training rows")
    prevalence = float(np.mean(y))
    semantics = (ProbabilitySemantics.INDEPENDENT_BINARY
                 if task == "winner"
                 else ProbabilitySemantics.POSITIVE_CLASS_PROBABILITY)

    def one(frame):
        values = np.full(len(frame), prevalence, dtype=float)
        return PredictionResult(
            kind=PredictionKind.BINARY_PROBABILITY,
            state_ids=tuple(frame["state_id"]), values=values,
            semantics=semantics, positive_class=1)
    return one(train_frame), one(validation_frame)


@dataclass(frozen=True)
class Baseline:
    name: str
    supported_tasks: tuple
    required_columns: tuple
    train_dependence: bool
    output: str
    description: str
    generator: Callable

    def generate(self, task: str, train_frame: pd.DataFrame,
                 validation_frame: pd.DataFrame, train_y=None) -> tuple:
        if task not in self.supported_tasks:
            raise ExperimentConfigError(
                f"baseline {self.name!r} does not support task {task!r}; "
                f"supported: {list(self.supported_tasks)}")
        return self.generator(task, train_frame, validation_frame, train_y)


BASELINES: tuple = (
    Baseline(
        "CURRENT_LEADER", ("winner", "podium", "points"), ("position",),
        False, "binary probability (winner: INDEPENDENT_BINARY)",
        "Predict the current race leader as the winner.",
        _current_leader_gen),
    Baseline(
        "CURRENT_ORDER", ("winner", "podium", "points"), ("position",),
        False, "binary probability (winner: INDEPENDENT_BINARY)",
        "Assume the current running order is the final order.",
        _current_order_gen),
    Baseline(
        "GRID_POLE", ("winner", "podium", "points", "final_position"),
        ("grid_position",), False,
        "binary probability / ordinal finish from grid",
        "Pre-race: pole wins; order by grid position.",
        _grid_pole_gen),
    Baseline(
        "RECENT_PACE", ("winner", "podium", "points"),
        ("representative_recent_pace_s",), False,
        "ranking score (NOT a probability)",
        "Rank by factual recent representative pace available at state time.",
        _recent_pace_gen),
    Baseline(
        "CLASS_PRIOR", ("winner", "podium", "points", "gain", "loss"), (),
        True, "constant train-prevalence binary probability",
        "Constant probability equal to the training prevalence. "
        "M2 handoff: train_y MUST be ExperimentDataset.y_train only.",
        _class_prior_gen),
)

BASELINES_BY_NAME: dict = {b.name: b for b in BASELINES}
BASELINE_NAMES: tuple = tuple(b.name for b in BASELINES)


def get_baseline(name: str) -> Baseline:
    if name not in BASELINES_BY_NAME:
        raise UnknownBaselineError(
            f"unknown baseline {name!r}; known: {list(BASELINE_NAMES)}")
    return BASELINES_BY_NAME[name]


def run_baseline(name: str, task: str, train_frame: pd.DataFrame,
                 validation_frame: pd.DataFrame, train_y=None) -> tuple:
    """Return (train_prediction, validation_prediction) for a baseline.

    For CLASS_PRIOR, ``train_y`` MUST be ``ExperimentDataset.y_train`` (see
    the M2 handoff contract on the generator); the runner owns provenance.
    """
    return get_baseline(name).generate(
        task, train_frame, validation_frame, train_y)
