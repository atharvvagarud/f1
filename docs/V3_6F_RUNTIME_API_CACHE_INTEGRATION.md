# V3.6F RUNTIME + API + CACHE INTEGRATION

## Final verdict

V3.6F COMPLETE — RUNTIME/API/CACHE INTEGRATED — READY FOR V3.6G

## Frozen scientific lineage

| Stage | Identity | Status |
|---|---|---|
| Frozen parent | `6df5d41d3ebead9a1c9b4f0f40ed20a21ce0bff1` (`v3.5-outcome-distribution`) | exact |
| V3.6A | `2d29c19b…0ae59b` | `V3.6A COMPLETE` |
| V3.6B | `df821fe1…443e3644` | contract `v3.6b-strategy-execution-contract-v1` |
| V3.6C engine | `v3.6c-engine-v1` (`raceintel/strategy/v3_engine.py`) | validated, unchanged |
| V3.6D protocol | `0c2bf7fb…64088fc` | `REFINEMENT_NOT_WARRANTED` |

No scientific file was modified: `raceintel/strategy/v3_engine.py`,
`raceintel/strategy/v3_contracts.py`, `raceintel/simulation/*`,
`raceintel/race_state/*` and all Phase-7 strategy code are byte-identical
to the frozen parent (only additive `api/v2_strategy_v3_*` modules, one
generator script, two test files, docs and result JSON were added).

## V3.6E skip

V3.6E (refinement) was intentionally skipped per the V3.6D verdict
(`REFINEMENT_NOT_WARRANTED`). No `*v3_6e*` / `*V3_6E*` file exists anywhere
in the tree (asserted by `test_v3_6e_absent`).

## Architecture

```
Phase-7 clients ──► POST /v2/strategies/compare   (UNCHANGED)
                         │  api/v2_strategy_service.py

Strategy 2.0 ──► POST /v2/strategies/compare-v3 ──► V3StrategyService
clients           GET  /v2/strategies/v3/availability      │
                                                   ┌──────┴──────┐
                                              LIVE_ENGINE      CACHED
                                              (real 5000-run  (validated
                                               V3.6C engine)   artifact)
                                                      │            │
                                                      ▼            ▼
                                          raceintel/strategy/v3_engine.py
                                          (ONE scientific engine)
                                                      │
                                                      ▼
                                              frozen MC2-E
```

One scientific engine serves both modes. There is no demo math, no
simplified browser logic, no handwritten showcase result: every cached
byte is engine output wrapped deterministically.

## Existing API audit

`POST /v2/strategies/compare` (Phase-7 S7): exact-anchor addressing,
caller-chosen `simulation_count` (100–10000, default 1000), required
single `objective`, neutral ≤4 default candidates, response with
`baseline`, three paired deltas, single-objective `uncertainty`, and
`objective_analysis`. Per-index outcomes never leave the process; error
mapping is 404 unknown_race / 422 unknown_state / 422
strategy_request_invalid / 200 supported=false / 503 / 500.

## API integration decision

**Decision: NEW_VERSIONED_ENDPOINT** — `POST /v2/strategies/compare-v3`
plus `GET /v2/strategies/v3/availability`.

V3.6A recommended `EXTEND_EXISTING_API`, "versioned-new only if V3.6B
finds the frozen schema cannot carry the outcome vector". That condition
is met:

- Strategy 2.0 returns a 6-field trade-off vector (win/podium/top5/
  top10/expected-finish/downside) where Phase-7 carries 3 deltas;
- Strategy 2.0 aggregates (`reference_aggregate` /
  `alternative_aggregate`) are over the complete-pair set, not the S4
  own-denominator aggregates behind Phase-7 `baseline`;
- Strategy 2.0 reports per-objective point-estimate `leaders` with no
  selected objective, where Phase-7 requires one `objective` and returns
  single-objective uncertainty;
- Strategy 2.0 fixes the production count at 5000 with no caller field,
  where Phase-7 accepts 100–10000.

Forcing these into the Phase-7 response would silently reinterpret old
fields or create ambiguous duplicates — both forbidden. The new endpoint
reuses the exact-anchor addressing convention and the frozen error
taxonomy, and Phase-7 request/response semantics are byte-identical
(frozen pre-change fixture in
`results/v3/v3_6f/phase7_compat_baseline.json`, regression-tested).

