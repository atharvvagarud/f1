"""Phase-12 historical spatial observation ingestion (P12-2).

Orchestration only; every contract decision lives in P12-1
(``contracts`` / ``validation`` / ``manifest``):

source load -> raw extraction -> canonicalization -> validation ->
atomic artifact write -> hash -> provenance -> manifest upsert.

Source policy: default ``cache-only``. FastF1 exposes no offline flag,
so cache-only is enforced at the repository level by blocking socket
creation during the session load: cached blobs read from disk, any
missing blob raises instead of downloading. A missing local source is
recorded UNAVAILABLE, never silently fetched. ``network`` mode removes
the guard and is explicitly opt-in.

No geometry, no normalization, no downsampling, no smoothing, no
interpolation, no pit-path removal. No predictive imports.
"""

from __future__ import annotations

import json
import socket
from pathlib import Path

import pandas as pd

from raceintel import contracts as C
from raceintel.spatial import contracts as SC
from raceintel.spatial import manifest as SM
from raceintel.spatial import validation as V
from raceintel.spatial.errors import SpatialContractError
from raceintel.spatial.io import (
    artifact_path,
    file_sha256,
    manifest_path,
    read_observations,
    write_observations_atomic,
)

#: P12-2 ingestion implementation version (provenance-adjacent run
#: metadata; the scientific identity stays the logical content hash).
INGESTION_VERSION = "p12-2-v1"

SOURCE_MODE_CACHE_ONLY = "cache-only"
SOURCE_MODE_NETWORK = "network"
SOURCE_MODES = (SOURCE_MODE_CACHE_ONLY, SOURCE_MODE_NETWORK)

SESSION_CODE = "R"

#: Load flags for spatial ingestion: position stream + results identity
#: only. Laps/weather/messages are Tier-A concerns, never re-derived
#: here (faster loads, same cached blobs).
LOAD_FLAGS = {"laps": False, "telemetry": True, "weather": False,
              "messages": False}


class SourceUnavailable(Exception):
    """Local source has no position stream for this race (no download)."""


class SourceLoadFailed(Exception):
    """Race-level load/extraction failure (recorded FAILED, never partial)."""


class _NetworkBlockedError(OSError):
    """Raised when cache-only ingestion attempts any network I/O."""


class _BlockedSocket(socket.socket):
    def __init__(self, *args, **kwargs):
        raise _NetworkBlockedError(
            "network disabled: cache-only spatial ingestion "
            "(missing local FastF1 source)")


def _caused_by_network_block(exc: BaseException) -> bool:
    """True when any link of the cause chain is the cache-only guard.

    HTTP clients (requests/urllib3) wrap raw socket errors, so the
    guard surfaces as __cause__/__context__, never bare.
    """
    seen = set()
    current: BaseException | None = exc
    while current is not None and id(current) not in seen:
        seen.add(id(current))
        if isinstance(current, _NetworkBlockedError):
            return True
        current = current.__cause__ or current.__context__
    return False


class blocked_network:
    """Repository-level cache-only guard: no socket may open inside."""

    def __enter__(self):
        self._real = socket.socket
        socket.socket = _BlockedSocket  # type: ignore[assignment]
        return self

    def __exit__(self, *exc):
        socket.socket = self._real
        return False


def fastf1_version() -> str:
    """Actual FastF1 version of this environment (provenance fact)."""
    try:
        import importlib.metadata as metadata

        return metadata.version("fastf1")
    except Exception:
        import fastf1  # lazy: ingestion-only dependency

        return getattr(fastf1, "__version__", "unknown")


def discover_universe(root: str | Path) -> list[dict]:
    """Authoritative ingestion universe from local Tier-A manifests.

    (season, round_no, race_id) for 2018-2025, sorted. No FastF1, no
    network, no invented calendar: Phase-1 already adjudicated the
    championship scope; P12-2 ingests exactly that universe.
    """
    manifests = Path(root) / "data" / "v2" / "raw" / "manifests"
    universe = []
    for season in range(SC.SPATIAL_DATA_MIN_SEASON,
                        SC.SPATIAL_DATA_MAX_SEASON + 1):
        path = manifests / f"tiera-{season}.json"
        if not path.is_file():
            raise SpatialContractError(
                f"Tier-A manifest missing for season {season}: "
                f"{path} (universe must come from repository evidence)")
        record = json.loads(path.read_text(encoding="utf-8"))
        for race_id, unit in record["units"].items():
            expected = C.make_race_id(int(season), int(unit["round_no"]))
            if race_id != expected:
                raise SpatialContractError(
                    f"Tier-A unit {race_id!r} does not match canonical "
                    f"identity {expected!r}")
            universe.append({"season": int(season),
                             "round_no": int(unit["round_no"]),
                             "race_id": race_id})
    universe.sort(key=lambda e: (e["season"], e["round_no"]))
    return universe


