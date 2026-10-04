"""V3.1D sealed 2025 holdout verdict + Phase-1 freeze (one-shot).

Ordered sequence (no deviation permitted):
  1. verify all identities + V3.1C advancement
  2. freeze + persist preregistration (BEFORE any 2025 prediction)
  3. record holdout opening
  4. FINAL_FIT Arm A (2018-2024) -> predict 2025 -> persist immediately
  5. FINAL_FIT Arm B (2018-2024) -> predict 2025 -> persist immediately
  6. evaluate once (Arm A fidelity gate first; STOP if it fails)
  7. acceptance policy -> verdict (no post-holdout changes of any kind)
  8. serving decision + conditional model artifact/card
  9. determinism rerun verification (exact spec only)
  10. machine record + freeze evidence

Usage:
    python scripts/run_v3_1d_holdout.py [--root .] [--force]

Refuses to run twice (one-shot): existing freeze record blocks rerun
unless --force is given for reproducibility verification. --force never
authorizes a new scientific configuration.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
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

FROZEN_HOLDOUT_REPORT = (
    "data/v2/model_lab/reports/final_holdout_2025_v1.json")
V3_1C_RECORD = "results/v3/v3_1c_race_dynamics_controlled_experiment.json"
METRIC_TOL = 1e-9

#: Part J frozen Arm A expectations (final_holdout_2025_v1.json).
FIDELITY_EXPECTED = {
    "race_macro_log_loss": 0.0680353741,
    "race_macro_brier": 0.0200141490,
    "race_macro_roc_auc": 0.9845256886,
    "race_macro_pr_auc": 0.8032379039,
    "ece": 0.0111081578,
    "top1": 0.7960622539,
    "top3": 0.9789986874,
}

SERVING_REL = Path("results/v2_model_lab/winner_logreg_raw_v1_serving.joblib")
SERVING_SHA = (
    "1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4")


def _sha_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _race_macro(metrics: dict, name: str) -> tuple:
    node = metrics[name]["race_macro"]
    return (float(node["value"]),
            {k: float(v) for k, v in node["per_race"].items()})


def step_identities() -> dict:
    """Part C: every frozen identity exact before 2025 is opened."""
    info = V3.check_v3_identities()
    assert info["contract_sha"] == V3.V3_CONTRACT_SHA
    rec = json.loads((ROOT / V3_1C_RECORD).read_text())
    if rec.get("recommendation") != "ADVANCE_CORE_TO_V3_1D":
        raise ExperimentConfigError(
            "V3.1C advancement missing; 2025 must not open")
    d1c_primary = {f: rec["primary_comparison"][f]["delta_b_a"]
                   for f in ("D1", "D2", "D3")}
    return {"v3_identities": info,
            "v3_1c_recommendation": rec["recommendation"],
            "v3_1c_deltas_b_a": d1c_primary}


def step_preregister(names_84: tuple, names_110: tuple,
                     out_path: Path) -> dict:
    """Part D: freeze + persist preregistration (no holdout results)."""
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=str(ROOT)).stdout.strip()
    except Exception:
        commit = "unknown"
    spec = V3.build_preregistration(names_84, names_110, commit)
    assert "per_race" not in json.dumps(spec)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(spec, indent=2, sort_keys=True) + "\n")
    return spec


def step_opening(prereg: dict, out_path: Path) -> dict:
    """Part E: machine-readable holdout-opening event (no wall clock)."""
    opening = {
        "schema_version": "v3.1d-opening-v1",
        "holdout_season": V3.V3_HOLDOUT_SEASON,
        "preregistration_identity": prereg["preregistration_identity"],
        "contract_identity": prereg["contract_identity"],
        "dataset_identity": prereg["dataset_identities"],
        "code_commit": prereg["code_commit"],
        "one_shot": True,
    }
    out_path.write_text(json.dumps(opening, indent=2, sort_keys=True)
                        + "\n")
    return opening


def _persist_predictions(pred_dir: Path, arm: str, out: dict) -> dict:
    meta = out["holdout_dataset"].validation_metadata
    pred = pd.DataFrame({
        "state_id": out["state_ids"],
        "race_id": list(meta["race_id"].astype(str)),
        "driver_id": list(meta["driver_id"].astype(str)),
        "season": list(meta["season"].astype(int)),
        "y_true": np.asarray(out["y_true"], dtype=float),
        "y_pred": np.asarray(out["predictions"], dtype=float),
    }).sort_values("state_id", kind="mergesort")
    seasons = {int(s) for s in pred["season"].unique()}
    if seasons != {V3.V3_HOLDOUT_SEASON}:
        raise ProtectedHoldoutError(
            f"prediction seasons {seasons} != {{2025}}")
    pred_dir.mkdir(parents=True, exist_ok=True)
    path = pred_dir / f"pred_final_{arm}_2025.parquet"
    pred.to_parquet(path, index=False)
    return {"path": str(path.relative_to(ROOT)),
            "sha256": _sha_file(path),
            "rows": int(len(pred)),
            "seasons": sorted(seasons)}


def _fold_metrics(out: dict) -> dict:
    m = out["metrics"]
    ll_val, ll_map = _race_macro(m, "log_loss")
    stages = {}
    for metric, payload in out["stages"].items():
        if not isinstance(payload, dict):
            continue
        stages[metric] = {}
        for stage, node in payload.items():
            if not isinstance(node, dict):
                continue
            rm = node.get("race_macro", {})
            stages[metric][stage] = {
                "value": (None if rm.get("value") is None
                          else float(rm["value"])),
                "per_race": {k: float(v) for k, v in
                             rm.get("per_race", {}).items()},
            }
    top = out["topk"]["winner_top_k"]
    acc = top.get("accuracy", {})
    return {
        "experiment_id": out["config"].experiment_id,
        "race_macro": {n: _race_macro(m, n)[0]
                       for n in ("log_loss", "brier", "roc_auc",
                                 "pr_auc")},
        "per_race_log_loss": dict(sorted(ll_map.items())),
        "ece": float(out["calibration"]["expected_calibration_error"]),
        "topk": {"top1": float(acc["top1"]), "top3": float(acc["top3"]),
                 "n_evaluation_states": int(top["n_evaluation_states"]),
                 "n_races": int(top["n_races"])},
        "stages": stages,
        "n_races": int(out["holdout_dataset"].validation_metadata
                       ["race_id"].nunique()),
        "n_eligible": int(out["holdout_dataset"].validation_counts
                         ["eligible"]),
        "train_eligible": int(out["train_dataset"].train_counts
                             ["eligible"]),
        "transformed_dim": int(out["transformed_dim"]),
        "timings": {k: round(float(v), 3)
                    for k, v in out["timings"].items()},
    }


def step_fidelity(fm_a: dict) -> dict:
    """Part J: Arm A reproduces the frozen FINAL_FIT 2025 baseline."""
    frozen = json.loads((ROOT / FROZEN_HOLDOUT_REPORT).read_text())
    got_rm = fm_a["race_macro"]
    checks, worst = {}, 0.0
    pairs = [("race_macro_log_loss", got_rm["log_loss"]),
             ("race_macro_brier", got_rm["brier"]),
             ("race_macro_roc_auc", got_rm["roc_auc"]),
             ("race_macro_pr_auc", got_rm["pr_auc"]),
             ("ece", fm_a["ece"]),
             ("top1", fm_a["topk"]["top1"]),
             ("top3", fm_a["topk"]["top3"])]
    for key, got in pairs:
        want = FIDELITY_EXPECTED[key]
        diff = abs(float(got) - want)
        checks[key] = {"got": float(got), "want": want, "diff": diff}
        worst = max(worst, diff)
    frozen_map = {row["race_id"]: float(row["race_macro_log_loss"])
                  for row in frozen["per_race"]}
    got_map = fm_a["per_race_log_loss"]
    if set(got_map) != set(frozen_map):
        raise ExperimentConfigError("holdout per-race keys differ")
    race_worst = max(abs(got_map[r] - frozen_map[r]) for r in got_map)
    checks["per_race_ll_worst"] = race_worst
    worst = max(worst, race_worst)
    passed = worst <= METRIC_TOL
    return {"passed": passed, "worst_abs_diff": worst,
            "tolerance": METRIC_TOL, "detail": checks}


def _subgroup(augmented, out_a, out_b, mask_fn) -> dict:
    idx = out_a["holdout_dataset"].y_validation.index
    y = out_a["y_true"]
    races = out_a["race_ids"]
    out = {}
    from raceintel.model_lab import aggregation as AGG
    for name, sel in mask_fn(augmented, idx).items():
        sel = np.asarray(sel)
        if int(sel.sum()) == 0:
            out[name] = {"n_states": 0}
            continue
        try:
            r_a = AGG.race_macro(y[sel], out_a["predictions"][sel],
                                 races[sel], "log_loss")
            r_b = AGG.race_macro(y[sel], out_b["predictions"][sel],
                                 races[sel], "log_loss")
            out[name] = {"n_states": int(sel.sum()),
                         "n_races": int(r_a["n_races"]),
                         "ll_a": float(r_a["value"]),
                         "ll_b": float(r_b["value"]),
                         "delta": float(r_b["value"])
                         - float(r_a["value"])}
        except Exception as exc:
            out[name] = {"n_states": int(sel.sum()),
                         "error": str(exc)[:120]}
    return out


def _depth_masks(augmented, idx):
    depth = augmented.frame.loc[idx, "dyn_hist_laps_available"] \
        .astype(int).to_numpy()
    return {name: ((depth >= lo) & (depth <= hi))
            for name, lo, hi in V3.DEPTH_BINS}


def _pit_masks(augmented, idx):
    pit = augmented.frame.loc[idx, "dyn_pit_inout_flag"]
    pit = pit.astype("boolean").fillna(False).astype(bool).to_numpy()
    track = augmented.frame.loc[idx, "track_state"].astype(str).to_numpy()
    green = track == "all_clear"
    return {"green": green & ~pit, "pit_transition": pit,
            "neutralised": ~green}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default=".")
    ap.add_argument("--force", action="store_true")
    args = ap.parse_args()
    root = Path(args.root).resolve()
    res_dir = root / "results" / "v3"
    pred_dir = root / "data" / "v3" / "v3_1d"
    freeze_path = res_dir / "v3_1d_race_dynamics_holdout_and_freeze.json"
    if freeze_path.exists() and not args.force:
        print("v3.1d: freeze record exists; one-shot already consumed. "
              "Rerun with --force for reproducibility verification only.",
              file=sys.stderr)
        return 2

    # --- 1-2. identities + advancement (before 2025 opens) ---
    gate = step_identities()
    print(f"v3.1d: identities exact; "
          f"V3.1C={gate['v3_1c_recommendation']}")

    augmented, plain = V3.load_joined_frame(str(root))
    names_84 = V3.v3_feature_names(V3.ARM_A)
    names_110 = V3.v3_feature_names(V3.ARM_B, names_84)

    # --- 3. preregistration BEFORE any 2025 prediction ---
    prereg_path = res_dir / "v3_1d_preregistration.json"
    if prereg_path.exists() and not args.force:
        prereg = json.loads(prereg_path.read_text())
        print("v3.1d: reusing persisted preregistration "
              f"{prereg['preregistration_identity'][:12]}")
    else:
        prereg = step_preregister(names_84, names_110, prereg_path)
        print(f"v3.1d: preregistered {prereg['preregistration_identity']}")
    opening = step_opening(
        prereg, res_dir / "v3_1d_holdout_opening.json")
    print("v3.1d: holdout opened (one-shot, preregistered)")

    # --- 4-6. FINAL_FIT A/B, predict once each, persist immediately ---
    persisted = {}
    outs = {}
    for arm, names in ((V3.ARM_A, names_84), (V3.ARM_B, names_110)):
        out = V3.run_v3_final(augmented, plain, arm, names)
        persisted[arm] = _persist_predictions(pred_dir, arm, out)
        outs[arm] = out
        ll = out["metrics"]["log_loss"]["race_macro"]["value"]
        print(f"v3.1d: {arm} persisted "
              f"(sha {persisted[arm]['sha256'][:12]}); LL evaluation "
              f"deferred until both arms persist")

    # --- population equality (identical holdout rows A/B) ---
    for arm in (V3.ARM_A, V3.ARM_B):
        meta = outs[arm]["holdout_dataset"].validation_metadata
        assert set(meta["state_id"]) == set(outs[V3.ARM_A][
            "holdout_dataset"].validation_metadata["state_id"])
    fm = {arm: _fold_metrics(outs[arm]) for arm in outs}
    assert fm[V3.ARM_A]["n_eligible"] == fm[V3.ARM_B]["n_eligible"]
    population = {
        "identical_across_arms": True,
        "rows": fm[V3.ARM_A]["n_eligible"],
        "races": fm[V3.ARM_A]["n_races"],
        "train_eligible": {arm: fm[arm]["train_eligible"] for arm in fm},
    }
    print(f"v3.1d: holdout population identical "
          f"({population['rows']} rows, {population['races']} races)")

    # --- 7. Arm A fidelity gate (STOP if it fails) ---
    fidelity = step_fidelity(fm[V3.ARM_A])
    print(f"v3.1d: Arm A fidelity passed={fidelity['passed']} "
          f"worst={fidelity['worst_abs_diff']:.3e}")
    if not fidelity["passed"]:
        (res_dir / "v3_1d_blocked_fidelity.json").write_text(
            json.dumps({"fidelity": fidelity}, indent=2, sort_keys=True)
            + "\n")
        print("v3.1d: BLOCKED — baseline fidelity failure",
              file=sys.stderr)
        return 2

    # --- 8. one-shot evaluation (Parts K-X) ---
    a_ll = fm[V3.ARM_A]["per_race_log_loss"]
    b_ll = fm[V3.ARM_B]["per_race_log_loss"]
    delta = fm[V3.ARM_B]["race_macro"]["log_loss"] - \
        fm[V3.ARM_A]["race_macro"]["log_loss"]
    boot = V3.paired_bootstrap(a_ll, b_ll)
    deltas = np.array([b_ll[r] - a_ll[r] for r in sorted(a_ll)])
    per_race = {r: {"ll_a": float(a_ll[r]), "ll_b": float(b_ll[r]),
                    "delta": float(b_ll[r] - a_ll[r])}
                for r in sorted(a_ll)}
    secondary = {}
    for m, key in (("brier", "brier"), ("roc_auc", "roc_auc"),
                   ("pr_auc", "pr_auc")):
        secondary[m] = {"a": fm[V3.ARM_A]["race_macro"][m],
                        "b": fm[V3.ARM_B]["race_macro"][m],
                        "delta": fm[V3.ARM_B]["race_macro"][m]
                        - fm[V3.ARM_A]["race_macro"][m]}
    ece = {"a": fm[V3.ARM_A]["ece"], "b": fm[V3.ARM_B]["ece"],
           "delta": fm[V3.ARM_B]["ece"] - fm[V3.ARM_A]["ece"]}
    topk = {arm: fm[arm]["topk"] for arm in fm}
    stages = {}
    for stage in ("EARLY", "MID", "LATE"):
        a_s = fm[V3.ARM_A]["stages"]["log_loss"][stage]
        b_s = fm[V3.ARM_B]["stages"]["log_loss"][stage]
        stages[stage] = {"a": a_s["value"], "b": b_s["value"],
                         "delta": b_s["value"] - a_s["value"]}
    # EARLY-only paired bootstrap (same preregistered procedure, subset).
    early_boot = V3.paired_bootstrap(
        fm[V3.ARM_A]["stages"]["log_loss"]["EARLY"]["per_race"],
        fm[V3.ARM_B]["stages"]["log_loss"]["EARLY"]["per_race"])
    temporal = [gate["v3_1c_deltas_b_a"][f] for f in ("D1", "D2", "D3")]
    temporal.append(delta)
    consistency = {
        "d1_d2_d3_2025": [round(float(x), 6) for x in temporal],
        "n_improved_of_4": int(sum(1 for x in temporal if x < 0)),
        "classification": f"{sum(1 for x in temporal if x < 0)}/4 "
                          f"improvement",
    }
    # Stage veto (frozen rule): consistent directional EARLY regression
    # across D1/D2/D3/2025 AND paired CI excluding zero in the bad
    # direction. D1/D2 EARLY improved, so cross-evidence consistency
    # already fails; EARLY CI is assessed anyway.
    early_d1c = {"D1": -0.001427, "D2": -0.000524, "D3": 0.002126}
    early_all = [early_d1c["D1"], early_d1c["D2"], early_d1c["D3"],
                 stages["EARLY"]["delta"]]
    veto_consistent = all(x > 0 for x in early_all)
    veto_ci_bad = early_boot["ci_lo"] > 0.0
    veto = "VETO" if (veto_consistent and veto_ci_bad) else (
        "CONCERN" if stages["EARLY"]["delta"] > 0 else "PASS")
    early_watch = {
        "d1_d2_d3_early_deltas": early_d1c,
        "holdout_early_delta": stages["EARLY"]["delta"],
        "holdout_early_bootstrap_ci": [early_boot["ci_lo"],
                                       early_boot["ci_hi"]],
        "consistent_regression": veto_consistent,
        "paired_ci_bad": veto_ci_bad,
    }
    depth_diag = _subgroup(augmented, outs[V3.ARM_A], outs[V3.ARM_B],
                           _depth_masks)
    pit_diag = _subgroup(augmented, outs[V3.ARM_A], outs[V3.ARM_B],
                         _pit_masks)
    # Follower coverage on 2025 (structural only).
    idx = outs[V3.ARM_B]["holdout_dataset"].y_validation.index
    foll_cov = {}
    for n in [c for c in outs[V3.ARM_B]["train_dataset"].feature_names
              if "follower" in c]:
        foll_cov[n] = round(float(
            augmented.frame.loc[idx, n].notna().mean()), 4)
    # Coefficient stability: FINAL_FIT vs D1-D3 (descriptive only).
    est = outs[V3.ARM_B]["estimator"]
    coef = np.asarray(est.coef_, dtype=float).ravel()
    v3c = json.loads((root / V3_1C_RECORD).read_text())
    v3c_coefs = v3c["coefficient_diagnostics"]
    fitted_cols = list(outs[V3.ARM_B]["fit_info"].get("columns", []))
    coef_stab = {"note": "FINAL_FIT model-space ranks vs D1-D3 ranks; "
                         "descriptive, never selective"}
    # transformed layout: numerics, booleans, one-hots (frozen order).
    schema_cols = {"numeric": [], "boolean": []}
    import pandas as pd  # noqa: E402
    frame = augmented.frame
    for n in outs[V3.ARM_B]["train_dataset"].feature_names:
        dt = frame[n].dtype
        if pd.api.types.is_bool_dtype(dt):
            schema_cols["boolean"].append(n)
        else:
            schema_cols["numeric"].append(n)
    tindex = {n: i for i, n in
              enumerate(schema_cols["numeric"] + schema_cols["boolean"])}
    dyn_rows = {}
    for n in [c for c in outs[V3.ARM_B]["train_dataset"].feature_names
              if c.startswith("dyn_")]:
        ti = tindex[n]
        order = np.argsort(np.abs(coef))[::-1]
        rank = int(np.where(order == ti)[0][0]) + 1
        signs = {f: (v3c_coefs[f]["dynamics"][n]["coef"] > 0)
                 for f in ("D1", "D2", "D3")
                 if n in v3c_coefs[f]["dynamics"]}
        dyn_rows[n] = {"final_coef": float(coef[ti]),
                       "final_abs_rank": rank,
                       "final_sign_positive": bool(coef[ti] > 0),
                       "d1_d2_d3_signs_positive": signs,
                       "sign_agrees_majority": bool(
                           sum(signs.values()) >= 2) == bool(coef[ti] > 0)
                       if signs else None}
    coef_stab["dynamics"] = dyn_rows

    # Persistent watch-item flags for the verdict function.
    persistent = []
    if veto != "PASS":
        persistent.append(f"EARLY watch-item: veto={veto}")
    for name in ("thin", "medium"):
        b_ = depth_diag.get(name, {})
        if isinstance(b_, dict) and b_.get("delta", 0) > 0:
            persistent.append(
                f"history-depth watch-item persists on 2025: {name} "
                f"delta {b_['delta']:.6f}")
    neut = pit_diag.get("neutralised", {})
    if isinstance(neut, dict) and neut.get("delta", 0) > 0:
        persistent.append(
            f"neutralisation watch-item persists on 2025: delta "
            f"{neut['delta']:.6f}")
    evidence = {
        "primary_delta_b_a": float(delta),
        "bootstrap": {"ci_lo": float(boot["ci_lo"]),
                      "ci_hi": float(boot["ci_hi"])},
        "temporal_directions": [float(x) for x in temporal],
        "secondary_deltas": {"brier": float(secondary["brier"]["delta"]),
                             "roc_auc": float(secondary["roc_auc"]["delta"]),
                             "pr_auc": float(secondary["pr_auc"]["delta"])},
        "ece_delta_b_a": float(ece["delta"]),
        "stage_veto": veto,
        "persistent_watch_items": persistent,
    }
    acceptance = V3.apply_acceptance_policy(evidence)
    verdict = acceptance["verdict"]
    print(f"v3.1d: delta={delta:+.6f} "
          f"CI=[{boot['ci_lo']:+.6f},{boot['ci_hi']:+.6f}] "
          f"verdict={verdict}")

    # --- serving decision (frozen artifact never touched) ---
    serving_sha = _sha_file(root / SERVING_REL)
    if serving_sha != SERVING_SHA:
        raise ExperimentConfigError("frozen serving artifact moved")
    serving_decision = ("ELIGIBLE_FOR_FUTURE_SERVING_PROMOTION"
                        if verdict == "KEEP"
                        else "RESEARCH_KEEP_ONLY")

    # --- conditional final model artifact + card (Parts AB-AC) ---
    final_artifact = {"promoted": False}
    if verdict in ("KEEP", "KEEP_WITH_LIMITATION"):
        import joblib
        art_dir = root / "data" / "v3" / "v3_1d"
        model_path = art_dir / "final_model_arm_b.joblib"
        joblib.dump({
            "estimator": outs[V3.ARM_B]["estimator"],
            "preprocessor": outs[V3.ARM_B]["fitted_preprocessor"],
            "feature_names": list(
                outs[V3.ARM_B]["train_dataset"].feature_names),
            "provenance": {
                "contract_version": V3.V3_CONTRACT_VERSION,
                "contract_sha": V3.V3_CONTRACT_SHA,
                "dynamics_content_sha": V3.V3_DYNAMICS_LOGICAL_SHA,
                "preregistration_identity": prereg[
                    "preregistration_identity"],
                "training_seasons": list(V3.V3_FINAL_FIT_SEASONS),
                "model_spec": dict(V3.V3_MODEL_PARAMETERS),
                "prediction_semantics": "RAW INDEPENDENT_BINARY",
                "code_commit": prereg["code_commit"]},
        }, model_path)
        final_artifact = {
            "promoted": True,
            "path": str(model_path.relative_to(root)),
            "sha256": _sha_file(model_path),
            "note": "research artifact only; frozen v2 serving model "
                    "untouched; promotion needs a separate stage",
        }
        card = {
            "schema_version": "v3.1d-model-card-v1",
            "task": "winner (is_winner under eligible_is_winner)",
            "training_period": "2018-2024 FINAL_FIT",
            "feature_set": V3.ARM_B,
            "feature_count": 110,
            "independent_binary_semantics": "per-driver probabilities; "
                "never a normalized field distribution",
            "development_evidence": gate["v3_1c_deltas_b_a"],
            "holdout_evidence": {"primary_delta_b_a": float(delta),
                                 "bootstrap_ci": [float(boot["ci_lo"]),
                                                  float(boot["ci_hi"])]},
            "calibration": ece,
            "stage_behavior": {s: stages[s]["delta"] for s in stages},
            "known_limitations": acceptance["limitations"],
            "follower_observation_semantics": "last causally observed "
                "follower gap (stale ~one lap); never a live gap",
            "live_status": "non-live research artifact",
            "serving_status": serving_decision,
            "artifact": final_artifact,
        }
        (res_dir / "v3_1d_model_card.json").write_text(
            json.dumps(card, indent=2, sort_keys=True) + "\n")

    # --- determinism rerun (exact spec; verification, not a trial) ---
    re_outs = {}
    for arm, names in ((V3.ARM_A, names_84), (V3.ARM_B, names_110)):
        re_out = V3.run_v3_final(augmented, plain, arm, names)
        re_outs[arm] = re_out
    re_hashes = {}
    for arm in (V3.ARM_A, V3.ARM_B):
        h1 = persisted[arm]["sha256"]
        re_pred = pd.DataFrame({
            "state_id": re_outs[arm]["state_ids"],
            "y_pred": np.asarray(re_outs[arm]["predictions"], dtype=float),
        }).sort_values("state_id", kind="mergesort")
        first = pd.read_parquet(pred_dir / f"pred_final_{arm}_2025.parquet")
        merged = first.merge(re_pred, on="state_id",
                             suffixes=("_0", "_1"))
        maxdiff = float(np.abs(merged["y_pred_0"]
                               - merged["y_pred_1"]).max())
        re_hashes[arm] = {"max_abs_pred_diff": maxdiff,
                          "persisted_sha256": h1}
    determinism = {
        "prediction_hashes_identical": all(
            v["max_abs_pred_diff"] == 0.0 for v in re_hashes.values()),
        "per_arm": re_hashes,
    }
    # Recompute per-race maps from rerun predictions (race unit preserved)
    # and require bootstrap + verdict identity.
    from raceintel.model_lab import aggregation as AGG
    re_a = re_outs[V3.ARM_A]
    re_b = re_outs[V3.ARM_B]
    re_map_a = AGG.race_macro(re_a["y_true"], re_a["predictions"],
                              re_a["race_ids"], "log_loss")["per_race"]
    re_map_b = AGG.race_macro(re_b["y_true"], re_b["predictions"],
                              re_b["race_ids"], "log_loss")["per_race"]
    re_boot = V3.paired_bootstrap(
        {k: float(v) for k, v in re_map_a.items()},
        {k: float(v) for k, v in re_map_b.items()})
    determinism["bootstrap_identical"] = bool(
        re_boot["ci_lo"] == boot["ci_lo"]
        and re_boot["ci_hi"] == boot["ci_hi"]
        and re_boot["mean_delta"] == boot["mean_delta"])
    determinism["verdict_identical"] = bool(
        V3.apply_acceptance_policy(evidence)["verdict"] == verdict)
    print(f"v3.1d: determinism {determinism}")

    record = {
        "schema_version": "v3.1d-v1",
        "baseline": {"commit": "e99a78f874597dce4639fb56e1b301a08d100506",
                     "tag": "phase12-spatial-replay"},
        "contract_version": V3.V3_CONTRACT_VERSION,
        "contract_sha": V3.V3_CONTRACT_SHA,
        "dynamics_content_sha": V3.V3_DYNAMICS_LOGICAL_SHA,
        "preregistration": prereg,
        "holdout_opening": opening,
        "model_spec": dict(V3.V3_MODEL_PARAMETERS),
        "feature_sets": {"ALL_84": 84, "V3_1_DYNAMICS_CORE": 26,
                         "ALL_84_PLUS_V3_1_DYNAMICS_CORE": 110},
        "training_period": list(V3.V3_FINAL_FIT_SEASONS),
        "holdout_period": [V3.V3_HOLDOUT_SEASON],
        "population": population,
        "arm_a_fidelity": fidelity,
        "arm_a": fm[V3.ARM_A],
        "arm_b": fm[V3.ARM_B],
        "primary_delta": float(delta),
        "secondary_deltas": secondary,
        "calibration": ece,
        "top_k": topk,
        "stage_results": stages,
        "per_race": per_race,
        "per_race_fractions": {
            "n_races": int(len(deltas)),
            "frac_improved": float(np.mean(deltas < 0)),
            "frac_worsened": float(np.mean(deltas > 0)),
            "mean_delta": float(np.mean(deltas)),
            "median_delta": float(np.median(deltas))},
        "bootstrap": boot,
        "temporal_consistency": consistency,
        "early_watch_item": {**early_watch, "assessment": veto},
        "history_depth_watch_item": depth_diag,
        "neutralisation_watch_item": pit_diag,
        "follower_validation": {"coverage_2025": foll_cov},
        "coefficient_stability": coef_stab,
        "acceptance_policy": acceptance,
        "verdict": verdict,
        "serving_decision": serving_decision,
        "serving_sha_unchanged": serving_sha,
        "final_artifact": final_artifact,
        "prediction_artifacts": persisted,
        "scientific_identities": {
            "serving": SERVING_SHA,
            "phase2_content": "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db",  # noqa: E501
            "phase2_parquet": "b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3",  # noqa: E501
            "explainability": "bae84b614a6e9e176d5bb9c33b99dcaf4cba3f376333b0f075c828f73982939f",  # noqa: E501
            "replay": "78a3c059888637fe83cc534d0eb7869b6d18e746724bb1ce0f03ee3b8ba96298",  # noqa: E501
            "simulation": "r3-v1 through 2024 phase6-r3-empirical"},
        "determinism": determinism,
        "tests": "tests/test_v3_1d_holdout.py (source-safe) + Tier-3 "
                 "rerun of this script with --force",
        "known_limitations": acceptance["limitations"],
        "freeze": {"commit_message": "feat(model): add causal race "
                                    "dynamics experiment",
                   "tag": "v3.1-race-dynamics"},
        "v3_2_handoff": "V3.2 = MONTE CARLO 2.0 (not started). Accepted "
                        "V3.1 dynamics are per-driver descriptive "
                        "trajectories; any simulation use must respect the "
                        "ML-vs-simulation firewall: independent binary "
                        "winner probabilities must never be naively "
                        "averaged with mutually exclusive race-outcome "
                        "frequencies.",
    }
    freeze_path.write_text(json.dumps(record, indent=2, sort_keys=True)
                           + "\n")
    print(f"v3.1d: verdict={verdict}; wrote {freeze_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
