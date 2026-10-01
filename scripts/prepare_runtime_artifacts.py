"""Stage the frozen V2 runtime-artifact bundle (P10-1A).

PACKAGER, not a builder of science. Copies already-validated generated
bytes into ``runtime_artifacts/`` and writes a deterministic manifest.
It never trains, refits, recalibrates, predicts, builds matrices,
generates replay predictions, estimates simulation parameters, computes
explainability, ingests data, or touches the network.

Stdlib only. Fails closed (nonzero exit) on any missing/mismatched input.

Usage:
    python scripts/prepare_runtime_artifacts.py [--root DIR] [--staging DIR]
    python scripts/prepare_runtime_artifacts.py --validate [--root DIR]
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Frozen contract constants (Phase 1-9 outputs; change requires a new phase).
# ---------------------------------------------------------------------------

MANIFEST_VERSION = "runtime-artifacts-v1"
BUNDLE_DIRNAME = "runtime_artifacts"
STAGING_TMP_SUFFIX = ".tmp"

SERVING_MODEL_REL = "results/v2_model_lab/winner_logreg_raw_v1_serving.joblib"
SERVING_MODEL_SHA256 = (
    "1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4"
)

EXPLAIN_REL = "results/v2_explainability/global_winner_logreg_v1.json"
EXPLAIN_SHA256 = (
    "bae84b614a6e9e176d5bb9c33b99dcaf4cba3f376333b0f075c828f73982939f"
)
EXPLAIN_SIDECAR_REL = "results/v2_explainability/global_winner_logreg_v1.sha256"

REPLAY_MANIFEST_REL = "results/v2_replay/phase8_e2_cache_manifest_v1.json"
REPLAY_MANIFEST_VERSION = "phase8-e2-cache-manifest-v1"
REPLAY_RACE_COUNT = 149
REPLAY_CHECKPOINT_COUNT = 9644
REPLAY_AGGREGATE_CORPUS_SHA256 = (
    "78a3c059888637fe83cc534d0eb7869b6d18e746724bb1ce0f03ee3b8ba96298"
)
REPLAY_MATRIX_SHA256 = (
    "b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3"
)
REPLAY_PHASE2_CONTENT_HASH = (
    "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db"
)
REPLAY_CHECKPOINTS_REL = "results/v2_replay/checkpoints"

SIM_MANIFEST_REL = (
    "data/v2/simulation/params/r3-v1__through-2024/manifest.json"
)
SIM_CONTRACT_VERSION = "r3-v1"
SIM_THROUGH_SEASON = 2024
SIM_SCIENTIFIC_HASH = (
    "4c2f85f08f1ce66cc6477982b2d5c97e9547f70927224b8e949ebe123ff3f140"
)
SIM_PARAMETER_SET_ID = "phase6-r3-empirical"

# Source-corpus identity anchors (read from existing manifests, never rebuilt).
MATRIX_MANIFEST_REL = (
    "data/v2/processed/model_matrix/matrix_version=v1/manifest.json"
)
MATRIX_CONTENT_HASH = (
    "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db"
)
MATRIX_FEATURE_ROWS = 189420

# Entities the serving path reads (api/v2_service.py + build_matrix globs).
REQUIRED_PROCESSED_ENTITIES = (
    "driver_lap_state_d9",
    "results",
    "races",
    "hist_results",
    "hist_races",
    "pit_stops",
)

# Generated trees copied verbatim into the bundle (relative to repo root).
STAGED_TREES = (
    "data/v2/processed",
    "data/v2/simulation/params/r3-v1__through-2024",
    REPLAY_CHECKPOINTS_REL,
)
# Generated single files copied verbatim (replay contract manifest +
# explainability artifact and its sha sidecar).
STAGED_FILES = (
    REPLAY_MANIFEST_REL,
    EXPLAIN_REL,
    EXPLAIN_SIDECAR_REL,
)

# Paths that must never appear in the bundle (prefix match, POSIX style).
FORBIDDEN_PREFIXES = (
    "data/raw",
    ".fastf1_cache",
    "data/v2/raw",
    "data/v2/model_lab",
    "data/v2/reports",
    "data/v2/strategy",
    "data/v2/simulation/validation",
    "results/analysis",
    "results/baselines",
    "results/comparisons",
    "results/debug",
    "results/data_quality",
    "results/v2_validation",
    "node_modules",
    "frontend/node_modules",
    "frontend/.next",
    ".next",
    "__pycache__",
    ".pytest_cache",
    ".git",
    "graphify-out",
)
FORBIDDEN_BASENAMES = (".env", ".env.local")

#: Generous staging guardrail: ~3x the expected ~155 MB bundle. Catches an
#: accidental 15 GB data/raw inclusion without imposing a tight byte budget.
MAX_TOTAL_BYTES = 512 * 1024 * 1024

SERVED_SEASONS = list(range(2018, 2025))


class ArtifactContractError(Exception):
    """Any packaging-contract violation (fail-closed signal)."""


def find_project_root(start: Path | None = None) -> Path:
    """Locate the repo root from this script's own location."""
    anchor = Path(__file__).resolve()
    for parent in (anchor.parent, *anchor.parents):
        if (parent / "raceintel").is_dir() and (parent / "data").is_dir():
            return parent
    raise ArtifactContractError(
        f"cannot locate project root from {anchor} (need raceintel/ + data/)")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_json(path: Path) -> dict:
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, ValueError) as exc:
        raise ArtifactContractError(
            f"unreadable JSON: {path}: {exc}") from exc
    if not isinstance(payload, dict):
        raise ArtifactContractError(
            f"expected JSON object: {path}")
    return payload


