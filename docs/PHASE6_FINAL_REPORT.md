# Phase 6 — Monte Carlo Simulation Engine — Final Report

Status: **PHASE 6 FROZEN.** This report closes Phase 6 (R0–R8). It is factual
and bounded; it makes no calibration, forecasting, real-time, or strategy
claims (see *Known limitations* and *Claim boundaries*).

Phase 6 integrates the already-validated Monte Carlo simulator into the
product while preserving every scientific semantic frozen by R1–R7.1. R8 is
integration, hardening, and freeze — not modelling.

---

## 1. Architecture

```
exact historical anchor (race_id, anchor_driver_id, anchor_lap_number,
anchor_state_time_s)
  └─ Phase-4 RaceStateReconstructor            -> RaceState   (FACTUAL_AT_T)
       └─ v2.simulation.adapter.from_race_state -> SimulationState
            └─ MonteCarloEngine.run              -> MonteCarloResult
                 └─ api.v2_simulation_service    -> aggregate payload
                      └─ POST /v2/simulations/race
                          └─ frontend /simulator
```

- `v2/simulation/*` is the frozen scientific runtime. R8 did not modify it
  (hashes re-verified; `docs/PHASE6_FREEZE_MANIFEST.json`).
- `api/v2_simulation_service.py` owns orchestration only: parameter caching,
  exact-anchor reconstruction, the R2 adapter seam, engine invocation, domain
  error translation. It contains no simulation logic.
- `api/v2_simulation_routes.py` is thin routing; `api/v2_simulation_schemas.py`
  is the HTTP boundary. `MonteCarloEngine` imports no replay, no API, no
  winner model.
- The product path shares the already-loaded Phase-4 corpus and reconstructor
  read-only (the same pattern as Phase-5 replay); it never loads a second
  corpus and never calls the Phase-3 winner model.

## 2. Scientific contracts (frozen)

| Contract | Value |
|---|---|
| simulation contract | `v1` |
| engine | `r4-engine-v1` |
| Monte Carlo | `r5-monte-carlo-v1` |
| pit dynamics | `r6-pit-dynamics-v1` |
| parameter contract | `r3-v1` (estimator `r3-estimator-v1`, eligibility `r3-eligibility-v1`) |
| probability semantics | `MONTE_CARLO_FREQUENCY` |
| RNG | `PCG64`, `SeedSequence([master_seed, simulation_id, contract_tag])` |
| residual sampler | piecewise-linear empirical quantile interpolation |
| execution policy (product) | `RETROSPECTIVE_PRODUCT` |
| product mechanics | pit dynamics enabled |
| contemporaneity reason | `non_contemporaneous_roster_member` (max 3.0 expected lap times) |

## 3. Data and parameter provenance

- Canonical Phase-1 D9 driver-lap state (2018–2024), read through the frozen
  Phase-4 exact-anchor reconstructor. No future rows, labels, results, or
  protected 2025 truth are read at run time.
- Production parameters: the frozen R3 through-2024 artifact,
  `phase6-r3-empirical` / `r3-v1.2024.4c2f85f08f1c`
  (`scientific_hash 4c2f85f0…`). Loaded once, read-only, hash-verified, cached.
  No runtime estimation. Season-specific backtest artifacts are never selected
  by the product service.
- Served product range: **2018–2024**. Any 2025 request → 404 `unknown_race`.

## 4. Deterministic engine (R4)

Lap-step evolution from the driver's own `(lap_number, race_time_s)`; event
ordering by cumulative race time; ordering `(laps DESC, race_time ASC, id)`;
race completion at the leader's scheduled distance. Expected pace is
`base(circuit,era) + constructor_offset + progress_slope·Δlap +
degradation_slope·Δtyre_age` (deltas from T). Zero-noise runs are the
deterministic baseline; no noise, no RNG.

## 5. Stochastic Monte Carlo (R5)

Per-lap empirical residuals drawn from the R3 quantile grid; one winner per
valid trial; win/podium/expected-finish/position distributions aggregated over
valid trajectories only. Winner mass over valid trials is 1 by construction
and is never normalized anywhere in the stack.

## 6. Pit dynamics (R6)

Opt-in historically plausible behaviour: target stint lengths drawn from the
R3 stint-length distribution, dry-filtered compound transitions, one-shot
effective pit loss, tyre-age reset at the stop, domain-separated RNG streams.
The model is behaviour, not strategy, and systematically over-pits by ≈0.3–0.4
stops/driver (documented, not retuned).

