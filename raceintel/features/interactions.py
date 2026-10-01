"""F11 domain-justified interactions (Phase 2).

Exactly three retained interactions (measured, named, reviewed); every
other candidate evaluated was rejected (see docs/PHASE2_INTERACTIONS.md
for the rejection log). Each is a pure function of already-computed
primitive values: temporal safety, validity, and nulls are inherited,
never broadened. No polynomial expansion, no ratios, no projections,
no scores.

Retained (with one-sentence rationale):
- positions_from_grid: current position relative to factual starting
  slot (grid 0 pit-lane code excluded as non-ordinal).
- relative_pace_to_ahead_in_traffic_s_per_lap: ahead-relative pace
  only while factually in traffic (null outside the regime).
- recent_gap_to_ahead_change_in_traffic_s_per_lap: ahead gap-change
  rate only while factually in traffic (null outside the regime).
"""

from __future__ import annotations

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


def _num(value):
    try:
        return None if value is None or pd.isna(value) else float(value)
    except (TypeError, ValueError):
        return None


def positions_from_grid_value(grid, position):
    """grid - position; null unless grid is an earned slot (> 0)."""
    g, p = _num(grid), _num(position)
    if g is None or p is None or g <= 0:
        return None
    return int(g - p)


def conditional_on_traffic(value, in_traffic):
    """Value iff traffic is True; null for False AND Unknown (None)."""
    if in_traffic is True:
        return value
    return None


def interaction_values(prims: dict) -> dict:
    """Pure F11 core over primitive values (single + batch share it)."""
    rel = prims.get("relative_pace_to_car_ahead_s_per_lap")
    rate = prims.get("recent_gap_to_ahead_change_s_per_lap")
    traffic = prims.get("in_traffic_2s")
    return {
        "positions_from_grid": positions_from_grid_value(
            prims.get("grid_position"), prims.get("position")),
        "relative_pace_to_ahead_in_traffic_s_per_lap":
            conditional_on_traffic(rel, traffic),
        "recent_gap_to_ahead_change_in_traffic_s_per_lap":
            conditional_on_traffic(rate, traffic),
    }


INTERACTION_NAMES = (
    "positions_from_grid",
    "relative_pace_to_ahead_in_traffic_s_per_lap",
    "recent_gap_to_ahead_change_in_traffic_s_per_lap",
)

#: Primitives each interaction reads (engine resolves these first).
REQUIRED_PRIMITIVES = {
    "positions_from_grid": ("grid_position", "position"),
    "relative_pace_to_ahead_in_traffic_s_per_lap": (
        "relative_pace_to_car_ahead_s_per_lap", "in_traffic_2s"),
    "recent_gap_to_ahead_change_in_traffic_s_per_lap": (
        "recent_gap_to_ahead_change_s_per_lap", "in_traffic_2s"),
}

_I_META = {
    "positions_from_grid":
        ("int64", "positions", TemporalRule.TARGET_STATE,
         SyncRequirement.NONE,
         "Current position relative to factual starting slot "
         "(grid - position; positive = ahead of slot; grid 0 excluded)."),
    "relative_pace_to_ahead_in_traffic_s_per_lap":
        ("float64", "seconds_per_lap", TemporalRule.SYNCHRONIZED_FIELD,
         SyncRequirement.SYNCHRONIZED_FIELD,
         "Ahead-relative pace gated on factual traffic (null outside)."),
    "recent_gap_to_ahead_change_in_traffic_s_per_lap":
        ("float64", "seconds_per_lap", TemporalRule.SYNCHRONIZED_FIELD,
         SyncRequirement.SYNCHRONIZED_FIELD,
         "Ahead gap-change rate gated on factual traffic (null outside)."),
}


def _build_interaction_definitions():
    from raceintel.features.contracts import (
        FeatureDef, FeatureFamily, FeatureStatus, MinHistory,
        MinHistoryKind, MissingPolicy, SyncRequirement, TemporalRule,
    )
    from raceintel import contracts as _C
    defs = []
    for name in INTERACTION_NAMES:
        dtype, unit, temporal, sync, desc = _I_META[name]
        defs.append(FeatureDef(
            name=name,
            family=FeatureFamily.INTERACTION,
            version=1,
            dtype=dtype,
            unit=unit,
            description=desc,
            sources=tuple(f"features.{p}" for p in REQUIRED_PRIMITIVES[name]),
            formula_ref="v2/features/interactions.py::interaction_values",
            temporal_rule=temporal,
            sync=sync,
            min_history=MinHistory(MinHistoryKind.NONE),
            missing=MissingPolicy.NULL_IF_NOT_APPLICABLE,
            availability=_C.Availability.LAP_END,
            predictive_eligible=True,
            status=FeatureStatus.CANDIDATE,
        ))
    return tuple(defs)


