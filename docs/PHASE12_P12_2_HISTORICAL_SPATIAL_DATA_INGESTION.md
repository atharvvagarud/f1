# PHASE 12 P12-2 HISTORICAL SPATIAL DATA INGESTION

> Canonical historical spatial observation corpus. Cache-only FastF1
> source, P12-1 canonicalization, per-race atomic Parquet, logical
> content identity, deterministic manifest. Baseline
> `post-v2-clean-baseline` untouched. Nothing staged, committed,
> tagged, or pushed. P12-3 not started.

## Final verdict

**P12-2 COMPLETE — READY FOR P12-3**

## Baseline

- HEAD `218f4a653f8e7148d06fefc69798053b275795bc` =
  `post-v2-clean-baseline^{commit}`, before and after.
- Pre-existing P12-0/P12-1 outputs intact. New P12-2 paths untracked,
  unstaged, uncommitted. `git diff` touches only `.gitignore`
  (generated-data policy) and `scripts/run_ci_tests.py` (collection
  pin via the governed reclassification path).

## P12-1 contract

P12-1 implementation + tests are the canonical authority
(`spatial-observation-v1`, exact column order/dtypes/sort, keep-last
duplicate rule, exact `(0,0,0)` sentinel exclusion, logical content
hash, provenance/manifest schema). P12-2 reuses them without
duplication or redesign. One corpus finding required an
implementation-ordering clarification (NOT a contract change, see
Duplicate handling / Sentinel handling): 2018 pre-roll sentinel rows
carry small negative Times, so extraction passes raw times through
and P12-1 validation rules after the contracted sentinel exclusion.

## Corpus universe

Authoritative universe from local Tier-A manifests
(`data/v2/raw/manifests/tiera-{season}.json`): 173 championship Race
sessions 2018–2025 (21/21/17/22/22/22/24/24). No independently
invented calendar. Statuses: EXPECTED_SESSION (173) → SOURCE_AVAILABLE
(171) → INGESTED_COMPLETE (164) / PARTIAL (6) / SOURCE_UNAVAILABLE
(2: 2018-r01-R, 2018-r02-R — no `position_data.ff1pkl` in the local
cache, exactly P12-0's 171/173) / FAILED (1: 2024-r09-R pre-roll
track positions fail closed per contract — see Known limitations).

## Source policy

