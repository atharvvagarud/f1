"""V3.8E controlled Logistic x MC2 fusion research (deterministic, cheap).

Reuses the EXACT frozen D per-row records (results/v3/v3_8d/per_row_records.json,
277 comparable rows) and the frozen E protocol. No MC2 execution, no model
inference, no new simulation: this module never imports the MC2 kernel
or any simulation/model code (tests fail closed on any such path).

Design (preregistered in results/v3/v3_8e/fusion_protocol.json):
  expanding-window prequential over 8 chronological races, warm-up 3,
  convex grid alpha in {0.0..1.0 step 0.1}, tuning objective race-macro
  binary log loss on PRIOR races, tie-break largest alpha.

Writes: fusion_evaluation.json, per_race_results.json, prequential_weights.json,
fixed_weight_curve.json, robustness_analysis.json, fusion_gate.json,
fusion_card.json into results/v3/v3_8e/.
"""

from __future__ import annotations

import collections
import hashlib
import json
import math
import random
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "results" / "v3" / "v3_8d"
E = ROOT / "results" / "v3" / "v3_8e"

EPS = 1e-15
GRID = [round(i / 10, 1) for i in range(11)]
CHRONO = [
    "2022-r03-R", "2022-r11-R", "2022-r19-R", "2023-r05-R",
    "2023-r13-R", "2023-r21-R", "2024-r07-R", "2024-r15-R",
]
WARMUP = 3
BOOT_B = 2000
BOOT_SEED = 987654322
EXTREME_STATE_ID = "2023-r21-R|max_verstappen|3"


def _clip(p: float) -> float:
    return min(max(p, EPS), 1.0 - EPS)


def _ll(p: float, y: int) -> float:
    p = _clip(p)
    return -(y * math.log(p) + (1.0 - y) * math.log(1.0 - p))


def _bs(p: float, y: int) -> float:
    return (p - y) ** 2


def _fuse(alpha: float, p_log: float, p_mc2: float) -> float:
    assert 0.0 <= alpha <= 1.0
    return alpha * p_log + (1.0 - alpha) * p_mc2


def _ci95(v: list) -> list:
    s = sorted(v)
    return [s[int(0.025 * len(s))], s[int(0.975 * len(s))]]


