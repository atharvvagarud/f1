"""F9 weather + race-control temporal context (Phase 2).

Backward-looking HISTORY only (F4 already exposes current values and
must not be duplicated): 5-minute weather deltas/rainfall context from
the distinct observation series along the target's own prefix, and
structural track-state duration/transitions/caution fractions from the
target's own token series. Race-clock windows (seconds), never
driver-lap windows. No forecasts, no NLP, no interactions.

Conventions (frozen): deltas = current − historical anchor (positive =
warmer now); anchor = latest distinct observation ≤ T−300; fractions =
known-state duration / known-covered duration over [T−300, T] (>= 60 s
covered else null; unknown intervals excluded, never assumed clear);
current-state duration is a lower bound ("held at least X").
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
from v2.features.registry import FEATURE_SET_VERSION, FeatureRegistry
from v2.features.temporal import (
    TemporalError,
    driver_prefix,
    require_columns,
    resolve_target,
)

#: Universal F9 history window (race-clock seconds). 60 s weather
#: cadence gives ~5 observations per window; token runs are far longer.
HISTORY_S = 300.0

#: Minimum known-covered duration for fractions (else null).
MIN_COVERED_S = 60.0

CAUTION_SETS = {
    "yellow": {"yellow"},
    "sc_vsc": {"safety_car", "vsc", "vsc_ending"},
    "red": {"red_flag"},
}


def _num(value) -> float | None:
    try:
        return None if value is None or pd.isna(value) else float(value)
    except (TypeError, ValueError):
        return None


def _tok(value) -> str | None:
    try:
        return None if value is None or pd.isna(value) else str(value)
    except (TypeError, ValueError):
        return None


def _is_rain(value) -> bool | None:
    """Rainfall source-bool with honest nulls (None = unknown)."""
    if value is None or (not isinstance(value, (bool, np.bool_))
                         and pd.isna(value)):
        return None
    return bool(value)


def distinct_observations(times: np.ndarray, values: np.ndarray):
    """Distinct (time, value) observations, ascending, last-wins ties."""
    best: dict = {}
    for t, v in zip(np.asarray(times, dtype=float),
                    np.asarray(values, dtype=object)):
        if np.isfinite(t):
            best[float(t)] = v
    return sorted(best.items())


def weather_values(obs: dict, T: float) -> dict:
    """4 weather-history features from distinct obs {time: row} ≤ T.

    ``obs`` maps observation time -> mapping with air/track temp and
    rainfall. Current = latest ≤ T; anchor = latest ≤ T−300.
    """
    W = HISTORY_S
    cur = anc = None
    for t in sorted(obs):
        if t <= T:
            cur = t
        if t <= T - W:
            anc = t
    out: dict = {}
    air_now = _num(obs[cur].get("wx_air_temp_c")) if cur is not None else None
    air_old = _num(obs[anc].get("wx_air_temp_c")) if anc is not None else None
    trk_now = _num(obs[cur].get("wx_track_temp_c")) if cur is not None else None
    trk_old = _num(obs[anc].get("wx_track_temp_c")) if anc is not None else None
    out["air_temp_change_5min_c"] = (air_now - air_old
                                    if air_now is not None
                                    and air_old is not None else None)
    out["track_temp_change_5min_c"] = (trk_now - trk_old
                                      if trk_now is not None
                                      and trk_old is not None else None)
    window = [(t, obs[t]) for t in sorted(obs) if T - W < t <= T]
    rains = [_is_rain(r.get("wx_rainfall")) for _, r in window]
    if not window:
        out["rain_in_last_5min"] = None
    elif any(r is None for r in rains):
        # Unknown samples exist: True only on positive evidence, False
        # only when every sample is known-dry; else null.
        if any(r is True for r in rains):
            out["rain_in_last_5min"] = True
        elif all(r is False for r in rains):
            out["rain_in_last_5min"] = False
        else:
            out["rain_in_last_5min"] = None
    else:
        out["rain_in_last_5min"] = bool(any(rains))
    rainy = [t for t in sorted(obs)
             if t <= T and _is_rain(obs[t].get("wx_rainfall")) is True]
    out["time_since_rain_observed_s"] = (T - max(rainy)
                                        if rainy else None)
    return out


def track_values(times: np.ndarray, tokens: list, T: float) -> dict:
    """5 track-state-history features from the target's token series."""
    W = HISTORY_S
    ts = np.asarray(times, dtype=float)
    tk = [_tok(v) for v in tokens]
    out: dict = {}
    cur = tk[-1] if tk else None
    if cur is None:
        out["current_track_state_duration_s"] = None
    else:
        k = len(tk) - 1
        while k >= 0 and tk[k] == cur:
            k -= 1
        out["current_track_state_duration_s"] = float(T - ts[k + 1])
    changes = 0
    for i in range(1, len(ts)):
        if ts[i] <= T - W or ts[i] > T:
            continue
        a, b = tk[i - 1], tk[i]
        if a is not None and b is not None and a != b:
            changes += 1
    out["track_state_changes_5min"] = int(changes)
    covered = {"yellow": 0.0, "sc_vsc": 0.0, "red": 0.0, "known": 0.0}
    for i in range(1, len(ts)):
        a = max(float(ts[i - 1]), T - W)
        b = min(float(ts[i]), T)
        if b <= a:
            continue
        tok = tk[i]
        if tok is None:
            continue  # unknown: excluded, never assumed clear
        covered["known"] += b - a
        for key, states in CAUTION_SETS.items():
            if tok in states:
                covered[key] += b - a
    if covered["known"] < MIN_COVERED_S:
        out["recent_yellow_fraction_5min"] = None
        out["recent_sc_vsc_fraction_5min"] = None
        out["recent_red_fraction_5min"] = None
    else:
        out["recent_yellow_fraction_5min"] = covered["yellow"] / covered["known"]
        out["recent_sc_vsc_fraction_5min"] = covered["sc_vsc"] / covered["known"]
        out["recent_red_fraction_5min"] = covered["red"] / covered["known"]
    return out


