# PHASE 12 — SPATIAL TRACK REPLAY — FINAL REPORT

## Final verdict

PHASE 12 COMPLETE — FROZEN — READY FOR V3

Nine stages (P12-0…P12-8) built a causal historical spatial track replay
integrated into the frozen replay product, validated end-to-end
(corpus → geometry → resolver → API → renderer → synchronized ReplayView
→ race-status context), cross-checked against an independent external
circuit source, and frozen in one commit + annotated tag. Zero backend
changes after P12-5; zero predictive surface touched; six scientific
identities exact; full Tier-3 regression green.

## Scope

P12-0 architecture audit; P12-1 contract/governance; P12-2 observation
ingestion (173 Tier-A sessions); P12-3 circuit+pit geometry; P12-4 causal
resolver; P12-5 frame-index-bound API; P12-6 SVG renderer; P12-7 replay
integration (one clock); P12-8 race-status context. Explicitly out:
sector polygons, pit-now/retirement semantics, trails, marker selection,
external SVG runtime use, predictions/strategy changes, v3 work.

## Baseline

Frozen pre-Phase-12 baseline `post-v2-clean-baseline`
(`218f4a653f8e7148d06fefc69798053b275795bc`); HEAD exact at P12-9 entry.
Freeze commit has exactly this parent; tag `phase12-spatial-replay`
points at the freeze commit; `v2-final` and `post-v2-clean-baseline`
unmoved; nothing pushed.

## Architecture

Historical source/cache → P12-2 observations → P12-3 geometry → P12-4
causal resolver → P12-5 API → P12-6 renderer → P12-7 ReplayView →
P12-8 status strip. Binding: `currentFrameIndex` → ReplayFrame →
`anchor_state_time_s` → spatial resolver. ONE CLOCK. Dependency
directions verified (api → raceintel.spatial; ReplayView →
SpatialTrackPanel → useSpatialTrack → spatial client → P12-5 HTTP;
RaceControlState → raceStatus view-model). No spatial→api, no
predictive↔spatial coupling, no cycles introduced.

## Data provenance

FastF1 3.7.0 session cache (local, read-only) → D5/D6 canonical state →
D7 as-of enrichment → D9 derived tokens → frozen replay artifacts →
spatial observation parquet (per-race, atomic snappy, content-hashed) +
geometry JSON (telemetry-derived centerline + pit branch + render
transform). Message text excluded from domain; untimed race-control
messages never attach; asymmetric pit boundaries preserved.

## Observation corpus

173 authoritative Tier-A sessions; 170 persisted parquet artifacts: 164
COMPLETE, 6 PARTIAL, 2 source-UNAVAILABLE (2018-r01-R, 2018-r02-R),
1 FAILED = 2024-r09-R (120 non-sentinel pre-roll positions at negative
session time violated the frozen contract — preserved, never fixed or
suppressed). Manifest identity
`87797e3f…2fc1` re-verified (byte-exact). 106,757,556 kept rows from
118,648,369 raw. data/spatial ignored, untracked (`git ls-files`
empty). No regeneration in P12-9.

## Geometry corpus

170 geometries / 3 skipped (the two unavailable + r09). 168 pit
supported, 2 deferred (2021-r12-R, 2021-r19-R). Manifest identity
`6329b205…c786` re-verified (byte-exact). 512-point main centerlines,
128-point pit branches, normalized render transform, source-hash
linkage. No regeneration in P12-9.

## Temporal resolver

Latest observation ≤ T (searchsorted); FRESH ≤3 s, STALE (3,15] s,
UNAVAILABLE >15 s or none; before-first unavailable; coordinates and
transform preserved verbatim; outside-viewport unclamped; geometry
mismatch fail-closed; 2025 low-level resolvable, never served.
Focused suites green (incl. future-poison, boundary, no-future
property tests).

## API

`geometry / frame/{i} / window/{i}` — frame-index bound, served-race
eligibility, driver universe from live RaceState, geometry identity,
bounded payloads (frame 4.6 KB, geometry 27.7 KB, 5 s window 2.1 KB),
strict input bounds (422, no tracebacks/paths), PARTIAL served,
r09 404 `spatial_unavailable`, 2025 404 `unknown_race`, traversal-safe,
OpenAPI-listed. No redesign in P12-9.

