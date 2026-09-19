# Phase 4 — Race State + Prediction Engine

R0 architecture/contract stage. READ-ONLY findings + implementation contract for R1–R7.
No code changed in R0. Phase 4 is NOT replay (Phase 5); it builds the deterministic
state/prediction primitives replay will call.

Seal anchor: commit `3887825`, tag `v2-model-lab-phase3`.

---

## 1. Frozen inputs

| Input | Frozen value | Source |
|---|---|---|
| Task / target / mask | `winner` / `is_winner` / `eligible_is_winner` | `v2/features/build_matrix.py: TASKS`, `v2/model_lab/serving.py` |
| Feature set | `ALL_84`, `FEATURE_SET_VERSION="v8"`, registry-sorted order | `v2/features/registry.py`, `v2/experiments/feature_sets.py: resolve_feature_set("ALL_84")` |
| Estimator | `LogisticRegression` C=0.01, lbfgs, max_iter=1000, class_weight=None, random_state=42 | `v2/model_lab/serving.py: EXPECTED_ESTIMATOR_PARAMS` |
| Calibration / semantics | `RAW`, `BINARY_PROBABILITY` / `INDEPENDENT_BINARY` (never normalized) | `serving.py`, P3.1 handoff report |
| Training / holdout | 2018–2024 (149 races, 162728 eligible) / 2025 protected, consumed once, mechanically sealed | `docs/MODEL_LAB_P31_HANDOFF_REPORT.md` |
| State grain | 189,420 D9 rows, `(race_id, driver_id, lap_number)` PK + `state_time_s` clock | `v2/features/build_matrix.py: load_states` |
| Roster universe | 3,458 race-drivers (results identity); 3,452 with states; 6 zero-state entrants | `docs/PHASE2_TEMPORAL_SEMANTICS.md` §6 |
| Serving artifact | `results/v2_model_lab/winner_logreg_raw_v1_serving.joblib`, sha `1116b34f…`, transformed dim 106, spec fp `3164de9e…` | P3.1 handoff report |
| Matrix content hash | `d2ee966c…` | P3.1 handoff report |

Full 84-name ordered list: `v2/experiments/feature_sets.py :: canonical_predictive_names()`
(manifest `predictive_columns`). Do NOT hand-copy it into Phase-4 code; resolve at runtime.

Absolute boundaries (R0 confirms none are needed): no retrain/recalibration/ALL_84 change/
reorder, no preprocessing change, no 2025 target access, no M9 rerun, no probability
renormalization, no Phase-1/2 semantic change.

---

## 2. Existing architecture findings

### 2.1 Temporal engine (`v2/features/temporal.py`, ~362 lines — REUSE)

- `driver_prefix(states, race_id, driver_id, T)` → rows with `state_time_s <= T`, ordered
  `(state_time_s, lap_number, driver_id)`. Empty when unobservable. Source never mutated.
- `latest_at_or_before(frame, time_col, T)` → latest row `<= T`, deterministic tie-break
  `(lap_number, driver_id)`. No fall-forward.
- `synchronized_driver_state(states, race_id, rival_id, T)` → `SyncState`
  (`observable, race_id, driver_id, observed_lap, observed_time_s, observation_age_s, values`).
  Stale stays observable with provenance; no prior state → `observable=False`, all nulls.
- `resolve_target(states, race_id, driver_id, lap_number, T)` → EXACT row match on all four
  fields; `TargetNotFoundError` on miss, `TemporalError` on duplicate key. No nearest-timestamp
  substitution.
- `synchronized_field_snapshot(states, race_id, driver_id, lap_number, T, roster)` →
  `FieldSnapshot(race_id, driver_id, lap_number, state_time_s, target_values, entries)` with
  entries ordered by `driver_id` (never final position), six zero-state entrants kept as explicit
  unobservable entries.
- `RaceIndex` — immutable per-(race, driver) sorted index; `sync_lookup` (binary search,
  tie-scan to end of equal-time group) and `field_snapshot` with IDENTICAL contracts to the
  module functions. Recommended serving path (F1 §21 measured 4.2 s whole-scope naive pass).
- `extract_roster(results_like)` → identity-only `{race_id: sorted driver_ids}` from
  `(race_id, driver_id)` columns; outcome-mutation-tested.
- `within_stint_prefix` (start-side only; `end_lap` present-but-ignored), `past_races_before`
  (canonical `(season, round_no)` order), `rolling_past_observations` (caller-owned mask).
- `observation_age_s(T, observed)` — provenance only, never a race gap (F1 §11).

### 2.2 Feature registry + engine (`v2/features/` — REUSE)

- `registry.py`: `FEATURE_SET_VERSION="v8"`, 84 predictive defs; `validate_definition` enforces
  label-guard (`label_outcome_fields()` from D9 LABEL_FIELDS + results label columns +
  `CANONICAL_LABEL_NAMES`), cross-driver sync declarations, TARGET_STATE-vs-PAST_RACES source rules.
- `engine.py`: `features_for_state(request, registry, states, names, history)` — per-family
  dispatch (passthrough F4 / pace F5 / gap F6 / context F7 / rates F8 / environment F9 /
  priors F10 +history / interactions F11), merged in registry order; `features_for_batch` =
  same path per request (parity contract §18, `results_equal` with 1e-9/1e-12 tolerances).
  `FeatureRequest(race_id, driver_id, lap_number, state_time_s)` carries NO labels.
- `build_matrix.py`: `compute_family_frames` (batch DAG: passthrough/pace/gap/environment/
  context/rates/priors → interactions over merged prims), `assemble_matrix`, `IDENTITY_COLUMNS`,
  `TASKS`, `CANONICAL_SORT`. Canonical matrix loader: `load_matrix / load_features / load_task`.
- `contracts.py`: `TemporalRule` (no same-lap variant — inexpressible by design),
  `SyncRequirement`, `MissingPolicy`, `FeatureFamily` (18 families), `CROSS_DRIVER_FAMILIES`.
- F16 (`v2/experiments/feature_sets.py`): `ALL_84` == registry order; group partition
  STATE/PACE/GAPS/FIELD_CONTEXT/RATES_MOMENTUM/ENVIRONMENT_HISTORY/PRE_RACE_PRIORS/INTERACTIONS.

### 2.3 Labels (`v2/labels/` — DO NOT IMPORT into Phase-4 serving path)

- 7 targets, `LABEL_SET_VERSION="v1"`, grain `(race_id, driver_id)`; state-dependent formulas
  (`position_change_from_state`, gains/loses) SPECIFIED here, materialized only in F15.
- `CANONICAL_LABEL_NAMES` imported by the feature registry as name-guard metadata only.
  Phase-4 prediction code must never import builder values; tests pin that calculators don't.

### 2.4 Serving (`v2/model_lab/serving.py` — REUSE, only production path)

- `load_frozen_winner_model(path=None)` → validates envelope/format/task/feature-set/RAW/
  semantics/84 ordered names+hash/dim-106/estimator class + recorded AND live params/training
  seasons/preprocessor agreement/coef shapes; raises `ServingArtifactError` on anything else.
- `FrozenWinnerPredictor.predict_proba(frame)` — batch, exact-84-ordered-columns DataFrame,
  row identity/order preserved, finite + [0,1] checked, independent per-driver output.
- Module import pulls no runner/tuning/holdout machinery (pinned by P3.1 test).
- Preprocessing: `FittedPreprocessor` (median+StandardScaler numeric / mode bool /
  `"MISSING"`+one-hot-unknown-ignore categoricals); `FORBIDDEN_*` guards reject labels/masks/identity.

### 2.5 API (`api/` — EXTEND under new namespace)

