"""V3.4E: freeze the execution record (one-shot writer).

Must run BEFORE 2025 prediction contents are loaded. Reads ONLY small
frozen metadata (paths/counts/hashes), never prediction parquet contents.
Refuses if 2025 contents were already loaded (prediction artifact exists).
"""
import hashlib
import json
from pathlib import Path

OUT = Path("results/v3/v3_4e")
A_SHA = "d6b12074db9895844c28c05c78baf56c113d63c33d685c5913c92ebb5036b352"
B_SHA = "64ca2d2911e63b1487334ca72fc024f47d59868f168b60d7d391d31df82b5b26"
P_SHA = "d0af402c550879dac7c2f85761d4d4a1f433bb2a2e4dba1bfd000282b8a37891"
C_SHA = "98b315970408000936aa9970224234436e9cd13c2573a823fec859650b41ed87"
R_SHA = "d715dcfb19db35f01cbf369bbcba52994ff99d366364f607779d3ec07539af68"
M_SHA = "9a6752b6cff97a6bf9d080dab5ac56bfaf1336e4503383ba4d14366000d368a1"


def load(path):
    return json.loads(Path(path).read_text())


def canon(payload, skip):
    return json.dumps({k: v for k, v in payload.items() if k != skip},
                      sort_keys=True, separators=(",", ":"))


def main() -> None:
    if (OUT / "prediction_identity.json").exists() or \
            Path("data/v3/v3_4e").exists():
        raise RuntimeError(
            "2025 contents already loaded; execution record immutable")
    manifest = load("results/v3/v3_4d/v3_4e_execution_manifest.json")
    assert hashlib.sha256(
        canon(manifest, "manifest_identity").encode()).hexdigest() == \
        manifest["manifest_identity"] == M_SHA
    assert manifest["final_recipe_identity"] == R_SHA
    base_meta = load("results/v3/v3_3e/baseline_holdout_identity.json")
    xgb_meta = load("results/v3/v3_3e/prediction_identity.json")
    assert base_meta["n_states"] == xgb_meta["n_rows"] == 26692
    record = {
        "schema_version": "v3.4e-execution-record-v1",
        "parent": {"tag": "v3.3-multi-model-lab",
                   "commit": "563fff21f94f169097079b003816181c31227aa9"},
        "a_identity": A_SHA, "b_identity": B_SHA,
        "c_protocol_identity": P_SHA, "c_candidate_identity": C_SHA,
        "d_recipe_identity": R_SHA, "e_manifest_identity": M_SHA,
        "allowed_inputs": {
            "logistic_2025": {"path": base_meta["source"],
                              "n_states": base_meta["n_states"],
                              "n_races": base_meta["n_races"]},
            "xgboost_2025": {"path": xgb_meta["path"],
                             "n_states": xgb_meta["n_rows"],
                             "sha256": xgb_meta["sha256"]},
        },
        "alignment": "state_id identity only; positional forbidden",
        "transformation": "p = 0.8 * p_logistic + 0.2 * p_xgb",
        "metrics": manifest["metrics"],
        "bootstrap": manifest["bootstrap"],
        "stage_policy": "EARLY/MID/LATE frozen partition",
        "disposition_policy": ["ENSEMBLE_GENERALIZES",
                               "ENSEMBLE_MIXED_OUT_OF_TIME",
                               "ENSEMBLE_FAILS_TO_GENERALIZE"],
        "no_reselection": True,
        "outputs": manifest["outputs"],
        "terminology": manifest["terminology"],
    }
    blob = json.dumps(record, sort_keys=True, separators=(",", ":"))
    record["record_identity"] = hashlib.sha256(blob.encode()).hexdigest()
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "execution_record.json").write_text(
        json.dumps(record, indent=1, sort_keys=True) + "\n")
    print("record_identity:", record["record_identity"])


if __name__ == "__main__":
    main()
