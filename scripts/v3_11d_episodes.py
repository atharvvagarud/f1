#!/usr/bin/env python3
"""V3.11D step 1 -- prior review, interval contract, episode dataset.

Read-only research pass. Emits: prior_vsc_experiment_review.json,
vsc_interval_contract.json, vsc_episode_dataset.csv,
vsc_episode_quality.json.

Deterministic. No production imports. No MC2 execution.

Usage:
    .venv/bin/python scripts/v3_11d_episodes.py
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
OUT = ROOT / "results" / "v3" / "v3_11d"

SEASONS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)
CALIB_SEASONS = (2018, 2019, 2020, 2021)
VALID_SEASONS = (2022, 2023, 2024)


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


def modal_runs(rdf):
    df = rdf.sort_values(["state_time_s", "lap_number", "driver_id"])
    per_t = {}
    for t, grp in df.groupby("state_time_s"):
        toks = [_norm(v) for v in grp["track_state"].tolist()]
        toks = [x for x in toks if x is not None]
        per_t[float(t)] = (Counter(toks).most_common(1)[0][0]
                           if toks else None)
    lap_at = df.groupby("state_time_s")["lap_number"].max().to_dict()
    runs, cur = [], None
    for t in sorted(per_t):
        tok = per_t[t]
        if cur is None or tok != cur["token"]:
            if cur is not None:
                runs.append(cur)
            cur = {"token": tok, "start_s": t, "end_s": t,
                   "entry_lap": lap_at.get(t), "exit_lap": lap_at.get(t)}
        else:
            cur["end_s"] = t
            cur["exit_lap"] = lap_at.get(t)
    if cur is not None:
        runs.append(cur)
    return runs


def main() -> int:
    t0 = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)

    _write("prior_vsc_experiment_review.json", {
        "schema_version": "v3.11d-prior-review-v1",
        "experiments": [
            {
                "id": "V3.2H-VSC",
                "source": "docs/V3_2H_CAUSAL_REGIME_MODELS.md + "
                          "results/v3/v3_2h/ (frozen, read-only)",
                "hypothesis": "VSC admittable via stochastic duration "
                              "model + median pace offset",
                "implementation": "lap-modal episodes; residual-duration "
                                  "survival fit; past-only median pace "
                                  "offset (+19s); AR(1)/dynamics-freeze "
                                  "options",
                "calibration": "past-only per fold (H1 train<=2021/"
                               "eval2022-23; H2 train<=2023/eval2024; "
                               "min cell N=30)",
                "protocol": "prereg a31aec4e; gates duration + during-"
                            "pace + post-exit + gaps; outcomes "
                            "NOT_MEASURABLE_OFFLINE (no simulator pre-"
                            "admission)",
                "result": "REJECT_VSC (duration FAIL/FAIL: slope 2.61 vs "
                          "[0.5,1.5]; pace MAE 10.38/11.58s vs gate "
                          "<=10.0s; post-exit PASS; gaps PASS)",
                "verdict": "REJECTED",
                "reason": "duration uncalibratable at ~55 episodes; "
                          "driver sd ~9s dominates central pace effect",
            },
            {
                "id": "V3.2F-VSC-AUDIT",
                "source": "results/v3/v3_2f/vsc_audit.json (frozen)",
                "hypothesis": "VSC pace process measurable enough to "
                              "motivate modelling",
                "result": "median +19.6s (n=892); 55 lap-level episodes "
                          "p50 1 lap; needs duration/restart/anchor-"
                          "conditioning (all unestimated)",
                "verdict": "DEFERRED (evidence pack, not a model)",
                "reason": "mechanism + estimation missing",
            },
        ],
        "d_differences": [
            "conditional dynamics only: D validates pace/gaps/order/"
            "spread/pit/withdrawal GIVEN causally-known VSC intervals "
            "(C token-run contract with explicit 6/7 withdrawal); H "
            "additionally required predictive duration (P(continues|age))",
            "transition-lap decontamination: D excludes entry/exit laps "
            "from ACTIVE pace windows (pre-declared); H scored all "
            "during-VSC laps including partials",
            "ratio-form pace + race-specific alternative tested "
            "pre-declared against H-comparable absolute gates",
            "duration re-tested independently as integration blocker, "
            "not as a fittable component",
        ],
    })

    _write("vsc_interval_contract.json", {
        "schema_version": "v3.11d-interval-contract-v1",
        "provenance": "V3.11C track-source forensics (token-run intervals; "
                      "no VSC RC category exists)",
        "activation_tokens": ["vsc"],
        "continuation_tokens": ["vsc"],
        "withdrawal_tokens": ["vsc_ending"],
        "green_return": "all_clear following vsc_ending (59/62) or "
                        "directly following vsc (13/82)",
        "equality_semantics": "lap-end clock: token at state_time_s == T "
                              "is observable at T (last-char rule); "
                              "activation >T invisible; withdrawal >T "
                              "invisible until observed",
        "pre_first_message": "UNKNOWN, never GREEN by default",
        "scope": "research input (episode construction + replay "
                 "anchoring); NOT production eligibility",
    })

    d9 = {}
    for season in SEASONS:
        df = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9"
            / f"season={season}"
            / f"driver_lap_state_d9__d9-{season}.parquet")
        for race_id, rdf in df.groupby("race_id"):
            d9[str(race_id)] = (season, rdf)

    episodes = []
    for race_id in sorted(d9):
        season, rdf = d9[race_id]
        runs = modal_runs(rdf)
        for i, r in enumerate(runs):
            if r["token"] != "vsc":
                continue
            prev_tok = runs[i - 1]["token"] if i > 0 else None
            nxt = runs[i + 1] if i + 1 < len(runs) else None
            nxt_tok = nxt["token"] if nxt else "END_OF_DATA"
            withdrawing = nxt_tok == "vsc_ending"
            post = runs[i + 2] if withdrawing and i + 2 < len(runs) else None
            episodes.append({
                "episode_id": f"{race_id}#vsc{i}",
                "race_id": race_id, "season": season,
                "start_s": r["start_s"], "end_s": r["end_s"],
                "duration_s": r["end_s"] - r["start_s"],
                "entry_lap": r["entry_lap"], "exit_lap": r["exit_lap"],
                "n_laps": (r["exit_lap"] - r["entry_lap"] + 1)
                if r["entry_lap"] is not None and r["exit_lap"]
                is not None else None,
                "prev_token": prev_tok, "next_token": nxt_tok,
                "withdrawal_run": withdrawing,
                "post_token": post["token"] if post else None,
                "split": ("calibration" if season in CALIB_SEASONS
                          else "validation"),
            })
    assert len(episodes) == 82, len(episodes)

    # Quality gate (fixed rules, no outcome peeking).
    # Rule v2 (token-semantic, decided before any scoring): ACTIVE laps
    # drop the run ENTRY lap (activation falls mid-lap by construction of
    # last-code-wins) and drop the EXIT lap only on direct vsc->all_clear
    # withdrawal (withdrawal falls mid-exit-lap); when withdrawal is
    # contained in a vsc_ending run, the exit lap ended under VSC and is
    # kept. Strict-interior counts (drop entry+exit always) reported as
    # sensitivity. Rationale: code 7 marks withdrawal onset (C evidence),
    # so only direct withdrawals contaminate the exit lap.
    usable, excluded = [], Counter()
    strict_usable = 0
    for e in episodes:
        reasons = []
        if e["next_token"] == "END_OF_DATA":
            reasons.append("TRUNCATED_ACTIVE_AT_END")
        if e["next_token"] in ("safety_car", "red_flag"):
            reasons.append(f"TRANSITION_INTO_{str(e['next_token']).upper()}")
        if e["prev_token"] in ("safety_car", "red_flag"):
            reasons.append(f"TRANSITION_FROM_{str(e['prev_token']).upper()}")
        n = e["n_laps"] or 0
        drop_exit = e["next_token"] == "all_clear"
        n_active = n - 1 - (1 if drop_exit else 0)
        if n_active < 1:
            reasons.append("NO_FULL_VSC_LAP")
        if reasons:
            for x in reasons:
                excluded[x] += 1
            e["usable"] = False
            e["exclusion"] = ";".join(sorted(set(reasons)))
        else:
            e["usable"] = True
            e["exclusion"] = None
        e["active_rule"] = ("drop_entry"
                            + ("+drop_exit_direct_withdrawal"
                               if drop_exit else ""))
        if n - 2 >= 1 and not reasons:
            strict_usable += 1
        usable.append(e)

    with open(OUT / "vsc_episode_dataset.csv", "w", newline="",
              encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(usable[0].keys()))
        wr.writeheader()
        for e in usable:
            wr.writerow(e)
    n_use = sum(1 for e in usable if e["usable"])
    _write("vsc_episode_quality.json", {
        "schema_version": "v3.11d-episode-quality-v1",
        "n_episodes": len(usable),
        "usable": n_use,
        "unusable": len(usable) - n_use,
        "strict_interior_usable": strict_usable,
        "quality_rule": "v2 token-semantic (drop entry; drop exit iff "
                        "direct vsc->all_clear withdrawal)",
        "quality_rule_rationale": ("code 7 marks withdrawal onset (C); "
                                   "only direct withdrawals contaminate "
                                   "the exit lap; decided before scoring"),
        "exclusions": dict(sorted(excluded.items())),
        "usable_by_split": dict(sorted(Counter(
            e["split"] for e in usable if e["usable"]).items())),
        "window_definitions": {
            "ACTIVE": "driver-lap rows with token vsc strictly inside "
                      "[start_s, end_s], dropping the run entry lap "
                      "always and the exit lap on direct vsc->all_clear "
                      "withdrawal (rule v2); sensitivity on strict "
                      "interior laps",
            "PRE": "up to 3 all_clear laps immediately before start_s, "
                   "same drivers, pit laps excluded for pace metrics",
            "POST": "up to 3 all_clear laps after end_s (after "
                    "vsc_ending run when present), pit laps excluded",
            "contamination": "SC/red-adjacent runs excluded at episode "
                             "level; pit/retirement laps excluded per "
                             "metric (retirement = driver absent all "
                             "later laps: retrospective label, fixed "
                             "before outcome comparison)",
        },
    })
    print(json.dumps({
        "status": "OK", "episodes": len(usable), "usable": n_use,
        "wall_s": round(time.perf_counter() - t0, 1),
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
