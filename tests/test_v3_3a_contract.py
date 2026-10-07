"""V3.3A experiment-contract tests (source-safe, corpus-independent).

Validates the frozen V3.3 contract against the Model Lab constitution:
parent/baseline/task/feature/fold identities, the 2025 firewall, metric
and statistical-unit rules, family uniqueness, budget bounds, OOF schema,
advancement limits, artifact metadata requirements, and contract-hash
determinism. No corpus reads, no 2025 access, no training.
"""
import hashlib
import json
from pathlib import Path

import pytest

from raceintel.model_lab import protocol as P
from raceintel.model_lab import splits as S
from raceintel.model_lab import tasks as T
from raceintel.model_lab.aggregation import race_macro
from raceintel.model_lab.errors import ProtectedHoldoutError

CONTRACT_PATH = Path("results/v3/v3_3a/experiment_contract.json")
FROZEN_PARENT_COMMIT = "197979d40af0c9dbf90667781d9c83e41613b047"
FROZEN_PARENT_TAG = "v3.2-monte-carlo-2"
BASELINE_SHA = "9a1aac515d12c4e86ac369977392f74394cf7f6853b8e89d948bcdec28f58960"


@pytest.fixture(scope="module")
def contract():
    return json.loads(CONTRACT_PATH.read_text())


def test_parent_identity(contract):
    assert contract["parent"]["tag"] == FROZEN_PARENT_TAG
    assert contract["parent"]["commit"] == FROZEN_PARENT_COMMIT


def test_baseline_identity(contract):
    base = contract["baseline"]
    assert base["stage"] == "V3.1B"
    assert base["hyperparameters"]["C"] == 0.01
    assert base["hyperparameters"]["random_state"] == 42
    assert base["feature_set"] == "ALL_84_PLUS_V3_1_DYNAMICS_CORE"
    assert base["feature_count"] == 110
    assert base["artifact_sha256"] == BASELINE_SHA


def test_task_identity(contract):
    assert contract["task"]["name"] == "winner"
    assert contract["task"]["probability_semantics"] == "INDEPENDENT_BINARY"
    resolved = T.resolve_task("winner")
    assert resolved.label_column == contract["task"]["label_column"]
    assert resolved.eligibility_mask == contract["task"]["eligibility_mask"]
    assert resolved.probability_semantics == "INDEPENDENT_BINARY"


def test_feature_contract(contract):
    assert contract["feature_arms"]["primary_count"] == 110
    assert contract["feature_arms"]["diagnostic_control"] == "ALL_84"
    assert contract["feature_arms"]["diagnostic_count"] == 84
    assert P.EXPECTED_PREDICTIVE_COUNT == 84


def test_fold_identity(contract):
    folds = contract["temporal_folds"]
    assert folds["D1"]["train"] == [2018, 2019, 2020, 2021]
    assert folds["D1"]["validate"] == [2022]
    assert folds["D2"]["validate"] == [2023]
    assert folds["D3"]["validate"] == [2024]
    assert 2025 not in folds["D1"]["train"] + folds["D1"]["validate"]
    assert 2025 not in folds["D2"]["train"] + folds["D2"]["validate"]
    assert 2025 not in folds["D3"]["train"] + folds["D3"]["validate"]
    for spec in S.development_splits():
        assert P.PROTECTED_HOLDOUT_SEASON not in spec.train_seasons
        assert P.PROTECTED_HOLDOUT_SEASON not in spec.validation_seasons
    counts = S.M0_FOLD_STATE_COUNTS
    assert (counts["D1"] == (88123, 23577) and counts["D2"] == (111700, 24422)
            and counts["D3"] == (136122, 26606))


def test_holdout_firewall():
    with pytest.raises(ProtectedHoldoutError):
        S.get_split("HOLDOUT")
    with pytest.raises(ProtectedHoldoutError):
        S.get_split("HOLDOUT", allow_protected_holdout=False)
    holdout = S.get_split("HOLDOUT", allow_protected_holdout=True)
    assert holdout.validation_seasons == (2025,)


def test_primary_metric_and_aggregation(contract):
    assert contract["metrics"]["primary"] == "race_macro_log_loss"
    out = race_macro([1, 0, 1, 0], [0.9, 0.1, 0.8, 0.2],
                     ["r1", "r1", "r2", "r2"], "log_loss")
    assert out["scope"] == "race_macro" and out["n_races"] == 2
    assert set(out["per_race"]) == {"r1", "r2"}


def test_race_level_statistical_unit(contract):
    sc = contract["statistical_comparison"]
    assert sc["unit"] == "race"
    assert "driver-state" in sc["forbidden"]
    assert sc["method"].startswith("paired race-level bootstrap")


def test_candidate_family_uniqueness(contract):
    fams = [f["family"] for f in contract["candidate_families"]]
    assert len(fams) == len(set(fams))
    assert 3 <= len(fams) <= 5
    assert "logistic_regression" in fams
    assert not any(f["new_dependency"] for f in contract["candidate_families"])
    excluded = {e["family"] for e in contract["excluded_families"]}
    assert not (set(fams) & excluded)


def test_hyperparameter_budget_bounds(contract):
    hp = contract["hyperparameter_policy"]
    assert hp["max_configurations_per_family"] <= 12
    assert hp["seeds"] == [42]
    budget = contract["compute_budget"]
    assert budget["max_total_wall_s"] <= 7200
    assert budget["matrix_states"] == 189420


def test_oof_identity_schema(contract):
    cols = contract["oof_prediction_contract"]["identity_columns"]
    for required in ("state_id", "race_id", "season", "driver_id", "fold",
                     "target", "baseline_probability",
                     "candidate_probability"):
        assert required in cols


def test_holdout_advancement_limit(contract):
    adv = contract["advancement_policy"]
    assert adv["max_non_baseline_finalists"] <= 3
    assert adv["plus_baseline"] is True
    assert "2025" in adv["evidence"] or "pre-2025" in adv["evidence"]


def test_artifact_metadata_requirements(contract):
    meta = contract["artifact_contract"]["metadata"]
    for required in ("model family", "hyperparameters", "random seed",
                     "artifact SHA256", "calibration"):
        assert required in meta


def test_contract_deterministic_hash(contract):
    payload = {k: v for k, v in contract.items() if k != "contract_hash"}
    blob = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == contract["contract_hash"]
    assert contract["schema_version"] == "v3.3a-experiment-contract-v1"
