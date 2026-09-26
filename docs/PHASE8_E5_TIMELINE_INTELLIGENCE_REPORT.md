# PHASE 8 E5 — PREDICTION TIMELINE INTELLIGENCE + CHANGE EXPLANATIONS

Status: **E5 COMPLETE — READY FOR E6**

Phase 8 progress: E0 complete, E1 complete, E1.5 complete, E1.6 complete,
E2 (production replay prediction cache: 149 races / 9,644 checkpoints /
189,610 observable predictions) complete, E3 (global explainability)
complete, E4 (exact local checkpoint explainability) complete, **E5
(prediction timeline intelligence + change explanations) complete**.

E5 turns the existing checkpoint probability timeline into a
prediction-evolution experience: for one driver between two REAL frozen
checkpoints `A -> B` it reports how the frozen model log-odds changed and
which canonical model-input contributions changed most, **without claiming
that those inputs caused the historical event or race outcome**. It never
retrains, retunes, recalibrates, changes ALL_84 / preprocessing /
coefficients / the replay cache / checkpoint selection, normalizes
probabilities, reads 2025, reads labels, installs SHAP, or introduces LLM /
heuristic event attribution.

## 1. Mathematics

The frozen winner model is linear in the transformed input `x'` (106 dims),
`c_j = beta_j * x'_j`, `z = intercept + sum_j c_j`, `p = sigmoid(z)`
(`INDEPENDENT_BINARY`). At two checkpoints:

```
z_A = intercept + sum_j c_A,j
z_B = intercept + sum_j c_B,j
dz  = z_B - z_A = sum_j (c_B,j - c_A,j) = sum_j dc_j
```

The intercept cancels **exactly** because the same frozen model is used at
both endpoints. `dc_j` is an additive change in **model log-odds**. It is
never a probability-point contribution: the sigmoid is nonlinear, so the
overall probability delta `dp = p_B - p_A` is reported only as an aggregate
model-prediction change, never decomposed per feature.

```
explanation_space        = "LOG_ODDS"
probability_semantics    = "INDEPENDENT_BINARY"
primary invariant        sum_j dc_j == z_B - z_A   (within 1e-12)
```

## 2. Change explanation contract (additive)

```
TIMELINE_EXPLANATION_CONTRACT_VERSION = "v1"
TIMELINE_EXPLANATION_FORMAT           = "timeline-explanation-v1"
```

Additive only. `REPLAY_PREDICTION_CONTRACT_VERSION = "v1"`,
`replay-checkpoints-v1` and `LOCAL_EXPLANATION_CONTRACT_VERSION = "v1"`
are untouched. The change payload carries: status, A/B checkpoint identity
(frame, T, leader lap, reasons, anchors, observed lap/time/position/age),
model identity, probability semantics, explanation space, from/to
probability, probability delta, from/to logit, logit delta, from/to cached
probabilities, reconstruction evidence (canonical delta sum, residual,
tolerances, intercept-cancels), 84 canonical deltas (domain only), top
positive/negative deltas, omitted-delta accounting and limitations.

## 3. Checkpoint comparison semantics (PART H / I)

- The selected frame must be a REAL frozen prediction checkpoint; arbitrary
  frames are **never** snapped to a nearest checkpoint. A non-checkpoint
  raises `NotPredictionCheckpointError`.
- The previous checkpoint is resolved **explicitly** from the frozen
  checkpoint series (`checkpoints[i-1]`), never by timestamp proximity.
- First checkpoint: explicit `NO_PREVIOUS_CHECKPOINT` (HTTP 200). No
  baseline is fabricated.
- The domain layer supports arbitrary `A -> B` (deterministic tests / future
  use); the public v1 API is previous-checkpoint -> selected-checkpoint.

## 4. Driver observability (PART H)

A valid two-point delta requires an evaluated probability at both endpoints.
If the driver is on the roster but unavailable at an endpoint, the service
returns `COMPARISON_UNAVAILABLE` with an exact reason rather than treating a
null probability as zero:

```
DRIVER_ABSENT_AT_PREVIOUS_CHECKPOINT
DRIVER_NOT_OBSERVABLE_AT_PREVIOUS_CHECKPOINT
NULL_PROBABILITY_AT_PREVIOUS_CHECKPOINT
DRIVER_NOT_OBSERVABLE_AT_SELECTED_CHECKPOINT
NULL_PROBABILITY_AT_SELECTED_CHECKPOINT
```

A driver absent from the roster is `unknown_driver` (404), consistent with
E4.

## 5. Canonical contribution deltas (PART C/D/E/F)

For each of the 84 canonical features the domain returns
`from_contribution`, `to_contribution`, `contribution_delta`, the raw values
and input states at both endpoints, active categories, imputed values and a
factual `transition`. The full delta vector is domain-internal; `sum(dc_j)
== logit_delta` is enforced to `1e-12`.

Transition labels (factual, never causal): `RAW_INPUT_UNCHANGED`,
`RAW_INPUT_CHANGED`, `CATEGORICAL_TRANSITION`, `IMPUTATION_TRANSITION`,
`MISSINGNESS_TRANSITION`, `INPUT_STATE_CHANGED`.
`MISSING_CATEGORY` and `UNKNOWN_CATEGORY` both classify as missingness; the
imputed median/mode states classify as imputation.

Categorical features reuse the E4 canonical grouping: the delta subtracts
the whole fitted one-hot block at B minus A (the active one-hot term alone
is not the block contribution). Missingness/imputation transitions are
explicit and never hidden.

