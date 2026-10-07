# V3.2D MONTE CARLO 2.0 DYNAMICS + STOCHASTIC SCIENCE

## Final verdict

V3.2D COMPLETE — READY FOR V3.2E (selected candidate: ADVANCE_E).

Development-only diagnostics on a bounded 5-checkpoint sample show every
MC2 arm runs clean (0 invalid trajectories), stays within TV 0.09–0.35 of
frozen R3, and preserves coverage exactly. No KEEP/REJECT verdict against
R3 is issued here — that belongs to the V3.2E controlled backtest.

## Frozen baseline

- tag `v3.1-race-dynamics` = commit
  `64c5af094bd1304e23a5c7d3d5b782b0eef11aca`; HEAD matches at entry.
- Accumulated uncommitted work: V3.2A (coverage + architecture audit),
  V3.2B (MC2 scientific contract), V3.2C (presence adapter + DNS repair).
- R3 stochastic science immutable: contract `r3-v1`, set
  `phase6-r3-empirical`, estimator `r3-estimator-v1`, through-2024 hash
  `4c2f85f0…ff3f140`. No R3 module was edited in V3.2D.

## Files changed

V3.2D additions only (tracked paths, nothing staged):

- `raceintel/simulation/mc2/` — new namespace: `__init__.py`,
  `contract.py`, `anchor.py`, `dynamics.py`, `variance.py`,
  `residuals.py`, `traffic.py`, `kernel.py`, `parameters.py`.
- `scripts/run_v3_2d_diagnostics.py` — preregistration-gated
  deterministic diagnostics generator.
- `tests/test_v3_2d_mc2_dynamics.py` — 18 tests (16 source-safe,
  2 corpus-dependent pinned in `scripts/ci_corpus_dependent.txt`).
- `scripts/run_ci_tests.py` — `EXPECTED_COLLECTED` 3616 → 3634.
- `results/v3/v3_2d/` — preregistration, 12 MC2 parameter artifacts,
  parameter_diagnostics, ablation_results, convergence, performance,
  selected_candidate.
- `docs/V3_2D_MONTE_CARLO_2_DYNAMICS.md` (this file),
  `results/v3/v3_2d_mc2_dynamics.json` (machine summary).

Inherited V3.2A/B/C paths are unchanged by V3.2D except the two CI
manifest lines above.

## Repository safety

Entry gate (Part A): HEAD = `v3.1-race-dynamics^{commit}` = `64c5af0…`;
`git status` showed only accumulated V3.2A/B/C paths; nothing staged.
No unexplained paths — gate passed, work proceeded.

## Graphify

- `graphify update .` at entry: 13462 nodes, 32037 edges, 372 communities.
- Targeted navigation used for R3 estimation (`estimator.py`), R4 kernel
  (`engine.py`), R5/R6 Monte Carlo (`monte_carlo.py`), RNG (`rng.py`),
  presence adapter (`presence.py`), field contract
  (`field_contract.py`), V3.1 pace dynamics
  (`raceintel/features/dynamics/contract.py`, `pace.py`).
- Final `graphify update .` re-run after all changes (see Graphify final).

## V3.2C inheritance

- State contract `mc2-field-v1`
  (`713d6e4d…b32691`); presence adapter `v3.2c-presence-v1`.
- Common population: 2305/9644 eligible (23.90%), 103/149 races.
- Eligibility inference frozen: no DNS/STALE/position_null/tyre-backfill
  revisit in V3.2D. `prepare_initial_state` untouched.

## R3 immutable baseline

R3 (`r3-v1` / `phase6-r3-empirical` / `r5-monte-carlo-v1` kernel) is arm A,
executed from the same eligible `SimulationState` as MC2 arms via the
unchanged `from_race_state` → `select_pace_parameters` →
`MonteCarloEngine` path. MC2 lives in `raceintel/simulation/mc2/` and
imports R3 only to *read* the deterministic expectation — never to edit.

## Common experiment population

