"""Phase-4 R1 canonical RaceState domain model.

"What was observably known about this race at synchronized historical
time T?" — typed, frozen (immutable) dataclasses with NO data loading,
NO reconstruction, NO feature computation, NO model, NO labels.

Time-T contract (R0 section 4): the snapshot key is an anchor observation
``(race_id, anchor_driver_id, anchor_lap_number, anchor_state_time_s)``
where ``state_time_s`` is the anchor row's D9 LAP_END clock and the
knowledge boundary for the whole snapshot. ``lap_number`` is per-driver
progress, never a global clock. Resolution (exact ``RaceIndex`` target
lookup, rival sync ``<= T``, roster handling) belongs to R2; this module
only represents the RESOLVED domain state.

Every field source: D9 state columns (D6 base + D7 as-of extensions + D9
derived temporal state) plus ``extract_roster`` identity columns. No
Phase-2 label value, no ALL_84 feature, no estimator may enter here
(guarded by :func:`label_outcome_fields` + the R1 test suite).

Provenance vocabulary per field: ``factual_observed`` (copied from a
state row observable at or before T) or ``derived_past_only``
(deterministic past-only derivation such as observation age). Never
``model_feature``, never future outcome.

Red-flag / status semantics: values are carried verbatim (including
nulls and ``track_state`` tokens); gaps during suspension stay nullable
with explicit validity flags and are never reinterpreted here.

R2 construction note: convert pandas/numpy scalars to plain Python
(``str``/``int``/``float``/``bool``) before constructing these types;
numpy scalars are rejected structurally (exact-type guards).

STDLIB ONLY. This module must never import ``v2.model_lab``, sklearn,
FastAPI, ``ml.*``, API routes, holdout machinery, pandas, or numpy
(pinned by test).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, fields

from v2.d9schema import TRACK_STATE_TOKENS

#: Provenance tag for values copied from a state row observable at/under T.
FACTUAL_OBSERVED = "factual_observed"
#: Provenance tag for deterministic past-only derivations (ages, validity).
DERIVED_PAST_ONLY = "derived_past_only"

#: Tolerance for the observation-age consistency check
#: ``age == state_time_s - observed_time_s`` (exact when both sides copy
#: the same frozen computation; tolerance guards binary-float formatting).
AGE_CONSISTENCY_TOL_S = 1e-6


class RaceStateError(ValueError):
    """Base domain error for the RaceState model."""


class InvalidRaceStateError(RaceStateError):
    """A RaceState domain object violates its construction contract."""


# ---------------------------------------------------------------------------
# Label / future-outcome firewall.
# ---------------------------------------------------------------------------

#: Exact canonical supervised-target names (v2/labels/contracts.py
#: CANONICAL_LABEL_NAMES, restated as literals so this module never imports
#: label values; the R1 suite asserts equality with the canonical set).
_CANONICAL_TARGET_NAMES = frozenset({
    "final_position",
    "is_winner",
    "is_podium",
    "scored_points",
    "position_change_from_state",
    "gains_position_by_finish",
    "loses_position_by_finish",
})

#: D9 outcome-label facts (race_driver_labels; POST_RACE / LABEL_ONLY).
_D9_LABEL_OUTCOME_NAMES = frozenset({
    "position_final",
    "classified_position",
    "position_text",
    "status_text",
    "points",
    "laps_completed",
    "classified_flag",
    "winner_flag",
    "podium_flag",
    "points_finish_flag",
})

#: Task eligibility masks (Phase-2/3 training scope; never domain state).
_MASK_NAMES = frozenset({
    "eligible_is_winner",
    "eligible_is_podium",
    "eligible_scored_points",
    "eligible_ordinal_final_position",
    "eligible_gain_loss",
})

#: Future-state leakage names (stint end is future inside the stint;
#: no DNF target exists, so any dnf-shaped name is forbidden).
_FUTURE_STATE_NAMES = frozenset({
    "end_lap",
    "dnf_flag",
    "dnf",
})


def label_outcome_fields() -> frozenset:
    """Outcome names that must never become RaceState domain fields.

    Mirrors ``v2.features.registry.label_outcome_fields`` for the domain
    layer, minus pure identity names (``race_id``/``season``/``driver_id``
    are legitimate domain identity, not outcomes). Exact names only;
    never substring matching.
    """
    return (
        _CANONICAL_TARGET_NAMES
        | _D9_LABEL_OUTCOME_NAMES
        | _MASK_NAMES
        | _FUTURE_STATE_NAMES
    )


# ---------------------------------------------------------------------------
# Validation helpers (stdlib type guards; numpy/pandas scalars rejected).
# ---------------------------------------------------------------------------

def _req_id(value: object, name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise InvalidRaceStateError(
            f"{name} must be a non-empty canonical identity string, "
            f"got {value!r}")
    return value


def _req_int(value: object, name: str, minimum: int | None = None) -> int:
    # Exact-type check (not isinstance): numpy/pandas integer scalars and
    # bools are rejected structurally; callers coerce via int().
    if type(value) is not int:
        raise InvalidRaceStateError(
            f"{name} must be a plain Python int (coerce numpy via int()), "
            f"got {value!r}")
    if minimum is not None and value < minimum:
        raise InvalidRaceStateError(
            f"{name} must be >= {minimum}, got {value!r}")
    return value


def _req_float(value: object, name: str) -> float:
    # Exact-type check: numpy floating scalars subclass Python float, so
    # isinstance would leak them; callers coerce via float().
    if type(value) not in (int, float):
        raise InvalidRaceStateError(
            f"{name} must be a finite plain Python number "
            f"(coerce numpy via float()), got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise InvalidRaceStateError(
            f"{name} must be finite (no NaN/Infinity), got {value!r}")
    return result


def _opt_str(value: object, name: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise InvalidRaceStateError(
            f"{name} must be a string or None, got {value!r}")
    return value


def _opt_int(value: object, name: str) -> int | None:
    if value is None:
        return None
    return _req_int(value, name)


def _opt_float(value: object, name: str) -> float | None:
    if value is None:
        return None
    return _req_float(value, name)


def _opt_bool(value: object, name: str) -> bool | None:
    if value is None:
        return None
    if type(value) is not bool:
        raise InvalidRaceStateError(
            f"{name} must be a bool or None, got {value!r}")
    return value


# ---------------------------------------------------------------------------
# Anchor observation.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class AnchorObservation:
    """Canonical Phase-4 Time-T key: a REQUESTED anchor identity.

    ``anchor_state_time_s`` is the D9 LAP_END clock of the anchor driver's
    own lap ``anchor_lap_number`` (per-driver progress, not a global lap).
    No nearest-state behaviour and no resolution logic live here; R2
    resolves this against the exact D9 row and raises on miss.
    """

    race_id: str
    anchor_driver_id: str
    anchor_lap_number: int
    anchor_state_time_s: float

    def __post_init__(self) -> None:
        object.__setattr__(self, "race_id",
                            _req_id(self.race_id, "race_id"))
        object.__setattr__(self, "anchor_driver_id",
                            _req_id(self.anchor_driver_id,
                                    "anchor_driver_id"))
        object.__setattr__(self, "anchor_lap_number",
                            _req_int(self.anchor_lap_number,
                                     "anchor_lap_number", minimum=1))
        object.__setattr__(self, "anchor_state_time_s",
                            _req_float(self.anchor_state_time_s,
                                       "anchor_state_time_s"))

    def to_dict(self) -> dict:
        return {
            "race_id": self.race_id,
            "anchor_driver_id": self.anchor_driver_id,
            "anchor_lap_number": self.anchor_lap_number,
            "anchor_state_time_s": self.anchor_state_time_s,
        }


# ---------------------------------------------------------------------------
# Driver-level observable state.
# ---------------------------------------------------------------------------

#: DriverRaceState fields that are deterministic past-only derivations
#: (everything else on the type is factual_observed).
DRIVER_DERIVED_PAST_ONLY_FIELDS = frozenset({
    "observation_age_s",
    "gap_to_leader_valid",
    "gap_to_ahead_valid",
    "stint_lap",
    "pit_stops_completed_so_far",
    "laps_since_last_pit_stop",
})


def driver_field_provenance(name: str) -> str:
    """Provenance tag for one DriverRaceState field name."""
    names = {f.name for f in fields(DriverRaceState)}
    if name not in names:
        raise RaceStateError(f"unknown DriverRaceState field: {name!r}")
    if name in DRIVER_DERIVED_PAST_ONLY_FIELDS:
        return DERIVED_PAST_ONLY
    return FACTUAL_OBSERVED


@dataclass(frozen=True)
class DriverRaceState:
    """One roster member's observable state at snapshot time T.

    ``observable=False`` means no state row exists at or before T (stale
    tail or never-observable zero-state entrant): every state field is
    then None and nothing is fabricated (in particular no ``position=0``
    or ``probability=0`` zero-fill). Whether an unobservable member is a
    permanent zero-state entrant or merely pre-first-observation is NOT
    decidable from a single snapshot; R4 maps both to null + reason.

    Staleness: ``observed_time_s`` is the driver's OWN clock (``<= T``);
    ``observation_age_s = T - observed_time_s``. Drivers are never
    silently presented as observed exactly at T.

    Gaps (F6 frozen semantics): seconds separations are valid ONLY under
    green, comparable laps, no suspension; otherwise the value is None
    with its validity companion False/None. Validity flags are
    past-only derivations, not observations.
    """

    driver_id: str
    observable: bool
    observed_lap_number: int | None = None
    observed_time_s: float | None = None
    observation_age_s: float | None = None
    position: int | None = None
    gap_to_leader_s: float | None = None
    gap_to_leader_valid: bool | None = None
    gap_to_leader_laps: int | None = None
    gap_to_ahead_s: float | None = None
    gap_to_ahead_valid: bool | None = None
    gap_to_ahead_laps: int | None = None
    compound: str | None = None
    tyre_life: int | None = None
    fresh_tyre: bool | None = None
    stint_number: int | None = None
    stint_lap: int | None = None
    pit_stops_completed_so_far: int | None = None
    laps_since_last_pit_stop: int | None = None
    constructor_id: str | None = None
    driver_number: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "driver_id",
                            _req_id(self.driver_id, "driver_id"))
        if not isinstance(self.observable, bool):
            raise InvalidRaceStateError(
                f"observable must be a bool, got {self.observable!r}")
        object.__setattr__(self, "observed_lap_number",
                            _opt_int(self.observed_lap_number,
                                     "observed_lap_number"))
        object.__setattr__(self, "observed_time_s",
                            _opt_float(self.observed_time_s,
                                       "observed_time_s"))
        object.__setattr__(self, "observation_age_s",
                            _opt_float(self.observation_age_s,
                                       "observation_age_s"))
        object.__setattr__(self, "position",
                            _opt_int(self.position, "position"))
        object.__setattr__(self, "gap_to_leader_s",
                            _opt_float(self.gap_to_leader_s,
                                       "gap_to_leader_s"))
        object.__setattr__(self, "gap_to_leader_valid",
                            _opt_bool(self.gap_to_leader_valid,
                                      "gap_to_leader_valid"))
        object.__setattr__(self, "gap_to_leader_laps",
                            _opt_int(self.gap_to_leader_laps,
                                     "gap_to_leader_laps"))
        object.__setattr__(self, "gap_to_ahead_s",
                            _opt_float(self.gap_to_ahead_s,
                                       "gap_to_ahead_s"))
        object.__setattr__(self, "gap_to_ahead_valid",
                            _opt_bool(self.gap_to_ahead_valid,
                                      "gap_to_ahead_valid"))
        object.__setattr__(self, "gap_to_ahead_laps",
                            _opt_int(self.gap_to_ahead_laps,
                                     "gap_to_ahead_laps"))
        object.__setattr__(self, "compound",
                            _opt_str(self.compound, "compound"))
        object.__setattr__(self, "tyre_life",
                            _opt_int(self.tyre_life, "tyre_life"))
        object.__setattr__(self, "fresh_tyre",
                            _opt_bool(self.fresh_tyre, "fresh_tyre"))
        object.__setattr__(self, "stint_number",
                            _opt_int(self.stint_number, "stint_number"))
        object.__setattr__(self, "stint_lap",
                            _opt_int(self.stint_lap, "stint_lap"))
        object.__setattr__(self, "pit_stops_completed_so_far",
                            _opt_int(self.pit_stops_completed_so_far,
                                     "pit_stops_completed_so_far"))
        object.__setattr__(self, "laps_since_last_pit_stop",
                            _opt_int(self.laps_since_last_pit_stop,
                                     "laps_since_last_pit_stop"))
        object.__setattr__(self, "constructor_id",
                            _opt_str(self.constructor_id, "constructor_id"))
        object.__setattr__(self, "driver_number",
                            _opt_int(self.driver_number, "driver_number"))

        if self.observed_lap_number is not None \
                and self.observed_lap_number < 1:
            raise InvalidRaceStateError(
                "observed_lap_number must be >= 1 when present, "
                f"got {self.observed_lap_number!r}")
        if self.observation_age_s is not None \
                and self.observation_age_s < 0:
            raise InvalidRaceStateError(
                "observation_age_s must be >= 0 when present, "
                f"got {self.observation_age_s!r}")

        if not self.observable:
            nulls = {
                "observed_lap_number": self.observed_lap_number,
                "observed_time_s": self.observed_time_s,
                "observation_age_s": self.observation_age_s,
                "position": self.position,
                "gap_to_leader_s": self.gap_to_leader_s,
                "gap_to_leader_valid": self.gap_to_leader_valid,
                "gap_to_leader_laps": self.gap_to_leader_laps,
                "gap_to_ahead_s": self.gap_to_ahead_s,
                "gap_to_ahead_valid": self.gap_to_ahead_valid,
                "gap_to_ahead_laps": self.gap_to_ahead_laps,
                "compound": self.compound,
                "tyre_life": self.tyre_life,
                "fresh_tyre": self.fresh_tyre,
                "stint_number": self.stint_number,
                "stint_lap": self.stint_lap,
                "pit_stops_completed_so_far":
                    self.pit_stops_completed_so_far,
                "laps_since_last_pit_stop": self.laps_since_last_pit_stop,
                "constructor_id": self.constructor_id,
                "driver_number": self.driver_number,
            }
            invented = sorted(n for n, v in nulls.items() if v is not None)
            if invented:
                raise InvalidRaceStateError(
                    f"unobservable driver {self.driver_id!r} must carry "
                    f"no state (got values for {invented}); roster members "
                    f"without observations are explicit nulls, never fills")
        else:
            if self.observed_lap_number is None \
                    or self.observed_time_s is None:
                raise InvalidRaceStateError(
                    f"observable driver {self.driver_id!r} requires "
                    f"observed_lap_number and observed_time_s")

    @classmethod
    def unobserved(cls, driver_id: str) -> "DriverRaceState":
        """Explicit null entry for a roster member with no state ``<= T``.

        Used for both pre-first-observation members and the permanent
        zero-state entrants; the distinction needs history (R4), not a
        single snapshot.
        """
        return cls(driver_id=driver_id, observable=False)

    def to_dict(self) -> dict:
        return {
            "driver_id": self.driver_id,
            "observable": self.observable,
            "observed_lap_number": self.observed_lap_number,
            "observed_time_s": self.observed_time_s,
            "observation_age_s": self.observation_age_s,
            "position": self.position,
            "gap_to_leader_s": self.gap_to_leader_s,
            "gap_to_leader_valid": self.gap_to_leader_valid,
            "gap_to_leader_laps": self.gap_to_leader_laps,
            "gap_to_ahead_s": self.gap_to_ahead_s,
            "gap_to_ahead_valid": self.gap_to_ahead_valid,
            "gap_to_ahead_laps": self.gap_to_ahead_laps,
            "compound": self.compound,
            "tyre_life": self.tyre_life,
            "fresh_tyre": self.fresh_tyre,
            "stint_number": self.stint_number,
            "stint_lap": self.stint_lap,
            "pit_stops_completed_so_far": self.pit_stops_completed_so_far,
            "laps_since_last_pit_stop": self.laps_since_last_pit_stop,
            "constructor_id": self.constructor_id,
            "driver_number": self.driver_number,
        }


# ---------------------------------------------------------------------------
# Race-level context.
# ---------------------------------------------------------------------------

#: RaceContext fields that are deterministic past-only derivations.
CONTEXT_DERIVED_PAST_ONLY_FIELDS = frozenset({"race_progress_frac"})

#: WeatherState lineage anchors (as-of join audit, not signal samples).
WEATHER_DERIVED_PAST_ONLY_FIELDS = frozenset({
    "observed_at_s",
    "observation_age_s",
})

#: RaceControlState lineage anchors.
RACE_CONTROL_DERIVED_PAST_ONLY_FIELDS = frozenset({"last_message_age_s"})


@dataclass(frozen=True)
class RaceContext:
    """Factual race-level progress at T.

    Progress is ``race_leader_laps_at_state`` over the PRE_RACE scheduled
    distance (never the eventual total). All fields nullable: partial /
    shortened races and unknown schedule metadata must not break the
    domain.
    """

    race_leader_laps_at_state: int | None = None
    race_progress_frac: float | None = None
    scheduled_laps: int | None = None
    season: int | None = None
    round_no: int | None = None
    circuit_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "race_leader_laps_at_state",
                            _opt_int(self.race_leader_laps_at_state,
                                     "race_leader_laps_at_state"))
        object.__setattr__(self, "race_progress_frac",
                            _opt_float(self.race_progress_frac,
                                       "race_progress_frac"))
        object.__setattr__(self, "scheduled_laps",
                            _opt_int(self.scheduled_laps, "scheduled_laps"))
        object.__setattr__(self, "season",
                            _opt_int(self.season, "season"))
        object.__setattr__(self, "round_no",
                            _opt_int(self.round_no, "round_no"))
        object.__setattr__(self, "circuit_id",
                            _opt_str(self.circuit_id, "circuit_id"))

    def to_dict(self) -> dict:
        return {
            "race_leader_laps_at_state": self.race_leader_laps_at_state,
            "race_progress_frac": self.race_progress_frac,
            "scheduled_laps": self.scheduled_laps,
            "season": self.season,
            "round_no": self.round_no,
            "circuit_id": self.circuit_id,
        }


@dataclass(frozen=True)
class WeatherState:
    """Weather known at T: strict backward as-of samples, null-preserving.

    ``observation_age_s = T - observed_at_s`` is audit provenance, never
    a feature. Null throughout means no prior observation (not clear
    weather).
    """

    air_temp_c: float | None = None
    track_temp_c: float | None = None
    humidity_pct: float | None = None
    pressure_hpa: float | None = None
    wind_speed: float | None = None
    wind_direction_deg: float | None = None
    rainfall: bool | None = None
    observed_at_s: float | None = None
    observation_age_s: float | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "air_temp_c",
                            _opt_float(self.air_temp_c, "air_temp_c"))
        object.__setattr__(self, "track_temp_c",
                            _opt_float(self.track_temp_c, "track_temp_c"))
        object.__setattr__(self, "humidity_pct",
                            _opt_float(self.humidity_pct, "humidity_pct"))
        object.__setattr__(self, "pressure_hpa",
                            _opt_float(self.pressure_hpa, "pressure_hpa"))
        object.__setattr__(self, "wind_speed",
                            _opt_float(self.wind_speed, "wind_speed"))
        object.__setattr__(self, "wind_direction_deg",
                            _opt_float(self.wind_direction_deg,
                                       "wind_direction_deg"))
        object.__setattr__(self, "rainfall",
                            _opt_bool(self.rainfall, "rainfall"))
        object.__setattr__(self, "observed_at_s",
                            _opt_float(self.observed_at_s, "observed_at_s"))
        object.__setattr__(self, "observation_age_s",
                            _opt_float(self.observation_age_s,
                                       "observation_age_s"))
        if self.observation_age_s is not None \
                and self.observation_age_s < 0:
            raise InvalidRaceStateError(
                "weather observation_age_s must be >= 0, "
                f"got {self.observation_age_s!r}")

    def to_dict(self) -> dict:
        return {
            "air_temp_c": self.air_temp_c,
            "track_temp_c": self.track_temp_c,
            "humidity_pct": self.humidity_pct,
            "pressure_hpa": self.pressure_hpa,
            "wind_speed": self.wind_speed,
            "wind_direction_deg": self.wind_direction_deg,
            "rainfall": self.rainfall,
            "observed_at_s": self.observed_at_s,
            "observation_age_s": self.observation_age_s,
        }


@dataclass(frozen=True)
class RaceControlState:
    """Race-control state known at T, carried verbatim.

    ``track_state`` is the D9 contemporaneous token derived from the
    source TrackStatus code channel (last code char of the lap); the
    ``flag_*`` companions are its deterministic per-flag view. The
    latest timestamped message's raw category/flag attach as past-message
    attributes (message text excluded: lineage-only, kept out of the
    minimal domain). Nothing here is reinterpreted (no gap invalidation,
    no retirement inference).
    """

    track_state: str | None = None
    flag_yellow: bool | None = None
    flag_safety_car: bool | None = None
    flag_red: bool | None = None
    flag_vsc: bool | None = None
    last_message_category: str | None = None
    last_message_flag: str | None = None
    last_message_age_s: float | None = None

    def __post_init__(self) -> None:
        value = _opt_str(self.track_state, "track_state")
        if value is not None and value not in TRACK_STATE_TOKENS:
            raise InvalidRaceStateError(
                f"track_state must be one of {TRACK_STATE_TOKENS} or None, "
                f"got {value!r}")
        object.__setattr__(self, "track_state", value)
        object.__setattr__(self, "flag_yellow",
                            _opt_bool(self.flag_yellow, "flag_yellow"))
        object.__setattr__(self, "flag_safety_car",
                            _opt_bool(self.flag_safety_car,
                                      "flag_safety_car"))
        object.__setattr__(self, "flag_red",
                            _opt_bool(self.flag_red, "flag_red"))
        object.__setattr__(self, "flag_vsc",
                            _opt_bool(self.flag_vsc, "flag_vsc"))
        object.__setattr__(self, "last_message_category",
                            _opt_str(self.last_message_category,
                                     "last_message_category"))
        object.__setattr__(self, "last_message_flag",
                            _opt_str(self.last_message_flag,
                                     "last_message_flag"))
        object.__setattr__(self, "last_message_age_s",
                            _opt_float(self.last_message_age_s,
                                       "last_message_age_s"))
        if self.last_message_age_s is not None \
                and self.last_message_age_s < 0:
            raise InvalidRaceStateError(
                "last_message_age_s must be >= 0, "
                f"got {self.last_message_age_s!r}")

    def to_dict(self) -> dict:
        return {
            "track_state": self.track_state,
            "flag_yellow": self.flag_yellow,
            "flag_safety_car": self.flag_safety_car,
            "flag_red": self.flag_red,
            "flag_vsc": self.flag_vsc,
            "last_message_category": self.last_message_category,
            "last_message_flag": self.last_message_flag,
            "last_message_age_s": self.last_message_age_s,
        }


# ---------------------------------------------------------------------------
# Snapshot root.
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class RaceState:
    """Synchronized race snapshot at T for one anchor observation.

    ``drivers`` holds ONE entry per roster member in ``driver_id`` order
    (observable members with state, unobservable members as explicit
    nulls — including the permanent zero-state entrants, which are never
    dropped and never fabricated). Entries carry no ``race_id`` of their
    own: same-race membership is structural (all entries are built for
    this snapshot's race), never joined on presentation attributes.
    """

    race_id: str
    anchor_driver_id: str
    anchor_lap_number: int
    state_time_s: float
    drivers: tuple
    race_context: RaceContext
    weather: WeatherState
    race_control: RaceControlState

    def __post_init__(self) -> None:
        object.__setattr__(self, "race_id",
                            _req_id(self.race_id, "race_id"))
        object.__setattr__(self, "anchor_driver_id",
                            _req_id(self.anchor_driver_id,
                                    "anchor_driver_id"))
        object.__setattr__(self, "anchor_lap_number",
                            _req_int(self.anchor_lap_number,
                                     "anchor_lap_number", minimum=1))
        object.__setattr__(self, "state_time_s",
                            _req_float(self.state_time_s, "state_time_s"))

        entries = list(self.drivers) if self.drivers is not None else []
        if not entries:
            raise InvalidRaceStateError(
                "RaceState requires at least the anchor driver entry")
        for entry in entries:
            if not isinstance(entry, DriverRaceState):
                raise InvalidRaceStateError(
                    "RaceState.drivers must contain only DriverRaceState, "
                    f"got {entry!r}")
        ids = [entry.driver_id for entry in entries]
        duplicates = sorted({i for i in ids if ids.count(i) > 1})
        if duplicates:
            raise InvalidRaceStateError(
                f"duplicate driver entries: {duplicates}")
        entries = sorted(entries, key=lambda entry: entry.driver_id)
        object.__setattr__(self, "drivers", tuple(entries))

        if not isinstance(self.race_context, RaceContext):
            raise InvalidRaceStateError(
                "race_context must be a RaceContext, "
                f"got {self.race_context!r}")
        if not isinstance(self.weather, WeatherState):
            raise InvalidRaceStateError(
                f"weather must be a WeatherState, got {self.weather!r}")
        if not isinstance(self.race_control, RaceControlState):
            raise InvalidRaceStateError(
                "race_control must be a RaceControlState, "
                f"got {self.race_control!r}")

        by_id = {entry.driver_id: entry for entry in entries}
        anchor = by_id.get(self.anchor_driver_id)
        if anchor is None:
            raise InvalidRaceStateError(
                f"anchor driver {self.anchor_driver_id!r} is not a member "
                f"of this snapshot's roster")
        if not anchor.observable:
            raise InvalidRaceStateError(
                f"anchor driver {self.anchor_driver_id!r} must be "
                f"observable (the anchor is an exact D9 row)")
        if anchor.observed_lap_number != self.anchor_lap_number:
            raise InvalidRaceStateError(
                "anchor observed_lap_number "
                f"({anchor.observed_lap_number!r}) must equal "
                f"anchor_lap_number ({self.anchor_lap_number!r})")
        if anchor.observed_time_s != self.state_time_s:
            raise InvalidRaceStateError(
                "anchor observed_time_s "
                f"({anchor.observed_time_s!r}) must equal snapshot "
                f"state_time_s ({self.state_time_s!r})")

        for entry in entries:
            if not entry.observable:
                continue
            if entry.observed_time_s > self.state_time_s:
                raise InvalidRaceStateError(
                    f"driver {entry.driver_id!r} observed after snapshot "
                    f"T: {entry.observed_time_s!r} > {self.state_time_s!r}")
            if entry.observation_age_s is not None:
                expected = self.state_time_s - entry.observed_time_s
                if abs(entry.observation_age_s - expected) \
                        > AGE_CONSISTENCY_TOL_S:
                    raise InvalidRaceStateError(
                        f"driver {entry.driver_id!r} observation_age_s "
                        f"({entry.observation_age_s!r}) inconsistent with "
                        f"T - observed ({expected!r})")

    @property
    def roster_driver_ids(self) -> tuple:
        """Every roster member, driver_id order (observable or not)."""
        return tuple(entry.driver_id for entry in self.drivers)

    @property
    def roster_size(self) -> int:
        return len(self.drivers)

    @property
    def observable_drivers(self) -> tuple:
        """Entries with state at or before T, driver_id order."""
        return tuple(entry for entry in self.drivers if entry.observable)

    @property
    def observable_driver_ids(self) -> tuple:
        return tuple(entry.driver_id for entry in self.observable_drivers)

    @property
    def unobservable_driver_ids(self) -> tuple:
        """Roster members with no state ``<= T`` (stale tail + zero-state
        entrants); R4 maps these to null predictions + reason."""
        return tuple(entry.driver_id for entry in self.drivers
                     if not entry.observable)

    def to_dict(self) -> dict:
        """Deterministic plain-Python snapshot (JSON-compatible).

        Driver entries in ``driver_id`` order; unavailable values are
        explicit None; construction-time finite validation guarantees no
        NaN/Infinity and no pandas/numpy scalars.
        """
        return {
            "race_id": self.race_id,
            "anchor_driver_id": self.anchor_driver_id,
            "anchor_lap_number": self.anchor_lap_number,
            "state_time_s": self.state_time_s,
            "roster_size": self.roster_size,
            "roster_driver_ids": list(self.roster_driver_ids),
            "observable_driver_ids": list(self.observable_driver_ids),
            "unobservable_driver_ids": list(self.unobservable_driver_ids),
            "drivers": [entry.to_dict() for entry in self.drivers],
            "race_context": self.race_context.to_dict(),
            "weather": self.weather.to_dict(),
            "race_control": self.race_control.to_dict(),
        }


def domain_field_names() -> frozenset:
    """Every dataclass field name in this module (firewall allow-list)."""
    names: set[str] = set()
    for cls in (AnchorObservation, DriverRaceState, RaceContext,
                WeatherState, RaceControlState, RaceState):
        names.update(f.name for f in fields(cls))
    return frozenset(names)
