# V3.3C FULL TEMPORAL CANDIDATE SCREENING

## Final verdict

V3.3C COMPLETE — CANDIDATE SCREENING COMPLETE — READY FOR V3.3D.
(No primary challenger beats the baseline; two diversity candidates
advance. This is pre-2025 evidence only — not a production promotion.)

## Frozen parent

- tag `v3.2-monte-carlo-2`, commit
  `197979d40af0c9dbf90667781d9c83e41613b047` (HEAD verified equal).

## Contract identities

- A: `v3.3a-experiment-contract-v1`,
  `d877e8b2f7821d2eb7ade05677a3a7920f538a0422d28c97956f43f4cce399d7`
- B prereg: `da60e8d9824cd284c830b0bb9b580db2f7a713f06e8c2fa61e459795b8b712d8`
  (full SHA recovered and verified before any experiment)
- C prereg: `v3.3c-preregistration-v1`,
  `a8a3d8be330013c38da2ba063ba47785467b0f96d67c004555f6fee9a4eb29a8`,
  frozen before the first fit; grids verified immutable at execution.

## C preregistration

`results/v3/v3_3c/preregistration.json` pins families, exact
grids/config IDs (4/8/8/8), feature/task/fold identities, metrics,
bootstrap (race unit, B=2000, seed 42), temporal/stage/calibration/
diversity definitions, disposition enum, advancement cap (<=3), seed 42,
threads, artifact layout, firewall, test policy.

## 2025 firewall

Pre-execution: resolver + direct/indirect harness paths all
`BLOCKED:ProtectedHoldoutError`, `2025_CONTACT = NONE`. Post-analysis:
OOF seasons are exactly {2022, 2023, 2024}; `2025_CONTACT = NONE`
re-verified. No 2025 fit/prediction/metric/artifact anywhere.

## Baseline OOF

Canonical V3.1B-aligned OOF for D1/D2/D3 (23577/24422/26606 rows),
independently verified three ways: row set equals harness
materialization, logistic refit bit-identical (diff 0.0), parquet LL
equals frozen V3.1C JSON to 1e-12. Pooled race-macro LL 0.067107
(D1 0.080675 / D2 0.039436 / D3 0.080036). Immutable C reference.

## Screening execution

`scripts/run_v3_3c_screening.py`: 4 families x 3 folds = 12 selected
outer models (180 inner + 12 outer estimator fits, checkpointed).
No candidate-specific shortcuts; grids unchanged after execution began.

## Inner tuning

All configs evaluated on inner folds only; <=1e-6 simpler-wins tie rule;
no silent failures (failures: none). Full per-config/inner-fold LLs in
`inner_tuning_results.json` + per-fold `tune_*.json` checkpoints.

## Selected configurations

- logistic_regression: C=0.003 / C=0.003 / C=0.01 (procedure estimate;
  control, not a challenger)
- hist_gradient_boosting: lr=0.05;leaves=15;min_leaf=20 on all folds
  (stable)
- extra_trees: sqrt/1/None, sqrt/5/20, sqrt/5/None (minor variation)
- xgboost: lr=0.05;d3;mcw5 on all folds (stable)

## Primary results

Pooled race-macro LL: baseline 0.067107; logistic 0.067842 (+0.0007);
HGB 0.089385 (+0.0223); ET 0.074985 (+0.0079); XGB 0.074437 (+0.0073).
Per-fold: D2 is the easy fold (~0.04); D1/D3 ~0.08-0.12. No challenger
beats baseline on any fold (closest: XGB D2 +0.0017).

## Secondary results

Brier/ROC/PR worse than baseline for every challenger on nearly every
fold, with two exceptions: ET D2 ROC 0.9972 (> 0.9956) and PR 0.9546
(> 0.9265). ECE: baseline 0.0084 pooled; XGB 0.0121 (smallest gap),
HGB 0.0176, ET 0.0171 (largest gap).

## Race-level paired comparisons

Mean deltas (candidate - baseline): LogReg +0.0007; HGB +0.0223;
ET +0.0079; XGB +0.0073. Improved/worsened races: 15/29, 29/39,
18/50, 33/35.

## Bootstrap intervals

95% paired race CI: LogReg [-0.0002, +0.0015] (tie); HGB [+0.0107,
+0.0347] (clearly worse); ET [+0.0008, +0.0150] (worse); XGB [-0.0007,
+0.0159] (spans zero — statistical tie).

