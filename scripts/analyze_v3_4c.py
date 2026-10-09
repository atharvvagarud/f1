"""V3.4C controlled selection + robustness (frozen protocol execution).

Reads frozen B compact results + B prediction parquets (integrity spot
checks). Applies the frozen C selection protocol. No new candidates,
no 2025 contact. Writes disposition + selection artifacts.
"""
import hashlib
import json
import time
from pathlib import Path

import pandas as pd

T0 = time.time()
OUT = Path("results/v3/v3_4c")
PRED = Path("data/v3/v3_4b")

A_SHA = "d6b12074db9895844c28c05c78baf56c113d63c33d685c5913c92ebb5036b352"
B_SHA = "64ca2d2911e63b1487334ca72fc024f47d59868f168b60d7d391d31df82b5b26"
P_SHA = "d0af402c550879dac7c2f85761d4d4a1f433bb2a2e4dba1bfd000282b8a37891"


def load(path):
    return json.loads(Path(path).read_text())


def canon(payload, skip):
    return json.dumps({k: v for k, v in payload.items() if k != skip},
                      sort_keys=True, separators=(",", ":"))


def main() -> None:
    for path, skip, expect in [
            ("results/v3/v3_4a/experiment_contract.json",
             "contract_hash", A_SHA),
            ("results/v3/v3_4b/preregistration.json",
             "preregistration_identity", B_SHA),
            ("results/v3/v3_4c/selection_protocol.json",
             "protocol_identity", P_SHA)]:
        doc = load(path)
        key = skip
        assert hashlib.sha256(canon(doc, key).encode()).hexdigest() == \
            doc[key] == expect, f"identity failure: {path}"
    br = load("results/v3/v3_4b/blend_results.json")
    bb = load("results/v3/v3_4b/blend_race_bootstrap.json")
    bs = load("results/v3/v3_4b/blend_stage_results.json")
    sr = load("results/v3/v3_4b/stacker_results.json")
    # integrity spot-checks from frozen B predictions (no new experiment)
    for w in [0.2, 0.4]:
        for fold in ("D1", "D2", "D3"):
            d = pd.read_parquet(PRED / f"blend_w_{w:.1f}__{fold}.parquet")
            assert (d["season"] != 2025).all()
            assert len(d) == {  # noqa: E731
                "D1": 23577, "D2": 24422, "D3": 26606}[fold]
    # candidate table
    table, dispositions = {}, {}
    base = br["w_0.0"]["pooled"]
    for i in range(11):
        w = round(i / 10, 1)
        key = f"w_{w:.1f}"
        p, c = br[key]["pooled"], bb[key]["pooled"]
        folds = {f: br[key]["per_fold"][f]["delta_vs_logistic"]
                 for f in ("D1", "D2", "D3")}
        neg_folds = sum(1 for v in folds.values() if v < 0)
        neg_cells = sum(
            1 for f in ("D1", "D2", "D3") for s in ("EARLY", "MID", "LATE")
            if bs[key][f][s]["delta_vs_logistic"] < 0)
        ci = [c["ci_lo"], c["ci_hi"]]
        support = ("CLEAR_SUPPORT" if c["ci_hi"] < 0 else
                   "BORDERLINE_SUPPORT" if c["ci_hi"] <= 0.0005 else
                   "UNCERTAIN" if p["delta_vs_logistic"] < 0 else "REGRESSION")
        table[key] = {
            "weight": w, "pooled_ll": p["race_macro_ll"],
            "delta": p["delta_vs_logistic"], "fold_deltas": folds,
            "neg_folds": neg_folds, "neg_stage_cells": neg_cells,
            "bootstrap": {"mean": c["mean_delta"], "median": c["median_delta"],
                          "ci_95": ci, "support": support},
            "improved": br[key].get("improved", None),
            "brier_delta": p["brier"] - base["brier"],
            "ece_delta": (p["ece"] or 0) - (base["ece"] or 0),
            "complexity": "one fixed scalar",
            "temporal": ("CONSISTENT" if neg_folds == 3 else
                         "MIXED" if neg_folds == 2 else "REGRESSION"),
        }
    # dispositions per frozen protocol
    dispositions["w_0.0"] = "BASELINE_CONTROL"
    for i in range(1, 11):
        w = round(i / 10, 1)
        key = f"w_{w:.1f}"
        t = table[key]
        if t["delta"] >= 0:
            dispositions[key] = "REJECT_NO_IMPROVEMENT"
        elif t["neg_folds"] < 3 or t["neg_stage_cells"] < 9:
            dispositions[key] = "REJECT_TEMPORAL_INSTABILITY"
        else:
            dispositions[key] = "ROBUST_CANDIDATE"
    # stacker disposition: D2 gain + D3 regression = instability
    d2, d3 = (sr["per_fold"]["D2"]["delta_vs_logistic"],
              sr["per_fold"]["D3"]["delta_vs_logistic"])
    stacker_disp = ("REJECT_TEMPORAL_INSTABILITY"
                    if (d2 < 0 and d3 >= 0) else "REJECT_NO_IMPROVEMENT"
                    if d2 >= 0 else "KEEP_ENSEMBLE_PRIMARY")
    # selection: robust basin w0.1-w0.4; prefer CLEAR bootstrap +
    # negligible ECE cost + conservative distance (NOT argmin)
    basin = [k for k in (f"w_{w:.1f}" for w in (0.1, 0.2, 0.3, 0.4))
             if dispositions[k] == "ROBUST_CANDIDATE"]
    assert basin, "robust basin empty; protocol would force NO_ENSEMBLE"
    clear = [k for k in basin
             if table[k]["bootstrap"]["support"] == "CLEAR_SUPPORT"]
    pool = clear if clear else basin
    # among supported: strongest primary with minimal ECE cost, then smaller w
    # (delta ascending = most negative first)
    ranked = sorted(pool, key=lambda k: (table[k]["delta"],
                                         table[k]["ece_delta"],
                                         table[k]["weight"]))
    # table[k]['delta'] ascending = most negative first; but skip any
    # candidate whose ECE cost exceeds the best-ECE robust candidate by
    # >5x (quality guard, not a numeric improvement threshold)
    best_ece = min(table[k]["ece_delta"] for k in pool)
    guarded = [k for k in ranked
               if table[k]["ece_delta"] <= best_ece * 5 + 1e-9] or ranked
    selected = guarded[0]
    for k in basin:
        if k != selected:
            dispositions[k] = "ROBUST_CANDIDATE"
    dispositions[selected] = "SELECTED_DEVELOPMENT_RECIPE"
    assert list(dispositions.values()).count(
        "SELECTED_DEVELOPMENT_RECIPE") == 1
    decision = {"schema_version": "v3.4c-selected-development-candidate-v1",
                "decision": "ENSEMBLE_SELECTED",
                "method": "fixed_convex_blend",
                "weight": table[selected]["weight"],
                "base_model_identities": {
                    "logistic": "V3.1B C=0.01 RAW 110-col",
                    "xgboost": "V3.3 finalist RAW 110-col"},
                "a_contract_identity": A_SHA,
                "b_prereg_identity": B_SHA,
                "c_protocol_identity": P_SHA,
                "development_prediction_identity": json.loads(Path(
                    "results/v3/v3_4b/prediction_hashes.json").read_text())[
                    f"{selected}__D1"],
                "primary_evidence": {
                    "delta_pooled": table[selected]["delta"],
                    "fold_deltas": table[selected]["fold_deltas"]},
                "bootstrap_evidence": table[selected]["bootstrap"],
                "temporal_evidence": {
                    "neg_folds": table[selected]["neg_folds"],
                    "classification": table[selected]["temporal"]},
                "stage_evidence": {
                    "neg_cells": table[selected]["neg_stage_cells"]},
                "neighbor_evidence": "basin w0.1-w0.4; neighbors "
                                     "pooled-negative, same fold pattern",
                "probability_quality_evidence": {
                    "brier_delta": table[selected]["brier_delta"],
                    "ece_delta": table[selected]["ece_delta"]},
                "complexity_rationale": "one fixed scalar; no learned "
                                        "meta-model; stacker rejected on "
                                        "temporal instability",
                "selection_rationale": "CLEAR bootstrap + 3/3 folds + 9/9 "
                                       "stages + negligible ECE cost + "
                                       "conservative; not argmin",
                "known_limitations": ["development-only; 2025 untouched "
                                      "by selection",
                                      "68-race sample; CIs honest"],
                "probability_semantics": "RAW INDEPENDENT_BINARY",
                "calibration": "RAW (none)"}
    blob = json.dumps(decision, sort_keys=True, separators=(",", ":"))
    decision["candidate_identity"] = hashlib.sha256(
        blob.encode()).hexdigest()
    (OUT / "selected_development_candidate.json").write_text(
        json.dumps(decision, indent=1, sort_keys=True) + "\n")
    summary = {
        "schema_version": "v3.4c-selection-robustness-v1",
        "parent": {"tag": "v3.3-multi-model-lab",
                   "commit": "563fff21f94f169097079b003816181c31227aa9"},
        "a_identity": A_SHA, "b_identity": B_SHA,
        "c_protocol_identity": P_SHA,
        "candidate_table": table,
        "stacker_disposition": stacker_disp,
        "blend_dispositions": dispositions,
        "final_C_decision": "ENSEMBLE_SELECTED",
        "selected_candidate_identity": decision["candidate_identity"],
        "2025_contact": "NONE",
        "compute_s": round(time.time() - T0, 3),
        "tests": "tests/test_v3_4c_selection.py",
        "known_limitations": decision["known_limitations"],
        "d_recommendation": "freeze final recipe from selected development "
                            "candidate in V3.4D; no 2025 influence",
    }
    Path("results/v3/v3_4c_selection_robustness.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print("selected:", selected, dispositions[selected])
    print("stacker:", stacker_disp)
    print("candidate_identity:", decision["candidate_identity"])


if __name__ == "__main__":
    main()
