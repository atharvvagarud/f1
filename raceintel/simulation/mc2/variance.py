"""MC2 context-conditioned residual variance (V3.2D Part O-P).

R3 residual std is ~1.5 s globally/coarsely. MC2 selects a regime std from
an explicit hierarchy with minimum-N, floor, ceiling, and fallback reason
at every level:

    circuit|era  --(n >= 2000)-->  era  --(n >= 30)-->  global

Conditioning beyond this (race phase, stint context, traffic regime) is
DECLARED but NOT estimated in V3.2D: sample support is inadequate and any
claimed split would be tiny-sample variance collapse. The selector takes
caller-supplied regime statistics (estimated temporally-safe elsewhere),
never touches parquet itself.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "VARIANCE_HIERARCHY",
    "VARIANCE_MIN_N",
    "VARIANCE_FLOOR_S",
    "VARIANCE_CEILING_S",
    "R3_GLOBAL_STD_S",
    "RegimeStat",
    "select_variance",
    "VarianceSelection",
]

#: Hierarchy levels in preference order.
VARIANCE_HIERARCHY = ("circuit|era", "era", "global")

#: Minimum sample support per level.
VARIANCE_MIN_N = {"circuit|era": 2000, "era": 30, "global": 1}

#: Floor/ceiling prevent tiny-sample collapse/explosion (seconds).
VARIANCE_FLOOR_S = 0.3
VARIANCE_CEILING_S = 4.0

#: Documented R3 coarse scale (reference only, never a silent fallback
#: without naming the fallback level: the selector always reports it).
R3_GLOBAL_STD_S = 1.5


@dataclass(frozen=True)
class RegimeStat:
    std_s: float
    n: int


@dataclass(frozen=True)
class VarianceSelection:
    std_s: float
    level: str  # one of VARIANCE_HIERARCHY
    fallback_reason: str  # 'preferred' | 'insufficient_n' | 'non_finite'


def _usable(stat: RegimeStat | None, level: str) -> bool:
    if stat is None:
        return False
    if not isinstance(stat.n, int) or stat.n < VARIANCE_MIN_N[level]:
        return False
    return math.isfinite(stat.std_s) and stat.std_s > 0


def select_variance(regimes: dict) -> VarianceSelection:
    """Pick the deepest supported regime std, clipped to [floor, ceiling]."""
    for level in VARIANCE_HIERARCHY:
        stat = regimes.get(level)
        if _usable(stat, level):
            std = max(VARIANCE_FLOOR_S, min(VARIANCE_CEILING_S, stat.std_s))
            return VarianceSelection(std_s=float(std), level=level,
                                     fallback_reason="preferred")
    # Global must always exist (R3 ships era+global); if even that is
    # missing/non-finite, fall back loudly to the documented R3 scale.
    gstat = regimes.get("global")
    if gstat is not None and math.isfinite(gstat.std_s) and gstat.std_s > 0:
        std = max(VARIANCE_FLOOR_S, min(VARIANCE_CEILING_S, gstat.std_s))
        return VarianceSelection(std_s=float(std), level="global",
                                 fallback_reason="insufficient_n")
    return VarianceSelection(std_s=R3_GLOBAL_STD_S, level="global",
                             fallback_reason="non_finite")
