#!/usr/bin/env python3
"""V3.2C offline at-T signal diagnostics (Parts J/K/L/N).

Measurement only. Uses future rows / final results strictly as offline
evaluation labels; nothing here enters runtime classification. Reports:

- STOPPED: precision/recall/support/FP/FN + season breakdown for the
  candidate signaled-stale rule (stopped + bound + behind>=2), and for
  STOPPED alone. Notes that RaceState carries no message text, so any
  runtime rule would need new plumbing (measured here from D9 directly).
- PIT_IN: garage-retirement hypothesis (last row pit_in among terminal
  no-signal offenders) + rule precision/recall/season stability.
- OTHER: small interpretable set (behind>=k, position-null, age buckets).
- TYRE: per null-tyre driver, last <=T known tyre + barrier analysis
  (pit/stint/compound discontinuity, never-observed, wholesale).

Output JSON on stdout (or --out). No timestamps, usernames, or paths.
"""

from __future__ import annotations

import argparse
import glob
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import pandas as pd  # noqa: E402

from audit_v3_2_simulation_coverage import (  # noqa: E402
    classify_checkpoint,
    load_race_inputs,
    season_of,
)
from raceintel.race_state.race_state_reconstruction import (  # noqa: E402
    RaceStateReconstructor,
)
from raceintel.replay import replay as RP  # noqa: E402
from raceintel.replay.replay_reconstruction import ReplayReconstructor  # noqa: E402
from raceintel.simulation.engine import (  # noqa: E402
    CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES,
    select_pace_parameters,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
CHECKPOINTS_DIR = PROJECT_ROOT / "results" / "v2_replay" / "checkpoints"

_CAR_RE = re.compile(r"CAR\s+(\d+)", re.IGNORECASE)


def _stopped_numbers(text) -> set[int]:
    if not isinstance(text, str) or "STOPPED" not in text.upper():
        return set()
    return {int(n) for n in _CAR_RE.findall(text.upper())}


def _is_null(value) -> bool:
    return value is None or (isinstance(value, float) and pd.isna(value))


def _grid_map(results: pd.DataFrame) -> dict:
    out = {}
    for row in results.itertuples():
        grid = getattr(row, "grid_position", None)
        out[str(row.driver_id)] = None if _is_null(grid) else float(grid)
    return out


def _truth(results: pd.DataFrame) -> dict:
    winner, top5 = None, set()
    for row in results.itertuples():
        pos = getattr(row, "position_final", None)
        if _is_null(pos):
            continue
        pos = int(pos)
        if pos == 1:
            winner = str(row.driver_id)
        if pos <= 5:
            top5.add(str(row.driver_id))
    return {"winner": winner, "top5": sorted(top5)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=None)
    parser.add_argument("--limit-races", type=int, default=None)
    args = parser.parse_args()

    paths = sorted(glob.glob(str(CHECKPOINTS_DIR / "*.json")))
    if args.limit_races is not None:
        paths = paths[:args.limit_races]

    offender_records = []  # one row per stale offender per checkpoint
    stopped_eval = []      # offender-level (stopped+bound+behind) eval rows
    tyre_cases = []        # one row per null-tyre driver per checkpoint
    missing_driver_cases = []
    state_summary = []

    from raceintel.simulation.params import (
        load_simulation_parameters,
        parameter_storage_dir,
    )
    parameters = load_simulation_parameters(
        parameter_storage_dir(PROJECT_ROOT, 2024))

    for path in paths:
        artifact = json.load(open(path, encoding="utf-8"))
        race_id = artifact["race_id"]
        season = season_of(race_id)
        frames = sorted(e["checkpoint"]["frame_index"]
                        for e in artifact["checkpoints"])
        states, results, meta = load_race_inputs(season, race_id)
        timeline = RP.build_replay_timeline(states)
        service = ReplayReconstructor(
            timeline, RaceStateReconstructor(states, results,
                                             race_meta=meta or None))
        grid = _grid_map(results)
        truth = _truth(results)
        num_by_driver = {}
        for _rid, group in states.groupby("driver_id"):
            nums = group["driver_number"].dropna().unique()
            if len(nums):
                num_by_driver[str(_rid)] = {int(n) for n in nums}
        num_to_driver: dict[int, str] = {}
        for did, nums in num_by_driver.items():
            for n in nums:
                num_to_driver.setdefault(n, did)
        # All distinct RC messages observable at or before each T are
        # derived from D9 rows: (message observed_at, stopped car numbers).
        msg = states[["rc_last_message_observed_at_s",
                      "rc_last_message_text"]].dropna(
            subset=["rc_last_message_text"]).drop_duplicates()
        msg_events = []  # (observed_at_s, frozenset(car numbers))
        for mrow in msg.itertuples():
            nums = _stopped_numbers(mrow.rc_last_message_text)
            if not nums:
                continue
            try:
                when = float(mrow.rc_last_message_observed_at_s)
            except (TypeError, ValueError):
                continue
            if when != when:  # NaN observed_at: not datable <= T, skip
                continue
            msg_events.append((when, frozenset(nums)))
        msg_events.sort()
        times_by_driver = {
            str(did): group.sort_values("state_time_s")["state_time_s"].to_numpy()
            for did, group in states.groupby("driver_id")
        }

        for frame_index in frames:
            verdict, _reason, _stage, _frac, _sim = classify_checkpoint(
                service.state_at, frame_index, parameters)
            state_summary.append({"race_id": race_id, "season": season,
                                  "frame_index": frame_index,
                                  "verdict": verdict})
            if verdict not in ("STALE_ROSTER_OBSERVATION",
                               "MISSING_DRIVER_OBSERVATION",
                               "MISSING_TYRE_STATE"):
                continue
            rs = service.state_at(frame_index)
            T = float(rs.state_time_s)
            leader_lap = rs.race_context.race_leader_laps_at_state
            try:
                selection = select_pace_parameters(
                    __import__("raceintel.simulation.adapter",
                               fromlist=["from_race_state"]).from_race_state(rs),
                    parameters)
                bound = (CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES
                         * float(selection.base.value))
            except Exception:
                bound = None
            # STOPPED knowledge at T: any RC STOPPED message observed
            # at or before T that names the driver's car number. Message
            # observed_at is the datable <=T evidence (offline scan; a
            # runtime rule would need this plumbing added to RaceState,
            # which today carries no message text at all).
            stopped_nums_T: set[int] = set()
            for when, nums in msg_events:
                if when <= T:
                    stopped_nums_T |= set(nums)
                else:
                    break
            stopped_drivers = {num_to_driver[n] for n in stopped_nums_T
                               if n in num_to_driver}
            # Anchor row's RC category at T (audits feed staleness by season).
            arows = states[(states["driver_id"] == rs.anchor_driver_id)
                           & (states["state_time_s"] == T)]
            rc_cat = (arows.iloc[-1].get("rc_last_message_category", None)
                      if len(arows) else None)

            if verdict == "STALE_ROSTER_OBSERVATION":
                from raceintel.simulation.adapter import from_race_state
                base_state = from_race_state(rs)
                by_id = {e.driver_id: e for e in rs.observable_drivers}
                for entry in base_state.drivers:
                    did = entry.driver_id
                    obs = by_id.get(did)
                    if obs is None:
                        continue
                    age = obs.observation_age_s
                    if bound is None or age is None \
                            or float(age) <= bound:
                        continue
                    times = times_by_driver.get(did)
                    has_later = bool(times is not None
                                     and (times > T).any())
                    _tail = states[
                        (states["driver_id"] == did)
                        & (states["state_time_s"] <= T)
                        ].sort_values("state_time_s")
                    tail = _tail.iloc[-1] if len(_tail) else None
                    behind = (None if leader_lap is None or obs.observed_lap_number is None
                              else int(leader_lap) - int(obs.observed_lap_number))
                    stopped = did in stopped_drivers
                    pit_in_last = bool(
                        tail is not None and not _is_null(tail.get("pit_in_s")))
                    pos_null = obs.position is None
                    rec = {"race_id": race_id, "season": season,
                           "frame_index": frame_index, "driver_id": did,
                           "age_s": float(age),
                           "bound_s": bound,
                           "age_x": (float(age) / bound),
                           "behind": behind,
                           "terminal": not has_later,
                           "stopped": stopped,
                           "rc_category": (None if _is_null(rc_cat)
                                           else str(rc_cat)),
                           "pit_in_last": pit_in_last,
                           "position_null": bool(pos_null),
                           "eventual_winner": truth["winner"] == did,
                           "eventual_top5": did in truth["top5"]}
                    offender_records.append(rec)
                    cand = bool(stopped and behind is not None and behind >= 2)
                    stopped_eval.append({**rec, "candidate": cand})
            elif verdict == "MISSING_DRIVER_OBSERVATION":
                for did in rs.unobservable_driver_ids:
                    times = times_by_driver.get(did)
                    has_later = bool(times is not None
                                     and (times > T).any())
                    has_any = bool(times is not None and len(times) > 0)
                    missing_driver_cases.append({
                        "race_id": race_id, "season": season,
                        "frame_index": frame_index, "driver_id": did,
                        "grid": grid.get(did),
                        "dns_shape": grid.get(did) is None,
                        "has_any_row": has_any,
                        "has_later_row": has_later,
                        "eventual_winner": truth["winner"] == did,
                        "eventual_top5": did in truth["top5"]})
            elif verdict == "MISSING_TYRE_STATE":
                from raceintel.simulation.adapter import from_race_state
                base_state = from_race_state(rs)
                by_id = {e.driver_id: e for e in rs.observable_drivers}
                for entry in base_state.drivers:
                    if entry.tyre_age is not None:
                        continue
                    did = entry.driver_id
                    obs = by_id.get(did)
                    tail = states[
                        (states["driver_id"] == did)
                        & (states["state_time_s"] <= T)
                        ].sort_values("state_time_s")
                    known = tail[tail["tyre_life"].notna()
                                & tail["compound"].notna()]
                    if not len(known):
                        tyre_cases.append({
                            "race_id": race_id, "season": season,
                            "frame_index": frame_index, "driver_id": did,
                            "class": "NEVER_OBSERVED_TYRE",
                            "compound_at_T": (None if obs.compound is None
                                              else str(obs.compound)),
                            "eventual_winner": truth["winner"] == did})
                        continue
                    last = known.iloc[-1]
                    cur = tail.iloc[-1]
                    gap_rows = int(len(tail) - len(known))
                    gap_s = float(T - float(last["state_time_s"]))
                    barriers = []
                    if str(cur.get("compound")) != str(last.get("compound")) \
                            and not _is_null(cur.get("compound")):
                        barriers.append("COMPOUND_CHANGE")
                    if _null_neq(cur.get("stint_number"),
                                 last.get("stint_number")):
                        barriers.append("STINT_CHANGE")
                    if _null_neq(cur.get("pit_stops_completed_so_far"),
                                 last.get("pit_stops_completed_so_far")):
                        barriers.append("PIT_COUNT_CHANGE")
                    if not _is_null(cur.get("pit_in_s")) or \
                            not _is_null(cur.get("pit_out_s")):
                        # pit transition on the at-T row itself: the row
                        # straddles a stop, tyre identity uncertain
                        barriers.append("PIT_TRANSITION_AT_T")
                    # any pit in/out between last-known and T
                    between = tail[tail["state_time_s"]
                                   > float(last["state_time_s"])]
                    if len(between) and (
                            between["pit_in_s"].notna().any()
                            or between["pit_out_s"].notna().any()):
                        barriers.append("PIT_BETWEEN")
                    tyre_cases.append({
                        "race_id": race_id, "season": season,
                        "frame_index": frame_index, "driver_id": did,
                        "class": ("CLEAN_CARRY" if not barriers
                                  else "BARRIER_" + "+".join(barriers)),
                        "gap_rows": gap_rows, "gap_s": round(gap_s, 1),
                        "last_compound": str(last.get("compound")),
                        "last_age": _py(last.get("tyre_life")),
                        "compound_at_T": (None if obs.compound is None
                                          else str(obs.compound)),
                        "eventual_winner": truth["winner"] == did})

    payload = {
        "schema_version": "v3.2c-diagnostics-v1",
        "offender_records": offender_records,
        "stopped_eval": stopped_eval,
        "missing_driver_cases": missing_driver_cases,
        "tyre_cases": tyre_cases,
        "state_count": len(state_summary),
        "summary": _summarize(offender_records, stopped_eval,
                              missing_driver_cases, tyre_cases),
    }
    text = json.dumps(payload, indent=1)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
    else:
        print(text)


def state_at_T(service, frame_index):
    return service.state_at(frame_index)


def _py(value):
    if value is None:
        return None
    try:
        import numpy as _np

        if isinstance(value, _np.generic):
            return _py(value.item())
    except ImportError:
        pass
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, float) and value.is_integer():
        return int(value)
    if isinstance(value, bool):
        return bool(value)
    if isinstance(value, (int, float, str)):
        return value
    return str(value)


