"""D9 — derived temporal state + outcome labels (deterministic, offline).

Consumes the D7 temporally-enriched canonical driver-lap state and the D5
canonical supporting entities (results / pit_stops) plus the D6 race-quality
metadata and produces the two D9 canonical outputs:

    data/v2/processed/driver_lap_state_d9/season=<Y>/driver_lap_state_d9__d9-<Y>.parquet
    data/v2/processed/race_driver_labels/season=<Y>/race_driver_labels__d9-<Y>.parquet
    data/v2/raw/manifests/d9-canonical.json        (dataset manifest)
    data/v2/reports/data_quality/d9_schema.json    (machine-readable schema)
    data/v2/reports/data_quality/d9_validation.json(measured validation)

Implementation map (D9 mission §1 / plan §D9):

| D9 field / output            | source columns            | formula / rule                      | availability | grain | output table            |
|------------------------------|---------------------------|-------------------------------------|--------------|-------|-------------------------|
| track_state                  | D6/D7 track_status code   | last code char -> token             | IN_LAP       | lap   | driver_lap_state_d9     |
| flag_yellow / flag_safety_car/ flag_red / flag_vsc | track_state token | equality on derived token  | IN_LAP | lap | driver_lap_state_d9 |
| race_leader_laps_at_state    | lap_number, state_time_s  | max completed lap with time <= t     | LAP_END      | lap   | driver_lap_state_d9     |
| race_progress_frac           | leader laps, scheduled    | leader / scheduled                  | LAP_END      | lap   | driver_lap_state_d9     |
| pit_stops_completed_so_far   | D5 pit_stops (full stops) | count pit_out_s <= state_time_s     | LAP_END      | lap   | driver_lap_state_d9     |
| laps_since_last_pit_stop     | D5 pit_stops (full stops) | lap - latest exit lap               | LAP_END      | lap   | driver_lap_state_d9     |
| stint_lap                    | D7 stint_start_lap        | lap - stint_start_lap + 1           | LAP_END      | lap   | driver_lap_state_d9     |
| outcome labels               | D5 results (official)     | verbatim facts + derived-fact flags | LABEL_ONLY   | race x driver | race_driver_labels  |

Rules enforced (see v2/d9schema.py):
- D9 derived state preserves the D6/D7 grain exactly (189,420 -> 189,420).
- state_time_s stays the D6 lap-end clock; every derived value is computable
  at or before state_time_s (no future laps/weather/RC/pit/stint/results).
- Race-control state is derived deterministically from the per-lap TrackStatus
  code channel (FastF1 3.7.0 mapping); NO message-text state machine and NO
  use of the 69 untimestamped 2018-r02 messages.
- Labels are a physically separate artifact (race x driver, official result
  population). No LABEL_ONLY/POST_RACE outcome column exists in any state
  table. Binary DNF target DEFERRED; factual classification preserved.
- Phase-2 feature families (pace, relative/degradation, traffic, priors,
  momentum, strategy, interactions) are NOT implemented.
- Telemetry remains deferred (ADR-0001): D9 uses no telemetry.
- Deterministic: pure per-race functions reusable for a full build, one race,
  or a state cutoff (training/serving parity; RaceState NOT implemented).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import resource
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from raceintel import contracts as C
from raceintel.pipeline import d7schema as D7
from raceintel.pipeline import d9schema as S
from raceintel.config import V2Paths
from raceintel.errors import IngestionError
from raceintel.storage import atomic_write_parquet, dest_for_unit

DEFAULT_SCOPE = tuple(range(2018, 2026))

_CLOCK_EPS = 1e-6

# Result columns consumed verbatim into the label artifact (season is derived
# from race_id because the D5 results entity does not carry a season column).
LABEL_SOURCE_COLUMNS = ("race_id", "driver_id", "driver_abbreviation",
                        "position_final", "classified_position",
                        "position_text", "status_text", "points",
                        "laps_completed")


# ---------------------------------------------------------------------------
# Pure derived-state helpers (offline-testable, deterministic).
# ---------------------------------------------------------------------------

def last_track_status_code(value) -> str | None:
    """The TrackStatus code in effect at the lap boundary.

    FastF1 appends each new status code to the lap's TrackStatus string in
    chronological order as the status changes overlap the lap; the LAST
    character is therefore the state at/around the lap's end (the state clock).
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    text = str(value).strip()
    if not text:
        return None
    return text[-1]


