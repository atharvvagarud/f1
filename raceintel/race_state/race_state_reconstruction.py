"""Phase-4 R2 historical RaceState reconstruction (domain projection layer).

``AnchorObservation -> exact frozen target resolution -> synchronized
field snapshot at T -> RaceState``. ONE synchronization authority: the
frozen Phase-2 ``RaceIndex``. ONE gap authority: frozen F6
``gaps_for_snapshot``. This module projects frozen synchronized state
into the R1 domain and coerces pandas/numpy scalars at the boundary.

Data-loading boundary (R0 open question 1, resolved): dependency
injection. The reconstructor takes an in-memory D9-shaped state frame
plus a roster (``extract_roster`` mapping or a results-like frame) and
builds one ``RaceIndex``. Scheduled distance is not a D9 state column,
so an optional ``race_meta`` mapping (PRE_RACE D5 ``races`` rows keyed
by race_id) fills ``scheduled_laps``; a ``total_laps_scheduled`` column
on the frame takes precedence when present. Canonical loading stays
with the frozen readers (``build_matrix.load_states`` for full scope,
per-race D9 parquet slices for serving); no second storage framework
here. A reconstructor instance is immutable and reusable across
anchors; no global mutable caches.

Exactness: anchors resolve via ``RaceIndex.field_snapshot`` (exact
``(race, driver, lap, T)`` match, no nearest substitution). Unknown
race -> ``RaceNotFoundError``; missing exact anchor ->
``AnchorNotFoundError`` (both carry structured context for R5's 404/422
mapping; no HTTP here).

Past-only sources (all already past-safe on the D9 row by frozen
Phase-1/2 construction; this module only selects, never recomputes):
driver facts from each member's own synchronized observed row; weather
from the anchor row's backward-as-of ``wx_*`` block; race control from
the anchor row's D9 track-state flags + latest-message lineage; pit /
stint from observed-row start-side facts and D9 completed-so-far
counts. Gap geometry per member is the frozen F6 evaluation of that
member's OWN observed state (sync at its own observed time) — the same
evaluation ``gap_batch`` performs for the row and the R3 bridge will
recompute from the member's ``FeatureRequest``; for the anchor this
coincides with the snapshot-T evaluation. Never T-minus-crossing
arithmetic (observation age is not a race gap).

This module must never import ``v2.model_lab``, sklearn, ``ml.*``,
API code, or call ``features_for_batch`` (pinned by test). It emits no
ALL_84 and no probabilities; that belongs to R3/R4.
"""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence

import pandas as pd

from raceintel.race_state import race_state as RS
from raceintel.features.gaps import GapStatus, gaps_for_snapshot
from raceintel.features.temporal import (
    RaceIndex,
    TargetNotFoundError,
    extract_roster,
)


class RaceStateReconstructionError(RS.RaceStateError):
    """Base reconstruction error (carries context, never HTTP codes)."""


class RaceNotFoundError(RaceStateReconstructionError):
    """No roster or state coverage for the requested race."""

    def __init__(self, race_id: str):
        super().__init__(f"unknown race: {race_id!r}")
        self.race_id = race_id


class AnchorNotFoundError(RaceStateReconstructionError):
    """No exact D9 row for the requested anchor (never substituted)."""

    def __init__(self, race_id: str, driver_id: str, lap_number: int,
                 state_time_s: float):
        super().__init__(
            "no exact anchor state for "
            f"{(race_id, driver_id, lap_number, state_time_s)}; list exact "
            f"anchors instead of substituting")
        self.race_id = race_id
        self.driver_id = driver_id
        self.lap_number = lap_number
        self.state_time_s = state_time_s


#: D9 columns read by the projection (identity/clock plus every mapped
#: field). Presence is required; nulls are preserved per-field.
REQUIRED_COLUMNS = frozenset({
    "race_id", "driver_id", "lap_number", "state_time_s",
    "season", "round_no", "circuit_id",
    "position", "compound", "tyre_life", "fresh_tyre", "stint_number",
    "stint_lap", "pit_stops_completed_so_far", "laps_since_last_pit_stop",
    "constructor_id", "driver_number",
    "track_state", "flag_yellow", "flag_safety_car", "flag_red", "flag_vsc",
    "rc_last_message_category", "rc_last_message_flag",
    "rc_last_message_age_s",
    "race_leader_laps_at_state", "race_progress_frac",
    "wx_air_temp_c", "wx_track_temp_c", "wx_humidity_pct",
    "wx_pressure_hpa", "wx_wind_speed", "wx_wind_direction_deg",
    "wx_rainfall", "wx_observed_at_s", "wx_age_s",
})

