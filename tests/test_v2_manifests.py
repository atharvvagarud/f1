"""D3 manifest tests: creation, persistence, transitions, recovery."""

import json

import pytest

from raceintel.errors import IngestionError
from raceintel.manifests import (IllegalTransitionError, Manifest, ManifestEntry,
                          UnitStatus)


def make_manifest():
    manifest = Manifest()
    manifest.plan_race_scope(2023, [1, 2], schema_version=1)
    return manifest


def test_plan_and_counts():
    manifest = make_manifest()
    assert manifest.status_counts()["pending"] == 2
    assert manifest.get("2023-r01-R").race_id == "2023-r01-R"


def test_duplicate_unit_rejected():
    manifest = make_manifest()
    with pytest.raises(IngestionError):
        manifest.plan_race_scope(2023, [1], schema_version=1)


def test_serialization_round_trip(tmp_path):
    manifest = make_manifest()
    manifest.transition("2023-r01-R", UnitStatus.DOWNLOADING, run_id="r1")
    manifest.record_attempt("2023-r01-R")
    path = manifest.save(tmp_path / "m.json")
    raw = json.loads(path.read_text())
    assert raw["format_version"] == 1
    loaded = Manifest.load(path)
    entry = loaded.get("2023-r01-R")
    assert entry.status == UnitStatus.DOWNLOADING
    assert entry.attempts == 1
    assert entry.claimed_by == "r1"
    assert entry.schema_version == 1


def test_legal_lifecycle():
    manifest = make_manifest()
    manifest.transition("2023-r01-R", UnitStatus.DOWNLOADING, run_id="r1")
    manifest.transition("2023-r01-R", UnitStatus.COMPLETE,
                        output_refs=["data/v2/x.parquet"])
    entry = manifest.get("2023-r01-R")
    assert entry.status == UnitStatus.COMPLETE
    assert entry.claimed_by is None  # claim released on terminal state


def test_illegal_transitions_fail():
    manifest = make_manifest()
    with pytest.raises(IllegalTransitionError):
        manifest.transition("2023-r01-R", UnitStatus.COMPLETE)  # skip claim
    manifest.transition("2023-r01-R", UnitStatus.DOWNLOADING, run_id="r1")
    with pytest.raises(IllegalTransitionError):
        # A claimed unit cannot return to PENDING implicitly; only
        # recover_stale (crash recovery) may do that.
        manifest.transition("2023-r01-R", UnitStatus.PENDING)


def test_complete_requires_force_to_reopen():
    manifest = make_manifest()
    manifest.transition("2023-r01-R", UnitStatus.DOWNLOADING, run_id="r1")
    manifest.transition("2023-r01-R", UnitStatus.COMPLETE)
    with pytest.raises(IllegalTransitionError):
        manifest.transition("2023-r01-R", UnitStatus.DOWNLOADING, run_id="r2")
    manifest.transition("2023-r01-R", UnitStatus.DOWNLOADING, run_id="r2",
                        force=True)
    assert manifest.get("2023-r01-R").status == UnitStatus.DOWNLOADING


def test_failed_partial_requeue():
    manifest = make_manifest()
    manifest.transition("2023-r01-R", UnitStatus.DOWNLOADING, run_id="r1")
    manifest.transition("2023-r01-R", UnitStatus.FAILED,
                        error_category="transient", error_message="boom")
    manifest.transition("2023-r01-R", UnitStatus.PENDING)  # requeue
    assert manifest.get("2023-r01-R").status == UnitStatus.PENDING
    assert manifest.get("2023-r01-R").attempts == 0  # attempts preserved below
    manifest.transition("2023-r02-R", UnitStatus.DOWNLOADING, run_id="r1")
    manifest.transition("2023-r02-R", UnitStatus.PARTIAL,
                        error_message="weird")
    manifest.transition("2023-r02-R", UnitStatus.PENDING)
    assert manifest.get("2023-r02-R").status == UnitStatus.PENDING


def test_skip_requires_reason():
    manifest = make_manifest()
    with pytest.raises(IngestionError):
        manifest.transition("2023-r01-R", UnitStatus.SKIPPED)
    manifest.transition("2023-r01-R", UnitStatus.SKIPPED,
                        skip_reason="cancelled event, no session")
    assert manifest.get("2023-r01-R").skip_reason.startswith("cancelled")


def test_stale_downloading_recovery():
    manifest = make_manifest()
    manifest.transition("2023-r01-R", UnitStatus.DOWNLOADING, run_id="dead")
    entry = manifest.get("2023-r01-R")
    entry.claimed_at = "2020-01-01T00:00:00+00:00"  # crashed long ago
    recovered = manifest.recover_stale(
        max_age_s=60, now_iso="2026-09-08T00:00:00+00:00")
    assert recovered == ["2023-r01-R"]
    assert manifest.get("2023-r01-R").status == UnitStatus.PENDING
    # Fresh claims are not recovered.
    manifest.transition("2023-r02-R", UnitStatus.DOWNLOADING, run_id="live")
    recovered = manifest.recover_stale(
        max_age_s=3600, now_iso="2026-09-08T00:00:00+00:00")
    assert recovered == []
    assert manifest.get("2023-r02-R").status == UnitStatus.DOWNLOADING


def test_unknown_unit_fails_clearly():
    manifest = make_manifest()
    with pytest.raises(IngestionError):
        manifest.transition("2099-r99-R", UnitStatus.DOWNLOADING)
