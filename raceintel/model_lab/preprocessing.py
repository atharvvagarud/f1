"""M3 train-fitted preprocessing for the Logistic Regression reference model.

Implements the M1 ``PreprocessingContract`` for actual training: every
learned statistic (imputation values, scaling parameters, categorical
vocabulary) is fitted on TRAIN rows only; validation rows are transformed
with the frozen fitted state. No component ever calls fit on validation.

Pipeline (frozen for M3, chosen before observing validation performance):

- numeric (70 cols): median imputation (train medians) + StandardScaler
  (train mean/variance). Logistic Regression is scale-sensitive, so scaling
  on the dense numeric block is scientifically appropriate.
- boolean (11 cols): cast to float, most-frequent imputation (train mode),
  no scaling (0/1 values are already on a benign scale).
- categorical (compound, stint_compound, track_state): missing values are
  structural (e.g. pre-race states with no stint yet) and are represented
  explicitly with the deterministic sentinel ``"MISSING"``; one-hot encoding
  fitted on train vocabulary only with ``handle_unknown="ignore"`` so unseen
  validation categories produce an all-zero block instead of crashing or
  refitting.

The transformed output is densified: the dense numeric/bool block dominates
(~81 of ~105 columns), so sparse storage buys nothing while ``lbfgs``
requires dense input. Dimensionality is ~105 columns, never a huge array.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

from raceintel.model_lab.data import IDENTITY_COLUMNS
from raceintel.model_lab.errors import ExperimentConfigError

#: Deterministic sentinel for structural categorical missingness.
MISSING_CATEGORY = "MISSING"

#: Label / target columns that must never enter the transformed design matrix.
FORBIDDEN_LABEL_COLUMNS = (
    "is_winner",
    "final_position",
    "is_podium",
    "scored_points",
    "position_change_from_state",
    "gains_position_by_finish",
    "loses_position_by_finish",
    "classified_flag",
)

#: Task-mask columns that must never enter the transformed design matrix.
FORBIDDEN_MASK_COLUMNS = (
    "eligible_is_winner",
    "eligible_is_podium",
    "eligible_scored_points",
    "eligible_ordinal_final_position",
    "eligible_gain_loss",
)

#: Identity metadata that must never enter the transformed design matrix.
FORBIDDEN_IDENTITY_COLUMNS = IDENTITY_COLUMNS + (
    "race_id",
    "driver_id",
    "constructor_id",
    "circuit_id",
    "season",
    "round_no",
    "lap_number",
    "state_time_s",
    "state_id",
)


def _forbidden_hits(columns) -> list:
    seen = set(columns)
    hits = []
    for name in (
        FORBIDDEN_LABEL_COLUMNS + FORBIDDEN_MASK_COLUMNS + FORBIDDEN_IDENTITY_COLUMNS
    ):
        if name in seen:
            hits.append(name)
    return sorted(set(hits))


def preprocessing_contract_dict() -> dict:
    """Declarative preprocessing config (stored in experiment identity)."""
    return {
        "numeric_imputation": "median (train-fitted)",
        "numeric_scaling": "StandardScaler (train-fitted)",
        "boolean_imputation": "most_frequent (train-fitted), cast to float, unscaled",
        "categorical_imputation": f"constant {MISSING_CATEGORY!r} (explicit structural sentinel)",
        "categorical_encoding": "one-hot, train-fitted vocabulary, unknown=ignore",
        "native_missing": False,
        "native_categorical": False,
        "notes": "fit on TRAIN only; validation transform-only; densified output",
        "fit_scope": "training only",
    }


@dataclass
class FittedPreprocessor:
    """Frozen train-fitted preprocessing state (transform-only after fit)."""

    numeric_columns: tuple
    boolean_columns: tuple
    categorical_columns: tuple
    transformer: ColumnTransformer
    output_dim: int

    def transform(self, frame: pd.DataFrame) -> np.ndarray:
        """Transform-only path for validation (never refits)."""
        missing = [
            c
            for c in (
                list(self.numeric_columns)
                + list(self.boolean_columns)
                + list(self.categorical_columns)
            )
            if c not in frame.columns
        ]
        if missing:
            raise ExperimentConfigError(
                f"transform frame is missing expected columns: {missing[:5]}"
            )
        prepared = _prepare_frame(
            frame, self.numeric_columns, self.boolean_columns,
            self.categorical_columns,
        )
        out = self.transformer.transform(prepared)
        if hasattr(out, "toarray"):
            out = out.toarray()
        return np.asarray(out, dtype=float)


def _prepare_frame(frame, numeric_columns, boolean_columns,
                   categorical_columns) -> pd.DataFrame:
    """Cast blocks to pipeline-friendly dtypes (no statistics computed)."""
    prepared = pd.DataFrame(index=frame.index)
    for col in numeric_columns:
        prepared[col] = pd.to_numeric(frame[col], errors="coerce")
    for col in boolean_columns:
        series = frame[col]
        if series.dtype == object or str(series.dtype).startswith("boolean"):
            prepared[col] = series.astype("boolean").astype(float)
        else:
            # numpy bool / numeric: SimpleImputer rejects bool dtype, so cast.
            prepared[col] = series.astype(float)
    for col in categorical_columns:
        series = frame[col]
        # Normalize every missing representation to np.nan: the constant
        # imputer replaces np.nan but passes None through untouched.
        prepared[col] = series.astype(object).mask(series.isna(), np.nan)
    return prepared


def _build_transformer(numeric_columns, boolean_columns,
                       categorical_columns) -> ColumnTransformer:
    numeric_pipe = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="median")),
            ("scale", StandardScaler()),
        ]
    )
    boolean_pipe = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="most_frequent")),
        ]
    )
    categorical_pipe = Pipeline(
        steps=[
            ("impute", SimpleImputer(strategy="constant",
                                     fill_value=MISSING_CATEGORY)),
            ("encode", OneHotEncoder(handle_unknown="ignore",
                                     sparse_output=True)),
        ]
    )
    return ColumnTransformer(
        transformers=[
            ("num", numeric_pipe, list(numeric_columns)),
            ("bool", boolean_pipe, list(boolean_columns)),
            ("cat", categorical_pipe, list(categorical_columns)),
        ],
        remainder="drop",
        sparse_threshold=0.0,
    )


def fit_preprocessor(X_train: pd.DataFrame, schema) -> FittedPreprocessor:
    """Fit preprocessing on TRAIN rows only (never call with validation)."""
    numeric_columns = tuple(schema.numeric)
    boolean_columns = tuple(schema.boolean)
    categorical_columns = tuple(schema.categorical)
    hits = _forbidden_hits(list(X_train.columns))
    if hits:
        raise ExperimentConfigError(
            f"label/mask/identity columns must not enter preprocessing: {hits}"
        )
    expected = set(numeric_columns + boolean_columns + categorical_columns)
    if set(X_train.columns) != expected:
        raise ExperimentConfigError(
            "training frame must contain exactly the predictive feature set: "
            f"missing={sorted(expected - set(X_train.columns))[:5]} "
            f"extra={sorted(set(X_train.columns) - expected)[:5]}"
        )
    prepared = _prepare_frame(
        X_train, numeric_columns, boolean_columns, categorical_columns)
    transformer = _build_transformer(
        numeric_columns, boolean_columns, categorical_columns)
    transformer.fit(prepared)
    probe = transformer.transform(prepared.iloc[: min(5, len(prepared))])
    if hasattr(probe, "toarray"):
        probe = probe.toarray()
    return FittedPreprocessor(
        numeric_columns=numeric_columns,
        boolean_columns=boolean_columns,
        categorical_columns=categorical_columns,
        transformer=transformer,
        output_dim=int(np.asarray(probe).shape[1]),
    )
