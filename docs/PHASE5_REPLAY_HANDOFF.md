# Phase 5 Handoff — Historical Race Replay

Phase 4 status: **FROZEN** (contract v1, tag
`v2-race-state-prediction-phase4`). Phase 5 is HISTORICAL RACE REPLAY.
This document states what Phase 5 receives and the architectural facts
it must respect. Phase 5 R0 owns all replay architecture decisions;
nothing here designs replay.

## Input

A historical race plus an exact historical anchor sequence, where each
anchor is `(race_id, anchor_driver_id, anchor_lap_number,
anchor_state_time_s)` resolved against the canonical D9 corpus.

## Available from Phase 4 (frozen, do not mutate casually)

- `RaceStateReconstructor` (`v2/race_state_reconstruction.py`):
  exact-anchor -> `RaceState`. Raises `RaceNotFoundError` /
  `AnchorNotFoundError`; never nearest-matches, never rounds T.
- `RaceState`: complete roster in `driver_id` order, observable members
  with lap/time/position/gap/tyre/stint facts, unobservable members as
  explicit nulls, staleness provenance (`observed_time_s`,
  `observation_age_s`), past-as-of weather, verbatim race control,
  race context. Deterministic `to_dict()`.
- `RaceStateFeatureBridge` (`v2/race_state_features.py`):
  observable-only requests at each driver's own observed lap/time ->
  exact ALL_84 `FeatureBatch` with positional `FeatureIdentity`
  alignment. Read-only; process-local per-race slice cache.
- `RacePredictionEngine` (`v2/prediction.py`): one batch
  `predict_proba` per snapshot -> `PredictionSnapshot` with complete
  roster, null + `NO_OBSERVATION_AT_SNAPSHOT` for unobservable members,
  `ModelIdentity`, `INDEPENDENT_BINARY` semantics, fixed
  do-not-renormalize note. No fallback, no refit path.
- Exact anchor discovery: `GET /v2/races/{race_id}/states`
  (deterministic `(state_time_s, lap_number, driver_id)` order,
  paginated) enumerates every valid anchor; any 4-part miss is a 422.
- Observability/staleness: per-driver `observable`,
  `observed_lap_number`, `observed_time_s`, `observation_age_s`
  distinguish synced / stale / never-observed members.
- Factual context: weather/race-control/pit/stint state is past-only
  factual context, safe to render directly without model dependency.
- Frozen winner probabilities + model identity + deterministic
  serialization for any consumer (replay, strategy, explainability).
- V2 HTTP endpoints (`/v2/races`, `/states`, `/state`,
  `/predictions/winner-snapshot`) with stable error mapping
  (404/422/503/500) and 2018–2024 serving scope.

## Critical performance fact

A full-field prediction snapshot currently costs approximately **~12
seconds** under the controlled R6 benchmark (feature generation
dominates; inference is milliseconds). Therefore Phase 5 MUST NOT
assume it can synchronously execute the full prediction pipeline on
every visual animation tick. This is an architectural input to Phase-5
R0. Do NOT solve it in R7.

## Phase-5 R0 questions (R0 owns the answers)

- What exactly constitutes one replay frame?
- Which exact anchors define replay progression?
- What is the anchor-driver selection policy?
- Is every driver-lap an anchor or is a canonical timeline required?
- What is prediction refresh cadence?
- Should predictions be precomputed?
- What is the cache identity?
- How is backward navigation handled?
- How is forward navigation handled?
- How is playback deterministic?
- How are stale drivers rendered?
- How are unavailable drivers rendered?
- How are partial races handled?
- How are red flags handled?
- How are safety-car states represented?
- What HTTP/transport boundary should frontend use?
- Is WebSocket actually necessary?
- How should prediction precomputation interact with historical replay?
- How much replay state can be cached safely?

Constraints carried forward: exact-anchor semantics (no interpolation
without explicit new semantics), complete-roster rendering (never drop
unavailable entrants), no probability renormalization, 2018–2024 scope
(no 2025 product inference), legacy V1 routes stay untouched.