F9_FEATURE_NAMES = (
    "air_temp_change_5min_c",
    "track_temp_change_5min_c",
    "rain_in_last_5min",
    "time_since_rain_observed_s",
    "current_track_state_duration_s",
    "track_state_changes_5min",
    "recent_yellow_fraction_5min",
    "recent_sc_vsc_fraction_5min",
    "recent_red_fraction_5min",
)

_F9_FAMILY = {
    "air_temp_change_5min_c": FeatureFamily.WEATHER,
    "track_temp_change_5min_c": FeatureFamily.WEATHER,
    "rain_in_last_5min": FeatureFamily.WEATHER,
    "time_since_rain_observed_s": FeatureFamily.WEATHER,
    "current_track_state_duration_s": FeatureFamily.RACE_CONTROL,
    "track_state_changes_5min": FeatureFamily.RACE_CONTROL,
    "recent_yellow_fraction_5min": FeatureFamily.RACE_CONTROL,
    "recent_sc_vsc_fraction_5min": FeatureFamily.RACE_CONTROL,
    "recent_red_fraction_5min": FeatureFamily.RACE_CONTROL,
}

_F9_META = {
    "air_temp_change_5min_c":
        ("float64", "°C", "NULL_IF_INSUFFICIENT_HISTORY",
         "Current as-of air temp minus latest distinct observation "
         "<= T-300 s; positive = warmer now."),
    "track_temp_change_5min_c":
        ("float64", "°C", "NULL_IF_INSUFFICIENT_HISTORY",
         "Current as-of track temp minus anchor <= T-300 s."),
    "rain_in_last_5min":
        ("bool", "boolean", "NULL_IF_INSUFFICIENT_HISTORY",
         "Any observation in (T-300, T] with rainfall True; null when "
         "the window holds no observation."),
    "time_since_rain_observed_s":
        ("float64", "seconds", "NULL_IF_INSUFFICIENT_HISTORY",
         "T minus latest rainfall-True observation <= T (NOT time since "
         "rain stopped); null when never observed rainy."),
    "current_track_state_duration_s":
        ("float64", "seconds", "PRESERVE_SOURCE_NULL",
         "T minus first row of the current token run (lower bound: "
         "state has held at least this long); null when token unknown."),
    "track_state_changes_5min":
        ("int64", "count", "NULL_IF_NOT_APPLICABLE",
         "Known-token transitions with row time in (T-300, T]; "
         "always defined (0 allowed)."),
    "recent_yellow_fraction_5min":
        ("float64", "fraction", "NULL_IF_INSUFFICIENT_HISTORY",
         "Yellow duration / known-covered duration over [T-300, T]; "
         "null when covered < 60 s."),
    "recent_sc_vsc_fraction_5min":
        ("float64", "fraction", "NULL_IF_INSUFFICIENT_HISTORY",
         "Safety-car/VSC duration share (neutralized running)."),
    "recent_red_fraction_5min":
        ("float64", "fraction", "NULL_IF_INSUFFICIENT_HISTORY",
         "Red-flag suspension share (session time, not racing time)."),
}