def track_state_from_status(value) -> str | None:
    code = last_track_status_code(value)
    if code is None:
        return None
    return S.TRACK_STATE_CODES.get(code)


def derive_track_state(state: pd.DataFrame) -> pd.DataFrame:
    """Append track_state + flag_* columns from the source track_status.

    Mutates-and-returns a copy of ``state``. Missing/empty/unknown statuses
    become null (never invented certainty)."""
    out = state.copy()
    if "track_status" not in out.columns:
        out["track_state"] = None
        for col in ("flag_yellow", "flag_safety_car", "flag_red", "flag_vsc"):
            out[col] = None
        return out
    tokens = out["track_status"].map(track_state_from_status)
    out["track_state"] = tokens

    def _flag(pred):
        series = tokens.map(lambda t: bool(pred(t)) if t is not None else None)
        return series.astype("boolean")

    out["flag_yellow"] = _flag(lambda t: t == "yellow")
    out["flag_safety_car"] = _flag(lambda t: t == "safety_car")
    out["flag_red"] = _flag(lambda t: t == "red_flag")
    out["flag_vsc"] = _flag(lambda t: t in ("vsc", "vsc_ending"))
    return out


def race_leader_laps_at_state(state: pd.DataFrame) -> pd.Series:
    """Per-row leader completed-lap count at state_time_s (past-only).

    For each row, the maximum lap_number over all drivers' state rows with
    state_time_s <= this row's state_time_s. Rows sharing an identical time
    receive the same value (the group maximum). Deterministic regardless of
    input row order."""
    sub = state[["state_time_s", "lap_number"]].copy()
    srt = sub.sort_values("state_time_s", kind="mergesort")
    lap = srt["lap_number"].astype("int64").to_numpy()
    times = srt["state_time_s"].to_numpy(dtype=float)
    cum = np.maximum.accumulate(lap)
    uniq, inv = np.unique(times, return_inverse=True)
    group_max = np.zeros(len(uniq), dtype=np.int64)
    np.maximum.at(group_max, inv, cum)
    srt["_leader_laps"] = group_max[inv]
    result = srt.sort_index()["_leader_laps"]
    result.index = state.index
    return result


def derive_race_progress(state: pd.DataFrame,
                         scheduled_laps: int | None) -> pd.DataFrame:
    """Append race_leader_laps_at_state and race_progress_frac."""
    out = state.copy()
    if "race_leader_laps_at_state" not in out.columns:
        out["race_leader_laps_at_state"] = race_leader_laps_at_state(out)
    if scheduled_laps is None or scheduled_laps <= 0:
        out["race_progress_frac"] = None
    else:
        out["race_progress_frac"] = (out["race_leader_laps_at_state"]
                                     .astype("float64") / float(scheduled_laps))
    return out


def full_stop_exits(pit_stops: pd.DataFrame, state: pd.DataFrame
                    ) -> pd.DataFrame:
    """Full-stop exit events (driver_id, exit_s, exit_lap) for one race.

    A full stop has BOTH pit_in_s and pit_out_s. The exit lap is resolved 1:1
    from the canonical state row carrying that exact pit_out_s (as in D7)."""
    full = pit_stops[pit_stops["pit_in_s"].notna()
                     & pit_stops["pit_out_s"].notna()]
    full = full[["driver_id", "pit_out_s"]].copy()
    markers = state[state["pit_out_s"].notna()][
        ["driver_id", "pit_out_s", "lap_number"]].sort_values(
        "lap_number", kind="mergesort").drop_duplicates(
        subset=["driver_id", "pit_out_s"], keep="first")
    markers["pit_out_s"] = markers["pit_out_s"].astype("float64")
    full["pit_out_s"] = full["pit_out_s"].astype("float64")
    exits = full.merge(markers, on=["driver_id", "pit_out_s"], how="left")
    if len(exits) != len(full):
        raise IngestionError.validation(
            "D9 pit: full-stop exit-lap resolution changed row count")
    unresolved = int(exits["lap_number"].isna().sum())
    if unresolved:
        raise IngestionError.validation(
            f"D9 pit: {unresolved} full-stop exits without a canonical exit "
            f"lap marker (source inconsistency); refusing to guess")
    return exits.rename(columns={"pit_out_s": "exit_s",
                                 "lap_number": "exit_lap"})


