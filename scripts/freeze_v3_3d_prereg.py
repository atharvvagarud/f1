"""Freeze V3.3D preregistration (before ANY D fit).

Pins A/B/C identities, ET+XGB candidate set, exact D refinement grids
(with IDs/rationales/complexity), calibration methods + temporal data
construction + support gates + selection rule, metrics, policies,
final-fit recipe policy, firewall, artifact layout, test policy. Hashes
the document. Immutable after the first D fit.
"""

from __future__ import annotations

import hashlib
import json
import sys

sys.path.insert(0, ".")
from raceintel.model_lab import v3_3b_harness as H  # noqa: E402
from raceintel.model_lab import v3_3d_refinement as D  # noqa: E402
from raceintel.model_lab import inner_splits as INNER  # noqa: E402
from raceintel.model_lab import splits as SPLITS  # noqa: E402


def main() -> None:
    contracts = H.verify_contracts()
    c_prereg = json.loads(
        __import__("pathlib").Path(
            "results/v3/v3_3c/preregistration.json").read_text())
    from raceintel.experiments.feature_sets import canonical_predictive_names

    names_84 = tuple(canonical_predictive_names())
    names_110 = H.feature_names_110(names_84)
    feature_contract = H.check_feature_contract(names_84, names_110)
    c_grids = H.candidate_grids()
    grids = D.d_grids()
    for fam, cfgs in grids.items():
        assert len(cfgs) <= 6, f"D grid bound violated: {fam}"
        live_ids = [D.d_config_id(fam, c) for c in cfgs]
        c_ids = [H.config_id(fam, c) for c in c_grids[fam]]
        assert not (set(live_ids) & set(c_ids)), \
            f"D grid overlaps C grid: {fam}"
    spec = {
        "schema_version": "v3.3d-preregistration-v1",
        "a_contract_sha": contracts["contract_sha"],
        "b_prereg_sha": contracts["prereg_sha"],
        "c_prereg_sha": c_prereg["preregistration_identity"],
        "candidate_set": list(D.D_FAMILIES),
        "closed": {"hist_gradient_boosting": "C REJECT_NO_IMPROVEMENT",
                   "logistic_regression": "control, not refined in D"},
        "feature_identity": {
            "primary_arm": H.ARM_PRIMARY, "primary_count": 110,
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
        "c_raw_references": {
            "selected_configs": json.loads(__import__("pathlib").Path(
                "results/v3/v3_3c/selected_configs.json").read_text())[
                "selected"],
            "oof_identities": json.loads(__import__("pathlib").Path(
                "results/v3/v3_3c/oof_identities.json").read_text())["oof"],
            "rule": "read-only; never overwritten; D labels distinguish "
                    "C_RAW / D_REFINED_RAW / D_CALIBRATED"},
        "refinement_grids": {
            fam: [{"id": D.d_config_id(fam, c),
                   "hyperparameters": {k: v for k, v in c.items()
                                       if not k.startswith("_")},
                   "rationale": c["_rationale"],
                   "complexity_rank": list(D.d_complexity_rank(fam, c))}
                  for c in cfgs]
            for fam, cfgs in grids.items()},
        "refinement_bound": "≤6 NEW configs/family; C configs are references; "
                            "no second round",
        "calibration_methods": ["RAW", "sigmoid", "isotonic"],
        "calibration_data": "cross-fitted inner-val predictions inside outer "
                            "TRAIN history only; earlier inner-val races fit, "
                            "later inner-val races select; winners refit on "
                            "full calibration set; outer validation never "
                            "fits/selects",
        "calibration_support_gates": {
            "isotonic": {"min_rows": D.ISOTONIC_MIN_ROWS,
                         "min_positives": D.ISOTONIC_MIN_POSITIVES,
                         "min_unique": D.ISOTONIC_MIN_UNIQUE},
            "sigmoid": {"min_rows": D.SIGMOID_MIN_ROWS,
                        "min_positives": D.SIGMOID_MIN_POSITIVES,
                        "min_unique": D.SIGMOID_MIN_UNIQUE},
            "inadequate": "NOT_RUN_INSUFFICIENT_SUPPORT"},
        "calibration_selection_rule": "calibrated wins iff LL gain > 1e-4 "
                                      "AND no Brier harm on train-history "
                                      "selection races; ties prefer "
                                      "RAW > SIGMOID > ISOTONIC; "
                                      "deterministic",
        "primary_metric": "race_macro_log_loss",
        "secondary_metrics": ["brier", "ece", "roc_auc", "pr_auc", "top_1",
                              "top_3"],
        "bootstrap_policy": "paired race-level, B=2000, seed=42, 95% CI",
        "diversity_policy": "best admissible PRE-2025 representation per "
                            "family vs V3.1B + ET vs XGB; useful "
                            "disagreement required (Part S gate)",
        "advancement_policy": {"max_challengers": 2, "plus_baseline": True,
                               "rule": "credible standalone OR credible "
                                       "useful diversity; zero is valid"},
        "final_fit_recipe_policy": {
            "training_years": "2018-2024",
            "rule": "family + hyperparameters + preprocessing + features + "
                    "seed/threads + calibration method + exact "
                    "calibration-training procedure frozen BEFORE 2025"},
        "random_seed": H.SEED,
        "thread_policy": dict(H.THREAD_POLICY),
        "firewall_2025": {"season": 2025, "status": "SEALED",
                          "requirement": "2025_CONTACT = NONE"},
        "artifact_layout": "results/v3/v3_3d/*.json + "
                           "results/v3/v3_3d_refinement_calibration.json; "
                           "OOF under ignored data/v3/v3_3d/",
        "test_policy": "tests/test_v3_3d_refinement.py + A/B/C tests + "
                       "calibration/tuning/metric tests; "
                       "FULL_TIER1 = NOT_REQUIRED_RESEARCH_EXECUTION_ONLY",
        "library_versions": H.library_versions(),
    }
    blob = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    spec["preregistration_identity"] = hashlib.sha256(
        blob.encode("utf-8")).hexdigest()
    dest = __import__("pathlib").Path(
        "results/v3/v3_3d/preregistration.json")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(spec, indent=1, sort_keys=True) + "\n")
    print(f"d_preregistration_identity: {spec['preregistration_identity']}")
    print(f"wrote {dest}")


if __name__ == "__main__":
    main()
