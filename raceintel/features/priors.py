"""F10 pre-race grid + past-race priors (Phase 2).

Race-boundary context: factual grid from D5 results; driver/constructor
priors from Tier-B history (deep, uniform); circuit priors from Tier-A
same-circuit editions. The firewall is structural: every history query
passes ``history_before()`` (H < R on frozen chronology), so the
current race and future races are inexpressible as priors.

Outcome semantics (frozen): started = position_text != 'W'; classified
= numeric position_text; mean_finish over classified only; points over
all starts (zeros included); grids over earned slots (> 0 — pit-lane 0
is factual context, not qualifying pace); W/DNS excluded everywhere;
R/D excluded from finish means. No reliability rates of any kind.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from raceintel import contracts as C
from raceintel.features.contracts import (
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
from raceintel.features.engine import NoCalculatorError
from raceintel.features.registry import FEATURE_SET_VERSION, FeatureRegistry
from raceintel.features.temporal import TemporalError, require_columns

#: Frozen minima (measured §1: >=3 prior starts at 98.1% of targets).
DRIVER_MIN_N = 3
CONSTRUCTOR_MIN_N = 3
CIRCUIT_MIN_EDITIONS = 2
RECENT_N = 5


@dataclass(frozen=True)
class PriorHistory:
    """Frozen history bundle (no current-race filtering inside)."""

    hist_results: pd.DataFrame    # Tier-B: season,round_no,driver_id,
    # constructor_id,grid,position,position_text,points
    hist_races: pd.DataFrame      # Tier-B: season,round_no,circuit_id
    results_tiera: pd.DataFrame   # D5: race_id,driver_id,grid_position,...
    races_tiera: pd.DataFrame     # D5 races: race_id,season,round_no,circuit_id
    pit_stops: pd.DataFrame       # D5: race_id,driver_id,...


def _num(value) -> float | None:
    try:
        return None if value is None or pd.isna(value) else float(value)
    except (TypeError, ValueError):
        return None


def history_before(hist: pd.DataFrame, season_col: str, round_col: str,
                   season: int, round_no: int) -> pd.DataFrame:
    """Centralized firewall: strictly prior races only (H < R)."""
    require_columns(hist, (season_col, round_col), "history_before input")
    return hist[((hist[season_col] < int(season)))
                | ((hist[season_col] == int(season))
                   & (hist[round_col] < int(round_no)))].copy()


def _classify(hb: pd.DataFrame) -> pd.DataFrame:
    """Add started/classified/numeric-position semantics (frozen §9)."""
    out = hb.copy()
    out["_numpos"] = pd.to_numeric(out["position_text"], errors="coerce")
    out["_started"] = out["position_text"] != "W"
    return out


def resolve_grid(results_tiera: pd.DataFrame, race_id: str,
                 driver_id: str):
    """Factual grid_position (D5 results identity join); null if missing.

    Pit-lane 0 preserved as the factual code (never imputed, never
    re-slotted). No other results column is read here.
    """
    require_columns(results_tiera, ("race_id", "driver_id", "grid_position"),
                    "grid resolver input")
    hit = results_tiera[(results_tiera["race_id"] == race_id)
                        & (results_tiera["driver_id"] == driver_id)]
    if not len(hit):
        return None
    if len(hit) > 1:
        raise TemporalError(
            f"duplicate results key for {(race_id, driver_id)}: "
            f"explicit failure, never silent selection")
    return _num(hit.iloc[0]["grid_position"])


def driver_priors(hist_results: pd.DataFrame, driver_id: str,
                  season: int, round_no: int) -> dict:
    """Driver priors from Tier-B H < R (started/classified semantics)."""
    past = _classify(history_before(hist_results, "season", "round_no",
                                    season, round_no))
    rows = past[(past["driver_id"] == driver_id) & (past["_started"])]
    rows = rows.sort_values(["season", "round_no"], kind="mergesort")
    starts = len(rows)
    out = {"prior_driver_starts": int(starts)}
    cls = rows[rows["_numpos"].notna()]
    out["prior_driver_mean_finish"] = float(cls["position"].mean()) \
        if len(cls) >= DRIVER_MIN_N else None
    out["prior_driver_points_per_start"] = float(rows["points"].sum()
                                                 / starts) \
        if starts >= DRIVER_MIN_N else None
    grids = rows[pd.to_numeric(rows["grid"], errors="coerce") > 0]
    out["prior_driver_mean_grid"] = float(grids["grid"].mean()) \
        if len(grids) >= DRIVER_MIN_N else None
    recent = rows.tail(RECENT_N)
    rcls = recent[recent["_numpos"].notna()]
    out["recent_driver_mean_finish_5"] = float(rcls["position"].mean()) \
        if len(rcls) >= DRIVER_MIN_N else None
    return out


def constructor_priors(hist_results: pd.DataFrame, constructor_id,
                       season: int, round_no: int) -> dict:
    """Constructor priors (per-entry denominators) from H < R."""
    if constructor_id is None or pd.isna(constructor_id):
        return {"prior_constructor_races": None,
                "prior_constructor_points_per_entry": None,
                "prior_constructor_mean_finish": None,
                "recent_constructor_points_per_entry_5": None}
    past = _classify(history_before(hist_results, "season", "round_no",
                                    season, round_no))
    rows = past[(past["constructor_id"] == str(constructor_id))
                & (past["_started"])]
    rows = rows.sort_values(["season", "round_no"], kind="mergesort")
    races = rows.drop_duplicates(["season", "round_no"])
    out = {"prior_constructor_races": int(len(races))}
    out["prior_constructor_points_per_entry"] = \
        float(rows["points"].sum() / len(rows)) \
        if len(rows) >= CONSTRUCTOR_MIN_N else None
    cls = rows[rows["_numpos"].notna()]
    out["prior_constructor_mean_finish"] = float(cls["position"].mean()) \
        if len(cls) >= CONSTRUCTOR_MIN_N else None
    recent_races = races.tail(RECENT_N)[["season", "round_no"]]
    recent = rows.merge(recent_races, on=["season", "round_no"])
    out["recent_constructor_points_per_entry_5"] = \
        float(recent["points"].sum() / len(recent)) \
        if len(recent) >= CONSTRUCTOR_MIN_N else None
    return out


def circuit_priors(races_tiera: pd.DataFrame, results_tiera: pd.DataFrame,
                   pit_stops: pd.DataFrame, circuit_id,
                   season: int, round_no: int) -> dict:
    """Circuit priors from same-circuit Tier-A editions H < R only."""
    if circuit_id is None or pd.isna(circuit_id):
        return {"prior_circuit_races": None,
                "prior_circuit_mean_pit_stops_per_entry": None,
                "prior_circuit_mean_position_change": None}
    prior = history_before(races_tiera, "season", "round_no", season,
                           round_no)
    prior = prior[prior["circuit_id"] == str(circuit_id)]
    out = {"prior_circuit_races": int(len(prior))}
    if len(prior) < CIRCUIT_MIN_EDITIONS:
        out["prior_circuit_mean_pit_stops_per_entry"] = None
        out["prior_circuit_mean_position_change"] = None
        return out
    pits, changes = [], []
    for _, r in prior.iterrows():
        rid = r["race_id"]
        entries = results_tiera[results_tiera["race_id"] == rid]
        if len(entries):
            n_pits = int((pit_stops["race_id"] == rid).sum())
            pits.append(n_pits / len(entries))
            grid = pd.to_numeric(entries["grid_position"], errors="coerce")
            fin = pd.to_numeric(entries["position_final"], errors="coerce")
            ok = entries[(grid > 0) & grid.notna() & fin.notna()]
            if len(ok):
                changes.append(float(
                    (pd.to_numeric(ok["grid_position"])
                     - pd.to_numeric(ok["position_final"])).mean()))
    out["prior_circuit_mean_pit_stops_per_entry"] = float(np.mean(pits)) \
        if pits else None
    out["prior_circuit_mean_position_change"] = float(np.mean(changes)) \
        if changes else None
    return out


F10_FEATURE_NAMES = (
    "grid_position",
    "prior_driver_starts",
    "prior_driver_mean_finish",
    "prior_driver_points_per_start",
    "prior_driver_mean_grid",
    "recent_driver_mean_finish_5",
    "prior_constructor_races",
    "prior_constructor_points_per_entry",
    "prior_constructor_mean_finish",
    "recent_constructor_points_per_entry_5",
    "prior_circuit_races",
    "prior_circuit_mean_pit_stops_per_entry",
    "prior_circuit_mean_position_change",
)

_F10_FAMILY = {
    "grid_position": FeatureFamily.GRID,
    "prior_driver_starts": FeatureFamily.DRIVER_PRIOR,
    "prior_driver_mean_finish": FeatureFamily.DRIVER_PRIOR,
    "prior_driver_points_per_start": FeatureFamily.DRIVER_PRIOR,
    "prior_driver_mean_grid": FeatureFamily.DRIVER_PRIOR,
    "recent_driver_mean_finish_5": FeatureFamily.DRIVER_PRIOR,
    "prior_constructor_races": FeatureFamily.CONSTRUCTOR_PRIOR,
    "prior_constructor_points_per_entry": FeatureFamily.CONSTRUCTOR_PRIOR,
    "prior_constructor_mean_finish": FeatureFamily.CONSTRUCTOR_PRIOR,
    "recent_constructor_points_per_entry_5":
        FeatureFamily.CONSTRUCTOR_PRIOR,
    "prior_circuit_races": FeatureFamily.CIRCUIT,
    "prior_circuit_mean_pit_stops_per_entry": FeatureFamily.CIRCUIT,
    "prior_circuit_mean_position_change": FeatureFamily.CIRCUIT,
}

_F10_META = {
    # name: (dtype, unit, missing, min_kind, min_n, description)
    "grid_position": ("int64", "position", "NULL_IF_NOT_APPLICABLE",
                      "NONE", 0, "Factual D5 starting grid (pit-lane 0 "
                      "preserved as the factual code; 3 known W-nulls)."),
    "prior_driver_starts": ("int64", "count", "NULL_IF_NOT_APPLICABLE",
                            "NONE", 0, "Prior Tier-B starts "
                            "(position_text != W); 0 for rookies."),
    "prior_driver_mean_finish": ("float64", "position",
                                 "NULL_IF_INSUFFICIENT_HISTORY",
                                 "COUNT", 3, "Mean classified finish over "
                                 "all prior starts (>= 3 classified)."),
    "prior_driver_points_per_start": ("float64", "points",
                                      "NULL_IF_INSUFFICIENT_HISTORY",
                                      "COUNT", 3, "Points per start over "
                                      "all prior starts (>= 3 starts)."),
    "prior_driver_mean_grid": ("float64", "position",
                               "NULL_IF_INSUFFICIENT_HISTORY",
                               "COUNT", 3, "Mean earned grid (> 0) over "
                               "prior starts (>= 3)."),
    "recent_driver_mean_finish_5": ("float64", "position",
                                    "NULL_IF_INSUFFICIENT_HISTORY",
                                    "COUNT", 3, "Mean classified finish "
                                    "over trailing 5 starts (>= 3 "
                                    "classified within)."),
    "prior_constructor_races": ("int64", "count", "NULL_IF_NOT_APPLICABLE",
                                "NONE", 0, "Prior team-races (>= 1 "
                                "starter); 0 for new entities."),
    "prior_constructor_points_per_entry": ("float64", "points",
                                           "NULL_IF_INSUFFICIENT_HISTORY",
                                           "COUNT", 3, "Points per entry "
                                           "over prior starts (>= 3 "
                                           "entries)."),
    "prior_constructor_mean_finish": ("float64", "position",
                                      "NULL_IF_INSUFFICIENT_HISTORY",
                                      "COUNT", 3, "Mean classified finish "
                                      "per entry (>= 3 classified)."),
    "recent_constructor_points_per_entry_5": ("float64", "points",
                                              "NULL_IF_INSUFFICIENT_HISTORY",
                                              "COUNT", 3, "Points per entry "
                                              "over trailing 5 team-races "
                                              "(>= 3 entries)."),
    "prior_circuit_races": ("int64", "count", "NULL_IF_NOT_APPLICABLE",
                            "NONE", 0, "Prior same-circuit Tier-A editions; "
                            "0 for debut venues."),
    "prior_circuit_mean_pit_stops_per_entry": ("float64", "count",
                                               "NULL_IF_INSUFFICIENT_HISTORY",
                                               "COUNT", 2, "Mean over "
                                               "editions of pit stops per "
                                               "entry (>= 2 editions)."),
    "prior_circuit_mean_position_change": ("float64", "position",
                                           "NULL_IF_INSUFFICIENT_HISTORY",
                                           "COUNT", 2, "Mean over editions "
                                           "of edition-mean(grid - final) "
                                           "over earned+classified entries "
                                           "(>= 2 editions with data)."),
}

_F10_SOURCES = {
    "grid_position": ("results.grid_position",),
    "prior_driver_starts": ("hist_results.position_text",),
    "prior_driver_mean_finish": ("hist_results.position",
                                 "hist_results.position_text"),
    "prior_driver_points_per_start": ("hist_results.points",
                                      "hist_results.position_text"),
    "prior_driver_mean_grid": ("hist_results.grid",
                               "hist_results.position_text"),
    "recent_driver_mean_finish_5": ("hist_results.position",
                                    "hist_results.position_text"),
    "prior_constructor_races": ("hist_results.constructor_id",),
    "prior_constructor_points_per_entry": ("hist_results.points",
                                           "hist_results.constructor_id",
                                           "hist_results.position_text"),
    "prior_constructor_mean_finish": ("hist_results.position",
                                      "hist_results.constructor_id",
                                      "hist_results.position_text"),
    "recent_constructor_points_per_entry_5": ("hist_results.points",
                                              "hist_results.constructor_id",
                                              "hist_results.position_text"),
    "prior_circuit_races": ("races.circuit_id",),
    "prior_circuit_mean_pit_stops_per_entry": ("pit_stops.race_id",
                                               "results.race_id"),
    "prior_circuit_mean_position_change": ("results.grid_position",
                                           "results.position_final"),
}

_F10_TEMPORAL = {
    "grid_position": "PRE_RACE",
}


def _build_f10_definitions():
    from raceintel.features.contracts import (
        FeatureDef, FeatureFamily, FeatureStatus, MinHistory,
        MinHistoryKind, MissingPolicy, SyncRequirement, TemporalRule,
    )
    from raceintel import contracts as _C
    defs = []
    for name in F10_FEATURE_NAMES:
        if name == "grid_position":
            continue  # F2-registered; superseded below, not duplicated
        dtype, unit, missing, minkind, minn, desc = _F10_META[name]
        defs.append(FeatureDef(
            name=name,
            family=_F10_FAMILY[name],
            version=1,
            dtype=dtype,
            unit=unit,
            description=desc,
            sources=_F10_SOURCES[name],
            formula_ref="v2/features/priors.py::driver_priors / "
                        "constructor_priors / circuit_priors "
                        "(history_before firewall, H < R)",
            temporal_rule=TemporalRule.PAST_RACES,
            sync=SyncRequirement.NONE,
            min_history=MinHistory(MinHistoryKind.NONE)
            if minkind == "NONE"
            else MinHistory(MinHistoryKind.COUNT, n=minn),
            missing=getattr(MissingPolicy, missing),
            availability=_C.Availability.PRE_RACE,
            predictive_eligible=True,
            status=FeatureStatus.CANDIDATE,
        ))
    return tuple(defs)


F10_DEFINITIONS = _build_f10_definitions()


def register_f10_features(registry: FeatureRegistry) -> FeatureRegistry:
    for d in F10_DEFINITIONS:
        registry.register(d)
    # Grid transitions PLANNED(v1) -> CANDIDATE(v2): join implemented here.
    from raceintel.features.contracts import (
        FeatureDef, FeatureStatus, MinHistory, MinHistoryKind,
        MissingPolicy, SyncRequirement, TemporalRule,
    )
    from raceintel import contracts as _C
    dtype, unit, missing, _, _, desc = _F10_META["grid_position"]
    registry.supersede(FeatureDef(
        name="grid_position",
        family=_F10_FAMILY["grid_position"],
        version=2,
        dtype=dtype,
        unit=unit,
        description=desc + " Join implemented in F10 (identity only).",
        sources=_F10_SOURCES["grid_position"],
        formula_ref="v2/features/priors.py::resolve_grid",
        temporal_rule=TemporalRule.PRE_RACE_CONSTANT,
        sync=SyncRequirement.NONE,
        min_history=MinHistory(MinHistoryKind.NONE),
        missing=getattr(MissingPolicy, missing),
        availability=_C.Availability.PRE_RACE,
        predictive_eligible=True,
        status=FeatureStatus.CANDIDATE,
    ))
    return registry


def build_f10_registry() -> FeatureRegistry:
    from raceintel.features.context import register_f7_features
    from raceintel.features.environment import register_f9_features
    from raceintel.features.gaps import register_gap_features
    from raceintel.features.pace import register_f5_features
    from raceintel.features.rates import register_f8_features
    from raceintel.features.registry import build_f2_registry
    return register_f10_features(register_f9_features(
        register_f8_features(register_f7_features(
            register_gap_features(register_f5_features(
                build_f2_registry()))))))


def _target_race_meta(states: pd.DataFrame, request) -> tuple:
    """(season, round_no, circuit_id, constructor_id) for the target."""
    require_columns(states, ("race_id", "driver_id", "season", "round_no",
                             "circuit_id", "constructor_id"),
                    "priors target lookup")
    from raceintel.features.temporal import resolve_target
    row = resolve_target(states, request.race_id, request.driver_id,
                         request.lap_number, request.state_time_s)
    season = row.get("season")
    rnd = row.get("round_no")
    if season is None or pd.isna(season) or rnd is None or pd.isna(rnd):
        raise TemporalError("target race lacks season/round_no metadata")
    return int(season), int(rnd), row.get("circuit_id"), \
        row.get("constructor_id")


def priors_for_state(request, registry: FeatureRegistry,
                     states: pd.DataFrame, history: PriorHistory,
                     names=None):
    """Single-state F10 computation (constant across laps by construction)."""
    from raceintel.features.registry import validate_definition
    wanted = [d for d in F10_DEFINITIONS
              if names is None or d.name in names]
    grid_wanted = names is None or "grid_position" in (names or [])
    if names is not None:
        known = {d.name for d in F10_DEFINITIONS} | {"grid_position"}
        missing = sorted(set(names) - known)
        if missing:
            raise NoCalculatorError(
                f"priors calculator has no features: {missing}")
    for d in wanted:
        validate_definition(d)
    season, rnd, circuit_id, constructor_id = _target_race_meta(
        states, request)
    out: dict = {}
    if grid_wanted:
        out["grid_position"] = resolve_grid(
            history.results_tiera, request.race_id, request.driver_id)
    if wanted:
        dp = driver_priors(history.hist_results, request.driver_id,
                           season, rnd)
        cp = constructor_priors(history.hist_results, constructor_id,
                                season, rnd)
        cp2 = circuit_priors(history.races_tiera, history.results_tiera,
                             history.pit_stops, circuit_id, season, rnd)
        for d in wanted:
            name = d.name
            if name in dp:
                out[name] = dp[name]
            elif name in cp:
                out[name] = cp[name]
            elif name in cp2:
                out[name] = cp2[name]
            else:  # pragma: no cover - defensive
                raise TemporalError(f"unresolved F10 feature: {name}")
    order = [n for n in ([d.name for d in F10_DEFINITIONS]
                             + ["grid_position"]) if n in out]
    from raceintel.features.contracts import FeatureResult
    from raceintel.features.registry import FEATURE_SET_VERSION
    return FeatureResult(
        race_id=request.race_id,
        driver_id=request.driver_id,
        lap_number=int(request.lap_number),
        state_time_s=float(request.state_time_s),
        feature_set_version=FEATURE_SET_VERSION,
        values=tuple((n, out[n]) for n in order),
        provenance=(("source", "hist_results/results"),
                    ("calculator", "priors-f10")),
    )


def priors_batch(states: pd.DataFrame, history: PriorHistory,
                 names=None) -> pd.DataFrame:
    """Batch F10 at race boundary + broadcast (chronological, past-only).

    Values computed once per (race_id, driver_id) through the same
    pure helpers as single-state, then broadcast to every lap state.
    Same-race constancy holds by construction.
    """
    require_columns(states, ("race_id", "driver_id", "lap_number",
                             "state_time_s", "season", "round_no",
                             "circuit_id", "constructor_id"),
                    "priors_batch input")
    if names is not None:
        known = {d.name for d in F10_DEFINITIONS} | {"grid_position"}
        missing = sorted(set(names) - known)
        if missing:
            raise NoCalculatorError(
                f"priors calculator has no features: {missing}")
    combos = states[["race_id", "driver_id", "season", "round_no",
                     "circuit_id", "constructor_id"]].drop_duplicates()
    # canonical season/round resolution per race (guard against
    # mixed metadata; season/round must be unique per race_id)
    per_race = combos.groupby("race_id")[["season", "round_no",
                                          "circuit_id"]].nunique()
    if bool((per_race > 1).any(axis=None)):
        raise TemporalError("race_id maps to multiple season/round/circuit")
    values: dict = {}
    for _, r in combos.iterrows():
        rid, drv = str(r["race_id"]), str(r["driver_id"])
        season, rnd = int(r["season"]), int(r["round_no"])
        out = {"grid_position": resolve_grid(history.results_tiera, rid,
                                             drv)}
        out.update(driver_priors(history.hist_results, drv, season, rnd))
        out.update(constructor_priors(history.hist_results,
                                      r["constructor_id"], season, rnd))
        out.update(circuit_priors(history.races_tiera,
                                  history.results_tiera, history.pit_stops,
                                  r["circuit_id"], season, rnd))
        values[(rid, drv)] = out
    wanted = [n for n in ([d.name for d in F10_DEFINITIONS]
                          + ["grid_position"])
              if names is None or n in names]
    rows_out = []
    for _, r in states.sort_values(
            ["race_id", "driver_id", "lap_number"],
            kind="mergesort").iterrows():
        rec = {"race_id": str(r["race_id"]), "driver_id": str(r["driver_id"]),
               "lap_number": int(r["lap_number"]),
               "state_time_s": float(r["state_time_s"])}
        src = values[(rec["race_id"], rec["driver_id"])]
        for n in wanted:
            rec[n] = src[n]
        rows_out.append(rec)
    cols = ["race_id", "driver_id", "lap_number", "state_time_s"] + wanted
    return pd.DataFrame(rows_out, columns=cols)
