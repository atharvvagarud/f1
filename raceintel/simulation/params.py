"""Phase-6 R3 empirical parameter artifact contract + read-only loader.

Owns the deterministic, versioned parameter layer that the future simulation
kernel (R4+) consumes. It contains NO estimation code and imports NO
pandas/numpy/sklearn: estimation lives in ``v2.simulation.estimator`` and the
``scripts/build_simulation_parameters.py`` CLI. This module is stdlib-only so
the runtime loader can never accidentally read canonical data, the feature
engine, the winner model, labels, replay prediction caches, or the API layer.

Scientific boundary (R3-D/E/T):
- a parameter set is an immutable typed artifact holding empirical families
  (pace baseline, constructor offset, race-progress trend, degradation,
  residual variation, pit loss, stint length, compound transitions);
- every entry exposes its samples/support/fallback so a global fallback can
  never masquerade as a circuit-specific measurement;
- the *scientific hash* is a SHA-256 over everything except creation
  metadata, so changing data, eligibility, parameters, or the estimation
  window changes identity, while timestamps/paths/hostnames do not;
- effects the canonical evidence cannot separate (compound offsets) are
  stored with an explicit ``deferred`` identifiability marker and a zero
  fallback rather than a fabricated precision.

Integration: :meth:`SimulationParameterSet.parameter_identity` returns the
R1 ``ParameterIdentity`` seam (set id / version / scientific hash).
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from raceintel.simulation.config import ParameterIdentity
from raceintel.simulation.errors import (
    SimulationContractError,
    SimulationValidationError,
)
from raceintel.simulation.state import canonical_sha256, _req_id, _req_int

__all__ = [
    "PARAMETER_CONTRACT_VERSION",
    "ESTIMATOR_VERSION",
    "ELIGIBILITY_RULE_VERSION",
    "PARAMETER_SET_ID",
    "PARAMETER_MANIFEST_FILENAME",
    "SUPPORT_LEVELS",
    "FALLBACK_LEVELS",
    "IDENTIFIABILITY_LEVELS",
    "DRY_COMPOUNDS",
    "WET_COMPOUNDS",
    "KNOWN_COMPOUNDS",
    "FAMILY_NAMES",
    "SupportEntry",
    "ParameterFamily",
    "SimulationParameterSet",
    "load_simulation_parameters",
    "parameter_storage_dir",
]

# ---------------------------------------------------------------------------
# Versioned identity.
# ---------------------------------------------------------------------------

#: Parameter-artifact schema version. Bump on any contract-shape change.
PARAMETER_CONTRACT_VERSION = "r3-v1"

#: Estimator logic version. Bump when estimation semantics change.
ESTIMATOR_VERSION = "r3-estimator-v1"

#: Eligibility rule version (R3-B). Bump when the eligible-lap rule changes.
ELIGIBILITY_RULE_VERSION = "r3-eligibility-v1"

#: Stable artifact set id (participates in R1 ``ParameterIdentity``).
PARAMETER_SET_ID = "phase6-r3-empirical"

PARAMETER_MANIFEST_FILENAME = "manifest.json"

SUPPORT_LEVELS = ("strong", "weak", "unavailable")
FALLBACK_LEVELS = ("exact", "circuit", "season", "era", "compound", "global",
                   "deferred", "none")
IDENTIFIABILITY_LEVELS = ("identified", "weak", "deferred")

DRY_COMPOUNDS = ("SOFT", "MEDIUM", "HARD", "SUPERSOFT", "ULTRASOFT",
                 "HYPERSOFT")
WET_COMPOUNDS = ("INTERMEDIATE", "WET")
KNOWN_COMPOUNDS = DRY_COMPOUNDS + WET_COMPOUNDS

# Family names (stable keys into ``SimulationParameterSet.families``).
FAMILY_NAMES = (
    "pace_base_s",
    "pace_base_fallback_s",
    "constructor_pace_offset_s",
    "race_progress_slope_s_per_lap",
    "degradation_slope_s_per_lap",
    "compound_offset_s",
    "lap_residual_distribution_s",
    "pit_effective_loss_s",
    "pit_lane_transit_s",
    "pit_in_lap_penalty_s",
    "pit_out_lap_penalty_s",
    "stint_length_laps",
    "compound_transition_probability",
)


def _finite(value: object, name: str) -> float:
    if type(value) not in (int, float):
        raise SimulationContractError(
            f"{name} must be a plain finite number, got {value!r}")
    result = float(value)
    if not math.isfinite(result):
        raise SimulationValidationError(
            f"{name} must be finite (no NaN/Inf), got {value!r}")
    return result


def _probabilities(values) -> tuple:
    probs = tuple(_finite(v, "probability") for v in values)
    if not probs:
        return probs
    if any(p <= 0.0 or p > 1.0 for p in probs):
        raise SimulationValidationError(
            f"probabilities must be in (0, 1], got {probs!r}")
    if any(b <= a for a, b in zip(probs, probs[1:])):
        raise SimulationValidationError(
            f"probabilities must be strictly ascending, got {probs!r}")
    return probs


@dataclass(frozen=True)
class SupportEntry:
    """One empirical value plus its visible evidence (R3-T).

    Exactly one of ``value`` (scalar) or ``probabilities`` +
    ``quantile_values`` (empirical distribution) is populated. ``deferred``
    entries carry no value and a zero-effect contract is applied by the
    consumer from ``fallback_level == 'deferred'``.
    """

    group_key: str
    sample_count: int
    support_level: str
    fallback_level: str
    value: float | None = None
    probabilities: tuple = ()
    quantile_values: tuple = ()
    observed_min: float | None = None
    observed_max: float | None = None
    std: float | None = None
    mad: float | None = None
    identifiability: str = "identified"

    def __post_init__(self) -> None:
        object.__setattr__(self, "group_key",
                            _req_id(self.group_key, "group_key"))
        object.__setattr__(self, "sample_count",
                            _req_int(self.sample_count, "sample_count",
                                     minimum=0))
        if self.support_level not in SUPPORT_LEVELS:
            raise SimulationContractError(
                f"support_level must be one of {SUPPORT_LEVELS}, "
                f"got {self.support_level!r}")
        if self.fallback_level not in FALLBACK_LEVELS:
            raise SimulationContractError(
                f"fallback_level must be one of {FALLBACK_LEVELS}, "
                f"got {self.fallback_level!r}")
        if self.identifiability not in IDENTIFIABILITY_LEVELS:
            raise SimulationContractError(
                f"identifiability must be one of {IDENTIFIABILITY_LEVELS}, "
                f"got {self.identifiability!r}")
        has_scalar = self.value is not None
        probs = _probabilities(self.probabilities)
        quants = tuple(_finite(v, "quantile_value")
                       for v in self.quantile_values)
        if probs and len(probs) != len(quants):
            raise SimulationValidationError(
                "probabilities and quantile_values must have equal length")
        if has_scalar and probs:
            raise SimulationValidationError(
                "SupportEntry carries both a scalar and a distribution")
        if not has_scalar and not probs and self.identifiability != "deferred":
            raise SimulationValidationError(
                "SupportEntry must carry a scalar, a distribution, or be "
                "explicitly deferred")
        if has_scalar:
            object.__setattr__(self, "value",
                               _finite(self.value, "value"))
        object.__setattr__(self, "probabilities", probs)
        object.__setattr__(self, "quantile_values", quants)
        for attr in ("observed_min", "observed_max", "std", "mad"):
            raw = getattr(self, attr)
            if raw is not None:
                object.__setattr__(self, attr, _finite(raw, attr))
        if (self.observed_min is not None and self.observed_max is not None
                and self.observed_min > self.observed_max):
            raise SimulationValidationError(
                f"observed_min {self.observed_min!r} exceeds observed_max "
                f"{self.observed_max!r}")
        if self.std is not None and self.std < 0.0:
            raise SimulationValidationError(
                f"std must be nonnegative, got {self.std!r}")
        if self.mad is not None and self.mad < 0.0:
            raise SimulationValidationError(
                f"mad must be nonnegative, got {self.mad!r}")

    @property
    def is_distribution(self) -> bool:
        return bool(self.probabilities)

    def to_dict(self) -> dict:
        return {
            "group_key": self.group_key,
            "sample_count": self.sample_count,
            "support_level": self.support_level,
            "fallback_level": self.fallback_level,
            "value": self.value,
            "probabilities": list(self.probabilities),
            "quantile_values": list(self.quantile_values),
            "observed_min": self.observed_min,
            "observed_max": self.observed_max,
            "std": self.std,
            "mad": self.mad,
            "identifiability": self.identifiability,
        }

    @classmethod
    def from_dict(cls, data: object) -> "SupportEntry":
        if not isinstance(data, dict):
            raise SimulationContractError(
                f"SupportEntry payload must be an object, got {data!r}")
        return cls(
            group_key=data["group_key"],
            sample_count=data["sample_count"],
            support_level=data["support_level"],
            fallback_level=data["fallback_level"],
            value=data.get("value"),
            probabilities=tuple(data.get("probabilities") or ()),
            quantile_values=tuple(data.get("quantile_values") or ()),
            observed_min=data.get("observed_min"),
            observed_max=data.get("observed_max"),
            std=data.get("std"),
            mad=data.get("mad"),
            identifiability=data.get("identifiability", "identified"),
        )


@dataclass(frozen=True)
class ParameterFamily:
    """A named, keyed family of :class:`SupportEntry` values (R3-D/T)."""

    name: str
    unit: str
    entries: Mapping[str, SupportEntry]
    notes: str = ""

    def __post_init__(self) -> None:
        object.__setattr__(self, "name", _req_id(self.name, "family name"))
        object.__setattr__(self, "unit", _req_id(self.unit, "family unit"))
        if not isinstance(self.entries, Mapping):
            raise SimulationContractError(
                f"family {self.name!r} entries must be a mapping")
        for key, entry in self.entries.items():
            if not isinstance(key, str) or not key:
                raise SimulationContractError(
                    f"family {self.name!r} has an invalid key {key!r}")
            if not isinstance(entry, SupportEntry):
                raise SimulationContractError(
                    f"family {self.name!r}[{key!r}] is not a SupportEntry")

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "unit": self.unit,
            "notes": self.notes,
            "entries": {k: v.to_dict() for k, v in self.entries.items()},
        }

    @classmethod
    def from_dict(cls, data: object) -> "ParameterFamily":
        if not isinstance(data, dict):
            raise SimulationContractError(
                f"ParameterFamily payload must be an object, got {data!r}")
        entries = data.get("entries")
        if not isinstance(entries, dict):
            raise SimulationContractError(
                f"family {data.get('name')!r} entries must be an object")
        return cls(
            name=data["name"],
            unit=data["unit"],
            notes=data.get("notes", ""),
            entries={k: SupportEntry.from_dict(v)
                     for k, v in entries.items()},
        )


@dataclass(frozen=True)
class SimulationParameterSet:
    """Immutable, versioned empirical parameter artifact (R3-D)."""

    parameter_contract_version: str
    estimator_version: str
    eligibility_rule_version: str
    parameter_set_id: str
    through_season: int
    estimation_seasons: tuple
    source_data: Mapping[str, object]
    regimes: Mapping[str, object]
    policies: Mapping[str, str]
    grouping_hierarchy: Mapping[str, tuple]
    support_thresholds: Mapping[str, int]
    families: Mapping[str, ParameterFamily]
    diagnostics: Mapping[str, object]
    creation_metadata: Mapping[str, object]

    def __post_init__(self) -> None:
        if self.parameter_contract_version != PARAMETER_CONTRACT_VERSION:
            raise SimulationContractError(
                f"unsupported parameter_contract_version "
                f"{self.parameter_contract_version!r} (expected "
                f"{PARAMETER_CONTRACT_VERSION!r})")
        object.__setattr__(self, "estimator_version",
                            _req_id(self.estimator_version,
                                    "estimator_version"))
        object.__setattr__(self, "eligibility_rule_version",
                            _req_id(self.eligibility_rule_version,
                                    "eligibility_rule_version"))
        object.__setattr__(self, "parameter_set_id",
                            _req_id(self.parameter_set_id,
                                    "parameter_set_id"))
        through = _req_int(self.through_season, "through_season", minimum=2018)
        if through > 2024:
            raise SimulationValidationError(
                f"through_season must be <= 2024 (2025 is firewalled), "
                f"got {through!r}")
        object.__setattr__(self, "through_season", through)
        seasons = tuple(int(s) for s in self.estimation_seasons)
        if not seasons:
            raise SimulationValidationError(
                "estimation_seasons must be non-empty")
        if tuple(sorted(set(seasons))) != seasons:
            raise SimulationValidationError(
                "estimation_seasons must be sorted and unique")
        if any(s < 2018 or s > 2024 for s in seasons):
            raise SimulationValidationError(
                f"estimation seasons must be within 2018-2024, got "
                f"{seasons!r}")
        if max(seasons) > through:
            raise SimulationValidationError(
                f"estimation_seasons {seasons!r} exceed through_season "
                f"{through!r}")
        object.__setattr__(self, "estimation_seasons", seasons)
        if not isinstance(self.families, Mapping):
            raise SimulationContractError("families must be a mapping")
        for name in FAMILY_NAMES:
            if name not in self.families:
                raise SimulationValidationError(
                    f"parameter artifact is missing family {name!r}")
            if not isinstance(self.families[name], ParameterFamily):
                raise SimulationContractError(
                    f"family {name!r} is not a ParameterFamily")
        self._validate_transitions()

    # -- scientific identity -------------------------------------------------

    def to_scientific_dict(self) -> dict:
        """Everything that defines the science, excluding creation metadata."""
        return {
            "parameter_contract_version": self.parameter_contract_version,
            "estimator_version": self.estimator_version,
            "eligibility_rule_version": self.eligibility_rule_version,
            "parameter_set_id": self.parameter_set_id,
            "through_season": self.through_season,
            "estimation_seasons": list(self.estimation_seasons),
            "source_data": _plain(self.source_data),
            "regimes": _plain(self.regimes),
            "policies": _plain(self.policies),
            "grouping_hierarchy": _plain(self.grouping_hierarchy),
            "support_thresholds": _plain(self.support_thresholds),
            "families": {k: v.to_dict() for k, v in self.families.items()},
            "diagnostics": _plain(self.diagnostics),
        }

    def scientific_hash(self) -> str:
        """SHA-256 over the scientific content only (R3-E)."""
        return canonical_sha256(self.to_scientific_dict())

    @property
    def parameter_version(self) -> str:
        return (f"{self.parameter_contract_version}."
                f"{self.through_season}.{self.scientific_hash()[:12]}")

    def parameter_identity(self) -> ParameterIdentity:
        """R1 identity seam (R3-E): set id + version + scientific hash."""
        return ParameterIdentity(
            parameter_set_id=self.parameter_set_id,
            parameter_version=self.parameter_version,
            parameter_hash=self.scientific_hash(),
        )

    # -- accessors -----------------------------------------------------------

    def family(self, name: str) -> ParameterFamily:
        try:
            return self.families[name]
        except KeyError as exc:
            raise SimulationContractError(
                f"unknown parameter family {name!r}") from exc

    def lookup(self, name: str, key: str) -> SupportEntry:
        family = self.family(name)
        try:
            return family.entries[key]
        except KeyError as exc:
            raise SimulationValidationError(
                f"family {name!r} has no entry for key {key!r}") from exc

    # -- validation ----------------------------------------------------------

    def _validate_transitions(self) -> None:
        totals: dict = defaultdict(float)
        for key, entry in self.family(
                "compound_transition_probability").entries.items():
            current = key.split("->", 1)[0]
            if entry.value is None:
                raise SimulationValidationError(
                    f"transition {key!r} must carry a probability")
            if entry.value < 0.0 or entry.value > 1.0:
                raise SimulationValidationError(
                    f"transition {key!r} probability out of [0,1]: "
                    f"{entry.value!r}")
            totals[current] += entry.value
        for current, total in totals.items():
            if abs(total - 1.0) > 1e-6:
                raise SimulationValidationError(
                    f"transition distribution for {current!r} sums to "
                    f"{total!r}, not 1")

    # -- serialization -------------------------------------------------------

    def to_dict(self) -> dict:
        payload = self.to_scientific_dict()
        payload["scientific_hash"] = self.scientific_hash()
        payload["creation_metadata"] = _plain(self.creation_metadata)
        return payload

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), sort_keys=True, indent=indent,
                          allow_nan=False)

    @classmethod
    def from_dict(cls, data: object) -> "SimulationParameterSet":
        if not isinstance(data, dict):
            raise SimulationContractError(
                "parameter artifact must be a JSON object")
        families_raw = data.get("families")
        if not isinstance(families_raw, dict):
            raise SimulationContractError(
                "parameter artifact must contain a families object")
        families = {k: ParameterFamily.from_dict(v)
                    for k, v in families_raw.items()}
        return cls(
            parameter_contract_version=data["parameter_contract_version"],
            estimator_version=data["estimator_version"],
            eligibility_rule_version=data["eligibility_rule_version"],
            parameter_set_id=data["parameter_set_id"],
            through_season=data["through_season"],
            estimation_seasons=tuple(data["estimation_seasons"]),
            source_data=data.get("source_data", {}),
            regimes=data.get("regimes", {}),
            policies=data.get("policies", {}),
            grouping_hierarchy=data.get("grouping_hierarchy", {}),
            support_thresholds=data.get("support_thresholds", {}),
            families=families,
            diagnostics=data.get("diagnostics", {}),
            creation_metadata=data.get("creation_metadata", {}),
        )


def _plain(value: object) -> object:
    """Convert tuples/frozensets to lists for deterministic JSON."""
    if isinstance(value, Mapping):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(v) for v in value]
    return value


def parameter_storage_dir(project_root, through_season: int) -> Path:
    """Canonical generated-artifact location (R3-F).

    ``data/v2/simulation/params/<contract>__through-<season>/``. Under
    ``data/v2/`` which the repository deliberately keeps untracked
    (generated, reproducible), so parameter artifacts are never committed.
    """
    return (Path(project_root) / "data" / "v2" / "simulation" / "params"
            / f"{PARAMETER_CONTRACT_VERSION}__through-{int(through_season)}")


def load_simulation_parameters(source, *, verify_hash: bool = True
                               ) -> SimulationParameterSet:
    """Read-only loader for a parameter artifact (R3-U).

    ``source`` is a directory containing ``manifest.json`` or a direct
    ``.json`` path. It validates the contract version, reconstructs the
    typed set, and (by default) re-derives the scientific hash and rejects a
    tampered artifact. It performs NO estimation, mutates nothing, reads no
    canonical data, and never touches the winner model or labels.

    Raises ``SimulationValidationError`` on a missing/corrupt/tampered
    artifact and ``SimulationContractError`` on programming misuse.
    """
    path = Path(source)
    if path.is_dir():
        path = path / PARAMETER_MANIFEST_FILENAME
    if not path.exists():
        raise SimulationValidationError(
            f"parameter artifact not found: {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise SimulationValidationError(
            f"parameter artifact unreadable: {path}: {exc}") from exc
    parameter_set = SimulationParameterSet.from_dict(raw)
    if verify_hash:
        recorded = raw.get("scientific_hash")
        derived = parameter_set.scientific_hash()
        if recorded is None:
            raise SimulationValidationError(
                "parameter artifact is missing scientific_hash")
        if recorded != derived:
            raise SimulationValidationError(
                "parameter artifact scientific hash mismatch: recorded "
                f"{recorded!r} != derived {derived!r} (tampered or corrupt)")
    return parameter_set
