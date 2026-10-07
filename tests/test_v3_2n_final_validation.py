"""V3.2N release-candidate focused tests (artifact-backed, deterministic).

No network. No 2025 in scientific paths. Full Tier-1 runs separately.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_2n"
LOUT = ROOT / "results" / "v3" / "v3_2l"


def _load(name: str) -> dict:
    return json.load(open(OUT / name, encoding="utf-8"))


def test_stage_ledger_completeness():
    ledger = _load("stage_ledger.json")
    stages = [s["stage"] for s in ledger["stages"]]
    assert stages == [f"V3.2{chr(c)}" for c in range(ord("A"), ord("N"))]
    for s in ledger["stages"]:
        assert s["verdict"] and s["disposition"] in {
            "accepted", "accepted-foundation", "accepted-feasibility",
            "rejected", "rejected/deferred"}
        assert s["artifacts"]


def test_artifact_identity_verification():
    audit = _load("artifact_identity_audit.json")
    assert audit["all_match"] is True
    assert all(c["match"] for c in audit["checks"])


def test_l_correction_identity():
    ident = _load("l_correction/correction_identity.json")
    assert ident["n_episodes"] == 476
    assert ident["original_classes"] == {
        "CLEAN": 211, "INITIAL_UNKNOWN": 41, "LATE_SESSION": 10,
        "PIT_CONTEXT": 214}
    corr = ident["corrected_classes"]
    assert sum(corr.values()) == 476
    assert corr.get("RED_REGIME", 0) == 11
    assert corr.get("NEUTRALISED_REGIME", 0) == 63
    assert corr["PIT_CONTEXT"] == 181
    assert corr["CLEAN"] == 171
    # originals untouched
    orig = json.load(open(LOUT / "episode_corpus.json", encoding="utf-8"))
    assert orig["n_episodes"] == 476


def test_corrected_l_verdict_sensitivity():
    sens = _load("l_correction/verdict_sensitivity.json")
    assert sens["original_decision"] == "REJECT_LIFECYCLE_MODEL"
    assert sens["sensitivity"] == "VERDICT_UNCHANGED"
    assert sens["corrected_return_time_n"] < 30
    assert sens["gates"]["return_time_n_adequate"] is False


def test_m_verdict_sensitivity():
    sens = _load("m_verdict_sensitivity.json")
    assert sens["original_m_decision"] == "REJECT_PIT_LIFECYCLE"
    assert sens["sensitivity"] == "VERDICT_UNCHANGED"
    assert sens["pit_fully_addressable_checkpoints"] == 0
    assert sens["corrected_p_return"] < 0.80


def test_final_9644_conservation():
    cat = _load("final_eligibility_catalogue.json")
    assert cat["total"] == 9644
    assert cat["eligible"] == 3678
    assert cat["ineligible"] == 5966
    assert len(cat["checkpoints"]) == 9644


def test_3678_expected_candidate_identity():
    cat = _load("final_eligibility_catalogue.json")
    elig = {(c["race_id"], c["frame_index"]) for c in cat["checkpoints"]
            if c["verdict"] == "SIMULATION_CAPABLE"}
    assert len(elig) == 3678
    j = json.load(open(ROOT / "results" / "v3" / "v3_2j" / "coverage_after.json",
                       encoding="utf-8"))
    j_elig = {(c["race_id"], c["frame_index"]) for c in j["checkpoints"]
              if c["verdict"] == "SIMULATION_CAPABLE"}
    assert elig == j_elig


def test_eligibility_determinism():
    det = _load("eligibility_determinism.json")
    assert det["identical"] is True
    assert det["pass_a_hash"] == det["pass_b_hash"]
    cat = _load("final_eligibility_catalogue.json")
    assert cat["corpus_hash"] == det["pass_a_hash"]


def test_blocker_conservation():
    blk = _load("final_blockers.json")
    assert blk["conservation"] is True
    assert blk["primary"]["STALE_ROSTER_OBSERVATION"] == 3294
    assert blk["primary"]["UNSUPPORTED_TRACK_STATE"] == 1165
    assert blk["primary"]["WET_CONDITIONS"] == 801
    assert blk["primary"]["MISSING_DRIVER_OBSERVATION"] == 354
    assert blk["primary"]["MISSING_TYRE_STATE"] == 198
    assert blk["primary"]["TERMINAL_STATE"] == 154
    assert blk["refused_total"] == 5966


def test_status_corpus_integrity():
    v = _load("status_corpus_validation.json")
    assert v["n_artifacts"] == 149 and v["n_ok"] == 149
    assert v["seasons_2018_2024_only"] is True
    assert v["has_2025"] is False
    assert v["problems"] == []


def test_2025_absence():
    v = _load("status_corpus_validation.json")
    assert "2025" not in json.dumps(v["seasons"])
    audit = _load("artifact_identity_audit.json")
    assert "2025" not in json.dumps(audit["checks"])


def test_retired_clearing_semantics():
    reg = _load("status_semantics_regression.json")
    assert reg["all_unit_passed"] is True
    names = {c["name"] for c in reg["unit_cases"] if c["passed"]}
    assert {"latest<=T", "false clearing", "true-false-true",
            "unknown stays unknown", "missing preserves"} <= names
    assert reg["n_windowed_pairs"] == 13


def test_mandatory_winner_firewall():
    reg = _load("status_semantics_regression.json")
    assert len(reg["firewall_probes"]) == 4


def test_future_poison():
    tp = _load("temporal_poison.json")
    assert tp["all_green"] is True
    assert len(tp["rows"]) == 3


def test_dry_green_parity_record():
    par = _load("old_mc2_parity.json")
    assert par["dry_green_corpus"] == "7ae97c3c8575679a"


def test_j_relieve_simulation_validity():
    val = _load("simulation_5000_validation.json")
    relieved = [r for r in val["results"]
                if (r["race_id"], r["frame_index"]) in {
                    (c["race_id"], c["frame_index"])
                    for c in json.load(open(
                        OUT / "final_validation_corpus.json",
                        encoding="utf-8"))["members"] if c["relieved"]}]
    assert relieved, "corpus must include J-relieved states"
    assert val["all_invariants_pass"] is True


def test_5000_run_invariants():
    val = _load("simulation_5000_validation.json")
    assert val["n_runs"] == 5000
    assert val["n_checkpoints"] == 21
    for r in val["results"]:
        assert r["valid"] == 5000 and r["invalid"] == 0
        assert sum(r["winner_counts"].values()) == 5000


def test_determinism():
    det = _load("determinism.json")
    assert det["rerun_identical"] is True


def test_convergence_confirmation():
    conv = _load("convergence_confirmation.json")
    assert len(conv["rows"]) == 6
    for r in conv["rows"]:
        assert r["tv_1000_vs_5000"] <= r["tv_100_vs_5000"]


def test_parameter_identity():
    audit = _load("parameter_audit.json")
    assert audit["no_retuning"] is True
    assert len(audit["files"]) == 12
    assert "2025" not in json.dumps(audit["files"])


def test_api_supported_unsupported():
    api = _load("api_contract.json")
    assert api["all_ok"] is True
    fail = _load("failure_mode_audit.json")
    assert fail["all_explicit"] is True
    assert len(fail["rows"]) == 6


def test_no_runtime_network():
    import ast
    for name in ("recompute_v3_2n_eligibility.py",
                 "run_v3_2n_final_validation.py",
                 "check_v3_2n_api_replay.py",
                 "check_v3_2n_science.py",
                 "analyze_v3_2n_l_correction.py"):
        src = (ROOT / "scripts" / name).read_text(encoding="utf-8")
        tree = ast.parse(src)
        mods = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                mods.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods.add(node.module.split(".")[0])
        assert "requests" not in mods and "urllib" not in mods, name


def test_replay_checkpoint_synchronization():
    sync = _load("replay_integration.json")
    assert sync["in_sync"] is True


def test_scientific_card_completeness():
    card = _load("v3_2_final_scientific_card.json")
    for key in ("accepted_simulator", "accepted_status_contract",
                "coverage", "scientific_metrics", "artifact_hashes",
                "rejected_experiments", "unsupported_regimes",
                "performance", "reproducibility"):
        assert key in card, key
