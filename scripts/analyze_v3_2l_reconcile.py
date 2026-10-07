#!/usr/bin/env python3
"""V3.2L stage 1b: checkpoint/offender opportunity reconciliation.

Uses stage-1 stopped semantics (no hard stopped-age boundary derivable:
P(return|age) stays nonzero; age is a model feature, not a gate).
Verifies L prereg hash. Labels (y_*) written to a SEPARATE file.
Deterministic. 2025 never read. No network.
"""

from __future__ import annotations

import bisect
import hashlib
import json
import pickle
import sqlite3
import sys
import time
from collections import Counter
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


def latest_leq(seq: list, T: float):
    if not seq:
        return (None, None)
    ts = [e[0] for e in seq]
    i = bisect.bisect_right(ts, T) - 1
    return seq[i] if i >= 0 else (None, None)


def main() -> int:
    t0 = time.perf_counter()
    prereg_hash = check_prereg()
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

    def windowed(race_id, did, T):
        return any(a <= T < b
                   for a, b in windows.get((race_id, did), ()))

    n2d_cache: dict = {}
    stream_cache: dict = {}

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

    def stop_keys(race_id: str, season: int) -> dict | None:
        if race_id not in stream_cache:
            rec = rec_by_race[race_id]
            raw = None
            if rec["retrieval_status"] == "local_cache":
                cc = sqlite3.connect(SQLITE)
                for (v,) in cc.execute(
                        "select value from responses").fetchall():
                    d = pickle.loads(v)
                    if d.get("url") == rec["source_locator"]:
                        raw = d["_content"]
                        break
                cc.close()
                if isinstance(raw, (bytes, bytearray)):
                    raw = bytes(raw).decode("utf-8-sig")
            else:
                p = RAW_DIR / str(season) / f"{race_id}.jsonStream"
                raw = p.read_text(encoding="utf-8-sig") if p.exists() else None
            per: dict = {}
            if raw is not None:
                for ln in raw.splitlines():
                    ln = ln.strip().lstrip("\ufeff")
                    if len(ln) < 13:
                        continue
                    try:
                        t = clock_to_seconds(ln[:12])
                        delta = json.loads(ln[12:])
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
                        d = per.setdefault(num, {"Stopped": [], "InPit": [],
                                                "Retired": [], "any": []})
                        d["any"].append(t)
                        for k in ("Stopped", "InPit", "Retired"):
                            v = entry.get(k)
                            if isinstance(v, bool):
                                d[k].append((t, v))
                for num in per:
                    for k in ("Stopped", "InPit", "Retired"):
                        per[num][k].sort(key=lambda e: e[0])
                    per[num]["any"].sort()
            stream_cache[race_id] = per if raw is not None else None
        return stream_cache[race_id]

    by_race: dict = {}
    for r in tgt["checkpoints"]:
        by_race.setdefault(r["race_id"], []).append(r)

    off_rows: list = []
    lab_rows: list = []
    for ri, race_id in enumerate(sorted(by_race)):
        season = int(race_id.split("-")[0])
        per = stop_keys(race_id, season)
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
        n2d = num_to_driver(race_id, season)
        rev = {v: k for k, v in n2d.items()}
        for r in by_race[race_id]:
            try:
                rs = service.state_at(r["frame_index"])
            except Exception:
                for off in r["stale_offenders"]:
                    off_rows.append(
                        {"race_id": race_id, "frame_index": r["frame_index"],
                         "offender": off, "oclass": "OTHER"})
                continue
            T = float(rs.state_time_s)
            obs = {e.driver_id: e for e in rs.observable_drivers}
            for off in r["stale_offenders"]:
                e = obs.get(off)
                ret = resolver.retired_known_at(race_id, off, T)
                win = windowed(race_id, off, T)
                num = rev.get(off)
                kd = (per.get(num) if per is not None and num else None)
                st_t, st_v = latest_leq(kd["Stopped"], T) if kd else (None,
                                                                     None)
                ip_t, ip_v = latest_leq(kd["InPit"], T) if kd else (None, None)
                any_after = (kd is not None and any(
                    t > T for t in kd["any"]))
                # last-state sufficiency (strict: tyre required per Part R)
                if e is None:
                    suff = "no_canonical_entry"
                elif e.pit_stops_completed_so_far is None:
                    suff = "missing_pit_count"
                elif e.constructor_id is None:
                    suff = "missing_constructor"
                elif e.compound is None or e.tyre_life is None:
                    suff = "missing_tyre"
                else:
                    suff = "sufficient"
                if ret is True:
                    oclass = "J_RETIRED"
                elif st_v is True:
                    oclass = ("ADDRESSABLE" if suff == "sufficient"
                              else "LAST_STATE_INSUFFICIENT")
                elif st_v is False:
                    oclass = "STOPPED_CLEARED"
                else:
                    oclass = "NO_STOP_SIGNAL"
                off_rows.append(
                    {"race_id": race_id, "season": season,
                     "frame_index": r["frame_index"], "stage": r["stage"],
                     "offender": off, "oclass": oclass,
                     "j_retired": ret, "j_windowed": win,
                     "stopped_at_T": st_v,
                     "stopped_update_age": (T - st_t if st_t is not None
                                            else None),
                     "inpit_at_T": ip_v,
                     "canon_age": (e.observation_age_s if e is not None
                                   else None),
                     "canon_lap": (e.observed_lap_number if e is not None
                                   else None),
                     "anchor_sufficiency": suff,
                     "canon_compound": (e.compound if e is not None else None),
                     "canon_tyre_life": (e.tyre_life if e is not None
                                         else None)})
                # LABELS ONLY, separate store
                d9 = states[states["driver_id"] == off].sort_values(
                    "state_time_s")
                fut = d9[d9["state_time_s"] > T]
                lab_rows.append(
                    {"race_id": race_id, "frame_index": r["frame_index"],
                     "offender": off,
                     "y_return_t": (float(fut["state_time_s"].iloc[0])
                                    if len(fut) else None),
                     "y_terminal": len(fut) == 0,
                     "y_later_raw_activity": bool(any_after)})
            # end offenders
        if (ri + 1) % 25 == 0:
            print(f"  reconcile race {ri + 1}/{len(by_race)} "
                  f"wall={time.perf_counter()-t0:.0f}s", flush=True)

    # checkpoint roll-up (exclusive)
    by_cp: dict = {}
    for o in off_rows:
        by_cp.setdefault((o["race_id"], o["frame_index"]), []).append(
            o["oclass"])
    SIG = {"STOPPED_CLEARED", "NO_STOP_SIGNAL", "STOPPED_TOO_OLD", "OTHER"}
    decomp: Counter = Counter()
    for key, clses in by_cp.items():
        u = set(clses)
        if u == {"ADDRESSABLE"}:
            decomp["LIFECYCLE_FULLY_ADDRESSABLE"] += 1
        elif u == {"J_RETIRED"}:
            decomp["OTHER_EXPLAINED"] += 1
        elif u <= {"J_RETIRED", "ADDRESSABLE"}:
            decomp["J_RETIRED_PLUS_LIFECYCLE"] += 1
        elif u == {"LAST_STATE_INSUFFICIENT"}:
            decomp["LAST_STATE_INSUFFICIENT"] += 1
        elif u <= SIG:
            decomp["NO_CAUSAL_STOP_SIGNAL"] += 1
        elif "ADDRESSABLE" in u and (u - {"ADDRESSABLE"}) <= SIG \
                and "J_RETIRED" not in u \
                and "LAST_STATE_INSUFFICIENT" not in u:
            decomp["LIFECYCLE_PARTIALLY_ADDRESSABLE"] += 1
        elif len(clses) > 1:
            decomp["MULTIPLE_OFFENDER_MIXED"] += 1
        else:
            decomp["OTHER_EXPLAINED"] += 1
    assert sum(decomp.values()) == 3294, sum(decomp.values())
    cats = ["LIFECYCLE_FULLY_ADDRESSABLE", "LIFECYCLE_PARTIALLY_ADDRESSABLE",
            "NO_CAUSAL_STOP_SIGNAL", "LAST_STATE_INSUFFICIENT",
            "MULTIPLE_OFFENDER_MIXED", "J_RETIRED_PLUS_LIFECYCLE",
            "OTHER_EXPLAINED"]
    json.dump({"schema_version": "v3.2l-opportunity-v1",
               "preregistration_sha256": prereg_hash, "n": 3294,
               "conservation": True,
               "checkpoint_categories": {c: decomp.get(c, 0) for c in cats},
               "offender_class_dist": dict(Counter(
                   o["oclass"] for o in off_rows)),
               "boundary_rule": "no hard stopped-age boundary: survival "
               "P(return|age) stays nonzero at all ages (stage-1); age is a "
               "model feature; staleness itself (no D9 crossing > bound) "
               "corroborates non-progression; STOPPED_TOO_OLD empty by "
               "evidence, not by tuning"},
              open(OUT / "opportunity.json", "w"), indent=1)
    json.dump({"schema_version": "v3.2l-stale-reconciliation-v1",
               "k_classes": {"RAW_SOURCE_STALE": 2866,
                             "LIFECYCLE_AMBIGUOUS": 147,
                             "MULTIPLE_OFFENDER_MIXED": 281},
               "reconciliation": "K RAW_SOURCE_STALE = raw feed equally "
               "stale AND last raw state Stopped=True in most cases; L "
               "re-expresses via stopped-signal availability: see "
               "opportunity.json checkpoint categories",
               "n_offender_rows": len(off_rows)},
              open(OUT / "stale_reconciliation.json", "w"), indent=1)
    # offender rows: split causal vs labels already (labels separate file)
    json.dump({"schema_version": "v3.2l-offender-opportunity-v1",
               "n": len(off_rows), "offenders": off_rows},
              open(OUT / "offender_opportunity.json", "w"))
    json.dump({"schema_version": "v3.2l-offender-labels-v1",
               "note": "FUTURE LABELS ONLY: never model/runtime inputs",
               "labels": lab_rows},
              open(OUT / "offender_labels.json", "w"))
    # lifecycle contract
    json.dump({"schema_version": "v3.2l-lifecycle-contract-v1",
               "state": "STOPPED_UNRESOLVED_AT_T",
               "means": "at T the driver is causally known stopped/"
               "non-progressing (latest Stopped True, D9-stale "
               "corroborated), not J-Retired, with last known race state "
               "sufficient to initialize a lifecycle process",
               "not_means": ["retired", "DNF", "will not return"],
               "stopped_semantics": "Stopped=False clearing unreliable "
               "(73/85 returns lack clearing); Stopped=True may persist "
               "stale after resume; age-conditioned modelling required, "
               "never sticky-forever assumption"},
              open(OUT / "lifecycle_contract.json", "w"), indent=1)
    print(f"RECONCILE DONE wall={time.perf_counter()-t0:.1f}s", flush=True)
    print("decomp:", {c: decomp.get(c, 0) for c in cats}, flush=True)
    print("oclass:", dict(Counter(o["oclass"] for o in off_rows)), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