def derive_pit_history_state(state: pd.DataFrame,
                             pit_stops: pd.DataFrame) -> pd.DataFrame:
    """Append pit_stops_completed_so_far + laps_since_last_pit_stop.

    Counts/laps are per (race, driver) over FULL stops only (entry+exit both
    observed) with pit_out_s <= state_time_s. Asymmetric in-only / out-only
    stops are never counted; future stops have zero effect."""
    out = state.copy()
    counts = pd.Series(np.zeros(len(out), dtype=np.int64), index=out.index)
    since = pd.Series(pd.NA, index=out.index, dtype="Int64")
    if pit_stops is not None and len(pit_stops):
        exits = full_stop_exits(pit_stops, out)
        if len(exits):
            for driver_id, ev in exits.groupby("driver_id", sort=True):
                ev = ev.sort_values("exit_s", kind="mergesort")
                times = ev["exit_s"].to_numpy(dtype=float)
                laps = ev["exit_lap"].to_numpy(dtype=np.int64)
                mask = (out["driver_id"] == driver_id).to_numpy()
                ts = out.loc[mask, "state_time_s"].to_numpy(dtype=float)
                lap_no = out.loc[mask, "lap_number"].to_numpy(dtype=np.int64)
                idx = np.searchsorted(times, ts, side="right")
                counts[mask] = idx
                valid = idx > 0
                chosen = idx[valid] - 1
                since_vals = (lap_no[valid].astype(np.int64)
                              - laps[chosen])
                out_idx = out.index[mask][valid]
                since.loc[out_idx] = pd.array(since_vals, dtype="Int64")
    out["pit_stops_completed_so_far"] = counts
    out["laps_since_last_pit_stop"] = since
    return out


def derive_stint_lap(state: pd.DataFrame) -> pd.DataFrame:
    """Append stint_lap = lap_number - stint_start_lap + 1 (current stint)."""
    out = state.copy()
    start = out.get("stint_start_lap")
    if start is None:
        out["stint_lap"] = None
        return out
    lap = out["lap_number"].astype("Int64")
    valid = start.notna() & (start <= out["lap_number"])
    out["stint_lap"] = pd.Series(pd.NA, index=out.index, dtype="Int64")
    out.loc[valid, "stint_lap"] = (
        lap[valid] - start[valid] + 1).astype("Int64")
    return out


def derived_state_for_race(state_d7: pd.DataFrame,
                           scheduled_laps: int | None,
                           pit_stops: pd.DataFrame | None,
                           race_id: str) -> pd.DataFrame:
    """Deterministic D9 derived-state construction for ONE race.

    Pure function (no I/O): applies the D9 derived columns onto the D7
    canonical enriched state for one race and casts/orders to the D9 schema.
    Reusable for a full build, one race, or a state-time cutoff."""
    if len(state_d7) == 0:
        raise IngestionError.validation(f"{race_id}: empty D7 state to derive")
    if set(state_d7["race_id"].astype(str).unique()) != {race_id}:
        raise IngestionError.validation(
            f"{race_id}: derived_state_for_race got other races "
            f"({sorted(set(state_d7['race_id'].astype(str).unique()))})")
    before = len(state_d7)
    out = derive_track_state(state_d7)
    out = derive_race_progress(out, scheduled_laps)
    out = derive_pit_history_state(
        out, pit_stops if pit_stops is not None
        else pd.DataFrame(columns=["race_id", "driver_id", "lap_number",
                                   "pit_in_s", "pit_out_s"]))
    out = derive_stint_lap(out)
    if len(out) != before:
        raise IngestionError.validation(
            f"{race_id}: D9 derivation changed row count "
            f"({before} -> {len(out)}); grain violated")
    out = out[S.STATE_COLUMNS]
    cast = S.state_cast_dtypes()
    for col, dtype in cast.items():
        if dtype == "Int64":
            out[col] = out[col].astype("Int64")
        elif dtype == "float64":
            out[col] = out[col].astype("float64")
        elif dtype == "boolean":
            out[col] = out[col].astype("boolean")
        elif dtype == "bool":
            out[col] = out[col].astype("bool")
    out = out.sort_values(["race_id", "driver_id", "lap_number"],
                          kind="mergesort").reset_index(drop=True)
    return out


