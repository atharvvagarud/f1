"""V3.7B counterfactual execution contracts (pure, additive, no execution).

Declarative schedule representation for admitted counterfactual plans
(PIT_IN_N_LAPS, multi-stop compositions, multi-target plans), canonical
identities, lifecycle/transitions, conflicts, eligibility, comparison
keys, outcome-schema extensions, CRN/complete-pair discipline, and
temporal-safety guards.

Import discipline: stdlib plus the frozen shared leaf
``raceintel.simulation.state`` (``Provenance``, ``canonical_sha256``)
only. Frozen V3.6 literals (reference kind, counts, seeds, compounds,
forbidden fields) are RE-DECLARED here and pinned equal by tests, so
this module never imports the V3.6 runtime engine, the API, the
frontend, or V3.5. No simulation execution, no cache, no frontend.
"""

from __future__ import annotations

from dataclasses import dataclass

from raceintel.simulation.state import Provenance, canonical_sha256

__all__ = [
    "PLAN_VERSION",
    "SCHEDULED_INTERVENTION_VERSION",
    "COMPARISON_KEY_VERSION",
    "OUTCOME_SCHEMA_VERSION",
    "REFERENCE_KIND",
    "PRODUCTION_SIMULATION_COUNT",
    "DEFAULT_MASTER_SEED",
    "INTERVENTION_KINDS",
    "REJECTED_INTERVENTION_KINDS",
    "SUPPORTED_REQUESTED_COMPOUNDS",
    "ELIGIBILITY_LEVELS",
    "V37_REASON_CODES",
    "LIFECYCLE_STATES",
    "LIFECYCLE_V36_MAPPING",
    "TRANSITIONS",
    "CONFLICT_VERDICTS",
    "COMPARISON_FORMS",
    "V37_OUTCOME_METRICS",
    "FORBIDDEN_PLAN_FIELDS",
    "FORBIDDEN_AT_T",
    "PROVENANCE_FIELDS",
    "CRN_RULE",
    "SEED_STREAM_RULE",
    "CounterfactualPlanError",
    "ScheduledIntervention",
    "CounterfactualPlan",
    "PlanComparisonKey",
    "mechanical_equivalent_action",
    "transition_allowed",
    "classify_conflict",
    "build_unsupported_result",
    "canonical_plan_dict",
    "plan_identity",
    "DELTA_ORIENTATION",
    "POSITION_GAIN_DEFINITION",
    "position_gain",
]

#: Contract versions (few, coarse; bump only on contract change).
PLAN_VERSION = "v3.7b-plan-v1"
SCHEDULED_INTERVENTION_VERSION = "v3.7b-scheduled-intervention-v1"
COMPARISON_KEY_VERSION = "v3.7b-comparison-key-v1"
OUTCOME_SCHEMA_VERSION = "v3.7b-outcome-schema-v1"

#: Canonical reference (re-declared; pinned equal to V3.6 by test).
REFERENCE_KIND = "SIMULATED_NO_INTERVENTION_REFERENCE"

#: Production futures and root seed (re-declared; pinned equal by test).
PRODUCTION_SIMULATION_COUNT = 5000
DEFAULT_MASTER_SEED = 20240101

#: The only admitted executable intervention kind (V3.7A SUPPORTED_NOW).
INTERVENTION_KINDS = ("PIT_IN_N_LAPS",)

#: Kinds that must fail closed: rejected classes plus narrative labels.
#: They may appear in A landscape docs; they must never become plan kinds.
REJECTED_INTERVENTION_KINDS = (
    "WEATHER",
    "SAFETY_CAR",
    "VSC",
    "RED_FLAG",
    "RETIREMENT",
    "RELIABILITY",
    "ARBITRARY_POSITION",
    "ARBITRARY_GAP",
    "ARBITRARY_PACE",
    "ARBITRARY_TYRE_AGE",
    "UNDERCUT",
    "OVERCUT",
)

