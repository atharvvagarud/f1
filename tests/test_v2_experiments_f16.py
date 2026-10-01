"""F16 tests: ablation configuration + Phase-3 handoff fixtures.

Configuration-only verification: registry authority, frozen versions,
primary partition, cumulative/LOGO/baseline configurations, interaction
dependency policy, drift rejection, deterministic export, fixture
identity, and the minimal Phase-3 handoff API. No model, no split, no
metric, no matrix rewrite.
"""

import hashlib
import inspect
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from raceintel.config import V2Paths
from raceintel.experiments import feature_sets as A
from raceintel.features import build_f11_registry
from raceintel.features.build_matrix import (
    MATRIX_VERSION,
    content_hash,
    output_dir,
)
from raceintel.features.registry import FEATURE_SET_VERSION
from raceintel.labels.contracts import LABEL_SET_VERSION

ROOT = V2Paths.resolve().root
_OUT = output_dir(V2Paths.resolve())
_HAS_ARTIFACT = (_OUT / "manifest.json").exists()

pytestmark = pytest.mark.skipif(
    not _HAS_ARTIFACT, reason="canonical F15 matrix artifact not present")


@pytest.fixture(scope="session")
def paths():
    return V2Paths.resolve()


@pytest.fixture(scope="session")
def registry():
    return build_f11_registry()


@pytest.fixture(scope="session")
def canonical(paths):
    from raceintel.features.build_matrix import load_matrix
    return load_matrix(paths)


@pytest.fixture(scope="session")
def matrix(canonical):
    return canonical[0]


@pytest.fixture(scope="session")
def manifest(canonical):
    return canonical[1]


# --- frozen versions + config version -------------------------------------

def test_frozen_versions_and_config_version():
    assert FEATURE_SET_VERSION == "v8"
    assert LABEL_SET_VERSION == "v1"
    assert MATRIX_VERSION == "v1"
    assert A.ABLATION_CONFIG_VERSION == "v1"
    assert A.REQUIRED_FEATURE_SET_VERSION == FEATURE_SET_VERSION
    assert A.REQUIRED_LABEL_SET_VERSION == LABEL_SET_VERSION
    assert A.REQUIRED_MATRIX_VERSION == MATRIX_VERSION
    assert A.EXPECTED_PREDICTIVE_FEATURE_COUNT == 84


def test_registry_is_authority(registry):
    A.validate_registry(registry)
    assert len(A.canonical_predictive_names(registry)) == 84
    assert len(build_f11_registry()) == 84


# --- primary partition -----------------------------------------------------

def test_primary_group_counts(registry):
    audit = A.partition_audit(registry)
    assert audit["counts"] == {
        "STATE": 23, "PACE": 12, "GAPS": 8, "FIELD_CONTEXT": 12,
        "RATES_MOMENTUM": 4, "ENVIRONMENT_HISTORY": 9,
        "PRE_RACE_PRIORS": 13, "INTERACTIONS": 3,
    }
    assert audit["total"] == 84


def test_partition_covers_exactly_once(registry):
    audit = A.partition_audit(registry)
    mapping = audit["feature_to_group"]
    canonical = A.canonical_predictive_names(registry)
    assert len(mapping) == 84
    assert set(mapping) == set(canonical)
    assert len(set(mapping.values())) == len(A.PRIMARY_GROUP_ORDER)


def test_resolved_names_only_predictive(registry):
    predictive = set(A.canonical_predictive_names(registry))
    for name in A.all_feature_set_names(registry):
        fs = A.get_feature_set(name, registry)
        assert set(fs.features) <= predictive, name
    for group in A.PRIMARY_GROUP_ORDER:
        assert set(A.group_features(group, registry)) <= predictive


def test_no_label_mask_or_metadata_in_any_config(registry):
    forbidden = set(A.CANONICAL_LABEL_NAMES)
    for col in ("state_id", "driver_id", "race_id", "season", "round_no",
                "state_time_s", "constructor_id", "circuit_id",
                "eligible_is_winner", "eligible_gain_loss",
                "classified_flag"):
        forbidden.add(col)
    for name in A.all_feature_set_names(registry):
        assert not (set(A.get_feature_set(name, registry).features) & forbidden)