# ---------------------------------------------------------------------------
# Label construction (pure; official result evidence only).
# ---------------------------------------------------------------------------

def labels_from_results(results: pd.DataFrame) -> pd.DataFrame:
    """Official outcome-label rows for one race's results.

    Outcome facts are copied verbatim from the authoritative FastF1 official
    results (never inferred from the final observed lap). Derived-fact flags:
    classified_flag (classified_position not null), winner_flag (position_final
    == 1), podium_flag (position_final in 1..3), points_finish_flag
    (points > 0). No binary DNF target is created (deferred)."""
    missing = [c for c in LABEL_SOURCE_COLUMNS if c not in results.columns]
    if missing:
        raise IngestionError.validation(
            f"results missing label source columns: {sorted(missing)}")
    out = results[list(LABEL_SOURCE_COLUMNS)].copy()
    out["season"] = out["race_id"].str[:4].astype(int)
    pos = out["position_final"]
    out["classified_flag"] = out["classified_position"].notna()
    out["winner_flag"] = pos.eq(1).where(pos.notna(), pd.NA)
    out["podium_flag"] = pos.isin([1, 2, 3]).where(pos.notna(), pd.NA)
    pts = out["points"]
    out["points_finish_flag"] = pts.notna() & (pts > 0)
    out = out[S.LABEL_COLUMNS]
    cast = S.label_cast_dtypes()
    for col, dtype in cast.items():
        if dtype == "Int64":
            out[col] = out[col].astype("Int64")
        elif dtype == "float64":
            out[col] = out[col].astype("float64")
        elif dtype == "boolean":
            out[col] = out[col].astype("boolean")
        elif dtype == "object":
            pass
    out = out.sort_values(["race_id", "driver_id"], kind="mergesort")
    out = out.reset_index(drop=True)
    return out


# ---------------------------------------------------------------------------
# Reading canonical inputs.
# ---------------------------------------------------------------------------

def _read_entity(paths: V2Paths, entity: str, season: int, race_id: str
                 ) -> pd.DataFrame:
    dest = dest_for_unit(paths.processed_dir, entity, season, race_id)
    if not dest.exists():
        raise IngestionError.storage(
            f"source missing for {entity} {race_id}: {paths.relative(dest)}")
    return pd.read_parquet(dest, engine="pyarrow")


def read_d7_state_season(paths: V2Paths, season: int) -> pd.DataFrame:
    return _read_entity(paths, D7.STATE_ENTITY, int(season),
                        D7.d7_unit_id(int(season)))


def read_d9_state_season(paths: V2Paths, season: int) -> pd.DataFrame:
    dest = dest_for_unit(paths.processed_dir, S.STATE_ENTITY, int(season),
                         S.d9_unit_id(int(season)))
    if not dest.exists():
        raise IngestionError.storage(f"D9 state file missing: {dest}")
    return pd.read_parquet(dest, engine="pyarrow")


def read_d9_label_season(paths: V2Paths, season: int) -> pd.DataFrame:
    dest = dest_for_unit(paths.processed_dir, S.LABEL_ENTITY, int(season),
                         S.d9_unit_id(int(season)))
    if not dest.exists():
        raise IngestionError.storage(f"D9 label file missing: {dest}")
    return pd.read_parquet(dest, engine="pyarrow")


def _read_d6_quality(paths: V2Paths, season: int) -> pd.DataFrame:
    return _read_entity(paths, "race_quality", int(season),
                        f"d6-{int(season)}")


# ---------------------------------------------------------------------------
# Season / whole-dataset orchestration.
# ---------------------------------------------------------------------------

