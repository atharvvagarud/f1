#!/usr/bin/env python3
"""V3.2K disagreement probes: position/lap/pit mismatch anatomy (read-only).

Self-contained (duplicates 20 lines of parsing helpers rather than
importing closures). Samples 8 races x up to 6 control checkpoints,
compares raw latest<=T vs canonical entries with per-key timestamps.
Deterministic. No network. 2025 never read.
"""

from __future__ import annotations

import bisect
import json
import pickle
import sqlite3
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "v3" / "v3_2k"
JOUT = ROOT / "results" / "v3" / "v3_2j"
RAW_DIR = ROOT / "data" / "raw" / "fastf1_cache" / "v3_2j_timing"
SQLITE = ROOT / "data" / "raw" / "fastf1_cache" / "fastf1_http_cache.sqlite"
PROCESSED = ROOT / "data" / "v2" / "processed"

KEYS = ("Position", "NumberOfLaps", "NumberOfPitStops")


def clock_to_seconds(prefix: str) -> float:
    h, m, s = prefix.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def to_int(v):
    try:
        if isinstance(v, bool):
            return None
        return int(str(v).strip())
    except (ValueError, TypeError, AttributeError):
        return None


def main() -> int:
    import pandas as pd  # noqa: E402
    from raceintel.race_state.race_state_reconstruction import (  # noqa: E402
        RaceStateReconstructor)
    from raceintel.replay import replay as RP  # noqa: E402
    from raceintel.replay.replay_reconstruction import (  # noqa: E402
        ReplayReconstructor)

    manifest = json.load(open(JOUT / "source_manifest.json", encoding="utf-8"))
    rec_by_race = {r["race_id"]: r for r in manifest["records"]}
    ctl = json.load(open(OUT / "trusted_control_population.json",
                         encoding="utf-8"))["checkpoints"]
    by_race: dict = {}
    for c in ctl:
        by_race.setdefault(c["race_id"], []).append(c)
    races = sorted(by_race)[:3] + sorted(by_race)[len(by_race) // 2:
                                                  len(by_race) // 2 + 2] \
        + sorted(by_race)[-3:]
    print("probe races:", races, flush=True)

    pos_dir = Counter()
    pos_age_diff = []
    lap_lag = []
    lap_dir = Counter()
    pit_dir = Counter()
    pit_detail = Counter()

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

    def num_to_driver(race_id: str, season: int) -> dict:
        df = pd.read_parquet(
            PROCESSED / "driver_lap_state_d9" / f"season={season}" /
            f"driver_lap_state_d9__d9-{season}.parquet",
            columns=["race_id", "driver_id", "driver_number"])
        df = df[df["race_id"] == race_id]
        return {str(int(n)): d for d, n in
                df[["driver_id", "driver_number"]].drop_duplicates()
                .itertuples(index=False)}

    for race_id in races:
        season = int(race_id.split("-")[0])
        raw = load_stream(race_id, season)
        per: dict = {}
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
                for k in KEYS:
                    if k in entry:
                        per.setdefault(str(num), {}).setdefault(k, []).append(
                            (t, entry[k]))
        for num in per:
            for k in per[num]:
                per[num][k].sort(key=lambda e: e[0])
        n2d = num_to_driver(race_id, season)
        rev = {v: k for k, v in n2d.items()}
        frame = pd.read_parquet(
            str(PROCESSED / "driver_lap_state_d9" / f"season={season}" /
                f"driver_lap_state_d9__d9-{season}.parquet"))
        states = frame[frame["race_id"] == race_id].copy()
        results = pd.read_parquet(
            str(PROCESSED / "results" / f"season={season}" /
                f"results__{race_id}.parquet"))
        timeline = RP.build_replay_timeline(states)
        service = ReplayReconstructor(
            timeline, RaceStateReconstructor(states, results,
                                             race_meta=None))
        for c in by_race[race_id][:6]:
            try:
                rs = service.state_at(c["frame_index"])
            except Exception:
                continue
            T = float(rs.state_time_s)
            for e in rs.observable_drivers:
                num = rev.get(e.driver_id)
                if num is None or num not in per:
                    continue
                kd = per[num]

                def lat(k):
                    seq = kd.get(k, [])
                    ts = [x[0] for x in seq]
                    i = bisect.bisect_right(ts, T) - 1
                    return seq[i] if i >= 0 else (None, None)

                rt, rv = lat("Position")
                rp, cp = to_int(rv), e.position
                if rp is not None and cp is not None and rp != cp:
                    pos_dir[(rt is not None and e.observed_time_s is not None
                             and rt >= e.observed_time_s)] += 1
                    if rt is not None and e.observed_time_s is not None:
                        pos_age_diff.append((T - rt) - (T - e.observed_time_s))
                lt_, lv = lat("NumberOfLaps")
                rl, cl = to_int(lv), e.observed_lap_number
                if rl is not None and cl is not None and rl != cl:
                    lap_dir[rl - cl] += 1
                    if lt_ is not None and e.observed_time_s is not None:
                        lap_lag.append(lt_ - e.observed_time_s)
                nt_, nv = lat("NumberOfPitStops")
                rn, cn = to_int(nv), e.pit_stops_completed_so_far
                if rn is not None and cn is not None and rn != cn:
                    pit_dir[rn - cn] += 1
                    pit_detail[(season, c["stage"])] += 1
    print("pos_mismatch raw_ts>=canon_ts:", dict(pos_dir))
    pos_age_diff.sort()
    if pos_age_diff:
        print(f"pos raw_age-minus-canon_age n={len(pos_age_diff)} "
              f"median={pos_age_diff[len(pos_age_diff)//2]:.1f}s "
              f"p90={pos_age_diff[int(0.9*(len(pos_age_diff)-1))]:.1f}s")
    print("lap_diff_dist:", dict(sorted(lap_dir.items())))
    lap_lag.sort()
    if lap_lag:
        print(f"lap raw_ts-minus-canon_ts n={len(lap_lag)} "
              f"median={lap_lag[len(lap_lag)//2]:.1f}s")
    print("pit_diff_dist:", dict(sorted(pit_dir.items())))
    print("pit_mismatch by (season,stage):", dict(pit_detail))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
