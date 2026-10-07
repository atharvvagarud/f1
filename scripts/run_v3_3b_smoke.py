"""V3.3B smoke experiment (HARNESS_SMOKE_ONLY -- NOT full screening).

Proves materialization, fit, predict_proba, metrics, OOF serialization,
comparison, determinism, provenance for all four families on the D1
development fold, plus the logistic parity gate vs V3.1B/C. Writes every
Part-AC result JSON under results/v3/v3_3b/ and OOF parquets under
data/v3/v3_3b/ (ignored). Never ranks or eliminates candidates.
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from raceintel.model_lab import aggregation as AGG  # noqa: E402
from raceintel.model_lab import data as DATA  # noqa: E402
from raceintel.model_lab import v3_3b_harness as H  # noqa: E402
from raceintel.model_lab import v3_dynamics_experiment as V3C  # noqa: E402

OUT = Path("results/v3/v3_3b")
BASELINE_PARQUET = Path(
    "data/v3/v3_1c/pred_ALL_84_PLUS_V3_1_DYNAMICS_CORE__D1.parquet")
FOLD = "D1"

SMOKE_CONFIGS = {
    "logistic_regression": {"C": 0.01},
    "hist_gradient_boosting": {"learning_rate": 0.1, "max_leaf_nodes": 31,
                               "min_samples_leaf": 20},
    "extra_trees": {"max_features": "sqrt", "min_samples_leaf": 1,
                    "max_depth": None},
    "xgboost": {"learning_rate": 0.1, "max_depth": 3, "min_child_weight": 1},
}


def write(name: str, payload: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / name
    dest.write_text(json.dumps(payload, indent=1, sort_keys=True,
                               default=str) + "\n")
    return dest


def main() -> None:
    contracts = H.verify_contracts()
    print(f"A={contracts['contract_sha'][:12]} B={contracts['prereg_sha'][:12]}")
    t0 = time.perf_counter()

    # -- 110-column materialization (Parts D-F) -------------------------
    augmented, plain = V3C.load_joined_frame()
    names_84 = V3C.v3_feature_names(V3C.ARM_A)
    names_110 = H.feature_names_110(names_84)
    feature_contract = H.check_feature_contract(names_84, names_110)
    write("feature_contract_110.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts,
           **feature_contract,
           "join": "state_id one_to_one; row-position join forbidden"})

    # Materialization parity vs V3.1 semantics (Part E): eligible rows,
    # labels, state identities, 84-prefix bytes, CORE values, masks.
    ds_b = V3C.materialize_v3(augmented, FOLD, V3C.ARM_B, names_110)
    ds_a = V3C.materialize_v3(augmented, FOLD, V3C.ARM_A, names_84)
    canon = DATA.load_canonical()
    mask_col = "eligible_is_winner"
    parity = {
        "label": "HARNESS_SMOKE_ONLY", **contracts,
        "fold": FOLD,
        "train_eligible": int(ds_b.train_counts["eligible"]),
        "val_eligible": int(ds_b.validation_counts["eligible"]),
        "m0_train_eligible": 88123, "m0_val_eligible": 23577,
        "counts_match_m0": bool(
            ds_b.train_counts["eligible"] == 88123
            and ds_b.validation_counts["eligible"] == 23577),
        "labels_match_canonical": bool(
            ds_b.y_train.equals(
                canon.frame.loc[ds_b.y_train.index]["is_winner"])
            and ds_b.y_validation.equals(
                canon.frame.loc[ds_b.y_validation.index]["is_winner"])),
        "state_identity_unique": bool(
            ds_b.train_metadata["state_id"].is_unique
            and ds_b.validation_metadata["state_id"].is_unique),
        "prefix_84_equal": bool(
            ds_b.X_train[list(names_84)].equals(
                canon.frame.loc[ds_b.X_train.index, list(names_84)])),
        "masks_match_arm_a": bool(
            ds_b.train_metadata["state_id"].equals(
                ds_a.train_metadata["state_id"])
            and ds_b.validation_metadata["state_id"].equals(
                ds_a.validation_metadata["state_id"])),
    }
    write("feature_materialization_parity.json", parity)
    write("control_arm_parity.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts, "fold": FOLD,
           "arm": H.ARM_CONTROL, "n_features": len(names_84),
           "train_eligible": int(ds_a.train_counts["eligible"]),
           "val_eligible": int(ds_a.validation_counts["eligible"]),
           "row_identity_matches_primary": bool(parity["masks_match_arm_a"])})

    # -- registry / grids / folds (Parts G, L-N) ------------------------
    registry = H.candidate_registry()
    write("candidate_registry.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts,
           "families": sorted(registry), "registry": registry})
    grids = H.candidate_grids()
    write("candidate_grids.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts,
           "grids": grids,
           "grid_ids": {f: [H.config_id(f, c) for c in cfgs]
                        for f, cfgs in grids.items()},
           "sizes": {f: len(c) for f, c in grids.items()},
           "bound_ok": all(len(c) <= 12 for c in grids.values()),
           "frozen_logistic_C_present": any(
               c.get("C") == 0.01 for c in grids["logistic_regression"])})
    from raceintel.model_lab import inner_splits as INNER
    from raceintel.model_lab import splits as SPLITS
    write("inner_fold_contract.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts,
           "objective": "mean inner race-macro log loss",
           "tie_tolerance": H.TIE_TOLERANCE,
           "layout": {f: [s.to_dict() for s in INNER.resolve_inner_splits(f)]
                      for f in H.OUTER_FOLDS}})
    write("outer_fold_contract.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts,
           "folds": {f: SPLITS.get_split(f).to_dict()
                     for f in H.OUTER_FOLDS},
           "holdout_2025_reachable": False})

    # -- smoke fits: one config per family on D1 (Part V) ----------------
    results, oof_paths, fit_times, artifact_sizes = {}, {}, {}, {}
    for family, cfg in SMOKE_CONFIGS.items():
        t_fit = time.perf_counter()
        res = H.run_outer(augmented, plain, FOLD, family, cfg,
                          feature_arm=H.ARM_PRIMARY,
                          feature_names=names_110)
        fit_times[family] = round(time.perf_counter() - t_fit, 3)
        results[family] = res
        ll = res["metrics"]["log_loss"]["race_macro"]["value"]
        print(f"{family}: race-macro LL={ll:.6f} "
              f"fit={fit_times[family]}s")

    # -- logistic parity gate vs V3.1B/C (Part W) ------------------------
    base = pd.read_parquet(BASELINE_PARQUET)
    logr = results["logistic_regression"]
    harness_p = np.asarray(logr["predictions"], dtype=float)
    base_ordered = base.set_index("state_id").loc[logr["state_ids"]]
    base_p = base_ordered["y_pred"].to_numpy(dtype=float)
    max_abs = float(np.max(np.abs(harness_p - base_p)))
    ll_h = float(logr["metrics"]["log_loss"]["race_macro"]["value"])
    brier_h = float(logr["metrics"]["brier"]["race_macro"]["value"])
    y_true = np.asarray(logr["y_true"], dtype=float)
    race_ids = np.asarray(logr["race_ids"])
    ll_b = float(AGG.race_macro(
        base_ordered["y_true"].to_numpy(dtype=float), base_p,
        base_ordered["race_id"].astype(str).to_numpy(),
        "log_loss")["value"])
    brier_b = float(AGG.race_macro(
        base_ordered["y_true"].to_numpy(dtype=float), base_p,
        base_ordered["race_id"].astype(str).to_numpy(), "brier")["value"])
    topk_h = logr["topk"]["winner_top_k"]
    parity_gate = {
        "label": "HARNESS_SMOKE_ONLY", **contracts,
        "fold": FOLD, "tolerance_prob": 1e-9, "tolerance_ll": 1e-9,
        "prediction_max_abs_difference": max_abs,
        "race_macro_ll_harness": ll_h,
        "race_macro_ll_baseline": ll_b,
        "race_macro_ll_difference": abs(ll_h - ll_b),
        "brier_harness": brier_h, "brier_baseline": brier_b,
        "brier_difference": abs(brier_h - brier_b),
        "top1_harness": (topk_h.get("accuracy") or {}).get("top1"),
        "gate": "PASS" if max_abs <= 1e-9 and abs(ll_h - ll_b) <= 1e-9
        else "FAIL",
    }
    write("logistic_parity.json", parity_gate)
    print(f"parity gate: {parity_gate['gate']} "
          f"(max_abs={max_abs:.3e}, dLL={abs(ll_h - ll_b):.3e})")

    # -- OOF frames + comparison + diversity (Parts O-R) -----------------
    oof_report = {}
    for family, res in results.items():
        frame = H.build_oof_frame(res, FOLD, H.ARM_PRIMARY,
                                  baseline_proba=(base_p if family
                                                  != "logistic_regression"
                                                  else None))
        # logistic control: baseline column would duplicate itself; store
        # the canonical aligned baseline table once instead.
        path = H.write_oof_parquet(
            frame, f"oof_{family}__{FOLD}.parquet")
        oof_paths[family] = str(path)
        artifact_sizes[family] = round(path.stat().st_size / 1024, 1)
        oof_report[family] = H.validate_oof_frame(
            frame, expect_baseline=("baseline_probability"
                                    in frame.columns))
    base_table = pd.DataFrame({
        "state_id": list(logr["state_ids"]),
        "season": [int(s) for s in
                   logr["dataset"].validation_metadata["season"]],
        "race_id": list(logr["dataset"].validation_metadata["race_id"]
                        .astype(str)),
        "driver_id": list(logr["dataset"].validation_metadata["driver_id"]
                          .astype(str)),
        "target": y_true, "fold": [FOLD] * len(y_true),
        "stage": list(logr["stage_labels"]),
        "feature_arm": [H.ARM_PRIMARY] * len(y_true),
        "model_family": ["v3_1b_baseline"] * len(y_true),
        "model_config_id": ["C=0.01"] * len(y_true),
        "probability": base_p})
    H.write_oof_parquet(base_table, f"oof_baseline__{FOLD}.parquet")
    write("oof_contract.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts,
           "columns": list(H.OOF_COLUMNS),
           "optional": ["baseline_probability"],
           "frames": oof_report,
           "storage": "data/v3/v3_3b/*.parquet (ignored)"})
    base_per_race = AGG.race_macro(
        y_true, base_p, race_ids, "log_loss")["per_race"]
    comparisons = {}
    for family, res in results.items():
        cand_per_race = res["metrics"]["log_loss"]["race_macro"]["per_race"]
        fam_oof = pd.read_parquet(oof_paths[family])
        comp = H.race_comparison(base_per_race, cand_per_race,
                                 baseline_oof=base_table,
                                 candidate_oof=fam_oof)
        comparisons[family] = comp
    write("comparison_contract.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts,
           "method": "paired race bootstrap B=2000 seed=42 95% CI",
           "comparisons": comparisons})
    write("metric_contract.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts,
           "primary": "race_macro_log_loss",
           "implementation": "raceintel.model_lab.metrics + aggregation "
                             "(reused, no candidate exceptions)",
           "metrics": {fam: {
               m: res["metrics"][m]["race_macro"]["value"]
               for m in ("log_loss", "brier", "roc_auc", "pr_auc")}
               for fam, res in results.items()}})
    write("diversity_support.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts,
           "families": {fam: comp.get("diversity", {})
                        for fam, comp in comparisons.items()}})

    # -- inner tuning proof on D1 logistic (Part M; outer consumes once) --
    tune_res = H.tune_family(augmented, "logistic_regression", FOLD,
                             feature_arm=H.ARM_PRIMARY,
                             feature_names=names_110)
    sel = tune_res["selection"]
    print(f"inner tune D1 logistic: selected {sel['selected_key']} "
          f"(mean={sel['selected_mean']:.6f})")

    # -- firewall validation (Part S) ------------------------------------
    firewall = {"label": "HARNESS_SMOKE_ONLY", **contracts}
    for bad in ("HOLDOUT", "2025", "FINAL_FIT"):
        try:
            H.assert_development_fold(bad)
            firewall[bad] = "NOT_BLOCKED"
        except Exception as exc:  # noqa: BLE001 -- record outcome
            firewall[bad] = f"BLOCKED:{type(exc).__name__}"
    try:
        H.tune_family(augmented, "logistic_regression", "HOLDOUT")
        firewall["tune_holdout"] = "NOT_BLOCKED"
    except Exception as exc:  # noqa: BLE001
        firewall["tune_holdout"] = f"BLOCKED:{type(exc).__name__}"
    write("firewall_validation.json", firewall)

    # -- provenance (Part T) ----------------------------------------------
    import subprocess as sp
    try:
        commit = sp.run(["git", "rev-parse", "HEAD"], capture_output=True,
                        text=True).stdout.strip()
    except Exception:
        commit = "unknown"
    write("provenance_contract.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts,
           "envelopes": {
               fam: H.provenance_envelope(
                   family=fam, config=SMOKE_CONFIGS[fam], fold_id=FOLD,
                   feature_arm=H.ARM_PRIMARY, feature_names=names_110,
                   dataset=results[fam]["dataset"], code_commit=commit)
               for fam in results}})

    # -- determinism + serialization (Parts U, Y) -------------------------
    schema = DATA.feature_schema(augmented.frame, list(names_110))
    det, ser = {}, {}
    for family, cfg in SMOKE_CONFIGS.items():
        res = results[family]
        det[family] = H.determinism_check(
            family, cfg, res["dataset"].X_train, res["dataset"].y_train,
            schema, res["dataset"].X_validation)
        ser[family] = H.serialization_roundtrip(
            family, cfg, res["fitted_preprocessor"], res["estimator"],
            res["dataset"].X_validation)
        print(f"{family}: det_diff={det[family]['max_abs_probability_difference']:.3e} "
              f"ser_diff={ser[family]['max_abs_probability_difference']:.3e}")
    write("determinism.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts, "checks": det})
    write("serialization.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts, "roundtrips": ser})

    # -- failure behavior spot-checks (Part Z) -----------------------------
    failures = {}
    cases = {
        "wrong_feature_count": lambda: H.run_outer(
            augmented, plain, FOLD, "logistic_regression", {"C": 0.01},
            feature_names=tuple(list(names_110)[:109])),
        "unknown_family": lambda: H.build_estimator("lightgbm", {}),
        "unknown_config_namespace": lambda: H.build_estimator(
            "logistic_regression", {"C": 0.01, "bogus": 1}),
        "holdout_fold": lambda: H.run_outer(
            augmented, plain, "HOLDOUT", "logistic_regression",
            {"C": 0.01}),
        "duplicate_oof": lambda: H.validate_oof_frame(
            pd.concat([pd.read_parquet(oof_paths["logistic_regression"])] * 2,
                      ignore_index=True)),
    }
    for name, fn in cases.items():
        try:
            fn()
            failures[name] = "NOT_RAISED"
        except Exception as exc:  # noqa: BLE001 -- record outcome
            failures[name] = f"RAISED:{type(exc).__name__}"
    write("failure_behavior.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts, "cases": failures})

    # -- compute profile + screening projection (Part X) -------------------
    per_fit = dict(fit_times)
    inner_counts = {"D1": 1, "D2": 2, "D3": 3}
    grid_sizes = {f: len(c) for f, c in H.candidate_grids().items()}
    projection = {}
    for fam, gsize in grid_sizes.items():
        inner_fits = sum(inner_counts.values()) * gsize
        outer_fits = 3
        unit = per_fit[fam]
        total = round((inner_fits + outer_fits) * unit, 1)
        projection[fam] = {"grid": gsize, "inner_fits": inner_fits,
                           "outer_refits": outer_fits,
                           "seconds_per_fit": unit,
                           "projected_seconds": total}
    total_proj = sum(v["projected_seconds"] for v in projection.values())
    write("compute_profile.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts,
           "smoke_fit_seconds": per_fit,
           "artifact_kb": artifact_sizes,
           "smoke_wall_seconds": round(time.perf_counter() - t0, 1),
           "screening_projection": projection,
           "projected_total_seconds": round(total_proj, 1),
           "budget_per_family_s": 3600, "budget_total_s": 7200,
           "budget_gate": "PASS" if total_proj <= 7200 and all(
               v["projected_seconds"] <= 3600
               for v in projection.values()) else "FAIL"})

    # -- smoke summary ------------------------------------------------------
    write("smoke_experiment.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts,
           "fold": FOLD, "configs": SMOKE_CONFIGS,
           "race_macro_ll": {
               fam: float(res["metrics"]["log_loss"]["race_macro"]["value"])
               for fam, res in results.items()},
           "inner_tune_d1_logistic": {
               "selected_key": sel["selected_key"],
               "selected_mean": sel["selected_mean"]},
           "parity_gate": parity_gate["gate"],
           "no_ranking": True, "no_elimination": True})
    write("reproducibility.json",
          {"label": "HARNESS_SMOKE_ONLY", **contracts,
           "commands": [
               "uv run python scripts/freeze_v3_3b_prereg.py",
               "uv run python scripts/run_v3_3b_smoke.py",
               "uv run pytest tests/test_v3_3b_harness.py tests/test_v3_3a_contract.py -q",
           ],
           "a_contract_sha": contracts["contract_sha"],
           "b_prereg_sha": contracts["prereg_sha"]})
    print("smoke complete.")


if __name__ == "__main__":
    main()
