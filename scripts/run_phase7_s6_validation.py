"""Phase-7 S6 scientific validation + historical characterization.

This is the final validation corpus for the Phase-7 Strategy Engine. It does
NOT add strategy capability. It measures the existing S1-S5 system on a
deterministic, predeclared representative corpus and records actual values
only.

Everything derives from the frozen S6 protocol in
``tests/s6_validation_protocol.py`` (frozen before this corpus ran). The
historical future is never an input; no counterfactual accuracy is claimed.

Output: ``data/v2/strategy/s6_validation_v1.json`` (``/data/v2/`` is
git-ignored by repository policy; generated, reproducible from this script).

Usage (from the repository root)::

    /opt/homebrew/bin/python3.11 scripts/run_phase7_s6_validation.py
"""

from __future__ import annotations

import hashlib
import json
import platform
import statistics
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (str(ROOT), str(ROOT / "tests")):
    if extra not in sys.path:
        sys.path.insert(0, extra)

import s6_validation_protocol as P  # noqa: E402

from v2.simulation.config import Assumptions  # noqa: E402
from v2.simulation.state import (  # noqa: E402
    DriverSimState,
    DriverStatus,
    SimulationEnvironment,
    SimulationState,
)
from v2.strategy import (  # noqa: E402
    COMPARISON_VERSION,
    OBJECTIVE_METRIC,
    STRATEGY_OBJECTIVES,
    UNCERTAINTY_VERSION,
    evaluate_objective,
    compare_strategies,
)
from v2.strategy.candidates import CANDIDATE_CONTRACT_VERSION  # noqa: E402
from v2.strategy.contracts import (  # noqa: E402
    INTERVENTION_VERSION,
    STRATEGY_CONTRACT_VERSION,
)
from v2.strategy.objectives import OBJECTIVE_VERSION  # noqa: E402
from v2.strategy.paired import PAIRED_CONTRACT_VERSION  # noqa: E402

ARTIFACT_PATH = ROOT / P.VALIDATION_ARTIFACT

PARAM_MANIFEST = (ROOT / "data" / "v2" / "simulation" / "params"
                  / "r3-v1__through-2024" / "manifest.json")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _environment() -> dict:
    import numpy as np
    try:
        import pandas as pd
        pandas_version = pd.__version__
    except Exception:  # pragma: no cover - pandas is present in this repo
        pandas_version = None
    try:
        import sklearn
        sklearn_version = sklearn.__version__
    except Exception:  # pragma: no cover
        sklearn_version = None
    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "machine": platform.machine(),
        "numpy_version": np.__version__,
        "pandas_version": pandas_version,
        "sklearn_version": sklearn_version,
        "simulation_contract_version": __import__(
            "v2.simulation", fromlist=["SIMULATION_CONTRACT_VERSION"]
        ).SIMULATION_CONTRACT_VERSION,
        "strategy_contract_version": STRATEGY_CONTRACT_VERSION,
        "intervention_version": INTERVENTION_VERSION,
        "comparison_version": COMPARISON_VERSION,
        "candidate_contract_version": CANDIDATE_CONTRACT_VERSION,
        "paired_contract_version": PAIRED_CONTRACT_VERSION,
        "uncertainty_version": UNCERTAINTY_VERSION,
        "objective_version": OBJECTIVE_VERSION,
        "parameter_identity_through_2024": (
            _sha256(PARAM_MANIFEST) if PARAM_MANIFEST.exists() else None),
        "monte_carlo_sha256": _sha256(
            ROOT / "v2" / "simulation" / "monte_carlo.py"),
    }