def _default_loader(season: int, round_no: int, cache_dir: Path):
    """Live FastF1 load (import + cache configuration stay lazy)."""
    from raceintel.config import configure_fastf1_cache

    import fastf1

    configure_fastf1_cache(cache_dir)
    session = fastf1.get_session(int(season), int(round_no), SESSION_CODE)
    session.load(**LOAD_FLAGS)
    return session


def load_session(season: int, round_no: int, cache_dir: str | Path,
                 source_mode: str = SOURCE_MODE_CACHE_ONLY,
                 loader=None):
    """Load one Race session under the source policy.

    Raises SourceUnavailable when the local source has no position
    stream (including any network attempt under cache-only); raises
    SourceLoadFailed for genuine race-level load errors.
    """
    if source_mode not in SOURCE_MODES:
        raise SpatialContractError(
            f"source_mode must be one of {list(SOURCE_MODES)}, "
            f"got {source_mode!r}")
    loader = loader or _default_loader
    try:
        if source_mode == SOURCE_MODE_CACHE_ONLY:
            with blocked_network():
                return loader(int(season), int(round_no), Path(cache_dir))
        return loader(int(season), int(round_no), Path(cache_dir))
    except _NetworkBlockedError as exc:
        raise SourceUnavailable(
            f"{season} R{round_no}: no local cached source "
            f"(cache-only; not downloaded)") from exc
    except SourceUnavailable:
        raise
    except SourceLoadFailed:
        raise
    except Exception as exc:
        if source_mode == SOURCE_MODE_CACHE_ONLY and \
                _caused_by_network_block(exc):
            raise SourceUnavailable(
                f"{season} R{round_no}: no local cached source "
                f"(cache-only; not downloaded)") from exc
        name = type(exc).__name__
        if name in ("InvalidSessionError", "NoLapDataError",
                    "DataNotLoadedError") or "proxy" in str(exc).lower() \
                or "failed to load" in str(exc).lower():
            raise SourceUnavailable(
                f"{season} R{round_no}: session unavailable "
                f"({name})") from exc
        raise SourceLoadFailed(
            f"{season} R{round_no}: load failed ({name}: {exc})") from exc


def session_time_s(value) -> float:
    """FastF1 Time (session clock) -> canonical observation_time_s.

    Raw conversion only: finiteness is checked here, but the >= 0
    session-clock rule is enforced by P12-1 validation AFTER the
    zero-fix exclusion (pre-roll sentinel rows carry small negative
    Times and are excluded, never persisted).
    """
    import math

    seconds = float(pd.Timedelta(value).total_seconds())
    if not math.isfinite(seconds):
        raise SpatialContractError(
            f"observation_time_s must be finite (session clock), "
            f"got {value!r}")
    return seconds


