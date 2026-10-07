# V3.2A SIMULATION COVERAGE + ARCHITECTURE AUDIT

Audit stage. The frozen Phase-6 simulator was read, measured, and classified.
No simulator source, parameter, artifact, dynamic, strategy, or serving
artifact was modified. No MC2.0 was designed or implemented beyond naming
gated future stages.

## Final verdict

V3.2A COMPLETE — READY FOR V3.2B CONTRACT (proposed below; V3.2B not started).

## Frozen baseline

- Tag `v3.1-race-dynamics` = `64c5af0`, HEAD identical, verdict KEEP.
- Winner: `ALL_84_PLUS_V3_1_DYNAMICS_CORE` (110 features), trained 2018–2024,
  2025 sealed holdout KEEP.
- V3.1 model artifact `data/v3/v3_1d/final_model_arm_b.joblib`, full SHA
  `9a1aac51…f58960` (authoritative value in machine record `scientific_identities`).
- Serving remains frozen V2 (`1116b34f…59f4`). V3.1 is eligible for future
  promotion only; no promotion occurred.

## Files created

- `docs/V3_2A_SIMULATION_COVERAGE_ARCHITECTURE_AUDIT.md` (this document)
- `results/v3/v3_2a_simulation_coverage_architecture_audit.json` (machine record)
- `scripts/audit_v3_2_simulation_coverage.py` (read-only audit driver)
- `tests/test_v3_2a_simulation_audit.py` (6 audit tests, passing)

## Repository safety

Entry gate held: HEAD = tag commit `64c5af0`; worktree clean except ignored
generated V3 data; nothing staged, committed, tagged, or pushed.

## Graphify

`graphify update .` before and after. 13164 nodes · 31207 edges ·
354 communities. No source topology change from this audit (new audit
script/test only). Targeted queries located the simulator, config, state
types, RNG, parameter tables, aggregation, seed handling, replay/strategy
seams, and eligibility logic without broad crawling.

## Current simulator architecture

Eight frozen stages: R1 contracts/state/config/RNG → R2 RaceState adapter →
R3 empirical parameters → R4 deterministic kernel → R5 stochastic Monte
Carlo → R6 opt-in pit dynamics → R7 evaluation-only validation → R8 product
service (`api/v2_simulation_service.py`, routes in
`api/v2_simulation_routes.py`, `POST /v2/simulations/race`).
Production defaults: pits off, reliability off, 1000 runs default,
10000 synchronous ceiling, seed `20240101`, chunk 512,
`RETROSPECTIVE_PRODUCT` with through-2024 parameters.

## One-run semantics

One simulation = one independent deterministically-seeded trajectory:
checkpoint-T `SimulationState` evolved lap by lap by the R4 kernel with
independent per-lap R3 residual draws until the leader completes
`scheduled_laps`. Pace per lap:
`mu = base(circuit|era) + constructor_offset + progress_slope·(l−T) +
degradation_slope·(clamped age − clamped anchor age)`, plus one empirical
residual draw consumed in strict event order (earliest next completion;
`driver_id` tiebreak). Terminal order is free-air
(laps DESC, time ASC, `driver_id` ASC): exactly one winner per valid trial.
Fixed: start state, anchors, roster, distance, streams. Numerically failed
runs are counted invalid and excluded, never fabricated.

## Input contract

Every input inventoried in the machine record `input_contract` (16 entries:
RaceState fields, R3 families, config, assumptions, explicit non-inputs).
Source families: RaceState (factual at T), empirical R3 parameters
(circuit|era→era/global hierarchies), static metadata (replay handle),
execution semantics (config/assumptions). NOT consumed: winner model,
feature engine, labels, replay prediction cache, any future row
(AST-pinned by structural tests).

## Output contract