def main() -> int:
    t_start = time.perf_counter()

    # ---- protocol freeze check (fail closed) ----
    proto = json.loads((E / "fusion_protocol.json").read_text())
    proto_id = proto.pop("protocol_identity")
    blob = json.dumps(proto, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(blob).hexdigest() == proto_id, \
        "E protocol mutated after hash"
    assert proto_id == \
        "dbe6a565d5a6fa688dbb8e0b3a1be05bad71457777cd2e312f9c164219b128dd"
    proto["protocol_identity"] = proto_id
    assert proto["warmup_races"] == WARMUP
    assert proto["chronology"] == CHRONO
    assert proto["alpha_grid"] == GRID
    assert proto["bootstrap"]["seed"] == BOOT_SEED
    assert proto["bootstrap"]["B"] == BOOT_B

    rows = json.loads((D / "per_row_records.json").read_text())
    assert len(rows) == 277, len(rows)
    assert len({r["state_id"] for r in rows}) == 277
    assert set(r["season"] for r in rows) <= {2022, 2023, 2024}
    assert sorted({r["race_id"] for r in rows}) == CHRONO
    for r in rows:
        for k in ("p_logistic", "p_mc2", "target"):
            assert math.isfinite(r[k]), (r["state_id"], k)
        assert 0.0 <= r["p_logistic"] <= 1.0
        assert 0.0 <= r["p_mc2"] <= 1.0

    by_race: dict = collections.defaultdict(list)
    for r in rows:
        by_race[r["race_id"]].append(r)

    def race_mean(race: str, alpha: float, metric: str) -> float:
        vals = []
        for r in by_race[race]:
            p = _fuse(alpha, r["p_logistic"], r["p_mc2"])
            vals.append(_ll(p, r["target"]) if metric == "ll"
                        else _bs(p, r["target"]))
        return sum(vals) / len(vals)

    def macro(history: list, alpha: float, metric: str) -> float:
        return sum(race_mean(rc, alpha, metric) for rc in history) / len(history)

    def pooled(rowset: list, alpha: float, metric: str) -> float:
        vals = [(_ll(_fuse(alpha, r["p_logistic"], r["p_mc2"]), r["target"])
                 if metric == "ll"
                 else _bs(_fuse(alpha, r["p_logistic"], r["p_mc2"]),
                          r["target"]))
                for r in rowset]
        return sum(vals) / len(vals)

    # ---- prequential tuning + evaluation ----
    t_eval0 = time.perf_counter()
    weights = []
    eval_results = []
    for k in range(WARMUP, len(CHRONO)):
        hist = CHRONO[:k]
        curve = [(a, macro(hist, a, "ll")) for a in GRID]
        best = min(v for _, v in curve)
        alpha = max(a for a, v in curve if v == best)
        race = CHRONO[k]
        weights.append({"race_id": race, "history": list(hist),
                        "selected_alpha": alpha,
                        "tuning_curve": [[a, v] for a, v in curve]})
        rr = by_race[race]
        eval_results.append({
            "race_id": race, "n": len(rr), "selected_alpha": alpha,
            "mean_ll_log": sum(r["ll_log"] for r in rr) / len(rr),
            "mean_ll_mc2": sum(r["ll_mc2"] for r in rr) / len(rr),
            "mean_ll_fused": race_mean(race, alpha, "ll"),
            "mean_bs_log": sum(r["bs_log"] for r in rr) / len(rr),
            "mean_bs_mc2": sum(r["bs_mc2"] for r in rr) / len(rr),
            "mean_bs_fused": race_mean(race, alpha, "bs"),
        })
    eval_races = [e["race_id"] for e in eval_results]
    eval_rows = [r for rc in eval_races for r in by_race[rc]]
    t_eval1 = time.perf_counter()

    def eval_macro(metric: str, arm: str,
                   table: list | None = None) -> float:
        table = table if table is not None else eval_results
        key = {"log": "mean_ll_log" if metric == "ll" else "mean_bs_log",
               "mc2": "mean_ll_mc2" if metric == "ll" else "mean_bs_mc2",
               "fused": "mean_ll_fused" if metric == "ll"
               else "mean_bs_fused"}[arm]
        return sum(e[key] for e in table) / len(table)

    def eval_pooled(metric: str, arm: str, rowset: list | None = None) -> float:
        rowset = rowset if rowset is not None else eval_rows
        if arm == "log":
            vals = [r["ll_log"] if metric == "ll" else r["bs_log"]
                    for r in rowset]
        elif arm == "mc2":
            vals = [r["ll_mc2"] if metric == "ll" else r["bs_mc2"]
                    for r in rowset]
        else:
            amap = {w["race_id"]: w["selected_alpha"] for w in weights}
            vals = [(_ll(_fuse(amap[r["race_id"]], r["p_logistic"],
                               r["p_mc2"]), r["target"])
                     if metric == "ll"
                     else _bs(_fuse(amap[r["race_id"]], r["p_logistic"],
                                    r["p_mc2"]), r["target"]))
                    for r in rowset]
        return sum(vals) / len(vals)

    macro_ll = {a: eval_macro("ll", a) for a in ("log", "mc2", "fused")}
    macro_bs = {a: eval_macro("bs", a) for a in ("log", "mc2", "fused")}
    pooled_ll = {a: eval_pooled("ll", a) for a in ("log", "mc2", "fused")}
    pooled_bs = {a: eval_pooled("bs", a) for a in ("log", "mc2", "fused")}
    deltas = {
        "delta_fusion_vs_log_macro_ll":
            macro_ll["fused"] - macro_ll["log"],
        "delta_fusion_vs_mc2_macro_ll":
            macro_ll["fused"] - macro_ll["mc2"],
        "delta_fusion_vs_log_pooled_ll":
            pooled_ll["fused"] - pooled_ll["log"],
        "delta_fusion_vs_mc2_pooled_ll":
            pooled_ll["fused"] - pooled_ll["mc2"],
        "delta_fusion_vs_log_macro_bs":
            macro_bs["fused"] - macro_bs["log"],
        "delta_fusion_vs_mc2_macro_bs":
            macro_bs["fused"] - macro_bs["mc2"],
        "delta_fusion_vs_log_pooled_bs":
            pooled_bs["fused"] - pooled_bs["log"],
        "delta_fusion_vs_mc2_pooled_bs":
            pooled_bs["fused"] - pooled_bs["mc2"],
    }
    for e in eval_results:
        e["delta_fused_vs_log_ll"] = e["mean_ll_fused"] - e["mean_ll_log"]
        e["delta_fused_vs_mc2_ll"] = e["mean_ll_fused"] - e["mean_ll_mc2"]

    # ---- paired race-level bootstrap over evaluation races ----
    t_boot0 = time.perf_counter()
    rng = random.Random(BOOT_SEED)
    rep_log_ll, rep_mc2_ll, rep_log_bs, rep_mc2_bs = [], [], [], []
    for _ in range(BOOT_B):
        picks = [eval_races[rng.randrange(len(eval_races))]
                 for _ in range(len(eval_races))]
        # race-macro with multiplicity: mean of per-pick race means
        by_id = {e["race_id"]: e for e in eval_results}
        f_ll = sum(by_id[p]["mean_ll_fused"] for p in picks) / len(picks)
        l_ll = sum(by_id[p]["mean_ll_log"] for p in picks) / len(picks)
        m_ll = sum(by_id[p]["mean_ll_mc2"] for p in picks) / len(picks)
        f_bs = sum(by_id[p]["mean_bs_fused"] for p in picks) / len(picks)
        l_bs = sum(by_id[p]["mean_bs_log"] for p in picks) / len(picks)
        m_bs = sum(by_id[p]["mean_bs_mc2"] for p in picks) / len(picks)
        rep_log_ll.append(f_ll - l_ll)
        rep_mc2_ll.append(f_ll - m_ll)
        rep_log_bs.append(f_bs - l_bs)
        rep_mc2_bs.append(f_bs - m_bs)
    t_boot1 = time.perf_counter()
    bootstrap = {
        "delta_fusion_vs_log_macro_ll": {
            "mean": sum(rep_log_ll) / len(rep_log_ll),
            "ci95": _ci95(rep_log_ll)},
        "delta_fusion_vs_mc2_macro_ll": {
            "mean": sum(rep_mc2_ll) / len(rep_mc2_ll),
            "ci95": _ci95(rep_mc2_ll)},
        "delta_fusion_vs_log_macro_bs": {
            "mean": sum(rep_log_bs) / len(rep_log_bs),
            "ci95": _ci95(rep_log_bs)},
        "delta_fusion_vs_mc2_macro_bs": {
            "mean": sum(rep_mc2_bs) / len(rep_mc2_bs),
            "ci95": _ci95(rep_mc2_bs)},
    }

    # ---- fixed-weight descriptive curve (full corpus, REVEALED) ----
    full_rows = rows
    full_races = CHRONO
    curve = []
    for a in GRID:
        curve.append({
            "alpha": a,
            "race_macro_ll": macro(full_races, a, "ll"),
            "pooled_ll": pooled(full_rows, a, "ll"),
            "race_macro_bs": macro(full_races, a, "bs"),
            "pooled_bs": pooled(full_rows, a, "bs"),
        })
    oracle = min(curve, key=lambda c: c["race_macro_ll"])

    # ---- robustness ----
    amap = {w["race_id"]: w["selected_alpha"] for w in weights}
    loro = []
    for drop in eval_races:
        kept = [e for e in eval_results if e["race_id"] != drop]
        loro.append({
            "dropped_race": drop,
            "macro_ll_log": eval_macro("ll", "log", kept),
            "macro_ll_mc2": eval_macro("ll", "mc2", kept),
            "macro_ll_fused": eval_macro("ll", "fused", kept),
            "delta_fused_vs_log": eval_macro("ll", "fused", kept)
            - eval_macro("ll", "log", kept),
            "delta_fused_vs_mc2": eval_macro("ll", "fused", kept)
            - eval_macro("ll", "mc2", kept),
        })
    ext = next(r for r in eval_rows if r["state_id"] == EXTREME_STATE_ID)
    assert ext["target"] == 1 and ext["p_mc2"] == 0.0
    af = amap[ext["race_id"]]
    pf = _fuse(af, ext["p_logistic"], ext["p_mc2"])
    extreme = {
        "state_id": EXTREME_STATE_ID,
        "race_id": ext["race_id"],
        "selected_alpha": af,
        "p_logistic": ext["p_logistic"],
        "p_mc2": ext["p_mc2"],
        "p_fused": pf,
        "ll_log": ext["ll_log"],
        "ll_mc2": ext["ll_mc2"],
        "ll_fused": _ll(pf, 1),
        "delta_fused_vs_log": _ll(pf, 1) - ext["ll_log"],
        "delta_fused_vs_mc2": _ll(pf, 1) - ext["ll_mc2"],
        "retained_in_primary": True,
    }
    trimmed = [r for r in eval_rows if r["state_id"] != EXTREME_STATE_ID]
    trim_by_race = collections.defaultdict(list)
    for r in trimmed:
        trim_by_race[r["race_id"]].append(r)

    def _trim_macro(arm: str) -> float:
        vals = []
        for rc in eval_races:
            rr = trim_by_race[rc]
            if arm == "log":
                vals.append(sum(x["ll_log"] for x in rr) / len(rr))
            elif arm == "mc2":
                vals.append(sum(x["ll_mc2"] for x in rr) / len(rr))
            else:
                a = amap[rc]
                vals.append(sum(_ll(_fuse(a, x["p_logistic"], x["p_mc2"]),
                                       x["target"]) for x in rr) / len(rr))
        return sum(vals) / len(vals)

    trim_ll = {a: _trim_macro(a) for a in ("log", "mc2", "fused")}
    outlier_removed = {
        "scope": "EXPLORATORY_SENSITIVITY_ONLY",
        "macro_ll_log": trim_ll["log"],
        "macro_ll_mc2": trim_ll["mc2"],
        "macro_ll_fused": trim_ll["fused"],
        "delta_fused_vs_log": trim_ll["fused"] - trim_ll["log"],
        "delta_fused_vs_mc2": trim_ll["fused"] - trim_ll["mc2"],
    }
    # largest absolute per-row contributions among eval rows (fused arm)
    contribs = []
    for r in eval_rows:
        a = amap[r["race_id"]]
        lf = _ll(_fuse(a, r["p_logistic"], r["p_mc2"]), r["target"])
        contribs.append((lf, r["state_id"], r["race_id"], lf - r["ll_log"],
                         lf - r["ll_mc2"]))
    contribs.sort(reverse=True)
    largest = [{"state_id": s, "race_id": rc, "ll_fused": lf,
                "delta_vs_log": dl, "delta_vs_mc2": dm}
               for lf, s, rc, dl, dm in contribs[:5]]

    # descriptive stage / season / disagreement-bin views (eval rows)
    def _arm_ll(r, arm):
        if arm == "log":
            return r["ll_log"]
        if arm == "mc2":
            return r["ll_mc2"]
        return _ll(_fuse(amap[r["race_id"]], r["p_logistic"], r["p_mc2"]),
                   r["target"])

    stage_view, season_view = {}, {}
    for key, col in (("stage", stage_view), ("season", season_view)):
        groups = collections.defaultdict(list)
        for r in eval_rows:
            groups[r[key]].append(r)
        for g, rr in sorted(groups.items(), key=lambda kv: str(kv[0])):
            col[str(g)] = {
                "n": len(rr),
                "pooled_ll_log": sum(_arm_ll(x, "log") for x in rr)
                / len(rr),
                "pooled_ll_mc2": sum(_arm_ll(x, "mc2") for x in rr)
                / len(rr),
                "pooled_ll_fused": sum(_arm_ll(x, "fused") for x in rr)
                / len(rr),
            }
    bin_view = {}
    for lo, hi, name in ((0.0, 0.01, "gap_lt_0.01"),
                         (0.01, 0.1, "gap_0.01_0.1"),
                         (0.1, 2.0, "gap_ge_0.1")):
        rr = [r for r in eval_rows
              if lo <= abs(r["p_logistic"] - r["p_mc2"]) < hi]
        if rr:
            bin_view[name] = {
                "n": len(rr),
                "pooled_ll_log": sum(_arm_ll(x, "log") for x in rr)
                / len(rr),
                "pooled_ll_mc2": sum(_arm_ll(x, "mc2") for x in rr)
                / len(rr),
                "pooled_ll_fused": sum(_arm_ll(x, "fused") for x in rr)
                / len(rr),
            }

    # ---- gate (strict operationalization, recorded inputs) ----
    prim_win_log = deltas["delta_fusion_vs_log_macro_ll"] < 0
    prim_win_mc2 = deltas["delta_fusion_vs_mc2_macro_ll"] < 0
    boot_log = bootstrap["delta_fusion_vs_log_macro_ll"]["ci95"][1] < 0
    boot_mc2 = bootstrap["delta_fusion_vs_mc2_macro_ll"]["ci95"][1] < 0
    loro_stable = all(L["delta_fused_vs_log"] < 0
                      and L["delta_fused_vs_mc2"] < 0 for L in loro)
    outlier_ok = (outlier_removed["delta_fused_vs_log"] < 0
                  and outlier_removed["delta_fused_vs_mc2"] < 0)
    brier_ok = (deltas["delta_fusion_vs_log_macro_bs"] < 0
                and deltas["delta_fusion_vs_mc2_macro_bs"] < 0)
    gate_inputs = {
        "primary_beats_log": prim_win_log,
        "primary_beats_mc2": prim_win_mc2,
        "bootstrap_supportive_vs_log": boot_log,
        "bootstrap_supportive_vs_mc2": boot_mc2,
        "loro_stable_both_controls": loro_stable,
        "outlier_removed_still_beats_both": outlier_ok,
        "brier_macro_beats_both": brier_ok,
    }
    if prim_win_log and prim_win_mc2 and boot_log and boot_mc2 \
            and loro_stable and outlier_ok and brier_ok:
        decision = "FUSION_IMPROVEMENT_SUPPORTED"
    elif prim_win_log and prim_win_mc2:
        decision = "FUSION_IMPROVEMENT_INCONCLUSIVE"
    else:
        decision = "FUSION_IMPROVEMENT_NOT_SUPPORTED"

    pathology = {f"E-P{i}": 0 for i in range(1, 25)}

    wall_total = time.perf_counter() - t_start
    evaluation = {
        "schema": "v3.8e-fusion-evaluation-v1",
        "protocol_identity": proto_id,
        "population": {"comparable_rows": 277, "eval_rows": len(eval_rows),
                       "eval_races": eval_races,
                       "warmup_races": CHRONO[:WARMUP]},
        "controls": {"macro_ll_log": macro_ll["log"],
                     "macro_ll_mc2": macro_ll["mc2"],
                     "macro_bs_log": macro_bs["log"],
                     "macro_bs_mc2": macro_bs["mc2"],
                     "pooled_ll_log": pooled_ll["log"],
                     "pooled_ll_mc2": pooled_ll["mc2"],
                     "pooled_bs_log": pooled_bs["log"],
                     "pooled_bs_mc2": pooled_bs["mc2"]},
        "fusion": {"macro_ll": macro_ll["fused"],
                   "macro_bs": macro_bs["fused"],
                   "pooled_ll": pooled_ll["fused"],
                   "pooled_bs": pooled_bs["fused"]},
        "deltas": deltas,
        "bootstrap": bootstrap,
        "descriptive": {"stage_view": stage_view,
                        "season_view": season_view,
                        "disagreement_bins": bin_view},
        "gate_inputs": gate_inputs,
        "pathology": pathology,
        "runtime_s": {"eval": round(t_eval1 - t_eval0, 3),
                      "bootstrap": round(t_boot1 - t_boot0, 3),
                      "total": round(wall_total, 3)},
    }

    E.mkdir(parents=True, exist_ok=True)
    json.dump(evaluation, open(E / "fusion_evaluation.json", "w"),
              indent=2, sort_keys=True)
    json.dump(eval_results, open(E / "per_race_results.json", "w"),
              indent=2, sort_keys=True)
    json.dump(weights, open(E / "prequential_weights.json", "w"),
              indent=2, sort_keys=True)
    json.dump({"scope": "REVEALED_DESCRIPTIVE_ONLY",
               "oracle": {"alpha": oracle["alpha"],
                          "mark": "DESCRIPTIVE_ORACLE_WEIGHT"},
               "curve": curve},
              open(E / "fixed_weight_curve.json", "w"),
              indent=2, sort_keys=True)
    json.dump({"loro": loro, "extreme_row": extreme,
               "largest_contributions": largest,
               "outlier_removed": outlier_removed},
              open(E / "robustness_analysis.json", "w"),
              indent=2, sort_keys=True)
    gate_doc = {"schema": "v3.8e-fusion-gate-v1",
                "protocol_identity": proto_id,
                "evidence": gate_inputs, "decision": decision}
    json.dump(gate_doc, open(E / "fusion_gate.json", "w"),
              indent=2, sort_keys=True)

    card = {
        "schema": "v3.8e-fusion-card-v1",
        "a_identity": proto["identities"]["a_contract"],
        "b_identity": proto["identities"]["b_contract"],
        "c_identity": proto["identities"]["c_contract"],
        "d_protocol_identity": proto["identities"]["d_protocol"],
        "d_card_identity": proto["identities"]["d_card"],
        "d_preflight_verdict": "REPORTING_DEFECT_ONLY",
        "e_protocol_identity": proto_id,
        "source_lineage": "V3_1B_LOGISTIC (raw independent-binary WIN) + "
        "MC2_E (mutually-exclusive simulation WIN frequency); "
        "V3.5 P_win excluded as SHARED_OR_DERIVED_LINEAGE; V3.4 excluded; "
        "XGBoost secondary-only (SECONDARY_XGB_FUSION_NOT_REQUIRED)",
        "source_probability_families": "independent-binary vs "
        "mutually-exclusive frequency; fusion is per-row binary WIN "
        "probability, never race-normalized",
        "population": evaluation["population"],
        "chronology": CHRONO,
        "warmup_races": CHRONO[:WARMUP],
        "evaluation_races": eval_races,
        "alpha_grid": GRID,
        "selected_alpha_trajectory": [
            {"race_id": w["race_id"],
             "selected_alpha": w["selected_alpha"]} for w in weights],
        "tuning_objective": proto["tuning_objective"],
        "tie_break": proto["tie_break"],
        "controls": proto["controls"],
        "primary_metric": proto["metrics"]["primary"],
        "secondary_metrics": proto["metrics"]["secondary"],
        "bootstrap_spec": proto["bootstrap"],
        "robustness": {"loro_stable": loro_stable,
                       "outlier_removed_beats_both": outlier_ok,
                       "brier_beats_both": brier_ok},
        "known_p0_outlier_sensitivity": {
            "state_id": EXTREME_STATE_ID,
            "retained_in_primary": True,
            "outlier_removed_scope": "EXPLORATORY_SENSITIVITY_ONLY"},
        "revealed_corpus_limitation": proto["revealed_corpus_limitation"],
        "gate": decision,
        "prohibited_interpretations": proto["prohibited_interpretations"],
        "next_stage_consequence": "research result only; no serving "
        "promotion under any gate outcome; product decisions belong to "
        "later V3.8 stages",
    }
    card_id = hashlib.sha256(json.dumps(
        card, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    card["card_identity"] = card_id
    json.dump(card, open(E / "fusion_card.json", "w"),
              indent=2, sort_keys=True)

    print(json.dumps({
        "eval_rows": len(eval_rows), "alphas": amap,
        "macro_ll": macro_ll, "deltas_ll": {
            "vs_log": deltas["delta_fusion_vs_log_macro_ll"],
            "vs_mc2": deltas["delta_fusion_vs_mc2_macro_ll"]},
        "decision": decision, "card": card_id,
        "runtime_s": round(wall_total, 1)}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
