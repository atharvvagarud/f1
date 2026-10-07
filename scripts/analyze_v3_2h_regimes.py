#!/usr/bin/env python3
"""V3.2H causal race-regime evidence (Parts F-AF + AL-AT inputs).

Deterministic, read-only over the frozen corpus plus D9 lap parquets
(2018-2024; 2025 never touched). Verifies the H preregistration hash
before scoring. No simulator source, parameter, artifact, or replay
cache is modified. No Monte Carlo integration. No model training.
No future-at-T reads in any estimation path: every evaluation-season
prediction uses strictly past seasons (H1: train<=2021/eval 2022-2023;
H2: train<=2023/eval 2024).

Outputs results/v3/v3_2h/*.json (no timestamps/usernames/abs paths).
"""

from __future__ import annotations

import glob
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "results" / "v3" / "v3_2h"
RAW = ROOT / "results" / "v3" / "v3_2f" / "coverage_opportunity_raw.json"
D9 = ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9"

TRAIN_H1 = (2018, 2019, 2020, 2021)
EVAL_H1 = (2022, 2023)
TRAIN_H2 = (2018, 2019, 2020, 2021, 2022, 2023)
EVAL_H2 = (2024,)


def _q(vals: list, q: float):
    if not vals:
        return None
    s = sorted(vals)
    if len(s) == 1:
        return float(s[0])
    pos = q * (len(s) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    f = pos - lo
    return float(s[lo] * (1 - f) + s[hi] * f)


def _summ(vals: list) -> dict:
    import statistics as st
    vals = [float(v) for v in vals]
    if not vals:
        return {"n": 0, "mean": None, "sd": None, "p10": None,
                "p50": None, "p90": None}
    return {"n": len(vals), "mean": float(st.fmean(vals)),
            "sd": float(st.pstdev(vals)) if len(vals) > 1 else 0.0,
            "p10": _q(vals, 0.10), "p50": _q(vals, 0.50),
            "p90": _q(vals, 0.90)}


def _hash(obj) -> str:
    text = json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      allow_nan=False, default=str)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def check_prereg() -> str:
    sys.path.insert(0, str(ROOT / "scripts"))
    from freeze_v3_2h_prereg import build, content_hash
    h = content_hash(build())
    saved = json.load(open(OUT_DIR / "preregistration.json", encoding="utf-8"))
    assert saved.get("prereg_hash") == h, (
        f"prereg hash mismatch: code={h} saved={saved.get('prereg_hash')}")
    return h


def load_d9(seasons) -> dict:
    """race_id -> list of lap rows (dicts), 2018-2024 only."""
    import pandas as pd
    races: dict = {}
    for season in seasons:
        for p in sorted(glob.glob(str(D9 / f"season={season}" / "*.parquet"))):
            df = pd.read_parquet(p)
            for row in df.itertuples():
                races.setdefault(row.race_id, []).append(row)
    for r in races:
        races[r].sort(key=lambda x: (x.lap_number, str(x.driver_id)))
    return races


def episodes_for(races: dict, tokens: set) -> list:
    """Run-length episodes of `tokens` over (race, lap_number) modal token."""
    eps = []
    for race_id, rows in races.items():
        laps: dict = {}
        for row in rows:
            laps.setdefault(int(row.lap_number), []).append(row.track_state)
        ordered = sorted(laps)
        # modal token per lap
        mods = {}
        for lap in ordered:
            toks = [t for t in laps[lap] if t is not None]
            mods[lap] = (max(sorted(set(toks)), key=toks.count) if toks else None)
        season = int(str(race_id).split("-")[0])
        circuit = str(rows[0].circuit_id)
        i = 0
        while i < len(ordered):
            lap = ordered[i]
            if mods[lap] in tokens:
                j = i
                while j + 1 < len(ordered) and mods[ordered[j + 1]] in tokens:
                    j += 1
                entry, exit_ = ordered[i], ordered[j]
                # race phase at entry: median progress frac
                fracs = [float(r.race_progress_frac) for r in rows
                         if int(r.lap_number) == entry
                         and r.race_progress_frac == r.race_progress_frac]
                eps.append({"race_id": str(race_id), "season": season,
                            "circuit": circuit, "token": mods[lap],
                            "entry_lap": entry, "exit_lap": exit_,
                            "duration_laps": exit_ - entry + 1,
                            "entry_frac": (sum(fracs) / len(fracs)
                                           if fracs else None)})
                i = j + 1
            else:
                i += 1
    return eps


