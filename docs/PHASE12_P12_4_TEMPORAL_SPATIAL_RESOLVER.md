# PHASE 12 P12-4 TEMPORAL SPATIAL RESOLVER

## Final verdict

P12-4 COMPLETE — resolver library, causal contract tests, probe,
evidence, and machine record are in place; P12-0/1/2/3 accumulations
are intact; focused tests and the spatial surface are green. P12-5 not
started.

## Baseline

- Frozen baseline: `218f4a653f8e7148d06fefc69798053b275795bc`
  (`post-v2-clean-baseline`); HEAD is exact at implementation time.
- Dirty work is only expected P12 accumulation: modified `.gitignore`
  + `scripts/run_ci_tests.py` (CI pin), untracked P12-0..P12-3 docs,
  `raceintel/spatial/`, `results/phase12/`, build scripts, and spatial
  tests. Zero UNKNOWN, nothing staged (see entry gate).

## Input identities

- Observation manifest identity: `87797e3f…` (164 COMPLETE,
  6 PARTIAL, 2 UNAVAILABLE, 1 FAILED, 106.76M observations).
- Geometry manifest identity: `6329b205…` (170 COMPLETE, 3 SKIPPED).
- Contracts consumed verbatim: `contracts.py` (availability
  thresholds, identity, seasons), `validation.py` (frame validation +
  logical content hash), `geometry.py` (`apply_transform`,
  content-hash, manifest rows), `io.py` (artifact/manifest paths),
  `manifest.py` (observation statuses).

## Replay clock

- ONE authoritative replay time: `T = anchor_state_time_s`
  (`ReplayFrame.anchor_state_time_s == RaceState.state_time_s`;
  `frame_index -> anchor` mapping is unchanged).
- The resolver takes `T` as a plain float; no lap clock, no
  wall-clock Date, no frame-relative or animation clock exists in
  `raceintel/spatial/`.
- P12-7 integration boundary: pass the live `RaceState` (or its
  `ReplayFrame`) through `universe_from_race_state()` and resolve at
  `race_state.state_time_s`. Not integrated yet (no replay imports in
  spatial; structural read only, dependency direction replay ->
  spatial preserved).

## Resolver contract

- New module `raceintel/spatial/resolver.py`
  (`RESOLVER_CONTRACT_VERSION = "spatial-resolver-v1"`).
- `SpatialDriverState`: race_id, driver_number (None for roster
  members without telemetry identity), driver_id (carried for P12-7
  presentation), query_time_s, observation_time_s / age_s (None when
  unavailable), availability, raw_x / raw_y (exact canonical),
  render_x / render_y (None without verified geometry), source /
  status (canonical provenance for P12-8), outside_viewport flag.
- `SpatialFrame`: race_id, query_time_s, observation/geometry
  identities, drivers tuple, fresh/stale/unavailable counts.
- `TrajectorySample`: causal window sample
  (time, raw, optional render).
- `DriverUniverseEntry`: (driver_number, driver_id), at least one
  required. No other fields were added (no consumer, no contract).

## Driver universe

- Replay-aware mode: explicit universe, caller order preserved as
  frame order (a live RaceState already normalizes to `driver_id`
  order via `universe_from_race_state()`).
- Observation-only mode (tests/tooling): sorted observation driver
  numbers.
- Coordinate availability and race participation stay distinct:
  retired/missing drivers get UNAVAILABLE rows, never dropped rows.

## Identity join

- Canonical key is `(race_id, driver_number)`; `driver_id` is carried,
  never joined on (no display name / abbreviation / team / array
  order anywhere in the path).
- `_check_universe` enforces one-to-one number <-> id mapping and
  fails closed (`SpatialIdentityError`) on ambiguity.

## Causal lookup

- Per-driver sorted float64 time arrays; latest-at-or-before via
  `numpy.searchsorted(times, T, side="right") - 1` (no linear scans).
- `side="right"` owns exact-timestamp equality to the earlier sample.

