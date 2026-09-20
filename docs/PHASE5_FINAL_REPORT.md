# Phase 5 — Historical Race Replay Final Report

Status: **FROZEN** · Replay contract: **v1** · Prediction contract: **v1**
· Probability-timeline contract: **v1** · Tag: `v2-historical-replay-phase5`

Phase 5 adds a deterministic historical replay subsystem on top of the
frozen Phase-1/2/3/4 stack. It is NOT a simulator: no Monte Carlo, no
strategy engine, no what-if, no track SVG, no real-time transport.

## 1. Executive Summary

Phase 5 lets a user select a 2018–2024 race, load its canonical timeline,
navigate it chronologically (first/previous/next/last/jump/play/pause,
0.5x–8x), inspect the exact factual `RaceState` at any point, and view
frozen winner probabilities at the checkpoints where the model was
actually evaluated. Every layer preserves strict historical temporal
semantics (`<= T`, no nearest lookup, no rounding, no forward-fill, no
interpolation presented as inference). Factual replay is cheap and
always available; model probabilities are precomputed offline and read
back read-only. No leakage was detected under the implemented adversarial
test suite. The production prediction cache was not generated as part of
the software freeze; factual replay works without it, and the prediction
endpoints return an explicit `503 cache_missing` until the offline
backfill runs.

## 2. Scope

In scope (R0–R8): canonical replay timeline and frame identity; exact
factual reconstruction service; model-free prediction checkpoints and a
filesystem cache contract; four read-only HTTP routes; a Next.js replay
UI; probability-timeline projection and visualization; hardening,
adversarial and performance audit; freeze seal (manifest, API contract,
tests, commit, tag, Phase-6 handoff).

Out of scope (explicitly deferred): Monte Carlo simulation, strategy
engine, what-if mutation, track rendering, richer probability UI beyond
the checkpoint timeline, any retrain/recalibration/renormalization, any
2025 serving or evaluation, any production prediction backfill.

## 3. Architecture

```
HTTP (api/v2_replay_routes.py)
  -> V2ReplayService            (read-only; holds NO engine)
     -> ReplayTimeline          v2/replay.py            (factual identity)
     -> ReplayReconstructor     v2/replay_reconstruction.py
        -> frozen RaceStateReconstructor -> RaceState
     -> CheckpointSeries        v2/replay_predictions.py (model-free select)
     -> load_validated_artifact / read_cached_prediction (read-only)
     -> build_probability_timeline v2/replay_probability_timeline.py
  -> frontend (Next.js) : lib/v2.ts + features/replay/
```

Dependency direction is strictly one-way: domain (`v2/replay*`) imports no
model/feature/API code; the service imports only read-only R3 helpers and
holds no engine, so request-time generation is impossible by
construction; routes import the service and schemas only. The frozen
Phase-4 `api/v2_service.py` is untouched; `api/main.py` gained the
authorized additive replay-router include (2 lines).

## 4. Timeline Semantics

- One `ReplayFrame` per exact unique `state_time_s` per race.
- Canonical order `(state_time_s, lap_number, driver_id)`.
- Representative at a shared T = the row first in
  `(lap_number ASC, driver_id ASC)`.
- `ReplayFrame` exact anchor identity: `race_id`, `frame_index`,
  `anchor_driver_id`, `anchor_lap_number`, `anchor_state_time_s`,
  `replay_contract_version`.
- `frame_index` is dense `0..N-1`; T strictly increases; navigation is
  index arithmetic (no wraparound; `None` at bounds).
- The real shared-T case `2020-r09-R @ T=2974.257` (Tuscan GP restart)
  resolves to `giovinazzi`/lap 6 (`track_state=yellow`), not
  `latifi`/lap 7 (`safety_car`); the non-representative row owns no frame.

## 5. Factual Reconstruction Semantics

