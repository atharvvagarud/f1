"""V3.4B development ensemble experiments (frozen A contract execution).

Reads ONLY the six frozen development OOF streams (+ shared feature
matrix for stage/canonical, filtered to development state_ids).
No 2025 contact. No selection. No fitting except the frozen
expanding-window stacker.
"""
import hashlib
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.linear_model import LogisticRegression

sys.path.insert(0, ".")
from raceintel.model_lab import aggregation as AGG  # noqa: E402
from raceintel.model_lab import calibration as CAL  # noqa: E402
from raceintel.model_lab import runner as RUN  # noqa: E402
from raceintel.model_lab import stages as STAGES  # noqa: E402
from raceintel.model_lab import v3_dynamics_experiment as V3C  # noqa: E402
from raceintel.model_lab.predictions import (  # noqa: E402
    PredictionKind,
    PredictionResult,
    ProbabilitySemantics,
)

OUT = Path("results/v3/v3_4b")
PRED_OUT = Path("data/v3/v3_4b")
FOLDS = ["D1", "D2", "D3"]
T0 = time.time()
TIMINGS = {}


def stamp(key):
    TIMINGS[key] = round(time.time() - T0, 3)


def write(name, payload):
    p = OUT / name
    p.write_text(json.dumps(payload, indent=1, sort_keys=True) + "\n")
    return p


def ff(value):
    return None if value is None else float(value)


# -- contract + prereg verification ------------------------------------
A = json.loads(Path("results/v3/v3_4a/experiment_contract.json").read_text())
A_SHA = "d6b12074db9895844c28c05c78baf56c113d63c33d685c5913c92ebb5036b352"
blob_a = json.dumps({k: v for k, v in A.items() if k != "contract_hash"},
                    sort_keys=True, separators=(",", ":"))
assert hashlib.sha256(blob_a.encode()).hexdigest() == \
    A["contract_hash"] == A_SHA, "A contract identity failure"

PRE = json.loads((OUT / "preregistration.json").read_text())
blob_p = json.dumps({k: v for k, v in PRE.items()
                     if k != "preregistration_identity"},
                    sort_keys=True, separators=(",", ":"))
assert hashlib.sha256(blob_p.encode()).hexdigest() == \
    PRE["preregistration_identity"], "B prereg mutated"
assert PRE["a_contract_identity"] == A_SHA
GRID = list(A["blend_grid"])
assert GRID == PRE["blend_grid"] == [round(i / 10, 1) for i in range(11)]
assert PRE["selection"] == "NONE IN B (V3.4C owns selection)"
for p in A["base_prediction_contract"]["streams"]["logistic_oof"] + \
        A["base_prediction_contract"]["streams"]["xgboost_oof"]:
    assert "2025" not in p, f"forbidden path in A streams: {p}"

# -- firewalled loader (development OOF allowlist only) -----------------
ALLOW = set(A["base_prediction_contract"]["streams"]["logistic_oof"]) | \
    set(A["base_prediction_contract"]["streams"]["xgboost_oof"])


def load_oof(path):
    assert path in ALLOW, f"forbidden artifact path: {path}"
    assert "2025" not in path
    frame = pd.read_parquet(path)
    assert not (frame["season"] == 2025).any(), "2025 row loaded"
    return frame


def race_macro_ll(frame, col="probability"):
    y = frame["target"].to_numpy(float)
    p = frame[col].to_numpy(float)
    r = frame["race_id"].astype(str).to_numpy()
    return AGG.race_macro(y, p, r, "log_loss")