def _build_f9_definitions():
    from v2.features.contracts import (
        FeatureDef, FeatureFamily, FeatureStatus, MinHistory,
        MinHistoryKind, MissingPolicy, SyncRequirement, TemporalRule,
    )
    from v2 import contracts as _C
    defs = []
    for name in F9_FEATURE_NAMES:
        dtype, unit, missing, desc = _F9_META[name]
        defs.append(FeatureDef(
            name=name,
            family=_F9_FAMILY[name],
            version=1,
            dtype=dtype,
            unit=unit,
            description=desc,
            sources=("driver_lap_state_d9.wx_observed_at_s",
                     "driver_lap_state_d9.wx_air_temp_c",
                     "driver_lap_state_d9.wx_track_temp_c",
                     "driver_lap_state_d9.wx_rainfall")
            if _F9_FAMILY[name] is FeatureFamily.WEATHER else (
                "driver_lap_state_d9.state_time_s",
                "driver_lap_state_d9.track_state"),
            formula_ref="v2/features/environment.py::weather_values / "
                        "track_values (300 s race-clock window)",
            temporal_rule=TemporalRule.DRIVER_PREFIX,
            sync=SyncRequirement.NONE,
            min_history=MinHistory(MinHistoryKind.NONE),
            missing=getattr(MissingPolicy, missing),
            availability=_C.Availability.LAP_END,
            predictive_eligible=True,
            status=FeatureStatus.CANDIDATE,
        ))
    return tuple(defs)


F9_DEFINITIONS = _build_f9_definitions()


def register_f9_features(registry) -> FeatureRegistry:
    for d in F9_DEFINITIONS:
        registry.register(d)
    return registry


def build_f9_registry() -> FeatureRegistry:
    from v2.features.context import register_f7_features
    from v2.features.gaps import register_gap_features
    from v2.features.pace import register_f5_features
    from v2.features.rates import register_f8_features
    from v2.features.registry import build_f2_registry
    return register_f9_features(register_f8_features(
        register_f7_features(register_gap_features(
            register_f5_features(build_f2_registry())))))


def _prefix_arrays(prefix: pd.DataFrame, T: float):
    """Own-prefix observation + token series (all <= T by construction)."""
    from v2.features.temporal import require_columns as _req
    _req(prefix, ("state_time_s", "track_state", "wx_observed_at_s",
                  "wx_air_temp_c", "wx_track_temp_c", "wx_rainfall"),
         "environment input")
    sub = prefix[prefix["state_time_s"] <= T].sort_values(
        ["state_time_s", "lap_number"], kind="mergesort")
    obs: dict = {}
    for _, r in sub.iterrows():
        t = _num(r["wx_observed_at_s"])
        if t is None or t > T:
            continue
        obs[float(t)] = {"wx_air_temp_c": r["wx_air_temp_c"],
                         "wx_track_temp_c": r["wx_track_temp_c"],
                         "wx_rainfall": r["wx_rainfall"]}
    return (sub["state_time_s"].to_numpy(dtype=float),
            [_tok(v) for v in sub["track_state"].tolist()], obs)


