"""V3.4D: freeze the final ensemble recipe (one-shot writer).

Verifies A/B/C provenance, then freezes exactly the C-selected
w=0.2 blend. No search, no fitting, no 2025 prediction contents.
Refuses if the recipe already exists.
"""
import hashlib
import json
from pathlib import Path

OUT = Path("results/v3/v3_4d")
A_SHA = "d6b12074db9895844c28c05c78baf56c113d63c33d685c5913c92ebb5036b352"
B_SHA = "64ca2d2911e63b1487334ca72fc024f47d59868f168b60d7d391d31df82b5b26"
P_SHA = "d0af402c550879dac7c2f85761d4d4a1f433bb2a2e4dba1bfd000282b8a37891"
C_SHA = "98b315970408000936aa9970224234436e9cd13c2573a823fec859650b41ed87"


def load(path):
    return json.loads(Path(path).read_text())


def canon(payload, skip):
    return json.dumps({k: v for k, v in payload.items() if k != skip},
                      sort_keys=True, separators=(",", ":"))


def identity(path, skip, expect):
    doc = load(path)
    assert hashlib.sha256(canon(doc, skip).encode()).hexdigest() == \
        doc[skip] == expect, f"identity failure: {path}"


def main() -> None:
    if (OUT / "final_ensemble_recipe.json").exists():
        raise RuntimeError("final recipe immutable; refusing overwrite")
    identity("results/v3/v3_4a/experiment_contract.json",
             "contract_hash", A_SHA)
    identity("results/v3/v3_4b/preregistration.json",
             "preregistration_identity", B_SHA)
    identity("results/v3/v3_4c/selection_protocol.json",
             "protocol_identity", P_SHA)
    identity("results/v3/v3_4c/selected_development_candidate.json",
             "candidate_identity", C_SHA)
    cand = load("results/v3/v3_4c/selected_development_candidate.json")
    assert cand["decision"] == "ENSEMBLE_SELECTED"
    assert cand["method"] == "fixed_convex_blend"
    assert cand["weight"] == 0.2
    assert cand["weight"] in load(
        "results/v3/v3_4a/experiment_contract.json")["blend_grid"]
    # base identities from frozen V3.3/V3.4A artifacts (no retraining)
    recipes = load(
        "results/v3/v3_3d/finalist_recipes.json")["recipes"]
    assert load("results/v3/v3_3d/finalist_recipes.json")["recipe_hash"] == \
        "ca0cd5d5f7c95e5446ae66111eff85232441023ad7be15d04a8f35e05fea332d"
    recipe = {
        "schema_version": "v3.4-final-ensemble-recipe-v1",
        "decision": "ENSEMBLE_SELECTED",
        "method": "FIXED_CONVEX_BLEND",
        "task": "winner",
        "probability_semantics": "INDEPENDENT_BINARY",
        "base_models": ["v3_1b_logistic", "v3_3_xgboost"],
        "base_model_identities": {
            "v3_1b_logistic": {
                "family": "logistic_regression", "role": "champion/baseline",
                "hyperparameters": recipes["v3_1b_baseline"][
                    "hyperparameters"],
                "training_years": [2018, 2019, 2020, 2021, 2022, 2023, 2024],
                "feature_arm": "ALL_84_PLUS_V3_1_DYNAMICS_CORE",
                "feature_count": 110,
                "calibration": "RAW",
                "probability_semantics": "RAW INDEPENDENT_BINARY",
            },
            "v3_3_xgboost": {
                "family": "xgboost", "role": "diversity candidate",
                "hyperparameters": recipes["xgboost"]["hyperparameters"],
                "training_years": [2018, 2019, 2020, 2021, 2022, 2023, 2024],
                "feature_arm": "ALL_84_PLUS_V3_1_DYNAMICS_CORE",
                "feature_count": 110,
                "feature_hash": "e054c6fb08c0832970165bcfc0e84f54b70787491a"
                                "f1d545b96a13977fc4c89e",
                "calibration": "RAW",
                "probability_semantics": "RAW INDEPENDENT_BINARY",
                "finalist_recipe_identity": "ca0cd5d5f7c95e5446ae66111"
                                            "eff85232441023ad7be15d04a8f35e"
                                            "05fea332d",
            },
        },
        "feature_identity": {"arm": "ALL_84_PLUS_V3_1_DYNAMICS_CORE",
                             "count": 110},
        "transformation": "p_ensemble = 0.8 * p_logistic + 0.2 * p_xgb",
        "logistic_weight": 0.8,
        "xgboost_weight": 0.2,
        "arithmetic": {"order": "0.8*p_log first, then +0.2*p_xgb; "
                                "float64 deterministic",
                       "input_dtype": "float64 probabilities",
                       "finite_required": True,
                       "input_bounds": [0.0, 1.0],
                       "output_bounds": [0.0, 1.0]},
        "calibration": "NONE",
        "normalization": "FORBIDDEN",
        "alignment_contract": {
            "rule": "state_id identity join; row-position use forbidden",
            "required": ["state_id", "race", "driver", "target/eligibility",
                         "season", "checkpoint/lap identity where applicable"],
            "fail_closed": ["duplicate", "missing", "extra", "mismatched"],
        },
        "input_validation": ["canonical columns", "unique state_id",
                             "finite", "bounds [0,1]",
                             "cross-input identity equality"],
        "output_validation": ["finite", "bounds [0,1]", "RAW",
                              "not field-normalized"],
        "seed_policy": {"recipe_seed": 42, "note": "blend is closed-form; "
                                                   "seed governs bootstrap "
                                                   "only"},
        "A_contract_identity": A_SHA,
        "B_prereg_identity": B_SHA,
        "C_protocol_identity": P_SHA,
        "C_selected_candidate_identity": C_SHA,
        "development_evidence_identity": C_SHA,
        "selection_rationale": "CLEAR bootstrap + 3/3 folds + 9/9 stages + "
                               "Brier gain + negligible ECE + conservative; "
                               "not argmin",
        "known_limitations": ["development-only evidence at freeze",
                              "68-race sample"],
        "2025_status": "PREVIOUSLY REVEALED OUT-OF-TIME ENSEMBLE "
                       "EVALUATION (pending V3.4E)",
        "created_before_2025_ensemble_evaluation": True,
    }
    assert recipe["logistic_weight"] + recipe["xgboost_weight"] == 1.0
    blob = json.dumps(recipe, sort_keys=True, separators=(",", ":"))
    recipe["recipe_identity"] = hashlib.sha256(blob.encode()).hexdigest()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "final_ensemble_recipe.json").write_text(
        json.dumps(recipe, indent=1, sort_keys=True) + "\n")
    print("recipe_identity:", recipe["recipe_identity"])
    chain = {
        "schema_version": "v3.4d-provenance-chain-v1",
        "v3_3_parent": {"tag": "v3.3-multi-model-lab",
                        "commit": "563fff21f94f169097079b003816181c31227aa9"},
        "v3_4a_contract": A_SHA,
        "v3_4b_prereg": B_SHA,
        "v3_4b_evidence": "results/v3/v3_4b_development_ensembles.json",
        "v3_4c_protocol": P_SHA,
        "v3_4c_candidate": C_SHA,
        "v3_4d_recipe": recipe["recipe_identity"],
    }
    (OUT / "provenance_chain.json").write_text(
        json.dumps(chain, indent=1, sort_keys=True) + "\n")
    # E manifest: reference 2025 sources via frozen V3.3 METADATA ONLY.
    # Existence checks only; prediction contents never opened here.
    base_meta = load("results/v3/v3_3e/baseline_holdout_identity.json")
    xgb_meta = load("results/v3/v3_3e/prediction_identity.json")
    base_src = base_meta["source"]
    xgb_src = xgb_meta["path"]
    assert Path(base_src).exists() and Path(xgb_src).exists()
    assert base_meta["n_states"] == xgb_meta["n_rows"] == 26692
    manifest = {
        "schema_version": "v3.4e-execution-manifest-v1",
        "final_recipe_identity": recipe["recipe_identity"],
        "transformation": recipe["transformation"],
        "base_sources": {
            "logistic_2025": {"path": base_src,
                              "n_states": base_meta["n_states"],
                              "n_races": base_meta["n_races"]},
            "xgboost_2025": {"path": xgb_src,
                             "n_states": xgb_meta["n_rows"],
                             "sha256": xgb_meta["sha256"]},
        },
        "alignment": "state_id identity (recipe module); positional forbidden",
        "metrics": {"primary": "race_macro_log_loss vs frozen Logistic",
                    "secondary": ["brier", "roc_auc", "pr_auc", "ece",
                                  "top_1", "top_3", "state_pooled_ll",
                                  "EARLY/MID/LATE"]},
        "bootstrap": {"unit": "race", "replicates": 2000, "seed": 42,
                      "ci": 0.95},
        "outputs": {"predictions": "data/v3/v3_4e/ (ignored)",
                    "results": "results/v3/v3_4e/"},
        "terminology": "PREVIOUSLY REVEALED OUT-OF-TIME ENSEMBLE EVALUATION",
        "rules": {"no_refit": True, "no_reselection": True,
                  "no_calibration": True, "no_weight_change": True,
                  "no_post_reveal_rescue": True},
        "disclosure": "base-model 2025 known pre-V3.4; w=0.2 transformation "
                      "selected without 2025 ensemble evaluation",
    }
    mblob = json.dumps(manifest, sort_keys=True, separators=(",", ":"))
    manifest["manifest_identity"] = hashlib.sha256(mblob.encode()).hexdigest()
    (OUT / "v3_4e_execution_manifest.json").write_text(
        json.dumps(manifest, indent=1, sort_keys=True) + "\n")
    print("manifest_identity:", manifest["manifest_identity"])
    (OUT / "artifact_inventory.json").write_text(json.dumps(
        {"a": ["results/v3/v3_4a/", "results/v3/v3_4a_ensemble_landscape.json"],
         "b": ["results/v3/v3_4b/", "results/v3/v3_4b_development_ensembles.json"],
         "c": ["results/v3/v3_4c/", "results/v3/v3_4c_selection_robustness.json"],
         "d": ["results/v3/v3_4d/", "results/v3/v3_4d_recipe_freeze.json"],
         "ignored_b_predictions": "data/v3/v3_4b/*.parquet (36 files)",
         "future_e_outputs": ["data/v3/v3_4e/ (ignored)", "results/v3/v3_4e/"],
         "tracked": "compact JSON/docs/scripts/tests",
         "ignored": "prediction parquets, model binaries, graphify, cache"},
        indent=1, sort_keys=True) + "\n")
    summary = {
        "schema_version": "v3.4d-recipe-freeze-v1",
        "parent": chain["v3_3_parent"],
        "provenance_chain": "results/v3/v3_4d/provenance_chain.json",
        "A_identity": A_SHA, "B_identity": B_SHA, "C_identity": P_SHA,
        "selected_candidate_identity": C_SHA,
        "final_recipe_identity": recipe["recipe_identity"],
        "decision": "ENSEMBLE_SELECTED", "method": "FIXED_CONVEX_BLEND",
        "weights": {"logistic": 0.8, "xgboost": 0.2},
        "base_models": ["v3_1b_logistic", "v3_3_xgboost"],
        "alignment": recipe["alignment_contract"]["rule"],
        "probability_semantics": "RAW INDEPENDENT_BINARY",
        "development_parity": "pending (module execution vs B w=0.2)",
        "2025_status": recipe["2025_status"],
        "E_manifest_identity": manifest["manifest_identity"],
        "E_disposition_policy": ["ENSEMBLE_GENERALIZES",
                                 "ENSEMBLE_MIXED_OUT_OF_TIME",
                                 "ENSEMBLE_FAILS_TO_GENERALIZE"],
        "tests": "tests/test_v3_4d_recipe.py",
        "known_limitations": recipe["known_limitations"],
        "V3_4E_recommendation": "execute manifest with recipe module; "
                                "no discretion; report as revealed",
    }
    Path("results/v3/v3_4d_recipe_freeze.json").write_text(
        json.dumps(summary, indent=1, sort_keys=True) + "\n")
    print("D freeze artifacts written.")


if __name__ == "__main__":
    main()
