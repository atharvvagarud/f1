import pandas as pd
import joblib
from pathlib import Path
import matplotlib.pyplot as plt

CHECKPOINTS = [5,10,15,20,25]
MODELS = ["logreg","hgb","xgboost"]

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

def get_root():
    return Path(__file__).resolve().parents[2]

def load_model(root, model, lap):
    path = root / "results" / "models" / f"{model}_lap{lap}_multilap" / "model_tuned.pkl"
    return joblib.load(path)

def load_dataset(root, lap):
    path = root / "data" / "processed" / f"lap{lap}" / "base" / "dataset_clean.csv"
    return pd.read_csv(path)

def main():

    year = 2023
    event = "British Grand Prix"

    root = get_root()

    probabilities = {m: [] for m in MODELS}

    for lap in CHECKPOINTS:

        df = load_dataset(root, lap)
        race_df = df[(df["year"]==year) & (df["event_name"]==event)].copy()

        actual = race_df[race_df["is_winner"]==1]["driver"].iloc[0]

        for model_name in MODELS:

            model = load_model(root, model_name, lap)

            X = race_df[FEATURE_COLS]
            probs = model.predict_proba(X)[:,1]

            race_df["pred"] = probs

            winner_prob = race_df[race_df["driver"]==actual]["pred"].iloc[0]

            probabilities[model_name].append(winner_prob)

    plt.figure(figsize=(8,5))

    for model in MODELS:
        plt.plot(CHECKPOINTS, probabilities[model], marker="o", label=model)

    plt.title("Winner Probability Evolution (2023 British GP)")
    plt.xlabel("Lap checkpoint")
    plt.ylabel("Probability of eventual winner")
    plt.legend()
    plt.grid(True)

    out = root / "results" / "analysis" / "winner_probability_evolution.png"
    out.parent.mkdir(parents=True, exist_ok=True)

    plt.savefig(out, dpi=300)

    print("Saved figure to:")
    print(out)

if __name__ == "__main__":
    main()