"""F16 ablation-group configuration + Model-Lab handoff fixtures.

Configuration metadata ONLY. This module defines the feature-family
groupings, cumulative / leave-one-group-out / simple-baseline
configurations, the deterministic fixtures Phase 3 uses to verify
loaders/splits/task masks/feature-set resolution, and a machine-readable
export. It does NOT train, evaluate, select, impute, encode, split, or
touch the canonical matrix.

The registry is the single authority for feature identity: every group
resolves its member names from `build_f11_registry()` metadata. There is
no hand-written copy of the 84-name master list. Groups that cut across a
registry family (factual stint state vs derived stint pace; current
environment vs environment history) are split by the registry's
`temporal_rule`, the same rule the feature docs use to separate factual
state from derived history.

Versions: `ABLATION_CONFIG_VERSION="v1"` is independent and never changes
`FEATURE_SET_VERSION` (v8), `LABEL_SET_VERSION` (v1) or `MATRIX_VERSION`
(v1). A future feature/label/matrix version fails compatibility here
loudly instead of silently absorbing new columns.
"""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, replace
from pathlib import Path

from raceintel.features.contracts import FeatureFamily, TemporalRule
from raceintel.features.interactions import REQUIRED_PRIMITIVES, build_f11_registry
from raceintel.features.registry import FEATURE_SET_VERSION, FeatureRegistry
from raceintel.labels.contracts import CANONICAL_LABEL_NAMES, LABEL_SET_VERSION

#: Ablation/grouping configuration version. Independent of the feature,
#: label and matrix versions; bump only for a deliberate grouping change.
ABLATION_CONFIG_VERSION = "v1"

#: Versions this configuration is compatible with. Kept as literals (not
#: imported from build_matrix) so this module imports without pulling the
#: matrix builder; a test pins equality with the real constants.
REQUIRED_FEATURE_SET_VERSION = "v8"
REQUIRED_LABEL_SET_VERSION = "v1"
REQUIRED_MATRIX_VERSION = "v1"
EXPECTED_PREDICTIVE_FEATURE_COUNT = 84

EXPORT_FILENAME = "ablation_config.json"


class AblationConfigError(RuntimeError):
    """Fatal F16 configuration/validation failure. Never repairs."""


# ---------------------------------------------------------------------------
# Feature-group contract
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FeatureGroup:
    """One primary semantic group (metadata contract, not a framework)."""

    name: str
    description: str
    rationale: str
    source_families: tuple
    dependencies: tuple = ()
    version: int = 1
    status: str = "frozen"
    features: tuple = ()  # resolved predictive names, canonical order


#: Primary groups in the frozen ablation order. The order follows the
#: F4-F11 computation DAG (factual state, pace, gaps, field context,
#: rates, environment history, pre-race priors, interactions last).
PRIMARY_GROUP_ORDER = (
    "STATE",
    "PACE",
    "GAPS",
    "FIELD_CONTEXT",
    "RATES_MOMENTUM",
    "ENVIRONMENT_HISTORY",
    "PRE_RACE_PRIORS",
    "INTERACTIONS",
)