def _null_neq(a, b) -> bool:
    a_null = _is_null(a) or (isinstance(a, float) and pd.isna(a))
    b_null = _is_null(b) or (isinstance(b, float) and pd.isna(b))
    if a_null or b_null:
        return True  # unknown continuity counts as a barrier
    try:
        return float(a) != float(b)
    except (TypeError, ValueError):
        return str(a) != str(b)


def _rate(rows, pred, label="terminal"):
    pos = [r for r in rows if r[pred]]
    if not rows:
        return {"support": 0}
    tp = sum(1 for r in pos if r[label])
    fp = len(pos) - tp
    fn = sum(1 for r in rows if (not r[pred]) and r[label])
    return {"support": len(rows), "predicted": len(pos), "tp": tp,
            "fp": fp, "fn": fn,
            "precision": (tp / len(pos) if pos else None),
            "recall": (tp / (tp + fn) if (tp + fn) else None)}


def _summarize(offenders, stopped_eval, missing, tyre):
    seasons = sorted({r["season"] for r in offenders})
    stopped_by_season = {}
    for s in seasons:
        sub = [r for r in stopped_eval if r["season"] == s]
        stopped_by_season[str(s)] = {
            "candidate_rule": _rate(sub, "candidate"),
            "stopped_alone": _rate(sub, "stopped"),
        }
    pit_rule = [dict(r, pit_rule=bool(r["pit_in_last"] and not r["stopped"]
                                      and r["behind"] is not None
                                      and r["behind"] >= 2))
                for r in offenders]
    pit_by_season = {}
    for s in seasons:
        sub = [r for r in pit_rule if r["season"] == s]
        pit_by_season[str(s)] = {"pit_in_rule": _rate(sub, "pit_rule")}
    other = {}
    for name, fn in (
            ("behind_ge_2", lambda r: r["behind"] is not None
             and r["behind"] >= 2),
            ("behind_ge_5", lambda r: r["behind"] is not None
             and r["behind"] >= 5),
            ("position_null", lambda r: r["position_null"]),
            ("age_gt_10x", lambda r: r["age_x"] >= 10.0)):
        rows = [dict(r, _p=bool(fn(r))) for r in offenders]
        by_season = {}
        for s in seasons:
            by_season[str(s)] = _rate([r for r in rows
                                       if r["season"] == s], "_p")
        other[name] = {"overall": _rate(rows, "_p"),
                       "by_season": by_season}
    tyre_classes: dict = {}
    for t in tyre:
        tyre_classes[t["class"]] = tyre_classes.get(t["class"], 0) + 1
    dns_shape = sum(1 for m in missing if m["dns_shape"])
    return {
        "offender_record_count": len(offenders),
        "terminal_fraction": (sum(1 for r in offenders if r["terminal"])
                              / len(offenders) if offenders else None),
        "transient_top5": sum(1 for r in offenders
                              if (not r["terminal"]) and r["eventual_top5"]),
        "transient_winners": sum(1 for r in offenders
                                 if (not r["terminal"])
                                 and r["eventual_winner"]),
        "stopped_overall_candidate": _rate(stopped_eval, "candidate"),
        "stopped_overall_alone": _rate(stopped_eval, "stopped"),
        "stopped_by_season": stopped_by_season,
        "pit_in_terminal_no_signal_fraction": _pit_in_frac(offenders),
        "pit_rule_by_season": pit_by_season,
        "other_signals": other,
        "missing_driver_cases": len(missing),
        "missing_driver_dns_shape": dns_shape,
        "missing_driver_eventual_top5": sum(
            1 for m in missing if m["eventual_top5"]),
        "tyre_cases": len(tyre),
        "tyre_classes": tyre_classes,
    }


def _pit_in_frac(offenders):
    no_sig = [r for r in offenders if not r["stopped"]]
    term = [r for r in no_sig if r["terminal"]]
    if not term:
        return None
    return sum(1 for r in term if r["pit_in_last"]) / len(term)


if __name__ == "__main__":
    main()
