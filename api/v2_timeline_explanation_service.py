"""V2 prediction-change (timeline) application service (Phase-8 E5).

Read-only facade that resolves ONE selected replay checkpoint + observable
driver to an EXACT change explanation against the driver's PREVIOUS frozen
prediction checkpoint:

    replay service (cached checkpoints + exact RaceState)
      -> previous checkpoint resolved explicitly from the frozen series
      -> two E4 local explanations (A, B) via V2ExplanationService
      -> v2.timeline_explainability.explain_prediction_change (frozen model)

The E2 prediction cache is required at both endpoints. A missing / stale /
incomplete cache raises ``PredictionUnavailableError``; a non-checkpoint
frame raises ``NotPredictionCheckpointError``; unknown races/frames/drivers
surface exactly as in E4. No arbitrary frame is ever snapped to a nearest
checkpoint.

No explanation mathematics lives here and none lives in the route handler.
This module only orchestrates frozen, read-only components.
"""

from __future__ import annotations

import functools

from api.v2_explanation_service import (
    DriverNotObservableError,
    ExplanationFeatureUnavailableError,
    UnknownDriverError,
    V2ExplanationService,
    get_v2_explanation_service,
)
from api.v2_replay_service import (
    NotPredictionCheckpointError,
    PredictionUnavailableError,
    V2ReplayService,
    get_v2_replay_service,
)
from v2.timeline_explainability import (
    REASON_DRIVER_ABSENT_AT_PREVIOUS,
    REASON_DRIVER_NOT_OBSERVABLE_AT_PREVIOUS,
    REASON_DRIVER_NOT_OBSERVABLE_AT_SELECTED,
    REASON_NULL_PROBABILITY_AT_PREVIOUS,
    REASON_NULL_PROBABILITY_AT_SELECTED,
    STATUS_AVAILABLE,
    STATUS_COMPARISON_UNAVAILABLE,
    STATUS_NO_PREVIOUS_CHECKPOINT,
    TIMELINE_EXPLANATION_CONTRACT_VERSION,
    TIMELINE_EXPLANATION_FORMAT,
    explain_prediction_change,
    public_change_explanation,
)


def _endpoint(checkpoint: dict, snapshot: dict, entry: dict | None) -> dict:
    return {
        "frame_index": int(checkpoint["frame_index"]),
        "state_time_s": float(snapshot["state_time_s"]),
        "leader_lap": checkpoint.get("leader_lap"),
        "reasons": list(checkpoint.get("reasons") or []),
        "anchor_driver_id": str(checkpoint["anchor_driver_id"]),
        "anchor_lap_number": int(checkpoint["anchor_lap_number"]),
        "anchor_state_time_s": float(checkpoint["anchor_state_time_s"]),
        "observed_lap_number": (
            entry.get("observed_lap_number") if entry else None),
        "observed_time_s": (
            entry.get("observed_time_s") if entry else None),
        "observed_position": (
            entry.get("observed_position") if entry else None),
        "observation_age_s": (
            entry.get("observation_age_s") if entry else None),
    }


def _entry(snapshot: dict, driver_id: str) -> dict | None:
    return next((e for e in snapshot["predictions"]
                 if e["driver_id"] == driver_id), None)