_PRIMARY_META = {
    "STATE": FeatureGroup(
        name="STATE",
        description=(
            "Factual current race state observable at the target LAP_END: "
            "position/progress, tyres, factual stint/pit state, current "
            "track/race-control flags and current as-of weather."),
        rationale=(
            "The minimal factual description of where the race is now; the "
            "first interpretable ablation rung and the source of the simple "
            "baselines."),
        source_families=("race_state", "tyre", "stint", "race_control",
                         "weather"),
    ),
    "PACE": FeatureGroup(
        name="PACE",
        description=(
            "Past-only pace of the target driver: trailing eligible-lap "
            "windows plus current-stint derived pace summaries and the "
            "in-stint pace-trend proxy."),
        rationale=(
            "Separates raw recent performance from factual stint state; "
            "derived stint pace belongs with pace, not with stint facts "
            "(task F16 section 5)."),
        source_families=("pace", "stint"),
    ),
    "GAPS": FeatureGroup(
        name="GAPS",
        description=(
            "Structured synchronized gap representation: seconds/lap "
            "difference to leader and car ahead, validity and observation "
            "age provenance."),
        rationale=(
            "Race separation is the primary cross-driver geometry and the "
            "input most later relative features build on."),
        source_families=("gap",),
    ),
    "FIELD_CONTEXT": FeatureGroup(
        name="FIELD_CONTEXT",
        description=(
            "Synchronized relative/teammate/field/traffic context: relative "
            "pace to ahead/field/teammate, teammate state, observable field "
            "counts and traffic flags."),
        rationale=(
            "Turns per-driver state into field-relative context without "
            "introducing rate or projection semantics."),
        source_families=("relative", "teammate", "field", "traffic"),
    ),
    "RATES_MOMENTUM": FeatureGroup(
        name="RATES_MOMENTUM",
        description=(
            "Backward-looking change over trailing laps: gap-to-leader / "
            "gap-to-ahead rates, position change and pace change."),
        rationale=(
            "Descriptive momentum only (no catch-time or projected values); "
            "the final pre-prior temporal rung."),
        source_families=("rate", "momentum"),
    ),
    "ENVIRONMENT_HISTORY": FeatureGroup(
        name="ENVIRONMENT_HISTORY",
        description=(
            "Derived environment history: weather deltas/rain recency and "
            "race-control duration/transition/fraction features."),
        rationale=(
            "Distinct from current factual environment state (in STATE); "
            "these describe how the environment got here, not where it is."),
        source_families=("weather", "race_control"),
    ),
    "PRE_RACE_PRIORS": FeatureGroup(
        name="PRE_RACE_PRIORS",
        description=(
            "Genuinely pre-race information: factual grid slot plus "
            "past-only driver/constructor/circuit historical priors."),
        rationale=(
            "Grid is a factual pre-race constant; historical priors are "
            "past-race aggregates. They enter together at F10 and are "
            "grouped together here, with GRID_ONLY / "
            "HISTORICAL_PRIORS_ONLY subgroups for diagnostics."),
        source_families=("grid", "driver_prior", "constructor_prior",
                         "circuit"),
    ),
    "INTERACTIONS": FeatureGroup(
        name="INTERACTIONS",
        description=(
            "The three explicit F11 interactions: positions_from_grid, "
            "traffic-gated relative pace and traffic-gated gap rate."),
        rationale=(
            "Consumes approved primitives only; added after its parent "
            "groups in cumulative experiments and removed with a parent in "
            "leave-one-group-out experiments."),
        source_families=("interaction",),
        dependencies=("STATE", "FIELD_CONTEXT", "RATES_MOMENTUM",
                      "PRE_RACE_PRIORS"),
    ),
}

#: Diagnostic subgroups inside PRE_RACE_PRIORS. They do not alter the
#: primary partition (a feature can appear in a group and a subgroup).
SEMANTIC_SUBGROUPS = {
    "GRID_ONLY": ("grid_position",),
    "HISTORICAL_PRIORS_ONLY": (
        "prior_constructor_mean_finish", "prior_constructor_points_per_entry",
        "prior_constructor_races", "prior_circuit_mean_pit_stops_per_entry",
        "prior_circuit_mean_position_change", "prior_circuit_races",
        "prior_driver_mean_finish", "prior_driver_mean_grid",
        "prior_driver_points_per_start", "prior_driver_starts",
        "recent_constructor_points_per_entry_5", "recent_driver_mean_finish_5",
    ),
}

#: Frozen interaction removal policy (documented, deterministic).
INTERACTION_DEPENDENCY_POLICY = (
    "Cumulative: INTERACTIONS is appended only in the final stage, after "
    "every parent primitive group is present. "
    "Leave-one-group-out: removing a primary group also removes every "
    "interaction whose required primitive is a member of that group; the "
    "removed interactions are recorded explicitly in the configuration."
)

_PRIOR_FAMILIES = frozenset({
    FeatureFamily.GRID,
    FeatureFamily.DRIVER_PRIOR,
    FeatureFamily.CONSTRUCTOR_PRIOR,
    FeatureFamily.CIRCUIT,
})
_FIELD_FAMILIES = frozenset({
    FeatureFamily.RELATIVE,
    FeatureFamily.TEAMMATE,
    FeatureFamily.FIELD,
    FeatureFamily.TRAFFIC,
})
_RATE_FAMILIES = frozenset({FeatureFamily.RATE, FeatureFamily.MOMENTUM})


def primary_group_name(defn) -> str:
    """Registry-derived primary group for one predictive definition.

    Deterministic partition. Family usually decides; the three families
    that mix factual current state with derived history (stint,
    race_control, weather) are split by the registry `temporal_rule`
    exactly as the family docs describe.
    """
    fam = defn.family
    rule = defn.temporal_rule
    if fam in _PRIOR_FAMILIES:
        return "PRE_RACE_PRIORS"
    if fam is FeatureFamily.INTERACTION:
        return "INTERACTIONS"
    if fam is FeatureFamily.GAP:
        return "GAPS"
    if fam in _FIELD_FAMILIES:
        return "FIELD_CONTEXT"
    if fam in _RATE_FAMILIES:
        return "RATES_MOMENTUM"
    if fam is FeatureFamily.PACE:
        return "PACE"
    if fam in (FeatureFamily.RACE_STATE, FeatureFamily.TYRE):
        return "STATE"
    if fam is FeatureFamily.STINT:
        return "STATE" if rule is TemporalRule.TARGET_STATE else "PACE"
    if fam is FeatureFamily.RACE_CONTROL:
        return "STATE" if rule is TemporalRule.TARGET_STATE \
            else "ENVIRONMENT_HISTORY"
    if fam is FeatureFamily.WEATHER:
        return "ENVIRONMENT_HISTORY" if rule is TemporalRule.DRIVER_PREFIX \
            else "STATE"
    raise AblationConfigError(
        f"no primary group for predictive family {fam.value!r} "
        f"(feature {defn.name!r})")


