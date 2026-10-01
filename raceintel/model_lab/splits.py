"""Temporal split engine + dataset materialization.

Frozen expanding-window development folds (D1/D2/D3), the FINAL_FIT window
and the protected 2025 holdout. Development paths cannot reach 2025; the
holdout requires explicit intent. Materialization applies the frozen task
mask before selecting X/y and preserves identity metadata.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from raceintel.model_lab.data import (
    IDENTITY_COLUMNS,
    CanonicalMatrix,
    resolve_features,
)
from raceintel.model_lab.errors import (
    ProtectedHoldoutError,
    UnknownFoldError,
)
from raceintel.model_lab.protocol import (
    DEVELOPMENT_FOLDS,
    PROTECTED_HOLDOUT_SEASON,
)
from raceintel.model_lab.tasks import ResolvedTask, resolve_task

DEVELOPMENT_FOLD_IDS = tuple(f.fold_id for f in DEVELOPMENT_FOLDS)
FINAL_FIT_ID = "FINAL_FIT"
HOLDOUT_ID = "HOLDOUT"
ALL_FOLD_IDS = DEVELOPMENT_FOLD_IDS + (FINAL_FIT_ID, HOLDOUT_ID)

#: M0 audit evidence (docs/generated/model_lab_split_audit_v1.json):
#: fold_id -> (train_states, validation_states).
M0_FOLD_STATE_COUNTS = {
    "D1": (88123, 23577),
    "D2": (111700, 24422),
    "D3": (136122, 26606),
}

#: fold_id -> side -> task -> (eligible, positives|None). From the M0 audit.
M0_FOLD_TASK_COUNTS = {
    "D1": {
        "train": {
            "winner": (88123, 4862), "podium": (88123, 14584),
            "points": (88123, 48458), "final_position": (82372, None),
            "gain": (87971, 35116), "loss": (87971, 24832),
            "position_change": (87971, None)},
        "validation": {
            "winner": (23577, 1295), "podium": (23577, 3883),
            "points": (23577, 12926), "final_position": (22087, None),
            "gain": (23536, 9752), "loss": (23536, 6490),
            "position_change": (23536, None)},
    },
    "D2": {
        "train": {
            "winner": (111700, 6157), "podium": (111700, 18467),
            "points": (111700, 61384), "final_position": (104459, None),
            "gain": (111507, 44868), "loss": (111507, 31322),
            "position_change": (111507, None)},
        "validation": {
            "winner": (24422, 1325), "podium": (24422, 3975),
            "points": (24422, 13246), "final_position": (23361, None),
            "gain": (24382, 9567), "loss": (24382, 7321),
            "position_change": (24382, None)},
    },
    "D3": {
        "train": {
            "winner": (136122, 7482), "podium": (136122, 22442),
            "points": (136122, 74630), "final_position": (127820, None),
            "gain": (135889, 54435), "loss": (135889, 38643),
            "position_change": (135889, None)},
        "validation": {
            "winner": (26606, 1444), "podium": (26606, 4332),
            "points": (26606, 14427), "final_position": (25766, None),
            "gain": (26578, 10129), "loss": (26578, 7406),
            "position_change": (26578, None)},
    },
}

#: Whole-matrix eligible totals (M0): task -> eligible.
M0_TASK_TOTALS = {
    "winner": 189420, "podium": 189420, "points": 189420,
    "final_position": 178963, "gain": 189126, "loss": 189126,
    "position_change": 189126,
}


@dataclass(frozen=True)
class SplitSpec:
    fold_id: str
    kind: str  # development | final_fit | holdout
    train_seasons: tuple
    validation_seasons: tuple

    @property
    def is_development(self) -> bool:
        return self.kind == "development"

    @property
    def is_final_fit(self) -> bool:
        return self.kind == "final_fit"

    @property
    def is_holdout(self) -> bool:
        return self.kind == "holdout"

    def to_dict(self) -> dict:
        return {
            "fold_id": self.fold_id, "kind": self.kind,
            "train_seasons": list(self.train_seasons),
            "validation_seasons": list(self.validation_seasons),
        }


def development_splits() -> tuple:
    return tuple(
        SplitSpec(f.fold_id, "development", tuple(f.train_seasons),
                  (f.validation_season,))
        for f in DEVELOPMENT_FOLDS)


def get_split(fold_id: str, *,
              allow_protected_holdout: bool = False) -> SplitSpec:
    """Resolve a frozen split id; the 2025 holdout needs explicit intent."""
    if fold_id in DEVELOPMENT_FOLD_IDS:
        return next(s for s in development_splits() if s.fold_id == fold_id)
    if fold_id == FINAL_FIT_ID:
        return SplitSpec(FINAL_FIT_ID, "final_fit",
                         tuple(range(2018, 2025)), ())
    if fold_id == HOLDOUT_ID:
        if not allow_protected_holdout:
            raise ProtectedHoldoutError(
                "the protected 2025 holdout requires explicit intent "
                "(allow_protected_holdout=True)")
        return SplitSpec(HOLDOUT_ID, "holdout", tuple(range(2018, 2025)),
                         (PROTECTED_HOLDOUT_SEASON,))
    raise UnknownFoldError(
        f"unknown fold {fold_id!r}; known: {list(ALL_FOLD_IDS)}")


def _season_set(seasons) -> set:
    return set(int(s) for s in seasons)


def validate_split(canonical: CanonicalMatrix, split: SplitSpec) -> None:
    """No race overlap, strict chronology, and no silent 2025 access."""
    keys = canonical.frame[["season", "race_id"]]
    season = keys["season"].astype(int)
    train_rows = keys.loc[season.isin(_season_set(split.train_seasons))]
    if split.validation_seasons:
        val_rows = keys.loc[season.isin(_season_set(split.validation_seasons))]
    else:
        val_rows = train_rows.iloc[0:0]

    train_races = set(train_rows["race_id"].unique())
    val_races = set(val_rows["race_id"].unique())
    overlap = train_races & val_races
    if overlap:
        raise ProtectedHoldoutError(
            f"{split.fold_id}: races appear in both train and validation: "
            f"{sorted(overlap)[:5]}")

    if split.validation_seasons:
        if int(train_rows["season"].max()) >= int(val_rows["season"].min()):
            raise UnknownFoldError(
                f"{split.fold_id}: train seasons are not strictly before "
                "validation")

    if not split.is_holdout:
        if PROTECTED_HOLDOUT_SEASON in _season_set(split.train_seasons) \
                or PROTECTED_HOLDOUT_SEASON in _season_set(
                    split.validation_seasons):
            raise ProtectedHoldoutError(
                f"{split.fold_id}: protected holdout leaked into a "
                "development/final-fit split")


def split_frame(canonical: CanonicalMatrix,
                split: SplitSpec) -> tuple:
    validate_split(canonical, split)
    train = canonical.select_seasons(split.train_seasons)
    if split.validation_seasons:
        validation = canonical.select_seasons(split.validation_seasons)
    else:
        validation = train.iloc[0:0].copy()
    return train, validation


def _apply_mask(frame: pd.DataFrame, task: ResolvedTask) -> tuple:
    if frame.empty:
        empty = frame.copy()
        return empty, empty[task.label_column].copy(), \
            empty[list(IDENTITY_COLUMNS)].copy()
    mask = frame[task.eligibility_mask].astype("boolean").fillna(False)
    eligible = frame.loc[mask.astype(bool)].copy()
    y = eligible[task.label_column].copy()
    metadata = eligible[list(IDENTITY_COLUMNS)].copy()
    return eligible, y, metadata


def _assert_m0_counts(fold_id: str, side: str, task: str,
                      eligible: int, positives) -> None:
    table = M0_FOLD_TASK_COUNTS.get(fold_id)
    if table is None:
        return
    expected = table[side].get(task)
    if expected is None:
        return
    exp_eligible, exp_pos = expected
    if eligible != exp_eligible:
        raise UnknownFoldError(
            f"{fold_id} {side} {task}: eligible {eligible} != M0 audit "
            f"{exp_eligible}")
    if exp_pos is not None and positives != exp_pos:
        raise UnknownFoldError(
            f"{fold_id} {side} {task}: positives {positives} != M0 audit "
            f"{exp_pos}")


@dataclass(frozen=True)
class ExperimentDataset:
    task: str
    fold_id: str
    feature_set: str
    feature_names: tuple
    split: SplitSpec
    X_train: pd.DataFrame
    y_train: pd.Series
    train_metadata: pd.DataFrame
    X_validation: pd.DataFrame
    y_validation: pd.Series
    validation_metadata: pd.DataFrame
    train_counts: dict
    validation_counts: dict

    def summary(self) -> dict:
        return {
            "task": self.task, "fold_id": self.fold_id,
            "feature_set": self.feature_set,
            "feature_count": len(self.feature_names),
            "split": self.split.to_dict(),
            "train": self.train_counts,
            "validation": self.validation_counts,
        }


def materialize(canonical: CanonicalMatrix, task: str, fold_id: str,
                feature_set: str, *,
                allow_protected_holdout: bool = False,
                assert_m0_counts: bool = True) -> ExperimentDataset:
    """Apply mask first, then select X/y + identity metadata."""
    resolved = resolve_task(task)
    features = resolve_features(feature_set, canonical)
    split = get_split(fold_id,
                      allow_protected_holdout=allow_protected_holdout)
    validate_split(canonical, split)

    full_train = canonical.select_seasons(split.train_seasons)
    full_val = (canonical.select_seasons(split.validation_seasons)
                if split.validation_seasons else full_train.iloc[0:0].copy())

    _, y_train, meta_train = _apply_mask(full_train, resolved)
    _, y_val, meta_val = _apply_mask(full_val, resolved)

    train_elig = len(y_train)
    val_elig = len(y_val)
    train_pos = int(y_train.astype("boolean").sum()) if resolved.is_binary \
        else None
    val_pos = int(y_val.astype("boolean").sum()) if resolved.is_binary \
        else None

    if assert_m0_counts and split.is_development:
        _assert_m0_counts(split.fold_id, "train", task, train_elig, train_pos)
        _assert_m0_counts(split.fold_id, "validation", task, val_elig, val_pos)

    X_train = full_train.loc[y_train.index, list(features)].copy()
    X_val = (full_val.loc[y_val.index, list(features)].copy()
             if len(y_val) else full_val[list(features)].copy())

    train_counts = {"states": int(len(full_train)), "eligible": train_elig,
                    "positives": train_pos, "coverage": int(y_train.notna().sum())}
    val_counts = {"states": int(len(full_val)), "eligible": val_elig,
                  "positives": val_pos, "coverage": int(y_val.notna().sum())}

    return ExperimentDataset(
        task=task, fold_id=fold_id, feature_set=feature_set,
        feature_names=tuple(features), split=split,
        X_train=X_train, y_train=y_train, train_metadata=meta_train,
        X_validation=X_val, y_validation=y_val,
        validation_metadata=meta_val,
        train_counts=train_counts, validation_counts=val_counts,
    )


def validate_task_masks(canonical: CanonicalMatrix) -> dict:
    """Assert the whole-matrix eligible totals match the M0 audit."""
    frame = canonical.frame
    observed = {}
    for task, expected in M0_TASK_TOTALS.items():
        mask = resolve_task(task).eligibility_mask
        total = int(frame[mask].astype("boolean").sum())
        observed[task] = total
        if total != expected:
            raise UnknownFoldError(
                f"task {task!r} eligible total {total} != M0 {expected}")
    return observed
