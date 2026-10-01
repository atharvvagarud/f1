"""E1.6 offline accelerated replay cache backend (builder surface ONLY).

Uses the already-frozen Phase-2 model matrix as the feature
materialization: replay checkpoints resolve observable driver states to
EXACT matrix rows by identity (race_id, driver_id, lap_number,
state_time_s) instead of recomputing ALL_84. E1.5 proved the two are the
same scientific vector (3,764/3,764 rows, max diff 0.0).

This module performs IDENTITY LOOKUP, never feature calculation, and
never modifies frozen science. It may import frozen domain, matrix,
registry and serving code; frozen scientific modules must never import
this module (one-way offline dependency).

Fail-closed rules: exact identity only (no tolerance/rounding/join
fuzz); missing or ambiguous matches raise; 2025 rows are excluded from
the served view and 2025 races are refused; labels/eligibility columns
are never loaded (strict projection to identity + 84 predictive
columns, registry-driven).
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import pandas as pd

from raceintel.prediction import (
    NO_OBSERVATION_AT_SNAPSHOT,
    DriverPrediction,
    PredictionSnapshot,
)

#: Frozen matrix location (relative to repo root).
MATRIX_REL = os.path.join(
    "data", "v2", "processed", "model_matrix", "matrix_version=v1",
    "model_matrix.parquet")
MANIFEST_REL = os.path.join(
    "docs", "generated", "phase2_freeze_manifest.json")

#: Exact lookup identity (canonical D9 state identity).
IDENTITY_COLUMNS = ("race_id", "driver_id", "lap_number", "state_time_s")

#: Identity metadata the builder may retain for lookup (no labels).
LOOKUP_META_COLUMNS = ("race_id", "season", "driver_id", "lap_number",
                       "state_time_s")


class MatrixBackendError(ValueError):
    """Accelerated-backend domain error (never an HTTP code)."""


class MatrixIdentityError(MatrixBackendError):
    """Frozen matrix identity/verification failure (fail closed)."""


class MatrixLookupError(MatrixBackendError):
    """Exact-lookup failure: missing or ambiguous matrix row."""


class MatrixScopeError(MatrixBackendError):
    """Served-scope / 2025 firewall refusal."""


def _manifest_matrix_record(root: str) -> dict:
    with open(os.path.join(root, MANIFEST_REL)) as handle:
        manifest = json.load(handle)
    return manifest["matrix"]


def _sha256_file(path: str) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _ordered_all84_names() -> tuple:
    from raceintel.experiments.feature_sets import canonical_predictive_names
    from raceintel.features.interactions import build_f11_registry
    return tuple(canonical_predictive_names(build_f11_registry()))


def served_seasons() -> tuple:
    from api.v2_service import SERVED_SEASONS
    return tuple(SERVED_SEASONS)


class FrozenReplayFeatureMatrix:
    """Exact-lookup view over the frozen Phase-2 model matrix.

    Holds ONLY served-scope rows (2018-2024) projected to lookup
    metadata + the 84 registry-ordered predictive columns. Labels,
    eligibility masks and companions are never loaded and therefore
    cannot enter prediction computation.
    """

    def __init__(self, frame: pd.DataFrame, feature_names: tuple,
                 manifest_record: dict):
        if tuple(feature_names) != tuple(_ordered_all84_names()):
            raise MatrixIdentityError(
                "ALL_84 registry order drifted at backend construction")
        missing = [c for c in (*IDENTITY_COLUMNS, *feature_names)
                   if c not in frame.columns]
        if missing:
            raise MatrixIdentityError(
                f"matrix frame missing required columns: {missing}")
        forbidden = {"is_winner", "final_position", "is_podium",
                     "scored_points", "position_change_from_state",
                     "gains_position_by_finish", "loses_position_by_finish",
                     "classified_flag", "eligible_is_winner",
                     "eligible_is_podium", "eligible_scored_points",
                     "eligible_ordinal_final_position", "eligible_gain_loss"}
        leaked = sorted(set(frame.columns) & forbidden)
        if leaked:
            raise MatrixIdentityError(
                f"label/eligibility columns must never enter the backend: "
                f"{leaked}")
        key = list(IDENTITY_COLUMNS)
        if bool(frame.duplicated(key).any()):
            raise MatrixIdentityError(
                "duplicate matrix identity rows (fail closed)")
        seasons = set(int(s) for s in frame["season"].unique().tolist())
        if not seasons <= set(served_seasons()):
            raise MatrixScopeError(
                f"served matrix view contains out-of-scope seasons: "
                f"{sorted(seasons)}")
        self._frame = frame.reset_index(drop=True)
        self._names = tuple(feature_names)
        self._manifest_record = dict(manifest_record)

    @classmethod
    def load(cls, root: str = REPO_ROOT,
             path: str | None = None) -> "FrozenReplayFeatureMatrix":
        """Load + verify the frozen matrix (identity check per process).

        Verifies file SHA-256, row/column counts, feature-set version,
        registry fingerprint and content hash against the frozen
        manifest before projecting to the served lookup view. ``path``
        overrides the frozen location for adversarial tests only;
        production always uses the default (which is SHA-pinned).
        """
        record = _manifest_matrix_record(root)
        path = path or os.path.join(root, MATRIX_REL)
        if not os.path.exists(path):
            raise MatrixIdentityError(f"frozen matrix missing at {path}")
        digest = _sha256_file(path)
        if digest != record["parquet_sha256"]:
            raise MatrixIdentityError(
                f"matrix SHA mismatch: got {digest[:16]}..., expected "
                f"{record['parquet_sha256'][:16]}... (fail closed)")
        if record.get("predictive_columns") != 84:
            raise MatrixIdentityError("manifest predictive_columns != 84")
        if record.get("rows") != 189420:
            raise MatrixIdentityError("manifest rows != frozen 189420")
        names = _ordered_all84_names()
        usecols = sorted(set(LOOKUP_META_COLUMNS) | set(names))
        frame = pd.read_parquet(path, columns=usecols)
        if len(frame) != 189420:
            raise MatrixIdentityError(
                f"matrix row count {len(frame)} != frozen 189420")
        frame = frame[frame["season"].isin(served_seasons())].copy()
        if len(frame) == 0:
            raise MatrixIdentityError("served matrix view is empty")
        return cls(frame, names, record)

    @property
    def feature_names(self) -> tuple:
        return self._names

    @property
    def manifest_record(self) -> dict:
        return dict(self._manifest_record)

    def race_slice(self, race_id: str) -> pd.DataFrame:
        """Served matrix rows for one race (2025 refused before lookup)."""
        try:
            season = int(str(race_id).split("-")[0])
        except (ValueError, IndexError):
            raise MatrixScopeError(f"bad race_id {race_id!r}")
        if season not in served_seasons():
            raise MatrixScopeError(
                f"race {race_id!r} is outside the served replay scope "
                f"{list(served_seasons())} (2025 excluded)")
        sliced = self._frame[self._frame["race_id"] == str(race_id)]
        if len(sliced) == 0:
            raise MatrixLookupError(
                f"no served matrix rows for race {race_id!r}")
        return sliced

    def lookup(self, requests: pd.DataFrame,
               race_frame: pd.DataFrame) -> pd.DataFrame:
        """Exact-identity join of request rows to matrix rows.

        ``requests`` carries exactly IDENTITY_COLUMNS (one row per
        observable driver state, duplicates allowed across
        checkpoints). Returns matrix rows in request order with the
        84 predictive columns. Missing or ambiguous matches raise
        (never fall back, never tolerate).
        """
        if list(requests.columns) != list(IDENTITY_COLUMNS):
            raise MatrixLookupError(
                "lookup requests must carry exactly the identity columns")
        want = requests.reset_index(drop=True)
        try:
            got = want.merge(
                race_frame, on=list(IDENTITY_COLUMNS), how="left",
                indicator=True, validate="many_to_one")
        except pd.errors.MergeError as exc:
            raise MatrixLookupError(
                f"ambiguous matrix identity rows (fail closed): {exc}"
            ) from None
        missing = int((got["_merge"] != "both").sum())
        if missing:
            bad = got[got["_merge"] != "both"].iloc[0]
            raise MatrixLookupError(
                f"no exact matrix row for "
                f"{(bad['race_id'], bad['driver_id'], bad['lap_number'], bad['state_time_s'])} "
                f"({missing} of {len(want)} missing; fail closed)")
        return got


class AcceleratedReplayPredictionBuilder:
    """Matrix-backed snapshot generation for one race (builder-only).

    Consumes frozen checkpoints + RaceState reconstruction (factual
    selection of observable states), resolves ALL_84 via exact matrix
    lookup, predicts with the frozen serving objects, and assembles
    snapshots with the existing frozen constructors. No feature is
    ever calculated here.
    """

    def __init__(self, matrix: FrozenReplayFeatureMatrix, predictor,
                 model_identity):
        if matrix is None or predictor is None or model_identity is None:
            raise MatrixBackendError(
                "matrix, predictor and model_identity are required")
        if tuple(predictor.feature_names) != tuple(matrix.feature_names):
            raise MatrixBackendError(
                "predictor ALL_84 order disagrees with matrix order")
        self._matrix = matrix
        self._predictor = predictor
        self._identity = model_identity

    def build_snapshots(self, series, replay_service,
                        bridge) -> dict:
        """Frame index -> frozen snapshot dict (verbatim values)."""
        from raceintel.replay.replay_predictions import CheckpointError
        race_frame = self._matrix.race_slice(series.race_id)
        names = list(self._matrix.feature_names)
        # 1-3. reconstruct every checkpoint, enumerate request identities.
        per_frame: list = []
        request_rows: list = []
        states: list = []
        for checkpoint in series.checkpoints:
            state = replay_service.state_at(checkpoint.frame_index)
            requests = bridge.requests_for(state)
            if not requests:
                raise CheckpointError(
                    f"no observable requests at frame "
                    f"{checkpoint.frame_index}")
            states.append(state)
            per_frame.append((checkpoint, requests))
            for request in requests:
                request_rows.append(request.key())
        # 4-5. one exact join for the race; fail closed on any miss.
        want = pd.DataFrame(request_rows, columns=list(IDENTITY_COLUMNS))
        joined = self._matrix.lookup(want, race_frame)
        # 6-8. restore checkpoint/driver order, project ALL_84, predict
        # per checkpoint (one batch call each, as the reference path).
        snapshots: dict = {}
        offset = 0
        for (checkpoint, requests), state in zip(per_frame, states):
            count = len(requests)
            block = joined.iloc[offset:offset + count]
            offset += count
            order = [r.driver_id for r in requests]
            block = block.set_index("driver_id").loc[order].reset_index()
            frame = block[names].copy()
            if tuple(frame.columns) != tuple(names):
                raise MatrixBackendError("feature frame order drifted")
            probabilities = self._predictor.predict_proba(frame)
            payload = self._assemble(state, requests, probabilities,
                                    checkpoint).to_dict()
            self._check_anchor(payload, checkpoint)
            snapshots[checkpoint.frame_index] = payload
        return snapshots

    def _assemble(self, race_state, requests, probabilities,
                  checkpoint) -> PredictionSnapshot:
        """Mirror of the frozen engine assembly (same constructors)."""
        by_request = {r.driver_id: r for r in requests}
        if len(by_request) != len(requests):
            raise MatrixBackendError("duplicate feature identity")
        by_member = {m.driver_id: m for m in race_state.drivers}
        scored: dict = {}
        for request, raw in zip(requests, list(probabilities)):
            driver_id = request.driver_id
            member = by_member.get(driver_id)
            if member is None or not member.observable:
                raise MatrixBackendError(
                    f"feature row for unobservable roster driver "
                    f"{driver_id!r}")
            value = raw.item() if hasattr(raw, "item") else float(raw)
            scored[driver_id] = DriverPrediction(
                driver_id=driver_id, observable=True,
                observed_lap_number=member.observed_lap_number,
                observed_time_s=member.observed_time_s,
                observation_age_s=member.observation_age_s,
                observed_position=member.position,
                winner_probability=value,
                unavailable_reason=None).winner_probability
        missing = [d for d in race_state.observable_driver_ids
                   if d not in scored]
        if missing:
            raise MatrixBackendError(
                f"observable drivers missing feature rows: {missing}")
        entries = []
        for member in race_state.drivers:
            if member.observable:
                entries.append(DriverPrediction(
                    driver_id=member.driver_id, observable=True,
                    observed_lap_number=member.observed_lap_number,
                    observed_time_s=member.observed_time_s,
                    observation_age_s=member.observation_age_s,
                    observed_position=member.position,
                    winner_probability=scored[member.driver_id],
                    unavailable_reason=None))
            else:
                entries.append(DriverPrediction(
                    driver_id=member.driver_id, observable=False,
                    unavailable_reason=NO_OBSERVATION_AT_SNAPSHOT))
        return PredictionSnapshot(
            race_id=race_state.race_id,
            anchor_driver_id=race_state.anchor_driver_id,
            anchor_lap_number=race_state.anchor_lap_number,
            state_time_s=race_state.state_time_s,
            model=self._identity,
            predictions=tuple(entries))

    @staticmethod
    def _check_anchor(payload: dict, checkpoint) -> None:
        from raceintel.replay.replay_predictions import CheckpointError
        if payload.get("anchor_driver_id") != checkpoint.anchor_driver_id or \
                payload.get("anchor_lap_number") != \
                checkpoint.anchor_lap_number or \
                payload.get("state_time_s") != \
                checkpoint.anchor_state_time_s:
            raise CheckpointError(
                "engine snapshot anchor mismatch at frame "
                f"{checkpoint.frame_index}")