#: D9-adjacent columns consumed when present (race-grain metadata that a
#: bare state slice may not carry; absence yields None or race_meta fill).
OPTIONAL_COLUMNS = frozenset({"total_laps_scheduled"})


def _coerce(value: object, *, kind: str, field: str) -> object:
    """Single boundary coercion: canonical scalars -> R1 primitives.

    Pandas/numpy missing (None/NaN/NA/NaT) -> None for nullable fields.
    Non-finite floats (Inf) are never valid domain state and raise
    instead of silently becoming None. Strings pass through verbatim
    (canonical normalization already applied upstream).
    """
    if value is None:
        return None
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        raise RaceStateReconstructionError(
            f"field {field!r}: uncoercible value {value!r}")
    try:
        if kind == "int":
            if isinstance(value, float) and not math.isfinite(value):
                raise RaceStateReconstructionError(
                    f"field {field!r}: non-finite {value!r} is not "
                    f"unavailable state")
            return int(value)
        if kind == "float":
            result = float(value)
            if not math.isfinite(result):
                raise RaceStateReconstructionError(
                    f"field {field!r}: non-finite {value!r} is not "
                    f"unavailable state")
            return result
        if kind == "bool":
            return bool(value)
        if kind == "str":
            return str(value)
    except RaceStateReconstructionError:
        raise
    except (TypeError, ValueError) as exc:
        raise RaceStateReconstructionError(
            f"field {field!r}: cannot coerce {value!r} to {kind}: {exc}")
    raise RaceStateReconstructionError(f"field {field!r}: unknown kind "
                                       f"{kind!r}")


def _project_gaps(leader_gap, ahead_gap) -> dict:
    """GapResult pair -> R1 domain gap slots.

    The derivation (statuses, seconds, lap differences) is frozen F6;
    validity mirrors ``gaps._gap_feature_values`` tri-state exactly
    (None only when the reference is unknown; a known reference with no
    valid seconds — leader with no car ahead, laps-apart, red-flag —
    is False).
    """
    def valid(gap) -> bool | None:
        if gap.reference_id is None and gap.status in (
                GapStatus.REFERENCE_UNOBSERVED, GapStatus.ORDER_AMBIGUOUS):
            return None
        return bool(gap.seconds_valid)

    return {
        "gap_to_leader_s": leader_gap.seconds_gap,
        "gap_to_leader_valid": valid(leader_gap),
        "gap_to_leader_laps": leader_gap.lap_difference,
        "gap_to_ahead_s": ahead_gap.seconds_gap,
        "gap_to_ahead_valid": valid(ahead_gap),
        "gap_to_ahead_laps": ahead_gap.lap_difference,
    }


def _driver_state(driver_id: str, sync, gaps: dict) -> RS.DriverRaceState:
    if not sync.observable:
        return RS.DriverRaceState.unobserved(driver_id)
    row = sync.values or {}
    return RS.DriverRaceState(
        driver_id=driver_id,
        observable=True,
        observed_lap_number=int(sync.observed_lap),
        observed_time_s=float(sync.observed_time_s),
        observation_age_s=float(sync.observation_age_s),
        position=_coerce(row.get("position"), kind="int",
                         field="position"),
        gap_to_leader_s=_coerce(gaps["gap_to_leader_s"], kind="float",
                                field="gap_to_leader_s")
        if gaps["gap_to_leader_s"] is not None else None,
        gap_to_leader_valid=gaps["gap_to_leader_valid"],
        gap_to_leader_laps=_coerce(gaps["gap_to_leader_laps"], kind="int",
                                   field="gap_to_leader_laps")
        if gaps["gap_to_leader_laps"] is not None else None,
        gap_to_ahead_s=_coerce(gaps["gap_to_ahead_s"], kind="float",
                               field="gap_to_ahead_s")
        if gaps["gap_to_ahead_s"] is not None else None,
        gap_to_ahead_valid=gaps["gap_to_ahead_valid"],
        gap_to_ahead_laps=_coerce(gaps["gap_to_ahead_laps"], kind="int",
                                  field="gap_to_ahead_laps")
        if gaps["gap_to_ahead_laps"] is not None else None,
        compound=_coerce(row.get("compound"), kind="str",
                         field="compound"),
        tyre_life=_coerce(row.get("tyre_life"), kind="int",
                          field="tyre_life"),
        fresh_tyre=_coerce(row.get("fresh_tyre"), kind="bool",
                           field="fresh_tyre"),
        stint_number=_coerce(row.get("stint_number"), kind="int",
                             field="stint_number"),
        stint_lap=_coerce(row.get("stint_lap"), kind="int",
                          field="stint_lap"),
        pit_stops_completed_so_far=_coerce(
            row.get("pit_stops_completed_so_far"), kind="int",
            field="pit_stops_completed_so_far"),
        laps_since_last_pit_stop=_coerce(
            row.get("laps_since_last_pit_stop"), kind="int",
            field="laps_since_last_pit_stop"),
        constructor_id=_coerce(row.get("constructor_id"), kind="str",
                               field="constructor_id"),
        driver_number=_coerce(row.get("driver_number"), kind="int",
                              field="driver_number"),
    )