def _require_file(root: Path, rel: str) -> Path:
    path = root / rel
    if not path.is_file() or path.is_symlink():
        raise ArtifactContractError(f"missing required artifact: {rel}")
    return path


def check_source_tree(root: Path) -> dict:
    """Validate every required source artifact BEFORE copying. Pure reads."""
    root = root.resolve()
    identities: dict = {}

    # F. Tracked serving model: reference its SHA (never copied into bundle).
    model_path = _require_file(root, SERVING_MODEL_REL)
    model_sha = sha256_file(model_path)
    if model_sha != SERVING_MODEL_SHA256:
        raise ArtifactContractError(
            f"serving model SHA mismatch: {model_sha} != "
            f"{SERVING_MODEL_SHA256}")
    identities["serving_model_sha256"] = model_sha

    # E. Explainability artifact + sidecar agreement.
    explain_path = _require_file(root, EXPLAIN_REL)
    explain_sha = sha256_file(explain_path)
    if explain_sha != EXPLAIN_SHA256:
        raise ArtifactContractError(
            f"explainability SHA mismatch: {explain_sha} != "
            f"{EXPLAIN_SHA256}")
    sidecar_path = _require_file(root, EXPLAIN_SIDECAR_REL)
    sidecar = sidecar_path.read_text(encoding="utf-8").strip().split()
    if not sidecar or sidecar[0] != EXPLAIN_SHA256:
        raise ArtifactContractError(
            f"explainability sidecar mismatch: {sidecar_path}")
    explain_doc = load_json(explain_path)
    model_identity = explain_doc.get("model_identity", {})
    if model_identity.get("serving_artifact_sha256") != SERVING_MODEL_SHA256:
        raise ArtifactContractError(
            "explainability model_identity does not reference the frozen "
            "serving artifact SHA")
    if explain_doc.get("canonical_feature_count") != 84:
        raise ArtifactContractError("explainability canonical count != 84")
    if explain_doc.get("transformed_feature_count") != 106:
        raise ArtifactContractError("explainability transformed count != 106")
    if explain_doc.get("probability_semantics") != "INDEPENDENT_BINARY":
        raise ArtifactContractError(
            "explainability probability semantics changed")
    identities["explainability_sha256"] = explain_sha

    # D. Replay cache contract manifest.
    replay_manifest_path = _require_file(root, REPLAY_MANIFEST_REL)
    replay_manifest = load_json(replay_manifest_path)
    if replay_manifest.get("manifest_version") != REPLAY_MANIFEST_VERSION:
        raise ArtifactContractError("replay manifest version mismatch")
    if replay_manifest.get("race_count") != REPLAY_RACE_COUNT:
        raise ArtifactContractError(
            f"replay race_count {replay_manifest.get('race_count')} != "
            f"{REPLAY_RACE_COUNT}")
    if replay_manifest.get("checkpoint_count") != REPLAY_CHECKPOINT_COUNT:
        raise ArtifactContractError(
            f"replay checkpoint_count "
            f"{replay_manifest.get('checkpoint_count')} != "
            f"{REPLAY_CHECKPOINT_COUNT}")
    if (replay_manifest.get("aggregate_corpus_sha256")
            != REPLAY_AGGREGATE_CORPUS_SHA256):
        raise ArtifactContractError("replay aggregate corpus identity "
                                    "mismatch")
    if replay_manifest.get("matrix_sha256") != REPLAY_MATRIX_SHA256:
        raise ArtifactContractError("replay matrix identity mismatch")
    if (replay_manifest.get("phase2_content_hash")
            != REPLAY_PHASE2_CONTENT_HASH):
        raise ArtifactContractError("replay phase2 content hash mismatch")
    embedded_model = (replay_manifest.get("model_identity") or {})
    if embedded_model.get("artifact_sha256") != SERVING_MODEL_SHA256:
        raise ArtifactContractError(
            "replay manifest model identity does not reference the frozen "
            "serving artifact SHA")
    if embedded_model.get("feature_count") != 84:
        raise ArtifactContractError("replay manifest feature_count != 84")
    if embedded_model.get("transformed_dim") != 106:
        raise ArtifactContractError("replay manifest transformed_dim != 106")
    if (embedded_model.get("probability_semantics")
            != "INDEPENDENT_BINARY"):
        raise ArtifactContractError(
            "replay manifest probability semantics changed")
    races = replay_manifest.get("races")
    if not isinstance(races, list) or len(races) != REPLAY_RACE_COUNT:
        raise ArtifactContractError("replay manifest races list scope "
                                    "mismatch")
    manifest_checkpoints = sum(
        int(entry.get("checkpoint_count", -1)) for entry in races)
    if manifest_checkpoints != REPLAY_CHECKPOINT_COUNT:
        raise ArtifactContractError(
            f"replay per-race checkpoint sum {manifest_checkpoints} != "
            f"{REPLAY_CHECKPOINT_COUNT}")
    checkpoints_dir = root / REPLAY_CHECKPOINTS_REL
    if not checkpoints_dir.is_dir():
        raise ArtifactContractError(
            f"missing replay checkpoints dir: {REPLAY_CHECKPOINTS_REL}")
    checkpoint_files = sorted(
        p for p in checkpoints_dir.glob("*.json") if p.is_file())
    if len(checkpoint_files) != REPLAY_RACE_COUNT:
        raise ArtifactContractError(
            f"checkpoint files {len(checkpoint_files)} != "
            f"{REPLAY_RACE_COUNT}")
    manifest_ids = {str(entry.get("race_id")) for entry in races}
    file_ids = {p.stem for p in checkpoint_files}
    if manifest_ids != file_ids:
        raise ArtifactContractError(
            "checkpoint files do not match manifest race coverage")
    identities["replay_manifest_sha256"] = sha256_file(replay_manifest_path)

    # C. Simulation parameter bundle (single self-validating manifest).
    sim_manifest_path = _require_file(root, SIM_MANIFEST_REL)
    sim_manifest = load_json(sim_manifest_path)
    if (sim_manifest.get("parameter_contract_version")
            != SIM_CONTRACT_VERSION):
        raise ArtifactContractError("sim parameter contract version "
                                    "mismatch")
    if sim_manifest.get("through_season") != SIM_THROUGH_SEASON:
        raise ArtifactContractError("sim parameter season cutoff != 2024")
    if sim_manifest.get("scientific_hash") != SIM_SCIENTIFIC_HASH:
        raise ArtifactContractError("sim parameter scientific hash mismatch")
    if sim_manifest.get("parameter_set_id") != SIM_PARAMETER_SET_ID:
        raise ArtifactContractError("sim parameter set id mismatch")
    if sorted(sim_manifest.get("estimation_seasons", [])) != SERVED_SEASONS:
        raise ArtifactContractError("sim estimation seasons != 2018-2024")
    identities["simulation_manifest_sha256"] = sha256_file(sim_manifest_path)

    # B. Canonical V2 corpus: entity dirs present + frozen matrix identity.
    processed = root / "data" / "v2" / "processed"
    for entity in REQUIRED_PROCESSED_ENTITIES:
        entity_dir = processed / entity
        if not entity_dir.is_dir():
            raise ArtifactContractError(
                f"missing corpus entity dir: data/v2/processed/{entity}")
        if not any(entity_dir.rglob("*.parquet")):
            raise ArtifactContractError(
                f"no parquet files under data/v2/processed/{entity}")
    matrix_manifest_path = _require_file(root, MATRIX_MANIFEST_REL)
    matrix_manifest = load_json(matrix_manifest_path)
    if matrix_manifest.get("content_hash") != MATRIX_CONTENT_HASH:
        raise ArtifactContractError("matrix content hash mismatch")
    label_join = matrix_manifest.get("label_join", {})
    if int(label_join.get("feature_rows", -1)) != MATRIX_FEATURE_ROWS:
        raise ArtifactContractError(
            f"matrix feature_rows {label_join.get('feature_rows')} != "
            f"{MATRIX_FEATURE_ROWS}")
    identities["matrix_manifest_sha256"] = sha256_file(matrix_manifest_path)
    identities["matrix_content_hash"] = MATRIX_CONTENT_HASH

    return identities


