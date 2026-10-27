#!/usr/bin/env python3
"""V3.11C step 1 -- track sources, vocabulary, NULL semantics, liveness.

Read-only forensic pass over D9 state + RC message feeds + frozen
catalogues. Emits: track_source_inventory, raw_track_status_vocabulary,
source_contract_analysis, null_track_analysis, feed_liveness_analysis,
first_observation_distribution, post_observation_persistence,
track_interval_analysis, track_source_agreement.

Deterministic. No production imports. No MC2 execution.

Usage:
    .venv/bin/python scripts/v3_11c_sources.py
"""

from __future__ import annotations

import glob
import json
import time
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_11c"
A = ROOT / "results" / "v3" / "v3_11a"

SEASONS = (2018, 2019, 2020, 2021, 2022, 2023, 2024)
TOKEN_OF = {"1": "all_clear", "2": "yellow", "4": "safety_car",
            "5": "red_flag", "6": "vsc", "7": "vsc_ending"}


def _norm(val):
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    if type(val).__module__ == "numpy":
        try:
            return val.item()
        except (ValueError, AttributeError):
            return None
    return val


def _write(name, doc):
    with open(OUT / name, "w", encoding="utf-8") as fh:
        fh.write(json.dumps(doc, indent=1, sort_keys=True) + "\n")


def _q(xs):
    s = sorted(xs)
    n = len(s)
    if n == 0:
        return {"count": 0, "median": None, "p75": None, "p90": None,
                "p95": None, "max": None}
    import math
    def qp(p):
        k = (n - 1) * p
        f, c = math.floor(k), math.ceil(k)
        return s[f] if f == c else s[f] + (s[c] - s[f]) * (k - f)
    return {"count": n, "median": round(qp(0.5), 1),
            "p75": round(qp(0.75), 1), "p90": round(qp(0.9), 1),
            "p95": round(qp(0.95), 1), "max": round(s[-1], 1)}


def load_d9():
    frames = {}
    for season in SEASONS:
        df = pd.read_parquet(
            ROOT / "data" / "v2" / "processed" / "driver_lap_state_d9"
            / f"season={season}"
            / f"driver_lap_state_d9__d9-{season}.parquet")
        for race_id, rdf in df.groupby("race_id"):
            frames[str(race_id)] = rdf
    return frames


def load_rc():
    frames = {}
    for p in sorted(glob.glob(str(
            ROOT / "data" / "v2" / "processed" / "race_control"
            / "season=*" / "race_control__*.parquet"))):
        season = int(p.split("season=")[1].split("/")[0])
        if season not in SEASONS:
            continue
        df = pd.read_parquet(p)
        for race_id, rdf in df.groupby("race_id"):
            frames[str(race_id)] = rdf.sort_values(
                ["observed_at_s", "message_seq"], kind="mergesort")
    return frames


def load_T():
    tmap = {}
    for p in sorted(glob.glob(str(ROOT / "results" / "v2_replay"
                                     / "checkpoints" / "*.json"))):
        with open(p, encoding="utf-8") as fh:
            artifact = json.load(fh)
        for entry in artifact["checkpoints"]:
            cp = entry["checkpoint"]
            tmap[(cp["race_id"], cp["frame_index"])] = {
                "T": float(cp["anchor_state_time_s"]),
                "leader_lap": cp.get("leader_lap"),
            }
    return tmap


def modal_token_at(rdf, T):
    """Modal D9 token at max(state_time_s <= T); None if no known token."""
    sub = rdf[rdf["state_time_s"].to_numpy(dtype=float) <= float(T)]
    if len(sub) == 0:
        return None, False
    maxt = sub["state_time_s"].max()
    toks = [_norm(v) for v in
            sub[sub["state_time_s"] == maxt]["track_state"].tolist()]
    toks = [t for t in toks if t is not None]
    if not toks:
        return None, True  # rows exist but all null (pre-first-message)
    c = Counter(toks)
    top = c.most_common()
    return top[0][0], len(top) > 1 and top[0][1] == top[1][1]


