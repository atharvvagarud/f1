"""V2 counterfactual runtime service (V3.7F integration).

Narrow product orchestration over the frozen V3.7C engine via the F
runtime adapter (``raceintel.counterfactual.runtime``), reusing the
frozen Phase-4 exact-anchor authority, the frozen through-2024
parameters, and the MC2-backed execution path::

    exact anchor -> RaceState (Phase-4) -> SimulationState (R2 adapter)
    -> frozen through-2024 parameters -> canonical plan/comparison
    -> cache lookup -> validated cached result (CACHE-FIRST)
    -> explicitly enabled live path: V3.7C engine, 5000 futures

Design rules (V3.7F):
- No counterfactual science lives here: no trigger semantics, no CRN
  policy, no delta estimand, no aggregation, no lifecycle rules. All of
  that is frozen in ``counterfactual.contracts`` / ``.engine`` / MC2.
- Production simulation count (5000) and root seed (20240101) are fixed
  by contract. The public request schema carries neither field; this
  service binds both by construction.
- CACHE-FIRST: every comparison resolves its deterministic cache
  identity before touching the engine. Live computation requires
  explicit server-side opt-in (constructor flag or the
  ``V3_7_COUNTERFACTUAL_ALLOW_LIVE=1`` environment switch). There is no
  client mode/live parameter: the request cannot authorize expensive
  execution. Cache miss with live disabled is an explicit 404, never a
  silent fallback to fabricated numbers.
- Corrupt/mismatched artifacts are never served: with live enabled the
  service falls through to a live run; otherwise it reports 503.
- Only supported results are cached. Unsupported (supported=false)
  outcomes carry EMPTY metrics, never zeros/NaN/fallbacks.
- Per-index outcomes never leave this process: cache and API carry
  aggregates, paired deltas and lifecycle summaries only.
"""

from __future__ import annotations

import functools
import json
import logging
import os
import time
from pathlib import Path

import pandas as pd

from api.observability import LOGGER_NAME
from raceintel.counterfactual import contracts as C
from raceintel.counterfactual import runtime as R
from raceintel.race_state import race_state as RS
from raceintel.race_state.race_state_reconstruction import RaceNotFoundError
from raceintel.simulation import (
    Assumptions,
    SimulationConfig,
    SimulationParameterSet,
)
from raceintel.simulation.adapter import (
    SimulationUnavailableError,
    from_race_state,
)
from raceintel.simulation.engine import SimulationUnsupportedError

_REPOS_ROOT = Path(__file__).resolve().parents[1]

#: Server-side live-compute opt-in (explicit; default is cache-only).
LIVE_ENV_VAR = "V3_7_COUNTERFACTUAL_ALLOW_LIVE"
CACHE_DIR_ENV_VAR = "V3_7_COUNTERFACTUAL_CACHE_DIR"


def _allow_live_from_env() -> bool:
    return os.environ.get(LIVE_ENV_VAR, "0") == "1"


def _provenance() -> dict:
    return {
        "v37a_contract_identity": R.A_CONTRACT_IDENTITY,
        "v37b_contract_identity": R.B_CONTRACT_IDENTITY,
        "v37c_engine_identity": R.E.ENGINE_IDENTITY,
        "mc2_identity": R.E.MC2_IDENTITY,
        "outcome_schema_version": C.OUTCOME_SCHEMA_VERSION,
        "comparison_key_version": C.COMPARISON_KEY_VERSION,
        "reference_kind": C.REFERENCE_KIND,
        "simulation_count": R.PRODUCTION_SIMULATION_COUNT,
        "master_seed": R.PRODUCTION_MASTER_SEED,
        "validated_by": f"{R.D_CARD_IDENTITY}",
        "evaluation_gate": R.D_GATE,
        "v37e_status": R.E_STATUS,
        "runtime_identity": R.RUNTIME_IDENTITY,
        "api_schema": R.API_SCHEMA_VERSION,
    }


