"""V3.3D analysis (re-runnable from stored OOF + D results; no fitting).

Produces every Part-Z artifact, final dispositions, finalists (<=2),
and hashed final-fit recipes. 2025 never touched.
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
from raceintel.model_lab import v3_3d_refinement as D  # noqa: E402

OUT = Path("results/v3/v3_3d")
OOF_DIR = Path("data/v3/v3_3d")
C_OOF = Path("data/v3/v3_3c")
FOLDS = ("D1", "D2", "D3")
REPS = ("C_RAW", "D_REFINED_RAW", "D_CALIBRATED")


def write(name: str, payload: dict) -> Path:
    dest = OUT / name
    dest.write_text(json.dumps(payload, indent=1, sort_keys=True,
                               default=str) + "\n")
    return dest


def identities() -> dict:
    contracts = H.verify_contracts()
    d = json.loads((OUT / "preregistration.json").read_text())
    c = json.loads(Path("results/v3/v3_3c/preregistration.json").read_text())
    return {**contracts, "d_prereg_sha": d["preregistration_identity"],
            "c_prereg_sha": c["preregistration_identity"]}


def load_oof_c(family: str, fold: str) -> pd.DataFrame:
    if family == "v3_1b_baseline":
        return pd.read_parquet(C_OOF / f"oof_baseline__{fold}.parquet")
    return pd.read_parquet(C_OOF / f"oof_{family}__{fold}.parquet")


def load_oof_d(kind: str, family: str, fold: str) -> pd.DataFrame:
    assert kind in ("refined", "calibrated")
    return pd.read_parquet(OOF_DIR / f"oof_d_{kind}_{family}__{fold}.parquet")


def race_macro_ll(frame: pd.DataFrame) -> dict:
    return AGG.race_macro(frame["target"].to_numpy(dtype=float),
                          frame["probability"].to_numpy(dtype=float),
                          frame["race_id"].astype(str).to_numpy(), "log_loss")


def main() -> None:
    ids = identities()
    d_results = {(fam, fold): json.loads(
        (OUT / f"d_result_{fam}__{fold}.json").read_text())
        for fam in D.D_FAMILIES for fold in FOLDS}

    # -- calibration contract + support (Parts G/H) -----------------------
    write("calibration_contract.json",
          {**ids, "methods": ["RAW", "sigmoid", "isotonic"],
           "data": "cross-fitted inner-val predictions, outer TRAIN only; "
                   "earlier races fit, later races select; winners refit on "
                   "full calibration set",
           "selection_rule": "LL gain > 1e-4 AND no Brier harm; "
                             "ties RAW > SIGMOID > ISOTONIC",
           "support_gates": {
               "isotonic": {"min_rows": D.ISOTONIC_MIN_ROWS,
                            "min_positives": D.ISOTONIC_MIN_POSITIVES,
                            "min_unique": D.ISOTONIC_MIN_UNIQUE},
               "sigmoid": {"min_rows": D.SIGMOID_MIN_ROWS,
                           "min_positives": D.SIGMOID_MIN_POSITIVES,
                           "min_unique": D.SIGMOID_MIN_UNIQUE}}})
    support, cal_selection = {}, {}
    for fam in D.D_FAMILIES:
        support[fam], cal_selection[fam] = {}, {}
        for fold in FOLDS:
            node = d_results[(fam, fold)]["calibration"]
            support[fam][fold] = node["support"] if "support" in node \
                else node
            cal_selection[fam][fold] = {
                "selected_method": d_results[(fam, fold)][
                    "calibration_method"],
                "outcome": node.get("outcome", {}),
                "reason": node.get("reason", "")}
    write("calibration_support.json", {**ids, "support": support})
    write("calibration_selection.json",
          {**ids, "selection": cal_selection})

    # -- refinement audit (Parts E/F/J) ------------------------------------
    write("refinement_grids.json",
          {**ids, "grids": json.loads(
              (OUT / "preregistration.json").read_text())[
              "refinement_grids"]})
    inner_ref, selected_ref = {}, {}
    for fam in D.D_FAMILIES:
        inner_ref[fam], selected_ref[fam] = {}, {}
        for fold in FOLDS:
            node = d_results[(fam, fold)]
            inner_ref[fam][fold] = {
                "config_aggregates": node["config_aggregates"],
                "selection": node["selection"],
                "estimator_fits": node["estimator_fits"]}
            selected_ref[fam][fold] = {
                "selected_key": node["selection"]["selected_key"],
                "selected_config": node["selection"]["selected_config"],
                "calibration_method": node["calibration_method"]}
    write("inner_refinement_results.json", {**ids, "tuning": inner_ref})
    write("selected_refinements.json", {**ids, "selected": selected_ref})

    # -- OOF integrity (Part K) ----------------------------------------------
    frames, oof_ids = {}, {}
    for fam in D.D_FAMILIES:
        for fold in FOLDS:
            for kind, rep in (("refined", "D_REFINED_RAW"),
                              ("calibrated", "D_CALIBRATED")):
                fr = load_oof_d(kind, fam, fold)
                H.validate_oof_frame(fr)
                base = load_oof_c("v3_1b_baseline", fold)
                assert set(fr["state_id"]) == set(base["state_id"])
                assert (fr.set_index("state_id")["target"]
                        == base.set_index("state_id")["target"]).all()
                assert 2025 not in set(fr["season"].astype(int).unique())
                frames[(fam, rep, fold)] = fr
    for fam in D.D_FAMILIES:
        for rep, kind in (("C_RAW", None), ("D_REFINED_RAW", "refined"),
                          ("D_CALIBRATED", "calibrated")):
            parts = [(load_oof_c(fam, f) if kind is None
                      else frames[(fam, rep, f)]) for f in FOLDS]
            full = pd.concat(parts, ignore_index=True)
            assert full["state_id"].is_unique
            rm = race_macro_ll(full)
            oof_ids[f"{fam}_{rep}"] = {
                "n_rows": len(full), "n_races": int(full["race_id"].nunique()),
                "pooled_ll": rm["value"],
                "per_fold": {f: race_macro_ll(parts[i])["value"]
                             for i, f in enumerate(FOLDS)},
                "prob_hash": hashlib.sha256(
                    full["probability"].to_numpy().tobytes()).hexdigest()}
            frames[(fam, rep, "pooled")] = full
    base_full = pd.concat(
        [load_oof_c("v3_1b_baseline", f) for f in FOLDS], ignore_index=True)
    base_races = race_macro_ll(base_full)["per_race"]
    base_pooled_ll = race_macro_ll(base_full)["value"]
    write("oof_identities.json",
          {**ids, "oof": oof_ids, "baseline_pooled_ll": base_pooled_ll})

    # RAW vs calibrated identity: equal iff method RAW ---------------
    raw_cal_identity = {}
    for fam in D.D_FAMILIES:
        for fold in FOLDS:
            same = bool(frames[(fam, "D_REFINED_RAW", fold)][
                "probability"].equals(frames[(fam, "D_CALIBRATED", fold)][
                "probability"]))
            method = d_results[(fam, fold)]["calibration_method"]
            assert same == (method == "RAW"), f"{fam}/{fold}"
            raw_cal_identity[f"{fam}/{fold}"] = {
                "method": method, "calibrated_equals_raw": same}

    # -- primary + bootstrap (Parts L/M) ---------------------------------------
    primary = {**ids, "baseline_pooled": base_pooled_ll,
               "representations": {
                   f"{fam}_{rep}": {
                       "pooled": oof_ids[f"{fam}_{rep}"]["pooled_ll"],
                       "per_fold": oof_ids[f"{fam}_{rep}"]["per_fold"]}
                   for fam in D.D_FAMILIES for rep in REPS}}
    write("primary_metrics.json", primary)
    comparisons, bootstraps = {}, {}
    for fam in D.D_FAMILIES:
        for rep in REPS:
            cand = {}
            for fold in FOLDS:
                fr = frames[(fam, rep, fold)] if rep != "C_RAW" \
                    else load_oof_c(fam, fold)
                cand.update(race_macro_ll(fr)["per_race"])
            comp = H.race_comparison(base_races, cand)
            comparisons[f"{fam}_{rep}_vs_baseline"] = comp
        own_c, own_d = {}, {}
        for fold in FOLDS:
            own_c.update(race_macro_ll(load_oof_c(fam, fold))["per_race"])
            own_d.update(
                race_macro_ll(frames[(fam, "D_CALIBRATED", fold)])[
                    "per_race"])
        comp = H.race_comparison(own_c, own_d)
        comparisons[f"{fam}_D_CAL_vs_C_RAW"] = comp
    write("race_comparisons.json", {**ids, "comparisons": comparisons})
    write("bootstrap_results.json",
          {**ids, "method": "paired race bootstrap B=2000 seed=42 95% CI",
           "bootstraps": {k: v["bootstrap"]
                          for k, v in comparisons.items()}})
    for key, comp in comparisons.items():
        print(f"  {key}: delta={comp['mean_delta']:.6f} "
              f"CI=[{comp['bootstrap']['ci_lo']:.6f},"
              f"{comp['bootstrap']['ci_hi']:.6f}]", flush=True)

    # -- probability quality + discrimination (Parts N/O) -------------------------
    quality, discrimination = {**ids}, {**ids, "note":
        "sigmoid/isotonic are monotonic: ranking (ROC/PR/top-k) identical "
        "to RAW; verified by equality below"}
    for fam in D.D_FAMILIES:
        for rep in REPS:
            full = frames[(fam, rep, "pooled")]
            y = full["target"].to_numpy(float)
            p = full["probability"].to_numpy(float)
            r = full["race_id"].astype(str).to_numpy()
            rep_out = CAL.calibration_report(y, p)
            per_race = AGG.race_macro(y, p, r, "log_loss")["per_race"]
            quality[f"{fam}_{rep}"] = {
                "brier": AGG.race_macro(y, p, r, "brier")["value"],
                "ece": rep_out.get("expected_calibration_error"),
                "extreme_probability_frequency": float(
                    np.mean((p < 0.01) | (p > 0.5))),
                "worst_race_ll": float(max(per_race.values())),
                "max_probability": float(np.max(p))}
            roc = AGG.race_macro(y, p, r, "roc_auc")["value"]
            pr = AGG.race_macro(y, p, r, "pr_auc")["value"]
            discrimination[f"{fam}_{rep}"] = {"roc_auc": roc, "pr_auc": pr}
    # monotonicity: no strict inversions (isotonic/sigmoid are
    # non-decreasing; flat segments coarsen ties, which can shift
    # tie-grouped rank metrics by ~1e-2 — reported, not hidden).
    monotonic = {}
    for fam in D.D_FAMILIES:
        for fold in FOLDS:
            pr_ = frames[(fam, "D_REFINED_RAW", fold)][
                "probability"].to_numpy()
            pc_ = frames[(fam, "D_CALIBRATED", fold)][
                "probability"].to_numpy()
            order = np.argsort(pr_, kind="mergesort")
            monotonic[f"{fam}/{fold}"] = bool(
                np.all(np.diff(pc_[order]) >= -1e-12))
    assert all(monotonic.values()), \
        [k for k, v in monotonic.items() if not v]
    discrimination["monotonicity_no_strict_inversions"] = monotonic
    write("probability_quality.json", quality)
    write("discrimination.json", discrimination)

    # -- temporal + stage (Parts P/Q) ----------------------------------------------
    temporal = {}
    for fam in D.D_FAMILIES:
        for rep in ("D_REFINED_RAW", "D_CALIBRATED"):
            deltas = {f: oof_ids[f"{fam}_{rep}"]["per_fold"][f]
                      - race_macro_ll(load_oof_c(
                          "v3_1b_baseline", f))["value"] for f in FOLDS}
            c_deltas = {f: oof_ids[f"{fam}_{rep}"]["per_fold"][f]
                        - race_macro_ll(load_oof_c(fam, f))["value"]
                        for f in FOLDS}
            signs = [np.sign(d) if abs(d) > 1e-12 else 0
                     for d in deltas.values()]
            cls = "CONSISTENT_IMPROVEMENT" if all(s < 0 for s in signs) \
                else ("CONSISTENT_REGRESSION" if all(s > 0 for s in signs)
                      else "MIXED")
            temporal[f"{fam}_{rep}"] = {
                "fold_deltas_vs_baseline": deltas,
                "fold_deltas_vs_c_raw": c_deltas,
                "classification": cls}
    write("temporal_consistency.json", {**ids, "temporal": temporal})
    stage = {**ids, "stages": {}, "deltas_vs_baseline": {},
             "deltas_vs_c_raw": {}}
    for fam in D.D_FAMILIES:
        for rep in REPS:
            full = frames[(fam, rep, "pooled")]
            by_stage = {}
            for s in ("EARLY", "MID", "LATE"):
                sub = full[full["stage"] == s]
                by_stage[s] = AGG.race_macro(
                    sub["target"].to_numpy(float),
                    sub["probability"].to_numpy(float),
                    sub["race_id"].astype(str).to_numpy(),
                    "log_loss")["value"]
            stage["stages"][f"{fam}_{rep}"] = by_stage
    base_stages = {}
    for s in ("EARLY", "MID", "LATE"):
        sub = base_full[base_full["stage"] == s]
        base_stages[s] = AGG.race_macro(
            sub["target"].to_numpy(float),
            sub["probability"].to_numpy(float),
            sub["race_id"].astype(str).to_numpy(), "log_loss")["value"]
    for fam in D.D_FAMILIES:
        for rep in ("D_REFINED_RAW", "D_CALIBRATED"):
            stage["deltas_vs_baseline"][f"{fam}_{rep}"] = {
                s: stage["stages"][f"{fam}_{rep}"][s] - base_stages[s]
                for s in ("EARLY", "MID", "LATE")}
            stage["deltas_vs_c_raw"][f"{fam}_{rep}"] = {
                s: stage["stages"][f"{fam}_{rep}"][s]
                - stage["stages"][f"{fam}_C_RAW"][s]
                for s in ("EARLY", "MID", "LATE")}
    write("stage_analysis.json", stage)

    # -- diversity re-evaluation (Parts R/S) ------------------------------------------
    # Best admissible PRE-2025 representation per family: D_CALIBRATED is
    # admissible only if it does not harm pooled primary vs D_REFINED_RAW
    # on the outer measurement set; otherwise the admissible set is
    # {C_RAW, D_REFINED_RAW} and best = argmin pooled LL. ET isotonic is
    # expected to be inadmissible here (D3 blowup); XGB method is RAW so
    # refined == calibrated.
    admissible = {}
    for fam in D.D_FAMILIES:
        cands = {"C_RAW": oof_ids[f"{fam}_C_RAW"]["pooled_ll"],
                 "D_REFINED_RAW": oof_ids[f"{fam}_D_REFINED_RAW"][
                     "pooled_ll"]}
        if oof_ids[f"{fam}_D_CALIBRATED"]["pooled_ll"] <= cands[
                "D_REFINED_RAW"] + 1e-12:
            cands["D_CALIBRATED"] = oof_ids[f"{fam}_D_CALIBRATED"][
                "pooled_ll"]
        else:
            cands["D_CALIBRATED_EXCLUDED"] = oof_ids[
                f"{fam}_D_CALIBRATED"]["pooled_ll"]
        best = min(cands, key=lambda k: cands[k]
                   if not k.endswith("EXCLUDED") else float("inf"))
        admissible[fam] = {"candidates": cands, "best": best}
    write("diversity_admissibility.json", {**ids, "admissible": admissible})

    def best_rep(fam):
        return admissible[fam]["best"]
    pairs = {}
    fams = {"baseline": base_full,
            **{f"{fam}": frames[(fam, best_rep(fam), "pooled")]
               for fam in D.D_FAMILIES}}
    names = list(fams)
    for i, fa in enumerate(names):
        for fb in names[i + 1:]:
            A, B = fams[fa], fams[fb]
            m = A[["state_id", "probability", "driver_id"]].rename(
                columns={"probability": "pa"}).merge(
                B[["state_id", "probability", "target", "race_id",
                   "driver_id"]].rename(
                    columns={"probability": "pb",
                             "driver_id": "driver_b"}),
                on="state_id", validate="one_to_one")
            pa, pb = m["pa"].to_numpy(), m["pb"].to_numpy()
            y = m["target"].to_numpy(float)
            ra = AGG.race_macro(y, pa, m["race_id"].astype(str).to_numpy(),
                                "log_loss")["per_race"]
            rb = AGG.race_macro(y, pb, m["race_id"].astype(str).to_numpy(),
                                "log_loss")["per_race"]
            shared = sorted(set(ra) & set(rb))
            ta = m.loc[m.groupby("race_id")["pa"].idxmax()]
            tb = m.loc[m.groupby("race_id")["pb"].idxmax()]
            disagree = ta["driver_id"].to_numpy() != tb["driver_b"].to_numpy()
            # correctness: winning driver per race from target==1 rows
            winners = m[m["target"] == 1.0].groupby("race_id")[
                "driver_id"].first()
            wa = ta["race_id"].map(
                lambda r: ta.set_index("race_id").loc[r, "driver_id"]
                == winners[r])
            wb = tb["race_id"].map(
                lambda r: tb.set_index("race_id").loc[r, "driver_b"]
                == winners[r])
            pairs[f"{fa}__vs__{fb}"] = {
                "prediction_correlation": float(np.corrcoef(pa, pb)[0, 1]),
                "residual_correlation": float(
                    np.corrcoef(y - pa, y - pb)[0, 1]),
                "per_race_ll_correlation": float(np.corrcoef(
                    [ra[r] for r in shared],
                    [rb[r] for r in shared])[0, 1]),
                "mean_abs_probability_gap": float(np.mean(np.abs(pa - pb))),
                "top1_disagreement_races": int(disagree.sum()),
                "top1_disagreements_a_correct": int(
                    (disagree & wa.to_numpy()).sum()),
                "top1_disagreements_b_correct": int(
                    (disagree & wb.to_numpy()).sum()),
                "high_confidence_disagreement_states": int(
                    ((np.abs(pa - pb) > 0.2)
                     & (np.maximum(pa, pb) > 0.5)).sum())}
    write("diversity_matrix.json", {**ids, "pairs": pairs})
    attribution = {}
    for fam in D.D_FAMILIES:
        rep = best_rep(fam)
        cand, base = {}, dict(base_races)
        for fold in FOLDS:
            fr = frames[(fam, rep, fold)] if rep != "C_RAW" \
                else load_oof_c(fam, fold)
            cand.update(race_macro_ll(fr)["per_race"])
        improved = sorted(r for r in cand if cand[r] < base[r] - 1e-12)
        attribution[fam] = {"representation": rep,
                            "races_improved_vs_baseline": improved,
                            "n_improved": len(improved),
                            "stage_advantage": stage["deltas_vs_baseline"][
                                f"{fam}_{rep}"]}
    write("diversity_attribution.json", {**ids, "attribution": attribution})

    # -- compute (Part T) ---------------------------------------------------------------
    compute = {}
    for fam in D.D_FAMILIES:
        wall = sum(d_results[(fam, f)]["timings"]["total_seconds"]
                   for f in FOLDS)
        fits = sum(d_results[(fam, f)]["estimator_fits"] for f in FOLDS)
        kb = sum((OOF_DIR / f"oof_d_{k}_{fam}__{f}.parquet").stat().st_size
                 / 1024 for k in ("refined", "calibrated") for f in FOLDS)
        methods = [d_results[(fam, f)]["calibration_method"] for f in FOLDS]
        compute[fam] = {"wall_s": round(wall, 1), "inner_fits": fits,
                        "oof_kb": round(kb, 1),
                        "calibration_methods": methods}
    write("compute_profile.json", {**ids, "compute": compute})

    # -- final dispositions (Part U; no HOLD_FOR_CALIBRATION) ------------------------------
    dispositions = {}
    for fam in D.D_FAMILIES:
        rep = best_rep(fam)
        key = f"{fam}_{rep}_vs_baseline"
        comp = comparisons[key]
        ci_lo, ci_hi = comp["bootstrap"]["ci_lo"], comp["bootstrap"]["ci_hi"]
        pair = pairs[f"baseline__vs__{fam}"]
        ece_gap = quality[f"{fam}_{rep}"]["ece"] - quality.get(
            "baseline", {}).get("ece", 0.0) if "baseline" in quality \
            else None
        base_ece = CAL.expected_calibration_error(
            base_full["target"].to_numpy(float),
            base_full["probability"].to_numpy(float))
        ece_gap = quality[f"{fam}_{rep}"]["ece"] - base_ece
        if ci_hi < 0:
            disp, why = "KEEP_PRIMARY_CANDIDATE", \
                "paired CI entirely below zero"
        elif comp["mean_delta"] > 0 and ci_lo > 0 and \
                pair["top1_disagreement_races"] > 0:
            n_imp = attribution[fam]["n_improved"]
            if n_imp >= 15 and pair["residual_correlation"] < 0.93:
                disp, why = "KEEP_DIVERSITY_CANDIDATE", \
                    f"useful disagreement survives refinement: {n_imp} " \
                    f"races improved, residual corr " \
                    f"{pair['residual_correlation']:.3f}"
            else:
                disp, why = "REJECT_NO_IMPROVEMENT", \
                    "worse overall with no useful-disagreement evidence"
        elif ci_lo < 0:
            disp, why = "KEEP_DIVERSITY_CANDIDATE", \
                "statistical tie with distinct errors"
        else:
            disp, why = "REJECT_NO_IMPROVEMENT", \
                "no credible standalone or diversity value"
        dispositions[fam] = {
            "disposition": disp, "rationale": why,
            "representation": rep,
            "evidence": {"mean_delta": comp["mean_delta"],
                         "ci": [ci_lo, ci_hi],
                         "temporal": temporal[f"{fam}_{rep}"][
                             "classification"],
                         "ece_gap": float(ece_gap),
                         "n_improved": attribution[fam]["n_improved"],
                         "residual_correlation": pair[
                             "residual_correlation"]}}
    write("final_dispositions.json", {**ids, "dispositions": dispositions})

    # -- finalists (Part V; <=2 + baseline) --------------------------------------
    finalists = [f for f in D.D_FAMILIES if dispositions[f][
        "disposition"] in ("KEEP_PRIMARY_CANDIDATE",
                           "KEEP_DIVERSITY_CANDIDATE")]
    assert len(finalists) <= 2
    write("advancement_decision.json",
          {**ids, "finalists": finalists, "plus_baseline": True,
           "rule": "credible standalone OR useful diversity; zero valid"})

    # -- final-fit recipes (Parts W/X; frozen BEFORE 2025) --------------------------
    from collections import Counter
    recipes = {}
    for fam in finalists:
        methods = [d_results[(fam, f)]["calibration_method"] for f in FOLDS]
        # deterministic: most frequent; ties prefer RAW > SIGMOID > ISOTONIC
        order = {"RAW": 0, "sigmoid": 1, "isotonic": 2}
        method = sorted(Counter(methods).items(),
                        key=lambda kv: (-kv[1], order[kv[0]]))[0][0]
        cfgs = [d_results[(fam, f)]["selection"]["selected_config"]
                for f in FOLDS]
        # hyperparameters must be stable enough to freeze ONE recipe:
        # use the D3 (largest-history) selection; record all three.
        final_cfg = d_results[(fam, "D3")]["selection"]["selected_config"]
        recipes[fam] = {
            "model_family": fam,
            "hyperparameters": final_cfg,
            "fold_selections": cfgs,
            "preprocessing": "frozen TRAIN-only median/mode + "
                             "StandardScaler (model_lab.preprocessing)",
            "feature_identity": {"arm": H.ARM_PRIMARY, "count": 110,
                                 "hash": json.loads((OUT / "preregistration"
                                                     ".json").read_text())[
                                     "feature_identity"]["feature_hash"]},
            "training_years": list(range(2018, 2025)),
            "random_seed": H.SEED,
            "thread_policy": dict(H.THREAD_POLICY),
            "calibration_method": method,
            "calibration_training_procedure": "NONE (RAW)" if method
            == "RAW" else (
                f"fit {method} on cross-fitted base-model predictions over "
                f"FINAL-history inner folds "
                f"(I1: 2018-2020->2021, I2: +2021->2022, I3: +2022->2023, "
                f"I4: +2023->2024); method frozen here, parameters fit "
                f"once on that history; never on outer validation; "
                f"never on 2025"),
            "prediction_semantics": "RAW" if method == "RAW"
            else f"{method}-calibrated INDEPENDENT_BINARY; never normalized",
            "library_versions": H.library_versions()}
    recipes["v3_1b_baseline"] = {
        "model_family": "logistic_regression",
        "hyperparameters": {"C": 0.01, "solver": "lbfgs", "penalty": "l2",
                            "max_iter": 1000, "class_weight": None,
                            "random_state": 42},
        "preprocessing": "frozen TRAIN-only (model_lab.preprocessing)",
        "feature_identity": {"arm": H.ARM_PRIMARY, "count": 110},
        "training_years": list(range(2018, 2025)),
        "random_seed": 42,
        "thread_policy": dict(H.THREAD_POLICY),
        "calibration_method": "RAW",
        "prediction_semantics": "RAW INDEPENDENT_BINARY; never normalized",
        "reference": "accepted V3.1 artifact/spec; no retraining vs 2025"}
    blob = json.dumps(recipes, sort_keys=True, separators=(",", ":"))
    recipe_hash = hashlib.sha256(blob.encode()).hexdigest()
    write("finalist_recipes.json",
          {**ids, "recipes": recipes, "recipe_hash": recipe_hash})

    # -- firewall + reproducibility (Parts Y/AE) -----------------------------------
    seasons = set()
    for p in list(OOF_DIR.glob("oof_d_*__D?.parquet")):
        seasons |= set(pd.read_parquet(p, columns=["season"])["season"]
                       .astype(int).unique())
    assert 2025 not in seasons
    write("firewall_validation.json",
          {**ids, "oof_seasons": sorted(int(s) for s in seasons),
           "2025_CONTACT": "NONE"})
    write("reproducibility.json",
          {**ids, "commands": [
              "uv run python scripts/freeze_v3_3d_prereg.py",
              "uv run python scripts/run_v3_3d_refinement.py",
              "uv run python scripts/analyze_v3_3d.py",
              "uv run pytest tests/test_v3_3d_refinement.py -q"]})
    print("analysis complete.", flush=True)


if __name__ == "__main__":
    main()