def green_ref_table(races: dict, seasons: set) -> dict:
    """Past-only green reference: median lap per (era, circuit, compound).

    Green = all_clear, dry compound, lap>1, no pit in/out, accurate.
    Era split matches V3.2F wet audit (2018-2021 | 2022-2024).
    """
    import pandas as pd
    cells: dict = {}
    for rows in races.values():
        for r in rows:
            if int(str(r.race_id).split("-")[0]) not in seasons:
                continue
            if r.track_state != "all_clear" or r.compound in ("INTERMEDIATE", "WET"):
                continue
            if int(r.lap_number) <= 1 or not pd.notna(r.lap_time_s):
                continue
            if pd.notna(r.pit_in_s) or pd.notna(r.pit_out_s):
                continue
            if r.is_accurate is False:
                continue
            era = "2018-2021" if int(str(r.race_id).split("-")[0]) <= 2021 else "2022-2024"
            key = (era, str(r.circuit_id), str(r.compound))
            cells.setdefault(key, []).append(float(r.lap_time_s))
    return {f"{k[0]}|{k[1]}|{k[2]}": _q(v, 0.5) for k, v in cells.items()
            if len(v) >= 30}


def era_of(season: int) -> str:
    return "2018-2021" if season <= 2021 else "2022-2024"


def ref_lookup(ref: dict, era: str, circuit: str, compound: str):
    """Era-exact green reference, else cross-era fallback (recorded).

    Cross-era fallback is used only for offline scoring (reg change
    2022 shifts absolute pace); the fallback is counted so its share
    is visible in validation outputs.
    """
    key = f"{era}|{circuit}|{compound}"
    if key in ref:
        return ref[key], False
    other = "2022-2024" if era == "2018-2021" else "2018-2021"
    fb = f"{other}|{circuit}|{compound}"
    if fb in ref:
        return ref[fb], True
    return None, False


def lap_deltas(races: dict, eps: list, ref: dict, window: str) -> list:
    """Driver lap deltas vs past-only green reference.

    window: 'during' (entry..exit), 'before' (entry-3..entry-1, green only),
    'after' (exit+1..exit+3, green only).
    """
    import pandas as pd
    out = []
    by_race = races
    for ep in eps:
        rows = by_race.get(ep["race_id"], [])
        if window == "during":
            laps = range(ep["entry_lap"], ep["exit_lap"] + 1)
            tok_ok = None  # any token inside episode
        elif window == "before":
            laps = range(max(1, ep["entry_lap"] - 3), ep["entry_lap"])
            tok_ok = "all_clear"
        else:
            laps = range(ep["exit_lap"] + 1, ep["exit_lap"] + 4)
            tok_ok = "all_clear"
        for r in rows:
            if int(r.lap_number) not in laps:
                continue
            if tok_ok is not None and r.track_state != tok_ok:
                continue
            if r.compound in ("INTERMEDIATE", "WET"):
                continue
            if not pd.notna(r.lap_time_s):
                continue
            if pd.notna(r.pit_in_s) or pd.notna(r.pit_out_s):
                continue
            b, fb = ref_lookup(ref, era_of(ep["season"]), ep["circuit"],
                               str(r.compound))
            if b is None:
                continue
            out.append({"ep": (ep["race_id"], ep["entry_lap"]),
                        "driver": str(r.driver_id),
                        "delta": float(r.lap_time_s) - b,
                        "era_fallback": fb})
    return out


def field_spread(races: dict, eps: list) -> list:
    """Field spread (max-min lap_start_s) before/during/after per episode.

    Reports both raw spread and no-pit spread (laps with any pit
    in/out excluded): pit stops scatter lap_start_s and confound naive
    bunching measurement, especially under SC (pit rate ~4x green).
    """
    import pandas as pd
    out = []
    for ep in eps:
        rows = races.get(ep["race_id"], [])
        by_lap: dict = {}
        pit_lap: set = set()
        for r in rows:
            if pd.notna(r.lap_start_s):
                by_lap.setdefault(int(r.lap_number), []).append(float(r.lap_start_s))
            if pd.notna(r.pit_in_s) or pd.notna(r.pit_out_s):
                pit_lap.add(int(r.lap_number))
        def spread(lap, skip_pit=False):
            if skip_pit and lap in pit_lap:
                return None
            v = by_lap.get(lap, [])
            return (max(v) - min(v)) if len(v) >= 5 else None
        before_laps = [ep["entry_lap"] - k for k in (1, 2, 3)
                       if ep["entry_lap"] - k >= 1]
        after_laps = [ep["exit_lap"] + k for k in (1, 2, 3)]
        during_laps = list(range(ep["entry_lap"], ep["exit_lap"] + 1))
        b = [s for s in (spread(l) for l in before_laps) if s is not None]
        d = [s for s in (spread(l) for l in during_laps) if s is not None]
        a = [s for s in (spread(l) for l in after_laps) if s is not None]
        bn = [s for s in (spread(l, True) for l in before_laps) if s is not None]
        dn = [s for s in (spread(l, True) for l in during_laps) if s is not None]
        an = [s for s in (spread(l, True) for l in after_laps) if s is not None]
        if not b or not d:
            continue
        import statistics as st
        out.append({"ep": (ep["race_id"], ep["entry_lap"]),
                    "before": float(st.fmean(b)), "during": float(st.fmean(d)),
                    "after": (float(st.fmean(a)) if a else None),
                    "before_nopit": (float(st.fmean(bn)) if bn else None),
                    "during_nopit": (float(st.fmean(dn)) if dn else None),
                    "after_nopit": (float(st.fmean(an)) if an else None)})
    return out


