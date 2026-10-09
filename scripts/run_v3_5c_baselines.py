"""V3.5C: frozen baselines + harness validation (one protocol, one run).

Fits ONLY the frozen L2-logistic control (C=0.01, no tuning). Deterministic
baselines need no fitting. 2018-2024 only; 2025 fails closed.
Asserts the C harness contract hash before doing anything learned.
"""
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
from raceintel.model_lab import metrics as MET
from raceintel.model_lab.errors import ProtectedHoldoutError

RES = Path("results/v3/v3_5c")
OUT = Path("data/v3/v3_5c")
C_HASH = "9dfee182215d6a56e4f19e2418b051883e9c75876418a6f4c92a05d799c7603a"
MATRIX = Path("data/v2/processed/model_matrix/matrix_version=v1/model_matrix.parquet")
SIDECAR = Path("data/v3/race_dynamics/dynamics_sidecar.parquet")
TARGETS = Path("data/v3/v3_5b/outcome_targets_2018_2024.parquet")
FOLDS = {"D1": ([2018, 2019, 2020, 2021], [2022]),
         "D2": ([2018, 2019, 2020, 2021, 2022], [2023]),
         "D3": ([2018, 2019, 2020, 2021, 2022, 2023], [2024])}
NAMES = list(OC.TARGET_NAMES)
KS = list(OC.THRESHOLD_ORDER)
TIMINGS = {}


def stamp(key):
    TIMINGS[key] = time.perf_counter()


def elapsed(a, b):
    return round(TIMINGS[b] - TIMINGS[a], 1)


def ll_race_macro(y, p, r):
    d = AGG.race_macro(np.asarray(y, float), np.asarray(p, float),
                       np.asarray(r, str), "log_loss")
    return d["value"], {k: float(v) for k, v in d["per_race"].items()}


