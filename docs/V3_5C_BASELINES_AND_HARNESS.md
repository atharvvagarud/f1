# V3.5C BASELINES + EVALUATION HARNESS

## Final verdict

V3.5C COMPLETE — baseline harness validated, ready for V3.5D. Four frozen
baselines evaluated on D1/D2/D3 with RAW and PROJECTED_COHERENT scoring,
paired race bootstrap validated, harness parity bit-exact, 2025 untouched.
The only learned model is the frozen L2-logistic control (C=0.01, no
tuning).

## Frozen parent

- Tag: `v3.4-ensemble`, commit `3cbd28470ffa211bd754d4262eb10d66d149bf00`
- C contract `9dfee182…799c7603a`, frozen BEFORE the first fit; the run
  script asserts its hash before fitting (immutability gate).

## Provenance

A `15ca7c17…` (task ordered_cumulative_finish_thresholds) → B dataset
`e9ac34e5…` (162,728 states / 2979 outcomes / 149 races) + feature arm
`e054c6fb…` (110) + projection v3.5b-projection-v1 → C contract above.

## Dataset identity

B logical identity recomputed and asserted at run start. State population,
threshold order, and feature identity all re-verified inside the C run.

## Scientific task

Per-driver marginal cumulative thresholds P(≤1/≤3/≤5/≤10) from causal
state T. RAW independent-binary semantics; coherence via the frozen
equal-weight L2 isotonic projection.

## Temporal splits

Frozen D1 (train 2018–2021 → validate 2022: 88,123 / 23,577 states, 81 /
22 races), D2 (+2022 → 2023: 111,700 / 24,422, 103 / 22), D3 (+2023 → 2024:
136,122 / 26,606, 125 / 24). Recorded in `split_audit.json` from
resolved folds, not memory. Preprocessing and all fits on outer TRAIN
only; no tuning exists in C.

## Baselines

Climatology (per-fold train-state rates, constant); position persistence
(1[pos≤K], null→train rate fallback — 261 null states corpus-wide);
grid (1[grid≤K], pit-lane 0 → 1.0 on all thresholds, documented); L2-logistic
control (4 independent binary models, frozen builder, C=0.01 from V3.1B/V3.3
lineage FROZEN_LOGR_C, lbfgs/1000/None/42).

## Logistic control

Config frozen in the C contract before fitting; namespace is exactly {C};
no search. Same train-only preprocessing contract as frozen Model Lab
(`fit_family`/`predict_family` reuse, not reimplementation).

## Preprocessing

`preprocessing_contract.json`: frozen `fit_preprocessor` via the harness
path, fit on outer TRAIN only, applied unchanged; 110 columns exact order;
finite outputs asserted at predict time by the reused path.

## Prediction contract

OOF frames (`data/v3/v3_5c/oof_{D1,D2,D3}.parquet`, ignored): state/race/
driver/season/fold/model identity + 4 targets + RAW + PROJECTED
probabilities. Targets/predictions joined by state_id, never row position.
Policy: both RAW and PROJECTED stored (projection deterministically
reproducible from RAW via the frozen utility).

## Primary metric

Mean race-macro log loss over the 4 thresholds (eps 1e-15, lower better,
per-threshold components persisted). Race-macro gives each race equal
weight; the mean is unweighted (A: no reason to weight thresholds).

## Race synchronization

Evaluation states are ALL sidecar states: each row is already a causal
(T → outcome) pair with T-safe features, so no cross-driver snapshot
synchronization is needed (unlike top-k ranking, which compares drivers at
a shared T). State-count distortion is handled by race-macro aggregation;
state-pooled LL is secondary only. Races with different checkpoint counts
contribute equally to the headline by construction.

## Secondary metrics

Per threshold: Brier, ECE, state-pooled LL (RAW + projected); accuracy@0.5
descriptive only, never a key metric.

## Coherence projection

Exact B implementation (`outcomes.project_isotonic`) applied to every
baseline/model, including already-coherent deterministic ones.

## Raw vs projected results

Primary (raw, projected): D1 clima 0.485202/0.485202, persist
2.897136/2.897136, grid 5.590324/5.590324, logistic 0.221509/0.221024; D2
0.482742, 2.856744, 5.082478, 0.202229/0.202037; D3 0.482779, 2.472132,
3.710082, 0.187933/0.187885. Projection never hurts; deterministic
baselines adjust exactly 0. Logistic violates on ~5% of rows with tiny
adjustments (D3: 1292/26606, mean abs 7.7e-05, max 0.070).

## Projection diagnostics

frac_violated_before, mean/max abs adjustment, per-threshold adjustments
persisted per fold/model. Deterministic baselines: 0 violations (verified,
not assumed).

## Race-level evidence

`race_level_results.json`: per-race primary contributions (raw + projected)
for every fold/model — independently reconstructs race-macro scores, paired
deltas, and bootstraps without state-level JSON.

## Bootstrap validation

Paired race bootstrap (B=2000, seed 42, 95% CI, reused frozen
`paired_bootstrap`). Logistic vs climatology: D1 −0.264 [−0.285,−0.239], D2
−0.281 [−0.304,−0.251], D3 −0.295 [−0.319,−0.267] (100% races improved). Vs
position persistence: ≈ −2.3…−2.7, CIs far from zero. Validation
infrastructure, not a C gate.

## OOF artifacts

Ignored `data/v3/v3_5c/` parquets with content-SHA identities in
`prediction_identities.json`. No 2025 predictions exist.

## Harness parity

Independent minimal paths: fresh-sklearn D3/top1 refit → max diff 0.0
(bit-exact); full numpy metric recompute (all folds/models/thresholds) →
0.0; independent persistence recompute → 0.0. `harness_parity.json`:
all_match true.

## V3.1B winner diagnostic

Same-state comparison of V3.5 logistic p_win vs frozen V3.1B OOF winner
probabilities: correlation 1.0, max abs diff 3e-11…3e-8, LL diff ~1e-11.
Machine-precision equivalent — explicitly NOT bit-exact, so NOT called
equivalent. Diagnostic only; nothing changed. (Near-identity is expected:
same arm, same C, same preprocessing lineage, same state population.)

## 2025 firewall

2025_CONTACT = NONE. Dev-season filter + 2025 tripwire + ProtectedHoldoutError
reuse + artifact scan (name + row-level: PASS) + tests. No 2025 prevalence,
fit, prediction, or metric.

## D screening interface

Frozen in the C contract: `fit(train_X[110], train_targets[4])` →
`predict_proba(validation_X)` returning 4 RAW probabilities in frozen order.
D inherits features/folds/preprocessing/targets/metric/projection/bootstrap/
OOF schema; redefinition forbidden. Candidate boundary stays narrow per A
(independent binary families; ordinal/ranking/survival/multiclass closed).

## Compute

24.0 s total for the full run (12 logistic fits + metrics + bootstraps).
Modest by design; no search.

## Tests

`tests/test_v3_5c_harness.py` (next section). Policy run: C + B + A +
metrics/aggregation/predictions/splits/temporal guards; no full Tier-1; the
V3.4 sentinel left untouched (narrow selection avoids it).

## Known limitations

0/1 baselines score poorly on LL by construction (expected; ranking value
not scored here); p_win/V3.1B equivalence is diagnostic; bands diagnostic;
C establishes behavior, selects nothing.

## V3.5D recommendation

Screen a small number of independent binary probabilistic families through
this frozen harness. Do not redefine it, tune nothing, touch nothing in
2025.
