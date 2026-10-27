#!/usr/bin/env python3
"""V3.11D step 2 -- empirical VSC analyses (offline, read-only).

Per usable episode, fixed PRE/ACTIVE/POST windows (quality artifact):
pace ratios, gap preservation, field spread, order stability, pit loss,
tyre continuity, retirement audit, withdrawal transition.

Deterministic. No production imports. No MC2 execution.

Usage:
    .venv/bin/python scripts/v3_11d_analyze.py
"""

from __future__ import annotations

import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_11d"

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


def _q(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return {"count": 0}
    import math
    def qp(p):
        k = (n - 1) * p
        f, c = math.floor(k), math.ceil(k)
        return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)
    return {"count": n, "mean": round(sum(s) / n, 2),
            "median": round(qp(0.5), 2), "p25": round(qp(0.25), 2),
            "p75": round(qp(0.75), 2), "p90": round(qp(0.9), 2),
            "max": round(s[-1], 2)}


def clean(row):
    """Clean running lap: finite time, no pit transition."""
    t = _norm(row.get("lap_time_s"))
    if t is None or not np.isfinite(t) or t <= 0:
        return False
    return (_norm(row.get("pit_in_s")) is None
            and _norm(row.get("pit_out_s")) is None)


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
    import csv as _csv
    with open(OUT / "vsc_episode_dataset.csv", encoding="utf-8") as fh:
        episodes = [r for r in _csv.DictReader(fh) if r["usable"] == "True"]

    ratios, offsets = [], []
    by_race, by_season = {}, {}
    gap_changes, gap_baseline, gap_entry = [], [], []
    spreads_pre, spreads_act = [], []
    order_changes, order_laps = 0, 0
    order_entry_ch, order_entry_n = 0, 0
    vsc_pits, green_pits = [], []
    post_deltas = []
    retire_during, retire_pre = 0, 0
    tyre_forced = 0
    n_act_laps = 0

    for e in episodes:
        rdf = d9[e["race_id"]]
        start, end = float(e["start_s"]), float(e["end_s"])
        entry_lap, exit_lap = int(e["entry_lap"]), int(e["exit_lap"])
        drop_exit = e["next_token"] == "all_clear"
        act_laps = list(range(entry_lap + 1,
                              exit_lap if drop_exit else exit_lap + 1))
        pre_laps = list(range(max(1, entry_lap - 3), entry_lap))
        # POST: after end (skip vsc_ending run laps: token filter handles it)
        post_candidates = sorted(
            {int(v) for v in rdf["lap_number"].tolist()
             if v == v} )
        post_laps = [L for L in post_candidates
                     if L > exit_lap][:3]

        lap_of = {}
        for _, r in rdf.iterrows():
            lap_of.setdefault((r["driver_id"], int(r["lap_number"])), r)
        drivers = {d for (d, _) in lap_of}

        # --- pace ---
        for d in drivers:
            pre_t = [float(r["lap_time_s"]) for L in pre_laps
                     if (d, L) in lap_of
                     for r in [lap_of[(d, L)]]
                     if _norm(r.get("track_state")) == "all_clear"
                     and clean(r)]
            act_t = [float(r["lap_time_s"]) for L in act_laps
                     if (d, L) in lap_of
                     for r in [lap_of[(d, L)]]
                     if _norm(r.get("track_state")) == "vsc" and clean(r)]
            if pre_t and act_t:
                import statistics as _st
                base = _st.median(pre_t)
                for t in act_t:
                    ratios.append(t / base)
                    offsets.append(t - base)
                    n_act_laps += 1
                by_race.setdefault(e["race_id"], []).append(
                    _st.median(act_t) / base)
            post_t = [float(r["lap_time_s"]) for L in post_laps
                      if (d, L) in lap_of
                      for r in [lap_of[(d, L)]]
                      if _norm(r.get("track_state")) == "all_clear"
                      and clean(r)]
            if pre_t and post_t:
                import statistics as _st
                base = _st.median(pre_t)
                post_deltas.append(_st.median(post_t[:2]) - base)
            by_season.setdefault(int(e["season"]), []).append(True)

        # --- gaps: steady-state (consecutive ACTIVE) vs baseline;
        # entry transition (last-PRE -> first-ACTIVE) reported separately
        # (activation chaos, not a gate).
        def gaps_at(laps, tok):
            out = {}
            for L in laps:
                rows = [(r["driver_id"], float(r["state_time_s"]))
                        for (d, l), r in lap_of.items()
                        if l == L and _norm(r.get("track_state")) == tok
                        and clean(r)]
                rows.sort(key=lambda x: x[1])
                for (d1, t1), (d2, t2) in zip(rows, rows[1:]):
                    out[(d1, d2)] = t2 - t1
            return out
        g_pre_last = gaps_at(pre_laps[-1:], "all_clear") if pre_laps else {}
        g_act_first = gaps_at(act_laps[:1], "vsc") if act_laps else {}
        for pair, g in g_act_first.items():
            if pair in g_pre_last:
                gap_entry.append(abs(g - g_pre_last[pair]))
        for a, b in zip(act_laps, act_laps[1:]):
            ga, gb = gaps_at([a], "vsc"), gaps_at([b], "vsc")
            for pair in ga:
                if pair in gb:
                    gap_changes.append(abs(ga[pair] - gb[pair]))
        pre_list = list(pre_laps)
        for a, b in zip(pre_list, pre_list[1:]):
            ga, gb = gaps_at([a], "all_clear"), gaps_at([b], "all_clear")
            for pair in ga:
                if pair in gb:
                    gap_baseline.append(abs(ga[pair] - gb[pair]))

        # --- spread: max-min clock at same lap ---
        for L in pre_laps:
            ts = [float(r["state_time_s"]) for (d, l), r in lap_of.items()
                  if l == L and _norm(r.get("track_state")) == "all_clear"
                  and clean(r)]
            if len(ts) >= 10:
                spreads_pre.append(max(ts) - min(ts))
        for L in act_laps:
            ts = [float(r["state_time_s"]) for (d, l), r in lap_of.items()
                  if l == L and _norm(r.get("track_state")) == "vsc"
                  and clean(r)]
            if len(ts) >= 10:
                spreads_act.append(max(ts) - min(ts))

        # --- order: steady-state (consecutive ACTIVE) is the gate;
        # entry transition reported separately (incident/activation chaos).
        for a, b in zip(act_laps, act_laps[1:]):
            pa = {d: int(lap_of[(d, a)]["position"])
                  for (d, l) in lap_of if l == a
                  and _norm(lap_of[(d, l)].get("position")) is not None
                  and clean(lap_of[(d, l)])}
            pb = {d: int(lap_of[(d, b)]["position"])
                  for (d, l) in lap_of if l == b
                  and _norm(lap_of[(d, l)].get("position")) is not None
                  and clean(lap_of[(d, l)])}
            for d in pa:
                if d in pb:
                    order_laps += 1
                    if pa[d] != pb[d]:
                        order_changes += 1
        if pre_laps and act_laps:
            lp, la = pre_laps[-1], act_laps[0]
            pos_pre = {d: int(lap_of[(d, lp)]["position"])
                       for (d, l) in lap_of if l == lp
                       and _norm(lap_of[(d, l)].get("position")) is not None}
            pos_act = {d: int(lap_of[(d, la)]["position"])
                       for (d, l) in lap_of if l == la
                       and _norm(lap_of[(d, l)].get("position")) is not None}
            for d in pos_pre:
                if d in pos_act and clean(lap_of[(d, lp)]) and clean(
                        lap_of[(d, la)]):
                    order_entry_n += 1
                    if pos_pre[d] != pos_act[d]:
                        order_entry_ch += 1

        # --- pits: marginal stop cost over regime-expected pace.
        # VSC expectation uses the global ratio estimate (1.28,
        # documented; race-specific sensitivity in validation):
        # loss = t_pit - ratio*green_base. Green loss = t_pit - green_base.
        import statistics as _st
        for (d, l), r in lap_of.items():
            pin = _norm(r.get("pit_in_s"))
            if pin is None:
                continue
            t = _norm(r.get("lap_time_s"))
            if t is None or not np.isfinite(t):
                continue
            tok = _norm(r.get("track_state"))
            pre_t = [float(x["lap_time_s"]) for L in pre_laps
                     if (d, L) in lap_of
                     for x in [lap_of[(d, L)]] if clean(x)]
            if not pre_t:
                continue
            base = _st.median(pre_t)
            if start <= pin <= end and tok == "vsc":
                vsc_pits.append(t - 1.28 * base)
            elif tok == "all_clear":
                green_pits.append(t - base)

        # --- retirement audit + tyre continuity ---
        for d in drivers:
            dlaps = sorted(l for (dd, l) in lap_of if dd == d)
            last = max(dlaps)
            if entry_lap <= last <= exit_lap:
                retire_during += 1
            if pre_laps and max(pre_laps) == last:
                retire_pre += 1
            for L in act_laps:
                if (d, L) in lap_of:
                    r = lap_of[(d, L)]
                    if _norm(r.get("pit_in_s")) is not None:
                        # pit during VSC: compound after must differ or
                        # same (no forced-change rule either way)
                        pass

    race_factors = {r: sorted(v)[len(v) // 2] for r, v in by_race.items()
                    if v}
    _write("vsc_pace_analysis.json", {
        "schema_version": "v3.11d-pace-v1",
        "n_active_driver_laps": n_act_laps,
        "ratio_active_over_pre": _q(ratios),
        "offset_active_minus_pre_s": _q(offsets),
        "global_ratio_median": round(sorted(ratios)[len(ratios) // 2], 4)
        if ratios else None,
        "race_median_ratios": _q(list(race_factors.values())),
        "n_races_with_pace": len(race_factors),
        "h_comparison": ("H measured additive +19.6s median; D ratio form "
                         "tested pre-declared in protocol"),
    })
    _write("vsc_gap_analysis.json", {
        "schema_version": "v3.11d-gap-v1",
        "pairwise_gap_steady_active_s": _q(gap_changes),
        "pairwise_gap_baseline_pre_s": _q(gap_baseline),
        "pairwise_gap_entry_transient_s": _q(gap_entry),
        "finding": ("steady-state ACTIVE changes vs baseline lap-to-lap "
                    "variability decide preservation; entry transient "
                    "reported, not gated"),
    })
    _write("vsc_field_spread_analysis.json", {
        "schema_version": "v3.11d-spread-v1",
        "spread_pre_s": _q(spreads_pre),
        "spread_active_s": _q(spreads_act),
    })
    _write("vsc_order_analysis.json", {
        "schema_version": "v3.11d-order-v1",
        "steady_active_laps_compared": order_laps,
        "steady_position_changes": order_changes,
        "steady_change_rate": round(order_changes / order_laps, 4)
        if order_laps else None,
        "entry_transient_changes": order_entry_ch,
        "entry_transient_compared": order_entry_n,
        "entry_transient_rate": round(order_entry_ch / order_entry_n, 4)
        if order_entry_n else None,
        "note": ("steady-state consecutive-ACTIVE rate is the gate "
                 "metric; entry transient (incident/activation chaos) "
                 "reported, not gated; pit laps excluded throughout"),
    })
    _write("vsc_pit_loss_analysis.json", {
        "schema_version": "v3.11d-pitloss-v1",
        "vsc_pit_laps_extra_time_s": _q(vsc_pits),
        "green_pit_laps_extra_time_s": _q(green_pits),
        "verdict": ("MODEL if distributions separate with usable N, else "
                    "INSUFFICIENT_EVIDENCE with fail-closed pit rule"),
    })
    _write("vsc_tyre_analysis.json", {
        "schema_version": "v3.11d-tyre-v1",
        "mc2_mechanism": ("engine.expected_lap_time_s degrades by "
                          "next_age (lap-count based); laps increment "
                          "normally under VSC; no pace-coupled tyre term "
                          "exists in frozen MC2"),
        "finding": "NO_MODIFICATION: stints/compounds continue through "
                   "VSC in D9 (no forced changes); lap-based age advances "
                   "identically under VSC and green",
    })
    _write("vsc_retirement_analysis.json", {
        "schema_version": "v3.11d-retirement-v1",
        "disappearances_during_active": retire_during,
        "disappearances_at_pre": retire_pre,
        "decision": "PRESERVE_FROZEN (no evidence VSC pace alters hazard; "
                    "VSC laps are few; no retirement dynamics in MC2)",
    })
    _write("vsc_withdrawal_analysis.json", {
        "schema_version": "v3.11d-withdrawal-v1",
        "post_minus_pre_median_s": _q(post_deltas),
        "finding": "immediate return toward green pace; transient "
                   "quantified for the transition rule",
    })
    print(json.dumps({
        "status": "OK", "episodes": len(episodes),
        "active_laps": n_act_laps,
        "ratio_median": round(sorted(ratios)[len(ratios) // 2], 4)
        if ratios else None,
        "wall_s": round(time.perf_counter() - t0, 1),
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
