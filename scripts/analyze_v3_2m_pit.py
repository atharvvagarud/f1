#!/usr/bin/env python3
"""V3.2M: causal pit-lifecycle feasibility + stale coverage recovery.

Research-only. No runtime modification. No 2025. No network.
Deterministic. Verifies M + L prereg hashes. Causal (x_) and future
(y_) tables never mixed in one store.

Stages:
  A  episode audit (214 PIT_CONTEXT): causal-at-start + future labels
  B  source semantics (Stopped/InPit/PitOut/Retired/NumberOfPitStops)
  C  pit-state candidates + return firewall
  D  temporal folds + remaining-duration baselines/validation
  E  STALE pit opportunity (3294 checkpoints, causal only) + projection
  F  materiality + design/kernel/RNG/finish-order/decision scaffolds
"""

from __future__ import annotations

import bisect
import hashlib
import json
import pickle
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "v3" / "v3_2m"
LOUT = ROOT / "results" / "v3" / "v3_2l"
JOUT = ROOT / "results" / "v3" / "v3_2j"
KOUT = ROOT / "results" / "v3" / "v3_2k"
RAW_DIR = ROOT / "data" / "raw" / "fastf1_cache" / "v3_2j_timing"
SQLITE = ROOT / "data" / "raw" / "fastf1_cache" / "fastf1_http_cache.sqlite"
PROCESSED = ROOT / "data" / "v2" / "processed"

KEYS = ("Stopped", "InPit", "PitOut", "Retired")


