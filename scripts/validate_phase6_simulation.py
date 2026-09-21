#!/usr/bin/env python3
"""Phase-6 R7 historical validation driver.

Freeze-then-evaluate: it loads the predeclared protocol, builds deterministic
expanding-chronology parameter artifacts (through ``season - 1``), selects a
predeclared systematic sample of races and three leader-progress checkpoints
per race, and compares the frozen R6 simulator against factual baselines using
evaluation-only historical truth.

It performs NO tuning. Selection, seeds, counts, bins and epsilons come from
``v2.simulation.validation`` (frozen before any scoring). Generated artifacts
are written under ``data/v2/simulation/validation/`` (repository-untracked).

Usage::

    python scripts/validate_phase6_simulation.py
    python scripts/validate_phase6_simulation.py --limit 2 --dry-run
    python scripts/validate_phase6_simulation.py --seasons 2023 --per-season 3

2025 is never read: the season allow-list is enforced structurally.
"""

from __future__ import annotations

import argparse
import json
import math
import resource
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from v2 import replay as RP  # noqa: E402
from v2.race_state_reconstruction import RaceStateReconstructor  # noqa: E402
from v2.replay_reconstruction import ReplayReconstructor  # noqa: E402
from v2.simulation import validation as V  # noqa: E402
from v2.simulation.adapter import (  # noqa: E402
    SimulationUnavailableError,
    from_race_state,
)
from v2.simulation.config import Assumptions, SimulationConfig  # noqa: E402
from v2.simulation.engine import (  # noqa: E402
    DeterministicRaceEngine,
    ExecutionPolicy,
    SimulationUnsupportedError,
    _validate_start_state,
    select_pace_parameters,
)
from v2.simulation.monte_carlo import (  # noqa: E402
    MonteCarloEngine,
    select_pit_parameters,
    select_residual_sampler,
)
from v2.simulation.params import (  # noqa: E402
    load_simulation_parameters,
    parameter_storage_dir,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
PROCESSED = PROJECT_ROOT / "data" / "v2" / "processed"
OUT_DIR = PROJECT_ROOT / "data" / "v2" / "simulation" / "validation"
PARAM_ROOT = PROJECT_ROOT / "data" / "v2" / "simulation" / "params"

D9_PATH = (str(PROCESSED) + "/driver_lap_state_d9/season={season}/"
           "driver_lap_state_d9__d9-{season}.parquet")
RESULTS_PATH = (str(PROCESSED) + "/results/season={season}/"
                "results__{race}.parquet")
RACES_PATH = (str(PROCESSED) + "/races/season={season}/races__{race}.parquet")
PIT_STOPS_PATH = (str(PROCESSED) + "/pit_stops/season={season}/"
                  "pit_stops__{race}.parquet")


# ---------------------------------------------------------------------------
# Small utilities.
# ---------------------------------------------------------------------------

def peak_rss_mb() -> float:
    value = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    if sys.platform == "darwin":
        return value / (1024.0 * 1024.0)
    return value / 1024.0


def _jsonable(value):
    if isinstance(value, dict):
        return {str(k): _jsonable(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(v) for v in value]
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def sha256_file(path: Path) -> str:
    import hashlib
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Data plumbing (evaluation only).
# ---------------------------------------------------------------------------

class RaceData:
    """Cached canonical slices plus the frozen replay seam for one race."""

    def __init__(self, paths, season: int, race_id: str):
        states = pd.read_parquet(D9_PATH.format(season=season))
        states = states[states["race_id"] == race_id].copy()
        results = pd.read_parquet(
            RESULTS_PATH.format(season=season, race=race_id))
        races = pd.read_parquet(
            RACES_PATH.format(season=season, race=race_id))
        scheduled = None
        for row in races.itertuples():
            value = getattr(row, "total_laps_scheduled", None)
            if value is not None and not pd.isna(value):
                scheduled = int(value)
        self.season = season
        self.race_id = race_id
        self.scheduled_laps = scheduled
        self.results_rows = results.to_dict("records")
        meta = {race_id: {"scheduled_laps": scheduled}}
        self.timeline = RP.build_replay_timeline(states)
        self.service = ReplayReconstructor(
            self.timeline,
            RaceStateReconstructor(states, results, race_meta=meta))
        leader_by_time = (states.groupby("state_time_s")
                          ["race_leader_laps_at_state"].first().to_dict())
        self.frames_meta = tuple(
            (frame.frame_index,
             leader_by_time.get(frame.anchor_state_time_s,
                                frame.anchor_lap_number))
            for frame in self.timeline.frames)
        self._pit_stops = None
        try:
            self._pit_stops = pd.read_parquet(
                PIT_STOPS_PATH.format(season=season, race=race_id))
        except FileNotFoundError:
            self._pit_stops = None

    def historical_total_stops(self) -> dict:
        counts: dict = {}
        if self._pit_stops is not None and len(self._pit_stops):
            for driver, n in self._pit_stops.groupby("driver_id").size().items():
                counts[str(driver)] = int(n)
        return counts


def build_sim_state(race: RaceData, frame_index: int):
    return from_race_state(race.service.state_at(frame_index),
                           anchor_frame_index=frame_index)


def support_status(state, params) -> tuple:
    """The runtime simulation-start support contract.

    R7.1: the runtime itself now rejects non-contemporaneous roster members
    (R7-BUG-2) with the stable ``non_contemporaneous_roster_member`` reason,
    so the evaluator no longer applies a separate contemporaneity criterion.
    """
    try:
        selection = select_pace_parameters(state, params)
        select_residual_sampler(params, selection.era)
        select_pit_parameters(state, selection, params)
        _validate_start_state(state, selection)
    except SimulationUnavailableError as exc:
        return False, exc.reason
    except SimulationUnsupportedError as exc:
        return False, exc.reason
    return True, None


def try_state(race: RaceData, frame_index: int, params):
    try:
        state = build_sim_state(race, frame_index)
    except SimulationUnavailableError as exc:
        return None, exc.reason
    except SimulationUnsupportedError as exc:
        return None, exc.reason
    ok, reason = support_status(state, params)
    return (state, None) if ok else (None, reason)


def select_stage_states(race: RaceData, params, protocol: V.R7Protocol):
    """Return ``{stage: (state, frame_index, leader_lap)}`` plus exclusions."""
    if race.scheduled_laps is None:
        return {}, {"missing_scheduled_laps": 1}
    targets = V.stage_target_laps(race.scheduled_laps, protocol)
    radius = V.checkpoint_radius_laps(race.scheduled_laps, protocol)
    selected: dict = {}
    exclusions: dict = {}
    for stage, target in targets.items():
        order = V.checkpoint_search_order(race.frames_meta, target,
                                          radius_laps=radius)
        if not order:
            exclusions[stage] = "no_supported_state_within_radius"
            continue
        last_reason = None
        for frame_index, leader_lap in order:
            state, reason = try_state(race, frame_index, params)
            if state is not None:
                selected[stage] = (state, frame_index, leader_lap)
                break
            last_reason = reason
        else:
            exclusions[stage] = last_reason or "no_supported_state"
    return selected, exclusions


# ---------------------------------------------------------------------------
# Simulation + evaluation.
# ---------------------------------------------------------------------------

def run_mc(state, params, count: int, seed: int, pit: bool,
           chunk_size: int):
    config = SimulationConfig(simulation_count=count, master_seed=seed,
                              sample_orders=0, pit_dynamics_enabled=pit)
    engine = MonteCarloEngine(chunk_size=chunk_size)
    result = engine.run(state, params, config, Assumptions(),
                        execution_policy=ExecutionPolicy.HISTORICAL_BACKTEST,
                        collect_diagnostics=pit)
    return result, engine.last_diagnostics


def point_distributions(order, predicted_position_by_driver: dict) -> dict:
    """Per-driver one-hot finish distribution at the predicted position."""
    size = len(order)
    distributions = {}
    for driver in order:
        position = int(round(float(predicted_position_by_driver[driver])))
        position = min(max(position, 1), size)
        distributions[driver] = {
            candidate: (1.0 if candidate == position else 0.0)
            for candidate in range(1, size + 1)}
    return distributions


def rank_order(order) -> dict:
    return {driver: float(position)
            for position, driver in enumerate(order, start=1)}


def evaluate_prediction(win_probs: dict, expected_finish: dict,
                        position_dists: dict, truth: dict) -> dict:
    winner = truth["winner_driver_id"]
    classified = list(truth["classified_driver_ids"])
    actual = truth["position_by_driver"]
    record = {
        "winner_log_loss": V.winner_log_loss(win_probs, winner),
        "brier": V.brier_score(win_probs, winner),
        "top1": bool(V.top_k_winner_accuracy(win_probs, winner, 1)),
        "top3": bool(V.top_k_winner_accuracy(win_probs, winner, 3)),
        "expected_finish_mae": V.expected_finish_mae(
            expected_finish, actual, classified),
        "spearman": V.spearman_rank_correlation(
            expected_finish, actual, classified),
    }
    if position_dists is not None:
        record["rps"] = float(np.mean([
            V.ranked_probability_score(position_dists[driver], actual[driver])
            for driver in classified]))
        record["position_nll"] = float(np.mean([
            V.position_log_score(position_dists[driver], actual[driver])
            for driver in classified]))
    else:
        record["rps"] = None
        record["position_nll"] = None
    return record


def compute_baselines(state, params, truth: dict, *, r5_result=None) -> dict:
    """Factual baselines from the T state / grid / deterministic kernel."""
    order = V.current_order(state)
    leader = order[0]
    current_win = V.one_hot_win_probabilities(state, leader)
    current_expected = rank_order(order)
    current_dist = point_distributions(order, current_expected)

    grid = truth["grid_by_driver"]
    grid_available = all(grid.get(driver) is not None for driver in order)
    if grid_available:
        pole = min(order, key=lambda d: (grid[d], d))
        grid_win = V.one_hot_win_probabilities(state, pole)
        grid_expected = {driver: float(grid[driver]) for driver in order}
        grid_dist = point_distributions(order, grid_expected)
    else:
        grid_win = grid_expected = grid_dist = None

    records = {}

    # CURRENT_LEADER winner-only baseline.
    records["CURRENT_LEADER"] = {
        "winner_log_loss": V.winner_log_loss(current_win,
                                             truth["winner_driver_id"]),
        "brier": V.brier_score(current_win, truth["winner_driver_id"]),
        "top1": bool(V.top_k_winner_accuracy(
            current_win, truth["winner_driver_id"], 1)),
        "top3": bool(V.top_k_winner_accuracy(
            current_win, truth["winner_driver_id"], 3)),
    }
    records["CURRENT_ORDER"] = evaluate_prediction(
        current_win, current_expected, current_dist, truth)
    if grid_available:
        records["GRID_ORDER"] = evaluate_prediction(
            grid_win, grid_expected, grid_dist, truth)

    deterministic = DeterministicRaceEngine().run(
        state, params,
        execution_policy=ExecutionPolicy.HISTORICAL_BACKTEST)
    if deterministic.valid:
        r4_order = deterministic.classification.finishing_order
        r4_winner = r4_order[0]
        r4_expected = rank_order(r4_order)
        records["R4_DETERMINISTIC"] = evaluate_prediction(
            V.one_hot_win_probabilities(state, r4_winner),
            r4_expected,
            point_distributions(order, r4_expected),
            truth)
    if r5_result is not None:
        records["R5_NO_PIT"] = evaluate_prediction(
            V.result_win_probabilities(r5_result),
            V.result_expected_finish(r5_result),
            V.result_position_distributions(r5_result), truth)
    return records


def finish_spread(result) -> float:
    dists = V.result_position_distributions(result)
    spreads = []
    for distribution in dists.values():
        positions = np.array(sorted(distribution))
        probs = np.array([distribution[p] for p in positions])
        mean = float((positions * probs).sum())
        variance = float(((positions - mean) ** 2 * probs).sum())
        spreads.append(math.sqrt(max(variance, 0.0)))
    return float(np.mean(spreads)) if spreads else float("nan")


def winner_entropy(result) -> float:
    probs = np.array([p for p in V.result_win_probabilities(result).values()
                      if p > 0.0])
    return float(-(probs * np.log(probs)).sum())


# ---------------------------------------------------------------------------
# Artifact generation (R7-C/D): expanding chronology, through season - 1.
# ---------------------------------------------------------------------------

def ensure_artifact(season: int, rebuild: bool) -> dict:
    from v2.simulation.estimator import estimate_simulation_parameters
    from v2.config import V2Paths
    from v2.simulation.params import PARAMETER_MANIFEST_FILENAME

    through = season - 1
    out_dir = parameter_storage_dir(PROJECT_ROOT, through)
    manifest = out_dir / PARAMETER_MANIFEST_FILENAME
    started = time.perf_counter()
    if rebuild or not manifest.exists():
        paths = V2Paths.resolve(str(PROJECT_ROOT))
        params = estimate_simulation_parameters(
            paths, through_season=through,
            creation_metadata={"generator": "r7-validation",
                               "estimator_version": None})
        out_dir.mkdir(parents=True, exist_ok=True)
        manifest.write_text(params.to_json() + "\n", encoding="utf-8")
    runtime = time.perf_counter() - started
    params = load_simulation_parameters(out_dir)
    return {
        "season": season,
        "through_season": through,
        "path": str(manifest),
        "scientific_hash": params.scientific_hash(),
        "parameter_version": params.parameter_version,
        "size_bytes": manifest.stat().st_size,
        "build_runtime_s": runtime,
        "estimation_seasons": list(params.estimation_seasons),
        "rebuilt": bool(rebuild or not manifest.exists()),
    }


# ---------------------------------------------------------------------------
# Main.
# ---------------------------------------------------------------------------

def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--seasons", type=int, nargs="+",
                        default=list(V.R7_EVALUATION_SEASONS))
    parser.add_argument("--per-season", type=int, default=6)
    parser.add_argument("--counts", type=int, nargs="+", default=[1000])
    parser.add_argument("--calibration-count", type=int, default=10000)
    parser.add_argument("--calibration-races-per-season", type=int, default=1)
    parser.add_argument("--seed", type=int, default=V.R7_MASTER_SEED)
    parser.add_argument("--chunk-size", type=int, default=512)
    parser.add_argument("--limit", type=int, default=None,
                        help="max races (smoke; NOT a protocol run)")
    parser.add_argument("--no-calibration", action="store_true")
    parser.add_argument("--no-sensitivity", action="store_true")
    parser.add_argument("--rebuild-artifacts", action="store_true")
    parser.add_argument("--out-dir", default=str(OUT_DIR))
    parser.add_argument("--dry-run", action="store_true",
                        help="selection only; no Monte Carlo")
    return parser.parse_args(argv)


def main(argv=None) -> int:
    args = parse_args(argv)
    protocol = V.default_protocol()
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if any(season in (2018, 2019, 2025) for season in args.seasons):
        print("error: evaluation seasons must be within 2020-2024 "
              "(2018/2019 lack prior estimation history; 2025 is firewalled)",
              file=sys.stderr)
        return 2
    if args.limit is None and tuple(args.seasons) != V.R7_EVALUATION_SEASONS:
        print("error: a non-default season set requires --limit "
              "(protocol runs use the predeclared seasons)", file=sys.stderr)
        return 2

    report: dict = {
        "protocol": protocol.to_dict(),
        "protocol_identity": protocol.identity(),
        "argv": {k: v for k, v in vars(args).items() if k != "argv"},
        "parameter_artifacts": [],
        "races": [],
        "exclusions": [],
        "state_records": [],
        "baseline_records": {},
        "calibration": {},
        "pit": {},
        "residual": {},
        "performance": {},
    }

    started = time.perf_counter()
    per_state: list = []
    baseline_records: dict = {name: [] for name in V.R7_BASELINES}
    calibration_points: list = []
    calibration_subset: list = []
    pit_records: list = []

    for season in args.seasons:
        artifact = ensure_artifact(season, args.rebuild_artifacts)
        report["parameter_artifacts"].append(artifact)
        params = load_simulation_parameters(artifact["path"])
        race_dir = PROCESSED / "results" / f"season={season}"
        race_ids = sorted(path.stem.replace("results__", "")
                          for path in race_dir.glob("*.parquet"))
        selected = V.systematic_race_selection(race_ids, args.per_season)
        if args.limit is not None:
            selected = selected[:args.limit]
        for race_id in selected:
            try:
                race = RaceData(PROJECT_ROOT, season, race_id)
            except Exception as exc:  # noqa: BLE001 - factual load guard
                report["exclusions"].append({
                    "season": season, "race_id": race_id,
                    "reason": "race_load_error", "detail": str(exc)[:200]})
                continue
            states, exclusions = select_stage_states(race, params, protocol)
            for stage, reason in sorted(exclusions.items()):
                report["exclusions"].append({
                    "season": season, "race_id": race_id, "stage": stage,
                    "reason": reason})
            report["races"].append({
                "season": season, "race_id": race_id,
                "scheduled_laps": race.scheduled_laps,
                "selected": True,
                "stages": {stage: {"frame_index": frame_index,
                                   "leader_lap": leader_lap,
                                   "state_identity": state.identity()}
                           for stage, (state, frame_index, leader_lap)
                           in states.items()},
                "excluded_stages": exclusions,
            })
            for stage, (state, frame_index, leader_lap) in states.items():
                truth = V.historical_truth(race.results_rows,
                                           state.roster_driver_ids)
                state_info = {
                    "season": season, "race_id": race_id, "stage": stage,
                    "frame_index": frame_index, "leader_lap": leader_lap,
                    "scheduled_laps": race.scheduled_laps,
                    "field_size": state.roster_size,
                    "state_identity": state.identity(),
                    "parameter_version": params.parameter_version,
                    "parameter_hash": params.scientific_hash(),
                    "initial_pit_counts": {
                        driver.driver_id: driver.pit_count
                        for driver in state.drivers},
                }
                if args.dry_run:
                    per_state.append(state_info)
                    continue

                for count in args.counts:
                    r6_result, diagnostics = run_mc(
                        state, params, count, args.seed, True,
                        args.chunk_size)
                    r5_result, _ = run_mc(
                        state, params, count, args.seed, False,
                        args.chunk_size)
                    r6_metrics = evaluate_prediction(
                        V.result_win_probabilities(r6_result),
                        V.result_expected_finish(r6_result),
                        V.result_position_distributions(r6_result), truth)
                    records = compute_baselines(state, params, truth,
                                               r5_result=r5_result)
                    for name, values in records.items():
                        baseline_records[name].append({
                            **state_info, "mode": name, **values})
                    winner = truth["winner_driver_id"]
                    p_winner = V.result_win_probabilities(
                        r6_result)[winner]
                    state_record = {
                        **state_info,
                        "mode": "R6_PIT",
                        "count": count,
                        "valid": r6_result.valid_simulation_count,
                        "invalid": r6_result.invalid_simulation_count,
                        "r6_result_identity": r6_result.identity(),
                        **r6_metrics,
                        "mc_se_actual_winner": V.monte_carlo_standard_error(
                            p_winner, r6_result.valid_simulation_count),
                        "winner_entropy": winner_entropy(r6_result),
                        "finish_spread": finish_spread(r6_result),
                        "actual_winner": winner,
                        "predicted_winner": max(
                            V.result_win_probabilities(r6_result),
                            key=V.result_win_probabilities(r6_result).get),
                    }
                    per_state.append(state_record)
                    for driver_id, prob in V.result_win_probabilities(
                            r6_result).items():
                        calibration_points.append({
                            **{k: state_info[k] for k in
                               ("season", "race_id", "stage", "frame_index",
                                "leader_lap", "field_size")},
                            "count": count,
                            "driver_id": driver_id,
                            "probability": prob,
                            "outcome": int(driver_id == winner),
                        })
                    if diagnostics is not None:
                        hist = diagnostics.pit_count_distribution
                        simulated = []
                        for pit_count, n in hist:
                            simulated.extend([int(pit_count)] * int(n))
                        historical_total = race.historical_total_stops()
                        historical = [historical_total.get(driver.driver_id, 0)
                                      for driver in state.drivers]
                        pit_records.append({
                            "season": season, "race_id": race_id,
                            "stage": stage,
                            "mean_pits_per_driver": diagnostics
                            .mean_pits_per_driver,
                            "total_pit_events": diagnostics.total_pit_events,
                            **V.pit_behaviour_metrics(simulated, historical),
                            "stint_target_sample":
                                diagnostics.stint_target_sample,
                            "compound_transitions":
                                [{"transition": t, "count": n}
                                 for t, n in
                                 diagnostics.compound_transition_counts],
                        })

                # Predeclared calibration subset: first race of each season,
                # MID stage.
                first_race = selected[0] if selected else None
                if (not args.no_calibration and stage == "MID"
                        and race_id == first_race
                        and len(calibration_subset) < (
                            args.calibration_races_per_season
                            * len(args.seasons))):
                    calibration_subset.append((season, race_id, stage, state,
                                               params, truth))

    # --- calibration subset at the higher simulation count ---------------
    if not args.no_calibration and not args.dry_run:
        for (season, race_id, stage, state, params, truth) in calibration_subset:
            for mode, pit in (("R6_PIT", True), ("R5_NO_PIT", False)):
                result, _ = run_mc(state, params,
                                   args.calibration_count, args.seed, pit,
                                   args.chunk_size)
                win_probs = V.result_win_probabilities(result)
                winner = truth["winner_driver_id"]
                metrics = evaluate_prediction(
                    win_probs, V.result_expected_finish(result),
                    V.result_position_distributions(result), truth)
                record = {
                    "season": season, "race_id": race_id, "stage": stage,
                    "mode": mode, "count": args.calibration_count,
                    "state_identity": state.identity(),
                    **metrics,
                    "mc_se_actual_winner": V.monte_carlo_standard_error(
                        win_probs[winner], result.valid_simulation_count),
                }
                report["calibration"].setdefault("subset_records",
                                                 []).append(record)
                for driver_id, prob in win_probs.items():
                    calibration_points.append({
                        "season": season, "race_id": race_id, "stage": stage,
                        "count": args.calibration_count, "driver_id": driver_id,
                        "probability": prob,
                        "outcome": int(driver_id == winner)})

    report["state_records"] = per_state
    report["baseline_records"] = baseline_records
    report["pit"]["records"] = pit_records

    # --- calibration bins + ECE ------------------------------------------
    if not args.dry_run and calibration_points:
        r6_points = [p for p in calibration_points]
        bins = V.calibration_bins(
            [p["probability"] for p in r6_points],
            [p["outcome"] for p in r6_points])
        report["calibration"]["bins"] = bins
        report["calibration"]["ece"] = V.expected_calibration_error(bins)
        report["calibration"]["point_count"] = len(r6_points)
        report["calibration"]["by_count"] = {}
        for count in sorted({p["count"] for p in r6_points}):
            subset = [p for p in r6_points if p["count"] == count]
            sub_bins = V.calibration_bins(
                [p["probability"] for p in subset],
                [p["outcome"] for p in subset])
            report["calibration"]["by_count"][str(count)] = {
                "point_count": len(subset),
                "ece": V.expected_calibration_error(sub_bins),
                "bins": sub_bins,
            }

    # --- residual audit + diagnostic sensitivity -------------------------
    if not args.dry_run:
        audit = []
        for season in args.seasons:
            params = load_simulation_parameters(
                parameter_storage_dir(PROJECT_ROOT, season - 1))
            for era in ("2018-2021", "2022-2024"):
                try:
                    audit.append(V.residual_sampler_audit(params, era))
                except Exception:  # noqa: BLE001 - era may be absent
                    continue
        report["residual"]["audit"] = audit
        if not args.no_sensitivity and calibration_subset:
            sensitivity = []
            for (season, race_id, stage, state, params, truth) in \
                    calibration_subset:
                matched = V.variance_matched_parameter_set(params)
                for label, use_params in (("production", params),
                                          ("variance_matched", matched)):
                    result, _ = run_mc(state, use_params, metrics_count(
                        args), args.seed, True, args.chunk_size)
                    win_probs = V.result_win_probabilities(result)
                    metrics = evaluate_prediction(
                        win_probs, V.result_expected_finish(result),
                        V.result_position_distributions(result), truth)
                    sensitivity.append({
                        "season": season, "race_id": race_id, "stage": stage,
                        "sampler": label,
                        "winner_entropy": winner_entropy(result),
                        "finish_spread": finish_spread(result),
                        "winner_log_loss": metrics["winner_log_loss"],
                        "brier": metrics["brier"],
                        "expected_finish_mae": metrics["expected_finish_mae"],
                        "rps": metrics["rps"],
                    })
            report["residual"]["sensitivity"] = sensitivity

    # --- aggregation ------------------------------------------------------
    if not args.dry_run and per_state:
        r6_records = [r for r in per_state if r["mode"] == "R6_PIT"]
        report["aggregates"] = {
            "race_macro": {
                metric: V.aggregate_race_macro(r6_records, metric)
                for metric in ("winner_log_loss", "brier",
                               "expected_finish_mae", "spearman", "rps",
                               "position_nll", "winner_entropy",
                               "finish_spread")},
            "by_stage": {
                metric: V.aggregate_race_macro(r6_records, metric,
                                               group_key="stage")
                for metric in ("winner_log_loss", "brier",
                               "expected_finish_mae", "rps")},
            "by_season": {
                metric: V.aggregate_race_macro(r6_records, metric,
                                               group_key="season")
                for metric in ("winner_log_loss", "brier",
                               "expected_finish_mae", "rps")},
            "baseline_race_macro": {
                name: V.aggregate_race_macro(records, "winner_log_loss")
                for name, records in baseline_records.items()},
            "mc_uncertainty": {
                "mean_mc_se_actual_winner": V.aggregate_race_macro(
                    r6_records, "mc_se_actual_winner"),
            },
        }
        per_race = {}
        for record in r6_records:
            key = (record["season"], record["race_id"])
            per_race.setdefault(key, []).append(record)
        bootstrap = {
            metric: V.race_level_bootstrap(
                [float(np.mean([r[metric] for r in records
                                if r.get(metric) is not None]))
                 for records in per_race.values()])
            for metric in ("winner_log_loss", "brier", "expected_finish_mae",
                           "rps")
        }
        report["aggregates"]["bootstrap"] = bootstrap
        failures = {}
        for label, metric in (("highest_winner_log_loss",
                               "winner_log_loss"),
                              ("largest_expected_finish_mae",
                               "expected_finish_mae"),
                              ("highest_brier", "brier")):
            ranked = sorted(
                r6_records,
                key=lambda r: (r.get(metric) is None,
                               -(r.get(metric) or 0.0)))[:5]
            failures[label] = [
                {k: r[k] for k in
                 ("season", "race_id", "stage", "field_size", "leader_lap",
                  "scheduled_laps", metric)}
                for r in ranked]
        report["failure_analysis"] = failures

    report["runtime_s"] = time.perf_counter() - started
    report["peak_rss_mb"] = peak_rss_mb()

    out_path = out_dir / "r7_validation.json"
    out_path.write_text(json.dumps(_jsonable(report), indent=2,
                                   sort_keys=True) + "\n", encoding="utf-8")
    protocol_path = out_dir / "r7_protocol_v1.json"
    protocol_path.write_text(
        json.dumps(_jsonable({"protocol": protocol.to_dict(),
                              "protocol_identity": protocol.identity()}),
                   indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"wrote {out_path}")
    print(f"wrote {protocol_path}")
    print(f"states={len(per_state)} exclusions={len(report['exclusions'])} "
          f"runtime={report['runtime_s']:.1f}s")
    return 0


def metrics_count(args) -> int:
    return args.counts[-1] if args.counts else 1000


if __name__ == "__main__":
    raise SystemExit(main())
