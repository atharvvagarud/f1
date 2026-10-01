"""F2 feature registry (Phase 2 Temporal Feature Engine).

Authoritative, deterministic, stdlib-only metadata layer. The registry
is metadata + validation: no feature store, no database, no service.
F2 registers frozen Phase-1 passthroughs (+ the planned grid contract);
substantive families belong to later stages.
"""

from __future__ import annotations

import hashlib
import json

from raceintel import contracts as C
from raceintel.pipeline import d6schema as D6
from raceintel.pipeline import d7schema as D7
from raceintel.pipeline import d9schema as D9
from raceintel.features.contracts import (
    CROSS_DRIVER_FAMILIES,
    FEATURE_DTYPES,
    UNITLESS,
    FeatureDef,
    FeatureFamily,
    FeatureStatus,
    InvalidFeatureError,
    MinHistory,
    MinHistoryKind,
    MissingPolicy,
    SyncRequirement,
    TemporalRule,
)

#: Feature matrix/schema version for outputs. F2 froze "v1" (23
#: passthroughs + planned grid); F5 added 12 pace/stint columns ("v2");
#: F6 added 8 gap columns ("v3"); F7 added 12 context columns ("v4");
#: F8 added 4 rate/momentum columns ("v5"); F9 adds 9 environment
#: columns ("v6"); F10 adds 12 prior/grid columns ("v7", grid superseded
#: to v2); F11 adds 3 interactions ("v8"). Exactly one bump per stage
#: per the F2 version policy.
FEATURE_SET_VERSION = "v8"

#: Registry code version (bump only for registry-schema changes here).
REGISTRY_VERSION = 1


def label_outcome_fields() -> frozenset:
    """Outcome fields that must never become predictive feature inputs.

    Derived from Phase-1 availability metadata (D9 label layer + D5
    results LABEL_ONLY columns), not a hand-written blacklist alone.
    F13 additionally guards the canonical target names (exact names
    only -- never substring matching, per the 'pressure' lesson).
    Only the NAME set is shared; label values never enter here.
    """
    from raceintel.labels.contracts import CANONICAL_LABEL_NAMES
    names = {f.name for f in D9.LABEL_FIELDS}
    names |= set(C.RESULTS.label_columns())
    names |= {"dnf_flag", "dnf"}  # belt-and-braces: no DNF target exists
    names |= set(CANONICAL_LABEL_NAMES)
    return frozenset(names)


def validate_definition(defn: FeatureDef) -> None:
    """Validate one definition. Raises InvalidFeatureError; never repairs."""
    if not defn.name or not defn.name.strip():
        raise InvalidFeatureError("feature name must be non-empty")
    if not isinstance(defn.family, FeatureFamily):
        raise InvalidFeatureError(
            f"{defn.name}: family must be a FeatureFamily")
    if not isinstance(defn.version, int) or defn.version < 1:
        raise InvalidFeatureError(
            f"{defn.name}: version must be an integer >= 1")
    if defn.dtype not in FEATURE_DTYPES:
        raise InvalidFeatureError(
            f"{defn.name}: unsupported dtype {defn.dtype!r}")
    if not defn.unit or not defn.unit.strip():
        raise InvalidFeatureError(
            f"{defn.name}: unit policy requires an explicit unit "
            f"(use {UNITLESS!r} for unitless quantities)")
    if not defn.description or not defn.description.strip():
        raise InvalidFeatureError(
            f"{defn.name}: description must be non-empty")
    if not defn.sources:
        raise InvalidFeatureError(
            f"{defn.name}: empty source lineage is forbidden; list exact "
            f"'entity.field' sources")
    for src in defn.sources:
        if not isinstance(src, str) or "." not in src:
            raise InvalidFeatureError(
                f"{defn.name}: source {src!r} must be 'entity.field'")
        entity, _, col = src.partition(".")
        if not entity.strip() or not col.strip():
            raise InvalidFeatureError(
                f"{defn.name}: source {src!r} must be 'entity.field'")
        for vague in ("fastf1", "race data", "historical"):
            if src.strip().lower() == vague:
                raise InvalidFeatureError(
                    f"{defn.name}: vague lineage {src!r} is insufficient")
    if not isinstance(defn.temporal_rule, TemporalRule):
        raise InvalidFeatureError(
            f"{defn.name}: missing/invalid temporal rule")
    if not isinstance(defn.sync, SyncRequirement):
        raise InvalidFeatureError(
            f"{defn.name}: missing/invalid sync requirement")
    if not isinstance(defn.min_history, MinHistory):
        raise InvalidFeatureError(
            f"{defn.name}: missing/invalid minimum-history declaration")
    defn.min_history.validate()
    if not isinstance(defn.missing, MissingPolicy):
        raise InvalidFeatureError(
            f"{defn.name}: missing/invalid missingness policy")
    if (defn.missing is MissingPolicy.DETERMINISTIC_FALLBACK
            and not defn.fallback_description.strip()):
        raise InvalidFeatureError(
            f"{defn.name}: DETERMINISTIC_FALLBACK requires a justified "
            f"fallback_description")
    if not isinstance(defn.status, FeatureStatus):
        raise InvalidFeatureError(
            f"{defn.name}: missing/invalid status")
    # Temporal safety: predictive features can never be POST_RACE/LABEL_ONLY.
    if defn.predictive_eligible and defn.availability in (
            C.Availability.POST_RACE, C.Availability.LABEL_ONLY):
        raise InvalidFeatureError(
            f"{defn.name}: predictive feature marked "
            f"{defn.availability.value} is forbidden")
    # Label guard: outcome NAMES can never become feature columns
    # (a model column named winner_flag is a footgun by construction).
    outcomes = label_outcome_fields()
    if defn.predictive_eligible and defn.name in outcomes:
        raise InvalidFeatureError(
            f"{defn.name}: label/outcome field cannot be a predictive feature")
    # Source lineage guard: historical outcome columns are legitimate
    # ONLY under the PAST_RACES temporal rule, where the H < R cutoff
    # (history_before firewall) is the leakage protection. LAP_END /
    # single-state features may never source outcomes.
    if not (defn.temporal_rule is TemporalRule.PAST_RACES):
        for src in defn.sources:
            _, _, col = src.partition(".")
            if defn.predictive_eligible and col in outcomes:
                raise InvalidFeatureError(
                    f"{defn.name}: source {src!r} references label/outcome "
                    f"field")
    # Cross-driver declaration: predictive features in cross-driver
    # families must require F1 synchronization (same-lap is
    # inexpressible: no such SyncRequirement exists, by F1 design).
    if (defn.predictive_eligible and defn.family in CROSS_DRIVER_FAMILIES
            and defn.sync is SyncRequirement.NONE):
        raise InvalidFeatureError(
            f"{defn.name}: predictive {defn.family.value} feature without "
            f"synchronization declaration is forbidden")
    # Status/predictive consistency.
    if defn.status is FeatureStatus.DEFERRED and defn.predictive_eligible:
        raise InvalidFeatureError(
            f"{defn.name}: DEFERRED concept must not be predictive_eligible")
    if defn.status is FeatureStatus.PASSTHROUGH and not defn.predictive_eligible:
        raise InvalidFeatureError(
            f"{defn.name}: PASSTHROUGH registers predictive reuse; "
            f"non-predictive metadata does not belong here")


