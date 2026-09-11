"""F8 temporal rates + momentum (Phase 2 Temporal Feature Engine).

Backward-looking descriptive change only: gap rates (OLS slope over
trailing same-reference valid-seconds points), position change, and
own-pace change. NEVER a projection: no catch time/laps, no future
positions, no outcome interpretation. Relative-pace momentum is
DEFERRED (changing references/contributors make it indefensible here).

Conventions (frozen): gap rate = d(seconds)/d(target lap); negative =
closing. Position change = earlier - current; positive = gained. Pace
change = (median_now - median_anchor)/lap_delta; negative = faster.
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
from v2.features.gaps import GapStatus, gaps_for_snapshot
from v2.features.engine import NoCalculatorError
from v2.features.registry import FEATURE_SET_VERSION, FeatureRegistry
from v2.features.temporal import (
    TemporalError,
    driver_prefix,
    require_columns,
    resolve_target,
    synchronized_field_snapshot,
)

#: Trailing history span in target laps (measured: last-5 covers 84.0%
#: of leader-rate states vs 82.9% for last-3; one robust window only).
RATE_SPAN_LAPS = 5


def ols_slope_xy(x: np.ndarray, y: np.ndarray) -> float:
    """Closed-form OLS slope; requires >= 2 points spanning x > 0."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    if len(x) < 2:
        raise TemporalError("rate requires >= 2 observations")
    if float(x.max() - x.min()) <= 0:
        raise TemporalError("rate requires positive lap span")
    xm, ym = x.mean(), y.mean()
    den = float(((x - xm) ** 2).sum())
    if den == 0.0:
        raise TemporalError("degenerate rate denominator")
    return float(((x - xm) * (y - ym)).sum() / den)


def gap_rate_from_points(points: list) -> float | None:
    """OLS slope over the contiguous trailing same-reference valid run.

    ``points``: ascending (lap, seconds, ref_id, valid) within the
    trailing span, current state last. Walks back from current and
    STOPS at the first invalid or different-reference entry: rates are
    never bridged across identity changes or invalid geometry
    (red/laps-apart/missing). Needs >= 2 points spanning >= 1 lap.
    """
    if not points:
        return None
    cur_lap, _, cur_ref, cur_valid = points[-1]
    if not cur_valid or cur_ref is None:
        return None
    run = []
    for lap, sec, ref, valid in reversed(points):
        if not valid or ref != cur_ref:
            break
        run.append((lap, sec))
    run.reverse()
    if len(run) < 2:
        return None
    laps = np.array([p[0] for p in run], dtype=float)
    secs = np.array([p[1] for p in run], dtype=float)
    if float(laps.max() - laps.min()) <= 0:
        return None
    return ols_slope_xy(laps, secs)


def change_from_anchors(current: float | None, anchor: float | None,
                        lap_delta: int | None) -> float | None:
    """Generic (current - anchor) change; None when inputs unavailable."""
    if current is None or anchor is None or lap_delta is None:
        return None
    if not np.isfinite(current) or not np.isfinite(anchor):
        return None
    if int(lap_delta) <= 0:
        return None
    return float(current - anchor)


def _pos(value) -> int | None:
    try:
        return None if value is None or pd.isna(value) else int(value)
    except (TypeError, ValueError):
        return None


def _num(value) -> float | None:
    try:
        return None if value is None or pd.isna(value) else float(value)
    except (TypeError, ValueError):
        return None