def test_factual_vs_derived_placement(registry):
    state = set(A.group_features("STATE", registry))
    pace = set(A.group_features("PACE", registry))
    env = set(A.group_features("ENVIRONMENT_HISTORY", registry))
    # factual stint state -> STATE; derived stint pace -> PACE
    assert {"stint_lap", "pit_stops_completed_so_far",
            "laps_since_last_pit_stop"} <= state
    assert {"current_stint_pace_median_s", "current_stint_pace_trend_s_per_lap",
            "current_stint_eligible_laps", "current_stint_pace_mean_s"} <= pace
    assert not (state & pace)
    # current environment -> STATE; environment history -> ENVIRONMENT_HISTORY
    assert {"wx_air_temp_c", "wx_rainfall", "track_state",
            "flag_safety_car"} <= state
    assert {"air_temp_change_5min_c", "rain_in_last_5min",
            "current_track_state_duration_s",
            "track_state_changes_5min"} <= env
    assert not (state & env)


def test_grid_and_prior_subgroups(registry):
    priors = set(A.group_features("PRE_RACE_PRIORS", registry))
    assert "grid_position" in priors
    grid_sub = set(A.SEMANTIC_SUBGROUPS["GRID_ONLY"])
    hist_sub = set(A.SEMANTIC_SUBGROUPS["HISTORICAL_PRIORS_ONLY"])
    assert grid_sub == {"grid_position"}
    assert grid_sub | hist_sub == priors
    assert not (grid_sub & hist_sub)


# --- interaction dependencies + policy ------------------------------------

def test_interaction_dependency_metadata(registry):
    deps = A.interaction_dependencies(registry)
    assert set(deps) == set(A.REQUIRED_PRIMITIVES)
    assert deps["positions_from_grid"]["required_groups"] == (
        "PRE_RACE_PRIORS", "STATE")
    assert deps["relative_pace_to_ahead_in_traffic_s_per_lap"][
        "required_groups"] == ("FIELD_CONTEXT",)
    assert deps["recent_gap_to_ahead_change_in_traffic_s_per_lap"][
        "required_groups"] == ("FIELD_CONTEXT", "RATES_MOMENTUM")


def test_parent_removal_interaction_policy(registry):
    assert A.interaction_dependencies_for_group("STATE", registry) == (
        "positions_from_grid",)
    assert A.interaction_dependencies_for_group("FIELD_CONTEXT", registry) == (
        "recent_gap_to_ahead_change_in_traffic_s_per_lap",
        "relative_pace_to_ahead_in_traffic_s_per_lap")
    assert A.interaction_dependencies_for_group("RATES_MOMENTUM", registry) == (
        "recent_gap_to_ahead_change_in_traffic_s_per_lap",)
    assert A.interaction_dependencies_for_group("PRE_RACE_PRIORS",
                                                registry) == (
        "positions_from_grid",)
    assert A.interaction_dependencies_for_group("PACE", registry) == ()
    assert A.interaction_dependencies_for_group("GAPS", registry) == ()


# --- cumulative plan -------------------------------------------------------

def test_cumulative_monotonic_exact_additions(registry):
    canonical = set(A.canonical_predictive_names(registry))
    prev = set()
    expected_counts = [23, 35, 43, 55, 59, 68, 81, 84]
    for i, group in enumerate(A.PRIMARY_GROUP_ORDER):
        name = f"CUMULATIVE_{i:02d}_{group}"
        cur = set(A.get_feature_set(name, registry).features)
        assert prev < cur or i == 0, name
        added = cur - prev
        assert added == set(A.group_features(group, registry)), name
        assert len(cur) == expected_counts[i], name
        assert cur <= canonical
        prev = cur
    final = A.get_feature_set("CUMULATIVE_07_INTERACTIONS", registry)
    all84 = A.get_feature_set("ALL_84", registry)
    assert set(final.features) == set(all84.features)


# --- LOGO plan -------------------------------------------------------------