class V2TimelineExplanationService:
    """Previous-checkpoint change explanation over E4 + frozen matrix/model."""

    def __init__(self, replay_service: V2ReplayService,
                 explanation_service: V2ExplanationService, *,
                 top_n: int = 5):
        if not isinstance(replay_service, V2ReplayService):
            raise ValueError(
                "replay_service must be a V2ReplayService, got "
                f"{type(replay_service)}")
        if not isinstance(explanation_service, V2ExplanationService):
            raise ValueError(
                "explanation_service must be a V2ExplanationService, got "
                f"{type(explanation_service)}")
        self._replay = replay_service
        self._explanation = explanation_service
        self._top_n = int(top_n)

    def get_change(self, race_id: str, frame_index: int,
                   driver_id: str) -> dict:
        """Selected checkpoint + driver -> previous-checkpoint change state."""
        cached = self._replay.get_prediction(race_id, frame_index)
        checkpoint = cached["checkpoint"]
        snapshot = cached["prediction"]
        entry_b = _entry(snapshot, driver_id)
        if entry_b is None:
            raise UnknownDriverError(race_id, frame_index, driver_id)

        series = self._replay.get_series(race_id)
        ordered = [c.frame_index for c in series.checkpoints]
        selected_frame = checkpoint["frame_index"]
        position = ordered.index(selected_frame)
        to_endpoint = _endpoint(checkpoint, snapshot, entry_b)

        if position == 0:
            return self._state(
                STATUS_NO_PREVIOUS_CHECKPOINT, race_id, driver_id,
                from_frame=None, to_frame=selected_frame,
                from_checkpoint=None, to_checkpoint=to_endpoint,
                reason=None)

        previous_frame = ordered[position - 1]
        previous = self._replay.get_prediction(race_id, previous_frame)
        checkpoint_a = previous["checkpoint"]
        snapshot_a = previous["prediction"]
        entry_a = _entry(snapshot_a, driver_id)
        from_endpoint = _endpoint(checkpoint_a, snapshot_a, entry_a)

        reason = self._unavailable_reason(entry_a, entry_b)
        if reason is not None:
            return self._state(
                STATUS_COMPARISON_UNAVAILABLE, race_id, driver_id,
                from_frame=previous_frame, to_frame=selected_frame,
                from_checkpoint=from_endpoint, to_checkpoint=to_endpoint,
                reason=reason)

        from_domain = self._explanation.get_domain_explanation(
            race_id, previous_frame, driver_id)
        to_domain = self._explanation.get_domain_explanation(
            race_id, selected_frame, driver_id)
        payload = explain_prediction_change(
            from_domain, to_domain, top_n=self._top_n)
        public = public_change_explanation(payload)
        public["status"] = STATUS_AVAILABLE
        public["cache_status"] = "HIT"
        return public

    @staticmethod
    def _unavailable_reason(entry_a: dict | None, entry_b: dict) -> str | None:
        """Explicit reason there is no valid two-point model delta (PART H)."""
        if entry_a is None:
            return REASON_DRIVER_ABSENT_AT_PREVIOUS
        if not entry_a["observable"]:
            return REASON_DRIVER_NOT_OBSERVABLE_AT_PREVIOUS
        if entry_a["winner_probability"] is None:
            return REASON_NULL_PROBABILITY_AT_PREVIOUS
        if not entry_b["observable"]:
            return REASON_DRIVER_NOT_OBSERVABLE_AT_SELECTED
        if entry_b["winner_probability"] is None:
            return REASON_NULL_PROBABILITY_AT_SELECTED
        return None

    @staticmethod
    def _state(status: str, race_id: str, driver_id: str, *,
               from_frame: int | None, to_frame: int,
               from_checkpoint: dict | None, to_checkpoint: dict,
               reason: str | None) -> dict:
        return {
            "contract_version": TIMELINE_EXPLANATION_CONTRACT_VERSION,
            "format": TIMELINE_EXPLANATION_FORMAT,
            "status": status,
            "identity": {
                "race_id": race_id,
                "driver_id": driver_id,
                "from_frame_index": from_frame,
                "to_frame_index": to_frame,
                "from_checkpoint": from_checkpoint,
                "to_checkpoint": to_checkpoint,
            },
            "model_identity": None,
            "probability_semantics": "INDEPENDENT_BINARY",
            "explanation_space": "LOG_ODDS",
            "reason": reason,
            "from_probability": None,
            "to_probability": None,
            "probability_delta": None,
            "from_logit": None,
            "to_logit": None,
            "logit_delta": None,
            "cached_from_probability": None,
            "cached_to_probability": None,
            "reconstruction": None,
            "canonical_feature_count": None,
            "top_positive": [],
            "top_negative": [],
            "accounting": None,
            "limitations": [],
            "cache_status": "HIT",
        }


def build_v2_timeline_explanation_service(
        replay_service=None, explanation_service=None, *,
        root=None) -> V2TimelineExplanationService:
    """Construct the service, loading frozen components only when omitted."""
    if replay_service is None:
        replay_service = get_v2_replay_service()
    if explanation_service is None:
        explanation_service = get_v2_explanation_service()
    return V2TimelineExplanationService(replay_service, explanation_service)


@functools.lru_cache(maxsize=1)
def _cached_timeline_explanation_service() -> V2TimelineExplanationService:
    return build_v2_timeline_explanation_service()


def get_v2_timeline_explanation_service() -> V2TimelineExplanationService:
    """FastAPI dependency: lazy process-local singleton (override in tests)."""
    return _cached_timeline_explanation_service()


__all__ = [
    "V2TimelineExplanationService",
    "build_v2_timeline_explanation_service",
    "get_v2_timeline_explanation_service",
    "DriverNotObservableError",
    "ExplanationFeatureUnavailableError",
    "UnknownDriverError",
    "NotPredictionCheckpointError",
    "PredictionUnavailableError",
    "STATUS_AVAILABLE",
    "STATUS_COMPARISON_UNAVAILABLE",
    "STATUS_NO_PREVIOUS_CHECKPOINT",
    "TIMELINE_EXPLANATION_CONTRACT_VERSION",
]
