"""V3.1A Race Dynamics scientific contract (declarative, frozen).

V3.1B consumes this exact specification; nothing here computes a feature
value, loads data, trains a model, or touches the frozen ALL_84 registry.
Only the standard library is imported (no I/O at import time, no model_lab,
API, replay, spatial, dataset, or calculator imports).

Contract version: ``v3.1a-v2`` (V3.1A-C1 behind-relationship correction;
supersedes ``v3.1a-v1``). Semantic changes require a version bump;
``contract_hash()`` covers every semantic field below.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field, replace

#: Frozen contract version. Bump only for a deliberate semantic change.
#: v3.1a-v2: V3.1A-C1 behind-relationship correction (supersedes v3.1a-v1,
#: hash cc63a548eaf493383df03c4341cbd85678b9eb64303194652718b1bcf2632b77).
CONTRACT_VERSION = "v3.1a-v2"

#: Primary trajectory unit (Part F: LAP-BASED PRIMARY, cadence evidence:
#: exactly one lap-end state per driver-lap; median state delta ~90 s).
PRIMARY_UNIT = "lap"

#: Predeclared horizons in laps. H5 is the frozen bridge: V3.1 reuses the
#: existing ALL_84 5-lap features and computes new values only at 3/10
#: (plus windowed 5-lap statistics where no frozen counterpart exists).
HORIZONS = (3, 5, 10)

#: Valid dtype vocabulary for V3.1B (no implicit inference).
VALID_DTYPES = ("float64", "int64", "bool")

#: Deterministic seed for the V3.1C race-level bootstrap.
BOOTSTRAP_SEED = 42
#: Bootstrap replicates (matches the Phase-7 S6 B=2000 precedent).
BOOTSTRAP_REPLICATES = 2000
#: Confidence level for paired race-level delta intervals.
BOOTSTRAP_CI_LEVEL = 0.95


@dataclass(frozen=True)
class DynamicFeatureDef:
    """One admitted dynamic feature (declaration, not computation)."""

    name: str
    domain: str  # position | gap | pace | relative | field | traffic | pit
    statistic: str  # endpoint_delta | ols_slope | slope_diff | iqr | spread | fraction | count | flag | level | age
    horizon_laps: int | None  # None for horizon-free flags/levels
    unit: str
    dtype: str  # one of VALID_DTYPES
    nullable: bool
    temporal_rule: str  # driver_prefix | synchronized_field
    min_points: int  # minimum valid trajectory points (0 for flags/counts)
    missing_policy: str
    description: str
    sources: tuple = ()
    # Closest ALL_84 feature(s) + what is new (duplication contract).
    duplicates_of: tuple = ()
    incremental_information: str = ""
    variant: bool = False  # True -> VARIANT_A, not CORE


def _d(name, domain, statistic, horizon, unit, dtype, nullable, rule,
       min_points, missing, description, sources=(),
       duplicates_of=(), incremental="", variant=False):
    return DynamicFeatureDef(
        name=name, domain=domain, statistic=statistic,
        horizon_laps=horizon, unit=unit, dtype=dtype, nullable=nullable,
        temporal_rule=rule, min_points=min_points,
        missing_policy=missing, description=description,
        sources=tuple(sources), duplicates_of=tuple(duplicates_of),
        incremental_information=incremental, variant=variant)


#: 26 CORE definitions (frozen membership of V3_1_DYNAMICS_CORE).
CORE_DEFINITIONS: tuple = (
    _d("dyn_position_change_l3", "position", "endpoint_delta", 3,
       "positions", "float64", True, "driver_prefix", 0,
       "null_if_insufficient_history",
       "Position at latest own state with lap <= N-3 minus current "
       "position; positive = gained; never called overtakes.",
       ("driver_lap_state_d9.position",),
       ("recent_position_change_5laps",),
       "short-horizon position momentum; frozen covers 5 laps only."),
    _d("dyn_position_change_l10", "position", "endpoint_delta", 10,
       "positions", "float64", True, "driver_prefix", 0,
       "null_if_insufficient_history",
       "Position at latest own state with lap <= N-10 minus current "
       "position; positive = gained; never called overtakes.",
       ("driver_lap_state_d9.position",),
       ("recent_position_change_5laps",),
       "stint-scale position momentum; frozen covers 5 laps only."),
    _d("dyn_gap_leader_slope_l3", "gap", "ols_slope", 3,
       "seconds_per_lap", "float64", True, "synchronized_field", 2,
       "null_if_invalid_geometry",
       "OLS slope over trailing same-leader valid-seconds points within "
       "3 target laps (>= 2); negative = closing; runs stop at invalid "
       "or different-reference entries.",
       ("driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state"),
       ("recent_gap_to_leader_change_s_per_lap",),
       "short-horizon gap trajectory; frozen covers 5 laps only."),
    _d("dyn_gap_leader_slope_l10", "gap", "ols_slope", 10,
       "seconds_per_lap", "float64", True, "synchronized_field", 2,
       "null_if_invalid_geometry",
       "OLS slope over trailing same-leader valid-seconds points within "
       "10 target laps (>= 2); negative = closing.",
       ("driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state"),
       ("recent_gap_to_leader_change_s_per_lap",),
       "stint-scale gap trajectory; frozen covers 5 laps only."),
    _d("dyn_gap_leader_slope_diff_l3_l10", "gap", "slope_diff", 10,
       "seconds_per_lap", "float64", True, "synchronized_field", 2,
       "null_if_invalid_geometry",
       "Short slope (l3) minus long slope (l10); positive = reclaiming "
       "time faster recently than over the stint scale. Honest "
       "trajectory-shape proxy, never called curvature.",
       ("driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state"),
       ("recent_gap_to_leader_change_s_per_lap",),
       "trajectory shape across horizons; no single-horizon slope holds it."),
    _d("dyn_gap_leader_vol_l5", "gap", "iqr", 5,
       "seconds", "float64", True, "synchronized_field", 3,
       "null_if_invalid_geometry",
       "IQR of trailing same-leader valid-seconds points within 5 target "
       "laps (>= 3); robust gap instability, no winsorization.",
       ("driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state"),
       ("recent_gap_to_leader_change_s_per_lap",
        "gap_to_leader_seconds"),
       "volatility is orthogonal to slope and level."),
    _d("dyn_gap_ahead_slope_l3", "gap", "ols_slope", 3,
       "seconds_per_lap", "float64", True, "synchronized_field", 2,
       "null_if_invalid_geometry",
       "OLS slope over trailing same-ahead valid-seconds points within "
       "3 target laps (>= 2); negative = closing.",
       ("driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state"),
       ("recent_gap_to_ahead_change_s_per_lap",),
       "short-horizon battle trajectory; frozen covers 5 laps only."),
    _d("dyn_gap_ahead_slope_l10", "gap", "ols_slope", 10,
       "seconds_per_lap", "float64", True, "synchronized_field", 2,
       "null_if_invalid_geometry",
       "OLS slope over trailing same-ahead valid-seconds points within "
       "10 target laps (>= 2); negative = closing.",
       ("driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state"),
       ("recent_gap_to_ahead_change_s_per_lap",),
       "stint-scale battle trajectory; frozen covers 5 laps only."),
    _d("dyn_follower_gap_last_seconds", "gap", "level", None,
       "seconds", "float64", True, "synchronized_field", 0,
       "null_if_no_valid_follower_observation",
       "Latest causally observed follower crossing interval F - T_at_F "
       "(>= 0, target led at F). F = unique successor's latest observation "
       "time <= T; T_at_F = target's latest observation time <= F. Valid "
       "only when target is the follower's unique predecessor at F, both "
       "share the observed lap, neither side is red, and both timings are "
       "available. Stale by dyn_follower_gap_last_age_s by construction.",
       ("driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state"),
       (),
       "no behind-gap representation exists in ALL_84; v1 same-lap-at-T "
       "seconds removed as causally unobservable (V3.1A-C1)."),
    _d("dyn_follower_gap_last_age_s", "gap", "age", None,
       "seconds", "float64", True, "synchronized_field", 0,
       "null_if_no_valid_follower_observation",
       "Staleness of the last follower gap: T - F. Finite exactly when "
       "dyn_follower_gap_last_seconds is finite. Provenance, never the gap "
       "(F6 age convention). Median ~ one lap time; large values mark "
       "lapped/red-interrupted follower histories.",
       ("driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state"),
       (),
       "honest staleness companion; no age-like provenance exists in "
       "ALL_84 for the follower side."),
    _d("dyn_follower_lap_diff", "gap", "endpoint_delta", None,
       "laps", "int64", True, "synchronized_field", 0,
       "null_if_no_sync_state",
       "Target lap minus follower observed lap (1 typical = follower one "
       "observation behind; 0 equal; >= 2 lapped; null when successor "
       "unknown). Lap-regime geometry companion to the last-gap level.",
       ("driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state"),
       (),
       "laps-apart geometry for the follower side (renamed v1 behind "
       "laps; definition unchanged)."),
    _d("dyn_follower_gap_slope_l5", "gap", "ols_slope", 5,
       "seconds_per_lap", "float64", True, "synchronized_field", 2,
       "null_if_no_valid_follower_observation",
       "OLS slope over trailing same-follower same-lap-regime last-gap "
       "points within 5 target laps (>= 2, span >= 1 lap); negative = "
       "follower closing (same sign convention as ahead slopes). Runs stop "
       "at follower-identity change, lap-regime change, or masked target "
       "lap. Replaces the unobservable v1 same-lap behind slope.",
       ("driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state"),
       (),
       "follower-threat trajectory; entirely absent from ALL_84."),
    _d("dyn_pace_slope_l3", "pace", "endpoint_delta", 3,
       "seconds_per_lap", "float64", True, "driver_prefix", 0,
       "null_if_insufficient_history",
       "(pace_median_3 now - pace_median_3 at anchor)/lap_delta, anchor "
       "= latest own state with lap <= N-3; negative = faster.",
       ("driver_lap_state_d9.lap_time_s",
        "driver_lap_state_d9.pit_in_s",
        "driver_lap_state_d9.pit_out_s",
        "driver_lap_state_d9.track_state",
        "driver_lap_state_d9.lap_number"),
       ("recent_pace_change_s_per_lap",),
       "short-horizon pace momentum; frozen anchor is 5 laps only."),
    _d("dyn_pace_slope_l10", "pace", "endpoint_delta", 10,
       "seconds_per_lap", "float64", True, "driver_prefix", 0,
       "null_if_insufficient_history",
       "(pace_median_5 now - pace_median_5 at anchor)/lap_delta, anchor "
       "= latest own state with lap <= N-10; negative = faster.",
       ("driver_lap_state_d9.lap_time_s",
        "driver_lap_state_d9.pit_in_s",
        "driver_lap_state_d9.pit_out_s",
        "driver_lap_state_d9.track_state",
        "driver_lap_state_d9.lap_number"),
       ("recent_pace_change_s_per_lap",),
       "stint-scale pace momentum; frozen anchor is 5 laps only."),
    _d("dyn_pace_vol_l5", "pace", "iqr", 5,
       "seconds", "float64", True, "driver_prefix", 3,
       "null_if_insufficient_history",
       "IQR of trailing pace-eligible lap times within 5 target laps "
       "(>= 3 eligible); robust pace instability, no winsorization.",
       ("driver_lap_state_d9.lap_time_s",
        "driver_lap_state_d9.pit_in_s",
        "driver_lap_state_d9.pit_out_s",
        "driver_lap_state_d9.track_state",
        "driver_lap_state_d9.lap_number"),
       ("pace_median_5", "pace_mean_5"),
       "spread is orthogonal to every central-tendency summary."),
    _d("dyn_relpace_field_change_l5", "relative", "endpoint_delta", 5,
       "seconds_per_lap", "float64", True, "synchronized_field", 0,
       "null_if_no_sync_state",
       "Current field-relative pace minus the same quantity recomputed "
       "at the anchor state (lap <= N-5) with that anchor's own "
       "comparable set; negative = improving vs field.",
       ("driver_lap_state_d9.lap_time_s",
        "driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state",
        "driver_lap_state_d9.constructor_id"),
       ("relative_pace_to_field_median_s_per_lap",),
       "trajectory of relative pace; frozen holds the level only."),
    _d("dyn_relpace_ahead_change_l5", "relative", "endpoint_delta", 5,
       "seconds_per_lap", "float64", True, "synchronized_field", 0,
       "null_if_no_sync_state",
       "Current ahead-relative pace minus the same quantity recomputed "
       "at the anchor state against whoever was ahead then; negative = "
       "improving vs the battle.",
       ("driver_lap_state_d9.lap_time_s",
        "driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state",
        "driver_lap_state_d9.constructor_id"),
       ("relative_pace_to_car_ahead_s_per_lap",),
       "battle-relative trajectory; frozen holds the level only."),
    _d("dyn_field_spread_lap", "field", "spread", None,
       "seconds", "float64", True, "synchronized_field", 5,
       "null_if_no_sync_state",
       "P90 minus P10 of synchronized valid-seconds leader gaps across "
       "drivers valid at T (>= 5 contributors); race-level compression "
       "broadcast to rows; null under red.",
       ("driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state"),
       ("observable_field_size",),
       "compression level; frozen holds counts, never dispersion."),
    _d("dyn_field_spread_change_l5", "field", "endpoint_delta", 5,
       "seconds_per_lap", "float64", True, "synchronized_field", 5,
       "null_if_no_sync_state",
       "Current field spread minus spread recomputed at the anchor "
       "state (lap <= N-5) from that anchor's own valid population; "
       "negative = field compressing.",
       ("driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state"),
       ("observable_field_size",),
       "compression dynamics; entirely absent from ALL_84."),
    _d("dyn_traffic_frac_l5", "traffic", "fraction", 5,
       "fraction", "float64", True, "synchronized_field", 0,
       "null_if_no_sync_state",
       "Fraction of the last 5 own laps with factual in_traffic_2s true; "
       "null when no lap in window has valid traffic geometry.",
       ("driver_lap_state_d9.lap_time_s",
        "driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state",
        "driver_lap_state_d9.constructor_id"),
       ("in_traffic_2s",),
       "persistence of traffic exposure; frozen holds the instant only."),
    _d("dyn_traffic_n_l5", "traffic", "count", 5,
       "count", "int64", False, "synchronized_field", 0,
       "null_if_not_applicable",
       "Laps in the last 5 with valid traffic geometry (0 allowed, "
       "always defined); depth companion to dyn_traffic_frac_l5.",
       ("driver_lap_state_d9.lap_time_s",
        "driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state",
        "driver_lap_state_d9.constructor_id"),
       ("in_traffic_2s",),
       "explicit coverage so frac nulls stay interpretable."),
    _d("dyn_pit_inout_flag", "pit", "flag", None,
       "boolean", "bool", True, "driver_prefix", 0,
       "preserve_source_null",
       "True iff the current state is a pit in-lap (pit_in_s non-null) "
       "or out-lap (pit_out_s non-null); factual past-only observables.",
       ("driver_lap_state_d9.pit_in_s",
        "driver_lap_state_d9.pit_out_s"),
       ("pit_stops_completed_so_far",
        "laps_since_last_pit_stop"),
       "transition marker; frozen holds counts, never the transition."),
    _d("dyn_recent_stop_l3", "pit", "flag", 3,
       "boolean", "bool", True, "driver_prefix", 0,
       "null_if_insufficient_history",
       "True iff a fully-observed pit stop completed within the last 3 "
       "laps (laps_since_last_pit_stop <= 2 and non-null).",
       ("driver_lap_state_d9.laps_since_last_pit_stop",),
       ("pit_stops_completed_so_far",
        "laps_since_last_pit_stop"),
       "recency of the stop; frozen counts never expire."),
    _d("dyn_hist_laps_available", "position", "count", 10,
       "count", "int64", False, "driver_prefix", 0,
       "null_if_not_applicable",
       "Own lap-end states with lap in [N-10, N) (0 allowed, always "
       "defined); universal history-depth companion so null dynamics "
       "stay interpretable downstream.",
       ("driver_lap_state_d9.lap_number",),
       ("pace_n_3", "pace_n_5", "pace_n_10"),
       "one window-scoped depth for all families; frozen depths are "
       "pace-window-scoped only."),
    _d("dyn_gap_n_l10_leader", "gap", "count", 10,
       "count", "int64", False, "synchronized_field", 0,
       "null_if_not_applicable",
       "Same-leader valid-seconds points within 10 target laps (0 "
       "allowed); depth companion to leader slopes.",
       ("driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state"),
       ("recent_gap_to_leader_change_s_per_lap",),
       "explicit valid-point depth for the multi-horizon slopes."),
    _d("dyn_gap_n_l10_ahead", "gap", "count", 10,
       "count", "int64", False, "synchronized_field", 0,
       "null_if_not_applicable",
       "Same-ahead valid-seconds points within 10 target laps (0 "
       "allowed); depth companion to ahead slopes.",
       ("driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state"),
       ("recent_gap_to_ahead_change_s_per_lap",),
       "explicit valid-point depth for the multi-horizon slopes."),
)

#: 3 PROVISIONAL definitions (V3_1_DYNAMICS_VARIANT_A only).
VARIANT_DEFINITIONS: tuple = (
    _d("dyn_stint_pace_resid", "pace", "endpoint_delta", None,
       "seconds", "float64", True, "driver_prefix", 0,
       "null_if_insufficient_history",
       "pace_median_5 now minus the median of eligible laps at the same "
       "stint ages in prior stints of this race; DESCRIPTIVE stint pace "
       "trajectory, never called degradation.",
       ("driver_lap_state_d9.lap_time_s",
        "driver_lap_state_d9.pit_in_s",
        "driver_lap_state_d9.pit_out_s",
        "driver_lap_state_d9.track_state",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.stint_number"),
       ("current_stint_pace_trend_s_per_lap",),
       "age-conditioned view; frozen trend proxy is confounded.",
       variant=True),
    _d("dyn_gap_leader_slope_gated_clean", "gap", "ols_slope", 5,
       "seconds_per_lap", "float64", True, "synchronized_field", 2,
       "null_if_not_applicable",
       "Frozen 5-lap leader-slope construction gated on a clean window "
       "(no pit transition, no neutralized lap in window); null outside "
       "clean windows. F11-style interaction form.",
       ("driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state"),
       ("recent_gap_to_leader_change_s_per_lap",),
       "interaction form of the masking policy; tests T1 vs T2.",
       variant=True),
    _d("dyn_gap_accel_l5", "gap", "slope_diff", 5,
       "seconds_per_lap_squared", "float64", True, "synchronized_field",
       3,
       "null_if_invalid_geometry",
       "Difference of successive same-leader slope segments within 5 "
       "target laps (>= 3 valid points); second-order shape, reported "
       "with shrinkage review in V3.1C.",
       ("driver_lap_state_d9.state_time_s",
        "driver_lap_state_d9.lap_number",
        "driver_lap_state_d9.position",
        "driver_lap_state_d9.track_state"),
       ("recent_gap_to_leader_change_s_per_lap",),
       "second-order shape; kept provisional for noise risk.",
       variant=True),
)

#: All admitted definitions (CORE + VARIANT_A).
ALL_DEFINITIONS: tuple = CORE_DEFINITIONS + VARIANT_DEFINITIONS

#: Frozen named feature sets (membership only; ALL_84 untouched).
FEATURE_SETS: dict = {
    "V3_1_DYNAMICS_CORE": tuple(d.name for d in CORE_DEFINITIONS),
    "V3_1_DYNAMICS_VARIANT_A": tuple(d.name for d in VARIANT_DEFINITIONS),
    "V3_1_DYNAMICS": tuple(d.name for d in ALL_DEFINITIONS),
}

#: Window / policy constants (frozen).
WINDOW_CONTRACT: dict = {
    "primary_unit": PRIMARY_UNIT,
    "horizons_laps": list(HORIZONS),
    "frozen_bridge_horizon": 5,
    "invariant": "source_time <= T for every source observation",
    "window_rule": "current_lap - H <= source_lap <= current_lap, "
                   "one value per driver lap-end state (latest "
                   "state_time_s row per (driver, lap))",
    "current_observation_included": True,
    "red_flag": "segment: red laps excluded and break runs",
    "neutralized_laps": "mask: non-all_clear laps excluded from "
                        "trajectory inputs and break runs",
    "pit_laps": "mask: in-lap/out-lap excluded from trajectory inputs; "
                "marked by dyn_pit_inout_flag / dyn_recent_stop_l3",
    "zero_fill": "forbidden: insufficient history yields null, never 0",
    "behind_identity": "unique successor at each historical state; "
                       "last-gap runs additionally stop at lap-regime "
                       "change (target lap minus follower observed lap); "
                       "strict predecessor check (target is the "
                       "follower's unique predecessor at F) required for "
                       "every last-gap level",
    "relative_comparator": "whoever held the relationship at that "
                           "historical state; retroactive T-competitor "
                           "comparison forbidden",
    "field_population": "drivers with valid leader-gap at that state, "
                        "min 5 contributors",
}


def _definition_dict(d: DynamicFeatureDef) -> dict:
    return {
        "name": d.name,
        "domain": d.domain,
        "statistic": d.statistic,
        "horizon_laps": d.horizon_laps,
        "unit": d.unit,
        "dtype": d.dtype,
        "nullable": d.nullable,
        "temporal_rule": d.temporal_rule,
        "min_points": d.min_points,
        "missing_policy": d.missing_policy,
        "description": d.description,
        "sources": list(d.sources),
        "duplicates_of": list(d.duplicates_of),
        "incremental_information": d.incremental_information,
        "variant": d.variant,
    }


def canonical_payload() -> dict:
    """Semantic contract content for hashing (no paths/timestamps)."""
    return {
        "contract_version": CONTRACT_VERSION,
        "primary_unit": PRIMARY_UNIT,
        "horizons_laps": list(HORIZONS),
        "bootstrap": {
            "seed": BOOTSTRAP_SEED,
            "replicates": BOOTSTRAP_REPLICATES,
            "ci_level": BOOTSTRAP_CI_LEVEL,
        },
        "definitions": [_definition_dict(d) for d in ALL_DEFINITIONS],
        "feature_sets": {k: list(v) for k, v in FEATURE_SETS.items()},
        "window_contract": dict(WINDOW_CONTRACT),
    }


def canonical_text() -> str:
    """Byte-deterministic serialization of the semantic contract."""
    return json.dumps(canonical_payload(), indent=2, sort_keys=True) + "\n"


def contract_hash() -> str:
    """sha256 over the canonical semantic payload."""
    blob = json.dumps(canonical_payload(), sort_keys=True,
                      separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def get_definition(name: str) -> DynamicFeatureDef:
    """Fetch one definition by exact name; unknown names fail loudly."""
    for d in ALL_DEFINITIONS:
        if d.name == name:
            return d
    raise KeyError(f"unknown V3.1 dynamic feature {name!r}")


def feature_set_names(kind: str = "all") -> tuple:
    """Deterministic feature-name tuple for a set or 'all'."""
    if kind == "all":
        return tuple(d.name for d in ALL_DEFINITIONS)
    if kind == "core":
        return FEATURE_SETS["V3_1_DYNAMICS_CORE"]
    if kind == "variant_a":
        return FEATURE_SETS["V3_1_DYNAMICS_VARIANT_A"]
    raise KeyError(f"unknown dynamics set kind {kind!r}")
