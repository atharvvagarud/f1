"""Phase-5 R3 prediction checkpoints + filesystem cache.

Checkpoint selection is MODEL-FREE: it reads only factual D9 columns
(leader progress + track-state token) for each timeline frame's
representative row. This module never imports the feature bridge, the
predictor, or model-lab code — the generation path receives a frozen
``RacePredictionEngine`` by injection (constructed once by the caller,
e.g. the backfill script) and calls ``engine.predict(state)`` per
selected frame. No second prediction implementation exists here.

v1 checkpoint policy (``REPLAY_PREDICTION_CONTRACT_VERSION = "v1"``):

- LEADER_LAP: the first replay frame at which leader progress reaches a
  new lap (``race_leader_laps_at_state`` from the frame's representative
  anchor row — the same value frozen reconstruction exposes as
  ``race_context.race_leader_laps_at_state``). Never any driver's own
  ``lap_number``.
- FLAG_TRANSITION: the frame's regime token differs from the previous
  frame's, where regime = the anchor row's ``track_state`` token
  (``all_clear``/``safety_car``/``yellow``/``vsc``/``vsc_ending``/
  ``red_flag``, or ``"unknown"`` when null). Covers normal<->SC/VSC/red
  and SC<->VSC in both directions. Frame 0 never carries FLAG_TRANSITION
  (no previous frame); it normally carries LEADER_LAP (leader lap 1).

One checkpoint per frame at most; a frame satisfying both carries both
reasons (sorted tuple). Stored probabilities are the frozen snapshot
values verbatim — never normalized, never interpolated.

Read path never generates: a missing/invalid artifact raises
``CheckpointCacheMissError``/``StaleCacheError``/``IncompleteCacheError``.
Generation is an offline operation (see
``scripts/build_replay_prediction_cache.py``).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import tempfile
from dataclasses import dataclass

import pandas as pd

from v2 import replay as RP

#: Prediction-artifact semantics version (independent from the frame
#: timeline version: the two may evolve separately).
REPLAY_PREDICTION_CONTRACT_VERSION = "v1"

#: Frozen Phase-4 contract identity consumed by the cache key.
PHASE4_CONTRACT_VERSION = "v1"

#: Checkpoint reason: first frame reaching a new leader lap.
LEADER_LAP = "LEADER_LAP"
#: Checkpoint reason: track-state regime token changed vs previous frame.
FLAG_TRANSITION = "FLAG_TRANSITION"

KNOWN_REASONS = frozenset({LEADER_LAP, FLAG_TRANSITION})

#: On-disk artifact envelope marker.
ARTIFACT_FORMAT = "replay-checkpoints-v1"

#: Default cache root (overridable by callers/CLI).
DEFAULT_CHECKPOINTS_DIR = "results/v2_replay/checkpoints"

#: Regime token when the anchor row carries no track_state.
UNKNOWN_REGIME = "unknown"

#: Columns the model-free selector reads (factual only; never labels,
#: features, or model outputs).
SELECTOR_COLUMNS = frozenset({
    "race_id", "driver_id", "lap_number", "state_time_s",
    "race_leader_laps_at_state", "track_state",
})


class CheckpointError(ValueError):
    """Checkpoint domain error (never an HTTP code)."""


class CheckpointCacheError(CheckpointError):
    """Cached artifact problem (miss / stale / incomplete)."""


class CheckpointCacheMissError(CheckpointCacheError):
    """No artifact file present (read path never generates)."""


class StaleCacheError(CheckpointCacheError):
    """Artifact identity does not match current scientific inputs."""


class IncompleteCacheError(CheckpointCacheError):
    """Artifact holds fewer checkpoints than its series (never complete)."""


def _req_reason_tuple(reasons: object) -> tuple:
    if not isinstance(reasons, (tuple, list)) or not reasons:
        raise CheckpointError(
            f"reasons must be a non-empty tuple/list, got {reasons!r}")
    ordered = tuple(sorted(reasons))
    unknown = [r for r in ordered if r not in KNOWN_REASONS]
    if unknown:
        raise CheckpointError(f"unknown checkpoint reasons: {unknown}")
    if len(set(ordered)) != len(ordered):
        raise CheckpointError(
            f"duplicate checkpoint reasons: {list(reasons)!r}")
    return ordered


@dataclass(frozen=True)
class PredictionCheckpoint:
    """One model-free checkpoint: WHERE to predict (never the values)."""

    race_id: str
    frame_index: int
    anchor_driver_id: str
    anchor_lap_number: int
    anchor_state_time_s: float
    reasons: tuple
    leader_lap: int | None
    replay_contract_version: str = RP.REPLAY_CONTRACT_VERSION
    prediction_contract_version: str = REPLAY_PREDICTION_CONTRACT_VERSION

    def __post_init__(self) -> None:
        frame = RP.ReplayFrame(
            race_id=self.race_id, frame_index=self.frame_index,
            anchor_driver_id=self.anchor_driver_id,
            anchor_lap_number=self.anchor_lap_number,
            anchor_state_time_s=self.anchor_state_time_s,
            replay_contract_version=self.replay_contract_version)
        object.__setattr__(self, "race_id", frame.race_id)
        object.__setattr__(self, "frame_index", frame.frame_index)
        object.__setattr__(self, "anchor_driver_id",
                            frame.anchor_driver_id)
        object.__setattr__(self, "anchor_lap_number",
                            frame.anchor_lap_number)
        object.__setattr__(self, "anchor_state_time_s",
                            frame.anchor_state_time_s)
        object.__setattr__(self, "reasons", _req_reason_tuple(self.reasons))
        if self.leader_lap is not None:
            if type(self.leader_lap) is not int or self.leader_lap < 1:
                raise CheckpointError(
                    f"leader_lap must be an int >= 1 or None, "
                    f"got {self.leader_lap!r}")
        version = self.prediction_contract_version
        if not isinstance(version, str) or not version.strip():
            raise CheckpointError(
                "prediction_contract_version must be non-empty")
        if version != REPLAY_PREDICTION_CONTRACT_VERSION:
            raise CheckpointError(
                f"unsupported prediction_contract_version {version!r}")

    def frame_id(self) -> RP.ReplayFrame:
        """The checkpoint's factual frame identity."""
        return RP.ReplayFrame(
            race_id=self.race_id, frame_index=self.frame_index,
            anchor_driver_id=self.anchor_driver_id,
            anchor_lap_number=self.anchor_lap_number,
            anchor_state_time_s=self.anchor_state_time_s,
            replay_contract_version=self.replay_contract_version)

    def to_dict(self) -> dict:
        return {
            "race_id": self.race_id,
            "frame_index": self.frame_index,
            "anchor_driver_id": self.anchor_driver_id,
            "anchor_lap_number": self.anchor_lap_number,
            "anchor_state_time_s": self.anchor_state_time_s,
            "reasons": list(self.reasons),
            "leader_lap": self.leader_lap,
            "replay_contract_version": self.replay_contract_version,
            "prediction_contract_version":
                self.prediction_contract_version,
        }