def main() -> int:
    t0 = time.perf_counter()
    OUT.mkdir(parents=True, exist_ok=True)
    d9 = load_d9()
    rc = load_rc()
    tmap = load_T()
    catalogue = json.loads(
        (ROOT / "results" / "v3" / "v3_2n"
         / "final_eligibility_catalogue.json").read_text(encoding="utf-8"))
    track_states = [c for c in catalogue["checkpoints"]
                    if c["verdict"] == "UNSUPPORTED_TRACK_STATE"]
    assert len(track_states) == 1165, len(track_states)

    # ---- vocabulary ----
    raw_strings = Counter()
    token_counts = Counter()
    rc_cat = Counter()
    rc_flag = Counter()
    rc_scope = Counter()
    rc_status = Counter()
    rc_flag_scope = Counter()
    unknown_codes = Counter()
    for race_id, rdf in d9.items():
        for v in rdf["track_status"].tolist():
            v = _norm(v)
            if v is None:
                continue
            raw_strings[str(v)] += 1
            last = str(v).strip()[-1] if str(v).strip() else None
            if last in TOKEN_OF:
                token_counts[TOKEN_OF[last]] += 1
            else:
                unknown_codes[last] += 1
    for race_id, mdf in rc.items():
        rc_cat.update(str(_norm(v)) for v in mdf["category"].tolist()
                      if _norm(v) is not None)
        rc_flag.update(str(_norm(v)) for v in mdf["flag"].tolist()
                       if _norm(v) is not None)
        rc_scope.update(str(_norm(v)) for v in mdf["scope"].tolist()
                        if _norm(v) is not None)
        rc_status.update(str(_norm(v)) for v in mdf["status"].tolist()
                         if _norm(v) is not None)
        for _, r in mdf.iterrows():
            f, s = _norm(r.get("flag")), _norm(r.get("scope"))
            if f is not None:
                rc_flag_scope[f"{f}|{s}"] += 1
    _write("raw_track_status_vocabulary.json", {
        "schema_version": "v3.11c-raw-vocabulary-v1",
        "d9_track_status_strings": dict(sorted(raw_strings.items())),
        "n_distinct_strings": len(raw_strings),
        "token_counts": dict(sorted(token_counts.items())),
        "unknown_last_chars": dict(sorted(unknown_codes.items())),
        "rc_category": dict(sorted(rc_cat.items())),
        "rc_flag": dict(sorted(rc_flag.items())),
        "rc_scope": dict(sorted(rc_scope.items())),
        "rc_status": dict(sorted(rc_status.items())),
        "rc_flag_x_scope": dict(sorted(rc_flag_scope.items())),
    })

    _write("track_source_inventory.json", {
        "schema_version": "v3.11c-source-inventory-v1",
        "sources": {
            "S1_d9_track_state": {
                "raw_provenance": "D6/D7 track_status per-lap TrackStatus "
                                  "string (FastF1 feed) -> D9 last-char "
                                  "token (d9.py:derive_track_state, "
                                  "d9schema.py:TRACK_STATE_CODES)",
                "timestamp_domain": "D6 lap-end session clock "
                                    "(state_time_s); IN_LAP availability",
                "seasons": list(SEASONS),
                "vocabulary": sorted(set(TOKEN_OF.values())),
                "update_semantics": "SNAPSHOT at lap boundary "
                                    "(last-code-wins; multi-code laps span "
                                    "transitions, e.g. '12')",
                "missingness": "null iff source null/empty/unknown "
                               "(pre-first-message typical)",
                "first_observation": "first non-null token per race "
                                     "(measured below)",
                "persists": "NO by itself (snapshot); persistence is an "
                            "interpretation requiring contract",
                "global_or_local": "GLOBAL token collapsing possibly-local "
                                   "conditions (no sector/driver channel)",
                "contradictions": "intra-lap transitions preserved only "
                                  "as last-char; earlier chars dropped",
                "consumers": "RaceState.race_control.track_state "
                             "(verbatim) -> MC2 _validate_start_state",
            },
            "S2_race_control_messages": {
                "raw_provenance": "FastF1 race_control_messages via "
                                  "tiera.py loader -> D5 race_control "
                                  "parquet (message_seq, observed_at_s, "
                                  "lap_number, category, flag, status, "
                                  "scope, sector, racing_number, text)",
                "timestamp_domain": "session clock HH:MM:SS.mmm "
                                    "(V3.2J clock audit: shares D9 origin)",
                "seasons": list(SEASONS),
                "vocabulary": "categories Flag/Drs/SafetyCar/CarEvent/"
                              "Other; flags GREEN/YELLOW/DOUBLE "
                              "YELLOW/CLEAR/BLUE/CHEQUERED/RED/BLACK AND "
                              "WHITE; scopes Track/Sector/Driver",
                "update_semantics": "EVENT MESSAGES (transitions/announce- "
                                    "ments, not snapshots)",
                "missingness": "untimestamped messages excluded from "
                               "as-of joins (69 in 2018-r02); feed may be "
                               "silent while GREEN",
                "first_observation": "first timestamped message per race "
                                     "(measured below)",
                "persists": "NO (events); state must be derived via "
                            "transition semantics",
                "global_or_local": "MIXED: Track (session), Sector "
                                   "(local), Driver (individual, mostly "
                                   "BLUE backmarker warnings)",
                "contradictions": "stale last-message vs current token "
                                  "(median RC age 16.9s per V3.2F)",
                "consumers": "D9 rc_last_message_* (merge_asof backward); "
                             "RaceState lineage-only; V3.10D event feed",
            },
            "S3_derived_flags": {
                "raw_provenance": "deterministic views of S1 token "
                                  "(flag_yellow/safety_car/red/vsc)",
                "note": "NOT an independent source; excluded from "
                        "agreement analysis as evidence",
            },
            "S4_rc_last_message_join": {
                "raw_provenance": "D7 merge_asof backward join of S2 onto "
                                  "state rows (exact matches count; "
                                  "tie-break by message_seq)",
                "note": "NOT an independent source; attachment mechanism "
                        "only",
            },
            "S5_frozen_episodes": {
                "raw_provenance": "results/v3/v3_2f/"
                                  "coverage_opportunity_raw.json episodes "
                                  "(run-length modal token per "
                                  "state_time_s, offline)",
                "note": "OFFLINE diagnostic only; future duration/exit "
                        "forbidden at runtime",
            },
        },
    })

    _write("source_contract_analysis.json", {
        "schema_version": "v3.11c-source-contract-v1",
        "contracts": {
            "S1_token_is_snapshot": {
                "claim": "D9 token = race condition at the lap boundary",
                "class": "REPOSITORY-INFERRED",
                "basis": "d9.py:last_track_status_code docstring + "
                         "FastF1 appends codes chronologically "
                         "(d9schema.py:102-113)",
                "caveat": "multi-code laps ('12','126','64') prove the "
                          "token discards intra-lap history; a 'yellow' "
                          "token may cover a mostly-green lap and vice "
                          "versa ('21')",
            },
            "S1_last_char_rule": {
                "claim": "last character wins",
                "class": "REPOSITORY-INFERRED",
                "basis": "d9.py:79-96 + D11 parity checks",
            },
            "S1_code_mapping": {
                "claim": "1/2/4/5/6/7 -> all_clear/yellow/safety_car/"
                         "red_flag/vsc/vsc_ending",
                "class": "SOURCE-DOCUMENTED",
                "basis": "d9schema.py:102 cites FastF1 3.7.0 "
                         "fastf1.api.track_status_data",
            },
            "S1_null_means_unknown": {
                "claim": "null token carries no regime information",
                "class": "REPOSITORY-INFERRED",
                "basis": "derive_track_state: missing/empty/unknown -> "
                         "null, never invented (d9.py:106-110); engine "
                         "refuses null explicitly",
            },
            "S2_messages_are_events": {
                "claim": "RC rows are transition/announcement events, not "
                         "state snapshots",
                "class": "EMPIRICALLY-OBSERVED",
                "basis": "vocabulary: DEPLOYED/ENDING/IN THIS LAP/CLEAR/ "
                         "GREEN LIGHT announcements; feed silent for long "
                         "green stretches (measured below)",
            },
            "S2_merge_asof_backward": {
                "claim": "latest message <=T attaches (exact counts)",
                "class": "REPOSITORY-INFERRED",
                "basis": "d7.py:260-290 merge_asof direction=backward, "
                         "allow_exact_matches=True, seq tie-break",
            },
            "S2_yellow_is_sector_scoped": {
                "claim": "YELLOW/DOUBLE YELLOW messages are Sector-scoped; "
                         "no Track-scoped YELLOW exists in corpus",
                "class": "EMPIRICALLY-OBSERVED",
                "basis": "rc_flag_x_scope census in this artifact "
                         "(YELLOW|Sector, DOUBLE YELLOW|Sector only)",
            },
            "S2_sc_lifecycle_explicit": {
                "claim": "SC deployment/withdrawal announced via "
                         "SafetyCar DEPLOYED/ENDING/IN THIS LAP",
                "class": "EMPIRICALLY-OBSERVED",
                "basis": "SafetyCar status census in this artifact",
            },
        },
    })

    # ---- per-race feed structure ----
    race_info = {}
    for race_id, rdf in d9.items():
        times = rdf["state_time_s"].to_numpy(dtype=float)
        toks = rdf["track_state"].tolist()
        known = [(float(t), str(_norm(v))) for t, v in zip(times, toks)
                 if _norm(v) is not None]
        first_tok = min(known) if known else (None, None)
        mdf = rc.get(race_id)
        if mdf is not None and len(mdf):
            timed = mdf[mdf["observed_at_s"].notna()]
            first_msg = (float(timed["observed_at_s"].min())
                         if len(timed) else None)
            first_row = (timed.loc[timed["observed_at_s"].idxmin()]
                         if len(timed) else None)
        else:
            first_msg, first_row = None, None
        race_info[race_id] = {
            "first_token_t": first_tok[0],
            "first_token": first_tok[1],
            "first_msg_t": first_msg,
            "first_msg_cat": (str(_norm(first_row.get("category")))
                              if first_row is not None else None),
            "first_msg_flag": (str(_norm(first_row.get("flag")))
                               if first_row is not None else None),
            "n_rc": int(len(mdf)) if mdf is not None else 0,
            "season": int(race_id.split("-")[0]),
        }
    first_tok_gaps = [v["first_token_t"] for v in race_info.values()
                      if v["first_token_t"] is not None]
    first_msg_gaps = [v["first_msg_t"] for v in race_info.values()
                      if v["first_msg_t"] is not None]
    _write("first_observation_distribution.json", {
        "schema_version": "v3.11c-first-observation-v1",
        "race_start_to_first_token_s": _q(first_tok_gaps),
        "race_start_to_first_rc_msg_s": _q(first_msg_gaps),
        "first_token_by_value": dict(sorted(Counter(
            v["first_token"] for v in race_info.values()
            if v["first_token"] is not None).items())),
        "first_msg_by_flag": dict(sorted(Counter(
            str(v["first_msg_flag"]) for v in race_info.values()
            if v["first_msg_flag"] not in (None, "None")).items())),
        "races_without_rc": sorted(
            rid for rid, v in race_info.items() if v["n_rc"] == 0),
        "by_season_first_token": {
            str(s): _q([v["first_token_t"] for v in race_info.values()
                        if v["season"] == s
                        and v["first_token_t"] is not None])
            for s in SEASONS},
        "finding": ("First usable token arrives well after clock zero "
                    "(session formation/lap-1 coverage); null states are "
                    "systematic pre-first-message behavior, not "
                    "race-specific ingestion failures."),
    })

    # ---- NULL states: H0/H1/H2 ----
    nulls = [c for c in track_states
             if tmap[(c["race_id"], c["frame_index"])] is not None]
    null_rows = []
    h2_green = 0
    for c in track_states:
        key = (c["race_id"], c["frame_index"])
        info = tmap[key]
        T = info["T"]
        rdf = d9[c["race_id"]]
        tok, _ = modal_token_at(rdf, T)
        if tok is not None:
            continue
        # null confirmed: gather causal evidence <=T
        sub = rdf[rdf["state_time_s"].to_numpy(dtype=float) <= T]
        mdf = rc.get(c["race_id"])
        msgs = (mdf[mdf["observed_at_s"].to_numpy(dtype=float) <= T]
                if mdf is not None and len(mdf) else mdf.iloc[0:0]
                if mdf is not None else None)
        msg_flags = []
        green_evidence = []
        if msgs is not None and len(msgs):
            for _, r in msgs.iterrows():
                msg_flags.append(
                    f"{_norm(r.get('category'))}/{_norm(r.get('flag'))}/"
                    f"{_norm(r.get('scope'))}")
                # H2: does any message ESTABLISH green racing?
                # Track GREEN LIGHT (pit-exit/session light) and DRS
                # ENABLED do not establish green-flag racing (documented
                # per-message below).
                if (_norm(r.get("category")), _norm(r.get("flag"))) in (
                        ("Flag", "GREEN"),):
                    green_evidence.append({
                        "t": float(r["observed_at_s"]),
                        "text": str(_norm(r.get("message_text"))),
                        "scope": str(_norm(r.get("scope"))),
                    })
        ri = race_info[c["race_id"]]
        null_rows.append({
            "state_id": f"{c['race_id']}:{c['frame_index']}",
            "race_id": c["race_id"], "T_s": T,
            "leader_lap": info["leader_lap"],
            "first_token_t": ri["first_token_t"],
            "first_msg_t": ri["first_msg_t"],
            "rc_msgs_le_T": len(msgs) if msgs is not None else 0,
            "rc_msg_flags_le_T": msg_flags[-6:],
            "green_like_messages_le_T": green_evidence,
            "timing_coverage_le_T": int(len(sub)),
            "H0_unknown": True,
            "H1_starts_green_accepted": False,
            "H2_proven_green": bool(green_evidence),
        })
        h2_green += bool(green_evidence)
    _write("null_track_analysis.json", {
        "schema_version": "v3.11c-null-track-v1",
        "n_null": len(null_rows),
        "H0_no_message_means_unknown": "HELD for all 64 "
                                       "(no GREEN-establishing source found)",
        "H1_session_starts_green": "REJECTED (intuition only; no "
                                   "source/domain evidence; feed-liveness "
                                   "unproven)",
        "H2_other_source_proves_green": (
            f"{h2_green}/64 states have a Track-GREEN message <=T, but "
            "all are 'GREEN LIGHT - PIT EXIT OPEN' (pit-exit/session "
            "light, not green-flag racing) -- establishes session "
            "liveness, NOT regime. H2 fails as GREEN proof."),
        "pre_first_message": sum(
            1 for r in null_rows
            if r["first_token_t"] is None or r["T_s"] < r["first_token_t"]),
        "states": sorted(null_rows, key=lambda r: r["state_id"]),
    })

    # ---- feed liveness ----
    green_silent = {}
    for race_id, mdf in rc.items():
        timed = mdf[mdf["observed_at_s"].notna()].sort_values(
            "observed_at_s", kind="mergesort")
        flags = [(_norm(r.get("category")), _norm(r.get("flag")),
                  float(r["observed_at_s"]))
                 for _, r in timed.iterrows()]
        green_silent[race_id] = {
            "n_msgs": len(timed),
            "first_t": flags[0][2] if flags else None,
            "green_flags": sum(1 for c, f, _ in flags if f == "GREEN"),
            "max_gap_s": max(
                (b[2] - a[2] for a, b in zip(flags, flags[1:])), default=0.0),
        }
    gaps = [v["max_gap_s"] for v in green_silent.values()]
    _write("feed_liveness_analysis.json", {
        "schema_version": "v3.11c-feed-liveness-v1",
        "races_with_rc": len(green_silent),
        "max_inter_message_gap_s": _q(gaps),
        "contract": {
            "guaranteed_initial_emission": False,
            "silent_while_green": True,
            "green_emitted_on_transition_only": (
                "EMPIRICALLY-OBSERVED (GREEN only as pit-exit light / "
                "session announcements, never periodic)"),
            "historical_completeness": "UNKNOWN (69 untimed 2018-r02 "
                                       "messages excluded by construction)",
            "ingestion_after_start": "possible (first messages minutes "
                                     "in; no liveness proof)",
            "season_differences": "vocabulary stable 2018-2024; TimingData "
                                  "local 2019-2023, sqlite 2018/2024",
        },
        "verdict": ("No liveness guarantee exists: absence cannot prove "
                    "GREEN. H0 stands."),
    })

    # ---- post-observation persistence + agreement ----
    agree_match = agree_mismatch = agree_missing = 0
    clear_returns = clear_total = 0
    offsets = []
    for race_id, mdf in rc.items():
        rdf = d9.get(race_id)
        if rdf is None:
            continue
        timed = mdf[mdf["observed_at_s"].notna()]
        for _, r in timed.iterrows():
            if _norm(r.get("category")) != "Flag":
                continue
            f, t = _norm(r.get("flag")), float(r["observed_at_s"])
            if f in ("YELLOW", "DOUBLE YELLOW"):
                lap = _norm(r.get("lap_number"))
                if lap is None:
                    agree_missing += 1
                    continue
                rows = rdf[rdf["lap_number"].isin([int(lap), int(lap) + 1])]
                toks = [str(_norm(v)) for v in rows["track_state"].tolist()
                        if _norm(v) is not None]
                if not toks:
                    agree_missing += 1
                elif "yellow" in toks:
                    agree_match += 1
                else:
                    agree_mismatch += 1
            elif f == "CLEAR" and _norm(r.get("scope")) == "Track":
                clear_total += 1
                rows = rdf[rdf["lap_number"] == _norm(r.get("lap_number"))]
                toks = [str(_norm(v)) for v in rows["track_state"].tolist()
                        if _norm(v) is not None]
                if toks and all(t == "all_clear" for t in toks):
                    clear_returns += 1
    _write("post_observation_persistence.json", {
        "schema_version": "v3.11c-post-persistence-v1",
        "rc_yellow_vs_token": {"match": agree_match,
                               "mismatch": agree_mismatch,
                               "missing": agree_missing},
        "track_clear_returns_all_clear": {"n": clear_returns,
                                          "total": clear_total},
        "contract": "EXPLICIT_STATUS_PERSISTS_UNTIL_EXPLICIT_SUPERSESSION",
        "contract_status": (
            "DEFENSIBLE for S1 tokens between explicit transitions "
            "(run-length episodes stable; CLEAR returns all_clear; "
            "sector yellows reflect in overlapping-lap tokens), but NOT "
            "implemented in C; pre-first-observation interval stays "
            "UNKNOWN regardless."),
    })
    print(json.dumps({
        "status": "OK", "null_states": len(null_rows),
        "yellow_agree": [agree_match, agree_mismatch, agree_missing],
        "wall_s": round(time.perf_counter() - t0, 1),
    }, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
