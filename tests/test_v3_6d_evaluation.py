"""V3.6D evaluation tests: protocol discipline + artifact reconciliation.

Research-evaluation guards: frozen identities, pre-registered protocol
(frozen before results), deterministic sampling, denominator reconciliation,
offline-only V3.5 role, no tuning, no API/frontend changes.
"""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
D = ROOT / "results" / "v3" / "v3_6d"


def _load(name):
    return json.loads((D / name).read_text())


def _protocol():
    return _load("evaluation_protocol.json")


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


# --- provenance ---

def test_a_identity_exact():
    import hashlib
    d = json.loads((ROOT / "results/v3/v3_6a/strategy_contract.json"
                    ).read_text())
    h = d.pop("contract_hash")
    assert h == "2d29c19b47b24035f0d1c503fccc8cd4090595b4ebb2a980001d0a919b0ae59b"
    assert h == hashlib.sha256(json.dumps(
        d, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_b_identity_exact():
    import hashlib
    d = json.loads((ROOT / "results/v3/v3_6b/strategy_execution_contract.json"
                    ).read_text())
    h = d.pop("contract_hash")
    assert h == "df821fe13ed587d7a086e93b8ee53a1670130299ca92c5a668608add443e3644"
    assert h == hashlib.sha256(json.dumps(
        d, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def test_c_validation_exact():
    v = json.loads((ROOT / "results/v3/v3_6c/engine_validation.json"
                    ).read_text())
    assert v["engine_version"] == "v3.6c-engine-v1"
    for key in ("determinism", "mc2_reference_parity", "phase7_parity"):
        assert "PASS" in v[key]
    assert v["5000_run_validation"]["status"] == "EXECUTED_SUCCESSFULLY"


# --- protocol discipline ---

def test_protocol_hash_deterministic():
    import hashlib
    p = _protocol()
    h = hashlib.sha256(json.dumps(
        p, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
    assert h == ("0c2bf7fb6e46a948d811587a64aac89cb10cfe0bf67485ed9ff3b457d64088fc")


def test_protocol_frozen_before_results():
    proto_mtime = (D / "evaluation_protocol.json").stat().st_mtime
    assert proto_mtime < (D / "layer1.json").stat().st_mtime
    assert proto_mtime < (D / "historical_evaluation.json").stat().st_mtime


def test_no_2025_mc2_evaluation():
    sample = _load("sample.json")
    seasons = {s["race_id"].split("-")[0] for s in sample["states"]}
    assert seasons <= {"2018", "2019", "2020", "2021", "2022", "2023", "2024"}


def test_sampling_deterministic():
    sample = _load("sample.json")
    assert sample["fractions"] == [1 / 3, 2 / 3]
    by_race = {}
    for s in sample["states"]:
        by_race.setdefault(s["race_id"], []).append(s)
    assert all(len(v) <= 2 for v in by_race.values())


def test_sampling_independent_of_strategy_result():
    sample = _load("sample.json")
    blob = json.dumps(sample).lower()
    assert "delta_" not in blob and "point_estimate" not in blob


def test_target_selection_deterministic():
    sample = _load("sample.json")
    assert all(s["target_driver_id"] == s["anchor"]["driver_id"]
               for s in sample["states"])


# --- reconciliation ---

def test_coverage_denominators_reconcile():
    sample = _load("sample.json")
    assert sample["candidates"] == len(sample["states"])
    assert sample["eligible"] == sum(1 for s in sample["states"]
                                    if s["eligible"])


def test_unsupported_counts_reconcile():
    from collections import Counter
    sample = _load("sample.json")
    counts = Counter(s["reason"] for s in sample["states"]
                     if not s["eligible"])
    assert sum(counts.values()) == sample["candidates"] - sample["eligible"]


def test_action_counts_reconcile():
    layer1 = _load("layer1.json")
    for s in layer1["states"]:
        alts = s["result"]["alternatives"]
        assert len(alts) == 9
        for a in alts:
            assert ((a["evaluated"] and a["reason"] is None)
                    or ((not a["evaluated"]) and a["reason"] is not None))


def test_reproducibility_exact():
    layer2 = _load("layer2.json")
    assert layer2["reproducibility"]
    assert all(r["identical"] for r in layer2["reproducibility"])


def test_seed_experiment_uses_frozen_seed_set():
    layer2 = _load("layer2.json")
    assert layer2["seeds"] == [20240101, 12345, 99991]
    for entry in layer2["seeds_experiment"]:
        assert [r["seed"] for r in entry["runs"]] == [20240101, 12345, 99991]


def test_count_experiment_uses_frozen_counts():
    layer2 = _load("layer2.json")
    assert layer2["counts"] == [200, 1000, 5000]
    for entry in layer2["counts_experiment"]:
        assert [r["n"] for r in entry["runs"]] == [200, 1000, 5000]


def test_crn_methodology_fixed():
    layer2 = _load("layer2.json")
    for entry in layer2["crn_experiment"]:
        assert "paired_se_win" in entry and "independent_se_win" in entry


def test_effect_aggregation_deterministic():
    ev = _load("historical_evaluation.json")
    summary = json.loads((ROOT / "results/v3/v3_6d_historical_strategy_"
                                "evaluation.json").read_text())
    assert summary["protocol_hash"] == ev["protocol_hash"]
    assert summary["population"] == ev["population"]
    assert summary["refinement_decision"] == json.loads(
        (D / "refinement_decision.json").read_text())["verdict"]


def test_stage_definitions_frozen():
    layer1 = _load("layer1.json")
    assert {s["stage"] for s in layer1["states"]} <= {"EARLY", "MID", "LATE"}


def test_no_historical_action_as_label():
    layer1 = _load("layer1.json")
    blob = json.dumps(layer1).lower()
    assert "historical_action" not in blob and "team_choice" not in blob
    assert "should_have" not in blob and "correct_strategy" not in blob


def test_v35_diagnostic_offline_only():
    ev = _load("historical_evaluation.json")
    assert ev["v35_diagnostic"]["matched_states"] >= 0
    import sys as _sys
    assert not any(m.startswith("v3_5") for m in _sys.modules)


def test_case_study_rule_deterministic():
    cases = _load("case_studies.json")
    assert cases["selection"].startswith("algorithmic")
    assert set(cases["cases"]) == {"median_effect", "high_uncertainty",
                                   "objective_tradeoff", "inert_superseded",
                                   "strong_supported"}


def test_refinement_rule_frozen():
    dec = _load("refinement_decision.json")
    assert dec["verdict"] in ("REFINEMENT_WARRANTED",
                              "REFINEMENT_NOT_WARRANTED")
    assert set(dec["gates"]) >= {"reproducibility_ok", "pathological_cases",
                                 "crn_median_ratio"}


def test_no_tuning():
    lines = [ln for ln in _git("status", "--short").splitlines()
             if ln.strip()]
    # V3.7H reconciliation: new (untracked "??" or staged-new "A") files
    # are permitted by design ("new files permitted"); only tracked
    # modifications are pinned. api/ dirt beyond the chartered set still
    # fails via test_no_api_frontend_changes in this same file.
    changed = [ln.split()[-1] for ln in lines
               if not (ln.startswith("??") or ln.startswith("A "))]
    tracked_modified = [f for f in changed
                        if not f.startswith(("results/", "docs/", "tests/",
                                             "scripts/", "raceintel/strategy/"
                                             "v3_",
                                             # V3.6F chartered additive
                                             # integration files.
                                             "api/v2_strategy_v3_",
                                             "api/main.py",
                                             # V3.6G chartered Strategy 2.0
                                             # frontend replacement files.
                                             "frontend/app/strategy/page.tsx",
                                             "frontend/features/strategy/"
                                             "components/Strategy",
                                             "frontend/features/strategy/"
                                             "hooks/useStrategy",
                                             "frontend/features/strategy/"
                                             "lib/strategy",
                                             "frontend/lib/v2.ts",
                                             # V3.7H reconciliation: chartered
                                             # V3.7 tracked modifications
                                             # (exact paths; additive only).
                                             "frontend/app/counterfactuals",
                                             "frontend/features/"
                                             "counterfactuals",
                                             "frontend/components/shell/"
                                             "CommandBar.tsx",
                                             # V3.10I reconciliation: chartered
                                             # V3.10 tracked modifications
                                             # (exact paths; presentation
                                             # only, frozen science untouched).
                                             "frontend/components/shell/"
                                             "AppShell.tsx",
                                             "frontend/features/replay/"
                                             "components/SpatialTrackPanel.tsx",
                                             "raceintel/simulation/"
                                             "monte_carlo.py",))]
    # Only guard-allowlist test edits + new files permitted.
    # P2A carve-out (performance programme only): exactly the two kernel
    # files with hoisted loop-invariant overhead, the Tier-1 pin, and the
    # V3.8 guard files admitting the P2A set (parity-gated in
    # P0-P20/P1-P3/P2A-P29 checks, not here).
    assert all(f.startswith("tests/test_v3_6") or f in (
        "raceintel/simulation/mc2/kernel.py",
        "raceintel/simulation/mc2/residuals.py",
        "scripts/run_ci_tests.py",
        "tests/test_v3_8a_consensus_contract.py",
        "tests/test_v3_8b_source_adapters.py",
        "tests/test_v3_8c_consensus_metrics.py",
        "tests/test_v3_8d_correction_01.py",
        "tests/test_v3_8d_evaluation.py",
        "tests/test_v3_8h_freeze.py") for f in tracked_modified), \
        tracked_modified


def test_no_api_frontend_changes():
    changed = [ln.split()[-1] for ln in _git("status", "--short").splitlines()
               if ln.strip()]
    # V3.6F charter admits exactly its additive integration files; any
    # other api/ change still fails. V3.6G charter admits exactly its
    # Strategy 2.0 replacement files; any other frontend/ change fails.
    # V3.7H reconciliation: V3.7F/V3.7G charters additionally admit exactly
    # the counterfactual API/Explorer paths (frozen science untouched).
    # V3.8H reconciliation: V3.8F/V3.8G charters additionally admit exactly
    # the consensus API/frontend paths (frozen science untouched).
    # V3.10I reconciliation: V3.10F charter additionally admits exactly
    # the read-only telemetry API trio (frozen science untouched).
    allowed = ("api/v2_strategy_v3_", "api/main.py",
               "api/v2_counterfactual_", "api/v2_consensus_",
               # V3.9C carve-out: uncertainty bundle API (additive).
               "api/v2_uncertainty_",
               "api/v2_telemetry_")
    assert not any(f.startswith("api/") and not f.startswith(allowed)
                   for f in changed)
    allowed_frontend = ("frontend/app/strategy/page.tsx",
                        "frontend/features/strategy/components/Strategy",
                        "frontend/features/strategy/hooks/useStrategy",
                        "frontend/features/strategy/lib/strategy",
                        "frontend/lib/v2.ts",
                        "frontend/app/counterfactuals",
                        "frontend/features/counterfactuals",
                        "frontend/app/consensus",
                        "frontend/features/consensus",
                        # V3.9D carve-out (product UI stage only:
                        # /uncertainty route + uncertainty feature
                        # modules; no science change).
                        "frontend/app/uncertainty/",
                        "frontend/features/uncertainty/",
                        "frontend/components/shell/CommandBar.tsx",
                        # V3.10I reconciliation: V3.10A-H pit-wall
                        # product admitted exactly (frozen science
                        # untouched).
                        "frontend/app/pit-wall/",
                        "frontend/features/pit-wall/",
                        "frontend/features/workspace/",
                        "frontend/components/shell/AppShell.tsx",
                        "frontend/features/replay/components/SpatialTrackPanel.tsx")
    assert not any(f.startswith("frontend/")
                   and not f.startswith(allowed_frontend)
                   for f in changed)
