"""Tier-3 science environment preflight (P11-1).

Fails early (before pytest) when the canonical local scientific corpus is
absent or structurally invalid. Tier-3 validates frozen science; it never
rebuilds it.

This script MUST stay stdlib-only: it checks interpreter version, marker
path presence, and marker manifest shape. It does not install packages,
start servers, download anything, run FastF1 ingestion, regenerate
datasets/matrices/caches/parameters, retrain models, or read 2025
evaluation targets. It loads no datasets (marker manifests only).

Corpus contract (minimum presence for the full ``pytest tests/`` Tier-3
suite, derived from ``scripts/ci_corpus_dependent.txt`` reason groups):

- D9 canonical states: ``data/v2/processed/driver_lap_state_d9/``
- simulation parameters: ``data/v2/simulation/params/r3-v1__through-2024/``
  with a readable ``manifest.json``
- feature matrix: ``data/v2/processed/model_matrix/matrix_version=v1/``
  with a readable ``manifest.json``
- replay cache: ``results/v2_replay/`` with the E2 cache manifest
  (149 races / 9644 checkpoints)
- model-lab holdout evidence: ``data/v2/model_lab/reports/``
  with the frozen one-shot holdout report

Two failure classes are distinguished:

- MISSING_CORPUS: a marker path is absent (fresh checkout / bundle-only
  tree). Tier-3 scientific regression requires the canonical local
  scientific corpus. No data is downloaded or generated automatically.
- INVALID_CONTRACT: a marker path exists but is empty, unreadable, or
  structurally wrong (failing manifest parse / count mismatch). This is
  NOT certified as scientifically valid — only as structurally present;
  validity is proven by the Tier-3 suite itself.

Exit status: 0 when the contract holds, 2 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SUPPORTED_PYTHON_MAJOR = 3
SUPPORTED_PYTHON_MINOR = 11

# (relative dir, purpose)
CORPUS_DIRS = (
    (Path("data/v2/processed/driver_lap_state_d9"),
     "canonical D9 states"),
    (Path("data/v2/simulation/params/r3-v1__through-2024"),
     "frozen simulation parameters"),
    (Path("data/v2/processed/model_matrix/matrix_version=v1"),
     "frozen feature matrix"),
    (Path("results/v2_replay"),
     "served replay cache"),
    (Path("data/v2/model_lab/reports"),
     "model-lab generated reports"),
)

# (relative manifest, required key, expected value or None)
CORPUS_MANIFESTS = (
    (Path("data/v2/simulation/params/r3-v1__through-2024/manifest.json"),
     None, None),
    (Path("data/v2/processed/model_matrix/matrix_version=v1/manifest.json"),
     None, None),
    (Path("results/v2_replay/phase8_e2_cache_manifest_v1.json"),
     "checkpoint_count", 9644),
    (Path("data/v2/model_lab/reports/final_holdout_2025_v1.json"),
     None, None),
)

EXPECTED_REPLAY_RACES = 149


def default_root() -> Path:
    """Repository root derived from this script's location (no cwd use)."""
    return Path(__file__).resolve().parents[1]


def check_python_version(version=None) -> list[str]:
    """The running interpreter must be the supported Python 3.11 line."""
    if version is None:
        version = sys.version_info
    major, minor = version[0], version[1]
    if (major, minor) != (SUPPORTED_PYTHON_MAJOR, SUPPORTED_PYTHON_MINOR):
        return [
            f"unsupported Python {major}.{minor} "
            f"(supported: {SUPPORTED_PYTHON_MAJOR}.{SUPPORTED_PYTHON_MINOR}.x); "
            "activate a Python 3.11 environment first, e.g. "
            "`python3.11 -m venv .venv && source .venv/bin/activate`",
        ]
    return []


def check_corpus(root: Path) -> tuple[list[str], list[str]]:
    """Return (missing, invalid) problem lists for the corpus contract."""
    missing: list[str] = []
    invalid: list[str] = []
    for rel, purpose in CORPUS_DIRS:
        path = root / rel
        if not path.is_dir():
            missing.append(
                f"MISSING_CORPUS: {rel}/ absent ({purpose})")
        elif not any(path.iterdir()):
            invalid.append(
                f"INVALID_CONTRACT: {rel}/ exists but is empty ({purpose})")
    for rel, key, expected in CORPUS_MANIFESTS:
        path = root / rel
        if not path.is_file():
            missing.append(f"MISSING_CORPUS: {rel} absent")
            continue
        try:
            manifest = json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            invalid.append(f"INVALID_CONTRACT: {rel} unreadable: {exc}")
            continue
        if not isinstance(manifest, dict) or not manifest:
            invalid.append(f"INVALID_CONTRACT: {rel} is not a JSON object")
            continue
        if key is not None and manifest.get(key) != expected:
            invalid.append(
                f"INVALID_CONTRACT: {rel} has {key}="
                f"{manifest.get(key)!r}, expected {expected!r}")
    replay_manifest = root / "results" / "v2_replay" / \
        "phase8_e2_cache_manifest_v1.json"
    if replay_manifest.is_file():
        try:
            races = json.loads(replay_manifest.read_text()).get("race_count")
        except (OSError, ValueError):
            races = None
        if races != EXPECTED_REPLAY_RACES:
            invalid.append(
                f"INVALID_CONTRACT: replay cache race_count={races!r}, "
                f"expected {EXPECTED_REPLAY_RACES}")
    checkpoints = root / "results" / "v2_replay" / "checkpoints"
    if checkpoints.is_dir():
        try:
            count = sum(1 for _ in checkpoints.iterdir())
        except OSError:
            count = -1
        if count != EXPECTED_REPLAY_RACES:
            invalid.append(
                f"INVALID_CONTRACT: results/v2_replay/checkpoints/ holds "
                f"{count} entries, expected {EXPECTED_REPLAY_RACES} "
                "per-race files")
    return missing, invalid


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Tier-3 science corpus preflight (no science).")
    parser.add_argument("--root", default=None,
                        help="project root (default: script location)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve() if args.root else default_root()
    errors = check_python_version()
    missing, invalid = check_corpus(root)
    errors.extend(missing)
    errors.extend(invalid)
    if errors:
        print("preflight SCIENCE FAIL "
              f"({len(errors)} problem(s)):", flush=True)
        for error in errors:
            print(f"  - {error}", flush=True)
        print("Tier-3 scientific regression requires the canonical local "
              "scientific corpus. No data is downloaded or generated "
              "automatically.", flush=True)
        return 2
    print(f"preflight SCIENCE OK (root={root})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