def build_season(paths: V2Paths, season: int) -> dict:
    """Deterministic D9 build for one season (derived state + labels)."""
    started = time.perf_counter()
    state_d7 = read_d7_state_season(paths, int(season))
    quality = _read_d6_quality(paths, int(season))
    scheduled = {row["race_id"]: row["total_laps_scheduled"]
                 for _, row in quality.iterrows()}
    race_ids = sorted(state_d7["race_id"].astype(str).unique())
    state_parts = []
    label_parts = []
    races = {}
    for race_id in race_ids:
        sub = state_d7[state_d7["race_id"] == race_id].reset_index(drop=True)
        sl = scheduled.get(race_id)
        pits = _read_entity(paths, "pit_stops", int(season), race_id)
        d9_state = derived_state_for_race(sub, sl, pits, race_id)
        state_parts.append(d9_state)
        results = _read_entity(paths, "results", int(season), race_id)
        label_parts.append(labels_from_results(results))
        races[race_id] = {"state_rows": int(len(d9_state)),
                          "label_rows": int(len(results))}
    season_state = pd.concat(state_parts, ignore_index=True)
    season_state = season_state.sort_values(
        ["race_id", "driver_id", "lap_number"],
        kind="mergesort").reset_index(drop=True)
    season_labels = pd.concat(label_parts, ignore_index=True)
    season_labels = season_labels.sort_values(
        ["race_id", "driver_id"], kind="mergesort").reset_index(drop=True)
    state_dest = dest_for_unit(paths.processed_dir, S.STATE_ENTITY,
                               int(season), S.d9_unit_id(int(season)))
    label_dest = dest_for_unit(paths.processed_dir, S.LABEL_ENTITY,
                               int(season), S.d9_unit_id(int(season)))
    atomic_write_parquet(season_state, state_dest)
    atomic_write_parquet(season_labels, label_dest)
    return {
        "season": int(season),
        "state_rows": int(len(season_state)),
        "label_rows": int(len(season_labels)),
        "races": {rid: r for rid, r in sorted(races.items())},
        "state_file": paths.relative(state_dest),
        "label_file": paths.relative(label_dest),
        "build_seconds": round(time.perf_counter() - started, 4),
    }


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def write_json(dest: Path, data: dict) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def build_dataset(paths: V2Paths, seasons=DEFAULT_SCOPE,
                  write_artifacts: bool = True) -> dict:
    started = time.perf_counter()
    per_season = []
    files = []
    for season in seasons:
        stats = build_season(paths, int(season))
        per_season.append(stats)
        files.append(paths.processed_dir / S.STATE_ENTITY
                     / f"season={int(season)}"
                     / f"{S.STATE_ENTITY}__{S.d9_unit_id(int(season))}.parquet")
        files.append(paths.processed_dir / S.LABEL_ENTITY
                     / f"season={int(season)}"
                     / f"{S.LABEL_ENTITY}__{S.d9_unit_id(int(season))}.parquet")
    total_state = sum(s["state_rows"] for s in per_season)
    total_labels = sum(s["label_rows"] for s in per_season)
    file_stats = {}
    for f in sorted(files):
        if f.exists():
            file_stats[paths.relative(f)] = {
                "bytes": f.stat().st_size,
                "sha256": _sha256(f),
            }
    total_bytes = sum(v["bytes"] for v in file_stats.values())
    elapsed = time.perf_counter() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss
    report = {
        "dataset": "f1-intelligence-v2-phase1-d9",
        "deliverable": "D9 derived temporal state + outcome labels",
        "d9_schema_version": S.D9_SCHEMA_VERSION,
        "base_d7_schema_version": D7.D7_SCHEMA_VERSION,
        "contracts_schema_version": C.SCHEMA_VERSION,
        "source": ("D7 driver_lap_state + D5 pit_stops/results + D6 "
                   "race_quality"),
        "telemetry": "deferred (ADR-0001); D9 uses no telemetry",
        "scope_seasons": [int(s) for s in seasons],
        "state_rows": total_state,
        "label_rows": total_labels,
        "per_season": per_season,
        "files": file_stats,
        "storage_bytes": total_bytes,
        "peak_rss_bytes": int(rss),
        "total_build_seconds": round(elapsed, 4),
    }
    if write_artifacts:
        manifest = dict(report)
        manifest["schema_json"] = S.schema_json()
        write_json(paths.manifest_path("d9-canonical.json"), manifest)
        write_json(paths.reports_dir / "d9_schema.json", S.schema_json())
    return report


# ---------------------------------------------------------------------------
# Validation + cross-source label comparison (measured).
# ---------------------------------------------------------------------------

