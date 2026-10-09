# V3.4 ENSEMBLE — FINAL REPORT

## Final verdict

V3.4F validation passed on every gate. V3.4 is frozen exactly as observed:
ENSEMBLE_MIXED_OUT_OF_TIME. No new science was performed in F; all values
below were recomputed from authoritative artifacts.

## Frozen parent

- Tag: `v3.3-multi-model-lab`
- Commit: `563fff21f94f169097079b003816181c31227aa9`

## Stage ledger

| Stage | Verdict | Key identity | 2025 contact |
|---|---|---|---|
| A | COMPLETE | `d6b12074…5036b352` | NONE |
| B | COMPLETE | `64ca2d29…82b5b26` | NONE |
| C | COMPLETE | `98b31597…0b41ed87` | NONE |
| D | COMPLETE | `d715dcfb…07539af68` | NONE |
| E | COMPLETE | record `74a59a50…95c72fc6`, prediction `4508c098…b81476bf` | EVALUATION_ONLY |

2025 was never used to select the ensemble recipe. Individual-model 2025
behavior was known before V3.4 (documented statically in A).

## Scientific question

Does XGBoost contain complementary predictive information that can be
combined with the frozen V3.1B Logistic model to improve winner probability
quality over Logistic alone? The burden of proof was on the ensemble; a null
result was acceptable.

## Base models

- V3.1B Logistic (C=0.01, RAW, 110 features, trained 2018–2024) — champion/baseline.
- V3.3 refined XGBoost (depth 3, lr 0.03, 300 trees, RAW, same 110 features) — diversity candidate.
- Retraining either model inside V3.4 was FORBIDDEN.

## Development protocol

Full preregistered grid w = 0.0…1.0 (resolution 0.1, adaptive refinement
FORBIDDEN) evaluated on D1/D2/D3 (validate 2022/2023/2024), plus an
expanding-window logistic stacker (D1 NOT_EVALUABLE). Primary metric:
race-macro log loss. Race-unit bootstrap (B=2000, seed 42).

## Development evidence

- w=0.2 pooled delta vs Logistic: -0.0014888766; folds 3/3 negative
  (D1 -0.001114, D2 -0.001938, D3 -0.001420).
- Fold x stage cells: 9/9 negative.
- Race bootstrap: CLEAR_SUPPORT, 95% CI [-0.00282, -0.00026] (excludes zero).
- Brier delta -0.000419 (gain); ECE delta +0.000097 (negligible cost).
- Neighbor basin w=0.1…0.4 all pooled-negative with the same fold pattern:
  broad useful region, not an isolated spike.

## Candidate selection

Exactly one candidate selected in C: fixed convex blend w=0.2, chosen for
robustness (3/3 folds + 9/9 stages + CLEAR bootstrap + Brier gain +
negligible ECE + conservative weight), NOT because it was pooled argmin.
Stacker rejected: REJECT_TEMPORAL_INSTABILITY (D2 improvement, D3
regression, D1 not evaluable).

## Final recipe

`p = 0.8 * p_logistic + 0.2 * p_xgb` (float64, state_id identity join,
RAW INDEPENDENT_BINARY, calibration NONE, field normalization FORBIDDEN).
Recipe identity: `d715dcfb19db35f01cbf369bbcba52994ff99d366364f607779d3ec07539af68`.
Bit-exact parity with frozen B w=0.2 predictions verified on all 3 folds
(23,577 + 24,422 + 26,606 rows).

## 2025 disclosure

PREVIOUSLY REVEALED OUT-OF-TIME ENSEMBLE EVALUATION. 2025 is NOT an
untouched/pristine/unseen holdout in the V3.4 context: individual-model 2025
results were observed in V3.3. The 2025 ENSEMBLE evaluation did not exist
until V3.4E executed the frozen recipe.

## 2025 result

- Logistic race-macro LL: 0.0634166678
- XGB race-macro LL: 0.0672136469
- Ensemble race-macro LL: 0.0626596199
- Ensemble − Logistic: -0.0007570479 (independently recomputed via a minimal
  identity-merge path; agreement to 1e-12; deterministic reproduction of the
  frozen prediction artifact is bit-exact, 26,692 states / 24 races).

