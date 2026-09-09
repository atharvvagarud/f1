"""Ingestion orchestration core (D3).

The pipeline every future source adapter (D4/D5) plugs into:

    load source -> normalize to D2 contract -> validate -> atomic write
    -> manifest update

Adapters are plain callables (dependency injection without a framework):
``adapter(ctx) -> AdapterResult``. The core owns transitions, retries,
validation gating, atomic writes and manifest bookkeeping — adapters own
source access + normalisation only. D3 ships no real source adapter.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from v2 import contracts as C
from v2.config import V2Paths
from v2.errors import ErrorCategory, IngestionError
from v2.manifests import Manifest, ManifestEntry, UnitStatus
from v2.retry import RetryOutcome, RetryPolicy, run_with_retry
from v2.runs import RunRecord
from v2.storage import dest_for_unit
from v2.storage import atomic_write_parquet
from v2.validation import validate_frame


# Entity -> frame key mapping is 1:1: adapter frames are named by entity.
@dataclass
class AdapterResult:
    frames: dict
    # Source/domain anomaly notes (quality provenance): the source is
    # faithfully represented and all contract-required outputs are
    # present/valid, but the real race contains something unusual
    # (pit-lane start, unpaired pit boundary, verbatim unknown compound,
    # cross-source identity mismatch). Persisted on the manifest entry;
    # the unit is still COMPLETE.
    anomaly_note: str | None = None
    # Material incompleteness: a contract-required output cannot be
    # faithfully reconstructed or expected source data is missing
    # (shortened race, dropped source laps). The unit is PARTIAL.
    partial_reason: str | None = None


@dataclass
class UnitContext:
    paths: V2Paths
    entry: ManifestEntry
    run: RunRecord


AdapterFn = Callable[[UnitContext], AdapterResult]


@dataclass
class UnitOutcome:
    unit_id: str
    status: UnitStatus
    attempts: int
    output_refs: list = field(default_factory=list)
    message: str | None = None


def run_unit(manifest: Manifest, unit_id: str, adapter: AdapterFn,
             paths: V2Paths, run: RunRecord,
             policy: RetryPolicy | None = None,
             force: bool = False,
             on_claim: Callable[[Manifest], None] | None = None) -> UnitOutcome:
    """Execute one manifest unit to a terminal state.

    COMPLETE units are skipped unless ``force=True`` (deterministic
    replace, never append). Validation failure never exposes output:
    the unit goes FAILED and any temp file is already cleaned by storage.

    ``on_claim`` (optional) runs synchronously right after the
    PENDING -> DOWNLOADING transition and BEFORE any blocking network
    work, so callers can persist the claim (crash recovery via
    ``recover_stale`` and live ``status`` visibility depend on the claim
    being on disk, not just in memory). A failing ``on_claim`` propagates
    immediately: running unclaimed work is never allowed to proceed
    silently.
    """
    policy = policy or RetryPolicy()
    entry = manifest.get(unit_id)

    if entry.status == UnitStatus.COMPLETE and not force:
        return UnitOutcome(unit_id, UnitStatus.COMPLETE, entry.attempts,
                           list(entry.output_refs), "skip: already COMPLETE")

    manifest.transition(unit_id, UnitStatus.DOWNLOADING, run_id=run.run_id,
                        force=force)
    if on_claim is not None:
        on_claim(manifest)

    def attempt_fn(attempt: int) -> AdapterResult:
        manifest.record_attempt(unit_id)
        try:
            return adapter(UnitContext(paths, manifest.get(unit_id), run))
        except IngestionError:
            raise
        except Exception as exc:  # boundary: preserve category + context
            raise IngestionError(
                ErrorCategory.UNEXPECTED,
                f"{type(exc).__name__}: {exc}") from exc

    try:
        outcome: RetryOutcome = run_with_retry(attempt_fn, policy)
    except IngestionError as exc:
        return _fail(manifest, entry, exc, run)

    result: AdapterResult = outcome.value
    try:
        output_refs = _validate_and_write(
            manifest, entry, result, paths, run)
    except IngestionError as exc:
        return _fail(manifest, entry, exc, run)

    if result.partial_reason is not None:
        quality = (result.anomaly_note[:2000]
                   if result.anomaly_note is not None else None)
        manifest.transition(
            unit_id, UnitStatus.PARTIAL, run_id=run.run_id,
            error_category=ErrorCategory.SOURCE_ANOMALY.value,
            error_message=result.partial_reason[:500],
            quality_note=quality,
            output_refs=output_refs)
        return UnitOutcome(unit_id, UnitStatus.PARTIAL, entry.attempts,
                           output_refs, result.partial_reason[:500])

    quality = (result.anomaly_note[:2000]
               if result.anomaly_note is not None else None)
    manifest.transition(unit_id, UnitStatus.COMPLETE, run_id=run.run_id,
                        quality_note=quality,
                        output_refs=output_refs)
    message = quality[:500] if quality is not None else "complete"
    return UnitOutcome(unit_id, UnitStatus.COMPLETE, entry.attempts,
                       output_refs, message)


def _validate_and_write(manifest: Manifest, entry: ManifestEntry,
                        result: AdapterResult, paths: V2Paths,
                        run: RunRecord) -> list:
    output_refs = []
    for entity_name, frame in result.frames.items():
        try:
            contract = C.get_table(entity_name)
        except KeyError:
            raise IngestionError.validation(
                f"adapter returned unknown entity: {entity_name}") from None
        validate_frame(frame, contract)
        season = entry.season
        if season is None:
            raise IngestionError.validation(
                f"unit {entry.unit_id} has no season; cannot partition output")
        dest = dest_for_unit(paths.processed_dir, entity_name, season,
                             entry.unit_id,
                             getattr(entry, "round_no", None)
                             if _round_partitioned(contract) else None)
        atomic_write_parquet(frame, dest)
        output_refs.append(paths.relative(dest))
    if not output_refs:
        raise IngestionError.validation(
            f"adapter returned no frames for unit {entry.unit_id}")
    return output_refs


def _round_partitioned(contract: C.TableContract) -> bool:
    return "round" in contract.partition_keys


def _fail(manifest: Manifest, entry: ManifestEntry, exc: IngestionError,
          run: RunRecord) -> UnitOutcome:
    category = exc.category
    if category == ErrorCategory.MISSING_SESSION:
        manifest.transition(
            entry.unit_id, UnitStatus.SKIPPED, run_id=run.run_id,
            error_category=category.value,
            error_message=exc.message[:500],
            skip_reason=f"missing session: {exc.message[:200]}")
        return UnitOutcome(entry.unit_id, UnitStatus.SKIPPED, entry.attempts,
                           [], exc.message[:500])
    if category == ErrorCategory.SOURCE_ANOMALY:
        manifest.transition(
            entry.unit_id, UnitStatus.PARTIAL, run_id=run.run_id,
            error_category=category.value,
            error_message=exc.message[:500])
        return UnitOutcome(entry.unit_id, UnitStatus.PARTIAL, entry.attempts,
                           [], exc.message[:500])
    manifest.transition(
        entry.unit_id, UnitStatus.FAILED, run_id=run.run_id,
        error_category=category.value, error_message=exc.message[:500])
    return UnitOutcome(entry.unit_id, UnitStatus.FAILED, entry.attempts,
                       [], exc.message[:500])
