# Phase 4 — Race State & Prediction Service Final Report

Status: **FROZEN** · Contract version: **v1** · Tag: `v2-race-state-prediction-phase4`

Phase 4 built the deterministic state/prediction primitives that Phase 5
replay will call. It is NOT replay: no WebSockets, no Monte Carlo, no
strategy, no what-if, no UI, no MLOps.

## 1. Executive Summary

Phase 4 exposes the frozen Phase-1/2/3 stack through a versioned V2 HTTP
API: exact historical `RaceState` reconstruction, frozen ALL_84 feature
bridging, frozen production winner inference, and independent-binary
probability semantics — all under `/v2`, with the four legacy routes
byte-identical. Scientific parity is exact on every tested fixture
(max abs diff 0.0 at each layer). R6 removed serving-time overhead for a
~6.8x end-to-end improvement with zero semantic change. Full repository
verification is green. No leakage was detected under the implemented
adversarial test suite. No protected 2025 target was accessed.

## 2. Scope

In scope (R1–R7): RaceState domain, historical reconstruction, ALL_84
bridge, frozen batch prediction engine, V2 API, integration/adversarial/
performance hardening, freeze seal (manifest, contract, commit, tag,
Phase-5 handoff). Out of scope (explicitly deferred): replay, streaming,
Monte Carlo, strategy, what-if, UI, MLOps, any retrain/recalibration,
any 2025 serving or evaluation.

## 3. Architecture

```
HTTP -> V2Service -> AnchorObservation -> RaceStateReconstructor
  -> RaceState -> RaceStateFeatureBridge -> frozen Phase-2
  features_for_batch -> exact ALL_84 -> FrozenWinnerPredictor
  .predict_proba ONCE -> PredictionSnapshot -> HTTP response
```

`V2Service` (process-local lazy singleton) binds the 2018–2024 D9
corpus, results roster, races metadata, one `PriorHistory`, one
reconstructor, one bridge, one frozen predictor, and one
`RacePredictionEngine`. `v2/*` is HTTP-independent; dependency direction
is HTTP schemas/routes -> service -> domain.

## 4. Canonical RaceState

R1 (`v2/race_state.py`, stdlib-only): `AnchorObservation(race_id,
anchor_driver_id, anchor_lap_number, anchor_state_time_s)` is the exact
Time-T key. `RaceState` carries one `DriverRaceState` per roster member
in `driver_id` order (observable with lap/time/position/gap/tyre/stint
facts + staleness provenance, or explicit full-null unobservable),
`RaceContext`, past-as-of `WeatherState`, and verbatim
`RaceControlState`. A `label_outcome_fields()` firewall plus import
guards keep final positions, winner/podium/points flags, masks,
`end_lap`, and every label value out of the domain.

## 5. Historical State Reconstruction

R2 (`v2/race_state_reconstruction.py`): `RaceStateReconstructor`
wraps the frozen `RaceIndex` (the sole synchronization authority).
Exact 4-key anchor lookup; `TargetNotFoundError` becomes
`AnchorNotFoundError`, unknown race becomes `RaceNotFoundError`. No
nearest substitution, no timestamp rounding, rivals synced at latest
observation `<= T`, zero-state entrants and stale drivers retained as
explicit nulls, frozen F6 gap geometry evaluated per member at its own
observed clock, past-only weather/race-control/pit facts.

## 6. Frozen ALL_84 Feature Bridge

R3 (`v2/race_state_features.py`): observable-only `FeatureRequest`s
using each driver's OWN observed lap/time through one
`features_for_batch` call over `build_f11_registry()` with
`resolve_feature_set("ALL_84")` ordering. `FeatureBatch` carries exact
84-column frames plus positional `FeatureIdentity` alignment. The bridge
defines no formula; the frozen preprocessor does all imputation.

## 7. Production Winner Inference