def rate_values_for_target(target_row, history: list) -> dict:
    """Shared core: F8 values from target row + its ascending history.

    ``history``: list of dicts with keys lap, gap_leader (GapResult),
    gap_ahead (GapResult), position, pace_median_5 — all computed at
    their own past boundaries, ending with the current state.
    """
    cur = history[-1]
    # --- gap rates over trailing same-ref valid runs ---
    lead_pts = [(h["lap"],
                 h["gap_leader"].seconds_gap
                 if h["gap_leader"] is not None else None,
                 h["gap_leader"].reference_id
                 if h["gap_leader"] is not None else None,
                 h["gap_leader"].status.value == "valid_seconds"
                 if h["gap_leader"] is not None else False)
                for h in history if h["lap"] >= cur["lap"] - RATE_SPAN_LAPS]
    ahead_pts = [(h["lap"],
                  h["gap_ahead"].seconds_gap
                  if h["gap_ahead"] is not None else None,
                  h["gap_ahead"].reference_id
                  if h["gap_ahead"] is not None else None,
                  h["gap_ahead"].status.value == "valid_seconds"
                  if h["gap_ahead"] is not None else False)
                 for h in history if h["lap"] >= cur["lap"] - RATE_SPAN_LAPS]
    # --- position anchor: latest history state with lap <= N-5 ---
    anchors = [h for h in history if h["lap"] <= cur["lap"] - RATE_SPAN_LAPS]
    anchor = anchors[-1] if anchors else None
    if anchor is None or _pos(anchor["position"]) is None \
            or _pos(cur["position"]) is None:
        pos_change = None
    else:
        pos_change = float(_pos(anchor["position"]) - _pos(cur["position"]))
    # --- pace momentum: medians at current + anchor states ---
    if anchor is None:
        pace_change = None
    else:
        lap_delta = int(cur["lap"] - anchor["lap"])
        v_now = _num(cur.get("pace_median_5"))
        v_old = _num(anchor.get("pace_median_5"))
        if v_now is None or v_old is None or lap_delta <= 0:
            pace_change = None
        else:
            pace_change = (v_now - v_old) / lap_delta
    return {
        "recent_gap_to_leader_change_s_per_lap":
            gap_rate_from_points(lead_pts),
        "recent_gap_to_ahead_change_s_per_lap":
            gap_rate_from_points(ahead_pts),
        "recent_position_change_5laps": pos_change,
        "recent_pace_change_s_per_lap": pace_change,
    }


F8_FEATURE_NAMES = (
    "recent_gap_to_leader_change_s_per_lap",
    "recent_gap_to_ahead_change_s_per_lap",
    "recent_position_change_5laps",
    "recent_pace_change_s_per_lap",
)

_F8_FAMILY = {
    "recent_gap_to_leader_change_s_per_lap": FeatureFamily.RATE,
    "recent_gap_to_ahead_change_s_per_lap": FeatureFamily.RATE,
    "recent_position_change_5laps": FeatureFamily.MOMENTUM,
    "recent_pace_change_s_per_lap": FeatureFamily.MOMENTUM,
}

_F8_META = {
    "recent_gap_to_leader_change_s_per_lap":
        ("float64", "seconds_per_lap",
         "OLS slope over trailing same-leader valid-seconds points "
         "within 5 target laps (>= 2); negative = closing."),
    "recent_gap_to_ahead_change_s_per_lap":
        ("float64", "seconds_per_lap",
         "OLS slope over trailing same-ahead valid-seconds points "
         "within 5 target laps (>= 2); negative = closing."),
    "recent_position_change_5laps":
        ("float64", "count",
         "Position at latest own state with lap <= N-5 minus current "
         "position; positive = gained; never called overtakes."),
    "recent_pace_change_s_per_lap":
        ("float64", "seconds_per_lap",
         "(pace_median_5 now - pace_median_5 at anchor)/lap_delta, "
         "anchor = latest own state with lap <= N-5; negative = faster. "
         "Adjacent medians overlap minimally by construction."),
}


def _f8_missing(name: str):
    from v2.features.contracts import MissingPolicy
    if "gap_to_" in name:
        return MissingPolicy.NULL_IF_INVALID_GEOMETRY
    return MissingPolicy.NULL_IF_INSUFFICIENT_HISTORY


