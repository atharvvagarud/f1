"""V3.5D temporal screening: HGB + XGB vs frozen logistic control.

Closed set, preregistered grids, inner selection on outer-TRAIN history
only, one outer evaluation per fold. 2018-2024 only; 2025 fails closed.
Asserts the D protocol hash before the first challenger fit.
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
from raceintel.model_lab import inner_splits as INNER
from raceintel.model_lab import stages as STAGES
from raceintel.model_lab.errors import ProtectedHoldoutError

RES = Path("results/v3/v3_5d")
OUT = Path("data/v3/v3_5d")
TARGETS = Path("data/v3/v3_5b/outcome_targets_2018_2024.parquet")
NAMES = list(OC.TARGET_NAMES)
KS = list(OC.THRESHOLD_ORDER)
FOLDS = ("D1", "D2", "D3")
TIMINGS = {}
FITS = {"inner": 0, "outer": 0}


def stamp(key):
    TIMINGS[key] = time.perf_counter()


def primary_of(y_dict, p_dict, races):
    """Mean over thresholds of race-macro LL; returns (primary, per_thr)."""
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
    p = json.loads((RES / "screening_protocol.json").read_text())
    blob = json.dumps({k: v for k, v in p.items() if k != "protocol_identity"},
                      sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        p["protocol_identity"] == \
        "8d82448ea5888beb6dd8f54c35ebb08ba40c58bd66b652bab6f0d39dfdf78ba4", \
        "D protocol changed after freeze"
    assert p["candidate_families"] == \
        ["LOGISTIC_CONTROL", "HIST_GRADIENT_BOOSTING", "XGBOOST"]
    assert len(p["hgb_grid"]) <= 6 and len(p["xgb_grid"]) <= 6

    # ---- control reproduction (Part M) ----
    c_res = json.loads(
        Path("results/v3/v3_5c/baseline_results.json").read_text())
    repro = {}
    for fid in FOLDS:
        o = pd.read_parquet(f"data/v3/v3_5c/oof_{fid}.parquet")
        sub = o[o["model"] == "l2_logistic"].sort_values("state_id")
        y = {n: sub["target_" + n].to_numpy(float) for n in NAMES}
        pr = {n: sub["raw_" + n].to_numpy(float) for n in NAMES}
        pj = {n: sub["proj_" + n].to_numpy(float) for n in NAMES}
        rr = sub["race_id"].astype(str).to_numpy()
        prim_raw, _, _ = primary_of(y, pr, rr)
        prim_pj, _, _ = primary_of(y, pj, rr)
        rec_raw = c_res[fid]["l2_logistic"]["primary_raw"]
        rec_pj = c_res[fid]["l2_logistic"]["primary_proj"]
        assert abs(prim_raw - rec_raw) < 1e-12, (fid, prim_raw, rec_raw)
        assert abs(prim_pj - rec_pj) < 1e-12, (fid, prim_pj, rec_pj)
        repro[fid] = {"primary_raw": prim_raw, "primary_proj": prim_pj,
                      "recorded_raw": rec_raw, "recorded_proj": rec_pj,
                      "match": True}
    print("control reproduction: exact")

    # ---- frozen frames ----
    augmented, _ = V3C.load_joined_frame()
    frame = augmented.frame
    frame = frame[frame["season"].isin(
        [2018, 2019, 2020, 2021, 2022, 2023, 2024])].copy()
    if (frame["season"] == 2025).any():
        raise ProtectedHoldoutError("2025 rows reached D screening")
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_84 = tuple(canonical_predictive_names())
    names_110 = V3C.v3_feature_names(V3C.ARM_B, names_84)
    assert H.check_feature_contract(names_84, names_110)["feature_hash"] == \
        "e054c6fb08c0832970165bcfc0e84f54b70787491af1d545b96a13977fc4c89e"
    tgt = pd.read_parquet(TARGETS)
    full = frame[["state_id", "race_id", "season", "driver_id"]
                  + list(names_110)].copy()
    # race_progress_frac is a member of the frozen 110 (CORE_26); stage
    # analysis reads it from the feature columns (no duplicate selection).
    assert "race_progress_frac" in names_110
    full = full.merge(tgt[["state_id"] + NAMES], on="state_id",
                      validate="one_to_one")
    assert len(full) == 162728
    full = full.sort_values("state_id", kind="mergesort").reset_index(drop=True)
    schema_full = DATA.feature_schema(full, list(names_110))
    _ = schema_full
    stamp("frames")

    families = {
        "hgb": ("hist_gradient_boosting", p["hgb_grid"]),
        "xgb": ("xgboost", p["xgb_grid"]),
    }
    tie_order = {
        "hgb": lambda cfg: (cfg["learning_rate"], cfg["max_leaf_nodes"],
                            -cfg["min_samples_leaf"]),
        "xgb": lambda cfg: (cfg["learning_rate"], -cfg["min_child_weight"],
                            cfg["max_depth"]),
    }
    selection, outer_results, race_level = {}, {}, {}
    OUT.mkdir(parents=True, exist_ok=True)

    for fid in FOLDS:
        from raceintel.model_lab import splits as SPLITS
        outer = SPLITS.get_split(fid)
        tr_seasons = [int(s) for s in outer.train_seasons]
        va_seasons = [int(s) for s in outer.validation_seasons]
        trm = full[full["season"].isin(tr_seasons)].reset_index(drop=True)
        vam = full[full["season"].isin(va_seasons)].reset_index(drop=True)
        assert len(trm) + len(vam) == len(
            full[full["season"].isin(tr_seasons + va_seasons)])
        inner_folds = INNER.resolve_inner_splits(fid)
        assert all(int(s) not in va_seasons
                   for sp in inner_folds
                   for s in (*sp.train_seasons, *sp.validation_seasons))
        rva = vam["race_id"].astype(str).to_numpy()
        yva = {n: vam[n].to_numpy(float) for n in NAMES}

        for fam, (family, grid) in families.items():
            # ---- inner selection on outer-TRAIN history only ----
            cfg_scores = []
            for cfg in grid:
                inner_primaries = []
                for sp in inner_folds:
                    itr = trm[trm["season"].isin(
                        [int(s) for s in sp.train_seasons])]
                    iva = trm[trm["season"].isin(
                        [int(s) for s in sp.validation_seasons])]
                    schema = DATA.feature_schema(itr, list(names_110))
                    p_inner = {}
                    for n in NAMES:
                        fitted, est, _ = H.fit_family(
                            itr[list(names_110)], pd.Series(
                                itr[n].to_numpy(float)),
                            schema, family, dict(cfg))
                        FITS["inner"] += 1
                        res = H.predict_family(
                            fitted, est, iva[list(names_110)],
                            iva["state_id"].astype(str).tolist())
                        p_inner[n] = np.asarray(res.values, float)
                    y_in = {n: iva[n].to_numpy(float) for n in NAMES}
                    r_in = iva["race_id"].astype(str).to_numpy()
                    prim, _, _ = primary_of(y_in, p_inner, r_in)
                    inner_primaries.append(prim)
                score = float(np.mean(inner_primaries))
                cfg_scores.append((score, tie_order[fam](cfg), cfg))
            # lowest inner score wins; ties within 1e-6 -> prereg order
            best_score = min(t[0] for t in cfg_scores)
            cands = [t for t in cfg_scores if abs(t[0] - best_score) <= 1e-6]
            cands.sort(key=lambda t: t[1])
            chosen = cands[0][2]
            selection.setdefault(fam, {})[fid] = {
                "chosen": chosen,
                "inner_scores": {json.dumps(c, sort_keys=True): s
                                 for s, _, c in cfg_scores},
                "inner_folds": [sp.inner_fold_id for sp in inner_folds]}

            # ---- outer refit on full outer TRAIN, predict VALIDATION once ----
            stamp(f"outer_{fam}_{fid}")
            schema = DATA.feature_schema(trm, list(names_110))
            raw = {}
            for n in NAMES:
                fitted, est, _ = H.fit_family(
                    trm[list(names_110)], pd.Series(
                        trm[n].to_numpy(float)),
                    schema, family, dict(chosen))
                FITS["outer"] += 1
                res = H.predict_family(
                    fitted, est, vam[list(names_110)],
                    vam["state_id"].astype(str).tolist())
                raw[n] = np.asarray(res.values, float)
            mat = np.column_stack([raw[n] for n in NAMES])
            proj, diag = OC.project_isotonic(mat)
            OC.derived_bands(proj)

            thr, per_race = {}, {}
            for j, n in enumerate(NAMES):
                d = AGG.race_macro(yva[n], raw[n], rva, "log_loss")
                v_raw, pr_raw = float(d["value"]), {
                    k: float(v) for k, v in d["per_race"].items()}
                e = AGG.race_macro(yva[n], proj[:, j], rva, "log_loss")
                v_prj, pr_prj = float(e["value"]), {
                    k: float(v) for k, v in e["per_race"].items()}
                thr[n] = {
                    "race_macro_ll_raw": v_raw, "race_macro_ll_proj": v_prj,
                    "brier_raw": MET.brier(yva[n], raw[n]),
                    "brier_proj": MET.brier(yva[n], proj[:, j]),
                    "ece_raw": CAL.expected_calibration_error(yva[n], raw[n]),
                    "ece_proj": CAL.expected_calibration_error(
                        yva[n], proj[:, j]),
                    "state_pooled_ll_raw": AGG.state_pooled(
                        yva[n], raw[n], rva, "log_loss")["value"],
                    "state_pooled_ll_proj": AGG.state_pooled(
                        yva[n], proj[:, j], rva, "log_loss")["value"]}
                per_race[n] = {"raw": pr_raw, "proj": pr_prj}
            prim_raw = float(np.mean([thr[n]["race_macro_ll_raw"]
                                      for n in NAMES]))
            prim_pj = float(np.mean([thr[n]["race_macro_ll_proj"]
                                     for n in NAMES]))
            outer_results.setdefault(fam, {})[fid] = {
                "primary_raw": prim_raw, "primary_proj": prim_pj,
                "projected_minus_raw": prim_pj - prim_raw,
                "thresholds": thr, "projection": diag, "bands_valid": True}
            race_level.setdefault(fam, {})[fid] = per_race

            # ---- OOF artifact ----
            stage = STAGES.stage_partition(
                vam["race_progress_frac"].to_numpy(float))
            rows = []
            for i in range(len(vam)):
                row = {"state_id": str(vam["state_id"].iloc[i]),
                       "season": int(vam["season"].iloc[i]),
                       "race_id": str(vam["race_id"].iloc[i]),
                       "driver_id": str(vam["driver_id"].iloc[i]),
                       "stage": str(stage[i]), "fold": fid, "model": fam}
                for n in NAMES:
                    row["target_" + n] = float(yva[n][i])
                for j, n in enumerate(NAMES):
                    row["raw_" + n] = float(mat[i, j])
                    row["proj_" + n] = float(proj[i, j])
                rows.append(row)
            oof = pd.DataFrame(rows).sort_values(
                "state_id", kind="mergesort").reset_index(drop=True)
            dest = OUT / f"oof_{fam}__{fid}.parquet"
            oof.to_parquet(dest, index=False)

    (RES / "selection_results.json").write_text(json.dumps(
        {"inner_selection": selection,
         "fits": dict(FITS)}, indent=1, sort_keys=True) + "\n")
    (RES / "outer_results.json").write_text(json.dumps(
        outer_results, indent=1, sort_keys=True) + "\n")
    (RES / "race_level_results.json").write_text(json.dumps(
        race_level, indent=1, sort_keys=True) + "\n")
    ids = {}
    for f in sorted(OUT.glob("oof_*.parquet")):
        ids[f.name] = {"path": str(f),
                       "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
                       "rows": int(pd.read_parquet(f).shape[0])}
    (RES / "prediction_identities.json").write_text(json.dumps(
        ids, indent=1, sort_keys=True) + "\n")
    total = round(time.perf_counter() - TIMINGS["start"], 1)
    (RES / "compute_profile.json").write_text(json.dumps(
        {"fits": dict(FITS), "total_seconds": total}, indent=1,
        sort_keys=True) + "\n")
    for fam in ("hgb", "xgb"):
        print(fam, {fid: (round(outer_results[fam][fid]["primary_raw"], 6),
                          round(outer_results[fam][fid]["primary_proj"], 6))
                    for fid in FOLDS})
    print("fits:", FITS, "total_seconds:", total)


if __name__ == "__main__":
    main()
