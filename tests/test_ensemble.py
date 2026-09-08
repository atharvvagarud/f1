"""E. Ensemble behaviour — characterise the vote rule, do not redesign it.

The app decides the final winner by majority vote across the three models at
the latest checkpoint, breaking ties via XGBoost (see
api/services/predictor.py::choose_final_prediction). These tests pin each
branch, including the exact decision-reason strings surfaced in the UI.
"""

import pandas as pd

from api.services.predictor import choose_final_prediction, run_ensemble_prediction


def _frame(rows):
    return pd.DataFrame(
        [
            {
                "lap": 25,
                "model": m,
                "predicted_winner": w,
                "predicted_win_probability": p,
            }
            for m, w, p in rows
        ]
    )


def test_unanimous_vote():
    winner, reason, count = choose_final_prediction(
        _frame([("logreg", "VER", 0.8), ("hgb", "VER", 0.7), ("xgboost", "VER", 0.9)])
    )
    assert (winner, reason, count) == ("VER", "Majority vote at latest checkpoint", 3)


def test_majority_two_of_three():
    winner, reason, count = choose_final_prediction(
        _frame([("logreg", "VER", 0.8), ("hgb", "HAM", 0.7), ("xgboost", "VER", 0.6)])
    )
    assert (winner, reason, count) == ("VER", "Majority vote at latest checkpoint", 2)


def test_full_disagreement_falls_back_to_xgboost():
    winner, reason, count = choose_final_prediction(
        _frame([("logreg", "VER", 0.8), ("hgb", "HAM", 0.7), ("xgboost", "PER", 0.6)])
    )
    assert (winner, reason, count) == (
        "PER",
        "Tie-breaker: XGBoost at latest checkpoint",
        1,
    )


def test_fallback_without_xgboost_uses_first_row():
    winner, reason, count = choose_final_prediction(
        _frame([("logreg", "VER", 0.8), ("hgb", "HAM", 0.7)])
    )
    assert (winner, reason, count) == (
        "VER",
        "Fallback: first available latest-checkpoint prediction",
        1,
    )


def test_ensemble_confidence_uses_xgboost(golden_by_race):
    # Baseline semantics: confidence_value is the XGBoost driver's latest
    # probability, labelled "Confidence (XGBoost)".
    rec = golden_by_race[(2023, "Bahrain Grand Prix")]["ensemble"]
    assert rec["confidence_label"] == "Confidence (XGBoost)"
    xgb_prob = next(
        r["win_probability"]
        for r in rec["summary"]
        if r["lap"] == 25 and r["model"] == "XGBoost"
    )
    assert abs(rec["confidence_value"] - xgb_prob) < 0.00011  # 4dp rounding
