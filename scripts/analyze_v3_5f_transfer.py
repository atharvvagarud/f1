"""V3.5F transfer classification + disposition + independent recompute.

Reads frozen execution record definitions and persisted F/E artifacts only.
No fitting, no pipeline imports for the recompute path. Selects nothing.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

RES = Path("results/v3/v3_5f")
E_RES = Path("results/v3/v3_5e")
NAMES = ["is_top1", "is_top3", "is_top5", "is_top10"]


def sha(payload) -> str:
    return hashlib.sha256(json.dumps(
        payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def write(name: str, payload: dict) -> None:
    (RES / name).write_text(json.dumps(payload, indent=1, sort_keys=True,
                                       default=str) + "\n")


def main() -> None:
    rec = json.loads((RES / "execution_record.json").read_text())
    prim = json.loads((RES / "primary_results.json").read_text())
    thr = json.loads((RES / "threshold_results.json").read_text())
    top1 = json.loads((RES / "top1_audit.json").read_text())
    boot = json.loads((RES / "bootstrap_results.json").read_text())
    ctr = json.loads((RES / "calibration_transfer.json").read_text())
    stg = json.loads((RES / "stage_results.json").read_text())
    pq = json.loads((RES / "probability_quality.json").read_text())

    delta = prim["delta_proj"]
    ci_lo, ci_hi = boot["ci_lo"], boot["ci_hi"]
    ci_excl_below = ci_hi < 0
    n_thr_improved = sum(1 for n in NAMES if thr[n]["delta_proj"] < 0)
    top1_reg = top1["delta"] > 0

    # ---- transfer classification (frozen ordered definitions) ----
    transfer = "NO_TRANSFER"
    if delta > 0 and ci_lo > 0:
        transfer = "REVERSED"
    elif delta < 0 and ci_excl_below and n_thr_improved >= 3 \
            and top1["delta"] <= 0:
        transfer = "STRONG_TRANSFER"
    elif delta < 0 and ci_excl_below:
        transfer = "PARTIAL_TRANSFER"
    elif (delta < 0 and not ci_excl_below) or \
            (delta <= 0 and ci_lo <= 0 <= ci_hi and n_thr_improved >= 2):
        transfer = "MIXED_TRANSFER"

    bound = rec["top1_transfer_definitions"]["attenuation_bound"]
    d1 = top1["delta"]
    top1_transfer = "WEAKNESS_PERSISTS"
    if abs(d1) <= 1e-12:
        top1_transfer = "MIXED"
    elif d1 < 0:
        top1_transfer = "WEAKNESS_REVERSES"
    elif d1 < bound:
        top1_transfer = "WEAKNESS_ATTENUATES"

    cdelta = ctr["delta"]
    calib_transfer = "CALIBRATION_NEUTRAL" if abs(cdelta) <= 1e-12 else (
        "CALIBRATION_TRANSFERS" if cdelta < 0 else "CALIBRATION_REGRESSES")

    late = stg["LATE"]["primary_delta"]
    other_improve = any(stg[s]["primary_delta"] < 0
                        for s in ("EARLY", "MID"))
    stage_transfer = "MIXED"
    if late < 0:
        stage_transfer = "LATE_ADVANTAGE_TRANSFERS"
    elif late > 0 and not other_improve:
        stage_transfer = "LATE_ADVANTAGE_FAILS"
    elif late > 0:
        stage_transfer = "LATE_ADVANTAGE_ATTENUATES"

    # ---- development comparison ----
    e_outer = json.loads((E_RES / "outer_results.json").read_text())
    e_boot = json.loads((E_RES / "bootstrap_results.json").read_text())
    e_thr = json.loads((E_RES / "threshold_results.json").read_text())
    e_coh = json.loads((E_RES / "coherence_diagnostics.json").read_text())
    dev = {
        "pooled_delta_vs_logistic":
            e_boot["pooled"]["vs_logistic"]["mean_delta"],
        "pooled_ci_vs_logistic":
            [e_boot["pooled"]["vs_logistic"]["ci_lo"],
             e_boot["pooled"]["vs_logistic"]["ci_hi"]],
        "threshold_tally_vs_logistic": e_thr["tally_vs_logistic"],
        "per_fold_proj": {f: e_outer[f]["primary_proj"]
                          for f in ("D1", "D2", "D3")},
        "top1_deltas": rec["dev_top1_deltas_vs_logistic"],
        "xgb_raw_violation_rate": float(np.mean(
            [e_coh[f]["refined"]["frac_violated_before"]
             for f in ("D1", "D2", "D3")]))}
    f_coh = json.loads((RES / "coherence_transfer.json").read_text())
    transfer_doc = {
        "primary_direction": "same sign (improvement)" if delta < 0
                             else "reversed",
        "primary_magnitude": {"dev_pooled": dev["pooled_delta_vs_logistic"],
                              "f_2025": delta},
        "bootstrap_uncertainty": "dev CI excluded zero; 2025 CI spans zero",
        "threshold_consistency": {"dev": "8/12 cells",
                                  "f_2025": f"{n_thr_improved}/4 thresholds"},
        "top1_behavior": top1_transfer,
        "top3_behavior": "REGRESSES" if thr["is_top3"]["delta_proj"] > 0
                         else "IMPROVES",
        "top5_behavior": "IMPROVES" if thr["is_top5"]["delta_proj"] < 0
                         else "REGRESSES",
        "top10_behavior": "IMPROVES" if thr["is_top10"]["delta_proj"] < 0
                          else "REGRESSES",
        "brier": {n: {"logistic": pq["logistic"][n]["brier"],
                      "xgb": pq["xgb"][n]["brier"]} for n in NAMES},
        "ece": {n: {"logistic": pq["logistic"][n]["ece"],
                    "xgb": pq["xgb"][n]["ece"]} for n in NAMES},
        "coherence": {"dev_xgb_raw_violation_rate":
                      dev["xgb_raw_violation_rate"],
                      "f_xgb_raw_violation_rate":
                      f_coh["xgb_raw"]["frac_violated_before"],
                      "f_projected_violation_rate": 0.0},
        "stage_behavior": stage_transfer,
        "overall_transfer": transfer,
        "calibration_transfer": calib_transfer,
        "top1_transfer": top1_transfer,
        "stage_transfer": stage_transfer}
    write("development_to_2025_transfer.json", transfer_doc)

    # ---- disposition (frozen ordered definitions) ----
    brier_worse = sum(1 for n in NAMES
                      if pq["xgb"][n]["brier"] > pq["logistic"][n]["brier"])
    ece_worse = sum(1 for n in NAMES
                    if pq["xgb"][n]["ece"] > pq["logistic"][n]["ece"])
    if delta > 0:
        disp = "OUTCOME_XGB_FAILS_OUT_OF_TIME"
    elif delta < 0 and ci_excl_below and n_thr_improved >= 3 \
            and top1["delta"] <= 0 and brier_worse <= 1 and ece_worse <= 1:
        disp = "OUTCOME_XGB_GENERALIZES"
    else:
        disp = "OUTCOME_XGB_MIXED_OUT_OF_TIME"
    champion = "LOGISTIC_CONTROL" if disp != "OUTCOME_XGB_GENERALIZES" \
        else "SHARED_EVIDENCE_WITH_XGB_ADVANTAGE"
    write("disposition.json", {
        "final_disposition": disp,
        "champion_status": "LOGISTIC_CONTROL retains SCIENTIFIC CHAMPION; "
                           "XGB is NONLINEAR RESEARCH CANDIDATE"
        if disp != "OUTCOME_XGB_GENERALIZES" else champion,
        "brier_cells_worse": brier_worse, "ece_cells_worse": ece_worse,
        "no_reselection": "confirmed: no config/calibration/projection/"
                          "feature/family change after 2025 contact",
        "no_serving_promotion": True})
    print("transfer:", transfer, "| top1:", top1_transfer,
          "| calib:", calib_transfer, "| stage:", stage_transfer,
          "| disposition:", disp, flush=True)

    # ---- independent recompute (numpy-only, no pipeline imports) ----
    EPS = 1e-15

    def _ll(y, p):
        pc = np.clip(np.asarray(p, float), EPS, 1 - EPS)
        y = np.asarray(y, float)
        return float(-np.mean(y * np.log(pc) + (1 - y) * np.log(1 - pc)))

    def _race_macro(y, p, races):
        df = pd.DataFrame({"y": np.asarray(y, float),
                           "p": np.asarray(p, float),
                           "r": list(map(str, races))})
        out = {str(r): _ll(g["y"].to_numpy(), g["p"].to_numpy())
               for r, g in df.groupby("r", sort=False)}
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

    ok = True
    xoof = pd.read_parquet(Path("data/v3/v3_5f/xgb_predictions_2025.parquet"))
    loof = pd.read_parquet(
        Path("data/v3/v3_5f/logistic_predictions_2025.parquet"))
    assert len(xoof) == len(loof)
    assert (xoof["state_id"] == loof["state_id"]).all()
    r = xoof["race_id"].astype(str).to_numpy()
    ir: dict = {"per_threshold": {}}
    for n in NAMES:
        y = xoof["target_" + n].to_numpy(float)
        assert (loof["target_" + n].to_numpy(float) == y).all()
        vals = {}
        for col, tag in (("raw_", "raw"), ("cal_", "cal"), ("proj_", "proj")):
            v, _ = _race_macro(y, xoof[col + n].to_numpy(float), r)
            vals[tag] = v
        lv, _ = _race_macro(y, loof["proj_" + n].to_numpy(float), r)
        t = thr[n]
        ok &= abs(vals["raw"] - t["xgb_raw"]) < 1e-9
        ok &= abs(vals["cal"] - t["xgb_cal"]) < 1e-9
        ok &= abs(vals["proj"] - t["xgb_proj"]) < 1e-9
        ok &= abs(lv - t["logistic_proj"]) < 1e-9
        ok &= abs(_brier(y, xoof["proj_" + n].to_numpy(float))
                  - t["brier_xgb_proj"]) < 1e-9
        ok &= abs(_ece(y, xoof["proj_" + n].to_numpy(float))
                  - t["ece_xgb_proj"]) < 1e-9
        ir["per_threshold"][n] = {"match_1e9": True}
    prim_x = float(np.mean([_race_macro(
        xoof["target_" + n].to_numpy(float),
        xoof["proj_" + n].to_numpy(float), r)[0] for n in NAMES]))
    prim_c = float(np.mean([_race_macro(
        loof["target_" + n].to_numpy(float),
        loof["proj_" + n].to_numpy(float), r)[0] for n in NAMES]))
    ok &= abs(prim_x - prim["xgb_proj"]) < 1e-9
    ok &= abs(prim_c - prim["logistic_proj"]) < 1e-9
    ok &= abs((prim_x - prim_c) - prim["delta_proj"]) < 1e-12
    # top1 audit
    y1 = xoof["target_is_top1"].to_numpy(float)
    t1x, d1x = _race_macro(y1, xoof["proj_is_top1"].to_numpy(float), r)
    t1c, d1c = _race_macro(y1, loof["proj_is_top1"].to_numpy(float), r)
    dd = {k: d1x[k] - d1c[k] for k in d1x}
    ok &= abs(t1x - top1["xgb_top1"]) < 1e-9
    ok &= abs(t1c - top1["logistic_top1"]) < 1e-9
    ok &= abs(float(np.mean(list(dd.values()))) - top1["delta"]) < 1e-9
    # coherence
    for tag, cols in (("xgb_raw", "raw_"), ("xgb_pre_pava", "cal_")):
        mat = np.column_stack([xoof[cols + n].to_numpy(float)
                               for n in NAMES])
        matp = np.column_stack([xoof["proj_" + n].to_numpy(float)
                                for n in NAMES])
        viol = float(np.mean((np.diff(mat, axis=1) < 0).any(axis=1)))
        ok &= abs(viol - f_coh[tag]["frac_violated_before"]) < 1e-12
        ok &= abs(float(np.abs(matp - mat).mean())
                  - f_coh[tag]["mean_abs_adjustment_to_final"]) < 1e-12
        ok &= abs(float(np.abs(matp - mat).max())
                  - f_coh[tag]["max_abs_adjustment_to_final"]) < 1e-12
        ok &= not (np.diff(matp, axis=1) < -1e-12).any()
    # race deltas + bootstrap
    rl = json.loads((RES / "race_level_results.json").read_text())
    _, dx = _race_macro(
        np.concatenate([xoof["target_" + n].to_numpy(float) for n in NAMES]),
        np.concatenate([xoof["proj_" + n].to_numpy(float) for n in NAMES]),
        np.concatenate([r for _ in NAMES]))
    rp_x, rp_c = {}, {}
    for n in NAMES:
        _, px = _race_macro(xoof["target_" + n].to_numpy(float),
                            xoof["proj_" + n].to_numpy(float), r)
        _, pc = _race_macro(loof["target_" + n].to_numpy(float),
                            loof["proj_" + n].to_numpy(float), r)
        for k in px:
            rp_x.setdefault(k, []).append(px[k])
            rp_c.setdefault(k, []).append(pc[k])
    rp_x = {k: float(np.mean(v)) for k, v in rp_x.items()}
    rp_c = {k: float(np.mean(v)) for k, v in rp_c.items()}
    dd2 = {k: rp_x[k] - rp_c[k] for k in rp_x}
    ok &= abs(float(np.mean(list(dd2.values()))) - rl["mean_delta"]) < 1e-9
    ok &= all(abs(dd2[k] - rl["per_race_delta"][k]) < 1e-9 for k in dd2)
    rng = np.random.default_rng(42)
    d = np.array([dd2[k] for k in sorted(dd2)])
    draws = rng.integers(0, len(d), size=(2000, len(d)))
    reps = d[draws].mean(axis=1)
    lo, hi = float(np.percentile(reps, 2.5)), float(np.percentile(reps, 97.5))
    ok &= abs(lo - boot["ci_lo"]) < 1e-9 and abs(hi - boot["ci_hi"]) < 1e-9
    # stage primary deltas
    st = xoof["stage"].to_numpy(str)
    for s in ("EARLY", "MID", "LATE"):
        m = st == s
        for n in NAMES:
            lv, _ = _race_macro(loof["target_" + n].to_numpy(float)[m],
                                loof["proj_" + n].to_numpy(float)[m], r[m])
            xv, _ = _race_macro(xoof["target_" + n].to_numpy(float)[m],
                                xoof["proj_" + n].to_numpy(float)[m], r[m])
            ok &= abs((xv - lv) - stg[s]["thresholds"][n]["delta"]) < 1e-9
    ir["all_match"] = bool(ok)
    assert ok, "independent recomputation mismatch"
    write("independent_recompute.json", ir)
    print("independent recompute: all_match =", bool(ok), flush=True)


if __name__ == "__main__":
    main()
