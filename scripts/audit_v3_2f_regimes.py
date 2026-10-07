#!/usr/bin/env python3
"""V3.2F regime opportunity audit (Parts D/E/F/K + season/stage/race cuts).

Read-only single pass over the 149-race / 9644-checkpoint replay
catalogue. For EVERY checkpoint (not only refused ones) records:

- primary verdict under the frozen V3.2C presence path (comparability
  with the V3.2C audit: same parameter set, same policy),
- ALL applicable blockers (every pipeline stage evaluated independently
  wherever its inputs exist; factual probes from RaceState always),
- factual regime snapshot at T: track_state token, rainfall flag,
  per-driver compound/tyre-age/observation-age summaries,
- stage / season / race / fraction / leader_lap context.

Also emits per-race track-state run-length episodes (neutralisation
entry/active/exit, OFFLINE analysis input for Part F) from the D9 frame.

No simulator source, parameter, artifact, or replay cache is modified.
No Monte Carlo runs. No model training. Output carries no timestamps,
usernames, or absolute paths.
"""

from __future__ import annotations

import argparse
import glob
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

OUT_DIR = ROOT / "results" / "v3" / "v3_2f"

WET_COMPOUNDS = ("INTERMEDIATE", "WET")


def season_of(race_id: str) -> int:
    return int(race_id.split("-")[0])


def stage_for(fraction) -> str | None:
    if fraction is None:
        return None
    try:
        f = float(fraction)
    except (TypeError, ValueError):
        return None
    if f != f:
        return None
    if f < 1.0 / 3.0:
        return "EARLY"
    if f < 2.0 / 3.0:
        return "MID"
    return "LATE"


def _grid_map(results) -> dict:
    out = {}
    for row in results.itertuples():
        grid = getattr(row, "grid_position", None)
        if grid is None or (isinstance(grid, float) and grid != grid):
            out[str(row.driver_id)] = None
        else:
            out[str(row.driver_id)] = float(grid)
    return out


def _snapshot_race_state(race_state) -> dict:
    """Factual probes straight from RaceState (no pipeline needed)."""
    rc = race_state.race_control
    wx = race_state.weather
    obs = {e.driver_id: e for e in race_state.observable_drivers}
    compounds = {}
    wet_drivers = []
    missing_tyre = []
    ages = {}
    for did in race_state.roster_driver_ids:
        e = obs.get(did)
        if e is None:
            continue
        compounds[did] = e.compound
        if e.compound in WET_COMPOUNDS:
            wet_drivers.append(did)
        if e.tyre_life is None:
            missing_tyre.append(did)
        ages[did] = (None if e.observation_age_s is None
                     else float(e.observation_age_s))
    return {
        "track_state": rc.track_state,
        "rainfall": (None if wx is None else wx.rainfall),
        "compounds": compounds,
        "wet_drivers": sorted(wet_drivers),
        "missing_tyre_drivers": sorted(missing_tyre),
        "observation_age_s": ages,
        "unobserved": sorted(race_state.unobservable_driver_ids),
        "roster": sorted(race_state.roster_driver_ids),
    }


