"""V3.8C agreement/disagreement metrics over B-aligned frames.

Deterministic, source-vs-source only. No ground truth, no normalization,
no fusion, no thresholds, no quality ordering. Every metric carries its
coverage context; undefined states are explicit, never 0/NaN/inf.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum

from raceintel.consensus import contracts as C

METRICS_IMPLEMENTATION_IDENTITY = "v3.8c-consensus-metrics-v1"

PRIMARY_PAIR = (C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E)


class MetricFamily(str, Enum):
    RANK_AGREEMENT = "RANK_AGREEMENT"
    LEADER_AGREEMENT = "LEADER_AGREEMENT"
    TOP_K_AGREEMENT = "TOP_K_AGREEMENT"
    MAGNITUDE_DISAGREEMENT = "MAGNITUDE_DISAGREEMENT"
    DIRECTIONAL_TEMPORAL_RELATIONSHIP = (
        "DIRECTIONAL_TEMPORAL_RELATIONSHIP")
    MC_SAMPLING_CONTEXT = "MC_SAMPLING_CONTEXT"


class UndefinedReason(str, Enum):
    INSUFFICIENT_COMMON_DRIVERS = "INSUFFICIENT_COMMON_DRIVERS"
    ZERO_RANK_VARIANCE = "ZERO_RANK_VARIANCE"
    TARGET_INCOMPATIBLE = "TARGET_INCOMPATIBLE"
    SOURCE_UNAVAILABLE = "SOURCE_UNAVAILABLE"
    MC_TRIAL_COUNT_MISSING = "MC_TRIAL_COUNT_MISSING"
    MC_TRIAL_COUNT_INVALID = "MC_TRIAL_COUNT_INVALID"
    NO_COMPARABLE_STATES = "NO_COMPARABLE_STATES"
    METADATA_MISMATCH = "METADATA_MISMATCH"


class LineageRelation(str, Enum):
    SHARED_OR_DERIVED_LINEAGE = "SHARED_OR_DERIVED_LINEAGE"
    DISTINCT_MECHANISM = "DISTINCT_MECHANISM"


def lineage_relation(source_a: C.SourceId, source_b: C.SourceId,
                     target: C.Target) -> LineageRelation:
    """V3.5 P_win shares the V3.1B winner lineage: never two votes."""
    pair = {source_a, source_b}
    if target is C.Target.WIN and pair == {
            C.SourceId.V3_1B_LOGISTIC,
            C.SourceId.V3_5_LOGISTIC_CONTROL}:
        return LineageRelation.SHARED_OR_DERIVED_LINEAGE
    return LineageRelation.DISTINCT_MECHANISM


def canonical_pair_order(source_a: C.SourceId,
                         source_b: C.SourceId) -> tuple:
    """Registry-ordinal ordering; orientation follows explicit A->B."""
    order = list(C.SourceId)
    if order.index(source_a) <= order.index(source_b):
        return (source_a, source_b)
    return (source_b, source_a)


@dataclass(frozen=True)
class MetricResult:
    state_id: str
    race_id: str
    lap: int
    stage: str
    source_a: C.SourceId
    source_b: C.SourceId
    target: C.Target
    metric_name: str
    metric_family: MetricFamily
    value: float | None
    support_status: str
    support_reason: str | None
    n_common_drivers: int
    candidate_driver_count: int
    source_a_driver_count: int
    source_b_driver_count: int
    excluded: tuple = ()
    provenance_a: C.Provenance | None = None
    provenance_b: C.Provenance | None = None
    mc_valid_trials: int | None = None
    lineage_relation: LineageRelation | None = None


def _undefined(name: str, family: MetricFamily, frame, reason,
               n_common: int = 0) -> MetricResult:
    return MetricResult(
        state_id=frame.state_id, race_id=frame.race_id, lap=frame.lap,
        stage=frame.stage, source_a=frame.source_a,
        source_b=frame.source_b, target=frame.target_a,
        metric_name=name, metric_family=family, value=None,
        support_status="UNSUPPORTED",
        support_reason=reason.value
        if isinstance(reason, Enum) else str(reason),
        n_common_drivers=n_common, candidate_driver_count=0,
        source_a_driver_count=0, source_b_driver_count=0)


def average_ranks(values_by_driver: dict) -> dict:
    """Descending average ranks. Rank 1 = highest value. Ties averaged.

    Example {0.8, 0.5, 0.5, 0.2} -> {1, 2.5, 2.5, 4}. Input order never
    affects rank values; ties are never broken by identity or order.
    """
    drivers = sorted(values_by_driver)
    ordered = sorted(drivers,
                     key=lambda d: values_by_driver[d], reverse=True)
    ranks: dict = {}
    i = 0
    while i < len(ordered):
        j = i
        while (j + 1 < len(ordered) and values_by_driver[ordered[j + 1]]
               == values_by_driver[ordered[i]]):
            j += 1
        avg = (i + 1 + j + 1) / 2.0
        for k in range(i, j + 1):
            ranks[ordered[k]] = avg
        i = j + 1
    return ranks


def _pearson(xs: list, ys: list) -> float | None:
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    num = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    dx = sum((x - mx) ** 2 for x in xs)
    dy = sum((y - my) ** 2 for y in ys)
    if dx == 0.0 or dy == 0.0:
        return None
    return num / math.sqrt(dx * dy)


def spearman(rank_a: dict, rank_b: dict) -> float | None:
    """Spearman rank correlation on average ranks. None if degenerate."""
    common = sorted(set(rank_a) & set(rank_b))
    if len(common) < 2:
        return None
    return _pearson([rank_a[d] for d in common],
                    [rank_b[d] for d in common])


def kendall_taub(rank_a: dict, rank_b: dict) -> float | None:
    """Kendall tau-b (tie-aware). None when no comparable ordered info."""
    common = sorted(set(rank_a) & set(rank_b))
    n = len(common)
    if n < 2:
        return None
    conc = disc = 0
    tie_a = tie_b = tie_both = 0
    for i in range(n):
        for j in range(i + 1, n):
            da = rank_a[common[i]] - rank_a[common[j]]
            db = rank_b[common[i]] - rank_b[common[j]]
            if da == 0.0 and db == 0.0:
                tie_both += 1
            elif da == 0.0:
                tie_a += 1
            elif db == 0.0:
                tie_b += 1
            elif da * db > 0.0:
                conc += 1
            else:
                disc += 1
    denom = math.sqrt((conc + disc + tie_a) * (conc + disc + tie_b))
    if denom == 0.0:
        return None
    return (conc - disc) / denom


def rank_displacement(rank_a: float, rank_b: float) -> float:
    """rank_b - rank_a. Positive = numerically LOWER rank from source B.

    Descriptive only: positive is neither better nor worse.
    """
    return rank_b - rank_a


def leader_set(ranks: dict) -> frozenset:
    """All drivers sharing the best (lowest) rank. Tie-safe by design."""
    if not ranks:
        return frozenset()
    best = min(ranks.values())
    return frozenset(d for d, r in ranks.items() if r == best)


def topk_set(ranks: dict, requested_k: int) -> tuple:
    """Top-k with boundary ties included. Never cuts through a tie.

    Returns (members frozenset, effective_set_size). k=3 over ranks
    {1, 2.5, 2.5, 4} yields the first three drivers, size 3; a tie at
    the boundary rank admits every tied driver.
    """
    if requested_k < 1:
        raise ValueError(f"invalid k: {requested_k!r}")
    if not ranks:
        return (frozenset(), 0)
    distinct = sorted(set(ranks.values()))
    if requested_k >= len(distinct):
        members = frozenset(ranks)
    else:
        cutoff = distinct[requested_k - 1]
        members = frozenset(d for d, r in ranks.items() if r <= cutoff)
    return (members, len(members))


def jaccard(set_a: frozenset, set_b: frozenset) -> float | None:
    if not set_a and not set_b:
        return None
    return len(set_a & set_b) / len(set_a | set_b)


def signed_gap(p_a: float, p_b: float) -> float:
    """p_b - p_a. Positive = source B numerically higher. Not correctness."""
    return p_b - p_a


def absolute_gap(p_a: float, p_b: float) -> float:
    return abs(p_b - p_a)


def mc_sampling_se(p_mc: float, n: int) -> float:
    """Binomial MC sampling SE. Finite-sampling variability ONLY."""
    if not isinstance(n, int) or isinstance(n, bool):
        raise ValueError(f"invalid MC trial count: {n!r}")
    if n <= 0:
        raise ValueError(f"invalid MC trial count: {n!r}")
    if not math.isfinite(p_mc) or p_mc < 0.0 or p_mc > 1.0:
        raise ValueError(f"MC frequency outside [0,1]: {p_mc!r}")
    return math.sqrt(p_mc * (1.0 - p_mc) / n)


def wilson_interval(p_mc: float, n: int, z: float = 1.96) -> tuple:
    """Wilson 95% MC sampling interval (bounded, non-zero at p=0/1)."""
    if not isinstance(n, int) or isinstance(n, bool) or n <= 0:
        raise ValueError(f"invalid MC trial count: {n!r}")
    if not math.isfinite(p_mc) or p_mc < 0.0 or p_mc > 1.0:
        raise ValueError(f"MC frequency outside [0,1]: {p_mc!r}")
    denom = 1.0 + z * z / n
    center = (p_mc + z * z / (2.0 * n)) / denom
    half = (z / denom) * math.sqrt(p_mc * (1.0 - p_mc) / n
                                   + z * z / (4.0 * n * n))
    return (max(0.0, center - half), min(1.0, center + half))


def value_inside_interval(value: float, interval: tuple) -> bool:
    """Numeric containment only. NOT statistical equivalence."""
    lo, hi = interval
    return lo <= value <= hi


def mean_absolute_gap(gaps: list) -> float | None:
    if not gaps:
        return None
    return sum(abs(g) for g in gaps) / len(gaps)


def median_absolute_gap(gaps: list) -> float | None:
    if not gaps:
        return None
    ordered = sorted(abs(g) for g in gaps)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return ordered[mid]
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def max_absolute_gap(gaps: list) -> float | None:
    if not gaps:
        return None
    return max(abs(g) for g in gaps)


def rms_gap(gaps: list) -> float | None:
    if not gaps:
        return None
    return math.sqrt(sum(g * g for g in gaps) / len(gaps))


def _common_natives(frame) -> tuple:
    """Common-driver natives from a pair frame (frame holds one driver).

    State-level metrics consume per-driver frames; this helper validates
    a single frame's comparability for driver-level gap metrics.
    """
    if not frame.pair_comparable:
        return None
    if frame.p_a_native is None or frame.p_b_native is None:
        return None
    return (frame.p_a_native, frame.p_b_native)


def driver_signed_gap(frame) -> float | None:
    pair = _common_natives(frame)
    if pair is None:
        return None
    if not frame.target_compatible:
        return None
    return signed_gap(pair[0], pair[1])


def driver_absolute_gap(frame) -> float | None:
    pair = _common_natives(frame)
    if pair is None:
        return None
    if not frame.target_compatible:
        return None
    return absolute_gap(pair[0], pair[1])


def state_ranks(natives_by_source: dict) -> dict:
    """Per-source average ranks over the common driver universe.

    Input: {source: {driver: native}}. Intersection is explicit; sources
    with fewer than 2 common drivers yield no ranks (caller reports
    INSUFFICIENT_COMMON_DRIVERS).
    """
    common = sorted(set.intersection(
        *(set(v) for v in natives_by_source.values()))) \
        if natives_by_source else []
    if len(common) < 2:
        return {}
    return {src: average_ranks({d: vals[d] for d in common})
            for src, vals in natives_by_source.items()}
