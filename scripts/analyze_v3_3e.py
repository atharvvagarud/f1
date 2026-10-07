"""V3.3E analysis FROM FROZEN PREDICTIONS ONLY (no fitting, no 2025 refit).

Reads the immutable XGB/baseline 2025 parquets + manifest/identity
artifacts; writes metrics, comparisons, transfer, stage, calibration,
discrimination, diversity, disposition, standalone + V3.4 decisions,
holdout record (hashed), scientific card, machine summary.
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
from raceintel.model_lab import data as DATA  # noqa: E402
from raceintel.model_lab import runner as RUN  # noqa: E402
from raceintel.model_lab import stages as STAGES  # noqa: E402
from raceintel.model_lab import v3_3b_harness as H  # noqa: E402
from raceintel.model_lab import v3_dynamics_experiment as V3C  # noqa: E402
from raceintel.model_lab.predictions import (  # noqa: E402
    PredictionKind,
    PredictionResult,
    ProbabilitySemantics,
)

OUT = Path("results/v3/v3_3e")
DATA_OUT = Path("data/v3/v3_3e")
PRED = DATA_OUT / "pred_xgb_final_2025.parquet"
BASELINE_PRED = Path(
    "data/v3/v3_1d/pred_final_ALL_84_PLUS_V3_1_DYNAMICS_CORE_2025.parquet")


def write(name: str, payload: dict) -> Path:
    dest = OUT / name
    dest.write_text(json.dumps(payload, indent=1, sort_keys=True,
                               default=str) + "\n")
    return dest


def ff(value):
    return float(value) if value is not None else None


def main() -> None:
    manifest = json.loads((OUT / "execution_manifest.json").read_text())
    revealed = json.loads((OUT / "holdout_revealed.json").read_text())
    assert revealed["HOLDOUT_REVEALED"] is True
    contracts = H.verify_contracts()
    ids = {**contracts,
           "manifest_identity": manifest["manifest_identity"],
           "recipe_sha": revealed["recipe_sha"]}

    xgb = pd.read_parquet(PRED)
    base = pd.read_parquet(BASELINE_PRED)
    assert hashlib.sha256(PRED.read_bytes()).hexdigest() == \
        revealed["prediction_sha256"]
    assert set(xgb["state_id"]) == set(base["state_id"])
    # Identity-align challenger to baseline order (sets match; order is
    # NOT guaranteed): every metric below pairs arrays positionally.
    xgb = xgb.set_index("state_id").loc[
        base["state_id"]].reset_index()
    assert len(xgb) == 26692 and xgb["state_id"].is_unique
    for frame in (xgb, base):
        p = frame["probability" if "probability" in frame.columns
                  else "y_pred"].to_numpy(float)
        assert np.all(np.isfinite(p)) and np.all((p >= 0) & (p <= 1))
    y = base["y_true"].to_numpy(float)
    xgb_targets = xgb.set_index("state_id").loc[
        base["state_id"], "target"].to_numpy(float)
    assert (xgb_targets == y).all()
    pb = base["y_pred"].to_numpy(float)
    px = xgb["probability"].to_numpy(float)
    races = base["race_id"].astype(str).to_numpy()
    assert (xgb["race_id"].astype(str).to_numpy() == races).all()
    n_races = len(set(races))
    assert n_races == 24

    # stages from the frozen input feature (read-only, no leakage)
    augmented, plain = V3C.load_joined_frame()
    hold_frame = augmented.frame.loc[
        augmented.frame["state_id"].isin(set(base["state_id"]))].copy()
    assert len(hold_frame) == 26692
    stage_by_id = dict(zip(
        hold_frame["state_id"],
        np.asarray(STAGES.stage_partition(
            hold_frame["race_progress_frac"]))))
    xgb["stage"] = [stage_by_id[s] for s in xgb["state_id"]]
    base["stage"] = [stage_by_id[s] for s in base["state_id"]]

    # -- primary + secondary (Parts J/K) --------------------------------
    ll_b = AGG.race_macro(y, pb, races, "log_loss")
    ll_x = AGG.race_macro(y, px, races, "log_loss")
    delta = ll_x["value"] - ll_b["value"]
    rep_b = CAL.calibration_report(y, pb)
    rep_x = CAL.calibration_report(y, px)
    secondary = {
        "baseline": {"brier": AGG.race_macro(y, pb, races, "brier")[
            "value"], "roc_auc": AGG.race_macro(y, pb, races, "roc_auc")[
            "value"], "pr_auc": AGG.race_macro(y, pb, races, "pr_auc")[
            "value"], "ece": rep_b.get("expected_calibration_error"),
            "state_pooled_ll": AGG.state_pooled(y, pb, races, "log_loss")[
            "value"]},
        "xgboost": {"brier": AGG.race_macro(y, px, races, "brier")[
            "value"], "roc_auc": AGG.race_macro(y, px, races, "roc_auc")[
            "value"], "pr_auc": AGG.race_macro(y, px, races, "pr_auc")[
            "value"], "ece": rep_x.get("expected_calibration_error"),
            "state_pooled_ll": AGG.state_pooled(y, px, races, "log_loss")[
            "value"]}}
    # top-k via the canonical one-shot path (mirrors V3.1D run_v3_final)
    pred_res = PredictionResult(
        kind=PredictionKind.BINARY_PROBABILITY,
        state_ids=tuple(xgb["state_id"]),
        values=np.asarray(px), semantics=ProbabilitySemantics.
        INDEPENDENT_BINARY, positive_class=1)
    topk_x, _ = RUN.evaluate_winner_top_k(
        pred_res, plain, tuple(sorted(set(races))),
        allow_protected_holdout=True)
    secondary["xgboost"]["topk"] = topk_x
    secondary["baseline"]["topk"] = json.loads(Path(
        "results/v3/v3_1d_race_dynamics_holdout_and_freeze.json"
    ).read_text())["arm_b"]["topk"]

    # -- paired comparison + bootstrap (Part L) --------------------------
    comp = H.race_comparison(ll_b["per_race"], ll_x["per_race"])
    print(f"baseline LL={ll_b['value']:.6f} xgb LL={ll_x['value']:.6f} "
          f"delta={delta:.6f}", flush=True)
    print(f"CI=[{comp['bootstrap']['ci_lo']:.6f},"
          f"{comp['bootstrap']['ci_hi']:.6f}] "
          f"+{comp['races_improved']}/-{comp['races_worsened']}/"
          f"={comp['ties']}", flush=True)

    # -- stage (Part N) ---------------------------------------------------
    stage = {"stages": {}, "deltas": {}}
    for s in ("EARLY", "MID", "LATE"):
        mask = (base["stage"] == s).to_numpy()
        lb = AGG.race_macro(y[mask], pb[mask], races[mask], "log_loss")
        lx = AGG.race_macro(y[mask], px[mask], races[mask], "log_loss")
        stage["stages"][s] = {"baseline_ll": lb["value"],
                              "xgboost_ll": lx["value"],
                              "n_states": int(mask.sum()),
                              "n_races": int(lb["n_races"])}
        stage["deltas"][s] = lx["value"] - lb["value"]

    # -- probability quality (Part O; RAW only, nothing fitted) ------------
    quality = {}
    for name, probs in (("baseline", pb), ("xgboost", px)):
        per_race = AGG.race_macro(y, probs, races, "log_loss")["per_race"]
        quality[name] = {
            "brier": AGG.race_macro(y, probs, races, "brier")["value"],
            "ece": (rep_b if name == "baseline" else rep_x).get(
                "expected_calibration_error"),
            "extreme_probability_frequency": float(
                np.mean((probs < 0.01) | (probs > 0.5))),
            "worst_race_ll": float(max(per_race.values())),
            "max_probability": float(np.max(probs))}

    # -- diversity transfer (Part Q) -----------------------------------------
    m = base[["state_id", "race_id", "driver_id"]].assign(pb=pb).merge(
        xgb[["state_id", "probability"]].rename(
            columns={"probability": "px"}),
        on="state_id", validate="one_to_one")
    pa, pxx = m["pb"].to_numpy(), m["px"].to_numpy()
    ra = AGG.race_macro(y, pa, m["race_id"].astype(str).to_numpy(),
                        "log_loss")["per_race"]
    rb = AGG.race_macro(y, pxx, m["race_id"].astype(str).to_numpy(),
                        "log_loss")["per_race"]
    shared = sorted(set(ra) & set(rb))
    ta = m.loc[m.groupby("race_id")["pb"].idxmax()]
    tb = m.loc[m.groupby("race_id")["px"].idxmax()]
    disagree = ta["driver_id"].to_numpy() != tb["driver_id"].to_numpy()
    win_driver = base[base["y_true"] == 1.0].groupby("race_id")[
        "driver_id"].first()
    wa = np.array([ta.set_index("race_id").loc[r, "driver_id"]
                   == win_driver[r] for r in ta["race_id"]])
    wb = np.array([tb.set_index("race_id").loc[r, "driver_id"]
                   == win_driver[r] for r in tb["race_id"]])
    diversity = {
        "prediction_correlation": float(np.corrcoef(pa, pxx)[0, 1]),
        "residual_correlation": float(np.corrcoef(y - pa, y - pxx)[0, 1]),
        "per_race_ll_correlation": float(np.corrcoef(
            [ra[r] for r in shared], [rb[r] for r in shared])[0, 1]),
        "mean_abs_probability_gap": float(np.mean(np.abs(pa - pxx))),
        "top1_disagreement_races": int(disagree.sum()),
        "top1_xgb_correct": int((disagree & wb).sum()),
        "top1_baseline_correct": int((disagree & wa).sum()),
        "high_confidence_disagreement_states": int(
            ((np.abs(pa - pxx) > 0.2) & (np.maximum(pa, pxx) > 0.5)).sum()),
        "races_xgb_improves": sorted(
            r for r in shared if rb[r] < ra[r] - 1e-12),
        "races_baseline_improves": sorted(
            r for r in shared if ra[r] < rb[r] - 1e-12)}

    # -- transfer narrative inputs (Part M) -------------------------------------
    transfer = {"development": {"delta": 0.003539, "ci": [-0.003810,
                                                          0.011191],
                                "temporal": "MIXED", "d2_win": True,
                                "n_improved": 38},
                "holdout": {"delta": float(delta),
                            "ci": [comp["bootstrap"]["ci_lo"],
                                   comp["bootstrap"]["ci_hi"]],
                            "n_improved": comp["races_improved"]}}

    # -- final disposition + decisions (Parts R/S/T; transparent rules) ----
    # Standalone YES iff XGB strictly wins primary (no thresholds).
    standalone = "YES" if delta < 0 else "NO"
    n_imp = comp["races_improved"]
    tail_ok = quality["xgboost"]["worst_race_ll"] < \
        2.0 * quality["baseline"]["worst_race_ll"]
    useful_diversity = n_imp >= 6 and (
        int((disagree & wb).sum()) >= int((disagree & wa).sum())
        or diversity["residual_correlation"] < 0.95) and tail_ok
    if delta < 0:
        disposition = "KEEP_PRIMARY_CANDIDATE"
    elif useful_diversity:
        disposition = "KEEP_DIVERSITY_CANDIDATE"
    elif quality["xgboost"]["ece"] - quality["baseline"]["ece"] > 0.01 \
            and not tail_ok:
        disposition = "REJECT_PROBABILITY_QUALITY"
    elif comp["races_worsened"] >= 20:
        disposition = "REJECT_TEMPORAL_INSTABILITY"
    elif quality["xgboost"]["worst_race_ll"] > \
            3.0 * quality["baseline"]["worst_race_ll"]:
        disposition = "REJECT_COMPLEXITY_WITHOUT_VALUE"
    else:
        disposition = "REJECT_NO_IMPROVEMENT"
    v3_4 = "YES" if disposition in ("KEEP_PRIMARY_CANDIDATE",
                                    "KEEP_DIVERSITY_CANDIDATE") else "NO"

    # -- immutable records (Parts V/X/AB) ----------------------------------
    holdout_result = {
        **ids, "schema_version": "v3.3e-holdout-result-v1",
        "execution_manifest_identity": manifest["manifest_identity"],
        "finalist_recipe_identity": revealed["recipe_sha"],
        "prediction_artifact_hash": revealed["prediction_sha256"],
        "baseline_identity": {"source": str(BASELINE_PRED),
                              "n_states": len(base), "n_races": n_races,
                              "race_macro_ll": ll_b["value"]},
        "holdout_identity": {"season": 2025, "n_states": len(xgb),
                             "n_races": n_races},
        "primary_metrics": {"baseline_ll": ll_b["value"],
                            "xgboost_ll": ll_x["value"], "delta": delta},
        "secondary_metrics": secondary,
        "race_comparison": comp,
        "bootstrap": comp["bootstrap"],
        "stage_analysis": stage,
        "calibration": quality,
        "discrimination": {k: {m: secondary[k][m] for m in
                               ("roc_auc", "pr_auc", "topk")}
                           for k in ("baseline", "xgboost")},
        "diversity": diversity,
        "transfer": transfer,
        "final_disposition": disposition,
        "standalone_decision": standalone,
        "v3_4_eligibility": v3_4,
        "holdout_revealed": True,
        "no_retry_attestation": "single fit/predict per frozen recipe; "
                                "no regeneration; prediction hash "
                                "authoritative"}
    blob = json.dumps(holdout_result, sort_keys=True,
                      separators=(",", ":"))
    holdout_result["result_hash"] = hashlib.sha256(
        blob.encode()).hexdigest()
    write("holdout_result.json", holdout_result)

    card = {**ids, "v3_3_question": "can any of 4 model families beat "
            "V3.1B LogReg on race-macro winner LL with valid uncertainty",
            "baseline": "V3.1B LogReg C=0.01, 110 features, RAW",
            "candidate_landscape": ["logistic_regression",
                                    "hist_gradient_boosting",
                                    "extra_trees", "xgboost"],
            "rejected_hgb": "C REJECT_NO_IMPROVEMENT; D closed",
            "rejected_et": "C diversity; D refinement+calibration failed "
                           "(REJECT_NO_IMPROVEMENT)",
            "sole_finalist": "xgboost lr=0.03/d3/mcw5 RAW (D recipe "
            + revealed["recipe_sha"][:12] + ")",
            "development_evidence": transfer["development"],
            "holdout_evidence": {"delta": float(delta),
                                 "ci": transfer["holdout"]["ci"]},
            "final_standalone_decision": standalone,
            "v3_4_eligibility": v3_4,
            "known_limitations": ["single 24-race holdout; CIs honest",
                                  "one-shot: no retry by design",
                                  "RAW probabilities; no 2025 calibration"],
            "artifact_identities": {
                "manifest": manifest["manifest_identity"],
                "recipe": revealed["recipe_sha"],
                "prediction": revealed["prediction_sha256"],
                "result": holdout_result["result_hash"]}}
    write("v3_3_scientific_card.json", card)
    write("reproducibility.json",
          {**ids, "commands": [
              "uv run python scripts/freeze_v3_3e_manifest.py  # pre-reveal only",
              "uv run python scripts/run_v3_3e_holdout.py  # ONE-SHOT; refuses rerun",
              "uv run python scripts/analyze_v3_3e.py  # rebuild from frozen predictions",
              "uv run pytest tests/test_v3_3e_holdout.py -q"],
           "note": "routine analysis uses the frozen prediction artifact; "
                   "retraining is NOT the reproducibility path"})
    machine = {**ids, "schema_version": "v3.3e-final-holdout-v1",
               "parent": {"tag": "v3.2-monte-carlo-2",
                          "commit": "197979d40af0c9dbf90667781d9c83e41613b047"},
               "execution_manifest_identity": manifest["manifest_identity"],
               "finalist_recipe_identity": revealed["recipe_sha"],
               "prediction_identity": revealed["prediction_sha256"],
               "baseline_ll": ll_b["value"], "xgboost_ll": ll_x["value"],
               "primary_comparison": delta,
               "bootstrap": comp["bootstrap"],
               "final_disposition": disposition,
               "standalone_decision": standalone,
               "v3_4_eligibility": v3_4,
               "tests": "see test_report.json",
               "next_recommendation": "V3.3 final validation/freeze"}
    Path("results/v3/v3_3e_final_holdout.json").write_text(
        json.dumps(machine, indent=1, sort_keys=True) + "\n")
    print(f"disposition={disposition} standalone={standalone} "
          f"v3.4={v3_4}", flush=True)
    print("analysis complete.", flush=True)


if __name__ == "__main__":
    main()
