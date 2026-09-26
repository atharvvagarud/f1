# PHASE 8 — REPLAY INTELLIGENCE: FINAL FREEZE REPORT (E8)

E8 is a freeze stage, not a development stage. No product/scientific
functionality was introduced in E8. E0–E7 reports are authoritative;
this report consolidates them into a reproducible checkpoint.

Stage history:

- E0 — scope/characterization (baseline cache pipeline probes).
- E1 — cache pipeline verification + transparent optimization
  (`docs/PHASE8_E1_CACHE_OPTIMIZATION_REPORT.md`).
- E1.5 — temporal-recompute vs matrix equivalence (3,764/3,764 rows,
  max diff 0.0; recompute and matrix lookup are the same vector).
- E1.6 — offline accelerated matrix-lookup backend
  (`docs/PHASE8_E1_6_MATRIX_ACCELERATION_REPORT.md`).
- E2 — replay cache backfill, 149 races
  (`docs/PHASE8_E2_REPLAY_CACHE_BACKFILL_REPORT.md`).
- E3 — global explainability, frozen permutation artifact
  (`docs/PHASE8_E3_GLOBAL_EXPLAINABILITY_REPORT.md`).
- E4 — local log-odds explainability
  (`docs/PHASE8_E4_LOCAL_EXPLAINABILITY_REPORT.md`).
- E5 — timeline/change intelligence
  (`docs/PHASE8_E5_TIMELINE_INTELLIGENCE_REPORT.md`).
- E6 — replay intelligence frontend integration
  (`docs/PHASE8_E6_REPLAY_INTELLIGENCE_INTEGRATION_REPORT.md`).
- E7 — final scientific + product validation, GREEN
  (`docs/PHASE8_E7_FINAL_VALIDATION_REPORT.md` +
  `results/v2_validation/phase8_e7_validation_manifest.json`).
- E8 — this freeze (report + deterministic manifest + commit + tag).

## 1. Final architecture

Historical canonical data → frozen Phase-2 feature matrix
(`matrix_version=v1`, ALL_84/v8) → frozen winner serving artifact
(LogisticRegression, RAW) → replay checkpoints (model-free selector:
LEADER_LAP / FLAG_TRANSITION) → E2 prediction cache (offline only,
never generated on the read path) → probability timeline → E4 local
explanation → E5 change explanation → replay frontend.

Four concepts that must never be collapsed:

1. FACTUAL HISTORICAL STATE — `RaceState` reconstruction (what happened).
2. INDEPENDENT-BINARY MODEL PREDICTION — per-driver `predict_proba`
   from the frozen winner; field sums routinely exceed 1 (e.g.
   2019-r11-R frame 798 sums to 1.987). Valid; never normalized.
3. LOCAL MODEL LOG-ODDS EXPLANATION — exact decomposition
   `z = intercept + Σ beta_j·x'_j`, additive in log-odds only, never
   probability points.
4. CHECKPOINT-TO-CHECKPOINT MODEL SCORE CHANGE — A→B delta of the same
   frozen score; overall probability deltas vs per-feature log-odds
   deltas are labeled separately in the UI.

## 2. Authoritative identities (all reverified in E8, no regeneration)

| Identity | Value |
|---|---|
| Matrix parquet SHA | `b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3` |
| Phase-2 content hash | `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db` |
| Winner serving SHA | `1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4` |
| Model | LogisticRegression ALL_84/v8 RAW INDEPENDENT_BINARY |
| E2 corpus aggregate SHA | `78a3c059888637fe83cc534d0eb7869b6d18e746724bb1ce0f03ee3b8ba96298` |
| E3 global explanation SHA | `bae84b614a6e9e176d5bb9c33b99dcaf4cba3f376333b0f075c828f73982939f` |

Corpus: 149 races · 9,644 checkpoints · 189,610 observable predictions ·
3,206 null/unavailable entries. E7 manifest
(`phase8-e7-validation-manifest-v1`) refers to exactly these identities.

## 3. Contracts (exact strings from code)

- `REPLAY_CONTRACT_VERSION = "v1"` (`v2/replay.py`).
- `REPLAY_PREDICTION_CONTRACT_VERSION = "v1"`
  (`v2/replay_predictions.py`); checkpoint reasons `LEADER_LAP`,
  `FLAG_TRANSITION`.
- Replay checkpoint artifact format `ARTIFACT_FORMAT =
  "replay-checkpoints-v1"` (envelope marker, fail-closed on mismatch).
- E2 cache manifest version `phase8-e2-cache-manifest-v1`.
- `PROBABILITY_TIMELINE_CONTRACT_VERSION = "v1"`
  (`v2/replay_probability_timeline.py`).
