"""F12 tests: telemetry ADR reassessment freeze guards (offline).

F12 implements NO telemetry. These tests pin the KEEP-DEFERRED outcome:
version stays v8, active count stays 84, no telemetry family/feature/
calculator/artifact exists, and Phase-1 contracts stay untouched.
"""

from pathlib import Path

import pytest

from raceintel import contracts as C
from raceintel.pipeline import d9schema as D9
from raceintel.features import (
    FEATURE_SET_VERSION,
    NoCalculatorError,
    build_f11_registry,
)
from raceintel.config import V2Paths

ROOT = V2Paths.resolve().root

TELEMETRY_LIKE_TOKENS = (
    "telemetry", "telem", "throttle", "brake_frac", "rpm", "drs_",
    "gear_change", "speed_max", "speed_mean", "speed_p95",
    "accel", "micro_sector", "corner_speed", "full_throttle",
)


@pytest.fixture()
def registry():
    return build_f11_registry()


def test_feature_set_version_stays_v8():
    assert FEATURE_SET_VERSION == "v8"


def test_active_count_unchanged_from_f11(registry):
    assert len(registry) == 84  # 23 passthrough + 61 candidate


def test_no_telemetry_family(registry):
    families = {d.family.value for d in registry}
    assert "telemetry" not in families


def test_no_telemetry_like_feature_names(registry):
    names = registry.names()
    hits = [n for n in names
            for tok in TELEMETRY_LIKE_TOKENS
            if tok in n.lower()]
    assert hits == []


def test_no_telemetry_module():
    import raceintel.features as pkg
    pkg_dir = Path(pkg.__file__).parent
    assert not (pkg_dir / "telemetry.py").exists()


def test_no_telemetry_mentions_in_feature_sources():
    import raceintel.features as pkg
    pkg_dir = Path(pkg.__file__).parent
    hits = []
    for path in sorted(pkg_dir.glob("*.py")):
        text = path.read_text().lower()
        if "telemetry" in text:
            hits.append(path.name)
    assert hits == []


def test_no_telemetry_calculator(registry):
    from raceintel.features.contracts import FeatureRequest
    req = FeatureRequest(race_id="2021-r10-R", driver_id="hamilton",
                         lap_number=10, state_time_s=1000.0)
    with pytest.raises(NoCalculatorError):
        from raceintel.features import features_for_state
        features_for_state(req, registry, states=None,
                           names=["throttle_pressed_frac"])


def test_no_canonical_telemetry_artifact():
    processed = ROOT / "data/v2/processed"
    if processed.is_dir():
        assert not (processed / "telemetry_summary").exists()


def test_telemetry_summary_contract_stays_inactive():
    assert "EXPLICITLY INACTIVE" in C.TELEMETRY_SUMMARY.notes


def test_d9_state_carries_no_telemetry_columns():
    cols = list(D9.STATE_COLUMNS) + list(D9.STATE_EXTENSION_COLUMNS)
    assert not [c for c in cols if "telemetry" in str(c).lower()]
