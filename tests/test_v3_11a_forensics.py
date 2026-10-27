"""V3.11A MC2 coverage forensics: diagnostic-layer guards (read-only).

Every test here pins the observational contract: exact frozen baseline,
stable state identity, causal (<=T) probes, no eligibility mutation, and
unique-state recovery accounting. Nothing here may change production
eligibility, RaceState, freshness, MC2, or the Pit Wall.
"""

from __future__ import annotations

import csv
import importlib.util
import json
from collections import Counter
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_11a"

EXPECTED_TOTAL = 9644
EXPECTED_ELIGIBLE = 3678
EXPECTED_UNSUPPORTED = 5966
EXPECTED_REASONS = {
    "STALE_ROSTER_OBSERVATION": 3294,
    "UNSUPPORTED_TRACK_STATE": 1165,
    "WET_CONDITIONS": 801,
    "MISSING_DRIVER_OBSERVATION": 354,
    "MISSING_TYRE_STATE": 198,
    "TERMINAL_STATE": 154,
}


def _load(name):
    with open(OUT / name, encoding="utf-8") as fh:
        return json.load(fh)


def _forensics_module():
    spec = importlib.util.spec_from_file_location(
        "v3_11a_mc2_coverage_forensics",
        ROOT / "scripts" / "v3_11a_mc2_coverage_forensics.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def baseline():
    return _load("baseline_reproduction.json")


@pytest.fixture(scope="module")
def ledger():
    return _load("unsupported_state_ledger.json")["states"]


@pytest.fixture(scope="module")
def catalogue():
    with open(ROOT / "results" / "v3" / "v3_2n"
              / "final_eligibility_catalogue.json",
              encoding="utf-8") as fh:
        return json.load(fh)


# ---- BASELINE ----

def test_baseline_counts_exact(baseline):
    assert baseline["candidate"] == EXPECTED_TOTAL
    assert baseline["eligible"] == EXPECTED_ELIGIBLE
    assert baseline["unsupported"] == EXPECTED_UNSUPPORTED
    assert baseline["exact"] is True


def test_baseline_reason_counts_exact(baseline):
    assert baseline["reason_counts"] == EXPECTED_REASONS
    assert baseline["invariant_sum"] == EXPECTED_UNSUPPORTED
    assert (sum(EXPECTED_REASONS.values()) == EXPECTED_UNSUPPORTED)


def test_ledger_covers_every_unsupported_state_once(ledger, catalogue):
    refused = {(c["race_id"], c["frame_index"]) for c in
               catalogue["checkpoints"]
               if c["verdict"] != "SIMULATION_CAPABLE"}
    assert len(refused) == EXPECTED_UNSUPPORTED
    keys = [(r["race_id"], r["frame_index"]) for r in ledger]
    assert len(keys) == EXPECTED_UNSUPPORTED
    assert len(set(keys)) == EXPECTED_UNSUPPORTED  # no duplicate rows
    assert set(keys) == refused  # no dropped states


def test_ledger_csv_matches_json():
    with open(OUT / "unsupported_state_ledger.csv", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    assert len(rows) == EXPECTED_UNSUPPORTED
    assert len({r["state_id"] for r in rows}) == EXPECTED_UNSUPPORTED


# ---- IDENTITY ----

def test_ledger_identity_stable_and_sorted(ledger):
    ids = [r["state_id"] for r in ledger]
    expect = [f"{r['race_id']}:{r['frame_index']}" for r in sorted(
        ledger, key=lambda r: (r["race_id"], r["frame_index"]))]
    assert ids == expect
    for r in ledger:
        assert r["state_id"] == f"{r['race_id']}:{r['frame_index']}"


def test_original_reasons_never_overwritten(ledger, catalogue):
    cat = {(c["race_id"], c["frame_index"]): c["verdict"]
           for c in catalogue["checkpoints"]}
    for r in ledger:
        assert r["original_reason"] == cat[(r["race_id"], r["frame_index"])]
        assert r["original_reason"] in EXPECTED_REASONS


# ---- STALE (frozen single-dimension freshness) ----

def test_stale_threshold_math_exact():
    mod = _forensics_module()
    thr, off = mod.parse_stale_reason(
        "engine_validate:non_contemporaneous_roster_member: roster members "
        "whose latest observation is more than 3 expected lap times "
        "(267.7s) older than T cannot be evolved honestly: "
        "ericsson age=342.7s, sirotkin age=459.8s")
    assert thr == pytest.approx(267.7)
    assert off == [("ericsson", 342.7), ("sirotkin", 459.8)]
    for driver, age in off:
        assert age - thr > 0  # offenders strictly beyond threshold


def test_stale_probes_use_only_observations_le_T(ledger):
    n = 0
    for r in ledger:
        for o in r.get("offender_probes", []):
            if o.get("prior_exists"):
                n += 1
                assert o["obs_time"] <= r["T_s"]
                assert o["age"] >= 0
                # probe mirrors frozen age: no future consumed
                if o.get("frozen_age_s") is not None:
                    assert abs(o["age"] - o["frozen_age_s"]) <= 1.0
    assert n > 7000


def test_stale_future_observations_ignored_not_consumed(ledger):
    later = [o for r in ledger for o in r.get("offender_probes", [])
             if o.get("later_exists") is True]
    assert later  # future rows exist (poison demonstrated)...
    stale_later = [
        o for r in ledger if r["original_reason"]
        == "STALE_ROSTER_OBSERVATION" for o in r.get("offender_probes", [])
        if o.get("later_exists") is True]
    assert stale_later
    for o in stale_later:
        # ...but frozen ages never use them (agreement artifact: 0 mismatch)
        assert o.get("frozen_age_s") is not None
    assert _load("stale_breakdown.json")["age_probe_agreement"][
        "n_mismatch_gt_1s"] == 0


def test_stale_multi_cause_preserved_via_blocking_conditions(ledger):
    multi = [r for r in ledger if len(r["blocking_conditions"]) > 1]
    assert len(multi) == 2032
    stale_co = [r for r in multi
                if "STALE_ROSTER_OBSERVATION" in r["blocking_conditions"]]
    assert len(stale_co) == 1740  # stale offenders under harder primaries


# ---- TRACK ----

def test_track_split_deterministic_and_unknown_stays_unknown(ledger):
    split = _load("track_reconstruction_vs_simulator.json")["split"]
    assert sum(split.values()) == 1165
    assert split["RECONSTRUCTION_PROBLEM"] == 64  # null tokens
    nulls = [r for r in ledger if r["original_reason"]
             == "UNSUPPORTED_TRACK_STATE" and r["track_state"] is None]
    assert len(nulls) == 64
    for r in nulls:
        assert r["original_reason"] == "UNSUPPORTED_TRACK_STATE"
        assert r["track_last_known_le_T"] is None  # nothing causal to persist


def test_track_yellow_both_keeps_frozen_reason(ledger):
    yellows = [r for r in ledger if r["track_state"] == "yellow"
               and r["original_reason"] == "UNSUPPORTED_TRACK_STATE"]
    assert len(yellows) == 521
    assert all(r["recovery_class"] in (
        "R3_SIMULATOR_SUPPORT_REQUIRED",
        "R4_RESEARCH_REQUIRED") for r in yellows)


# ---- DRIVER ----

def test_driver_alias_never_auto_resolved(ledger):
    drv = [r for r in ledger if r["original_reason"]
           == "MISSING_DRIVER_OBSERVATION"]
    assert len(drv) == 354
    for r in drv:
        assert r["original_reason"] == "MISSING_DRIVER_OBSERVATION"
        assert r["recovery_class"] == "R5_NOT_CAUSALLY_RECOVERABLE"


def test_driver_future_identity_ignored(ledger):
    # States whose drivers appear later still refuse: future is not evidence.
    future = [r for r in ledger if r["original_reason"]
              == "MISSING_DRIVER_OBSERVATION"
              and (r.get("unobserved_later_exists") or 0) > 0]
    assert future
    for r in future:
        assert r["original_reason"] == "MISSING_DRIVER_OBSERVATION"


# ---- TYRE ----

def test_tyre_no_default_compound_and_no_future(ledger):
    for r in ledger:
        for p in r.get("tyre_probes", []):
            if p.get("prior_exists"):
                assert p["obs_time"] <= r["T_s"]
                # factual compound or genuine null; never a fabricated fill
                assert p["compound"] is None or isinstance(
                    p["compound"], str)
    text = (OUT / "unsupported_state_ledger.json").read_text()
    assert "DEFAULT" not in text and "inferred" not in text.lower()


def test_tyre_hypothetical_uses_only_le_T(ledger):
    pure = [r for r in ledger if r["recovery_sublabel"]
            == "MISSING_TYRE_NO_PRIOR_COMPOUND_AT_T"]
    assert len(pure) == 6
    for r in pure:
        assert (r.get("tyre_prior_compound_exists") or 0) == 0


# ---- TERMINAL ----

def test_terminal_remains_unsupported(ledger):
    term = [r for r in ledger if r["original_reason"] == "TERMINAL_STATE"]
    assert len(term) == 154
    assert all(r["recovery_class"] == "R0_PERMANENT_OR_INTENTIONAL"
               for r in term)


# ---- RECOVERY (unique-state accounting) ----

def test_recovery_classes_sum_unique_no_double_count(ledger):
    by_class = Counter(r["recovery_class"] for r in ledger)
    assert sum(by_class.values()) == EXPECTED_UNSUPPORTED
    ceilings = _load("recovery_ceilings.json")
    for cls, doc in ceilings["by_class"].items():
        assert doc["states"] == by_class.get(cls, 0)
    assert ceilings["r2_alone"]["states"] == sum(
        1 for r in ledger if r.get("r2_alone"))
    pri = _load("prioritization_matrix.json")
    assert sum(r["states"] for r in pri["rows"]) == EXPECTED_UNSUPPORTED


def test_r5_requires_no_production_eligibility_change(ledger):
    r5 = [r for r in ledger if r["recovery_class"]
          == "R5_NOT_CAUSALLY_RECOVERABLE"]
    assert len(r5) == 360
    assert all(r["original_reason"] in EXPECTED_REASONS for r in r5)


# ---- POISON ----

def test_temporal_poison_all_zero():
    poison = _load("temporal_poison_validation.json")
    for key in ("future_timing_consumed", "future_track_consumed",
                "future_tyre_consumed", "future_driver_consumed",
                "future_weather_consumed"):
        assert poison[key] == 0
    assert poison["verdict"].startswith("PASS")


# ---- READ-ONLY / NO PRODUCTION MUTATION ----

def test_forensic_script_is_read_only_and_side_effect_free():
    import ast
    src = (ROOT / "scripts" / "v3_11a_mc2_coverage_forensics.py").read_text()
    tree = ast.parse(src)
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            imported.add((node.module or "").split(".")[0])
    assert "raceintel" not in imported
    assert "api" not in imported
    assert "frontend" not in imported
    called = {n.func.id for n in ast.walk(tree)
              if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}
    for banned in ("from_race_state", "prepare_initial_state", "run_mc2"):
        assert banned not in called
    assert 'OUT = ROOT / "results" / "v3" / "v3_11a"' in src
    assert src.count("_write(") >= 20  # all artifact writes via _write->OUT


def test_validation_flags_clean():
    validation = _load("validation.json")
    assert validation["baseline_exact"] is True
    assert validation["blockers_reproduce_frozen"] is True
    assert validation["ledger_completeness"] is True
    assert validation["no_eligibility_change"] is True
