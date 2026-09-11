"""F14 red-team helpers (verification scope only).

Threat model (A-T), leakage matrix (family x mutation), machine-readable
dependency manifests, and the full temporal mutation campaign machinery.
No production semantics live here; production code is only exercised.
"""

from __future__ import annotations

import glob

import pandas as pd

from v2.config import V2Paths
from v2.features import (
    FeatureRequest,
    PriorHistory,
    build_f11_registry,
    features_for_batch,
    features_for_state,
    results_equal,
)
from v2.labels import build_label_registry

ROOT = V2Paths.resolve().root

# ---------------------------------------------------------------------------
# 1. Threat model (F14 §1, classes A-T)
# ---------------------------------------------------------------------------

THREAT_MODEL: dict[str, dict] = {
    "A": {"title": "same-driver future-state leakage",
          "attack": "mutate/delete/insert own-driver rows with time > T"},
    "B": {"title": "cross-driver future-state leakage",
          "attack": "mutate rival rows with time > T (values only)"},
    "C": {"title": "same-lap rival leakage",
          "attack": "extreme values in rival same-lap row crossing after T; "
                    "synthetic insert at T+0.001"},
    "D": {"title": "future weather leakage",
          "attack": "mutate/insert wx obs with time in (T, T+300]"},
    "E": {"title": "future race-control leakage",
          "attack": "future track_state tokens incl. red/SC/VSC"},
    "F": {"title": "current-race result leakage",
          "attack": "rewrite R outcomes (finish/points/status)"},
    "G": {"title": "future-race historical-prior leakage",
          "attack": "rewrite H>R outcomes; off-by-one N/N+1 + season edge"},
    "H": {"title": "target-label leakage",
          "attack": "absurd race-driver label values; recompute all 84"},
    "I": {"title": "presentation identity leakage",
          "attack": "global display/number/abbreviation rewrite"},
    "J": {"title": "row-order dependence",
          "attack": "multi-seed shuffles of states/weather/history/labels"},
    "K": {"title": "single/batch semantic drift",
          "attack": "complete-84 single vs batch; optimized vs reference"},
    "L": {"title": "missingness collapse",
          "attack": "null inputs must stay null (never silent zero)"},
    "M": {"title": "tri-state collapse",
          "attack": "True/False/None through validity/traffic/gates/labels"},
    "N": {"title": "race-boundary off-by-one",
          "attack": "N-1 allowed / R forbidden / N+1 forbidden; Y/Y+1 edge"},
    "O": {"title": "source-table contamination",
          "attack": "outcome columns into state paths; results outside H<R"},
    "P": {"title": "accidental final-state inference",
          "attack": "final position/winner/points/status inside calculators"},
    "Q": {"title": "state-dependent label mistakes",
          "attack": "ties, +/-1, nulls, unclassified numerics"},
    "R": {"title": "stateless-participant mistakes",
          "attack": "six zero-state entrants: kept, never fabricated"},
    "S": {"title": "cache/index eventual-state leakage",
          "attack": "fast vs reference paths under adversarial data"},
    "T": {"title": "equal-timestamp tie instability",
          "attack": "stroll 2021-r08 laps 4/5 + synthetic ties; shuffle"},
}

# Mutation ids: F_* / *_RES / LABELS / IDENT are forbidden (expect NO
# change); SELF / PAST_* / GRID_SELF are eligible (expect MAY change).
NEGATIVE_IDS = ("F_OWN", "F_RIVAL", "F_INSERT", "F_DELETE", "F_WX", "F_RC",
                "CUR_RES", "FUT_RES", "LABELS", "IDENT")
POSITIVE_IDS = ("SELF", "PAST_OWN", "PAST_RIVAL", "PAST_WX", "PAST_PRIOR",
                "GRID_SELF")