def test_logo_exact_removal(registry):
    order = A.canonical_predictive_names(registry)
    all84 = set(order)
    for group in A.PRIMARY_GROUP_ORDER:
        name = f"ALL_MINUS_{group}"
        removed = set(A.group_features(group, registry))
        removed |= set(A.interaction_dependencies_for_group(group, registry))
        expected = all84 - removed
        got = set(A.get_feature_set(name, registry).features)
        assert got == expected, name
        # no hidden removal
        assert set(order) - got == removed


def test_logo_counts(registry):
    counts = {g: len(A.get_feature_set(f"ALL_MINUS_{g}", registry).features)
              for g in A.PRIMARY_GROUP_ORDER}
    assert counts == {
        "STATE": 60, "PACE": 72, "GAPS": 76, "FIELD_CONTEXT": 70,
        "RATES_MOMENTUM": 79, "ENVIRONMENT_HISTORY": 75,
        "PRE_RACE_PRIORS": 70, "INTERACTIONS": 81,
    }


# --- baselines + ALL_84 ----------------------------------------------------

def test_baseline_exact_names_and_counts(registry):
    order = list(A.canonical_predictive_names(registry))
    current = A.get_feature_set("CURRENT_ORDER_ONLY", registry)
    minimal = A.get_feature_set("MINIMAL_RACE_STATE", registry)
    assert current.features == ("position",)
    assert minimal.features == tuple(
        c for c in order
        if c in {"position", "race_progress_frac", "grid_position"})
    assert set(minimal.features) == {
        "position", "race_progress_frac", "grid_position"}
    assert len(minimal.features) == 3


def test_all_84_matches_manifest(registry, manifest):
    fs = A.get_feature_set("ALL_84", registry)
    assert list(fs.features) == manifest["predictive_columns"]
    assert list(fs.features) == list(A.canonical_predictive_names(registry))
    assert A.resolve_feature_set("ALL_84", manifest) == tuple(
        manifest["predictive_columns"])


def test_configuration_target_independence(registry):
    # No configuration names a label or a task mask; resolution has no
    # target parameter.
    labels = set(A.CANONICAL_LABEL_NAMES)
    for name in A.all_feature_set_names(registry):
        assert not (set(A.get_feature_set(name, registry).features) & labels)
    sig = inspect.signature(A.resolve_feature_set)
    assert "target" not in sig.parameters
    assert "task" not in sig.parameters


# --- resolution API + rejection -------------------------------------------

def test_resolve_preserves_canonical_order(registry, manifest):
    order = list(manifest["predictive_columns"])
    for name in A.all_feature_set_names(registry):
        resolved = A.resolve_feature_set(name, manifest)
        assert list(resolved) == [c for c in order if c in set(resolved)]
        assert resolved == tuple(
            A.get_feature_set(name, registry).features)


def test_resolve_rejects_unknown_config(manifest):
    with pytest.raises(A.AblationConfigError, match="unknown feature set"):
        A.resolve_feature_set("TOTALLY_MADE_UP", manifest)


def test_validate_feature_names_rejections(registry):
    with pytest.raises(A.AblationConfigError, match="duplicate"):
        A.validate_feature_names(["position", "position"], registry)
    with pytest.raises(A.AblationConfigError, match="label"):
        A.validate_feature_names(["is_winner"], registry)
    with pytest.raises(A.AblationConfigError, match="unknown"):
        A.validate_feature_names(["state_id"], registry)
    with pytest.raises(A.AblationConfigError, match="unknown"):
        A.validate_feature_names(["not_a_real_feature"], registry)


def test_unknown_group_rejected(registry):
    with pytest.raises(A.AblationConfigError, match="unknown primary group"):
        A.group_features("NOT_A_GROUP", registry)


# --- drift / mutation rejection -------------------------------------------

