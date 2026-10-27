#!/usr/bin/env python3
"""V3.11E step 1 -- VSC duration evidence (offline, read-only).

Builds the duration dataset from frozen D intervals, fits the D1
empirical (Kaplan-Meier) duration distribution on calibration, and
validates remaining-duration queries on validation per the predeclared
E protocol. D2 is constructed only if the predeclared sample bars pass.

Emits: vsc_duration_dataset.csv, vsc_duration_quality.json,
vsc_duration_analysis.json, vsc_duration_validation.json.

Deterministic. No production imports. Zero stochastic futures.

Usage:
    .venv/bin/python scripts/v3_11e_duration.py
"""

from __future__ import annotations

import csv
import json
import math
import time
from collections import Counter, defaultdict
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "results" / "v3" / "v3_11d"
OUT = ROOT / "results" / "v3" / "v3_11e"

QUERY_MARKS = (30.0, 60.0, 120.0)


def _write(name, doc):
    with open(OUT / name, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")


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


def km_fit(durations, censored):
    """Kaplan-Meier survival table. Returns sorted [(t, S(t))]."""
    events = sorted(zip(durations, censored))
    n = len(events)
    at_risk = n
    surv = 1.0
    table = [(0.0, 1.0)]
    i = 0
    while i < n:
        t = events[i][0]
        d = sum(1 for j in range(i, n) if events[j][0] == t
                and not events[j][1])
        c = sum(1 for j in range(i, n) if events[j][0] == t
                and events[j][1])
        if at_risk > 0 and d > 0:
            surv *= (at_risk - d) / at_risk
        table.append((t, surv))
        at_risk -= (d + c)
        i += d + c
    return table


def km_quantile(table, surv_at_e, q):
    """Conditional quantile of remaining time given survival past e.

    Smallest r with S(e+r)/S(e) <= q; None if unreachable.
    """
    if surv_at_e <= 0:
        return None
    e = table_e
    for t, s in table:
        if t < e:
            continue
        if s / surv_at_e <= q:
            return t - e
    return None


def km_surv(table, e):
    s = 1.0
    for t, sv in table:
        if t <= e:
            s = sv
        else:
            break
    return s


table_e = 0.0


def main() -> int:
    t0 = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)
    proto = json.loads((OUT / "evidence_resolution_protocol.json")
                       .read_text(encoding="utf-8"))
    proto_sha = proto["protocol_sha256"]

    with open(D / "vsc_episode_dataset.csv", encoding="utf-8") as fh:
        eps = list(csv.DictReader(fh))
    assert len(eps) == 82, len(eps)

    # Circuit per race (same D9 corpus; descriptive only).
    race_circuit = {}
    for season in (2018, 2019, 2020, 2021, 2022, 2023, 2024):
        df = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9"
            / f"season={season}"
            / f"driver_lap_state_d9__d9-{season}.parquet",
            columns=["race_id", "circuit_id"])
        for rid, grp in df.groupby("race_id"):
            vals = grp["circuit_id"].dropna().unique().tolist()
            race_circuit[str(rid)] = str(vals[0]) if vals else None

    rows = []
    for e in eps:
        nxt = e["next_token"]
        cens = nxt == "END_OF_DATA"
        competing = nxt in ("safety_car", "red_flag")
        try:
            nlaps = int(float(e["n_laps"])) if e["n_laps"] else None
        except (TypeError, ValueError):
            nlaps = None
        rows.append({
            "episode_id": e["episode_id"],
            "race_id": e["race_id"],
            "season": int(e["season"]),
            "circuit_id": race_circuit.get(e["race_id"]),
            "duration_s": float(e["duration_s"]),
            "duration_laps": nlaps,
            "exit_type": nxt,
            "prev_token": e["prev_token"] or None,
            "withdrawal_run": e["withdrawal_run"] == "True",
            "censored": cens,
            "competing_exit": competing,
            "complete_primary": not cens,
            "split": e["split"],
            "d_usable": e["usable"] == "True",
        })
    with open(OUT / "vsc_duration_dataset.csv", "w", newline="",
              encoding="utf-8") as fh:
        wr = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        wr.writeheader()
        for r in rows:
            wr.writerow(r)

    cal = [r for r in rows if r["split"] == "calibration"]
    val = [r for r in rows if r["split"] == "validation"]
    cal_complete = [r for r in cal if r["complete_primary"]]
    val_complete = [r for r in val if r["complete_primary"]]
    censored = [r for r in rows if r["censored"]]
    competing = [r for r in rows if r["competing_exit"]]
    single = [r for r in rows
              if r["duration_laps"] is not None and r["duration_laps"] <= 1]

    _write("vsc_duration_quality.json", {
        "schema_version": "v3.11e-duration-quality-v1",
        "protocol_sha256": proto_sha,
        "n_intervals": len(rows),
        "exit_types": dict(sorted(Counter(
            r["exit_type"] for r in rows).items())),
        "right_censored": len(censored),
        "competing_exits": len(competing),
        "single_lap_or_less": len(single),
        "by_split": {
            "calibration": len(cal),
            "validation": len(val),
            "calibration_complete": len(cal_complete),
            "validation_complete": len(val_complete),
        },
        "season_distribution": dict(sorted(Counter(
            r["season"] for r in rows).items(), key=str)),
        "circuit_distribution": dict(sorted(Counter(
            r["circuit_id"] or "UNKNOWN" for r in rows).items())),
        "duration_s_all": _q([r["duration_s"] for r in rows]),
        "duration_s_complete": _q(
            [r["duration_s"] for r in rows if r["complete_primary"]]),
    })

    # ---- D1: Kaplan-Meier on calibration ----
    table = km_fit([r["duration_s"] for r in cal],
                   [r["censored"] for r in cal])
    cal_durs = sorted(r["duration_s"] for r in cal_complete)
    emp_med = cal_durs[len(cal_durs) // 2] if cal_durs else None

    # D2 gating (predeclared bars).
    per_circuit = Counter(r["circuit_id"] or "UNKNOWN"
                          for r in cal_complete)
    rich_circuits = sum(1 for c in per_circuit.values() if c >= 10)
    d2_allowed = len(cal_complete) >= 50
    d2_circuit_allowed = rich_circuits >= 3
    _write("vsc_duration_analysis.json", {
        "schema_version": "v3.11e-duration-analysis-v1",
        "protocol_sha256": proto_sha,
        "D0_refuse": "control: refuse future VSC continuation; always "
                     "available, confirms blocker",
        "D1_empirical": {
            "method": "Kaplan-Meier on calibration intervals "
                      "(competing exits complete for primary endpoint; "
                      "END_OF_DATA right-censored)",
            "n_fit": len(cal),
            "n_complete": len(cal_complete),
            "n_censored": sum(1 for r in cal if r["censored"]),
            "empirical_median_s": emp_med,
            "km_table": [[round(t, 3), round(s, 4)] for t, s in table],
        },
        "D2_conditional": {
            "allowed": bool(d2_allowed),
            "reason": ("N_cal_complete >= 50 required; "
                       f"observed {len(cal_complete)}"),
            "circuit_class_allowed": bool(d2_circuit_allowed),
            "circuit_class_reason": (">= 3 circuits with >= 10 "
                f"complete durations required; observed {rich_circuits}"),
            "covariate_set_if_allowed": ["elapsed VSC time at T"],
            "fitted": False,
            "note": "D2 not constructed unless predeclared bars pass; "
                    "bars evaluated here from counts only",
        },
    })

    # ---- validation: remaining duration at elapsed marks ----
    global table_e
    aes, hits, widths, n_eval, n_uneval = [], [], [], 0, 0
    per_mark = {}
    for mark in QUERY_MARKS:
        m_ae, m_hit, m_n = [], [], 0
        for r in val_complete:
            if r["duration_s"] <= mark:
                continue
            table_e = mark
            s_e = km_surv(table, mark)
            med_r = km_quantile(table, s_e, 0.5)
            lo_r = km_quantile(table, s_e, 0.9)
            hi_r = km_quantile(table, s_e, 0.1)
            if med_r is None or lo_r is None or hi_r is None:
                n_uneval += 1
                continue
            true_r = r["duration_s"] - mark
            m_ae.append(abs(med_r - true_r))
            m_hit.append(1.0 if lo_r <= true_r <= hi_r else 0.0)
            widths.append(hi_r - lo_r)
            m_n += 1
            n_eval += 1
        per_mark[str(mark)] = {
            "n_queries": m_n,
            "median_ae_s": round(sorted(m_ae)[len(m_ae) // 2], 1)
            if m_ae else None,
            "hit_rate_80": round(sum(m_hit) / len(m_hit), 3)
            if m_hit else None,
        }
        aes.extend(m_ae)
        hits.extend(m_hit)
    med_ae = sorted(aes)[len(aes) // 2] if aes else None
    hit = sum(hits) / len(hits) if hits else None
    dur1 = len(cal_complete) >= 30 and len(val_complete) >= 10
    dur2 = hit is not None and 0.6 <= hit <= 1.0
    dur3 = med_ae is not None and med_ae <= 90.0
    verdict = ("SUPPORTED" if (dur1 and dur2 and dur3)
               else "UNDERPOWERED")
    _write("vsc_duration_validation.json", {
        "schema_version": "v3.11e-duration-validation-v1",
        "protocol_sha256": proto_sha,
        "method": "D1 conditional-survival queries at elapsed marks; "
                  "validation complete episodes active at mark",
        "query_marks_s": list(QUERY_MARKS),
        "n_scored_queries": n_eval,
        "n_unevaluable_queries": n_uneval,
        "per_mark": per_mark,
        "median_ae_s": round(med_ae, 1) if med_ae is not None else None,
        "hit_rate_80": round(hit, 3) if hit is not None else None,
        "interval_width_s": _q(widths),
        "DUR1_sample": bool(dur1),
        "DUR2_calibration": bool(dur2),
        "DUR3_sharpness": bool(dur3),
        "verdict": verdict,
        "refutation": "NOT_APPLICABLE (feasibility question)",
        "stochastic_futures_run": 0,
    })
    print(json.dumps({
        "status": "OK", "n": len(rows), "verdict": verdict,
        "wall_s": round(time.perf_counter() - t0, 1),
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
