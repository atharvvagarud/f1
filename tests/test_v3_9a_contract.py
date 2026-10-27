"""V3.9A uncertainty-intelligence contract tests (synthetic fixtures only).

Contract + audit validation: no production computation, no MC2 reruns, no
API/UI. Frozen V3.8 + performance-freeze provenance is asserted, not modified.
"""

import hashlib
import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
A = ROOT / "results" / "v3" / "v3_9a"
V38 = "15df86b864fa552c69c4b7a53e22f1fc3b4c4ca1"
VTAG = "v3.8-model-simulation-consensus"
PERF = "32466c436845ee02c3af79ce08d1c102b9d91384"
PTAG = "v3.8-mc2-performance"


def _load(name):
    return json.loads((A / name).read_text())


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout.strip()


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


# --- provenance (frozen, not modified) ---


def test_v38_and_performance_provenance():
    assert _git("rev-list", "-n", "1", VTAG) == V38
    assert _git("rev-list", "-n", "1", PTAG) == PERF
    assert _git("merge-base", "--is-ancestor", V38, "HEAD") == ""
    assert _git("merge-base", "--is-ancestor", PERF, "HEAD") == ""
    reg = _load("source_registry.json")
    assert reg["parents"]["v38_commit"] == V38
    assert reg["parents"]["perf_commit"] == PERF


def test_frozen_performance_code_untouched():
    out = _git("status", "--porcelain=v1")
    touched = [ln.split()[-1] for ln in out.splitlines()
               if ln.startswith(("M ", " M"))]
    assert "raceintel/simulation/mc2/kernel.py" not in touched
    assert "raceintel/simulation/mc2/residuals.py" not in touched
    assert "raceintel/simulation/mc2_batch.py" not in touched


# --- source registry ---


def test_source_roles():
    reg = _load("source_registry.json")["sources"]
    assert reg["V3_1B_LOGISTIC"]["role"] == "PRIMARY_MODEL"
    assert reg["MC2_E"]["role"] == "PRIMARY_SIMULATOR"
    assert reg["MC2_E"]["production_config"]["futures"] == 5000
    assert reg["V3_4_ENSEMBLE"]["role"] == "EXCLUDED_FROM_V3_9_PRIMARY"
    assert reg["V3_5_MARGINALS"]["role"] == "SECONDARY_RESEARCH"
    assert reg["V3_3_XGBOOST"]["role"] == "SECONDARY_DIVERSITY_RESEARCH_ONLY"


def test_probability_families_preserved():
    from raceintel.consensus import contracts as C
    assert C.SOURCE_FAMILIES[C.SourceId.V3_1B_LOGISTIC] == \
        C.SourceFamily.INDEPENDENT_BINARY
    assert C.SOURCE_FAMILIES[C.SourceId.MC2_E] == \
        C.SourceFamily.MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY
    prod = (ROOT / "raceintel" / "consensus" / "product.py").read_text()
    assert "never" in prod and "race-normalized" in prod


def test_v34_ensemble_excluded_and_no_promotion():
    tax = _load("uncertainty_taxonomy.json")
    assert tax["rejected"]["V3_4_ENSEMBLE"].startswith("REJECTED")
    assert "V3_4" not in json.dumps(tax["families"])


# --- U1 disagreement ---


def test_disagreement_is_not_confidence():
    tax = _load("uncertainty_taxonomy.json")["families"]["U1_DISAGREEMENT"]
    assert tax["status"] == "PRIMARY_V3_9"
    for forbidden in ("confidence", "epistemic variance", "calibration error"):
        assert forbidden in tax["is_not"]
    # synthetic: model=0.8 vs simulation=0.4 -> gap exists, no confidence
    from raceintel.consensus import metrics as M
    assert M.absolute_gap(0.8, 0.4) == 0.4
    assert M.signed_gap(0.8, 0.4) == -0.4  # simulation_minus_model