# ---------------------------------------------------------------------------
# Registry authority + drift guards
# ---------------------------------------------------------------------------

def validate_registry(registry: FeatureRegistry | None = None) -> None:
    """Fail loudly if the registry is not the frozen v8 / 84 predictive set."""
    reg = build_f11_registry() if registry is None else registry
    if FEATURE_SET_VERSION != REQUIRED_FEATURE_SET_VERSION:
        raise AblationConfigError(
            f"FEATURE_SET_VERSION {FEATURE_SET_VERSION!r} != required "
            f"{REQUIRED_FEATURE_SET_VERSION!r}; F16 {ABLATION_CONFIG_VERSION} "
            f"is incompatible until deliberately re-versioned")
    names = [d.name for d in reg if d.predictive_eligible]
    if len(names) != EXPECTED_PREDICTIVE_FEATURE_COUNT:
        raise AblationConfigError(
            f"predictive feature count {len(names)} != "
            f"{EXPECTED_PREDICTIVE_FEATURE_COUNT}")
    if len(set(names)) != len(names):
        raise AblationConfigError("duplicate predictive feature names")
    overlap = set(names) & set(CANONICAL_LABEL_NAMES)
    if overlap:
        raise AblationConfigError(
            f"label names present in predictive set: {sorted(overlap)}")
    if any(d.status.value == "deferred" for d in reg if d.predictive_eligible):
        raise AblationConfigError("a DEFERRED definition is marked predictive")


def canonical_predictive_names(registry: FeatureRegistry | None = None) -> tuple:
    """Registry-ordered (sorted-name) predictive list; no hand-written copy."""
    reg = build_f11_registry() if registry is None else registry
    validate_registry(reg)
    return tuple(d.name for d in reg if d.predictive_eligible)


def build_primary_groups(registry: FeatureRegistry | None = None) -> dict:
    """Name -> FeatureGroup with resolved features in canonical order."""
    reg = build_f11_registry() if registry is None else registry
    names = canonical_predictive_names(reg)
    members: dict = {g: [] for g in PRIMARY_GROUP_ORDER}
    for d in reg:
        if not d.predictive_eligible:
            continue
        g = primary_group_name(d)
        if g not in members:
            raise AblationConfigError(
                f"feature {d.name!r} resolved to unknown group {g!r}")
        members[g].append(d.name)
    out = {}
    for g in PRIMARY_GROUP_ORDER:
        # members already in registry (sorted) order; re-filter for safety
        ordered = tuple(n for n in names if n in set(members[g]))
        out[g] = replace(_PRIMARY_META[g], features=ordered)
    return out


def group_features(group_name: str,
                   registry: FeatureRegistry | None = None) -> tuple:
    """Resolved features of one primary group; unknown group fails."""
    groups = build_primary_groups(registry)
    if group_name not in groups:
        raise AblationConfigError(
            f"unknown primary group {group_name!r}; known: "
            f"{list(PRIMARY_GROUP_ORDER)}")
    return groups[group_name].features


def partition_audit(registry: FeatureRegistry | None = None) -> dict:
    """feature -> primary group, covering all 84 exactly once."""
    reg = build_f11_registry() if registry is None else registry
    names = canonical_predictive_names(reg)
    groups = build_primary_groups(reg)
    mapping: dict = {}
    for g in PRIMARY_GROUP_ORDER:
        for f in groups[g].features:
            if f in mapping:
                raise AblationConfigError(
                    f"feature {f!r} assigned to two groups "
                    f"({mapping[f]!r}, {g!r})")
            mapping[f] = g
    unassigned = [n for n in names if n not in mapping]
    if unassigned:
        raise AblationConfigError(f"unassigned features: {unassigned}")
    if len(mapping) != len(names):
        raise AblationConfigError("partition does not cover the predictive set")
    counts = {g: len(groups[g].features) for g in PRIMARY_GROUP_ORDER}
    return {"feature_to_group": mapping, "counts": counts,
            "total": len(mapping)}


def interaction_dependencies(registry: FeatureRegistry | None = None) -> dict:
    """Interaction -> required primitives + their primary groups.

    The dependency metadata comes from `interactions.REQUIRED_PRIMITIVES`
    (registry authority), never a second hand-written table.
    """
    groups = build_primary_groups(registry)
    feature_to_group = {}
    for g in PRIMARY_GROUP_ORDER:
        for f in groups[g].features:
            feature_to_group[f] = g
    out = {}
    for name, primitives in REQUIRED_PRIMITIVES.items():
        missing = [p for p in primitives if p not in feature_to_group]
        if missing:
            raise AblationConfigError(
                f"interaction {name!r} depends on unknown/unpartitioned "
                f"primitives {missing}")
        out[name] = {
            "required_primitives": tuple(primitives),
            "required_groups": tuple(sorted({feature_to_group[p]
                                             for p in primitives})),
        }
    return out


