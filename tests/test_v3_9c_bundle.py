"""V3.9C runtime bundle + API tests (fixture-backed, no MC2 execution)."""

import hashlib
import json
import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]

from api.v2_consensus_service import (  # noqa: E402
    ConsensusUnsupportedError,
    FixtureProvider,
    V2ConsensusService,
)
from api.v2_uncertainty_service import V2UncertaintyService  # noqa: E402
from raceintel.consensus import contracts as C  # noqa: E402
from raceintel.consensus import metrics as M  # noqa: E402
from raceintel.uncertainty import bundle as B  # noqa: E402

ANCHOR = {"race_id": "2022-r03-R", "anchor_lap_number": 2,
          "anchor_state_time_s": None}
FX = ROOT / "results" / "v3" / "v3_8f" / "fixtures"
V38 = "15df86b864fa552c69c4b7a53e22f1fc3b4c4ca1"
VTAG = "v3.8-model-simulation-consensus"
PERF = "32466c436845ee02c3af79ce08d1c102b9d91384"
PTAG = "v3.8-mc2-performance"


def _load(name):
    return json.loads((ROOT / "results" / "v3" / "v3_9c" / name).read_text())


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout.strip()


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _service(**kw):
    return V2UncertaintyService(
        model_provider=FixtureProvider(
            fixture_dir=kw.get("dir", FX), arm="model",
            source=C.SourceId.V3_1B_LOGISTIC),
        simulation_provider=FixtureProvider(
            fixture_dir=kw.get("dir", FX), arm="simulation",
            source=C.SourceId.MC2_E))


def _client(svc=None):
    from api.config import get_serving_config
    from api.main import create_app
    from api.v2_uncertainty_service import get_v2_uncertainty_service
    app = create_app(get_serving_config())
    app.dependency_overrides[get_v2_uncertainty_service] = \
        lambda: svc or _service()
    return TestClient(app)


# --- provenance ---


def test_tags_intact():
    assert _git("rev-list", "-n", "1", VTAG) == V38
    assert _git("rev-list", "-n", "1", PTAG) == PERF


def test_performance_freeze_provenance():
    touched = [ln.split()[-1] for ln in
               _git("status", "--porcelain=v1").splitlines()
               if ln.startswith(("M ", " M"))]
    for f in ("raceintel/simulation/mc2/kernel.py",
              "raceintel/simulation/mc2/residuals.py",
              "raceintel/simulation/mc2_batch.py"):
        assert f not in touched, f


def test_runtime_source_registry():
    assert B.CALCULATION_VERSION == "v3.9c-uncertainty-bundle-v1"
    out = _service().compare(ANCHOR)
    assert out["sources"]["model"]["source"] == "V3_1B_LOGISTIC"
    assert out["sources"]["simulation"]["source"] == "MC2_E"
    assert "XGB" not in json.dumps(out["sources"])
    assert "ensemble" not in json.dumps(out["sources"]).lower()


def test_family_labels_and_no_normalization():
    out = _service().compare(ANCHOR)
    assert out["sources"]["model"]["probability_family"] == \
        "INDEPENDENT_BINARY"
    assert out["sources"]["simulation"]["probability_family"] == \
        "MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY"
    for d in out["drivers"]:
        if d["status"] == "AVAILABLE":
            assert d["disagreement"]["p_model_family"] == \
                "INDEPENDENT_BINARY"


def test_exact_alignment_and_no_silent_drop():
    out = _service().compare(ANCHOR)
    assert len(out["drivers"]) == 20
    assert out["field"]["n_common_drivers"] == 20

    class PartialSim(FixtureProvider):
        def fetch(self, anchor):
            probs, meta = super().fetch(anchor)
            probs.pop("sainz")
            return probs, meta

    svc = V2UncertaintyService(
        model_provider=FixtureProvider(
            fixture_dir=FX, arm="model",
            source=C.SourceId.V3_1B_LOGISTIC),
        simulation_provider=PartialSim(
            fixture_dir=FX, arm="simulation", source=C.SourceId.MC2_E))
    o = svc.compare(ANCHOR)
    assert len(o["drivers"]) == 20
    missing = [d for d in o["drivers"] if d["status"] == "MISSING_SOURCE"]
    assert len(missing) == 1 and missing[0]["driver_id"] == "sainz"
    assert missing[0]["disagreement"] is None


def test_u1_metric_parity_live():
    art = _load("u1_runtime_parity.json")
    assert art["verdict"] == "EXACT"
    assert art["max_abs_diff_vs_frozen_metric_defs"] == 0.0
    out = _service().compare(ANCHOR)
    assert out["metric_implementation"] == "v3.8c-consensus-metrics-v1"


def test_u1_orientation():
    out = _service().compare(ANCHOR)
    d = next(x for x in out["drivers"] if x["status"] == "AVAILABLE")
    g = d["disagreement"]
    assert g["signed_gap"] == g["p_simulation"] - g["p_model"]
    assert g["absolute_gap"] == abs(g["signed_gap"])


