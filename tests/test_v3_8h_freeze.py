"""V3.8H freeze tests: reconciliation, full validation and freeze.

Final FREEZE / RELEASE stage for the V3.8 Model x Simulation Consensus
programme. No new science. Verifies the complete A->G provenance chain,
corrected D/E provenance, final architecture, source registry, probability
and support semantics, temporal safety, API/frontend audits, the H-P1..H-P30
pathology superset, and the freeze manifest / final card identities.

All worktree assertions are universal (every dirty path must be allowed),
so they hold both pre-commit (accumulated V3.8 tree) and post-commit
(clean tree). No corpus, no network, no MC2 execution.
"""

import hashlib
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D8 = ROOT / "results" / "v3"
MANIFEST = D8 / "v3_8h" / "freeze_manifest.json"
FINAL_CARD = D8 / "v3_8h" / "final_card.json"

A_CONTRACT = "d0b8785a01347580125b38b311984c793c012352ce3ff175cfa3504379b9a67b"
B_CONTRACT = "d212803f7ed7e8a8563abdd5b7686326e7094d810f415fa1468117541dfbfde7"
C_CONTRACT = "07cf1ddd9708eaea2280b1d46492d972234f68c77cf3a59cbf412f638e3a74a8"
D_PROTOCOL = "9cbe85de7c8f0553a098a9a03d016beed80159c785b566c312502d3bf10f2ed1"
D_CARD_ORIG = "523898b3d626a7c3baffd65d2c5c921983db361faeb3feb57a7f8984f2e137f9"
D_CARD_FIXED = "67f97c185ca8cc687b59b376bc5a48776e9290d6463a05653fa1a6e18a298985"
E_CARD_ORIG = "86d94ba7da69eb1e45aeb496a92c51d7519e70851253de043c53a332ff5f47ac"
E_CARD_FIXED = "ec6578de410f1ec8f6975e1cf4a2575aa4984967804b22a0b583fe2740948357"
E_PROTOCOL = "dbe6a565d5a6fa688dbb8e0b3a1be05bad71457777cd2e312f9c164219b128dd"
F_CARD = "0086785cafe4298dafe171e9a7b6c0fd099d4636151568b3a6c4f7ed1f1f2a45"
G_CARD = "7c2313fc36e98f58a3f8fd7b3dd328d16fa5f0c3245403c2c80e970785a45391"