class RaceStateReconstructor:
    """Deterministic historical reconstruction over a D9 state frame."""

    def __init__(self, states: pd.DataFrame,
                 roster: Mapping[str, Sequence[str]] | pd.DataFrame,
                 race_meta: Mapping[str, Mapping[str, object]] | None = None):
        """Bind a D9-shaped state frame (+ roster, + optional PRE_RACE meta).

        ``race_meta`` maps race_id to race-grain metadata; only
        ``scheduled_laps`` is consumed (PRE_RACE D5 ``races`` entity —
        scheduled distance is not a D9 state column). Column
        ``total_laps_scheduled`` on the frame takes precedence when
        present; otherwise ``race_meta``; otherwise None (contract
        permits null scheduled distance).
        """
        if not isinstance(states, pd.DataFrame):
            raise RaceStateReconstructionError(
                f"states must be a D9-shaped DataFrame, got {type(states)}")
        missing = sorted(REQUIRED_COLUMNS - set(states.columns))
        if missing:
            raise RaceStateReconstructionError(
                f"state frame is missing required columns: {missing}")
        if isinstance(roster, pd.DataFrame):
            roster = extract_roster(roster)
        try:
            normalized = {str(race): tuple(sorted({str(d) for d in ids}))
                          for race, ids in dict(roster).items()}
        except (TypeError, ValueError) as exc:
            raise RaceStateReconstructionError(
                f"roster must map race_id to driver-id sequences: {exc}")
        self._states = states
        self._roster = normalized
        self._race_meta = dict(race_meta) if race_meta is not None else {}
        self._index = RaceIndex(states)

    @property
    def roster(self) -> dict:
        """Normalized roster: race_id -> sorted driver ids (copy)."""
        return {race: tuple(ids) for race, ids in self._roster.items()}

    def reconstruct(self, anchor: RS.AnchorObservation) -> RS.RaceState:
        """Project the exact anchor snapshot at T into the R1 domain."""
        if not isinstance(anchor, RS.AnchorObservation):
            raise RaceStateReconstructionError(
                f"anchor must be an AnchorObservation, got {anchor!r}")
        race_id = anchor.race_id
        if race_id not in self._roster \
                and not self._index.drivers(race_id):
            raise RaceNotFoundError(race_id)
        members = sorted(set(self._roster.get(race_id, ()))
                         | {anchor.anchor_driver_id})
        try:
            snap = self._index.field_snapshot(
                race_id, anchor.anchor_driver_id,
                anchor.anchor_lap_number, anchor.anchor_state_time_s,
                members)
        except TargetNotFoundError:
            raise AnchorNotFoundError(
                race_id, anchor.anchor_driver_id,
                anchor.anchor_lap_number,
                anchor.anchor_state_time_s) from None
        entries = dict(snap.entries)
        target = dict(snap.target_values)

        drivers = []
        for member in members:
            sync = entries[member]
            if not sync.observable:
                drivers.append(RS.DriverRaceState.unobserved(member))
                continue
            # Own-observed-time gap geometry (frozen F6): sync every
            # roster member at the member's own clock so reference ages
            # are >= 0 by construction, exactly as gap_batch evaluates
            # this row. Anchor member: own clock == T, identical to the
            # snapshot evaluation.
            own_t = float(sync.observed_time_s)
            own_entries = {m: self._index.sync_lookup(race_id, m, own_t)
                           for m in members}
            leader_gap, ahead_gap = gaps_for_snapshot(
                dict(sync.values), own_entries)
            drivers.append(_driver_state(
                member, sync, _project_gaps(leader_gap, ahead_gap)))

        row = target
        scheduled = row.get("total_laps_scheduled")
        if _is_pd_missing(scheduled):
            meta = self._race_meta.get(race_id, {})
            scheduled = meta.get("scheduled_laps")
        weather = RS.WeatherState(
            air_temp_c=_coerce(row.get("wx_air_temp_c"), kind="float",
                               field="wx_air_temp_c"),
            track_temp_c=_coerce(row.get("wx_track_temp_c"), kind="float",
                                 field="wx_track_temp_c"),
            humidity_pct=_coerce(row.get("wx_humidity_pct"), kind="float",
                                 field="wx_humidity_pct"),
            pressure_hpa=_coerce(row.get("wx_pressure_hpa"), kind="float",
                                 field="wx_pressure_hpa"),
            wind_speed=_coerce(row.get("wx_wind_speed"), kind="float",
                               field="wx_wind_speed"),
            wind_direction_deg=_coerce(row.get("wx_wind_direction_deg"),
                                       kind="float",
                                       field="wx_wind_direction_deg"),
            rainfall=_coerce(row.get("wx_rainfall"), kind="bool",
                             field="wx_rainfall"),
            observed_at_s=_coerce(row.get("wx_observed_at_s"), kind="float",
                                  field="wx_observed_at_s"),
            observation_age_s=_coerce(row.get("wx_age_s"), kind="float",
                                      field="wx_age_s"),
        )
        race_control = RS.RaceControlState(
            track_state=_coerce(row.get("track_state"), kind="str",
                                field="track_state"),
            flag_yellow=_coerce(row.get("flag_yellow"), kind="bool",
                                field="flag_yellow"),
            flag_safety_car=_coerce(row.get("flag_safety_car"), kind="bool",
                                    field="flag_safety_car"),
            flag_red=_coerce(row.get("flag_red"), kind="bool",
                             field="flag_red"),
            flag_vsc=_coerce(row.get("flag_vsc"), kind="bool",
                             field="flag_vsc"),
            last_message_category=_coerce(
                row.get("rc_last_message_category"), kind="str",
                field="rc_last_message_category"),
            last_message_flag=_coerce(row.get("rc_last_message_flag"),
                                      kind="str",
                                      field="rc_last_message_flag"),
            last_message_age_s=_coerce(row.get("rc_last_message_age_s"),
                                       kind="float",
                                       field="rc_last_message_age_s"),
        )
        context = RS.RaceContext(
            race_leader_laps_at_state=_coerce(
                row.get("race_leader_laps_at_state"), kind="int",
                field="race_leader_laps_at_state"),
            race_progress_frac=_coerce(row.get("race_progress_frac"),
                                       kind="float",
                                       field="race_progress_frac"),
            scheduled_laps=_coerce(scheduled, kind="int",
                                   field="scheduled_laps"),
            season=_coerce(row.get("season"), kind="int", field="season"),
            round_no=_coerce(row.get("round_no"), kind="int",
                             field="round_no"),
            circuit_id=_coerce(row.get("circuit_id"), kind="str",
                               field="circuit_id"),
        )
        return RS.RaceState(
            race_id=race_id,
            anchor_driver_id=anchor.anchor_driver_id,
            anchor_lap_number=anchor.anchor_lap_number,
            state_time_s=anchor.anchor_state_time_s,
            drivers=tuple(drivers),
            race_context=context,
            weather=weather,
            race_control=race_control,
        )


def _is_pd_missing(value: object) -> bool:
    try:
        return bool(pd.isna(value))
    except (TypeError, ValueError):
        return False


def reconstruct_race_state(
        anchor: RS.AnchorObservation, states: pd.DataFrame,
        roster: Mapping[str, Sequence[str]] | pd.DataFrame,
        race_meta: Mapping[str, Mapping[str, object]] | None = None,
) -> RS.RaceState:
    """One-shot reconstruction (builds an index; reuse the class for many)."""
    return RaceStateReconstructor(states, roster,
                                  race_meta=race_meta).reconstruct(anchor)