R4 (`v2/prediction.py`): `RacePredictionEngine` tuple-compares batch
columns against `predictor.feature_names`, calls `predict_proba` ONCE,
validates finite [0,1] outputs, and merges positionally onto the full
roster (observable -> probability, unobservable -> null +
`NO_OBSERVATION_AT_SNAPSHOT`). `ModelIdentity` anchors task
`winner`, target `is_winner`, mask `eligible_is_winner`, `ALL_84`/`v8`,
`LogisticRegression` recorded params, `RAW`, `INDEPENDENT_BINARY`,
2018–2024 training, dim 106, artifact SHA, spec fingerprint. Factory
`load_production_prediction_engine` wires bridge + frozen artifact;
serving failures become `ProductionModelUnavailableError`. No clamp,
normalize, threshold, label, fallback, or refit path exists.

## 8. V2 API

R5 (`api/v2_schemas.py`, `api/v2_service.py`, `api/v2_routes.py`,
additive `api/main.py` include): `GET /v2/races` (identity-only),
`GET /v2/races/{race_id}/states` (exact anchors, limit 1–500 default
100, `{total, offset, limit}`), `GET /v2/races/{race_id}/state`
(exact 4-part query), `POST /v2/predictions/winner-snapshot`
(anchor-only body). Error mapping: unknown race 404 `unknown_race`,
anchor miss 422 `unknown_state`, artifact failure 503
`model_unavailable` with no fallback, contract/internal failures 500
`internal`, stable `{error, detail}` bodies. V2/legacy import firewall
pinned both directions. Normalized contract:
`docs/PHASE4_V2_API_CONTRACT.json`.

## 9. Exact-Anchor Semantics

All four Time-T parts are required everywhere. A miss at any layer is a
422 with a states-discovery hint — never a nearest row, never silent
rounding (parametrized ±1e-4 s and off-by-one-lap tests). `lap_number`
remains per-driver progress, never a global clock.

## 10. Complete-Roster / Unavailable Semantics

Every roster member appears in every state and prediction payload in
`driver_id` order. Unobservable members carry full nulls (state) or
`winner_probability: null` + `unavailable_reason:
"NO_OBSERVATION_AT_SNAPSHOT"` (prediction) — never dropped, never
zero-filled. Zero-state entrants and pre-first-observation members are
deliberately indistinguishable from one snapshot.

## 11. Probability Semantics

Every `winner_probability` is P(is_winner=1 | state) from an
independent binary model. Values are never normalized, never summed,
never called a distribution; no `probability_share` or sum-to-one field
exists at any layer. Regression tests pin sums above and below 1
passing through exactly. The fixed do-not-renormalize note ships in
every snapshot and API payload.

## 12. Temporal Leakage Protections

Reused frozen machinery (RaceIndex sync, `<= T` bounds, prior
strictly-past firewall, label name-guards) plus Phase-4 adversarial
coverage: R2 11-case and R3 7-case future-mutation harnesses, same-lap
future hazard end-to-end (state/batch/snapshot byte-identical), row
reorder/delete/mutate invariance, weather/RC/pit futures, tie
determinism, identifier-mutation invariance, partial/red-flag fixtures.
No leakage was detected under the implemented adversarial test suite.

## 13. Scientific Parity Evidence

Max absolute difference 0.0 on tested parity fixtures at every layer:
R3 bridge vs direct `features_for_batch` oracle (4 anchors x 20 rows x
84 cols), R3 bridge vs frozen F15 matrix rows (same cells, null
patterns equal), R4 engine snapshot vs direct serving inference, R6
slice-vs-full oracle and pre/post-optimization snapshot probabilities
(identity/null mismatches 0 throughout).

## 14. R6 Performance Investigation

Full-corpus feature generation cost 81.56 s vs 11.92 s per-race slice
(6.8x). Profiling showed ~9,500 `synchronized_driver_state` + ~1,400
`driver_prefix` + ~700 `resolve_target` full-frame (162,728-row)
boolean scans dominating; reconstruction (37 ms) and inference
(7 ms) are corpus-size independent. Root cause: per-scan row width —
every frozen calculator reads same-race rows only, so the extra 154x
rows per scan were pure overhead.