SUPPORTED: win frequencies (sum to 1), podium frequencies, expected finish,
full per-driver position distributions, bounded retained `sample_orders`,
valid/invalid counts. NOT_SUPPORTED: points/probabilities of points
(`None`, no points table), DNF probability (`None`, no hazard), trajectory,
event log, per-lap uncertainty. The demo must not promise expected-finish
UX beyond the supported per-driver mean, and must never promise DNF output.

## Probability semantics

ML: `INDEPENDENT_BINARY` per-driver scores, need not sum to 1.
MC: `MONTE_CARLO_FREQUENCY` over mutually exclusive winners, sums to 1 by
construction (invariant-enforced: winner counts total the valid count).
Prohibited: naive averaging, renormalizing ML into an MC distribution,
treating the two estimators as interchangeable.

## Randomness / determinism

PCG64 via `SeedSequence([master_seed, simulation_id, contract_tag])`;
per-simulation streams; R6 pit/compound/loss domains use a 4th entropy word
so enabling pits never shifts the frozen R5 pace stream. Verified live:
same seed+chunk → identical result identity; chunk 64 vs 512 → identical;
request identity stable. Chunking/parallelism never affect science.
CRN (shared per-(seed,index) streams for strategy pairing) is adopted with
documented limitations. No nondeterminism found; `runtime_s` is excluded
from identity.

## Circuit agnosticism

CIRCUIT_CONDITIONED, zero hardcoding: no circuit/race names, no per-circuit
branches in `raceintel/simulation/`. Conditioning flows through data, never
code: pace base and progress slope (`circuit|era`), pit loss/transit
(`circuit`), stint lengths (`era|circuit|compound`), with visible
era/global fallbacks. Kernel, RNG, aggregation, adapter are GENERIC.

## Race agnosticism

No fixed field size or race length (both from state); no year/regulation/
compound-specific logic beyond the two estimation eras
(2018–2021/2022–2024); no SC/pit-pattern assumptions. Limits are data-driven
refusals (wet, neutralised, stale, missing), not hardcoded special cases.

## Supported seasons

Engine eras 2018–2024; estimator reads 2018..through_season, 2025 never
read; R7 evaluated 2020–2024 (2018/2019 excluded: ≤1 estimation season).
Demo cache policy is retrospective through-2024, so all replay seasons
2018–2024 are in principle eligible.

## Replay catalogue

149 races / 9644 checkpoints, verified by direct artifact count; corpus SHA
`78a3c059…98`; served seasons 2018–2024; `generation_mode: matrix`.

## Eligibility contract

Deterministic audit-only classifier = the honest prefix of every real
request: `from_race_state` → terminal check → `select_pace_parameters` →
`_validate_start_state`, under retrospective through-2024 parameters.
No Monte Carlo is run to determine eligibility.

## Overall coverage

2274 / 9644 capable (23.6%). 101 races partially eligible, 48 zero-coverage,
0 fully covered; median race coverage 9.1%. No unsupported state is counted
available: every refusal carries a stable reason token.

## Coverage by season

| season | races | checkpoints | eligible | coverage | full/part/zero |
|---|---|---|---|---|---|
| 2018 | 21 | 1386 | 121 | 8.7% | 0/10/11 |
| 2019 | 21 | 1361 | 547 | 40.2% | 0/18/3 |
| 2020 | 17 | 1127 | 208 | 18.5% | 0/10/7 |
| 2021 | 22 | 1401 | 270 | 19.3% | 0/13/9 |
| 2022 | 22 | 1435 | 333 | 23.2% | 0/14/8 |
| 2023 | 22 | 1412 | 321 | 22.7% | 0/17/5 |
| 2024 | 24 | 1522 | 474 | 31.1% | 0/19/5 |

## Coverage by race

Full 149-race table in machine record `race_coverage`
(`race_id`, season, round, counts, coverage, dominant failure).
Extremes: best `2024-r15-R` 70/72 (97.2%); five races ≥95% (clean,
no pre-T retirement); 48 races at 0%, dominated by early retirements
(e.g. `2018-r05-R` 6 DNFs) or wholesale data gaps (`2018-r02-R` null
tyre state).