INTERACTION_DEFINITIONS = _build_interaction_definitions()


def register_interaction_features(registry: FeatureRegistry) -> FeatureRegistry:
    for d in INTERACTION_DEFINITIONS:
        registry.register(d)
    return registry


def build_f11_registry() -> FeatureRegistry:
    from raceintel.features.priors import register_f10_features
    from raceintel.features.context import register_f7_features
    from raceintel.features.environment import register_f9_features
    from raceintel.features.gaps import register_gap_features
    from raceintel.features.pace import register_f5_features
    from raceintel.features.rates import register_f8_features
    from raceintel.features.registry import build_f2_registry
    return register_interaction_features(register_f10_features(
        register_f9_features(register_f8_features(
            register_f7_features(register_gap_features(
                register_f5_features(build_f2_registry())))))))


def _resolve_primitives(request, registry, states, history):
    """Compute required primitives through approved calculators."""
    from raceintel.features import engine as _engine
    needed: list = []
    for name in INTERACTION_NAMES:
        for p in REQUIRED_PRIMITIVES[name]:
            if p not in needed:
                needed.append(p)
    res = _engine.features_for_state(request, registry, states,
                                     names=needed, history=history)
    return res.value_dict()


def interactions_for_state(request, registry, states, history=None,
                           names=None):
    """Single-state F11: approved primitives first, then pure formulas."""
    from raceintel.features.registry import validate_definition
    wanted = [d for d in INTERACTION_DEFINITIONS
              if names is None or d.name in names]
    if names is not None:
        missing = sorted(set(names) - {d.name for d in wanted})
        if missing:
            raise NoCalculatorError(
                f"interaction calculator has no features: {missing}")
    for d in wanted:
        validate_definition(d)
    prims = _resolve_primitives(request, registry, states, history)
    vals = interaction_values(prims)
    return FeatureResult(
        race_id=request.race_id,
        driver_id=request.driver_id,
        lap_number=int(request.lap_number),
        state_time_s=float(request.state_time_s),
        feature_set_version=FEATURE_SET_VERSION,
        values=tuple((d.name, vals[d.name]) for d in wanted),
        provenance=(("source", "features.*"),
                    ("calculator", "interactions-f11")),
    )


def interactions_batch(prims: pd.DataFrame, names=None) -> pd.DataFrame:
    """Batch F11 over a primitive batch frame (identical formulas).

    ``prims`` carries identity columns plus the required primitive
    columns (e.g. a merged family-batch frame). Vectorized, same
    ``interaction_values`` semantics per row.
    """
    require_columns(prims, ("race_id", "driver_id", "lap_number",
                            "state_time_s"),
                    "interactions_batch input")
    wanted = [n for n in INTERACTION_NAMES if names is None or n in names]
    if names is not None:
        missing = sorted(set(names) - set(INTERACTION_NAMES))
        if missing:
            raise NoCalculatorError(
                f"interaction calculator has no features: {missing}")
    need = set()
    for n in wanted:
        need.update(REQUIRED_PRIMITIVES[n])
    require_columns(prims, sorted(need), "interactions_batch input")
    out = prims[["race_id", "driver_id", "lap_number",
                 "state_time_s"]].copy()
    rel = prims["relative_pace_to_car_ahead_s_per_lap"] \
        if "relative_pace_to_car_ahead_s_per_lap" in need else None
    rate = prims["recent_gap_to_ahead_change_s_per_lap"] \
        if "recent_gap_to_ahead_change_s_per_lap" in need else None
    traf = prims["in_traffic_2s"] if "in_traffic_2s" in need else None
    grid = prims["grid_position"] if "grid_position" in need else None
    pos = prims["position"] if "position" in need else None
    for n in wanted:
        if n == "positions_from_grid":
            g = pd.to_numeric(grid, errors="coerce")
            p = pd.to_numeric(pos, errors="coerce")
            ok = g.notna() & p.notna() & (g > 0)
            out[n] = pd.Series(np.where(ok, g - p, np.nan),
                               index=prims.index, dtype="float64")
        elif n == "relative_pace_to_ahead_in_traffic_s_per_lap":
            mask = traf.eq(True)
            out[n] = pd.to_numeric(rel, errors="coerce").where(mask)
        elif n == "recent_gap_to_ahead_change_in_traffic_s_per_lap":
            mask = traf.eq(True)
            out[n] = pd.to_numeric(rate, errors="coerce").where(mask)
    return out[["race_id", "driver_id", "lap_number",
                "state_time_s"] + wanted]
