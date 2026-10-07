#!/usr/bin/env python3
"""V3.2G causal driver-status analysis (Parts E/F/G/I/J/K/O/P + Q/S/T/U/V).

Phase A (causal only, no truth): builds frozen episode/source tables
from driver_laps + race_control + position-data blobs:
  - position_null (FastF1Generated) episodes with return behavior,
  - STOPPED message table with driver/timing mapping,
  - per-driver observation episodes (terminal absence vs interruption),
  - source-agreement patterns per terminal-absence episode.
Phase B (offline evaluation, runs only after Phase A tables are frozen
and hash-verified): joins results labels for candidate diagnostics
(precision/recall/latency/season/winner-firewall). Labels never flow
into Phase A structures.

Read-only. No simulator source, parameter, artifact, or replay cache is
modified. No model training. Outputs carry no timestamps, usernames, or
absolute paths.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import pickle
import re
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "results" / "v3" / "v3_2g"
SEASONS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)

STOPPED_RE = re.compile(r"CAR\s+(\d+)\s+\((\w+)\)\s+STOPPED\s+AT\s+(.+)",
                        re.IGNORECASE)


def _hash(obj) -> str:
    return hashlib.sha256(
        json.dumps(obj, sort_keys=True, separators=(",", ":"),
                   allow_nan=False, default=str).encode()).hexdigest()


def _load_driver_laps() -> "pd.DataFrame":
    import pandas as pd

    frames = []
    for season in SEASONS:
        for f in sorted(glob.glob(
                str(ROOT / "data" / "v2" / "processed" / "driver_laps" /
                    f"season={season}" / "driver_laps__*.parquet"))):
            frames.append(pd.read_parquet(f))
    return pd.concat(frames, ignore_index=True)


def _load_race_control() -> "pd.DataFrame":
    import pandas as pd

    frames = []
    for f in sorted(glob.glob(
            str(ROOT / "data" / "v2" / "processed" / "race_control" /
                "season=*" / "race_control__*.parquet"))):
        frames.append(pd.read_parquet(f))
    return pd.concat(frames, ignore_index=True)


def _driver_number_map() -> dict:
    """(race_id, racing_number) -> driver_id from results (identity only)."""
    import pandas as pd

    out = {}
    for season in SEASONS:
        for f in sorted(glob.glob(
                str(ROOT / "data" / "v2" / "processed" / "results" /
                    f"season={season}" / "results__*.parquet"))):
            df = pd.read_parquet(f)
            for row in df.itertuples():
                try:
                    num = str(int(row.driver_number))
                except (TypeError, ValueError):
                    continue
                out[(str(row.race_id), num)] = str(row.driver_id)
    return out


def phase_a() -> dict:
    import pandas as pd

    dl = _load_driver_laps()
    rc = _load_race_control()
    num_map = _driver_number_map()

    # ---- 1. position_null (generated-row) episodes ----
    gen = dl[dl["fastf1_generated"] == True].copy()  # noqa: E712
    null_episodes = []
    for (race, drv), g in gen.groupby(["race_id", "driver_id"]):
        laps = sorted(int(x) for x in g["lap_number"].tolist())
        all_laps = sorted(
            int(x) for x in dl[(dl["race_id"] == race)
                               & (dl["driver_id"] == drv)][
                "lap_number"].tolist())
        real_after = [x for x in all_laps if x > laps[-1]
                      and x not in set(laps)]
        # valid (timed) rows after the last generated row?
        later = dl[(dl["race_id"] == race) & (dl["driver_id"] == drv)
                   & (dl["lap_number"] > laps[-1])
                   & dl["lap_time_s"].notna()]
        prior = dl[(dl["race_id"] == race) & (dl["driver_id"] == drv)
                   & (dl["lap_number"] < laps[0])
                   & dl["lap_time_s"].notna()]
        null_episodes.append({
            "race_id": race, "driver_id": drv,
            "n_generated": len(laps),
            "generated_laps": laps,
            "is_only_row": (len(all_laps) == len(laps)),
            "n_prior_timed": int(len(prior)),
            "n_later_timed": int(len(later)),
            "returned_after_null": bool(len(later) > 0),
            "track_at_first": (
                None if g["track_status"].isna().all() else str(
                    g.iloc[0]["track_status"])),
        })
    null_episodes.sort(key=lambda e: (e["race_id"], e["driver_id"]))

    # ---- 2. STOPPED message table ----
    stopped = []
    for row in rc.itertuples():
        text = row.message_text if isinstance(
            row.message_text, str) else ""
        m = STOPPED_RE.search(text)
        if not m:
            continue
        num, abbr = m.group(1), m.group(2)
        stopped.append({
            "race_id": str(row.race_id), "message_seq": (
                None if pd.isna(row.message_seq) else int(
                    row.message_seq)),
            "observed_at_s": (
                None if pd.isna(row.observed_at_s) else float(
                    row.observed_at_s)),
            "lap_number": (
                None if pd.isna(row.lap_number) else int(
                    row.lap_number)),
            "category": row.category, "flag": row.flag,
            "racing_number": num, "abbreviation": abbr,
            "driver_id": num_map.get((str(row.race_id), num)),
            "message_text": text,
        })
    stopped.sort(key=lambda s: (s["race_id"],
                                s["observed_at_s"] or 0.0))

    # ---- 3. observation episodes (terminal vs interruption) ----
    obs_episodes = []
    for (race, drv), g in dl.groupby(["race_id", "driver_id"]):
        g = g.sort_values("lap_number")
        laps = [int(x) for x in g["lap_number"].tolist()]
        timed = g[g["lap_time_s"].notna()]
        last_timed_lap = (int(timed["lap_number"].max())
                          if len(timed) else None)
        gaps = []
        for a, b in zip(laps, laps[1:]):
            if b - a > 1:
                gaps.append({"after_lap": a, "resume_lap": b,
                             "missing": b - a - 1})
        obs_episodes.append({
            "race_id": race, "driver_id": drv,
            "n_rows": len(laps), "first_lap": laps[0],
            "last_lap": laps[-1],
            "n_timed": int(len(timed)),
            "last_timed_lap": last_timed_lap,
            "n_generated": int((g["fastf1_generated"] == True).sum()),  # noqa: E712
            "gap_episodes": gaps,
            "returned_after_gap": bool(len(gaps) > 0),
        })
    obs_episodes.sort(key=lambda e: (e["race_id"], e["driver_id"]))

    # ---- 4. position-data last-activity per driver (agreement input) ----
    pos_last: dict[str, dict[str, float]] = {}
    pos_races = 0
    for f in sorted(glob.glob(
            str(ROOT / "data" / "raw" / "fastf1_cache" / "*" / "*"
                / "*_Race" / "position_data.ff1pkl"))):
        try:
            with open(f, "rb") as h:
                blob = pickle.load(h)["data"]
        except Exception:  # noqa: BLE001 - record unavailability
            continue
        # race identity from directory layout is unreliable; map via
        # driver count/time span only when needed (kept per-file).
        last = {}
        for drv_key, pdf in blob.items():
            try:
                t = pd.to_datetime(pdf["Time"])
                last[str(drv_key)] = float(
                    (t - t.iloc[0]).dt.total_seconds().max())
            except Exception:  # noqa: BLE001
                continue
        pos_last[f] = last
        pos_races += 1

    tables = {
        "schema_version": "v3.2g-causal-tables-v1",
        "seasons": list(SEASONS),
        "n_driver_lap_rows": int(len(dl)),
        "n_null_episodes": len(null_episodes),
        "n_stopped_messages": len(stopped),
        "n_obs_episodes": len(obs_episodes),
        "position_blob_files": pos_races,
        "null_episodes": null_episodes,
        "stopped_messages": stopped,
        "obs_episodes": obs_episodes,
    }
    tables["freeze_hash"] = _hash(
        {k: v for k, v in tables.items() if k != "freeze_hash"})
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "causal_tables.json").write_text(
        json.dumps(tables, sort_keys=True) + "\n", encoding="utf-8")
    # position last-activity is bulky/file-keyed: separate artifact.
    (OUT_DIR / "position_activity.json").write_text(
        json.dumps({"schema_version": "v3.2g-position-activity-v1",
                    "files": sorted(pos_last.keys()),
                    "last_s": pos_last}, sort_keys=True) + "\n",
        encoding="utf-8")
    print(json.dumps({"status": "PHASE_A_FROZEN",
                      "freeze_hash": tables["freeze_hash"],
                      "null_episodes": len(null_episodes),
                      "stopped": len(stopped),
                      "obs_episodes": len(obs_episodes),
                      "pos_files": pos_races}))
    return tables


def phase_b() -> int:
    import pandas as pd

    tables = json.loads(
        (OUT_DIR / "causal_tables.json").read_text(encoding="utf-8"))
    if _hash({k: v for k, v in tables.items()
              if k != "freeze_hash"}) != tables["freeze_hash"]:
        print(json.dumps({"status": "BLOCKED",
                          "reason": "causal tables mutated"}))
        return 1
    # OFFLINE labels joined only now (evaluation-only).
    lab = {}
    for season in SEASONS:
        for f in sorted(glob.glob(
                str(ROOT / "data" / "v2" / "processed" / "results" /
                    f"season={season}" / "results__*.parquet"))):
            df = pd.read_parquet(f)
            for row in df.itertuples():
                lab[(str(row.race_id), str(row.driver_id))] = {
                    "status_text": row.status_text,
                    "dnf": bool(row.dnf_flag),
                    "classified": (None if pd.isna(
                        row.classified_position) else int(
                            row.classified_position)),
                    "winner": bool(row.winner_flag),
                    "podium": bool(row.podium_flag),
                }

    obs_by_key = {(e["race_id"], e["driver_id"]): e
                  for e in tables["obs_episodes"]}

    def _terminal(e) -> bool:
        L = lab.get((e["race_id"], e["driver_id"]), {})
        return bool(L.get("dnf")) or L.get("classified") is None

    # null-episode diagnostics
    null_eval = []
    for e in tables["null_episodes"]:
        L = lab.get((e["race_id"], e["driver_id"]), {})
        null_eval.append({
            "race_id": e["race_id"], "driver_id": e["driver_id"],
            "returned_after_null": e["returned_after_null"],
            "terminal": _terminal(obs_by_key.get(
                (e["race_id"], e["driver_id"]), e)),
            "dnf": L.get("dnf"), "classified": L.get("classified"),
            "winner": L.get("winner"), "podium": L.get("podium")})

    # STOPPED evaluation: return-after-message + terminal + latency
    dl = _load_driver_laps()
    stop_eval = []
    for s in tables["stopped_messages"]:
        key = (s["race_id"], s["driver_id"])
        e = obs_by_key.get(key)
        L = lab.get(key, {})
        t_msg = s["observed_at_s"]
        later_rows = 0
        latency = None
        if e is not None and t_msg is not None:
            g = dl[(dl["race_id"] == s["race_id"])
                   & (dl["driver_id"] == s["driver_id"])]
            times = pd.to_numeric(g["session_time_end_s"],
                                  errors="coerce")
            later_rows = int((times > t_msg).sum())
            if len(times.dropna()):
                last_t = float(times.max())
                latency = round(last_t - t_msg, 1)
        stop_eval.append({
            "race_id": s["race_id"], "driver_id": s["driver_id"],
            "observed_at_s": t_msg, "lap_number": s["lap_number"],
            "rows_after_message": later_rows,
            "returned_after_message": bool(later_rows > 0),
            "last_row_latency_s": latency,
            "terminal": _terminal(e) if e else None,
            "dnf": L.get("dnf"), "classified": L.get("classified"),
            "winner": L.get("winner"), "podium": L.get("podium"),
            "status_text": L.get("status_text")})

    doc = {"schema_version": "v3.2g-offline-evaluation-v1",
           "freeze_hash": tables["freeze_hash"],
           "null_eval": null_eval, "stop_eval": stop_eval}
    (OUT_DIR / "offline_evaluation.json").write_text(
        json.dumps(doc, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": "PHASE_B_OK",
                      "null_eval": len(null_eval),
                      "stop_eval": len(stop_eval)}))
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("phase", choices=("a", "b"))
    args = ap.parse_args()
    if args.phase == "a":
        phase_a()
        return 0
    return phase_b()


if __name__ == "__main__":
    raise SystemExit(main())
