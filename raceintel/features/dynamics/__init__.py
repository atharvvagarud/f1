"""V3.1 dynamics feature package (V3.1B construction).

Consumes the frozen V3.1A contract (``contract.py``); calculators assemble
causal lap-window trajectories over per-row frozen values plus D9 source
fields. No model training, no labels, no API/replay/spatial/simulation
imports anywhere in this package.
"""

from raceintel.features.dynamics.contract import (
    ALL_DEFINITIONS,
    BOOTSTRAP_CI_LEVEL,
    BOOTSTRAP_REPLICATES,
    BOOTSTRAP_SEED,
    CONTRACT_VERSION,
    CORE_DEFINITIONS,
    FEATURE_SETS,
    HORIZONS,
    PRIMARY_UNIT,
    VARIANT_DEFINITIONS,
    WINDOW_CONTRACT,
    canonical_payload,
    canonical_text,
    contract_hash,
    feature_set_names,
    get_definition,
)

__all__ = [
    "ALL_DEFINITIONS",
    "BOOTSTRAP_CI_LEVEL",
    "BOOTSTRAP_REPLICATES",
    "BOOTSTRAP_SEED",
    "CONTRACT_VERSION",
    "CORE_DEFINITIONS",
    "FEATURE_SETS",
    "HORIZONS",
    "PRIMARY_UNIT",
    "VARIANT_DEFINITIONS",
    "WINDOW_CONTRACT",
    "canonical_payload",
    "canonical_text",
    "contract_hash",
    "feature_set_names",
    "get_definition",
]
