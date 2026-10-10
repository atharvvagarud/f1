"""V3.6D Phase 4: aggregate analysis (deterministic, protocol-bound).

Reads sample/layer1/layer2 + frozen V3.5 OOF; writes historical_evaluation,
case_studies, refinement_decision, and the top-level summary. No simulations
here. All thresholds/bands come from the frozen protocol.
"""

from __future__ import annotations

import json
import statistics
import sys
from collections import Counter, defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "results" / "v3" / "v3_6d"
PROTOCOL_HASH = "0c2bf7fb6e46a948d811587a64aac89cb10cfe0bf67485ed9ff3b457d64088fc"
DELTA_PP = ("delta_win_frequency", "delta_podium_frequency",
            "delta_top5_frequency", "delta_top10_frequency")


def q(v, p):
    s = sorted(v)
    if not s:
        return None
    k = (len(s) - 1) * p
    f = int(k)
    c = min(f + 1, len(s) - 1)
    return s[f] + (s[c] - s[f]) * (k - f)


def dist(v):
    v = list(v)
    return {"n": len(v), "median": q(v, 0.5), "q25": q(v, 0.25),
            "q75": q(v, 0.75), "min": min(v) if v else None,
            "max": max(v) if v else None}


def main() -> None:
    sample = json.loads((D / "sample.json").read_text())
    layer1 = json.loads((D / "layer1.json").read_text())
    layer2 = json.loads((D / "layer2.json").read_text())
    states = layer1["states"]

    # ---- G/H coverage ----
    cand, elig = sample["candidates"], sample["eligible"]
    unsup = Counter(c["reason"] for c in sample["states"] if not c["eligible"])
    supported = sum(1 for s in states if s["result"]["supported"])

    # ---- per-comparison flat table ----
    rows = []
    for s in states:
        res = s["result"]
        for a in res["alternatives"]:
            row = {"race": s["race_id"], "anchor": s["anchor"],
                   "target": s["target_driver_id"], "stage": s["stage"],
                   "decision_lap": s["decision_lap"],
                   "key": a["candidate_key"], "evaluated": a["evaluated"],
                   "reason": a["reason"], "pairs": a["complete_pairs"],
                   "excluded": a["excluded_pairs"], "supported": res["supported"]}
            if a["evaluated"]:
                row["deltas"] = {d["metric"]: d for d in a["deltas"]}
                row["ref"] = a["reference_aggregate"]
                row["alt"] = a["alternative_aggregate"]
                row["exec"] = a["execution"]
                row["cid"] = a["comparison_identity"]
            rows.append(row)
    ev = [r for r in rows if r["evaluated"]]

    # ---- I action coverage ----
    action_cov = {}
    for key in sorted({r["key"] for r in rows}):
        sub = [r for r in rows if r["key"] == key]
        sev = [r for r in sub if r["evaluated"]]
        ex = [r["exec"] for r in sev]
        action_cov[key] = {
            "states_valid": len(sev), "states_invalid": len(sub) - len(sev),
            "invalid_reasons": dict(Counter(r["reason"] for r in sub
                                            if not r["evaluated"])),
            "mean_execution_rate": statistics.fmean(
                e["applied_rate"] for e in ex) if ex else None,
            "mean_inert_rate": statistics.fmean(
                e["inert_rate"] for e in ex) if ex else None,
            "mean_superseded_rate": statistics.fmean(
                e["superseded_rate"] for e in ex) if ex else None,
            "mean_cancelled_rate": statistics.fmean(
                e["race_end_cancelled_rate"] for e in ex) if ex else None,
            "mean_complete_pairs": statistics.fmean(
                r["pairs"] for r in sev) if sev else None}

    # ---- J reproducibility ----
    repro = layer2["reproducibility"]
    repro_ok = all(r["identical"] for r in repro)

    # ---- K seed stability (PIT_NOW + STAY_OUT, 6 states) ----
    seed_rows = []
    for entry in layer2["seeds_experiment"]:
        by_seed = {}
        for run in entry["runs"]:
            for a in run["result"]["alternatives"]:
                if a["evaluated"]:
                    by_seed.setdefault(a["candidate_key"], {})[run["seed"]] = {
                        d["metric"]: (d["point_estimate"], d["ci_low"],
                                      d["ci_high"]) for d in a["deltas"]}
        for key, per_seed in by_seed.items():
            metrics = {}
            for m in ("delta_win_frequency", "delta_podium_frequency",
                      "delta_expected_finish", "delta_downside_probability"):
                pts = [per_seed[s][m][0] for s in per_seed]
                metrics[m] = {
                    "spread": max(pts) - min(pts),
                    "max_abs": max(abs(p) for p in pts),
                    "sign_consistent": all(p >= 0 for p in pts) or all(
                        p <= 0 for p in pts)}
            seed_rows.append({"race": entry["race_id"], "key": key,
                              "metrics": metrics})
    seed_spread = {m: dist(r["metrics"][m]["spread"] for r in seed_rows)
                   for m in next(iter(seed_rows))["metrics"]} if seed_rows else {}
    sign_consistent_rate = statistics.fmean(
        1.0 if all(v["sign_consistent"] for v in r["metrics"].values())
        else 0.0 for r in seed_rows) if seed_rows else None
    material = [r for r in seed_rows if any(
        r["metrics"][m]["max_abs"] >= t
        for m, t in (("delta_win_frequency", 0.03),
                     ("delta_podium_frequency", 0.03),
                     ("delta_expected_finish", 0.25)))]
    material_consistent_rate = statistics.fmean(
        1.0 if all(v["sign_consistent"] for v in r["metrics"].values())
        else 0.0 for r in material) if material else None

    # ---- L count stability ----
    count_rows = []
    for entry in layer2["counts_experiment"]:
        by_n = {}
        for run in entry["runs"]:
            for a in run["result"]["alternatives"]:
                if a["evaluated"] and a["candidate_key"] == "PIT_NOW:SAMPLED":
                    by_n[run["n"]] = {
                        d["metric"]: d["point_estimate"] for d in a["deltas"]}
        if set(by_n) == {200, 1000, 5000}:
            count_rows.append({
                "race": entry["race_id"],
                "diff_200": {m: abs(by_n[200][m] - by_n[5000][m])
                             for m in by_n[5000]},
                "diff_1000": {m: abs(by_n[1000][m] - by_n[5000][m])
                              for m in by_n[5000]}})
    count_conv = {}
    for m in ("delta_win_frequency", "delta_podium_frequency",
              "delta_expected_finish"):
        count_conv[m] = {
            "median_absdiff_200_vs_5000": q(
                [r["diff_200"][m] for r in count_rows], 0.5),
            "median_absdiff_1000_vs_5000": q(
                [r["diff_1000"][m] for r in count_rows], 0.5)}

    # ---- M CRN ----
    crn = layer2["crn_experiment"]
    informative = [c for c in crn
                   if (c["independent_se_win"] or 0) > 0]
    degenerate = [c for c in crn if not (c["independent_se_win"] or 0) > 0]
    ratios = [c["paired_se_win"] / c["independent_se_win"]
              for c in informative]
    crn_result = {
        "ratio_definition": "paired_SE / independent_SE; >1 means CRN "
                            "worse (paired wider). Gate label plain meaning.",
        "n_informative": len(informative),
        "n_degenerate_both_zero": len(degenerate),
        "median_ratio_paired_over_indep": q(ratios, 0.5),
        "min": min(ratios) if ratios else None,
        "max": max(ratios) if ratios else None,
        "all_favor_paired": all(r <= 1.0 for r in ratios)
        if ratios else None}

    # ---- N sanity flags ----
    flags = []
    for r in ev:
        bound = r["ref"]["roster_size"] - 1
        for d in r["deltas"].values():
            if d["metric"] == "delta_expected_finish":
                ok = -bound - 1e-9 <= d["point_estimate"] <= bound + 1e-9
            else:
                ok = -1.0 - 1e-9 <= d["point_estimate"] <= 1.0 + 1e-9
            if not ok:
                flags.append((r["race"], r["key"], d["metric"], "out_of_bounds"))
        tot = sum(e["frequency"] for e in r["alt"]["finish_position_distribution"])
        if abs(tot - 1.0) > 1e-9:
            flags.append((r["race"], r["key"], "distribution", "sum!=1"))
        if r["exec"]["inert_rate"] > 0.9:
            for m in DELTA_PP:
                if abs(r["deltas"][m]["point_estimate"]) > 0.01:
                    flags.append((r["race"], r["key"], m, "inert_but_large"))
    for r in rows:
        if not r["evaluated"] and r["reason"] not in (
                "unsupported_action", "unsupported_compound",
                "anchor_mismatch", "decision_lap_mismatch",
                "decision_beyond_race", "pit_dynamics_required",
                "malformed_intervention", "NO_VALID_PAIRS",
                "target_driver_not_in_roster", None):
            flags.append((r["race"], r["key"], "-", "unknown_reason"))

    # ---- O/P sensitivity + distributions ----
    win_pp = [abs(r["deltas"]["delta_win_frequency"]["point_estimate"]) * 100
              for r in ev]
    fin_pos = [abs(r["deltas"]["delta_expected_finish"]["point_estimate"])
               for r in ev]

    def band(v, cuts):
        small, moderate, large = cuts
        return {"zero": sum(1 for x in v if x < small),
                "small": sum(1 for x in v if small <= x < moderate),
                "moderate": sum(1 for x in v if moderate <= x < large),
                "large": sum(1 for x in v if x >= large)}

    effects = {}
    for m in ("delta_win_frequency", "delta_podium_frequency",
              "delta_top5_frequency", "delta_top10_frequency",
              "delta_expected_finish", "delta_downside_probability"):
        vals = [r["deltas"][m]["point_estimate"] for r in ev]
        effects[m] = dist(vals)
    by_action = {}
    for key in sorted({r["key"] for r in ev}):
        sub = [r for r in ev if r["key"] == key]
        by_action[key] = {
            m: dist([r["deltas"][m]["point_estimate"] for r in sub])
            for m in effects}

    # ---- Q classification ----
    def classify(d):
        if d["ci_low"] is None:
            return "UNCERTAIN"
        if d["ci_low"] > 0:
            return "POSITIVE"
        if d["ci_high"] < 0:
            return "NEGATIVE"
        return "UNCERTAIN"

    qrates = {}
    for key in sorted({r["key"] for r in ev}):
        sub = [r for r in ev if r["key"] == key]
        qrates[key] = {
            m: dict(Counter(classify(r["deltas"][m]) for r in sub))
            for m in ("delta_win_frequency", "delta_podium_frequency",
                      "delta_expected_finish")}

    # ---- R disagreement ----
    n_ev = len(ev)
    disagree = {
        "podium_up_downside_up": sum(
            1 for r in ev if r["deltas"]["delta_podium_frequency"][
                "point_estimate"] > 0 and r["deltas"][
                "delta_downside_probability"]["point_estimate"] > 0.02) / n_ev,
        "finish_up_win_down": sum(
            1 for r in ev if r["deltas"]["delta_expected_finish"][
                "point_estimate"] > 0 > r["deltas"][
                "delta_win_frequency"]["point_estimate"]) / n_ev,
        "top10_up_podium_down": sum(
            1 for r in ev if r["deltas"]["delta_top10_frequency"][
                "point_estimate"] > 0 > r["deltas"][
                "delta_podium_frequency"]["point_estimate"]) / n_ev}

    # ---- T stage ----
    stage = {}
    for st in ("EARLY", "MID", "LATE"):
        sub = [r for r in ev if r["stage"] == st]
        stage[st] = {"comparisons": len(sub),
                     "median_abs_win_pp": q([abs(
                         r["deltas"]["delta_win_frequency"]["point_estimate"])
                         * 100 for r in sub], 0.5),
                     "median_abs_finish": q([abs(
                         r["deltas"]["delta_expected_finish"]["point_estimate"])
                         for r in sub], 0.5)}

    # ---- U race heterogeneity ----
    by_race = {}
    for race in sorted({r["race"] for r in ev}):
        sub = [r for r in ev if r["race"] == race]
        by_race[race] = {"comparisons": len(sub), "median_abs_finish": q(
            [abs(r["deltas"]["delta_expected_finish"]["point_estimate"])
             for r in sub], 0.5)}

    # ---- V PIT_NOW vs PIT_NEXT_LAP (same compound+state) ----
    vrows = []
    for s in states:
        mp = {a["candidate_key"]: a for a in s["result"]["alternatives"]}
        for comp in ("SAMPLED", "SOFT", "MEDIUM", "HARD"):
            a = mp.get(f"PIT_NOW:{comp}")
            b = mp.get(f"PIT_NEXT_LAP:{comp}")
            if a and b and a["evaluated"] and b["evaluated"]:
                vrows.append({
                    "race": s["race_id"],
                    "compound": comp,
                    "now_superseded": a["execution"]["superseded"],
                    "next_superseded": b["execution"]["superseded"],
                    "d_win_diff": next(
                        d["point_estimate"] for d in b["deltas"]
                        if d["metric"] == "delta_win_frequency") - next(
                        d["point_estimate"] for d in a["deltas"]
                        if d["metric"] == "delta_win_frequency")})

    # ---- W STAY_OUT vs reference ----
    so = [r for r in ev if r["key"] == "STAY_OUT:SAMPLED"]
    stay_out = {
        "n": len(so),
        "suppression_rate": statistics.fmean(
            r["exec"]["suppressed_rate"] for r in so),
        "inert_rate": statistics.fmean(r["exec"]["inert_rate"] for r in so),
        "differs_rate": sum(
            1 for r in so if r["exec"]["baseline_pit_suppressed"] > 0) / len(
            so) if so else None,
        "abs_win_pp_dist": dist([abs(
            r["deltas"]["delta_win_frequency"]["point_estimate"]) * 100
            for r in so])}

    # ---- X compounds ----
    comp_eff = {}
    for act in ("PIT_NOW", "PIT_NEXT_LAP"):
        comp_eff[act] = {}
        for comp in ("SAMPLED", "SOFT", "MEDIUM", "HARD"):
            sub = [r for r in ev if r["key"] == f"{act}:{comp}"]
            comp_eff[act][comp] = dist([abs(
                r["deltas"]["delta_expected_finish"]["point_estimate"])
                for r in sub])

    # ---- Y V3.5 diagnostic ----
    import pandas as pd
    oof = pd.concat([pd.read_parquet(
        f"data/v3/v3_5c/oof_{f}.parquet") for f in ("D1", "D2", "D3")],
        ignore_index=True)
    oof = oof[oof["model"] == "l2_logistic"].set_index(
        ["race_id", "driver_id"])
    yrows = []
    for s in states:
        for a in s["result"]["alternatives"]:
            if not a["evaluated"]:
                continue
            try:
                prow = oof.loc[(s["race_id"], s["target_driver_id"])]
            except KeyError:
                continue
            lap = s["decision_lap"]
            # prow is one row (Series) or several lap rows (DataFrame).
            if getattr(prow, "ndim", 2) == 2:
                found = None
                for _, pr in prow.iterrows():
                    sid = str(pr["state_id"])
                    if sid.rsplit("|", 1)[-1] == str(lap):
                        found = float(pr["proj_is_top1"])
                        break
                if found is None:
                    continue
                p_win = found
            else:
                sid = str(prow["state_id"])
                if sid.rsplit("|", 1)[-1] != str(lap):
                    continue
                p_win = float(prow["proj_is_top1"])
            yrows.append({"mc2_win": a["reference_aggregate"][
                "win_frequency"], "v35_p_win": p_win,
                "stage": s["stage"], "race": s["race_id"]})
            break  # one reference per state
    import math
    diffs = [abs(r["mc2_win"] - r["v35_p_win"]) for r in yrows]
    v35 = {"matched_states": len(yrows),
           "mean_abs_diff": statistics.fmean(diffs) if diffs else None,
           "median_abs_diff": q(diffs, 0.5),
           "correlation": (statistics.correlation(
               [r["mc2_win"] for r in yrows],
               [r["v35_p_win"] for r in yrows]) if len(yrows) > 2 else None),
           "by_stage": {st: dist([abs(r["mc2_win"] - r["v35_p_win"])
                                  for r in yrows if r["stage"] == st])["median"]
                        for st in ("EARLY", "MID", "LATE")}}

    # ---- Z case studies (frozen algorithmic rules) ----
    desc = []
    for s in states:
        for a in s["result"]["alternatives"]:
            if not a["evaluated"]:
                continue
            widths = [(d["ci_high"] - d["ci_low"]) if d["ci_low"] is not None
                      else None for d in a["deltas"]]
            widths = [w for w in widths if w is not None]
            pod = next(d["point_estimate"] for d in a["deltas"]
                       if d["metric"] == "delta_podium_frequency")
            win = next(d["point_estimate"] for d in a["deltas"]
                       if d["metric"] == "delta_win_frequency")
            down = next(d["point_estimate"] for d in a["deltas"]
                        if d["metric"] == "delta_downside_probability")
            nz_win = next((d["ci_low"] > 0 or d["ci_high"] < 0)
                          for d in a["deltas"]
                          if d["metric"] == "delta_win_frequency"
                          and d["ci_low"] is not None)
            desc.append({"state": s, "alt": a, "abs_pod": abs(pod),
                         "mean_width": statistics.fmean(widths) if widths
                         else None, "win": win, "down": down,
                         "nz_win": bool(nz_win),
                         "non_exec": a["execution"]["superseded_rate"]
                         + a["execution"]["inert_rate"]
                         + a["execution"]["race_end_cancelled_rate"]})
    med_pod = q([d["abs_pod"] for d in desc], 0.5)
    cases = {
        "median_effect": min(desc, key=lambda d: abs(d["abs_pod"] - med_pod)),
        "high_uncertainty": max(
            (d for d in desc if d["mean_width"] is not None),
            key=lambda d: d["mean_width"]),
        "objective_tradeoff": max(
            (d for d in desc if d["down"] > 0.02),
            key=lambda d: next(
                x["point_estimate"] for x in d["alt"]["deltas"]
                if x["metric"] == "delta_podium_frequency"),
            default=None) or min(desc, key=lambda d: abs(d["down"] - 0.02)),
        "inert_superseded": max(desc, key=lambda d: d["non_exec"]),
        "strong_supported": max(
            (d for d in desc if d["nz_win"]),
            key=lambda d: abs(d["win"]), default=None) or max(
            desc, key=lambda d: abs(d["win"]))}

    eval_out = {
        "protocol_hash": PROTOCOL_HASH,
        "population": {"candidates": cand, "eligible": elig,
                       "supported": supported},
        "unsupported_composition": dict(unsup),
        "action_coverage": action_cov,
        "reproducibility": {"all_identical": repro_ok, "n": len(repro)},
        "seed_stability": {"spread": seed_spread,
                           "sign_consistent_rate": sign_consistent_rate},
        "count_stability": count_conv,
        "crn": crn_result,
        "sanity_flags": flags,
        "sensitivity_bands": {
            "abs_win_pp": {"dist": dist(win_pp), "bands": {
                "zero_<1": sum(1 for x in win_pp if x < 1),
                "small_1_3": sum(1 for x in win_pp if 1 <= x < 3),
                "moderate_3_8": sum(1 for x in win_pp if 3 <= x < 8),
                "large_>=8": sum(1 for x in win_pp if x >= 8)}},
            "abs_finish": {"dist": dist(fin_pos), "bands": {
                "zero_<0.1": sum(1 for x in fin_pos if x < 0.1),
                "small_0.1_0.5": sum(1 for x in fin_pos if 0.1 <= x < 0.5),
                "moderate_0.5_1.5": sum(
                    1 for x in fin_pos if 0.5 <= x < 1.5),
                "large_>=1.5": sum(1 for x in fin_pos if x >= 1.5)}}},
        "effect_distributions": effects,
        "effects_by_action": by_action,
        "classification_rates": qrates,
        "objective_disagreement": disagree,
        "leader_stability_note": "adjacent-checkpoint N/A (one checkpoint "
                                 "per race); seed/count leader agreement in "
                                 "seed_stability/count appendices",
        "stage": stage,
        "race_heterogeneity": by_race,
        "pit_now_vs_next": {
            "n_paired": len(vrows),
            "median_abs_d_win_diff": q(
                [abs(v["d_win_diff"]) for v in vrows], 0.5),
            "mean_next_superseded": statistics.fmean(
                v["next_superseded"] / 200 for v in vrows) if vrows else None},
        "stay_out_vs_reference": stay_out,
        "compound_effects": comp_eff,
        "v35_diagnostic": v35,
    }
    (D / "historical_evaluation.json").write_text(json.dumps(eval_out))

    # ---- AA/AB case records + plausibility ----
    def pathology(s, a):
        hits = []
        for d in a["deltas"]:
            if d["metric"] != "delta_expected_finish" and not (
                    -1.0 - 1e-9 <= d["point_estimate"] <= 1.0 + 1e-9):
                hits.append(f"{d['metric']}_out_of_bounds")
        tot = sum(e["frequency"] for e in a["alternative_aggregate"][
            "finish_position_distribution"])
        if abs(tot - 1.0) > 1e-9:
            hits.append("distribution_sum")
        for e in a["alternative_aggregate"][
                "finish_position_distribution"]:
            if not (1 <= e["position"] <= a["alternative_aggregate"]["roster_size"]):
                hits.append("impossible_position")
        if a["execution"]["inert_rate"] > 0.9:
            for d in a["deltas"]:
                if d["metric"].startswith("delta_win") and abs(
                        d["point_estimate"]) > 0.01:
                    hits.append("inert_but_large")
        return hits

    case_records = {}
    for name, d in cases.items():
        s, a = d["state"], d["alt"]
        hits = pathology(s, a)
        case_records[name] = {
            "race": s["race_id"], "anchor": s["anchor"],
            "target": s["target_driver_id"], "stage": s["stage"],
            "decision_lap": s["decision_lap"],
            "alternative": a["candidate_key"],
            "reference": {k: a["reference_aggregate"][k] for k in (
                "win_frequency", "podium_frequency", "expected_finish")},
            "deltas": {x["metric"]: {
                "point": x["point_estimate"], "se": x["paired_se"],
                "ci": [x["ci_low"], x["ci_high"]],
                "availability": x["availability"]} for x in a["deltas"]},
            "execution": a["execution"],
            "comparison_identity": a["comparison_identity"],
            "pathology_hits": hits,
            "plausibility": ("PATHOLOGICAL" if hits else "PLAUSIBLE")}
    (D / "case_studies.json").write_text(json.dumps(
        {"selection": "algorithmic per frozen protocol", "cases": case_records}))
    n_path = sum(1 for c in case_records.values()
                 if c["plausibility"] == "PATHOLOGICAL")

    # ---- AC refinement gate ----
    zero_pair_rate = 1 - (sum(1 for r in ev) / max(
        1, sum(1 for r in rows if r["supported"])))
    sign_flip = 1 - (sign_consistent_rate or 1.0)
    median_ratio = crn_result["median_ratio_paired_over_indep"]
    gates = {
        "reproducibility_ok": bool(repro_ok),
        "pathological_cases": n_path,
        "crn_median_ratio": median_ratio,
        "crn_sign_flip_rate": sign_flip,
        "zero_pair_rate_proxy": zero_pair_rate,
    }
    warranted = (not repro_ok) or (n_path > 0) or (
        median_ratio is not None and median_ratio > 1.05
        and sign_flip > 0.20)
    decision = {"verdict": ("REFINEMENT_WARRANTED" if warranted else
                            "REFINEMENT_NOT_WARRANTED"),
                "gates": gates,
                "material_sign_consistent_rate": material_consistent_rate,
                "ratio_disambiguation": "protocol froze the trigger as "
                "median width ratio > 1.05 under the label CRN worse; the "
                "analyzer reports paired/indep so the literal rule matches "
                "its label. Protocol file itself unchanged.",
                "note": "No tuning performed; small effects / zero-crossing "
                        "intervals / team-choice divergence are not defects."}
    (D / "refinement_decision.json").write_text(json.dumps(decision))

    summary = {
        "protocol_hash": PROTOCOL_HASH,
        "population": eval_out["population"],
        "coverage": {"unsupported": dict(unsup)},
        "reproducibility": eval_out["reproducibility"],
        "seed_stability": {"sign_consistent_rate": sign_consistent_rate},
        "count_stability": count_conv,
        "crn": crn_result,
        "effects": {m: {"median": v["median"], "q25": v["q25"],
                        "q75": v["q75"]} for m, v in effects.items()},
        "objective_disagreement": disagree,
        "stage": stage,
        "stay_out_vs_reference": {k: v for k, v in stay_out.items()
                                  if k != "abs_win_pp_dist"},
        "v35_diagnostic": {k: v for k, v in v35.items()},
        "cases": {k: {"race": v["race"], "alternative": v["alternative"],
                      "plausibility": v["plausibility"]}
                  for k, v in case_records.items()},
        "pathology_count": n_path,
        "refinement_decision": decision["verdict"],
        "known_limitations": [
            "simulator-conditional counterfactuals; no ground truth",
            "no status-resolver relief (conservative eligibility)",
            "single target per state (anchor driver)",
            "Layer-1 n=200 (intervals mostly withheld); Layer-2 n=5000 on 8",
            "V3.5 join limited to matched (race,driver,lap) OOF rows"],
    }
    (ROOT / "results" / "v3" / "v3_6d_historical_strategy_evaluation.json"
     ).write_text(json.dumps(summary, indent=1))
    print("analysis done:",
          f"comparisons={len(rows)} evaluated={len(ev)} "
          f"flags={len(flags)} pathological={n_path} "
          f"verdict={decision['verdict']}")


if __name__ == "__main__":
    main()
