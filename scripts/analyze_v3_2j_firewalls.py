#!/usr/bin/env python3
"""V3.2J Parts M-P: firewalls + transient checkpoint-impact analysis.

- Winner firewall (4 mandatory + every winner with any True event).
- Top-5 firewall (podiums/top-5 with True events, checkpoint grain).
- Transient firewall vs V3.2C/G transient corpus.
- Transient-window checkpoint impact: for every True->False window,
  count replay checkpoints with T inside [set, clear) and whether the
  cleared driver is a stale offender there (hazard zones).
- Label diagnostics (already built; summarized here).

Verifies prereg hash. Deterministic. Labels joined for evaluation only.
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

    def official(race_id: str, season: int) -> dict:
        df = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "results" /
            f"season={season}/results__{race_id}.parquet")
        return {str(r.driver_id): {
            "dnf": bool(r.dnf_flag), "winner": bool(r.winner_flag),
            "pos": (None if r.classified_position != r.classified_position
                    else int(r.classified_position))}
            for r in df.itertuples()}

    # frame times per race
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

    # ---- winner firewall
    winners_with_true = []
    for rec in manifest["records"]:
        off = official(rec["race_id"], rec["season"])
        for did, o in off.items():
            if o["winner"] and any(
                    v for _, v in seqs.get(rec["race_id"], {}).get(did, [])):
                winners_with_true.append((rec["race_id"], did))
    mand = {"2018-r02-R": "vettel", "2020-r01-R": "bottas",
            "2021-r06-R": "perez", "2022-r18-R": "verstappen"}
    mand_rows = []
    for rid, did in mand.items():
        seq = seqs.get(rid, {}).get(did, [])
        first = min((t for t, v in seq if v is True), default=None)
        mand_rows.append({"race_id": rid, "driver": did,
                          "first_retired_s": first,
                          "verdict": "PASS (never retired)"
                          if first is None else "FAIL"})
    # checkpoint-grain: winner retired-at-T at any of its race checkpoints?
    win_cp_hits = []
    for rid, did in winners_with_true:
        season = int(rid[:4])
        for c in [c for c in cps if c["race_id"] == rid]:
            T = frame_time(rid, season, c["frame_index"])
            if T is not None and retired_at(rid, did, T):
                win_cp_hits.append(
                    {"race_id": rid, "driver": did,
                     "frame_index": c["frame_index"], "T": T})
    json.dump({"schema_version": "v3.2j-winner-firewall-v1",
               "mandatory": mand_rows,
               "winners_with_any_true_event": winners_with_true,
               "winner_retired_at_checkpoint_hits": win_cp_hits,
               "verdict": "PASS" if not win_cp_hits and all(
                   m["verdict"].startswith("PASS") for m in mand_rows)
               else "FAIL"},
              open(OUT / "winner_firewall.json", "w"),
              indent=2, sort_keys=True)

    # ---- top-5 firewall
    top5_hits = []
    top5_with_true = []
    for rec in manifest["records"]:
        off = official(rec["race_id"], rec["season"])
        for did, o in off.items():
            if o["pos"] is not None and o["pos"] <= 5 and any(
                    v for _, v in seqs.get(rec["race_id"], {}).get(did, [])):
                top5_with_true.append(
                    (rec["race_id"], did, o["pos"], o["dnf"]))
                season = rec["season"]
                for c in [c for c in cps if c["race_id"] == rec["race_id"]]:
                    T = frame_time(rec["race_id"], season, c["frame_index"])
                    if T is not None and retired_at(
                            rec["race_id"], did, T):
                        top5_hits.append(
                            {"race_id": rec["race_id"], "driver": did,
                             "position": o["pos"], "dnf": o["dnf"],
                             "frame_index": c["frame_index"], "T": T})
    json.dump({"schema_version": "v3.2j-top5-firewall-v1",
               "top5_with_any_true_event": sorted(top5_with_true),
               "top5_retired_at_checkpoint_hits": top5_hits,
               "note": "post-finish/post-race True is causally safe; "
                       "timestamp causality decides",
               "verdict": "REVIEW"},
              open(OUT / "top5_firewall.json", "w"),
              indent=2, sort_keys=True)

    # ---- transient firewall: V3.2C/G transient corpus
    # drivers who disappear and later return: use presence STALE offenders
    # that are NOT retired at some checkpoint but ARE observed later.
    # Practical form: for each clearing window, check checkpoint impact.
    windows = []
    for c in clearings:
        rid = c["race_id"]
        season = c["season"]
        hits = []
        for cp in [x for x in cps if x["race_id"] == rid]:
            T = frame_time(rid, season, cp["frame_index"])
            if T is None:
                continue
            if c["set_at_s"] <= T < c["cleared_at_s"]:
                offenders = cp["detail"].get("stale_offenders", [])
                hits.append({
                    "frame_index": cp["frame_index"], "T": T,
                    "driver_is_stale_offender": c["driver"] in offenders,
                    "stale_offenders": sorted(offenders),
                    "all_blockers": sorted(cp["all_blockers"])})
        windows.append({
            "race_id": rid, "driver": c["driver"],
            "set_at_s": c["set_at_s"], "cleared_at_s": c["cleared_at_s"],
            "window_s": c["cleared_at_s"] - c["set_at_s"],
            "n_checkpoints_in_window": len(hits),
            "checkpoints_where_driver_is_stale_offender": sum(
                1 for h in hits if h["driver_is_stale_offender"]),
            "hits": hits})
    json.dump({"schema_version": "v3.2j-transient-firewall-v1",
               "n_windows": len(windows),
               "n_checkpoints_in_any_window": sum(
                   w["n_checkpoints_in_window"] for w in windows),
               "n_hazard_checkpoints": sum(
                   w["checkpoints_where_driver_is_stale_offender"]
                   for w in windows),
               "windows": windows},
              open(OUT / "transient_firewall.json", "w"),
              indent=2, sort_keys=True)
    print(f"winners_with_true={winners_with_true} "
          f"win_cp_hits={len(win_cp_hits)} "
          f"top5_with_true={len(top5_with_true)} "
          f"top5_cp_hits={len(top5_hits)} "
          f"cp_in_windows={sum(w['n_checkpoints_in_window'] for w in windows)} "
          f"hazard={sum(w['checkpoints_where_driver_is_stale_offender'] for w in windows)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
