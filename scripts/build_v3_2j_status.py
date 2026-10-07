#!/usr/bin/env python3
"""V3.2J Parts H-L + Q-R: build derived Retired status corpus (149 races).

Reads pinned TimingData streams (local sqlite cache for 2018/2024,
fetched files for 2019-2023; 2025 NEVER read), reconstructs causal
per-driver Retired transitions with the immutable adapter, resolves
stream racing numbers to D9 driver_ids, and writes one deterministic
derived artifact per race plus season/schema/clock/clearing evidence.

Final result labels are joined AFTER freezing timelines, for
diagnostics only. Verifies the prereg hash first. Deterministic.
"""

from __future__ import annotations

import hashlib
import json
import pickle
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from raceintel.simulation import driver_status as DS  # noqa: E402

OUT = ROOT / "results" / "v3" / "v3_2j"
STATUS_DIR = OUT / "status"
SQLITE = ROOT / "data" / "raw" / "fastf1_cache" / "fastf1_http_cache.sqlite"
RAW_DIR = ROOT / "data" / "raw" / "fastf1_cache" / "v3_2j_timing"


def check_prereg() -> str:
    pre = json.load(open(OUT / "preregistration.json", encoding="utf-8"))
    expect = open(OUT / "preregistration.sha256", encoding="utf-8").read().strip()
    got = hashlib.sha256(json.dumps(pre, sort_keys=True).encode()).hexdigest()
    if got != expect:
        raise SystemExit(f"PREREG HASH MISMATCH: {got} != {expect}")
    return got


def sqlite_streams() -> dict[str, str]:
    con = sqlite3.connect(SQLITE)
    out: dict[str, str] = {}
    for (v,) in con.execute("select value from responses").fetchall():
        d = pickle.loads(v)
        u = d.get("url", "")
        if u.endswith("/TimingData.jsonStream") and "/2018/" in u or \
                u.endswith("/TimingData.jsonStream") and "/2024/" in u:
            raw = d["_content"]
            if isinstance(raw, (bytes, bytearray)):
                raw = bytes(raw).decode("utf-8-sig")
            out[u] = raw
    return out


