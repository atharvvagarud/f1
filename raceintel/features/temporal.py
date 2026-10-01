"""F3 primitive temporal operators (Phase 2 Temporal Feature Engine).

Executable F1 semantics (``docs/PHASE2_TEMPORAL_SEMANTICS.md``) as small,
deterministic, side-effect-free primitives over D9-style state frames.
Requires pandas (frame operators, like ``v2/d9.py``); pure selection and
ordering only — NO feature calculation, NO pace/gap/traffic/prior logic.

Global invariant: for target clock T, no operator exposes information
with event time after T.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

REQUIRED_STATE_COLUMNS = ("race_id", "driver_id", "lap_number",
                          "state_time_s")


class TemporalError(ValueError):
    """Invalid temporal input or contract violation."""


class TargetNotFoundError(TemporalError):
    """No exact target state exists for the requested identity."""


def require_columns(frame: pd.DataFrame, columns: Sequence[str],
                    what: str = "frame") -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise TemporalError(
            f"{what} is missing required columns: {missing}; "
            f"alternate names are never inferred")


def _sorted_by_time(frame: pd.DataFrame) -> pd.DataFrame:
    """Deterministic temporal order; never relies on input row order."""
    require_columns(frame, ("state_time_s", "lap_number", "driver_id"),
                    "temporal ordering")
    order = frame.sort_values(
        ["state_time_s", "lap_number", "driver_id"],
        kind="mergesort").index
    return frame.loc[order].copy()


def driver_prefix(states: pd.DataFrame, race_id: str, driver_id: str,
                  T: float) -> pd.DataFrame:
    """All states for driver in race with ``state_time_s <= T`` (inclusive).

    Deterministic temporal order; empty when nothing is observable; the
    source frame is never modified; all source columns preserved.
    """
    require_columns(states, REQUIRED_STATE_COLUMNS, "driver_prefix input")
    sub = states[(states["race_id"] == race_id)
                 & (states["driver_id"] == driver_id)
                 & (states["state_time_s"] <= T)]
    return _sorted_by_time(sub)


def latest_at_or_before(frame: pd.DataFrame, time_col: str, T: float,
                        tie_cols: Sequence[str] = ("lap_number",)
                        ) -> pd.Series | None:
    """Latest observation with ``frame[time_col] <= T``; None if none.

    No fall-forward: a future row arbitrarily close to T is rejected.
    Ties broken deterministically by ``tie_cols`` then ``driver_id``
    where present.
    """
    require_columns(frame, (time_col,), "latest_at_or_before input")
    sub = frame[frame[time_col] <= T]
    if not len(sub):
        return None
    keys = [time_col] + [c for c in tie_cols if c in sub.columns]
    if "driver_id" in sub.columns and "driver_id" not in keys:
        keys.append("driver_id")
    row = sub.sort_values(keys, kind="mergesort").iloc[-1]
    return row.copy()


def observation_age_s(T: float, observed_time_s: float) -> float:
    """Synchronization provenance: ``T - observed``. Must be >= 0.

    This is observation age, NEVER a race gap (F1 §11). No staleness
    cutoff is applied here; validity decisions belong to later stages.
    """
    age = float(T) - float(observed_time_s)
    if age < 0:
        raise TemporalError(
            f"observation after target clock: T={T}, observed={observed_time_s}")
    return age


@dataclass(frozen=True)
class SyncState:
    """Explicit synchronized-rival result (never an ambiguous scalar)."""

    observable: bool
    race_id: str
    driver_id: str
    observed_lap: int | None          # None when unobservable
    observed_time_s: float | None     # None when unobservable
    observation_age_s: float | None   # >= 0 when observable, else None
    values: Mapping | None = None     # copied row values (dict) or None


def synchronized_driver_state(states: pd.DataFrame, race_id: str,
                              rival_id: str, T: float) -> SyncState:
    """Latest state for rival in race with ``state_time_s <= T``.

    No fall-forward, no same-lap preference, no retirement inference:
    a stale state stays observable provenance; no prior state yields
    ``observable=False`` with null state.
    """
    require_columns(states, REQUIRED_STATE_COLUMNS,
                    "synchronized_driver_state input")
    sub = states[(states["race_id"] == race_id)
                 & (states["driver_id"] == rival_id)]
    row = latest_at_or_before(sub, "state_time_s", T)
    if row is None:
        return SyncState(False, race_id, rival_id, None, None, None, None)
    obs_time = float(row["state_time_s"])
    return SyncState(
        observable=True,
        race_id=race_id,
        driver_id=rival_id,
        observed_lap=int(row["lap_number"]),
        observed_time_s=obs_time,
        observation_age_s=observation_age_s(T, obs_time),
        values=dict(row),
    )


@dataclass(frozen=True)
class FieldSnapshot:
    """Target-time field snapshot: exact target + per-participant sync."""

    race_id: str
    driver_id: str
    lap_number: int
    state_time_s: float
    target_values: Mapping              # exact target row values (dict)
    entries: tuple = ()                 # ((driver_id, SyncState), ...) by id


def resolve_target(states: pd.DataFrame, race_id: str, driver_id: str,
                   lap_number: int, T: float) -> pd.Series:
    """Exact target row for (race, driver, lap, T); fail clearly otherwise.

    No nearest-timestamp substitution: a close timestamp is still an
    error when nothing matches exactly.
    """
    require_columns(states, REQUIRED_STATE_COLUMNS, "resolve_target input")
    sub = states[(states["race_id"] == race_id)
                 & (states["driver_id"] == driver_id)
                 & (states["lap_number"] == int(lap_number))
                 & (states["state_time_s"] == float(T))]
    if not len(sub):
        raise TargetNotFoundError(
            f"no exact target state for {(race_id, driver_id, lap_number, T)}")
    if len(sub) > 1:
        raise TemporalError(
            f"ambiguous target state (duplicate key) for "
            f"{(race_id, driver_id, lap_number, T)}")
    return sub.iloc[0].copy()


def synchronized_field_snapshot(states: pd.DataFrame, race_id: str,
                                driver_id: str, lap_number: int, T: float,
                                roster: Sequence[str]) -> FieldSnapshot:
    """Field snapshot at T over an explicit identity roster.

    The target contributes its exact state; every other roster member
    contributes ``synchronized_driver_state`` or an explicit
    unobservable entry (never silently dropped — including the six
    known zero-state participants). Entries ordered by ``driver_id``;
    never by final position.
    """
    target = resolve_target(states, race_id, driver_id, lap_number, T)
    members = sorted(set(roster) | {driver_id})
    entries = []
    for member in members:
        if member == driver_id:
            entries.append((member, SyncState(
                observable=True, race_id=race_id, driver_id=member,
                observed_lap=int(target["lap_number"]),
                observed_time_s=float(target["state_time_s"]),
                observation_age_s=0.0, values=dict(target))))
        else:
            entries.append((member, synchronized_driver_state(
                states, race_id, member, T)))
    return FieldSnapshot(race_id, driver_id, int(lap_number), float(T),
                         dict(target), tuple(entries))


#: Identity-only allow-list for roster extraction (F1 §6 decision).
ROSTER_IDENTITY_COLUMNS = ("race_id", "driver_id")


def extract_roster(results_like: pd.DataFrame) -> dict:
    """Identity-only roster: race_id -> sorted driver_ids.

    Accepts D5-results-shaped frames but returns ONLY allow-listed
    identity columns; outcome fields can never enter selection (outcome
    mutation cannot change the roster — tested).
    """
    require_columns(results_like, ROSTER_IDENTITY_COLUMNS, "roster input")
    roster: dict[str, list] = {}
    for race_id, group in results_like.groupby("race_id"):
        roster[str(race_id)] = sorted(
            {str(v) for v in group["driver_id"].dropna().to_numpy()})
    return roster


def within_stint_prefix(states: pd.DataFrame, race_id: str, driver_id: str,
                        T: float) -> pd.DataFrame:
    """Current-stint prefix: prefix rows sharing the target row's stint.

    Uses only start-side/current facts (per-row ``stint_number`` at
    ``<= T``). ``end_lap`` / future pit-out / eventual stint length are
    NEVER consulted (and need not exist). Null/absent stint identity on
    the target row yields an empty frame.
    """
    require_columns(states, REQUIRED_STATE_COLUMNS + ("stint_number",),
                    "within_stint_prefix input")
    if "end_lap" in states.columns:
        pass  # present-but-ignored by construction; never read below
    prefix = driver_prefix(states, race_id, driver_id, T)
    if not len(prefix):
        return prefix
    current = prefix.iloc[-1]["stint_number"]
    if current is None or (isinstance(current, float) and np.isnan(current)) \
            or (pd.isna(current)):
        return prefix.iloc[0:0].copy()
    return prefix[prefix["stint_number"] == current].copy()


def past_races_before(races: pd.DataFrame, season: int,
                      round_no: int) -> pd.DataFrame:
    """Races chronologically before (season, round_no).

    Canonical (season, round_no) ordering — never lexical race_id order.
    Current race, future rounds, and future seasons excluded. No outcome
    aggregation; selects eligible historical races only.
    """
    require_columns(races, ("race_id", "season", "round_no"),
                    "past_races_before input")
    sub = races[((races["season"] < int(season)))
                | ((races["season"] == int(season))
                   & (races["round_no"] < int(round_no)))]
    return sub.sort_values(["season", "round_no", "race_id"],
                           kind="mergesort").copy()


def rolling_past_observations(prefix: pd.DataFrame, T: float,
                              mask, window: int) -> pd.DataFrame:
    """Latest-``window`` eligible rows of an already-``<= T`` prefix.

    ``mask`` is a caller-supplied boolean array/Series aligned with
    ``prefix`` (eligibility policy lives with the caller/F5, never
    here). The target row is included when eligible (LAP_END boundary).
    No centered windows, no future rows (caller prefix guarantees
    ``<= T``; re-asserted here), nulls preserved, no min-n decision.
    """
    require_columns(prefix, ("state_time_s",), "rolling input")
    if int(window) < 1:
        raise TemporalError("rolling window must be >= 1")
    eligible = prefix[np.asarray(mask, dtype=bool)]
    eligible = eligible[eligible["state_time_s"] <= T]
    ordered = eligible.sort_values(["state_time_s", "lap_number"],
                                   kind="mergesort")
    return ordered.iloc[-int(window):].copy()


class RaceIndex:
    """Simple immutable per-race/per-driver sorted index over states.

    Built once from D9 states; repeated synchronization via binary
    search (``searchsorted``) instead of full-race scans. Read-only:
    inputs are copied on build and never mutated.
    """

    def __init__(self, states: pd.DataFrame) -> None:
        require_columns(states, REQUIRED_STATE_COLUMNS, "RaceIndex input")
        self._times: dict = {}
        self._laps: dict = {}
        self._rows: dict = {}
        for (race_id, driver_id), group in states.groupby(
                ["race_id", "driver_id"]):
            ordered = group.sort_values(["state_time_s", "lap_number"],
                                        kind="mergesort")
            key = (str(race_id), str(driver_id))
            self._times[key] = ordered["state_time_s"].to_numpy(dtype=float)
            self._laps[key] = ordered["lap_number"].to_numpy(dtype=np.int64)
            self._rows[key] = ordered.reset_index(drop=True)
        self._drivers: dict = {}
        for (race_id, driver_id) in self._times:
            self._drivers.setdefault(race_id, set()).add(driver_id)

    def drivers(self, race_id: str) -> tuple:
        return tuple(sorted(self._drivers.get(str(race_id), ())))

    def sync_lookup(self, race_id: str, driver_id: str,
                    T: float) -> SyncState:
        """Binary-search sync lookup; same contract as module function."""
        key = (str(race_id), str(driver_id))
        times = self._times.get(key)
        if times is None or not len(times):
            return SyncState(False, str(race_id), str(driver_id),
                             None, None, None, None)
        j = int(np.searchsorted(times, float(T), side="right")) - 1
        if j < 0:
            return SyncState(False, str(race_id), str(driver_id),
                             None, None, None, None)
        # Deterministic tie handling matches _sorted_by_time order
        # (state_time_s, lap_number): with duplicate times the LAST
        # row in sorted order wins; rows are pre-sorted, so scan the
        # tie group to its end.
        t = times[j]
        while j + 1 < len(times) and times[j + 1] == t:
            j += 1
        row = self._rows[key].iloc[j]
        obs = float(row["state_time_s"])
        return SyncState(True, str(race_id), str(driver_id),
                         int(row["lap_number"]), obs,
                         observation_age_s(float(T), obs), dict(row))

    def field_snapshot(self, race_id: str, driver_id: str, lap_number: int,
                       T: float, roster: Sequence[str]) -> FieldSnapshot:
        """Index-backed snapshot; identical contract to the module-level
        ``synchronized_field_snapshot`` (exact target + per-member sync,
        entries ordered by driver_id)."""
        key = (str(race_id), str(driver_id))
        rows = self._rows.get(key)
        target = None
        if rows is not None:
            hit = rows[(rows["lap_number"] == int(lap_number))
                       & (rows["state_time_s"] == float(T))]
            if len(hit) == 1:
                target = hit.iloc[0]
        if target is None:
            raise TargetNotFoundError(
                f"no exact target state for "
                f"{(race_id, driver_id, lap_number, T)}")
        members = sorted(set(roster) | {str(driver_id)})
        entries = []
        for member in members:
            if member == str(driver_id):
                entries.append((member, SyncState(
                    observable=True, race_id=str(race_id), driver_id=member,
                    observed_lap=int(target["lap_number"]),
                    observed_time_s=float(target["state_time_s"]),
                    observation_age_s=0.0, values=dict(target))))
            else:
                entries.append((member, self.sync_lookup(
                    race_id, member, T)))
        return FieldSnapshot(str(race_id), str(driver_id), int(lap_number),
                             float(T), dict(target), tuple(entries))
