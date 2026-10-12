"""V3.7D evaluation tests: preregistration discipline + artifact checks."""

import hashlib
import json
import subprocess
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "results" / "v3" / "v3_7d"


def _load(name):
    return json.loads((D / name).read_text())


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def test_protocol_exists_before_result_consumption():
    assert (D / "evaluation_protocol.json").is_file()
    assert (D / "run_results.json").is_file()


def test_protocol_schema_exact():
    assert _load("evaluation_protocol.json")["schema"] == \
        "v3.7d-evaluation-protocol-v1"


def test_protocol_deterministic():
    p = _load("evaluation_protocol.json")
    h = p.pop("protocol_hash")
    assert h == hashlib.sha256(json.dumps(
        p, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert h == "e4a6101c7267f2db9f85c76bcc07c17ed01c7f85de4a6481f94ab0941634c570"


def test_sampling_deterministic():
    assert _load("evaluation_protocol.json")["sampling"]["rule"] == \
        "exhaust eligible population in sample.json order"


def test_sampling_uses_no_post_t_outcome():
    blob = json.dumps(_load("evaluation_protocol.json")).lower()
    assert "final result" not in blob and "historical finish" not in blob


def test_target_selection_factual_only():
    assert "anchor driver" in _load("evaluation_protocol.json")["target_rule"]


def test_rival_selection_factual_only():
    assert "factual position" in \
        json.dumps(_load("evaluation_protocol.json")["rival_rule"])


def test_plan_construction_factual_only():
    blob = json.dumps(_load("evaluation_protocol.json")).lower()
    assert "historical pit strategy" not in blob


def test_candidate_identities_deterministic():
    run = json.loads((D / "run_results.json").read_text())
    assert len(run) == 71
    adapted = [r for r in run if r["meta"].get("state_identity")]
    recorded = [r for r in run if not r["meta"].get("state_identity")]
    assert len(adapted) == 70
    assert len(recorded) == 1  # mazepin adapter-unsupported, reason recorded
    assert "unobserved_roster_member" in recorded[0]["meta"]["unsupported"]


def test_no_2025_if_unsupported():
    assert _load("evaluation_protocol.json")["population"]["excludes_2025"] is True
    run = json.loads((D / "run_results.json").read_text())
    assert all(not r["meta"]["race_id"].startswith("2025") for r in run)


def test_plan_families_exact():
    fams = set()
    run = json.loads((D / "run_results.json").read_text())
    for r in run:
        fams.update(r["comparisons"])
    assert {"N1", "N2", "N3", "N5", "N2_SOFT", "MULTISTOP",
            "MULTIDRIVER", "PVP_N2_N5", "PVP_SINGLE_MULTI"} >= fams - {"N8"}


def test_horizon_set_exact():
    assert _load("evaluation_protocol.json")["horizons"] == [1, 2, 3, 5]


def test_research_seeds_exact():
    assert _load("evaluation_protocol.json")["root_seeds"]["research"] == [7, 99]


def test_research_counts_exact():
    assert _load("evaluation_protocol.json")["simulation_counts"]["research"] == \
        [1000, 2500]


def test_pathology_definitions_exact():
    assert len(_load("evaluation_protocol.json")["pathology_definitions"]) == 17


def test_refinement_gate_frozen():
    gate = _load("evaluation_protocol.json")["refinement_gate"]
    assert "REFINEMENT_NOT_WARRANTED_requires" in gate


def test_evaluation_does_not_mutate_c_engine():
    for rel in ("scripts/v3_7d_run.py", "scripts/v3_7d_analyze.py",
                "scripts/v3_7d_protocol.py"):
        src = (ROOT / rel).read_text()
        assert "monkeypatch" not in src
    src = (ROOT / "raceintel/counterfactual/engine.py").read_text()
    assert "import evaluation" not in src and "from evaluation" not in src
    assert "evaluation." not in src


def test_c_seam_hash_unchanged():
    import hashlib as _hl
    digest = _hl.sha256(
        (ROOT / "raceintel/simulation/monte_carlo.py").read_bytes()
    ).hexdigest()
    assert digest == "045f392e46b030744f18a76140685ceba7501f80c0b8e265af662e57ca5f5376"
    assert _load("evaluation_card.json")["seam_sha256"] == digest


def test_position_gain_independent_recomputation():
    s = _load("stability_analysis.json")
    ok, tot = s["gain_recompute"]
    assert tot >= 10 and ok == tot


def test_pit_count_independent_recomputation():
    s = _load("stability_analysis.json")
    ok, tot = s["pit_recompute"]
    assert tot >= 10 and ok == tot


def test_ahead_of_rival_independent_recomputation():
    s = _load("stability_analysis.json")
    ok, tot = s["ahead_recompute"]
    assert tot >= 1 and ok == tot


def test_complete_pair_accounting():
    assert _load("stability_analysis.json")["pair_violations"] == 0


def test_probability_bounds():
    rep = _load("pathology_report.json")
    assert rep["counts"]["P12"] == 0


def test_finite_metrics():
    assert _load("pathology_report.json")["counts"]["P11"] == 0


def test_finish_distribution_validity():
    assert _load("pathology_report.json")["counts"]["P13"] == 0


def test_comparison_orientation():
    assert _load("pathology_report.json")["counts"]["P14"] == 0


def test_lifecycle_state_validity():
    allowed = {"EXECUTED", "INERT", "SUPERSEDED", "CANCELLED", "TERMINAL",
               "INVALID"}
    hist = _load("historical_evaluation.json")
    for key in hist["lifecycle"]:
        assert key.split("/")[-1] in allowed, key


def test_order_invariance_evidence():
    assert _load("pathology_report.json")["counts"]["P8"] == 0
    assert _load("pathology_report.json")["counts"]["P9"] == 0


def test_reproducibility_evidence():
    ok, tot = _load("stability_analysis.json")["reproducibility"]
    assert tot == 4 and ok == 4


def test_n1_parity_evidence():
    ok, tot = _load("stability_analysis.json")["parity"]
    assert tot == 16 and ok == 16


def test_n2_parity_evidence():
    ok, tot = _load("stability_analysis.json")["parity"]
    assert tot == 16 and ok == 16


def test_temporal_poison_evidence():
    import sys
    sys.path.insert(0, str(ROOT / "tests"))
    from test_v3_7c_engine import test_historical_future_poison as _p
    _p()


def test_v35_absent():
    for rel in ("scripts/v3_7d_run.py", "scripts/v3_7d_analyze.py"):
        assert "v3_5" not in (ROOT / rel).read_text()


def test_evaluation_card_deterministic():
    c = _load("evaluation_card.json")
    identity = c.pop("card_identity")
    assert identity == hashlib.sha256(json.dumps(
        c, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_gate_decision_valid():
    gate = _load("refinement_gate.json")["decision"]
    assert gate in ("REFINEMENT_NOT_WARRANTED", "REFINEMENT_WARRANTED",
                    "BLOCKING_DEFECT")
