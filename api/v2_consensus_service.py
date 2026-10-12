"""V2 consensus product service (V3.8F).

Cache-first MODEL / SIMULATION / DISAGREEMENT comparison over an exact
factual RaceState(T). Read-only orchestration: cheap availability first,
exact-key in-memory result cache, provider fetch on miss.

Providers take the anchor ONLY. There are no client-settable science
controls anywhere in this module: no seed, no simulation count, no
configuration. No combination path exists. No source-winner
logic exists. 2025 is refused explicitly (REVEALED_HOLDOUT /
PRODUCT_EXCLUDED). D/E ground truth never enters this module.
"""

from __future__ import annotations

import functools
import json
from pathlib import Path

from raceintel.consensus import contracts as C
from raceintel.consensus import product as P
from raceintel.race_state.race_state_reconstruction import RaceNotFoundError

_REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = (_REPO_ROOT / "results" / "v3" / "v3_8f" / "fixtures")

PROVENANCE = {
    "a_contract": "d0b8785a01347580125b38b311984c793c012352ce3ff175cfa3504379b9a67b",  # noqa: E501
    "b_contract": "d212803f7ed7e8a8563abdd5b7686326e7094d810f415fa1468117541dfbfde7",  # noqa: E501
    "c_contract": "07cf1ddd9708eaea2280b1d46492d972234f68c77cf3a59cbf412f638e3a74a8",  # noqa: E501
    "d_protocol": "9cbe85de7c8f0553a098a9a03d016beed80159c785b566c312502d3bf10f2ed1",  # noqa: E501
    "d_card_corrected": "67f97c185ca8cc687b59b376bc5a48776e9290d6463a05653fa1a6e18a298985",  # noqa: E501
    "d_gate_corrected": "FUSION_RESEARCH_WARRANTED",
    "e_protocol": "dbe6a565d5a6fa688dbb8e0b3a1be05bad71457777cd2e312f9c164219b128dd",  # noqa: E501
    "e_card_corrected": "ec6578de410f1ec8f6975e1cf4a2575aa4984967804b22a0b583fe2740948357",  # noqa: E501
    "e_gate": "FUSION_IMPROVEMENT_NOT_SUPPORTED",
    "evidence_note": "D observed Logistic x MC2 disagreement/complementarity; E gate FUSION_IMPROVEMENT_NOT_SUPPORTED; MODEL, SIMULATION, and descriptive DISAGREEMENT only.",  # noqa: E501
}


class ConsensusUnknownStateError(ValueError):
    """Well-formed race but no exact anchor state (422 unknown_state)."""


class ConsensusUnsupportedError(ValueError):
    """Well-formed exact state a source cannot serve (422, typed reason)."""

    def __init__(self, reason: str, detail: str):
        super().__init__(detail)
        self.reason = reason
        self.detail = detail


class ConsensusArtifactUnavailableError(RuntimeError):
    """Fixture/cache artifact missing or corrupt (503, fail loudly)."""


class SourceProvider:
    """Anchor-in, natives-out. No science parameters on the interface."""

    def supports(self, anchor: dict) -> bool:
        raise NotImplementedError

    def fetch(self, anchor: dict) -> tuple:
        """Return (probs dict, meta dict). Corruption raises loudly."""
        raise NotImplementedError


