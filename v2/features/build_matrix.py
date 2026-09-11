"""F15 canonical model-ready feature matrix builder.

Assembly/materialization ONLY: combines frozen D9 state identities, the
84 registry-authorized predictive definitions (computed via the approved
batch calculators), and the F13 label layer into deterministic,
versioned, auditable Parquet + manifest.

No new feature, no new label, no model training, no split, no
imputation/encoding/scaling, no row sampling. Predictive columns come
from the feature registry; labels come from the label registry/builder.
"""

from __future__ import annotations

import argparse
import glob
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from v2.config import V2Paths
from v2.features import (
    FEATURE_SET_VERSION,
    PriorHistory,
    build_f11_registry,
    context_batch,
    environment_batch,
    gap_batch,
    interactions_batch,
    pace_batch,
    passthrough_batch,
    priors_batch,
    rates_batch,
)
from v2.features.contracts import FeatureStatus
from v2.labels import (
    LABEL_SET_VERSION,
    build_label_frame,
    build_label_registry,
    join_labels_for_f15,
)

#: Assembly/schema/materialization contract. Independent of feature and
#: label semantics; never implies a predictive feature change.
MATRIX_VERSION = "v1"

MATRIX_ENTITY = "model_matrix"

#: Exact-state identity: D9 PK + clock. `state_id` is derived metadata.
PK_COLUMNS = ("race_id", "driver_id", "lap_number")
IDENTITY_COLUMNS = ("race_id", "driver_id", "lap_number", "state_time_s")

METADATA_COLUMNS = (
    "race_id", "season", "round_no", "circuit_id", "driver_id",
    "constructor_id", "lap_number", "state_time_s", "state_id",
)

#: Non-predictive companion carried from the frozen label artifact so the
#: ordinal-eligibility indicator is reconstructible.
LABEL_COMPANION_COLUMNS = ("classified_flag",)

TASK_ELIGIBILITY_COLUMNS = (
    "eligible_is_winner",
    "eligible_is_podium",
    "eligible_scored_points",
    "eligible_ordinal_final_position",
    "eligible_gain_loss",
)

#: Phase-3 task contract: task -> (label column, eligibility mask column).
TASKS: dict = {
    "winner": ("is_winner", "eligible_is_winner"),
    "podium": ("is_podium", "eligible_is_podium"),
    "points": ("scored_points", "eligible_scored_points"),
    "final_position": ("final_position", "eligible_ordinal_final_position"),
    "gain": ("gains_position_by_finish", "eligible_gain_loss"),
    "loss": ("loses_position_by_finish", "eligible_gain_loss"),
}

CANONICAL_SORT = ("season", "round_no", "race_id", "state_time_s",
                  "lap_number", "driver_id")

_SOURCE_GLOBS = {
    "d9_states": "data/v2/processed/driver_lap_state_d9/season=*/*.parquet",
    "labels": "data/v2/processed/race_driver_labels/*/*.parquet",
    "hist_results": "data/v2/processed/hist_results/season=*/*.parquet",
    "hist_races": "data/v2/processed/hist_races/season=*/*.parquet",
    "results": "data/v2/processed/results/season=*/*.parquet",
    "races": "data/v2/processed/races/season=*/*.parquet",
    "pit_stops": "data/v2/processed/pit_stops/season=*/*.parquet",
}

_LABEL_DTYPES = {
    "final_position": "Int64",
    "is_winner": "boolean",
    "is_podium": "boolean",
    "scored_points": "boolean",
    "position_change_from_state": "Int64",
    "gains_position_by_finish": "boolean",
    "loses_position_by_finish": "boolean",
    "classified_flag": "boolean",
}

_METADATA_DTYPES = {
    "race_id": "object",
    "season": "Int64",
    "round_no": "Int64",
    "circuit_id": "object",
    "driver_id": "object",
    "constructor_id": "object",
    "lap_number": "Int64",
    "state_time_s": "float64",
    "state_id": "object",
}


class MatrixBuildError(RuntimeError):
    """Fatal F15 build failure: loud, no partial artifact."""


# ---------------------------------------------------------------------------
# Source loading + fingerprints
# ---------------------------------------------------------------------------

