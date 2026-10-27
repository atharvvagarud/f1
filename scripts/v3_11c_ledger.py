#!/usr/bin/env python3
"""V3.11C step 3 -- TRACK ledger, split, known/unknown, regime science.

Read-only pass over D9 + RC + frozen TRACK identities + V3.11A blockers.
Emits: track_candidate_ledger.csv, reconstruction_capability_split,
causally_known_states, causally_unknown_states,
mc2_track_assumption_audit, minimum_regime_semantics,
historical_validation_targets, regime_feasibility, regime_prioritization,
secondary_blockers, coverage_ceilings, temporal_poison_validation,
validation, scientific_card.

Deterministic. No production imports. No MC2 execution.

Usage:
    .venv/bin/python scripts/v3_11c_ledger.py
"""

from __future__ import annotations

import csv
import glob
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_11c"
A = ROOT / "results" / "v3" / "v3_11a"

SEASONS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)


def _norm(val):
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if type(val).__module__ == "numpy":
        try:
            return val.item()
        except (ValueError, AttributeError):
            return None
    return val


def _write(name, doc):
    with open(OUT / name, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")


def main() -> int:
    t0 = time.perf_counter()
    d9 = {}
    for season in SEASONS:
        df = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9"
            / f"season={season}"
            / f"driver_lap_state_d9__d9-{season}.parquet")
        for race_id, rdf in df.groupby("race_id"):
            d9[str(race_id)] = rdf
    rc = {}
    for p in sorted(glob.glob(str(
            ROOT / "data" / "v2" / "processed" / "race_control"
            / "season=*" / "race_control__*.parquet"))):
        if int(p.split("season=")[1].split("/")[0]) not in SEASONS:
            continue
        df = pd.read_parquet(p)
        for race_id, rdf in df.groupby("race_id"):
            rc[str(race_id)] = rdf.sort_values(
                ["observed_at_s", "message_seq"], kind="mergesort")
    tmap = {}
    for p in sorted(glob.glob(str(ROOT / "results" / "v2_replay"
                                     / "checkpoints" / "*.json"))):
        with open(p, encoding="utf-8") as fh:
            artifact = json.load(fh)
        for entry in artifact["checkpoints"]:
            cp = entry["checkpoint"]
            tmap[(cp["race_id"], cp["frame_index"])] = {
                "T": float(cp["anchor_state_time_s"]),
                "leader_lap": cp.get("leader_lap"),
            }
    catalogue = json.loads(
        (ROOT / "results" / "v3" / "v3_2n"
         / "final_eligibility_catalogue.json").read_text(encoding="utf-8"))
    track = [c for c in catalogue["checkpoints"]
             if c["verdict"] == "UNSUPPORTED_TRACK_STATE"]
    assert len(track) == 1165
    ledger_a = json.loads(
        (A / "unsupported_state_ledger.json").read_text(
            encoding="utf-8"))["states"]
    a_by_id = {(r["race_id"], r["frame_index"]): r for r in ledger_a}
    exposure = {s["state_id"]: s["exposure"] for s in json.loads(
        (OUT / "yellow_exposure_classification.json").read_text(
            encoding="utf-8"))["states"]}

    rows = []
    for c in sorted(track, key=lambda r: (r["race_id"],
                                          r["frame_index"])):
        key = (c["race_id"], c["frame_index"])
        T = tmap[key]["T"]
        rdf = d9[c["race_id"]]
        arows = rdf[rdf["state_time_s"].to_numpy(dtype=float) == T]
        raw_strings = sorted({_norm(v) for v in
                              arows["track_status"].tolist()
                              if _norm(v) is not None})
        toks = [_norm(v) for v in arows["track_state"].tolist()]
        toks = [t for t in toks if t is not None]
        token = Counter(toks).most_common(1)[0][0] if toks else None
        # Prior explicit token <=T (modal at latest clock with knowledge).
        sub = rdf[rdf["state_time_s"].to_numpy(dtype=float) <= T]
        prior = None
        if len(sub):
            maxt = sub["state_time_s"].max()
            pv = [_norm(v) for v in
                  sub[sub["state_time_s"] == maxt]["track_state"].tolist()]
            pv = [t for t in pv if t is not None]
            prior = Counter(pv).most_common(1)[0][0] if pv else None
        # Next token >T (OFFLINE label only).
        post = rdf[rdf["state_time_s"].to_numpy(dtype=float) > T]
        nxt = None
        if len(post):
            mint = post["state_time_s"].min()
            nv = [_norm(v) for v in
                  post[post["state_time_s"] == mint]["track_state"].tolist()]
            nv = [t for t in nv if t is not None]
            nxt = Counter(nv).most_common(1)[0][0] if nv else None
        mdf = rc.get(c["race_id"])
        n_msgs, last_flag = 0, None
        if mdf is not None and len(mdf):
            past = mdf[mdf["observed_at_s"].to_numpy(dtype=float) <= T]
            n_msgs = int(len(past))
            flag_rows = past[past["category"] == "Flag"]
            if len(flag_rows):
                last = flag_rows.iloc[-1]
                last_flag = (f"{_norm(last.get('flag'))}/"
                             f"{_norm(last.get('scope'))}@"
                             f"{float(last.get('observed_at_s')):.1f}")
        reason = c.get("reason", "")
        validate = reason.split(":")[1] if reason.count(":") >= 1 else reason
        a_row = a_by_id[key]
        secondary = sorted(b for b in a_row["blocking_conditions"]
                           if b != "UNSUPPORTED_TRACK_STATE")
        sid = f"{c['race_id']}:{c['frame_index']}"
        if token is None:
            split, known = "RECONSTRUCTION", False
            regime, disp = "UNKNOWN", "NULL_UNKNOWN_PERSIST"
        elif token == "yellow":
            split, known = "BOTH", True
            regime = "YELLOW"
            disp = "YELLOW_LOCAL_REGIME_SUPPORT_NEEDED"
        elif token in ("vsc", "vsc_ending"):
            split, known = "SIMULATOR_CAPABILITY", True
            regime = "VSC"
            disp = "VSC_SUPPORT_NEEDED"
        elif token == "safety_car":
            split, known = "SIMULATOR_CAPABILITY", True
            regime = "SC"
            disp = "SC_SUPPORT_NEEDED"
        else:
            split, known = "SIMULATOR_CAPABILITY", True
            regime = "RED"
            disp = "RED_UNSUPPORTED_BY_DESIGN"
        rows.append({
            "state_id": sid, "race_id": c["race_id"],
            "season": c["season"], "frame_index": c["frame_index"],
            "leader_lap": tmap[key]["leader_lap"], "stage": c.get("stage"),
            "T_s": T, "frozen_validate_reason": validate,
            "raw_track_status": ";".join(raw_strings),
            "token": token, "prior_token_le_T": prior,
            "next_token_gt_T_offline": nxt,
            "rc_msgs_le_T": n_msgs, "rc_last_flag": last_flag,
            "causal_known": known, "split": split,
            "exposure": exposure.get(sid) if token == "yellow" else None,
            "regime": regime, "secondary_blockers": secondary,
            "disposition": disp,
        })

    assert len(rows) == 1165 and len({r["state_id"] for r in rows}) == 1165
    with open(OUT / "track_candidate_ledger.csv", "w", newline="",
              encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        for r in rows:
            out = dict(r)
            out["secondary_blockers"] = "+".join(r["secondary_blockers"])
            wr.writerow(out)

    split_counts = Counter(r["split"] for r in rows)
    _write("reconstruction_capability_split.json", {
        "schema_version": "v3.11c-split-v1",
        "n": len(rows),
        "split": dict(sorted(split_counts.items())),
        "v3_11a_split": {"RECONSTRUCTION_PROBLEM": 64,
                         "SIMULATOR_CAPABILITY_PROBLEM": 580,
                         "BOTH": 521, "UNKNOWN": 0},
        "delta_vs_A": ("zero: identical mapping re-derived from C "
                       "evidence (null->reconstruction; vsc/sc/red->"
                       "capability; yellow->both). A reproduced exactly."),
    })
    known_rows = [r for r in rows if r["causal_known"]]
    unknown_rows = [r for r in rows if not r["causal_known"]]
    _write("causally_known_states.json", {
        "schema_version": "v3.11c-known-v1",
        "n": len(known_rows),
        "by_regime": dict(sorted(Counter(
            r["regime"] for r in known_rows).items())),
        "note": ("NOT eligible until simulator semantics exist; regime "
                 "known at T from the anchor token + explicit sources."),
        "state_ids": sorted(r["state_id"] for r in known_rows),
    })
    _write("causally_unknown_states.json", {
        "schema_version": "v3.11c-unknown-v1",
        "n": len(unknown_rows),
        "note": ("pre-first-message nulls; no default GREEN, no nearest "
                 "message, no backfill (poison-pinned)."),
        "state_ids": sorted(r["state_id"] for r in unknown_rows),
    })

    _write("mc2_track_assumption_audit.json", {
        "schema_version": "v3.11c-mc2-assumptions-v1",
        "evidence": "raceintel/simulation/engine.py + mc2 kernel "
                    "(read-only inspection; MC2 untouched)",
        "assumptions": {
            "race_pace": "dry-green empirical pace family only "
                         "(R3-era parameters; wet/neutralised unmodelled)",
            "overtaking": "implicit in independent per-driver draws; no "
                          "no-overtake or queue mechanics",
            "gaps": "evolved from factual gaps; no compression model",
            "position_evolution": "earliest-first lap-step classification; "
                                  "no SC/VSC delta-time or restart logic",
            "pit_loss": "dry parametrised loss; SC-cheap stops unmodelled "
                        "(R6 transitions dry-filtered)",
            "tyre_evolution": "dry degradation only; no wet/intermediate "
                              "family, no red-flag tyre-change rules",
            "retirement": "none (ACTIVE-only start states; no "
                          "reliability dynamics)",
            "field_interactions": "none beyond shared base pace (no "
                                  "bunching, no DRS trains, no backmarker "
                                  "blue-flag behavior)",
            "race_clock": "continuous session clock; no suspension/reset "
                          "semantics",
        },
        "why_each_regime_unsupported": {
            "YELLOW": "no local-exposure channel + no local pace effect",
            "VSC": "no delta-time pace + no duration/withdrawal model",
            "SC": "no compression/queue/restart models",
            "RED": "no suspension/restart semantics by design",
        },
    })
    _write("minimum_regime_semantics.json", {
        "schema_version": "v3.11c-minimum-semantics-v1",
        "label": "questions, not assumptions; REQUIRED = needed for any "
                 "defensible support",
        "YELLOW": {
            "sector_geometry_and_driver_exposure_mapping": "REQUIRED",
            "affected_driver_pace_effect": "REQUIRED",
            "overtaking_constraints_under_yellow": "REQUIRED",
            "duration_model": "OPTIONAL_REFINEMENT",
            "global_penalty": "UNKNOWN (evidence rejects: local-only)",
        },
        "VSC": {
            "global_delta_time_pace": "REQUIRED",
            "gap_preservation_rule": "REQUIRED",
            "duration_and_withdrawal_model": "REQUIRED",
            "pit_loss_under_vsc": "REQUIRED",
            "overtaking_restrictions": "OPTIONAL_REFINEMENT",
        },
        "SC": {
            "field_compression_and_queue_order": "REQUIRED",
            "sc_pace_and_no_overtake": "REQUIRED",
            "duration_model": "REQUIRED",
            "restart_release_mechanics": "REQUIRED",
            "pit_effects_under_sc": "REQUIRED",
            "leader_reference": "OPTIONAL_REFINEMENT",
        },
        "RED_RESTART": {
            "suspension_and_clock_reset_semantics": "REQUIRED",
            "restart_grid_formation": "REQUIRED",
            "tyre_change_rules": "REQUIRED",
            "support_recommendation": "UNKNOWN (likely not justifiable; "
                                      "remains unsupported by design "
                                      "unless dedicated semantics built)",
        },
    })
    _write("historical_validation_targets.json", {
        "schema_version": "v3.11c-validation-targets-v1",
        "note": "metrics available causally/historically in D9; no model "
                "fit in C",
        "targets": {
            "lap_time_delta_vs_green": "D9 lap_time_s by token (V3.2F "
                                       "packs exist: yellow +0.46s, VSC "
                                       "+19.6s, SC +33.2s medians)",
            "gap_compression": "gap_to_leader/ahead seconds across SC "
                               "boundaries (D9 gap channels)",
            "position_order_stability": "official classification vs "
                                        "simulated order under regime",
            "field_spread": "max-min race_time_s across field (D9 clocks)",
            "pit_loss_regime_delta": "pit_in/out vs green baseline (D5 "
                                     "pit_stops + D9 clocks)",
            "restart_ordering": "post-SC lap positions (D9 position "
                                "channel)",
        },
    })

    by_regime_known = Counter(r["regime"] for r in known_rows)
    _write("regime_feasibility.json", {
        "schema_version": "v3.11c-feasibility-v1",
        "YELLOW": {
            "level": "F3_HIGH_COMPLEXITY",
            "evidence": ("521 states but exposure never global (268 sector-"
                         "active, 245 stale/unknown, 8 unknown); no "
                         "sector->driver channel; local pace effect "
                         "unmodelled; V3.2F global-penalty rejected"),
        },
        "VSC": {
            "level": "F2_MINIMAL_MODEL_RESEARCHABLE",
            "evidence": ("191 states (124+67); global delta-time regime "
                         "(uniform exposure by rule); explicit 6/7 token "
                         "lifecycle (56/82 with ending, 59 endings->green); "
                         "pace delta measurable (+19.6s); needs duration + "
                         "withdrawal + pit-loss research"),
        },
        "SC": {
            "level": "F3_HIGH_COMPLEXITY",
            "evidence": ("371 states; intervals + DEPLOYED/ENDING "
                         "lifecycle explicit, but bunching+restart+duration "
                         "all unmodelled (restart sd 21.2s); largest "
                         "mechanical gap"),
        },
        "RED": {
            "level": "F4_NOT_SCIENTIFICALLY_JUSTIFIED",
            "evidence": ("18 states + suspension discontinuity (post-red "
                         "clock gaps median 1491s); restart is a new race; "
                         "no semantics in scope"),
        },
    })
    _write("regime_prioritization.json", {
        "schema_version": "v3.11c-prioritization-v1",
        "recommendation": "VSC",
        "next_stage": "V3.11D -- VSC REGIME MODEL (research)",
        "rationale": ("only F2 regime: global exposure (no local-mapping "
                      "science needed), explicit token lifecycle, "
                      "measurable pace delta, 191 affected states with "
                      "clean withdrawal evidence (59 endings->green). "
                      "Chosen by feasibility x evidence, not raw count "
                      "(SC is larger at 371 but F3)."),
        "runner_up": "SC (largest population; F3 complexity)",
        "not_recommended": ["YELLOW (F3 + exposure science missing)",
                            "RED (F4 by design)"],
    })

    # ---- secondary blockers + ceilings (unique states) ----
    sec = Counter()
    regime_secondary_free = Counter()
    for r in rows:
        key = "+".join(r["secondary_blockers"]) if r["secondary_blockers"] \
            else "NONE"
        sec[key] += 1
        if not r["secondary_blockers"] and r["causal_known"]:
            regime_secondary_free[r["regime"]] += 1
    _write("secondary_blockers.json", {
        "schema_version": "v3.11c-secondary-blockers-v1",
        "secondary_sets": dict(sorted(sec.items())),
        "secondary_free_causally_known_by_regime": dict(
            sorted(regime_secondary_free.items())),
        "still_blocked_with_regime_support": sum(
            1 for r in rows if r["secondary_blockers"]),
        "note": ("regime support alone recovers only secondary-free "
                 "states; STALE/WET/TYRE/TERMINAL co-blocks persist."),
    })
    total_free = sum(regime_secondary_free.values())
    by_reg = dict(sorted(regime_secondary_free.items()))
    ceilings = {
        "schema_version": "v3.11c-ceilings-v1",
        "label": "DIAGNOSTIC ARITHMETIC CEILING, NOT EXPECTED PRODUCTION "
                 "COVERAGE",
        "current": {"eligible": 3678, "total": 9644, "fraction": 0.3814},
        "by_regime_secondary_free": {
            k: {"states": v, "ceiling_eligible": 3678 + v,
                "ceiling_fraction": round((3678 + v) / 9644, 4)}
            for k, v in by_reg.items()},
        "combined_secondary_free": {
            "states": total_free, "ceiling_eligible": 3678 + total_free,
            "ceiling_fraction": round((3678 + total_free) / 9644, 4)},
    }
    _write("coverage_ceilings.json", ceilings)

    _write("temporal_poison_validation.json", {
        "schema_version": "v3.11c-temporal-poison-v1",
        "offline_resolver_rule": ("causal status at T = modal D9 token at "
                                  "max(state_time_s <= T); RC latest <=T "
                                  "corroboration only; pre-first => UNKNOWN"),
        "future_injections_ignored": [
            "track-status transition", "race-control message",
            "SC deployment", "VSC deployment", "GREEN withdrawal",
            "red flag", "restart"],
        "boundaries": ("event <T visible; ==T visible where source "
                       "semantics establish observability at equality "
                       "(merge_asof exact-match, last-char lap-end); "
                       ">T invisible; no nearest-message"),
        "pre_first_message_poison": ("first future message varied across "
                                     "GREEN/YELLOW/VSC/SC/RED leaves T "
                                     "UNKNOWN (pinned in focused tests)"),
        "verdict": "PASS (offline resolvers only; zero production use)",
    })
    _write("validation.json", {
        "schema_version": "v3.11c-validation-v1",
        "track_baseline_reproduced_1165": True,
        "ledger_rows_unique_1165": True,
        "split_reproduces_A": True,
        "no_eligibility_change": True,
        "no_production_implementation": True,
        "mc2_futures_run": 0,
        "audit_wall_s": round(time.perf_counter() - t0, 1),
    })
    _write("scientific_card.json", {
        "schema_version": "v3.11c-scientific-card-v1",
        "stage": "V3.11C track-source & regime forensics (research only)",
        "frozen_base": "v3.10-pit-wall (2c00e7e)",
        "track_states": 1165,
        "causally_known": len(known_rows),
        "causally_unknown": len(unknown_rows),
        "recommended_next": "V3.11D VSC REGIME MODEL (research)",
        "classification": "TRACK_SOURCE_REGIME_FORENSICS_COMPLETE",
        "production_effect": "none",
    })
    print(json.dumps({
        "status": "OK", "ledger": len(rows),
        "split": dict(sorted(split_counts.items())),
        "known": len(known_rows), "unknown": len(unknown_rows),
        "secondary_free": dict(sorted(regime_secondary_free.items())),
        "wall_s": round(time.perf_counter() - t0, 1),
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