def _build_f8_definitions():
    from v2.features.contracts import (
        FeatureDef, FeatureFamily, FeatureStatus, MinHistory,
        MinHistoryKind, MissingPolicy, SyncRequirement, TemporalRule,
    )
    from v2 import contracts as _C
    sync_of = {"rate": SyncRequirement.SYNCHRONIZED_FIELD,
               "momentum": SyncRequirement.NONE}
    temporal_of = {"rate": TemporalRule.SYNCHRONIZED_FIELD,
                   "momentum": TemporalRule.DRIVER_PREFIX}
    defs = []
    for name in F8_FEATURE_NAMES:
        fam = _F8_FAMILY[name].value
        dtype, unit, desc = _F8_META[name]
        defs.append(FeatureDef(
            name=name,
            family=_F8_FAMILY[name],
            version=1,
            dtype=dtype,
            unit=unit,
            description=desc,
            sources=("driver_lap_state_d9.state_time_s",
                     "driver_lap_state_d9.lap_number",
                     "driver_lap_state_d9.position",
                     "driver_lap_state_d9.track_state",
                     "driver_lap_state_d9.lap_time_s")
            if fam == "rate" else (
                "driver_lap_state_d9.position",)
            if "position_change" in name else (
                "driver_lap_state_d9.lap_time_s",
                "driver_lap_state_d9.pit_in_s",
                "driver_lap_state_d9.pit_out_s",
                "driver_lap_state_d9.track_state",
                "driver_lap_state_d9.lap_number"),
            formula_ref="v2/features/rates.py::rate_values_for_target",
            temporal_rule=temporal_of[fam],
            sync=sync_of[fam],
            min_history=MinHistory(MinHistoryKind.COUNT, n=2),
            missing=_f8_missing(name),
            availability=_C.Availability.LAP_END,
            predictive_eligible=True,
            status=FeatureStatus.CANDIDATE,
        ))
    return tuple(defs)


F8_DEFINITIONS = _build_f8_definitions()


def register_f8_features(registry: FeatureRegistry) -> FeatureRegistry:
    for d in F8_DEFINITIONS:
        registry.register(d)
    return registry


def build_f8_registry() -> FeatureRegistry:
    from v2.features.context import register_f7_features
    from v2.features.gaps import register_gap_features
    from v2.features.pace import register_f5_features
    from v2.features.registry import build_f2_registry
    return register_f8_features(register_f7_features(
        register_gap_features(register_f5_features(build_f2_registry()))))


def _history_for_prefix(states: pd.DataFrame, race_id: str, driver_id: str,
                        T: float, lap_now: int,
                        pace_of, gap_of) -> list:
    """Target's own ascending history with exact-state F5/F6 values.

    ``pace_of(driver, lap, time)`` and ``gap_of(row_dict, entries)``
    are caller-supplied past-only resolvers (single-state computes
    live; batch reads exact-state caches).
    """
    prefix = driver_prefix(states, race_id, driver_id, T)
    prefix = prefix[prefix["lap_number"] >= lap_now - RATE_SPAN_LAPS - 5]
    hist = []
    for _, h in prefix.iterrows():
        hT = float(h["state_time_s"])
        roster = sorted({str(v) for v in
                         states[states["race_id"] == race_id]
                         ["driver_id"].to_numpy()})
        from v2.features.temporal import synchronized_field_snapshot
        snap = synchronized_field_snapshot(
            states, race_id, driver_id, int(h["lap_number"]), hT, roster)
        entries = {m: s for m, s in snap.entries}
        leader_gap, ahead_gap = gap_of(dict(h), entries)
        hist.append({"lap": int(h["lap_number"]),
                     "gap_leader": leader_gap, "gap_ahead": ahead_gap,
                     "position": h.get("position"),
                     "pace_median_5": pace_of(
                         driver_id, int(h["lap_number"]), hT)})
    return hist


def rates_for_state(request: FeatureRequest, registry: FeatureRegistry,
                    states: pd.DataFrame, names=None) -> FeatureResult:
    """Single-state F8 computation over the target's own past states."""
    from v2.features.registry import validate_definition
    wanted = [d for d in F8_DEFINITIONS
              if names is None or d.name in names]
    if names is not None:
        missing = sorted(set(names) - {d.name for d in wanted})
        if missing:
            raise NoCalculatorError(
                f"rates calculator has no features: {missing}")
    for d in wanted:
        validate_definition(d)
    require_columns(states, ("race_id", "driver_id", "lap_number",
                             "state_time_s", "position", "track_state",
                             "lap_time_s", "pit_in_s", "pit_out_s",
                             "stint_number"),
                    "rates_for_state input")
    target = resolve_target(states, request.race_id, request.driver_id,
                            request.lap_number, request.state_time_s)
    T = float(request.state_time_s)
    lap_now = int(request.lap_number)
    from v2.features.pace import pace_for_state as _pace_single

    def pace_of(drv, lap, t):
        res = _pace_single(
            FeatureRequest(request.race_id, drv, lap, t),
            None, states, names=["pace_median_5"])
        return res.value_dict().get("pace_median_5")

    hist = _history_for_prefix(
        states, request.race_id, request.driver_id, T, lap_now, pace_of,
        gaps_for_snapshot)
    vals = rate_values_for_target(target, hist)
    return FeatureResult(
        race_id=request.race_id,
        driver_id=request.driver_id,
        lap_number=lap_now,
        state_time_s=T,
        feature_set_version=FEATURE_SET_VERSION,
        values=tuple((d.name, vals[d.name]) for d in wanted),
        provenance=(("source", "driver_lap_state_d9"),
                    ("calculator", "rates-f8")),
    )


