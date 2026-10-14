"""V3.7A research-contract tests: counterfactual landscape discipline.

Audit-only: no simulations, no runtime changes. Asserts frozen V3.6
parentage, the V3.7 counterfactual definition, the complete candidate
inventory with exact classifications, boundaries, and no frozen-tree
modifications.
"""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = ROOT / "results" / "v3" / "v3_7a" / "counterfactual_contract.json"
LANDSCAPE = ROOT / "results" / "v3" / "v3_7a_counterfactual_landscape.json"
DOC = ROOT / "docs" / "V3_7A_COUNTERFACTUAL_LANDSCAPE_AND_SCIENTIFIC_CONTRACT.md"


def _load(path):
    return json.loads(path.read_text())


def _contract():
    return _load(CONTRACT)


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


# --- V3.6 parent ---


def test_v36_parent_exact():
    c = _contract()["parent"]
    assert c["tag"] == "v3.6-strategy-2.0"
    assert c["commit"] == "1eb462631b9d7a948e35b8a1658e3bb90035c94c"


def test_v36_tag_exact():
    assert _git("rev-parse", "v3.6-strategy-2.0^{commit}") == \
        "1eb462631b9d7a948e35b8a1658e3bb90035c94c"


def test_v36_card_exact():
    assert _contract()["v36_scientific_card_identity"] == \
        "102079ab81101f442d380c109a32b71a3b6850f0106e021f0fc4b05a64c80aeb"
    card = _load(ROOT / "results" / "v3" / "v3_6_final_scientific_card.json")
    assert card["scientific_card_identity"] == \
        _contract()["v36_scientific_card_identity"]


def test_baseline_clean_at_entry():
    # Only V3.7 research-contract/engine/evaluation paths may be dirty.
    # V3.7H reconciliation: C/F/G charters explicitly supersede the A
    # stage-entry boundary. Final-phase allowlist admits exactly the
    # chartered C seam, F API/runtime, G frontend, and H freeze paths;
    # any other dirt still fails.
    out = _git("status", "--short")
    allowed = ("results/v3/v3_7a", "results/v3/v3_7a_counterfactual",
               "results/v3/v3_7b", "results/v3/v3_7b_readiness",
               "results/v3/v3_7c", "results/v3/v3_7d",
               "results/v3/v3_7d_historical_evaluation",
               "results/v3/v3_7f", "results/v3/v3_7g", "results/v3/v3_7h",
               "results/v3/v3_7_",
               # V3.7H freeze card + validation artifact directory.
               "results/v3/v3_7/",
               "docs/V3_7A", "docs/V3_7B", "docs/V3_7C", "docs/V3_7D",
               "docs/V3_7F", "docs/V3_7G", "docs/V3_7H",
               "tests/test_v3_7a", "tests/test_v3_7b", "tests/test_v3_7c",
               "tests/test_v3_7d", "tests/test_v3_7f",
               # V3.7H guard-allowlist corrections to historical stage
               # guards (provenance-neutral; frozen science untouched).
               "tests/test_v3_6", "tests/test_v3_5", "tests/test_v3_4e",
               "scripts/v3_7d_", "scripts/v3_7f_",
    # V3.7H Tier-1 reclassification (freeze machinery;
    # frozen science untouched): allowed.
    "scripts/run_ci_tests.py",
    "scripts/run_ci_frontend_tests.py",
    "raceintel/counterfactual/",
               # V3.8H reconciliation: V3.8 charters explicitly supersede the
               # A stage-entry boundary. Admitted exactly (frozen science
               # untouched; any other path still fails): V3.8
               # research/evaluation/product artifacts, consensus science
               # package, D/E scripts, F API integration, G frontend,
               # H freeze, Tier-1 reclassification.
               "results/v3/v3_8", "docs/V3_8", "tests/test_v3_8",
               "scripts/v3_8", "scripts/run_ci_tests.py",
               "scripts/run_ci_frontend_tests.py",
               "raceintel/consensus/",
               "api/v2_consensus_",
               "frontend/app/consensus", "frontend/features/consensus",
               # V3.10I reconciliation (freeze): V3.10A-H charters
               # admitted exactly (pit-wall product, workspace
               # substrate, read-only telemetry API, stage
               # docs/artifacts/scripts/tests, and these
               # guard-allowlist edits themselves; frozen science
               # untouched; any other path still fails).
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
               "api/v2_telemetry_",
               "frontend/app/pit-wall/",
               "frontend/features/pit-wall/",
               "frontend/features/workspace/",
               "frontend/components/shell/AppShell.tsx",
               "frontend/features/counterfactuals/components/CounterfactualView.tsx",
               "frontend/features/strategy/components/Strategy2View.tsx",
               "frontend/lib/v2.ts",
               "frontend/features/replay/components/SpatialTrackPanel.tsx",
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
               # P2A carve-out (performance programme only): exactly the
               # two kernel files with hoisted loop-invariant overhead
               # (parity-gated in P0-P20/P1-P3/P2A-P29 checks, not here)
               # plus the performance-programme files (exact paths).
               "raceintel/simulation/mc2/kernel.py",
               "raceintel/simulation/mc2/residuals.py",
               "raceintel/simulation/mc2_batch.py",
               "scripts/mc2_batch_benchmark.py",
               "results/v3/performance_mc2/",
               "docs/MC2_PERFORMANCE_",
               "tests/test_perf_mc2_p0.py",
               "tests/test_mc2_batch_p1.py",
               "tests/test_mc2_p2a.py",
               # P2B carve-out (performance programme only): exact-order
               # heap queue tests (parity-gated by P2B-P1..P30, not here).
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
               # V3.9D carve-out (product UI stage only: /uncertainty
               # route, uncertainty feature modules, stage docs/artifacts;
               # no science change).
               "results/v3/v3_9d/",
               "docs/V3_9D",
               "frontend/app/uncertainty/",
               "frontend/features/uncertainty/",
               # V3.9E carve-out (freeze stage only: programme manifest,
               # parity records, final audits, freeze test + final doc;
               # no science change).
               "results/v3/v3_9e/",
               "docs/V3_9_UNCERTAINTY_INTELLIGENCE_FINAL.md",
               "tests/test_v3_9e_freeze.py",
               # Chartered C additive seam extension (the frozen V3.6B
               # guard independently records this trip; see C doc).
               "raceintel/simulation/monte_carlo.py",
               # Chartered F additive API integration.
               "api/v2_counterfactual_", "api/main.py",
               # Chartered G Counterfactual Explorer integration.
               "frontend/app/counterfactuals",
               "frontend/features/counterfactuals",
               "frontend/lib/v2.ts",
               "frontend/components/shell/CommandBar.tsx")
    for line in out.splitlines():
        if line.strip():
            # Porcelain XY prefix is not fixed-width after strip(); split.
            pth = line.split(None, 1)[-1]
            assert pth.startswith(allowed), line


