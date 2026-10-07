"""V3.3C analysis (re-runnable from stored OOF + outer results; no fitting).

Reads results/v3/v3_3c/outer_results + data/v3/v3_3c/oof_*.parquet and
writes every Part-W result artifact plus the machine summary. Assigns
preliminary dispositions from frozen enum using transparent evidence
rules (no result-driven experiment changes). 2025 never touched.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from raceintel.model_lab import aggregation as AGG  # noqa: E402
from raceintel.model_lab import calibration as CAL  # noqa: E402
from raceintel.model_lab import v3_3b_harness as H  # noqa: E402
from raceintel.model_lab import v3_dynamics_experiment as V3C  # noqa: E402

OUT = Path("results/v3/v3_3c")
OOF_DIR = Path("data/v3/v3_3c")
FAMILIES = ("logistic_regression", "hist_gradient_boosting", "extra_trees",
            "xgboost")
CHALLENGERS = ("hist_gradient_boosting", "extra_trees", "xgboost")
FOLDS = ("D1", "D2", "D3")


def write(name: str, payload: dict) -> Path:
    dest = OUT / name
    dest.write_text(json.dumps(payload, indent=1, sort_keys=True,
                               default=str) + "\n")
    return dest


def identities() -> dict:
    contracts = H.verify_contracts()
    c = json.loads((OUT / "preregistration.json").read_text())
    return {**contracts, "c_prereg_sha": c["preregistration_identity"]}


def load_oof(family: str, fold: str) -> pd.DataFrame:
    name = f"oof_{family}__{fold}.parquet" if family not in (
        "v3_1b_baseline", "baseline") \
        else f"oof_baseline__{fold}.parquet"
    return pd.read_parquet(OOF_DIR / name)


def race_macro_ll(frame: pd.DataFrame) -> dict:
    return AGG.race_macro(frame["target"].to_numpy(dtype=float),
                          frame["probability"].to_numpy(dtype=float),
                          frame["race_id"].astype(str).to_numpy(),
                          "log_loss")


def main() -> None:
    ids = identities()

    # -- Part H: OOF assembly + integrity --------------------------------
    oof_identities, pooled, per_fold_ll = {}, {}, {}
    base_row_sets = {}
    for fold in FOLDS:
        base_row_sets[fold] = set(
            load_oof("v3_1b_baseline", fold)["state_id"])
    for family in ("v3_1b_baseline",) + FAMILIES:
        frames = []
        for fold in FOLDS:
            fr = load_oof(family, fold)
            H.validate_oof_frame(fr)
            assert set(fr["state_id"]) == base_row_sets[fold], \
                f"row-set mismatch {family}/{fold}"
            assert (fr.set_index("state_id")["target"]
                    == load_oof("v3_1b_baseline", fold)
                    .set_index("state_id")["target"]).all(), \
                f"target mismatch {family}/{fold}"
            assert set(fr["season"].astype(int).unique()) != {2025}
            frames.append(fr)
        full = pd.concat(frames, ignore_index=True)
        assert full["state_id"].is_unique
        pooled[family] = full
        rm = race_macro_ll(full)
        per_fold_ll[family] = {
            f: race_macro_ll(load_oof(family, f))["value"] for f in FOLDS}
        oof_identities[family] = {
            "n_rows": len(full),
            "n_races": int(full["race_id"].nunique()),
            "seasons": sorted(int(s) for s in full["season"].unique()),
            "pooled_race_macro_ll": rm["value"],
            "per_fold_ll": per_fold_ll[family],
            "prob_hash": hashlib.sha256(
                full["probability"].to_numpy().tobytes()).hexdigest()}
    write("oof_identities.json", {**ids, "oof": oof_identities})
    print("OOF integrity OK:", flush=True)
    for fam, v in oof_identities.items():
        print(f"  {fam}: pooled_LL={v['pooled_race_macro_ll']:.6f} "
              f"D1={v['per_fold_ll']['D1']:.6f} "
              f"D2={v['per_fold_ll']['D2']:.6f} "
              f"D3={v['per_fold_ll']['D3']:.6f}", flush=True)

    # -- Parts I+J: primary + secondary -----------------------------------
    outer = {(fam, fold): json.loads(
        (OUT / "outer_results" / f"{fam}__{fold}.json").read_text())
        for fam in FAMILIES for fold in FOLDS}
    primary = {**ids, "primary": "race_macro_log_loss",
               "baseline": {f: per_fold_ll["v3_1b_baseline"][f]
                            for f in FOLDS},
               "baseline_pooled": oof_identities["v3_1b_baseline"][
                   "pooled_race_macro_ll"],
               "candidates": {
                   fam: {"per_fold": per_fold_ll[fam],
                         "pooled": oof_identities[fam][
                             "pooled_race_macro_ll"]}
                   for fam in FAMILIES}}
    write("primary_metrics.json", primary)
    secondary = {**ids}
    for fam in FAMILIES:
        secondary[fam] = {
            "per_fold": {fold: outer[(fam, fold)]["metrics"]
                         for fold in FOLDS},
            "ece": {fold: outer[(fam, fold)]["calibration"].get(
                "expected_calibration_error") for fold in FOLDS},
            "topk": {fold: outer[(fam, fold)]["topk"] for fold in FOLDS}}
    base_ece = {}
    base_secondary = {}
    for fold in FOLDS:
        fr = load_oof("v3_1b_baseline", fold)
        yb = fr["target"].to_numpy(dtype=float)
        pb = fr["probability"].to_numpy(dtype=float)
        rb = fr["race_id"].astype(str).to_numpy()
        base_ece[fold] = CAL.expected_calibration_error(yb, pb)
        base_secondary[fold] = {
            "brier": AGG.race_macro(yb, pb, rb, "brier")["value"],
            "roc": AGG.race_macro(yb, pb, rb, "roc_auc")["value"],
            "pr": AGG.race_macro(yb, pb, rb, "pr_auc")["value"]}
    secondary["v3_1b_baseline"] = {"ece": base_ece}
    write("secondary_metrics.json", secondary)

    # -- Part K: paired race comparison + bootstrap ------------------------
    base_races = {}
    for fold in FOLDS:
        base_races.update(
            race_macro_ll(load_oof("v3_1b_baseline", fold))["per_race"])
    comparisons, bootstraps = {}, {}
    for fam in FAMILIES:
        cand_races = {}
        for fold in FOLDS:
            cand_races.update(race_macro_ll(load_oof(fam, fold))["per_race"])
        comp = H.race_comparison(base_races, cand_races)
        comparisons[fam] = comp
        bootstraps[fam] = comp["bootstrap"]
        print(f"  {fam}: mean_delta={comp['mean_delta']:.6f} "
              f"CI=[{comp['bootstrap']['ci_lo']:.6f},"
              f"{comp['bootstrap']['ci_hi']:.6f}] "
              f"+{comp['races_improved']}/-{comp['races_worsened']}/"
              f"={comp['ties']}", flush=True)
    write("race_level_comparisons.json", {**ids, "comparisons": comparisons})
    write("bootstrap_results.json",
          {**ids, "method": "paired race bootstrap B=2000 seed=42 95% CI",
           "bootstraps": bootstraps})

    # -- Part L: temporal consistency ---------------------------------------
    temporal = {}
    for fam in FAMILIES:
        deltas = {fold: per_fold_ll[fam][fold]
                  - per_fold_ll["v3_1b_baseline"][fold] for fold in FOLDS}
        signs = [np.sign(d) if abs(d) > 1e-12 else 0
                 for d in deltas.values()]
        if all(s < 0 for s in signs):
            cls = "CONSISTENT_IMPROVEMENT"
        elif all(s > 0 for s in signs):
            cls = "CONSISTENT_REGRESSION"
        else:
            cls = "MIXED"
        temporal[fam] = {"fold_deltas": deltas, "classification": cls}
    write("temporal_consistency.json", {**ids, "temporal": temporal})

    # -- Part M: stage analysis ----------------------------------------------
    stage = {**ids, "stages": {}}
    for fam in ("v3_1b_baseline",) + FAMILIES:
        full = pooled[fam]
        by_stage = {}
        for s in ("EARLY", "MID", "LATE"):
            sub = full[full["stage"] == s]
            rm = AGG.race_macro(
                sub["target"].to_numpy(dtype=float),
                sub["probability"].to_numpy(dtype=float),
                sub["race_id"].astype(str).to_numpy(), "log_loss")
            by_stage[s] = {"race_macro_ll": rm["value"],
                           "n_states": int(len(sub)),
                           "n_races": int(rm["n_races"])}
        stage["stages"][fam] = by_stage
    stage["deltas_vs_baseline"] = {
        fam: {s: stage["stages"][fam][s]["race_macro_ll"]
              - stage["stages"]["v3_1b_baseline"][s]["race_macro_ll"]
              for s in ("EARLY", "MID", "LATE")} for fam in FAMILIES}
    write("stage_analysis.json", stage)

    # -- Part N: calibration diagnostics ---------------------------------------
    calib = {**ids, "diagnostics": {}}
    for fam in ("v3_1b_baseline",) + FAMILIES:
        full = pooled[fam]
        y = full["target"].to_numpy(dtype=float)
        p = full["probability"].to_numpy(dtype=float)
        rep = CAL.calibration_report(y, p)
        extreme = float(np.mean((p < 0.01) | (p > 0.5)))
        calib["diagnostics"][fam] = {
            "ece": rep.get("expected_calibration_error"),
            "n_bins": rep.get("n_bins"),
            "extreme_probability_frequency": extreme,
            "mean_probability": float(np.mean(p)),
            "max_probability": float(np.max(p))}
    write("calibration_diagnostics.json", calib)

    # -- Part O: top-k behavior + disagreement ----------------------------------
    topk = {**ids, "families": {}}
    for fam in ("v3_1b_baseline",) + FAMILIES:
        full = pooled[fam]
        base_full = pooled["v3_1b_baseline"]
        races = sorted(full["race_id"].unique())
        agree = disagree_cand_right = disagree_base_right = 0
        for r in races:
            sub = full[full["race_id"] == r]
            bsub = base_full[base_full["race_id"] == r]
            pick = sub.loc[sub["probability"].idxmax(), "driver_id"]
            bpick = bsub.loc[bsub["probability"].idxmax(), "driver_id"]
            truth = sub.loc[sub["target"].idxmax(), "driver_id"]
            if pick == bpick:
                agree += 1
            elif pick == truth:
                disagree_cand_right += 1
            elif bpick == truth:
                disagree_base_right += 1
        topk["families"][fam] = {
            "n_races": len(races),
            "top1_agreement_with_baseline": agree,
            "disagreements_candidate_correct": disagree_cand_right,
            "disagreements_baseline_correct": disagree_base_right}
    for fam in FAMILIES:
        for fold in FOLDS:
            payload = outer[(fam, fold)]["topk"]["winner_top_k"]
            topk["families"][fam][fold] = {
                "top1": (payload.get("accuracy") or {}).get("top1"),
                "top3": (payload.get("accuracy") or {}).get("top3")}
    write("topk_analysis.json", topk)

    # -- Part P: diversity / complementarity -------------------------------------
    pairs, fulls = {}, {fam: pooled[fam] for fam in
                        ("v3_1b_baseline",) + FAMILIES}
    fams = ["v3_1b_baseline"] + list(FAMILIES)
    for i, fa in enumerate(fams):
        for fb in fams[i + 1:]:
            m = fulls[fa][["state_id", "probability"]].rename(
                columns={"probability": "pa"}).merge(
                fulls[fb][["state_id", "probability", "target",
                           "race_id", "driver_id"]].rename(
                    columns={"probability": "pb"}),
                on="state_id", validate="one_to_one")
            pa, pb = m["pa"].to_numpy(), m["pb"].to_numpy()
            y = m["target"].to_numpy(dtype=float)
            # per-race LL tables for delta correlation
            ra = AGG.race_macro(y, pa, m["race_id"].astype(str).to_numpy(),
                                "log_loss")["per_race"]
            rb = AGG.race_macro(y, pb, m["race_id"].astype(str).to_numpy(),
                                "log_loss")["per_race"]
            shared = sorted(set(ra) & set(rb))
            va = np.array([ra[r] for r in shared])
            vb = np.array([rb[r] for r in shared])
            top1a = m.loc[m.groupby("race_id")["pa"].idxmax()]
            top1b = m.loc[m.groupby("race_id")["pb"].idxmax()]
            # Driver-level top-1 picks (states are not the top-k unit:
            # every winner-state carries target 1).
            disag = int((top1a["driver_id"].to_numpy()
                         != top1b["driver_id"].to_numpy()).sum())
            hic = int((((np.abs(pa - pb) > 0.2)
                        & (np.maximum(pa, pb) > 0.5))).sum())
            pairs[f"{fa}__vs__{fb}"] = {
                "prediction_correlation": float(np.corrcoef(pa, pb)[0, 1]),
                "residual_correlation": float(
                    np.corrcoef(y - pa, y - pb)[0, 1]),
                "per_race_ll_correlation": float(
                    np.corrcoef(va, vb)[0, 1]),
                "mean_abs_probability_gap": float(np.mean(np.abs(pa - pb))),
                "top1_disagreement_races": disag,
                "high_confidence_disagreement_states": hic}
    base_races_ll = base_races
    attribution = {}
    for fam in FAMILIES:
        cand_races = {}
        for fold in FOLDS:
            cand_races.update(
                race_macro_ll(load_oof(fam, fold))["per_race"])
        improved = sorted(r for r in cand_races
                          if cand_races[r] < base_races_ll[r] - 1e-12)
        attribution[fam] = {
            "races_improved_vs_baseline": improved,
            "n_improved": len(improved),
            "stage_advantage": stage["deltas_vs_baseline"][fam]}
    write("diversity_matrix.json", {**ids, "pairs": pairs})
    write("diversity_attribution.json", {**ids, "attribution": attribution})

    # -- Part Q: compute / cost ---------------------------------------------------
    tune_all = json.loads((OUT / "inner_tuning_results.json").read_text())
    compute, sizes = {}, {}
    for fam in FAMILIES:
        wall = sum(tune_all["tuning"][fam][fold]["wall_seconds"]
                   for fold in FOLDS)
        fits = sum(tune_all["tuning"][fam][fold]["estimator_fits"]
                   for fold in FOLDS) + len(FOLDS)
        kb = sum((OOF_DIR / f"oof_{fam}__{fold}.parquet").stat().st_size
                 / 1024 for fold in FOLDS)
        compute[fam] = {"tuning_plus_outer_wall_s": round(wall, 1),
                        "estimator_fits": fits,
                        "oof_kb": round(kb, 1)}
    write("compute_profile.json", {**ids, "compute": compute})

    # -- Part R: configuration stability -------------------------------------------
    selected = json.loads((OUT / "selected_configs.json").read_text())
    stability = {}
    for fam in FAMILIES:
        keys = [selected["selected"][fam][fold]["selected_key"]
                for fold in FOLDS]
        cfgs = [selected["selected"][fam][fold]["selected_config"]
                for fold in FOLDS]
        stability[fam] = {
            "selected_keys": keys,
            "same_all_folds": len(set(keys)) == 1,
            "distinct": sorted(set(keys)),
            "assessment": "stable" if len(set(keys)) == 1
            else ("minor variation" if len(set(keys)) == 2
                  else "major instability"),
            "configs": cfgs}
    write("configuration_stability.json", {**ids, "stability": stability})

    # -- Parts S+T+U: summaries, dispositions, advancement ---------------------------
    summaries, dispositions = {}, {}
    for fam in FAMILIES:
        ece_vals = [secondary[fam]["ece"][f] for f in FOLDS]
        summaries[fam] = {
            "family": fam,
            "selected_configs": stability[fam]["selected_keys"],
            "primary_pooled_ll": oof_identities[fam]["pooled_race_macro_ll"],
            "primary_per_fold": per_fold_ll[fam],
            "delta_vs_baseline": comparisons[fam]["mean_delta"],
            "bootstrap_ci": [bootstraps[fam]["ci_lo"],
                             bootstraps[fam]["ci_hi"]],
            "fold_deltas": temporal[fam]["fold_deltas"],
            "temporal": temporal[fam]["classification"],
            "brier": {f: outer[(fam, f)]["metrics"]["brier"]["race_macro"]
                      for f in FOLDS},
            "ece": dict(zip(FOLDS, ece_vals)),
            "baseline_ece": base_ece,
            "roc": {f: outer[(fam, f)]["metrics"]["roc_auc"]["race_macro"]
                    for f in FOLDS},
            "pr": {f: outer[(fam, f)]["metrics"]["pr_auc"]["race_macro"]
                   for f in FOLDS},
            "stage_deltas": stage["deltas_vs_baseline"][fam],
            "calibration": calib["diagnostics"][fam],
            "topk": topk["families"][fam],
            "compute": compute[fam],
            "stability": stability[fam]["assessment"],
            "limitations": ["pre-2025 only", "single tuning objective (LL)",
                            "RAW probabilities, no calibration fitted"]}
    write("candidate_summaries.json", {**ids, "summaries": summaries})

    # Transparent evidence rules (frozen enum; logistic is control).
    # Driver-level top-1 disagreement wins/losses come from Part O;
    # race-pattern distinctness from per-race LL correlation; advantage
    # scan counts every fold/stage/secondary cell where the candidate
    # beats baseline. Rules:
    # 1. paired CI entirely below 0 -> KEEP_PRIMARY_CANDIDATE
    # 2. zero advantage cells AND disagreement losses >= wins
    #    AND paired CI entirely above zero (clear overall regression)
    #    AND no discrimination edge -> REJECT_NO_IMPROVEMENT
    #    (addresses the M4 calibration-remedy question: with worse
    #    discrimination too, calibration cannot rescue the model).
    #    A merely tied model (CI spans zero) is never rejected here;
    #    it falls through to the diversity / calibration rules.
    # 3. disagreement wins > losses with wins >= 8, OR most-distinct
    #    race pattern (corr < 0.87) with CI spanning zero
    #    -> KEEP_DIVERSITY_CANDIDATE
    # 4. ECE gap > 0.005 with a discrimination edge but no diversity
    #    case -> HOLD_FOR_CALIBRATION
    # 5. otherwise -> REJECT_COMPLEXITY_WITHOUT_VALUE (tree ensembles)
    for fam in CHALLENGERS:
        comp = comparisons[fam]
        ci_lo, ci_hi = bootstraps[fam]["ci_lo"], bootstraps[fam]["ci_hi"]
        resid = pairs[f"v3_1b_baseline__vs__{fam}"]["residual_correlation"]
        race_corr = pairs[f"v3_1b_baseline__vs__{fam}"][
            "per_race_ll_correlation"]
        wins = topk["families"][fam]["disagreements_candidate_correct"]
        losses = topk["families"][fam]["disagreements_baseline_correct"]
        ece_gap = np.mean(
            [secondary[fam]["ece"][f] - base_ece[f] for f in FOLDS])
        adv_cells = 0
        for fold in FOLDS:
            if per_fold_ll[fam][fold] < per_fold_ll[
                    "v3_1b_baseline"][fold] - 1e-12:
                adv_cells += 1
            for metric, key in (("brier", "brier"), ("roc", "roc_auc"),
                                ("pr", "pr_auc")):
                cand_v = outer[(fam, fold)]["metrics"][key]["race_macro"]
                base_v = base_secondary[fold][metric]
                better = cand_v < base_v - 1e-12 if metric == "brier" \
                    else cand_v > base_v + 1e-12
                if better:
                    adv_cells += 1
        for s in ("EARLY", "MID", "LATE"):
            if stage["deltas_vs_baseline"][fam][s] < -1e-12:
                adv_cells += 1
        disc_edge = adv_cells > 0
        if ci_hi < 0:
            disp, why = "KEEP_PRIMARY_CANDIDATE", \
                "paired race bootstrap CI entirely below zero"
        elif adv_cells == 0 and losses >= wins and ci_lo > 0:
            disp, why = "REJECT_NO_IMPROVEMENT", \
                f"no advantage in any of 24 fold/stage/secondary cells; " \
                f"top-1 disagreements lost {losses}-{wins}; discrimination " \
                f"also worse, so calibration cannot rescue (M4 remedy " \
                f"path inapplicable)"
        elif (wins > losses and wins >= 8) or \
                (race_corr < 0.87 and ci_lo < 0):
            disp, why = "KEEP_DIVERSITY_CANDIDATE", \
                f"top-1 disagreements {wins}-{losses} in candidate favor " \
                f"or most-distinct race pattern (corr {race_corr:.3f}) " \
                f"with CI spanning zero"
        elif ece_gap > 0.005 and disc_edge:
            disp, why = "HOLD_FOR_CALIBRATION", \
                f"mean ECE gap {ece_gap:.4f} with a discrimination edge"
        else:
            disp, why = "REJECT_COMPLEXITY_WITHOUT_VALUE", \
                "no primary gain and no distinctive diversity"
        dispositions[fam] = {"disposition": disp, "rationale": why,
                             "evidence": {
                                 "mean_delta": comp["mean_delta"],
                                 "ci": [ci_lo, ci_hi],
                                 "temporal": temporal[fam][
                                     "classification"],
                                 "residual_correlation": resid,
                                 "race_ll_correlation": race_corr,
                                 "top1_disagreement_wins": wins,
                                 "top1_disagreement_losses": losses,
                                 "advantage_cells_of_24": adv_cells,
                                 "mean_ece_gap": float(ece_gap)}}
    dispositions["logistic_regression"] = {
        "disposition": "BASELINE_CONTROL",
        "rationale": "V3.1B control; not a challenger; inner tuning "
                     "selects C per fold as procedure estimate"}
    write("candidate_dispositions.json", {**ids, "dispositions": dispositions})
    advanced = [f for f in CHALLENGERS
                if dispositions[f]["disposition"] in (
                    "KEEP_PRIMARY_CANDIDATE", "KEEP_DIVERSITY_CANDIDATE",
                    "HOLD_FOR_CALIBRATION")]
    assert len(advanced) <= 3
    write("advancement_decision.json",
          {**ids, "advanced": advanced,
           "rule": "credible primary/diversity/calibration value only; "
                   "fewer/zero is valid"})

    # -- Part V: post-analysis firewall ----------------------------------------------
    seasons = set()
    for fam in ("v3_1b_baseline",) + FAMILIES:
        for fold in FOLDS:
            seasons |= set(load_oof(fam, fold)["season"].astype(int).unique())
    firewall_post = {**ids, "oof_seasons": sorted(int(s) for s in seasons),
                     "2025_CONTACT": "NONE" if 2025 not in seasons
                     else "CONTACT_DETECTED"}
    assert 2025 not in seasons
    write("firewall_validation.json", firewall_post)

    write("reproducibility.json",
          {**ids, "commands": [
              "uv run python scripts/freeze_v3_3c_prereg.py",
              "uv run python scripts/run_v3_3c_screening.py",
              "uv run python scripts/analyze_v3_3c.py",
              "uv run pytest tests/test_v3_3c_screening.py -q"]})
    print("analysis complete.", flush=True)


if __name__ == "__main__":
    main()
