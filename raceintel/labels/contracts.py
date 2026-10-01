"""F13 canonical label/target contracts (Phase 2 label layer).

Authoritative, separate namespace for supervised-learning TARGETS.
Labels are observed outcomes at (race_id, driver_id) grain, physically
and logically separate from predictive state. This module is metadata +
validation + pure derivation: no model training, no feature computation,
no Phase-1 mutation.

Retained targets (LABEL_SET_VERSION v1):
- final_position (ORDINAL, canonical passthrough of frozen position_final)
- is_winner / is_podium / scored_points (BINARY, frozen derived flags)
- position_change_from_state + gains/loses_position_by_finish
  (state-dependent FORMULAS, specified here, materialized in F15)

Deferred: any DNF/reliability target, expected_finish label, ranking
pairs/groups. Telemetry untouched.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


#: Independent label-set version. Never affects FEATURE_SET_VERSION.
LABEL_SET_VERSION = "v1"

#: Canonical outcome grain. Labels never vary by lap.
LABEL_GRAIN: tuple[str, ...] = ("race_id", "driver_id")


class LabelTask(str, Enum):
    """Minimal task vocabulary. Only what Phase 3 needs."""

    BINARY = "binary"
    ORDINAL = "ordinal"
    CONTINUOUS = "continuous"


class LabelStatus(str, Enum):
    """Lifecycle. Status never implies model quality."""

    CANONICAL = "canonical"  # verbatim frozen outcome column, renamed
    SPECIFIED = "specified"  # formula frozen here, materialized in F15


@dataclass(frozen=True)
class LabelDef:
    """Immutable machine-readable target definition."""

    name: str
    version: int
    dtype: str  # bool | int64 | float64
    description: str
    sources: tuple  # exact 'entity.field' lineage, >= 1
    grain: tuple  # LABEL_GRAIN or LABEL_GRAIN + state lap
    derivation: str
    null_policy: str
    task: LabelTask
    status: LabelStatus

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "version": self.version,
            "dtype": self.dtype,
            "description": self.description,
            "sources": list(self.sources),
            "grain": list(self.grain),
            "derivation": self.derivation,
            "null_policy": self.null_policy,
            "task": self.task.value,
            "status": self.status.value,
        }


class LabelRegistry:
    """Deterministic registry: sorted enumeration, explicit registration."""

    def __init__(self) -> None:
        self._defs: dict[str, LabelDef] = {}

    def register(self, defn: LabelDef) -> LabelDef:
        if not defn.name or not defn.name.strip():
            raise ValueError("label name must be non-empty")
        if not isinstance(defn.version, int) or defn.version < 1:
            raise ValueError(f"{defn.name}: version must be >= 1")
        if defn.dtype not in ("bool", "int64", "float64"):
            raise ValueError(f"{defn.name}: bad dtype {defn.dtype!r}")
        if not defn.sources:
            raise ValueError(f"{defn.name}: empty source lineage forbidden")
        if defn.name in self._defs:
            raise ValueError(f"duplicate label name: {defn.name}")
        self._defs[defn.name] = defn
        return defn

    def get(self, name: str) -> LabelDef:
        return self._defs[name]

    def __len__(self) -> int:
        return len(self._defs)

    def __iter__(self):
        for name in sorted(self._defs):
            yield self._defs[name]

    def names(self) -> list:
        return sorted(self._defs)

    def to_dict(self) -> dict:
        return {
            "label_set_version": LABEL_SET_VERSION,
            "label_count": len(self._defs),
            "labels": [self._defs[n].to_dict() for n in sorted(self._defs)],
        }


def _race_driver() -> tuple:
    return LABEL_GRAIN


def build_label_registry() -> LabelRegistry:
    """The 7 retained F13 target definitions (measured §29 audit)."""
    registry = LabelRegistry()
    registry.register(LabelDef(
        name="final_position", version=1, dtype="int64",
        description="Official final position (FastF1 Position), verbatim. "
                    "Null only where the source orders nothing (3 W rows). "
                    "W/D numerics are source back-rank, not earned slots: "
                    "ordinal/ranking use should condition on classified "
                    "companionship (see docs).",
        sources=("race_driver_labels.position_final",),
        grain=_race_driver(),
        derivation="canonical passthrough (frozen v2/d9.py "
                   "labels_from_results; never recomputed here)",
        null_policy="null iff frozen position_final is null",
        task=LabelTask.ORDINAL, status=LabelStatus.CANONICAL,
    ))
    registry.register(LabelDef(
        name="is_winner", version=1, dtype="bool",
        description="Factual race winner: official final position 1.",
        sources=("race_driver_labels.winner_flag",),
        grain=_race_driver(),
        derivation="canonical passthrough (frozen: position_final == 1, "
                   "null iff position_final null; exactly 1 per race)",
        null_policy="null iff frozen winner_flag is null (3 W rows)",
        task=LabelTask.BINARY, status=LabelStatus.CANONICAL,
    ))
    registry.register(LabelDef(
        name="is_podium", version=1, dtype="bool",
        description="Factual podium: official final position in (1, 2, 3).",
        sources=("race_driver_labels.podium_flag",),
        grain=_race_driver(),
        derivation="canonical passthrough (frozen: position_final in "
                   "1..3, null iff position_final null; exactly 3 per race)",
        null_policy="null iff frozen podium_flag is null (3 W rows)",
        task=LabelTask.BINARY, status=LabelStatus.CANONICAL,
    ))
    registry.register(LabelDef(
        name="scored_points", version=1, dtype="bool",
        description="Officially scored >0 championship points in this race "
                    "(half-points included; never position-inferred).",
        sources=("race_driver_labels.points_finish_flag",),
        grain=_race_driver(),
        derivation="canonical passthrough (frozen: points > 0; never null)",
        null_policy="never null (source points never null)",
        task=LabelTask.BINARY, status=LabelStatus.CANONICAL,
    ))
    registry.register(LabelDef(
        name="position_change_from_state", version=1, dtype="int64",
        description="Eventual position movement from a LAP_END state: "
                    "current_position minus final_position. Positive = "
                    "finishes ahead of current slot; negative = behind. "
                    "Captures pits/retirements/penalties/passes/incidents "
                    "indiscriminately: never called 'overtake'.",
        sources=("driver_lap_state_d9.position",
                 "race_driver_labels.position_final"),
        grain=_race_driver() + ("lap_number",),
        derivation="SPECIFIED formula (F15 materializes): "
                   "current_position - final_position, null-propagating",
        null_policy="null iff either input null (294 position-null "
                    "states; 0 final-null states in D9 scope)",
        task=LabelTask.CONTINUOUS, status=LabelStatus.SPECIFIED,
    ))
    registry.register(LabelDef(
        name="gains_position_by_finish", version=1, dtype="bool",
        description="Eventual net gain vs current state (difference > 0).",
        sources=("driver_lap_state_d9.position",
                 "race_driver_labels.position_final"),
        grain=_race_driver() + ("lap_number",),
        derivation="SPECIFIED formula: position_change_from_state > 0; "
                   "ties -> False; null-propagating",
        null_policy="null iff position_change_from_state is null",
        task=LabelTask.BINARY, status=LabelStatus.SPECIFIED,
    ))
    registry.register(LabelDef(
        name="loses_position_by_finish", version=1, dtype="bool",
        description="Eventual net loss vs current state (difference < 0).",
        sources=("driver_lap_state_d9.position",
                 "race_driver_labels.position_final"),
        grain=_race_driver() + ("lap_number",),
        derivation="SPECIFIED formula: position_change_from_state < 0; "
                   "ties -> False; null-propagating",
        null_policy="null iff position_change_from_state is null",
        task=LabelTask.BINARY, status=LabelStatus.SPECIFIED,
    ))
    return registry


#: Exact canonical target names. Imported by the predictive feature
#: registry ONLY as an outcome-name guard (metadata, never values).
#: No feature calculator may import this module (pinned by test).
CANONICAL_LABEL_NAMES: frozenset = frozenset(
    d.name for d in build_label_registry()
)
