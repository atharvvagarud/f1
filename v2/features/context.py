"""F7 relative/teammate/field/traffic context (Phase 2).

Cross-driver race context from F1 synchronized state: rival F5 pace
evaluated at each rival's own synchronized state (never later),
teammate identity from stable constructor scope, robust field median,
factual F6 car-ahead reference, and evidence-backed proximity counts.
No closing rates, no momentum, no priors, no projections.

Sign convention (frozen): relative = target_recent_pace - reference;
negative = target faster (seconds/lap). Pace basis: pace_median_5
(robust; 92% coverage) — the ONLY cross-driver basis in F7.
"""

from __future__ import annotations

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
from v2.features.gaps import GapStatus, gaps_for_snapshot
from v2.features.registry import FEATURE_SET_VERSION, FeatureRegistry
from v2.features.temporal import (
    TemporalError,
    driver_prefix,
    require_columns,
    resolve_target,
    synchronized_field_snapshot,
)

#: The single F5 basis used for every cross-driver pace comparison.
PACE_BASIS = "pace_median_5"

#: Field median requires at least this many comparable rivals (92.4%).
FIELD_MIN_RIVALS = 5

#: Proximity bands from measured same-lap ahead-gap distribution
#: (p50 ~3 s; <=2 s ~40%; <=5 s ~65%). Conventional bands, not
#: physical claims; never DRS inference.
TRAFFIC_S = 2.0
PACK_S = 5.0


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


def rival_pace_at_sync(states: pd.DataFrame, race_id: str, rival_id: str,
                       sync_lap: int, sync_time: float):
    """Rival F5 basis evaluated at its OWN synchronized state.

    Prefix ends at the rival's sync observation (<= T by F1 rule), so a
    later same-lap rival crossing can never contribute. Returns None
    when the rival lacks sufficient eligible history.
    """
    from v2.features.pace import pace_values
    prefix = driver_prefix(states, race_id, rival_id, float(sync_time))
    if not len(prefix):
        return None
    # The sync observation must be the prefix end (exact sync state).
    vals = pace_values(prefix)
    return vals.get(PACE_BASIS)


def _median(values: list):
    return float(np.median(np.asarray(values, dtype=float))) if values else None


