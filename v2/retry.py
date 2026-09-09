"""Bounded retry policy (D3).

Finite attempts, deterministic backoff, no sleeps in tests (inject
``sleep_fn``). Only ``RETRYABLE`` categories are retried; anything else
fails fast. Attempt counts are returned so the manifest records them —
retries are never silent.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

from v2.errors import RETRYABLE, ErrorCategory, IngestionError


def compute_backoff(attempt: int, base_s: float, factor: float,
                     max_s: float) -> float:
    """Deterministic exponential backoff for a 1-based failed attempt."""
    return min(base_s * (factor ** (attempt - 1)), max_s)


@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3
    backoff_base_s: float = 2.0
    backoff_factor: float = 2.0
    backoff_max_s: float = 60.0
    retryable: frozenset = field(default_factory=lambda: RETRYABLE)
    sleep_fn: Callable[[float], None] = time.sleep

    def __post_init__(self):
        if self.max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")


@dataclass
class RetryOutcome:
    value: object = None
    attempts: int = 0


def run_with_retry(fn: Callable[[int], object],
                   policy: RetryPolicy) -> RetryOutcome:
    """Call ``fn(attempt)`` until success or the budget is exhausted.

    ``fn`` raises IngestionError on failure. Retryable categories sleep
    (via the injected ``sleep_fn``) and retry; anything else — including
    non-IngestionError exceptions, re-raised untouched — fails immediately.
    """
    last_error: IngestionError | None = None
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return RetryOutcome(value=fn(attempt), attempts=attempt)
        except IngestionError as exc:
            last_error = exc
            if exc.category not in policy.retryable or attempt >= policy.max_attempts:
                raise
            policy.sleep_fn(compute_backoff(
                attempt, policy.backoff_base_s,
                policy.backoff_factor, policy.backoff_max_s))
    assert last_error is not None  # max_attempts >= 1 guarantees a pass
    raise last_error


def is_retryable_category(category: ErrorCategory) -> bool:
    return category in RETRYABLE
