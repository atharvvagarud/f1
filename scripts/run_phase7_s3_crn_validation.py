"""Phase-7 S3 CRN validation experiment (paired vs independent).

Predeclared protocol. This script MEASURES whether common random numbers
(paired streams) reduce the variance of the estimated strategy difference
relative to independent streams. It does not assume they do.

Protocol (fixed before running; do not tune on results):

- States: three accepted R7.1 historical anchors (EARLY / MID / LATE).
- Actions: STAY_OUT, PIT_NOW, PIT_NEXT_LAP, with both a baseline-drawn (null)
  compound and an explicit dry compound.
- Count: 1000 trajectories per run.
- Master seeds: the predeclared list ``MASTER_SEEDS``.
- Independent arm: baseline seed S, intervention seed ``S2 = derive(S)``.

For each (state, action, compound, metric) the estimator across seeds is:

- PAIRED: the mean of the raw paired differences over complete valid pairs;
- INDEPENDENT: the difference of the two arm aggregates (target win/podium
  probability; baseline minus intervention expected finish, so positive =
  improvement).

The variance ratio is VR = Var(paired estimator) / Var(independent estimator)
over the seed set. VR < 1 means pairing reduced estimator variance.

Artifact: ``data/v2/strategy/s3_crn_validation_v1.json``. ``/data/v2/`` is
git-ignored by repository policy (generated scientific data is not tracked);
the artifact is reproducible from this script.

Usage (from the repository root)::

    /opt/homebrew/bin/python3.11 scripts/run_phase7_s3_crn_validation.py
"""

from __future__ import annotations

import json
import statistics
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
for extra in (str(ROOT), str(ROOT / "tests")):
    if extra not in sys.path:
        sys.path.insert(0, extra)

from v2.simulation.config import Assumptions, SimulationConfig  # noqa: E402
from v2.simulation.monte_carlo import MonteCarloEngine  # noqa: E402
from v2.strategy import (  # noqa: E402
    StrategyAction,
    StrategyIntervention,
    paired_differences,
    run_pair,
)

ARTIFACT_PATH = ROOT / "data" / "v2" / "strategy" / "s3_crn_validation_v1.json"

PROTOCOL_VERSION = "s3-crn-protocol-v1"
PAIRED_CONTRACT_VERSION = "s3-paired-v1"
SIMULATION_COUNT = 1000

#: Predeclared master seeds (never selected on results).
MASTER_SEEDS = (20240101, 7, 11, 101, 202, 303, 404, 505, 606, 707)

#: Deterministic independent-intervention seed derivation (different stream
#: identity, no shared randomness with the baseline).
def derive_independent_seed(seed: int) -> int:
    return (seed * 6364136223846793005 + 1442695040888963407) & ((1 << 63) - 1)


#: Independent R7.1 accepted anchors (EARLY / MID / LATE).
STATE_SPECS = (
    {"stage": "EARLY", "season": 2023, "race_id": "2023-r01-R",
     "driver": "alonso", "lap": 2},
    {"stage": "MID", "season": 2022, "race_id": "2022-r01-R",
     "driver": "perez", "lap": 30},
    {"stage": "LATE", "season": 2022, "race_id": "2022-r01-R",
     "driver": "russell", "lap": 38},
)

#: Predeclared action/compound grid.
ACTION_SPECS = (
    {"action": "STAY_OUT", "requested_compound": None},
    {"action": "PIT_NOW", "requested_compound": None},
    {"action": "PIT_NOW", "requested_compound": "SOFT"},
    {"action": "PIT_NEXT_LAP", "requested_compound": None},
    {"action": "PIT_NEXT_LAP", "requested_compound": "HARD"},
)

METRICS = ("d_win", "d_podium", "d_finish")

#: Conservative, predeclared acceptance policy (do not edit after running).
DECISION_POLICY = {
    "version": "s3-crn-policy-v1",
    "mechanical_validity_required": [
        "per_index outcomes reproduce the arm aggregates exactly",
        "pre-divergence invariance holds where mechanically expected",
        "no change to draws or to the frozen MonteCarloResult identity",
    ],
    "adopt": "median variance ratio <= 0.95, >= 80% of defined cases < 1, "
             "and no material bias",
    "adopt_with_limitations": "median variance ratio < 1.0 but mixed "
                              "evidence across cases",
    "no_benefit": "median variance ratio in [0.95, 1.05]",
    "unsafe": "median variance ratio >= 1.05 or material bias detected",
}


