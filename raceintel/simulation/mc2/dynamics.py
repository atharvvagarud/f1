"""MC2 bounded pace dynamics (V3.2D Part L-N).

Maps the two V3.2B-admitted V3.1 pace-slope dynamics to simulation drift:

    dyn_pace_slope_l3  -> short-horizon pace momentum (s/lap)
    dyn_pace_slope_l10 -> stint-scale pace momentum (s/lap)

Both are endpoint deltas recomputed causally from source history at T;
the simulator never ingests a classifier feature vector. Future drift is
a BOUNDED, DECAYING function of the slope — never indefinite linear
extrapolation:

    drift(h) = clip(slope * h, +/-BOUND) * decay**h        (exponential)
    drift(h) = clip(slope * min(h, HORIZON), +/-BOUND)     (fixed horizon)

The primary is exponential decay (lambda=0.5/lap, bound +/-1.5 s): a
0.1 s/lap trend contributes ~0.05 s on lap 1 and vanishes by lap ~6.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "ADMITTED_SLOPE_FEATURES",
    "DYNAMICS_DECAY_CANDIDATES",
    "DYNAMICS_PRIMARY_DECAY",
    "DYNAMICS_DRIFT_BOUND_S",
    "DYNAMICS_HORIZON_LAPS",
    "DynamicsInput",
    "drift_exponential",
    "drift_fixed_horizon",
    "combined_drift",
]

#: The only V3.1 dynamics admitted to the MC2 pace mechanism (V3.2B ADMIT_NOW).
ADMITTED_SLOPE_FEATURES = ("dyn_pace_slope_l3", "dyn_pace_slope_l10")

#: Predeclared decay family (per-lap exponential factors).
DYNAMICS_DECAY_CANDIDATES = (0.3, 0.5, 0.7)

#: Primary decay: simplest mid value, no outcome tuning in V3.2D.
DYNAMICS_PRIMARY_DECAY = 0.5

#: Finite bound on cumulative drift (seconds) and fixed-horizon cap (laps).
DYNAMICS_DRIFT_BOUND_S = 1.5
DYNAMICS_HORIZON_LAPS = 6


@dataclass(frozen=True)
class DynamicsInput:
    slope_l3_s_per_lap: float | None = None
    slope_l10_s_per_lap: float | None = None


def _finite_or_zero(value: float | None) -> float:
    if value is None:
        return 0.0
    try:
        v = float(value)
    except (TypeError, ValueError):
        return 0.0
    return v if math.isfinite(v) else 0.0


def _clip(value: float, bound: float) -> float:
    return max(-bound, min(bound, value))


def drift_exponential(slope_s_per_lap: float | None, laps_ahead: int, *,
                      decay: float = DYNAMICS_PRIMARY_DECAY,
                      bound_s: float = DYNAMICS_DRIFT_BOUND_S) -> float:
    """Bounded exponentially-decaying drift h laps ahead (h >= 1)."""
    if laps_ahead < 1:
        raise ValueError("laps_ahead must be >= 1")
    if decay not in DYNAMICS_DECAY_CANDIDATES:
        raise ValueError(f"decay must be one of {DYNAMICS_DECAY_CANDIDATES}")
    slope = _finite_or_zero(slope_s_per_lap)
    return float(_clip(slope * laps_ahead, bound_s) * (decay ** laps_ahead))


def drift_fixed_horizon(slope_s_per_lap: float | None, laps_ahead: int, *,
                        horizon: int = DYNAMICS_HORIZON_LAPS,
                        bound_s: float = DYNAMICS_DRIFT_BOUND_S) -> float:
    """Linear drift capped at `horizon` laps, then regressed to zero."""
    if laps_ahead < 1:
        raise ValueError("laps_ahead must be >= 1")
    slope = _finite_or_zero(slope_s_per_lap)
    if laps_ahead > horizon:
        return 0.0
    return float(_clip(slope * laps_ahead, bound_s))


def combined_drift(dynamics: DynamicsInput, laps_ahead: int, *,
                   decay: float = DYNAMICS_PRIMARY_DECAY) -> float:
    """Primary mechanism: short-horizon slope dominates, stint slope halves.

    Missing slopes contribute zero (no imputation, no fallback invention).
    Bounded by construction: |drift| <= 1.5 * BOUND via the 1.0 + 0.5 mix,
    then clipped to a single BOUND.
    """
    short = drift_exponential(dynamics.slope_l3_s_per_lap, laps_ahead,
                              decay=decay)
    long = drift_exponential(dynamics.slope_l10_s_per_lap, laps_ahead,
                             decay=decay)
    return float(_clip(short + 0.5 * long, DYNAMICS_DRIFT_BOUND_S))
