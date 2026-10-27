"""V3.9B evidence-measurement tests (frozen evidence + small fixtures).

No MC2 execution (no 5000-future runs), no refits, no perturbations, no
API/UI. Measurement functions are verified against committed artifacts and
the frozen v3.8c implementation.
"""

import hashlib
import json
import math
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
B = ROOT / "results" / "v3" / "v3_9b"
V38 = "15df86b864fa552c69c4b7a53e22f1fc3b4c4ca1"
VTAG = "v3.8-model-simulation-consensus"
PERF = "32466c436845ee02c3af79ce08d1c102b9d91384"
PTAG = "v3.8-mc2-performance"


def _load(name):
    return json.loads((B / name).read_text())


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True,
        check=True).stdout.strip()


def _canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def _frozen_rows():
    return json.loads(
        (ROOT / "results" / "v3" / "v3_8d" / "per_row_records.json").read_text())


# --- provenance ---


def test_tags_intact():
    assert _git("rev-list", "-n", "1", VTAG) == V38
    assert _git("rev-list", "-n", "1", PTAG) == PERF
    assert _git("merge-base", "--is-ancestor", V38, "HEAD") == ""
    assert _git("merge-base", "--is-ancestor", PERF, "HEAD") == ""


def test_no_runtime_code_modified():
    out = _git("status", "--porcelain=v1")
    mods = [ln.split()[-1] for ln in out.splitlines()
            if ln.startswith(("M ", " M"))]
    runtime = [m for m in mods if not m.startswith("tests/")
               and m != "scripts/run_ci_tests.py"
               # V3.9C carve-out: uncertainty router registration (additive).
               and m != "api/main.py"
               # V3.9D carve-out: uncertainty nav entry (one line,
               # presentation only; already V3.8H-allowlisted wiring file).
               and m != "frontend/components/shell/CommandBar.tsx"
               # V3.10I reconciliation (freeze): exact V3.10 product
               # modifications (workspace shell, replay calm prop,
               # expert prefill x2, telemetry client; presentation
               # only, frozen science untouched).
               and m != "frontend/components/shell/AppShell.tsx"
               and m != "frontend/features/counterfactuals/components/CounterfactualView.tsx"
               and m != "frontend/features/replay/components/SpatialTrackPanel.tsx"
               and m != "frontend/features/strategy/components/Strategy2View.tsx"
               and m != "frontend/lib/v2.ts"
               # V3 Final reconciliation (freeze): navigation docs are
               # tracked since the V3.11 freeze; terminal-status lines
               # only (docs-only, not runtime code).
               and m != "docs/INDEX.md"
               and m != "scripts/README.md"
               # C5 post-V3: exact C5 client-consolidation files
               # (frontend transport delegation; contracts
               # unchanged) + frontend-CI pin bump.
               and m != "frontend/lib/v2.ts"
               and m != "frontend/lib/spatial.ts"
               and m != "frontend/lib/api.ts"
               and m != "frontend/features/consensus/lib/consensusClient.ts"
               and m != "frontend/features/uncertainty/lib/uncertaintyClient.ts"
               and m != "scripts/run_ci_frontend_tests.py"
               # C1 post-V3: exact C1 suite-orchestration charter
               # (Makefile target recomposition only).
               and m != "Makefile"]
    assert runtime == [], runtime
    # V3.9C owns raceintel/uncertainty (thin bundle over frozen seams):
    # purity holds iff it imports only frozen consensus seams, never MC2
    # execution, inference, or sensitivity machinery.
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
    blob = (ROOT / "raceintel" / "uncertainty" / "bundle.py").read_text()
    assert "run_mc2" not in blob and "SeedSequence" not in blob
    assert not (ROOT / "raceintel" / "simulation" / "sensitivity.py").exists()


# --- alignment ---


def test_exact_alignment_no_zero_fill():
    acc = _load("aligned_evidence_accounting.json")
    assert acc["pairs"] == 277
    assert acc["missing_zero_filled"] == 0
    assert acc["unsupported_silently_dropped"] == 0
    ck = json.loads((ROOT / "results" / "v3" / "v3_8d"
                     / "mc2_checkpoint.json").read_text())["mc2_out"]
    assert {r["state_id"] for r in _frozen_rows()} == set(ck.keys())