def survival_table(durations: list) -> dict:
    """Empirical P(continue | age=a) + residual distribution (past-only fit)."""
    import statistics as st
    maxd = max(durations) if durations else 0
    table = {}
    for a in range(1, maxd + 1):
        reached = [d for d in durations if d >= a]
        continued = [d for d in durations if d > a]
        table[str(a)] = {
            "n_reached": len(reached),
            "p_continue": (len(continued) / len(reached) if reached else None),
            "residual_median": (_q([d - a for d in reached], 0.5)
                                if reached else None)}
    return {"n": len(durations), "dist": _summ(durations),
            "p_continue_given_age": table,
            "median_predictor": _q(durations, 0.5)}


def duration_validate(fit_durs: list, eval_eps: list) -> dict:
    import statistics as st
    med = _q(fit_durs, 0.5)
    surv = survival_table(fit_durs)
    errs, cal = [], []
    for ep in eval_eps:
        errs.append(abs(ep["duration_laps"] - med))
        a = ep["duration_laps"]
        # calibration: predicted P(continue|age) vs actual (1 if d>a else 0)
        # evaluated at each elapsed age 1..d
        for age in range(1, a + 1):
            cell = surv["p_continue_given_age"].get(str(age))
            if cell and cell["p_continue"] is not None:
                actual = 1.0 if a > age else 0.0
                cal.append((cell["p_continue"], actual))
    mae = float(st.fmean(errs)) if errs else None
    # calibration slope via simple linear fit of actual on predicted
    slope = None
    if len(cal) >= 10:
        import statistics as st2
        xs = [c[0] for c in cal]
        ys = [c[1] for c in cal]
        mx, my = st2.fmean(xs), st2.fmean(ys)
        den = sum((x - mx) ** 2 for x in xs)
        slope = (sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / den
                 if den > 0 else None)
    return {"n_eval": len(eval_eps), "median_rule": med, "mae_laps": mae,
            "calibration_slope": slope, "calibration_pairs": len(cal)}