## Coverage by stage

EARLY 1198/2830 (42.3%), MID 737/3103 (23.8%), LATE 339/3219 (10.5%).
Eligibility decays with race progress because retirements accumulate and
every post-DNF checkpoint is refused. (492 adapter-level failures carry no
stage.) Early failures are data sparsity (null track/tyre state, incomplete
lap-1 roster); late failures are stale retired drivers and terminal frames.

## Failure taxonomy

`STALE_ROSTER_OBSERVATION` 4590 · `UNSUPPORTED_TRACK_STATE` 1138 ·
`WET_CONDITIONS` 801 · `MISSING_DRIVER_OBSERVATION` 492 ·
`MISSING_TYRE_STATE` 198 · `TERMINAL_STATE` 151. Zero occurrences of
missing-parameter, unsupported-season, temporal-policy, retired-driver,
invalid-input, or reconstruction-failure tokens: parameters cover every
circuit via fallbacks and the reconstruction path is error-free.

## Representative failures

- `2018-r05-R` stale offenders (Ericsson/Gasly/Sirotkin/Grosjean/Magnussen…)
  match factual DNFs with thousand-second observation ages:
  SCIENTIFICALLY_REQUIRED.
- `2018-r05-R` lap 9+ wet refusal under `rainfall=True`: dry-only kernel,
  SCIENTIFICALLY_REQUIRED.
- `2018-r02-R` wholesale null `tyre_life` (zero-coverage race):
  DATA_LIMITATION.
- `2018-r01-R` lap-2 null track state: DATA_LIMITATION.
- Frame-0 unobserved roster (all races): INTENTIONAL_PRODUCT_BOUNDARY.
- Final-checkpoint terminal state: SCIENTIFICALLY_REQUIRED.
No correctness bug proven; no MC2.0 blocker.

## Performance benchmarks

Measured on 9 capable states (3 races × early/mid/late), seed 20240101,
pits off, 0 invalid runs. 100 runs: 0.02–0.08 s. 1000 runs: 0.09–0.56 s
(~1800–11000 runs/s). 10000 runs: early 4.4–5.3 s, mid 2.7–3.1 s,
late 0.9–1.0 s. Cost scales with remaining laps, near-linear in run count.
Aggregate payload ~20 KB. Full rows in machine record `performance`.

## Full-catalogue precompute estimate

2274 eligible states (EARLY 1198 / MID 737 / LATE 339).
MEASURED serial: 1000 runs ≈ 14 min; 10000 runs ≈ 2.3 h.
EXTRAPOLATED serial (verified linear): 5000 runs ≈ 1.2 h.
Reasonable parallel (8 workers): ≈ 2 / 9 / 18 min + overhead.
Storage per corpus EXTRAPOLATED ≈ 46 MB payload (~20 KB × 2274),
≈ 50–100 MB with envelope.

## Cache payload

Minimum: `race_id`, frame/checkpoint identity, leader lap, simulation
version block, input-state hash, parameter identity hash, seed policy +
`n_runs`, winner frequencies in canonical driver order, valid/invalid
counts, payload content hash. Supported-today extras: podium, expected
finish, full position distributions, bounded `sample_orders`. Excluded:
timestamps, hostnames, paths, runtime in identity.

## Demo precompute architecture

Replay state → cache key
(`race_id|frame_index|sim_version|param_hash|seed|n_runs`) → precomputed
result → frontend. Static JSON lookup; unavailable states return explicit
reasons; no hidden live-simulation fallback. The same frozen simulator code
generates the cache locally/Docker-side.

## Local / Docker execution

Docker/local runs the real simulator and returns the cached-demo schema.
Current API (`POST /v2/simulations/race`, exact anchors, 1000/10000) and
the React-free `simulatorMachine.ts` helpers (anchor mapping/display only)
are close; missing: a precompute/export path and the cache corpus itself
(V3.2F work). No Docker changes in this stage.

