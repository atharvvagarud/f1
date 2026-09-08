"""B. Prediction equivalence — current outputs vs the R0 golden baseline.

Recomputes ensemble + single-model predictions for all six fixture races
(direct predictor calls, local artifacts only) and compares against
tests/fixtures/legacy_predictions.json:

- winners / ranks / reasons / counts / laps: exact match;
- summary win_probability values (rounded to 4dp by the app): exact match;
- raw probabilities: NaN-aware match within PROB_ABS_TOL (see conftest);
- latest top-5 driver order: exact match.

Any failure here means prediction behaviour drifted and must be
investigated, never papered over by regenerating the fixture.
"""

import pytest

from api.services.predictor import (
    run_ensemble_prediction,
    run_single_model_prediction,
)
from conftest import fixture_races, probs_close


def _check_single(computed, recorded, model):
    assert computed["latest"]["lap"] == recorded["latest"]["lap"] == 25
    assert (
        computed["latest"]["predicted_winner"]
        == recorded["latest"]["predicted_winner"]
    )
    assert probs_close(
        computed["latest"]["predicted_win_probability"],
        recorded["latest"]["predicted_win_probability"],
    ), f"{model}: raw latest probability drifted"
    comp_rows = {r["lap"]: r for r in computed["summary"]}
    rec_rows = {r["lap"]: r for r in recorded["summary"]}
    assert set(comp_rows) == set(rec_rows) == {5, 10, 15, 20, 25}
    for lap in comp_rows:
        assert comp_rows[lap]["predicted_winner"] == rec_rows[lap]["predicted_winner"]
        assert comp_rows[lap]["win_probability"] == rec_rows[lap]["win_probability"]
        assert comp_rows[lap]["actual_winner"] == rec_rows[lap]["actual_winner"]
        assert comp_rows[lap]["actual_rank"] == rec_rows[lap]["actual_rank"]
    comp_top = [d["driver"] for d in computed["latest"]["top5"]]
    rec_top = [d["driver"] for d in recorded["latest"]["top5"]]
    assert comp_top == rec_top, f"{model}: top-5 ranking drifted"
    for c, r in zip(computed["latest"]["top5"], recorded["latest"]["top5"]):
        assert probs_close(c["win_probability"], r["win_probability"]), (
            f"{model}: top-5 probability drifted for {c['driver']}"
        )


@pytest.mark.parametrize("year,event", fixture_races())
def test_ensemble_equivalence(golden_by_race, year, event):
    recorded = golden_by_race[(year, event)]["ensemble"]
    computed = run_ensemble_prediction(year, event)
    assert computed["final_winner"] == recorded["final_winner"]
    assert computed["actual_winner"] == recorded["actual_winner"]
    assert computed["latest_lap"] == recorded["latest_lap"] == 25
    assert computed["agreement_count"] == recorded["agreement_count"]
    assert computed["decision_reason"] == recorded["decision_reason"]
    assert computed["confidence_label"] == recorded["confidence_label"]
    assert probs_close(computed["confidence_value"], recorded["confidence_value"])
    comp_rows = {(r["lap"], r["model"]): r for r in computed["summary"]}
    rec_rows = {(r["lap"], r["model"]): r for r in recorded["summary"]}
    assert set(comp_rows) == set(rec_rows)
    assert len(comp_rows) == 15
    for key in comp_rows:
        assert comp_rows[key]["predicted_winner"] == rec_rows[key]["predicted_winner"]
        assert comp_rows[key]["win_probability"] == rec_rows[key]["win_probability"]
        assert comp_rows[key]["actual_winner"] == rec_rows[key]["actual_winner"]
        assert comp_rows[key]["actual_rank"] == rec_rows[key]["actual_rank"]
    assert set(computed["latest_top5"]) == set(recorded["latest_top5"])
    for label in recorded["latest_top5"]:
        comp_top = [d["driver"] for d in computed["latest_top5"][label]]
        rec_top = [d["driver"] for d in recorded["latest_top5"][label]]
        assert comp_top == rec_top, f"{label}: top-5 ranking drifted"


@pytest.mark.parametrize("year,event", fixture_races())
@pytest.mark.parametrize("model", ["logreg", "hgb", "xgboost"])
def test_single_model_equivalence(golden_by_race, year, event, model):
    recorded = golden_by_race[(year, event)]["single"][model]
    computed = run_single_model_prediction(year, event, model)
    _check_single(computed, recorded, model)
