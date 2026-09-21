"""Phase-6 R3 tests — empirical parameter layer.

Covers eligibility, filtering, temporal cutoff / 2025 exclusion, grouping and
support/fallback metadata, parameter validity, the adopted/deferred effect
decisions, residual model, pit/stint/transition distributions, artifact
determinism, hash validation and tamper rejection, read-only loading, future
poisoning, in-window mutation sensitivity, the label/model firewall, and R1
``ParameterIdentity`` integration.

Estimation tests run on a small hermetic copy of 2018-2019 canonical data so
they are fast and never touch 2025 or the frozen stack.
"""

from __future__ import annotations

import ast
import json
import shutil
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pytest

from v2.config import V2Paths
from v2.simulation.config import (
    Assumptions,
    ParameterIdentity,
    SimulationConfig,
    simulation_request_identity,
)
from v2.simulation.errors import (
    SimulationContractError,
    SimulationValidationError,
)
from v2.simulation.estimator import (
    D9_COLUMNS,
    eligibility_funnel,
    eligible_laps,
    estimate_simulation_parameters,
)
from v2.simulation.params import (
    FAMILY_NAMES,
    SimulationParameterSet,
    SupportEntry,
    load_simulation_parameters,
    parameter_storage_dir,
)
from v2.simulation.state import (
    DriverSimState,
    SimulationEnvironment,
    SimulationState,
)

REPO_ROOT = Path(__file__).resolve().parents[1]
CANON = REPO_ROOT / "data" / "v2" / "processed"
SEASONS = (2018, 2019)
ENTITIES = ("driver_lap_state_d9", "stints", "pit_stops", "races")


# ---------------------------------------------------------------------------
# Fixtures / helpers.
# ---------------------------------------------------------------------------

def _make_root(root: Path, seasons=SEASONS) -> Path:
    for entity in ENTITIES:
        for season in seasons:
            src = CANON / entity / f"season={season}"
            if not src.is_dir():
                continue
            dst = root / "data" / "v2" / "processed" / entity / f"season={season}"
            if not dst.exists():
                shutil.copytree(src, dst)
    return root


@pytest.fixture(scope="session")
def dataset_root(tmp_path_factory):
    return _make_root(tmp_path_factory.mktemp("r3_dataset"))


@pytest.fixture(scope="session")
def paths(dataset_root):
    return V2Paths.from_root(dataset_root)


@pytest.fixture(scope="session")
def params2018(paths):
    return estimate_simulation_parameters(paths, through_season=2018)


@pytest.fixture(scope="session")
def params2019(paths):
    return estimate_simulation_parameters(paths, through_season=2019)


def _d9_row(**over) -> dict:
    base = {
        "race_id": "2019-r01-R", "season": 2019, "circuit_id": "bahrain",
        "driver_id": "d1", "constructor_id": "c1", "lap_number": 5,
        "lap_time_s": 90.0, "compound": "MEDIUM", "tyre_life": 3,
        "stint_number": 1, "pit_in_s": None, "pit_out_s": None,
        "track_state": "all_clear", "is_accurate": True, "deleted": False,
        "race_leader_laps_at_state": 10, "wx_rainfall": False,
    }
    base.update(over)
    return base


def _d9(rows) -> pd.DataFrame:
    return pd.DataFrame(rows, columns=list(D9_COLUMNS))


# ---------------------------------------------------------------------------
# R3-B eligibility rule.
# ---------------------------------------------------------------------------

def test_eligible_base_lap_is_eligible():
    assert len(eligible_laps(_d9([_d9_row()]))) == 1


@pytest.mark.parametrize("over", [
    {"pit_in_s": 1000.0},
    {"pit_out_s": 1005.0},
    {"track_state": "safety_car"},
    {"track_state": "vsc"},
    {"track_state": "vsc_ending"},
    {"track_state": "red_flag"},
    {"track_state": "yellow"},
    {"track_state": None},
    {"lap_number": 1},
    {"is_accurate": False},
    {"deleted": True},
    {"compound": None},
    {"compound": "INTERMEDIATE"},
    {"compound": "WET"},
    {"tyre_life": None},
    {"lap_time_s": None},
    {"lap_time_s": 0.0},
    {"lap_time_s": -5.0},
    {"wx_rainfall": True},
])
def test_eligibility_exclusions(over):
    assert len(eligible_laps(_d9([_d9_row(**over)]))) == 0


