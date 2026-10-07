"""MC2 traffic construction gate + minimal mechanism (V3.2D Part V-Y).

Gate (Part V): F runs ONLY if the available state supports an
interpretable causal traffic quantity. Candidate quantities — gap ahead,
gap behind, field compression, recent near-car persistence — must be
factual at T or simulated thereafter.

Verdict for V3.2D: NOT_RUN. The factual gap geometry exists at T (RaceState
positions/times), but no temporally-safe conditioned traffic-penalty
family was estimated in V3.2D: any penalty fitted on observed gaps without
disentangling pace-deficit-from-traffic vs traffic-caused-by-pace-deficit
is confounded, and inventing a penalty to complete the ladder is
explicitly forbidden. The gate function below records exactly this, and
the mechanism is implemented but GATED (raises unless evidence is
supplied), so F cannot silently run on invented numbers.

Mechanism (Part W, gated): free-air pace + bounded penalty when close to
the car ahead, conditioned on gap/circuit/phase. Never an overtaking
physics engine.

Firewall (Part X): after T, traffic context derives ONLY from simulated
field state. The module holds no history handle; callers pass simulated
gaps. Poison-tested: mutating historical future gaps cannot change a
penalty computed from simulated inputs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

__all__ = [
    "TRAFFIC_GATE_VERDICT",
    "TRAFFIC_GATE_REASON",
    "TRAFFIC_PENALTY_BOUND_S",
    "TRAFFIC_CLOSE_GAP_S",
    "TrafficGate",
    "traffic_penalty_s",
    "evaluate_gate",
]

#: V3.2D construction-gate verdict. F = NOT_RUN (see module docstring).
TRAFFIC_GATE_VERDICT = "NOT_RUN"

TRAFFIC_GATE_REASON = (
    "no temporally-safe conditioned traffic-penalty family estimated in "
    "V3.2D; observed-gap penalties confound pace-deficit selection with "
    "traffic causation; inventing a penalty to complete the ladder is "
    "forbidden (Part F/V/Y)"
)

#: Hard bound on any traffic penalty (seconds per lap).
TRAFFIC_PENALTY_BOUND_S = 0.8

#: Gap below which the car ahead may cost pace (seconds of race time).
TRAFFIC_CLOSE_GAP_S = 2.0


@dataclass(frozen=True)
class TrafficGate:
    verdict: str
    reason: str


def evaluate_gate() -> TrafficGate:
    """The V3.2D traffic construction gate (deterministic, evidence-bound)."""
    return TrafficGate(verdict=TRAFFIC_GATE_VERDICT,
                       reason=TRAFFIC_GATE_REASON)


def traffic_penalty_s(gap_ahead_s: float | None, *, evidence: dict | None,
                      bound_s: float = TRAFFIC_PENALTY_BOUND_S) -> float:
    """Minimal pace-level traffic penalty (GATED: requires `evidence`).

    `gap_ahead_s` must come from factual-at-T or SIMULATED field state —
    never historical future gaps. `evidence` is the temporally-safe
    estimated penalty family; ``None`` (the V3.2D state) raises instead of
    inventing pace loss.
    """
    if evidence is None:
        raise ValueError(
            "traffic penalty requires an estimated evidence family; "
            "V3.2D verdict is NOT_RUN (no invented penalty)")
    if gap_ahead_s is None or not math.isfinite(gap_ahead_s):
        return 0.0
    base = float(evidence.get("penalty_s", 0.0))
    if not math.isfinite(base) or base < 0:
        return 0.0
    if gap_ahead_s >= TRAFFIC_CLOSE_GAP_S:
        return 0.0
    proximity = 1.0 - max(0.0, gap_ahead_s) / TRAFFIC_CLOSE_GAP_S
    return float(max(0.0, min(bound_s, base * proximity)))
