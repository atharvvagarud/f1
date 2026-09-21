"""Phase-6 R7 focused tests: historical validation + calibration + freeze.

R7 is evaluation-only. These tests pin the frozen protocol identity and
selection rules, the pure metric definitions (including the RPS
normalization), calibration/ECE, Monte Carlo standard error and race-level
bootstrap, pit-behaviour comparison, the residual-sampler audit, the
diagnostic variance-matched parameter set, the temporal adversarial suite,
the 2025 firewall, the R7-BUG-1 batch/scalar diagnostic parity fix, and the
module/AST firewalls. Real-data tests use only the frozen Phase-1..5 replay
seam and the explicit R3 artifacts.
"""

from __future__ import annotations

import ast
import functools
import json
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from v2 import replay as RP
from v2.race_state_reconstruction import RaceStateReconstructor
from v2.replay_reconstruction import ReplayReconstructor
from v2.simulation import validation as V
from v2.simulation.adapter import from_race_state
from v2.simulation.config import Assumptions, SimulationConfig
from v2.simulation.errors import (
    SimulationContractError,
    SimulationValidationError,
)
from v2.simulation.monte_carlo import MonteCarloEngine
from v2.simulation.params import load_simulation_parameters

from test_v2_phase6_r6 import make_params

REPO_ROOT = Path(__file__).resolve().parents[1]
VALIDATION_PATH = REPO_ROOT / "v2" / "simulation" / "validation.py"
SCRIPT_PATH = REPO_ROOT / "scripts" / "validate_phase6_simulation.py"
ARTIFACT_2024 = (REPO_ROOT / "data" / "v2" / "simulation" / "params"
                 / "r3-v1__through-2024")
D9 = (str(REPO_ROOT) + "/data/v2/processed/driver_lap_state_d9/season="
      "{season}/driver_lap_state_d9__d9-{season}.parquet")
RESULTS = (str(REPO_ROOT) + "/data/v2/processed/results/season={season}/"
           "results__{race}.parquet")
RACES = (str(REPO_ROOT) + "/data/v2/processed/races/season={season}/"
         "races__{race}.parquet")


def _dist(observed_max, *, probs=(0.5,), quants=(20.0,), observed_min=1.0,
          std=None):
    from v2.simulation.params import SupportEntry
    return SupportEntry(
        group_key="g", sample_count=1000, support_level="strong",
        fallback_level="global", probabilities=probs,
        quantile_values=quants, observed_min=observed_min,
        observed_max=observed_max, std=std)


# ===========================================================================
# R7-B  Protocol identity / freeze.
# ===========================================================================

def test_protocol_identity_is_deterministic_and_complete():
    protocol = V.default_protocol()
    assert protocol.identity() == V.default_protocol().identity()
    payload = protocol.to_dict()
    assert payload["no_2025"] is True
    assert 2025 in payload["excluded_seasons"]
    assert tuple(payload["evaluation_seasons"]) == (2020, 2021, 2022, 2023,
                                                    2024)
    assert payload["parameter_cutoff_rule"] == (
        "through_season = evaluation_season - 1")
    assert payload["simulation_count_broad"] == 1000
    assert payload["simulation_count_calibration"] == 10000
    assert payload["checkpoint_radius_fraction"] == 0.10
    assert payload["checkpoint_radius_min_laps"] == 3
    assert payload["baselines"] == list(V.R7_BASELINES)
    assert protocol.winner_log_epsilon == 1e-6
    assert protocol.position_log_epsilon == 1e-6


def test_protocol_version_is_pinned():
    assert V.R7_VALIDATION_VERSION == "r7-validation-v1"


def test_selection_rules_are_frozen_constants():
    assert V.R7_STAGE_FRACTIONS == (("EARLY", 0.25), ("MID", 0.50),
                                    ("LATE", 0.75))
    assert V.R7_MASTER_SEED == 20240101
    assert V.R7_CALIBRATION_BINS[0] == 0.0
    assert V.R7_CALIBRATION_BINS[-1] == 1.0
    assert tuple(sorted(V.R7_CALIBRATION_BINS)) == V.R7_CALIBRATION_BINS