def _candidate_record(candidate) -> dict:
    record = {
        "candidate_key": candidate.candidate.key,
        "valid": candidate.valid,
        "reason": candidate.reason,
        "evaluated": candidate.evaluated,
        "delta_win_probability": candidate.delta_win_probability,
        "delta_podium_probability": candidate.delta_podium_probability,
        "delta_expected_finish": candidate.delta_expected_finish,
        "valid_pairs": candidate.valid_pairs,
        "baseline_only_valid": candidate.baseline_only_valid,
        "intervention_only_valid": candidate.intervention_only_valid,
        "both_invalid": candidate.both_invalid,
        "validity_sets_match": candidate.validity_sets_match,
    }
    if candidate.aggregate is not None:
        record["aggregate"] = candidate.aggregate.to_dict()
    if candidate.execution is not None:
        execution = candidate.execution
        record["execution"] = {
            "applied_rate": execution.applied_rate,
            "suppressed_rate": execution.suppressed_rate,
            "superseded_rate": execution.superseded_rate,
            "inert_rate": execution.inert_rate,
            "race_end_cancelled_rate": execution.race_end_cancelled_rate,
            "baseline_pit_suppressed": execution.baseline_pit_suppressed,
        }
    return record


def _objective_record(comparison, objective) -> dict:
    result = evaluate_objective(
        comparison, objective,
        bootstrap_replicates=P.BOOTSTRAP_REPLICATES,
        confidence_level=P.CONFIDENCE_LEVEL,
        bootstrap_seed_root=P.BOOTSTRAP_SEED_ROOT)
    pairwise_counts = {}
    for pairwise in result.pairwise_comparisons:
        pairwise_counts[pairwise.classification] = \
            pairwise_counts.get(pairwise.classification, 0) + 1
    evaluations = []
    for evaluation in result.candidate_evaluations:
        uncertainty = evaluation.uncertainty
        evaluations.append({
            "candidate_key": evaluation.candidate_key,
            "point_estimate": evaluation.point_estimate,
            "classification": evaluation.classification,
            "paired_se": uncertainty.paired_se,
            "unpaired_se": uncertainty.unpaired_se,
            "se_ratio": uncertainty.se_ratio,
            "ci_low": uncertainty.ci_low,
            "ci_high": uncertainty.ci_high,
            "ci_width": (None if uncertainty.ci_low is None
                         else uncertainty.ci_high - uncertainty.ci_low),
            "valid_pairs": uncertainty.valid_pairs,
            "availability": uncertainty.availability,
        })
    return {
        "objective": result.objective,
        "metric": result.metric,
        "objective_identity": result.identity(),
        "baseline_relative_counts": dict(result.baseline_relative_counts),
        "point_estimate_order": list(result.point_estimate_order),
        "leader_by_point_estimate": result.leader_by_point_estimate,
        "indistinguishable_from_leader":
            list(result.indistinguishable_from_leader),
        "distinguishable_from_leader":
            list(result.distinguishable_from_leader),
        "pairwise_status_counts": pairwise_counts,
        "pairwise_comparison_count": len(result.pairwise_comparisons),
        "candidate_evaluations": evaluations,
    }


