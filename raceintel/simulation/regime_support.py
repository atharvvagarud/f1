"""V3.2F regime support admission table (declarative only).

Pins the V3.2F per-regime admission decisions in importable code so the
deferred status of every non-DRY_GREEN regime is explicit, typed, and
testable:

- :func:`is_supported` answers whether a regime may start a simulation
  (all non-green regimes: False in V3.2F);
- :func:`refusal_taxonomy` gives the frozen eligibility taxonomy token a
  refused regime checkpoint carries (the same tokens the unchanged
  R2/R4 pipeline already raises, so API 422 behavior is unchanged);
- :func:`regime_rng_domain` reserves deterministic RNG domain names for
  any future stochastic regime evolution (VSC/SC duration, weather
  transition). The domains are RESERVED and unconsumed in V3.2F: no
  caller draws from them, and the accepted dry-green MC2 E streams are
  untouched.

This module changes no simulation behavior: nothing in the engine,
kernel, adapter, presence path, parameters, or API imports it at
runtime. It imports nothing but stdlib.
"""

from __future__ import annotations

__all__ = [
    "REGIME_SUPPORT_VERSION",
    "REGIMES",
    "ADMISSION_DECISIONS",
    "REFUSAL_TAXONOMY",
    "RESERVED_RNG_PURPOSES",
    "is_supported",
    "refusal_taxonomy",
    "regime_rng_domain",
]

#: Regime-support contract version. Bumps only when a regime admission
#: decision changes (V3.2G+).
REGIME_SUPPORT_VERSION = "v3.2f-regime-support-v1"

#: Candidate regimes evaluated in V3.2F (DRY_GREEN is the accepted
#: baseline, not a candidate).
REGIMES = (
    "YELLOW",
    "VSC",
    "SAFETY_CAR",
    "WET",
    "RED",
)

#: Frozen V3.2F admission verdicts. Every non-green regime is DEFERRED;
#: each entry names the exact deferral identity from the regime audits.
ADMISSION_DECISIONS = {
    "YELLOW": {
        "decision": "DEFER_YELLOW",
        "reason": "YELLOW_DEFERRED_INSUFFICIENT_SPATIAL_SEMANTICS",
    },
    "VSC": {
        "decision": "DEFER_VSC",
        "reason": "VSC_DEFERRED_DURATION_RESTART_ANCHOR_EVIDENCE_THIN",
    },
    "SAFETY_CAR": {
        "decision": "DEFER_SC",
        "reason": "SC_DEFERRED_COMPRESSION_RESTART_OUT_OF_SCOPE",
    },
    "WET": {
        "decision": "DEFER_WET",
        "reason": "WET_DEFERRED_EVOLUTION_TRANSITION_NO_CAUSAL_MECHANISM",
    },
    "RED": {
        "decision": "DEFER_RED",
        "reason": "RED_DEFERRED_DEFAULT_EXPECTATION_CONFIRMED",
    },
}

#: Eligibility taxonomy token each deferred regime keeps raising through
#: the unchanged R2/R4 pipeline (hence the unchanged API 422 mapping).
REFUSAL_TAXONOMY = {
    "YELLOW": "UNSUPPORTED_TRACK_STATE",
    "VSC": "UNSUPPORTED_TRACK_STATE",
    "SAFETY_CAR": "UNSUPPORTED_TRACK_STATE",
    "WET": "WET_CONDITIONS",
    "RED": "UNSUPPORTED_TRACK_STATE",
}

#: Reserved stochastic-regime purposes (unconsumed in V3.2F).
RESERVED_RNG_PURPOSES = (
    "duration",
    "weather-transition",
)


def _require_regime(regime: str) -> str:
    if regime not in REGIMES:
        raise ValueError(
            f"unknown regime {regime!r}; expected one of {list(REGIMES)}")
    return regime


def is_supported(regime: str) -> bool:
    """Whether ``regime`` may start a simulation in V3.2F (all False)."""
    _require_regime(regime)
    return ADMISSION_DECISIONS[regime]["decision"].startswith("ADMIT_")


def refusal_taxonomy(regime: str) -> str:
    """Frozen eligibility refusal token for a deferred ``regime``."""
    _require_regime(regime)
    return REFUSAL_TAXONOMY[regime]


def regime_rng_domain(regime: str, purpose: str) -> str:
    """Reserved deterministic RNG domain name (unconsumed in V3.2F).

    Format ``mc2-<regime>-<purpose>`` (lowercase, hyphenated), disjoint
    from the residual/pace RNG domains by construction. Raises for
    unknown regimes or purposes so a future consumer cannot silently
    reuse an unrelated stream.
    """
    _require_regime(regime)
    if purpose not in RESERVED_RNG_PURPOSES:
        raise ValueError(
            f"unknown RNG purpose {purpose!r}; expected one of "
            f"{list(RESERVED_RNG_PURPOSES)}")
    return f"mc2-{regime.lower().replace('_', '-')}-{purpose}"