# Final V3.8 freeze allowlist (V3.8H reconciliation). Admits exactly the
# chartered V3.8-owned paths, the two additive wiring files, and the Tier-1
# runner reclassification. Any other dirt still fails.
FINAL_ALLOW = (
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
    # V3.8H Tier-1-driven historical-guard reconciliations (exact files).
    "tests/test_v3_5a_contract.py", "tests/test_v3_5b_dataset.py",
    "tests/test_v3_5c_harness.py", "tests/test_v3_5d_screening.py",
    "tests/test_v3_6a_contract.py", "tests/test_v3_6b_contracts.py",
    "tests/test_v3_6d_evaluation.py", "tests/test_v3_6f_runtime.py",
    "tests/test_v3_6h_freeze.py", "tests/test_v3_7a_contract.py",
    # P2A carve-out (performance programme only): exactly the two kernel
    # files with hoisted loop-invariant overhead (parity-gated in
    # P0-P20/P1-P3/P2A-P29 checks, not here).
    "raceintel/simulation/mc2/kernel.py",
    "raceintel/simulation/mc2/residuals.py",
    # P2A performance-programme files (exact paths/prefixes).
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
    "scripts/run_ci_tests.py",
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
               # V3.11A reconciliation (forensics): offline diagnostic stage
               # only (coverage forensics script/tests/artifacts + CI count
               # pin; frozen science untouched; any other path still fails).
               "results/v3/v3_11a/",
               "docs/V3_11A",
               "scripts/v3_11a",
               "tests/test_v3_11a",
               # V3.11B reconciliation (causal reconstruction validation):
               # offline rule-validation stage only (registry/protocol/
               # analysis scripts + focused tests + artifacts + CI count
               # pin; zero production implementation; frozen science
               # untouched; any other path still fails).
               "results/v3/v3_11b/",
               "docs/V3_11B",
               "scripts/v3_11b",
               "tests/test_v3_11b",
               # V3.11C reconciliation (track-source/regime forensics):
               # offline research stage only (source/regime/ledger
               # scripts + focused tests + artifacts + CI count pin;
               # zero production implementation; frozen science
               # untouched; any other path still fails).
               "results/v3/v3_11c/",
               "docs/V3_11C",
               "scripts/v3_11c",
               "tests/test_v3_11c",
               # V3.11D reconciliation (VSC regime model research):
               # isolated research model + validation stage only
               # (episode/analysis/protocol/model/validation scripts +
               # focused tests + artifacts + CI count pin; zero
               # production implementation; frozen science untouched;
               # any other path still fails).
               "results/v3/v3_11d/",
               "docs/V3_11D",
               "scripts/v3_11d",
               "tests/test_v3_11d",
               # V3.11E reconciliation (VSC evidence resolution):
               # offline evidence stage only (protocol/duration/evidence/
               # validation scripts + focused tests + artifacts + CI
               # count pin; zero production implementation; frozen
               # science untouched; any other path still fails).
               "results/v3/v3_11e/",
               "docs/V3_11E",
               "scripts/v3_11e",
               "tests/test_v3_11e",
               # Architecture navigation baseline (docs-only, pre-E):
               # domain index + scripts forward rule; navigation
               # artifacts only; zero production implementation;
               # frozen science untouched; any other path still fails.
               "docs/INDEX.md",
               "scripts/README.md",
               # V3.11F reconciliation (programme freeze):
               # freeze script + final card/results + synthesis doc +
               # focused freeze tests + CI count pin; zero production
               # implementation; frozen science untouched; any other
               # path still fails.
               "results/v3/v3_11_final/",
               "docs/V3_11_MC2_COVERAGE_EXPANSION_FINAL.md",
               "scripts/v3_11f",
               "tests/test_v3_11f",
               # V3 Final reconciliation (freeze): final
               # consolidation records admitted exactly (tag
               # registry/manifests/claim registry/synthesis +
               # focused freeze tests; frozen science untouched;
               # any other path still fails).
               "results/v3/final/",
               "docs/V3_FINAL",
               "scripts/v3_final",
               "tests/test_v3_final",
)
# Tracked files H is permitted to show as modified pre-commit.
TRACKED_ALLOW = {
    "api/main.py",
    "frontend/components/shell/CommandBar.tsx",
    "tests/test_v3_8a_consensus_contract.py",
    "tests/test_v3_8b_source_adapters.py",
    "tests/test_v3_8c_consensus_metrics.py",
    "tests/test_v3_8d_evaluation.py",
    "scripts/run_ci_tests.py",
    "scripts/run_ci_frontend_tests.py",
    # V3.9A carve-out: freeze pin/pathology reconciliation (no science).
    "tests/test_perf_mc2_freeze.py",
    "tests/test_perf_mc2_p0.py",
    "tests/test_mc2_p2a.py",
    # V3.9C carve-out: uncertainty router registration (2 lines, additive).
    "api/main.py",
    # V3.8H Tier-1-driven historical-guard reconciliations (exact files).
    "tests/test_v3_5a_contract.py",
    "tests/test_v3_5b_dataset.py",
    "tests/test_v3_5c_harness.py",
    "tests/test_v3_5d_screening.py",
    "tests/test_v3_6a_contract.py",
    "tests/test_v3_6b_contracts.py",
    "tests/test_v3_6d_evaluation.py",
    "tests/test_v3_6f_runtime.py",
    "tests/test_v3_6h_freeze.py",
    "tests/test_v3_7a_contract.py",
    # P2A carve-out (performance programme only): exactly the two kernel
    # files with hoisted loop-invariant overhead (parity-gated in
    # P0-P20/P1-P3/P2A-P29 checks, not here).
    "raceintel/simulation/mc2/kernel.py",
    "raceintel/simulation/mc2/residuals.py",
    # P2A guard carve-outs themselves (tracked V3.8 test files edited to
    # admit exactly the P2A set; frozen manifest untouched).
    "tests/test_v3_8d_correction_01.py",
    "tests/test_v3_8h_freeze.py",
    # P2A historical-guard carve-outs (exact files).
    "tests/test_v3_6a_contract.py",
    "tests/test_v3_6b_contracts.py",
    "tests/test_v3_6d_evaluation.py",
    "tests/test_v3_7a_contract.py",
    # V3.10I reconciliation (freeze): exact V3.10 tracked
    # modifications (7 product files: shell, replay calm prop,
    # expert prefill x2, telemetry client/router; frozen science
    # untouched).
    "frontend/components/shell/AppShell.tsx",
    "frontend/features/counterfactuals/components/CounterfactualView.tsx",
    "frontend/features/replay/components/SpatialTrackPanel.tsx",
    "frontend/features/strategy/components/Strategy2View.tsx",
    "frontend/lib/v2.ts",
    # V3.10I reconciliation (freeze): exact V3.10 guard-allowlist
    # edits themselves (provenance-neutral; frozen science untouched).
    # (test_v3_6a/6b/6d/7a already listed above.)
    "tests/test_v3_6f_runtime.py",
    "tests/test_v3_8h_freeze.py",
    "tests/test_v3_9a_contract.py",
    "tests/test_v3_9b_measurement.py",
    "tests/test_v3_9c_bundle.py",
    "tests/test_v3_9e_freeze.py",
    "tests/test_perf_mc2_freeze.py",
    "scripts/run_ci_tests.py",
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
    # V3.11F reconciliation (freeze): narrow stale-guard repair of the
    # time-bound V3.9 HEAD pin (tag pin kept; ancestry asserted with
    # equal strength; frozen science untouched).
    "tests/test_v3_10b_workspace_ownership.py",
    # V3 Final reconciliation (freeze): navigation docs are tracked
    # since the V3.11 freeze; terminal-status lines only (docs-only;
    # frozen science untouched).
    "docs/INDEX.md",
    "scripts/README.md",
}


