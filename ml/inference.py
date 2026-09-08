"""Reusable runtime inference (R3 foundation refactor).

Framework-free prediction logic moved verbatim from
``api/services/predictor.py``: dataset access, model discovery/loading,
feature preparation, single-model inference and the existing ensemble rule
(majority vote at the latest checkpoint, XGBoost tie-break, XGBoost
confidence semantics). No FastAPI concerns live here; behaviour — including
the known Monaco-2022 NaN passthrough — is intentionally unchanged.
"""

from collections import Counter

import joblib
import pandas as pd

from ml.config import CHECKPOINTS, MODEL_LABELS, MODELS, get_dataset_path, get_model_dir
from ml.features import FEATURE_COLS


def load_dataset(lap: int) -> pd.DataFrame:
    path = get_dataset_path(lap)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    return pd.read_csv(path)


def load_model(model_name: str, lap: int):
    model_dir = get_model_dir(model_name, lap)
    tuned = model_dir / "model_tuned.pkl"
    base = model_dir / "model.pkl"

    if tuned.exists():
        return joblib.load(tuned), tuned.name
    if base.exists():
        return joblib.load(base), base.name

    raise FileNotFoundError(f"No model found in {model_dir}")


def get_available_races():
    df = load_dataset(10)
    races = (
        df[["year", "event_name"]]
        .drop_duplicates()
        .sort_values(["year", "event_name"])
        .reset_index(drop=True)
    )
    return races.to_dict(orient="records")


def predict_one_model_one_checkpoint(model_name: str, lap: int, year: int, event: str):
    df = load_dataset(lap)
    race_df = df[(df["year"] == year) & (df["event_name"] == event)].copy()

    if race_df.empty:
        return None

    model, model_file = load_model(model_name, lap)

    X = race_df[FEATURE_COLS].copy()
    probs = model.predict_proba(X)[:, 1]

    race_df["pred_proba"] = probs
    race_df = race_df.sort_values("pred_proba", ascending=False).reset_index(drop=True)

    predicted = race_df.iloc[0]

    actual_driver = None
    actual_rank = None
    if "is_winner" in race_df.columns:
        actual_rows = race_df[race_df["is_winner"] == 1]
        if not actual_rows.empty:
            actual_driver = actual_rows.iloc[0]["driver"]
            actual_rank = int(race_df.index[race_df["driver"] == actual_driver][0] + 1)

    top5 = race_df[
        [
            c for c in [
                "driver",
                "driver_number",
                "pred_proba",
                "position_x",
                "gap_to_leader_seconds",
                "compound_x",
                "tyre_life_x",
                "stint_x",
            ] if c in race_df.columns
        ]
    ].head(5).copy()

    top5 = top5.rename(columns={"pred_proba": "win_probability"})

    return {
        "model": model_name,
        "lap": lap,
        "model_file": model_file,
        "predicted_winner": predicted["driver"],
        "predicted_driver_number": int(predicted["driver_number"]) if pd.notna(predicted["driver_number"]) else None,
        "predicted_win_probability": float(predicted["pred_proba"]),
        "actual_winner": actual_driver,
        "actual_rank": actual_rank,
        "top5": top5.to_dict(orient="records"),
    }


def choose_final_prediction(latest_df: pd.DataFrame):
    votes = latest_df["predicted_winner"].tolist()
    counts = Counter(votes)
    winner, count = counts.most_common(1)[0]

    if count >= 2:
        return winner, "Majority vote at latest checkpoint", count

    xgb_row = latest_df[latest_df["model"] == "xgboost"]
    if not xgb_row.empty:
        return xgb_row.iloc[0]["predicted_winner"], "Tie-breaker: XGBoost at latest checkpoint", 1

    return latest_df.iloc[0]["predicted_winner"], "Fallback: first available latest-checkpoint prediction", 1


def run_ensemble_prediction(year: int, event: str):
    results = []

    for lap in CHECKPOINTS:
        for model_name in MODELS:
            r = predict_one_model_one_checkpoint(model_name, lap, year, event)
            if r is not None:
                results.append(r)

    if not results:
        raise ValueError("No predictions could be generated for this race.")

    summary_df = pd.DataFrame(
        [
            {
                "lap": r["lap"],
                "model": MODEL_LABELS[r["model"]],
                "predicted_winner": r["predicted_winner"],
                "win_probability": round(r["predicted_win_probability"], 4),
                "actual_winner": r["actual_winner"],
                "actual_rank": r["actual_rank"],
            }
            for r in results
        ]
    ).sort_values(["lap", "model"]).reset_index(drop=True)

    latest_lap = summary_df["lap"].max()

    latest_raw_df = pd.DataFrame(
        [
            {
                "lap": r["lap"],
                "model": r["model"],
                "predicted_winner": r["predicted_winner"],
                "predicted_win_probability": r["predicted_win_probability"],
            }
            for r in results if r["lap"] == latest_lap
        ]
    )

    final_winner, decision_reason, agreement_count = choose_final_prediction(latest_raw_df)

    xgb_latest = latest_raw_df[latest_raw_df["model"] == "xgboost"]
    if not xgb_latest.empty:
        confidence_value = float(xgb_latest.iloc[0]["predicted_win_probability"])
        confidence_label = "Confidence (XGBoost)"
    else:
        confidence_value = float(latest_raw_df["predicted_win_probability"].max())
        confidence_label = "Confidence"

    actual_winner = None
    actuals = summary_df["actual_winner"].dropna().unique().tolist()
    if actuals:
        actual_winner = actuals[0]

    latest_top5 = {
        MODEL_LABELS[r["model"]]: r["top5"]
        for r in results if r["lap"] == latest_lap
    }

    return {
        "summary": summary_df.to_dict(orient="records"),
        "latest_lap": int(latest_lap),
        "final_winner": final_winner,
        "decision_reason": decision_reason,
        "actual_winner": actual_winner,
        "agreement_count": int(agreement_count),
        "confidence_value": confidence_value,
        "confidence_label": confidence_label,
        "latest_top5": latest_top5,
    }


def run_single_model_prediction(year: int, event: str, selected_model: str):
    results = []

    for lap in CHECKPOINTS:
        r = predict_one_model_one_checkpoint(selected_model, lap, year, event)
        if r is not None:
            results.append(r)

    if not results:
        raise ValueError("No predictions could be generated for this race.")

    summary_df = pd.DataFrame(
        [
            {
                "lap": r["lap"],
                "predicted_winner": r["predicted_winner"],
                "win_probability": round(r["predicted_win_probability"], 4),
                "actual_winner": r["actual_winner"],
                "actual_rank": r["actual_rank"],
            }
            for r in results
        ]
    ).sort_values("lap").reset_index(drop=True)

    latest = max(results, key=lambda x: x["lap"])

    return {
        "summary": summary_df.to_dict(orient="records"),
        "latest": latest,
    }