## Backwards compatibility

A compatibility fixture was frozen BEFORE any integration code was
written. `test_phase7_request_still_works` replays the identical request
and requires identical `strategy_contract_version`,
`comparison_version`, `metric`, `probability_semantics`,
`comparison_identity` and `delta_win_probability`. Phase-7 product
bounds (100/1000/10000) are re-asserted. No Phase-7 file was modified.

## Strategy 2.0 request

`V3CompareRequest` (extra fields forbidden, so a stray
`simulation_count` is a 422, never silently accepted):

| Field | Meaning |
|---|---|
| `race_id`, `anchor_driver_id`, `anchor_lap_number`, `anchor_state_time_s` | exact historical anchor (same authority as Phase-7) |
| `target_driver_id` | driver the alternatives are compared for |
| `alternatives` | subset of the frozen 9-action space; `None` = full 9 |
| `master_seed` | optional; defaults to deterministic `20240101`; part of cache identity |
| `mode` | `live` (real engine) or `cached` (validated artifact) |

Validation (`invalid_action`, `duplicate_alternatives`,
`no_alternatives`, `too_many_alternatives`, `unknown_mode`) fails closed
with 422 before any expensive work. `STAY_OUT` with an explicit compound
is rejected: it is outside the frozen 9-action space.

## Strategy 2.0 response

Compare-only payload: `engine_version`, `execution_contract_version`,
`outcome_schema_version`, `strategy_identity`, state/parameter/config
identities, `master_seed`, `simulation_count` (always the service
constant, 5000 in production), race/checkpoint/driver echo,
`supported` / `unsupported_reason`, `reference_kind`
(`SIMULATED_NO_INTERVENTION_REFERENCE`, never conflated with STAY_OUT),
per-alternative reference/alternative aggregates, 6-field `deltas` with
`paired_se`, `ci_low/high`, `availability`, `valid_pairs` and the frozen
`95% MC interval` label, execution diagnostics
(`requested/complete/excluded` pairs), per-alternative
`comparison_identity`, objective-specific `leaders`, full `provenance`,
`execution_source` (`live_engine` | `cache`), `cache_key`, and small
`runtime` timings (presentation-only, excluded from identity).

No per-simulation futures, no RNG state, no D-evaluation content cross
this boundary.

## Runtime modes

- `LIVE_ENGINE` (`mode="live"`): reconstruct → adapt → validated V3.6C
  engine → projection. Available locally and wherever
  `V3_STRATEGY_ALLOW_LIVE=1` (default).
- `CACHED` (`mode="cached"`): reconstruct → adapt (cheap identity
  authority, no simulation) → deterministic key → validated artifact →
  subset projection. A deployment sets `V3_STRATEGY_ALLOW_LIVE=0` for
  honest cache-only operation (`live_engine_disabled` is explicit;
  `cache_miss` is explicit; nothing is fabricated).

The served response always identifies its source. Scientific values for
the same comparison identity match across modes (parity-tested,
including subset and request-order variations).

## Live engine path

Developer-local full-engine execution (no cache required):

```
.venv/bin/python -c "
from api.v2_service import load_v2_service
from api.v2_strategy_v3_service import build_v3_strategy_service
svc = build_v3_strategy_service(load_v2_service())
svc.run_comparison(race_id=..., anchor_driver_id=..., anchor_lap_number=...,
    anchor_state_time_s=..., target_driver_id=..., alternatives=None,
    mode='live')"
```

or over HTTP: `POST /v2/strategies/compare-v3` with `mode="live"`.
Production count is fixed at 5000; a real-state full-9 comparison takes
on the order of 45–180 s (V3.6D evidence), consistent with the existing
Phase-7 synchronous long-request convention (10k comparisons already run
synchronously). No async/job framework was built: smallest architecture
consistent with measured latency.

## Cached path

