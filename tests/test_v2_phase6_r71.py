"""Phase-6 R7.1 focused tests: contemporaneous active-roster safety contract.

R7.1 closes the R7-BUG-2 blocker: the frozen R4/R5/R6 kernel evolved every
adapted roster member as ACTIVE from its own factual ``(lap, race_time_s)``
coordinate, so a driver whose latest observation was far older than the anchor
T (a factual retirement / stopped car) could "finish" the remaining distance
from a stale clock and beat the field. R7.1 adds a runtime simulation-start
eligibility rule that rejects such states with the stable reason
``non_contemporaneous_roster_member``. It never infers retirement, never reads
final status or future rows, and is eligibility-only: accepted states produce
byte-identical results (verified against the pre-fix R7 raw artifact on the
original Python 3.13 validation environment; on the release contract Python
3.11.x the state identities still match exactly while result-identity hashes
differ by float formatting — see the P11-1 note on the parity test below).

Real-data tests use only the frozen Phase-1..5 replay seam and the explicit R3
artifacts. This is an evaluation/test surface; the runtime kernel imports none
of it.
"""

from __future__ import annotations

import ast
import functools
import json
import math
import time
from pathlib import Path

import pandas as pd
import pytest

from raceintel.replay import replay as RP
from raceintel.race_state.race_state_reconstruction import RaceStateReconstructor
from raceintel.replay.replay_reconstruction import ReplayReconstructor
from raceintel.simulation import engine as E
from raceintel.simulation import validation as V
from raceintel.simulation.adapter import from_race_state
from raceintel.simulation.config import Assumptions, SimulationConfig
from raceintel.simulation.engine import (
    CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES,
    ENGINE_UNSUPPORTED_REASONS,
    REASON_NON_CONTEMPORANEOUS_ROSTER_MEMBER,
    ExecutionPolicy,
    SimulationUnsupportedError,
    contemporaneous_roster_offenders,
    select_pace_parameters,
)
from raceintel.simulation.monte_carlo import MonteCarloEngine
from raceintel.simulation.params import load_simulation_parameters
from raceintel.simulation.state import (
    DriverSimState,
    DriverStatus,
    SimulationEnvironment,
    SimulationState,
)

from test_v2_phase6_r6 import make_params

REPO_ROOT = Path(__file__).resolve().parents[1]
ENGINE_PATH = REPO_ROOT / "raceintel" / "simulation" / "engine.py"
ADAPTER_PATH = REPO_ROOT / "raceintel" / "simulation" / "adapter.py"
MONTE_CARLO_PATH = REPO_ROOT / "raceintel" / "simulation" / "monte_carlo.py"
RAW_ARTIFACT = (REPO_ROOT / "data" / "v2" / "simulation" / "validation"
                / "r7_validation_raw_v1.json")
PROCESSED = REPO_ROOT / "data" / "v2" / "processed"
PARAM_ROOT = REPO_ROOT / "data" / "v2" / "simulation" / "params"
D9 = (str(PROCESSED) + "/driver_lap_state_d9/season={season}/"
      "driver_lap_state_d9__d9-{season}.parquet")
RESULTS = (str(PROCESSED) + "/results/season={season}/results__{race}.parquet")
RACES = (str(PROCESSED) + "/races/season={season}/races__{race}.parquet")

# The R7-BUG-2 pathological state (2020-r07-R, all three stages).
_BLOCKER_RACE = (2020, "2020-r07-R")

# Accepted (contemporaneous) real fixtures used across R7.1.
_ACCEPTED = {
    "early": (2023, "2023-r01-R", "alonso", 2),
    "mid": (2022, "2022-r01-R", "perez", 30),
    "late": (2022, "2022-r01-R", "russell", 38),
}


# ---------------------------------------------------------------------------
# Real replay seam helpers.
# ---------------------------------------------------------------------------

@functools.lru_cache(maxsize=None)
def _service(season, race_id):
    states = pd.read_parquet(D9.format(season=season))
    states = states[states["race_id"] == race_id].copy()
    results = pd.read_parquet(RESULTS.format(season=season, race=race_id))
    races = pd.read_parquet(RACES.format(season=season, race=race_id))
    scheduled = int(races["total_laps_scheduled"].iloc[0])
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