def test_manifest_version_and_drift_rejection(manifest, registry):
    preds = list(manifest["predictive_columns"])
    bad = dict(manifest)
    bad["matrix_version"] = "v2"
    with pytest.raises(A.AblationConfigError, match="matrix_version"):
        A.validate_manifest_compatibility(bad, registry)
    bad = dict(manifest)
    bad["feature_set_version"] = "v9"
    with pytest.raises(A.AblationConfigError, match="feature_set_version"):
        A.validate_manifest_compatibility(bad, registry)
    bad = dict(manifest)
    bad["label_set_version"] = "v2"
    with pytest.raises(A.AblationConfigError, match="label_set_version"):
        A.validate_manifest_compatibility(bad, registry)
    bad = dict(manifest)
    bad["predictive_columns"] = preds[:-1]
    with pytest.raises(A.AblationConfigError):
        A.validate_manifest_compatibility(bad, registry)
    bad = dict(manifest)
    bad["predictive_columns"] = preds + ["fake_extra_feature"]
    with pytest.raises(A.AblationConfigError):
        A.validate_manifest_compatibility(bad, registry)
    bad = dict(manifest)
    bad["label_columns"] = list(manifest["label_columns"]) + [preds[0]]
    with pytest.raises(A.AblationConfigError, match="forbidden"):
        A.validate_manifest_compatibility(bad, registry)


def test_registry_drift_rejection(registry, monkeypatch):
    # extra predictive definition -> 85, rejected (fresh registry: do not
    # mutate the session-scoped one)
    reg = build_f11_registry()
    extra = replace(next(d for d in reg if d.predictive_eligible),
                    name="zz_f16_injected_feature")
    reg.register(extra)
    with pytest.raises(A.AblationConfigError, match="predictive feature count"):
        A.validate_registry(reg)
    # required-version drift rejected
    monkeypatch.setattr(A, "REQUIRED_FEATURE_SET_VERSION", "v9")
    with pytest.raises(A.AblationConfigError, match="FEATURE_SET_VERSION"):
        A.validate_registry(build_f11_registry())


def test_interaction_dependency_unknown_feature_rejected(registry, monkeypatch):
    bogus = dict(A.REQUIRED_PRIMITIVES)
    bogus["fake_interaction"] = ("position", "nonexistent_primitive")
    monkeypatch.setattr(A, "REQUIRED_PRIMITIVES", bogus)
    with pytest.raises(A.AblationConfigError, match="unknown/unpartitioned"):
        A.interaction_dependencies(registry)


# --- deterministic export / hash ------------------------------------------

def test_config_hash_deterministic_and_repeated_export_identical(registry):
    c1 = A.ablation_config_dict(registry)
    c2 = A.ablation_config_dict(registry)
    assert c1 == c2
    assert c1["config_hash"] == c2["config_hash"]
    assert A.semantic_hash(registry) == c1["config_hash"]
    assert A.render_ablation_config(registry) == \
        A.render_ablation_config(registry)


def test_machine_readable_export_shape(registry):
    cfg = A.ablation_config_dict(registry)
    for key in ("ablation_config_version", "required_feature_set_version",
                "required_label_set_version", "required_matrix_version",
                "primary_groups", "named_feature_sets",
                "cumulative_configurations", "logo_configurations",
                "baseline_configurations", "all_feature_set",
                "interaction_dependencies", "interaction_policy",
                "config_hash", "fixtures", "partition_audit"):
        assert key in cfg, key
    assert cfg["all_feature_set"] == "ALL_84"
    assert cfg["total_predictive_features"] == 84
    assert cfg["named_feature_sets"]["ALL_84"]["feature_count"] == 84
    assert len(cfg["fixtures"]) == len(A.FIXTURES)


def test_export_has_no_predictions_or_metrics(registry):
    blob = A.render_ablation_config(registry)
    for token in ("logloss", "log_loss", "brier", "shap", "accuracy",
                  "prediction", "probability", "feature_importance"):
        assert token not in blob.lower(), token


def test_no_matrix_rewrite(paths, manifest, tmp_path):
    pq = _OUT / "model_matrix.parquet"
    mf = _OUT / "manifest.json"
    before_pq = hashlib.sha256(pq.read_bytes()).hexdigest()
    before_mf = hashlib.sha256(mf.read_bytes()).hexdigest()
    A.write_ablation_config(paths, out_dir=tmp_path)
    assert hashlib.sha256(pq.read_bytes()).hexdigest() == before_pq
    assert hashlib.sha256(mf.read_bytes()).hexdigest() == before_mf
    from raceintel.features.build_matrix import load_matrix
    _, m = load_matrix(paths)
    assert m["content_hash"] == manifest["content_hash"]