def test_disagreement_metrics_reused_unchanged():
    from raceintel.consensus import metrics as M
    assert M.METRICS_IMPLEMENTATION_IDENTITY == "v3.8c-consensus-metrics-v1"
    assert M.PRIMARY_PAIR[0].value == "V3_1B_LOGISTIC"
    reg = _load("disagreement_metric_registry.json")
    assert reg["implementation"].startswith("v3.8c-consensus-metrics-v1")
    assert reg["orientation"] == "signed_gap = simulation_minus_model"
    assert set(reg["metrics"]) == {"rank_disagreement", "leader_disagreement",
                                   "topk_overlap", "magnitude_gap",
                                   "directional_temporal"}


# --- U2 sampling ---


def test_sampling_is_not_sensitivity_or_spread():
    tax = _load("uncertainty_taxonomy.json")["families"]["U2_MC_SAMPLING"]
    assert "simulator model uncertainty" in tax["is_not"]
    mc = _load("mc_sampling_contract.json")
    assert mc["outcome_spread_distinction"]["rule"].startswith("NOT the same")


def test_allowed_sampling_metrics_synthetic():
    from raceintel.consensus import metrics as M
    # k=0, n=5000 -> valid zero frequency, NOT missing
    assert M.mc_sampling_se(0.0, 5000) == 0.0
    lo, hi = M.wilson_interval(0.0, 5000)
    assert lo == 0.0 and hi > 0.0
    # production-scale spot check: max SE at p=0.5
    assert abs(M.mc_sampling_se(0.5, 5000) - math.sqrt(0.25 / 5000)) < 1e-12
    lo, hi = M.wilson_interval(0.5, 5000)
    assert lo < 0.5 < hi
    # n=0 raises -> INSUFFICIENT, never zero-filled
    try:
        M.mc_sampling_se(0.5, 0)
        raise AssertionError("n=0 must raise")
    except ValueError:
        pass
    try:
        M.wilson_interval(0.5, 0)
        raise AssertionError("n=0 must raise")
    except ValueError:
        pass
    mc = _load("mc_sampling_contract.json")
    assert mc["edge_behavior"]["p_hat=0"].startswith("VALID zero")


def test_zero_is_not_missing():
    st = _load("status_contract.json")["statuses"]
    assert "never encoded as 0" in _load("status_contract.json")["zero_rule"]
    assert st["MISSING_SOURCE"].endswith("NOT 0")
    assert st["INSUFFICIENT_SIMULATIONS"].endswith("NOT 0")


# --- U3 sensitivity ---


def test_sensitivity_range_requires_provenance():
    audit = _load("sensitivity_parameter_audit.json")
    assert audit["parameters"]["rho_ar1"]["status"] == "NEEDS_PROVENANCE"
    assert audit["parameters"]["regime_std_s"]["status"] == \
        "ELIGIBLE_FOR_SENSITIVITY_RESEARCH"
    assert audit["parameters"]["anchor_offset_s"]["status"] == \
        "UNSUPPORTED_FOR_SENSITIVITY"
    assert audit["parameters"]["dynamics_primary_decay"]["status"] == \
        "SCIENTIFICALLY_FIXED"
    assert "arbitrary" in audit["range_rule"]


def test_arbitrary_percentage_ranges_prohibited():
    blob = (_load("sensitivity_parameter_audit.json")["range_rule"]
            + _load("uncertainty_taxonomy.json")["families"]
            ["U3_SIMULATOR_SENSITIVITY"]["range_rule"])
    assert "arbitrary" in blob and "PROHIBITED" in blob
    # no invented numeric range anywhere in the audit (e.g. 5%/10%)
    assert "5%" not in blob and "10%" not in blob


def test_crn_policy_encoded_and_no_experiment():
    audit = _load("sensitivity_parameter_audit.json")["rng_policy_crn"]
    assert audit["rule"].startswith("compare configurations under COMMON RANDOM NUMBERS")
    assert audit["status"] == "POLICY_ENCODED_EXPERIMENT_DEFERRED"
    # no sensitivity experiment executed: no new runtime module. V3.9C may
    # own raceintel/uncertainty/{__init__,bundle}.py (thin bundle); anything
    # beyond that (e.g. sensitivity.py) still fails.
    pkg = ROOT / "raceintel" / "uncertainty"
    if pkg.exists():
        assert sorted(p.name for p in pkg.iterdir() if p.suffix == ".py") == \
            ["__init__.py", "bundle.py"]
    assert not (ROOT / "raceintel" / "simulation" / "sensitivity.py").exists()


