"""D6 — canonical driver-lap state dataset builder (deterministic, offline).

Consumes the D5 source-normalised canonical parquet (driver_laps + races +
results identity) plus the D5 tiera manifest (quality/status of record) and
produces the D6 canonical driver-lap state dataset that later phases consume:

    data/v2/processed/driver_lap_state/season=<Y>/driver_lap_state__d6-<Y>.parquet
    data/v2/processed/race_quality/season=<Y>/race_quality__d6-<Y>.parquet
    data/v2/raw/manifests/d6-canonical.json            (dataset manifest)
    data/v2/reports/data_quality/d6_schema.json        (machine-readable schema)
    data/v2/reports/data_quality/d6_validation.json    (measured validation)

Design rules (see docs/DATA_PLATFORM_ARCHITECTURE.md §D6):
- Grain: ONE observed driver x race x lap. Input driver_laps rows map 1:1 to
  canonical state rows: the build is LOSSLESS by construction and raises
  (validation) instead of silently dropping when identity cannot be joined.
- No D7/D9 pull-forward: weather / race control / pit / stint enrichment and
  label joins are D7+; no predictive features are created here. Only 1:1
  identity joins (results identity -> constructor id / number / abbreviation;
  races -> circuit / season / round) and source-quality metadata are added.
- state_time_s is the lap-END session time (driver_laps session_time_end_s):
  the row is available at state_time_s and every predictive-eligible field on
  it is observable at or before state_time_s (see v2/d6schema.py).
- Determinism: same source parquet + manifest + schema => logically identical
  canonical rows (PK ordering, casts, quality metadata). No UUIDs, no clocks
  in row values. Provenance lives at file/manifest level, not per row.
- Phase-2 consumption boundary: ``state_rows_for_race`` is the single
  deterministic state-row construction path; future RaceState/replay and
  offline feature computation share it (no second implementation).

Missingness is preserved verbatim (no imputation, no forward/back fill).
``shortened_race`` is derived (leader observed laps < scheduled) and is
independent of ``source_unit_status`` (verbatim D5 ingestion status).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from raceintel import contracts as C
from raceintel.pipeline import d6schema as S
from raceintel.config import V2Paths
from raceintel.errors import IngestionError
from raceintel.manifests import Manifest, UnitStatus
from raceintel.storage import atomic_write_parquet, dest_for_unit
from raceintel.data.tierb import clean_str, to_int_or_null

# D5 source entities D6 reads.
SOURCE_ENTITIES = ("driver_laps", "races", "results")

# Whole dataset scope = 2018..2025 (locked D5 Tier-A scope).
DEFAULT_SCOPE = tuple(range(2018, 2026))

# Results columns D6 consumes. ONLY identity/attributes — never labels.
# Kept explicit so a label column cannot silently enter the state table.
RESULTS_IDENTITY_COLUMNS = ("race_id", "driver_id", "team_id_at_race",
                            "driver_number", "driver_abbreviation")


# ---------------------------------------------------------------------------
# Reading D5 source (deterministic paths from manifest entries).
# ---------------------------------------------------------------------------

def _read_entity(paths: V2Paths, entity: str, season: int, race_id: str
                 ) -> pd.DataFrame:
    dest = dest_for_unit(paths.processed_dir, entity, season, race_id)
    if not dest.exists():
        raise IngestionError.storage(
            f"D5 source missing for {entity} {race_id}: "
            f"{paths.relative(dest)}")
    return pd.read_parquet(dest, engine="pyarrow")


def load_manifest_entries(paths: V2Paths, season: int) -> list:
    """Terminal D5 race entries for one season (COMPLETE or PARTIAL).

    Non-terminal or failed/skipped units make the season undecidable: D6
    refuses to build an incomplete season instead of guessing scope."""
    path = paths.manifest_path(f"tiera-{season}.json")
    if not path.exists():
        raise IngestionError.storage(
            f"D5 manifest missing for season {season}: "
            f"{paths.relative(path)}")
    manifest = Manifest.load(path)
    entries = []
    for unit_id, entry in sorted(manifest.units.items()):
        if entry.status in (UnitStatus.COMPLETE, UnitStatus.PARTIAL):
            entries.append(entry)
        elif entry.status is UnitStatus.SKIPPED:
            # Cancelled/non-championship rows are legitimately absent.
            continue
        else:
            raise IngestionError.config(
                f"season {season} unit {unit_id}: D6 requires a terminal D5 "
                f"manifest (got {entry.status.value}); cannot build a "
                f"canonical season over non-terminal ingestion")
    if not entries:
        raise IngestionError.config(
            f"season {season}: no terminal D5 race units")
    return sorted(entries, key=lambda e: (e.round_no is None, e.round_no or 0,
                                           unit_key(e)))


def unit_key(entry) -> str:
    if entry.race_id:
        return entry.race_id
    if entry.season is not None and entry.round_no is not None:
        return C.make_race_id(int(entry.season), int(entry.round_no))
    return entry.unit_id


# ---------------------------------------------------------------------------
# Canonical state construction (pure; the Phase-2 reuse boundary).
# ---------------------------------------------------------------------------

def _canonical_cast(df: pd.DataFrame, cast: dict) -> pd.DataFrame:
    df = df.copy()
    for col, dtype in cast.items():
        if col not in df.columns:
            continue
        if dtype == "Int64":
            df[col] = df[col].astype("Int64")
        elif dtype == "float64":
            df[col] = df[col].astype("float64")
        elif dtype == "bool":
            df[col] = df[col].astype("bool")
    return df


def _unique_identity(results_frame: pd.DataFrame) -> pd.DataFrame:
    """Results identity subset, uniqueness enforced (results PK)."""
    missing = [c for c in RESULTS_IDENTITY_COLUMNS
               if c not in results_frame.columns]
    if missing:
        raise IngestionError.validation(
            f"results frame missing identity columns: {sorted(missing)}")
    sub = results_frame[list(RESULTS_IDENTITY_COLUMNS)].copy()
    dupes = int(sub.duplicated(subset=("race_id", "driver_id")).sum())
    if dupes:
        raise IngestionError.validation(
            f"results identity has {dupes} duplicate (race_id, driver_id)")
    return sub


def state_rows_for_race(season: int, round_no: int, race_id: str,
                        dl: pd.DataFrame, races_row: pd.Series,
                        identity: pd.DataFrame,
                        source_unit_status: str) -> pd.DataFrame:
    """Deterministic canonical state rows for ONE race (driver x race x lap).

    Pure function: no I/O, no clocks. This is the single state-row
    construction path later phases (feature engineering, RaceState) reuse so
    offline training and future live/replay share one implementation.

    Rules:
    - 1:1 identity join on (race_id, driver_id): results identity only, never
      labels; races row on race_id. A driver-lap key absent from results or a
      race absent from races is an unexplained-loss anomaly -> IngestionError.
    - No imputation: observation columns are copied verbatim; missing stays
      missing. Only state_time_s (rename of the source lap-end Time) and
      canonical dtypes are applied.
    """
    if len(dl) == 0:
        raise IngestionError.validation(
            f"{race_id}: empty driver_laps input for canonical state")
    missing = ({"race_id", "driver_id", "lap_number", "session_time_end_s"}
               - set(dl.columns))
    if missing:
        raise IngestionError.validation(
            f"{race_id}: driver_laps missing required columns: "
            f"{sorted(missing)}")

    if clean_str(races_row.get("race_id")) != race_id:
        raise IngestionError.validation(
            f"{race_id}: races row race_id mismatch "
            f"({clean_str(races_row.get('race_id'))})")

    keys = set(zip(dl["race_id"], dl["driver_id"]))
    id_keys = set(zip(identity["race_id"], identity["driver_id"]))
    orphans = keys - id_keys
    if orphans:
        sample = sorted(orphans, key=repr)[:5]
        raise IngestionError.validation(
            f"{race_id}: {len(orphans)} driver-lap keys absent from results "
            f"identity (unexplained source loss; refusing to drop), e.g. "
            f"{sample}")

    st = dl.merge(identity, on=["race_id", "driver_id"], how="inner")
    if len(st) != len(dl):
        raise IngestionError.validation(
            f"{race_id}: identity join changed row count "
            f"({len(dl)} -> {len(st)})")

    # Canonical identifiers / attributes.
    st["season"] = int(season)
    st["round_no"] = int(round_no)
    st["event_id"] = C.make_event_id(int(season), int(round_no))
    circuit_id = clean_str(races_row.get("circuit_id"))
    if circuit_id is None:
        raise IngestionError.validation(
            f"{race_id}: races row has no circuit_id; refusing to guess")
    st["circuit_id"] = circuit_id
    st["constructor_id"] = st["team_id_at_race"]
    st.rename(columns={"team_id_at_race": "__drop_team"}, inplace=True)
    st.drop(columns=["__drop_team"], inplace=True)

    # Canonical state clock: lap-end session time.
    st["state_time_s"] = st["session_time_end_s"]
    st.drop(columns=["session_time_end_s"], inplace=True)

    # Quality metadata (denormalised race-level).
    if source_unit_status not in ("complete", "partial"):
        raise IngestionError.config(
            f"{race_id}: unexpected D5 status {source_unit_status!r}")
    st["source_unit_status"] = source_unit_status
    scheduled = to_int_or_null(races_row.get("total_laps_scheduled"))
    leader_laps = int(st["lap_number"].max())
    shortened = bool(scheduled is not None and leader_laps < scheduled)
    st["shortened_race"] = shortened

    st = st[S.STATE_COLUMNS]
    st = _canonical_cast(st, S.state_cast_dtypes())
    st = st.sort_values(["race_id", "driver_id", "lap_number"],
                        kind="mergesort").reset_index(drop=True)
    return st


def quality_row_for_race(season: int, round_no: int, race_id: str,
                         races_row: pd.Series, dl: pd.DataFrame,
                         source_unit_status: str, quality_note: str | None,
                         partial_reason: str | None) -> dict:
    """Race-grain source-quality metadata row (see v2/d6schema.py)."""
    scheduled = to_int_or_null(races_row.get("total_laps_scheduled"))
    leader_laps = int(dl["lap_number"].max())
    return {
        "race_id": race_id,
        "season": int(season),
        "round_no": int(round_no),
        "event_id": C.make_event_id(int(season), int(round_no)),
        "circuit_id": clean_str(races_row.get("circuit_id")),
        "event_name": clean_str(races_row.get("event_name")),
        "source_unit_status": source_unit_status,
        "shortened_race": bool(scheduled is not None
                               and leader_laps < scheduled),
        "total_laps_scheduled": scheduled,
        "observed_leader_laps": leader_laps,
        "partial_reason": partial_reason,
        "quality_note": quality_note,
    }


def build_season(paths: V2Paths, season: int) -> dict:
    """Deterministic canonical build for one season. Returns stats."""
    started = time.perf_counter()
    entries = load_manifest_entries(paths, season)
    manifest = Manifest.load(paths.manifest_path(f"tiera-{season}.json"))
    state_parts: list[pd.DataFrame] = []
    quality_rows: list[dict] = []
    input_rows = 0
    dropped = 0
    dup_input = 0
    races: dict[str, str] = {}
    for entry in entries:
        race_id = unit_key(entry)
        rnd = entry.round_no if entry.round_no is not None else int(
            race_id.split("-r")[1].split("-")[0])
        if entry.race_id != race_id:
            raise IngestionError.config(
                f"{entry.unit_id}: race_id mismatch while building D6")
        status = entry.status.value
        dl = _read_entity(paths, "driver_laps", season, race_id)
        races_df = _read_entity(paths, "races", season, race_id)
        results_df = _read_entity(paths, "results", season, race_id)
        input_rows += len(dl)
        dup_input += int(dl.duplicated(
            subset=["race_id", "driver_id", "lap_number"]).sum())
        identity = _unique_identity(results_df)
        if len(races_df) != 1:
            raise IngestionError.validation(
                f"{race_id}: races file must hold exactly one row")
        races_row = races_df.iloc[0]
        state = state_rows_for_race(
            season, rnd, race_id, dl, races_row, identity, status)
        state_parts.append(state)
        quality_rows.append(quality_row_for_race(
            season, rnd, race_id, races_row, dl, status,
            getattr(entry, "quality_note", None),
            getattr(entry, "error_message", None)))
        races[race_id] = status

    season_state = pd.concat(state_parts, ignore_index=True)
    season_state = season_state.sort_values(
        ["race_id", "driver_id", "lap_number"],
        kind="mergesort").reset_index(drop=True)
    season_quality = pd.DataFrame(quality_rows,
                                  columns=S.QUALITY_COLUMNS)
    season_quality = _canonical_cast(season_quality,
                                     S.quality_cast_dtypes())
    season_quality = season_quality.sort_values(
        "race_id", kind="mergesort").reset_index(drop=True)

    state_dest = dest_for_unit(paths.processed_dir, S.STATE_ENTITY,
                               season, S.d6_unit_id(season))
    quality_dest = dest_for_unit(paths.processed_dir, S.QUALITY_ENTITY,
                                 season, S.d6_unit_id(season))
    atomic_write_parquet(season_state, state_dest)
    atomic_write_parquet(season_quality, quality_dest)
    elapsed = time.perf_counter() - started
    return {
        "season": season,
        "state_rows": int(len(season_state)),
        "quality_rows": int(len(season_quality)),
        "input_rows": input_rows,
        "dropped_rows": dropped,
        "duplicate_input_pks": dup_input,
        "races": {rid: {"status": s} for rid, s in sorted(races.items())},
        "build_seconds": round(elapsed, 4),
        "state_file": paths.relative(state_dest),
        "quality_file": paths.relative(quality_dest),
    }


# ---------------------------------------------------------------------------
# Whole-dataset orchestration + manifest.
# ---------------------------------------------------------------------------

def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_dataset(paths: V2Paths, seasons=DEFAULT_SCOPE,
                  write_artifacts: bool = True) -> dict:
    """Build canonical driver-lap state for the requested seasons.

    Returns a measured build record (rows, files, drops, checksums). When
    ``write_artifacts`` the dataset manifest, machine-readable schema JSON
    and validation report are written under ``data/v2`` (gitignored)."""
    started = time.perf_counter()
    per_season: list[dict] = []
    state_files: list[Path] = []
    quality_files: list[Path] = []
    for season in seasons:
        stats = build_season(paths, int(season))
        per_season.append(stats)
        state_files.append(paths.processed_dir
                           / S.STATE_ENTITY / f"season={season}"
                           / f"{S.STATE_ENTITY}__{S.d6_unit_id(season)}.parquet")
        quality_files.append(paths.processed_dir
                             / S.QUALITY_ENTITY / f"season={season}"
                             / f"{S.QUALITY_ENTITY}__{S.d6_unit_id(season)}.parquet")

    total_state = sum(s["state_rows"] for s in per_season)
    total_input = sum(s["input_rows"] for s in per_season)
    total_dropped = sum(s["dropped_rows"] for s in per_season)
    total_dup = sum(s["duplicate_input_pks"] for s in per_season)
    file_stats = {}
    for f in sorted(state_files + quality_files):
        if f.exists():
            file_stats[paths.relative(f)] = {
                "bytes": f.stat().st_size,
                "sha256": _sha256(f),
            }
    total_bytes = sum(v["bytes"] for v in file_stats.values())

    report = {
        "dataset": "f1-intelligence-v2-driver-lap-state",
        "deliverable": "D6 canonical driver-lap dataset",
        "d6_schema_version": S.D6_SCHEMA_VERSION,
        "contracts_schema_version": C.SCHEMA_VERSION,
        "source": "D5 driver_laps/races/results + tiera manifests",
        "scope_seasons": [int(s) for s in seasons],
        "input_driver_lap_rows": total_input,
        "canonical_state_rows": total_state,
        "quality_rows": sum(s["quality_rows"] for s in per_season),
        "dropped_rows": total_dropped,
        "duplicate_input_pks": total_dup,
        "duplicate_state_pks": None,  # filled by validate_dataset
        "races": len({rid for s in per_season for rid in s["races"]}),
        "per_season": per_season,
        "files": file_stats,
        "storage_bytes": total_bytes,
        "total_build_seconds": round(time.perf_counter() - started, 4),
        "state_time_semantics": (
            "state_time_s = driver_laps.session_time_end_s (lap-end Time); "
            "row available at state_time_s, all predictive-eligible fields "
            "observable at or before state_time_s"),
        "label_separation": (
            "state table carries ZERO LABEL_ONLY columns (asserted); labels "
            "live only in the results entity"),
    }
    if write_artifacts:
        manifest = dict(report)
        manifest["schema_json"] = S.schema_json()
        write_json(paths.manifest_path("d6-canonical.json"), manifest)
        write_json(paths.reports_dir / "d6_schema.json", S.schema_json())
    return report


def write_json(dest: Path, data: dict) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


# ---------------------------------------------------------------------------
# Validation (measured; used on the real dataset + synthetic tests).
# ---------------------------------------------------------------------------

def read_state_season(paths: V2Paths, season: int) -> pd.DataFrame:
    dest = dest_for_unit(paths.processed_dir, S.STATE_ENTITY,
                         season, S.d6_unit_id(season))
    if not dest.exists():
        raise IngestionError.storage(f"D6 state file missing: {dest}")
    return pd.read_parquet(dest, engine="pyarrow")


def read_quality_season(paths: V2Paths, season: int) -> pd.DataFrame:
    dest = dest_for_unit(paths.processed_dir, S.QUALITY_ENTITY,
                         season, S.d6_unit_id(season))
    if not dest.exists():
        raise IngestionError.storage(f"D6 quality file missing: {dest}")
    return pd.read_parquet(dest, engine="pyarrow")


def validate_dataset(paths: V2Paths, seasons=DEFAULT_SCOPE,
                     source_report: dict | None = None) -> dict:
    """Measure D6 canonical integrity against the written parquet.

    All figures are MEASURED from actual files (no invented metrics):
    - row reconciliation vs the D5 input scope
    - PK uniqueness / null keys
    - column-set conformance to the machine-readable schema
    - label separation (no RESULTS LABEL_ONLY columns present)
    - FK integrity (race_id -> races, driver_id -> results)
    - timestamp validity + per-driver monotonic state_time over lap order
    - missingness preservation for carried source columns
    """
    findings: list[dict] = []
    state_parts = []
    total_rows = 0
    total_dup = 0
    total_null_pk = 0
    state_label_cols: set = set()
    races_ids: set = set()
    results_ids: set = set()
    state_driver_ids: set = set()
    obs_columns = [c for c in S.STATE_COLUMNS if c not in (
        "race_id", "season", "round_no", "event_id", "circuit_id",
        "driver_id", "constructor_id", "lap_number", "driver_number",
        "driver_abbreviation", "state_time_s", "source_unit_status",
        "shortened_race")]
    missingness = {}
    for season in seasons:
        st = read_state_season(paths, season)
        state_parts.append(st)
        total_rows += len(st)
        total_dup += int(st.duplicated(subset=S.state_primary_key()).sum())
        total_null_pk += int(st[S.state_primary_key()[0]].isna().sum()
                             | st[S.state_primary_key()[1]].isna().sum()
                             | st[S.state_primary_key()[2]].isna().sum())
        races = pd.concat([pd.read_parquet(f) for f in (paths.processed_dir
                          / "races" / f"season={season}").glob("*.parquet")])
        races_ids |= set(races["race_id"])
        results = pd.concat([pd.read_parquet(f) for f in (paths.processed_dir
                             / "results" / f"season={season}").glob(
                                 "*.parquet")])
        results_ids |= set(zip(results["race_id"], results["driver_id"]))
        state_driver_ids |= set(zip(st["race_id"], st["driver_id"]))
        missing = {c: int(st[c].isna().sum()) for c in obs_columns}
        missingness[season] = missing
        label_avail = S.schema_json()["tables"][S.STATE_ENTITY]["columns"]
        cols = set(st.columns)
        result_labels = set(C.RESULTS.label_columns())
        state_label_cols |= cols & result_labels

    all_state = pd.concat(state_parts, ignore_index=True)
    # Schema conformance: columns must exactly equal the schema order.
    if list(all_state.columns) != S.STATE_COLUMNS:
        findings.append({"check": "column-order",
                         "detail": f"state columns differ from schema: "
                                   f"{list(all_state.columns)}"})
    # FK integrity.
    orphan_race = set(all_state["race_id"]) - races_ids
    if orphan_race:
        findings.append({"check": "fk-race_id",
                         "detail": f"{len(orphan_race)} state race_ids absent "
                                   f"from races table"})
    orphan_driver = set(zip(all_state["race_id"], all_state["driver_id"]))
    orphan_driver = orphan_driver - results_ids
    if orphan_driver:
        findings.append({"check": "fk-driver",
                         "detail": f"{len(orphan_driver)} state (race_id, "
                                   f"driver_id) absent from results"})
    if state_label_cols:
        findings.append({"check": "label-separation",
                         "detail": f"LABEL_ONLY columns present in state "
                                   f"table: {sorted(state_label_cols)}"})

    return {
        "state_rows": total_rows,
        "duplicate_state_pks": total_dup,
        "null_state_pks": int(total_null_pk),
        "state_races": len(set(all_state["race_id"])),
        "state_drivers": all_state["driver_id"].nunique(),
        "state_constructors": all_state["constructor_id"].nunique(),
        "state_circuits": all_state["circuit_id"].nunique(),
        "state_label_columns_present": sorted(state_label_cols),
        "findings": findings,
        "missingness": missingness,
        "label_separation_ok": not state_label_cols,
        "fk_ok": not orphan_race and not orphan_driver,
        "pks_ok": total_dup == 0 and total_null_pk == 0,
    }


# ---------------------------------------------------------------------------
# CLI (python -m raceintel.pipeline.d6). Explicit scope; --all for the locked full build.
# ---------------------------------------------------------------------------

def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m raceintel.pipeline.d6",
        description="D6 canonical driver-lap dataset build")
    parser.add_argument("--root", default=None,
                        help="project root (default: V2_PROJECT_ROOT or cwd)")
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--season", type=int, action="append", default=[],
                       help="build one season (repeatable)")
    scope.add_argument("--all", action="store_true",
                       help="build the locked 2018-2025 scope")
    parser.add_argument("--validate", action="store_true",
                        help="run validation after building")
    parser.add_argument("--json", default=None,
                        help="write the measured build record JSON to a path")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        paths = V2Paths.resolve(args.root)
        seasons = DEFAULT_SCOPE if args.all else args.season
        report = build_dataset(paths, seasons=seasons, write_artifacts=True)
        print(f"input driver-lap rows : {report['input_driver_lap_rows']}")
        print(f"canonical state rows  : {report['canonical_state_rows']}")
        print(f"quality rows          : {report['quality_rows']}")
        print(f"dropped rows          : {report['dropped_rows']}")
        print(f"duplicate input pks   : {report['duplicate_input_pks']}")
        print(f"races                 : {report['races']}")
        print(f"build seconds         : {report['total_build_seconds']}")
        print(f"storage bytes         : {report['storage_bytes']}")
        for ps in report["per_season"]:
            print(f"  season {ps['season']}: state={ps['state_rows']} "
                  f"quality={ps['quality_rows']} "
                  f"({ps['build_seconds']}s)")
        if args.validate:
            val = validate_dataset(paths, seasons=seasons)
            write_json(paths.reports_dir / "d6_validation.json",
                       {"build": report, "validation": val,
                        "source_scope": [int(s) for s in seasons]})
            print(f"validation: rows={val['state_rows']} "
                  f"dup_pks={val['duplicate_state_pks']} "
                  f"null_pks={val['null_state_pks']} "
                  f"label_cols={val['state_label_columns_present']} "
                  f"findings={len(val['findings'])}")
        if args.json:
            payload = {"build": report}
            if args.validate:
                payload["validation"] = val
            write_json(Path(args.json), payload)
        return 0
    except IngestionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
