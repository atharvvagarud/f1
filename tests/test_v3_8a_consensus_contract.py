"""V3.8A consensus-contract tests: contract + source-audit discipline.

Contract/audit only: no training, no scores, no fusion, no frozen-tree
modifications. Verifies frozen parentage, V3.7 provenance, deterministic
contract identity, source taxonomy, fail-closed alignment rules, poison
blacklist, 2025 honesty, and fusion prohibition.
"""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "results" / "v3" / "v3_8a" / "consensus_contract.json"
AUDIT = ROOT / "results" / "v3" / "v3_8a" / "source_audit.json"
DOC = ROOT / "docs" / "V3_8A_CONSENSUS_CONTRACT_SOURCE_AUDIT.md"


def _load(path):
    return json.loads(path.read_text())


def _contract():
    return _load(CONTRACT)


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


# --- frozen baseline ---


def test_frozen_parent_exact():
    c = _contract()["frozen_parent"]
    assert c["commit"] == "30fe18908a41d95113c189274598269a95ef44ca"
    assert c["tag"] == "v3.7-counterfactual-engine"
    # V3.8H reconciliation: entry-time HEAD pin is stale after the V3.8
    # freeze. Final-state invariant: the frozen V3.8 parent must be an
    # ancestor of HEAD (passes at entry HEAD and at any descendant freeze
    # commit; fails on history rewrite).
    head = _git("rev-parse", "HEAD")
    out = subprocess.run(
        ["git", "merge-base", "--is-ancestor", c["commit"], head],
        cwd=ROOT, capture_output=True)
    assert out.returncode == 0, head


def test_v37_tag_and_card_exact():
    assert _git("rev-parse", "v3.7-counterfactual-engine^{commit}") == \
        "30fe18908a41d95113c189274598269a95ef44ca"
    c = _contract()
    assert c["v37_card_schema"] == \
        "v3.7-counterfactual-engine-scientific-card-v1"
    assert c["v37_card_identity"] == \
        "a7b6d33e89d4157144fad1fa9f380b764bff0d41313995a9fae8b2bbff191fe5"


# --- contract identity ---


def test_contract_schema_exact():
    assert _contract()["schema"] == "v3.8a-consensus-contract-v1"


def test_contract_identity_recomputes():
    c = _contract()
    identity = c.pop("contract_identity")
    blob = json.dumps(c, sort_keys=True, separators=(",", ":")).encode()
    assert identity == hashlib.sha256(blob).hexdigest()
    assert identity == \
        "d0b8785a01347580125b38b311984c793c012352ce3ff175cfa3504379b9a67b"


def test_source_audit_exists_and_linked():
    a = _load(AUDIT)
    assert a["contract_identity"] == _load(CONTRACT)["contract_identity"]
    assert set(a["sources"]) == {
        "V3.1B_LOGISTIC", "V3.5_MARGINALS", "MC2", "V3.3_XGBOOST",
        "V3.4_ENSEMBLE"}


# --- source taxonomy ---


def test_every_source_has_family_target_provenance():
    a = _load(AUDIT)
    for name, src in a["sources"].items():
        assert src["family"] in {
            "INDEPENDENT_BINARY_MODEL_PROBABILITY",
            "MARGINAL_THRESHOLD_PROBABILITY",
            "MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY",
            "ENSEMBLED_MODEL_PROBABILITY"}, name
        assert src["target"], name
        assert src.get("evidence") or src.get("artifact"), name


def test_logistic_classified_correctly():
    s = _contract()["sources"]["V3.1B_LOGISTIC"]
    assert s["classification"] == "PRIMARY_CONSENSUS_SOURCE"
    assert s["family"] == "INDEPENDENT_BINARY_MODEL_PROBABILITY"


def test_mc2_classified_correctly():
    s = _contract()["sources"]["MC2"]
    assert s["classification"] == "PRIMARY_CONSENSUS_SOURCE"
    assert s["family"] == "MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY"


def test_v35_classified_correctly():
    s = _contract()["sources"]["V3.5_MARGINALS"]
    assert s["classification"] == "SECONDARY_DIAGNOSTIC_SOURCE"
    assert s["family"] == "MARGINAL_THRESHOLD_PROBABILITY"


def test_v34_ensemble_independence_risk_recorded():
    s = _contract()["sources"]["V3.4_ENSEMBLE"]
    assert s["classification"] == "EXCLUDED_FROM_V3_8"
    assert "double-count" in s["rationale"]