## Availability

- Frozen P12-1 helper reused (`classify_availability`): FRESH age <=
  3.0, STALE 3.0 < age <= 15.0, UNAVAILABLE otherwise. Boundaries:
  0/3 -> FRESH, 15 -> STALE, >15 -> UNAVAILABLE.
- Float note: exact decimal offsets do not survive session-clock
  addition (100.0 + nextafter(3.0) rounds to 103.0, age exactly 3.0 ->
  FRESH). Ownership is decided on the computed float age; tests pin
  exact 3.0/15.0 plus unambiguous 3.001/15.001 offsets.

## Before-first / after-last

- Before-first: UNAVAILABLE with the full missing-value
  representation (no backfill, no future coordinate).
- After-last: latest causal sample selected, then age governs
  (verified: last=100 -> T=102 FRESH, T=110 STALE, T=116
  UNAVAILABLE). Aged-out UNAVAILABLE keeps observation_time_s + age_s
  (audit provenance) with nulled coordinates.

## Retirement separation

- Resolver never infers retirement (not from missing/stale/frozen
  coordinates or telemetry cessation). `OffTrack` status with fresh
  age resolves FRESH with status preserved; RaceState/status stays
  authoritative and P12-7/P12-8 combine the two signals.

## Raw coordinate semantics

- Returned raw X/Y equal the selected canonical observation exactly
  (tested); no smoothing, interpolation, centerline/pit-lane
  snapping, or projection. Geometry is a visual reference only.

## Render transform

- The store's verified P12-3 transform is applied via the shared
  `geometry.apply_transform` (never recomputed, never per-frame
  fitted, never per-driver normalized). Same raw point -> same render
  point regardless of T (tested across query times).

## Geometry consistency

- Load pins `observation_content_sha256` against the manifest
  provenance, then requires the geometry record's
  `source.observation_content_sha256` to match and the geometry
  content hash to reproduce the manifest row.
- Mismatch -> `geometry_ok=False, geometry_stale=True`;
  render-space frames raise `SpatialGeometryMismatchError`; raw
  resolution keeps working with render None.

## Missing/partial races

- Observation manifest FAILED/UNAVAILABLE (or missing row/artifact)
  -> `SpatialArtifactUnavailableError` on load. 2024-r09-R (FAILED)
  and 2018-r01/r02-R (UNAVAILABLE) remain unsupported, untouched.
- No COMPLETE geometry (SKIPPED rows) -> render frames raise
  `SpatialArtifactUnavailableError`; `require_geometry=False` still
  yields exact raw frames (no invented render coordinates).
- PARTIAL races load with status preserved (never upgraded to
  COMPLETE); 6 PARTIAL races resolve causally per available driver
  with UNAVAILABLE gap rows (tmp-fixture test + corpus audit covers
  PARTIAL races in the 40-race sample).

## Query-time domain