# Family -> mutations that MAY legitimately change it (all others: NO).
MAY_CHANGE: dict[str, frozenset] = {
    "race_state": frozenset({"SELF"}),
    "tyre": frozenset({"SELF"}),
    "stint": frozenset({"SELF", "PAST_OWN"}),
    "pace": frozenset({"SELF", "PAST_OWN"}),
    "gap": frozenset({"SELF", "PAST_RIVAL"}),
    "relative": frozenset({"SELF", "PAST_OWN", "PAST_RIVAL"}),
    "teammate": frozenset({"SELF", "PAST_OWN", "PAST_RIVAL"}),
    "field": frozenset({"SELF", "PAST_RIVAL"}),
    "traffic": frozenset({"SELF", "PAST_RIVAL"}),
    "rate": frozenset({"SELF", "PAST_OWN", "PAST_RIVAL"}),
    "momentum": frozenset({"SELF", "PAST_OWN", "PAST_RIVAL"}),
    "weather": frozenset({"SELF", "PAST_WX"}),
    "race_control": frozenset({"SELF"}),
    "grid": frozenset({"SELF", "GRID_SELF"}),
    "driver_prior": frozenset({"PAST_PRIOR"}),
    "constructor_prior": frozenset({"PAST_PRIOR"}),
    "circuit": frozenset({"PAST_PRIOR"}),
    "interaction": frozenset({"SELF", "PAST_OWN", "PAST_RIVAL"}),
}


def leakage_matrix() -> dict:
    """Family x mutation -> 'NO' (must not change) or 'MAY' (may change)."""
    fams = sorted({d.family.value for d in build_f11_registry()
                   if d.predictive_eligible})
    return {fam: {m: ("MAY" if m in MAY_CHANGE.get(fam, frozenset()) else "NO")
                  for m in NEGATIVE_IDS + POSITIVE_IDS} for fam in fams}


def feature_dependency_manifest() -> list[dict]:
    """Machine-readable per-definition dependency record (84 entries)."""
    out = []
    for d in build_f11_registry():
        fam = d.family.value
        allowed = sorted(MAY_CHANGE.get(fam, frozenset()))
        forbidden = sorted(set(NEGATIVE_IDS) - set(allowed))
        out.append({
            "name": d.name, "family": fam, "version": d.version,
            "temporal_rule": d.temporal_rule.value, "sync": d.sync.value,
            "sources": list(d.sources), "status": d.status.value,
            "allowed_mutations": allowed, "forbidden_mutations": forbidden,
        })
    return out


def label_dependency_manifest() -> list[dict]:
    """Machine-readable per-target dependency record (7 entries)."""
    out = []
    for d in build_label_registry():
        out.append({
            "name": d.name, "version": d.version, "dtype": d.dtype,
            "grain": list(d.grain), "sources": list(d.sources),
            "derivation": d.derivation, "null_policy": d.null_policy,
            "task": d.task.value, "status": d.status.value,
            "race_driver_constant": d.status.value == "canonical",
            "forbidden_upstream": ["feature_calculator"],
        })
    return out


# ---------------------------------------------------------------------------
# Campaign data loading (cached per session)
# ---------------------------------------------------------------------------

_CACHE: dict = {}


def _read_many(pattern: str, columns=None) -> pd.DataFrame:
    return pd.concat(
        [pd.read_parquet(f, columns=columns) for f in sorted(glob.glob(
            str(ROOT / pattern)))], ignore_index=True)


def load_race_states(season: int) -> pd.DataFrame:
    key = f"d9-{season}"
    if key not in _CACHE:
        _CACHE[key] = _read_many(
            f"data/v2/processed/driver_lap_state_d9/season={season}/*.parquet")
    return _CACHE[key]


def load_history() -> PriorHistory:
    if "history" not in _CACHE:
        mk = lambda pat: _read_many(f"data/v2/processed/{pat}/season=*/*.parquet")
        _CACHE["history"] = PriorHistory(
            mk("hist_results"), mk("hist_races"), mk("results"),
            mk("races"), mk("pit_stops"))
    return _CACHE["history"]


def load_labels() -> pd.DataFrame:
    if "labels" not in _CACHE:
        _CACHE["labels"] = _read_many(
            "data/v2/processed/race_driver_labels/*/*.parquet")
    return _CACHE["labels"]


