# PHASE 11 P11-3 FINAL PERFORMANCE BENCHMARK

Authoritative final performance measurement of the frozen F1
Intelligence v2 release candidate. The system was measured exactly as
it exists: no code, algorithm, cache, API, frontend, Docker,
dependency, or input change. This stage measures performance; it does
not improve it.

## Final verdict

P11-3 COMPLETE — READY FOR P11-4. All six frozen P11-2 anchors
measured native and containerized (28 operation-records, zero
failures, all semantic checks green), methodology recorded, portfolio
candidates selected defensively, artifact hashed.

## Frozen baseline

- HEAD: `3c069b529f568dd25ea4a8213a6579afad631c0e`
- Tag at HEAD: `v2-productionization-phase10`
- P11-2 summary SHA verified before benchmarking:
  `5091cb777dd9a5362e1db1cc5666b129c3f538ac4747d6aede19632222e0971c`
- No scientific identity re-verified by recomputation; the release
  candidate is the P11-2-validated tree (no product/scientific change
  in P11-3).

## Repository safety

At start: HEAD/tag exact, nothing staged. Dirty paths classified, zero
UNKNOWN: PREEXISTING_OTHER_WORK (unchanged), P11_0 + P11_1 reports
(unchanged), P11_2 (`docs/PHASE11_P11_2…md`,
`results/v2_final_validation/p11_2_validation_summary.json`,
unchanged). Graphify updated (code graph only). No git add/commit/tag/
reset/restore/checkout/clean/stash in P11-3; P11-3 files remain
uncommitted.

## Environment

| Field | Value |
|---|---|
| OS | macOS (Darwin) |
| Architecture | arm64 |
| CPU | Apple M4, 10 logical CPUs |
| RAM | 17.2 GB |
| Python | 3.11.15 |
| Node | v22.23.1 |
| Docker | 29.8.0 |
| Docker Compose | v5.5.1 |
| Concurrency | 1 (single-request latency; no load testing) |
| Network ingestion | OFF |
| Competing workloads | none intentional (benchmark server or compose stack only) |

No usernames, home paths, UUIDs, IPs, or secrets recorded.

## Methodology

- Timer: `time.perf_counter_ns()` (monotonic, high resolution).
- Boundary: client-observed complete local HTTP request duration over
  loopback (native `uvicorn` on a local port; container backend via
  published port). Server `duration_ms` never substituted, never called
  inference latency.
- Percentiles: one consistent NumPy linear method for every operation.
- Warm-ups excluded from statistics: cheap ops 5, MC-1k 2, MC-10k 1,
  strategy 1, frontend 5.
- Samples: cheap N=200 (health, state, predict, replay), moderate N=100
  (readiness, explanations, frontend), MC-1k N=30, MC-10k N=10,
  strategy N=20. p99 over N<100 is an empirical percentile over a
  limited sample, not a production SLO.
- Outliers: none discarded; failures recorded separately (zero).
- One documented full rerun: the first container attempt completed all
  11 backend operations green but the script crashed before persisting
  when JSON-parsing frontend HTML; after adding a raw-HTML timing path
  the entire container operation was rerun. No cherry-picking.
- Native/container and direct/HTTP boundaries kept separate (all
  measurements here are HTTP; no direct-Python timings mixed in).

## Benchmark anchors

Exact P11-2 frozen anchors, including the perez lap-20 correction
(lap-30 does not exist in served 2022-r01-R data; lap-30 never
restored): 2019-r01-R bottas lap-1 2106.767s (predict/replay/explain),
frame 20-from-0 change, 2022-r01-R perez lap-20 5761.839s seed 7
(simulation + strategy MAXIMIZE_WIN_PROBABILITY, 100 sims, 4 default
candidates).

## Health

GET /health, W5. Native N=200: min 0.6 / p50 0.7 / p95 1.1 / p99 1.5 /
max 3.4 ms. Container N=200: min 0.7 / p50 0.9 / p95 2.1 / p99 2.8 /
max 3.7 ms. STATIC_SERVICE. Baseline HTTP/service overhead.

## Readiness