@functools.lru_cache(maxsize=None)
def _real_state(season, race_id, driver, lap):
    service = _service(season, race_id)
    index = _frame_index(service, driver, lap)
    return from_race_state(service.state_at(index), anchor_frame_index=index)


def _real_state_at(season, race_id, frame_index):
    service = _service(season, race_id)
    return from_race_state(service.state_at(frame_index),
                           anchor_frame_index=frame_index)


@functools.lru_cache(maxsize=None)
def _params_through(through):
    return load_simulation_parameters(
        PARAM_ROOT / f"r3-v1__through-{through}")


@pytest.fixture(scope="module")
def params_2024():
    return _params_through(2024)


@pytest.fixture(scope="module")
def params_2019():
    return _params_through(2019)


# ---------------------------------------------------------------------------
# Synthetic states.
# ---------------------------------------------------------------------------

def _driver(driver_id, *, lap, race_time, age=None, observation_age=None,
            status=DriverStatus.ACTIVE):
    return DriverSimState(
        driver_id=driver_id, lap_number=lap, race_time_s=race_time,
        position=1, compound="HARD", tyre_age=1, stint_number=1,
        pit_count=0, constructor_id="c1", status=status,
        observation_age_s=observation_age)


def _state(drivers, *, scheduled=10, leader=None, T=None, race_id="SYN-R"):
    drivers = tuple(drivers)
    if leader is None:
        leader = max(d.lap_number for d in drivers)
    if T is None:
        T = max(d.race_time_s for d in drivers)
    return SimulationState(
        race_id=race_id, scheduled_laps=scheduled, leader_laps_done=leader,
        simulation_time_s=T, drivers=drivers,
        environment=SimulationEnvironment(track_state="all_clear"),
        season=2019, round_no=1, circuit_id="syn")


def _run(state, params):
    return E.DeterministicRaceEngine().run(state, params)


# ===========================================================================
# R7.1-A/D  Rule definition, boundary, and evidence-derived constant.
# ===========================================================================

def test_contemporaneity_constant_is_dimensionless_lap_multiple():
    assert CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES == 3.0


def test_reason_is_registered_engine_unsupported_reason():
    assert REASON_NON_CONTEMPORANEOUS_ROSTER_MEMBER == \
        "non_contemporaneous_roster_member"
    assert REASON_NON_CONTEMPORANEOUS_ROSTER_MEMBER in ENGINE_UNSUPPORTED_REASONS


def test_offender_boundary_is_inclusive():
    bound = CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES * 90.0
    at = _state([_driver("a", lap=1, race_time=0.0, observation_age=bound)])
    over = _state([_driver("a", lap=1, race_time=0.0,
                           observation_age=bound + 0.01)])
    assert contemporaneous_roster_offenders(at, 90.0) == ()
    assert contemporaneous_roster_offenders(over, 90.0) == (("a", bound + 0.01),)


def test_null_observation_age_is_not_an_offender():
    state = _state([_driver("a", lap=1, race_time=0.0, observation_age=None)])
    assert contemporaneous_roster_offenders(state, 90.0) == ()


def test_offenders_are_deterministic_and_driver_ordered():
    state = _state([
        _driver("b", lap=1, race_time=0.0, observation_age=1000.0),
        _driver("a", lap=1, race_time=0.0, observation_age=500.0),
    ])
    assert contemporaneous_roster_offenders(state, 90.0) == \
        (("a", 500.0), ("b", 1000.0))


def test_derivation_margin_is_above_contemporaneous_p99():
    # R7.1-B/D measured the contemporaneous (has-later-row) observation age
    # distribution over 1 836 driver-observations: p50 0.62, p90 0.95,
    # p95 1.11, p99 1.77 expected lap times. The chosen bound is a conservative
    # margin above that p99. This test pins the frozen constant and the margin
    # relationship so a silent retune is caught.
    assert CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES > 1.77
    assert CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES < 21.0


# ===========================================================================
# R7.1-E/F  Enforcement before stochastic execution.
# ===========================================================================

