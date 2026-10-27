#!/usr/bin/env python3
"""V3.11D research VSC model (isolated; stdlib only).

Pure functions implementing candidates V1/V2 around frozen MC2 semantics:

    V0: refuse (control)
    V1: expected green pace * R during causally-known VSC laps
    V2: V1 + gap-preservation claim (uniform ratio => gaps carried)

Fail-closed at: non-VSC tokens, SC/red transitions, ambiguous intervals,
missing withdrawal context, pit events under VSC (no validated loss).

No production imports. No RNG. No simulation execution. Deterministic.
NOT imported by production (pinned by tests).
"""

from __future__ import annotations

VSC_TOKENS = ("vsc",)
WITHDRAWAL_TOKENS = ("vsc_ending",)
GREEN_TOKENS = ("all_clear",)
UNSUPPORTED_TOKENS = ("safety_car", "red_flag", "yellow")

MODEL_VERSION = "vsc-research-v1"


def interval_state(token, prior_token_known=True):
    """Classify a lap token for the research model.

    Returns (usable_as_vsc, reason). Pre-first (token None) => unknown.
    """
    if token is None:
        return False, "UNKNOWN_PRE_FIRST"
    if token in VSC_TOKENS:
        return True, "VSC_ACTIVE"
    if token in WITHDRAWAL_TOKENS:
        return False, "WITHDRAWAL_OBSERVED"
    if token in GREEN_TOKENS:
        return False, "GREEN"
    return False, f"UNSUPPORTED_{token}"


def vsc_expected_lap_time(green_expected_s: float, ratio: float) -> float:
    """V1: uniform ratio applied to expected green pace."""
    if not (green_expected_s > 0 and ratio > 0):
        raise ValueError("pace and ratio must be positive")
    return green_expected_s * ratio


def gap_preserved(gap_before_s: float) -> float:
    """V2 claim: uniform ratio carries pairwise gaps unchanged."""
    return gap_before_s


def fail_closed(token, pit_event_under_vsc: bool = False,
                withdrawal_known: bool = True) -> str | None:
    """Return a refusal reason, or None if the model may proceed."""
    usable, reason = interval_state(token)
    if not usable:
        return reason
    if pit_event_under_vsc:
        return "PIT_UNDER_VSC_NO_VALIDATED_LOSS"
    if not withdrawal_known:
        return "WITHDRAWAL_UNKNOWN (duration unmodelled)"
    return None
