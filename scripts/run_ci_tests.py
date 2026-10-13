"""Ordinary-CI Python test runner (P10-2, selection contract P10-4R).

TIER 1 — NORMAL SOURCE CI: the strongest deterministic test surface that
runs from a FRESH GIT CHECKOUT with only Python 3.11 plus
``requirements.txt`` / ``requirements-test.txt`` — no ``runtime_artifacts``
bundle, no ignored scientific corpus (``data/v2/processed/*``,
canonical ``results/*``, model-lab outputs), no FastF1 cache, no
scientific generation, no network F1 acquisition, no local developer
files. Tracked small artifacts (e.g. the serving joblib, frontend
``*.v1.json``) are allowed inputs.

A test is SOURCE_SAFE only if it satisfies the paragraph above. Tests
that do not are classified below — "not run in normal source CI" does
NOT mean "validated by normal source CI":

- ``ci_corpus_dependent.txt`` (sibling manifest): frozen scientific
  tests requiring the ignored canonical corpus at canonical paths.
  They fail on a clean checkout (FileNotFoundError / empty-glob
  concatenation / NaN from estimation on empty inputs) and pass where
  the corpus exists. This corrects the P10-2 assumption that such
  tests self-skip: P10-4 proved several files (e.g. F14 with
  ``_HAS_D9 = True``) have no skip guard. Full scientific validation
  is TIER 3 (local/release, science-owner evidence), not ordinary CI.
  Frozen science files are NOT modified to add skips.
- RUNTIME_DEPENDENT_NODE_IDS: tests requiring the validated
  ``runtime_artifacts`` bundle. P10-4 evidence shows this class is
  currently EMPTY (no failure references the bundle); the manifest
  exists so any future bundle dependency is explicit, never silent.
- KNOWN_STALE_NODE_IDS: pre-existing stale historical pins (frozen
  Phase-4–6 expectations legitimately moved past by later phases;
  disposition belongs to science owners / P11). Different reason from
  corpus dependence; kept separate on purpose.

TIER 2 — DEPLOYABLE RUNTIME VALIDATION (source + bundle + Docker/
Compose, P10-1/P10-4 evidence) is not ordinary CI until bundle
distribution exists.

Contains no science: this script only collects, checks the manifest
fail-closed, and shells out to pytest. Selected source-safe tests fail
normally on regression — no suppression, no exit-code rewriting.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CORPUS_MANIFEST = Path(__file__).resolve().parent / "ci_corpus_dependent.txt"

# Total collected tests/ at the frozen baseline. Pinned fail-closed: any
# added/removed/renamed test changes collection and forces a manifest
# review instead of silently entering (or leaving) normal CI.
# 3184 at Phase-9 freeze + 7 P10-4R CI-contract tests = 3191 at the P10
# freeze; P11-1 adds 11 Tier-3 contract tests
# (tests/test_science_validation_contract.py) with no removals
# (the stale cache test was renamed 1:1) = 3202; P11-3 adds 6
# benchmark-script unit tests (tests/test_p11_benchmark_script.py, pure
# computation, source-safe, no corpus) with no removals = 3210; P12-1 adds
# 48 spatial contract/governance tests (tests/test_spatial_contracts.py,
# test_spatial_validation.py, test_spatial_manifest.py,
# test_spatial_firewall.py; pure computation/source-scan, source-safe, no
# corpus) with no removals = 3258; P12-2 adds 31 spatial ingestion tests
# (tests/test_spatial_ingestion.py; fake sessions/tmp dirs, source-safe,
# no corpus) with no removals = 3289; P12-3 adds 27 circuit geometry
# tests (tests/test_spatial_geometry.py; synthetic loops/tmp dirs,
# source-safe, no corpus) with no removals = 3316; P12-4 adds 62
# temporal resolver tests (tests/test_spatial_resolver.py; synthetic
# series/tmp dirs, source-safe, no corpus) with no removals = 3378;
# P12-5 adds 29 spatial API tests (tests/test_spatial_api.py; stub
# replay service/tmp dirs, source-safe, no corpus) with no removals
# = 3407; V3.1B adds 64 dynamics tests (57 source-safe across
# test_v3_race_dynamics_contract / primitives / calculators / leakage /
# governance, plus 7 corpus-dependent artifact tests now pinned in
# ci_corpus_dependent.txt; repaired under V3.1A-C1 v3.1a-v2) with no
# removals = 3471; V3.1C adds 14 experiment tests (10 source-safe in
# tests/test_v3_1c_experiment.py plus 4 corpus-dependent in
# tests/test_v3_1c_corpus.py, pinned in ci_corpus_dependent.txt) with
# no removals = 3485; V3.1D adds 11 holdout-governance tests (source-safe
# in tests/test_v3_1d_holdout.py; preregistration, firewall, acceptance
# policy, verdict serialization, serving non-overwrite) with no removals
# = 3496; V3.2A adds 6 audit tests (5 source-safe, 1 corpus-dependent
# pinned in ci_corpus_dependent.txt) with no removals = 3502; V3.2B adds
# 12 contract tests (9 source-safe, 3 corpus-dependent pinned in
# ci_corpus_dependent.txt) with no removals = 3514; V3.2C adds 102 adapter
# and parity tests (5 source-safe presence tests + 77 corpus-dependent
# parity/API nodes + 20 corpus-dependent presence nodes, pinned in
# ci_corpus_dependent.txt) with no removals = 3616; V3.2D adds 18 MC2
# dynamics tests (16 source-safe in tests/test_v3_2d_mc2_dynamics.py plus
# 2 corpus-dependent pinned in ci_corpus_dependent.txt) with no removals
# = 3634; V3.2E adds 15 backtest tests (10 source-safe in
# tests/test_v3_2e_backtest.py plus 5 corpus-dependent pinned in
# ci_corpus_dependent.txt) with no removals = 3649; V3.2F adds 23
# regime-support tests (9 source-safe in
# tests/test_v3_2f_regime_decisions.py plus 14 corpus-dependent in
# tests/test_v3_2f_regime_corpus.py, pinned in ci_corpus_dependent.txt)
# with no removals = 3672; V3.2G adds 19 driver-status tests (9
# source-safe in tests/test_v3_2g_driver_status.py plus 10
# corpus-dependent in tests/test_v3_2g_status_corpus.py, pinned in
# ci_corpus_dependent.txt) with no removals = 3691; V3.2H adds 15
# regime-model tests (7 source-safe in
# tests/test_v3_2h_regime_models.py plus 8 corpus-dependent in
# tests/test_v3_2h_regime_corpus.py, pinned in ci_corpus_dependent.txt)
# with no removals = 3706; V3.2I adds 13 status-source tests (6
# source-safe in tests/test_v3_2i_status_models.py plus 7
# corpus-dependent in tests/test_v3_2i_status_corpus.py, pinned in
# ci_corpus_dependent.txt) with no removals = 3719; V3.2J adds 29
# driver-status tests (18 source-safe in
# tests/test_v3_2j_status_models.py plus 11 corpus-dependent in
# tests/test_v3_2j_status_corpus.py, pinned in ci_corpus_dependent.txt)
# with no removals = 3748; V3.2K adds 12 reconstruction-freeze tests
# (source-safe in tests/test_v3_2k_reconstruction.py) with no removals
# = 3760; V3.2L adds 27 lifecycle-freeze tests (source-safe in
# tests/test_v3_2l_lifecycle.py) with no removals = 3787; V3.2M adds 20
# pit-lifecycle tests plus V3.2N adds 24 freeze-validation tests (all
# corpus-dependent in tests/test_v3_2m_pit_lifecycle.py and
# tests/test_v3_2n_final_validation.py, pinned in ci_corpus_dependent.txt)
# with no removals = 3831; V3.6H reclassifies the V3.3/V3.4/V3.5/V3.6
# backlog (EXPECTED was last reclassified at V3.2N): 598 added tests
# across 24 files, of which 109 are corpus-dependent (pinned in
# ci_corpus_dependent.txt; clean-checkout simulation evidence in the
# manifest header) and 489 source-safe, plus 20 source-safe V3.6H freeze
# tests (tests/test_v3_6h_freeze.py), with no removals = 4449.
# V3.7H reclassification: 244 added tests across 7 new files
# (tests/test_v3_7a_contract.py, test_v3_7b_contracts.py,
# test_v3_7c_engine.py, test_v3_7d_evaluation.py, test_v3_7f_api.py,
# test_v3_7f_cache.py, test_v3_7f_runtime.py), of which 0 are
# corpus-dependent (no ignored-corpus references; serving-stack inputs
# match existing Tier-1 serving tests) and 244 source-safe, with no
# removals = 4693.
# V3.8H reclassification: 309 added tests across 11 new files
# (tests/test_v3_8a_consensus_contract.py, test_v3_8b_alignment.py,
# test_v3_8b_source_adapters.py, test_v3_8c_consensus_metrics.py,
# test_v3_8c_consensus_trajectories.py, test_v3_8d_correction_01.py,
# test_v3_8d_evaluation.py, test_v3_8e_fusion.py,
# test_v3_8f_consensus_api.py, test_v3_8f_consensus_contract.py,
# test_v3_8h_freeze.py), of which 0 are corpus-dependent (committed
# results/v3/v3_8* artifacts are Tier-1 inputs like other tracked
# artifacts; no ignored-corpus references) and 309 source-safe, with no
# removals = 5002.
# MC2-Perf-P0 reclassification: 8 added tests in tests/test_perf_mc2_p0.py
# (audit-only performance baseline; corpus-guarded live check + static
# artifact/config/pathology checks; no corpus dependence added), with no
# removals = 5010.
# MC2-Perf-P1 reclassification: 18 added tests in
# tests/test_mc2_batch_p1.py (deterministic batch-executor unit/audit
# checks + corpus-guarded small live parity smoke; production-scale proof
# asserted via committed p1 artifacts, not rerun), with no removals = 5028.
# MC2-Perf-P2A reclassification: 12 added tests in
# tests/test_mc2_p2a.py (low-risk kernel-overhead audit; parity/pathology
# checks + corpus-guarded small live checks; production evidence asserted
# via committed p2a artifacts, not rerun), with no removals = 5040.
# MC2-Perf-P2B reclassification: 13 added tests in
# tests/test_mc2_p2b.py (exact-order heap event-queue audit; scripted/fuzz/
# tie/live-trace checks + corpus-guarded small live parity; production
# evidence asserted via committed p2b artifacts, not rerun), with no
# removals = 5053.
# MC2-Perf-P3-1 reclassification: 14 added tests in
# tests/test_mc2_p3_1.py (exact scalar-interpolation audit: inventory/
# exactness/microbenchmark/parity/pathology checks + corpus-guarded grid
# assumption checks; production evidence asserted via committed p3_1
# artifacts, not rerun), with no removals = 5067.
# MC2-Perf-Freeze reclassification: 9 added tests in
# tests/test_perf_mc2_freeze.py (focused freeze validation only: provenance/
# manifest/parity/benchmark-identity/P3-1-zero-delta/guard/card/pathology/
# pin checks; production evidence asserted via committed freeze artifacts,
# not rerun), with no removals = 5076.
EXPECTED_COLLECTED = 5076

# (pytest node id, reason it cannot pass at the frozen baseline)
# P11-1: the 12 pre-existing stale historical pins were genuinely corrected
# (drift chains extended, bundle-era cache contract, lineage assertions,
# Python-3.11 re-baselined MC identities), so this list is empty. Corrected
# tests that still need the ignored corpus are excluded under the
# CORPUS_DEPENDENT reason in ci_corpus_dependent.txt, never here. The empty
# tuple plus the disjointness/non-empty guards below keep the mechanism
# fail-closed for any future stale debt.
KNOWN_STALE_NODE_IDS: tuple[tuple[str, str], ...] = ()

# Tests requiring the validated runtime_artifacts bundle. Empty per P10-4
# evidence (zero failures reference the bundle); kept explicit so a future
# bundle dependency cannot slip in silently.
RUNTIME_DEPENDENT_NODE_IDS: tuple[tuple[str, str], ...] = ()


def _read_corpus_manifest() -> list[str]:
    if not CORPUS_MANIFEST.is_file():
        print(f"run_ci_tests: missing {CORPUS_MANIFEST.name}.",
              file=sys.stderr)
        raise SystemExit(2)
    nodes = [ln.strip() for ln in CORPUS_MANIFEST.read_text().splitlines()
             if ln.strip() and not ln.strip().startswith("#")]
    return nodes


def _collect() -> list[str]:
    proc = subprocess.run(
        [sys.executable, "-m", "pytest", "tests/", "--collect-only",
         "-q", "-p", "no:cacheprovider"],
        capture_output=True, text=True, cwd=ROOT)
    if proc.returncode != 0:
        print("run_ci_tests: collection failed:\n" + proc.stdout
              + proc.stderr, file=sys.stderr)
        raise SystemExit(2)
    return [ln for ln in proc.stdout.splitlines() if ln.startswith("tests/")]


def main() -> int:
    corpus_nodes = _read_corpus_manifest()
    collected = _collect()
    if len(collected) != EXPECTED_COLLECTED:
        print(f"run_ci_tests: collected {len(collected)} != expected "
              f"{EXPECTED_COLLECTED}; the suite drifted — reclassify new/ "
              f"removed tests before CI can pass.", file=sys.stderr)
        return 2
    manifest = ([n for n, _ in KNOWN_STALE_NODE_IDS]
                + [n for n, _ in RUNTIME_DEPENDENT_NODE_IDS]
                + corpus_nodes)
    if len(set(manifest)) != len(manifest):
        print("run_ci_tests: duplicate node ids in exclusion manifest.",
              file=sys.stderr)
        return 2
    stale_overlap = set(corpus_nodes) & {n for n, _ in KNOWN_STALE_NODE_IDS}
    if stale_overlap:
        print("run_ci_tests: nodes in both stale and corpus manifests "
              f"(keep stale only): {sorted(stale_overlap)[:10]}",
              file=sys.stderr)
        return 2
    collected_set = set(collected)

    def _covered(node: str) -> bool:
        # Exact node id, or a bare test id covering its parametrizations
        # (pytest --deselect matches "test_x" against "test_x[...]").
        return (node in collected_set or any(
            c.startswith(node + "[") for c in collected_set))

    gone = [n for n in manifest if not _covered(n)]
    if gone:
        print(f"run_ci_tests: {len(gone)} manifest node(s) no longer "
              f"collected (renamed/removed?) — review manifest: {gone[:10]}",
              file=sys.stderr)
        return 2
    selected = len(collected) - len(manifest)
    if selected <= 0:
        print("run_ci_tests: manifest deselects the whole suite.",
              file=sys.stderr)
        return 2
    print(f"run_ci_tests: collected={len(collected)} "
          f"selected={selected} deselected={len(manifest)} "
          f"(stale={len(KNOWN_STALE_NODE_IDS)} "
          f"runtime={len(RUNTIME_DEPENDENT_NODE_IDS)} "
          f"corpus={len(corpus_nodes)})")
    cmd = [sys.executable, "-m", "pytest", "tests/", "-q"]
    for nodeid in manifest:
        cmd += ["--deselect", nodeid]
    proc = subprocess.run(cmd, cwd=ROOT)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