def _state_and_params(spec):
    from test_v2_phase6_r71 import _params_through, _real_state
    state = _real_state(spec["season"], spec["race_id"], spec["driver"],
                        spec["lap"])
    params = _params_through(spec["season"] - 1)
    return state, params


def _aggregate_difference(baseline_result, intervention_result, target, metric):
    base = baseline_result.driver_summary_by_id[target]
    iv = intervention_result.driver_summary_by_id[target]
    if metric == "d_win":
        return iv.win_probability - base.win_probability
    if metric == "d_podium":
        return iv.podium_probability - base.podium_probability
    # Positive = intervention improved (lower) finishing position.
    return base.expected_finish - iv.expected_finish


def _pearson(xs, ys):
    if len(xs) < 2:
        return None
    mean_x = sum(xs) / len(xs)
    mean_y = sum(ys) / len(ys)
    var_x = sum((x - mean_x) ** 2 for x in xs)
    var_y = sum((y - mean_y) ** 2 for y in ys)
    if var_x == 0.0 or var_y == 0.0:
        return None
    cov = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return cov / (var_x ** 0.5 * var_y ** 0.5)


def _reproduction_ok(result, outcomes, target, roster):
    """Per-index outcomes reproduce the arm aggregate (exact)."""
    valid = [o for o in outcomes if o.valid]
    if not valid:
        return result.valid_simulation_count == 0
    summary = result.driver_summary_by_id[target]
    n = len(valid)
    win = sum(1 for o in valid if o.target_won is True) / n
    podium = sum(1 for o in valid if o.target_podium is True) / n
    finish = sum(o.target_finish_position for o in valid) / n
    return (win == summary.win_probability
            and podium == summary.podium_probability
            and abs(finish - summary.expected_finish) < 1e-12)