def environment_for_state(request, registry: FeatureRegistry,
                          states: pd.DataFrame, names=None):
    """Single-state F9 computation over the target's own prefix."""
    from v2.features.registry import validate_definition
    wanted = [d for d in F9_DEFINITIONS
              if names is None or d.name in names]
    if names is not None:
        missing = sorted(set(names) - {d.name for d in wanted})
        if missing:
            raise NoCalculatorError(
                f"environment calculator has no features: {missing}")
    for d in wanted:
        validate_definition(d)
    target = resolve_target(states, request.race_id, request.driver_id,
                            request.lap_number, request.state_time_s)
    T = float(request.state_time_s)
    prefix = driver_prefix(states, request.race_id, request.driver_id, T)
    times, tokens, obs = _prefix_arrays(prefix, T)
    vals = {**weather_values(obs, T), **track_values(times, tokens, T)}
    return FeatureResult(
        race_id=request.race_id,
        driver_id=request.driver_id,
        lap_number=int(request.lap_number),
        state_time_s=T,
        feature_set_version=FEATURE_SET_VERSION,
        values=tuple((d.name, vals[d.name]) for d in wanted),
        provenance=(("source", "driver_lap_state_d9"),
                    ("calculator", "environment-f9")),
    )


def environment_batch(states: pd.DataFrame, names=None) -> pd.DataFrame:
    """Batch F9 via per-driver incremental own-history walk.

    Each target sees exactly its own prefix observations (same pure
    cores as single-state). No cross-driver data, no rescan per target
    beyond the bounded per-driver walk.
    """
    require_columns(states, ("race_id", "driver_id", "lap_number",
                             "state_time_s", "track_state",
                             "wx_observed_at_s", "wx_air_temp_c",
                             "wx_track_temp_c", "wx_rainfall"),
                    "environment_batch input")
    wanted = [n for n in F9_FEATURE_NAMES if names is None or n in names]
    if names is not None:
        missing = sorted(set(names) - set(F9_FEATURE_NAMES))
        if missing:
            raise NoCalculatorError(
                f"environment calculator has no features: {missing}")
    rows_out = []
    for (race_id, driver_id), group in states.groupby(
            ["race_id", "driver_id"]):
        g = group.sort_values(["state_time_s", "lap_number"],
                              kind="mergesort")
        times_all = g["state_time_s"].to_numpy(dtype=float)
        toks_all = [_tok(v) for v in g["track_state"].tolist()]
        wx_t = g["wx_observed_at_s"].to_numpy(dtype=float)
        obs: dict = {}
        seen_times: list = []
        seen_toks: list = []
        for i in range(len(g)):
            T = float(times_all[i])
            ot = wx_t[i]
            if np.isfinite(ot) and ot <= T and float(ot) not in obs:
                obs[float(ot)] = {
                    "wx_air_temp_c": g["wx_air_temp_c"].to_numpy()[i],
                    "wx_track_temp_c": g["wx_track_temp_c"].to_numpy()[i],
                    "wx_rainfall": g["wx_rainfall"].to_numpy()[i]}
            seen_times.append(T)
            seen_toks.append(toks_all[i])
            vals = {**weather_values(obs, T),
                    **track_values(np.asarray(seen_times),
                                   list(seen_toks), T)}
            rec = {"race_id": race_id, "driver_id": driver_id,
                   "lap_number": int(g["lap_number"].to_numpy()[i]),
                   "state_time_s": T}
            for n in wanted:
                rec[n] = vals[n]
            rows_out.append(rec)
    cols = ["race_id", "driver_id", "lap_number", "state_time_s"] + wanted
    return pd.DataFrame(rows_out, columns=cols)
