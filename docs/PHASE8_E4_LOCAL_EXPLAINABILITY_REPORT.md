# PHASE 8 E4 — LOCAL CHECKPOINT EXPLAINABILITY REPORT

Status: **E4 COMPLETE — READY FOR E5**

Phase 8 progress: E0 (contract audit) complete, E1 (reference cache path)
complete, E1.5 (frozen matrix reuse) approved, E1.6 (accelerated cache
builder) complete, E2 (production replay cache: 149 races / 9,644
checkpoints / 189,610 observable predictions) complete, E3 (global
explainability) complete, **E4 (local checkpoint explainability) complete**.

E4 explains one frozen winner `LogisticRegression` score for one observable
driver at one replay checkpoint as an **exact additive decomposition in
model log-odds**. It is model explanation, not causal or race-outcome
explanation. It never retrains, retunes, recalibrates, changes
preprocessing/ALL_84/coefficients, normalizes probabilities, reads 2025,
reads labels, uses SHAP, or touches the E2 prediction cache.

## 1. Mathematics

For the frozen fitted linear model and the transformed input `x'` (106
dimensions):

```
x'  = preprocessor.transform(canonical_ALL_84_row)
c_j = beta_j * x'_j                              # log-odds contribution
z   = intercept + sum_j c_j                      # model logit
p   = 1 / (1 + exp(-z))                          # INDEPENDENT_BINARY
```

`explanation_space = "LOG_ODDS"`, `probability_semantics =
"INDEPENDENT_BINARY"`. Contributions are never converted into
win-probability increments and per-driver probabilities are never
normalized across a race.

## 2. Local explanation contract (additive)

```
LOCAL_EXPLANATION_CONTRACT_VERSION = "v1"
LOCAL_EXPLANATION_FORMAT          = "local-explanation-v1"
```

The contract is additive. Older replay/prediction contracts are unchanged:
`REPLAY_PREDICTION_CONTRACT_VERSION = "v1"` and the on-disk
`replay-checkpoints-v1` artifact are untouched. A local explanation
identifies: race/frame/checkpoint identity, driver, feature identity, model
identity, probability semantics, explanation space, intercept, logit,
probability, transformed contributions, canonical grouped contributions,
reconstruction residual, missingness/imputation metadata and limitations.

## 3. Frozen identities

| Field | Value |
|---|---|
| Estimator | `LogisticRegression` |
| Params | `C=0.01`, `penalty=l2`, `solver=lbfgs`, `max_iter=1000`, `class_weight=None`, `random_state=42` |
| Feature set | `ALL_84` / `v8` |
| Calibration / semantics | `RAW` / `BINARY_PROBABILITY` / `INDEPENDENT_BINARY` |
| Canonical / transformed | 84 / 106 = 70 numeric + 11 boolean + 25 one-hot |
| Intercept | `-5.574170885990861` |
| Serving artifact SHA-256 | `1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4` |
| Specification fingerprint | `3164de9e61ca94ab958e26590608824ca6c7b05de29c5398d3d204a8c329c24d` |
| Phase-2 matrix content hash | `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db` |
| Training seasons | 2018–2024 |

The explanation consumes the frozen preprocessor and estimator directly
(`preprocessor.transform`, `estimator.coef_`, `estimator.intercept_`,
`estimator.decision_function`, `estimator.predict_proba`); preprocessing is
never independently reproduced.

## 4. Feature source (exact Phase-2 lookup)

For a checkpoint `T` and observable driver `D`, E4 resolves the **exact**
frozen Phase-2 matrix row by identity:

```
(race_id, driver_id, lap_number = observed_lap_number, state_time_s = observed_time_s)
```

via `scripts.replay_feature_matrix.FrozenReplayFeatureMatrix` (the E1.6
exact-lookup backend; SHA-pinned to the frozen manifest, 2018–2024 only).
Lookup is exact identity only: **no nearest, tolerance, rounding,
fall-forward, or interpolation**. A missing or ambiguous row raises and the
request fails closed. E1.5 proved matrix rows equal recomputed features
(3,764/3,764 rows, max diff 0.0); E1.6 extended exact coverage to the whole
served corpus.

The driver observation identity is taken from the cached frozen snapshot
itself (stored verbatim at checkpoint generation), so E4 re-derives no
state and the E2 cache is the three-way anchor.

## 5. 2025 firewall

- `FrozenReplayFeatureMatrix.load` projects to the 2018–2024 served view and
  rejects any out-of-scope season (`MatrixScopeError`).
- The replay service rejects unknown races (including every 2025 race)
  before explanation (`RaceNotFoundError`); the API returns 404
  `unknown_race`.