def test_eligibility_funnel_counts_each_reason():
    rows = [
        _d9_row(),                                  # eligible
        _d9_row(pit_in_s=1.0),                      # pit
        _d9_row(track_state="safety_car"),          # neutralized
        _d9_row(lap_number=1),                      # opening lap
        _d9_row(is_accurate=False),                 # timing anomaly
        _d9_row(deleted=True),                      # deleted
        _d9_row(compound="WET"),                    # wet regime
        _d9_row(wx_rainfall=True),                  # rainfall
        _d9_row(lap_time_s=None),                   # missing time
    ]
    funnel = eligibility_funnel(_d9(rows))
    assert funnel["total_rows"] == 9
    assert funnel["no_rainfall"] == 1
    assert funnel["excluded_pit_marker"] == 1
    assert funnel["excluded_not_green"] == 1
    assert funnel["excluded_lap_1"] == 1
    assert funnel["excluded_wet_compound_or_missing"] == 1
    assert funnel["excluded_rainfall"] == 1
    assert funnel["excluded_deleted"] >= 1
    assert funnel["excluded_inaccurate"] >= 1


def test_eligibility_is_stricter_than_f5_on_accurate_deleted():
    rows = [_d9_row(is_accurate=False), _d9_row(deleted=True)]
    assert len(eligible_laps(_d9(rows))) == 0


# ---------------------------------------------------------------------------
# R3-C temporal boundary / 2025 firewall.
# ---------------------------------------------------------------------------

def test_through_season_2025_rejected(paths):
    with pytest.raises(ValueError):
        estimate_simulation_parameters(paths, through_season=2025)


def test_through_season_below_2018_rejected(paths):
    with pytest.raises(ValueError):
        estimate_simulation_parameters(paths, through_season=2017)


def test_estimation_seasons_are_window_bounded(params2018, params2019):
    assert params2018.estimation_seasons == (2018,)
    assert params2019.estimation_seasons == (2018, 2019)
    assert params2018.through_season == 2018


def test_2025_file_present_is_not_estimated(tmp_path):
    root = _make_root(tmp_path / "proj")
    src2025 = (CANON / "driver_lap_state_d9" / "season=2025"
               / "driver_lap_state_d9__d9-2025.parquet")
    if src2025.exists():
        dst = (root / "data" / "v2" / "processed" / "driver_lap_state_d9"
               / "season=2025" / src2025.name)
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src2025, dst)
    parameter_set = estimate_simulation_parameters(
        V2Paths.from_root(root), through_season=2019)
    assert max(parameter_set.estimation_seasons) == 2019
    expected_rows = sum(
        len(pd.read_parquet(
            CANON / "driver_lap_state_d9" / f"season={s}"
            / f"driver_lap_state_d9__d9-{s}.parquet"))
        for s in (2018, 2019))
    assert parameter_set.diagnostics["rows_total"] == expected_rows


def test_parameter_set_rejects_2025_through_season(params2018):
    payload = params2018.to_dict()
    payload["through_season"] = 2025
    with pytest.raises(SimulationValidationError):
        SimulationParameterSet.from_dict(payload)


def test_parameter_set_rejects_season_outside_era(params2018):
    payload = params2018.to_dict()
    payload["estimation_seasons"] = [2018, 2025]
    with pytest.raises(SimulationValidationError):
        SimulationParameterSet.from_dict(payload)


# ---------------------------------------------------------------------------
# R3-D artifact contract / R3-T support metadata.
# ---------------------------------------------------------------------------

def test_all_families_present(params2018):
    assert set(params2018.families) == set(FAMILY_NAMES)