## 7. Deferred mechanics (absent, not faked)

Traffic/overtaking, reliability/DNF, stochastic SC/VSC/red generation, weather
evolution, laps-remaining SC unlapping, and strategy/what-if mutation. DNF and
points are therefore `null` in the product response; `reliability_enabled=True`
is rejected rather than fabricating a no-DNF result.

## 8. R7 validation

42 supported historical states across 23 races (2020–2024), evaluated
chronologically with parameters fit strictly before each target season.
Race-macro R6 (pit-enabled): winner log loss **1.2237**, Brier **0.02669**,
expected-finish MAE **2.4452**, RPS **0.09280**, Spearman **0.79837**, ECE
**0.01899**; mean MC standard error of the actual winner **0.0128** at N=1000.
Exclusions (75): 52 non-contemporaneous, 9 wet compound, 6 neutralized, 6
unobserved, 1 wet track, 1 missing tyre age. LATE has only 8 states, so LATE
results are indicative, not precise. No leakage was detected under the
implemented adversarial test suite (not a proof).

## 9. R7.1 defect and fix

R7 found that the runtime evolved roster members whose latest observation was
far older than the anchor T as if contemporaneous, letting a factually
stopped/retired car "finish early" and beat the field (e.g. `2020-r07-R`,
where `giovinazzi` received p(win) ≈ 0.90 while the winner was `hamilton`).
R7.1 added a runtime simulation-start **eligibility** rule: a roster member is
evolved only if `observation_age_s <= 3.0 × expected_lap_time_s`; otherwise
the whole state is refused with `non_contemporaneous_roster_member`. It never
infers retirement, never drops a driver, preserves lapped/active drivers, and
reads no future information. Accepted states reproduce the pre-fix scientific
identity byte-for-byte; the accepted metrics are unchanged.

## 10. API

One core endpoint: `POST /v2/simulations/race`. Exact four-part anchor + a
bounded `simulation_count` and optional `master_seed`. The server reconstructs
the factual state; arbitrary user-created `SimulationState` JSON is rejected.
The response is aggregate only (no raw trajectories, per-event traces, or pit
events) and identifies the anchor, contract/parameter identity, scientific
result identity, valid/invalid counts, seed, mechanics, and runtime. Stable
errors: 404 `unknown_race`, 422 `unknown_state`, 422 `simulation_unsupported`
(machine-readable `reason`), 503 `parameter_unavailable`, 500 `internal`.
Contract: `docs/PHASE6_SIMULATION_API_CONTRACT.json`.

## 11. Count policy

Default **1 000**, synchronous maximum **10 000**, minimum 1. Derived from the
measured product latency (below) and the R7 engine benchmark. No async worker
infrastructure was added.

## 12. Frontend

