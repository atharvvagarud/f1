"""V3.6H freeze tests: final immutable invariants for Strategy 2.0.

Source-safe (tracked files + git only). Designed to stay green after the
V3.6 tag exists: no assertion requires any tag to be absent.
"""

import hashlib
import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARD = ROOT / "results" / "v3" / "v3_6_final_scientific_card.json"
FREEZE = ROOT / "results" / "v3" / "v3_6_freeze.json"

A = "2d29c19b47b24035f0d1c503fccc8cd4090595b4ebb2a980001d0a919b0ae59b"
B = "df821fe13ed587d7a086e93b8ee53a1670130299ca92c5a668608add443e3644"
D = "0c2bf7fb6e46a948d811587a64aac89cb10cfe0bf67485ed9ff3b457d64088fc"
PARENT = "6df5d41d3ebead9a1c9b4f0f40ed20a21ce0bff1"


def _load(path):
    return json.loads(path.read_text())


def _git(*args):
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, check=True
    ).stdout.strip()


def _card():
    return _load(CARD)


# --- parent / stage identities ---


def test_parent_identity():
    assert _card()["parent"] == {
        "tag": "v3.5-outcome-distribution", "commit": PARENT}


def test_head_parent_before_freeze_commit():
    # V3.8H reconciliation: the HEAD-position pin is stale after the V3.7
    # freeze (HEAD is legitimately two+ commits past the v3.5 tag).
    # Final-state invariant preserving the original intent (V3.6 freeze is
    # exactly one commit atop the v3.5 parent; no history rewrite): the
    # frozen parent is an ancestor of HEAD, and the recorded V3.6 freeze
    # commit is a direct child of the parent.
    head = _git("rev-parse", "HEAD")
    out = subprocess.run(
        ["git", "merge-base", "--is-ancestor", PARENT, head],
        cwd=ROOT, capture_output=True)
    assert out.returncode == 0, head
    assert _git("rev-parse", "v3.6-strategy-2.0^{commit}") == \
        "1eb462631b9d7a948e35b8a1658e3bb90035c94c"
    assert _git("rev-parse", "v3.6-strategy-2.0^{commit}^") == PARENT


def test_a_identity():
    assert _card()["a_identity"] == A


def test_b_identity():
    assert _card()["b_identity"] == B


def test_c_identity():
    assert _card()["c_engine_identity"] == "v3.6c-engine-v1"


def test_d_protocol_identity():
    assert _card()["d_protocol_identity"] == D


def test_d_refinement_decision():
    assert _card()["d_conclusion"] == "REFINEMENT_NOT_WARRANTED"


def test_e_absent():
    assert _card()["e_status"] == "SKIPPED_BY_V3.6D_GATE"
    assert not list(ROOT.glob("**/*v3_6e*"))
    assert not list(ROOT.glob("**/*V3_6E*"))


def test_f_completion():
    assert "READY FOR V3.6G" in _card()["f_runtime"]["verdict"]


def test_g_completion():
    assert _card()["g_frontend"]["schema"] == "v3.6g-frontend-validation-v1"


# --- card schema / identity ---


def test_card_schema():
    assert _card()["schema"] == "v3.6-final-scientific-card-v1"


def test_card_identity_deterministic():
    c = _card()
    identity = c.pop("scientific_card_identity")
    blob = json.dumps(c, sort_keys=True, separators=(",", ":")).encode()
    assert identity == hashlib.sha256(blob).hexdigest()


def test_scientific_identity_fields_exact():
    c = _card()
    assert c["production_simulation_count"] == 5000
    assert c["reference_semantics"] == "SIMULATED_NO_INTERVENTION_REFERENCE"
    assert len(c["action_space"]) == 9
    assert c["action_space"][0] == "STAY_OUT:SAMPLED"
    assert c["crn_semantics"] == "COMMON_RANDOM_NUMBERS"
    assert c["pair_policy"] == "COMPLETE_PAIRS"
    assert c["delta_orientation"]["rule"] == "POSITIVE = IMPROVEMENT"
    assert c["delta_orientation"]["delta_win_frequency"].startswith("alt - ref")
    assert c["delta_orientation"]["delta_expected_finish"].startswith("ref - alt")
    assert c["uncertainty_semantics"] == "MONTE_CARLO_SAMPLING_UNCERTAINTY_ONLY"
    assert c["utility_policy"] == "NO_SINGLE_UNIVERSAL_PRIMARY_UTILITY"
    assert c["v35_role"] == "OFFLINE_DIAGNOSTIC_ONLY"
    assert c["status_2025"] == "UNSUPPORTED"
    assert c["public_cache_policy"] == "CACHE_FIRST"
    assert c["claim_posture"] == "SIMULATOR-CONDITIONAL COUNTERFACTUAL ESTIMATES"


def test_limitations_present():
    lim = " ".join(_card()["limitations"]).lower()
    for term in ("dry-only", "compound pace", "expected-points", "weather",
                 "single-driver", "single-decision", "2025 unsupported",
                 "not yet fully materialized"):
        assert term in lim, term


# --- runtime / API presence ---


def test_v3_api_present():
    src = (ROOT / "api" / "v2_strategy_v3_routes.py").read_text()
    assert "/strategies/compare-v3" in src
    assert "/strategies/v3/availability" in src


def test_phase7_api_still_present():
    src = (ROOT / "api" / "v2_strategy_routes.py").read_text()
    assert "/strategies/compare" in src
    main = (ROOT / "api" / "main.py").read_text()
    assert "v2_strategy_router" in main
    assert "v2_strategy_v3_router" in main


def test_production_count_fixed():
    from raceintel.strategy import v3_contracts as V3
    assert V3.PRODUCTION_SIMULATION_COUNT == 5000
    assert V3.REFERENCE_KIND == "SIMULATED_NO_INTERVENTION_REFERENCE"


# --- claim audit ---


def test_no_forbidden_recommendation_claim():
    phrases = ("best strategy", "optimal strategy", "recommended strategy",
               "should pit", "correct strategy", "guaranteed", "proves")
    checked = 0
    for rel in ("frontend/features/strategy/components/Strategy2View.tsx",
                "frontend/features/strategy/components/Strategy2Results.tsx",
                "frontend/features/strategy/hooks/useStrategy2.ts",
                "api/v2_strategy_v3_service.py"):
        text = (ROOT / rel).read_text()
        # Strip the forbidden-copy definition blocks: the audit checks
        # shipped copy, not the audit list itself.
        cut = text.find("FORBIDDEN")
        body = text[:cut] if cut != -1 else text
        lowered = body.lower()
        for phrase in phrases:
            assert phrase not in lowered, (rel, phrase)
        checked += 1
    assert checked == 4


# --- freeze record ---


def test_freeze_schema():
    assert _load(FREEZE)["schema"] == "v3.6-freeze-v1"


def test_freeze_references_scientific_card():
    freeze = _load(FREEZE)
    assert freeze["scientific_card_identity"] == _card()["scientific_card_identity"]
    assert freeze["parent_commit"] == PARENT
    assert freeze["push_status"] == "NOT_PUSHED"