@dataclass(frozen=True)
class CheckpointSeries:
    """Immutable ordered checkpoints for one race."""

    race_id: str
    replay_contract_version: str
    prediction_contract_version: str
    checkpoints: tuple

    def __post_init__(self) -> None:
        if not isinstance(self.race_id, str) or not self.race_id.strip():
            raise CheckpointError("series race_id must be non-empty")
        if self.replay_contract_version != RP.REPLAY_CONTRACT_VERSION:
            raise CheckpointError("series replay_contract_version mismatch")
        if self.prediction_contract_version != \
                REPLAY_PREDICTION_CONTRACT_VERSION:
            raise CheckpointError(
                "series prediction_contract_version mismatch")
        entries = list(self.checkpoints) if self.checkpoints else []
        if not entries:
            raise CheckpointError("CheckpointSeries requires a checkpoint")
        for entry in entries:
            if not isinstance(entry, PredictionCheckpoint):
                raise CheckpointError(
                    "series must contain only PredictionCheckpoint, "
                    f"got {entry!r}")
            if entry.race_id != self.race_id:
                raise CheckpointError("series mixes race_ids")
        indices = [e.frame_index for e in entries]
        if indices != sorted(indices) or len(set(indices)) != len(indices):
            raise CheckpointError(
                "checkpoints must have increasing unique frame_index")
        times = [e.anchor_state_time_s for e in entries]
        if any(b <= a for a, b in zip(times, times[1:])):
            raise CheckpointError(
                "checkpoint historical T must strictly increase")
        object.__setattr__(self, "checkpoints", tuple(entries))

    @property
    def checkpoint_count(self) -> int:
        return len(self.checkpoints)

    def to_dict(self) -> dict:
        return {
            "race_id": self.race_id,
            "replay_contract_version": self.replay_contract_version,
            "prediction_contract_version":
                self.prediction_contract_version,
            "checkpoint_count": self.checkpoint_count,
            "checkpoints": [e.to_dict() for e in self.checkpoints],
        }


