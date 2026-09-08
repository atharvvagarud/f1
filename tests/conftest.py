"""Shared fixtures for the R2 regression safety net.

All tests are characterisation tests: they pin the CURRENT (R0/R1 baseline)
behaviour so later restructuring (R3+) cannot silently change it.

Rules honoured here:
- local datasets/models only, no network, no FastF1 downloads;
- never writes to data/, results/ or model artifacts;
- the golden fixture file itself is never modified (integrity is
  asserted by sha256 in test_known_defects.py).
"""

import hashlib
import json
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ml.config import CHECKPOINTS, MODELS  # noqa: E402
from ml.features import FEATURE_COLS  # noqa: E402

FIXTURE_PATH = ROOT / "tests" / "fixtures" / "legacy_predictions.json"
# sha256 of the fixture file as captured in R0. Any byte change fails loudly
# instead of silently shifting the baseline.
FIXTURE_SHA256 = "8e23031af4a680a4d493e9a6052d342defccfbf4c6db1d89c3ed31c1f6530228"

# Absolute tolerance for raw win probabilities. Rationale: recomputation uses
# the identical saved pipelines and library versions, so outputs are
# deterministic; 1e-9 absorbs only floating-point/BLAS noise. Any real drift
# (feature change, imputation change, model swap, vote-rule change) moves
# probabilities by orders of magnitude more, or flips winners (exact checks).
PROB_ABS_TOL = 1e-9

# Races that must succeed over HTTP (no known serialization defect).
HTTP_CLEAN_RACES = [
    (2023, "Bahrain Grand Prix"),
    (2021, "Abu Dhabi Grand Prix"),
    (2019, "German Grand Prix"),
    (2023, "Las Vegas Grand Prix"),
    (2020, "70th Anniversary Grand Prix"),
]


def load_fixture():
    """Parse the golden fixture, tolerating its faithful bare-NaN tokens.

    The R0 capture used Python json defaults, so genuine NaN outputs were
    written as bare ``NaN`` literals (non-strict JSON). The harness accepts
    them via ``parse_constant`` mapping to float('nan'); the fixture file
    itself is never rewritten (see the sha256 integrity test).
    """
    text = FIXTURE_PATH.read_text()
    data = json.loads(
        text,
        parse_constant=lambda tok: float("nan") if tok.strip() == "NaN" else tok,
    )
    assert "fixtures" in data and len(data["fixtures"]) == 6
    return data


def fixture_races():
    return [(f["year"], f["event"]) for f in load_fixture()["fixtures"]]


def probs_close(a, b):
    """NaN-aware float comparison for recorded probabilities."""
    if isinstance(a, float) and isinstance(b, float):
        if math.isnan(a) and math.isnan(b):
            return True
    return abs(a - b) <= PROB_ABS_TOL


@pytest.fixture(scope="session")
def golden():
    return load_fixture()


@pytest.fixture(scope="session")
def golden_by_race(golden):
    return {(f["year"], f["event"]): f for f in golden["fixtures"]}


@pytest.fixture(scope="session")
def api_client():
    from fastapi.testclient import TestClient

    from api.main import app

    return TestClient(app, raise_server_exceptions=False)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()
