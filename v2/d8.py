"""D8 — telemetry decision evidence: measurement + candidate summaries.

D8 is a DECISION stage (plan §31 / §D8). This module measures the actual
telemetry available in the FastF1 cache for a bounded representative sample of
Race sessions and evaluates a SMALL candidate set of lap-level summaries so the
retention decision is evidence-backed. It NEVER writes canonical telemetry
data: the FastF1 cache stays the recoverable raw/source layer and raw streams
are never copied into ``data/v2``.

Scope of this module:
- a bounded representative sample (one 2018 race, 2019 wet/chaotic, 2021
  sprint-weekend GP, 2021 Belgium shortened, 2022 Monaco, 2023 normal, 2024,
  2025) — all already cached, no downloads;
- actual channel inventory (columns / dtypes / units / value ranges) from the
  cached ``car_data`` streams;
- telemetry coverage vs the D6 canonical driver-lap windows (lap_start_s ..
  state_time_s): drivers, laps, samples/lap, zero-sample windows;
- scale: samples/race, sample bytes, cache file sizes, extraction/aggregation
  time, peak RSS; whole-scope projection clearly labelled PROJECTED;
- a SMALL candidate lap-level summary set with exact formulas, units, temporal
  availability (LAP_END), missingness policy and plausible use — evaluated for
  computability/quality on the sample, NOT materialized canonically;
- position-data scale (X/Y/Z) as input to the "separate track asset pipeline"
  assessment (no canonical retention, no track built).

Determinism: functions here are pure/deterministic; telemetry reading is
read-only over the cache and canonical D5/D6 parquet. No network is ever used.
All measurements are written to a gitignored JSON report
(``data/v2/reports/data_quality/d8_telemetry_sample.json``).

Decision output (see ``docs/adr/ADR-0001-telemetry-retention.md``): telemetry
is DEFERRED from the canonical Phase-1 dataset. The FastF1 cache is retained
as the source layer; ``telemetry_summary`` stays an explicitly inactive
contract; D9 must not depend on telemetry.
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import pickle
import re
import resource
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from v2.config import V2Paths
from v2.errors import IngestionError

# Bounded D8 representative sample (all cached; no downloads). One race per
# plan-specified bucket.
D8_SAMPLE = [
    (2018, "2018-r11-R", "2018 Germany (sparse era)"),
    (2019, "2019-r11-R", "2019 Germany (wet/chaotic)"),
    (2021, "2021-r10-R", "2021 Britain (sprint weekend)"),
    (2021, "2021-r12-R", "2021 Belgium (shortened/red-flag)"),
    (2022, "2022-r07-R", "2022 Monaco (wet, slow)"),
    (2023, "2023-r01-R", "2023 Bahrain (normal)"),
    (2024, "2024-r01-R", "2024 Bahrain"),
    (2025, "2025-r06-R", "2025 Miami (wet/mixed)"),
]

# Raw car-telemetry channels seen in the cache (measured across the sample).
# Values are the raw livetiming scalars; units as documented by FastF1 3.7.0.
CAR_TELEMETRY_CHANNELS = {
    "Time": ("timedelta", "session-relative (aligned to D6 state clock)"),
    "Date": ("datetime", "absolute UTC"),
    "RPM": ("int", "rpm"),
    "Speed": ("int", "km/h"),
    "nGear": ("int", "gear"),
    "Throttle": ("int", "% 0..~104 (raw)"),
    "Brake": ("bool", "0/1"),
    "DRS": ("int", "raw status code (0=off,1=on,10/12/14 other)"),
    "Source": ("str", "data source tag"),
}

# Position-data channels (measured).
POSITION_CHANNELS = {
    "Date": ("datetime", "absolute UTC"),
    "Status": ("int", "car status code"),
    "X": ("float", "metres (world offset)"),
    "Y": ("float", "metres (world offset)"),
    "Z": ("float", "metres (world offset)"),
    "Source": ("str", "data source tag"),
    "Time": ("timedelta", "session-relative"),
    "SessionTime": ("float", "session-relative seconds"),
}


def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def resolve_race_telemetry_dir(paths: V2Paths, cache_root: Path,
                               season: int, race_id: str) -> Path | None:
    """Map a canonical race_id to its cached telemetry session directory.

    Resolved from canonical race ``event_name`` against the cache event
    directory names (round never used; names are normalized ASCII). Returns
    None when no directory matches (e.g. un-decomposed accent encodings)."""
    event_files = glob.glob(str(paths.processed_dir / "races" /
                                f"season={season}" / "races__*.parquet"))
    want = None
    for f in event_files:
        df = pd.read_parquet(f)
        hit = df[df["race_id"] == race_id]
        if len(hit) == 1:
            want = _norm(hit.iloc[0]["event_name"])
            break
    if want is None:
        return None
    for race_dir in sorted(glob.glob(str(cache_root / f"{season}" / "*" /
                                         "*_Race"))):
        ev = os.path.basename(os.path.dirname(race_dir))
        _, _, ename = ev.partition("_")
        if _norm(ename) == want:
            return Path(race_dir)
    return None


def load_car_data_blob(race_dir: Path) -> dict[str, pd.DataFrame]:
    """Read the cached car_data blob: car number -> raw telemetry DataFrame."""
    path = race_dir / "car_data.ff1pkl"
    if not path.exists():
        raise IngestionError.storage(f"no car_data blob at {path}")
    with open(path, "rb") as handle:
        payload = pickle.load(handle)
    return payload["data"]


def load_position_data_blob(race_dir: Path) -> dict[str, pd.DataFrame] | None:
    path = race_dir / "position_data.ff1pkl"
    if not path.exists():
        return None
    with open(path, "rb") as handle:
        return pickle.load(handle)["data"]


# ---------------------------------------------------------------------------
# Pure, deterministic lap-window + summary helpers (offline-testable).
# ---------------------------------------------------------------------------

def sample_indices_in_window(times_s: np.ndarray, start_s: float,
                             end_s: float) -> np.ndarray:
    """Indices of samples with start_s <= t < end_s (half-open window).

    Session seconds are the D6 state clock (verified aligned with the cached
    car_data Time across the sample)."""
    lo = int(np.searchsorted(times_s, start_s - 1e-9, side="left"))
    hi = int(np.searchsorted(times_s, end_s - 1e-9, side="left"))
    return np.arange(lo, hi, dtype=np.intp)


def _frac(mask, n):
    if n == 0:
        return None
    return float(mask.sum()) / float(n)


def summarize_lap(frame: pd.DataFrame) -> dict:
    """Candidate lap-level summaries from one lap's telemetry window.

    Exact formulas (documented in docs/DATA_PLATFORM_ARCHITECTURE.md §D8):
    - sample_count: rows in the window
    - speed_max_kmh / speed_mean_kmh / speed_p95_kmh from Speed
    - rpm_mean / rpm_p95 from RPM
    - throttle_pressed_frac: fraction of samples with Throttle > 0
    - brake_frac: fraction of samples with Brake truthy
    - drs_active_frac: fraction of samples with DRS == 1 (raw code; 10/12/14
      and other raw codes are NOT counted as active — see ADR caveat)
    - gear_changes: count of consecutive-sample nGear transitions to a
      non-zero gear

    Temporal availability: LAP_END (the window is exactly the canonical lap
    [lap_start_s, state_time_s); no future-lap/future-race telemetry can
    enter). Missingness policy: a missing channel yields null for the metrics
    that depend on it; sparse windows still compute from whatever samples
    exist; nothing is imputed. Deterministic: independent of row order."""
    n = int(len(frame))
    if n == 0:
        keys = ("sample_count", "speed_max_kmh", "speed_mean_kmh",
                "speed_p95_kmh", "throttle_pressed_frac", "brake_frac",
                "drs_active_frac", "rpm_mean", "rpm_p95", "gear_changes")
        return {k: None for k in keys}

    # Time-ordered aggregation: gear transitions are defined over consecutive
    # samples in time, so rows are stably ordered by the Time channel when it
    # is present. This makes summaries invariant to source row order.
    if "Time" in frame.columns:
        raw = frame["Time"]
        if hasattr(raw.dtype, "type") and np.issubdtype(
                raw.dtype, np.timedelta64):
            time_s = raw.dt.total_seconds().to_numpy(dtype=float)
        else:
            time_s = pd.to_numeric(raw, errors="coerce").to_numpy(
                dtype=float)
        order = np.argsort(np.nan_to_num(time_s, nan=-np.inf),
                           kind="mergesort")
        frame = frame.iloc[order]

    def _num(col):
        if col not in frame.columns:
            return None
        return pd.to_numeric(frame[col], errors="coerce").to_numpy(dtype=float)

    speed = _num("Speed")
    rpm = _num("RPM")
    throttle = _num("Throttle")
    brake = _num("Brake")
    drs = _num("DRS")
    gear = _num("nGear")

    out = {"sample_count": n}

    def _stat(a, fn, default=None):
        if a is None or len(a) == 0:
            return default
        valid = a[~np.isnan(a)]
        if len(valid) == 0:
            return default
        try:
            return float(fn(valid))
        except (ValueError, TypeError):
            return default

    out["speed_max_kmh"] = _stat(speed, np.max)
    out["speed_mean_kmh"] = _stat(speed, np.mean)
    out["speed_p95_kmh"] = _stat(speed, lambda a: np.percentile(a, 95))
    out["rpm_mean"] = _stat(rpm, np.mean)
    out["rpm_p95"] = _stat(rpm, lambda a: np.percentile(a, 95))

    if throttle is not None:
        th = throttle[~np.isnan(throttle)]
        out["throttle_pressed_frac"] = _frac(th > 0, len(th))
    else:
        out["throttle_pressed_frac"] = None
    if brake is not None:
        br = brake[~np.isnan(brake)]
        out["brake_frac"] = _frac(br > 0, len(br))
    else:
        out["brake_frac"] = None
    if drs is not None:
        dv = drs[~np.isnan(drs)]
        out["drs_active_frac"] = _frac(dv == 1.0, len(dv))
    else:
        out["drs_active_frac"] = None
    if gear is not None:
        g = gear
        valid = ~np.isnan(g)
        if valid.sum() < 2:
            out["gear_changes"] = None
        else:
            gv = g[valid]
            transitions = int(((np.diff(gv) != 0) & (gv[1:] > 0)).sum())
            out["gear_changes"] = transitions
    else:
        out["gear_changes"] = None
    return out


# ---------------------------------------------------------------------------
# Whole-race measurement over the cached telemetry (read-only, offline).
# ---------------------------------------------------------------------------

def _read_d6_state(paths: V2Paths, season: int, race_id: str) -> pd.DataFrame:
    from v2 import d6 as d6mod

    st = d6mod.read_state_season(paths, int(season))
    return st[st["race_id"] == race_id].reset_index(drop=True)


def _car_to_driver(paths: V2Paths, season: int, race_id: str) -> dict:
    import glob as _glob

    res_files = _glob.glob(str(paths.processed_dir / "results" /
                               f"season={season}" /
                               f"results__{race_id}.parquet"))
    if not res_files:
        raise IngestionError.storage(f"no results file for {race_id}")
    res = pd.read_parquet(res_files[0])
    mapping = {}
    for _, r in res.iterrows():
        num = r.get("driver_number")
        if pd.notna(num) and r.get("driver_id"):
            mapping[str(int(num))] = r["driver_id"]
    return mapping


def _measure_one_race(paths: V2Paths, cache_root: Path, season: int,
                      race_id: str, label: str) -> dict:
    race_dir = resolve_race_telemetry_dir(paths, cache_root, int(season),
                                          race_id)
    if race_dir is None:
        raise IngestionError.storage(
            f"cannot resolve cached telemetry dir for {race_id}")
    car_path = race_dir / "car_data.ff1pkl"
    pos_path = race_dir / "position_data.ff1pkl"
    started = time.perf_counter()
    car_blob = load_car_data_blob(race_dir)
    load_s = time.perf_counter() - started
    st = _read_d6_state(paths, int(season), race_id)
    car_to_driver = _car_to_driver(paths, int(season), race_id)

    channel_sets = set()
    channel_null = {c: 0 for c in ("RPM", "Speed", "nGear", "Throttle",
                                   "Brake", "DRS")}
    total_samples = 0
    per_car = {}
    windows = []
    windowed_drs_counts: dict = {}
    agg_started = time.perf_counter()
    for car, frame in car_blob.items():
        driver_id = car_to_driver.get(car)
        channel_sets.add(tuple(str(c) for c in frame.columns))
        n_car = len(frame)
        total_samples += n_car
        ts = frame["Time"].dt.total_seconds().to_numpy(dtype=float)
        for c in channel_null:
            if c in frame.columns:
                channel_null[c] += int(frame[c].isna().sum())
        if driver_id is None:
            per_car[car] = {"driver_id": None, "samples": n_car}
            continue
        laps = st[st["driver_id"] == driver_id]
        lap_hits = 0
        for _, r in laps.iterrows():
            if pd.isna(r.get("lap_start_s")) or pd.isna(r.get("state_time_s")):
                continue
            idx = sample_indices_in_window(ts, float(r["lap_start_s"]),
                                           float(r["state_time_s"]))
            if len(idx) == 0:
                continue
            win = frame.iloc[idx]
            summary = summarize_lap(win)
            if "DRS" in win.columns:
                for code, count in win["DRS"].value_counts(dropna=False).items():
                    windowed_drs_counts[int(code)] = (
                        windowed_drs_counts.get(int(code), 0) + int(count))
            windows.append({
                "race_id": race_id, "driver_id": driver_id,
                "lap_number": int(r["lap_number"]), "sample_count": len(idx),
                **summary,
            })
            lap_hits += 1
        per_car[car] = {"driver_id": driver_id, "samples": n_car,
                        "lap_windows": lap_hits}
    agg_s = time.perf_counter() - agg_started

    win_df = pd.DataFrame(windows)
    pos_report = None
    if pos_path.exists():
        pos_blob = load_position_data_blob(race_dir)
        pos_samples = sum(len(v) for v in pos_blob.values())
        pos_report = {
            "present": True,
            "cache_bytes": pos_path.stat().st_size,
            "sample_rows": int(pos_samples),
            "columns": sorted({str(c) for v in pos_blob.values()
                               for c in v.columns}),
        }
    else:
        pos_report = {"present": False, "cache_bytes": 0, "sample_rows": 0,
                      "columns": []}

    summary_cols = [c for c in (
        "sample_count", "speed_max_kmh", "speed_mean_kmh", "speed_p95_kmh",
        "throttle_pressed_frac", "brake_frac", "drs_active_frac", "rpm_mean",
        "rpm_p95", "gear_changes")]

    def _valid_rate(col):
        if col not in win_df.columns or len(win_df) == 0:
            return None
        return round(float(win_df[col].notna().mean()), 6)

    def _bounds(col):
        if col not in win_df.columns or len(win_df) == 0:
            return None
        vals = pd.to_numeric(win_df[col], errors="coerce").dropna()
        if len(vals) == 0:
            return None
        return {
            "min": round(float(vals.min()), 4),
            "median": round(float(vals.median()), 4),
            "p95": round(float(vals.quantile(0.95)), 4),
            "max": round(float(vals.max()), 4),
        }

    return {
        "race_id": race_id,
        "season": int(season),
        "label": label,
        "session_dir": str(race_dir.relative_to(cache_root.parent.parent)),
        "car_data_cache_bytes": car_path.stat().st_size,
        "load_seconds": round(load_s, 4),
        "aggregate_seconds": round(agg_s, 4),
        "total_seconds": round(time.perf_counter() - started, 4),
        "cars": len(car_blob),
        "cars_with_mapped_driver": sum(1 for v in per_car.values()
                                       if v["driver_id"]),
        "drivers_in_state": int(st["driver_id"].nunique()),
        "state_driver_laps": int(len(st)),
        "covered_driver_lap_windows": int(len(win_df)),
        "zero_sample_windows": int(len(st) - len(win_df)),
        "samples_per_lap": {
            "min": int(win_df["sample_count"].min()) if len(win_df) else None,
            "median": int(win_df["sample_count"].median())
            if len(win_df) else None,
            "max": int(win_df["sample_count"].max()) if len(win_df) else None,
        },
        "samples_total": total_samples,
        "samples_per_driver": round(total_samples / max(len(car_blob), 1), 1),
        "channel_sets": sorted([list(c) for c in channel_sets],
                               key=repr),
        "channel_null_counts": channel_null,
        "windowed_drs_value_counts": {
            int(k): int(v) for k, v in sorted(windowed_drs_counts.items())
        },
        "position": pos_report,
        "candidate_summary_valid_rate": {c: _valid_rate(c)
                                         for c in summary_cols},
        "candidate_summary_bounds": {c: _bounds(c) for c in summary_cols},
    }


def run_sample_measurement(paths: V2Paths, cache_root: Path) -> dict:
    """Measure the bounded D8 sample. Returns a measured record."""
    started = time.perf_counter()
    races = []
    for season, race_id, label in D8_SAMPLE:
        races.append(_measure_one_race(paths, cache_root, season, race_id,
                                       label))
    elapsed = time.perf_counter() - started
    rss = resource.getrusage(resource.RUSAGE_SELF).ru_maxrss

    def _sum(key):
        vals = [r.get(key) for r in races]
        return sum(v for v in vals if v is not None)

    covered = sum(r["covered_driver_lap_windows"] for r in races)
    state_laps = sum(r["state_driver_laps"] for r in races)
    zero = sum(r["zero_sample_windows"] for r in races)

    # Measured per-sample bytes: (car_data cache bytes) / total samples per
    # race, averaged across the sample.
    per_sample_bytes = [
        r["car_data_cache_bytes"] / r["samples_total"] for r in races
        if r["samples_total"] > 0
    ]

    # Whole-scope cache file inventory (cheap, file sizes only).
    whole_scope = _cache_inventory(cache_root)

    return {
        "scope": "D8 bounded representative sample (8 races, cached)",
        "races": races,
        "sample_state_driver_laps": state_laps,
        "sample_covered_lap_windows": covered,
        "sample_zero_sample_windows": zero,
        "sample_total_samples": _sum("samples_total"),
        "sample_car_data_cache_bytes": _sum("car_data_cache_bytes"),
        "measured_seconds_per_race_load": round(
            float(np.mean([r["load_seconds"] for r in races])), 4),
        "measured_seconds_per_race_aggregate": round(
            float(np.mean([r["aggregate_seconds"] for r in races])), 4),
        "measured_seconds_per_race_total": round(
            float(np.mean([r["total_seconds"] for r in races])), 4),
        "measured_bytes_per_sample_mean": round(
            float(np.mean(per_sample_bytes)), 4),
        "measured_peak_rss_bytes": int(rss),
        "total_sample_seconds": round(elapsed, 4),
        "whole_scope_cache_inventory": whole_scope,
        "decision": (
            "telemetry deferred from canonical Phase-1 dataset (see "
            "docs/adr/ADR-0001-telemetry-retention.md); no canonical "
            "telemetry artifacts created; FastF1 cache retained as source"),
        "d9_dependency": "D9 must NOT depend on telemetry.",
    }


def _cache_inventory(cache_root: Path) -> dict:
    """File-size inventory of the whole cache + telemetry/position blobs.

    File existence/size only (no unpickling), so the whole scope is cheap."""
    total_bytes = 0
    tel_bytes = 0
    pos_bytes = 0
    tel_files = 0
    pos_files = 0
    http_bytes = 0
    for p in sorted(cache_root.rglob("*")):
        if not p.is_file():
            continue
        sz = p.stat().st_size
        total_bytes += sz
        if p.name == "fastf1_http_cache.sqlite":
            http_bytes += sz
        elif p.name == "car_data.ff1pkl":
            tel_bytes += sz
            tel_files += 1
        elif p.name == "position_data.ff1pkl":
            pos_bytes += sz
            pos_files += 1
    return {
        "cache_total_bytes": int(total_bytes),
        "http_sqlite_bytes": int(http_bytes),
        "car_data_files": tel_files,
        "car_data_bytes": int(tel_bytes),
        "position_data_files": pos_files,
        "position_data_bytes": int(pos_bytes),
    }


def write_json(dest: Path, data: dict) -> None:
    dest = Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m v2.d8",
        description="D8 telemetry decision evidence (bounded sample)")
    parser.add_argument("--root", default=None)
    parser.add_argument("--cache", default=None,
                        help="FastF1 cache root (default: data/raw/"
                             "fastf1_cache under project root)")
    parser.add_argument("--report", default=None,
                        help="write the measured JSON report to a path "
                             "(default: data/v2/reports/data_quality/"
                             "d8_telemetry_sample.json)")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _build_parser().parse_args(argv)
    try:
        paths = V2Paths.resolve(args.root)
        cache_root = Path(args.cache) if args.cache else paths.cache_dir
        report = run_sample_measurement(paths, Path(cache_root))
        dest = (Path(args.report) if args.report
                else paths.reports_dir / "d8_telemetry_sample.json")
        write_json(dest, report)
        print(f"sample races        : {len(report['races'])}")
        print(f"state driver-laps   : {report['sample_state_driver_laps']}")
        print(f"covered lap windows : {report['sample_covered_lap_windows']}")
        print(f"zero-sample windows : {report['sample_zero_sample_windows']}")
        print(f"total samples       : {report['sample_total_samples']}")
        print(f"car-data cache MB   : "
              f"{round(report['sample_car_data_cache_bytes']/1e6, 1)}")
        print(f"peak RSS bytes      : {report['measured_peak_rss_bytes']}")
        print(f"report              : {paths.relative(dest)}")
        return 0
    except IngestionError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
