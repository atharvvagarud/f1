"""MC2 causal driver pace anchor (V3.2D Part H-K).

Concept: driver current pace relative to the expected contextual baseline,
estimated ONLY from observations <= T.

    anchor_i = shrink(n) * median(clean deviations vs R3 expectation)

A "clean" lap excludes pit laps, SC/VSC/yellow/red laps, lap 1, and laps
with missing compound/age (R3-B eligibility spirit, causal past-only).
Shrinkage ``n / (n + K)`` pulls thin histories toward the prior (0 = drive
at the contextual expectation). No future lap, pit event, classification,
or tyre fact can change Anchor(T): inputs are explicit caller-supplied
past-only records (poison-tested).

Window candidates {3, 5, 8} predeclared; 5 is the primary (median-family
convention of representative_recent_pace_s, halved for recency). Selection
is structural (fallback-rate reasoning), never outcome-tuned in V3.2D.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "ANCHOR_WINDOW_CANDIDATES",
    "ANCHOR_PRIMARY_WINDOW",
    "ANCHOR_SHRINKAGE_K",
    "ANCHOR_CLIP_S",
    "PastLap",
    "is_clean_lap",
    "compute_anchor",
    "AnchorResult",
]

#: Predeclared window candidate set (counts of clean laps).
ANCHOR_WINDOW_CANDIDATES = (3, 5, 8)

#: Primary window (structural choice, see module docstring).
ANCHOR_PRIMARY_WINDOW = 5

#: Shrinkage strength: weight = n / (n + K). K=4 means a single usable lap
#: carries weight 0.2 against the prior.
ANCHOR_SHRINKAGE_K = 4

#: Hard bound on any anchor offset (seconds). Anchors beyond this are
#: measurement artefacts, never genuine pace.
ANCHOR_CLIP_S = 3.0


@dataclass(frozen=True)
class PastLap:
    """One causal past-only lap observation (all fields known at T)."""

    lap_time_s: float
    expected_s: float  # R3 contextual expectation for that lap (mu at row)
    pit_lap: bool = False
    neutralised: bool = False  # SC/VSC/yellow/red
    lap_number: int = 2
    compound_known: bool = True
    tyre_age_known: bool = True


def is_clean_lap(lap: PastLap) -> bool:
    """R3-B-spirit eligibility for anchor evidence (past-only fields)."""
    if lap.pit_lap or lap.neutralised:
        return False
    if lap.lap_number <= 1:
        return False
    if not (lap.compound_known and lap.tyre_age_known):
        return False
    if not (math.isfinite(lap.lap_time_s) and math.isfinite(lap.expected_s)):
        return False
    return True


@dataclass(frozen=True)
class AnchorResult:
    offset_s: float  # shrunk, clipped driver offset vs expectation
    n_clean: int  # clean laps available (before window cap)
    n_used: int  # clean laps actually used (after window cap)
    weight: float  # shrinkage weight n_used / (n_used + K)
    fallback: str  # 'evidence' | 'thin' | 'none'


def _median(values: list) -> float:
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2:
        return float(ordered[mid])
    return float((ordered[mid - 1] + ordered[mid]) / 2.0)


def compute_anchor(past_laps: list,
                   *, window: int = ANCHOR_PRIMARY_WINDOW,
                   shrinkage_k: int = ANCHOR_SHRINKAGE_K) -> AnchorResult:
    """Shrunk driver pace offset from past-only laps (latest `window`)."""
    if window not in ANCHOR_WINDOW_CANDIDATES:
        raise ValueError(f"window must be one of {ANCHOR_WINDOW_CANDIDATES}")
    clean = [lap for lap in past_laps if is_clean_lap(lap)]
    n_clean = len(clean)
    used = clean[-window:] if window else []
    n_used = len(used)
    if n_used == 0:
        return AnchorResult(offset_s=0.0, n_clean=n_clean, n_used=0,
                            weight=0.0, fallback="none")
    deviations = [lap.lap_time_s - lap.expected_s for lap in used]
    raw = _median(deviations)
    # ponytail: median of <=8 values; O(n log n) sort is the whole algorithm.
    weight = n_used / (n_used + shrinkage_k)
    offset = max(-ANCHOR_CLIP_S, min(ANCHOR_CLIP_S, weight * raw))
    if not math.isfinite(offset):
        offset = 0.0
    return AnchorResult(
        offset_s=float(offset), n_clean=n_clean, n_used=n_used,
        weight=float(weight),
        fallback="evidence" if n_used >= 3 else "thin",
    )
