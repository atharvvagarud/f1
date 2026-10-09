# V3.4E PREVIOUSLY REVEALED 2025 OUT-OF-TIME ENSEMBLE EVALUATION

## Final verdict

ENSEMBLE_MIXED_OUT_OF_TIME. Frozen w=0.2 blend improves 2025
race-macro LL (0.0626596199 vs Logistic 0.0634166678, Δ −0.000757) with
better Brier/ECE/worst-race and all stages negative — but only 11/24
races improve and the race bootstrap CI spans zero ([−0.00260,
+0.00097]). Corroborative, not conclusive. No reselection. Serving
promotion NONE. Ready for V3.4F.

## Frozen parent

`v3.3-multi-model-lab` / `563fff21f94f169097079b003816181c31227aa9`;
entry tree A+B+C+D only, nothing staged.

## Provenance

A `d6b12074…` → B `64ca2d29…` → C protocol `d0af402c…` → C candidate
`98b31597…` → D recipe `d715dcfb…` → E manifest `9a6752b6…` → E record
`74a59a50…` → prediction `sha256 recorded in prediction_identity.json`.
All recomputed pre-execution.

## Evaluation disclosure

PREVIOUSLY REVEALED OUT-OF-TIME ENSEMBLE EVALUATION. Base-model 2025 was
known pre-V3.4; the w=0.2 transformation was frozen without 2025
ensemble evaluation. Never untouched/pristine/unseen/one-shot-selection.

## Frozen recipe

p = 0.8·p_logistic + 0.2·p_xgb, RAW INDEPENDENT_BINARY, no calibration,
no normalization (`d715dcfb…`), executed via the shared recipe module.

## Input identity

26,692 states / 24 races / season 2025 only; identical identity sets;
XGB sha matches frozen V3.3 (`71b9bb80…`); bounds finite. state_id joins
only.

## Base reproduction

Logistic 0.0634166678 and XGB 0.0672136469 reproduced within 1e-9 of
V3.3 before blending. Gate passed.

## Frozen ensemble prediction

Persisted BEFORE analysis to ignored
`data/v3/v3_4e/ensemble_predictions_2025.parquet` (identity frozen).
Deterministic recompute + permutation invariance verified.

## Primary result

Ensemble 0.0626596199; Δ vs Logistic −0.0007570479; Δ vs XGB −0.004554.
Lower is better; sign respected (negative = ensemble better).

## Race-level evidence

Mean −0.000757, median +0.000291, 11 improved / 13 worsened / 0 ties.
Gains concentrated; majority of races marginally worse.

## Bootstrap

Race unit, B=2000, seed 42: mean −0.000757, 95% CI [−0.00260, +0.00097].
Spans zero — support is directional, not conclusive.

## Secondary metrics

Ensemble vs Logistic: Brier 0.01832<0.01858, ECE 0.00899<0.00939,
worst-race 0.200<0.213, ROC 0.98602>0.98586, pooled LL better; PR
0.82117<0.82531, top-1 0.79201<0.79415, top-3 0.98579>0.98485. No
secondary rescues anything alone; none needed to — quality is intact.

## Stage analysis

EARLY −0.000198, MID −0.001278, LATE −0.000850 — all negative, Brier
better in all stages. Development stage consistency transferred.

## Probability quality

Finite, bounded, RAW, not normalized. Blending reduced tails
(worst-race, max-prob lower) with no damage. No calibration response
permitted (and none needed).

## Development-to-2025 consistency

Direction generalized (dev −0.001489 → 2025 −0.000757, attenuated as
honestly expected); ensemble stayed conservative; XGB contribution
helped out of time. Recipe unchanged.

## Diversity transfer

Ensemble wins exactly the 11 XGB-win races; zero XGB pull-away races.
The V3.3 complementarity mechanism transferred precisely.

## Final disposition

ENSEMBLE_MIXED_OUT_OF_TIME (frozen 3-category policy): primary negative
with intact quality/stages/diversity, but race majority and CI prevent a
generalizes claim. Not forced positive.

## Serving decision

SERVING_PROMOTION = NONE. No model, API, or serving change in E.

## No-reselection confirmation

Only `ensemble_predictions_2025.parquet` exists under `data/v3/v3_4e/`.
No w0.1/w0.3/w0.4/stacker/calibrated 2025 artifact. Confirmed.

## Tests

`tests/test_v3_4e_evaluation.py` (35 checks) + D/C/B/A + V3.3 holdout +
metric suites. No Tier-1 (NOT_REQUIRED_OUT_OF_TIME_EVALUATION_ONLY;
full Tier-1 at V3.4F).

## Known limitations

Revealed-set (not pristine) evaluation; 24-race sample with CI spanning
zero; single frozen transformation; median race slightly negative.

## V3.4F recommendation

Freeze V3.4 (research-only ensemble, mixed evidence, Logistic still
standalone champion for serving) with full Tier-1 gate.
