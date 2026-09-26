# PHASE 8 E7 — FINAL SCIENTIFIC + PRODUCT VALIDATION REPORT

E7 is a validation stage, not a feature stage. This report records final
evidence that Phase 8 behaves correctly end-to-end over the frozen artifacts
and current product implementation:

historical state → prediction checkpoint → frozen cached prediction →
timeline → local explanation → checkpoint-to-checkpoint change explanation →
frontend presentation.

Machine-readable companion:
`results/v2_validation/phase8_e7_validation_manifest.json`.

No feature development was performed. One real responsive defect was found
and fixed with a one-line scoped change (Part S); it is documented below
with root cause and re-validation. No scientific artifact, tolerance,
semantic, or frozen identity was altered.

---

## 1. Repository / identity preflight (Part A)

- HEAD: `17c04b30b124c087c51243a53d2f55bb3d9feeae`
- Working tree: dirty with pre-existing Phase-8 work only (E0–E6 additions);
  nothing staged (`git diff --cached` empty). E7 staged/committed nothing.
- Interpreters: Python 3.11.15 (project), NumPy 2.4.2, pandas 2.3.3,
  scikit-learn 1.8.0, Node v22.23.1.

Authoritative identities — all verified intact:

| Identity | Expected | Observed |
|---|---|---|
| Matrix rows / predictive features | 189,420 / 84 | 189,420 / 84 |
| Matrix parquet SHA | `b0f17b66…7ba1590b3` | match |
| Phase-2 content hash | `d2ee966c…92799db` | match |
| Winner serving SHA | `1116b34f…eaf3fcaa59f4` | match |
| Winner semantics | LogReg ALL_84/v8 RAW INDEPENDENT_BINARY | confirmed |
| Global explanation SHA | `bae84b61…828f73982939f` | match |
| Cache aggregate SHA | `78a3c059…3ee3b8ba96298` | match (recomputed, see Part C) |
| Races / checkpoints / observable / null | 149 / 9,644 / 189,610 / 3,206 | match |

No cache mutation since E2: the full E2 validator was rerun with output
redirected to `/tmp`; the regenerated manifest is byte-identical to the
committed `results/v2_replay/phase8_e2_cache_manifest_v1.json` except the
`validation_seconds` field. Verdict: **not blocked**.

Graphify-first navigation: `graphify update .` then targeted
`graphify query` calls identified the replay/explanation/timeline services,
matrix backend, serving model, ReplayView integration and Phase-8 tests.
Final graph: 10,721 nodes · 27,276 edges · 317 communities. Product modules
(`api/v2_explanation_*`, `api/v2_timeline_explanation_*`, frontend replay)
consume frozen layers (`v2/*`, scripts backends); no `v2/*` module imports
any Phase-8 product module (only pre-existing `SERVED_SEASONS` import from
frozen Phase-4 `api.v2_service`). No dependency inversion, no new cycle.

---

## 2. Deterministic validation sample (Part B)

`SAMPLE_RACES` (10, deterministic, no 2025):

- Per-season first races: 2018-r01-R, 2019-r01-R, 2020-r01-R, 2021-r01-R,
  2022-r01-R, 2023-r01-R, 2024-r01-R.
- Extremes: 2021-r12-R (min, 3 checkpoints), 2023-r06-R (max, 95).
- Null-heavy: 2022-r02-R (129 nulls).