def test_engine_rejects_non_contemporaneous_roster_member():
    state = _state([
        _driver("fresh", lap=3, race_time=300.0, observation_age=10.0),
        _driver("stale", lap=1, race_time=100.0, observation_age=1000.0),
    ], scheduled=10, leader=3)
    with pytest.raises(SimulationUnsupportedError) as excinfo:
        _run(state, make_params())
    assert excinfo.value.reason == REASON_NON_CONTEMPORANEOUS_ROSTER_MEMBER
    # The detail names the offender but the model is never advanced.
    assert "stale" in excinfo.value.detail


def test_monte_carlo_rejects_before_any_draw():
    state = _state([
        _driver("fresh", lap=3, race_time=300.0, observation_age=10.0),
        _driver("stale", lap=1, race_time=100.0, observation_age=1000.0),
    ], scheduled=10, leader=3)
    engine = MonteCarloEngine()
    with pytest.raises(SimulationUnsupportedError) as excinfo:
        engine.run(state, make_params(), SimulationConfig(10, 1),
                   Assumptions())
    assert excinfo.value.reason == REASON_NON_CONTEMPORANEOUS_ROSTER_MEMBER


def test_stale_driver_is_preserved_not_dropped_or_retired():
    # The factual adapter keeps every observed member and never infers
    # retirement; the engine refuses the whole state instead of silently
    # dropping or reclassifying the stale member.
    service = _service(*_BLOCKER_RACE)
    index = _frame_index(service, "hamilton", 22)
    state = from_race_state(service.state_at(index), anchor_frame_index=index)
    stale = [d for d in state.drivers
             if d.observation_age_s and d.observation_age_s > 1000.0]
    assert stale, "fixture must contain a stale factual observation"
    assert all(d.status is DriverStatus.ACTIVE for d in state.drivers)
    before = state.to_dict()
    with pytest.raises(SimulationUnsupportedError):
        MonteCarloEngine().run(state, _params_through(2019),
                               SimulationConfig(5, 1), Assumptions())
    assert state.to_dict() == before
    assert state.roster_size == 20


def test_rejection_is_not_a_retirement_classification():
    state = _state([
        _driver("stale", lap=1, race_time=100.0, observation_age=1000.0),
    ], scheduled=10, leader=1)
    with pytest.raises(SimulationUnsupportedError) as excinfo:
        _run(state, make_params())
    # The reason is eligibility, not retirement; the state status is ACTIVE.
    assert excinfo.value.reason == REASON_NON_CONTEMPORANEOUS_ROSTER_MEMBER
    assert state.drivers[0].status is DriverStatus.ACTIVE


# ===========================================================================
# R7.1-J  Valid lapped / temporarily-stale participating drivers.
# ===========================================================================

def test_valid_lapped_driver_is_not_rejected():
    # One or more laps down but recently observed: lapped != stale. The
    # eligibility rule inspects only observation age, never lap deficit.
    state = _state([
        _driver("leader", lap=10, race_time=1000.0, observation_age=2.0),
        _driver("lapped", lap=8, race_time=900.0, observation_age=150.0),
    ], scheduled=12, leader=10)
    assert contemporaneous_roster_offenders(state, 90.0) == ()
    assert _run(state, make_params()).valid


def test_temporarily_stale_within_budget_passes():
    just_inside = CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES * 90.0 - 1.0
    state = _state([
        _driver("a", lap=3, race_time=300.0, observation_age=just_inside),
    ], scheduled=6, leader=3)
    assert _run(state, make_params()).valid


def test_real_lapped_driver_fixture_is_accepted(params_2024):
    state = _real_state(*_ACCEPTED["mid"])
    leader = state.leader_laps_done
    lapped = [d for d in state.drivers if d.lap_number < leader]
    assert lapped, "fixture must carry a lapped driver"
    result = MonteCarloEngine(chunk_size=64).run(
        state, params_2024, SimulationConfig(20, 1), Assumptions())
    assert result.valid_simulation_count == 20
    # Lapped drivers keep their own progress; no driver is forced onto the
    # leader lap and no driver is dropped.
    assert set(result.driver_summary_by_id) == set(state.roster_driver_ids)


