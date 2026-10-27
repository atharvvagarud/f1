"""V3.6A contract tests: audit-only gate for the Strategy 2.0 scientific contract.

Asserts frozen parentage, V3.5/MC2/Phase-7 identities, CRN/baseline/outcome/
eligibility semantics, prohibited fusion, boundaries, and no runtime changes.
"""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "results" / "v3" / "v3_6a" / "strategy_contract.json"
LANDSCAPE_PATH = ROOT / "results" / "v3" / "v3_6a_strategy_landscape.json"
DOC_PATH = ROOT / "docs" / "V3_6A_STRATEGY_LANDSCAPE_AND_SCIENTIFIC_CONTRACT.md"


def _load(path):
    return json.loads(path.read_text())


def _contract():
    return _load(CONTRACT_PATH)


def _canonical_hash(payload):
    core = {k: v for k, v in payload.items() if k != "contract_hash"}
    blob = json.dumps(core, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(blob).hexdigest()


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


# --- parent ---


def test_parent_tag_exact():
    assert _contract()["parent"]["tag"] == "v3.5-outcome-distribution"


def test_parent_commit_exact():
    assert (
        _contract()["parent"]["commit"]
        == "6df5d41d3ebead9a1c9b4f0f40ed20a21ce0bff1"
    )


def test_head_matches_parent():
    # V3.7H reconciliation (2026): entry-time pin to 6df5d41 (V3.6A parent)
    # is stale after the V3.6 freeze. Final-state invariant: the frozen
    # V3.6 parent 1eb462631b9d7a948e35b8a1658e3bb90035c94c must be an
    # ancestor of HEAD (passes at V3.6 freeze HEAD and any descendant
    # freeze commit; fails on history rewrite).
    head = _git("rev-parse", "HEAD")
    frozen = "1eb462631b9d7a948e35b8a1658e3bb90035c94c"
    out = subprocess.run(
        ["git", "merge-base", "--is-ancestor", frozen, head], cwd=ROOT,
        capture_output=True)
    assert out.returncode == 0, head


# --- V3.5 identity ---


def test_v35_card_identity_exact():
    c = _contract()["v35_identity"]
    assert c["scientific_card_identity"] == (
        "8d3a8d2ec6aef5d4bb50306036e100b0db6c83386c19ec8f7ce07ae25714446d"
    )
    assert c["task"] == "ordered_cumulative_finish_thresholds"
    assert c["champion"] == "LOGISTIC_CONTROL"
    assert c["research_candidate"].startswith("XGB_E")


def test_v35_serving_none():
    assert _contract()["v35_identity"]["serving"] == "NONE"


def test_v35_semantics_marginal():
    sem = _contract()["v35_identity"]["probability_semantics"]
    assert "PER_DRIVER_MARGINAL" in sem
    assert "NOT a joint finishing-order distribution" in sem


def test_v35_matches_frozen_card():
    frozen = _load(ROOT / "results" / "v3" / "v3_5_final_scientific_card.json")
    c = _contract()["v35_identity"]
    assert frozen["scientific_card_identity"] == c["scientific_card_identity"]
    assert frozen["serving"] == "NONE"
    assert frozen["champion"] == "LOGISTIC_CONTROL"
    assert "PER_DRIVER_MARGINAL" in frozen["probability_semantics"]


# --- MC2 kept separate / no fusion ---


def test_mc2_identity():
    m = _contract()["mc2_identity"]
    assert m["tag"] == "v3.2-monte-carlo-2"
    assert m["commit"] == "197979d40af0c9dbf90667781d9c83e41613b047"
    assert m["accepted_simulator"].startswith("MC2-E")
    assert m["production_demo_count"] == 5000


def test_no_normalization_or_averaging():
    fused = _contract()["prohibited_fusion"]
    text = " ".join(fused).lower()
    assert "normalization" in text
    assert "averaging" in text or "average" in text
    assert "fusion" in text or "fuse" in text
    assert "stack" in text


def test_no_fusion():
    role = _contract()["v35_role"]
    assert role["primary"] == "C_VALIDATION_CONSISTENCY_SIGNAL"
    assert "V3.8" in role["v38_note"]


# --- Phase 7 audit ---


def test_phase7_audit_complete():
    p = _contract()["phase7_audit_identity"]
    for key in ("actions", "contracts", "crn", "estimator", "uncertainty",
                "objectives", "probability_semantics", "engine"):
        assert key in p, key
    assert set(p["actions"]) == {"STAY_OUT", "PIT_NOW", "PIT_NEXT_LAP"}
    assert p["candidate_space"] == 9
    assert "paired" in p["estimator"].lower()


# --- scientific question / comparison / baseline ---


def test_scientific_question_frozen():
    q = _contract()["scientific_question"]
    assert "causal race state" in q
    assert "paired stochastic futures" in q
    lowered = q.lower()
    assert "best" not in lowered and "optimal" not in lowered


def test_comparison_key_defined():
    u = _contract()["comparison_unit"]
    assert u["key_name"] == "StrategyComparisonKey"
    joined = json.dumps(u["fields"])
    for field in ("race_id", "driver_id", "baseline_action",
                  "alternative_action", "paired_seed_set"):
        assert field in joined, field


def test_baseline_semantics_explicit():
    b = _contract()["baseline_semantics"]
    assert "SIMULATED_NO_INTERVENTION_REFERENCE" in b["adopted_baseline"]
    assert "historical_observed_future" in b["terminology"]
    assert "POST_T_FORBIDDEN" in json.dumps(b) or "forbidden" in json.dumps(b).lower()


def test_action_set_closed():
    a = _contract()["action_policy"]
    assert len(a["admitted_initial"]) == 9
    assert "UNDERCUT" in json.dumps(a).upper() or "undercut" in json.dumps(a).lower()


def test_crn_semantics_explicit():
    crn = _contract()["crn_semantics"]
    assert "paired_seed_set" in json.dumps(_contract()["comparison_unit"])
    assert "complete valid pairs" in crn["pairing_unit"]
    assert "structural_divergence_rule" in crn


# --- outcomes / primary / uncertainty ---


def test_outcome_scorecard_complete():
    oc = _contract()["outcome_measures"]["classification"]
    for key in ("WIN_FREQ_DIFF", "PODIUM_FREQ_DIFF", "TOP5_FREQ_DIFF",
                "TOP10_FREQ_DIFF", "EXPECTED_FINISH_DIFF", "EXPECTED_POINTS",
                "DOWNSIDE_RISK", "DNF_RETIREMENT_OUTCOMES"):
        assert key in oc, key


def test_primary_outcome_policy_explicit():
    p = _contract()["primary_outcome_policy"]
    assert p["decision"] == "NO_SINGLE_UNIVERSAL_PRIMARY_UTILITY"
    assert "FORBIDDEN" in p["synthetic_score"]


def test_uncertainty_terminology_explicit():
    u = _contract()["uncertainty_semantics"]
    assert "MONTE_CARLO_SAMPLING_UNCERTAINTY_ONLY" in u["terminology"]
    assert "real-world confidence interval" in u["terminology"]


# --- eligibility / unsupported ---


def test_eligibility_explicit():
    e = _contract()["eligibility_policy"]
    assert "target_driver_not_in_roster" in json.dumps(e)
    assert "reason" in json.dumps(e).lower()


def test_unsupported_not_negative():
    pol = _contract()["unsupported_state_policy"]
    assert "UNSUPPORTED != NEGATIVE RESULT" in pol


# --- leakage ---


def test_future_data_risk_table_complete():
    table = _contract()["historical_action_leakage_policy"]["risk_table"]
    for key in ("historical_action_after_T", "race_results_table",
                "simulation_futures", "v35_probabilities",
                "status_corpus_retired_transitions"):
        assert key in table, key
    assert table["historical_action_after_T"].startswith("POST_T_FORBIDDEN")


def test_historical_future_not_decision_input():
    forb = _contract()["historical_action_leakage_policy"]["forbidden"]
    assert any("pit events" in f for f in forb)
    assert any("finish" in f for f in forb)


def test_ground_truth_limitation_explicit():
    assert "counterfactual" in json.dumps(_contract()).lower()
    doc = DOC_PATH.read_text()
    assert "Counterfactual ground-truth limitation" in doc


# --- product language / architecture / boundaries ---


def test_product_language_policy_explicit():
    doc = DOC_PATH.read_text()
    assert "## Product language" in doc
    assert "BEST" in doc and "GUARANTEED" in doc


def test_selected_architecture_explicit():
    a = _contract()["architecture"]
    assert a["selected"] == (
        "OPTION_2_THIN_PAIRED_LAYER_AROUND_FROZEN_MC2_PRESERVING_PHASE7"
    )
    assert len(a["options_considered"]) == 3


def test_v37_boundary_explicit():
    b = _contract()["v37_boundary"]
    assert "v37_owns" in b and "v36_owns" in b
    assert any("weather" in x for x in b["v37_owns"])


def test_v38_boundary_explicit():
    assert "V3.8" in _contract()["v38_boundary"]


# --- no runtime changes ---


def _changed_files():
    out = _git("status", "--short")
    return [line.split()[-1] for line in out.splitlines() if line.strip()]


def test_no_serving_api_frontend_mc2_v35_changes():
    allowed_prefixes = ("results/v3/v3_6a", "results/v3/v3_6a_strategy",
                        "results/v3/v3_6b", "results/v3/v3_6b_readiness",
                        "results/v3/v3_6c", "results/v3/v3_6c_paired_engine",
                        "results/v3/v3_6d", "results/v3/v3_6d_historical",
                        "docs/V3_6A", "docs/V3_6B", "docs/V3_6C",
                        "docs/V3_6D", "docs/V3_6F",
                        "results/v3/v3_6f", "results/v3/v3_6f_runtime",
                        "tests/test_v3_6f",
                        "scripts/v3_6f_",
                        # V3.6H Tier-1 reclassification (freeze
                        # machinery; frozen science untouched): allowed.
                        "scripts/ci_corpus_dependent.txt",
                        "scripts/run_ci_tests.py",
                        "scripts/run_ci_frontend_tests.py",
                        # V3.6F additive runtime/API/cache integration
                        # (chartered; frozen science untouched): allowed.
                        "api/v2_strategy_v3_", "api/main.py",
                        # V3.6G Strategy 2.0 frontend replacement
                        # (chartered; backend/science untouched): allowed.
                        # Covers Strategy2View/Strategy2Results/
                        # useStrategy2/strategy2Machine(+tests), the
                        # page.tsx switch, the append-only lib/v2.ts v3
                        # client, the strategyMachine.test.ts guard
                        # update, the G doc/results, and exactly the
                        # three deleted Phase-7 presentation paths.
                        "docs/V3_6G", "results/v3/v3_6g",
                        "frontend/app/strategy/page.tsx",
                        "frontend/features/strategy/components/Strategy",
                        "frontend/features/strategy/hooks/useStrategy",
                        "frontend/features/strategy/lib/strategy",
                        "frontend/lib/v2.ts",
                        # V3.6H freeze machinery (provenance-neutral):
                        # card/freeze records, H doc, H tests, and these
                        # guard-allowlist edits themselves.
                        "docs/V3_6H", "results/v3/v3_6_final",
                        "results/v3/v3_6_freeze", "tests/test_v3_6h",
                        "tests/test_v3_6a", "tests/test_v3_6b",
                        "tests/test_v3_6c_engine", "tests/test_v3_6d",
                        # V3.6H guard-allowlist corrections to V3.5
                        # stage guards (broken-test category): allowed.
                        "tests/test_v3_5",
                        # V3.7H guard-allowlist corrections to V3.4/V3.5
                        # stage guards (provenance-neutral): allowed.
                        "tests/test_v3_4e",
                        "scripts/v3_6d_",
                        # V3.6B pure typed contracts (no execution): allowed.
                        # V3.6C thin orchestration layer (wraps frozen
                        # Phase-7/MC2; no frozen behavior change): allowed.
                        "raceintel/strategy/v3_contracts.py",
                        "raceintel/strategy/v3_engine.py",
                        # V3.7H reconciliation (2026): V3.7 charters
                        # explicitly supersede the V3.6A stage-entry
                        # boundary. Admitted exactly (frozen science
                        # untouched; any other path still fails):
                        # A/B research contracts, C engine package, D
                        # evaluation, F runtime/API/cache, G frontend.
                        "results/v3/v3_7",
                        "docs/V3_7",
                        "tests/test_v3_7",
                        "scripts/v3_7",
                        "raceintel/counterfactual/",
                        # V3.7C additive MC2 seam (chartered; pinned hash
                        # preserves the no-mutation protection).
                        "raceintel/simulation/monte_carlo.py",
                        # V3.7F additive API integration (chartered).
                        "api/v2_counterfactual_",
                        # V3.7G Counterfactual Explorer (chartered;
                        # backend/science untouched).
                        "frontend/app/counterfactuals",
                        "frontend/features/counterfactuals",
                        "frontend/components/shell/CommandBar.tsx",
                        # V3.8H reconciliation (2026): V3.8 charters
                        # explicitly supersede the V3.6A stage-entry
                        # boundary. Admitted exactly (frozen science
                        # untouched; any other path still fails):
                        # V3.8 research/evaluation/product artifacts,
                        # consensus science package, D/E scripts, F API
                        # integration, G frontend, H freeze, H tests,
                        # Tier-1 reclassification, H reconciliations of
                        # historical guards themselves.
                        "results/v3/v3_8", "docs/V3_8",
                        "tests/test_v3_8",
                        "tests/test_v3_7a",
                        "scripts/v3_8",
                        "raceintel/consensus/",
                        "api/v2_consensus_",
                        "frontend/app/consensus",
                        "frontend/features/consensus",
                        # P2A carve-out (performance programme only):
                        # exactly the two kernel files with hoisted
                        # loop-invariant overhead (parity-gated in
                        # P0-P20/P1-P3/P2A-P29 checks, not here) plus
                        # the performance-programme files (exact paths).
                        "raceintel/simulation/mc2/kernel.py",
                        "raceintel/simulation/mc2/residuals.py",
                        "raceintel/simulation/mc2_batch.py",
                        "scripts/mc2_batch_benchmark.py",
                        "results/v3/performance_mc2/",
                        "docs/MC2_PERFORMANCE_",
                        "tests/test_perf_mc2_p0.py",
                        "tests/test_mc2_batch_p1.py",
                        "tests/test_mc2_p2a.py",
                        # P2B carve-out: exact-order heap queue tests
                        # (parity-gated by P2B-P1..P30, not here).
                        "tests/test_mc2_p2b.py",
                        # P3-1 carve-out: exact scalar-interpolation audit
                        # tests (parity-gated by P3-1-P1..P30, not here).
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
                        # V3.9D carve-out (product UI stage only:
                        # /uncertainty route, uncertainty feature modules,
                        # stage docs/artifacts; no science change).
                        "results/v3/v3_9d/",
                        "docs/V3_9D",
                        "frontend/app/uncertainty/",
                        "frontend/features/uncertainty/",
                        # V3.9E carve-out (freeze stage only: programme
                        # manifest, parity records, final audits, freeze
                        # test + final doc; no science change).
                        "results/v3/v3_9e/",
                        "docs/V3_9_UNCERTAINTY_INTELLIGENCE_FINAL.md",
                        "tests/test_v3_9e_freeze.py",
                        # V3.10I reconciliation (freeze): V3.10A-H
                        # charters admitted exactly (pit-wall product,
                        # workspace substrate, read-only telemetry API,
                        # stage docs/artifacts/scripts/tests, and these
                        # guard-allowlist edits themselves; frozen
                        # science untouched; any other path still fails).
                        "results/v3/v3_10",
                        "docs/V3_10",
                        "tests/test_v3_10",
                        "tests/test_v3_6a_contract.py",
                        "tests/test_v3_6b_contracts.py",
                        "tests/test_v3_6d_evaluation.py",
                        "tests/test_v3_6f_runtime.py",
                        "tests/test_v3_7a_contract.py",
                        "tests/test_v3_8h_freeze.py",
                        "tests/test_v3_9a_contract.py",
                        "tests/test_v3_9b_measurement.py",
                        "tests/test_v3_9c_bundle.py",
                        "tests/test_v3_9e_freeze.py",
                        "tests/test_perf_mc2_freeze.py",
                        "scripts/v3_10",
                        "scripts/run_ci_tests.py",
                        "api/v2_telemetry_",
                        "frontend/app/pit-wall/",
                        "frontend/features/pit-wall/",
                        "frontend/features/workspace/",
                        "frontend/components/shell/AppShell.tsx",
                        "frontend/features/replay/components/SpatialTrackPanel.tsx",
                        # V3.10I wave-2 reconciliations below (exact
                        # guard files admitting the V3.10 set; frozen
                        # science untouched).
                        "tests/test_v3_5a_contract.py",
                        "tests/test_v3_5b_dataset.py",
                        "tests/test_v3_5c_harness.py",
                        "tests/test_v3_5d_screening.py",
                        "tests/test_v3_8a_consensus_contract.py",
                        "tests/test_v3_8b_source_adapters.py",
                        "tests/test_v3_8c_consensus_metrics.py",
                        "tests/test_v3_8d_correction_01.py",
                        "tests/test_v3_8d_evaluation.py",
                        "tests/test_mc2_batch_p1.py",
                        "tests/test_mc2_p2a.py",
                        "tests/test_mc2_p2b.py",
                        "tests/test_mc2_p3_1.py",
                        "tests/test_perf_mc2_p0.py",
                        "tests/test_v2_phase5_r7.py",
                        "tests/test_v3_2i_status_models.py",
                        # V3.11F reconciliation (freeze): V3.11A-F
                        # charters admitted exactly (coverage forensics,
                        # causal reconstruction, track/regime forensics,
                        # VSC model, evidence resolution, programme
                        # freeze + navigation baseline; frozen science
                        # untouched; any other path still fails).
                        "results/v3/v3_11",
                        "docs/V3_11",
                        "docs/INDEX.md",
                        "tests/test_v3_11",
                        "scripts/v3_11",
                        "scripts/README.md",
                        "scripts/run_ci_tests.py",
                        "tests/test_perf_mc2_freeze.py",
                        "tests/test_perf_mc2_p0.py",
                        "tests/test_mc2_p2a.py",
                        "tests/test_v3_10b_workspace_ownership.py",
                        "tests/test_v3_8h_freeze.py",
                        "tests/test_v3_9e_freeze.py",
                        "tests/test_v3_6a_contract.py",
                        "tests/test_v3_7a_contract.py",
                        "tests/test_v3_8a_consensus_contract.py",
                        "tests/test_v3_8b_source_adapters.py",
                        "tests/test_v3_8c_consensus_metrics.py",
                        "tests/test_v3_8d_correction_01.py",
                        "tests/test_v3_8d_evaluation.py",
                        "tests/test_v3_9a_contract.py",
                        "tests/test_v3_9b_measurement.py")
    for f in _changed_files():
        assert any(f.startswith(p) for p in allowed_prefixes), f


def test_no_api_change():
    # V3.6F charter admits exactly its additive integration files; any
    # other api/ change still fails.
    # V3.7H reconciliation: V3.7F charter additionally admits exactly the
    # counterfactual API integration files (frozen science untouched).
    # V3.8H reconciliation: V3.8F charter additionally admits exactly the
    # consensus API integration files (frozen science untouched).
    # V3.10I reconciliation: V3.10F charter additionally admits exactly
    # the read-only telemetry API trio (frozen science untouched).
    allowed = ("api/v2_strategy_v3_", "api/main.py",
               "api/v2_counterfactual_", "api/v2_consensus_",
               # V3.9C carve-out: uncertainty bundle API (additive).
               "api/v2_uncertainty_",
               "api/v2_telemetry_")
    assert not any(f.startswith("api/") and not f.startswith(allowed)
                   for f in _changed_files())


def test_no_frontend_change():
    # V3.6G charter admits exactly its Strategy 2.0 replacement files;
    # any other frontend/ change still fails.
    # V3.7H reconciliation: V3.7G charter additionally admits exactly the
    # Counterfactual Explorer paths (backend/science untouched).
    # V3.8H reconciliation: V3.8G charter additionally admits exactly the
    # consensus frontend paths (backend/science untouched).
    # V3.9D reconciliation: V3.9D charter additionally admits exactly the
    # uncertainty product UI paths (presentation only; frozen science
    # untouched).
    allowed = ("frontend/app/strategy/page.tsx",
               "frontend/features/strategy/components/Strategy",
               "frontend/features/strategy/hooks/useStrategy",
               "frontend/features/strategy/lib/strategy",
               "frontend/lib/v2.ts",
               "frontend/app/counterfactuals",
               "frontend/features/counterfactuals",
               "frontend/app/consensus", "frontend/features/consensus",
               "frontend/app/uncertainty",
               "frontend/features/uncertainty",
               "frontend/components/shell/CommandBar.tsx",
               # V3.10I reconciliation: V3.10A-H pit-wall product
               # admitted exactly (workspace substrate, shell,
               # replay calm-announcement prop, expert prefill,
               # read-only telemetry client; frozen science untouched).
               "frontend/app/pit-wall/",
               "frontend/features/pit-wall/",
               "frontend/features/workspace/",
               "frontend/components/shell/AppShell.tsx",
               "frontend/features/replay/components/SpatialTrackPanel.tsx")
    assert not any(f.startswith("frontend/") and not f.startswith(allowed)
                   for f in _changed_files())


def test_no_mc2_change():
    # V3.7H reconciliation: V3.7C charter admits exactly the additive MC2
    # seam in raceintel/simulation/monte_carlo.py. The pinned SHA-256
    # preserves the no-mutation protection: any byte drift fails.
    # P2A carve-out (performance programme only): exactly kernel.py +
    # residuals.py with hoisted loop-invariant overhead; public APIs,
    # validation, RNG, and arithmetic order unchanged (parity-gated in
    # P0-P20/P1-P3/P2A-P29 checks, not here). Any other
    # raceintel/simulation change still fails.
    allowed = ("raceintel/simulation/monte_carlo.py",
               "raceintel/simulation/mc2/kernel.py",
               "raceintel/simulation/mc2/residuals.py",
               "raceintel/simulation/mc2_batch.py")
    changed = _changed_files()
    assert not any(
        f.startswith("raceintel/simulation") and f not in allowed
        for f in changed
    )
    if "raceintel/simulation/monte_carlo.py" in changed:
        import hashlib as _hl
        digest = _hl.sha256(
            (ROOT / "raceintel/simulation/monte_carlo.py").read_bytes()
        ).hexdigest()
        assert digest == ("045f392e46b030744f18a76140685ceba7501f80c0b8e265"
                          "af662e57ca5f5376")


def test_no_v35_change():
    changed = _changed_files()
    assert not any("v3_5" in f and f.startswith("raceintel/") for f in changed)
    assert not any("v3_5" in f and f.startswith("src/") for f in changed)


# --- determinism / artifacts ---


def test_contract_hash_deterministic():
    c = _contract()
    assert c["contract_hash"] == _canonical_hash(c)


def test_landscape_exists_and_consistent():
    land = _load(LANDSCAPE_PATH)
    c = _contract()
    assert land["entry_state"]["commit"] == c["parent"]["commit"]
    assert land["selected_architecture"] == c["architecture"]["selected"]
    assert land["v35_role_scorecard"]["C_VALIDATION_CONSISTENCY"] == (
        "SELECTED (primary)"
    )


def test_doc_required_sections():
    doc = DOC_PATH.read_text()
    for section in ("## Final verdict", "## Frozen parent",
                    "## Scientific question", "## Phase 7 strategy audit",
                    "## MC2 audit", "## V3.5 role decision",
                    "## Prohibited fusion", "## V3.7 boundary",
                    "## V3.8 boundary", "## Stage plan",
                    "## V3.6B recommendation"):
        assert section in doc, section