def main() -> int:
    prereg_hash = check_prereg()
    import pandas as pd  # noqa: E402

    manifest = json.load(open(OUT / "source_manifest.json", encoding="utf-8"))
    cached = sqlite_streams()
    # url -> race_id for cached streams
    url_race = {r["source_locator"]: r["race_id"] for r in manifest["records"]
                if r["retrieval_status"] == "local_cache"}
    assert len(cached) == 45, f"expected 45 cached, got {len(cached)}"
    assert set(cached) == set(url_race), "cached URL set drifted"

    STATUS_DIR.mkdir(parents=True, exist_ok=True)
    by_season: dict = {}
    transitions_all: dict = {}
    clearings: list = []
    clock_rows: list = []
    label_rows: list = []
    corpus_hashes: dict = {}
    n2d_cache: dict = {}

    def num_to_driver(race_id: str, season: int) -> dict:
        if (race_id, season) not in n2d_cache:
            df = pd.read_parquet(
                ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9" /
                f"season={season}/driver_lap_state_d9__d9-{season}.parquet",
                columns=["race_id", "driver_id", "driver_number"])
            df = df[df["race_id"] == race_id]
            n2d_cache[(race_id, season)] = {
                str(int(n)): d for d, n in
                df[["driver_id", "driver_number"]].drop_duplicates()
                .itertuples(index=False)}
        return n2d_cache[(race_id, season)]

    def official(race_id: str, season: int) -> dict:
        df = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "results" /
            f"season={season}/results__{race_id}.parquet")
        out = {}
        for r in df.itertuples():
            out[str(r.driver_id)] = {
                "dnf": bool(r.dnf_flag), "status": str(r.status_text),
                "winner": bool(r.winner_flag),
                "position": (None if r.classified_position != r.classified_position
                             else int(r.classified_position))}
        return out

    def last_lap_start(race_id: str, season: int, did: str,
                       cache: dict) -> float | None:
        if ("laps", season) not in cache:
            df = pd.read_parquet(
                ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9" /
                f"season={season}/driver_lap_state_d9__d9-{season}.parquet",
                columns=["race_id", "driver_id", "lap_number",
                         "lap_start_s"])
            cache[("laps", season)] = df
        df = cache[("laps", season)]
        g = df[(df["race_id"] == race_id) & (df["driver_id"] == did)]
        if not len(g):
            return None
        g = g[g["lap_number"] == g["lap_number"].max()]
        v = g["lap_start_s"].values[0]
        return None if v != v else float(v)

    lap_cache: dict = {}
    for rec in sorted(manifest["records"], key=lambda r: r["race_id"]):
        rid, season = rec["race_id"], rec["season"]
        if rec["retrieval_status"] == "local_cache":
            raw = cached[rec["source_locator"]]
            raw_sha = rec["content_sha256"]
            served = "official_cache"
        else:
            p = RAW_DIR / str(season) / f"{rid}.jsonStream"
            raw = p.read_text(encoding="utf-8-sig")
            raw_sha = hashlib.sha256(
                p.read_bytes()).hexdigest()
            assert raw_sha == rec["content_sha256"], rid
            served = rec.get("served_by", "fetched")
        events, diag = DS.parse_timing_stream(raw)
        trans_num = DS.build_retired_transitions(events)
        n2d = num_to_driver(rid, season)
        trans: dict[str, list] = {}
        unmapped: list = []
        for num, seq in trans_num.items():
            did = n2d.get(num)
            if did is None:
                unmapped.append(num)
                continue
            trans[did] = [[t, v] for t, v in seq]
        # true->false audit (number space -> driver space)
        for num, seq in trans_num.items():
            for i in range(1, len(seq)):
                if seq[i - 1][1] is True and seq[i][1] is False:
                    clearings.append({
                        "race_id": rid, "season": season,
                        "driver": n2d.get(num, "#" + num),
                        "set_at_s": seq[i - 1][0],
                        "cleared_at_s": seq[i][0]})
        content_hash = hashlib.sha256(
            json.dumps(trans, sort_keys=True).encode()).hexdigest()
        artifact = {
            "schema_version": "v3.2j-derived-status-v1",
            "race_id": rid, "season": season, "round": rec["round"],
            "session": "Race",
            "source_locator": rec["source_locator"],
            "raw_sha256": raw_sha,
            "served_by": served,
            "adapter_version": DS.RAW_ADAPTER_VERSION,
            "status_contract_version": DS.STATUS_CONTRACT_VERSION,
            "transitions": trans,
            "unmapped_stream_numbers": sorted(unmapped),
            "n_transitions": sum(len(v) for v in trans.values()),
            "n_drivers_with_updates": len(trans),
            "content_hash": content_hash,
            "diagnostics": {
                "n_messages": diag.n_messages,
                "n_retired_updates": diag.n_retired_updates,
                "n_stopped_updates": diag.n_stopped_updates,
                "n_inpit_updates": diag.n_inpit_updates,
                "n_pitout_updates": diag.n_pitout_updates,
                "n_malformed_rows": diag.n_malformed_rows,
                "n_non_dict_deltas": diag.n_non_dict_deltas,
            },
        }
        json.dump(artifact, open(STATUS_DIR / f"{rid}.json", "w"),
                  indent=2, sort_keys=True)
        corpus_hashes[rid] = content_hash
        transitions_all[rid] = trans

        s = by_season.setdefault(str(season), {
            "races": 0, "races_parsed": 0, "drivers_with_updates": 0,
            "true_events": 0, "false_clearings": 0, "schema_variants": [],
            "malformed_rows": 0, "unknown_values": 0,
            "drivers_seen_per_race": []})
        s["races"] += 1
        s["races_parsed"] += 1
        s["drivers_with_updates"] += len(trans)
        s["true_events"] += sum(1 for seq in trans.values()
                                for _, v in seq if v is True)
        s["false_clearings"] += sum(
            1 for c in clearings if c["race_id"] == rid)
        s["malformed_rows"] += diag.n_malformed_rows
        s["drivers_seen_per_race"].append(len(diag.drivers_seen))

        off = official(rid, season)
        for did, seq in trans.items():
            trues = [t for t, v in seq if v is True]
            last = last_lap_start(rid, season, did, lap_cache)
            if trues:
                first = min(trues)
                clock_rows.append({
                    "race_id": rid, "driver": did,
                    "first_retired_s": first, "last_lap_start_s": last,
                    "gap_s": (first - last) if last else None})
            o = off.get(did, {})
            label_rows.append({
                "race_id": rid, "driver": did, "season": season,
                "n_true": len(trues),
                "official_dnf": o.get("dnf"),
                "official_status": o.get("status"),
                "official_winner": o.get("winner"),
                "official_position": o.get("position")})

    # schema by season: key census on one race per season
    schema = {}
    for season in ("2018", "2019", "2020", "2021", "2022", "2023", "2024"):
        from collections import Counter  # noqa: E402
        rid = sorted(t for t in transitions_all if t.startswith(season))[0]
        rec = next(r for r in manifest["records"] if r["race_id"] == rid)
        if rec["retrieval_status"] == "local_cache":
            raw = cached[rec["source_locator"]]
        else:
            raw = (RAW_DIR / season / f"{rid}.jsonStream").read_text(
                encoding="utf-8-sig")
        key_use: Counter = Counter()
        for raw_line in raw.splitlines()[:4000]:
            line = raw_line.strip().lstrip("\ufeff")
            if len(line) < 13:
                continue
            try:
                import json as _j  # noqa: E402
                m = _j.loads(line[12:])
            except Exception:  # noqa: BLE001
                continue
            if isinstance(m, dict) and isinstance(m.get("Lines"), dict):
                for entry in m["Lines"].values():
                    if isinstance(entry, dict):
                        for k in entry:
                            key_use[k] += 1
        schema[season] = {"sample_race": rid,
                          "top_keys": dict(key_use.most_common(40))}
    json.dump({"schema_version": "v3.2j-schema-by-season-v1",
               "seasons": schema},
              open(OUT / "schema_by_season.json", "w"),
              indent=2, sort_keys=True)

    for s in by_season.values():
        import statistics  # noqa: E402
        ds = s.pop("drivers_seen_per_race")
        s["drivers_seen_median"] = statistics.median(ds)
        s["drivers_seen_min"] = min(ds)
        s["drivers_seen_max"] = max(ds)
    json.dump({"schema_version": "v3.2j-retired-transitions-v1",
               "sequences": transitions_all},
              open(OUT / "retired_transitions.json", "w"),
              indent=2, sort_keys=True)
    json.dump({"schema_version": "v3.2j-retired-clearings-v1",
               "n_clearings": len(clearings),
               "clearings": sorted(
                   clearings, key=lambda c: (c["race_id"], c["driver"]))},
              open(OUT / "retired_clearings.json", "w"),
              indent=2, sort_keys=True)

    gaps = sorted(c["gap_s"] for c in clock_rows if c["gap_s"] is not None)

    def q(v, x):
        return v[int(x * (len(v) - 1))] if v else None

    json.dump({"schema_version": "v3.2j-clock-alignment-v1",
               "rule": "feed session clock shares the live-timing session "
                       "origin with D9 state_time_s; query is latest delta "
                       "timestamp <= T (exact equality counts); no "
                       "nearest-future lookup",
               "conversion": "HH:MM:SS.mmm prefix -> h*3600+m*60+s.sss",
               "n_timelines": len(clock_rows),
               "gap_first_retired_minus_last_lap_s": {
                   "n": len(gaps), "min": min(gaps) if gaps else None,
                   "p50": q(gaps, 0.5), "p90": q(gaps, 0.9),
                   "max": max(gaps) if gaps else None,
                   "negative": sum(1 for g in gaps if g < 0)},
               "timelines": sorted(
                   clock_rows, key=lambda t: (t["race_id"], t["driver"]))},
              open(OUT / "clock_alignment.json", "w"),
              indent=2, sort_keys=True)

    # label join: diagnostics ONLY (never feeds runtime)
    tp = sum(1 for r in label_rows if r["n_true"] and r["official_dnf"])
    fp = sum(1 for r in label_rows if r["n_true"] and not r["official_dnf"])
    fn_drivers = set()
    for rec in sorted(manifest["records"], key=lambda r: r["race_id"]):
        off = official(rec["race_id"], rec["season"])
        seq = transitions_all[rec["race_id"]]
        for did, o in off.items():
            if o["dnf"] and not any(v for _, v in seq.get(did, [])):
                fn_drivers.add((rec["race_id"], did))
    json.dump({"schema_version": "v3.2j-label-diagnostics-v1",
               "note": "diagnostic-only; runtime never reads final labels",
               "drivers_with_retired_true": len(label_rows),
               "precision_like_tp": tp, "classified_with_retired_fp": fp,
               "dnf_without_retired_fn": len(fn_drivers),
               "rows": sorted(label_rows,
                              key=lambda r: (r["race_id"], r["driver"]))},
              open(OUT / "label_diagnostics.json", "w"),
              indent=2, sort_keys=True)

    corpus_id = {
        "schema_version": "v3.2j-status-corpus-identity-v1",
        "preregistration_sha256": prereg_hash,
        "adapter_version": DS.RAW_ADAPTER_VERSION,
        "status_contract_version": DS.STATUS_CONTRACT_VERSION,
        "n_races": len(corpus_hashes),
        "n_2025_races": 0,
        "per_race_content_hash": dict(sorted(corpus_hashes.items())),
        "corpus_hash": hashlib.sha256(json.dumps(
            dict(sorted(corpus_hashes.items())),
            sort_keys=True).encode()).hexdigest(),
    }
    json.dump(corpus_id, open(OUT / "status_corpus_identity.json", "w"),
              indent=2, sort_keys=True)
    print(f"races={len(corpus_hashes)} clearings={len(clearings)} "
          f"gap_min={min(gaps) if gaps else None} "
          f"gap_neg={sum(1 for g in gaps if g < 0)} "
          f"label tp={tp} fp={fp} fn={len(fn_drivers)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