class FeatureRegistry:
    """Deterministic registry: sorted enumeration, explicit registration."""

    def __init__(self) -> None:
        self._defs: dict[str, FeatureDef] = {}

    def register(self, defn: FeatureDef) -> FeatureDef:
        validate_definition(defn)
        if defn.name in self._defs:
            raise InvalidFeatureError(
                f"duplicate feature name: {defn.name}")
        self._defs[defn.name] = defn
        return defn

    def get(self, name: str) -> FeatureDef:
        return self._defs[name]

    def supersede(self, defn: FeatureDef) -> FeatureDef:
        """Replace an existing definition with a new version of itself.

        Lifecycle operation for stage transitions (e.g. PLANNED grid
        implemented in F10): validates, requires the same name with a
        strictly higher version, and preserves deterministic ordering.
        """
        validate_definition(defn)
        if defn.name not in self._defs:
            raise InvalidFeatureError(
                f"cannot supersede unregistered feature: {defn.name}")
        if defn.version <= self._defs[defn.name].version:
            raise InvalidFeatureError(
                f"supersede requires a higher version for {defn.name}")
        self._defs[defn.name] = defn
        return defn

    def __len__(self) -> int:
        return len(self._defs)

    def __iter__(self):
        for name in sorted(self._defs):
            yield self._defs[name]

    def names(self) -> list:
        return sorted(self._defs)

    def to_dict(self) -> dict:
        return {
            "registry_version": REGISTRY_VERSION,
            "feature_set_version": FEATURE_SET_VERSION,
            "feature_count": len(self._defs),
            "features": [self._defs[n].to_dict() for n in sorted(self._defs)],
        }

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True,
                          separators=(",", ":"))

    def fingerprint(self) -> str:
        return hashlib.sha256(self.to_json().encode("utf-8")).hexdigest()


# ---------------------------------------------------------------------------
# F2 passthrough inventory (frozen Phase-1 reuse, no recomputation)
# ---------------------------------------------------------------------------

def _phase1_field(name: str):
    """Look up frozen field metadata across D6/D7/D9 schemas."""
    for table in (D6.STATE_FIELDS, D7.EXTENSION_FIELDS,
                  D9.STATE_EXTENSION_FIELDS):
        for f in table:
            if f.name == name:
                return f
    raise KeyError(f"unknown Phase-1 field: {name}")


