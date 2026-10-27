"""V3.9E uncertainty intelligence freeze tests (cheap, no MC2 execution).

Final programme gate: parent tags, A/B/C/D card identities, manifest
linkage, U1/U2/U3 taxonomy, source registry, boundary semantics, alignment,
temporal contract, 2025 exclusion, API surface, frontend boundary,
collection accounting, guard-reconciliation completeness. Fixture-backed
service calls only; production MC2 never runs here.
"""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

from api.v2_consensus_service import (  # noqa: E402
    ConsensusUnsupportedError,
    FixtureProvider,
)
from api.v2_uncertainty_service import V2UncertaintyService  # noqa: E402
from raceintel.consensus import contracts as C  # noqa: E402
from raceintel.uncertainty import bundle as B  # noqa: E402

V38 = "15df86b864fa552c69c4b7a53e22f1fc3b4c4ca1"
VTAG = "v3.8-model-simulation-consensus"
PERF = "32466c436845ee02c3af79ce08d1c102b9d91384"
PTAG = "v3.8-mc2-performance"
ANCHOR = {"race_id": "2022-r03-R", "anchor_lap_number": 2,
          "anchor_state_time_s": None}
# Collection provenance (history only, not an executable second pin):
# 5148 at V3.9C + 28 V3.9E freeze tests + 10 V3.10I ownership/API +
# 22 V3.11A forensics + 21 V3.11B reconstruction + 21 V3.11C
# track-forensics + 18 V3.11D VSC-model + 21 V3.11E evidence +
# 16 V3.11F freeze + 14 V3 Final = 5319. C7 derives the live
# expectation from the Tier-1 selector instead of maintaining this
# arithmetic a second time (see _runner_expected_collected).