## Cache identity

Reproduce one result from: schema/version, code identity
(contract+engine+MC versions), checkpoint/RaceState identity, parameter
scientific hash, seed, `n_runs`, output content hash — following the
`simulation_request_identity` precedent (no timestamps/hosts/PIDs).

## Cache invalidation

Stale on: simulator code, parameter artifact, RaceState contract,
checkpoint identity, seed policy, or output-schema change. Frontend
styling/copy never invalidates.

## V3.1 dynamics audit

26 CORE + 3 VARIANT_A (provisional, excluded). Audit classification:
USEFUL_CANDIDATE (13: pace/gap slopes, slope-diffs, vols, spread-change,
traffic frac/n); REDUNDANT_FOR_SIMULATION (5: position changes, gap-count
horizons, history-availability — outcome-derived or bookkeeping);
MODEL_ONLY (8: pit flags, relpace deltas, absolute spread, follower
snapshots — classifier descriptors without a stochastic mechanism);
NOT_JUSTIFIED (3 variants); UNSAFE (none). Full lists in machine record.

## Candidate MC2.0 dynamics

Each candidate names its mechanism or is rejected: gap slopes →
overtake-pressure/variance modulation (needs a non-existent
traffic-interaction mechanism); pace slopes → driver-specific pace anchor
(strongest structural gap, R4-I option C); field compression →
spread-dependent residual variance; traffic persistence → interaction
probability (new family); follower gap → follower-pressure variance
(new family). Rule: no dynamic enters on classifier lift alone.

## ML / simulation firewall

Current coupling is none (AST-pinned imports). Default holds: state
evolution from empirical mechanics, never winner-probability queries. The
V3.1 classifier must not become a hidden oracle without explicit future
experimental justification.

## Empirical parameter audit

13 families, 2018–2024, 124040 eligible laps (162728 rows, 149 races);
residual n=124040, std 1.5 s, lag-1 autocorr 0.264 (independence is a
documented approximation); compound offsets deferred (zero fallback);
pit in/out penalties global-only; sparse regimes: wet, restarts,
neutralised evolution, reliability (absent). Artifact hash
`4c2f85f0…3f140`.

## Temporal leakage audit

No same-race future leakage: RaceState is past-only ≤ T; adapter is
`FACTUAL_AT_T` with no D9 bypass; retirement never inferred (stale refused);
parameters come from historical past races with backtest policy
`through < target`. Training-history evidence ≠ same-race future.

## Simulated events

Supported: pace variation, free-air position changes, pit effects (when
enabled), era-pooled degradation. Not supported: retirements, SC/VSC/red
evolution, traffic, weather, strategy optimisation, compound pace deltas.
Retirement/traffic belong to later phases only with new empirical families;
weather is out of scope.

## Outcome Distribution boundary

V3.5 owns richer Outcome Distribution. Phase-6 already records full
position distributions, expected finish, and bounded `sample_orders` in
every result — V3.5 may aggregate/validate/calibrate later. No V3.5 work
here.

## Strategy boundary

Phase-7 owns strategy via `paired.py` over
`engine.run(collect_index_outcomes=True)` with shared per-(seed,index)
streams and reusable baseline arms. V3.2 must preserve: `run` signature,
index-outcome schema, stream identities, `intervention=None`
byte-equivalence, result identity. Untouched.

## Counterfactual boundary

V3.7 owns the counterfactual lab. V3.2 provides only the clean interface
(cloneable `SimulationState`, `Assumptions` and strategy-owned intervention
seams). No user counterfactuals now.

## Uncertainty boundary

V3.9 owns unified uncertainty. V3.2 may report only MC sampling uncertainty
(MC standard error). Model/simulation/data/calibration/scenario
uncertainties stay separate.

## Demo UX contract