`mode="cached"` serves `CACHE_DIR/v3strat_<key>.json`
(`V3_STRATEGY_CACHE_DIR` overrides; default
`runtime_artifacts/v3_strategy_cache/`). Same schema, same provenance,
`execution_source="cache"`. Cache miss → 404 `cache_miss`; corrupt /
stale / mismatched artifact → 503 `cache_invalid`; both explicit, never
a silent fallback. A cache-only deployment without Python/MC2 capability
can serve these artifacts as static, scientifically honest data.

## Cache key

`build_cache_key` = `canonical_sha256` over:

```
key_version, engine_version, execution_contract_version,
outcome_schema_version, mc2_identity, state_identity,
parameter_identity, config_identity, simulation_count,
master_seed, target_driver_id
```

No timestamps, paths, or presentation state. Any scientific change
(engine, contract, outcome schema, MC2, state, parameters, config,
count, seed, target) invalidates naturally; no manual cache-version
magic. Filenames are hex-only (`v3strat_<64-hex>.json`), so caller input
can never select an arbitrary file.

## Cache schema

Artifact: `{cache_schema_version, cache_key_version, cache_key, result,
request}` where `result` is the engine-shaped scientific dict (compact
aggregates, deltas, diagnostics, leaders, provenance — never simulation
trajectories) and `request` carries human-readable anchor metadata for
the catalogue. Canonical bytes are `json.dumps(sort_keys=True,
indent=2)`; `artifact_hash` is their SHA-256.

## Cache validation

Every read validates: schema version, key equality, all frozen
identities (engine/contract/outcome/state/parameter/config/count/seed/
target), MC2 identity inside provenance, and recomputed result identity
(tamper-evident). Failure raises `V3CacheInvalidError` → 503, never a
served stale result. The generator validates before every write and the
service re-validates on every read.

## Cache parity

`LIVE → CACHE → LOAD` preserves deltas, intervals, aggregates, counts,
leaders, identities and diagnostics exactly (JSON-canonical equality),
for full-9 and subset projections in any request order
(`test_api_cached_equals_api_live`, `test_cache_roundtrip_exact`).

## Cache generation

`scripts/v3_6f_build_strategy_cache.py --fixture` (or `--anchors-json`)
runs the service live path at the frozen 5000 configuration, asserts the
served cache key, wraps, validates, and atomically writes each artifact;
unsupported states produce explicit `supported=false` artifacts. It is
resume-safe (valid existing artifacts skipped), deterministic in order,
and ends with a progress/failure summary (nonzero exit on failures;
unsupported is not failure). No strategy math lives in the script.

## Catalogue capacity

Repository truth: 149 served races, 162,728 exact-anchor rows, ~20-driver
rosters. V3.6D measured MC2 eligibility at 71/298 sampled states
(~24%), i.e. roughly 38k eligible states before target expansion, and
real-state 5000-run cost at 45–180 s per (state, target) comparison
(one comparison covers all 9 actions: one shared reference + 9 arms).

Full materialization (eligible states × roster targets × ~100 s) is on
the order of thousands of machine-days — see
`results/v3/v3_6f/cache_capacity.json`. Even a D-style 2-anchor/race
catalogue (298 states × ~20 targets) is on the order of a machine-week.

## Full-build estimate

Recorded in `results/v3/v3_6f/cache_capacity.json` (inputs, eligibility
fraction, timing range, artifact-size measurement, and low/mid/high
projections). Conclusion: full catalogue materialization is deferred to
Portfolio Release / deployment preparation.

## Public cache policy

F validates the cache ARCHITECTURE with a deterministic representative
fixture (one supported + one unsupported real state, full-9, 5000-run),
not by precomputing history. The manifest
(`results/v3/v3_6f/cache_manifest.json`) describes what a full build
requires. Simulation count is never reduced to make generation cheaper.

## Availability catalogue

`GET /v2/strategies/v3/availability[?race_id=]` scans validated cache
artifacts and returns a deterministic, sorted catalogue (race, anchor,
target, seed, count, support, alternative count, comparison identities,
cache keys) so the future frontend never has to discover support by
submitting failed simulation requests.

## Unsupported states

The frozen STATE → ACTION → COMPARISON hierarchy is preserved end to
end: state-level unsupported → 200 `supported=false` with the canonical
`s4` reason (live) or the recorded reason (cached); action-level
inadmissible → `evaluated=false` with per-alternative reason and no
aggregates/deltas; comparison-level zero pairs → `NO_VALID_PAIRS`. No
HTTP 200 with fabricated zero metrics, no silent Phase-7 fallback, and
server failure (500/503) is never disguised as scientific unsupported.

