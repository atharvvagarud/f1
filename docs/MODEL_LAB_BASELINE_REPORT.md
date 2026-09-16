# Model Lab Baseline Report — non-ML development benchmarks

**DEVELOPMENT RESULTS — 2022 / 2023 / 2024**

**2025 PROTECTED FINAL HOLDOUT — NOT EVALUATED**

All numbers below are development-fold results produced by the frozen non-ML baselines. They are the empirical floor later ML models must beat — not final test performance. No candidate ML model has been run. Every value traces to a stored experiment result (task `winner`, protocol v1, matrix d2ee966c18d2…).

## 1. Headline probability quality (race-macro)

### log_loss (race-macro; lower is better)

| baseline | D1 | D2 | D3 | mean |
| --- | --- | --- | --- | --- |
| CURRENT_LEADER | 1.012626 | 0.539277 | 0.951977 | 0.834627 |
| CURRENT_ORDER | 1.012626 | 0.539277 | 0.951977 | 0.834627 |
| GRID_POLE | 1.852530 | 1.349017 | 1.915861 | 1.705803 |
| RECENT_PACE | N/A | N/A | N/A | N/A |
| CLASS_PRIOR | 0.214068 | 0.211307 | 0.211340 | 0.212238 |

### brier (race-macro; lower is better)

| baseline | D1 | D2 | D3 | mean |
| --- | --- | --- | --- | --- |
| CURRENT_LEADER | 0.029318 | 0.015613 | 0.027562 | 0.024165 |
| CURRENT_ORDER | 0.029318 | 0.015613 | 0.027562 | 0.024165 |
| GRID_POLE | 0.053636 | 0.039058 | 0.055469 | 0.049388 |
| RECENT_PACE | N/A | N/A | N/A | N/A |
| CLASS_PRIOR | 0.052315 | 0.051450 | 0.051461 | 0.051742 |

## 2. State-pooled diagnostics (not headline)

### log_loss (state-pooled)

| baseline | D1 | D2 | D3 | mean |
| --- | --- | --- | --- | --- |
| CURRENT_LEADER | 0.997632 | 0.503478 | 0.965840 | 0.822317 |
| CURRENT_ORDER | 0.997632 | 0.503478 | 0.965840 | 0.822317 |
| GRID_POLE | 1.800423 | 1.272838 | 1.914803 | 1.662688 |
| RECENT_PACE | N/A | N/A | N/A | N/A |
| CLASS_PRIOR | 0.212773 | 0.210864 | 0.210916 | 0.211518 |

### brier (state-pooled)

| baseline | D1 | D2 | D3 | mean |
| --- | --- | --- | --- | --- |
| CURRENT_LEADER | 0.028884 | 0.014577 | 0.027964 | 0.023808 |
| CURRENT_ORDER | 0.028884 | 0.014577 | 0.027964 | 0.023808 |
| GRID_POLE | 0.052127 | 0.036852 | 0.055439 | 0.048139 |
| RECENT_PACE | N/A | N/A | N/A | N/A |
| CLASS_PRIOR | 0.051910 | 0.051312 | 0.051328 | 0.051516 |

## 3. Discrimination (race-macro ROC-AUC / PR-AUC)

### roc_auc (race-macro; higher is better)

| baseline | D1 | D2 | D3 | mean |
| --- | --- | --- | --- | --- |
| CURRENT_LEADER | 0.860631 | 0.923215 | 0.863590 | 0.882478 |
| CURRENT_ORDER | 0.860631 | 0.923215 | 0.863590 | 0.882478 |
| GRID_POLE | 0.714963 | 0.807863 | 0.715322 | 0.746049 |
| RECENT_PACE | 0.853633 | 0.802262 | 0.784896 | 0.813597 |
| CLASS_PRIOR | 0.500000 | 0.500000 | 0.500000 | 0.500000 |

### pr_auc (race-macro; higher is better)

| baseline | D1 | D2 | D3 | mean |
| --- | --- | --- | --- | --- |
| CURRENT_LEADER | 0.613725 | 0.762168 | 0.639359 | 0.671751 |
| CURRENT_ORDER | 0.613725 | 0.762168 | 0.639359 | 0.671751 |
| GRID_POLE | 0.484940 | 0.655892 | 0.487607 | 0.542813 |
| RECENT_PACE | 0.325139 | 0.298350 | 0.211801 | 0.278430 |
| CLASS_PRIOR | 0.055382 | 0.054410 | 0.054423 | 0.054738 |

