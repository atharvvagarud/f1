# V3.3D CONTROLLED REFINEMENT + TEMPORAL CALIBRATION

## Final verdict

V3.3D COMPLETE — FINALISTS FROZEN — READY FOR V3.3E.
(One challenger finalist + baseline. ET answered negatively but
honestly; HGB stayed closed; 2025 untouched.)

## Frozen parent

- tag `v3.2-monte-carlo-2`, commit
  `197979d40af0c9dbf90667781d9c83e41613b047` (HEAD verified equal).

## Contract identities

- A `d877e8b2…`, B `da60e8d9…`, C `a8a3d8be…` — all verified exactly.
- C advancement verified as `["extra_trees", "xgboost"]`; HGB verified
  `REJECT_NO_IMPROVEMENT` and refused by gate + tests.
- D prereg `v3.3d-preregistration-v1`,
  `b74a9a7cb20b502bca2f05c2a071e9ed2f46312ac785194124b234d8ff94bca2`,
  frozen before any D fit; D grids verified against it at execution.

## D preregistration

`results/v3/v3_3d/preregistration.json`: ET+XGB set, exact 6+6 grids
with IDs/rationales/complexity, temporal calibration design, support
gates, >1e-4 + no-Brier-harm selection rule, metrics, advancement cap
(<=2), final-fit recipe policy, firewall, layout, test policy.

## Scientific questions

- Q1 (ET): does valid calibration + narrow refinement convert its
  disagreement/D2 evidence into a useful probability model?
  Answer: NO — refinement marginal (+0.0009 pooled), isotonic harmful
  out-of-time (see below).
- Q2 (XGB): does it convert near-tie + distinct errors into a credible
  candidate? Answer: YES, as diversity — refined pooled gap halved
  (+0.0073 -> +0.0035), CI spans zero, D2 outright win, 38 improved
  races, near-zero ECE gap.

## C references

C RAW configs, OOF identities, deltas preserved read-only in
`c_reference_identities.json`. D labels always distinguish C_RAW /
D_REFINED_RAW / D_CALIBRATED; no relabelling.

## Refinement grids

ET (sqrt frozen — 0.5 never competitive in C): msl {3,10} neighbors,
5/10 mid-depth, 3/10 interior. XGB (around stable 0.05/d3/mcw5):
lr 0.03, mcw {3,10}, depth 4, n=500 stability probe, 0.1/d2 corner.
6+6, all distinct from C, each with rationale + complexity rank,
hashed before execution, never edited.

## Temporal calibration design

Cross-fitted inner-val predictions inside outer TRAIN only; earlier
inner-val races fit sigmoid/isotonic, later races select; winners
refit on full calibration history; outer validation only measured.
Isotonic clips out-of-bounds; both methods monotone (no strict
inversions verified; tie-coarsening can shift grouped rank metrics
~1e-2, reported openly).

## Calibration support

Gates: isotonic >=10k rows/500 positives/50 unique; sigmoid
>=1k/50/10; else NOT_RUN_INSUFFICIENT_SUPPORT. All 6 fold-runs met
gates (no skips).

## Calibration selection

Train-history rule only: LL gain >1e-4 + no Brier harm; ties prefer
RAW > SIGMOID > ISOTONIC. Selected: ET isotonic on all folds; XGB RAW
on all folds (correctly — no spurious calibration).

## Nested refinement

Inner selection over D grids (mean inner race-macro LL + tie rule),
calibration recipe from selected config's history preds, outer refit,
single validation prediction, RAW + CALIBRATED OOF. Outer validation
influenced nothing. Fits: ET 39, XGB 39 (18 inner + 1 outer per fold
for ET D3 etc.; recorded per fold).

## Selected refinements

- ET: D1 sqrt/10/20, D2 sqrt/3/10, D3 sqrt/10/20 (all isotonic recipe).
- XGB: D1 mcw10, D2 lr0.03, D3 lr0.03 (all RAW recipe).

## OOF integrity

12 D frames (6 refined + 6 calibrated) aligned to baseline rows/
targets/folds/stages, bounds finite, hashes persisted. RAW==CALIBRATED
iff method RAW (asserted per fold).

## Primary results

Pooled LL — baseline 0.067107; ET C 0.074985 -> refined 0.074108 ->
calibrated 0.113177; XGB C 0.074437 -> refined 0.070646 (== calibrated).
XGB D-vs-C gain -0.0038 (CI entirely below zero); XGB D2 refined
0.0352 beats baseline D2 0.0394 — the only challenger fold-win in V3.3.