Preregistered: `results/v3/v3_2c_coverage.json` (2305 eligible states).
Development sample: 5 parity-corpus checkpoints, one per eval season
2020–2024, deterministic MID-stage preference
(`2020-r05-R@340`, `2021-r07-R@340`, `2022-r01-R@360`,
`2023-r05-R@360`, `2024-r01-R@359`). Same state across all arms —
no arm drops difficult states (all report valid+invalid counts).

## Temporal folds

R7-compatible, 2025 never read:

- D1: train through 2019 → evaluate 2020–2021
- D2: train through 2021 → evaluate 2022–2023
- D3: train through 2023 → evaluate 2024

Fold evaluating Y uses R3 parameters through Y−1 (existing
`data/v2/simulation/params/r3-v1__through-*` artifacts) plus MC2
quantities estimated strictly before Y (`check_temporal` enforces
through < Y).

## Preregistration

`results/v3/v3_2d/preregistration.json`, hash
`dc0ae2dbade08514ed3b7cbf5e4be965edccf40b60d7bcad86c99f245854ee16`.
Persisted and hash-verified BEFORE any comparative scoring; the
generator aborts on mismatch. Pins arms, population, folds, training
policy, metrics (winner TV vs A, expected-finish MAE vs A, invalid rate,
coverage parity, residual variance ratio, runs/sec), seeds (R7
`20240101`, MC2 domain `mc2-ar1`, R3 streams unperturbed), counts
(200 dev, convergence 100/200/500/1000), ablation order, traffic gate,
failure policy (failures count as invalid, never refilled).

## Candidate ladder

Pre-registered before scoring: A R3_BASELINE, B DRIVER_ANCHOR,
C DRIVER_ANCHOR_PLUS_DYNAMICS, D CONDITIONED_VARIANCE, E AR1_RESIDUAL,
F TRAFFIC_CONTEXT. F evaluated at its construction gate → NOT_RUN
(no mechanism implemented on invented numbers).

## Driver pace anchor

`mc2/anchor.py`: `anchor_i = shrink(n) × median(clean deviations vs R3
expectation)`, deviations computed against the *contemporary* reference
lap per historical row (causal cummax of leader progress — using T's
reference for past laps would inject the progress trend as bias).
Clean = accurate, kept, no pit markers, `all_clear`, lap > 1, dry
compound + age known, dry weather (R3-B spirit, past-only).

## Anchor window / shrinkage

Windows {3, 5, 8} predeclared; primary 5 (median-family convention,
halved for recency). Shrinkage `n/(n+4)` toward prior 0; clip ±3.0 s.
Fallbacks: `evidence` (n≥3), `thin`, `none` (offset 0 = R3
expectation). Development sample: 100/100 drivers `evidence`
(median 8 clean laps) — no pathological fallback dependence.

## Pace dynamics

V3.2B-admitted features identified from the frozen contract
(`raceintel/features/dynamics/contract.py`): `dyn_pace_slope_l3`
(short-horizon momentum) and `dyn_pace_slope_l10` (stint-scale
momentum), both endpoint deltas `(median_now − median_anchor)/lap_delta`.
No classifier vector enters the simulator: slopes are recomputed
causally from source history at T in deviation domain.

## Dynamics decay

Primary: exponential decay 0.5/lap, bound ±1.5 s, mix
`short + 0.5×long` clipped to one bound (`mc2/dynamics.py`).
Candidates {0.3, 0.5, 0.7} + fixed-horizon-6 available; simplest mid
value taken without outcome tuning. No runaway trajectories by
construction (tested to lap 55+).

## Residual distribution

Audited: R3 empirical quantile residual retained as stored (zero-median,
heavy positive tail — R5-E documents the positive mean). No parametric
replacement: stds re-measured per fold (0.98 through-2019 → 1.46
through-2021 → 1.58 global through-2023; supports [−10, +69] s).
Variance fallback rate in dev sample: 0% inadequate (era always
supported).

## Conditioned variance