# ===========================================================================
# R7-E/F/G  Deterministic selection.
# ===========================================================================

def test_systematic_race_selection_deterministic_and_spread():
    ids = [f"2023-r{index:02d}-R" for index in range(1, 23)]
    first = V.systematic_race_selection(ids, 6)
    assert first == V.systematic_race_selection(reversed(ids), 6)
    assert tuple(sorted(first)) == first
    assert 4 <= len(first) <= 8


def test_systematic_race_selection_rejects_bad_target():
    with pytest.raises(SimulationValidationError):
        V.systematic_race_selection(["a"], 0)


def test_stage_target_laps_uses_leader_progress():
    assert V.stage_target_laps(57) == {"EARLY": 14, "MID": 28, "LATE": 43}
    assert V.stage_target_laps(1) == {"EARLY": 1, "MID": 1, "LATE": 1}


def test_checkpoint_search_order_tie_break():
    frames = [(5, 10), (3, 10), (9, 11), (1, 9)]
    order = V.checkpoint_search_order(frames, 10)
    assert order[0] == (3, 10)  # |0| then lower leader lap then frame index
    assert order[1] == (5, 10)
    assert order[2][1] == 9
    assert order[3][1] == 11


def test_checkpoint_radius_is_frozen_and_bounded():
    assert V.checkpoint_radius_laps(57) == 6  # round(0.10 * 57)
    assert V.checkpoint_radius_laps(10) == 3  # min-laps floor
    frames = [(1, 2), (2, 30), (3, 28), (4, 40)]
    order = V.checkpoint_search_order(frames, 28, radius_laps=3)
    assert order == ((3, 28), (2, 30))
    assert V.checkpoint_search_order(frames, 35, radius_laps=3) == ()


def test_select_checkpoint_returns_nearest_supported():
    candidates = [
        {"frame_index": 3, "leader_lap": 10, "supported": False},
        {"frame_index": 5, "leader_lap": 10, "supported": True},
    ]
    chosen, reason = V.select_checkpoint(candidates, 10)
    assert reason is None and chosen["frame_index"] == 5
    missing, reason = V.select_checkpoint(
        [{"frame_index": 1, "leader_lap": 1, "supported": False}], 1)
    assert missing is None and reason == "no_supported_state"


# ===========================================================================
# R7-I  Historical-truth separation.
# ===========================================================================

def _truth_rows(positions, dnf=(), grid=None):
    rows = []
    position = 0
    for index, driver in enumerate(positions, start=1):
        is_dnf = driver in dnf
        if not is_dnf:
            position += 1
        rows.append({
            "driver_id": driver,
            "position_final": None if is_dnf else position,
            "dnf_flag": is_dnf,
            "winner_flag": position == 1 and not is_dnf,
            "grid_position": (index if grid is None else grid[driver]),
        })
    return rows


def test_historical_truth_separates_dnf_and_picks_winner():
    rows = _truth_rows(["a", "b", "c"], dnf=("b",))
    truth = V.historical_truth(rows, ["a", "b", "c"])
    assert truth["winner_driver_id"] == "a"
    assert truth["position_by_driver"] == {"a": 1, "b": None, "c": 2}
    assert truth["dnf_by_driver"]["b"] is True
    assert truth["classified_driver_ids"] == ("a", "c")


def test_historical_truth_requires_full_roster():
    rows = _truth_rows(["a"])
    with pytest.raises(SimulationValidationError):
        V.historical_truth(rows, ["a", "b"])


def test_historical_truth_requires_exactly_one_winner():
    rows = _truth_rows(["a", "b"])
    for row in rows:
        row["winner_flag"] = True
    with pytest.raises(SimulationValidationError):
        V.historical_truth(rows, ["a", "b"])


def test_historical_truth_does_not_mutate_input_rows():
    rows = _truth_rows(["a", "b"])
    before = [dict(row) for row in rows]
    V.historical_truth(rows, ["a", "b"])
    assert rows == before