def validate_feature_names(names, registry: FeatureRegistry | None = None,
                           context: str = "configuration") -> None:
    """Reject duplicates, unknown features, labels, masks and metadata."""
    reg = build_f11_registry() if registry is None else registry
    predictive = set(canonical_predictive_names(reg))
    label_names = set(CANONICAL_LABEL_NAMES)
    seen = set()
    for n in names:
        if n in seen:
            raise AblationConfigError(f"duplicate feature {n!r} in {context}")
        seen.add(n)
        if n in label_names:
            raise AblationConfigError(
                f"label column {n!r} cannot appear in {context}")
        if n not in predictive:
            raise AblationConfigError(
                f"unknown/non-predictive column {n!r} in {context}")


# ---------------------------------------------------------------------------
# Named feature sets
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FeatureSet:
    """One named, frozen feature configuration (target-independent)."""

    name: str
    kind: str  # all | primary_group | cumulative | logo | baseline
    description: str
    features: tuple
    groups: tuple = ()
    rationale: str = ""


#: Simple factual baselines (target-independent, no engineered values).
_BASELINES = (
    FeatureSet(
        name="CURRENT_ORDER_ONLY", kind="baseline",
        description="Current racing position only.",
        features=("position",),
        groups=("STATE",),
        rationale="Simplest factual ordering signal."),
    FeatureSet(
        name="MINIMAL_RACE_STATE", kind="baseline",
        description="Current position, race progress and starting grid.",
        features=("position", "race_progress_frac", "grid_position"),
        groups=("STATE", "PRE_RACE_PRIORS"),
        rationale="Tiny factual state baseline; no imputation of the "
                  "nullable grid slot."),
)


def _ordered(members, order, context,
             registry: FeatureRegistry | None = None) -> tuple:
    member_list = list(members)
    validate_feature_names(member_list, registry, context)
    member_set = set(member_list)
    ordered = tuple(n for n in order if n in member_set)
    if len(ordered) != len(member_set):
        missing = member_set - set(order)
        raise AblationConfigError(
            f"{context}: features absent from canonical order: "
            f"{sorted(missing)}")
    return ordered


def build_feature_sets(registry: FeatureRegistry | None = None) -> dict:
    """All named configurations, frozen and registry-derived."""
    reg = build_f11_registry() if registry is None else registry
    order = canonical_predictive_names(reg)
    groups = build_primary_groups(reg)
    deps = interaction_dependencies(reg)
    group_member = {g: set(groups[g].features) for g in PRIMARY_GROUP_ORDER}

    sets: dict = {}

    for base in _BASELINES:
        sets[base.name] = replace(
            base, features=_ordered(base.features, order, base.name, reg))

    # Cumulative plan C0..C7 follows PRIMARY_GROUP_ORDER (F4-F11 DAG).
    cumulative_names = []
    acc: list = []
    for i, g in enumerate(PRIMARY_GROUP_ORDER):
        acc = acc + list(groups[g].features)
        name = f"CUMULATIVE_{i:02d}_{g}"
        cumulative_names.append(name)
        sets[name] = FeatureSet(
            name=name, kind="cumulative",
            description="Cumulative groups up to and including "
                        f"{g} (stage C{i}).",
            features=_ordered(acc, order, name, reg),
            groups=tuple(PRIMARY_GROUP_ORDER[:i + 1]),
            rationale="Matches the approved F4-F11 computation DAG; each "
                      "rung adds exactly one semantic group.")

    # ALL_84 must equal the F15 manifest predictive list exactly.
    sets["ALL_84"] = FeatureSet(
        name="ALL_84", kind="all",
        description="All 84 predictive columns (registry / F15 manifest).",
        features=tuple(order),
        groups=tuple(PRIMARY_GROUP_ORDER),
        rationale="Canonical complete feature set; no selection performed.")

    # Leave-one-group-out; removing a parent also removes dependent
    # interactions (frozen INTERACTION_DEPENDENCY_POLICY).
    logo_names = []
    for g in PRIMARY_GROUP_ORDER:
        removed = set(group_member[g])
        removed_interactions = [
            name for name, info in deps.items() if g in info["required_groups"]]
        removed |= set(removed_interactions)
        name = f"ALL_MINUS_{g}"
        logo_names.append(name)
        sets[name] = FeatureSet(
            name=name, kind="logo",
            description=f"ALL_84 with {g} removed"
                        + (f" (and dependent interactions: "
                           f"{sorted(removed_interactions)})"
                           if removed_interactions else ""),
            features=_ordered([n for n in order if n not in removed],
                              order, name, reg),
            groups=tuple(x for x in PRIMARY_GROUP_ORDER if x != g),
            rationale="Leave-one-group-out; orphan interactions are removed "
                      "with their parent group.")

    sets["_ORDER"] = order
    return sets


