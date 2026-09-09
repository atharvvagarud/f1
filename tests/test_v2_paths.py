"""D3 path tests: cwd-independence, tmp isolation, no real writes."""

import os

import pytest

from v2 import contracts as C
from v2.config import V2Paths, ConfigError, configure_fastf1_cache
from v2.ingestion import run_unit
from v2.manifests import Manifest, UnitStatus
from v2.retry import RetryPolicy
from v2.runs import start_run
from v2.synthetic import synthetic_adapter


def test_explicit_root_isolates_all_writes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    paths = V2Paths.from_root(tmp_path / "scratch")
    manifest = Manifest()
    manifest.plan_race_scope(2023, [1], schema_version=C.SCHEMA_VERSION)
    run = start_run(source="synthetic", source_lib_version="synthetic-0",
                    schema_version=C.SCHEMA_VERSION, scope={},
                    config_snapshot={"v2_root": "data/v2"})
    outcome = run_unit(manifest, "2023-r01-R", synthetic_adapter, paths, run,
                       RetryPolicy(sleep_fn=lambda s: None))
    assert outcome.status == UnitStatus.COMPLETE
    assert str(paths.processed_dir).startswith(str(tmp_path))
    assert list(paths.processed_dir.rglob("*.parquet"))


def _snapshot_tree(root) -> dict:
    """Read-only snapshot of a directory tree: relpath -> (size, mtime_ns).

    Stat-only, never reads file contents. Missing root snapshots as empty.
    """
    from pathlib import Path

    snapshot = {}
    root = Path(root)
    if not root.exists():
        return snapshot
    for path in sorted(root.rglob("*")):
        if path.is_file() and not path.is_symlink():
            stat = path.stat()
            snapshot[path.relative_to(root).as_posix()] = (
                stat.st_size, stat.st_mtime_ns)
    return snapshot


def test_repo_data_v2_untouched_by_tmp_runs(tmp_path, monkeypatch):
    """Correct invariant: tmp-isolated runs must not create, modify or
    delete real repository ``data/v2`` content.

    D4 legitimately materializes canonical data under the repo ``data/v2``
    (git-ignored generated output), so asserting its absence is wrong.
    Instead snapshot it, run the tmp-isolated operation, and prove the
    repository state is unchanged.
    """
    from pathlib import Path

    monkeypatch.chdir(tmp_path)
    repo_root = Path(__file__).resolve().parents[1]
    repo_v2 = repo_root / "data" / "v2"
    before = _snapshot_tree(repo_v2)
    # Tmp-isolated operation: all writes must land under tmp_path.
    paths = V2Paths.from_root(tmp_path / "scratch")
    manifest = Manifest()
    manifest.plan_race_scope(2023, [1], schema_version=C.SCHEMA_VERSION)
    run = start_run(source="synthetic", source_lib_version="synthetic-0",
                    schema_version=C.SCHEMA_VERSION, scope={},
                    config_snapshot={"v2_root": "data/v2"})
    outcome = run_unit(manifest, "2023-r01-R", synthetic_adapter, paths, run,
                       RetryPolicy(sleep_fn=lambda s: None))
    assert outcome.status == UnitStatus.COMPLETE
    assert str(paths.processed_dir).startswith(str(tmp_path))
    assert list(paths.processed_dir.rglob("*.parquet"))
    assert _snapshot_tree(repo_v2) == before


def test_discovery_fails_clearly_outside_repo(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("V2_PROJECT_ROOT", raising=False)
    with pytest.raises(ConfigError):
        V2Paths.resolve(root=None)


def test_discovery_from_repo_root():
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[1]
    paths = V2Paths.from_root(repo_root)
    assert paths.cache_dir == repo_root / "data" / "raw" / "fastf1_cache"
    assert paths.processed_dir == repo_root / "data" / "v2" / "processed"


def test_portable_relative_refs(tmp_path):
    paths = V2Paths.from_root(tmp_path)
    ref = paths.relative(paths.processed_dir / "x.parquet")
    assert ref == "data/v2/processed/x.parquet"
    assert os.path.isabs(ref) is False


def test_cache_override_does_not_touch_real_cache(tmp_path):
    target = configure_fastf1_cache(tmp_path / "scratch-cache")
    assert target.is_dir()