- `api/main.py`: app + CORS only. `api/routes.py`: 4 legacy routes
  (`GET /health`, `GET /races`, `POST /predict/ensemble`, `POST /predict/single-model`).
  `api/schemas.py`: `RaceRequest{year, event}`, `SingleModelRequest{+model}`.
  `api/services/prediction_service.py`: thin delegation to `ml/inference.py`.
- Baseline pinned by `tests/test_api_baseline.py` (104 races 2019–2023, checkpoints 5/10/15/20/25,
  15-row ensemble summary, known Monaco-2022 NaN passthrough preserved).

### 2.6 Legacy (`ml/` — DO NOT ROUTE V2 THROUGH)

- `ml/inference.py`: CSV datasets per lap, `FEATURE_COLS`, pickled per-(model, lap) estimators,
  majority-vote ensemble + XGBoost tie-break/confidence, `year`+`event_name` keys, actual-winner
  disclosure in responses. Entirely separate data/model universe from v2.

### 2.7 Frontend / tests

- `frontend/` (Next.js, `app/page.tsx`): consumes the 4 legacy routes. Phase 4 adds no UI.
- `tests/`: per-stage suites (`test_v2_features_f2…f15`, `test_v2_labels_f13`,
  `test_v2_model_lab_m0…m9/p31`, `test_api_baseline.py`, …). P3.1 medium gate: 475 passed.

---

## 3. Canonical temporal semantics

Authoritative: `docs/PHASE2_TEMPORAL_SEMANTICS.md` + `v2/features/temporal.py` (executable form).

- Target state `S = (race_id, driver_id, lap_number, state_time_s=T)`; `state_time_s` is the
  LAP_END clock; knowledge boundary = all information observable at or before T per each field's
  Phase-1 availability class (§8: POST_RACE/LABEL_ONLY never predictive; SOURCE_METADATA
  non-predictive; PRE_RACE constants; LAP_START/IN_LAP/LAP_END eligible inside `<= T` states).
- `lap_number` is per-driver descriptive progress, NOT a global clock. Equal lap numbers are
  never treated as simultaneous (same-lap spreads to 121 s dry / 1320 s red).
- Rival sync: latest rival row `<= T`, deterministic ties, no fall-forward, no same-lap
  preference, no retirement inference. Stale persists with age provenance; no global staleness
  cutoff (p50 rival age 48.2 s; retirees dominate the tail — correct, not missing).
- Running status unknowable exactly at T (retirement is future-absence; classification evidence
  is LABEL_ONLY). Four observable tiers only: roster member / synced at T / stale at T (reason
  unknown) / never observable (six zero-state entrants).
- Gaps: seconds separation valid ONLY under green, comparable laps, no suspension; otherwise
  validity=false + lapdiff + provenance (F8 gap structs already encode this).
- `observation_age_s` ≠ race gap. `lap_difference` ≠ ahead/behind. Progress =
  `race_leader_laps_at_state` ÷ PRE_RACE scheduled distance (never eventual total).
- Partial / red-flag / SC / VSC / time-limited races: same rule, validity companions do the work.
- Identity keys `(race_id, driver_id)` only (Ergast slugs); never driver_number/abbreviation/team.
- Roster: D5 `results` identity columns only (documented pre-race-fact justification, §6).
- Ordering: `(state_time_s, lap_number, driver_id)`; never input row order.

REUSE, don't reimplement: `RaceIndex`, `resolve_target`, `synchronized_driver_state`,
`synchronized_field_snapshot`, `extract_roster`, `driver_prefix`, `within_stint_prefix`,
`past_races_before`, `FeatureRequest/FeatureResult`, `results_equal`.

---

## 4. Canonical Time-T contract

**Selected: anchor-observation snapshot key** (narrowest contract consistent with frozen semantics).

- Exact input: `(race_id, anchor_driver_id, anchor_lap_number, anchor_state_time_s)`.
  All four required; types `str, str, int, float`.
- Resolution algorithm:
  1. `RaceIndex.field_snapshot(race_id, anchor_driver_id, anchor_lap_number, T=anchor_state_time_s, roster)`
     with roster = `extract_roster` output for the race (union anchor id).
  2. `resolve_target` enforces the anchor is an exact D9 row; `T := anchor state_time_s`.
  3. Every other roster member resolves via `sync_lookup(race_id, member, T)` → observable with
     `(observed_lap, observed_time_s, observation_age_s)` or explicit unobservable.
- `state_time_s` (T) = the anchor's LAP_END clock; the knowledge boundary for the whole snapshot.
- Lap representation under divergence: NO single "race lap". The snapshot carries `anchor_lap`
  plus per-driver `observed_lap`; lap-difference is per-driver factual index data, never a global clock.
- Requested state missing → `TargetNotFoundError` → API 422 (never nearest substitution, never
  silent rounding of T).
- Arbitrary wall-clock T: DEFERRED. Phase 4 requires T to equal an exact D9 `state_time_s`
  for the anchor driver. Rationale: frozen `resolve_target` forbids nearest substitution; inventing
  interpolation would be a new temporal definition. Revisit in Phase 5 only with explicit semantics.
- Why this shape: it reuses the frozen `FieldSnapshot` verbatim (target + per-member sync +
  driver_id ordering + zero-state handling), yields a synchronized RACE snapshot by construction
  (all rivals `<= T`, no future rows), and maps 1:1 onto `FeatureRequest` per observable driver.

---

## 5. RaceState domain contract

Minimal classes (no proliferation). ML-free: no feature names, no estimator, no probabilities.

```
RaceState
  race_id: str                    factual, PK part — D9 race_id
  anchor_driver_id: str           factual, which D9 row anchored T — request
  anchor_lap_number: int          factual — request (per-driver progress, §3)
  state_time_s: float (T)         factual clock — anchor D9 state_time_s
  roster_size: int                factual — len(entries)
  drivers: tuple[DriverRaceState] factual+derived — one per roster member, driver_id order
  race_context: RaceContext       factual — progress/leader-lap at T
  weather: WeatherState           factual as-of — BACKWARD_ASOF row
  race_control: RaceControlState  factual — target-row flags + as-of message
```

`DriverRaceState` (per roster member):

| field | type/nullable | meaning | source | factual/derived | availability at T |
|---|---|---|---|---|---|
| driver_id | str | Ergast slug | roster/D9 | factual | always |
| observable | bool | ≥1 state `<= T` | sync lookup | factual | always |
| observed_lap_number | int \| null | rival's own lap index | SyncState | factual | null iff unobservable |
| observed_time_s | float \| null | rival's own clock | SyncState | factual | null iff unobservable |
| observation_age_s | float \| null | T − observed | SyncState | derived past-only | null iff unobservable |
| position | int \| null | running order at observed row | D9 row | factual | null preserved (294 known nulls) |
| gap_to_leader_s / gap_to_ahead_s | float \| null + validity flags | seconds separation where valid | D9-derived gap state | factual+validity | null when invalid geometry / red / no sync |
| compound / tyre_life / fresh_tyre | str/int/bool \| null | current tyre | D9 row | factual | null preserved |
| stint_number / stint_lap / pit_stops_completed_so_far / laps_since_last_pit | int \| null | stint/pit facts | D9 row | factual | start-side only; end_lap never exposed |
| constructor_id / driver_number* | str/int \| null | presentation only | D9 row | factual | *number/abbreviation never key joins |

`RaceContext`: `race_leader_laps_at_state: int`, `race_progress_frac: float`,
`scheduled_laps: int | null` (PRE_RACE D5), `season/round_no/circuit_id: factual metadata`.
`WeatherState`: 7 `wx_*` values as-of (`BACKWARD_ASOF`, null-preserving) + `observation_age_s | null`.
`RaceControlState`: `track_state: str | null`, `flag_yellow/safety_car/vsc/red: bool | null`
(TARGET_STATE), plus as-of last-message category/flag/age (IN_LAP message fields, text optional).