def test_is_contemporaneous_rejects_stale_driver():
    from v2.simulation.state import (
        DriverSimState, SimulationEnvironment, SimulationState)
    fresh = DriverSimState("a", lap_number=20, race_time_s=1800.0,
                           observation_age_s=5.0)
    stale = DriverSimState("b", lap_number=5, race_time_s=500.0,
                           observation_age_s=4000.0)
    environment = SimulationEnvironment(track_state="all_clear")
    ok = SimulationState(race_id="r", scheduled_laps=50, leader_laps_done=20,
                         simulation_time_s=1800.0, drivers=(fresh,),
                         environment=environment)
    result = V.is_contemporaneous(ok, 90.0, lap_budget=3.0)
    assert result["contemporaneous"] is True
    assert result["bound_s"] == pytest.approx(270.0)

    bad = SimulationState(race_id="r", scheduled_laps=50, leader_laps_done=20,
                          simulation_time_s=1800.0, drivers=(fresh, stale),
                          environment=environment)
    result = V.is_contemporaneous(bad, 90.0, lap_budget=3.0)
    assert result["contemporaneous"] is False
    assert result["offenders"] == (("b", 4000.0),)


# ===========================================================================
# R7-J/K/L/M  Metrics.
# ===========================================================================

def test_current_order_is_free_air_order():
    from v2.simulation.state import (
        DriverSimState, SimulationEnvironment, SimulationState)
    drivers = (
        DriverSimState("a", lap_number=5, race_time_s=100.0),
        DriverSimState("b", lap_number=5, race_time_s=90.0),
        DriverSimState("c", lap_number=4, race_time_s=80.0),
    )
    state = SimulationState(
        race_id="r", scheduled_laps=10, leader_laps_done=5,
        simulation_time_s=100.0, drivers=drivers,
        environment=SimulationEnvironment(track_state="all_clear"))
    assert V.current_order(state) == ("b", "a", "c")


def test_winner_log_loss_clips_impossible_outcome():
    assert V.winner_log_loss({"a": 1.0, "b": 0.0}, "a") == 0.0
    assert V.winner_log_loss({"a": 0.0, "b": 1.0}, "b") == 0.0
    clipped = V.winner_log_loss({"a": 0.0, "b": 1.0}, "a")
    assert clipped == pytest.approx(-math.log(V.R7_WINNER_LOG_EPSILON))


def test_brier_score_is_mean_over_field():
    assert V.brier_score({"a": 1.0, "b": 0.0}, "a") == 0.0
    assert V.brier_score({"a": 0.0, "b": 1.0}, "a") == pytest.approx(2 / 2)


def test_top_k_winner_accuracy():
    probs = {"a": 0.2, "b": 0.5, "c": 0.3}
    assert V.top_k_winner_accuracy(probs, "b", 1) is True
    assert V.top_k_winner_accuracy(probs, "c", 2) is True
    assert V.top_k_winner_accuracy(probs, "a", 2) is False


def test_ranked_probability_score_known_values():
    uniform = {position: 1.0 / 20 for position in range(1, 21)}
    assert V.ranked_probability_score(uniform, 1) == pytest.approx(0.325)
    assert V.ranked_probability_score(uniform, 20) == pytest.approx(0.325)
    peaked = {p: (0.9 if p == 1 else 0.1 / 19) for p in range(1, 21)}
    assert V.ranked_probability_score(peaked, 1) < 0.01
    assert V.ranked_probability_score(peaked, 20) > 0.8


def test_ranked_probability_score_validates_support():
    with pytest.raises(SimulationValidationError):
        V.ranked_probability_score({1: 1.0, 3: 0.0}, 1)
    with pytest.raises(SimulationValidationError):
        V.ranked_probability_score({1: 1.0}, 2)


def test_position_log_score_clip():
    assert V.position_log_score({1: 1.0, 2: 0.0}, 1) == 0.0
    assert V.position_log_score({1: 0.0, 2: 1.0}, 1) == pytest.approx(
        -math.log(V.R7_POSITION_LOG_EPSILON))


def test_expected_finish_mae():
    expected = {"a": 1.0, "b": 3.5, "c": 2.0}
    actual = {"a": 1, "b": 2, "c": 3}
    assert V.expected_finish_mae(expected, actual, ["a", "b", "c"]) == (
        pytest.approx((0.0 + 1.5 + 1.0) / 3))


