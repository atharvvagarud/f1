"""V3.2H regime outcomes (corpus-dependent, TIER 3).

Requires the frozen V3.2F raw audit, D9 lap parquets, and H result
files at canonical paths. Listed in scripts/ci_corpus_dependent.txt;
NOT run in TIER 1 ordinary CI.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

H = ROOT / "results" / "v3" / "v3_2h"


def _load(name: str) -> dict:
    return json.load(open(H / name, encoding="utf-8"))


def test_prereg_file_hash():
    import hashlib
    sys.path.insert(0, str(ROOT / "scripts"))
    from freeze_v3_2h_prereg import build, content_hash
    saved = _load("preregistration.json")
    assert saved["prereg_hash"] == content_hash(build())


def test_all_regimes_rejected_by_gates():
    assert _load("vsc_decision.json")["decision"] == "REJECT_VSC"
    assert _load("wet_decision.json")["decision"] == "REJECT_WET"
    assert _load("sc_decision.json")["decision"] == "REJECT_SC"
    assert _load("yellow_decision.json")["decision"] == "REJECT_YELLOW"
    assert _load("red_decision.json")["decision"] == "REJECT_RED"
    assert _load("vsc_ending_decision.json")["decision"] == \
        "REJECT_VSC_ENDING"


def test_vsc_gates_match_validation():
    gates = _load("vsc_validation.json")["gates"]
    assert gates["H1"]["during_pace"] == "FAIL"
    assert gates["H2"]["during_pace"] == "FAIL"
    assert gates["H1"]["duration"] == "FAIL"


def test_opportunity_freezes_headroom():
    opp = _load("opportunity.json")
    assert opp["track_only_total"] == 292
    assert opp["wet_only_total"] == 176
    assert sum(v["n"] for v in opp["track_only_by_token"].values()) == 292


def test_coverage_unchanged_and_attributed():
    after = _load("coverage_after.json")
    assert (after["eligible"], after["total"]) == (2305, 9644)
    attr = _load("coverage_attribution.json")
    assert attr["newly_supported"] == 0
    assert attr["unexplained_growth"] == 0
    assert all(v == 0 for v in attr["by_regime"].values())


def test_blockers_match_frozen_taxonomy():
    b = _load("blockers_after.json")
    assert b["primary"]["STALE_ROSTER_OBSERVATION"] == 4667
    assert b["primary"]["UNSUPPORTED_TRACK_STATE"] == 1165
    assert b["primary"]["WET_CONDITIONS"] == 801


def test_parity_and_firewall_recorded():
    assert _load("dry_green_parity.json")["status"] == \
        "PARITY_OK_BIT_EXACT"
    assert _load("oracle_firewall.json")["runtime_reads_added"] == []
    assert _load("regime_identities.json")["rng_status"].startswith(
        "RESERVED_UNCONSUMED")


def test_no_2025_in_evidence():
    for name in ("vsc_episodes.json", "vsc_parameters.json",
                 "wet_episodes.json", "wet_parameters.json",
                 "sc_episodes.json", "sc_parameters.json"):
        text = (H / name).read_text(encoding="utf-8")
        assert "2025" not in text