`ReplayFrame -> to_anchor() -> frozen RaceStateReconstructor.reconstruct()
-> RaceState`. No nearest match, no rounding, no future fall-forward; a
miss is an explicit error. Each driver uses its latest observable state
`<= T`; stale drivers keep their last factual observation plus
`observation_age_s`; pre-first members are explicit full nulls;
retirement is never inferred from staleness; partial races are never
synthetically extended. `leader_lap` is always leader progress, never the
anchor driver's own lap.

## 6. Prediction Checkpoint Architecture

Actual model evaluations happen only at selected checkpoints (contract
v1): every leader-lap transition plus meaningful track-state regime
transitions. Overlap produces one checkpoint with deterministically
sorted multiple reasons (`LEADER_LAP`, `FLAG_TRANSITION`). Selection is
model-free: it reads only the representative row's leader progress and
`track_state` token, and never imports the engine or feature bridge.

Measured served corpus: 149 races, 9,644 checkpoints, mean 64.72/race.

## 7. Offline Cache Architecture

Checkpoints are generated offline by
`scripts/build_replay_prediction_cache.py` and stored as immutable
per-race JSON artifacts under `results/v2_replay/checkpoints/{race_id}.json`
(gitignored, reproducible, tens of MB for a full backfill). The artifact
records the frozen `ModelIdentity` once and each checkpoint snapshot
verbatim. Publication is atomic (temp file + `os.replace`); incomplete,
stale, or corrupt artifacts are rejected on read; the read path never
generates. The cache key includes the replay/prediction/Phase-4 contract
versions, race identity, series identity, ALL_84/v8, serving-artifact
SHA-256, spec fingerprint, Phase-2 content hash, canonical data identity,
and `INDEPENDENT_BINARY`.

## 8. HTTP API

Four additive read-only GET routes under the existing `/v2` namespace:

```
GET /v2/races/{race_id}/replay/timeline
GET /v2/races/{race_id}/replay/frames/{frame_index}
GET /v2/races/{race_id}/replay/predictions/{frame_index}
GET /v2/races/{race_id}/replay/probability-timeline
```

Error mapping mirrors Phase-4 conventions: unknown race (incl. any 2025
id) → `404 unknown_race`; unknown frame → `404 unknown_frame`;
non-checkpoint prediction → `404 not_prediction_checkpoint` (with
nearest-checkpoint pointers, never a past-prediction substitution);
missing/stale/incomplete/corrupt cache → `503 prediction_unavailable`
with an explicit reason; malformed index/pagination → `422`; otherwise
`500 internal`. Bodies never carry traces, paths, or model internals. The
compact frozen contract is `docs/PHASE5_REPLAY_API_CONTRACT.json`.

## 9. Frontend Replay Architecture

`frontend/lib/v2.ts` is the typed V2 client; `frontend/features/replay/`
contains a React-free replay machine (`replayMachine.ts`), a React-free
probability projection (`probabilityTimeline.ts`), the `useReplay` hook,
and the replay components (`RaceSelector`, `TimelineScrubber`,
`PlaybackControls`, `StandingsTable`, `ContextBar`, `PredictionPanel`,
`ProbabilityTimelineChart`, `ReplayView`) plus
`frontend/app/replay/page.tsx`. The legacy prediction feature and
`lib/api.ts` are untouched. The client owns the playback clock
(step-based, one frame fetch outstanding at a time, bounded 200-entry
cache, stale-response guard). It renders only served races and never
invents frames, probabilities, or retirements.

## 10. Probability Timeline

`build_probability_timeline` projects an already-validated artifact into
one point per `(driver_id, ACTUAL prediction checkpoint)`. There is no
frame expansion, no resampling, no interpolation, no forward/backward
fill, and no nearest-checkpoint substitution; the projected frame set
equals the stored checkpoint set. Null stays null (never 0.0); the
complete roster is preserved; independent binary values pass through
verbatim (`INDEPENDENT_BINARY`). Lines in the UI connect measured points
only as rendering.

## 11. Scientific Integrity / Temporal Leakage Controls

- `RaceState` construction enforces `observed_time <= T`; frozen sync and
  F6 gap geometry use each member's own observed clock.