def load_races() -> pd.DataFrame:
    if "races" not in _CACHE:
        _CACHE["races"] = _read_many(
            "data/v2/processed/races/season=*/*.parquet")
    return _CACHE["races"]


# (season, race_id, driver_selector, lap_selector): representative set
# spanning normal/wet/SC/red/partial/sparse/chaotic conditions.
TARGETS: tuple = (
    (2023, "2023-r01-R", "alonso", 28),        # normal dry mid
    (2023, "2023-r01-R", "max_verstappen", 2),  # normal early
    (2023, "2023-r01-R", "sargeant", 55),       # lapped-car late
    (2022, "2022-r07-R", "norris", 30),         # Monaco wet slow mid
    (2021, "2021-r12-R", "hamilton", 2),        # Belgium partial
    (2022, "2022-r18-R", "alonso", 14),         # Japan post-red mid
    (2022, "2022-r18-R", "ocon", 2),            # Japan red-flag early
    (2019, "2019-r11-R", "hamilton", 30),       # wet chaotic mid
    (2018, "2018-r04-R", "alonso", 2),          # sparse-era missing timing
    (2025, "2025-r01-R", "norris", 35),         # SC bunching
)


def get_target(season: int, race_id: str, driver_id: str,
               lap_number: int) -> tuple:
    """(request, race_frame, target_row, T) for a representative target."""
    d9 = load_race_states(season)
    sub = d9[d9["race_id"] == race_id].reset_index(drop=True)
    hit = sub[(sub["driver_id"] == driver_id)
              & (sub["lap_number"] == lap_number)]
    if not len(hit):
        raise AssertionError(f"target missing: {(race_id, driver_id)}")
    t = hit.iloc[0]
    q = FeatureRequest(str(t["race_id"]), str(t["driver_id"]),
                       int(t["lap_number"]), float(t["state_time_s"]))
    return q, sub, t, float(t["state_time_s"])


def full84(q, sub, history) -> object:
    return features_for_state(q, build_f11_registry(), sub, history=history)


def values_of(result) -> dict:
    return result.value_dict()


def family_of(name: str) -> str:
    reg = build_f11_registry()
    return reg.get(name).family.value


def differs(a: dict, b: dict, names) -> list:
    """Names whose values differ (null-aware, tolerance for floats)."""
    out = []
    for n in names:
        x, y = a.get(n), b.get(n)
        if x is None or y is None:
            if not (x is None and y is None):
                out.append(n)
        elif isinstance(x, bool) or isinstance(y, bool):
            if bool(x) != bool(y):
                out.append(n)
        elif isinstance(x, float) or isinstance(y, float):
            if abs(float(x) - float(y)) > 1e-9:
                out.append(n)
        elif x != y:
            out.append(n)
    return out


# ---------------------------------------------------------------------------
# Mutations (all operate on copies; canonical data never touched)
# ---------------------------------------------------------------------------

def _future(sub: pd.DataFrame, driver_id: str, T: float,
            own_only: bool) -> pd.Series:
    m = sub["state_time_s"] > T
    if own_only:
        m = m & (sub["driver_id"] == driver_id)
    return m


_EXTREME = {
    "position": 1, "lap_time_s": 200.0, "compound": "HARD",
    "tyre_life": 0, "track_state": "red_flag",
    "wx_air_temp_c": 60.0, "wx_track_temp_c": 80.0,
}