## 4. Calibration (ECE, 10 equal-width bins)

| baseline | D1 | D2 | D3 |
| --- | --- | --- | --- |
| CURRENT_LEADER | 0.028884 | 0.014577 | 0.027964 |
| CURRENT_ORDER | 0.028884 | 0.014577 | 0.027964 |
| GRID_POLE | 0.052127 | 0.036852 | 0.055439 |
| RECENT_PACE | N/A | N/A | N/A |
| CLASS_PRIOR | 0.000246 | 0.000866 | 0.000692 |

Reliability-bin detail (counts, mean predicted, observed frequency, weight) is stored per experiment result; no calibrator was fitted.

## 5. Race-stage performance (race-macro)

### log_loss by stage

#### D1

| baseline | EARLY | MID | LATE |
| --- | --- | --- | --- |
| CURRENT_LEADER | 1.486141 | 1.023644 | 0.487823 |
| CURRENT_ORDER | 1.486141 | 1.023644 | 0.487823 |
| GRID_POLE | 1.875084 | 1.805015 | 1.986676 |
| RECENT_PACE | N/A | N/A | N/A |
| CLASS_PRIOR | 0.205200 | 0.215058 | 0.223789 |

#### D2

| baseline | EARLY | MID | LATE |
| --- | --- | --- | --- |
| CURRENT_LEADER | 1.041433 | 0.498744 | 0.082389 |
| CURRENT_ORDER | 1.041433 | 0.498744 | 0.082389 |
| GRID_POLE | 1.314293 | 1.345199 | 1.388270 |
| RECENT_PACE | N/A | N/A | N/A |
| CLASS_PRIOR | 0.205385 | 0.211248 | 0.217709 |

#### D3

| baseline | EARLY | MID | LATE |
| --- | --- | --- | --- |
| CURRENT_LEADER | 1.450905 | 0.920854 | 0.471920 |
| CURRENT_ORDER | 1.450905 | 0.920854 | 0.471920 |
| GRID_POLE | 1.883874 | 1.931108 | 1.937344 |
| RECENT_PACE | N/A | N/A | N/A |
| CLASS_PRIOR | 0.205713 | 0.211662 | 0.216977 |

### brier by stage

#### D1

| baseline | EARLY | MID | LATE |
| --- | --- | --- | --- |
| CURRENT_LEADER | 0.043028 | 0.029637 | 0.014124 |
| CURRENT_ORDER | 0.043028 | 0.029637 | 0.014124 |
| GRID_POLE | 0.054289 | 0.052260 | 0.057520 |
| RECENT_PACE | N/A | N/A | N/A |
| CLASS_PRIOR | 0.049537 | 0.052625 | 0.055360 |

#### D2

| baseline | EARLY | MID | LATE |
| --- | --- | --- | --- |
| CURRENT_LEADER | 0.030152 | 0.014440 | 0.002385 |
| CURRENT_ORDER | 0.030152 | 0.014440 | 0.002385 |
| GRID_POLE | 0.038052 | 0.038947 | 0.040194 |
| RECENT_PACE | N/A | N/A | N/A |
| CLASS_PRIOR | 0.049596 | 0.051432 | 0.053455 |

#### D3

| baseline | EARLY | MID | LATE |
| --- | --- | --- | --- |
| CURRENT_LEADER | 0.042008 | 0.026661 | 0.013663 |
| CURRENT_ORDER | 0.042008 | 0.026661 | 0.013663 |
| GRID_POLE | 0.054543 | 0.055911 | 0.056091 |
| RECENT_PACE | N/A | N/A | N/A |
| CLASS_PRIOR | 0.049700 | 0.051562 | 0.053225 |

## 6. Synchronized winner top-k (development races)

