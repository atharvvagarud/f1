# Lap-10 Master Comparison (Non-Weather vs Weather)

| Model | Dataset | Top-1 | Top-3 | Log Loss |
| --- | --- | --- | --- | --- |
| Fastest lap at lap 10 (lap_time_x_seconds) | Non-Weather | 0.4619 ± 0.0573 | 0.7800 ± 0.0848 | nan |
| Leader at lap 10 (position_x) | Non-Weather | 0.5786 ± 0.1325 | 0.9048 ± 0.1010 | nan |
| Lowest driver_number (sanity baseline) | Non-Weather | 0.3371 ± 0.0529 | 0.3467 ± 0.0562 | nan |
| Logistic Regression | Non-Weather | 0.5786 ± 0.1185 | 0.8852 ± 0.0880 | 0.3135 ± 0.0101 |
| HistGradientBoostingClassifier | Non-Weather | 0.5105 ± 0.0829 | 0.9048 ± 0.0852 | 0.1528 ± 0.0391 |
| Fastest lap at lap 10 (lap_time_x_seconds) | Weather | 0.4614 ± 0.0707 | 0.7786 ± 0.0995 | nan |
| Leader at lap 10 (position_x) | Weather | 0.5786 ± 0.1141 | 0.9043 ± 0.0470 | nan |
| Lowest driver_number (sanity baseline) | Weather | 0.3367 ± 0.0678 | 0.3462 ± 0.0850 | nan |
| Logistic Regression (weather) | Weather | 0.5590 ± 0.0975 | 0.8943 ± 0.0354 | 0.3309 ± 0.0221 |
| HGB (weather) | Weather | 0.5295 ± 0.0782 | 0.8848 ± 0.0226 | 0.1513 ± 0.0187 |
| HGB (weather, tuned) | Weather | 0.5786 ± 0.1020 | 0.9043 ± 0.0421 | 0.1096 ± 0.0154 |
