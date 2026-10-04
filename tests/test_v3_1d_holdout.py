"""V3.1D holdout-governance tests (source-safe; never touch 2025).

Covers preregistration identity determinism + immutability, FINAL_FIT
season constants, the holdout firewall (opt-in required; V3.1C path
still sealed), the pure acceptance-policy function on synthetic
evidence, verdict serialization, and serving-artifact non-overwrite.
No test here materializes, predicts, or evaluates the holdout.
"""

import json

import pytest

from raceintel.model_lab import v3_dynamics_experiment as V3
from raceintel.model_lab.errors import (
    ExperimentConfigError,
    ProtectedHoldoutError,
)


def _names():
    from raceintel.experiments.feature_sets import canonical_predictive_names
    names_84 = tuple(canonical_predictive_names())
    core = V3.v3_feature_names(V3.ARM_C)
    return names_84, tuple(names_84) + tuple(core)


def test_preregistration_identity_deterministic():
    names_84, names_110 = _names()
    first = V3.build_preregistration(names_84, names_110, "abc123")
    second = V3.build_preregistration(names_84, names_110, "abc123")
    assert first["preregistration_identity"] == \
        second["preregistration_identity"]
    assert len(first["preregistration_identity"]) == 64
    assert "per_race" not in json.dumps(first)
    assert "2025" not in json.dumps(first["arm_a_feature_order"])
    assert first["one_shot"] is True
    assert first["holdout_season"] == 2025
    assert first["training_seasons"] == [2018, 2019, 2020, 2021, 2022,
                                         2023, 2024]


def test_preregistration_spec_immutable():
    names_84, names_110 = _names()
    spec = V3.build_preregistration(names_84, names_110, "abc123")
    assert spec["task"] == "winner"
    assert spec["target"] == "is_winner"
    assert spec["eligibility"] == "eligible_is_winner"
    assert spec["arm_a_feature_set"] == "ALL_84"
    assert spec["arm_b_feature_set"] == "ALL_84_PLUS_V3_1_DYNAMICS_CORE"
    assert len(spec["arm_a_feature_order"]) == 84
    assert len(spec["arm_b_feature_order"]) == 110
    assert spec["variant_a"].startswith("NOT AUTHORIZED")
    assert spec["hyperparameters"]["C"] == 0.01
    assert spec["hyperparameters"]["solver"] == "lbfgs"
    assert spec["hyperparameters"]["max_iter"] == 1000
    assert spec["hyperparameters"]["penalty"] == "l2"
    assert spec["hyperparameters"]["class_weight"] is None
    assert spec["hyperparameters"]["random_state"] == 42
    assert spec["random_seed"] == 42
    assert spec["bootstrap_procedure"]["seed"] == 42
    assert spec["bootstrap_procedure"]["replicates"] == 2000
    assert spec["bootstrap_procedure"]["ci_level"] == 0.95
    assert spec["bootstrap_procedure"]["unit"].startswith("race")


def test_final_fit_seasons_frozen():
    assert V3.V3_FINAL_FIT_SEASONS == (2018, 2019, 2020, 2021, 2022, 2023,
                                       2024)
    assert V3.V3_HOLDOUT_SEASON == 2025
    assert V3.V3_FINAL_FIT_EXPECTED["eligible"] == 162728
    assert V3.V3_HOLDOUT_EXPECTED["eligible"] == 26692
    assert V3.V3_HOLDOUT_EXPECTED["races"] == 24


def test_holdout_requires_explicit_opt_in():
    with pytest.raises(ProtectedHoldoutError):
        V3.materialize_v3_holdout(None)
    # V3.1C development path remains sealed against 2025.
    for bad in ("2025", "HOLDOUT", "FINAL_FIT"):
        with pytest.raises(ProtectedHoldoutError):
            V3.assert_no_holdout_request(bad)
    for good in ("D1", "D2", "D3"):
        V3.assert_no_holdout_request(good)


def test_final_fit_rejects_non_ab_arms():
    with pytest.raises(ExperimentConfigError):
        V3.materialize_v3_final_fit(None, "V3_1_DYNAMICS_CORE", ())
    with pytest.raises(ExperimentConfigError):
        V3.materialize_v3_final_fit(None, "ALL_84_PLUS_VARIANT", ())