## 2025 firewall

Strategy 2.0 is through-2024 per frozen MC2 support. Any 2025 race id
misses the served registry → 404 `unknown_race` (regression-tested on
the v3 route). MC2 was not extended; no V3.5 2025 output is substituted.

## Serialization

`typed engine result → serialized response → cache artifact →
deserialized response` is byte-exact on scientific content
(canonical-JSON equality). `strategy_identity` is recomputed over served
content with the frozen field set; presentation-only `runtime` /
`execution_source` never enter identity or cache.

## Performance

Measured (see `results/v3/v3_6f/runtime_integration.json`):
reconstruction+adaptation on the order of 0.1–1 s; cache lookup +
deserialization + validation on the order of milliseconds; live
small-count fixture on the order of seconds; one real 5000-run
single-alternative comparison for the integrated live path (tens of
seconds; full-9 D range 45–180 s). Integration overhead is negligible
relative to MC2. D's expensive corpus was not repeated.

## API live-engine parity

For one deterministic eligible fixture at the production 5000
configuration: DIRECT V3.6C ENGINE == API LIVE_ENGINE exactly
(`strategy_identity`, per-alternative payloads, leaders) —
`test_direct_engine_vs_api_live_parity_5000`. Then API LIVE_ENGINE ==
API CACHED exactly (same test module, all subset shapes).

## API cache parity

Covered above plus `test_cache_roundtrip_exact` and order-invariance
(`test_cached_subset_identity_matches_direct_subset`). Load-bearing and
green.

## Phase 7 regression

Frozen pre-change fixture replayed: identical request → identical
`strategy_contract_version`, `comparison_version`, `metric`,
`probability_semantics`, `comparison_identity`, `delta_win_probability`;
product bounds re-asserted; existing S7 API suite passes (see Tests).
No Phase-7 file modified, no Phase-7 test edited.

## Security/robustness

Focused checks (full audit remains Portfolio Release): hex-only cache
filenames (traversal impossible by construction; route-tested with
adversarial ids), caller cannot select arbitrary cache files (key is a
digest of validated identities, never of raw input), malformed JSON
artifacts rejected, oversized/free-form alternative payloads and unknown
enums rejected by schema + service validation, extra production-forbidden
fields (e.g. `simulation_count`) rejected. No stack traces, paths, or
model internals in error bodies.

## V3.5 separation

Runtime, API, cache and generator never import or execute V3.5: AST
guard `test_no_v3_5_or_d_runtime_dependency` scans all new modules for
`v3_5`/outcome-model, `v3_6d`, `historical_evaluation`, `case_studies`
and `refinement_decision` imports. D's V3.5 diagnostic stays
research-only.

## Known limitations

- Synchronous live 5000-run requests block for up to minutes; public
  deployment must be cache-first (`V3_STRATEGY_ALLOW_LIVE=0`).
- Cache fixture covers 2 states; broad historical coverage is deferred
  (see capacity estimate).
- Availability catalogue reflects cached artifacts only; live-mode
  support for uncached states is determined by attempt (documented).
- Leaders are point-estimate maxima with frozen tie-break (canonical
  order); ties are order-determined, exactly as the engine defines.
- No 2025, no expected-points, no new actions — all frozen boundaries.

## V3.6G frontend contract

- `POST /v2/strategies/compare-v3` — request/response as above; always
  check `supported` / `unsupported_reason` and `execution_source`
  (render loading/cache states distinctly).
- `GET /v2/strategies/v3/availability` — catalogue for race/checkpoint/
  driver support; never probe support via repeated compare requests.
- Vocabulary: compare, alternative, simulated difference, paired
  simulations, 95% MC interval. Forbidden: best/optimal/recommended/
  should-pit/correct-strategy/guaranteed.
- `leaders` are point-estimate maxima only (not recommendations);
  `deltas[].ci_low/ci_high` + `availability` drive (in)distinguishability
  display; `complete_pairs`/`excluded_pairs` are the honest denominators.