#: Passthrough feature name -> (temporal rule, missing policy).
PASSTHROUGH_SPECS: tuple = (
    ("position", TemporalRule.TARGET_STATE,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("race_leader_laps_at_state", TemporalRule.TARGET_STATE,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("race_progress_frac", TemporalRule.TARGET_STATE,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("track_state", TemporalRule.TARGET_STATE,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("flag_yellow", TemporalRule.TARGET_STATE,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("flag_safety_car", TemporalRule.TARGET_STATE,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("flag_vsc", TemporalRule.TARGET_STATE,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("flag_red", TemporalRule.TARGET_STATE,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("pit_stops_completed_so_far", TemporalRule.TARGET_STATE,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("laps_since_last_pit_stop", TemporalRule.TARGET_STATE,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("stint_lap", TemporalRule.TARGET_STATE,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("compound", TemporalRule.TARGET_STATE,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("tyre_life", TemporalRule.TARGET_STATE,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("fresh_tyre", TemporalRule.TARGET_STATE,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("wx_air_temp_c", TemporalRule.BACKWARD_ASOF,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("wx_track_temp_c", TemporalRule.BACKWARD_ASOF,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("wx_humidity_pct", TemporalRule.BACKWARD_ASOF,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("wx_pressure_hpa", TemporalRule.BACKWARD_ASOF,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("wx_wind_speed", TemporalRule.BACKWARD_ASOF,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("wx_wind_direction_deg", TemporalRule.BACKWARD_ASOF,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("wx_rainfall", TemporalRule.BACKWARD_ASOF,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("stint_compound", TemporalRule.TARGET_STATE,
     MissingPolicy.PRESERVE_SOURCE_NULL),
    ("stint_fresh_tyre", TemporalRule.TARGET_STATE,
     MissingPolicy.PRESERVE_SOURCE_NULL),
)

_PASSTHROUGH_FAMILY = {
    "position": FeatureFamily.RACE_STATE,
    "race_leader_laps_at_state": FeatureFamily.RACE_STATE,
    "race_progress_frac": FeatureFamily.RACE_STATE,
    "track_state": FeatureFamily.RACE_CONTROL,
    "flag_yellow": FeatureFamily.RACE_CONTROL,
    "flag_safety_car": FeatureFamily.RACE_CONTROL,
    "flag_vsc": FeatureFamily.RACE_CONTROL,
    "flag_red": FeatureFamily.RACE_CONTROL,
    "pit_stops_completed_so_far": FeatureFamily.STINT,
    "laps_since_last_pit_stop": FeatureFamily.STINT,
    "stint_lap": FeatureFamily.STINT,
    "compound": FeatureFamily.TYRE,
    "tyre_life": FeatureFamily.TYRE,
    "fresh_tyre": FeatureFamily.TYRE,
    "wx_air_temp_c": FeatureFamily.WEATHER,
    "wx_track_temp_c": FeatureFamily.WEATHER,
    "wx_humidity_pct": FeatureFamily.WEATHER,
    "wx_pressure_hpa": FeatureFamily.WEATHER,
    "wx_wind_speed": FeatureFamily.WEATHER,
    "wx_wind_direction_deg": FeatureFamily.WEATHER,
    "wx_rainfall": FeatureFamily.WEATHER,
    "stint_compound": FeatureFamily.TYRE,
    "stint_fresh_tyre": FeatureFamily.TYRE,
}


def build_f2_registry() -> FeatureRegistry:
    """F2 registry: 23 Phase-1 passthroughs + planned grid contract.

    Passthrough metadata (dtype/unit/availability/eligibility) is read
    from the frozen schemas, so it cannot drift from Phase 1. Only
    predictive-eligible Phase-1 fields are registered; non-predictive
    provenance is never promoted.
    """
    registry = FeatureRegistry()
    for name, rule, missing in PASSTHROUGH_SPECS:
        src = _phase1_field(name)
        if not src.predictive_eligible:
            raise InvalidFeatureError(
                f"refusing to promote non-predictive field: {name}")
        registry.register(FeatureDef(
            name=name,
            family=_PASSTHROUGH_FAMILY[name],
            version=1,
            dtype=src.dtype,
            unit=src.unit,
            description=f"D9 passthrough (frozen): {src.description}",
            sources=(f"driver_lap_state_d9.{name}",),
            formula_ref="passthrough: value copied from frozen D9 state row; "
                        "no recomputation",
            temporal_rule=rule,
            sync=SyncRequirement.NONE,
            min_history=MinHistory(MinHistoryKind.NONE),
            missing=missing,
            availability=src.availability,
            predictive_eligible=True,
            status=FeatureStatus.PASSTHROUGH,
        ))
    # Planned grid contract (F10 owns the join; registered PLANNED now).
    registry.register(FeatureDef(
        name="grid_position",
        family=FeatureFamily.GRID,
        version=1,
        dtype="int64",
        unit="position",
        description="Factual starting grid from D5 results (PRE_RACE join "
                    "on (race_id, driver_id); 3,455/3,458 coverage, 3 known "
                    "W/DNS-style nulls). No qualifying fields.",
        sources=("results.grid_position",),
        formula_ref="planned: PRE_RACE identity join in F10; no outcome "
                    "columns from results may enter",
        temporal_rule=TemporalRule.PRE_RACE_CONSTANT,
        sync=SyncRequirement.NONE,
        min_history=MinHistory(MinHistoryKind.NONE),
        missing=MissingPolicy.NULL_IF_NOT_APPLICABLE,
        availability=C.Availability.PRE_RACE,
        predictive_eligible=True,
        status=FeatureStatus.PLANNED,
    ))
    return registry