def context_for_snapshot(target_row, entries: dict,
                         rival_pace_of) -> dict:
    """Pure F7 core over a synchronized snapshot.

    ``rival_pace_of(driver_id, sync_lap, sync_time)`` supplies each
    rival's basis pace at its own sync state (single-state computes it
    live; batch looks it up from the exact-state cache). Returns all
    F7 values (None where unavailable).
    """
    target_id = str(target_row["driver_id"])
    target_lap = int(target_row["lap_number"])
    target_time = float(target_row["state_time_s"])
    target_pos = _pos(target_row.get("position"))
    target_track = _track(target_row.get("track_state"))
    out: dict = {}
    # Target basis pace at its own state.
    t_pace = rival_pace_of(target_id, target_lap, target_time)
    # --- teammate ---
    tm_id = teammate_id_from_entries(
        entries, target_id, target_row.get("constructor_id"))
    if tm_id is None or tm_id not in entries or not entries[tm_id].observable:
        out["relative_pace_to_teammate_s_per_lap"] = None
        out["teammate_observation_age_s"] = None
        out["teammate_lap_difference"] = None
        out["teammate_position"] = None
    else:
        tm = entries[tm_id]
        tm_pace = rival_pace_of(tm_id, int(tm.observed_lap),
                                float(tm.observed_time_s))
        out["teammate_observation_age_s"] = float(tm.observation_age_s)
        out["teammate_lap_difference"] = target_lap - int(tm.observed_lap)
        out["teammate_position"] = _pos(tm.values.get("position"))
        if t_pace is None or tm_pace is None:
            out["relative_pace_to_teammate_s_per_lap"] = None
        else:
            out["relative_pace_to_teammate_s_per_lap"] = float(t_pace - tm_pace)
    # --- field (observable others, target excluded) ---
    field_paces = []
    for m, s in entries.items():
        if m == target_id or not s.observable:
            continue
        p = rival_pace_of(m, int(s.observed_lap), float(s.observed_time_s))
        if p is not None and np.isfinite(p):
            field_paces.append(float(p))
    out["field_pace_comparable_rivals"] = int(len(field_paces))
    if len(field_paces) >= FIELD_MIN_RIVALS and t_pace is not None:
        out["relative_pace_to_field_median_s_per_lap"] = float(
            t_pace - _median(field_paces))
    else:
        out["relative_pace_to_field_median_s_per_lap"] = None
    observable_others = [m for m, s in entries.items()
                         if m != target_id and s.observable]
    out["observable_field_size"] = int(len(observable_others) + 1)
    if target_pos is None:
        out["cars_ahead_observable"] = None
        out["cars_behind_observable"] = None
    else:
        ahead = behind = 0
        for m in observable_others:
            p = _pos(entries[m].values.get("position"))
            if p is None:
                continue
            if p < target_pos:
                ahead += 1
            elif p > target_pos:
                behind += 1
        out["cars_ahead_observable"] = int(ahead)
        out["cars_behind_observable"] = int(behind)
    # --- car-ahead relative pace + proximity (F6 identity/geometry) ---
    _, ahead_gap = gaps_for_snapshot(target_row, entries)
    if ahead_gap.reference_id is None:
        out["relative_pace_to_car_ahead_s_per_lap"] = None
        out["in_traffic_2s"] = None
    else:
        a_id = ahead_gap.reference_id
        a_sync = entries[a_id]
        a_pace = rival_pace_of(a_id, int(a_sync.observed_lap),
                               float(a_sync.observed_time_s))
        if t_pace is None or a_pace is None:
            out["relative_pace_to_car_ahead_s_per_lap"] = None
        else:
            out["relative_pace_to_car_ahead_s_per_lap"] = float(t_pace - a_pace)
        if ahead_gap.status.value == "valid_seconds" \
                and ahead_gap.seconds_gap is not None:
            out["in_traffic_2s"] = bool(ahead_gap.seconds_gap <= TRAFFIC_S)
        else:
            out["in_traffic_2s"] = None
    # --- pack: same-lap valid intervals within PACK_S, both directions ---
    if target_track == "red_flag":
        out["nearby_cars_within_5s"] = None
    else:
        n_pack = 0
        for m, s in entries.items():
            if m == target_id or not s.observable:
                continue
            if int(s.observed_lap) != target_lap:
                continue  # laps-apart never masquerades as proximity
            if _track(s.values.get("track_state")) == "red_flag":
                continue
            if abs(target_time - float(s.observed_time_s)) <= PACK_S:
                n_pack += 1
        out["nearby_cars_within_5s"] = int(n_pack)
    return out


def teammate_id_from_entries(entries: dict, target_id: str,
                             constructor_id) -> str | None:
    """Teammate identity over snapshot entries (same rule as frame)."""
    if constructor_id is None or pd.isna(constructor_id):
        return None
    others = set()
    for m, s in entries.items():
        if m == target_id or not s.observable:
            continue
        if str(s.values.get("constructor_id")) == str(constructor_id):
            others.add(m)
    # Entries only cover observables; unobserved roster members cannot
    # contribute (snapshot semantics). Ambiguity -> None.
    if len(others) == 1:
        return next(iter(others))
    # Fall back to constructor peers regardless of observability is
    # impossible here by design; caller (frame path) covers it.
    return None


F7_FEATURE_NAMES = (
    "relative_pace_to_teammate_s_per_lap",
    "teammate_observation_age_s",
    "teammate_lap_difference",
    "teammate_position",
    "relative_pace_to_field_median_s_per_lap",
    "field_pace_comparable_rivals",
    "observable_field_size",
    "cars_ahead_observable",
    "cars_behind_observable",
    "relative_pace_to_car_ahead_s_per_lap",
    "in_traffic_2s",
    "nearby_cars_within_5s",
)

_F7_FAMILY = {
    "relative_pace_to_teammate_s_per_lap": "teammate",
    "teammate_observation_age_s": "teammate",
    "teammate_lap_difference": "teammate",
    "teammate_position": "teammate",
    "relative_pace_to_field_median_s_per_lap": "field",
    "field_pace_comparable_rivals": "field",
    "observable_field_size": "field",
    "cars_ahead_observable": "field",
    "cars_behind_observable": "field",
    "relative_pace_to_car_ahead_s_per_lap": "relative",
    "in_traffic_2s": "traffic",
    "nearby_cars_within_5s": "traffic",
}

_F7_DTYPE = {
    "teammate_lap_difference": "int64",
    "teammate_position": "int64",
    "field_pace_comparable_rivals": "int64",
    "observable_field_size": "int64",
    "cars_ahead_observable": "int64",
    "cars_behind_observable": "int64",
    "nearby_cars_within_5s": "int64",
    "in_traffic_2s": "bool",
}

