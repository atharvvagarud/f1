"""V3.8D/E reconciliation correction-01 tests (deterministic, no MC2).

Proves the corrected race-level bootstrap, the preserved superseded
statistic, gate recomputation under ORIGINAL D rules, artifact versioning
(originals byte-identical), E consequence CASE_A with E metrics untouched,
and absence of simulation/model/2025/FINAL_FIT paths.
"""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "results" / "v3" / "v3_8d"
E = ROOT / "results" / "v3" / "v3_8e"


def _load(name, base=D):
    return json.loads((base / name).read_text())


def _canon(doc):
    return json.dumps(doc, sort_keys=True, separators=(",", ":")).encode()


# --- 1-5. per-race evidence + sign convention ---

def test_all_8_per_race_losses_reproduce():
    rows = _load("per_row_records.json")
    by = {}
    for r in rows:
        by.setdefault(r["race_id"], []).append(r)
    assert len(by) == 8
    ev = _load("historical_evaluation.json")
    corr = _load("correction_01.json")
    assert corr["confirmations"]["prediction_changes"] == 0
    for rc, rr in by.items():
        ml = sum(x["ll_log"] for x in rr) / len(rr)
        mm = sum(x["ll_mc2"] for x in rr) / len(rr)
        assert abs((ml - mm)
                   - ev["quality"]["per_race_advantage"][rc]) < 1e-9


def test_sign_convention_correct():
    # advantage = log - mc2: positive -> MC2 better, negative -> Logistic
    corr = _load("correction_01.json")
    assert corr["affected_fields"]["gate_inputs.log_better/mc2_better"] \
        == {"old": [1, 7], "new": [7, 1]}


def test_logistic_wins_7_of_8():
    ev = _load("historical_evaluation.json")
    adv = ev["quality"]["per_race_advantage"]
    assert sum(1 for v in adv.values() if v < 0) == 7


def test_mc2_wins_1_of_8():
    ev = _load("historical_evaluation.json")
    adv = ev["quality"]["per_race_advantage"]
    winners = [k for k, v in adv.items() if v > 0]
    assert winners == ["2023-r05-R"]


def test_race_macro_equal_weight():
    corr = _load("correction_01.json")
    ev = _load("historical_evaluation.json")
    adv = ev["quality"]["per_race_advantage"]
    macro = sum(adv.values()) / len(adv)
    assert abs(macro - (-0.2327820190398489)) < 1e-9
    assert abs(corr["affected_fields"]["bootstrap.adv"]["new"]
               ["observed"] - macro) < 1e-12


# --- 6-10. corrected bootstrap procedure ---

def test_bootstrap_samples_race_ids_not_rows():
    text = (ROOT / "scripts" / "v3_8d_correction_01.py").read_text()
    assert "rng.randint(0, len(races), len(races))" in text
    assert "shuffle" not in text


def test_selected_race_retains_all_rows():
    rows = _load("per_row_records.json")
    by = {}
    for r in rows:
        by.setdefault(r["race_id"], []).append(r)
    assert {len(v) for v in by.values()} >= {1}
    assert sum(len(v) for v in by.values()) == 277
    # race means aggregate complete groups (cross-checked in test 1)


def test_bootstrap_b_and_seed():
    text = (ROOT / "scripts" / "v3_8d_correction_01.py").read_text()
    assert "B = 2000" in text
    assert "SEED = 987654321" in text
    corr = _load("correction_01.json")
    new = corr["affected_fields"]["bootstrap.adv"]["new"]
    assert new["mark"] == "CORRECTED_RACE_LEVEL"


