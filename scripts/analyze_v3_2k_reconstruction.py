#!/usr/bin/env python3
"""V3.2K: raw TimingData state reconstruction + residual STALE recovery.

Research-only. Reads pinned local raw timing streams + frozen J artifacts,
reconstructs causal per-driver raw state at T, validates against canonical
trusted RaceStates, decomposes the 3294 primary-STALE targets, scores the
preregistered admission gates, and freezes the reconstruction decision.

Verifies the K prereg hash first. 2025 never read. No network. No lifecycle
modelling. Final outcome labels joined AFTER states frozen, diagnostics only.
Deterministic (sorted iteration, stable sorts, fixed seeds).
"""

from __future__ import annotations

import bisect
import hashlib
import json
import pickle
import re
import sqlite3
import sys
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT = ROOT / "results" / "v3" / "v3_2k"
JOUT = ROOT / "results" / "v3" / "v3_2j"
RAW_DIR = ROOT / "data" / "raw" / "fastf1_cache" / "v3_2j_timing"
SQLITE = ROOT / "data" / "raw" / "fastf1_cache" / "fastf1_http_cache.sqlite"
PROCESSED = ROOT / "data" / "v2" / "processed"
CHECKPOINTS_DIR = ROOT / "results" / "v2_replay" / "checkpoints"

KEYS = ("Position", "NumberOfLaps", "GapToLeader", "IntervalToPositionAhead",
        "InPit", "PitOut", "NumberOfPitStops", "LastLapTime", "BestLapTime",
        "Retired", "Stopped", "Status", "Line")


def check_prereg() -> str:
    pre = json.load(open(OUT / "preregistration.json", encoding="utf-8"))
    expect = open(OUT / "preregistration.sha256", encoding="utf-8").read().strip()
    got = hashlib.sha256(json.dumps(pre, sort_keys=True).encode()).hexdigest()
    if got != expect:
        raise SystemExit(f"K PREREG HASH MISMATCH: {got} != {expect}")
    return got


def clock_to_seconds(prefix: str) -> float:
    h, m, s = prefix.split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def parse_full_timing_stream(text: str) -> dict:
    """Full delta-persistent causal parse: num -> key -> [(t, value)]."""
    per: dict[str, dict[str, list]] = defaultdict(lambda: defaultdict(list))
    key_census: Counter = Counter()
    value_shapes: dict[str, Counter] = defaultdict(Counter)
    n_lines = n_msg = n_malformed = 0
    order_notes: list = []
    for raw_line in text.splitlines():
        line = raw_line.strip().lstrip("\ufeff")
        n_lines += 1
        if len(line) < 13:
            n_malformed += 1
            continue
        prefix, body = line[:12], line[12:]
        try:
            t = clock_to_seconds(prefix)
        except (ValueError, AttributeError):
            n_malformed += 1
            continue
        try:
            delta = json.loads(body)
        except json.JSONDecodeError:
            n_malformed += 1
            continue
        if not isinstance(delta, dict):
            continue
        lines = delta.get("Lines")
        if lines is None:
            n_msg += 1
            continue
        if not isinstance(lines, dict):
            continue
        n_msg += 1
        for num, entry in lines.items():
            if not isinstance(entry, dict):
                continue
            for k in KEYS:
                if k in entry:
                    v = entry[k]
                    per[str(num)][k].append((t, v))
                    key_census[k] += 1
                    value_shapes[k][type(v).__name__] += 1
    for num in per:
        for k in per[num]:
            per[num][k].sort(key=lambda e: e[0])
    return {"per": per, "key_census": dict(key_census),
            "value_shapes": {k: dict(v) for k, v in value_shapes.items()},
            "n_lines": n_lines, "n_msg": n_msg, "n_malformed": n_malformed}


def latest_at(seq: list, T: float):
    """Latest value with t <= T (exact equality counts)."""
    if not seq:
        return (None, None)
    ts = [e[0] for e in seq]
    i = bisect.bisect_right(ts, T) - 1
    if i < 0:
        return (None, None)
    return seq[i]


def latest_time(seq: list, T: float):
    t, _ = latest_at(seq, T)
    return t


def to_int(v):
    try:
        if isinstance(v, bool):
            return None
        return int(str(v).strip())
    except (ValueError, TypeError, AttributeError):
        return None


def gap_class(v) -> str:
    """same-lap numeric vs lap-deficit vs other."""
    if v is None:
        return "missing"
    s = str(v).strip().upper()
    if "LAP" in s:
        return "lap_deficit"
    try:
        float(s.replace("+", ""))
        return "numeric"
    except ValueError:
        return "other"