def main() -> None:
    stamp("start")
    c = json.loads((RES / "screening_harness_contract.json").read_text())
    blob = json.dumps({k: v for k, v in c.items() if k != "contract_hash"},
                      sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        c["contract_hash"] == C_HASH, "C contract changed after freeze"
    assert c["baselines"]["l2_logistic_control"]["config"] == {"C": 0.01}

    t = json.loads(Path("results/v3/v3_5b/dataset_manifest.json").read_text())
    assert t["logical_identity"] == \
        "e9ac34e5792a5aabba9038094a231a4a94789b481178739e46ece72457cc5289"

    # ---- frozen frames (2018-2024 only; exact V3.1/V3.3 join path) ----
    stamp("load")
    augmented, _plain = V3C.load_joined_frame()
    frame = augmented.frame
    if "season" not in frame.columns:
        raise ProtectedHoldoutError("joined frame lacks season firewall column")
    frame = frame[frame["season"].isin([2018, 2019, 2020, 2021, 2022, 2023, 2024])].copy()
    if (frame["season"] == 2025).any():
        raise ProtectedHoldoutError("2025 matrix rows reached C harness")
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_84 = tuple(canonical_predictive_names())
    names_110 = V3C.v3_feature_names(V3C.ARM_B, names_84)
    fcheck = H.check_feature_contract(names_84, names_110)
    assert fcheck["feature_hash"] == \
        "e054c6fb08c0832970165bcfc0e84f54b70787491af1d545b96a13977fc4c89e"
    assert list(augmented.manifest["predictive_columns"]) == list(names_110)
    for col in ("state_id", "race_id", "season", "driver_id", "position",
                "grid_position"):
        assert col in frame.columns, col
    base = frame[["state_id", "race_id", "season", "driver_id"]
                  + list(names_110)].copy()
    # `position`/`grid_position` are members of the frozen 110 (CORE_26);
    # baselines read them from the feature columns (causal state at T).
    assert base["state_id"].is_unique
    tgt = pd.read_parquet(TARGETS)
    full = base.merge(tgt[["state_id"] + NAMES], on="state_id",
                      validate="one_to_one")
    assert len(full) == 162728, len(full)
    full = full.sort_values("state_id", kind="mergesort").reset_index(drop=True)
    stamp("frames")

    # ---- split audit ----
    split_audit = {}
    for fid, (tr, va) in FOLDS.items():
        trm = full[full["season"].isin(tr)]
        vam = full[full["season"].isin(va)]
        split_audit[fid] = {
            "train_seasons": tr, "validate_seasons": va,
            "train_states": int(len(trm)), "validation_states": int(len(vam)),
            "train_races": int(trm["race_id"].nunique()),
            "validation_races": int(vam["race_id"].nunique())}
    (RES / "split_audit.json").write_text(
        json.dumps(split_audit, indent=1, sort_keys=True) + "\n")

    schema_all = DATA.feature_schema(full, list(names_110))
    (RES / "preprocessing_contract.json").write_text(json.dumps({
        "module": "raceintel.model_lab.preprocessing.fit_preprocessor via harness fit_family",
        "fit_on": "outer TRAIN only",
        "numeric": len(schema_all.numeric), "boolean": len(schema_all.boolean),
        "categorical": len(schema_all.categorical),
        "features_110_exact": list(names_110),
    }, indent=1, sort_keys=True) + "\n")
    (RES / "baseline_configs.json").write_text(json.dumps(
        c["baselines"], indent=1, sort_keys=True) + "\n")

    # ---- baselines per fold ----
    results, race_level, oof_identities = {}, {}, {}
    OUT.mkdir(parents=True, exist_ok=True)
    for fid, (tr, va) in FOLDS.items():
        stamp(f"fit_{fid}")
        trm = full[full["season"].isin(tr)].reset_index(drop=True)
        vam = full[full["season"].isin(va)].reset_index(drop=True)
        ytr = {n: trm[n].to_numpy(float) for n in NAMES}
        yva = {n: vam[n].to_numpy(float) for n in NAMES}
        rva = vam["race_id"].astype(str).to_numpy()
        train_rates = {n: float(ytr[n].mean()) for n in NAMES}

        probs = {}
        # climatology
        probs["climatology"] = {
            n: np.full(len(vam), train_rates[n]) for n in NAMES}
        # position persistence (+ causal train-rate fallback for nulls)
        ppos = vam["position"].to_numpy(float)
        probs["position_persistence"] = {}
        for n, k in zip(NAMES, KS):
            p = np.where(np.isnan(ppos), train_rates[n],
                         np.where(ppos <= k, 1.0, 0.0))
            probs["position_persistence"][n] = p
        # grid
        gpos = vam["grid_position"].to_numpy(float)
        assert np.all(np.isfinite(gpos)), "null grid in state population"
        probs["grid"] = {n: np.where(gpos <= k, 1.0, 0.0)
                         for n, k in zip(NAMES, KS)}
        # L2-logistic control (only learned model in C)
        Xtr = trm[list(names_110)]
        schema = DATA.feature_schema(trm, list(names_110))
        probs["l2_logistic"] = {}
        prep_ids = []
        for n in NAMES:
            fitted, est, info = H.fit_family(
                Xtr, pd.Series(ytr[n]), schema, "logistic_regression",
                {"C": 0.01})
            res = H.predict_family(
                fitted, est, vam[list(names_110)],
                vam["state_id"].astype(str).tolist())
            probs["l2_logistic"][n] = np.asarray(res.values, float)
            prep_ids.append(info["transformed_dim"])
        assert len(set(prep_ids)) == 1
        stamp(f"eval_{fid}")

        fold_res, fold_races, proj_mats = {}, {}, {}
        oof_rows = []
        for model, pdict in probs.items():
            raw = np.column_stack([pdict[n] for n in NAMES])
            proj, diag = OC.project_isotonic(raw)
            proj_mats[model] = (raw, proj)
            bands = OC.derived_bands(proj)
            thr, per_race = {}, {}
            for j, n in enumerate(NAMES):
                v_raw, pr_raw = ll_race_macro(yva[n], raw[:, j], rva)
                v_prj, pr_prj = ll_race_macro(yva[n], proj[:, j], rva)
                thr[n] = {
                    "race_macro_ll_raw": v_raw, "race_macro_ll_proj": v_prj,
                    "brier_raw": MET.brier(yva[n], raw[:, j]),
                    "brier_proj": MET.brier(yva[n], proj[:, j]),
                    "ece_raw": CAL.expected_calibration_error(yva[n], raw[:, j]),
                    "ece_proj": CAL.expected_calibration_error(yva[n], proj[:, j]),
                    "state_pooled_ll_raw": AGG.state_pooled(
                        yva[n], raw[:, j], rva, "log_loss")["value"],
                    "state_pooled_ll_proj": AGG.state_pooled(
                        yva[n], proj[:, j], rva, "log_loss")["value"],
                    "acc_at_05_raw": float(
                        ((raw[:, j] >= 0.5) == yva[n]).mean())}
                per_race[n] = {"raw": pr_raw, "proj": pr_prj}
            primary_raw = float(np.mean([thr[n]["race_macro_ll_raw"]
                                         for n in NAMES]))
            primary_proj = float(np.mean([thr[n]["race_macro_ll_proj"]
                                          for n in NAMES]))
            fold_res[model] = {
                "primary_raw": primary_raw, "primary_proj": primary_proj,
                "projected_minus_raw": primary_proj - primary_raw,
                "thresholds": thr, "projection": diag,
                "bands_valid": True}
            fold_races[model] = per_race
            for i in range(len(vam)):
                row = {"state_id": str(vam["state_id"].iloc[i]),
                       "season": int(vam["season"].iloc[i]),
                       "race_id": str(vam["race_id"].iloc[i]),
                       "driver_id": str(vam["driver_id"].iloc[i]),
                       "fold": fid, "model": model}
                for n in NAMES:
                    row["target_" + n] = float(yva[n][i])
                for j, n in enumerate(NAMES):
                    row["raw_" + n] = float(raw[i, j])
                    row["proj_" + n] = float(proj[i, j])
                oof_rows.append(row)
        results[fid] = fold_res
        # per-race PRIMARY (mean over thresholds), raw + projected
        race_prim = {}
        for model in probs:
            raw, proj = proj_mats[model]
            prim_raw, prim_proj = {}, {}
            for r in sorted(set(rva)):
                m = rva == r
                prim_raw[r], prim_proj[r] = [], []
                for arr, store in ((raw, prim_raw[r]), (proj, prim_proj[r])):
                    vals = []
                    for j, n in enumerate(NAMES):
                        pp = np.clip(arr[m, j], 1e-15, 1 - 1e-15)
                        vals.append(float(-np.mean(
                            yva[n][m] * np.log(pp)
                            + (1 - yva[n][m]) * np.log(1 - pp))))
                    store.append(float(np.mean(vals)))
                prim_raw[r] = prim_raw[r][0]
                prim_proj[r] = prim_proj[r][0]
            race_prim[model] = {"per_race_primary_raw": prim_raw,
                                "per_race_primary_proj": prim_proj}
        race_level[fid] = race_prim
        oof = pd.DataFrame(oof_rows).sort_values(
            ["model", "state_id"], kind="mergesort").reset_index(drop=True)
        dest = OUT / f"oof_{fid}.parquet"
        oof.to_parquet(dest, index=False)
        oof_identities[fid] = {
            "path": str(dest),
            "sha256": hashlib.sha256(dest.read_bytes()).hexdigest(),
            "rows": int(len(oof)), "models": sorted(probs)}
        stamp(f"oof_{fid}")

    (RES / "baseline_results.json").write_text(
        json.dumps(results, indent=1, sort_keys=True) + "\n")
    (RES / "race_level_results.json").write_text(
        json.dumps(race_level, indent=1, sort_keys=True) + "\n")
    (RES / "prediction_identities.json").write_text(
        json.dumps(oof_identities, indent=1, sort_keys=True) + "\n")

    # ---- bootstrap validation (per fold; paired race primary) ----
    boot = {}
    for fid in FOLDS:
        boot[fid] = {}
        base = race_level[fid]
        for cand, base_name in (("l2_logistic", "climatology"),
                                ("l2_logistic", "position_persistence")):
            a = base[base_name]["per_race_primary_raw"]
            # recompute candidate per-race primary from OOF parquet (independent read)
            oof = pd.read_parquet(OUT / f"oof_{fid}.parquet")
            oc = oof[oof["model"] == cand].sort_values("state_id")
            b = {}
            for r, g in oc.groupby("race_id"):
                vals = []
                for n in NAMES:
                    y = g["target_" + n].to_numpy(float)
                    p = np.clip(g["raw_" + n].to_numpy(float), 1e-15, 1 - 1e-15)
                    vals.append(float(-np.mean(
                        y * np.log(p) + (1 - y) * np.log(1 - p))))
                b[str(r)] = float(np.mean(vals))
            out = V3C.paired_bootstrap(a, b, seed=42, replicates=2000,
                                       ci_level=0.95)
            boot[fid][f"{cand}_vs_{base_name}"] = out
    (RES / "bootstrap_validation.json").write_text(
        json.dumps(boot, indent=1, sort_keys=True) + "\n")

    # ---- V3.1B winner diagnostic (same states, frozen OOF) ----
    diag = {}
    for fid in FOLDS:
        src = f"data/v3/v3_3c/oof_baseline__{fid}.parquet"
        ref = pd.read_parquet(src)
        oof = pd.read_parquet(OUT / f"oof_{fid}.parquet")
        sub = oof[oof["model"] == "l2_logistic"].set_index("state_id")
        rj = ref.set_index("state_id")
        common = sub.index.intersection(rj.index)
        pv = sub.loc[common, "raw_is_top1"].to_numpy(float)
        pr = rj.loc[common, "probability"].to_numpy(float)
        yv = sub.loc[common, "target_is_top1"].to_numpy(float)
        ll_v, _ = ll_race_macro(
            yv, pv, sub.loc[common, "race_id"].astype(str).to_numpy())
        ll_r, _ = ll_race_macro(
            yv, pr, sub.loc[common, "race_id"].astype(str).to_numpy())
        diag[fid] = {
            "n_common_states": int(len(common)),
            "configs_differ": "unknown (frozen OOF reused as-is; C harness C=0.01 same lineage)",
            "correlation": float(np.corrcoef(pv, pr)[0, 1]),
            "max_abs_prob_diff": float(np.abs(pv - pr).max()),
            "ll_v35_pwin": ll_v, "ll_v31b": ll_r,
            "ll_diff": ll_v - ll_r,
            "bit_exact": bool(np.array_equal(pv, pr))}
    (RES / "v31b_diagnostic.json").write_text(
        json.dumps(diag, indent=1, sort_keys=True) + "\n")

    total = round(TIMINGS[f"oof_D3"] - TIMINGS["start"], 1)
    (RES / "compute_profile.json").write_text(json.dumps({
        "total_seconds": total,
        "note": "single learned family (logistic control); deterministic baselines trivial",
    }, indent=1, sort_keys=True) + "\n")
    for fid in FOLDS:
        print(fid, {m: (round(results[fid][m]["primary_raw"], 6),
                        round(results[fid][m]["primary_proj"], 6))
                    for m in results[fid]})
    print("total_seconds:", total)


if __name__ == "__main__":
    main()
