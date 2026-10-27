#!/usr/bin/env python3
"""V3.11D step 3 -- validation protocol (PRE-DECLARED, before scoring).

Freezes candidates, calibration/validation splits, metrics, aggregation,
acceptance/rejection criteria, exclusions, and determinism policy BEFORE
any validation-split scoring. Refuses to regenerate once validation
results exist (fail closed against post-hoc tuning).

Usage:
    .venv/bin/python scripts/v3_11d_protocol.py
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_11d"


def main() -> int:
    t0 = time.perf_counter()
    if (OUT / "vsc_validation_results.json").exists():
        print("STOP: validation results already exist; protocol frozen",
              flush=True)
        return 2
    quality = json.loads(
        (OUT / "vsc_episode_quality.json").read_text(encoding="utf-8"))

    doc = {
        "schema_version": "v3.11d-validation-protocol-v1",
        "declared_before_scoring": True,
        "candidates": {
            "V0": "refuse VSC (frozen control; explicit TRACK rejection)",
            "V1": "global pace ratio R (median ACTIVE/PRE on calibration "
                  "episodes) applied to expected green pace during "
                  "causally-known VSC laps; frozen ordering mechanics",
            "V2": "V1 + validated gap-preservation claim (uniform ratio; "
                  "no extra mechanism)",
            "V3": "EXCLUDED at protocol time: pit-loss evidence "
                  "insufficient (out-lap marginals n=7); fail-closed "
                  "where pit events are relevant",
        },
        "calibration": {
            "episodes": "usable calibration split (2018-2021)",
            "parameter": "R = median driver-lap ACTIVE/PRE ratio, pooled "
                         "calibration ACTIVE laps",
            "race_specific_alternative": "per-race median ratio (research "
                                         "comparison only; global "
                                         "preferred unless validation "
                                         "proves need)",
        },
        "validation": {
            "episodes": "usable validation split (2022-2024), unscored "
                        "until this protocol froze",
            "aggregation": "episode-macro (each episode equal weight) + "
                           "pooled driver-lap; both reported",
        },
        "metrics": {
            "pace": "MAE of R_cal*base vs actual ACTIVE lap times "
                    "(seconds, absolute scale)",
            "gap": "steady ACTIVE pairwise-gap-change distribution vs "
                   "PRE baseline",
            "order": "steady ACTIVE position-change rate vs PRE baseline",
            "spread": "ACTIVE/PRE field-spread ratio",
            "withdrawal": "POST-PRE median pace delta",
            "pit": "INSUFFICIENT (fail-closed rule instead of metric)",
            "duration": "median-duration rule MAE (laps) + calibration "
                        "slope on validation split (independent H check)",
        },
        "acceptance_gates": {
            "G1_pace": "validation MAE <= 10.0s (H-comparable absolute "
                       "gate; decontaminated windows)",
            "G2_gap": "steady ACTIVE gap-change median <= 1.0s AND p90 "
                      "<= 3.0s (~2x PRE baseline 0.42/1.53)",
            "G3_order": "steady ACTIVE change rate <= 15% (PRE baseline "
                        "bound 14.4%)",
            "G4_spread": "ACTIVE/PRE spread median ratio in [0.8, 1.25]",
            "G5_withdrawal": "|POST-PRE median| <= 5.0s (immediate green "
                             "return)",
            "G6_pit_fail_closed": "rule specified: refuse VSC simulation "
                                  "crossing pit events under VSC "
                                  "(no validated loss model)",
            "G7_causality": "interval semantics causal (C contract); "
                            "poison-pinned; deterministic",
            "G8_green_parity": "GREEN path byte-identical (isolation + "
                               "frozen suites green)",
        },
        "rejection_criteria": [
            "any of G1-G5 fails on the validation split",
            "G6/G7/G8 not satisfiable",
            "duration gate fails => integration blocked (dynamics may "
            "still be reported, verdict at most INSUFFICIENT_EVIDENCE)",
        ],
        "duration_gate": {
            "rule": "median-duration predictor; calibration slope in "
                    "[0.5, 1.5] AND MAE <= 1.0 lap on validation split",
            "on_failure": "duration remains the integration blocker "
                          "(confirms H); no duration component fitted",
        },
        "exclusions": list(quality["exclusions"].keys()) + [
            "entry/exit transition laps from ACTIVE pace metric",
            "pit laps from pace/order/gap metrics",
            "retirement laps from order metric (retrospective label)",
            "single-lap runs (NO_FULL_VSC_LAP) from all metrics",
        ],
        "seed_policy": "deterministic replay only; zero stochastic "
                       "futures in D; no RNG streams created or consumed",
        "coverage_note": "no gate uses coverage percentage; +41/38.57% "
                         "is context only",
    }
    text = json.dumps(doc, indent=1, sort_keys=True)
    doc["protocol_sha256"] = hashlib.sha256(text.encode("utf-8")).hexdigest()
    with open(OUT / "vsc_validation_protocol.json", "w",
              encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print(json.dumps({
        "status": "OK",
        "protocol_sha256": doc["protocol_sha256"],
        "wall_s": round(time.perf_counter() - t0, 1),
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