## 15. R6 Serving Optimization

Two serving-adapter-only changes in `v2/race_state_features.py`, frozen
Phase-2 code untouched: OPT-1 lazy per-race slice cache keyed by
complete `race_id` (81.56 s -> 15.12 s); OPT-2 contiguous index on the
cached slice (15.12 s -> 12.02 s; full/per-race ratio 1.0x). History
bundle untouched, strictly-past reads preserved. Each optimization was
independently parity-gated before keeping.

## 16. Final Performance

Controlled R6 benchmark (2023-r01-R alonso-28, 20/20): FeatureBatch
81.56 s -> ~12.11 s; full snapshot 81.78 s -> ~12.18 s (~6.8x);
inference ~7 ms; warm state ~39 ms; service init ~6.8 s once per
process; repeated warm predictions +0.0 MB. Memory peak ~966 MB (dual
full-frame RaceIndex). Feature generation remains the dominant cost by
~1500x over inference.

## 17. Verification

Focused freeze gate (R1–R6 + freeze + Phase-2 parity + P3.1 + baseline
+ OpenAPI + compile/import) green; full repository suite green with
only the four documented pre-existing Monaco NaN xfails; frontend
(eslint/tsc/build) green with one pre-existing lint warning; D11
read-only scientific/data checks green (Git-hygiene sections reflect
the pre-commit uncommitted state, recorded pre/post). Frozen hashes
(Phase-2 x8, spec fp, serving SHA, holdout SHA, model metadata)
recomputed live and unchanged.

## 18. Legacy Compatibility

The four legacy routes are byte-identical (baseline 11/11; full legacy
characterization green). Legacy `ml/*`, routes, schemas, and service
unmodified; V2 never imports `ml.*`, legacy never imports `v2.*`.
The known Monaco-2022 NaN passthrough is preserved, still pinned by
the four xfails.

## 19. Protected Holdout / 2025 Policy

Development-era serving only (2018–2024); 2025 race_ids are unknown
(404). No serving path loads labels, the model matrix, or evaluation
artifacts; no M9 path is reachable from Phase-4 code. The holdout
artifact identity is unchanged (hash-verified, values never read);
the one-shot M9 seal remains intact via green seal tests.

## 20. Frozen Phase-4 Contracts

Contract v1 (see `docs/PHASE4_FREEZE_MANIFEST.json`): AnchorObservation,
DriverRaceState, RaceState, reconstructor/bridge/engine public
interfaces, FeatureIdentity/FeatureBatch alignment, ModelIdentity,
DriverPrediction, PredictionSnapshot, V2 schemas, four endpoint
paths/methods, exact-anchor semantics, complete-roster semantics,
null + `NO_OBSERVATION_AT_SNAPSHOT`, `INDEPENDENT_BINARY`,
no-normalization, 2018–2024 scope, no-model-fallback. Later phases may
build on these; they must not casually mutate them.

## 21. Known Limitations / Technical Debt

~12 s per full-field snapshot (frozen ~9,500 sync scans; F11 2x
primitive recompute ~40%); dual RaceIndex ~550 MB; one-time ~6.8 s
service init; Monaco NaN xfails (legacy only); pandas concat
FutureWarning noise in logs; `/tmp`-path D11 cosmetic reporting issue.
Full detail: `docs/PHASE4_R6_HARDENING_REPORT.md` §20.

## 22. Phase-5 Handoff

Phase 5 (Historical Race Replay) receives the frozen interfaces above
plus `docs/PHASE5_REPLAY_HANDOFF.md`. Critical input: a full-field
snapshot costs ~12 s — Phase 5 must not synchronously predict every
visual tick; R0 owns that architecture decision.
