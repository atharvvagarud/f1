"""V3.4A ensemble contract tests (Part AC). Planning/contract only.

No fitting, no weight search, no 2025 contact.
"""
import hashlib
import json
from pathlib import Path

C = json.loads(Path("results/v3/v3_4a/experiment_contract.json").read_text())


def canon(payload, skip):
    inner = {k: v for k, v in payload.items() if k != skip}
    return json.dumps(inner, sort_keys=True, separators=(",", ":"))


def test_parent_identity():
    assert C["parent"] == {
        "tag": "v3.3-multi-model-lab",
        "commit": "563fff21f94f169097079b003816181c31227aa9",
    }


def test_contract_hash():
    assert hashlib.sha256(canon(C, "contract_hash").encode()).hexdigest() \
        == C["contract_hash"] == \
        "d6b12074db9895844c28c05c78baf56c113d63c33d685c5913c92ebb5036b352"


def test_v3_3_freeze_identity():
    ident = C["v3_3_freeze_identity"]
    assert ident["freeze_record_sha256"] == \
        "a051780776c2726ae9365c7002db80ecb1e6b17f071533dbca5a94ec3d12dc67"
    assert ident["scientific_card_sha256"] == \
        "1bc365efed16d6a3c2c445b595b44cbce224ae6591b3418524c654ff9ab41260"
    assert ident["conclusions"]["v3_1b_logistic"] == "STANDALONE_CHAMPION"
    assert ident["conclusions"]["xgboost"].startswith(
        "KEEP_DIVERSITY_CANDIDATE")


def test_base_models_exactly_logistic_plus_xgb():
    base = C["base_models"]
    assert base["logistic"]["family"] == "logistic_regression"
    assert base["xgboost"]["family"] == "xgboost"
    assert base["logistic"]["hyperparameters"]["C"] == 0.01
    assert base["xgboost"]["hyperparameters"]["learning_rate"] == 0.03
    assert base["xgboost"]["hyperparameters"]["max_depth"] == 3
    assert base["xgboost"]["hyperparameters"]["min_child_weight"] == 5
    assert "hist_gradient_boosting" in base["excluded"]
    assert "extra_trees" in base["excluded"]


def test_task_semantics_and_features():
    assert C["task"]["name"] == "winner"
    assert C["task"]["probability_semantics"] == "INDEPENDENT_BINARY"
    assert "field-normalized" in C["task"]["probabilities"]
    for m in ("logistic", "xgboost"):
        assert C["base_models"][m]["feature_count"] == 110
        assert C["base_models"][m]["feature_arm"] == \
            "ALL_84_PLUS_V3_1_DYNAMICS_CORE"


def test_no_field_normalization_anywhere():
    blob = json.dumps(C)
    assert "softmax" not in blob.lower()
    assert C["task"]["probabilities"] == "RAW, never field-normalized"


def test_development_folds_exact():
    folds = C["development_folds"]
    assert folds["D1"]["validate"] == [2022]
    assert folds["D2"]["validate"] == [2023]
    assert folds["D3"]["validate"] == [2024]
    assert folds["D1"]["ensemble_training_history"] == []
    assert folds["D2"]["ensemble_training_history"] == ["D1"]
    assert folds["D3"]["ensemble_training_history"] == ["D1", "D2"]


def test_identity_alignment_required():
    assert "state_id" in C["alignment_contract"]["rule"]
    assert "row-position" in C["base_prediction_contract"]["identity_join"]


def test_blend_grid_frozen():
    grid = C["blend_grid"]
    assert grid == [round(i / 10, 1) for i in range(11)]
    assert 0.0 in grid and 1.0 in grid
    assert C["admitted_methods"]["fixed_convex_blend"]["bounds"] == [0.0, 1.0]
    assert C["blend_grid_policy"]["adaptive_refinement"].startswith("FORBIDDEN")


def test_stacker_complexity_bounded():
    stacker = C["admitted_methods"]["logistic_stacker"]
    assert stacker["status"] == "ADMITTED"
    assert "C=1.0" in stacker["regularization"]
    assert stacker["seed"] == 42
    assert C["stacker_contract"]["forbidden"]


def test_primary_metric_and_bootstrap():
    assert C["metrics"]["primary"].startswith("race_macro_log_loss")
    assert C["bootstrap"]["unit"].startswith("race")
    assert C["bootstrap"]["replicates"] == 2000
    assert C["bootstrap"]["seed"] == 42


def test_2025_previously_revealed_and_firewalled():
    assert "PREVIOUSLY REVEALED" in C["2025_status"]
    assert "untouched holdout" not in C["2025_status"].lower() \
        or "NOT" in C["2025_status"]
    fw = C["2025_firewall"]
    assert "2025 labels" in fw["forbidden_in_selection"]
    assert "2025 XGB predictions" in fw["forbidden_in_selection"]
    assert "data/v3/v3_3e/*" in fw["forbidden_paths"]
    assert "REVEALED" in fw["final_evaluation"]


def test_no_adaptive_refinement():
    assert C["robustness_policy"]["adaptive_grid_refinement"] == "FORBIDDEN"


def test_final_recipe_max_one_and_null_valid():
    assert C["final_recipe_policy"]["cardinality"] == \
        "exactly one of NO_ENSEMBLE | one ensemble recipe"
    assert "NO_ENSEMBLE" in C["null_result_policy"]["rule"]


def test_stage_plan_frozen():
    stages = C["stage_plan"]
    assert list(stages) == ["V3.4A", "V3.4B", "V3.4C", "V3.4D", "V3.4E",
                            "V3.4F"]
    assert "ONLY if an ensemble survives" in stages["V3.4E"]


def test_landscape_summary_consistent():
    land = json.loads(
        Path("results/v3/v3_4a_ensemble_landscape.json").read_text())
    assert land["contract_identity"] == C["contract_hash"]
    assert land["parent"] == C["parent"]
    assert land["xgb_2025_policy"]["forbidden_in_selection"] is True