def _regime(track_state: object) -> str:
    if track_state is None:
        return UNKNOWN_REGIME
    try:
        if bool(pd.isna(track_state)):
            return UNKNOWN_REGIME
    except (TypeError, ValueError):
        raise CheckpointError(
            f"uncoercible track_state {track_state!r}")
    return str(track_state)


def select_checkpoints(timeline: RP.ReplayTimeline,
                       states: pd.DataFrame) -> CheckpointSeries:
    """Model-free checkpoint selection for one race (v1 policy).

    Reads representative-row leader progress + regime token per frame;
    never touches features, models, labels, or future rows.
    """
    if not isinstance(timeline, RP.ReplayTimeline):
        raise CheckpointError(
            f"timeline must be a ReplayTimeline, got {timeline!r}")
    if not isinstance(states, pd.DataFrame):
        raise CheckpointError(
            f"states must be a canonical DataFrame, got {type(states)}")
    missing = sorted(SELECTOR_COLUMNS - set(states.columns))
    if missing:
        raise CheckpointError(
            f"state frame is missing selector columns: {missing}")
    lookup: dict[tuple, tuple] = {}
    for row in states.itertuples(index=False):
        key = (str(row.driver_id), int(row.lap_number),
               float(row.state_time_s))
        if str(row.race_id) != timeline.race_id:
            raise CheckpointError(
                f"selector input mixes race {row.race_id!r} into "
                f"{timeline.race_id!r}")
        leader = row.race_leader_laps_at_state
        try:
            leader_lap = None if bool(pd.isna(leader)) else int(leader)
        except (TypeError, ValueError) as exc:
            raise CheckpointError(
                f"bad race_leader_laps_at_state {leader!r}: {exc}") from None
        # Exact-duplicate identity rows are corruption (R1 policy).
        if key in lookup and lookup[key] != (leader_lap,
                                             _regime(row.track_state)):
            raise CheckpointError(
                f"conflicting duplicate selector row: {key}")
        lookup.setdefault(key, (leader_lap, _regime(row.track_state)))
    selected: list[PredictionCheckpoint] = []
    seen_leader = 0
    previous_regime: str | None = None
    for frame in timeline.frames:
        key = (frame.anchor_driver_id, frame.anchor_lap_number,
               frame.anchor_state_time_s)
        try:
            leader_lap, regime = lookup[key]
        except KeyError:
            raise CheckpointError(
                f"timeline anchor has no canonical row: {key}") from None
        reasons: list[str] = []
        if leader_lap is not None and leader_lap > seen_leader:
            reasons.append(LEADER_LAP)
            seen_leader = leader_lap
        if previous_regime is not None and regime != previous_regime:
            reasons.append(FLAG_TRANSITION)
        previous_regime = regime
        if reasons:
            selected.append(PredictionCheckpoint(
                race_id=frame.race_id, frame_index=frame.frame_index,
                anchor_driver_id=frame.anchor_driver_id,
                anchor_lap_number=frame.anchor_lap_number,
                anchor_state_time_s=frame.anchor_state_time_s,
                reasons=tuple(sorted(reasons)), leader_lap=leader_lap))
    return CheckpointSeries(
        race_id=timeline.race_id,
        replay_contract_version=RP.REPLAY_CONTRACT_VERSION,
        prediction_contract_version=REPLAY_PREDICTION_CONTRACT_VERSION,
        checkpoints=tuple(selected))


