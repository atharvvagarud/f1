"""V3.9C uncertainty product service (thin orchestration over V3.8 seams).

Cache-first: providers are the frozen consensus FixtureProviders (model +
simulation arms of the same fixture records). Each source is fetched at most
once per uncertainty request; the exact-key cache serves repeats without any
refetch. No science controls on the interface (no seed/count/rho/arm/range/
workers). 2025 refused explicitly. No fusion, no source winner, no score.
"""

from __future__ import annotations

import functools
from pathlib import Path

from raceintel.consensus import contracts as C
from raceintel.consensus import product as P
from raceintel.race_state.race_state_reconstruction import RaceNotFoundError
from raceintel.uncertainty import bundle as B

from api.v2_consensus_service import (
    ConsensusArtifactUnavailableError,
    ConsensusUnknownStateError,
    ConsensusUnsupportedError,
    FixtureProvider,
    SourceProvider,
)

_REPO_ROOT = Path(__file__).resolve().parents[1]

PROVENANCE = {
    "uncertainty_calculation": B.CALCULATION_VERSION,
    "metric_implementation": "v3.8c-consensus-metrics-v1",
    "u3_gate": "U3_NOT_EXECUTABLE",
    "u3_gate_version": "v3.9b-u3-gate-v1",
    "contract": "V3.9A",
    "measurement": "V3.9B",
}

U3_AVAILABILITY = "PROVENANCE_UNAVAILABLE"


class V2UncertaintyService:
    """Read-only uncertainty orchestration (providers injected)."""

    def __init__(self, model_provider: SourceProvider,
                 simulation_provider: SourceProvider):
        self._model = model_provider
        self._simulation = simulation_provider
        self._cache: dict = {}

    @staticmethod
    def _key(anchor: dict) -> tuple:
        return (anchor["race_id"], anchor["anchor_lap_number"],
                anchor.get("anchor_state_time_s"))

    @staticmethod
    def _season_of(race_id: str) -> int:
        try:
            return int(str(race_id).split("-", 1)[0])
        except (ValueError, IndexError):
            raise ConsensusUnknownStateError(
                f"malformed race_id {race_id!r}")

    def availability(self, anchor: dict) -> dict:
        """Cheap availability only: never triggers expensive work."""
        season = self._season_of(anchor["race_id"])
        if season in P.PRODUCT_EXCLUDED_SEASONS:
            base = {"race_id": anchor["race_id"],
                    "anchor_lap_number": anchor["anchor_lap_number"],
                    "anchor_state_time_s": anchor.get("anchor_state_time_s"),
                    **P.assess_availability(
                        season=season,
                        model_status=C.SupportStatus.UNAVAILABLE,
                        simulation_status=C.SupportStatus.UNAVAILABLE)}
            return {**base, "simulator_sensitivity": U3_AVAILABILITY}
        model_ok = self._model.supports(anchor)
        sim_ok = self._simulation.supports(anchor)
        base = {"race_id": anchor["race_id"],
                "anchor_lap_number": anchor["anchor_lap_number"],
                "anchor_state_time_s": anchor.get("anchor_state_time_s"),
                **P.assess_availability(
                    season=season,
                    model_status=C.SupportStatus.AVAILABLE if model_ok
                    else C.SupportStatus.UNAVAILABLE,
                    simulation_status=C.SupportStatus.AVAILABLE if sim_ok
                    else C.SupportStatus.UNAVAILABLE,
                    model_reason=None if model_ok
                    else C.ReasonCode(
                        self._model.unsupported_reason(anchor)),
                    simulation_reason=None if sim_ok
                    else C.ReasonCode(
                        self._simulation.unsupported_reason(anchor)))}
        return {**base, "simulator_sensitivity": U3_AVAILABILITY}

    def compare(self, anchor: dict) -> dict:
        """Full bundle; exact-key cache hit returns without any refetch."""
        key = self._key(anchor)
        if key in self._cache:
            return self._cache[key]
        season = self._season_of(anchor["race_id"])
        if season in P.PRODUCT_EXCLUDED_SEASONS:
            raise ConsensusUnsupportedError(
                C.ReasonCode.STATE_NOT_AVAILABLE.value,
                f"{anchor['race_id']}: 2025 is REVEALED_HOLDOUT / "
                f"PRODUCT_EXCLUDED")
        if not self._model.supports(anchor):
            raise ConsensusUnsupportedError(
                C.ReasonCode.SOURCE_NOT_AVAILABLE.value,
                f"model unavailable for {anchor['race_id']} "
                f"lap {anchor['anchor_lap_number']}")
        if not self._simulation.supports(anchor):
            raise ConsensusUnsupportedError(
                self._simulation.unsupported_reason(anchor),
                f"simulation unavailable for {anchor['race_id']} "
                f"lap {anchor['anchor_lap_number']}")
        # Each source resolved exactly once per request (cache-first).
        model_probs, model_meta = self._model.fetch(anchor)
        sim_probs, sim_meta = self._simulation.fetch(anchor)
        if model_meta["season"] != sim_meta["season"]:
            raise ConsensusUnsupportedError(
                C.ReasonCode.IDENTITY_MISMATCH.value,
                "model/simulation season mismatch for "
                f"{anchor['race_id']}")
        payload = B.build_bundle(
            race_id=anchor["race_id"],
            lap_number=anchor["anchor_lap_number"],
            state_time_s=anchor.get("anchor_state_time_s"),
            stage=model_meta.get("stage"),
            season=season,
            model_probs=model_probs,
            sim_probs=sim_probs,
            valid_trials=sim_meta["valid_trials"])
        payload["availability"] = self.availability(anchor)
        payload["provenance"] = dict(PROVENANCE)
        self._cache[key] = payload
        return payload


@functools.lru_cache(maxsize=1)
def _cached_uncertainty_service() -> V2UncertaintyService:
    return V2UncertaintyService(
        model_provider=FixtureProvider(
            arm="model", source=C.SourceId.V3_1B_LOGISTIC),
        simulation_provider=FixtureProvider(
            arm="simulation", source=C.SourceId.MC2_E))


def get_v2_uncertainty_service() -> V2UncertaintyService:
    """FastAPI dependency (mirrors the consensus-service convention)."""
    return _cached_uncertainty_service()