def validate_dataset(paths: V2Paths, seasons=DEFAULT_SCOPE) -> dict:
    findings = []
    state_parts = []
    label_parts = []
    total_state = 0
    total_labels = 0
    dup_state = 0
    dup_label = 0
    null_state = 0
    null_label = 0
    result_labels = set(C.RESULTS.label_columns())
    label_cols_in_state = set()
    temporal = {"leader_laps_lt_lap": 0, "progress_out_of_range": 0,
                "laps_since_pit_negative": 0, "stint_lap_lt_1": 0,
                "flag_inconsistent": 0}
    track_token_counts = {}
    for season in seasons:
        st = read_d9_state_season(paths, int(season))
        lb = read_d9_label_season(paths, int(season))
        state_parts.append(st)
        label_parts.append(lb)
        total_state += len(st)
        total_labels += len(lb)
        dup_state += int(st.duplicated(subset=list(S.state_primary_key())).sum())
        dup_label += int(lb.duplicated(subset=list(S.label_primary_key())).sum())
        null_state += int((st["race_id"].isna() | st["driver_id"].isna()
                           | st["lap_number"].isna()).sum())
        null_label += int((lb["race_id"].isna() | lb["driver_id"].isna()).sum())
        label_cols_in_state |= set(st.columns) & result_labels
        both = st[st["race_leader_laps_at_state"].notna()
                  & st["lap_number"].notna()]
        temporal["leader_laps_lt_lap"] += int(
            (both["race_leader_laps_at_state"] < both["lap_number"]).sum())
        pr = st[st["race_progress_frac"].notna()]
        temporal["progress_out_of_range"] += int(
            ((pr["race_progress_frac"] < 0)
             | (pr["race_progress_frac"] > 1.0 + _CLOCK_EPS)).sum())
        since = st[st["laps_since_last_pit_stop"].notna()]
        temporal["laps_since_pit_negative"] += int(
            (since["laps_since_last_pit_stop"] < 0).sum())
        sl = st[st["stint_lap"].notna()]
        temporal["stint_lap_lt_1"] += int((sl["stint_lap"] < 1).sum())
        ts = st[st["track_state"].notna()]
        if len(ts):
            flags = ts[["flag_yellow", "flag_safety_car", "flag_red",
                        "flag_vsc"]].sum(axis=1)
            expected = (ts["track_state"] != "all_clear").astype(int)
            temporal["flag_inconsistent"] += int((flags != expected).sum())
        track_token_counts[season] = {
            (str(k) if k is not None else "null"): int(v)
            for k, v in st["track_state"].value_counts(
                dropna=False).to_dict().items()}
    if list(state_parts[0].columns) != S.STATE_COLUMNS:
        findings.append({"check": "state-column-order",
                         "detail": "D9 state columns differ from schema"})
    if list(label_parts[0].columns) != S.LABEL_COLUMNS:
        findings.append({"check": "label-column-order",
                         "detail": "D9 label columns differ from schema"})
    if label_cols_in_state:
        findings.append({"check": "label-separation",
                         "detail": f"outcome columns present in state: "
                                   f"{sorted(label_cols_in_state)}"})
    state_all = pd.concat(state_parts, ignore_index=True)
    label_all = pd.concat(label_parts, ignore_index=True)
    # winner invariant
    win = label_all[label_all["position_final"] == 1].groupby(
        "race_id").size()
    winner_exceptions = sorted(
        race for race, c in win.items() if c != 1)
    return {
        "state_rows": total_state,
        "label_rows": total_labels,
        "state_duplicate_pks": dup_state,
        "label_duplicate_pks": dup_label,
        "state_null_pks": null_state,
        "label_null_pks": null_label,
        "label_columns_in_state": sorted(label_cols_in_state),
        "temporal": temporal,
        "winner_invariant_exceptions": winner_exceptions,
        "track_state_token_counts": track_token_counts,
        "findings": findings,
        "integrity_ok": (dup_state == 0 and null_state == 0
                         and dup_label == 0 and null_label == 0
                         and not label_cols_in_state
                         and all(v == 0 for v in temporal.values())
                         and not winner_exceptions and not findings),
    }


def _read_hist_results(paths: V2Paths, season: int) -> pd.DataFrame:
    dest = dest_for_unit(paths.processed_dir, "hist_results", int(season),
                         f"tierb-{int(season)}")
    if not dest.exists():
        raise IngestionError.storage(
            f"D4 Tier-B hist_results missing for season {season}: "
            f"{paths.relative(dest)}")
    return pd.read_parquet(dest, engine="pyarrow")


