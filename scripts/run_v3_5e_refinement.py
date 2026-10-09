"""V3.5E controlled XGB refinement + temporal calibration (PRE-2025).

Closed 4-config XGB neighborhood around the D anchor; M6 inner selection on
outer-TRAIN history only; one outer evaluation per fold; RAW + optional
history-only threshold calibration -> frozen PAVA projection. 2018-2024
only; 2025 fails closed. Asserts the E protocol hash before anything else,
reproduces the D anchor and C control from persisted OOF before any E fit.
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

PROTO_ID = "4adf3da33b86e734e7b663c6702c64f9377c08ac4318fb5439eebd439aec38e6"
RES = Path("results/v3/v3_5e")
OUT = Path("data/v3/v3_5e")
TARGETS = Path("data/v3/v3_5b/outcome_targets_2018_2024.parquet")
NAMES = list(OC.TARGET_NAMES)
FOLDS = ("D1", "D2", "D3")
TIMINGS: dict = {}
FITS = {"inner": 0, "outer": 0}
CAL_METHODS = ("SIGMOID", "ISOTONIC")


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


def race_primary(per_thr_race: dict) -> dict:
    races = sorted({r for n in NAMES for r in per_thr_race[n]})
    return {r: float(np.mean([per_thr_race[n][r] for n in NAMES]))
            for r in races}


def bootcmp(a: dict, b: dict) -> dict:
    races = sorted(set(a) & set(b))
    deltas = {r: float(b[r]) - float(a[r]) for r in races}
    boot = V3C.paired_bootstrap(a, b, seed=42, replicates=2000, ci_level=0.95)
    imp = sum(1 for v in deltas.values() if v < 0.0)
    wor = sum(1 for v in deltas.values() if v > 0.0)
    return {"n_races": len(races), "mean_delta": float(np.mean(list(
        deltas.values()))), "median_delta": float(np.median(list(
            deltas.values()))),
            "frac_improved": imp / len(races),
            "frac_worsened": wor / len(races),
            "frac_tied": (len(races) - imp - wor) / len(races),
            "ci_lo": float(boot["ci_lo"]), "ci_hi": float(boot["ci_hi"]),
            "ci_level": 0.95, "replicates": 2000, "seed": 42,
            "procedure": "paired race resampling with replacement; "
                         "statistic = mean(LL_B - LL_A); percentile CI",
            "per_race_delta": deltas}


def oof_primary_frame(oof: pd.DataFrame, col: str):
    y = {n: oof["target_" + n].to_numpy(float) for n in NAMES}
    p = {n: oof[col + n].to_numpy(float) for n in NAMES}
    r = oof["race_id"].astype(str).to_numpy()
    prim, per_thr, per_race = primary_of(y, p, r)
    return prim, per_thr, per_race, y, p, r


def main() -> None:
    stamp("start")
    p = json.loads((RES / "refinement_protocol.json").read_text())
    blob = json.dumps({k: v for k, v in p.items() if k != "protocol_identity"},
                      sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        p["protocol_identity"] == PROTO_ID, "E protocol changed after freeze"
    assert len(p["refinement_configurations"]) == 4
    assert p["refinement_configurations"][0]["id"] == "X0"
    assert all(c["max_depth"] == 3 for c in p["refinement_configurations"])
    assert p["calibration_candidates"] == ["RAW", "SIGMOID", "ISOTONIC"]
    d_sum = json.loads(
        Path("results/v3/v3_5d_model_screening.json").read_text())
    assert d_sum["advancing_candidates"] == ["xgb"]
    CFGS = [(c["id"], {k: c[k] for k in ("learning_rate", "max_depth",
                                         "min_child_weight", "n_estimators")})
            for c in p["refinement_configurations"]]
    ORDER = {cid: i for i, (cid, _) in enumerate(CFGS)}

    # ---- Part D anchor + C control reproduction from persisted OOF ----
    d_outer = json.loads(
        Path("results/v3/v3_5d/outer_results.json").read_text())
    c_res = json.loads(
        Path("results/v3/v3_5c/baseline_results.json").read_text())
    anchor, ctrl = {}, {}
    for fid in FOLDS:
        xa = pd.read_parquet(f"data/v3/v3_5d/oof_xgb__{fid}.parquet")
        prim_raw, per_thr_raw, _, _, _, _ = oof_primary_frame(xa, "raw_")
        prim_pj, per_thr_pj, _, _, _, _ = oof_primary_frame(xa, "proj_")
        rec = d_outer["xgb"][fid]
        assert abs(prim_raw - rec["primary_raw"]) < 1e-12, fid
        assert abs(prim_pj - rec["primary_proj"]) < 1e-12, fid
        for n in NAMES:
            assert abs(per_thr_raw[n] -
                       rec["thresholds"][n]["race_macro_ll_raw"]) < 1e-12
            assert abs(per_thr_pj[n] -
                       rec["thresholds"][n]["race_macro_ll_proj"]) < 1e-12
        anchor[fid] = {"oof": xa, "primary_raw": prim_raw,
                       "primary_proj": prim_pj}
        co = pd.read_parquet(f"data/v3/v3_5c/oof_{fid}.parquet")
        co = co[co["model"] == "l2_logistic"].sort_values("state_id")
        cprim_raw, _, _, _, _, _ = oof_primary_frame(co, "raw_")
        cprim_pj, _, _, _, _, _ = oof_primary_frame(co, "proj_")
        assert abs(cprim_raw - c_res[fid]["l2_logistic"]["primary_raw"]) < 1e-12
        assert abs(cprim_pj - c_res[fid]["l2_logistic"]["primary_proj"]) < 1e-12
        ctrl[fid] = {"oof": co, "primary_raw": cprim_raw,
                     "primary_proj": cprim_pj}
    print("D anchor + C control reproduction: exact", flush=True)
    repro = {fid: {"anchor_primary_raw": anchor[fid]["primary_raw"],
                   "anchor_primary_proj": anchor[fid]["primary_proj"],
                   "control_primary_raw": ctrl[fid]["primary_raw"],
                   "control_primary_proj": ctrl[fid]["primary_proj"],
                   "match_1e12": True} for fid in FOLDS}
    write("anchor_reproduction.json", repro)

    # ---- frozen frames ----
    augmented, _ = V3C.load_joined_frame()
    frame = augmented.frame
    frame = frame[frame["season"].isin(
        [2018, 2019, 2020, 2021, 2022, 2023, 2024])].copy()
    if (frame["season"] == 2025).any():
        raise ProtectedHoldoutError("2025 rows reached E refinement")
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_84 = tuple(canonical_predictive_names())
    names_110 = V3C.v3_feature_names(V3C.ARM_B, names_84)
    assert H.check_feature_contract(names_84, names_110)["feature_hash"] == \
        "e054c6fb08c0832970165bcfc0e84f54b70787491af1d545b96a13977fc4c89e"
    tgt = pd.read_parquet(TARGETS)
    full = frame[["state_id", "race_id", "season", "driver_id"]
                 + list(names_110)].copy()
    full = full.merge(tgt[["state_id"] + NAMES], on="state_id",
                      validate="one_to_one")
    assert len(full) == 162728
    full = full.sort_values("state_id", kind="mergesort").reset_index(drop=True)
    stamp("frames")
    OUT.mkdir(parents=True, exist_ok=True)

    # ---- inner selection over closed XGB neighborhood ----
    selection, outer_results, race_level = {}, {}, {}
    cal_support_all: dict = {}
    inner_oos: dict = {}  # outer -> cfg -> inner_id -> thr -> (pred, y, races)
    for fid in FOLDS:
        from raceintel.model_lab import splits as SPLITS
        outer = SPLITS.get_split(fid)
        tr_seasons = [int(s) for s in outer.train_seasons]
        va_seasons = [int(s) for s in outer.validation_seasons]
        trm = full[full["season"].isin(tr_seasons)].reset_index(drop=True)
        vam = full[full["season"].isin(va_seasons)].reset_index(drop=True)
        inner_folds = INNER.resolve_inner_splits(fid)
        assert all(int(s) not in va_seasons
                   for sp in inner_folds
                   for s in (*sp.train_seasons, *sp.validation_seasons))
        rva = vam["race_id"].astype(str).to_numpy()
        yva = {n: vam[n].to_numpy(float) for n in NAMES}
        inner_oos[fid] = {}
        cfg_scores = []
        for cid, cfg in CFGS:
            inner_primaries = []
            inner_oos[fid][cid] = {}
            for sp in inner_folds:
                itr = trm[trm["season"].isin(
                    [int(s) for s in sp.train_seasons])]
                iva = trm[trm["season"].isin(
                    [int(s) for s in sp.validation_seasons])]
                schema = DATA.feature_schema(itr, list(names_110))
                p_inner = {}
                inner_oos[fid][cid][sp.inner_fold_id] = {}
                for n in NAMES:
                    fitted, est, _ = H.fit_family(
                        itr[list(names_110)],
                        pd.Series(itr[n].to_numpy(float)),
                        schema, "xgboost", dict(cfg))
                    FITS["inner"] += 1
                    res = H.predict_family(
                        fitted, est, iva[list(names_110)],
                        iva["state_id"].astype(str).tolist())
                    p_inner[n] = np.asarray(res.values, float)
                    inner_oos[fid][cid][sp.inner_fold_id][n] = (
                        np.asarray(res.values, float),
                        iva[n].to_numpy(float),
                        iva["race_id"].astype(str).to_numpy(),
                        [int(s) for s in sp.validation_seasons])
                y_in = {n: iva[n].to_numpy(float) for n in NAMES}
                r_in = iva["race_id"].astype(str).to_numpy()
                prim, _, _ = primary_of(y_in, p_inner, r_in)
                inner_primaries.append(prim)
            score = float(np.mean(inner_primaries))
            rank = (0 if cid == "X0" else 1, cfg["n_estimators"], ORDER[cid])
            cfg_scores.append((score, rank, cid, cfg))
        best = min(t[0] for t in cfg_scores)
        cands = [t for t in cfg_scores if abs(t[0] - best) <= 1e-6]
        cands.sort(key=lambda t: t[1])
        chosen_id, chosen = cands[0][2], dict(cands[0][3])
        selection[fid] = {
            "chosen": chosen_id, "config": chosen,
            "inner_scores": {t[2]: t[0] for t in cfg_scores},
            "inner_folds": [sp.inner_fold_id for sp in inner_folds]}
        print(fid, "selected", chosen_id,
              {t[2]: round(t[0], 6) for t in cfg_scores}, flush=True)

        # ---- outer refit on full outer TRAIN, predict VALIDATION once ----
        schema = DATA.feature_schema(trm, list(names_110))
        raw = {}
        for n in NAMES:
            fitted, est, _ = H.fit_family(
                trm[list(names_110)], pd.Series(trm[n].to_numpy(float)),
                schema, "xgboost", dict(chosen))
            FITS["outer"] += 1
            res = H.predict_family(
                fitted, est, vam[list(names_110)],
                vam["state_id"].astype(str).tolist())
            raw[n] = np.asarray(res.values, float)

        # ---- temporal calibration (history-only) ----
        inner_ids = [sp.inner_fold_id for sp in inner_folds]
        cal_applied, cal_info, cal_support, cal_hist = {}, {}, {}, {}
        for n in NAMES:
            if len(inner_ids) < 2:
                cal_support[n] = {"status": "CALIBRATION_NOT_EVALUABLE",
                                  "reason": "single inner fold",
                                  "method": "RAW"}
                cal_applied[n] = np.asarray(raw[n], float)
                cal_hist[n] = {"method": "RAW", "history_eval": None}
                continue
            earlier, later = inner_ids[:-1], inner_ids[-1]
            fp = np.concatenate([inner_oos[fid][chosen_id][i][n][0]
                                 for i in earlier])
            fy = np.concatenate([inner_oos[fid][chosen_id][i][n][1]
                                 for i in earlier])
            fr = np.concatenate([inner_oos[fid][chosen_id][i][n][2]
                                 for i in earlier])
            fseasons = sorted({s for i in earlier
                               for s in inner_oos[fid][chosen_id][i][n][3]})
            npos, nneg = int((fy == 1).sum()), int((fy == 0).sum())
            gates = (len(fy) >= 1000 and len(set(map(str, fr))) >= 10
                     and npos >= 20 and nneg >= 20 and len(fseasons) >= 1)
            cal_support[n] = {"status": "EVALUABLE" if gates
                              else "CALIBRATION_NOT_EVALUABLE",
                              "n_states": int(len(fy)),
                              "n_races": int(len(set(map(str, fr)))),
                              "n_positive": npos, "n_negative": nneg,
                              "seasons": fseasons}
            lp, ly, lr = inner_oos[fid][chosen_id][later][n][:3]
            lr = lr.astype(str)
            base = AGG.race_macro(ly, lp, lr, "log_loss")["value"]
            base_br = MET.brier(ly, lp)
            cands_cal = {}
            if gates:
                for m, fit in (("SIGMOID", CALSEL.fit_platt),
                               ("ISOTONIC", CALSEL.fit_isotonic)):
                    try:
                        cb = fit(fp, fy)
                    except Exception as e:  # noqa: BLE001
                        cands_cal[m] = {"error": str(e)}
                        continue
                    t = np.asarray(cb.transform(lp), float)
                    dll = float(AGG.race_macro(ly, t, lr, "log_loss")["value"]
                                - base)
                    dbr = float(MET.brier(ly, t) - base_br)
                    if m == "SIGMOID":
                        dg = cb.diagnostics()
                        patho = not (np.isfinite([dg["coefficient"],
                                                  dg["intercept"]]).all()
                                     and dg["coefficient"] > 0.0)
                    else:
                        patho = False
                    cands_cal[m] = {"dll": dll, "dbr": dbr,
                                    "pathological": bool(patho)}
                admitted = [m for m in CAL_METHODS
                            if isinstance(cands_cal.get(m), dict)
                            and "dll" in cands_cal[m]
                            and cands_cal[m]["dll"] < -1e-4
                            and cands_cal[m]["dbr"] <= 1e-12
                            and not cands_cal[m]["pathological"]]
                admitted.sort(key=lambda m: (
                    min(cands_cal[m]["dll"], 0.0),
                    CAL_METHODS.index(m)))
                method = admitted[0] if admitted else "RAW"
            else:
                method = "RAW"
            cal_hist[n] = {"method": method, "history_eval": {
                "later_fold": later, "raw_ll": float(base),
                "raw_brier": float(base_br), "candidates": cands_cal}}
            if method == "RAW":
                cal_support[n]["method"] = "RAW"
                cal_applied[n] = np.asarray(raw[n], float)
                continue
            pool_p = np.concatenate(
                [inner_oos[fid][chosen_id][i][n][0] for i in inner_ids])
            pool_y = np.concatenate(
                [inner_oos[fid][chosen_id][i][n][1] for i in inner_ids])
            fit = CALSEL.fit_platt if method == "SIGMOID" \
                else CALSEL.fit_isotonic
            cb = fit(pool_p, pool_y)
            t_outer = np.asarray(cb.transform(np.asarray(raw[n], float)),
                                 float)
            if method == "ISOTONIC":
                frac_extreme = float(np.mean((t_outer == 0.0)
                                             | (t_outer == 1.0)))
                if frac_extreme > 0.5:
                    cal_hist[n]["method"] = "RAW"
                    cal_hist[n]["tail_reject"] = frac_extreme
                    cal_support[n]["method"] = "RAW"
                    cal_applied[n] = np.asarray(raw[n], float)
                    continue
            cal_support[n]["method"] = method
            cal_applied[n] = t_outer
        cal_before = {n: np.asarray(cal_applied[n], float) for n in NAMES}
        mat_raw = np.column_stack([np.asarray(raw[n], float) for n in NAMES])
        mat_cal = np.column_stack([cal_before[n] for n in NAMES])
        proj, diag = OC.project_isotonic(mat_cal)
        OC.derived_bands(proj)

        thr = {}
        for j, n in enumerate(NAMES):
            d = AGG.race_macro(yva[n], mat_raw[:, j], rva, "log_loss")
            e = AGG.race_macro(yva[n], cal_before[n], rva, "log_loss")
            f = AGG.race_macro(yva[n], proj[:, j], rva, "log_loss")
            thr[n] = {
                "race_macro_ll_raw": float(d["value"]),
                "race_macro_ll_cal": float(e["value"]),
                "race_macro_ll_proj": float(f["value"]),
                "brier_raw": MET.brier(yva[n], mat_raw[:, j]),
                "brier_cal": MET.brier(yva[n], cal_before[n]),
                "brier_proj": MET.brier(yva[n], proj[:, j]),
                "ece_raw": CAL.expected_calibration_error(
                    yva[n], mat_raw[:, j]),
                "ece_cal": CAL.expected_calibration_error(
                    yva[n], cal_before[n]),
                "ece_proj": CAL.expected_calibration_error(
                    yva[n], proj[:, j]),
                "state_pooled_ll_raw": AGG.state_pooled(
                    yva[n], mat_raw[:, j], rva, "log_loss")["value"],
                "state_pooled_ll_cal": AGG.state_pooled(
                    yva[n], cal_before[n], rva, "log_loss")["value"],
                "state_pooled_ll_proj": AGG.state_pooled(
                    yva[n], proj[:, j], rva, "log_loss")["value"]}
        prim_raw = float(np.mean([thr[n]["race_macro_ll_raw"] for n in NAMES]))
        prim_cal = float(np.mean([thr[n]["race_macro_ll_cal"] for n in NAMES]))
        prim_pj = float(np.mean([thr[n]["race_macro_ll_proj"] for n in NAMES]))
        outer_results[fid] = {
            "selected_config": chosen_id, "config": chosen,
            "primary_raw": prim_raw, "primary_cal": prim_cal,
            "primary_proj": prim_pj,
            "projected_minus_raw": prim_pj - prim_raw,
            "thresholds": thr, "projection": diag, "bands_valid": True,
            "calibration": {n: cal_hist[n] for n in NAMES}}
        write("outer_results.json", outer_results)
        write("selection_results.json",
              {"inner_selection": selection, "fits": dict(FITS)})
        cal_support_all[fid] = cal_support
        write("calibration_support.json", cal_support_all)
        print(fid, "outer raw/cal/proj", round(prim_raw, 6),
              round(prim_cal, 6), round(prim_pj, 6), flush=True)

        # ---- OOF artifact ----
        stage = STAGES.stage_partition(
            vam["race_progress_frac"].to_numpy(float))
        rows = []
        for i in range(len(vam)):
            row = {"state_id": str(vam["state_id"].iloc[i]),
                   "season": int(vam["season"].iloc[i]),
                   "race_id": str(vam["race_id"].iloc[i]),
                   "driver_id": str(vam["driver_id"].iloc[i]),
                   "stage": str(stage[i]), "fold": fid, "model": "xgb_e"}
            for n in NAMES:
                row["target_" + n] = float(yva[n][i])
            for j, n in enumerate(NAMES):
                row["raw_" + n] = float(mat_raw[i, j])
                row["cal_" + n] = float(mat_cal[i, j])
                row["proj_" + n] = float(proj[i, j])
            rows.append(row)
        oof = pd.DataFrame(rows).sort_values(
            "state_id", kind="mergesort").reset_index(drop=True)
        oof.to_parquet(OUT / f"oof_xgb_e__{fid}.parquet", index=False)

    race_level_out = {}
    for fid in FOLDS:
        oof = pd.read_parquet(OUT / f"oof_xgb_e__{fid}.parquet")
        _, _, per_race_raw, _, _, _ = oof_primary_frame(oof, "raw_")
        _, _, per_race_pj, _, _, _ = oof_primary_frame(oof, "proj_")
        race_level_out[fid] = {"raw": per_race_raw, "proj": per_race_pj}
    write("selection_results.json",
          {"inner_selection": selection, "fits": dict(FITS)})
    write("outer_results.json", outer_results)
    write("race_level_results.json", race_level_out)
    ids = {}
    for f in sorted(OUT.glob("oof_*.parquet")):
        ids[f.name] = {"path": str(f),
                       "sha256": hashlib.sha256(f.read_bytes()).hexdigest(),
                       "rows": int(pd.read_parquet(f).shape[0])}
    write("prediction_identities.json", ids)
    total = round(time.perf_counter() - TIMINGS["start"], 1)
    write("compute_profile.json",
          {"fits": dict(FITS), "total_seconds": total})
    print("fits:", FITS, "total_seconds:", total, flush=True)


if __name__ == "__main__":
    main()
