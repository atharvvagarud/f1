"""V3.6B Strategy 2.0 execution contracts (pure, versioned, frozen).

This module turns the V3.6A scientific architecture into exact,
machine-testable contracts for the V3.6C paired-simulation engine. It
contains NO simulation execution, NO comparison execution, NO pit
dynamics, NO model calls and NO API wiring. Allowed contents only:

- re-exports of frozen Phase-7 / MC2 vocabulary (no duplicate enums),
- frozen dataclasses with canonical serialization + identity hashing,
- pure validity/eligibility helpers encoding frozen contract logic.

Reuse policy (V3.6B Part B): every structure below is classified
REUSE_VERBATIM, WRAP, or NEW_REQUIRED in
``results/v3/v3_6b/strategy_execution_contract.json``. Nothing here
changes Phase-7, MC2, or V3.5 runtime behaviour.

Dependency direction: ``raceintel.strategy`` -> ``raceintel.simulation``.
This module never imports ``api`` or ``frontend``.
"""

from __future__ import annotations

from dataclasses import dataclass

from raceintel.simulation.monte_carlo import (
    INTERVENTION_APPLIED,
    INTERVENTION_RACE_END_CANCELLED,
    INTERVENTION_SUPERSEDED,
    INTERVENTION_SUPPRESSED,
    REASON_STRATEGY_ANCHOR_MISMATCH,
    REASON_STRATEGY_DECISION_BEYOND_RACE,
    REASON_STRATEGY_DECISION_LAP_MISMATCH,
    REASON_STRATEGY_MALFORMED,
    REASON_STRATEGY_PIT_DYNAMICS_REQUIRED,
    REASON_STRATEGY_TARGET_DRIVER_NOT_IN_ROSTER,
    REASON_STRATEGY_UNSUPPORTED_ACTION,
    REASON_STRATEGY_UNSUPPORTED_COMPOUND,
    STRATEGY_ACTION_LAP_OFFSETS,
    STRATEGY_ACTIONS,
    STRATEGY_INTERVENTION_REASONS,
)
from raceintel.simulation.state import canonical_sha256
from raceintel.strategy.candidates import (
    CANDIDATE_CONTRACT_VERSION,
    CANONICAL_CANDIDATE_SPECS,
    candidate_identity,
    candidate_key,
)
from raceintel.strategy.contracts import (
    INTERVENTION_VERSION,
    STRATEGY_CONTRACT_VERSION,
    SUPPORTED_REQUESTED_COMPOUNDS,
    StrategyAction,
)
from raceintel.strategy.interventions import INTERVENTION_OUTCOME_STATUSES
from raceintel.strategy.uncertainty import (
    BOOTSTRAP_CI_METHOD,
    DEFAULT_BOOTSTRAP_REPLICATES,
    DEFAULT_BOOTSTRAP_SEED,
    DEFAULT_CONFIDENCE_LEVEL,
    MIN_VALID_PAIRS_FOR_CI,
    QUANTILE_METHOD,
    UNCERTAINTY_AVAILABLE,
    UNCERTAINTY_INSUFFICIENT_PAIRS,
    UNCERTAINTY_NO_VALID_PAIRS,
    UNCERTAINTY_SEMANTICS,
    UNCERTAINTY_VERSION,
)

__all__ = [
    "ACTION_LEVEL_REASONS",
    "BOOTSTRAP_CI_METHOD",
    "CANDIDATE_CONTRACT_VERSION",
    "CANONICAL_CANDIDATE_SPECS",
    "COMPARISON_KEY_VERSION",
    "COMPARISON_LEVEL_REASONS",
    "DEFAULT_BOOTSTRAP_REPLICATES",
    "DEFAULT_BOOTSTRAP_SEED",
    "DEFAULT_CONFIDENCE_LEVEL",
    "DIAGNOSTIC_ONLY_STATUSES",
    "DOWNSIDE_DEFINITION",
    "ELIGIBILITY_LEVELS",
    "EXECUTION_RATE_DENOMINATOR",
    "EXPECTED_POINTS_DECISION",
    "FORBIDDEN_AT_T",
    "INTERVENTION_OUTCOME_STATUSES",
    "INTERVENTION_VERSION",
    "MIN_VALID_PAIRS_FOR_CI",
    "OUTCOME_METRICS",
    "OUTCOME_SCHEMA_VERSION",
    "PAIRED_DELTA_CONVENTIONS",
    "PRODUCTION_SIMULATION_COUNT",
    "PROVENANCE_FIELDS",
    "QUANTILE_METHOD",
    "REFERENCE_KIND",
    "SEED_STREAM_RULE",
    "SIMULATOR_IDENTITY",
    "STRATEGY_ACTION_LAP_OFFSETS",
    "STRATEGY_ACTIONS",
    "STRATEGY_CONTRACT_VERSION",
    "STRATEGY_INTERVENTION_REASONS",
    "SUPPORTED_REQUESTED_COMPOUNDS",
    "TRADE_OFF_FIELDS",
    "UNCERTAINTY_AVAILABLE",
    "UNCERTAINTY_INSUFFICIENT_PAIRS",
    "UNCERTAINTY_NO_VALID_PAIRS",
    "UNCERTAINTY_SEMANTICS",
    "UNCERTAINTY_VERSION",
    "V35_CONSISTENCY_ROLE",
    "V35_EXCLUDED_FROM",
    "V3B_EXECUTION_CONTRACT_VERSION",
    "StrategyAction",
    "StrategyComparisonKey",
    "build_unsupported_result",
    "candidate_identity",
    "candidate_key",
]