def _sweep_gap_results(states: pd.DataFrame) -> dict:
    """Per-exact-state (leader_gap, ahead_gap) via chronological sweep.

    Same sweep mechanics and same pure core (``gaps_for_snapshot``) as
    ``gap_batch``: equal-``state_time_s`` groups enter the latest-map
    before any of their targets resolve, so same-T rivals are visible
    exactly as the <= T rule requires. Stored GapResults carry
    reference ids, which scalar caches cannot.
    """
    from v2.features.temporal import SyncState as _Sync
    require_columns(states, ("race_id", "driver_id", "lap_number",
                             "state_time_s", "position", "track_state"),
                    "gap sweep input")
    out: dict = {}
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
                leader_gap, ahead_gap = gaps_for_snapshot(dict(r), entries)
                out[(str(race_id), str(r["driver_id"]), int(r["lap_number"]),
                     T)] = (leader_gap, ahead_gap)
    return out


def rates_batch(states: pd.DataFrame, names=None) -> pd.DataFrame:
    """Batch F8 via exact-state caches + chronological per-driver trails.

    The sweep caches full GapResults (with reference ids) and F5 basis
    pace per exact state — every cached value past-only by
    construction. Each target's trailing history assembles from cache;
    the shared pure core (``rate_values_for_target``) matches
    single-state exactly.
    """
    require_columns(states, ("race_id", "driver_id", "lap_number",
                             "state_time_s", "position", "track_state",
                             "lap_time_s"),
                    "rates_batch input")
    wanted = [n for n in F8_FEATURE_NAMES if names is None or n in names]
    if names is not None:
        missing = sorted(set(names) - set(F8_FEATURE_NAMES))
        if missing:
            raise NoCalculatorError(
                f"rates calculator has no features: {missing}")
    from v2.features.pace import pace_batch as _pace_batch
    gap_results = _sweep_gap_results(states)
    pb = _pace_batch(states, names=["pace_median_5"])
    pace_cache: dict = {}
    for _, r in pb.iterrows():
        v = r["pace_median_5"]
        pace_cache[(str(r["race_id"]), str(r["driver_id"]),
                    int(r["lap_number"]),
                    float(r["state_time_s"]))] = (
            None if (v is None or (isinstance(v, float)
                                   and np.isnan(v))) else float(v))
    out_rows = []
    for (race_id, group) in states.groupby("race_id", sort=True):
        g = group.sort_values(["state_time_s", "lap_number", "driver_id"],
                              kind="mergesort")
        trails: dict = {}
        for _, r in g.iterrows():
            drv = str(r["driver_id"])
            lap = int(r["lap_number"])
            T = float(r["state_time_s"])
            key = (str(race_id), drv, lap, T)
            leader_gap, ahead_gap = gap_results[key]
            trail = trails.setdefault(drv, [])
            trail.append({"lap": lap, "gap_leader": leader_gap,
                          "gap_ahead": ahead_gap,
                          "position": r.get("position"),
                          "pace_median_5": pace_cache.get(
                              (str(race_id), drv, lap, T))})
            # trailing window bound: target span + anchor reach
            while trail and trail[0]["lap"] < lap - RATE_SPAN_LAPS - 5 \
                    and len(trail) > 12:
                trail.pop(0)
            vals = rate_values_for_target(dict(r), trail)
            rec = {"race_id": str(race_id), "driver_id": drv,
                   "lap_number": lap, "state_time_s": T}
            for n in wanted:
                rec[n] = vals[n]
            out_rows.append(rec)
    cols = ["race_id", "driver_id", "lap_number", "state_time_s"] + wanted
    return pd.DataFrame(out_rows, columns=cols)