def _read_glob(paths: V2Paths, pattern: str) -> pd.DataFrame:
    files = sorted(glob.glob(str(paths.root / pattern)))
    if not files:
        raise MatrixBuildError(f"no source files for pattern {pattern}")
    return pd.concat([pd.read_parquet(f) for f in files], ignore_index=True)


def _fingerprint_glob(paths: V2Paths, pattern: str) -> dict:
    files = sorted(glob.glob(str(paths.root / pattern)))
    if not files:
        raise MatrixBuildError(f"no source files for pattern {pattern}")
    digest = hashlib.sha256()
    for f in files:
        p = Path(f)
        rel = paths.relative(p)
        digest.update(rel.encode("utf-8"))
        digest.update(hashlib.sha256(p.read_bytes()).digest())
    return {"files": len(files), "sha256": digest.hexdigest()}


def load_states(paths: V2Paths) -> pd.DataFrame:
    states = _read_glob(paths, _SOURCE_GLOBS["d9_states"])
    if len(states) != 189420:
        raise MatrixBuildError(
            f"D9 state row count {len(states)} != frozen 189420")
    if states.duplicated(list(PK_COLUMNS)).any():
        raise MatrixBuildError("duplicate D9 state identity")
    return states.reset_index(drop=True)


def load_history(paths: V2Paths) -> PriorHistory:
    return PriorHistory(
        _read_glob(paths, _SOURCE_GLOBS["hist_results"]),
        _read_glob(paths, _SOURCE_GLOBS["hist_races"]),
        _read_glob(paths, _SOURCE_GLOBS["results"]),
        _read_glob(paths, _SOURCE_GLOBS["races"]),
        _read_glob(paths, _SOURCE_GLOBS["pit_stops"]),
    )


def load_source_labels(paths: V2Paths) -> pd.DataFrame:
    labels = _read_glob(paths, _SOURCE_GLOBS["labels"])
    if len(labels) != 3458:
        raise MatrixBuildError(
            f"label row count {len(labels)} != frozen 3458")
    if labels.duplicated(["race_id", "driver_id"]).any():
        raise MatrixBuildError("duplicate race-driver label key")
    return labels.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Registry authority
# ---------------------------------------------------------------------------

def resolve_predictive_names(registry) -> list:
    """Registry-derived predictive feature list (never hand-written)."""
    if FEATURE_SET_VERSION != "v8":
        raise MatrixBuildError(
            f"FEATURE_SET_VERSION {FEATURE_SET_VERSION} != v8")
    defs = [d for d in registry if d.predictive_eligible]
    names = [d.name for d in defs]
    if len(names) != 84:
        raise MatrixBuildError(
            f"predictive feature count {len(names)} != 84")
    if len(set(names)) != len(names):
        raise MatrixBuildError("duplicate predictive feature names")
    if any(d.status is FeatureStatus.DEFERRED for d in defs):
        raise MatrixBuildError("deferred definition marked predictive")
    return names


def resolve_label_names() -> list:
    if LABEL_SET_VERSION != "v1":
        raise MatrixBuildError(
            f"LABEL_SET_VERSION {LABEL_SET_VERSION} != v1")
    lreg = build_label_registry()
    names = lreg.names()
    if len(names) != 7:
        raise MatrixBuildError(f"label count {len(names)} != 7")
    return names


# ---------------------------------------------------------------------------
# Feature computation DAG (batch, reuse-first)
# ---------------------------------------------------------------------------

def compute_family_frames(states: pd.DataFrame, history: PriorHistory,
                          registry) -> dict:
    """Compute every family batch exactly once; return by family.

    DAG:
      passthrough  <- D9 state
      pace         <- D9 state
      gap          <- D9 state
      environment  <- D9 state
      priors       <- history (H<R)
      context      <- pace basis + gap geometry (internal batch cache)
      rates        <- gap results + pace basis (internal batch cache)
      interactions <- merged approved primitive columns
    """
    frames: dict = {}
    frames["passthrough"] = passthrough_batch(states, registry)
    frames["pace"] = pace_batch(states)
    frames["gap"] = gap_batch(states)
    frames["environment"] = environment_batch(states)
    frames["context"] = context_batch(states)
    frames["rates"] = rates_batch(states)
    frames["priors"] = priors_batch(states, history)
    # interactions consume already-approved primitive columns only
    # (`position` arrives via passthrough; `grid_position` via priors).
    prims = states[list(IDENTITY_COLUMNS)].copy()
    for key in ("passthrough", "pace", "gap", "context", "rates", "priors"):
        prims = prims.merge(frames[key], on=list(IDENTITY_COLUMNS),
                            how="left", validate="one_to_one")
    frames["interactions"] = interactions_batch(prims)
    return frames