## SVG renderer

Deterministic `svg = render × 1000` mapping, neutral circuit + pit
branch, exact-coordinate markers (FRESH solid / STALE dashed / no fake
for UNAVAILABLE), labels/paint-order never move dots, PARTIAL note,
loading/error/unavailable/integrity states, `role=img` + per-frame
label, discrete updates only, no dependencies.

## Replay integration

Single `currentFrameIndex` drives ReplayFrame + predictions + spatial
frame. Race-scoped geometry (once/race), exact-index frames
(`race|index` cache, bounded 200), abort + generation-ticket +
live-coordinate admission, governed pending cue, panel retries, failure
isolation (r09 replay usable). No second clock, no prefetch, no trails,
no marker clicks.

## Race-status context

`RACE STATUS` chip (GREEN/YELLOW/SAFETY CAR/VIRTUAL SC/RED FLAG/STATUS
UNKNOWN) + filtered `RC {YELLOW,DOUBLE YELLOW,RED}` line, from the
current frame's causal RaceControlState. Zero new requests/bytes.
Sector/pit-now/retirement/session surfaces deferred or rejected on
evidence. Geometry stays neutral; never colour-only.

## One-clock invariant

`currentFrameIndex` is the single replay position; spatial
`query_time_s === anchor_state_time_s` exact; status shares T by frozen
construction. Re-audited 40/40 exact (P12-9 seed-99 sample).

## Causality guarantees

Every temporal lookup backward-only (≤ T): resolver searchsorted,
D7 as-of joins, frozen lap-boundary tokens, no nearest-future, no
interpolation, no prefetch. Independent random audit (seed 1209, 8
races × 25 driver×T queries vs direct dataframe mask): 200/200,
0 mismatches. Boundaries: pre-event frame shows previous state, first
T ≥ E shows new state — verified for yellow/VSC/SC/red/restart.

## External circuit cross-validation

julesr0y/f1-circuits-svg (rev `9c93759`, CC BY 4.0, /tmp clone,
validation-only, removed afterwards, never vendored/runtime).
Historical layouts matched per season metadata (incl. melbourne-2 for
2023, bahrain-1 GP, monaco-6, suzuka-2, monza-7, spa-4, silverstone-8,
zandvoort-5). Method: SVG path sampling + arc-length resampling +
Procrustes (flip/reversal/cyclic-shift search) — orientation/scale free.
Results: 7/8 ≤ 0.008 (near-coincident; Suzuka crossover, Monaco harbour,
Melbourne-2022 layout all confirmed); Bahrain 0.041 investigated per
disagreement policy → both shapes recognizably Bahrain GP, P12-3 follows
the raw telemetry envelope point-for-point (independent source check),
delta attributed to artistic infield proportions — NOT a P12-3 defect,
geometry stays authoritative. No pixel equality claimed; topology,
loops, turns, straights, closure all agree; no chords, no false
connections.

## Pit-lane validation

Telemetry-derived branches revalidated against raw pit-traversal
segments (D9 `pit_in_s` windows) for Bahrain/Monaco/Japan/Australia:
entry divergence, box/slow region, rejoin all follow the branch;
markers unsnapped. External SVG not used for pit (metadata
insufficient).

## Product eligibility

149 served races (2018–2024) via existing eligibility; spatial served
only through it. 2025 resolvable internally, publicly rejected
(`unknown_race` verified live).

## 2025 firewall

No 2025 endpoint path, no 2025 frontend call, no 2025 geometry served;
P12-5 HTTP policy authoritative. Firewall tests green.

## Failure / partial-data behavior

r09: spatial-unavailable panel, replay + GREEN status strip intact.
PARTIAL: markers for available drivers only, `N NO FIX` + coverage
note, status independent. Errors: panel-scoped + retry, never cached
poisonously. Integrity mismatch: markers withheld.

## Performance

Offline builds: ingestion 1766 s full / ~11 s per golden race
(resume 400 s); geometry 1983 s full / ~11 s per race. Cold race load:
frame ~2.1 s, geometry lazy per race ~2.5 s (loading states, replay
usable). Warm: resolver 0.16 ms, replay frame 39 ms, HTTP frame ~41 ms
(median 37.5 ms over 10). 100 warm frames 3.5 s. Frontend: one flex-row
strip, no measurable render cost; no FPS claims; no animation.