def test_spearman_perfect_and_reversed():
    actual = {"a": 1, "b": 2, "c": 3}
    assert V.spearman_rank_correlation({"a": 1.0, "b": 2.0, "c": 3.0},
                                       actual, ["a", "b", "c"]) == (
        pytest.approx(1.0))
    assert V.spearman_rank_correlation({"a": 3.0, "b": 2.0, "c": 1.0},
                                       actual, ["a", "b", "c"]) == (
        pytest.approx(-1.0))


# ===========================================================================
# R7-N  Calibration.
# ===========================================================================

def test_calibration_bins_and_ece():
    bins = V.calibration_bins([0.0, 0.5, 0.5, 1.0], [0, 0, 1, 1])
    assert sum(b["count"] for b in bins) == 4
    assert V.expected_calibration_error(bins) == pytest.approx(0.0, abs=1e-9)
    biased = V.calibration_bins([0.9, 0.9, 0.9, 0.9], [0, 0, 0, 0])
    assert V.expected_calibration_error(biased) == pytest.approx(0.9)


def test_calibration_bins_reject_out_of_range():
    with pytest.raises(SimulationValidationError):
        V.calibration_bins([1.5], [1])


# ===========================================================================
# R7-O/W  Uncertainty.
# ===========================================================================

def test_monte_carlo_standard_error():
    assert V.monte_carlo_standard_error(0.25, 100) == pytest.approx(0.0433,
                                                                    rel=1e-3)
    with pytest.raises(SimulationValidationError):
        V.monte_carlo_standard_error(0.5, 0)


def test_race_level_bootstrap_is_seeded_and_brackets_mean():
    values = [0.4, 0.5, 0.6, 0.7, 0.8]
    first = V.race_level_bootstrap(values, replicates=200, seed=42)
    second = V.race_level_bootstrap(values, replicates=200, seed=42)
    assert first == second
    assert first["ci95_low"] <= first["mean"] <= first["ci95_high"]


# ===========================================================================
# R7-Q  Pit behaviour.
# ===========================================================================

def test_pit_behaviour_metrics():
    metrics = V.pit_behaviour_metrics([0, 1, 2, 2], [1, 1, 2, 3])
    assert metrics["simulated_mean"] == pytest.approx(1.25)
    assert metrics["historical_mean"] == pytest.approx(1.75)
    assert metrics["mean_difference"] == pytest.approx(-0.5)
    assert 0.0 <= metrics["stop_count_total_variation"] <= 1.0


def test_pit_behaviour_metrics_rejects_empty():
    with pytest.raises(SimulationValidationError):
        V.pit_behaviour_metrics([], [1])


# ===========================================================================
# R7-S/T  Residual sampler audit.
# ===========================================================================

def test_piecewise_linear_variance_uniform():
    # Q(u) = a + (b-a)u is the uniform quantile function; var = (b-a)^2/12.
    xp = (0.0, 0.25, 0.5, 0.75, 1.0)
    fp = (0.0, 0.25, 0.5, 0.75, 1.0)
    assert V.piecewise_linear_variance(xp, fp) == pytest.approx(1.0 / 12.0)


def test_variance_matched_parameter_set_reduces_grid_variance():
    params = make_params(residual=_dist(
        40.0, probs=(0.01, 0.5, 0.99), quants=(-4.0, 0.0, 4.0),
        observed_min=-20.0, std=1.5))
    matched = V.variance_matched_parameter_set(params)
    original = params.family("lap_residual_distribution_s").entries[
        "2018-2021"]
    scaled = matched.family("lap_residual_distribution_s").entries[
        "2018-2021"]
    xp = (0.0,) + tuple(original.probabilities) + (1.0,)
    fp = (original.observed_min,) + tuple(original.quantile_values) \
        + (original.observed_max,)
    grid_std = math.sqrt(V.piecewise_linear_variance(xp, fp))
    xp2 = (0.0,) + tuple(scaled.probabilities) + (1.0,)
    fp2 = (scaled.observed_min,) + tuple(scaled.quantile_values) \
        + (scaled.observed_max,)
    matched_std = math.sqrt(V.piecewise_linear_variance(xp2, fp2))
    assert matched_std == pytest.approx(original.std, rel=1e-9)
    assert matched_std < grid_std
    # Production parameters are untouched (diagnostic copy only).
    assert original.observed_max == 40.0


