# PHASE 12 P12-5 SPATIAL API

## Final verdict

P12-5 COMPLETE — replay-bound spatial HTTP surface (geometry, frame,
causal window) over the frozen P12-4 resolver is implemented, tested
(29 new source-safe tests), validated against the real corpus, and
green through CI. P12-6 not started.

## Baseline

- Frozen baseline: `218f4a653f8e7148d06fefc69798053b275795bc`
  (`post-v2-clean-baseline`); HEAD is exact at implementation time.
- Dirty work is only expected P12 accumulation: modified `.gitignore`
  + `scripts/run_ci_tests.py` (CI pin 3378 -> 3407), untracked P12-0..5
  docs, `raceintel/spatial/`, `results/phase12/`, build/probe scripts,
  and spatial tests (incl. `tests/test_spatial_api.py`,
  `scripts/probe_spatial_api.py`). Zero UNKNOWN, nothing staged.

## Input identities

- P12-4 handoff consumed verbatim: `SpatialStoreCache.get(root,
  race_id)` + `resolve_frame(store, T,
  universe_from_race_state(race_state))` (`spatial-resolver-v1`).
- Observation manifest identity: `87797e3f…` (164 COMPLETE, 6
  PARTIAL, 2 UNAVAILABLE, 1 FAILED, 106.76M observations).
- Geometry manifest identity: `6329b205…` (170 COMPLETE, 3 SKIPPED).

## API integration point

Graphify-first (12238 nodes, 29454 edges, 345 communities; 12376 /
29800 / 355 after P12-5) plus
targeted reads of `api/main.py`, `api/v2_replay_routes.py`,
`api/v2_replay_service.py`, `api/v2_replay_schemas.py`, and
`api/v2_service.py` fixed the smallest integration point:

- New files only: `api/v2_spatial_schemas.py` (public DTOs),
  `api/v2_spatial_service.py` (adapter), `api/v2_spatial_routes.py`
  (thin routes, `APIRouter(prefix="/v2", tags=["v2-spatial"])`).
- One-line registration in `api/main.py` (`include_router`); no
  second application/server; replay service and resolver untouched.
- Service lifetime mirrors the replay service: process-local lazy
  singleton via `get_v2_spatial_service()` (`lru_cache(maxsize=1)`),
  overridable in tests; no per-request cache, no global preload.

## Endpoint namespace

Existing `/v2` routing conventions followed (path race identity,
`frame_index` path params, `{error, detail}` bodies, FastAPI 422 on
bad query/path input):

- `GET /v2/races/{race_id}/spatial/geometry`
- `GET /v2/races/{race_id}/spatial/frame/{frame_index}`
- `GET /v2/races/{race_id}/spatial/window/{frame_index}?driver_number=&history_s=`

## Product eligibility

All spatial endpoints reuse the canonical served-race policy by
construction: geometry calls `replay.get_timeline(race_id)` and
frame/window call `replay.get_frame(race_id, frame_index)` before
touching the spatial corpus, so unknown/unserved races — including
any 2025 race — raise the existing `RaceNotFoundError` and map to the
existing 404 `unknown_race`. No season list is duplicated in the
spatial adapter (source-scanned: no `SERVED_SEASONS`, no `range(`, no
`2025` literal in the three new API modules).

## Geometry endpoint

Serves the verified P12-3 record's renderer-ready subset from the
same cached store that resolves frames (same transform, same
identity). Bounded fixed artifact (512 main points on golden races).

## Geometry DTO

`V2SpatialGeometryResponse`: `race_id`, `schema_version`,
`algorithm_version`, `geometry_sha256`, `main_track`
(`points`/`n_points`/`closed_loop`), `pit_lane` (same shape or null),
`pit_status`, `render_bounds`. Excluded: `raw_points`, `raw_bounds`,
`transform`, `source` provenance, `quality`, absolute paths. The
internal record may evolve without changing the API (exact
serialization tested).

## Frame endpoint

`GET spatial/frame/{frame_index}` — the canonical replay-facing
endpoint. No direct `time_s` query exists.

## Replay clock binding

Design B chosen (frame_index path param; design A — client `time_s`
— rejected): the service resolves the existing replay frame first,
then `T = replay_frame.anchor_state_time_s`, then calls the P12-4
resolver. No lap-derived clock, no second clock, no frontend rounding
in the path. Time-travel is impossible by construction: there is no
input that sets T except through the replay frame.

## Driver universe

`universe_from_race_state(replay_state)` from the exact replay state
of the resolved frame (caller order preserved as frame order), so the
replay table and spatial markers share one driver universe. Roster
members without telemetry identity resolve UNAVAILABLE rows, never
dropped rows.

## Frame DTO

