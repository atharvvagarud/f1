# PHASE 12 P12-0 SPATIAL DATA + ARCHITECTURE AUDIT

> Audit and design only. No track implementation, no ingestion, no
> source changes, no dependency changes, no artifact regeneration.
> Baseline `post-v2-clean-baseline` untouched. Nothing staged,
> committed, tagged, or pushed.

## Final verdict

**P12-0 COMPLETE — GO WITH CONSTRAINTS — READY FOR P12-1**

Phase 12 spatial track replay is technically justified: position data
is already local for ~171 race sessions, the replay clock provably
shares the FastF1 session clock (measured delta ~0.1s), storage is
trivial (~1.3MB per race compact), and the architecture isolates the
frozen predictive pipeline. Constraints: causal-only sync, staleness
explicitness, race-wide flag fallback, 2025 firewall reuse, no
spatial-to-science leakage (separate approved phase required).

## Baseline

- HEAD `218f4a653f8e7148d06fefc69798053b275795bc` =
  `post-v2-clean-baseline^{commit}`.
- Tracked tree clean, nothing staged, before and after the audit.
- C0–C6 closed; v2 frozen; this audit adds only
  `results/phase12/p12_0_spatial_audit.json` and this report
  (both untracked, uncommitted).

## Repository safety

Read-only evidence gathering: file reads, FastF1 cache inspection,
local parquet reads, one `/tmp` measurement write (outside the repo).
No source, test, config, dependency, or dataset mutation. No full
ingestion. Targeted samples only.

## Graphify

- `graphify update .` run; no code-graph topology changes detected
  (outputs left untouched): **11583 nodes / 27974 edges /
  339 communities**.
- Targeted queries mapped the replay flow before opening source
  trees; exact search covered imports, clocks, caches, and contracts.

## Current replay architecture

Historical corpus (`data/v2/processed/driver_lap_state`, Tier-A)
→ `raceintel/race_state` (frozen reconstructor, anchor identity)
→ `raceintel/replay` (timeline, frames, predictions, probability
timeline) → `api/v2_replay_*` (read-only service facade over
2018–2024 served races; 2025 unknown) → `frontend/features/replay`
(`useReplay`, scrubber, playback controls, panels) backed by the
`results/v2_replay` prediction cache (149 races / 9644 checkpoints).
Replay cache generation lives in
`scripts/build_replay_prediction_cache.py`; the read path never
generates (cache miss raises, offline backfill resolves).

## Replay time semantics

- A replay frame is `ReplayFrame`: `race_id`, dense `frame_index`,
  `anchor_driver_id`, `anchor_lap_number`, `anchor_state_time_s` —
  one frame per exact unique `state_time_s`, never reordered,
  invented anchors rejected (422, no fall-forward).
- `state_time_s` is the D9 lap-end clock in float session seconds.
- Checkpoints are frames carrying cached R3 prediction artifacts;
  predictions are fetched only at checkpoints.
- Previous/next/first/last navigation has no wraparound; timeline
  construction rejects mixed races, mixed versions, non-dense
  indices, and unordered input.
- **Authoritative coordinate for spatial replay:
  `anchor_state_time_s`.** Lap number alone is insufficient (many
  states share a lap); the session-second clock is exact and dense.
- Frontend clock is a single authoritative `currentFrameIndex` in
  `useReplay` with exact fetches and abort/stale protection.

## FastF1 spatial sources

- Installed FastF1 **3.7.0** (pinned in `requirements.txt`).
- Spatial coordinates live in the **position stream**
  (`position_data`): per-driver frames keyed by driver-number
  string, columns `Time` (session-seconds timedelta), `Date`
  (absolute UTC), `Status`, `X`, `Y`, `Z`, `Source`.
- Companion streams in the same session cache: `car_data`
  (`RPM/Speed/nGear/Throttle/Brake/DRS`, same clock),
  `track_status_data`, `race_control_messages` (UTC, sector-scoped
  flags), `session_status_data`, `lap_count`, `weather_data`.
