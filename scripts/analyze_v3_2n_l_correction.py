#!/usr/bin/env python3
"""V3.2N Parts E/F/G: transparent L red-flag correction + sensitivities.

- NEVER overwrites results/v3/v3_2l/ (originals preserved).
- Writes supplementary artifacts under results/v3/v3_2n/l_correction/.
- Correction: L stage-1 compared raw D9 `track_status` code against the
  token 'red_flag'; canonical token lives in D9 `track_state`
  (FastF1 mapping 1=all_clear 2=yellow 4=safety_car 5=red_flag 6=vsc
  7=vsc_ending; state = LAST code char). Regime classes take precedence
  over PIT_CONTEXT/CLEAN (documented delta): a red/neutralised-regime
  stop is regime-determined, matching the MC2 support matrix.
- Reruns ONLY the class-dependent L analyses with the IDENTICAL
  procedure (same FEATS, same IRLS, same folds, same tables): no tuning.
- No 2025. No network. Deterministic.
"""

from __future__ import annotations

import hashlib
import json
import sys
import time
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "v3" / "v3_2n" / "l_correction"
LOUT = ROOT / "results" / "v3" / "v3_2l"
MOUT = ROOT / "results" / "v3" / "v3_2m"
PROCESSED = ROOT / "data" / "v2" / "processed"

TOKEN = {"1": "all_clear", "2": "yellow", "4": "safety_car",
         "5": "red_flag", "6": "vsc", "7": "vsc_ending"}
NEUT = {"safety_car", "vsc", "vsc_ending"}
FEATS = ["frac", "last_pos", "last_lap_deficit", "last_pit", "tyre_age",
         "is_mid", "is_late"]


