#!/usr/bin/env python3
"""V3.2M: freeze preregistration before any pit-outcome scoring.

No 2025. No network. Deterministic (sorted keys, no timestamps).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_2m"


def main() -> int:
    pre = {
        "schema_version": "v3.2m-preregistration-v1",
        "inherited_target_population": {
            "total_checkpoints": 9644,
            "eligible_before": 3678,
            "primary_stale": 3294,
            "note": "frozen V3.2L identities; M projects only, recounts only if admitted",
        },
        "frozen_identities": {
            "baseline_tag": "v3.1-race-dynamics",
            "baseline_commit": "64c5af094bd1304e23a5c7d3d5b782b0eef11aca",
            "accepted_mc2": "unchanged MC2-E",
            "accepted_status_contract": "v3.2j-driver-status-v1",
            "j_corpus": "8229a8606d5331338607dfd4a117a58369534325e0444a3052815299137c6f30",
            "k_prereg": "567260af8072d2e1700a4d1e9ad24265fc458c838010dc8a0d27b745c6a2f22b",
            "l_prereg": "4c3eb5c8cdfe9ebf44555de540ee1378d0b12089d5c8cbc44dea7c0de6c48533",
            "dry_green_parity": "7ae97c3c8575679a",
            "l_episodes": 476,
            "l_pit_context_episodes": 214,
        },
        "pit_context_under_investigation": {
            "definition": "L episode with latest causally observed TimingData InPit value True at stop start (Stopped False->True or first-True transition time). Nothing more is assumed.",
            "explicitly_not": [
                "NOT Stopped+InPit implies routine service",
                "NOT pit context implies return",
                "NOT pit context ignores staleness",
            ],
        },
        "allowed_causal_signals": [
            "TimingData.InPit latest value <= T",
            "TimingData.Stopped latest value <= T and transition times <= T",
            "TimingData.PitOut latest value <= T (as state, never future)",
            "TimingData.NumberOfPitStops latest value <= T",
            "TimingData.Retired latest value <= T (J contract, exclusion only)",
            "D9 canonical state <= T (lap/pos/tyre/pit count/track status)",
            "TimingAppData stint/compound <= T where available",
            "race-control messages <= T",
            "elapsed time since stop start (T minus stop-start time)",
        ],
        "forbidden_future_signals": [
            "final DNF/classification",
            "future PitOut as input",
            "future pit duration as input",
            "future lap crossing as input",
            "actual historical remaining service time at inference",
            "driver-specific lookup table",
            "driver identity as shortcut",
            "2025 data",
        ],
        "episode_inclusion_rules": [
            "inherit L 476-episode corpus verbatim (no regeneration/redefinition)",
            "audit all 214 PIT_CONTEXT episodes with causal/future table separation",
        ],
        "episode_exclusion_rules": [
            "CLEAN/INITIAL_UNKNOWN/LATE_SESSION episodes are context only, never training for pit duration",
            "RED/neutralised-affected pit episodes excluded from duration modelling",
        ],
        "temporal_folds": [
            "train <=2020 eval 2021",
            "train <=2021 eval 2022",
            "train <=2022 eval 2023",
            "train <=2023 eval 2024",
        ],
        "no_random_episode_split": True,
        "pit_return_analysis": {
            "target": "P(return | candidate causal pit state) with uncertainty/sample count",
            "return_def_primary": "competitive D9 lap crossing after stop start (same L definition)",
            "return_def_mechanism": "which event corresponds to MC2 resumption decided in duration-target analysis (PitOut vs D9 crossing), not by lowest error",
            "non_return_taxonomy": [
                "different causal state",
                "garage retirement",
                "mechanical failure",
                "red flag",
                "session termination",
                "feed artifact",
                "genuinely unpredictable terminal event",
            ],
            "gate": "if routine service cannot be separated causally from garage/terminal states: REJECT",
        },
        "remaining_duration_target": {
            "definition": "time from checkpoint T until driver resumes exact competitive process required by MC2",
            "conditioning": "P(additional pit delay | elapsed pit duration, causal context); sample must never imply completion before T",
            "mc2_resumption_event": "to be determined (PitOut vs D9 crossing); chosen by mechanism semantics",
        },
        "candidate_duration_baselines": [
            "global median remaining duration",
            "season/era median",
            "circuit median where sufficiently supported",
            "elapsed-duration conditional empirical distribution",
            "pit-state conditioned empirical distribution",
        ],
        "candidate_duration_model": {
            "only_if_needed": True,
            "family": "simple empirical/parametric conditional distribution; no driver identity; no future outcome",
            "allowed_inputs": [
                "elapsed pit-state duration",
                "race stage",
                "circuit characteristics if sufficiently supported",
                "pit-state subtype",
                "tyre change context if known at T",
                "track status at T",
            ],
        },
        "duration_metrics": ["MAE", "median absolute error", "p90 absolute error", "bias", "sampled-vs-heldout distributional resemblance"],
        "admission_gates": [
            "causal state identifiable",
            "return semantics defensible",
            "duration model temporally adequate",
            "state anchor sufficient",
            "no general terminal branching required",
            "MC2 extension scientifically coherent",
            "projected gain material enough to justify complexity",
            "future poison PASS",
            "deterministic implementation possible",
            "old-state parity preservable",
        ],
        "runtime_mechanism_gate": {
            "classes": ["MINIMAL_INITIAL_CONDITION_EXTENSION", "LOCAL_KERNEL_EXTENSION", "FUNDAMENTAL_KERNEL_REWRITE"],
            "rule": "FUNDAMENTAL_KERNEL_REWRITE -> do not implement in M (defer/reject)",
            "precedence": "J Retired=True retains absolute precedence; M never reactivates J-retired driver",
        },
        "coverage_rules": {
            "checkpoint_pit_fully_addressable": "every unresolved stale offender is J_RETIRED or PIT_LIFECYCLE_CANDIDATE (causal classification only, no future outcome)",
            "offender_classes": ["J_RETIRED", "PIT_LIFECYCLE_CANDIDATE", "GENERAL_LIFECYCLE", "NO_PIT_SIGNAL", "AMBIGUOUS"],
            "projection_is_projection_only": True,
        },
        "parity_rules": {
            "old_eligible": "all 3678 existing eligible checkpoints remain eligible",
            "dry_green": "7ae97c3c corpus bit-exact",
            "new_rng_domain": "e.g. mc2-initial-pit-delay; existing MC2-E streams untouched; old-state sims consume zero new draws",
        },
        "rng_policy": "stdlib/deterministic; dedicated domain reserved only if admitted; no perturbation of frozen streams",
        "testing_policy": {
            "always": ["new V3.2M tests", "touched module tests", "J/K/L pit-semantics contract tests", "temporal poison tests", "parity tests if runtime changed", "MC2 tests if kernel changed", "API tests only if API changed"],
            "full_tier1_only_if": "admitted + shared runtime/MC2 modified, or targeted testing shows cross-cutting regression",
            "if_rejected": "FULL_TIER1 = NOT_REQUIRED_RESEARCH_ONLY",
        },
        "stopping_rule": [
            "routine pit not causally separable from garage/terminal -> REJECT",
            "remaining duration temporally unstable -> REJECT",
            "terminal-vs-return modelling required -> REJECT",
            "fundamental MC2 rewrite required -> DEFER/REJECT",
            "gain immaterial vs complexity -> REJECT as tradeoff",
            "never weaken a gate to increase coverage",
        ],
        "forbidden_2025": True,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    text = json.dumps(pre, sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(text.encode()).hexdigest()
    (OUT / "preregistration.json").write_text(text, encoding="utf-8")
    (OUT / "preregistration.sha256").write_text(digest + "\n", encoding="utf-8")
    print(f"prereg {digest} n_keys={len(pre)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