class CounterfactualService:
    """Reusable counterfactual product runtime (cache-first + live)."""

    def __init__(self, states: pd.DataFrame, reconstructor,
                 served_race_ids, parameters: SimulationParameterSet, *,
                 cache_dir: Path | str | None = None,
                 allow_live: bool = False,
                 chunk_size: int | None = None):
        if not isinstance(states, pd.DataFrame):
            raise ValueError(f"states must be a DataFrame, got {type(states)}")
        if not isinstance(parameters, SimulationParameterSet):
            raise TypeError(
                "parameters must be a SimulationParameterSet, "
                f"got {type(parameters)}")
        self._states = states
        self._reconstructor = reconstructor
        self._served = tuple(served_race_ids)
        self._parameters = parameters
        self._cache_dir = Path(cache_dir) if cache_dir is not None \
            else Path(os.environ.get(CACHE_DIR_ENV_VAR,
                                     str(R.DEFAULT_CACHE_DIR)))
        self._allow_live = bool(allow_live) or _allow_live_from_env()
        self._chunk_size = chunk_size

    @property
    def race_ids(self) -> tuple:
        return self._served

    @property
    def cache_dir(self) -> Path:
        return self._cache_dir

    @property
    def allow_live(self) -> bool:
        return self._allow_live

    def _require_race(self, race_id: str) -> None:
        if race_id not in self._served:
            raise RaceNotFoundError(race_id)

    def _reconstruct(self, *, race_id: str, anchor_driver_id: str,
                     anchor_lap_number: int, anchor_state_time_s: float):
        self._require_race(race_id)
        anchor = RS.AnchorObservation(
            race_id=race_id, anchor_driver_id=anchor_driver_id,
            anchor_lap_number=anchor_lap_number,
            anchor_state_time_s=anchor_state_time_s)
        return self._reconstructor.reconstruct(anchor)

    def _request_identities(self, *, sim_state):
        config = SimulationConfig(
            simulation_count=R.PRODUCTION_SIMULATION_COUNT,
            master_seed=R.PRODUCTION_MASTER_SEED,
            pit_dynamics_enabled=True)
        return config, {
            "state_identity": sim_state.identity(),
            "parameter_identity":
                self._parameters.parameter_identity().identity(),
            "config_identity": config.identity(),
        }

    # -- availability ----------------------------------------------------

    def describe_availability(self, *, race_id: str, anchor_driver_id: str,
                              anchor_lap_number: int,
                              anchor_state_time_s: float) -> dict:
        """Cheap factual availability (never simulates)."""
        base = {
            "api_schema": R.API_SCHEMA_VERSION,
            "race_id": race_id,
            "anchor_driver_id": anchor_driver_id,
            "anchor_lap_number": anchor_lap_number,
            "anchor_state_time_s": anchor_state_time_s,
            "provenance": _provenance(),
            "limitations": R.LIMITATIONS,
            "live_enabled": self._allow_live,
        }
        try:
            race_state = self._reconstruct(
                race_id=race_id, anchor_driver_id=anchor_driver_id,
                anchor_lap_number=anchor_lap_number,
                anchor_state_time_s=anchor_state_time_s)
            sim_state = from_race_state(race_state)
        except SimulationUnavailableError as exc:
            base.update({
                "supported": False, "level": "STATE",
                "reason_code": exc.reason,
                "human_reason": str(exc),
                "state_identity": None,
                "season": None, "scheduled_laps": None,
                "leader_laps_done": None, "drivers": [],
                "eligible_targets": [],
                "supported_compounds": list(
                    C.SUPPORTED_REQUESTED_COMPOUNDS),
                "comparison_forms": list(C.COMPARISON_FORMS),
                "multi_stop_capable": False,
                "multi_driver_capable": False,
                "rival_candidates": [],
                "cached_comparison_identities": [],
            })
            return base
        factual = R.describe_state(sim_state)
        eligible = bool(factual["eligible_targets"])
        base.update({
            "supported": eligible,
            "level": None if eligible else "STATE",
            "reason_code": None if eligible else "NO_ELIGIBLE_TARGETS",
            "human_reason": ("" if eligible else
                             "no factual driver admits N>=1 "
                             "(N <= remaining - 1)"),
            "cached_comparison_identities":
                self._cached_identities_for_state(
                    factual["state_identity"]),
            **factual,
        })
        return base

    def _cached_identities_for_state(self, state_identity: str) -> list:
        found = []
        cache_dir = Path(self._cache_dir)
        if not cache_dir.is_dir():
            return found
        for path in sorted(cache_dir.glob("v3_7cf_*.json")):
            try:
                artifact = json.loads(path.read_bytes().decode("utf-8"))
                key = artifact.get("comparison_key") or {}
                if key.get("state_identity") == state_identity:
                    found.append(key.get("identity", ""))
            except (ValueError, UnicodeDecodeError, OSError):
                continue
        return sorted(i for i in found if i)

    # -- comparison ------------------------------------------------------

    def run_comparison(self, *, race_id: str, anchor_driver_id: str,
                       anchor_lap_number: int, anchor_state_time_s: float,
                       comparison_form: str = "REFERENCE_VS_PLAN",
                       base_plan: dict | None = None,
                       alternative_plan: dict,
                       rival_driver_id: str | None = None) -> dict:
        """Cache-first comparison (live only on explicit server opt-in)."""
        total_started = time.perf_counter()
        race_state = self._reconstruct(
            race_id=race_id, anchor_driver_id=anchor_driver_id,
            anchor_lap_number=anchor_lap_number,
            anchor_state_time_s=anchor_state_time_s)
        reconstructed = time.perf_counter()
        try:
            sim_state = from_race_state(race_state)
        except SimulationUnavailableError as exc:
            return self._unsupported_payload(
                race_id=race_id, anchor_driver_id=anchor_driver_id,
                anchor_lap_number=anchor_lap_number,
                anchor_state_time_s=anchor_state_time_s,
                level="STATE", reason_code=exc.reason,
                human_reason=str(exc), state_identity=None,
                plan_identity=None, comparison_identity=None,
                execution_source=None, cache_key=None,
                runtime={
                    "reconstruction_s": reconstructed - total_started,
                    "adaptation_s": time.perf_counter() - reconstructed,
                    "simulation_s": 0.0, "analysis_s": 0.0,
                    "total_s": time.perf_counter() - total_started,
                })
        adapted = time.perf_counter()
        if comparison_form not in C.COMPARISON_FORMS:
            raise R.RuntimeRequestError(
                "unsupported_comparison_form",
                f"comparison_form must be one of "
                f"{list(C.COMPARISON_FORMS)}, got {comparison_form!r}")
        if comparison_form == "PLAN_VS_PLAN" and base_plan is None:
            raise R.RuntimeRequestError(
                "missing_base_plan",
                "PLAN_VS_PLAN requires base_plan")
        if comparison_form == "REFERENCE_VS_PLAN" and base_plan is not None:
            raise R.RuntimeRequestError(
                "unexpected_base_plan",
                "REFERENCE_VS_PLAN forbids base_plan")

        def _plan(payload: dict, name: str):
            if not isinstance(payload, dict):
                raise R.RuntimeRequestError(
                    "invalid_plan", f"{name} must be an object")
            return R.build_plan(
                sim_state,
                target_driver_ids=payload.get("target_driver_ids"),
                interventions=payload.get("interventions"))

        alt = _plan(alternative_plan, "alternative_plan")
        base = (_plan(base_plan, "base_plan")
                if base_plan is not None else None)
        for plan in ([base] if base is not None else []) + [alt]:
            eligible, level, reason, human = R.check_request_eligibility(
                sim_state, plan, rival_driver_id=rival_driver_id)
            if not eligible:
                return self._unsupported_payload(
                    race_id=race_id,
                    anchor_driver_id=anchor_driver_id,
                    anchor_lap_number=anchor_lap_number,
                    anchor_state_time_s=anchor_state_time_s,
                    level=level, reason_code=reason,
                    human_reason=human,
                    state_identity=sim_state.identity(),
                    plan_identity=plan.identity(),
                    comparison_identity=None,
                    execution_source=None, cache_key=None,
                    runtime={
                        "reconstruction_s": reconstructed - total_started,
                        "adaptation_s": adapted - reconstructed,
                        "simulation_s": 0.0, "analysis_s": 0.0,
                        "total_s": time.perf_counter() - total_started,
                    })
        if (base is not None and base.target_driver_ids[0]
                != alt.target_driver_ids[0]):
            return self._unsupported_payload(
                race_id=race_id, anchor_driver_id=anchor_driver_id,
                anchor_lap_number=anchor_lap_number,
                anchor_state_time_s=anchor_state_time_s,
                level="COMPARISON", reason_code="INVALID_PLAN",
                human_reason="plan-vs-plan requires the same primary "
                             "target",
                state_identity=sim_state.identity(),
                plan_identity=alt.identity(), comparison_identity=None,
                execution_source=None, cache_key=None,
                runtime={
                    "reconstruction_s": reconstructed - total_started,
                    "adaptation_s": adapted - reconstructed,
                    "simulation_s": 0.0, "analysis_s": 0.0,
                    "total_s": time.perf_counter() - total_started,
                })

        config, ids = self._request_identities(sim_state=sim_state)
        base_identity = (C.REFERENCE_KIND if base is None
                         else base.identity())
        key = R.build_comparison_key(
            state_identity=ids["state_identity"],
            comparison_form=comparison_form,
            base_identity=base_identity,
            alternative_identity=alt.identity(),
            rival_driver_id=rival_driver_id,
            parameter_identity=ids["parameter_identity"],
            config_identity=ids["config_identity"])
        cache_key = R.build_cache_key(
            state_identity=ids["state_identity"],
            comparison_form=comparison_form,
            base_identity=base_identity,
            alternative_identity=alt.identity(),
            primary_target_driver_id=alt.target_driver_ids[0],
            rival_driver_id=rival_driver_id,
            parameter_identity=ids["parameter_identity"],
            config_identity=ids["config_identity"],
            simulation_count=R.PRODUCTION_SIMULATION_COUNT,
            master_seed=R.PRODUCTION_MASTER_SEED)

        try:
            artifact = R.read_cache_artifact(self._cache_dir, cache_key)
            stored = R.validate_cached_artifact(
                artifact, cache_key=cache_key,
                state_identity=ids["state_identity"],
                comparison_form=comparison_form,
                base_identity=base_identity,
                alternative_identity=alt.identity(),
                primary_target_driver_id=alt.target_driver_ids[0],
                rival_driver_id=rival_driver_id,
                parameter_identity=ids["parameter_identity"],
                config_identity=ids["config_identity"],
                simulation_count=R.PRODUCTION_SIMULATION_COUNT,
                master_seed=R.PRODUCTION_MASTER_SEED)
        except R.CacheMissError:
            stored = None
        except R.CacheInvalidError:
            if not self._allow_live:
                raise
            stored = None  # fall through to enabled live computation
            artifact = None
        if stored is not None:
            simulated = time.perf_counter()
            payload = self._supported_payload(
                race_id=race_id, anchor_driver_id=anchor_driver_id,
                anchor_lap_number=anchor_lap_number,
                anchor_state_time_s=anchor_state_time_s,
                scientific=stored, execution_source="cache",
                cache_key=cache_key,
                target_driver_ids=list(alt.target_driver_ids),
                runtime={
                    "reconstruction_s": reconstructed - total_started,
                    "adaptation_s": adapted - reconstructed,
                    "simulation_s": simulated - adapted,
                    "analysis_s": 0.0,
                    "total_s": simulated - total_started,
                })
            self._log_compare(cache_key, key["identity"], True, None,
                              "cache", simulated - total_started)
            return payload

        if not self._allow_live:
            raise R.CacheMissError(
                f"no cached counterfactual result for "
                f"{cache_key[:12]}...; live computation is disabled in "
                f"this runtime")
        try:
            if base is None:
                result = R.run_reference_vs_plan(
                    state=sim_state, parameters=self._parameters,
                    config=config, assumptions=Assumptions(), plan=alt,
                    rival_driver_id=rival_driver_id,
                    chunk_size=self._chunk_size)
            else:
                result = R.run_plan_vs_plan(
                    state=sim_state, parameters=self._parameters,
                    config=config, assumptions=Assumptions(), plan_a=base,
                    plan_b=alt, rival_driver_id=rival_driver_id,
                    chunk_size=self._chunk_size)
        except (SimulationUnsupportedError, SimulationUnavailableError) \
                as exc:
            return self._unsupported_payload(
                race_id=race_id, anchor_driver_id=anchor_driver_id,
                anchor_lap_number=anchor_lap_number,
                anchor_state_time_s=anchor_state_time_s,
                level="STATE", reason_code=exc.reason,
                human_reason=str(exc),
                state_identity=sim_state.identity(),
                plan_identity=alt.identity(),
                comparison_identity=key["identity"],
                execution_source="live_engine", cache_key=cache_key,
                runtime={
                    "reconstruction_s": reconstructed - total_started,
                    "adaptation_s": adapted - reconstructed,
                    "simulation_s": time.perf_counter() - adapted,
                    "analysis_s": 0.0,
                    "total_s": time.perf_counter() - total_started,
                })
        simulated = time.perf_counter()
        scientific = R.result_to_dict(result)
        if not scientific.get("supported"):
            analyzed = time.perf_counter()
            payload = self._supported_payload(
                race_id=race_id, anchor_driver_id=anchor_driver_id,
                anchor_lap_number=anchor_lap_number,
                anchor_state_time_s=anchor_state_time_s,
                scientific=scientific, execution_source="live_engine",
                cache_key=cache_key,
                target_driver_ids=list(alt.target_driver_ids),
                runtime={
                    "reconstruction_s": reconstructed - total_started,
                    "adaptation_s": adapted - reconstructed,
                    "simulation_s": simulated - adapted,
                    "analysis_s": analyzed - simulated,
                    "total_s": analyzed - total_started,
                })
            self._log_compare(cache_key, key["identity"], False,
                              scientific.get("reason_code"), "live_engine",
                              analyzed - total_started)
            return payload
        scientific["parameter_identity"] = ids["parameter_identity"]
        scientific["config_identity"] = ids["config_identity"]
        artifact = R.build_cache_artifact(
            cache_key=cache_key, comparison_key=key,
            result_dict=scientific,
            request_meta={
                "race_id": race_id,
                "anchor_driver_id": anchor_driver_id,
                "anchor_lap_number": anchor_lap_number,
                "anchor_state_time_s": anchor_state_time_s,
                "comparison_form": comparison_form,
                "base_identity": base_identity,
                "alternative_identity": alt.identity(),
                "rival_driver_id": rival_driver_id,
                "master_seed": R.PRODUCTION_MASTER_SEED,
            })
        R.validate_cached_artifact(
            artifact, cache_key=cache_key,
            state_identity=ids["state_identity"],
            comparison_form=comparison_form,
            base_identity=base_identity,
            alternative_identity=alt.identity(),
            primary_target_driver_id=alt.target_driver_ids[0],
            rival_driver_id=rival_driver_id,
            parameter_identity=ids["parameter_identity"],
            config_identity=ids["config_identity"],
            simulation_count=R.PRODUCTION_SIMULATION_COUNT,
            master_seed=R.PRODUCTION_MASTER_SEED)
        R.write_cache_artifact(self._cache_dir, artifact)
        analyzed = time.perf_counter()
        payload = self._supported_payload(
            race_id=race_id, anchor_driver_id=anchor_driver_id,
            anchor_lap_number=anchor_lap_number,
            anchor_state_time_s=anchor_state_time_s,
            scientific=scientific, execution_source="live_engine",
            cache_key=cache_key,
            target_driver_ids=list(alt.target_driver_ids),
            runtime={
                "reconstruction_s": reconstructed - total_started,
                "adaptation_s": adapted - reconstructed,
                "simulation_s": simulated - adapted,
                "analysis_s": analyzed - simulated,
                "total_s": analyzed - total_started,
            })
        self._log_compare(cache_key, key["identity"], True, None,
                          "live_engine", analyzed - total_started)
        return payload

    # -- projection --------------------------------------------------------

    def _supported_payload(self, *, race_id: str, anchor_driver_id: str,
                           anchor_lap_number: int,
                           anchor_state_time_s: float, scientific: dict,
                           execution_source: str, cache_key: str,
                           target_driver_ids: list | None = None,
                           runtime: dict) -> dict:
        if not scientific.get("supported"):
            return self._unsupported_payload(
                race_id=race_id, anchor_driver_id=anchor_driver_id,
                anchor_lap_number=anchor_lap_number,
                anchor_state_time_s=anchor_state_time_s,
                level=scientific.get("level", "STATE"),
                reason_code=scientific.get(
                    "reason_code", "UNKNOWN_STATE"),
                human_reason=scientific.get("human_reason", ""),
                state_identity=scientific.get("state_identity"),
                plan_identity=scientific.get("plan_identity"),
                comparison_identity=scientific.get(
                    "comparison_identity"),
                execution_source=execution_source, cache_key=cache_key,
                runtime=runtime)
        provenance = dict(scientific.get("provenance") or {})
        provenance.update({
            "runtime_identity": R.RUNTIME_IDENTITY,
            "api_schema": R.API_SCHEMA_VERSION,
            "validated_by": R.D_CARD_IDENTITY,
            "evaluation_gate": R.D_GATE,
            "cache_schema_version": R.CACHE_SCHEMA_VERSION,
        })
        # The engine nests identities in provenance; the service attaches
        # parameter/config identities at cache-build time. Both shapes
        # project identically (live == cached parity).
        state_identity = (scientific.get("state_identity")
                          or provenance.get("state_identity"))
        return {
            "api_schema": R.API_SCHEMA_VERSION,
            "supported": True,
            "level": None, "reason_code": None, "human_reason": "",
            "comparison_form": scientific["comparison_form"],
            "comparison_identity": scientific["comparison_identity"],
            "base_identity": scientific["base_identity"],
            "alternative_identity": scientific["alternative_identity"],
            "state_identity": state_identity,
            "parameter_identity": scientific.get("parameter_identity"),
            "config_identity": scientific.get("config_identity"),
            "master_seed": scientific.get("master_seed",
                                          provenance.get("master_seed")),
            "simulation_count": scientific.get(
                "simulation_count",
                provenance.get("simulation_count")),
            "race_id": race_id,
            "anchor_driver_id": anchor_driver_id,
            "anchor_lap_number": anchor_lap_number,
            "anchor_state_time_s": anchor_state_time_s,
            "target_driver_ids": (list(target_driver_ids)
                                  if target_driver_ids is not None
                                  else [scientific["target_driver_id"]]),
            "primary_target_driver_id": scientific["target_driver_id"],
            "rival_driver_id": scientific["rival_driver_id"],
            "base_aggregate": scientific["base_aggregate"],
            "alternative_aggregate": scientific["alternative_aggregate"],
            "deltas": scientific["deltas"],
            "complete_pairs": scientific["complete_pairs"],
            "requested_pairs": scientific["requested_pairs"],
            "excluded_pairs": scientific["excluded_pairs"],
            "lifecycle_summary": R.summarize_lifecycle(
                scientific.get("schedule_outcomes")),
            "provenance": provenance,
            "limitations": R.LIMITATIONS,
            "execution_source": execution_source,
            "cache_key": cache_key,
            "runtime": runtime,
        }

    def _unsupported_payload(self, *, race_id: str, anchor_driver_id: str,
                             anchor_lap_number: int,
                             anchor_state_time_s: float, level: str,
                             reason_code: str, human_reason: str,
                             state_identity, plan_identity,
                             comparison_identity, execution_source,
                             cache_key, runtime: dict) -> dict:
        return {
            "api_schema": R.API_SCHEMA_VERSION,
            "supported": False,
            "level": level, "reason_code": reason_code,
            "human_reason": human_reason,
            "comparison_form": None, "comparison_identity":
                comparison_identity,
            "base_identity": None, "alternative_identity": plan_identity,
            "state_identity": state_identity,
            "parameter_identity": None, "config_identity": None,
            "master_seed": R.PRODUCTION_MASTER_SEED,
            "simulation_count": R.PRODUCTION_SIMULATION_COUNT,
            "race_id": race_id,
            "anchor_driver_id": anchor_driver_id,
            "anchor_lap_number": anchor_lap_number,
            "anchor_state_time_s": anchor_state_time_s,
            "target_driver_ids": [], "primary_target_driver_id": None,
            "rival_driver_id": None,
            "base_aggregate": None, "alternative_aggregate": None,
            "deltas": {},
            "complete_pairs": None, "requested_pairs": None,
            "excluded_pairs": None, "lifecycle_summary": {},
            "provenance": _provenance(),
            "limitations": R.LIMITATIONS,
            "execution_source": execution_source,
            "cache_key": cache_key,
            "runtime": runtime,
        }

    @staticmethod
    def _log_compare(cache_key: str, comparison_identity: str,
                     supported: bool, reason, source: str,
                     duration_s: float) -> None:
        logging.getLogger(LOGGER_NAME).info(json.dumps({
            "event": "counterfactual_compare",
            "cache_key_prefix": cache_key[:12],
            "comparison_identity_prefix": (comparison_identity or "")[:12],
            "supported": supported,
            "reason_code": reason,
            "execution_source": source,
            "duration_s": round(duration_s, 3),
        }))


