"""V2 path / cache configuration (D3).

One authoritative layer: every V2 path derives from an explicit project
root. No cwd-relative strings anywhere in V2 ingestion code. Tests and
scratch runs pass an explicit root (tmp_path); production defaults to the
repository root. FastF1 cache is configured deliberately through one
helper — the single cache location for all new V2 code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Env override for the project root (CI/scratch). Absolute personal paths
# must never leak into canonical metadata — see runs.py.
PROJECT_ROOT_ENV_VAR = "V2_PROJECT_ROOT"

# Legacy cache location, reused as-is (D0/D1). Never moved/duplicated.
LEGACY_CACHE_REL = Path("data/raw/fastf1_cache")

V2_ROOT_REL = Path("data/v2")
MANIFESTS_REL = V2_ROOT_REL / "raw" / "manifests"
INTERIM_REL = V2_ROOT_REL / "interim"
PROCESSED_REL = V2_ROOT_REL / "processed"
REPORTS_REL = V2_ROOT_REL / "reports" / "data_quality"


def discover_project_root(start: Path) -> Path:
    """Walk up from ``start`` to the repo root (holds ``raceintel/`` + ``data/``).

    Raises ConfigError instead of guessing: a wrong root silently scatters
    canonical output, which idempotency cannot repair.
    """
    for candidate in (start,) + tuple(start.parents):
        if (candidate / "raceintel").is_dir() and (candidate / "data").is_dir():
            return candidate
    raise ConfigError(
        f"cannot locate V2 project root from {start} "
        f"(set {PROJECT_ROOT_ENV_VAR} explicitly)")


@dataclass(frozen=True)
class V2Paths:
    """All V2 locations resolved against one explicit root."""

    root: Path
    v2_root: Path
    manifests_dir: Path
    interim_dir: Path
    processed_dir: Path
    reports_dir: Path
    cache_dir: Path

    @classmethod
    def from_root(cls, root: str | Path) -> "V2Paths":
        root = Path(root).resolve()
        v2_root = root / V2_ROOT_REL
        return cls(
            root=root,
            v2_root=v2_root,
            manifests_dir=root / MANIFESTS_REL,
            interim_dir=root / INTERIM_REL,
            processed_dir=root / PROCESSED_REL,
            reports_dir=root / REPORTS_REL,
            cache_dir=root / LEGACY_CACHE_REL,
        )

    @classmethod
    def resolve(cls, root: str | Path | None = None) -> "V2Paths":
        """Explicit root wins; then env override; then cwd discovery."""
        if root is not None:
            return cls.from_root(root)
        env = os.environ.get(PROJECT_ROOT_ENV_VAR)
        if env:
            return cls.from_root(env)
        return cls.from_root(discover_project_root(Path.cwd()))

    def relative(self, path: str | Path) -> str:
        """Portable project-relative reference for manifests/output refs."""
        return Path(path).resolve().relative_to(self.root).as_posix()

    def manifest_path(self, name: str = "manifest.json") -> Path:
        return self.manifests_dir / name


class ConfigError(Exception):
    """Configuration failure: non-retryable by definition (see errors.py)."""


def configure_fastf1_cache(cache_dir: str | Path) -> Path:
    """Enable the FastF1 cache at exactly one location.

    Must be called before any V2 session loading. Returns the resolved dir.
    The cache stays outside canonical data semantics: it accelerates loads,
    it is never an ingestion input of record.
    """
    import fastf1

    resolved = Path(cache_dir).resolve()
    resolved.mkdir(parents=True, exist_ok=True)
    fastf1.Cache.enable_cache(str(resolved))
    return resolved