- Checkpoint selection reads only factual columns; the projection and the
  read path never touch the engine.
- Adversarial tests poison strictly-future rows (position, lap, tyre,
  stint, pit, weather, RC/flags, leader lap): current-T `RaceState`
  bytes, frame identity, and checkpoints `<= T` are unchanged.
- **No leakage was detected under the implemented adversarial test
  suite** (this is not a proof beyond it).
- **R6 introduced no new inferred probability observations.**
- **Prediction probabilities are independent binary estimates and are not
  normalized across the field.**
- **Historical prediction cache generation is an offline operational step
  and was not performed as part of the software freeze.**

## 12. Edge Cases

| Case | Verified behavior |
|---|---|
| Shared T (2020-r09-R) | deterministic representative; `yellow` context; non-representative row has no frame |
| Pre-first observation | explicit full nulls; anchor observable; complete roster retained |
| Stale driver (2022-r07-R) | observable with positive `observation_age_s`; no retirement inferred |
| Partial race (2021-r12-R) | 60 frames, leader max 3; jump-to-4 raises; no synthetic extension |
| Red flag (2022-r18-R) | `flag_red` / `red_flag` verbatim; seconds gaps null + invalid |
| Safety car (2020-r09-R) | `flag_safety_car` / `safety_car` verbatim |
| VSC (2018-r01-R) | `flag_vsc` + `vsc` / `vsc_ending` tokens verbatim |
| Lapped/late field | members keep their own observed laps; never forced to anchor lap |
| 2025 | 404 `unknown_race` on all replay routes; never served |

## 13. Performance

Controlled R7 benchmark (model-free, 30 samples, this machine; ms):
timeline cold 2.73 (p95 2.75), timeline warm ~0.00, checkpoint selection
3.83, reconstruction early 0.66 / ordinary mid–late ~37, red 22.6,
shared-T 34.2, artifact load 1.38, cached prediction 0.68,
probability projection 1.53, timeline HTTP pagination 4.38, frame HTTP
38.8 (p95 39.5), cached prediction HTTP 0.87, probability timeline HTTP
2.82 (p95 4.01). Leader-lap backend helper `frame_for_leader_lap` measured
~374 ms (reconstruct-per-probe); it is not exposed by any endpoint
(frontend probes client-side).

Target assessment: frame `< 100 ms` p95 **MET** in the controlled R7
environment; timeline `< 1 s` **MET**; cached HTTP `< 250 ms` **MET**;
frontend transition `< 200 ms` **NOT DIRECTLY MEASURED** (no browser
harness; structurally supported by the backend frame HTTP p95 plus
paint). Representative values are not universal guarantees.

Memory (R7-T, RSS, 6-race slice): after imports 93.0 MB, after
corpus+reconstructor 213.5 MB, service init 213.5 MB (shared references,
no copy), all 6 timelines 215.1 MB, 100 frame requests 215.4 MB,
probability timeline 215.5 MB. No unexpected monotonic growth.

## 14. Testing / Verification

- R8 freeze seal: `tests/test_v2_phase5_freeze.py` — pins contract
  versions, the four routes, the API-contract artifact against live
  routes, the representative rule, the shared-T critical fixture, served
  scope and 2025 exclusion, checkpoint policy identity, the model-free
  149/162,728/162,639/9,644 corpus facts, `INDEPENDENT_BINARY` / no
  normalization, the read-only cache boundary, actually-evaluated-only
  probability grain, null != zero, frontend/backend field compatibility,
  freeze-manifest identities, the authorized `api/main.py` drift, and the
  upstream frozen identities.
- Phase-5 domain suites: `test_v2_phase5_r1..r7` — 348 passed, 5 skipped.
- Phase-4 frozen gates: all green except the single **authorized**
  `api/main.py` hash drift (the additive replay-router include); every
  other Phase-4 pinned path is byte-identical.
- Frontend release gate: `node --test` over all six suites — **62 passed,
  0 failed**; TypeScript `tsc --noEmit` clean; ESLint **0 errors, 1
  pre-existing warning** in the untouched legacy `ResultCards.tsx`;
  production `next build` green with the `/replay` route prerendered.