- NaN/inf/non-numeric/bool -> `SpatialResolutionError` (mirrors the
  frozen replay clock's finite-only rule).
- Finite negative T is accepted and resolves all-UNAVAILABLE
  (canonical observations are non-negative; no causal sample exists).
- `history_s` must be finite and >= 0.

## Single-driver resolution

- `resolve_driver(store, driver_number, T, driver_id=None)`:
  independently tested primitive returning `SpatialDriverState`;
  unknown drivers and `driver_number=None` resolve UNAVAILABLE.

## Frame resolution

- `resolve_frame(store, T, universe=None, require_geometry=True)`:
  deterministic order (caller order, else driver_number-sorted),
  coverage counts, identity references embedded.

## Historical window

- `resolve_window(store, driver, T, history_s)` returns ascending
  `TrajectorySample`s within `[T - history, T]` (history-only, never
  `T + future`); immediate post-T samples are poison-tested out.
- Intended P12-5 consumers: short client trails / known-sample
  tweening. No API implemented here.

## Scientific/rendering boundary

- Scientific state = latest causal observation <= T (exact, frozen in
  the frame). Rendering may later animate between already-known
  states as the replay clock advances; P12-4 synthesizes nothing and
  offers no `t_next` interpolation. Future P12-6 animation must never
  mutate resolved states.

## Race-level store/cache

- `RaceSpatialStore.load(root, race_id)`: one race artifact ->
  validated, hashed, per-driver indexed arrays + verified transform.
  No per-frame Parquet reads, no global 563 MB preload.
- `SpatialStoreCache(max_races=4)`: bounded LRU keyed by race; every
  hit re-checks manifest identities AND artifact file stats
  (mtime/size) and reloads through the fail-closed load on any drift
  (a replaced parquet under an unchanged manifest reloads and raises
  provenance instead of serving stale index — regression-tested).
- Explicit `invalidate(race_id=None)`; identity-aware reload tested.

## Memory

Measured loaded-race memory (artifact bytes / DataFrame deep bytes /
indexed numpy payload bytes):

- 2023-r01-R (Bahrain 2023, 646470 rows): 3.33 / 149.33 / 25.86 MB
- 2021-r05-R (Monaco 2021, 739460 rows): 3.92 / 170.82 / 29.58 MB
- 2024-r04-R (Japan 2024, 744119 rows): 3.73 / 171.89 / 29.76 MB
- 2023-r03-R (Australia 2023, 887309 rows): 3.88 / 204.97 / 35.49 MB
- 2020-r15-R (largest artifact, 1184320 rows): 5.18 / 273.58 / 47.37 MB

A race-level resolver is backend-reasonable (tens of MB indexed; the
DataFrame intermediate dominates and is freed after indexing). No
micro-optimization undertaken.

## Performance

- Cold race load: 2.04 s (2023-r01-R; validation + indexing).
- Single warm frame (20 drivers): 0.20 ms.
- 100 sequential warm frames: 9.9 ms (~0.10 ms/frame).
- Single-driver lookup mean: 0.004 ms.
- Causal window (10 s, ~tens of samples) mean: 0.12 ms.
- Comfortably interactive; no optimization needed, no target invented.

## Golden-race validation

Validated against an independent pandas reference (boolean-mask max,
separate code path from searchsorted) on Bahrain 2023, Monaco 2021,
Japan 2024, Australia 2023 — before-first, exact sample, between
samples, late race, after-last, plus a Tier-A pit-window sample
(Bahrain Verstappen stop 1, T=5145.9785 -> obs 5145.836, age 0.14 s,
FRESH, raw (-337, 2253)): zero mismatches on all four races
(observation_time <= T, latest-causal, exact age/availability/raw,
render within 1e-12 of the stored transform).

## Random causal audit

- Deterministic seed 1204: 40 sampled COMPLETE/PARTIAL races x 8
  (driver, T) queries = 320 comparisons against the independent
  reference: zero mismatches.

## No-future property

- Property test over a synthetic time grid x drivers: every available
  state satisfies observation_time_s <= T and age_s == T -
  observation_time_s (>= 0). Future-poison fixtures (10.0/x=100 vs
  10.01/x=999999 at T=10.005, plus availability-edge and window
  variants) would fail on any nearest-neighbor regression.

## Monotonic property

- Increasing query times never decrease a driver's selected
  observation_time_s (tested on a synthetic stream).

## Availability statistics

30 s replay grid x all drivers (descriptive, thresholds frozen):

- 2023-r01-R: FRESH 98.69%, STALE 0.00%, UNAVAILABLE 1.31%
- 2021-r05-R: FRESH 100.00%, STALE 0.00%, UNAVAILABLE 0.00%
- 2024-r04-R: FRESH 98.72%, STALE 0.00%, UNAVAILABLE 1.28%
- 2023-r03-R: FRESH 95.98%, STALE 0.01%, UNAVAILABLE 4.01%

STALE ~0% is expected (max feed gap ~3.8 s; the 30 s grid rarely
lands inside a (3, 15] s age band except retired-driver tails, e.g.
Australia drivers 31/63 with >2000 s tails). No threshold change.

## Pit trajectory validation

- Bahrain 2023 Verstappen stop 1 (5133.83–5158.13 s): five resolver
  samples move from 48u off the main centerline to 21u off the pit
  branch (160u off main) — the raw pit trajectory is returned
  verbatim, never snapped to main_track or pit_lane geometry. FRESH
  throughout.

## Cache invalidation

- Reuse (same object), explicit invalidate, LRU eviction at the bound,
  and identity-change reload are unit-tested on tmp fixtures.

## 2025 firewall

- `SERVED_SEASONS == (2018..2024)` unchanged; resolver has no season
  gate (mathematics), so 2025 data resolves for validation while
  `is_product_servable(2025)` stays False. DATA_RESOLVABLE !=
  PRODUCT_SERVABLE; P12-5 owns the serving gate.

## Predictive firewall

- `resolver.py` carries no predictive/API/web imports (source-scanned
  in tests); no resolved coordinate enters any feature path;
  ALL_84 remains 84 (existing firewall test green, unchanged).

## Tests

- New `tests/test_spatial_resolver.py`: 62 collected nodes covering
  the Part AO inventory (boundaries, future-poison, before/after,
  3 s/15 s edges, negative-age, identity join/universe forms,
  missing/partial/mismatch/missing-geometry/missing-observations,
  ordering, window bounds, cache reuse/eviction/invalidation, no-future
  + monotonic properties, 2025 distinction, firewall, query domain).
- Synthetic series + tmp-dir fixtures only; corpus not required.
- CI pin: 3316 -> 3378 (+62, no removals, no weakening).

## Scientific identities

Reverified without regeneration (frozen test surface green, zero diff
on frozen paths):

- serving: `1116b34f…caa59f4`
- Phase-2 content: `d2ee966c…92799db`
- Phase-2 parquet: `b0f17b66…7ba1590b`
- explainability: `bae84b61…075c828f`
- replay: `78a3c059…3b8ba96298`
- simulation: `r3-v1` through 2024, phase6-r3-empirical

## Known limitations

- Cold load (~2 s/race, dominated by fail-closed validation) is paid
  once per race per cache residency; warm resolution is sub-ms.
- Float-boundary note (see Availability): ownership is on computed
  float age.
- `outside_viewport` tripped on 0.0% of Bahrain observations (bounds
  include the pit branch); the flag exists for runoff/incident/noise
  cases on other circuits.
- Window samples carry render coordinates only when geometry is
  verified; otherwise raw-only.
- Empty-universe frames resolve zero-driver coverage (caller choice).

## P12-5 handoff

- `SpatialStoreCache.get(root, race_id)` + `resolve_frame(store, T,
  universe_from_race_state(race_state))` is the serving path; P12-5
  enforces served-season eligibility and HTTP contracts.
- `resolve_window` feeds client trail rendering; scientific/rendering
  boundary above is binding on P12-6 animation.

## Entry gate

All boxes green: baseline exact; P12-0/1/2/3 intact; zero UNKNOWN;
nothing staged; Graphify-first used; replay clock reconfirmed
(T = anchor_state_time_s, no second clock); causal lookup exact;
boundaries exact; future-poison green; retirement separated; raw
exact; P12-3 transform reused; off-track preserved + flagged;
geometry linkage fail-closed; missing/partial explicit; query domain
handled; single + frame + window tested and ordered; cache bounded
and identity-aware; memory/perf measured; golden + 320-sample audit
zero mismatches; properties green; statistics reported; pit raw;
2025/product split kept; ALL_84 = 84; 2024-r09-R unsupported;
focused tests green; CI pin governed 3316 -> 3378; six identities
exact; no frozen artifact regenerated; frontend untouched; no frame
corpus; report + record written; diff classified; nothing committed,
tagged, or pushed; P12-5 not started.