def _assert_safe_rel(rel_posix: str) -> None:
    if not rel_posix or rel_posix.startswith("/") or ".." in rel_posix.split(
            "/"):
        raise ArtifactContractError(f"unsafe relative path: {rel_posix!r}")
    for prefix in FORBIDDEN_PREFIXES:
        if rel_posix == prefix or rel_posix.startswith(prefix + "/"):
            raise ArtifactContractError(
                f"forbidden path in bundle: {rel_posix!r}")
    if Path(rel_posix).name in FORBIDDEN_BASENAMES:
        raise ArtifactContractError(
            f"forbidden basename in bundle: {rel_posix!r}")


def collect_staged_paths(root: Path) -> list[str]:
    """Enumerate exactly the allowlisted generated paths (deterministic)."""
    collected: list[str] = []
    for tree in STAGED_TREES:
        base = root / tree
        if not base.is_dir():
            raise ArtifactContractError(f"missing source tree: {tree}")
        for path in sorted(base.rglob("*")):
            if path.is_symlink():
                raise ArtifactContractError(
                    f"symlink refused in source tree: {path}")
            if path.is_file():
                rel = path.relative_to(root).as_posix()
                _assert_safe_rel(rel)
                collected.append(rel)
    for rel in STAGED_FILES:
        path = root / rel
        if not path.is_file() or path.is_symlink():
            raise ArtifactContractError(f"missing staged file: {rel}")
        _assert_safe_rel(rel)
        collected.append(rel)
    return sorted(set(collected))


