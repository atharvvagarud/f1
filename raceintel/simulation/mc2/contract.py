"""MC2.0 research candidate contract (V3.2D, declarative only).

Research identity, candidate ladder, temporal folds, and firewall rules.
Pure stdlib. Imports nothing from the R3 kernel, the winner model, replay,
or the frontend. The kernel never imports R3 science in place; R3 stays
the immutable comparator A.
"""

from __future__ import annotations

import hashlib
import json

__all__ = [
    "MC2_RESEARCH_VERSION",
    "MC2_KERNEL_SCHEMA",
    "MC2_RNG_SCHEMA",
    "MC2_STATE_CONTRACT",
    "CANDIDATE_ARMS",
    "TEMPORAL_FOLDS",
    "ABLATON_ORDER",
    "FORBIDDEN_MC2_IMPORTS",
    "contract_identity",
]

#: Research candidate identity. Never "accepted"/"final"; V3.2E owns verdict.
MC2_RESEARCH_VERSION = "mc2-r1-research"

#: Kernel + RNG schema versions pinned into the research identity.
MC2_KERNEL_SCHEMA = "mc2-kernel-v1"
MC2_RNG_SCHEMA = "mc2-rng-v1"

#: V3.2C state contract this candidate binds to (immutable inheritance).
MC2_STATE_CONTRACT = "mc2-field-v1"
MC2_PRESENCE_ADAPTER = "v3.2c-presence-v1"

#: Pre-registered conceptual ladder. F runs only if the traffic gate passes.
CANDIDATE_ARMS = (
    "A_R3_BASELINE",
    "B_DRIVER_ANCHOR",
    "C_DRIVER_ANCHOR_PLUS_DYNAMICS",
    "D_CONDITIONED_VARIANCE",
    "E_AR1_RESIDUAL",
    "F_TRAFFIC_CONTEXT",
)

#: Temporal development folds. 2025 is never touched. Each fold evaluates
#: period Y on parameters estimated strictly before Y (R7 cutoff rule:
#: through_season = evaluation_season - 1).
TEMPORAL_FOLDS = (
    {"fold": "D1", "train_through": 2019, "evaluate": (2020, 2021)},
    {"fold": "D2", "train_through": 2021, "evaluate": (2022, 2023)},
    {"fold": "D3", "train_through": 2023, "evaluate": (2024,)},
)

#: Ablation order for V3.2D development diagnostics (NOT a V3.2E verdict).
ABLATON_ORDER = (
    "A_R3_BASELINE",
    "B_DRIVER_ANCHOR",
    "C_DRIVER_ANCHOR_PLUS_DYNAMICS",
    "D_CONDITIONED_VARIANCE",
    "E_AR1_RESIDUAL",
)

#: Substrings that must never appear as MC2 module imports (ML/MC firewall).
FORBIDDEN_MC2_IMPORTS = (
    "v2.prediction",
    "v2.model_lab",
    "model_lab",
    "replay",
    "frontend",
    "sklearn",
)


def contract_identity() -> str:
    """Canonical SHA-256 over the frozen MC2 contract (no timestamps)."""
    payload = {
        "research_version": MC2_RESEARCH_VERSION,
        "kernel_schema": MC2_KERNEL_SCHEMA,
        "rng_schema": MC2_RNG_SCHEMA,
        "state_contract": MC2_STATE_CONTRACT,
        "presence_adapter": MC2_PRESENCE_ADAPTER,
        "arms": list(CANDIDATE_ARMS),
        "folds": [
            {"fold": f["fold"], "train_through": f["train_through"],
             "evaluate": list(f["evaluate"])} for f in TEMPORAL_FOLDS
        ],
    }
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"),
                      allow_nan=False)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
