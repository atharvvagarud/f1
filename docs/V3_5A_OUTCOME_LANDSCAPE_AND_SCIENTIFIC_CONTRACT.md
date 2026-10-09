# V3.5A OUTCOME LANDSCAPE + SCIENTIFIC CONTRACT

## Final verdict

V3.5A COMPLETE — outcome contract frozen, ready for V3.5B. Audit + problem
formulation + contract only. No predictive model was fitted, no V3.5
predictions exist, 2025 was not contacted.

## Frozen parent

- Tag: `v3.4-ensemble`
- Commit: `3cbd28470ffa211bd754d4262eb10d66d149bf00`
- Contract hash: `15ca7c17146062edb5196a5de244fadd81d38562b2ca5714e58a21d4efb5efab`

## Scientific question

Can the platform estimate useful probability distributions over driver race
outcomes from a historical race state at time T while preserving strict
temporal causality, coherent probability semantics, and honest uncertainty?
V3.5 is NOT another attempt to improve winner probability.

## Repository/data audit

Canonical outcome evidence lives in the frozen D5 `results` entity, consumed
verbatim by frozen `raceintel/pipeline/d9.py::labels_from_results` into the
`race_driver_labels` artifact, then validated by `raceintel/labels/builder.py`
(F13/F14) against `raceintel/labels/contracts.py` (LABEL_SET_VERSION v1).
Key modules: results source of truth; labels/builder + contracts (targets);
model_lab/winner.py (synchronized winner evaluation); model_lab/protocol.py
(D1/D2/D3, PROTECTED_HOLDOUT_SEASON=2025); model_lab/metrics.py +
aggregation.py + calibration.py (evaluation reuse); simulation/results.py
FinishOrder (MC2 joint-future semantics). Features never receive label values
(pinned by existing tests); `FORBIDDEN_LABEL_COLUMNS` in preprocessing.

## Canonical outcome semantics

"Finishing position" = official classified position (FastF1 Position),
verbatim as `position_final`. Verified: `classified_position` is identical
whenever both are non-null, so `position_final` IS the canonical ordering —
there is no second competing ordering. Null only for 3 never-started
withdrawals (0 laps). Physical track position at retirement and last observed
running position are NOT what the repository means by finishing position.

## Status taxonomy

2018–2024 corpus (149 races, 2979 driver-race outcomes): Finished 1665;
lapped-but-classified (+1 Lap 536, +2 Laps 101, +3 Laps 12, Lapped 208);
classified retirements 59 (90%-distance rule); unclassified `R` retirements
374 with tail back-rank numerics (observed 13–20, never ≤10); withdrawals `W`
15 (3 null-final/0-lap + 12 numeric back-rank); disqualifications `D` 7 (all
numeric back-rank, unclassified); did-not-start 6 (0 laps, within W/R rows);
free-text mechanical causes (Collision/Engine/Accident/…) are retirement
causes, not targets. No DNF target exists (deferred in F13).

## Prediction population

All starters with an observable state at time T (state existence at T only).
DNS/never-started drivers are excluded by construction — no lap states exist
— never by label filtering, so no leakage. Drivers who later retire are
INCLUDED; excluding them would leak future information.

## Target distribution

Driver-race grain (NOT state rows): winner 149 (5.0%), podium 447 (15.0%),
top-5 745 (25.0%), top-10 1490 (50.0%), classified 2583 (86.7%),
unclassified 396 (13.3%). Exactly 1/3/5/10 per race for win/podium/top-5/
top-10. State grain for scale: 162,728 D9 lap-state rows (~54.6 per
outcome) — prevalence is reported at outcome grain only. `scored_points`
(points > 0) is per-row identical to top-10 in 2018–2024, so P(points) would
duplicate P(top-10), not extend it. No model performance exists by design.

## Field-size analysis

Field is 20 drivers except 2024-r03-R (19). A fixed 20-class formulation is
therefore NOT scientifically exact for this corpus. Cumulative thresholds are
field-size-free and unaffected — one reason they were selected.

## Temporal safety

Labels are post-race supervision at (race_id, driver_id) grain, physically
and logically separate from the feature matrix (feature calculators cannot
import label modules — pinned by test). Target construction from official
results cannot leak into predictive features because features are computed
from lap-state at T only. Phase2 untouched.

## Outcome coherence

Per-driver requirement: p_win ≤ p_podium ≤ p_top5 ≤ p_top10 for every row,
enforced by a deterministic monotonic projection frozen as part of the method
before any screening (post-hoc repair forbidden). Whole-field exclusivity
(exactly one P1, etc.) is NOT claimed: per-driver marginals summing across
thresholds do not imply a joint field distribution. That distinction is the
V3.5/MC2 boundary.

## Relationship to V3.1B

V3.5 neither replaces nor reuses V3.1B as a component. V3.1B P(win) is RAW
INDEPENDENT_BINARY and remains the standalone champion reference; V3.5 p_win
is compared against it on the same race-macro log loss, with large
divergences to be explained, never reinterpreted. No serving change.

## Relationship to MC2