def test_every_entry_exposes_support(params2019):
    for name, family in params2019.families.items():
        for key, entry in family.entries.items():
            assert entry.sample_count >= 0, (name, key)
            assert entry.support_level in ("strong", "weak", "unavailable")
            assert entry.fallback_level in (
                "exact", "circuit", "season", "era", "compound", "global",
                "deferred", "none")
            assert entry.identifiability in ("identified", "weak", "deferred")
            if entry.is_distribution:
                assert len(entry.probabilities) == len(entry.quantile_values)
                assert all(b > a for a, b in
                           zip(entry.probabilities, entry.probabilities[1:]))
                if entry.std is not None:
                    assert entry.std >= 0.0


def test_distribution_values_are_ordered(params2019):
    for family in params2019.families.values():
        for entry in family.entries.values():
            if entry.is_distribution and len(entry.quantile_values) > 1:
                vals = entry.quantile_values
                assert all(b >= a for a, b in zip(vals, vals[1:]))


def test_loader_lookup_returns_support_entry(params2019):
    entry = params2019.lookup("race_progress_slope_s_per_lap", "global")
    assert isinstance(entry, SupportEntry)
    assert entry.sample_count > 0


def test_unknown_family_and_key_rejected(params2019):
    with pytest.raises(SimulationContractError):
        params2019.family("no_such_family")
    with pytest.raises(SimulationValidationError):
        params2019.lookup("pace_base_s", "no_such_key")


# ---------------------------------------------------------------------------
# R3-H grouping / fallback hierarchy.
# ---------------------------------------------------------------------------

def test_pace_base_hierarchy(params2019):
    base = params2019.family("pace_base_s").entries
    fallback = params2019.family("pace_base_fallback_s").entries
    assert base and all("|" in k for k in base)
    assert any("|" not in k for k in fallback)  # circuit-level
    assert "global" in fallback
    assert fallback["global"].support_level == "weak"


def test_constructor_offset_hierarchy(params2019):
    entries = params2019.family("constructor_pace_offset_s").entries
    assert "global" in entries
    assert any(k.endswith("|2018-2021") or k.endswith("|2022-2024")
               for k in entries)
    assert any(k.rsplit("|", 1)[-1].isdigit() for k in entries)


def test_pit_hierarchy(params2019):
    effective = params2019.family("pit_effective_loss_s").entries
    assert "global" in effective
    assert effective["global"].is_distribution


def test_stint_length_hierarchy(params2019):
    entries = params2019.family("stint_length_laps").entries
    assert "global" in entries
    assert any(k.count("|") == 1 for k in entries)  # era|compound


def test_transition_has_global_fallback(params2019):
    entries = params2019.family(
        "compound_transition_probability").entries
    assert any(k.startswith("GLOBAL->") for k in entries)


# ---------------------------------------------------------------------------
# Adopted / deferred effect decisions.
# ---------------------------------------------------------------------------

def test_race_progress_trend_is_negative(params2019):
    for key in ("global", "2018-2021"):
        entry = params2019.lookup("race_progress_slope_s_per_lap", key)
        assert entry.value < 0.0


def test_degradation_is_positive_but_marked_weak(params2019):
    for entry in params2019.family(
            "degradation_slope_s_per_lap").entries.values():
        assert entry.value > 0.0
        assert entry.identifiability == "weak"


def test_compound_offset_is_deferred_with_no_fabricated_precision(params2019):
    entries = params2019.family("compound_offset_s").entries
    assert entries
    for entry in entries.values():
        assert entry.identifiability == "deferred"
        assert entry.fallback_level == "deferred"
        assert entry.value is None
        assert not entry.is_distribution
    assert params2019.diagnostics["compound_effect_policy"] == \
        "deferred_confounded"


def test_diagnostics_expose_compound_weak_estimates(params2018):
    observed = params2018.diagnostics["compound_effect_observed_weak"]
    assert isinstance(observed, dict)


# ---------------------------------------------------------------------------
# R3-L/M residual model.
# ---------------------------------------------------------------------------

def test_residual_distribution_is_heavy_tailed(params2019):
    entry = params2019.lookup("lap_residual_distribution_s", "global")
    assert entry.is_distribution
    # Robust core scale is well below the full std: heavy tails.
    assert entry.mad < entry.std


