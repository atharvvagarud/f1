"""Lightweight validation boundary (D3).

D11 owns comprehensive validation. This module implements only the hook
that prevents obviously invalid writes from ever becoming canonical
COMPLETE output: required key columns present, keys non-null and unique,
and no columns outside the D2 contract. Anything deeper is a D11 concern.
"""

from __future__ import annotations

from dataclasses import dataclass

from raceintel import contracts as C
from raceintel.errors import IngestionError


@dataclass(frozen=True)
class Finding:
    level: C.Severity
    check: str
    detail: str


def validate_frame(df, contract: C.TableContract) -> list[Finding]:
    """Boundary checks for one canonical frame. Returns findings; raises
    IngestionError(VALIDATION) on any ERROR-level finding."""
    findings: list[Finding] = []
    known = set(contract.column_names())

    unknown = [c for c in df.columns if c not in known]
    if unknown:
        findings.append(Finding(
            C.Severity.ERROR, "unknown-columns",
            f"columns outside D2 contract: {sorted(unknown)}"))

    present_keys = []
    for key_col in contract.primary_key:
        if key_col not in df.columns:
            findings.append(Finding(
                C.Severity.ERROR, "missing-key-column",
                f"primary-key column absent: {key_col}"))
            continue
        present_keys.append(key_col)
        nulls = int(df[key_col].isna().sum())
        if nulls:
            findings.append(Finding(
                C.Severity.ERROR, "null-key",
                f"{nulls} null values in key column {key_col}"))

    if len(present_keys) == len(contract.primary_key):
        dupes = int(df.duplicated(subset=list(contract.primary_key)).sum())
        if dupes:
            findings.append(Finding(
                C.Severity.ERROR, "duplicate-key",
                f"{dupes} duplicate primary-key rows"))

    errors = [f for f in findings if f.level is C.Severity.ERROR]
    if errors:
        raise IngestionError.validation(
            "; ".join(f"{f.check}: {f.detail}" for f in errors))
    return findings
