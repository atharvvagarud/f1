"""D3 idempotency tests: skip-COMPLETE, deterministic rebuild, no partials."""

import pandas as pd
import pytest

from raceintel import contracts as C
from raceintel.config import V2Paths
from raceintel.errors import IngestionError
from raceintel.data.ingestion import AdapterResult, run_unit
from raceintel.manifests import Manifest, UnitStatus
from raceintel.retry import RetryPolicy
from raceintel.runs import start_run
from raceintel.data.synthetic import synthetic_adapter


def noop_policy():
    return RetryPolicy(max_attempts=2, sleep_fn=lambda s: None)


def make_run(**scope):
    return start_run(source="synthetic", source_lib_version="synthetic-0",
                     schema_version=C.SCHEMA_VERSION,
                     scope=scope or {"units": ["2023-r01-R"]},
                     config_snapshot={"v2_root": "data/v2"})


def setup_manifest(paths):
    manifest = Manifest()
    manifest.plan_race_scope(2023, [1], schema_version=C.SCHEMA_VERSION)
    return manifest


def written_parquet_files(paths):
    return sorted(paths.processed_dir.rglob("*.parquet"))


def test_first_run_writes_second_run_skips(tmp_path):
    paths = V2Paths.from_root(tmp_path)
    manifest = setup_manifest(paths)
    first = run_unit(manifest, "2023-r01-R", synthetic_adapter, paths,
                     make_run(), noop_policy())
    assert first.status == UnitStatus.COMPLETE
    files = written_parquet_files(paths)
    assert len(files) == 2  # races + driver_laps
    mtimes = {f: f.stat().st_mtime_ns for f in files}

    second = run_unit(manifest, "2023-r01-R", synthetic_adapter, paths,
                      make_run(), noop_policy())
    assert second.status == UnitStatus.COMPLETE
    assert second.message.startswith("skip")
    assert second.attempts == first.attempts == 1  # no new attempts
    assert written_parquet_files(paths) == files  # no duplicates
    assert {f: f.stat().st_mtime_ns for f in files} == mtimes  # untouched


def test_forced_rebuild_replaces_deterministically(tmp_path):
    paths = V2Paths.from_root(tmp_path)
    manifest = setup_manifest(paths)
    run_unit(manifest, "2023-r01-R", synthetic_adapter, paths, make_run(),
             noop_policy())
    before = {f: f.read_bytes() for f in written_parquet_files(paths)}
    outcome = run_unit(manifest, "2023-r01-R", synthetic_adapter, paths,
                       make_run(), noop_policy(), force=True)
    assert outcome.status == UnitStatus.COMPLETE
    after = {f: f.read_bytes() for f in written_parquet_files(paths)}
    assert set(after) == set(before)  # same files, none added
    assert after == before  # deterministic bytes


def test_failing_adapter_leaves_no_canonical_file(tmp_path):
    paths = V2Paths.from_root(tmp_path)
    manifest = setup_manifest(paths)

    def boom(ctx):
        raise IngestionError.transient("source down")

    outcome = run_unit(manifest, "2023-r01-R", boom, paths, make_run(),
                       noop_policy())
    assert outcome.status == UnitStatus.FAILED
    assert written_parquet_files(paths) == []
    assert manifest.get("2023-r01-R").attempts == 2  # budget exhausted
    assert manifest.get("2023-r01-R").error_category == "transient"


def test_validation_failure_never_exposes_output(tmp_path):
    paths = V2Paths.from_root(tmp_path)
    manifest = setup_manifest(paths)

    def bad_frame(ctx):
        return AdapterResult(frames={"driver_laps": pd.DataFrame(
            [{"race_id": "2023-r01-R", "oops": 1}])})

    outcome = run_unit(manifest, "2023-r01-R", bad_frame, paths, make_run(),
                       noop_policy())
    assert outcome.status == UnitStatus.FAILED
    assert written_parquet_files(paths) == []
    assert manifest.get("2023-r01-R").error_category == "validation"


def test_missing_session_becomes_skipped(tmp_path):
    paths = V2Paths.from_root(tmp_path)
    manifest = setup_manifest(paths)

    def gone(ctx):
        raise IngestionError.missing("2020 Australian GP cancelled")

    outcome = run_unit(manifest, "2023-r01-R", gone, paths, make_run(),
                       noop_policy())
    assert outcome.status == UnitStatus.SKIPPED
    assert "cancelled" in manifest.get("2023-r01-R").skip_reason
    assert written_parquet_files(paths) == []


def test_anomaly_note_is_complete_with_quality(tmp_path):
    paths = V2Paths.from_root(tmp_path)
    manifest = setup_manifest(paths)

    def odd(ctx):
        result = synthetic_adapter(ctx)
        result.anomaly_note = "stint fix applied upstream"
        return result

    outcome = run_unit(manifest, "2023-r01-R", odd, paths, make_run(),
                       noop_policy())
    # A source/domain anomaly with complete contract outputs is COMPLETE,
    # with the note persisted as quality provenance — not PARTIAL.
    assert outcome.status == UnitStatus.COMPLETE
    assert "stint fix applied upstream" in outcome.message
    assert len(written_parquet_files(paths)) == 2
    assert manifest.get("2023-r01-R").quality_note == "stint fix applied upstream"

    # Skip path preserves the persisted quality note (no re-run needed).
    again = run_unit(manifest, "2023-r01-R", odd, paths, make_run(),
                     noop_policy())
    assert again.status == UnitStatus.COMPLETE
    assert again.message.startswith("skip")
    assert manifest.get("2023-r01-R").quality_note == "stint fix applied upstream"


def test_partial_reason_is_partial_with_quality(tmp_path):
    paths = V2Paths.from_root(tmp_path)
    manifest = setup_manifest(paths)

    def incomplete(ctx):
        result = synthetic_adapter(ctx)
        result.anomaly_note = "pit-lane start driver x (kept, nulls)"
        result.partial_reason = "shortened race: 3/39 laps observed"
        return result

    outcome = run_unit(manifest, "2023-r01-R", incomplete, paths, make_run(),
                       noop_policy())
    # Material incompleteness (shortened race) is PARTIAL; the anomaly note
    # is still persisted alongside so nothing unusual is hidden.
    assert outcome.status == UnitStatus.PARTIAL
    assert "shortened race" in outcome.message
    assert len(written_parquet_files(paths)) == 2
    entry = manifest.get("2023-r01-R")
    assert entry.quality_note == "pit-lane start driver x (kept, nulls)"
    assert entry.error_message == "shortened race: 3/39 laps observed"


def test_manifest_roundtrip_preserves_quality_note(tmp_path):
    paths = V2Paths.from_root(tmp_path)
    manifest = setup_manifest(paths)

    def odd(ctx):
        result = synthetic_adapter(ctx)
        result.anomaly_note = "verbatim source quirk"
        return result

    run_unit(manifest, "2023-r01-R", odd, paths, make_run(), noop_policy())
    manifest_path = paths.manifest_path("manifest.json")
    manifest.save(manifest_path)
    reloaded = Manifest.load(manifest_path)
    assert reloaded.get("2023-r01-R").status == UnitStatus.COMPLETE
    assert reloaded.get("2023-r01-R").quality_note == "verbatim source quirk"