# ---------------------------------------------------------------------------
# Cache identity (deterministic; no mtime/uuid/timestamps).
# ---------------------------------------------------------------------------

def canonical_data_identity(states: pd.DataFrame, race_id: str) -> str:
    """Fingerprint of one race's canonical anchor rows (exact values)."""
    if len(states) == 0 or bool((states["race_id"] != race_id).any()):
        raise CheckpointError(
            "data identity requires exactly one race's rows")
    rows = sorted(
        (str(d), int(lap), repr(float(t)))
        for d, lap, t in zip(states["driver_id"], states["lap_number"],
                             states["state_time_s"]))
    payload = {"race_id": race_id, "count": len(rows), "rows": rows}
    return hashlib.sha256(canonical_json(payload).encode()).hexdigest()


def series_identity(series: CheckpointSeries) -> str:
    """Fingerprint of the selected checkpoint series."""
    return hashlib.sha256(
        canonical_json(series.to_dict()).encode()).hexdigest()


def canonical_json(payload: object) -> str:
    """Deterministic JSON (sorted keys, exact float repr)."""
    return json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)


def cache_identity_inputs(*, series: CheckpointSeries,
                          data_identity: str,
                          feature_set: str, feature_set_version: str,
                          artifact_sha256: str,
                          specification_fingerprint: str,
                          phase2_content_hash: str,
                          probability_semantics: str) -> dict:
    """Ordered cache-key inputs (all strings; no timestamps)."""
    inputs = {
        "replay_contract_version": series.replay_contract_version,
        "prediction_contract_version":
            series.prediction_contract_version,
        "phase4_contract_version": PHASE4_CONTRACT_VERSION,
        "race_id": series.race_id,
        "series_identity": series_identity(series),
        "checkpoint_count": series.checkpoint_count,
        "feature_set": feature_set,
        "feature_set_version": feature_set_version,
        "serving_artifact_sha256": artifact_sha256,
        "model_specification_fingerprint": specification_fingerprint,
        "phase2_content_hash": phase2_content_hash,
        "canonical_data_identity": data_identity,
        "probability_semantics": probability_semantics,
    }
    for name, value in inputs.items():
        if not isinstance(value, (str, int)) or (
                isinstance(value, str) and not value):
            raise CheckpointError(
                f"cache identity input {name!r} must be a non-empty "
                f"value, got {value!r}")
    return inputs


def cache_key(inputs: dict) -> str:
    """sha256 over the canonical cache-identity inputs."""
    return hashlib.sha256(canonical_json(inputs).encode()).hexdigest()


# ---------------------------------------------------------------------------
# Artifact build / write / load (read path never generates).
# ---------------------------------------------------------------------------

def build_artifact(series: CheckpointSeries,
                   snapshots: dict,
                   model_identity: dict,
                   identity_inputs: dict) -> dict:
    """Assemble the JSON-able artifact (snapshot dicts stored verbatim)."""
    expected = [c.frame_index for c in series.checkpoints]
    present = [c for c in expected if c in snapshots]
    if set(snapshots) != set(present) or len(snapshots) != len(present):
        raise CheckpointError(
            "snapshot keys must be a series-ordered prefix")
    entries = []
    for checkpoint in series.checkpoints:
        if checkpoint.frame_index not in snapshots:
            break
        snapshot = snapshots[checkpoint.frame_index]
        if snapshot.get("race_id") != series.race_id or \
                snapshot.get("anchor_driver_id") != \
                checkpoint.anchor_driver_id or \
                snapshot.get("anchor_lap_number") != \
                checkpoint.anchor_lap_number or \
                snapshot.get("state_time_s") != \
                checkpoint.anchor_state_time_s:
            raise CheckpointError(
                "snapshot anchor mismatch at frame "
                f"{checkpoint.frame_index}")
        if len(snapshot.get("predictions", [])) != snapshot.get(
                "roster_size"):
            raise CheckpointError(
                "snapshot roster incomplete at frame "
                f"{checkpoint.frame_index}")
        entries.append({"checkpoint": checkpoint.to_dict(),
                        "prediction": snapshot})
    complete = len(entries) == series.checkpoint_count
    return {
        "artifact_format": ARTIFACT_FORMAT,
        "race_id": series.race_id,
        "replay_contract_version": series.replay_contract_version,
        "prediction_contract_version":
            series.prediction_contract_version,
        "complete": complete,
        "series": series.to_dict(),
        "model": model_identity,
        "cache_identity": dict(identity_inputs),
        "cache_key": cache_key(identity_inputs),
        "checkpoints": entries,
    }


