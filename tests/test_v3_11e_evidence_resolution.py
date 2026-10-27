"""V3.11E VSC evidence resolution: focused guards (research only).

Pins the E evidence contract: predeclared protocol identity, fixed
thresholds, no coverage gate, causal duration handling with censoring,
episode-level (never pair-level) N, ending quarantine, pit
fail-closed retention, poison/parity properties, terminal B verdict,
and A/B/C/D + navigation-baseline integrity. Nothing here changes
eligibility, RaceState, MC2, or product behavior.
"""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_11e"
D = ROOT / "results" / "v3" / "v3_11d"

E_SCRIPTS = ("v3_11e_protocol.py", "v3_11e_duration.py",
             "v3_11e_evidence.py", "v3_11e_validate.py")


def _load_e(name):
    with open(OUT / name, encoding="utf-8") as fh:
        return json.load(fh)


def _load_d(name):
    with open(D / name, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def protocol():
    return _load_e("evidence_resolution_protocol.json")


@pytest.fixture(scope="module")
def validation():
    return _load_e("validation.json")


# ---- PROTOCOL ----

def test_protocol_predeclared_and_pinned(protocol):
    assert protocol["declared_before_scoring"] is True
    assert protocol["d_protocol_sha256"] == \
        "fd710c688c57abaab6e0ac31a7ca8e10a1cf0112bee875dc26cd5b33f9836d1f"
    body = {k: v for k, v in protocol.items() if k != "protocol_sha256"}
    blob = json.dumps(body, sort_keys=True,
                      separators=(",", ":")).encode("utf-8")
    assert hashlib.sha256(blob).hexdigest() == protocol["protocol_sha256"]
    assert _load_e("validation.json")["protocol_sha256"] == \
        protocol["protocol_sha256"]


def test_thresholds_fixed(protocol):
    assert protocol["gap_protocol"]["thresholds_unchanged"] == \
        "median <= 1.0s AND p90 <= 3.0s"
    assert protocol["spread_protocol"]["thresholds_unchanged"] == \
        "episode-median ratio in [0.8, 1.25]"
    assert "median AE on remaining duration <= 90s" in \
        protocol["duration_protocol"]["success_DUR3_sharpness"]
    assert "out-lap marginal N >= 15" in \
        protocol["pit_protocol"]["full_loss_bar"]
    assert protocol["uncertainty_method"].startswith(
        "episode-cluster bootstrap")
    assert "B=2000, seed=7" in protocol["gap_protocol"]["uncertainty"]


def test_no_coverage_gate(protocol, validation):
    assert protocol["no_coverage_gate"] is True
    assert "coverage" not in json.dumps(
        protocol["terminal_criteria"]).lower().replace(
            "coverage expansion", "")
    proj = _load_e("projected_eligibility.json")
    assert proj["status"] == "NOT_APPLICABLE"
    assert validation["classification"] != "VSC_EVIDENCE_RESOLVED"


# ---- DURATION ----

def test_duration_causal_features_only(protocol):
    d2 = _load_e("vsc_duration_analysis.json")["D2_conditional"]
    assert d2["covariate_set_if_allowed"] == ["elapsed VSC time at T"]
    assert d2["fitted"] is False
    assert "future withdrawal/duration/message/state in runtime " \
        "semantics" in protocol["forbidden_inputs"]
    assert "season=2025" in " ".join(protocol["forbidden_inputs"])


def test_duration_censoring_handled():
    qual = _load_e("vsc_duration_quality.json")
    assert qual["n_intervals"] == 82
    assert qual["right_censored"] == 2
    assert qual["competing_exits"] == 11
    assert qual["by_split"]["calibration_complete"] == 43
    assert qual["by_split"]["validation_complete"] == 37
    analysis = _load_e("vsc_duration_analysis.json")
    assert analysis["D1_empirical"]["method"].startswith("Kaplan-Meier")
    assert len(analysis["D1_empirical"]["km_table"]) > 10


def test_duration_queries_use_elapsed_marks_only():
    doc = _load_e("vsc_duration_validation.json")
    assert doc["query_marks_s"] == [30.0, 60.0, 120.0]
    assert doc["n_scored_queries"] == 62
    assert doc["hit_rate_80"] == pytest.approx(0.581, abs=1e-3)
    assert doc["median_ae_s"] == pytest.approx(56.9, abs=0.1)
    assert doc["DUR1_sample"] is True
    assert doc["DUR2_calibration"] is False
    assert doc["DUR3_sharpness"] is True
    assert doc["verdict"] == "UNDERPOWERED"


def test_duration_deterministic_bootstrap():
    for name in ("vsc_gap_power.json", "vsc_field_spread_power.json"):
        boot = _load_e(name)["bootstrap"]
        assert boot["B"] == 2000 and boot["seed"] == 7
    assert _load_e("validation.json")["stochastic_futures_run"] == 0
    assert _load_e("validation.json")["bootstrap_record"]["seed"] == 7


# ---- GAP/SPREAD ----

def test_no_pseudo_replication():
    gap = _load_e("vsc_gap_power.json")
    assert gap["independent_unit"] == "episode"
    assert gap["contributing_validation_episodes"] == 2
    assert gap["pair_observations"] == 17
    assert "never independent N" in gap["effective_N_note"]
    spread = _load_e("vsc_field_spread_power.json")
    assert spread["independent_unit"] == "episode"
    assert spread["contributing_validation_episodes"] == 3


def test_episode_aggregation_correct():
    gap = _load_e("vsc_gap_power.json")
    assert gap["bootstrap"]["method"] == "episode-cluster percentile CI"
    assert gap["median_ci95_s"] == pytest.approx([1.038, 2.854],
                                                 abs=1e-3)
    assert gap["point_gate_pass"] is False
    assert gap["verdict"] == "UNDERPOWERED"
    spread = _load_e("vsc_field_spread_power.json")
    assert spread["median_ci95"] == pytest.approx([1.1797, 1.5167],
                                                  abs=1e-3)
    assert spread["point_gate_pass"] is False
    assert spread["verdict"] == "UNDERPOWERED"


def test_validation_split_preserved(protocol):
    manifest = _load_e("temporal_split_manifest.json")
    assert manifest["split_changed"] is False
    assert len(manifest["episodes"]) == 82
    counts = manifest["counts"]
    assert counts["calibration|usable=True"] == 16
    assert counts["validation|usable=True"] == 13
    assert "validation split" in \
        _load_e("vsc_gap_evidence.json")["construction"]
    assert "no calibration mixing" in \
        _load_e("vsc_field_spread_evidence.json")["construction"]


# ---- ENDING ----

def test_ending_semantics_explicit():
    doc = _load_e("vsc_ending_analysis.json")
    assert doc["verdict"] in ("SAME_DYNAMICS",
                              "DISTINCT_TRANSITION_DYNAMICS",
                              "INSUFFICIENT_EVIDENCE")
    assert doc["verdict"] == "INSUFFICIENT_EVIDENCE"
    assert doc["n_ending_driver_laps"] == 7
    assert "vsc_ending" in doc["method"]
    assert doc["mae_s"] == pytest.approx(11.78, abs=0.01)


def test_ending_not_silently_merged():
    doc = _load_e("vsc_ending_analysis.json")
    assert "EXCLUDED" in doc["construction_consequence"]
    assert "excluded" in _load_e("vsc_gap_evidence.json")["construction"]
    assert "excluded" in \
        _load_e("vsc_field_spread_evidence.json")["construction"]


# ---- PIT ----

def test_pit_fail_closed_retained(validation):
    pit = _load_e("vsc_pit_loss_evidence.json")
    assert pit["verdict"] == "PIT_LOSS_INSUFFICIENT_EVIDENCE"
    assert pit["bar_met"] is False
    assert pit["primary_usable29"]["out_lap"]["count"] == 7
    assert pit["primary_usable29"]["in_lap"]["count"] == 73
    assert validation["gates"]["pit"] == "UNDERPOWERED"
    rel = _load_e("vsc_pit_relevance.json")
    assert rel["verdict"] == "PIT_MANDATORY_BLOCKER_RETAINED"


def test_no_invented_pit_adjustment():
    pit = _load_e("vsc_pit_loss_evidence.json")
    blob = json.dumps(pit).lower()
    assert "pit_loss_model" not in blob
    assert "adjustment" not in blob
    assert pit["secondary_all_nontruncated"]["out_lap"]["count"] == 14


# ---- POISON ----

def test_future_duration_withdrawal_status_pit_ignored():
    doc = _load_e("temporal_poison_validation.json")
    assert doc["verdict"] == "PASS"
    assert doc["d_contract_intact"] is True
    for needle in ("VSC withdrawal", "VSC duration", "GREEN transition",
                   "SC transition", "RED transition", "pit event",
                   "timing observation", "tyre observation"):
        assert needle in doc["injections_ignored_at_T"]


# ---- PARITY ----

def test_production_unchanged():
    doc = _load_e("parity_validation.json")
    assert doc["verdict"] == "PASS"
    assert doc["production_diff_empty"] is True
    assert doc["production_status_empty"] is True
    assert doc["production_diff_paths"] == []
    assert doc["green_rng_streams_changed"] is False
    assert doc["green_prediction_outputs_changed"] is False


def test_green_and_d_inputs_unchanged(validation):
    assert validation["stochastic_futures_run"] == 0
    assert _load_d("vsc_validation_protocol.json")["protocol_sha256"] == \
        "fd710c688c57abaab6e0ac31a7ca8e10a1cf0112bee875dc26cd5b33f9836d1f"
    assert _load_d("vsc_episode_quality.json")["usable"] == 29
    assert _load_d("validation.json")["integration_decision"] == \
        "INSUFFICIENT_EVIDENCE"


# ---- VERDICT ----

def test_classification_b_recorded(validation):
    assert validation["classification"] == \
        "VSC_EVIDENCE_STILL_INSUFFICIENT"
    assert validation["all_supported"] is False
    assert validation["duration_blocks_integration"] is True
    assert validation["gates"]["duration"] == "UNDERPOWERED"
    assert validation["gates"]["gap"] == "UNDERPOWERED"
    assert validation["gates"]["spread"] == "UNDERPOWERED"
    assert validation["gates"]["pit"] == "UNDERPOWERED"
    assert "REFUTED" not in set(validation["gates"].values())
    card = _load_e("scientific_card.json")
    assert card["classification"] == "VSC_EVIDENCE_STILL_INSUFFICIENT"
    assert card["production_effect"] == "none"


def test_d_supported_dimensions_retained(validation):
    assert validation["gates"]["pace"] == "SUPPORTED"
    assert validation["gates"]["order"] == "SUPPORTED"
    assert validation["gates"]["withdrawal"] == "SUPPORTED"
    table = _load_e("evidence_gate_table.json")
    assert table["values"]["pace_mae_pooled_s"] == pytest.approx(
        9.54, abs=0.01)
    assert table["values"]["order_steady_rate"] == pytest.approx(
        0.0469, abs=1e-4)


# ---- INTEGRITY ----

def test_e_scripts_offline_only():
    for script in E_SCRIPTS:
        src = (ROOT / "scripts" / script).read_text(encoding="utf-8")
        tree = ast.parse(src)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        assert "raceintel" not in imported, script
        assert "api" not in imported, script
        assert 'OUT = ROOT / "results" / "v3" / "v3_11e"' in src, script


def test_abcd_and_nav_baseline_intact():
    assert _load_d("scientific_card.json")["classification"] == \
        "VSC_REGIME_MODEL_INSUFFICIENT_EVIDENCE"
    for stage, cls in (
            ("v3_11a", "MC2_COVERAGE_FORENSICS_COMPLETE"),
            ("v3_11b", "CAUSAL_STATE_RECONSTRUCTION_REJECTED"),
            ("v3_11c", "TRACK_SOURCE_REGIME_FORENSICS_COMPLETE")):
        with open(ROOT / "results" / "v3" / stage / "scientific_card.json",
                  encoding="utf-8") as fh:
            assert json.load(fh)["classification"] == cls
    assert (ROOT / "docs" / "INDEX.md").exists()
    assert (ROOT / "scripts" / "README.md").exists()
    assert "VSC_EVIDENCE" in (ROOT / "docs" / "V3_11E_VSC_EVIDENCE_"
                              "RESOLUTION.md").read_text(encoding="utf-8")
