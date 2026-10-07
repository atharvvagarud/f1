"""V3.2B MC2.0 field-contract tests (declarative; kernel untouched).

Pins the frozen active-field presence levels, the condition support
matrix, the contract identity, and the retirement temporal boundary:
poisoning final classification / future rows must leave at-T presence
decisions unchanged, a driver active at T1 must stay active despite a
later factual retirement, and no runtime source may read DNF-shaped
future truth.
"""

import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from raceintel.simulation.field_contract import (  # noqa: E402
    FIELD_CONTRACT_VERSION,
    PRESENCE_LEVELS,
    SUPPORT_MATRIX,
    classify_presence,
    contract_identity,
    support_decision,
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
from raceintel.simulation.adapter import from_race_state  # noqa: E402
from raceintel.simulation.params import (  # noqa: E402
    load_simulation_parameters,
    parameter_storage_dir,
)

CONTRACT_IDENTITY_PIN = (
    "713d6e4df22bf09664ca3c6a2a99fea1941c57492d5afe55fb836e7bdab32691"
)

# Spain 2018: 6 factual DNFs incl. a lap-1 crash (grosjean). T1 (frame 17,
# leader lap 2: roster complete, crash driver still freshly observed) is
# before any retirement is knowable; T2 (frame 430, leader lap 25) is after.
_BOUNDARY_RACE = "2018-r05-R"
_T1_FRAME = 17
_T2_FRAME = 430
_CRASH_DRIVER = "grosjean"


def _service(results):
    season = int(_BOUNDARY_RACE[:4])
    base = ROOT / "data" / "v2" / "processed"
    states = pd.read_parquet(
        base / f"driver_lap_state_d9/season={season}/"
        f"driver_lap_state_d9__d9-{season}.parquet")
    states = states[states["race_id"] == _BOUNDARY_RACE].copy()
    meta = {}
    rp = (base / f"races/season={season}/races__{_BOUNDARY_RACE}.parquet")
    if rp.exists():
        for row in pd.read_parquet(rp).itertuples():
            meta[str(row.race_id)] = {
                "scheduled_laps": (None if pd.isna(
                    row.total_laps_scheduled)
                    else int(row.total_laps_scheduled))}
    timeline = RP.build_replay_timeline(states)
    return ReplayReconstructor(
        timeline, RaceStateReconstructor(states, results,
                                         race_meta=meta or None))


def _presence_inputs(service, frame_index, driver_id):
    state = service.state_at(frame_index)
    sim_state = from_race_state(state)
    params = load_simulation_parameters(
        parameter_storage_dir(ROOT, 2024))
    selection = select_pace_parameters(sim_state, params)
    bound = (CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES
             * selection.base.value)
    entry = {e.driver_id: e for e in state.observable_drivers}.get(driver_id)
    unobserved = driver_id in set(state.unobservable_driver_ids)
    return {
        "observed": entry is not None,
        "observation_age_s": (None if entry is None
                              else entry.observation_age_s),
        "age_bound_s": bound,
        "unobserved": unobserved,
        "leader_lap": sim_state.leader_laps_done,
        "lap": (None if entry is None else entry.observed_lap_number),
    }


# ---------------------------------------------------------------------------
# Presence levels.
# ---------------------------------------------------------------------------

def test_presence_active_within_bound():
    assert classify_presence(observed=True, observation_age_s=80.0,
                             age_bound_s=267.0) == "ACTIVE"


def test_presence_stale_unresolved_without_signal():
    assert classify_presence(observed=True, observation_age_s=900.0,
                             age_bound_s=267.0,
                             laps_behind_leader=5) == "STALE_UNRESOLVED"


def test_presence_signaled_stale_requires_behind_guard():
    assert classify_presence(observed=True, observation_age_s=900.0,
                             age_bound_s=267.0, rc_stopped=True,
                             laps_behind_leader=3) == "EXCLUDE_SIGNALED_STALE"
    assert classify_presence(observed=True, observation_age_s=900.0,
                             age_bound_s=267.0, rc_stopped=True,
                             laps_behind_leader=1) == "STALE_UNRESOLVED"


def test_presence_dns_requires_pre_race_fact():
    assert classify_presence(observed=False, dns_no_grid_slot=True) == \
        "EXCLUDE_DNS_PRE_RACE"
    assert classify_presence(observed=False) == "UNOBSERVED_PRE_FIRST"
    assert classify_presence(observed=False, observation_age_s=5.0) == \
        "UNOBSERVED_DATA_GAP"


# ---------------------------------------------------------------------------
# Support matrix.
# ---------------------------------------------------------------------------

def test_support_matrix_frozen_values():
    assert support_decision("DRY_GREEN") == "SUPPORTED_INITIAL"
    for condition in ("DRY_YELLOW", "DRY_VSC", "DRY_SC", "RED",
                      "WET_GREEN", "WET_NEUTRALISED"):
        assert support_decision(condition) == "DEFERRED", condition
    for condition in ("TERMINAL", "UNKNOWN_TRACK"):
        assert support_decision(condition) == "INVALID", condition


def test_support_matrix_deterministic_and_complete():
    first = {key: support_decision(key) for key in SUPPORT_MATRIX}
    second = {key: support_decision(key) for key in SUPPORT_MATRIX}
    assert first == second
    assert set(first) == {"DRY_GREEN", "DRY_YELLOW", "DRY_VSC", "DRY_SC",
                          "RED", "WET_GREEN", "WET_NEUTRALISED", "TERMINAL",
                          "UNKNOWN_TRACK"}
    with pytest.raises(ValueError):
        support_decision("DRY_BLACK_FLAG_CHEQUERED")


def test_contract_identity_pinned():
    assert FIELD_CONTRACT_VERSION == "mc2-field-v1"
    assert contract_identity() == CONTRACT_IDENTITY_PIN
    assert contract_identity() == CONTRACT_IDENTITY_PIN
    assert len(set(PRESENCE_LEVELS)) == 6


# ---------------------------------------------------------------------------
# Retirement temporal boundary (poison future truth).
# ---------------------------------------------------------------------------

def _load_results():
    season = int(_BOUNDARY_RACE[:4])
    return pd.read_parquet(
        ROOT / "data" / "v2" / "processed" / "results" /
        f"season={season}/results__{_BOUNDARY_RACE}.parquet")


def test_t1_active_despite_later_factual_retirement():
    service = _service(_load_results())
    inputs = _presence_inputs(service, _T1_FRAME, _CRASH_DRIVER)
    assert inputs["observed"] is True
    assert classify_presence(**{k: v for k, v in inputs.items()
                                if k in ("observed", "observation_age_s",
                                         "age_bound_s")}) == "ACTIVE"


def test_future_poisoning_leaves_presence_inputs_identical():
    baseline = _service(_load_results())
    poisoned_results = _load_results().copy()
    if "dnf_flag" in poisoned_results.columns:
        poisoned_results["dnf_flag"] = False
    if "position_final" in poisoned_results.columns:
        poisoned_results["position_final"] = 20
    if "winner_flag" in poisoned_results.columns:
        poisoned_results["winner_flag"] = False
    poisoned = _service(poisoned_results)
    for frame_index in (_T1_FRAME, _T2_FRAME):
        assert _presence_inputs(baseline, frame_index,
                                _CRASH_DRIVER) == _presence_inputs(
            poisoned, frame_index, _CRASH_DRIVER)


def test_t2_stale_never_claims_retirement():
    service = _service(_load_results())
    inputs = _presence_inputs(service, _T2_FRAME, _CRASH_DRIVER)
    level = classify_presence(
        observed=inputs["observed"],
        observation_age_s=inputs["observation_age_s"],
        age_bound_s=inputs["age_bound_s"],
        laps_behind_leader=(None if inputs["lap"] is None else
                            inputs["leader_lap"] - inputs["lap"]))
    assert level in ("STALE_UNRESOLVED", "EXCLUDE_SIGNALED_STALE")
    assert "RETIRED" not in level


# ---------------------------------------------------------------------------
# No future-DNF inference in runtime sources.
# ---------------------------------------------------------------------------

_FORBIDDEN_TOKENS = (
    "dnf_flag", "winner_flag", "position_final", "classified_position",
    "status_text", "race_driver_labels",
)


def test_runtime_sources_read_no_dnf_future_truth():
    for name in ("engine.py", "adapter.py", "field_contract.py"):
        source = (ROOT / "raceintel" / "simulation" / name).read_text()
        for token in _FORBIDDEN_TOKENS:
            assert token not in source, f"{name} references {token}"


def test_field_contract_is_stdlib_only():
    tree = ast.parse((ROOT / "raceintel" / "simulation" /
                      "field_contract.py").read_text())
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                assert alias.name in ("hashlib", "json"), alias.name
        elif isinstance(node, ast.ImportFrom):
            assert node.module in ("__future__",), node.module
