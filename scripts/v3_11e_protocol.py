#!/usr/bin/env python3
"""V3.11E step 0 -- D blocker registry + E evidence protocol (predeclared).

Reads frozen D artifacts (read-only) and emits, BEFORE any E scoring:
  d_blocker_registry.json
  evidence_resolution_protocol.json (with protocol_sha256 identity)
  temporal_split_manifest.json

Deterministic. No production imports. No MC2 execution. Writes are
content-addressed: identical content is not rewritten (mtime = first
declaration, supporting protocol-before-scoring ordering).

Usage:
    .venv/bin/python scripts/v3_11e_protocol.py
"""

from __future__ import annotations

import csv
import hashlib
import json
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "results" / "v3" / "v3_11d"
OUT = ROOT / "results" / "v3" / "v3_11e"


def _read_d(name):
    with open(D / name, encoding="utf-8") as fh:
        return json.load(fh)


def _write(name, doc):
    OUT.mkdir(parents=True, exist_ok=True)
    blob = json.dumps(doc, indent=1, sort_keys=True) + "\n"
    path = OUT / name
    if path.exists() and path.read_text(encoding="utf-8") == blob:
        return False
    path.write_text(blob, encoding="utf-8")
    return True


def _sha(doc_without_sha):
    blob = json.dumps(doc_without_sha, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(blob).hexdigest()


def main() -> int:
    t0 = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)

    proto = _read_d("vsc_validation_protocol.json")
    res = _read_d("vsc_validation_results.json")
    qual = _read_d("vsc_episode_quality.json")
    gap = _read_d("vsc_gap_analysis.json")
    spread = _read_d("vsc_field_spread_analysis.json")
    pit = _read_d("vsc_pit_loss_analysis.json")
    wd = _read_d("vsc_withdrawal_analysis.json")
    dur = _read_d("vsc_duration_check.json")
    card = _read_d("scientific_card.json")

    # ---- D blocker registry (extraction only; no reinterpretation) ----
    registry = {
        "schema_version": "v3.11e-blocker-registry-v1",
        "d_classification": card["classification"],
        "d_protocol_sha256": proto["protocol_sha256"],
        "d_integration_decision": "INSUFFICIENT_EVIDENCE",
        "frozen_parameters": {
            "R_cal": res["calibration"]["R_median"],
            "R_mean": res["calibration"]["R_mean"],
            "calibration_driver_laps": res["calibration"]["driver_laps"],
            "note": "E reuses R_cal frozen; E does not refit pace",
        },
        "temporal_split": {
            "calibration": "seasons 2018-2021",
            "validation": "seasons 2022-2024",
            "usable_calibration_episodes":
                qual["usable_by_split"]["calibration"],
            "usable_validation_episodes":
                qual["usable_by_split"]["validation"],
        },
        "episodes": {
            "n_intervals": qual["n_episodes"],
            "usable": qual["usable"],
            "unusable": qual["unusable"],
            "strict_interior_usable": qual["strict_interior_usable"],
            "exclusions": qual["exclusions"],
            "quality_rule": qual["quality_rule"],
        },
        "gates": {
            gid: {
                "definition": proto["acceptance_gates"][gid],
                "d_result": res["gates"][gid],
            } for gid in proto["acceptance_gates"]
        },
        "d_validation_values": res["validation"],
        "blockers": {
            "gap": {
                "gate": "G2_gap",
                "threshold": proto["acceptance_gates"]["G2_gap"],
                "validation_median_s":
                    res["validation"]["gap_steady_median_s"],
                "validation_p90_s":
                    res["validation"]["gap_steady_p90_s"],
                "adequacy": res["sample_adequacy_note"],
                "full_sample_median_s":
                    gap["pairwise_gap_steady_active_s"]["median"],
                "full_sample_count":
                    gap["pairwise_gap_steady_active_s"]["count"],
            },
            "spread": {
                "gate": "G4_spread",
                "threshold": proto["acceptance_gates"]["G4_spread"],
                "validation_ratio_median":
                    res["validation"]["spread_ratio_median"],
                "full_sample_active_count":
                    spread["spread_active_s"]["count"],
            },
            "duration": {
                "gate": proto["duration_gate"]["rule"],
                "on_failure": proto["duration_gate"]["on_failure"],
                "d_result": dur["gate"],
                "n_intervals": dur["n_intervals"],
                "median_duration_s": dur["median_duration_s"],
                "finding": dur["finding"],
            },
            "pit": {
                "v3_status": proto["candidates"]["V3"],
                "vsc_pit_lap_count":
                    pit["vsc_pit_laps_extra_time_s"]["count"],
                "out_lap_note": "out-lap marginals n=7 (protocol text)",
            },
        },
        "ending_treatment_in_d": {
            "policy": "vsc_ending laps excluded from ACTIVE windows; "
                      "withdrawal onset marker only (rule v2)",
            "micro_scope": "noted but refused post-hoc in D",
        },
        "d_supported_dimensions": {
            "pace_mae_pooled_s": res["validation"]["pace_mae_pooled_s"],
            "pace_mae_macro_s":
                res["validation"]["pace_mae_episode_macro_s"],
            "order_steady_rate": res["validation"]["order_steady_rate"],
            "withdrawal_median_s":
                res["validation"]["withdrawal_post_minus_pre_median_s"],
        },
    }
    _write("d_blocker_registry.json", registry)

    # ---- temporal split manifest (from frozen D episode CSV) ----
    with open(D / "vsc_episode_dataset.csv", encoding="utf-8") as fh:
        eps = list(csv.DictReader(fh))
    assert len(eps) == 82, len(eps)
    manifest = {
        "schema_version": "v3.11e-split-manifest-v1",
        "source": "results/v3/v3_11d/vsc_episode_dataset.csv "
                  "(frozen, read-only)",
        "split_rule": "calibration = season <= 2021; "
                      "validation = season >= 2022 (D split retained)",
        "split_changed": False,
        "episodes": [
            {"episode_id": e["episode_id"], "race_id": e["race_id"],
             "season": int(e["season"]), "split": e["split"],
             "usable": e["usable"] == "True",
             "exclusion": e["exclusion"] or None}
            for e in eps
        ],
        "counts": {f"{s}|usable={u}": n for (s, u), n in sorted(
            Counter((e["split"], e["usable"] == "True")
                    for e in eps).items(), key=str)},
    }
    _write("temporal_split_manifest.json", manifest)
    # ---- E evidence protocol (PREDECLARED before any E scoring) ----
    protocol = {
        "schema_version": "v3.11e-evidence-protocol-v1",
        "stage": "V3.11E VSC evidence resolution",
        "frozen_base": "v3.10-pit-wall (2c00e7e)",
        "predecessors": {
            "V3.11A": "MC2_COVERAGE_FORENSICS_COMPLETE",
            "V3.11B": "CAUSAL_STATE_RECONSTRUCTION_REJECTED",
            "V3.11C": "TRACK_SOURCE_REGIME_FORENSICS_COMPLETE",
            "V3.11D": "VSC_REGIME_MODEL_INSUFFICIENT_EVIDENCE",
        },
        "declared_before_scoring": True,
        "d_protocol_sha256": proto["protocol_sha256"],
        "evidence_questions": {
            "EQ1": "Is future VSC duration required by MC2 once "
                   "simulation advances beyond factual T?",
            "EQ2": "Can remaining VSC duration at T be represented "
                   "without future leakage and with enough fidelity?",
            "EQ3": "Does legitimate sample construction resolve the "
                   "gap gate (D thresholds unchanged)?",
            "EQ4": "Does legitimate sample construction resolve the "
                   "spread gate (D thresholds unchanged)?",
            "EQ5": "Is VSC_ENDING dynamically equivalent to ACTIVE VSC?",
            "EQ6": "Did defensible pit-loss evidence improve over D?",
            "EQ7": "Is pit semantics still a mandatory blocker?",
        },
        "permitted_datasets": [
            "data/v2/processed/driver_lap_state_d9/season=2018..2024 "
            "(same corpus as D; season=2025 excluded: outside D frame)",
            "results/v3/v3_11d/vsc_episode_dataset.csv (frozen intervals; "
            "read-only)",
            "results/v3/v3_11d/*.json (frozen D evidence; read-only)",
            "results/v3/v3_11a/unsupported_state_ledger.json (read-only; "
            "secondary-blocker accounting only)",
        ],
        "forbidden_inputs": [
            "season=2025 rows (outside the frozen D frame)",
            "any rewriting of A/B/C/D artifacts",
            "future withdrawal/duration/message/state in runtime "
            "semantics",
            "coverage percentage as any gate",
        ],
        "temporal_split": "D split retained unchanged: calibration "
                          "seasons <= 2021, validation seasons >= 2022; "
                          "all E scoring on validation unless a dimension "
                          "protocol states otherwise",
        "window_rules_retained_from_d": [
            "entry lap always dropped; exit lap dropped iff direct "
            "vsc->all_clear withdrawal (rule v2)",
            "PRE = up to 3 all_clear laps before start_s; POST = up to 3 "
            "laps after exit_lap",
            "clean() = finite positive lap_time_s and no pit_in_s/out_s",
            "spread lap needs >= 10 clean same-token rows",
            "pit/retirement laps excluded per metric",
            "SC/red-adjacent runs excluded at episode level",
        ],
        "ending_policy": {
            "quarantine": "vsc_ending laps excluded from all ACTIVE "
                          "windows until EQ5 resolves",
            "test": "pooled MAE of frozen R_cal=1.272 on ending-lap "
                    "driver laps (same driver-PRE base method as D)",
            "SAME_DYNAMICS": "MAE <= 10.0s (D G1 bar) AND "
                             "N_ending_driver_laps >= 20; ending laps "
                             "then join ACTIVE windows for gap/spread "
                             "construction only",
            "DISTINCT_TRANSITION_DYNAMICS": "N >= 20 AND (MAE > 10.0s "
                                            "OR |median_ratio - 1.272| "
                                            "> 0.10)",
            "INSUFFICIENT_EVIDENCE": "N_ending_driver_laps < 20",
            "consequence_if_not_same": "D behavior retained (ending "
                                       "excluded); no silent merge",
        },
        "duration_protocol": {
            "question": "EQ1/EQ2",
            "hypotheses": {
                "A": "no duration prediction needed: runtime advances "
                     "under VSC only while causal state remains VSC",
                "B": "simulation beyond factual T needs future VSC "
                     "duration: explicit duration handling required",
                "C": "stochastic duration distribution fitted from "
                     "history",
            },
            "mapping_rule": "A holds only for anchoring/replay AT "
                            "factual T; B holds iff MC2 steps beyond T "
                            "under VSC (verified by reading frozen MC2 "
                            "engine stepping, no modification); C is the "
                            "candidate under test",
            "endpoint_primary": "time to VSC-token exit in seconds "
                                "(any exit cause)",
            "endpoint_secondary": "time to GREEN return (SC/RED exits "
                                  "as competing risks; descriptive only)",
            "censoring": {
                "END_OF_DATA": "right-censored at observed length",
                "SC_RED_exits": "complete for primary endpoint; "
                                "competing for GREEN-return endpoint",
                "single_lap": "complete short durations (informative)",
            },
            "candidates": {
                "D0": "refuse future VSC continuation (control; "
                      "confirms blocker)",
                "D1": "empirical global duration distribution "
                      "(Kaplan-Meier; remaining via conditional "
                      "survival)",
                "D2": "conditional model ONLY if N_cal_complete >= 50 "
                      "AND covariates from predeclared set "
                      "{elapsed VSC time at T} plus circuit class only "
                      "if >= 3 circuits have >= 10 complete durations "
                      "each",
            },
            "remaining_duration_queries": "elapsed marks {30, 60, 120}s "
                                          "post-activation on episodes "
                                          "active at the mark",
            "metrics": ["median absolute error on remaining duration",
                        "80% interval hit rate (calibration)",
                        "interval width distribution"],
            "success_DUR1_sample": "N_cal_complete >= 30 AND "
                                   "N_val_complete >= 10",
            "success_DUR2_calibration": "80% interval hit rate on "
                                        "validation in [0.6, 1.0]",
            "success_DUR3_sharpness": "median AE on remaining duration "
                                      "<= 90s (one racing lap: larger "
                                      "errors misplace green-return by "
                                      ">= 1 lap at ~25s/lap pace delta)",
            "verdicts": {
                "SUPPORTED": "DUR1 AND DUR2 AND DUR3",
                "UNDERPOWERED": "otherwise (duration feasibility is not "
                                "refutable from these data; refutation "
                                "NOT_APPLICABLE)",
            },
        },
        "gap_protocol": {
            "question": "EQ3",
            "construction": "D windows + conditional ending-lap "
                            "inclusion (only if EQ5 == SAME_DYNAMICS); "
                            "validation split only",
            "thresholds_unchanged": "median <= 1.0s AND p90 <= 3.0s",
            "uncertainty": "episode-cluster bootstrap percentile CI, "
                           "B=2000, seed=7",
            "SUPPORTED": "point gate passes AND contributing validation "
                         "episodes >= 5 AND 95% CI upper bound of median "
                         "<= 1.0s",
            "UNDERPOWERED": "episodes < 5 OR CI wider (without confident "
                            "violation)",
            "REFUTED": "episodes >= 5 AND 95% CI lower bound of median "
                       "> 1.0s",
        },
        "spread_protocol": {
            "question": "EQ4",
            "construction": "D episode metric (mean ACTIVE / mean PRE, "
                            ">=10-row rule) + conditional ending-lap "
                            "inclusion; validation split only; no "
                            "calibration mixing",
            "thresholds_unchanged": "episode-median ratio in [0.8, 1.25]",
            "uncertainty": "episode-cluster bootstrap percentile CI, "
                           "B=2000, seed=7",
            "SUPPORTED": "point in band AND contributing validation "
                         "episodes >= 5 AND 95% CI within [0.7, 1.4]",
            "UNDERPOWERED": "episodes < 5 OR CI wider",
            "REFUTED": "episodes >= 5 AND 95% CI entirely outside "
                       "[0.8, 1.25]",
        },
        "pit_protocol": {
            "question": "EQ6/EQ7",
            "primary_scope": "usable-29 episodes (D scope)",
            "secondary_scope": "all non-truncated intervals (reported "
                               "separately; exit type does not "
                               "contaminate the VSC token run itself)",
            "full_loss_bar": "out-lap marginal N >= 15 AND in-lap N >= "
                             "30 AND median 95% CI width <= 5s",
            "verdict_if_bar_missed": "PIT_LOSS_INSUFFICIENT_EVIDENCE "
                                     "retained (fail-closed stands)",
            "relevance_gate": "read frozen MC2 engine for forward pit "
                              "mechanics; if MC2 simulates pit stops "
                              "forward from T, pit semantics stay "
                              "mandatory (no T-knowable pit-free scope "
                              "exists without predicting pits)",
        },
        "retained_dimensions": {
            "pace_G1": "re-verify MAE <= 10.0s on validation with "
                       "frozen R_cal=1.272 (no refit)",
            "order_G3": "re-verify rate <= 0.15 on validation",
            "withdrawal_G5": "re-verify |median| <= 5.0s on validation",
            "hard_refutation_bounds": "MAE > 15.0 OR order > 0.30 OR "
                                      "|withdrawal| > 10.0 (D bounds)",
        },
        "minimum_evidence": "per-dimension N bars above; effective N = "
                            "contributing episodes (primary); pairs/laps "
                            "reported as observations, never as "
                            "independent N",
        "uncertainty_method": "episode-cluster bootstrap (resample "
                              "episodes), B=2000, seed=7, percentile CI; "
                              "offline resampling only (not MC2 futures)",
        "no_coverage_gate": True,
        "stochastic_policy": "0 MC2 stochastic futures; bootstrap is "
                             "deterministic given recorded seed",
        "terminal_criteria": {
            "A_VSC_EVIDENCE_RESOLVED": "every mandatory gate SUPPORTED",
            "B_VSC_EVIDENCE_STILL_INSUFFICIENT": "any mandatory "
                "UNDERPOWERED and none REFUTED -> STOP V3.11 coverage "
                "expansion",
            "C_VSC_EVIDENCE_REFUTED": "any mandatory REFUTED -> STOP "
                "V3.11 coverage expansion",
            "D_VSC_EVIDENCE_BLOCKED": "analysis incompletable",
        },
        "mandatory_gates": ["pace", "gap", "spread", "order",
                            "withdrawal", "duration", "pit", "poison",
                            "parity", "fail_closed"],
    }
    protocol["protocol_sha256"] = _sha(protocol)
    _write("evidence_resolution_protocol.json", protocol)
    print(json.dumps({
        "status": "OK", "wall_s": round(time.perf_counter() - t0, 1),
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