def _run_job(record, band, *, count, seed, specs):
    state = P.load_state(record)
    params = P.load_parameters(record["season"])
    targets = P.select_targets(state)
    target = targets[band]
    config = P.make_config(count, seed)
    state_identity_before = state.identity()
    config_identity_before = config.identity()
    parameter_identity_before = params.parameter_identity().identity()
    started = time.perf_counter()
    comparison = compare_strategies(
        state, params, config, Assumptions(), target,
        candidate_specs=[(action, compound) for action, compound in specs])
    comparison_s = time.perf_counter() - started

    objective_started = time.perf_counter()
    tracemalloc.start()
    objectives = {}
    if comparison.supported:
        for objective in STRATEGY_OBJECTIVES:
            objectives[objective] = _objective_record(comparison, objective)
    _, analysis_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    analysis_s = time.perf_counter() - objective_started

    result = {
        "stage": record["stage"],
        "season": record["season"],
        "race_id": record["race_id"],
        "scheduled_laps": record["scheduled_laps"],
        "leader_lap": record["leader_lap"],
        "band": band,
        "target_driver_id": target,
        "target_lap": state.driver_by_id[target].lap_number,
        "target_position": state.driver_by_id[target].position,
        "target_compound": state.driver_by_id[target].compound,
        "target_tyre_age": state.driver_by_id[target].tyre_age,
        "count": count,
        "seed": seed,
        "candidate_specs": [list(spec) for spec in specs],
        "supported": comparison.supported,
        "unsupported_reason": comparison.unsupported_reason,
        "comparison_identity": (comparison.identity()
                                if comparison.supported else None),
        "state_identity": state_identity_before,
        "flag_state_unchanged": state.identity() == state_identity_before,
        "flag_config_unchanged": config.identity() == config_identity_before,
        "flag_parameters_unchanged": (
            params.parameter_identity().identity()
            == parameter_identity_before),
        "comparison_s": comparison_s,
        "analysis_s": analysis_s,
        "analysis_traced_peak_bytes": analysis_peak,
        "baseline": (comparison.baseline.to_dict()
                     if comparison.baseline is not None else None),
        "candidates": [_candidate_record(candidate)
                       for candidate in comparison.candidates],
        "objectives": objectives,
    }
    return result


def _aggregate_jobs(jobs) -> dict:
    """Descriptive characterization over supported jobs (no ranking)."""
    activation = {"applied": [], "suppressed": [], "superseded": [],
                  "inert": [], "race_end_cancelled": []}
    deltas = {"win": [], "podium": [], "finish": []}
    se_ratios = []
    ci_widths = {"win": [], "podium": [], "finish": []}
    classification_counts = {objective: {} for objective in STRATEGY_OBJECTIVES}
    leader_ambiguous = 0
    leader_total = 0
    definitive_leaders = 0
    validity_mismatch = 0
    valid_pairs_total = 0
    candidates_total = 0
    unsupported = 0
    immutable = True

    for job in jobs:
        if not job["supported"]:
            unsupported += 1
            continue
        immutable = immutable and job["flag_state_unchanged"] \
            and job["flag_config_unchanged"] and job["flag_parameters_unchanged"]
        for candidate in job["candidates"]:
            if not candidate["evaluated"]:
                continue
            candidates_total += 1
            valid_pairs_total += candidate["valid_pairs"]
            if not candidate["validity_sets_match"]:
                validity_mismatch += 1
            execution = candidate.get("execution") or {}
            for key in activation:
                rate = execution.get(f"{key}_rate")
                if rate is not None:
                    activation[key].append(rate)
            deltas["win"].append(candidate["delta_win_probability"])
            deltas["podium"].append(candidate["delta_podium_probability"])
            deltas["finish"].append(candidate["delta_expected_finish"])
        for objective, record in job["objectives"].items():
            counts = classification_counts[objective]
            for classification, value in record["baseline_relative_counts"].items():
                counts[classification] = counts.get(classification, 0) + value
            if record["leader_by_point_estimate"] is not None:
                leader_total += 1
                if record["indistinguishable_from_leader"]:
                    leader_ambiguous += 1
                else:
                    definitive_leaders += 1
            for evaluation in record["candidate_evaluations"]:
                if evaluation["se_ratio"] is not None:
                    se_ratios.append(evaluation["se_ratio"])
                if evaluation["ci_width"] is not None:
                    bucket = {
                        "WIN_PROBABILITY": "win",
                        "PODIUM_PROBABILITY": "podium",
                        "EXPECTED_FINISH": "finish",
                    }[record["metric"]]
                    ci_widths[bucket].append(evaluation["ci_width"])

    def summary(values):
        if not values:
            return {"count": 0, "mean": None, "median": None,
                    "min": None, "max": None}
        return {
            "count": len(values),
            "mean": statistics.fmean(values),
            "median": statistics.median(values),
            "min": min(values),
            "max": max(values),
        }

    crn_worse = sum(1 for ratio in se_ratios if ratio > 1.0)
    crn_better = sum(1 for ratio in se_ratios if ratio < 1.0)
    return {
        "supported_jobs": len(jobs) - unsupported,
        "unsupported_jobs": unsupported,
        "evaluated_candidates": candidates_total,
        "valid_pairs_total": valid_pairs_total,
        "validity_set_mismatches": validity_mismatch,
        "all_lower_layers_immutable": immutable,
        "execution_rate_summary": {key: summary(values)
                                    for key, values in activation.items()},
        "delta_summary": {key: summary(values)
                          for key, values in deltas.items()},
        "se_ratio_summary": summary(se_ratios),
        "se_ratio_below_one": crn_better,
        "se_ratio_above_one": crn_worse,
        "se_ratio_defined": len(se_ratios),
        "ci_width_summary": {key: summary(values)
                             for key, values in ci_widths.items()},
        "classification_counts": classification_counts,
        "leader_total": leader_total,
        "leader_ambiguous": leader_ambiguous,
        "leader_definitive": definitive_leaders,
        "leader_ambiguity_fraction": (
            leader_ambiguous / leader_total if leader_total else None),
    }


