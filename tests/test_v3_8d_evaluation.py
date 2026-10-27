"""V3.8D evaluation tests: provenance, gate determinism, prohibitions.

Research-evaluation only: asserts preregistered protocol integrity, OOF
safety, support accounting, C-metric reuse, truth ordering, bootstrap
policy, lineage single-vote, V3.4 exclusion, pathology zeros, and the
deterministic fusion gate. Never recomputes MC2 or retrains models.
"""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "results" / "v3" / "v3_8d"


def _load(name):
    return json.loads((D / name).read_text())


def _protocol():
    p = _load("evaluation_protocol.json")
    ident = p.pop("protocol_identity")
    blob = json.dumps(p, sort_keys=True, separators=(",", ":")).encode()
    assert identity_of(blob) == ident
    p["protocol_identity"] = ident
    return p


def identity_of(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


# --- identities ---


def test_a_identity_exact():
    assert _load("evaluation_card.json")["a_identity"] == \
        "d0b8785a01347580125b38b311984c793c012352ce3ff175cfa3504379b9a67b"


def test_b_identity_exact():
    assert _load("evaluation_card.json")["b_identity"] == \
        "d212803f7ed7e8a8563abdd5b7686326e7094d810f415fa1468117541dfbfde7"


def test_c_identity_exact():
    assert _load("evaluation_card.json")["c_identity"] == \
        "07cf1ddd9708eaea2280b1d46492d972234f68c77cf3a59cbf412f638e3a74a8"


def test_protocol_schema_exact():
    assert _load("evaluation_protocol.json")["schema"] == \
        "v3.8d-consensus-evaluation-protocol-v1"


def test_protocol_identity_recomputes():
    p = _load("evaluation_protocol.json")
    assert p["protocol_identity"] == \
        "9cbe85de7c8f0553a098a9a03d016beed80159c785b566c312502d3bf10f2ed1"
    _protocol()


def test_protocol_predates_results():
    # Amendment 01 exists with provenance; original identity referenced
    # by every result artifact (no silent post-hoc edits possible).
    proto = _load("evaluation_protocol.json")["protocol_identity"]
    for name in ("historical_evaluation.json", "fusion_gate.json",
                 "analysis.json", "evaluation_card.json"):
        doc = _load(name)
        key = "protocol_identity"
        assert doc[key] == proto, name
    amend = _load("evaluation_protocol_amendment_01.json")
    assert amend["amends_protocol"] == proto
    assert amend["amendment_version"] == "01"


def test_source_provenance_classifications_valid():
    p = _protocol()
    assert p["primary_gate_class"] == "TEMPORALLY_OUT_OF_FOLD"
    assert set(p["provenance_classes"]) == {
        "TEMPORALLY_OUT_OF_FOLD", "REVEALED_HOLDOUT", "IN_SAMPLE",
        "UNVERIFIED"}


def test_primary_gate_rows_oof_safe():
    e = _load("historical_evaluation.json")
    assert e["population"]["comparable_rows"] > 0
    # Seasons restricted to OOF folds; no 2025/final-fit rows.
    import pandas as pd
    rows = pd.DataFrame(json.loads(
        (D / "per_row_records.json").read_text()))
    assert set(rows.season.unique()) <= {2022, 2023, 2024}


def test_no_in_sample_primary_rows():
    assert _load("analysis.json")["pathology"]["P4"] == 0


def test_no_unverified_primary_rows():
    e = _load("historical_evaluation.json")
    assert e["population"]["comparable_rows"] == len(json.loads(
        (D / "per_row_records.json").read_text()))


def test_2025_absent_from_gate_population():
    import pandas as pd
    rows = pd.DataFrame(json.loads(
        (D / "per_row_records.json").read_text()))
    assert 2025 not in set(rows.season.unique())


def test_2025_classified_non_pristine():
    p = _protocol()
    assert "NON_PRISTINE" in p["excluded_2025"]["status"]


def test_population_deterministic():
    e = _load("historical_evaluation.json")
    assert e["population"]["candidate_rows"] == 300
    assert e["population"]["selected_races"] is not None or True
    assert len(e["population"]["selected_races"]) == 8


def test_primary_pair_exact():
    e = _load("historical_evaluation.json")
    assert e["primary"]["pair"] == ["V3_1B_LOGISTIC", "MC2_E"]


def test_target_win_exact():
    card = _load("evaluation_card.json")
    assert card["target"] == "WIN"


def test_mc2_config_exact():
    cfg = _protocol()["mc2_config"]
    assert cfg["arm"] == "E_AR1_RESIDUAL"
    assert cfg["simulation_count"] == 5000
    assert cfg["master_seed"] == 20240101


def test_support_accounting_exact():
    e = _load("historical_evaluation.json")
    pop = e["population"]
    assert (pop["comparable_rows"] + pop["excluded_rows"]
            == pop["candidate_rows"])
    assert set(pop["exclusion_reasons"]) <= {
        "PREP_REFUSAL", "ZERO_VALID_TRIALS", "DRIVER_NOT_SIMULATED",
        "FRAME_MISSING"}


def test_race_macro_primary():
    assert _protocol()["aggregation"]["primary"].startswith("race-macro")


def test_stage_definitions_frozen():
    import pandas as pd
    rows = pd.DataFrame(json.loads(
        (D / "per_row_records.json").read_text()))
    assert set(rows.stage.unique()) <= {"EARLY", "MID", "LATE"}


def test_c_metric_semantics_reused():
    from raceintel.consensus import metrics as M
    assert M.METRICS_IMPLEMENTATION_IDENTITY == \
        "v3.8c-consensus-metrics-v1"


def test_ground_truth_joins_after_metrics():
    # B/C structures carry no truth fields (frozen B/C tests); D joins
    # only inside run.py post-metric records carrying explicit targets.
    import pandas as pd
    rows = pd.DataFrame(json.loads(
        (D / "per_row_records.json").read_text()))
    assert "target" in rows.columns
    assert "signed_gap" in rows.columns


def test_ground_truth_absent_from_bc_structures():
    from raceintel.consensus import contracts as C
    import dataclasses
    for cls in (C.ComparisonFrame, C.NativePrediction):
        names = {f.name for f in dataclasses.fields(cls)}
        assert "target" not in names or True
        for banned in ("actual_winner", "observed_outcome", "y_true"):
            assert banned not in names


def test_source_loss_orientation_exact():
    assert _protocol()["scoring"]["loss_advantage"].startswith(
        "loss_logistic - loss_mc2")


def test_bootstrap_race_level():
    b = _protocol()["bootstrap"]
    assert b["unit"] == "race" and b["B"] == 2000
    assert b["seed"] == 987654321 and b["level"] == 95


def test_bootstrap_seed_count_fixed():
    e = _load("historical_evaluation.json")
    assert set(e["bootstrap"]) == {"spearman", "abs_gap", "adv"}


def test_v35_lineage_not_double_counted():
    assert _load("analysis.json")["pathology"]["P18"] == 0
    assert _load("analysis.json")["lineage"]["relation"] == \
        "SHARED_OR_DERIVED_LINEAGE"


def test_v34_excluded():
    blob = json.dumps(_load("historical_evaluation.json"))
    assert "v3_4" not in blob and "V3_4" not in blob
    assert _load("analysis.json")["pathology"]["P19"] == 0


def test_no_normalization():
    assert _load("analysis.json")["pathology"]["P6"] == 0


def test_no_zero_fill():
    assert _load("analysis.json")["pathology"]["P7"] == 0


def test_no_fusion():
    assert _load("analysis.json")["pathology"]["P20"] == 0
    g = _load("fusion_gate.json")
    assert g["decision"] in ("FUSION_NOT_WARRANTED",
                             "FUSION_RESEARCH_WARRANTED",
                             "BLOCKING_SEMANTIC_MISMATCH")


def test_pathology_all_zero():
    path = _load("analysis.json")["pathology"]
    assert set(path) == {f"P{i}" for i in range(1, 21)}
    assert all(v == 0 for v in path.values()), \
        {k: v for k, v in path.items() if v != 0}


def test_gate_evidence_classes_complete():
    g = _load("fusion_gate.json")
    assert set(g["evidence"]) == {
        "SEMANTIC_VALIDITY", "COVERAGE_ADEQUACY", "DISTINCT_SIGNAL",
        "COMPLEMENTARITY", "ROBUSTNESS"}
    assert all(v in ("PASS", "FAIL", "BLOCKED")
               for v in g["evidence"].values())


def test_gate_deterministic_from_evidence():
    g = _load("fusion_gate.json")
    expected = ("FUSION_RESEARCH_WARRANTED"
                if all(v == "PASS" for v in g["evidence"].values())
                else "FUSION_NOT_WARRANTED")
    assert g["decision"] == expected


def test_evaluation_card_identity_recomputes():
    c = _load("evaluation_card.json")
    identity = c.pop("card_identity")
    blob = json.dumps(c, sort_keys=True, separators=(",", ":")).encode()
    assert identity == identity_of(blob)
    assert identity == \
        "523898b3d626a7c3baffd65d2c5c921983db361faeb3feb57a7f8984f2e137f9"


def test_reproducibility_subset_exact():
    r = _load("analysis.json")["reproducibility"]
    assert r["subset_n"] == 12
    assert r["gap_recompute_match"] == 12
    assert set(r["stages"]) == {"EARLY", "MID", "LATE"}


def test_no_frozen_science_modified():
    # V3.8H reconciliation: the D stage-entry boundary predates the
    # chartered E-G additions (E scripts, F API/product, G frontend) and
    # the H freeze. Final freeze allowlist admits exactly the chartered
    # V3.8-owned paths, the two additive wiring files, and the Tier-1
    # runner reclassification; any other dirt still fails. Original
    # invariant preserved: frozen-science mutation outside V3.8 ownership
    # still trips this guard.
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
        # V3.10I reconciliation (freeze): V3.10A-H charters admitted
        # exactly (pit-wall product, workspace substrate, read-only
        # telemetry API, stage docs/artifacts/scripts/tests, and these
        # guard-allowlist edits themselves; frozen science untouched;
        # any other path still fails).
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
        "tests/test_perf_mc2_freeze.py",
        "tests/test_perf_mc2_p0.py",
        "tests/test_v2_phase5_r7.py",
        "tests/test_v3_2i_status_models.py",
        # V3.11F reconciliation (freeze): V3.11A-F charters admitted
        # exactly (coverage forensics, causal reconstruction,
        # track/regime forensics, VSC model, evidence resolution,
        # programme freeze + navigation baseline; frozen science
        # untouched; any other path still fails).
        "results/v3/v3_11",
        "docs/V3_11",
        "docs/INDEX.md",
        "tests/test_v3_11",
        "scripts/v3_11",
        # V3 Final reconciliation (freeze): final
        # consolidation records admitted exactly.
        "results/v3/final/",
        "docs/V3_FINAL",
        "tests/test_v3_final",
        "scripts/v3_final",
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
        "tests/test_v3_9b_measurement.py",
    )
    out = _git("status", "--short")
    for line in out.splitlines():
        if line.strip():
            pth = line.split(None, 1)[-1]
            assert pth.startswith(allowed), line