def test_logistic_unnormalized_and_frequency_semantics():
    from raceintel.consensus import contracts as C
    assert C.SOURCE_FAMILIES[C.SourceId.V3_1B_LOGISTIC] == \
        C.SourceFamily.INDEPENDENT_BINARY
    assert C.SOURCE_FAMILIES[C.SourceId.MC2_E] == \
        C.SourceFamily.MUTUALLY_EXCLUSIVE_SIMULATION_FREQUENCY
    # stored gaps recompute as raw native differences (no normalization)
    for r in _frozen_rows():
        assert abs((r["p_mc2"] - r["p_logistic"]) - r["signed_gap"]) < 1e-9


# --- U1 ---


def test_u1_metric_reuse_identity_and_orientation():
    from raceintel.consensus import metrics as M
    assert M.METRICS_IMPLEMENTATION_IDENTITY == "v3.8c-consensus-metrics-v1"
    u1 = _load("u1_measurements.json")
    assert u1["metric_implementation"] == "v3.8c-consensus-metrics-v1"
    assert u1["orientation"] == "signed_gap = simulation_minus_model"
    assert u1["evidence"]["outcome_labels_used"] is False


def test_u1_overall_measurements():
    s = _load("u1_summary.json")
    assert s["classification"] == "U1_MEASURED"
    m = s["magnitudes"]["absolute_gap"]
    assert m["count"] == 277
    assert m["median"] < m["mean"]  # heavy tail, documented descriptively
    assert "HIGH" not in json.dumps(s) and "MEDIUM" not in json.dumps(s)


def test_u1_stage_measurements():
    s = _load("u1_stage_summary.json")
    assert set(s["by_stage"]) == {"EARLY", "MID", "LATE"}
    assert sum(v["n"] for v in s["by_stage"].values()) == 277
    assert len(s["temporal_within_race"]) >= 1


def test_sampling_is_not_disagreement_or_spread():
    d = _load("disagreement_sampling_diagnostic.json")
    assert d["label"] == "DESCRIPTIVE_DIAGNOSTIC_ONLY"
    assert d["not_a_hypothesis_test"] is True
    assert d["no_source_winner"] is True


def test_no_combined_score_and_no_winner():
    blob = json.loads(json.dumps(_load("u1_summary.json"))), json.loads(
        json.dumps(_load("u2_summary.json")))
    flat = json.dumps(blob).lower()
    for forbidden in ("combined_uncertainty", "confidence_score",
                      "trust_score", "reliability_score", "uncertainty_score",
                      "source_winner", "model_wins", "simulator_wins"):
        assert forbidden not in flat, forbidden


# --- U2 ---


def test_u2_count_identity_and_n():
    u2 = _load("u2_measurements.json")
    assert u2["n"] == 5000 and u2["states"] == 277
    assert u2["n_below_5000"] == 0
    assert u2["stored_context_recomputed_max_abs_diff"] == 0.0


def test_u2_se_and_wilson_spot():
    from raceintel.consensus import metrics as M
    assert abs(M.mc_sampling_se(0.5, 5000) - math.sqrt(0.25 / 5000)) < 1e-12
    lo, hi = M.wilson_interval(0.0, 5000)
    assert lo == 0.0 and hi > 0.0
    lo, hi = M.wilson_interval(1.0, 5000)
    assert hi == 1.0 and lo < 1.0
    u2 = _load("u2_measurements.json")
    assert u2["se"]["max"] <= 0.0072


def test_k0_valid_zero_and_kn():
    u2 = _load("u2_measurements.json")
    assert u2["k_eq_0_valid_zero_count"] > 0
    assert u2["interpretation"] == "finite Monte Carlo sampling precision ONLY"


def test_missing_is_not_zero_in_evidence():
    for r in _frozen_rows():
        assert r["p_mc2"] is not None and r["p_logistic"] is not None


# --- U3 ---


def test_regime_std_status_and_no_se_invention():
    p = _load("regime_std_provenance.json")
    assert p["status"] == "PROVENANCE_INSUFFICIENT"
    assert p["estimator_se_frozen"] is False
    assert p["normal_theory_se_valid"] is False
    assert "AR(1)" in p["normal_theory_invalid_reason"]


