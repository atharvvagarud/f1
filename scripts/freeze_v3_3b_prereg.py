"""Freeze V3.3B preregistration (before any candidate smoke benchmark).

Verifies the V3.3A contract hash, pins families/feature identity/folds/
grids/seeds/thread policy/metric/tie policy/OOF schema/smoke scope/2025
firewall/artifact layout/test policy, hashes the document, and writes
results/v3/v3_3b/preregistration.json. Grids are frozen once smoke begins.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

sys.path.insert(0, ".")
from raceintel.model_lab import v3_3b_harness as H  # noqa: E402


def main() -> None:
    a = H.verify_a_contract()
    from raceintel.features.dynamics import contract as DYN
    from raceintel.experiments.feature_sets import canonical_predictive_names

    names_84 = tuple(canonical_predictive_names())
    names_110 = H.feature_names_110(names_84)
    feature_contract = H.check_feature_contract(names_84, names_110)
    registry = H.candidate_registry()
    grids = H.candidate_grids()
    grid_ids = {fam: [H.config_id(fam, c) for c in cfgs]
                for fam, cfgs in grids.items()}
    complexity = {fam: [H.complexity_rank(fam, c) for c in cfgs]
                  for fam, cfgs in grids.items()}
    inner_layout = {fold: [{"inner_fold_id": s.inner_fold_id,
                            "train_seasons": list(s.train_seasons),
                            "validation_seasons": list(s.validation_seasons)}
                           for s in __import__(
                               "raceintel.model_lab.inner_splits",
                               fromlist=["resolve_inner_splits"]
                           ).resolve_inner_splits(fold)]
                    for fold in H.OUTER_FOLDS}
    spec = {
        "schema_version": H.B_PREREG_SCHEMA,
        "a_contract_sha": a["contract_sha"],
        "a_contract_schema": a["schema_version"],
        "task": {"name": H.TASK, "label": "is_winner",
                 "semantics": "INDEPENDENT_BINARY",
                 "rule": "RAW probabilities; never field-normalized"},
        "candidate_families": sorted(registry),
        "feature_identity": {
            "primary_arm": H.ARM_PRIMARY,
            "primary_count": H.N_110,
            "diagnostic_arm": H.ARM_CONTROL,
            "diagnostic_count": H.N_84,
            "core_count": H.N_CORE,
            "feature_hash": feature_contract["feature_hash"],
            "sidecar_non_core_excluded": feature_contract[
                "sidecar_non_core_excluded"],
        },
        "outer_folds": {fold: {
            "train": list(__import__(
                "raceintel.model_lab.splits",
                fromlist=["get_split"]).get_split(fold).train_seasons),
            "validate": list(__import__(
                "raceintel.model_lab.splits",
                fromlist=["get_split"]).get_split(fold).validation_seasons)}
            for fold in H.OUTER_FOLDS},
        "inner_folds": inner_layout,
        "candidate_grids": {fam: [dict(c) for c in cfgs]
                            for fam, cfgs in grids.items()},
        "candidate_grid_ids": grid_ids,
        "grid_size_bound": 12,
        "grid_sizes": {fam: len(cfgs) for fam, cfgs in grids.items()},
        "complexity_ordering": {
            fam: [list(r) for r in ranks]
            for fam, ranks in complexity.items()},
        "seed": H.SEED,
        "thread_policy": dict(H.THREAD_POLICY),
        "primary_metric": "race_macro_log_loss",
        "tie_policy": {"tolerance": H.TIE_TOLERANCE,
                       "rule": "difference <= 1e-6 -> simpler preregistered "
                               "configuration wins"},
        "oof_schema": {"columns": list(H.OOF_COLUMNS),
                       "optional": ["baseline_probability"],
                       "storage": "data/v3/v3_3b/*.parquet (ignored, "
                                  "never committed)"},
        "smoke_test_scope": {
            "label": "HARNESS_SMOKE_ONLY",
            "runs": ["logistic_regression C=0.01 on D1 (parity control)",
                     "one hist_gradient_boosting config on D1",
                     "one extra_trees config on D1",
                     "one xgboost config on D1"],
            "forbidden": ["ranking candidates", "eliminating candidates",
                          "calibration", "ensembling", "full screening"]},
        "holdout_2025_firewall": {
            "season": 2025, "status": "SEALED",
            "mechanism": "development-only resolvers + "
                         "assert_development_fold + season scans; "
                         "HOLDOUT/2025/FINAL_FIT raise ProtectedHoldoutError"},
        "artifact_layout": "results/v3/v3_3b/*.json (+ machine summary "
                           "results/v3/v3_3b_screening_harness.json)",
        "test_policy": "tests/test_v3_3b_harness.py + A contract tests + "
                       "relevant Model Lab / V3.1 dynamics / M6 tests; "
                       "FULL_TIER1 = NOT_REQUIRED_RESEARCH_INFRA_ONLY",
        "library_versions": H.library_versions(),
        "budget": {"max_wall_per_family_s": 3600, "max_total_wall_s": 7200},
    }
    blob = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    spec["preregistration_identity"] = hashlib.sha256(
        blob.encode("utf-8")).hexdigest()
    dest = H.B_PREREG_PATH
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(spec, indent=1, sort_keys=True) + "\n")
    print(f"preregistration_identity: {spec['preregistration_identity']}")
    print(f"wrote {dest}")
    check = H.verify_prereg()
    assert check["prereg_sha"] == spec["preregistration_identity"]
    print("B preregistration hash verified.")


if __name__ == "__main__":
    main()
