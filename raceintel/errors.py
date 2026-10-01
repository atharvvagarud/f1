"""V2 ingestion error taxonomy (D3).

Small and explicit: every failure recorded in a manifest carries one of
these categories plus a short safe message. No giant tracebacks, no
secrets. ``retryable`` is the single mapping the retry policy consults —
orchestration never catches bare ``Exception`` and treats all failures
identically.
"""

from __future__ import annotations

from enum import Enum


class ErrorCategory(str, Enum):
    TRANSIENT = "transient"        # network/source hiccup; bounded retry
    STORAGE = "storage"            # write/read failure; bounded retry
    MISSING_SESSION = "missing"    # session has no usable data; skip, don't retry
    SOURCE_ANOMALY = "anomaly"     # legitimate unusual source data; partial, don't retry
    VALIDATION = "validation"      # contract violation; fail, never expose output
    CONFIG = "config"              # bad scope/paths/setup; fail immediately
    UNEXPECTED = "unexpected"      # non-IngestionError at the boundary; fail, keep type info


# The only failures worth a second attempt. Everything else either resolves
# to a terminal manifest state or is a programming/setup problem that
# retrying cannot fix.
RETRYABLE = frozenset({ErrorCategory.TRANSIENT, ErrorCategory.STORAGE})


class IngestionError(Exception):
    """Categorised ingestion failure with a short safe message."""

    def __init__(self, category: ErrorCategory, message: str):
        super().__init__(f"[{category.value}] {message}")
        self.category = category
        self.message = message

    @classmethod
    def transient(cls, message: str) -> "IngestionError":
        return cls(ErrorCategory.TRANSIENT, message)

    @classmethod
    def missing(cls, message: str) -> "IngestionError":
        return cls(ErrorCategory.MISSING_SESSION, message)

    @classmethod
    def anomaly(cls, message: str) -> "IngestionError":
        return cls(ErrorCategory.SOURCE_ANOMALY, message)

    @classmethod
    def validation(cls, message: str) -> "IngestionError":
        return cls(ErrorCategory.VALIDATION, message)

    @classmethod
    def storage(cls, message: str) -> "IngestionError":
        return cls(ErrorCategory.STORAGE, message)

    @classmethod
    def config(cls, message: str) -> "IngestionError":
        return cls(ErrorCategory.CONFIG, message)