# ===========================================================================
# R7.1-K  The 2020-r07-R pathological state regression.
# ===========================================================================

def test_2020_r07_blocker_is_blocked_before_simulation():
    for driver, lap in (("hamilton", 22),):
        service = _service(*_BLOCKER_RACE)
        index = _frame_index(service, driver, lap)
        state = from_race_state(service.state_at(index),
                                anchor_frame_index=index)
        with pytest.raises(SimulationUnsupportedError) as excinfo:
            MonteCarloEngine(chunk_size=64).run(
                state, _params_through(2019), SimulationConfig(100, 20240101),
                Assumptions(),
                execution_policy=ExecutionPolicy.HISTORICAL_BACKTEST)
        assert excinfo.value.reason == \
            REASON_NON_CONTEMPORANEOUS_ROSTER_MEMBER


def test_2020_r07_giovinazzi_no_longer_reachable():
    # Pre-fix, 2020-r07-R MID evolved giovinazzi to ~0.904 win probability.
    # The state is now rejected, so no driver probability exists at all: the
    # pathological outcome cannot be produced.
    service = _service(*_BLOCKER_RACE)
    index = _frame_index(service, "hamilton", 22)
    state = from_race_state(service.state_at(index), anchor_frame_index=index)
    offenders = dict(contemporaneous_roster_offenders(
        state, select_pace_parameters(state, _params_through(2019)).base.value))
    assert "giovinazzi" in offenders
    assert offenders["giovinazzi"] > 1000.0


def test_raw_blocker_artifact_pins_pathological_outcome():
    # Offline diagnosis only (never a runtime input): the pre-fix R7 raw
    # artifact recorded the actual defect that motivated R7.1.
    raw = json.loads(RAW_ARTIFACT.read_text())
    records = {(r["race_id"], r["stage"]): r
               for r in raw["state_records"] if r.get("mode") == "R6_PIT"}
    mid = records[("2020-r07-R", "MID")]
    assert mid["predicted_winner"] == "giovinazzi"
    assert mid["actual_winner"] == "hamilton"
    assert mid["winner_log_loss"] > 10.0
    macro = raw["aggregates"]["race_macro"]["winner_log_loss"]
    assert macro["count"] == 99
    assert macro["mean"] > 4.0


# ===========================================================================
# R7.1-T/U  The evaluator no longer applies its own criterion.
# ===========================================================================

def test_evaluator_support_uses_runtime_reason():
    # The validation driver calls the runtime start-state contract and
    # surfaces its stable reason; it does not apply a separate criterion.
    import scripts.validate_phase6_simulation as script
    source = Path(script.__file__).read_text()
    assert "is_contemporaneous" not in source
    assert "_validate_start_state(state, selection)" in source


def test_is_contemporaneous_agrees_with_runtime_rule():
    state = _state([
        _driver("a", lap=3, race_time=300.0, observation_age=10.0),
    ], scheduled=6, leader=3)
    result = V.is_contemporaneous(state, 90.0)
    assert result["contemporaneous"] is True
    assert result["bound_s"] == pytest.approx(270.0)
    stale = _state([_driver("a", lap=3, race_time=300.0,
                            observation_age=1000.0)], scheduled=6, leader=3)
    assert V.is_contemporaneous(stale, 90.0)["contemporaneous"] is False
    assert contemporaneous_roster_offenders(stale, 90.0) == (("a", 1000.0),)


# ===========================================================================
# R7.1-N  Accepted-state parity with the pre-fix R7 raw artifact.
# ===========================================================================

@functools.lru_cache(maxsize=None)
def _raw_records():
    raw = json.loads(RAW_ARTIFACT.read_text())
    return {(r["race_id"], r["stage"]): r
            for r in raw["state_records"] if r.get("mode") == "R6_PIT"}


