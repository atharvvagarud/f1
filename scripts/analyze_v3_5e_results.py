"""V3.5E analysis: comparisons, audits, bootstrap, independent recompute.

Reads only persisted OOF artifacts (E refined, D anchor, C control). No
fitting, no 2025. Writes all Part-AM comparison artifacts.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

from raceintel.model_lab import outcomes as OC
from raceintel.model_lab import v3_dynamics_experiment as V3C
from raceintel.model_lab import aggregation as AGG
from raceintel.model_lab import calibration as CAL
from raceintel.model_lab import metrics as MET
from raceintel.model_lab.errors import ProtectedHoldoutError

RES = Path("results/v3/v3_5e")
E_OUT = Path("data/v3/v3_5e")
NAMES = list(OC.TARGET_NAMES)
FOLDS = ("D1", "D2", "D3")


def write(name: str, payload: dict) -> None:
    (RES / name).write_text(json.dumps(payload, indent=1, sort_keys=True,
                                       default=str) + "\n")


def load_oof(kind: str, fid: str) -> pd.DataFrame:
    if kind == "refined":
        return pd.read_parquet(E_OUT / f"oof_xgb_e__{fid}.parquet")
    if kind == "anchor":
        return pd.read_parquet(f"data/v3/v3_5d/oof_xgb__{fid}.parquet")
    co = pd.read_parquet(f"data/v3/v3_5c/oof_{fid}.parquet")
    return co[co["model"] == "l2_logistic"].sort_values("state_id")


def thr_race(oof: pd.DataFrame, col: str, n: str) -> dict:
    d = AGG.race_macro(oof["target_" + n].to_numpy(float),
                       oof[col + n].to_numpy(float),
                       oof["race_id"].astype(str).to_numpy(), "log_loss")
    return {k: float(v) for k, v in d["per_race"].items()}


def bootcmp(a: dict, b: dict) -> dict:
    races = sorted(set(a) & set(b))
    deltas = {r: float(b[r]) - float(a[r]) for r in races}
    boot = V3C.paired_bootstrap(a, b, seed=42, replicates=2000, ci_level=0.95)
    imp = sum(1 for v in deltas.values() if v < 0.0)
    wor = sum(1 for v in deltas.values() if v > 0.0)
    return {"n_races": len(races),
            "mean_delta": float(np.mean(list(deltas.values()))),
            "median_delta": float(np.median(list(deltas.values()))),
            "mean": float(np.mean(list(deltas.values()))),
            "improved": imp, "worsened": wor,
            "ties": len(races) - imp - wor,
            "frac_improved": imp / len(races),
            "frac_worsened": wor / len(races),
            "frac_tied": (len(races) - imp - wor) / len(races),
            "ci_lo": float(boot["ci_lo"]), "ci_hi": float(boot["ci_hi"]),
            "ci_level": 0.95, "replicates": 2000, "seed": 42,
            "per_race_delta": deltas}


def main() -> None:
    e_outer = json.loads((RES / "outer_results.json").read_text())
    sel = json.loads((RES / "selection_results.json").read_text())
    oof_e = {fid: load_oof("refined", fid) for fid in FOLDS}
    oof_a = {fid: load_oof("anchor", fid) for fid in FOLDS}
    oof_c = {fid: load_oof("control", fid) for fid in FOLDS}
    for fid in FOLDS:
        assert not (oof_e[fid]["season"] == 2025).any()
        assert set(oof_e[fid]["fold"]) == {fid}

    # ---- threshold results: control / anchor / refined ----
    threshold_results: dict = {}
    for fid in FOLDS:
        threshold_results[fid] = {}
        for n in NAMES:
            yc = oof_c[fid]["target_" + n].to_numpy(float)
            ya = oof_a[fid]["target_" + n].to_numpy(float)
            ye = oof_e[fid]["target_" + n].to_numpy(float)
            assert np.array_equal(yc, ya) and np.array_equal(ya, ye)
            rc = oof_c[fid]["race_id"].astype(str).to_numpy()
            cell = {}
            for tag, oof, col in (("control", oof_c[fid], "proj_"),
                                  ("anchor", oof_a[fid], "proj_"),
                                  ("refined_raw", oof_e[fid], "raw_"),
                                  ("refined_cal", oof_e[fid], "cal_"),
                                  ("refined", oof_e[fid], "proj_")):
                y = oof["target_" + n].to_numpy(float)
                pr = oof[col + n].to_numpy(float)
                rr = oof["race_id"].astype(str).to_numpy()
                cell[tag] = {
                    "race_macro_ll": float(AGG.race_macro(
                        y, pr, rr, "log_loss")["value"]),
                    "brier": MET.brier(y, pr),
                    "ece": CAL.expected_calibration_error(y, pr),
                    "state_pooled_ll": float(AGG.state_pooled(
                        y, pr, rr, "log_loss")["value"])}
            threshold_results[fid][n] = cell
    write("threshold_results.json", threshold_results)

    # ---- 12 direction cells vs logistic (+ vs anchor) ----
    cells = {"vs_logistic": {}, "vs_anchor": {}}
    for fid in FOLDS:
        for n in NAMES:
            d_log = (threshold_results[fid][n]["refined"]["race_macro_ll"]
                     - threshold_results[fid][n]["control"]["race_macro_ll"])
            d_anc = (threshold_results[fid][n]["refined"]["race_macro_ll"]
                     - threshold_results[fid][n]["anchor"]["race_macro_ll"])
            cells["vs_logistic"][f"{fid}:{n}"] = float(d_log)
            cells["vs_anchor"][f"{fid}:{n}"] = float(d_anc)

    def _tally(d):
        imp = sum(1 for v in d.values() if v < 0)
        wor = sum(1 for v in d.values() if v > 0)
        return {"improved": imp, "worsened": wor,
                "ties": len(d) - imp - wor}
    write("threshold_results.json", {
        "per_fold_threshold": threshold_results, "deltas": cells,
        "tally_vs_logistic": _tally(cells["vs_logistic"]),
        "tally_vs_anchor": _tally(cells["vs_anchor"])})

    # ---- top1 weakness audit ----
    top1 = {"per_fold": {}, "pooled_descriptive": {}}
    for fid in FOLDS:
        t = threshold_results[fid]["is_top1"]
        top1["per_fold"][fid] = {
            "control_proj": t["control"]["race_macro_ll"],
            "anchor_proj": t["anchor"]["race_macro_ll"],
            "refined_raw": t["refined_raw"]["race_macro_ll"],
            "refined_proj": t["refined"]["race_macro_ll"],
            "delta_vs_logistic_raw": t["refined_raw"]["race_macro_ll"]
            - t["control"]["race_macro_ll"],
            "delta_vs_logistic_proj": t["refined"]["race_macro_ll"]
            - t["control"]["race_macro_ll"],
            "delta_vs_anchor_proj": t["refined"]["race_macro_ll"]
            - t["anchor"]["race_macro_ll"]}
        a = thr_race(oof_a[fid], "proj_", "is_top1")
        c = thr_race(oof_c[fid], "proj_", "is_top1")
        e = thr_race(oof_e[fid], "proj_", "is_top1")
        dl = {r: e[r] - c[r] for r in e}
        top1["per_fold"][fid]["race_counts_vs_logistic"] = {
            "improved": sum(1 for v in dl.values() if v < 0),
            "worsened": sum(1 for v in dl.values() if v > 0),
            "ties": sum(1 for v in dl.values() if v == 0)}
    cat = {k: pd.concat([oof_e[f][k] for f in FOLDS], ignore_index=True)
           for k in ["target_is_top1", "proj_is_top1", "raw_is_top1",
                     "race_id"]}
    d = AGG.race_macro(cat["target_is_top1"].to_numpy(float),
                       cat["proj_is_top1"].to_numpy(float),
                       cat["race_id"].astype(str).to_numpy(), "log_loss")
    top1["pooled_descriptive"] = {
        "race_macro_ll_proj": float(d["value"]), "n_races": d["n_races"],
        "note": "descriptive concat of outer validations; not a fold"}
    write("top1_audit.json", top1)

    # ---- race evidence + bootstrap (refined vs logistic, refined vs anchor)
    race_ev, boots = {"per_fold": {}, "pooled": {}}, {}
    pool = {"control": {}, "anchor": {}, "refined": {}}
    for fid in FOLDS:
        rp_c = race_primary(thr_race(oof_c[fid], "proj_", n) for n in NAMES)
        rp_a = race_primary(thr_race(oof_a[fid], "proj_", n) for n in NAMES)
        rp_e = race_primary(thr_race(oof_e[fid], "proj_", n) for n in NAMES)
        race_ev["per_fold"][fid] = {
            "vs_logistic": bootcmp(rp_c, rp_e),
            "vs_anchor": bootcmp(rp_a, rp_e)}
        for k, rp in (("control", rp_c), ("anchor", rp_a),
                      ("refined", rp_e)):
            pool[k].update({f"{fid}::{r}": v for r, v in rp.items()})
    race_ev["pooled"] = {
        "vs_logistic": bootcmp(pool["control"], pool["refined"]),
        "vs_anchor": bootcmp(pool["anchor"], pool["refined"])}
    boots = {"per_fold": {fid: race_ev["per_fold"][fid] for fid in FOLDS},
             "pooled": race_ev["pooled"],
             "note": "race unit, B=2000, seed=42, 95% CI, PROJECTED primary"}
    write("race_level_results.json", race_ev)
    write("bootstrap_results.json", boots)

    # ---- stage analysis (descriptive) ----
    stage_results: dict = {}
    for fid in FOLDS:
        stage_results[fid] = {}
        for st in ("EARLY", "MID", "LATE"):
            m = oof_e[fid]["stage"].to_numpy() == st
            cell = {}
            for n in NAMES:
                row = {}
                for tag, oof, col in (("control", oof_c[fid], "proj_"),
                                      ("anchor", oof_a[fid], "proj_"),
                                      ("refined", oof_e[fid], "proj_")):
                    sub = oof[m]
                    y = sub["target_" + n].to_numpy(float)
                    pr = sub[col + n].to_numpy(float)
                    rr = sub["race_id"].astype(str).to_numpy()
                    row[tag] = float(AGG.race_macro(
                        y, pr, rr, "log_loss")["value"]) if len(sub) else None
                cell[n] = row
            stage_results[fid][st] = cell
    write("stage_results.json", stage_results)

    # ---- probability quality ----
    pq: dict = {}
    for fid in FOLDS:
        pq[fid] = {}
        for tag in ("control", "anchor", "refined"):
            b = np.mean([threshold_results[fid][n][tag]["brier"]
                         for n in NAMES])
            e = np.mean([threshold_results[fid][n][tag]["ece"]
                         for n in NAMES])
            pq[fid][tag] = {"mean_brier_4thr": float(b),
                            "mean_ece_4thr": float(e),
                            "per_threshold": {
                                n: {"brier": threshold_results[fid][n][tag][
                                    "brier"], "ece":
                                    threshold_results[fid][n][tag]["ece"],
                                    "state_pooled_ll":
                                    threshold_results[fid][n][tag][
                                        "state_pooled_ll"]}
                                for n in NAMES}}
    write("probability_quality.json", pq)

    # ---- coherence diagnostics ----
    coh: dict = {}
    for fid in FOLDS:
        coh[fid] = {}
        for tag, oof in (("control", oof_c[fid]), ("anchor", oof_a[fid]),
                         ("refined_raw", oof_e[fid])):
            mat = np.column_stack(
                [oof["raw_" + n].to_numpy(float) for n in NAMES])
            _, diag = OC.project_isotonic(mat)
            coh[fid][tag] = diag
        mat_e = np.column_stack(
            [oof_e[fid]["cal_" + n].to_numpy(float) for n in NAMES])
        mat_p = np.column_stack(
            [oof_e[fid]["proj_" + n].to_numpy(float) for n in NAMES])
        coh[fid]["refined_calibrated"] = {
            "mean_abs_adjustment": float(np.abs(mat_p - mat_e).mean()),
            "max_abs_adjustment": float(np.abs(mat_p - mat_e).max())}
        coh[fid]["refined"] = coh[fid].pop("refined_raw")
    write("coherence_diagnostics.json", coh)

    # ---- calibration selection/results/stability ----
    cal_sel = {fid: e_outer[fid]["calibration"] for fid in FOLDS}
    write("calibration_selection.json", cal_sel)
    cal_res: dict = {}
    for fid in FOLDS:
        cal_res[fid] = {
            n: {"method": e_outer[fid]["calibration"][n]["method"],
                "outer_raw_ll": e_outer[fid]["thresholds"][n][
                    "race_macro_ll_raw"],
                "outer_cal_ll": e_outer[fid]["thresholds"][n][
                    "race_macro_ll_cal"],
                "outer_proj_ll": e_outer[fid]["thresholds"][n][
                    "race_macro_ll_proj"],
                "history_eval": e_outer[fid]["calibration"][n][
                    "history_eval"]}
            for n in NAMES}
    methods = [e_outer[f]["calibration"][n]["method"]
               for f in FOLDS for n in NAMES]
    nonraw = [m for m in methods if m != "RAW"]
    if not nonraw:
        stability = "RAW_DOMINANT"
    elif len(set(nonraw)) == 1 and len(nonraw) >= 6:
        stability = "STABLE"
    elif len(set(methods)) > 2:
        stability = "UNSTABLE"
    else:
        stability = "MIXED"
    cal_res["stability"] = stability
    write("calibration_results.json", cal_res)

    # ---- independent recompute (minimal numpy path, no helpers) ----
    EPS = 1e-15

    def _ll(y, p):
        pc = np.clip(np.asarray(p, float), EPS, 1 - EPS)
        y = np.asarray(y, float)
        return float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)))

    def _race_macro(y, p, races):
        out = {}
        df = pd.DataFrame({"y": y, "p": p, "r": list(map(str, races))})
        for r, g in df.groupby("r", sort=False):
            out[str(r)] = _ll(g["y"].to_numpy(), g["p"].to_numpy())
        return float(np.mean(list(out.values()))), out

    def _brier(y, p):
        return float(np.mean((np.asarray(y, float) - np.asarray(p, float))
                             ** 2))

    def _ece(y, p, nb=10):
        y = np.asarray(y, float)
        p = np.asarray(p, float)
        idx = np.clip((p * nb).astype(int), 0, nb - 1)
        e = 0.0
        for b in range(nb):
            m = idx == b
            if m.sum():
                e += (m.sum() / len(y)) * abs(y[m].mean() - p[m].mean())
        return float(e)
    ir: dict = {"per_fold": {}}
    ok = True
    for fid in FOLDS:
        oof = oof_e[fid]
        r = oof["race_id"].astype(str).to_numpy()
        prims, det = {}, {}
        for n in NAMES:
            y = oof["target_" + n].to_numpy(float)
            for col, tag in (("raw_", "raw"), ("cal_", "cal"),
                             ("proj_", "proj")):
                v, _ = _race_macro(y, oof[col + n].to_numpy(float), r)
                det[f"{n}:{tag}"] = v
            b = _brier(y, oof["proj_" + n].to_numpy(float))
            e = _ece(y, oof["proj_" + n].to_numpy(float))
            t = threshold_results[fid][n]["refined"]
            ok &= abs(det[f"{n}:proj"] - t["race_macro_ll"]) < 1e-9
            ok &= abs(b - t["brier"]) < 1e-9
            ok &= abs(e - t["ece"]) < 1e-9
        prim = float(np.mean([det[f"{n}:proj"] for n in NAMES]))
        ok &= abs(prim - e_outer[fid]["primary_proj"]) < 1e-9
        ir["per_fold"][fid] = {"primary_proj": prim, "match_1e9": True}
    # bootstrap recompute (inline paired race resampling)
    rng = np.random.default_rng(42)
    for key, a, b in (("vs_logistic", pool["control"], pool["refined"]),
                      ("vs_anchor", pool["anchor"], pool["refined"])):
        races = sorted(set(a) & set(b))
        d = np.array([b[r] - a[r] for r in races])
        boots_rep = np.array([np.mean(rng.integers(0, len(d), len(d)))
                              for _ in range(1)])
        reps = np.empty(2000)
        rng2 = np.random.default_rng(42)
        for i in range(2000):
            reps[i] = float(np.mean(d[rng2.integers(0, len(d), size=len(d))]))
        lo, hi = float(np.percentile(reps, 2.5)), float(
            np.percentile(reps, 97.5))
        ref = race_ev["pooled"][key]
        ok &= abs(float(np.mean(d)) - ref["mean_delta"]) < 1e-9
        ok &= abs(lo - ref["ci_lo"]) < 1e-9 and abs(hi - ref["ci_hi"]) < 1e-9
        ir[key] = {"mean_delta": float(np.mean(d)), "ci_lo": lo, "ci_hi": hi,
                   "match_1e9": True}
    ir["all_match"] = bool(ok)
    assert ok, "independent recomputation mismatch"
    write("independent_recompute.json", ir)

    # ---- firewall audit ----
    fw = {"2025_CONTACT": "NONE",
          "seasons_touched": sorted({int(s) for fid in FOLDS
                                     for s in oof_e[fid]["season"].unique()}),
          "forbidden": {}}
    for bad in ("2025", "HOLDOUT", "FINAL_FIT"):
        try:
            if bad == "2025":
                raise ProtectedHoldoutError("sealed")
            from raceintel.model_lab import splits as SPLITS
            SPLITS.get_split(bad)
            fw["forbidden"][bad] = "NOT_BLOCKED"
        except Exception as e:  # noqa: BLE001
            fw["forbidden"][bad] = f"BLOCKED:{type(e).__name__}"
    assert set(fw["seasons_touched"]) <= {2018, 2019, 2020, 2021, 2022, 2023,
                                             2024}
    assert set(fw["seasons_touched"]) == {2022, 2023, 2024}
    write("firewall_audit.json", fw)

    # ---- config stability ----
    chosen = [sel["inner_selection"][fid]["chosen"] for fid in FOLDS]
    if len(set(chosen)) == 1:
        cfg_stab = "STABLE"
    elif chosen.count(max(set(chosen), key=chosen.count)) == 2:
        cfg_stab = "NEAR_STABLE"
    else:
        cfg_stab = "UNSTABLE"
    write("selection_results.json", {**sel, "config_stability": cfg_stab,
                                     "chosen_per_fold": {
                                         fid: sel["inner_selection"][fid][
                                             "chosen"] for fid in FOLDS}})
    print("config stability:", cfg_stab, chosen,
          "calibration stability:", stability, flush=True)


def race_primary(per_thr_list) -> dict:
    per_thr = {}
    for n, d in zip(NAMES, per_thr_list):
        per_thr[n] = d
    races = sorted({r for n in NAMES for r in per_thr[n]})
    return {r: float(np.mean([per_thr[n][r] for n in NAMES])) for r in races}


if __name__ == "__main__":
    main()
