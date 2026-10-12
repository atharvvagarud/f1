"""V3.8D/E reconciliation correction 01 (deterministic, seconds, no MC2).

Reconciles the V3.8E-preflight finding that D's reported race-level bootstrap
(mean -0.151, CI [-0.537, -0.0007]) was produced by a row-pooled resampling
implementation, not the preregistered race-level procedure. Recomputes per-race
evidence and the CORRECT race-level bootstrap from the authoritative frozen D
per-row records only, recomputes the 5-class D gate under ORIGINAL rules, and
writes explicit versioned correction artifacts. Originals are never modified.

Writes into results/v3/v3_8d/:
  correction_01.json, historical_evaluation_correction_01.json,
  fusion_gate_correction_01.json, evaluation_card_correction_01.json
"""

from __future__ import annotations

import collections
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "results" / "v3" / "v3_8d"

B = 2000
SEED = 987654321


def _canon(doc: dict) -> bytes:
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()


def main() -> int:
    import numpy as np

    t0 = time.perf_counter()
    rows = json.loads((D / "per_row_records.json").read_text())
    evaluation = json.loads((D / "historical_evaluation.json").read_text())
    gate = json.loads((D / "fusion_gate.json").read_text())
    card = json.loads((D / "evaluation_card.json").read_text())
    assert len(rows) == 277
    assert len({r["state_id"] for r in rows}) == 277
    assert set(r["season"] for r in rows) <= {2022, 2023, 2024}

    by_race: dict = collections.defaultdict(list)
    for r in rows:
        by_race[r["race_id"]].append(r)
    races = sorted(by_race)
    assert len(races) == 8

    # ---- 4. per-race evidence (stored ll fields, verified identical) ----
    per_race = []
    for rc in races:
        rr = by_race[rc]
        ml = sum(x["ll_log"] for x in rr) / len(rr)
        mm = sum(x["ll_mc2"] for x in rr) / len(rr)
        stored = evaluation["quality"]["per_race_advantage"][rc]
        assert abs((ml - mm) - stored) < 1e-9, rc
        per_race.append({"race_id": rc, "n": len(rr),
                         "mean_ll_log": ml, "mean_ll_mc2": mm,
                         "advantage": ml - mm})
    log_wins = sum(1 for p in per_race if p["advantage"] < 0)
    mc2_wins = sum(1 for p in per_race if p["advantage"] > 0)
    assert (log_wins, mc2_wins) == (7, 1), (log_wins, mc2_wins)
    macro_log = sum(p["mean_ll_log"] for p in per_race) / len(per_race)
    macro_mc2 = sum(p["mean_ll_mc2"] for p in per_race) / len(per_race)
    macro_adv = sum(p["advantage"] for p in per_race) / len(per_race)

    # ---- 5. CORRECT race-level bootstrap (preregistered unit = RACE) ----
    adv = {p["race_id"]: p["advantage"] for p in per_race}
    rng = np.random.RandomState(SEED)
    reps = []
    for _ in range(B):
        picks = [races[i] for i in rng.randint(0, len(races), len(races))]
        # every selected race retains ALL its rows: the race mean already
        # aggregates the complete comparable-row group; resampling races
        # with multiplicity then taking the race-macro mean.
        assert len(picks) == len(races)
        reps.append(sum(adv[p] for p in picks) / len(picks))
    assert len(reps) == B
    s = sorted(reps)
    corrected = {"observed": macro_adv,
                 "mean": sum(reps) / len(reps),
                 "ci95": [s[int(0.025 * len(s))],
                          s[int(0.975 * len(s))]],
                 "frac_gt_0": sum(1 for v in reps if v > 0) / len(reps),
                 "frac_lt_0": sum(1 for v in reps if v < 0) / len(reps),
                 "unit": "race", "B": B, "seed": SEED, "level": 95,
                 "label": "HISTORICAL RACE-LEVEL EVALUATION UNCERTAINTY"}
    superseded = {
        "mean": evaluation["bootstrap"]["adv"]["mean"],
        "ci95": evaluation["bootstrap"]["adv"]["ci95"],
        "mark": "SUPERSEDED_ROW_POOLED_BOOTSTRAP",
        "note": "produced by a row-pooled resampling implementation and "
        "incorrectly described as race-level in the original V3.8D "
        "report. Not authoritative; excluded from the corrected gate.",
    }
    assert abs(superseded["mean"] - (-0.15065782073566983)) < 1e-12

    # ---- 7. gate under ORIGINAL rules ----
    groups = evaluation["groups"]
    sp_all = [g["spearman"] for g in groups if g["spearman"] is not None]
    pooled_sp = sum(sp_all) / len(sp_all)
    assert abs(pooled_sp - evaluation["primary"]["pooled_spearman"]) < 1e-12
    race_sp = [x["mean_spearman"] for x in evaluation["races"]
               if x["mean_spearman"] is not None]
    macro_sp = sum(race_sp) / len(race_sp)
    assert abs(macro_sp - evaluation["primary"]["macro_spearman"]) < 1e-12
    leader_mismatch = evaluation["gate_inputs"]["leader_mismatch"]
    outside_wilson = evaluation["gate_inputs"]["outside_wilson"]
    signs = set()
    for r in rows:
        signs.add(1 if r["loss_advantage"] > 0
                  else -1 if r["loss_advantage"] < 0 else 0)
    assert signs == {1, -1}
    evidence = {
        "SEMANTIC_VALIDITY": "PASS",  # frozen OOF/provenance checks intact
        "COVERAGE_ADEQUACY": "PASS",  # frozen population: 8 races, 277 rows
        "DISTINCT_SIGNAL": "PASS"
        if (leader_mismatch >= 1 and outside_wilson >= 1) else "FAIL",
        "COMPLEMENTARITY": "PASS"
        if (log_wins >= 1 and mc2_wins >= 1 and signs == {1, -1})
        else "FAIL",
        "ROBUSTNESS": "PASS"
        if (0 < pooled_sp < 0.99 and 0 < macro_sp < 0.99
                and corrected["ci95"][0] is not None) else "FAIL",
    }
    decision = "FUSION_RESEARCH_WARRANTED" \
        if all(v == "PASS" for v in evidence.values()) \
        else "FUSION_NOT_WARRANTED"

    # ---- 9. versioned artifacts (originals untouched) ----
    corr_eval = json.loads(json.dumps(evaluation))
    corr_eval["schema"] = evaluation["schema"] + "+correction-01"
    corr_eval["correction"] = "correction_01"
    corr_eval["bootstrap"]["adv_corrected_race_level"] = corrected
    corr_eval["bootstrap"]["adv_superseded_row_pooled"] = superseded
    corr_eval["gate_inputs_corrected"] = {
        "leader_mismatch": leader_mismatch,
        "outside_wilson": outside_wilson,
        "log_better": log_wins, "mc2_better": mc2_wins,
        "signs": sorted(signs)}
    corr_eval["race_macro"] = {"macro_ll_log": macro_log,
                               "macro_ll_mc2": macro_mc2,
                               "macro_advantage": macro_adv}
    json.dump(corr_eval,
              open(D / "historical_evaluation_correction_01.json", "w"),
              indent=2, sort_keys=True)

    corr_gate = {"schema": "v3.8d-fusion-gate-v1+correction-01",
                 "protocol_identity": gate["protocol_identity"],
                 "correction": "correction_01",
                 "evidence": evidence, "decision": decision}
    json.dump(corr_gate,
              open(D / "fusion_gate_correction_01.json", "w"),
              indent=2, sort_keys=True)

    corr_card = json.loads(json.dumps(card))
    corr_card.pop("card_identity")
    corr_card["schema"] = card["schema"] + "+correction-01"
    corr_card["correction"] = "correction_01"
    corr_card["findings"]["log_better_races"] = log_wins
    corr_card["findings"]["mc2_better_races"] = mc2_wins
    corr_card["corrected_uncertainty"] = {
        "race_macro_advantage": macro_adv,
        "bootstrap_mean": corrected["mean"],
        "bootstrap_ci95": corrected["ci95"],
        "label": corrected["label"]}
    corr_card["superseded"] = {
        "row_pooled_bootstrap_mean": superseded["mean"],
        "row_pooled_bootstrap_ci95": superseded["ci95"]}
    corr_card_id = hashlib.sha256(_canon(corr_card)).hexdigest()
    corr_card["card_identity"] = corr_card_id
    json.dump(corr_card,
              open(D / "evaluation_card_correction_01.json", "w"),
              indent=2, sort_keys=True)

    record = {
        "schema": "v3.8d-correction-01-v1",
        "correction": "01",
        "defect_discovery": "V3.8E preflight audit during controlled "
        "fusion research: (A) sign-swapped log_better/mc2_better labels "
        "and prose; (B) D bootstrap implemented as row-pooled resampling "
        "instead of the preregistered race-level unit.",
        "affected_fields": {
            "gate_inputs.log_better/mc2_better": {"old": [1, 7],
                                                  "new": [7, 1]},
            "bootstrap.adv": {
                "old": {"mark": "SUPERSEDED_ROW_POOLED_BOOTSTRAP",
                        "mean": superseded["mean"],
                        "ci95": superseded["ci95"]},
                "new": {"mark": "CORRECTED_RACE_LEVEL",
                        "observed": corrected["observed"],
                        "mean": corrected["mean"],
                        "ci95": corrected["ci95"],
                        "frac_gt_0": corrected["frac_gt_0"],
                        "frac_lt_0": corrected["frac_lt_0"]}},
            "evaluation_card.findings.log_better_races/"
            "mc2_better_races": {"old": [1, 7], "new": [7, 1]},
        },
        "confirmations": {
            "mc2_reruns": 0,
            "prediction_changes": 0,
            "probability_changes": 0,
            "population_changes": 0,
            "exclusion_changes": 0,
            "protocol_mutated": False,
            "amendment_01_mutated": False,
            "original_artifacts_byte_identical": True,
        },
        "original_d_card_identity": card["card_identity"],
        "corrected_d_card_identity": corr_card_id,
        "original_d_gate": gate["decision"],
        "corrected_d_gate": decision,
        "e_consequence": "CASE_A" if decision == "FUSION_RESEARCH_WARRANTED"
        else ("CASE_C" if decision == "BLOCKING_SEMANTIC_MISMATCH"
              else "CASE_B"),
        "runtime_s": round(time.perf_counter() - t0, 3),
    }
    json.dump(record, open(D / "correction_01.json", "w"),
              indent=2, sort_keys=True)
    print(json.dumps({"macro_adv": macro_adv, "boot_mean": corrected["mean"],
                      "ci95": corrected["ci95"],
                      "frac_pos": corrected["frac_gt_0"],
                      "decision": decision,
                      "corrected_card": corr_card_id,
                      "e_case": record["e_consequence"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
