"""V3.7D preregistration: generate evaluation_protocol.json BEFORE results."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_7d"
OUT.mkdir(parents=True, exist_ok=True)

protocol = {
    "schema": "v3.7d-evaluation-protocol-v1",
    "population": {
        "source": "V3.6D eligible anchors (SIMULATION_CAPABLE, 71 states)",
        "seasons": [2018, 2019, 2020, 2021, 2022, 2023, 2024],
        "excludes_2025": True,
        "selection": "ALL 71 eligible (no subsampling; V3.6D sampled pre-V3.7)",
    },
    "sampling": {"rule": "exhaust eligible population in sample.json order"},
    "target_rule": "V3.6D anchor driver (factual T anchor; no post-T input)",
    "rival_rule": {
        "rule": "nearest valid factual position rival (|pos-target| min, pos != target)",
        "tie_break": "lower driver_id alphabetical",
        "unavailable": "skip rival outcomes, record RIVAL_UNAVAILABLE",
    },
    "horizons": [1, 2, 3, 5],
    "long_horizon": {"n": 8, "condition": "N <= remaining_laps - 1 else skip"},
    "compound_policy": {
        "horizon_matrix": "MEDIUM (single neutral compound)",
        "override_probe": "N=2 SOFT (exercises override machinery once)",
        "caveat": "no compound performance ranking (frozen pace limitation)",
    },
    "multi_stop_template": {"first": {"n": 2, "compound": "MEDIUM"},
                            "second": {"n": 8, "compound": "HARD"},
                            "condition": "both N <= remaining_laps - 1 else skip"},
    "multi_driver_template": {"second_target": "rival rule",
                              "plans": "PIT N=2 MEDIUM each",
                              "limits": "no stacking/traffic/team-order claims"},
    "plan_vs_plan": [{"base": "N=2 MEDIUM", "alt": "N=5 MEDIUM"},
                     {"base": "single N=2", "alt": "multi-stop template"}],
    "simulation_counts": {"production": 5000, "research": [1000, 2500]},
    "root_seeds": {"production": 20240101, "research": [7, 99]},
    "stability_subset": "first 12 anchors by sample.json order",
    "reproducibility": {"cases": 4, "required": "4/4 exact"},
    "parity_subset": "first 8 anchors by sample.json order (N=1/N=2 legacy)",
    "sentinel_subset": "first 12 anchors by sample.json order",
    "metrics": ["win/podium/top5/top10 deltas", "expected-finish delta",
                "downside", "P(ahead) delta", "pit count", "position gain",
                "lifecycle rates", "pair counts"],
    "pathology_definitions": {
        "P1": "same-input nondeterminism",
        "P2": "post-T historical dependency",
        "P3": "complete-pair accounting violation",
        "P4": "position-gain sign/invariant failure",
        "P5": "ahead-of-rival aggregate mismatch",
        "P6": "pit-count aggregate mismatch",
        "P7": "illegal lifecycle transition",
        "P8": "plan input-order dependence",
        "P9": "multi-driver target-order dependence",
        "P10": "unexpected unsupported/invalid after eligibility",
        "P11": "NaN/inf/non-finite scientific metric",
        "P12": "probability outside [0,1]",
        "P13": "finish distribution mass violation",
        "P14": "comparison orientation inversion",
        "P15": "reference semantics drift",
        "P16": "V3.5/historical-result dependency",
        "P17": "legacy V3.6 N=1/N=2 parity regression",
    },
    "refinement_gate": {
        "REFINEMENT_NOT_WARRANTED_requires": [
            "zero blocking invariants", "repro 4/4", "temporal intact",
            "pairs intact", "parity intact", "no recomputation mismatch",
            "no order dependence", "no P11/P12", "nonzero usable support",
            "explainable lifecycle", "no evidence-backed correction needed"],
        "REFINEMENT_WARRANTED_requires": "concrete reproducible issue fixable without A/B change",
        "BLOCKING_DEFECT": "leakage/pairing corruption/contract mismatch/parity failure/invariant failure",
    },
    "stop_conditions": ["reproducibility failure", "parity failure",
                        "poison failure", "pair accounting failure",
                        "gain orientation failure"],
}

blob = json.dumps(protocol, sort_keys=True, separators=(",", ":")).encode()
identity = hashlib.sha256(blob).hexdigest()
doc = dict(protocol)
doc["protocol_hash"] = identity
(OUT / "evaluation_protocol.json").write_text(
    json.dumps(doc, sort_keys=True, indent=2) + "\n")
print(identity)