`V2SpatialFrameResponse`: `race_id`, `frame_index`, `query_time_s`,
`source_status` (COMPLETE/PARTIAL), `geometry_sha256`,
`observation_content_sha256`, `resolver_contract_version`,
fresh/stale/unavailable counts, `drivers[]` with `driver_id`,
`driver_number`, `availability`, `observation_time_s`, `age_s`,
`render_x`/`render_y`, `outside_viewport`. Excluded: `raw_x`/`raw_y`
(no consumer), per-driver provenance (frame-level counts +
`source_status` instead). UNAVAILABLE rows carry null coordinates
(resolver contract preserved).

## Partial races

PARTIAL races serve valid frames: present drivers resolve normally,
missing drivers are UNAVAILABLE, `source_status` reports PARTIAL.
Validated on synthetic fixture and real 2023-r15-R (20 drivers, 1
unavailable at mid-race).

## Unsupported spatial races

2024-r09-R (observations FAILED, geometry SKIPPED): non-spatial
replay keeps working (`get_frame` succeeds); spatial geometry/frame
return 404 `spatial_unavailable`. The P12-2 contract is untouched.

## Window decision

Implemented — a short causal trail is the justified P12-6 consumer
(client motion rendering over already-known samples). Strictly
causal (`[T - history, T]`, every sample `<= T`, poison-tested),
strictly bounded (`history_s` in `[0, 30]`, single driver per
request, samples bounded by observations in the window), one-clock
(frame_index path, same T derivation as frame). Unknown drivers
return an empty trail, never an error. No all-telemetry endpoint
exists.

## Payload bounds

Geometry: fixed artifact (<= 1024 points asserted). Frame: exactly
the replay universe (~20 rows). Window: 30 s cap, one driver.
Measured real JSON bytes: geometry 27703, frame 4602, window (5 s,
20 samples) 2102. No compression middleware added.

## Cache lifecycle

`SpatialStoreCache(max_races=4)` lives on the service singleton:
race-level lazy loading on first spatial request, identity-aware
hits across requests (tested: repeated frame/geometry/window calls
keep one cached store). No per-request instantiation, no corpus
preload, no test-isolation breakage (service is built per fixture
via dependency override).

## Error mapping

`unknown_race` 404 (incl. 2025 and path-traversal identities, which
never reach the filesystem); `unknown_frame` 404; FastAPI 422 on
negative frame / out-of-range driver / over-long history / missing
driver; `spatial_unavailable` 404 (missing observations or geometry);
`spatial_integrity_error` 500 on geometry source-identity mismatch
(fail closed, never fake empty success); `internal` 500 otherwise.
Bodies carry no tracebacks, paths, or model internals (asserted).

## Determinism

Same race/frame/artifacts produce byte-identical JSON (service-level
`sort_keys` equality plus HTTP body equality tested). No response
timestamps, no request IDs in bodies.

## Payload sizes

Real serialized JSON bytes (2023-r01-R mid-race): geometry 27703 B
(512 main + 128 pit points), 20-driver frame 4602 B, 5 s window
2102 B (20 samples). Renderer-safe without extra middleware.

## Performance

Measured on 2023-r01-R (mid-race frame, service level + HTTP):

- Spatial cold load (fail-closed validation + indexing): 2.10 s,
  paid once per race per cache residency (matches P12-4: 2.04 s).
- Warm service frame: 35.2 ms, split as replay `get_frame`
  (RaceState reconstruction) ~39.4 ms + P12-4 resolver 0.16 ms
  (matches P12-4: ~0.20 ms) + DTO/serialization remainder.
- 100 sequential warm frames: 3.51 s (~35 ms/frame, replay-bound).
- HTTP warm frame (TestClient): 41.1 ms, status 200.
- No frontend-FPS claim is made from backend numbers.

## Real integration validation

`scripts/probe_spatial_api.py` against the real corpus (Bahrain
2023, Monaco 2021, Japan 2024, Australia 2023, mid-race frames):

- Geometry valid (512 main points, `PIT_GEOMETRY_SUPPORTED`),
  frame valid, 20 drivers == replay universe, `query_time_s` ==
  replay `anchor_state_time_s` exactly, all available
  `observation_time_s <= T`, render coordinates delta vs direct
  P12-4 `resolve_frame` exactly 0.0, clean JSON serialization.
- PARTIAL 2023-r15-R: valid frame, `source_status` PARTIAL, 1
  unavailable driver.
- 2024-r09-R: replay frame resolves, spatial returns unavailable.
- 2025-r01-R: `RaceNotFoundError` (HTTP `unknown_race` covered in
  CI tests).

## OpenAPI

FastAPI generates all three paths with typed models
(`V2SpatialGeometryResponse`, `V2SpatialFrameResponse`,
`V2SpatialWindowResponse`, plus track/driver/sample models); no
duplicate schema names, no untyped dictionaries (asserted in CI).

## Input validation

`frame_index` path `ge=0`; `driver_number` query in `[1, 99]`;
`history_s` query in `[0, 30]`; race identity resolves only through
the served registry (arbitrary/traversal strings 404 before any
filesystem access). NaN/inf time cannot occur (no `time_s` input).

