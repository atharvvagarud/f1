"""V3.5A outcome-contract tests. No fitting, no 2025 contact."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "results/v3/v3_5a/experiment_contract.json"
LANDSCAPE = ROOT / "results/v3/v3_5a_outcome_landscape.json"
EXPECT = "15ca7c17146062edb5196a5de244fadd81d38562b2ca5714e58a21d4efb5efab"


def load(path):
    return json.loads(Path(path).read_text())


def canon(doc):
    return json.dumps({k: v for k, v in doc.items() if k != "contract_hash"},
                      sort_keys=True, separators=(",", ":"))


def contract():
    return load(CONTRACT)


def test_parent_exact():
    c = contract()
    assert c["parent"] == {"tag": "v3.4-ensemble",
                           "commit": "3cbd28470ffa211bd754d4262eb10d66d149bf00"}


def test_contract_canonical_hash():
    c = contract()
    assert hashlib.sha256(canon(c).encode()).hexdigest() == \
        c["contract_hash"] == EXPECT


def test_selected_primary_task_exactly_one():
    c = contract()
    assert c["selected_primary_task"] == \
        "ordered_cumulative_finish_thresholds"


def test_target_semantics_explicit():
    c = contract()
    ts = c["canonical_target_semantics"]
    assert "tail orderings" in ts["unclassified_back_rank"]
    assert set(ts["threshold_labels"]) == \
        {"P_win", "P_podium", "P_top5", "P_top10"}


def test_prediction_population_explicit():
    c = contract()
    assert "observable state at time T" in c["prediction_population"]
    assert "INCLUDED" in c["prediction_population"]


def test_status_policy_complete():
    c = contract()
    sp = c["status_policy"]
    for k in ("classified_finishers", "classified_retirements",
              "unclassified_retirements", "DSQ", "DNS_never_started",
              "null_final_withdrawals", "eligibility_rule"):
        assert k in sp, k


def test_feature_policy_pinned():
    c = contract()
    fp = c["feature_policy"]
    assert fp["basis"] == "ALL_84_PLUS_V3_1_DYNAMICS_CORE (110 features, frozen)"
    assert fp["new_features_in_A"] == "FORBIDDEN"
    assert "spatial_P12" in fp
    assert "excluded" in fp["spatial_P12"]


def test_no_spatial_features_silently_added():
    c = contract()
    blob = json.dumps(c, sort_keys=True)
    assert "P12" in blob  # only via explicit exclusion/future-justification
    assert c["feature_policy"]["new_features_in_A"] == "FORBIDDEN"


def test_temporal_protocol_explicit():
    c = contract()
    tp = c["temporal_protocol"]
    assert "D1" in tp["development"] and "D3" in tp["development"]
    assert tp["final_fit"] == "2018-2024"


def test_2025_excluded():
    c = contract()
    fw = c["2025_firewall"]
    assert fw["contact_in_A"] == "NONE"
    assert fw["selection_use_of_2025"].startswith("FORBIDDEN")
    assert "2018-2024" in fw["mechanism_BCD"][1]


def test_primary_metric_exactly_one():
    c = contract()
    assert c["primary_metric"] == \
        "mean_race_macro_log_loss_over_4_thresholds"


def test_race_statistical_unit():
    c = contract()
    assert c["race_aggregation"]["unit"] == "race"
    assert c["statistical_comparison"]["unit"] == "race"
    assert c["statistical_comparison"]["states_as_units"] == "FORBIDDEN"


def test_bootstrap_config():
    c = contract()
    sc = c["statistical_comparison"]
    assert (sc["replicates"], sc["seed"], sc["ci"]) == (2000, 42, 0.95)


def test_calibration_predeclared():
    c = contract()
    assert c["calibration_policy"]["primary"] == "RAW"


def test_coherence_policy_explicit():
    c = contract()
    cp = c["coherence_policy"]
    assert "p_win <= p_podium <= p_top5 <= p_top10" in cp["rule"]
    assert cp["post_hoc_repair"].startswith("FORBIDDEN")


def test_dnf_policy_explicit():
    c = contract()
    assert "unclassified_retirements" in c["status_policy"]
    assert "ordinal_supervision" in c["censoring_policy"]


def test_field_size_policy_explicit():
    c = contract()
    assert "2024-r03-R" in c["field_size_policy"]["corpus_fact"]


def test_candidate_formulations_closed():
    c = contract()
    assert c["candidate_models"]["policy"].startswith("closed set")
    assert len(c["formulation_scorecard"]) == 7


def test_stage_plan_explicit():
    c = contract()
    for s in ("V3.5A", "V3.5B", "V3.5C", "V3.5D", "V3.5E", "V3.5F", "V3.5G"):
        assert s in c["stage_plan"], s


def test_no_model_performance():
    land = load(LANDSCAPE)
    assert land["model_performance"].startswith("NONE")
    blob = json.dumps(contract(), sort_keys=True).lower()
    for token in ("race_macro_ll", "delta_vs_", "roc_auc",
                  "coef_", "feature_importance", "brier\":"):
        assert token not in blob, token


def test_no_v35_predictions():
    # A-scope intent (preserved verbatim in force): no LEARNED predictions
    # and no fitted models anywhere under V3.5 paths. B-stage target
    # sidecars (integer labels + identities, authorized by the A contract's
    # V3.5B dataset requirement) are not predictions and are allowed.
    import glob
    import pandas as pd
    for path in glob.glob("data/v3/v3_5*") + glob.glob("results/v3/v3_5*"):
        low = path.lower()
        assert "predict" not in low, path
        assert not low.endswith((".joblib", ".pkl", ".pt", ".onnx")), path
    for pq in glob.glob("data/v3/v3_5b/*.parquet"):
        frame = pd.read_parquet(pq)
        assert "probability" not in frame.columns, pq
        floats = [c for c in frame.columns
                  if str(frame[c].dtype).startswith("float")
                  and c not in ("position_final", "points")]
        assert not floats, (pq, floats)


def test_no_serving_changes():
    import subprocess
    out = subprocess.run(["git", "status", "--short"], capture_output=True,
                         text=True, cwd=ROOT).stdout
    for line in out.splitlines():
        assert "api/" not in line and "frontend/" not in line \
            and "serving" not in line, line


def test_landscape_no_2025_stats():
    land = load(LANDSCAPE)
    assert land["corpus"]["seasons"] == \
        [2018, 2019, 2020, 2021, 2022, 2023, 2024]
    assert land["corpus"]["races"] == 149
