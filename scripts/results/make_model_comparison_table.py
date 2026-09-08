"""
Build NON-WEATHER Lap-10 comparison table (Baselines + LogReg + HGB).

Inputs:
- results/baselines/lap10_baseline_results_cv_summary.csv
- results/models/logreg_lap10/metrics_cv.csv
- results/models/hgb_lap10/metrics_cv.csv

Outputs:
- results/comparisons/lap10_model_comparison.csv
- results/comparisons/lap10_model_comparison.md

Run:
  python .\scripts\results\make_model_comparison_table.py
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


def parse_mean_std(text: str) -> tuple[float, float]:
    """
    Parse strings like:
      '0.5600 ± 0.1735'
      '0.5600 +/- 0.1735'
      '0.5600±0.1735'
    """
    s = str(text).strip()
    s = s.replace("+/-", "±")
    s = s.replace("+-", "±")
    s = s.replace(" ", "")
    m = re.match(r"^([0-9]*\.?[0-9]+)±([0-9]*\.?[0-9]+)$", s)
    if not m:
        raise ValueError(f"Could not parse mean±std from: {text}")
    return float(m.group(1)), float(m.group(2))


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

    # Newer format: top1_mean±std / top3_mean±std
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

    # Older format: top1_mean, top1_std, top3_mean, top3_std
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

    # Find the MEAN±STD row robustly
    mean_row = None
    for _, r in df.iterrows():
        for v in r.values:
            if isinstance(v, str) and "MEAN±STD" in v:
                mean_row = r
                break
        if mean_row is not None:
            break

    if mean_row is None:
        # Fallback: compute mean/std from folds (numeric)
        for col in ["top1_accuracy", "top3_accuracy", "log_loss"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")
        mean_row = {
            "top1_accuracy": fmt_mean_std(df["top1_accuracy"].mean(), df["top1_accuracy"].std(ddof=0)),
            "top3_accuracy": fmt_mean_std(df["top3_accuracy"].mean(), df["top3_accuracy"].std(ddof=0)),
            "log_loss": fmt_mean_std(df["log_loss"].mean(), df["log_loss"].std(ddof=0)),
        }
        return {"model": pretty_name, **mean_row}

    # In your scripts, the MEAN±STD row already stores strings like "0.5495 ± 0.1569"
    return {
        "model": pretty_name,
        "top1_accuracy": str(mean_row["top1_accuracy"]),
        "top3_accuracy": str(mean_row["top3_accuracy"]),
        "log_loss": str(mean_row["log_loss"]),
    }


def main() -> None:
    ROOT = find_project_root(Path(__file__).resolve())

    BASELINE_CV_SUM = ROOT / "results" / "baselines" / "lap10_baseline_results_cv_summary.csv"
    LOGREG_CV = ROOT / "results" / "models" / "logreg_lap10" / "metrics_cv.csv"
    HGB_CV = ROOT / "results" / "models" / "hgb_lap10" / "metrics_cv.csv"

    OUT_DIR = ROOT / "results" / "comparisons"
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    OUT_CSV = OUT_DIR / "lap10_model_comparison.csv"
    OUT_MD = OUT_DIR / "lap10_model_comparison.md"

    baselines = load_baseline_cv_summary(BASELINE_CV_SUM)
    logreg = load_model_cv_metrics(LOGREG_CV, "Logistic Regression")
    hgb = load_model_cv_metrics(HGB_CV, "HistGradientBoostingClassifier")

    models_df = pd.DataFrame([logreg, hgb])
    comparison = pd.concat([baselines, models_df], ignore_index=True)

    # Save CSV
    comparison.to_csv(OUT_CSV, index=False)

    # Save MD without tabulate
    headers = ["model", "top1_accuracy", "top3_accuracy", "log_loss"]
    rows = comparison[headers].astype(str).values.tolist()
    md = "# Lap-10 (Non-Weather) Model Comparison\n\n"
    md += markdown_table(["Model", "Top-1", "Top-3", "Log Loss"], rows)
    md += "\nNotes:\n- Metrics are GroupKFold CV mean ± std across folds.\n- Log Loss is N/A for non-probabilistic baselines.\n"
    OUT_MD.write_text(md, encoding="utf-8")

    print(f"Saved NON-WEATHER model comparison CSV: {OUT_CSV}")
    print(f"Saved NON-WEATHER model comparison MD:  {OUT_MD}")


if __name__ == "__main__":
    main()