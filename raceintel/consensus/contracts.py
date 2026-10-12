"""V3.8B frozen contracts: source registry, families, targets, frames.

Pure data contracts only (no I/O, no inference, no metrics). Freezes the
V3.8A decisions in executable form: canonical (state_id, driver_id) key,
exact-identity alignment, explicit support accounting, fail-closed rules,
and the target-compatibility table. Comparison frames carry NO agreement
metrics and NO ground truth (C/D territory).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum


class SourceId(str, Enum):
    V3_1B_LOGISTIC = "V3_1B_LOGISTIC"
    MC2_E = "MC2_E"
    V3_5_LOGISTIC_CONTROL = "V3_5_LOGISTIC_CONTROL"
    V3_5_XGB_E = "V3_5_XGB_E"
    V3_3_XGBOOST = "V3_3_XGBOOST"


class SourceFamily(str, Enum):
    INDEPENDENT_BINARY = "INDEPENDENT_BINARY"
    MARGINAL_THRESHOLD = "MARGINAL_THRESHOLD"
    MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY = (
        "MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY")


class Target(str, Enum):
    WIN = "WIN"
    TOP3 = "TOP3"
    TOP5 = "TOP5"
    TOP10 = "TOP10"


class NormalizationSemantics(str, Enum):
    NOT_RACE_NORMALIZED = "NOT_RACE_NORMALIZED"
    NOT_JOINT_NOT_RACE_NORMALIZED = "NOT_JOINT_NOT_RACE_NORMALIZED"
    MUTUALLY_EXCLUSIVE_RACE_FREQUENCY = (
        "MUTUALLY_EXCLUSIVE_RACE_FREQUENCY")


class SupportStatus(str, Enum):
    AVAILABLE = "AVAILABLE"
    UNAVAILABLE = "UNAVAILABLE"
    UNSUPPORTED = "UNSUPPORTED"


class ReasonCode(str, Enum):
    STATE_NOT_AVAILABLE = "STATE_NOT_AVAILABLE"
    DRIVER_NOT_AVAILABLE = "DRIVER_NOT_AVAILABLE"
    SOURCE_NOT_AVAILABLE = "SOURCE_NOT_AVAILABLE"
    TARGET_NOT_AVAILABLE = "TARGET_NOT_AVAILABLE"
    MC2_STATE_INELIGIBLE = "MC2_STATE_INELIGIBLE"
    TERMINAL_STATE = "TERMINAL_STATE"
    PROVENANCE_MISMATCH = "PROVENANCE_MISMATCH"
    IDENTITY_MISMATCH = "IDENTITY_MISMATCH"


STAGES = ("EARLY", "MID", "LATE")

# Adapter implementation identities (mechanics only; never a substitute
# for frozen source/model identities).
ADAPTER_IDENTITIES = {
    SourceId.V3_1B_LOGISTIC: "v3.8b-logistic-adapter-v1",
    SourceId.MC2_E: "v3.8b-mc2-adapter-v1",
    SourceId.V3_5_LOGISTIC_CONTROL: "v3.8b-v3.5-adapter-v1",
    SourceId.V3_5_XGB_E: "v3.8b-v3.5-adapter-v1",
    SourceId.V3_3_XGBOOST: "v3.8b-xgb-adapter-v1",
}

SOURCE_FAMILIES = {
    SourceId.V3_1B_LOGISTIC: SourceFamily.INDEPENDENT_BINARY,
    SourceId.MC2_E: SourceFamily.MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY,
    SourceId.V3_5_LOGISTIC_CONTROL: SourceFamily.MARGINAL_THRESHOLD,
    SourceId.V3_5_XGB_E: SourceFamily.MARGINAL_THRESHOLD,
    SourceId.V3_3_XGBOOST: SourceFamily.INDEPENDENT_BINARY,
}

SOURCE_NORMALIZATION = {
    SourceId.V3_1B_LOGISTIC: NormalizationSemantics.NOT_RACE_NORMALIZED,
    SourceId.MC2_E: NormalizationSemantics.MUTUALLY_EXCLUSIVE_RACE_FREQUENCY,
    SourceId.V3_5_LOGISTIC_CONTROL:
        NormalizationSemantics.NOT_JOINT_NOT_RACE_NORMALIZED,
    SourceId.V3_5_XGB_E:
        NormalizationSemantics.NOT_JOINT_NOT_RACE_NORMALIZED,
    SourceId.V3_3_XGBOOST: NormalizationSemantics.NOT_RACE_NORMALIZED,
}

# V3.5 P_win shares the Logistic winner lineage (diagnostic alignment at
# ~3e-11, not identity). It is NOT an independent vote; C/D decides use.
V3_5_P_WIN_LINEAGE_NOTE = (
    "V3.5 P_win is lineage-linked to V3.1B winner output; "
    "agreement between them must never be counted as two "
    "independent pieces of evidence.")

# Explicit target-compatibility contract (magnitude comparison only).
TARGET_COMPATIBLE = frozenset({
    (Target.WIN, Target.WIN),
})
MC2_DERIVED_TOPK = frozenset({Target.TOP3, Target.TOP5, Target.TOP10})
V3_5_MARGINALS = frozenset({Target.WIN, Target.TOP3, Target.TOP5,
                            Target.TOP10})


def targets_compatible(source_a: SourceId, target_a: Target,
                       source_b: SourceId, target_b: Target,
                       mc2_targets: frozenset = frozenset({Target.WIN})
                       ) -> bool:
    """Same-target magnitude comparability, MC2 top-k only if exposed."""
    if target_a is not target_b:
        return False
    if target_a is Target.WIN:
        return True
    if target_a in MC2_DERIVED_TOPK and target_a in V3_5_MARGINALS:
        pair = {source_a, source_b}
        if SourceId.MC2_E in pair and target_a in mc2_targets:
            return True
    return False


# A's temporal poison blacklist (contract-level; B never reads these).
TEMPORAL_POISON_BLACKLIST = (
    "future lap time",
    "future position",
    "future gap",
    "future pit",
    "future compound",
    "future retirement",
    "future status",
    "future weather",
    "future race control",
    "future SC/VSC/red flag",
    "future finish",
    "winner label",
    "future team action",
)

# Ground-truth fields forbidden in B structures.
FORBIDDEN_GROUND_TRUTH_FIELDS = (
    "actual_winner",
    "final_position",
    "observed_outcome",
    "label",
    "y_true",
    "is_winner",
    "position_final",
)


@dataclass(frozen=True)
class Provenance:
    artifact_path: str
    artifact_identity: str
    model_identity: str
    extra: tuple = ()


@dataclass(frozen=True)
class NativePrediction:
    """One immutable source-native prediction (no metrics, no truth)."""
    state_id: str
    race_id: str
    year: int
    round: int
    lap: int
    stage: str
    driver_id: str
    source_id: SourceId
    source_family: SourceFamily
    target: Target
    native_probability: float
    normalization_semantics: NormalizationSemantics
    support_status: SupportStatus
    support_reason: str | None
    provenance: Provenance
    mc_valid_trials: int | None = None
    derived_from_mc2_counts: bool = False

    def key(self) -> tuple:
        return (self.state_id, self.driver_id)


@dataclass(frozen=True)
class ComparisonFrame:
    """Identity-safe pair frame. No metrics, no ground truth by design."""
    state_id: str
    driver_id: str
    race_id: str
    year: int
    round: int
    lap: int
    stage: str
    source_a: SourceId
    source_b: SourceId
    family_a: SourceFamily
    family_b: SourceFamily
    target_a: Target
    target_b: Target
    target_compatible: bool
    p_a_native: float | None
    p_b_native: float | None
    support_a: SupportStatus
    support_b: SupportStatus
    reason_a: str | None
    reason_b: str | None
    pair_comparable: bool
    provenance_a: Provenance | None
    provenance_b: Provenance | None
    mc_valid_trials_a: int | None = None
    mc_valid_trials_b: int | None = None


@dataclass(frozen=True)
class MultiSourceFrame:
    """Deterministic per-(state_id, driver_id) view across sources."""
    state_id: str
    driver_id: str
    race_id: str
    year: int
    round: int
    lap: int
    stage: str
    entries: tuple = ()
    excluded: tuple = ()


@dataclass(frozen=True)
class SupportAccounting:
    candidate_drivers: tuple
    available_by_source: tuple = ()
    intersection: tuple = ()
    exclusions: tuple = ()
    candidate_states: tuple = ()
    pair_supported_states: tuple = ()
    multi_supported_states: tuple = ()


def comparison_frame_fields() -> tuple:
    return tuple(ComparisonFrame.__dataclass_fields__)


def frame_has_no_metrics_or_truth() -> bool:
    names = set(comparison_frame_fields())
    banned = {"absolute_difference", "rank", "rank_difference", "leader",
              "spearman", "kendall", "overlap", "consensus", "confidence",
              "actual_winner", "final_position", "observed_outcome",
              "label", "y_true", "is_winner", "position_final"}
    return not (names & banned)