- `GLOBAL_EXPLANATION_FORMAT = "global-explanation-v1"`;
  explanation space `LOG_ODDS`; semantics `INDEPENDENT_BINARY`;
  evaluation protocol `PRE_2025_FINAL_FIT_IN_SAMPLE`
  (`v2/explainability.py`).
- `LOCAL_EXPLANATION_CONTRACT_VERSION = "v1"`,
  `LOCAL_EXPLANATION_FORMAT = "local-explanation-v1"`
  (`v2/local_explainability.py`); tolerances 1e-12 logit/probability.
- `TIMELINE_EXPLANATION_CONTRACT_VERSION = "v1"`,
  `TIMELINE_EXPLANATION_FORMAT = "timeline-explanation-v1"`
  (`v2/timeline_explainability.py`).

## 4. API inventory (all `GET`, read-only; never generate on the read path)

Replay family (`api/v2_replay_routes.py`):

- `/v2/races/{race_id}/replay/timeline` — paginated ReplayFrame metadata.
  404 `unknown_race`.
- `/v2/races/{race_id}/replay/frames/{frame_index}` — factual frame +
  exact R2 RaceState + checkpoint flags + nearest-checkpoint pointers.
  404 `unknown_race` / `unknown_frame`.
- `/v2/races/{race_id}/replay/predictions/{frame_index}` — cached
  checkpoint prediction only (`cache_status: HIT`). 404
  `not_prediction_checkpoint` (with previous/next pointers, never
  snapped); 503 `prediction_unavailable`.
- `/v2/races/{race_id}/replay/probability-timeline` — cached probability
  series only. 503 `prediction_unavailable`.

Local explanation (`api/v2_explanation_routes.py`):

- `/v2/replay/{race_id}/frames/{frame_index}/predictions/{driver_id}/explanation`
  — exact local log-odds explanation of one cached checkpoint
  prediction. 404 `unknown_race` / `unknown_frame` /
  `not_prediction_checkpoint` / `unknown_driver`; 422
  `driver_not_observable`; 503 `prediction_unavailable`; 500 `internal`
  (fail closed, never fabricated).

Change explanation (`api/v2_timeline_explanation_routes.py`):

- `/v2/replay/{race_id}/frames/{frame_index}/predictions/{driver_id}/change`
  — exact A→B change vs the driver's previous checkpoint. Product
  states (HTTP 200): `AVAILABLE`, `NO_PREVIOUS_CHECKPOINT` (first
  checkpoint), `COMPARISON_UNAVAILABLE` (null endpoint + reason).
  Same error family as the explanation route.

## 5. Frontend inventory

- `ReplayView` — owns the single race-tagged `selectedDriverId` shared
  by both explanation surfaces; race switch derives selection to null
  immediately (no cross-race leak).
- `PredictionPanel` — checkpoint prediction list; observable drivers are
  buttons (`aria-expanded`) gating `LocalExplanationPanel`; E7 fix: the
  unavailable-reason label carries
  `max-xl:min-w-0 max-xl:shrink max-xl:break-words` (only E7 change;
  no semantic effect).
- `ProbabilityTimelineChart` — cached probability series + checkpoint
  details table (probability + Δ-vs-previous in percentage points) +
  exact-frame replay action (no nearest-frame snapping) +
  `ChangeExplanationPanel` for the active driver.
- `LocalExplanationPanel` (`useLocalExplanation`) — per-driver log-odds
  contribution list for the current checkpoint.
- `ChangeExplanationPanel` (`useTimelineChange`) — A→B log-odds delta
  list with `AVAILABLE` / `NO_PREVIOUS_CHECKPOINT` /
  `COMPARISON_UNAVAILABLE` states.
- Shared: `explanationSelection.ts` (selection helpers),
  `localExplanation.ts` / `timelineChange.ts` (payload shaping),
  `lib/v2.ts` (typed API client incl. explanation/change endpoints).

## 6. Scientific invariants (frozen)

Phase-1 data, Phase-2 features, ALL_84, Phase-3 model, preprocessing,
RaceState semantics, replay checkpoint semantics, Monte Carlo,
strategy, prediction cache, and all explanation mathematics are
untouched. No retrain/retune/recalibration, no cache regeneration, no
E3 artifact rebuild, no normalization, no 2025 access, no tolerance
changes, no new features.

## 7. E7 validation summary (authoritative)

