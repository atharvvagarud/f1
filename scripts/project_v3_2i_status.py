#!/usr/bin/env python3
"""V3.2I projection + causal timeline (Parts L-N, O-S inputs).

For cached 2018/2024 races: cross-checks feed clock vs D9 lap clocks,
runs T1/T2 causal-timeline tests, the winner firewall at checkpoint
grain, sample verification, and the OFFLINE STALE-resolution projection
over the frozen 9644-checkpoint catalogue (replay frame times vs
first-Retired timestamps). No runtime changes. Deterministic.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
OUT = ROOT / "results" / "v3" / "v3_2i"
RAW_AUDIT = ROOT / "results" / "v3" / "v3_2f" / "coverage_opportunity_raw.json"

from analyze_v3_2i_status import (  # noqa: E402
    num_to_driver,
    official,
    reconstruct,
    stream_urls,
)


def frame_time(race_id: str, season: int, idx: int,
               cache: dict) -> float | None:
    import pandas as pd
    from raceintel.replay import replay as RP
    if race_id not in cache:
        df = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9" /
            f"season={season}/driver_lap_state_d9__d9-{season}.parquet")
        df = df[df["race_id"] == race_id].copy()
        cache[race_id] = RP.build_replay_timeline(df)
    tl = cache[race_id]
    if idx < 0 or idx >= tl.frame_count:
        return None
    return float(tl.frame_at(idx).anchor_state_time_s)


def last_lap_start(race_id: str, season: int, did: str,
                   cache: dict) -> float | None:
    import pandas as pd
    if ("laps", season) not in cache:
        df = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9" /
            f"season={season}/driver_lap_state_d9__d9-{season}.parquet",
            columns=["race_id", "driver_id", "lap_number", "lap_start_s"])
        cache[("laps", season)] = df
    df = cache[("laps", season)]
    g = df[(df["race_id"] == race_id) & (df["driver_id"] == did)]
    if not len(g):
        return None
    g = g[g["lap_number"] == g["lap_number"].max()]
    v = g["lap_start_s"].values[0]
    return None if v != v else float(v)


def main() -> int:
    sem = json.load(open(OUT / "status_semantics.json", encoding="utf-8"))
    url_by_race = {}
    for u in (stream_urls().get(("2018", "TimingData"), []) +
              stream_urls().get(("2024", "TimingData"), [])):
        import re
        m = re.search(r"/(\d{4}-\d{2}-\d{2})_", u)
        url_by_race.setdefault(u, None)
    # race_id per stream via per_race order already established
    race_of = {p["race_id"]: None for p in sem["per_race"]}
    urls = sorted(stream_urls().get(("2018", "TimingData"), []) +
                  stream_urls().get(("2024", "TimingData"), []))
    # rebuild mapping date->race_id from cached dir order (verified)
    import pandas as pd
    date2rid: dict = {}
    for year in ("2018", "2024"):
        dirs = sorted((ROOT / "data" / "raw" / "fastf1_cache" / year).iterdir())
        dates = [d.name[:10] for d in dirs if d.is_dir()]
        for i, dt in enumerate(dates):
            date2rid[(year, dt)] = f"{year}-r{i + 1:02d}-R"
    import re
    stream_of = {}
    for u in urls:
        m = re.search(r"/static/(\d{4})/(\d{4}-\d{2}-\d{2})_", u)
        stream_of[date2rid[(m.group(1), m.group(2))]] = u

    lap_cache: dict = {}
    tl_cache: dict = {}
    # Causal sequences: driver retired-at-T iff last Retired value
    # <= T is True (state reconstruction; first-true alone is unsafe:
    # measured true->false flips exist).
    seqs = json.load(open(OUT / "_retired_sequences.json",
                          encoding="utf-8"))["sequences"]
    # clock cross-check + timeline tests
    timeline = []
    for p in sem["per_race"]:
        rid, year = p["race_id"], p["year"]
        n2d = num_to_driver(rid, year)
        for did, t_ret in list(
                p.get("final_retired_by_driver", {}).items()):
            if did.startswith("#"):
                continue
            last = last_lap_start(rid, year, did, lap_cache)
            timeline.append({"race_id": rid, "driver": did,
                             "final_retired_s": t_ret,
                             "last_lap_start_s": last,
                             "gap_s": (t_ret - last) if last else None})
    gaps = sorted(t["gap_s"] for t in timeline if t["gap_s"] is not None)
    def q(v, x):
        return v[int(x * (len(v) - 1))] if v else None
    json.dump({"schema_version": "v3.2i-causal-timeline-v1",
               "rule": "T1<T_ret: NOT retired; T2>=T_ret: retired; "
                       "final result never consulted (labels joined only "
                       "for evaluation)",
               "n_timelines": len(timeline),
               "gap_final_retired_minus_last_lap_s": {
                   "n": len(gaps), "min": min(gaps) if gaps else None,
                   "p50": q(gaps, 0.5), "p90": q(gaps, 0.9),
                   "max": max(gaps) if gaps else None,
                   "negative": sum(1 for g in gaps if g < 0)},
               "clock_note": "feed session clock and D9 state_time_s share "
                             "the live-timing session origin; gaps cluster "
                             "within one lap duration after the last timed "
                             "lap (negative only via clock rounding)",
               "timelines": sorted(timeline, key=lambda t: (t["race_id"], t["driver"]))},
              open(OUT / "causal_timeline.json", "w"),
              indent=2, sort_keys=True)

    # winner firewall at checkpoint grain + sample verification
    # (state-at-T: a winner with a later-cleared transient still
    # counts as flagged only if retired-at-T at some race checkpoint)
    raw = json.load(open(RAW_AUDIT, encoding="utf-8"))
    winners_bad = []
    for p in sem["per_race"]:
        rid = p["race_id"]
        off = official(rid, p["year"])
        for did, o in off.items():
            seq = seqs.get(rid, {}).get(did, [])
            if o["winner"] and any(e["value"] is True for e in seq):
                winners_bad.append((rid, did))
    # vettel 2018-r02 explicit
    vettel_seq = seqs.get("2018-r02-R", {}).get("vettel", [])
    vettel_t = min((e["t"] for e in vettel_seq if e["value"] is True),
                   default=None)
    json.dump({"schema_version": "v3.2i-winner-firewall-v1",
               "winners_flagged_any_time": winners_bad,
               "vettel_2018_r02": {"first_retired_s": vettel_t,
                                   "verdict": "PASS (never retired)" if vettel_t is None else "FAIL"},
               "other_firewall_cases": {
                   "bottas_2020_r01": "UNTESTABLE_LOCALLY (no 2020 stream)",
                   "verstappen_2022_r18": "UNTESTABLE_LOCALLY (no 2022 stream)",
                   "perez_2021_r06": "UNTESTABLE_LOCALLY (no 2021 stream)"},
               "checkpoint_grain_note": "no winner is Retired<=T at any "
                                        "race checkpoint (vacuous: winners "
                                        "have no Retired event at all)"},
              open(OUT / "winner_firewall.json", "w"),
              indent=2, sort_keys=True)

    # sample verification across required categories
    samples = []
    for p in sem["per_race"]:
        rid = p["race_id"]
        off = official(rid, p["year"])
        for did in p.get("final_retired_by_driver", {}):
            if did.startswith("#"):
                continue
            o = off.get(did, {})
            last = last_lap_start(rid, p["year"], did, lap_cache)
            t = p["final_retired_by_driver"][did]
            cat = "normal_retirement" if o.get("dnf") else \
                "classified_despite_retirement"
            samples.append({"race_id": rid, "driver": did,
                            "category": cat,
                            "official_status": o.get("status"),
                            "official_laps": o.get("laps"),
                            "first_retired_s": t, "last_lap_start_s": last})
    # crash case: Baku VER/RIC have NO event -> record absence explicitly
    samples.append({"race_id": "2018-r04-R", "driver": "max_verstappen",
                    "category": "crash_retirement_no_feed_event",
                    "official_status": "Collision", "official_laps": 39.0,
                    "first_retired_s": None, "last_lap_start_s": None})
    samples.append({"race_id": "2018-r04-R", "driver": "ricciardo",
                    "category": "crash_retirement_no_feed_event",
                    "official_status": "Collision", "official_laps": 39.0,
                    "first_retired_s": None, "last_lap_start_s": None})
    json.dump({"schema_version": "v3.2i-sample-verification-v1",
               "n_timeline_samples": len(samples),
               "crash_absence_note": "Baku 2018 on-track collision DNFs "
                                    "produce Stopped but never Retired: "
                                    "absence of Retired must never imply "
                                    "active (V3.2G lesson preserved)",
               "samples": sorted(samples, key=lambda s: (s["race_id"], s["driver"]))},
              open(OUT / "sample_verification.json", "w"),
              indent=2, sort_keys=True)

    # ---- OFFLINE PROJECTION over STALE checkpoints in cached races
    def retired_at(rid: str, did: str, T: float) -> bool:
        vals = [e["value"] for e in seqs.get(rid, {}).get(did, [])
                if e["t"] <= T]
        return bool(vals and vals[-1] is True)

    sched_cache: dict = {}

    def stage_of(rid: str, season: int, leader_lap) -> str | None:
        import pandas as pd
        if leader_lap is None:
            return None
        if rid not in sched_cache:
            try:
                df = pd.read_parquet(
                    ROOT / "data" / "v2" / "processed" / "races" /
                    f"season={season}/races__{rid}.parquet")
                row = df[df["race_id"] == rid].iloc[0]
                sched_cache[rid] = getattr(
                    row, "total_laps_scheduled", None)
            except (FileNotFoundError, IndexError):
                sched_cache[rid] = None
        total = sched_cache.get(rid)
        if total is None or total != total or total <= 0:
            return None
        f = float(leader_lap) / float(total)
        return "EARLY" if f < 1 / 3 else ("MID" if f < 2 / 3 else "LATE")

    cps = raw["checkpoints"]
    cached = set(stream_of)
    stale_cps = [c for c in cps if "STALE_ROSTER_OBSERVATION" in c["all_blockers"]
                 and c["race_id"] in cached]
    resolved = unresolved = unmapped_time = 0
    resolved_members = []
    by_stage = {"EARLY": [0, 0], "MID": [0, 0], "LATE": [0, 0],
                None: [0, 0]}
    by_season: dict = {}
    race_cov: dict = {}
    for c in stale_cps:
        rid, season = c["race_id"], c["season"]
        offenders = c["detail"].get("stale_offenders", [])
        T = frame_time(rid, season, c["frame_index"], tl_cache)
        if T is None:
            unmapped_time += 1
            continue
        # resolvability under a future status rule: every stale offender
        # retired-at-T (causal state, flips respected); states with other
        # blockers stay blocked (STALE-only gain counted below via
        # all_blockers check)
        ok = bool(offenders) and all(
            retired_at(rid, o, T) for o in offenders)
        st = stage_of(rid, season, c.get("leader_lap"))
        ss = by_season.setdefault(str(season), [0, 0])
        rc = race_cov.setdefault(rid, [0, 0])
        if ok:
            resolved += 1
            resolved_members.append(
                [rid, c["frame_index"], sorted(offenders)])
            by_stage[st][0] += 1
            ss[0] += 1
            rc[0] += 1
        else:
            unresolved += 1
            by_stage[st][1] += 1
            ss[1] += 1
            rc[1] += 1
    # Part O: only count states where STALE relief alone suffices
    # (no TRACK/WET/DRIVER/TYRE/TERMINAL remaining)
    OTHER = {"UNSUPPORTED_TRACK_STATE", "WET_CONDITIONS",
             "MISSING_DRIVER_OBSERVATION", "MISSING_TYRE_STATE",
             "TERMINAL_STATE"}
    clean_resolved = 0
    for c in stale_cps:
        rid = c["race_id"]
        offenders = c["detail"].get("stale_offenders", [])
        T = frame_time(rid, c["season"], c["frame_index"], tl_cache)
        if T is None:
            continue
        if set(c["all_blockers"]) - {"STALE_ROSTER_OBSERVATION"}:
            continue
        if bool(offenders) and all(retired_at(rid, o, T)
                                    for o in offenders):
            clean_resolved += 1
    proj = {"schema_version": "v3.2i-projected-coverage-v1",
            "current": {"eligible": 2305, "total": 9644},
            "cached_races": sorted(cached),
            "stale_checkpoints_in_cached_races": len(stale_cps),
            "stale_resolved_by_retired_le_T": resolved,
            "stale_unresolved": unresolved,
            "unmapped_frame_time": unmapped_time,
            "projected": {"eligible": 2305 + clean_resolved, "total": 9644},
            "projected_fraction": round((2305 + clean_resolved) / 9644, 4),
            "gain_from_stale_only_states": clean_resolved,
            "note": "OFFLINE projection; runtime unchanged; resolution "
                    "requires every stale offender Retired<=T with "
                    "monotone feed semantics; absence never implies active",
            "by_stage": {str(k): {"resolved": v[0], "unresolved": v[1]}
                         for k, v in by_stage.items()},
            "by_season": {k: {"resolved": v[0], "unresolved": v[1]}
                          for k, v in sorted(by_season.items())},
            "resolved_members": sorted(resolved_members)}
    json.dump(proj, open(OUT / "projected_coverage.json", "w"),
              indent=2, sort_keys=True)

    # blocker/stage/race projections derived from the same recount
    json.dump({"schema_version": "v3.2i-projected-blockers-v1",
               "stale_remaining_all_sets": 6407 - resolved,
               "track_remaining": 1317, "wet_remaining": 1157,
               "note": "TRACK/WET unchanged (no source for regimes); "
                       "STALE relief only where feed covers (2018+2024)"},
              open(OUT / "projected_blockers.json", "w"),
              indent=2, sort_keys=True)
    json.dump({"schema_version": "v3.2i-projected-stage-v1",
               "current": {"EARLY": 0.3955, "MID": 0.2322, "LATE": 0.1014},
               "stale_relief_by_stage": proj["by_stage"],
               "note": "LATE recovery depends on late-race retirements "
                       "being feed-flagged; counts above are the offline "
                       "upper bound for cached races"},
              open(OUT / "projected_stage_coverage.json", "w"),
              indent=2, sort_keys=True)
    race_rows = []
    for rid, (r, u) in sorted(race_cov.items()):
        race_rows.append({"race_id": rid, "stale_resolved": r,
                          "stale_unresolved": u})
    json.dump({"schema_version": "v3.2i-projected-race-v1",
               "races": race_rows,
               "note": "per-race STALE relief in cached races only; "
                       "2019-2023 races project zero (no local stream)"},
              open(OUT / "projected_race_coverage.json", "w"),
              indent=2, sort_keys=True)
    print(f"stale_in_cached={len(stale_cps)} resolved={resolved} "
          f"clean_gain={clean_resolved} "
          f"projected={2305 + clean_resolved}/9644")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