def test_ablation_config_does_not_mutate_matrix_content(matrix, manifest):
    assert content_hash(matrix) == manifest["content_hash"]


# --- fixtures --------------------------------------------------------------

def test_fixtures_exist_unique_with_stable_ids():
    names = [f.name for f in A.FIXTURES]
    ids = [f.state_id for f in A.FIXTURES]
    assert len(names) == len(set(names))
    assert len(ids) == len(set(ids))
    for fx in A.FIXTURES:
        assert fx.state_id == f"{fx.race_id}|{fx.driver_id}|{fx.lap_number}"
        assert isinstance(fx.season, int) and isinstance(fx.lap_number, int)


def test_fixture_resolution_and_validation(matrix, manifest):
    report = A.validate_fixtures(matrix, manifest)
    assert len(report) == len(A.FIXTURES) == 11
    assert A.resolve_fixture("era_2025_dry_late").state_id == \
        "2025-r01-R|norris|41"
    with pytest.raises(A.AblationConfigError, match="unknown fixture"):
        A.resolve_fixture("no_such_fixture")


def test_fixture_identity_agreement(matrix, manifest):
    for fx in A.FIXTURES:
        row = matrix.loc[matrix["state_id"] == fx.state_id].iloc[0]
        assert str(row["race_id"]) == fx.race_id
        assert str(row["driver_id"]) == fx.driver_id
        assert int(row["season"]) == fx.season
        assert int(row["round_no"]) == fx.round_no
        assert int(row["lap_number"]) == fx.lap_number
        assert str(row["constructor_id"]) == fx.constructor_id


def test_fixture_coverage_is_representative():
    tags = set()
    for fx in A.FIXTURES:
        tags |= set(fx.coverage)
    assert {"2018", "2025", "early", "mid", "late", "wet", "dry",
            "caution", "partial", "rookie", "pit_lane"} <= tags


def test_fixtures_have_no_split_or_prediction_fields():
    split_tokens = {"train", "val", "valid", "validation", "test",
                    "holdout", "split", "fold", "evaluation"}
    for fx in A.FIXTURES:
        payload = A._fixture_dict(fx) if hasattr(A, "_fixture_dict") else {}
        lowered = {k.lower() for k in payload}
        assert not (lowered & split_tokens)
        assert "prediction" not in " ".join(lowered)
        assert "metric" not in " ".join(lowered)
    assert not (A._fixture_dict(A.FIXTURES[0])["expected_masks"] is None)


def test_fixture_state_disappears_fails(matrix, manifest):
    empty = matrix.head(0).copy()
    with pytest.raises(A.AblationConfigError, match="resolved 0 rows"):
        A.validate_fixtures(empty, manifest)


# --- scope: no model / preprocessing / matrix rewrite ----------------------

def test_no_estimator_or_preprocessing_code():
    src = inspect.getsource(A)
    for banned in ("sklearn", "xgboost", "lightgbm", "catboost",
                   "train_test_split", "cross_val", "GridSearchCV",
                   ".fit(", ".predict(", "StandardScaler", "OneHotEncoder",
                   "fillna", "imputer", "resample", "log_loss", "brier"):
        assert banned not in src, banned


# --- Phase-3 handoff API ---------------------------------------------------

def test_phase3_handoff_api(paths, manifest):
    resolved = A.resolve_feature_set("MINIMAL_RACE_STATE", manifest)
    assert set(resolved) == {"position", "race_progress_frac", "grid_position"}
    fx = A.resolve_fixture("stage_mid_dry_2023")
    assert fx.season == 2023 and fx.lap_number == 28
    X, y, mask = A.load_task("winner", paths, with_metadata=False)
    assert list(X.columns) == manifest["predictive_columns"]
    assert len(mask) == manifest["row_count"]
    mat, man = A.load_canonical_matrix(paths)
    assert len(mat) == man["row_count"] == 189420