## 6. Top-N policy + omitted accounting (PART G)

Deterministic top 5 positive and top 5 negative deltas: positives descending,
negatives ascending, ties broken by canonical feature name. Accounting
returns total / shown / omitted for both signs and requires
`shown + omitted = total` and `total_positive + total_negative = logit_delta`
within `1e-12`. The compact public payload does not send all 84 deltas.

The frontend defines `NEUTRAL_DISPLAY_TOLERANCE = 1e-9` for arrow
classification only, documented PRESENTATIONAL ONLY; the scientific payload
retains exact values and classification is never changed.

## 7. API

```
GET /v2/replay/{race_id}/frames/{frame_index}/predictions/{driver_id}/change
```

Read-only, additive, same namespace and error semantics as E4:
unknown race / 2025 -> 404 `unknown_race`; unknown frame -> 404
`unknown_frame`; non-checkpoint -> 404 `not_prediction_checkpoint` (+
nearest pointers, never snapped); missing/stale/incomplete/corrupt cache ->
503 `prediction_unavailable` (never generated on this path); unknown driver
-> 404 `unknown_driver`; reconstruction failure -> 500 `internal`.

HTTP 200 body statuses: `AVAILABLE`, `NO_PREVIOUS_CHECKPOINT`,
`COMPARISON_UNAVAILABLE`.

## 8. Frontend (PART L/M/N)

`ProbabilityTimelineChart` was extended, not replaced:

- Checkpoint details now show the previous REAL checkpoint and a `Δ vs
  previous (pp)` column (data only; nulls preserved).
- A `ChangeExplanationPanel` renders the `MODEL SCORE CHANGE`:
  `P from -> to  Δ pp`, `LOGIT from -> to  Δ`, and top positive/negative
  **log-odds** deltas. Feature rows never show percentage points.
- A `Replay frame N` button navigates to the exact selected checkpoint
  (`navigation.seek`); no nearest-frame behaviour.
- Local vs change distinction is explicit copy: the Winner model panel is
  the LOCAL view ("what contributes now?"), the timeline change panel is the
  CHANGE view ("what changed since the previous checkpoint?").

The frontend preserves the brutalist motorsport telemetry design and adds
no chart dependency.

## 9. Language contract (PART O)

Extends E3/E4. Allowed: "model score changed", "model log-odds
increased/decreased", "contribution increased/decreased", "prediction
changed by X percentage points", "between these checkpoints". Forbidden
(among others): "caused", "because", "due to", "led to", "reason
probability", "made the driver", "reacted to", "the cause of", "as a result
of". Feature rows are never described with probability points.

## 10. Temporal safety (PART P)

Each endpoint explanation consumes only its own frozen Phase-2 row at its
exact `(race_id, driver_id, lap_number=observed_lap_number,
state_time_s=observed_time_s)` identity, resolved by the E1.6 exact-lookup
backend (no tolerance). Tests confirm that (a) mutating all matrix rows
after B leaves A, B and the delta byte-identical, and (b) mutating rows
strictly between A and B (not the exact A/B rows) leaves A/B authoritative.

## 11. Red team (PART Q)

Tested: 2025; non-checkpoint; nearest-checkpoint attempt; first checkpoint;
driver absent/unobservable at A or B; null cached probability; altered
cached probability; feature-order tamper; coefficient tamper (inherited E4
fail-closed); categorical / missingness / imputation transitions; all-zero
deltas; positive/negative cancellation; top-N omitted accounting;
normalization rejection; future-row and between-row mutation; causal
forbidden wording; determinism. Each fails closed or returns the exact
defined state.

## 12. Performance (PART R)

`get_change` = two E4 local explanations + exact delta. Measured on the
local session corpus: **p50 38.6 ms, p95 40.8 ms, max 62.0 ms** (E4 local
explanation is ~19 ms p50). Comfortably interactive. No timeline-explanation
cache was created; none is justified.

## 13. Cache decision

No new cache. E5 is computed on demand from frozen components and the
existing E2 prediction cache; the route cannot generate predictions.

## 14. Tests

- Backend `tests/test_v2_phase8_e5.py`: **51 passed** (contract, previous
  checkpoint, first checkpoint, observability states, identity, cached
  probabilities, probability/logit deltas, 84 deltas, exact reconstruction,
  three-way consistency, categorical/missingness/imputation transitions,
  top-N + tie determinism, omitted accounting, zero/cancellation, API
  statuses, 2025 + label firewalls, temporal mutation invariance,
  determinism, language contract, performance).
- Backend regression: `test_v2_phase8_e4.py`, `test_v2_phase8_e3.py`,
  `test_v2_phase5_r6.py`, `test_v2_phase5_r4.py` -> **184 passed**.
- Frontend `node --test`: **137 passed** (new `timelineChange.test.ts`
  covers point/previous-checkpoint data, probability-delta and logit-delta
  formatting, positive/negative delta rendering, no per-feature probability
  attribution, first-checkpoint state, no snapping, language copy).
- `tsc --noEmit` clean; `eslint` clean; `next build` success.

## 15. Limitations

- Model-score evolution only; not historical causation or race outcome.
- Deltas are additive in model log-odds, never win-probability increments.
- The overall probability delta is global (percentage points); the sigmoid
  prevents an exact per-feature probability decomposition.
- Numeric deltas are per standardized transformed input and conditional on
  the other inputs; boolean and categorical inputs are not magnitude-
  comparable with standardized numeric inputs.
- Independent per-driver binary probabilities are never normalized into a
  race distribution.