- No 2025 row, target, label, seed or metric is read anywhere in E4.

## 6. Label firewall

`FrozenReplayFeatureMatrix` structurally refuses label/eligibility columns
at construction, and the served view carries only identity metadata + the 84
predictive columns. `v2/local_explainability.py` references no label,
companion or task-mask column, no `classified_flag`, and never reads a
parquet file (pinned by test).

## 7. Contribution mathematics (106 dimensions)

```
contribution_vector = estimator.coef_[0] * preprocessor.transform(row)[0]
reconstructed_logit  = intercept + contribution_vector.sum()
```

Required exactness (validated, never loosened):

| Check | Tolerance |
|---|---|
| `abs(reconstructed_logit - decision_function)` | `<= 1e-12` (observed `0`–`1.8e-15`) |
| `abs(sigmoid(reconstructed_logit) - predict_proba)` | `<= 1e-12` |
| `abs(sigmoid(reconstructed_logit) - cached_probability)` | `<= 1e-12` |
| `abs(sum(canonical) - sum(transformed))` | `<= 1e-12` |

Each transformed contribution identifies `transformed_index`,
`transformed_name`, `canonical_feature`, `family`, `feature_type`,
`category_value`, `transformed_value`, `coefficient` and
`log_odds_contribution`. The authoritative 106 → 84 map is E3's
`build_transformed_feature_map` (fitted
`get_feature_names_out()` order, never guessed); a second parser does not
exist. `_group_rows` additionally asserts each mapped coefficient equals the
frozen estimator coefficient (stale/tampered maps fail closed).

## 8. 106 → 84 canonical grouping

- numeric: one transformed dimension → one canonical contribution;
- boolean: one transformed dimension → one canonical contribution;
- categorical: **sum** of the fitted one-hot block → one canonical
  contribution.

`sum(canonical contributions) == sum(transformed contributions)` within
machine precision, and all 84 canonical features are covered with exactly
106 transformed dimensions total.

## 9. Missingness / imputation

Per canonical feature, `input_state` is derived from the raw canonical value
plus the fitted preprocessing state (never from the transformed value
alone):

| State | Meaning |
|---|---|
| `OBSERVED` | raw value present (categorical: a fitted category fires) |
| `IMPUTED_NUMERIC_MEDIAN` | raw numeric missing → fitted training median |
| `IMPUTED_BOOLEAN_MODE` | raw boolean missing → fitted training mode |
| `MISSING_CATEGORY` | raw categorical missing → `"MISSING"` sentinel (or the literal sentinel) |
| `UNKNOWN_CATEGORY` | non-missing value outside the fitted vocabulary → all-zero one-hot block |

`IMPUTED_*` report the fitted imputed value; `MISSING_CATEGORY` and
`UNKNOWN_CATEGORY` are distinct states; no reference-category explanation is
invented.

## 10. Categorical semantics

`OneHotEncoder(handle_unknown="ignore")` with no dropped category: all
fitted categories are encoded and an unseen category fires the all-zero
block (`grouped contribution = 0`, `unknown_category`/`UNKNOWN_CATEGORY`
explicit). The active fitted category is reported when one fires.

## 11. Three-way prediction consistency

For every explanation E4 requires agreement between:

1. the additive reconstruction `sigmoid(intercept + Σc_j)`;
2. the frozen serving estimator (`decision_function` / `predict_proba`);
3. the E2 cached replay probability.

Any disagreement raises (`LocalReconstructionError` /
`CachedPredictionMismatchError`). Tested on early/mid/late checkpoints of a
full race and on the thin 2021 Spa race.

## 12. Top-N policy + omitted accounting

Deterministic compact view: top 5 positive canonical contributions
(descending, tie-break canonical name) and top 5 negative (ascending,
tie-break canonical name). The payload also carries
`total_positive_log_odds`, `total_negative_log_odds`,
`shown_*`, `omitted_positive_log_odds`, `omitted_negative_log_odds`,
`positive_feature_count`, `negative_feature_count`, and the explicit
contract that **top-N does not reconstruct the prediction; only the full
canonical vector does**.

## 13. API

```
GET /v2/replay/{race_id}/frames/{frame_index}/predictions/{driver_id}/explanation
```

(The endpoint namespaces under `/v2/replay` rather than the frozen
`/v2/races/{race_id}/replay` family so the Phase-5 replay route inventory
stays exactly four routes.)

Read-only; no explanation mathematics is in the route handler. Public
payload is compact (identity, probability, logit, intercept, residual,
top positive/negative canonical contributions, omitted accounting,
model/probability semantics, limitations); the full 84/106 evidence stays
domain-internal.