def _merge_family_frames(states: pd.DataFrame, frames: dict,
                         names: list) -> pd.DataFrame:
    out = states[list(IDENTITY_COLUMNS)].copy()
    for key in ("passthrough", "pace", "gap", "environment", "context",
                "rates", "priors", "interactions"):
        out = out.merge(frames[key], on=list(IDENTITY_COLUMNS), how="left",
                        validate="one_to_one")
    missing = [n for n in names if n not in out.columns]
    if missing:
        raise MatrixBuildError(f"predictive columns missing: {missing}")
    extra = [c for c in out.columns
             if c not in set(IDENTITY_COLUMNS) | set(names)]
    if extra:
        raise MatrixBuildError(f"unexpected predictive columns: {extra}")
    return out


# ---------------------------------------------------------------------------
# Column classes + casting
# ---------------------------------------------------------------------------

def _cast_predictive(frame: pd.DataFrame, registry) -> None:
    for d in registry:
        if not d.predictive_eligible:
            continue
        col = frame[d.name]
        if d.dtype == "int64":
            frame[d.name] = pd.to_numeric(col, errors="coerce").astype("Int64")
        elif d.dtype == "float64":
            frame[d.name] = pd.to_numeric(col, errors="coerce").astype("float64")
        elif d.dtype == "bool":
            frame[d.name] = col.astype("boolean")
        elif d.dtype == "string":
            frame[d.name] = col.astype("object")
        else:  # pragma: no cover - registry validates dtypes
            raise MatrixBuildError(f"bad registry dtype {d.dtype} for {d.name}")


def _materialize_state_labels(state_position: pd.Series,
                              label_frame: pd.DataFrame) -> pd.DataFrame:
    """F13 SPECIFIED state-dependent formulas, vectorized."""
    pos = pd.to_numeric(state_position, errors="coerce").astype("Int64")
    fp = label_frame["final_position"].astype("Int64")
    change = (pos - fp).astype("Int64")
    out = pd.DataFrame(index=label_frame.index)
    out["position_change_from_state"] = change
    out["gains_position_by_finish"] = change.gt(0).astype("boolean")
    out["loses_position_by_finish"] = change.lt(0).astype("boolean")
    return out


def _ordinal_eligible(classified_flag: pd.Series,
                      final_position: pd.Series) -> pd.Series:
    """Vectorized ordinal_training_eligible (F13/F14 contract)."""
    cf = classified_flag.astype("boolean")
    fp = final_position.astype("Int64")
    return (cf & fp.notna()).astype("boolean")


def _build_task_masks(label_frame: pd.DataFrame) -> pd.DataFrame:
    out = pd.DataFrame(index=label_frame.index)
    out["eligible_is_winner"] = label_frame["is_winner"].notna()
    out["eligible_is_podium"] = label_frame["is_podium"].notna()
    out["eligible_scored_points"] = label_frame["scored_points"].notna()
    out["eligible_ordinal_final_position"] = _ordinal_eligible(
        label_frame["classified_flag"], label_frame["final_position"])
    out["eligible_gain_loss"] = \
        label_frame["position_change_from_state"].notna()
    return out


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

