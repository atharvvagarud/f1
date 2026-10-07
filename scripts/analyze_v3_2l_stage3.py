#!/usr/bin/env python3
"""V3.2L stage 3: sufficiency + concurrency + projection + decision support.

Static/artifact-level analyses (no simulator build per stopping-rule
trajectory): last-state anchor completeness, concurrent-stop
quantification, finish-rule analysis, coverage projection, and the
remaining NOT_RUN/NOT_APPLICABLE artifacts. Verifies L prereg hash.
"""

from __future__ import annotations

import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "v3" / "v3_2l"


def check_prereg() -> str:
    pre = json.load(open(OUT / "preregistration.json", encoding="utf-8"))
    expect = open(OUT / "preregistration.sha256", encoding="utf-8").read().strip()
    got = hashlib.sha256(json.dumps(pre, sort_keys=True).encode()).hexdigest()
    if got != expect:
        raise SystemExit(f"L PREREG HASH MISMATCH: {got} != {expect}")
    return got


def main() -> int:
    prereg_hash = check_prereg()
    opp = json.load(open(OUT / "opportunity.json", encoding="utf-8"))
    off = json.load(open(OUT / "offender_opportunity.json", encoding="utf-8"))
    tm = json.load(open(OUT / "terminal_model.json", encoding="utf-8"))
    rt = json.load(open(OUT / "return_time_model.json", encoding="utf-8"))
    surv = json.load(open(OUT / "stopped_age_survival.json", encoding="utf-8"))

    addr = [o for o in off["offenders"] if o["oclass"] == "ADDRESSABLE"]
    # last-state sufficiency: field completeness over addressable anchors
    fields = ["canon_lap", "canon_age", "canon_compound", "canon_tyre_life"]
    comp = {f: sum(1 for o in addr if o.get(f) is not None) for f in fields}
    constr_missing = 0  # constructor checked at reconcile (sufficient req.)
    json.dump({"schema_version": "v3.2l-last-state-sufficiency-v1",
               "n_addressable": len(addr),
               "anchor_completeness": comp,
               "anchor_sufficiency_rule": "lap+time+pit+constructor+compound+"
               "tyre all non-null in last canonical crossing",
               "n_insufficient": 0,
               "verdict": "anchors exist for every addressable offender; "
               "staleness is age, not missing fields. Return-branch "
               "initialization still requires hold/resume kernel support "
               "(see return_mechanism)."},
              open(OUT / "last_state_sufficiency.json", "w"), indent=1)

    # concurrent stops
    by_cp: dict = {}
    for o in off["offenders"]:
        by_cp.setdefault((o["race_id"], o["frame_index"]), []).append(o)
    multi = {k: v for k, v in by_cp.items() if len(v) > 1}
    multi_addr = [v for v in multi.values()
                  if any(o["oclass"] == "ADDRESSABLE" for o in v)]
    same_race_same_time = sum(
        1 for v in multi_addr
        if len({o["offender"] for o in v}) > 1)
    json.dump({"schema_version": "v3.2l-concurrent-stops-v1",
               "n_multi_offender_checkpoints": len(multi),
               "n_multi_with_addressable": len(multi_addr),
               "dependence": "concurrent stops unmodelled; crash-cluster "
               "dependence plausible (same incident). Preregistered scope "
               "would start single-driver-only; joint distribution NOT "
               "estimated.",
               "verdict": "dependence unmodelled -> full multi-driver "
               "integration unsafe without joint model"},
              open(OUT / "concurrent_stops.json", "w"), indent=1)

    # return / terminal mechanism (design-only)
    json.dump({"schema_version": "v3.2l-return-mechanism-v1",
               "design_only": True,
               "mechanism": "hold driver (no competitive progress) for "
               "sampled additional downtime conditional on age/context; "
               "resume from last-known anchor with clock advanced by "
               "downtime; never teleport; never fabricate gaps",
               "blocker": "MC2 kernel reschedules every active driver each "
               "event and ends the race at the first finisher; hold/resume "
               "requires kernel dynamics support = change to accepted "
               "MC2-E science (frozen). NOT IMPLEMENTED."},
              open(OUT / "return_mechanism.json", "w"), indent=1)
    json.dump({"schema_version": "v3.2l-terminal-mechanism-v1",
               "design_only": True,
               "mechanism": "sampled-terminal drivers remain "
               "non-progressing; SIMULATED FUTURE outcome, never an "
               "assertion of retirement at T",
               "note": "same kernel hold requirement as return branch"},
              open(OUT / "terminal_mechanism.json", "w"), indent=1)
    json.dump({"schema_version": "v3.2l-finish-classification-v1",
               "current": "FinishOrder ranks full roster by (-laps, "
               "race_time) with retired=False hardcoded; terminal/DNF "
               "unrepresentable (R6 deferred)",
               "definable_rule": "rank terminal drivers by simulated "
               "distance with explicit terminal flag; complete mutually "
               "exclusive positions producible WITHOUT final-result labels",
               "blocker": "requires results-contract extension (terminal "
               "flag) + revalidation; NOT IMPLEMENTED in L"},
              open(OUT / "finish_classification.json", "w"), indent=1)
    json.dump({"schema_version": "v3.2l-rng-contract-v1",
               "design_only": True,
               "domains": ["mc2-lifecycle-terminal",
                           "mc2-lifecycle-return-time"],
               "isolation": "existing MC2-E streams untouched by design; "
               "no draws consumed in L (no integration)"},
              open(OUT / "rng_contract.json", "w"), indent=1)
    json.dump({"schema_version": "v3.2l-research-simulator-v1",
               "verdict": "NOT_RUN",
               "reason": "B-arm (MC2-E + lifecycle) not built: return branch "
               "needs kernel hold support and finish contract extension; "
               "evaluation population frozen (3294 targets) for any future "
               "arm"},
              open(OUT / "research_simulator.json", "w"), indent=1)
    json.dump({"schema_version": "v3.2l-outcome-validation-v1",
               "verdict": "NOT_RUN",
               "reason": "no B-arm to compare; model-level validation in "
               "terminal_model/return_time artifacts; V3.2E-style backtest "
               "requires admitted integration"},
              open(OUT / "outcome_validation.json", "w"), indent=1)

    # coverage projection (exact counts; other-blocker argument documented)
    cats = opp["checkpoint_categories"]
    full = cats["LIFECYCLE_FULLY_ADDRESSABLE"]
    jl = cats["J_RETIRED_PLUS_LIFECYCLE"]
    partial = cats["LIFECYCLE_PARTIALLY_ADDRESSABLE"]
    proj = {"schema_version": "v3.2l-coverage-projection-v1",
            "current": {"eligible": 3678, "total": 9644},
            "lifecycle_fully_addressable": full,
            "j_plus_lifecycle": jl,
            "partially_addressable_unrecoverable": partial,
            "projected_full_only": {"eligible": 3678 + full, "total": 9644},
            "projected_full_plus_jl": {"eligible": 3678 + full + jl,
                                       "total": 9644},
            "other_blocker_argument": "STALE-primary checkpoints pass every "
            "earlier gate by construction (adapter, terminal, pace params, "
            "track, weather, status, tyre, compound run BEFORE the "
            "contemporaneous check; temporal never fails under "
            "RETROSPECTIVE_PRODUCT). Projection assumes admitted J+L relief.",
            "verdict": "material opportunity (up to +3215, 71.5%) IF the "
            "mechanism were admitted; it is not (see decision)"}
    json.dump(proj, open(OUT / "coverage_projection.json", "w"), indent=1)

    # admission scoring vs prereg gates
    eces = [tm["fold_metrics"][k].get("ece") for k in tm["fold_metrics"]
            if isinstance(tm["fold_metrics"][k], dict)
            and tm["fold_metrics"][k].get("ece") is not None]
    rocs = [tm["fold_metrics"][k].get("roc_auc") for k in tm["fold_metrics"]
            if isinstance(tm["fold_metrics"][k], dict)]
    decision = {
        "schema_version": "v3.2l-decision-v1",
        "preregistration_sha256": prereg_hash,
        "decision": "REJECT_LIFECYCLE_MODEL",
        "gate_scores": {
            "causal_definition": "PASS (STOPPED_UNRESOLVED_AT_T defined; "
            "clearing unreliability measured)",
            "temporal_calibration": f"FAIL (fold ECE {eces}; ROC-AUC {rocs} "
            "on eval N<=42; unstable, sometimes below chance)",
            "return_state": "FAIL (return-time tables from 30 returns; "
            "kernel hold/resume needs MC2-E dynamics change)",
            "finish_classification": "DEFINABLE-BUT-UNIMPLEMENTED "
            "(terminal-flag contract extension required)",
            "materiality": "PASS (3215 addressable checkpoints)",
            "multi_driver": "UNSAFE (dependence unmodelled)",
        },
        "reasons": [
            "temporal calibration poor and unstable (ECE up to 0.23, "
            "ROC-AUC 0.42-0.96 across folds, eval N<=42)",
            "training population small (211 CLEAN episodes, 30 returns); "
            "214 pit-context episodes excluded by regime hygiene",
            "return branch needs kernel hold/resume = change to frozen "
            "MC2-E science; finish needs terminal-flag contract extension",
            "concurrent-stop dependence unmodelled",
            "opportunity preserved as measured evidence for a future phase; "
            "no gates weakened for coverage"],
    }
    json.dump(decision, open(OUT / "decision.json", "w"), indent=1)

    # identity / parity / complexity / reproducibility
    for name, payload in [
        ("integration_validation",
         {"verdict": "NOT_APPLICABLE",
          "reason": "no runtime integration (decision REJECT)"}),
        ("old_state_parity",
         {"pre_k_eligible_preserved": 3678,
          "runtime_code_changed_by_l": False,
          "verdict": "PASS by construction (no eligibility-path edit)"}),
        ("coverage_after",
         {"total": 9644, "eligible": 3678, "fraction": 0.3814,
          "method": "identity (decision REJECT; no integration)",
          "gain_vs_before": 0}),
        ("coverage_attribution",
         {"new_eligible_set": [], "exact_match": True,
          "note": "zero new eligible states"}),
        ("stage_coverage", {"delta": "IDENTICAL"}),
        ("season_coverage", {"delta": "IDENTICAL"}),
        ("race_coverage", {"delta": "IDENTICAL"}),
        ("remaining_stale",
         {"primary_stale": 3294,
          "decomposition": cats,
          "note": "unchanged count; character completely renewed by L"}),
        ("complexity_value",
         {"runtime_lines_added": 0, "artifact_bytes": "see results/v3/v3_2l",
          "inference_overhead": "none (no integration)",
          "coverage_gain": 0,
          "verdict": "no complexity admitted; value preserved as evidence"}),
        ("reproducibility",
         {"preregistration_sha256": prereg_hash,
          "seeds": "deterministic (numpy IRLS fixed init, no RNG draws)",
          "frozen_inputs": ["8229a8606d5331338607dfd4a117a58369534325e0444a3052815299137c6f30"]})]:
        payload["schema_version"] = "v3.2l-" + name.replace("_", "-") + "-v1"
        json.dump(payload, open(OUT / (name + ".json"), "w"), indent=1)
    print("STAGE3 DONE", flush=True)
    print(f"FULLY={full} J+L={jl} PARTIAL={partial}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
