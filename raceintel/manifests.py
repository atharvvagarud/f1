"""Manifest model + state machine (D3).

The manifest is the resumability record: one entry per ingestion unit
(race/session scope for rich FastF1 ingestion), JSON-serialised, with an
explicit legal-transition map. Crash recovery is deliberate: a unit left in
DOWNLOADING by a dead process carries its claim (run id + timestamp), and
only ``recover_stale`` — never normal execution — may return it to PENDING.

Output references are portable project-relative paths (see config.V2Paths).
Messages are short and safe: no tracebacks, no secrets.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from enum import Enum
from pathlib import Path
from typing import Iterable

from raceintel import contracts as C
from raceintel.errors import ErrorCategory, IngestionError
from raceintel.runs import utc_now_iso


class UnitStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETE = "complete"
    PARTIAL = "partial"
    FAILED = "failed"
    SKIPPED = "skipped"


# Legal transitions. Absent edges raise on attempt (fail clearly).
# COMPLETE -> DOWNLOADING exists only via force_rebuild, never implicitly.
# FAILED/PARTIAL -> PENDING is the explicit requeue used by CLI retry.
LEGAL_TRANSITIONS: dict[UnitStatus, frozenset] = {
    UnitStatus.PENDING: frozenset({UnitStatus.DOWNLOADING, UnitStatus.SKIPPED}),
    UnitStatus.DOWNLOADING: frozenset({UnitStatus.COMPLETE, UnitStatus.PARTIAL,
                                       UnitStatus.FAILED, UnitStatus.SKIPPED}),
    UnitStatus.COMPLETE: frozenset({UnitStatus.DOWNLOADING}),
    UnitStatus.PARTIAL: frozenset({UnitStatus.DOWNLOADING, UnitStatus.PENDING}),
    UnitStatus.FAILED: frozenset({UnitStatus.DOWNLOADING, UnitStatus.PENDING}),
    UnitStatus.SKIPPED: frozenset({UnitStatus.PENDING}),
}


@dataclass
class ManifestEntry:
    unit_id: str
    season: int | None = None
    round_no: int | None = None
    session_code: str | None = None
    race_id: str | None = None
    status: UnitStatus = UnitStatus.PENDING
    attempts: int = 0
    error_category: str | None = None
    error_message: str | None = None
    # Persisted source/domain anomaly notes (quality provenance). A COMPLETE
    # unit may still carry a quality_note: PARTIAL means expected output is
    # materially incomplete, while unusual-but-faithful source facts
    # (pit-lane starts, unpaired pit boundaries, verbatim unknown compounds,
    # cross-source identity mismatches) stay visible without implying
    # incompleteness. PARTIAL units may carry both fields.
    quality_note: str | None = None
    skip_reason: str | None = None
    output_refs: list = field(default_factory=list)
    schema_version: int | None = None
    run_id: str | None = None
    claimed_by: str | None = None
    claimed_at: str | None = None
    updated_at: str | None = None

    def to_dict(self) -> dict:
        data = asdict(self)
        data["status"] = self.status.value
        return data

    @classmethod
    def from_dict(cls, data: dict) -> "ManifestEntry":
        data = dict(data)
        data["status"] = UnitStatus(data.get("status", UnitStatus.PENDING.value))
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in data.items() if k in known})


class IllegalTransitionError(IngestionError):
    def __init__(self, unit_id: str, from_status: UnitStatus,
                 to_status: UnitStatus):
        super().__init__(
            ErrorCategory.CONFIG,
            f"unit {unit_id}: illegal transition "
            f"{from_status.value} -> {to_status.value}")
        self.unit_id = unit_id


class Manifest:
    """In-memory manifest, explicitly saved/loaded as JSON."""

    FORMAT_VERSION = 1

    def __init__(self):
        self.units: dict[str, ManifestEntry] = {}

    # -- construction ----------------------------------------------------
    def add_unit(self, entry: ManifestEntry) -> None:
        if entry.unit_id in self.units:
            raise IngestionError.config(f"duplicate unit {entry.unit_id}")
        self.units[entry.unit_id] = entry

    def plan_race_scope(self, season: int, rounds: Iterable[int],
                        session_code: str = "R",
                        schema_version: int | None = None) -> list[str]:
        """Plan an explicit bounded race scope. No defaults, no 'all years':
        callers pass the exact rounds (the CLI enforces explicit scope)."""
        unit_ids = []
        for round_no in rounds:
            race_id = C.make_race_id(season, int(round_no))
            entry = ManifestEntry(
                unit_id=race_id, season=season, round_no=int(round_no),
                session_code=session_code, race_id=race_id,
                schema_version=schema_version, updated_at=utc_now_iso())
            self.add_unit(entry)
            unit_ids.append(race_id)
        return unit_ids

    def plan_tierb_scope(self, seasons: Iterable[int],
                         schema_version: int | None = None) -> list[str]:
        """Plan explicit Tier-B season units (``tierb-<YYYY>``).

        One unit = one season across all seven Tier-B entities (D4): the
        adapter writes one Parquet file per entity under
        ``processed/<entity>/season=<YYYY>/``. Seasons are an explicit
        caller-supplied list — there is no 'all history' default anywhere.
        """
        from raceintel.data.tierb import tierb_unit_id  # local: keeps D3 import-light

        unit_ids = []
        for season in seasons:
            season = int(season)
            unit_id = tierb_unit_id(season)
            entry = ManifestEntry(
                unit_id=unit_id, season=season,
                schema_version=schema_version, updated_at=utc_now_iso())
            self.add_unit(entry)
            unit_ids.append(unit_id)
        return unit_ids

    # -- state machine ----------------------------------------------------
    def transition(self, unit_id: str, to_status: UnitStatus, *,
                   run_id: str | None = None,
                   error_category: str | None = None,
                   error_message: str | None = None,
                   quality_note: str | None = None,
                   skip_reason: str | None = None,
                   output_refs: list | None = None,
                   force: bool = False) -> ManifestEntry:
        entry = self._require(unit_id)
        allowed = LEGAL_TRANSITIONS[entry.status]
        if to_status not in allowed:
            raise IllegalTransitionError(unit_id, entry.status, to_status)
        if entry.status == UnitStatus.COMPLETE and not force:
            # COMPLETE -> DOWNLOADING without force would silently re-fetch.
            raise IllegalTransitionError(unit_id, entry.status, to_status)
        if to_status == UnitStatus.SKIPPED and not skip_reason:
            raise IngestionError.config(
                f"unit {unit_id}: SKIPPED requires an explicit reason")
        # PENDING (requeue) and COMPLETE (success) clear stale error/quality
        # failure text from earlier attempts unless the caller supplies new
        # values; quality notes are carried by the caller explicitly.
        if to_status in (UnitStatus.PENDING, UnitStatus.COMPLETE):
            if error_category is None:
                entry.error_category = None
            if error_message is None:
                entry.error_message = None
        entry.status = to_status
        if run_id is not None:
            entry.run_id = run_id
        if error_category is not None:
            entry.error_category = error_category
        if error_message is not None:
            entry.error_message = error_message
        if quality_note is not None:
            entry.quality_note = quality_note
        if skip_reason is not None:
            entry.skip_reason = skip_reason
        if output_refs is not None:
            entry.output_refs = list(output_refs)
        if to_status == UnitStatus.DOWNLOADING:
            entry.claimed_by = run_id
            entry.claimed_at = utc_now_iso()
        else:
            entry.claimed_by = None
            entry.claimed_at = None
        entry.updated_at = utc_now_iso()
        return entry

    def record_attempt(self, unit_id: str) -> int:
        entry = self._require(unit_id)
        entry.attempts += 1
        entry.updated_at = utc_now_iso()
        return entry.attempts

    def recover_stale(self, max_age_s: float,
                      now_iso: str | None = None) -> list[str]:
        """Return crashed DOWNLOADING units to PENDING.

        Only this method may do so: normal execution never touches a unit
        claimed by another (or dead) run. Staleness is judged on the claim
        timestamp, never on output-file existence.
        """
        from datetime import datetime, timezone

        now = (datetime.fromisoformat(now_iso) if now_iso
               else datetime.now(timezone.utc))
        recovered = []
        for entry in self.units.values():
            if entry.status != UnitStatus.DOWNLOADING or not entry.claimed_at:
                continue
            claimed = datetime.fromisoformat(entry.claimed_at)
            if (now - claimed).total_seconds() > max_age_s:
                entry.status = UnitStatus.PENDING
                entry.claimed_by = None
                entry.claimed_at = None
                entry.updated_at = utc_now_iso()
                recovered.append(entry.unit_id)
        return recovered

    # -- queries -----------------------------------------------------------
    def get(self, unit_id: str) -> ManifestEntry:
        return self._require(unit_id)

    def by_status(self, status: UnitStatus) -> list[ManifestEntry]:
        return [e for e in self.units.values() if e.status == status]

    def status_counts(self) -> dict[str, int]:
        counts = {s.value: 0 for s in UnitStatus}
        for e in self.units.values():
            counts[e.status.value] += 1
        return counts

    # -- persistence --------------------------------------------------------
    def to_dict(self) -> dict:
        return {"format_version": self.FORMAT_VERSION,
                "units": {uid: e.to_dict() for uid, e in self.units.items()}}

    @classmethod
    def from_dict(cls, data: dict) -> "Manifest":
        manifest = cls()
        for uid, raw in data.get("units", {}).items():
            entry = ManifestEntry.from_dict(raw)
            manifest.units[uid] = entry
        return manifest

    def save(self, path: str | Path) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2, sort_keys=True)
                        + "\n")
        return path

    @classmethod
    def load(cls, path: str | Path) -> "Manifest":
        return cls.from_dict(json.loads(Path(path).read_text()))

    def _require(self, unit_id: str) -> ManifestEntry:
        try:
            return self.units[unit_id]
        except KeyError:
            raise IngestionError.config(f"unknown unit {unit_id}") from None
