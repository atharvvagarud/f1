"""F+G. Known legacy defect + fixture integrity.

Monaco 2022: NaN ``tyre_life_x`` values in the source lap-25 rows flow into
the API ``top5`` payload, and Starlette's JSONResponse raises
``ValueError: Out of range float values are not JSON compliant`` → HTTP 500.

This is a DOCUMENTED legacy defect (audit §5.1), not a contract: the tests
below pin its root cause with passing assertions, while the HTTP-level
expectation is marked xfail so the suite turns green-through-XPASS (not red)
the day the defect is deliberately fixed. The 500 must never be asserted as
desired behaviour.

Fixture integrity: the golden file is hashed against its R0 capture value;
any byte change — including well-meaning "cleanup" of the bare-NaN tokens
(see conftest.load_fixture) — fails loudly.
"""

import math

import pytest

from api.services.predictor import load_dataset
from conftest import FIXTURE_PATH, FIXTURE_SHA256, _sha256, load_fixture


def test_fixture_file_byte_identical_to_r0():
    assert _sha256(FIXTURE_PATH) == FIXTURE_SHA256


def test_fixture_harness_tolerates_faithful_nans(golden_by_race):
    # The R0 capture faithfully recorded real NaN outputs as bare NaN
    # literals. The harness must parse them (not the fixture to change).
    monaco = golden_by_race[(2022, "Monaco Grand Prix")]["ensemble"]
    nans = [
        d["driver"]
        for label in monaco["latest_top5"]
        for d in monaco["latest_top5"][label]
        if isinstance(d.get("tyre_life_x"), float)
        and math.isnan(d["tyre_life_x"])
    ]
    assert len(nans) >= 1, "expected the faithfully-recorded NaN rows"


def test_monaco_nan_originates_in_source_data():
    df = load_dataset(25)
    race = df[(df["year"] == 2022) & (df["event_name"] == "Monaco Grand Prix")]
    assert not race.empty
    assert race["tyre_life_x"].isna().any(), (
        "root cause: NaN tyre_life_x in the lap-25 source rows"
    )


@pytest.mark.xfail(
    reason="Known legacy defect (audit §5.1): NaN tyre_life_x breaks JSON "
    "serialization for Monaco 2022. Deliberate fix pending; remove this "
    "marker when fixed.",
    strict=False,
)
@pytest.mark.parametrize("model", ["logreg", "hgb", "xgboost"])
def test_monaco_single_model_http_ok(api_client, model):
    resp = api_client.post(
        "/predict/single-model",
        json={"year": 2022, "event": "Monaco Grand Prix", "model": model},
    )
    assert resp.status_code == 200


@pytest.mark.xfail(
    reason="Known legacy defect (audit §5.1): NaN tyre_life_x breaks JSON "
    "serialization for Monaco 2022. Deliberate fix pending; remove this "
    "marker when fixed.",
    strict=False,
)
def test_monaco_ensemble_http_ok(api_client):
    resp = api_client.post(
        "/predict/ensemble", json={"year": 2022, "event": "Monaco Grand Prix"}
    )
    assert resp.status_code == 200
