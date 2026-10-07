"""V3.2F regime corpus tests (Tier-3, corpus-dependent manifest).

- Pinned deferred-regime checkpoints refuse with the frozen taxonomy
  (no silent dry-green fallback), one pin per regime/token.
- Future-regime poison: mutating/removing after-T TrackStatus,
  WeatherData rainfall, and compounds leaves a capable T-state
  bit-identical (no future regime knowledge after T).
- Dry-green MC2-E parity corpus reruns bit-exact (Part Y gate).
- Deferred regimes return explicit 422 via the API (Part AJ).

Deterministic; no model, no refit, no stochastic-science change.
"""

import dataclasses
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
from raceintel.simulation.engine import ExecutionPolicy  # noqa: E402
from raceintel.simulation.params import (  # noqa: E402
    load_simulation_parameters,
    parameter_storage_dir,
)
from raceintel.simulation.presence import (  # noqa: E402
    prepare_initial_state,
)

# (race_id, frame_index, expected primary, expected token detail needle)
REGIME_PINS = [
    ("2018-r01-R", 83, "UNSUPPORTED_TRACK_STATE", "yellow"),
    ("2018-r03-R", 597, "UNSUPPORTED_TRACK_STATE", "safety_car"),
    ("2018-r09-R", 269, "UNSUPPORTED_TRACK_STATE", "vsc"),
    ("2018-r19-R", 80, "UNSUPPORTED_TRACK_STATE", "vsc_ending"),
    ("2021-r10-R", 19, "UNSUPPORTED_TRACK_STATE", "red_flag"),
    ("2018-r06-R", 40, "WET_CONDITIONS", None),
    ("2020-r03-R", 20, "WET_CONDITIONS", None),
    ("2018-r01-R", 20, "UNSUPPORTED_TRACK_STATE", None),
]

_SERVICE_CACHE: dict = {}
_PARAMS_2024 = None


def _params():
    global _PARAMS_2024
    if _PARAMS_2024 is None:
        _PARAMS_2024 = load_simulation_parameters(
            parameter_storage_dir(ROOT, 2024))
    return _PARAMS_2024


def _service_for(race_id):
    import pandas as pd

    if race_id not in _SERVICE_CACHE:
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
                    "scheduled_laps":
                        (None if pd.isna(row.total_laps_scheduled)
                         else int(row.total_laps_scheduled))}
        timeline = RP.build_replay_timeline(states)
        grid = {}
        for row in results.itertuples():
            g = getattr(row, "grid_position", None)
            grid[str(row.driver_id)] = (
                None if g is None or (isinstance(g, float) and g != g)
                else float(g))
        _SERVICE_CACHE[race_id] = (ReplayReconstructor(
            timeline, RaceStateReconstructor(states, results,
                                             race_meta=meta or None)),
            states, results, grid)
    return _SERVICE_CACHE[race_id]


@pytest.mark.parametrize(
    "race_id,frame,primary,needle", REGIME_PINS)
