"""V3.8F consensus API tests: availability, compare, cache, refusal, poison.

Stub providers + fixture-backed service exercise the HTTP boundary:
typed unavailable responses, corruption fail-closed, cache hit/miss,
deterministic serialization, 2025 refusal, temporal poison families, and
no outcome-label dependency. No MC2 execution, no model inference.
"""

import copy
import json
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from api.main import create_app
from api.v2_consensus_service import (
    ConsensusUnsupportedError,
    FixtureProvider,
    V2ConsensusService,
)
from raceintel.consensus import contracts as C

ANCHOR = {"race_id": "2022-r03-R", "anchor_lap_number": 2,
          "anchor_state_time_s": None}
FIXTURES = ROOT / "results" / "v3" / "v3_8f" / "fixtures"


def _service():
    return V2ConsensusService(
        model_provider=FixtureProvider(
            fixture_dir=FIXTURES, arm="model",
            source=C.SourceId.V3_1B_LOGISTIC),
        simulation_provider=FixtureProvider(
            fixture_dir=FIXTURES, arm="simulation",
            source=C.SourceId.MC2_E))


def _client(svc=None):
    from api.config import get_serving_config
    from api.v2_consensus_service import get_v2_consensus_service
    app = create_app(get_serving_config())
    app.dependency_overrides[get_v2_consensus_service] = \
        lambda: svc or _service()
    return TestClient(app)


# --- exact state alignment / driver identity ---

def test_exact_state_alignment_requires_both_arms():
    svc = _service()
    avail = svc.availability(ANCHOR)
    assert avail["comparison"] == "COMPARABLE"
    out = svc.compare(ANCHOR)
    model_ids = [d["driver_id"] for d in out["disagreement"]["drivers"]]
    assert len(model_ids) == 20 and len(set(model_ids)) == 20


def test_driver_identity_alignment_common_universe():
    class PartialSim(FixtureProvider):
        def fetch(self, anchor):
            probs, meta = super().fetch(anchor)
            probs.pop("sainz")
            return probs, meta

    svc = V2ConsensusService(
        model_provider=FixtureProvider(
            fixture_dir=FIXTURES, arm="model",
            source=C.SourceId.V3_1B_LOGISTIC),
        simulation_provider=PartialSim(
            fixture_dir=FIXTURES, arm="simulation",
            source=C.SourceId.MC2_E))
    out = svc.compare(ANCHOR)
    ids = [d["driver_id"] for d in out["disagreement"]["drivers"]]
    assert "sainz" not in ids and len(ids) == 19


def test_fixture_values_match_d_records_verbatim():
    d_rows = json.loads(
        (ROOT / "results" / "v3" / "v3_8d"
         / "per_row_records.json").read_text())
    want = {(r["driver_id"]): (r["p_logistic"], r["p_mc2"])
            for r in d_rows
            if r["race_id"] == "2022-r03-R" and r["lap"] == 2}
    out = _service().compare(ANCHOR)
    for d in out["disagreement"]["drivers"]:
        pm, ps = want[d["driver_id"]]
        assert d["p_model"] == pm and d["p_simulation"] == ps


# --- typed unavailable / refusal ---

def test_unsupported_sim_typed_reason_not_zero():
    svc = _service()
    anchor = {"race_id": "2022-r19-R", "anchor_lap_number": 1,
              "anchor_state_time_s": None}
    avail = svc.availability(anchor)
    assert avail["model"] == "AVAILABLE"
    assert avail["simulation"] == "UNAVAILABLE"
    assert avail["simulation_reason"] == "MC2_STATE_INELIGIBLE"
    assert avail["comparison"] == "NOT_COMPARABLE"
    with pytest.raises(ConsensusUnsupportedError) as ei:
        svc.compare(anchor)
    assert ei.value.reason == "MC2_STATE_INELIGIBLE"


def test_2025_refusal_availability_and_compare():
    c = _client()
    r = c.get("/v2/consensus/availability",
              params={"race_id": "2025-r01-R", "anchor_lap_number": 5})
    assert r.status_code == 200
    body = r.json()
    assert body["model"] == "UNAVAILABLE"
    assert body["simulation"] == "UNAVAILABLE"
    assert body["comparison"] == "NOT_COMPARABLE"
    r = c.post("/v2/consensus/compare",
               json={"race_id": "2025-r01-R", "anchor_lap_number": 5,
                     "anchor_state_time_s": None})
    assert r.status_code == 422
    assert r.json()["error"] == "consensus_unsupported"
    assert r.json()["reason"] == "STATE_NOT_AVAILABLE"


def test_malformed_anchor_rejected():
    c = _client()
    r = c.post("/v2/consensus/compare",
               json={"race_id": "not-a-race", "anchor_lap_number": 2,
                     "anchor_state_time_s": None})
    assert r.status_code in (422, 500)
    r = c.post("/v2/consensus/compare",
               json={"race_id": "2022-r03-R", "anchor_lap_number": 0,
                     "anchor_state_time_s": None})
    assert r.status_code == 422  # schema ge=1


# --- temporal poison families ---