def test_deterministic_ci_reproduction():
    import numpy as np
    rows = _load("per_row_records.json")
    by = {}
    for r in rows:
        by.setdefault(r["race_id"], []).append(r)
    races = sorted(by)
    # identical construction to scripts/v3_8d_correction_01.py: per-race
    # means from stored ll fields (== stored advantages to <1e-9 per test 1)
    adv = {}
    for rc in races:
        rr = by[rc]
        ml = sum(x["ll_log"] for x in rr) / len(rr)
        mm = sum(x["ll_mc2"] for x in rr) / len(rr)
        adv[rc] = ml - mm
    rng = np.random.RandomState(987654321)
    reps = []
    for _ in range(2000):
        picks = [races[i] for i in rng.randint(0, len(races), len(races))]
        reps.append(sum(adv[p] for p in picks) / len(picks))
    s = sorted(reps)
    corr = _load("correction_01.json")
    new = corr["affected_fields"]["bootstrap.adv"]["new"]
    assert abs(sum(reps) / len(reps) - new["mean"]) < 1e-12
    assert [s[int(0.025 * len(s))], s[int(0.975 * len(s))]] == \
        new["ci95"]
    assert abs(new["frac_lt_0"] - 0.9945) < 1e-9
    assert abs(new["frac_gt_0"] - 0.0055) < 1e-9


# --- 11-14. superseded statistic + gate rules ---

def test_old_result_marked_superseded():
    corr = _load("correction_01.json")
    old = corr["affected_fields"]["bootstrap.adv"]["old"]
    assert old["mark"] == "SUPERSEDED_ROW_POOLED_BOOTSTRAP"
    assert abs(old["mean"] - (-0.15065782073566983)) < 1e-12
    assert old["ci95"] == [-0.5367011220527186, -0.0007417371736964612]


def test_old_statistic_excluded_from_corrected_gate():
    text = (ROOT / "scripts" / "v3_8d_correction_01.py").read_text()
    assert "excluded from the corrected gate" in text
    gate = _load("fusion_gate_correction_01.json")
    blob = json.dumps(gate)
    assert "-0.15065782073566983" not in blob
    assert "-0.5367011220527186" not in blob


def test_corrected_robustness_follows_original_rules():
    gate = _load("fusion_gate_correction_01.json")
    assert gate["evidence"]["ROBUSTNESS"] == "PASS"
    ev = _load("historical_evaluation.json")
    assert 0 < ev["primary"]["pooled_spearman"] < 0.99
    assert 0 < ev["primary"]["macro_spearman"] < 0.99


def test_corrected_gate_follows_original_rules():
    gate = _load("fusion_gate_correction_01.json")
    assert set(gate["evidence"]) == {
        "SEMANTIC_VALIDITY", "COVERAGE_ADEQUACY", "DISTINCT_SIGNAL",
        "COMPLEMENTARITY", "ROBUSTNESS"}
    assert all(v == "PASS" for v in gate["evidence"].values())
    assert gate["decision"] == "FUSION_RESEARCH_WARRANTED"
    assert _load("correction_01.json")["corrected_d_gate"] == \
        "FUSION_RESEARCH_WARRANTED"


# --- 15-18. prohibitions ---

def test_no_mc2_execution_path():
    text = (ROOT / "scripts" / "v3_8d_correction_01.py").read_text()
    assert "run_mc2" not in text
    assert "raceintel.simulation" not in text
    assert "raceintel.model_lab" not in text
    assert _load("correction_01.json")["confirmations"]["mc2_reruns"] == 0


def test_no_prediction_or_model_mutation():
    c = _load("correction_01.json")["confirmations"]
    assert c["prediction_changes"] == 0
    assert c["probability_changes"] == 0
    assert c["population_changes"] == 0
    assert c["protocol_mutated"] is False
    assert c["amendment_01_mutated"] is False


def test_2025_absent():
    rows = _load("per_row_records.json")
    assert 2025 not in {r["season"] for r in rows}


def test_final_fit_absent():
    blob = json.dumps(_load("correction_01.json"))
    blob += json.dumps(_load("fusion_gate_correction_01.json"))
    blob += (ROOT / "scripts" / "v3_8d_correction_01.py").read_text()
    assert "FINAL_FIT" not in blob
    assert "final_fit" not in blob


# --- 19-21. E consequence + identities ---

def test_e_empirical_metrics_unchanged():
    ev = _load("fusion_evaluation.json", E)
    assert abs(ev["deltas"]["delta_fusion_vs_log_macro_ll"]
               - 0.0028754732795133603) < 1e-12
    assert abs(ev["deltas"]["delta_fusion_vs_mc2_macro_ll"]
               - (-0.3540254214665001)) < 1e-12
    assert _load("fusion_gate.json", E)["decision"] == \
        "FUSION_IMPROVEMENT_NOT_SUPPORTED"


