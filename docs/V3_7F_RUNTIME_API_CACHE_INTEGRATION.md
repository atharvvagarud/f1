# V3.7F RUNTIME + API + CACHE INTEGRATION

## Final verdict

V3.7F COMPLETE — RUNTIME/API/CACHE INTEGRATED — READY FOR V3.7G

## Frozen parent

- HEAD: `1eb462631b9d7a948e35b8a1658e3bb90035c94c`
- Tag: `v3.6-strategy-2.0`
- V3.6 scientific card (repository-authoritative full identity, read from
  `results/v3/v3_6_final_scientific_card.json`, field
  `scientific_card_identity`):
  `102079ab81101f442d380c109a32b71a3b6850f0106e021f0fc4b05a64c80aeb`

## A/B/C/D provenance

- V3.7A: schema `v3.7a-counterfactual-contract-v1`, identity
  `1735954212ec31286fede041639875610003a09cf817177e22cc908e3fcb0a12`
  (`results/v3/v3_7a/counterfactual_contract.json`, `contract_hash`).
- Corrected V3.7B/B1: schema
  `v3.7b-counterfactual-execution-contract-v1`, identity
  `1865537503136ed3d8603e53741902c320df9387222655b38eef51640294e970`
  (`results/v3/v3_7b/counterfactual_execution_contract.json`).
- V3.7C engine: `v3.7c-counterfactual-engine-v1`
  (`raceintel.counterfactual.engine.ENGINE_IDENTITY`, validated in
  `results/v3/v3_7c/counterfactual_engine_validation.json`).
- V3.7D: schema `v3.7d-evaluation-card-v1`, card identity
  `96debc6392c79019abedc3a51c7c26fb1536e97cabb3fed3136c43ed7c2b19c3`;
  protocol `v3.7d-evaluation-protocol-v1`, full identity
  `e4a6101c7267f2db9f85c76bcc07c17ed01c7f85de4a6481f94ab0941634c570`
  (field `protocol_hash` in `results/v3/v3_7d/evaluation_protocol.json`,
  pinned in the D card); gate `REFINEMENT_NOT_WARRANTED`
  (`results/v3/v3_7d/refinement_gate.json`, `decision`).
- C simulation seam entry/exit SHA (D card `seam_sha256`, verified equal
  to the working-tree file):
  `045f392e46b030744f18a76140685ceba7501f80c0b8e265af662e57ca5f5376`

## V3.7E skipped status

`SKIPPED_BY_V3.7D_GATE`. No V3.7E file, module, route, or artifact
exists (glob-verified in tests). D concluded `REFINEMENT_NOT_WARRANTED`,
so F exposes the already-validated V3.7C science unchanged.

## Architecture

```text
HTTP request
    |
typed V3.7 API request (api/v2_counterfactual_schemas.py, extra=forbid)
    |
runtime service (api/v2_counterfactual_service.py, cache-first policy)
    |
RaceState(T) resolver (frozen Phase-4 exact anchors, R2 adapter)
    |
F runtime adapter (raceintel/counterfactual/runtime.py)
    |
V3.7 eligibility (frozen B hierarchy, no simulation)
    |
canonical CounterfactualPlan / PlanComparisonKey
    |
cache lookup -> [hit] validated cached result
            -> [miss + explicit server-side live opt-in] V3.7C engine
            -> [miss + live disabled] explicit 404 cache_miss
    |
typed response (live and cached share one projection function)
```

Scientific computation stays `API -> runtime adapter -> V3.7C -> MC2`.
Forbidden edges hold by construction and are test-pinned: the engine
imports no API/cache, the runtime adapter imports no API/frontend/V3.5/
evaluation code (AST-verified), and D evaluation output never enters
runtime calculations (only the D card identity travels as provenance).

## Runtime identity

- `v3.7f-counterfactual-runtime-v1` (`raceintel.counterfactual.runtime`).
- API schema `v3.7f-counterfactual-api-v1`.
- Cache key `v3.7f-counterfactual-cache-key-v1`; cache artifact
  `v3.7f-counterfactual-cache-v1`; manifest
  `v3.7f-counterfactual-manifest-v1`.
- These identify integration mechanics only; A/B/C scientific
  identities are carried verbatim and invalidate the cache naturally.

## API routes

- `GET /v2/counterfactuals/availability` — cheap factual availability
  for one exact anchor (resolves RaceState(T) only; never simulates).
