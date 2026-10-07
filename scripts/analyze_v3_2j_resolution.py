#!/usr/bin/env python3
"""V3.2J Parts M-P (quantified) + AA-AB inputs: causal resolution analysis.

For every frozen replay checkpoint: retired-at-T stale offenders under
state-at-T semantics, unreliable-window suppression (True cleared while
the driver demonstrably continued: a D9 lap_start exists after the
clearing), continuation measurement (lap_start after T, evaluation
only), and firewall intersection (winner/top-5/transient).

Writes resolution_analysis.json. Verifies prereg hash. Deterministic.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from raceintel.simulation import driver_status as DS  # noqa: E402

OUT = ROOT / "results" / "v3" / "v3_2j"


def check_prereg() -> str:
    pre = json.load(open(OUT / "preregistration.json", encoding="utf-8"))
    expect = open(OUT / "preregistration.sha256", encoding="utf-8").read().strip()
    got = hashlib.sha256(json.dumps(pre, sort_keys=True).encode()).hexdigest()
    if got != expect:
        raise SystemExit(f"PREREG HASH MISMATCH: {got} != {expect}")
    return got


def main() -> int:
    check_prereg()
    import pandas as pd  # noqa: E402
    from raceintel.replay import replay as RP  # noqa: E402

    manifest = json.load(open(OUT / "source_manifest.json", encoding="utf-8"))
    seqs = json.load(open(OUT / "retired_transitions.json",
                          encoding="utf-8"))["sequences"]
    clearings = json.load(open(OUT / "retired_clearings.json",
                               encoding="utf-8"))["clearings"]
    raw = json.load(
        open(ROOT / "results" / "v3" / "v3_2f" / "coverage_opportunity_raw.json",
             encoding="utf-8"))
    cps = raw["checkpoints"]

    # lap starts per (race, driver): continuation evidence
    lap_cache: dict = {}

    def lap_starts(race_id: str, season: int, did: str) -> list:
        if ("laps", season) not in lap_cache:
            df = pd.read_parquet(
                ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9" /
                f"season={season}/driver_lap_state_d9__d9-{season}.parquet",
                columns=["race_id", "driver_id", "lap_start_s"])
            lap_cache[("laps", season)] = df
        df = lap_cache[("laps", season)]
        g = df[(df["race_id"] == race_id) & (df["driver_id"] == did)]
        return sorted(float(v) for v in g["lap_start_s"].values if v == v)

    # unreliable windows: cleared AND lap_start after clearing
    windows: dict[tuple, list] = {}
    for c in clearings:
        starts = lap_starts(c["race_id"], c["season"], c["driver"])
        continued = any(s > c["cleared_at_s"] for s in starts)
        if continued:
            windows.setdefault(
                (c["race_id"], c["driver"]), []).append(
                (c["set_at_s"], c["cleared_at_s"]))
    json.dump({"schema_version": "v3.2j-unreliable-windows-v1",
               "rule": "build-time source-reliability pinning (stream + "
                       "lap continuation only; no result labels): a True "
                       "that the same source retracts while the driver "
                       "demonstrably continues cannot exclude. Post-race "
                       "clears (no laps after) stay reliable.",
               "n_windows": sum(len(v) for v in windows.values()),
               "windows": {f"{k[0]}|{k[1]}": v
                           for k, v in sorted(windows.items())}},
              open(OUT / "unreliable_windows.json", "w"),
              indent=2, sort_keys=True)

    tl_cache: dict = {}

    def frame_time(race_id: str, season: int, idx: int) -> float | None:
        if race_id not in tl_cache:
            df = pd.read_parquet(
                ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9" /
                f"season={season}/driver_lap_state_d9__d9-{season}.parquet")
            df = df[df["race_id"] == race_id].copy()
            tl_cache[race_id] = RP.build_replay_timeline(df)
        tl = tl_cache[race_id]
        if idx < 0 or idx >= tl.frame_count:
            return None
        return float(tl.frame_at(idx).anchor_state_time_s)

    def retired_at(rid: str, did: str, T: float) -> bool:
        return DS.retired_known_at(
            [(t, v) for t, v in seqs.get(rid, {}).get(did, [])], T) is True

    def suppressed(rid: str, did: str, T: float) -> bool:
        return any(a <= T < b for a, b in windows.get((rid, did), []))

    season_of = {r["race_id"]: r["season"] for r in manifest["records"]}
    stale_cps = [c for c in cps
                 if "STALE_ROSTER_OBSERVATION" in c["all_blockers"]]
    OTHER = {"UNSUPPORTED_TRACK_STATE", "WET_CONDITIONS",
             "MISSING_DRIVER_OBSERVATION", "MISSING_TYRE_STATE",
             "TERMINAL_STATE"}
    analysis = {"n_stale_checkpoints": len(stale_cps), "resolved": [],
                "suppressed_only": [], "unresolved": [], "hazard": []}
    for c in stale_cps:
        rid = c["race_id"]
        season = season_of[rid]
        T = frame_time(rid, season, c["frame_index"])
        if T is None:
            analysis["unresolved"].append(
                [rid, c["frame_index"], "unmapped_time"])
            continue
        offenders = c["detail"].get("stale_offenders", [])
        ret = [o for o in offenders if retired_at(rid, o, T)]
        supp = [o for o in ret if suppressed(rid, o, T)]
        eff = [o for o in ret if o not in supp]
        unret = [o for o in offenders if o not in ret]
        clean = not (set(c["all_blockers"]) - {"STALE_ROSTER_OBSERVATION"})
        # continuation measurement (evaluation only): offender with a
        # timed lap_start after T is demonstrably still racing
        continuing = [o for o in eff
                      if any(s > T for s in lap_starts(rid, season, o))]
        key = [rid, c["frame_index"], sorted(offenders)]
        if continuing:
            analysis["hazard"].append(
                {"checkpoint": key, "T": T,
                 "continuing_despite_true": sorted(continuing),
                 "stale_only": clean})
        elif eff and not unret and not supp:
            # fully resolved, nothing suppressed
            if clean:
                analysis["resolved"].append(key)
            else:
                analysis["unresolved"].append(
                    [rid, c["frame_index"], "other_blockers_remain"])
        elif eff and not unret and supp:
            analysis["suppressed_only"].append(key)
        else:
            analysis["unresolved"].append(
                [rid, c["frame_index"], "stale_unresolved"])
    json.dump({"schema_version": "v3.2j-resolution-analysis-v1",
               "n_stale_checkpoints": analysis["n_stale_checkpoints"],
               "n_resolved_stale_only": len(analysis["resolved"]),
               "n_suppressed_only": len(analysis["suppressed_only"]),
               "n_hazard": len(analysis["hazard"]),
               "hazard_all_stale_only": all(
                   h["stale_only"] for h in analysis["hazard"]),
               "hazard": analysis["hazard"],
               "resolved": sorted(analysis["resolved"]),
               "suppressed_only": sorted(analysis["suppressed_only"])},
              open(OUT / "resolution_analysis.json", "w"),
              indent=2, sort_keys=True)
    print(f"stale={len(stale_cps)} resolved_stale_only={len(analysis['resolved'])} "
          f"suppressed_only={len(analysis['suppressed_only'])} "
          f"hazard={len(analysis['hazard'])}")
    for h in analysis["hazard"][:20]:
        print("HAZARD", h["checkpoint"], h["continuing_despite_true"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