def artifact_path(checkpoints_dir: str, race_id: str) -> str:
    return os.path.join(checkpoints_dir, f"{race_id}.json")


def write_artifact(path: str, artifact: dict) -> None:
    """Atomic write (temp file in same directory + os.replace)."""
    payload = canonical_json(artifact)
    directory = os.path.dirname(os.path.abspath(path))
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(fd, "w") as handle:
            handle.write(payload)
        # Validate bytes before publishing: reloadable + complete shape.
        json.loads(payload)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def validate_snapshot(snapshot: object) -> None:
    """Structural validation of a stored ``PredictionSnapshot``.

    Verifies roster completeness, unique driver identities, and
    probability semantics (finite, in [0, 1]; null carries an
    availability reason). Values are otherwise passed through verbatim:
    totals may exceed 1 under INDEPENDENT_BINARY and are never
    renormalized. A malformed snapshot is never served.
    """
    if not isinstance(snapshot, dict):
        raise CheckpointError("snapshot must be a dict")
    predictions = snapshot.get("predictions")
    if not isinstance(predictions, list):
        raise CheckpointError("snapshot predictions must be a list")
    if snapshot.get("roster_size") != len(predictions):
        raise CheckpointError(
            "snapshot roster incomplete: len(predictions) != roster_size")
    seen: set = set()
    for entry in predictions:
        if not isinstance(entry, dict):
            raise CheckpointError("snapshot prediction entry must be a dict")
        driver_id = entry.get("driver_id")
        if not isinstance(driver_id, str) or not driver_id:
            raise CheckpointError(
                f"snapshot driver identity must be a non-empty string, "
                f"got {driver_id!r}")
        if driver_id in seen:
            raise CheckpointError(
                f"duplicate driver in snapshot: {driver_id!r}")
        seen.add(driver_id)
        probability = entry.get("winner_probability")
        if probability is None:
            reason = entry.get("unavailable_reason")
            if not isinstance(reason, str) or not reason:
                raise CheckpointError(
                    "null winner_probability requires an availability "
                    "reason")
            continue
        if isinstance(probability, bool) or \
                not isinstance(probability, (int, float)) or \
                not math.isfinite(probability) or \
                not 0.0 <= probability <= 1.0:
            raise CheckpointError(
                f"invalid winner_probability {probability!r} for "
                f"{driver_id!r}")


def load_validated_artifact(path: str, *, expected_inputs: dict,
                            series: CheckpointSeries) -> dict:
    """Read + validate; raises miss/stale/incomplete/corrupt (never generates).

    Validation is structural and defensive: a truncated/invalid JSON body,
    a non-object root, a wrong envelope/race/identity/series, an
    incomplete checkpoint set, drifted checkpoint entries, or a malformed
    prediction snapshot all fail deterministically. Callers map these to
    explicit errors; nothing is ever served from a corrupt artifact.
    """
    if not os.path.exists(path):
        raise CheckpointCacheMissError(f"no checkpoint artifact: {path}")
    with open(path) as handle:
        artifact = json.load(handle)
    if not isinstance(artifact, dict):
        raise CheckpointCacheError(
            f"artifact root is not a JSON object in {path}")
    if artifact.get("artifact_format") != ARTIFACT_FORMAT:
        raise StaleCacheError(f"unknown artifact format in {path}")
    if artifact.get("race_id") != series.race_id:
        raise StaleCacheError(f"race mismatch in {path}")
    if artifact.get("cache_identity") != expected_inputs or \
            artifact.get("cache_key") != cache_key(expected_inputs):
        raise StaleCacheError(
            f"cache identity mismatch in {path} (scientific inputs "
            f"changed; regenerate offline)")
    if artifact.get("series") != series.to_dict():
        raise StaleCacheError(f"checkpoint series drift in {path}")
    entries = artifact.get("checkpoints")
    if not isinstance(entries, list) or not artifact.get("complete") or \
            len(entries) != series.checkpoint_count:
        raise IncompleteCacheError(
            f"partial artifact {path} is not a complete cache")
    for entry, expected in zip(entries, series.checkpoints):
        if not isinstance(entry, dict):
            raise CheckpointCacheError(
                f"malformed checkpoint entry in {path}")
        if entry.get("checkpoint") != expected.to_dict():
            raise StaleCacheError(
                f"checkpoint entry drift in {path} at frame "
                f"{expected.frame_index} (regenerate offline)")
        validate_snapshot(entry.get("prediction"))
    return artifact


