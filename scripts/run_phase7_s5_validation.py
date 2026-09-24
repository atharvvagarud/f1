"""Phase-7 S5 validation: sampling uncertainty + explicit objective policy.

Runs the S5 analysis layer over REAL S4 comparisons and records only measured
values (no fabricated numbers):

- EARLY / MID / LATE accepted R7.1 anchors at 1 000 trajectories, all canonical
  valid candidates, for all three objectives (baseline-relative classifications,
  point-estimate leader, indistinguishable-from-leader set, pairwise status
  counts, SE / CI examples, execution / inert / supersession context);
- a MID 1 000 vs 10 000 stability check on a fixed 3-candidate subset;
- paired-SE / unpaired-SE diagnostics across representative candidate metrics;
- S5 analysis wall time (uncertainty + all three objectives) after the S4
  comparison already exists, for 1 candidate/1k, 9 candidates/1k, 3/10k, and
  the tracemalloc peak of the statistical layer.

The S5 statistical layer NEVER reruns a simulation: every number is derived from
the per-index terminal outcomes the S4 comparison already retains.

Artifact: ``data/v2/strategy/s5_uncertainty_validation_v1.json``. ``/data/v2/``
is git-ignored by repository policy (generated scientific data is not tracked);
the artifact is reproducible from this script.

Usage (from the repository root)::

    /opt/homebrew/bin/python3.11 scripts/run_phase7_s5_validation.py
"""

from __future__ import annotations

import json
import sys
import time
import tracemalloc
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (str(ROOT), str(ROOT / "tests")):
    if extra not in sys.path:
        sys.path.insert(0, extra)

from v2.simulation.config import Assumptions, SimulationConfig  # noqa: E402
from v2.strategy import (  # noqa: E402
    OBJECTIVE_METRIC,
    STRATEGY_OBJECTIVES,
    UNCERTAINTY_VERSION,
    OBJECTIVE_VERSION,
    compare_strategies,
    evaluate_objective,
)
from v2.strategy.candidates import (  # noqa: E402
    CANDIDATE_CONTRACT_VERSION,
    CANONICAL_CANDIDATE_SPECS,
)
from v2.strategy.comparison import COMPARISON_VERSION  # noqa: E402
from v2.strategy.uncertainty import (  # noqa: E402
    DEFAULT_BOOTSTRAP_REPLICATES,
    DEFAULT_BOOTSTRAP_SEED,
    DEFAULT_CONFIDENCE_LEVEL,
    MIN_VALID_PAIRS_FOR_CI,
    QUANTILE_METHOD,
)

ARTIFACT_PATH = (ROOT / "data" / "v2" / "strategy"
                 / "s5_uncertainty_validation_v1.json")

PROTOCOL_VERSION = "s5-uncertainty-objective-protocol-v1"
SEED = 20240101
COUNT = 1000
STABILITY_HIGH_COUNT = 10000
STABILITY_SPECS = (("STAY_OUT", None), ("PIT_NOW", None),
                   ("PIT_NEXT_LAP", None))
ONE_SPEC = (("PIT_NOW", None),)

STATE_SPECS = (
    {"stage": "EARLY", "season": 2023, "race_id": "2023-r01-R",
     "driver": "alonso", "lap": 2},
    {"stage": "MID", "season": 2022, "race_id": "2022-r01-R",
     "driver": "perez", "lap": 30},
    {"stage": "LATE", "season": 2022, "race_id": "2022-r01-R",
     "driver": "russell", "lap": 38},
)


def _state_and_params(spec):
    from test_v2_phase6_r71 import _params_through, _real_state
    state = _real_state(spec["season"], spec["race_id"], spec["driver"],
                        spec["lap"])
    params = _params_through(spec["season"] - 1)
    return state, params


def _config(count: int) -> SimulationConfig:
    return SimulationConfig(simulation_count=count, master_seed=SEED,
                            sample_orders=0, pit_dynamics_enabled=True)


def _comparison(state, params, target, count, specs):
    started = time.perf_counter()
    comparison = compare_strategies(
        state, params, _config(count), Assumptions(), target,
        candidate_specs=[(action, compound) for action, compound in specs])
    return comparison, time.perf_counter() - started


def _evaluation_record(evaluation) -> dict:
    uncertainty = evaluation.uncertainty
    record = {
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
        "availability": uncertainty.availability,
        "valid_pairs": uncertainty.valid_pairs,
    }
    if evaluation.execution is not None:
        record["execution"] = {
            "applied_rate": evaluation.execution.applied_rate,
            "suppressed_rate": evaluation.execution.suppressed_rate,
            "superseded_rate": evaluation.execution.superseded_rate,
            "inert_rate": evaluation.execution.inert_rate,
            "race_end_cancelled_rate":
                evaluation.execution.race_end_cancelled_rate,
        }
    return record