def extract_raw(session, race_id: str) -> tuple[pd.DataFrame, list[int]]:
    """Per-driver position streams -> raw frame + expected driver set.

    Raw frame carries persisted columns plus the transient
    ``source_observed_at`` ordering key (absolute FastF1 Date). Driver
    identity is the integer behind FastF1's string driver-number keys;
    display names never participate.
    """
    try:
        pos_data = getattr(session, "pos_data", None)
    except Exception as exc:
        # FastF1 raises DataNotLoadedError (by name; never imported at
        # module scope) when the cached blobs lack the position stream.
        if type(exc).__name__ in ("DataNotLoadedError",) \
                or "not been loaded" in str(exc):
            raise SourceUnavailable(
                f"{race_id}: no position stream in source") from exc
        raise
    if not pos_data:
        raise SourceUnavailable(f"{race_id}: no position stream in source")
    rows = []
    for key, frame in pos_data.items():
        try:
            number = int(str(key))
        except (TypeError, ValueError):
            raise SourceLoadFailed(
                f"{race_id}: non-numeric driver key {key!r}") from None
        if not SC.DRIVER_NUMBER_MIN <= number <= SC.DRIVER_NUMBER_MAX:
            raise SourceLoadFailed(
                f"{race_id}: driver number out of range: {number!r}")
        if frame is None or len(frame) == 0:
            continue
        for record in frame.to_dict(orient="records"):
            rows.append({
                "race_id": race_id,
                "driver_number": number,
                "observation_time_s": session_time_s(record["Time"]),
                V.TRANSIENT_SOURCE_TIME_COLUMN: record["Date"],
                "x": record["X"],
                "y": record["Y"],
                "z": record["Z"],
                "source": record["Source"],
                "status": record["Status"],
            })
    if not rows:
        raise SourceUnavailable(f"{race_id}: position stream is empty")
    raw = pd.DataFrame(rows)
    results = getattr(session, "results", None)
    if results is None or len(results) == 0:
        raise SourceLoadFailed(f"{race_id}: expected driver set "
                               f"unavailable (no results)")
    expected = sorted({int(v) for v in results["DriverNumber"].tolist()})
    return raw, expected


def _source_input_ref(cache_dir: str | Path, season: int,
                      round_no: int) -> str:
    root = Path(cache_dir).resolve()
    try:
        repo = root
        while not (repo / "raceintel").is_dir() or not (repo / "data").is_dir():
            if repo.parent == repo:
                raise ValueError
            repo = repo.parent
        ref = Path(root).relative_to(repo).as_posix()
    except ValueError:
        ref = "data/raw/fastf1_cache"
    return f"{ref}#season={season}/round={round_no:02d}/session=R"


def ingest_race(season: int, round_no: int, race_id: str, *,
                root: str | Path, cache_dir: str | Path,
                source_mode: str = SOURCE_MODE_CACHE_ONLY,
                loader=None) -> dict:
    """Ingest one race: load -> canonicalize -> validate -> write.

    Returns a result record {race_id, status, provenance|reason, stats,
    file_sha256?}. Never raises for per-race outcomes (race-level
    failure and driver-level partiality become manifest rows); raises
    only for programmer errors (bad mode, bad identity).
    """
    if race_id != C.make_race_id(int(season), int(round_no)):
        raise SpatialContractError(
            f"race_id {race_id!r} does not match season={season} "
            f"round_no={round_no}")
    stats: dict = {"season": int(season), "round_no": int(round_no)}
    try:
        session = load_session(season, round_no, cache_dir, source_mode,
                               loader=loader)
    except SourceUnavailable as exc:
        return {"race_id": race_id, "status": SM.STATUS_UNAVAILABLE,
                "reason": str(exc), "stats": stats}
    except SourceLoadFailed as exc:
        return {"race_id": race_id, "status": SM.STATUS_FAILED,
                "reason": str(exc), "stats": stats}
    try:
        raw, expected = extract_raw(session, race_id)
        stats["raw_row_count"] = int(len(raw))
        stats["raw_drivers"] = sorted(raw["driver_number"].unique().tolist())
        canonical = V.canonicalize_observations(raw)
        kept = int(len(canonical))
        zero_fix = int(canonical.attrs.get("excluded_zero_fix_rows", 0))
        nonzero = int((~((raw["x"] == 0) & (raw["y"] == 0)
                           & (raw["z"] == 0))).sum())
        stats["excluded_zero_fix_rows"] = zero_fix
        stats["excluded_exact_duplicate_rows"] = int(nonzero - kept)
        report = V.validate_observations(canonical, race_id=race_id)
        logical = V.logical_content_hash(canonical)
        dest = artifact_path(root, race_id)
        logical_written, file_hash = write_observations_atomic(
            canonical, dest)
        assert logical_written == logical
        present = sorted(canonical["driver_number"].unique().tolist())
        provenance_kwargs: dict = {}
        event = getattr(session, "event", None)
        try:
            name = (event.get("EventName") if event is not None else None)
        except Exception:
            name = None
        if name:
            provenance_kwargs["event_name"] = str(name)
        provenance_kwargs["round_no"] = int(round_no)
        t0 = getattr(session, "t0_date", None)
        try:
            stamp = (pd.Timestamp(t0).isoformat()
                     if t0 is not None and not pd.isna(t0) else None)
        except Exception:
            stamp = None
        if stamp:
            provenance_kwargs["source_session_start_utc"] = stamp
        provenance = SM.build_provenance(
            season=int(season), race_id=race_id, session=SESSION_CODE,
            source_input_ref=_source_input_ref(cache_dir, int(season),
                                               int(round_no)),
            fastf1_version=fastf1_version(),
            raw_row_count=int(len(raw)), kept_row_count=kept,
            excluded_zero_fix_rows=zero_fix,
            excluded_exact_duplicate_rows=int(nonzero - kept),
            driver_numbers=present,
            expected_driver_numbers=list(expected),
            time_min_s=float(report["time_min_s"]),
            time_max_s=float(report["time_max_s"]),
            observed_source_values=report["observed_source_values"],
            observed_status_values=report["observed_status_values"],
            content_sha256=logical, **provenance_kwargs)
        stats.update({"kept_row_count": kept,
                      "driver_numbers": present,
                      "expected_driver_numbers": list(expected),
                      "time_min_s": float(report["time_min_s"]),
                      "time_max_s": float(report["time_max_s"]),
                      "file_sha256": file_hash})
        if present == list(expected):
            return {"race_id": race_id, "status": SM.STATUS_COMPLETE,
                    "provenance": provenance, "stats": stats,
                    "file_sha256": file_hash}
        missing = sorted(set(expected) - set(present))
        extra = sorted(set(present) - set(expected))
        detail = []
        if missing:
            detail.append(f"missing drivers {missing}")
        if extra:
            detail.append(f"unexpected drivers {extra}")
        return {"race_id": race_id, "status": SM.STATUS_PARTIAL,
                "provenance": provenance,
                "reason": f"source present but expected driver set "
                          f"incomplete: {'; '.join(detail)}",
                "stats": stats, "file_sha256": file_hash}
    except SourceUnavailable as exc:
        return {"race_id": race_id, "status": SM.STATUS_UNAVAILABLE,
                "reason": str(exc), "stats": stats}
    except Exception as exc:
        return {"race_id": race_id, "status": SM.STATUS_FAILED,
                "reason": f"{race_id}: {type(exc).__name__}: {exc}",
                "stats": stats}


