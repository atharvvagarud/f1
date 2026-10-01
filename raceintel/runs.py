"""Ingestion run identity (D3).

Every ingestion run carries a unique run ID plus enough metadata to
reconstruct when/what/how. Only portable, project-relative configuration
enters the record — never absolute personal paths, never secrets.
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def new_run_id() -> str:
    return uuid.uuid4().hex


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    started_at: str
    source: str
    source_lib_version: str
    schema_version: int
    scope: dict
    config_snapshot: dict
    status: str = "running"
    finished_at: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict) -> "RunRecord":
        known = ("run_id", "started_at", "source", "source_lib_version",
                 "schema_version", "scope", "config_snapshot",
                 "status", "finished_at")
        return cls(**{k: data[k] for k in known if k in data})

    def finished(self, status: str) -> "RunRecord":
        return RunRecord(
            run_id=self.run_id, started_at=self.started_at,
            source=self.source, source_lib_version=self.source_lib_version,
            schema_version=self.schema_version, scope=dict(self.scope),
            config_snapshot=dict(self.config_snapshot), status=status,
            finished_at=utc_now_iso())


def start_run(source: str, source_lib_version: str, schema_version: int,
              scope: dict, config_snapshot: dict) -> RunRecord:
    return RunRecord(
        run_id=new_run_id(), started_at=utc_now_iso(), source=source,
        source_lib_version=source_lib_version, schema_version=schema_version,
        scope=dict(scope), config_snapshot=dict(config_snapshot))