def read_cached_prediction(artifact: dict, frame_index: int) -> dict:
    """One checkpoint's stored prediction (KeyError-free explicit error)."""
    for entry in artifact.get("checkpoints", []):
        if entry["checkpoint"]["frame_index"] == frame_index:
            return entry["prediction"]
    raise CheckpointCacheMissError(
        f"frame {frame_index} has no cached checkpoint prediction")


# ---------------------------------------------------------------------------
# Offline generation (injected frozen engine; model loaded once by caller).
# ---------------------------------------------------------------------------

def generate_checkpoint(engine, replay_service,
                        checkpoint: PredictionCheckpoint) -> dict:
    """One checkpoint frame -> frozen snapshot dict (verbatim values)."""
    state = replay_service.state_at(checkpoint.frame_index)
    snapshot = engine.predict(state)
    payload = snapshot.to_dict()
    if payload.get("anchor_driver_id") != checkpoint.anchor_driver_id or \
            payload.get("anchor_lap_number") != \
            checkpoint.anchor_lap_number or \
            payload.get("state_time_s") != checkpoint.anchor_state_time_s:
        raise CheckpointError(
            "engine snapshot anchor mismatch at frame "
            f"{checkpoint.frame_index}")
    return payload


def generate_race_artifact(*, series: CheckpointSeries, replay_service,
                           engine, model_identity: dict,
                           identity_inputs: dict,
                           only_frames: frozenset | None = None,
                           progress=None) -> dict:
    """Generate an artifact dict (complete, or prefix-subset for validation).

    ``only_frames`` restricts generation to a deterministic subset (the
    series-ordered prefix intersected with the set); the artifact records
    ``complete: false`` unless every series checkpoint was generated.
    Subset artifacts always fail complete-cache validation by design.
    """
    wanted = [c for c in series.checkpoints
              if only_frames is None or c.frame_index in only_frames]
    snapshots: dict = {}
    for position, checkpoint in enumerate(wanted):
        snapshots[checkpoint.frame_index] = generate_checkpoint(
            engine, replay_service, checkpoint)
        if progress is not None:
            progress(position + 1, len(wanted), checkpoint)
    return build_artifact(series, snapshots, model_identity,
                          identity_inputs)


def ensure_race_artifact(*, path: str, series: CheckpointSeries,
                         replay_service, engine, model_identity: dict,
                         identity_inputs: dict, force: bool = False,
                         only_frames: frozenset | None = None,
                         progress=None) -> tuple:
    """Skip valid-complete artifacts (resume); else generate + write.

    Returns ("skipped" | "generated", path). Never generates on the read
    path: this is the offline entry point only.
    """
    if not force and only_frames is None and os.path.exists(path):
        try:
            load_validated_artifact(path, expected_inputs=identity_inputs,
                                    series=series)
            return "skipped", path
        except CheckpointCacheError:
            pass
    artifact = generate_race_artifact(
        series=series, replay_service=replay_service, engine=engine,
        model_identity=model_identity, identity_inputs=identity_inputs,
        only_frames=only_frames, progress=progress)
    write_artifact(path, artifact)
    return "generated", path
