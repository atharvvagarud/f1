"""
Predict race winner from a lap snapshot dataset.

Example:
python scripts/predict/predict_race_winner.py --model xgboost --lap 10 --input-csv data/processed/lap10/base/dataset_clean.csv --year 2023 --event "British Grand Prix"
"""

import argparse
from pathlib import Path
import joblib
import pandas as pd


def get_project_root():
    """
    Always resolve the project root correctly.

    File structure:
    project_root/
        data/
        results/
        scripts/
            predict/
                predict_race_winner.py
    """

    return Path(__file__).resolve().parents[2]


def load_model(model_name, lap, root):

    lap_tag = f"lap{lap}"

    model_dir = root / "results" / "models" / f"{model_name}_{lap_tag}_multilap"

    tuned_model = model_dir / "model_tuned.pkl"
    base_model = model_dir / "model.pkl"

    if tuned_model.exists():
        print(f"\nLoading tuned model:\n{tuned_model}")
        return joblib.load(tuned_model)

    if base_model.exists():
        print(f"\nLoading base model:\n{base_model}")
        return joblib.load(base_model)

    raise FileNotFoundError(f"No model found in {model_dir}")


def main():

    parser = argparse.ArgumentParser()

    parser.add_argument("--model", required=True,
                        choices=["logreg", "hgb", "xgboost"])

    parser.add_argument("--lap", type=int, required=True)

    parser.add_argument("--input-csv", required=True)

    parser.add_argument("--year", type=int, required=True)

    parser.add_argument("--event", required=True)

    args = parser.parse_args()

    ROOT = get_project_root()

    print("Project root:", ROOT)

    # Load dataset
    df = pd.read_csv(args.input_csv)

    race_df = df[
        (df["year"] == args.year) &
        (df["event_name"] == args.event)
    ].copy()

    if race_df.empty:
        raise ValueError("Race not found in dataset")

    # Load trained model
    model = load_model(args.model, args.lap, ROOT)

    feature_cols = [
        "position_x",
        "session_time_x_seconds",
        "gap_to_leader_seconds",
        "lap_time_x_seconds",
        "tyre_life_x",
        "stint_x",
        "pit_in_time_present",
        "pit_out_time_present",
        "track_status_x",
        "compound_x"
    ]

    X = race_df[feature_cols]

    probs = model.predict_proba(X)[:, 1]

    race_df["pred_proba"] = probs

    race_df = race_df.sort_values("pred_proba", ascending=False)

    predicted_winner = race_df.iloc[0]

    print("\n=== Race Winner Prediction ===")

    print(f"Model: {args.model}")
    print(f"Lap checkpoint: {args.lap}")
    print(f"Race: {args.year} {args.event}")
    print(f"Drivers in snapshot: {len(race_df)}")

    print("\nPredicted winner:")

    print(
        f"{predicted_winner['driver']} "
        f"(driver_number={predicted_winner['driver_number']}, "
        f"predicted_win_probability={predicted_winner['pred_proba']:.4f})"
    )

    print("\nTop 5 predictions:")

    cols = [
        "driver",
        "driver_number",
        "pred_proba",
        "position_x",
        "gap_to_leader_seconds",
        "compound_x",
        "tyre_life_x",
        "stint_x"
    ]

    print(race_df[cols].head(5).to_string(index=False))

    # Show actual winner if dataset contains it
    if "is_winner" in race_df.columns:

        actual = race_df[race_df["is_winner"] == 1]

        if not actual.empty:

            actual_driver = actual.iloc[0]["driver"]

            rank = race_df.reset_index().query(
                "driver == @actual_driver"
            ).index[0] + 1

            print("\nActual winner (available in this dataset):")

            print(
                f"{actual_driver} "
                f"(predicted_win_probability="
                f"{actual.iloc[0]['pred_proba']:.4f}, "
                f"predicted_rank={rank})"
            )


if __name__ == "__main__":
    main()