## Temporal consistency

HGB/ET/XGB: CONSISTENT_REGRESSION (worse on D1, D2, D3). Logistic
control: MIXED (D3 delta exactly 0.0 — selected C=0.01 there).
Magnitudes: D2 gaps are small for all families (+0.0017 to +0.0041);
D1/D3 gaps dominate.

## Stage analysis

Baseline: EARLY 0.0881 / MID 0.0633 / LATE 0.0496. All challengers
regress in ALL stages (no phase-specific advantage found): HGB worst
(+0.018 to +0.025); ET +0.006 to +0.009; XGB +0.004 to +0.010 with the
smallest LATE gap (+0.0043).

## Calibration diagnostics

RAW primary; nothing fitted in C. Pooled ECE above; HGB shows
heavy-tail blowups (worst race +0.166, 91% extreme-probability states);
ET worst mean ECE gap (+0.0098); XGB smallest (+0.0043). Reliability
bins in per-fold outer payloads.

## Top-k behavior

Driver-level top-1 disagreements vs baseline (68 races): ET 13 (won
9-3), HGB 15 (lost 3-7), XGB 20 (lost 6-10), LogReg 7 (tied 1-0 with
D3-identical model). Diagnostic only — not used for selection.

## Diversity / complementarity

Pairwise prediction correlations 0.885-0.941 with baseline; residual
correlations 0.867 (HGB) / 0.892 (XGB) / 0.919 (ET); per-race LL
correlations lowest for XGB (0.857 — most distinct race pattern);
high-confidence disagreement states 906-1461. ET owns the only
net-positive disagreement record (9-3) plus the largest single-race
gain (-0.074); XGB owns the most balanced race record (33 improved)
at a tied overall level. Full matrix in `diversity_matrix.json`.

## Compute profile

Tuning+outer wall: LogReg 42 s, HGB 239 s, XGB 154 s, ET 1267 s
(51 fits each for trees; ET D3 dominates). OOF ~0.9-1.3 MB/family.
No budget pressure for D (calibration is cheap relative to this).

## Configuration stability

HGB/XGB stable (same config all folds); LogReg near-stable (C=0.003,
0.003, 0.01); ET minor variation (min_samples_leaf 1 vs 5, depth
None vs 20). No retuning performed on this observation.

## Candidate summaries

`candidate_summaries.json`: per-family configs, primary/secondary,
deltas, CIs, temporal, stages, calibration, top-k, diversity, cost,
stability, limitations.

## Preliminary dispositions

- logistic_regression: BASELINE_CONTROL (never a challenger).
- hist_gradient_boosting: REJECT_NO_IMPROVEMENT — zero advantage in
  all 24 fold/stage/secondary cells, CI entirely above zero,
  disagreements lost 3-7, discrimination also worse so the M4
  calibration-remedy path is inapplicable.
- extra_trees: KEEP_DIVERSITY_CANDIDATE — disagreement wins 9-3, D2
  ROC/PR edges, largest single-race gain; limitation: worst ECE gap,
  thin (13-race) disagreement sample.
- xgboost: KEEP_DIVERSITY_CANDIDATE — statistical tie with baseline,
  most-distinct race pattern (0.857), 33 improved races, smallest ECE
  gap; limitation: no outright winning dimension, lost disagreements
  6-10.

## V3.3D advancement

`["extra_trees", "xgboost"]` (2 <= 3): credible diversity value only;
no primary winner; HGB rejected. Fewer-than-max is the honest result.

## Known limitations

Pre-2025 only; small preregistered grids; RAW probabilities; ET
diversity evidence thin; single 2025 holdout still sealed; analysis
scripts were iterated for correctness (dead-code removal, state-vs-
driver top-k fix, rule ordering) without touching experiments or grids.

## Tests

C screening 17 + A 14 + B 20 = 51 passed; M0/M1/M1.1 guards green
(stage-allowlist entries per V3.1C precedent); M6, dynamics governance
sampled green. FULL_TIER1 = NOT_REQUIRED_RESEARCH_EXECUTION_ONLY.

## Reproducibility

Freeze, execute, analyze, test — four commands in
`reproducibility.json`; compact artifacts rebuildable from stored OOF
via `analyze_v3_3c.py` alone.
