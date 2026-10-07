"""MC2.0 research candidate namespace (V3.2D).

Frozen R3 science is never imported for modification — the kernel reads the
R3 deterministic expectation and adds causal mechanisms (anchor, bounded
dynamics, conditioned variance, AR(1)) under the V3.2C presence contract.
"""

from raceintel.simulation.mc2.contract import (
    CANDIDATE_ARMS,
    MC2_RESEARCH_VERSION,
    TEMPORAL_FOLDS,
    contract_identity,
)
from raceintel.simulation.mc2.kernel import kernel_identity

__all__ = [
    "MC2_RESEARCH_VERSION",
    "CANDIDATE_ARMS",
    "TEMPORAL_FOLDS",
    "contract_identity",
    "kernel_identity",
]
