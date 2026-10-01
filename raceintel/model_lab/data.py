"""Canonical read-only matrix access for the Model Lab.

One validated loader over the frozen F15 artifact. It verifies version,
counts and (optionally) hashes, preserves canonical order, exposes identity /
predictive / label / task-mask columns and a raw dtype schema, and never
mutates the source. Feature selection always goes through the F16
``resolve_feature_set`` contract; raw dataframe column dropping is not a
supported selector.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from raceintel.config import V2Paths
from raceintel.experiments.feature_sets import resolve_feature_set
from raceintel.features.build_matrix import load_manifest, load_matrix, output_dir
from raceintel.model_lab.errors import MatrixContractError, UnknownFeatureSetError
from raceintel.model_lab.protocol import (
    EXPECTED_ABLATION_CONFIG_SHA256,
    EXPECTED_MATRIX_CONTENT_HASH,
    EXPECTED_MATRIX_PARQUET_SHA256,
    EXPECTED_MANIFEST_SHA256,
    ModelLabProtocolError,
    validate_ablation_contract,
    validate_manifest_contract,
)

#: Identity/metadata that must survive into evaluation for race aggregation,
#: stage evaluation and synchronized winner evaluation.
IDENTITY_COLUMNS = (
    "state_id", "race_id", "season", "round_no", "circuit_id", "driver_id",
    "constructor_id", "lap_number", "state_time_s",
)

_CACHE: dict = {}


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


@dataclass(frozen=True)
class FeatureSchema:
    """Raw dtype contract of the predictive surface (no preprocessing)."""

    numeric: tuple
    boolean: tuple
    categorical: tuple

    def kind_of(self, name: str) -> str:
        if name in self.categorical:
            return "categorical"
        if name in self.boolean:
            return "boolean"
        if name in self.numeric:
            return "numeric"
        raise MatrixContractError(f"unknown predictive column {name!r}")

    def to_dict(self) -> dict:
        return {
            "numeric": list(self.numeric),
            "boolean": list(self.boolean),
            "categorical": list(self.categorical),
            "counts": {
                "numeric": len(self.numeric),
                "boolean": len(self.boolean),
                "categorical": len(self.categorical),
            },
        }


def feature_schema(matrix: pd.DataFrame, predictive: list) -> FeatureSchema:
    numeric, boolean, categorical = [], [], []
    for name in predictive:
        dtype = matrix[name].dtype
        if pd.api.types.is_bool_dtype(dtype):
            boolean.append(name)
        elif dtype == object or isinstance(dtype, pd.CategoricalDtype):
            categorical.append(name)
        elif pd.api.types.is_numeric_dtype(dtype):
            numeric.append(name)
        else:
            raise MatrixContractError(
                f"predictive column {name!r} has unsupported dtype {dtype}")
    return FeatureSchema(tuple(numeric), tuple(boolean), tuple(categorical))


class CanonicalMatrix:
    """Read-only view over the frozen canonical matrix + manifest."""

    def __init__(self, paths: V2Paths, matrix: pd.DataFrame,
                 manifest: dict) -> None:
        self._paths = paths
        self._matrix = matrix
        self._manifest = manifest
        self._schema: FeatureSchema | None = None

    @property
    def paths(self) -> V2Paths:
        return self._paths

    @property
    def frame(self) -> pd.DataFrame:
        """The cached frame. Consumers must treat it as read-only."""
        return self._matrix

    @property
    def manifest(self) -> dict:
        return self._manifest

    @property
    def predictive_columns(self) -> tuple:
        return tuple(self._manifest["predictive_columns"])

    @property
    def label_columns(self) -> tuple:
        return tuple(self._manifest["label_columns"])

    @property
    def metadata_columns(self) -> tuple:
        return tuple(self._manifest["metadata_columns"])

    @property
    def task_eligibility_columns(self) -> tuple:
        return tuple(self._manifest["task_eligibility_columns"])

    @property
    def schema(self) -> FeatureSchema:
        if self._schema is None:
            self._schema = feature_schema(self._matrix,
                                          self.predictive_columns)
        return self._schema

    def select_seasons(self, seasons) -> pd.DataFrame:
        """Rows for the given seasons, canonical order preserved (copy)."""
        season_set = set(int(s) for s in seasons)
        mask = self._matrix["season"].astype(int).isin(season_set)
        return self._matrix.loc[mask].copy()

    def race_ids(self) -> tuple:
        key = ["season", "round_no", "race_id"]
        return tuple(self._matrix[key].drop_duplicates()
                     .sort_values(key)["race_id"].tolist())


def load_canonical(paths: V2Paths | None = None, *,
                   verify_content_hash: bool = False,
                   verify_bytes: bool = False) -> CanonicalMatrix:
    """Load and validate the canonical F15 matrix (cached per process).

    ``verify_content_hash`` recomputes the semantic content hash (the strong
    integrity check); ``verify_bytes`` re-hashes Parquet/manifest/ablation
    bytes. Both default off for cheap iteration; tests turn them on.
    """
    paths = paths or V2Paths.resolve()
    key = (str(paths.root), bool(verify_content_hash), bool(verify_bytes))
    if key in _CACHE:
        return _CACHE[key]

    out = output_dir(paths)
    matrix, manifest = load_matrix(paths, out)
    try:
        validate_manifest_contract(manifest)
    except ModelLabProtocolError as exc:
        raise MatrixContractError(str(exc)) from exc

    if verify_content_hash:
        from raceintel.features.build_matrix import content_hash
        actual = content_hash(matrix)
        if actual != EXPECTED_MATRIX_CONTENT_HASH:
            raise MatrixContractError(
                f"matrix content hash drift: {actual} != "
                f"{EXPECTED_MATRIX_CONTENT_HASH}")

    if verify_bytes:
        for name, path, expected in (
                ("parquet", out / "model_matrix.parquet",
                 EXPECTED_MATRIX_PARQUET_SHA256),
                ("manifest", out / "manifest.json", EXPECTED_MANIFEST_SHA256),
                ("ablation_config", out / "ablation_config.json",
                 EXPECTED_ABLATION_CONFIG_SHA256)):
            if not path.exists():
                raise MatrixContractError(f"missing Phase-2 artifact {path}")
            actual = _sha256_file(path)
            if actual != expected:
                raise MatrixContractError(
                    f"{name} sha256 drift: {actual} != {expected}")
        ablation = json.loads((out / "ablation_config.json").read_text())
        try:
            validate_ablation_contract(ablation)
        except ModelLabProtocolError as exc:
            raise MatrixContractError(str(exc)) from exc

    obj = CanonicalMatrix(paths, matrix, manifest)
    _CACHE[key] = obj
    return obj


def clear_cache() -> None:
    """Drop the process-local validated matrix cache (tests/debug)."""
    _CACHE.clear()


def resolve_features(name: str, canonical: CanonicalMatrix) -> tuple:
    """Ordered predictive feature names for a frozen F16 configuration."""
    try:
        return tuple(resolve_feature_set(name, canonical.manifest))
    except Exception as exc:  # AblationConfigError or manifest drift
        raise UnknownFeatureSetError(
            f"feature set {name!r} not resolvable: {exc}") from exc


def feature_frame(canonical: CanonicalMatrix, name: str) -> pd.DataFrame:
    """Selected predictive columns in canonical order (copy)."""
    return canonical.frame[list(resolve_features(name, canonical))].copy()