Hierarchy `circuit|era (n≥2000)` → `era (n≥30)` → `global`, floor 0.3 s,
ceiling 4.0 s, fallback reason at every selection (`mc2/variance.py`).
Phase/stint/traffic conditioning DECLARED but not estimated (support
inadequate). V3.2D dev: 100% era fallback by design (per-circuit R3
residual groups do not exist).

## Residual autocorrelation

Re-estimated temporally-safe per fold (causal trailing-median lag-1
Pearson on clean laps, estimation races strictly before Y):
D1 ρ=0.225 (n=1208), D2 ρ=0.485 (n=1588), D3 ρ=0.365 (n=2054).
All inside (0.05, 0.8) → AR(1) admitted in every fold. V3.2A reference
0.264 retained as the development prior.

## AR(1) mathematics

`ε_t = ρ·ε_{t−1} + √(1−ρ²)·innovation_t`, |ρ|≤0.8, own-driver only.
Innovation scaling (not recursion scaling) preserves stationary variance
exactly; 20k-draw test: mean <0.05, variance within 5% of target.

## RNG domain

`mc2-ar1` domain (`mc2-rng-v1` tag): same (seed, sim) → identical draws,
per-simulation streams consumed in event order (chunk invariant),
verified unequal to the R3 `rng_for_simulation` stream for identical
inputs. R3 pace/residual streams never perturbed.

## Traffic construction gate

Verdict: NOT_RUN. Gap geometry exists at T, but no temporally-safe
conditioned penalty family was estimated — observed-gap penalties
confound pace-deficit selection with traffic causation, and inventing a
penalty to complete the ladder is forbidden. `traffic_penalty_s`
raises without an evidence family, so F cannot silently run.

## Traffic mechanism

Designed but gated: free-air pace + proximity-weighted penalty
(`base × (1 − gap/2s)`, bound 0.8 s/lap) from factual-at-T or SIMULATED
gaps only. No overtaking physics.

## Stint context

Audited, no compound effects added: degradation already flows through
the R3 mu (age-clamped); anchor/drift/variance/traffic carry no tyre
modifiers without empirical support (none claimed in V3.2D).

## Pit boundary

Frozen: dev comparisons run pits-off on both arms (R6 semantics
untouched). Stint-family recalibration deferred to V3.6 Strategy 2.0.

## DNF boundary

No stochastic retirements simulated. All arms run the V3.2C active
roster; `reliability_enabled` still rejected by the kernel.

## Track/weather boundary

DRY_GREEN only. No wet/yellow/SC/VSC/red evolution; unsupported states
stay refused exactly as V3.2C left them.

## Parameter hierarchy

12 artifacts (`mc2-params-v1`): 4 families × 3 folds, each with schema,
family, training seasons, conditioning, min-N, fallback rules, estimator
config, values, content hash. R3 families never redefined.

## Temporal parameter estimation

Every fold artifact uses history before Y only
(`training_seasons.through` ∈ {2019, 2021, 2023}); `check_temporal`
raises otherwise. No through-2024 retrospective artifact created in
V3.2D (post-acceptance demo material only).

## MC2 architecture

`eligible SimulationState → anchor → bounded dynamics → context variance
→ AR(1) residual → [traffic: OFF] → R4 base + R6 pit boundary →
terminal order`. `run_mc2` mirrors R4 ordering (earliest completion,
`driver_id` tie-break, `(−laps, time, id)` classification). No monolith,
no R3 edits.

## Research version identity

`mc2-r1-research+mc2-kernel-v1+mc2-rng-v1+state:mc2-field-v1+presence:v3.2c-presence-v1`.
Never "accepted"/"final". Contract hash
`25b35762c4f1…04837953`.

## Output semantics

Preserved: winner counts/frequency, expected finish, sample order,
valid/invalid counts. No DNF/event-trajectory claims added.

## ML / MC firewall

MC2 imports stdlib + numpy + simulation contracts only (import-level
scan in-suite). No winner-model invocation anywhere in the MC2 path;
frequencies come solely from simulated outcomes.

## Construction tests

