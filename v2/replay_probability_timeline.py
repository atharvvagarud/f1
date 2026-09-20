"""Phase-5 R6 probability timeline projection (read-only).

Projects an already-validated R3 checkpoint artifact
(``results/v2_replay/checkpoints/{race_id}.json``) into the
``ProbabilityTimeline`` domain: one probability point per
(driver_id, ACTUAL prediction checkpoint). No frame expansion, no
resampling, no interpolation, no forward/backward fill, no
nearest-checkpoint substitution, no normalization.

Scientific grain: (driver_id, prediction checkpoint). A probability
exists ONLY where the frozen model was actually evaluated. Nulls stay
null (never 0.0); the complete roster is preserved; sums != 1 pass
through verbatim (INDEPENDENT_BINARY).

This module never imports the prediction engine, the feature bridge,
the predictor, model-lab code, or generation functions. It operates on
an already-validated artifact dict only. Driver ordering is
deterministic: driver_id ascending.
"""

from __future__ import annotations

import hashlib
import json

from v2 import replay as RP
from v2.replay_predictions import (
    KNOWN_REASONS,
    REPLAY_PREDICTION_CONTRACT_VERSION,
    canonical_json,
)

#: Probability-timeline projection contract version.
PROBABILITY_TIMELINE_CONTRACT_VERSION = "v1"

#: Frozen probability semantics (mirrors Phase-4 / R3; never normalized).
PROBABILITY_SEMANTICS = "INDEPENDENT_BINARY"

#: On-disk artifact envelope this projection consumes.
ARTIFACT_FORMAT = "replay-checkpoints-v1"


class ProbabilityTimelineError(ValueError):
    """Probability timeline domain error (never an HTTP code)."""


class InconsistentTimelineError(ProbabilityTimelineError):
    """Artifact identity/model mismatch (tampered or mixed artifact)."""


def _req_artifact(artifact: object) -> dict:
    if not isinstance(artifact, dict):
        raise ProbabilityTimelineError(
            f"artifact must be a dict, got {type(artifact)}")
    if artifact.get("artifact_format") != ARTIFACT_FORMAT:
        raise ProbabilityTimelineError(
            "artifact has unknown format "
            f"{artifact.get('artifact_format')!r}")
    if not artifact.get("complete"):
        raise ProbabilityTimelineError(
            "artifact is not a complete cache (refusing projection)")
    for key in ("race_id", "replay_contract_version",
                "prediction_contract_version", "model", "checkpoints"):
        if key not in artifact:
            raise ProbabilityTimelineError(
                f"artifact is missing key {key!r}")
    if artifact.get("replay_contract_version") != RP.REPLAY_CONTRACT_VERSION:
        raise ProbabilityTimelineError("replay_contract_version mismatch")
    if artifact.get("prediction_contract_version") != \
            REPLAY_PREDICTION_CONTRACT_VERSION:
        raise ProbabilityTimelineError(
            "prediction_contract_version mismatch")
    model = artifact.get("model")
    if not isinstance(model, dict) or \
            model.get("probability_semantics") != PROBABILITY_SEMANTICS:
        raise InconsistentTimelineError(
            "artifact model identity is not INDEPENDENT_BINARY")
    entries = artifact.get("checkpoints")
    if not isinstance(entries, list) or not entries:
        raise ProbabilityTimelineError(
            "artifact holds no checkpoint entries")
    return artifact


