"""
Build WEATHER Lap-10 comparison table (Baselines + LogReg + HGB + Tuned HGB).

Inputs:
- results/baselines/lap10_baseline_results_cv_weather_summary.csv
- results/models/logreg_weather_lap10/metrics_cv.csv
- results/models/hgb_weather_lap10/metrics_cv.csv
- results/models/hgb_weather_lap10_tuned/metrics_cv.csv

Outputs:
- results/comparisons/lap10_weather_model_comparison.csv
- results/comparisons/lap10_weather_model_comparison.md

Run:
  python .\scripts\results\make_model_comparison_table_weather.py
"""

from __future__ import annotations

from pathlib import Path
import re
import pandas as pd


def find_project_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "data").exists() and (p / "scripts").exists():
            return p
    raise RuntimeError("Could not locate project root (missing data/ and scripts/).")


def fmt_mean_std(mean: float, std: float, decimals: int = 4) -> str:
    return f"{mean:.{decimals}f} ± {std:.{decimals}f}"


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    out = []
    out.append("| " + " | ".join(headers) + " |")
    out.append("| " + " | ".join(["---"] * len(headers)) + " |")
    for r in rows:
        out.append("| " + " | ".join(r) + " |")
    return "\n".join(out) + "\n"


def load_baseline_cv_summary(path: Path) -> pd.DataFrame:
    df = pd.read_csv(path)

    if {"top1_mean±std", "top3_mean±std"}.issubset(df.columns):
        rows = []
        for _, r in df.iterrows():
            rows.append(
                {
                    "model": r["baseline"],
                    "top1_accuracy": str(r["top1_mean±std"]),
                    "top3_accuracy": str(r["top3_mean±std"]),
                    "log_loss": "N/A",
                }
            )
        return pd.DataFrame(rows)

    needed = {"baseline", "top1_mean", "top1_std", "top3_mean", "top3_std"}
    if needed.issubset(df.columns):
        rows = []
        for _, r in df.iterrows():
            rows.append(
                {
                    "model": r["baseline"],
                    "top1_accuracy": fmt_mean_std(float(r["top1_mean"]), float(r["top1_std"])),
                    "top3_accuracy": fmt_mean_std(float(r["top3_mean"]), float(r["top3_std"])),
                    "log_loss": "N/A",
                }
            )
        return pd.DataFrame(rows)

    raise ValueError(f"Unrecognized baseline summary format: {path}. Columns: {list(df.columns)}")


def load_model_cv_metrics(path: Path, pretty_name: str) -> dict:
    df = pd.read_csv(path)

    mean_row = None
    for _, r in df.iterrows():
        for v in r.values:
            if isinstance(v, str) and "MEAN±STD" in v:
                mean_row = r
                break
        if mean_row is not None:
            break

    if mean_row is None:
        for col in ["top1_accuracy", "top3_accuracy", "log_loss"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        mean_row = {
            "top1_accuracy": fmt_mean_std(df["top1_accuracy"].mean(), df["top1_accuracy"].std(ddof=0)),
            "top3_accuracy": fmt_mean_std(df["top3_accuracy"].mean(), df["top3_accuracy"].std(ddof=0)),
            "log_loss": fmt_mean_std(df["log_loss"].mean(), df["log_loss"].std(ddof=0)),
        }
        return {"model": pretty_name, **mean_row}

    return {
        "model": pretty_name,
        "top1_accuracy": str(mean_row["top1_accuracy"]),
        "top3_accuracy": str(mean_row["top3_accuracy"]),
        "log_loss": str(mean_row["log_loss"]),
    }


def main() -> None:
    ROOT = find_project_root(Path(__file__).resolve())

    BASELINE_CV_SUM = ROOT / "results" / "baselines" / "lap10_baseline_results_cv_weather_summary.csv"
    LOGREG_CV = ROOT / "results" / "models" / "logreg_weather_lap10" / "metrics_cv.csv"
    HGB_CV = ROOT / "results" / "models" / "hgb_weather_lap10" / "metrics_cv.csv"
    HGB_TUNED_CV = ROOT / "results" / "models" / "hgb_weather_lap10_tuned" / "metrics_cv.csv"

    OUT_DIR = ROOT / "results" / "comparisons"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_CSV = OUT_DIR / "lap10_weather_model_comparison.csv"
    OUT_MD = OUT_DIR / "lap10_weather_model_comparison.md"

    baselines = load_baseline_cv_summary(BASELINE_CV_SUM)
    logreg = load_model_cv_metrics(LOGREG_CV, "Logistic Regression (weather)")
    hgb = load_model_cv_metrics(HGB_CV, "HGB (weather)")
    hgb_tuned = load_model_cv_metrics(HGB_TUNED_CV, "HGB (weather, tuned)")

    comparison = pd.concat([baselines, pd.DataFrame([logreg, hgb, hgb_tuned])], ignore_index=True)

    comparison.to_csv(OUT_CSV, index=False)

    headers = ["model", "top1_accuracy", "top3_accuracy", "log_loss"]
    rows = comparison[headers].astype(str).values.tolist()
    md = "# Lap-10 (Weather) Model Comparison\n\n"
    md += markdown_table(["Model", "Top-1", "Top-3", "Log Loss"], rows)
    md += "\nNotes:\n- Metrics are GroupKFold CV mean ± std across folds.\n- Log Loss is N/A for non-probabilistic baselines.\n"
    OUT_MD.write_text(md, encoding="utf-8")

    print(f"Saved WEATHER model comparison CSV: {OUT_CSV}")
    print(f"Saved WEATHER model comparison MD:  {OUT_MD}")


if __name__ == "__main__":
    main()