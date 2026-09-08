from pathlib import Path
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RESULTS_DIR = ROOT / "results" / "analysis"
RESULTS_DIR.mkdir(parents=True, exist_ok=True)

MODEL_FILES = {
    "LogisticRegression": ROOT / "results/models/logreg_lap10/race_predictions_cv.csv",
    "HistGradientBoosting": ROOT / "results/models/hgb_lap10/race_predictions_cv.csv",
    "XGBoost": ROOT / "results/models/xgboost_lap10/race_predictions_cv.csv",
    "LogisticRegression_weather": ROOT / "results/models/logreg_weather_lap10/race_predictions_cv.csv",
    "HistGradientBoosting_weather": ROOT / "results/models/hgb_weather_lap10/race_predictions_cv.csv",
    "HistGradientBoosting_weather_tuned": ROOT / "results/models/hgb_weather_lap10_tuned/race_predictions_cv.csv",
}


def normalize_prediction_file(model_name: str, path: Path) -> pd.DataFrame:

    df = pd.read_csv(path)

    # -----------------------------
    # Schema A — Race-level summary
    # -----------------------------
    if {"predicted_winner", "true_winner", "hit_top1", "hit_top3"}.issubset(df.columns):

        out = df.copy()
        out["model_name"] = model_name
        out["predicted"] = out["predicted_winner"]
        out["actual"] = out["true_winner"]
        out["top1"] = out["hit_top1"].astype(int)
        out["top3"] = out["hit_top3"].astype(int)

        out["winner_rank"] = 1
        out.loc[(out["top1"] == 0) & (out["top3"] == 1), "winner_rank"] = 2
        out.loc[(out["top1"] == 0) & (out["top3"] == 0), "winner_rank"] = 4

        return out[["model_name", "year", "event_name", "top1", "top3", "winner_rank"]]

    # -----------------------------
    # Schema B — Weather models
    # -----------------------------
    if {"winner_driver", "winner_rank", "top1_hit", "top3_hit"}.issubset(df.columns):

        out = df.copy()
        out["model_name"] = model_name
        out["top1"] = out["top1_hit"].astype(int)
        out["top3"] = out["top3_hit"].astype(int)
        out["winner_rank"] = out["winner_rank"]

        return out[["model_name", "year", "event_name", "top1", "top3", "winner_rank"]]

    # -----------------------------
    # Schema C — Driver-level (XGBoost)
    # -----------------------------
    if {"driver", "is_winner", "pred_proba"}.issubset(df.columns):

        rows = []

        for (year, event), g in df.groupby(["year", "event_name"]):

            g = g.sort_values("pred_proba", ascending=False)

            predicted = g.iloc[0]
            actual = g[g["is_winner"] == 1].iloc[0]

            winner_rank = (
                g.reset_index(drop=True)
                .index[g.reset_index(drop=True)["driver"] == actual["driver"]][0]
                + 1
            )

            rows.append(
                {
                    "model_name": model_name,
                    "year": year,
                    "event_name": event,
                    "top1": int(predicted["driver"] == actual["driver"]),
                    "top3": int(actual["driver"] in g.head(3)["driver"].values),
                    "winner_rank": winner_rank,
                }
            )

        return pd.DataFrame(rows)

    raise ValueError(
        f"{model_name}: unknown prediction file format\nColumns: {df.columns}"
    )


def main():

    all_rows = []

    for model_name, path in MODEL_FILES.items():

        print(f"Processing {model_name}...")

        if not path.exists():
            print(f"⚠ Missing file: {path}")
            continue

        norm = normalize_prediction_file(model_name, path)
        all_rows.append(norm)

    df = pd.concat(all_rows)

    # --------------------------------
    # Model summary
    # --------------------------------

    model_summary = (
        df.groupby("model_name")
        .agg(
            races=("event_name", "count"),
            top1_accuracy=("top1", "mean"),
            top3_accuracy=("top3", "mean"),
            mean_winner_rank=("winner_rank", "mean"),
        )
        .sort_values("top1_accuracy", ascending=False)
    )

    # --------------------------------
    # Race difficulty
    # --------------------------------

    race_level = (
        df.groupby(["year", "event_name"])
        .agg(
            models=("model_name", "count"),
            models_correct_top1=("top1", "sum"),
            models_correct_top3=("top3", "sum"),
            avg_winner_rank=("winner_rank", "mean"),
        )
        .reset_index()
    )

    race_level["models_wrong_top1"] = race_level["models"] - race_level["models_correct_top1"]

    hard_races = race_level.sort_values(
        ["models_wrong_top1", "avg_winner_rank"], ascending=[False, False]
    )

    # --------------------------------
    # Save results
    # --------------------------------

    model_summary.to_csv(RESULTS_DIR / "error_analysis_model_summary.csv")
    race_level.to_csv(RESULTS_DIR / "error_analysis_race_level.csv")
    hard_races.to_csv(RESULTS_DIR / "error_analysis_hard_races.csv")

    print("\n=== Error Analysis Model Summary ===")
    print(model_summary)

    print("\n=== Hardest Races ===")
    print(hard_races.head(15))

    print("\nSaved to:", RESULTS_DIR)


if __name__ == "__main__":
    main()