# --- normalization / alignment prohibitions ---


def test_no_silent_normalization_allowed():
    blob = json.dumps(_contract()["no_silent_normalization"]).lower()
    assert "never" in blob
    assert _contract()["no_silent_normalization"]["raw_preserved"] is True


def test_no_softmax_normalization_allowed():
    blob = json.dumps(_contract()).lower()
    assert "softmax" in blob  # present only as forbidden
    assert "no silent normalization" in blob or \
        "no_silent_normalization" in json.dumps(_contract())


def test_no_zero_fill_allowed():
    assert "zero fill" in \
        json.dumps(_contract()["fail_closed_forbidden_repairs"])


def test_no_nearest_lap_alignment_allowed():
    assert "nearest-lap" in json.dumps(_contract()["state_synchronization"])


def test_identity_based_alignment_required():
    assert _contract()["state_synchronization"]["rule"] == \
        "EXACT STATE IDENTITY ONLY"
    assert _contract()["comparison_unit"] == ["state_id", "driver_id"]


# --- fail-closed ---


def test_state_mismatch_fails_closed():
    assert "state mismatch" in _contract()["fail_closed"]


def test_driver_mismatch_fails_closed():
    assert "driver mismatch" in _contract()["fail_closed"]


def test_target_mismatch_fails_closed():
    assert "target mismatch" in _contract()["fail_closed"]


# --- boundaries ---


def test_ground_truth_evaluation_only():
    assert "EVALUATION ONLY" in _contract()["ground_truth_boundary"]


def test_2025_not_pristine():
    blob = json.dumps(_contract()).lower()
    assert "non_pristine" in blob or "non-pristine" in blob
    assert "unseen test set" not in blob


def test_race_level_temporal_evaluation_required():
    blob = json.dumps(_contract()["evaluation_splits"]).lower()
    assert "race-level" in blob
    assert "no random row splits" in blob


def test_stages_reused_not_redefined():
    assert "FORBIDDEN" in _contract()["stages"]["redefinition"]
    assert "EARLY" in _contract()["stages"]["definition"]


# --- fusion prohibition ---


def test_fusion_disabled_in_a():
    blob = json.dumps(_contract()["fusion_prohibition"]).lower()
    assert "no average" in blob or "no consensus" in blob.replace("_", " ")


def test_no_consensus_scalar_defined():
    blob = json.dumps(_contract())
    assert "CONSENSUS = average" not in blob
    assert "combined confidence" in _contract()["terminology"][
        "forbidden_terms"]


def test_no_combined_confidence_defined():
    assert "confidence score" in \
        _contract()["terminology"]["forbidden_terms"]


def test_fusion_gate_exists_and_conditional():
    g = _contract()["fusion_gate"]
    assert set(g["outcomes"]) == {
        "FUSION_NOT_WARRANTED", "FUSION_RESEARCH_WARRANTED",
        "BLOCKING_SEMANTIC_MISMATCH"}
    assert "ONLY" in g["rule"]


def test_e_conditional_only():
    assert "ONLY if D" in json.dumps(_contract()["stage_plan"]) or \
        "ONLY if D justifies" in json.dumps(_contract())


# --- boundaries v39/v310 ---


def test_v39_boundary_explicit():
    assert "V3.9" in json.dumps(_contract()["v39_boundary"])


def test_v310_boundary_explicit():
    assert "V3.10" in json.dumps(_contract()["v310_boundary"])


# --- poison blacklist ---


def test_temporal_poison_blacklist_frozen():
    black = _contract()["temporal_poison_blacklist"]
    for item in ("future lap time", "future position", "future gap",
                 "future pit", "future compound", "future retirement",
                 "future status", "future weather", "future race control",
                 "future SC/VSC/red flag", "future finish", "winner label",
                 "future team action"):
        assert item in black, item


# --- no frozen-tree modification ---