_F7_UNIT = {
    "relative_pace_to_teammate_s_per_lap": "seconds_per_lap",
    "teammate_observation_age_s": "seconds",
    "teammate_lap_difference": "laps",
    "teammate_position": "position",
    "relative_pace_to_field_median_s_per_lap": "seconds_per_lap",
    "field_pace_comparable_rivals": "count",
    "observable_field_size": "count",
    "cars_ahead_observable": "count",
    "cars_behind_observable": "count",
    "relative_pace_to_car_ahead_s_per_lap": "seconds_per_lap",
    "in_traffic_2s": "boolean",
    "nearby_cars_within_5s": "count",
}

_F7_FAMILY_ENUM = {
    "teammate": "TEAMMATE", "field": "FIELD", "relative": "RELATIVE",
    "traffic": "TRAFFIC",
}

_F7_DESCRIPTIONS = {
    "relative_pace_to_teammate_s_per_lap": "Target pace_median_5 minus "
        "teammate pace_median_5 evaluated at the teammate's own "
        "synchronized state (s/lap; negative = target faster).",
    "teammate_observation_age_s": "T minus teammate sync time (sync "
        "provenance; stale kept, retirement never inferred).",
    "teammate_lap_difference": "Target lap minus teammate observed lap.",
    "teammate_position": "Teammate position at its synchronized state.",
    "relative_pace_to_field_median_s_per_lap": "Target pace_median_5 "
        "minus median over comparable rivals' own-state pace_median_5 "
        "(target excluded; >= 5 contributors; negative = faster).",
    "field_pace_comparable_rivals": "Rivals contributing pace to the "
        "field median (0 allowed; always defined).",
    "observable_field_size": "Observable participants incl. target "
        "(honest count, NOT a running field).",
    "cars_ahead_observable": "Observable others with better (smaller) "
        "position; duplicates each count (no strict order claimed).",
    "cars_behind_observable": "Observable others with worse position.",
    "relative_pace_to_car_ahead_s_per_lap": "Target minus F6 factual "
        "car-ahead pace_median_5 (unique predecessor only).",
    "in_traffic_2s": "True iff valid same-lap ahead gap <= 2.0 s "
        "(measured band; null when geometry invalid/unknown; never DRS).",
    "nearby_cars_within_5s": "Same-lap rivals within a 5 s line interval "
        "either direction, red-flag pairs excluded (0 allowed).",
}


def _f7_missing(name: str):
    from v2.features.contracts import MissingPolicy
    if name in ("field_pace_comparable_rivals", "observable_field_size",
                "cars_ahead_observable", "cars_behind_observable",
                "nearby_cars_within_5s"):
        return MissingPolicy.NULL_IF_NOT_APPLICABLE  # always defined
    return MissingPolicy.NULL_IF_NO_SYNC_STATE


def _build_f7_definitions():
    from v2.features.contracts import (
        FeatureDef, FeatureFamily, FeatureStatus, MinHistory,
        MinHistoryKind, MissingPolicy, SyncRequirement, TemporalRule,
    )
    from v2 import contracts as _C
    sync_of = {"teammate": SyncRequirement.SYNCHRONIZED_RIVAL,
               "field": SyncRequirement.SYNCHRONIZED_FIELD,
               "relative": SyncRequirement.SYNCHRONIZED_RIVAL,
               "traffic": SyncRequirement.SYNCHRONIZED_FIELD}
    defs = []
    for name in F7_FEATURE_NAMES:
        fam = _F7_FAMILY[name]
        defs.append(FeatureDef(
            name=name,
            family=getattr(FeatureFamily, _F7_FAMILY_ENUM[fam]),
            version=1,
            dtype=_F7_DTYPE.get(name, "float64"),
            unit=_F7_UNIT[name],
            description=_F7_DESCRIPTIONS[name],
            sources=("driver_lap_state_d9.lap_time_s",
                     "driver_lap_state_d9.state_time_s",
                     "driver_lap_state_d9.position",
                     "driver_lap_state_d9.track_state",
                     "driver_lap_state_d9.constructor_id"),
            formula_ref="v2/features/context.py::context_for_snapshot "
                        f"(basis {PACE_BASIS}; target minus reference)",
            temporal_rule=TemporalRule.SYNCHRONIZED_FIELD,
            sync=sync_of[fam],
            min_history=MinHistory(MinHistoryKind.NONE),
            missing=_f7_missing(name),
            availability=_C.Availability.LAP_END,
            predictive_eligible=True,
            status=FeatureStatus.CANDIDATE,
        ))
    return tuple(defs)


