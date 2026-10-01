"""Phase-8 E5 prediction-change (timeline) explainability.

Exact, read-only decomposition of the change in ONE frozen winner
``LogisticRegression`` score for ONE driver between two REAL prediction
checkpoints A -> B. It consumes two already-computed E4 local explanations
(:mod:`v2.local_explainability`) and subtracts them; it never retrains,
retunes, recalibrates, changes preprocessing or ALL_84, changes coefficients,
normalizes probabilities, touches 2025, reads labels, uses SHAP, or invents
probability-point attributions.

Mathematics (exact change decomposition, not causality):

    z_A = intercept + sum_j c_A,j
    z_B = intercept + sum_j c_B,j
    dz  = z_B - z_A = sum_j (c_B,j - c_A,j) = sum_j dc_j

The intercept cancels exactly because the same frozen model is used at both
checkpoints. ``dc_j`` is an additive change in MODEL LOG-ODDS. It is NEVER a
probability-point contribution: the sigmoid is nonlinear, so the probability
delta ``dp = p_B - p_A`` is reported only as an overall model-prediction
change, never decomposed per feature.

Both endpoints must be REAL frozen checkpoints; arbitrary frame indices are
resolved explicitly by the caller from the frozen checkpoint series, never by
nearest-checkpoint substitution.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from raceintel.explainability import explainability as E3
from raceintel.explainability import local_explainability as E4

#: Additive timeline-change contract version (independent of replay v1/E4 v1).
TIMELINE_EXPLANATION_CONTRACT_VERSION = "v1"

#: Deterministic artifact/payload format identifier.
TIMELINE_EXPLANATION_FORMAT = "timeline-explanation-v1"

#: Explanation space is additive model log-odds, never probability points.
EXPLANATION_SPACE = E3.EXPLANATION_SPACE              # "LOG_ODDS"
PROBABILITY_SEMANTICS = E3.PROBABILITY_SEMANTICS      # "INDEPENDENT_BINARY"

#: Default compact view size (top positive / top negative deltas).
TOP_N = 5

#: Strict numerical tolerances (validated, never loosened to pass).
LOGIT_ABS_TOL = E4.LOGIT_ABS_TOL
PROBABILITY_ABS_TOL = E4.PROBABILITY_ABS_TOL

#: Product comparison states (PART H / PART J).
STATUS_AVAILABLE = "AVAILABLE"
STATUS_NO_PREVIOUS_CHECKPOINT = "NO_PREVIOUS_CHECKPOINT"
STATUS_COMPARISON_UNAVAILABLE = "COMPARISON_UNAVAILABLE"

#: Explicit unavailability reasons (never a null probability treated as zero).
REASON_DRIVER_NOT_OBSERVABLE_AT_SELECTED = (
    "DRIVER_NOT_OBSERVABLE_AT_SELECTED_CHECKPOINT")
REASON_DRIVER_NOT_OBSERVABLE_AT_PREVIOUS = (
    "DRIVER_NOT_OBSERVABLE_AT_PREVIOUS_CHECKPOINT")
REASON_DRIVER_ABSENT_AT_PREVIOUS = "DRIVER_ABSENT_AT_PREVIOUS_CHECKPOINT"
REASON_NULL_PROBABILITY_AT_SELECTED = "NULL_PROBABILITY_AT_SELECTED_CHECKPOINT"
REASON_NULL_PROBABILITY_AT_PREVIOUS = "NULL_PROBABILITY_AT_PREVIOUS_CHECKPOINT"

#: Per-feature transition labels (PART D/F): factual, never causal.
TRANSITION_UNCHANGED = "RAW_INPUT_UNCHANGED"
TRANSITION_INPUT_CHANGED = "RAW_INPUT_CHANGED"
TRANSITION_CATEGORICAL = "CATEGORICAL_TRANSITION"
TRANSITION_IMPUTATION = "IMPUTATION_TRANSITION"
TRANSITION_MISSINGNESS = "MISSINGNESS_TRANSITION"
TRANSITION_STATE_CHANGED = "INPUT_STATE_CHANGED"

_IMPUTED_STATES = frozenset({
    E4.IMPUTED_NUMERIC_MEDIAN, E4.IMPUTED_BOOLEAN_MODE})
_MISSING_STATES = frozenset({
    E4.MISSING_CATEGORY, E4.UNKNOWN_CATEGORY})

#: Candidate-only labels: NO causal wording and NO per-feature probability
#: attribution is ever permitted. Extends the E4 local contract with
#: change-specific forbidden phrases.
TIMELINE_FORBIDDEN_LANGUAGE = tuple(E4.LOCAL_FORBIDDEN_LANGUAGE) + (
    "because",
    "due to",
    "led to",
    "reason the probability",
    "reason probability",
    "made the driver",
    "reacted to",
    "drove the increase",
    "drove the change",
    "explains the increase",
    "responsible for the change",
    "the cause of",
    "as a result of",
)

TIMELINE_ALLOWED_LANGUAGE = tuple(E4.LOCAL_ALLOWED_LANGUAGE) + (
    "between these checkpoints",
    "model score changed",
    "model log-odds increased",
    "model log-odds decreased",
    "contribution increased",
    "contribution decreased",
    "prediction changed by x percentage points",
    "change in model log-odds",
)


class TimelineExplanationError(E3.ExplainabilityError):
    """Fatal E5 timeline-explanation failure. Never repairs or falls back."""


class ChangeReconstructionError(TimelineExplanationError):
    """The canonical contribution deltas do not reconstruct the logit delta."""


class ChangeIdentityError(TimelineExplanationError):
    """The two endpoints cannot form a valid A -> B model delta."""


@dataclass(frozen=True)
class PredictionChangeIdentity:
    """Explicit typed identity of one A -> B prediction comparison (PART B)."""

    race_id: str
    driver_id: str
    from_frame_index: int
    to_frame_index: int
    from_checkpoint: dict
    to_checkpoint: dict

    def to_dict(self) -> dict:
        return {
            "race_id": self.race_id,
            "driver_id": self.driver_id,
            "from_frame_index": self.from_frame_index,
            "to_frame_index": self.to_frame_index,
            "from_checkpoint": dict(self.from_checkpoint),
            "to_checkpoint": dict(self.to_checkpoint),
        }


def _endpoint(identity: dict) -> dict:
    """Compact checkpoint endpoint identity built from an E4 identity dict."""
    observation = identity.get("observation") or {}
    return {
        "frame_index": identity["frame_index"],
        "state_time_s": identity["state_time_s"],
        "leader_lap": identity.get("leader_lap"),
        "reasons": list(identity.get("checkpoint_reasons") or []),
        "anchor_driver_id": identity["anchor_driver_id"],
        "anchor_lap_number": identity["anchor_lap_number"],
        "anchor_state_time_s": identity["anchor_state_time_s"],
        "observed_lap_number": observation.get("observed_lap_number"),
        "observed_time_s": observation.get("observed_time_s"),
        "observed_position": observation.get("observed_position"),
        "observation_age_s": observation.get("observation_age_s"),
    }


def _is_na(value) -> bool:
    return E4._is_na(value)


def _raw_equal(a, b) -> bool:
    if _is_na(a) and _is_na(b):
        return True
    if _is_na(a) or _is_na(b):
        return False
    if isinstance(a, float) and isinstance(b, float) and math.isnan(a) and \
            math.isnan(b):
        return True
    return bool(a == b)


def _transition(from_row: dict, to_row: dict) -> dict:
    """Factual per-feature transition (PART D/E/F). Never causal."""
    from_state = from_row["input_state"]
    to_state = to_row["input_state"]
    state_changed = from_state != to_state
    raw_changed = not _raw_equal(from_row.get("raw_value"),
                                 to_row.get("raw_value"))
    active_changed = from_row.get("active_category") != \
        to_row.get("active_category")

    if state_changed and (
            from_state in _MISSING_STATES or to_state in _MISSING_STATES):
        label = TRANSITION_MISSINGNESS
    elif state_changed and (
            from_state in _IMPUTED_STATES or to_state in _IMPUTED_STATES):
        label = TRANSITION_IMPUTATION
    elif state_changed:
        label = TRANSITION_STATE_CHANGED
    elif to_row["feature_type"] == "categorical" and active_changed:
        label = TRANSITION_CATEGORICAL
    elif raw_changed:
        label = TRANSITION_INPUT_CHANGED
    else:
        label = TRANSITION_UNCHANGED

    return {
        "from_raw_value": from_row.get("raw_value"),
        "to_raw_value": to_row.get("raw_value"),
        "from_input_state": from_state,
        "to_input_state": to_state,
        "from_active_category": from_row.get("active_category"),
        "to_active_category": to_row.get("active_category"),
        "from_imputed_value": from_row.get("imputed_value"),
        "to_imputed_value": to_row.get("imputed_value"),
        "raw_value_changed": raw_changed,
        "input_state_changed": state_changed,
        "transition": label,
    }


def _delta_rows(from_payload: dict, to_payload: dict) -> list:
    from_rows = {r["canonical_feature"]: r
                 for r in from_payload["canonical_contributions"]}
    to_rows = {r["canonical_feature"]: r
               for r in to_payload["canonical_contributions"]}
    order = [r["canonical_feature"]
             for r in from_payload["canonical_contributions"]]
    if [r["canonical_feature"]
            for r in to_payload["canonical_contributions"]] != order:
        raise ChangeIdentityError(
            "canonical feature order differs between the two checkpoints")
    out = []
    for feature in order:
        left = from_rows[feature]
        right = to_rows[feature]
        if left["feature_type"] != right["feature_type"]:
            raise ChangeIdentityError(
                f"feature type drift for {feature!r}")
        from_contribution = float(left["log_odds_contribution"])
        to_contribution = float(right["log_odds_contribution"])
        out.append({
            "canonical_feature": feature,
            "feature_family": left["feature_family"],
            "feature_type": left["feature_type"],
            "from_contribution": from_contribution,
            "to_contribution": to_contribution,
            "contribution_delta": to_contribution - from_contribution,
            "from_direction": left["direction"],
            "to_direction": right["direction"],
            **_transition(left, right),
        })
    return out


def _top_delta_entries(rows, positive: bool, top_n: int):
    if positive:
        selected = [r for r in rows if r["contribution_delta"] > 0.0]
        selected.sort(key=lambda r: (-r["contribution_delta"],
                                     r["canonical_feature"]))
    else:
        selected = [r for r in rows if r["contribution_delta"] < 0.0]
        selected.sort(key=lambda r: (r["contribution_delta"],
                                     r["canonical_feature"]))
    return selected[:top_n], selected


def _limitations() -> list:
    return [
        "This is an exact decomposition of the change in the fitted linear "
        "model's log-odds between two frozen inputs; it is not a causal or "
        "race-outcome explanation and says nothing about why a historical "
        "event occurred.",
        "Contribution deltas are additive in model log-odds. They are never "
        "win-probability increments and are never converted into changes in "
        "win probability.",
        "The overall probability delta is an aggregate model-prediction "
        "change in percentage points. The sigmoid is nonlinear, so it is "
        "never decomposed into per-feature percentage-point shares.",
        "Numeric deltas are per the standardized transformed input, "
        "conditional on the other model inputs; boolean inputs are unscaled "
        "and are not magnitude-comparable with standardized numeric inputs.",
        "Categorical deltas subtract the whole fitted one-hot block for that "
        "canonical feature at both endpoints; the active one-hot term alone "
        "is not the block contribution.",
        "Missing / unknown / imputed inputs are represented explicitly; no "
        "imputation is hidden and a null probability is never treated as "
        "zero.",
        "Independent per-driver binary probabilities are never normalized "
        "into a race distribution.",
    ]


def explain_prediction_change(
    from_payload: dict,
    to_payload: dict,
    *,
    top_n: int = TOP_N,
) -> dict:
    """Exact A -> B change decomposition from two E4 local explanations.

    ``from_payload`` / ``to_payload`` must be full E4 domain payloads (with
    ``canonical_contributions``) for the SAME driver at two REAL checkpoints
    of the same race. The function fails closed on any identity or
    reconstruction mismatch.
    """
    if type(top_n) is not int or top_n < 1:
        raise TimelineExplanationError("top_n must be an int >= 1")
    for name, payload in (("from", from_payload), ("to", to_payload)):
        if not isinstance(payload, dict):
            raise TimelineExplanationError(
                f"{name} payload must be a dict")
        if payload.get("contract_version") != \
                E4.LOCAL_EXPLANATION_CONTRACT_VERSION:
            raise ChangeIdentityError(
                f"{name} payload is not an E4 local-explanation "
                f"{E4.LOCAL_EXPLANATION_CONTRACT_VERSION!r}")
        if payload.get("canonical_contributions") is None:
            raise ChangeIdentityError(
                f"{name} payload is missing canonical contributions")

    from_identity = from_payload["identity"]
    to_identity = to_payload["identity"]
    race_id = from_identity["race_id"]
    driver_id = from_identity["driver_id"]
    if to_identity["race_id"] != race_id or \
            to_identity["driver_id"] != driver_id:
        raise ChangeIdentityError(
            "both endpoints must share race_id and driver_id")
    from_frame = from_identity["frame_index"]
    to_frame = to_identity["frame_index"]
    if not isinstance(from_frame, int) or not isinstance(to_frame, int) or \
            from_frame >= to_frame:
        raise ChangeIdentityError(
            "from_frame_index must be an int strictly below to_frame_index")
    if from_payload["model_identity"] != to_payload["model_identity"]:
        raise ChangeIdentityError(
            "model identity differs between the two checkpoints")
    if from_payload["probability_semantics"] != PROBABILITY_SEMANTICS or \
            to_payload["probability_semantics"] != PROBABILITY_SEMANTICS:
        raise ChangeIdentityError("probability semantics drift")
    if from_payload["explanation_space"] != EXPLANATION_SPACE or \
            to_payload["explanation_space"] != EXPLANATION_SPACE:
        raise ChangeIdentityError("explanation space drift")

    from_logit = float(from_payload["logit"])
    to_logit = float(to_payload["logit"])
    logit_delta = to_logit - from_logit
    from_probability = float(from_payload["probability"])
    to_probability = float(to_payload["probability"])
    probability_delta = to_probability - from_probability

    if from_payload["canonical_feature_count"] != \
            to_payload["canonical_feature_count"]:
        raise ChangeIdentityError("canonical feature count drift")

    rows = _delta_rows(from_payload, to_payload)
    delta_sum = float(sum(r["contribution_delta"] for r in rows))
    residual = delta_sum - logit_delta
    if abs(residual) > LOGIT_ABS_TOL:
        raise ChangeReconstructionError(
            f"canonical contribution deltas do not reconstruct the logit "
            f"delta: residual {residual!r} exceeds {LOGIT_ABS_TOL!r}")

    # Three-way consistency: cached probability must match the frozen model.
    for name, payload, probability in (
            ("from", from_payload, from_probability),
            ("to", to_payload, to_probability)):
        cached = payload.get("cached_probability")
        if cached is not None and abs(float(cached) - probability) > \
                PROBABILITY_ABS_TOL:
            raise ChangeIdentityError(
                f"{name} cached probability disagrees with the frozen model")

    positive, all_positive = _top_delta_entries(rows, True, top_n)
    negative, all_negative = _top_delta_entries(rows, False, top_n)
    total_positive = float(sum(r["contribution_delta"]
                               for r in all_positive))
    total_negative = float(sum(r["contribution_delta"]
                               for r in all_negative))
    shown_positive = float(sum(r["contribution_delta"] for r in positive))
    shown_negative = float(sum(r["contribution_delta"] for r in negative))

    if abs((total_positive + total_negative) - logit_delta) > LOGIT_ABS_TOL:
        raise ChangeReconstructionError(
            "positive + negative delta accounting does not reconstruct the "
            "logit delta")

    identity = PredictionChangeIdentity(
        race_id=race_id,
        driver_id=driver_id,
        from_frame_index=from_frame,
        to_frame_index=to_frame,
        from_checkpoint=_endpoint(from_identity),
        to_checkpoint=_endpoint(to_identity))

    payload = {
        "contract_version": TIMELINE_EXPLANATION_CONTRACT_VERSION,
        "format": TIMELINE_EXPLANATION_FORMAT,
        "status": STATUS_AVAILABLE,
        "identity": identity.to_dict(),
        "model_identity": dict(from_payload["model_identity"]),
        "probability_semantics": PROBABILITY_SEMANTICS,
        "explanation_space": EXPLANATION_SPACE,
        "from_probability": from_probability,
        "to_probability": to_probability,
        "probability_delta": probability_delta,
        "from_logit": from_logit,
        "to_logit": to_logit,
        "logit_delta": logit_delta,
        "cached_from_probability": from_payload.get("cached_probability"),
        "cached_to_probability": to_payload.get("cached_probability"),
        "reconstruction": {
            "from_logit": from_logit,
            "to_logit": to_logit,
            "logit_delta": logit_delta,
            "canonical_delta_sum": delta_sum,
            "residual": residual,
            "logit_abs_tolerance": LOGIT_ABS_TOL,
            "probability_abs_tolerance": PROBABILITY_ABS_TOL,
            "intercept_cancels": True,
            "full_decomposition_reconstructs_change": True,
        },
        "canonical_feature_count": len(rows),
        "canonical_deltas": rows,
        "top_positive": positive,
        "top_negative": negative,
        "accounting": {
            "top_n": top_n,
            "total_positive_log_odds_delta": total_positive,
            "total_negative_log_odds_delta": total_negative,
            "shown_positive_log_odds_delta": shown_positive,
            "shown_negative_log_odds_delta": shown_negative,
            "omitted_positive_log_odds_delta": total_positive - shown_positive,
            "omitted_negative_log_odds_delta": total_negative - shown_negative,
            "positive_feature_count": len(all_positive),
            "negative_feature_count": len(all_negative),
            "full_decomposition_reconstructs_change": True,
            "top_n_reconstructs_change": False,
            "note": ("Top contribution changes are a compact view; only the "
                     "full canonical change vector reconstructs the log-odds "
                     "delta."),
        },
        "limitations": _limitations(),
        "language_contract": {
            "allowed": list(TIMELINE_ALLOWED_LANGUAGE),
            "forbidden": list(TIMELINE_FORBIDDEN_LANGUAGE),
        },
    }
    E3.assert_language_compliant(payload, forbidden=TIMELINE_FORBIDDEN_LANGUAGE)
    return payload


def _public_delta_row(row: dict) -> dict:
    return {
        "canonical_feature": row["canonical_feature"],
        "feature_family": row["feature_family"],
        "feature_type": row["feature_type"],
        "from_raw_value": row["from_raw_value"],
        "to_raw_value": row["to_raw_value"],
        "from_input_state": row["from_input_state"],
        "to_input_state": row["to_input_state"],
        "from_active_category": row["from_active_category"],
        "to_active_category": row["to_active_category"],
        "from_contribution": row["from_contribution"],
        "to_contribution": row["to_contribution"],
        "contribution_delta": row["contribution_delta"],
        "transition": row["transition"],
    }


def public_change_explanation(payload: dict) -> dict:
    """Compact product projection (PART J): no full 84 delta dump."""
    return {
        "contract_version": payload["contract_version"],
        "format": payload["format"],
        "status": payload["status"],
        "identity": payload["identity"],
        "model_identity": payload["model_identity"],
        "probability_semantics": payload["probability_semantics"],
        "explanation_space": payload["explanation_space"],
        "from_probability": payload["from_probability"],
        "to_probability": payload["to_probability"],
        "probability_delta": payload["probability_delta"],
        "from_logit": payload["from_logit"],
        "to_logit": payload["to_logit"],
        "logit_delta": payload["logit_delta"],
        "cached_from_probability": payload["cached_from_probability"],
        "cached_to_probability": payload["cached_to_probability"],
        "reconstruction": payload["reconstruction"],
        "canonical_feature_count": payload["canonical_feature_count"],
        "top_positive": [_public_delta_row(r)
                         for r in payload["top_positive"]],
        "top_negative": [_public_delta_row(r)
                         for r in payload["top_negative"]],
        "accounting": payload["accounting"],
        "limitations": payload["limitations"],
    }