# --- definition ---


def test_counterfactual_definition_frozen():
    d = _contract()["definition"]
    assert "SIMULATOR-CONDITIONAL" in d["counterfactual"]
    assert "FORBIDDEN" in d["historical_future"]
    assert "causal" in d["causal_boundary"].lower() or "T" in d["causal_boundary"]


def test_historical_future_forbidden():
    blob = json.dumps(_contract()["definition"]).lower()
    assert "forbidden" in blob
    assert any("truly have happened" in x
               for x in _contract()["definition"]["not_established"])


# --- classification ---


def test_classification_enum_exact():
    assert _contract()["classification_enum"] == [
        "SUPPORTED_NOW", "SUPPORTABLE_WITH_CAUSAL_EXTENSION",
        "RESEARCH_ONLY", "REJECT"]


def test_candidate_inventory_complete():
    cands = _contract()["candidates"]
    assert set(cands) == {
        "PIT_IN_N_LAPS", "MULTI_STOP_PLAN", "ALTERNATIVE_COMPOUND_PLAN",
        "UNDERCUT_OVERCUT_PRIMITIVE", "DRIVER_RETIREMENT", "SAFETY_CAR",
        "WEATHER", "TRACK_STATUS_RED_FLAG", "COMPETITOR_STRATEGY",
        "MULTI_DRIVER", "RACE_STATE_EDITS",
    }
    for name, cand in cands.items():
        assert cand["classification"] in _contract()["classification_enum"], name
        for key in ("reason", "required_mechanics", "required_data",
                    "temporal_safety_risk", "validation_requirement",
                    "v37_stage"):
            assert key in cand, (name, key)


def test_weather_classification_present():
    w = _contract()["candidates"]["WEATHER"]
    assert w["classification"] == "REJECT"
    assert "evolution" in w["reason"].lower()


def test_sc_classification_present():
    sc = _contract()["candidates"]["SAFETY_CAR"]
    assert sc["classification"] == "REJECT"
    assert "trigger" in sc["reason"].lower() or "compression" in sc["reason"].lower()


def test_multi_stop_classification_present():
    assert _contract()["candidates"]["MULTI_STOP_PLAN"]["classification"] == \
        "SUPPORTABLE_WITH_CAUSAL_EXTENSION"


def test_multi_driver_classification_present():
    assert _contract()["candidates"]["MULTI_DRIVER"]["classification"] == \
        "SUPPORTABLE_WITH_CAUSAL_EXTENSION"


# --- boundaries ---


def test_spatial_role_explicit():
    assert _contract()["spatial_role"] == "VISUALIZATION_CONTEXT_ONLY"


def test_v35_excluded():
    assert "outside" in _contract()["v35_boundary"].lower()