def mutate_negative(sub: pd.DataFrame, t, T: float, kind: str,
                    history: PriorHistory):
    """Return (mutated_sub, mutated_history) for a forbidden mutation."""
    if kind == "F_OWN":
        mod = sub.copy()
        m = _future(sub, str(t["driver_id"]), T, True)
        for col, val in _EXTREME.items():
            if col in mod.columns:
                mod.loc[m, col] = val
        if "pit_in_s" in mod.columns:
            mod.loc[m, "pit_in_s"] = T + 1.0
        return mod, history
    if kind == "F_RIVAL":
        mod = sub.copy()
        m = (sub["state_time_s"] > T) & (sub["driver_id"] != t["driver_id"])
        for col, val in _EXTREME.items():
            if col in mod.columns:
                mod.loc[m, col] = val
        if "lap_time_s" in mod.columns:
            mod.loc[m, "lap_time_s"] = 300.0
        return mod, history
    if kind == "F_INSERT":
        rows = []
        for i, (drv, dt) in enumerate(
                [(str(t["driver_id"]), 0.001),
                 (str(t["driver_id"]), 100.0),
                 ("__rival__", 0.001)]):
            row = t.copy()
            if drv == "__rival__":
                others = sub[(sub["driver_id"] != t["driver_id"])]
                row = others.iloc[0].copy()
            row["state_time_s"] = T + dt + i * 0.0001
            row["lap_number"] = int(t["lap_number"]) + (1 if dt > 1 else 0)
            for col, val in _EXTREME.items():
                if col in sub.columns:
                    row[col] = val
            rows.append(row)
        mod = pd.concat([sub, pd.DataFrame(rows)], ignore_index=True)
        return mod, history
    if kind == "F_DELETE":
        keep = (sub["state_time_s"] <= T) | (
            (sub["driver_id"] == t["driver_id"])
            & (sub["lap_number"] == int(t["lap_number"]))
            & (sub["state_time_s"] == T))
        return sub[keep].reset_index(drop=True), history
    if kind == "F_WX":
        mod = sub.copy()
        m = sub["state_time_s"] > T
        for col in ("wx_air_temp_c", "wx_track_temp_c", "wx_humidity_pct",
                    "wx_pressure_hpa", "wx_wind_speed"):
            if col in mod.columns:
                mod.loc[m, col] = 99.0
        if "wx_rainfall" in mod.columns:
            mod.loc[m, "wx_rainfall"] = True
        if "wx_observed_at_s" in mod.columns:
            mod.loc[m, "wx_observed_at_s"] = T + 10.0
        return mod, history
    if kind == "F_RC":
        mod = sub.copy()
        m = sub["state_time_s"] > T
        if "track_state" in mod.columns:
            mod.loc[m, "track_state"] = "red_flag"
        return mod, history
    if kind == "CUR_RES":
        h = _clone_history(history)
        rid = str(t["race_id"])
        season, rnd = _season_round(rid)
        ta = h.results_tiera
        m = ta["race_id"] == rid
        for col, val in (("position_final", 20), ("points", 0.0),
                         ("classified_position", 20)):
            if col in ta.columns:
                ta.loc[m, col] = val
        if "status_text" in ta.columns:
            ta.loc[m, "status_text"] = "Retired"
        hb = h.hist_results
        hm = (hb["season"].astype(int) == season) \
            & (hb["round_no"].astype(int) == rnd)
        for col, val in (("position", 20), ("points", 0)):
            if col in hb.columns:
                hb.loc[hm, col] = val
        return sub, h
    if kind == "FUT_RES":
        h = _clone_history(history)
        season, rnd = _season_round(str(t["race_id"]))
        hb = h.hist_results
        m = (hb["season"].astype(int) > season) | (
            (hb["season"].astype(int) == season)
            & (hb["round_no"].astype(int) > rnd))
        for col, val in (("position", 1), ("points", 25)):
            if col in hb.columns:
                hb.loc[m, col] = val
        return sub, h
    if kind == "LABELS":
        return sub, history  # engine takes no labels; equality is the test
    if kind == "IDENT":
        mod = sub.copy()
        for col, val in (("driver_abbreviation", "ZZZ"),
                         ("driver_number", 99)):
            if col in mod.columns:
                mod[col] = val
        return mod, history
    raise AssertionError(f"unknown negative mutation {kind}")


def _clone_history(history: PriorHistory) -> PriorHistory:
    return PriorHistory(
        history.hist_results.copy(), history.hist_races.copy(),
        history.results_tiera.copy(), history.races_tiera.copy(),
        history.pit_stops.copy())