def test_residual_is_centered_near_zero(params2019):
    entry = params2019.lookup("lap_residual_distribution_s", "global")
    probs = list(entry.probabilities)
    vals = list(entry.quantile_values)
    median = vals[probs.index(0.5)]
    assert abs(median) < 0.5


def test_residual_independence_is_documented(params2019):
    note = params2019.diagnostics["residual_independence"]
    assert "assumption" in note and "limitation" in note
    assert note["measured_within_driver_race_lag1_autocorr"] > 0.0


# ---------------------------------------------------------------------------
# R3-N/O/P pit, stint, transition parameters.
# ---------------------------------------------------------------------------

def test_pit_transit_distribution_plausible(params2019):
    entry = params2019.lookup("pit_lane_transit_s", "global")
    assert entry.is_distribution
    assert 10.0 < entry.observed_min < entry.observed_max < 200.0
    assert 10.0 < entry.quantile_values[
        list(entry.probabilities).index(0.5)] < 60.0


def test_pit_effective_loss_distribution_plausible(params2019):
    entry = params2019.lookup("pit_effective_loss_s", "global")
    assert entry.is_distribution
    assert entry.quantile_values[
        list(entry.probabilities).index(0.5)] > 5.0


def test_stint_length_distribution_plausible(params2019):
    entry = params2019.lookup("stint_length_laps", "global")
    assert entry.is_distribution
    assert 1.0 <= entry.observed_min
    assert 5.0 < entry.quantile_values[
        list(entry.probabilities).index(0.5)] < 40.0


def test_compound_transitions_sum_to_one(params2019):
    entries = params2019.family(
        "compound_transition_probability").entries
    totals: dict = defaultdict(float)
    for entry in entries.values():
        assert 0.0 < entry.value <= 1.0
        totals[entry.group_key] += entry.value
    for current, total in totals.items():
        assert abs(total - 1.0) < 1e-9, current


# ---------------------------------------------------------------------------
# R3-W determinism.
# ---------------------------------------------------------------------------

def test_rebuild_is_byte_identical(paths, params2019):
    again = estimate_simulation_parameters(paths, through_season=2019)
    assert again.to_json() == params2019.to_json()
    assert again.scientific_hash() == params2019.scientific_hash()


def test_cutoff_changes_identity(params2018, params2019):
    assert params2018.scientific_hash() != params2019.scientific_hash()
    assert params2018.parameter_version != params2019.parameter_version


def test_creation_metadata_excluded_from_hash(params2019):
    altered = SimulationParameterSet.from_dict(params2019.to_dict())
    payload = params2019.to_dict()
    payload["creation_metadata"] = {"created_at_utc": "2099-01-01T00:00:00Z"}
    rebuilt = SimulationParameterSet.from_dict(payload)
    assert rebuilt.scientific_hash() == altered.scientific_hash()


# ---------------------------------------------------------------------------
# R3-U loader / R3-AC validation / tamper rejection.
# ---------------------------------------------------------------------------

def _write_manifest(tmp_path, parameter_set) -> Path:
    out = tmp_path / "manifest.json"
    out.write_text(parameter_set.to_json() + "\n", encoding="utf-8")
    return out


def test_loader_roundtrip(params2018, tmp_path):
    path = _write_manifest(tmp_path, params2018)
    loaded = load_simulation_parameters(path)
    assert loaded.scientific_hash() == params2018.scientific_hash()
    assert loaded.parameter_identity().to_dict() == \
        params2018.parameter_identity().to_dict()


def test_loader_accepts_directory(params2018, tmp_path):
    _write_manifest(tmp_path, params2018)
    loaded = load_simulation_parameters(tmp_path)
    assert loaded.scientific_hash() == params2018.scientific_hash()


def test_loader_is_read_only(params2018, tmp_path):
    path = _write_manifest(tmp_path, params2018)
    before = path.read_bytes()
    files_before = sorted(p.name for p in tmp_path.iterdir())
    load_simulation_parameters(path)
    assert path.read_bytes() == before
    assert sorted(p.name for p in tmp_path.iterdir()) == files_before