- Phase-1 loads full sessions but never promotes position or
  telemetry to canonical storage — spatial data is cache-only
  today, which is exactly the P12-2 ingestion gap.

## Existing local data

- `data/raw/fastf1_cache`: **~15GB, 1900 `.ff1pkl` files**,
  seasons 2018–2025, every race session carrying
  `position_data.ff1pkl` plus car/track-status/race-control/
  session-status companions.
- Tier-A canonical corpus present locally
  (`data/v2/processed/driver_lap_state*`) with `driver_number`,
  `state_time_s`, per-lap `track_status`, and `pit_in_s/pit_out_s`
  columns — the join base for spatial work.
- Nothing mutated or regenerated; `runtime_artifacts/` untouched.

## Sample-race evidence

- **2023 Bahrain** (dry baseline): 20 drivers, ~37k rows/driver
  over 9660s → **9505 unique timestamps (~0.98Hz)** after exact-
  duplicate removal; max unique gap 3.6s; zero NaNs; all
  `Status=OnTrack`, `Source=pos`; X/Y int metre-scale, Z coarse
  (169 unique, noisy).
- **2021 Monaco** (street circuit): all 20 drivers identical row
  counts and end time; retiree BOT frozen at one X/Y late
  (`late_Xuniq=1` vs runners ~5k) — frozen tail, not missing data.
  HAM pit window (state 4207.7s) holds 204 continuous rows over 45s
  with a 10-row `Speed==0` box stop: pit trajectories present, no
  teleport gaps.
- **2024 Japan** (red flag): track-status stream shows
  AllClear→Yellow→Red→AllClear→Yellow→AllClear; race control
  carries sector-scoped yellows plus the red; session status shows
  Aborted→Started restart capability.
- **2023 Australia**: full flag vocabulary in one race —
  AllClear/Yellow/SC/VSC/VSC-ending/Red.
- **Clock identity (decisive)**: lap-counter lap-2 transition at
  pos-Time **2056.896s** vs VER lap-1-end `state_time_s`
  **2056.8s** — the replay clock IS the FastF1 session clock
  (delta ~0.1s). No offset calibration needed.

## Coverage

Position-data sessions: 2018:19, 2019:21, 2020:17, 2021:22,
2022:22, 2023:22, 2024:24, 2025:24 — near-complete
DATA_AVAILABLE for the Tier-A era against 149 served replay races.
2025 sessions carry data but stay PRODUCT_NOT_SERVABLE. No full
coverage claimed beyond the counted sessions; per-race driver/time
completeness is a P12-2 manifest measurement.

## Coordinate semantics

X/Y metre-scale on an event-specific arbitrary origin (negatives
common; spans match circuit scale plus offset). Axes and orientation
are event-specific — translation/rotation/reflection must be derived
per event, never assumed. X/Y suffice for 2D rendering after
per-event normalization; no lat/lon source needed. Z is coarse and
noisy — retained optionally, not rendered.

## Circuit geometry

Recommended: derive a representative racing-line trace from the
historical X/Y observations themselves (segment-wise median with
outlier rejection), keyed per `race_id` and shared across years only
on identical hash. Exclude pit branch (pit windows + `Speed==0`),
formation/cooldown laps, off-track noise. No third-party map
(licensing/projection risk); FastF1 circuit metadata only as
supplementary bounds. Sector-to-segment painting needs marshal-sector
geometry — not yet available — so race-wide SC/VSC/red indicators
are the defensible P12 default.

## Temporal synchronization

At replay time T, each car uses the latest observation with
`position_time <= T` — never nearest, never future interpolation,
never lap-end backfill. The measured clock identity makes the join
direct: `anchor_state_time_s` against deduped per-driver series.
Rendering may tween between already-known samples during playback,
but interpolated values never enter scientific state.

## Staleness