Primary source is the existing local FastF1 cache. Default corpus
build is `cache-only`: socket creation is blocked during the session
load, so cached blobs read from disk and any missing blob raises
instead of downloading. Missing sources record UNAVAILABLE, never
fetch. `--source-mode network` is explicitly opt-in and separated.
No network is required to reproduce the corpus when the cache is
present. FastF1 itself offers no offline flag; the socket guard is
the documented repository-level enforcement (covers socket-based HTTP,
i.e. FastF1's requests path).

## Ingestion architecture

`raceintel/spatial/ingestion.py` orchestrates load → extract →
canonicalize → validate → atomic write → hash → provenance → manifest
upsert, reusing P12-1 code throughout. `raceintel/spatial/io.py`
holds the file layer (atomic Parquet writes, deterministic manifest
persistence, hashing). No module sprawl, no geometry/resolver/API/
frontend surface, no predictive imports (firewall-tested).

## Source extraction

Correct Race session per (season, round) via `fastf1.get_session`
with minimal load flags (`laps=False, telemetry=True, weather=False,
messages=False`: position stream + results identity only, ~1s loads).
Per-driver `pos_data` frames supply `Time/Date/Status/X/Y/Z/Source`;
driver identity is the integer behind FastF1's string driver-number
keys (display names never identity); expected driver set comes from
`session.results` DriverNumber. `Date` is the transient
`source_observed_at` ordering key only, never persisted.

## Session time

FastF1 `Time` (== `SessionTime` on all sampled races) converts via
`total_seconds()` to `observation_time_s` at full float64 precision:
no rounding, no checkpoint quantization, no lap-relative time, no
per-race offsets. Deterministic re-conversion verified (unit test +
corpus rebuild identity).

## Duplicate handling

P12-1 semantics exactly: order by transient source time within
`(driver_number, observation_time_s)`, keep last; same
(Time, Date) conflicts fail closed. Corpus evidence (current cache
state): zero same-Time rows in all 170 ingested race artifacts,
i.e. the rule applies vacuously; the mechanism is unit-tested with
synthetic duplicates including the fail-closed conflict path.
P12-0's exploratory dup-fraction note described a coarser sampling
view, not current-cache row identity — classified, not a contract
contradiction.

## Sentinel handling

Exact `(0,0,0)` tuples excluded deterministically; removal counts
recorded in provenance (`excluded_zero_fix_rows` = 11,890,813 total).
Single-axis zeros (e.g. `x == 0` alone) are valid and retained
(unit-tested). Corpus finding: 2018 streams carry 26 pre-roll
sentinel rows per driver with small negative Times (before the
session clock zero); exclusion precedes time validation, so kept
artifacts contain no negative times and no sentinels. A negative Time
on a non-sentinel row still fails closed (unit-tested).

## Canonicalization

Exactly the P12-1 schema in exact column order/dtypes, canonical
sort `(driver_number, observation_time_s)`, uniqueness on
`(driver_number, observation_time_s)`. No downsampling, smoothing,
interpolation, normalization, geometry extraction, or pit-path
removal: full ~3 Hz raw observations preserved (pit trajectories and
retiree freeze-tails intact, verified on Monaco 2021).

## Validation

P12-1 `validate_observations` runs before every artifact completion:
schema/dtype/sort/identity/time/coordinates/zero-fix/uniqueness/
vocabulary violations fail closed (FAILED, no artifact). Present-but-
incomplete driver sets become PARTIAL with provenance + reason, never
COMPLETE.

## Atomic writes

Canonical frame → tmp sibling (same dir, `.tmp-` prefix, never
masquerading as complete) → reopen + validate + logical-hash check →
`os.replace` → file hash. Pre-existing known-good artifacts survive
failed rebuilds; tmp files cleaned on failure (unit-tested).

## Logical identity

`logical_content_hash` over schema version + columns + sorted rows:
reordering-insensitive, value-sensitive (both unit-tested). File
SHA-256 computed after final write for environment-level evidence
(surfaced in run stats/coverage, not in provenance — the contract
allows no extra provenance keys).

## Provenance

`build_provenance` per race with real values only: schema/FastF1/
stream/season/race/session, repo-relative input ref, raw/kept/
exclusion counts, driver sets, time range, observed vocabularies,
content hash, plus `round_no`/`event_name`/`source_session_start_utc`
optionals. No absolute paths, users, or write timestamps.

## Manifest

`data/spatial/manifests/spatial_manifest.json`
(`spatial-manifest-v1`), deterministic bytes (sorted races/keys,
`sort_keys`, indent 2), byte identity published per run. COMPLETE
requires full expected driver set + green validation; nothing is
COMPLETE merely because a file exists (resume re-verifies artifact +
hash before skipping).

## Resume / rebuild

Second runs skip verified COMPLETE races (existence + validation +
content-hash + driver-set checks, never manifest trust alone).
Corrupt/missing/stale entries rebuild. Default reuses; `--force`
rebuilds selected scope (season/race); a failed rebuild keeps a
still-verifying COMPLETE row, otherwise records fresh evidence. No
global destructive reset exists.

## CLI

One entry point: `scripts/build_spatial_observations.py` (`--season`,
`--race`, `--source-mode` default `cache-only`, `--force`, `--list`
dry-run, `--cache-dir`, `--root`). Concise per-race status lines +
closing JSON summary. No competing CLI. No Makefile target: the
Makefile carries no canonical generator targets (wrappers only), so
none was added; the script is the documented surface.

## Golden-race validation

Ingested first, all COMPLETE, all properties match P12-0 evidence:
Bahrain 2023 (x/y ranges exact, ~1 Hz→ full-rate preserved,
OnTrack-only); Monaco 2021 (identical 36973-row counts, single end
time, BOT freeze-tail, pit trajectories retained); Japan 2024
(1.8 s → 3:01:21 span); Australia 2023 (longest span, red-flag
coverage preserved for later stages). Resume SKIP verified (2.4 s vs
~12 s rebuild).

## Corpus results

From the deterministic manifest after the full cache-only run
(`manifest_sha256 =
87797e3fe22e850e47fb751c69e8fd382510d71e5731e0858c57a1d8bcdd2fc1`):
expected 173, source-available 171, COMPLETE 164, PARTIAL 6 (all
genuine DNS-type source gaps: HUL 2020 Britain, MAZ 2021 Abu Dhabi,
MSC 2022 Saudi, STR stream 2023 Dutch, SAI stream 2023 Japan, ALB
2024 Brazil), UNAVAILABLE 2 (2018 Australia/Bahrain: no
`position_data.ff1pkl` locally — exactly P12-0's 171/173),
FAILED 1 (2024 Canada: 120 pre-roll track positions at
`t in [-1.44, 0)` fail closed per contract — classified in Known
limitations, never concealed, no artifact).

## Coverage

Per-season COMPLETE/PARTIAL/UNAVAILABLE/FAILED: 2018 19/0/2/0, 2019
21/0/0/0, 2020 16/1/0/0, 2021 21/1/0/0, 2022 21/1/0/0, 2023 20/2/0/0,
2024 22/1/0/1, 2025 24/0/0/0. Rows by season (kept): 2018 7.64M, 2019
8.15M, 2020 12.51M, 2021 17.69M, 2022 14.90M, 2023 15.32M, 2024
14.94M, 2025 15.61M — 106.76M rows from 118.65M raw (11.89M
sentinels removed, 0 same-Time duplicates corpus-wide).
Driver counts 19 (PARTIAL) or 20; time spans 4687–16031 s (median
8293 s); observed vocabularies corpus-wide `source={pos}`,
`status={OnTrack}`. Source coverage 171/173 = 98.8% of Tier-A;
product-serving coverage unchanged (2025 ingestible, never servable;
frozen served replay-race count untouched).

## Storage

563.6 MB total Parquet (170 artifacts): median 3.47 MB/race, p95
4.34 MB, max 5.18 MB (2020-r15-R), ~5.28 bytes/row snappy. Above
P12-0's 1.3 MB/race sketch (which assumed coarser sampling) and
slightly above its ~500 MB raw-ish upper range at full ~3 Hz
fidelity — descriptive only; data untouched to hit estimates.

## Performance

Golden singles (incl. load): Bahrain 2023 10.7 s, Monaco 2021
11.8 s, Japan 2024 12.5 s, Australia 2023 14.4 s. Full corpus
1766.1 s for 164 ingested (~10.8 s/race, 0.093 races/s). Resume run
399.7 s (~2.3 s/race verify; 164 SKIP + 7 re-processed, manifest
identity unchanged). No optimization; no fake benchmarks. Dominant
cost is per-row Python content hashing (correctness first).

## Determinism

`--force` rebuild of 2021-r05-R and 2018-r03-R reproduces row counts
and logical content hashes exactly, and the manifest byte identity
is unchanged (provenance carries no timestamps). The full resume run
likewise reproduced the manifest identity byte-for-byte.
Unit-tested at the frame level (reorder-stable, value-sensitive).

## Cache-only guarantee

Socket-guard implementation + unit test (network attempt inside the
loader maps to SourceUnavailable); missing-cache races record
UNAVAILABLE in 0.3 s without traffic (2018-r01/r02 evidence). No
global FastF1 patching; unrelated functionality untouched.

## 2025 firewall

2025 races ingestible into `data/spatial/observations` + manifest +
coverage; `api.v2_service.SERVED_SEASONS` unchanged (2018–2024);
`is_data_ingestible(2025) and not is_product_servable(2025)` tested.
DATA_ALLOWED != PRODUCT_SERVABLE.

## Predictive firewall

P12-1 source-scan tests re-run green over the enlarged package
(`ingestion.py`/`io.py` auto-covered): no predictive module imports
spatial; spatial imports no predictive/API/web modules (explicit
P12-2 test pins the new files). `ALL_84` untouched: feature count
remains 84, no coordinate names added. Spatial corpus is
presentation/history data only.

## Scientific identities

6/6 exact, no regeneration: serving `1116b34f…`, phase-2 content
`d2ee966c…`, parquet `b0f17b66…`, explainability `bae84b61…`,
replay `78a3c059…`, simulation `r3-v1` through 2024 /
`phase6-r3-empirical` (asserted by the existing frozen test
surface, re-run in final validation; no frozen paths modified).

## Tests

31 P12-2 tests in `tests/test_spatial_ingestion.py` (fake sessions,
tmp dirs; corpus integration stays outside CI by construction):
extraction, time conversion (+pre-roll sentinel regression),
identity, duplicates, conflicts, sentinels, canonicalization
integration, atomic writes, hashing, provenance, manifest, resume
(first/second/corrupt/stale/force via the real CLI), cache-only
(+wrapped-error chain), 2025 distinction, predictive firewall. CI pin
3258 → 3289 through the governed reclassification comment. Final
validation: `make preflight-source` green; `make ci` green with one
note — the first `ci-python` run showed a single failure in the
frozen `test_v2_model_lab_m7.py::
test_estimator_fresh_per_c_and_only_c_varies` (`id()`-identity count
3 vs 4: CPython address reuse after garbage collection, sensitive to
allocator history). It passes alone, with the new tests, and at file
scope; the frozen test was not touched; the full-suite rerun on
identical code is green (2559 passed, 4 xfailed). Pre-existing
order-sensitive flake, unrelated to P12-2 (no shared imports either
direction, firewall-verified).

## Known limitations

- `Date` not persisted (transient ordering only).
- Strict Source/Status vocabularies (`pos` / `OnTrack,OffTrack`)
  fail closed on unseen values — deliberate extension point.
- Byte-identical Parquet not promised across dependency versions
  (logical hash is the identity).
- Two 2018 races have no local position stream (UNAVAILABLE, source
  fact, not a code gap).
- 2024-r09-R carries 120 pre-roll track positions at `t in [-1.44, 0)`
  (cars on grid with GPS fix before the session-clock zero). The
  contract allows no cleaning beyond exact-duplicate and zero-fix
  exclusion and requires `observation_time_s >= 0`, so the race fails
  closed (FAILED with reason, no artifact) instead of silently
  dropping valid observations or shifting the clock. Adjudicating
  pre-roll (allowlist window vs. clock shift) is a deliberate future
  contract-extension decision — never a silent ingestion fix.
- Socket guard covers socket-based HTTP (FastF1's path); an exotic
  non-socket exfiltration would bypass it — accepted, documented.
- Manifest + artifacts are ignored generated data (see policy). One
  crash-orphaned tmp sibling (killed-run leftover, never a readable
  artifact) was removed after verifying the final artifact.

## P12-3 handoff

Corpus ready: 170/173 Tier-A races as validated per-race Parquet
(164 COMPLETE + 6 PARTIAL) + deterministic manifest + provenance;
2 source-unavailable and 1 fail-closed race recorded with reasons.
Geometry stage may consume
`data/spatial/observations/{race_id}.parquet` via the frozen
`spatial-observation-v1` reader contract. 2025 present but flagged.
No geometry/resolver/API/frontend started.

## Entry gate

- [x] baseline exact; P12-0/P12-1 intact; nothing staged
- [x] zero UNKNOWN (after generated-data policy); Graphify-first
- [x] universe from Tier-A evidence (173); cache-only default
- [x] minimal ingestion module reusing P12-1; canonical source/identity
- [x] session time preserved, no rounding/offsets
- [x] duplicate + sentinel semantics exact; conflicts fail closed
- [x] no downsampling/smoothing/interpolation/normalization; pits kept
- [x] validation before COMPLETE; atomic Parquet; logical + file hashes
- [x] provenance valid; manifest deterministic; COMPLETE means verified
- [x] resume + stale/corrupt detection + targeted rebuild
- [x] canonical CLI; goldens first, validation passed
- [x] full cache-only corpus attempted; all statuses accounted
- [x] every COMPLETE artifact validates; coverage + storage + perf measured
- [x] determinism verified; 2025 ingestible but unservable
- [x] predictive firewall green; ALL_84 = 84; 6/6 identities exact
- [x] tests green; CI pin via governed path; preflight + ci green
- [x] report + record created; no geometry/resolver/API/frontend
- [x] nothing staged/committed/tagged/pushed; P12-3 not started