# --- alignment / temporal / 2025 ---


def test_exact_alignment_contract():
    t = _load("temporal_contract.json")["alignment"]
    assert t["identity"].startswith("(state_id, driver_id)")
    assert "nearest-state substitution" in t["prohibited"]
    assert t["missing"].endswith("not zero")


def test_no_future_information():
    t = _load("temporal_contract.json")
    assert "outcome-blind" in t["runtime_rule"]
    assert "outcomes" in t["prohibited_future_inputs"]
    assert t["evaluation_labels"].startswith("offline")


def test_2025_policy_preserved():
    t = _load("temporal_contract.json")["policy_2025"]
    assert "PRODUCT-EXCLUDED" in t
    from raceintel.consensus import product as P
    assert 2025 in P.PRODUCT_EXCLUDED_SEASONS


# --- language / product / strategy ---


def test_claim_language_restrictions():
    cl = _load("claim_language_contract.json")
    assert any("disagree on the leading driver" in s for s in cl["allowed"])
    assert any("90% certain" in s for s in cl["prohibited"])
    assert any("true race probability" in s for s in cl["prohibited"])


def test_no_universal_confidence_score():
    tax = _load("uncertainty_taxonomy.json")
    assert "uncertainty_score" in tax["universal_score_prohibition"]
    assert "HIGH/MEDIUM/LOW universal confidence" in \
        tax["universal_score_prohibition"]
    assert tax["representation"].startswith("VECTOR")
    prod = _load("product_representation_contract.json")
    # the scalar appears ONLY inside the prohibited list, never as a field
    assert "CONFIDENCE: 82%" in prod["prohibited"]
    fields = json.dumps({k: v for k, v in prod.items()
                         if k != "prohibited"}).lower()
    assert "score" not in fields and "confidence" not in fields


def test_no_epistemic_aleatoric_without_construction():
    tax = _load("uncertainty_taxonomy.json")
    assert tax["epistemic_aleatoric_rule"].startswith("labels PROHIBITED")


def test_strategy_counterfactual_compatible_not_reinterpreted():
    tax = _load("uncertainty_taxonomy.json")["candidates"] \
        ["strategy_counterfactual_mc_sampling"]
    assert tax["status"] == "SECONDARY_V3_9"
    assert "not reinterpret as causal confidence" in tax["rationale"]
    from raceintel.strategy import objectives as O
    assert "Monte Carlo" in O.OBJECTIVE_SAMPLING_SEMANTICS or \
        "sampling" in O.OBJECTIVE_SAMPLING_SEMANTICS.lower()