def stage_tree(root: Path, dest: Path, rels: list[str]) -> list[dict]:
    """Copy allowlisted files into dest, returning sorted file records."""
    records: list[dict] = []
    for rel in rels:
        src = root / rel
        target = dest / rel
        if not src.is_file() or src.is_symlink():
            raise ArtifactContractError(f"source vanished: {rel}")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, target)
        records.append({
            "path": rel,
            "sha256": sha256_file(target),
            "size": target.stat().st_size,
        })
    records.sort(key=lambda record: record["path"])
    return records


def build_manifest(root: Path, records: list[dict], identities: dict) -> dict:
    total_bytes = sum(record["size"] for record in records)
    by_class: dict = {}
    for record in records:
        rel = record["path"]
        if rel.startswith("data/v2/processed/"):
            cls = "A/canonical-v2-serving-corpus"
        elif rel.startswith("data/v2/simulation/params/"):
            cls = "B/simulation-parameter-bundle"
        elif rel.startswith("results/v2_replay/"):
            cls = "C/replay-prediction-cache"
        elif rel.startswith("results/v2_explainability/"):
            cls = "D/global-explainability-artifact"
        else:  # pragma: no cover - allowlist makes this unreachable
            raise ArtifactContractError(f"unclassified staged path: {rel}")
        entry = by_class.setdefault(cls, {
            "file_count": 0, "size_bytes": 0, "paths": []})
        entry["file_count"] += 1
        entry["size_bytes"] += record["size"]
        entry["paths"].append(rel)
    for entry in by_class.values():
        entry["paths"].sort()
    return {
        "manifest_version": MANIFEST_VERSION,
        "project_phase": "phase10-p10-1a",
        "serving_scope": {
            "seasons": SERVED_SEASONS,
            "served_races": REPLAY_RACE_COUNT,
            "prediction_checkpoints": REPLAY_CHECKPOINT_COUNT,
        },
        "artifact_classes": by_class,
        "file_count": len(records),
        "total_bytes": total_bytes,
        "files": records,
        "scientific_identities": {
            "serving_model_sha256": identities["serving_model_sha256"],
            "explainability_sha256": identities["explainability_sha256"],
            "replay_aggregate_corpus_sha256":
                REPLAY_AGGREGATE_CORPUS_SHA256,
            "replay_matrix_sha256": REPLAY_MATRIX_SHA256,
            "replay_phase2_content_hash": REPLAY_PHASE2_CONTENT_HASH,
            "matrix_content_hash": MATRIX_CONTENT_HASH,
            "matrix_feature_rows": MATRIX_FEATURE_ROWS,
            "simulation_scientific_hash": SIM_SCIENTIFIC_HASH,
            "simulation_contract": (
                f"{SIM_CONTRACT_VERSION}.{SIM_THROUGH_SEASON}."
                f"{SIM_SCIENTIFIC_HASH[:12]}"
            ),
            "matrix_manifest_sha256": identities["matrix_manifest_sha256"],
            "replay_manifest_sha256": identities["replay_manifest_sha256"],
            "simulation_manifest_sha256":
                identities["simulation_manifest_sha256"],
        },
        "required_tracked_artifacts": [
            {"path": SERVING_MODEL_REL,
             "sha256": identities["serving_model_sha256"]},
        ],
        "validation_contract": {
            "replay_manifest_version": REPLAY_MANIFEST_VERSION,
            "max_total_bytes": MAX_TOTAL_BYTES,
            "forbidden_prefixes": list(FORBIDDEN_PREFIXES),
        },
    }


