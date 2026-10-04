"""V3.1C controlled temporal experiment (deterministic; D1-D3 only).

Runs the Arm A fidelity gate (M7 per-fold C values on ALL_84, compared
against stored outer result.json metric nodes incl. per-race maps) and
then Arms A/B/C at the frozen C=0.01, with the full V3.1A analysis
(race-macro primary, secondary, ECE, top-k, stages, paired race deltas,
B=2000 bootstrap, fold consistency, stage veto, diagnostics).

2025 is unreachable: folds resolve exclusively through development-only
resolvers (no holdout flag exists anywhere in this script). Never
trains, evaluates, or predicts on 2025.

Usage:
    python scripts/run_v3_1c_experiment.py [--root .] [--out-dir DIR]
        [--skip-fidelity] [--force]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from raceintel.model_lab import v3_dynamics_experiment as V3  # noqa: E402
from raceintel.model_lab.errors import (  # noqa: E402
    ExperimentConfigError,
    ProtectedHoldoutError,
)

#: M7 per-fold selected C values (frozen development reference).
FIDELITY_C = {"D1": 0.003, "D2": 0.01, "D3": 0.03}
M7_REPORT = ("data/v2/model_lab/reports/"
             "logreg_boundary_resolution_v1.json")
METRIC_TOL = 1e-9


def _race_macro_ll(metrics: dict) -> tuple:
    node = metrics["log_loss"]["race_macro"]
    return float(node["value"]), {k: float(v)
                                  for k, v in node["per_race"].items()}


def _metric_value(metrics: dict, name: str) -> float:
    return float(metrics[name]["race_macro"]["value"])


def fidelity_gate(augmented, plain, names_84) -> dict:
    """Reproduce M7 outer metric nodes (per-race maps incl.) within 1e-9."""
    report = json.loads((ROOT / M7_REPORT).read_text())
    detail = {}
    worst = 0.0
    for fold in V3.V3_FOLDS:
        stored_path = (ROOT / "data/v2/model_lab/experiments/protocol=v1"
                       / report["per_fold"][fold]["outer"]["dest"].split(
                           "protocol=v1/")[-1] / "result.json")
        stored = json.loads(stored_path.read_text())
        out = V3.run_v3_arm(augmented, plain, fold, V3.ARM_A, names_84,
                            model_c=FIDELITY_C[fold])
        checks = {}
        for metric in ("log_loss", "brier", "roc_auc", "pr_auc"):
            got = _metric_value(out["metrics"], metric)
            want = float(stored["metrics"][metric]["race_macro"]["value"])
            diff = abs(got - want)
            checks[metric] = {"got": got, "want": want, "diff": diff}
            worst = max(worst, diff)
        got_ll, got_map = _race_macro_ll(out["metrics"])
        want_map = {k: float(v) for k, v in
                    stored["metrics"]["log_loss"]["race_macro"]
                    ["per_race"].items()}
        if set(got_map) != set(want_map):
            raise ExperimentConfigError(
                f"{fold}: per-race map keys differ")
        race_worst = max(abs(got_map[r] - want_map[r]) for r in got_map)
        checks["per_race_ll_worst"] = race_worst
        worst = max(worst, race_worst)
        got_ece = float(out["calibration"]["expected_calibration_error"])
        want_ece = float(stored["calibration"]
                         ["expected_calibration_error"])
        checks["ece"] = {"got": got_ece, "want": want_ece,
                         "diff": abs(got_ece - want_ece)}
        worst = max(worst, abs(got_ece - want_ece))
        got_top = out["topk"]["winner_top_k"]
        want_top = stored["race_metrics"]["winner_top_k"]
        for tk in ("top1", "top3"):
            gk = got_top.get("accuracy", {}).get(tk)
            wk = want_top.get("accuracy", {}).get(tk)
            if gk is not None and wk is not None:
                diff = abs(float(gk) - float(wk))
                checks[f"topk_{tk}"] = diff
                worst = max(worst, diff)
        detail[fold] = checks
    passed = worst <= METRIC_TOL
    return {"passed": passed, "worst_abs_diff": worst,
            "tolerance": METRIC_TOL, "detail": detail}


def fold_metrics(out: dict) -> dict:
    """Compact deterministic fold summary for one arm/fold run."""
    m = out["metrics"]
    ll_val, ll_map = _race_macro_ll(m)
    stages = {metric: {stage: node.get("race_macro", {}).get("value")
                       for stage, node in payload.items()
                       if isinstance(node, dict)}
              for metric, payload in out["stages"].items()
              if isinstance(payload, dict)}
    top = out["topk"]["winner_top_k"]
    acc = top.get("accuracy", {}) if isinstance(
        top.get("accuracy"), dict) else {}
    topk = {"top1": float(acc["top1"]), "top3": float(acc["top3"]),
            "n_evaluation_states": int(top["n_evaluation_states"]),
            "n_races": int(top["n_races"])}
    return {
        "experiment_id": out["config"].experiment_id,
        "race_macro": {name: _metric_value(m, name)
                       for name in ("log_loss", "brier", "roc_auc",
                                    "pr_auc")},
        "per_race_log_loss": dict(sorted(ll_map.items())),
        "ece": float(out["calibration"]["expected_calibration_error"]),
        "topk": topk,
        "stages": stages,
        "n_races": int(out["dataset"].validation_metadata["race_id"]
                       .nunique()),
        "n_eligible": int(out["dataset"].validation_counts["eligible"]),
        "train_eligible": int(out["dataset"].train_counts["eligible"]),
        "transformed_dim": int(out["transformed_dim"]),
        "timings": {k: round(float(v), 3)
                    for k, v in out["timings"].items()},
    }


def diagnostics_b(augmented, out_b, out_a) -> dict:
    """Non-selective Arm B diagnostics (no refits, no selection)."""
    frame = augmented.frame
    diag: dict = {}
    # --- follower coverage by fold ---
    foll = [n for n in out_b["dataset"].feature_names
            if "follower" in n]
    foll_cov = {}
    idx = out_b["dataset"].y_validation.index
    for n in foll:
        col = augmented.frame.loc[idx, n]
        foll_cov[n] = round(float(col.notna().mean()), 4)
    diag["follower_coverage"] = foll_cov
    # --- missingness subgroups via predeclared depth bins ---
    depth = augmented.frame.loc[idx, "dyn_hist_laps_available"] \
        .astype(int).to_numpy()
    y = out_b["y_true"]
    p_b = out_b["predictions"]
    p_a = out_a["predictions"]
    races = out_b["race_ids"]
    from raceintel.model_lab import aggregation as AGG
    from raceintel.model_lab import metrics as METRICS
    bins_out = {}
    for name, lo, hi in V3.DEPTH_BINS:
        sel = (depth >= lo) & (depth <= hi)
        if int(sel.sum()) == 0:
            bins_out[name] = {"n_states": 0}
            continue
        r_b = AGG.race_macro(y[sel], p_b[sel], races[sel], "log_loss")
        r_a = AGG.race_macro(y[sel], p_a[sel], races[sel], "log_loss")
        bins_out[name] = {
            "n_states": int(sel.sum()),
            "n_races": int(r_b["n_races"]),
            "ll_a": r_b["value"] and float(
                AGG.race_macro(y[sel], p_a[sel], races[sel],
                               "log_loss")["value"]),
            "ll_b": float(r_b["value"]),
            "delta": float(r_b["value"]) - float(
                AGG.race_macro(y[sel], p_a[sel], races[sel],
                               "log_loss")["value"]),
        }
    diag["missingness_bins"] = bins_out
    # --- pit / neutralisation subgroups (factual flags only) ---
    pit = augmented.frame.loc[idx, "dyn_pit_inout_flag"]
    pit = pit.astype("boolean").fillna(False).astype(bool).to_numpy()
    track = augmented.frame.loc[idx, "track_state"].astype(str).to_numpy()
    green = track == "all_clear"
    subs = {}
    for name, sel in (("green", green & ~pit),
                      ("pit_transition", pit),
                      ("neutralised", ~green)):
        if int(sel.sum()) == 0:
            subs[name] = {"n_states": 0}
            continue
        try:
            r_b = AGG.race_macro(y[sel], p_b[sel], races[sel], "log_loss")
            r_a = AGG.race_macro(y[sel], p_a[sel], races[sel], "log_loss")
            subs[name] = {"n_states": int(sel.sum()),
                          "ll_a": float(r_a["value"]),
                          "ll_b": float(r_b["value"]),
                          "delta": float(r_b["value"])
                          - float(r_a["value"])}
        except Exception as exc:
            subs[name] = {"n_states": int(sel.sum()),
                          "error": str(exc)[:120]}
    diag["pit_neutralisation"] = subs
    return diag


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--out-dir", default=None)
    ap.add_argument("--pred-dir", default=None)
    ap.add_argument("--skip-fidelity", action="store_true")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()

    out_dir = Path(args.out_dir) if args.out_dir \
        else Path(args.root) / "results" / "v3" / "v3_1c"
    pred_dir = Path(args.pred_dir) if args.pred_dir \
        else Path(args.root) / "data" / "v3" / "v3_1c"
    summary_path = out_dir / "v3_1c_summary.json"
    if summary_path.exists() and not args.force:
        print("v3.1c: summary exists; rerun with --force.",
              file=sys.stderr)
        return 2

    V3.assert_no_holdout_request("D1")
    try:
        V3.assert_no_holdout_request("2025")
        print("v3.1c: FIREWALL FAILURE (2025 accepted)", file=sys.stderr)
        return 2
    except ProtectedHoldoutError:
        pass

    augmented, plain = V3.load_joined_frame(args.root)
    names_84 = V3.v3_feature_names(V3.ARM_A)
    names_core = V3.v3_feature_names(V3.ARM_C)
    names_110 = V3.v3_feature_names(V3.ARM_B, names_84)

    record: dict = {
        "schema_version": "v3.1c-v1",
        "contract_version": V3.V3_CONTRACT_VERSION,
        "contract_sha": V3.V3_CONTRACT_SHA,
        "dynamics_content_sha": V3.V3_DYNAMICS_LOGICAL_SHA,
        "model_spec": dict(V3.V3_MODEL_PARAMETERS),
        "holdout_policy": "2025 sealed; development folds D1-D3 only",
    }

    if not args.skip_fidelity:
        gate = fidelity_gate(augmented, plain, names_84)
        record["fidelity_gate"] = gate
        print(f"v3.1c: fidelity passed={gate['passed']} "
              f"worst={gate['worst_abs_diff']:.3e}")
        if not gate["passed"]:
            out_dir.mkdir(parents=True, exist_ok=True)
            summary_path.write_text(json.dumps(record, indent=2,
                                               sort_keys=True) + "\n")
            print("v3.1c: BLOCKED — baseline reproduction failure",
                  file=sys.stderr)
            return 2
    else:
        record["fidelity_gate"] = {"skipped": True}

    arms = {V3.ARM_A: names_84, V3.ARM_B: names_110, V3.ARM_C: names_core}
    results: dict = {}
    populations: dict = {}
    for arm, names in arms.items():
        for fold in V3.V3_FOLDS:
            out = V3.run_v3_arm(augmented, plain, fold, arm, names)
            key = f"{arm}__{fold}"
            results[key] = fold_metrics(out)
            populations[key] = {
                "state_ids_hash": hashlib.sha256(
                    "\n".join(out["state_ids"]).encode()).hexdigest(),
                "n_eligible": int(
                    out["dataset"].validation_counts["eligible"]),
                "n_races": int(out["dataset"].validation_metadata
                               ["race_id"].nunique()),
                "experiment_id": out["config"].experiment_id,
            }
            pred_dir.mkdir(parents=True, exist_ok=True)
            pred = pd.DataFrame({
                "state_id": out["state_ids"],
                "race_id": list(out["dataset"].validation_metadata
                                ["race_id"].astype(str)),
                "driver_id": list(out["dataset"].validation_metadata
                                  ["driver_id"].astype(str)),
                "season": list(out["dataset"].validation_metadata
                               ["season"].astype(int)),
                "y_true": out["y_true"].astype(float),
                "y_pred": np.asarray(out["predictions"], dtype=float),
            }).sort_values("state_id", kind="mergesort")
            pred_path = pred_dir / f"pred_{arm}__{fold}.parquet"
            pred.to_parquet(pred_path, index=False)
            print(f"v3.1c: {key} LL={results[key]['race_macro']['log_loss']:.6f} "
                  f"n={results[key]['n_eligible']}")
            if arm == V3.ARM_B and fold == V3.V3_FOLDS[0]:
                first_b = out
            if arm == V3.ARM_A and fold == V3.V3_FOLDS[0]:
                first_a = out
    record["arm_results"] = results
    record["populations"] = populations

    # --- population equality: identical eligible state sets A/B/C ---
    pop_ok = True
    for fold in V3.V3_FOLDS:
        hashes = {populations[f"{arm}__{fold}"]["state_ids_hash"]
                  for arm in arms}
        if len(hashes) != 1:
            pop_ok = False
    record["population_equality"] = {"identical_across_arms": pop_ok}
    if not pop_ok:
        print("v3.1c: BLOCKED — population mismatch", file=sys.stderr)
        return 2

    # --- primary comparison + bootstrap per fold ---
    comparison = {}
    for fold in V3.V3_FOLDS:
        a_ll = results[f"{V3.ARM_A}__{fold}"]["per_race_log_loss"]
        b_ll = results[f"{V3.ARM_B}__{fold}"]["per_race_log_loss"]
        boot = V3.paired_bootstrap(a_ll, b_ll)
        comparison[fold] = {
            "a_ll": results[f"{V3.ARM_A}__{fold}"]["race_macro"]
            ["log_loss"],
            "b_ll": results[f"{V3.ARM_B}__{fold}"]["race_macro"]
            ["log_loss"],
            "delta": results[f"{V3.ARM_B}__{fold}"]["race_macro"]
            ["log_loss"] - results[f"{V3.ARM_A}__{fold}"]["race_macro"]
            ["log_loss"],
            "bootstrap": boot,
        }
    record["primary_comparison"] = comparison
    record["diagnostics_b_d1"] = diagnostics_b(
        augmented, first_b, first_a)

    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path.write_text(json.dumps(record, indent=2, sort_keys=True)
                            + "\n")
    print(f"v3.1c: wrote {summary_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
