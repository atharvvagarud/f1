"""Runtime environment preflight for the source tree (P10-1B).

Verifies SOFTWARE/runtime prerequisites, not science. Two modes map to
P10-1A's tree states::

    python scripts/check_runtime_environment.py --source
    python scripts/check_runtime_environment.py --deployable   # default

SOURCE mode checks tracked source/software declarations only (fresh-clone
state). DEPLOYABLE mode additionally requires a valid ``runtime_artifacts/``
staging bundle (via ``scripts/prepare_runtime_artifacts.py --validate``)
and a network-off serving posture (``V2_ALLOW_NETWORK`` must not be ``1``).

This script MUST stay stdlib-only: it must never import training code,
feature/matrix builders, simulation/replay builders, FastF1 ingestion, or
explainability computation. It hashes files, inspects versions, reads JSON,
checks tracked-path existence, and shells out to the P10-1A validator. It
does not install packages, start servers, download anything, regenerate
artifacts, load datasets, or run inference (model compatibility is proven
by SHA identity, not by loading the model).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

SUPPORTED_PYTHON_MAJOR = 3
SUPPORTED_PYTHON_MINOR = 11

EXPECTED_SERVING_MODEL_SHA = (
    "1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4"
)
SERVING_MODEL_REL = Path(
    "results/v2_model_lab/winner_logreg_raw_v1_serving.joblib")

PHASE9_EVIDENCE_RELS = (
    Path("frontend/data/models.v1.json"),
    Path("frontend/data/about.v1.json"),
)

V1_RESOURCE_RELS = (
    Path("data/processed"),
    Path("data/interim"),
    Path("results/models"),
)

FRONTEND_MANIFEST_RELS = (
    Path("frontend/package.json"),
    Path("frontend/package-lock.json"),
)

RUNTIME_STAGING_REL = Path("runtime_artifacts")
RUNTIME_MANIFEST_REL = RUNTIME_STAGING_REL / "manifest.json"

PREPARE_SCRIPT_REL = Path("scripts/prepare_runtime_artifacts.py")

NETWORK_ENV_VAR = "V2_ALLOW_NETWORK"

VALIDATOR_TIMEOUT_S = 300


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


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def check_source_tree(root: Path) -> list[str]:
    """Tracked source/software declarations only (fresh-clone state)."""
    errors: list[str] = []
    model = root / SERVING_MODEL_REL
    if not model.is_file():
        errors.append(
            f"missing tracked serving model {SERVING_MODEL_REL} "
            "(fresh clone must contain it; do NOT regenerate — investigate)")
    elif _sha256_file(model) != EXPECTED_SERVING_MODEL_SHA:
        errors.append(
            f"serving model {SERVING_MODEL_REL} SHA mismatch "
            "(frozen artifact identity violated — investigate, do NOT "
            "overwrite with a regenerated file)")
    for rel in PHASE9_EVIDENCE_RELS:
        if not (root / rel).is_file():
            errors.append(
                f"missing Phase-9 evidence {rel} "
                "(tracked; fresh clone must contain it)")
    for rel in V1_RESOURCE_RELS:
        if not (root / rel).is_dir():
            errors.append(
                f"missing V1 runtime resource {rel}/ "
                "(tracked; fresh clone must contain it)")
    for rel in FRONTEND_MANIFEST_RELS:
        if not (root / rel).is_file():
            errors.append(
                f"missing frontend manifest {rel} "
                "(run from the repository root or pass --root)")
    return errors


def run_artifact_validator(root: Path) -> list[str]:
    """Reuse the P10-1A validator; never duplicate its logic here."""
    script = root / PREPARE_SCRIPT_REL
    if not script.is_file():
        return [f"missing artifact packager {PREPARE_SCRIPT_REL}"]
    try:
        completed = subprocess.run(
            [sys.executable, str(script),
             "--validate", "--root", str(root)],
            capture_output=True, text=True, timeout=VALIDATOR_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return [f"artifact validator could not run: {exc}"]
    if completed.returncode != 0:
        tail = (completed.stderr or completed.stdout or "").strip()
        tail = "\n".join(tail.splitlines()[-5:]) if tail else "(no output)"
        return [
            "runtime_artifacts validation failed "
            f"(scripts/prepare_runtime_artifacts.py --validate exit "
            f"{completed.returncode}): {tail} — rebuild with "
            "`python scripts/prepare_runtime_artifacts.py`",
        ]
    return []


def check_network_posture() -> list[str]:
    """Production serving must be network-off (fail closed)."""
    if os.environ.get(NETWORK_ENV_VAR) == "1":
        return [
            f"{NETWORK_ENV_VAR}=1 is set: production serving must stay "
            "network-off (live ingestion opt-in is for offline CLIs only); "
            f"unset {NETWORK_ENV_VAR} before serving",
        ]
    return []


def check_deployable_tree(root: Path) -> list[str]:
    """Source checks plus staged-runtime requirements."""
    errors = check_source_tree(root)
    if not (root / RUNTIME_STAGING_REL).is_dir():
        errors.append(
            f"missing {RUNTIME_STAGING_REL}/ — run "
            "`python scripts/prepare_runtime_artifacts.py` to stage it")
    elif not (root / RUNTIME_MANIFEST_REL).is_file():
        errors.append(
            f"missing {RUNTIME_MANIFEST_REL} — re-run "
            "`python scripts/prepare_runtime_artifacts.py`")
    else:
        manifest_path = root / RUNTIME_MANIFEST_REL
        try:
            manifest = json.loads(manifest_path.read_text())
        except (OSError, ValueError) as exc:
            errors.append(f"unreadable {RUNTIME_MANIFEST_REL}: {exc}")
        else:
            if manifest.get("manifest_version") != "runtime-artifacts-v1":
                errors.append(
                    f"{RUNTIME_MANIFEST_REL} has unexpected "
                    "manifest_version — re-run "
                    "`python scripts/prepare_runtime_artifacts.py`")
            else:
                errors.extend(run_artifact_validator(root))
    errors.extend(check_network_posture())
    return errors


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Verify software/runtime prerequisites (no science).")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--source", action="store_true",
                      help="check tracked source declarations only")
    mode.add_argument("--deployable", action="store_true",
                      help="also require valid runtime_artifacts (default)")
    parser.add_argument("--root", default=None,
                        help="project root (default: script location)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve() if args.root else default_root()
    errors = check_python_version()
    if args.source:
        errors.extend(check_source_tree(root))
        mode = "SOURCE"
    else:
        errors.extend(check_deployable_tree(root))
        mode = "DEPLOYABLE"
    if errors:
        print(f"preflight {mode} FAIL ({len(errors)} problem(s)):", flush=True)
        for error in errors:
            print(f"  - {error}", flush=True)
        return 1
    print(f"preflight {mode} OK (root={root})", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
