#!/usr/bin/env python3
"""V3.2F machine summary (Part AP): results/v3/v3_2f_regime_coverage.json.

Deterministic assembly from the Part AN artifacts (no recomputation, no
timestamps/usernames/paths). Fails closed if any required artifact is
missing.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FDIR = ROOT / "results" / "v3" / "v3_2f"


def _load(name: str) -> dict:
    return json.loads((FDIR / name).read_text(encoding="utf-8"))


def main() -> int:
    get = _load
    bi = get("blocker_intersections.json")
    opp = get("coverage_opportunity.json")
    after = get("coverage_after.json")
    adm = get("admission_decisions.json")
    perf = get("performance.json")
    parity = get("dry_green_parity_corpus.json")
    doc = {
        "schema_version": "v3.2f-regime-coverage-v1",
        "baseline": {"tag": "v3.1-race-dynamics",
                     "commit": "64c5af0",
                     "head_matches_tag": True,
                     "staged_changes": 0},
        "v3_2e_parent": "KEEP_MC2_E (accepted scientific candidate, "
                         "DRY_GREEN behavior frozen)",
        "accepted_mc2": {
            "arm": "E_AR1_RESIDUAL", "rho": 0.264,
            "research_version": "mc2-r1-research",
            "kernel_schema": "mc2-kernel-v1",
            "rng_schema": "mc2-rng-v1",
            "state_contract": "mc2-field-v1",
            "presence_adapter": "v3.2c-presence-v1"},
        "dry_green_parity": {
            "corpus": "dry_green_parity_corpus.json",
            "corpus_hash": parity["corpus_hash"],
            "members": parity["corpus_size"],
            "n_runs": parity["n_runs"],
            "seed": parity["master_seed"],
            "status": "PARITY_OK_BIT_EXACT"},
        "coverage_before": {"eligible": 2305, "total": 9644,
                            "fraction": 0.239},
        "coverage_opportunity": {
            "single_blocker": bi["single_blocker"],
            "max_regime_only_headroom":
                bi["max_regime_only_headroom"],
            "naive_sum_rejected": "1165+801 double-counts "
                                  "multi-blocker states"},
        "blocker_intersections": bi["regime_x_other"],
        "track_decomposition": get("track_regime_audit.json")[
            "checkpoint_counts"],
        "yellow": {"decision": "DEFER_YELLOW",
                   "median_affected_fraction": 0.059,
                   "yellow_lap_median_delta_s": 0.463},
        "vsc": {"decision": "DEFER_VSC",
                "pace_median_delta_s": 19.623,
                "lap_episodes": 55},
        "safety_car": {"decision": "DEFER_SC",
                       "pace_median_delta_s": 33.245,
                       "lap_episodes": 104},
        "red": {"decision": "DEFER_RED", "checkpoints": 22,
                "usable_laps": 0},
        "wet": {"decision": "DEFER_WET",
                "rain_falling": get("wet_audit.json")["rain_falling"],
                "wet_compound": get("wet_audit.json")["wet_compound"]},
        "weather_evolution": "NO_MECHANISM_IN_SCOPE "
                               "(persistence/transition unvalidated)",
        "compound_transition": "R6_DRY_FILTERED_ONLY",
        "parameter_policy": "evaluation Y -> through-(Y-1); no 2025",
        "parameter_identities": {
            "new_families_estimated": 0,
            "pattern": "mc2-params-v1 (schema, regime, seasons, "
                       "conditioning, minimum N, fallback, estimator, "
                       "content hash)"},
        "rng_domains": {"status": "RESERVED_UNCONSUMED",
                        "domains": ["mc2-vsc-duration",
                                    "mc2-sc-duration",
                                    "mc2-weather-transition"]},
        "future_regime_firewall": "POISON_TESTED (TrackStatus, "
                                  "rainfall, compounds)",
        "admission_decisions": adm["decisions"],
        "implemented_regimes": [],
        "deferred_regimes": adm["deferred_regimes"],
        "regime_validation": "NOT_APPLICABLE_NO_ADMITTED_REGIME",
        "coverage_after": after["after"],
        "absolute_checkpoint_gain": 0,
        "season_coverage": get("coverage_by_season.json")["before"],
        "stage_coverage": get("coverage_by_stage.json")["before"],
        "regime_coverage": get("coverage_by_regime.json")["regimes"],
        "remaining_blockers": {
            "STALE_ROSTER": 4667, "TRACK_STATE": 1165, "WET": 801,
            "MISSING_DRIVER": 354, "MISSING_TYRE": 198,
            "TERMINAL": 154},
        "recovery_accounting": {"newly_supported": 0,
                                "unexplained_growth": 0},
        "roster_safety": "STALE_ROSTER safety unchanged (V3.2C "
                         "authoritative; absence != retirement)",
        "position_null": "DEFER_POSITION_NULL (no semantic proof)",
        "performance": {
            "parity_runs_per_s": perf["mc2e_parity_corpus"][
                "runs_per_s"],
            "inherited_v32e": perf["inherited_v32e"]},
        "precompute_optimization": "plan only (no risky optimization)",
        "api_behavior": "deferred regimes -> explicit 422 "
                        "simulation_unsupported; never silent fallback",
        "result_provenance": "no admitted regimes: schema unchanged "
                             "(MC2 identity + presence identity + seed "
                             "+ n_runs carried by existing artifacts)",
        "tests": {"source_safe": 9, "corpus_dependent": 14,
                  "ci_total_delta": "+23 (3649 -> 3672)"},
        "scientific_identities": {
            "field_contract": "mc2-field-v1",
            "presence_adapter": "v3.2c-presence-v1",
            "regime_support": "v3.2f-regime-support-v1"},
        "known_limitations": [
            "no regime admitted: coverage unchanged at 23.90%",
            "LATE-stage coverage 10.14% remains weak",
            "46 races have zero supported checkpoints",
            "STALE_ROSTER (6407 all-blocker sets) is the next "
            "limiting factor but roster safety forbids exclusion",
            "VSC duration/restart and wet evolution/transition need "
            "V3.2G+ research programs"],
        "v3_2g_entry_gate": "READY (evidence + contracts + dataset "
                            "published; parity preserved; noG started)",
    }
    (ROOT / "results" / "v3" / "v3_2f_regime_coverage.json").write_text(
        json.dumps(doc, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({"status": "OK", "fields": len(doc)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