def test_u2_parity_and_identity():
    art = _load("u2_runtime_parity.json")
    assert art["verdict"] == "EXACT"
    out = _service().compare(ANCHOR)
    for d in out["drivers"]:
        s = d["monte_carlo_sampling"]
        assert s["p_hat"] == s["success_count_k"] / s["valid_futures_n"]
        assert s["precision_label"] == "FINITE_MC_SAMPLING_CONTEXT_ONLY"


def test_k0_available_zero_and_boundaries():
    lo, hi = M.wilson_interval(0.0, 5000)
    assert lo == 0.0 and hi > 0.0
    lo, hi = M.wilson_interval(1.0, 5000)
    assert hi == 1.0 and lo < 1.0
    out = _service().compare(ANCHOR)
    for d in out["drivers"]:
        assert d["status"] in ("AVAILABLE", "MISSING_SOURCE",
                               "INSUFFICIENT_SIMULATIONS")
        if d["status"] == "AVAILABLE":
            assert d["monte_carlo_sampling"]["valid_futures_n"] > 0


def test_missing_is_not_zero():
    art = _load("alignment_validation.json")
    assert art["partial_arm_behavior"].startswith("explicit MISSING_SOURCE")
    assert art["prohibited"] and "zero filling" in art["prohibited"]


def test_u3_explicitly_unavailable():
    out = _service().compare(ANCHOR)
    u3 = out["simulator_sensitivity"]
    assert u3["status"] == "PROVENANCE_UNAVAILABLE"
    assert u3["executable"] is False
    assert "reason" in u3 and u3["reason"]
    assert "lower" not in u3 and "upper" not in u3


def test_no_confidence_fusion_or_winner():
    out = _service().compare(ANCHOR)
    blob = json.dumps(out).lower()
    for f in ("confidence_score", "uncertainty_score", "trust_score",
              "reliability_score", "combined_score", "overall_confidence",
              "certainty_percentage", "preferred_source", "winner_source",
              "trusted_source", "recommended_probability",
              "consensus_probability"):
        assert f not in blob, f
    assert "average" not in blob


def test_no_high_medium_low():
    out = _service().compare(ANCHOR)
    assert "HIGH" not in json.dumps(out) and "MEDIUM" not in json.dumps(out)


def test_2025_refusal():
    c = _client()
    r = c.post("/v2/uncertainty/compare",
               json={"race_id": "2025-r01-R", "anchor_lap_number": 1})
    assert r.status_code == 422
    assert r.json()["reason"] == "STATE_NOT_AVAILABLE"
    r = c.get("/v2/uncertainty/availability",
              params={"race_id": "2025-r01-R", "anchor_lap_number": 1})
    assert r.status_code == 200


def test_temporal_boundary_no_future_fetch():
    import inspect
    from api import v2_uncertainty_service as S
    src = inspect.getsource(S)
    body = "\n".join(ln for ln in src.splitlines()
                     if "__future__" not in ln)
    assert "anchor_lap_number + 1" not in body
    assert "future" not in body.lower().replace("futures_n", "")


def test_cache_first_single_resolution():
    svc = _service()
    a = dict(ANCHOR)
    svc.compare(a)
    assert (svc._model.fetch_count, svc._simulation.fetch_count) == (1, 1)
    again = svc.compare(a)
    assert (svc._model.fetch_count, svc._simulation.fetch_count) == (1, 1)
    assert again == svc.compare(a)


