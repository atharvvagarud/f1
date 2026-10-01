"""F4 D9 factual passthrough calculator (Phase 2 Temporal Feature Engine).

Registry-driven, computation-free resolution: for target S, each
PASSTHROUGH feature returns the exact approved D9 value from S. No
transformation, normalization, clipping, filling, inference, encoding,
smoothing, or recalculation. Nulls and types preserved canonically.

Only registry definitions with status PASSTHROUGH may resolve here;
any other requested status fails explicitly (NoCalculatorError).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from raceintel.features.contracts import FeatureRequest, FeatureResult
from raceintel.features.engine import NoCalculatorError
from raceintel.features.registry import (
    FEATURE_SET_VERSION,
    FeatureRegistry,
    validate_definition,
)
from raceintel.features.temporal import (
    TemporalError,
    require_columns,
    resolve_target,
)

#: The only entity passthrough sources may reference.
PASSTHROUGH_ENTITY = "driver_lap_state_d9"

#: Identity columns carried alongside every batch row.
IDENTITY_COLUMNS = ("race_id", "driver_id", "lap_number", "state_time_s")


def canonical_scalar(value):
    """Deterministic Python scalar for a D9 cell value.

    numpy integers -> int, numpy floats -> float, NaN/NA/NaT -> None,
    booleans -> bool, strings -> str (or None when null). Anything else
    fails clearly rather than silently coercing meaning.
    """
    if value is None:
        return None
    if isinstance(value, bool):
        return value
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return None if bool(np.isnan(value)) else float(value)
    if value is pd.NA or value is pd.NaT:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        raise TemporalError(
            f"unsupported passthrough cell type: {type(value).__name__}")
    if isinstance(value, str):
        return value
    raise TemporalError(
        f"unsupported passthrough cell type: {type(value).__name__}")


def _target_definitions(registry: FeatureRegistry, names=None):
    if names is None:
        # Default: the authorized PASSTHROUGH set only. Explicitly
        # requested non-passthrough features raise below.
        defs = [d for d in registry if d.status.value == "passthrough"]
    else:
        defs = [d for d in registry if d.name in set(names)]
        wanted = set(names)
        found = {d.name for d in defs}
        missing = sorted(wanted - found)
        if missing:
            raise NoCalculatorError(
                f"requested features are not registered: {missing}")
    for d in defs:
        validate_definition(d)
        if d.status.value != "passthrough":
            raise NoCalculatorError(
                f"no authorized calculator for {d.name!r} "
                f"(status={d.status.value}); F4 resolves PASSTHROUGH only")
        if len(d.sources) != 1:
            raise TemporalError(
                f"passthrough {d.name!r} must reference exactly one source")
        entity, _, column = d.sources[0].partition(".")
        if entity != PASSTHROUGH_ENTITY or not column:
            raise TemporalError(
                f"passthrough {d.name!r} has non-D9 source {d.sources[0]!r}")
        if column != d.name:
            raise TemporalError(
                f"passthrough {d.name!r} must copy its own D9 column, "
                f"not {column!r}")
    return defs


def passthrough_for_state(request: FeatureRequest,
                          registry: FeatureRegistry,
                          states: pd.DataFrame, names=None) -> FeatureResult:
    """Single-state passthrough: exact target lookup + registry copy."""
    defs = _target_definitions(registry, names)
    target = resolve_target(states, request.race_id, request.driver_id,
                            request.lap_number, request.state_time_s)
    values = tuple((d.name, canonical_scalar(target[d.name])) for d in defs)
    return FeatureResult(
        race_id=request.race_id,
        driver_id=request.driver_id,
        lap_number=int(request.lap_number),
        state_time_s=float(request.state_time_s),
        feature_set_version=FEATURE_SET_VERSION,
        values=values,
        provenance=(("source", PASSTHROUGH_ENTITY),
                    ("calculator", "passthrough")),
    )


def passthrough_batch(states: pd.DataFrame, registry: FeatureRegistry,
                      names=None) -> pd.DataFrame:
    """Vectorized passthrough batch: identity + registered columns only.

    No recomputation: column selection in deterministic registry order.
    Never mutates the input frame. Not the F15 canonical matrix — a
    test/parity vehicle returning a DataFrame.
    """
    defs = _target_definitions(registry, names)
    require_columns(states, IDENTITY_COLUMNS, "passthrough_batch input")
    columns = [d.name for d in defs]
    require_columns(states, columns, "passthrough_batch input")
    out = states.loc[:, list(IDENTITY_COLUMNS) + columns].copy()
    out = out.sort_values(list(IDENTITY_COLUMNS), kind="mergesort")
    return out.reset_index(drop=True)


def batch_row_to_result(row: pd.Series, feature_names,
                        version: str = FEATURE_SET_VERSION) -> FeatureResult:
    """Convert one batch row to a FeatureResult for parity comparison."""
    values = tuple((n, canonical_scalar(row[n])) for n in feature_names)
    return FeatureResult(
        race_id=str(row["race_id"]),
        driver_id=str(row["driver_id"]),
        lap_number=int(row["lap_number"]),
        state_time_s=float(row["state_time_s"]),
        feature_set_version=version,
        values=values,
        provenance=(("source", PASSTHROUGH_ENTITY),
                    ("calculator", "passthrough")),
    )
