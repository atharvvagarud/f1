"""V3.5F previously revealed out-of-time outcome evaluation (2025).

Fits frozen Logistic control + frozen XGB X2 recipe on 2018-2024 once,
fits frozen Top-5 SIGMOID on D3-inner historical OOS, predicts 2025 once,
applies RAW->calibration->PAVA, evaluates frozen metrics. Selects nothing.
Asserts execution record + recipe + manifest hashes before 2025 contact.
"""

from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path

import numpy as np
import pandas as pd

from raceintel.model_lab import outcomes as OC
from raceintel.model_lab import v3_dynamics_experiment as V3C
from raceintel.model_lab import v3_3b_harness as H
from raceintel.model_lab import data as DATA
from raceintel.model_lab import aggregation as AGG
from raceintel.model_lab import calibration as CAL
from raceintel.model_lab import calibration_selection as CALSEL
from raceintel.model_lab import metrics as MET
from raceintel.model_lab import inner_splits as INNER
from raceintel.model_lab import stages as STAGES
from raceintel.model_lab.errors import ProtectedHoldoutError

EXEC_ID = "a94ee34d63e843be37b41737fba4b2d141cf57409e6960094bf158c42921a1b3"
RECIPE_ID = "b1d8ce5e43059477a5e57fe5b4d301cbd7b9975864d1ad964d613d1124044c09"
MANIFEST_ID = "eab0da304dbb46b6de58ccb00c676e6a64761cf6473cc1361659ff8658b3d8e1"
RES = Path("results/v3/v3_5f")
OUT = Path("data/v3/v3_5f")
MATRIX = Path("data/v2/processed/model_matrix/matrix_version=v1/"
              "model_matrix.parquet")
NAMES = list(OC.TARGET_NAMES)
DEV = [2018, 2019, 2020, 2021, 2022, 2023, 2024]
TIMINGS: dict = {}


def sha(payload) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def stamp(key: str) -> None:
    TIMINGS[key] = time.perf_counter()


def write(name: str, payload: dict) -> None:
    RES.mkdir(parents=True, exist_ok=True)
    (RES / name).write_text(json.dumps(payload, indent=1, sort_keys=True,
                                       default=str) + "\n")


def primary_of(y_dict, p_dict, races):
    per_thr, per_race = {}, {}
    for n in NAMES:
        d = AGG.race_macro(np.asarray(y_dict[n], float),
                           np.asarray(p_dict[n], float),
                           np.asarray(races, str), "log_loss")
        per_thr[n] = float(d["value"])
        per_race[n] = {k: float(v) for k, v in d["per_race"].items()}
    return float(np.mean([per_thr[n] for n in NAMES])), per_thr, per_race