def _load(path):
    return json.loads(Path(path).read_text())


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _git_status():
    out = subprocess.run(["git", "status", "--short"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return out.splitlines()


def _v38_files(stage):
    return [p for p in _load(MANIFEST)["ownership_manifest"]
            if p.startswith(f"results/v3/v3_8{stage}/")]


# --- provenance chain ---


def test_provenance_a_b_c_identities():
    assert _load(D8 / "v3_8a" / "consensus_contract.json")[
        "contract_identity"] == A_CONTRACT
    assert _load(D8 / "v3_8b" / "alignment_contract.json")[
        "contract_identity"] == B_CONTRACT
    assert _load(D8 / "v3_8c" / "metrics_contract.json")[
        "contract_identity"] == C_CONTRACT


def test_provenance_d_original_and_protocol():
    card = _load(D8 / "v3_8d" / "evaluation_card.json")
    assert card["card_identity"] == D_CARD_ORIG
    assert card["protocol_identity"] == D_PROTOCOL
    proto = _load(D8 / "v3_8d" / "evaluation_protocol.json")
    ident = proto.pop("protocol_identity")
    assert hashlib.sha256(_canon(proto)).hexdigest() == ident == D_PROTOCOL


def test_provenance_d_corrected_identity_recomputes():
    card = _load(D8 / "v3_8d" / "evaluation_card_correction_01.json")
    ident = card.pop("card_identity")
    assert hashlib.sha256(_canon(card)).hexdigest() == ident == D_CARD_FIXED
    corr = _load(D8 / "v3_8d" / "correction_01.json")
    assert corr["corrected_d_card_identity"] == D_CARD_FIXED
    assert corr["original_d_card_identity"] == D_CARD_ORIG


def test_provenance_e_corrected_identity_recomputes():
    card = _load(D8 / "v3_8e" / "fusion_card.json")
    ident = card.pop("card_identity")
    assert hashlib.sha256(_canon(card)).hexdigest() == ident == E_CARD_FIXED
    assert card["d_card_identity"] == D_CARD_FIXED
    assert card["d_protocol_identity"] == D_PROTOCOL
    assert card["e_protocol_identity"] == E_PROTOCOL
    corr = _load(D8 / "v3_8d" / "correction_01.json")
    assert corr["e_status"]["e_card_new"] == E_CARD_FIXED
    assert corr["e_status"]["e_card_old"] == E_CARD_ORIG


def test_provenance_f_g_identities():
    assert _load(D8 / "v3_8f" / "product_card.json")[
        "card_identity"] == F_CARD
    assert _load(D8 / "v3_8g" / "ui_card.json")["card_identity"] == G_CARD


# --- corrected D selection / supersession ---


def test_corrected_d_gate():
    card = _load(D8 / "v3_8d" / "evaluation_card_correction_01.json")
    assert card["fusion_gate"] == "FUSION_RESEARCH_WARRANTED"
    assert _load(D8 / "v3_8d" / "correction_01.json")[
        "corrected_d_gate"] == "FUSION_RESEARCH_WARRANTED"


def test_corrected_d_bootstrap_authoritative():
    card = _load(D8 / "v3_8d" / "evaluation_card_correction_01.json")
    u = card["corrected_uncertainty"]
    assert u["race_macro_advantage"] == -0.23278201903984877
    assert u["bootstrap_mean"] == -0.23183645937178618
    assert u["bootstrap_ci95"] == [-0.675070800341179,
                                  -0.0038341926858394522]
    assert card["bootstrap_policy"] == {"B": 2000, "level": 95,
                                       "seed": 987654321, "unit": "race"}
    assert card["findings"]["log_better_races"] == 7
    assert card["findings"]["mc2_better_races"] == 1


def test_superseded_d_statistic_never_authoritative():
    corr = _load(D8 / "v3_8d" / "correction_01.json")
    old = corr["affected_fields"]["bootstrap.adv"]["old"]
    assert old["mark"] == "SUPERSEDED_ROW_POOLED_BOOTSTRAP"
    assert old["mean"] == -0.15065782073566983
    assert old["ci95"] == [-0.5367011220527186, -0.0007417371736964612]
    new = corr["affected_fields"]["bootstrap.adv"]["new"]
    assert new["mark"] == "CORRECTED_RACE_LEVEL"
    assert old["mean"] != new["mean"]
    assert old["ci95"] != new["ci95"]
    # The superseded row-pooled values appear nowhere as a corrected result.
    fixed = _load(D8 / "v3_8d" / "evaluation_card_correction_01.json")
    blob = json.dumps(fixed)
    assert "SUPERSEDED_ROW_POOLED_BOOTSTRAP" not in blob
    assert fixed["corrected_uncertainty"]["bootstrap_mean"] != old["mean"]
    assert corr["confirmations"]["prediction_changes"] == 0
    assert corr["confirmations"]["population_changes"] == 0
    assert corr["confirmations"]["mc2_reruns"] == 0


# --- E negative fusion result ---


def test_corrected_e_gate_and_numbers():
    card = _load(D8 / "v3_8e" / "fusion_card.json")
    assert card["gate"] == "FUSION_IMPROVEMENT_NOT_SUPPORTED"
    ev = _load(D8 / "v3_8e" / "fusion_evaluation.json")
    assert ev["fusion"]["macro_ll"] == 0.03853232288952204
    assert ev["controls"]["macro_ll_log"] == 0.03565684961000868
    assert ev["controls"]["macro_ll_mc2"] == 0.39255774435602214
    assert ev["deltas"]["delta_fusion_vs_log_macro_ll"] == 0.0028754732795133603
    assert ev["deltas"]["delta_fusion_vs_mc2_macro_ll"] == -0.3540254214665001
    assert card["alpha_grid"][-1] == 1.0


# --- source registry / runtime composition ---


def test_final_source_registry_exact():
    from raceintel.consensus import product as P
    from raceintel.consensus import contracts as C
    assert P.PRODUCT_SOURCES == (C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E)
    assert P.PRODUCT_TARGET == C.Target.WIN
    assert set(P.PRODUCT_EXCLUDED_SEASONS) == {2025}


def test_no_v34_no_v35_vote_in_runtime():
    from raceintel.consensus import product as P
    blob = open(P.__file__).read()
    assert "v3_4" not in blob.lower()
    assert "V3_4" not in blob
    assert "V3_5" not in blob
    assert "P_win" not in blob
    assert "ensemble" not in blob.lower()


def _runtime_blobs():
    from raceintel.consensus import product as P
    import api.v2_consensus_routes as R
    import api.v2_consensus_schemas as S
    import api.v2_consensus_service as V
    return [open(P.__file__).read(), open(R.__file__).read(),
            open(S.__file__).read(), open(V.__file__).read()]


def test_no_fusion_runtime():
    for blob in _runtime_blobs():
        for token in ("combined_probability",
                      "consensus_probability", "consensus_score",
                      "confidence_score", "preferred_source",
                      "winning_source", "source_winner",
                      "weighted_average"):
            assert token not in blob, token
        # Word-boundary: "refused" (typed-refusal contract) must not trip
        # a "fused" ban; standalone blend/ensemble must be absent.
        for word in ("fused", "blend", "ensemble"):
            assert re.search(r"\b" + word + r"\b", blob) is None, word


def test_no_source_winner_policy():
    for blob in _runtime_blobs():
        for token in ("preferred_source", "winning_source",
                      "source_winner", "recommended_source"):
            assert token not in blob, token


def test_probability_family_semantics():
    from raceintel.consensus import product as P
    out = P.compose(race_id="2022-r03-R", lap_number=2, state_time_s=None,
                    stage="EARLY", season=2022,
                    model_probs={"a": 0.9, "b": 0.8},
                    simulation_probs={"a": 0.5, "b": 0.5},
                    valid_trials={"a": 5000, "b": 5000})
    assert out["model"]["probability_family"] == "INDEPENDENT_BINARY"
    assert out["simulation"]["probability_family"] == \
        "MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY"
    # Raw natives pass through verbatim: Logistic never race-normalized,
    # MC2 never renormalized.
    got_m = {d["driver_id"]: d["p_model"]
             for d in out["disagreement"]["drivers"]}
    got_s = {d["driver_id"]: d["p_simulation"]
             for d in out["disagreement"]["drivers"]}
    assert got_m == {"a": 0.9, "b": 0.8}
    assert got_s == {"a": 0.5, "b": 0.5}


def test_signed_gap_semantics():
    from raceintel.consensus import metrics as M
    from raceintel.consensus import product as P
    assert M.signed_gap(0.2, 0.5) == 0.3
    assert P.SIGNED_GAP_DEFINITION == "simulation_minus_model"
    out = P.compose(race_id="2022-r03-R", lap_number=2, state_time_s=None,
                    stage="EARLY", season=2022,
                    model_probs={"a": 0.2, "b": 0.8},
                    simulation_probs={"a": 0.5, "b": 0.5},
                    valid_trials={"a": 5000, "b": 5000})
    gaps = {d["driver_id"]: d["signed_gap"]
            for d in out["disagreement"]["drivers"]}
    assert gaps["a"] == M.signed_gap(0.2, 0.5) == 0.3
    assert abs(gaps["b"] - (-0.3)) < 1e-12
    assert out["disagreement"]["signed_gap_definition"] == \
        "simulation_minus_model"


def test_rank_displacement_semantics():
    from raceintel.consensus import metrics as M
    assert M.rank_displacement(1, 3) == 2
    assert M.rank_displacement(3, 1) == -2


def test_zero_vs_missing_distinction():
    from raceintel.consensus import product as P
    from raceintel.consensus import contracts as C
    # Legitimate supported MC2 zero stays numeric 0.0.
    out = P.compose(race_id="2022-r03-R", lap_number=2, state_time_s=None,
                    stage="EARLY", season=2022,
                    model_probs={"a": 0.4, "b": 0.6},
                    simulation_probs={"a": 0.0, "b": 1.0},
                    valid_trials={"a": 5000, "b": 5000})
    sim = {d["driver_id"]: d["p_simulation"]
           for d in out["disagreement"]["drivers"]}
    assert sim["a"] == 0.0 and isinstance(sim["a"], float)
    # Unsupported/missing is UNAVAILABLE, never 0.0.
    av = P.assess_availability(
        season=2022, model_status=C.SupportStatus.AVAILABLE,
        simulation_status=C.SupportStatus.UNAVAILABLE,
        simulation_reason=C.ReasonCode.SOURCE_NOT_AVAILABLE)
    assert av["simulation"] == "UNAVAILABLE"
    assert av["comparison"] == "NOT_COMPARABLE"


def test_2025_exclusion():
    from raceintel.consensus import product as P
    from raceintel.consensus import contracts as C
    av = P.assess_availability(
        season=2025, model_status=C.SupportStatus.AVAILABLE,
        simulation_status=C.SupportStatus.AVAILABLE)
    assert av["model"] == "UNAVAILABLE"
    assert av["simulation"] == "UNAVAILABLE"
    assert av["comparison"] == "NOT_COMPARABLE"
    try:
        P.compose(race_id="2025-r01-R", lap_number=1, state_time_s=None,
                  stage="EARLY", season=2025,
                  model_probs={"a": 0.5}, simulation_probs={"a": 0.5},
                  valid_trials={"a": 5000})
    except ValueError:
        pass
    else:
        raise AssertionError("2025 compose must refuse")


def test_temporal_boundary_blacklist():
    contract = _load(D8 / "v3_8a" / "consensus_contract.json")
    black = contract["temporal_poison_blacklist"]
    for item in ("future lap time", "future position", "future pit",
                 "future retirement", "future finish", "winner label"):
        assert item in black, item
    for blob in _runtime_blobs():
        for token in ("actual_winner", "observed_outcome", "y_true",
                      "winner_driver_id", "ground_truth"):
            assert token not in blob, token


def test_api_science_controls_prohibited():
    import api.v2_consensus_routes as R
    import api.v2_consensus_schemas as S
    routes = open(R.__file__).read()
    schemas = open(S.__file__).read()
    assert routes.count("Query(") == 3
    for token in ("seed=", "master_seed", "simulation_count",
                  "n_trials", "n_futures", "fusion_alpha",
                  "blend_weight", "weight="):
        assert token not in routes, token
        assert token not in schemas, token


def test_frontend_research_artifact_isolation():
    base = ROOT / "frontend" / "features" / "consensus"
    app = ROOT / "frontend" / "app" / "consensus"
    files = [p for p in list(base.rglob("*.ts")) + list(base.rglob("*.tsx"))
             + list(app.rglob("*.tsx")) if ".test." not in p.name]
    assert files, "consensus frontend sources missing"
    for path in files:
        text = path.read_text()
        for token in ("results/v3", "scripts/v3", ".parquet", ".pkl",
                      "joblib", "from \"raceintel", "from 'raceintel",
                      "require(\"raceintel", "require('raceintel"):
            assert token not in text, (path.name, token)


def test_no_fusion_ui():
    base = ROOT / "frontend" / "features" / "consensus"
    app = ROOT / "frontend" / "app" / "consensus"
    texts = [p.read_text() for p in list(base.rglob("*.ts"))
             + list(base.rglob("*.tsx")) + list(app.rglob("*.tsx"))
             if ".test." not in p.name]
    blob = "\n".join(texts)
    for token in ("combined_probability", "consensus_score",
                  "confidence_score", "preferred_source", "winning_source",
                  "source_winner", "weighted_average", "Slider",
                  "type=\"range\"", "recommendation", "consensusProbability"):
        assert token not in blob, token
    assert re.search(r"\bfused\b", blob) is None
    # "blend" may appear ONLY inside the researched-but-rejected disclosure
    # copy ("instead of a blended probability"); never as a control/value.
    for match in re.finditer("blend", blob):
        context = blob[max(0, match.start() - 60):match.end() + 60]
        assert "instead of a blended probability" in context, context
    # The researched-but-rejected fusion outcome stays disclosed as copy.
    assert "instead of a blended probability" in blob


def test_demo_state_disclosure():
    view = (ROOT / "frontend" / "features" / "consensus" / "components"
            / "ConsensusView.tsx").read_text()
    assert "Historical replay" in view
    assert "Illustrative supported state" in view
    assert "not typical of all races" in view


# --- manifest / card / ownership ---


def test_freeze_manifest_completeness():
    manifest = _load(MANIFEST)
    assert manifest["schema"] == "v3.8h-freeze-manifest-v1"
    assert manifest["frozen_parent"] == {
        "commit": "30fe18908a41d95113c189274598269a95ef44ca",
        "tag": "v3.7-counterfactual-engine"}
    assert manifest["runtime_sources"] == ["V3_1B_LOGISTIC", "MC2_E"]
    assert set(manifest["stages"]) == {"A", "B", "C", "D", "D_correction_01",
                                       "E", "F", "G", "H"}
    assert manifest["stages"]["D"]["gate"] == "FUSION_RESEARCH_WARRANTED"
    assert manifest["stages"]["D_correction_01"]["gate"] == \
        "FUSION_RESEARCH_WARRANTED"
    assert manifest["stages"]["E"]["gate"] == \
        "FUSION_IMPROVEMENT_NOT_SUPPORTED"
    for path in manifest["ownership_manifest"]:
        assert (ROOT / path).exists(), path
    assert manifest["reconciled_historical_guards"] == [
        "tests/test_v3_5a_contract.py",
        "tests/test_v3_5b_dataset.py",
        "tests/test_v3_5c_harness.py",
        "tests/test_v3_5d_screening.py",
        "tests/test_v3_6a_contract.py",
        "tests/test_v3_6b_contracts.py",
        "tests/test_v3_6d_evaluation.py",
        "tests/test_v3_6f_runtime.py",
        "tests/test_v3_6h_freeze.py",
        "tests/test_v3_7a_contract.py",
    ]
    for path in manifest["reconciled_historical_guards"]:
        assert (ROOT / path).exists(), path
        assert "V3.8H reconciliation" in (ROOT / path).read_text(), path
    union = set()
    for stage in manifest["stages"].values():
        union.update(stage["owned_files"])
    assert union == set(manifest["ownership_manifest"])


def test_manifest_identity_recomputes():
    manifest = _load(MANIFEST)
    ident = manifest.pop("manifest_identity")
    assert hashlib.sha256(_canon(manifest)).hexdigest() == ident


def test_final_card_identity_recomputes():
    card = _load(FINAL_CARD)
    ident = card.pop("card_identity")
    assert hashlib.sha256(_canon(card)).hexdigest() == ident
    assert card["provenance_chain"]["a_contract_identity"] == A_CONTRACT
    assert card["provenance_chain"]["d_card_corrected"] == D_CARD_FIXED
    assert card["provenance_chain"]["e_card_corrected"] == E_CARD_FIXED
    assert card["provenance_chain"]["f_card"] == F_CARD
    assert card["provenance_chain"]["g_card"] == G_CARD
    assert card["product_decision"].startswith(
        "preserve Model and Simulation as separate mechanisms")


def test_no_unknown_v38_owned_files():
    manifest = _load(MANIFEST)
    owned = set(manifest["ownership_manifest"])
    walked = set()
    for owned_dir in ("results/v3/v3_8a", "results/v3/v3_8b",
                      "results/v3/v3_8c", "results/v3/v3_8d",
                      "results/v3/v3_8e", "results/v3/v3_8f",
                      "results/v3/v3_8g", "results/v3/v3_8h",
                      "raceintel/consensus", "frontend/app/consensus",
                      "frontend/features/consensus"):
        base = ROOT / owned_dir
        for path in base.rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts \
                    and not path.name.endswith(".pyc"):
                walked.add(str(path.relative_to(ROOT)))
    assert walked - owned == set()


def test_stage_ownership_attribution():
    manifest = _load(MANIFEST)
    for stage_name, stage in manifest["stages"].items():
        assert stage["owned_files"], stage_name
        assert stage["verdict"], stage_name
        for path in stage["owned_files"]:
            assert (ROOT / path).exists(), (stage_name, path)


def test_guard_reconciliation_landed():
    v38 = ("tests/test_v3_8a_consensus_contract.py",
           "tests/test_v3_8b_source_adapters.py",
           "tests/test_v3_8c_consensus_metrics.py",
           "tests/test_v3_8d_evaluation.py")
    for rel in v38:
        text = (ROOT / rel).read_text()
        assert "V3.8H reconciliation" in text, rel
        assert "frontend/app/consensus" in text, rel
        assert "api/main.py" in text, rel
        assert "assert pth.startswith" in text, rel
    historical = ("tests/test_v3_5a_contract.py",
                  "tests/test_v3_5b_dataset.py",
                  "tests/test_v3_5c_harness.py",
                  "tests/test_v3_5d_screening.py",
                  "tests/test_v3_6a_contract.py",
                  "tests/test_v3_6b_contracts.py",
                  "tests/test_v3_6d_evaluation.py",
                  "tests/test_v3_6f_runtime.py",
                  "tests/test_v3_6h_freeze.py",
                  "tests/test_v3_7a_contract.py")
    for rel in historical:
        text = (ROOT / rel).read_text()
        assert "V3.8H reconciliation" in text, rel
        assert "api/v2_consensus_" in text \
            or "frontend/app/consensus" in text \
            or "merge-base" in text, rel
    # Frozen-ancestor invariant survives the freeze commit.
    text = (ROOT / "tests/test_v3_8a_consensus_contract.py").read_text()
    assert "merge-base" in text and "--is-ancestor" in text
    # Additive wiring present exactly once each.
    main = (ROOT / "api" / "main.py").read_text()
    assert main.count("v2_consensus_router") == 2
    cmd = (ROOT / "frontend" / "components" / "shell"
           / "CommandBar.tsx").read_text()
    assert cmd.count('href: "/consensus"') == 1


def test_worktree_contains_only_owned_v38_paths():
    for line in _git_status():
        if line.strip():
            pth = line.split(None, 1)[-1].strip().strip('"')
            assert pth.startswith(FINAL_ALLOW), line
    modified = [ln.split()[-1].strip().strip('"')
                for ln in _git_status()
                if ln.startswith(("M ", " M"))]
    assert set(modified) <= TRACKED_ALLOW, modified
    # The freeze manifest names every intentional tracked modification.
    # P2A carve-out (performance programme only, manifest untouched):
    # exactly the two kernel files, admitted only when P2A parity is EXACT.
    manifest = _load(MANIFEST)
    intended = {e["path"]
                for e in manifest["intentional_worktree_changes"]}
    p2a_pair = {"raceintel/simulation/mc2/kernel.py",
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
                "tests/test_v3_7a_contract.py",
                # V3.9A carve-out: freeze pin/pathology reconciliation.
                "tests/test_perf_mc2_freeze.py",
                "tests/test_perf_mc2_p0.py",
                "tests/test_mc2_p2a.py",
                # V3.9C carve-out: uncertainty router registration.
                "api/main.py"}
    # V3.10I reconciliation (freeze): exact V3.10 tracked
    # modifications admitted alongside P2A (ownership manifest
    # results/v3/v3_10i/v3_10_ownership_manifest.json inventories
    # every path; frozen science untouched).
    v10_tracked = {"api/main.py",
                   "frontend/components/shell/AppShell.tsx",
                   "frontend/components/shell/CommandBar.tsx",
                   "frontend/features/counterfactuals/components/CounterfactualView.tsx",
                   "frontend/features/replay/components/SpatialTrackPanel.tsx",
                   "frontend/features/strategy/components/Strategy2View.tsx",
                   "frontend/lib/v2.ts",
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
                   "scripts/run_ci_tests.py",
                   # V3.10I wave-2 reconciliations below (exact guard
                   # files admitting the V3.10 set; frozen science
                   # untouched).
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
                   # V3.11F reconciliation (freeze): narrow stale-guard
                   # repair of the time-bound V3.9 HEAD pin (tag pin
                   # kept; ancestry asserted with equal strength).
                   "tests/test_v3_10b_workspace_ownership.py",
                   # V3 Final reconciliation (freeze): navigation
                   # docs terminal-status lines only (docs-only).
                   "docs/INDEX.md",
                   "scripts/README.md",}
    p2a_ok = _load(
        ROOT / "results" / "v3" / "performance_mc2" / "p2a"
        / "parity_results.json")["overall"] == "EXACT" \
        if (ROOT / "results" / "v3" / "performance_mc2" / "p2a"
            / "parity_results.json").is_file() else False
    extra = set(modified) - intended
    assert extra <= ((p2a_pair | v10_tracked) if p2a_ok else v10_tracked), extra
    assert intended <= TRACKED_ALLOW, intended - TRACKED_ALLOW


# --- H-P1..H-P30 pathology superset: all zero ---


def _h_pathology_counts():
    from raceintel.consensus import product as P
    from raceintel.consensus import metrics as M
    from raceintel.consensus import contracts as C
    counts = {}
    runtime = "\n".join(_runtime_blobs())
    fe_base = ROOT / "frontend" / "features" / "consensus"
    fe_app = ROOT / "frontend" / "app" / "consensus"
    fe_files = [p for p in list(fe_base.rglob("*.ts"))
                + list(fe_base.rglob("*.tsx")) + list(fe_app.rglob("*.tsx"))
                if ".test." not in p.name]
    fe = "\n".join(p.read_text() for p in fe_files)
    truth_tokens = ("actual_winner", "observed_outcome", "y_true",
                    "winner_driver_id", "ground_truth")
    counts["H-P1"] = sum(1 for t in truth_tokens if t in runtime)
    counts["H-P2"] = len(re.findall(r"FINAL_FIT", runtime + fe))
    av25 = P.assess_availability(
        season=2025, model_status=C.SupportStatus.AVAILABLE,
        simulation_status=C.SupportStatus.AVAILABLE)
    counts["H-P3"] = 0 if (av25["comparison"] == "NOT_COMPARABLE"
                           and av25["model"] == "UNAVAILABLE") else 1
    out = P.compose(race_id="2022-r03-R", lap_number=2, state_time_s=None,
                    stage="EARLY", season=2022,
                    model_probs={"a": 0.9, "b": 0.8},
                    simulation_probs={"a": 0.3, "b": 0.4},
                    valid_trials={"a": 5000, "b": 5000})
    got_m = {d["driver_id"]: d["p_model"]
             for d in out["disagreement"]["drivers"]}
    got_s = {d["driver_id"]: d["p_simulation"]
             for d in out["disagreement"]["drivers"]}
    counts["H-P4"] = 0 if got_m == {"a": 0.9, "b": 0.8} else 1
    counts["H-P5"] = 0 if got_s == {"a": 0.3, "b": 0.4} else 1
    counts["H-P6"] = 0 if av25["simulation"] == "UNAVAILABLE" else 1
    zero_out = P.compose(
        race_id="2022-r03-R", lap_number=2, state_time_s=None,
        stage="EARLY", season=2022, model_probs={"a": 0.4, "b": 0.6},
        simulation_probs={"a": 0.0, "b": 1.0},
        valid_trials={"a": 5000, "b": 5000})
    zero_sim = {d["driver_id"]: d["p_simulation"]
                for d in zero_out["disagreement"]["drivers"]}
    counts["H-P7"] = 0 if zero_sim["a"] == 0.0 else 1
    counts["H-P8"] = 0 if {"model_reason", "simulation_reason"} <= set(
        P.assess_availability(
            season=2022, model_status=C.SupportStatus.AVAILABLE,
            simulation_status=C.SupportStatus.UNAVAILABLE,
            simulation_reason=C.ReasonCode.SOURCE_NOT_AVAILABLE)) else 1
    counts["H-P9"] = 0 if "IDENTITY_MISMATCH" in runtime else 1
    counts["H-P10"] = sum(1 for t in ("V3_5", "P_win") if t in runtime)
    counts["H-P11"] = sum(1 for t in ("v3_4", "V3_4") if t in runtime)
    fusion_tokens = ("combined_probability",
                     "consensus_probability", "consensus_score",
                     "confidence_score", "preferred_source",
                     "winning_source", "weighted_average")
    counts["H-P12"] = sum(1 for t in fusion_tokens if t in runtime)
    counts["H-P12"] += sum(
        1 for w in ("fused", "blend", "ensemble")
        if re.search(r"\b" + w + r"\b", runtime) is not None)
    counts["H-P13"] = sum(1 for t in fusion_tokens + ("Slider",
                                                     "type=\"range\"")
                          if t in fe)
    counts["H-P13"] += 0 if re.search(r"\bfused\b", fe) is None else 1
    counts["H-P13"] += sum(
        1 for m in re.finditer("blend", fe)
        if "instead of a blended probability"
        not in fe[max(0, m.start() - 60):m.end() + 60])
    counts["H-P14"] = sum(1 for t in ("preferred_source", "winning_source",
                                      "source_winner") if t in runtime + fe)
    counts["H-P15"] = 0 if (P.SAMPLING_CONTEXT_LABEL ==
                            "FINITE_MC_SAMPLING_CONTEXT_ONLY"
                            and M.mc_sampling_se.__doc__.startswith(
                                "Binomial MC sampling SE")) else 1
    topk = P.compose(race_id="2022-r03-R", lap_number=2, state_time_s=None,
                     stage="EARLY", season=2022,
                     model_probs={"a": 0.5, "b": 0.3, "c": 0.2},
                     simulation_probs={"a": 0.4, "b": 0.4, "c": 0.2},
                     valid_trials=5000)["disagreement"]["top_k"]
    note = json.dumps(topk)
    counts["H-P16"] = 0 if "NOT P(finish<=k)" in note else 1
    old_mean = -0.15065782073566983
    fixed = _load(D8 / "v3_8d" / "evaluation_card_correction_01.json")
    counts["H-P17"] = 0 if (fixed["corrected_uncertainty"]
                            ["bootstrap_mean"] != old_mean) else 1
    corr = _load(D8 / "v3_8d" / "correction_01.json")
    ecard = _load(D8 / "v3_8e" / "fusion_card.json")
    counts["H-P18"] = 0 if (
        corr["corrected_d_card_identity"] == D_CARD_FIXED
        and ecard["d_card_identity"] == D_CARD_FIXED
        and "d_correction" in ecard) else 1
    counts["H-P19"] = 0 if (
        ecard["gate"] == "FUSION_IMPROVEMENT_NOT_SUPPORTED"
        and "FUSION_IMPROVEMENT_NOT_SUPPORTED" in runtime) else 1
    counts["H-P20"] = sum(
        1 for t in ("results/v3", "scripts/v3", ".parquet", ".pkl",
                    "joblib") if t in fe)
    counts["H-P21"] = counts["H-P1"]
    import api.v2_consensus_routes as R
    import api.v2_consensus_schemas as S
    rs = open(R.__file__).read() + open(S.__file__).read()
    counts["H-P22"] = sum(1 for t in ("seed=", "master_seed",
                                      "simulation_count", "n_trials",
                                      "n_futures", "fusion_alpha",
                                      "blend_weight") if t in rs)
    counts["H-P23"] = 0 if ("corrupt" in runtime
                            and "parameter_unavailable" in runtime) else 1
    counts["H-P24"] = sum(
        1 for ln in _git_status() if ln.strip()
        and not ln.split(None, 1)[-1].strip().strip('"').startswith(
            FINAL_ALLOW))
    guards = "\n".join(
        (ROOT / rel).read_text() for rel in (
            "tests/test_v3_8a_consensus_contract.py",
            "tests/test_v3_8b_source_adapters.py",
            "tests/test_v3_8c_consensus_metrics.py",
            "tests/test_v3_8d_evaluation.py",
            "tests/test_v3_8d_correction_01.py",
            "tests/test_v3_5a_contract.py",
            "tests/test_v3_5b_dataset.py",
            "tests/test_v3_5c_harness.py",
            "tests/test_v3_5d_screening.py",
            "tests/test_v3_6a_contract.py",
            "tests/test_v3_6b_contracts.py",
            "tests/test_v3_6d_evaluation.py",
            "tests/test_v3_6f_runtime.py",
            "tests/test_v3_6h_freeze.py",
            "tests/test_v3_7a_contract.py"))
    counts["H-P25"] = sum(
        1 for t in ("xfail", "pytest.mark.skip", "ignore v3_8",
                    "ignore all untracked", "ignore results/",
                    "ignore docs/", "ignore scripts/") if t in guards)
    runner = (ROOT / "scripts" / "run_ci_tests.py").read_text()
    counts["H-P26"] = 0 if ("KNOWN_STALE_NODE_IDS: tuple[tuple[str, str], ...]"
                            " = ()" in runner) else 1
    view = (fe_base / "components" / "ConsensusView.tsx").read_text()
    counts["H-P27"] = 0 if "Historical replay" in view else 1
    counts["H-P28"] = 0 if ("Illustrative supported state" in view
                            and "not typical of all races" in view) else 1
    sci = "".join(open((ROOT / "raceintel" / "consensus" / m).as_posix()).read()
                  for m in ("contracts.py", "adapters.py", "alignment.py",
                            "metrics.py", "trajectories.py", "product.py"))
    counts["H-P29"] = sum(1 for t in ("from api", "import api",
                                      "from frontend", "import frontend")
                          if t in sci)
    manifest = _load(MANIFEST)
    owned = set(manifest["ownership_manifest"])
    walked = set()
    for owned_dir in ("results/v3/v3_8a", "results/v3/v3_8b",
                      "results/v3/v3_8c", "results/v3/v3_8d",
                      "results/v3/v3_8e", "results/v3/v3_8f",
                      "results/v3/v3_8g", "results/v3/v3_8h",
                      "raceintel/consensus", "frontend/app/consensus",
                      "frontend/features/consensus"):
        for path in (ROOT / owned_dir).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts \
                    and not path.name.endswith(".pyc"):
                walked.add(str(path.relative_to(ROOT)))
    counts["H-P30"] = len(walked - owned)
    return counts


def test_h_pathology_superset_all_zero():
    counts = _h_pathology_counts()
    assert set(counts) == {f"H-P{i}" for i in range(1, 31)}, set(counts)
    bad = {k: v for k, v in counts.items() if v != 0}
    assert bad == {}, bad
