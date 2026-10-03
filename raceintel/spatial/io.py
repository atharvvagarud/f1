"""Phase-12 spatial artifact + manifest file I/O (P12-2).

Thin file layer over the P12-1 pure contracts: crash-safe per-race
Parquet writes, deterministic manifest persistence, content/file hashing.
No FastF1, no predictive imports.
"""

from __future__ import annotations

import hashlib
import json
import os
import tempfile
from pathlib import Path

import pandas as pd

from raceintel.spatial import contracts as SC
from raceintel.spatial import manifest as SM
from raceintel.spatial import validation as V

MANIFEST_FILE = SC.SPATIAL_MANIFEST_FILENAME


def spatial_root(root: str | Path) -> Path:
    """Repository-rooted spatial data directory (generated, ignored)."""
    return Path(root) / "data" / SC.SPATIAL_ROOT_DIRNAME


def observations_dir(root: str | Path) -> Path:
    return spatial_root(root) / SC.OBSERVATIONS_SUBDIR


def manifests_dir(root: str | Path) -> Path:
    return spatial_root(root) / SC.MANIFESTS_SUBDIR


def artifact_path(root: str | Path, race_id: str) -> Path:
    return observations_dir(root) / SC.observations_filename(race_id)


def manifest_path(root: str | Path) -> Path:
    return manifests_dir(root) / MANIFEST_FILE


GEOMETRY_MANIFEST_FILE = "spatial_geometry_manifest.json"


def geometry_dir(root: str | Path) -> Path:
    return spatial_root(root) / SC.GEOMETRY_SUBDIR


def geometry_path(root: str | Path, race_id: str) -> Path:
    if not isinstance(race_id, str) or not race_id.strip():
        raise ValueError(f"race_id must be non-empty, got {race_id!r}")
    return geometry_dir(root) / f"{race_id}.json"


def geometry_manifest_path(root: str | Path) -> Path:
    return manifests_dir(root) / GEOMETRY_MANIFEST_FILE


def load_geometry_manifest(path: str | Path) -> dict:
    """Load the geometry manifest, or the empty P12-3 constructor."""
    from raceintel.spatial import geometry as G

    manifest_file = Path(path)
    if not manifest_file.exists():
        return G.new_geometry_manifest()
    record = json.loads(manifest_file.read_text(encoding="utf-8"))
    return G.validate_geometry_manifest(record)


def save_geometry_manifest(manifest: dict, path: str | Path) -> str:
    """Persist the geometry manifest deterministically (byte identity)."""
    from raceintel.spatial import geometry as G

    G.validate_geometry_manifest(manifest)
    ordered = {
        "manifest_schema_version": manifest["manifest_schema_version"],
        "geometry_schema_version": manifest["geometry_schema_version"],
        "algorithm_version": manifest["algorithm_version"],
        "races": {key: manifest["races"][key]
                  for key in sorted(manifest["races"])},
    }
    payload = (json.dumps(ordered, sort_keys=True, indent=2,
                          allow_nan=False) + "\n").encode("utf-8")
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()


def write_geometry_atomic(record: dict, path: str | Path) -> str:
    """Crash-safe geometry write: tmp sibling -> validate -> replace.

    Returns the canonical byte identity (sha256 of the persisted
    bytes). Tmp files never masquerade as completed artifacts.
    """
    from raceintel.spatial import geometry as G

    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = (json.dumps(record, sort_keys=True, indent=2,
                          allow_nan=False) + "\n").encode("utf-8")
    tmp = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=str(dest.parent), prefix=dest.stem + ".tmp-",
            suffix=".json")
        os.close(fd)
        tmp = Path(tmp_name)
        tmp.write_bytes(payload)
        reread = json.loads(tmp.read_text(encoding="utf-8"))
        G.validate_geometry(reread)
        if G.geometry_content_hash(reread) != record["content_sha256"]:
            raise ValueError(
                f"geometry round-trip changed logical content for "
                f"{dest.name}")
        file_hash = hashlib.sha256(payload).hexdigest()
        os.replace(tmp, dest)
        tmp = None
        return file_hash
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink()


def file_sha256(path: str | Path) -> str:
    """SHA-256 over file bytes (writer-environment identity, not science)."""
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_observations(path: str | Path) -> pd.DataFrame:
    """Read one per-race artifact with the contract engine (no index)."""
    return pd.read_parquet(path, engine=SC.PARQUET_ENGINE)


def write_observations_atomic(frame: pd.DataFrame,
                              path: str | Path) -> tuple[str, str]:
    """Crash-safe write: tmp sibling -> reopen/validate -> hash -> replace.

    Returns (logical_content_hash, file_sha256). The existing artifact at
    ``path`` is untouched until the replacement is validated. Tmp files
    never masquerade as completed artifacts (distinct suffix, same dir
    for atomic os.replace, cleaned on failure).
    """
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    logical = V.logical_content_hash(frame)
    tmp = None
    try:
        fd, tmp_name = tempfile.mkstemp(
            dir=str(dest.parent),
            prefix=dest.stem + ".tmp-",
            suffix=".parquet")
        os.close(fd)
        tmp = Path(tmp_name)
        frame.to_parquet(tmp, engine=SC.PARQUET_ENGINE,
                         compression=SC.PARQUET_COMPRESSION,
                         index=SC.PARQUET_WRITE_INDEX)
        reread = read_observations(tmp)
        V.validate_observations(reread)
        if V.logical_content_hash(reread) != logical:
            raise ValueError(
                f"parquet round-trip changed logical content for "
                f"{dest.name}")
        file_hash = file_sha256(tmp)
        os.replace(tmp, dest)
        tmp = None
        return logical, file_hash
    finally:
        if tmp is not None and tmp.exists():
            tmp.unlink()


def load_manifest(path: str | Path) -> dict:
    """Load the ingestion manifest, or the empty P12-1 constructor."""
    manifest_file = Path(path)
    if not manifest_file.exists():
        return SM.new_manifest()
    record = json.loads(manifest_file.read_text(encoding="utf-8"))
    return SM.validate_manifest(record)


def manifest_bytes(manifest: dict) -> bytes:
    """Canonical manifest bytes (sorted races + sorted keys)."""
    SM.validate_manifest(manifest)
    ordered = {
        "manifest_schema_version": manifest["manifest_schema_version"],
        "spatial_schema_version": manifest["spatial_schema_version"],
        "races": {key: manifest["races"][key]
                  for key in sorted(manifest["races"])},
    }
    return (json.dumps(ordered, sort_keys=True, indent=2,
                       allow_nan=False) + "\n").encode("utf-8")


def save_manifest(manifest: dict, path: str | Path) -> str:
    """Persist the manifest deterministically; return its byte identity."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    payload = manifest_bytes(manifest)
    dest.write_bytes(payload)
    return hashlib.sha256(payload).hexdigest()