Derived past-only state (kept OUT of `RaceState` core; computed in the bridge via frozen
calculators, not stored as domain facts): trailing pace windows, gap rates, relative/teammate/
field/traffic context, environment-history deltas, pre-race priors, interactions.

Label firewall — `RaceState` MUST NOT contain: `final_position`, `is_winner`, `is_podium`,
`scored_points`, `position_change_from_state`, `gains/loses_position_by_finish`,
`classified_flag/status/points/laps_completed`, `classified_position`, any eligibility mask,
future pit/weather/race-control, `end_lap`/eventual stint length, `driver_number`-keyed joins.
Enforcement: construct ONLY from D9 state columns + `extract_roster` identity columns;
`label_outcome_fields()` name-guard test on the domain module's imports.

Future consumers: Phase 5 replay (calls reconstruction per anchor), Phase 6 Monte Carlo +
Phase 7 strategy (consume domain state, not features), Phase 8 what-if (mutates domain fields),
Phase 9 explainability (pairs domain state with snapshot predictions), Phase 10 UI (renders
domain state directly without model dependency).

---

## 6. Feature bridge contract

**Architecture: `RaceState → FeatureRequest[] → frozen engine → ALL_84` (reuse, no second implementation).**

Exact reuse path for one snapshot at T (observable drivers only):

1. For each observable `DriverRaceState`, build
   `FeatureRequest(race_id, driver_id, observed_lap_number, observed_time_s)`.
   (Note: rival requests use their OWN observed lap/time, not the anchor's — this is the
   frozen per-state identity; the sync rule already bounded each to `<= T`.)
2. Single call: `features_for_batch(requests, build_f11_registry(), states, names=ALL_84_ORDER, history)`
   where `ALL_84_ORDER = resolve_feature_set("ALL_84", manifest)` (manifest order == registry
   order; validated equal by F16), `states` = frozen D9 frame (or per-race slice),
   `history = PriorHistory(...)` as built in `build_matrix.load_history`.
3. Result rows → DataFrame with EXACTLY `predictor.feature_names` column order
   (tuple-compare before inference; order comes from the artifact, not a copy).
4. Alternative accepted: `build_matrix.compute_family_frames` on the snapshot-row frame, ONLY if
   R3 proves byte-equality with (2) via `results_equal` on sampled anchors. Default is (2).

Functions/modules reused: `RaceIndex`, `extract_roster`, `FeatureRequest`,
`features_for_batch`/`features_for_state`, family `*_batch` calculators (transitively),
`build_f11_registry`, `PriorHistory`, `resolve_feature_set`, `results_equal`.

Impedance mismatches (all resolvable WITHOUT frozen-semantic change — no freeze conflict):
per-driver observed lap/time vs anchor T (resolved: request per observed identity);
`compute_family_frames` expects full-frame batch (resolved: use request-loop `features_for_batch`);
interactions need merged prims (resolved: inside engine path, not caller code);
nullable/boolean dtypes (resolved: engine emits registry dtypes; serving preprocessor imputes);
history bundle required for priors (resolved: caller supplies `PriorHistory`, raises
`NoCalculatorError` otherwise — surfaced as 503/500 per §11, never fabricated).

Forbidden: any new per-feature formula, any reordered/renamed column, any imputation before the
frozen preprocessor, any label/mask/identity column entering the frame.

---

## 7. Prediction domain contract

```text
PredictionSnapshot
  race_id: str
  anchor_driver_id: str
  anchor_lap_number: int
  state_time_s: float                     # resolved T (= anchor clock)
  observable_driver_count / roster_size: int
  model: ModelIdentity
    { task: "winner", target: "is_winner", mask: "eligible_is_winner",
      feature_set: "ALL_84", feature_set_version: "v8",
      calibration: "RAW", probability_semantics: "INDEPENDENT_BINARY",
      estimator: "LogisticRegression(C=0.01, lbfgs, max_iter=1000)",
      artifact_sha256, specification_fingerprint, sklearn_version,
      transformed_dim: 106 }
  probability_semantics_note: str         # fixed human-readable warning (below)
  predictions: tuple[DriverPrediction]    # driver_id order

DriverPrediction
  driver_id: str
  observable: bool
  observed_lap_number / observed_time_s / observation_age_s  (null iff unobservable)
  position: int | null                    # observable running order, NOT a prediction
  winner_probability: float | null        # null iff unobservable, with reason str
  unobservable_reason: str | null         # "no_state_at_or_before_T" | "zero_state_entrant"
```

Semantics (explicit, UI-proof): each `winner_probability` is `P(is_winner=1 | state)` from an
independent binary model; values MUST NOT be renormalized, MUST NOT be described as summing to 1,
MUST NOT be called a categorical race distribution, MUST NOT feed categorical log-loss.
The fixed note ships in every snapshot payload + API schema description, e.g.:
"Independent per-driver binary probabilities. They do not sum to 1 and are not a race-winner
distribution. Do not renormalize." Follow repo convention: frozen dataclasses with `to_dict()`
(`FeatureDef`/`LabelDef` pattern), sorted `driver_id` enumeration, `state_equal` weighting noted.

---

## 8. Batch inference contract

- Input: one `pd.DataFrame` with EXACTLY `predictor.feature_names` (84, artifact order).
  `predict_proba` tuple-compares columns; any deviation → `ServingArtifactError`.
- One batch per snapshot (all observable drivers, one call). Driver-by-driver inference forbidden
  (single-row accepted by the API only as a degenerate case, not the path).
- Identity alignment: caller keeps `request[i] ↔ row[i] ↔ proba[i]`; output row i IS input row i
  (predictor guarantees order preservation). Map back via positional index, never via
  `driver_number`/abbreviation.
- Unobservable members (stale-none, six zero-state entrants): EXCLUDED from the frame;
  emitted as `winner_probability: null` + reason. Never zero-filled, never imputed as a row.
- Zero-state entrants: permanent nulls (no future row can ever appear — §3).
- Errors: `ServingArtifactError` (schema mismatch, non-finite transform, non-finite/out-of-range
  proba, class-vector drift, missing/tampered artifact) — all explicit, no silent fallback estimator.

---

## 9. V2 API contract

Preserve all 4 legacy routes byte-identically. New explicit `v2` namespace (fresh router module,
e.g. `api/v2_routes.py` + `api/v2_schemas.py` + `api/services/race_state_service.py`; exact file
names fixed in R1).

| method/path | input | output | reads model | deterministic |
|---|---|---|---|---|
| `GET /v2/races` | — | `{races: [{race_id, season, round_no, circuit_id}]}` from frozen D5/results identity (NOT legacy CSV inventory) | no | yes |
| `GET /v2/races/{race_id}/states` | optional `driver_id` | `{race_id, anchor_states: [{driver_id, lap_number, state_time_s}], count}` — exact D9 anchors (paged if large) | no | yes |
| `GET /v2/races/{race_id}/state?driver_id=&lap_number=&state_time_s=` | anchor key (§4) | `RaceState` (§5), no labels, no probabilities | no | yes |
| `POST /v2/predictions/winner-snapshot` `{race_id, driver_id, lap_number, state_time_s}` | anchor key | `PredictionSnapshot` (§7) | yes | yes (same artifact → same bytes) |

No replay / WebSocket / Monte Carlo endpoints in Phase 4.

---

## 10. Legacy/v2 boundary

