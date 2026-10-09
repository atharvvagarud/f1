# V3.4B DEVELOPMENT ENSEMBLE EXPERIMENTS

## Final verdict

Development ensemble evidence ready. Broad blend region (w=0.1–0.7)
improves pooled race-macro LL over Logistic; descriptive best w=0.4
(−0.001903). Stacker strong on D2 (−0.0088, CI excludes zero), flat on
D3 (+0.0009, CI spans zero). All leaders marked
DESCRIPTIVE_ONLY_NOT_SELECTED. No recipe selected. Ready for V3.4C.

## Frozen parent

`v3.3-multi-model-lab` / `563fff21f94f169097079b003816181c31227aa9`;
V3.4A work present uncommitted at entry; nothing staged.

## Contract identities

A `d6b12074db9895844c28c05c78baf56c113d63c33d685c5913c92ebb5036b352`
(recomputed, matched). B prereg
`64ca2d2911e63b1487334ca72fc024f47d59868f168b60d7d391d31df82b5b26`
frozen before any output; runtime config asserted equal at execution.

## B preregistration

Pinned A identity, base prediction identities + V3.3 prob hashes/LLs,
aligned row identity (74,605/68), exact 11-point grid, stacker spec
(C=1.0/logit-clip/expanding window), metrics, bootstrap, stages,
firewall, artifact paths, seed 42, budget 1800 s, selection NONE IN B.

## Development alignment

74,605 rows (23,577/24,422/26,606), 68 races, state_id joins, zero
mismatches; V3.3 prob hashes reproduced exactly for both streams; finite
bounded probabilities; seasons 2022–2024 only.

## Baseline reproduction

Logistic pooled 0.0671072660 and XGB refined pooled 0.0706461281 plus all
six per-fold LLs reproduced vs V3.3 artifacts within 1e-9. Gate passed.

## Convex blend experiment

All 11 frozen weights evaluated per fold + pooled from identity-joined
frames; w=0/w=1 bitwise identities verified; no normalization/clipping
needed; 33 blend + 3 stacker prediction parquets persisted ignored under
`data/v3/v3_4b/` with SHA256 (`prediction_hashes.json`).

## Weight landscape

| w | pooled Δ | D1 Δ | D2 Δ | D3 Δ | imp/wor |
|---|---|---|---|---|---|
| 0.1 | −0.000951 | −0.000787 | −0.001251 | −0.000826 | 42/26 |
| 0.2 | −0.001489 | −0.001114 | −0.001938 | −0.001420 | 41/27 |
| 0.3 | −0.001798 | −0.001084 | −0.002492 | −0.001817 | 40/28 |
| 0.4 | −0.001903 | −0.000718 | −0.002951 | −0.002029 | 40/28 |
| 0.5 | −0.001804 | −0.000002 | −0.003332 | −0.002055 | 40/28 |
| 0.6 | −0.001486 | +0.001104 | −0.003642 | −0.001885 | 39/29 |
| 0.7 | −0.000915 | +0.002684 | −0.003886 | −0.001491 | 39/29 |

w=0.8+ degrades toward pure XGB (+0.003539). Full table with CIs in
`weight_landscape.json`. DESCRIPTIVE_ONLY_NOT_SELECTED throughout.

## Race-level bootstrap

Race unit, B=2000, seed 42, 95% CI per weight per fold + pooled
(`blend_race_bootstrap.json`). Small-w CIs sit at/below zero pooled;
large-w CIs span zero widely.

## Stage analysis

w=0.2 and w=0.4 negative in all 9 fold×stage cells (EARLY/MID/LATE via
frozen `race_progress_frac` partition; no new definitions).

## Robustness structure

Broad useful region, smooth neighbors, no isolated spike; D1 turns
positive beyond w≈0.5 while D2 improves monotonically — fold tension for
C to weigh. No adaptive grid, no interpolation candidates.

## Temporal stacker

Frozen spec executed: D1 NOT_EVALUABLE (baseline fallback, explicit);
D2 trained on D1 (22 races/23,577 rows); D3 trained on D1+D2 (44
races/47,999 rows). No target-fold labels in any fit.

## Stacker coefficients

D2: β0=0.726, β_log=0.837, β_xgb=0.381. D3: β0=0.856, β_log=0.824,
β_xgb=0.549. Positive use of XGB alongside dominant Logistic; no
pathology, no collapse, no suppression (descriptive, model unaltered).

## Stacker results

D2 LL 0.030650 (Δ −0.008786, CI [−0.011885, −0.005929]); D3 LL 0.080897
(Δ +0.000862, CI [−0.010467, +0.014478]). Fold instability is material
evidence for C.

## Probability quality

All candidates finite, bounded [0,1], RAW, not field-normalized. No
tail pathology observed (`probability_quality.json`).

## Diversity utilization

All 38 pure-XGB race wins retained at w=0.2 and w=0.4; small weight
avoids most XGB losses. Disagreement–gain correlation −0.044: gains are
not a disagreement-magnitude artifact.

## 2025 firewall

2025_CONTACT=NONE. Six-path OOF allowlist loader; seasons seen
2022–2024; no 2025 ensemble artifact generated. Fail-closed tests added.

## Compute profile

627.9 s total vs 1800 s budget. No base models retrained.

## Tests

`tests/test_v3_4b_development.py` (A hash, B immutability, grid exactness,
w=0/w=1 identities, identity joins, permutation invariance, bounds, no
normalization, D1 fallback, D2/D3 temporal safety, no leakage, fixed C,
race-macro primary, race-unit B=2000/seed42, stages, prediction hashes,
2025 prohibitions, no recipe) plus A/V3.3/M6 suites. No Tier-1
(NOT_REQUIRED_RESEARCH_EXECUTION_ONLY).

## Known limitations

Descriptive only; D1 learned-params gap; stacker fold instability;
68-race sample; single fixed stacker C by design.

## V3.4C recommendation

Apply advancement + robustness rules to the broad blend region vs the
unstable stacker; neighbor-gate any candidate; freeze exactly one recipe
or NO_ENSEMBLE. Reproducibility: `freeze_v3_4b_prereg.py` (refuses if
output exists), `run_v3_4b_experiments.py` (asserts prereg first),
focused tests. No 2025 command exists by design.
