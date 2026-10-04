"""V3.1B deterministic dynamics matrix builder (no training, no metrics).

Reads the frozen F15 matrix (parent identity verified) plus D9 source
fields, runs the per-race sweep + per-driver assembly from
``calculators``, and writes the sidecar artifact atomically with
provenance. Label-blind: label/mask columns are never read.
"""

from __future__ import annotations

import hashlib
import json
import subprocess
import time
from pathlib import Path

import numpy as np
import pandas as pd

from raceintel.config import V2Paths
from raceintel.features import build_matrix as F15
from raceintel.features.dynamics import calculators as calc
from raceintel.features.dynamics.contract import (
    ALL_DEFINITIONS,
    CONTRACT_VERSION,
    contract_hash,
    feature_set_names,
)
from raceintel.features.dynamics import validation as V
from raceintel.features.pace import pace_eligibility_mask
from raceintel.storage import atomic_write_parquet

#: V3.1 dynamics artifact identity.
DYNAMICS_SCHEMA_VERSION = "v3.1b-sidecar-v1"
DYNAMICS_ENTITY = "race_dynamics"
DYNAMICS_FILE = "dynamics_sidecar.parquet"
PROVENANCE_FILE = "provenance.json"

#: D9 source columns joined onto matrix rows (never labels/masks).
D9_JOIN_COLUMNS = (
    "race_id", "driver_id", "lap_number", "lap_time_s", "pit_in_s",
    "pit_out_s", "stint_number",
)

#: Frozen matrix columns consumed as causal per-row trajectory inputs.
MATRIX_INPUT_COLUMNS = (
    "position", "track_state",
    "gap_to_leader_seconds", "gap_to_leader_seconds_valid",
    "gap_to_ahead_seconds", "gap_to_ahead_seconds_valid",
    "pace_median_3", "pace_median_5",
    "relative_pace_to_field_median_s_per_lap",
    "relative_pace_to_car_ahead_s_per_lap",
    "in_traffic_2s", "laps_since_last_pit_stop", "stint_lap",
)

IDENTITY_KEY = "state_id"


def _is_na(v) -> bool:
    try:
        return v is None or (isinstance(v, float) and np.isnan(v)) or \
            pd.isna(v)
    except (TypeError, ValueError):
        return False


def _fnum(v):
    if _is_na(v):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _fbool(v):
    if _is_na(v):
        return None
    return bool(v)


def _fint(v):
    if _is_na(v):
        return None
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def parquet_path(paths) -> Path:
    """Frozen F15 parquet location (bytes-hashed, never content-inferred)."""
    return F15.output_dir(paths) / "model_matrix.parquet"


def sha256_file(path: Path) -> str:
    """Streaming sha256 over file bytes (no wall-clock, no identity)."""
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_inputs(root=None):
    """Load + verify frozen parent matrix and D9 source fields."""
    paths = V2Paths.resolve(root)
    matrix, manifest = F15.load_matrix(paths)
    content = F15.content_hash(matrix)
    V.check_parent_identities(content, sha256_file(parquet_path(paths)))
    if content != V.EXPECTED_PARENT_CONTENT:
        raise V.DynamicsValidationError(
            f"recomputed parent content {content} != frozen")
    states = F15.load_states(paths)
    missing = [c for c in D9_JOIN_COLUMNS if c not in states.columns]
    if missing:
        raise V.DynamicsValidationError(
            f"D9 join columns missing: {missing}")
    return paths, matrix, manifest, states


def build_points(matrix: pd.DataFrame, states: pd.DataFrame) -> pd.DataFrame:
    """Join D9 source fields onto matrix rows; validate 1:1 coverage."""
    d9 = states[list(D9_JOIN_COLUMNS)].copy()
    if d9.duplicated(subset=["race_id", "driver_id", "lap_number"]).any():
        raise V.DynamicsValidationError("duplicate D9 join keys")
    m = matrix.copy()
    joined = m.merge(d9, on=["race_id", "driver_id", "lap_number"],
                     how="left", validate="many_to_one",
                     indicator=True)
    unmatched = joined[joined["_merge"] != "both"]
    if len(unmatched):
        raise V.DynamicsValidationError(
            f"{len(unmatched)} matrix rows lack D9 source fields")
    return joined.drop(columns=["_merge"])