def test_availability_behavior():
    c = _client()
    r = c.get("/v2/uncertainty/availability",
              params={"race_id": "2022-r03-R", "anchor_lap_number": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["comparison"] == "COMPARABLE"
    assert body["simulator_sensitivity"] == "PROVENANCE_UNAVAILABLE"


def test_compare_endpoint_shape():
    c = _client()
    r = c.post("/v2/uncertainty/compare",
               json={"race_id": "2022-r03-R", "anchor_lap_number": 2})
    assert r.status_code == 200
    body = r.json()
    assert body["schema_version"] == "v3.9c-uncertainty-bundle-v1"
    assert len(body["drivers"]) == 20
    assert body["simulator_sensitivity"]["executable"] is False
    assert body["provenance"]["u3_gate"] == "U3_NOT_EXECUTABLE"


def test_malformed_missing_corrupt():
    import tempfile
    c = _client()
    assert c.post("/v2/uncertainty/compare",
                  json={"race_id": "2022-r03-R"}).status_code == 422
    r = c.post("/v2/uncertainty/compare",
               json={"race_id": "2022-r03-R", "anchor_lap_number": 999})
    assert r.status_code == 422
    with tempfile.TemporaryDirectory() as td:
        (Path(td) / "2022-r03-R__lap2.json").write_text("{corrupt")
        bad = V2UncertaintyService(
            model_provider=FixtureProvider(
                fixture_dir=Path(td), arm="model",
                source=C.SourceId.V3_1B_LOGISTIC),
            simulation_provider=FixtureProvider(
                fixture_dir=Path(td), arm="simulation",
                source=C.SourceId.MC2_E))
        c2 = _client(bad)
        assert c2.post("/v2/uncertainty/compare",
                       json={"race_id": "2022-r03-R",
                             "anchor_lap_number": 2}).status_code == 503


def test_provenance_fields():
    c = _client()
    body = c.post("/v2/uncertainty/compare",
                  json={"race_id": "2022-r03-R",
                        "anchor_lap_number": 2}).json()
    assert body["state"]["state_id"] == "2022-r03-R|lap2"
    assert body["provenance"]["metric_implementation"] == \
        "v3.8c-consensus-metrics-v1"
    assert body["provenance"]["contract"] == "V3.9A"


def test_api_schema_no_score_fields():
    import api.v2_uncertainty_schemas as S
    blob = json.dumps({k: sorted(v.model_fields)
                       for k, v in vars(S).items()
                       if isinstance(v, type)}).lower()
    for f in ("confidence", "trust", "combined", "winner", "fused"):
        assert f not in blob, f


def test_no_public_science_controls():
    import inspect
    from api import v2_uncertainty_routes as R
    from api import v2_uncertainty_service as S
    blob = inspect.getsource(R) + inspect.getsource(S)
    for tok in ("master_seed", "simulation_count", "rho=",
                "sensitivity range", "worker_count", "workers=",
                "n_futures"):
        assert tok not in blob, tok
    import api.v2_uncertainty_schemas as SM
    assert "seed" not in json.dumps(
        {k: sorted(v.model_fields) for k, v in vars(SM).items()
         if isinstance(v, type)}).lower()


def test_no_frontend_changes():
    out = _git("status", "--porcelain=v1")
    fe = [ln for ln in out.splitlines()
          if "/frontend/" in ln or "frontend/" in ln.split()[-1]]
    # V3.9D carve-out (product UI stage only): exactly the /uncertainty
    # route, the uncertainty feature modules, and the one-line nav entry.
    # Any other frontend dirt still fails; the API-only boundary is
    # asserted below, not weakened.
    # V3.10I reconciliation: V3.10A-H pit-wall product admitted exactly
    # (workspace substrate, shell, replay calm-announcement prop, expert
    # prefill, read-only telemetry client; frozen science untouched).
    allowed_fe = (
        "frontend/app/uncertainty/",
        "frontend/features/uncertainty/",
        "frontend/components/shell/CommandBar.tsx",
        "frontend/app/pit-wall/",
        "frontend/features/pit-wall/",
        "frontend/features/workspace/",
        "frontend/components/shell/AppShell.tsx",
        "frontend/features/counterfactuals/components/CounterfactualView.tsx",
        "frontend/features/strategy/components/Strategy2View.tsx",
        "frontend/lib/v2.ts",
        "frontend/features/replay/components/SpatialTrackPanel.tsx",
        # C5 post-V3: exact C5 client-consolidation files
        # (v2.ts + uncertainty clients above).
        "frontend/lib/http",
        "frontend/lib/spatial.ts",
        "frontend/lib/api.ts",
        "frontend/features/consensus/lib/consensusClient.ts",
    )
    unexpected = [ln for ln in fe
                  if not ln.split()[-1].startswith(allowed_fe)]
    assert unexpected == [], unexpected
    assert (ROOT / "frontend" / "app" / "uncertainty").exists()
    client = (ROOT / "frontend" / "features" / "uncertainty" / "lib"
              / "uncertaintyClient.ts").read_text()
    assert "/v2/uncertainty/availability" in client
    assert "/v2/uncertainty/compare" in client
    view = (ROOT / "frontend" / "features" / "uncertainty" / "components"
            / "UncertaintyView.tsx").read_text()
    assert "raceintel" not in view and "results/v3" not in view


def test_overhead_negligible():
    art = _load("performance_overhead.json")
    assert art["p90_ms"] < 5.0
    assert art["verdict"].startswith("NEGLIGIBLE")


def test_scientific_card_identity():
    card = _load("scientific_card.json")
    ident = card.pop("card_identity")
    assert hashlib.sha256(_canon(card)).hexdigest() == ident
    assert card["classification"] == "RUNTIME_UNCERTAINTY_BUNDLE_VALIDATED"


def test_v39c_pathology_all_zero():
    counts = _load("validation.json")["pathology"]
    assert set(counts) == {f"V3.9C-P{i}" for i in range(1, 31)}
    bad = {k: v for k, v in counts.items() if v != 0}
    assert bad == {}, bad
    import api.v2_uncertainty_service as S
    import inspect
    assert "confidence_score" not in inspect.getsource(S)
    assert "preferred_source" not in inspect.getsource(S)
