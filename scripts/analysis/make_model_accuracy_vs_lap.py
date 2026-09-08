"""
Create a final multilap comparison table and plot for:
- Leader baseline
- Logistic Regression (multilap)
- HistGradientBoosting (multilap)
- XGBoost (multilap)

Reads summary CSVs from:
- results/baselines/lap{lap}_baseline_results_cv_summary.csv
- results/models/logreg_lap{lap}_multilap/summary_cv.csv
- results/models/hgb_lap{lap}_multilap/summary_cv.csv
- results/models/xgboost_lap{lap}_multilap/summary_cv.csv

Writes:
- results/analysis/model_accuracy_vs_lap.csv
- results/analysis/model_accuracy_vs_lap_top1.png
- results/analysis/model_accuracy_vs_lap_top3.png

How to run:
    python scripts/analysis/make_model_accuracy_vs_lap.py
"""

from pathlib import Path
import pandas as pd
import matplotlib.pyplot as plt


LAPS = [5, 10, 15, 20, 25]


def find_project_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "results").exists() and (p / "scripts").exists():
            return p
    raise RuntimeError("Project root not found")


def extract_mean(value: str) -> float:
    """
    Convert strings like:
        '0.5786 ± 0.1325'
    into:
        0.5786
    """
    return float(str(value).split("±")[0].strip())


def read_baseline_summary(path: Path, lap: int) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing baseline summary: {path}")

    df = pd.read_csv(path)
    row = df[df["baseline"].str.contains("Leader", case=False, na=False)].iloc[0]

    return {
        "lap": lap,
        "model": "Leader baseline",
        "top1": extract_mean(row["top1_mean±std"]),
        "top3": extract_mean(row["top3_mean±std"]),
    }


def read_model_summary(path: Path, lap: int, model_name: str) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"Missing model summary: {path}")

    df = pd.read_csv(path)
    row = df.iloc[0]

    return {
        "lap": lap,
        "model": model_name,
        "top1": extract_mean(row["top1_mean±std"]),
        "top3": extract_mean(row["top3_mean±std"]),
    }


def plot_metric(df: pd.DataFrame, metric: str, out_path: Path, title: str) -> None:
    plt.figure(figsize=(9, 5))

    for model_name in df["model"].unique():
        sub = df[df["model"] == model_name].sort_values("lap")
        plt.plot(sub["lap"], sub[metric], marker="o", linewidth=2, label=model_name)

    plt.xlabel("Race Lap Checkpoint")
    plt.ylabel("Accuracy")
    plt.title(title)
    plt.xticks(LAPS)
    plt.grid(True, linestyle="--", alpha=0.5)
    plt.legend()
    plt.tight_layout()
    plt.savefig(out_path, dpi=300, bbox_inches="tight")
    plt.close()


def main() -> None:
    root = find_project_root(Path(__file__).resolve())
    results_dir = root / "results"
    analysis_dir = results_dir / "analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    rows = []

    for lap in LAPS:
        # Baseline
        rows.append(
            read_baseline_summary(
                results_dir / "baselines" / f"lap{lap}_baseline_results_cv_summary.csv",
                lap,
            )
        )

        # Logistic Regression
        rows.append(
            read_model_summary(
                results_dir / "models" / f"logreg_lap{lap}_multilap" / "summary_cv.csv",
                lap,
                "Logistic Regression",
            )
        )

        # HistGradientBoosting
        rows.append(
            read_model_summary(
                results_dir / "models" / f"hgb_lap{lap}_multilap" / "summary_cv.csv",
                lap,
                "HistGradientBoosting",
            )
        )

        # XGBoost
        rows.append(
            read_model_summary(
                results_dir / "models" / f"xgboost_lap{lap}_multilap" / "summary_cv.csv",
                lap,
                "XGBoost",
            )
        )

    out_df = pd.DataFrame(rows).sort_values(["model", "lap"]).reset_index(drop=True)

    out_csv = analysis_dir / "model_accuracy_vs_lap.csv"
    out_df.to_csv(out_csv, index=False)

    # Wide tables for quick inspection
    top1_pivot = out_df.pivot(index="model", columns="lap", values="top1")
    top3_pivot = out_df.pivot(index="model", columns="lap", values="top3")

    print("\n=== Top-1 Accuracy by Lap ===")
    print(top1_pivot.to_string(float_format=lambda x: f"{x:.4f}"))

    print("\n=== Top-3 Accuracy by Lap ===")
    print(top3_pivot.to_string(float_format=lambda x: f"{x:.4f}"))

    # Plots
    top1_plot = analysis_dir / "model_accuracy_vs_lap_top1.png"
    top3_plot = analysis_dir / "model_accuracy_vs_lap_top3.png"

    plot_metric(
        out_df,
        metric="top1",
        out_path=top1_plot,
        title="Top-1 Race Winner Prediction Accuracy vs Race Progress",
    )

    plot_metric(
        out_df,
        metric="top3",
        out_path=top3_plot,
        title="Top-3 Race Winner Prediction Accuracy vs Race Progress",
    )

    print("\nSaved:")
    print(out_csv)
    print(top1_plot)
    print(top3_plot)


if __name__ == "__main__":
    main()