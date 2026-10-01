"""Deployability readiness (P10-3).

``GET /ready`` answers whether this backend can serve the frozen V2
runtime — NOT whether the process is alive (that is ``GET /health``).
Readiness validates runtime availability/identity only: file presence,
frozen SHA identity, and manifest fields. It never regenerates, repairs,
downloads, trains, loads models for inference, or evaluates anything.

Cost: the full validation runs once per process per project root and the
result is cached in process memory (orchestrators may poll repeatedly).
Startup/lazy service initialization is untouched and no scientific
artifact is mutated. Reset via :func:`reset_readiness_cache` (tests).
"""

from __future__ import annotations

import functools
import hashlib
import json
import os
from pathlib import Path

from raceintel.explainability import explainability as E3
from raceintel.config import V2Paths
from raceintel.model_lab import serving as SERVING
from raceintel.simulation import parameter_storage_dir

#: Frozen serving-model identity (same bytes the source preflight pins;
#: kept as a module constant so the serving layer needs no scripts import).
EXPECTED_SERVING_MODEL_SHA = (
    "1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4"
)

REPLAY_MANIFEST_REL = Path(
    "results/v2_replay/phase8_e2_cache_manifest_v1.json")
REPLAY_CHECKPOINTS_REL = Path("results/v2_replay/checkpoints")
EXPECTED_REPLAY_MANIFEST_VERSION = "phase8-e2-cache-manifest-v1"
EXPECTED_REPLAY_RACE_COUNT = 149
EXPECTED_REPLAY_CHECKPOINT_COUNT = 9644

EXPECTED_SIMULATION_PARAMETER_SET_ID = "phase6-r3-empirical"
EXPECTED_SIMULATION_THROUGH_SEASON = 2024

PROCESSED_ENTITIES: tuple[str, ...] = (
    "driver_lap_state_d9", "results", "races")
SERVED_SEASONS: tuple[int, ...] = tuple(range(2018, 2025))

NETWORK_ENV_VAR = "V2_ALLOW_NETWORK"

SERVICE_NAME = "f1-intelligence-v2"
WINNER_SEMANTICS = "INDEPENDENT_BINARY"
SERVING_YEARS = "2018-2024"


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _check_serving_model(root: Path) -> str | None:
    """None when ok, else a bounded failure code (no paths)."""
    path = root / SERVING.SERVING_ARTIFACT_REL
    if not path.is_file():
        return "missing_artifact"
    try:
        actual = _sha256_file(path)
    except OSError:
        return "unreadable_artifact"
    if actual != EXPECTED_SERVING_MODEL_SHA:
        return "sha_mismatch"
    return None


def _check_replay(root: Path) -> str | None:
    manifest_path = root / REPLAY_MANIFEST_REL
    if not manifest_path.is_file():
        return "missing_manifest"
    if not (root / REPLAY_CHECKPOINTS_REL).is_dir():
        return "missing_checkpoints"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError):
        return "manifest_invalid"
    if manifest.get("manifest_version") != EXPECTED_REPLAY_MANIFEST_VERSION:
        return "manifest_invalid"
    if manifest.get("race_count") != EXPECTED_REPLAY_RACE_COUNT:
        return "manifest_invalid"
    if manifest.get("checkpoint_count") != EXPECTED_REPLAY_CHECKPOINT_COUNT:
        return "manifest_invalid"
    model_identity = manifest.get("model_identity") or {}
    if model_identity.get("artifact_sha256") != EXPECTED_SERVING_MODEL_SHA:
        return "model_identity_mismatch"
    return None


def _check_explainability(root: Path) -> str | None:
    artifact = E3.default_artifact_path(V2Paths.from_root(root))
    if not artifact.is_file():
        return "missing_artifact"
    sidecar = artifact.with_name(artifact.stem + ".sha256")
    if not sidecar.is_file():
        return "missing_sidecar"
    try:
        expected = sidecar.read_text().strip().lower()
        actual = _sha256_file(artifact)
    except OSError:
        return "unreadable_artifact"
    if expected != actual:
        return "sha_mismatch"
    return None


def _check_simulation(root: Path) -> str | None:
    manifest_path = (
        parameter_storage_dir(root, EXPECTED_SIMULATION_THROUGH_SEASON)
        / "manifest.json")
    if not manifest_path.is_file():
        return "missing_manifest"
    try:
        manifest = json.loads(manifest_path.read_text())
    except (OSError, ValueError):
        return "manifest_invalid"
    if (manifest.get("parameter_set_id")
            != EXPECTED_SIMULATION_PARAMETER_SET_ID):
        return "manifest_invalid"
    if manifest.get("through_season") != EXPECTED_SIMULATION_THROUGH_SEASON:
        return "manifest_invalid"
    return None


def _check_processed_data(root: Path) -> str | None:
    processed = V2Paths.from_root(root).processed_dir
    for entity in PROCESSED_ENTITIES:
        for season in SERVED_SEASONS:
            matches = sorted(
                (processed / entity / f"season={season}").glob("*.parquet"))
            if not matches:
                return "missing_partition"
    return None


def _check_network_policy() -> str | None:
    if os.environ.get(NETWORK_ENV_VAR) == "1":
        return "network_ingestion_enabled"
    return None


def run_readiness_checks(root: Path | str | None = None) -> dict:
    """Run every check once (no caching); returns the readiness payload."""
    resolved = (Path(root).resolve() if root is not None
                else V2Paths.resolve().root)
    failures = {
        "serving_model": _check_serving_model(resolved),
        "replay": _check_replay(resolved),
        "explainability": _check_explainability(resolved),
        "simulation": _check_simulation(resolved),
        "processed_data": _check_processed_data(resolved),
        "network_policy": _check_network_policy(),
    }
    checks = {name: ("ok" if failure is None else failure)
              for name, failure in failures.items()}
    ready = all(failure is None for failure in failures.values())
    return {
        "status": "ready" if ready else "not_ready",
        "service": SERVICE_NAME,
        "model_sha_short": EXPECTED_SERVING_MODEL_SHA[:8],
        "winner_semantics": WINNER_SEMANTICS,
        "serving_years": SERVING_YEARS,
        "checks": checks,
    }


@functools.lru_cache(maxsize=32)
def _cached_readiness(root_str: str) -> dict:
    return run_readiness_checks(Path(root_str))


def get_readiness(root: Path | str | None = None) -> dict:
    """Cached readiness payload (bounded: one validation per root)."""
    resolved = (str(Path(root).resolve()) if root is not None
                else str(V2Paths.resolve().root))
    return _cached_readiness(resolved)


def reset_readiness_cache() -> None:
    """Clear the cached payload (tests; never used on the serving path)."""
    _cached_readiness.cache_clear()