#: Structural version of the V3.6B execution contract. A bump is required
#: if any frozen meaning below changes.
V3B_EXECUTION_CONTRACT_VERSION = "v3.6b-strategy-execution-contract-v1"

#: Version of the StrategyComparisonKey serialization/identity rule.
COMPARISON_KEY_VERSION = "v3.6b-comparison-key-v1"

#: Version of the Strategy 2.0 outcome-vector / delta schema.
OUTCOME_SCHEMA_VERSION = "v3.6b-outcome-vector-v1"

#: Frozen MC2 simulator identity for Strategy 2.0.
SIMULATOR_IDENTITY = "MC2-E (E_AR1_RESIDUAL)"

#: Frozen default simulation count: 5000 paired futures per action.
PRODUCTION_SIMULATION_COUNT = 5000

#: Machine identity of the decision-time baseline. It is a reference KIND,
#: not an action: it must never be conflated with STAY_OUT.
REFERENCE_KIND = "SIMULATED_NO_INTERVENTION_REFERENCE"

#: Seed-family rule (frozen R5/R6/MC2 doctrine, reused verbatim).
SEED_STREAM_RULE = (
    "per-(master_seed, simulation_index[, domain]) PCG64 streams; "
    "baseline and alternative share stream identities (CRN), never "
    "trajectories"
)

#: Expected points verdict (V3.6B Part V): DEFERRED. No points table exists
#: in the frozen summaries, field sizes vary, and season/fastest-lap scoring
#: would introduce unsupported assumptions.
EXPECTED_POINTS_DECISION = "DEFERRED"

#: Downside-risk definition (V3.6B Part W): paired-only harm probability.
#: No arbitrary N, no factual-position reference (position at T may be None).
DOWNSIDE_DEFINITION = (
    "DOWNSIDE_PROBABILITY = mean over complete valid pairs of "
    "I(finish_alt > finish_ref); paired-only diagnostic estimand in [0,1]; "
    "lower means less estimated harm relative to the reference"
)

#: Execution-rate denominator (V3.6B Part AE): frozen S4 doctrine reused
#: verbatim — status rates divide by requested simulations (pairs_total),
#: so invalid-inclusive accounting is preserved end to end.
EXECUTION_RATE_DENOMINATOR = "pairs_total (requested simulations)"

#: Per-arm outcome metrics: name -> (unit, range note). Frequencies are
#: MONTE_CARLO_FREQUENCY over valid futures; positions are 1-based ints.
OUTCOME_METRICS = {
    "win_frequency": ("frequency", "[0,1] over valid futures"),
    "podium_frequency": ("frequency", "[0,1] over valid futures"),
    "top5_frequency": ("frequency", "[0,1] over valid futures"),
    "top10_frequency": ("frequency", "[0,1] over valid futures"),
    "expected_finish": ("positions", "mean finish position over valid futures"),
    "median_finish": ("positions", "median finish position over valid futures"),
    "finish_q25": ("positions", "25th percentile over valid futures"),
    "finish_q75": ("positions", "75th percentile over valid futures"),
}