# ===========================================================================
# R7-K/P  Aggregation.
# ===========================================================================

def test_aggregate_race_macro_and_stage_grouping():
    records = [
        {"winner_log_loss": 0.2, "stage": "EARLY"},
        {"winner_log_loss": 0.4, "stage": "EARLY"},
        {"winner_log_loss": 0.6, "stage": "LATE"},
    ]
    assert V.aggregate_race_macro(records, "winner_log_loss")["mean"] == (
        pytest.approx(0.4))
    grouped = V.aggregate_race_macro(records, "winner_log_loss", "stage")
    assert grouped["EARLY"]["mean"] == pytest.approx(0.3)
    assert grouped["LATE"]["mean"] == pytest.approx(0.6)


# ===========================================================================
# Firewalls / 2025.
# ===========================================================================

def test_validation_module_import_firewall():
    tree = ast.parse(VALIDATION_PATH.read_text(encoding="utf-8"))
    forbidden = ("pandas", "v2.prediction", "v2.model_lab", "v2.replay",
                 "v2.race_state", "fastapi", "v2.api", "sklearn", "scipy")
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    for name in imported:
        for banned in forbidden:
            assert not (name == banned or name.startswith(banned + ".")), (
                f"validation.py must not import {name}")


def test_validation_module_runs_without_pandas_imported():
    code = (
        "import sys;"
        "import v2.simulation.validation as v;"
        "assert 'pandas' not in sys.modules;"
        "assert 'v2.prediction' not in sys.modules;"
        "print(v.default_protocol().identity()[:8])")
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, cwd=str(REPO_ROOT))
    assert proc.returncode == 0, proc.stderr
    assert proc.stdout.strip()


def test_validation_script_rejects_2025_and_earlier_seasons():
    from scripts.validate_phase6_simulation import main
    assert main(["--dry-run", "--seasons", "2025"]) == 2
    assert main(["--dry-run", "--seasons", "2019"]) == 2
    assert main(["--dry-run", "--seasons", "2018"]) == 2


def test_validation_script_requires_limit_for_nondefault_seasons():
    from scripts.validate_phase6_simulation import main
    assert main(["--dry-run", "--seasons", "2023"]) == 2


# ===========================================================================
# R7-BUG-1  Batch/scalar pit diagnostics parity.
# ===========================================================================

@functools.lru_cache(maxsize=None)
def _load_race(season, race_id):
    states = pd.read_parquet(D9.format(season=season))
    states = states[states["race_id"] == race_id].copy()
    results = pd.read_parquet(RESULTS.format(season=season, race=race_id))
    races = pd.read_parquet(RACES.format(season=season, race=race_id))
    scheduled = int(races["total_laps_scheduled"].iloc[0])
    return states, results, scheduled


@functools.lru_cache(maxsize=None)
def _service(season, race_id):
    states, results, scheduled = _load_race(season, race_id)
    meta = {race_id: {"scheduled_laps": scheduled}}
    return ReplayReconstructor(
        RP.build_replay_timeline(states),
        RaceStateReconstructor(states, results, race_meta=meta))


def _frame_index(service, driver, lap):
    for frame in service.timeline.frames:
        if (frame.anchor_driver_id == driver
                and frame.anchor_lap_number == lap):
            return frame.frame_index
    raise AssertionError(f"anchor {(driver, lap)} not found")


def _real_state(season, race_id, driver, lap, service=None):
    service = service or _service(season, race_id)
    index = _frame_index(service, driver, lap)
    return from_race_state(service.state_at(index), anchor_frame_index=index)


@pytest.fixture(scope="module")
def real_params():
    return load_simulation_parameters(ARTIFACT_2024)