- `POST /v2/counterfactuals/compare` — cache-first comparison.
- Naming follows the `/v2/...` convention. Phase-7
  (`POST /v2/strategies/compare`) and V3.6 (`POST
  /v2/strategies/compare-v3`, `GET /v2/strategies/v3/availability`)
  routes are untouched. One deliberate difference from the V3.6
  proposal: the public compare schema carries **no execution-mode
  field** — cache-first with server-side live opt-in is a runtime
  policy, never a client parameter, so no browser flag can authorize
  expensive scientific execution.

## Availability contract

For one exact `(race_id, anchor_driver_id, anchor_lap_number,
anchor_state_time_s)` key the endpoint returns: `supported`, state
identity, race/season/schedule/leader facts, per-driver decision lap
(own lap at T), remaining laps, eligible N range (`N <= remaining -
1`, `NO_CAP_WARRANTED` per D — no invented product maximum),
factual compounds, supported compounds, rival candidates, multi-stop
capability (any target with room for two triggers), multi-driver
capability, comparison forms, reason codes when unsupported,
cached comparison identities for the state, `live_enabled`, frozen
provenance, and methodological limitations. No historical future, no
future strategy, no results. Deterministic across calls; responds in
well under a second (no simulation).

## Compare contract

Typed strict request: comparison form (`REFERENCE_VS_PLAN` default,
`PLAN_VS_PLAN`), base plan (required iff plan-vs-plan, forbidden
otherwise), alternative plan (targets + `PIT_IN_N_LAPS` schedules +
compound parameter, at most 8 interventions), optional rival. Plans
canonicalize before identity: targets sorted (primary target is the
canonically first, matching the D convention), identical duplicates
collapsed per the B conflict matrix. Rival is comparison-level (plans
carry none); the frozen B COMPARISON verdict owns rival/target
conflicts with explicit unsupported semantics.

## Request validation