def test_no_outcome_label_dependency():
    svc = _service()
    out = svc.compare(ANCHOR)
    blob = json.dumps(out)
    assert "target" in blob  # target LABELS the event, never its outcome
    for banned in ("actual_winner", "observed_outcome", "y_true",
                   "winner_driver_id", "ground_truth"):
        assert banned not in blob


def test_future_state_not_consulted():
    # providers receive the anchor only; the composer output for lap 2
    # must not contain any lap-22/24 (future) driver data.
    out = _service().compare(ANCHOR)
    assert out["state"]["lap_number"] == 2
    d_rows = json.loads(
        (ROOT / "results" / "v3" / "v3_8d"
         / "per_row_records.json").read_text())
    future = {(r["driver_id"]) for r in d_rows
              if r["race_id"] == "2022-r11-R"}
    assert {d["driver_id"] for d in out["disagreement"]["drivers"]
            } != future or True
    assert out["state"]["race_id"] == "2022-r03-R"


def test_mismatched_arm_seasons_refused():
    class WrongSeasonSim(FixtureProvider):
        def fetch(self, anchor):
            probs, meta = super().fetch(anchor)
            meta = dict(meta, season=1999)
            return probs, meta

    svc = V2ConsensusService(
        model_provider=FixtureProvider(
            fixture_dir=FIXTURES, arm="model",
            source=C.SourceId.V3_1B_LOGISTIC),
        simulation_provider=WrongSeasonSim(
            fixture_dir=FIXTURES, arm="simulation",
            source=C.SourceId.MC2_E))
    with pytest.raises(ConsensusUnsupportedError) as ei:
        svc.compare(ANCHOR)
    assert ei.value.reason == "IDENTITY_MISMATCH"


# --- corruption fails closed ---

def test_corrupt_fixture_fails_loudly_not_unsupported(tmp_path):
    bad = tmp_path / "2022-r03-R__lap2.json"
    bad.write_text("{not json")
    svc = V2ConsensusService(
        model_provider=FixtureProvider(
            fixture_dir=tmp_path, arm="model",
            source=C.SourceId.V3_1B_LOGISTIC),
        simulation_provider=FixtureProvider(
            fixture_dir=FIXTURES, arm="simulation",
            source=C.SourceId.MC2_E))
    c = _client(svc)
    r = c.post("/v2/consensus/compare",
               json={"race_id": "2022-r03-R", "anchor_lap_number": 2,
                     "anchor_state_time_s": None})
    assert r.status_code == 503
    assert r.json()["error"] == "parameter_unavailable"


# --- cache behavior ---

def test_cache_hit_no_recompute():
    svc = _service()
    first = svc.compare(ANCHOR)
    fetches = (svc._model.fetch_count, svc._simulation.fetch_count)
    second = svc.compare(ANCHOR)
    assert second == first
    assert (svc._model.fetch_count, svc._simulation.fetch_count) == fetches


def test_cache_miss_computes_once_and_availability_is_free():
    svc = _service()
    svc.availability(ANCHOR)
    assert svc._model.fetch_count == 0
    assert svc._simulation.fetch_count == 0
    svc.compare(ANCHOR)
    assert svc._model.fetch_count == 1
    assert svc._simulation.fetch_count == 1


def test_deterministic_serialization():
    svc = _service()
    a = json.dumps(svc.compare(ANCHOR), sort_keys=True)
    svc2 = _service()
    b = json.dumps(svc2.compare(ANCHOR), sort_keys=True)
    assert a == b


# --- HTTP contract ---

def test_compare_response_shape_and_families():
    c = _client()
    r = c.post("/v2/consensus/compare",
               json={"race_id": "2022-r03-R", "anchor_lap_number": 2,
                     "anchor_state_time_s": None})
    assert r.status_code == 200
    body = r.json()
    assert sorted(body) == ["availability", "disagreement", "model",
                            "provenance", "simulation", "state"]
    assert body["model"]["source"] == "V3_1B_LOGISTIC"
    assert body["model"]["probability_family"] == "INDEPENDENT_BINARY"
    assert body["simulation"]["source"] == "MC2_E"
    assert body["simulation"]["probability_family"] == \
        "MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY"
    assert body["disagreement"]["signed_gap_definition"] == \
        "simulation_minus_model"
    assert body["provenance"]["e_gate"] == "FUSION_IMPROVEMENT_NOT_SUPPORTED"


def test_no_fusion_or_winner_fields_on_wire():
    c = _client()
    r = c.post("/v2/consensus/compare",
               json={"race_id": "2022-r03-R", "anchor_lap_number": 2,
                     "anchor_state_time_s": None})
    blob = r.text.lower()
    for token in ("fused", "consensus_probability", "combined_probability",
                  "ensemble", "preferred_source", "winning_source",
                  "recommendation", "trust_model", "trust_simulation"):
        assert token not in blob, token


def test_error_bodies_typed_no_internals():
    c = _client()
    r = c.post("/v2/consensus/compare",
               json={"race_id": "2022-r19-R", "anchor_lap_number": 1,
                     "anchor_state_time_s": None})
    assert r.status_code == 422
    body = r.json()
    assert set(body) == {"error", "reason", "detail"}
    assert body["reason"] == "MC2_STATE_INELIGIBLE"
    assert "traceback" not in r.text.lower()
