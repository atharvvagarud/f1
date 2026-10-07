#!/usr/bin/env python3
"""V3.2J Part E: frozen expected 2018-2024 race/session source manifest.

Population is derived from the frozen replay catalogue (D9 race_ids,
149 races 2018-2024) crossed with local FastF1 event dirs for URL
resolution. NEVER derived from download success. Verifies the
preregistration hash before running. Deterministic output.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import sqlite3
import sys
import unicodedata
import urllib.parse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "v3" / "v3_2j"
SQLITE = ROOT / "data" / "raw" / "fastf1_cache" / "fastf1_http_cache.sqlite"
HOST = "https://livetiming.formula1.com/static"


def check_prereg() -> str:
    pre = json.load(open(OUT / "preregistration.json", encoding="utf-8"))
    expect = open(OUT / "preregistration.sha256", encoding="utf-8").read().strip()
    got = hashlib.sha256(
        json.dumps(pre, sort_keys=True).encode()).hexdigest()
    if got != expect:
        raise SystemExit(f"PREREG HASH MISMATCH: {got} != {expect}")
    return got


def event_dirs(season: str) -> list[str]:
    base = ROOT / "data" / "raw" / "fastf1_cache" / season
    return sorted(d.name for d in base.iterdir() if d.is_dir())


def sqlite_timing_urls() -> dict[str, str]:
    """Full URL -> raw text for cached TimingData streams."""
    con = sqlite3.connect(SQLITE)
    out: dict[str, str] = {}
    for (v,) in con.execute("select value from responses").fetchall():
        d = pickle.loads(v)
        u = d.get("url", "")
        if u.endswith("/TimingData.jsonStream"):
            raw = d["_content"]
            if isinstance(raw, (bytes, bytearray)):
                raw = bytes(raw).decode("utf-8-sig")
            out[u] = raw
    return out


def main() -> int:
    prereg_hash = check_prereg()
    import pandas as pd  # noqa: E402

    race_ids: list[tuple[str, int, int]] = []
    for season in (2018, 2019, 2020, 2021, 2022, 2023, 2024):
        df = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9" /
            f"season={season}/driver_lap_state_d9__d9-{season}.parquet",
            columns=["race_id"])
        for rid in sorted(df["race_id"].unique().tolist()):
            rnd = int(rid.split("-r")[1].split("-")[0])
            race_ids.append((rid, season, rnd))
    assert len(race_ids) == 149, f"expected 149 races, got {len(race_ids)}"

    cached = sqlite_timing_urls()
    records = []
    for rid, season, rnd in race_ids:
        dirs = event_dirs(str(season))
        assert len(dirs) == len([r for r in race_ids if r[1] == season]), \
            f"dir count mismatch {season}"
        gp = dirs[rnd - 1]
        date = gp[:10]
        # Live-timing static host percent-encodes non-ASCII (Sao Paulo):
        # local dirs may use NFD combining marks; host uses NFC.
        gp_enc = urllib.parse.quote(
            unicodedata.normalize("NFC", gp), safe="_-")
        locator = f"{HOST}/{season}/{gp_enc}/{date}_Race/TimingData.jsonStream"
        if locator in cached:
            retrieval = "local_cache"
            sha = hashlib.sha256(cached[locator].encode("utf-8")).hexdigest()
            n_bytes = len(cached[locator].encode("utf-8"))
        elif 2019 <= season <= 2023:
            retrieval = "pending_fetch"
            sha = None
            n_bytes = None
        else:
            raise AssertionError(f"missing local stream {rid} {locator}")
        records.append({
            "race_id": rid, "season": season, "round": rnd,
            "session": "Race",
            "expected_replay_identity": rid,
            "source_locator": locator,
            "retrieval_status": retrieval,
            "content_sha256": sha,
            "content_bytes": n_bytes,
            "parse_status": "pending",
            "semantic_validation_status": "pending",
        })
    manifest = {
        "schema_version": "v3.2j-source-manifest-v1",
        "preregistration_sha256": prereg_hash,
        "host": HOST,
        "n_races": len(records),
        "n_pending_fetch": sum(1 for r in records
                               if r["retrieval_status"] == "pending_fetch"),
        "n_local_cache": sum(1 for r in records
                             if r["retrieval_status"] == "local_cache"),
        "records": records,
    }
    json.dump(manifest, open(OUT / "source_manifest.json", "w"),
              indent=2, sort_keys=True)
    print(f"races={len(records)} pending={manifest['n_pending_fetch']} "
          f"cached={manifest['n_local_cache']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