Per-driver `age = T - observation_time`, rendered distinctly as
FRESH / STALE / UNAVAILABLE. Evidence-grounded proposal: FRESH ≤3s,
STALE ≤15s, else UNAVAILABLE (max unique gap ~3.8s across samples).
Retirement/session-end freezes are resolved via RaceState status
join, never inferred from coordinates alone.

## Pit lane

Pit trajectories are present in the feed (continuous, with box dwell
detectable via `Speed==0`); branch-vs-main separation is P12-3
geometry work. Cars must be shown entering the lane, never
teleporting. Garage vs circuit ambiguity is resolved with pit
windows and status, not coordinate guessing.

## Retirement / missing data

Retired drivers freeze at last position with full row padding —
detectable as zero-variance runs but classified only via RaceState
status. Session-end parc fermé freezes all cars identically. Missing
telemetry must surface as UNAVAILABLE, never as a fabricated mark.

## Race control

`track_status` codes observed end-to-end (1/2/4/5/6/7 with FastF1
documented meanings). Race-wide SC/VSC/red/yellow indicators are
fully supportable on the replay clock. Sector-level painting is
possible at the message level (`Scope=Sector`) but spatial sector
polygons await geometry work — deferred to P12-8 with the race-wide
fallback as default.

## Driver identity

Canonical join is `(race_id, driver_number)`: corpus
`driver_number` matches position-stream keys; `driver_id` slug and
abbreviation serve display. No display-name joins. Time join needs
no offset (measured ~0.1s agreement).

## Proposed spatial data contract

`SpatialObservation`: race/driver identity, observation time (float
session seconds), X/Y metres in event frame, optional Z,
availability state. `CircuitGeometry`: race/layout identity,
normalized aspect-preserved polyline, optional pit path, bounds,
transform metadata. Final fields in the JSON artifact; schemas
themselves are P12-1.

## Storage estimate

Measured (Bahrain 2023, 190k dedup rows → 1.35MB snappy, 1.27MB
zstd): **~1.3MB per race compact**, ~200MB for 149 races, ~500MB
raw-ish upper bound; geometry tens of KB per race — well below
existing data scales. Assumptions documented in the artifact.

## Replay performance architecture

Recommended hybrid **D**: static per-race geometry asset +
windowed trajectory endpoint + exact frame endpoint, all on the
existing `frame_index` clock. No WebSockets (historical replay does
not need them); no per-tick polling storms; seeks are exact frame
fetches; playback speed scales client-side within known windows.

## Backend architecture

New `raceintel/spatial/` package (loader, temporal resolver,
geometry resolver, normalizer, availability/staleness, serial
contracts) behind a read-only replay-style service facade reusing
`served_race_ids` eligibility. It may import replay time identity
types only — never features, model_lab, simulation, strategy,
explainability, or labels.

## API design

Evaluate `spatial/geometry` (tiny, cacheable), `spatial/frame?time=`
(~20 rows), `spatial/window` (capped compact trajectories), plus a
race-wide flag endpoint from the track-status stream. No giant JSON
tables; 2025 rejected identically to replay.

## Frontend renderer

**SVG recommended** (native, accessible, zero bytes, sufficient for
~20 markers + polyline + labels at 60fps); Canvas fallback only on
profiling evidence; WebGL rejected. Extends `useReplay` state —
clock, scrubber, playback, and driver selection stay unified with
prediction/explainability/timeline panels.

## Interaction model

Play/pause/speed/seek/checkpoint-jump/driver-select all drive the
one authoritative `frame_index` clock. Selected driver synchronizes
track marker with prediction, explanation, and timeline views. No
second clock.

## Predictive firewall

Separate package, separate artifacts outside the canonical corpus
and bundle manifests, separate DTOs, import-direction tests
mirroring existing firewall tests, D11 no-leak assertions. ALL_84,
winner model, simulation, strategy, and explainability stay frozen;
any spatial-as-feature work needs a separately approved phase.