def run_experiment() -> dict:
    experiments = []
    for spec in STATE_SPECS:
        state, params = _state_and_params(spec)
        target = spec["driver"]
        for action_spec in ACTION_SPECS:
            action = StrategyAction(action_spec["action"])
            compound = action_spec["requested_compound"]
            record = {
                "stage": spec["stage"],
                "race_id": spec["race_id"],
                "season": spec["season"],
                "target_driver_id": target,
                "target_lap": spec["lap"],
                "action": action.value,
                "requested_compound": compound,
                "count": SIMULATION_COUNT,
                "seeds": [],
                "paired": {metric: [] for metric in METRICS},
                "independent": {metric: [] for metric in METRICS},
                "correlation": {metric: [] for metric in METRICS},
                "valid_pairs": [],
                "diagnostics": [],
                "aggregate_reproduction_ok": True,
                "superseded": 0,
                "inert": 0,
                "applied": 0,
                "race_end_cancelled": 0,
            }
            for seed in MASTER_SEEDS:
                config = SimulationConfig(
                    simulation_count=SIMULATION_COUNT, master_seed=seed,
                    sample_orders=0, pit_dynamics_enabled=True)
                intervention = StrategyIntervention(
                    target_driver_id=target, action=action,
                    requested_compound=compound,
                    decision_lap=state.driver_by_id[target].lap_number,
                    decision_state_identity=state.identity())
                pair = run_pair(state, params, config, Assumptions(),
                                intervention)

                diffs = paired_differences(pair)
                record["seeds"].append(seed)
                record["paired"]["d_win"].append(diffs.mean_d_win)
                record["paired"]["d_podium"].append(diffs.mean_d_podium)
                record["paired"]["d_finish"].append(diffs.mean_d_finish)
                record["valid_pairs"].append(diffs.valid_pairs)
                record["diagnostics"].append(
                    pair.diagnostics.to_dict())
                record["superseded"] += pair.diagnostics.intervention_superseded
                record["inert"] += pair.diagnostics.intervention_inert
                record["applied"] += pair.diagnostics.intervention_applied
                record["race_end_cancelled"] += \
                    pair.diagnostics.race_end_cancelled

                # Independent arm: baseline is the SAME seed-S run (reused);
                # only the intervention is re-run with an independent stream.
                independent_engine = MonteCarloEngine()
                independent_result = independent_engine.run(
                    state, params,
                    SimulationConfig(
                        simulation_count=SIMULATION_COUNT,
                        master_seed=derive_independent_seed(seed),
                        sample_orders=0, pit_dynamics_enabled=True),
                    Assumptions(), intervention=intervention)
                for metric in METRICS:
                    record["independent"][metric].append(
                        _aggregate_difference(pair.baseline_result,
                                              independent_result, target,
                                              metric))

                # Correlation of complete valid pairs (finish position and the
                # binary indicators). Undefined when an arm is constant.
                pairs = [(b, i) for b, i in zip(pair.baseline_outcomes,
                                                pair.intervention_outcomes)
                         if b.valid and i.valid]
                base_finish = [b.target_finish_position for b, _ in pairs]
                iv_finish = [i.target_finish_position for _, i in pairs]
                base_win = [int(b.target_won) for b, _ in pairs]
                iv_win = [int(i.target_won) for _, i in pairs]
                base_podium = [int(b.target_podium) for b, _ in pairs]
                iv_podium = [int(i.target_podium) for _, i in pairs]
                for metric, xs, ys in (
                        ("d_finish", base_finish, iv_finish),
                        ("d_win", base_win, iv_win),
                        ("d_podium", base_podium, iv_podium)):
                    value = _pearson(xs, ys)
                    if value is not None:
                        record["correlation"][metric].append(round(value, 6))

                if not _reproduction_ok(pair.baseline_result,
                                        pair.baseline_outcomes, target,
                                        state.roster_driver_ids):
                    record["aggregate_reproduction_ok"] = False
                if not _reproduction_ok(pair.intervention_result,
                                        pair.intervention_outcomes, target,
                                        state.roster_driver_ids):
                    record["aggregate_reproduction_ok"] = False

            record["variance"] = {}
            record["bias"] = {}
            for metric in METRICS:
                paired_values = record["paired"][metric]
                independent_values = record["independent"][metric]
                paired_var = (statistics.variance(paired_values)
                              if len(paired_values) > 1 else None)
                independent_var = (statistics.variance(independent_values)
                                   if len(independent_values) > 1 else None)
                ratio = None
                if paired_var is not None and independent_var not in (None, 0.0):
                    ratio = paired_var / independent_var
                record["variance"][metric] = {
                    "paired": paired_var,
                    "independent": independent_var,
                    "ratio": ratio,
                }
                paired_mean = statistics.fmean(paired_values)
                independent_mean = statistics.fmean(independent_values)
                record["bias"][metric] = {
                    "paired_mean": paired_mean,
                    "independent_mean": independent_mean,
                    "difference": paired_mean - independent_mean,
                }
            record["correlation_summary"] = {
                metric: {
                    "defined": len(record["correlation"][metric]),
                    "mean": (round(statistics.fmean(record["correlation"][metric]), 6)
                             if record["correlation"][metric] else None),
                }
                for metric in METRICS}
            experiments.append(record)
    return experiments


def summarise(experiments) -> dict:
    ratios = []
    for experiment in experiments:
        for metric in METRICS:
            ratio = experiment["variance"][metric]["ratio"]
            if ratio is not None:
                ratios.append(ratio)
    ratios_sorted = sorted(ratios)
    median = (statistics.median(ratios) if ratios else None)
    fraction_below_one = (sum(1 for r in ratios if r < 1.0) / len(ratios)
                          if ratios else None)
    bias_differences = [abs(experiment["bias"][metric]["difference"])
                        for experiment in experiments
                        for metric in METRICS]
    return {
        "variance_ratio_count": len(ratios),
        "variance_ratio_median": median,
        "variance_ratio_min": (ratios_sorted[0] if ratios else None),
        "variance_ratio_max": (ratios_sorted[-1] if ratios else None),
        "variance_ratio_fraction_below_one": fraction_below_one,
        "variance_ratio_fraction_below_0_95": (
            sum(1 for r in ratios if r <= 0.95) / len(ratios)
            if ratios else None),
        "max_abs_bias_difference": max(bias_differences)
        if bias_differences else None,
        "total_pairs": sum(sum(experiment["valid_pairs"])
                           for experiment in experiments),
        "total_superseded": sum(experiment["superseded"]
                                for experiment in experiments),
        "total_inert": sum(experiment["inert"] for experiment in experiments),
        "total_applied": sum(experiment["applied"]
                             for experiment in experiments),
        "total_race_end_cancelled": sum(
            experiment["race_end_cancelled"] for experiment in experiments),
        "all_aggregates_reproduce": all(
            experiment["aggregate_reproduction_ok"]
            for experiment in experiments),
    }