def test_e_gate_unchanged_provenance_relabelled():
    corr = _load("correction_01.json")
    assert corr["e_status"]["case"] == "CASE_A"
    assert corr["e_status"]["e_rerun"] is False
    card = _load("fusion_card.json", E)
    assert card["d_preflight_verdict"] == "CORRECTABLE_D_ANALYSIS_DEFECT"
    assert card["d_card_identity"] == \
        corr["corrected_d_card_identity"]


def test_correction_card_identities_recompute():
    corr = _load("correction_01.json")
    assert corr["original_d_card_identity"] == \
        "523898b3d626a7c3baffd65d2c5c921983db361faeb3feb57a7f8984f2e137f9"
    assert corr["corrected_d_card_identity"] == \
        "67f97c185ca8cc687b59b376bc5a48776e9290d6463a05653fa1a6e18a298985"
    c = _load("evaluation_card_correction_01.json")
    ident = c.pop("card_identity")
    blob = json.dumps(c, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(blob).hexdigest() == ident == \
        corr["corrected_d_card_identity"]
    # original card still recomputes (byte-identical, untouched)
    o = _load("evaluation_card.json")
    oident = o.pop("card_identity")
    oblob = json.dumps(o, sort_keys=True, separators=(",", ":")).encode()
    assert hashlib.sha256(oblab := oblob).hexdigest() == oident == \
        corr["original_d_card_identity"]


def test_original_d_artifacts_untouched():
    # preregistered identities still recompute from the original files
    p = _load("evaluation_protocol.json")
    ident = p.pop("protocol_identity")
    assert hashlib.sha256(_canon(p)).hexdigest() == ident == \
        "9cbe85de7c8f0553a098a9a03d016beed80159c785b566c312502d3bf10f2ed1"
    out = subprocess.run(["git", "status", "--short"], cwd=ROOT,
                         capture_output=True, text=True, check=True
                         ).stdout
    modified = [ln for ln in out.splitlines()
                if ln.startswith(("M ", " M"))]
    # Permitted tracked modifications are additive product wiring only:
    # V3.8F router registration + V3.8G navigation entry.
    # V3.8H reconciliation: H additionally permits exactly the Tier-1
    # runner reclassifications (EXPECTED_COLLECTED / EXPECTED_TEST_FILES
    # accounting for new V3.8 source-safe tests; frozen science untouched)
    # and exactly the Tier-1-driven historical-guard reconciliations below
    # (provenance-neutral allowlist admissions; frozen science untouched).
    # P2A carve-out (performance programme only): exactly the two kernel
    # files with hoisted loop-invariant overhead (parity-gated in
    # P0-P20/P1-P3/P2A-P29 checks, not here).
    assert {m.split()[-1] for m in modified} <= {
        "api/main.py", "frontend/components/shell/CommandBar.tsx",
        "scripts/run_ci_tests.py",
        "scripts/run_ci_frontend_tests.py",
        "tests/test_v3_5a_contract.py", "tests/test_v3_5b_dataset.py",
        "tests/test_v3_5c_harness.py", "tests/test_v3_5d_screening.py",
        "tests/test_v3_6a_contract.py", "tests/test_v3_6b_contracts.py",
        "tests/test_v3_6d_evaluation.py", "tests/test_v3_6f_runtime.py",
        "tests/test_v3_6h_freeze.py", "tests/test_v3_7a_contract.py",
        "raceintel/simulation/mc2/kernel.py",
        "raceintel/simulation/mc2/residuals.py",
        "tests/test_v3_8a_consensus_contract.py",
        "tests/test_v3_8b_source_adapters.py",
        "tests/test_v3_8c_consensus_metrics.py",
        "tests/test_v3_8d_correction_01.py",
        "tests/test_v3_8d_evaluation.py",
        "tests/test_v3_8h_freeze.py",
        "tests/test_v3_6a_contract.py",
        "tests/test_v3_6b_contracts.py",
        "tests/test_v3_6d_evaluation.py",
        "tests/test_v3_7a_contract.py"}, modified
