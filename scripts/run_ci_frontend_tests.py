"""Ordinary-CI frontend test selector (P10-4R).

TIER 1 — NORMAL SOURCE CI for the frontend: every tracked
``frontend/**/*.test.ts`` EXCEPT the files in CORPUS_DEPENDENT_TEST_FILES.
Runs from a fresh git checkout with only Node 22 + ``npm ci`` — no
ignored scientific corpus, no ``runtime_artifacts`` bundle, no local
developer state.

A frontend test file is SOURCE_SAFE only if it loads and passes under
those inputs. Currently exactly one file is corpus-dependent:

- ``features/models/lib/evidence.test.ts`` reads the IGNORED generated
  report ``data/v2/model_lab/reports/final_holdout_2025_v1.json`` at
  module top level (used by a single test,
  "holdout values equal the frozen report at stored precision"). The
  top-level read makes the file atomic: the remaining 15 tests (which
  use only TRACKED ``frontend/data/*.v1.json`` and the TRACKED
  ``scripts/build_phase9_evidence.py``) cannot run without the corpus
  either, so the whole file is Tier 3 (full validation with corpus),
  not Tier 1. This is a test-design dependency, not a product defect:
  the shipped evidence contract itself (``frontend/data/*.v1.json``)
  is tracked and self-contained.

Normal developer semantics are unchanged: plain ``node --test`` still
runs everything where the corpus exists. This script only selects the
source-safe subset for CI, fail-closed (manifest entries must exist;
discovered file count must match EXPECTED_TEST_FILES; selection must
be non-empty). No dependencies beyond the stdlib; node failures
propagate normally.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"

# Total frontend *.test.ts files at the frozen baseline. Pinned
# fail-closed: a new/renamed test file forces manifest review.
# 17 at the P10-4R freeze; P12-6 adds lib/spatial.test.ts (pure
# spatial client/view-model, node type-stripping, no corpus) = 18;
# P12-7 adds features/replay/lib/spatialIntegration.test.ts (pure
# replay-integration guards, node type-stripping, no corpus) = 19;
# P12-8 adds features/replay/lib/raceStatus.test.ts (pure status
# view-model, node type-stripping, no corpus) = 20; V3.6G adds
# features/strategy/lib/strategy2Machine.test.ts (reads only tracked
# Strategy2 sources; copy/contract guards, no corpus) = 21; V3.7G adds
# features/counterfactuals/lib/counterfactualMachine.test.ts (reads only
# tracked counterfactual machine sources + committed sibling fixtures;
# orientation/copy/contract guards, no corpus) = 22; V3.8G adds
# features/consensus/components/consensus-page.test.ts and
# features/consensus/lib/consensusFormat.test.ts (read only tracked
# consensus sources + committed v3_8f fixtures; copy/contract guards,
# no corpus) = 24; later stages added pit-wall/workspace/models/
# prediction/replay/simulation/strategy/uncertainty/consensus suites
# without bumping this pin (43 at the V3-final freeze); C5 post-V3
# adds lib/http.test.ts (shared transport guards, node
# type-stripping, no corpus) and corrects the pin to the true
# tracked count = 44.
EXPECTED_TEST_FILES = 44

# Repo-root-relative frontend test files requiring the ignored corpus.
CORPUS_DEPENDENT_TEST_FILES: tuple[tuple[str, str], ...] = (
    ("frontend/features/models/lib/evidence.test.ts",
     "top-level read of ignored data/v2/model_lab/reports/"
     "final_holdout_2025_v1.json; file is atomic, rest is Tier 3"),
)


def main() -> int:
    test_files = sorted(
        str(p.relative_to(ROOT)) for p in FRONTEND.rglob("*.test.ts")
        if "node_modules" not in p.parts and ".next" not in p.parts)
    if len(test_files) != EXPECTED_TEST_FILES:
        print(f"run_ci_frontend_tests: found {len(test_files)} test files "
              f"!= expected {EXPECTED_TEST_FILES}; review manifest.",
              file=sys.stderr)
        return 2
    excluded = [f for f, _ in CORPUS_DEPENDENT_TEST_FILES]
    missing = [f for f in excluded
               if not (ROOT / f).is_file()]
    if missing:
        print(f"run_ci_frontend_tests: exclusion disappeared: {missing}.",
              file=sys.stderr)
        return 2
    selected = [f for f in test_files if f not in excluded]
    if not selected:
        print("run_ci_frontend_tests: manifest excludes everything.",
              file=sys.stderr)
        return 2
    print(f"run_ci_frontend_tests: collected={len(test_files)} "
          f"selected={len(selected)} deselected={len(excluded)}")
    cmd = (["node", "--test"]
           + [str(ROOT / f) for f in selected])
    proc = subprocess.run(cmd, cwd=FRONTEND)
    return proc.returncode


if __name__ == "__main__":
    raise SystemExit(main())
