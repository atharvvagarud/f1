"""Deterministic result/config serialization + environment capture.

Generated runs live under the gitignored ``data/v2/model_lab/experiments``
tree, never inside Phase-2 artifact directories. Writes are atomic so a
killed run cannot leave a valid-looking partial JSON document.
"""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import tempfile
from pathlib import Path

from raceintel.config import V2Paths
from raceintel.model_lab.errors import ResultSchemaError
from raceintel.model_lab.experiment import (
    ExperimentConfig,
    ExperimentResult,
    validate_result,
)
from raceintel.model_lab.protocol import MODEL_LAB_PROTOCOL_VERSION

EXPERIMENTS_REL = "data/v2/model_lab/experiments"
PROTOCOL_DIR = f"protocol={MODEL_LAB_PROTOCOL_VERSION}"


def experiments_root(paths: V2Paths | None = None,
                     root: str | Path | None = None) -> Path:
    if root is not None:
        base = Path(root)
    elif paths is not None:
        base = paths.root
    else:
        base = V2Paths.resolve().root
    return base / EXPERIMENTS_REL / PROTOCOL_DIR


def experiment_dir(experiment_id: str, paths: V2Paths | None = None,
                   root: str | Path | None = None) -> Path:
    if not experiment_id:
        raise ResultSchemaError("experiment_id must be non-empty")
    return experiments_root(paths, root) / experiment_id


def atomic_write_text(path: str | Path, text: str) -> Path:
    """Write text atomically (tmp in same dir -> fsync -> replace)."""
    dest = Path(path)
    dest.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_name = tempfile.mkstemp(dir=str(dest.parent),
                                    prefix=f".{dest.name}.", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp_name, dest)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)
    return dest


def atomic_write_json(path: str | Path, payload: dict) -> Path:
    text = json.dumps(payload, indent=2, sort_keys=True) + "\n"
    return atomic_write_text(path, text)


def write_experiment(config: ExperimentConfig, result: ExperimentResult,
                     *, paths: V2Paths | None = None,
                     root: str | Path | None = None) -> Path:
    """Persist config.json + result.json under the experiment directory."""
    if result.experiment_id != config.experiment_id:
        raise ResultSchemaError(
            f"result experiment_id {result.experiment_id!r} != config "
            f"{config.experiment_id!r}")
    validate_result(result)
    dest = experiment_dir(config.experiment_id, paths, root)
    atomic_write_json(dest / "config.json", config.to_dict())
    atomic_write_json(dest / "result.json", result.to_dict())
    return dest


def read_experiment(directory: str | Path) -> tuple:
    """Round-trip read; rejects unknown schema versions."""
    directory = Path(directory)
    config = ExperimentConfig.from_dict(
        json.loads((directory / "config.json").read_text()))
    result = ExperimentResult.from_dict(
        json.loads((directory / "result.json").read_text()))
    return config, result


def environment_metadata(root: str | Path | None = None) -> dict:
    """Capture reproducibility-relevant environment facts (not identity)."""
    base = Path(root) if root is not None else V2Paths.resolve().root
    return {
        "python_version": sys.version.split()[0],
        "platform": platform.platform(),
        "system": platform.system(),
        "machine": platform.machine(),
        "processor": platform.processor(),
        "git_commit": _git(base, "rev-parse", "HEAD"),
        "git_dirty": bool(_git(base, "status", "--porcelain")),
    }


def _git(root: Path, *args) -> str | None:
    try:
        proc = subprocess.run(["git", *args], cwd=str(root),
                              capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    return proc.stdout.strip()
