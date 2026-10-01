"""Phase-4 R3 RaceState -> frozen ALL_84 feature bridge.

``RaceState -> FeatureRequest[] (one per observable driver, each with
its OWN observed lap/time) -> features_for_batch -> ALL_84 DataFrame``
in exact production-serving order. ONE feature implementation remains:
frozen Phase-2. This module computes no feature itself; it identifies
the canonical driver observations the frozen engine must evaluate and
aligns the resulting frame.

Request semantics (critical): a stale rival observed at ``t < T`` is
requested as ``(observed_lap, observed_time_s)``, never as
``(anchor_lap, T)`` — the same canonical observation Phase 2 evaluates
for that driver (and the same identity R2 projects). Unobservable
roster members get no request, no zeros, no null rows.

ALL_84 authority: ``resolve_feature_set("ALL_84")`` over the frozen F11
registry (registry order == manifest order == serving artifact order by
frozen invariant; R4 tuple-compares against the artifact before
inference). The bridge never loads or runs the model.

PriorHistory: injected once per bridge and reused across requests. The
engine only reads it, so reuse is behaviorally identical to per-call
passing (R0/R3-I decision; timings reported in the R3 record).

This module may import frozen Phase-2 feature infrastructure. It must
never import ``v2.model_lab`` runners/tuning/final_fit, sklearn
estimators, ``ml.*``, FastAPI, or API routes (pinned by test), and must
never call ``predict_proba``.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from raceintel.race_state import race_state as RS
from raceintel.experiments.feature_sets import (
    EXPECTED_PREDICTIVE_FEATURE_COUNT,
    canonical_predictive_names,
    resolve_feature_set,
)
from raceintel.features.contracts import FeatureRequest
from raceintel.features.engine import features_for_batch
from raceintel.features.interactions import build_f11_registry
from raceintel.features.priors import PriorHistory
from raceintel.features.registry import FEATURE_SET_VERSION
from raceintel.features.temporal import RaceIndex, TargetNotFoundError, resolve_target


class RaceStateFeatureError(RS.RaceStateError):
    """Base bridge error (no HTTP, no sklearn leakage)."""


class RaceStateFeatureMismatchError(RaceStateFeatureError):
    """Supplied RaceState is inconsistent with the feature corpus."""

    def __init__(self, detail: str):
        super().__init__(f"racestate/feature-corpus mismatch: {detail}")
        self.detail = detail


@dataclass(frozen=True)
class FeatureIdentity:
    """Row identity for one feature row (positional alignment)."""

    race_id: str
    driver_id: str
    observed_lap_number: int
    observed_time_s: float

    def to_dict(self) -> dict:
        return {
            "race_id": self.race_id,
            "driver_id": self.driver_id,
            "observed_lap_number": self.observed_lap_number,
            "observed_time_s": self.observed_time_s,
        }


@dataclass(frozen=True)
class FeatureBatch:
    """ALL_84 frame plus explicit positional identities.

    ``identities[i]`` corresponds exactly to ``features.iloc[i]``; never
    rely on the DataFrame index alone. Observable drivers only, in
    ``driver_id`` order (RaceState normalization). No labels, no
    identity columns inside ``features`` — exactly the 84 frozen names
    in production order.
    """

    race_id: str
    anchor_driver_id: str
    anchor_lap_number: int
    state_time_s: float
    identities: tuple
    features: pd.DataFrame
    feature_names: tuple

    def __len__(self) -> int:
        return len(self.identities)

    @property
    def driver_ids(self) -> tuple:
        return tuple(identity.driver_id for identity in self.identities)


class RaceStateFeatureBridge:
    """Reusable RaceState -> ALL_84 bridge over a canonical corpus."""

    def __init__(self, states: pd.DataFrame, history: PriorHistory,
                 registry=None):
        if not isinstance(states, pd.DataFrame):
            raise RaceStateFeatureError(
                f"states must be a D9-shaped DataFrame, got {type(states)}")
        if not isinstance(history, PriorHistory):
            raise RaceStateFeatureError(
                "history must be a frozen PriorHistory bundle "
                f"(ALL_84 includes priors), got {type(history)}")
        registry = build_f11_registry() if registry is None else registry
        names = resolve_feature_set("ALL_84", None, registry)
        if len(names) != EXPECTED_PREDICTIVE_FEATURE_COUNT:
            raise RaceStateFeatureError(
                "ALL_84 resolved to "
                f"{len(names)} != {EXPECTED_PREDICTIVE_FEATURE_COUNT}")
        if FEATURE_SET_VERSION != "v8":
            raise RaceStateFeatureError(
                f"feature-set version {FEATURE_SET_VERSION!r} != 'v8'")
        if tuple(names) != canonical_predictive_names(registry):
            raise RaceStateFeatureError(
                "ALL_84 order disagrees with canonical registry order")
        self._states = states
        self._history = history
        self._registry = registry
        self._names = tuple(names)
        self._index = RaceIndex(states)
        # R6 serving optimization: per-race slices of the bound corpus,
        # materialized lazily and keyed by the complete semantic input
        # (race_id; the corpus frame itself is fixed at construction).
        # Scientifically invariant: every frozen calculator reads only
        # same-race rows from ``states`` (driver_prefix / resolve_target /
        # field snapshots / race-filtered roster / target meta row) plus
        # the untouched history bundle for priors, so the slice exposes
        # exactly the rows the full frame would. Slices are read-only
        # shared state (the frozen engine only reads them); at most one
        # entry per requested race is retained.
        self._slices: dict = {}

    def _race_slice(self, race_id: str) -> pd.DataFrame:
        """Per-race slice of the bound corpus (cached, read-only)."""
        cached = self._slices.get(str(race_id))
        if cached is not None:
            return cached
        sliced = self._states[self._states["race_id"] == str(race_id)]
        if not len(sliced):
            raise RaceStateFeatureMismatchError(
                f"race {race_id!r} has no states in the feature corpus")
        # R6 OPT-2: contiguous index for the cached slice. The DataFrame
        # index carries no temporal semantics (all frozen operators are
        # boolean-mask / sort / iloc based and index-agnostic), while a
        # fragmented filter index measurably slows pandas take/copy paths
        # (~25% on the primary fixture). Values and rows are unchanged.
        cached = sliced.reset_index(drop=True)
        self._slices[str(race_id)] = cached
        return cached

    @property
    def feature_names(self) -> tuple:
        """Frozen ALL_84 order (== serving artifact order by invariant)."""
        return self._names

    def requests_for(self, race_state: RS.RaceState) -> list:
        """Observable-only requests with per-driver own observed lap/time."""
        if not isinstance(race_state, RS.RaceState):
            raise RaceStateFeatureError(
                f"race_state must be a RaceState, got {race_state!r}")
        if not self._index.drivers(race_state.race_id):
            raise RaceStateFeatureMismatchError(
                f"race {race_state.race_id!r} has no states in the "
                f"feature corpus")
        states = self._race_slice(race_state.race_id)
        try:
            resolve_target(
                states, race_state.race_id,
                race_state.anchor_driver_id, race_state.anchor_lap_number,
                race_state.state_time_s)
        except (TargetNotFoundError, ValueError) as exc:
            raise RaceStateFeatureMismatchError(
                f"anchor does not resolve exactly in the feature corpus: "
                f"{exc}") from None
        requests = []
        for entry in race_state.observable_drivers:
            if entry.observed_time_s > race_state.state_time_s:
                raise RaceStateFeatureMismatchError(
                    f"driver {entry.driver_id!r} observed after snapshot T")
            try:
                resolve_target(
                    states, race_state.race_id, entry.driver_id,
                    entry.observed_lap_number, entry.observed_time_s)
            except (TargetNotFoundError, ValueError) as exc:
                raise RaceStateFeatureMismatchError(
                    f"observable driver {entry.driver_id!r} "
                    f"({entry.observed_lap_number}, "
                    f"{entry.observed_time_s}) does not resolve exactly "
                    f"in the feature corpus: {exc}") from None
            requests.append(FeatureRequest(
                race_id=race_state.race_id, driver_id=entry.driver_id,
                lap_number=entry.observed_lap_number,
                state_time_s=entry.observed_time_s))
        driver_ids = [request.driver_id for request in requests]
        if len(set(driver_ids)) != len(driver_ids):
            raise RaceStateFeatureMismatchError("duplicate driver requests")
        return requests

    def features_for_state(self, race_state: RS.RaceState) -> FeatureBatch:
        """One RaceState -> one batch engine call -> aligned FeatureBatch."""
        requests = self.requests_for(race_state)
        # R6: evaluate over the per-race slice (identical rows to the full
        # frame for this race; see _race_slice). The history bundle is
        # passed through untouched, preserving strictly-past prior reads.
        states = self._race_slice(race_state.race_id)
        results = features_for_batch(
            requests, self._registry, states, names=list(self._names),
            history=self._history)
        if len(results) != len(requests):
            raise RaceStateFeatureError(
                f"engine returned {len(results)} results for "
                f"{len(requests)} requests")
        rows = []
        identities = []
        for request, result in zip(requests, results):
            result_key = (result.race_id, result.driver_id,
                          int(result.lap_number), float(result.state_time_s))
            if result_key != request.key():
                raise RaceStateFeatureError(
                    f"engine result identity {result_key} does not match "
                    f"request {request.key()}")
            values = result.value_dict()
            rows.append([values[name] for name in self._names])
            identities.append(FeatureIdentity(
                race_id=request.race_id, driver_id=request.driver_id,
                observed_lap_number=int(request.lap_number),
                observed_time_s=float(request.state_time_s)))
        frame = pd.DataFrame(rows, columns=list(self._names))
        if tuple(frame.columns) != self._names:
            raise RaceStateFeatureError("feature frame order drifted")
        return FeatureBatch(
            race_id=race_state.race_id,
            anchor_driver_id=race_state.anchor_driver_id,
            anchor_lap_number=race_state.anchor_lap_number,
            state_time_s=race_state.state_time_s,
            identities=tuple(identities),
            features=frame,
            feature_names=self._names,
        )
