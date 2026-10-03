# PHASE 12 P12-1 SPATIAL DATA CONTRACT

> Contract/governance foundation only. No ingestion, geometry,
> resolver, API, or frontend. Baseline `post-v2-clean-baseline`
> untouched. Nothing staged, committed, tagged, or pushed. P12-2
> not started.

## Final verdict

**P12-1 COMPLETE — READY FOR P12-2**

## Baseline

- HEAD `218f4a653f8e7148d06fefc69798053b275795bc` =
  `post-v2-clean-baseline^{commit}`, before and after.
- Pre-existing untracked P12-0 outputs (audit report + JSON) left
  untouched. New P12-1 paths untracked, unstaged, uncommitted.

## P12-0 constraints

P12-0 decisions carried unchanged: FastF1 3.7.0 position stream;
`anchor_state_time_s` == session clock; `(race_id, driver_number)`
join; causal latest-`<= T` only; FRESH `<= 3s` / STALE `<= 15s`;
event-relative metre coordinates; Z retained-not-rendered; pit
trajectories preserved; retirement never inferred from coordinates;
race-wide flags default; 2025 ingestible but not servable;
~1.3MB/race; no new dependencies; full science isolation. No
contradiction found during implementation — including one refinement
with direct evidence: same-`Time` rows differ by sub-second `Date`,
so the duplicate rule keeps last-by-source-time (P12-0's
"drop exact dupes" sharpened, not contradicted).

## Package boundary

`raceintel/spatial/` with five modules only: `__init__`
(boundary/version), `contracts` (constants + pure helpers),
`errors` (minimal hierarchy), `validation` (schema/canonical/hash),
`manifest` (provenance + ingestion manifest). No ingestion,
geometry, resolver, API, or frontend modules. No predictive, API,
or web-framework imports anywhere in the package.

## Observation schema

`spatial-observation-v1`: `(race_id str, driver_number int64,
observation_time_s float64, x/y/z int64, source/status str)` in
exact order; uniqueness on `(driver_number, observation_time_s)`;
canonical sort `(driver_number, observation_time_s)`. Excluded
deliberately: `observation_age_s` (query-time derived) and absolute
`Date` (transient dedup ordering key `source_observed_at` only).

## Identity

`(race_id, driver_number)`; `driver_number` int 1–99 canonicalized
from FastF1 string keys; display slugs/abbreviations never identity.

## Time semantics

Float64 session seconds, finite, `>= 0`, on the identical clock as
replay anchors (measured ~0.1s). Canonical sort, keep-last dedup by
source time. Causal invariant frozen: future resolution may only
select `observation_time_s <= T`; negative ages raise.

## Duplicate semantics

EXACT_DUPLICATE (identical payload) removed by the keep-last rule;
SUB_TIMESTAMP_UPDATES (same Time, ordered Dates) keep the latest;
CONFLICTING_DUPLICATE (same Time+Date, differing coordinates —
zero observed) fails closed via `SpatialDuplicateConflictError`.

## Coordinate semantics

Raw int64 integral metres, finite, non-nullable, negatives allowed;
`(0,0,0)` is a no-fix sentinel — P12-2 must exclude it, persisted
artifacts containing it fail validation. No normalization in P12-1
(P12-3 owns geometry).

## Source/status semantics

Persisted raw non-empty strings. Known sets `{'pos'}` /
`{'OnTrack','OffTrack'}` from sampled evidence; strict validation
rejects anything else so new semantics force deliberate extension.
No retirement/pit/flag meaning inferred from these fields.

## Availability/staleness

`classify_availability` frozen pure helper: 0→FRESH, 3.0→FRESH,
3.000…→STALE, 15→STALE, >15→UNAVAILABLE; negative/non-finite ages
raise (future observation). Resolver output type belongs to P12-4.

## Missingness

Absent driver, no-causal-observation, invalid coordinates,
over-threshold staleness, retirement, and session interruption are
six distinct states; retirement stays RaceState truth, spatial
reports coordinate availability only.

## Provenance

Required: schema/FastF1/stream/season/race/session versions and
identity, repo-relative input ref, raw/kept/exclusion counts,
driver sets, time range, observed vocabularies, content hash.
Optional allowlist only (`round_no`, `event_name`,
`source_session_start_utc`). No absolute paths, users, or write
timestamps.

## Manifest

`spatial-manifest-v1` with COMPLETE/PARTIAL/FAILED/UNAVAILABLE rows
(precise entry rules; COMPLETE needs the full expected driver set;
non-COMPLETE needs a reason), pure upserts, fail-closed validation.
P12-1 ships schema + empty constructor — no fake bulk rows.

