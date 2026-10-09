# V3.4A ENSEMBLE LANDSCAPE + EXPERIMENT CONTRACT

## Final verdict

Contract frozen (`d6b12074…b352`). Two methods admitted (11-point fixed
convex blend; two-input logistic stacker with fixed C=1.0). Ensemble
output stays RAW INDEPENDENT_BINARY. 2025 is a PREVIOUSLY REVEALED
OUT-OF-TIME EVALUATION SET under a fail-closed firewall. Null result
(NO_ENSEMBLE) is an acceptable, predeclared outcome. Ready for V3.4B.

## Frozen parent

- Tag: `v3.3-multi-model-lab`, commit `563fff21f94f169097079b003816181c31227aa9`
- V3.3 freeze record `a0517807…`, scientific card `1bc365ef…` verified.
- V3.3 conclusions: V3.1B STANDALONE CHAMPION; HGB/ET REJECT_NO_IMPROVEMENT;
  XGB KEEP_DIVERSITY_CANDIDATE (V3.4-eligible, does not replace V3.1B).

## V3.3 evidence

Development: Logistic OOF LL ~0.067107; refined XGB ~0.070646
(delta ~+0.0035, bootstrap spans zero; D2 fold win; 38 improved races).
2025 (revealed in V3.3): Logistic 0.0634166678 vs XGB 0.0672136469
(delta +0.0037969791, CI [-0.003725, +0.011783], 11/24 XGB-improved).
XGB edges on ECE/top-1 only. Base recipes/retraining frozen; V3.4 fits no
base models. Evidence inventory: card, freeze record, finalist recipes
(`ca0cd5d5…`), all C/D OOF parquets + 2025 prediction parquets present.

## Scientific question

Does XGBoost contain complementary predictive information that can be
combined with frozen V3.1B Logistic to improve winner probability quality
over Logistic alone? Burden of proof on the ensemble; null acceptable.

## Base models

Frozen Logistic (C=0.01, RAW, 110 cols, 2018–2024) and frozen XGB
(lr=0.03/depth 3/min_child_weight 5/300 trees/seed 42, RAW, 110 cols).
HGB/ET excluded (V3.3 rejections stand; reopening forbidden). No
retraining or retuning in V3.4.

## Prediction compatibility

Development streams `oof_baseline__D{1,2,3}` + `oof_d_refined_xgboost__D{1,2,3}`:
74,605 rows / 68 races identity-joined on state_id with zero mismatch
(same target/race/driver/fold/stage/arm/semantics). Row-position joins
forbidden (V3.3 incident invariant).

## Ensemble semantics

Single independent binary winner probability per driver-state;
INDEPENDENT_BINARY, never field-normalized, not an MC2 distribution.

## Candidate methods

1. FIXED CONVEX BLEND: p = (1−w)·p_log + w·p_xgb, w ∈ [0,1].
2. LOGISTIC STACKER: logit(P) = β0 + β1·logit_clip(p_log) +
   β2·logit_clip(p_xgb), L2 C=1.0 fixed, lbfgs, seed 42, RAW output.
Calibrated blend excluded (no distinct justification).

## Excluded methods

Large/neural/boosted meta-models, subgroup-specific or per-race weights,
2025-informed or manual post-hoc weights, MC2 fusion (V3.8 owns it).

## Blend grid

Frozen: 0.0, 0.1, …, 1.0 (11 points; 0.0 = pure Logistic, 1.0 = pure XGB).
Adaptive refinement forbidden.

## Stacker design

Two logit-clipped inputs (clip [1e-6, 1−1e-6]; extreme-mass ~0.8
justifies logit scale), fixed C=1.0 (no search → no selection-leakage
surface), trained on earlier-fold OOF history only. Not fitted in A.

## Temporal protocol

Whole fixed grid evaluated on D1/D2/D3 (pure evaluation, temporally safe);
ONE recipe selected after all folds in V3.4C. Outer validation selects
nothing. Learned stacker: D2←D1 history, D3←D1+D2, D1 NOT_EVALUABLE
(baseline-only fallback).

## Primary metric

Race-macro winner log loss vs frozen V3.1B Logistic. Lower better.

## Secondary metrics

Brier, ROC/PR AUC, ECE, top-1/top-3, state-pooled LL + EARLY/MID/LATE.
Never select on ROC/accuracy/top-1 alone.

## Race-level statistics

Race is the unit. Per-race LL delta, paired bootstrap B=2000 seed 42 95%
CI; report mean/median delta, improved/worsened/ties. States never units.

## Calibration policy

Option A: ensemble output stays RAW. No temporal calibration admitted, no
2025 calibration, no rescue calibration.

## Weight robustness

Winning w checked at ±0.1 neighbors; isolated spike = weak evidence;
broad region = strong. No second finer grid.

## Advancement rules

KEEP_ENSEMBLE_PRIMARY / KEEP_ENSEMBLE_TIE_BREAK / REJECT_NO_IMPROVEMENT /
REJECT_TEMPORAL_INSTABILITY / REJECT_PROBABILITY_QUALITY /
REJECT_COMPLEXITY_WITHOUT_VALUE. No invented minimum effect size.

## 2025 disclosure

2025 is PREVIOUSLY REVEALED (base-model results observed in V3.3), NOT an
untouched holdout. Historical numbers documented statically only.

## 2025 firewall

Selection code must not load 2025 labels/predictions/metrics/outcomes;
forbidden paths `data/v3/v3_1d/*2025*`, `data/v3/v3_3e/*`; dev-only
resolver + season assertions + ProtectedHoldoutError + artifact scan +
tests. Final evaluation of the frozen recipe only, reported as revealed.

## Final recipe policy

Exactly one of NO_ENSEMBLE | one fully-specified recipe, frozen before
any 2025 ensemble evaluation. 2025 cannot change it.

## Null-result path

No credible pre-2025 gain → NO_ENSEMBLE, V3.1B stays champion, no 2025
fishing, no forced V3.4E, proceed to V3.5.

## Stage plan

A contract (here) → B development experiments → C selection+robustness →
D recipe freeze → E revealed-2025 evaluation only if an ensemble survives
→ F validation+freeze. Each stage has stop boundaries (see contract).

## Compute budget

≤30 min total for B/C (expect minutes); blends seconds; stacker cheap.
Base-model retraining = design error unless justified.

## Dependency policy

numpy/pandas/sklearn only. No Optuna/LightGBM/CatBoost/SHAP/deep learning.

## Explainability

Blend weight is explicit; stacker coefficients + input probabilities
suffice. No SHAP. No frontend in V3.4A.

## Known limitations

Revealed-2025 caveat; 68-race development sample; D1 learned-params gap;
linear pool can't capture interactions; fixed stacker C by design; no
serving changes.

## V3.4B recommendation

Execute the frozen grid + expanding-window stacker on aligned OOF under
the firewall; run contract tests; FULL_TIER1 = NOT_REQUIRED_CONTRACT_ONLY.
Reproducibility: `scripts/freeze_v3_4a_contract.py` (hash must match),
`pytest tests/test_v3_4a_contract.py`, V3.3 freeze verification commands.
