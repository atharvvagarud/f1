"""F6 temporal race gap engine (Phase 2 Temporal Feature Engine).

Factual race separation for a target at clock T from F1 synchronized
state. Rejects the universal scalar: same-lap line-crossing intervals
are valid seconds; different observed laps are LAPS_APART (never
converted to seconds); red-flag suspension invalidates seconds;
unknown/ambiguous references are explicit nulls — never the legacy
session-minimum + 300 s clip.

Sign convention (frozen): ``seconds_gap = T_target - T_reference >= 0``;
positive means the target trails the reference (crossed the shared
line later); 0.0 for the leader itself or an exact dead heat.
``lap_difference = target_lap - reference_lap`` (0 equal, negative =
laps down). Observation age (``T - reference_time``) rides along as
provenance and is NEVER the gap (separate names, separate tests).
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

import numpy as np
import pandas as pd

from v2 import contracts as C
from v2.features.contracts import (
    FeatureDef,
    FeatureFamily,
    FeatureRequest,
    FeatureResult,
    FeatureStatus,
    MinHistory,
    MinHistoryKind,
    MissingPolicy,
    SyncRequirement,
    TemporalRule,
)
from v2.features.engine import NoCalculatorError
from v2.features.registry import FEATURE_SET_VERSION, FeatureRegistry
from v2.features.temporal import (
    RaceIndex,
    SyncState,
    TemporalError,
    driver_prefix,
    require_columns,
    resolve_target,
    synchronized_field_snapshot,
)


class GapStatus(str, Enum):
    VALID_SECONDS = "valid_seconds"
    LAPS_APART = "laps_apart"
    NO_CAR_AHEAD = "no_car_ahead"          # target leads / sole observable
    REFERENCE_UNOBSERVED = "reference_unobserved"
    TIMING_UNAVAILABLE = "timing_unavailable"  # defensive; state_time is
    # complete in frozen D9, but the contract must not assume it
    RED_FLAG_INVALID = "red_flag_invalid"  # suspension breaks the spatial
    # reading of clock differences
    ORDER_AMBIGUOUS = "order_ambiguous"    # 0 or 2+ holders of the
    # identifying position


@dataclass(frozen=True)
class GapResult:
    status: GapStatus
    target_id: str
    reference_id: str | None
    target_lap: int
    reference_lap: int | None
    lap_difference: int | None     # target_lap - reference_lap
    seconds_gap: float | None      # >= 0 when valid; else None
    seconds_valid: bool | None     # True/False/None(unknown reference)
    reference_age_s: float | None  # provenance, never the gap
    basis: str                     # human-readable reason


def _pos(value) -> int | None:
    try:
        return None if value is None or pd.isna(value) else int(value)
    except (TypeError, ValueError):
        return None


def _track(value) -> str | None:
    try:
        return None if value is None or pd.isna(value) else str(value)
    except (TypeError, ValueError):
        return None


def leader_reference(entries: dict, target_id: str,
                     target_pos: int | None) -> tuple[str | None, GapStatus,
                                                     str]:
    """Factual leader identity from a synchronized snapshot.

    Priority: unique sync position-1 holder (official timing order);
    then the target itself when it holds position 1 (provisional
    self-leadership, e.g. first lap-1 crosser); then max completed laps
    with earliest crossing among OTHER observables (clock-pure fallback
    for pit-cycle skew windows, measured 1.6% of states). Otherwise the
    leader is unknown — never a guess, never final results.
    """
    observable = [(m, s) for m, s in entries.items() if s.observable]
    if not observable:
        return None, GapStatus.REFERENCE_UNOBSERVED, "no observable state"
    holders = [m for m, s in observable
               if _pos(s.values.get("position")) == 1]
    if len(holders) == 1:
        return holders[0], GapStatus.VALID_SECONDS, \
            "unique synchronized position-1"
    if target_pos == 1 and target_id in dict(observable):
        return target_id, GapStatus.VALID_SECONDS, \
            "target holds position 1 (provisional)"
    others = [(m, s) for m, s in observable if m != target_id]
    if not others:
        return None, GapStatus.REFERENCE_UNOBSERVED, \
            "leader unobserved at target clock"
    maxlap = max(s.observed_lap for _, s in others)
    cands = [(m, s) for m, s in others if s.observed_lap == maxlap]
    best = min(cands, key=lambda ms: ms[1].observed_time_s)[0]
    return best, GapStatus.VALID_SECONDS, (
        "max-lap earliest-crossing fallback "
        f"({len(holders)} position-1 holders)")


def ahead_reference(entries: dict, target_id: str,
                    target_pos: int | None) -> tuple[str | None, GapStatus,
                                                    str]:
    """Factual car-ahead identity: unique holder of target_pos - 1.

    Leader (or null position) has no ahead: NO_CAR_AHEAD. Zero or
    multiple holders (measured 3.7% multi): ORDER_AMBIGUOUS, never a
    guess from final order.
    """
    if target_pos is None:
        return None, GapStatus.ORDER_AMBIGUOUS, "target position unknown"
    if target_pos <= 1:
        return None, GapStatus.NO_CAR_AHEAD, "target leads"
    holders = [m for m, s in entries.items()
               if s.observable and m != target_id
               and _pos(s.values.get("position")) == target_pos - 1]
    if len(holders) == 1:
        return holders[0], GapStatus.VALID_SECONDS, \
            "unique predecessor position"
    if not holders:
        return None, GapStatus.ORDER_AMBIGUOUS, \
            "no holder of predecessor position"
    return None, GapStatus.ORDER_AMBIGUOUS, \
        f"{len(holders)} holders of predecessor position"


def gap_between(target_lap: int, target_time: float,
                target_track: str | None, target_id: str,
                reference: SyncState | None,
                unknown_reason: str = "") -> GapResult:
    """Structured gap between a target observation and one sync reference."""
    if reference is None or not reference.observable:
        return GapResult(GapStatus.REFERENCE_UNOBSERVED, target_id, None,
                         target_lap, None, None, None, None, None,
                         unknown_reason or "reference unobserved")
    ref_id = reference.driver_id
    ref_lap = int(reference.observed_lap)
    ref_time = reference.observed_time_s
    if ref_time is None:
        return GapResult(GapStatus.TIMING_UNAVAILABLE, target_id, ref_id,
                         target_lap, ref_lap, None, None, False, None,
                         "reference crossing time unavailable")
    age = float(target_time) - float(ref_time)
    if age < 0:
        raise TemporalError("reference observed after target clock")
    if target_id == ref_id:
        return GapResult(GapStatus.VALID_SECONDS, target_id, ref_id,
                         target_lap, ref_lap, 0, 0.0, True, 0.0,
                         "target is its own reference")
    ref_track = _track(reference.values.get("track_state"))
    if target_track == "red_flag" or ref_track == "red_flag":
        return GapResult(GapStatus.RED_FLAG_INVALID, target_id, ref_id,
                         target_lap, ref_lap, target_lap - ref_lap, None,
                         False, age, "suspension breaks spatial reading")
    if ref_lap != target_lap:
        return GapResult(GapStatus.LAPS_APART, target_id, ref_id,
                         target_lap, ref_lap, target_lap - ref_lap, None,
                         False, age, "different observed laps: no seconds")
    return GapResult(GapStatus.VALID_SECONDS, target_id, ref_id,
                     target_lap, ref_lap, 0, age, True, age,
                     "same-lap line-crossing interval")


def gaps_for_snapshot(target_row, entries: dict) -> tuple[GapResult,
                                                          GapResult]:
    """Leader + car-ahead gaps for one target from a snapshot dict."""
    target_id = str(target_row["driver_id"])
    target_lap = int(target_row["lap_number"])
    target_time = float(target_row["state_time_s"])
    target_track = _track(target_row.get("track_state"))
    target_pos = _pos(target_row.get("position"))
    leader_id, _, _ = leader_reference(entries, target_id, target_pos)
    leader_ref = entries.get(leader_id) if leader_id else None
    leader_gap = gap_between(target_lap, target_time, target_track,
                             target_id, leader_ref,
                             unknown_reason="leader unresolvable")
    ahead_id, ahead_status, ahead_reason = ahead_reference(
        entries, target_id, target_pos)
    if ahead_status is GapStatus.NO_CAR_AHEAD:
        ahead_gap = GapResult(GapStatus.NO_CAR_AHEAD, target_id, None,
                              target_lap, None, None, None, None, None,
                              ahead_reason)
    else:
        ahead_gap = gap_between(target_lap, target_time, target_track,
                                target_id,
                                entries.get(ahead_id) if ahead_id else None,
                                unknown_reason=ahead_reason)
    return leader_gap, ahead_gap


GAP_SOURCES = (
    "driver_lap_state_d9.state_time_s",
    "driver_lap_state_d9.lap_number",
    "driver_lap_state_d9.position",
    "driver_lap_state_d9.track_state",
)

GAP_FEATURE_NAMES = (
    "gap_to_leader_laps",
    "gap_to_leader_seconds",
    "gap_to_leader_seconds_valid",
    "leader_observation_age_s",
    "gap_to_ahead_laps",
    "gap_to_ahead_seconds",
    "gap_to_ahead_seconds_valid",
    "ahead_observation_age_s",
)

_GAP_META = {
    "gap_to_leader_laps": ("int64", "laps"),
    "gap_to_leader_seconds": ("float64", "seconds"),
    "gap_to_leader_seconds_valid": ("bool", "boolean"),
    "leader_observation_age_s": ("float64", "seconds"),
    "gap_to_ahead_laps": ("int64", "laps"),
    "gap_to_ahead_seconds": ("float64", "seconds"),
    "gap_to_ahead_seconds_valid": ("bool", "boolean"),
    "ahead_observation_age_s": ("float64", "seconds"),
}

_GAP_DESCRIPTIONS = {
    "gap_to_leader_laps": "target_lap - leader observed lap (0 equal, "
        "negative = laps down); null when leader unknown.",
    "gap_to_leader_seconds": "Same-lap line-crossing interval "
        "T_target - T_leader (>= 0, target trails); null unless VALID.",
    "gap_to_leader_seconds_valid": "True iff seconds is a valid interval; "
        "False for laps-apart/red/ambiguous; null when leader unknown.",
    "leader_observation_age_s": "T - leader observed time (sync "
        "provenance, never the gap); null when leader unknown.",
    "gap_to_ahead_laps": "target_lap - ahead observed lap; null when "
        "ahead unknown (leader, ambiguous, or unobserved).",
    "gap_to_ahead_seconds": "Same-lap interval to car ahead; null unless "
        "VALID.",
    "gap_to_ahead_seconds_valid": "True iff ahead seconds valid; False for "
        "laps-apart/red/ambiguous; null when ahead unknown.",
    "ahead_observation_age_s": "T - ahead observed time (provenance); null "
        "when ahead unknown.",
}


def _gap_missing(name: str):
    from v2.features.contracts import MissingPolicy
    if name in ("gap_to_leader_seconds", "gap_to_ahead_seconds"):
        return MissingPolicy.NULL_IF_INVALID_GEOMETRY
    return MissingPolicy.NULL_IF_NO_SYNC_STATE


def _build_gap_definitions():
    from v2.features.contracts import (
        FeatureDef, FeatureFamily, FeatureStatus, MinHistory,
        MinHistoryKind, MissingPolicy, SyncRequirement, TemporalRule,
    )
    from v2 import contracts as _C
    defs = []
    for name in GAP_FEATURE_NAMES:
        dtype, unit = _GAP_META[name]
        defs.append(FeatureDef(
            name=name,
            family=FeatureFamily.GAP,
            version=1,
            dtype=dtype,
            unit=unit,
            description=_GAP_DESCRIPTIONS[name],
            sources=GAP_SOURCES,
            formula_ref="v2/features/gaps.py::gaps_for_snapshot "
                        "(F1 sync + same-lap crossing rule)",
            temporal_rule=TemporalRule.SYNCHRONIZED_FIELD,
            sync=SyncRequirement.SYNCHRONIZED_FIELD,
            min_history=MinHistory(MinHistoryKind.NONE),
            missing=_gap_missing(name),
            availability=_C.Availability.LAP_END,
            predictive_eligible=True,
            status=FeatureStatus.CANDIDATE,
        ))
    return tuple(defs)


GAP_DEFINITIONS = _build_gap_definitions()


def register_gap_features(registry: FeatureRegistry) -> FeatureRegistry:
    for d in GAP_DEFINITIONS:
        registry.register(d)
    return registry


def build_f6_registry() -> FeatureRegistry:
    from v2.features.pace import register_f5_features
    from v2.features.registry import build_f2_registry
    return register_gap_features(register_f5_features(build_f2_registry()))


def _gap_feature_values(leader_gap: GapResult,
                        ahead_gap: GapResult) -> dict:
    def tri(gap: GapResult):
        if gap.reference_id is None and gap.status in (
                GapStatus.REFERENCE_UNOBSERVED, GapStatus.ORDER_AMBIGUOUS):
            valid = None
        else:
            valid = bool(gap.seconds_valid)
        return valid
    return {
        "gap_to_leader_laps": leader_gap.lap_difference,
        "gap_to_leader_seconds": leader_gap.seconds_gap,
        "gap_to_leader_seconds_valid": tri(leader_gap),
        "leader_observation_age_s": leader_gap.reference_age_s,
        "gap_to_ahead_laps": ahead_gap.lap_difference,
        "gap_to_ahead_seconds": ahead_gap.seconds_gap,
        "gap_to_ahead_seconds_valid": tri(ahead_gap),
        "ahead_observation_age_s": ahead_gap.reference_age_s,
    }


def gap_for_state(request: FeatureRequest, registry: FeatureRegistry,
                  states: pd.DataFrame, names=None) -> FeatureResult:
    """Single-state F6 computation via F1 field snapshot."""
    from v2.features.registry import validate_definition
    wanted = [d for d in GAP_DEFINITIONS
              if names is None or d.name in names]
    if names is not None:
        missing = sorted(set(names) - {d.name for d in wanted})
        if missing:
            raise NoCalculatorError(f"gap calculator has no features: {missing}")
    for d in wanted:
        validate_definition(d)
    target = resolve_target(states, request.race_id, request.driver_id,
                            request.lap_number, request.state_time_s)
    roster = sorted({str(v) for v in
                     states[states["race_id"] == request.race_id]
                     ["driver_id"].to_numpy()})
    snap = synchronized_field_snapshot(
        states, request.race_id, request.driver_id,
        int(request.lap_number), float(request.state_time_s), roster)
    entries = {m: s for m, s in snap.entries}
    leader_gap, ahead_gap = gaps_for_snapshot(target, entries)
    vals = _gap_feature_values(leader_gap, ahead_gap)
    return FeatureResult(
        race_id=request.race_id,
        driver_id=request.driver_id,
        lap_number=int(request.lap_number),
        state_time_s=float(request.state_time_s),
        feature_set_version=FEATURE_SET_VERSION,
        values=tuple((d.name, vals[d.name]) for d in wanted),
        provenance=(("source", "driver_lap_state_d9"),
                    ("calculator", "gap-f6")),
    )


def gap_batch(states: pd.DataFrame, names=None) -> pd.DataFrame:
    """Chronological per-race sweep with identical gap semantics.

    Rows grouped by equal ``state_time_s``: the whole time-group enters
    the latest-map before any of its targets resolve, so same-T rivals
    are visible exactly as the ``<= T`` rule requires. One shared pure
    core (``gaps_for_snapshot``) with the single-state path.
    """
    require_columns(states, ("race_id", "driver_id", "lap_number",
                             "state_time_s", "position", "track_state"),
                    "gap_batch input")
    wanted = [n for n in GAP_FEATURE_NAMES if names is None or n in names]
    if names is not None:
        missing = sorted(set(names) - set(GAP_FEATURE_NAMES))
        if missing:
            raise NoCalculatorError(f"gap calculator has no features: {missing}")
    from v2.features.temporal import SyncState as _Sync
    rows_out = []
    for race_id, group in states.groupby("race_id", sort=True):
        g = group.sort_values(["state_time_s", "lap_number", "driver_id"],
                              kind="mergesort")
        latest: dict = {}
        for T, cohort in g.groupby("state_time_s", sort=True):
            T = float(T)
            for _, r in cohort.iterrows():
                drv = str(r["driver_id"])
                latest[drv] = _Sync(
                    observable=True, race_id=str(race_id), driver_id=drv,
                    observed_lap=int(r["lap_number"]), observed_time_s=T,
                    observation_age_s=0.0, values=dict(r))
            for _, r in cohort.iterrows():
                entries = {}
                for m, s in latest.items():
                    age = T - float(s.observed_time_s)
                    entries[m] = _Sync(
                        observable=True, race_id=str(race_id), driver_id=m,
                        observed_lap=int(s.observed_lap),
                        observed_time_s=float(s.observed_time_s),
                        observation_age_s=age, values=dict(s.values))
                leader_gap, ahead_gap = gaps_for_snapshot(r, entries)
                vals = _gap_feature_values(leader_gap, ahead_gap)
                rec = {"race_id": str(race_id),
                       "driver_id": str(r["driver_id"]),
                       "lap_number": int(r["lap_number"]),
                       "state_time_s": T}
                for n in wanted:
                    rec[n] = vals[n]
                rows_out.append(rec)
    cols = ["race_id", "driver_id", "lap_number", "state_time_s"] + wanted
    return pd.DataFrame(rows_out, columns=cols)
