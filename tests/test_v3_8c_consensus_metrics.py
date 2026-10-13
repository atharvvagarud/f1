"""V3.8C metrics tests: rank/magnitude/MC-context math + prohibitions.

Hand-computed fixtures with independent recomputation (values derived
here, not by calling helpers twice), scipy cross-checks for Spearman/
Kendall, tie matrix, orientation sentinels, poison cases, and structural
prohibition guards.
"""

import hashlib
import json
import math
from pathlib import Path

import pytest

from raceintel.consensus import contracts as C
from raceintel.consensus import metrics as M

ROOT = Path(__file__).resolve().parents[1]
C_CONTRACT = ROOT / "results" / "v3" / "v3_8c" / "metrics_contract.json"


def _c():
    return json.loads(C_CONTRACT.read_text())


# --- contract / identities ---


def test_a_identity_exact():
    assert _c()["a_identity"] == \
        "d0b8785a01347580125b38b311984c793c012352ce3ff175cfa3504379b9a67b"


def test_b_identity_exact():
    assert _c()["b_identity"] == \
        "d212803f7ed7e8a8563abdd5b7686326e7094d810f415fa1468117541dfbfde7"


def test_c_contract_schema():
    assert _c()["schema"] == "v3.8c-consensus-metrics-contract-v1"


def test_c_contract_identity_recomputes():
    c = _c()
    identity = c.pop("contract_identity")
    blob = json.dumps(c, sort_keys=True, separators=(",", ":")).encode()
    assert identity == hashlib.sha256(blob).hexdigest()
    assert identity == \
        "07cf1ddd9708eaea2280b1d46492d972234f68c77cf3a59cbf412f638e3a74a8"


def test_metric_implementation_identity():
    assert M.METRICS_IMPLEMENTATION_IDENTITY == "v3.8c-consensus-metrics-v1"
    assert _c()["implementation_identities"]["metrics"] == \
        M.METRICS_IMPLEMENTATION_IDENTITY


def test_primary_pair_frozen():
    assert M.PRIMARY_PAIR == (
        C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E)


def test_lineage_relation_exact():
    assert M.lineage_relation(
        C.SourceId.V3_1B_LOGISTIC, C.SourceId.V3_5_LOGISTIC_CONTROL,
        C.Target.WIN) is M.LineageRelation.SHARED_OR_DERIVED_LINEAGE
    assert M.lineage_relation(
        C.SourceId.V3_1B_LOGISTIC, C.SourceId.MC2_E,
        C.Target.WIN) is M.LineageRelation.DISTINCT_MECHANISM


# --- average ranks ---


def test_average_rank_no_ties():
    assert M.average_ranks({"a": 0.9, "b": 0.5, "c": 0.1}) == {
        "a": 1.0, "b": 2.0, "c": 3.0}


def test_average_rank_ties():
    assert M.average_ranks(
        {"a": 0.8, "b": 0.5, "c": 0.5, "d": 0.2}) == {
        "a": 1.0, "b": 2.5, "c": 2.5, "d": 4.0}


def test_average_rank_input_order_irrelevant():
    assert (M.average_ranks({"x": 0.5, "y": 0.5, "z": 0.8})
            == M.average_ranks({"z": 0.8, "y": 0.5, "x": 0.5}))


# --- Spearman (hand + scipy) ---


def test_spearman_plus_one():
    ra = {"a": 1.0, "b": 2.0, "c": 3.0}
    assert M.spearman(ra, dict(ra)) == pytest.approx(1.0)


