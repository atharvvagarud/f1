#!/usr/bin/env python3
"""V3.2J Part F: fetch required 2019-2023 TimingData.jsonStream sources.

- Population from frozen source_manifest.json (never from success).
- Bounded concurrency (4), retry with backoff, explicit failures.
- Streaming writes to temp + atomic rename; resume skips complete files.
- Content SHA256 recorded in fetch_report.json.
- No credentials, no webpage scraping. Verifies prereg hash first.
"""

from __future__ import annotations

import concurrent.futures
import hashlib
import json
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "v3" / "v3_2j"
RAW_DIR = ROOT / "data" / "raw" / "fastf1_cache" / "v3_2j_timing"
MIRROR = "https://livetiming-mirror.fastf1.dev"
WORKERS = 4
RETRIES = 4
TIMEOUT_S = 120


def check_prereg() -> None:
    pre = json.load(open(OUT / "preregistration.json", encoding="utf-8"))
    expect = open(OUT / "preregistration.sha256", encoding="utf-8").read().strip()
    got = hashlib.sha256(json.dumps(pre, sort_keys=True).encode()).hexdigest()
    if got != expect:
        raise SystemExit(f"PREREG HASH MISMATCH: {got} != {expect}")


def fetch_one(rec: dict) -> dict:
    rid, url = rec["race_id"], rec["source_locator"]
    dest = RAW_DIR / str(rec["season"]) / f"{rid}.jsonStream"
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        h = hashlib.sha256(dest.read_bytes()).hexdigest()
        return {"race_id": rid, "status": "resumed_local",
                "bytes": dest.stat().st_size, "sha256": h, "url": url}
    last_err = None
    # Official host first, FastF1 mirror fallback (same bytes, same path;
    # mirrors fetch_one official-then-mirror order in fastf1/_api.py).
    # Provenance records which host served each stream.
    candidates = [url]
    if "/static/" in url:
        candidates.append(url.replace(
            "https://livetiming.formula1.com", MIRROR, 1))
    served_by = None
    for attempt in range(1, RETRIES + 1):
        for cand in candidates:
            try:
                req = urllib.request.Request(
                    cand, headers={"User-Agent": "f1-in-race-prediction/v3.2j"})
                tmp = dest.with_suffix(".jsonStream.tmp")
                h = hashlib.sha256()
                n = 0
                with urllib.request.urlopen(req, timeout=TIMEOUT_S) as r, \
                        open(tmp, "wb") as f:
                    if getattr(r, "status", 200) != 200:
                        raise IOError(f"HTTP {getattr(r, 'status', '?')}")
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        h.update(chunk)
                        n += len(chunk)
                if n == 0:
                    raise IOError("empty body")
                tmp.replace(dest)
                served_by = ("official" if "formula1.com" in cand
                             else "fastf1_mirror")
                return {"race_id": rid, "status": "fetched",
                        "bytes": n, "sha256": h.hexdigest(), "url": url,
                        "served_by": served_by, "attempts": attempt}
            except Exception as exc:  # noqa: BLE001 - recorded explicitly
                last_err = f"{type(exc).__name__}: {exc}"
        time.sleep(min(2 ** attempt, 30))
    return {"race_id": rid, "status": "FAILED", "error": last_err, "url": url}


def main() -> int:
    check_prereg()
    manifest = json.load(open(OUT / "source_manifest.json", encoding="utf-8"))
    pending = [r for r in manifest["records"]
               if r["retrieval_status"] == "pending_fetch"]
    assert len(pending) == 104, f"expected 104 pending, got {len(pending)}"
    results = []
    with concurrent.futures.ThreadPoolExecutor(
            max_workers=WORKERS) as pool:
        for res in pool.map(fetch_one, pending):
            results.append(res)
            print(f"{res['race_id']}: {res['status']} "
                  f"{res.get('bytes', '')} {res.get('error', '')}",
                  flush=True)
    failed = [r for r in results if r["status"] == "FAILED"]
    report = {
        "schema_version": "v3.2j-fetch-report-v1",
        "preregistration_sha256": open(
            OUT / "preregistration.sha256").read().strip(),
        "n_required": len(pending),
        "n_ok": len(results) - len(failed),
        "n_failed": len(failed),
        "results": sorted(results, key=lambda r: r["race_id"]),
    }
    json.dump(report, open(OUT / "fetch_report.json", "w"),
              indent=2, sort_keys=True)
    print(f"ok={report['n_ok']} failed={report['n_failed']}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