## Artifact layout

`data/spatial/{observations,manifests,schema,geometry}/` with
`observations/{race_id}.parquet` atomic files — outside `data/v2`
so the frozen D11 artifact-inventory scope is untouched, and outside
bundle manifests.

## Serialization

Parquet via existing pyarrow, snappy (measured), contract column
order/dtypes/sort, never a persisted index. Determinism promised at
the logical-dataset level, not file bytes.

## Logical content identity

SHA-256 over canonical JSON of schema version + columns + sorted
rows; excludes paths and timestamps. P12-2 reproducibility key.

## Source preservation

Raw cache untouched; only exact duplicates and zero-fix sentinels
removed. No downsampling, smoothing, interpolation, normalization,
or pit removal — enforced by contract text and tests.

## Served-season firewall

Data epoch 2018–2025 (`is_data_ingestible`); product 2018–2024
(`is_product_servable`); single product truth stays in
`api/v2_service.SERVED_SEASONS` with a drift-guard test (no
`raceintel → api` import, forbidden direction).

## Predictive firewall

Source-scan tests both directions: no predictive module imports
`raceintel.spatial`; spatial imports no predictive/API/web module.
Allowed flow is source → spatial → (later) replay/API/frontend.

## ALL_84 firewall

Registry still 84 (`EXPECTED_PREDICTIVE_FEATURE_COUNT`,
`canonical_predictive_names`, `ALL_84` length asserted) with no
spatial-coordinate names; registry untouched (no exclusions added).

## D11 governance

Assessed, deliberately not extended: D11 checks frozen science
behavior, and any new D11 row risks changing frozen outcomes — the
concrete `SPATIAL-PRESENTATION` check proposal (scope/area/leakage
wording) is specified for P12-9 instead. Import-direction and
no-leak enforcement lives in the new firewall tests now.

## Validation

`validate_observations` (exact schema, dtypes, identity, time,
coordinates, zero-fix, uniqueness, vocabularies, sort report),
`canonicalize_observations` (exclusion, conflict detection,
keep-last, casting, sorting), `logical_content_hash`,
provenance/manifest builders and validators.

## Error model

`SpatialContractError` base plus `Schema/Identity/
DuplicateConflict/Provenance/Manifest` — one per contract surface,
fail-closed messages without local paths.

## Fixtures

Tiny synthetic builders local to each test file; no fixture files,
no real telemetry committed.

## Tests

48 tests across `test_spatial_contracts/validation/manifest/
firewall.py`: schema, identity, time, duplicates, availability
boundaries, provenance, manifest rules, determinism, served
firewall, predictive firewall, ALL_84. CI pin updated 3210→3258
with provenance comment (the pin's designed reclassification path).

## P12-2 producer contract

Load (cache-first) → canonicalize → validate → write atomic
snappy parquet → hash → provenance → manifest upsert, honoring the
allows/forbids lists. Sufficient to implement without redesign.

## Scientific identities

6/6 exact, no regeneration: serving `1116b34f…`, phase-2 content
`d2ee966c…`, parquet `b0f17b66…`, explainability `bae84b61…`,
replay `78a3c059…`, simulation `r3-v1` through 2024 /
`phase6-r3-empirical`.

## Known limitations

`Date` not persisted (transient ordering only; absolute anchoring
via session metadata if ever needed); strict vocabularies require
deliberate extension for unseen Source/Status; byte-identical
Parquet not promised; D11 extension deferred to P12-9; no bulk
manifest rows exist yet.

## Entry gate

- [x] baseline exact; P12-0 artifacts present; nothing staged
- [x] zero unexplained dirt; Graphify-first navigation
- [x] package boundary minimal (5 modules, no impl surface)
- [x] schema/identity/time/duplicate/coordinate/status frozen
- [x] no geometry normalization; age not persisted
- [x] availability/missingness/provenance/manifest exact
- [x] no fake bulk manifest; layout/serialization/content-hash set
- [x] no new dependency; no downsampling/smoothing/interpolation
- [x] pit trajectories preserved; 2025 distinction preserved
- [x] predictive + ALL_84 firewalls tested; D11 assessed+deferred
- [x] validation/errors/fixtures/tests implemented, 48 green
- [x] P12-2 contract explicit; no P12-2+ implementation
- [x] identities exact; preflight + ci green; frontend unaffected
- [x] report + record created; diff classified; zero UNKNOWN
- [x] nothing staged/committed/tagged/pushed; P12-2 not started