## 2025 firewall

Spatial routes reuse `SERVED_SEASONS = 2018–2024` eligibility and
the shared unknown-race 404 path. 2025 data may exist and even be
ingested, but is never product-servable without an explicit future
phase change, tested by 2025-rejection contract tests.

## Acquisition plan

Same `fastf1.get_session` source Phase-1 uses (cache-first; only
uncached sessions hit network), manifest-driven resume, per-race
atomic parquet writes, schema v1, provenance (FastF1 version, file
hashes), failure/partial recording, deterministic normalization
(sort + dedup). No bulk acquisition in P12-0 (171/172 sessions
already cached regardless).

## Validation plan

Data (schema, bounds, monotonicity, identity join, dedup, pit
continuity, retirement+status, coverage, deterministic geometry),
sync (no-future causal property tests on golden races), API
(schema, 2025 rejection, budgets), frontend (golden snapshots,
staleness styling, single-clock), plus D11/firewall/identity gates.

## Golden cases

Bahrain 2023 (clean baseline), Monaco 2021 (street geometry,
retirement, pits, density), Japan 2024 (red flag, restart),
Australia 2023 (yellow/SC/VSC/red combined) — chosen for system
coverage, not narrative.

## Risk register

Thirteen risks (missing data, irregular rates, noise, pit geometry,
layout drift, bad joins, future leakage, storage, animation cost,
label collisions, stale markers, 2025 bypass, FastF1 drift) each
with LOW/MEDIUM/HIGH likelihood, impact, and mitigation in the
JSON artifact. No fake probabilities.

## Go / no-go

**GO_WITH_CONSTRAINTS**: causal-only sync; explicit staleness;
race-wide flags by default; per-race geometry; 2025 reuse of
existing firewall; zero science leakage. Constraints are
architectural, not placeholders.

## Proposed P12 stages

P12-1 contract → P12-2 ingestion → P12-3 geometry → P12-4 temporal
resolver → P12-5 API → P12-6 renderer → P12-7 integration → P12-8
status layers → P12-9 validation/freeze, each with mission, inputs,
outputs, tests, and STOP gate (full definitions in the artifact).
No stage executed.

## v3 extension boundary

Overtaking geometry, traffic models, spatial gaps, corner pace,
track-position strategy effects are future v3 research surface
only — explicitly not Phase-12 deliverables and never automatic
consumers of spatial data.

## Entry gate

- [x] HEAD = post-v2-clean-baseline, tag exact, tree clean,
  nothing staged
- [x] Graphify refreshed (11583/27974/339, topology unchanged)
- [x] replay time model documented (anchor_state_time_s authority)
- [x] FastF1 3.7.0 identified, position stream identified
- [x] real samples inspected (2018/2021/2023/2024)
- [x] coordinate semantics documented (metre-scale, event frame)
- [x] coverage counted (171 sessions; 2025 distinguished)
- [x] geometry approach evaluated (trace-derived, per-race)
- [x] causal sync designed, no-future rule explicit
- [x] staleness designed with evidence thresholds
- [x] pit-lane behavior measured (continuous + box dwell)
- [x] retirement/freeze behavior measured (status-join rule)
- [x] race-control feasibility documented (all codes observed)
- [x] identity join defined (race_id, driver_number; Δ~0.1s)
- [x] data contract proposed, storage measured (~1.3MB/race)
- [x] backend/API/frontend options evaluated, hybrid D + SVG
  recommended, one clock preserved
- [x] predictive + 2025 firewalls explicit; ALL_84, model,
  simulation, strategy, explainability unchanged
- [x] acquisition, validation, golden cases, risks, stages defined
- [x] GO_WITH_CONSTRAINTS evidence-based
- [x] no implementation, ingestion, source/dep/artifact changes
- [x] six identities exact, preflight green, JSON + report created
- [x] nothing staged/committed/tagged/pushed