def all_feature_set_names(registry: FeatureRegistry | None = None) -> tuple:
    """Public named configurations, deterministic order (ALL_84 first)."""
    sets = build_feature_sets(registry)
    priority = ["ALL_84", "CURRENT_ORDER_ONLY", "MINIMAL_RACE_STATE"]
    cumulative = [n for n in sets if n.startswith("CUMULATIVE_")]
    logo = [n for n in sets if n.startswith("ALL_MINUS_")]
    rest = [n for n in sets
            if n not in priority + cumulative + logo and n != "_ORDER"]
    return tuple(priority + sorted(cumulative) + sorted(logo) + sorted(rest))


def get_feature_set(name: str,
                    registry: FeatureRegistry | None = None) -> FeatureSet:
    sets = build_feature_sets(registry)
    if name not in sets or name == "_ORDER":
        raise AblationConfigError(
            f"unknown feature set {name!r}; known: "
            f"{list(all_feature_set_names(registry))}")
    return sets[name]


# ---------------------------------------------------------------------------
# Manifest compatibility + resolution API
# ---------------------------------------------------------------------------

def _forbidden_columns(manifest: dict) -> set:
    forbidden = set(manifest.get("metadata_columns", []))
    forbidden |= set(manifest.get("label_columns", []))
    forbidden |= set(manifest.get("label_companion_columns", []))
    forbidden |= set(manifest.get("task_eligibility_columns", []))
    forbidden |= set(CANONICAL_LABEL_NAMES)
    return forbidden


def validate_manifest_compatibility(manifest: dict,
                                    registry: FeatureRegistry | None = None
                                    ) -> None:
    """Fail loudly if the F15 manifest is not the frozen compatible one."""
    reg = build_f11_registry() if registry is None else registry
    validate_registry(reg)
    if manifest.get("matrix_version") != REQUIRED_MATRIX_VERSION:
        raise AblationConfigError(
            f"matrix_version {manifest.get('matrix_version')!r} != required "
            f"{REQUIRED_MATRIX_VERSION!r}")
    if manifest.get("feature_set_version") != REQUIRED_FEATURE_SET_VERSION:
        raise AblationConfigError(
            f"manifest feature_set_version "
            f"{manifest.get('feature_set_version')!r} != required "
            f"{REQUIRED_FEATURE_SET_VERSION!r}")
    if manifest.get("label_set_version") != REQUIRED_LABEL_SET_VERSION:
        raise AblationConfigError(
            f"manifest label_set_version "
            f"{manifest.get('label_set_version')!r} != required "
            f"{REQUIRED_LABEL_SET_VERSION!r}")
    preds = list(manifest.get("predictive_columns", []))
    if len(preds) != EXPECTED_PREDICTIVE_FEATURE_COUNT:
        raise AblationConfigError(
            f"manifest predictive count {len(preds)} != "
            f"{EXPECTED_PREDICTIVE_FEATURE_COUNT}")
    canonical = list(canonical_predictive_names(reg))
    if preds != canonical:
        extra = [p for p in preds if p not in set(canonical)]
        missing = [p for p in canonical if p not in set(preds)]
        raise AblationConfigError(
            f"manifest predictive list is not the canonical registry list; "
            f"extra={extra}, missing={missing}")
    overlap = set(preds) & _forbidden_columns(manifest)
    if overlap:
        raise AblationConfigError(
            f"forbidden column(s) in predictive list: {sorted(overlap)}")


def resolve_feature_set(name: str, manifest: dict | None = None,
                        registry: FeatureRegistry | None = None) -> tuple:
    """Ordered predictive feature names for a named configuration.

    Validates the manifest when supplied, preserves canonical order, and
    rejects unknown configuration names or missing/forbidden features.
    Never infers columns from dataframe contents.
    """
    reg = build_f11_registry() if registry is None else registry
    if manifest is not None:
        validate_manifest_compatibility(manifest, reg)
        order = tuple(manifest["predictive_columns"])
    else:
        order = canonical_predictive_names(reg)
    fs = get_feature_set(name, reg)
    validate_feature_names(fs.features, reg, context=name)
    missing = set(fs.features) - set(order)
    if missing:
        raise AblationConfigError(
            f"{name}: features absent from canonical manifest: "
            f"{sorted(missing)}")
    return tuple(n for n in order if n in set(fs.features))


def interaction_dependencies_for_group(
        group: str, registry: FeatureRegistry | None = None) -> tuple:
    """Interactions removed with a parent group under the frozen policy."""
    deps = interaction_dependencies(registry)
    if group not in PRIMARY_GROUP_ORDER:
        raise AblationConfigError(f"unknown primary group {group!r}")
    return tuple(sorted(n for n, info in deps.items()
                        if group in info["required_groups"]))