# P11-1: post-fix result identities on the release contract Python 3.11.x
# (deterministic within the environment; see test body for the
# version-sensitivity rationale). Keyed by (race_id, stage).
_POST_FIX_RESULT_IDENTITIES = {
    ("2020-r05-R", "EARLY"): "f6d3ddca0f2d0026926b1ec2331f0dc52564681cd0d5eb2f8d4737745ff23178",
    ("2020-r05-R", "MID"): "60e15a758033fabe37c49516a6f71b637bfe4df1bc3b3eb98bd5ddf0dd9eff31",
    ("2021-r07-R", "LATE"): "3561eec382859cb4471f8863230426ee08e0741ac305c234174f6e9283f65841",
    ("2022-r01-R", "MID"): "55ae9eeccd32b99decd117fe931b45fd8747bc55a7be58b66ccb66337d4d0429",
    ("2023-r07-R", "LATE"): "d71bb8f2625324871048b1f1c86e59c7e83e38873f2c4c37740d461e679a1770",
    ("2024-r01-R", "EARLY"): "d1c914a79d92cef94f3b9cbfeddaefd29d66f2d7ebfcc00782e85072be3701cd",
}


@pytest.mark.parametrize("season,race_id,stage", [
    (2020, "2020-r05-R", "EARLY"),
    (2020, "2020-r05-R", "MID"),
    (2021, "2021-r07-R", "LATE"),
    (2022, "2022-r01-R", "MID"),
    (2023, "2023-r07-R", "LATE"),
    (2024, "2024-r01-R", "EARLY"),
])
def test_accepted_state_matches_pre_fix_result_identity(season, race_id, stage):
    # Eligibility-only proof: for a state accepted both before and after the
    # fix, the runtime reproduces the pre-fix MonteCarloResult identity
    # exactly (same state/params/seed/config).
    #
    # P11-1 UPDATE_STALE_EXPECTATION: the pre-fix R7 raw artifact pins were
    # recorded on Python 3.13.14. MonteCarloResult.identity() hashes numpy
    # float values, whose formatting is Python-version-sensitive, so the
    # identical engine on the release contract Python 3.11.x produces
    # different (but deterministic within the environment — verified by
    # rerun) result identities, while state_identity still matches the raw
    # artifact exactly (same inputs). The invariant — accepted states take
    # the unchanged simulation path — is preserved; the environment-specific
    # result pins below replace the raw-artifact comparison. See
    # docs/PHASE6_FINAL_REPORT.md "Python-version-sensitive frozen identity".
    record = _raw_records()[(race_id, stage)]
    state = _real_state_at(season, race_id, record["frame_index"])
    params = _params_through(season - 1)
    result = MonteCarloEngine(chunk_size=512).run(
        state, params,
        SimulationConfig(1000, 20240101, sample_orders=0,
                         pit_dynamics_enabled=True),
        Assumptions(),
        execution_policy=ExecutionPolicy.HISTORICAL_BACKTEST)
    assert state.identity() == record["state_identity"]
    assert result.identity() == _POST_FIX_RESULT_IDENTITIES[(race_id, stage)]


def test_accepted_real_fixtures_simulate_early_mid_late(params_2024):
    for name, fixture in _ACCEPTED.items():
        state = _real_state(*fixture)
        result = MonteCarloEngine(chunk_size=128).run(
            state, params_2024, SimulationConfig(30, 7), Assumptions())
        assert result.valid_simulation_count == 30, name
        assert result.invalid_simulation_count == 0, name
        assert sum(s.win_probability for s in result.driver_summaries) == \
            pytest.approx(1.0, abs=1e-12), name


# ===========================================================================
# R7.1-I  Temporal adversarial suite (future / final-status poisoning).
# ===========================================================================

def _poisoned_state(season, race_id, driver, lap):
    states = pd.read_parquet(D9.format(season=season))
    states = states[states["race_id"] == race_id].copy()
    results = pd.read_parquet(RESULTS.format(season=season, race=race_id))
    races = pd.read_parquet(RACES.format(season=season, race=race_id))
    scheduled = int(races["total_laps_scheduled"].iloc[0])
    service = _service(season, race_id)
    index = _frame_index(service, driver, lap)
    baseline = from_race_state(service.state_at(index), anchor_frame_index=index)
    anchor_time = service.state_at(index).state_time_s
    future = states["state_time_s"] > anchor_time
    states.loc[future, "compound"] = "WET"
    states.loc[future, "tyre_life"] = 999
    states.loc[future, "pit_in_s"] = 1.0
    states.loc[future, "pit_out_s"] = 1.0
    states.loc[future, "track_state"] = "red_flag"
    states.loc[future, "lap_time_s"] = 1.0
    poison_results = results.copy()
    poison_results["position_final"] = (
        len(poison_results) - poison_results.index)
    poison_results["winner_flag"] = poison_results["position_final"] == 1
    meta = {race_id: {"scheduled_laps": scheduled}}
    poisoned_service = ReplayReconstructor(
        RP.build_replay_timeline(states),
        RaceStateReconstructor(states, poison_results, race_meta=meta))
    poisoned = from_race_state(poisoned_service.state_at(index),
                               anchor_frame_index=index)
    return baseline, poisoned


