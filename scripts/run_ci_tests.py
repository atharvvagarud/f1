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
# = 3496.
EXPECTED_COLLECTED = 3496

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