def test_tampered_value_rejected(params2018, tmp_path):
    payload = params2018.to_dict()
    payload["families"]["degradation_slope_s_per_lap"]["entries"][
        "global"]["value"] = 999.0
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SimulationValidationError):
        load_simulation_parameters(path)


def test_missing_hash_rejected(params2018, tmp_path):
    payload = params2018.to_dict()
    payload.pop("scientific_hash")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SimulationValidationError):
        load_simulation_parameters(path)


def test_wrong_contract_version_rejected(params2018, tmp_path):
    payload = params2018.to_dict()
    payload["parameter_contract_version"] = "r9-vX"
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SimulationContractError):
        load_simulation_parameters(path)


def test_missing_family_rejected(params2018, tmp_path):
    payload = params2018.to_dict()
    payload["families"].pop("pace_base_s")
    path = tmp_path / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(SimulationValidationError):
        load_simulation_parameters(path)


def test_nonfinite_value_rejected():
    with pytest.raises(SimulationValidationError):
        SupportEntry(group_key="g", sample_count=1, support_level="weak",
                     fallback_level="global", value=float("inf"))


def test_invalid_support_level_rejected():
    with pytest.raises(SimulationContractError):
        SupportEntry(group_key="g", sample_count=1, support_level="bogus",
                     fallback_level="global", value=1.0)


def test_entry_without_value_or_distribution_rejected():
    with pytest.raises(SimulationValidationError):
        SupportEntry(group_key="g", sample_count=1, support_level="weak",
                     fallback_level="global")


def test_storage_dir_is_generated_data_path(params2018):
    directory = parameter_storage_dir(REPO_ROOT, 2024)
    assert directory.as_posix().endswith(
        "data/v2/simulation/params/r3-v1__through-2024")


# ---------------------------------------------------------------------------
# R3-X temporal adversarial: future poisoning + in-window mutation.
# ---------------------------------------------------------------------------

def _mutate_d9_lap_times(root: Path, season: int) -> None:
    directory = root / "data" / "v2" / "processed" / "driver_lap_state_d9" \
        / f"season={season}"
    for path in directory.glob("*.parquet"):
        frame = pd.read_parquet(path)
        frame["lap_time_s"] = frame["lap_time_s"] * 1.5
        frame.to_parquet(path, index=False)


def test_future_poisoning_does_not_change_identity(tmp_path):
    root = _make_root(tmp_path / "proj")
    before = estimate_simulation_parameters(
        V2Paths.from_root(root), through_season=2018)
    _mutate_d9_lap_times(root, 2019)
    after = estimate_simulation_parameters(
        V2Paths.from_root(root), through_season=2018)
    assert after.scientific_hash() == before.scientific_hash()
    assert after.to_json() == before.to_json()


def test_in_window_mutation_changes_identity(tmp_path):
    root = _make_root(tmp_path / "proj")
    before = estimate_simulation_parameters(
        V2Paths.from_root(root), through_season=2018)
    _mutate_d9_lap_times(root, 2018)
    after = estimate_simulation_parameters(
        V2Paths.from_root(root), through_season=2018)
    assert after.scientific_hash() != before.scientific_hash()


def test_in_window_stint_mutation_changes_identity(tmp_path):
    root = _make_root(tmp_path / "proj")
    before = estimate_simulation_parameters(
        V2Paths.from_root(root), through_season=2018)
    directory = root / "data" / "v2" / "processed" / "stints" / "season=2018"
    for path in directory.glob("*.parquet"):
        frame = pd.read_parquet(path)
        frame["end_lap"] = frame["end_lap"] + 5
        frame.to_parquet(path, index=False)
    after = estimate_simulation_parameters(
        V2Paths.from_root(root), through_season=2018)
    assert after.scientific_hash() != before.scientific_hash()


# ---------------------------------------------------------------------------
# R3-Y/R3-Z firewalls.
# ---------------------------------------------------------------------------

def _import_modules(path: Path) -> set:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                modules.add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                modules.add(node.module)
    return modules


