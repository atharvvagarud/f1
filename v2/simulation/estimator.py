"""Phase-6 R3 offline empirical estimator.

Builds a deterministic :class:`~v2.simulation.params.SimulationParameterSet`
from canonical Phase-1 Parquet, using ONLY the explicit estimation window
(seasons 2018..``through_season``; 2025 is never read). Estimation is
chronological by construction and never consumes labels, results, the
feature engine, the winner model, or any replay artifact.

Scientific policy actually applied here (decisions recorded in
``docs/PHASE6_MONTE_CARLO_PLAN.md`` R3):
- eligible pace lap = R3-B rule (accurate, not deleted, no pit marker,
  ``all_clear``, lap>1, compound+age present) restricted to DRY compounds
  and non-rainfall laps for dry pace (wet regime excluded);
- race-progress trend: adopted per era (circuit where support allows);
- compound offset: DEFERRED (observational confounding; not identifiable
  with stable sign/magnitude across designs) -> zero fallback;
- tyre degradation: broad pooled per era only (conditional on the progress
  trend), never per compound/circuit;
- lap residual: empirical quantile distribution (heavy tails), independence
  documented, not silently assumed.

The module imports pandas/numpy; the runtime loader (``params.py``) does
not. This is the loader/estimator isolation the R3 mandate requires.
"""

from __future__ import annotations

import hashlib
from collections import defaultdict

import numpy as np
import pandas as pd

from v2.simulation.params import (
    DRY_COMPOUNDS,
    ELIGIBILITY_RULE_VERSION,
    ESTIMATOR_VERSION,
    FAMILY_NAMES,
    KNOWN_COMPOUNDS,
    PARAMETER_CONTRACT_VERSION,
    PARAMETER_SET_ID,
    ParameterFamily,
    SimulationParameterSet,
    SupportEntry,
    WET_COMPOUNDS,
)

# ---------------------------------------------------------------------------
# Frozen estimation design constants (evidence-backed; see R3 record).
# ---------------------------------------------------------------------------

SEASON_MIN = 2018
SEASON_MAX = 2024
ERAS = ((2018, 2021, "2018-2021"), (2022, 2024, "2022-2024"))

#: Minimum samples for a per-circuit slope / per-circuit distribution.
SLOPE_MIN_N = 2000
#: Minimum samples for a distribution group at the preferred hierarchy level.
DIST_GROUP_MIN_N = 30
#: Minimum samples for a stint-length group at circuit granularity.
STINT_GROUP_MIN_N = 25
#: Minimum samples for a constructor season offset.
CONSTRUCTOR_MIN_N = 200
#: Minimum samples for a per-circuit pit distribution.
PIT_CIRCUIT_MIN_N = 25
#: Plausible pit-lane transit window; outside this is red-flag/penalty noise.
TRANSIT_MIN_S = 8.0
TRANSIT_MAX_S = 120.0
#: Plausible effective pit-loss window (2-lap race-time cost).
PIT_LOSS_MIN_S = 5.0
PIT_LOSS_MAX_S = 120.0

RESIDUAL_PROBS = (0.001, 0.005, 0.01, 0.025, 0.05, 0.10, 0.25, 0.50,
                  0.75, 0.90, 0.95, 0.975, 0.99, 0.995, 0.999)
DIST_PROBS = (0.05, 0.10, 0.25, 0.50, 0.75, 0.90, 0.95)

SUPPORT_THRESHOLDS = {
    "slope_min_n": SLOPE_MIN_N,
    "distribution_group_min_n": DIST_GROUP_MIN_N,
    "stint_group_min_n": STINT_GROUP_MIN_N,
    "constructor_min_n": CONSTRUCTOR_MIN_N,
    "pit_circuit_min_n": PIT_CIRCUIT_MIN_N,
}

GROUPING_HIERARCHY = {
    "pace_base_s": ("circuit|era", "circuit", "global"),
    "pace_base_fallback_s": ("circuit", "global"),
    "constructor_pace_offset_s": ("constructor|season", "constructor|era",
                                  "global"),
    "race_progress_slope_s_per_lap": ("circuit|era", "era", "global"),
    "degradation_slope_s_per_lap": ("era", "global"),
    "compound_offset_s": ("deferred",),
    "lap_residual_distribution_s": ("era", "global"),
    "pit_effective_loss_s": ("circuit", "global"),
    "pit_lane_transit_s": ("circuit", "global"),
    "pit_in_lap_penalty_s": ("global",),
    "pit_out_lap_penalty_s": ("global",),
    "stint_length_laps": ("era|circuit|compound", "era|compound", "compound",
                          "global"),
    "compound_transition_probability": ("compound", "GLOBAL"),
}