GET /ready, W5. Native N=100: p50 0.8 / p95 0.9 / p99 1.2 / max 1.9 ms.
Container N=100: p50 0.9 / p95 1.5 / p99 3.2 / max 4.8 ms.
WARM_READINESS; the server may use its internal readiness cache (not
defeated).

## RaceState

Frozen anchor retrieval, W5. Native N=200: p50 1.6 / p95 2.1 / p99 2.3 /
max 2.6 ms. Container N=200: p50 2.2 / p95 3.6 / p99 4.1 / max 5.0 ms.

## Prediction

winner-snapshot INDEPENDENT_BINARY (20-driver full field, unnormalized),
W5. Native N=200: p50 87.7 / p95 90.1 / p99 98.2 / max 281.0 ms.
Container N=200: p50 102.2 / p95 109.4 / p99 112.4 / max 126.0 ms. All
probabilities finite in [0,1]; null-with-reason semantics held on
every sample.

## Replay

CACHE_HIT, no rebuild, W5. Timeline — native N=200: p50 1.0 / p95 1.3 /
p99 1.4 ms; container: p50 1.4 / p95 2.1 / p99 2.4 ms. Cached frame-0
prediction — native: p50 0.9 / p95 1.1 / p99 1.3 ms; container: p50 1.0 /
p95 1.7 / p99 1.9 ms. Every sample returned frame 0 with HIT status.

## Explainability

COMPUTE over cache-backed input, W5. Local LOG_ODDS — native N=100:
p50 20.2 / p95 20.9 / p99 21.1 ms; container: p50 22.5 / p95 24.7 /
p99 25.2 ms. Timeline change frame-20-from-0 — native: p50 40.7 /
p95 42.6 / p99 50.1 / max 234.7 ms; container: p50 45.3 / p95 47.9 /
p99 50.8 / max 245.7 ms (isolated slow first samples retained, not
discarded). No global evidence regenerated.

## Monte Carlo — 1,000 trials

Frozen seed 7, parameter identity phase6-r3-empirical, W2, N=30.
Native: p50 1550.5 / p95 1564.8 / p99 1566.0 / max 1566.1 ms.
Container: p50 1700.6 / p95 1723.0 / p99 1729.0 / max 1729.2 ms.
Requested == valid on every sample.

## Monte Carlo — 10,000 trials

Frozen seed 7, W1, N=10 (sufficient per mission; trial count never
reduced for prettier latency). Native: p50 15350.4 (≈15.4 s) /
p95 15839.3 / p99 16100.1 / max 16165.3 ms. Container: p50 16549.2
(≈16.5 s) / p95 16599.6 / p99 16605.3 / max 16606.7 ms. Requested ==
valid on every sample. The Phase-6 ≈11.31 s mid-state observation is
superseded by these final measured values on the frozen anchors.

## Strategy comparison

STRATEGY COMPARISON LATENCY (never an optimizer benchmark). Frozen
anchor: baseline + 4 default candidates, 100 sims, seed 7,
MAXIMIZE_WIN_PROBABILITY, W1, N=20. Native: p50 1037.6 / p95 1041.1 /
p99 1041.2 / max 1041.2 ms. Container: p50 1092.9 / p95 1125.2 /
p99 1310.6 / max 1356.9 ms. Candidate count and objective matched the
anchor on every sample.

## Native vs container

Kept separate in all 28 records; never averaged. Container is modestly
slower across operations (loopback + Docker Desktop virtualization on
macOS); no universality claim made. Full per-operation tables live in
the artifact.

## Optional frontend server timing

Measured (cheap, non-blocking): N=100, W5 per route against the
production compose frontend. LOCAL FRONTEND SERVER RESPONSE TIME only:
`/` p50 1.0 / p95 1.3 ms; `/replay` p50 1.0 / p95 1.3 ms; `/simulator`
p50 1.0 / p95 1.3 ms; `/strategy` p50 1.0 / p95 1.2 ms; `/models`
p50 2.2 / p95 2.8 ms; `/about` p50 1.7 / p95 1.9 ms. Never page load,
render, hydration, browser performance, or Core Web Vitals — no browser
engine exists or was installed.

