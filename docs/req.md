# Reproducibility Guide

This document describes how to reproduce the results of the **F1 In-Race Winner Prediction (Lap-10 Snapshot)** project.

---

# Environment

## Python Version

Python 3.14.0


## Core Libraries

fastf1==3.7.0
pandas==2.3.3
scikit-learn==1.8.0
numpy==2.4.2

The full environment is captured in: requirements.txt

Install dependencies with:  pip install -r requirements.txt

---

# FastF1 Cache

FastF1 telemetry and race data are cached locally to ensure reproducible extraction.

Cache location: data/raw/fastf1_cache/


Cache behaviour:

- Most sessions reused cached telemetry.
- The following races were newly downloaded during dataset repair:

2023 Abu Dhabi Grand Prix
2023 Japanese Grand Prix
2023 Las Vegas Grand Prix
2023 Mexico City Grand Prix
2023 Qatar Grand Prix
2023 São Paulo Grand Prix
2023 United States Grand Prix


These races were missing in the base dataset and were rebuilt to ensure dataset alignment.

---

# Dataset Pipeline

## Step 1 — Build race snapshots

Extract lap-10 snapshots from FastF1.

python scripts/data/build_dataset_multi_race.py


This produces the interim dataset: data/interim/lap10/lap10_base.csv



---

## Step 2 — Repair missing races (if necessary)

python scripts/data/build_missing_base_races.py


Adds missing races and ensures dataset completeness.

---

## Step 3 — Clean dataset

python scripts/cleaning/clean_dataset.py

Outputs: data/processed/lap10/base/dataset_clean.csv

Also generates quality reports: 
results/data_quality/lap10_base_data_quality_report.csv
results/data_quality/lap10_base_race_integrity_report.csv


Integrity checks performed:

- exactly **1 winner row per race**
- numeric coercion
- clipping of extreme values
- missing value reporting

---

# Dataset Integrity

Final dataset statistics:

Total races: 104
Winner rows per race: 1
Race set mismatch: none


Weather and non-weather datasets contain identical race sets.

---

# Model Training

## Baseline Models
python scripts/baselines/evaluate_baselines_cv.py

## Non-Weather Models

python scripts/models/train_logistic_regression.py
python scripts/models/train_hgb_classifier.py


## Weather Models
python scripts/models_weather/train_logistic_regression_weather.py
python scripts/models_weather/train_hgb_classifier_weather.py
python scripts/models_weather/train_hgb_classifier_weather_tuned.py


---

# Results Generation

Generate comparison tables:
python scripts/results/make_model_comparison_table.py
python scripts/results/make_model_comparison_table_weather.py
python scripts/results/make_master_model_comparison.py


Outputs stored in:
results/


---

# Notes

- Lap-10 snapshot was chosen to simulate **mid-race prediction conditions**.
- Missing values are not dropped; they are handled using **model imputers**.
- FastF1 lap extraction uses telemetry data and race timing information.
- Dataset cleaning ensures numerical stability and integrity before model training.