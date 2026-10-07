"""V3.2I status-source outcomes (corpus-dependent, TIER 3).

Requires the FastF1 sqlite cache, D9/results parquets, and H/I result
files at canonical paths. Listed in scripts/ci_corpus_dependent.txt;
NOT run in TIER 1 ordinary CI.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

I = ROOT / "results" / "v3" / "v3_2i"


def _load(name: str) -> dict:
    return json.load(open(I / name, encoding="utf-8"))


def test_decision_follows_evidence():
    d = _load("decision.json")
    assert d["decision"] == "LOCAL_RAW_STATUS_SOURCE_PARTIALLY_VIABLE"
    assert "V3.2J" in d["next_stage"]


def test_scorecard_schema_and_verdicts():
    s = _load("source_scorecard.json")
    by_src = {r["source"]: r["verdict"] for r in s["sources"]}
    assert any(v == "PARTIALLY_VIABLE" for v in by_src.values())
    assert any("VALIDATION_ONLY" in str(v) for v in by_src.values())
    assert s["feed_vs_official_accounting"]["official_dnfs"] == 127


def test_flips_measured_not_assumed():
    sem = _load("status_semantics.json")
    flips = sem["true_to_false_flips"]
    assert len(flips) == 2
    assert {f["driver"] for f in flips} == {"ricciardo", "alonso"}


def test_winner_firewall():
    w = _load("winner_firewall.json")
    assert w["winners_flagged_any_time"] == []
    assert w["vettel_2018_r02"]["verdict"].startswith("PASS")


def test_projection_accounting():
    p = _load("projected_coverage.json")
    assert p["current"] == {"eligible": 2305, "total": 9644}
    assert p["projected"] == {"eligible": 2685, "total": 9644}
    assert p["gain_from_stale_only_states"] == 380
    assert p["stale_resolved_by_retired_le_T"] == 469
    assert p["projected_fraction"] == round(2685 / 9644, 4)


def test_no_2025_in_evidence():
    for name in ("status_semantics.json", "projected_coverage.json",
                 "source_availability.json", "causal_timeline.json"):
        assert "2025" not in (I / name).read_text(encoding="utf-8")


def test_runtime_coverage_unchanged():
    assert _load("projected_coverage.json")["current"]["eligible"] == 2305