def assemble_matrix(states: pd.DataFrame, history: PriorHistory,
                    source_labels: pd.DataFrame, registry,
                    validate: bool = True) -> tuple:
    predictive = resolve_predictive_names(registry)
    label_names = resolve_label_names()
    frames = compute_family_frames(states, history, registry)
    feat = _merge_family_frames(states, frames, predictive)

    # metadata (identity + grouping) with deterministic state_id
    meta = states[["race_id", "season", "round_no", "circuit_id",
                   "driver_id", "constructor_id", "lap_number",
                   "state_time_s"]].copy()
    meta["state_id"] = (meta["race_id"].astype(str) + "|"
                        + meta["driver_id"].astype(str) + "|"
                        + meta["lap_number"].astype("Int64").astype(str))

    # label layer from the approved builder + F15 state formulas
    label_frame, label_manifest = build_label_frame(source_labels)
    joined, join_report = join_labels_for_f15(
        states[list(IDENTITY_COLUMNS)].copy(), label_frame)
    if join_report["missing_label"] != 0:
        raise MatrixBuildError(
            f"label join left {join_report['missing_label']} states unmatched")
    if len(joined) != len(states):
        raise MatrixBuildError("label join changed state row count")
    state_labels = _materialize_state_labels(
        states["position"].reset_index(drop=True),
        joined.reset_index(drop=True))
    label_block = pd.concat(
        [joined.drop(columns=list(IDENTITY_COLUMNS)).reset_index(drop=True),
         state_labels], axis=1)
    label_block = label_block[list(_LABEL_DTYPES)]
    masks = _build_task_masks(label_block)

    # assemble in explicit class order
    matrix = pd.concat([meta.reset_index(drop=True),
                        feat[predictive].reset_index(drop=True),
                        label_block.reset_index(drop=True),
                        masks.reset_index(drop=True)], axis=1)
    for col, dt in _METADATA_DTYPES.items():
        matrix[col] = matrix[col].astype(dt)
    _cast_predictive(matrix, registry)
    for col, dt in _LABEL_DTYPES.items():
        matrix[col] = matrix[col].astype(dt)
    for col in TASK_ELIGIBILITY_COLUMNS:
        matrix[col] = matrix[col].astype("boolean")

    matrix = matrix.sort_values(list(CANONICAL_SORT),
                                kind="mergesort").reset_index(drop=True)

    manifest = _build_manifest(states, source_labels, registry, predictive,
                               label_names, label_manifest, matrix,
                               join_report)
    if validate:
        validate_matrix(matrix, manifest)
    return matrix, manifest


def _build_manifest(states, source_labels, registry, predictive,
                    label_names, label_manifest, matrix,
                    join_report) -> dict:
    labels_reg = build_label_registry()
    label_reg_hash = hashlib.sha256(
        json.dumps(labels_reg.to_dict(), sort_keys=True).encode("utf-8")
    ).hexdigest()
    nulls = {c: int(matrix[c].isna().sum()) for c in matrix.columns}
    manifest = {
        "matrix_version": MATRIX_VERSION,
        "matrix_entity": MATRIX_ENTITY,
        "feature_set_version": FEATURE_SET_VERSION,
        "feature_registry_fingerprint": registry.fingerprint(),
        "predictive_feature_count": len(predictive),
        "label_set_version": LABEL_SET_VERSION,
        "label_registry_fingerprint": label_reg_hash,
        "label_count": len(label_names),
        "row_count": int(len(matrix)),
        "race_count": int(matrix["race_id"].nunique()),
        "season_range": [int(matrix["season"].min()),
                         int(matrix["season"].max())],
        "column_count": int(matrix.shape[1]),
        "metadata_columns": list(METADATA_COLUMNS),
        "predictive_columns": list(predictive),
        "label_columns": list(label_names),
        "label_companion_columns": list(LABEL_COMPANION_COLUMNS),
        "task_eligibility_columns": list(TASK_ELIGIBILITY_COLUMNS),
        "task_contract": {k: list(v) for k, v in TASKS.items()},
        "canonical_sort": list(CANONICAL_SORT),
        "label_join": {"cardinality": "many_to_one",
                       **{k: int(v) for k, v in join_report.items()}},
        "source": {
            "d9_states": {"rows": int(len(states))},
            "race_driver_labels": {"rows": int(len(source_labels))},
        },
        "null_counts": nulls,
        "schema_hash": _schema_hash(matrix, predictive),
        "content_hash": content_hash(matrix),
    }
    return manifest


def content_hash(matrix: pd.DataFrame) -> str:
    """Deterministic semantic content hash over ordered rows + columns.

    Uses pandas row hashing on the canonically sorted frame (stable for
    fixed dtypes), never raw Parquet bytes (writer metadata unstable).
    """
    cols = sorted(matrix.columns)
    h = pd.util.hash_pandas_object(matrix[cols], index=False)
    return hashlib.sha256(h.to_numpy().tobytes()).hexdigest()