Deterministic 10-race sample (71 observable + 12 null points): matrix→
cache 71/71 exact (max 3.331e-16); recompute→matrix 82 rows ALL_84
exact; local explanations 71/71 (logit residual ≤ 7.105e-15,
probability ≤ 4.441e-16); timeline 603 checkpoints byte-exact; change
630 A→B validations (delta residual ≤ 3.886e-15); probability semantics
INDEPENDENT_BINARY confirmed verbatim in serving code; 2025/label
firewalls reject; language contract clean; API + live frontend
end-to-end agreement; responsive defect found and fixed (Part S);
accessibility/stale-response/determinism green. Verdict: E7 COMPLETE —
READY FOR E8 FREEZE.

## 8. Performance (E7 figures, not re-chased in E8)

Warm TestClient medians: E4 ~24.5 ms, E5 ~41.8 ms, frame+timeline
~28.9 ms — interactive, hence no explanation cache by design.

## 9. Test status

E8 runs the targeted freeze gate (Part N), not massive recomputation:
E3/E4/E5 suites, E6 integration, E1.6 identity/firewall, replay
API/timeline, serving tests, all node tests, `tsc`, `eslint`,
`next build`, plus the E2 cache validator (output to `/tmp`,
byte-compare of the manifest). Only historically documented
freeze-pin failures may remain (see §10).

## 10. Known historical failures (pre-existing, must not be "fixed")

Old manifests pinning older `api/main.py` (+6 Phase-8 router lines),
E2 cache existence conflicting with historical assumptions, old HEAD
pin (`test_head_and_phase4_tag_intact` pins a Phase-5 commit; HEAD has
moved through legitimate Phase-6/7/8 work). Any NEW unexplained
failure blocks E8.

## 11. Known limitations (frozen, verbatim)

1. Winner probabilities are independent binary estimates, not a
   normalized race distribution.
2. Global permutation importance is PRE_2025_FINAL_FIT_IN_SAMPLE, not
   temporally out-of-sample.
3. Explanations are associational/model-internal, not causal.
4. Feature contributions are additive in log-odds, not probability points.
5. SHAP is not part of v1.
6. Timeline operates at prediction checkpoints, not every replay frame.
7. 2025 remains unserved/holdout.
8. No explanation cache because on-demand latency is interactive.
9. Track visualization remains deferred.
10. No natural historical UNKNOWN_CATEGORY example was found in E7;
    behavior is synthetically tested.

## 12. Artifact policy

| Artifact | Location | Tracked | Command | Identity | Runtime |
|---|---|---|---|---|---|
| E2 replay cache (58.6 MB) | `results/v2_replay/` | No (gitignored) | `python scripts/build_replay_prediction_cache.py --all-served-races` | aggregate `78a3c059…` | Required |
| E2 cache manifest | `results/v2_replay/phase8_e2_cache_manifest_v1.json` | Yes | `python scripts/validate_replay_prediction_cache.py` | same aggregate | Required |
| E3 global explanation | `results/v2_explainability/` | No (gitignored) | `python -m v2.explainability` | `bae84b61…` | Required |
| E7 validation manifest | `results/v2_validation/phase8_e7_validation_manifest.json` | Yes | E7 harness (frozen evidence) | pins all identities | Evidence |
| E8 freeze manifest | `results/v2_validation/phase8_freeze_manifest.json` | Yes | deterministic, hand-authored from E7 + code | — | Evidence |

Ignored artifacts are never force-added. Validators read them in place;
regeneration is forbidden in E8.

## 13. Reproduction / validation commands (no regeneration in E8)

- `python scripts/validate_replay_prediction_cache.py` (redirect stdout
  to `/tmp`; expect manifest byte-identity except `validation_seconds`).
- `pytest tests/test_v2_phase8_e3.py tests/test_v2_phase8_e4.py
  tests/test_v2_phase8_e5.py tests/test_v2_phase8_e1.py
  tests/test_v2_phase8_e1_6.py` (targeted gate; E3 suite includes the
  149-race structural scan, ~11 min).
- Frontend: `node --test` (replay lib tests), `tsc --noEmit`,
  `eslint`, `next build`.
- Hashes: `sha256sum` the three files in §2; compare with the table.

## 14. Dependency direction (graphify)

Phase-8 product (`api/v2_explanation_*`,
`api/v2_timeline_explanation_*`, frontend replay) consumes frozen
science (`v2/*`, scripts backends); no `v2/*` scientific module imports
any Phase-8 product module; no new scientific cycle. Final graph
recorded in the freeze manifest.

## 15. Freeze commit / tag

Recorded after the gate: commit `feat(v2): freeze replay intelligence
phase 8`, annotated tag `v2-replay-intelligence-phase8` pointing at
that commit.
