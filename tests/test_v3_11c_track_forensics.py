"""V3.11C track-source & regime forensics: focused guards (read-only).

Pins the C research contract: exact TRACK baseline, NULL/UNKNOWN
semantics, persistence boundaries, exposure taxonomy, ledger
completeness, unique-state ceilings, poison properties, and zero
production effect. Nothing here changes eligibility, RaceState,
freshness, MC2, or product behavior.
"""

from __future__ import annotations

import ast
import csv
import json
from bisect import bisect_right
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_11c"
A = ROOT / "results" / "v3" / "v3_11a"

EXPECTED_TRACK = 1165
EXPECTED_SPLIT = {"BOTH": 521, "RECONSTRUCTION": 64,
                  "SIMULATOR_CAPABILITY": 580}


def _load(name):
    with open(OUT / name, encoding="utf-8") as fh:
        return json.load(fh)


def causal_token(times_tokens, T):
    """Offline C resolver: modal token at max(t <= T); None if unknown."""
    prior = [(t, tok) for t, tok in times_tokens if t <= T]
    if not prior:
        return None
    maxt = max(t for t, _ in prior)
    toks = [tok for t, tok in prior if t == maxt and tok is not None]
    if not toks:
        return None
    from collections import Counter
    return Counter(toks).most_common(1)[0][0]