def _schema_hash(matrix: pd.DataFrame, predictive: list) -> str:
    schema = {
        "metadata": list(METADATA_COLUMNS),
        "predictive": list(predictive),
        "label": list(_LABEL_DTYPES),
        "task": list(TASK_ELIGIBILITY_COLUMNS),
        "dtypes": {c: str(matrix[c].dtype) for c in matrix.columns},
    }
    return hashlib.sha256(
        json.dumps(schema, sort_keys=True).encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_matrix(matrix: pd.DataFrame, manifest: dict,
                    expected_rows: int = 189420) -> None:
    predictive = manifest["predictive_columns"]
    labels = manifest["label_columns"]
    companions = manifest["label_companion_columns"]
    meta = manifest["metadata_columns"]
    if len(predictive) != 84:
        raise MatrixBuildError("predictive column count != 84")
    if len(labels) != 7:
        raise MatrixBuildError("label column count != 7")
    if len(set(matrix.columns)) != matrix.shape[1]:
        raise MatrixBuildError("duplicate output column names")
    if set(predictive) & (set(labels) | set(companions)):
        raise MatrixBuildError("feature/label name overlap")
    if set(predictive) & set(TASK_ELIGIBILITY_COLUMNS):
        raise MatrixBuildError("feature/task-mask name overlap")
    if (set(labels) | set(companions)) & set(TASK_ELIGIBILITY_COLUMNS):
        raise MatrixBuildError("label/task-mask name overlap")
    expected = set(meta) | set(predictive) | set(labels) \
        | set(companions) | set(TASK_ELIGIBILITY_COLUMNS)
    if set(matrix.columns) != expected:
        raise MatrixBuildError("unclassified output columns present")
    if len(matrix) != expected_rows:
        raise MatrixBuildError(
            f"matrix row count {len(matrix)} != {expected_rows}")
    if matrix.duplicated(list(PK_COLUMNS)).any():
        raise MatrixBuildError("duplicate matrix identity")
    if matrix["state_id"].duplicated().any():
        raise MatrixBuildError("duplicate state_id")
    for col in predictive + labels + companions:
        if matrix[col].isna().all():
            raise MatrixBuildError(f"unexpected all-null column {col}")
    for col in TASK_ELIGIBILITY_COLUMNS:
        vals = set(matrix[col].dropna().unique().tolist())
        if not vals <= {True, False}:
            raise MatrixBuildError(f"non-boolean task mask {col}")


# ---------------------------------------------------------------------------
# Atomic write / load
# ---------------------------------------------------------------------------

def output_dir(paths: V2Paths) -> Path:
    return paths.processed_dir / MATRIX_ENTITY / f"matrix_version={MATRIX_VERSION}"


def _portable_ref(paths: V2Paths, p: Path, out_dir: Path) -> str:
    """Project-relative when inside the repo; else relative to the output
    dir (never a machine-specific absolute path)."""
    try:
        return paths.relative(p)
    except ValueError:
        return p.relative_to(out_dir).as_posix()


def write_matrix(paths: V2Paths, matrix: pd.DataFrame, manifest: dict,
                 out_dir: Path | None = None) -> dict:
    out_dir = Path(out_dir) if out_dir else output_dir(paths)
    out_dir.mkdir(parents=True, exist_ok=True)
    pq = out_dir / "model_matrix.parquet"
    mf = out_dir / "manifest.json"
    tmp_pq = pq.with_suffix(".parquet.tmp")
    tmp_mf = mf.with_suffix(".json.tmp")
    try:
        matrix.to_parquet(tmp_pq, index=False)
        reloaded = pd.read_parquet(tmp_pq)
        if len(reloaded) != len(matrix) or list(reloaded.columns) != \
                list(matrix.columns):
            raise MatrixBuildError("written artifact failed reload check")
        os.replace(tmp_pq, pq)
        manifest = dict(manifest)
        manifest["artifact"] = {
            "parquet": _portable_ref(paths, pq, out_dir),
            "manifest": _portable_ref(paths, mf, out_dir),
            "parquet_bytes": int(pq.stat().st_size),
        }
        tmp_mf.write_text(json.dumps(manifest, indent=2, sort_keys=True)
                          + "\n")
        os.replace(tmp_mf, mf)
    except Exception:
        for p in (tmp_pq, tmp_mf):
            if p.exists():
                p.unlink()
        raise
    return manifest


def load_manifest(paths: V2Paths, out_dir: Path | None = None) -> dict:
    out_dir = Path(out_dir) if out_dir else output_dir(paths)
    return json.loads((out_dir / "manifest.json").read_text())


def load_matrix(paths: V2Paths, out_dir: Path | None = None) -> tuple:
    out_dir = Path(out_dir) if out_dir else output_dir(paths)
    return pd.read_parquet(out_dir / "model_matrix.parquet"), \
        load_manifest(paths, out_dir)


def load_features(paths: V2Paths, out_dir: Path | None = None,
                  metadata: bool = True) -> pd.DataFrame:
    """Select X explicitly from the manifest (never df.drop(labels))."""
    matrix, manifest = load_matrix(paths, out_dir)
    cols = list(manifest["predictive_columns"])
    if metadata:
        cols = list(manifest["metadata_columns"]) + cols
    return matrix[cols].copy()


def load_labels(paths: V2Paths, out_dir: Path | None = None) -> pd.DataFrame:
    matrix, manifest = load_matrix(paths, out_dir)
    cols = list(manifest["metadata_columns"]) \
        + list(manifest["label_columns"]) \
        + list(manifest["label_companion_columns"]) \
        + list(manifest["task_eligibility_columns"])
    return matrix[cols].copy()


def load_task(task: str, paths: V2Paths, out_dir: Path | None = None,
              with_metadata: bool = True) -> tuple:
    """Return (X, y, eligibility_mask) using the manifest.

    No split, no imputation, no encoding, no scaling, no rebalancing.
    The mask is the frozen eligibility contract; callers must not ignore
    it. Ordinal final-position uses ordinal_training_eligible, never
    final_position.notna().
    """
    if task not in TASKS:
        raise MatrixBuildError(f"unknown task {task!r}; known: {sorted(TASKS)}")
    matrix, manifest = load_matrix(paths, out_dir)
    label_col, mask_col = TASKS[task]
    if label_col not in manifest["label_columns"]:
        raise MatrixBuildError(f"task label {label_col} not in manifest")
    if mask_col not in manifest["task_eligibility_columns"]:
        raise MatrixBuildError(f"task mask {mask_col} not in manifest")
    cols = list(manifest["predictive_columns"])
    if with_metadata:
        cols = list(manifest["metadata_columns"]) + cols
    return matrix[cols].copy(), matrix[label_col].copy(), \
        matrix[mask_col].astype("boolean").copy()


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def build(paths: V2Paths, out_dir: Path | None = None,
          force: bool = False) -> dict:
    started = time.perf_counter()
    registry = build_f11_registry()
    if not force:
        try:
            existing = load_manifest(paths, out_dir)
            if (existing.get("feature_set_version") == FEATURE_SET_VERSION
                    and existing.get("label_set_version") == LABEL_SET_VERSION
                    and existing.get("row_count") == 189420):
                print("model matrix up to date (use --force to rebuild)")
                return existing
        except (FileNotFoundError, json.JSONDecodeError):
            pass
    source_fp = {k: _fingerprint_glob(paths, p)
                 for k, p in _SOURCE_GLOBS.items()}
    states = load_states(paths)
    history = load_history(paths)
    source_labels = load_source_labels(paths)
    matrix, manifest = assemble_matrix(states, history, source_labels,
                                       registry)
    manifest["source_fingerprints"] = source_fp
    manifest["build_seconds"] = round(time.perf_counter() - started, 3)
    manifest = write_matrix(paths, matrix, manifest, out_dir)
    return manifest


def _build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="python -m v2.features.build_matrix",
        description="Build the canonical F15 model-ready feature matrix")
    p.add_argument("--root", default=None)
    p.add_argument("--output", default=None)
    p.add_argument("--force", action="store_true")
    return p


def main(argv: list | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        paths = V2Paths.resolve(args.root)
        out = Path(args.output) if args.output else None
        manifest = build(paths, out, force=args.force)
        print(f"matrix rows        : {manifest['row_count']}")
        print(f"columns            : {manifest['column_count']}")
        print(f"predictive         : {manifest['predictive_feature_count']}")
        print(f"labels             : {manifest['label_count']}")
        print(f"matrix_version     : {manifest['matrix_version']}")
        print(f"content_hash       : {manifest['content_hash']}")
        if "artifact" in manifest:
            print(f"parquet bytes      : {manifest['artifact']['parquet_bytes']}")
        return 0
    except MatrixBuildError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