def metrics_for(frame, col, races_list, plain):
    y = frame["target"].to_numpy(float)
    p = frame[col].to_numpy(float)
    r = frame["race_id"].astype(str).to_numpy()
    rep = CAL.calibration_report(y, p)
    pred_res = PredictionResult(
        kind=PredictionKind.BINARY_PROBABILITY,
        state_ids=tuple(frame["state_id"]), values=np.asarray(p),
        semantics=ProbabilitySemantics.INDEPENDENT_BINARY, positive_class=1)
    topk, _ = RUN.evaluate_winner_top_k(
        pred_res, plain, tuple(sorted(set(races_list))))
    acc = topk.get("accuracy") or {}
    return {
        "race_macro_ll": AGG.race_macro(y, p, r, "log_loss")["value"],
        "per_race_ll": {k: float(v) for k, v in
                        AGG.race_macro(y, p, r, "log_loss")["per_race"].items()},
        "brier": AGG.race_macro(y, p, r, "brier")["value"],
        "roc_auc": AGG.race_macro(y, p, r, "roc_auc")["value"],
        "pr_auc": AGG.race_macro(y, p, r, "pr_auc")["value"],
        "ece": ff(rep.get("expected_calibration_error")),
        "state_pooled_ll": AGG.state_pooled(y, p, r, "log_loss")["value"],
        "topk": {"top1": ff(acc.get("top1")),
                 "top3": ff(acc.get("top3")),
                 "status": topk.get("status")},
        "worst_race_ll": float(max(
            AGG.race_macro(y, p, r, "log_loss")["per_race"].values())),
        "max_probability": float(p.max()),
    }