| | LEGACY V1 | V2 (Phase 4) |
|---|---|---|
| data | per-lap CSVs, `FEATURE_COLS` (`ml/features.py`) | frozen D9 states + canonical matrix lineage |
| models | per-(model, lap) pickles, XGBoost/HGB/logreg, tuned-or-base discovery | ONE tracked serving artifact, frozen LogReg |
| keys | `(year, event_name)` strings; checkpoints 5/10/15/20/25 | `(race_id, driver_id, lap_number, state_time_s)` slugs |
| logic | `ml/inference.py` majority-vote + XGB tie-break, actual-winner disclosure | independent binary proba, no voting, no outcome disclosure |
| routes | `/health /races /predict/ensemble /predict/single-model` | `/v2/*` (new router) |

Boundary rule: `api/v2_*` + v2 services import ONLY `v2.*` (`v2.model_lab.serving`,
`v2.features.*`, `v2.config`); NEVER `ml.*`. Legacy files untouched until a later phase
explicitly retires them. Pinned by an import-guard test (mirror of the P3.1 serving import test).

---

## 11. Error model

| domain error | HTTP | body |
|---|---|---|
| unknown `race_id` | 404 | `{error: "unknown_race", race_id}` |
| anchor not an exact D9 row | 422 | `{error: "unknown_state", hint: "list exact anchors via …/states"}` |
| malformed key (types/NaN/missing) | 422 (Pydantic) | validation detail |
| race with no observable driver at T / unsupported partial | 422 | `{error: "no_observable_state", ...}` |
| serving artifact missing/invalid | 503 | `{error: "model_unavailable"}` (no path leak) |
| feature-frame contract violation (internal) | 500 + alert | `{error: "internal"}` (cannot happen on valid anchors; indicates freeze drift) |
| legacy unknown-race ValueError path | unchanged (R0 characterizes; R5 decides mapping, default: keep legacy bytes) |

Rule: ordinary domain errors NEVER become 500. 500 reserved for genuine internal breakage.

---

## 12. Temporal leakage threat model

Per-snapshot adversarial checks (each: mutate future, recompute, assert identical):

1. Rival future same-lap row (Bahrain-121 s hazard) / later-lap row / future timing mutation /
   future-row deletion / source row reorder — `SyncState` + snapshot + features unchanged.
2. Future weather / race-control / pit rows — snapshot weather/RC/pit facts unchanged.
3. Label join — `RaceState` builders import no label values; `CANONICAL_LABEL_NAMES` name-guard.
4. Stale-rival use — ages carried, no cutoff silently dropping retirees; gap validity companions.
5. Same-timestamp ties (67 cross-driver groups; 2021-r08 stroll duplicate) — deterministic order.
6. Zero-state entrants — permanent explicit nulls, never dropped, never fabricated.
7. Partial/shortened (2021-r12, 2022-r18, Belgium-2021, Japan-2022) — same rule, thin histories.
8. Red-flag suspension — sync resolves, seconds-gap validity=false.
9. Presentation-identifier mutation (number/abbrev/team) — selection identical.
10. 2025 firewall — Phase-4 code paths never reference holdout seasons; regression test asserts no
    `2025`/holdout-target access in new modules (static import + content guard).

---

## 13. Performance measurement plan

Descriptive benchmarks first; NO pass/fail gates in Phase 4 (no product requirement justifies
invented thresholds). Method: real execution on the frozen D9 scope, warmed `RaceIndex` +
preloaded artifact, per-race sampling across dry/wet/SC/red/partial strata; report p50/p95/p99
+ N + machine/python/sklearn versions:

- state reconstruction (anchor → `RaceState`): target ~ms scale (index binary search; F1 §21:
  4.2 s whole 3.6M-pair naive scope ⇒ per-snapshot budget trivially small).
- feature bridge (field → ALL_84 frame): dominant cost; measure per-driver-feature latency and
  per-snapshot totals at field sizes 18–20.
- frozen batch inference (`predict_proba` on ~20×84 → 106): expected sub-ms–ms; measure.
- end-to-end snapshot (HTTP `POST …/winner-snapshot`): measure + break down by stage.
- memory: resident delta of loaded D9 slice + `PriorHistory` + artifact (informational).

Persist results to `docs/PHASE4_PERFORMANCE.md` (R6), never as gates in code.

---

## 14. Test strategy

- UNIT (`tests/test_v2_phase4_*.py`, new): domain invariants (no-label fields, ordering,
  serialization round-trip); anchor resolution (exact-match, miss→raise, duplicate→raise);
  sync (stale provenance, tie determinism, zero-state nulls); snapshot semantics text present;
  batch alignment (positional identity); finite [0,1]; determinism (same anchor twice → equal).
- TEMPORAL/ADVERSARIAL: §12 ten-case mutation harness (future-row add/delete/mutate/reorder;
  weather/RC/pit futures; ties; partial; red; identifier mutation); finished-status leakage
  (final/classified/points absent); 2025-content guard.
- FEATURE BRIDGE: requested names == artifact `feature_names` tuple-exact; sampled anchors
  `results_equal(engine_batch, F15 matrix row)`; determinism; no second-formula (import guard:
  bridge imports calculators, defines none).
- PREDICTION: null-probability for unobservables (never 0.0); no renormalization
  (`sum != 1` tolerated, never asserted); artifact tamper → `ServingArtifactError`;
  missing artifact → 503 path.
- API: valid state/snapshot golden shape; 404/422/503 matrix; malformed → 422; legacy 4 routes
  byte-identical (existing baseline suite untouched).
- REGRESSION: Phase-2 parquet/manifest/ablation hashes, M0–M9 artifacts, holdout sha
  `2c3a166d…` unchanged; protocol/ablation contract tests still green. No 2025 target read
  anywhere (seal test extended to new modules).

---

## 15. R1–R7 implementation plan

**R1 — RaceState domain model** — Objective: frozen dataclasses (§5) + constructors from
`FieldSnapshot`/`SyncState`, no model/feature imports. Files: new `v2/race_state.py`
(or `v2/race_state/` package — R1 decides, single module preferred) + `tests/test_v2_phase4_r1.py`.
Reuse: `temporal.SyncState/FieldSnapshot`, `d9schema` availability metadata. Tests: unit domain
invariants + label-firewall. Gate: FAST (unit only). STOP: any field needs a frozen-semantic
change ⇒ freeze conflict. Complexity: LOW.

**R2 — Historical state reconstruction** — Objective: anchor-key → `RaceState` service over a
loaded D9 slice + `RaceIndex` + `extract_roster`. Files: `v2/race_state.py` (loader/resolver) or
new `v2/race_history.py`; reuse `RaceIndex.field_snapshot`, `extract_roster`, `V2Paths`.
Tests: resolution/adversarial sync cases (§12 subset) + roster identity. Gate: MEDIUM (needs
`data/v2` artifacts). Depends: R1. STOP: arbitrary-T interpolation requested ⇒ defer to Phase 5.
Complexity: MEDIUM.

**R3 — RaceState → ALL_84 bridge** — Objective: §6 path (`FeatureRequest[]` → `features_for_batch`
→ ordered frame) + tuple-exact order check vs artifact. Files: new `v2/race_features.py`;
reuse engine/registry/F16/`PriorHistory`. Tests: order/parity/determinism + no-second-formula
guard. Gate: MEDIUM. Depends: R1–R2. STOP: parity mismatch vs F15 ⇒ halt, diagnose (likely caller
bug, NOT a license to alter frozen code). Complexity: MEDIUM.

**R4 — Frozen batch prediction engine** — Objective: `RaceState` + frame → `PredictionSnapshot`
via `load_frozen_winner_model` singleton + `predict_proba`; unobservable→null mapping; semantics
note. Files: new `v2/race_predict.py`; reuse `serving.py` only. Tests: alignment/semantics/
determinism/artifact-error paths. Gate: MEDIUM. Depends: R1–R3. STOP: any retrain/recalibration
temptation ⇒ freeze conflict. Complexity: LOW.

