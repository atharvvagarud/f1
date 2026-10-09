# V3.5B DATASET + TARGET + COHERENCE

## Final verdict

V3.5B COMPLETE — dataset contract validated, ready for V3.5C. Data layer
only: no model was fitted, no learned predictions exist, 2025 was not
contacted.

## Frozen parent

- Tag: `v3.4-ensemble`, commit `3cbd28470ffa211bd754d4262eb10d66d149bf00`
- A contract `15ca7c17…f5efab` recomputed from artifact (match); task
  `ordered_cumulative_finish_thresholds` unchanged.

## A contract

V3.5A selected four cumulative threshold tasks with a deterministic
monotonic projection frozen as part of the method. B implements exactly
that: `raceintel/model_lab/outcomes.py` (target v3.5b-target-v1, status
v3.5b-status-v1, population v3.5b-population-v1, projection
v3.5b-projection-v1) plus one-shot builder `scripts/build_v3_5b_targets.py`.

## Canonical target construction

Outcome grain (race_id, driver_id) from frozen D9 label rows (2018–2024):
y_topK = classified AND position_final ≤ K for K in (1,3,5,10), canonical
names is_top1/3/5/10, aliases p_win/p_podium/p_top5/p_top10. Labels computed
once at outcome grain, then identity-joined to states — never re-derived
per state row, never by row order. Duplicate keys and unknown shapes fail
closed.

## Outcome semantics

position_final is the canonical official ordering (classified_position
agrees where both non-null). Sidecar tags every outcome: CLASSIFIED_POSITION
(2583), UNCLASSIFIED_TAIL (393: back-rank never interpreted as earned —
threshold labels 0 by policy), WITHDRAWN_NO_RESULT (3 null-final rows, 0 by
policy). The semantic tag is metadata, never a feature.

## Status handling

Finished / lap-deficit classified / classified retirements → full labels.
Unclassified R, W, D, DNS → threshold negatives only, excluded from any
ordinal supervision. Unknown position_text tokens or classified rows with
R/W/D shape raise (fail closed). Verified against every observed category in
the 2018–2024 corpus.

## Prediction population

Starters with observable state at T. The 3 never-started withdrawals have no
states (correctly absent from the sidecar); all 2976 other outcomes join to
≥1 state. Later retirements included (9142 unclassified-tail state rows
present as negatives). DNS filtering by label is impossible by construction
— eligibility uses state existence at T only.

## Development dataset

`data/v3/v3_5b/outcome_targets_2018_2024.parquet` (ignored): 162,728 state
rows — exactly the A figure — with state/race/season/driver identity, four
int8 targets, semantic tag. Features stay in the frozen canonical matrix;
the sidecar is joined by identity, never duplicated.

## Identity alignment

state_id unique; exact set-equality with the frozen matrix 2018–2024 state
population; race/driver/season identity match per row; permutation-invariant
(order-free merge + sorted write). Zero missing, zero extra targets.

## Outcome-grain audit

2979 unique (race_id, driver_id) outcomes across 149 races, one canonical
assignment each; no conflicting finals (duplicates would fail closed).

## Label nesting

y_top1 ≤ y_top3 ≤ y_top5 ≤ y_top10 holds for all 162,728 rows (0 violations)
and at outcome grain before expansion.

## Prevalence

Outcome grain: top1 149 (5.00%), top3 447 (15.01%), top5 745 (25.01%),
top10 1490 (50.02%). State grain: 8926 / 26774 / 44612 / 89057 of 162,728.
Per-season tables in the manifest. Outcome and state grains kept separate —
state rows are not independent outcomes.

## Field sizes

148×20 + 2024-r03-R×19. Thresholds well-defined at every size; no fixed-20
assumption anywhere in B code.

## Top-10 / points audit

top10 ⟺ points>0 holds for all 2979 outcome rows. Persisted as observed
empirical equivalence; points is NOT the label and never gates construction.

## Feature identity

ALL_84 (matrix order) + CORE_26 = 110 via the frozen V3.1/V3.3 assemblers
(no reimplementation): hash `e054c6fb…77fc4c89e` (matches V3.3/V3.4 lineage),
matrix prefix verified, zero overlap with targets/semantics/status, no
spatial columns. Feature matrix unmutated.

## Coherence problem

Independent threshold classifiers may emit p1>p3>p5>p10-violating rows. A
froze deterministic projection as part of the method; post-hoc repair after
seeing results is forbidden.

## Projection mathematics

q = argmin Σ(q−p)² s.t. 0 ≤ q1 ≤ q3 ≤ q5 ≤ q10 ≤ 1, equal weights, input order
[top1,top3,top5,top10]. Canonical least-squares isotonic regression solved
by Pool Adjacent Violators. Deterministic, unlearned, race-/stage-/
2025-independent.

## Projection implementation

`outcomes.project_isotonic`: vectorized over states, finite-[0,1]-only
(NaN/Inf/out-of-bounds raise), coherent rows bit-preserved, outputs bounded.
Returns projected probabilities + diagnostics (violation fraction, mean/max
absolute adjustment, per-threshold adjustment). Not exposed to serving.

## Raw vs projected semantics

Threshold models emit RAW probabilities; the projection emits
PROJECTED_COHERENT probabilities. Later screening reports both; projection
diagnostics (fraction violating, adjustment magnitudes) prevent it from
hiding severe incoherence.

## Derived outcome bands

Deterministic differencing of coherent outputs: P(P1), P(P2–P3), P(P4–P5),
P(P6–P10), P(>P10). Verified nonnegative and summing to 1. These are
threshold-differenced diagnostic bands, NOT a P1–P20 distribution.

## Dataset identity

Logical (content) identity `e9ac34e5…57cc5289` over parent + A + seasons +
state IDs + label bytes + thresholds + policy versions + feature hash.
Physical parquet SHA `5892742f…c7426aa7a2`. Rebuild reproduces both exactly
(logical authoritative).

## 2025 firewall

2025_CONTACT = NONE. `ALLOWED_SEASONS` + `ProtectedHoldoutError` on any
2025/other-season request through loaders and the builder; matrix read
filtered to 2018–2024 with an explicit 2025 tripwire. No V3.5 2025 targets
materialized, inspected, or evaluated.

## Reproducibility

Two consecutive builds: identical logical identity and identical physical
bytes. Projection cross-checked against sklearn IsotonicRegression
(dev-only, not a dependency): max diff 1.1e-16 over 2000 random rows; 7
analytical vectors exact.

## Harness readiness

`results/v3/v3_5b/harness_readiness.json`: all pass — 110 features
recomputable, 4 targets, identities, seasons, D1/D2/D3 reusable, threshold
order, projection importable, no 2025 rows.

## Tests

`tests/test_v3_5b_dataset.py`: 37/37 pass (contract SHA, seasons/firewall,
order, uniqueness, alignment, permutation invariance, binary/nesting,
population/DNS semantics, status fail-closed, field sizes, 110/feature
identity, leakage/spatial guards, projection vectors/monotonicity/bounds/
determinism/rejection, bands, identity, readiness, no-fitting guards).

## Known limitations

Sidecar carries no features (matrix is the source); points/status metadata
excluded from state rows by design; top10/points equivalence empirical; no
model/predictions/calibration in B.

## V3.5C recommendation

Validate baselines + metric/bootstrap harness on this dataset (climatology,
position persistence, grid, L2-logistic control), reporting RAW and
PROJECTED_COHERENT quality with violation diagnostics. No screening until
the harness is green.
