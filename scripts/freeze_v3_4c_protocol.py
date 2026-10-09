"""V3.4C: freeze the selection protocol (one-shot writer).

Encodes V3.4A advancement philosophy as executable checks WITHOUT any
new numeric improvement threshold. Must run BEFORE any disposition.
Refuses if disposition artifacts already exist.
"""
import hashlib
import json
from pathlib import Path

A_SHA = "d6b12074db9895844c28c05c78baf56c113d63c33d685c5913c92ebb5036b352"
B_SHA = "64ca2d2911e63b1487334ca72fc024f47d59868f168b60d7d391d31df82b5b26"
OUT = Path("results/v3/v3_4c")

PROTOCOL = {
    "schema_version": "v3.4c-selection-protocol-v1",
    "a_contract_identity": A_SHA,
    "b_prereg_identity": B_SHA,
    "candidate_set": {
        "blends": [round(i / 10, 1) for i in range(11)],
        "stacker": "temporal expanding-window (D1 fallback)",
        "reference": "logistic w=0.0 (BASELINE_CONTROL, not selectable)",
        "closed": True,
    },
    "primary_metric": "race_macro_log_loss, delta vs Logistic (lower better)",
    "candidacy": "pooled delta < 0 (directional; NOT a numeric threshold)",
    "race_bootstrap": {"unit": "race", "replicates": 2000, "seed": 42,
                       "support_labels": ["CLEAR_SUPPORT", "BORDERLINE_SUPPORT",
                                          "UNCERTAIN", "REGRESSION"]},
    "temporal_criteria": {
        "fold_support": "count of D1/D2/D3 folds with delta < 0; "
                        ">=2 required for ROBUST consideration",
        "instability": "gain concentrated in one fold while others "
                       "regress -> REJECT_TEMPORAL_INSTABILITY",
    },
    "stage_criteria": {
        "cells": "9 fold x stage cells; report count negative; "
                 "unanimity is strong supporting evidence",
    },
    "probability_quality_criteria": {
        "brier_ece": "pooled deltas must not be materially positive",
        "worst_race": "descriptive guard against tail damage",
        "rule": "LL gain via worse Brier/ECE -> REJECT_PROBABILITY_QUALITY",
    },
    "neighbor_robustness": {
        "window": "+/-0.1 on frozen grid",
        "basin": "both neighbors pooled-negative with same fold-sign "
                 "pattern; penalize isolated/edge/exact-precision optima",
    },
    "complexity_preference": {
        "rule": "blend preferred; stacker advances only on materially "
                "stronger AND robust evidence",
        "stacker_handicap": "D1 unevaluable + D2/D3 instability weigh "
                            "against",
    },
    "tie_handling": "indistinguishable neighbors -> more conservative "
                    "(smaller w; less departure from Logistic)",
    "firewall_2025": {"contact": "NONE",
                      "forbidden": "labels/predictions/metrics/ensemble use"},
    "allowed_dispositions": [
        "BASELINE_CONTROL", "ROBUST_CANDIDATE", "SELECTED_DEVELOPMENT_RECIPE",
        "REJECT_NO_IMPROVEMENT", "REJECT_TEMPORAL_INSTABILITY",
        "REJECT_PROBABILITY_QUALITY", "REJECT_COMPLEXITY_WITHOUT_VALUE"],
    "stacker_dispositions": [
        "KEEP_ENSEMBLE_PRIMARY", "KEEP_ENSEMBLE_TIE_BREAK",
        "REJECT_NO_IMPROVEMENT", "REJECT_TEMPORAL_INSTABILITY",
        "REJECT_PROBABILITY_QUALITY", "REJECT_COMPLEXITY_WITHOUT_VALUE"],
    "selection_cap": "max ONE SELECTED_DEVELOPMENT_RECIPE; "
                     "NO_ENSEMBLE valid",
    "no_numeric_threshold": True,
}


def main() -> None:
    if list(OUT.glob("*disposition*.json")) or \
            (OUT / "selected_development_candidate.json").exists():
        raise RuntimeError(
            "disposition exists; protocol immutable after disposition")
    blob = json.dumps(PROTOCOL, sort_keys=True, separators=(",", ":"))
    doc = dict(PROTOCOL)
    doc["protocol_identity"] = hashlib.sha256(blob.encode()).hexdigest()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "selection_protocol.json").write_text(
        json.dumps(doc, indent=1, sort_keys=True) + "\n")
    print("protocol_identity:", doc["protocol_identity"])


if __name__ == "__main__":
    main()