def verify_complete_artifact(root: str | Path, race_id: str,
                             provenance: dict) -> bool:
    """Resume check: artifact exists, validates, hash matches provenance."""
    try:
        path = artifact_path(root, race_id)
        if not path.is_file():
            return False
        frame = read_observations(path)
        V.validate_observations(frame, race_id=race_id)
        if V.logical_content_hash(frame) != provenance["content_sha256"]:
            return False
        SM.validate_provenance(provenance)
        if sorted(frame["driver_number"].unique().tolist()) != \
                sorted(provenance["driver_numbers"]):
            return False
        return True
    except Exception:
        return False


def apply_result(manifest: dict, result: dict,
                 previous: dict | None = None,
                 root: str | Path | None = None) -> tuple[dict, str]:
    """Fold one ingest result into the manifest.

    Returns (manifest, disposition) where disposition is "recorded" or
    "kept-previous". A failed rebuild never destroys a previously
    verified row: when the fresh outcome is FAILED/UNAVAILABLE but the
    previous COMPLETE artifact still verifies, the known-good row is
    kept and the failure lives in the run log only. In every other
    case the fresh result is recorded (stale rows never mask new
    evidence).
    """
    race_id = result["race_id"]
    status = result["status"]
    if status in (SM.STATUS_COMPLETE, SM.STATUS_PARTIAL):
        kwargs: dict = {"provenance": result["provenance"]}
        if status == SM.STATUS_PARTIAL:
            kwargs["reason"] = result["reason"]
        return SM.set_race_row(manifest, race_id, status=status,
                               **kwargs), "recorded"
    if (previous is not None
            and previous.get("status") == SM.STATUS_COMPLETE
            and previous.get("provenance") is not None
            and root is not None
            and verify_complete_artifact(root, race_id,
                                        previous["provenance"])):
        return manifest, "kept-previous"
    return SM.set_race_row(manifest, race_id, status=status,
                           reason=result["reason"]), "recorded"
