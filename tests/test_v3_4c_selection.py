"""V3.4C selection + robustness tests. No fitting, no 2025 contact."""
import hashlib
import json
from pathlib import Path

import pandas as pd

OUT = Path("results/v3/v3_4c")
A_SHA = "d6b12074db9895844c28c05c78baf56c113d63c33d685c5913c92ebb5036b352"
B_SHA = "64ca2d2911e63b1487334ca72fc024f47d59868f168b60d7d391d31df82b5b26"
P_SHA = "d0af402c550879dac7c2f85761d4d4a1f433bb2a2e4dba1bfd000282b8a37891"
GRID = [round(i / 10, 1) for i in range(11)]


def load(name, directory=OUT):
    return json.loads((directory / name).read_text())


def canon(doc, skip):
    return json.dumps({k: v for k, v in doc.items() if k != skip},
                      sort_keys=True, separators=(",", ":"))


def test_a_identity():
    a = load("experiment_contract.json", Path("results/v3/v3_4a"))
    assert hashlib.sha256(canon(a, "contract_hash").encode()).hexdigest() \
        == a["contract_hash"] == A_SHA


def test_b_identity():
    b = load("preregistration.json", Path("results/v3/v3_4b"))
    assert hashlib.sha256(
        canon(b, "preregistration_identity").encode()).hexdigest() == \
        b["preregistration_identity"] == B_SHA


def test_c_protocol_immutable():
    p = load("selection_protocol.json")
    assert hashlib.sha256(
        canon(p, "protocol_identity").encode()).hexdigest() == \
        p["protocol_identity"] == P_SHA
    assert p["no_numeric_threshold"] is True
    assert p["selection_cap"].startswith("max ONE")


def test_candidate_set_exactly_b_candidates():
    p = load("selection_protocol.json")
    assert p["candidate_set"]["blends"] == GRID
    assert p["candidate_set"]["closed"] is True
    s = load("selected_development_candidate.json")
    assert s["weight"] in GRID


def test_no_new_weights():
    s = load("selected_development_candidate.json")
    assert s["weight"] in GRID
    summary = json.loads(
        Path("results/v3/v3_4c_selection_robustness.json").read_text())
    assert sorted(float(k.split("_")[1])
                  for k in summary["blend_dispositions"]) == GRID


def test_no_adaptive_refinement():
    summary = json.loads(
        Path("results/v3/v3_4c_selection_robustness.json").read_text())
    assert len(summary["blend_dispositions"]) == 11


def test_b_prediction_hash_verification():
    hashes = json.loads(
        Path("results/v3/v3_4b/prediction_hashes.json").read_text())
    for name in ("w_0.2__D1", "w_0.2__D2", "w_0.2__D3",
                 "w_0.4__D1", "stacker__D2"):
        fname = name if name.startswith("stacker") else f"blend_{name}"
        path = Path("data/v3/v3_4b") / f"{fname}.parquet"
        assert hashlib.sha256(path.read_bytes()).hexdigest() == hashes[name]


def test_identity_based_alignment():
    for fold in ("D1", "D2", "D3"):
        d = pd.read_parquet(
            Path("data/v3/v3_4b") / f"blend_w_0.2__{fold}.parquet")
        assert d["state_id"].is_unique
        assert (d["season"] != 2025).all()


def test_candidate_table_completeness():
    summary = json.loads(
        Path("results/v3/v3_4c_selection_robustness.json").read_text())
    table = summary["candidate_table"]
    assert len(table) == 11
    for key, row in table.items():
        for field in ("pooled_ll", "delta", "fold_deltas", "bootstrap",
                      "brier_delta", "ece_delta", "temporal"):
            assert field in row, (key, field)


def test_bootstrap_race_unit():
    summary = json.loads(
        Path("results/v3/v3_4c_selection_robustness.json").read_text())
    row = summary["candidate_table"]["w_0.2"]
    assert set(row["bootstrap"]) >= {"mean", "median", "ci_95", "support"}


def test_temporal_fold_preservation():
    summary = json.loads(
        Path("results/v3/v3_4c_selection_robustness.json").read_text())
    assert set(summary["candidate_table"]["w_0.2"]["fold_deltas"]) == \
        {"D1", "D2", "D3"}


def test_stage_preservation():
    bs = load("blend_stage_results.json", Path("results/v3/v3_4b"))
    assert set(bs["w_0.2"]["D1"]) == {"EARLY", "MID", "LATE"}


def test_neighbor_logic():
    summary = json.loads(
        Path("results/v3/v3_4c_selection_robustness.json").read_text())
    table = summary["candidate_table"]
    for w in (0.1, 0.2, 0.3):
        assert table[f"w_{w:.1f}"]["delta"] < 0
    # selected sits inside basin with negative neighbors
    assert table["w_0.1"]["delta"] < 0 and table["w_0.3"]["delta"] < 0


def test_probability_quality_fields():
    summary = json.loads(
        Path("results/v3/v3_4c_selection_robustness.json").read_text())
    row = summary["candidate_table"]["w_0.2"]
    assert row["brier_delta"] < 0
    assert abs(row["ece_delta"]) < 0.001


def test_stacker_d1_fallback_semantics():
    coefs = load("stacker_coefficients.json", Path("results/v3/v3_4b"))
    assert coefs["D1"]["status"].startswith("NOT_EVALUABLE")
    assert coefs["D1"]["coef_logistic"] is None


def test_stacker_disposition():
    summary = json.loads(
        Path("results/v3/v3_4c_selection_robustness.json").read_text())
    assert summary["stacker_disposition"] == "REJECT_TEMPORAL_INSTABILITY"


def test_all_blend_dispositions_assigned():
    summary = json.loads(
        Path("results/v3/v3_4c_selection_robustness.json").read_text())
    disp = summary["blend_dispositions"]
    assert len(disp) == 11
    allowed = set(load("selection_protocol.json")["allowed_dispositions"])
    assert set(disp.values()) <= allowed
    assert disp["w_0.0"] == "BASELINE_CONTROL"


def test_max_one_selected_candidate():
    summary = json.loads(
        Path("results/v3/v3_4c_selection_robustness.json").read_text())
    assert list(summary["blend_dispositions"].values()).count(
        "SELECTED_DEVELOPMENT_RECIPE") == 1


def test_selected_in_frozen_b_set():
    s = load("selected_development_candidate.json")
    assert s["method"] == "fixed_convex_blend"
    assert s["weight"] == 0.2
    blob = json.dumps({k: v for k, v in s.items()
                       if k != "candidate_identity"},
                      sort_keys=True, separators=(",", ":"))
    assert hashlib.sha256(blob.encode()).hexdigest() == \
        s["candidate_identity"]


def test_no_final_recipe_artifact():
    assert not (OUT / "final_ensemble_recipe.json").exists()
    assert list(Path("results/v3").glob("v3_4*_final_ensemble_recipe.json")) == []


def test_2025_forbidden():
    s = load("selected_development_candidate.json")
    blob = json.dumps(s).lower()
    assert "2025" in blob  # limitations mention only
    summary = json.loads(
        Path("results/v3/v3_4c_selection_robustness.json").read_text())
    assert summary["2025_contact"] == "NONE"


def test_2025_contact_none():
    assert not list(Path("data/v3/v3_4b").glob("*2025*"))
    for p in Path("data/v3/v3_4b").glob("*.parquet"):
        assert (pd.read_parquet(p, columns=["season"])["season"]
                != 2025).all()
