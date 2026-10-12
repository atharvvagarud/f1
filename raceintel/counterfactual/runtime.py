"""V3.7F production runtime adapter (integration only; no science).

Thin orchestration over the frozen V3.7C engine
(``raceintel.counterfactual.engine``), which itself drives the frozen MC2
seam. Call direction is strictly::

    API/service -> runtime (this module) -> V3.7C engine -> MC2

This module never imports the API, the cache transport, the frontend,
V3.5, or V3.7D evaluation code. Cache artifacts are *built and validated*
here as deterministic scientific payloads, but the cache directory, the
cache-first policy and the live-compute opt-in live in the service layer
(``api.v3_7_counterfactual_service``), mirroring the proven V3.6F split
where the engine never touches the cache.

Simulator-conditional outcomes under controlled interventions. Nothing
here claims what would truly have happened, an optimal or recommended
strategy, or a causal real-world effect.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

from raceintel.counterfactual import contracts as C
from raceintel.counterfactual import engine as E
from raceintel.simulation.state import canonical_sha256

__all__ = [
    "RUNTIME_IDENTITY",
    "API_SCHEMA_VERSION",
    "CACHE_KEY_VERSION",
    "CACHE_SCHEMA_VERSION",
    "MANIFEST_SCHEMA_VERSION",
    "A_CONTRACT_IDENTITY",
    "B_CONTRACT_IDENTITY",
    "D_CARD_IDENTITY",
    "D_PROTOCOL_IDENTITY",
    "D_GATE",
    "E_STATUS",
    "DEFAULT_CACHE_DIR",
    "PRODUCTION_SIMULATION_COUNT",
    "PRODUCTION_MASTER_SEED",
    "RuntimeRequestError",
    "CacheMissError",
    "CacheInvalidError",
    "LiveDisabledError",
    "reject_kind",
    "build_plan",
    "build_comparison_key",
    "check_request_eligibility",
    "run_reference_vs_plan",
    "run_plan_vs_plan",
    "result_to_dict",
    "describe_state",
    "summarize_lifecycle",
    "build_cache_key",
    "cache_filename",
    "served_result_identity",
    "build_cache_artifact",
    "artifact_bytes",
    "artifact_hash",
    "write_cache_artifact",
    "read_cache_artifact",
    "validate_cached_artifact",
    "build_manifest",
]

#: Integration mechanics identity (not a scientific identity; A/B/C keep
#: their frozen identities below).
RUNTIME_IDENTITY = "v3.7f-counterfactual-runtime-v1"

#: Typed API contract version served by the F routes.
API_SCHEMA_VERSION = "v3.7f-counterfactual-api-v1"

#: Deterministic cache identity/schema versions (runtime-owned).
CACHE_KEY_VERSION = "v3.7f-counterfactual-cache-key-v1"
CACHE_SCHEMA_VERSION = "v3.7f-counterfactual-cache-v1"
MANIFEST_SCHEMA_VERSION = "v3.7f-counterfactual-manifest-v1"

#: Frozen scientific provenance (pinned equal to artifacts by test).
A_CONTRACT_IDENTITY = (
    "1735954212ec31286fede041639875610003a09cf817177e22cc908e3fcb0a12")
B_CONTRACT_IDENTITY = (
    "1865537503136ed3d8603e53741902c320df9387222655b38eef51640294e970")
D_CARD_IDENTITY = (
    "96debc6392c79019abedc3a51c7c26fb1536e97cabb3fed3136c43ed7c2b19c3")
D_PROTOCOL_IDENTITY = (
    "e4a6101c7267f2db9f85c76bcc07c17ed01c7f85de4a6481f94ab0941634c570")
D_GATE = "REFINEMENT_NOT_WARRANTED"
E_STATUS = "SKIPPED_BY_V3.7D_GATE"

#: Production configuration (single source: frozen B/C contracts).
PRODUCTION_SIMULATION_COUNT = C.PRODUCTION_SIMULATION_COUNT
PRODUCTION_MASTER_SEED = C.DEFAULT_MASTER_SEED

_REPOS_ROOT = Path(__file__).resolve().parents[2]

#: Default on-disk cache location (overridable via
#: V3_7_COUNTERFACTUAL_CACHE_DIR).
DEFAULT_CACHE_DIR = (
    _REPOS_ROOT / "runtime_artifacts" / "v3_7_counterfactual_cache")

#: Intervention payload keys admitted by ``build_plan``. Anything else
#: (historical-future smuggling, recommendation scores, ...) fails closed.
ADMITTED_INTERVENTION_FIELDS = frozenset({
    "target_driver_id", "kind", "lap_offset_n", "requested_compound",
})

#: Methodological labels served with every supported response.
LIMITATIONS = (
    "simulator-conditional outcomes under controlled interventions; "
    "not what would truly have happened; no optimal/recommended strategy; "
    "no causal real-world effect; compound-specific pace differentiation "
    "is limited/absent per frozen MC2 (compound is an intervention "
    "parameter, not a pace-effect claim); multi-driver plans propagate "
    "through joint ordering only (no pit-box stacking, traffic-battle, "
    "or team-order model)")


class RuntimeRequestError(ValueError):
    """A malformed F request (maps to 422; never coerced)."""

    def __init__(self, reason: str, detail: str = ""):
        super().__init__(detail or reason)
        self.reason = reason
        self.detail = detail or reason


class CacheMissError(RuntimeError):
    """No cache artifact exists for the requested comparison identity."""


class CacheInvalidError(RuntimeError):
    """A cache artifact failed validation (never served)."""


class LiveDisabledError(RuntimeError):
    """Live engine execution is disabled in this runtime (cache-only)."""


def reject_kind(kind: str) -> None:
    """Fail closed on any non-admitted executable intervention kind."""
    if kind not in C.INTERVENTION_KINDS:
        raise RuntimeRequestError(
            "unsupported_intervention_kind",
            f"kind must be one of {list(C.INTERVENTION_KINDS)} "
            f"(rejected kinds fail closed), got {kind!r}")


def _decision_lap(state, driver_id: str) -> int:
    for entry in state.drivers:
        if entry.driver_id == driver_id:
            return entry.lap_number
    raise RuntimeRequestError(
        "target_not_present",
        f"target {driver_id!r} not in factual roster")


def build_plan(state, *, target_driver_ids, interventions):
    """Build a canonical ``CounterfactualPlan`` from admitted user choices.

    Canonicalization (before identity): targets sorted (primary target is
    the canonically first, so input order never affects plan identity,
    cache identity, or science); identical duplicate interventions
    deduplicated per the B conflict matrix (DEDUPLICATE verdict).
    Anything outside ``ADMITTED_INTERVENTION_FIELDS`` fails closed here,
    before any identity is computed.

    The plan carries no rival: rival is a comparison-level choice owned
    by the caller (frozen B COMPARISON semantics rule on rival/target
    conflicts with an explicit unsupported verdict, never silent
    science). At most 8 interventions per plan (structural cost bound;
    D used at most 2).
    """
    targets = tuple(target_driver_ids or ())
    if not targets:
        raise RuntimeRequestError(
            "invalid_plan", "plan needs at least one target_driver_id")
    if len(set(targets)) != len(targets):
        raise RuntimeRequestError(
            "conflicting_targets",
            f"duplicate target_driver_id in {list(targets)!r}")
    roster = set(state.roster_driver_ids)
    for target in targets:
        if target not in roster:
            raise RuntimeRequestError(
                "target_not_present",
                f"target {target!r} not in factual roster")
    items = list(interventions or [])
    if not items:
        raise RuntimeRequestError(
            "invalid_plan", "plan needs at least one intervention")
    if len(items) > 8:
        raise RuntimeRequestError(
            "too_many_interventions",
            "at most 8 interventions per plan")
    seen = set()
    built = []
    for raw in items:
        if not isinstance(raw, dict):
            raise RuntimeRequestError(
                "invalid_plan",
                f"interventions must be objects, got {raw!r}")
        unknown = set(raw) - ADMITTED_INTERVENTION_FIELDS
        if unknown:
            raise RuntimeRequestError(
                "forbidden_plan_field",
                f"intervention carries forbidden fields {sorted(unknown)!r}")
        target = raw.get("target_driver_id")
        if target not in targets:
            raise RuntimeRequestError(
                "conflicting_targets",
                f"intervention target {target!r} not in plan targets "
                f"{list(targets)!r}")
        kind = raw.get("kind", "PIT_IN_N_LAPS")
        reject_kind(kind)
        compound = raw.get("requested_compound", "SAMPLED")
        if compound is None:
            compound = "SAMPLED"
        if compound not in C.SUPPORTED_REQUESTED_COMPOUNDS:
            raise RuntimeRequestError(
                "invalid_compound",
                f"requested_compound must be one of "
                f"{list(C.SUPPORTED_REQUESTED_COMPOUNDS)}, "
                f"got {compound!r}")
        n = raw.get("lap_offset_n")
        if type(n) is not int or n < 1:
            raise RuntimeRequestError(
                "invalid_trigger",
                f"lap_offset_n must be a positive plain int (N >= 1), "
                f"got {n!r}")
        key = (target, kind, n, compound)
        if key in seen:
            continue  # B conflict matrix: identical duplicates collapse
        seen.add(key)
        built.append(C.ScheduledIntervention(
            target_driver_id=target, kind=kind, lap_offset_n=n,
            requested_compound=compound,
            decision_lap=_decision_lap(state, target),
            decision_state_identity=state.identity()))
    covered = {t for (t, _, _, _) in seen}
    missing = [t for t in targets if t not in covered]
    if missing:
        raise RuntimeRequestError(
            "conflicting_targets",
            f"plan targets without interventions: {missing!r}")
    # NOTE: rival == target is NOT rejected here: plans carry no rival
    # (comparison-level choice). Frozen B COMPARISON semantics own that
    # verdict (engine eligibility returns an explicit unsupported
    # RIVAL_NOT_PRESENT result, never silent science).
    try:
        return C.CounterfactualPlan(
            target_driver_ids=tuple(sorted(targets)),
            interventions=tuple(built),
            rival_driver_id=None)
    except C.CounterfactualPlanError as exc:
        raise RuntimeRequestError("invalid_plan", str(exc)) from exc


def check_request_eligibility(state, plan, *, rival_driver_id=None):
    """Frozen B eligibility hierarchy (STATE/INTERVENTION/PLAN/COMPARISON)."""
    return E.check_eligibility(
        state, plan, rival_driver_id=rival_driver_id)


def run_reference_vs_plan(*, state, parameters, config, assumptions,
                          plan, rival_driver_id=None, chunk_size=None):
    """REFERENCE_VS_PLAN via the frozen V3.7C engine (no reorientation)."""
    return E.compare_reference_vs_plan(
        state=state, parameters=parameters, config=config,
        assumptions=assumptions, plan=plan,
        rival_driver_id=rival_driver_id, chunk_size=chunk_size)


def run_plan_vs_plan(*, state, parameters, config, assumptions,
                     plan_a, plan_b, rival_driver_id=None, chunk_size=None):
    """PLAN_VS_PLAN via the frozen V3.7C engine (BASE=A, ALT=B)."""
    return E.compare_plan_vs_plan(
        state=state, parameters=parameters, config=config,
        assumptions=assumptions, plan_a=plan_a, plan_b=plan_b,
        rival_driver_id=rival_driver_id, chunk_size=chunk_size)


def result_to_dict(result) -> dict:
    """Plain-dict view of an engine result (supported or unsupported)."""
    if hasattr(result, "to_dict"):
        return result.to_dict()
    return dict(result)


def describe_state(state) -> dict:
    """Cheap factual availability description (never simulates).

    Only T-factual facts: roster, per-driver decision lap (own lap at T),
    remaining laps, eligible N range (N <= remaining - 1), factual
    compounds. No historical future, no future strategy, no results.
    """
    drivers = []
    for entry in state.drivers:
        remaining = int(state.scheduled_laps) - int(entry.lap_number)
        n_max = max(0, remaining - 1)
        drivers.append({
            "driver_id": entry.driver_id,
            "position": entry.position,
            "decision_lap": int(entry.lap_number),
            "remaining_laps": remaining,
            "eligible_n_min": 1 if n_max >= 1 else None,
            "eligible_n_max": n_max if n_max >= 1 else None,
            "eligible": n_max >= 1,
            "compound": entry.compound,
            "status": (entry.status.value
                       if hasattr(entry.status, "value")
                       else str(entry.status)),
        })
    drivers = sorted(drivers, key=lambda d: d["driver_id"])
    multi_stop = any(d["eligible_n_max"] is not None
                     and d["eligible_n_max"] >= 2 for d in drivers)
    return {
        "state_identity": state.identity(),
        "race_id": state.race_id,
        "season": state.season,
        "scheduled_laps": int(state.scheduled_laps),
        "leader_laps_done": int(state.leader_laps_done),
        "drivers": drivers,
        "eligible_targets": [d["driver_id"] for d in drivers
                             if d["eligible"]],
        "supported_compounds": list(C.SUPPORTED_REQUESTED_COMPOUNDS),
        "comparison_forms": list(C.COMPARISON_FORMS),
        "multi_stop_capable": multi_stop,
        "multi_driver_capable": len(drivers) >= 2,
        "rival_candidates": [d["driver_id"] for d in drivers],
    }


def build_comparison_key(*, state_identity: str, comparison_form: str,
                          base_identity: str, alternative_identity: str,
                          rival_driver_id: str | None,
                          parameter_identity: str,
                          config_identity: str) -> dict:
    """Canonical comparison key dict (cheap; never simulates).

    Returns the frozen ``PlanComparisonKey`` payload plus its ``identity``.
    Raises ``RuntimeRequestError`` for unsupported forms or identical
    base/alternative. Production count/seed are bound by construction
    (no caller override exists at any layer).
    """
    try:
        key = C.PlanComparisonKey(
            key_version=C.COMPARISON_KEY_VERSION,
            comparison_form=comparison_form,
            state_identity=state_identity,
            base_identity=base_identity,
            alternative_identity=alternative_identity,
            simulator_identity=E.MC2_IDENTITY,
            parameter_identity=parameter_identity,
            simulation_count=PRODUCTION_SIMULATION_COUNT,
            master_seed=PRODUCTION_MASTER_SEED,
            outcome_schema_version=C.OUTCOME_SCHEMA_VERSION,
            rival_driver_id=rival_driver_id)
    except C.CounterfactualPlanError as exc:
        raise RuntimeRequestError("invalid_comparison", str(exc)) from exc
    # NOTE: the key dict stays exactly the frozen engine key fields (its
    # identity must equal the engine result's comparison_identity).
    # config_identity binds one layer up: in the cache key and in the
    # stored result payload (both validated on read).
    payload = key.to_dict()
    payload["identity"] = key.identity()
    return payload


def summarize_lifecycle(schedule_outcomes) -> dict:
    """Deterministic lifecycle counts per arm (B/C vocabulary preserved).

    EXECUTED/INERT/SUPERSEDED/CANCELLED/TERMINAL/INVALID are never
    collapsed: SUPERSEDED stays distinct from failure, cancellation stays
    visible. Same projection serves live and cached paths (parity).
    """
    summary = {}
    sched = schedule_outcomes or {}
    for arm in ("base", "alternative"):
        counts: dict = {}
        for sim in sched.get(arm, []):
            events = sim.get("events", []) if isinstance(sim, dict) else []
            for event in events:
                status = event.get("status") if isinstance(event, dict) \
                    else None
                if status is not None:
                    counts[status] = counts.get(status, 0) + 1
        summary[arm] = dict(sorted(counts.items()))
    return summary


def build_cache_key(*, state_identity: str, comparison_form: str,
                    base_identity: str, alternative_identity: str,
                    primary_target_driver_id: str,
                    rival_driver_id: str | None,
                    parameter_identity: str, config_identity: str,
                    simulation_count: int, master_seed: int) -> str:
    """Deterministic scientific cache identity (no volatile inputs).

    Binds state, comparison form, base/alternative identities, primary
    target, rival, simulation config, frozen count/seed, and the full
    A/B/C/outcome-schema provenance. Never binds display labels, request
    field order, timestamps, or machine paths. Semantically identical
    (permuted) plans share plan identities, hence share cache keys.
    """
    if simulation_count != PRODUCTION_SIMULATION_COUNT:
        raise CacheInvalidError(
            f"cache binds production count {PRODUCTION_SIMULATION_COUNT}, "
            f"got {simulation_count!r}")
    if master_seed != PRODUCTION_MASTER_SEED:
        raise CacheInvalidError(
            f"cache binds production seed {PRODUCTION_MASTER_SEED}, "
            f"got {master_seed!r}")
    return canonical_sha256({
        "key_version": CACHE_KEY_VERSION,
        "runtime_identity": RUNTIME_IDENTITY,
        "v37a_contract_identity": A_CONTRACT_IDENTITY,
        "v37b_contract_identity": B_CONTRACT_IDENTITY,
        "v37c_engine_identity": E.ENGINE_IDENTITY,
        "outcome_schema_version": C.OUTCOME_SCHEMA_VERSION,
        "mc2_identity": E.MC2_IDENTITY,
        "state_identity": state_identity,
        "comparison_form": comparison_form,
        "base_identity": base_identity,
        "alternative_identity": alternative_identity,
        "primary_target_driver_id": primary_target_driver_id,
        "rival_driver_id": rival_driver_id,
        "parameter_identity": parameter_identity,
        "config_identity": config_identity,
        "simulation_count": simulation_count,
        "master_seed": master_seed,
    })


def cache_filename(cache_key: str) -> str:
    """Hex-only artifact filename (path traversal impossible)."""
    if (len(cache_key) != 64
            or any(ch not in "0123456789abcdef" for ch in cache_key)):
        raise CacheInvalidError(f"non-canonical cache key {cache_key!r}")
    return f"v3_7cf_{cache_key}.json"


def served_result_identity(scientific: dict) -> str:
    """Recompute the served scientific identity (transport never enters).

    Covers the full scientific payload (aggregates, deltas, pair
    accounting, schedule evidence, provenance). The caller strips the
    previously stored ``served_result_identity`` before recomputing.
    """
    return canonical_sha256(scientific)


def build_cache_artifact(*, cache_key: str, comparison_key: dict,
                         result_dict: dict, request_meta: dict) -> dict:
    """Wrap a live engine result as a deterministic cache artifact."""
    if result_dict.get("comparison_identity") != comparison_key.get(
            "identity"):
        raise ValueError("comparison identity mismatch (refusing cache)")
    scientific = dict(result_dict)
    scientific["served_result_identity"] = served_result_identity(
        result_dict)
    return {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "cache_key_version": CACHE_KEY_VERSION,
        "cache_key": cache_key,
        "runtime_identity": RUNTIME_IDENTITY,
        "comparison_key": comparison_key,
        "result": scientific,
        "request": request_meta,
    }


def artifact_bytes(artifact: dict) -> bytes:
    """Canonical artifact serialization (stable field order)."""
    return json.dumps(artifact, sort_keys=True, indent=2).encode("utf-8")


def artifact_hash(artifact: dict) -> str:
    return hashlib.sha256(artifact_bytes(artifact)).hexdigest()


def write_cache_artifact(cache_dir, artifact: dict):
    """Atomic, resume-safe artifact write (validated shape before write)."""
    path = Path(cache_dir) / cache_filename(artifact["cache_key"])
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_bytes(artifact_bytes(artifact))
    os.replace(tmp, path)
    return path


def read_cache_artifact(cache_dir, cache_key: str) -> dict:
    """Load one artifact by key (hex-only filename; miss is explicit)."""
    path = Path(cache_dir) / cache_filename(cache_key)
    try:
        raw = path.read_bytes()
    except FileNotFoundError as exc:
        raise CacheMissError(
            f"no cached counterfactual result for {cache_key[:12]}...") \
            from exc
    try:
        artifact = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as exc:
        raise CacheInvalidError(
            f"malformed cache artifact {path.name}") from exc
    return artifact


def validate_cached_artifact(artifact: dict, *, cache_key: str,
                             state_identity: str, comparison_form: str,
                             base_identity: str, alternative_identity: str,
                             primary_target_driver_id: str,
                             rival_driver_id: str | None,
                             parameter_identity: str, config_identity: str,
                             simulation_count: int,
                             master_seed: int) -> dict:
    """Fail-closed validation of one cache artifact (never serve stale).

    Corrupt or mismatched payloads raise ``CacheInvalidError``; the
    service then fails closed (or falls through to explicitly enabled
    live computation, per runtime policy). Stale/mismatched science is
    never silently served.
    """
    if not isinstance(artifact, dict):
        raise CacheInvalidError("artifact must be a JSON object")
    if artifact.get("cache_schema_version") != CACHE_SCHEMA_VERSION:
        raise CacheInvalidError(
            "schema mismatch: "
            f"{artifact.get('cache_schema_version')!r}")
    if artifact.get("cache_key") != cache_key:
        raise CacheInvalidError("cache key mismatch")
    key = artifact.get("comparison_key")
    if not isinstance(key, dict):
        raise CacheInvalidError("artifact lacks comparison key")
    for field, expected in (
            ("key_version", C.COMPARISON_KEY_VERSION),
            ("comparison_form", comparison_form),
            ("state_identity", state_identity),
            ("base_identity", base_identity),
            ("alternative_identity", alternative_identity),
            ("simulator_identity", E.MC2_IDENTITY),
            ("parameter_identity", parameter_identity),
            ("simulation_count", simulation_count),
            ("master_seed", master_seed),
            ("outcome_schema_version", C.OUTCOME_SCHEMA_VERSION),
            ("rival_driver_id", rival_driver_id)):
        if key.get(field) != expected:
            raise CacheInvalidError(
                f"comparison-key mismatch on {field}")
    if key.get("identity") != canonical_sha256(
            {k: v for k, v in key.items() if k != "identity"}):
        raise CacheInvalidError("comparison-key identity mismatch (corrupt)")
    stored = artifact.get("result")
    if not isinstance(stored, dict):
        raise CacheInvalidError("artifact lacks result payload")
    # Top-level engine fields (parameter/config identities are attached
    # by the service at cache-build time; the engine nests the rest in
    # provenance, checked below).
    for field, expected in (
            ("supported", True),
            ("comparison_form", comparison_form),
            ("comparison_identity", key["identity"]),
            ("base_identity", base_identity),
            ("alternative_identity", alternative_identity),
            ("parameter_identity", parameter_identity),
            ("config_identity", config_identity),
            ("target_driver_id", primary_target_driver_id),
            ("rival_driver_id", rival_driver_id)):
        if stored.get(field) != expected:
            raise CacheInvalidError(
                f"provenance mismatch on {field}")
    provenance = stored.get("provenance") or {}
    for field, expected in (
            ("v37a_contract_identity", A_CONTRACT_IDENTITY),
            ("v37b_contract_identity", B_CONTRACT_IDENTITY),
            ("engine_identity", E.ENGINE_IDENTITY),
            ("mc2_identity", E.MC2_IDENTITY),
            ("state_identity", state_identity),
            ("simulation_count", simulation_count),
            ("master_seed", master_seed),
            ("outcome_schema_version", C.OUTCOME_SCHEMA_VERSION),
            ("comparison_form", comparison_form)):
        if provenance.get(field) != expected:
            raise CacheInvalidError(
                f"scientific provenance mismatch on {field}")
    if stored.get("served_result_identity") != served_result_identity(
            {k: v for k, v in stored.items()
             if k != "served_result_identity"}):
        raise CacheInvalidError("result identity mismatch (corrupt)")
    return stored


def build_manifest(entries: list, *, status: str = "fixture") -> dict:
    """Deterministic cache manifest (ordering fixed, no local paths)."""
    ordered = sorted(
        entries,
        key=lambda e: (e.get("race_id", ""), e.get("anchor_lap_number", 0),
                       str(e.get("anchor_state_time_s", 0.0)),
                       e.get("comparison_form", ""),
                       e.get("alternative_identity", "")))
    return {
        "manifest_schema": MANIFEST_SCHEMA_VERSION,
        "status": status,
        "runtime_identity": RUNTIME_IDENTITY,
        "v37a_contract_identity": A_CONTRACT_IDENTITY,
        "v37b_contract_identity": B_CONTRACT_IDENTITY,
        "v37c_engine_identity": E.ENGINE_IDENTITY,
        "outcome_schema_version": C.OUTCOME_SCHEMA_VERSION,
        "comparison_key_version": C.COMPARISON_KEY_VERSION,
        "mc2_identity": E.MC2_IDENTITY,
        "reference_kind": C.REFERENCE_KIND,
        "simulation_count": PRODUCTION_SIMULATION_COUNT,
        "master_seed": PRODUCTION_MASTER_SEED,
        "entry_count": len(ordered),
        "entries": ordered,
    }
