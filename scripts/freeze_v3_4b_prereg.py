"""V3.4B: freeze the development-experiment preregistration (one-shot writer).

Must run BEFORE any ensemble prediction/result artifact exists. Re-run
refuses if experiment output already present (prereg immutable).
"""
import hashlib
import json
from pathlib import Path

A = json.loads(
    Path("results/v3/v3_4a/experiment_contract.json").read_text())
A_SHA = "d6b12074db9895844c28c05c78baf56c113d63c33d685c5913c92ebb5036b352"

OUT = Path("results/v3/v3_4b")
PRED_OUT = Path("data/v3/v3_4b")


def main() -> None:
    blob_a = json.dumps(
        {k: v for k, v in A.items() if k != "contract_hash"},
        sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob_a.encode()).hexdigest() == \
        A["contract_hash"] == A_SHA, "V3.4A contract identity failure"
    if any(OUT.glob("blend_*.json")) or any(OUT.glob("stacker_*.json")) \
            or any(PRED_OUT.glob("*.parquet")):
        raise RuntimeError(
            "experiment output already exists; B preregistration immutable")
    spec = {
        "schema_version": "v3.4b-preregistration-v1",
        "parent": dict(A["parent"]),
        "a_contract_identity": A_SHA,
        "base_predictions": {
            "logistic_oof": {
                "paths": A["base_prediction_contract"]["streams"][
                    "logistic_oof"],
                "v3_3_prob_hash": "71649b6a757a80eb5045bbe76dba2f80f93c95"
                                   "ab6051729c42492c30df0e4240",
                "v3_3_pooled_race_macro_ll": 0.06710726601117191,
                "v3_3_per_fold_ll": {
                    "D1": 0.08067523650595465,
                    "D2": 0.03943563529462307,
                    "D3": 0.08003562121445756},
            },
            "xgboost_oof": {
                "paths": A["base_prediction_contract"]["streams"][
                    "xgboost_oof"],
                "v3_3_prob_hash": "ce459f4dd1cc6d09809e0c6d3b4daa7109d90a1"
                                   "611c6bbe48015bfa7b83c8996",
                "v3_3_pooled_race_macro_ll": 0.07064612807567275,
                "v3_3_per_fold_ll": {
                    "D1": 0.09378650529454774,
                    "D2": 0.03520555673176539,
                    "D3": 0.08192130602361906},
            },
        },
        "aligned_identity": {"rows": {"D1": 23577, "D2": 24422,
                                      "D3": 26606, "total": 74605},
                             "races": 68,
                             "join": "state_id only"},
        "blend_grid": list(A["blend_grid"]),
        "stacker": {
            "form": A["admitted_methods"]["logistic_stacker"]["form"],
            "clip": [1e-6, 1 - 1e-6],
            "C": 1.0,
            "solver": "lbfgs",
            "seed": 42,
            "temporal": {"D1": "NOT_EVALUABLE/baseline-only",
                         "D2": "train on D1", "D3": "train on D1+D2"},
        },
        "metrics": dict(A["metrics"]),
        "bootstrap": dict(A["bootstrap"]),
        "stage_policy": "EARLY/MID/LATE thirds (model_lab.stages; "
                        "no new definitions)",
        "firewall_2025": {
            "status": "PREVIOUSLY REVEALED; FORBIDDEN in V3.4B",
            "forbidden_paths": list(
                A["2025_firewall"]["forbidden_paths"]),
            "contact_must_be_none": True,
        },
        "artifact_paths": {
            "compact": "results/v3/v3_4b/*.json",
            "predictions": "data/v3/v3_4b/*.parquet (ignored)",
            "summary": "results/v3/v3_4b_development_ensembles.json",
        },
        "seed": 42,
        "test_policy": "tests/test_v3_4b_development.py + A contract + "
                       "relevant V3.3/M6 tests; FULL_TIER1 = "
                       "NOT_REQUIRED_RESEARCH_EXECUTION_ONLY",
        "compute_budget_s": 1800,
        "selection": "NONE IN B (V3.4C owns selection)",
    }
    assert spec["blend_grid"] == [round(i / 10, 1) for i in range(11)]
    blob = json.dumps(spec, sort_keys=True, separators=(",", ":"))
    spec["preregistration_identity"] = hashlib.sha256(
        blob.encode()).hexdigest()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "preregistration.json").write_text(
        json.dumps(spec, indent=1, sort_keys=True) + "\n")
    print("preregistration_identity:", spec["preregistration_identity"])


if __name__ == "__main__":
    main()