V3.5 learns conditional per-driver outcome marginals from historical states.
MC2 simulates mutually exclusive joint futures (FinishOrder: unique 1..K
plus explicit retirees per roster). Different objects; do not fuse. V3.8 owns
model × simulation consensus.

## Candidate formulations

A. Independent cumulative thresholds — SELECTED. B. Ordinal — DEFERRED (no
ordinal implementation in frozen deps; proportional-odds untested). C.
Multiclass exact-position — DEFERRED (back-rank contamination, no
exclusivity, 19-driver breakage, heavier). D. Regression/distributional —
REJECTED (bounded-discrete loss mismatch, ad-hoc uncertainty). E.
Pairwise/ranking — DEFERRED with head-to-head outputs (190 pairs/state
compute; distribution conversion nontrivial). F. Survival/competing-risk —
REJECTED (classification flags already handle retirement structure). G. None
superior discovered.

## Formulation scorecard

In contract `formulation_scorecard` (STRONG/ACCEPTABLE/WEAK + verdicts).
A is STRONG on temporal safety, labels, semantics, field handling, reuse,
compute, and strategy usefulness, ACCEPTABLE on coherence (projection
predeclared). Nothing selected for novelty.

## Selected primary task

`ordered_cumulative_finish_thresholds`: P(≤1), P(≤3), P(≤5), P(≤10) as four
binary tasks on the same state rows with frozen monotonic projection.
Secondary (diagnostic only): exact-position distribution via
threshold-differencing, with coherence caveats — not a promotion path.

## Output contract

Admitted: p_win, p_podium, p_top5, p_top10 (all [0,1], RAW
independent-binary, state_id/driver_id/race_id/season keys). Deferred:
expected_finish, position_probabilities, quantiles, head-to-head (need
machinery a later contract must justify). No fake intervals.

## Baselines

Climatology (empirical base rates), current-position persistence
(deterministic from state at T), grid-position thresholds, and one ML
control (L2-logistic per threshold on the frozen 110 arm, V3.1B recipe
lineage). All use only information available at T. Closed set.

## Feature policy

Frozen ALL_84 + CORE_26 (110 features); contains state `position`,
`race_progress_frac`, `grid_position`. No new features in A; spatial P12
excluded unless separately justified later.

## Temporal protocol

Reuse frozen D1 (train 2018–2021 → validate 2022), D2 (→2023), D3 (→2024);
final fit 2018–2024. Outer validation selects nothing; inner tuning on
training history only. 2025: no selection use, ever.

## Metrics

Primary: mean race-macro log loss over the 4 thresholds (proper scoring
rule, V3.1B lineage, race-macro against state-count dominance). Secondary:
per-threshold Brier/ECE, top-K calibration, monotonic-violation rate,
state-pooled LL diagnostics. No RPS/CRPS in frozen metrics — such
diagnostics may be added as evaluation code in B, not as dependencies.

## Race-level statistics

Race is the unit. Paired race bootstrap, B=2000, seed 42, 95% CI on
candidate-minus-baseline (direction explicit). Bootstrapping states as
independent samples is forbidden.

## Calibration

RAW primary. Learned calibration only from training history; never outer
labels, never 2025, never post-hoc rescue. Per-threshold reliability/ECE via
the frozen calibration module.

## Coherence policy

Projection (non-decreasing rearrangement across thresholds) is part of the
frozen method, specified mathematically in the V3.5B dataset contract before
screening. Violation rate reported; incoherent shipment disallowed.

## Censoring policy

Threshold supervision: all rows with non-null `position_final` (unclassified
are structural >10 negatives); 3 null-final rows excluded. Ordinal
supervision (deferred): `classified_flag` true only. Prediction-time
eligibility from state existence only.

## 2025 firewall

2025_CONTACT = NONE in A. B/C/D mechanism: ProtectedHoldoutError reuse,
allowed seasons 2018–2024, forbidden result/label paths, artifact scan,
tests. Final-evaluation policy frozen in V3.5F under the conservative
previously-revealed posture (2025 globally non-pristine from earlier phases'
other tasks).

## Compute budget

Minutes to low tens of minutes per candidate family on M4 MacBook Air;
small predeclared grids; no GPU.

## Dependencies

numpy/pandas/scikit-learn/xgboost only. Nothing added in A. No
PyTorch/TensorFlow/ranking/probabilistic-programming additions without a
genuinely indefensible-with-current-deps formulation.

## Stage plan

V3.5A contract (here) → B dataset/targets → C baselines/harness → D
screening → E refinement/calibration (if warranted; RAW default) → F
out-of-time evaluation → G validation + freeze. B must specify the
monotonic projection mathematically and construct the threshold label frame.

## Known limitations

Per-driver marginals only; top-10/points equivalence is empirical;
19-driver race noted; p_win/V3.1B comparability is diagnostic; 2025 globally
non-pristine; no performance at contract time by design.

## V3.5B recommendation

Build the threshold dataset: (race_id, driver_id, state) × 4 binary labels
from frozen artifacts, population rule as above, frozen monotonic projection
spec, 2025 firewall enforced in code + tests. No model screening until the
C harness is validated.
