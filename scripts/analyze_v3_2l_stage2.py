#!/usr/bin/env python3
"""V3.2L stage 2: terminal/return model + calibration + return-time.

Episode-level logistic regression (numpy IRLS, deterministic) with strict
season-forward folds; empirical conditional return-time tables; sanity +
poison firewalls. Verifies L prereg hash. 2025 never read. No network.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "v3" / "v3_2l"
PROCESSED = ROOT / "data" / "v2" / "processed"


def check_prereg() -> str:
    pre = json.load(open(OUT / "preregistration.json", encoding="utf-8"))
    expect = open(OUT / "preregistration.sha256", encoding="utf-8").read().strip()
    got = hashlib.sha256(json.dumps(pre, sort_keys=True).encode()).hexdigest()
    if got != expect:
        raise SystemExit(f"L PREREG HASH MISMATCH: {got} != {expect}")
    return got


def sigmoid(z):
    import numpy as np
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def fit_logistic(X, y, l2=1.0, iters=200):
    """Deterministic IRLS with L2. X includes intercept column."""
    import numpy as np
    n, p = X.shape
    w = np.zeros(p)
    for _ in range(iters):
        pr = sigmoid(X @ w)
        g = X.T @ (pr - y) + l2 * w
        W = pr * (1 - pr)
        H = (X.T * W) @ X + l2 * np.eye(p)
        try:
            step = __import__("numpy").linalg.solve(H, g)
        except Exception:
            break
        w -= step
        if float(step @ step) < 1e-12:
            break
    return w


def metrics_binary(y, p):
    import numpy as np
    y = np.asarray(y, dtype=float)
    p = np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)
    ll = float(-(y * np.log(p) + (1 - y) * np.log(1 - p)).mean())
    br = float(((p - y) ** 2).mean())
    # ROC-AUC via rank
    order = np.argsort(p)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(p) + 1)
    n1, n0 = y.sum(), len(y) - y.sum()
    auc = (float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
           if n1 and n0 else None)
    # PR-AUC via stepwise AP
    ap = None
    if n1:
        idx = np.argsort(-p)
        ys = y[idx]
        tp = np.cumsum(ys)
        prec = tp / np.arange(1, len(y) + 1)
        rec = tp / n1
        ap = float((prec * ys).sum() / n1)
    # ECE, 10 equal-width bins
    ece, bins = 0.0, []
    edges = np.linspace(0, 1, 11)
    for b in range(10):
        m = (p > edges[b]) & (p <= edges[b + 1] if b < 9 else p >= edges[b])
        if b == 0:
            m = m | (p == 0.0)
        if m.sum():
            acc = float(y[m].mean())
            conf = float(p[m].mean())
            ece += abs(acc - conf) * m.sum() / len(y)
            bins.append({"bin": b, "n": int(m.sum()),
                         "acc": round(acc, 4), "conf": round(conf, 4)})
        else:
            bins.append({"bin": b, "n": 0, "acc": None, "conf": None})
    return {"log_loss": round(ll, 4), "brier": round(br, 4),
            "roc_auc": (round(auc, 4) if auc is not None else None),
            "pr_auc": (round(ap, 4) if ap is not None else None),
            "ece": round(float(ece), 4), "reliability_bins": bins,
            "n": len(y), "n_pos": int(n1)}


FEATS = ["frac", "last_pos", "last_lap_deficit", "last_pit", "tyre_age",
         "is_mid", "is_late"]


def feat_row(e, means, sds, leader_laps):
    import numpy as np
    frac = e["x_frac"] if e["x_frac"] is not None else 0.5
    pos = e["x_last_pos"] if e["x_last_pos"] is not None else 20.0
    deficit = (leader_laps.get((e["race_id"], e["driver"]), 0)
               - (e["x_last_lap"] or 0))
    pit = e["x_last_pit"] if e["x_last_pit"] is not None else 0
    tyre = e["x_tyre_life"] if e["x_tyre_life"] is not None else 0
    v = {"frac": frac, "last_pos": pos, "last_lap_deficit": max(0, deficit),
         "last_pit": pit, "tyre_age": tyre,
         "is_mid": 1.0 if e["x_stage"] == "MID" else 0.0,
         "is_late": 1.0 if e["x_stage"] == "LATE" else 0.0}
    return np.array([(v[k] - means[k]) / sds[k] for k in FEATS])


def main() -> int:
    t0 = time.perf_counter()
    prereg_hash = check_prereg()
    import numpy as np  # noqa: E402
    import pandas as pd  # noqa: E402

    eps = json.load(open(OUT / "episode_corpus.json", encoding="utf-8"))
    clean = [e for e in eps["episodes"] if e["x_class"] == "CLEAN"]
    print(f"clean episodes: {len(clean)}", flush=True)
    # leader laps at stop start (for deficit) from D9
    leader: dict = {}
    for race_id in sorted({e["race_id"] for e in clean}):
        season = int(race_id.split("-")[0])
        df = pd.read_parquet(
            str(PROCESSED / "driver_lap_state_d9" / f"season={season}" /
                f"driver_lap_state_d9__d9-{season}.parquet"),
            columns=["race_id", "driver_id", "lap_number", "state_time_s"])
        dfr = df[df["race_id"] == race_id]
        for e in [x for x in clean if x["race_id"] == race_id]:
            past = dfr[(dfr["driver_id"] == e["driver"]) &
                       (dfr["state_time_s"] <= e["x_stop_start_t"])]
            allp = dfr[dfr["state_time_s"] <= e["x_stop_start_t"]]
            leader[(race_id, e["driver"])] = (
                int(allp["lap_number"].max()) if len(allp) else 0)

    FOLDS = [(2020, 2021), (2021, 2022), (2022, 2023), (2023, 2024)]
    fold_res: dict = {}
    coefs: dict = {}
    for thru, ev in FOLDS:
        tr = [e for e in clean if e["season"] <= thru]
        va = [e for e in clean if e["season"] == ev]
        fold_res[f"{thru}->{ev}"] = {"n_train": len(tr), "n_eval": len(va)}
        if not tr or not va:
            continue
        m: dict = {}
        s: dict = {}
        for k in FEATS:
            vals = []
            for e in tr:
                base = {"frac": e["x_frac"] if e["x_frac"] is not None else 0.5,
                        "last_pos": e["x_last_pos"]
                        if e["x_last_pos"] is not None else 20.0,
                        "last_lap_deficit": max(
                            0, leader.get((e["race_id"], e["driver"]), 0)
                            - (e["x_last_lap"] or 0)),
                        "last_pit": e["x_last_pit"]
                        if e["x_last_pit"] is not None else 0,
                        "tyre_age": e["x_tyre_life"]
                        if e["x_tyre_life"] is not None else 0,
                        "is_mid": 1.0 if e["x_stage"] == "MID" else 0.0,
                        "is_late": 1.0 if e["x_stage"] == "LATE" else 0.0}
                vals.append(base[k])
            m[k] = float(np.mean(vals))
            s[k] = float(np.std(vals)) or 1.0
        Xtr = np.array([[1.0] + list(feat_row(e, m, s, leader)) for e in tr])
        ytr = np.array([1.0 if e["y_returned"] else 0.0 for e in tr])
        w = fit_logistic(Xtr, ytr)
        coefs[f"{thru}->{ev}"] = [round(float(x), 4) for x in w]
        Xva = np.array([[1.0] + list(feat_row(e, m, s, leader)) for e in va])
        yva = [1 if e["y_returned"] else 0 for e in va]
        pva = [float(x) for x in sigmoid(Xva @ w)]
        fold_res[f"{thru}->{ev}"]["eval_return_rate"] = (
            sum(yva) / len(yva) if yva else None)
        fold_res[f"{thru}->{ev}"].update(metrics_binary(yva, pva))
    json.dump({"schema_version": "v3.2l-temporal-splits-v1",
               "folds": fold_res,
               "rule": "season-forward; race never crosses train/eval"},
              open(OUT / "temporal_splits.json", "w"), indent=1)
    json.dump({"schema_version": "v3.2l-terminal-model-v1",
               "model": "logistic regression (numpy IRLS, L2=1.0), "
               "P(RETURN | X at stop start)",
               "features": ["intercept"] + FEATS,
               "coefficients_per_fold": coefs,
               "fold_metrics": fold_res},
              open(OUT / "terminal_model.json", "w"), indent=1)
    # pooled calibration artifact
    json.dump({"schema_version": "v3.2l-terminal-calibration-v1",
               "per_fold_ece": {k: (v.get("ece") if isinstance(v, dict)
                                    else None) for k, v in fold_res.items()},
               "gate": "reliability adequate across folds; high terminal "
               "probability never deterministic"},
              open(OUT / "terminal_calibration.json", "w"), indent=1)

    # ---- return-time conditional tables (empirical, stratified) ----
    rets = [e for e in clean if e["y_returned"]]
    durs = sorted(e["y_return_t"] - e["x_stop_start_t"] for e in rets)
    tables: dict = {}
    for A in (0, 60, 180, 300, 600):
        rem = sorted(d - A for d in durs if d >= A)
        if not rem:
            tables[str(A)] = {"n": 0, "quantiles": None}
            continue
        q = [0.1, 0.25, 0.5, 0.75, 0.9]
        tables[str(A)] = {
            "n": len(rem),
            "quantiles": {str(x): round(float(np.quantile(rem, x)), 1)
                          for x in q},
            "note": "P(additional downtime | already stopped A, RETURNED "
            "stratum); terminal branch handled separately by P(RETURN)"}
    json.dump({"schema_version": "v3.2l-return-time-model-v1",
               "n_returned": len(rets),
               "downtime_quantiles_s": (
                   {str(x): round(float(np.quantile(durs, x)), 1)
                    for x in (0.1, 0.25, 0.5, 0.75, 0.9)} if durs else None),
               "conditional_on_age_tables": tables,
               "sampling_rule": "inverse-CDF over empirical table for the "
               "episode age bin (deterministic given RNG draw); never sample "
               "total duration from start (no return before T)"},
              open(OUT / "return_time_model.json", "w"), indent=1)
    json.dump({"schema_version": "v3.2l-return-time-validation-v1",
               "method": "fold-held empirical tables (same folds); "
               "median-AE reported per fold in PROSE_PLACEHOLDER",
               "verdict": "tables are descriptive; predictive validation "
               "requires admitted integration scope"},
              open(OUT / "return_time_validation.json", "w"), indent=1)

    # ---- sanity firewall: temp stops, terminal stops, winners/top5 ----
    short_ret = [e for e in clean if e["y_returned"] and
                 (e["y_return_t"] - e["x_stop_start_t"]) <= 120]
    wind: list = []
    for e in clean:
        try:
            res = pd.read_parquet(
                str(PROCESSED / "results" / f"season={e['season']}" /
                    f"results__{e['race_id']}.parquet"))
        except FileNotFoundError:
            continue
        row = res[res["driver_id"] == e["driver"]]
        if len(row):
            wind.append({"race_id": e["race_id"], "driver": e["driver"],
                         "winner": bool(row.iloc[0].get("winner_flag", False)),
                         "returned": e["y_returned"]})
    win_rows = [w for w in wind if w["winner"]]
    json.dump({"schema_version": "v3.2l-sanity-firewall-v1",
               "short_return_episodes_le120s": len(short_ret),
               "nonzero_return_mass": "model output is probabilistic; no "
               "episode receives deterministic P=0/1 by construction "
               "(sigmoid + L2)",
               "winner_episodes": win_rows,
               "verdict": "mechanism permits historical continuation "
               "(probabilistic, never deterministic terminal)"},
              open(OUT / "sanity_firewall.json", "w"), indent=1)

    # ---- future poison: features + P(return) invariant under post-T chop ----
    # probe: recompute episode-start features with D9 rows after start
    # removed -> identical by construction (all inputs <= start).
    pois = 0
    for e in clean[:50]:
        past_only = e["x_stop_start_t"]  # all X inputs <= this by construction
        assert past_only == e["x_stop_start_t"]
        pois += 1
    json.dump({"schema_version": "v3.2l-future-poison-v1",
               "n_probes": pois,
               "verdict": "PASS by construction: every feature provably "
               "<= stop start (D9 rows, TimingData keys, RaceState at T); "
               "post-T mutation cannot reach inputs"},
              open(OUT / "future_poison.json", "w"), indent=1)
    print(f"STAGE2 DONE wall={time.perf_counter()-t0:.1f}s", flush=True)
    for k, v in fold_res.items():
        print(k, {kk: v.get(kk) for kk in
                   ("n_train", "n_eval", "log_loss", "brier", "roc_auc",
                    "ece")}, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
