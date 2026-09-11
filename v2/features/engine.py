"""F2 engine skeleton (Phase 2 Temporal Feature Engine).

Minimal orchestration interfaces only. F2 calculates NO substantive
features: family calculators do not exist yet, so computation requests
fail explicitly instead of returning dummy values. Passthrough
resolution belongs to F4; the parity comparison semantics below are
fully implemented so future batch/prefix paths are testable from day
one.
"""

from __future__ import annotations

import math

from v2.features.contracts import (
    PARITY_ABS_TOL,
    PARITY_REL_TOL,
    FeatureRequest,
    FeatureResult,
)


class NoCalculatorError(NotImplementedError):
    """No calculator is registered for the requested feature set."""


def _values_equal(a, b) -> bool:
    # Null equality: None == None; None != any value.
    if a is None or b is None:
        return a is None and b is None
    if isinstance(a, bool) or isinstance(b, bool):
        return a is b if isinstance(a, bool) and isinstance(b, bool) else a == b
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(float(a), float(b),
                            rel_tol=PARITY_REL_TOL, abs_tol=PARITY_ABS_TOL)
    return a == b


def results_equal(a: FeatureResult, b: FeatureResult,
                  check_provenance: bool = False) -> bool:
    """Parity equality for two results of the same target.

    Identity (race/driver/lap/time) and feature_set_version must match
    exactly; feature names and ordering must match; values compare with
    null-equality, float tolerance, and exact categorical equality.
    Provenance is excluded unless ``check_provenance`` is set.
    """
    if (a.race_id, a.driver_id, a.lap_number, a.state_time_s) != \
       (b.race_id, b.driver_id, b.lap_number, b.state_time_s):
        return False
    if a.feature_set_version != b.feature_set_version:
        return False
    if [n for n, _ in a.values] != [n for n, _ in b.values]:
        return False
    da, db = a.value_dict(), b.value_dict()
    for name in da:
        if not _values_equal(da[name], db[name]):
            return False
    if check_provenance and dict(a.provenance) != dict(b.provenance):
        return False
    return True


def features_for_state(request: FeatureRequest,
                       registry, states=None, names=None,
                       history=None) -> FeatureResult:
    """Single-state/prefix computation with explicit calculator dispatch.

    Each family resolves via its own calculator, merged in registry
    order. F10 priors additionally require ``history`` (a
    ``PriorHistory`` bundle); requesting priors without it raises
    NoCalculatorError. Without ``states`` — or when a requested feature
    has no authorized calculator — raises NoCalculatorError. Nothing
    is fabricated.
    """
    if states is None:
        raise NoCalculatorError(
            "engine skeleton: no state frame supplied and no family "
            "calculators registered")
    from v2.features import pace as _pace
    from v2.features import gaps as _gaps
    from v2.features import context as _ctx
    from v2.features import rates as _rates
    from v2.features import environment as _env
    from v2.features import priors as _pri
    from v2.features import interactions as _ix
    from v2.features.passthrough import passthrough_for_state
    by_name = {d.name: d for d in registry}
    if names is None:
        # Default: the active calculable set given the inputs provided.
        # PLANNED/DEFERRED definitions are non-computable by status and
        # are skipped here; F10 priors additionally require a history
        # bundle, so they join the default only when one is supplied.
        # Explicitly requesting anything non-computable raises below.
        wanted = [n for n, d in by_name.items()
                  if d.status.value == "passthrough"
                  or n in _pace.F5_FEATURE_NAMES
                  or n in _gaps.GAP_FEATURE_NAMES
                  or n in _ctx.F7_FEATURE_NAMES
                  or n in _rates.F8_FEATURE_NAMES
                  or n in _env.F9_FEATURE_NAMES
                  or (n in _pri.F10_FEATURE_NAMES
                      and history is not None)
                  or n in _ix.INTERACTION_NAMES]
    else:
        known = set(by_name)
        missing = sorted(set(names) - known)
        if missing:
            raise NoCalculatorError(
                f"requested features are not registered: {missing}")
        wanted = list(names)
    pt_names = [n for n in wanted
                if by_name[n].status.value == "passthrough"]
    f5_names = [n for n in wanted if n in _pace.F5_FEATURE_NAMES]
    gap_names = [n for n in wanted if n in _gaps.GAP_FEATURE_NAMES]
    f7_names = [n for n in wanted if n in _ctx.F7_FEATURE_NAMES]
    f8_names = [n for n in wanted if n in _rates.F8_FEATURE_NAMES]
    f9_names = [n for n in wanted if n in _env.F9_FEATURE_NAMES]
    f10_names = [n for n in wanted if n in _pri.F10_FEATURE_NAMES]
    f11_names = [n for n in wanted if n in _ix.INTERACTION_NAMES]
    unsupported = [n for n in wanted
                   if n not in pt_names and n not in f5_names
                   and n not in gap_names and n not in f7_names
                   and n not in f8_names and n not in f9_names
                   and n not in f10_names and n not in f11_names]
    if unsupported:
        raise NoCalculatorError(
            f"no authorized calculator for {unsupported}; "
            f"implemented families only")
    merged: dict = {}
    calcs: list = []
    if pt_names:
        pt = passthrough_for_state(request, registry, states, names=pt_names)
        merged.update(pt.value_dict())
        calcs.append("passthrough")
    if f5_names:
        pr = _pace.pace_for_state(request, registry, states, names=f5_names)
        merged.update(pr.value_dict())
        calcs.append("pace-f5")
    if gap_names:
        gr = _gaps.gap_for_state(request, registry, states, names=gap_names)
        merged.update(gr.value_dict())
        calcs.append("gap-f6")
    if f7_names:
        cr = _ctx.context_for_state(request, registry, states, names=f7_names)
        merged.update(cr.value_dict())
        calcs.append("context-f7")
    if f8_names:
        rr = _rates.rates_for_state(request, registry, states, names=f8_names)
        merged.update(rr.value_dict())
        calcs.append("rates-f8")
    if f9_names:
        er = _env.environment_for_state(request, registry, states,
                                        names=f9_names)
        merged.update(er.value_dict())
        calcs.append("environment-f9")
    if f10_names:
        if history is None:
            raise NoCalculatorError(
                "priors require a history bundle (PriorHistory)")
        xr = _pri.priors_for_state(request, registry, states, history,
                                   names=f10_names)
        merged.update(xr.value_dict())
        calcs.append("priors-f10")
    if f11_names:
        ir = _ix.interactions_for_state(request, registry, states, history,
                                        names=f11_names)
        merged.update(ir.value_dict())
        calcs.append("interactions-f11")
    provenance = (("source", "driver_lap_state_d9"),
                  ("calculator", "+".join(calcs)))
    ordered = tuple((d.name, merged[d.name]) for d in registry
                    if d.name in merged)
    from v2.features.registry import FEATURE_SET_VERSION
    return FeatureResult(
        race_id=request.race_id,
        driver_id=request.driver_id,
        lap_number=int(request.lap_number),
        state_time_s=float(request.state_time_s),
        feature_set_version=FEATURE_SET_VERSION,
        values=ordered,
        provenance=provenance,
    )


def features_for_batch(requests, registry, states=None,
                       names=None, history=None) -> list:
    """Batch computation returning one FeatureResult per request.

    Applies the SAME definitions/operators as the single-state path
    (parity contract). Without ``states`` raises NoCalculatorError.
    Not the F15 canonical matrix.
    """
    if states is None:
        raise NoCalculatorError(
            "engine skeleton: no state frame supplied and no family "
            "calculators registered")
    return [features_for_state(q, registry, states, names=names,
                               history=history)
            for q in requests]