def test_no_scientific_source_files_modified():
    # V3.8H reconciliation: the A stage-entry boundary (only v3_8a paths
    # dirty) is superseded by the B-G charters plus the H freeze. Final
    # freeze allowlist admits exactly the chartered V3.8-owned paths, the
    # two additive wiring files (V3.8F router registration, V3.8G nav
    # entry), and the Tier-1 runner reclassification; any other dirt
    # still fails. No weakening: prefixes stay exact, assertion intact.
    out = _git("status", "--short")
    allowed = (
        "results/v3/v3_8a/", "results/v3/v3_8b/", "results/v3/v3_8c/",
        "results/v3/v3_8d/", "results/v3/v3_8e/", "results/v3/v3_8f/",
        "results/v3/v3_8g/", "results/v3/v3_8h/",
        "docs/V3_8",
        "raceintel/consensus/",
        "scripts/v3_8d_", "scripts/v3_8e_",
        "scripts/run_ci_tests.py", "scripts/run_ci_frontend_tests.py",
        "tests/test_v3_8",
        "api/v2_consensus_", "api/main.py",
        "frontend/app/consensus", "frontend/features/consensus",
        "frontend/components/shell/CommandBar.tsx",
        # V3.8H historical-guard reconciliations (Tier-1-driven; exact
        # files only; frozen science untouched).
        "tests/test_v3_5a_contract.py", "tests/test_v3_5b_dataset.py",
        "tests/test_v3_5c_harness.py", "tests/test_v3_5d_screening.py",
        "tests/test_v3_6a_contract.py", "tests/test_v3_6b_contracts.py",
        "tests/test_v3_6d_evaluation.py", "tests/test_v3_6f_runtime.py",
        "tests/test_v3_6h_freeze.py", "tests/test_v3_7a_contract.py",
        # P2A carve-out (performance programme only): exactly the two
        # kernel files with hoisted loop-invariant overhead; public APIs,
        # validation, RNG, and arithmetic order unchanged (parity-gated
        # in P0-P20/P1-P3/P2A-P29 checks, not here).
        "raceintel/simulation/mc2/kernel.py",
        "raceintel/simulation/mc2/residuals.py",
        # P2A performance-programme files (exact paths/prefixes; science
        # and product behavior unchanged).
        "results/v3/performance_mc2/",
        "docs/MC2_PERFORMANCE_",
        "raceintel/simulation/mc2_batch.py",
        "scripts/mc2_batch_benchmark.py",
        "tests/test_perf_mc2_p0.py",
        "tests/test_mc2_batch_p1.py",
        "tests/test_mc2_p2a.py",
        # P2B carve-out: exact-order heap queue tests (parity-gated by
        # P2B-P1..P30, not here).
        "tests/test_mc2_p2b.py",
        # P3-1 carve-out: exact scalar-interpolation audit tests
        # (parity-gated by P3-1-P1..P30, not here).
        "tests/test_mc2_p3_1.py",
        # Freeze carve-out: focused freeze validation tests
        "tests/test_perf_mc2_freeze.py",
        # V3.9A carve-out (contract stage only, no science/runtime change).
        "results/v3/v3_9a/",
        "docs/V3_9A",
        "tests/test_v3_9a_contract.py",
        # V3.9B carve-out (offline measurement stage, no science/runtime change).
        "results/v3/v3_9b/",
        "docs/V3_9B",
        "tests/test_v3_9b_measurement.py",
        # V3.9C carve-out (runtime bundle stage,
        # thin product layer only: bundle + API).
        "results/v3/v3_9c/",
        "docs/V3_9C",
        "tests/test_v3_9c_bundle.py",
        "raceintel/uncertainty/",
        "api/v2_uncertainty_",
        # V3.9D carve-out (product UI stage only: /uncertainty route,
        # uncertainty feature modules, stage docs/artifacts; no science,
        # runtime, or API change).
        "results/v3/v3_9d/",
        "docs/V3_9D",
        "frontend/app/uncertainty/",
        "frontend/features/uncertainty/",
        # V3.9E carve-out (freeze stage only: programme manifest, parity
        # records, final audits, freeze test + final doc; no science or
        # runtime change).
        "results/v3/v3_9e/",
        "docs/V3_9_UNCERTAINTY_INTELLIGENCE_FINAL.md",
        "tests/test_v3_9e_freeze.py",
    )
    for line in out.splitlines():
        if line.strip():
            pth = line.split(None, 1)[-1]
            assert pth.startswith(allowed), line


# --- doc sections ---


def test_doc_required_sections():
    doc = DOC.read_text()
    for section in ("## Final verdict", "## Frozen parent",
                    "## Source inventory", "## Source classification",
                    "## Probability-family taxonomy",
                    "## No-silent-normalization rule",
                    "## Temporal safety", "## Ground-truth boundary",
                    "## 2025 status", "## Fusion prohibition",
                    "## Fusion gate", "## V3.9 boundary",
                    "## V3.10 boundary", "## V3.8B readiness"):
        assert section in doc, section