def test_runtime_loader_is_stdlib_only():
    modules = _import_modules(REPO_ROOT / "v2" / "simulation" / "params.py")
    roots = {m.split(".")[0] for m in modules}
    assert roots <= {"__future__", "collections", "json", "math", "dataclasses",
                     "pathlib", "typing", "v2"}


@pytest.mark.parametrize("module", [
    "v2/model_lab", "v2/prediction", "v2/replay", "v2/replay_predictions",
    "v2/replay_probability_timeline", "api", "sklearn", "joblib", "fastapi",
])
def test_parameter_layer_has_no_forbidden_imports(module):
    for rel in ("v2/simulation/params.py", "v2/simulation/estimator.py",
                "scripts/build_simulation_parameters.py"):
        modules = _import_modules(REPO_ROOT / rel)
        assert not any(m == module or m.startswith(module + ".")
                       for m in modules), (rel, module)


def test_parameter_layer_source_has_no_label_or_model_coupling():
    forbidden = ("race_driver_labels", "winner_logreg", "is_winner",
                 "final_position", "replay_prediction", "model_lab")
    for rel in ("v2/simulation/params.py", "v2/simulation/estimator.py"):
        text = (REPO_ROOT / rel).read_text(encoding="utf-8")
        for token in forbidden:
            assert token not in text, (rel, token)


def test_estimator_never_reads_labels(tmp_path):
    # Estimation over a root that contains no labels/results works and the
    # source-data fingerprint names only state/stint/pit/race entities.
    root = _make_root(tmp_path / "proj")
    parameter_set = estimate_simulation_parameters(
        V2Paths.from_root(root), through_season=2018)
    assert set(parameter_set.source_data) == {
        "driver_lap_state_d9", "stints", "pit_stops", "races"}


# ---------------------------------------------------------------------------
# R3-AB: effects that must NOT be estimated here.
# ---------------------------------------------------------------------------

def test_no_out_of_scope_families():
    lowered = " ".join(FAMILY_NAMES).lower()
    for token in ("overtake", "traffic", "reliability", "safety_car",
                  "vsc", "weather", "strategy"):
        assert token not in lowered


# ---------------------------------------------------------------------------
# R3-E R1 ParameterIdentity integration.
# ---------------------------------------------------------------------------

def test_parameter_identity_is_r1_seam(params2019):
    identity = params2019.parameter_identity()
    assert isinstance(identity, ParameterIdentity)
    assert identity.supplied
    assert identity.parameter_set_id == params2019.parameter_set_id
    assert identity.parameter_hash == params2019.scientific_hash()
    assert identity.parameter_version == params2019.parameter_version


def test_parameter_identity_changes_request_identity(params2019):
    state = SimulationState(
        race_id="2023-r01-R", scheduled_laps=57, leader_laps_done=10,
        simulation_time_s=1000.0,
        drivers=(DriverSimState(driver_id="d1", lap_number=10,
                                race_time_s=1000.0),),
        environment=SimulationEnvironment(track_state="all_clear"),
    )
    config = SimulationConfig(simulation_count=10, master_seed=7)
    assumptions = Assumptions()
    without = simulation_request_identity(
        state, config, assumptions, ParameterIdentity.contract_only())
    with_params = simulation_request_identity(
        state, config, assumptions, params2019.parameter_identity())
    assert without != with_params


# ---------------------------------------------------------------------------
# R3-AF performance (generous bounds; recorded elsewhere).
# ---------------------------------------------------------------------------

def test_loader_latency_is_small(params2019, tmp_path):
    import time
    path = _write_manifest(tmp_path, params2019)
    start = time.perf_counter()
    for _ in range(20):
        load_simulation_parameters(path)
    elapsed = (time.perf_counter() - start) / 20
    assert elapsed < 1.0


def test_full_artifact_build_is_seconds_scale():
    # Recorded indicative bound; the estimator is offline and not on the
    # request path. 2018-2019 is a small slice.
    import time
    root = Path(REPO_ROOT)
    paths = V2Paths.from_root(root)
    start = time.perf_counter()
    estimate_simulation_parameters(paths, through_season=2018)
    assert time.perf_counter() - start < 120.0