# ---------------------------------------------------------------------------
# Fixtures (testing aids, NOT evaluation samples)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class FixtureDef:
    """Deterministic canonical state used to verify Phase-3 plumbing.

    Carries only identity + rationale + expected task-mask states. No
    prediction, no metric, no train/validation/test designation.
    """

    name: str
    state_id: str
    race_id: str
    driver_id: str
    constructor_id: str
    season: int
    round_no: int
    lap_number: int
    rationale: str
    coverage: tuple
    expected_ordinal_eligible: bool = True
    expected_gain_loss_eligible: bool = True
    expected_binary_eligible: bool = True


FIXTURES: tuple = (
    FixtureDef(
        name="era_2018_caution_mid",
        state_id="2018-r01-R|ricciardo|27",
        race_id="2018-r01-R", driver_id="ricciardo",
        constructor_id="red_bull", season=2018, round_no=1, lap_number=27,
        rationale="2018 sparse-era mid-race state under a factual Safety "
                  "Car; exercises caution passthrough on old data.",
        coverage=("2018", "mid", "dry", "caution")),
    FixtureDef(
        name="era_2025_dry_late",
        state_id="2025-r01-R|norris|41",
        race_id="2025-r01-R", driver_id="norris",
        constructor_id="mclaren", season=2025, round_no=1, lap_number=41,
        rationale="Latest-season late-race dry state; exercises the newest "
                  "coverage era and a late position/progress state.",
        coverage=("2025", "late", "dry")),
    FixtureDef(
        name="stage_early_dry_2023",
        state_id="2023-r01-R|alonso|5",
        race_id="2023-r01-R", driver_id="alonso",
        constructor_id="aston_martin", season=2023, round_no=1, lap_number=5,
        rationale="Early race: windowed pace features are history-limited "
                  "and must resolve as explicit nulls/counts.",
        coverage=("2023", "early", "dry")),
    FixtureDef(
        name="stage_mid_dry_2023",
        state_id="2023-r01-R|alonso|28",
        race_id="2023-r01-R", driver_id="alonso",
        constructor_id="aston_martin", season=2023, round_no=1, lap_number=28,
        rationale="Mid race: representative windows and relative context "
                  "available; normal dry operating point.",
        coverage=("2023", "mid", "dry")),
    FixtureDef(
        name="stage_late_dry_2023",
        state_id="2023-r01-R|alonso|50",
        race_id="2023-r01-R", driver_id="alonso",
        constructor_id="aston_martin", season=2023, round_no=1, lap_number=50,
        rationale="Late race: deepest history and highest feature coverage.",
        coverage=("2023", "late", "dry")),
    FixtureDef(
        name="wet_2019_germany",
        state_id="2019-r11-R|hamilton|20",
        race_id="2019-r11-R", driver_id="hamilton",
        constructor_id="mercedes", season=2019, round_no=11, lap_number=20,
        rationale="Wet race (rainfall true, intermediate tyres) mid-race, "
                  "green track; exercises weather/tyre state under rain.",
        coverage=("2019", "mid", "wet")),
    FixtureDef(
        name="partial_wet_2021_belgium",
        state_id="2021-r12-R|hamilton|2",
        race_id="2021-r12-R", driver_id="hamilton",
        constructor_id="mercedes", season=2021, round_no=12, lap_number=2,
        rationale="PARTIAL race (Belgium 2021) with null compound and rain; "
                  "short-history nulls must propagate, not impute.",
        coverage=("2021", "partial", "wet", "early")),
    FixtureDef(
        name="partial_red_2022_japan",
        state_id="2022-r18-R|ocon|2",
        race_id="2022-r18-R", driver_id="ocon",
        constructor_id="alpine", season=2022, round_no=18, lap_number=2,
        rationale="PARTIAL/time-affected race (Japan 2022) under a red flag "
                  "with rain; exercises red-flag invalidity handling.",
        coverage=("2022", "partial", "red", "wet", "early")),
    FixtureDef(
        name="pit_lane_start_2019",
        state_id="2019-r04-R|kubica|49",
        race_id="2019-r04-R", driver_id="kubica",
        constructor_id="williams", season=2019, round_no=4, lap_number=49,
        rationale="Pit-lane starter (grid_position 0) late in race; verifies "
                  "the non-ordinal grid code is preserved, not re-slotted.",
        coverage=("2019", "late", "pit_lane", "dry")),
    FixtureDef(
        name="rookie_substitute_2023",
        state_id="2023-r13-R|lawson|30",
        race_id="2023-r13-R", driver_id="lawson",
        constructor_id="alphatauri", season=2023, round_no=13, lap_number=30,
        rationale="Mid-season substitute with cold-start priors; exercises "
                  "rookie history counts and null summaries.",
        coverage=("2023", "mid", "rookie", "substitute", "dry")),
    FixtureDef(
        name="mask_position_null_2018",
        state_id="2018-r01-R|sirotkin|5",
        race_id="2018-r01-R", driver_id="sirotkin",
        constructor_id="williams", season=2018, round_no=1, lap_number=5,
        rationale="Factual position null and unclassified: gain/loss and "
                  "ordinal task masks must be False while binary masks stay "
                  "True.",
        coverage=("2018", "early", "mask_edge", "dry"),
        expected_ordinal_eligible=False,
        expected_gain_loss_eligible=False,
        expected_binary_eligible=True),
)


