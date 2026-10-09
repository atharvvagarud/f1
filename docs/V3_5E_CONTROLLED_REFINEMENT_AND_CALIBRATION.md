# V3.5E CONTROLLED REFINEMENT + TEMPORAL CALIBRATION

## Final verdict

V3.5E COMPLETE — FINALIST FROZEN — READY FOR V3.5F. Refined XGB recipe
(X2 + top5-SIGMOID + PAVA) advances as KEEP_DIVERSITY_CANDIDATE; Logistic
remains control. Top1 weakness is explicit and blocks any performance claim.

## Frozen parent

commit 3cbd28470ffa211bd754d4262eb10d66d149bf00, tag v3.4-ensemble. HEAD
verified equal; tree holds V3.5A+B+C+D+E only; nothing staged/committed/
tagged/pushed.

## Provenance

- A contract 15ca7c17146062edb5196a5de244fadd81d38562b2ca5714e58a21d4efb5efab
- B dataset e9ac34e5792a5aabba9038094a231a4a94789b481178739e46ece72457cc5289
- C harness 9dfee182215d6a56e4f19e2418b051883e9c75876418a6f4c92a05d799c7603a
- D protocol 8d82448ea5888beb6dd8f54c35ebb08ba40c58bd66b652bab6f0d39dfdf78ba4
- Feature e054c6fb08c0832970165bcfc0e84f54b70787491af1d545b96a13977fc4c89e (110)
- Projection v3.5b-projection-v1. D advancing set exactly ["xgb"]; HGB closed.

## E preregistration

results/v3/v3_5e/refinement_protocol.json,
identity 4adf3da33b86e734e7b663c6702c64f9377c08ac4318fb5439eebd439aec38e6,
frozen before the first E fit; asserted by hash at runner start.

## Scientific question

Can the D XGB candidate be modestly refined, on development-history
evidence only, into a temporally robust outcome model without masking win
weakness or relying on coherence repair? Answer: modestly yes as a
diversity candidate; no as a performance candidate (top1 guard).

## Frozen control

Logistic C=0.01, L2, lbfgs, max_iter=1000, class_weight=None,
random_state=42; four independent binary models on the frozen 110.
Untouched throughout E.

## D anchor reproduction

Reloaded D XGB OOF + C control OOF; recomputed RAW/PROJECTED primaries,
threshold LLs — machine-precision agreement (<1e-12, all folds, both
models). Recorded in anchor_reproduction.json.

## Refinement candidates

Closed set of four (anchor included): X0 ANCHOR (lr .03/depth 3/mcw 10/
n300), X1 CAPACITY (n500), X2 REGULARIZED (mcw 15/n300), X3 SLOWER
(lr .02/n500). All other D parameters identical. No depth search, no new
families, no blending.

## Temporal selection

M6 expanding-window inner folds on outer-TRAIN history only; one shared
config across four thresholds; primary = mean inner race-macro LL;
tie-break X0, then 300-tree, then prereg order. Outer validation selects
nothing.

## Selected configurations

D1 -> X0 (inner 0.239724; X1 far worse at 0.252199), D2 -> X2 (0.224459
vs X0 0.225177), D3 -> X2 (0.217008 vs X0 0.217862). Stability:
NEAR_STABLE. Extra capacity (X1/X3, n500) hurt everywhere; mild extra
regularization (X2) helped on later folds. Final rule (majority vote) ->
X2.

## Raw results

Outer RAW primary: D1 0.210631 (= anchor, X0), D2 0.202105 (anchor
0.203232), D3 0.185013 (anchor 0.185460).

## Projected results

Outer PROJECTED primary: D1 0.210427, D2 0.201515, D3 0.183038.
Pooled refined-minus-Logistic: -0.005308, 95% CI [-0.010345, -0.000790],
37 improved / 31 worsened of 68 races.

## Comparison with D anchor

Pooled refined-minus-anchor: -0.001288, CI [-0.002283, -0.000319]
(excludes zero). Per fold: D1 tie (same config), D2 -0.001414, D3
-0.002354. Refinement never worsens any fold vs anchor (22 ties are D1).

## Threshold-specific results

12 direction cells vs Logistic: 8 improved / 4 worsened (same count as D,
different mix). Vs anchor: 4/4/4. D2 top3/top5 and D1/D3 top1 are the
regressing cells.

## Top1 weakness audit

EXPLICIT: top1 PROJECTED delta vs Logistic: D1 +0.003115, D2 -0.003604,
D3 +0.003134. Race majorities: D1 10/12, D2 13/9, D3 16/8 (D3 mean
regresses despite a race majority — a few bad races dominate). The D
weakness persists under refinement; it caps the disposition at diversity.

## Race-level evidence

Pooled 68 races: mean -0.005308, median -0.003894 vs Logistic; vs anchor
mean -0.001288, median -0.000253. Per-fold race splits in
race_level_results.json.