def load_production_parameters(
        project_root=None) -> SimulationParameterSet:
    """Load the frozen through-2024 R3 artifact once (read-only)."""
    from api.v2_strategy_service import (
        StrategyParameterUnavailableError,
        load_production_parameters as _load,
    )
    try:
        return _load(project_root)
    except StrategyParameterUnavailableError as exc:
        from api.v2_strategy_service import (
            StrategyParameterUnavailableError as _E)
        raise _E(str(exc)) from exc


def build_counterfactual_service(
        v2_service, *, parameters: SimulationParameterSet | None = None,
        cache_dir: Path | str | None = None,
        allow_live: bool = False,
        chunk_size: int | None = None):
    """Share the loaded corpus/reconstructor read-only; build no model."""
    from api.v2_service import V2Service as _V2Service
    if not isinstance(v2_service, _V2Service):
        raise ValueError(
            f"v2_service must be a V2Service, got {type(v2_service)}")
    if parameters is None:
        parameters = load_production_parameters()
    return CounterfactualService(
        v2_service._states,  # noqa: SLF001 - shared read-only corpus
        v2_service._reconstructor,  # noqa: SLF001 - shared read-only index
        v2_service.race_ids, parameters, cache_dir=cache_dir,
        allow_live=allow_live, chunk_size=chunk_size)


@functools.lru_cache(maxsize=1)
def _cached_counterfactual_service() -> CounterfactualService:
    from api.v2_service import get_v2_service
    return build_counterfactual_service(get_v2_service())


def get_counterfactual_service() -> CounterfactualService:
    """FastAPI dependency: process-local lazy singleton (override in tests)."""
    return _cached_counterfactual_service()
