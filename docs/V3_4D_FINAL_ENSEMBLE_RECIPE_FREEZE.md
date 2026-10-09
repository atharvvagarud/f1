# V3.4D FINAL ENSEMBLE RECIPE FREEZE

## Final verdict

Final ensemble recipe frozen: FIXED_CONVEX_BLEND w=0.2
(p = 0.8·p_logistic + 0.2·p_xgb), identity
`d715dcfb…39af68`. Bit-exact development parity with B. E manifest
frozen (`9a6752b6…00d368a1`). No 2025 contents touched. Ready for V3.4E.

## Frozen parent

`v3.3-multi-model-lab` / `563fff21f94f169097079b003816181c31227aa9`;
entry tree V3.4A+B+C only, nothing staged.

## Provenance chain

V3.3 parent → A `d6b12074…` → B `64ca2d29…` → B evidence →
C protocol `d0af402c…` → C candidate `98b31597…` → D recipe
`d715dcfb…`. Every child references exact parent identities
(`provenance_chain.json`, full SHA256, no abbreviations).

## Selected development candidate

C ENSEMBLE_SELECTED, fixed convex blend w=0.2 (`98b31597…`, verified).
No mutation B→C→D: weight, method, bases, semantics all preserved.

## Base model identities

V3.1B Logistic (C=0.01, RAW, 110-col, 2018–2024) and V3.3 XGB finalist
(lr=0.03/d3/mcw5, RAW, 110-col, recipe `ca0cd5d5…`) resolved from frozen
artifacts. Neither retrained; no new binaries.

## Final ensemble recipe

`final_ensemble_recipe.json` (schema v3.4-final-ensemble-recipe-v1):
0.8/0.2 weights summing exactly to 1, RAW INDEPENDENT_BINARY, no
calibration, no normalization, identity alignment mandatory, seed policy,
full lineage, `created_before_2025_ensemble_evaluation=true`. Immutable
(one-shot writer refuses overwrite).

## Transformation semantics

Closed-form float64 blend; finite/bounded inputs required; outputs
bounded [0,1]; deterministic order; no post-processing. Probability
blend, not epistemic confidence.

## Alignment contract

state_id identity join; positional use forbidden (V3.3 incident);
duplicates/missing/extra/mismatches fail closed. Implemented in
`raceintel/model_lab/v3_4_ensemble.py`, shared by D and E.

## Development parity

Recipe module executed on B w=0.2 dev inputs: BIT-EXACT
(maxabsdiff 0.0, all folds; LL parity exact). Verification, not
selection.

## Recipe immutability

Module verifies recipe SHA + A/B/C identities on every load; freeze
script refuses regeneration; tests pin the hash.

## V3.4E execution manifest

`v3_4e_execution_manifest.json` (`9a6752b6…`): exact recipe, base 2025
sources (paths + XGB sha from V3.3 metadata; contents never opened in
D), metrics/bootstrap/stage policies, output paths, revealed
terminology, no-refit/reselection/calibration/weight-change/rescue
rules. E needs zero scientific discretion.

## 2025 disclosure

V3.4E will be a PREVIOUSLY REVEALED OUT-OF-TIME ENSEMBLE EVALUATION —
never untouched/pristine/one-shot-unseen. Base-model 2025 was known
pre-V3.4; the w=0.2 transformation was selected without 2025 ensemble
evaluation. Both facts documented.

## Evaluation claim boundary

Development selection temporally isolated from 2025, but E is
corroborative evidence for the frozen transformation, not a pristine
discovery-to-confirmation experiment. Conservative language frozen.

## No-reselection guarantee

Poor E result changes nothing: no other weight, no C revisit, no tuning,
no calibration, no stacker. Accept the evidence; Logistic remains
champion if the ensemble fails to generalize.

## E metrics

Primary race-macro LL (ensemble − Logistic) + XGB reference, Brier,
ROC/PR, ECE, top-1/top-3, pooled LL, stages; paired race bootstrap
B=2000/seed42/95%. No post-hoc success metrics.

## E disposition policy

ENSEMBLE_GENERALIZES / ENSEMBLE_MIXED_OUT_OF_TIME /
ENSEMBLE_FAILS_TO_GENERALIZE from frozen primary/bootstrap/directions/
quality/stages/consistency. Secondaries can't rescue poor LL alone.

## Explainability

80% Logistic probability + 20% XGB probability. Not confidence weights.

## Artifact inventory

`artifact_inventory.json`: A/B/C/D tracked compacts, 36 ignored B
parquets, future E outputs. Nothing staged.

## Tests

`tests/test_v3_4d_recipe.py` (33 checks: identities, weights 0.8/0.2,
semantics, alignment, parity, immutability, manifest rules, terminology,
firewall) + A/B/C/V3.3 suites. No Tier-1
(NOT_REQUIRED_RECIPE_FREEZE_ONLY; full Tier-1 at V3.4 final freeze).

## Known limitations

Development-only evidence at freeze; 68-race sample; corroborative (not
pristine) E ahead.

## V3.4E recommendation

Execute the manifest with the recipe module; report revealed
terminology; apply E disposition policy. Rebuild: `freeze_v3_4d_recipe.py`
(one-shot), module parity snippet, focused tests. No 2025 command runs
in D.
