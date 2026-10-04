"""V3.1B fail-closed validation for dynamics artifacts (no model code).

Every check raises :class:`DynamicsValidationError` on violation; NaN is
allowed exactly where the contract declares nullability, infinity never.
"""

from __future__ import annotations

from raceintel.features.dynamics.contract import (
    ALL_DEFINITIONS,
    CONTRACT_VERSION,
    VALID_DTYPES,
    contract_hash,
    feature_set_names,
)


class DynamicsValidationError(ValueError):
    """Fail-closed dynamics validation failure. Never repairs."""


EXPECTED_CONTRACT_VERSION = CONTRACT_VERSION

#: Parent Phase-2 identities the V3.1 sidecar builds upon (frozen).
EXPECTED_PARENT_CONTENT = (
    "d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db")
EXPECTED_PARENT_PARQUET = (
    "b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3")
EXPECTED_MATRIX_ROWS = 189420

_CANONICAL_ORDER = tuple(d.name for d in ALL_DEFINITIONS)
_NULLABLE = {d.name: d.nullable for d in ALL_DEFINITIONS}
_DTYPE = {d.name: d.dtype for d in ALL_DEFINITIONS}


def check_contract_pinned(version: str, sha: str) -> None:
    """Provenance contract hash must equal the frozen V3.1A identity."""
    if version != EXPECTED_CONTRACT_VERSION:
        raise DynamicsValidationError(
            f"contract version {version!r} != {EXPECTED_CONTRACT_VERSION!r}")
    if sha != contract_hash():
        raise DynamicsValidationError(
            "contract sha mismatch: rebuild against the frozen contract")


def check_parent_identities(content_sha: str, parquet_sha: str) -> None:
    """Sidecar parent must be the frozen Phase-2 artifact pair."""
    if content_sha != EXPECTED_PARENT_CONTENT:
        raise DynamicsValidationError("parent content sha mismatch")
    if parquet_sha != EXPECTED_PARENT_PARQUET:
        raise DynamicsValidationError("parent parquet sha mismatch")


def check_frame_schema(frame, feature_names: list) -> None:
    """Exact predictive membership, dtypes, order; no extras."""
    cols = list(frame.columns)
    identity = [c for c in cols if c not in set(_CANONICAL_ORDER)]
    if sorted(feature_names) != sorted(_CANONICAL_ORDER):
        raise DynamicsValidationError("feature set is not the 29 contract")
    missing = [n for n in feature_names if n not in cols]
    if missing:
        raise DynamicsValidationError(f"missing columns: {missing}")
    extra = [c for c in cols
             if c not in set(feature_names) | set(identity)]
    # identity columns are validated separately; predictive extras fail:
    extras_pred = [c for c in extra if c.startswith("dyn_")]
    if extras_pred:
        raise DynamicsValidationError(
            f"extra predictive columns: {extras_pred}")
    if [c for c in cols if c in set(feature_names)] != feature_names:
        raise DynamicsValidationError("predictive columns not canonical")
    for name in feature_names:
        want = _DTYPE[name]
        got = str(frame[name].dtype)
        # Storage note: logical int64 with contracted nullability is
        # stored pandas-Int64 (repo precedent: frozen "Int64" label
        # dtypes); float64/bool map 1:1.
        ok = (want == "float64" and got == "float64") or \
             (want == "int64" and got in ("int64", "Int64")) or \
             (want == "bool" and got in ("boolean", "bool"))
        if not ok:
            raise DynamicsValidationError(
                f"dtype drift {name}: {got} != {want}")


def check_values(frame, feature_names: list) -> None:
    """No infinities; nulls only where the contract allows them."""
    import pandas as pd
    for name in feature_names:
        col = frame[name]
        if _DTYPE[name] == "float64":
            # vectorized: reject inf, allow NaN/None
            arr = pd.to_numeric(col, errors="coerce")
            if bool((arr == float("inf")).any()) or \
                    bool((arr == float("-inf")).any()):
                raise DynamicsValidationError(f"infinity in {name}")
            if not _NULLABLE[name] and bool(arr.isna().any()):
                raise DynamicsValidationError(
                    f"unexpected null in non-nullable {name}")
        elif _DTYPE[name] == "bool":
            vals = set(pd.unique(col.dropna()))
            if not vals <= {True, False}:
                raise DynamicsValidationError(
                    f"non-boolean in {name}: {vals}")
            if not _NULLABLE[name] and bool(col.isna().any()):
                raise DynamicsValidationError(
                    f"unexpected null in non-nullable {name}")
        elif _DTYPE[name] == "int64":
            if not _NULLABLE[name] and bool(col.isna().any()):
                raise DynamicsValidationError(
                    f"unexpected null in non-nullable {name}")
            if (col.dropna() < 0).any():
                raise DynamicsValidationError(f"negative count in {name}")


def check_row_identity(frame, key: str = "state_id",
                       expected_rows: int = EXPECTED_MATRIX_ROWS) -> None:
    """Unique keys, exact row count (no silent drops)."""
    if len(frame) != expected_rows:
        raise DynamicsValidationError(
            f"row count {len(frame)} != {expected_rows}")
    if frame[key].duplicated().any():
        raise DynamicsValidationError(f"duplicate {key}")
    if frame[key].isna().any():
        raise DynamicsValidationError(f"null {key}")


def validate_feature_names(names: list) -> None:
    """Output names must be exactly the 29 contracted names."""
    if sorted(names) != sorted(_CANONICAL_ORDER):
        raise DynamicsValidationError(
            f"names != contract 29: extra={sorted(set(names) - set(_CANONICAL_ORDER))}, "
            f"missing={sorted(set(_CANONICAL_ORDER) - set(names))}")
    if len(names) != len(set(names)):
        raise DynamicsValidationError("duplicate feature names")


def validate_dtypes() -> None:
    """Every contract dtype is in the frozen vocabulary."""
    for d in ALL_DEFINITIONS:
        if d.dtype not in VALID_DTYPES:
            raise DynamicsValidationError(
                f"invalid dtype {d.dtype!r} for {d.name}")
