"""MC2.0 active-field + condition-support contract (V3.2B, declarative only).

Frozen decision tables for the MC2.0 scientific contract. This module is
pure stdlib, imports nothing from the simulator kernel, the adapter, the
feature engine, or any model, and is imported by nothing in the runtime:
it declares the contract so tests and later stages can pin it. It changes
no simulation behavior.

Temporal rule: every classifier here is a function of information legally
available at T (plus pre-race facts such as a missing grid slot). Final
classification, future rows, and post-T outcomes are never inputs; tests
poison them to prove invariance.
"""

from __future__ import annotations

import hashlib
import json

__all__ = [
    "FIELD_CONTRACT_VERSION",
    "SUPPORT_MATRIX",
    "PRESENCE_LEVELS",
    "classify_presence",
    "support_decision",
    "contract_identity",
]

#: Declarative contract version. Any semantic change bumps this string.
FIELD_CONTRACT_VERSION = "mc2-field-v1"

#: Driver presence levels at T (V3.2B Part E).
PRESENCE_LEVELS = (
    "ACTIVE",
    "EXCLUDE_DNS_PRE_RACE",
    "EXCLUDE_SIGNALED_STALE",
    "STALE_UNRESOLVED",
    "UNOBSERVED_PRE_FIRST",
    "UNOBSERVED_DATA_GAP",
)

#: Frozen condition support matrix (V3.2B Part N).
#: Values: SUPPORTED_INITIAL | DEFERRED | INVALID.
SUPPORT_MATRIX = {
    "DRY_GREEN": ("SUPPORTED_INITIAL",
                  "dry pace parameters exist; green evolution modelled"),
    "DRY_YELLOW": ("DEFERRED",
                   "no neutralisation evolution model exists"),
    "DRY_VSC": ("DEFERRED",
                "no neutralisation evolution model exists"),
    "DRY_SC": ("DEFERRED",
               "bunching/restart dynamics unmodelled"),
    "RED": ("DEFERRED",
            "restart is a new race; no restart model in scope"),
    "WET_GREEN": ("DEFERRED",
                  "no wet pace family; dry-only empirical evidence"),
    "WET_NEUTRALISED": ("DEFERRED",
                        "wet and neutralisation gaps compound"),
    "TERMINAL": ("INVALID",
                 "no remaining race to simulate"),
    "UNKNOWN_TRACK": ("INVALID",
                      "null track state is not a green condition"),
}


def classify_presence(*, observed: bool, observation_age_s=None,
                      age_bound_s=None, dns_no_grid_slot: bool = False,
                      rc_stopped: bool = False,
                      laps_behind_leader=None) -> str:
    """Classify one roster member's presence at T from <=T evidence.

    ``dns_no_grid_slot`` is a pre-race fact (no qualifying/grid slot), never
    derived from final classification. ``rc_stopped`` is a race-control
    STOPPED message observed at or before T. Exclusion levels are candidate
    rules with measured residual risk (V3.2B audit); the simulator kernel
    does not call this function.
    """
    if not observed:
        if bool(dns_no_grid_slot):
            return "EXCLUDE_DNS_PRE_RACE"
        if observation_age_s is None:
            return "UNOBSERVED_PRE_FIRST"
        return "UNOBSERVED_DATA_GAP"
    if age_bound_s is None or observation_age_s is None:
        return "ACTIVE"
    if float(observation_age_s) <= float(age_bound_s):
        return "ACTIVE"
    behind = None if laps_behind_leader is None else int(laps_behind_leader)
    if bool(rc_stopped) and behind is not None and behind >= 2:
        return "EXCLUDE_SIGNALED_STALE"
    return "STALE_UNRESOLVED"


def support_decision(condition: str) -> str:
    """Frozen support verdict for one race-condition token."""
    if condition not in SUPPORT_MATRIX:
        raise ValueError(f"unknown MC2.0 condition {condition!r}")
    return SUPPORT_MATRIX[condition][0]


def contract_identity() -> str:
    """Canonical SHA-256 over the frozen tables (no timestamps/hosts)."""
    payload = {
        "field_contract_version": FIELD_CONTRACT_VERSION,
        "presence_levels": list(PRESENCE_LEVELS),
        "support_matrix": {key: list(value)
                           for key, value in sorted(SUPPORT_MATRIX.items())},
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