def check_prereg() -> str:
    pre = json.load(open(OUT / "preregistration.json", encoding="utf-8"))
    expect = (OUT / "preregistration.sha256").read_text(
        encoding="utf-8").strip()
    got = hashlib.sha256(json.dumps(
        pre, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode()).hexdigest()
    if got != expect:
        raise SystemExit(f"M PREREG HASH MISMATCH: {got} != {expect}")
    lpre = json.load(open(LOUT / "preregistration.json", encoding="utf-8"))
    lexp = (LOUT / "preregistration.sha256").read_text(
        encoding="utf-8").strip()
    lgot = hashlib.sha256(json.dumps(lpre, sort_keys=True).encode()
                           ).hexdigest()
    if lgot != lexp:
        raise SystemExit(f"L PREREG HASH MISMATCH: {lgot} != {lexp}")
    return got


def clock_to_seconds(prefix: str) -> float:
    h, m, s = prefix.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_keys(text: str) -> dict:
    per: dict[str, dict] = defaultdict(
        lambda: {"Stopped": [], "InPit": [], "PitOut": [], "Retired": [],
                 "PitStops": [], "any_t": []})
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        if len(line) < 13:
            continue
        try:
            t = clock_to_seconds(line[:12])
            delta = json.loads(line[12:])
        except (ValueError, json.JSONDecodeError):
            continue
        if not isinstance(delta, dict):
            continue
        lines = delta.get("Lines")
        if not isinstance(lines, dict):
            continue
        for num, entry in lines.items():
            if not isinstance(entry, dict):
                continue
            num = str(num)
            per[num]["any_t"].append(t)
            for k in KEYS:
                v = entry.get(k)
                if isinstance(v, bool):
                    per[num][k].append((t, v))
            nps = entry.get("NumberOfPitStops")
            if isinstance(nps, int):
                per[num]["PitStops"].append((t, nps))
    for num in per:
        for k in ("Stopped", "InPit", "PitOut", "Retired", "PitStops",
                  "any_t"):
            per[num][k].sort(key=lambda e: e[0] if isinstance(e, tuple)
                             else e)
    return per


def latest_leq(seq: list, T: float):
    if not seq:
        return (None, None)
    ts = [e[0] for e in seq]
    i = bisect.bisect_right(ts, T) - 1
    return seq[i] if i >= 0 else (None, None)


def first_gt(seq: list, T: float, value=None):
    for t, v in seq:
        if t > T and (value is None or v == value):
            return (t, v)
    return (None, None)


def last_transition_before(seq: list, T: float, frm, to):
    """Last time value went frm->to at or before T (None if never)."""
    prev = None
    last = None
    for t, v in seq:
        if t > T:
            break
        if prev is not None and prev == frm and v == to:
            last = t
        prev = v
    return last


def main() -> int:
    t0 = time.perf_counter()
    m_hash = check_prereg()
    OUT.mkdir(parents=True, exist_ok=True)
    import pandas as pd  # noqa: E402

    corpus = json.load(open(LOUT / "episode_corpus.json", encoding="utf-8"))
    assert corpus["n_episodes"] == 476, corpus["n_episodes"]
    episodes = corpus["episodes"]
    pit_eps = [e for e in episodes if e["x_class"] == "PIT_CONTEXT"]
    assert len(pit_eps) == 214, len(pit_eps)
    print(f"episodes=476 pit_context={len(pit_eps)}", flush=True)

    manifest = json.load(open(JOUT / "source_manifest.json", encoding="utf-8"))
    rec_by_race = {r["race_id"]: r for r in manifest["records"]}

    def load_stream(race_id: str, season: int):
        rec = rec_by_race[race_id]
        if rec["retrieval_status"] == "local_cache":
            cc = sqlite3.connect(SQLITE)
            raw = None
            for (v,) in cc.execute("select value from responses").fetchall():
                d = pickle.loads(v)
                if d.get("url") == rec["source_locator"]:
                    raw = d["_content"]
                    break
            cc.close()
            if raw is None:
                return None
            if isinstance(raw, (bytes, bytearray)):
                raw = bytes(raw).decode("utf-8-sig")
            return raw
        p = RAW_DIR / str(season) / f"{race_id}.jsonStream"
        return p.read_text(encoding="utf-8-sig") if p.exists() else None

    n2d_cache: dict = {}

    def num_to_driver(race_id: str, season: int) -> dict:
        if (race_id, season) not in n2d_cache:
            df = pd.read_parquet(
                PROCESSED / "driver_lap_state_d9" / f"season={season}" /
                f"driver_lap_state_d9__d9-{season}.parquet",
                columns=["race_id", "driver_id", "driver_number"])
            df = df[df["race_id"] == race_id]
            n2d_cache[(race_id, season)] = {
                str(int(n)): d for d, n in
                df[["driver_id", "driver_number"]].drop_duplicates()
                .itertuples(index=False)}
        return n2d_cache[(race_id, season)]

    # ---- parse streams for all races needed (pit episodes + stale cps) ----
    off_doc = json.load(open(LOUT / "offender_opportunity.json",
                             encoding="utf-8"))
    stale_races = sorted({o["race_id"] for o in off_doc["offenders"]})
    pit_races = sorted({e["race_id"] for e in pit_eps})
    races = sorted(set(stale_races) | set(pit_races))
    print(f"races to parse: {len(races)}", flush=True)
    streams: dict = {}
    for ri, race_id in enumerate(races):
        season = int(race_id.split("-")[0])
        assert season != 2025
        raw = load_stream(race_id, season)
        streams[race_id] = parse_keys(raw) if raw is not None else None
        if (ri + 1) % 30 == 0:
            print(f"  parsed {ri + 1}/{len(races)} "
                  f"wall={time.perf_counter()-t0:.0f}s", flush=True)

    # ================= STAGE A: 214 episode audit =================
    causal_rows, future_rows = [], []
    for e in pit_eps:
        race_id, season, did = e["race_id"], e["season"], e["driver"]
        start_t = float(e["x_stop_start_t"])
        n2d = num_to_driver(race_id, season)
        rev = {d: n for n, d in n2d.items()}
        num = rev.get(did)
        per = streams.get(race_id) or {}
        kd = per.get(num) if num else None
        st_t, st_v = latest_leq(kd["Stopped"], start_t) if kd else (None,
                                                                   None)
        ip_t, ip_v = latest_leq(kd["InPit"], start_t) if kd else (None, None)
        po_t, po_v = latest_leq(kd["PitOut"], start_t) if kd else (None, None)
        rt_t, rt_v = latest_leq(kd["Retired"], start_t) if kd else (None,
                                                                   None)
        ps_t, ps_v = latest_leq(kd["PitStops"], start_t) if kd else (None,
                                                                    None)
        inpit_entry = (last_transition_before(kd["InPit"], start_t, False,
                                              True) if kd else None)
        pitout_last_true = None
        if kd:
            for t, v in kd["PitOut"]:
                if t <= start_t and v is True:
                    pitout_last_true = t
        causal_rows.append({
            "race_id": race_id, "season": season, "driver": did,
            "start_t": start_t, "x_initial_unknown": e["x_initial_unknown"],
            "x_last_lap": e["x_last_lap"], "x_last_pos": e["x_last_pos"],
            "x_last_pit": e["x_last_pit"], "x_compound": e["x_compound"],
            "x_tyre_life": e["x_tyre_life"], "x_frac": e["x_frac"],
            "x_stage": e["x_stage"], "x_track": e["x_track"],
            "inpit_at_start": ip_v, "inpit_update_t": ip_t,
            "inpit_entry_t": inpit_entry,
            "elapsed_in_pit_at_start": (
                start_t - inpit_entry if inpit_entry is not None else None),
            "pitout_at_start": po_v, "pitout_update_t": po_t,
            "pitout_last_true_t": pitout_last_true,
            "stopped_at_start": st_v, "stopped_update_t": st_t,
            "retired_at_start": rt_v, "retired_update_t": rt_t,
            "pitstops_at_start": ps_v, "pitstops_update_t": ps_t,
        })
        # future labels only
        po_ft, _ = first_gt(kd["PitOut"], start_t, True) if kd else (None,
                                                                    None)
        clr_ft, _ = first_gt(kd["Stopped"], start_t, False) if kd else (
            None, None)
        r_ft, _ = first_gt(kd["Retired"], start_t, True) if kd else (None,
                                                                    None)
        y_ret = e["y_return_t"]
        future_rows.append({
            "race_id": race_id, "season": season, "driver": did,
            "start_t": start_t,
            "y_return_t": y_ret,
            "y_remaining_to_d9": (y_ret - start_t if y_ret is not None
                                  else None),
            "y_pitout_t": po_ft,
            "y_remaining_to_pitout": (po_ft - start_t if po_ft is not None
                                      else None),
            "y_stopped_clear_t": clr_ft,
            "y_retired_after_t": e["y_retired_after"],
            "y_retired_raw_after_t": r_ft,
            "y_returned": e["y_returned"],
            "y_terminal": e["y_terminal"],
        })
    json.dump({"schema_version": "v3.2m-pit-episode-causal-v1",
               "preregistration_sha256": m_hash,
               "n": len(causal_rows),
               "note": "causal at/before stop start ONLY; no future fields",
               "rows": causal_rows},
              open(OUT / "pit_episode_causal.json", "w"))
    json.dump({"schema_version": "v3.2m-pit-episode-future-v1",
               "preregistration_sha256": m_hash,
               "n": len(future_rows),
               "note": "FUTURE LABELS ONLY: never model/runtime inputs",
               "rows": future_rows},
              open(OUT / "pit_episode_future.json", "w"))
    print(f"stage A done wall={time.perf_counter()-t0:.0f}s", flush=True)

    # ================= STAGE B: source semantics =================
    sem = {"schema_version": "v3.2m-source-semantics-v1",
           "preregistration_sha256": m_hash, "per_key": {},
           "season_availability": {}, "pitstops_availability": {}}
    for k in KEYS:
        n_races_with = sum(
            1 for r in races if streams.get(r) and any(
                len(streams[r][num][k]) > 0 for num in streams[r]))
        n_updates = sum(
            len(streams[r][num][k]) for r in races if streams.get(r)
            for num in streams[r])
        sem["per_key"][k] = {"n_races_with_updates": n_races_with,
                             "n_races_parsed": len(races),
                             "n_updates": n_updates}
    # persistence: fraction of True values still True 60/180s later
    # (sampled on pit-race streams, InPit/Stopped only; bounded work)
    for k in ("InPit", "Stopped"):
        still60 = still180 = tot = 0
        for r in pit_races:
            per = streams.get(r)
            if not per:
                continue
            for num in per:
                seq = per[num][k]
                for i, (t, v) in enumerate(seq):
                    if v is not True:
                        continue
                    tot += 1
                    j = bisect.bisect_right([e[0] for e in seq], t + 60)
                    # latest value as of t+60: scan window
                    cur = v
                    for t2, v2 in seq[i + 1:j]:
                        cur = v2
                    if cur is True:
                        still60 += 1
                    j2 = bisect.bisect_right([e[0] for e in seq], t + 180)
                    cur2 = cur
                    for t2, v2 in seq[i + 1:j2]:
                        cur2 = v2
                    if cur2 is True:
                        still180 += 1
                    if tot >= 4000:
                        break
                if tot >= 4000:
                    break
            if tot >= 4000:
                break
        sem["per_key"][k]["persist_true_60s"] = still60 / tot if tot else None
        sem["per_key"][k]["persist_true_180s"] = (
            still180 / tot if tot else None)
        sem["per_key"][k]["persistence_sample_n"] = tot
    # NumberOfPitStops availability by season
    for r in races:
        season = int(r.split("-")[0])
        per = streams.get(r)
        has = bool(per and any(len(per[num]["PitStops"]) > 0
                                for num in per))
        s = sem["pitstops_availability"].setdefault(str(season),
                                                    {"races": 0, "with": 0})
        s["races"] += 1
        s["with"] += has
    for k in KEYS:
        by_sea = Counter()
        for r in races:
            season = str(int(r.split("-")[0]))
            per = streams.get(r)
            if per and any(len(per[num][k]) > 0 for num in per):
                by_sea[season] += 1
        sem["season_availability"][k] = dict(sorted(by_sea.items()))
    # PitOut pulse behavior: True->False clearing delay distribution
    clears = []
    for r in pit_races:
        per = streams.get(r)
        if not per:
            continue
        for num in per:
            seq = per[num]["PitOut"]
            for i in range(1, len(seq)):
                if seq[i - 1][1] is True and seq[i][1] is False:
                    clears.append(seq[i][0] - seq[i - 1][0])
    clears.sort()
    sem["pitout_pulse"] = {
        "n_true_false_cycles": len(clears),
        "median_true_hold_s": (clears[len(clears) // 2] if clears else None),
        "p90_true_hold_s": (clears[int(len(clears) * 0.9)] if clears
                            else None),
        "note": "PitOut True behaves as a pulse (set then cleared), "
                "not a persistent state",
    }
    # Stopped clearing behavior: True->False delay
    scl = []
    for r in pit_races:
        per = streams.get(r)
        if not per:
            continue
        for num in per:
            seq = per[num]["Stopped"]
            for i in range(1, len(seq)):
                if seq[i - 1][1] is True and seq[i][1] is False:
                    scl.append(seq[i][0] - seq[i - 1][0])
    scl.sort()
    sem["stopped_clearing"] = {
        "n_true_false_cycles": len(scl),
        "median_true_hold_s": (scl[len(scl) // 2] if scl else None),
        "p90_true_hold_s": (scl[int(len(scl) * 0.9)] if scl else None),
        "note": "Stopped True->False clearing latency; long/no clearing "
                "means Stopped persists stale after resume (L finding)",
    }
    sem["notes"] = [
        "Field names are not documentation: persistence measured above.",
        "TimingAppData stint/compound: D9 canonical tyre fields compound/tyre_life used as causal-at-T proxy (see causal rows); dedicated TimingAppData stream audit deferred (NOT_RUN) unless admission proceeds.",
        "Canonical pit-stop tables: pit_stops_completed_so_far (D9) + NumberOfPitStops stream key counted in season availability; no fabricated mapping to timing-line crossing.",
        "Track state: D9 track_status at stop start (x_track in causal rows).",
    ]
    json.dump(sem, open(OUT / "source_semantics.json", "w"))
    print(f"stage B done wall={time.perf_counter()-t0:.0f}s", flush=True)

    # ================= STAGE C: candidates + return firewall ============
    cand_rows = []
    for c, f in zip(causal_rows, future_rows):
        ip = c["inpit_at_start"]
        po = c["pitout_at_start"]
        el = c["elapsed_in_pit_at_start"]
        if po is True:
            cand = "PIT_EXIT_TRANSITION"
        elif ip is True and el is not None and el <= 120:
            cand = "PIT_SERVICE_ACTIVE"
        elif ip is True:
            cand = "PIT_LANE_STOPPED"
        else:
            cand = "PIT_CONTEXT_AMBIGUOUS"
        cand_rows.append({"candidate": cand, "returned": f["y_returned"],
                          "terminal": f["y_terminal"]})
    cand_counts = Counter(c["candidate"] for c in cand_rows)
    fw = {"schema_version": "v3.2m-return-firewall-v1",
          "preregistration_sha256": m_hash,
          "n_pit_context": len(future_rows),
          "overall": {},
          "by_candidate": {},
          "by_stage": {},
          "non_return_taxonomy": {},
          "verdict": ""}
    n_ret = sum(1 for f in future_rows if f["y_returned"])
    fw["overall"] = {"n": len(future_rows), "returned": n_ret,
                     "p_return": n_ret / len(future_rows)}
    for cand in sorted(cand_counts):
        sub = [c for c in cand_rows if c["candidate"] == cand]
        nr = sum(1 for c in sub if c["returned"])
        fw["by_candidate"][cand] = {"n": len(sub), "returned": nr,
                                    "p_return": nr / len(sub) if sub
                                    else None}
    for st in ("EARLY", "MID", "LATE"):
        sub = [f for f, c in zip(future_rows, causal_rows)
               if c["x_stage"] == st]
        nr = sum(1 for f in sub if f["y_returned"])
        fw["by_stage"][st] = {"n": len(sub), "returned": nr,
                              "p_return": nr / len(sub) if sub else None}
    # non-return taxonomy (future labels, diagnostic only)
    tax = Counter()
    for c, f in zip(causal_rows, future_rows):
        if f["y_returned"]:
            continue
        if f["y_retired_after_t"] is not None or (
                f["y_retired_raw_after_t"] is not None):
            tax["garage_retirement_retired_true_after"] += 1
        elif c["x_track"] in ("red_flag",):
            tax["red_flag_affected"] += 1
        elif c["x_track"] in ("safety_car", "vsc", "vsc_ending"):
            tax["neutralised_affected"] += 1
        elif f["y_stopped_clear_t"] is not None:
            tax["stopped_cleared_but_no_d9_return"] += 1
        elif f["y_pitout_t"] is not None:
            tax["pitout_but_no_d9_return"] += 1
        else:
            tax["no_return_no_clear_no_pitout"] += 1
    fw["non_return_taxonomy"] = dict(tax)
    p_all = fw["overall"]["p_return"]
    p_best = max((v["p_return"] for v in fw["by_candidate"].values()
                  if v["p_return"] is not None), default=0.0)
    if p_best >= 0.95 and fw["non_return_taxonomy"].get(
            "no_return_no_clear_no_pitout", 0) == 0:
        fw["verdict"] = "RETURN_STRUCTURAL"
    elif p_best >= 0.80:
        fw["verdict"] = "RETURN_LIKELY_BUT_TERMINAL_UNCERTAINTY_REMAINS"
    else:
        fw["verdict"] = ("REJECT_CANDIDATE_SCOPE: routine service not "
                         "causally separable from garage/terminal states")
    json.dump({"schema_version": "v3.2m-pit-state-candidates-v1",
               "preregistration_sha256": m_hash,
               "rule": "causal-only: PitOut latest True -> EXIT; InPit True "
                       "+ entry<=120s -> SERVICE_ACTIVE; InPit True "
                       "(entry old/unknown) -> LANE_STOPPED; else AMBIGUOUS",
               "counts": dict(cand_counts)},
              open(OUT / "pit_state_candidates.json", "w"))
    json.dump(fw, open(OUT / "return_firewall.json", "w"))
    print(f"stage C done wall={time.perf_counter()-t0:.0f}s verdict="
          f"{fw['verdict']}", flush=True)

    # ================= STAGE D: folds + duration =======================
    folds = [("<=2020", 2021), ("<=2021", 2022), ("<=2022", 2023),
             ("<=2023", 2024)]
    ret = [(c, f) for c, f in zip(causal_rows, future_rows)
           if f["y_returned"] and f["y_remaining_to_d9"] is not None
           and f["y_remaining_to_d9"] >= 0]
    dur = {"schema_version": "v3.2m-duration-validation-v1",
           "preregistration_sha256": m_hash,
           "target": "remaining_duration(T) = first D9 crossing after stop "
                     "start minus start (mechanism target TBD vs PitOut; "
                     "both reported, choice by semantics not error)",
           "n_returned": len(ret),
           "folds": {}, "baselines": {}, "stability_verdict": ""}
    import statistics as stats  # noqa: E402
    for name, ev in folds:
        tr = [f["y_remaining_to_d9"] for c, f in ret if c["season"] < ev]
        te = [(c, f["y_remaining_to_d9"]) for c, f in ret
              if c["season"] == ev]
        if not tr or not te:
            dur["folds"][name] = {"n_train": len(tr), "n_eval": len(te),
                                  "status": "INSUFFICIENT_DATA"}
            continue
        med = stats.median(tr)
        by_stage_med = {}
        for st in ("EARLY", "MID", "LATE"):
            s = [f["y_remaining_to_d9"] for c, f in ret
                 if c["season"] < ev and c["x_stage"] == st]
            by_stage_med[st] = stats.median(s) if s else None
        errs, errs_stage, signed = [], [], []
        for c, y in te:
            errs.append(abs(y - med))
            signed.append(y - med)
            sm = by_stage_med.get(c["x_stage"])
            errs_stage.append(abs(y - sm) if sm is not None else None)
        errs_stage = [e for e in errs_stage if e is not None]
        errs.sort()
        dur["folds"][name] = {
            "n_train": len(tr), "n_eval": len(te), "status": "SCORED",
            "global_median_train": med,
            "eval_mae": sum(errs) / len(errs),
            "eval_medae": errs[len(errs) // 2],
            "eval_p90ae": errs[int(len(errs) * 0.9)],
            "eval_bias": sum(signed) / len(signed),
            "eval_mae_stage_median": (sum(errs_stage) / len(errs_stage)
                                      if errs_stage else None),
            "eval_max": max(errs),
        }
    all_y = sorted(f["y_remaining_to_d9"] for _, f in ret)
    dur["baselines"] = {
        "global_median": (stats.median(all_y) if all_y else None),
        "global_p90": (all_y[int(len(all_y) * 0.9)] if all_y else None),
        "global_max": (max(all_y) if all_y else None),
        "global_n": len(all_y),
        "note": "circuit/season/elapsed-conditional tables only if "
                "returned N supports them (N expected small)",
    }
    # elapsed-conditional check: does elapsed-in-pit predict remaining?
    el_pairs = [(c["elapsed_in_pit_at_start"], f["y_remaining_to_d9"])
                for c, f in ret
                if c["elapsed_in_pit_at_start"] is not None]
    dur["elapsed_conditional"] = {
        "n": len(el_pairs),
        "note": "P(additional delay | elapsed): pit entry time known "
                "only when False->True observed; unknown-entry rows excluded",
    }
    scored = [v for v in dur["folds"].values()
              if v.get("status") == "SCORED"]
    if len(scored) < 2 or any(v["n_eval"] < 5 for v in scored):
        dur["stability_verdict"] = ("DURATION_MODEL_FAILURE: too few "
                                    "returned episodes per fold for stable "
                                    "temporal validation")
    elif max(v["eval_mae"] for v in scored) > 2 * min(
            v["eval_mae"] for v in scored):
        dur["stability_verdict"] = ("DURATION_MODEL_FAILURE: fold MAE "
                                    "unstable across seasons")
    else:
        dur["stability_verdict"] = "TEMPORALLY_ADEQUATE"
    json.dump({"schema_version": "v3.2m-temporal-splits-v1",
               "preregistration_sha256": m_hash, "folds": folds,
               "rule": "season-forward only; no random split; 2025 forbidden"},
              open(OUT / "temporal_splits.json", "w"))
    json.dump({"schema_version": "v3.2m-duration-target-v1",
               "preregistration_sha256": m_hash,
               "definition": dur["target"]},
              open(OUT / "duration_target.json", "w"))
    json.dump({"schema_version": "v3.2m-duration-baselines-v1",
               "preregistration_sha256": m_hash,
               "baselines": dur["baselines"]},
              open(OUT / "duration_baselines.json", "w"))
    json.dump({"schema_version": "v3.2m-duration-model-v1",
               "preregistration_sha256": m_hash,
               "model": "elapsed-conditional empirical distribution "
                        "(admitted only if validation passes); no ML; no "
                        "driver identity",
               "elapsed_conditional": dur["elapsed_conditional"]},
              open(OUT / "duration_model.json", "w"))
    json.dump(dur, open(OUT / "duration_validation.json", "w"))
    print(f"stage D done wall={time.perf_counter()-t0:.0f}s "
          f"n_ret={len(ret)} verdict={dur['stability_verdict']}", flush=True)

    # ================= STAGE E: stale opportunity =====================
    # Causal-only offender classes. STRICT contract: stopped True AND
    # InPit True AND sufficient anchor AND not J-retired.
    by_cp: dict = defaultdict(list)
    for o in off_doc["offenders"]:
        by_cp[(o["race_id"], o["frame_index"])].append(o)
    assert len(by_cp) == 3294, len(by_cp)
    opp = {"schema_version": "v3.2m-stale-pit-opportunity-v1",
           "preregistration_sha256": m_hash,
           "n_checkpoints": len(by_cp),
           "offender_classes": {}, "checkpoint_rollup": {},
           "single_vs_multi": {}, "by_season": {}, "by_stage": {}}
    cp_class: dict = {}
    for key, offs in by_cp.items():
        cls = []
        for o in offs:
            if o["j_retired"] is True:
                c = "J_RETIRED"
            elif (o["stopped_at_T"] is True and o["inpit_at_T"] is True
                  and o["oclass"] == "ADDRESSABLE"):
                c = "PIT_LIFECYCLE_CANDIDATE"
            elif o["stopped_at_T"] is True:
                c = "GENERAL_LIFECYCLE"
            elif o["stopped_at_T"] is False:
                c = "AMBIGUOUS"
            else:
                c = "NO_PIT_SIGNAL"
            cls.append(c)
        opp["offender_classes"].update(Counter())
        u = set(cls)
        if u <= {"J_RETIRED", "PIT_LIFECYCLE_CANDIDATE"} and (
                "PIT_LIFECYCLE_CANDIDATE" in u):
            cp = ("PIT_FULLY_ADDRESSABLE" if "J_RETIRED" not in u
                  else "J_PLUS_PIT_ADDRESSABLE")
        elif u <= {"J_RETIRED"}:
            cp = "J_ONLY"
        elif "PIT_LIFECYCLE_CANDIDATE" in u and "GENERAL_LIFECYCLE" in u:
            cp = "PIT_PLUS_GENERAL_MIXED"
        elif "PIT_LIFECYCLE_CANDIDATE" in u:
            cp = "PIT_PLUS_OTHER_MIXED"
        elif "GENERAL_LIFECYCLE" in u:
            cp = "GENERAL_ONLY"
        else:
            cp = "OTHER"
        cp_class[key] = (cp, cls, offs)
    roll = Counter(cp for cp, _, _ in cp_class.values())
    opp["checkpoint_rollup"] = dict(sorted(roll.items()))
    flat = Counter(c for _, cls, _ in cp_class.values() for c in cls)
    opp["offender_classes"] = dict(sorted(flat.items()))
    sm = Counter("multi" if len(v[1]) > 1 else "single"
                 for v in cp_class.values())
    opp["single_vs_multi"] = dict(sm)
    sea = Counter()
    stg = Counter()
    for (rid, _), (cp, _, offs) in cp_class.items():
        if cp in ("PIT_FULLY_ADDRESSABLE", "J_PLUS_PIT_ADDRESSABLE"):
            sea[str(offs[0]["season"])] += 1
            stg[str(offs[0]["stage"])] += 1
    opp["by_season"] = dict(sorted(sea.items()))
    opp["by_stage"] = dict(sorted(stg.items()))
    json.dump(opp, open(OUT / "stale_pit_opportunity.json", "w"))
    n_pit = (roll.get("PIT_FULLY_ADDRESSABLE", 0)
             + roll.get("J_PLUS_PIT_ADDRESSABLE", 0))
    proj = {"schema_version": "v3.2m-coverage-projection-v1",
            "preregistration_sha256": m_hash,
            "before": {"eligible": 3678, "total": 9644, "fraction": 0.3814},
            "pit_addressable_checkpoints": n_pit,
            "projected": {"eligible": 3678 + n_pit, "total": 9644,
                           "fraction": round((3678 + n_pit) / 9644, 4)},
            "gain_n": n_pit,
            "gain_pp": round(n_pit / 9644 * 100, 2),
            "note": "PROJECTION ONLY, not actual coverage"}
    json.dump(proj, open(OUT / "coverage_projection.json", "w"))
    print(f"stage E done wall={time.perf_counter()-t0:.0f}s "
          f"pit_addressable={n_pit}", flush=True)

    # ================= STAGE F: materiality + design scaffolds =========
    mat = {"schema_version": "v3.2m-materiality-v1",
           "preregistration_sha256": m_hash,
           "n_recovered_checkpoints": n_pit,
           "gain_pp": proj["gain_pp"],
           "firewall_verdict": fw["verdict"],
           "duration_verdict": dur["stability_verdict"],
           "verdict": "",
           "rationale": ""}
    if fw["verdict"].startswith("REJECT") or dur[
            "stability_verdict"].startswith("DURATION_MODEL_FAILURE"):
        mat["verdict"] = "IMMATERIAL_OR_INADMISSIBLE"
        mat["rationale"] = ("science gates fail first: no runtime "
                            "integration regardless of N; recorded as "
                            "product/scientific tradeoff per stopping rule")
    elif proj["gain_pp"] < 1.0:
        mat["verdict"] = "IMMATERIAL"
        mat["rationale"] = ("sub-1pp gain cannot justify kernel/presence "
                            "complexity + new RNG domain + poison surface")
    else:
        mat["verdict"] = "MATERIAL"
        mat["rationale"] = ("gain justifies complexity ONLY if all ten "
                            "admission gates pass")
    json.dump(mat, open(OUT / "materiality.json", "w"))

    design = {
        "schema_version": "v3.2m-initial-pit-state-design-v1",
        "preregistration_sha256": m_hash,
        "status": "DESIGN_ONLY_NO_IMPLEMENTATION",
        "semantics": "at T driver is in admitted pit lifecycle state; "
                     "simulator initialises driver with last causally valid "
                     "race-distance state + pit lifecycle state + sampled "
                     "additional pit delay; during delay driver makes no "
                     "normal racing progress; after delay resumes accepted "
                     "MC2-E dynamics; others continue; no teleportation, no "
                     "fabricated gap reset, no historical actual return time",
        "component": "raceintel/simulation/pit_lifecycle.py (isolated, "
                     "repo conventions; identify/use precomputed admitted "
                     "pit state, sample additional delay, provide MC2 "
                     "initial pit condition; no network/results/future)",
    }
    json.dump(design, open(OUT / "initial_pit_state_design.json", "w"))
    kernel = {
        "schema_version": "v3.2m-kernel-boundary-v1",
        "preregistration_sha256": m_hash,
        "finding": "MC2 represents post-T pits ONLY as forward R6 "
                   "decisions (stint target age -> pit_effective_loss_s "
                   "added once, pit_count++, tyre reset). No driver can "
                   "begin inside a pit process: all drivers start ACTIVE "
                   "with race_time_s and are immediately scheduled for "
                   "the next lap. An initial remaining pit delay would "
                   "belong architecturally to SimulationState/adapter "
                   "output (initial condition) + a hold in the event loop "
                   "(kernel). Finish order is sorted (finish_time, "
                   "driver_id) over full-distance finishers; no terminal "
                   "classification exists (DNF unsupported).",
        "verdict": "LOCAL_KERNEL_EXTENSION",
        "detail": "initial-condition extension (presence/adapter) plus a "
                  "local event-loop hold/resume; R3/R6 pace science "
                  "untouched. Verdict is conditional: reached only if "
                  "science + materiality pass; with REJECT verdicts "
                  "above, boundary is NOT crossed (no implementation).",
    }
    json.dump(kernel, open(OUT / "kernel_boundary.json", "w"))
    json.dump(
        {"schema_version": "v3.2m-rng-contract-v1",
         "preregistration_sha256": m_hash,
         "status": "RESERVED_ONLY_NOT_IMPLEMENTED",
         "domain": "mc2-initial-pit-delay",
         "rule": "project RNG conventions; existing MC2-E streams "
                 "untouched; old-state sims consume zero new draws"},
        open(OUT / "rng_contract.json", "w"))
    json.dump(
        {"schema_version": "v3.2m-finish-order-v1",
         "preregistration_sha256": m_hash,
         "semantics": "admitted routine-pit driver is expected to return; "
                      "no terminal classification semantics added. If "
                      "terminal branching were required: STOP runtime "
                      "integration (rejected/general lifecycle science)."},
        open(OUT / "finish_order.json", "w"))
    if (fw["verdict"].startswith("REJECT") or dur["stability_verdict"]
            .startswith("DURATION_MODEL_FAILURE")):
        decision = "REJECT_PIT_LIFECYCLE"
    elif mat["verdict"] != "MATERIAL":
        decision = "REJECT_PIT_LIFECYCLE"
    else:
        decision = "ADMIT_RESTRICTED_PIT_LIFECYCLE"
    json.dump({"schema_version": "v3.2m-decision-v1",
               "preregistration_sha256": m_hash,
               "decision": decision,
               "gates": {"return_firewall": fw["verdict"],
                         "duration": dur["stability_verdict"],
                         "materiality": mat["verdict"]}},
              open(OUT / "decision.json", "w"))
    for name, payload in [
            ("future_poison",
             {"schema_version": "v3.2m-future-poison-v1",
              "verdict": "NOT_RUN",
              "note": "representative-state poison (strip post-T timing, "
                      "pits, laps, position, race control, results) required "
                      "only if admitted; research-only run needs no runtime"}),
            ("runtime_integration",
             {"schema_version": "v3.2m-runtime-integration-v1",
              "status": "NOT_APPLICABLE",
              "note": "no runtime modification (decision %s)" % decision}),
            ("old_state_parity",
             {"schema_version": "v3.2m-old-state-parity-v1",
              "status": "NOT_APPLICABLE",
              "note": "no runtime change: 3678 eligible + dry-green "
                      "7ae97c3c untouched"}),
            ("new_state_validation",
             {"schema_version": "v3.2m-new-state-validation-v1",
              "status": "NOT_RUN",
              "note": "500-1000 sim validity runs required only if "
                      "admitted"}),
            ("coverage_after",
             {"schema_version": "v3.2m-coverage-after-v1",
              "method": "identity (no integration)",
              "total": 9644, "eligible": 3678, "fraction": 0.3814,
              "gain_vs_before": 0}),
            ("performance",
             {"schema_version": "v3.2m-performance-v1",
              "status": "NOT_APPLICABLE",
              "note": "no runtime artifact; no perf measurement owed"}),
            ("reproducibility",
             {"schema_version": "v3.2m-reproducibility-v1",
              "m_prereg": m_hash, "rng": "stdlib deterministic; seeds "
                         "pinned in tests",
              "command": "python3 scripts/analyze_v3_2m_pit.py"}),
    ]:
        json.dump(payload, open(OUT / f"{name}.json", "w"))
    print(f"stage F done decision={decision} "
          f"wall={time.perf_counter()-t0:.0f}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())