def _runner_expected_collected() -> int:
    """Canonical collection pin, derived from the Tier-1 selector (C7).

    ``scripts/run_ci_tests.py`` EXPECTED_COLLECTED is the single manual
    authority; this freeze test reads that value instead of keeping an
    independent total. Deterministic, stdlib-only, no network.
    """
    import importlib.util
    path = ROOT / "scripts" / "run_ci_tests.py"
    spec = importlib.util.spec_from_file_location(
        "c7_run_ci_tests_pin", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.EXPECTED_COLLECTED


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout.strip()


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _load(stage, name):
    return json.loads((ROOT / "results" / "v3" / stage / name).read_text())


def _service():
    return V2UncertaintyService(
        model_provider=FixtureProvider(
            arm="model", source=C.SourceId.V3_1B_LOGISTIC),
        simulation_provider=FixtureProvider(
            arm="simulation", source=C.SourceId.MC2_E))


# --- parent anchors ---


def test_parent_v38_tag_intact():
    assert _git("rev-list", "-n", "1", VTAG) == V38


def test_parent_perf_tag_intact():
    assert _git("rev-list", "-n", "1", PTAG) == PERF


# --- stage card identities ---


def _card_identity(stage):
    card = _load(stage, "scientific_card.json")
    ident = card.pop("card_identity")
    assert hashlib.sha256(_canon(card)).hexdigest() == ident
    return card


def test_card_a_identity():
    card = _card_identity("v3_9a")
    assert card["classification"] == \
        "UNCERTAINTY_CONTRACT_PARTIALLY_SUPPORTED"


def test_card_b_identity():
    card = _card_identity("v3_9b")
    assert card["classification"] == "U1_U2_MEASURED_U3_NOT_READY"


def test_card_c_identity():
    card = _card_identity("v3_9c")
    assert card["classification"] == "RUNTIME_UNCERTAINTY_BUNDLE_VALIDATED"


def test_card_d_classification():
    card = _load("v3_9d", "scientific_card.json")
    assert "UNCERTAINTY_PRODUCT_UI_VALIDATED" in card["classification"]
    assert (ROOT / "frontend" / "app" / "uncertainty" / "page.tsx").is_file()


def test_programme_manifest_links():
    man = _load("v3_9e", "programme_manifest.json")
    assert man["stage_links"]["V3.9A"]["card_identity"] == \
        "e3e2c3cfa2ebbd239b205479d6b7b9ee12130deddf3d4803c261c06b91ae099a"
    assert man["stage_links"]["V3.9B"]["card_identity"] == \
        "a016290d56567805f715c91157960277ee76d7c8ecd00573a4b1ca56ce4b5ebf"
    assert man["stage_links"]["V3.9C"]["card_identity"] == \
        "2f7eb9a49311e34f5b7b9978a21b54787f8be17c9e242b23e04c780c847fbb25"
    assert "NOT a universal uncertainty estimator" in \
        man["statement_of_bound"]


# --- taxonomy: sources and families ---


def test_u1_source_roles():
    out = _service().compare(ANCHOR)
    assert out["sources"]["model"]["source"] == "V3_1B_LOGISTIC"
    assert out["sources"]["simulation"]["source"] == "MC2_E"
    blob = json.dumps(out["sources"])
    assert "XGB" not in blob and "ensemble" not in blob.lower()


def test_logistic_family_preserved():
    out = _service().compare(ANCHOR)
    assert out["sources"]["model"]["probability_family"] == \
        "INDEPENDENT_BINARY"


def test_mc2_family_preserved():
    out = _service().compare(ANCHOR)
    assert out["sources"]["simulation"]["probability_family"] == \
        "MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY"


def test_logistic_not_normalized():
    out = _service().compare(ANCHOR)
    total = sum(d["disagreement"]["p_model"] for d in out["drivers"]
                if d["status"] == "AVAILABLE")
    assert total > 1.5, total


def test_u2_semantics():
    out = _service().compare(ANCHOR)
    d = next(x for x in out["drivers"] if x["status"] == "AVAILABLE")
    mc = d["monte_carlo_sampling"]
    assert mc["precision_label"] == "FINITE_MC_SAMPLING_CONTEXT_ONLY"
    assert mc["valid_futures_n"] == 5000
    assert 0 <= mc["wilson_95_lower"] <= mc["p_hat"] <= \
        mc["wilson_95_upper"] <= 1


def test_u3_non_executable():
    out = _service().compare(ANCHOR)
    u3 = out["simulator_sensitivity"]
    assert u3["status"] == "PROVENANCE_UNAVAILABLE"
    assert u3["executable"] is False
    assert u3["gate"] == "U3_NOT_EXECUTABLE"
    assert out["availability"]["simulator_sensitivity"] == \
        "PROVENANCE_UNAVAILABLE"


def test_zero_executable_sensitivity_ranges():
    reg = _load("v3_9b", "sensitivity_range_registry.json")["entries"]
    supported = [k for k, v in reg.items()
                 if v.get("lower") is not None
                 or v.get("upper") is not None]
    assert supported == [], supported
    assert reg["regime_std_s"]["lower"] is None
    assert reg["rho"]["lower"] is None


def test_valid_zero_is_available():
    bundle = B.build_bundle(
        race_id="2022-r03-R", lap_number=2, state_time_s=None,
        stage="EARLY", season=2022,
        model_probs={"a": 0.4, "b": 0.1}, sim_probs={"a": 0.5, "b": 0.0},
        valid_trials={"a": 5000, "b": 5000})
    zero = next(d for d in bundle["drivers"] if d["driver_id"] == "b")
    assert zero["status"] == "AVAILABLE"
    assert zero["monte_carlo_sampling"]["success_count_k"] == 0
    assert zero["monte_carlo_sampling"]["p_hat"] == 0.0
    assert zero["disagreement"]["p_simulation"] == 0.0


# --- prohibitions: scores, winner, fusion ---


def test_no_universal_confidence_score():
    out = _service().compare(ANCHOR)
    blob = json.dumps(out).lower()
    for tok in ("confidence_score", "uncertainty_score", "trust_score",
                "reliability_score", "overall_confidence", "combined",
                "blend", "preferred_source", "winner_source"):
        assert tok not in blob, tok


def test_no_source_winner():
    out = _service().compare(ANCHOR)
    assert "winner" not in json.dumps(out["sources"]).lower()
    assert out["metric_implementation"] == "v3.8c-consensus-metrics-v1"


def test_no_fusion():
    out = _service().compare(ANCHOR)
    assert set(out.keys()) == {
        "schema_version", "metric_implementation", "state", "sources",
        "drivers", "field", "simulator_sensitivity", "availability",
        "provenance"}


# --- alignment, temporal contract, 2025 ---


def test_exact_alignment():
    out = _service().compare(ANCHOR)
    assert out["state"]["state_id"] == "2022-r03-R|lap2"
    assert out["field"]["n_common_drivers"] == len(
        [d for d in out["drivers"] if d["status"] == "AVAILABLE"])


def test_temporal_contract():
    import ast
    tree = ast.parse(
        (ROOT / "raceintel" / "uncertainty" / "bundle.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(n.name.split(".")[0] for n in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert imported <= {"__future__", "raceintel"}, imported
    assert not (ROOT / "raceintel" / "simulation" / "sensitivity.py").exists()


def test_2025_excluded():
    anchor = {"race_id": "2025-r01-R", "anchor_lap_number": 5,
              "anchor_state_time_s": None}
    avail = _service().availability(anchor)
    assert avail["comparison"] == "NOT_COMPARABLE"
    try:
        _service().compare(anchor)
    except ConsensusUnsupportedError:
        return
    raise AssertionError("2025 compare did not fail closed")


# --- API surface ---


def test_api_routes_registered():
    from api.config import get_serving_config
    from api.main import create_app
    app = create_app(get_serving_config())
    paths = {(r.path, tuple(r.methods)) for r in app.routes
             if hasattr(r, "methods")}
    assert any(p == "/v2/uncertainty/availability" for p, _ in paths)
    assert any(p == "/v2/uncertainty/compare" for p, _ in paths)


def test_no_public_science_controls():
    src = (ROOT / "api" / "v2_uncertainty_schemas.py").read_text() + \
        (ROOT / "api" / "v2_uncertainty_routes.py").read_text()
    for tok in ("master_seed", "simulation_count", "rho=",
                "sensitivity_range", "worker_count"):
        assert tok not in src, tok
    anchor_fields = set(
        __import__("api.v2_uncertainty_schemas", fromlist=["S"])
        .UncertaintyAnchor.model_fields)
    assert anchor_fields == {
        "race_id", "anchor_lap_number", "anchor_state_time_s"}


# --- frontend boundary ---


def test_frontend_route_exists():
    page = (ROOT / "frontend" / "app" / "uncertainty" / "page.tsx"
            ).read_text()
    assert "UncertaintyView" in page
    cmd = (ROOT / "frontend" / "components" / "shell"
           / "CommandBar.tsx").read_text()
    assert 'href: "/uncertainty"' in cmd
    assert 'href: "/consensus"' in cmd


def test_no_frontend_result_imports():
    base = ROOT / "frontend"
    for rel in ("app/uncertainty/page.tsx",
                "features/uncertainty/lib/uncertaintyClient.ts",
                "features/uncertainty/lib/uncertaintyFormat.ts",
                "features/uncertainty/hooks/useUncertainty.ts",
                "features/uncertainty/components/UncertaintyView.tsx"):
        text = (base / rel).read_text()
        assert "results/v3" not in text, rel
        assert "raceintel" not in text, rel


def test_no_frontend_science_imports():
    base = ROOT / "frontend"
    blob = "\n".join(
        (base / rel).read_text() for rel in
        ("features/uncertainty/lib/uncertaintyClient.ts",
         "features/uncertainty/lib/uncertaintyFormat.ts",
         "features/uncertainty/hooks/useUncertainty.ts",
         "features/uncertainty/components/UncertaintyView.tsx"))
    for tok in (".parquet", ".pkl", "joblib", "ml/inference",
                "wilson_interval", "average_ranks", "mc_sampling_se"):
        assert tok not in blob, tok


# --- collection + reconciliation ---


def test_collection_accounting():
    out = subprocess.run(
        ["/Users/tfatharva/f1-in-race-prediction_main/.venv/bin/python",
         "-m", "pytest", "tests/", "--collect-only", "-q",
         "-p", "no:cacheprovider"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout
    n = int(out.strip().splitlines()[-1].split()[0])
    # C7: expectation derived from the Tier-1 selector's canonical pin;
    # the old regex-agreement half is tautological once derived.
    assert n == _runner_expected_collected(), n


def test_guard_reconciliation_complete():
    ledger = _load("v3_9e", "guard_reconciliation.json")
    ids = [r["failing_test"] for r in ledger["reconciliations"]]
    assert len(ids) == 23
    for frag in ("test_no_scientific_source_files_modified",
                 "test_v3_8b_source_adapters",
                 "test_v3_8c_consensus_metrics",
                 "test_no_frozen_science_modified",
                 "test_worktree_contains_only_owned_v38_paths",
                 "test_h_pathology_superset_all_zero",
                 "test_no_production_runtime_dependency",
                 "test_no_runtime_code_modified",
                 "test_no_frontend_changes",
                 "PF-P24",
                 "test_no_serving_changes",
                 "test_v3_5b_dataset",
                 "test_v3_5c_harness",
                 "test_v3_5d_screening",
                 "test_no_serving_api_frontend_mc2_v35_changes",
                 "test_v3_6a_contract.py::test_no_frontend_change",
                 "test_v3_6b_contracts",
                 "test_v3_6d_evaluation",
                 "test_v3_6f_runtime",
                 "test_baseline_clean_at_entry",
                 "test_no_mc2_api_frontend_modification",
                 "P2A-P29",
                 "P0-P20"):
        assert any(frag in i for i in ids), frag