def resolve_fixture(name: str) -> FixtureDef:
    for fx in FIXTURES:
        if fx.name == name:
            return fx
    raise AblationConfigError(
        f"unknown fixture {name!r}; known: {[f.name for f in FIXTURES]}")


def validate_fixtures(matrix, manifest: dict,
                      registry: FeatureRegistry | None = None) -> list:
    """Validate every fixture against the canonical matrix + manifest.

    Returns a report list. Fails loudly on any mismatch. No predictions
    or metrics are read or stored.
    """
    validate_manifest_compatibility(manifest, registry)
    predictive = list(manifest["predictive_columns"])
    absent = [c for c in predictive if c not in matrix.columns]
    if absent:
        raise AblationConfigError(
            f"matrix is missing predictive columns: {absent[:10]}")
    expected_cols = set(predictive) | set(manifest.get("metadata_columns", []))
    expected_cols |= set(manifest.get("label_columns", []))
    expected_cols |= set(manifest.get("label_companion_columns", []))
    expected_cols |= set(manifest.get("task_eligibility_columns", []))
    unexpected = [c for c in matrix.columns if c not in expected_cols]
    if unexpected:
        raise AblationConfigError(
            f"matrix exposes unclassified columns (e.g. predictions/metrics): "
            f"{unexpected[:10]}")
    report = []
    for fx in FIXTURES:
        rows = matrix[matrix["state_id"] == fx.state_id]
        if len(rows) != 1:
            raise AblationConfigError(
                f"fixture {fx.name!r} state_id {fx.state_id!r} resolved "
                f"{len(rows)} rows (expected exactly 1)")
        row = rows.iloc[0]
        identity = {
            "race_id": fx.race_id, "driver_id": fx.driver_id,
            "season": fx.season, "round_no": fx.round_no,
            "lap_number": fx.lap_number,
        }
        for col, expected in identity.items():
            got = row[col]
            if col in ("season", "round_no", "lap_number"):
                if int(got) != int(expected):
                    raise AblationConfigError(
                        f"fixture {fx.name!r} {col}={got} != {expected}")
            elif str(got) != str(expected):
                raise AblationConfigError(
                    f"fixture {fx.name!r} {col}={got!r} != {expected!r}")
        ordinal = bool(row["eligible_ordinal_final_position"])
        gain_loss = bool(row["eligible_gain_loss"])
        binary = all(bool(row[c]) for c in (
            "eligible_is_winner", "eligible_is_podium", "eligible_scored_points"))
        if ordinal != fx.expected_ordinal_eligible:
            raise AblationConfigError(
                f"fixture {fx.name!r} ordinal_eligible={ordinal} != "
                f"{fx.expected_ordinal_eligible}")
        if gain_loss != fx.expected_gain_loss_eligible:
            raise AblationConfigError(
                f"fixture {fx.name!r} gain_loss_eligible={gain_loss} != "
                f"{fx.expected_gain_loss_eligible}")
        if binary != fx.expected_binary_eligible:
            raise AblationConfigError(
                f"fixture {fx.name!r} binary_eligible={binary} != "
                f"{fx.expected_binary_eligible}")
        report.append({
            "name": fx.name, "state_id": fx.state_id,
            "race_id": fx.race_id, "driver_id": fx.driver_id,
            "season": fx.season, "round_no": fx.round_no,
            "lap_number": fx.lap_number, "coverage": list(fx.coverage),
            "ordinal_eligible": ordinal, "gain_loss_eligible": gain_loss,
            "binary_eligible": binary,
        })
    return report


# ---------------------------------------------------------------------------
# Machine-readable export + deterministic hash
# ---------------------------------------------------------------------------

def _fixture_dict(fx: FixtureDef) -> dict:
    return {
        "name": fx.name, "state_id": fx.state_id, "race_id": fx.race_id,
        "driver_id": fx.driver_id, "constructor_id": fx.constructor_id,
        "season": fx.season, "round_no": fx.round_no,
        "lap_number": fx.lap_number, "rationale": fx.rationale,
        "coverage": list(fx.coverage),
        "expected_masks": {
            "ordinal_eligible": fx.expected_ordinal_eligible,
            "gain_loss_eligible": fx.expected_gain_loss_eligible,
            "binary_eligible": fx.expected_binary_eligible,
        },
    }