def test_spearman_minus_one():
    ra = {"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0}
    rb = {"a": 4.0, "b": 3.0, "c": 2.0, "d": 1.0}
    assert M.spearman(ra, rb) == pytest.approx(-1.0)


def test_spearman_partial_hand_computed():
    # a: ranks 1,2.5,2.5,4 ; b: ranks 1,2,3,4.
    # Pearson on ([1,2.5,2.5,4],[1,2,3,4]): mean 2.5/2.5,
    # num = 1.5*1.5 + 0*0.5 + 0*(-0.5)... hand: cov num = 4.5,
    # dx = 4.5, dy = 5 -> 4.5/sqrt(22.5) = 0.948683...
    ra = {"d1": 1.0, "d2": 2.5, "d3": 2.5, "d4": 4.0}
    rb = {"d1": 1.0, "d2": 2.0, "d3": 3.0, "d4": 4.0}
    assert M.spearman(ra, rb) == pytest.approx(0.9486832980505138)


def test_spearman_matches_scipy():
    scipy = pytest.importorskip("scipy.stats")
    ra = {"d1": 1.0, "d2": 2.5, "d3": 2.5, "d4": 4.0}
    rb = {"d1": 2.0, "d2": 1.0, "d3": 3.0, "d4": 4.0}
    got = M.spearman(ra, rb)
    exp = scipy.spearmanr([1, 2.5, 2.5, 4], [2, 1, 3, 4]).statistic
    assert got == pytest.approx(exp)


def test_spearman_zero_variance_unsupported():
    r = M.average_ranks({"a": 0.5, "b": 0.5})
    assert M.spearman(r, r) is None
    assert M.spearman({"a": 1.0}, {"a": 1.0}) is None


# --- Kendall tau-b (hand + scipy) ---


def test_kendall_plus_one():
    ra = {"a": 1.0, "b": 2.0, "c": 3.0}
    assert M.kendall_taub(ra, dict(ra)) == pytest.approx(1.0)


def test_kendall_minus_one():
    ra = {"a": 1.0, "b": 2.0, "c": 3.0}
    rb = {"a": 3.0, "b": 2.0, "c": 1.0}
    assert M.kendall_taub(ra, rb) == pytest.approx(-1.0)


def test_kendall_tie_case_hand_computed():
    # a ranks {1,2.5,2.5,4}, b ranks {1,2,3,4}: pairs C(4,2)=6.
    # concordant 5 (all but d2/d3 tied in a), tie_a 1, tie_b 0.
    # tau-b = 5/sqrt(6*5) = 5/sqrt(30) = 0.912870...
    ra = {"d1": 1.0, "d2": 2.5, "d3": 2.5, "d4": 4.0}
    rb = {"d1": 1.0, "d2": 2.0, "d3": 3.0, "d4": 4.0}
    assert M.kendall_taub(ra, rb) == pytest.approx(0.9128709291752769)


def test_kendall_matches_scipy():
    scipy = pytest.importorskip("scipy.stats")
    a = [0.8, 0.5, 0.5, 0.2, 0.1]
    b = [0.7, 0.6, 0.4, 0.3, 0.05]
    ra = M.average_ranks({f"d{i}": v for i, v in enumerate(a)})
    rb = M.average_ranks({f"d{i}": v for i, v in enumerate(b)})
    assert M.kendall_taub(ra, rb) == pytest.approx(
        scipy.kendalltau(a, b).statistic)


def test_kendall_degenerate_unsupported():
    r = M.average_ranks({"a": 0.5, "b": 0.5})
    assert M.kendall_taub(r, r) is None
    assert M.kendall_taub({"a": 1.0}, {"a": 1.0}) is None


# --- displacement / leaders / top-k ---


def test_rank_displacement_orientation():
    assert M.rank_displacement(2.0, 5.0) == 3.0
    assert M.rank_displacement(5.0, 2.0) == -3.0


def test_rank_displacement_reverse_pair_negation():
    assert (M.rank_displacement(2.0, 5.0)
            == -M.rank_displacement(5.0, 2.0))


def test_leader_exact_match_overlap_disagreement():
    assert M.leader_set({"a": 1.0, "b": 2.0}) == frozenset({"a"})
    tie = M.leader_set({"a": 1.0, "b": 1.0, "c": 3.0})
    assert tie == frozenset({"a", "b"})
    other = M.leader_set({"a": 2.0, "b": 1.0, "c": 3.0})
    assert (tie == other) is False
    assert len(tie & other) > 0  # overlap without exact match


def test_leader_disagreement():
    assert M.leader_set({"a": 1.0, "b": 2.0}) != \
        M.leader_set({"a": 2.0, "b": 1.0})


def test_topk_exact_partial_none_overlap():
    r = {"a": 1.0, "b": 2.0, "c": 3.0, "d": 4.0}
    s1, n1 = M.topk_set(r, 2)
    assert (s1, n1) == (frozenset({"a", "b"}), 2)
    s2, _ = M.topk_set({"a": 1.0, "b": 3.0, "c": 2.0, "d": 4.0}, 2)
    assert M.jaccard(s1, s2) == pytest.approx(1 / 3)
    s3, _ = M.topk_set({"a": 4.0, "b": 3.0, "c": 2.0, "d": 1.0}, 2)
    assert M.jaccard(s1, s3) == pytest.approx(0.0)


def test_topk_boundary_tie_effective_size():
    r = {"a": 1.0, "b": 2.5, "c": 2.5, "d": 2.5, "e": 5.0}
    members, n = M.topk_set(r, 2)
    assert members == frozenset({"a", "b", "c", "d"})
    assert n == 4


# --- magnitude gaps ---


def test_signed_gap_orientation():
    assert M.signed_gap(0.2, 0.31) == pytest.approx(0.11)
    assert M.signed_gap(0.31, 0.2) == pytest.approx(-0.11)


def test_absolute_gap_symmetry():
    assert M.absolute_gap(0.2, 0.31) == M.absolute_gap(0.31, 0.2)


def test_reverse_pair_signed_negation():
    assert M.signed_gap(0.2, 0.5) == -M.signed_gap(0.5, 0.2)


def test_cross_target_gap_rejected():
    assert C.targets_compatible(
        C.SourceId.V3_1B_LOGISTIC, C.Target.WIN,
        C.SourceId.MC2_E, C.Target.TOP3) is False


def test_cross_target_rank_comparison_rejected_by_default():
    # Rankings of different targets answer different questions; the
    # compatibility gate is the single choke point for both families.
    assert C.targets_compatible(
        C.SourceId.V3_5_LOGISTIC_CONTROL, C.Target.TOP3,
        C.SourceId.V3_5_LOGISTIC_CONTROL, C.Target.TOP5) is False


def test_state_level_magnitude_summaries():
    gaps = [0.11, -0.05, 0.2]
    assert M.mean_absolute_gap(gaps) == pytest.approx(0.12)
    assert M.median_absolute_gap(gaps) == pytest.approx(0.11)
    assert M.max_absolute_gap(gaps) == pytest.approx(0.2)
    assert M.rms_gap([3.0, 4.0]) == pytest.approx(math.sqrt(12.5))
    assert M.mean_absolute_gap([]) is None


# --- MC sampling ---


def test_mc_se_known_fixture():
    assert M.mc_sampling_se(0.25, 100) == pytest.approx(
        math.sqrt(0.25 * 0.75 / 100))


def test_mc_wilson_known_fixture():
    lo, hi = M.wilson_interval(0.22, 5000)
    assert lo == pytest.approx(0.2087350384231392)
    assert hi == pytest.approx(0.23169489045390598)
    assert 0.0 <= lo <= 0.22 <= hi <= 1.0


def test_mc_p_zero():
    assert M.mc_sampling_se(0.0, 5000) == 0.0
    lo, hi = M.wilson_interval(0.0, 5000)
    assert lo == 0.0 and hi > 0.0


def test_mc_p_one():
    lo, hi = M.wilson_interval(1.0, 10)
    assert hi == 1.0 and lo < 1.0


def test_mc_invalid_n_rejected():
    with pytest.raises(ValueError):
        M.mc_sampling_se(0.2, 0)
    with pytest.raises(ValueError):
        M.wilson_interval(0.2, -5)


def test_model_value_inside_mc_interval_semantics():
    lo, hi = M.wilson_interval(0.22, 5000)
    assert M.value_inside_interval(0.22, (lo, hi)) is True
    assert M.value_inside_interval(0.9, (lo, hi)) is False


# --- permutation / support / zero ---


def test_permutation_invariance():
    r1 = M.average_ranks({"a": 0.8, "b": 0.5, "c": 0.5, "d": 0.2})
    r2 = M.average_ranks({"d": 0.2, "c": 0.5, "b": 0.5, "a": 0.8})
    assert r1 == r2
    assert M.spearman(r1, r1) == M.spearman(r2, r2)


def test_missing_not_zero_state_ranks():
    got = M.state_ranks({"s1": {"a": 0.4}, "s2": {"a": 0.3, "b": 0.2}})
    assert got == {}


def test_native_zero_remains_numeric():
    assert M.signed_gap(0.0, 0.1) == pytest.approx(0.1)
    assert M.absolute_gap(0.0, 0.0) == 0.0


# --- structural prohibitions ---


def test_no_normalization_in_metrics():
    import raceintel.consensus.metrics as mod
    blob = open(mod.__file__).read().lower()
    for token in ("softmax", "simplex", "rescale", "renormaliz",
                  "normal("):
        assert token not in blob, token


def test_no_fusion_in_metrics():
    import raceintel.consensus.metrics as mod
    blob = open(mod.__file__).read().lower()
    for token in ("consensus =", "confidence", "fuse", "blend",
                  "stacking", "meta-model", "majority", "average("):
        assert token not in blob, token


def test_no_disagreement_thresholds():
    import raceintel.consensus.metrics as mod
    import raceintel.consensus.trajectories as tra
    blob = (open(mod.__file__).read() + open(tra.__file__).read())
    assert "0.05" not in blob and "0.10" not in blob and "0.20" not in blob
    assert "LOW_DISAGREEMENT" not in blob
    assert "HIGH_DISAGREEMENT" not in blob


def test_no_source_quality_ordering():
    import raceintel.consensus.metrics as mod
    blob = open(mod.__file__).read().lower()
    for token in ("winner_source", "preferred_source",
                  "more_reliable", "better_source"):
        assert token not in blob, token


def test_ground_truth_absent():
    import raceintel.consensus.metrics as mod
    import raceintel.consensus.trajectories as tra
    blob = (open(mod.__file__).read() + open(tra.__file__).read()).lower()
    for token in ("actual_winner", "final_position", "observed_outcome",
                  "y_true", "is_winner", "position_final", "accuracy"):
        assert token not in blob, token


def test_future_data_imports_absent():
    import raceintel.consensus.metrics as mod
    blob = "\n".join(
        ln for ln in open(mod.__file__).read().splitlines()
        if "from __future__" not in ln).lower()
    for token in ("parquet", "result_table", "labels", "future_",
                  "historical"):
        assert token not in blob, token


def test_no_frozen_source_modified():
    import subprocess
    out = subprocess.run(["git", "status", "--short"], capture_output=True,
                         text=True,
                         cwd=str(ROOT)).stdout
    # V3.8H reconciliation: the C stage-entry boundary predates the
    # chartered D-G additions (D/E scripts, F API/product, G frontend)
    # and the H freeze. Final freeze allowlist admits exactly the
    # chartered V3.8-owned paths, the two additive wiring files, and the
    # Tier-1 runner reclassification; any other dirt still fails.
    # Original invariant preserved: frozen-science mutation outside V3.8
    # ownership still trips this guard.
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


def test_reproducibility_exact():
    ra = {"a": 1.0, "b": 2.5, "c": 2.5}
    assert M.spearman(ra, dict(ra)) == M.spearman(dict(ra), ra)
    assert M.wilson_interval(0.3, 100) == M.wilson_interval(0.3, 100)
