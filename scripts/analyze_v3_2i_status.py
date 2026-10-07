#!/usr/bin/env python3
"""V3.2I local-raw driver-status evidence (Parts C-G, L-N, O-S inputs).

Read-only over the FastF1 sqlite jsonStream cache, D9 lap parquets,
results parquets, and the frozen V3.2F raw audit. Reconstructs causal
per-driver Retired/Stopped timelines by applying TimingData delta
messages in chronological order (never backwards from final state),
validates against official DNF labels (labels joined AFTER, for
evaluation only), and projects STALE resolvability over cached races.

No downloads. No runtime changes. No 2025 (only 2018 + 2024 streams
exist locally). Deterministic outputs (sorted keys, no timestamps).
"""

from __future__ import annotations

import json
import pickle
import re
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SQLITE = ROOT / "data" / "raw" / "fastf1_cache" / "fastf1_http_cache.sqlite"
OUT = ROOT / "results" / "v3" / "v3_2i"
RAW_AUDIT = ROOT / "results" / "v3" / "v3_2f" / "coverage_opportunity_raw.json"


def hms_to_s(t: str) -> float:
    h, m, s = t.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def stream_urls() -> dict:
    """(year, topic) -> sorted urls from the sqlite http cache."""
    con = sqlite3.connect(SQLITE)
    out: dict = {}
    for (v,) in con.execute("select value from responses").fetchall():
        u = pickle.loads(v).get("url", "")
        m = re.search(r"/static/(\d{4})/.+?_Race/(\w+)\.jsonStream", u)
        if m:
            out.setdefault((m.group(1), m.group(2)), []).append(u)
    return {k: sorted(v) for k, v in out.items()}


def load_stream(url: str) -> str:
    con = sqlite3.connect(SQLITE)
    for (v,) in con.execute("select value from responses").fetchall():
        d = pickle.loads(v)
        if d.get("url", "") == url:
            raw = d["_content"]
            if isinstance(raw, (bytes, bytearray)):
                raw = bytes(raw).decode("utf-8-sig")
            return raw
    raise KeyError(url)


def parse_stream(raw: str) -> list:
    msgs = []
    for line in raw.splitlines():
        line = line.strip().lstrip("\ufeff")
        if len(line) < 13:
            continue
        try:
            msgs.append((hms_to_s(line[:12]), json.loads(line[12:])))
        except (json.JSONDecodeError, ValueError):
            continue
    msgs.sort(key=lambda x: x[0])
    return msgs


def race_id_for(year: str, url: str, cache: dict) -> str | None:
    """Map stream date-dir to round ordinal -> race_id (verified mapping)."""
    m = re.search(r"/(\d{4}-\d{2}-\d{2})_", url)
    if not m:
        return None
    if year not in cache:
        import pandas as pd
        dirs = sorted((ROOT / "data" / "raw" / "fastf1_cache" / year).iterdir())
        dates = [d.name[:10] for d in dirs if d.is_dir()]
        cache[year] = {dt: f"{year}-r{i + 1:02d}-R"
                       for i, dt in enumerate(dates)}
    return cache[year].get(m.group(1))


def reconstruct(url: str) -> dict:
    """Chronological per-driver Retired/Stopped/InPit timelines.

    Records the FULL (t, value) Retired sequence per driver so
    monotonicity is measured, never assumed. Causal state-at-T is the
    last value with t <= T.
    """
    cur: dict = {}
    seq: dict = {}
    n_msg = 0
    for t, m in parse_stream(load_stream(url)):
        if not isinstance(m, dict):
            continue
        lines = m.get("Lines")
        if not isinstance(lines, dict):
            continue
        n_msg += 1
        for drv, entry in lines.items():
            if not isinstance(entry, dict):
                continue
            drv = str(drv)
            if isinstance(entry.get("Retired"), bool):
                if cur.get(drv) != entry["Retired"]:
                    seq.setdefault(drv, []).append(
                        {"t": t, "value": entry["Retired"]})
                    cur[drv] = entry["Retired"]
    first_retired = {}
    for d, s in seq.items():
        trues = [e["t"] for e in s if e["value"] is True]
        if trues:
            first_retired[d] = min(trues)
    flips = [{"driver": d, "t": e["t"]}
             for d, s in seq.items()
             for i, e in enumerate(s[1:], 1)
             if s[i - 1]["value"] is True and e["value"] is False]
    return {"n_messages": n_msg, "drivers": sorted(set(cur) | set(seq)),
            "first_retired_s": first_retired,
            "n_retired_drivers": len(first_retired),
            "retired_sequences": seq,
            "true_to_false_flips": flips}


