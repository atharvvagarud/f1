"""
Predict the race winner across all checkpoint models:
- Lap 5
- Lap 10
- Lap 15
- Lap 20
- Lap 25

This script:
- loads the tuned model for each checkpoint
- loads the corresponding checkpoint dataset
- filters one race (year + event_name)
- predicts probabilities for all drivers
- prints checkpoint-by-checkpoint winner predictions
- prints a final overall winner using the latest available checkpoint

Example:
python scripts/predict/predict_race_winner_all_checkpoints.py --model xgboost --year 2023 --event "British Grand Prix"
python scripts/predict/predict_race_winner_all_checkpoints.py --model hgb --year 2022 --event "Hungarian Grand Prix"
"""

import argparse
from pathlib import Path
import joblib
import pandas as pd


CHECKPOINTS = [5, 10, 15, 20, 25]

FEATURE_COLS = [
    "position_x",
    "session_time_x_seconds",
    "gap_to_leader_seconds",
    "lap_time_x_seconds",
    "tyre_life_x",
    "stint_x",
    "pit_in_time_present",
    "pit_out_time_present",
    "track_status_x",
    "compound_x",
]


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
        return joblib.load(tuned_model), str(tuned_model.name)

    if base_model.exists():
        return joblib.load(base_model), str(base_model.name)

    raise FileNotFoundError(f"No model found in {model_dir}")


def get_dataset_path(root: Path, lap: int) -> Path:
    lap_tag = f"lap{lap}"
    return root / "data" / "processed" / lap_tag / "base" / "dataset_clean.csv"


def predict_for_checkpoint(root: Path, model_name: str, lap: int, year: int, event: str) -> dict | None:
    dataset_path = get_dataset_path(root, lap)
    if not dataset_path.exists():
        print(f"[WARN] Missing dataset for lap {lap}: {dataset_path}")
        return None

    df = pd.read_csv(dataset_path)

    race_df = df[(df["year"] == year) & (df["event_name"] == event)].copy()
    if race_df.empty:
        print(f"[WARN] Race not found at lap {lap}: {year} {event}")
        return None

    model, loaded_name = load_model(root, model_name, lap)

    missing = [c for c in FEATURE_COLS if c not in race_df.columns]
    if missing:
        raise ValueError(f"Missing feature columns at lap {lap}: {missing}")

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
            actual_rank = int(
                race_df.index[race_df["driver"] == actual_driver][0] + 1
            )

    return {
        "lap": lap,
        "loaded_model_file": loaded_name,
        "predicted_winner": predicted["driver"],
        "predicted_driver_number": int(predicted["driver_number"]) if pd.notna(predicted["driver_number"]) else None,
        "predicted_win_probability": float(predicted["pred_proba"]),
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
        "actual_winner": actual_driver,
        "actual_rank": actual_rank,
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", required=True, choices=["logreg", "hgb", "xgboost"])
    parser.add_argument("--year", type=int, required=True)
    parser.add_argument("--event", required=True)
    args = parser.parse_args()

    root = get_project_root()

    print("Project root:", root)
    print(f"Model family: {args.model}")
    print(f"Race: {args.year} {args.event}")

    checkpoint_results = []

    for lap in CHECKPOINTS:
        try:
            result = predict_for_checkpoint(root, args.model, lap, args.year, args.event)
            if result is not None:
                checkpoint_results.append(result)
        except FileNotFoundError as e:
            print(f"[WARN] {e}")
        except Exception as e:
            print(f"[WARN] Failed at lap {lap}: {e}")

    if not checkpoint_results:
        raise ValueError("No checkpoint predictions could be generated for this race.")

    print("\n=== Checkpoint-by-Checkpoint Predictions ===")
    summary_rows = []
    for r in checkpoint_results:
        summary_rows.append({
            "lap": r["lap"],
            "predicted_winner": r["predicted_winner"],
            "predicted_win_probability": round(r["predicted_win_probability"], 4),
            "actual_winner": r["actual_winner"],
            "actual_rank": r["actual_rank"],
            "model_file": r["loaded_model_file"],
        })

    summary_df = pd.DataFrame(summary_rows).sort_values("lap")
    print(summary_df.to_string(index=False))

    # Final overall prediction = latest available checkpoint
    final_result = max(checkpoint_results, key=lambda x: x["lap"])

    print("\n=== Final Overall Prediction ===")
    print(f"Using latest available checkpoint: Lap {final_result['lap']}")
    print(
        f"Predicted winner: {final_result['predicted_winner']} "
        f"(driver_number={final_result['predicted_driver_number']}, "
        f"predicted_win_probability={final_result['predicted_win_probability']:.4f})"
    )

    if final_result["actual_winner"] is not None:
        print(
            f"Actual winner: {final_result['actual_winner']} "
            f"(predicted_rank={final_result['actual_rank']})"
        )

    print("\n=== Top 5 at Final Checkpoint ===")
    print(final_result["top5"].to_string(index=False))


if __name__ == "__main__":
    main()