Per race: checkpoints at indices {0, n//2, n−1} (EARLY/MID/LATE); per
checkpoint: observable drivers at roster positions {0, m//2, m−1}
(front/mid/rear by roster order) plus the first null/unobservable entry.
Result: **71 observable points, 12 null points**. Naturally covered:
ordinary green running, flag-transition checkpoints (e.g. 2018-r01-R f83+),
categorical compound transitions, missing/imputed inputs, front/mid/rear
drivers, unobservable drivers, first checkpoints, 3-checkpoint and
95-checkpoint races.

---

## 3. Cache corpus revalidation (Part C)

Ran `scripts/validate_replay_prediction_cache.py` unmodified (output to
`/tmp`): **149/149 races, 9,644 checkpoints, 189,610 observable, 3,206
null** — every artifact `complete=true`, correct format/race/series
identity, strict checkpoint ordering, valid reasons/roster, single frozen
model + feature identity, INDEPENDENT_BINARY semantics, finite [0,1]
probabilities, nulls preserved with reasons, valid cache keys, recorded
artifact SHAs. Aggregate corpus SHA recomputed `78a3c059…` — match.

---

## 4. Matrix ↔ cache consistency (Part D)

For all 71 sampled observable points: exact replay-observation identity →
exact Phase-2 matrix lookup (no fallback) → ordered ALL_84 → frozen
preprocessor (106 dims exact) → frozen estimator `predict_proba` vs E2
cached probability. **Max abs diff 3.331e-16 ≤ 1e-12. 71/71 pass.**

## 5. Recompute → matrix cross-check (Part E)

Bounded subset (2021-r12-R, 2023-r01-R × EARLY/MID/LATE checkpoints, all
observable drivers, **82 rows**): `RaceStateFeatureBridge` temporal
recomputation at the checkpoint state vs exact-identity matrix lookup —
**ALL_84 exact equality (NaN-aware), transformed/logit/probability equal**.
Acceleration did not change science. (One script-side comparison bug found
during validation — compared against the driver's first matrix row instead
of the exact-identity row — was fixed in the harness, not the product; all
82 rows then matched exactly.)

## 6. Local explanation reconstruction (Part F)

71/71 domain explanations: `|z_reconstructed − decision_function|`
max **7.105e-15**; `|sigmoid − predict_proba|` and `|sigmoid − cached|`
max **4.441e-16**; all ≤ 1e-12. Cached probability equals E2 value.

## 7. 106 → 84 grouping (Part G)

All 71: 106 transformed dims and 84 canonical features accounted for, no
duplication/omission (index set == 0..105), Σ canonical == Σ transformed
within 1e-12. Multi-dimensional categorical blocks present.

## 8. Missingness (Part H)

Naturally observed input states across the sample: OBSERVED,
IMPUTED_NUMERIC_MEDIAN, IMPUTED_BOOLEAN_MODE, MISSING_CATEGORY.
UNKNOWN_CATEGORY does not occur naturally in the sample and was not
manufactured as historical evidence (synthetic UNKNOWN path remains covered
by E4 unit tests). Displayed/input state matches frozen preprocessing
(median/mode/vocabulary logic in `v2/local_explainability.py`).

## 9. Timeline identity (Part I)

603 sampled checkpoints across 10 races: service output **byte-equal** to
production artifacts (checkpoint identity, frame index, state_time,
roster, probabilities, nulls, deterministic ordering). No interpolation,
no snapping, strictly increasing state_time.

## 10. Change explanation (Part J)

**630 full A→B validations** (one rotating driver per pair + all 40
detected categorical/missingness-transition candidates): from/to
probabilities match cache ≤ 1e-12; from/to logits match E4 ≤ 1e-12;
logit_delta == B−A ≤ 1e-12; Σ canonical deltas == logit_delta, max
residual **3.886e-15 ≤ 1e-12**. Cache-wide scan of 12,193 pair-driver
deltas: 3,765 positive / 6,120 negative / 2,308 near-zero — all three
classes validated, including positive/negative contribution cancellation
in top-delta lists. (Aligned to the frozen E5 contract: 1e-12 tolerance,
not bit-exact — JSON round-trip accounts for ~1e-16 differences.)

## 11. First / null / unavailable (Part K)

- First checkpoint → `NO_PREVIOUS_CHECKPOINT` (all 10 races).
- Driver unobservable/null at an endpoint → `COMPARISON_UNAVAILABLE` with
  explicit reason (observed `DRIVER_NOT_OBSERVABLE_AT_PREVIOUS_CHECKPOINT`;
  299 null entries checked across sampled checkpoints).
- No B-roster driver was absent from the A roster at pairs 0→1 in the
  sample (stable rosters); the absent-driver path is covered by
  `UnknownDriverError` + E5 unit tests.
- Null never treated as 0 (299/299 remain null with reasons).
- Non-checkpoint frame → `NotPredictionCheckpointError` with
  previous/next checkpoint pointers (never snapped).
- Unknown driver → `UnknownDriverError`.

## 12. Temporal adversarial (Part L)

Post-T mutation (all matrix rows strictly after T overwritten with
garbage): exact row identity, cached prediction and explanation unchanged.
Post-B mutation for A→B: both endpoint explanations and the delta
unchanged. Bounded claim only: **no temporal leakage was detected under
the implemented E7 adversarial validation.**

## 13. 2025 firewall (Part M)

Matrix slice, matrix lookup, replay frame/prediction/timeline, local
explanation, change explanation, and validator scope all reject 2025
(`MatrixScopeError`/`MatrixLookupError`/`RaceNotFoundError`; served-ID
scan contains no 2025). 2025 labels never read.

## 14. Label firewall (Part N)

ALL_84 contains none of `is_winner/is_podium/scored_points/final_position/
position_change_from_state/gains_position_by_finish/
loses_position_by_finish/classified_flag/eligible_*`. Label-poisoned rows
projected through the frozen preprocessor/predictor produce
bit-identical transforms and probabilities — labels are structurally
excluded, not merely ignored.

## 15. Probability semantics (Part O)

No normalization/softmax/sum-division anywhere in Phase-8 serving/product
code (only docstrings asserting never-normalized). Real example:
**2019-r11-R frame 798 field sum = 1.987 > 1**, stored verbatim and served
as-is; product labels it "independent binary estimates (not shares)" in
PredictionPanel, timeline chart, and change views. Sum > 1 is valid, not
an error.

## 16. Language audit (Part P)

E3/E4/E5 forbidden lists applied to the global artifact, a live local
domain+public payload and a change payload — clean. Frontend replay copy
(components + lib, excluding tests): zero prohibited phrases
(caused/because/true reason/win factor/added % chance/model thinks/knows);
log-odds framing present in Local/Change/Prediction panels. E4/E5
`test_language_contract` and frontend language-contract tests pass.

## 17. API end-to-end (Part Q)

Live backend (fresh process from current tree) via TestClient across
2018-r01-R, 2021-r12-R, 2023-r06-R, 2024-r01-R: race listing (149, no
2025), replay frame, prediction checkpoint, probability timeline, local
explanation, change explanation — identity consistent
(race/frame/driver/checkpoint/model/probability) across endpoints.
Non-checkpoint → 404/422; 2025 → 404. Warm timings (TestClient):
frame+timeline p50 28.9 / p95 30.1 ms; E4 p50 24.5 / p95 24.7 ms; E5 p50
41.8 / p95 41.9 ms — consistent with E6 integrated baselines (E4 ~40 ms,
E5 ~45 ms); no material regression.

## 18. Frontend end-to-end (Part R)

Production build served live; validated 2018-r01-R (frame 0 → checkpoint
frame 20 navigation, HAMILTON select, local + change panels), 2021-r12-R
(rain-affected 3-checkpoint race, stale-row semantics), 2024-r01-R.
API↔UI agreement: HAMILTON@2018-r01-R/f20 shows 84.94% / +4.4pp and
LOGIT 1.417→1.730 Δ+0.31, exactly matching API values
(0.8493530206654356; 1.4170225734105353→1.7295356930097965).
VERSTAPPEN@2024-r01-R/f0 shows 90.51%, matching API 0.9051. First
checkpoint shows "no previous comparison"; unobservable drivers show
explicit unavailable reasons.

## 19. Responsive (Part S) — REAL DEFECT FOUND AND FIXED

Initial measurement: page-level horizontal overflow at 1024/768/650/390/
360 (57–99px). Root cause: the unavailable-reason label
(`NO_OBSERVATION_AT_SNAPSHOT`, 27 unbreakable uppercase tracked chars) in
PredictionPanel rows used `w-20 shrink-0`, forcing `min-content: 178px`
into an 80px box that flex could not shrink → page scroll.

Fix (one line, `PredictionPanel.tsx`): keep desktop rendering identical
and allow shrink+wrap only below the `xl` breakpoint:

`w-20 shrink-0 …` → `w-20 shrink-0 … max-xl:min-w-0 max-xl:shrink
max-xl:break-words`

(No scientific/product logic touched; label text unchanged; no clipping —
text wraps, rows grow.) Re-validated after rebuild at all six widths:
**no page-level overflow at 1440/1024/768/650/390/360**; desktop ≥1280
renders single-line exactly as before. Telemetry tables scroll internally
(`overflow-x-auto`); timeline, local/change explanations, and controls
reachable at 360px. Per E7 deviation rules this is explicitly reported.

## 20. Accessibility (Part T)

Keyboard-only frame stepping verified live (focus Next → Enter advances
20→21, URL + content follow). Driver disclosure buttons carry
`aria-expanded`; transport/timeline controls labelled; `role=alert/status`
and `aria-live` regions present for loading/error/announcement paths;
timeline scrubber is a keyboard-operable slider. No new tooling added
(existing suites + live spot checks).

## 21. Stale response (Part U)

Live rapid race-switch (2024 → 2021 → 2018 with no settle): final state
settles on the last selection; no cross-race driver/payload leak.
Implementation guards verified in code (`requestIdRef` + AbortController
in `useReplay`, session/request guards in `useLocalExplanation`/
`useTimelineChange`) and covered by frontend unit tests
(`replayIntegration.test.ts`: selection keying, abort of superseded
requests — 148/148 pass).

## 22. Performance (Part V)

No microbenchmark chase. Representative warm figures in Part Q; live
frame stepping/timeline/driver/explanation interactions observed
interactive (sub-second, no jank noted). No material regression vs E6.

## 23. Determinism (Part W)

Repeated live requests byte-identical: probability timeline, E4 local
explanation, E5 change explanation (`cmp` clean). Build determinism
covered by E1.6 `test_matrix_build_deterministic` (pass). No
non-scientific timestamps in scientific payloads.

## 24. Full test gate (Part X)

| Suite | Result |
|---|---|
| E4 + E5 | 96 passed |
| E1 + E1.6 + E3 | 73 passed (11.3 min; 149-race structural scan) |
| Phase-5 r2/r3/r4/freeze + Phase-4 freeze + P3.1 | 159 passed, **4 failed (pre-existing)** |
| Phase-5 r6/r7 + Phase-6 r1 | 325 passed, 5 skipped, **1 failed (pre-existing)** |
| Phase-2 features f2–f6 | 155 passed |
| Frontend node `--test` | 148 passed |
| tsc / eslint / `next build` | clean / clean / success |

Pre-existing failures (each proven unrelated to E7 — E7 made no commits
and, except the Part S one-line UI fix, no repo edits):

1. `phase5_freeze::test_freeze_manifest_file_hashes_match` — `api/main.py`
   SHA drift: exactly +6 lines adding the E4/E5 explanation routers
   (legitimate Phase-8 additions).
2. `phase5_freeze::test_freeze_manifest_generated_cache_not_required` —
   asserts `results/v2_replay` must not exist; the E2 production cache
   exists by design (gitignored).
3. `phase5_freeze::test_freeze_manifest_documents_authorized_api_main_drift`
   — same `api/main.py` drift.
4. `phase4_freeze::test_frozen_module_hashes_match` — same drift.
5. `phase5_r7::test_head_and_phase4_tag_intact` — pins HEAD to Phase-5
   commit `4f26801`; HEAD is `17c04b3` (4 legitimate later commits).

No test was weakened, deleted, or modified to obtain green.

## 25. Requirements matrix (Part Y)

| Requirement | Implementation / evidence | Validation | Status |
|---|---|---|---|
| Replay cache backfill | 149 matrix-built artifacts | Part C rerun, SHA match | green |
| Prediction timeline | probability-timeline endpoint + chart | Parts I, Q, R | green |
| Global explainability | frozen E3 artifact | SHA + E3 suite (in X) | green |
| Local explainability | E4 log-odds decomposition | Parts F–H, E4 suite | green |
| Timeline/change explainability | E5 A→B deltas | Parts J–K, E5 suite | green |
| Exact checkpoint semantics | identity-keyed serving | Parts D, I, K | green |
| Temporal safety | identity lookups, no refit | Parts E, L | green (bounded) |
| 2025 firewall | scope rejection everywhere | Part M | green |
| Label firewall | structural exclusion | Part N | green |
| Probability semantics | INDEPENDENT_BINARY verbatim | Parts O, R | green |
| Determinism | byte-identity | Part W | green |
| Performance | interactive latencies | Parts Q, V | acceptable |
| Responsive UX | 6 widths, 1 defect fixed | Part S | green after fix |
| Accessibility | keyboard/ARIA/live regions | Part T | green |
| Scientific language | forbidden-list guards | Part P | green |
| Regression safety | gate above; 5 pre-existing failures dispositioned | Part X | green with notes |

## 26. Known limitations (Part Z)

Winner model remains independent-binary (no joint distribution); global
permutation evidence is pre-2025 final-fit in-sample; explanations are
associational decompositions, not causal; no SHAP; no explanation cache
(on-demand compute is interactive: ~25 ms E4 / ~42 ms E5); timeline covers
prediction checkpoints, not every frame; 2025 remains unserved holdout;
track visualization deferred; UNKNOWN_CATEGORY has no natural historical
example in the E7 sample (covered synthetically in unit tests).

## 27. Graphify final

`graphify update .` — 10,721 nodes · 27,276 edges · 317 communities.
Phase-8 product modules consume frozen layers only; no scientific module
imports product modules; no new cycle.

## 28. Repository safety

No `reset/restore/checkout/clean/stash/add/commit/tag`. Nothing staged.
E7 repo writes: `docs/PHASE8_E7_FINAL_VALIDATION_REPORT.md` (this file),
`results/v2_validation/phase8_e7_validation_manifest.json`, and the
Part S one-line UI fix. All validation harnesses live in `/tmp/e7`,
outside the repo. Two stale 4-day-old dev servers (:8000 uvicorn,
:3000 next-server, predating E7 and noted as stale in E6) were replaced
by fresh E7-validation instances; all E7-started servers were stopped
after validation.

## 29. E8 freeze gate

- [x] authoritative hashes intact
- [x] 149 replay artifacts validated
- [x] 9,644 checkpoints validated
- [x] aggregate cache SHA intact
- [x] deterministic E7 sample spans 2018–2024
- [x] matrix→prediction consistency green
- [x] recompute→matrix subset green
- [x] local logit reconstruction green
- [x] local probability reconstruction green
- [x] 106→84 grouping green
- [x] missingness semantics green
- [x] timeline identity green
- [x] change delta reconstruction green
- [x] first/null/unavailable semantics green
- [x] temporal adversarial validation green (bounded)
- [x] 2025 firewall green
- [x] label firewall green
- [x] independent-binary semantics green
- [x] language audit green
- [x] API E2E green
- [x] frontend E2E green
- [x] responsive validation green (after 1-line fix)
- [x] accessibility validation green
- [x] stale-response validation green
- [x] performance acceptable
- [x] determinism green
- [x] practical Phase-8 regression suite green (5 pre-existing failures dispositioned)
- [x] requirements matrix complete
- [x] known limitations documented
- [x] no new scientific blocker