def _objective_record(result) -> dict:
    pairwise_counts = {}
    for comparison in result.pairwise_comparisons:
        pairwise_counts[comparison.classification] = \
            pairwise_counts.get(comparison.classification, 0) + 1
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
        "candidate_evaluations": [
            _evaluation_record(evaluation)
            for evaluation in result.candidate_evaluations],
    }


def _check_point_estimate_reproduces_s4(comparison) -> bool:
    for objective in STRATEGY_OBJECTIVES:
        metric = OBJECTIVE_METRIC[objective]
        result = evaluate_objective(comparison, objective)
        by_key = {candidate.candidate.key: candidate
                  for candidate in comparison.candidates}
        for evaluation in result.candidate_evaluations:
            candidate = by_key[evaluation.candidate_key]
            if candidate.valid_pairs == 0:
                continue
            s4_value = {
                "WIN_PROBABILITY": candidate.delta_win_probability,
                "PODIUM_PROBABILITY": candidate.delta_podium_probability,
                "EXPECTED_FINISH": candidate.delta_expected_finish}[metric]
            if evaluation.point_estimate != s4_value:
                return False
    return True


def _analyse(comparison):
    """S5 analysis only (no simulation), with timing and peak memory."""
    started = time.perf_counter()
    tracemalloc.start()
    records = [_objective_record(evaluate_objective(comparison, objective))
               for objective in STRATEGY_OBJECTIVES]
    _, traced_peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    return records, time.perf_counter() - started, traced_peak


def _stability_record(state, params, target):
    runs = {}
    for count in (COUNT, STABILITY_HIGH_COUNT):
        comparison, comparison_s = _comparison(
            state, params, target, count, STABILITY_SPECS)
        objectives, analysis_s, _ = _analyse(comparison)
        runs[count] = {
            "comparison_s": comparison_s,
            "analysis_s": analysis_s,
            "comparison_identity": comparison.identity(),
            "objectives": {record["objective"]: record
                           for record in objectives},
        }

    stability = []
    for objective in STRATEGY_OBJECTIVES:
        low = {evaluation["candidate_key"]: evaluation
               for evaluation in runs[COUNT]["objectives"][objective][
                   "candidate_evaluations"]}
        high = {evaluation["candidate_key"]: evaluation
                for evaluation in runs[STABILITY_HIGH_COUNT]["objectives"][
                    objective]["candidate_evaluations"]}
        for key in sorted(low):
            stability.append({
                "objective": objective,
                "candidate_key": key,
                "point_estimate_1k": low[key]["point_estimate"],
                "point_estimate_10k": high[key]["point_estimate"],
                "paired_se_1k": low[key]["paired_se"],
                "paired_se_10k": high[key]["paired_se"],
                "ci_width_1k": low[key]["ci_width"],
                "ci_width_10k": high[key]["ci_width"],
                "classification_1k": low[key]["classification"],
                "classification_10k": high[key]["classification"],
                "valid_pairs_1k": low[key]["valid_pairs"],
                "valid_pairs_10k": high[key]["valid_pairs"],
            })
    return {
        "state": MID,
        "seed": SEED,
        "candidate_specs": [list(spec) for spec in STABILITY_SPECS],
        "counts": [COUNT, STABILITY_HIGH_COUNT],
        "runs": {str(count): {"comparison_s": runs[count]["comparison_s"],
                              "analysis_s": runs[count]["analysis_s"],
                              "comparison_identity":
                                  runs[count]["comparison_identity"]}
                 for count in runs},
        "candidate_stability": stability,
    }


MID = {"season": 2022, "race_id": "2022-r01-R", "driver": "perez", "lap": 30}


def run_experiment() -> dict:
    states = []
    for spec in STATE_SPECS:
        state, params = _state_and_params(spec)
        target = spec["driver"]
        comparison, comparison_s = _comparison(
            state, params, target, COUNT,
            tuple((action.value, compound)
                  for action, compound in CANONICAL_CANDIDATE_SPECS))
        objectives, analysis_s, traced_peak = _analyse(comparison)
        valid_candidates = [candidate.candidate.key
                            for candidate in comparison.candidates
                            if candidate.evaluated]
        states.append({
            "stage": spec["stage"],
            "season": spec["season"],
            "race_id": spec["race_id"],
            "target_driver_id": target,
            "target_lap": spec["lap"],
            "count": COUNT,
            "supported": comparison.supported,
            "unsupported_reason": comparison.unsupported_reason,
            "comparison_identity": comparison.identity(),
            "comparison_s": comparison_s,
            "analysis_s": analysis_s,
            "analysis_traced_peak_bytes": traced_peak,
            "valid_candidates": valid_candidates,
            "point_estimate_reproduces_s4": (
                _check_point_estimate_reproduces_s4(comparison)
                if comparison.supported else None),
            "objectives": {record["objective"]: record
                           for record in objectives},
        })
    return states