**R5 — V2 API** — Objective: §9 routes + §11 error mapping; legacy untouched. Files: new
`api/v2_routes.py`, `api/v2_schemas.py`, `api/services/race_state_service.py`; wire router in
`api/main.py` (additive one-liner). Tests: API matrix + legacy baseline green. Gate: FAST.
Depends: R1–R4. STOP: legacy behavior change required ⇒ explicit decision, default no.
Complexity: MEDIUM.

**R6 — Integration/adversarial/performance verification** — Objective: full §12 harness + §13
benchmarks (`docs/PHASE4_PERFORMANCE.md`) + regression hashes. Gate: FULL (medium P3.1 gate +
new suites; full `pytest tests/` only if cheap gates green per AGENTS.md fast-gates-first).
Depends: R1–R5. STOP: leakage found ⇒ fix Phase-4 code, never frozen code. Complexity: MEDIUM.

**R7 — Phase-4 freeze** — Objective: seal report (`docs/PHASE4_FREEZE_REPORT.md`), hash table,
readiness for Phase 5. No commit/tag unless repo workflow requires ( überseal pattern: follow
P3.1 precedent only on instruction). Gate: FULL verification review. Depends: R6 green.
Complexity: LOW.

---

## 16. Risks / open questions

1. D9-slice loading shape for serving (full 189k frame vs per-race parquet lazy load) — R2
   measures; default per-race lazy + cached `RaceIndex`.
2. `/v2/races` source of truth (D5 results identity vs matrix metadata) — R5 decides; must be
   identity-only either way.
3. `/states` pagination for 20-driver × ~60-lap listings — R5 decides; anchors are bounded (~1k/race).
4. `PriorHistory` load cost per snapshot (5 history globs) — cache once at startup; measure in R6.
5. Preprocessing `MISSING`-sentinel vs bridge nulls — already handled inside frozen preprocessor;
   bridge passes nulls through, never pre-imputes.
6. Frontend keeps legacy routes — no Phase-4 UI work; v2 payload conventions documented for Phase 10.

---

## 17. Scientific freeze conflicts

NONE. Every Phase-4 need maps onto frozen machinery without semantic change (§§4–6, 15 STOP
conditions guard each stage). If implementation reveals otherwise, STOP and report
`SCIENTIFIC FREEZE CONFLICT` per the R0 brief.

---

## 18. R0 readiness decision

**R0 COMPLETE — READY FOR R1.** Contracts defined, reuse paths identified, no frozen change
required, no 2025 access, no code touched. R1 may proceed with `v2/race_state.py` domain model.

---

## 19. R1 implementation record (2026-09-17, R1 COMPLETE — READY FOR R2)

Status: domain-only stage implemented; no frozen Phase-1/2/3 file modified
(`git status` shows only the two new R1 files plus this plan note as new).

Actual domain types (`v2/race_state.py`, stdlib-only + `TRACK_STATE_TOKENS`
from frozen `v2.d9schema`; no pandas/numpy/sklearn/FastAPI/`v2.model_lab`/
`ml.*`/API/label-value imports — pinned by an isolated-interpreter test):

- `AnchorObservation{race_id, anchor_driver_id, anchor_lap_number,
  anchor_state_time_s}` — requested-key identity; finite/exact-type
  validation; no resolution logic.
- `DriverRaceState` — one entry per roster member with `observable` flag;
  per-R0 §5 field set (position, gap seconds + validity companions +
  gap lap-differences, tyre/stint/pit-so-far facts, presentation-only
  `constructor_id`/`driver_number`); `unobserved()` factory for
  null-only entries; unobservable members with any state value rejected.
- `RaceContext{race_leader_laps_at_state, race_progress_frac,
  scheduled_laps, season, round_no, circuit_id}` (all nullable).
- `WeatherState` — 7 as-of values + `observed_at_s`/`observation_age_s`
  lineage anchors (age kept because R1-H requires inspectable staleness).
- `RaceControlState` — D9-exact flag names (`flag_yellow`,
  `flag_safety_car`, `flag_red`, `flag_vsc`) + `track_state` token
  (validated against `TRACK_STATE_TOKENS`) + last-message
  category/flag/age; message text excluded per "text optional".
- `RaceState` — snapshot root; drivers normalized to `driver_id` order,
  duplicates rejected, anchor membership/observability/lap/time pinned,
  `observed_time <= T` + age-consistency enforced; `roster_size`,
  `roster/observable/unobservable_driver_ids` derived properties.
- Errors: `RaceStateError(ValueError)` / `InvalidRaceStateError`; no HTTP.
- `label_outcome_fields()` — domain firewall name set (7 canonical target
  names restated as literals + D9 label facts + eligibility masks +
  `end_lap`/`dnf_flag`/`dnf`); `domain_field_names()` allow-list pinned
  exactly by test. Cross-checked equal to `CANONICAL_LABEL_NAMES` in test
  (test-only import; domain never imports label values).
- `to_dict()` on every type: deterministic key order, JSON primitives,
  explicit None, finite-validated at construction, exact-type guards
  reject numpy/pandas scalars structurally (incl. `numpy.float64`, which
  subclasses Python `float`).

Non-scientific clarifications discovered during implementation (no R0
semantic change):

1. Gap fields live on `DriverRaceState` as nullable domain slots filled by
   R2 from the frozen F6 calculators (gaps are not D9 state columns);
   seconds values require no validity-true precondition at construction —
   `None` + explicit `False`/`None` validity is the red/invalid encoding.
2. `DriverRaceState` carries no `race_id`: same-race membership is
   structural (R2 builds all entries for the snapshot race), so the R1-K
   "anchor belongs to the same race" invariant is enforced as anchor roster
   membership, never via presentation-attribute joins.
3. Zero-state vs pre-first-observation unobservables are intentionally
   indistinguishable at a single snapshot; both use `observable=False` +
   full nulls, and R4 assigns the reason (`no_state_at_or_before_T` |
   `zero_state_entrant`) from history.
4. `driver_field_provenance()` tags every `DriverRaceState` field
   `factual_observed` (default) or `derived_past_only`
   (`observation_age_s`, gap validity flags, `stint_lap`,
   `pit_stops_completed_so_far`, `laps_since_last_pit_stop`).

Tests: `tests/test_v2_phase4_r1.py` — 37 synthetic tests, all green, plus
FAST gate green (`test_v2_features_f3` + `test_v2_labels_f13`: 58 passed;
`py_compile` clean). No scientific freeze conflict. R2 NOT started.

---

## 20. R2 implementation record (2026-09-17, R2 COMPLETE — READY FOR R3)

Status: deterministic historical reconstruction implemented; no frozen
Phase-1/2/3 file modified; no 2025 access; serving artifact sha re-verified
`1116b34f…` (unchanged).

Actual interface (`v2/race_state_reconstruction.py`):

- `RaceStateReconstructor(states, roster, race_meta=None)` — immutable,
  reusable; builds one frozen `RaceIndex`. `reconstruct(anchor) ->
  RaceState`. One-shot helper `reconstruct_race_state(...)` for single use.
- Errors: `RaceStateReconstructionError(RaceStateError)` /
  `AnchorNotFoundError` (carries race/driver/lap/T) / `RaceNotFoundError`
  (carries race_id); no HTTP codes.
- Data-loading boundary (R0 open question 1 resolved): dependency
  injection of an in-memory D9-shaped frame + roster mapping (or
  results-like frame via `extract_roster`) + optional `race_meta`
  (PRE_RACE D5 `races` rows; only `scheduled_laps` consumed). No new
  storage, no DB/Redis, no caches. Serving default: per-race D9 slice +
  cached reconstructor; `build_matrix.load_states` remains the full-scope
  canonical loader.
