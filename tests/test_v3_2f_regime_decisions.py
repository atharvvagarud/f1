"""V3.2F regime admission decisions (source-safe, normal CI).

Pure-logic pins for the V3.2F defer-all verdict. No corpus, no pandas,
no simulation: safe for TIER 1 ordinary CI from a fresh checkout.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from raceintel.simulation.regime_support import (  # noqa: E402
    ADMISSION_DECISIONS,
    REFUSAL_TAXONOMY,
    REGIME_SUPPORT_VERSION,
    REGIMES,
    is_supported,
    refusal_taxonomy,
    regime_rng_domain,
)


def test_version_is_pinned():
    assert REGIME_SUPPORT_VERSION == "v3.2f-regime-support-v1"


def test_all_five_regimes_evaluated():
    assert tuple(REGIMES) == (
        "YELLOW", "VSC", "SAFETY_CAR", "WET", "RED")
    assert set(ADMISSION_DECISIONS) == set(REGIMES)
    assert set(REFUSAL_TAXONOMY) == set(REGIMES)


def test_no_regime_admitted_in_v32f():
    for regime in REGIMES:
        assert is_supported(regime) is False
    assert [r for r in REGIMES if is_supported(r)] == []


def test_deferral_identities_are_exact():
    assert ADMISSION_DECISIONS["YELLOW"]["decision"] == "DEFER_YELLOW"
    assert ADMISSION_DECISIONS["VSC"]["decision"] == "DEFER_VSC"
    assert ADMISSION_DECISIONS["SAFETY_CAR"]["decision"] == "DEFER_SC"
    assert ADMISSION_DECISIONS["WET"]["decision"] == "DEFER_WET"
    assert ADMISSION_DECISIONS["RED"]["decision"] == "DEFER_RED"
    for regime, entry in ADMISSION_DECISIONS.items():
        assert entry["reason"], regime
        assert "DEFERRED" in entry["reason"], regime


def test_refusal_taxonomy_never_silently_green():
    for regime in REGIMES:
        assert refusal_taxonomy(regime) in (
            "UNSUPPORTED_TRACK_STATE", "WET_CONDITIONS")


def test_unknown_regime_raises():
    import pytest

    for fn in (is_supported, refusal_taxonomy):
        with pytest.raises(ValueError):
            fn("DRY_GREEN")
    with pytest.raises(ValueError):
        regime_rng_domain("DRY_GREEN", "duration")
    with pytest.raises(ValueError):
        regime_rng_domain("VSC", "residuals")


def test_rng_domains_deterministic_and_disjoint():
    seen = set()
    for regime in REGIMES:
        for purpose in ("duration", "weather-transition"):
            first = regime_rng_domain(regime, purpose)
            assert regime_rng_domain(regime, purpose) == first
            assert first.startswith("mc2-")
            assert "residual" not in first
            seen.add(first)
    assert len(seen) == len(REGIMES) * 2


def test_headroom_identity_on_synthetic_blockers():
    # Part D rule: only single-blocker regime states are independently
    # recoverable; multi-blocker states (e.g. regime x STALE) are not.
    singles = {"TRACK_only": 292, "WET_only": 176}
    assert singles["TRACK_only"] + singles["WET_only"] == 468
    multi = {"TRACK_x_STALE": 811, "WET_x_STALE": 799,
             "TRACK_x_WET": 278}
    assert (sum(singles.values())
            < sum(singles.values()) + sum(multi.values()))


def test_parity_selection_deterministic_on_synthetic_population():
    import sys as _sys

    _sys.path.insert(0, str(ROOT / "scripts"))
    import freeze_v3_2f_parity_corpus as F

    pop = {"evaluated": [
        {"race_id": f"202{i}-r0{j}-R", "season": 2020 + i,
         "frame_index": 10 * j, "stage": s,
         "fold_through": 2019, "roster": ["a", "b"]}
        for i in range(5) for j in range(1, 7)
        for s in ("EARLY", "MID", "LATE")]}
    first = F.select_corpus(pop)
    second = F.select_corpus(pop)
    assert [(e["race_id"], e["frame_index"]) for e in first] == [
        (e["race_id"], e["frame_index"]) for e in second]
    assert len(first) == 50
    seasons = {e["season"] for e in first}
    assert seasons == {2020, 2021, 2022, 2023, 2024}