## Storage

Observations 563.6 MB total (median 3.5 MB/race, p95 4.3 MB) —
P12-0's rough estimate superseded by full-fidelity P12-2 measurement
(documented, not a failure). Geometry 16.0 MB (~35× smaller). Manifests
0.3 MB. All ignored/generated; tracked records carry identities only.

## Testing

Phase-12 focused suites all green (contracts, ingestion, geometry,
resolver 45 incl. poison, API, firewall, renderer/client,
integration 13 incl. 10-11-12 out-of-order gate, status 5). Frontend
selector green incl. P12-6..8 tests (manifest exact). tsc/lint/build
green. Backend CI selector 2677 passed (P12-7 evidence, no backend
changes since). Full Tier-3 regression: see below. Browser matrix
(wide/tablet/390 px × green/yellow/red/unavailable/partial/first/last/
rapid/race-switch): zero page errors, zero overflow, labels intact.

## Predictive firewall

ALL_84 = 84 (firewall test green, no spatial names). Graphify +
source scans: spatial/status touch no features, model_lab, winner
model, simulation, strategy, explainability. No predictive artifact
changed (identities exact).

## Scientific identities

6/6 exact, reverified without regeneration (see machine record).

## Security / input validation

Bounds enforced (frame/driver/history 422s), traversal-safe routing,
2025/unknown 404s, sanitized error bodies, no path/traceback leakage,
no filesystem exposure. Scope kept to the spatial surface.

## Accessibility

Track `role=img` + per-frame label + `<title>`; status `role=status`
with text (never colour-only); loading/error states announced;
single h1; existing replay keyboard controls untouched; no meaningless
primitive exposure.

## Responsive validation

1600/820/390 px verified: no distortion, no page overflow, tower
usable, track legible (356×356 at 390 px), status strip wraps.

## Reproducibility

`scripts/build_spatial_observations.py` + `build_spatial_geometry.py`
= PRODUCTION/REPRODUCIBILITY (kept); `probe_spatial_{api,resolver}.py`
= DIAGNOSTIC_WORTH_KEEPING (report evidence tooling, kept).
`/app/spatial` harness KEPT as deliberate diagnostic/demo surface
(no nav link, no inappropriate exposure, small surface). No temporary
files retained in repo; /tmp clones/screenshots removed or outside
repo and never committed.

## Product claims

Supported: historical spatial replay; causal lap/frame-synchronized
driver positions; telemetry-derived circuit geometry; historical
race-status context; served 2018–2024. Refused: real-time, live
telemetry, GPS-accurate, exact physical track map, sector-level flags.

## Known limitations

r09 spatial unavailable (frozen contract); six PARTIAL races; two
source-unavailable races (no geometry); two deferred pit geometries;
no sector polygons/local-yellow overlay; no pit-now marker state; no
retirement/stopped UI; no safety-car vehicle; no future-aware
interpolation; trail deferred; marker selection deferred; 2025 not
served; lap-boundary status granularity; dev CORS needs localhost:3000.

## Deferred work

v3 handoff: marker interactivity, selected-driver trail, pit/retirement
semantics only with authoritative sources, sector geometry only with
real polygons, harness retention review, cold-load prefetch only with
evidence. P12 decisions 1–24 frozen (see mission); reopen only on a
proven correctness failure.

## Repository freeze

One commit `feat(spatial): add causal historical track replay`,
parent = post-v2-clean-baseline, tag `phase12-spatial-replay`
(annotated) → HEAD exactly. `v2-final`, `post-v2-clean-baseline`
unmoved. Nothing pushed. Worktree clean (ignored data/spatial
untracked only). No data/spatial, screenshots, clones, or secrets in
the freeze set.

## v3 handoff

Spatial replay is a frozen, validated product surface. v3 (Race
Dynamics / MC2.0 / ensembles) must treat P12-0..8 contracts, corpora,
and firewalls as immutable inputs; any geometry/resolver change
requires a new phase, never a silent edit.
