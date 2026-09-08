"""
Predict race winner using all 3 model families across all checkpoints:
- Logistic Regression
- HistGradientBoosting
- XGBoost

Checkpoints:
- Lap 5
- Lap 10
- Lap 15
- Lap 20
- Lap 25

Final overall prediction rule:
1. use the latest available checkpoint
2. compare predictions from logreg / hgb / xgboost at that checkpoint
3. if 2 or more models agree -> majority vote winner
4. if all 3 disagree -> use XGBoost prediction as tie-breaker

Example:
python scripts/predict/predict_race_winner_ensemble.py --year 2023 --event "British Grand Prix"
"""

import argparse
import sys
from pathlib import Path
from collections import Counter
import joblib
import pandas as pd

# R3: constants single-sourced from the ml package (values unchanged).
# Bootstrap the project root so `python scripts/...` invocations resolve `ml`.
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from ml.config import CHECKPOINTS, MODELS
from ml.features import FEATURE_COLS


def get_project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def get_model_dir(root: Path, model_name: str, lap: int) -> Path:
    lap_tag = f"lap{lap}"
    return root / "results" / "models" / f"{model_name}_{lap_tag}_multilap"


def load_model(root: Path, model_name: str, lap: int):
    model_dir = get_model_dir(root, model_name, lap)

    tuned_model = model_dir / "model_tuned.pkl"
    base_model = model_dir / "model.pkl"

    if tuned_model.exists():
        return joblib.load(tuned_model), tuned_model.name

    if base_model.exists():
        return joblib.load(base_model), base_model.name

    raise FileNotFoundError(f"No model found in {model_dir}")


def get_dataset_path(root: Path, lap: int) -> Path:
    lap_tag = f"lap{lap}"
    return root / "data" / "processed" / lap_tag / "base" / "dataset_clean.csv"


def predict_one_model_one_checkpoint(root: Path, model_name: str, lap: int, year: int, event: str):
    dataset_path = get_dataset_path(root, lap)
    if not dataset_path.exists():
        return None

    df = pd.read_csv(dataset_path)
    race_df = df[(df["year"] == year) & (df["event_name"] == event)].copy()

    if race_df.empty:
        return None

    model, loaded_name = load_model(root, model_name, lap)

    missing = [c for c in FEATURE_COLS if c not in race_df.columns]
    if missing:
        raise ValueError(f"Missing feature columns for lap {lap}: {missing}")

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

    return {
        "model": model_name,
        "lap": lap,
        "model_file": loaded_name,
        "predicted_winner": predicted["driver"],
        "predicted_driver_number": int(predicted["driver_number"]) if pd.notna(predicted["driver_number"]) else None,
        "predicted_win_probability": float(predicted["pred_proba"]),
        "actual_winner": actual_driver,
        "actual_rank": actual_rank,
        "top5": race_df[
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
        ].head(5).copy(),
    }


def choose_final_prediction(latest_df: pd.DataFrame) -> tuple[str, str]:
    """
    latest_df contains one row per model for the latest checkpoint.
    Rule:
    - if 2 or more models agree -> majority vote
    - if all 3 disagree -> XGBoost tie-breaker
    """
    votes = latest_df["predicted_winner"].tolist()
    counts = Counter(votes)
    winner, count = counts.most_common(1)[0]

    if count >= 2:
        return winner, "Majority vote at latest checkpoint"

    xgb_row = latest_df[latest_df["model"] == "xgboost"]
    if not xgb_row.empty:
        return xgb_row.iloc[0]["predicted_winner"], "Tie-breaker: XGBoost at latest checkpoint"

    return latest_df.iloc[0]["predicted_winner"], "Fallback: first available latest-checkpoint prediction"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--event", required=True)
    args = parser.parse_args()

    root = get_project_root()

    print("Project root:", root)
    print(f"Race: {args.year} {args.event}")

    results = []

    for lap in CHECKPOINTS:
        for model_name in MODELS:
            try:
                result = predict_one_model_one_checkpoint(root, model_name, lap, args.year, args.event)
                if result is not None:
                    results.append(result)
            except FileNotFoundError as e:
                print(f"[WARN] {e}")
            except Exception as e:
                print(f"[WARN] Failed for model={model_name}, lap={lap}: {e}")

    if not results:
        raise ValueError("No predictions could be generated for this race.")

    results_df = pd.DataFrame(
        [
            {
                "lap": r["lap"],
                "model": r["model"],
                "predicted_winner": r["predicted_winner"],
                "predicted_win_probability": round(r["predicted_win_probability"], 4),
                "actual_winner": r["actual_winner"],
                "actual_rank": r["actual_rank"],
                "model_file": r["model_file"],
            }
            for r in results
        ]
    ).sort_values(["lap", "model"]).reset_index(drop=True)

    print("\n=== Checkpoint Predictions Across All Models ===")
    print(results_df.to_string(index=False))

    latest_lap = results_df["lap"].max()
    latest_df = results_df[results_df["lap"] == latest_lap].copy()

    final_winner, reason = choose_final_prediction(latest_df)

    print("\n=== Final Overall Prediction ===")
    print(f"Latest available checkpoint: Lap {latest_lap}")
    print(f"Final predicted winner: {final_winner}")
    print(f"Decision rule: {reason}")

    actual_rows = latest_df["actual_winner"].dropna().unique().tolist()
    if actual_rows:
        print(f"Actual winner: {actual_rows[0]}")

    print("\n=== Latest Checkpoint Top Predictions ===")
    for r in results:
        if r["lap"] == latest_lap:
            print(f"\nModel: {r['model']} | Lap {r['lap']} | File: {r['model_file']}")
            print(r["top5"].to_string(index=False))


if __name__ == "__main__":
    main()