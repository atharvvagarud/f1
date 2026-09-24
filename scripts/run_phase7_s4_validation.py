"""Phase-7 S4 validation + performance / memory experiment.

Runs the S4 comparison layer on the accepted MID R7.1 anchor and records REAL
measurements (no fabricated numbers):

- comparison wall time for 1, 3 and all valid default candidates at 1 000
  trajectories, and for 1 and 3 candidates at 10 000;
- the S3 naive baseline (repeated ``run_pair``: one baseline + one intervention
  PER candidate) for the same candidate sets, to measure the baseline-reuse
  saving;
- ``tracemalloc`` peak for the 1 000 all-candidate comparison and the 10 000
  three-candidate comparison;
- a validity-denominator audit (how often the baseline and candidate valid sets
  differ) and the candidate execution-status rates.

Artifact: ``data/v2/strategy/s4_comparison_validation_v1.json``. ``/data/v2/``
is git-ignored by repository policy (generated scientific data is not tracked);
the artifact is reproducible from this script.

Usage (from the repository root)::

    /opt/homebrew/bin/python3.11 scripts/run_phase7_s4_validation.py
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
    COMPARISON_VERSION,
    CRN_POLICY,
    build_candidate,
    compare_strategies,
    run_pair,
)
from v2.strategy.candidates import (  # noqa: E402
    CANDIDATE_CONTRACT_VERSION,
    CANONICAL_CANDIDATE_SPECS,
)

ARTIFACT_PATH = (ROOT / "data" / "v2" / "strategy"
                 / "s4_comparison_validation_v1.json")

PROTOCOL_VERSION = "s4-comparison-protocol-v1"
MID = {"season": 2022, "race_id": "2022-r01-R", "driver": "perez", "lap": 30}
SEED = 20240101

#: 1-candidate and 3-candidate subsets used for the 10 000-trial runs.
ONE_SPEC = (("STAY_OUT", None),)
THREE_SPECS = (("STAY_OUT", None), ("PIT_NOW", None),
               ("PIT_NEXT_LAP", None))


def _state_and_params():
    from test_v2_phase6_r71 import _params_through, _real_state
    state = _real_state(MID["season"], MID["race_id"], MID["driver"], MID["lap"])
    params = _params_through(MID["season"] - 1)
    return state, params


def _valid_specs(state, config, target, specs):
    out = []
    for action, compound in specs:
        candidate = build_candidate(state, config, target, action, compound)
        if candidate.valid:
            out.append(candidate)
    return out


def _spec_names(candidates):
    return [candidate.key for candidate in candidates]


def _naive_pairs(state, params, config, candidates):
    """S3 baseline: one ``run_pair`` per candidate (repeats the baseline)."""
    return [run_pair(state, params, config, Assumptions(),
                     candidate.intervention)
            for candidate in candidates]


def _timed(func):
    started = time.perf_counter()
    value = func()
    return value, time.perf_counter() - started


def _run_benchmark(state, params, target, count, specs, *, measure_memory):
    config = SimulationConfig(simulation_count=count, master_seed=SEED,
                              sample_orders=0, pit_dynamics_enabled=True)
    candidates = _valid_specs(state, config, target, specs)

    # Timing pass (never under tracemalloc, which would distort wall time).
    result, comparison_s = _timed(lambda: compare_strategies(
        state, params, config, Assumptions(), target,
        candidate_specs=[(action, compound) for action, compound in specs]))

    traced_peak = None
    if measure_memory:
        tracemalloc.start()
        compare_strategies(
            state, params, config, Assumptions(), target,
            candidate_specs=[(action, compound) for action, compound
                             in specs])
        _, traced_peak = tracemalloc.get_traced_memory()
        tracemalloc.stop()

    _, naive_s = _timed(lambda: _naive_pairs(state, params, config, candidates))

    return {
        "count": count,
        "requested_candidates": [list(spec) for spec in specs],
        "valid_candidates": _spec_names(candidates),
        "comparison_s": comparison_s,
        "naive_repeated_run_pair_s": naive_s,
        "baseline_reuse_speedup": (naive_s / comparison_s
                                   if comparison_s else None),
        "comparison_traced_peak_bytes": traced_peak,
        "comparison_identity": result.identity(),
        "supported": result.supported,
        "candidates": [
            {
                "candidate_key": candidate.candidate.key,
                "evaluated": candidate.evaluated,
                "valid": candidate.valid,
                "reason": candidate.reason,
                "delta_win_probability": candidate.delta_win_probability,
                "delta_podium_probability": candidate.delta_podium_probability,
                "delta_expected_finish": candidate.delta_expected_finish,
                "valid_pairs": candidate.valid_pairs,
                "baseline_only_valid": candidate.baseline_only_valid,
                "intervention_only_valid": candidate.intervention_only_valid,
                "both_invalid": candidate.both_invalid,
                "validity_sets_match": candidate.validity_sets_match,
                "execution": (candidate.execution.to_dict()
                              if candidate.execution is not None else None),
            }
            for candidate in result.candidates
        ],
    }


def main() -> dict:
    state, params = _state_and_params()
    target = MID["driver"]

    benchmarks = [
        _run_benchmark(state, params, target, 1000,
                       tuple((action.value, compound)
                             for action, compound
                             in CANONICAL_CANDIDATE_SPECS),
                       measure_memory=True),
        _run_benchmark(state, params, target, 10000, ONE_SPEC,
                       measure_memory=False),
        _run_benchmark(state, params, target, 10000, THREE_SPECS,
                       measure_memory=True),
    ]

    all_candidate_bench = benchmarks[0]
    mismatch_count = sum(
        1 for candidate in all_candidate_bench["candidates"]
        if candidate["evaluated"] and not candidate["validity_sets_match"])
    total_baseline_only = sum(c["baseline_only_valid"]
                              for c in all_candidate_bench["candidates"])
    total_intervention_only = sum(c["intervention_only_valid"]
                                  for c in all_candidate_bench["candidates"])

    return {
        "generated_by": "scripts/run_phase7_s4_validation.py",
        "protocol_version": PROTOCOL_VERSION,
        "comparison_version": COMPARISON_VERSION,
        "candidate_contract_version": CANDIDATE_CONTRACT_VERSION,
        "pairing_policy": CRN_POLICY,
        "state": MID,
        "seed": SEED,
        "counts": [benchmark["count"] for benchmark in benchmarks],
        "benchmarks": benchmarks,
        "validity_denominator_audit": {
            "scope": "1000-trial all-valid-candidate comparison",
            "candidates_with_mismatched_validity_sets": mismatch_count,
            "total_baseline_only_valid": total_baseline_only,
            "total_intervention_only_valid": total_intervention_only,
            "comment": (
                "Delta estimand is the complete-valid-pair mean; arm aggregates "
                "keep their own ordinary valid denominators. A mismatch means "
                "the two differ."),
        },
        "baseline_reuse": {
            "note": (
                "compare_strategies runs ONE baseline + K intervention arms; "
                "the naive S3 path runs K baselines + K intervention arms."),
            "measured": [
                {
                    "count": benchmark["count"],
                    "candidate_count": len(benchmark["valid_candidates"]),
                    "comparison_s": benchmark["comparison_s"],
                    "naive_repeated_run_pair_s":
                        benchmark["naive_repeated_run_pair_s"],
                    "speedup": benchmark["baseline_reuse_speedup"],
                }
                for benchmark in benchmarks
            ],
        },
        "limitations": [
            "Estimates are simulator-conditional Monte Carlo frequencies, "
            "not truth; alternative-strategy outcomes are counterfactual.",
            "One baseline is reused across candidates, so a comparison costs "
            "one baseline + K intervention arms.",
            "No ranking, objective, or production uncertainty is computed.",
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
        "baseline_reuse": payload["baseline_reuse"]["measured"],
        "validity_denominator_audit": payload["validity_denominator_audit"],
    }, indent=2, sort_keys=True))
