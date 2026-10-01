"""Timing + latency-summary utilities (generic; no candidate benchmarking)."""

from __future__ import annotations

import time
from dataclasses import dataclass, field


def monotonic() -> float:
    return time.perf_counter()


@dataclass
class Timer:
    """Context manager measuring wall time with a monotonic clock."""

    seconds: float = field(default=0.0, init=False)
    _start: float = field(default=0.0, init=False, repr=False)

    def __enter__(self) -> "Timer":
        self._start = monotonic()
        return self

    def __exit__(self, *exc) -> None:
        self.seconds = monotonic() - self._start


def timed_call(fn, *args, repeats: int = 1, warmup: int = 0, **kwargs):
    """Call ``fn`` and return (last_result, elapsed_samples).

    Warm-up calls are untimed; each timed call is measured with the
    monotonic clock. No sampling is fabricated.
    """
    if repeats < 1:
        raise ValueError("repeats must be >= 1")
    result = None
    for _ in range(warmup):
        result = fn(*args, **kwargs)
    samples = []
    for _ in range(repeats):
        start = monotonic()
        result = fn(*args, **kwargs)
        samples.append(monotonic() - start)
    return result, samples


def percentile(samples, q: float) -> float:
    import numpy as np
    arr = np.asarray(samples, dtype=float)
    if len(arr) == 0:
        return float("nan")
    return float(np.percentile(arr, q))


def latency_summary(samples) -> dict:
    """count / mean / min / max / p50 / p95 / p99 over measured samples."""
    import numpy as np
    arr = np.asarray(samples, dtype=float)
    if len(arr) == 0:
        return {"count": 0, "mean": None, "min": None, "max": None,
                "p50": None, "p95": None, "p99": None}
    return {
        "count": int(len(arr)),
        "mean": float(arr.mean()),
        "min": float(arr.min()),
        "max": float(arr.max()),
        "p50": percentile(arr, 50),
        "p95": percentile(arr, 95),
        "p99": percentile(arr, 99),
    }
