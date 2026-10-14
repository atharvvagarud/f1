"""V3.10D event-coverage audit (offline, read-only).

Derives replay events over all served races with the SAME rules as
frontend/features/pit-wall/lib/events.ts (first-observable-frame mapping,
frame-0 baseline, closed taxonomy, rejection classes) and writes
results/v3/v3_10d/event_coverage.json.

Read-only: uses the frozen replay service (timelines + factual frames).
No models, no MC2, no predictions, no science changes. Multiprocess to keep
a 162k-frame corpus tractable; each worker builds one shared service.

Usage: uv run python3 scripts/v3_10d_event_coverage.py [--workers N]
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))
OUT = REPO / "results" / "v3" / "v3_10d" / "event_coverage.json"

_SERVICE = None


def _service():
    global _SERVICE
    if _SERVICE is None:
        from api.v2_replay_service import _cached_replay_service

        _SERVICE = _cached_replay_service()
    return _SERVICE


def _flag_kind(track_state):
    return {
        "yellow": "FLAG_YELLOW",
        "safety_car": "FLAG_SAFETY_CAR",
        "vsc": "FLAG_VSC",
        "vsc_ending": "FLAG_VSC",
        "red_flag": "FLAG_RED",
        "all_clear": "FLAG_GREEN",
    }.get(track_state, "FLAG_UNKNOWN")


def audit_race(race_id: str) -> dict:
    """Mirror of TS buildEventIndex; returns compact per-race stats."""
    svc = _service()
    total = len(svc.get_timeline(race_id).frames)
    by_kind: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    lap_starts = 0
    prev = None
    for i in range(total):
        result = svc.get_frame(race_id, i)
        state = result["state"].to_dict()
        rc = state["race_control"]
        pits = {
            d["driver_id"]: d["pit_stops_completed_so_far"]
            for d in state["drivers"]
            if d["pit_stops_completed_so_far"] is not None
        }
        curr = (
            rc["track_state"],
            rc["last_message_category"],
            rc["last_message_flag"],
            result["leader_lap"],
            pits,
        )
        if prev is not None:
            p_track, p_cat, p_flag, p_lap, p_pits = prev
            c_track, c_cat, c_flag, c_lap, _ = curr
            if c_track != p_track:
                by_kind[_flag_kind(c_track)] = by_kind.get(_flag_kind(c_track), 0) + 1
            if (c_cat != p_cat or c_flag != p_flag) and c_cat is not None:
                by_kind["RC_MESSAGE"] = by_kind.get("RC_MESSAGE", 0) + 1
            for driver in sorted(pits):
                nxt, bef = pits[driver], p_pits.get(driver)
                if bef is None:
                    if nxt > 0:
                        by_reason["pit-from-unknown"] = by_reason.get("pit-from-unknown", 0) + 1
                elif nxt > bef:
                    by_kind["PIT"] = by_kind.get("PIT", 0) + 1
                elif nxt < bef:
                    by_reason["pit-decrease"] = by_reason.get("pit-decrease", 0) + 1
            if c_lap is not None and c_lap != p_lap:
                if p_lap is None or c_lap > p_lap:
                    by_kind["LAP"] = by_kind.get("LAP", 0) + 1
                    lap_starts += 1
                else:
                    by_reason["lap-decrease"] = by_reason.get("lap-decrease", 0) + 1
            elif c_lap is None and p_lap is not None:
                by_reason["null-lap-skipped"] = by_reason.get("null-lap-skipped", 0) + 1
        prev = curr
    events_total = sum(by_kind.values())
    return {
        "race_id": race_id,
        "total_frames": total,
        "events_total": events_total,
        "by_kind": by_kind,
        "rejected_total": sum(by_reason.values()),
        "by_reason": by_reason,
        "lap_count": lap_starts,
    }


def _init_worker():
    _service()


def sample_races(race_ids: list[str], per_season: int = 2) -> list[str]:
    """Deterministic season-stratified sample (machine cannot hold a full
    multiprocess corpus; reported honestly in the payload). Two races per
    season (first + last round by race_id sort) plus the wet 2024 São Paulo
    race already covered by the product validation."""
    by_season: dict[str, list[str]] = {}
    for race_id in sorted(race_ids):
        by_season.setdefault(race_id[:4], []).append(race_id)
    sample: list[str] = []
    for season in sorted(by_season):
        group = by_season[season]
        sample.append(group[0])
        if len(group) > 1:
            sample.append(group[-1])
    if "2024-r21-R" not in sample:
        sample.append("2024-r21-R")
    return sorted(set(sample))[: per_season * len(by_season) + 1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--workers", type=int, default=8)
    parser.add_argument(
        "--sample",
        action="store_true",
        help="season-stratified sample instead of the full registry",
    )
    args = parser.parse_args()
    from concurrent.futures import ProcessPoolExecutor

    svc = _service()
    race_ids = list(svc.race_ids)
    sampled = False
    if args.sample:
        race_ids = sample_races(race_ids)
        sampled = True
        # Single process, one shared service: the audit machine cannot hold
        # a multiprocess corpus. Deterministic and sufficient: derivation is
        # a pure function of frames, so mapping-rate findings generalize.
        rows = []
        started = time.time()
        for n, race_id in enumerate(race_ids, 1):
            rows.append(audit_race(race_id))
            print(f"[{n}/{len(race_ids)}] {time.time()-started:.0f}s", flush=True)
        results = rows
    else:
        started = time.time()
        results = []
        with ProcessPoolExecutor(
            max_workers=args.workers, initializer=_init_worker
        ) as pool:
            for row in pool.map(audit_race, race_ids):
                results.append(row)
                done = len(results)
                if done % 10 == 0 or done == len(race_ids):
                    print(f"[{done}/{len(race_ids)}] {time.time()-started:.0f}s", flush=True)
    by_kind: dict[str, int] = {}
    by_reason: dict[str, int] = {}
    for row in results:
        for k, v in row["by_kind"].items():
            by_kind[k] = by_kind.get(k, 0) + v
        for k, v in row["by_reason"].items():
            by_reason[k] = by_reason.get(k, 0) + v
    zero = sorted(r["race_id"] for r in results if r["events_total"] == 0)
    payload = {
        "audit": "V3.10D",
        "scope": "sample" if sampled else "full-registry",
        "scope_note": (
            "Season-stratified sample (first+last round per season plus wet "
            "2024 São Paulo). Full-registry multiprocess audit exceeds this "
            "machine's memory; derivation is a pure function of frames so "
            "mapping-rate findings generalize. Every served race still gets "
            "its corpus derived at runtime when visited in the product."
            if sampled
            else "Full served registry."
        ),
        "races_audited": len(results),
        "frames_total": sum(r["total_frames"] for r in results),
        "events_total": sum(by_kind.values()),
        "by_kind": by_kind,
        "rejected_total": sum(by_reason.values()),
        "by_reason": by_reason,
        "races_with_zero_events": zero,
        "elapsed_s": round(time.time() - started, 1),
        "per_race": sorted(results, key=lambda r: r["race_id"]),
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=2))
    print(f"wrote {OUT} ({payload['events_total']} events)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
