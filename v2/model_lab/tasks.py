"""Frozen task resolution for the Model Lab.

Resolves a task name to its target column, eligibility mask, kind, metric
set and probability semantics from the M0 contracts. Eligibility logic is
never re-derived here — the mask name comes straight from
``protocol.TASK_SPECS`` / the Phase-2 ``TASKS`` table.
"""

from __future__ import annotations

from dataclasses import dataclass

from v2.model_lab.errors import UnknownTaskError
from v2.model_lab.protocol import (
    BINARY_PRIMARY_METRICS,
    BINARY_SECONDARY_METRICS,
    ORDINAL_METRICS,
    POSITION_CHANGE_METRICS,
    RACE_LEVEL_WINNER_METRICS,
    TASK_SPECS,
    TaskKind,
    TaskTier,
)

#: Binary probability semantics identifiers (see protocol.PROBABILITY_SEMANTICS).
SEMANTICS_INDEPENDENT_BINARY = "INDEPENDENT_BINARY"
SEMANTICS_POSITIVE_CLASS = "POSITIVE_CLASS_PROBABILITY"


@dataclass(frozen=True)
class ResolvedTask:
    name: str
    tier: str
    kind: str
    label_column: str
    eligibility_mask: str
    metrics: tuple
    race_metrics: tuple
    probability_semantics: str | None

    @property
    def is_binary(self) -> bool:
        return self.kind == TaskKind.BINARY.value

    @property
    def is_ordinal(self) -> bool:
        return self.kind == TaskKind.ORDINAL.value

    @property
    def is_regression(self) -> bool:
        return self.kind == TaskKind.REGRESSION.value

    @property
    def is_primary(self) -> bool:
        return self.tier == TaskTier.PRIMARY.value

    def to_dict(self) -> dict:
        return {
            "name": self.name, "tier": self.tier, "kind": self.kind,
            "label_column": self.label_column,
            "eligibility_mask": self.eligibility_mask,
            "metrics": list(self.metrics),
            "race_metrics": list(self.race_metrics),
            "probability_semantics": self.probability_semantics,
        }


def resolve_task(name: str) -> ResolvedTask:
    """Resolve a frozen task; DNF and unknown tasks fail explicitly."""
    if name not in TASK_SPECS:
        raise UnknownTaskError(
            f"unknown task {name!r}; known: {sorted(TASK_SPECS)}")
    spec = TASK_SPECS[name]
    if spec.tier is TaskTier.DEFERRED:
        raise UnknownTaskError(
            f"task {name!r} is DEFERRED (no frozen Phase-2 target); "
            "it must not be resolved for experimentation")
    if spec.label_column is None or spec.eligibility_mask is None:
        raise UnknownTaskError(f"task {name!r} has no materialized contract")

    if spec.kind is TaskKind.BINARY:
        metrics = tuple(BINARY_PRIMARY_METRICS + BINARY_SECONDARY_METRICS)
        semantics = (SEMANTICS_INDEPENDENT_BINARY
                     if name == "winner" else SEMANTICS_POSITIVE_CLASS)
    elif spec.kind is TaskKind.ORDINAL:
        metrics = tuple(ORDINAL_METRICS)
        semantics = None
    elif spec.kind is TaskKind.REGRESSION:
        metrics = tuple(POSITION_CHANGE_METRICS)
        semantics = None
    else:  # pragma: no cover - guarded by the registry
        raise UnknownTaskError(f"task {name!r} has unsupported kind")

    race_metrics = (tuple(RACE_LEVEL_WINNER_METRICS)
                    if name == "winner" else ())
    return ResolvedTask(
        name=name, tier=spec.tier.value, kind=spec.kind.value,
        label_column=spec.label_column,
        eligibility_mask=spec.eligibility_mask,
        metrics=metrics, race_metrics=race_metrics,
        probability_semantics=semantics,
    )


def all_task_names() -> tuple:
    """Resolvable (non-deferred) task names, frozen order."""
    return tuple(s.name for s in TASK_SPECS.values()
                 if s.tier is not TaskTier.DEFERRED)
