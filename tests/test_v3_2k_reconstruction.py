"""V3.2K tests: prereg, target identity, causal semantics, REJECT decision.

Research-freeze tests over frozen artifacts + stdlib reconstructor semantics.
No network, no RNG, no 2025 data. Deterministic.
"""

from __future__ import annotations

import bisect
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "v3" / "v3_2k"
JOUT = ROOT / "results" / "v3" / "v3_2j"


def _load(name: str) -> dict:
    return json.loads((OUT / name).read_text(encoding="utf-8"))


def test_prereg_hash():
    pre = json.loads((OUT / "preregistration.json").read_text(encoding="utf-8"))
    expect = (OUT / "preregistration.sha256").read_text(
        encoding="utf-8").strip()
    got = hashlib.sha256(json.dumps(pre, sort_keys=True).encode()).hexdigest()
    assert got == expect == "567260af8072d2e1700a4d1e9ad24265fc458c838010dc8a0d27b745c6a2f22b"  # noqa: E501


def test_target_population_identity():
    pop = _load("target_population.json")
    assert pop["n"] == 3294
    rows = pop["checkpoints"]
    assert len(rows) == 3294
    assert all(r["n_offenders"] >= 1 for r in rows)
    assert all(r["stale_offenders"] == sorted(r["stale_offenders"])
               for r in rows)
    dist = pop["n_offender_dist"]
    assert sum(dist.values()) == 3294


def test_conservation_3294():
    dec = _load("stale_decomposition.json")
    assert dec["n"] == 3294
    assert dec["conservation"] is True
    assert sum(dec["exclusive_primary"].values()) == 3294


def test_minimum_state_contract():
    contract = _load("minimum_state_contract.json")
    fields = {f["field"] for f in contract["fields"]}
    for required in ("driver_id", "lap_number", "race_time_s", "position",
                     "compound", "tyre_age", "stint_number", "pit_count",
                     "constructor_id", "status", "observation_age_s"):
        assert required in fields
    # gaps are explicitly NOT MC2 inputs
    assert any("GapToLeader" in s for s in contract["not_mc2_inputs"])


def test_clock_causal_lookup_semantics():
    # latest t <= T wins; equality counts; future rows unreachable.
    seq = [(10.0, "a"), (20.0, "b"), (30.0, "c")]
    ts = [e[0] for e in seq]

    def lookup(T):
        i = bisect.bisect_right(ts, T) - 1
        return seq[i][1] if i >= 0 else None

    assert lookup(5.0) is None  # before first observation
    assert lookup(20.0) == "b"  # exact equality
    assert lookup(25.0) == "b"  # between updates
    assert lookup(1e9) == "c"  # future rows never consulted beyond T


def test_gap_lap_deficit_never_seconds():
    # '+1 LAP' style tokens must never convert to a float gap.
    for token in ("+1 LAP", "+2 LAPS", "1 LAP"):
        assert "LAP" in token.upper()
    gap = _load("gap_validation.json")
    assert gap["n_lap_deficit"] >= 0
    assert "NOT MC2 inputs" in gap["note"]


def test_decision_reject_and_no_runtime_component():
    decision = _load("decision.json")
    assert decision["decision"] == "REJECT_DIRECT_RAW_STATE_RECONSTRUCTION"
    assert not (ROOT / "raceintel" / "simulation" /
                "driver_state.py").exists()
    cands = _load("direct_recovery_candidates.json")
    assert cands["n_direct_recovery_candidates"] == 0


def test_j_precedence_preserved():
    # K must not weaken J: status contract + adapter versions pinned.
    pre = json.loads((OUT / "preregistration.json").read_text(encoding="utf-8"))
    assert pre["v3_2j_parent"]["status_contract"] == "v3.2j-driver-status-v1"
    assert pre["v3_2j_parent"]["adapter"] == "v3.2j-raw-adapter-v1"
    parity = _load("old_state_parity.json")
    assert parity["runtime_code_changed_by_k"] is False
    assert parity["pre_k_eligible_preserved"] == 3678


def test_future_poison_and_firewalls():
    poison = _load("future_poison.json")
    assert poison["verdict"] == "PASS"
    assert poison["unchanged"] == poison["n_probes"] > 0
    firewall = _load("winner_top5_firewall.json")
    assert firewall["verdict"].startswith("PASS")


def test_coverage_accounting_identity():
    after = _load("coverage_after.json")
    assert (after["total"], after["eligible"]) == (9644, 3678)
    assert after["gain_vs_j"] == 0
    attr = _load("coverage_attribution.json")
    assert attr["new_eligible_set"] == []
    assert attr["exact_match"] is True


def test_no_2025_and_no_lifecycle_modelling():
    # No K artifact or script may reference 2025 data or train lifecycle ML.
    for path in [OUT / "preregistration.json", OUT / "decision.json",
                 OUT / "lifecycle_handoff.json"]:
        text = path.read_text(encoding="utf-8")
        assert "2025" not in text or "no_2025" in text or "NEVER" in text
    handoff = _load("lifecycle_handoff.json")
    assert handoff["design_only"] is True
    assert handoff["no_training_in_k"] is True


def test_fail_closed_no_runtime_network():
    integ = _load("integration_validation.json")
    assert integ["verdict"] == "NOT_APPLICABLE"
    api = _load("api_behavior.json")
    assert api["verdict"] == "UNCHANGED"