D9_COLUMNS = (
    "race_id", "season", "circuit_id", "driver_id", "constructor_id",
    "lap_number", "lap_time_s", "compound", "tyre_life", "stint_number",
    "pit_in_s", "pit_out_s", "track_state", "is_accurate", "deleted",
    "race_leader_laps_at_state", "wx_rainfall",
)


def _era_of(season: int) -> str:
    for lo, hi, name in ERAS:
        if lo <= int(season) <= hi:
            return name
    raise ValueError(f"season {season} outside supported eras")


def _support_level(n: int, strong_n: int) -> str:
    if n <= 0:
        return "unavailable"
    return "strong" if n >= strong_n else "weak"


def _ols(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta


def _distribution_entry(values, *, group_key, probabilities,
                        fallback_level, strong_n,
                        identifiability="identified") -> SupportEntry:
    arr = np.asarray(values, dtype=float)
    arr = arr[np.isfinite(arr)]
    n = int(len(arr))
    if n == 0:
        return SupportEntry(
            group_key=group_key, sample_count=0,
            support_level="unavailable", fallback_level=fallback_level,
            value=None, identifiability="deferred")
    med = float(np.median(arr))
    mad = float(np.median(np.abs(arr - med)) * 1.4826)
    quants = tuple(float(np.quantile(arr, q)) for q in probabilities)
    return SupportEntry(
        group_key=group_key, sample_count=n,
        support_level=_support_level(n, strong_n),
        fallback_level=fallback_level,
        probabilities=tuple(probabilities),
        quantile_values=quants,
        observed_min=float(arr.min()),
        observed_max=float(arr.max()),
        std=float(np.std(arr)),
        mad=mad,
        identifiability=identifiability,
    )


def _scalar_entry(value, *, group_key, sample_count, fallback_level,
                  strong_n, identifiability="identified") -> SupportEntry:
    return SupportEntry(
        group_key=group_key, sample_count=int(sample_count),
        support_level=_support_level(int(sample_count), strong_n),
        fallback_level=fallback_level, value=float(value),
        identifiability=identifiability,
    )


def _deferred_entry(group_key: str, sample_count: int) -> SupportEntry:
    return SupportEntry(
        group_key=group_key, sample_count=int(sample_count),
        support_level=_support_level(int(sample_count), 1),
        fallback_level="deferred", value=None,
        identifiability="deferred",
    )


# ---------------------------------------------------------------------------
# Canonical loading (read-only, window-bounded).
# ---------------------------------------------------------------------------

def _read_entity(processed_dir, entity: str, seasons) -> pd.DataFrame:
    frames = []
    for s in seasons:
        directory = processed_dir / entity / f"season={s}"
        if not directory.is_dir():
            continue
        for path in sorted(directory.glob("*.parquet")):
            frames.append(pd.read_parquet(path))
    if not frames:
        return pd.DataFrame()
    return pd.concat(frames, ignore_index=True)


def _read_d9(processed_dir, seasons) -> pd.DataFrame:
    frames = []
    for s in seasons:
        path = (processed_dir / "driver_lap_state_d9" / f"season={s}"
                / f"driver_lap_state_d9__d9-{s}.parquet")
        if not path.exists():
            continue
        frames.append(pd.read_parquet(path, columns=list(D9_COLUMNS)))
    if not frames:
        return pd.DataFrame(columns=list(D9_COLUMNS))
    return pd.concat(frames, ignore_index=True)


def _fingerprint(frame: pd.DataFrame, columns) -> str:
    """Deterministic content fingerprint over the rows actually loaded."""
    if not len(frame):
        return hashlib.sha256(b"").hexdigest()
    ordered = frame.sort_values(list(columns), kind="mergesort")
    sub = ordered[list(columns)].copy()
    for c in columns:
        if pd.api.types.is_float_dtype(sub[c]):
            sub[c] = sub[c].map(
                lambda v: "" if pd.isna(v) else f"{float(v):.6f}")
        else:
            sub[c] = sub[c].astype(str)
    payload = "\n".join(sub[list(columns)].agg("|".join, axis=1).tolist())
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# Eligibility.
# ---------------------------------------------------------------------------

def eligibility_funnel(d9: pd.DataFrame) -> dict:
    """Audit-grade exclusion counts (diagnostics only)."""
    lt = d9["lap_time_s"]
    present = lt.notna()
    positive = present & (lt > 0)
    no_pit = positive & d9["pit_in_s"].isna() & d9["pit_out_s"].isna()
    green = no_pit & (d9["track_state"] == "all_clear")
    lap = green & (d9["lap_number"] > 1)
    accurate = lap & d9["is_accurate"].fillna(False).astype(bool)
    deleted = accurate & (~d9["deleted"].fillna(True).astype(bool))
    dry = deleted & d9["compound"].isin(DRY_COMPOUNDS)
    has_age = dry & d9["compound"].notna() & d9["tyre_life"].notna()
    no_rain = has_age & ~(d9["wx_rainfall"].fillna(False).astype(bool))
    return {
        "total_rows": int(len(d9)),
        "lap_time_present": int(present.sum()),
        "lap_time_positive": int(positive.sum()),
        "no_pit_marker": int(no_pit.sum()),
        "green_all_clear": int(green.sum()),
        "lap_number_gt_1": int(lap.sum()),
        "is_accurate": int(accurate.sum()),
        "not_deleted": int(deleted.sum()),
        "dry_compound": int(dry.sum()),
        "compound_and_age_present": int(has_age.sum()),
        "no_rainfall": int(no_rain.sum()),
        "excluded_pit_marker": int((present & ~no_pit).sum()),
        "excluded_not_green": int((no_pit & ~green).sum()),
        "excluded_lap_1": int((green & ~lap).sum()),
        "excluded_inaccurate": int((lap & ~accurate).sum()),
        "excluded_deleted": int((accurate & ~deleted).sum()),
        "excluded_wet_compound_or_missing": int((deleted & ~dry).sum()),
        "excluded_rainfall": int((has_age & ~no_rain).sum()),
    }


def eligible_laps(d9: pd.DataFrame) -> pd.DataFrame:
    lt = d9["lap_time_s"]
    mask = (lt.notna() & (lt > 0)
            & d9["pit_in_s"].isna() & d9["pit_out_s"].isna()
            & (d9["track_state"] == "all_clear")
            & (d9["lap_number"] > 1)
            & d9["is_accurate"].fillna(False).astype(bool)
            & (~d9["deleted"].fillna(True).astype(bool))
            & d9["compound"].isin(DRY_COMPOUNDS)
            & d9["compound"].notna() & d9["tyre_life"].notna()
            & ~(d9["wx_rainfall"].fillna(False).astype(bool)))
    out = d9[mask].copy()
    out["era"] = out["season"].map(_era_of)
    return out


def _demean(frame: pd.DataFrame, values: pd.Series) -> np.ndarray:
    keys = (frame["race_id"] + "|" + frame["driver_id"]).to_numpy()
    v = values.to_numpy(dtype=float)
    return v - pd.Series(v).groupby(keys).transform("mean").to_numpy()


def _pace_fit(frame: pd.DataFrame) -> tuple:
    """Within (race,driver) joint fit of relative pace on progress + age."""
    ref = frame.groupby(["race_id", "driver_id"])["lap_time_s"].transform(
        "median")
    y = (frame["lap_time_s"] - ref)
    y = _demean(frame, y)
    prog = _demean(frame, frame["lap_number"])
    age = _demean(frame, frame["tyre_life"])
    X = np.column_stack([np.ones(len(frame)), prog, age])
    beta = _ols(y, X)
    resid = y - X @ beta
    return {"progress": float(beta[1]), "degradation": float(beta[2]),
            "residual": resid}


def _lag1_autocorr(frame: pd.DataFrame, resid: np.ndarray) -> float:
    data = frame[["race_id", "driver_id", "lap_number"]].copy()
    data["resid"] = resid
    data = data.sort_values(["race_id", "driver_id", "lap_number"])
    data["prev"] = data.groupby(["race_id", "driver_id"])["resid"].shift(1)
    pair = data[["resid", "prev"]].dropna()
    if len(pair) < 2:
        return 0.0
    return float(pair["resid"].corr(pair["prev"]))


# ---------------------------------------------------------------------------
# Family builders.
# ---------------------------------------------------------------------------

def _build_pace_base(el: pd.DataFrame) -> tuple:
    base_entries = {}
    fallback_entries = {}
    for (circuit, era), group in el.groupby(["circuit_id", "era"]):
        key = f"{circuit}|{era}"
        base_entries[key] = _scalar_entry(
            group["lap_time_s"].median(), group_key=key,
            sample_count=len(group), fallback_level="exact",
            strong_n=CONSTRUCTOR_MIN_N)
    for circuit, group in el.groupby("circuit_id"):
        fallback_entries[circuit] = _scalar_entry(
            group["lap_time_s"].median(), group_key=circuit,
            sample_count=len(group), fallback_level="circuit",
            strong_n=CONSTRUCTOR_MIN_N)
    fallback_entries["global"] = _scalar_entry(
        el["lap_time_s"].median(), group_key="global",
        sample_count=len(el), fallback_level="global",
        strong_n=len(el) + 1)  # always weak: not a circuit-comparable value
    return base_entries, fallback_entries


def _build_constructor_offsets(el: pd.DataFrame) -> dict:
    entries = {}
    race_med = el.groupby("race_id")["lap_time_s"].transform("median")
    rel = el["lap_time_s"] - race_med
    work = el.assign(_rel=rel)
    for (constructor, season), group in work.groupby(
            ["constructor_id", "season"]):
        key = f"{constructor}|{int(season)}"
        if len(group) < CONSTRUCTOR_MIN_N:
            continue
        entries[key] = _scalar_entry(
            group["_rel"].median(), group_key=key,
            sample_count=len(group), fallback_level="exact",
            strong_n=CONSTRUCTOR_MIN_N)
    for (constructor, era), group in work.groupby(
            ["constructor_id", "era"]):
        key = f"{constructor}|{era}"
        entries[key] = _scalar_entry(
            group["_rel"].median(), group_key=key,
            sample_count=len(group), fallback_level="era",
            strong_n=CONSTRUCTOR_MIN_N)
    entries["global"] = _scalar_entry(
        0.0, group_key="global", sample_count=len(work),
        fallback_level="global", strong_n=1)
    return entries


def _build_progress(el: pd.DataFrame) -> tuple:
    entries = {}
    degradation = {}
    resid_by_era = {}
    global_fit = _pace_fit(el)
    resid_by_era["global"] = global_fit["residual"]
    entries["global"] = _scalar_entry(
        global_fit["progress"], group_key="global",
        sample_count=len(el), fallback_level="global",
        strong_n=SLOPE_MIN_N)
    degradation["global"] = _scalar_entry(
        global_fit["degradation"], group_key="global",
        sample_count=len(el), fallback_level="global",
        strong_n=SLOPE_MIN_N, identifiability="weak")
    for era, era_frame in el.groupby("era"):
        era_fit = _pace_fit(era_frame)
        resid_by_era[era] = era_fit["residual"]
        entries[era] = _scalar_entry(
            era_fit["progress"], group_key=era,
            sample_count=len(era_frame), fallback_level="era",
            strong_n=SLOPE_MIN_N)
        degradation[era] = _scalar_entry(
            era_fit["degradation"], group_key=era,
            sample_count=len(era_frame), fallback_level="era",
            strong_n=SLOPE_MIN_N, identifiability="weak")
        for circuit, circuit_frame in era_frame.groupby("circuit_id"):
            if len(circuit_frame) < SLOPE_MIN_N:
                continue
            key = f"{circuit}|{era}"
            fit = _pace_fit(circuit_frame)
            entries[key] = _scalar_entry(
                fit["progress"], group_key=key,
                sample_count=len(circuit_frame), fallback_level="exact",
                strong_n=SLOPE_MIN_N)
    return entries, degradation, resid_by_era


def _build_residual(resid_by_era: dict) -> dict:
    entries = {}
    for key, resid in resid_by_era.items():
        centered = np.asarray(resid, dtype=float)
        centered = centered - np.median(centered)
        entries[key] = _distribution_entry(
            centered, group_key=key, probabilities=RESIDUAL_PROBS,
            fallback_level="exact" if key != "global" else "global",
            strong_n=SLOPE_MIN_N)
    return entries


def _build_pit(d9: pd.DataFrame, race_circuit: pd.Series) -> tuple:
    lt = d9["lap_time_s"]
    clean = (lt.notna() & (lt > 0) & d9["pit_in_s"].isna()
             & d9["pit_out_s"].isna() & (d9["track_state"] == "all_clear")
             & (d9["lap_number"] > 1)
             & d9["is_accurate"].fillna(False).astype(bool)
             & (~d9["deleted"].fillna(True).astype(bool)))
    ref = (d9[clean].groupby(["race_id", "driver_id"])["lap_time_s"]
           .median().rename("ref"))
    green = (lt.notna() & (lt > 0) & (d9["track_state"] == "all_clear"))
    in_laps = d9[green & d9["pit_in_s"].notna()][
        ["race_id", "driver_id", "lap_number", "lap_time_s"]].merge(
        ref, on=["race_id", "driver_id"])
    in_laps["in_pen"] = in_laps["lap_time_s"] - in_laps["ref"]
    out_laps = d9[green & d9["pit_out_s"].notna()][
        ["race_id", "driver_id", "lap_number", "lap_time_s"]].merge(
        ref, on=["race_id", "driver_id"])
    out_laps["out_lap"] = out_laps["lap_number"] - 1
    out_laps["out_pen"] = out_laps["lap_time_s"] - out_laps["ref"]
    matched = out_laps.merge(
        in_laps[["race_id", "driver_id", "lap_number", "in_pen"]],
        left_on=["race_id", "driver_id", "out_lap"],
        right_on=["race_id", "driver_id", "lap_number"],
        suffixes=("", "_in"))
    matched["effective"] = matched["out_pen"] + matched["in_pen"]
    effective = matched["effective"].dropna()
    effective = effective[effective.between(PIT_LOSS_MIN_S, PIT_LOSS_MAX_S)]
    in_pen = in_laps["in_pen"].dropna()
    in_pen = in_pen[in_pen.between(-30.0, 300.0)]
    out_pen = out_laps["out_pen"].dropna()
    out_pen = out_pen[out_pen.between(-30.0, 300.0)]

    races_idx = race_circuit
    matched = matched.assign(circuit_id=matched["race_id"].map(races_idx))

    effective_entries = {}
    for circuit, group in matched.groupby("circuit_id"):
        vals = group["effective"].dropna()
        vals = vals[vals.between(PIT_LOSS_MIN_S, PIT_LOSS_MAX_S)]
        if len(vals) < PIT_CIRCUIT_MIN_N:
            continue
        effective_entries[circuit] = _distribution_entry(
            vals, group_key=circuit, probabilities=DIST_PROBS,
            fallback_level="exact", strong_n=PIT_CIRCUIT_MIN_N)
    effective_entries["global"] = _distribution_entry(
        effective, group_key="global", probabilities=DIST_PROBS,
        fallback_level="global", strong_n=SLOPE_MIN_N)

    return {
        "effective_entries": effective_entries,
        "in_pen": in_pen, "out_pen": out_pen,
        "matched": matched, "in_laps": in_laps, "out_laps": out_laps,
    }


def _build_transit(pits: pd.DataFrame, race_circuit: pd.Series) -> dict:
    transit = (pits["pit_out_s"] - pits["pit_in_s"]).dropna()
    transit = transit[transit.between(TRANSIT_MIN_S, TRANSIT_MAX_S)]
    pit_work = pits.assign(
        transit=(pits["pit_out_s"] - pits["pit_in_s"]))
    pit_work["circuit_id"] = pit_work["race_id"].map(race_circuit)
    pit_work = pit_work[pit_work["transit"].between(
        TRANSIT_MIN_S, TRANSIT_MAX_S)]
    entries = {}
    for circuit, group in pit_work.groupby("circuit_id"):
        if len(group) < PIT_CIRCUIT_MIN_N:
            continue
        entries[circuit] = _distribution_entry(
            group["transit"], group_key=circuit, probabilities=DIST_PROBS,
            fallback_level="exact", strong_n=PIT_CIRCUIT_MIN_N)
    entries["global"] = _distribution_entry(
        transit, group_key="global", probabilities=DIST_PROBS,
        fallback_level="global", strong_n=SLOPE_MIN_N)
    return entries


def _build_stint_lengths(stints: pd.DataFrame, race_circuit: pd.Series) -> dict:
    work = stints.copy()
    work["season"] = work["race_id"].str.split("-").str[0].astype(int)
    work["era"] = work["season"].map(_era_of)
    work["length"] = work["end_lap"] - work["start_lap"] + 1
    work["circuit_id"] = work["race_id"].map(race_circuit)
    entries = {}
    for (era, circuit, compound), group in work.groupby(
            ["era", "circuit_id", "compound"], dropna=True):
        if len(group) < STINT_GROUP_MIN_N:
            continue
        key = f"{era}|{circuit}|{compound}"
        entries[key] = _distribution_entry(
            group["length"], group_key=key, probabilities=DIST_PROBS,
            fallback_level="exact", strong_n=STINT_GROUP_MIN_N)
    for (era, compound), group in work.groupby(["era", "compound"]):
        key = f"{era}|{compound}"
        entries[key] = _distribution_entry(
            group["length"], group_key=key, probabilities=DIST_PROBS,
            fallback_level="era", strong_n=STINT_GROUP_MIN_N)
    for compound, group in work.groupby("compound"):
        entries[compound] = _distribution_entry(
            group["length"], group_key=compound, probabilities=DIST_PROBS,
            fallback_level="compound", strong_n=STINT_GROUP_MIN_N)
    entries["global"] = _distribution_entry(
        work["length"], group_key="global", probabilities=DIST_PROBS,
        fallback_level="global", strong_n=STINT_GROUP_MIN_N)
    return entries


def _build_transitions(stints: pd.DataFrame) -> tuple:
    work = stints.sort_values(["race_id", "driver_id", "stint_number"]).copy()
    work["next_compound"] = work.groupby(
        ["race_id", "driver_id"])["compound"].shift(-1)
    trans = work[work["next_compound"].notna()]
    entries = {}
    counts = defaultdict(int)
    for (current, nxt), group in trans.groupby(["compound", "next_compound"]):
        counts[current] += len(group)
    for (current, nxt), group in trans.groupby(["compound", "next_compound"]):
        total = counts[current]
        key = f"{current}->{nxt}"
        entries[key] = SupportEntry(
            group_key=current, sample_count=total,
            support_level=_support_level(total, DIST_GROUP_MIN_N),
            fallback_level="exact" if total >= DIST_GROUP_MIN_N else "global",
            value=len(group) / total)
    global_counts = trans["next_compound"].value_counts()
    total_all = int(global_counts.sum())
    for nxt, n in global_counts.items():
        key = f"GLOBAL->{nxt}"
        entries[key] = SupportEntry(
            group_key="GLOBAL", sample_count=total_all,
            support_level=_support_level(total_all, DIST_GROUP_MIN_N),
            fallback_level="global", value=int(n) / total_all)
    return entries, counts, trans


# ---------------------------------------------------------------------------
# Top-level estimator.
# ---------------------------------------------------------------------------

def _source_data_fingerprint(d9, stints, pits, races) -> dict:
    return {
        "driver_lap_state_d9": {
            "rows": int(len(d9)),
            "fingerprint": _fingerprint(
                d9, ["race_id", "driver_id", "lap_number", "lap_time_s"]),
        },
        "stints": {
            "rows": int(len(stints)),
            "fingerprint": _fingerprint(
                stints, ["race_id", "driver_id", "stint_number", "start_lap",
                         "end_lap", "compound"]),
        },
        "pit_stops": {
            "rows": int(len(pits)),
            "fingerprint": _fingerprint(
                pits, ["race_id", "driver_id", "stop_sequence", "lap_number",
                       "pit_in_s", "pit_out_s"]),
        },
        "races": {
            "rows": int(len(races)),
            "fingerprint": _fingerprint(races, ["race_id", "circuit_id"]),
        },
    }


def estimate_simulation_parameters(paths, *, through_season: int,
                                  creation_metadata=None
                                  ) -> SimulationParameterSet:
    """Build a parameter set from canonical data in the explicit window.

    ``paths`` is a :class:`v2.config.V2Paths` (an explicit project root).
    Only seasons ``2018..through_season`` are read; ``through_season`` is
    required and must be within 2018-2024. No 2025 row is ever touched.
    """
    through = int(through_season)
    if through < SEASON_MIN or through > SEASON_MAX:
        raise ValueError(
            f"through_season must be in [{SEASON_MIN}, {SEASON_MAX}], "
            f"got {through}")
    seasons = tuple(range(SEASON_MIN, through + 1))
    processed = paths.processed_dir

    d9_all = _read_d9(processed, seasons)
    stints = _read_entity(processed, "stints", seasons)
    pits = _read_entity(processed, "pit_stops", seasons)
    races = _read_entity(processed, "races", seasons)
    # Filter defensively: entity files are per-race and could contain a
    # season outside the window if the directory layout were mixed.
    for frame in (d9_all, stints, pits, races):
        if "season" in frame.columns:
            frame.drop(
                frame.index[~frame["season"].isin(seasons)], inplace=True)

    el = eligible_laps(d9_all)
    funnel = eligibility_funnel(d9_all)

    race_circuit = (d9_all.drop_duplicates("race_id")
                    .set_index("race_id")["circuit_id"])

    pace_base, pace_fallback = _build_pace_base(el)
    constructor_offsets = _build_constructor_offsets(el)
    progress, degradation, resid_by_era = _build_progress(el)
    residual = _build_residual(resid_by_era)
    pit = _build_pit(d9_all, race_circuit)
    transit = _build_transit(pits, race_circuit)
    stint_lengths = _build_stint_lengths(stints, race_circuit)
    transitions, transition_counts, trans_frame = _build_transitions(stints)

    compound_offsets = {
        compound: _deferred_entry(
            compound, int((el["compound"] == compound).sum()))
        for compound in KNOWN_COMPOUNDS
    }
    compound_observed = {}
    race_med = el.groupby("race_id")["lap_time_s"].transform("median")
    rel = (el["lap_time_s"] - race_med)
    work = el.assign(_rel=rel)
    med_rel = work.groupby("compound")["_rel"].median()
    base = float(med_rel.median())
    for compound in DRY_COMPOUNDS:
        if compound in med_rel.index:
            compound_observed[compound] = round(
                float(med_rel[compound] - base), 4)

    in_pen = pit["in_pen"]
    out_pen = pit["out_pen"]
    matched = pit["matched"]

    families = {
        "pace_base_s": ParameterFamily(
            "pace_base_s", "seconds",
            pace_base,
            "median eligible clean dry lap time by circuit x era"),
        "pace_base_fallback_s": ParameterFamily(
            "pace_base_fallback_s", "seconds", pace_fallback,
            "circuit pooled across eras, then a non-comparable global"),
        "constructor_pace_offset_s": ParameterFamily(
            "constructor_pace_offset_s", "seconds", constructor_offsets,
            "median relative pace (race-median-removed) by constructor"),
        "race_progress_slope_s_per_lap": ParameterFamily(
            "race_progress_slope_s_per_lap", "seconds_per_lap", progress,
            "within race x driver joint OLS; race-progress/fuel-like trend"),
        "degradation_slope_s_per_lap": ParameterFamily(
            "degradation_slope_s_per_lap", "seconds_per_lap", degradation,
            "broad pooled tyre-age slope, conditional on progress; weak"),
        "compound_offset_s": ParameterFamily(
            "compound_offset_s", "seconds", compound_offsets,
            "DEFERRED: observational confounding; zero fallback"),
        "lap_residual_distribution_s": ParameterFamily(
            "lap_residual_distribution_s", "seconds", residual,
            "empirical zero-median residual quantiles (heavy-tailed)"),
        "pit_effective_loss_s": ParameterFamily(
            "pit_effective_loss_s", "seconds",
            pit["effective_entries"],
            "green in-lap + out-lap excess over driver clean pace"),
        "pit_lane_transit_s": ParameterFamily(
            "pit_lane_transit_s", "seconds", transit,
            "pit_out_s - pit_in_s within [8,120] s"),
        "pit_in_lap_penalty_s": ParameterFamily(
            "pit_in_lap_penalty_s", "seconds",
            {"global": _distribution_entry(
                in_pen, group_key="global", probabilities=DIST_PROBS,
                fallback_level="global", strong_n=SLOPE_MIN_N)},
            "green in-lap excess over driver clean pace"),
        "pit_out_lap_penalty_s": ParameterFamily(
            "pit_out_lap_penalty_s", "seconds",
            {"global": _distribution_entry(
                out_pen, group_key="global", probabilities=DIST_PROBS,
                fallback_level="global", strong_n=SLOPE_MIN_N)},
            "green out-lap excess over driver clean pace"),
        "stint_length_laps": ParameterFamily(
            "stint_length_laps", "laps", stint_lengths,
            "histogram of observed stint lengths (behaviour, not optimum)"),
        "compound_transition_probability": ParameterFamily(
            "compound_transition_probability", "probability",
            transitions,
            "observed current -> next compound frequencies"),
    }
    assert set(families) == set(FAMILY_NAMES)

    lag1 = _lag1_autocorr(el, resid_by_era["global"])
    lag1_by_era = {"global": lag1}
    for era, era_frame in el.groupby("era"):
        lag1_by_era[era] = _lag1_autocorr(
            era_frame, resid_by_era[era])
    diagnostics = {
        "eligibility_funnel": funnel,
        "rows_total": int(len(d9_all)),
        "races_total": int(d9_all["race_id"].nunique()),
        "eligible_lap_count": int(len(el)),
        "eligible_by_season": {
            int(k): int(v) for k, v in el.groupby("season").size().items()},
        "eligible_by_era": {
            str(k): int(v) for k, v in el.groupby("era").size().items()},
        "eligible_by_compound": {
            str(k): int(v) for k, v in
            el.groupby("compound").size().items()},
        "eligible_by_circuit": {
            str(k): int(v) for k, v in
            el.groupby("circuit_id").size().items()},
        "wet_lap_count": int(
            d9_all["compound"].isin(WET_COMPOUNDS).sum()),
        "rain_race_count": int(
            d9_all[d9_all["wx_rainfall"].fillna(False).astype(bool)]
            ["race_id"].nunique()),
        "pace_residual_summary": {
            key: {
                "n": int(len(vals)),
                "std": round(float(np.std(vals)), 4),
                "mad": round(float(
                    np.median(np.abs(vals - np.median(vals))) * 1.4826), 4),
                "lag1_autocorr": round(lag1_by_era[key], 4),
            }
            for key, vals in resid_by_era.items()},
        "degradation_support": {
            key: int(entry.sample_count)
            for key, entry in degradation.items()},
        "progress_support": {
            key: int(entry.sample_count) for key, entry in progress.items()},
        "pit_sample_counts": {
            "in_lap": int(len(in_pen)),
            "out_lap": int(len(out_pen)),
            "effective_loss": int(len(matched["effective"].dropna())),
            "circuits_with_transit": int(len(transit) - 1),
        },
        "stint_sample_counts": {
            "stints": int(len(stints)),
            "groups": int(len(stint_lengths)),
        },
        "transition_counts": {
            str(k): int(v) for k, v in transition_counts.items()},
        "transition_rows": int(len(trans_frame)),
        "compound_effect_observed_weak": compound_observed,
        "compound_effect_policy": "deferred_confounded",
        "fallback_usage_potential": {
            "circuit_era_base_groups": int(len(pace_base)),
            "circuit_base_fallbacks": int(len(pace_fallback) - 1),
            "constructor_season_offsets": int(
                sum(1 for k in constructor_offsets if "|" in k
                    and not k.endswith(tuple(e[2] for e in ERAS)))),
            "progress_circuit_era_groups": int(
                sum(1 for k in progress if "|" in k)),
            "pit_circuit_distributions": int(len(pit["effective_entries"]) - 1),
            "stint_circuit_groups": int(
                sum(1 for k in stint_lengths if k.count("|") == 2)),
        },
        "residual_independence": {
            "assumption": "independent per-lap residual draws (v1)",
            "measured_within_driver_race_lag1_autocorr": round(lag1, 4),
            "limitation": "positive serial correlation from track evolution/"
                          "weather is not modelled; trial-level outcomes are "
                          "not independent across laps",
        },
    }

    policies = {
        "wet_dry": "dry pace uses DRY compounds only and excludes rainfall "
                   "laps; wet/intermediate lap pace is DEFERRED",
        "sc_vsc_red": "excluded from normal pace: eligible laps require "
                      "track_state == all_clear; red/SC/VSC laps may inform "
                      "a later event model, not R3",
        "compound": "observed compound-associated pace effect DEFERRED "
                    "(confounded, unstable sign across designs); zero "
                    "fallback; weak point estimates recorded in diagnostics",
        "degradation": "broad pooled per-era slope adopted, conditional on "
                       "the race-progress trend; not causal, not per-compound",
        "progress": "adopted per era / circuit-era; named race-progress pace "
                    "trend, NOT causally attributed to fuel",
        "residual": "empirical quantile distribution (heavy tails); "
                    "independence assumed and documented as a limitation",
        "pit_loss": "effective pit loss = green in-lap + out-lap excess over "
                    "driver clean pace; pit-lane transit reported separately",
        "stint_length": "observed historical behaviour, not optimal strategy",
    }

    regimes = {
        "dry_compounds": list(DRY_COMPOUNDS),
        "wet_compounds": list(WET_COMPOUNDS),
        "eras": [{"label": name, "season_start": lo, "season_end": hi}
                 for lo, hi, name in ERAS],
        "temporal_contract": "seasons 2018..through_season inclusive; "
                             "2025 never read",
        "maximum_season": SEASON_MAX,
    }

    return SimulationParameterSet(
        parameter_contract_version=PARAMETER_CONTRACT_VERSION,
        estimator_version=ESTIMATOR_VERSION,
        eligibility_rule_version=ELIGIBILITY_RULE_VERSION,
        parameter_set_id=PARAMETER_SET_ID,
        through_season=through,
        estimation_seasons=seasons,
        source_data=_source_data_fingerprint(d9_all, stints, pits, races),
        regimes=regimes,
        policies=policies,
        grouping_hierarchy=GROUPING_HIERARCHY,
        support_thresholds=SUPPORT_THRESHOLDS,
        families=families,
        diagnostics=diagnostics,
        creation_metadata=creation_metadata or {
            "generator": "scripts/build_simulation_parameters.py",
            "estimator_version": ESTIMATOR_VERSION,
        },
    )
