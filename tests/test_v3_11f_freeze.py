"""V3.11F programme freeze: final consolidation guards.

Pins the terminal V3.11 programme: stage registry (exactly A-E with
exact classifications), coverage reconciliation (3678/9644 entry ==
exit, delta 0), terminal decision (no integration, nothing else
authorized), production parity, A-E provenance (referenced, never
rewritten), navigation linkage, and manifest identities.
"""

from __future__ import annotations

import ast
import hashlib
import json
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FINAL = ROOT / "results" / "v3" / "v3_11_final"

EXPECTED_CLASS = {
    "A": "MC2_COVERAGE_FORENSICS_COMPLETE",
    "B": "CAUSAL_STATE_RECONSTRUCTION_REJECTED",
    "C": "TRACK_SOURCE_REGIME_FORENSICS_COMPLETE",
    "D": "VSC_REGIME_MODEL_INSUFFICIENT_EVIDENCE",
    "E": "VSC_EVIDENCE_STILL_INSUFFICIENT",
}


def _load(name):
    with open(FINAL / name, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def registry():
    return _load("stage_identity_registry.json")["stages"]


@pytest.fixture(scope="module")
def coverage():
    return _load("coverage_reconciliation.json")


@pytest.fixture(scope="module")
def terminal():
    return _load("terminal_decision.json")


@pytest.fixture(scope="module")
def card():
    return _load("programme_scientific_card.json")


# ---- STAGE REGISTRY ----

def test_registry_exactly_a_to_e(registry):
    assert sorted(registry) == ["A", "B", "C", "D", "E"]


def test_classifications_exact(registry, card):
    for s, cls in EXPECTED_CLASS.items():
        assert registry[s]["classification"] == cls
        assert card["stage_classifications"][s] == cls


def test_referenced_cards_docs_exist(registry):
    for s, entry in registry.items():
        assert (ROOT / entry["scientific_card"]).is_file(), s
        assert (ROOT / entry["doc"]).is_file(), s
        assert (ROOT / entry["result_root"]).is_dir(), s


# ---- COVERAGE ----

def test_entry_exit_total(coverage):
    assert coverage["candidate_total"] == 9644
    assert coverage["eligible_entry"] == 3678
    assert coverage["eligible_exit"] == 3678
    assert coverage["unsupported_entry"] == 5966
    assert coverage["unsupported_exit"] == 5966
    assert coverage["coverage_entry_pct"] == 38.14
    assert coverage["coverage_exit_pct"] == 38.14


def test_reason_counts_exact(coverage):
    assert coverage["reason_counts"] == {
        "STALE": 3294, "TRACK": 1165, "WET": 801,
        "MISSING_DRIVER": 354, "MISSING_TYRE": 198, "TERMINAL": 154}
    assert sum(coverage["reason_counts"].values()) == 5966


def test_delta_zero(coverage):
    assert coverage["delta_eligible"] == 0
    assert coverage["arithmetic_verified"] is True


# ---- TERMINAL DECISION ----

def test_vsc_integration_false(terminal, card):
    assert terminal["vsc_production_integration_authorized"] is False
    assert terminal["terminal"] is True
    assert terminal["decision"] == "STOP_V3_11_COVERAGE_EXPANSION"
    assert card["VSC"] == "PLAUSIBLE_BUT_INSUFFICIENT_EVIDENCE"
    assert card["final_decision"] == "STOP_V3_11_COVERAGE_EXPANSION"


def test_sc_wet_yellow_red_not_started(terminal, card):
    assert terminal["sc_research_authorized"] is False
    assert terminal["wet_research_authorized"] is False
    assert terminal["yellow_research_authorized"] is False
    assert terminal["red_restart_research_authorized"] is False
    assert card["SC"] == "NOT_STARTED"
    assert card["WET"] == "NOT_STARTED"
    assert card["YELLOW"] == "NOT_STARTED"
    assert card["RED_RESTART"] == "NOT_STARTED"


def test_no_next_stage_authorized(terminal):
    assert terminal["no_further_coverage_stage_authorized"] is True
    assert terminal["existing_production_mc2_canonical"] is True
    assert "insufficient evidence, not refutation" in \
        terminal["scientific_reason"]


# ---- PRODUCTION PARITY ----

def test_no_production_integration_marker(card):
    assert card["production_effect"] == "none"
    manifest = _load("programme_manifest.json")
    assert manifest["production_diff_empty"] is True
    assert manifest["production_status_empty"] is True
    assert manifest["eligibility_delta"] == 0


def test_mc2_identity_unchanged():
    d_green = json.loads(
        (ROOT / "results" / "v3" / "v3_11d"
         / "green_parity_validation.json").read_text(encoding="utf-8"))
    assert d_green["production_diff_empty"] is True
    e_par = json.loads(
        (ROOT / "results" / "v3" / "v3_11e"
         / "parity_validation.json").read_text(encoding="utf-8"))
    assert e_par["verdict"] == "PASS"


# ---- PROVENANCE ----

def test_ae_artifacts_exist():
    assert (ROOT / "results" / "v3" / "v3_11a"
            / "unsupported_state_ledger.json").is_file()
    assert (ROOT / "results" / "v3" / "v3_11b"
            / "reconstruction_protocol.json").is_file()
    assert (ROOT / "results" / "v3" / "v3_11c"
            / "track_candidate_ledger.csv").is_file()
    assert (ROOT / "results" / "v3" / "v3_11d"
            / "vsc_episode_dataset.csv").is_file()
    assert (ROOT / "results" / "v3" / "v3_11e"
            / "evidence_resolution_protocol.json").is_file()


def test_final_references_without_rewrite(registry):
    for s, entry in registry.items():
        blob = (ROOT / entry["scientific_card"]).read_bytes()
        assert hashlib.sha256(blob).hexdigest() == \
            entry["scientific_card_sha256"], s


# ---- NAVIGATION ----

def test_index_references_final_status():
    text = (ROOT / "docs" / "INDEX.md").read_text(encoding="utf-8")
    assert "V3_11_MC2_COVERAGE_EXPANSION_FINAL" in text
    assert "STOP_V3_11_COVERAGE_EXPANSION" in text
    assert "V3.11E has not started" not in text


# ---- MANIFEST ----

def test_manifest_identities():
    text = (ROOT / "docs" / "V3_11_MC2_COVERAGE_EXPANSION_FINAL.md").read_text(
        encoding="utf-8")
    for name in ("programme_manifest.json",
                 "programme_scientific_card.json",
                 "terminal_decision.json"):
        digest = hashlib.sha256(
            (FINAL / name).read_bytes()).hexdigest()
        assert digest in text, name
        assert re.search(r"[0-9a-f]{64}", text)


def test_validation_manifest_consistent():
    manifest = _load("validation_manifest.json")
    tree = ast.parse(Path(__file__).read_text(encoding="utf-8"))
    n_here = sum(1 for n in ast.walk(tree)
                 if isinstance(n, ast.FunctionDef)
                 and n.name.startswith("test_"))
    assert manifest["f_freeze_tests"] == n_here
    assert manifest["collection_expected"] == 5289 + n_here
    assert manifest["p0_guard_review"]["verdict"] == "NOT_WEAKENED"
    assert manifest["v39_guard_review"]["verdict"] == \
        "NARROWLY_REPAIRED_EQUAL_STRENGTH"
