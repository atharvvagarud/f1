"""V3.11D VSC regime model: focused guards (research only).

Pins the D research contract: prior review, causal interval contract,
episode quality, pre-declared protocol, research-model isolation,
gate results, INSUFFICIENT_EVIDENCE verdict, fail-closed matrix,
poison/boundary properties, and zero production effect. Nothing here
changes eligibility, RaceState, MC2, or product behavior.
"""

from __future__ import annotations

import ast
import csv
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_11d"

sys.path.insert(0, str(ROOT / "scripts"))
from v3_11d_vsc_model import (  # noqa: E402
    MODEL_VERSION,
    fail_closed,
    gap_preserved,
    interval_state,
    vsc_expected_lap_time,
)

PROTOCOL_SHA = "fd710c688c57abaab6e0ac31a7ca8e10a1cf0112bee875dc26cd5b33f9836d1f"


def _load(name):
    with open(OUT / name, encoding="utf-8") as fh:
        return json.load(fh)


@pytest.fixture(scope="module")
def results():
    return _load("vsc_validation_results.json")


# ---- INTERVAL ----

def test_activation_causal_and_future_invisible():
    assert interval_state("vsc") == (True, "VSC_ACTIVE")
    doc = _load("vsc_interval_contract.json")
    assert doc["activation_tokens"] == ["vsc"]
    assert "invisible" in doc["equality_semantics"]


def test_withdrawal_causal_and_future_invisible():
    assert interval_state("vsc_ending") == (False, "WITHDRAWAL_OBSERVED")
    assert interval_state("all_clear") == (False, "GREEN")


def test_pre_first_remains_unknown():
    assert interval_state(None) == (False, "UNKNOWN_PRE_FIRST")


# ---- MODEL ----

def test_model_only_active_inside_valid_interval():
    assert vsc_expected_lap_time(90.0, 1.272) == pytest.approx(114.48)
    assert gap_preserved(12.5) == 12.5  # uniform ratio carries gaps
    with pytest.raises(ValueError):
        vsc_expected_lap_time(-90.0, 1.272)


def test_fail_closed_matrix():
    assert fail_closed("safety_car") is not None  # VSC->SC
    assert fail_closed("red_flag") is not None  # VSC->RED
    assert fail_closed(None) == "UNKNOWN_PRE_FIRST"  # ambiguous
    assert fail_closed("vsc", withdrawal_known=False) is not None
    assert fail_closed("vsc", pit_event_under_vsc=True) is not None
    assert fail_closed("vsc") is None  # valid interval proceeds


def test_green_path_exact_parity():
    doc = _load("green_parity_validation.json")
    assert doc["production_diff_empty"] is True
    assert doc["green_rng_streams_changed"] is False
    assert doc["green_prediction_outputs_changed"] is False


# ---- PACE ----

def test_calibrated_parameter_deterministic(results):
    assert results["model_version"] == MODEL_VERSION
    assert results["calibration"]["R_median"] == pytest.approx(1.272, abs=1e-3)
    assert results["protocol_sha256"] == PROTOCOL_SHA


def test_validation_split_respected():
    quality = _load("vsc_episode_quality.json")
    assert quality["usable_by_split"]["calibration"] == 16
    assert quality["usable_by_split"]["validation"] == 13
    assert set(["calibration", "validation"]) == set(
        quality["usable_by_split"])


def test_no_future_labels_in_runtime_input():
    import inspect
    src = inspect.getsource(vsc_expected_lap_time)
    assert "next" not in src and "future" not in src
    model_src = (ROOT / "scripts" / "v3_11d_vsc_model.py").read_text()
    assert "raceintel" not in model_src


# ---- GAP/ORDER ----

def test_gap_semantics_no_sc_compression(results):
    assert results["validation"]["gap_baseline_median_s"] is not None
    assert results["validation"]["gap_steady_median_s"] is not None
    # No SC-like compression asserted anywhere in D artifacts.
    for name in ("vsc_gap_analysis.json", "vsc_field_spread_analysis.json",
                 "vsc_validation_results.json"):
        text = (OUT / name).read_text()
        assert "compression" not in text.lower()


def test_order_freezes_in_steady_state(results):
    assert results["validation"]["order_steady_rate"] is not None
    assert results["validation"]["order_steady_rate"] <= 0.15


# ---- PIT ----

def test_pit_adjustment_absent_and_fail_closed():
    assert fail_closed("vsc", pit_event_under_vsc=True) == \
        "PIT_UNDER_VSC_NO_VALIDATED_LOSS"
    protocol = _load("vsc_validation_protocol.json")
    assert "EXCLUDED" in protocol["candidates"]["V3"]


# ---- RNG ----

def test_green_rng_unchanged_and_reproducible():
    doc = _load("green_parity_validation.json")
    assert doc["green_rng_streams_changed"] is False
    assert vsc_expected_lap_time(90.0, 1.272) == \
        vsc_expected_lap_time(90.0, 1.272)
    validation = _load("validation.json")
    assert validation["stochastic_futures_run"] == 0


# ---- SECONDARY ----

def test_other_blockers_preserved():
    doc = _load("secondary_blocker_validation.json")
    assert doc["vsc_secondary_free_anchors"] == 41
    assert doc["other_blockers_preserved"] == [
        "STALE", "WET", "MISSING_DRIVER", "MISSING_TYRE", "TERMINAL"]
    proj = _load("projected_eligibility.json")
    assert proj["status"] == "NOT_APPLICABLE_MODEL_NOT_ACCEPTED"


# ---- POISON ----

def test_future_regime_timing_tyre_pit_ignored():
    doc = _load("temporal_poison_validation.json")
    assert doc["verdict"] == "PASS"
    assert "VSC activation" in doc["injections_ignored_at_T"]
    assert "pit event" in doc["injections_ignored_at_T"]


def test_boundaries_explicit():
    doc = _load("boundary_validation.json")
    assert doc["activation_gt_T"] == "invisible"
    assert doc["withdrawal_gt_T"] == "invisible until observed"
    assert doc["vsc_to_sc"] == "FAIL CLOSED (refuse)"
    assert doc["vsc_to_red"] == "FAIL CLOSED (refuse)"
    assert doc["nearest_transition"] == "absent"


# ---- VERDICT ----

def test_insufficient_evidence_recorded():
    validation = _load("validation.json")
    assert validation["integration_decision"] == "INSUFFICIENT_EVIDENCE"
    assert validation["all_required_pass"] is False
    assert validation["gates"]["G1_pace"] is True
    assert validation["gates"]["G2_gap"] is False
    assert validation["duration_blocks_integration"] is True
    card = _load("scientific_card.json")
    assert card["classification"] == "VSC_REGIME_MODEL_INSUFFICIENT_EVIDENCE"
    assert card["production_effect"] == "none"


def test_d_scripts_are_read_only_and_side_effect_free():
    for script in ("v3_11d_episodes.py", "v3_11d_analyze.py",
                   "v3_11d_protocol.py", "v3_11d_vsc_model.py",
                   "v3_11d_validate.py"):
        tree = ast.parse(
            (ROOT / "scripts" / script).read_text(encoding="utf-8"))
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom):
                imported.add((node.module or "").split(".")[0])
        assert "raceintel" not in imported, script
        assert "api" not in imported, script