def write_manifest_deterministic(staging: Path, manifest: dict) -> Path:
    path = staging / "manifest.json"
    text = json.dumps(manifest, indent=2, sort_keys=True) + "\n"
    path.write_text(text, encoding="utf-8")
    return path


def validate_staged(root: Path, staging: Path) -> dict:
    """Validation-only gate over an existing staging tree. Pure reads."""
    root = root.resolve()
    staging = staging.resolve()
    manifest_path = staging / "manifest.json"
    if not manifest_path.is_file():
        raise ArtifactContractError("staging manifest.json missing")
    manifest = load_json(manifest_path)
    if manifest.get("manifest_version") != MANIFEST_VERSION:
        raise ArtifactContractError("staging manifest version mismatch")

    records = manifest.get("files")
    if not isinstance(records, list) or not records:
        raise ArtifactContractError("staging manifest has no file records")
    seen: set[str] = set()
    total = 0
    for record in records:
        rel = record.get("path", "")
        if not isinstance(rel, str):
            raise ArtifactContractError("non-string path in manifest")
        _assert_safe_rel(rel)
        if rel in seen:
            raise ArtifactContractError(f"duplicate manifest entry: {rel}")
        seen.add(rel)
        staged = staging / rel
        if not staged.is_file() or staged.is_symlink():
            raise ArtifactContractError(f"staged file missing: {rel}")
        if staged.resolve() != staged:
            raise ArtifactContractError(f"staged path escapes: {rel}")
        actual_sha = sha256_file(staged)
        if actual_sha != record.get("sha256"):
            raise ArtifactContractError(f"staged SHA mismatch: {rel}")
        if staged.stat().st_size != record.get("size"):
            raise ArtifactContractError(f"staged size mismatch: {rel}")
        total += staged.stat().st_size
    if total != manifest.get("total_bytes"):
        raise ArtifactContractError("staging total_bytes mismatch")
    if total > MAX_TOTAL_BYTES:
        raise ArtifactContractError(
            f"staging total {total} exceeds guardrail {MAX_TOTAL_BYTES}")

    # No symlinks, no env files, no git metadata anywhere in the bundle.
    for path in staging.rglob("*"):
        if path.is_symlink():
            raise ArtifactContractError(
                f"symlink in staging: {path.relative_to(staging)}")
        if path.is_file() and path.name in FORBIDDEN_BASENAMES:
            raise ArtifactContractError(
                f"env file in staging: {path.relative_to(staging)}")
    if (staging / ".git").exists():
        raise ArtifactContractError("git metadata in staging")

    # Identity anchors re-verified against the frozen contract.
    scientific = manifest.get("scientific_identities", {})
    expected = {
        "serving_model_sha256": SERVING_MODEL_SHA256,
        "explainability_sha256": EXPLAIN_SHA256,
        "replay_aggregate_corpus_sha256": REPLAY_AGGREGATE_CORPUS_SHA256,
        "matrix_content_hash": MATRIX_CONTENT_HASH,
        "simulation_scientific_hash": SIM_SCIENTIFIC_HASH,
    }
    for key, value in expected.items():
        if scientific.get(key) != value:
            raise ArtifactContractError(f"staging identity mismatch: {key}")

    # Tracked-model dependency: the live file must still match.
    live_sha = sha256_file(_require_file(root, SERVING_MODEL_REL))
    if live_sha != scientific.get("serving_model_sha256"):
        raise ArtifactContractError(
            "tracked serving model drifted from staging manifest")

    scope = manifest.get("serving_scope", {})
    if (scope.get("served_races") != REPLAY_RACE_COUNT
            or scope.get("prediction_checkpoints")
            != REPLAY_CHECKPOINT_COUNT):
        raise ArtifactContractError("staging serving scope mismatch")
    return manifest