## Bootstrap

Race unit, B=2000, seed=42, 95% CI, PROJECTED primary, both estimands
(refined-Logistic, refined-anchor), per fold + pooled. Both pooled CIs
exclude zero.

## Stage analysis

Frozen EARLY/MID/LATE, descriptive. LATE strength preserved and broadened
(11/12 LATE cells improve, all strongly negative on D2/D3); EARLY/MID
mixed. No stage-based tuning.

## Probability quality

Mean Brier/ECE over four thresholds: refined beats control on D1 and D3;
on D2 Brier is marginally worse (0.06092 vs 0.06079) while ECE improves.
No primary regression is rescued by ECE anywhere (primary stands alone).

## Coherence behavior

RAW violation rates ~13% (anchor-like; control ~6-8%) with tiny mean
adjustments (~3-7e-4) and max ~0.09-0.20. Refined requires no materially
larger projection repair than the anchor. Projection unchanged.

## Calibration protocol

Candidates exactly RAW/SIGMOID/ISOTONIC, per threshold, history-only:
fit on earlier inner-OOS, select on later inner-OOS, refit pooled,
apply once. D1 single-inner-fold -> CALIBRATION_NOT_EVALUABLE -> RAW.
Order RAW -> calibration -> PAVA frozen.

## Calibration support

Per-threshold gates (>=1000 states, >=10 races, >=20 pos/neg) pass on all
evaluable folds (top1 positives ~1000+). Recorded in
calibration_support.json.

## Calibration selection

History-eval admission (LL > 1e-4, Brier <= 1e-12, pathology clean):
top5-SIGMOID admitted on D2 (dll -0.000487) and D3 (dll -0.000715);
D3 top1/top10 SIGMOID admitted on history but inconsistent across folds.
ISOTONIC never admitted (history LL always worse).

## Calibration results

Outer: D2 top5 0.239667 -> 0.238951; D3 top5 0.189830 -> 0.183751,
top10 0.294192 -> 0.292629, top1 cal-before-PAVA slightly worsened
(0.083288 -> 0.083850) with final projected still improved via PAVA
interaction. Outer never reversed any admission decision.

## Calibration stability

MIXED (D1 all-RAW unevaluable; D2 1/4 non-RAW; D3 3/4 non-RAW).
Per the preregistered final rule (same non-RAW method on every evaluable
fold), only top5-SIGMOID survives into the final recipe; all other
thresholds RAW.

## Final candidate decision

At most one nonlinear recipe: X2 + top5-SIGMOID + PAVA ->
KEEP_DIVERSITY_CANDIDATE. KEEP_PERFORMANCE is forbidden by the top1
guard (D1/D3 mean regression). No ensemble. HGB never reconsidered.

## Final-fit recipe

results/v3/v3_5e/final_fit_recipe.json,
identity b1d8ce5e43059477a5e57fe5b4d301cbd7b9975864d1ad964d613d1124044c09.
X2 full params, 110 features, TRAIN-only preprocessing, seasons
2018-2024, top5-SIGMOID refit protocol on D3-inner OOS history,
PAVA order, seed/threading/library versions, prediction schema, 2025
metrics + no-reselection disposition policy. Immutable.

## V3.5F execution contract

results/v3/v3_5e/v3_5f_execution_manifest.json,
identity eab0da304dbb46b6de58ccb00c676e6a64761cf6473cc1361659ff8658b3d8e1.
F fits the frozen recipe once, predicts once, reports frozen metrics;
no discretionary tuning.

## 2025 firewall

2025_CONTACT=NONE throughout E. Seasons touched: outer validations only
(2022/2023/2024) plus 2018-2024 training history. No 2025 targets,
predictions, prevalence, metrics, calibration, or selection. Firewall
audit + ProtectedHoldoutError tripwires pass.

## Independent recomputation

Second minimal numpy-only path from persisted E OOF reproduces primary,
threshold LLs, top1, Brier, ECE (1e-9) and both pooled bootstraps
exactly. all_match=true.

## Compute

96 inner + 12 outer binary fits (as budgeted), calibration transforms
only; runner 234.3 s; no search expansion.

## Tests

tests/test_v3_5e_refinement.py (protocol freeze, identities, closed set,
history-only selection, calibration gates/order, top1 audit, bootstrap,
firewall, recomputation, no-blend, recipe/manifest immutability).
Focused E + D/C/B/A + calibration suites pass; full Tier-1 not required
(refinement only).

## Known limitations

Top1 D1/D3 regression persists; D2 Brier marginally worse than control;
calibration MIXED (top5-only in recipe); D1 shows no refinement signal;
pooled CI is wide despite excluding zero.

## V3.5F recommendation

Evaluate the frozen X2 recipe once on the PREVIOUSLY REVEALED OUT-OF-TIME
OUTCOME EVALUATION per the manifest. Poor F keeps Logistic champion
(no-reselection). Do not start F in this task.