#: Paired delta conventions (V3.6B Part Y). All deltas use the frozen Phase-7
#: standardized paired-effect orientation (positive = alternative improves
#: the estimate), explicitly documented here as the contract's standardized
#: effect — this is the escape clause Part Y provides for changing none of
#: the shipped Phase-7 API/frontend semantics. Raw alt-ref units would flip
#: the sign of the shipped ``delta_expected_finish`` field and break
#: OPTION-2 compatibility, so they are NOT adopted.
PAIRED_DELTA_CONVENTIONS = {
    "delta_win_frequency": "alt - ref, frequency units, positive = improvement",
    "delta_podium_frequency": (
        "alt - ref, frequency units, positive = improvement"
    ),
    "delta_top5_frequency": (
        "alt - ref, frequency units, positive = improvement"
    ),
    "delta_top10_frequency": (
        "alt - ref, frequency units, positive = improvement"
    ),
    "delta_expected_finish": (
        "ref - alt, positions, positive = improved (lowered) expected finish"
    ),
    "delta_downside_probability": (
        "ref - alt is NOT used; downside is already harm-oriented: "
        "reported as P(alt worse than ref); negative paired shift of this "
        "quantity means less harm. See DOWNSIDE_DEFINITION."
    ),
}

#: Trade-off vector field order (V3.6B Part Z). No scalar ranking, no score.
TRADE_OFF_FIELDS = (
    "delta_win_frequency",
    "delta_podium_frequency",
    "delta_top5_frequency",
    "delta_top10_frequency",
    "delta_expected_finish",
    "delta_downside_probability",
)

#: Eligibility hierarchy levels (V3.6B Part S). Distinct by construction.
ELIGIBILITY_LEVELS = ("STATE", "ACTION", "COMPARISON")

#: Reason codes that block a whole comparison (reference cannot be built or
#: the state cannot be evolved). Subset of STRATEGY_INTERVENTION_REASONS
#: plus engine-level unsupported reasons, composed — never replaced.
COMPARISON_LEVEL_REASONS = (
    REASON_STRATEGY_TARGET_DRIVER_NOT_IN_ROSTER,
)

#: Reason codes that invalidate ONE action while siblings may stay valid.
#: Every other STRATEGY_INTERVENTION_REASONS entry lives here.
ACTION_LEVEL_REASONS = (
    REASON_STRATEGY_MALFORMED,
    REASON_STRATEGY_UNSUPPORTED_ACTION,
    REASON_STRATEGY_ANCHOR_MISMATCH,
    REASON_STRATEGY_DECISION_LAP_MISMATCH,
    REASON_STRATEGY_UNSUPPORTED_COMPOUND,
    REASON_STRATEGY_DECISION_BEYOND_RACE,
    REASON_STRATEGY_PIT_DYNAMICS_REQUIRED,
)

#: Execution statuses are DIAGNOSTIC ONLY: they describe what happened
#: inside paired futures, never eligibility. Inert/superseded/cancelled
#: outcomes must not be reported as evidence of equivalence or failure.
DIAGNOSTIC_ONLY_STATUSES = INTERVENTION_OUTCOME_STATUSES

#: Forbidden decision-time inputs (V3.6B Part AI). Anything post-T or
#: post-race is excluded by construction.
FORBIDDEN_AT_T = (
    "future_pit_events",
    "future_compounds",
    "future_lap_times",
    "future_result",
    "future_finishing_position",
    "future_status_not_known_at_T",
    "future_safety_car",
    "future_weather",
    "historical_observed_action_after_T",
    "v35_post_race_labels",
)

#: V3.5 computation surfaces it must never enter (V3.6B Part AJ).
V35_EXCLUDED_FROM = (
    "candidate_generation",
    "intervention",
    "simulation",
    "strategy_scoring",
    "action_ranking",
    "eligibility",
    "uncertainty",
)

#: The only permitted V3.5 role: offline disagreement diagnostic in V3.6D.
V35_CONSISTENCY_ROLE = "OFFLINE_DIAGNOSTIC_ONLY"

#: Minimum provenance on every future Strategy 2.0 result.
PROVENANCE_FIELDS = (
    "contract_version",
    "comparison_identity",
    "racestate_identity",
    "mc2_identity",
    "simulation_config_identity",
    "reference_identity",
    "action_identity",
    "simulation_count",
    "complete_pair_count",
    "seed_family_identity",
    "outcome_schema_identity",
    "eligibility_status",
)


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a non-empty string, got {value!r}")
    return value


def _require_nonneg_int(value: object, name: str) -> int:
    if type(value) is not int or value < 0:
        raise ValueError(
            f"{name} must be a non-negative plain int, got {value!r}"
        )
    return value