def _per_stage(jobs) -> dict:
    by_stage = {}
    for stage in P.STAGES:
        by_stage[stage] = _aggregate_jobs(
            [job for job in jobs if job["stage"] == stage])
    return by_stage


# ---------------------------------------------------------------------------
# Unsupported-state audit (adversarial fixtures, clearly labelled).
# ---------------------------------------------------------------------------

def _base_driver(driver_id, *, lap=5, race_time=400.0, position=1,
                 compound="MEDIUM", age=5, status=DriverStatus.ACTIVE,
                 observation_age=None):
    return DriverSimState(
        driver_id=driver_id, lap_number=lap, race_time_s=race_time,
        position=position, compound=compound, tyre_age=age, stint_number=1,
        pit_count=0, constructor_id="c1", status=status,
        observation_age_s=observation_age)


def _synthetic_state(*, track_state="all_clear", scheduled=20,
                     drivers=None, season=2022, race_id="SYN-S6",
                     weather=None):
    if drivers is None:
        drivers = tuple(
            _base_driver(f"d{i}", lap=5, race_time=400.0 + i, position=i + 1)
            for i in range(6))
    return SimulationState(
        race_id=race_id, scheduled_laps=scheduled, leader_laps_done=5,
        simulation_time_s=400.0, drivers=tuple(drivers),
        environment=SimulationEnvironment(track_state=track_state,
                                          weather=weather),
        season=season, round_no=1, circuit_id="syn")