def _points_for_race(frame: pd.DataFrame) -> tuple[list, list]:
    """Per-row sweep inputs (time order) for one race frame."""
    frame = frame.sort_values(["state_time_s", "lap_number", "driver_id"],
                              kind="mergesort")
    rows = []
    for r in frame.itertuples(index=False):
        d = r._asdict()
        rows.append({
            "key": d[IDENTITY_KEY],
            "driver": str(d["driver_id"]), "lap": int(d["lap_number"]),
            "t": float(d["state_time_s"]),
            "pos": None if _is_na(d.get("position")) else d.get("position"),
            "track": None if _is_na(d.get("track_state"))
            else str(d.get("track_state")),
            "gL_sec": _fnum(d.get("gap_to_leader_seconds")),
            "gL_valid": None if _is_na(
                d.get("gap_to_leader_seconds_valid")) else bool(
                    d.get("gap_to_leader_seconds_valid")),
        })
    swept = calc.sweep_race(rows)
    return rows, swept


def _assemble_race_points(frame: pd.DataFrame, rows: list,
                          swept: list) -> dict:
    """Full POINT_KEYS dicts per state_id for one race frame."""
    by_key = {}
    sval = {r["key"]: (r, s) for r, s in zip(rows, swept)}
    # pace eligibility over the race D9 frame (frozen predicate)
    elig = pace_eligibility_mask(frame)
    elig_by_key = dict(zip(frame[IDENTITY_KEY].astype(str), elig))
    for _, row in frame.iterrows():
        key = str(row[IDENTITY_KEY])
        r, s = sval[key]
        by_key[key] = {
            "lap": r["lap"], "t": r["t"],
            "pos": None if _is_na(row.get("position")) else row["position"],
            "track": r["track"],
            "pit_in": not _is_na(row.get("pit_in_s")),
            "pit_out": not _is_na(row.get("pit_out_s")),
            "elig": bool(elig_by_key.get(key, False)),
            "lt": _fnum(row.get("lap_time_s")),
            "gL_sec": _fnum(row.get("gap_to_leader_seconds")),
            "gL_valid": _fbool(row.get("gap_to_leader_seconds_valid")),
            "gL_ref": s["gL_ref"],
            "gA_sec": _fnum(row.get("gap_to_ahead_seconds")),
            "gA_valid": _fbool(row.get("gap_to_ahead_seconds_valid")),
            "gA_ref": s["gA_ref"],
            "b_ref": s["b_ref"], "b_F": s["b_F"], "b_Fl": s["b_Fl"],
            "b_predF": s["b_predF"], "b_red": s["b_red"],
            "pace_m3": _fnum(row.get("pace_median_3")),
            "pace_m5": _fnum(row.get("pace_median_5")),
            "rel_field": _fnum(row.get(
                "relative_pace_to_field_median_s_per_lap")),
            "rel_ahead": _fnum(row.get(
                "relative_pace_to_car_ahead_s_per_lap")),
            "traffic": _fbool(row.get("in_traffic_2s")),
            "laps_since": _fint(row.get("laps_since_last_pit_stop")),
            "stint_no": _fint(row.get("stint_number")),
            "stint_lap": _fint(row.get("stint_lap")),
            "spread": s["spread"], "spread_n": s["spread_n"],
            "driver": str(row["driver_id"]),
        }
    return by_key


def build_sidecar(joined: pd.DataFrame) -> pd.DataFrame:
    """Full sidecar frame: identity + 29 dynamics columns (matrix order)."""
    names = list(feature_set_names("all"))
    records: dict = {}
    for race_id, frame in joined.groupby("race_id", sort=False):
        rows, swept = _points_for_race(frame)
        points = _assemble_race_points(frame, rows, swept)
        by_driver: dict = {}
        for key, p in points.items():
            by_driver.setdefault(p["driver"], []).append((key, p))
        for driver, kl in by_driver.items():
            kl.sort(key=lambda kp: (float(kp[1]["t"]), int(kp[1]["lap"])))
            assembled = calc.assemble_driver([p for _, p in kl],
                                             driver=driver)
            for (lap, vals), (key, _) in zip(assembled, kl):
                records[key] = vals
    missing = [k for k in joined[IDENTITY_KEY].astype(str)
               if k not in records]
    if missing:
        raise V.DynamicsValidationError(
            f"{len(missing)} rows without dynamics assembly")
    out = pd.DataFrame(
        [{IDENTITY_KEY: k, **records[k]} for k in
         joined[IDENTITY_KEY].astype(str)],
        columns=[IDENTITY_KEY] + names)
    # canonical dtypes: float64 / boolean / int64 (contract, no inference).
    # Logical int64 with contracted nullability stores pandas-Int64
    # (repo precedent); non-nullable counts store plain int64.
    nullable_of = {d.name: d.nullable for d in ALL_DEFINITIONS}
    for d in ALL_DEFINITIONS:
        if d.dtype == "float64":
            out[d.name] = pd.to_numeric(out[d.name], errors="coerce"
                                        ).astype("float64")
        elif d.dtype == "bool":
            out[d.name] = out[d.name].astype("boolean")
        elif d.dtype == "int64":
            conv = pd.to_numeric(out[d.name], errors="coerce")
            out[d.name] = conv.astype("Int64" if nullable_of[d.name]
                                      else "int64")
    return out