def test_v38_boundary_explicit():
    assert "V3.8" in _contract()["v38_boundary"]


def test_validation_limits_explicit():
    lim = _contract()["validation_limits"]
    assert "true_counterfactual_accuracy" in lim["impossible"]
    assert "determinism" in lim["possible"]


def test_architecture_decision_present():
    a = _contract()["architecture"]
    assert a["selected"] == "generic_schedule_above_MC2"
    assert len(a["options"]) == 3


def test_stage_plan_present():
    assert _contract()["stage_plan"][0] == "V3.7A"
    assert "V3.7H" in _contract()["stage_plan"]


# --- identity / landscape ---


def test_contract_hash_deterministic():
    c = _contract()
    identity = c.pop("contract_hash")
    blob = json.dumps(c, sort_keys=True, separators=(",", ":")).encode()
    assert identity == hashlib.sha256(blob).hexdigest()


def test_landscape_consistent():
    land = _load(LANDSCAPE)
    assert land["contract_hash"] == _load(CONTRACT)["contract_hash"]
    assert set(land["rejected_scope"]) >= {
        "SAFETY_CAR", "WEATHER", "DRIVER_RETIREMENT"}


def test_doc_required_sections():
    doc = DOC.read_text()
    for section in ("## Final verdict", "## Frozen parent",
                    "## Counterfactual definition", "## V3.6 boundary",
                    "## Candidate inventory", "## Safety Car",
                    "## Weather", "## Architecture decision",
                    "## V3.7 stage plan"):
        assert section in doc, section


# --- no frozen-tree modification ---


def test_no_v36_modification():
    # V3.7H reconciliation: the guard protects frozen V3.6 scientific
    # artifacts (results/docs/science). H's chartered guard-allowlist
    # corrections touch only historical *test* files, which are admitted
    # exactly; any results/docs/science v3_6 change still fails.
    out = _git("status", "--short")
    for line in out.splitlines():
        pth = line[3:] if len(line) > 3 else ""
        if pth.startswith(("tests/test_v3_6", "tests/test_v3_5")):
            continue
        assert "v3_6" not in pth and "V3_6" not in pth, line


def test_no_mc2_api_frontend_modification():
    # V3.7H reconciliation: C/F/G charters explicitly supersede the A
    # stage-entry assumption. Final-state invariant admits exactly the
    # chartered additive paths (seam hash-pinned); any other
    # MC2/API/frontend mutation still fails.
    # V3.8H reconciliation: V3.8F/V3.8G charters additionally admit
    # exactly the consensus API/frontend paths (frozen science untouched).
    # P2A carve-out (performance programme only): exactly the two kernel
    # files with hoisted overhead plus the additive batch executor
    # (parity-gated in P0-P20/P1-P3/P2A-P29 checks, not here).
    out = _git("status", "--short")
    allowed = ("raceintel/simulation/monte_carlo.py",
               "raceintel/simulation/mc2/kernel.py",
               "raceintel/simulation/mc2/residuals.py",
               "raceintel/simulation/mc2_batch.py",
               "api/v2_counterfactual_", "api/v2_consensus_", "api/main.py",
               # V3.9C carve-out: uncertainty bundle API (additive).
               "api/v2_uncertainty_",
               "frontend/app/counterfactuals",
               "frontend/features/counterfactuals",
               "frontend/app/consensus", "frontend/features/consensus",
               # V3.9D carve-out (product UI stage only: /uncertainty
               # route + uncertainty feature modules; no science change).
               "frontend/app/uncertainty/",
               "frontend/features/uncertainty/",
               "frontend/lib/v2.ts",
               "frontend/components/shell/CommandBar.tsx",
               # V3.10I reconciliation: V3.10A-H product admitted
               # exactly (pit-wall, workspace, shell, replay calm
               # prop, expert prefill, telemetry client/API; frozen
               # science untouched).
               "frontend/app/pit-wall/",
               "frontend/features/pit-wall/",
               "frontend/features/workspace/",
               "frontend/components/shell/AppShell.tsx",
               "frontend/features/strategy/components/Strategy2View.tsx",
               "frontend/features/replay/components/SpatialTrackPanel.tsx",
               "api/v2_telemetry_")
    for line in out.splitlines():
        pth = line[3:] if len(line) > 3 else ""
        if pth.startswith(("raceintel/simulation/", "api/", "frontend/")):
            assert pth.startswith(allowed), line
    if any("raceintel/simulation/monte_carlo.py" in ln for ln in
           out.splitlines()):
        import hashlib as _hl
        digest = _hl.sha256(
            (ROOT / "raceintel/simulation/monte_carlo.py").read_bytes()
        ).hexdigest()
        assert digest == ("045f392e46b030744f18a76140685ceba7501f80c0b8e265"
                          "af662e57ca5f5376")