def cross_source_label_comparison(paths: V2Paths, seasons=DEFAULT_SCOPE
                                  ) -> dict:
    """Compare D9 factual labels vs D4 Tier-B hist_results (2018-2025).

    Read-only comparison; disagreements are reported, never overwritten. The
    known 3 DNS/withdrawn position differences (FastF1 leaves them unordered;
    Jolpica ranks them at the back) should remain the only position_final
    disagreements."""
    label_all = pd.concat([read_d9_label_season(paths, s)
                           for s in seasons], ignore_index=True)
    label_all["round_no"] = label_all["race_id"].str.split("-").str[1].str[1:]
    label_all["round_no"] = label_all["round_no"].astype(int)
    tier_parts = [_read_hist_results(paths, int(s)) for s in seasons]
    hist = pd.concat(tier_parts, ignore_index=True)
    merged = label_all.merge(
        hist[["season", "round_no", "driver_id", "position", "position_text",
              "points", "status"]],
        on=["season", "round_no", "driver_id"], how="left",
        suffixes=("_label", "_tierb"))
    pos_diffs = merged[merged["position_final"].notna()
                       & merged["position"].notna()
                       & (merged["position_final"] != merged["position"])]
    ff_null_jr = merged[merged["position_final"].isna()
                        & merged["position"].notna()]
    token_diffs = merged[merged["position_text_label"].notna()
                         & merged["position_text_tierb"].notna()
                         & (merged["position_text_label"]
                            != merged["position_text_tierb"])]
    points_diffs = merged[
        merged["points_label"].notna() & merged["points_tierb"].notna()
        & (merged["points_label"] != merged["points_tierb"])]
    return {
        "label_rows_compared": int(len(merged)),
        "tierb_matches": int(merged["position"].notna().sum()),
        "position_final_disagreements": [
            {"race_id": r["race_id"], "driver_id": r["driver_id"],
             "fastf1": int(r["position_final"]),
             "jolpica": int(r["position"])}
            for _, r in pos_diffs.iterrows()],
        "fastf1_null_jolpica_ranked": [
            {"race_id": r["race_id"], "driver_id": r["driver_id"],
             "fastf1_position": None, "jolpica_position": int(r["position"]),
             "token": r["position_text_label"]}
            for _, r in ff_null_jr.iterrows()],
        "position_text_disagreements": int(len(token_diffs)),
        "points_disagreements": int(len(points_diffs)),
    }


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m raceintel.pipeline.d9",
        description="D9 derived temporal state + outcome labels build")
    parser.add_argument("--root", default=None)
    scope = parser.add_mutually_exclusive_group(required=True)
    scope.add_argument("--season", type=int, action="append", default=[])
    scope.add_argument("--all", action="store_true")
    parser.add_argument("--validate", action="store_true")
    parser.add_argument("--json", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        paths = V2Paths.resolve(args.root)
        seasons = DEFAULT_SCOPE if args.all else args.season
        report = build_dataset(paths, seasons=seasons, write_artifacts=True)
        print(f"state rows  : {report['state_rows']}")
        print(f"label rows  : {report['label_rows']}")
        print(f"storage MB  : {round(report['storage_bytes']/1e6, 2)}")
        print(f"build secs  : {report['total_build_seconds']}")
        if args.validate:
            val = validate_dataset(paths, seasons=seasons)
            x = cross_source_label_comparison(paths, seasons=seasons)
            write_json(paths.reports_dir / "d9_validation.json",
                       {"build": report, "validation": val,
                        "cross_source": x})
            print(f"validation  : state={val['state_rows']} "
                  f"labels={val['label_rows']} "
                  f"dup_state={val['state_duplicate_pks']} "
                  f"dup_label={val['label_duplicate_pks']} "
                  f"integrity={val['integrity_ok']} "
                  f"findings={len(val['findings'])}")
            print(f"cross-source: compared={x['label_rows_compared']} "
                  f"position_diffs={len(x['position_final_disagreements'])}")
        if args.json:
            payload = {"build": report}
            if args.validate:
                payload["validation"] = val
                payload["cross_source"] = x
            write_json(Path(args.json), payload)
        return 0
    except IngestionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