def resolve_staging(root: Path, override: str | None) -> Path:
    staging = Path(override).resolve() if override else (
        root / BUNDLE_DIRNAME)
    staging = staging.resolve()
    if staging == root:
        raise ArtifactContractError("staging must not be the project root")
    try:
        staging.relative_to(root)
    except ValueError as exc:
        raise ArtifactContractError(
            "staging must live inside the project root") from exc
    for protected in ("data", "results", "frontend", "tests", "api", "raceintel"):
        if staging == (root / protected) or (
                root / protected) in staging.parents:
            raise ArtifactContractError(
                f"staging must not overlap canonical tree: {protected}")
    return staging


def package(root: Path, staging: Path) -> dict:
    """Full packager run: validate sources, stage to tmp, validate, swap."""
    tmp = staging.parent / (staging.name + STAGING_TMP_SUFFIX)
    if tmp.resolve() == root.resolve():
        raise ArtifactContractError("staging tmp collides with project root")
    identities = check_source_tree(root)
    rels = collect_staged_paths(root)
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    try:
        records = stage_tree(root, tmp, rels)
        manifest = build_manifest(root, records, identities)
        write_manifest_deterministic(tmp, manifest)
        validate_staged(root, tmp)
    except BaseException:
        shutil.rmtree(tmp, ignore_errors=True)
        raise
    if staging.exists():
        backup = staging.parent / (staging.name + ".prev")
        if backup.exists():
            shutil.rmtree(backup)
        os.replace(staging, backup)
        try:
            os.replace(tmp, staging)
        except BaseException:
            os.replace(backup, staging)
            raise
        shutil.rmtree(backup, ignore_errors=True)
    else:
        os.replace(tmp, staging)
    return validate_staged(root, staging)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Stage frozen V2 runtime artifacts (packager only).")
    parser.add_argument("--root", default=None,
                        help="project root (default: auto-detect)")
    parser.add_argument("--staging", default=None,
                        help="staging dir (default: <root>/runtime_artifacts)")
    parser.add_argument("--validate", action="store_true",
                        help="validation-only mode over existing staging")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = Path(args.root).resolve() if args.root else find_project_root()
    staging = resolve_staging(root, args.staging)
    try:
        if args.validate:
            manifest = validate_staged(root, staging)
            print(f"VALID staging={staging} "
                  f"files={manifest['file_count']} "
                  f"bytes={manifest['total_bytes']}")
        else:
            manifest = package(root, staging)
            print(f"STAGED staging={staging} "
                  f"files={manifest['file_count']} "
                  f"bytes={manifest['total_bytes']}")
    except ArtifactContractError as exc:
        print(f"CONTRACT FAILURE: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
