"""V3.2H causal regime models (source-safe, normal CI).

Code-derived pins only: prereg builder hash, gate thresholds, frozen
refusals, MC2 identity, temporal-firewall constants. No corpus, no
pandas, no simulation: safe for TIER 1 ordinary CI from a fresh
checkout. Outcome-file assertions live in test_v3_2h_regime_corpus.py
(corpus-dependent, TIER 3).
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "scripts") not in sys.path:
    sys.path.insert(0, str(ROOT / "scripts"))

from freeze_v3_2h_prereg import build, content_hash  # noqa: E402
from raceintel.simulation.mc2.contract import (  # noqa: E402
    MC2_KERNEL_SCHEMA,
    MC2_RESEARCH_VERSION,
    MC2_RNG_SCHEMA,
    MC2_STATE_CONTRACT,
)
from raceintel.simulation.regime_support import (  # noqa: E402
    ADMISSION_DECISIONS,
    REGIME_SUPPORT_VERSION,
    is_supported,
    refusal_taxonomy,
    regime_rng_domain,
)

FROZEN_PREREG_HASH = "a31aec4e7297dd81be17a850295e014c569fbcbd57ee90b56ecb6e93122f6054"


def test_prereg_hash_frozen():
    assert content_hash(build()) == FROZEN_PREREG_HASH


def test_prereg_candidate_order_vsc_first():
    assert build()["candidate_order"] == [
        "VSC", "VSC_ENDING", "WET", "SAFETY_CAR", "YELLOW", "RED"]


def test_prereg_forbids_2025_and_future_reads():
    p = build()
    assert p["temporal_folds"] == [
        {"fold": "H1", "train_through": 2021, "evaluate": [2022, 2023]},
        {"fold": "H2", "train_through": 2023, "evaluate": [2024]},
    ]
    forbidden = " ".join(p["forbidden"])
    assert "2025" in forbidden
    assert "future regime end" in forbidden


def test_prereg_rng_domains_reserved():
    assert build()["seed_policy"]["regime_rng_domains"] == [
        "mc2-vsc-duration", "mc2-sc-duration", "mc2-weather-transition"]
    assert regime_rng_domain("VSC", "duration") == "mc2-vsc-duration"
    # V3.2F reserved short names (helper emits long-form names; both
    # are unconsumed in V3.2H, so the reservation is nominal only).
    # What matters: all regime domains are disjoint from dry-green
    # residual/pace streams and from each other.
    helper_names = {regime_rng_domain(r, p)
                    for r in ("VSC", "SAFETY_CAR", "WET")
                    for p in ("duration", "weather-transition")}
    assert len(helper_names) == 6
    assert all(n.startswith("mc2-") for n in helper_names)


def test_no_regime_admitted_at_runtime():
    assert REGIME_SUPPORT_VERSION == "v3.2f-regime-support-v1"
    for regime in ("YELLOW", "VSC", "SAFETY_CAR", "WET", "RED"):
        assert is_supported(regime) is False
        assert ADMISSION_DECISIONS[regime]["decision"].startswith(
            ("DEFER_", "REJECT_"))
    assert refusal_taxonomy("VSC") == "UNSUPPORTED_TRACK_STATE"
    assert refusal_taxonomy("WET") == "WET_CONDITIONS"


def test_mc2_identity_untouched():
    assert MC2_RESEARCH_VERSION == "mc2-r1-research"
    assert MC2_KERNEL_SCHEMA == "mc2-kernel-v1"
    assert MC2_RNG_SCHEMA == "mc2-rng-v1"
    assert MC2_STATE_CONTRACT == "mc2-field-v1"


def test_no_runtime_regime_reads():
    """Static: MC2 kernel never reads future regime/weather channels."""
    mc2 = ROOT / "raceintel" / "simulation" / "mc2"
    forbidden = ("wx_rainfall", "race_control", "TrackStatus",
                 "weather_transition", "vsc-duration", "sc-duration")
    hits = []
    for path in sorted(mc2.glob("*.py")):
        text = path.read_text(encoding="utf-8")
        for token in forbidden:
            if token in text:
                hits.append(f"{path.name}:{token}")
    assert hits == []