| baseline | fold | top-1 | top-3 | eval states | skipped (none/winner-unobs/degen) | min field | top-3 coverage |
| --- | --- | --- | --- | --- | --- | --- | --- |
| CURRENT_LEADER | D1 | 0.730339 | 0.734333 | 23537 | 0/32/8 | 2 | INSUFFICIENT for 3-way discrimination (field < 3) |
| CURRENT_ORDER | D1 | 0.730339 | 0.734333 | 23537 | 0/32/8 | 2 | INSUFFICIENT for 3-way discrimination (field < 3) |
| GRID_POLE | D1 | 0.468411 | 0.470323 | 23537 | 0/32/8 | 2 | INSUFFICIENT for 3-way discrimination (field < 3) |
| RECENT_PACE | D1 | N/A | N/A | N/A | N/A | N/A | winner top-k requires BINARY_PROBABILITY predictions; got RANKING_SCORE |
| CLASS_PRIOR | D1 | 0.000510 | 0.004546 | 23537 | 0/32/8 | 2 | INSUFFICIENT for 3-way discrimination (field < 3) |
| CURRENT_LEADER | D2 | 0.861478 | 0.863364 | 24386 | 0/25/11 | 2 | INSUFFICIENT for 3-way discrimination (field < 3) |
| CURRENT_ORDER | D2 | 0.861478 | 0.863364 | 24386 | 0/25/11 | 2 | INSUFFICIENT for 3-way discrimination (field < 3) |
| GRID_POLE | D2 | 0.657877 | 0.658944 | 24386 | 0/25/11 | 2 | INSUFFICIENT for 3-way discrimination (field < 3) |
| RECENT_PACE | D2 | N/A | N/A | N/A | N/A | N/A | winner top-k requires BINARY_PROBABILITY predictions; got RANKING_SCORE |
| CLASS_PRIOR | D2 | 0.000492 | 0.003814 | 24386 | 0/25/11 | 2 | INSUFFICIENT for 3-way discrimination (field < 3) |
| CURRENT_LEADER | D3 | 0.732987 | 0.735735 | 26568 | 0/30/8 | 2 | INSUFFICIENT for 3-way discrimination (field < 3) |
| CURRENT_ORDER | D3 | 0.732987 | 0.735735 | 26568 | 0/30/8 | 2 | INSUFFICIENT for 3-way discrimination (field < 3) |
| GRID_POLE | D3 | 0.460291 | 0.461984 | 26568 | 0/30/8 | 2 | INSUFFICIENT for 3-way discrimination (field < 3) |
| RECENT_PACE | D3 | N/A | N/A | N/A | N/A | N/A | winner top-k requires BINARY_PROBABILITY predictions; got RANKING_SCORE |
| CLASS_PRIOR | D3 | 0.000828 | 0.004780 | 26568 | 0/30/8 | 2 | INSUFFICIENT for 3-way discrimination (field < 3) |

Top-3 values on fields smaller than 3 are reported for completeness but are NOT genuine three-way discrimination (see coverage column and M1.1 eligibility contract).

## 7. Baseline semantics + metric applicability

- CURRENT_LEADER: kind=BINARY_PROBABILITY; train_dependence=False; required_columns=['position']; output=binary probability (winner: INDEPENDENT_BINARY)
- CURRENT_ORDER: kind=BINARY_PROBABILITY; train_dependence=False; required_columns=['position']; output=binary probability (winner: INDEPENDENT_BINARY)
- GRID_POLE: kind=BINARY_PROBABILITY; train_dependence=False; required_columns=['grid_position']; output=binary probability / ordinal finish from grid
- RECENT_PACE: kind=RANKING_SCORE; train_dependence=False; required_columns=['representative_recent_pace_s']; output=ranking score (NOT a probability)
  NOT_APPLICABLE: log_loss: NOT_APPLICABLE; brier: NOT_APPLICABLE; expected_calibration_error: NOT_APPLICABLE; winner_top_k: NOT_APPLICABLE
- CLASS_PRIOR: kind=BINARY_PROBABILITY; train_dependence=True; required_columns=[]; output=constant train-prevalence binary probability

## 8. Baseline comparison (development means, factual)

- strongest probability baseline by mean race-macro log loss: **CLASS_PRIOR** (0.212238)
- strongest probability baseline by mean race-macro Brier: **CURRENT_LEADER** (0.024165)
- strongest ranking baseline by mean race-macro ROC-AUC: **CURRENT_LEADER** (0.882478)
- strongest synchronized winner ranking by mean top-1: **CURRENT_LEADER** (0.774935)
- no combined score is constructed; no significance is claimed.

## 9. Baseline floor for M3+ (development)