#: Frozen compound enum (re-declared; pinned equal by test). No
#: INTERMEDIATE/WET: weather counterfactuals are rejected.
SUPPORTED_REQUESTED_COMPOUNDS = ("SOFT", "MEDIUM", "HARD", "SAMPLED")

#: Eligibility hierarchy: V3.6 (STATE/ACTION/COMPARISON) extended with PLAN.
#: INTERVENTION succeeds V3.6 ACTION for scheduled (non-enum) interventions.
ELIGIBILITY_LEVELS = ("STATE", "INTERVENTION", "PLAN", "COMPARISON")

#: New V3.7 reason codes (frozen V3.6 codes reused by reference, not
#: redefined). Naming follows the frozen lower_snake convention.
V37_REASON_CODES = (
    "INVALID_TRIGGER",
    "CONFLICTING_INTERVENTIONS",
    "TARGET_NOT_PRESENT",
    "RIVAL_NOT_PRESENT",
    "UNSUPPORTED_INTERVENTION_KIND",
    "INVALID_PLAN",
)

#: Intervention lifecycle. V3.6 vocabulary reused where it exists.
LIFECYCLE_STATES = (
    "PLANNED",
    "ELIGIBLE",
    "EXECUTED",
    "INERT",
    "SUPERSEDED",
    "CANCELLED",
    "TERMINAL",
    "INVALID",
)

#: Authoritative mapping to frozen V3.6/runtime execution states.
#: None means contract-level only (no V3.6 counterpart).
LIFECYCLE_V36_MAPPING = {
    "PLANNED": None,
    "ELIGIBLE": None,
    "EXECUTED": "INTERVENTION_APPLIED",
    "INERT": None,
    "SUPERSEDED": "INTERVENTION_SUPERSEDED",
    "CANCELLED": "INTERVENTION_RACE_END_CANCELLED",
    "TERMINAL": None,
    "INVALID": None,
}

#: Legal lifecycle transitions (machine-readable). Absent edge = fail closed.
TRANSITIONS = {
    "PLANNED": ("ELIGIBLE", "CANCELLED", "TERMINAL", "INVALID"),
    "ELIGIBLE": ("EXECUTED", "INERT", "SUPERSEDED", "CANCELLED", "TERMINAL"),
    "EXECUTED": (),
    "INERT": (),
    "SUPERSEDED": (),
    "CANCELLED": (),
    "TERMINAL": (),
    "INVALID": (),
}

#: Conflict-matrix verdicts.
CONFLICT_VERDICTS = ("VALID", "DEDUPLICATE", "INVALID", "RUNTIME_SUPERSESSION")

#: Comparison forms. Plan-vs-plan never redefines the canonical reference.
COMPARISON_FORMS = ("REFERENCE_VS_PLAN", "PLAN_VS_PLAN")

#: Outcome metrics: V3.6 eight plus V3.7A admissions.
V37_OUTCOME_METRICS = (
    "win_frequency",
    "podium_frequency",
    "top5_frequency",
    "top10_frequency",
    "expected_finish",
    "median_finish",
    "finish_q25",
    "finish_q75",
    "p_ahead_of_rival",
    "pit_count",
    "position_gain_loss",
)

#: Plan payload fields that would smuggle post-T historical information.
FORBIDDEN_PLAN_FIELDS = (
    "observed_future_pit_lap",
    "future_weather",
    "future_safety_car",
    "future_finish",
    "historical_outcome",
    "recommendation_score",
    "future_result",
    "winner",
    "future",
    "result",
)

#: Frozen V3.6 post-T blacklist (re-declared; pinned equal by test).
FORBIDDEN_AT_T = (
    "future_pit_events",
    "future_compounds",
    "future_lap_times",
    "future_result",
    "future_finishing_position",
    "future_safety_car",
    "future_weather",
    "historical_observed_action_after_T",
    "v35_post_race_labels",
)

#: Deterministic result provenance fields.
PROVENANCE_FIELDS = (
    "v37a_contract_identity",
    "v37b_contract_identity",
    "plan_schema_version",
    "comparison_schema_version",
    "mc2_identity",
    "state_identity",
    "simulation_count",
    "master_seed",
    "outcome_schema_version",
    "reference_kind",
    "comparison_form",
    "seed_stream_rule",
)

