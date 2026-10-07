"""V3.3F freeze integrity tests (Part Q / Part H).

Read-only recomputation from frozen artifacts. No fitting, no 2025
regeneration, no scientific decisions. Fails loudly on any identity,
headline, or alignment regression.
"""
import hashlib
import json
from pathlib import Path

import numpy as np
import pandas as pd

F = Path("results/v3/v3_3f")
PRED = Path("data/v3/v3_3e/pred_xgb_final_2025.parquet")
BASELINE_PRED = Path(
    "data/v3/v3_1d/pred_final_ALL_84_PLUS_V3_1_DYNAMICS_CORE_2025.parquet")

A_SHA = "d877e8b2f7821d2eb7ade05677a3a7920f538a0422d28c97956f43f4cce399d7"
B_SHA = "da60e8d9824cd284c830b0bb9b580db2f7a713f06e8c2fa61e459795b8b712d8"
C_SHA = "a8a3d8be330013c38da2ba063ba47785467b0f96d67c004555f6fee9a4eb29a8"
D_SHA = "b74a9a7cb20b502bca2f05c2a071e9ed2f46312ac785194124b234d8ff94bca2"
RECIPE_SHA = ("ca0cd5d5f7c95e5446ae66111eff85232441023ad7be15d04a8f35e05fea332d")
MANIFEST_SHA = ("34188a8598db8c308ba288d2fc9ed8f8ec7db00c555869962affb1b77cb51c50")
PRED_SHA = ("71b9bb807a8a845ec787109a5671d7014cc49b6873a674a50a6b434053b3e5d3")


def canon(payload, skip):
    inner = {k: v for k, v in payload.items() if k != skip}
    return json.dumps(inner, sort_keys=True, separators=(",", ":"))


def load(path):
    return json.loads(Path(path).read_text())