def _paired_vs_unpaired(states):
    rows = []
    for state in states:
        for objective, record in state["objectives"].items():
            for evaluation in record["candidate_evaluations"]:
                rows.append({
                    "stage": state["stage"],
                    "objective": objective,
                    "candidate_key": evaluation["candidate_key"],
                    "paired_se": evaluation["paired_se"],
                    "unpaired_se": evaluation["unpaired_se"],
                    "se_ratio": evaluation["se_ratio"],
                })
    return rows


def _performance(state, params, target, count, specs, label):
    comparison, comparison_s = _comparison(state, params, target, count,
                                           specs)
    _, analysis_s, traced_peak = _analyse(comparison)
    return {
        "label": label,
        "count": count,
        "candidate_count": len([c for c in comparison.candidates
                                if c.evaluated]),
        "comparison_s": comparison_s,
        "s5_analysis_s": analysis_s,
        "s5_analysis_traced_peak_bytes": traced_peak,
        "analysis_to_comparison_ratio": (analysis_s / comparison_s
                                         if comparison_s else None),
    }


def main() -> dict:
    started = time.perf_counter()
    mid_state, mid_params = _state_and_params(MID)
    mid_target = MID["driver"]

    states = run_experiment()

    performance = [
        _performance(mid_state, mid_params, mid_target, COUNT, ONE_SPEC,
                     "1 candidate / 1k"),
        {"label": "9 candidates / 1k",
         "count": COUNT,
         "candidate_count": len(states[1]["valid_candidates"]),
         "comparison_s": states[1]["comparison_s"],
         "s5_analysis_s": states[1]["analysis_s"],
         "s5_analysis_traced_peak_bytes":
             states[1]["analysis_traced_peak_bytes"],
         "analysis_to_comparison_ratio": (
             states[1]["analysis_s"] / states[1]["comparison_s"]
             if states[1]["comparison_s"] else None)},
    ]

    stability = _stability_record(mid_state, mid_params, mid_target)
    performance.append({
        "label": "3 candidates / 10k",
        "count": STABILITY_HIGH_COUNT,
        "candidate_count": 3,
        "comparison_s": stability["runs"][str(STABILITY_HIGH_COUNT)][
            "comparison_s"],
        "s5_analysis_s": stability["runs"][str(STABILITY_HIGH_COUNT)][
            "analysis_s"],
        "s5_analysis_traced_peak_bytes": None,
        "analysis_to_comparison_ratio": (
            stability["runs"][str(STABILITY_HIGH_COUNT)]["analysis_s"]
            / stability["runs"][str(STABILITY_HIGH_COUNT)]["comparison_s"]),
    })

    return {
        "generated_by": "scripts/run_phase7_s5_validation.py",
        "protocol_version": PROTOCOL_VERSION,
        "uncertainty_version": UNCERTAINTY_VERSION,
        "objective_version": OBJECTIVE_VERSION,
        "comparison_version": COMPARISON_VERSION,
        "candidate_contract_version": CANDIDATE_CONTRACT_VERSION,
        "bootstrap_config": {
            "replicates": DEFAULT_BOOTSTRAP_REPLICATES,
            "confidence_level": DEFAULT_CONFIDENCE_LEVEL,
            "bootstrap_seed_root": DEFAULT_BOOTSTRAP_SEED,
            "quantile_method": QUANTILE_METHOD,
            "ci_method": "paired_percentile_bootstrap",
            "small_n_policy_min_valid_pairs": MIN_VALID_PAIRS_FOR_CI,
        },
        "seed": SEED,
        "count": COUNT,
        "states": states,
        "paired_vs_unpaired": _paired_vs_unpaired(states),
        "stability": stability,
        "performance": performance,
        "wall_time_s": time.perf_counter() - started,
        "limitations": [
            "Uncertainty is MONTE_CARLO_SAMPLING_UNCERTAINTY_ONLY: it is not "
            "parameter, model-form, pit-loss, pace, traffic, compound-effect, "
            "weather or real-world counterfactual uncertainty.",
            "The interval is a Monte Carlo resampling interval for the paired "
            "simulation delta, not a confidence interval for the true "
            "real-world causal effect of a pit strategy.",
            "Pairwise intervals are exploratory Monte Carlo diagnostics and are "
            "not a family-wise inferential procedure; no p-value or "
            "multiple-comparison correction is applied.",
            "leader_by_point_estimate names only the highest simulator point "
            "estimate; it is not a recommendation.",
            "S5 reruns no simulation; all values derive from the per-index "
            "outcomes the S4 comparison already produced.",
            "The artifact is generated (not tracked) under /data/v2/ per "
            "repository policy.",
        ],
    }


if __name__ == "__main__":
    payload = main()
    ARTIFACT_PATH.parent.mkdir(parents=True, exist_ok=True)
    ARTIFACT_PATH.write_text(json.dumps(payload, indent=2, sort_keys=True)
                             + "\n")
    print(json.dumps({
        "artifact": str(ARTIFACT_PATH),
        "wall_time_s": payload["wall_time_s"],
        "performance": payload["performance"],
        "stability_runs": payload["stability"]["runs"],
    }, indent=2, sort_keys=True))