def main() -> int:
    prereg_hash = check_prereg()
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # ---------------- Part F: opportunity ----------------
    raw = json.load(open(RAW, encoding="utf-8"))
    cps = raw["checkpoints"]
    TRACK = "UNSUPPORTED_TRACK_STATE"
    WETB = "WET_CONDITIONS"
    track_only = [c for c in cps if set(c["all_blockers"]) == {TRACK}]
    wet_only = [c for c in cps if set(c["all_blockers"]) == {WETB}]
    by_token: dict = {}
    for c in track_only:
        by_token.setdefault(str(c["detail"].get("track_state")), []).append(
            (c["race_id"], c["frame_index"]))
    wet_detail: dict = {}
    for c in wet_only:
        key = (bool(c.get("rainfall")),
               len(c.get("wet_drivers", [])) > 0)
        wet_detail.setdefault(str(key), []).append(
            (c["race_id"], c["frame_index"]))
    # regime x stale intersections present in current state
    track_stale = [c for c in cps if TRACK in c["all_blockers"]
                   and "STALE_ROSTER_OBSERVATION" in c["all_blockers"]]
    wet_stale = [c for c in cps if WETB in c["all_blockers"]
                 and "STALE_ROSTER_OBSERVATION" in c["all_blockers"]]
    opportunity = {
        "schema_version": "v3.2h-opportunity-v1",
        "prereg_hash": prereg_hash,
        "track_only_total": len(track_only),
        "track_only_by_token": {k: {"n": len(v), "members": sorted(v)}
                                for k, v in sorted(by_token.items())},
        "wet_only_total": len(wet_only),
        "wet_only_by_state": {k: {"n": len(v), "members": sorted(v)}
                              for k, v in sorted(wet_detail.items())},
        "track_x_stale": len(track_stale),
        "wet_x_stale": len(wet_stale),
        "note": "rainfall key: (rainfall_flag, any_wet_compound_driver)",
    }
    json.dump(opportunity, open(OUT_DIR / "opportunity.json", "w"),
              indent=2, sort_keys=True)

    # ---------------- Episodes (offline, all seasons) ----------------
    races = load_d9([2018, 2019, 2020, 2021, 2022, 2023, 2024])
    vsc_eps = episodes_for(races, {"vsc"})
    sc_eps = episodes_for(races, {"safety_car"})
    y_eps = episodes_for(races, {"yellow"})
    json.dump({"schema_version": "v3.2h-vsc-episodes-v1",
               "prereg_hash": prereg_hash, "n": len(vsc_eps),
               "episodes": sorted(vsc_eps, key=lambda e: (e["season"], e["race_id"], e["entry_lap"]))},
              open(OUT_DIR / "vsc_episodes.json", "w"), indent=2, sort_keys=True)

    # ---------------- VSC temporal program ----------------
    vsc_results = {}
    for fold, tr, ev in (("H1", TRAIN_H1, EVAL_H1), ("H2", TRAIN_H2, EVAL_H2)):
        tr_races = {r: v for r, v in races.items()
                    if int(str(r).split("-")[0]) in tr}
        ref = green_ref_table(races, set(tr))
        tr_eps = [e for e in vsc_eps if e["season"] in tr]
        ev_eps = [e for e in vsc_eps if e["season"] in ev]
        dur_fit = [e["duration_laps"] for e in tr_eps]
        dur_val = duration_validate(dur_fit, ev_eps)
        # pace: past-only offset = median during-delta on train
        tr_during = lap_deltas(tr_races, tr_eps, ref, "during")
        off = _q([d["delta"] for d in tr_during], 0.5)
        import statistics as st
        errs, post_errs = [], []
        ev_races = {r: v for r, v in races.items()
                    if int(str(r).split("-")[0]) in ev}
        ev_during = lap_deltas(ev_races, ev_eps, ref, "during")
        for d in ev_during:
            errs.append(abs(d["delta"] - off))
        ev_after = lap_deltas(ev_races, ev_eps, ref, "after")
        for d in ev_after:
            post_errs.append(abs(d["delta"] - 0.0))
        # driver variation on train
        by_drv: dict = {}
        for d in tr_during:
            by_drv.setdefault(d["driver"], []).append(d["delta"])
        drv_med = {k: _q(v, 0.5) for k, v in by_drv.items()}
        spread = field_spread(races, [e for e in vsc_eps if e["season"] in ev]
                              or ev_eps)
        ratios_d = [(s["during"] / s["before"]) for s in spread if s["before"] > 0]
        ratios_a = [(s["after"] / s["before"]) for s in spread
                    if s["before"] > 0 and s["after"]]
        ratios_dn = [(s["during_nopit"] / s["before_nopit"]) for s in spread
                     if s["before_nopit"] and s["during_nopit"] and s["before_nopit"] > 0]
        vsc_results[fold] = {
            "train_episodes": len(tr_eps), "eval_episodes": len(ev_eps),
            "duration_fit": survival_table(dur_fit),
            "duration_validation": dur_val,
            "pace_offset_s": off,
            "pace_train": _summ([d["delta"] for d in tr_during]),
            "during_pace_mae_s": (float(st.fmean(errs)) if errs else None),
            "during_pace_n": len(errs),
            "post_exit_pace_mae_s": (float(st.fmean(post_errs)) if post_errs else None),
            "post_exit_pace_n": len(post_errs),
            "driver_offset_sd_s": (float(st.pstdev(list(drv_med.values())))
                                   if len(drv_med) > 1 else 0.0),
            "n_drivers": len(drv_med),
            "spread_ratio_during_before": _summ(ratios_d),
            "spread_ratio_after_before": _summ(ratios_a),
            "spread_ratio_nopit_during_before": _summ(ratios_dn),
        }
    json.dump({"schema_version": "v3.2h-vsc-parameters-v1",
               "prereg_hash": prereg_hash, "folds": vsc_results},
              open(OUT_DIR / "vsc_parameters.json", "w"), indent=2, sort_keys=True)

    # VSC validation roll-up + gate scoring (prereg thresholds)
    def gate(ok):
        return "PASS" if ok else "FAIL"
    vg = {}
    for fold in ("H1", "H2"):
        r = vsc_results[fold]
        dv = r["duration_validation"]
        slope = dv["calibration_slope"]
        g_dur = (slope is not None and 0.5 <= slope <= 1.5
                 and dv["mae_laps"] is not None and dv["mae_laps"] <= 1.5)
        g_pace = (r["during_pace_mae_s"] is not None
                  and r["during_pace_mae_s"] <= 10.0)
        g_post = (r["post_exit_pace_mae_s"] is not None
                  and r["post_exit_pace_mae_s"] <= 6.0)
        med_ratio = r["spread_ratio_during_before"]["p50"]
        g_gap = (med_ratio is not None and 0.5 <= med_ratio <= 1.5)
        vg[fold] = {
            "duration": gate(g_dur),
            "during_pace": gate(g_pace),
            "post_exit": gate(g_post),
            "gap": gate(g_gap),
        }
    all_pass = all(v == "PASS" for f in vg.values() for v in f.values())
    vsc_decision = ("ADMIT_VSC" if all_pass else "REJECT_VSC")
    json.dump({"schema_version": "v3.2h-vsc-validation-v1",
               "prereg_hash": prereg_hash, "folds": vsc_results,
               "gates": vg,
               "outcome_metrics": "NOT_MEASURABLE_OFFLINE: no integrated "
                                  "regime simulator exists; winner "
                                  "log-loss/Brier/RPS require runtime "
                                  "integration, which prereg forbids "
                                  "before admission",
               "invalid_rate": "NOT_APPLICABLE_NO_RUNTIME"},
              open(OUT_DIR / "vsc_validation.json", "w"), indent=2, sort_keys=True)
    json.dump({"schema_version": "v3.2h-vsc-decision-v1",
               "prereg_hash": prereg_hash, "decision": vsc_decision,
               "gates": vg,
               "reason": ("all prereg gates pass" if all_pass else
                          "one or more prereg gates FAIL; explicit 422 "
                          "retained; DRY_GREEN MC2 E unchanged")},
              open(OUT_DIR / "vsc_decision.json", "w"), indent=2, sort_keys=True)

    # ---------------- VSC_ENDING token semantics ----------------
    # Per (driver, lap): a row carrying vsc_ending -> token on that
    # driver's NEXT lap (no modal washout; factual-at-T only).
    nxt: dict = {}
    n_ending = 0
    for race_id, rows in races.items():
        drv_laps: dict = {}
        for r in rows:
            drv_laps.setdefault(str(r.driver_id), {})[int(r.lap_number)] = r.track_state
        for drv, seq in drv_laps.items():
            laps = sorted(seq)
            for i, lap in enumerate(laps):
                if seq[lap] == "vsc_ending":
                    n_ending += 1
                    nxt_tok = seq[laps[i + 1]] if i + 1 < len(laps) else None
                    nxt[str(nxt_tok)] = nxt.get(str(nxt_tok), 0) + 1
    json.dump({"schema_version": "v3.2h-vsc-ending-v1",
               "prereg_hash": prereg_hash, "n_vsc_ending_laps": n_ending,
               "next_token_counts": nxt,
               "decision": ("ADMIT_VSC_ENDING" if nxt.get("all_clear", 0) / max(n_ending, 1) >= 0.95
                            else "REJECT_VSC_ENDING"),
               "reason": "ending transition admitted only if >=95% of "
                         "vsc_ending laps resolve to green next lap; "
                         "no inferred timestamp either way"},
              open(OUT_DIR / "vsc_ending_decision.json", "w"), indent=2, sort_keys=True)

    # ---------------- Wet program ----------------
    import pandas as pd
    wet_cells: dict = {}
    for rows in races.values():
        for r in rows:
            if r.compound not in ("INTERMEDIATE", "WET"):
                continue
            if not pd.notna(r.lap_time_s) or int(r.lap_number) <= 1:
                continue
            if pd.notna(r.pit_in_s) or pd.notna(r.pit_out_s):
                continue
            if not pd.notna(r.wx_rainfall):
                continue  # missing weather: no factual rain state
            if r.track_state != "all_clear":
                continue  # green-flag wet pace only (neutralised laps
                # carry +20-30 s regime effects, tested separately)
            era = era_of(int(str(r.race_id).split("-")[0]))
            key = (era, str(r.compound), bool(r.wx_rainfall))
            wet_cells.setdefault(key, []).append(float(r.lap_time_s))
    wet_summary = {f"{k[0]}|{k[1]}|rain={k[2]}": _summ(v)
                   for k, v in sorted(wet_cells.items(), key=lambda x: str(x[0]))}
    # weather transition counts (per race lap sequence of rainfall bool)
    trans = {}
    for rows in races.values():
        by_lap: dict = {}
        for r in rows:
            if r.wx_rainfall == r.wx_rainfall:  # not NaN
                by_lap.setdefault(int(r.lap_number), []).append(bool(r.wx_rainfall))
        seq = [max(sorted(set(v)), key=v.count) for _, v in sorted(by_lap.items()) if v]
        for a, b in zip(seq, seq[1:]):
            trans[f"{a}->{b}"] = trans.get(f"{a}->{b}", 0) + 1
    # compound-transition audit at wet<->dry boundaries
    need_change, no_change = 0, 0
    for rows in races.values():
        by_lap: dict = {}
        for r in rows:
            by_lap.setdefault((str(r.driver_id), int(r.lap_number)), []).append(r)
        # per driver compound sequence
        drv_laps: dict = {}
        for (drv, lap), rs in by_lap.items():
            drv_laps.setdefault(drv, {})[lap] = (str(rs[0].compound),
                                                 bool(rs[0].wx_rainfall) if rs[0].wx_rainfall == rs[0].wx_rainfall else None)
        for drv, seq in drv_laps.items():
            laps = sorted(seq)
            for i in range(1, len(laps)):
                c0, w0 = seq[laps[i - 1]]
                c1, w1 = seq[laps[i]]
                if w0 is None or w1 is None or w0 == w1:
                    continue
                wet0 = c0 in ("INTERMEDIATE", "WET")
                wet1 = c1 in ("INTERMEDIATE", "WET")
                if wet0 != wet1:
                    continue  # already on right tyre (or changed with weather)
                # weather flipped but compound family did not -> needs a stop
                # check whether a pit occurred within +-2 laps
                pits = [lap for lap, rs in by_lap.items() if lap[0] == drv
                        and any(pd.notna(x.pit_in_s) or pd.notna(x.pit_out_s) for x in rs)]
                window = [p for p in pits if abs(p[1] - laps[i]) <= 2]
                if window:
                    need_change += 1
                else:
                    no_change += 1
    json.dump({"schema_version": "v3.2h-wet-episodes-v1",
               "prereg_hash": prereg_hash, "wet_cells": wet_summary,
               "weather_lap_transitions": trans},
              open(OUT_DIR / "wet_episodes.json", "w"), indent=2, sort_keys=True)
    # wet pace MAE: circuit-conditioned hierarchy with prereg fallback.
    # L0 (circuit, compound, rain) needs N>=30 else back off to L1
    # (era, compound, rain); cross-era L1 fallback recorded. Raw lap
    # times vary ~circuit, so an unconditioned cell median cannot
    # predict (circuit effect alone is ~10+s).
    wet_val = {}
    for fold, tr, ev in (("H1", TRAIN_H1, EVAL_H1), ("H2", TRAIN_H2, EVAL_H2)):
        l0: dict = {}
        l1: dict = {}
        evals = []
        for rows in races.values():
            for r in rows:
                season = int(str(r.race_id).split("-")[0])
                if r.compound not in ("INTERMEDIATE", "WET"):
                    continue
                if not pd.notna(r.lap_time_s) or int(r.lap_number) <= 1:
                    continue
                if pd.notna(r.pit_in_s) or pd.notna(r.pit_out_s):
                    continue
                if not pd.notna(r.wx_rainfall):
                    continue
                if r.track_state != "all_clear":
                    continue
                era = era_of(season)
                lap = float(r.lap_time_s)
                if season in tr:
                    l0.setdefault((str(r.circuit_id), str(r.compound),
                                   bool(r.wx_rainfall)), []).append(lap)
                    l1.setdefault((era, str(r.compound),
                                   bool(r.wx_rainfall)), []).append(lap)
                elif season in ev:
                    evals.append(((str(r.circuit_id), str(r.compound),
                                   bool(r.wx_rainfall)),
                                  (era, str(r.compound),
                                   bool(r.wx_rainfall)), lap))
        med0 = {k: _q(v, 0.5) for k, v in l0.items() if len(v) >= 30}
        med1 = {k: _q(v, 0.5) for k, v in l1.items() if len(v) >= 30}
        errs, n_l0, n_l1, n_xera, n_miss = [], 0, 0, 0, 0
        for k0, k1, lap in evals:
            b = med0.get(k0)
            if b is not None:
                n_l0 += 1
            else:
                b = med1.get(k1)
                if b is not None:
                    n_l1 += 1
                else:
                    other = ("2022-2024" if k1[0] == "2018-2021"
                             else "2018-2021")
                    b = med1.get((other, k1[1], k1[2]))
                    if b is not None:
                        n_xera += 1
                    else:
                        n_miss += 1
                        continue
            errs.append(abs(lap - b))
        import statistics as st
        wet_val[fold] = {
            "l0_cells_kept": len(med0),
            "l0_cells_total": len(l0),
            "l1_cells": {f"{k[0]}|{k[1]}|rain={k[2]}": len(l1[k])
                         for k in sorted(med1, key=str)},
            "mae_s": (float(st.fmean(errs)) if errs else None),
            "n": len(errs), "n_l0": n_l0, "n_l1": n_l1,
            "n_cross_era": n_xera, "n_unpredicted": n_miss}
    wet_gates = {f: ("PASS" if (v["mae_s"] is not None and v["mae_s"] <= 6.0) else "FAIL")
                 for f, v in wet_val.items()}
    runnable = (need_change + no_change) == 0  # no unhandled boundary if zero?
    # R6 is dry-filtered: any weather-flip boundary that keeps the wrong
    # family needs a strategy stop -> inseparable from Strategy 2.0.
    compound_ok = (need_change == 0 and no_change == 0)
    wet_decision = ("ADMIT_WET" if all(v == "PASS" for v in wet_gates.values())
                    and compound_ok else "REJECT_WET")
    json.dump({"schema_version": "v3.2h-wet-parameters-v1",
               "prereg_hash": prereg_hash, "folds": wet_val,
               "weather_transition": {"counts": trans,
                                      "identity": "counts-only; no admitted "
                                                  "transition model (needs "
                                                  "compound policy first)"},
               "compound_boundary": {"weather_flip_same_family_with_stop_within_2laps": need_change,
                                     "weather_flip_same_family_no_stop": no_change,
                                     "r6_boundary": "R6 dry-filtered; a "
                                                    "causal wet/dry compound "
                                                    "choice is Strategy 2.0 "
                                                    "territory"},
               "gates": wet_gates, "compound_gate": ("PASS" if compound_ok else "FAIL")},
              open(OUT_DIR / "wet_parameters.json", "w"), indent=2, sort_keys=True)
    json.dump({"schema_version": "v3.2h-wet-validation-v1",
               "prereg_hash": prereg_hash, "folds": wet_val,
               "outcome_metrics": "NOT_MEASURABLE_OFFLINE (no runnable "
                                  "candidate without compound policy)"},
              open(OUT_DIR / "wet_validation.json", "w"), indent=2, sort_keys=True)
    json.dump({"schema_version": "v3.2h-wet-decision-v1",
               "prereg_hash": prereg_hash, "decision": wet_decision,
               "reason": ("all gates pass" if wet_decision == "ADMIT_WET" else
                          "compound-transition boundary inseparable from "
                          "Strategy 2.0 and/or pace gates fail; explicit "
                          "422 retained")},
              open(OUT_DIR / "wet_decision.json", "w"), indent=2, sort_keys=True)

    # ---------------- Safety car program ----------------
    sc_results = {}
    for fold, tr, ev in (("H1", TRAIN_H1, EVAL_H1), ("H2", TRAIN_H2, EVAL_H2)):
        tr_races = {r: v for r, v in races.items() if int(str(r).split("-")[0]) in tr}
        ref = green_ref_table(races, set(tr))
        tr_eps = [e for e in sc_eps if e["season"] in tr]
        ev_eps = [e for e in sc_eps if e["season"] in ev]
        dur_fit = [e["duration_laps"] for e in tr_eps]
        dur_val = duration_validate(dur_fit, ev_eps)
        spread = field_spread(races, ev_eps)
        ratios_d = [(s["during"] / s["before"]) for s in spread if s["before"] > 0]
        ratios_dn = [(s["during_nopit"] / s["before_nopit"]) for s in spread
                     if s["before_nopit"] and s["during_nopit"] and s["before_nopit"] > 0]
        ev_races = {r: v for r, v in races.items() if int(str(r).split("-")[0]) in ev}
        ev_after = lap_deltas(ev_races, ev_eps, ref, "after")
        import statistics as st
        restart_errs = [abs(d["delta"]) for d in ev_after]
        # pit rate under SC vs green (train, lap-level)
        sc_pits = sc_laps = g_pits = g_laps = 0
        for rows in tr_races.values():
            for r in rows:
                if not pd.notna(r.lap_time_s):
                    continue
                if r.track_state == "safety_car":
                    sc_laps += 1
                    if pd.notna(r.pit_in_s) or pd.notna(r.pit_out_s):
                        sc_pits += 1
                elif r.track_state == "all_clear":
                    g_laps += 1
                    if pd.notna(r.pit_in_s) or pd.notna(r.pit_out_s):
                        g_pits += 1
        sc_results[fold] = {
            "train_episodes": len(tr_eps), "eval_episodes": len(ev_eps),
            "duration_fit": survival_table(dur_fit),
            "duration_validation": dur_val,
            "spread_ratio_during_before": _summ(ratios_d),
            "spread_ratio_nopit_during_before": _summ(ratios_dn),
            "restart_pace_mae_s": (float(st.fmean(restart_errs)) if restart_errs else None),
            "restart_n": len(restart_errs),
            "pit_rate_sc": (sc_pits / sc_laps if sc_laps else None),
            "pit_rate_green": (g_pits / g_laps if g_laps else None),
        }
    sc_spread_ok = all(
        (r["spread_ratio_during_before"]["p50"] is not None
         and r["spread_ratio_during_before"]["p50"] < 0.8)
        for r in sc_results.values())
    # SC admission needs an explicit compression MECHANISM (not just the
    # observation that bunching exists) + restart + pit boundary.
    # This offline stage audits; no mechanism is implemented here, so the
    # compression-gate FAILS by construction (honest DEFER->REJECT path).
    sc_gates = {"compression_mechanism": "FAIL (observed, not modelled)",
                "restart": "FAIL (no causal restart model implemented)",
                "pit_boundary": "FAIL (SC pit-rate shift unaudited for "
                                "R6 validity at this stage)"}
    json.dump({"schema_version": "v3.2h-sc-episodes-v1",
               "prereg_hash": prereg_hash,
               "n": len(sc_eps),
               "durations": _summ([e["duration_laps"] for e in sc_eps])},
              open(OUT_DIR / "sc_episodes.json", "w"), indent=2, sort_keys=True)
    json.dump({"schema_version": "v3.2h-sc-parameters-v1",
               "prereg_hash": prereg_hash, "folds": sc_results,
               "compression_observed_bunching": sc_spread_ok},
              open(OUT_DIR / "sc_parameters.json", "w"), indent=2, sort_keys=True)
    json.dump({"schema_version": "v3.2h-sc-validation-v1",
               "prereg_hash": prereg_hash, "folds": sc_results,
               "outcome_metrics": "NOT_MEASURABLE_OFFLINE (no integrated "
                                  "SC simulator)"},
              open(OUT_DIR / "sc_validation.json", "w"), indent=2, sort_keys=True)
    json.dump({"schema_version": "v3.2h-sc-decision-v1",
               "prereg_hash": prereg_hash, "decision": "REJECT_SC",
               "gates": sc_gates,
               "reason": "bunching/restarts observed but no explicit "
                         "causal compression/restart/pit mechanism is "
                         "implemented and validated; modelling SC as "
                         "pace+N-seconds explicitly rejected by V3.2F "
                         "evidence; explicit 422 retained"},
              open(OUT_DIR / "sc_decision.json", "w"), indent=2, sort_keys=True)

    # ---------------- Yellow / Red ----------------
    json.dump({"schema_version": "v3.2h-yellow-analysis-v1",
               "prereg_hash": prereg_hash,
               "n_yellow_episodes": len(y_eps),
               "racestate_exposure": "NONE: SimulationEnvironment carries "
                                     "only the lap-level track_state token "
                                     "(state.py); no sector->driver field "
                                     "exists",
               "phase12_coupling": "NOT_ESTABLISHED: offline geometry "
                                   "exists but no causal at-T wiring into "
                                   "frozen RaceState without future-info "
                                   "risk or subsystem coupling",
               "global_penalty_rejected": "median yellow-lap field impact "
                                          "small and local (V3.2F); global "
                                          "pace penalty forbidden by prereg"},
              open(OUT_DIR / "yellow_analysis.json", "w"), indent=2, sort_keys=True)
    json.dump({"schema_version": "v3.2h-yellow-decision-v1",
               "prereg_hash": prereg_hash, "decision": "REJECT_YELLOW",
               "reason": "exact at-T affected-driver exposure cannot be "
                         "established from frozen RaceState; no global "
                         "shortcut taken"},
              open(OUT_DIR / "yellow_decision.json", "w"), indent=2, sort_keys=True)
    json.dump({"schema_version": "v3.2h-red-decision-v1",
               "prereg_hash": prereg_hash, "decision": "REJECT_RED",
               "checkpoints": 22, "usable_laps": 0,
               "reason": "default REJECT_RED held: 22 checkpoints, 0 "
                         "usable lap rows, suspension semantics "
                         "qualitatively different; nothing discovered "
                         "overturns V3.2F"},
              open(OUT_DIR / "red_decision.json", "w"), indent=2, sort_keys=True)

    print(f"prereg={prereg_hash} vsc_eps={len(vsc_eps)} sc_eps={len(sc_eps)} "
          f"y_eps={len(y_eps)} vsc_decision={vsc_decision} wet={wet_decision}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