Error mapping (mirrors the R4 replay family):

| Case | Response |
|---|---|
| served checkpoint + observable driver | 200 explanation |
| served checkpoint + roster driver with no observation | 422 `driver_not_observable` |
| driver not in roster | 404 `unknown_driver` |
| unknown race / 2025 | 404 `unknown_race` |
| unknown frame | 404 `unknown_frame` |
| non-checkpoint frame | 404 `not_prediction_checkpoint` (+ pointers, never snapped) |
| cache missing/stale/incomplete/corrupt | 503 `prediction_unavailable` |
| exact feature row unavailable / reconstruction failure | 500 `internal` (fail closed) |

## 14. Cache relationship + explanation cache decision

The 58.6 MB E2 prediction cache is immutable and is never rewritten or
embedded; E4 reads it (and the frozen matrix) separately. No explanation
cache was built. On-demand generation is cheap (linear model + matrix
lookup); see §18.

## 15. Frontend

`PredictionPanel` gains an expandable per-driver local view
(`LocalExplanationPanel` + `useLocalExplanation`). It renders:

- **MODEL LOG-ODDS — KEY INPUTS** with `LOG-ODDS ↑` / `LOG-ODDS ↓` rows;
- model probability, an independent-binary note and a log-odds
  (not-probability-points) note;
- omitted-contribution accounting;
- `IMPUTED` / `MISSING` / `UNKNOWN TO FITTED ENCODER` markers so hidden
  input state is never presented as observed;
- an optional technical detail (intercept, reconstructed logit, residual,
  model version).

Factual context (the prediction header) stays visually separate from model
contribution evidence.

## 16. Language contract

Reuses and extends E3's contract: allowed wording includes "increased model
log-odds", "decreased model log-odds", "model input", "fitted coefficient",
"local model contribution", "prediction". Forbidden wording includes
"caused", "will win", "chance", "reason for", "true reason", "helped",
"hurt(s)", "win factor", "percentage of the win", "the model knows/thinks",
"probability points". Guarded in generated copy (backend + frontend tests).

## 17. Temporal validation (post-T mutation invariance)

The explanation consumes only the exact frozen Phase-2 row at the checkpoint
identity `T`. Overwriting every later row with garbage leaves both the
resolved row and the explanation byte-identical (tested). This mirrors the
Phase-2 bounded temporal-safety philosophy and is **not** claimed to prove
the absence of every possible leakage mechanism.

## 18. Red team

| Attack | Outcome |
|---|---|
| 2025 request | matrix scope + unknown-race rejection (tested) |
| future row substituted | explanation invariant (tested) |
| nearest timestamp attempted | exact lookup fails closed (tested) |
| missing exact matrix row | `MatrixLookupError` / `ExplanationFeatureUnavailableError` (tested) |
| duplicate matrix identity | constructor refuses (tested) |
| label injected | constructor refuses; projection carries no labels (tested) |
| feature order changed | early column-order guard fails closed (tested) |
| coefficient (map) order/value changed | map/estimator coefficient integrity check fails closed (tested) |
| categorical block grouped incorrectly | explicit per-feature block sum + coverage (tested) |
| unknown category | all-zero block, contribution 0 (tested) |
| numeric NaN / boolean NaN | imputation state + fitted value (tested) |
| MISSING categorical | distinct from unknown (tested) |
| cached probability deliberately altered | `CachedPredictionMismatchError` (tested) |
| top-N accounting dropped | accounting required + explicit note (tested) |
| probability normalization attempted | semantics pinned; no normalization (tested) |

## 19. Performance (on-demand, no cache)

Measured over early/mid/late checkpoints of a full race (frozen matrix path,
warm process):

| Measure | Value |
|---|---|
| Full checkpoint field (42 explanations) | p50 `20.4 ms`, p95 `21.2 ms`, max `46.8 ms` |
| Warm single driver | p50 `20.2 ms`, p95 `20.8 ms` |

p95 is comfortably interactive, so **no explanation cache was built**. The
matrix is loaded lazily once per process on first explanation request.

## 20. Tests

`tests/test_v2_phase8_e4.py` — **45 passed**. Coverage: contract version and
semantics; frozen model identity; exact feature identity; exact matrix row
equality; 84 → 106 transform; logit/sigmoid reconstruction; three-way cached
probability consistency; 106-dimension contribution vector; 106 → 84
canonical grouping (84 covered, 106 dims, categorical block sums); numeric /
boolean / MISSING / unknown-category missingness; direction labels; top
positive / negative ordering + tie determinism; omitted accounting; compact
public projection; no probability normalization; determinism; 2025 + label
firewalls; nearest-timestamp / missing-row / duplicate-identity / feature
order / coefficient / altered-cached-probability fail-closed; post-T
mutation invariance; language contract; API hit / unknown driver /
unobservable / non-checkpoint / cache missing / unknown race / 2025 / route
inventory; latency characterization.