def _season_round(race_id: str) -> tuple[int, int]:
    races = load_races()
    hit = races[races["race_id"] == race_id].iloc[0]
    return int(hit["season"]), int(hit["round_no"])


def mutate_positive(sub: pd.DataFrame, t, T: float, kind: str,
                    history: PriorHistory):
    """Eligible-source mutations; relevant outputs SHOULD change."""
    if kind == "SELF":
        mod = sub.copy()
        mod.loc[(mod["driver_id"] == t["driver_id"])
                & (mod["lap_number"] == int(t["lap_number"])),
                "position"] = 20 if int(t["position"]) != 20 else 1
        return mod, history
    if kind == "PAST_OWN":
        mod = sub.copy()
        past = (mod["driver_id"] == t["driver_id"]) \
            & (mod["state_time_s"] <= T) \
            & (mod["lap_time_s"].notna())
        idx = mod[past].index
        if not len(idx):
            raise AssertionError("no eligible past own laps")
        mod.loc[idx, "lap_time_s"] = mod.loc[idx, "lap_time_s"] + 8.0
        return mod, history
    if kind == "PAST_RIVAL":
        # Eligible synchronized-rival control: move every observable
        # rival clock 30 s earlier (order preserved, still <= T), which
        # must enlarge the factual clock separation for gap/relative.
        mod = sub.copy()
        m = (mod["driver_id"] != t["driver_id"]) \
            & (mod["state_time_s"] <= T)
        if not m.any():
            raise AssertionError("no observable rivals")
        mod.loc[m, "state_time_s"] = mod.loc[m, "state_time_s"] - 30.0
        return mod, history
    if kind == "PAST_WX":
        # Eligible historical-weather control: change the CURRENT as-of
        # observation value only (all rows carrying that observation
        # timestamp), so current-minus-anchor deltas must move.
        mod = sub.copy()
        pref = mod[mod["state_time_s"] <= T]
        if "wx_observed_at_s" not in mod.columns or pref.empty:
            raise AssertionError("no weather observations")
        latest = pref["wx_observed_at_s"].max()
        if pd.isna(latest):
            raise AssertionError("no timestamped weather observation")
        m = mod["wx_observed_at_s"] == latest
        if "wx_air_temp_c" in mod.columns:
            mod.loc[m, "wx_air_temp_c"] = mod.loc[m, "wx_air_temp_c"] + 5.0
        if "wx_track_temp_c" in mod.columns:
            mod.loc[m, "wx_track_temp_c"] = mod.loc[m, "wx_track_temp_c"] + 5.0
        return mod, history
    if kind == "PAST_PRIOR":
        # Eligible-prior control: rewrite ALL H<R rows for the driver to
        # a winning classified result, guaranteeing mean-finish and
        # points-per-start movement regardless of the latest row's status.
        h = _clone_history(history)
        season, rnd = _season_round(str(t["race_id"]))
        hb = h.hist_results
        elig = (hb["driver_id"] == str(t["driver_id"])) & (
            (hb["season"].astype(int) < season)
            | ((hb["season"].astype(int) == season)
               & (hb["round_no"].astype(int) < rnd)))
        if not elig.any():
            raise AssertionError("no eligible prior races")
        for col, val in (("position", 1), ("points", 25.0)):
            if col in hb.columns:
                hb.loc[elig, col] = val
        if "position_text" in hb.columns:
            hb.loc[elig, "position_text"] = "1"
        return sub, h
    if kind == "GRID_SELF":
        h = _clone_history(history)
        ta = h.results_tiera
        m = (ta["race_id"] == str(t["race_id"])) \
            & (ta["driver_id"] == str(t["driver_id"]))
        if "grid_position" in ta.columns:
            cur = ta.loc[m, "grid_position"]
            ta.loc[m, "grid_position"] = 20 if int(cur.iloc[0]) != 20 else 1
        return sub, h
    raise AssertionError(f"unknown positive mutation {kind}")