def main() -> None:
    PRED_OUT.mkdir(parents=True, exist_ok=True)
    # -- materialize + align -------------------------------------------
    frames = {}
    for fold in FOLDS:
        b = load_oof(
            f"data/v3/v3_3c/oof_baseline__{fold}.parquet")
        x = load_oof(
            f"data/v3/v3_3d/oof_d_refined_xgboost__{fold}.parquet")
        m = b.merge(x[["state_id", "probability"]], on="state_id",
                    suffixes=("_log", "_xgb"))
        assert len(m) == len(b) == len(x) and m["state_id"].is_unique
        assert (m["season"] != 2025).all()
        for c in ["race_id", "driver_id", "target", "fold", "stage"]:
            assert (m[c].astype(str) == b.set_index("state_id").loc[
                m["state_id"], c].astype(str).to_numpy()).all()
        assert np.all(np.isfinite(m["probability_log"])) and \
            np.all(np.isfinite(m["probability_xgb"]))
        assert ((m["probability_log"] >= 0) &
                (m["probability_log"] <= 1)).all()
        assert ((m["probability_xgb"] >= 0) &
                (m["probability_xgb"] <= 1)).all()
        frames[fold] = m
    assert len(frames["D1"]) == 23577 and len(frames["D2"]) == 24422 \
        and len(frames["D3"]) == 26606
    full = pd.concat([frames[f] for f in FOLDS], ignore_index=True)
    assert len(full) == 74605 and full["race_id"].nunique() == 68
    stamp("alignment")
    # V3.3 prob-hash reproduction (concat D1+D2+D3 probability bytes)
    assert hashlib.sha256(full["probability_log"].to_numpy().tobytes()
                          ).hexdigest() == \
        PRE["base_predictions"]["logistic_oof"]["v3_3_prob_hash"]
    assert hashlib.sha256(full["probability_xgb"].to_numpy().tobytes()
                          ).hexdigest() == \
        PRE["base_predictions"]["xgboost_oof"]["v3_3_prob_hash"]
    write("alignment_audit.json", {
        "a_contract_identity": A_SHA,
        "join": "state_id only",
        "rows": {f: len(frames[f]) for f in FOLDS},
        "total_rows": len(full),
        "n_races": int(full["race_id"].nunique()),
        "per_fold_races": {f: int(frames[f]["race_id"].nunique())
                           for f in FOLDS},
        "mismatches": 0,
        "v3_3_prob_hash_match": {"logistic": True, "xgboost": True},
        "seasons": sorted(int(s) for s in full["season"].unique()),
        "no_2025": True,
    })
    # -- baseline reproduction ------------------------------------------
    base_ref = PRE["base_predictions"]["logistic_oof"]
    xgb_ref = PRE["base_predictions"]["xgboost_oof"]
    base_rep, xgb_rep = {}, {}
    for fold in FOLDS:
        lb = race_macro_ll(frames[fold], "probability_log")["value"]
        lx = race_macro_ll(frames[fold], "probability_xgb")["value"]
        assert abs(lb - base_ref["v3_3_per_fold_ll"][fold]) < 1e-9
        assert abs(lx - xgb_ref["v3_3_per_fold_ll"][fold]) < 1e-9
        base_rep[fold], xgb_rep[fold] = lb, lx
    lb_pool = race_macro_ll(full, "probability_log")["value"]
    lx_pool = race_macro_ll(full, "probability_xgb")["value"]
    assert abs(lb_pool - base_ref["v3_3_pooled_race_macro_ll"]) < 1e-9
    assert abs(lx_pool - xgb_ref["v3_3_pooled_race_macro_ll"]) < 1e-9
    write("baseline_reproduction.json", {
        "logistic_per_fold": base_rep, "logistic_pooled": lb_pool,
        "xgboost_per_fold": xgb_rep, "xgboost_pooled": lx_pool,
        "tolerance": 1e-9, "match": True})
    stamp("baseline")
    # -- shared stage + canonical (filtered to dev states immediately) --
    augmented, plain = V3C.load_joined_frame()
    dev_ids = set(full["state_id"])
    hold = augmented.frame.loc[
        augmented.frame["state_id"].isin(dev_ids)].copy()
    assert len(hold) == len(full) and (hold["season"] != 2025).all()
    stage_by_id = dict(zip(hold["state_id"], np.asarray(
        STAGES.stage_partition(hold["race_progress_frac"]))))
    for fold in FOLDS:
        frames[fold] = frames[fold].copy()
        frames[fold]["stage"] = [stage_by_id[s]
                                 for s in frames[fold]["state_id"]]
    full = pd.concat([frames[f] for f in FOLDS], ignore_index=True)
    stamp("canonical")
    # -- fixed convex blends ---------------------------------------------
    blend_results, blend_boot, blend_stage = {}, {}, {}
    pred_hashes = {}
    for w in GRID:
        key = f"w_{w:.1f}"
        per_fold, per_boot, per_stage = {}, {}, {}
        for fold in FOLDS:
            d = frames[fold].copy()
            d["probability"] = (1 - w) * d["probability_log"] + \
                w * d["probability_xgb"]
            if w == 0.0:
                assert (d["probability"].to_numpy() ==
                        d["probability_log"].to_numpy()).all()
            if w == 1.0:
                assert (d["probability"].to_numpy() ==
                        d["probability_xgb"].to_numpy()).all()
            assert ((d["probability"] >= 0) &
                    (d["probability"] <= 1)).all()
            out = PRED_OUT / f"blend_{key}__{fold}.parquet"
            d[["state_id", "race_id", "season", "driver_id", "target",
               "fold", "stage", "probability"]].to_parquet(out, index=False)
            pred_hashes[f"{key}__{fold}"] = hashlib.sha256(
                out.read_bytes()).hexdigest()
            races = d["race_id"].astype(str).tolist()
            met = metrics_for(d, "probability", races, plain)
            met["delta_vs_logistic"] = met["race_macro_ll"] - \
                base_rep[fold]
            per_fold[fold] = met
            ll_b = race_macro_ll(frames[fold], "probability_log")
            ll_e = race_macro_ll(d, "probability")
            boot = V3C.paired_bootstrap(ll_b["per_race"], ll_e["per_race"],
                                        seed=42, replicates=2000, ci_level=0.95)
            per_boot[fold] = boot
            st = {}
            for stage in ("EARLY", "MID", "LATE"):
                dd = d[d["stage"] == stage]
                db = frames[fold][frames[fold]["stage"] == stage]
                ll = race_macro_ll(dd, "probability")["value"]
                y = dd["target"].to_numpy(float)
                p = dd["probability"].to_numpy(float)
                r = dd["race_id"].astype(str).to_numpy()
                st[stage] = {
                    "race_macro_ll": ll,
                    "delta_vs_logistic": ll - race_macro_ll(
                        db, "probability_log")["value"],
                    "brier": AGG.race_macro(y, p, r, "brier")["value"],
                    "ece": ff(CAL.calibration_report(y, p).get(
                        "expected_calibration_error")),
                    "n_states": int(len(dd)),
                }
            per_stage[fold] = st
        pool = pd.concat([frames[f].assign(
            probability=(1 - w) * frames[f]["probability_log"] +
            w * frames[f]["probability_xgb"]) for f in FOLDS],
            ignore_index=True)
        races = pool["race_id"].astype(str).tolist()
        met = metrics_for(pool, "probability", races, plain)
        met["delta_vs_logistic"] = met["race_macro_ll"] - lb_pool
        ll_b = race_macro_ll(full, "probability_log")
        ll_e = race_macro_ll(pool, "probability")
        boot = V3C.paired_bootstrap(ll_b["per_race"], ll_e["per_race"],
                                    seed=42, replicates=2000, ci_level=0.95)
        blend_results[key] = {"weight": w, "per_fold": per_fold,
                              "pooled": met,
                              "descriptive_status":
                              "DESCRIPTIVE_ONLY_NOT_SELECTED"}
        blend_boot[key] = {"per_fold": per_boot, "pooled": boot}
        blend_stage[key] = per_stage
        stamp(f"blend_{key}")
    write("blend_results.json", {**{"a_contract_identity": A_SHA}, **blend_results})
    write("blend_race_bootstrap.json", blend_boot)
    write("blend_stage_results.json", blend_stage)
    # -- weight landscape --------------------------------------------------
    base_pool_met = metrics_for(full, "probability_log",
                                full["race_id"].astype(str).tolist(), plain)
    base_pool_per_race = AGG.race_macro(
        full["target"].to_numpy(float),
        full["probability_log"].to_numpy(float),
        full["race_id"].astype(str).to_numpy(), "log_loss")["per_race"]
    landscape = []
    for w in GRID:
        key = f"w_{w:.1f}"
        row = {"weight": w,
               "primary_ll_pooled": blend_results[key]["pooled"][
                   "race_macro_ll"],
               "delta_pooled": blend_results[key]["pooled"][
                   "delta_vs_logistic"],
               "ci_pooled": [blend_boot[key]["pooled"]["ci_lo"],
                             blend_boot[key]["pooled"]["ci_hi"]],
               "deltas": {f: blend_results[key]["per_fold"][f][
                   "delta_vs_logistic"] for f in FOLDS},
               "brier_delta_pooled": blend_results[key]["pooled"]["brier"] -
               base_pool_met["brier"],
               "ece_delta_pooled": blend_results[key]["pooled"]["ece"] -
               base_pool_met["ece"],
               "improved_pooled": int(sum(
                   1 for r, v in blend_results[key]["pooled"][
                       "per_race_ll"].items()
                   if v < base_pool_per_race[r])),
               "worsened_pooled": int(sum(
                   1 for r, v in blend_results[key]["pooled"][
                       "per_race_ll"].items()
                   if v > base_pool_per_race[r])),
               "status": "DESCRIPTIVE_ONLY_NOT_SELECTED"}
        landscape.append(row)
    write("weight_landscape.json", landscape)
    # -- expanding-window stacker -------------------------------------------
    CLIP = PRE["stacker"]["clip"]

    def feats(d):
        p = np.clip(d[["probability_log", "probability_xgb"]].to_numpy(
            float), CLIP[0], CLIP[1])
        return np.log(p / (1 - p))

    coefs, stacker_res, stacker_boot = {}, {}, {}
    hist = {"D2": ["D1"], "D3": ["D1", "D2"]}
    for fold in FOLDS:
        if fold == "D1":
            d = frames["D1"].copy()
            d["probability"] = d["probability_log"]
            coefs["D1"] = {"status": "NOT_EVALUABLE/baseline-only fallback",
                           "intercept": None, "coef_logistic": None,
                           "coef_xgb": None, "n_train_rows": 0,
                           "n_train_races": 0}
            met = metrics_for(d, "probability",
                              d["race_id"].astype(str).tolist(), plain)
            stacker_res["D1"] = {**met, "note": "baseline fallback, "
                                                 "not a learned result"}
            stacker_boot["D1"] = None
            out = PRED_OUT / "stacker__D1.parquet"
            d[["state_id", "race_id", "season", "driver_id", "target",
               "fold", "stage", "probability"]].to_parquet(out, index=False)
            pred_hashes["stacker__D1"] = hashlib.sha256(
                out.read_bytes()).hexdigest()
            continue
        tr = pd.concat([frames[f] for f in hist[fold]], ignore_index=True)
        Xtr, ytr = feats(tr), tr["target"].to_numpy(float)
        clf = LogisticRegression(C=1.0, solver="lbfgs", random_state=42)
        clf.fit(Xtr, ytr)
        d = frames[fold].copy()
        d["probability"] = clf.predict_proba(feats(d))[:, 1]
        assert ((d["probability"] > 0) &
                (d["probability"] < 1)).all()
        coefs[fold] = {
            "intercept": float(clf.intercept_[0]),
            "coef_logistic": float(clf.coef_[0][0]),
            "coef_xgb": float(clf.coef_[0][1]),
            "n_train_rows": int(len(tr)),
            "n_train_races": int(tr["race_id"].nunique()),
            "train_seasons": sorted(int(s) for s in tr["season"].unique()),
            "train_folds": hist[fold],
            "p_range": [float(d["probability"].min()),
                        float(d["probability"].max())],
        }
        met = metrics_for(d, "probability",
                          d["race_id"].astype(str).tolist(), plain)
        met["delta_vs_logistic"] = met["race_macro_ll"] - \
            (base_rep[fold])
        stacker_res[fold] = met
        ll_b = race_macro_ll(frames[fold], "probability_log")
        ll_e = race_macro_ll(d, "probability")
        stacker_boot[fold] = V3C.paired_bootstrap(
            ll_b["per_race"], ll_e["per_race"], seed=42, replicates=2000,
            ci_level=0.95)
        out = PRED_OUT / f"stacker__{fold}.parquet"
        d[["state_id", "race_id", "season", "driver_id", "target",
           "fold", "stage", "probability"]].to_parquet(out, index=False)
        pred_hashes[f"stacker__{fold}"] = hashlib.sha256(
            out.read_bytes()).hexdigest()
        stamp(f"stacker_{fold}")
    write("stacker_coefficients.json", coefs)
    write("stacker_results.json", {"per_fold": stacker_res,
                                   "bootstrap": stacker_boot,
                                   "descriptive_status":
                                   "DESCRIPTIVE_ONLY_NOT_SELECTED"})
    write("prediction_hashes.json", pred_hashes)
    # -- probability quality --------------------------------------------------
    pq = {}
    for w in GRID:
        key = f"w_{w:.1f}"
        pq[key] = {
            "finite": True, "bounded_01": True, "raw": True,
            "field_normalized": False,
            "brier_pooled": blend_results[key]["pooled"]["brier"],
            "ece_pooled": blend_results[key]["pooled"]["ece"],
            "worst_race_ll_pooled": blend_results[key]["pooled"][
                "worst_race_ll"],
            "max_probability_pooled": blend_results[key]["pooled"][
                "max_probability"],
        }
    pq["stacker"] = {
        "finite": True, "bounded_01": True, "raw": True,
        "field_normalized": False,
        "per_fold": {f: {
            "brier": stacker_res[f]["brier"], "ece": stacker_res[f]["ece"],
            "worst_race_ll": stacker_res[f]["worst_race_ll"],
            "max_probability": stacker_res[f]["max_probability"]}
            for f in FOLDS},
    }
    write("probability_quality.json", pq)
    # -- firewall + compute ---------------------------------------------------
    write("firewall_audit.json", {
        "2025_CONTACT": "NONE",
        "loader": "6-path OOF allowlist; forbidden paths assert",
        "seasons_seen": sorted(int(s) for s in full["season"].unique()),
        "ensemble_prediction_paths": sorted(str(p) for p in
                                            PRED_OUT.glob("*.parquet")),
    })
    stamp("done")
    write("compute_profile.json", {
        "timings_s": TIMINGS,
        "total_s": round(time.time() - T0, 3),
        "budget_s": 1800,
        "base_models_retrained": False,
    })
    print("V3.4B experiments complete.")


if __name__ == "__main__":
    main()