def test_rho_status_and_no_fold_ci():
    p = _load("rho_provenance.json")
    assert p["status"] == "PROVENANCE_INSUFFICIENT"
    assert p["deployment_value"] == 0.264
    assert "hard-coded" in p["deployment_origin"]
    assert p["ci"] is False and p["bootstrap"] is False


def test_ranges_null_and_no_percentages():
    reg = _load("sensitivity_range_registry.json")
    assert reg["executable_ranges"] == 0
    for name, e in reg["entries"].items():
        assert e["lower"] is None and e["upper"] is None, name
    blob = json.dumps(reg)
    assert "10%" not in blob and "± 10" not in blob


def test_u3_gate_logic():
    g = _load("u3_gate.json")
    assert g["classification"] == "U3_PROVENANCE_INSUFFICIENT"
    assert g["gate"] == "U3_NOT_EXECUTABLE"
    reg = _load("sensitivity_range_registry.json")
    assert (g["gate"] == "U3_NOT_EXECUTABLE") == \
        (reg["executable_ranges"] == 0)


# --- policy ---


def test_2025_policy_and_no_exposure():
    acc = _load("aligned_evidence_accounting.json")
    assert acc["has_2025"] is False
    assert acc["seasons"] == [2022, 2023, 2024]
    from raceintel.consensus import product as P
    assert 2025 in P.PRODUCT_EXCLUDED_SEASONS


def test_no_mc2_rerun_or_bayes_or_api():
    card = _load("scientific_card.json")
    assert card["mc2_reruns"] == 0
    assert card["api_added"] is False and card["frontend_added"] is False
    assert not (ROOT / "raceintel" / "simulation" / "bayesian_tyre.py").exists()
    # V3.9C owns exactly the additive uncertainty API trio (no other api/);
    # V3.9B itself adds no API.
    # V3.10I reconciliation (freeze): the V3.9C trio is committed at the
    # frozen parent, so the pre-commit worktree check becomes a freeze
    # invariant — trio tracked, and exactly the additive V3.10F telemetry
    # trio untracked (no other api/).
    import subprocess as sp
    out = sp.run(["git", "status", "--porcelain=v1"], cwd=ROOT,
                 capture_output=True, text=True, check=True).stdout
    tracked = sp.run(["git", "ls-files", "api/"], cwd=ROOT,
                     capture_output=True, text=True, check=True).stdout.split()
    for f in ("api/v2_uncertainty_routes.py",
              "api/v2_uncertainty_schemas.py",
              "api/v2_uncertainty_service.py"):
        assert f in tracked, f
    new_api = sorted(ln.split()[-1] for ln in out.splitlines()
                     if ln.strip().startswith("??")
                     and ln.split()[-1].startswith("api/"))
    # V3.11F reconciliation (freeze): the V3.10F telemetry trio is
    # committed at the frozen v3.10 parent, so the pre-commit
    # expectation (trio untracked) is stale; V3.11 adds no api/
    # files. Invariant preserved: no other (untracked) api/.
    assert new_api == [], new_api


def test_performance_freeze_provenance():
    out = _git("status", "--porcelain=v1")
    touched = [ln.split()[-1] for ln in out.splitlines()
               if ln.startswith(("M ", " M"))]
    assert "raceintel/simulation/mc2/kernel.py" not in touched
    assert "raceintel/simulation/mc2/residuals.py" not in touched


# --- card / pathology ---


def test_scientific_card_identity_and_class():
    card = _load("scientific_card.json")
    ident = card.pop("card_identity")
    assert hashlib.sha256(_canon(card)).hexdigest() == ident
    assert card["classification"] == "U1_U2_MEASURED_U3_NOT_READY"
    assert card["u1"] == "U1_MEASURED" and card["u2"] == "U2_MEASURED"
    assert card["u3"] == "U3_PROVENANCE_INSUFFICIENT"


def test_v39b_pathology_all_zero():
    counts = _load("validation.json")["pathology"]
    assert set(counts) == {f"V3.9B-P{i}" for i in range(1, 31)}
    bad = {k: v for k, v in counts.items() if v != 0}
    assert bad == {}, bad
    assert "combined_uncertainty" not in (ROOT / "raceintel" / "consensus"
                                          / "metrics.py").read_text()
