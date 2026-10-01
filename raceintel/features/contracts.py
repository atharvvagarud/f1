"""F2 feature-definition contracts (Phase 2 Temporal Feature Engine).

STDLIB ONLY. No pandas/pyarrow/fastf1 imports: contracts must be
evaluable anywhere, exactly like ``v2/contracts.py`` and the D6/D7/D9
schemas. F1 temporal semantics (``docs/PHASE2_TEMPORAL_SEMANTICS.md``)
are authoritative; this module encodes them as validated metadata, not
as computation. F3 owns operators; families own calculators.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from raceintel import contracts as C


# ---------------------------------------------------------------------------
# Vocabulary
# ---------------------------------------------------------------------------

class FeatureFamily(str, Enum):
    """Stable family identifiers for revised Phase-2 families."""

    RACE_STATE = "race_state"
    PACE = "pace"
    TYRE = "tyre"
    STINT = "stint"
    GAP = "gap"
    RELATIVE = "relative"
    TEAMMATE = "teammate"
    FIELD = "field"
    TRAFFIC = "traffic"
    RATE = "rate"
    MOMENTUM = "momentum"
    WEATHER = "weather"
    RACE_CONTROL = "race_control"
    DRIVER_PRIOR = "driver_prior"
    CONSTRUCTOR_PRIOR = "constructor_prior"
    CIRCUIT = "circuit"
    GRID = "grid"
    INTERACTION = "interaction"


#: Families whose predictive features inherently resolve rival/field
#: state. Any predictive feature in these families MUST declare a
#: non-NONE sync requirement (validated in ``registry.py``).
CROSS_DRIVER_FAMILIES = frozenset({
    FeatureFamily.GAP,
    FeatureFamily.RELATIVE,
    FeatureFamily.TEAMMATE,
    FeatureFamily.FIELD,
    FeatureFamily.TRAFFIC,
    FeatureFamily.RATE,
})


class FeatureStatus(str, Enum):
    """Lifecycle vocabulary. Status NEVER implies model quality."""

    PASSTHROUGH = "passthrough"  # frozen Phase-1 factual reuse, no recompute
    PLANNED = "planned"          # contracted; implementation owned by later stage
    CANDIDATE = "candidate"      # defined/implemented, awaiting validation
    VALIDATED = "validated"      # definition + leakage/parity tests green
    EXPERIMENTAL = "experimental"  # provisional; needs further evidence
    DEFERRED = "deferred"        # intentionally not built in Phase 2
    DEPRECATED = "deprecated"    # superseded; kept for history only


class TemporalRule(str, Enum):
    """Smallest useful vocabulary of temporal requirements.

    There is deliberately NO same-lap variant: same-lap-number
    synchronization is forbidden by F1, so it must be inexpressible
    here (pinned by test).
    """

    TARGET_STATE = "target_state"      # value of the target row itself
    DRIVER_PREFIX = "driver_prefix"    # trailing history of target driver <= T
    SYNCHRONIZED_FIELD = "synchronized_field"  # F1 field snapshot at T
    PAST_RACES = "past_races"          # strictly prior races only
    PRE_RACE_CONSTANT = "pre_race_constant"  # genuinely pre-race factual
    BACKWARD_ASOF = "backward_asof"    # latest observation with time <= T


class SyncRequirement(str, Enum):
    """Cross-driver synchronization declaration (F1 contract)."""

    NONE = "none"  # single-driver / single-row / pre-race computation
    SYNCHRONIZED_RIVAL = "synchronized_rival"  # F1 sync_state(r, T)
    SYNCHRONIZED_FIELD = "synchronized_field"  # F1 field_snapshot(S)


class MissingPolicy(str, Enum):
    """Descriptive missingness contract. No imputation is encoded."""

    PRESERVE_SOURCE_NULL = "preserve_source_null"
    NULL_IF_INSUFFICIENT_HISTORY = "null_if_insufficient_history"
    NULL_IF_INVALID_GEOMETRY = "null_if_invalid_geometry"
    NULL_IF_NO_SYNC_STATE = "null_if_no_sync_state"
    NULL_IF_NOT_APPLICABLE = "null_if_not_applicable"
    DETERMINISTIC_FALLBACK = "deterministic_fallback"  # allowed only with
    # a mathematically justified fallback formula recorded in
    # ``fallback_description``.


class MinHistoryKind(str, Enum):
    NONE = "none"            # no history requirement
    COUNT = "count"          # explicit observation count n
    POLICY_REF = "policy_ref"  # reference to a later family contract


#: Canonical dtypes for feature values (parquet logical tokens).
FEATURE_DTYPES = ("int64", "float64", "bool", "string")

#: Unitless marker for fractions/counts/booleans/categoricals.
UNITLESS = "unitless"


# ---------------------------------------------------------------------------
# Feature definition
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class MinHistory:
    kind: MinHistoryKind = MinHistoryKind.NONE
    n: int | None = None          # required when kind == COUNT
    policy_ref: str = ""          # required when kind == POLICY_REF

    def validate(self) -> None:
        if self.kind is MinHistoryKind.COUNT:
            if self.n is None or self.n < 1:
                raise InvalidFeatureError(
                    "min_history COUNT requires n >= 1")
        elif self.kind is MinHistoryKind.POLICY_REF:
            if not self.policy_ref.strip():
                raise InvalidFeatureError(
                    "min_history POLICY_REF requires a policy reference")
        elif self.n is not None or self.policy_ref:
            raise InvalidFeatureError(
                "min_history NONE must not carry n or policy_ref")


class InvalidFeatureError(ValueError):
    """Raised when a feature definition violates F2 validation."""


@dataclass(frozen=True)
class FeatureDef:
    """Immutable machine-readable feature definition (F2 contract)."""

    name: str
    family: FeatureFamily
    version: int                     # per-feature definition version, >= 1
    dtype: str                       # one of FEATURE_DTYPES
    unit: str                        # explicit unit or UNITLESS
    description: str
    sources: tuple                   # exact "entity.field" lineage, >= 1
    formula_ref: str                 # algorithm/derivation reference
    temporal_rule: TemporalRule
    sync: SyncRequirement
    min_history: MinHistory = field(
        default_factory=lambda: MinHistory(MinHistoryKind.NONE))
    missing: MissingPolicy = MissingPolicy.PRESERVE_SOURCE_NULL
    fallback_description: str = ""   # required iff DETERMINISTIC_FALLBACK
    availability: C.Availability = C.Availability.LAP_END
    predictive_eligible: bool = True
    status: FeatureStatus = FeatureStatus.CANDIDATE

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "family": self.family.value,
            "version": self.version,
            "dtype": self.dtype,
            "unit": self.unit,
            "description": self.description,
            "sources": list(self.sources),
            "formula_ref": self.formula_ref,
            "temporal_rule": self.temporal_rule.value,
            "sync": self.sync.value,
            "min_history": {
                "kind": self.min_history.kind.value,
                "n": self.min_history.n,
                "policy_ref": self.min_history.policy_ref,
            },
            "missing": self.missing.value,
            "fallback_description": self.fallback_description,
            "availability": self.availability.value,
            "predictive_eligible": self.predictive_eligible,
            "status": self.status.value,
        }


# ---------------------------------------------------------------------------
# Request / result contracts (single-state computation)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FeatureRequest:
    """Unambiguous target-state identity. Carries NO labels/outcomes."""

    race_id: str
    driver_id: str
    lap_number: int
    state_time_s: float

    def key(self) -> tuple:
        return (self.race_id, self.driver_id, int(self.lap_number),
                float(self.state_time_s))


@dataclass(frozen=True)
class FeatureResult:
    """Deterministic single-target result.

    ``values`` maps feature name -> value (None = null/missing).
    ``provenance`` is optional debug info and is EXCLUDED from parity
    equality by default (see ``engine.results_equal``).
    """

    race_id: str
    driver_id: str
    lap_number: int
    state_time_s: float
    feature_set_version: str
    values: tuple = ()               # tuple of (name, value) pairs, sorted
    provenance: tuple = ()           # tuple of (key, info) pairs

    def value_dict(self) -> dict:
        return dict(self.values)


#: Parity float tolerances (same definitions, batch vs prefix).
PARITY_REL_TOL = 1e-9
PARITY_ABS_TOL = 1e-12
