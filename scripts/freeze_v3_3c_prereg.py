"""Freeze V3.3C preregistration (before fitting any C screening model).

Pins A/B identities, families, exact grids/config IDs, feature/task/fold
identities, metrics, bootstrap, temporal/stage/calibration/diversity
definitions, disposition + advancement rules, seed/threads, artifact
layout, firewall, test policy. Hashes the document. Immutable after the
first fit begins.
"""

from __future__ import annotations

import hashlib
import json
import sys

sys.path.insert(0, ".")
from raceintel.model_lab import v3_3b_harness as H  # noqa: E402
from raceintel.model_lab import inner_splits as INNER  # noqa: E402
from raceintel.model_lab import splits as SPLITS  # noqa: E402


def main() -> None:
    contracts = H.verify_contracts()
    from raceintel.experiments.feature_sets import canonical_predictive_names

    names_84 = tuple(canonical_predictive_names())
    names_110 = H.feature_names_110(names_84)
    feature_contract = H.check_feature_contract(names_84, names_110)
    grids = H.candidate_grids()
    spec = {
        "schema_version": "v3.3c-preregistration-v1",
        "a_contract_sha": contracts["contract_sha"],
        "b_prereg_sha": contracts["prereg_sha"],
        "candidate_families": sorted(H.candidate_registry()),
        "exact_grids": {f: [dict(c) for c in cfgs]
                        for f, cfgs in grids.items()},
        "exact_config_ids": {
            f: [H.config_id(f, c) for c in cfgs]
            for f, cfgs in grids.items()},
        "complexity_ordering": {
            f: [list(H.complexity_rank(f, c)) for c in cfgs]
            for f, cfgs in grids.items()},
        "feature_identity": {
            "primary_arm": H.ARM_PRIMARY, "primary_count": 110,
            "diagnostic_arm": H.ARM_CONTROL, "diagnostic_count": 84,
            "feature_hash": feature_contract["feature_hash"]},
        "task_identity": {"task": "winner", "label": "is_winner",
                          "semantics": "INDEPENDENT_BINARY",
                          "probabilities": "RAW, never field-normalized"},
        "outer_folds": {
            f: {"train": list(SPLITS.get_split(f).train_seasons),
                "validate": list(SPLITS.get_split(f).validation_seasons)}
            for f in H.OUTER_FOLDS},
        "inner_folds": {
            f: [s.to_dict() for s in INNER.resolve_inner_splits(f)]
            for f in H.OUTER_FOLDS},
        "primary_metric": "race_macro_log_loss",
        "secondary_metrics": ["brier", "roc_auc", "pr_auc", "ece", "top_1",
                              "top_3", "state_pooled_log_loss"],
        "bootstrap_method": "paired race-level resampling with replacement; "
                            "statistic = mean(candidate LL - baseline LL); "
                            "percentile CI; states never bootstrapped",
        "bootstrap_replicates": 2000,
        "bootstrap_seed": 42,
        "temporal_consistency": {
            "inputs": ["D1 delta", "D2 delta", "D3 delta"],
            "classes": ["CONSISTENT_IMPROVEMENT", "MIXED",
                        "CONSISTENT_REGRESSION"],
            "rule": "signs with 1e-12 deadband; no every-fold-must-improve "
                    "veto; magnitude discussed, not just signs"},
        "stage_definitions": "race_progress_frac thirds EARLY/MID/LATE; "
                             "thin slices carry no strong claims",
        "calibration_diagnostics": ["ECE", "reliability bins",
                                    "over/underconfidence pattern",
                                    "extreme probability frequency", "Brier"],
        "calibration_rule": "RAW primary; NO calibration fitting in C",
        "diversity_diagnostics": ["prediction correlation",
                                  "residual correlation",
                                  "per-race delta correlation",
                                  "mean absolute probability gap",
                                  "top-1 disagreement rate",
                                  "high-confidence disagreement"],
        "disposition_rules": {
            "enum": ["KEEP_PRIMARY_CANDIDATE", "KEEP_DIVERSITY_CANDIDATE",
                     "HOLD_FOR_CALIBRATION", "REJECT_NO_IMPROVEMENT",
                     "REJECT_TEMPORAL_INSTABILITY",
                     "REJECT_PROBABILITY_QUALITY",
                     "REJECT_COMPLEXITY_WITHOUT_VALUE",
                     "REJECT_CONTRACT_INCOMPATIBLE"],
            "logistic": "baseline/control; never artificially rejected",
            "evidence": "C pre-2025 evidence only"},
        "advancement_rules": {"max_non_baseline": 3,
                              "rule": "credible primary improvement, "
                                      "credible diversity value, or "
                                      "calibration-worthy discrimination; "
                                      "fewer/zero is valid"},
        "random_seed": H.SEED,
        "thread_policy": dict(H.THREAD_POLICY),
        "artifact_layout": "results/v3/v3_3c/*.json + "
                           "results/v3/v3_3c_candidate_screening.json; "
                           "OOF parquets under ignored data/v3/v3_3c/",
        "firewall_2025": {"season": 2025, "status": "SEALED",
                          "requirement": "2025_CONTACT = NONE before, "
                                         "during, and after C"},
        "test_policy": "tests/test_v3_3c_screening.py + A/B tests + "
                       "relevant Model Lab/V3.1 tests; "
                       "FULL_TIER1 = NOT_REQUIRED_RESEARCH_EXECUTION_ONLY",
        "library_versions": H.library_versions(),
    }
    blob = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    spec["preregistration_identity"] = hashlib.sha256(
        blob.encode("utf-8")).hexdigest()
    dest = H.B_PREREG_PATH.parent.parent / "v3_3c" / "preregistration.json"
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(spec, indent=1, sort_keys=True) + "\n")
    print(f"c_preregistration_identity: {spec['preregistration_identity']}")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
