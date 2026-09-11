"""F5 pace feature family (Phase 2 Temporal Feature Engine).

Past-only target-driver pace context over ``driver_prefix(driver, T)``:
eligibility mask, recent eligible windows (3/5/10), a representative
recent pace, current-stint pace, and an honestly named within-stint
pace-trend proxy. No cross-driver information (sync NONE everywhere).

Eligibility (frozen from F5 measurement; 84.42% of D9 states eligible):
lap_time present and > 0, no pit-in/out marker on the lap,
``track_state == 'all_clear'`` (SC/VSC/yellow/red AND unknown excluded
by factual flag, never by speed), lap_number > 1 (standing-start
effects). Slow laps stay eligible: no statistical outlier filtering.
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
    within_stint_prefix,
)

ELIGIBILITY_SOURCES = (
    "driver_lap_state_d9.lap_time_s",
    "driver_lap_state_d9.pit_in_s",
    "driver_lap_state_d9.pit_out_s",
    "driver_lap_state_d9.track_state",
    "driver_lap_state_d9.lap_number",
)

ELIGIBILITY_COLUMNS = ("lap_time_s", "pit_in_s", "pit_out_s", "track_state",
                       "lap_number")

#: Frozen min-history policy (F5 coverage: w3 93.89%, w5 91.97%,
#: w10 88.07%, representative 81.98%, stint 86.68%, trend 72.86%).
MIN_N = {"w3": 2, "w5": 3, "w10": 5, "rep": 8, "stint": 2, "trend": 5}


def pace_eligibility_mask(states: pd.DataFrame) -> pd.Series:
    """Factual eligibility mask over a D9-style frame (vectorized).

    Uses the D9 derived ``track_state`` token (deterministic last-code
    mapping: only ``'all_clear'`` is eligible), NOT the raw
    ``track_status`` code string.
    """
    require_columns(states, ELIGIBILITY_COLUMNS, "pace eligibility input")
    lap_time = states["lap_time_s"]
    return ((lap_time.notna()) & (lap_time > 0)
            & states["pit_in_s"].isna() & states["pit_out_s"].isna()
            & (states["track_state"] == "all_clear")
            & (states["lap_number"] > 1))


def _eligible_tail(lap_times: np.ndarray, eligible: np.ndarray,
                   window: int, min_n: int):
    """Latest-``window`` eligible values (ascending); (vals, n, ok)."""
    vals = np.asarray(lap_times, dtype=float)[np.asarray(eligible, dtype=bool)]
    vals = vals[np.isfinite(vals)][-int(window):]
    return vals, len(vals), len(vals) >= min_n


def _summarize(vals: np.ndarray):
    return float(np.median(vals)), float(np.mean(vals))


def ols_slope(y: np.ndarray) -> float:
    """Closed-form OLS slope of y over progress index 0..k-1.

    Deterministic; no scipy/statsmodels. Constant y yields exactly 0.0;
    x-variance is structurally positive for k >= 2.
    """
    y = np.asarray(y, dtype=float)
    if len(y) < 2:
        raise TemporalError("ols_slope requires >= 2 observations")
    x = np.arange(len(y), dtype=float)
    xm, ym = x.mean(), y.mean()
    den = float(((x - xm) ** 2).sum())
    if den == 0.0:  # unreachable for k>=2; pinned, never silent NaN
        raise TemporalError("degenerate progress index in ols_slope")
    return float(((x - xm) * (y - ym)).sum() / den)


def pace_values(prefix: pd.DataFrame) -> dict:
    """All 12 F5 values for an ordered ``<= T`` driver prefix.

    Shared core used identically by single-state and batch paths.
    Missing history (or unknown stint) yields None per feature.
    """
    require_columns(prefix, ELIGIBILITY_COLUMNS + ("stint_number",),
                    "pace_values input")
    prefix = prefix.sort_values(["state_time_s", "lap_number"],
                                kind="mergesort")
    elig = pace_eligibility_mask(prefix).to_numpy(dtype=bool)
    lt = prefix["lap_time_s"].to_numpy(dtype=float)
    out: dict = {}
    cfgs = [("w3", 3, MIN_N["w3"]), ("w5", 5, MIN_N["w5"]),
            ("w10", 10, MIN_N["w10"])]
    tails = {}
    for tag, window, min_n in cfgs:
        vals, n, ok = _eligible_tail(lt, elig, window, min_n)
        tails[tag] = (vals, n, ok)
        out[f"pace_n_{window}"] = int(n)
    for tag, window, _ in cfgs:
        vals, n, ok = tails[tag]
        out[f"pace_median_{window}"] = float(np.median(vals)) if ok else None
    vals5, _, ok5 = tails["w5"]
    out["pace_mean_5"] = float(np.mean(vals5)) if ok5 else None
    rep_vals, rep_n, rep_ok = _eligible_tail(lt, elig, 10, MIN_N["rep"])
    out["representative_recent_pace_s"] = float(np.median(rep_vals)) \
        if rep_ok else None
    # Current-stint scope: prefix rows sharing the target row's stint.
    stint = within_stint_prefix_by_frame(prefix)
    if stint is None or not len(stint):
        out["current_stint_pace_median_s"] = None
        out["current_stint_pace_mean_s"] = None
        out["current_stint_eligible_laps"] = None
        out["current_stint_pace_trend_s_per_lap"] = None
        return out
    s_elig = pace_eligibility_mask(stint).to_numpy(dtype=bool)
    s_lt = stint["lap_time_s"].to_numpy(dtype=float)
    s_vals_all = s_lt[s_elig]
    s_vals_all = s_vals_all[np.isfinite(s_vals_all)]
    n_stint = len(s_vals_all)
    out["current_stint_eligible_laps"] = int(n_stint)
    if n_stint >= MIN_N["stint"]:
        out["current_stint_pace_median_s"] = float(np.median(s_vals_all))
        out["current_stint_pace_mean_s"] = float(np.mean(s_vals_all))
    else:
        out["current_stint_pace_median_s"] = None
        out["current_stint_pace_mean_s"] = None
    if n_stint >= MIN_N["trend"]:
        out["current_stint_pace_trend_s_per_lap"] = ols_slope(s_vals_all)
    else:
        out["current_stint_pace_trend_s_per_lap"] = None
    return out


def within_stint_prefix_by_frame(prefix: pd.DataFrame) -> pd.DataFrame | None:
    """Current-stint rows of an ordered prefix (None when unknown)."""
    if not len(prefix) or "stint_number" not in prefix.columns:
        return None
    current = prefix.iloc[-1]["stint_number"]
    if current is None or (isinstance(current, float)
                           and np.isnan(current)) or pd.isna(current):
        return None
    return prefix[prefix["stint_number"] == current].copy()


F5_FEATURE_NAMES = (
    "pace_median_3",
    "pace_median_5",
    "pace_mean_5",
    "pace_median_10",
    "pace_n_3",
    "pace_n_5",
    "pace_n_10",
    "representative_recent_pace_s",
    "current_stint_pace_median_s",
    "current_stint_pace_mean_s",
    "current_stint_eligible_laps",
    "current_stint_pace_trend_s_per_lap",
)

_F5_FAMILY = {
    "pace_median_3": FeatureFamily.PACE,
    "pace_median_5": FeatureFamily.PACE,
    "pace_mean_5": FeatureFamily.PACE,
    "pace_median_10": FeatureFamily.PACE,
    "pace_n_3": FeatureFamily.PACE,
    "pace_n_5": FeatureFamily.PACE,
    "pace_n_10": FeatureFamily.PACE,
    "representative_recent_pace_s": FeatureFamily.PACE,
    "current_stint_pace_median_s": FeatureFamily.STINT,
    "current_stint_pace_mean_s": FeatureFamily.STINT,
    "current_stint_eligible_laps": FeatureFamily.STINT,
    "current_stint_pace_trend_s_per_lap": FeatureFamily.STINT,
}

_F5_DTYPE = {
    "pace_n_3": "int64", "pace_n_5": "int64", "pace_n_10": "int64",
    "current_stint_eligible_laps": "int64",
}

_F5_UNIT = {
    "pace_n_3": "count", "pace_n_5": "count", "pace_n_10": "count",
    "current_stint_eligible_laps": "count",
    "current_stint_pace_trend_s_per_lap": "seconds_per_lap",
}

_F5_MIN_HISTORY = {
    "pace_median_3": ("w3", "latest 3 eligible; null unless >= 2"),
    "pace_median_5": ("w5", "latest 5 eligible; null unless >= 3"),
    "pace_mean_5": ("w5", "latest 5 eligible; null unless >= 3"),
    "pace_median_10": ("w10", "latest 10 eligible; null unless >= 5"),
    "pace_n_3": ("w3", "eligible count used (0..3); always available"),
    "pace_n_5": ("w5", "eligible count used (0..5); always available"),
    "pace_n_10": ("w10", "eligible count used (0..10); always available"),
    "representative_recent_pace_s": (
        "rep", "median of latest 10 eligible; null unless >= 8; "
               "high-confidence operating point vs pace_median_10"),
    "current_stint_pace_median_s": (
        "stint", "eligible in current stint; null unless >= 2 or "
                 "stint unknown"),
    "current_stint_pace_mean_s": (
        "stint", "eligible in current stint; null unless >= 2 or "
                 "stint unknown"),
    "current_stint_eligible_laps": (
        "stint", "eligible count in current stint; null when stint unknown"),
    "current_stint_pace_trend_s_per_lap": (
        "trend", "OLS slope over eligible in-stint laps; null unless >= 5; "
                 "proxy only (fuel/traffic/management/evolution confounded)"),
}

_F5_DESCRIPTIONS = {
    "pace_median_3": "Median of the latest 3 pace-eligible lap times "
                     "(robust short-horizon pace).",
    "pace_median_5": "Median of the latest 5 pace-eligible lap times.",
    "pace_mean_5": "Mean of the latest 5 pace-eligible lap times "
                   "(pairs median for skew; matches trend OLS basis).",
    "pace_median_10": "Median of the latest 10 pace-eligible lap times "
                      "(coverage-oriented operating point).",
    "pace_n_3": "Eligible observations used in the 3-window.",
    "pace_n_5": "Eligible observations used in the 5-window.",
    "pace_n_10": "Eligible observations used in the 10-window.",
    "representative_recent_pace_s": "Median of the latest 10 eligible laps "
        "requiring >= 8 (stable representative pace; distinct from "
        "pace_median_10 by its strict minimum).",
    "current_stint_pace_median_s": "Median eligible pace in the currently "
        "observable stint (start side only).",
    "current_stint_pace_mean_s": "Mean eligible pace in the currently "
        "observable stint.",
    "current_stint_eligible_laps": "Eligible lap count in the current stint.",
    "current_stint_pace_trend_s_per_lap": "OLS slope of eligible lap times "
        "over in-stint progress (s/lap). PROXY ONLY: confounded by fuel, "
        "traffic, management, tyre/track evolution, weather; never physical "
        "degradation.",
}

# Counts are always available (0 when nothing eligible yet): NONE.
# Every other F5 feature carries its frozen COUNT minimum.
def _min_history_for(name: str) -> MinHistory:
    if "pace_n" in name:
        return MinHistory(MinHistoryKind.NONE)
    return MinHistory(MinHistoryKind.COUNT,
                      n=MIN_N[_F5_MIN_HISTORY[name][0]])


F5_DEFINITIONS: tuple = tuple(
    FeatureDef(
        name=name,
        family=_F5_FAMILY[name],
        version=1,
        dtype=_F5_DTYPE.get(name, "float64"),
        unit=_F5_UNIT.get(name, "seconds"),
        description=_F5_DESCRIPTIONS[name],
        sources=ELIGIBILITY_SOURCES + (
            ("driver_lap_state_d9.stint_number",)
            if _F5_FAMILY[name] is FeatureFamily.STINT else ()),
        formula_ref=f"v2/features/pace.py::pace_values ({_F5_MIN_HISTORY[name][1]})",
        temporal_rule=TemporalRule.DRIVER_PREFIX,
        sync=SyncRequirement.NONE,
        min_history=_min_history_for(name),
        missing=MissingPolicy.NULL_IF_INSUFFICIENT_HISTORY,
        availability=C.Availability.LAP_END,
        predictive_eligible=True,
        status=FeatureStatus.CANDIDATE,
    )
    for name in F5_FEATURE_NAMES
)


def register_f5_features(registry: FeatureRegistry) -> FeatureRegistry:
    """Register the 12 F5 definitions on a registry (e.g. F2 inventory)."""
    for d in F5_DEFINITIONS:
        registry.register(d)
    return registry


def build_f5_registry() -> FeatureRegistry:
    """Authoritative Phase-2 registry: F2 inventory + 12 F5 features."""
    from v2.features.registry import build_f2_registry
    return register_f5_features(build_f2_registry())


def pace_for_state(request: FeatureRequest, registry: FeatureRegistry,
                   states: pd.DataFrame, names=None) -> FeatureResult:
    """Single-state F5 computation over ``driver_prefix(driver, T)``."""
    from v2.features.registry import validate_definition
    wanted = [d for d in F5_DEFINITIONS
              if names is None or d.name in names]
    if names is not None:
        missing = sorted(set(names) - {d.name for d in wanted})
        if missing:
            raise NoCalculatorError(
                f"pace calculator has no features: {missing}")
    for d in wanted:
        validate_definition(d)
    prefix = driver_prefix(states, request.race_id, request.driver_id,
                           float(request.state_time_s))
    values = pace_values(prefix)
    return FeatureResult(
        race_id=request.race_id,
        driver_id=request.driver_id,
        lap_number=int(request.lap_number),
        state_time_s=float(request.state_time_s),
        feature_set_version=FEATURE_SET_VERSION,
        values=tuple((d.name, values[d.name]) for d in wanted),
        provenance=(("source", "driver_lap_state_d9"),
                    ("calculator", "pace-f5")),
    )


def _tail_stats(vals: list, window: int, min_n: int):
    """Median/mean over the latest-``window`` values; (med, mean, n, ok)."""
    tail = vals[-int(window):]
    n = len(tail)
    if n < min_n:
        return None, None, n
    arr = np.asarray(tail, dtype=float)
    return float(np.median(arr)), float(np.mean(arr)), n


def _is_na(value) -> bool:
    return value is None or (isinstance(value, float)
                             and np.isnan(value)) or pd.isna(value)


def pace_batch(states: pd.DataFrame, names=None) -> pd.DataFrame:
    """Incremental F5 batch using the SAME window semantics as single-state.

    Per (race, driver) walk over temporally ordered rows maintaining the
    eligible-value history (prefix equivalent); each target sees exactly
    the observations ``driver_prefix`` would expose. Not the F15 matrix.
    """
    require_columns(states, ("race_id", "driver_id", "lap_number",
                             "state_time_s") + ELIGIBILITY_COLUMNS
                    + ("stint_number",), "pace_batch input")
    wanted = [n for n in F5_FEATURE_NAMES if names is None or n in names]
    if names is not None:
        missing = sorted(set(names) - set(F5_FEATURE_NAMES))
        if missing:
            raise NoCalculatorError(
                f"pace calculator has no features: {missing}")
    need = set(wanted)
    elig_mask = pace_eligibility_mask(states)
    rows_out = []
    for (race_id, driver_id), group in states.groupby(
            ["race_id", "driver_id"]):
        g = group.sort_values(["state_time_s", "lap_number"],
                              kind="mergesort")
        idx = g.index.to_numpy()
        lt = g["lap_time_s"].to_numpy(dtype=float)
        el = elig_mask.loc[idx].to_numpy(dtype=bool)
        st = g["stint_number"].to_numpy()
        laps = g["lap_number"].to_numpy(dtype=np.int64)
        times = g["state_time_s"].to_numpy(dtype=float)
        hist: list = []
        stint_id = None
        stint_hist: list = []
        stint_known = True
        for i in range(len(g)):
            if _is_na(st[i]):
                stint_id, stint_hist, stint_known = None, [], False
            else:
                if st[i] != stint_id:
                    stint_id, stint_hist = st[i], []
                stint_known = True
            if bool(el[i]) and np.isfinite(lt[i]):
                hist.append(float(lt[i]))
                if stint_known:
                    stint_hist.append(float(lt[i]))
            rec = {"race_id": race_id, "driver_id": driver_id,
                   "lap_number": int(laps[i]), "state_time_s": float(times[i])}
            if need & {"pace_median_3", "pace_n_3"}:
                med, _, n = _tail_stats(hist, 3, MIN_N["w3"])
                if "pace_median_3" in need:
                    rec["pace_median_3"] = med
                if "pace_n_3" in need:
                    rec["pace_n_3"] = int(len(hist[-3:]))
            if need & {"pace_median_5", "pace_mean_5", "pace_n_5"}:
                med, mean, n = _tail_stats(hist, 5, MIN_N["w5"])
                if "pace_median_5" in need:
                    rec["pace_median_5"] = med
                if "pace_mean_5" in need:
                    rec["pace_mean_5"] = mean
                if "pace_n_5" in need:
                    rec["pace_n_5"] = int(len(hist[-5:]))
            if need & {"pace_median_10", "pace_n_10",
                       "representative_recent_pace_s"}:
                med10, _, n10 = _tail_stats(hist, 10, MIN_N["w10"])
                rep, _, _ = _tail_stats(hist, 10, MIN_N["rep"])
                if "pace_median_10" in need:
                    rec["pace_median_10"] = med10
                if "pace_n_10" in need:
                    rec["pace_n_10"] = int(len(hist[-10:]))
                if "representative_recent_pace_s" in need:
                    rec["representative_recent_pace_s"] = rep
            if need & {"current_stint_pace_median_s",
                       "current_stint_pace_mean_s",
                       "current_stint_eligible_laps",
                       "current_stint_pace_trend_s_per_lap"}:
                if not stint_known:
                    if "current_stint_pace_median_s" in need:
                        rec["current_stint_pace_median_s"] = None
                    if "current_stint_pace_mean_s" in need:
                        rec["current_stint_pace_mean_s"] = None
                    if "current_stint_eligible_laps" in need:
                        rec["current_stint_eligible_laps"] = None
                    if "current_stint_pace_trend_s_per_lap" in need:
                        rec["current_stint_pace_trend_s_per_lap"] = None
                else:
                    ns = len(stint_hist)
                    if "current_stint_eligible_laps" in need:
                        rec["current_stint_eligible_laps"] = int(ns)
                    if ns >= MIN_N["stint"]:
                        arr = np.asarray(stint_hist, dtype=float)
                        if "current_stint_pace_median_s" in need:
                            rec["current_stint_pace_median_s"] = float(
                                np.median(arr))
                        if "current_stint_pace_mean_s" in need:
                            rec["current_stint_pace_mean_s"] = float(
                                np.mean(arr))
                    else:
                        if "current_stint_pace_median_s" in need:
                            rec["current_stint_pace_median_s"] = None
                        if "current_stint_pace_mean_s" in need:
                            rec["current_stint_pace_mean_s"] = None
                    if "current_stint_pace_trend_s_per_lap" in need:
                        rec["current_stint_pace_trend_s_per_lap"] = \
                            ols_slope(np.asarray(stint_hist, dtype=float)) \
                            if ns >= MIN_N["trend"] else None
            rows_out.append(rec)
    cols = ["race_id", "driver_id", "lap_number", "state_time_s"] + wanted
    return pd.DataFrame(rows_out, columns=cols)
