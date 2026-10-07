#!/usr/bin/env python3
"""V3.2H preregistration freezer (Part E).

Writes results/v3/v3_2h/preregistration.json with a content hash.
Must be frozen BEFORE any regime outcome scoring; all evaluation
scripts verify this hash. No post-result tuning.

Deterministic: no timestamps, usernames, or absolute paths.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "results" / "v3" / "v3_2h"
PREREG_PATH = OUT_DIR / "preregistration.json"

SCHEMA = "v3.2h-preregistration-v1"


def build() -> dict:
    return {
        "schema_version": SCHEMA,
        "baseline": {"tag": "v3.1-race-dynamics", "commit": "64c5af0"},
        "accepted_mc2": {
            "research": "mc2-r1-research",
            "kernel": "mc2-kernel-v1",
            "rng": "mc2-rng-v1",
            "field": "mc2-field-v1",
            "presence": "v3.2c-presence-v1",
            "arm": "E_AR1_RESIDUAL",
            "rho": 0.264,
            "n_runs_production": 5000,
        },
        "dry_green_parity": {
            "corpus": "results/v3/v3_2f/dry_green_parity_corpus.json",
            "hash_prefix": "7ae97c3c",
            "members": 50,
            "requirement": "PARITY_OK_BIT_EXACT before and after H",
        },
        "candidate_order": ["VSC", "VSC_ENDING", "WET", "SAFETY_CAR",
                            "YELLOW", "RED"],
        "mechanisms": {
            "VSC": {
                "duration": "empirical residual-duration distribution "
                            "conditional on elapsed VSC age "
                            "(past-only laps); P(continue|age=a) from "
                            "historical survival; no factual end read",
                "pace": "VSC-specific central offset + driver variation + "
                        "variance estimated past-only; minimal supported "
                        "choice among {freeze, carry-shrunk, reset}",
                "gaps": "evidence audit only (preserve/compress/expand); "
                        "no overtaking mechanism",
                "exit": "transition back to accepted DRY_GREEN MC2 E with "
                        "explicit anchor/AR/gap state; no factual restart "
                        "observations",
                "rng": "mc2-vsc-duration (reserved, dedicated)",
            },
            "VSC_ENDING": {
                "mechanism": "token-semantics audit only; ending "
                             "transition iff token proven factual-at-T; "
                             "no inferred green timestamp",
            },
            "WET": {
                "pace": "temporal hierarchy INTERMEDIATE/WET by era "
                        "(x circuit/rain-state/phase only if N supports); "
                        "past-only",
                "driver_state": "evaluate dry-anchor transfer; choose "
                                "among {carry-shrunk, reset, wet-anchor} "
                                "on causal evidence BEFORE outcome scoring",
                "residual": "estimate variance/autocorr where supported; "
                            "else simpler justified process (no auto "
                            "rho=0.264 reuse)",
                "weather_evolution": "historical transition/survival over "
                                     "{WET, INTERMEDIATE, DRY} if "
                                     "supported; no ML; "
                                     "rng mc2-weather-transition",
                "tyre_transition": "audit R6 dry-filtered boundary; minimal "
                                   "empirical rule only if separable from "
                                   "Strategy 2.0, else REJECT_WET",
            },
            "SAFETY_CAR": {
                "duration": "past-only episode distribution/survival; "
                            "rng mc2-sc-duration; never factual end",
                "compression": "mandatory interpretable field-bunching "
                               "model from historical evidence; no "
                               "overtaking",
                "restart": "SC->DRY_GREEN transition, no factual future",
                "pits": "audit R6 green-flag pit validity under SC; "
                        "REJECT_SC if SC-aware pits needed but "
                        "inseparable from Strategy 2.0",
            },
            "YELLOW": {
                "mechanism": "investigation only: causal sector->driver "
                             "exposure from Phase12 artifacts without "
                             "future info or subsystem coupling; "
                             "no global pace penalty ever",
            },
            "RED": {
                "mechanism": "none by default (REJECT_RED); audit only",
            },
        },
        "temporal_folds": [
            {"fold": "H1", "train_through": 2021, "evaluate": [2022, 2023]},
            {"fold": "H2", "train_through": 2023, "evaluate": [2024]},
        ],
        "forbidden": [
            "2025 data for training or evaluation",
            "future TrackStatus / race-control / weather / rainfall / "
            "compounds / pits / lap timing at or after T",
            "future regime end / restart observations",
            "position_null or STOPPED for retirement",
            "external retirement source; future-DNF inference",
            "altering DRY_GREEN MC2-E behavior or retuning dry params "
            "on regime outcomes",
            "ML classifiers/predictors; winner-model probabilities; "
            "Strategy 2.0; Counterfactual Lab; frontend; demo cache",
        ],
        "parameter_families": [
            "vsc-duration-survival-v1",
            "vsc-pace-v1",
            "vsc-exit-v1",
            "wet-pace-v1",
            "weather-transition-v1",
            "sc-duration-v1",
            "sc-compression-v1",
            "sc-restart-v1",
        ],
        "metrics": [
            "duration calibration slope + MAE (laps)",
            "during-regime pace MAE (s)",
            "post-exit pace MAE (s)",
            "field-spread ratio (during/before, after/before)",
            "winner log-loss / Brier, expected-finish MAE, RPS "
            "(only if an integrated simulator exists; else "
            "NOT_MEASURABLE_OFFLINE)",
            "invalid rate (must be 0/unacceptably-low for admission)",
        ],
        "admission_gates": {
            "common": [
                "causal start state (factual-at-T only)",
                "past-only parameters (strictly races before Y)",
                "future-end/weather firewall (poison-tested)",
                "determinism (same seed equality; domain-separated RNG; "
                "no perturbation of DRY_GREEN streams)",
                "dry-green parity bit-exact (50-checkpoint corpus)",
                "invalid rate 0 or unacceptably low",
                "no material outcome pathology",
            ],
            "VSC": [
                "duration calibration slope in [0.5, 1.5] on held-future "
                "episodes AND duration MAE <= 1.5 laps",
                "during-VSC pace MAE <= 10.0 s (past-only median rule)",
                "post-exit pace MAE <= 6.0 s",
                "field-spread ratio during/before in [0.5, 1.5] "
                "(no bunching/dispersion pathology)",
            ],
            "WET": [
                "runnable candidate exists (weather evolution + compound "
                "transition both causal)",
                "wet pace MAE <= 6.0 s on held-future wet laps",
                "compound-transition policy explicit and separable "
                "from Strategy 2.0",
            ],
            "SAFETY_CAR": [
                "compression mechanism explicit, interpretable, "
                "evidence-backed",
                "restart transition explicit with no factual future",
                "pit-validity boundary explicit (green-flag R6 valid "
                "under SC or REJECT)",
            ],
            "YELLOW": [
                "exact at-T affected-driver exposure established "
                "causally; else REJECT_YELLOW (no global penalty)",
            ],
            "RED": [
                "admit only if V3.2F conclusion overturned by new "
                "evidence; default REJECT_RED",
            ],
        },
        "seed_policy": {
            "parity_seed": 20240101,
            "parity_runs": 500,
            "regime_rng_domains": ["mc2-vsc-duration", "mc2-sc-duration",
                                   "mc2-weather-transition"],
            "rule": "deterministic seeds only; same-seed equality "
                    "required; DRY_GREEN streams unperturbed",
        },
        "simulation_counts": {
            "production": 5000,
            "parity_corpus_runs": 500,
            "offline_validation": "episode/lap-level (no MC integration "
                                  "unless admitted)",
        },
        "fallback_policy": {
            "sparse_cells": "back off to coarser conditioning "
                            "(era -> global); report N and fallback",
            "minimum_cell_n": 30,
            "no_fallback_data": "REJECT the mechanism (no fabrication)",
        },
        "comparison_policy": {
            "comparator": "accepted DRY_GREEN MC2 E (arm E_AR1_RESIDUAL, "
                          "rho=0.264) for green segments only",
            "unit": "race/episode is the high-level statistical unit",
            "no_retune": "dry parameters never retuned on regime outcomes",
        },
        "verdicts_allowed": ["ADMIT_VSC", "REJECT_VSC",
                             "ADMIT_WET", "REJECT_WET",
                             "ADMIT_INTERMEDIATE_STABLE_ONLY",
                             "ADMIT_SC", "REJECT_SC",
                             "ADMIT_YELLOW", "REJECT_YELLOW",
                             "ADMIT_RED", "REJECT_RED"],
    }


def content_hash(obj: dict) -> str:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def main() -> int:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "freeze"
    if cmd == "freeze":
        OUT_DIR.mkdir(parents=True, exist_ok=True)
        payload = build()
        h = content_hash(payload)
        payload["prereg_hash"] = h
        with open(PREREG_PATH, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, sort_keys=True)
            f.write("\n")
        print(f"froze {PREREG_PATH} hash={h}")
        return 0
    if cmd == "verify":
        payload = build()
        h = content_hash(payload)
        saved = json.load(open(PREREG_PATH, encoding="utf-8"))
        ok = saved.get("prereg_hash") == h
        print(f"prereg verify: {'OK' if ok else 'MISMATCH'} "
              f"expected={h} saved={saved.get('prereg_hash')}")
        return 0 if ok else 1
    print(f"unknown command {cmd!r}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