@dataclass(frozen=True)
class StrategyComparisonKey:
    """Unique scientific identity of one Strategy 2.0 comparison.

    Canonical field order is the declaration order below; ``identity()``
    hashes exactly that ordered mapping. Season/round/session are
    intentionally absent (inside ``state_identity``); future outcome data
    is forbidden by construction (no field can carry it).
    """

    key_version: str
    race_id: str
    decision_lap: int
    state_identity: str
    target_driver_id: str
    reference_kind: str
    alternative_identity: str
    simulator_identity: str
    parameter_identity: str
    simulation_count: int
    master_seed: int
    outcome_schema_version: str

    def __post_init__(self) -> None:
        if self.key_version != COMPARISON_KEY_VERSION:
            raise ValueError(
                f"unsupported key_version {self.key_version!r}"
            )
        object.__setattr__(
            self, "race_id", _require_text(self.race_id, "race_id")
        )
        object.__setattr__(
            self,
            "decision_lap",
            _require_nonneg_int(self.decision_lap, "decision_lap"),
        )
        object.__setattr__(
            self,
            "state_identity",
            _require_text(self.state_identity, "state_identity"),
        )
        object.__setattr__(
            self,
            "target_driver_id",
            _require_text(self.target_driver_id, "target_driver_id"),
        )
        if self.reference_kind != REFERENCE_KIND:
            raise ValueError(
                "reference_kind must be "
                f"{REFERENCE_KIND!r}, got {self.reference_kind!r}"
            )
        object.__setattr__(
            self,
            "alternative_identity",
            _require_text(
                self.alternative_identity, "alternative_identity"
            ),
        )
        object.__setattr__(
            self,
            "simulator_identity",
            _require_text(self.simulator_identity, "simulator_identity"),
        )
        object.__setattr__(
            self,
            "parameter_identity",
            _require_text(
                self.parameter_identity, "parameter_identity"
            ),
        )
        object.__setattr__(
            self,
            "simulation_count",
            _require_nonneg_int(
                self.simulation_count, "simulation_count"
            ),
        )
        if self.simulation_count < 1:
            raise ValueError("simulation_count must be >= 1")
        object.__setattr__(
            self,
            "master_seed",
            _require_nonneg_int(self.master_seed, "master_seed"),
        )
        if self.outcome_schema_version != OUTCOME_SCHEMA_VERSION:
            raise ValueError(
                f"unsupported outcome_schema_version "
                f"{self.outcome_schema_version!r}"
            )

    def to_dict(self) -> dict:
        return {
            "key_version": self.key_version,
            "race_id": self.race_id,
            "decision_lap": self.decision_lap,
            "state_identity": self.state_identity,
            "target_driver_id": self.target_driver_id,
            "reference_kind": self.reference_kind,
            "alternative_identity": self.alternative_identity,
            "simulator_identity": self.simulator_identity,
            "parameter_identity": self.parameter_identity,
            "simulation_count": self.simulation_count,
            "master_seed": self.master_seed,
            "outcome_schema_version": self.outcome_schema_version,
        }

    def identity(self) -> str:
        return canonical_sha256(self.to_dict())


def build_unsupported_result(
    *,
    level: str,
    reason_code: str,
    human_reason: str,
    state_identity: str,
    action_identity: str | None = None,
) -> dict:
    """Machine-readable unsupported result (V3.6B Part T).

    Carries NO metrics, NO zero-filled deltas, NO NaN: the ``metrics``
    mapping is always empty. ``level`` is one of ELIGIBILITY_LEVELS.
    """
    if level not in ELIGIBILITY_LEVELS:
        raise ValueError(f"unknown eligibility level {level!r}")
    if not reason_code or not str(reason_code).strip():
        raise ValueError("reason_code must be a non-empty string")
    return {
        "supported": False,
        "level": level,
        "reason_code": reason_code,
        "human_reason": human_reason,
        "state_identity": state_identity,
        "action_identity": action_identity,
        "metrics": {},
        "provenance": {
            "contract_version": V3B_EXECUTION_CONTRACT_VERSION,
            "outcome_schema_version": OUTCOME_SCHEMA_VERSION,
        },
    }


#: Re-exported execution-status markers used by diagnostics (frozen S2).
EXECUTED_STATUSES = (INTERVENTION_APPLIED, INTERVENTION_SUPPRESSED)
NON_EXECUTED_STATUSES = (
    INTERVENTION_SUPERSEDED,
    INTERVENTION_RACE_END_CANCELLED,
)
