"""M6 deterministic expanding-window INNER temporal splits.

Tuning must live entirely inside each OUTER training history. This module
resolves, for a development outer fold (D1/D2/D3), a deterministic set of
chronology-preserving inner folds built from the outer-training seasons only:

- seasons are used as whole units (whole races, never row-level splits);
- the inner validation season is always strictly later than every inner
  training season;
- every inner season is drawn from the outer TRAIN seasons, so the outer
  validation season and the protected 2025 holdout are unreachable;
- the expansion rule is fixed and deterministic (no randomization, no
  ordering from filesystem/row order).

Rule (fixed before observing any tuning result): the first inner fold trains
on the first ``MIN_INNER_TRAIN_SEASONS`` (3) outer-training seasons and
validates on the next one; each subsequent fold adds exactly one training
season. Requiring three seasons of history is the largest scientifically
defensible set available for D1 (2018-2021) and matches the frozen conceptual
example for D3. One or two seasons is not a defensible base for a rare-event
winner model on 84 features.

Resulting inner folds (documented, asserted in tests):

- D1 outer TRAIN 2018-2021:
    I1 train 2018-2020 -> validate 2021
- D2 outer TRAIN 2018-2022:
    I1 train 2018-2020 -> validate 2021
    I2 train 2018-2021 -> validate 2022
- D3 outer TRAIN 2018-2023:
    I1 train 2018-2020 -> validate 2021
    I2 train 2018-2021 -> validate 2022
    I3 train 2018-2022 -> validate 2023
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from raceintel.model_lab import data as DATA
from raceintel.model_lab import splits as SPLITS
from raceintel.model_lab.errors import ExperimentConfigError, ProtectedHoldoutError
from raceintel.model_lab.protocol import PROTECTED_HOLDOUT_SEASON
from raceintel.model_lab.tasks import resolve_task

#: Minimum number of outer-training seasons an inner fold must train on.
MIN_INNER_TRAIN_SEASONS = 3

#: Inner folds are defined only for the frozen development outer folds.
INNER_OUTER_FOLDS = ("D1", "D2", "D3")


@dataclass(frozen=True)
class InnerSplit:
    """One chronology-preserving inner fold (TRAIN strictly before VAL)."""

    outer_fold: str
    inner_fold_id: str
    train_seasons: tuple
    validation_seasons: tuple

    def to_dict(self) -> dict:
        return {
            "outer_fold": self.outer_fold,
            "inner_fold_id": self.inner_fold_id,
            "train_seasons": list(self.train_seasons),
            "validation_seasons": list(self.validation_seasons),
        }


def resolve_inner_splits(outer_fold: str) -> tuple:
    """Deterministic inner folds for one development outer fold.

    Derives the fold set from the outer TRAIN seasons carried by the frozen
    M0 split, never from a hardcoded season list.
    """
    if outer_fold not in INNER_OUTER_FOLDS:
        raise ExperimentConfigError(
            f"inner tuning folds exist for {list(INNER_OUTER_FOLDS)} only; "
            f"got {outer_fold!r}")
    outer = SPLITS.get_split(outer_fold)
    if not outer.is_development:
        raise ExperimentConfigError(
            f"{outer_fold}: inner tuning is restricted to development folds")
    seasons = tuple(int(s) for s in outer.train_seasons)
    if len(seasons) <= MIN_INNER_TRAIN_SEASONS:
        raise ExperimentConfigError(
            f"{outer_fold}: {len(seasons)} outer-training seasons cannot "
            f"yield an inner fold with >= {MIN_INNER_TRAIN_SEASONS} training "
            "seasons")
    splits: list = []
    for index, k in enumerate(
            range(MIN_INNER_TRAIN_SEASONS, len(seasons)), start=1):
        train = seasons[:k]
        validation = (seasons[k],)
        split = InnerSplit(outer_fold, f"{outer_fold}-I{index}", train,
                           validation)
        _validate_inner_split(split)
        splits.append(split)
    return tuple(splits)


def _validate_inner_split(split: InnerSplit) -> None:
    if not split.train_seasons or not split.validation_seasons:
        raise ExperimentConfigError(
            f"{split.inner_fold_id}: empty inner train/validation")
    if max(split.train_seasons) >= min(split.validation_seasons):
        raise ExperimentConfigError(
            f"{split.inner_fold_id}: inner train is not strictly before "
            "inner validation")
    for season in (*split.train_seasons, *split.validation_seasons):
        if int(season) == PROTECTED_HOLDOUT_SEASON:
            raise ProtectedHoldoutError(
                f"{split.inner_fold_id}: protected 2025 holdout reached the "
                "inner tuning folds")


def inner_folds_payload(folds=INNER_OUTER_FOLDS) -> dict:
    """Documented inner-fold layout for the machine-readable artifact."""
    return {fold: [s.to_dict() for s in resolve_inner_splits(fold)]
            for fold in folds}


def materialize_seasons(canonical: DATA.CanonicalMatrix, seasons,
                        task_name: str, feature_set: str):
    """Apply the canonical task mask to a season selection.

    Reuses the frozen M1 mask helper so inner tuning sees exactly the same
    eligibility/label/identity semantics as the outer evaluator. Returns
    ``(X_frame, y, metadata)`` for the eligible rows.
    """
    task = resolve_task(task_name)
    features = DATA.resolve_features(feature_set, canonical)
    frame = canonical.select_seasons(seasons)
    _, y, metadata = SPLITS._apply_mask(frame, task)
    X = frame.loc[y.index, list(features)]
    return X, y, metadata


def inner_split_frame(canonical: DATA.CanonicalMatrix, split: InnerSplit,
                      task_name: str, feature_set: str) -> tuple:
    """Materialize inner train/validation sides through the frozen mask."""
    X_train, y_train, meta_train = materialize_seasons(
        canonical, split.train_seasons, task_name, feature_set)
    X_val, y_val, meta_val = materialize_seasons(
        canonical, split.validation_seasons, task_name, feature_set)
    return (X_train, y_train, meta_train, X_val, y_val, meta_val)


def assert_no_holdout_seasons(seasons) -> None:
    seasons = {int(s) for s in seasons}
    if PROTECTED_HOLDOUT_SEASON in seasons:
        raise ProtectedHoldoutError(
            "protected 2025 holdout season reached the tuning path")


def _season_race_keys(canonical: DATA.CanonicalMatrix, seasons) -> set:
    frame = canonical.select_seasons(seasons)
    return set(zip(frame["season"].astype(int), frame["race_id"].astype(str)))


def assert_whole_races(canonical: DATA.CanonicalMatrix,
                       split: InnerSplit) -> None:
    """Inner train/validation share no race; every race is wholly in one."""
    train = _season_race_keys(canonical, split.train_seasons)
    val = _season_race_keys(canonical, split.validation_seasons)
    overlap = train & val
    if overlap:
        raise ExperimentConfigError(
            f"{split.inner_fold_id}: races split across inner train/val: "
            f"{sorted(overlap)[:3]}")