@pytest.fixture(scope="module")
def ledger():
    with open(OUT / "track_candidate_ledger.csv", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


# ---- BASELINE ----

def test_track_baseline_reproduced_exactly(ledger):
    assert len(ledger) == EXPECTED_TRACK
    assert len({r["state_id"] for r in ledger}) == EXPECTED_TRACK
    catalogue = json.loads(
        (ROOT / "results" / "v3" / "v3_2n"
         / "final_eligibility_catalogue.json").read_text(encoding="utf-8"))
    frozen = {(c["race_id"], c["frame_index"]) for c in
              catalogue["checkpoints"]
              if c["verdict"] == "UNSUPPORTED_TRACK_STATE"}
    assert len(frozen) == EXPECTED_TRACK
    assert {(r["race_id"], int(r["frame_index"])) for r in ledger} == frozen


def test_split_reproduces_A(ledger):
    from collections import Counter
    split = Counter(r["split"] for r in ledger)
    assert dict(split) == EXPECTED_SPLIT
    doc = _load("reconstruction_capability_split.json")
    assert doc["delta_vs_A"].startswith("zero")


def test_ledger_completeness_and_categories(ledger):
    for r in ledger:
        assert r["split"] in ("RECONSTRUCTION", "SIMULATOR_CAPABILITY",
                              "BOTH", "UNKNOWN")
        assert r["causal_known"] in ("True", "False")
        assert r["regime"] in ("YELLOW", "VSC", "SC", "RED", "UNKNOWN")
        assert r["disposition"]


# ---- NULL ----

def test_pre_first_message_remains_unknown(ledger):
    nulls = [r for r in ledger if r["token"] == ""]
    assert len(nulls) == 64
    for r in nulls:
        assert r["causal_known"] == "False"
        assert r["split"] == "RECONSTRUCTION"
        assert r["disposition"] == "NULL_UNKNOWN_PERSIST"


def test_null_analysis_holds_H0(ledger):
    doc = _load("null_track_analysis.json")
    assert doc["n_null"] == 64
    assert doc["pre_first_message"] == 64
    assert "HELD for all 64" in doc["H0_no_message_means_unknown"]
    assert "REJECTED" in doc["H1_session_starts_green"]
    assert "GREEN LIGHT - PIT EXIT OPEN" in doc["H2_other_source_proves_green"]


def test_first_future_message_ignored_by_resolver():
    # Pre-first-observation T stays UNKNOWN however the future reads.
    base = [(100.0, None), (200.0, None)]
    assert causal_token(base, 50.0) is None
    for future in ("all_clear", "yellow", "vsc", "safety_car", "red_flag"):
        extended = base + [(300.0, future)]
        assert causal_token(extended, 50.0) is None  # type cannot alter T


def test_no_default_green_in_artifacts(ledger):
    for r in ledger:
        if r["token"] == "":
            assert r["causal_known"] == "False"
    text = (OUT / "track_candidate_ledger.csv").read_text()
    assert "DEFAULT_GREEN" not in text


# ---- PERSISTENCE ----

def test_persistence_requires_explicit_observation():
    assert causal_token([(100.0, None)], 150.0) is None  # no persistence
    assert causal_token([(100.0, "all_clear")], 150.0) == "all_clear"
    doc = _load("post_observation_persistence.json")
    assert doc["contract"] == \
        "EXPLICIT_STATUS_PERSISTS_UNTIL_EXPLICIT_SUPERSESSION"


def test_supersession_boundary_exact():
    series = [(100.0, "all_clear"), (200.0, "yellow"), (300.0, "all_clear")]
    assert causal_token(series, 199.9) == "all_clear"
    assert causal_token(series, 200.0) == "yellow"  # equality: lap-end clock
    assert causal_token(series, 299.9) == "yellow"
    assert causal_token(series, 300.0) == "all_clear"


def test_no_nearest_message_behavior():
    series = [(100.0, "all_clear"), (500.0, "yellow")]
    assert causal_token(series, 490.0) == "all_clear"  # not nearest (500)


# ---- YELLOW ----

def test_yellow_never_global():
    vocab = _load("raw_track_status_vocabulary.json")
    assert vocab["rc_flag_x_scope"].get("YELLOW|Track", 0) == 0
    assert vocab["rc_flag_x_scope"].get("DOUBLE YELLOW|Track", 0) == 0
    doc = _load("yellow_exposure_classification.json")
    assert doc["n_states"] == 521
    assert sum(doc["by_exposure"].values()) == 521
    assert doc["by_exposure"].get("GLOBAL_OR_SESSION_WIDE", 0) == 0


def test_unknown_exposure_remains_unknown():
    doc = _load("yellow_exposure_classification.json")
    assert doc["by_exposure"].get("LOCAL_EXPOSURE_UNKNOWN", 0) > 0
    assert doc["by_exposure"].get("UNKNOWN", 0) > 0


# ---- VSC/SC ----

def test_vsc_activation_after_T_invisible():
    series = [(100.0, "all_clear"), (500.0, "vsc")]
    assert causal_token(series, 499.9) == "all_clear"
    doc = _load("vsc_forensics.json")
    assert doc["vsc_intervals"] > 0
    assert doc["vsc_followed_by_vsc_ending"] > 0


def test_sc_withdrawal_after_T_invisible():
    series = [(100.0, "safety_car"), (500.0, "all_clear")]
    assert causal_token(series, 499.9) == "safety_car"
    doc = _load("sc_forensics.json")
    assert doc["sc_intervals"] > 0
    assert "DEPLOYED" in doc["rc_safetycar_statuses"]


# ---- RED ----

def test_no_reconstruction_across_restart():
    doc = _load("red_flag_forensics.json")
    assert doc["post_red_clock_gap_s"]["median"] is not None
    assert "remains unsupported by design" in doc["conclusion"]
    series = [(100.0, "safety_car"), (200.0, "red_flag"),
              (2000.0, "all_clear")]
    # Offline resolver reports the restart regime; production must never
    # bridge the discontinuity (no implementation exists to do so).
    assert causal_token(series, 150.0) == "safety_car"
    assert causal_token(series, 500.0) == "red_flag"


# ---- SECONDARY BLOCKERS + CEILINGS ----

def test_secondary_blocker_arithmetic_unique():
    doc = _load("secondary_blockers.json")
    total = sum(doc["secondary_sets"].values())
    assert total == EXPECTED_TRACK
    assert doc["secondary_sets"].get("NONE", 0) == 292
    free = doc["secondary_free_causally_known_by_regime"]
    assert sum(free.values()) == 233  # 292 TRACK-only minus 59 unknown nulls
    ceilings = _load("coverage_ceilings.json")
    assert ceilings["combined_secondary_free"]["states"] == 233
    assert ceilings["combined_secondary_free"]["ceiling_eligible"] == 3911
    assert "NOT EXPECTED PRODUCTION COVERAGE" in ceilings["label"]


def test_regime_support_erases_no_unrelated_blocker(ledger):
    for r in ledger:
        if r["secondary_blockers"]:
            assert r["disposition"] in (
                "YELLOW_LOCAL_REGIME_SUPPORT_NEEDED", "VSC_SUPPORT_NEEDED",
                "SC_SUPPORT_NEEDED", "RED_UNSUPPORTED_BY_DESIGN",
                "NULL_UNKNOWN_PERSIST")


# ---- POISON ----

def test_future_status_and_rc_ignored():
    series = [(100.0, "all_clear"), (200.0, "yellow")]
    assert causal_token(series, 150.0) == "all_clear"
    poisoned = series + [(160.0, "safety_car"), (170.0, "red_flag")]
    assert causal_token(poisoned, 150.0) == "all_clear"
    doc = _load("temporal_poison_validation.json")
    assert doc["verdict"].startswith("PASS")


# ---- READ-ONLY / NO PRODUCTION EFFECT ----

def test_c_scripts_are_read_only_and_side_effect_free():
    for script in ("v3_11c_sources.py", "v3_11c_regimes.py",
                   "v3_11c_ledger.py"):
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


def test_no_production_implementation_markers():
    for path in (ROOT / "raceintel").rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "EXPLICIT_STATUS_PERSISTS_UNTIL_EXPLICIT_SUPERSESSION" \
            not in text
        assert "V3_11C" not in text


def test_validation_clean():
    validation = _load("validation.json")
    assert validation["track_baseline_reproduced_1165"] is True
    assert validation["ledger_rows_unique_1165"] is True
    assert validation["no_eligibility_change"] is True
    assert validation["mc2_futures_run"] == 0