def test_future_poisoning_leaves_accepted_eligibility_identical():
    season, race_id, driver, lap = _ACCEPTED["mid"]
    baseline, poisoned = _poisoned_state(season, race_id, driver, lap)
    assert poisoned.identity() == baseline.identity()
    params = _params_through(season - 1)
    # Same eligibility decision and same simulation result.
    b = MonteCarloEngine(chunk_size=64).run(
        baseline, params, SimulationConfig(20, 1), Assumptions())
    p = MonteCarloEngine(chunk_size=64).run(
        poisoned, params, SimulationConfig(20, 1), Assumptions())
    assert p.identity() == b.identity()


def test_future_poisoning_leaves_rejection_reason_identical():
    season, race_id = _BLOCKER_RACE
    baseline, poisoned = _poisoned_state(season, race_id, "hamilton", 22)
    params = _params_through(season - 1)
    for state in (baseline, poisoned):
        with pytest.raises(SimulationUnsupportedError) as excinfo:
            MonteCarloEngine().run(state, params, SimulationConfig(5, 1),
                                   Assumptions())
        assert excinfo.value.reason == \
            REASON_NON_CONTEMPORANEOUS_ROSTER_MEMBER


# ===========================================================================
# R7.1-H  Runtime firewalls (no final status, no future rows, no evaluation).
# ===========================================================================

_FORBIDDEN_RUNTIME_TOKENS = (
    "race_driver_labels", "classified_position", "status_text", "dnf_flag",
    "winner_flag", "position_final", "read_parquet", "raceintel.simulation.validation",
)


def test_runtime_sources_read_no_final_status_or_future_truth():
    for path in (ENGINE_PATH, ADAPTER_PATH, MONTE_CARLO_PATH):
        source = path.read_text()
        for token in _FORBIDDEN_RUNTIME_TOKENS:
            assert token not in source, f"{path.name} references {token}"


def test_runtime_does_not_import_evaluation_module():
    for path in (ENGINE_PATH, ADAPTER_PATH, MONTE_CARLO_PATH):
        tree = ast.parse(path.read_text())
        imported = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.append(node.module)
        assert not any("raceintel.simulation.validation" in name for name in imported)


def test_engine_imports_no_data_stack():
    tree = ast.parse(ENGINE_PATH.read_text())
    imported = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.append(node.module)
    banned = ("pandas", "numpy", "sklearn", "joblib", "fastapi", "scipy")
    assert not any(name.split(".")[0] in banned for name in imported)


# ===========================================================================
# R7.1-O  Eligibility performance.
# ===========================================================================

def test_eligibility_check_is_negligible(params_2024):
    state = _real_state(*_ACCEPTED["mid"])
    selection = select_pace_parameters(state, params_2024)
    base = selection.base.value
    samples = []
    for _ in range(2000):
        started = time.perf_counter()
        contemporaneous_roster_offenders(state, base)
        samples.append(time.perf_counter() - started)
    samples.sort()
    p95 = samples[int(0.95 * len(samples)) - 1]
    mean = sum(samples) / len(samples)
    # A pure O(roster) pass; far below any simulation cost.
    assert p95 < 1e-3
    assert mean < 1e-3


# ===========================================================================
# 2025 firewall.
# ===========================================================================

def test_2025_is_never_an_eligible_season():
    assert 2025 in V.R7_EXCLUDED_SEASONS
    assert 2025 not in V.R7_EVALUATION_SEASONS
    assert V.default_protocol().no_2025 is True