def _unsupported_audit() -> dict:
    """Exercise genuine unsupported states as labelled adversarial fixtures."""
    params = P.load_parameters(2022)
    cases = []

    def attempt(label, state):
        try:
            comparison = compare_strategies(
                state, params, P.make_config(64, P.BROAD_SEED),
                Assumptions(), "d0", candidate_specs=P.DEEP_SPECS)
            cases.append({
                "label": label,
                "supported": comparison.supported,
                "unsupported_reason": comparison.unsupported_reason,
                "candidates_evaluated": [c.evaluated
                                         for c in comparison.candidates],
                "returned_partial_table": any(
                    c.evaluated for c in comparison.candidates)
                if not comparison.supported else None,
            })
        except Exception as exc:  # noqa: BLE001 - record the actual behaviour
            cases.append({"label": label, "raised": type(exc).__name__,
                          "detail": str(exc)[:200]})

    from v2.race_state import WeatherState

    attempt("wet_track_conditions", _synthetic_state(
        weather=WeatherState(rainfall=True)))
    attempt("neutralized_track_state",
            _synthetic_state(track_state="safety_car"))
    attempt("red_flag_track_state", _synthetic_state(track_state="red_flag"))
    attempt("unknown_track_state", _synthetic_state(track_state=None))

    wet_tyres = tuple(
        _base_driver(f"d{i}", lap=5, race_time=400.0 + i, position=i + 1,
                     compound="WET", age=5)
        for i in range(6))
    attempt("wet_compound_state",
            _synthetic_state(drivers=wet_tyres))

    missing_tyre = tuple(
        _base_driver(f"d{i}", lap=5, race_time=400.0 + i, position=i + 1,
                     age=None)
        for i in range(6))
    attempt("missing_tyre_state",
            _synthetic_state(drivers=missing_tyre))

    stale = tuple(
        _base_driver(f"d{i}", lap=5, race_time=400.0 + i, position=i + 1,
                     observation_age=100000.0)
        for i in range(6))
    attempt("non_contemporaneous_roster_member",
            _synthetic_state(drivers=stale))

    # Target outside roster must be a structured comparison-level refusal.
    try:
        comparison = compare_strategies(
            _synthetic_state(), params, P.make_config(64, P.BROAD_SEED),
            Assumptions(), "ghost_driver", candidate_specs=P.DEEP_SPECS)
        cases.append({
            "label": "target_driver_not_in_roster",
            "supported": comparison.supported,
            "unsupported_reason": comparison.unsupported_reason,
            "returned_partial_table": any(
                c.evaluated for c in comparison.candidates),
        })
    except Exception as exc:  # noqa: BLE001
        cases.append({"label": "target_driver_not_in_roster",
                      "raised": type(exc).__name__, "detail": str(exc)[:200]})

    def _structured(case):
        if "raised" in case:
            return False
        return (case.get("supported") is False
                and case.get("returned_partial_table") is False)

    return {
        "fixture_label": "ADVERSARIAL_FIXTURES (not part of representative "
                         "metrics)",
        "cases": cases,
        "all_structured": all(_structured(case) for case in cases),
    }


# ---------------------------------------------------------------------------
# Temporal firewall audit (parameter leak + future-input channel).
# ---------------------------------------------------------------------------

def _temporal_audit(record) -> dict:
    import copy
    from v2.simulation.engine import (
        ExecutionPolicy,
        SimulationUnsupportedError,
    )
    from v2.simulation.params import load_simulation_parameters
    state = P.load_state(record)
    target = P.select_targets(state)["FRONT"]
    param_root = (ROOT / "data" / "v2" / "simulation" / "params")
    result = {"through_current_season_rejected": None,
              "through_previous_season_accepted": None,
              "future_poison_output_invariant": None}
    # Parameters fit INCLUDING the target season are a temporal leak and must
    # be refused whole-state under the leakage-enforced policy.
    leak_path = param_root / f"r3-v1__through-{record['season']}"
    if leak_path.exists():
        leak_params = load_simulation_parameters(leak_path)
        try:
            leak_comparison = compare_strategies(
                state, leak_params, P.make_config(64, P.BROAD_SEED),
                Assumptions(), target, candidate_specs=P.DEEP_SPECS,
                execution_policy=ExecutionPolicy.HISTORICAL_BACKTEST)
            result["through_current_season_rejected"] = (
                not leak_comparison.supported)
            result["through_current_season_reason"] = (
                leak_comparison.unsupported_reason)
        except SimulationUnsupportedError as exc:
            result["through_current_season_rejected"] = True
            result["through_current_season_reason"] = exc.reason
    ok_params = P.load_parameters(record["season"])
    comparison = compare_strategies(
        state, ok_params, P.make_config(64, P.BROAD_SEED), Assumptions(),
        target, candidate_specs=P.DEEP_SPECS)
    result["through_previous_season_accepted"] = comparison.supported

    # Future-information poisoning: the factual state at T is an immutable
    # snapshot; mutate every field a "future" leak could attach to (the
    # state's own race identity, environment, driver positions) is NOT
    # future data. Instead confirm the strategy result is a pure function of
    # the supplied state by re-running from an independent reconstruction of
    # the same factual state and requiring an identical comparison identity.
    state_copy = copy.deepcopy(state)
    comparison_copy = compare_strategies(
        state_copy, ok_params, P.make_config(64, P.BROAD_SEED), Assumptions(),
        target, candidate_specs=P.DEEP_SPECS)
    result["future_poison_output_invariant"] = (
        comparison.identity() == comparison_copy.identity())
    return result


