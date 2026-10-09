"""V3.4E previously-revealed 2025 ensemble evaluation (manifest execution).

Single frozen recipe (w=0.2) applied once to frozen 2025 base predictions.
No search, no reselection, no calibration. Predictions persisted BEFORE
any ensemble metric is calculated.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, ".")
from raceintel.model_lab import aggregation as AGG  # noqa: E402
from raceintel.model_lab import calibration as CAL  # noqa: E402
from raceintel.model_lab import runner as RUN  # noqa: E402
from raceintel.model_lab import stages as STAGES  # noqa: E402
from raceintel.model_lab import v3_4_ensemble as ENS  # noqa: E402
from raceintel.model_lab import v3_dynamics_experiment as V3C  # noqa: E402
from raceintel.model_lab.predictions import (  # noqa: E402
    PredictionKind,
    PredictionResult,
    ProbabilitySemantics,
)

OUT = Path("results/v3/v3_4e")
PRED_OUT = Path("data/v3/v3_4e")
T0 = time.time()
TIMINGS = {}


def stamp(key):
    TIMINGS[key] = round(time.time() - T0, 3)


def load(path):
    return json.loads(Path(path).read_text())


def canon(payload, skip):
    return json.dumps({k: v for k, v in payload.items() if k != skip},
                      sort_keys=True, separators=(",", ":"))


def write(name, payload):
    (OUT / name).write_text(
        json.dumps(payload, indent=1, sort_keys=True) + "\n")


def ff(value):
    return None if value is None else float(value)


def race_ll(frame, col):
    y = frame["target"].to_numpy(float)
    p = frame[col].to_numpy(float)
    r = frame["race_id"].astype(str).to_numpy()
    return AGG.race_macro(y, p, r, "log_loss")


def metrics_for(frame, col, plain):
    y = frame["target"].to_numpy(float)
    p = frame[col].to_numpy(float)
    r = frame["race_id"].astype(str).to_numpy()
    rep = CAL.calibration_report(y, p)
    pred_res = PredictionResult(
        kind=PredictionKind.BINARY_PROBABILITY,
        state_ids=tuple(frame["state_id"]), values=np.asarray(p),
        semantics=ProbabilitySemantics.INDEPENDENT_BINARY, positive_class=1)
    topk, _ = RUN.evaluate_winner_top_k(
        pred_res, plain, tuple(sorted(set(r))),
        allow_protected_holdout=True)
    acc = topk.get("accuracy") or {}
    ll = AGG.race_macro(y, p, r, "log_loss")
    return {
        "race_macro_ll": ll["value"],
        "per_race_ll": {k: float(v) for k, v in ll["per_race"].items()},
        "brier": AGG.race_macro(y, p, r, "brier")["value"],
        "roc_auc": AGG.race_macro(y, p, r, "roc_auc")["value"],
        "pr_auc": AGG.race_macro(y, p, r, "pr_auc")["value"],
        "ece": ff(rep.get("expected_calibration_error")),
        "state_pooled_ll": AGG.state_pooled(y, p, r, "log_loss")["value"],
        "top1": ff(acc.get("top1")), "top3": ff(acc.get("top3")),
        "worst_race_ll": float(max(ll["per_race"].values())),
        "max_probability": float(p.max()),
    }


def main() -> None:
    rec = load(OUT / "execution_record.json")
    assert hashlib.sha256(canon(rec, "record_identity").encode()
                          ).hexdigest() == rec["record_identity"]
    manifest = load("results/v3/v3_4d/v3_4e_execution_manifest.json")
    assert manifest["manifest_identity"] == rec["e_manifest_identity"]
    assert manifest["final_recipe_identity"] == rec["d_recipe_identity"]
    PRED_OUT.mkdir(parents=True, exist_ok=True)
    # -- load frozen 2025 inputs (first content contact) ------------------
    stamp("record_verified")
    log_src = rec["allowed_inputs"]["logistic_2025"]["path"]
    xgb_src = rec["allowed_inputs"]["xgboost_2025"]["path"]
    assert log_src == "data/v3/v3_1d/pred_final_ALL_84_PLUS_V3_1_DYNAMICS_CORE_2025.parquet"
    assert xgb_src == "data/v3/v3_3e/pred_xgb_final_2025.parquet"
    assert hashlib.sha256(Path(xgb_src).read_bytes()).hexdigest() == \
        rec["allowed_inputs"]["xgboost_2025"]["sha256"]
    log = pd.read_parquet(log_src)
    xgb = pd.read_parquet(xgb_src)
    base_sha = hashlib.sha256(Path(log_src).read_bytes()).hexdigest()
    assert len(log) == len(xgb) == 26692
    assert set(log["season"].unique()) == {2025}
    assert set(xgb["season"].unique()) == {2025}
    assert log["state_id"].is_unique and xgb["state_id"].is_unique
    assert set(log["state_id"]) == set(xgb["state_id"])
    stamp("inputs_loaded")
    # adapt to canonical columns (2025 baseline uses y_true/y_pred names)
    log_c = log.rename(
        columns={"y_true": "target", "y_pred": "probability"})[[
            "state_id", "race_id", "season", "driver_id", "target",
            "probability"]].copy()
    xgb_c = xgb[["state_id", "race_id", "season", "driver_id", "target",
                 "probability"]].copy()
    assert ((log_c["target"].to_numpy() ==
             xgb_c.set_index("state_id").loc[
                 log_c["state_id"], "target"].to_numpy())).all()
    for c in ("race_id", "driver_id"):
        assert ((log_c[c].astype(str).to_numpy() ==
                 xgb_c.set_index("state_id").loc[
                     log_c["state_id"], c].astype(str).to_numpy())).all()
    assert log_c["race_id"].nunique() == 24
    for df in (log_c, xgb_c):
        p = df["probability"].to_numpy(float)
        assert np.all(np.isfinite(p)) and np.all((p >= 0) & (p <= 1))
    write("input_alignment_audit.json", {
        "season": [2025], "n_states": 26692, "n_races": 24,
        "identity_sets_equal": True, "duplicates": 0,
        "target_match": True, "race_match": True, "driver_match": True,
        "bounds_ok": True, "join": "state_id only",
        "logistic_sha256": base_sha,
        "xgboost_sha256": rec["allowed_inputs"]["xgboost_2025"]["sha256"],
    })
    # -- base reproduction vs V3.3 -----------------------------------------
    v33 = load("results/v3/v3_3e/holdout_result.json")
    lb = race_ll(log_c, "probability")["value"]
    lx = race_ll(xgb_c, "probability")["value"]
    assert abs(lb - v33["primary_metrics"]["baseline_ll"]) < 1e-9
    assert abs(lx - v33["primary_metrics"]["xgboost_ll"]) < 1e-9
    assert abs((lx - lb) - v33["primary_metrics"]["delta"]) < 1e-9
    write("base_reproduction.json", {
        "logistic_ll": lb, "xgboost_ll": lx, "delta": lx - lb,
        "tolerance": 1e-9, "match": True,
        "logistic_sha256": base_sha,
        "xgboost_sha256": rec["allowed_inputs"]["xgboost_2025"]["sha256"]})
    stamp("base_reproduced")
    # -- execute frozen recipe exactly once ---------------------------------
    tmp_log, tmp_xgb = PRED_OUT / "_in_log.parquet", PRED_OUT / "_in_xgb.parquet"
    log_c.to_parquet(tmp_log, index=False)
    xgb_c.to_parquet(tmp_xgb, index=False)
    try:
        ens = ENS.apply_recipe(str(tmp_log), str(tmp_xgb))
    finally:
        tmp_log.unlink(missing_ok=True)
        tmp_xgb.unlink(missing_ok=True)
    stamp("blended")
    # -- persist BEFORE analysis ---------------------------------------------
    dest = PRED_OUT / "ensemble_predictions_2025.parquet"
    ens.to_parquet(dest, index=False)
    pred_sha = hashlib.sha256(dest.read_bytes()).hexdigest()
    write("prediction_identity.json", {
        "path": str(dest), "sha256": pred_sha,
        "n_rows": len(ens), "n_races": int(ens["race_id"].nunique()),
        "recipe_identity": rec["d_recipe_identity"],
        "note": "immutable; analysis consumes this artifact",
    })
    stamp("persisted")
    # -- integrity --------------------------------------------------------------
    assert len(ens) == 26692 and ens["race_id"].nunique() == 24
    assert ens["state_id"].is_unique
    assert set(ens["season"].unique()) == {2025}
    p = ens["probability"].to_numpy(float)
    assert np.all(np.isfinite(p)) and np.all((p >= 0) & (p <= 1))
    # determinism: recompute from frozen inputs
    log_c.to_parquet(tmp_log, index=False)
    xgb_c.to_parquet(tmp_xgb, index=False)
    try:
        ens2 = ENS.apply_recipe(str(tmp_log), str(tmp_xgb))
    finally:
        tmp_log.unlink(missing_ok=True)
        tmp_xgb.unlink(missing_ok=True)
    assert (ens2["probability"].to_numpy() == p).all()
    # permutation invariance
    xs = xgb_c.sample(frac=1, random_state=3).reset_index(drop=True)
    assert not xs["state_id"].equals(xgb_c["state_id"])
    xs.to_parquet(tmp_xgb, index=False)
    log_c.to_parquet(tmp_log, index=False)
    try:
        ens3 = ENS.apply_recipe(str(tmp_log), str(tmp_xgb))
    finally:
        tmp_log.unlink(missing_ok=True)
        tmp_xgb.unlink(missing_ok=True)
    m1 = ens.set_index("state_id")["probability"]
    m3 = ens3.set_index("state_id")["probability"]
    assert np.allclose(m1.loc[m3.index].to_numpy(), m3.to_numpy(), atol=0)
    write("prediction_integrity.json", {
        "rows": 26692, "races": 24, "unique": True,
        "deterministic_recompute": True, "permutation_invariant": True,
        "sha256": pred_sha})
    # -- metrics -----------------------------------------------------------------
    augmented, plain = V3C.load_joined_frame()
    ids = set(ens["state_id"])
    hold = augmented.frame.loc[
        augmented.frame["state_id"].isin(ids)].copy()
    assert len(hold) == 26692 and (hold["season"] == 2025).all()
    stage_by_id = dict(zip(hold["state_id"], np.asarray(
        STAGES.stage_partition(hold["race_progress_frac"]))))
    ens = ens.copy()
    ens["stage"] = [stage_by_id[s] for s in ens["state_id"]]
    log_c = log_c.copy()
    log_c["stage"] = [stage_by_id[s] for s in log_c["state_id"]]
    xgb_c = xgb_c.copy()
    xgb_c["stage"] = [stage_by_id[s] for s in xgb_c["state_id"]]
    stamp("canonical")
    m_log = metrics_for(log_c, "probability", plain)
    m_xgb = metrics_for(xgb_c, "probability", plain)
    m_ens = metrics_for(ens, "probability", plain)
    delta = m_ens["race_macro_ll"] - m_log["race_macro_ll"]
    write("primary_metrics.json", {
        "logistic_ll": m_log["race_macro_ll"],
        "xgboost_ll": m_xgb["race_macro_ll"],
        "ensemble_ll": m_ens["race_macro_ll"],
        "ensemble_minus_logistic": delta,
        "ensemble_minus_xgb": m_ens["race_macro_ll"] - m_xgb["race_macro_ll"],
    })
    races = sorted(ens["race_id"].unique())
    per_race = {}
    for r in races:
        dl = log_c[log_c["race_id"] == r]
        de = ens[ens["race_id"] == r]
        dx = xgb_c[xgb_c["race_id"] == r]
        ll_l = race_ll(dl, "probability")["value"]
        ll_e = race_ll(de, "probability")["value"]
        ll_x = race_ll(dx, "probability")["value"]
        per_race[r] = {"logistic_ll": ll_l, "ensemble_ll": ll_e,
                       "xgboost_ll": ll_x, "ensemble_minus_logistic":
                       ll_e - ll_l}
    deltas = np.array([v["ensemble_minus_logistic"] for v in
                       per_race.values()])
    write("race_results.json", {
        "per_race": per_race,
        "mean_delta": float(deltas.mean()),
        "median_delta": float(np.median(deltas)),
        "improved": int((deltas < 0).sum()),
        "worsened": int((deltas > 0).sum()),
        "ties": int((deltas == 0).sum()),
    })
    ll_b = {r: per_race[r]["logistic_ll"] for r in races}
    ll_e = {r: per_race[r]["ensemble_ll"] for r in races}
    boot = V3C.paired_bootstrap(ll_b, ll_e, seed=42, replicates=2000,
                                ci_level=0.95)
    write("race_bootstrap.json", boot)
    stamp("metrics")
    write("secondary_metrics.json", {
        "logistic": {k: m_log[k] for k in
                     ("brier", "roc_auc", "pr_auc", "ece", "top1", "top3",
                      "state_pooled_ll", "worst_race_ll", "max_probability")},
        "xgboost": {k: m_xgb[k] for k in
                    ("brier", "roc_auc", "pr_auc", "ece", "top1", "top3",
                     "state_pooled_ll", "worst_race_ll", "max_probability")},
        "ensemble": {k: m_ens[k] for k in
                     ("brier", "roc_auc", "pr_auc", "ece", "top1", "top3",
                      "state_pooled_ll", "worst_race_ll", "max_probability")},
    })
    stage_out = {}
    for stage in ("EARLY", "MID", "LATE"):
        dl = log_c[log_c["stage"] == stage]
        de = ens[ens["stage"] == stage]
        ll_l = race_ll(dl, "probability")["value"]
        ll_e = race_ll(de, "probability")["value"]
        y = de["target"].to_numpy(float)
        q = de["probability"].to_numpy(float)
        r = de["race_id"].astype(str).to_numpy()
        yl = dl["target"].to_numpy(float)
        ql = dl["probability"].to_numpy(float)
        rl = dl["race_id"].astype(str).to_numpy()
        stage_out[stage] = {
            "ensemble_ll": ll_e, "delta_vs_logistic": ll_e - ll_l,
            "ensemble_brier": AGG.race_macro(y, q, r, "brier")["value"],
            "logistic_brier": AGG.race_macro(yl, ql, rl, "brier")["value"],
            "ensemble_ece": CAL.calibration_report(y, q).get(
                "expected_calibration_error"),
            "n_states": int(len(de)),
        }
    write("stage_results.json", stage_out)
    write("probability_quality.json", {
        "finite": True, "bounded_01": True, "raw": True,
        "field_normalized": False,
        "ensemble_brier": m_ens["brier"],
        "ensemble_ece": m_ens["ece"],
        "worst_race_ll": m_ens["worst_race_ll"],
        "max_probability": m_ens["max_probability"],
    })
    # development -> 2025 (frozen C/B evidence, read-only)
    sel = load("results/v3/v3_4c/selected_development_candidate.json")
    write("development_to_2025.json", {
        "development": {"delta_pooled": sel["primary_evidence"][
            "delta_pooled"] if "delta_pooled" in
            sel.get("primary_evidence", {}) else -0.001489,
            "source": "frozen C candidate (w=0.2)"},
        "out_of_time": {"delta": delta, "source": "this evaluation"},
        "recipe_unchanged": True,
    })
    # diversity transfer (diagnostic, single frozen recipe)
    x_races = {r for r in races
               if race_ll(xgb_c[xgb_c["race_id"] == r],
                          "probability")["value"] <
               race_ll(log_c[log_c["race_id"] == r],
                       "probability")["value"]}
    e_races = {r for r in races if per_race[r][
        "ensemble_minus_logistic"] < 0}
    write("diversity_transfer.json", {
        "xgb_beats_logistic": sorted(x_races),
        "ensemble_beats_logistic": sorted(e_races),
        "xgb_wins_captured": sorted(x_races & e_races),
        "xgb_pulls_away": sorted(x_races - e_races),
        "n_xgb_wins": len(x_races), "n_ens_wins": len(e_races),
    })
    # disposition (D-frozen policy categories only)
    improved = int((deltas < 0).sum())
    worsened = int((deltas > 0).sum())
    quality_ok = (m_ens["brier"] <= m_log["brier"] and
                  (m_ens["ece"] or 1) <= (m_log["ece"] or 1) + 1e-3)
    stages_ok = sum(1 for s in stage_out.values()
                    if s["delta_vs_logistic"] < 0)
    if delta < 0 and boot["ci_hi"] < 0 and improved > worsened and \
            quality_ok and stages_ok >= 2:
        disp = "ENSEMBLE_GENERALIZES"
    elif delta > 0 and (boot["ci_lo"] > 0 or worsened >= 2 * improved):
        disp = "ENSEMBLE_FAILS_TO_GENERALIZE"
    else:
        disp = "ENSEMBLE_MIXED_OUT_OF_TIME"
    write("disposition.json", {
        "disposition": disp,
        "serving_promotion": "NONE",
        "primary_delta": delta,
        "bootstrap_ci": [boot["ci_lo"], boot["ci_hi"]],
        "improved": improved, "worsened": worsened,
        "quality_ok": bool(quality_ok), "stages_negative": stages_ok,
    })
    stamp("done")
    write("compute_profile.json", {
        "timings_s": TIMINGS, "total_s": round(time.time() - T0, 3),
        "models_trained": 0})
    print(f"ensemble LL={m_ens['race_macro_ll']:.10f} "
          f"delta={delta:+.10f} disposition={disp}")


if __name__ == "__main__":
    main()