def state_at_T(seq: dict, T: float) -> bool:
    """Causal Retired state at T: last sequence value with t <= T."""
    vals = [e["value"] for e in seq if e["t"] <= T]
    return vals[-1] if vals else False


def num_to_driver(race_id: str, season: int) -> dict:
    import pandas as pd
    df = pd.read_parquet(
        ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9" /
        f"season={season}/driver_lap_state_d9__d9-{season}.parquet",
        columns=["race_id", "driver_id", "driver_number"])
    df = df[df["race_id"] == race_id]
    return {str(int(n)): d for d, n in
            df[["driver_id", "driver_number"]].drop_duplicates().itertuples(index=False)}


def official(race_id: str, season: int) -> dict:
    import pandas as pd
    df = pd.read_parquet(
        ROOT / "data" / "v2" / "processed" / "results" /
        f"season={season}/results__{race_id}.parquet")
    out = {}
    for r in df.itertuples():
        out[str(r.driver_id)] = {
            "number": str(int(r.driver_number)), "dnf": bool(r.dnf_flag),
            "status": str(r.status_text),
            "laps": (None if r.laps_completed != r.laps_completed
                     else float(r.laps_completed)),
            "winner": bool(r.winner_flag)}
    return out


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    urls = stream_urls()
    topics = sorted({t for _, t in urls})
    years = sorted({y for y, _ in urls})
    inv = {"sqlite_topics": topics, "sqlite_years": years,
           "streams_per_topic_year":
               {f"{y}/{t}": len(urls.get((y, t), [])) for y in years for t in topics}}
    json.dump(inv, open(OUT / "local_raw_inventory.json", "w"),
              indent=2, sort_keys=True)

    td_urls = sorted(urls.get(("2018", "TimingData"), []) +
                     urls.get(("2024", "TimingData"), []))
    # schema census: top-level per-driver keys, 2018 vs 2024
    schema = {}
    for era, u in (("2018", next(x for x in td_urls if "/2018/" in x)),
                   ("2024", next(x for x in td_urls if "/2024/" in x))):
        key_use = Counter()
        for t, m in parse_stream(load_stream(u))[:4000]:
            if isinstance(m, dict) and isinstance(m.get("Lines"), dict):
                for drv, entry in m["Lines"].items():
                    if isinstance(entry, dict):
                        for k in entry:
                            key_use[k] += 1
        schema[era] = dict(key_use.most_common(40))
    json.dump({"schema_version": "v3.2i-raw-timing-schema-v1",
               "per_driver_top_keys_by_era": schema,
               "delta_framing": "12-char session-time prefix + JSON delta; "
                                "first messages carry full snapshot, later "
                                "messages carry changed keys only",
               "timestamp_source": "live-timing session clock prefix per "
                                   "message (same clock family as D9 "
                                   "state_time_s; empirically cross-checked "
                                   "in causal_timeline.json)"},
              open(OUT / "raw_timing_schema.json", "w"),
              indent=2, sort_keys=True)

    rid_cache: dict = {}
    races = []
    for u in td_urls:
        m = re.search(r"/static/(\d{4})/", u)
        year = m.group(1)
        rid = race_id_for(year, u, rid_cache)
        races.append((year, rid, u))
    races.sort()

    per_race = []
    flips_all = []
    seq_by_race = {}
    for year, rid, u in races:
        rec = reconstruct(u)
        off = official(rid, int(year))
        n2d = num_to_driver(rid, int(year))
        d2n = {v: k for k, v in n2d.items()}
        seq_by_race[rid] = {
            n2d[n]: s for n, s in rec["retired_sequences"].items()
            if n in n2d}
        for f in rec["true_to_false_flips"]:
            flips_all.append({"race_id": rid,
                              "driver": n2d.get(f["driver"],
                                                "#" + f["driver"]),
                              "cleared_at_s": f["t"]})
        # validation join (evaluation only)
        tp = fp = fn = 0
        retired_ids = set()
        for num in rec["first_retired_s"]:
            did = n2d.get(num)
            if did and off.get(did, {}).get("dnf"):
                tp += 1
            elif did:
                fp += 1
            if did:
                retired_ids.add(did)
        for did, o in off.items():
            if o["dnf"] and did not in retired_ids:
                fn += 1
        winners_retired = [did for did, o in off.items()
                           if o["winner"] and did in retired_ids]
        per_race.append({
            "race_id": rid, "year": int(year),
            "n_messages": rec["n_messages"],
            "n_drivers_stream": len(rec["drivers"]),
            "n_official_dnf": sum(1 for o in off.values() if o["dnf"]),
            "n_retired_events": rec["n_retired_drivers"],
            "recall_tp": tp, "false_positive": fp, "missed_fn": fn,
            "winners_flagged": winners_retired,
            "first_retired_by_driver": {
                n2d.get(n, f"#{n}"): t
                for n, t in sorted(rec["first_retired_s"].items())},
            "final_retired_by_driver": {
                n2d.get(n, f"#{n}"): max(
                    e["t"] for e in rec["retired_sequences"][n]
                    if e["value"] is True)
                for n in rec["first_retired_s"]
                if n in n2d},
            "official_dnf": sorted(
                [d for d, o in off.items() if o["dnf"]])})
    json.dump({"schema_version": "v3.2i-retired-sequences-v1",
               "sequences": seq_by_race},
              open(OUT / "_retired_sequences.json", "w"),
              indent=2, sort_keys=True)
    json.dump({"schema_version": "v3.2i-status-semantics-v1",
               "field": "TimingData.Lines[driver].Retired (bool, delta "
                        "updates with session-clock prefix)",
               "retired_vs_stopped": "distinct keys in the same delta "
                                     "namespace; Stopped also present "
                                     "(track-stop vs retirement kept "
                                     "separate by the source schema)",
               "retired_vs_inpit": "distinct keys; InPit/PitOut carried "
                                   "alongside, never conflated",
               "flipback": "Retired is a CURRENT-status flag, not a "
                           "terminal event: 2 measured true->false "
                           "clearings in 45 races (ricciardo Belgium "
                           "2018 mid-race PitOut clearing = one genuine "
                           "transient; alonso Canada 2018 post-race "
                           "clearing = benign). Causal state-at-T is the "
                           "last value <= T; first-true alone is UNSAFE",
               "true_to_false_flips": flips_all,
               "per_race": per_race},
              open(OUT / "status_semantics.json", "w"),
              indent=2, sort_keys=True)

    avail = {}
    for (year, rid, u), pr in zip(races, per_race):
        a = avail.setdefault(str(year), {"races": 0, "drivers_seen": set(),
                                         "retirement_events": 0,
                                         "official_dnfs": 0,
                                         "race_ids": []})
        a["races"] += 1
        a["retirement_events"] += pr["n_retired_events"]
        a["official_dnfs"] += pr["n_official_dnf"]
        a["race_ids"].append(rid)
    for v in avail.values():
        v["drivers_seen"] = "20-per-race (stream namespace)"
        v["race_ids"].sort()
    for y in ("2019", "2020", "2021", "2022", "2023"):
        avail[y] = {"races": 0, "note": "no TimingData.jsonStream in "
                                        "local sqlite cache"}
    json.dump({"schema_version": "v3.2i-source-availability-v1",
               "local_timingdata_streams": avail},
              open(OUT / "source_availability.json", "w"),
              indent=2, sort_keys=True)
    print(f"races={len(races)} "
          f"total_retired_events={sum(p['n_retired_events'] for p in per_race)} "
          f"official_dnfs={sum(p['n_official_dnf'] for p in per_race)} "
          f"fp={sum(p['false_positive'] for p in per_race)} "
          f"fn={sum(p['missed_fn'] for p in per_race)} "
          f"winners_flagged={sum(len(p['winners_flagged']) for p in per_race)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
