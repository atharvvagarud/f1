"""Phase-8 E4 local (per-checkpoint, per-driver) explainability.

Exact, read-only explanation of ONE frozen winner ``LogisticRegression``
score for ONE observable driver at ONE replay checkpoint. This module never
retrains, retunes, recalibrates, changes preprocessing or ALL_84, changes
coefficients, normalizes probabilities, touches 2025, reads labels, or
invents probability-point attributions.

Mathematics (exact model decomposition, not causality):

    x'   = preprocessor.transform(canonical_all_84_row)   # 106 dims
    c_j  = beta_j * x'_j                                   # log-odds
    z    = intercept + sum_j c_j                           # model logit
    p    = 1 / (1 + exp(-z))                                # INDEPENDENT_BINARY

The contract guarantees ``z == estimator.decision_function(x')`` and
``p == estimator.predict_proba(x')`` to machine precision, and (when a
cached replay probability is supplied) ``p == cached_probability``. Coeffi-
cients and fitted preprocessing statistics are read from the frozen
serving artifact; preprocessing is never independently reproduced.

The 106 -> 84 canonical map is the authoritative E3 mapping
(:func:`v2.explainability.build_transformed_feature_map`); no second parser
exists. Contributions are additive in model log-odds only; they are NEVER
win-probability increments and are never normalized across a race.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from raceintel.explainability import explainability as E3
from raceintel.model_lab import serving as SERVING

#: Additive local-explanation contract version (independent of replay v1).
LOCAL_EXPLANATION_CONTRACT_VERSION = "v1"

#: Deterministic artifact/payload format identifier.
LOCAL_EXPLANATION_FORMAT = "local-explanation-v1"

#: Explanation space is additive model log-odds, never probability points.
EXPLANATION_SPACE = E3.EXPLANATION_SPACE            # "LOG_ODDS"
PROBABILITY_SEMANTICS = E3.PROBABILITY_SEMANTICS    # "INDEPENDENT_BINARY"

#: Default compact view size.
TOP_N = 5

#: Strict numerical tolerances (validated, never loosened to pass).
LOGIT_ABS_TOL = 1e-12
PROBABILITY_ABS_TOL = 1e-12

#: Canonical per-feature model-input states (PART F).
OBSERVED = "OBSERVED"
IMPUTED_NUMERIC_MEDIAN = "IMPUTED_NUMERIC_MEDIAN"
IMPUTED_BOOLEAN_MODE = "IMPUTED_BOOLEAN_MODE"
MISSING_CATEGORY = "MISSING_CATEGORY"
UNKNOWN_CATEGORY = "UNKNOWN_CATEGORY"

DIRECTION_INCREASES = "INCREASES_MODEL_LOG_ODDS"
DIRECTION_DECREASES = "DECREASES_MODEL_LOG_ODDS"
DIRECTION_NEUTRAL = "NEUTRAL"

#: Candidate-only labels: NO probability-point wording is ever permitted.
LOCAL_FORBIDDEN_LANGUAGE = tuple(E3.FORBIDDEN_LANGUAGE) + (
    "will win",
    "wins because",
    "reason for",
    "true reason",
    "chance",
    "percentage of the win",
    "contributed to the win",
    "win factor",
    "win factors",
    "helped",
    "hurts",
    "hurting",
    "added x%",
)

LOCAL_ALLOWED_LANGUAGE = tuple(E3.ALLOWED_LANGUAGE) + (
    "increased model log-odds",
    "decreased model log-odds",
    "local model contribution",
    "fitted coefficient",
    "model input",
)


class LocalExplanationError(E3.ExplainabilityError):
    """Fatal E4 local-explanation failure. Never repairs or falls back."""


class LocalReconstructionError(LocalExplanationError):
    """Logit / probability reconstruction did not meet the exact tolerance."""


class CachedPredictionMismatchError(LocalExplanationError):
    """The E2 cached replay probability disagrees with the frozen model."""


@dataclass(frozen=True)
class LocalExplanationIdentity:
    """Explicit typed identity of one local explanation (PART A)."""

    race_id: str
    frame_index: int
    driver_id: str
    observed_lap_number: int
    observed_time_s: float
    state_time_s: float
    anchor_driver_id: str
    anchor_lap_number: int
    anchor_state_time_s: float
    checkpoint_reasons: tuple = ()
    leader_lap: int | None = None
    observed_position: int | None = None
    observation_age_s: float | None = None

    def to_dict(self) -> dict:
        return {
            "race_id": self.race_id,
            "frame_index": self.frame_index,
            "driver_id": self.driver_id,
            "checkpoint_reasons": list(self.checkpoint_reasons),
            "leader_lap": self.leader_lap,
            "state_time_s": self.state_time_s,
            "anchor_driver_id": self.anchor_driver_id,
            "anchor_lap_number": self.anchor_lap_number,
            "anchor_state_time_s": self.anchor_state_time_s,
            "feature_identity": {
                "race_id": self.race_id,
                "driver_id": self.driver_id,
                "lap_number": self.observed_lap_number,
                "state_time_s": self.observed_time_s,
            },
            "observation": {
                "observed_lap_number": self.observed_lap_number,
                "observed_time_s": self.observed_time_s,
                "observation_age_s": self.observation_age_s,
                "observed_position": self.observed_position,
            },
        }


def _is_na(value) -> bool:
    if value is None:
        return True
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def _jsonable(value):
    if _is_na(value):
        return None
    if isinstance(value, (np.bool_, bool)):
        return bool(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating, float)):
        return float(value)
    return value


def _direction(contribution: float) -> str:
    if contribution > 0.0:
        return DIRECTION_INCREASES
    if contribution < 0.0:
        return DIRECTION_DECREASES
    return DIRECTION_NEUTRAL


def _sigmoid(z: float) -> float:
    if z >= 0.0:
        return 1.0 / (1.0 + math.exp(-z))
    exp_z = math.exp(z)
    return exp_z / (1.0 + exp_z)


def _model_identity(predictor) -> dict:
    return {
        "feature_set": SERVING.EXPECTED_FEATURE_SET,
        "feature_set_version": "v8",
        "estimator_class": type(predictor._estimator).__name__,
        "specification_fingerprint": predictor.specification_fingerprint,
        "transformed_dim": int(predictor.transformed_dim),
        "canonical_feature_count": len(predictor.feature_names),
        "calibration_method": "RAW",
        "probability_kind": "BINARY_PROBABILITY",
        "probability_semantics": PROBABILITY_SEMANTICS,
        "training_seasons": list(SERVING.EXPECTED_TRAINING_SEASONS),
        "sklearn_version": predictor.sklearn_version,
    }


def _preprocessor_stats(predictor) -> dict:
    """Read fitted imputation/scaling/vocabulary state (never recompute)."""
    pre = predictor._preprocessor
    numeric = pre.transformer.named_transformers_["num"]
    boolean = pre.transformer.named_transformers_["bool"]
    encoder = pre.transformer.named_transformers_[
        "cat"].named_steps["encode"]
    return {
        "numeric_medians": {
            str(col): float(value) for col, value in zip(
                pre.numeric_columns,
                np.asarray(numeric.named_steps["impute"].statistics_,
                           dtype=float))},
        "boolean_modes": {
            str(col): float(value) for col, value in zip(
                pre.boolean_columns,
                np.asarray(boolean.named_steps["impute"].statistics_,
                           dtype=float))},
        "categorical_vocabulary": {
            str(col): [str(v) for v in cats] for col, cats in zip(
                pre.categorical_columns, encoder.categories_)},
        "categorical_handle_unknown": str(encoder.handle_unknown),
    }


def _group_rows(canonical_row: pd.DataFrame, predictor, transformed, stats,
                map_entries) -> list:
    """One canonical row -> 84 grouped local contributions (PART E/G)."""
    names = list(predictor.feature_names)
    if list(canonical_row.columns) != names or len(canonical_row) != 1:
        raise LocalExplanationError(
            "canonical row must carry exactly the ordered ALL_84 columns "
            "for one row")
    transformer = predictor._preprocessor.transformer
    authority = [str(n) for n in transformer.get_feature_names_out()]
    if list(authority) != [e["transformed_name"] for e in map_entries]:
        raise LocalExplanationError(
            "transformed-map order disagrees with the fitted transformer")
    coefficient = np.asarray(predictor._estimator.coef_, dtype=float).ravel()
    vector = np.asarray(transformed, dtype=float).ravel()
    if vector.shape[0] != len(map_entries):
        raise LocalExplanationError(
            "transformed vector width disagrees with the 106-dim map")

    by_feature: dict = {}
    for entry in map_entries:
        by_feature.setdefault(entry["canonical_feature"], []).append(entry)

    rows = []
    for feature in names:
        dims = by_feature.get(feature)
        if not dims:
            raise LocalExplanationError(
                f"canonical feature {feature!r} has no transformed dimension")
        feature_type = dims[0]["feature_type"]
        raw = canonical_row[feature].iloc[0]
        raw_missing = _is_na(raw)
        imputed_value = None
        active_category = None

        if feature_type == "numeric":
            input_state = IMPUTED_NUMERIC_MEDIAN if raw_missing else OBSERVED
            if raw_missing:
                imputed_value = stats["numeric_medians"][feature]
            raw_value = None if raw_missing else _jsonable(raw)
        elif feature_type == "boolean":
            input_state = IMPUTED_BOOLEAN_MODE if raw_missing else OBSERVED
            if raw_missing:
                imputed_value = stats["boolean_modes"][feature]
            raw_value = None if raw_missing else bool(raw)
        else:
            vocabulary = stats["categorical_vocabulary"][feature]
            raw_str = None if raw_missing else str(raw)
            if raw_missing:
                input_state = MISSING_CATEGORY
                active_category = ("MISSING" if "MISSING" in vocabulary
                                   else None)
                imputed_value = active_category
                raw_value = None
            elif raw_str not in vocabulary:
                input_state = UNKNOWN_CATEGORY
                raw_value = raw_str
            elif raw_str == "MISSING":
                input_state = MISSING_CATEGORY
                active_category = "MISSING"
                raw_value = "MISSING"
            else:
                input_state = OBSERVED
                active_category = raw_str
                raw_value = raw_str

        dimension_entries = []
        contribution = 0.0
        for entry in dims:
            index = entry["transformed_index"]
            if float(entry["coefficient"]) != float(coefficient[index]):
                raise LocalExplanationError(
                    f"transformed map coefficient for {feature!r} disagrees "
                    f"with the frozen estimator")
            transformed_value = float(vector[index])
            dim_contribution = float(entry["coefficient"]) * transformed_value
            contribution += dim_contribution
            dimension_entries.append({
                "transformed_index": int(index),
                "transformed_name": entry["transformed_name"],
                "category_value": entry["category_value"],
                "transformed_value": transformed_value,
                "coefficient": float(entry["coefficient"]),
                "log_odds_contribution": dim_contribution,
            })

        rows.append({
            "canonical_feature": feature,
            "feature_family": dims[0]["feature_family"],
            "feature_type": feature_type,
            "raw_value": raw_value,
            "input_state": input_state,
            "imputed_value": imputed_value,
            "active_category": active_category,
            "transformed_dimensions": dimension_entries,
            "log_odds_contribution": float(contribution),
            "direction": _direction(contribution),
        })
    return rows


def _top_entries(rows, contribution_positive: bool, top_n: int):
    if contribution_positive:
        selected = [r for r in rows if r["log_odds_contribution"] > 0.0]
        selected.sort(key=lambda r: (-r["log_odds_contribution"],
                                     r["canonical_feature"]))
    else:
        selected = [r for r in rows if r["log_odds_contribution"] < 0.0]
        selected.sort(key=lambda r: (r["log_odds_contribution"],
                                     r["canonical_feature"]))
    return selected[:top_n], selected


def _limitations() -> list:
    return [
        "This is a decomposition of the fitted linear model's log-odds for "
        "one exact transformed input; it is not a causal or race-outcome "
        "explanation.",
        "Contributions are additive in model log-odds. They are never "
        "win-probability increments and are never converted into changes in "
        "win probability.",
        "Numeric contributions are per the standardized transformed input, "
        "conditional on the other model inputs; boolean inputs are unscaled "
        "and are not magnitude-comparable with standardized numeric inputs.",
        "Categorical contributions sum the fitted one-hot block for that "
        "canonical feature; there is no dropped reference category and an "
        "unseen category fires the all-zero block.",
        "The top-N view is a compact product display. It does not reconstruct "
        "the prediction by itself; the full canonical contribution vector "
        "does.",
        "Independent per-driver binary probabilities are never normalized "
        "into a race distribution.",
    ]


def explain_winner_prediction(
    predictor,
    canonical_row: pd.DataFrame,
    identity: LocalExplanationIdentity,
    *,
    cached_probability: float | None = None,
    map_entries=None,
    top_n: int = TOP_N,
) -> dict:
    """Exact local explanation of one frozen winner-model score.

    ``canonical_row`` must carry exactly one row with the ordered 84 ALL_84
    columns (the EXACT frozen Phase-2 row for ``identity``). The explanation
    is deterministic and fails closed on any reconstruction mismatch.
    """
    if not isinstance(identity, LocalExplanationIdentity):
        raise LocalExplanationError(
            "identity must be a LocalExplanationIdentity")
    if type(top_n) is not int or top_n < 1:
        raise LocalExplanationError("top_n must be an int >= 1")
    if not isinstance(canonical_row, pd.DataFrame):
        raise LocalExplanationError("canonical_row must be a pandas DataFrame")
    if list(canonical_row.columns) != list(predictor.feature_names):
        raise LocalExplanationError(
            "canonical row columns do not match the frozen ordered ALL_84 "
            "feature set")
    if map_entries is None:
        map_entries = E3.build_transformed_feature_map(predictor)

    estimator = predictor._estimator
    intercept = float(np.asarray(estimator.intercept_, dtype=float).ravel()[0])
    transformed = predictor._preprocessor.transform(canonical_row)
    transformed = np.asarray(transformed, dtype=float)
    if transformed.shape != (1, int(predictor.transformed_dim)):
        raise LocalExplanationError(
            f"transformed shape {transformed.shape} != "
            f"(1, {predictor.transformed_dim})")

    coefficient = np.asarray(estimator.coef_, dtype=float).ravel()
    contribution_vector = coefficient * transformed.ravel()
    reconstructed_logit = intercept + float(contribution_vector.sum())

    decision = float(np.asarray(
        estimator.decision_function(transformed), dtype=float).ravel()[0])
    residual = reconstructed_logit - decision
    if abs(residual) > LOGIT_ABS_TOL:
        raise LocalReconstructionError(
            f"logit reconstruction residual {residual!r} exceeds "
            f"{LOGIT_ABS_TOL!r}")

    probability = _sigmoid(reconstructed_logit)
    model_probability = float(np.asarray(
        predictor.predict_proba(canonical_row), dtype=float).ravel()[0])
    if abs(probability - model_probability) > PROBABILITY_ABS_TOL:
        raise LocalReconstructionError(
            f"probability reconstruction |{probability!r} - "
            f"{model_probability!r}| exceeds {PROBABILITY_ABS_TOL!r}")

    cached = None
    if cached_probability is not None:
        cached = float(cached_probability)
        if abs(probability - cached) > PROBABILITY_ABS_TOL:
            raise CachedPredictionMismatchError(
                f"cached replay probability {cached!r} disagrees with the "
                f"frozen model {probability!r} beyond "
                f"{PROBABILITY_ABS_TOL!r}")

    stats = _preprocessor_stats(predictor)
    rows = _group_rows(canonical_row, predictor, transformed, stats,
                       map_entries)

    grouped_sum = float(sum(r["log_odds_contribution"] for r in rows))
    if abs(grouped_sum - float(contribution_vector.sum())) > LOGIT_ABS_TOL:
        raise LocalReconstructionError(
            "106 -> 84 canonical grouping does not sum to the transformed "
            "contribution vector")

    positive, all_positive = _top_entries(rows, True, top_n)
    negative, all_negative = _top_entries(rows, False, top_n)
    total_positive = float(sum(r["log_odds_contribution"]
                               for r in all_positive))
    total_negative = float(sum(r["log_odds_contribution"]
                               for r in all_negative))
    shown_positive = float(sum(r["log_odds_contribution"] for r in positive))
    shown_negative = float(sum(r["log_odds_contribution"] for r in negative))

    payload = {
        "contract_version": LOCAL_EXPLANATION_CONTRACT_VERSION,
        "format": LOCAL_EXPLANATION_FORMAT,
        "identity": identity.to_dict(),
        "model_identity": _model_identity(predictor),
        "probability_semantics": PROBABILITY_SEMANTICS,
        "explanation_space": EXPLANATION_SPACE,
        "intercept": intercept,
        "logit": reconstructed_logit,
        "probability": probability,
        "model_probability": model_probability,
        "cached_probability": cached,
        "reconstruction": {
            "estimator_decision_function": decision,
            "residual": residual,
            "logit_abs_tolerance": LOGIT_ABS_TOL,
            "probability_abs_tolerance": PROBABILITY_ABS_TOL,
            "transformed_contribution_sum": float(contribution_vector.sum()),
            "canonical_contribution_sum": grouped_sum,
        },
        "transformed_feature_count": int(predictor.transformed_dim),
        "canonical_feature_count": len(rows),
        "canonical_contributions": rows,
        "top_positive": positive,
        "top_negative": negative,
        "accounting": {
            "top_n": top_n,
            "total_positive_log_odds": total_positive,
            "total_negative_log_odds": total_negative,
            "shown_positive_log_odds": shown_positive,
            "shown_negative_log_odds": shown_negative,
            "omitted_positive_log_odds": total_positive - shown_positive,
            "omitted_negative_log_odds": total_negative - shown_negative,
            "positive_feature_count": len(all_positive),
            "negative_feature_count": len(all_negative),
            "full_decomposition_reconstructs_prediction": True,
            "top_n_reconstructs_prediction": False,
            "note": ("Top contributions are a compact view; only the full "
                     "canonical contribution vector reconstructs the "
                     "prediction."),
        },
        "limitations": _limitations(),
        "language_contract": {
            "allowed": list(LOCAL_ALLOWED_LANGUAGE),
            "forbidden": list(LOCAL_FORBIDDEN_LANGUAGE),
        },
    }
    E3.assert_language_compliant(payload, forbidden=LOCAL_FORBIDDEN_LANGUAGE)
    return payload


def _public_row(row: dict) -> dict:
    return {
        "canonical_feature": row["canonical_feature"],
        "feature_family": row["feature_family"],
        "feature_type": row["feature_type"],
        "raw_value": row["raw_value"],
        "input_state": row["input_state"],
        "imputed_value": row["imputed_value"],
        "active_category": row["active_category"],
        "log_odds_contribution": row["log_odds_contribution"],
        "direction": row["direction"],
    }


def public_explanation(payload: dict) -> dict:
    """Compact product projection (PART K): no full 84/106 evidence dump.

    The complete canonical/transformed evidence stays domain-internal; the
    wire payload carries identity, reconstruction, top contributions and the
    omitted-contribution accounting.
    """
    return {
        "contract_version": payload["contract_version"],
        "format": payload["format"],
        "identity": payload["identity"],
        "model_identity": payload["model_identity"],
        "probability_semantics": payload["probability_semantics"],
        "explanation_space": payload["explanation_space"],
        "intercept": payload["intercept"],
        "logit": payload["logit"],
        "probability": payload["probability"],
        "model_probability": payload["model_probability"],
        "cached_probability": payload["cached_probability"],
        "reconstruction": payload["reconstruction"],
        "transformed_feature_count": payload["transformed_feature_count"],
        "canonical_feature_count": payload["canonical_feature_count"],
        "top_positive": [_public_row(r) for r in payload["top_positive"]],
        "top_negative": [_public_row(r) for r in payload["top_negative"]],
        "accounting": payload["accounting"],
        "limitations": payload["limitations"],
    }