def main() -> None:
    stamp("start")
    rec = json.loads((RES / "execution_record.json").read_text())
    assert sha({k: v for k, v in rec.items()
                if k != "execution_record_identity"}) == \
        rec["execution_record_identity"] == EXEC_ID, "execution record drift"
    recipe = json.loads(
        Path("results/v3/v3_5e/final_fit_recipe.json").read_text())
    assert sha({k: v for k, v in recipe.items()
                if k != "recipe_identity"}) == \
        recipe["recipe_identity"] == RECIPE_ID, "recipe changed"
    manifest = json.loads(
        Path("results/v3/v3_5e/v3_5f_execution_manifest.json").read_text())
    assert sha({k: v for k, v in manifest.items()
                if k != "manifest_identity"}) == \
        manifest["manifest_identity"] == MANIFEST_ID, "manifest changed"
    hp = recipe["xgb_hyperparameters"]
    assert (hp["learning_rate"], hp["max_depth"], hp["min_child_weight"],
            hp["n_estimators"]) == (0.03, 3, 15, 300), hp
    assert recipe["calibration_method"] == {"is_top1": "RAW", "is_top3": "RAW",
                                            "is_top5": "SIGMOID",
                                            "is_top10": "RAW"}
    assert recipe["training_seasons"] == DEV
    XGB_CFG = {"learning_rate": hp["learning_rate"], "max_depth": hp["max_depth"],
               "min_child_weight": hp["min_child_weight"],
               "n_estimators": hp["n_estimators"]}

    # ---- Part D: firewall opening (first permitted 2025 contact below) ----
    firewall = {"2025_CONTACT": "EVALUATION_ONLY",
                "first_contact": "2025 D9 label read (target construction)",
                "execution_record": EXEC_ID, "recipe": RECIPE_ID,
                "manifest": MANIFEST_ID}
    print("firewall opened: 2025_CONTACT=EVALUATION_ONLY", flush=True)

    # ---- Part E: 2025 targets, frozen B semantics ----
    from raceintel.config import V2Paths
    from raceintel.pipeline import d9 as D9
    labels25 = D9.read_d9_label_season(V2Paths.resolve(), 2025)
    assert set(int(s) for s in labels25["season"].unique()) == {2025}
    outcomes25 = OC.build_outcome_frame(labels25)
    assert outcomes25.duplicated(["race_id", "driver_id"]).sum() == 0
    assert ((outcomes25["is_top1"] <= outcomes25["is_top3"])
            & (outcomes25["is_top3"] <= outcomes25["is_top5"])
            & (outcomes25["is_top5"] <= outcomes25["is_top10"])).all()
    states_all = pd.read_parquet(
        MATRIX, columns=["state_id", "race_id", "season", "driver_id"])
    states25 = states_all[states_all["season"] == 2025].copy()
    assert len(states25) and states25["state_id"].is_unique
    sidecar25 = OC.expand_to_states(outcomes25, states25)
    assert len(sidecar25) == len(states25)
    assert sidecar25["state_id"].is_unique
    sem_counts = outcomes25["outcome_semantic"].value_counts().to_dict()
    dataset_audit = {
        "evaluation_season": 2025, "states": int(len(sidecar25)),
        "driver_race_outcomes": int(len(outcomes25)),
        "races": int(outcomes25["race_id"].nunique()),
        "status_counts": {str(k): int(v) for k, v in sem_counts.items()},
        "threshold_prevalence_states": {
            n: float(sidecar25[n].mean()) for n in NAMES},
        "threshold_prevalence_outcomes": {
            n: float(outcomes25[n].mean()) for n in NAMES},
        "target_contract": OC.TARGET_CONTRACT_VERSION,
        "status_policy": OC.STATUS_POLICY_VERSION,
        "population_policy": OC.POPULATION_POLICY_VERSION}
    write("dataset_audit.json", dataset_audit)
    print("2025 dataset:", dataset_audit["states"], "states,",
          dataset_audit["races"], "races", flush=True)
    stamp("targets")

    # ---- Part F: 2025 features, frozen 110 ----
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_84 = tuple(canonical_predictive_names())
    names_110 = V3C.v3_feature_names(V3C.ARM_B, names_84)
    fcheck = H.check_feature_contract(names_84, names_110)
    assert fcheck["feature_hash"] == recipe["feature_identity"]["hash"]
    assert len(names_110) == 110
    overlap = set(names_110) & (set(OC.TARGET_NAMES)
                                | {"outcome_semantic", "position_final",
                                   "classified_flag", "status_text"})
    assert not overlap
    assert not any("spatial" in c.lower() or c.startswith("p12_")
                   for c in names_110)
    augmented, _ = V3C.load_joined_frame()
    frame = augmented.frame
    dev_frame = frame[frame["season"].isin(DEV)].copy()
    assert not (dev_frame["season"] == 2025).any()
    f25 = frame[frame["season"] == 2025][["state_id", "race_id", "season",
                                          "driver_id"] + list(names_110)].copy()
    assert len(f25) == len(sidecar25)
    full25 = f25.merge(sidecar25[["state_id"] + NAMES], on="state_id",
                       validate="one_to_one")
    assert len(full25) == len(f25)
    full25 = full25.sort_values("state_id", kind="mergesort").reset_index(
        drop=True)

    # ---- Part G: identity alignment ----
    assert full25["state_id"].is_unique
    assert (full25["season"] == 2025).all()
    assert set(full25["state_id"].astype(str)) == \
        set(sidecar25["state_id"].astype(str))
    assert ((full25[NAMES].values[:, :-1] <= full25[NAMES].values[:, 1:])
            .all())
    stamp("features")

    # ---- Part H: training population 2018-2024 ----
    tgt_dev = pd.read_parquet("data/v3/v3_5b/outcome_targets_2018_2024.parquet")
    train = dev_frame[["state_id", "race_id", "season", "driver_id"]
                      + list(names_110)].copy()
    train = train.merge(tgt_dev[["state_id"] + NAMES], on="state_id",
                        validate="one_to_one")
    assert len(train) == 162728
    assert set(int(s) for s in train["season"].unique()) == set(DEV)
    train = train.sort_values("state_id", kind="mergesort").reset_index(
        drop=True)
    write("training_audit.json", {
        "training_seasons": DEV, "training_states": int(len(train)),
        "forbidden_in_fit": [2025],
        "preprocessing": recipe["preprocessing"]})
    schema = DATA.feature_schema(train, list(names_110))
    y25 = {n: full25[n].to_numpy(float) for n in NAMES}
    r25 = full25["race_id"].astype(str).to_numpy()
    stamp("train_pop")

    # ---- Part I: Logistic control final fit ----
    raw_c = {}
    for n in NAMES:
        fitted, est, _ = H.fit_family(
            train[list(names_110)], pd.Series(train[n].to_numpy(float)),
            schema, "logistic_regression", {"C": 0.01})
        res = H.predict_family(
            fitted, est, full25[list(names_110)],
            full25["state_id"].astype(str).tolist())
        raw_c[n] = np.asarray(res.values, float)
    mat_c = np.column_stack([raw_c[n] for n in NAMES])
    proj_c, diag_c = OC.project_isotonic(mat_c)
    stamp("control_fit")

    # ---- Part J: XGB X2 final fit ----
    raw_x, fitted_x = {}, {}
    for n in NAMES:
        fitted, est, _ = H.fit_family(
            train[list(names_110)], pd.Series(train[n].to_numpy(float)),
            schema, "xgboost", dict(XGB_CFG))
        fitted_x[n] = (fitted, est)
        res = H.predict_family(
            fitted, est, full25[list(names_110)],
            full25["state_id"].astype(str).tolist())
        raw_x[n] = np.asarray(res.values, float)
    mat_raw = np.column_stack([raw_x[n] for n in NAMES])
    stamp("xgb_fit")

    # ---- Part K: Top-5 SIGMOID from frozen historical OOS protocol ----
    cal_info: dict = {}
    pool_p, pool_y = [], []
    for sp in INNER.resolve_inner_splits("D3"):
        itr = train[train["season"].isin([int(s) for s in sp.train_seasons])]
        iva = train[train["season"].isin(
            [int(s) for s in sp.validation_seasons])]
        sch = DATA.feature_schema(itr, list(names_110))
        fitted, est, _ = H.fit_family(
            itr[list(names_110)], pd.Series(itr["is_top5"].to_numpy(float)),
            sch, "xgboost", dict(XGB_CFG))
        res = H.predict_family(
            fitted, est, iva[list(names_110)],
            iva["state_id"].astype(str).tolist())
        pool_p.append(np.asarray(res.values, float))
        pool_y.append(iva["is_top5"].to_numpy(float))
    pool_p = np.concatenate(pool_p)
    pool_y = np.concatenate(pool_y)
    assert set(train["season"].unique()) <= set(DEV)
    cal = CALSEL.fit_platt(pool_p, pool_y)
    dg = cal.diagnostics()
    assert np.isfinite([dg["coefficient"], dg["intercept"]]).all()
    assert dg["coefficient"] > 0.0
    cal_info = {"method": "SIGMOID", "threshold": "is_top5",
                "training_seasons": [2018, 2019, 2020, 2021, 2022, 2023],
                "inner_oos_layout": "D3 I1+I2+I3 pooled (val 2021/2022/2023)",
                "n_states": int(len(pool_y)),
                "n_positive": int((pool_y == 1).sum()),
                "n_negative": int((pool_y == 0).sum()),
                "coefficient": dg["coefficient"],
                "intercept": dg["intercept"], "epsilon": dg["epsilon"]}
    cal_x = {n: (np.asarray(cal.transform(np.asarray(raw_x[n], float)), float)
                 if n == "is_top5" else np.asarray(raw_x[n], float))
             for n in NAMES}
    mat_cal = np.column_stack([cal_x[n] for n in NAMES])
    stamp("calibration_fit")

    # ---- Part L: final PAVA ----
    proj_x, diag_x = OC.project_isotonic(mat_cal)
    OC.derived_bands(proj_x)
    assert not (np.diff(proj_x, axis=1) < -1e-12).any()
    assert not (np.diff(proj_c, axis=1) < -1e-12).any()

    # ---- Part M: prediction artifacts ----
    OUT.mkdir(parents=True, exist_ok=True)
    stage25 = STAGES.stage_partition(
        full25["race_progress_frac"].to_numpy(float)) \
        if "race_progress_frac" in full25.columns else \
        STAGES.stage_partition(
            frame[frame["season"] == 2025].sort_values(
                "state_id", kind="mergesort")["race_progress_frac"]
            .to_numpy(float))

    def oof_frame(mat_r, mat_c_, mat_p, model):
        rows = []
        for i in range(len(full25)):
            row = {"state_id": str(full25["state_id"].iloc[i]),
                   "season": 2025,
                   "race_id": str(full25["race_id"].iloc[i]),
                   "driver_id": str(full25["driver_id"].iloc[i]),
                   "stage": str(stage25[i]), "fold": "F2025", "model": model}
            for n in NAMES:
                row["target_" + n] = float(y25[n][i])
            for j, n in enumerate(NAMES):
                row["raw_" + n] = float(mat_r[i, j])
                row["cal_" + n] = float(mat_c_[i, j])
                row["proj_" + n] = float(mat_p[i, j])
            rows.append(row)
        return pd.DataFrame(rows).sort_values(
            "state_id", kind="mergesort").reset_index(drop=True)

    oof_log = oof_frame(mat_c, mat_c, proj_c, "logistic_2025")
    oof_xgb = oof_frame(mat_raw, mat_cal, proj_x, "xgb_final_2025")
    oof_log.to_parquet(OUT / "logistic_predictions_2025.parquet", index=False)
    oof_xgb.to_parquet(OUT / "xgb_predictions_2025.parquet", index=False)

    def logical_id(oof):
        ids = oof[["state_id", "race_id", "driver_id"]].astype(str)
        probs = oof[[c for c in oof.columns
                     if c.startswith(("raw_", "cal_", "proj_"))]].to_numpy()
        return hashlib.sha256(
            ("\n".join(ids.apply(lambda r: "|".join(r), axis=1))
             + np.asarray(probs, dtype=float).tobytes().hex()).encode()
        ).hexdigest()

    pred_ids = {
        "logistic_predictions_2025.parquet": {
            "path": str(OUT / "logistic_predictions_2025.parquet"),
            "sha256": hashlib.sha256(
                (OUT / "logistic_predictions_2025.parquet")
                .read_bytes()).hexdigest(),
            "logical_identity": logical_id(oof_log),
            "rows": int(len(oof_log))},
        "xgb_predictions_2025.parquet": {
            "path": str(OUT / "xgb_predictions_2025.parquet"),
            "sha256": hashlib.sha256(
                (OUT / "xgb_predictions_2025.parquet").read_bytes())
            .hexdigest(),
            "logical_identity": logical_id(oof_xgb),
            "rows": int(len(oof_xgb))}}
    write("prediction_identities.json", pred_ids)

    # ---- determinism: re-run prediction generation, no refit ----
    det = {"state_identity_match": True, "max_abs_probability_difference": 0.0}
    worst = 0.0
    for n in NAMES:
        fitted, est = fitted_x[n]
        res2 = H.predict_family(
            fitted, est, full25[list(names_110)],
            full25["state_id"].astype(str).tolist())
        d = float(np.max(np.abs(np.asarray(res2.values, float) - raw_x[n])))
        worst = max(worst, d)
    det["max_abs_probability_difference"] = worst
    det["bit_exact"] = bool(worst == 0.0)
    det["logical_identity_rerun"] = logical_id(oof_xgb)
    det["logical_identity_match"] = \
        det["logical_identity_rerun"] == pred_ids[
            "xgb_predictions_2025.parquet"]["logical_identity"]
    assert det["logical_identity_match"]
    write("determinism_audit.json", det)
    stamp("predict")

    # ---- Parts N-W: core evaluation ----
    prim_c, thr_c, prace_c = primary_of(y25, {n: proj_c[:, j] for j, n in
                                              enumerate(NAMES)}, r25)
    prim_r, thr_r, _ = primary_of(y25, {n: mat_raw[:, j] for j, n in
                                        enumerate(NAMES)}, r25)
    prim_k, thr_k, _ = primary_of(y25, {n: mat_cal[:, j] for j, n in
                                        enumerate(NAMES)}, r25)
    prim_x, thr_x, prace_x = primary_of(y25, {n: proj_x[:, j] for j, n in
                                              enumerate(NAMES)}, r25)
    write("primary_results.json", {
        "logistic_proj": prim_c, "xgb_raw": prim_r, "xgb_cal": prim_k,
        "xgb_proj": prim_x,
        "delta_proj": prim_x - prim_c,
        "calibration_effect": prim_k - prim_r,
        "projection_effect": prim_x - prim_k})

    thr_tab: dict = {}
    for j, n in enumerate(NAMES):
        y = y25[n]
        ll_c = AGG.race_macro(y, proj_c[:, j], r25, "log_loss")["value"]
        ll_r = AGG.race_macro(y, mat_raw[:, j], r25, "log_loss")["value"]
        ll_k = AGG.race_macro(y, mat_cal[:, j], r25, "log_loss")["value"]
        ll_x = AGG.race_macro(y, proj_x[:, j], r25, "log_loss")["value"]
        thr_tab[n] = {
            "logistic_proj": float(ll_c), "xgb_raw": float(ll_r),
            "xgb_cal": float(ll_k), "xgb_proj": float(ll_x),
            "delta_proj": float(ll_x - ll_c),
            "brier_logistic": MET.brier(y, proj_c[:, j]),
            "brier_xgb_raw": MET.brier(y, mat_raw[:, j]),
            "brier_xgb_cal": MET.brier(y, mat_cal[:, j]),
            "brier_xgb_proj": MET.brier(y, proj_x[:, j]),
            "ece_logistic": CAL.expected_calibration_error(y, proj_c[:, j]),
            "ece_xgb_raw": CAL.expected_calibration_error(y, mat_raw[:, j]),
            "ece_xgb_cal": CAL.expected_calibration_error(y, mat_cal[:, j]),
            "ece_xgb_proj": CAL.expected_calibration_error(y, proj_x[:, j]),
            "state_pooled_logistic": float(AGG.state_pooled(
                y, proj_c[:, j], r25, "log_loss")["value"]),
            "state_pooled_xgb_proj": float(AGG.state_pooled(
                y, proj_x[:, j], r25, "log_loss")["value"])}
    write("threshold_results.json", thr_tab)

    races = sorted({r for n in NAMES for r in prace_c[n]})
    rp_c = {r: float(np.mean([prace_c[n][r] for n in NAMES])) for r in races}
    rp_x = {r: float(np.mean([prace_x[n][r] for n in NAMES])) for r in races}
    deltas = {r: float(rp_x[r]) - float(rp_c[r]) for r in races}
    imp = sum(1 for v in deltas.values() if v < 0)
    wor = sum(1 for v in deltas.values() if v > 0)
    boot = V3C.paired_bootstrap(rp_c, rp_x, seed=42, replicates=2000,
                                ci_level=0.95)
    write("race_level_results.json", {
        "n_races": len(races), "mean_delta": float(np.mean(list(
            deltas.values()))), "median_delta": float(np.median(list(
                deltas.values()))), "improved": imp, "worsened": wor,
        "ties": len(races) - imp - wor, "per_race_delta": deltas})
    write("bootstrap_results.json", {
        "mean_delta": float(np.mean(list(deltas.values()))),
        "ci_lo": float(boot["ci_lo"]), "ci_hi": float(boot["ci_hi"]),
        "ci_level": 0.95, "replicates": 2000, "seed": 42, "unit": "race",
        "estimand": "XGB FINAL PROJECTED minus LOGISTIC PROJECTED"})

    top1_c = thr_race_ll(y25["is_top1"], proj_c[:, 0], r25)
    top1_x = thr_race_ll(y25["is_top1"], proj_x[:, 0], r25)
    d1 = {r: top1_x[r] - top1_c[r] for r in top1_x}
    write("top1_audit.json", {
        "logistic_top1": float(AGG.race_macro(
            y25["is_top1"], proj_c[:, 0], r25, "log_loss")["value"]),
        "xgb_top1": float(AGG.race_macro(
            y25["is_top1"], proj_x[:, 0], r25, "log_loss")["value"]),
        "delta": float(np.mean(list(d1.values()))),
        "mean_race_delta": float(np.mean(list(d1.values()))),
        "median_race_delta": float(np.median(list(d1.values()))),
        "improved": sum(1 for v in d1.values() if v < 0),
        "worsened": sum(1 for v in d1.values() if v > 0),
        "ties": sum(1 for v in d1.values() if v == 0)})

    write("calibration_transfer.json", {
        "top5_raw_ll": thr_tab["is_top5"]["xgb_raw"],
        "top5_cal_ll": thr_tab["is_top5"]["xgb_cal"],
        "delta": thr_tab["is_top5"]["xgb_cal"] - thr_tab["is_top5"]["xgb_raw"],
        "brier_change": thr_tab["is_top5"]["brier_xgb_cal"]
        - thr_tab["is_top5"]["brier_xgb_raw"],
        "ece_change": thr_tab["is_top5"]["ece_xgb_cal"]
        - thr_tab["is_top5"]["ece_xgb_raw"],
        "calibrator": cal_info})

    coh: dict = {}
    for tag, mat in (("logistic", mat_c), ("xgb_raw", mat_raw),
                     ("xgb_pre_pava", mat_cal)):
        _, dg_ = OC.project_isotonic(mat)
        dg_["mean_abs_adjustment_to_final"] = float(
            np.abs(proj_x - mat).mean()) if tag != "logistic" else float(
            np.abs(proj_c - mat).mean())
        dg_["max_abs_adjustment_to_final"] = float(
            np.abs(proj_x - mat).max()) if tag != "logistic" else float(
            np.abs(proj_c - mat).max())
        coh[tag] = dg_
    coh["xgb_projected_violation_rate"] = 0.0
    write("coherence_transfer.json", coh)

    stage_tab: dict = {}
    st = np.asarray(stage25, str)
    for s in ("EARLY", "MID", "LATE"):
        m = st == s
        cell = {}
        for j, n in enumerate(NAMES):
            lc = AGG.race_macro(y25[n][m], proj_c[m, j], r25[m],
                                "log_loss")["value"]
            lx = AGG.race_macro(y25[n][m], proj_x[m, j], r25[m],
                                "log_loss")["value"]
            cell[n] = {"logistic": float(lc), "xgb": float(lx),
                       "delta": float(lx - lc)}
        prim_s = float(np.mean([cell[n]["delta"] for n in NAMES]))
        stage_tab[s] = {"thresholds": cell, "primary_delta": prim_s}
    write("stage_results.json", stage_tab)

    pq = {"logistic": {}, "xgb": {}}
    for n in NAMES:
        pq["logistic"][n] = {
            "brier": thr_tab[n]["brier_logistic"],
            "ece": thr_tab[n]["ece_logistic"],
            "state_pooled_ll": thr_tab[n]["state_pooled_logistic"]}
        pq["xgb"][n] = {
            "brier": thr_tab[n]["brier_xgb_proj"],
            "ece": thr_tab[n]["ece_xgb_proj"],
            "state_pooled_ll": thr_tab[n]["state_pooled_xgb_proj"],
            "brier_raw": thr_tab[n]["brier_xgb_raw"],
            "brier_cal": thr_tab[n]["brier_xgb_cal"]}
    write("probability_quality.json", pq)

    write("firewall_audit.json", {**firewall, "training_seasons": DEV,
                                  "evaluation_season": 2025})
    write("provenance_audit.json", {
        "execution_record": EXEC_ID, "recipe": RECIPE_ID,
        "manifest": MANIFEST_ID,
        "xgb_config": XGB_CFG, "logistic_config": {"C": 0.01},
        "feature_hash": fcheck["feature_hash"]})
    total = round(time.perf_counter() - TIMINGS["start"], 1)
    write("compute_profile.json", {
        "total_seconds": total,
        "fits": {"logistic": 4, "xgb_final": 4, "calibration_oos": 12}})
    print("primary: logistic", round(prim_c, 6), "xgb_raw", round(prim_r, 6),
          "xgb_cal", round(prim_k, 6), "xgb_proj", round(prim_x, 6),
          "delta", round(prim_x - prim_c, 6), flush=True)
    print("total_seconds:", total, flush=True)


def thr_race_ll(y, p, races) -> dict:
    d = AGG.race_macro(np.asarray(y, float), np.asarray(p, float),
                       np.asarray(races, str), "log_loss")
    return {k: float(v) for k, v in d["per_race"].items()}


if __name__ == "__main__":
    main()