def test_no_production_runtime_dependency():
    import subprocess as sp
    out = sp.run(["git", "status", "--porcelain=v1"], cwd=ROOT,
                 capture_output=True, text=True, check=True).stdout
    allowed_modified = {
        # Tier-1 pin reconciliation (collection guard reclassification).
        "scripts/run_ci_tests.py",
        # Freeze pin/pathology reconciliation for the v3_9a stage.
        "tests/test_perf_mc2_freeze.py",
        "tests/test_perf_mc2_p0.py",
        # Guard carve-out admissions for v3_9a contract paths (exact).
        "tests/test_v3_6a_contract.py",
        "tests/test_v3_6b_contracts.py",
        "tests/test_v3_6d_evaluation.py",
        "tests/test_v3_7a_contract.py",        "tests/test_v3_8a_consensus_contract.py",
        "tests/test_v3_8b_source_adapters.py",
        "tests/test_v3_8c_consensus_metrics.py",
        "tests/test_v3_8d_correction_01.py",
        "tests/test_v3_8d_evaluation.py",
        "tests/test_v3_8h_freeze.py",
        # P2A pathology allowlist admission for the same V3.9A set.
        "tests/test_mc2_p2a.py",
        # V3.9C carve-out: uncertainty router registration (additive).
        "api/main.py",
        # V3.9D carve-out: uncertainty nav entry (one line, presentation
        # only; already V3.8H-allowlisted wiring file).
        "frontend/components/shell/CommandBar.tsx",
        # V3.9E carve-out: freeze-owned guard reconciliations admitting
        # exact V3.9 paths (no science change).
        "tests/test_v3_5a_contract.py",
        "tests/test_v3_5b_dataset.py",
        "tests/test_v3_5c_harness.py",
        "tests/test_v3_5d_screening.py",
        "tests/test_v3_6f_runtime.py",
        # V3.10I reconciliation (freeze): exact V3.10 tracked
        # modifications (7 product files: shell, replay calm prop,
        # expert prefill x2, telemetry client/router; frozen science
        # untouched) plus these guard-allowlist edits themselves.
        "frontend/components/shell/AppShell.tsx",
        "frontend/features/counterfactuals/components/CounterfactualView.tsx",
        "frontend/features/replay/components/SpatialTrackPanel.tsx",
        "frontend/features/strategy/components/Strategy2View.tsx",
        "frontend/lib/v2.ts",
        "tests/test_v3_6f_runtime.py",
        "tests/test_v3_8h_freeze.py",
        "tests/test_v3_9a_contract.py",
        "tests/test_v3_9b_measurement.py",
        "tests/test_v3_9c_bundle.py",
        "tests/test_v3_9e_freeze.py",
        # V3.10I wave-2 reconciliations below (exact guard files
        # admitting the V3.10 set; frozen science untouched).
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
        # V3.11F reconciliation (freeze): narrow stale-guard repair
        # of the time-bound V3.9 HEAD pin (tag pin kept; ancestry
        # asserted with equal strength; frozen science untouched).
        "tests/test_v3_10b_workspace_ownership.py",
        # V3 Final reconciliation (freeze): navigation docs are
        # tracked since the V3.11 freeze; terminal-status lines
        # only (docs-only; frozen science untouched).
        "docs/INDEX.md",
        "scripts/README.md",
        # C5 post-V3: exact C5 client-consolidation files +
        # frontend-CI pin correction (44 files).
        "frontend/lib/v2.ts",
        "frontend/lib/spatial.ts",
        "frontend/lib/api.ts",
        "frontend/features/consensus/lib/consensusClient.ts",
        "frontend/features/uncertainty/lib/uncertaintyClient.ts",
        "scripts/run_ci_frontend_tests.py",
        # C1 post-V3: exact C1 suite-orchestration charter (Makefile
        # target recomposition only; no science/contract change).
        "Makefile",
    }
    for ln in out.splitlines():
        if ln.startswith(("M ", " M")):
            assert ln.split()[-1] in allowed_modified, ln
    # API-ownership precision lives in V3.9B's test (exact trio); V3.9A
    # itself adds no API files.


def test_bayesian_tyre_deferred():
    assert "deferred" in (ROOT / "docs"
                           / "V3_9A_UNCERTAINTY_INTELLIGENCE_CONTRACT.md"
                           ).read_text().lower()
    assert not (ROOT / "raceintel" / "simulation" / "bayesian_tyre.py").exists()


# --- card / pathology ---


def test_scientific_card_identity():
    card = _load("scientific_card.json")
    ident = card.pop("card_identity")
    assert hashlib.sha256(_canon(card)).hexdigest() == ident
    assert card["classification"] == \
        "UNCERTAINTY_CONTRACT_PARTIALLY_SUPPORTED"


def test_v39a_pathology_all_zero():
    counts = _load("validation.json")["pathology"]
    assert set(counts) == {f"V3.9A-P{i}" for i in range(1, 31)}
    bad = {k: v for k, v in counts.items() if v != 0}
    assert bad == {}, bad
    # live spot checks for the load-bearing prohibitions
    assert "uncertainty_score" not in (ROOT / "raceintel" / "consensus"
                                       / "metrics.py").read_text()
    assert "uncertainty_score" not in (ROOT / "raceintel" / "consensus"
                                       / "product.py").read_text()