18 tests green: anchor finite/bounded/shrunk/clipped, trend
finite/decaying/bounded, variance positive/bounded/fallback-explicit,
ρ bound + innovation identity, 20k-draw stationary variance, MC2 RNG
determinism + R3 independence, traffic gate, kernel semantics,
extreme states (thin history, huge gaps, lap 55+, missing dynamics).

## Temporal poison tests

Post-T mutations (lap times, pits, classification, tyre state) leave
anchor/dynamics/variance/traffic inputs identical (inputs carry no
future fields by shape); simulated traffic uses simulated gaps only.
Anchor(T) recomputation uses observations ≤ T exclusively.

## R3 regression

V3.2C 70-entry parity corpus untouched; spot check
(`2018-r01-R@90`, pits-off, seed 20240101, n=100) reproduces all 20
winner frequencies bit-exact (abs 1e−9). No R3 file modified.

## Parameter diagnostics

`parameter_diagnostics.json`: anchor 100/100 evidence (median 8 clean
laps); residual families per fold with n/std/support; lag-1 per fold
with stability flags; variance fallback by design; traffic NOT_RUN.

## Development ablations

5 checkpoints × paired A vs B–E, n=200, seed 20240101 (all temporal-safe
parameters). Winner TV vs A: B 0.09–0.34, C 0.115–0.32, D = C,
E 0.09–0.35; expected-finish MAE vs A ≤ 1.7 laps; invalid = 0 on all
25 arm-runs. D≡C because era==available variance level (no independent
D signal in dev); E adds AR(1) persistence (TV moves ±0.03 vs D).
Diagnostics only — no KEEP/REJECT.

## Coverage

Identical population by construction (same `SimulationState` per
checkpoint): eligible 2305/9644 on both arms, 0 eligibility delta,
0 invalid on all dev runs. Complexity never reduces coverage.

## Performance

Measured (200 runs × 5 checkpoints): A 1619, B 188, C 156, D 155,
E 146 runs/sec → E ≈ 11× slower than vectorized R3 (unoptimized
research loop vs batch engine; no premature optimization).

## Convergence

Arm E on `2020-r05-R@340`: winner TV vs n=1000 → 0.068 (n=100),
0.051 (n=200), 0.019 (n=500). V3.2A convention (TV≤0.005) not yet met
at n=1000 — run-count freeze deferred to V3.2E. Demo count NOT frozen.

## Runtime estimate

2305 eligible states at 146 runs/sec: n=1k → 4.4 serial h
(0.55 h @8w); n=5k → 21.9 h (2.7 h @8w); n=10k → 43.7 h (5.5 h @8w).
Planning evidence only.

## Selected candidate

ADVANCE_E: most complete stable mechanism chain (anchor + bounded
dynamics + conditioned variance + admitted AR(1)), 0 invalid, lag-1
stable in all 3 folds, coverage identical, CRN-compatible. Traffic
NOT_RUN. Final verdict deferred to V3.2E.

## Strategy compatibility

Preserved architecturally: deterministic `(master_seed, sim_id)` stream
identity, per-simulation event-order consumption (CRN pairable),
`run_mc2` accepts paired-scenario extension without touching Phase-7.
No Phase-7 migration in V3.2D.

## Known limitations

- Dev sample is 5 checkpoints, not the catalogue backtest (V3.2E).
- D≡C in dev (era-only variance levels); circuit|era variance needs
  a new residual family, not claimed here.
- Anchor primary window 5 is structural, not outcome-tuned.
- Convergence TV≤0.005 not reached at n=1000; research loop 11× slower
  than R3 (optimization only after acceptance).
- Traffic NOT_RUN; wet/neutralised/DNF/strategy untouched by design.

## V3.2E entry gate

Preregistration hash `dc0ae2db…854ee16`; common population
(2305/9644, `mc2-field-v1`); folds D1–D3 with through-{2019,2021,2023}
artifacts; arms A–E runnable + F NOT_RUN; candidate ADVANCE_E with
mechanistic justification; R3 bit-exact; 2025 untouched; no model
training, no serving promotion, no public cache, no frontend;
nothing staged, committed, tagged, or pushed.