def test_contract_chain_identities_byte_exact():
    a = load("results/v3/v3_3a/experiment_contract.json")
    assert hashlib.sha256(canon(a, "contract_hash").encode()).hexdigest() \
        == a["contract_hash"] == A_SHA
    b = load("results/v3/v3_3b/preregistration.json")
    assert hashlib.sha256(
        canon(b, "preregistration_identity").encode()).hexdigest() \
        == b["preregistration_identity"] == B_SHA
    c = load("results/v3/v3_3c/preregistration.json")
    assert hashlib.sha256(
        canon(c, "preregistration_identity").encode()).hexdigest() \
        == c["preregistration_identity"] == C_SHA
    d = load("results/v3/v3_3d/preregistration.json")
    assert hashlib.sha256(
        canon(d, "preregistration_identity").encode()).hexdigest() \
        == d["preregistration_identity"] == D_SHA
    assert d["a_contract_sha"] == A_SHA
    assert d["b_prereg_sha"] == B_SHA
    assert d["c_prereg_sha"] == C_SHA
    r = load("results/v3/v3_3d/finalist_recipes.json")
    blob = json.dumps(r["recipes"], sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() \
        == r["recipe_hash"] == RECIPE_SHA
    e = load("results/v3/v3_3e/execution_manifest.json")
    assert hashlib.sha256(
        canon(e, "manifest_identity").encode()).hexdigest() \
        == e["manifest_identity"] == MANIFEST_SHA
    assert (e["a_contract_sha"], e["b_prereg_sha"], e["c_prereg_sha"],
            e["d_prereg_sha"], e["d_finalist_recipe_sha"]) == \
        (A_SHA, B_SHA, C_SHA, D_SHA, RECIPE_SHA)


def test_prediction_artifact_hash_authoritative():
    assert hashlib.sha256(PRED.read_bytes()).hexdigest() == PRED_SHA
    ident = load("results/v3/v3_3e/prediction_identity.json")
    assert ident["sha256"] == PRED_SHA
    assert load("results/v3/v3_3e/holdout_result.json")[
        "prediction_artifact_hash"] == PRED_SHA


def _aligned():
    x = pd.read_parquet(PRED)
    b = pd.read_parquet(BASELINE_PRED)
    m = b.merge(x[["state_id", "probability"]], on="state_id",
                suffixes=("_b", "_x"))
    assert len(m) == 26692 and m["state_id"].is_unique
    return m


def _race_ll(p, y):
    eps = 1e-15
    pc = np.clip(p, eps, 1 - eps)
    return float(-(y * np.log(pc) + (1 - y) * np.log(1 - pc)).mean())


def test_headline_recomputation_from_frozen_predictions():
    m = _aligned()
    lb = float(m.groupby("race_id").apply(
        lambda d: _race_ll(d["y_pred"].to_numpy(), d["y_true"].to_numpy()),
        include_groups=False).mean())
    lx = float(m.groupby("race_id").apply(
        lambda d: _race_ll(d["probability"].to_numpy(),
                           d["y_true"].to_numpy()),
        include_groups=False).mean())
    assert lb == abs(0.06341666779729628)
    assert abs(lx - 0.06721364694311552) < 1e-9
    assert abs((lx - lb) - 0.0037969791458192376) < 1e-9
    res = load("results/v3/v3_3e/holdout_result.json")
    assert abs(res["primary_metrics"]["baseline_ll"] - lb) < 1e-12
    assert abs(res["primary_metrics"]["xgboost_ll"] - lx) < 1e-12


def test_race_level_counts_reproduce():
    m = _aligned()
    deltas = (m.groupby("race_id").apply(
        lambda d: _race_ll(d["probability"].to_numpy(),
                           d["y_true"].to_numpy()),
        include_groups=False)
        - m.groupby("race_id").apply(
            lambda d: _race_ll(d["y_pred"].to_numpy(),
                               d["y_true"].to_numpy()),
            include_groups=False))
    assert int((deltas < 0).sum()) == 11
    assert int((deltas > 0).sum()) == 13
    assert int((deltas == 0).sum()) == 0


def test_row_permutation_invariance():
    # Regression test for the H incident: identity-based analysis must be
    # invariant to incidental dataframe ordering.
    m = _aligned()
    ref = m.groupby("race_id").apply(
        lambda d: _race_ll(d["probability"].to_numpy(),
                           d["y_true"].to_numpy()),
        include_groups=False).sort_index()
    x = pd.read_parquet(PRED)
    shuffled = x.sample(frac=1, random_state=7).reset_index(drop=True)
    assert not shuffled["state_id"].equals(x["state_id"])
    b = pd.read_parquet(BASELINE_PRED)
    m2 = b.merge(shuffled[["state_id", "probability"]], on="state_id",
                 suffixes=("_b", "_x"))
    got = m2.groupby("race_id").apply(
        lambda d: _race_ll(d["probability"].to_numpy(),
                           d["y_true"].to_numpy()),
        include_groups=False).sort_index()
    assert np.allclose(ref.to_numpy(), got.to_numpy(), atol=0)
    assert abs(float(got.mean()) - 0.06721364694311552) < 1e-9


def test_no_alternate_post_reveal_prediction_artifact():
    preds = sorted(Path("data/v3/v3_3e").glob("pred_*.parquet"))
    assert [q.name for q in preds] == ["pred_xgb_final_2025.parquet"]
    assert load("results/v3/v3_3e/holdout_revealed.json")[
        "HOLDOUT_REVEALED"] is True


def test_f_artifacts_hashed_and_consistent():
    ledger = load(str(F / "stage_ledger.json"))
    assert ledger["stages_complete"] == ["A", "B", "C", "D", "E"]
    assert all(ledger["stages"][s]["verdict"] == "COMPLETE"
               for s in "ABCDE")
    integrity = load(str(F / "holdout_integrity.json"))
    assert integrity["chronology_verdict"].endswith("PROVEN.")
    assert integrity["prediction_artifact_hash"] == PRED_SHA
    incident = load(str(F / "row_alignment_incident_audit.json"))
    assert incident["classification"].startswith("ANALYSIS_ALIGNMENT_BUG")
    assert incident["frozen_predictions_changed"] is False
