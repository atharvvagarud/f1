"""V3.7C schedule-capable counterfactual execution engine.

Orchestration only: CounterfactualPlan -> schedule adapter -> frozen MC2
seam (``MonteCarloEngine.run``) -> outcome/comparison aggregation. No new
simulator, no API, no cache, no frontend, no V3.5. Scientific semantics
are frozen in V3.7A/B; this module executes them.

Import discipline: stdlib + numpy + frozen simulation leaves
(``simulation.state``, ``simulation.config``, ``simulation.engine``,
``simulation.monte_carlo``) + ``counterfactual.contracts``. Never the
V3.6 strategy engine, the API, the frontend, V3.5, or evaluation code.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from raceintel.counterfactual import contracts as C
from raceintel.simulation.config import Assumptions, SimulationConfig
from raceintel.simulation.engine import ExecutionPolicy
from raceintel.simulation.monte_carlo import MonteCarloEngine
from raceintel.simulation.state import canonical_sha256

__all__ = [
    "ENGINE_IDENTITY",
    "MC2_IDENTITY",
    "BOOTSTRAP_REPLICATES",
    "CONFIDENCE_LEVEL",
    "MIN_VALID_PAIRS_FOR_CI",
    "SeamEvent",
    "SeamSchedule",
    "ArmAggregate",
    "PlanComparisonResult",
    "check_eligibility",
    "unsupported_for",
    "run_arm",
    "compare_reference_vs_plan",
    "compare_plan_vs_plan",
    "paired_percentile_ci",
]

#: C engine mechanics identity (not a performance claim).
ENGINE_IDENTITY = "v3.7c-counterfactual-engine-v1"

#: Frozen simulator identity served by this engine.
MC2_IDENTITY = "MC2-E (E_AR1_RESIDUAL)"

#: Paired MC sampling uncertainty (frozen V3.6 machinery, re parameters).
BOOTSTRAP_REPLICATES = 2000
CONFIDENCE_LEVEL = 0.95
MIN_VALID_PAIRS_FOR_CI = 30


@dataclass(frozen=True)
class SeamEvent:
    """Duck-typed schedule event for the frozen MC2 seam.

    ``requested_compound`` translates SAMPLED to None (sampled transition,
    matching V3.6 seam semantics); explicit compounds pass through.
    """

    target_driver_id: str
    kind: str
    lap_offset_n: int
    requested_compound: str | None
    decision_lap: int


@dataclass(frozen=True)
class SeamSchedule:
    """Duck-typed schedule for ``_resolve_schedule`` (seam protocol)."""

    schedule_events: tuple
    decision_state_identity: str


def _to_seam(plan: C.CounterfactualPlan) -> SeamSchedule:
    seen = set()
    events = []
    for i in plan.interventions:
        key = (i.target_driver_id, i.kind, i.lap_offset_n,
               i.requested_compound, i.decision_lap)
        if key in seen:
            continue  # B conflict matrix: identical duplicates collapse
        seen.add(key)
        events.append(SeamEvent(
            target_driver_id=i.target_driver_id,
            kind=i.kind,
            lap_offset_n=i.lap_offset_n,
            requested_compound=(None if i.requested_compound in
                                (None, "SAMPLED") else i.requested_compound),
            decision_lap=i.decision_lap,
        ))
    return SeamSchedule(
        schedule_events=tuple(events),
        decision_state_identity=plan.interventions[0].decision_state_identity,
    )


def unsupported_for(*, level: str, reason_code: str, human_reason: str,
                    state, plan: C.CounterfactualPlan | None = None,
                    comparison: C.PlanComparisonKey | None = None) -> dict:
    """B unsupported-result contract wrapper."""
    return C.build_unsupported_result(
        level=level, reason_code=reason_code, human_reason=human_reason,
        state_identity=state.identity(),
        plan_identity=(plan.identity() if plan is not None else None),
        comparison_identity=(comparison.identity()
                             if comparison is not None else None),
        provenance={"engine_identity": ENGINE_IDENTITY},
    )


def check_eligibility(state, plan: C.CounterfactualPlan,
                      *, rival_driver_id: str | None = None,
                      scheduled_laps: int | None = None):
    """Eligibility hierarchy STATE/INTERVENTION/PLAN/COMPARISON.

    Returns ``(eligible, level, reason_code, human_reason)``; eligible True
    carries level/reason None. Syntactically valid is not automatically
    eligible.
    """
    roster = list(state.roster_driver_ids)
    for target in plan.target_driver_ids:
        if target not in roster:
            return (False, "STATE", "TARGET_NOT_PRESENT",
                    f"target {target!r} not in factual roster")
    horizon = scheduled_laps if scheduled_laps is not None else \
        state.scheduled_laps
    for item in plan.interventions:
        try:
            item.validate_horizon(horizon)
        except C.CounterfactualPlanError as exc:
            return (False, "INTERVENTION", "INVALID_TRIGGER", str(exc))
    items = list(plan.interventions)
    for a in range(len(items)):
        for b in range(a + 1, len(items)):
            if C.classify_conflict(items[a], items[b]) == "INVALID":
                return (False, "PLAN", "CONFLICTING_INTERVENTIONS",
                        "same target and trigger with different compounds")
    if not items:
        return (False, "PLAN", "INVALID_PLAN", "plan has no interventions")
    if rival_driver_id is not None and rival_driver_id not in roster:
        return (False, "COMPARISON", "RIVAL_NOT_PRESENT",
                f"rival {rival_driver_id!r} not in factual roster")
    if rival_driver_id is not None and \
            rival_driver_id in plan.target_driver_ids:
        return (False, "COMPARISON", "RIVAL_NOT_PRESENT",
                "rival must differ from plan targets")
    return (True, None, None, None)


def _column(state, driver_id: str) -> int:
    return list(state.roster_driver_ids).index(driver_id)


def paired_percentile_ci(values, *, seed: int):
    """Paired percentile bootstrap CI (B=2000, 95%) over pair differences.

    Mechanical reuse of the frozen paired estimator pattern. Returns
    ``(low, high)`` or ``(None, None)`` under MIN_VALID_PAIRS_FOR_CI.
    """
    arr = np.asarray(values, dtype=float)
    n = int(arr.size)
    if n < MIN_VALID_PAIRS_FOR_CI:
        return (None, None)
    rng = np.random.default_rng(seed)
    means = np.empty(BOOTSTRAP_REPLICATES, dtype=float)
    for r in range(BOOTSTRAP_REPLICATES):
        means[r] = arr[rng.integers(0, n, size=n)].mean()
    alpha = (1.0 - CONFIDENCE_LEVEL) / 2.0
    return (float(np.quantile(means, alpha)),
            float(np.quantile(means, 1.0 - alpha)))


def _ci_seed(comparison_identity: str) -> int:
    return int(comparison_identity[:8], 16) % (2 ** 31 - 1)


@dataclass
class ArmAggregate:
    """Per-arm aggregates over an index membership mask."""

    target_driver_id: str
    n: int
    win_frequency: float
    podium_frequency: float
    top5_frequency: float
    top10_frequency: float
    expected_finish: float
    median_finish: float
    finish_q25: float
    finish_q75: float
    finish_position_distribution: tuple
    downside_vs_other: float | None
    p_ahead_of_rival: float | None
    expected_pit_count: float
    expected_position_gain: float | None

    def to_dict(self) -> dict:
        return {
            "target_driver_id": self.target_driver_id,
            "n": self.n,
            "win_frequency": self.win_frequency,
            "podium_frequency": self.podium_frequency,
            "top5_frequency": self.top5_frequency,
            "top10_frequency": self.top10_frequency,
            "expected_finish": self.expected_finish,
            "median_finish": self.median_finish,
            "finish_q25": self.finish_q25,
            "finish_q75": self.finish_q75,
            "finish_position_distribution": [
                {"finish_position": int(p), "frequency": float(f)}
                for p, f in self.finish_position_distribution],
            "downside_vs_other": self.downside_vs_other,
            "p_ahead_of_rival": self.p_ahead_of_rival,
            "expected_pit_count": self.expected_pit_count,
            "expected_position_gain": self.expected_position_gain,
        }


def _aggregate(*, state, target_driver_id: str, positions: np.ndarray,
               other_positions: np.ndarray | None,
               rival_positions: np.ndarray | None,
               pit_counts: np.ndarray, factual_position: int | None,
               roster_size: int) -> ArmAggregate:
    pos = np.asarray(positions, dtype=float)
    n = int(pos.size)
    dist = []
    for p in range(1, roster_size + 1):
        dist.append((p, float((pos == p).mean()) if n else 0.0))
    downside = None
    if other_positions is not None and n:
        downside = float((pos > np.asarray(other_positions,
                                           dtype=float)).mean())
    ahead = None
    if rival_positions is not None and n:
        ahead = float((pos < np.asarray(rival_positions, dtype=float)).mean())
    gain = None
    if factual_position is not None and n:
        gain = float(np.mean([C.position_gain(int(factual_position), int(v))
                              for v in pos]))
    return ArmAggregate(
        target_driver_id=target_driver_id, n=n,
        win_frequency=float((pos == 1).mean()) if n else 0.0,
        podium_frequency=float((pos <= 3).mean()) if n else 0.0,
        top5_frequency=float((pos <= 5).mean()) if n else 0.0,
        top10_frequency=float((pos <= 10).mean()) if n else 0.0,
        expected_finish=float(pos.mean()) if n else 0.0,
        median_finish=float(np.median(pos)) if n else 0.0,
        finish_q25=float(np.quantile(pos, 0.25)) if n else 0.0,
        finish_q75=float(np.quantile(pos, 0.75)) if n else 0.0,
        finish_position_distribution=tuple(dist),
        downside_vs_other=downside,
        p_ahead_of_rival=ahead,
        expected_pit_count=float(np.asarray(pit_counts,
                                            dtype=float).mean()) if n else 0.0,
        expected_position_gain=gain,
    )


def run_arm(state, parameters, config: SimulationConfig,
            assumptions: Assumptions, plan: C.CounterfactualPlan | None, *,
            chunk_size: int | None = None):
    """Run one arm (reference when plan is None, else the plan).

    Returns ``(result, index_outcomes, schedule_outcomes)``. Same config
    and seeds across arms give CRN pairing by construction.
    """
    kwargs = {}
    if chunk_size is not None:
        kwargs["chunk_size"] = chunk_size
    engine = MonteCarloEngine(**kwargs)
    intervention = None if plan is None else _to_seam(plan)
    result = engine.run(
        state, parameters, config, assumptions,
        execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT,
        collect_index_outcomes=True, intervention=intervention)
    return result, engine.last_index_outcomes, engine.last_intervention_outcome


def _factual_position(state, driver_id: str):
    for entry in state.drivers:
        if entry.driver_id == driver_id:
            return entry.position
    return None


def _delta(name: str, alt: float | None, base: float | None,
           seed: int, alt_vals=None, base_vals=None):
    if alt is None or base is None:
        return {"metric": name, "point_estimate": None, "paired_se": None,
                "ci_low": None, "ci_high": None}
    point = float(alt - base)
    se = None
    low, high = (None, None)
    if alt_vals is not None and base_vals is not None:
        diffs = np.asarray(alt_vals, dtype=float) - np.asarray(
            base_vals, dtype=float)
        if diffs.size >= MIN_VALID_PAIRS_FOR_CI:
            se = float(diffs.std(ddof=1) / np.sqrt(diffs.size))
            low, high = paired_percentile_ci(diffs, seed=seed)
    return {"metric": name, "point_estimate": point, "paired_se": se,
            "ci_low": low, "ci_high": high}


@dataclass
class PlanComparisonResult:
    """Typed deterministic comparison result (reference-vs-plan or plan-vs-plan)."""

    supported: bool
    comparison_form: str
    comparison_identity: str
    base_identity: str
    alternative_identity: str
    target_driver_id: str
    rival_driver_id: str | None
    complete_pairs: int
    requested_pairs: int
    excluded_pairs: int
    base_aggregate: dict
    alternative_aggregate: dict
    deltas: dict
    provenance: dict = field(default_factory=dict)
    schedule_outcomes: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "supported": self.supported,
            "comparison_form": self.comparison_form,
            "comparison_identity": self.comparison_identity,
            "base_identity": self.base_identity,
            "alternative_identity": self.alternative_identity,
            "target_driver_id": self.target_driver_id,
            "rival_driver_id": self.rival_driver_id,
            "complete_pairs": self.complete_pairs,
            "requested_pairs": self.requested_pairs,
            "excluded_pairs": self.excluded_pairs,
            "base_aggregate": self.base_aggregate,
            "alternative_aggregate": self.alternative_aggregate,
            "deltas": self.deltas,
            "provenance": self.provenance,
            "schedule_outcomes": self.schedule_outcomes,
        }

    def identity(self) -> str:
        return canonical_sha256(self.to_dict())


def _sched_to_dicts(sched_out) -> list:
    """Schedule lifecycle evidence as plain dicts (empty for reference).

    Events within each simulation are canonically ordered by
    (target, trigger) so input-order-permuted plans share result identity.
    """
    if not sched_out:
        return []
    out = []
    for entry in sched_out:
        entry = dict(entry) if isinstance(entry, dict) else entry
        if isinstance(entry, dict) and isinstance(entry.get("events"), list):
            entry = dict(entry)
            entry["events"] = sorted(
                entry["events"],
                key=lambda e: (e.get("target_driver_id"),
                               e.get("trigger_lap")))
        out.append(entry)
    return out


def _compare(*, state, parameters, config: SimulationConfig,
             assumptions: Assumptions, form: str,
             base_plan: C.CounterfactualPlan | None,
             alt_plan: C.CounterfactualPlan,
             target_driver_id: str, rival_driver_id: str | None,
             base_identity: str, chunk_size: int | None = None):
    base_res, base_idx, base_sched = run_arm(
        state, parameters, config, assumptions, base_plan,
        chunk_size=chunk_size)
    alt_res, alt_idx, sched_out = run_arm(
        state, parameters, config, assumptions, alt_plan,
        chunk_size=chunk_size)
    requested = int(config.simulation_count)
    valid_base = np.asarray(base_idx["valid"], dtype=bool)
    valid_alt = np.asarray(alt_idx["valid"], dtype=bool)
    mask = valid_base & valid_alt
    pair_idx = np.where(mask)[0]
    n = int(mask.sum())
    key = C.PlanComparisonKey(
        key_version=C.COMPARISON_KEY_VERSION, comparison_form=form,
        state_identity=state.identity(), base_identity=base_identity,
        alternative_identity=alt_plan.identity(),
        simulator_identity=MC2_IDENTITY,
        parameter_identity=parameters.parameter_identity().identity(),
        simulation_count=config.simulation_count,
        master_seed=config.master_seed,
        outcome_schema_version=C.OUTCOME_SCHEMA_VERSION,
        rival_driver_id=rival_driver_id)
    roster = int(state.roster_size)
    tcol = _column(state, target_driver_id)
    rcol = _column(state, rival_driver_id) if rival_driver_id else None
    bp = np.asarray(base_idx["finish_position"])[pair_idx][:, tcol]
    ap = np.asarray(alt_idx["finish_position"])[pair_idx][:, tcol]
    bpit = np.asarray(base_idx["pit_count"])[pair_idx][:, tcol]
    apit = np.asarray(alt_idx["pit_count"])[pair_idx][:, tcol]
    factual = _factual_position(state, target_driver_id)
    br = np.asarray(base_idx["finish_position"])[pair_idx][:, rcol] \
        if rcol is not None else None
    ar = np.asarray(alt_idx["finish_position"])[pair_idx][:, rcol] \
        if rcol is not None else None
    base_agg = _aggregate(
        state=state, target_driver_id=target_driver_id, positions=bp,
        other_positions=ap, rival_positions=br, pit_counts=bpit,
        factual_position=factual, roster_size=roster)
    alt_agg = _aggregate(
        state=state, target_driver_id=target_driver_id, positions=ap,
        other_positions=bp, rival_positions=ar, pit_counts=apit,
        factual_position=factual, roster_size=roster)
    seed = _ci_seed(key.identity())
    # Orientation (both forms): probability-like deltas ALT - BASE;
    # expected finish BASE - ALT (smaller finish is better); position
    # gain ALT - BASE (larger gain is better). For REFERENCE_VS_PLAN
    # BASE is the reference; for PLAN_VS_PLAN BASE is plan A.
    deltas = {
        "delta_win_frequency": _delta(
            "delta_win_frequency", alt_agg.win_frequency,
            base_agg.win_frequency, seed,
            (ap == 1).astype(float), (bp == 1).astype(float)),
        "delta_podium_frequency": _delta(
            "delta_podium_frequency", alt_agg.podium_frequency,
            base_agg.podium_frequency, seed + 1,
            (ap <= 3).astype(float), (bp <= 3).astype(float)),
        "delta_expected_finish": _delta(
            "delta_expected_finish", base_agg.expected_finish,
            alt_agg.expected_finish, seed + 2,
            bp.astype(float), ap.astype(float)),
        "delta_p_ahead_of_rival": _delta(
            "delta_p_ahead_of_rival", alt_agg.p_ahead_of_rival,
            base_agg.p_ahead_of_rival, seed + 3),
        "delta_position_gain_loss": _delta(
            "delta_position_gain_loss", alt_agg.expected_position_gain,
            base_agg.expected_position_gain, seed + 4),
    }
    provenance = {
        "v37a_contract_identity": "1735954212ec31286fede041639875610003a09cf817177e22cc908e3fcb0a12",
        "v37b_contract_identity": "1865537503136ed3d8603e53741902c320df9387222655b38eef51640294e970",
        "engine_identity": ENGINE_IDENTITY,
        "mc2_identity": MC2_IDENTITY,
        "state_identity": state.identity(),
        "plan_identity": alt_plan.identity(),
        "comparison_identity": key.identity(),
        "simulation_count": config.simulation_count,
        "master_seed": config.master_seed,
        "outcome_schema_version": C.OUTCOME_SCHEMA_VERSION,
        "reference_kind": C.REFERENCE_KIND,
        "comparison_form": form,
        "seed_stream_rule": C.SEED_STREAM_RULE,
    }
    return PlanComparisonResult(
        supported=True, comparison_form=form,
        comparison_identity=key.identity(), base_identity=base_identity,
        alternative_identity=alt_plan.identity(),
        target_driver_id=target_driver_id, rival_driver_id=rival_driver_id,
        complete_pairs=n, requested_pairs=requested,
        excluded_pairs=int(requested - n),
        base_aggregate=base_agg.to_dict(),
        alternative_aggregate=alt_agg.to_dict(), deltas=deltas,
        provenance=provenance,
        schedule_outcomes={
            "base": _sched_to_dicts(base_sched),
            "alternative": _sched_to_dicts(sched_out),
        })


def compare_reference_vs_plan(*, state, parameters, config,
                              assumptions, plan: C.CounterfactualPlan,
                              rival_driver_id: str | None = None,
                              chunk_size: int | None = None):
    """REFERENCE_VS_PLAN with V3.6 positive-improvement orientation."""
    eligible, level, reason, human = check_eligibility(
        state, plan, rival_driver_id=rival_driver_id)
    if not eligible:
        return unsupported_for(level=level, reason_code=reason,
                               human_reason=human, state=state, plan=plan)
    result = _compare(
        state=state, parameters=parameters, config=config,
        assumptions=assumptions, form="REFERENCE_VS_PLAN", base_plan=None,
        alt_plan=plan, target_driver_id=plan.target_driver_ids[0],
        rival_driver_id=rival_driver_id or plan.rival_driver_id,
        base_identity=C.REFERENCE_KIND, chunk_size=chunk_size)
    return result


def compare_plan_vs_plan(*, state, parameters, config, assumptions,
                         plan_a: C.CounterfactualPlan,
                         plan_b: C.CounterfactualPlan,
                         rival_driver_id: str | None = None,
                         chunk_size: int | None = None):
    """PLAN_A_VS_PLAN_B with BASE=A, ALT=B orientation.

    Canonicalization never swaps orientation: callers pass plans in BASE,
    ALT roles explicitly.
    """
    for plan in (plan_a, plan_b):
        eligible, level, reason, human = check_eligibility(
            state, plan, rival_driver_id=rival_driver_id)
        if not eligible:
            return unsupported_for(level=level, reason_code=reason,
                                   human_reason=human, state=state, plan=plan)
    if plan_a.target_driver_ids[0] != plan_b.target_driver_ids[0]:
        return unsupported_for(
            level="COMPARISON", reason_code="INVALID_PLAN",
            human_reason="plan-vs-plan requires the same primary target",
            state=state, plan=plan_b)
    result = _compare(
        state=state, parameters=parameters, config=config,
        assumptions=assumptions, form="PLAN_VS_PLAN", base_plan=plan_a,
        alt_plan=plan_b, target_driver_id=plan_b.target_driver_ids[0],
        rival_driver_id=rival_driver_id or plan_b.rival_driver_id,
        base_identity=plan_a.identity(), chunk_size=chunk_size)
    return result