- Full repository Python suite run exactly once at the freeze gate:
  **1,926 passed, 5 skipped, 4 xfailed, 1 failed in ~58 min (3,524 s)**.
  The single failure is the authorized Phase-4
  `test_frozen_module_hashes_match` `api/main.py` drift; the 5 skips are
  the documented R7 non-checkpoint edge cases; the 4 xfails are the
  pre-existing Monaco-2022 NaN cases (unchanged).
- Data/scientific validator: D11 (tests/fresh-env/frontend-build skipped
  to avoid duplicating the gates above) — every data/scientific section
  passed; the only pre-commit failures are the `LEGACY`/`GIT` hygiene
  signals caused by the not-yet-committed Phase-5 files, which resolve on
  commit. No data/scientific failure and no blocker after the freeze
  commit.

## 15. Operational Cache Workflow

```
python scripts/build_replay_prediction_cache.py --race-id 2023-r01-R --dry-run
python scripts/build_replay_prediction_cache.py --race-id 2023-r01-R
python scripts/build_replay_prediction_cache.py --season 2023
python scripts/build_replay_prediction_cache.py --all-served-races
```

Default behavior resumes by skipping valid-complete artifacts (`--resume`
is the explicit marker); `--force` regenerates; `--max-checkpoints`
produces validation subsets. Dry-run verified live: 2023-r01-R = 61
checkpoints (57 leader + 4 flag); 2023 season = 22 races / 1,412
checkpoints. Full expected: **9,644** checkpoints / 149 races, ~29–30
serial CPU-hours, ~90 MB storage (estimates from R3 arithmetic, not work
performed). Before backfill: factual replay fully works; prediction
endpoint and probability timeline return `503 cache_missing`. After a
valid artifact: prediction HIT and probability timeline verified with
controlled/synthetic artifacts.

## 16. Known Limitations / Technical Debt

1. Full prediction cache **not generated**: ~9,644 checkpoints, ~29–30
   serial CPU-hours estimated, ~90 MB estimated.
2. Prediction and probability endpoints return `503 cache_missing` until
   the relevant race artifact exists.
3. Leader-lap client jump may require ~11 frame probes typical/worst
   observed, bounded by 40.
4. Backend helper `frame_for_leader_lap` measured ~374 ms and is not
   exposed by any endpoint.
5. Frontend transition `< 200 ms` not directly browser-benchmarked.
6. Any existing Monaco-2022 Phase-4 xfails remain upstream debt.
7. The legacy `ResultCards.tsx` ESLint warning remains (untouched).
8. The full-field frozen feature path remains ~12 s/snapshot; Phase 5 does
   not optimize it (frozen).

## 17. Frozen Contract

Contract v1 (see `docs/PHASE5_FREEZE_MANIFEST.json`): `ReplayFrame` /
`ReplayTimeline` and the representative rule; `ReplayReconstructor` exact
`state_at` and navigation; `PredictionCheckpoint` / `CheckpointSeries` /
`select_checkpoints`; cache identity and artifact envelope; the four
read-only replay routes and error mapping; `ProbabilityTimeline`
projection and its identity; `INDEPENDENT_BINARY`, no-normalization,
null != zero, actual-checkpoints-only grain; the 2018–2024 scope with the
2025 firewall. Later phases may build on these; they must not casually
mutate them.

## 18. Phase-6 Readiness

Phase 5 is frozen and provides the seams Phase 6 needs: canonical replay
timelines and `ReplayFrame` navigation, the frozen `RaceState`, frozen
prediction snapshots and the probability timeline, and a documented
offline cache contract. The Phase-6 handoff
(`docs/PHASE6_MONTE_CARLO_HANDOFF.md`) states the distinction between
Phase-5 independent binary probabilities and Phase-6 mutually exclusive
simulated outcomes, and enumerates the Phase-6 R0 architecture questions.
Phase 6 was NOT implemented here.
