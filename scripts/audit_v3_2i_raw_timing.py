#!/usr/bin/env python3
"""V3.2I raw TimingData audit (Parts C-G, read-only).

Censuses per-driver keys in cached F1 live-timing TimingData.jsonStream
delta messages (2018 + 2024 only) and hunts retirement-like vocabulary
(Retired/Stopped/InPit/Status) with timestamps. No downloads. No
runtime changes. Deterministic outputs.
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
SQLITE = ROOT / "data" / "raw" / "fastf1_cache" / "fastf1_http_cache.sqlite"

TARGETS = ("Retired", "Stopped", "InPit", "PitOut", "PitIn", "Status")


def load_stream(url_suffix: str) -> str:
    con = sqlite3.connect(SQLITE)
    for (v,) in con.execute("select value from responses").fetchall():
        d = pickle.loads(v)
        if d.get("url", "").endswith(url_suffix):
            raw = d["_content"]
            if isinstance(raw, (bytes, bytearray)):
                raw = bytes(raw).decode("utf-8-sig")
            return raw
    raise KeyError(url_suffix)


def split_messages(raw: str) -> list:
    """jsonStream framing: 12-char time prefix + JSON object per line."""
    msgs = []
    for line in raw.splitlines():
        line = line.strip().lstrip("\ufeff")
        if len(line) < 13:
            continue
        try:
            msgs.append((line[:12], json.loads(line[12:])))
        except json.JSONDecodeError:
            continue
    return msgs


def walk_keys(obj, prefix=""):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield f"{prefix}{k}"
            yield from walk_keys(v, f"{prefix}{k}.")
    elif isinstance(obj, list):
        for i, v in enumerate(obj[:3]):
            yield from walk_keys(v, f"{prefix}[{i}].")


def audit_race(url_suffix: str, out: dict) -> dict:
    raw = load_stream(url_suffix)
    msgs = split_messages(raw)
    key_use = Counter()
    target_hits = []
    lines_seen = set()
    for t, m in msgs:
        if not isinstance(m, dict):
            continue
        lines = m.get("Lines", m) if isinstance(m, dict) else {}
        if isinstance(lines, dict):
            for drv, entry in lines.items():
                if not isinstance(entry, dict):
                    continue
                lines_seen.add(str(drv))
                for k in walk_keys(entry):
                    key_use[k] += 1
                    if k.split(".")[-1].strip("[]0123456789") in TARGETS or \
                            k in TARGETS:
                        target_hits.append((t, str(drv), k,
                                            json.dumps(entry.get(k.split(".")[0], entry))[:160]))
    return {"n_messages": len(msgs), "drivers": sorted(lines_seen),
            "key_counts": dict(key_use.most_common(80)),
            "target_hits": target_hits[:60],
            "n_target_hits": len(target_hits)}


def main() -> int:
    con = sqlite3.connect(SQLITE)
    urls = []
    for (v,) in con.execute("select value from responses").fetchall():
        u = pickle.loads(v).get("url", "")
        if u.endswith("/TimingData.jsonStream"):
            urls.append(u)
    urls.sort()
    print(f"TimingData streams cached: {len(urls)}")
    # audit 2 races with known retirements: Baku 2018 (VER/RIC crash),
    # plus one 2024 race
    picks = [u for u in urls if "2018-04-29" in u] + \
            [u for u in urls if "2024-03-02" in u]
    res = {}
    for u in picks:
        suffix = u.split("/static/")[1]
        r = audit_race(suffix, res)
        res[u] = r
        print(f"== {u.split('/')[-2]} ==")
        print(f"  messages={r['n_messages']} drivers={len(r['drivers'])}")
        print(f"  target_hits={r['n_target_hits']}")
        for h in r["target_hits"][:25]:
            print("   ", h)
    out = ROOT / "results" / "v3" / "v3_2i"
    out.mkdir(parents=True, exist_ok=True)
    json.dump({"streams_cached": len(urls), "races": res},
              open(out / "_timing_audit_tmp.json", "w"),
              indent=2, sort_keys=True, default=str)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
