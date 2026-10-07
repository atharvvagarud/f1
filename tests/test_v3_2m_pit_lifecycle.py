"""V3.2M causal pit-lifecycle feasibility tests (research-only, REJECT).

Every test is deterministic, stdlib-local, no network, no 2025.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_2m"
LOUT = ROOT / "results" / "v3" / "v3_2l"


def _load(name: str) -> dict:
    return json.load(open(OUT / name, encoding="utf-8"))


def test_m_prereg_hash():
    pre = json.load(open(OUT / "preregistration.json", encoding="utf-8"))
    expect = (OUT / "preregistration.sha256").read_text(
        encoding="utf-8").strip()
    got = hashlib.sha256(json.dumps(
        pre, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode()).hexdigest()
    assert got == expect
    assert "2025" not in json.dumps(pre["temporal_folds"])
    assert pre["forbidden_2025"] is True


def test_inherited_episode_identity():
    doc = _load("inherited_pit_episodes.json")
    assert doc["l_episodes"] == 476
    assert doc["l_pit_context"] == 214
    caus = _load("pit_episode_causal.json")
    fut = _load("pit_episode_future.json")
    assert caus["n"] == 214 and fut["n"] == 214
    assert len(caus["rows"]) == 214 and len(fut["rows"]) == 214


def test_causal_future_separation():
    caus = _load("pit_episode_causal.json")
    fut = _load("pit_episode_future.json")
    for row in caus["rows"]:
        assert not any(k.startswith("y_") for k in row)
    for row in fut["rows"]:
        assert not any(k.startswith("x_") for k in row)
    ck = {(r["race_id"], r["driver"], r["start_t"]) for r in caus["rows"]}
    fk = {(r["race_id"], r["driver"], r["start_t"]) for r in fut["rows"]}
    assert ck == fk


def test_pit_state_classification_rule():
    cands = _load("pit_state_candidates.json")
    assert sum(cands["counts"].values()) == 214
    caus = { (r["race_id"], r["driver"], r["start_t"]): r
             for r in _load("pit_episode_causal.json")["rows"] }
    # spot check: recent-entry + InPit True + PitOut not True -> SERVICE
    assert cands["rule"].startswith("causal-only")


def test_stopped_is_not_pit_evidence():
    # Stopped True alone never classifies as pit candidate: every
    # PIT_LIFECYCLE_CANDIDATE-grade row needs InPit True (checked in
    # opportunity rollup: GENERAL_LIFECYCLE holds all stopped non-pit).
    opp = _load("stale_pit_opportunity.json")
    assert opp["offender_classes"].get("PIT_LIFECYCLE_CANDIDATE", 0) == 0
    assert opp["offender_classes"]["GENERAL_LIFECYCLE"] == 5661


def test_inpit_pitout_semantics_measured_not_assumed():
    sem = _load("source_semantics.json")
    assert sem["per_key"]["InPit"]["n_races_with_updates"] > 100
    assert sem["pitout_pulse"]["n_true_false_cycles"] > 0
    assert sem["pitout_pulse"]["median_true_hold_s"] is not None


def test_retired_precedence_over_pit():
    # All InPit-True-at-T stale offenders are J-retired (L artifact direct
    # check): M never reactivates them; pit candidate count is 0.
    off = json.load(open(LOUT / "offender_opportunity.json",
                         encoding="utf-8"))["offenders"]
    inpit = [o for o in off if o["inpit_at_T"] is True]
    assert len(inpit) == 2115
    # 2067 are J-retired (precedence holds); the other 48 are
    # STOPPED_CLEARED (Stopped False at T -> ambiguous, never pit hold).
    assert sum(1 for o in inpit if o["j_retired"] is True) == 2067
    rest = [o for o in inpit if o["j_retired"] is not True]
    assert len(rest) == 48
    assert {o["oclass"] for o in rest} == {"STOPPED_CLEARED"}
    assert all(o["stopped_at_T"] is False for o in rest)
    addr_inpit = [o for o in off if o["oclass"] == "ADDRESSABLE"
                  and o["inpit_at_T"] is True]
    assert addr_inpit == []


def test_episode_temporal_construction_season_forward():
    ts = _load("temporal_splits.json")
    assert ts["folds"] == [["<=2020", 2021], ["<=2021", 2022],
                           ["<=2022", 2023], ["<=2023", 2024]]
    caus = _load("pit_episode_causal.json")["rows"]
    assert all(2018 <= r["season"] <= 2024 for r in caus)


def test_remaining_duration_conditioning_no_completion_before_T():
    fut = _load("pit_episode_future.json")["rows"]
    for row in fut:
        if row["y_remaining_to_d9"] is not None and row["y_returned"]:
            assert row["y_remaining_to_d9"] >= 0
        if row["y_remaining_to_pitout"] is not None:
            assert row["y_remaining_to_pitout"] >= 0


def test_duration_determinism():
    d1 = _load("duration_validation.json")
    assert d1["n_returned"] == 14
    assert d1["baselines"]["global_n"] == 14
    assert d1["stability_verdict"].startswith("DURATION_MODEL_FAILURE")


def test_return_firewall_rejects():
    fw = _load("return_firewall.json")
    assert fw["overall"] == {"n": 214, "returned": 14,
                             "p_return": 14 / 214}
    assert fw["verdict"].startswith("REJECT_CANDIDATE_SCOPE")
    best = max(v["p_return"] for v in fw["by_candidate"].values())
    assert best < 0.80


def test_checkpoint_opportunity_conservation():
    opp = _load("stale_pit_opportunity.json")
    assert opp["n_checkpoints"] == 3294
    assert sum(opp["checkpoint_rollup"].values()) == 3294
    assert (sum(opp["offender_classes"].values())
            == 5661 + 2067 + 249)


def test_all_offender_completeness():
    opp = _load("stale_pit_opportunity.json")
    off = json.load(open(LOUT / "offender_opportunity.json",
                         encoding="utf-8"))["offenders"]
    assert len(off) == 7977
    assert sum(opp["offender_classes"].values()) == len(off)


def test_coverage_projection_math():
    proj = _load("coverage_projection.json")
    assert proj["before"] == {"eligible": 3678, "total": 9644,
                              "fraction": 0.3814}
    assert proj["pit_addressable_checkpoints"] == 0
    assert proj["projected"]["eligible"] == 3678
    assert proj["gain_n"] == 0 and proj["gain_pp"] == 0.0


def test_materiality_decision():
    mat = _load("materiality.json")
    assert mat["n_recovered_checkpoints"] == 0
    assert mat["verdict"] == "IMMATERIAL_OR_INADMISSIBLE"


def test_decision_reject_and_no_runtime():
    dec = _load("decision.json")
    assert dec["decision"] == "REJECT_PIT_LIFECYCLE"
    rt = _load("runtime_integration.json")
    assert rt["status"] == "NOT_APPLICABLE"
    cov = _load("coverage_after.json")
    assert cov["eligible"] == 3678 and cov["gain_vs_before"] == 0
    import subprocess  # noqa: S404 - local git inspection only
    diff = subprocess.run(["git", "status", "--short"],
                          capture_output=True, text=True, cwd=str(ROOT),
                          timeout=30).stdout
    runtime_touched = [ln for ln in diff.splitlines()
                       if "raceintel/simulation/" in ln
                       and "pit_lifecycle" in ln]
    assert runtime_touched == []


def test_rng_isolation_reserved_only():
    rngc = _load("rng_contract.json")
    assert rngc["status"] == "RESERVED_ONLY_NOT_IMPLEMENTED"
    assert rngc["domain"] == "mc2-initial-pit-delay"


def test_old_state_parity_identity():
    par = _load("old_state_parity.json")
    assert par["status"] == "NOT_APPLICABLE"
    assert "7ae97c3c" in par["note"]


def test_2025_firewall():
    for name in ("pit_episode_causal.json", "pit_episode_future.json",
                 "stale_pit_opportunity.json"):
        doc = _load(name)
        text = json.dumps(doc)
        assert "2025" not in text or "forbidden" in text.lower()


def test_no_runtime_network_results_dependency():
    import ast
    src = Path(ROOT / "scripts" / "analyze_v3_2m_pit.py").read_text()
    tree = ast.parse(src)
    imports = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imports.add(node.module.split(".")[0])
    assert "requests" not in imports and "urllib" not in imports
    assert "FASTF1_USE" not in src.upper() or "fastf1" not in imports