## Measurement boundaries

Every record carries its boundary: client-observed complete local HTTP
request duration (perf_counter_ns), concurrency 1. Server endpoint
duration appears nowhere as a benchmark number. HTTP latency is never
described as model inference latency. No throughput derived.

## Portfolio metric candidates

Five defensible candidates in the artifact (product-facing HTTP,
p50+p95, 10k simulation for scale, no cherry-picking): prediction
≈88/102 ms; replay HIT ≈1 ms; explanation ≈20/22 ms; 10k simulation
≈15 s / ≈17 s; strategy ≈1 s. Selection only — no marketing copy.

## Limitations

Local loopback only (never cloud); no browser metrics; endpoint
duration ≠ inference latency; readiness cache intact; small-N p99 is
empirical; no throughput/load claims; Docker Desktop overhead on macOS;
benchmark machine only; timing values non-deterministic (schema and
method deterministic, timings empirical).

## Benchmark artifact

`results/v2_final_validation/p11_3_performance_benchmark.json` —
schema `p11-3-performance-benchmark-v1`, 28 operations with full
statistics and raw sample arrays, no timestamps/paths/hostnames/
secrets. SHA-256:
`c9fe7f89c40001b35ee2f8d3dd11da20b7945bb1168a7667fc1e702d44e45d58`.
`p11_2_validation_summary.json` untouched (P11-2 frozen).

## Scientific firewall

P11-3 added only the benchmark script, its unit tests, the benchmark
artifact, and this report, plus a fail-closed collection-pin update
(3202→3210 for the 8 new script tests, same protocol as P11-1). No
change to `ml/`, `v2/`, `api/`, `data/`, frozen artifacts, `frontend/`,
Dockerfiles, Compose, or CI behavior. No training, fitting, FastF1,
generation, or 2025 evaluation. No Tier-3 rerun; no broad Tier-1 rerun
(selector mechanism verified by collection math: 3210 collected,
721 corpus nodes covered, 2489 selected).

## Risks / blockers

None blocking. Noted: MC-10k container p99 rests on 10 samples
(empirical); B5b max samples are retained first-touch outliers;
pin must be revisited if tests are added later (fail-closed by design).

## P11-4 handoff

Inputs: this report, the benchmark artifact (SHA above), portfolio
candidates. P11-4 (Case Study Evidence + Visual Assets) may cite the
candidates with their safe wordings and boundaries; it must not invent
browser, throughput, or cloud numbers.

## Entry gate

- [x] Phase-10 HEAD/tag exact
- [x] nothing staged
- [x] dirty paths fully classified
- [x] P11-2 summary SHA verified
- [x] exact P11-2 anchors used
- [x] Pérez lap-20 correction preserved
- [x] environment recorded safely
- [x] methodology recorded
- [x] high-resolution monotonic timer used
- [x] warm-ups excluded
- [x] percentile method consistent
- [x] concurrency = 1
- [x] health native + container measured
- [x] readiness native + container measured
- [x] RaceState native + container measured
- [x] prediction native + container measured
- [x] replay timeline native + container measured
- [x] replay cache HIT native + container measured
- [x] explanation native + container measured
- [x] timeline-change explanation measured (frozen anchor)
- [x] MC 1,000 native + container measured
- [x] MC 10,000 native + container measured
- [x] strategy native + container measured
- [x] all benchmark semantic checks green
- [x] no samples silently discarded
- [x] failures recorded (zero everywhere)
- [x] native/container kept separate
- [x] direct/HTTP boundaries kept separate
- [x] server duration not called inference latency
- [x] no browser metrics fabricated
- [x] no throughput fabricated
- [x] no cloud latency claim
- [x] portfolio candidates selected defensibly
- [x] benchmark artifact created
- [x] artifact contains no sensitive machine identifiers
- [x] artifact SHA recorded
- [x] timing non-determinism documented
- [x] report complete
- [x] no application/scientific behavior changed
- [x] scientific firewall green
- [x] no Tier-3 rerun
- [x] nothing staged/committed/tagged
- [x] unrelated work untouched
- [x] P11-4 handoff explicit
