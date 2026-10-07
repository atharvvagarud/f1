"""V3.2E results analysis: aggregation, bootstrap, verdict, convergence.

Reads population/pilot/fold_results/checkpoint_scores/race_results.
Proposes the scientific verdict per the frozen decision logic (reviewed
by the operator before it becomes final). No rescoring, no tuning.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

OUT = ROOT / "results" / "v3" / "v3_2e"
ARMS = ("A_R3_BASELINE", "B_DRIVER_ANCHOR", "C_DRIVER_ANCHOR_PLUS_DYNAMICS",
        "D_CONDITIONED_VARIANCE", "E_AR1_RESIDUAL")
PRIMARY = "winner_logloss"
SECONDARIES = ("winner_brier", "podium_brier", "exp_mae", "rps")


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def _save(name: str, obj: dict) -> None:
    (OUT / name).write_text(
        json.dumps(obj, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def _mean(vals: list) -> float | None:
    vs = [v for v in vals if v is not None]
    return sum(vs) / len(vs) if vs else None


def main() -> None:
    prereg = _load("preregistration.json")
    pop = _load("population.json")
    pilot = _load("pilot.json")
    fold = _load("fold_results.json")
    cps = _load("checkpoint_scores.json")
    races_doc = _load("race_results.json")
    races = races_doc["races"]
    margins = prereg["non_degradation_margins"]

    # --- safety: population identity + arm equality + temporal firewall ---
    assert fold["population_hash"] == pop["population_hash"]
    assert cps["population_hash"] == pop["population_hash"]
    for entry in fold["checkpoints"]:
        for arm in ARMS:
            assert arm in entry, (entry["race_id"], entry["frame_index"], arm)
            tot = entry[arm]["valid"] + entry[arm]["invalid"]
            assert tot == fold["n_runs"], (arm, tot)
    seasons = {e["season"] for e in pop["evaluated"]}
    assert max(seasons) <= 2024 and min(seasons) >= 2020
    assert "2025" not in json.dumps(pop["evaluated"])
    throughs = {e["fold_through"] for e in pop["evaluated"]}
    assert max(throughs) <= 2023

    race_ids = sorted(races)

    def diffs(metric: str, x: str, y: str) -> list:
        # race-macro paired differences, arm x minus arm y (positive favors y)
        return [races[r]["arms"][x][metric] - races[r]["arms"][y][metric]
                for r in race_ids
                if races[r]["arms"][x][metric] is not None
                and races[r]["arms"][y][metric] is not None]

def boot(values: list) -> dict:
    from raceintel.simulation import validation as V7

    return V7.race_level_bootstrap(values, replicates=2000, seed=42)


def propose_verdict(bootstrap: dict, invalid: dict, fold_deltas: dict,
                    fold_ci_ok: bool, margins: dict) -> tuple:
    """Frozen decision logic (testable unit; operates on aggregates only).

    ``bootstrap``: {metric: {mean, ci95_low, ci95_high}} for A-minus-E,
    plus ``simpler_{arm}`` sub-dicts with the same shape for A-minus-arm.
    ``invalid``: {arm: {invalid_rate}}. ``fold_deltas``: {fold: pointDelta}.
    Returns (proposed, keep_e_inputs, simpler).
    """
    b = bootstrap
    inv_e = invalid["E_AR1_RESIDUAL"]["invalid_rate"] or 0.0
    inv_a = invalid["A_R3_BASELINE"]["invalid_rate"] or 0.0
    fold_point = sum(1 for v in fold_deltas.values()
                     if v is not None and v >= margins["fold_neutral_point"])
    keep_inputs = {
        "primary_ci": [b["winner_logloss"]["ci95_low"],
                       b["winner_logloss"]["ci95_high"]],
        "brier_ci_low": b["winner_brier"]["ci95_low"],
        "podium_brier_ci_low": b["podium_brier"]["ci95_low"],
        "mae_ci_low": b["exp_mae"]["ci95_low"],
        "invalid_e": inv_e, "invalid_a": inv_a,
        "folds_neutral_or_better": fold_point,
        "fold_ci_ok": fold_ci_ok}
    keep_e = (
        b["winner_logloss"]["ci95_low"] > 0
        and b["winner_brier"]["ci95_low"] > margins["brier_ci_low"]
        and b["podium_brier"]["ci95_low"] > margins["podium_brier_ci_low"]
        and b["exp_mae"]["ci95_low"] > margins["mae_ci_low_laps"]
        and inv_e <= margins["invalid_rate_max"]
        and (inv_e - inv_a) <= margins["invalid_rate_vs_A_pp"]
        and fold_point >= 2 and fold_ci_ok)
    if keep_e:
        return "KEEP_MC2_E", keep_inputs, None
    for arm, tag in (("B_DRIVER_ANCHOR", "KEEP_SIMPLER_ARM_B"),
                     ("C_DRIVER_ANCHOR_PLUS_DYNAMICS", "KEEP_SIMPLER_ARM_C"),
                     ("D_CONDITIONED_VARIANCE", "KEEP_SIMPLER_ARM_D")):
        key = f"simpler_{arm}"
        if key not in b:
            continue
        s = b[key]
        if (s["winner_logloss"]["ci95_low"] > 0
                and s["winner_brier"]["ci95_low"] > margins["brier_ci_low"]
                and s["podium_brier"]["ci95_low"]
                > margins["podium_brier_ci_low"]
                and s["exp_mae"]["ci95_low"] > margins["mae_ci_low_laps"]):
            return tag, keep_inputs, {"arm": arm}
    return "RETAIN_R3", keep_inputs, None

    # --- primary + secondary bootstrap (A minus E, positive favors E) ---
    bootstrap = {}
    for m in (PRIMARY,) + SECONDARIES:
        d = diffs(m, "A_R3_BASELINE", "E_AR1_RESIDUAL")
        b = boot(d)
        bootstrap[m] = {"n_races": len(d), "mean": b["mean"],
                        "ci95_low": b["ci95_low"],
                        "ci95_high": b["ci95_high"],
                        "improved": sum(1 for v in d if v > 0),
                        "degraded": sum(1 for v in d if v < 0),
                        "ties": sum(1 for v in d if v == 0)}
    _save("bootstrap.json", {
        "schema_version": "v3.2e-bootstrap-v1",
        "population_hash": pop["population_hash"],
        "design": "race-level paired A-minus-E, B=2000, seed=42",
        "metrics": bootstrap})

    # --- stage / season / fold aggregates ---
    rows = cps["rows"]
    stage_results, season_results, fold_results_agg = {}, {}, {}
    for stage in ("EARLY", "MID", "LATE"):
        sel = [r for r in rows if r["stage"] == stage]
        stage_results[stage] = {
            "n_checkpoints": len(sel),
            "n_races": len(set(r["race_id"] for r in sel)),
            "arms": {arm: {m: _mean([r["arms"][arm][m] for r in sel])
                           for m in (PRIMARY,) + SECONDARIES}
                     for arm in ARMS}}
    for season in (2020, 2021, 2022, 2023, 2024):
        sel = [r for r in rows if r["season"] == season]
        season_results[str(season)] = {
            "n_checkpoints": len(sel),
            "n_races": len(set(r["race_id"] for r in sel)),
            "arms": {arm: {m: _mean([r["arms"][arm][m] for r in sel])
                           for m in (PRIMARY,) + SECONDARIES}
                     for arm in ARMS}}
    folds = {"D1": (2020, 2021), "D2": (2022, 2023), "D3": (2024,)}
    for name, yrs in folds.items():
        sel = [r for r in rows if r["season"] in yrs]
        fold_results_agg[name] = {
            "n_checkpoints": len(sel),
            "n_races": len(set(r["race_id"] for r in sel)),
            "arms": {arm: {m: _mean([r["arms"][arm][m] for r in sel])
                           for m in (PRIMARY,) + SECONDARIES}
                     for arm in ARMS}}
    _save("stage_results.json", {"schema_version": "v3.2e-stage-v1",
                                 "population_hash": pop["population_hash"],
                                 "stages": stage_results})
    _save("season_results.json", {"schema_version": "v3.2e-season-v1",
                                  "population_hash": pop["population_hash"],
                                  "seasons": season_results,
                                  "folds": fold_results_agg})

    # --- ablations (paired race-macro primary diffs + CI) ---
    ablations = {}
    for label, x, y in (("anchor_A_vs_B", "A_R3_BASELINE", "B_DRIVER_ANCHOR"),
                        ("dynamics_B_vs_C", "B_DRIVER_ANCHOR",
                         "C_DRIVER_ANCHOR_PLUS_DYNAMICS"),
                        ("variance_C_vs_D",
                         "C_DRIVER_ANCHOR_PLUS_DYNAMICS",
                         "D_CONDITIONED_VARIANCE"),
                        ("ar1_D_vs_E", "D_CONDITIONED_VARIANCE",
                         "E_AR1_RESIDUAL")):
        d = diffs(PRIMARY, x, y)
        b = boot(d)
        ablations[label] = {"n_races": len(d), "mean": b["mean"],
                            "ci95_low": b["ci95_low"],
                            "ci95_high": b["ci95_high"]}
    _save("ablations.json", {"schema_version": "v3.2e-ablations-v1",
                             "population_hash": pop["population_hash"],
                             "primary": PRIMARY, "ablations": ablations})

    # --- calibration (favorite-based, descriptive) ---
    from raceintel.simulation import validation as V7

    calibration = {}
    for arm in ARMS:
        probs, outs = [], []
        for r in rows:
            probs.append(r["arms"][arm]["top_prob"])
            outs.append(1 if r["arms"][arm]["top_is_winner"] else 0)
        bins = V7.calibration_bins(probs, outs)
        calibration[arm] = {
            "n": len(probs),
            "ece": V7.expected_calibration_error(bins),
            "favorite_hit_rate": sum(outs) / len(outs),
            "bins": [{"lo": b["lo"], "hi": b["hi"], "count": b["count"],
                      "mean_p": b["mean_probability"],
                      "emp_rate": b["empirical_rate"]} for b in bins],
        }
    _save("calibration.json", {
        "schema_version": "v3.2e-calibration-v1",
        "population_hash": pop["population_hash"],
        "note": "favorite-based, checkpoints correlated within race; descriptive only",
        "arms": calibration})

    # --- failure inspection (race-macro primary A-minus-E extremes) ---
    ranked = sorted(
        race_ids,
        key=lambda r: (races[r]["arms"]["A_R3_BASELINE"][PRIMARY]
                       - races[r]["arms"]["E_AR1_RESIDUAL"][PRIMARY]))
    diag_by_key = {(e["race_id"], e["frame_index"]): e.get("anchor_diag", {})
                   for e in fold["checkpoints"]}

    def race_context(race_id: str) -> dict:
        rws = [r for r in rows if r["race_id"] == race_id]
        fb: dict[str, int] = {}
        ncl = []
        for r in rws:
            d = diag_by_key.get((r["race_id"], r["frame_index"]), {})
            for v in (d.get("fallback") or {}).values():
                fb[v] = fb.get(v, 0) + 1
            ncl.extend((d.get("n_clean") or {}).values())
        return {"n_checkpoints": len(rws),
                "stages": sorted(set(r["stage"] for r in rws)),
                "anchor_fallbacks": fb,
                "anchor_n_clean_mean": (sum(ncl) / len(ncl) if ncl else None)}

    inspection = {"improved": [], "degraded": []}
    for race_id in ranked[-3:][::-1]:
        inspection["improved"].append({
            "race_id": race_id,
            "delta_A_minus_E": races[race_id]["arms"]["A_R3_BASELINE"][PRIMARY]
            - races[race_id]["arms"]["E_AR1_RESIDUAL"][PRIMARY],
            **race_context(race_id)})
    for race_id in ranked[:3]:
        inspection["degraded"].append({
            "race_id": race_id,
            "delta_A_minus_E": races[race_id]["arms"]["A_R3_BASELINE"][PRIMARY]
            - races[race_id]["arms"]["E_AR1_RESIDUAL"][PRIMARY],
            **race_context(race_id)})
    _save("failure_inspection.json", {
        "schema_version": "v3.2e-failure-v1",
        "population_hash": pop["population_hash"],
        "inspection": inspection})

    # --- parameter stability per fold ---
    param_stab = {"variance_std": {}, "rho": {}, "anchor_fallback": {}}
    for through in (2019, 2021, 2023):
        v = json.loads((ROOT / "results" / "v3" / "v3_2d" /
                        f"mc2_params_through-{through}_variance.json")
                       .read_text(encoding="utf-8"))
        param_stab["variance_std"][f"through-{through}"] = v["values"]
    param_stab["rho"] = json.loads(
        (ROOT / "results" / "v3" / "v3_2d" / "parameter_diagnostics.json")
        .read_text(encoding="utf-8"))["lag1"]
    for name, yrs in folds.items():
        fb: dict[str, int] = {}
        for e in fold["checkpoints"]:
            season = next(p["season"] for p in pop["evaluated"]
                          if p["race_id"] == e["race_id"]
                          and p["frame_index"] == e["frame_index"])
            if season in yrs:
                for v in (e.get("anchor_diag", {}).get("fallback")
                          or {}).values():
                    fb[v] = fb.get(v, 0) + 1
        param_stab["anchor_fallback"][name] = fb
    _save("parameter_stability.json", {
        "schema_version": "v3.2e-param-stability-v1",
        "population_hash": pop["population_hash"], **param_stab})

    # --- invalid-run report ---
    invalid = {}
    for arm in ARMS:
        v = sum(e[arm]["valid"] for e in fold["checkpoints"])
        iv = sum(e[arm]["invalid"] for e in fold["checkpoints"])
        invalid[arm] = {"valid": v, "invalid": iv,
                        "invalid_rate": iv / (v + iv) if v + iv else None}
    _save("invalid_runs.json", {
        "schema_version": "v3.2e-invalid-v1",
        "population_hash": pop["population_hash"], "arms": invalid})

    # --- verdict proposal per frozen decision logic ---
    fold_deltas = {}
    for name in ("D1", "D2", "D3"):
        a = fold_results_agg[name]["arms"]["A_R3_BASELINE"][PRIMARY]
        e = fold_results_agg[name]["arms"]["E_AR1_RESIDUAL"][PRIMARY]
        fold_deltas[name] = (a - e) if (a is not None and e is not None) \
            else None
    # fold CI check via per-fold race diffs
    fold_ci_ok = True
    for name, yrs in folds.items():
        rids = [r for r in race_ids if races[r]["season"] in yrs]
        d = [races[r]["arms"]["A_R3_BASELINE"][PRIMARY]
             - races[r]["arms"]["E_AR1_RESIDUAL"][PRIMARY] for r in rids]
        ci = boot(d)
        if ci["ci95_high"] < margins["fold_degradation_ci_high"]:
            fold_ci_ok = False

    def bar_for(arm: str) -> dict:
        out = {}
        for m in (PRIMARY, "winner_brier", "podium_brier", "exp_mae"):
            ci = boot(diffs(m, "A_R3_BASELINE", arm))
            out[m] = {"mean": ci["mean"], "ci95_low": ci["ci95_low"],
                      "ci95_high": ci["ci95_high"]}
        return out

    verdict_bootstrap = {
        m: {"mean": bootstrap[m]["mean"],
            "ci95_low": bootstrap[m]["ci95_low"],
            "ci95_high": bootstrap[m]["ci95_high"]}
        for m in (PRIMARY, "winner_brier", "podium_brier", "exp_mae")}
    for arm in ("B_DRIVER_ANCHOR", "C_DRIVER_ANCHOR_PLUS_DYNAMICS",
                "D_CONDITIONED_VARIANCE"):
        verdict_bootstrap[f"simpler_{arm}"] = bar_for(arm)
    proposed, keep_inputs, simpler = propose_verdict(
        verdict_bootstrap, invalid, fold_deltas, fold_ci_ok, margins)
    _save("scientific_verdict.json", {
        "schema_version": "v3.2e-verdict-v1",
        "population_hash": pop["population_hash"],
        "proposed": proposed,
        "keep_e_inputs": keep_inputs,
        "simpler": simpler,
        "note": "operator reviews before final; no tuning permitted"})
    print("analysis complete; proposed:", proposed, flush=True)
    return proposed


if __name__ == "__main__":
    main()