def test_pinned_deferred_checkpoints_refuse(race_id, frame, primary,
                                            needle):
    service, _, _, grid = _service_for(race_id)
    race_state = service.state_at(frame)
    verdict = prepare_initial_state(
        race_state, grid_by_driver=grid, parameters=_params(),
        execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
    assert verdict.eligible is False
    assert verdict.reason == primary
    if needle is not None:
        assert needle in verdict.detail


def test_future_regime_poison_leaves_capable_state_identical():
    """After-T TrackStatus/weather/compound poison cannot move T-state."""
    import pandas as pd

    from raceintel.simulation.adapter import from_race_state

    race_id, frame = "2018-r01-R", 90
    service, states, results, grid = _service_for(race_id)
    race_state = service.state_at(frame)
    before = prepare_initial_state(
        race_state, grid_by_driver=grid, parameters=_params(),
        execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
    assert before.eligible is True
    t_now = float(race_state.state_time_s)
    future = states["state_time_s"].astype(float) > t_now
    assert int(future.sum()) > 0
    poisoned = states.copy()
    poisoned.loc[future, "track_state"] = "safety_car"
    poisoned.loc[future, "wx_rainfall"] = True
    poisoned.loc[future, "compound"] = "WET"
    poisoned.loc[future, "tyre_life"] = 3
    timeline = RP.build_replay_timeline(poisoned)
    meta = {}
    season = int(race_id[:4])
    rp = (ROOT / "data" / "v2" / "processed" / "races" /
          f"season={season}" / f"races__{race_id}.parquet")
    for row in pd.read_parquet(rp).itertuples():
        meta[str(row.race_id)] = {
            "scheduled_laps": (None if pd.isna(row.total_laps_scheduled)
                               else int(row.total_laps_scheduled))}
    poisoned_service = ReplayReconstructor(
        timeline, RaceStateReconstructor(poisoned, results,
                                         race_meta=meta or None))
    after_state = poisoned_service.state_at(frame)
    assert from_race_state(after_state) == from_race_state(race_state)
    verdict = prepare_initial_state(
        after_state, grid_by_driver=grid, parameters=_params(),
        execution_policy=ExecutionPolicy.RETROSPECTIVE_PRODUCT)
    assert verdict.eligible is True
    assert verdict.reason == "SIMULATION_CAPABLE"


def test_dry_green_parity_corpus_bit_exact():
    import concurrent.futures

    import freeze_v3_2f_parity_corpus as F

    frozen = json.loads(
        (ROOT / "results" / "v3" / "v3_2f" /
         "dry_green_parity_corpus.json").read_text(encoding="utf-8"))
    corpus = [
        {"race_id": r["race_id"], "season": r["season"],
         "frame_index": r["frame_index"], "stage": r["stage"],
         "fold_through": r["fold_through"], "roster": r["roster"]}
        for r in frozen["results"]
    ]
    with concurrent.futures.ProcessPoolExecutor(max_workers=8) as pool:
        outs = list(pool.map(F._worker, corpus))
    assert all(o.get("ok") for o in outs), [
        o for o in outs if not o.get("ok")]
    by_key = {(r["race_id"], r["frame_index"]): r
              for r in frozen["results"]}

    def _norm(obj):
        # JSON round-trip normalizes int dict keys to strings; compare
        # in the stored representation so the test checks science, not
        # serialization.
        return json.loads(json.dumps(obj, sort_keys=True, default=str))

    for o in outs:
        r = o["result"]
        ref = by_key[(r["race_id"], r["frame_index"])]
        for key in ("valid", "invalid", "winner_counts",
                    "winner_frequency", "expected_finish",
                    "position_counts", "sample_order"):
            assert _norm(r[key]) == _norm(ref[key]), (
                r["race_id"], r["frame_index"], key)


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


def _anchor_for(race_id, frame_index):
    artifact = json.load(open(
        ROOT / "results" / "v2_replay" / "checkpoints" /
        f"{race_id}.json", encoding="utf-8"))
    for entry in artifact["checkpoints"]:
        cp = entry["checkpoint"]
        if cp["frame_index"] == frame_index:
            return cp
    raise AssertionError(f"no anchor {race_id}@{frame_index}")


@pytest.mark.parametrize("race_id,frame", [
    ("2018-r01-R", 83),    # yellow
    ("2018-r03-R", 597),   # safety car
    ("2018-r09-R", 269),   # vsc
    ("2018-r06-R", 40),    # wet
])
def test_api_deferred_regimes_422_without_fallback(race_id, frame):
    client = _api_client()
    cp = _anchor_for(race_id, frame)
    body = {"race_id": race_id,
            "anchor_driver_id": cp["anchor_driver_id"],
            "anchor_lap_number": cp["anchor_lap_number"],
            "anchor_state_time_s": cp["anchor_state_time_s"],
            "simulation_count": 64}
    response = client.post("/v2/simulations/race", json=body)
    assert response.status_code == 422
    assert response.json()["error"] == "simulation_unsupported"
