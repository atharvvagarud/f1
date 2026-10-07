"""V3.3C full temporal candidate screening (PRE-2025 ONLY).

Execution stage: pre-firewall -> baseline OOF (D1/D2/D3, independently
verified) -> nested tuning + outer refit for all 4 families x 3 folds ->
aligned OOF parquets. Analysis lives in scripts/analyze_v3_3c.py
(re-runnable from stored artifacts). Checkpointed per family-fold:
re-running skips completed units. 2025 is never touched.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from raceintel.model_lab import aggregation as AGG  # noqa: E402
from raceintel.model_lab import data as DATA  # noqa: E402
from raceintel.model_lab import stages as STAGES  # noqa: E402
from raceintel.model_lab import v3_3b_harness as H  # noqa: E402
from raceintel.model_lab import v3_dynamics_experiment as V3C  # noqa: E402
from raceintel.model_lab.errors import ProtectedHoldoutError  # noqa: E402

OUT = Path("results/v3/v3_3c")
OOF_DIR = Path("data/v3/v3_3c")
V3_1C_EVIDENCE = Path(
    "results/v3/v3_1c_race_dynamics_controlled_experiment.json")
FAMILIES = ("logistic_regression", "hist_gradient_boosting", "extra_trees",
            "xgboost")
FOLDS = ("D1", "D2", "D3")
ARM = "ALL_84_PLUS_V3_1_DYNAMICS_CORE"


def write(name: str, payload: dict) -> Path:
    OUT.mkdir(parents=True, exist_ok=True)
    dest = OUT / name
    dest.write_text(json.dumps(payload, indent=1, sort_keys=True,
                               default=str) + "\n")
    return dest


def write_oof(frame: pd.DataFrame, dest: Path) -> Path:
    """Validate (harness contract) + write OOF to an explicit C path.

    Uses H.validate_oof_frame but NOT H.write_oof_parquet: the harness
    helper targets the frozen B directory (data/v3/v3_3b); C owns
    data/v3/v3_3c.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    H.validate_oof_frame(
        frame, expect_baseline=("baseline_probability" in frame.columns))
    frame.to_parquet(dest, index=False)
    return dest


def load_c_prereg() -> dict:    prereg = json.loads((OUT / "preregistration.json").read_text())
    payload = {k: v for k, v in prereg.items()
               if k != "preregistration_identity"}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    if hashlib.sha256(blob.encode()).hexdigest() != \
            prereg["preregistration_identity"]:
        raise RuntimeError("C preregistration hash mismatch")
    return prereg