def content_hash(frame: pd.DataFrame) -> str:
    """Deterministic logical content hash (state_id-ordered, by value)."""
    ordered = frame.sort_values([IDENTITY_KEY], kind="mergesort")
    cols = sorted(ordered.columns)
    h = pd.util.hash_pandas_object(ordered[cols], index=False)
    return hashlib.sha256(h.to_numpy().tobytes()).hexdigest()


def default_out_dir(root=None) -> Path:
    """Generated-data home (git-ignored): data/v3/race_dynamics/."""
    paths = V2Paths.resolve(root)
    return paths.root / "data" / "v3" / DYNAMICS_ENTITY


def build(root=None, out_dir=None, verify_parent: bool = True) -> dict:
    """End-to-end deterministic build; returns paths + provenance."""
    t0 = time.perf_counter()
    paths = V2Paths.resolve(root)
    matrix, manifest = F15.load_matrix(paths)
    t_load = time.perf_counter()
    if verify_parent:
        content = F15.content_hash(matrix)
        V.check_parent_identities(content,
                                  sha256_file(parquet_path(paths)))
    states = F15.load_states(paths)
    joined = build_points(matrix, states)
    t_join = time.perf_counter()
    sidecar = build_sidecar(joined)
    t_build = time.perf_counter()
    V.check_row_identity(sidecar)
    V.check_frame_schema(sidecar,
                         list(feature_set_names("all")))
    V.check_values(sidecar, list(feature_set_names("all")))
    # anti-join both directions against the frozen matrix
    mkeys = set(matrix[IDENTITY_KEY].astype(str))
    skeys = set(sidecar[IDENTITY_KEY].astype(str))
    if mkeys != skeys:
        raise V.DynamicsValidationError(
            f"join mismatch: matrix-only={len(mkeys - skeys)}, "
            f"sidecar-only={len(skeys - mkeys)}")
    digest = content_hash(sidecar)
    dest = Path(out_dir) if out_dir else default_out_dir(paths.root)
    dest.mkdir(parents=True, exist_ok=True)
    atomic_write_parquet(sidecar, dest / DYNAMICS_FILE)
    try:
        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=str(paths.root)).stdout.strip()
    except Exception:
        commit = "unknown"
    provenance = {
        "dynamics_schema_version": DYNAMICS_SCHEMA_VERSION,
        "contract_version": CONTRACT_VERSION,
        "contract_sha": contract_hash(),
        "parent_content_sha": F15.content_hash(matrix),
        "parent_parquet_sha": sha256_file(parquet_path(paths)),
        "parent_matrix_version": manifest.get("matrix_version"),
        "row_count": len(sidecar),
        "feature_count": len(feature_set_names("all")),
        "feature_names": list(feature_set_names("all")),
        "feature_sets": {
            "V3_1_DYNAMICS_CORE":
                list(feature_set_names("core")),
            "V3_1_DYNAMICS_VARIANT_A":
                list(feature_set_names("variant_a")),
            "V3_1_DYNAMICS": list(feature_set_names("all")),
        },
        "logical_content_sha": digest,
        "code_commit": commit,
        "season_coverage": sorted(int(s) for s in
                                  matrix["season"].unique()),
        "label_blind": True,
        "timings_s": {
            "load": round(t_load - t0, 3),
            "join": round(t_join - t_load, 3),
            "build": round(t_build - t_join, 3),
            "validate_write": round(time.perf_counter() - t_build, 3),
        },
    }
    (dest / PROVENANCE_FILE).write_text(
        json.dumps(provenance, indent=2, sort_keys=True) + "\n")
    return {"sidecar": str(dest / DYNAMICS_FILE),
            "provenance": str(dest / PROVENANCE_FILE),
            "provenance_record": provenance}