#: CRN discipline generalized to schedules (same streams, plans differ).
CRN_RULE = (
    "same factual state, same simulation config, same root seed family, "
    "same simulation index, same stochastic stream family; only the "
    "intervention schedule differs"
)

#: Seed-stream rule (re-declared; pinned equal by test).
SEED_STREAM_RULE = "PCG64 SeedSequence[master_seed, simulation_index, domain_tag]"


class CounterfactualPlanError(ValueError):
    """A plan/schedule/comparison contract violation (fail closed)."""


def _require_text(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise CounterfactualPlanError(
            f"{name} must be a non-empty string, got {value!r}")
    return value


def _require_identity(value: object, name: str) -> str:
    text = _require_text(value, name)
    if len(text) != 64:
        raise CounterfactualPlanError(
            f"{name} must be a 64-hex identity, got {value!r}")
    return text


def _require_offset_n(value: object) -> int:
    # Exact-type check, mirroring frozen conventions.
    if type(value) is not int or value < 1:
        raise CounterfactualPlanError(
            f"lap_offset_n must be a positive plain int (N >= 1), got {value!r}")
    return value


def _require_compound(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and value in SUPPORTED_REQUESTED_COMPOUNDS:
        return value
    raise CounterfactualPlanError(
        "requested_compound must be None or one of "
        f"{list(SUPPORTED_REQUESTED_COMPOUNDS)}, got {value!r}")


#: Canonical per-future position-gain definition (B1 correction):
#: factual_T - simulated_final, so positive means a numerically
#: lower/better finishing position (P5 -> P2 = +3).
POSITION_GAIN_DEFINITION = (
    "factual_position_T - simulated_final_position; "
    "positive = numerically lower/better finish (positions gained); "
    "zero = unchanged; negative = numerically higher/worse finish "
    "(positions lost); expected aggregate is the arithmetic mean over "
    "valid membership"
)


def position_gain(factual_position_t: int,
                  simulated_final_position: int) -> int:
    """Per-future position gain (descriptive simulated outcome).

    ``factual_position_t - simulated_final_position``: P5 -> P2 = +3,
    P5 -> P5 = 0, P5 -> P8 = -3. Uses the factual causal position at T
    and the MC2 simulated final position \u2014 never any historical
    final result.
    """
    if type(factual_position_t) is not int or factual_position_t < 1:
        raise CounterfactualPlanError(
            "factual_position_t must be a positive plain int, "
            f"got {factual_position_t!r}")
    if type(simulated_final_position) is not int or simulated_final_position < 1:
        raise CounterfactualPlanError(
            "simulated_final_position must be a positive plain int, "
            f"got {simulated_final_position!r}")
    return factual_position_t - simulated_final_position


def mechanical_equivalent_action(lap_offset_n: int) -> str | None:
    """Validation-only equivalence to frozen V3.6 mechanics.

    From the frozen runtime decision rule (force at decision_lap+1 for
    PIT_NOW; baseline at +1 then force at +2 for PIT_NEXT_LAP):
    N=1 behaves as PIT_NOW, N=2 as PIT_NEXT_LAP. Larger N has no V3.6
    counterpart. This never reinterprets V3.6 actions.
    """
    _require_offset_n(lap_offset_n)
    if lap_offset_n == 1:
        return "PIT_NOW"
    if lap_offset_n == 2:
        return "PIT_NEXT_LAP"
    return None


@dataclass(frozen=True)
class ScheduledIntervention:
    """One declarative scheduled intervention (no execution logic).

    ``lap_offset_n`` is the simulation-relative future lap offset from
    factual T (NOT a historical lap lookup). The scheduled pit lap is
    ``decision_lap + lap_offset_n``: N=1 forces at the first simulated
    lap (PIT_NOW mechanics), N=2 waits one lap then forces
    (PIT_NEXT_LAP mechanics).
    """

    target_driver_id: str
    kind: str
    lap_offset_n: int
    requested_compound: str | None = None
    decision_lap: int = 0
    decision_state_identity: str = ""
    schema_version: str = SCHEDULED_INTERVENTION_VERSION
    provenance: Provenance = Provenance.USER_ASSUMPTION

    def __post_init__(self) -> None:
        if self.schema_version != SCHEDULED_INTERVENTION_VERSION:
            raise CounterfactualPlanError(
                f"unsupported schema_version {self.schema_version!r}")
        if self.kind not in INTERVENTION_KINDS:
            raise CounterfactualPlanError(
                f"kind must be one of {list(INTERVENTION_KINDS)} "
                f"(rejected kinds fail closed), got {self.kind!r}")
        object.__setattr__(self, "target_driver_id",
                           _require_text(self.target_driver_id,
                                         "target_driver_id"))
        object.__setattr__(self, "lap_offset_n",
                           _require_offset_n(self.lap_offset_n))
        object.__setattr__(self, "requested_compound",
                           _require_compound(self.requested_compound))
        if type(self.decision_lap) is not int or self.decision_lap < 0:
            raise CounterfactualPlanError(
                "decision_lap must be a non-negative plain int, "
                f"got {self.decision_lap!r}")
        object.__setattr__(self, "decision_state_identity",
                           _require_identity(self.decision_state_identity,
                                             "decision_state_identity"))
        if self.provenance is not Provenance.USER_ASSUMPTION:
            raise CounterfactualPlanError(
                "provenance must be USER_ASSUMPTION (a plan is a user "
                "assumption, never factual state)")

    @property
    def scheduled_lap(self) -> int:
        """Simulated trigger lap: decision_lap + N (off-by-one frozen)."""
        return self.decision_lap + self.lap_offset_n

    def validate_horizon(self, scheduled_laps: int) -> None:
        """Enforce N <= remaining_laps - 1 (V3.7A horizon rule)."""
        if type(scheduled_laps) is not int or scheduled_laps < 1:
            raise CounterfactualPlanError(
                f"scheduled_laps must be a positive int, got {scheduled_laps!r}")
        remaining = scheduled_laps - self.decision_lap
        if self.lap_offset_n > remaining - 1:
            raise CounterfactualPlanError(
                f"lap_offset_n={self.lap_offset_n} exceeds horizon "
                f"(remaining {remaining} laps: N <= remaining - 1)")

    def to_dict(self) -> dict:
        return {
            "target_driver_id": self.target_driver_id,
            "kind": self.kind,
            "lap_offset_n": self.lap_offset_n,
            "requested_compound": self.requested_compound,
            "decision_lap": self.decision_lap,
            "decision_state_identity": self.decision_state_identity,
            "schema_version": self.schema_version,
            "provenance": self.provenance.value,
        }

    def identity(self) -> str:
        return canonical_sha256(self.to_dict())


def canonical_plan_dict(*, targets: tuple, interventions: tuple,
                        rival_driver_id: str | None) -> dict:
    """Canonical payload: interventions sorted chronologically.

    Sort key (scheduled_lap, target, kind, compound) makes input order
    irrelevant across targets while preserving chronological meaning for
    same-target sequences.
    """
    ordered = sorted(
        interventions,
        key=lambda i: (i.scheduled_lap, i.target_driver_id, i.kind,
                       i.requested_compound or ""),
    )
    return {
        "targets": sorted(targets),
        "interventions": [i.to_dict() for i in ordered],
        "rival_driver_id": rival_driver_id,
        "plan_version": PLAN_VERSION,
    }


def plan_identity(*, targets: tuple, interventions: tuple,
                  rival_driver_id: str | None) -> str:
    return canonical_sha256(
        canonical_plan_dict(targets=targets, interventions=interventions,
                            rival_driver_id=rival_driver_id))


@dataclass(frozen=True)
class CounterfactualPlan:
    """A declarative counterfactual schedule (no execution logic)."""

    target_driver_ids: tuple
    interventions: tuple
    rival_driver_id: str | None = None
    plan_version: str = PLAN_VERSION
    provenance: Provenance = Provenance.USER_ASSUMPTION

    def __post_init__(self) -> None:
        if self.plan_version != PLAN_VERSION:
            raise CounterfactualPlanError(
                f"unsupported plan_version {self.plan_version!r}")
        targets = tuple(_require_text(t, "target_driver_id")
                        for t in self.target_driver_ids)
        if len(set(targets)) != len(targets):
            raise CounterfactualPlanError(
                f"duplicate target_driver_id in {targets!r}")
        if not targets:
            raise CounterfactualPlanError("plan needs at least one target")
        object.__setattr__(self, "target_driver_ids", targets)
        for item in self.interventions:
            if not isinstance(item, ScheduledIntervention):
                raise CounterfactualPlanError(
                    "interventions must be ScheduledIntervention, "
                    f"got {item!r}")
            if item.target_driver_id not in targets:
                raise CounterfactualPlanError(
                    "intervention target "
                    f"{item.target_driver_id!r} not in plan targets "
                    f"{list(targets)!r}")
        if not self.interventions:
            raise CounterfactualPlanError("plan needs at least one intervention")
        rival = self.rival_driver_id
        if rival is not None:
            rival = _require_text(rival, "rival_driver_id")
            if rival in targets:
                raise CounterfactualPlanError(
                    f"rival {rival!r} must differ from plan targets")
        object.__setattr__(self, "rival_driver_id", rival)
        if self.provenance is not Provenance.USER_ASSUMPTION:
            raise CounterfactualPlanError(
                "provenance must be USER_ASSUMPTION")

    def to_dict(self) -> dict:
        return canonical_plan_dict(
            targets=self.target_driver_ids,
            interventions=self.interventions,
            rival_driver_id=self.rival_driver_id)

    def identity(self) -> str:
        return plan_identity(
            targets=self.target_driver_ids,
            interventions=self.interventions,
            rival_driver_id=self.rival_driver_id)


def transition_allowed(from_state: str, to_state: str) -> bool:
    """Legal lifecycle edge check (absent edge = fail closed)."""
    if from_state not in TRANSITIONS:
        raise CounterfactualPlanError(f"unknown lifecycle state {from_state!r}")
    if to_state not in LIFECYCLE_STATES:
        raise CounterfactualPlanError(f"unknown lifecycle state {to_state!r}")
    return to_state in TRANSITIONS[from_state]


def classify_conflict(first: ScheduledIntervention,
                      second: ScheduledIntervention) -> str:
    """Conflict-matrix verdict for an intervention pair (fail closed)."""
    same_target = first.target_driver_id == second.target_driver_id
    same_trigger = first.scheduled_lap == second.scheduled_lap
    identical = (
        same_target and same_trigger and first.kind == second.kind
        and first.requested_compound == second.requested_compound
        and first.lap_offset_n == second.lap_offset_n
    )
    if identical:
        return "DEDUPLICATE"
    if same_target and same_trigger:
        # Same trigger, different compounds (or kinds): scientific
        # contradiction \u2014 no silent priority.
        return "INVALID"
    if same_target:
        # Compositional multi-stop: valid at contract time; the earlier
        # event may supersede the later at runtime.
        return "RUNTIME_SUPERSESSION"
    # Distinct targets: valid (no team-stacking delay modelled \u2014
    # documented limitation, not invented mechanics).
    return "VALID"


@dataclass(frozen=True)
class PlanComparisonKey:
    """Deterministic comparison identity (reference-vs-plan or plan-vs-plan).

    For REFERENCE_VS_PLAN, ``base_identity`` is REFERENCE_KIND and
    ``alternative_identity`` is the plan identity. For PLAN_VS_PLAN,
    BASE = plan A and ALT = plan B (positive = improvement of B over A).
    """

    key_version: str
    comparison_form: str
    state_identity: str
    base_identity: str
    alternative_identity: str
    simulator_identity: str
    parameter_identity: str
    simulation_count: int
    master_seed: int
    outcome_schema_version: str
    rival_driver_id: str | None = None

    def __post_init__(self) -> None:
        if self.key_version != COMPARISON_KEY_VERSION:
            raise CounterfactualPlanError(
                f"unsupported key_version {self.key_version!r}")
        if self.comparison_form not in COMPARISON_FORMS:
            raise CounterfactualPlanError(
                f"comparison_form must be one of {list(COMPARISON_FORMS)}, "
                f"got {self.comparison_form!r}")
        object.__setattr__(self, "state_identity",
                           _require_identity(self.state_identity,
                                             "state_identity"))
        object.__setattr__(self, "base_identity",
                           _require_text(self.base_identity, "base_identity"))
        object.__setattr__(self, "alternative_identity",
                           _require_text(self.alternative_identity,
                                         "alternative_identity"))
        if self.base_identity == self.alternative_identity:
            raise CounterfactualPlanError(
                "base and alternative must differ")
        if self.simulation_count != PRODUCTION_SIMULATION_COUNT:
            raise CounterfactualPlanError(
                "simulation_count is fixed at "
                f"{PRODUCTION_SIMULATION_COUNT} (no caller override), "
                f"got {self.simulation_count!r}")
        if type(self.master_seed) is not int or self.master_seed < 0:
            raise CounterfactualPlanError(
                f"master_seed must be a non-negative int, got {self.master_seed!r}")
        if self.outcome_schema_version != OUTCOME_SCHEMA_VERSION:
            raise CounterfactualPlanError(
                "unsupported outcome_schema_version "
                f"{self.outcome_schema_version!r}")
        if self.rival_driver_id is not None:
            object.__setattr__(self, "rival_driver_id",
                               _require_text(self.rival_driver_id,
                                             "rival_driver_id"))

    def to_dict(self) -> dict:
        return {
            "key_version": self.key_version,
            "comparison_form": self.comparison_form,
            "state_identity": self.state_identity,
            "base_identity": self.base_identity,
            "alternative_identity": self.alternative_identity,
            "simulator_identity": self.simulator_identity,
            "parameter_identity": self.parameter_identity,
            "simulation_count": self.simulation_count,
            "master_seed": self.master_seed,
            "outcome_schema_version": self.outcome_schema_version,
            "rival_driver_id": self.rival_driver_id,
        }

    def identity(self) -> str:
        return canonical_sha256(self.to_dict())


def build_unsupported_result(*, level: str, reason_code: str,
                             human_reason: str, state_identity: str,
                             plan_identity: str | None = None,
                             comparison_identity: str | None = None,
                             provenance: dict | None = None) -> dict:
    """Deterministic unsupported result: metrics EMPTY, never zeros/NaN."""
    if level not in ELIGIBILITY_LEVELS:
        raise CounterfactualPlanError(
            f"level must be one of {list(ELIGIBILITY_LEVELS)}, got {level!r}")
    _require_text(reason_code, "reason_code")
    _require_text(human_reason, "human_reason")
    _require_identity(state_identity, "state_identity")
    return {
        "supported": False,
        "level": level,
        "reason_code": reason_code,
        "human_reason": human_reason,
        "state_identity": state_identity,
        "plan_identity": plan_identity,
        "comparison_identity": comparison_identity,
        "metrics": {},
        "provenance": provenance or {},
    }


#: Delta orientation (positive = improvement; plan-vs-plan BASE=A, ALT=B).
DELTA_ORIENTATION = {
    "delta_win_frequency": "alt - base",
    "delta_podium_frequency": "alt - base",
    "delta_top5_frequency": "alt - base",
    "delta_top10_frequency": "alt - base",
    "delta_expected_finish": "base - alt",
    "delta_p_ahead_of_rival": "alt - base",
    "delta_pit_count": "alt - base (descriptive; not improvement-directed)",
    "delta_position_gain_loss": "alt - base",
    "rule": "POSITIVE = IMPROVEMENT (except pit_count, descriptive)",
}