Fail closed, never coerced: `N < 1`, unknown kinds, bad compounds,
unknown/off-target/duplicate targets, targets without interventions,
>8 interventions, form/plan presence mismatches, and any extra field
(counts, seeds, modes, historical-future smuggling, recommendation
scores) are 422 (`counterfactual_request_invalid` with a stable
`reason`; pydantic violations use FastAPI's default 422). Horizon
violations, plan conflicts, rival conflicts, and primary-target
mismatches are well-formed but un-simulatable: 200 `supported=false`
with B reason codes and EMPTY metrics.

## Production configuration

Locked to 5000 futures / root seed 20240101 by construction (single
source: frozen B/C contracts). Neither appears in the public schema;
`extra="forbid"` makes override attempts 422. No fast mode, no
approximate fallback, no engine substitution.

## Cache identity

Deterministic SHA-256 over: key/runtime versions, A/B/C identities,
outcome-schema version, MC2 identity, state identity, comparison form,
base/alternative identities, primary target, rival, parameter/config
identities, count, seed. Never display labels, field order,
timestamps, or machine paths. Permuted but semantically identical
plans share identities, hence share cache keys (tested).

## Cache-first policy

Every comparison resolves its cache identity before touching the
engine. Live execution requires explicit server-side opt-in
(constructor flag or `V3_7_COUNTERFACTUAL_ALLOW_LIVE=1`; default is
cache-only). Cache miss with live disabled is an explicit 404
`cache_miss`, never fabricated numbers.

## Live-compute policy

Server-side only. The client request cannot authorize or bypass
expensive execution: there is no mode/live/count/seed field.
When enabled, live runs execute the frozen V3.7C engine at the full
production configuration and write through a validated artifact.

## Cache validation

On read: schema versions, cache-key match, comparison-key field match
(form/state/base/alt/simulator/parameter/count/seed/outcome-schema/
rival), key-identity recompute, result field match (incl. attached
parameter/config identities, primary target), A/B/C/MC2 provenance
match, and served-result-identity recompute. Any mismatch or
malformation raises and is never served: with live enabled the service
falls through to a live run, otherwise 503 `cache_invalid`.

## Direct/live/cache parity

For deterministic eligible fixtures `DIRECT V3.7C == LIVE API ==
CACHED API` on scientific content (aggregates, deltas, pair
accounting, lifecycle, identities), verified for reference-vs-N1/N2/
N>2, multi-stop, plan-vs-plan, rival outcome, and multi-driver at the
production 5000/20240101 configuration.

## N=1/N=2 overlap parity

V3.7 `N=1 SAMPLED` matches V3.6 `PIT_NOW` and V3.7 `N=2 SAMPLED`
matches V3.6 `PIT_NEXT_LAP` on expected finish, win frequency, and pit
count at the API level (schemas differ; science matches).

## Plan canonicalization

Target/intervention/JSON ordering never affects plan identity,
comparison identity, cache key, or results (tested at runtime and
cache layers).

## Outcome orientation

Frozen B orientation preserved end to end with no runtime
transformation: position gain `factual_T - simulated_final`
(positive = gained), comparison `ALT - BASE`; expected finish
`BASE - ALT` (lower is better); win/podium/top5/top10/`P(ahead)`
`ALT - BASE`; pit count descriptive only.

## Position gain

B1 definition intact through direct engine, live API, and cached API
serialization (`P5 -> P2 = +3`).

## Pit count

Expected pit count exposed descriptively (per-future integers plus
expected aggregate). No more/fewer-is-better transformation anywhere.

## Rival handling

Rival only where admitted; factual presence validated; `target ==
rival` (or rival as co-target) returns explicit COMPARISON
unsupported (`RIVAL_NOT_PRESENT`), never a workaround. `P(ahead of
rival)` is a simulated-ordering frequency with `ALT - BASE` deltas.

## Multi-stop

Compositional multi-stop plans execute chronologically in one
trajectory with per-event lifecycle evidence; supersession follows
frozen runtime semantics (absolute window, conservative per C).

## Multi-driver

Validated joint execution with ordering-only propagation. Limits
preserved and disclosed: no pit-box stacking model, no
traffic-battle claim, no team-order model, no team-strategy labels.

## Unsupported semantics

`supported=false` with eligibility level, B reason codes, available
identities, and provenance. Metrics EMPTY (`{}` / null aggregates) —
never 0, NaN, historical, V3.5, V3.6, or Phase-7 substitutes.

## 2025 boundary

Any 2025 race id is outside the served 2018–2024 registry: 404
`unknown_race` on both endpoints. Never routed elsewhere. Tested.

## Temporal safety

Runtime resolution materializes factual RaceState(T) only. Proven by
`read_parquet`-blocked reruns (identical) at runtime, API, and cache
layers; the F stack has no historical-read call sites.

## Cost safety

No client-controlled count/seed/plan-list/intervention-list/target-list
surface: schema caps interventions at 8, targets are roster-bounded,
comparisons take exactly base+alternative, and payload size rides
normal API validation. No N horizon cap invented (`NO_CAP_WARRANTED`).

## Error semantics

| situation | mapping |
|---|---|
| malformed request | 422 `counterfactual_request_invalid` (+ stable `reason`; pydantic violations use the default 422 body) |
| scientifically unsupported | 200 `supported=false` + reason codes, metrics empty |
| cache miss, live disabled | 404 `cache_miss` |
| corrupt cache, live disabled | 503 `cache_invalid` |
| corrupt cache, live enabled | fall through to live run |
| missing parameters | 503 `parameter_unavailable` |
| internal | 500 `internal` |

## D artifact boundary

D is provenance only (`validated_by` card identity + gate in every
response). Runtime imports no evaluation code (AST-pinned), loads no D
deltas/distributions, and never ranks, filters, or recommends plans
from D results.

## Known limitations

- Two V3.7A stage-entry guards trip by charter on F's additive
  integration (frozen tests left unmodified per immutability; V3.7H owns
  Tier-1 reclassification): `test_baseline_clean_at_entry` (entry
  allowlist trips on `M api/main.py` and F additive paths) and
  `test_no_mc2_api_frontend_modification` (trips on the chartered C
  seam plus F `api/` integration). Same-Tier-A run: 233 passed; all
  frozen A/B/C/D contract, engine, evaluation, leakage, and F runtime/
  cache tests green — the trips assert stage-entry cleanliness, not
  scientific semantics. Tier-B API/runtime/MC2-path regression below.

- Second-stop premise uses the absolute supersession window
  (conservative, inherited from C).
- Multi-driver same-lap pits allowed with no stacking delay modelled.
- Compound-specific pace differentiation limited/absent (frozen MC2);
  compound is an intervention parameter, not an optimization claim.
- `TERMINAL` reachable only via individual-finish edge cases (no DNF
  generation exists); time-loss outcome remains research-only.
- Availability `supported=true` is factual eligibility; a compare may
  still return `supported=false` with engine reason codes (e.g.
  wet/retired states).
- Fixture/demo cache only; no combinatorial precomputation shipped.

## G readiness

G can build the frontend using only the F API contract: availability
(state identity, drivers, horizons, compounds, forms, cached/live
status, reasons, provenance, limitations) plus compare (outcomes,
deltas, uncertainty, pair counts, lifecycle, pit count, position
gain, rival result). No Python scientific import is needed client-side.
No frontend was built in F.