## Race-level comparisons

Deltas vs baseline: ET refined +0.0070 (CI above zero), ET calibrated
+0.0461; XGB refined +0.0035 (CI spans zero). D-vs-own-C: ET refined
-0.0009 (marginal), XGB refined -0.0038 (real).

## Bootstrap intervals

Race unit, B=2000, seed 42. ET refined [+0.0012,+0.0120] (still worse);
XGB refined [-0.0038,+0.0112] (tie); XGB D-vs-C [-0.0068,-0.0008]
(genuine refinement gain).

## Probability quality

ET calibrated: ECE improved (0.0111 vs 0.0179) but worst-race 1.68 —
calibration fixed the average while creating catastrophic tail
(confident wrongs on shifted D3). XGB refined: Brier 0.0201, ECE
0.0093 (gap +0.0009), worst-race 0.31. Calibration must fix quality
*without* sacrificing LL — it failed that joint test for ET.

## Discrimination

Monotone methods preserve ranking (verified, tie-coarsening noted).
XGB refined improves on C in all stages (EARLY -0.0048, MID -0.0039,
LATE -0.0029 vs C RAW). ET refined still regresses in all stages.

## Temporal consistency

XGB refined: MIXED (D2 win, D1/D3 regression) — improved on C in every
fold. ET refined: CONSISTENT_REGRESSION (marginally better than C
everywhere, still behind baseline).

## Stage analysis

No challenger owns a stage vs baseline (XGB LATE gap smallest,
+0.0013). XGB refined beats its own C RAW in all stages.

## Diversity re-evaluation

Best admissible representations only (ET isotonic excluded: harmful on
measurement set). ET refined vs baseline: disagreements lost 2-8 (C's
9-3 did NOT survive), resid 0.926, 14 improved races. XGB refined:
16 disagreements roughly even, resid 0.904, race-pattern corr 0.87
(most distinct), 38 improved races, stage gains vs C everywhere.
Diversity survives refinement for XGB only.

## Diversity value gate

"Different" is not enough: ET is merely worse and more redundant now
-> rejected. XGB kept on 38 improved races + tie-level primary +
distinct patterns + near-zero ECE gap.

## Compute profile

Wall ~206 s ET + ~84 s XGB + calibration seconds each; OOF ~2.3 MB
total. Trivial vs screening.

## Final dispositions

- extra_trees: REJECT_NO_IMPROVEMENT (refinement marginal,
  calibration harmful out-of-time, diversity case evaporated: 2-8
  disagreements, 14 improved races, redundant errors).
- xgboost: KEEP_DIVERSITY_CANDIDATE (tie-level primary, D2 win, 38
  improved races, distinct errors, ECE gap +0.0009).
- No HOLD_FOR_CALIBRATION remains (D resolved it: harmful for ET,
  unnecessary for XGB).

## Finalists

`["xgboost"]` + V3.1B baseline. Zero-would-have-been-valid; one earned.

## Frozen final-fit recipes

`finalist_recipes.json`, hash
`ca0cd5d5f7c95e5446ae66111eff85232441023ad7be15d04a8f35e05fea332d`:
XGB lr=0.03/d3/mcw5 (D3 largest-history selection; all fold selections
recorded), frozen preprocessing, 110 features, 2018-2024, seed 42,
n_jobs<=4, calibration RAW (unanimous across folds — no calibrator to
fit), INDEPENDENT_BINARY never normalized. Baseline recipe pinned
(LogReg C=0.01, RAW). NO CHANGES AFTER 2025 IS REVEALED.

## 2025 firewall

Before and after: `2025_CONTACT = NONE`. D OOF seasons 2022-2024 only;
no 2025 metric/prediction/label/result. Scanned artifacts clean.

## Tests

D 20 + A/B/C 51 + guards/M6 138 passed.
FULL_TIER1 = NOT_REQUIRED_RESEARCH_EXECUTION_ONLY (only test-guard
allowlists + research modules touched).

## Known limitations

Pre-2025 only; narrow grids, no second round; ET negative is evidence,
not failure; single finalist; isotonic fragility is a finding about
temporal transfer, not a bug; 2025 still sealed.

## Next recommendation

V3.3E one-shot 2025 holdout: V3.1B baseline + frozen XGB recipe, then
V3.3 finalization. Do NOT start E here.