- Exact anchor behavior: `RaceIndex.field_snapshot` (exact 4-key match);
  `TargetNotFoundError` → `AnchorNotFoundError`; unknown race →
  `RaceNotFoundError`. No nearest substitution (parametrized miss tests at
  ±1e-4 s and off-by-one lap).
- Synchronization reuse: `RaceIndex` is the sole authority (field snapshot
  for observed_* provenance; per-member `sync_lookup` at each member's own
  observed time for gap geometry). No DataFrame-filter/groupby/merge_asof
  reimplementation.
- Coercion policy: single `_coerce(value, kind, field)` boundary helper
  (numpy int/float/bool → plain; pandas NA/NaN/None → None on nullable
  fields; Inf raises `RaceStateReconstructionError`, never silent None;
  strings verbatim). R1 strict validation untouched.
- Gap source: frozen F6 `gaps_for_snapshot` per observable member at its
  OWN observed time (sync at that clock, ages ≥ 0 by construction); anchor
  coincides with the snapshot-T evaluation. Validity mirrors frozen
  `_gap_feature_values` tri-state exactly (None iff reference unknown;
  leader-no-ahead → False). Rationale recorded: evaluating stale members
  at anchor T would conflate observation age with race gap (F1 §11).
- Weather/RC/pit source: anchor observed row's past-safe D9/D7 as-of
  block (`wx_*`+`wx_age_s`; D9 track-state flags + `rc_last_message_*`);
  per-member start-side stint facts + D9 completed-so-far counts.
  `end_lap` and any extra/unknown columns are ignored by the allowlist
  projection (tested).
- Zero-state behavior: roster preserved (union anchor); zero-state and
  pre-first-observation members → `DriverRaceState.unobserved` full nulls.
- Corrections found during implementation (no R0 semantic change):
  `total_laps_scheduled` is NOT a D9 state column (race-grain quality
  table) — hence the `race_meta` injection path; `scheduled_laps` stays
  nullable per contract.

Tests: `tests/test_v2_phase4_r2.py` — 39 tests green (exactness, sync,
staleness, roster/zero-state, coercion incl. numpy/NA/Inf, ordering +
shuffle determinism, 11-case future-mutation harness, label/status
firewalls, red-flag/partial, F6 parity vs both `gap_for_state` and
`gap_batch`, import/source architecture guards, 3 canonical smoke tests).

Canonical smoke (2021/2022 only, read-only): Belgium 2021-r12-R partial
(roster 20, observable 1 at first anchor, 7.6 ms), Japan 2022-r18-R red
(20/3, 17.6 ms), Monaco 2022-r07-R (20/1, 7.3 ms); mid-race Monaco anchor
(russell lap 31: 20/20 observable, 44.6 ms incl. index build,
`scheduled_laps=77`, serialize-ok). No scientific freeze conflict.
R3 NOT started.

---

## 21. R3 implementation record (2026-09-17, R3 COMPLETE — READY FOR R4)

Status: RaceState → frozen ALL_84 bridge implemented; no frozen
Phase-1/2/3 file modified; model never loaded or run; no 2025 access;
serving artifact sha re-verified `1116b34f…` (unchanged).

Public API (`v2/race_state_features.py`):

- `RaceStateFeatureBridge(states, history, registry=None)` — reusable
  (one bridge serves many snapshots; NOT one per driver). `history` is a
  frozen `PriorHistory` injected once and reused read-only across calls
  (behaviorally identical to per-call passing; engine never mutates it).
- `requests_for(race_state) -> list[FeatureRequest]` — observable-only
  requests with each driver's OWN `(observed_lap, observed_time_s)`
  (stale rivals keep `(lap39, 2960)`, never `(anchor_lap, T)`), exact
  corpus resolution (anchor + every request via `resolve_target`, miss →
  `RaceStateFeatureMismatchError`, never nearest-matched).
- `features_for_state(race_state) -> FeatureBatch` — ONE
  `features_for_batch` call; frame columns exactly the resolved ALL_84
  order; `FeatureIdentity` per row with positional
  `identities[i] ↔ features.iloc[i]` alignment (driver_id order, default
  RangeIndex, no labels/identity/metadata columns in the frame).
- Errors: `RaceStateFeatureError(RaceStateError)` /
  `RaceStateFeatureMismatchError` (structured detail, no HTTP, no
  sklearn leakage).
- `FeatureBatch{race_id, anchor_*, identities, features, feature_names}`
  + `FeatureIdentity{race_id, driver_id, observed_lap_number,
  observed_time_s}` (both frozen dataclasses with `to_dict` on identity).

ALL_84 authority: `resolve_feature_set("ALL_84")` over
`build_f11_registry()` (no hand list); validated count == 84,
`FEATURE_SET_VERSION == "v8"`, order == `canonical_predictive_names`.
Artifact order == this order by the frozen serving invariant (final-fit
`model._feature_names == DATA.resolve_features("ALL_84")` check); the
bridge deliberately does NOT load the artifact — R4 tuple-compares
`batch.feature_names` against `predictor.feature_names` before inference
(R0 §6 step 3). No `predict_proba` call anywhere in R3 (guarded).

RaceState-is-not-source-of-truth: the bridge reads identities/clocks from
RaceState only; all 84 values come from the canonical corpus + RaceIndex
+ PriorHistory through the frozen engine. No pace/rank/momentum/prior/
interaction recomputation (source-guard test).

Parity fixtures (dev only) + results:

- 2022-r07-R norris lap30 (ordinary/stale), 2021-r12-R hamilton lap2
  (partial), 2022-r18-R ocon lap2 (red), 2023-r01-R alonso lap28 (full
  field). Direct `features_for_batch` oracle: 20 rows × 84 cols each,
  max abs diff **0.0** on all four. Frozen matrix rows (F15 idiom, 1680
  cells each): max abs diff **0.0** on all four, null patterns equal
  (matrix `pd.NA` ≡ bridge `None`). Per-family subsets (≥7 families:
  pace/gap/context/rate/environment/prior/interaction) green.
- Stale-driver case: rivals with age > 0 requested at own identity;
  equals direct evaluation at that identity (fails if T were used).
- Same-lap future hazard: injected same-lap +1 s rival row leaves the
  84-col frame byte-identical (`assert_frame_equal`).
- 7-case future-mutation harness (driver/weather/RC/pit/label/status/
  unrelated race) green; determinism + source-shuffle green; firewall
  (frame cols == ALL_84, ∩ `label_outcome_fields()` == ∅) green.

Performance observation (descriptive, no gate): 2023-r01-R alonso-28
(20 drivers) — request construction 9.3 ms, end-to-end 12.0 s
(~600 ms/driver engine evaluation, history warm and reused). Cold
`load_history` cost is one-time per process; no caching added (R6
measures properly). Semantics untouched for speed.

Import-boundary note: importing the frozen F16 authority transitively
loads the `v2.labels` package `__init__` (which imports builder) — a
frozen package-init side effect also present inside Phase-2 itself. The
R3 guard asserts the bridge module holds NO reference to anything
defined in `v2.labels.builder` (value coupling would fail), plus no
`v2.model_lab`/`ml.*`/`api.*`/sklearn/scipy/fastapi at runtime.

Tests: `tests/test_v2_phase4_r3.py` — 37 tests green. MEDIUM gate (R1 +
R2 + R3 + F15 + F16 + P3.1 serving contracts) green; F3/F5/F6/F7/F9/D7/
F13/F14 results reused from the R2 gate (no frozen change since).
No scientific freeze conflict. R4 NOT started.

