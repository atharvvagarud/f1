"""V3.2C R3 parity, RNG parity, and Phase-7 compatibility (Parts V, W, X).

- Corpus parity: every pre-change parity entry (frozen BEFORE any
  simulation-source change) reproduces its canonical result identity
  bit-exactly after V3.2C, for both the pits-off R3 arm and the pits-on
  production-path subset.
- RNG parity: same-seed equality, chunk invariance, and proof that
  initial-state classification consumes no RNG stream position.
- Strategy compatibility: a pinned small Phase-7 comparison on a
  previously supported state is unchanged (CRN pairing intact).

Deterministic; no model, no refit, no stochastic-science change.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import pytest  # noqa: E402

from raceintel.race_state.race_state_reconstruction import (  # noqa: E402
    RaceStateReconstructor,
)
from raceintel.replay import replay as RP  # noqa: E402
from raceintel.replay.replay_reconstruction import ReplayReconstructor  # noqa: E402
from raceintel.simulation.config import (  # noqa: E402
    Assumptions,
    SimulationConfig,
)
from raceintel.simulation.engine import ExecutionPolicy  # noqa: E402
from raceintel.simulation.monte_carlo import MonteCarloEngine  # noqa: E402
from raceintel.simulation.params import (  # noqa: E402
    load_simulation_parameters,
    parameter_storage_dir,
)

CORPUS_PATH = ROOT / "results" / "v3" / "v3_2c_parity_corpus.json"


def _corpus():
    return json.load(open(CORPUS_PATH, encoding="utf-8"))


_CORPUS_ENTRY_IDS = [
    f"{e['race_id']}@{e['frame_index']}"
    for e in json.load(open(CORPUS_PATH, encoding="utf-8"))["entries"]
]

_SERVICE_CACHE: dict = {}


def _cached_service(race_id):
    if race_id not in _SERVICE_CACHE:
        _SERVICE_CACHE[race_id] = _service_for(race_id)
    return _SERVICE_CACHE[race_id]


def _service_for(race_id):
    import pandas as pd

    season = int(race_id[:4])
    base = ROOT / "data" / "v2" / "processed"
    states = pd.read_parquet(
        base / f"driver_lap_state_d9/season={season}/"
        f"driver_lap_state_d9__d9-{season}.parquet")
    states = states[states["race_id"] == race_id].copy()
    results = pd.read_parquet(
        base / f"results/season={season}/results__{race_id}.parquet")
    meta = {}
    rp = base / f"races/season={season}/races__{race_id}.parquet"
    if rp.exists():
        for row in pd.read_parquet(rp).itertuples():
            meta[str(row.race_id)] = {
                "scheduled_laps": (None if pd.isna(row.total_laps_scheduled)
                                   else int(row.total_laps_scheduled))}
    timeline = RP.build_replay_timeline(states)
    return ReplayReconstructor(
        timeline, RaceStateReconstructor(states, results,
                                         race_meta=meta or None))


def _run(sim_state, parameters, *, pits, seed, n_runs, chunk_size=512):
    from raceintel.simulation.adapter import from_race_state  # noqa

    config = SimulationConfig(simulation_count=n_runs, master_seed=seed,
                              pit_dynamics_enabled=pits)
    return MonteCarloEngine(chunk_size=chunk_size).run(
        sim_state, parameters, config, Assumptions(),
        execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)


# ---------------------------------------------------------------------------
# Corpus parity (Part V): 100% of previously valid states remain valid with
# bit-exact scientific output.
# ---------------------------------------------------------------------------

def test_parity_corpus_is_frozen_and_sufficient():
    corpus = _corpus()
    assert corpus["schema_version"] == "v3.2c-parity-v1"
    assert corpus["entry_count"] >= 30
    seasons = {e["race_id"][:4] for e in corpus["entries"]}
    assert len(seasons) >= 5
    stages = {e["stage"] for e in corpus["entries"]}
    assert stages == {"EARLY", "MID", "LATE"}


@pytest.mark.parametrize("entry_id", _CORPUS_ENTRY_IDS)
def test_parity_corpus_entry_bit_exact(entry_id):
    import pandas as pd  # noqa: F401

    from raceintel.simulation.adapter import from_race_state

    corpus = _corpus()
    entry = next(e for e in corpus["entries"]
                 if f"{e['race_id']}@{e['frame_index']}" == entry_id)
    parameters = load_simulation_parameters(
        parameter_storage_dir(ROOT, 2024))
    assert parameters.scientific_hash() == corpus["parameter_hash"]
    service = _cached_service(entry["race_id"])
    sim_state = from_race_state(service.state_at(entry["frame_index"]))
    for arm in entry["arms"]:
        result = _run(sim_state, parameters, pits=arm["pits_enabled"],
                      seed=arm["seed"], n_runs=arm["n_runs"])
        assert result.identity() == arm["result_identity"], (
            entry["race_id"], entry["frame_index"], arm["pits_enabled"])
        assert result.simulation_request_identity == arm["request_identity"]
        assert [s.driver_id for s in result.driver_summaries] == arm["roster"]
        assert result.valid_simulation_count == arm["valid"]
        assert result.invalid_simulation_count == arm["invalid"]
        assert max(((s.driver_id, float(s.win_probability))
                    for s in result.driver_summaries),
                   key=lambda kv: (kv[1], kv[0]))[0] == arm["top_driver"]


# ---------------------------------------------------------------------------
# RNG parity (Part W).
# ---------------------------------------------------------------------------

def _first_corpus_state():
    from raceintel.simulation.adapter import from_race_state

    entry = _corpus()["entries"][0]
    return entry, from_race_state(
        _cached_service(entry["race_id"]).state_at(entry["frame_index"]))


def test_rng_same_seed_equal_and_chunk_invariant():
    parameters = load_simulation_parameters(
        parameter_storage_dir(ROOT, 2024))
    entry, sim_state = _first_corpus_state()
    arm = entry["arms"][0]
    first = _run(sim_state, parameters, pits=arm["pits_enabled"],
                 seed=arm["seed"], n_runs=arm["n_runs"], chunk_size=512)
    second = _run(sim_state, parameters, pits=arm["pits_enabled"],
                  seed=arm["seed"], n_runs=arm["n_runs"], chunk_size=512)
    assert first.identity() == second.identity() == arm["result_identity"]
    chunked = _run(sim_state, parameters, pits=arm["pits_enabled"],
                   seed=arm["seed"], n_runs=arm["n_runs"], chunk_size=64)
    assert chunked.identity() == arm["result_identity"]


def test_presence_classification_consumes_no_rng():
    from raceintel.simulation.adapter import from_race_state
    from raceintel.simulation.presence import (
        classify_roster,
        dns_exclusions,
        prepare_initial_state,
    )

    parameters = load_simulation_parameters(
        parameter_storage_dir(ROOT, 2024))
    entry, sim_state = _first_corpus_state()
    arm = entry["arms"][0]
    service = _cached_service(entry["race_id"])
    race_state = service.state_at(entry["frame_index"])
    # Interleave arbitrary presence classification between two runs.
    before = _run(sim_state, parameters, pits=arm["pits_enabled"],
                  seed=arm["seed"], n_runs=arm["n_runs"])
    for _ in range(5):
        classify_roster(race_state, {"__nobody__": None})
        dns_exclusions(race_state, {"__nobody__": None})
        prepare_initial_state(race_state, grid_by_driver={},
                              parameters=parameters)
        from_race_state(race_state)
    after = _run(sim_state, parameters, pits=arm["pits_enabled"],
                 seed=arm["seed"], n_runs=arm["n_runs"])
    assert before.identity() == after.identity() == arm["result_identity"]


# ---------------------------------------------------------------------------
# Strategy compatibility (Part X): pinned small comparison unchanged.
# ---------------------------------------------------------------------------

def test_strategy_comparison_pinned_identity():
    from raceintel.simulation.adapter import from_race_state
    from raceintel.strategy.comparison import compare_strategies

    parameters = load_simulation_parameters(
        parameter_storage_dir(ROOT, 2024))
    entry, sim_state = _first_corpus_state()
    assert sim_state is not None
    _ = from_race_state  # state built via the unchanged R2 path
    target = sim_state.roster_driver_ids[0]
    config = SimulationConfig(simulation_count=32, master_seed=20240101,
                              pit_dynamics_enabled=False)
    comparison = compare_strategies(
        sim_state, parameters, config, Assumptions(),
        target, execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
    assert comparison.supported is True
    identity = comparison.identity()
    assert identity == _STRATEGY_PIN, (
        "Phase-7 comparison changed; V3.2C must not alter strategy science")


# ---------------------------------------------------------------------------
# API compatibility (Part AK): previously-valid 200-identical, DNS-repaired
# 200-deterministic, unsupported still 422 with stable reasons.
# ---------------------------------------------------------------------------

_API_SERVICE = None


def _api_client():
    global _API_SERVICE
    if _API_SERVICE is None:
        from api.v2_service import load_v2_service
        from api.v2_simulation_service import build_v2_simulation_service

        _API_SERVICE = build_v2_simulation_service(load_v2_service())
    from fastapi.testclient import TestClient

    from api.main import app
    from api.v2_simulation_service import get_v2_simulation_service

    app.dependency_overrides[get_v2_simulation_service] = (
        lambda: _API_SERVICE)
    return TestClient(app)


def _checkpoint_anchor(race_id, position):
    artifact = json.load(open(
        ROOT / "results" / "v2_replay" / "checkpoints" / f"{race_id}.json",
        encoding="utf-8"))
    return artifact["checkpoints"][position]["checkpoint"]


def test_api_dns_repaired_state_returns_deterministic_success():
    client = _api_client()
    cp = _checkpoint_anchor("2021-r22-R", 10)
    body = {"race_id": "2021-r22-R",
            "anchor_driver_id": cp["anchor_driver_id"],
            "anchor_lap_number": cp["anchor_lap_number"],
            "anchor_state_time_s": cp["anchor_state_time_s"],
            "simulation_count": 64}
    first = client.post("/v2/simulations/race", json=body)
    second = client.post("/v2/simulations/race", json=body)
    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["scientific_result_identity"] == \
        second.json()["scientific_result_identity"]
    assert len(first.json()["drivers"]) == 19  # mazepin excluded


def test_api_unsupported_states_still_422_without_fallback():
    client = _api_client()
    wet = {"race_id": "2018-r11-R", "anchor_driver_id": "alonso",
           "anchor_lap_number": 44, "anchor_state_time_s": 4004.408,
           "simulation_count": 64}
    response = client.post("/v2/simulations/race", json=wet)
    assert response.status_code == 422
    assert response.json()["error"] == "simulation_unsupported"
    assert response.json()["reason"] in (
        "wet_track_conditions", "wet_compound_state")


def test_api_previously_valid_state_matches_parity_identity():
    client = _api_client()
    corpus = _corpus()
    entry = corpus["entries"][0]
    service = _cached_service(entry["race_id"])
    race_state = service.state_at(entry["frame_index"])
    body = {"race_id": entry["race_id"],
            "anchor_driver_id": race_state.anchor_driver_id,
            "anchor_lap_number": race_state.anchor_lap_number,
            "anchor_state_time_s": race_state.state_time_s,
            "simulation_count": 100}
    response = client.post("/v2/simulations/race", json=body)
    assert response.status_code == 200
    # Production path runs pits-on; the parity corpus pits-on arm pins it.
    pits_arm = next(a for a in entry["arms"] if a["pits_enabled"])
    assert response.json()["scientific_result_identity"] == \
        pits_arm["result_identity"]


# Pinned 2026-10-05: first corpus entry (2018-r01-R frame 90) baseline
# comparison for target alonso, 32 runs, pits off. Strategy + simulation
# sources frozen; any drift fails loudly.
_STRATEGY_PIN = (
    "f54e95a1a95c413a46ee949396256e29a46a913e6e1425030ba6eef666889771"
)