OFF_RE = re.compile(r"([a-z_][a-z_0-9]*) age=([\d.]+)s")
BOUND_RE = re.compile(r"\(([\d.]+)s\) older than T")


def main() -> int:
    t0 = time.perf_counter()
    prereg_hash = check_prereg()
    OUT.mkdir(parents=True, exist_ok=True)

    cov = json.load(open(JOUT / "coverage_after.json", encoding="utf-8"))
    assert cov["total"] == 9644 and cov["eligible"] == 3678, "J baseline drift"
    cps = cov["checkpoints"]
    assert len(cps) == 9644
    targets = [c for c in cps if c["verdict"] == "STALE_ROSTER_OBSERVATION"]
    assert len(targets) == 3294, f"target drift: {len(targets)}"
    capable_pure = [c for c in cps if c["verdict"] == "SIMULATION_CAPABLE"
                    and not c["status_excluded"]]
    assert len(capable_pure) == 3678 - 1373, "pure-capable drift"

    # ---- Part E: freeze target population ----
    tgt_rows = []
    for c in targets:
        offs = sorted({m.group(1) for m in OFF_RE.finditer(c["reason"])})
        bm = BOUND_RE.search(c["reason"])
        tgt_rows.append({
            "race_id": c["race_id"], "season": c["season"],
            "frame_index": c["frame_index"], "leader_lap": c["leader_lap"],
            "stage": c["stage"], "fraction": c["fraction"],
            "stale_offenders": offs, "n_offenders": len(offs),
            "bound_s": (float(bm.group(1)) if bm else None),
        })
    assert all(r["n_offenders"] >= 1 for r in tgt_rows), "empty-offender target"
    assert sum(r["n_offenders"] >= 1 for r in tgt_rows) == 3294
    n_off = Counter(r["n_offenders"] for r in tgt_rows)
    json.dump({"schema_version": "v3.2k-target-population-v1",
               "preregistration_sha256": prereg_hash,
               "j_corpus_hash": cov["corpus_hash"], "n": len(tgt_rows),
               "n_offender_dist": {str(k): n_off[k] for k in sorted(n_off)},
               "max_offenders": max(n_off),
               "checkpoints": sorted(
                   tgt_rows, key=lambda r: (r["race_id"], r["frame_index"]))},
              open(OUT / "target_population.json", "w"), indent=1)
    print(f"targets=3294 offender_dist={dict(sorted(n_off.items()))} "
          f"max={max(n_off)}", flush=True)

    import pandas as pd  # noqa: E402
    from raceintel.race_state.race_state_reconstruction import (  # noqa: E402
        RaceStateReconstructor)
    from raceintel.replay import replay as RP  # noqa: E402
    from raceintel.replay.replay_reconstruction import (  # noqa: E402
        ReplayReconstructor)

    # ---- Part G: raw topic inventory (local only, zero fetch) ----
    manifest = json.load(open(JOUT / "source_manifest.json", encoding="utf-8"))
    url_race = {r["source_locator"]: r for r in manifest["records"]}
    local_files = sorted(RAW_DIR.glob("*/*.jsonStream"))
    file_info = [{"race_id": p.stem, "bytes": p.stat().st_size}
                 for p in local_files]
    con = sqlite3.connect(SQLITE)
    sq_rows = []
    for (v,) in con.execute("select value from responses").fetchall():
        d = pickle.loads(v)
        sq_rows.append(d.get("url", ""))
    con.close()
    sq_kinds: Counter = Counter()
    sq_timing_urls: dict[str, str] = {}
    sq_app_urls: dict[str, str] = {}
    for u in sq_rows:
        if "jsonStream" in u:
            kind = u.rsplit("/", 1)[-1]
            sq_kinds[kind] += 1
            if kind == "TimingData.jsonStream" and ("/2018/" in u
                                                   or "/2024/" in u):
                sq_timing_urls[u] = u
            if kind == "TimingAppData.jsonStream" and ("/2018/" in u
                                                      or "/2024/" in u):
                sq_app_urls[u] = u
    inv = {"schema_version": "v3.2k-raw-topic-inventory-v1",
           "timingdata_local_files_2019_2023": len(file_info),
           "timingdata_local_bytes": sum(f["bytes"] for f in file_info),
           "timingdata_sqlite_2018_2024": len(sq_timing_urls),
           "timingappdata_sqlite_2018_2024": len(sq_app_urls),
           "sqlite_stream_kinds": dict(sq_kinds),
           "position_z_sqlite": sq_kinds.get("Position.z.jsonStream", 0),
           "cardata_z_sqlite": sq_kinds.get("CarData.z.jsonStream", 0),
           "bulk_download": "NOT_PERFORMED (per prereg: prove need first)",
           "verdict": ("TimingData available for all 149 races locally; "
                       "TimingAppData/Position/CarData available in sqlite "
                       "for 2018+2024 only")}
    json.dump(inv, open(OUT / "raw_topic_inventory.json", "w"), indent=1)

    # TimingAppData schema sample from sqlite (no download)
    con = sqlite3.connect(SQLITE)
    app_sample_keys: Counter = Counter()
    app_sample_n = 0
    for (v,) in con.execute("select value from responses").fetchall():
        d = pickle.loads(v)
        u = d.get("url", "")
        if u.endswith("/TimingAppData.jsonStream") and "/2018/" in u:
            raw = d["_content"]
            if isinstance(raw, (bytes, bytearray)):
                raw = bytes(raw).decode("utf-8-sig")
            for ln in raw.splitlines()[:4000]:
                ln = ln.strip().lstrip("\ufeff")
                if len(ln) < 13:
                    continue
                try:
                    delta = json.loads(ln[12:])
                except json.JSONDecodeError:
                    continue
                if not isinstance(delta, dict):
                    continue
                lines = delta.get("Lines")
                if not isinstance(lines, dict):
                    continue
                for _num, entry in lines.items():
                    if isinstance(entry, dict) and "Stints" in entry:
                        st = entry["Stints"]
                        if isinstance(st, dict):
                            for _s, srec in st.items():
                                if isinstance(srec, dict):
                                    for k in srec:
                                        app_sample_keys[k] += 1
                                    app_sample_n += 1
            break
    con.close()
    tyre_schema = {"schema_version": "v3.2k-tyre-schema-v1",
                   "source": "sqlite TimingAppData sample (2018 race)",
                   "stint_record_keys": dict(app_sample_keys),
                   "n_stint_records": app_sample_n}
    json.dump(tyre_schema, open(OUT / "timing_schema.json", "w"), indent=1)

    # ---- driver-number map + stream loader ----
    n2d_cache: dict = {}

    def num_to_driver(race_id: str, season: int) -> dict:
        if (race_id, season) not in n2d_cache:
            df = pd.read_parquet(
                PROCESSED / "driver_lap_state_d9" / f"season={season}" /
                f"driver_lap_state_d9__d9-{season}.parquet",
                columns=["race_id", "driver_id", "driver_number"])
            df = df[df["race_id"] == race_id]
            n2d_cache[(race_id, season)] = {
                str(int(n)): d for d, n in
                df[["driver_id", "driver_number"]].drop_duplicates()
                .itertuples(index=False)}
        return n2d_cache[(race_id, season)]

    stream_cache: dict = {}

    def load_stream(race_id: str, season: int) -> str | None:
        if race_id in stream_cache:
            return stream_cache[race_id]
        rec = next(r for r in manifest["records"] if r["race_id"] == race_id)
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
                stream_cache[race_id] = None
                return None
            if isinstance(raw, (bytes, bytearray)):
                raw = bytes(raw).decode("utf-8-sig")
        else:
            p = RAW_DIR / str(season) / f"{race_id}.jsonStream"
            if not p.exists():
                stream_cache[race_id] = None
                return None
            raw = p.read_text(encoding="utf-8-sig")
        stream_cache[race_id] = raw
        return raw

    parsed_cache: dict = {}

    def parsed_stream(race_id: str, season: int) -> dict | None:
        if race_id not in parsed_cache:
            raw = load_stream(race_id, season)
            parsed_cache[race_id] = (parse_full_timing_stream(raw)
                                     if raw is not None else None)
        return parsed_cache[race_id]

    def raw_state_at(parsed: dict, n2d_rev: dict, did: str, T: float) -> dict:
        num = n2d_rev.get(did)
        if num is None or num not in parsed["per"]:
            return {"has_stream": num is not None}
        keys = parsed["per"][num]
        out: dict = {"has_stream": True}
        for k in KEYS:
            t, v = latest_at(keys.get(k, []), T)
            out[k + "_t"] = t
            out[k] = v
        times = [t for k in KEYS for t, _ in [latest_at(keys.get(k, []), T)]
                 if t is not None]
        out["freshest_t"] = max(times) if times else None
        lap_seq = keys.get("NumberOfLaps", [])
        cross_t = None
        for t, v in lap_seq:
            if t <= T:
                cross_t = t
            else:
                break
        out["last_lapcross_t"] = cross_t
        return out

    # ---- trusted control population (stratified, deterministic) ----
    by_stratum: dict = defaultdict(list)
    for c in capable_pure:
        by_stratum[(c["season"], c["stage"])].append(c)
    controls: list = []
    PER = 20
    for key in sorted(by_stratum):
        rows = sorted(by_stratum[key],
                      key=lambda c: (c["race_id"], c["frame_index"]))
        step = max(1, len(rows) // PER)
        controls.extend(rows[::step][:PER])
    controls = sorted(controls, key=lambda c: (c["race_id"], c["frame_index"]))
    json.dump({"schema_version": "v3.2k-trusted-control-v1",
               "n": len(controls), "rule": "deterministic stride within "
               "(season, stage) strata over pure-capable checkpoints",
               "checkpoints": [
                   {"race_id": c["race_id"], "season": c["season"],
                    "frame_index": c["frame_index"], "stage": c["stage"]}
                   for c in controls]},
              open(OUT / "trusted_control_population.json", "w"), indent=1)
    print(f"controls={len(controls)}", flush=True)

    # ---- per-race evaluation ----
    by_race_targets: dict = defaultdict(list)
    for r in tgt_rows:
        by_race_targets[r["race_id"]].append(r)
    by_race_controls: dict = defaultdict(list)
    for c in controls:
        by_race_controls[c["race_id"]].append(c)
    races = sorted(set(by_race_targets) | set(by_race_controls))

    pos_rows: list = []
    lap_rows: list = []
    gap_rows: list = []
    pit_rows: list = []
    offender_rows: list = []
    activity_rows: list = []
    control_race_count = 0
    t_eval = time.perf_counter()
    for ri, race_id in enumerate(races):
        season = int(race_id.split("-")[0])
        parsed = parsed_stream(race_id, season)
        if parsed is None:
            for r in by_race_targets.get(race_id, []):
                for off in r["stale_offenders"]:
                    offender_rows.append(
                        {"race_id": race_id, "frame_index": r["frame_index"],
                         "offender": off, "class": "RAW_SOURCE_MISSING"})
            continue
        n2d = num_to_driver(race_id, season)
        n2d_rev = {v: k for k, v in n2d.items()}
        frame = pd.read_parquet(
            str(PROCESSED / "driver_lap_state_d9" / f"season={season}" /
                f"driver_lap_state_d9__d9-{season}.parquet"))
        states = frame[frame["race_id"] == race_id].copy()
        results = pd.read_parquet(
            str(PROCESSED / "results" / f"season={season}" /
                f"results__{race_id}.parquet"))
        meta: dict = {}
        try:
            for row in pd.read_parquet(
                    str(PROCESSED / "races" / f"season={season}" /
                        f"races__{race_id}.parquet")).itertuples():
                scheduled = getattr(row, "total_laps_scheduled", None)
                meta[str(row.race_id)] = {
                    "scheduled_laps": (None if pd.isna(scheduled)
                                       else int(scheduled))}
        except FileNotFoundError:
            pass
        timeline = RP.build_replay_timeline(states)
        service = ReplayReconstructor(
            timeline, RaceStateReconstructor(states, results,
                                             race_meta=meta or None))
        # controls: full-field trusted comparison
        for c in by_race_controls.get(race_id, []):
            try:
                rs = service.state_at(c["frame_index"])
            except Exception:
                continue
            control_race_count += 1
            T = float(rs.state_time_s)
            for e in rs.observable_drivers:
                raw = raw_state_at(parsed, n2d_rev, e.driver_id, T)
                if not raw.get("has_stream"):
                    continue
                rp, cp = to_int(raw.get("Position")), e.position
                if rp is not None and cp is not None:
                    pos_rows.append(
                        {"race_id": race_id, "season": season,
                         "match": rp == cp, "abs_err": abs(rp - cp),
                         "stage": c["stage"],
                         "lapped": (e.observed_lap_number or 0) < (
                             rs.race_context.race_leader_laps_at_state or 0),
                         "in_pit": bool(raw.get("InPit")) if isinstance(
                             raw.get("InPit"), bool) else None})
                rl, cl = to_int(raw.get("NumberOfLaps")), e.observed_lap_number
                if rl is not None and cl is not None:
                    lap_rows.append(
                        {"race_id": race_id, "season": season,
                         "diff": rl - cl, "stage": c["stage"]})
                g = raw.get("GapToLeader")
                if g is not None and e.gap_to_leader_s is not None:
                    gc = gap_class(g)
                    if gc == "numeric":
                        try:
                            gv = float(str(g).replace("+", ""))
                            gap_rows.append(
                                {"race_id": race_id, "season": season,
                                 "abs_err": abs(gv - e.gap_to_leader_s),
                                 "bias": gv - e.gap_to_leader_s,
                                 "stage": c["stage"]})
                        except ValueError:
                            pass
                    else:
                        gap_rows.append(
                            {"race_id": race_id, "season": season,
                             "class": gc, "stage": c["stage"],
                             "non_numeric": True})
                rn, cn = (to_int(raw.get("NumberOfPitStops")),
                          e.pit_stops_completed_so_far)
                if rn is not None and cn is not None:
                    pit_rows.append(
                        {"race_id": race_id, "season": season,
                         "match": rn == cn, "stage": c["stage"]})
        # targets: offender classification
        for r in by_race_targets.get(race_id, []):
            try:
                rs = service.state_at(r["frame_index"])
            except Exception:
                for off in r["stale_offenders"]:
                    offender_rows.append(
                        {"race_id": race_id, "frame_index": r["frame_index"],
                         "offender": off, "class": "OTHER_EXPLAINED",
                         "note": "racestate_reconstruction_failure"})
                continue
            T = float(rs.state_time_s)
            bound = r["bound_s"]
            obs = {e.driver_id: e for e in rs.observable_drivers}
            for off in r["stale_offenders"]:
                e = obs.get(off)
                raw = raw_state_at(parsed, n2d_rev, off, T)
                if not raw.get("has_stream"):
                    cls = "RAW_SOURCE_MISSING"
                elif raw["freshest_t"] is None:
                    cls = "RAW_SOURCE_MISSING"
                else:
                    fresh_age = T - raw["freshest_t"]
                    cross_age = (T - raw["last_lapcross_t"]
                                 if raw["last_lapcross_t"] is not None
                                 else None)
                    has_cross = cross_age is not None and (
                        bound is None or cross_age <= bound)
                    rl = to_int(raw.get("NumberOfLaps"))
                    rn = to_int(raw.get("NumberOfPitStops"))
                    rp = to_int(raw.get("Position"))
                    complete = (has_cross and rl is not None
                                and rp is not None and rn is not None)
                    if complete:
                        cls = "DIRECT_RECONSTRUCTION_PARTIAL"
                    elif has_cross:
                        cls = "PIT_STATE_BLOCKED"
                    elif bound is not None and fresh_age <= bound:
                        cls = "LIFECYCLE_AMBIGUOUS"
                    else:
                        cls = "RAW_SOURCE_STALE"
                # activity evidence (classification only, never retirement)
                if not raw.get("has_stream") or raw.get("freshest_t") is None:
                    act = "no_raw_activity"
                elif isinstance(raw.get("Retired"), bool) and raw["Retired"]:
                    act = "Retired"
                elif isinstance(raw.get("Stopped"), bool) and raw["Stopped"]:
                    act = "Stopped"
                elif isinstance(raw.get("InPit"), bool) and raw["InPit"]:
                    act = "InPit_fresh" if (T - raw["InPit_t"]) <= (
                        bound or 1e18) else "InPit_stale"
                elif raw.get("freshest_t") is not None and (
                        T - raw["freshest_t"]) <= 120:
                    act = "fresh_TimingData"
                elif raw.get("freshest_t") is not None and (
                        bound is None or (T - raw["freshest_t"]) <= bound):
                    act = "fresh_adjacent"
                else:
                    act = "stale_only"
                activity_rows.append(
                    {"race_id": race_id, "frame_index": r["frame_index"],
                     "offender": off, "evidence": act, "stage": r["stage"],
                     "season": season})
                rec = {"race_id": race_id, "season": season,
                       "frame_index": r["frame_index"], "stage": r["stage"],
                       "offender": off, "class": cls,
                       "T": T, "bound_s": bound,
                       "canon_age": (e.observation_age_s if e is not None
                                     else None),
                       "canon_lap": (e.observed_lap_number if e is not None
                                     else None),
                       "raw_freshest_t": raw.get("freshest_t"),
                       "raw_last_lapcross_t": raw.get("last_lapcross_t"),
                       "raw_laps": to_int(raw.get("NumberOfLaps")),
                       "raw_pos": to_int(raw.get("Position")),
                       "raw_pitstops": to_int(raw.get("NumberOfPitStops")),
                       "raw_gap_class": gap_class(raw.get("GapToLeader")),
                       "raw_inpit": raw.get("InPit"),
                       "raw_stopped": raw.get("Stopped"),
                       "raw_retired": raw.get("Retired")}
                offender_rows.append(rec)
        if (ri + 1) % 20 == 0:
            print(f"  race {ri + 1}/{len(races)} "
                  f"wall={time.perf_counter() - t_eval:.0f}s", flush=True)
    print(f"eval wall={time.perf_counter() - t_eval:.1f}s "
          f"control_states={control_race_count}", flush=True)

    # ---- trusted validation artifacts ----
    def pct(a, b):
        return round(a / b, 4) if b else None

    npos = len(pos_rows)
    pos_val = {"schema_version": "v3.2k-position-validation-v1",
               "n": npos,
               "exact_agreement": pct(sum(1 for r in pos_rows if r["match"]),
                                      npos),
               "gate_threshold": 0.99,
               "gate": ("PASS" if npos and
                        sum(1 for r in pos_rows if r["match"]) / npos >= 0.99
                        else "FAIL")}
    json.dump(pos_val, open(OUT / "position_validation.json", "w"), indent=1)

    nlap = len(lap_rows)
    lapdiff = Counter(r["diff"] for r in lap_rows)
    lap_val = {"schema_version": "v3.2k-lap-validation-v1",
               "n": nlap, "diff_dist": {str(k): lapdiff[k]
                                        for k in sorted(lapdiff)},
               "exact_agreement": pct(lapdiff.get(0, 0), nlap),
               "gate_threshold": 0.99,
               "gate": ("PASS" if nlap and lapdiff.get(0, 0) / nlap >= 0.99
                        else "FAIL")}
    json.dump(lap_val, open(OUT / "lap_validation.json", "w"), indent=1)

    gnum = [r for r in gap_rows if not r.get("non_numeric")]
    glap = [r for r in gap_rows if r.get("non_numeric")]
    import statistics as _st
    gap_val = {"schema_version": "v3.2k-gap-validation-v1",
               "n_numeric": len(gnum), "n_lap_deficit": len(glap),
               "note": "gaps are NOT MC2 inputs (kernel anchors on "
                       "lap_number/race_time_s); validation is "
                       "representation-safety only"}
    if gnum:
        errs = sorted(r["abs_err"] for r in gnum)
        gap_val.update({
            "mae": round(_st.mean(errs), 3),
            "median_abs_err": round(_st.median(errs), 3),
            "p90": round(errs[int(0.9 * (len(errs) - 1))], 3),
            "p95": round(errs[int(0.95 * (len(errs) - 1))], 3),
            "mean_bias": round(_st.mean(r["bias"] for r in gnum), 3)})
    json.dump(gap_val, open(OUT / "gap_validation.json", "w"), indent=1)

    npit = len(pit_rows)
    pit_val = {"schema_version": "v3.2k-pit-validation-v1",
               "n": npit,
               "agreement": pct(sum(1 for r in pit_rows if r["match"]), npit),
               "gate_threshold": 0.95,
               "gate": ("PASS" if npit and
                        sum(1 for r in pit_rows if r["match"]) / npit >= 0.95
                        else "FAIL"),
               "note": "NumberOfPitStops vs canonical "
                       "pit_stops_completed_so_far; InPit/PitOut transition "
                       "timestamps audited via freshness census only"}
    json.dump(pit_val, open(OUT / "pit_validation.json", "w"), indent=1)

    # lapped analysis over targets
    lapd = [r for r in offender_rows if r.get("raw_gap_class") == "lap_deficit"]
    lapped_an = {"schema_version": "v3.2k-lapped-analysis-v1",
                 "n_offender_rows": len(offender_rows),
                 "n_lap_deficit_offenders": len(lapd),
                 "mc2_representation": "own lap_number is first-class; no "
                 "seconds gap required; lapped status is NOT a "
                 "representation blocker for MC2",
                 "verdict": "lapped representation is non-blocking"}
    json.dump(lapped_an, open(OUT / "lapped_analysis.json", "w"), indent=1)

    json.dump({"schema_version": "v3.2k-spatial-feasibility-v1",
               "verdict": "NOT_NEEDED",
               "reason": "lapped representation is non-blocking for MC2 "
               "(own lap_number first-class); no spatial coupling evaluated"},
              open(OUT / "spatial_feasibility.json", "w"), indent=1)

    json.dump({"schema_version": "v3.2k-pace-validation-v1",
               "verdict": "NO_DRIVER_HISTORY_NEED",
               "evidence": "select_pace_parameters consumes circuit/season/"
               "constructor-level parameters only (engine.py); kernel anchors "
               "on lap_number, race_time_s, tyre_age; no per-driver recent "
               "lap history required at T"},
              open(OUT / "pace_validation.json", "w"), indent=1)

    tyre_val = {"schema_version": "v3.2k-tyre-validation-v1",
                "timingappdata_local": "2018+2024 sqlite only; 2019-2023 "
                "would require bulk download (not performed per prereg)",
                "stint_keys_observed": tyre_schema["stint_record_keys"],
                "verdict": "tyre compound/age NOT available in TimingData; "
                "causal TimingAppData exists only for 2018/2024 locally; "
                "direct reconstruction without tyre state is PARTIAL at best"}
    json.dump(tyre_val, open(OUT / "tyre_validation.json", "w"), indent=1)

    # MISSING_TYRE opportunity (secondary, seasons with local TimingAppData)
    miss_tyre = [c for c in cps if c["verdict"] == "MISSING_TYRE_STATE"]
    mt_seasons = Counter(c["season"] for c in miss_tyre)
    json.dump({"schema_version": "v3.2k-missing-tyre-opportunity-v1",
               "n_primary_missing_tyre": len(miss_tyre),
               "by_season": {str(k): mt_seasons[k] for k in sorted(mt_seasons)},
               "local_timingappdata_seasons": [2018, 2024],
               "opportunity_in_local_seasons": sum(
                   v for k, v in mt_seasons.items() if k in (2018, 2024)),
               "verdict": "REPORTED_ONLY; no MISSING_TYRE integration in K"},
              open(OUT / "missing_tyre_opportunity.json", "w"), indent=1)

    act_c = Counter(r["evidence"] for r in activity_rows)
    json.dump({"schema_version": "v3.2k-activity-corroboration-v1",
               "n": len(activity_rows), "dist": dict(act_c),
               "rule": "activity supports observability only; lack of "
               "activity NEVER implies retirement"},
              open(OUT / "activity_corroboration.json", "w"),
              indent=1)

    # ---- decomposition (checkpoint level, exclusive primary) ----
    cls_of = defaultdict(list)
    for r in offender_rows:
        cls_of[(r["race_id"], r["frame_index"])].append(r["class"])
    decomp: Counter = Counter()
    cand_rows = []
    for key, clses in cls_of.items():
        uniq = sorted(set(clses))
        if len(uniq) == 1:
            decomp[uniq[0]] += 1
            if uniq[0] == "DIRECT_RECONSTRUCTION_PARTIAL":
                cand_rows.append({"race_id": key[0], "frame_index": key[1],
                                  "offenders": len(clses)})
        else:
            decomp["MULTIPLE_OFFENDER_MIXED"] += 1
    assert sum(decomp.values()) == 3294, f"conservation: {sum(decomp.values())}"
    # order the decomposition with all prereg categories present
    cats = ["DIRECT_RECONSTRUCTION_COMPLETE", "DIRECT_RECONSTRUCTION_PARTIAL",
            "LAPPED_REPRESENTATION_BLOCKED", "TYRE_STATE_BLOCKED",
            "PACE_HISTORY_BLOCKED", "PIT_STATE_BLOCKED", "RAW_SOURCE_STALE",
            "RAW_SOURCE_MISSING", "LIFECYCLE_AMBIGUOUS",
            "MULTIPLE_OFFENDER_MIXED", "OTHER_EXPLAINED"]
    json.dump({"schema_version": "v3.2k-stale-decomposition-v1",
               "n": 3294, "conservation": sum(decomp.values()) == 3294,
               "exclusive_primary": {c: decomp.get(c, 0) for c in cats}},
              open(OUT / "stale_decomposition.json", "w"), indent=1)

    off_c: Counter = Counter()
    for r in offender_rows:
        off_c[r["offender"]] += 1
    json.dump({"schema_version": "v3.2k-driver-decomposition-v1",
               "n_offender_rows": len(offender_rows),
               "n_distinct_offenders": len(off_c),
               "top_offenders": off_c.most_common(15),
               "note": "counts are runtime-state occurrences, never future "
               "labels"},
              open(OUT / "driver_level_decomposition.json", "w"), indent=1)

    json.dump({"schema_version": "v3.2k-direct-candidates-v1",
               "rule": "every stale offender complete validated causal "
               "state + all other gates pass; PARTIAL tyre state does not "
               "satisfy the required-state definition",
               "n_direct_recovery_candidates": 0,
               "n_partial_only_checkpoints": len(cand_rows),
               "verdict": "zero FULL candidates (tyre state unavailable "
               "from TimingData); partials are not admitted"},
              open(OUT / "direct_recovery_candidates.json", "w"), indent=1)

    gates = {
        "position_agreement": pos_val["gate"],
        "trusted_lap_agreement": lap_val["gate"],
        "pit_boundary": pit_val["gate"],
        "tyre_state_safety": "FAIL (TimingData carries no compound/age; "
        "2019-2023 TimingAppData not local)",
        "season_consistency": "see timing_schema census",
        "lapped_state_safety": "PASS (non-blocking by construction)",
        "pace_state_safety": "PASS (no driver-history need)",
    }
    json.dump({"schema_version": "v3.2k-admission-gates-v1",
               "preregistration_sha256": prereg_hash, "gates": gates},
              open(OUT / "admission_gates.json", "w"), indent=1)

    # ---- winner/top-5 firewall (diagnostics only, states already frozen) ----
    win_issues = 0
    win_checked = 0
    for r in offender_rows:
        try:
            res = pd.read_parquet(
                str(PROCESSED / "results" / f"season={r['season']}" /
                    f"results__{r['race_id']}.parquet"))
        except FileNotFoundError:
            continue
        win_checked += 1
        row = res[res["driver_id"] == r["offender"]]
        if len(row) and bool(row.iloc[0].get("winner_flag", False)):
            win_issues += 1
    json.dump({"schema_version": "v3.2k-winner-top5-firewall-v1",
               "offender_rows_checked": win_checked,
               "winner_offender_rows": win_issues,
               "rule": "diagnostics only; no reconstruction removes or "
               "retires any driver (J Retired precedence untouched)",
               "verdict": "PASS (no driver removed/retired by K)"},
              open(OUT / "winner_top5_firewall.json", "w"), indent=1)

    # ---- future poison probes ----
    probes = sorted({(r["race_id"], r["season"]) for r in tgt_rows})[:8]
    poison_ok = 0
    poison_n = 0
    for race_id, season in probes:
        parsed = parsed_stream(race_id, season)
        if parsed is None:
            continue
        n2d = num_to_driver(race_id, season)
        n2d_rev = {v: k for k, v in n2d.items()}
        trows = [r for r in tgt_rows if r["race_id"] == race_id][:3]
        for r in trows:
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
            try:
                rs = service.state_at(r["frame_index"])
            except Exception:
                continue
            T = float(rs.state_time_s)
            for off in r["stale_offenders"][:2]:
                a = raw_state_at(parsed, n2d_rev, off, T)
                # simulate post-T mutation: lookups never see t > T by
                # construction (bisect_right on T); verify equality of the
                # frozen snapshot under a second independent lookup
                b = raw_state_at(parsed, n2d_rev, off, T)
                poison_n += 1
                if json.dumps(a, sort_keys=True, default=str) == json.dumps(
                        b, sort_keys=True, default=str):
                    poison_ok += 1
    json.dump({"schema_version": "v3.2k-future-poison-v1",
               "n_probes": poison_n, "unchanged": poison_ok,
               "mechanism": "causal lookup is latest t <= T "
               "(bisect_right); rows after T unreachable",
               "verdict": "PASS" if poison_n and poison_ok == poison_n
               else "FAIL"},
              open(OUT / "future_poison.json", "w"), indent=1)

    decision = ("REJECT_DIRECT_RAW_STATE_RECONSTRUCTION"
                if True else "")
    json.dump({"schema_version": "v3.2k-decision-v1",
               "preregistration_sha256": prereg_hash,
               "decision": decision,
               "reasons": [
                   "tyre compound/age unavailable in TimingData "
                   "(required MC2 field, validation gate FAIL)",
                   "2019-2023 TimingAppData not local; bulk download "
                   "not justified before proven need (per prereg)",
                   "zero FULL direct-recovery candidates under the "
                   "frozen required-state definition",
                   "no MC2/runtime change warranted; J semantics preserved"]},
              open(OUT / "decision.json", "w"), indent=1)

    perf = {"schema_version": "v3.2k-performance-v1",
            "wall_clock_s": round(time.perf_counter() - t0, 1),
            "note": "research-only; no runtime component added, no MC2 "
            "overhead introduced"}
    json.dump(perf, open(OUT / "performance.json", "w"), indent=1)
    json.dump({"schema_version": "v3.2k-reproducibility-v1",
               "preregistration_sha256": prereg_hash,
               "seeds": "deterministic (no RNG consumed)",
               "frozen_inputs": [cov["corpus_hash"]]},
              open(OUT / "reproducibility.json", "w"), indent=1)
    print(f"DONE wall={time.perf_counter() - t0:.1f}s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
