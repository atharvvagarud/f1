"""Atomic canonical Parquet storage (D3).

Write-temp-in-place, fsync, atomic rename. Readers never see a half-written
file, and a failed write can neither corrupt a previous valid output nor
leave a valid-looking partial behind (temps are cleaned on failure).
Filenames are deterministic per (entity, unit); manifests store portable
project-relative references.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

from raceintel.errors import IngestionError


def entity_file_name(entity: str, unit_id: str) -> str:
    """Deterministic filename. Unit ids are canonical keys (no slashes)."""
    safe = unit_id.replace("/", "_")
    if safe != unit_id:
        raise IngestionError.config(f"unit id not filename-safe: {unit_id}")
    return f"{entity}__{safe}.parquet"


def atomic_write_parquet(df, dest: str | Path,
                         engine: str = "pyarrow",
                         compression: str = "snappy") -> Path:
    """Write ``df`` to ``dest`` atomically. Returns the final path."""
    try:
        import pandas as pd  # noqa: F401  (pinned; required for Parquet I/O)
    except ImportError as exc:
        raise IngestionError.config(
            "pandas is required for canonical Parquet writes") from exc

    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp_fd, tmp_name = tempfile.mkstemp(prefix=".tmp-",
                                        suffix=".parquet",
                                        dir=str(dest.parent))
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(tmp_fd, "wb") as handle:
            df.to_parquet(tmp_path, engine=engine, compression=compression,
                           index=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(tmp_path, dest)  # atomic on POSIX and Windows
    except Exception as exc:
        try:
            if tmp_path.exists():
                tmp_path.unlink()
        finally:
            if isinstance(exc, IngestionError):
                raise
            raise IngestionError.storage(
                f"atomic write failed for {dest}: {type(exc).__name__}: {exc}"
            ) from exc
    return dest


def read_parquet(path: str | Path, engine: str = "pyarrow"):
    import pandas as pd

    try:
        return pd.read_parquet(path, engine=engine)
    except Exception as exc:
        raise IngestionError.storage(
            f"parquet read failed for {path}: {type(exc).__name__}: {exc}"
        ) from exc


def dest_for_unit(processed_dir: str | Path, entity: str, season: int,
                  unit_id: str, round_no: int | None = None) -> Path:
    """D2 layout: processed/<entity>/season=<YYYY>[/round=<NN>]/<file>.

    Mirrors ``contracts.partition_path`` (which renders the repo-relative
    form); this builds the absolute destination directly to avoid
    prefix-splitting bugs.
    """
    dest = Path(processed_dir) / entity / f"season={season}"
    if round_no is not None:
        dest = dest / f"round={round_no:02d}"
    return dest / entity_file_name(entity, unit_id)
