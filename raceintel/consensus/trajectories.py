"""V3.8C temporal trajectories over exact aligned states.

Descriptive sequences only: ordered exact-state observations from the
same race/source-pair/target, no interpolation, no forward-fill, no
nearest-lap matching. Non-consecutive observations stay visibly
non-consecutive (lap deltas + missing counts). Stage/race-macro helpers
are pure aggregation utilities; D owns historical interpretation.
"""

from __future__ import annotations

from dataclasses import dataclass

from raceintel.consensus import contracts as C
from raceintel.consensus import metrics as M

TRAJECTORIES_IMPLEMENTATION_IDENTITY = "v3.8c-consensus-trajectories-v1"


@dataclass(frozen=True)
class GapObservation:
    state_id: str
    race_id: str
    lap: int
    stage: str
    driver_id: str
    source_a: C.SourceId
    source_b: C.SourceId
    target: C.Target
    signed_gap: float | None
    absolute_gap: float | None
    rank_displacement: float | None
    comparable: bool
    reason: str | None = None


@dataclass(frozen=True)
class DirectionalChange:
    state_id_from: str
    state_id_to: str
    lap_from: int
    lap_to: int
    lap_delta: int
    missing_intermediate_states: int | None
    driver_id: str
    delta_absolute_gap: float | None
    delta_signed_gap: float | None
    direction_label: str


@dataclass(frozen=True)
class StageAggregate:
    stage: str
    n_values: int
    n_races: int
    mean_value: float | None
    median_value: float | None
    support_count: int


@dataclass(frozen=True)
class RaceMacroAggregate:
    race_id: str
    n_states: int
    mean_value: float | None
    support_count: int


def gap_series(frames_by_state: tuple, driver_id: str,
               source_a: C.SourceId, source_b: C.SourceId
               ) -> tuple:
    """Per-driver descriptive gap sequence over exact states.

    ``frames_by_state``: ordered (state_id, lap, stage, p_a, p_b,
    rank_a, rank_b, comparable, reason) records using exact aligned
    states only. Drivers absent at a state yield a non-comparable
    observation with its reason; coverage gaps are explicit.
    """
    out = []
    for rec in frames_by_state:
        (state_id, lap, stage, p_a, p_b, rank_a, rank_b, comparable,
         reason) = rec
        if comparable and p_a is not None and p_b is not None:
            sgap = M.signed_gap(p_a, p_b)
            agap = M.absolute_gap(p_a, p_b)
            disp = (M.rank_displacement(rank_a, rank_b)
                    if rank_a is not None and rank_b is not None
                    else None)
        else:
            sgap = agap = disp = None
        out.append(GapObservation(
            state_id=state_id, race_id="", lap=lap, stage=stage,
            driver_id=driver_id, source_a=source_a, source_b=source_b,
            target=C.Target.WIN, signed_gap=sgap, absolute_gap=agap,
            rank_displacement=disp, comparable=bool(comparable),
            reason=reason))
    return tuple(out)


def directional_changes(observations: tuple,
                        missing_counts: dict | None = None
                        ) -> tuple:
    """Consecutive-comparable deltas with lap deltas and missing counts.

    Numeric deltas are primary; CONVERGING/DIVERGING/UNCHANGED are purely
    descriptive (absolute gap decreased/increased/exactly equal).
    """
    missing_counts = missing_counts or {}
    out = []
    for prev, cur in zip(observations, observations[1:]):
        if (not prev.comparable or not cur.comparable
                or prev.absolute_gap is None
                or cur.absolute_gap is None):
            continue
        d_abs = cur.absolute_gap - prev.absolute_gap
        d_sgn = cur.signed_gap - prev.signed_gap
        if d_abs < 0.0:
            label = "CONVERGING"
        elif d_abs > 0.0:
            label = "DIVERGING"
        else:
            label = "UNCHANGED"
        key = (prev.state_id, cur.state_id)
        out.append(DirectionalChange(
            state_id_from=prev.state_id, state_id_to=cur.state_id,
            lap_from=prev.lap, lap_to=cur.lap,
            lap_delta=cur.lap - prev.lap,
            missing_intermediate_states=missing_counts.get(key),
            driver_id=cur.driver_id, delta_absolute_gap=d_abs,
            delta_signed_gap=d_sgn, direction_label=label))
    return tuple(out)


def _mean(values: list) -> float | None:
    if not values:
        return None
    return sum(values) / len(values)


def _median(values: list) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def aggregate_by_stage(values_with_context: tuple) -> tuple:
    """Pure stage aggregation over supplied (stage, race_id, value).

    Returns one StageAggregate per stage present, in EARLY/MID/LATE
    order. No historical interpretation.
    """
    by_stage: dict = {}
    for stage, race_id, value in values_with_context:
        if stage not in C.STAGES:
            raise ValueError(f"unknown stage: {stage!r}")
        by_stage.setdefault(stage, []).append((race_id, value))
    out = []
    for stage in C.STAGES:
        rows = by_stage.get(stage, [])
        vals = [v for _, v in rows if v is not None]
        races = {r for r, v in rows if v is not None}
        out.append(StageAggregate(
            stage=stage, n_values=len(vals), n_races=len(races),
            mean_value=_mean(vals), median_value=_median(vals),
            support_count=len(rows)))
    return tuple(out)


def aggregate_race_macro(values_with_context: tuple) -> tuple:
    """Race-macro aggregation: equal per-race weight downstream.

    Input (race_id, value) rows; one aggregate per race, race-sorted.
    State-pooled weighting is never forced: per-race means are the
    primary unit, pooled views are the caller's explicit choice.
    """
    by_race: dict = {}
    for race_id, value in values_with_context:
        by_race.setdefault(race_id, []).append(value)
    out = []
    for race_id in sorted(by_race):
        vals = [v for v in by_race[race_id] if v is not None]
        out.append(RaceMacroAggregate(
            race_id=race_id, n_states=len(vals),
            mean_value=_mean(vals),
            support_count=len(by_race[race_id])))
    return tuple(out)
