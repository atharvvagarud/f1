# Model Evaluation — 2025 One-Shot Holdout (D-EVAL)

Factual compact record. No composite score. No ranking against external
systems. ROC-AUC/PR-AUC are discrimination metrics, not race-ranking
metrics.

| Metric | Value | Aggregation |
|---|---|---|
| Log Loss | 0.0680 | race-macro |
| Brier | 0.0200 | race-macro |
| ROC-AUC | 0.9845 | race-macro |
| PR-AUC | 0.8032 | race-macro |
| Top-1 | 79.6% | synchronized |
| Top-3 | 97.9% | synchronized |

Stage log loss: EARLY 0.077468 / MID 0.069800 / LATE 0.056847.

Model: LogisticRegression, C=0.01, RAW (retained over Platt/Isotonic per
M8 development evidence), 84 predictive features (ALL_84 v8). Training:
2018–2024 (FINAL_FIT, 149 races, 162728 states). Evaluation: 2025
ONE-SHOT HOLDOUT (24 races, 26692 states), first and only sanctioned
target evaluation; no post-holdout tuning. Full precision in
`data/v2/model_lab/reports/final_holdout_2025_v1.json`; rounded display
matches `MODEL_LAB_FINAL_MODEL_CARD.md`.
