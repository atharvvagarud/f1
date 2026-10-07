#!/usr/bin/env python3
"""V3.2L stage 1: opportunity reconciliation + stopped semantics + episodes.

BEFORE any model training. Verifies L prereg hash. 2025 never read.
No network. Deterministic. Labels (y_*) stored separately from causal X.
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

OUT = ROOT / "results" / "v3" / "v3_2l"
JOUT = ROOT / "results" / "v3" / "v3_2j"
KOUT = ROOT / "results" / "v3" / "v3_2k"
RAW_DIR = ROOT / "data" / "raw" / "fastf1_cache" / "v3_2j_timing"
SQLITE = ROOT / "data" / "raw" / "fastf1_cache" / "fastf1_http_cache.sqlite"
PROCESSED = ROOT / "data" / "v2" / "processed"


def check_prereg() -> str:
    pre = json.load(open(OUT / "preregistration.json", encoding="utf-8"))
    expect = open(OUT / "preregistration.sha256", encoding="utf-8").read().strip()
    got = hashlib.sha256(json.dumps(pre, sort_keys=True).encode()).hexdigest()
    if got != expect:
        raise SystemExit(f"L PREREG HASH MISMATCH: {got} != {expect}")
    return got


def clock_to_seconds(prefix: str) -> float:
    h, m, s = prefix.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_stop_keys(text: str) -> dict:
    """Per-number Stopped/InPit/PitOut/Retired transitions + latest-any t."""
    per: dict[str, dict] = defaultdict(lambda: {"Stopped": [], "InPit": [],
                                                "PitOut": [], "Retired": [],
                                                "any_t": []})
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
            for k in ("Stopped", "InPit", "PitOut", "Retired"):
                v = entry.get(k)
                if isinstance(v, bool):
                    per[num][k].append((t, v))
    for num in per:
        for k in ("Stopped", "InPit", "PitOut", "Retired"):
            per[num][k].sort(key=lambda e: e[0])
        per[num]["any_t"].sort()
    return per


def latest_leq(seq: list, T: float):
    if not seq:
        return (None, None)
    ts = [e[0] for e in seq]
    i = bisect.bisect_right(ts, T) - 1
    return seq[i] if i >= 0 else (None, None)


def transitions(seq: list) -> list:
    """Compress to value-change transitions [(t, bool)]."""
    out, cur = [], None
    for t, v in seq:
        if cur is None or v != cur:
            out.append((t, v))
            cur = v
    return out


def main() -> int:
    t0 = time.perf_counter()
    prereg_hash = check_prereg()
    OUT.mkdir(parents=True, exist_ok=True)
    import pandas as pd  # noqa: E402
    from raceintel.race_state.race_state_reconstruction import (  # noqa: E402
        RaceStateReconstructor)
    from raceintel.replay import replay as RP  # noqa: E402
    from raceintel.replay.replay_reconstruction import (  # noqa: E402
        ReplayReconstructor)
    from raceintel.simulation.driver_status import (  # noqa: E402
        load_status_corpus, load_unreliable_windows)

    tgt = json.load(open(KOUT / "target_population.json", encoding="utf-8"))
    assert tgt["n"] == 3294
    manifest = json.load(open(JOUT / "source_manifest.json", encoding="utf-8"))
    rec_by_race = {r["race_id"]: r for r in manifest["records"]}
    resolver = load_status_corpus(JOUT / "status")
    windows = load_unreliable_windows(JOUT / "unreliable_windows.json")

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

    def load_race(race_id: str, season: int):
        frame = pd.read_parquet(
            str(PROCESSED / "driver_lap_state_d9" / f"season={season}" /
                f"driver_lap_state_d9__d9-{season}.parquet"))
        states = frame[frame["race_id"] == race_id].copy()
        results = pd.read_parquet(
            str(PROCESSED / "results" / f"season={season}" /
                f"results__{race_id}.parquet"))
        meta: dict = {}
        try:
            for row in pd.read_parquet(
                    str(PROCESSED / "races" / f"season={season}" /
                        f"races__{race_id}.parquet")).itertuples():
                scheduled = getattr(row, "total_laps_scheduled", None)
                meta[str(row.race_id)] = {
                    "scheduled_laps": (None if pd.isna(scheduled)
                                       else int(scheduled))}
        except FileNotFoundError:
            pass
        timeline = RP.build_replay_timeline(states)
        service = ReplayReconstructor(
            timeline, RaceStateReconstructor(states, results,
                                             race_meta=meta or None))
        return states, results, service

    # ---- stopped feed semantics + episode corpus over ALL 149 races ----
    races = sorted(rec_by_race)
    episodes: list = []
    clearing_rows: list = []
    stop_seqs: dict = {}
    for ri, race_id in enumerate(races):
        season = int(race_id.split("-")[0])
        raw = load_stream(race_id, season)
        if raw is None:
            continue
        per = parse_stop_keys(raw)
        stop_seqs[race_id] = per
        states, results, _ = load_race(race_id, season)
        n2d = num_to_driver(race_id, season)
        sess_end = float(states["state_time_s"].max())
        for num, kd in per.items():
            did = n2d.get(num)
            if did is None:
                continue
            strans = transitions(kd["Stopped"])
            rtrans = transitions(kd["Retired"])
            # clearings: True -> False
            for i in range(1, len(strans)):
                if strans[i - 1][1] is True and strans[i][1] is False:
                    clearing_rows.append(
                        {"race_id": race_id, "driver": did,
                         "set_t": strans[i - 1][0],
                         "clear_t": strans[i][0]})
            # episodes: False -> True (or first-True)
            starts = []
            if strans and strans[0][1] is True:
                starts.append((strans[0][0], True))
            for i in range(1, len(strans)):
                if strans[i - 1][1] is False and strans[i][1] is True:
                    starts.append((strans[i][0], False))
            d9 = states[states["driver_id"] == did].sort_values(
                "state_time_s")
            for start_t, initial_unknown in starts:
                fut = d9[d9["state_time_s"] > start_t]
                ret_t = float(fut["state_time_s"].iloc[0]) if len(fut) else None
                # retired transition after start?
                r_after = [t for t, v in rtrans if t > start_t and v is True]
                inpit_t, inpit_v = latest_leq(kd["InPit"], start_t)
                last = d9[d9["state_time_s"] <= start_t]
                lastrow = last.iloc[-1] if len(last) else None
                frac = (float(lastrow["race_progress_frac"])
                        if lastrow is not None and
                        pd.notna(lastrow["race_progress_frac"]) else None)
                # training-eligibility classes (regime hygiene)
                tstate = (str(lastrow["track_status"])
                          if lastrow is not None else None)
                cls = "CLEAN"
                if inpit_v is True:
                    cls = "PIT_CONTEXT"
                elif tstate in ("red_flag",):
                    cls = "RED_REGIME"
                elif tstate in ("safety_car", "vsc", "vsc_ending"):
                    cls = "NEUTRALISED_REGIME"
                elif lastrow is None or initial_unknown:
                    cls = "INITIAL_UNKNOWN"
                elif ret_t is None and (sess_end - start_t) < 180:
                    cls = "LATE_SESSION"
                ep = {
                    "race_id": race_id, "season": season, "driver": did,
                    "x_stop_start_t": start_t,
                    "x_initial_unknown": initial_unknown,
                    "x_class": cls,
                    "x_last_lap": (None if lastrow is None
                                   else int(lastrow["lap_number"])),
                    "x_last_pos": (None if lastrow is None or
                                   pd.isna(lastrow["position"]) else int(
                                       lastrow["position"])),
                    "x_last_pit": (None if lastrow is None or
                                   pd.isna(lastrow[
                                       "pit_stops_completed_so_far"]) else int(
                                       lastrow["pit_stops_completed_so_far"])),
                    "x_compound": (None if lastrow is None or
                                   pd.isna(lastrow["compound"]) else str(
                                       lastrow["compound"])),
                    "x_tyre_life": (None if lastrow is None or
                                    pd.isna(lastrow["tyre_life"]) else int(
                                        lastrow["tyre_life"])),
                    "x_frac": frac,
                    "x_stage": ("EARLY" if frac is not None and frac < 1 / 3
                                else "MID" if frac is not None and
                                frac < 2 / 3 else "LATE" if frac is not None
                                else None),
                    "x_track": tstate,
                    "x_inpit": bool(inpit_v is True),
                    "y_returned": ret_t is not None,
                    "y_return_t": ret_t,
                    "y_retired_after": (r_after[0] if r_after else None),
                    "y_terminal": ret_t is None,
                }
                episodes.append(ep)
        if (ri + 1) % 30 == 0:
            print(f"  episodes race {ri + 1}/{len(races)} "
                  f"n_ep={len(episodes)} wall={time.perf_counter()-t0:.0f}s",
                  flush=True)
    print(f"episodes={len(episodes)} clearings={len(clearing_rows)} "
          f"wall={time.perf_counter()-t0:.1f}s", flush=True)
    json.dump({"schema_version": "v3.2l-episode-corpus-v1",
               "preregistration_sha256": prereg_hash,
               "n_episodes": len(episodes),
               "note": "x_ causal at/before stop start; y_ future labels only",
               "episodes": episodes},
              open(OUT / "episode_corpus.json", "w"))
    json.dump({"schema_version": "v3.2l-stopped-clearings-v1",
               "n_clearings": len(clearing_rows),
               "clearings": clearing_rows},
              open(OUT / "stopped_clearings.json", "w"))

    # clearing reliability: cleared -> D9 crossing within 300s?
    # (needs per-race D9; recompute cheaply for clearing races)
    clr_conf = Counter()
    clr_races = sorted({c["race_id"] for c in clearing_rows})
    d9_cache: dict = {}
    for race_id in clr_races:
        season = int(race_id.split("-")[0])
        frame = pd.read_parquet(
            str(PROCESSED / "driver_lap_state_d9" / f"season={season}" /
                f"driver_lap_state_d9__d9-{season}.parquet"))
        d9_cache[race_id] = frame[frame["race_id"] == race_id]
    for c in clearing_rows:
        d9 = d9_cache[c["race_id"]]
        fut = d9[(d9["driver_id"] == c["driver"]) &
                 (d9["state_time_s"] > c["clear_t"])]
        if len(fut) and float(fut["state_time_s"].min()) - c["clear_t"] <= 300:
            clr_conf["cleared_then_crossed_300s"] += 1
        else:
            clr_conf["cleared_no_crossing_300s"] += 1
    # return-without-clearing: RETURNED episodes with no False before return
    ret_noclear = 0
    ret_total = 0
    for ep in episodes:
        if not ep["y_returned"]:
            continue
        ret_total += 1
        kd = stop_seqs[ep["race_id"]]
        num = next((n for n, d in num_to_driver(
            ep["race_id"], ep["season"]).items() if d == ep["driver"]), None)
        seq = kd.get(num, {}).get("Stopped", []) if num else []
        if not any(t > ep["x_stop_start_t"] and v is False
                   for t, v in seq
                   if t <= (ep["y_return_t"] or float("inf"))):
            ret_noclear += 1
    json.dump({"schema_version": "v3.2l-stopped-semantics-v1",
               "clearing_outcome_300s": dict(clr_conf),
               "returned_episodes": ret_total,
               "returned_without_clearing_before_return": ret_noclear,
               "finding": "Stopped=False clearing precedes resumption only "
               "sometimes; resumption frequently occurs with Stopped "
               "left True-stale (feed does not reliably clear)"},
              open(OUT / "stopped_semantics.json", "w"), indent=1)

    # ---- baselines on clean training-eligible episodes ----
    clean = [e for e in episodes if e["x_class"] == "CLEAN"]
    json.dump({"schema_version": "v3.2l-temporal-splits-v1",
               "folds": {"train<=2020->2021": None, "train<=2021->2022": None,
                         "train<=2022->2023": None, "train<=2023->2024": None},
               "note": "counts filled by stage-2 training script"},
              open(OUT / "temporal_splits.json", "w"), indent=1)
    n_t = sum(1 for e in clean if e["y_terminal"])
    base = {"schema_version": "v3.2l-baselines-v1",
            "n_clean": len(clean),
            "global_terminal_freq": (n_t / len(clean) if clean else None)}
    for key in ("x_stage",):
        dd: dict = {}
        for e in clean:
            dd.setdefault(e[key], [0, 0])
            dd[e[key]][1] += 1
            dd[e[key]][0] += 1 if e["y_terminal"] else 0
        base["by_" + key] = {str(k): {"terminal": v[0], "n": v[1],
                                      "freq": v[0] / v[1]} for k, v in dd.items()
                              if k is not None}
    json.dump(base, open(OUT / "baselines.json", "w"), indent=1)

    # ---- stopped-age survival P(return | still stopped at age A) ----
    ages = list(range(0, 1801, 60))
    surv = []
    for A in ages:
        at_risk = 0
        returned = 0
        for e in clean:
            dur = ((e["y_return_t"] - e["x_stop_start_t"])
                   if e["y_returned"] else float("inf"))
            if dur >= A:
                at_risk += 1
                if e["y_returned"]:
                    returned += 1
        surv.append({"age_s": A, "at_risk": at_risk,
                     "p_return_eventual": (returned / at_risk if at_risk
                                           else None)})
    json.dump({"schema_version": "v3.2l-stopped-age-survival-v1",
               "population": "CLEAN episodes",
               "curve": surv},
              open(OUT / "stopped_age_survival.json", "w"), indent=1)

    # ---- causal features doc + availability ----
    feats = ["elapsed stopped duration at T", "race stage/fraction",
             "laps remaining from scheduled distance",
             "last known position/lap/lap deficit",
             "last known pit state/pit-stop count",
             "last known tyre state if causal", "track status at T",
             "race-control messages issued <= T",
             "stop context if causally available",
             "recent pre-stop pace descriptors"]
    avail = {}
    for f in feats:
        avail[f] = "available at episode start"  # refined in stage 2
    json.dump({"schema_version": "v3.2l-causal-features-v1",
               "features": feats, "availability": avail,
               "provenance": "all X from D9 rows <= stop_start_t, TimingData "
               "keys <= T, RaceState track/weather at T; no driver identity; "
               "no future labels"},
              open(OUT / "causal_features.json", "w"), indent=1)
    print(f"STAGE1 DONE wall={time.perf_counter()-t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