def _all_blockers(race_state, grid: dict, params, snap: dict) -> dict:
    """Every applicable blocker, evaluated independently per stage."""
    from raceintel.simulation.adapter import from_race_state
    from raceintel.simulation.engine import (
        ExecutionPolicy,
        SimulationUnsupportedError,
        _validate_start_state,
        _validate_temporal,
        contemporaneous_roster_offenders,
        select_pace_parameters,
    )
    from raceintel.simulation.presence import (
        ADAPTER_REASON_TO_TAXONOMY,
        ENGINE_REASON_TO_TAXONOMY,
        dns_exclusions,
        without_drivers,
    )

    blockers: set[str] = set()
    stage_detail: dict = {}
    dns = dns_exclusions(race_state, grid)
    active = without_drivers(race_state, dns) if dns else race_state

    # Factual probes (always available).
    if snap["track_state"] != "all_clear":
        blockers.add("UNSUPPORTED_TRACK_STATE")
        stage_detail["track_state"] = snap["track_state"]
    if snap["rainfall"] is True:
        blockers.add("WET_CONDITIONS")
        stage_detail["wet"] = "rainfall"
    if snap["wet_drivers"]:
        blockers.add("WET_CONDITIONS")
        stage_detail["wet_compound_drivers"] = snap["wet_drivers"]
    if snap["missing_tyre_drivers"]:
        blockers.add("MISSING_TYRE_STATE")
    raw_unobs = [d for d in snap["unobserved"] if d not in set(dns)]
    if raw_unobs:
        blockers.add("MISSING_DRIVER_OBSERVATION")

    sim_state = None
    try:
        sim_state = from_race_state(active)
    except Exception as exc:  # noqa: BLE001 - record, keep probing
        reason = getattr(exc, "reason", type(exc).__name__)
        taxon = ADAPTER_REASON_TO_TAXONOMY.get(reason, "OTHER")
        blockers.add(taxon)
        stage_detail["adapter_reason"] = reason
    if sim_state is not None:
        if sim_state.leader_laps_done >= sim_state.scheduled_laps:
            blockers.add("TERMINAL_STATE")
        selection = None
        try:
            selection = select_pace_parameters(sim_state, params)
        except Exception as exc:  # noqa: BLE001
            reason = getattr(exc, "reason", type(exc).__name__)
            taxon = ENGINE_REASON_TO_TAXONOMY.get(reason, "OTHER")
            blockers.add(taxon)
            stage_detail["select_reason"] = reason
        if selection is not None:
            try:
                _validate_start_state(sim_state, selection)
            except Exception as exc:  # noqa: BLE001
                reason = getattr(exc, "reason", type(exc).__name__)
                taxon = ENGINE_REASON_TO_TAXONOMY.get(reason, "OTHER")
                blockers.add(taxon)
                stage_detail.setdefault("validate_reason", reason)
            try:
                _validate_temporal(
                    sim_state, params,
                    ExecutionPolicy.RETROSPECTIVE_PRODUCT, selection)
            except Exception as exc:  # noqa: BLE001
                reason = getattr(exc, "reason", type(exc).__name__)
                taxon = ENGINE_REASON_TO_TAXONOMY.get(reason, "OTHER")
                blockers.add(taxon)
            try:
                offenders = contemporaneous_roster_offenders(
                    sim_state, selection.base.value)
            except Exception:  # noqa: BLE001 - no scale, no conclusion
                offenders = ()
            if offenders:
                blockers.add("STALE_ROSTER_OBSERVATION")
                stage_detail["stale_offenders"] = [
                    d for d, _ in offenders]
                stage_detail["n_stale"] = len(offenders)
    return {"blockers": sorted(blockers), "detail": stage_detail,
            "dns_excluded": sorted(dns)}


def _race_episodes(states, race_id: str) -> list:
    """Run-length episodes of track_state over the D9 frame (OFFLINE)."""
    df = states[states["race_id"] == race_id].copy()
    if df.empty:
        return []
    df = df.sort_values(["state_time_s", "lap_number", "driver_id"])
    # One token per distinct state_time_s: the modal non-null token.
    per_t = (df.groupby("state_time_s")["track_state"]
             .agg(lambda s: s.mode().iloc[0] if len(s.mode()) else None))
    episodes = []
    cur_token, cur_start, cur_end, cur_laps = None, None, None, set()
    lap_at = df.groupby("state_time_s")["lap_number"].max().to_dict()
    for t, tok in per_t.items():
        if tok != cur_token:
            if cur_token is not None:
                episodes.append({
                    "token": cur_token, "start_s": cur_start,
                    "end_s": cur_end, "entry_lap": cur_lap0,
                    "exit_lap": cur_lap1})
            cur_token, cur_start = tok, t
            cur_lap0 = lap_at.get(t)
        cur_end = t
        cur_lap1 = lap_at.get(t)
    if cur_token is not None:
        episodes.append({"token": cur_token, "start_s": cur_start,
                         "end_s": cur_end, "entry_lap": cur_lap0,
                         "exit_lap": cur_lap1})
    return episodes