States: `AVAILABLE_CACHED` / `UNAVAILABLE_WITH_REASON` / `LOCAL_ONLY_OPTION`
(no UI built). Public term "Race Simulation" ("Monte Carlo" in technical
details only); primary display "N simulated race futures".

## Demo disclosure

"Historical simulation results are precomputed for fast, reproducible demo
playback. Clone the repository or run the Docker environment to execute
simulations locally." (Final copy may be polished at Portfolio Release.)

## Hosting implications

Cached playback needs no public heavy-Python compute: static JSON plus the
Next.js frontend makes static/serverless hosting (e.g. Vercel) plausible at
~50–100 MB per corpus. No deployment performed. Docker/local retains the
live API.

## MC2.0 scientific gaps

Ranked: (1) driver-specific pace anchor; (2) context-conditioned variance;
(3) traffic interaction; (4) pit-cycle handling (0.3–0.4 over-pitting);
(5) state-dependent stochasticity (AR(1), width mismatch);
(6) neutralisation handling; (7) deeper circuit conditioning. Evidence in
machine record `scientific_gaps`.

## MC2.0 non-goals

New classifier, new target, ensemble, full outcome-distribution research,
strategy recommender, counterfactual UI, ML/MC fusion, pre-race simulation,
spatial physics simulator.

## Experimental ladder

V3.2A audit (this) → V3.2B simulation contract → V3.2C state/dynamics
integration → V3.2D empirical parameter upgrade → V3.2E
validation/backtesting → V3.2F precompute/export contract → V3.2G freeze.
One scientific purpose per stage.

## Future validation strategy

Winner calibration (log-loss/Brier/top-k), order metrics (RPS,
expected-finish MAE, Spearman), race-level bootstrap, seed/parity
stability, convergence, coverage, cost — following the R7 evaluation-only
precedent. Never score single simulated runs as deterministic truth.

## Convergence audit

Top driver stable from n=100; total-variation 1k→5k ≤ 0.011, 5k→10k ≤
0.0016 (3 states × 100/500/1k/5k/10k). Full rows in machine record
`convergence`.

## Demo run-count recommendation

5000 runs (recommendation, not frozen): captures convergence (marginal
5k→10k gain ≤ 0.0016 TV at ~2× cost); n=100 shows up to 0.054 instability.
10000 remains the justified high-quality alternative pending V3.2E.

## Security / trust boundaries

Verify content hash + parameter identity on ingestion; validate
identifiers against the manifest; bound counts/seeds; serve JSON as data,
never code; pin Docker deps with offline serving; ship version/identity in
every payload. Portfolio Release needs the full repository security audit
(Cloudflare security-audit skill as one input, plus
deployment/container/dependency checks). Not run now.

## Scientific identities

V3.1 tag → `64c5af0…`; V2 serving `1116b34f…59f4`; Phase-2 content
`d2ee966c…`, parquet `b0f17b66…`; explainability `bae84b61…`;
replay `78a3c059…98`; simulation `r3-v1` through 2024
`phase6-r3-empirical`; V3.1 artifact SHA
`9a1aac515d12c4e86ac369977392f74394cf7f6853b8e89d948bcdec28f58960`
(`ELIGIBLE_FOR_FUTURE_SERVING_PROMOTION`, unpromoted). Verified without
regeneration; full values in machine record.

## Known limitations

23.6% coverage (48 zero-coverage races, 0 full, median 9.1%); post-DNF
refusals by design; dry-green anchors only; constructor-shared pace
anchor; independent residuals; free-air ordering; pit over-behaviour;
numpy-version-sensitive MC identities (documented R7 finding); no
DNF/points/trajectory/event outputs.

## V3.2B entry gate

Simulator untouched · nothing regenerated · no training · no strategy
change · no demo frontend · zero unexplained dirty paths · nothing staged/
committed/tagged/pushed · V3.2B not started. V3.2B may proceed to freeze
the simulation contract.
