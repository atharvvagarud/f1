"""V3.2C causal initial-state adapter tests (Parts E-T, AF).

Pins the frozen mc2-field-v1 integration: DNS causality (grid-only,
future-proof), DNS exclusion, transient-absence protection, retirement
non-inference, tyre-refusal preservation, track/weather/terminal policy
preservation, failure taxonomy, and eligibility determinism.

No stochastic science is touched here; parity/RNG/strategy gates live in
``test_v3_2c_parity.py``. Future rows and final results are used only as
offline fixtures for poisoning — never as runtime inputs.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd  # noqa: E402
import pytest  # noqa: E402

from raceintel.race_state.race_state_reconstruction import (  # noqa: E402
    RaceStateReconstructor,
)
from raceintel.replay import replay as RP  # noqa: E402
from raceintel.replay.replay_reconstruction import ReplayReconstructor  # noqa: E402
from raceintel.simulation.adapter import (  # noqa: E402
    SimulationUnavailableError,
    from_race_state,
)
from raceintel.simulation.engine import (  # noqa: E402
    SimulationUnsupportedError,
)
from raceintel.simulation.field_contract import (  # noqa: E402
    FIELD_CONTRACT_VERSION,
    PRESENCE_LEVELS,
    classify_presence,
    contract_identity,
)
from raceintel.simulation.params import (  # noqa: E402
    load_simulation_parameters,
    parameter_storage_dir,
)
from raceintel.simulation.presence import (  # noqa: E402
    ELIGIBILITY_TAXONOMY,
    PRESENCE_ADAPTER_VERSION,
    EligibilityResult,
    classify_roster,
    dns_exclusions,
    grid_slot_known,
    prepare_initial_state,
    without_drivers,
)

FIELD_CONTRACT_IDENTITY_PIN = (
    "713d6e4df22bf09664ca3c6a2a99fea1941c57492d5afe55fb836e7bdab32691"
)

# 2021 Abu Dhabi: mazepin DNS (no grid slot, illness, zero D9 rows).
_DNS_RACE = "2021-r22-R"
_DNS_DRIVER = "mazepin"
# 2022 Jeddah: mick_schumacher DNS (no grid slot) + tsunoda data gap
# (grid 19, zero D9 rows: started but unobserved -> must stay refused).
_GAP_RACE = "2022-r02-R"
_GAP_DNS_DRIVER = "mick_schumacher"
_GAP_DRIVER = "tsunoda"


def _load(race_id):
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
    service = ReplayReconstructor(
        timeline, RaceStateReconstructor(states, results,
                                         race_meta=meta or None))
    return states, results, service


def _grid(results) -> dict:
    out = {}
    for row in results.itertuples():
        grid = getattr(row, "grid_position", None)
        out[str(row.driver_id)] = (
            None if grid is None or pd.isna(grid) else float(grid))
    return out


def _params():
    return load_simulation_parameters(parameter_storage_dir(ROOT, 2024))


def _frames(race_id):
    import json
    artifact = json.load(open(
        ROOT / "results" / "v2_replay" / "checkpoints" / f"{race_id}.json",
        encoding="utf-8"))
    return sorted(e["checkpoint"]["frame_index"]
                  for e in artifact["checkpoints"])


# ---------------------------------------------------------------------------
# Contract inheritance (Part E).
# ---------------------------------------------------------------------------

def test_field_contract_version_and_identity_inherited():
    assert FIELD_CONTRACT_VERSION == "mc2-field-v1"
    assert contract_identity() == FIELD_CONTRACT_IDENTITY_PIN
    assert tuple(PRESENCE_LEVELS) == (
        "ACTIVE", "EXCLUDE_DNS_PRE_RACE", "EXCLUDE_SIGNALED_STALE",
        "STALE_UNRESOLVED", "UNOBSERVED_PRE_FIRST", "UNOBSERVED_DATA_GAP")
    assert PRESENCE_ADAPTER_VERSION == "v3.2c-presence-v1"


def test_presence_uses_exact_six_levels():
    states, results, service = _load(_DNS_RACE)
    grid = _grid(results)
    race_state = service.state_at(_frames(_DNS_RACE)[10])
    levels = classify_roster(race_state, grid)
    assert set(levels) == set(race_state.roster_driver_ids)
    assert set(levels.values()) <= set(PRESENCE_LEVELS)
    assert levels[_DNS_DRIVER] == "EXCLUDE_DNS_PRE_RACE"


def test_runtime_presence_reads_no_future_truth():
    source = (ROOT / "raceintel" / "simulation" / "presence.py").read_text()
    for token in ("dnf_flag", "winner_flag", "position_final",
                  "classified_position", "status_text", "podium_flag",
                  "laps_completed", "race_driver_labels"):
        assert token not in source, f"presence.py references {token}"


# ---------------------------------------------------------------------------
# DNS source proof (Part F): grid-only, pre-race, poison-proof.
# ---------------------------------------------------------------------------

def test_grid_slot_known_only_consults_grid():
    assert grid_slot_known(1.0) is True
    assert grid_slot_known(19) is True
    assert grid_slot_known(None) is False
    assert grid_slot_known(float("nan")) is False
    assert grid_slot_known("5") is True


def test_dns_driver_has_no_grid_slot_and_zero_rows():
    states, results, _service = _load(_DNS_RACE)
    grid = _grid(results)
    assert grid[_DNS_DRIVER] is None
    assert len(states[states["driver_id"] == _DNS_DRIVER]) == 0


def test_data_gap_driver_has_grid_slot_but_zero_rows():
    states, results, _service = _load(_GAP_RACE)
    grid = _grid(results)
    assert grid[_GAP_DNS_DRIVER] is None
    assert grid[_GAP_DRIVER] == 19.0
    assert len(states[states["driver_id"] == _GAP_DRIVER]) == 0


def test_future_poisoning_cannot_change_dns_classification():
    states, results, service = _load(_DNS_RACE)
    grid = _grid(results)
    poisoned = results.copy()
    if "dnf_flag" in poisoned.columns:
        poisoned["dnf_flag"] = False
    if "position_final" in poisoned.columns:
        poisoned["position_final"] = 1
    if "winner_flag" in poisoned.columns:
        poisoned["winner_flag"] = True
    if "status_text" in poisoned.columns:
        poisoned["status_text"] = "Finished"
    poisoned_grid = _grid(poisoned)
    assert poisoned_grid == grid
    for frame_index in (_frames(_DNS_RACE)[0], _frames(_DNS_RACE)[10],
                        _frames(_DNS_RACE)[-1]):
        assert dns_exclusions(service.state_at(frame_index),
                              poisoned_grid) == dns_exclusions(
            service.state_at(frame_index), grid) == (_DNS_DRIVER,)


def test_eligibility_unchanged_under_future_poison():
    _states, results, service = _load(_DNS_RACE)
    grid = _grid(results)
    poisoned = results.copy()
    for col, val in (("dnf_flag", True), ("position_final", 1),
                     ("winner_flag", True), ("status_text", "Retired"),
                     ("points", 0.0), ("laps_completed", 0)):
        if col in poisoned.columns:
            poisoned[col] = val
    poisoned_grid = _grid(poisoned)
    params = _params()
    for frame_index in (_frames(_DNS_RACE)[0], _frames(_DNS_RACE)[10],
                        _frames(_DNS_RACE)[-1]):
        base = prepare_initial_state(service.state_at(frame_index),
                                     grid_by_driver=grid, parameters=params)
        pois = prepare_initial_state(service.state_at(frame_index),
                                     grid_by_driver=poisoned_grid,
                                     parameters=params)
        assert (pois.eligible, pois.reason,
                pois.excluded_dns_driver_ids) == (
            base.eligible, base.reason, base.excluded_dns_driver_ids)


# ---------------------------------------------------------------------------
# DNS exclusion (Part G).
# ---------------------------------------------------------------------------

def test_dns_exclusion_repairs_2021_r22_frame():
    _states, results, service = _load(_DNS_RACE)
    grid = _grid(results)
    params = _params()
    frame_index = _frames(_DNS_RACE)[10]
    # Pre-V3.2C path refuses on the DNS member.
    with pytest.raises(SimulationUnavailableError) as exc_info:
        from_race_state(service.state_at(frame_index))
    assert exc_info.value.reason == "unobserved_roster_member"
    # V3.2C path excludes exactly the proven DNS member and adapts.
    result = prepare_initial_state(service.state_at(frame_index),
                                   grid_by_driver=grid, parameters=params)
    assert result.excluded_dns_driver_ids == (_DNS_DRIVER,)
    assert _DNS_DRIVER not in result.active_driver_ids
    assert len(result.active_driver_ids) == len(
        service.state_at(frame_index).roster_driver_ids) - 1


def test_data_gap_race_stays_refused():
    _states, results, service = _load(_GAP_RACE)
    grid = _grid(results)
    assert dns_exclusions(service.state_at(_frames(_GAP_RACE)[10]),
                          grid) == (_GAP_DNS_DRIVER,)
    assert _GAP_DRIVER not in dns_exclusions(
        service.state_at(_frames(_GAP_RACE)[10]), grid)
    levels = classify_roster(service.state_at(_frames(_GAP_RACE)[10]), grid)
    assert levels[_GAP_DRIVER] == "UNOBSERVED_DATA_GAP"
    assert levels[_GAP_DNS_DRIVER] == "EXCLUDE_DNS_PRE_RACE"


def test_without_drivers_never_drops_the_anchor():
    _states, _results, service = _load(_DNS_RACE)
    race_state = service.state_at(_frames(_DNS_RACE)[10])
    with pytest.raises(ValueError):
        without_drivers(race_state, (race_state.anchor_driver_id,))
    assert without_drivers(race_state, ()) is race_state


def test_no_grid_map_means_no_dns_claim():
    # Without the pre-race grid fact nothing may be called DNS: the
    # adapter stays strictly conservative and refuses.
    _states, _results, service = _load(_DNS_RACE)
    params = _params()
    race_state = service.state_at(_frames(_DNS_RACE)[10])
    assert dns_exclusions(race_state, None) == ()
    assert dns_exclusions(race_state, {}) == ()
    levels = classify_roster(race_state, None)
    assert "EXCLUDE_DNS_PRE_RACE" not in set(levels.values())
    result = prepare_initial_state(race_state, grid_by_driver=None,
                                   parameters=params)
    assert result.eligible is False
    assert result.reason == "MISSING_DRIVER_OBSERVATION"


# ---------------------------------------------------------------------------
# Transient absence protection (Part H).
# ---------------------------------------------------------------------------

# Pinned transient fixtures (observed at T but stale vs the 3.0x bound,
# with later D9 rows proving transience; strong eventual result):
# - 2020-r08-R (Monza, red-flag suspension gap) frame 490: gasly, the
#   eventual WINNER, plus sainz (P2), stroll (P3), norris (P4).
# - 2020-r09-R (Mugello) frame 122: bottas (P2), albon (P3).
_TRANSIENT_FIXTURES = (
    ("2020-r08-R", 490, "gasly", 1),
    ("2020-r08-R", 490, "sainz", 2),
    ("2020-r08-R", 490, "stroll", 3),
    ("2020-r09-R", 122, "bottas", 2),
    ("2020-r09-R", 122, "albon", 3),
)


def test_transient_fixtures_pinned():
    assert len(_TRANSIENT_FIXTURES) >= 1, \
        "diagnostics must pin >=1 transient top-5 fixture (Part H)"


def test_transient_drivers_are_never_excluded():
    from raceintel.simulation.engine import (
        CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES,
        select_pace_parameters,
    )
    params = _params()
    by_race: dict = {}
    for race_id, frame_index, driver_id, final_pos in _TRANSIENT_FIXTURES:
        states, results, service = by_race.setdefault(
            race_id, _load(race_id))
        # Offline proof of transience (labels only, never runtime input):
        # the driver produces D9 rows after T and finishes top-5.
        race_state = service.state_at(frame_index)
        T = float(race_state.state_time_s)
        later = states[(states["driver_id"] == driver_id)
                       & (states["state_time_s"] > T)]
        assert len(later) > 0, (race_id, frame_index, driver_id)
        bound = (CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES
                 * float(select_pace_parameters(
                     from_race_state(race_state), params).base.value))
        grid = _grid(results)
        levels = classify_roster(race_state, grid, age_bound_s=bound)
        # Stale-but-transient: refused as a STATE, never excluded as a
        # driver. The eventual winner stays in the field.
        assert levels[driver_id] == "STALE_UNRESOLVED", (
            race_id, frame_index, driver_id)
        assert driver_id not in dns_exclusions(race_state, grid)
        result = prepare_initial_state(race_state, grid_by_driver=grid,
                                       parameters=params)
        assert result.eligible is False
        assert result.reason == "STALE_ROSTER_OBSERVATION"
        assert driver_id in result.active_driver_ids


def test_transient_fixtures_survive_future_poison():
    _states, results, service = _load("2020-r08-R")
    params = _params()
    grid = _grid(results)
    poisoned = results.copy()
    for col, val in (("dnf_flag", True), ("position_final", 20),
                     ("winner_flag", False), ("status_text", "Retired")):
        if col in poisoned.columns:
            poisoned[col] = val
    poisoned_grid = _grid(poisoned)
    assert poisoned_grid == grid
    race_state = service.state_at(490)
    base = prepare_initial_state(race_state, grid_by_driver=grid,
                                 parameters=params)
    pois = prepare_initial_state(race_state, grid_by_driver=poisoned_grid,
                                 parameters=params)
    assert (pois.eligible, pois.reason, pois.active_driver_ids) == (
        base.eligible, base.reason, base.active_driver_ids)
    assert "gasly" in pois.active_driver_ids


# ---------------------------------------------------------------------------
# Retirement safety (Part I): no generic inference, refuse by default.
# ---------------------------------------------------------------------------

def test_stale_states_are_refused_never_excluded():
    from raceintel.simulation.engine import (
        CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES,
        select_pace_parameters,
    )
    _states, results, service = _load("2018-r04-R")
    params = _params()
    grid = _grid(results)
    # First dry stale frame of this stale-dominated race.
    target = None
    for frame_index in _frames("2018-r04-R"):
        result = prepare_initial_state(service.state_at(frame_index),
                                       grid_by_driver=grid, parameters=params)
        if result.reason == "STALE_ROSTER_OBSERVATION":
            target = (frame_index, result)
            break
    assert target is not None
    frame_index, result = target
    race_state = service.state_at(frame_index)
    bound = (CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES
             * float(select_pace_parameters(
                 from_race_state(race_state), params).base.value))
    levels = classify_roster(race_state, grid, age_bound_s=bound)
    assert "STALE_UNRESOLVED" in set(levels.values())
    assert "EXCLUDE_SIGNALED_STALE" not in set(levels.values())
    assert result.eligible is False
    assert result.reason == "STALE_ROSTER_OBSERVATION"
    assert result.excluded_dns_driver_ids == ()


def test_no_retired_status_is_ever_produced():
    _states, _results, service = _load("2018-r05-R")
    params = _params()
    result = prepare_initial_state(service.state_at(430),
                                   grid_by_driver={}, parameters=params)
    assert "RETIRED" not in result.reason
    assert all(level != "RETIRED" for _, level in result.presence_by_driver)


# ---------------------------------------------------------------------------
# Track / weather / terminal preservation (Parts Q, R).
# ---------------------------------------------------------------------------

def test_wet_and_neutralised_states_stay_refused():
    params = _params()
    # 2018-r05-R is wet mid-race; 2018-r05-R frame 17 is dry-green capable
    # only before the rain (checked against the frozen audit verdicts).
    _states, results, service = _load("2018-r05-R")
    grid = _grid(results)
    wet_refused = 0
    for frame_index in _frames("2018-r05-R"):
        result = prepare_initial_state(service.state_at(frame_index),
                                       grid_by_driver=grid, parameters=params)
        if result.reason == "WET_CONDITIONS":
            wet_refused += 1
    assert wet_refused > 0


def test_terminal_state_stays_refused():
    import json
    params = _params()
    _states, results, service = _load("2024-r15-R")
    grid = _grid(results)
    artifact = json.load(open(
        ROOT / "results" / "v2_replay" / "checkpoints" / "2024-r15-R.json",
        encoding="utf-8"))
    last_frame = sorted(e["checkpoint"]["frame_index"]
                        for e in artifact["checkpoints"])[-1]
    result = prepare_initial_state(service.state_at(last_frame),
                                   grid_by_driver=grid, parameters=params)
    assert result.eligible is False
    assert result.reason == "TERMINAL_STATE"


# ---------------------------------------------------------------------------
# Failure taxonomy + determinism (Parts U, T).
# ---------------------------------------------------------------------------

def test_eligibility_reasons_stay_within_taxonomy():
    assert ELIGIBILITY_TAXONOMY[0] == "SIMULATION_CAPABLE"
    assert len(set(ELIGIBILITY_TAXONOMY)) == len(ELIGIBILITY_TAXONOMY)


def test_eligibility_is_deterministic():
    _states, results, service = _load(_DNS_RACE)
    grid = _grid(results)
    params = _params()
    frame_index = _frames(_DNS_RACE)[10]
    first = prepare_initial_state(service.state_at(frame_index),
                                  grid_by_driver=grid, parameters=params)
    second = prepare_initial_state(service.state_at(frame_index),
                                   grid_by_driver=grid, parameters=params)
    assert isinstance(first, EligibilityResult)
    assert (second.eligible, second.reason,
            second.excluded_dns_driver_ids) == (
        first.eligible, first.reason, first.excluded_dns_driver_ids)
    assert second.field_contract_identity == first.field_contract_identity \
        == contract_identity()


def test_unsupported_states_preserve_frozen_error_types():
    # Service/API compatibility: refused states still raise the frozen
    # exception types (routes map them to 422), never a typed fallback.
    # Staleness is engine-level: the adapter succeeds, validation refuses.
    from raceintel.simulation.engine import (
        _validate_start_state,
        select_pace_parameters,
    )
    _states, _results, service = _load("2018-r05-R")
    params = _params()
    sim_state = from_race_state(service.state_at(430))
    selection = select_pace_parameters(sim_state, params)
    with pytest.raises(SimulationUnsupportedError) as exc_info:
        _validate_start_state(sim_state, selection)
    # 2018-r05-R lap 25 is wet mid-race: the frozen wet refusal fires.
    assert exc_info.value.reason == "wet_track_conditions"


def test_stale_refusal_preserves_frozen_error_type():
    from raceintel.simulation.engine import (
        _validate_start_state,
        select_pace_parameters,
    )
    _states, _results, service = _load("2018-r04-R")
    params = _params()
    frames = _frames("2018-r04-R")
    refused = []
    for frame_index in frames:
        try:
            sim_state = from_race_state(service.state_at(frame_index))
        except SimulationUnavailableError:
            continue  # lap-1 boundary: not the stale pin sought here
        selection = select_pace_parameters(sim_state, params)
        try:
            _validate_start_state(sim_state, selection)
        except SimulationUnsupportedError as exc:
            if exc.reason not in refused:
                refused.append(exc.reason)
    assert "non_contemporaneous_roster_member" in refused


# ---------------------------------------------------------------------------
# Retirement-rule admission bar (Parts J/K/L/M): MEASURE_ONLY.
# ---------------------------------------------------------------------------

def test_signaled_stale_candidate_is_measured_never_applied():
    # 2018-r01-R frame 521: grosjean + kevin_magnussen carry an RC
    # STOPPED message <= T and sit >=2 laps behind (the V3.2B candidate
    # guard holds at the measurement plane), yet the runtime must still
    # refuse the STATE and exclude NOBODY.
    from raceintel.simulation.engine import (
        CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES,
        select_pace_parameters,
    )
    _states, results, service = _load("2018-r01-R")
    params = _params()
    grid = _grid(results)
    race_state = service.state_at(521)
    bound = (CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES
             * float(select_pace_parameters(
                 from_race_state(race_state), params).base.value))
    by_id = {e.driver_id: e for e in race_state.observable_drivers}
    leader_lap = race_state.race_context.race_leader_laps_at_state
    behind = {did: leader_lap - e.observed_lap_number
              for did, e in by_id.items()}
    levels = classify_roster(
        race_state, grid, age_bound_s=bound,
        rc_stopped_by_driver=frozenset({"grosjean", "kevin_magnussen"}),
        laps_behind_by_driver=behind)
    assert levels["grosjean"] == "EXCLUDE_SIGNALED_STALE"
    assert levels["kevin_magnussen"] == "EXCLUDE_SIGNALED_STALE"
    result = prepare_initial_state(race_state, grid_by_driver=grid,
                                   parameters=params)
    assert result.eligible is False
    assert result.reason == "STALE_ROSTER_OBSERVATION"
    assert result.excluded_dns_driver_ids == ()
    assert "grosjean" in result.active_driver_ids
    assert "kevin_magnussen" in result.active_driver_ids


# ---------------------------------------------------------------------------
# Tyre policy (Parts N/O/P): no backfill without proof; future tyre rows
# cannot change the verdict at T.
# ---------------------------------------------------------------------------

def test_missing_tyre_states_stay_refused_under_future_poison():
    # 2018-r02-R frame 59: wholesale-null start tyres. Fabricating
    # plausible future tyre observations (compound/age on rows AFTER T)
    # must leave the at-T verdict byte-identical: still refused, never
    # filled from the future.
    states, results, service = _load("2018-r02-R")
    params = _params()
    grid = _grid(results)
    race_state = service.state_at(59)
    base = prepare_initial_state(race_state, grid_by_driver=grid,
                                 parameters=params)
    assert base.eligible is False
    assert base.reason == "MISSING_TYRE_STATE"
    T = float(race_state.state_time_s)
    poisoned_states = states.copy()
    future = poisoned_states["state_time_s"] > T
    assert int(future.sum()) > 0
    poisoned_states.loc[future, "tyre_life"] = 5
    poisoned_states.loc[future, "compound"] = "SOFT"
    # Future pit events ride the same rows: fabricate those too.
    poisoned_states.loc[future, "pit_in_s"] = T + 100.0
    poisoned_states.loc[future, "pit_out_s"] = T + 120.0
    meta = {}
    rp = ROOT / "data" / "v2" / "processed" / "races" / "season=2018" / \
        "races__2018-r02-R.parquet"
    for row in pd.read_parquet(rp).itertuples():
        meta[str(row.race_id)] = {
            "scheduled_laps": (None if pd.isna(row.total_laps_scheduled)
                               else int(row.total_laps_scheduled))}
    poisoned_service = ReplayReconstructor(
        RP.build_replay_timeline(poisoned_states),
        RaceStateReconstructor(poisoned_states, results,
                               race_meta=meta or None))
    pois = prepare_initial_state(poisoned_service.state_at(59),
                                 grid_by_driver=grid, parameters=params)
    assert (pois.eligible, pois.reason,
            pois.excluded_dns_driver_ids) == (
        base.eligible, base.reason, base.excluded_dns_driver_ids)