def _feature_set_dict(fs: FeatureSet) -> dict:
    return {
        "kind": fs.kind,
        "description": fs.description,
        "feature_count": len(fs.features),
        "groups": list(fs.groups),
        "rationale": fs.rationale,
        "features": list(fs.features),
    }


def _hash_payload(registry: FeatureRegistry | None = None) -> dict:
    """Semantic payload hashed for drift detection (no paths/timestamps)."""
    reg = build_f11_registry() if registry is None else registry
    groups = build_primary_groups(reg)
    sets = build_feature_sets(reg)
    deps = interaction_dependencies(reg)
    return {
        "ablation_config_version": ABLATION_CONFIG_VERSION,
        "required_feature_set_version": REQUIRED_FEATURE_SET_VERSION,
        "required_label_set_version": REQUIRED_LABEL_SET_VERSION,
        "required_matrix_version": REQUIRED_MATRIX_VERSION,
        "primary_group_order": list(PRIMARY_GROUP_ORDER),
        "primary_groups": {
            g: {
                "description": groups[g].description,
                "rationale": groups[g].rationale,
                "source_families": list(groups[g].source_families),
                "dependencies": list(groups[g].dependencies),
                "features": list(groups[g].features),
            } for g in PRIMARY_GROUP_ORDER
        },
        "semantic_subgroups": {
            k: sorted(v) for k, v in SEMANTIC_SUBGROUPS.items()
        },
        "interaction_dependencies": {
            k: {"required_primitives": list(v["required_primitives"]),
                "required_groups": list(v["required_groups"])}
            for k, v in deps.items()
        },
        "interaction_policy": INTERACTION_DEPENDENCY_POLICY,
        "named_feature_sets": {
            n: _feature_set_dict(sets[n])
            for n in all_feature_set_names(reg)
        },
        "fixtures": [_fixture_dict(fx) for fx in FIXTURES],
    }


def semantic_hash(registry: FeatureRegistry | None = None) -> str:
    blob = json.dumps(_hash_payload(registry), sort_keys=True,
                      separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def ablation_config_dict(registry: FeatureRegistry | None = None) -> dict:
    """Deterministic machine-readable representation (config_hash included)."""
    reg = build_f11_registry() if registry is None else registry
    payload = _hash_payload(reg)
    config = dict(payload)
    config["config_hash"] = semantic_hash(reg)
    config["cumulative_configurations"] = [
        n for n in all_feature_set_names(reg) if n.startswith("CUMULATIVE_")]
    config["logo_configurations"] = [
        n for n in all_feature_set_names(reg) if n.startswith("ALL_MINUS_")]
    config["baseline_configurations"] = ["CURRENT_ORDER_ONLY",
                                         "MINIMAL_RACE_STATE"]
    config["all_feature_set"] = "ALL_84"
    config["partition_audit"] = partition_audit(reg)
    config["registry_fingerprint"] = reg.fingerprint()
    config["total_predictive_features"] = len(canonical_predictive_names(reg))
    return config


def render_ablation_config(registry: FeatureRegistry | None = None) -> str:
    """Canonical JSON text; repeated calls are byte-identical."""
    return json.dumps(ablation_config_dict(registry), indent=2,
                      sort_keys=True) + "\n"


def write_ablation_config(paths, out_dir: Path | None = None,
                          registry: FeatureRegistry | None = None) -> Path:
    """Write the F16 config beside the F15 manifest (separate artifact)."""
    from raceintel.features.build_matrix import MATRIX_ENTITY, MATRIX_VERSION
    base = Path(out_dir) if out_dir else (
        paths.processed_dir / MATRIX_ENTITY / f"matrix_version={MATRIX_VERSION}")
    base.mkdir(parents=True, exist_ok=True)
    dest = base / EXPORT_FILENAME
    tmp = dest.with_suffix(".json.tmp")
    try:
        tmp.write_text(render_ablation_config(registry))
        os.replace(tmp, dest)
    except Exception:
        if tmp.exists():
            tmp.unlink()
        raise
    return dest


# ---------------------------------------------------------------------------
# Phase-3 handoff API (thin wrappers; no estimator, no split, no preprocess)
# ---------------------------------------------------------------------------

def load_canonical_matrix(paths, out_dir: Path | None = None):
    """Load the F15 (matrix, manifest) pair. No transformation."""
    from raceintel.features.build_matrix import load_matrix
    return load_matrix(paths, out_dir)


def load_task(task: str, paths, out_dir: Path | None = None,
              with_metadata: bool = True):
    """Load (X, y, eligibility_mask) via the F15 contract. No preprocessing."""
    from raceintel.features.build_matrix import load_task as _load_task
    return _load_task(task, paths, out_dir=out_dir,
                      with_metadata=with_metadata)