---

## 22. R4 implementation record (2026-09-17, R4 COMPLETE — READY FOR R5)

Status: production prediction domain + frozen batch engine implemented;
first Phase-4 stage to execute the frozen model, via the narrow P3.1
serving path only. No frozen Phase-1/2/3 file modified (only two new
files: `v2/prediction.py`, `tests/test_v2_phase4_r4.py`); no 2025
access; serving artifact sha re-verified
`1116b34fc716035c…` (full match); spec fingerprint `3164de9e…` verified.

Public API (`v2/prediction.py`, ~430 lines):

- Errors (`RaceStateError` subclasses, no HTTP, no sklearn leakage):
  `PredictionEngineError` / `PredictionFeatureMismatchError`
  (feature-order) / `PredictionAlignmentError` (identity) /
  `PredictionOutputError` (probability validity) /
  `ProductionModelUnavailableError` (serving failure, cause preserved).
- `ModelIdentity` — task/target/mask (`winner`/`is_winner`/
  `eligible_is_winner`), `ALL_84` + `v8`, `LogisticRegression` +
  recorded params, `RAW`, `INDEPENDENT_BINARY`, training seasons
  2018–2024, transformed dim 106, artifact SHA-256, spec fingerprint,
  sklearn version. Anchors read from frozen `serving.EXPECTED_*`
  constants (no hardcoded copies);
  `from_production_predictor()` fills SHA via
  `describe_serving_artifact`. Semantics mismatch rejected at
  construction; JSON-safe `to_dict()`.
- `DriverPrediction` — `driver_id`, `observable`, observed lap/time/age,
  `observed_position` (running order, not a prediction),
  `winner_probability` (float in [0,1] iff observable, else None —
  never 0.0), `unavailable_reason` (single factual reason
  `NO_OBSERVATION_AT_SNAPSHOT`; zero-state vs pre-first-observation
  deliberately not split per R1/R2). No ALL_84, no sklearn internals.
- `PredictionSnapshot` — race/anchor identity, T, model, predictions in
  `driver_id` order (never probability/position order), derived
  `roster_size`/`observable_count`/`unavailable_count`, explicit
  semantics + fixed do-not-renormalize note, `probability_by_driver()`,
  deterministic `to_dict()`.
- `RacePredictionEngine(feature_bridge, predictor, model_identity=None)`
  — DI-first; `predict(race_state)` runs the exact 12-step pipeline
  (validate → ONE `features_for_state` call → tuple-exact order check →
  ONE `predict_proba` call → length/finite/[0,1] validation →
  positional `identities[i] ↔ proba[i]` → roster merge → snapshot).
  Alignment rejects duplicates, unknown drivers, missing observable
  rows, and feature rows for unobservable members. Never clamps,
  coerces, normalizes, thresholds, or labels.
- `load_production_prediction_engine(states, history, ...)` — factory
  wiring `RaceStateFeatureBridge` + `load_frozen_winner_model`;
  data loading stays outside (caller passes D9 slice + PriorHistory).

Production smoke (dev only, smoke outputs — not quality metrics):

- 2023-r01-R alonso-28 (ordinary full-field 20/20) + 2021-r12-R
  hamilton-2 (partial edge): complete roster, observable finite [0,1],
  unobservable None + reason, identity/sha/fingerprint correct,
  deterministic repeat, JSON-safe, no normalization.
- Direct serving parity on alonso-28: R3 FeatureBatch →
  `FrozenWinnerPredictor` vs engine snapshot, max abs diff **0.0**.
- End-to-end future-mutation regression (future position + weather
  poisoned): identical snapshot dict.
- Sum-to-one non-invariant pinned both sides: [0.60, 0.35, 0.20] →
  sum 1.15 preserved exactly; [0.10, 0.05, 0.02] → sum < 1 preserved.

Performance observation (descriptive, no gate; 2023-r01-R alonso-28,
20 drivers): RaceState → FeatureBatch 12.18 s, batch model inference
8.2 ms, merge/domain negligible, full snapshot 12.14 s (repeat 12.15 s).
Inference is ~1500× cheaper than features; R3 feature generation
dominates end-to-end. No optimization in R4 (R6 decides).

Import boundary: `v2/prediction.py` imports only `v2.model_lab.serving`
from Model Lab (single sanctioned line, pinned); no `.fit(`, no
estimator construction, no `LogisticRegression(`/`joblib` reference.
Runtime probe mirrors the P3.1 list (runner/tuning/final_fit/run_final/
run_calibration/calibration_selection/model_runner + `ml.*`/`api.*`
absent); `serving`'s own transitive frozen-resolution pulls
(data/splits/experiments, incl. package-`__init__` side effects) are
documented as non-fitting and match the P3.1 serving-import precedent.

Tests: `tests/test_v2_phase4_r4.py` — 38 tests green (32 synthetic +
6 canonical). MEDIUM gate rerun in R4: R1+R2 76 passed, R3 37 passed,
R4 38 passed, P3.1 18 passed, F15+F16 81 passed; `py_compile` clean.
No scientific freeze conflict. R5 NOT started.

---

## 23. R5 implementation record (2026-09-17, R5 COMPLETE — READY FOR R6)

Status: versioned FastAPI boundary over the frozen pipeline; HTTP/API
integration only. No frozen Phase-1/2/3 file modified; legacy routes,
schemas, service, and `ml.inference` behavior untouched (only
`api/main.py` gains one additive `include_router` line).

New modules (dependency direction HTTP → service → v2 domain):

- `api/v2_schemas.py` — Pydantic responses (`V2RaceSummary`,
  `V2StateAnchor`/`V2StateListResponse`, `V2RaceStateResponse` +
  driver/context/weather/race-control parts, `V2ModelIdentityResponse`,
  `V2DriverPredictionResponse`, `V2PredictionSnapshotResponse`,
  `V2AnchorRequest`, `V2ErrorResponse`). Domain `to_dict()` unpacked
  into models; probabilities pass through verbatim (no share, no sum,
  no normalization field).
- `api/v2_service.py` — `V2Service` holding the read-only corpus (D9
  2018–2024, results roster, races meta) + `load_history` bundle + one
  reconstructor + one bridge + one frozen predictor + one engine.
  Process-local lazy singleton via `functools.lru_cache(maxsize=1)`
  (`get_v2_service`, overridable in tests). No Redis/DB/queues.
- `api/v2_routes.py` — `APIRouter(prefix="/v2")`: `GET /v2/races`
  (identity-only, `(season, round_no, race_id)` order), `GET
  /v2/races/{id}/states` (exact anchors, `(state_time_s, lap_number,
  driver_id)` order, `offset >= 0`, `limit` 1–500 default 100, with
  total/offset/limit), `GET /v2/races/{id}/state` (exact four-part
  anchor query, never nearest-matched/rounded), `POST
  /v2/predictions/winner-snapshot` (server owns reconstruction +
  features; callers submit anchors only, never feature vectors or
  probabilities).

Error mapping: unknown race → 404 `unknown_race`; anchor miss/bad
anchor → 422 `unknown_state` (+ states hint); artifact
missing/invalid → 503 `model_unavailable` with NO fallback (no legacy,
no checkpoint, no fake probs); feature/prediction contract violations
→ 500 `internal` (deviation from R5-L's 422 default, documented:
these cannot occur on valid anchors per R0 §11, so they indicate
freeze drift/server corruption); unexpected → 500 `internal`, never a
client error. Bodies are stable `{error, detail}` via `JSONResponse`
(FastAPI nests `HTTPException.detail`, so raising was unsuitable); no
stack traces, paths, or model internals.