Frontend: `node --test` **126 passed** including the new local-explanation
display/language tests; `tsc` clean; `eslint` clean; `next build` clean.

## 21. Regression

Rerun under Python 3.11 / scikit-learn 1.8.0:

| Suite | Result |
|---|---|
| `tests/test_v2_phase8_e4.py` | 45 passed |
| `tests/test_v2_phase8_e3.py`, `test_v2_phase5_r3/r4/r6/r7.py`, `test_v2_model_lab_p31.py`, `test_v2_phase4_r4/r5.py` | 433 passed, 5 skipped |
| `tests/test_v2_phase8_e1_6.py` | 19 passed (~9m51s) |
| `tests/test_v2_phase5_freeze.py`, `test_v2_phase4_freeze.py`, `test_v2_phase6_freeze.py` | 51 passed, 4 pre-existing failures (see below) |
| frontend `node --test` | 126 passed |
| frontend `tsc` / `eslint` / `next build` | clean |

Pre-existing, E4-unrelated historical freeze failures (present before E4,
driven by later-phase repository state, not by E4):

- `test_v2_phase4_freeze.py::test_frozen_module_hashes_match` and
  `test_v2_phase5_freeze.py::test_freeze_manifest_file_hashes_match` /
  `test_freeze_manifest_documents_authorized_api_main_drift`: the frozen
  manifests pin `api/main.py` at the Phase-4 (`455910…`) and Phase-5
  (`284027…`) hashes, while the repository `api/main.py` at `HEAD`
  (`c43221…`) already differs because Phases 6/7 added their routers. The
  Phase-5 suite explicitly authorises this `api/main.py` drift
  (`test_phase4_upstream_module_hashes_except_authorized_drift` passes).
- `test_v2_phase5_freeze.py::test_freeze_manifest_generated_cache_not_required`
  asserts `results/v2_replay` does not exist; the E2 production cache
  (149 races) exists by design.

No E4 change introduces a new failure in these suites: the only E4 effect on
`api/main.py` is one additive router import/include, which the Phase-5
authorized-drift model anticipates. A first E4 route under
`/v2/races/{race_id}/replay/…` did collide with the frozen Phase-5 replay
route-count pin (`test_app_registers_replay_routes_once`, exactly 4), so the
endpoint was namespaced under `/v2/replay/…` to keep that inventory intact.

`v2/explainability.py` received one additive, backward-compatible change (an
optional `forbidden` argument on `assert_language_compliant`, defaulting to
the E3 contract) so E4 copy can extend the contract without mutating E3
output or the stored E3 artifact. The E3 artifact SHA remains
`bae84b614a6e9e176d5bb9c33b99dcaf4cba3f376333b0f075c828f73982939f`.

## 22. Limitations

- Model log-odds decomposition only; not causal, not a race-outcome
  explanation, not probability-point attribution.
- Numeric contributions are per the standardized transformed input,
  conditional on other inputs; boolean inputs are unscaled.
- Categorical contributions sum the fitted one-hot block (no dropped
  reference category).
- Top-N is a compact view, not a full decomposition.
- Independent per-driver binary probabilities are never normalized.
- SHAP remains deferred/dropped for v1; exact linear mathematics is the
  method.

## 23. Repository safety

No `git reset/restore/checkout/clean/stash`, no `git add`, no commit, no
tag. Only new E4 modules/tests/report plus the additive `api/main.py` router
include and the one additive `v2/explainability.py` argument were authored.
Unrelated working-tree changes were left untouched.

## 24. E5 entry gate

- [x] local contract frozen
- [x] exact Phase-2 row used
- [x] label firewall green
- [x] 2025 firewall green
- [x] 106 transformed contributions exact
- [x] logit reconstruction exact
- [x] sigmoid reconstruction exact
- [x] cached probability matches
- [x] 106 → 84 canonical grouping exact
- [x] missingness states correct
- [x] categorical grouping correct
- [x] top-N deterministic
- [x] omitted contribution accounting correct
- [x] no probability-point attribution
- [x] API checkpoint semantics preserved
- [x] frontend language scientifically correct
- [x] temporal mutation tests green
- [x] red-team green
- [x] on-demand performance characterized
- [x] explanation cache avoided (p95 interactive)
- [x] relevant backend regressions green
- [x] frontend tests/tsc/lint/build green

Final verdict: **E4 COMPLETE — READY FOR E5**.
