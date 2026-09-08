import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path


def find_project_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "results").exists() and (p / "scripts").exists():
            return p
    raise RuntimeError("Project root not found")


def extract_mean(value):
    return float(value.split("±")[0].strip())


def main():

    ROOT = find_project_root(Path(__file__).resolve())

    laps = [5, 10, 15, 20, 25]

    records = []

    for lap in laps:

        path = ROOT / "results" / "baselines" / f"lap{lap}_baseline_results_cv_summary.csv"

        print("Reading:", path)

        df = pd.read_csv(path)

        leader_row = df[df["baseline"].str.contains("Leader")].iloc[0]

        records.append({
            "lap": lap,
            "top1": extract_mean(leader_row["top1_mean±std"]),
            "top3": extract_mean(leader_row["top3_mean±std"])
        })

    plot_df = pd.DataFrame(records)

    out_dir = ROOT / "results" / "analysis"
    out_dir.mkdir(parents=True, exist_ok=True)

    plt.figure(figsize=(8,5))

    plt.plot(plot_df["lap"], plot_df["top1"], marker="o", linewidth=2, label="Top-1 Accuracy")
    plt.plot(plot_df["lap"], plot_df["top3"], marker="o", linewidth=2, label="Top-3 Accuracy")

    plt.xlabel("Race Lap Checkpoint")
    plt.ylabel("Prediction Accuracy")
    plt.title("Race Winner Prediction Accuracy vs Race Progress")

    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()

    plt.tight_layout()

    output_file = out_dir / "prediction_accuracy_vs_lap.png"

    plt.savefig(output_file, dpi=300)

    print("\nSaved plot:", output_file)

    plt.show()


if __name__ == "__main__":
    main()