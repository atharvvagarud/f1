"""Race-stage partitioning under the frozen M0 thirds contract.

EARLY = [0, 1/3) · MID = [1/3, 2/3) · LATE = [2/3, 1] on
``race_progress_frac``. Boundaries are deterministic: exactly 1/3 -> MID,
exactly 2/3 -> LATE, 1.0 -> LATE.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from raceintel.model_lab.protocol import STAGE_BUCKETS

STAGE_NAMES = tuple(name for name, _, _ in STAGE_BUCKETS)


def stage_partition(progress):
    """Assign each progress value to EARLY/MID/LATE (Series in, Series out)."""
    is_series = isinstance(progress, pd.Series)
    values = progress.astype(float) if is_series else np.asarray(
        progress, dtype=float)
    arr = values.to_numpy() if is_series else values
    if not np.all(np.isfinite(arr)):
        raise ValueError("race_progress_frac contains null/non-finite values")
    if np.any(arr < 0.0) or np.any(arr > 1.0):
        raise ValueError("race_progress_frac outside [0, 1]")
    early = arr < (1.0 / 3.0)
    mid = (arr >= (1.0 / 3.0)) & (arr < (2.0 / 3.0))
    out = np.where(early, "EARLY", np.where(mid, "MID", "LATE"))
    if is_series:
        return pd.Series(out, index=progress.index, name="stage")
    return out


def stage_counts(progress) -> dict:
    labels = stage_partition(progress)
    if isinstance(labels, pd.Series):
        counts = labels.value_counts().to_dict()
    else:
        values, counts_arr = np.unique(labels, return_counts=True)
        counts = dict(zip(values.tolist(), counts_arr.tolist()))
    return {name: int(counts.get(name, 0)) for name in STAGE_NAMES}