def build_probability_timeline(artifact: dict) -> dict:
    """Project a validated R3 artifact into a ProbabilityTimeline dict.

    Verbatim preservation: frame_index, state_time_s, leader_lap,
    reasons, driver winner_probability (float or None), artifact-level
    ModelIdentity. Raises on incomplete artifacts, empty series, model
    drift between entries, or non-INDEPENDENT_BINARY semantics.
    """
    artifact = _req_artifact(artifact)
    race_id = artifact["race_id"]
    shared_model = artifact["model"]
    checkpoints_meta: list[dict] = []
    per_driver: dict[str, list[dict]] = {}
    roster: list[str] | None = None
    previous_frame = -1
    previous_t: float | None = None

    for entry in artifact["checkpoints"]:
        if not isinstance(entry, dict):
            raise ProbabilityTimelineError("checkpoint entry must be a dict")
        checkpoint = entry.get("checkpoint")
        prediction = entry.get("prediction")
        if not isinstance(checkpoint, dict) or \
                not isinstance(prediction, dict):
            raise ProbabilityTimelineError(
                "checkpoint entry must hold checkpoint + prediction dicts")
        frame_index = checkpoint.get("frame_index")
        if type(frame_index) is not int or frame_index <= previous_frame:
            raise ProbabilityTimelineError(
                "checkpoints must have increasing unique frame_index")
        previous_frame = frame_index
        reasons = checkpoint.get("reasons")
        if not isinstance(reasons, list) or not reasons or \
                any(r not in KNOWN_REASONS for r in reasons):
            raise ProbabilityTimelineError(
                f"bad checkpoint reasons at frame {frame_index}: "
                f"{reasons!r}")
        if list(sorted(reasons)) != list(reasons):
            raise ProbabilityTimelineError(
                f"checkpoint reasons must be sorted at frame {frame_index}")
        leader_lap = checkpoint.get("leader_lap")
        if leader_lap is not None and (
                type(leader_lap) is not int or leader_lap < 1):
            raise ProbabilityTimelineError(
                f"bad leader_lap at frame {frame_index}: {leader_lap!r}")
        if prediction.get("race_id") != race_id:
            raise InconsistentTimelineError(
                f"prediction race mismatch at frame {frame_index}")
        if prediction.get("model") != shared_model:
            raise InconsistentTimelineError(
                "per-checkpoint model identity drift at frame "
                f"{frame_index} (refusing projection)")
        if prediction.get("probability_semantics") != PROBABILITY_SEMANTICS:
            raise InconsistentTimelineError(
                f"probability semantics drift at frame {frame_index}")
        state_time = prediction.get("state_time_s")
        if not isinstance(state_time, (int, float)) or (
                previous_t is not None and state_time <= previous_t):
            raise ProbabilityTimelineError(
                f"checkpoint historical T must strictly increase "
                f"(frame {frame_index})")
        previous_t = state_time
        expected_anchor = (
            prediction.get("anchor_driver_id"),
            prediction.get("anchor_lap_number"),
            prediction.get("state_time_s"),
        )
        actual_anchor = (
            checkpoint.get("anchor_driver_id"),
            checkpoint.get("anchor_lap_number"),
            checkpoint.get("anchor_state_time_s"),
        )
        if expected_anchor != actual_anchor:
            raise InconsistentTimelineError(
                f"checkpoint/prediction anchor mismatch at frame "
                f"{frame_index}")
        drivers = prediction.get("predictions")
        if not isinstance(drivers, list) or not drivers:
            raise ProbabilityTimelineError(
                f"prediction holds no driver entries at frame {frame_index}")
        driver_ids = [d.get("driver_id") for d in drivers]
        if any(not isinstance(i, str) or not i for i in driver_ids):
            raise ProbabilityTimelineError(
                f"bad driver identity at frame {frame_index}")
        if len(set(driver_ids)) != len(driver_ids):
            raise ProbabilityTimelineError(
                f"duplicate driver entries at frame {frame_index}")
        if roster is None:
            roster = sorted(driver_ids)
        elif sorted(driver_ids) != roster:
            raise InconsistentTimelineError(
                f"roster drift at frame {frame_index} "
                f"(complete roster required)")
        checkpoints_meta.append({
            "frame_index": frame_index,
            "state_time_s": state_time,
            "leader_lap": leader_lap,
            "reasons": list(reasons),
        })
        by_driver = {d["driver_id"]: d for d in drivers}
        for driver_id in roster:
            record = by_driver[driver_id]
            prob = record.get("winner_probability")
            if prob is not None and not isinstance(prob, (int, float)):
                raise ProbabilityTimelineError(
                    f"bad winner_probability for {driver_id!r} at frame "
                    f"{frame_index}: {prob!r}")
            if isinstance(prob, float) and (
                    prob != prob or prob in (float("inf"), float("-inf"))):
                raise ProbabilityTimelineError(
                    f"non-finite winner_probability for {driver_id!r} at "
                    f"frame {frame_index}")
            point = {
                "frame_index": frame_index,
                "state_time_s": state_time,
                "leader_lap": leader_lap,
                "winner_probability": prob,
            }
            per_driver.setdefault(driver_id, []).append(point)

    assert roster is not None
    driver_series = [
        {"driver_id": driver_id, "points": per_driver[driver_id]}
        for driver_id in roster
    ]
    timeline = {
        "race_id": race_id,
        "replay_contract_version": artifact["replay_contract_version"],
        "prediction_contract_version":
            artifact["prediction_contract_version"],
        "probability_timeline_contract_version":
            PROBABILITY_TIMELINE_CONTRACT_VERSION,
        "probability_semantics": PROBABILITY_SEMANTICS,
        "model": dict(shared_model),
        "timeline_identity": "",
        "checkpoints": checkpoints_meta,
        "driver_series": driver_series,
    }
    timeline["timeline_identity"] = timeline_identity(timeline)
    return timeline


def timeline_identity(timeline: dict) -> str:
    """Deterministic identity over the canonical timeline payload.

    Derives from race + contract versions + semantics + model + series
    content only. No timestamps, no random IDs: repeated projection of
    an identical artifact yields a byte-identical identity.
    """
    payload = {
        "race_id": timeline["race_id"],
        "replay_contract_version": timeline["replay_contract_version"],
        "prediction_contract_version":
            timeline["prediction_contract_version"],
        "probability_timeline_contract_version": timeline[
            "probability_timeline_contract_version"],
        "probability_semantics": timeline["probability_semantics"],
        "model": timeline["model"],
        "checkpoints": timeline["checkpoints"],
        "driver_series": timeline["driver_series"],
    }
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def canonical_timeline_json(timeline: dict) -> str:
    """Canonical bytes for determinism checks (sorted keys, exact floats)."""
    return json.dumps(timeline, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