Minimal `/simulator` surface in the existing race-first telemetry language:
served-race selector, exact-state selection over the frozen replay timeline
(the replay frame's exact anchor is sent), bounded count options, and an
explicit **Run simulation** action. No auto-run, no strategy knobs. Loading,
error/retry, stale-response protection, and result/state identity are handled;
changing race/lap/count clears the prior result. Unsupported states render a
factual message; the non-contemporaneous case never claims a driver retired.
Probabilities are rendered verbatim, never normalized.

## 13. Performance (product path)

`scripts/benchmark_phase6_product.py`, in-process HTTP via TestClient, frozen
through-2024 parameters, seed 20240101, pit dynamics enabled:

| case | count | HTTP total | engine | reconstruct | serialize | valid/invalid |
|---|---|---|---|---|---|---|
| early (`2023-r01-R` alonso lap 2) | 1 000 | 2.36 s | 2.31 s | 0.031 s | 0.008 s | 1000/0 |
| mid (`2022-r01-R` perez lap 30) | 1 000 | 1.17 s | 1.12 s | 0.038 s | 0.005 s | 1000/0 |
| late (`2022-r01-R` russell lap 38) | 1 000 | 0.80 s | 0.75 s | 0.038 s | 0.005 s | 1000/0 |
| mid | 10 000 | 11.31 s | 11.26 s | 0.038 s | 0.006 s | 10000/0 |

Service initialization: corpus 3.67 s, frozen parameters 0.005 s, service
build ≈0 s (one-time; cached singleton). Peak RSS is whole-process with the
full Phase-4 serving stack loaded (~1 013 MB); the R7 simulation-runtime
production memory is ~170 MB. R7 engine-only context: 10k 24.6 s early /
12.7 s mid / 7.3 s late.

## 14. Testing

Environment: Python 3.11.15, NumPy 2.4.2, pandas 2.3.3, macOS arm64. (The
frozen R7 validation environment was Python 3.13.14; frozen result identities
are Python-version-sensitive, as documented in the R7 report.)

- Phase-6 R1–R8 suites (`tests/test_v2_phase6_r1..r71 + r8 + freeze`):
  **647 passed, 7 failed** in 44.08 s.
- R8 backend: `tests/test_v2_phase6_r8.py` — 45 passed (service init,
  production parameter identity, exact reconstruction, replay seam, shared-T,
  validation, count/seed bounds, served range, 2025 404, ordinary simulation,
  probability semantics/invariants, unsupported states incl. the R7.1
  regression, determinism, concurrency, firewalls, schema, performance smoke).
- Phase-6 freeze seal: `tests/test_v2_phase6_freeze.py` — 15 passed (hashes,
  contracts, R7 metrics, API contract, routes, range, semantics).
- **Full repository suite** (`pytest tests/`): **2570 passed, 11 failed,
  5 skipped, 4 xfailed, 56 warnings in 2869.60 s (47:49)**.
- Frontend: 81 `node --test` unit tests passed; typecheck 0 errors; lint 0
  errors (1 pre-existing warning); production build succeeds with the
  `/simulator` route.

The 11 full-suite failures are all pre-existing/environmental, none caused by
the Phase-6 scientific runtime (whose file hashes are unchanged):

| class | count | explanation |
|---|---|---|
| Python-version-sensitive frozen identity | 7 | `test_v2_phase6_r6::test_pit_disabled_reproduces_r5_result_identity` + six `test_v2_phase6_r71::test_accepted_state_matches_pre_fix_result_identity` cases. R7 artifacts were pinned on Python 3.13.14; on 3.11.15 the accepted states reproduce the recorded `state_identity` but a different `MonteCarloResult.identity()` (numpy float values feed the hash). Documented in the R7 report. |
| authorized `api/main.py` drift | 3 | Phase-4/5 freeze manifests pin `api/main.py` (`455910f5…` → Phase-5 `2840271a…`); R8 additively integrates the simulation router to `5a0ec439…`. Historical manifests are deliberately **not** rewritten; `docs/PHASE6_FREEZE_MANIFEST.json` records the drift. |
| stale upstream commit pin | 1 | `test_v2_phase5_r7::test_head_and_phase4_tag_intact` asserts HEAD is the Phase-4 commit; HEAD is the Phase-5 freeze commit. Stale since the Phase-5 freeze, independent of R8. |

No assertion was weakened, no xfail added, and no expected result changed to
make the suite green.

## 15. Known limitations

- No driver-specific pace term (constructor-shared anchor).
- No traffic/overtaking model: free-air ordering only.
- No reliability/DNF hazard; non-contemporaneous states are refused rather
  than modelled.
- Independent per-lap residuals (positive lag-1 correlation documented); the
  residual representation is ~6–22 % wider than the stored sample std.
- No future SC/VSC/red or weather evolution; dry green anchors only.
- Pit timing is behaviour, not strategy; systematic over-pitting ≈0.3–0.4
  stops/driver.
- Lap-boundary 2-lap pit-loss approximation.
- Coverage: 42 supported states / 23 races; LATE only 8; calibration subset
  only 2.
- Product peak RSS reflects the full Phase-4 serving process, not simulator
  isolation.

## 16. Claim boundaries

Allowed: "Monte Carlo outcome frequencies"; "validated on 42 supported
historical states across 23 races"; "no leakage was detected under the
implemented adversarial test suite"; "10k engine simulations completed within
measured R7 ranges". Not claimed: perfect calibration, real-time forecasting,
production-grade forecasting, all F1 race conditions, DNF prediction, weather
prediction, strategy optimization, overtaking simulation, or a causal tyre
model.

## 17. Phase-7 handoff

See `docs/PHASE7_STRATEGY_HANDOFF.md`. Phase 7 owns strategy comparison and
what-if controls (pit now / next lap / stay out / compound choice, expected
outcome under candidate strategy). Phase 6 provides the historically plausible
stochastic future; Phase 7 provides intervention/counterfactual candidate
actions over the same cloneable `SimulationState`/`Assumptions` seam.