def _future_input_channel_audit() -> dict:
    """No Strategy entry point accepts a future/history/oracle argument."""
    import inspect
    from v2.strategy import comparison, candidates, uncertainty, objectives
    banned = ("future", "oracle", "history", "historical", "actual",
              "truth", "replay")
    surfaces = {
        "compare_strategies": comparison.compare_strategies,
        "generate_candidates": candidates.generate_candidates,
        "build_candidate": candidates.build_candidate,
        "compute_uncertainty": uncertainty.compute_uncertainty,
        "evaluate_objective": objectives.evaluate_objective,
    }
    offending = {}
    for name, function in surfaces.items():
        parameters = list(inspect.signature(function).parameters)
        hits = [parameter for parameter in parameters
                if any(token in parameter.lower() for token in banned)]
        if hits:
            offending[name] = hits
    return {"entry_points_checked": list(surfaces),
            "future_accepting_parameters": offending,
            "clean": not offending}


# ---------------------------------------------------------------------------
# Performance / memory audit for the S7 product path.
# ---------------------------------------------------------------------------

def _performance_audit() -> list:
    rows = []
    deep = P.select_deep_corpus()
    for record in deep:
        state = P.load_state(record)
        params = P.load_parameters(record["season"])
        target = P.select_targets(state)["FRONT"]
        for label, count, specs in (
                ("1k/9candidates", P.BROAD_SIMULATION_COUNT, P.CANONICAL_SPECS),
                ("10k/3candidates", P.DEEP_SIMULATION_COUNT, P.DEEP_SPECS)):
            tracemalloc.start()
            started = time.perf_counter()
            comparison = compare_strategies(
                state, params, P.make_config(count, P.DEEP_SEED),
                Assumptions(), target,
                candidate_specs=[(a, c) for a, c in specs])
            comparison_s = time.perf_counter() - started
            current, peak = tracemalloc.get_traced_memory()
            tracemalloc.stop()
            analysis_started = time.perf_counter()
            for objective in STRATEGY_OBJECTIVES:
                evaluate_objective(
                    comparison, objective,
                    bootstrap_replicates=P.BOOTSTRAP_REPLICATES,
                    confidence_level=P.CONFIDENCE_LEVEL,
                    bootstrap_seed_root=P.BOOTSTRAP_SEED_ROOT)
            analysis_s = time.perf_counter() - analysis_started
            rows.append({
                "stage": record["stage"],
                "season": record["season"],
                "race_id": record["race_id"],
                "label": label,
                "count": count,
                "candidate_count": sum(1 for c in comparison.candidates
                                       if c.evaluated),
                "supported": comparison.supported,
                "comparison_s": comparison_s,
                "analysis_s": analysis_s,
                "total_s": comparison_s + analysis_s,
                "traced_peak_bytes": peak,
                "traced_current_bytes": current,
            })
    return rows