class FixtureProvider(SourceProvider):
    """Deterministic demonstration/research-fixture provider (cache-first).

    Serves exactly the anchors stored under the fixture directory; every
    value is a verbatim frozen research record, never fabricated. One file
    per anchor carries both arms, each nullable: a null arm means that
    source is unsupported for the state (explicit reason recorded).
    """

    def __init__(self, fixture_dir: Path | None = None, arm: str = "model",
                 source: C.SourceId = C.SourceId.V3_1B_LOGISTIC):
        if arm not in ("model", "simulation"):
            raise ValueError(f"invalid arm: {arm!r}")
        self._dir = Path(fixture_dir) if fixture_dir else FIXTURE_DIR
        self._arm = arm
        self._source = source
        self.fetch_count = 0

    def _path(self, anchor: dict) -> Path:
        return (self._dir
                / f"{anchor['race_id']}__lap{anchor['anchor_lap_number']}.json")  # noqa: E501

    def _doc(self, anchor: dict) -> dict | None:
        path = self._path(anchor)
        if not path.is_file():
            return None
        try:
            return json.loads(path.read_text())
        except (OSError, ValueError) as exc:
            raise ConsensusArtifactUnavailableError(
                f"consensus fixture corrupt: {path.name}: {exc}")

    def supports(self, anchor: dict) -> bool:
        doc = self._doc(anchor)
        return doc is not None and doc.get(self._arm) is not None

    def unsupported_reason(self, anchor: dict) -> str:
        doc = self._doc(anchor)
        if doc is not None and doc.get(f"{self._arm}_reason"):
            return doc[f"{self._arm}_reason"]
        return C.ReasonCode.SOURCE_NOT_AVAILABLE.value

    def fetch(self, anchor: dict) -> tuple:
        doc = self._doc(anchor)
        arm_doc = (doc.get(self._arm) if doc else None)
        if not arm_doc:
            raise ConsensusUnsupportedError(
                self.unsupported_reason(anchor),
                f"{self._source.value} has no fixture arm for "
                f"{anchor['race_id']} lap {anchor['anchor_lap_number']}")
        probs = {d["driver_id"]: float(d["probability"])
                 for d in arm_doc["drivers"]}
        meta = {"valid_trials": {d["driver_id"]: int(d["valid_trials"])
                                 for d in arm_doc["drivers"]},
                "stage": doc["state"].get("stage"),
                "season": int(doc["state"]["season"])}
        self.fetch_count += 1
        return probs, meta


class V2ConsensusService:
    """Read-only consensus orchestration (providers injected)."""

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
            return {"race_id": anchor["race_id"],
                    "anchor_lap_number": anchor["anchor_lap_number"],
                    "anchor_state_time_s": anchor.get("anchor_state_time_s"),
                    **P.assess_availability(
                        season=season,
                        model_status=C.SupportStatus.UNAVAILABLE,
                        simulation_status=C.SupportStatus.UNAVAILABLE)}
        model_ok = self._model.supports(anchor)
        sim_ok = self._simulation.supports(anchor)
        return {"race_id": anchor["race_id"],
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

    def compare(self, anchor: dict) -> dict:
        """Full comparison; exact-key cache hit returns without recompute."""
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
        model_probs, model_meta = self._model.fetch(anchor)
        sim_probs, sim_meta = self._simulation.fetch(anchor)
        if model_meta["season"] != sim_meta["season"]:
            raise ConsensusUnsupportedError(
                C.ReasonCode.IDENTITY_MISMATCH.value,
                "model/simulation season mismatch for "
                f"{anchor['race_id']}")
        composed = P.compose(
            race_id=anchor["race_id"],
            lap_number=anchor["anchor_lap_number"],
            state_time_s=anchor.get("anchor_state_time_s"),
            stage=model_meta.get("stage"),
            season=season,
            model_probs=model_probs,
            simulation_probs=sim_probs,
            valid_trials=sim_meta["valid_trials"])
        avail = self.availability(anchor)
        payload = {**composed, "availability": avail,
                   "provenance": dict(PROVENANCE)}
        self._cache[key] = payload
        return payload


@functools.lru_cache(maxsize=1)
def _cached_consensus_service() -> V2ConsensusService:
    return V2ConsensusService(
        model_provider=FixtureProvider(
            arm="model", source=C.SourceId.V3_1B_LOGISTIC),
        simulation_provider=FixtureProvider(
            arm="simulation", source=C.SourceId.MC2_E))


def get_v2_consensus_service() -> V2ConsensusService:
    """FastAPI dependency (mirrors the simulation-service convention)."""
    return _cached_consensus_service()