F7_DEFINITIONS = _build_f7_definitions()


def register_f7_features(registry: FeatureRegistry) -> FeatureRegistry:
    for d in F7_DEFINITIONS:
        registry.register(d)
    return registry


def build_f7_registry() -> FeatureRegistry:
    from v2.features.gaps import register_gap_features
    from v2.features.pace import register_f5_features
    from v2.features.registry import build_f2_registry
    return register_f7_features(
        register_gap_features(register_f5_features(build_f2_registry())))


def context_for_state(request: FeatureRequest, registry: FeatureRegistry,
                      states: pd.DataFrame, names=None) -> FeatureResult:
    """Single-state F7 computation via F1 field snapshot."""
    from v2.features.registry import validate_definition
    wanted = [d for d in F7_DEFINITIONS
              if names is None or d.name in names]
    if names is not None:
        missing = sorted(set(names) - {d.name for d in wanted})
        if missing:
            raise NoCalculatorError(
                f"context calculator has no features: {missing}")
    for d in wanted:
        validate_definition(d)
    require_columns(states, ("race_id", "driver_id", "lap_number",
                             "state_time_s", "position", "track_state",
                             "constructor_id", "lap_time_s", "pit_in_s",
                             "pit_out_s", "stint_number"),
                    "context_for_state input")
    target = resolve_target(states, request.race_id, request.driver_id,
                            request.lap_number, request.state_time_s)
    roster = sorted({str(v) for v in
                     states[states["race_id"] == request.race_id]
                     ["driver_id"].to_numpy()})
    snap = synchronized_field_snapshot(
        states, request.race_id, request.driver_id,
        int(request.lap_number), float(request.state_time_s), roster)
    entries = {m: s for m, s in snap.entries}
    out = context_for_snapshot(
        target, entries,
        lambda m, sl, st: rival_pace_at_sync(
            states, request.race_id, m, sl, st))
    return FeatureResult(
        race_id=request.race_id,
        driver_id=request.driver_id,
        lap_number=int(request.lap_number),
        state_time_s=float(request.state_time_s),
        feature_set_version=FEATURE_SET_VERSION,
        values=tuple((d.name, out[d.name]) for d in wanted),
        provenance=(("source", "driver_lap_state_d9"),
                    ("calculator", "context-f7")),
    )


def context_batch(states: pd.DataFrame, names=None) -> pd.DataFrame:
    """Batch F7 via exact-state F5 cache + chronological sweep.

    F5 basis pace is computed ONCE per D9 state and keyed by exact
    (driver, lap, time); the sweep synchronizes to rival exact states
    and looks the cached pace up. Cached values are past-only by
    construction (each computed at its own boundary), so reuse is
    temporally safe. Same pure core (``context_for_snapshot``) as
    single-state.
    """
    require_columns(states, ("race_id", "driver_id", "lap_number",
                             "state_time_s", "position", "track_state",
                             "constructor_id", "lap_time_s", "pit_in_s",
                             "pit_out_s", "stint_number"),
                    "context_batch input")
    wanted = [n for n in F7_FEATURE_NAMES if names is None or n in names]
    if names is not None:
        missing = sorted(set(names) - set(F7_FEATURE_NAMES))
        if missing:
            raise NoCalculatorError(
                f"context calculator has no features: {missing}")
    from v2.features.pace import pace_batch as _pace_batch
    from v2.features.temporal import SyncState as _Sync
    pace_all = _pace_batch(states, names=[PACE_BASIS])
    cache: dict = {}
    for _, r in pace_all.iterrows():
        v = r[PACE_BASIS]
        cache[(str(r["driver_id"]), int(r["lap_number"]),
               float(r["state_time_s"]))] = (
            None if (v is None or (isinstance(v, float)
                                   and np.isnan(v))) else float(v))

    def pace_of(m, sl, st):
        return cache.get((str(m), int(sl), float(st)))

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
                out = context_for_snapshot(r, entries, pace_of)
                rec = {"race_id": str(race_id),
                       "driver_id": str(r["driver_id"]),
                       "lap_number": int(r["lap_number"]), "state_time_s": T}
                for n in wanted:
                    rec[n] = out[n]
                rows_out.append(rec)
    cols = ["race_id", "driver_id", "lap_number", "state_time_s"] + wanted
    return pd.DataFrame(rows_out, columns=cols)
