#!/usr/bin/env python3
"""V3.11E step 2 -- gap/spread/ending/pit evidence (offline, read-only).

EQ5 VSC_ENDING test first (quarantine until resolved); then gap/spread
construction with conditional ending inclusion; then pit-loss evidence
(primary + secondary scopes) and the pit-relevance gate (frozen MC2
sources read, never imported).

Emits: vsc_ending_analysis.json, vsc_gap_evidence.json,
vsc_gap_power.json, vsc_field_spread_evidence.json,
vsc_field_spread_power.json, vsc_pit_loss_evidence.json,
vsc_pit_relevance.json.

Deterministic (bootstrap seed=7, B=2000). No production imports.
Zero stochastic futures.

Usage:
    .venv/bin/python scripts/v3_11e_evidence.py
"""

from __future__ import annotations

import csv
import json
import math
import random
import statistics as st
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "results" / "v3" / "v3_11d"
OUT = ROOT / "results" / "v3" / "v3_11e"

SEASONS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)
R_CAL = 1.272
BOOT_B = 2000
BOOT_SEED = 7


def _write(name, doc):
    with open(OUT / name, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")


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


def _q(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return {"count": 0}
    def qp(p):
        k = (n - 1) * p
        f, c = math.floor(k), math.ceil(k)
        return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)
    return {"count": n, "mean": round(sum(s) / n, 2),
            "median": round(qp(0.5), 2), "p25": round(qp(0.25), 2),
            "p75": round(qp(0.75), 2), "p90": round(qp(0.9), 2),
            "max": round(s[-1], 2)}


def clean(row):
    t = _norm(row.get("lap_time_s"))
    if t is None or not np.isfinite(t) or t <= 0:
        return False
    return (_norm(row.get("pit_in_s")) is None
            and _norm(row.get("pit_out_s")) is None)


def med(xs):
    return sorted(xs)[len(xs) // 2] if xs else None


def boot_median_ci(clusters, b=BOOT_B, seed=BOOT_SEED):
    """Episode-cluster bootstrap percentile CI for the pooled median.

    clusters: list of per-episode observation lists (non-empty).
    Resamples episodes with replacement; pools; takes median.
    """
    rng = random.Random(seed)
    k = len(clusters)
    stats = []
    for _ in range(b):
        pool = []
        for _ in range(k):
            pool.extend(clusters[rng.randrange(k)])
        stats.append(med(pool))
    stats.sort()
    lo = stats[int(0.025 * (b - 1))]
    hi = stats[int(0.975 * (b - 1))]
    return round(lo, 4), round(hi, 4)


def boot_ratio_ci(ratios, b=BOOT_B, seed=BOOT_SEED):
    """Bootstrap CI for the median of per-episode ratios."""
    rng = random.Random(seed)
    k = len(ratios)
    stats = sorted(
        med([ratios[rng.randrange(k)] for _ in range(k)])
        for _ in range(b))
    return (round(stats[int(0.025 * (b - 1))], 4),
            round(stats[int(0.975 * (b - 1))], 4))


def load_d9():
    d9 = {}
    for season in SEASONS:
        df = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9"
            / f"season={season}"
            / f"driver_lap_state_d9__d9-{season}.parquet")
        for race_id, rdf in df.groupby("race_id"):
            d9[str(race_id)] = rdf
    return d9


def lap_index(rdf):
    lap_of = {}
    for _, r in rdf.iterrows():
        lap_of.setdefault((r["driver_id"], int(r["lap_number"])), r)
    return lap_of


def windows(e):
    el, xl = int(e["entry_lap"]), int(e["exit_lap"])
    drop_exit = e["next_token"] == "all_clear"
    act = list(range(el + 1, xl if drop_exit else xl + 1))
    pre = list(range(max(1, el - 3), el))
    return pre, act


def main() -> int:
    t0 = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)
    proto = json.loads((OUT / "evidence_resolution_protocol.json")
                       .read_text(encoding="utf-8"))
    proto_sha = proto["protocol_sha256"]
    d9 = load_d9()
    with open(D / "vsc_episode_dataset.csv", encoding="utf-8") as fh:
        eps = [r for r in csv.DictReader(fh) if r["usable"] == "True"]
    valid = [e for e in eps if e["split"] == "validation"]
    assert valid, "validation split empty"

    # ============ EQ5: VSC_ENDING quarantine test ============
    end_err, end_ratios = [], []
    end_eps = 0
    for e in eps:
        if e["withdrawal_run"] != "True":
            continue
        rdf = d9[e["race_id"]]
        lap_of = lap_index(rdf)
        xl = int(e["exit_lap"])
        pre, _ = windows(e)
        laps = sorted({int(v) for v in rdf["lap_number"].tolist()
                       if v == v})
        endlaps = [L for L in laps
                   if xl < L <= xl + 3]
        got = False
        for (d, l), r in lap_of.items():
            if l not in endlaps:
                continue
            if _norm(r.get("track_state")) != "vsc_ending":
                continue
            if not clean(r):
                continue
            base = [float(x["lap_time_s"]) for L in pre
                    if (d, L) in lap_of
                    for x in [lap_of[(d, L)]]
                    if _norm(x.get("track_state")) == "all_clear"
                    and clean(x)]
            if not base:
                continue
            b = st.median(base)
            t = float(r["lap_time_s"])
            end_ratios.append(t / b)
            end_err.append(abs(R_CAL * b - t))
            got = True
        if got:
            end_eps += 1
    n_end = len(end_err)
    mae_end = (sum(end_err) / n_end) if n_end else None
    med_ratio_end = med(end_ratios)
    if n_end < 20:
        eq5 = "INSUFFICIENT_EVIDENCE"
    elif mae_end <= 10.0:
        eq5 = "SAME_DYNAMICS"
    elif abs(med_ratio_end - R_CAL) > 0.10:
        eq5 = "DISTINCT_TRANSITION_DYNAMICS"
    else:
        eq5 = "DISTINCT_TRANSITION_DYNAMICS"
    same = eq5 == "SAME_DYNAMICS"
    _write("vsc_ending_analysis.json", {
        "schema_version": "v3.11e-ending-v1",
        "protocol_sha256": proto_sha,
        "question": "EQ5",
        "method": "pooled MAE of frozen R_cal=1.272 on vsc_ending-lap "
                  "driver laps (driver-PRE base, D method); laps in "
                  "(exit_lap, exit_lap+3] with token vsc_ending",
        "n_ending_driver_laps": n_end,
        "n_contributing_episodes": end_eps,
        "mae_s": round(mae_end, 2) if mae_end is not None else None,
        "median_ratio": round(med_ratio_end, 4)
        if med_ratio_end is not None else None,
        "ratio_dist": _q(end_ratios),
        "verdict": eq5,
        "construction_consequence": (
            "ending laps JOIN active windows for gap/spread"
            if same else
            "D behavior retained: ending laps EXCLUDED (quarantine "
            "holds); no silent merge"),
    })

    ACTIVE_TOKS = {"vsc", "vsc_ending"} if same else {"vsc"}

    def act_extended(e, rdf):
        pre, act = windows(e)
        if not same:
            return pre, act
        xl = int(e["exit_lap"])
        laps = sorted({int(v) for v in rdf["lap_number"].tolist()
                       if v == v})
        extra = [L for L in laps if xl < L <= xl + 3]
        return pre, sorted(set(act) | set(extra))

    # ============ gap evidence (validation gated) ============
    def gap_obs(ep_list):
        per_ep = []
        for e in ep_list:
            rdf = d9[e["race_id"]]
            lap_of = lap_index(rdf)
            _, act = act_extended(e, rdf)

            def gaps(laps):
                out = {}
                for L in laps:
                    rows = [(r["driver_id"], float(r["state_time_s"]))
                            for (d, l), r in lap_of.items()
                            if l == L
                            and _norm(r.get("track_state")) in ACTIVE_TOKS
                            and clean(r)]
                    rows.sort(key=lambda x: x[1])
                    for (d1, t1), (d2, t2) in zip(rows, rows[1:]):
                        out[(d1, d2)] = t2 - t1
                return out
            ep_pairs = []
            for a, b in zip(act, act[1:]):
                if b != a + 1:
                    continue
                ga, gb = gaps([a]), gaps([b])
                for p in ga:
                    if p in gb:
                        ep_pairs.append(abs(ga[p] - gb[p]))
            if ep_pairs:
                per_ep.append(ep_pairs)
        return per_ep

    vgap = gap_obs(valid)
    vall = [x for ep in vgap for x in ep]
    g_med = med(vall)
    g_p90 = (sorted(vall)[int(0.9 * (len(vall) - 1))]
             if vall else None)
    if vgap:
        g_lo, g_hi = boot_median_ci(vgap)
    else:
        g_lo = g_hi = None
    point_pass = (g_med is not None and g_med <= 1.0
                  and g_p90 is not None and g_p90 <= 3.0)
    n_gep = len(vgap)
    if n_gep >= 5 and g_lo is not None and g_lo > 1.0:
        g_verdict = "REFUTED"
    elif (point_pass and n_gep >= 5 and g_hi is not None
          and g_hi <= 1.0):
        g_verdict = "SUPPORTED"
    else:
        g_verdict = "UNDERPOWERED"
    # Full-sample context (diagnostic, not gated).
    fall = [x for ep in gap_obs(eps) for x in ep]
    inc_note = ("included: EQ5 SAME" if same
                else f"excluded: EQ5 {eq5}")
    _write("vsc_gap_evidence.json", {
        "schema_version": "v3.11e-gap-evidence-v1",
        "protocol_sha256": proto_sha,
        "question": "EQ3",
        "construction": "D consecutive-ACTIVE pairs + ending laps "
                        f"({inc_note}); validation split; thresholds "
                        "unchanged (median <= 1.0s, p90 <= 3.0s)",
        "validation_pairs": _q(vall),
        "validation_point_median_s": g_med,
        "validation_point_p90_s": g_p90,
        "full_sample_context_median_s": med(fall),
        "full_sample_context_count": len(fall),
        "full_sample_note": "diagnostic only; gate is validation-only",
    })
    _write("vsc_gap_power.json", {
        "schema_version": "v3.11e-gap-power-v1",
        "protocol_sha256": proto_sha,
        "independent_unit": "episode",
        "contributing_validation_episodes": n_gep,
        "pair_observations": len(vall),
        "effective_N_note": "episodes are the independent unit; pairs "
                            "are observations, never independent N",
        "bootstrap": {"method": "episode-cluster percentile CI",
                      "B": BOOT_B, "seed": BOOT_SEED},
        "median_ci95_s": [g_lo, g_hi],
        "point_gate_pass": bool(point_pass),
        "verdict": g_verdict,
    })

    # ============ spread evidence (validation gated) ============
    def spread_ratios(ep_list):
        out = []
        for e in ep_list:
            rdf = d9[e["race_id"]]
            lap_of = lap_index(rdf)
            pre, act = act_extended(e, rdf)

            def spread(laps, toks):
                vals = []
                for L in laps:
                    ts = [float(r["state_time_s"])
                          for (d, l), r in lap_of.items()
                          if l == L
                          and _norm(r.get("track_state")) in toks
                          and clean(r)]
                    if len(ts) >= 10:
                        vals.append(max(ts) - min(ts))
                return vals
            sp = spread(pre, {"all_clear"})
            sa = spread(act, ACTIVE_TOKS)
            if sp and sa:
                out.append((sum(sa) / len(sa)) / (sum(sp) / len(sp)))
        return out

    vrat = spread_ratios(valid)
    s_med = med(vrat)
    if vrat:
        s_lo, s_hi = boot_ratio_ci(vrat)
    else:
        s_lo = s_hi = None
    s_point = (s_med is not None and 0.8 <= s_med <= 1.25)
    n_sep = len(vrat)
    if (n_sep >= 5 and s_lo is not None and s_hi is not None
            and (s_hi < 0.8 or s_lo > 1.25)):
        s_verdict = "REFUTED"
    elif (s_point and n_sep >= 5 and s_lo is not None
          and s_hi is not None and s_lo >= 0.7 and s_hi <= 1.4):
        s_verdict = "SUPPORTED"
    else:
        s_verdict = "UNDERPOWERED"
    fall_r = spread_ratios(eps)
    _write("vsc_field_spread_evidence.json", {
        "schema_version": "v3.11e-spread-evidence-v1",
        "protocol_sha256": proto_sha,
        "question": "EQ4",
        "construction": "D episode metric (mean ACTIVE / mean PRE, "
                        ">=10-row rule) + ending laps "
                        f"({inc_note}); validation only; no calibration "
                        "mixing; band unchanged [0.8, 1.25]",
        "validation_episode_ratios": _q(vrat),
        "validation_point_median": round(s_med, 4)
        if s_med is not None else None,
        "full_sample_context_median": round(med(fall_r), 4)
        if fall_r else None,
        "full_sample_context_count": len(fall_r),
        "full_sample_note": "diagnostic only; gate is validation-only",
    })
    _write("vsc_field_spread_power.json", {
        "schema_version": "v3.11e-spread-power-v1",
        "protocol_sha256": proto_sha,
        "independent_unit": "episode",
        "contributing_validation_episodes": n_sep,
        "effective_N_note": "one ratio per episode; episodes are N",
        "bootstrap": {"method": "episode percentile CI", "B": BOOT_B,
                      "seed": BOOT_SEED},
        "median_ci95": [s_lo, s_hi],
        "point_gate_pass": bool(s_point),
        "verdict": s_verdict,
    })

    # ============ pit-loss evidence ============
    with open(D / "vsc_episode_dataset.csv", encoding="utf-8") as fh:
        all_eps = list(csv.DictReader(fh))
    primary = [e for e in all_eps if e["usable"] == "True"]
    secondary = [e for e in all_eps
                 if e["next_token"] != "END_OF_DATA"]

    def pit_obs(ep_list):
        inl, outl = [], []
        for e in ep_list:
            rdf = d9[e["race_id"]]
            start, end = float(e["start_s"]), float(e["end_s"])
            el = int(e["entry_lap"])
            pre = list(range(max(1, el - 3), el))
            lap_of = lap_index(rdf)
            for (d, l), r in lap_of.items():
                t = _norm(r.get("lap_time_s"))
                if t is None or not np.isfinite(t):
                    continue
                tok = _norm(r.get("track_state"))
                pin = _norm(r.get("pit_in_s"))
                pout = _norm(r.get("pit_out_s"))
                if pin is None and pout is None:
                    continue
                base_l = [float(x["lap_time_s"]) for L in pre
                          if (d, L) in lap_of
                          for x in [lap_of[(d, L)]] if clean(x)]
                if not base_l:
                    continue
                base = st.median(base_l)
                if (pin is not None and start <= pin <= end
                        and tok == "vsc"):
                    inl.append(t - 1.28 * base)
                if (pout is not None and start <= pout <= end
                        and tok == "vsc"):
                    outl.append(t - 1.28 * base)
        return inl, outl

    p_in, p_out = pit_obs(primary)
    s_in, s_out = pit_obs(secondary)
    def ci_width(xs):
        if len(xs) < 3:
            return None
        rng = random.Random(BOOT_SEED)
        ss = sorted(med([xs[rng.randrange(len(xs))]
                         for _ in range(len(xs))])
                    for _ in range(BOOT_B))
        lo = ss[int(0.025 * (BOOT_B - 1))]
        hi = ss[int(0.975 * (BOOT_B - 1))]
        return round(hi - lo, 2)
    bar = (len(p_out) >= 15 and len(p_in) >= 30
           and (ci_width(p_in) or 9e9) <= 5.0)
    _write("vsc_pit_loss_evidence.json", {
        "schema_version": "v3.11e-pit-evidence-v1",
        "protocol_sha256": proto_sha,
        "question": "EQ6",
        "method": "D in-lap method replicated exactly (1.28 documented "
                  "ratio); out-lap marginals added (pit_out_s in window "
                  "+ token vsc)",
        "primary_usable29": {
            "in_lap": _q(p_in),
            "out_lap": _q(p_out),
            "in_lap_median_ci_width_s": ci_width(p_in),
        },
        "secondary_all_nontruncated": {
            "in_lap": _q(s_in),
            "out_lap": _q(s_out),
            "note": "diagnostic; exit type does not contaminate the VSC "
                    "token run itself",
        },
        "d_comparison_in_lap_count": 73,
        "full_loss_bar": "out N>=15 AND in N>=30 AND in-lap median CI "
                         "width <= 5s (primary scope)",
        "bar_met": bool(bar),
        "verdict": ("PIT_LOSS_MODELABLE" if bar
                    else "PIT_LOSS_INSUFFICIENT_EVIDENCE"),
    })

    # ============ pit relevance + MC2 horizon (read-only sources) ===
    sim = ROOT / "raceintel" / "simulation"
    markers = {
        "engine_forward_stepping": ("engine.py", "_schedule_next"),
        "engine_event_trace": ("engine.py", "_trace_event"),
        "engine_pit_state": ("engine.py", "pit_count"),
        "params_pit_loss": ("params.py", "pit_effective_loss_s"),
        "params_pit_penalties": ("params.py", "pit_in_lap_penalty_s"),
        "mc_pit_set": ("monte_carlo.py", "class PitParameterSet"),
        "mc_pit_select": ("monte_carlo.py", "def select_pit_parameters"),
    }
    hits = {}
    for key, (fname, needle) in markers.items():
        text = (sim / fname).read_text(encoding="utf-8")
        lines = [i + 1 for i, ln in enumerate(text.splitlines())
                 if needle in ln]
        hits[key] = {"file": f"raceintel/simulation/{fname}",
                     "needle": needle, "lines": lines[:6],
                     "present": bool(lines)}
    fwd = hits["engine_forward_stepping"]["present"]
    pitmech = all(hits[k]["present"] for k in
                  ("engine_pit_state", "params_pit_loss",
                   "mc_pit_set", "mc_pit_select"))
    _write("vsc_pit_relevance.json", {
        "schema_version": "v3.11e-pit-relevance-v1",
        "protocol_sha256": proto_sha,
        "question": "EQ1/EQ7",
        "method": "read-only text search of frozen MC2 sources "
                  "(no import, no execution, no modification)",
        "markers": hits,
        "mc2_steps_beyond_T": bool(fwd),
        "mc2_simulates_pits_forward": bool(pitmech),
        "EQ1_mapping": ("B HOLDS: MC2 builds a forward kernel from T "
                        "and steps laps beyond factual time; A holds "
                        "only for anchoring/replay AT T"
                        if fwd else
                        "UNDETERMINED: forward-stepping marker absent"),
        "EQ7_relevance": ("pit semantics MANDATORY: MC2 samples pit "
                          "targets and applies pit losses forward from "
                          "T; no T-knowable pit-free scope exists "
                          "without predicting future pits"
                          if pitmech else
                          "pit scope undetermined from markers"),
        "verdict": ("PIT_MANDATORY_BLOCKER_RETAINED" if pitmech
                    else "PIT_RELEVANCE_UNDETERMINED"),
    })
    print(json.dumps({
        "status": "OK", "eq5": eq5, "gap": g_verdict,
        "spread": s_verdict, "wall_s": round(time.perf_counter() - t0, 1),
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