def decide(summary: dict, experiments) -> dict:
    median = summary["variance_ratio_median"]
    below_one = summary["variance_ratio_fraction_below_one"]
    below = summary["variance_ratio_fraction_below_0_95"]
    material_bias = _material_bias(experiments)
    if not summary["all_aggregates_reproduce"]:
        decision = "S3 BLOCKED — PER-INDEX CONTRACT INVALID"
        rationale = ["per-index outcomes do not reproduce the arm aggregates"]
    elif material_bias:
        decision = "CRN_UNSAFE"
        rationale = ["paired and independent estimators disagree beyond "
                     "Monte Carlo uncertainty (material bias)"]
    elif median is None:
        decision = "NO_CRN_BENEFIT"
        rationale = ["no defined variance ratios"]
    elif median >= 1.05:
        decision = "CRN_UNSAFE"
        rationale = [f"median variance ratio {median:.3f} >= 1.05"]
    elif 0.95 <= median < 1.05:
        decision = "NO_CRN_BENEFIT"
        rationale = [f"median variance ratio {median:.3f} is ~1"]
    elif median < 1.0 and (below is not None and below >= 0.8):
        decision = "ADOPT_CRN"
        rationale = [f"median variance ratio {median:.3f} < 1 and "
                     f"{below:.0%} of cases < 0.95"]
    else:
        decision = "ADOPT_CRN_WITH_LIMITATIONS"
        rationale = [f"median variance ratio {median:.3f} < 1 but evidence "
                     "is mixed across cases"]
    return {"decision": decision, "rationale": rationale,
            "material_bias_detected": material_bias}


def _material_bias(experiments) -> bool:
    """Conservative bias check across seeds.

    Flags a metric if the paired and independent seed-mean estimators differ
    by more than 4 standard errors of the independent seed-mean (using the
    independent seed-to-seed variance), on any case.
    """
    n = len(MASTER_SEEDS)
    for experiment in experiments:
        for metric in METRICS:
            paired = experiment["paired"][metric]
            independent = experiment["independent"][metric]
            if len(independent) < 2:
                continue
            variance = statistics.variance(independent)
            if variance <= 0.0:
                continue
            se = (variance / n) ** 0.5
            difference = abs(statistics.fmean(paired)
                             - statistics.fmean(independent))
            if se > 0.0 and difference > 4.0 * se:
                return True
    return False


def main() -> dict:
    started = time.perf_counter()
    experiments = run_experiment()
    summary = summarise(experiments)
    decision = decide(summary, experiments)
    payload = {
        "generated_by": "scripts/run_phase7_s3_crn_validation.py",
        "protocol_version": PROTOCOL_VERSION,
        "paired_contract_version": PAIRED_CONTRACT_VERSION,
        "simulation_count": SIMULATION_COUNT,
        "master_seeds": list(MASTER_SEEDS),
        "independent_seed_rule": (
            "S2 = (S * 6364136223846793005 + 1442695040888963407) mod 2^63"),
        "independent_baseline_rule": (
            "the seed-S baseline run is reused; only the intervention is "
            "re-run with the independent seed S2"),
        "states": list(STATE_SPECS),
        "actions": list(ACTION_SPECS),
        "counts": {
            "experiments": len(experiments),
            "seeds": len(MASTER_SEEDS),
        },
        "decision_policy": DECISION_POLICY,
        "experiments": experiments,
        "summary": summary,
        "decision": decision,
        "wall_time_s": time.perf_counter() - started,
        "limitations": [
            "This is an estimator-variance study, not a strategy "
            "recommendation; no ranking or objective is computed.",
            "Real anchors use only the point-in-time state at T and "
            "parameters fit strictly before the target season; the historical "
            "future is never an input.",
            "The variance ratio is estimated from a predeclared seed set; it "
            "is itself a noisy estimate.",
            "The artifact is generated (not tracked) under /data/v2/, which "
            "repository policy keeps out of version control.",
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
        "summary": result["summary"],
        "decision": result["decision"],
        "wall_time_s": result["wall_time_s"],
    }, indent=2, sort_keys=True))