def main() -> None:
    contracts = H.verify_contracts()
    c_prereg = load_c_prereg()
    # Grid immutability gate: frozen grids must equal C prereg exact grids.
    live = H.candidate_grids()
    for fam in FAMILIES:
        assert [dict(c) for c in live[fam]] == \
            c_prereg["exact_grids"][fam], f"grid drift: {fam}"
        assert [H.config_id(fam, c) for c in live[fam]] == \
            c_prereg["exact_config_ids"][fam], f"config-id drift: {fam}"
    print("A/B/C identities + grid immutability verified.", flush=True)

    # -- Part D: pre-execution firewall --------------------------------
    firewall_pre = {"2025_CONTACT": "NONE", **contracts,
                    "c_prereg_sha": c_prereg["preregistration_identity"]}
    for bad in ("HOLDOUT", "2025", "FINAL_FIT", "HOLDOUT_2025"):
        try:
            H.assert_development_fold(bad)
            firewall_pre[bad] = "NOT_BLOCKED"
        except ProtectedHoldoutError:
            firewall_pre[bad] = "BLOCKED:ProtectedHoldoutError"
    try:
        from raceintel.model_lab import splits as SPLITS
        SPLITS.get_split("HOLDOUT")
        firewall_pre["resolver_holdout"] = "NOT_BLOCKED"
    except ProtectedHoldoutError:
        firewall_pre["resolver_holdout"] = "BLOCKED:ProtectedHoldoutError"
    if any(v == "NOT_BLOCKED" for v in firewall_pre.values()):
        write("firewall_pre.json", firewall_pre)
        raise RuntimeError("V3.3C BLOCKED - 2025 FIREWALL FAILURE")
    write("firewall_pre.json", firewall_pre)
    print("pre-execution firewall: 2025_CONTACT = NONE", flush=True)

    # -- materialization ------------------------------------------------
    augmented, plain = V3C.load_joined_frame()
    names_84 = V3C.v3_feature_names(V3C.ARM_A)
    names_110 = H.feature_names_110(names_84)
    H.check_feature_contract(names_84, names_110)

    # -- Part E: baseline OOF (stored V3.1C evidence, independently verified)
    evidence = json.loads(V3_1C_EVIDENCE.read_text())
    baseline_identity, oof_dir = {}, OOF_DIR
    oof_dir.mkdir(parents=True, exist_ok=True)
    for fold in FOLDS:
        stored = pd.read_parquet(
            f"data/v3/v3_1c/pred_{ARM}__{fold}.parquet")
        # independent check 1: row set == harness materialization row set
        ds = V3C.materialize_v3(augmented, fold, V3C.ARM_B, names_110)
        harness_ids = list(ds.validation_metadata["state_id"])
        assert sorted(stored["state_id"]) == sorted(harness_ids), \
            f"baseline row-set drift: {fold}"
        # independent check 2: refit logistic control, require bit-identity
        refit = H.run_outer(augmented, plain, fold, "logistic_regression",
                            {"C": 0.01}, feature_arm=H.ARM_PRIMARY,
                            feature_names=names_110)
        ordered = stored.set_index("state_id").loc[refit["state_ids"]]
        max_abs = float(np.max(np.abs(
            np.asarray(refit["predictions"])
            - ordered["y_pred"].to_numpy(dtype=float))))
        assert max_abs == 0.0, f"baseline refit drift {fold}: {max_abs}"
        # independent check 3: parquet LL == frozen V3.1C JSON race_macro
        key = f"{ARM}__{fold}"
        frozen_ll = evidence["arm_results"][key]["race_macro"]["log_loss"]
        y = ordered["y_true"].to_numpy(dtype=float)
        p = ordered["y_pred"].to_numpy(dtype=float)
        r = ordered["race_id"].astype(str).to_numpy()
        parquet_ll = AGG.race_macro(y, p, r, "log_loss")["value"]
        assert abs(parquet_ll - frozen_ll) <= 1e-12, \
            f"baseline metric drift {fold}"
        # canonical C-schema baseline frame (+ stage labels)
        val_frame = augmented.frame.loc[ds.y_validation.index]
        stages = list(np.asarray(STAGES.stage_partition(
            val_frame["race_progress_frac"])))
        stage_by_id = dict(zip(list(val_frame["state_id"]), stages))
        frame = pd.DataFrame({
            "state_id": list(ordered.index),
            "season": ordered["season"].astype(int).to_numpy(),
            "race_id": ordered["race_id"].astype(str).to_numpy(),
            "driver_id": ordered["driver_id"].astype(str).to_numpy(),
            "target": y, "fold": [fold] * len(ordered),
            "stage": [stage_by_id[s] for s in ordered.index],
            "feature_arm": [H.ARM_PRIMARY] * len(ordered),
            "model_family": ["v3_1b_baseline"] * len(ordered),
            "model_config_id": ["C=0.01"] * len(ordered),
            "probability": p})
        write_oof(frame, oof_dir / f"oof_baseline__{fold}.parquet")        baseline_identity[fold] = {
            "n_rows": len(frame), "n_races": int(frame["race_id"].nunique()),
            "race_macro_ll": parquet_ll,
            "frozen_v3_1c_ll": frozen_ll,
            "refit_max_abs_diff": max_abs,
            "sha256": hashlib.sha256(
                frame["probability"].to_numpy().tobytes()).hexdigest()}
        print(f"baseline {fold}: n={len(frame)} LL={parquet_ll:.6f} "
              f"refit_diff={max_abs:.1e}", flush=True)
    write("baseline_oof_identity.json",
          {"c_prereg_sha": c_prereg["preregistration_identity"],
           **contracts, "arm": H.ARM_PRIMARY, "folds": baseline_identity})

    # -- Part F+G: nested tuning + outer refit, all families x folds -----
    tuning_audit, selected, outer_dir = {}, {}, OUT / "outer_results"
    outer_dir.mkdir(parents=True, exist_ok=True)
    import subprocess as sp
    try:
        commit = sp.run(["git", "rev-parse", "HEAD"], capture_output=True,
                        text=True).stdout.strip()
    except Exception:
        commit = "unknown"
    for family in FAMILIES:
        tuning_audit[family], selected[family] = {}, {}
        for fold in FOLDS:
            tune_path = OUT / f"tune_{family}__{fold}.json"
            oof_path = oof_dir / f"oof_{family}__{fold}.parquet"
            outer_path = outer_dir / f"{family}__{fold}.json"
            if tune_path.exists() and oof_path.exists() \
                    and outer_path.exists():
                print(f"skip {family}/{fold} (checkpointed)", flush=True)
                tune = json.loads(tune_path.read_text())
                tuning_audit[family][fold] = tune["audit"]
                selected[family][fold] = tune["selection"]
                continue
            t_start = time.perf_counter()
            tune = H.tune_family(augmented, family, fold,
                                 feature_arm=H.ARM_PRIMARY,
                                 feature_names=names_110)
            sel = tune["selection"]
            res = H.run_outer(augmented, plain, fold, family,
                              sel["selected_config"],
                              feature_arm=H.ARM_PRIMARY,
                              feature_names=names_110)
            wall_s = round(time.perf_counter() - t_start, 1)
            frame = H.build_oof_frame(res, fold, H.ARM_PRIMARY)
            write_oof(frame, oof_path)
            audit = {
                "inner_folds": [
                    {"inner_fold_id": r["inner_fold_id"],
                     "train_seasons": r["train_seasons"],
                     "validation_seasons": r["validation_seasons"],
                     "configs": r["configs"]} for r in tune["inner_folds"]],
                "config_aggregates": {
                    k: {"config": v["config"], "mean": v["mean"],
                        "std": v["std"], "min": v["min"], "max": v["max"]}
                    for k, v in tune["config_aggregates"].items()},
                "selection": sel, "estimator_fits": tune["estimator_fits"],
                "wall_seconds": wall_s, "failures": []}
            tune_path.write_text(json.dumps(
                {"audit": audit, "selection": {
                    "selected_key": sel["selected_key"],
                    "selected_config": sel["selected_config"],
                    "selected_mean": sel["selected_mean"],
                    "tie_break_applied": sel["tie_break_applied"]}},
                indent=1, sort_keys=True, default=str) + "\n")
            prov = H.provenance_envelope(
                family=family, config=sel["selected_config"], fold_id=fold,
                feature_arm=H.ARM_PRIMARY, feature_names=names_110,
                dataset=res["dataset"], code_commit=commit)
            outer_payload = {
                "family": family, "fold": fold,
                "model_config_id": res["model_config_id"],
                "config_dict": res["config_dict"],
                "metrics": {m: {
                    "race_macro": p["race_macro"]["value"],
                    "state_pooled": p["state_pooled"]["value"]}
                    for m, p in res["metrics"].items()
                    if p.get("status") == "OK"},
                "per_race_log_loss": res["metrics"]["log_loss"][
                    "race_macro"]["per_race"],
                "stages": {
                    s: {m: pay[s]["race_macro"]["value"]
                        for m, pay in res["stages"].items()
                        if pay.get("status") == "OK" and s in pay
                        and pay[s].get("race_macro")}
                    for s in ("EARLY", "MID", "LATE")},
                "calibration": res["calibration"],
                "topk": res["topk"],
                "timings": res["timings"],
                "transformed_dim": res["transformed_dim"],
                "convergence_warnings": res["convergence_warnings"],
                "provenance": prov,
                "c_prereg_sha": c_prereg["preregistration_identity"]}
            outer_path.write_text(json.dumps(
                outer_payload, indent=1, sort_keys=True, default=str) + "\n")
            tuning_audit[family][fold] = audit
            selected[family][fold] = {
                "selected_key": sel["selected_key"],
                "selected_config": sel["selected_config"]}
            ll = res["metrics"]["log_loss"]["race_macro"]["value"]
            print(f"{family}/{fold}: {sel['selected_key']} "
                  f"outer_LL={ll:.6f} wall={wall_s}s", flush=True)
    # reload checkpointed selections for the summary files
    for family in FAMILIES:
        for fold in FOLDS:
            if fold not in selected[family]:
                tune = json.loads(
                    (OUT / f"tune_{family}__{fold}.json").read_text())
                selected[family][fold] = tune["selection"]
    write("inner_tuning_results.json",
          {"c_prereg_sha": c_prereg["preregistration_identity"],
           **contracts, "tuning": tuning_audit})
    write("selected_configs.json",
          {"c_prereg_sha": c_prereg["preregistration_identity"],
           **contracts, "selected": selected,
           "n_selected_outer_models": sum(
               len(v) for v in selected.values())})
    print("screening execution complete.", flush=True)


if __name__ == "__main__":
    main()