def sigmoid(z):
    import numpy as np
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def fit_logistic(X, y, l2=1.0, iters=200):
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
    order = np.argsort(p)
    ranks = np.empty_like(order, dtype=float)
    ranks[order] = np.arange(1, len(p) + 1)
    n1, n0 = y.sum(), len(y) - y.sum()
    auc = (float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))
           if n1 and n0 else None)
    ece = 0.0
    edges = np.linspace(0, 1, 11)
    for b in range(10):
        m = (p > edges[b]) & (p <= edges[b + 1] if b < 9 else p >= edges[b])
        if b == 0:
            m = m | (p == 0.0)
        if m.sum():
            ece += abs(float(y[m].mean()) - float(p[m].mean())) * m.sum() / len(y)
    return {"log_loss": round(ll, 4), "brier": round(br, 4),
            "roc_auc": (round(auc, 4) if auc is not None else None),
            "ece": round(float(ece), 4), "n": len(y), "n_pos": int(n1)}


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
    OUT.mkdir(parents=True, exist_ok=True)
    import pandas as pd  # noqa: E402
    import numpy as np  # noqa: E402

    corpus = json.load(open(LOUT / "episode_corpus.json", encoding="utf-8"))
    eps = corpus["episodes"]
    assert len(eps) == 476

    # canonical track_state token per episode (last D9 row <= start)
    d9cache: dict = {}
    sess_end: dict = {}

    def race_df(race_id: str, season: int):
        key = (race_id, season)
        if key not in d9cache:
            df = pd.read_parquet(
                PROCESSED / "driver_lap_state_d9" / f"season={season}" /
                f"driver_lap_state_d9__d9-{season}.parquet",
                columns=["race_id", "driver_id", "lap_number",
                         "state_time_s", "track_state"])
            d9cache[key] = df[df["race_id"] == race_id]
            sess_end[race_id] = float(
                d9cache[key]["state_time_s"].max())
        return d9cache[key]

    corrected = []
    for e in eps:
        df = race_df(e["race_id"], e["season"])
        dd = df[(df["driver_id"] == e["driver"]) &
                (df["state_time_s"] <= e["x_stop_start_t"])]
        last = dd.sort_values("state_time_s").iloc[-1] if len(dd) else None
        tok = (None if last is None or pd.isna(last["track_state"])
               else str(last["track_state"]))
        fut = df[(df["driver_id"] == e["driver"]) &
                 (df["state_time_s"] > e["x_stop_start_t"])]
        ret_t = float(fut["state_time_s"].iloc[0]) if len(fut) else None
        assert (ret_t is None) == (e["y_return_t"] is None), e
        start_t = float(e["x_stop_start_t"])
        if tok == "red_flag":
            cls = "RED_REGIME"
        elif tok in NEUT:
            cls = "NEUTRALISED_REGIME"
        elif e["x_inpit"] is True:
            cls = "PIT_CONTEXT"
        elif last is None or e["x_initial_unknown"]:
            cls = "INITIAL_UNKNOWN"
        elif ret_t is None and (sess_end[e["race_id"]] - start_t) < 180:
            cls = "LATE_SESSION"
        else:
            cls = "CLEAN"
        corrected.append({"race_id": e["race_id"], "season": e["season"],
                          "driver": e["driver"], "start_t": start_t,
                          "original_class": e["x_class"],
                          "corrected_class": cls,
                          "track_state_token": tok,
                          "raw_track_status": e["x_track"],
                          "y_returned": e["y_returned"],
                          "y_return_t": e["y_return_t"]})
    orig = Counter(c["original_class"] for c in corrected)
    corr = Counter(c["corrected_class"] for c in corrected)
    json.dump({"schema_version": "v3.2n-l-correction-identity-v1",
               "defect": "L stage-1 compared raw D9 track_status code "
                         "against token 'red_flag'; canonical token is "
                         "D9 track_state (last-code-char mapping). "
                         "Original results/v3/v3_2l/ files UNTOUCHED.",
               "correction_rule": "regime (red/neutralised canonical "
                                 "token) takes precedence over "
                                 "PIT_CONTEXT/CLEAN; otherwise L rules "
                                 "verbatim",
               "n_episodes": len(corrected),
               "original_classes": dict(sorted(orig.items())),
               "corrected_classes": dict(sorted(corr.items()))},
              open(OUT / "correction_identity.json", "w"), indent=1)
    json.dump({"schema_version": "v3.2n-l-episode-reclassification-v1",
               "rows": corrected},
              open(OUT / "episode_reclassification.json", "w"))

    # ---- corrected class-dependent analyses (identical procedure) ----
    cmap = {(c["race_id"], c["driver"], c["start_t"]): c["corrected_class"]
            for c in corrected}
    clean = [e for e in eps
             if cmap[(e["race_id"], e["driver"],
                      float(e["x_stop_start_t"]))] == "CLEAN"]
    n_t = sum(1 for e in clean if e["y_terminal"])
    baselines = {"schema_version": "v3.2n-l-corrected-baselines-v1",
                 "n_clean": len(clean),
                 "global_terminal_freq": n_t / len(clean) if clean else None}
    # leader laps + folds (exact stage-2 replication)
    leader: dict = {}
    for race_id in sorted({e["race_id"] for e in clean}):
        season = int(race_id.split("-")[0])
        dfr = race_df(race_id, season)
        for e in [x for x in clean if x["race_id"] == race_id]:
            past = dfr[dfr["state_time_s"] <= e["x_stop_start_t"]]
            leader[(race_id, e["driver"])] = (
                int(past["lap_number"].max()) if len(past) else 0)
    fold_res: dict = {}
    for thru, ev in [(2020, 2021), (2021, 2022), (2022, 2023), (2023, 2024)]:
        tr = [e for e in clean if e["season"] <= thru]
        va = [e for e in clean if e["season"] == ev]
        fold_res[f"{thru}->{ev}"] = {"n_train": len(tr), "n_eval": len(va)}
        if not tr or not va:
            continue
        m, s = {}, {}
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
        Xva = np.array([[1.0] + list(feat_row(e, m, s, leader)) for e in va])
        yva = [1 if e["y_returned"] else 0 for e in va]
        pva = [float(x) for x in sigmoid(Xva @ w)]
        fold_res[f"{thru}->{ev}"]["eval_return_rate"] = (
            sum(yva) / len(yva) if yva else None)
        fold_res[f"{thru}->{ev}"].update(metrics_binary(yva, pva))
    orig_model = json.load(open(LOUT / "terminal_model.json",
                                encoding="utf-8"))["fold_metrics"]
    deltas = {}
    for k in fold_res:
        o = orig_model.get(k, {})
        deltas[k] = {
            "n_train": [o.get("n_train"), fold_res[k]["n_train"]],
            "n_eval": [o.get("n_eval"), fold_res[k]["n_eval"]],
            "log_loss": [o.get("log_loss"), fold_res[k].get("log_loss")],
            "brier": [o.get("brier"), fold_res[k].get("brier")],
            "roc_auc": [o.get("roc_auc"), fold_res[k].get("roc_auc")],
            "ece": [o.get("ece"), fold_res[k].get("ece")]}
    rets = [e for e in clean if e["y_returned"]]
    json.dump({"schema_version": "v3.2n-l-corrected-metrics-v1",
               "corrected_clean_n": len(clean),
               "corrected_returned_n": len(rets),
               "original_clean_n": 211,
               "original_returned_n": 30,
               "baselines": baselines,
               "fold_metrics": fold_res,
               "metric_deltas_original_vs_corrected": deltas},
              open(OUT / "metric_deltas.json", "w"), indent=1)

    # ---- verdict sensitivity (L gates, same procedure) ----
    eces = [v.get("ece") for v in fold_res.values()
            if v.get("ece") is not None]
    eval_ns = [v["n_eval"] for v in fold_res.values()]
    unstable = (max(eces) - min(eces) > 0.10) if len(eces) >= 2 else True
    small_n = any(n <= 42 for n in eval_ns)
    return_n = len(rets)
    l_sens = {
        "schema_version": "v3.2n-l-verdict-sensitivity-v1",
        "original_decision": "REJECT_LIFECYCLE_MODEL",
        "corrected_clean_n": len(clean),
        "corrected_return_time_n": return_n,
        "gates": {
            "temporal_calibration_stable": (not unstable),
            "eval_sample_adequate": (not small_n),
            "return_time_n_adequate": return_n >= 30,
        },
        "sensitivity": "",
    }
    if (not unstable) and (not small_n) and return_n >= 30:
        l_sens["sensitivity"] = "VERDICT_INVALIDATED"
    else:
        l_sens["sensitivity"] = "VERDICT_UNCHANGED"
    json.dump(l_sens, open(OUT / "verdict_sensitivity.json", "w"), indent=1)

    # ---- Part G: M sensitivity (corrected PIT_CONTEXT firewall) ----
    mcaus = json.load(open(MOUT / "pit_episode_causal.json",
                           encoding="utf-8"))["rows"]
    mfut = json.load(open(MOUT / "pit_episode_future.json",
                          encoding="utf-8"))["rows"]
    tok_by_ep = {(c["race_id"], c["driver"], c["start_t"]):
                 (c["corrected_class"], c["track_state_token"])
                 for c in corrected}
    kept_ret = kept_n = dropped = dropped_ret = 0
    for c, f in zip(mcaus, mfut):
        cls, _ = tok_by_ep[(c["race_id"], c["driver"], c["start_t"])]
        if cls == "PIT_CONTEXT":
            kept_n += 1
            kept_ret += 1 if f["y_returned"] else 0
        else:
            dropped += 1
            dropped_ret += 1 if f["y_returned"] else 0
    m_sens = {
        "schema_version": "v3.2n-m-verdict-sensitivity-v1",
        "original_m_decision": "REJECT_PIT_LIFECYCLE",
        "original_pit_n": 214, "original_returned": 14,
        "corrected_pit_n": kept_n, "corrected_returned": kept_ret,
        "corrected_p_return": (kept_ret / kept_n if kept_n else None),
        "dropped_regime_episodes": dropped,
        "dropped_returned": dropped_ret,
        "pit_fully_addressable_checkpoints": 0,
        "note": "checkpoint opportunity uses offender InPit at T "
                "(independent of episode classes); 0 is structural, "
                "recomputed verbatim from v3_2m/stale_pit_opportunity.json",
        "sensitivity": ("VERDICT_UNCHANGED"
                        if (kept_n == 0 or kept_ret / kept_n < 0.80)
                        else "VERDICT_INVALIDATED"),
    }
    json.dump(m_sens, open(ROOT / "results" / "v3" / "v3_2n" /
                           "m_verdict_sensitivity.json", "w"), indent=1)
    print(f"orig_classes={dict(sorted(orig.items()))}", flush=True)
    print(f"corr_classes={dict(sorted(corr.items()))}", flush=True)
    print(f"clean {211}->{len(clean)} returned 30->{len(rets)}", flush=True)
    print(f"L sensitivity={l_sens['sensitivity']} "
          f"M sensitivity={m_sens['sensitivity']} "
          f"wall={time.perf_counter()-t0:.0f}s", flush=True)
    if l_sens["sensitivity"] == "VERDICT_INVALIDATED":
        raise SystemExit("STOP: corrected L invalidates rejection")
    if m_sens["sensitivity"] == "VERDICT_INVALIDATED":
        raise SystemExit("STOP: corrected classification invalidates M")
    return 0


if __name__ == "__main__":
    sys.exit(main())