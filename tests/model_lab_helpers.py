"""Shared fresh-clone helpers for Model Lab tests (P3.1-C).

Policy distinction (do not blur it):

- TRACKED prerequisites (committed source, tests, docs such as the freeze
  manifest, model card and final report): a missing file is a real failure
  and must still FAIL.
- GENERATED prerequisites (gitignored under ``data/v2/``: the canonical
  matrix, experiment directories and suite/report JSON): absent on a fresh
  checkout until a pipeline/suite materializes them. Tests depending on
  them must SKIP clearly instead of reporting false failures.

When the prerequisites ARE present, behavior is identical to a direct
load: no scientific assertion is weakened.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

# Files whose absence proves the canonical matrix was never built here.
# Checked directly so a corrupt-but-present matrix still fails loudly
# inside load_canonical instead of being masked as a skip.
MATRIX_PREREQUISITES = (
    "data/v2/processed/model_matrix/matrix_version=v1/model_matrix.parquet",
    "data/v2/processed/model_matrix/matrix_version=v1/manifest.json",
    "data/v2/processed/model_matrix/matrix_version=v1/ablation_config.json",
)


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def matrix_available(root=None) -> bool:
    """True when the generated canonical matrix prerequisites exist."""
    base = Path(root) if root is not None else _repo_root()
    return all((base / rel).exists() for rel in MATRIX_PREREQUISITES)


def require_matrix(root=None) -> None:
    """Skip the calling test when the gitignored matrix is absent."""
    if not matrix_available(root):
        missing = [rel for rel in MATRIX_PREREQUISITES
                   if not (_repo_root() / rel).exists()]
        pytest.skip(
            "canonical F15 matrix not materialized "
            f"(missing {missing[0] if missing else 'artifacts'}); "
            "build the Phase-2 matrix first")


def load_canonical_or_skip(**kwargs):
    """Load the canonical matrix, skipping on a fresh clone.

    Only a missing generated prerequisite skips. A present-but-invalid
    matrix still raises (and fails) inside ``load_canonical``.
    """
    from raceintel.model_lab import data as DATA

    require_matrix()
    return DATA.load_canonical(**kwargs)


def require_generated_artifact(path, *, purpose: str) -> Path:
    """Return ``path`` or SKIP when a gitignored artifact is absent."""
    dest = Path(path)
    if not dest.exists():
        pytest.skip(
            f"{purpose} missing at {dest}; "
            "run the generating suite first (fresh-clone skip)")
    return dest


def load_json_artifact_or_skip(path, *, purpose: str) -> dict:
    """Load a generated JSON artifact, skipping on a fresh clone."""
    dest = require_generated_artifact(path, purpose=purpose)
    with open(dest, encoding="utf-8") as fh:
        return json.load(fh)