- probability quality log_loss (mean race-macro): CURRENT_LEADER=0.834627; CURRENT_ORDER=0.834627; GRID_POLE=1.705803; CLASS_PRIOR=0.212238
- probability quality brier (mean race-macro): CURRENT_LEADER=0.024165; CURRENT_ORDER=0.024165; GRID_POLE=0.049388; CLASS_PRIOR=0.051742
- discrimination ROC-AUC (mean race-macro): CURRENT_LEADER=0.882478; CURRENT_ORDER=0.882478; GRID_POLE=0.746049; RECENT_PACE=0.813597; CLASS_PRIOR=0.500000
- discrimination PR-AUC (mean race-macro): CURRENT_LEADER=0.671751; CURRENT_ORDER=0.671751; GRID_POLE=0.542813; RECENT_PACE=0.278430; CLASS_PRIOR=0.054738
- calibration ECE per fold: D1=CURRENT_LEADER=0.028884, CURRENT_ORDER=0.028884, GRID_POLE=0.052127, RECENT_PACE=N/A, CLASS_PRIOR=0.000246; D2=CURRENT_LEADER=0.014577, CURRENT_ORDER=0.014577, GRID_POLE=0.036852, RECENT_PACE=N/A, CLASS_PRIOR=0.000866; D3=CURRENT_LEADER=0.027964, CURRENT_ORDER=0.027964, GRID_POLE=0.055439, RECENT_PACE=N/A, CLASS_PRIOR=0.000692
- synchronized winner top-1/top-3: see §6 (coverage-qualified).
- stage performance: see §5 (per-fold EARLY/MID/LATE).

## 10. Firewalls, determinism, runtime

- holdout_accessed: False (2025 protected final holdout — not evaluated)
- determinism rerun (CLASS_PRIOR/D1, d0ffd4a2eb1c…): rerun result bytes identical = True
- synchronized top-k subset benchmark (CURRENT_LEADER/D1, 2 races, 1942 states): 0.68 s
- full suite wall time: 120.3 s
- peak RSS: 1.02 GB
- secondary smoke (GRID_POLE/final_position/D1): mae race-macro = 3.377613 (737ee290be03…; infrastructure smoke only; not a leaderboard)

## 11. Artifacts

- CURRENT_LEADER/D1: `673df77d958b466caebfe6bbe2e6ef96f03e0750a4a82570ff2318274cb81f2d`
- CURRENT_ORDER/D1: `58b315c42a19059de7541163f2773a9c6cbdf86e162eb0e8bfc2a9a9c1bbbe5d`
- GRID_POLE/D1: `d15833fa269b5bab1f3631422cf92ece4376c8c56b378db121b51bfd9d52af88`
- RECENT_PACE/D1: `8728995288e04ecbc66aefc55091d891f9ad27f599e21c313f2e5faf49a1cd19`
- CLASS_PRIOR/D1: `d0ffd4a2eb1c5e5749b6c6c8cc261832bf46c8eaaa439d2ed4cb954f3415659a`
- CURRENT_LEADER/D2: `298652df6c6d02914d16afc2fdd1c47ee5df3a45fa325b6c67bae9caa644939c`
- CURRENT_ORDER/D2: `4bc50439d2ba3c942d0144a6f63f04fa08c557aee6b95938f1a83e41b566b1bb`
- GRID_POLE/D2: `d7283136b80db7aaab84e66fcf256bcb9f943d75c1cefff34f24ac423a222568`
- RECENT_PACE/D2: `6cff38ca27443ea74a8d47e1c97e72b50205a8b4c2fd0d7f976a0202829894ca`
- CLASS_PRIOR/D2: `920048fdb8c0164990655b8988d9c4c8986e834eb7f98bb53fa9883bfee0db87`
- CURRENT_LEADER/D3: `ac0cc555b177c0226b8f84394d440f8f6da445175d9b408f25578838dc2d6b37`
- CURRENT_ORDER/D3: `300c5ed539cc16b546eda04a8dbd9ca01ca0ef7d90a0885f5f4b5a3f6fdfaf35`
- GRID_POLE/D3: `85e78c00a70b122d4e2404484dc88101fdf6f04a10ed32102f3c3c9a53456645`
- RECENT_PACE/D3: `ef504c72a19908c5082081b072e080fe0cc5a68693f0670afd93ecbb22e63c39`
- CLASS_PRIOR/D3: `d27ba2138b3d6c419c504ffbef767f828ddc452b87532fb2ff363e60fd89e20a`

Suite summary: `data/v2/model_lab/reports/baseline_suite_v1.json` (machine-readable; this document was rendered from it).