## Race-level evidence

11 improved / 13 worsened / 0 ties. Mean delta -0.000757 (improves) while
median delta +0.000291 (median race does not improve). This nuance is
preserved; E is not summarized as universal improvement.

## Bootstrap

Race-unit paired resampling, B=2000, seed 42. 95% CI approximately
[-0.00260, +0.00097] — spans zero. Load-bearing for the MIXED disposition.

## Secondary metrics

Direction vs Logistic (diagnostic only; did not override primary
uncertainty): Brier improvement, ROC AUC improvement, PR AUC regression,
ECE improvement, top-1 regression, top-3 improvement, state-pooled LL
improvement, worst-race LL improvement (0.2000 vs 0.2133).

## Stage behavior

Frozen EARLY/MID/LATE partition: EARLY -0.000198, MID -0.001278,
LATE -0.000850 — all three negative vs Logistic (direction only; no
significance claimed).

## Probability quality

RAW, finite, bounded in [0,1], not field-normalized, no calibration.
Intact: Brier and ECE both improve vs Logistic; worst-race LL improves.

## Diversity transfer

The ensemble wins exactly the 11 races where XGB beats Logistic, with zero
pull-away races — using the frozen single recipe only. No alternative weight
was derived from this analysis.

## Final disposition

ENSEMBLE_MIXED_OUT_OF_TIME. Development-to-2025 reads as
ATTENUATED_OUT_OF_TIME_EFFECT (same improvement direction, smaller 2025
magnitude, probability quality intact, stage consistency transferred,
race-level evidence uncertain). Reinterpretation as confirmed superiority is
forbidden.

## Standalone champion

V3.1B Logistic remains the standalone champion.

## Serving decision

SERVING_PROMOTION = NONE. The serving boundary
(`raceintel/model_lab/serving.py`) loads only the frozen sklearn
LogisticRegression artifact; no ensemble code is reachable from the
API/frontend/simulation paths.

## No-reselection audit

NO-RESELECTION CONFIRMED. The only 2025 ensemble artifact in outputs is the
frozen w=0.2 prediction file; no w0.1/w0.3/w0.4/stacker/calibrated-alternative
ensemble exists anywhere in V3.4 E outputs or data.

## Validation

- Focused V3.4 A–E tests: 124 passed.
- V3.3 final integrity + holdout tests: 27 passed.
- Full Tier-1 (`pytest tests/`): 0 failures (see freeze record).
- Graphify: 15539 nodes / 35929 edges / 429 communities; no path from the
  V3.4 research module to API/frontend; no serving coupling.

## Artifact inventory

Tracked for freeze: `raceintel/model_lab/v3_4_ensemble.py`, 8 V3.4 scripts,
5 V3.4 tests, 6 V3.4 docs (incl. this report), compact V3.4 results
(A/B/C/D/E/F), final scientific card, freeze record. Kept ignored:
`data/v3/v3_4b/*.parquet` (36 files) and the 2025 ensemble prediction
parquet. No databases, model binaries, credentials, or large redundant data
in the staged payload.

## Known limitations

- Revealed-set evaluation, not pristine holdout.
- 24-race 2025 sample; race-level CI spans zero.
- 68-race development history; race-level sample still limited.
- Single fixed transformation; no reselection by design.
- Two-model linear opinion pool cannot capture interactions.
- **V3.4 did NOT prove ensemble superiority.**

## Freeze

- Card: `results/v3/v3_4_final_scientific_card.json` (`36e5df11…167fc576`).
- Freeze record: `results/v3/v3_4_freeze.json`.
- Commit: single commit on top of `563fff2`; tag `v3.4-ensemble`; NOT_PUSHED.

## Next stage

V3.5+ may use the frozen w=0.2 blend as a research input (e.g. model /
simulation consensus work). No serving promotion, no refit, no recalibration
of the V3.4 recipe is authorized by this freeze.