def _audit_race(path: str, through_season: int = 2024) -> dict:
    import pandas as pd

    from raceintel.race_state.race_state_reconstruction import (
        RaceStateReconstructor,
    )
    from raceintel.replay import replay as RP
    from raceintel.replay.replay_reconstruction import ReplayReconstructor
    from raceintel.simulation.engine import ExecutionPolicy
    from raceintel.simulation.params import (
        load_simulation_parameters,
        parameter_storage_dir,
    )
    from raceintel.simulation.presence import prepare_initial_state

    artifact = json.load(open(path, encoding="utf-8"))
    race_id = artifact["race_id"]
    season = season_of(race_id)
    params = load_simulation_parameters(
        parameter_storage_dir(ROOT, through_season))
    base = ROOT / "data" / "v2" / "processed"
    states = pd.read_parquet(
        base / f"driver_lap_state_d9/season={season}/"
        f"driver_lap_state_d9__d9-{season}.parquet")
    states = states[states["race_id"] == race_id].copy()
    results = pd.read_parquet(
        base / f"results/season={season}/results__{race_id}.parquet")
    meta: dict = {}
    races_path = base / f"races/season={season}/races__{race_id}.parquet"
    try:
        for row in pd.read_parquet(races_path).itertuples():
            scheduled = getattr(row, "total_laps_scheduled", None)
            meta[str(row.race_id)] = {
                "scheduled_laps": (None if pd.isna(scheduled)
                                   else int(scheduled))}
    except FileNotFoundError:
        pass
    grid = _grid_map(results)
    timeline = RP.build_replay_timeline(states)
    service = ReplayReconstructor(
        timeline, RaceStateReconstructor(states, results,
                                         race_meta=meta or None))
    out = []
    for entry in artifact["checkpoints"]:
        cp = entry["checkpoint"]
        frame = cp["frame_index"]
        try:
            race_state = service.state_at(frame)
        except Exception as exc:  # noqa: BLE001
            out.append({
                "race_id": race_id, "season": season,
                "frame_index": frame, "stage": cp.get("stage"),
                "fraction": cp.get("fraction"),
                "leader_lap": cp.get("leader_lap"),
                "primary": "RECONSTRUCTION_FAILURE",
                "all_blockers": ["RECONSTRUCTION_FAILURE"],
                "track_state": None, "rainfall": None,
                "detail": {"error": type(exc).__name__},
            })
            continue
        snap = _snapshot_race_state(race_state)
        probe = _all_blockers(race_state, grid, params, snap)
        try:
            verdict = prepare_initial_state(
                race_state, grid_by_driver=grid, parameters=params,
                execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
            primary = (verdict.reason if not verdict.eligible
                       else "SIMULATION_CAPABLE")
        except Exception:  # noqa: BLE001 - probe already recorded facts
            primary = sorted(probe["blockers"])[0] if probe["blockers"] \
                else "OTHER"
        if primary == "SIMULATION_CAPABLE":
            all_b: list = []
        else:
            all_b = probe["blockers"] or [primary]
            if primary not in all_b:
                all_b = [primary] + all_b
        out.append({
            "race_id": race_id, "season": season, "frame_index": frame,
            "stage": cp.get("stage") or stage_for(cp.get("fraction")),
            "fraction": cp.get("fraction"), "leader_lap": cp.get(
                "leader_lap"),
            "primary": primary, "all_blockers": all_b,
            "track_state": snap["track_state"], "rainfall": snap["rainfall"],
            "wet_drivers": snap["wet_drivers"],
            "missing_tyre_drivers": snap["missing_tyre_drivers"],
            "n_stale": probe["detail"].get("n_stale"),
            "dns_excluded": probe["dns_excluded"],
            "detail": probe["detail"],
        })
    episodes = _race_episodes(states, race_id)
    return {"race_id": race_id, "checkpoints": out, "episodes": episodes}


def _worker(path: str) -> dict:
    try:
        return {"ok": True, **_audit_race(path)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "path": path,
                "error": f"{type(exc).__name__}: {exc}"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workers", type=int, default=8)
    ap.add_argument("--limit-races", type=int, default=None)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()

    import concurrent.futures

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    paths = sorted(glob.glob(
        str(ROOT / "results" / "v2_replay" / "checkpoints" / "*.json")))
    if args.limit_races is not None:
        paths = paths[:args.limit_races]
    t0 = time.perf_counter()
    with concurrent.futures.ProcessPoolExecutor(
            max_workers=args.workers) as pool:
        outs = list(pool.map(_worker, paths))
    failures = [o for o in outs if not o.get("ok")]
    checkpoints = []
    episodes = {}
    for o in outs:
        if not o.get("ok"):
            continue
        checkpoints.extend(o["checkpoints"])
        episodes[o["race_id"]] = o["episodes"]
    doc = {
        "schema_version": "v3.2f-regime-opportunity-v1",
        "parameter_through_season": 2024,
        "execution_policy": "retrospective_product",
        "n_races": len(paths),
        "n_checkpoints": len(checkpoints),
        "worker_failures": failures,
        "checkpoints": checkpoints,
        "episodes": episodes,
        "wall_clock_s": round(time.perf_counter() - t0, 1),
    }
    out_path = Path(args.out) if args.out else (
        OUT_DIR / "coverage_opportunity_raw.json")
    out_path.write_text(json.dumps(doc, sort_keys=True) + "\n",
                        encoding="utf-8")
    print(json.dumps({"status": "OK",
                      "n_checkpoints": len(checkpoints),
                      "worker_failures": len(failures),
                      "wall_clock_s": doc["wall_clock_s"]}))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
