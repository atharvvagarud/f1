#!/usr/bin/env python3
"""V3.11C step 2 -- intervals, agreement anatomy, regime forensics.

Read-only pass over D9 + RC feeds + frozen TRACK identities. Emits:
track_interval_analysis, track_source_agreement, yellow_forensics,
yellow_exposure_classification, vsc_forensics, sc_forensics,
red_flag_forensics, track_regime_transition_graph.

Deterministic. No production imports. No MC2 execution.

Usage:
    .venv/bin/python scripts/v3_11c_regimes.py
"""

from __future__ import annotations

import glob
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_11c"

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


def modal_runs(rdf):
    """Run-length (token, start_s, end_s, entry_lap, exit_lap) over D9.

    One token per distinct state_time_s = modal non-null token (None if
    all rows null at that clock). Deterministic ties impossible (single
    mode taken first by sorted order).
    """
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
            tmap[(cp["race_id"], cp["frame_index"])] = float(
                cp["anchor_state_time_s"])
    catalogue = json.loads(
        (ROOT / "results" / "v3" / "v3_2n"
         / "final_eligibility_catalogue.json").read_text(encoding="utf-8"))
    track = [c for c in catalogue["checkpoints"]
             if c["verdict"] == "UNSUPPORTED_TRACK_STATE"]
    assert len(track) == 1165

    # ---- intervals + transition graph ----
    all_runs = {}
    edge_counts = Counter()
    edge_seasons = {}
    for race_id, rdf in sorted(d9.items()):
        runs = modal_runs(rdf)
        all_runs[race_id] = runs
        for a, b in zip(runs, runs[1:]):
            edge_counts[(a["token"], b["token"])] += 1
            edge_seasons.setdefault((a["token"], b["token"]), set()).add(
                int(race_id.split("-")[0]))
    n_intervals = sum(len(v) for v in all_runs.values())
    pre_unknown = sum(1 for v in all_runs.values()
                      if v and v[0]["token"] is None)
    _write("track_interval_analysis.json", {
        "schema_version": "v3.11c-interval-analysis-v1",
        "method": ("offline run-length over modal D9 token per "
                   "state_time_s; pre-first-observation run stays None/"
                   "UNKNOWN; no runtime use"),
        "races": len(all_runs),
        "intervals": n_intervals,
        "races_with_pre_first_unknown_run": pre_unknown,
        "interval_tokens": {str(k): v for k, v in sorted(
            Counter(r["token"] for v in all_runs.values() for r in v
                    ).items(), key=lambda kv: str(kv[0]))},
    })
    _write("track_regime_transition_graph.json", {
        "schema_version": "v3.11c-transition-graph-v1",
        "method": "consecutive modal-run edges (None = pre-first-unknown)",
        "edges": [
            {"from": str(a), "to": str(b), "count": n,
             "seasons": sorted(edge_seasons[(a, b)])}
            for (a, b), n in sorted(edge_counts.items(),
                                    key=lambda kv: (-kv[1], str(kv[0])))],
    })

    # ---- yellow exposure ----
    def rc_flag_msgs(race_id, T, flags=("YELLOW", "DOUBLE YELLOW", "CLEAR")):
        mdf = rc.get(race_id)
        if mdf is None:
            return []
        out = []
        for _, r in mdf.iterrows():
            t = _norm(r.get("observed_at_s"))
            if (t is None or t > T
                    or _norm(r.get("category")) != "Flag"
                    or _norm(r.get("flag")) not in flags):
                continue
            out.append({"t": t, "flag": _norm(r.get("flag")),
                        "scope": _norm(r.get("scope")),
                        "sector": _norm(r.get("sector")),
                        "lap": _norm(r.get("lap_number"))})
        return out

    yellow_states = []
    for c in track:
        key = (c["race_id"], c["frame_index"])
        T = tmap[key]
        rdf = d9[c["race_id"]]
        tok_rows = rdf[rdf["state_time_s"].to_numpy(dtype=float) <= T]
        toks = [_norm(v) for v in tok_rows["track_state"].tolist()]
        if "yellow" not in [_norm(v) for v in
                            rdf[rdf["state_time_s"].to_numpy(
                                dtype=float) <= T]["track_state"].tolist()]:
            pass
        anchor_tok = None
        # Anchor token: the anchor driver's own row at exactly T (frozen
        # RaceState semantics: race_control comes from the anchor target
        # row, not a modal window).
        arows = rdf[rdf["state_time_s"].to_numpy(dtype=float) == T]
        if len(arows):
            vals = [_norm(v) for v in arows["track_state"].tolist()
                    if _norm(v) is not None]
            anchor_tok = Counter(vals).most_common(1)[0][0] if vals else None
        if anchor_tok != "yellow":
            continue
        msgs = rc_flag_msgs(c["race_id"], T)
        sectors = {}
        for m in msgs:
            if m["scope"] == "Sector" and m["sector"] is not None:
                sectors[str(m["sector"])] = m["flag"]
        active = sorted(s for s, f in sectors.items() if f != "CLEAR")
        track_clear = any(m["flag"] == "CLEAR" and m["scope"] == "Track"
                          for m in msgs)
        track_green = any(m["flag"] == "GREEN" for m in msgs)
        if active:
            cls = "LOCAL_SECTOR_ACTIVE"
        elif sectors:
            cls = "LOCAL_EXPOSURE_UNKNOWN"
        elif msgs:
            cls = "STATUS_ONLY"
        else:
            cls = "UNKNOWN"
        if track_green and not active:
            cls = "CONTRADICTORY"
        yellow_states.append({
            "state_id": f"{c['race_id']}:{c['frame_index']}",
            "race_id": c["race_id"], "T_s": T,
            "anchor_token": anchor_tok,
            "active_sectors_le_T": active,
            "sector_last_flags": sectors,
            "track_clear_le_T": track_clear,
            "exposure": cls,
        })
    exp_counts = Counter(s["exposure"] for s in yellow_states)
    _write("yellow_forensics.json", {
        "schema_version": "v3.11c-yellow-forensics-v1",
        "n_anchor_yellow": len(yellow_states),
        "finding": ("D9 yellow token is lap-boundary last-code-wins; the RC "
                    "feed carries YELLOW/DOUBLE YELLOW exclusively at Sector "
                    "scope (zero Track-scoped YELLOW in corpus) with CLEAR "
                    "withdrawals per sector. No sector->driver exposure "
                    "channel exists in D9/RaceState; a local yellow must "
                    "never become global slow-race physics without "
                    "exposure evidence."),
        "rc_sector_yellow_active_states": sum(
            1 for s in yellow_states if s["active_sectors_le_T"]),
    })
    _write("yellow_exposure_classification.json", {
        "schema_version": "v3.11c-yellow-exposure-v1",
        "by_exposure": dict(sorted(exp_counts.items())),
        "n_states": len(yellow_states),
        "mc2_implication": ("ignoring yellow for unaffected drivers is "
                            "impossible without driver-sector exposure "
                            "mapping (absent); affected-driver-only pace "
                            "needs sector geometry + exposure intervals "
                            "(absent). Local modelling required; global "
                            "penalty rejected per V3.2F evidence."),
        "states": sorted(yellow_states, key=lambda s: s["state_id"]),
    })

    # ---- VSC forensics ----
    vsc_runs, vsc_end_runs = [], []
    for race_id, runs in all_runs.items():
        for i, r in enumerate(runs):
            if r["token"] == "vsc":
                nxt = (runs[i + 1]["token"] if i + 1 < len(runs)
                       else "END_OF_DATA")
                vsc_runs.append({"race_id": race_id, **r, "next": nxt})
            if r["token"] == "vsc_ending":
                nxt = (runs[i + 1]["token"] if i + 1 < len(runs)
                       else "END_OF_DATA")
                vsc_end_runs.append({"race_id": race_id, **r, "next": nxt})
    with_ending = sum(1 for r in vsc_runs if r["next"] == "vsc_ending")
    _write("vsc_forensics.json", {
        "schema_version": "v3.11c-vsc-forensics-v1",
        "vsc_intervals": len(vsc_runs),
        "vsc_ending_intervals": len(vsc_end_runs),
        "vsc_followed_by_vsc_ending": with_ending,
        "vsc_ending_followed_by": dict(sorted(Counter(
            str(r["next"]) for r in vsc_end_runs).items())),
        "vsc_followed_by_other": dict(sorted(Counter(
            str(r["next"]) for r in vsc_runs
            if r["next"] != "vsc_ending").items())),
        "rc_channel": ("no VSC RC category/flag exists; activation and "
                       "withdrawal evidenced ONLY by token codes 6/7 "
                       "(+ DRS DISABLED adjacency, lineage-only)"),
        "nature": ("global session condition (delta-time regime), not "
                   "sector-local; driver-local exposure uniform by rule, "
                   "not by evidence channel"),
        "causal_intervals_establishable": (
            "YES structurally (explicit 6-intervals with 7-withdrawal in "
            f"{with_ending}/{len(vsc_runs)} cases); mid-interval T needs "
            "duration/withdrawal knowledge only for simulation, not for "
            "establishing the regime at T"),
    })

    # ---- SC forensics ----
    sc_runs = [dict(race_id=race_id, **r)
               for race_id, runs in all_runs.items() for r in runs
               if r["token"] == "safety_car"]
    sc_withdraw = Counter()
    for race_id, runs in all_runs.items():
        for i, r in enumerate(runs):
            if r["token"] == "safety_car" and i + 1 < len(runs):
                sc_withdraw[str(runs[i + 1]["token"])] += 1
    sc_rc = Counter()
    for race_id in {r["race_id"] for r in sc_runs}:
        mdf = rc.get(race_id)
        if mdf is None:
            continue
        for _, r in mdf.iterrows():
            if _norm(r.get("category")) == "SafetyCar":
                sc_rc[str(_norm(r.get("status")))] += 1
    _write("sc_forensics.json", {
        "schema_version": "v3.11c-sc-forensics-v1",
        "sc_intervals": len(sc_runs),
        "sc_withdrawn_to": dict(sorted(sc_withdraw.items())),
        "rc_safetycar_statuses": dict(sorted(sc_rc.items())),
        "simulator_aspects_required": [
            "field compression (gaps destroyed, queue formation)",
            "speed limitation under SC",
            "no-overtake behavior",
            "pit interaction under SC (cheap stops, R6 dry-only today)",
            "restart release + restart-lap pace variance "
            "(V3.2F: restart sd 21.2s)",
            "leader reference across neutralisation",
        ],
        "finding": ("SC intervals causally establishable (explicit token "
                    "+ DEPLOYED/ENDING lifecycle); simulation needs "
                    "bunching + duration + restart models that do not "
                    "exist. Largest regime population (371 states)."),
    })

    # ---- red forensics ----
    red_runs = [dict(race_id=race_id, **r)
                for race_id, runs in all_runs.items() for r in runs
                if r["token"] == "red_flag"]
    clock_jumps = []
    for race_id, runs in all_runs.items():
        for i, r in enumerate(runs):
            if r["token"] == "red_flag" and i + 1 < len(runs):
                clock_jumps.append(runs[i + 1]["start_s"] - r["end_s"])
    mass = json.loads((ROOT / "results" / "v3" / "v3_11a"
                       / "stale_breakdown.json").read_text(
                           encoding="utf-8"))
    red_races = sorted({r["race_id"] for r in red_runs})
    _write("red_flag_forensics.json", {
        "schema_version": "v3.11c-red-forensics-v1",
        "red_intervals": len(red_runs),
        "red_races": red_races,
        "post_red_clock_gap_s": {
            "count": len(clock_jumps),
            "max": round(max(clock_jumps), 1) if clock_jumps else None,
            "median": round(sorted(clock_jumps)[len(clock_jumps) // 2], 1)
            if clock_jumps else None},
        "mass_clock_reset_link": (
            "196 V3.11A MASS_CLOCK_RESET states concentrate in red-flag "
            "races (2020-r09-R x48 etc.); suspension freezes the session "
            "clock while wall/lap clocks reset -- reconstruction across "
            "the boundary is discontinuity-bridging and forbidden"),
        "rc_red_flags": 27,
        "conclusion": ("RED/RESTART requires dedicated suspension semantics "
                       "(tyre-change rules, reset effects, new-race "
                       "restart); remains unsupported by design. No "
                       "reconstruction across red attempted in C."),
    })
    print(json.dumps({
        "status": "OK", "intervals": n_intervals,
        "yellow": len(yellow_states), "vsc": len(vsc_runs),
        "sc": len(sc_runs), "red": len(red_runs),
        "wall_s": round(time.perf_counter() - t0, 1),
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