def _s7_guidance(performance) -> dict:
    onek = [row for row in performance if row["label"].startswith("1k")]
    tenk = [row for row in performance if row["label"].startswith("10k")]
    full = [row for row in onek if row["candidate_count"] >= 9]
    max_full_1k = max((row["total_s"] for row in full), default=None)
    # A synchronous default is only comfortable when the full candidate space
    # at 1k stays within this predeclared engineering budget.
    synchronous_budget_s = 10.0
    full_ok = max_full_1k is not None and max_full_1k <= synchronous_budget_s
    tenk_range = ([min(row["total_s"] for row in tenk),
                   max(row["total_s"] for row in tenk)] if tenk else None)
    if full_ok:
        recommendation = (
            "expose the full 9-candidate space at 1k synchronously; treat 10k "
            "as explicit advanced/manual (the 9-candidate 10k path was not run "
            "and is out of the synchronous band)")
    else:
        recommendation = (
            "the full 9-candidate space at 1k exceeded the "
            f"{synchronous_budget_s:.0f}s synchronous budget on at least one "
            "stage; for the synchronous S7 default use a reduced candidate "
            "subset (<=4) at 1k, treat the full 9-candidate space as an "
            "advanced/async request, and treat 10k as explicit/manual")
    return {
        "default_simulation_count": P.BROAD_SIMULATION_COUNT,
        "synchronous_budget_s": synchronous_budget_s,
        "default_full_candidate_space_acceptable_synchronously": full_ok,
        "max_full_candidate_1k_total_s": max_full_1k,
        "min_full_candidate_1k_total_s": (
            min(row["total_s"] for row in full) if full else None),
        "deep_10k_3candidate_total_s_range": tenk_range,
        "recommendation": recommendation,
        "note": "engineering latency guidance only; not a scientific ranking",
    }


def main() -> dict:
    started = time.perf_counter()
    jobs = []
    for record, band in P.select_broad_jobs():
        jobs.append(_run_job(record, band,
                             count=P.BROAD_SIMULATION_COUNT,
                             seed=P.BROAD_SEED, specs=P.CANONICAL_SPECS))

    # Deep validation: same state/target at 1k and 10k on a 3-candidate subset
    # so interval widths are directly comparable.
    deep_rows = []
    for record in P.select_deep_corpus():
        for count in (P.BROAD_SIMULATION_COUNT, P.DEEP_SIMULATION_COUNT):
            deep_rows.append(_run_job(record, "FRONT", count=count,
                                      seed=P.DEEP_SEED, specs=P.DEEP_SPECS))

    deep_reference = P.select_corpus()[0]
    unsupported = _unsupported_audit()
    temporal = _temporal_audit(deep_reference)
    performance = _performance_audit()

    payload = {
        "generated_by": "scripts/run_phase7_s6_validation.py",
        "protocol": P.PROTOCOL_RECORD,
        "environment": _environment(),
        "corpus": [dict(record) for record in P.select_corpus()],
        "deep_corpus": [dict(record) for record in P.select_deep_corpus()],
        "corpus_eligibility_audit": P.eligibility_audit(),
        "broad_jobs": jobs,
        "deep_runs": deep_rows,
        "characterization": _aggregate_jobs(jobs),
        "characterization_by_stage": _per_stage(jobs),
        "unsupported_state_audit": unsupported,
        "temporal_firewall_audit": temporal,
        "future_input_channel_audit": _future_input_channel_audit(),
        "performance": performance,
        "s7_guidance": _s7_guidance(performance),
        "no_counterfactual_accuracy_claim": True,
        "wall_time_s": time.perf_counter() - started,
        "limitations": [
            "Simulator-conditional Monte Carlo frequencies; alternative "
            "strategy outcomes are counterfactual, not observable truth.",
            "No counterfactual or recommendation accuracy is computed: no "
            "historical ground truth exists for an alternative strategy.",
            "No traffic/overtaking model and no per-compound pace delta.",
            "CRN shares stream identities, not trajectories; pairing is not a "
            "universal variance reduction.",
            "The broad corpus is deterministic but finite; estimates are "
            "sampling-limited.",
        ],
    }
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True)
                             + "\n")
    return payload


if __name__ == "__main__":
    result = main()
    print(json.dumps({
        "artifact": str(ARTIFACT_PATH),
        "wall_time_s": result["wall_time_s"],
        "characterization": result["characterization"],
        "unsupported_state_audit": result["unsupported_state_audit"],
        "temporal_firewall_audit": result["temporal_firewall_audit"],
        "future_input_channel_audit": result["future_input_channel_audit"],
        "performance": result["performance"],
        "s7_guidance": result["s7_guidance"],
    }, indent=2, sort_keys=True))