## 2025 firewall

Low-level resolver still resolves 2025 data (mathematics, no season
gate — P12-4 property preserved); HTTP spatial rejects 2025 with the
same `unknown_race` semantics as every other unserved v2 race
(service-level + HTTP-level tests). No duplicated season constant.

## Predictive firewall

Adapter direction is API -> spatial only (source-scanned:
`raceintel/spatial/*.py` carries no `api` import; spatial API
modules carry no features/labels/model_lab/simulation/strategy/
explainability/prediction imports). No science duplication in the
adapter (no `searchsorted`, `classify_availability`,
`apply_transform`/`compute_transform`, `logical_content_hash` —
asserted). ALL_84 remains 84 (existing firewall surface green).

## Frontend handoff

- `GET geometry` -> normalized SVG-ready track/pit polylines in
  `[0, 1] x [0, 1]` render space (`y_down` already applied) plus
  `render_bounds` and `geometry_sha256`.
- `GET frame/{frame_index}` -> replay-synchronized driver render
  coordinates (`render_x`/`render_y`, null when UNAVAILABLE) with
  `availability` + `outside_viewport` flags and count metadata.
- `GET window/{frame_index}?driver_number=&history_s=` -> ascending
  causal trail samples for short motion trails.
- P12-6 needs no FastF1/parquet/normalization/availability/geometry
  knowledge; match `geometry_sha256` across geometry + frame
  responses to detect staleness. Frontend source untouched (zero
  diff).

## Tests

New `tests/test_spatial_api.py`: 29 collected nodes (stub replay
service + tmp-dir corpus; no 563 MB corpus in CI) covering geometry
shape/serialization, one-clock + universe binding, FRESH/STALE/
UNAVAILABLE incl. aged-out provenance, future-poison, PARTIAL,
unsupported race, 2025 rejection (service + HTTP), invalid
race/frame/query inputs, mismatch fail-closed, determinism
(service + HTTP bytes), payload bounds, cache reuse, no-science-
duplication/no-season-duplication/direction scans, traversal
safety, OpenAPI presence. CI pin: 3378 -> 3407 (+29, no removals,
no weakening).

## Scientific identities

Reverified without regeneration (frozen paths untouched; frozen
test surface green):

- serving: `1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4`
- Phase-2 content: `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db`
- Phase-2 parquet: `b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3`
- explainability: `bae84b614a6e9e176d5bb9c33b99dcaf4cba3f376333b0f075c828f73982939f`
- replay: `78a3c059888637fe83cc534d0eb7869b6d18e746724bb1ce0f03ee3b8ba96298`
- simulation: `r3-v1` through 2024, phase6-r3-empirical

6/6 exact.

## Known limitations

- First spatial request per race pays ~2.1 s cold load (fail-closed
  validation + indexing); warm frames are replay-bound (~35 ms,
  resolver contributes ~0.16 ms).
- Window cap is 30 s / one driver per request; longer trails
  require repeated calls (each still causal and bounded).
- Races without renderable geometry serve no spatial state
  (render-space frames fail closed; no raw-only HTTP mode).
- 2024-r09-R remains spatially unsupported (P12-2 contract
  unchanged).

## P12-6 handoff

`SpatialStoreCache.get(root, race_id)` + replay-bound
`V2SpatialService.get_geometry/get_frame/get_window` is the serving
path; `geometry_sha256` links geometry to frames; the
scientific/rendering boundary from P12-4 still binds animation
(never mutate resolved states; trails use already-known samples
only).

## Entry gate

All boxes green: baseline exact; P12-0..4 intact; zero UNKNOWN;
nothing staged; Graphify-first used; existing API architecture
reused; no second server; canonical race identity; served
eligibility reused; 2025 HTTP rejected; no duplicated season
policy; geometry endpoint + separate public DTO, bounded; canonical
frame_index endpoint; replay-clock binding explicit (design B, no
`time_s` input); no lap-derived clock; RaceState universe reused;
compact frame DTO; FRESH/STALE/UNAVAILABLE preserved; no future
data; no science duplication; no geometry recomputation; PARTIAL
supported; 2024-r09-R spatially unavailable only; window causal and
bounded; no telemetry dump; race-level cache across requests; no
preload; conventional error mapping; no path leaks;
geometry/frame identity consistency; deterministic bytes; sizes
measured; performance split measured; golden + PARTIAL +
unsupported + 2025 integration validated; OpenAPI valid; input
bounds tested; traversal impossible; frontend handoff explicit;
frontend untouched; API -> spatial direction; no spatial -> API;
predictive firewall green; ALL_84 = 84; six identities exact; no
frozen regeneration; focused tests green; CI pin governed
3378 -> 3407; `make preflight-source` green; `make ci` green;
report + record written; diff classified; nothing committed,
tagged, or pushed; P12-6 not started.