2025 serving policy: development era only (`SERVED_SEASONS =
2018–2024`, `MAX_SERVED_SEASON = 2024`). R0 never authorized 2025
product inference and the holdout targets are sealed, so 2025 race_ids
are unknown (404). The service never loads label entities, the model
matrix, or evaluation artifacts (source-guard pinned); `PriorHistory`
may physically contain later rows but the frozen strictly-past
firewall keeps dev snapshots unaffected (R3).

Isolation: V2 modules import no `ml.*`/legacy service (pinned); legacy
`routes`/`schemas`/`prediction_service` import no `v2.*` (pinned).
CORS/auth/rate-limit unchanged per R5-V.

Integration (dev only, 2023-r01-R alonso-28): state 200 with full
roster + ordering + no label tokens; prediction 200 with
INDEPENDENT_BINARY, `artifact_sha256 1116b34f…`, deterministic repeat.
Timings (descriptive): service init ~3.9 s (corpus + history +
artifact, once per process); warm state request ~41 ms; full-corpus
prediction request ~82 s (vs ~12 s per-race-slice in R4 — larger-frame
feature evaluation; R6 input, NOT optimized). Repeated requests reuse
the singleton (no corpus/history/artifact reload; `maxsize=1` pinned).

Tests: `tests/test_v2_phase4_r5.py` — 49 tests green (46 fake-service
+ 3 real). MEDIUM gate: R1+R2 76, R3 37, R4 38, R5 49, API baseline
11, P3.1 18, F15+F16 81; OpenAPI paths verified (4 V2 + 4 legacy);
`py_compile` clean. No scientific freeze conflict. R6 NOT started.

---

## 24. R6 implementation record (2026-09-18, R6 COMPLETE — READY FOR R7)

Status: performance/adversarial/integration hardening. No frozen
Phase-1/2/3 file modified (only `v2/race_state_features.py` changed,
plus new `scripts/benchmark_phase4.py`, `tests/test_v2_phase4_r6.py`,
`docs/PHASE4_R6_HARDENING_REPORT.md`); no 2025 access; no retrain /
recalibration / renormalization. Full report:
`docs/PHASE4_R6_HARDENING_REPORT.md`.

Profile-then-optimize (fixtures: 2023-r01-R alonso-28 primary +
alonso-2 early, 2022-r07-R norris-30 stale, 2021-r12-R hamilton-2
partial, 2022-r18-R ocon-2 red; dev-only):

- Baseline: per-race slice 11.92 s vs full corpus 81.56 s features
  (6.8x). cProfile: ~9,500 `synchronized_driver_state` + ~1,400
  `driver_prefix` + ~700 `resolve_target` full-frame (162,728-row)
  boolean scans dominate; reconstruction (37 ms) and inference
  (7 ms) are corpus-size independent. Root cause: per-scan row width,
  not races/drivers/history size (all family calculators read only
  same-race `states` rows; priors read only the untouched history
  bundle).
- OPT-1 (kept): bridge evaluates the frozen engine over a lazily
  cached per-race slice (complete key `race_id`, read-only, bounded),
  history bundle untouched. 81.56 s -> 15.12 s.
- OPT-2 (kept): contiguous index on the cached slice (index carries no
  temporal semantics). 15.12 s -> 12.02 s; full/per-race ratio 1.0x.
- Each optimization independently parity-gated before keeping.

Parity (max abs diff **0.0**, null/identity mismatches 0 throughout):
slice vs full-frame oracle 4 anchors x 1,680 cells; post-opt bridge vs
frozen F15 matrix (red fixture) 1,680 cells; pre/post
PredictionSnapshot (same artifact, INDEPENDENT_BINARY, never
normalized). End-to-end same-lap future hazard: state/batch/snapshot
byte-identical.

Gates: `tests/test_v2_phase4_r6.py` 15 green; R1-R5 rerun 200 green;
Phase-2 F3/F5/F6/F7/F9/F13/F14/F15/F16 406 green; P3.1 18 green; FULL
suite **1540 passed, 4 xfailed** (pre-existing Monaco NaN legacy
xfails only); frontend lint 0 errors / typecheck clean / build ok;
D11 read-only 17/19 PASS (LEGACY/GIT fails are the expected
dirty-worktree hygiene signal for the sanctioned uncommitted R5/R6
additions - artifacts intact, baseline 11/11 green); all 10 frozen
hashes + holdout seal unchanged.

Final: warm state 39 ms, warm full-corpus prediction ~12.5 s end to
end (was ~82 s); memory 966 MB peak, +0.0 MB across repeated warm
predictions. Remaining debt (frozen 2x F11 recompute ~40%, dual
RaceIndex ~550 MB) documented for Phase 5 budgeting. No scientific
freeze conflict. R7 NOT started.

---

## 25. R7 implementation record (2026-09-19, PHASE 4 FROZEN — READY FOR PHASE 5)

Status: VERIFY/DOCUMENT/FREEZE/COMMIT/TAG/HANDOFF stage; no
implementation, refactor, or performance change (only R7 seal files
added plus minimal README status updates).

Contract version: `v1`. New seal artifacts:

- `docs/PHASE4_FREEZE_MANIFEST.json` — machine-readable freeze
  (phase 4, FROZEN; full upstream + Phase-4 SHAs, no abbreviations;
  manifest never hashes itself).
- `docs/PHASE4_FINAL_REPORT.md` — authoritative final report (22
  sections per R7-E).
- `docs/PHASE5_REPLAY_HANDOFF.md` — replay handoff with the explicit
  ~12 s/snapshot architectural warning for Phase-5 R0.
- `docs/PHASE4_V2_API_CONTRACT.json` — normalized frozen V2 surface
  (4 endpoints, methods, schemas, params, 200/422).
- `tests/test_v2_phase4_freeze.py` — compact seal suite (manifest,
  module/test/contract hashes, artifact identity, route inventory,
  OpenAPI normalization, anchor/roster representation, 2025 exclusion,
  no-fallback, no-training-entry, legacy presence).
- README status lines updated (Phase 4 FROZEN, Phase 5 NEXT, counts).

Verification: focused freeze gate green (R1–R6 + freeze + Phase-2
parity + P3.1 + baseline + OpenAPI + compile/import); full repository
suite green with only the four documented Monaco NaN xfails; frontend
(eslint/tsc/build) green with the one pre-existing lint warning; D11
read-only scientific/data checks green pre- and post-commit (Git
hygiene sections recorded separately; unrelated user-owned dirty files
left untouched).

Scientific parity unchanged: ALL_84 max abs diff 0.0, prediction max
abs diff 0.0, INDEPENDENT_BINARY, no normalization. Final performance
unchanged from R6 (~12.18 s full snapshot, ~6.8x vs R5 baseline).

Upstream hashes recomputed live and unchanged: Phase-2 schema/content/
parquet/manifest/registry/label/F16 x8, spec fingerprint
`3164de9e…`, serving artifact `1116b34fc716035c…` (full), holdout
`2c3a166d…7415` (hash only, values never read), final model metadata,
Phase-3 freeze manifest identity. 2025 exclusion intact
(SERVED_SEASONS 2018–2024; no serving path loads labels/evaluation;
M9 seal green).

Git seal: Phase-4-only commit `feat(v2): freeze race state and
prediction service` via explicit pathspec (unrelated staged/unstaged
user work preserved and verified absent from the commit); annotated
tag `v2-race-state-prediction-phase4` on the seal commit; nothing
pushed. Graphify refreshed.

Known debt: ~12 s/snapshot feature cost, F11 recompute, dual RaceIndex
memory, Monaco xfails, log FutureWarning noise, D11 /tmp-path cosmetic
issue — all carried in the final report §21.

No scientific freeze conflict. PHASE 5 NOT IMPLEMENTED.