def test_acceptance_policy_keep():
    evidence = {
        "primary_delta_b_a": -0.003,
        "bootstrap": {"ci_lo": -0.005, "ci_hi": -0.001},
        "temporal_directions": [-0.003, -0.003, -0.003, -0.003],
        "secondary_deltas": {"brier": -0.001, "roc_auc": 0.002,
                             "pr_auc": 0.01},
        "ece_delta_b_a": -0.001,
        "stage_veto": "PASS",
        "persistent_watch_items": [],
    }
    out = V3.apply_acceptance_policy(evidence)
    assert out["verdict"] == "KEEP"
    assert out["limitations"] == []
    assert out["clause3_temporal_consistency"]["n_improved_of_4"] == 4


def test_acceptance_policy_null_and_reject():
    weak = {
        "primary_delta_b_a": 0.0005,
        "bootstrap": {"ci_lo": -0.002, "ci_hi": 0.003},
        "temporal_directions": [-0.003, -0.003, -0.003, 0.0005],
        "secondary_deltas": {"brier": 0.0002, "roc_auc": -0.001,
                             "pr_auc": 0.001},
        "ece_delta_b_a": 0.0,
        "stage_veto": "PASS",
        "persistent_watch_items": [],
    }
    assert V3.apply_acceptance_policy(weak)["verdict"] == "NULL_RESULT"
    harm = dict(weak, primary_delta_b_a=0.004,
                bootstrap={"ci_lo": 0.001, "ci_hi": 0.007})
    assert V3.apply_acceptance_policy(harm)["verdict"] == "REJECT"
    vetoed = dict(weak, primary_delta_b_a=-0.002,
                  bootstrap={"ci_lo": -0.004, "ci_hi": -0.001},
                  stage_veto="VETO")
    assert V3.apply_acceptance_policy(vetoed)["verdict"] == "REJECT"


def test_acceptance_policy_limitation():
    evidence = {
        "primary_delta_b_a": -0.002,
        "bootstrap": {"ci_lo": -0.005, "ci_hi": 0.001},
        "temporal_directions": [-0.003, -0.003, -0.003, -0.002],
        "secondary_deltas": {"brier": -0.001, "roc_auc": 0.002,
                             "pr_auc": -0.001},
        "ece_delta_b_a": 0.0,
        "stage_veto": "PASS",
        "persistent_watch_items": ["EARLY watch-item persists"],
    }
    out = V3.apply_acceptance_policy(evidence)
    assert out["verdict"] == "KEEP_WITH_LIMITATION"
    assert any("bootstrap" in item for item in out["limitations"])
    assert any("secondar" in item or "pr_auc" in item or "partial" in item
               for item in out["limitations"])
    assert "EARLY watch-item persists" in out["limitations"]


def test_no_probability_normalization_in_spec():
    names_84, names_110 = _names()
    spec = V3.build_preregistration(names_84, names_110, "abc123")
    assert "never normalized" in spec["prediction_semantics"]
    assert V3.V3_MODEL_PARAMETERS["C"] == 0.01


def test_serving_artifact_untouched_helper():
    import hashlib
    from pathlib import Path
    root = Path(V3.__file__).resolve().parent.parent.parent
    serving = root / "results/v2_model_lab/winner_logreg_raw_v1_serving.joblib"
    h = hashlib.sha256()
    with open(serving, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    assert h.hexdigest() == (
        "1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4")


def test_verdict_serialization_round_trip(tmp_path):
    evidence = {
        "primary_delta_b_a": -0.003,
        "bootstrap": {"ci_lo": -0.005, "ci_hi": -0.001},
        "temporal_directions": [-0.003, -0.003, -0.003, -0.003],
        "secondary_deltas": {"brier": -0.001, "roc_auc": 0.002,
                             "pr_auc": 0.01},
        "ece_delta_b_a": -0.001,
        "stage_veto": "PASS",
        "persistent_watch_items": [],
    }
    out = V3.apply_acceptance_policy(evidence)
    path = tmp_path / "verdict.json"
    path.write_text(json.dumps(out, indent=2, sort_keys=True))
    assert json.loads(path.read_text())["verdict"] in (
        "KEEP", "KEEP_WITH_LIMITATION", "NULL_RESULT", "REJECT")
