import sys
from pathlib import Path
from collections import Counter
import joblib
import pandas as pd
import streamlit as st
import matplotlib.pyplot as plt

# --------------------------------------------------
# Project root / imports
# --------------------------------------------------

ROOT = Path(__file__).resolve().parent
sys.path.append(str(ROOT))

CHECKPOINTS = [5, 10, 15, 20, 25]
MODELS = ["logreg", "hgb", "xgboost"]

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

MODEL_LABELS = {
    "logreg": "Logistic Regression",
    "hgb": "HistGradientBoosting",
    "xgboost": "XGBoost",
}


# --------------------------------------------------
# Styling
# --------------------------------------------------

def load_css():
    st.markdown(
        """
        <style>
        .stApp {
            background: linear-gradient(180deg, #0b1220 0%, #0f172a 100%);
        }

        h1 {
            font-size: 48px !important;
            font-weight: 700 !important;
            letter-spacing: -0.5px;
            margin-bottom: 0.2rem !important;
        }

        h2 {
            font-size: 28px !important;
            margin-top: 18px !important;
        }

        h3 {
            font-size: 22px !important;
        }

        section[data-testid="stSidebar"] {
            background-color: #111827;
            border-right: 1px solid #1f2937;
        }

        div[data-testid="stMetric"] {
            background-color: #111827;
            border: 1px solid #1f2937;
            padding: 18px;
            border-radius: 14px;
            text-align: center;
            box-shadow: 0 4px 14px rgba(0,0,0,0.28);
        }

        div[data-testid="stMetricLabel"] {
            font-size: 14px;
            color: #9ca3af;
        }

        div[data-testid="stMetricValue"] {
            font-size: 32px;
            font-weight: 700;
        }

        button[kind="primary"] {
            background: linear-gradient(90deg, #ff4b4b, #ff6b6b);
            border: none;
            border-radius: 10px;
            font-weight: 600;
        }

        button[kind="primary"]:hover {
            background: linear-gradient(90deg, #ff5a5a, #ff7b7b);
        }

        .stDataFrame {
            border-radius: 12px;
            overflow: hidden;
        }

        div[data-testid="stInfo"],
        div[data-testid="stSuccess"],
        div[data-testid="stWarning"] {
            border-radius: 10px;
        }

        .stPlotlyChart, .stPyplot {
            background-color: #111827;
            padding: 10px;
            border-radius: 12px;
        }

        hr {
            border: none;
            border-top: 1px solid #1f2937;
            margin-top: 24px;
            margin-bottom: 24px;
        }

        .hero-card {
            padding: 20px;
            border-radius: 14px;
            background: #111827;
            border: 1px solid #1f2937;
            margin-bottom: 20px;
            box-shadow: 0 4px 14px rgba(0,0,0,0.28);
        }

        .prob-card {
            background: #111827;
            border: 1px solid #1f2937;
            border-radius: 14px;
            padding: 18px;
            box-shadow: 0 4px 14px rgba(0,0,0,0.28);
        }

        .prob-title {
            font-size: 18px;
            font-weight: 600;
            margin-bottom: 12px;
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


# --------------------------------------------------
# Helpers
# --------------------------------------------------

def get_dataset_path(lap: int) -> Path:
    return ROOT / "data" / "processed" / f"lap{lap}" / "base" / "dataset_clean.csv"


def get_model_dir(model_name: str, lap: int) -> Path:
    return ROOT / "results" / "models" / f"{model_name}_lap{lap}_multilap"


@st.cache_data
def load_dataset(lap: int) -> pd.DataFrame:
    path = get_dataset_path(lap)
    if not path.exists():
        raise FileNotFoundError(f"Dataset not found: {path}")
    return pd.read_csv(path)


@st.cache_resource
def load_model(model_name: str, lap: int):
    model_dir = get_model_dir(model_name, lap)
    tuned = model_dir / "model_tuned.pkl"
    base = model_dir / "model.pkl"

    if tuned.exists():
        return joblib.load(tuned), tuned.name
    if base.exists():
        return joblib.load(base), base.name

    raise FileNotFoundError(f"No model found in {model_dir}")


@st.cache_data
def get_available_races():
    df = load_dataset(10)
    races = (
        df[["year", "event_name"]]
        .drop_duplicates()
        .sort_values(["year", "event_name"])
        .reset_index(drop=True)
    )
    return races


def predict_one_model_one_checkpoint(model_name: str, lap: int, year: int, event: str):
    df = load_dataset(lap)
    race_df = df[(df["year"] == year) & (df["event_name"] == event)].copy()

    if race_df.empty:
        return None

    model, model_file = load_model(model_name, lap)

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

    if "pred_proba" in top5.columns:
        top5["pred_proba"] = top5["pred_proba"].round(3)

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
        "top5": top5,
        "race_df": race_df,
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


def build_probability_evolution_figure(results, year, event):
    fig, ax = plt.subplots(figsize=(9, 5))

    for model_name in MODELS:
        model_results = [r for r in results if r["model"] == model_name]
        model_results = sorted(model_results, key=lambda x: x["lap"])

        if not model_results:
            continue

        laps = [r["lap"] for r in model_results]
        probs = [r["predicted_win_probability"] for r in model_results]

        ax.plot(laps, probs, marker="o", linewidth=2, label=MODEL_LABELS[model_name])

    ax.set_title(f"Winner Probability Evolution – {year} {event}")
    ax.set_xlabel("Lap checkpoint")
    ax.set_ylabel("Predicted winner probability")
    ax.set_xticks(CHECKPOINTS)
    ax.grid(True, alpha=0.3)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.legend()

    return fig


def make_probability_bar_df(top5_df: pd.DataFrame) -> pd.DataFrame:
    df = top5_df.copy()
    if "win_probability" in df.columns:
        df["win_probability"] = df["win_probability"].astype(float)
        df["win_probability_pct"] = (df["win_probability"] * 100).round(1)
    return df


def run_ensemble_prediction(year: int, event: str):
    results = []

    for lap in CHECKPOINTS:
        for model_name in MODELS:
            try:
                r = predict_one_model_one_checkpoint(model_name, lap, year, event)
                if r is not None:
                    results.append(r)
            except Exception as e:
                st.warning(f"{MODEL_LABELS[model_name]} at Lap {lap} failed: {e}")

    if not results:
        return None, None, None, None, None

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

    confidence_value = None
    confidence_label = None
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

    return (
        summary_df,
        latest_lap,
        (final_winner, decision_reason, actual_winner, agreement_count, confidence_value, confidence_label),
        latest_top5,
        results,
    )


def run_single_model_prediction(year: int, event: str, selected_model: str):
    results = []

    for lap in CHECKPOINTS:
        try:
            r = predict_one_model_one_checkpoint(selected_model, lap, year, event)
            if r is not None:
                results.append(r)
        except Exception as e:
            st.warning(f"{MODEL_LABELS[selected_model]} at Lap {lap} failed: {e}")

    if not results:
        return None, None, None

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
    return summary_df, latest, results


# --------------------------------------------------
# Streamlit UI
# --------------------------------------------------

st.set_page_config(
    page_title="F1 Race Winner Predictor",
    page_icon="🏁",
    layout="wide",
)

load_css()

st.markdown(
    """
# 🏁 F1 Race Winner Predictor

Predict the **eventual race winner** using tuned machine learning models across multiple race checkpoints.
"""
)

st.markdown(
    """
<div class="hero-card">
<b>This dashboard uses tuned machine learning models trained on FastF1 telemetry data.</b><br><br>
Models included:<br>
• Logistic Regression<br>
• HistGradientBoosting<br>
• XGBoost<br><br>
Predictions are generated at race checkpoints:<br>
Lap 5 • Lap 10 • Lap 15 • Lap 20 • Lap 25
</div>
""",
    unsafe_allow_html=True,
)

with st.sidebar:
    st.markdown("### ⚙️ Controls")

    races = get_available_races()
    years = sorted(races["year"].unique().tolist())

    selected_year = st.selectbox("Year", years, index=len(years) - 1)

    race_options = races[races["year"] == selected_year]["event_name"].tolist()
    selected_event = st.selectbox("Grand Prix", race_options)

    mode = st.radio("Mode", ["Ensemble", "Single model"])

    selected_model = None
    if mode == "Single model":
        selected_model = st.selectbox(
            "Model family",
            options=["logreg", "hgb", "xgboost"],
            format_func=lambda x: MODEL_LABELS[x],
        )

    run_button = st.button("Predict Winner", type="primary")

if run_button:
    if mode == "Ensemble":
        output = run_ensemble_prediction(selected_year, selected_event)

        if output[0] is None:
            st.error("No predictions could be generated for this race.")
        else:
            summary_df, latest_lap, final_info, latest_top5, raw_results = output
            final_winner, decision_reason, actual_winner, agreement_count, confidence_value, confidence_label = final_info

            col1, col2, col3, col4, col5 = st.columns(5, gap="large")
            col1.metric("Final Predicted Winner", final_winner)
            col2.metric("Latest Checkpoint Used", f"Lap {latest_lap}")
            col3.metric("Actual Winner", actual_winner if actual_winner else "N/A")
            col4.metric("Model Agreement", f"{agreement_count} / 3")
            col5.metric(confidence_label, f"{confidence_value * 100:.1f}%")

            st.info(f"Decision rule: **{decision_reason}**")

            st.success(
                f"All available checkpoint models were evaluated. The final ensemble prediction is **{final_winner}**, "
                f"with **{agreement_count}/3** model agreement at **Lap {latest_lap}**."
            )

            st.markdown("## Checkpoint Predictions Across All Models")
            st.dataframe(summary_df, use_container_width=True)

            st.markdown("## Winner Probability Evolution")
            fig = build_probability_evolution_figure(raw_results, selected_year, selected_event)
            st.pyplot(fig, use_container_width=True)

            st.divider()
            st.markdown(f"## 🏎 Top 5 Drivers at Final Checkpoint (Lap {latest_lap})")
            cols = st.columns(3, gap="large")
            labels = ["Logistic Regression", "HistGradientBoosting", "XGBoost"]

            for i, label in enumerate(labels):
                with cols[i]:
                    st.markdown(f"### {label}")
                    if label in latest_top5:
                        top5_df = latest_top5[label].copy()
                        st.dataframe(top5_df, use_container_width=True)

                        prob_df = make_probability_bar_df(top5_df)
                        if "win_probability_pct" in prob_df.columns:
                            st.markdown('<div class="prob-card">', unsafe_allow_html=True)
                            st.markdown('<div class="prob-title">Driver Probability Bars</div>', unsafe_allow_html=True)
                            chart_df = prob_df.set_index("driver")[["win_probability_pct"]]
                            st.bar_chart(chart_df, use_container_width=True)
                            st.markdown("</div>", unsafe_allow_html=True)
                    else:
                        st.write("No data available.")

    else:
        output = run_single_model_prediction(selected_year, selected_event, selected_model)

        if output[0] is None:
            st.error("No predictions could be generated for this race.")
        else:
            summary_df, latest, raw_results = output

            col1, col2, col3 = st.columns(3, gap="large")
            col1.metric("Model", MODEL_LABELS[selected_model])
            col2.metric("Final Predicted Winner", latest["predicted_winner"])
            col3.metric("Latest Checkpoint Used", f"Lap {latest['lap']}")

            if latest["actual_winner"] is not None:
                st.metric("Actual Winner", latest["actual_winner"])

            st.success(
                f"{MODEL_LABELS[selected_model]} predicts **{latest['predicted_winner']}** "
                f"at the latest available checkpoint (**Lap {latest['lap']}**)."
            )

            st.markdown("## Checkpoint Predictions")
            st.dataframe(summary_df, use_container_width=True)

            st.markdown("## Winner Probability Evolution")
            fig, ax = plt.subplots(figsize=(9, 5))
            laps = [r["lap"] for r in sorted(raw_results, key=lambda x: x["lap"])]
            probs = [r["predicted_win_probability"] for r in sorted(raw_results, key=lambda x: x["lap"])]
            ax.plot(laps, probs, marker="o", linewidth=2)
            ax.set_title(f"Winner Probability Evolution – {MODEL_LABELS[selected_model]} – {selected_year} {selected_event}")
            ax.set_xlabel("Lap checkpoint")
            ax.set_ylabel("Predicted winner probability")
            ax.set_xticks(CHECKPOINTS)
            ax.grid(True, alpha=0.3)
            ax.spines["top"].set_visible(False)
            ax.spines["right"].set_visible(False)
            st.pyplot(fig, use_container_width=True)

            st.divider()
            st.markdown(f"## 🏎 Top 5 Drivers at Final Checkpoint (Lap {latest['lap']})")
            st.dataframe(latest["top5"], use_container_width=True)

            prob_df = make_probability_bar_df(latest["top5"])
            if "win_probability_pct" in prob_df.columns:
                st.markdown('<div class="prob-card">', unsafe_allow_html=True)
                st.markdown('<div class="prob-title">Driver Probability Bars</div>', unsafe_allow_html=True)
                chart_df = prob_df.set_index("driver")[["win_probability_pct"]]
                st.bar_chart(chart_df, use_container_width=True)
                st.markdown("</div>", unsafe_allow_html=True)
else:
    st.markdown("## How it works")
    st.markdown(
        """
- Select a **year** and **Grand Prix**
- Choose **Ensemble** or **Single model**
- Click **Predict Winner**

**Ensemble mode**:
- runs Logistic Regression, HGB, and XGBoost at all checkpoints
- uses the latest checkpoint available
- applies majority vote across model predictions
- uses XGBoost as tie-breaker if all three disagree

**Single model mode**:
- lets you inspect one model family across checkpoints
"""
    )