def test_batch_scalar_pit_diagnostics_parity_mid_race(real_params):
    state = _real_state(2022, "2022-r01-R", "perez", 30)
    config = SimulationConfig(simulation_count=50, master_seed=1,
                              pit_dynamics_enabled=True)
    engine = MonteCarloEngine(chunk_size=16)
    engine.run(state, real_params, config, Assumptions(),
               collect_diagnostics=True)
    batch_diag = engine.last_diagnostics
    engine.run_scalar(state, real_params, config, Assumptions(),
                      collect_diagnostics=True)
    scalar_diag = engine.last_diagnostics
    assert batch_diag.mean_pits_per_driver == pytest.approx(
        scalar_diag.mean_pits_per_driver, abs=1e-9)
    assert batch_diag.pit_count_distribution == \
        scalar_diag.pit_count_distribution
    initial = np.mean([driver.pit_count for driver in state.drivers])
    assert batch_diag.mean_pits_per_driver >= initial


# ===========================================================================
# R7-AG  Temporal adversarial suite (implemented test, not a proof).
# ===========================================================================

def test_no_leakage_under_future_poisoning():
    states, results, scheduled = _load_race(2023, "2023-r01-R")
    service = _service(2023, "2023-r01-R")
    index = _frame_index(service, "alonso", 28)
    baseline_state = from_race_state(service.state_at(index),
                                     anchor_frame_index=index)
    leader_lap = baseline_state.leader_laps_done

    poisoned_states = states.copy()
    future = poisoned_states["lap_number"] > leader_lap
    poisoned_states.loc[future, "compound"] = "WET"
    poisoned_states.loc[future, "tyre_life"] = 999
    poisoned_states.loc[future, "pit_in_s"] = 1.0
    poisoned_states.loc[future, "pit_out_s"] = 1.0
    poisoned_states.loc[future, "track_state"] = "red_flag"
    poisoned_states.loc[future, "lap_time_s"] = 1.0

    poisoned_results = results.copy()
    poisoned_results["position_final"] = (
        len(poisoned_results) - poisoned_results.index)
    poisoned_results["winner_flag"] = poisoned_results["position_final"] == 1
    poisoned_meta = {"2023-r01-R": {"scheduled_laps": scheduled}}
    poisoned_service = ReplayReconstructor(
        RP.build_replay_timeline(poisoned_states),
        RaceStateReconstructor(poisoned_states, poisoned_results,
                               race_meta=poisoned_meta))
    poisoned_state = from_race_state(
        poisoned_service.state_at(index), anchor_frame_index=index)

    # Simulation input is unchanged under strictly-future poisoning.
    assert poisoned_state.identity() == baseline_state.identity()
    # Evaluation truth *is* allowed to change (it is evaluation-only).
    baseline_truth = V.historical_truth(results.to_dict("records"),
                                        baseline_state.roster_driver_ids)
    poisoned_truth = V.historical_truth(poisoned_results.to_dict("records"),
                                        poisoned_state.roster_driver_ids)
    assert poisoned_truth["winner_driver_id"] != \
        baseline_truth["winner_driver_id"]


# ===========================================================================
# R7-AD  Deterministic validation artifact.
# ===========================================================================

def test_dry_run_validation_artifact(tmp_path):
    code = (
        "import sys;"
        f"sys.argv=['validate','--dry-run','--limit','1','--seasons','2023',"
        f"'--out-dir',{str(tmp_path)!r}];"
        "from scripts.validate_phase6_simulation import main;"
        "raise SystemExit(main(sys.argv[1:]))")
    proc = subprocess.run([sys.executable, "-c", code],
                          capture_output=True, text=True, cwd=str(REPO_ROOT))
    assert proc.returncode == 0, proc.stderr
    report = json.loads((tmp_path / "r7_validation.json").read_text())
    protocol = json.loads((tmp_path / "r7_protocol_v1.json").read_text())
    assert protocol["protocol_identity"] == V.default_protocol().identity()
    assert report["protocol_identity"] == V.default_protocol().identity()
    assert len(report["state_records"]) >= 1
    assert report["races"][0]["race_id"] == "2023-r01-R"
    for record in report["state_records"]:
        assert record["state_identity"]
        assert record["parameter_hash"]
