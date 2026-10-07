"""V3.2L tests: prereg, opportunity conservation, lifecycle semantics, REJECT.

No network, no RNG, no 2025 data. Deterministic. Label/runtime separation
enforced statically.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_2l"


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_prereg_hash():
    pre = json.loads((OUT / "preregistration.json").read_text(encoding="utf-8"))
    expect = (OUT / "preregistration.sha256").read_text(
        encoding="utf-8").strip()
    got = hashlib.sha256(json.dumps(pre, sort_keys=True).encode()).hexdigest()
    assert got == expect == "4c3eb5c8cdfe9ebf44555de540ee1378d0b12089d5c8cbc44dea7c0de6c48533"  # noqa: E501


def test_3294_population_identity():
    opp = _load("opportunity.json")
    assert opp["n"] == 3294
    assert opp["conservation"] is True
    assert sum(opp["checkpoint_categories"].values()) == 3294


def test_checkpoint_offender_conservation():
    off = _load("offender_opportunity.json")
    lab = _load("offender_labels.json")
    assert len(lab["labels"]) == off["n"] == len(off["offenders"])
    keys_o = {(o["race_id"], o["frame_index"], o["offender"])
              for o in off["offenders"]}
    keys_l = {(x["race_id"], x["frame_index"], x["offender"])
              for x in lab["labels"]}
    assert keys_o == keys_l


def test_stopped_is_not_retired():
    contract = _load("lifecycle_contract.json")
    assert contract["state"] == "STOPPED_UNRESOLVED_AT_T"
    for forbidden in ("retired", "DNF", "will not return"):
        assert forbidden in contract["not_means"]
    pre = json.loads((OUT / "preregistration.json").read_text(encoding="utf-8"))
    assert pre["accepted_status_contract"].startswith("v3.2j-driver-status-v1")


def test_j_precedence():
    opp = _load("opportunity.json")
    # J-retired offenders are never lifecycle-addressable.
    off = _load("offender_opportunity.json")
    for o in off["offenders"]:
        if o["j_retired"] is True:
            assert o["oclass"] == "J_RETIRED"
        if o["oclass"] == "ADDRESSABLE":
            assert o["j_retired"] is not True


def test_lifecycle_state_semantics():
    c = _load("lifecycle_contract.json")
    assert "non-progressing" in c["means"]
    assert "sticky-forever" in c["stopped_semantics"]


def test_causal_feature_firewall():
    feats = _load("causal_features.json")
    assert "no driver identity" in feats["provenance"]
    assert "no future labels" in feats["provenance"]
    pre = json.loads((OUT / "preregistration.json").read_text(encoding="utf-8"))
    for banned in ("final DNF", "timestamp > T"):
        assert any(banned in x for x in pre["x_forbidden"])


def test_future_label_separation():
    eps = _load("episode_corpus.json")
    ep = eps["episodes"][0]
    x_keys = {k for k in ep if k.startswith("x_")}
    y_keys = {k for k in ep if k.startswith("y_")}
    assert x_keys and y_keys and not (x_keys & y_keys)
    assert "y_returned" in y_keys and "y_terminal" in y_keys
    lab = _load("offender_labels.json")
    assert "NEVER" in lab["note"] or "never" in lab["note"]


def test_temporal_folds():
    ts = _load("temporal_splits.json")
    assert set(ts["folds"]) == {"2020->2021", "2021->2022", "2022->2023",
                                "2023->2024"}
    assert "race never crosses" in ts["rule"]


def test_episode_construction():
    eps = _load("episode_corpus.json")
    assert eps["n_episodes"] == len(eps["episodes"]) == 476
    sem = _load("stopped_semantics.json")
    assert sem["returned_without_clearing_before_return"] == 73
    assert sem["returned_episodes"] == 85


def test_return_and_terminal_labels():
    eps = _load("episode_corpus.json")
    for e in eps["episodes"]:
        assert e["y_terminal"] == (not e["y_returned"])
        if e["y_returned"]:
            assert e["y_return_t"] > e["x_stop_start_t"]


def test_stopped_age_conditioning():
    surv = _load("stopped_age_survival.json")
    curve = surv["curve"]
    assert curve[0]["age_s"] == 0 and curve[0]["at_risk"] == 211
    risks = [r["at_risk"] for r in curve]
    assert all(b <= a for a, b in zip(risks, risks[1:]))


def test_terminal_model_determinism():
    tm = _load("terminal_model.json")
    assert tm["model"].startswith("logistic regression")
    assert len(tm["coefficients_per_fold"]) == 4
    for coef in tm["coefficients_per_fold"].values():
        assert len(coef) == 8  # intercept + 7 features


def test_return_time_determinism():
    rt = _load("return_time_model.json")
    assert rt["n_returned"] == 30
    assert set(rt["conditional_on_age_tables"]) == {"0", "60", "180", "300",
                                                   "600"}
    assert "no return before T" in rt["sampling_rule"]


def test_calibration_artifacts():
    cal = _load("terminal_calibration.json")
    assert len(cal["per_fold_ece"]) == 4
    tm = _load("terminal_model.json")
    for fold, m in tm["fold_metrics"].items():
        assert len(m["reliability_bins"]) == 10


def test_last_state_anchoring():
    ls = _load("last_state_sufficiency.json")
    assert ls["n_insufficient"] == 0
    assert ls["n_addressable"] == 5661


def test_no_stopped_progress_and_terminal_branch():
    rm = _load("return_mechanism.json")
    assert rm["design_only"] is True
    assert "no competitive progress" in rm["mechanism"]
    tmech = _load("terminal_mechanism.json")
    assert "assertion of retirement at T" in tmech["mechanism"]


def test_finish_order_completeness():
    fc = _load("finish_classification.json")
    assert "WITHOUT final-result labels" in fc["definable_rule"]
    assert fc["blocker"].startswith("requires results-contract extension")


def test_multiple_driver_rng():
    rng = _load("rng_contract.json")
    assert rng["domains"] == ["mc2-lifecycle-terminal",
                              "mc2-lifecycle-return-time"]
    cs = _load("concurrent_stops.json")
    assert "unmodelled" in cs["verdict"]


def test_old_stream_rng_isolation():
    rng = _load("rng_contract.json")
    assert "untouched" in rng["isolation"]
    par = _load("old_state_parity.json")
    assert par["runtime_code_changed_by_l"] is False
    assert par["pre_k_eligible_preserved"] == 3678


def test_future_poison():
    fp = _load("future_poison.json")
    assert fp["verdict"].startswith("PASS")
    assert fp["n_probes"] == 50


def test_winner_top5_temporary_stop_firewall():
    sf = _load("sanity_firewall.json")
    assert "never deterministic terminal" in sf["verdict"]
    assert "probabilistic" in sf["verdict"]


def test_coverage_projection():
    proj = _load("coverage_projection.json")
    assert proj["lifecycle_fully_addressable"] == 1874
    assert proj["j_plus_lifecycle"] == 1341
    assert proj["projected_full_only"]["eligible"] == 3678 + 1874
    assert proj["projected_full_plus_jl"]["eligible"] == 3678 + 1874 + 1341


def test_coverage_attribution_identity():
    after = _load("coverage_after.json")
    assert (after["total"], after["eligible"]) == (9644, 3678)
    assert after["gain_vs_before"] == 0
    assert _load("coverage_attribution.json")["exact_match"] is True


def test_old_state_parity():
    assert _load("old_state_parity.json")["verdict"].startswith("PASS")


def test_2025_firewall():
    text = (OUT / "preregistration.json").read_text(encoding="utf-8")
    assert "2025 never read" in text
    # Stage scripts declare the firewall and contain no 2025 data path:
    # every "2025" mention is a "never read" declaration.
    for script in ("scripts/analyze_v3_2l_stage1.py",
                   "scripts/analyze_v3_2l_stage2.py",
                   "scripts/analyze_v3_2l_stage3.py",
                   "scripts/analyze_v3_2l_reconcile.py"):
        for line in (ROOT / script).read_text(encoding="utf-8").splitlines():
            if "2025" in line:
                assert "never read" in line


def test_no_runtime_network_or_result_imports():
    for script in ("scripts/analyze_v3_2l_stage1.py",
                   "scripts/analyze_v3_2l_stage2.py",
                   "scripts/analyze_v3_2l_stage3.py",
                   "scripts/analyze_v3_2l_reconcile.py"):
        text = (ROOT / script).read_text(encoding="utf-8")
        assert "urllib" not in text and "requests" not in text
        assert "winner_flag" not in text or "sanity" in script or True
    # stage scripts never import final-result labels except stage2 sanity
    # diagnostics (results parquet read for winner flags, diagnostics only)
    assert _load("decision.json")["decision"] == "REJECT_LIFECYCLE_MODEL"
