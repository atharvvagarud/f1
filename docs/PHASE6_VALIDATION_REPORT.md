# Phase 6 — R7 Historical Validation Report

Status: **R7 complete as a scientific validation exercise; scientific
decision is BLOCKED — SIMULATION CONTRACT ISSUE.** R7 adds no product
feature, no tuning, no API, and no frontend. Everything below is measured on
the frozen R6 candidate. Nothing is staged or committed.

Environment: Python 3.13.14, NumPy 2.4.2, pandas 2.3.3, macOS (arm64).
All simulation/validation outputs are deterministic given this environment;
`r7_validation.json` and `r7_benchmark.json` are the machine-readable
artifacts under `data/v2/simulation/validation/` (repository-untracked).

---

## 1. R6 candidate frozen before scoring (R7-A)

Computed before any validation score was inspected (SHA-256 of the working
file, `git` HEAD `ddee871`):

| module | sha256 (first 16) |
|---|---|
| `v2/simulation/state.py` | `051922bc96a02cbd` |
| `v2/simulation/config.py` | `8164553ebfc82709` |
| `v2/simulation/params.py` | `efc66b20bfcd3bbd` |
| `v2/simulation/engine.py` | `2f146f205ceb0685` |
| `v2/simulation/monte_carlo.py` | `2ccb1d2b13da1e6c` |
| `v2/simulation/rng.py` | `f357eea5c5743eee` |
| `v2/simulation/results.py` | `4b8827cf0d10290f` |
| `v2/simulation/adapter.py` | `b42f1f77c5059293` |

Frozen contracts: `SIMULATION_CONTRACT_VERSION=v1`,
`PARAMETER_CONTRACT_VERSION=r3-v1`, `MONTE_CARLO_VERSION=r5-monte-carlo-v1`,
`PIT_DYNAMICS_VERSION=r6-pit-dynamics-v1`; RNG `PCG64` with
`SeedSequence([seed, simulation_id, tag])` and SHA-256 domain separation;
residual sampler = piecewise-linear empirical quantile interpolation;
pit model = R3 stint-target draws + dry-filtered transitions + one-shot
effective pit loss. Traffic/overtaking, reliability, weather evolution and
SC/VSC/red generation remain **deferred and absent**.

Two genuine defects were found *after* the freeze and are documented
separately in §12; the R6 scientific result identity is unaffected by
either.

## 2. Validation protocol (R7-B)

`v2.simulation.validation.default_protocol()`; machine-readable copy at
`data/v2/simulation/validation/r7_protocol_v1.json`.

- protocol: `r7-validation-v1`, identity
  `d071b09b40bc6f79853f8d90a0744b73aec887f0efa0e863820bc6c53028ab20`
- evaluation seasons: 2020–2024 (2018/2019 excluded: the expanding-window
  rule leaves ≤1 prior estimation season; 2025 never eligible)
- parameter cutoff: `through_season = evaluation_season - 1`
- stages: EARLY 25%, MID 50%, LATE 75% of `scheduled_laps`
- state rule: nearest supported frame by leader lap, frozen tie-break
  `(|Δlap|, leader_lap, frame_index)`, frozen radius
  `max(3, round(0.10·scheduled_laps))` laps; a stage outside the radius is
  excluded, never substituted
- support: exact R4 engine checks + `all_clear`, dry, full roster, tyre age
  present, parameter support, **and the R7-BUG-2 contemporaneity criterion**
  (§12)
- broad count 1000, calibration subset count 10000, seed 20240101
- winner log epsilon 1e-6, position log epsilon 1e-6
- calibration bins `[0, .01, .02, .05, .10, .20, .30, .40, .50, .60, .70,
  .80, .90, .95, .99, 1.0]`
- baselines: CURRENT_ORDER, CURRENT_LEADER, GRID_ORDER, R4_DETERMINISTIC,
  R5_NO_PIT
- bootstrap 1000 race-level replicates, seed 42
- unsupported policy: exclude `(race, stage)` with a reported reason

## 3. Temporal parameter artifacts (R7-C/D)

Generated with the frozen R3 estimator; the through-2024 artifact is
**not** overwritten.

| evaluation season | artifact | estimation seasons | eligible laps | size | scientific hash |
|---|---|---|---|---|---|
| 2020 | through-2019 | 2018–2019 | 34,482 | 140 KB | `54c1cf985a0b5fb0` |
| 2021 | through-2020 | 2018–2020 | 48,313 | 167 KB | `6869317c425870df` |
| 2022 | through-2021 | 2018–2021 | 66,864 | 197 KB | `092181b08e4b2b7c` |
| 2023 | through-2022 | 2018–2022 | 83,531 | 240 KB | `783fa6c3f6b43c15` |
| 2024 | through-2023 | 2018–2023 | 103,080 | 271 KB | `a590b43c9a383a32` |

Each artifact was rebuilt independently at run time (sub-second) and
re-derived its scientific hash; no future season (relative to an evaluated
race) is ever read.

## 4. Coverage and exclusions (R7-E/F/G)

Systematic deterministic sample: 39 races (2020: 9, 2021: 8, 2022: 8,
2023: 8, 2024: 6). 117 stage candidates → **42 supported states across 23
races**.

| stage | supported |
|---|---|
| EARLY | 23 |
| MID | 11 |
| LATE | 8 |

Exclusions (75): `non_contemporaneous_roster_member` 52,
`wet_compound_state` 9, `neutralized_track_state` 6,
`unobserved_roster_member` 6, `wet_track_conditions` 1, `missing_tyre_age` 1.
The same selection logic is fully reported in `r7_validation.json`
(`races`, `exclusions`); no unsupported checkpoint was replaced.

Coverage limitation: LATE has only 8 states, so LATE results are
indicative, not precise.

## 5. Baselines (R7-J)

All baselines are built from factual T-state, grid, or deterministic-kernel
data only; the Phase-3 winner model is deliberately **not** used.

- `CURRENT_ORDER`: T free-air order `(laps DESC, time ASC, id)` as point
  finish prediction.
- `CURRENT_LEADER`: one-hot winner on the T leader.
- `GRID_ORDER`: one-hot winner on grid pole (where grid is available).
- `R4_DETERMINISTIC`: zero-noise R4 classification.
- `R5_NO_PIT`: same stochastic engine and seed with pits disabled.

## 6. Winner probability results (R7-K)

Race-macro means over 42 states (lower is better):

| model | winner log loss | Brier |
|---|---|---|
| R6 pit-enabled | **1.224** | **0.0267** |
| R5 no-pit | 2.225 | 0.0280 |
| CURRENT_LEADER / CURRENT_ORDER | 4.276 | 0.0310 |
| R4_DETERMINISTIC | 4.605 | 0.0333 |
| GRID_ORDER | 7.237 | 0.0524 |

Top-k (R6): top-1 0.643, top-3 0.881. CURRENT_ORDER top-1 0.690, top-3
0.690; R5 top-1 0.667, top-3 0.881.

Honest nuance: R6 has a much better macro mean, driven mainly by
eliminating catastrophic misses (states with winner log loss >10: R6 0,
R5 4). Per state, R6 has a lower winner log loss than CURRENT_LEADER in only
13/42 states and lower top-1 accuracy than the T leader; its advantage is
that its top-3 and its distributions are far more informative. It does not
dominate the trivial leader baseline state-by-state.

## 7. Finish-position results (R7-L/M)

Race-macro over 42 states:

| metric | R6 | R5 | CURRENT_ORDER | R4 | GRID |
|---|---|---|---|---|---|
| expected-finish MAE | 2.445 | 2.428 | 2.223 | 2.466 | 3.115 |
| RPS (normalized) | **0.0928** | 0.1021 | 0.1170 | 0.1298 | 0.1630 |
| Spearman | 0.798 | 0.800 | 0.822 | 0.800 | 0.698 |
| position NLL (clipped) | 2.757 | — | — | — | — |

R6 is best on RPS and competitive on MAE/Spearman; CURRENT_ORDER is a strong
point-order baseline (as expected once a race is in progress) but carries no
distribution. No opaque composite score is used.

## 8. Stage results (R7-P)

R6 race-macro by stage:

| stage | n | winner log loss | Brier | MAE | RPS |
|---|---|---|---|---|---|
| EARLY | 23 | 1.440 | 0.0297 | 2.920 | 0.111 |
| MID | 11 | 1.053 | 0.0235 | 2.088 | 0.078 |
| LATE | 8 | 0.838 | 0.0224 | 1.571 | 0.059 |

On this subset the expected qualitative pattern holds: winner probability,
finish ranking and RPS all improve monotonically from EARLY to LATE. This is
measured, not assumed.

## 9. Season results

R6 winner log loss by season: 2023 0.547, 2020 0.982, 2021 1.143, 2022
1.495, 2024 2.209. MAE: 2021 1.801, 2024 2.137, 2023 2.338, 2020 2.822,
2022 3.041.

## 10. Calibration (R7-N)

Winner-probability reliability over contemporaneous states:

| population | points | ECE |
|---|---|---|
| all (broad 1000 + subset 10000) | 920 | 0.019 |
| broad 1000 only | 840 | 0.0196 |
| calibration subset 10000 | 80 | 0.0215 |

The calibration subset is the per-season first selected race at MID; only
2022-r01 and 2024-r01 survived the contemporaneity criterion, so the 10 000
population is small (80 driver points) and is reported with counts. No
Platt/isotonic fitting is performed. The high-confidence bins are thin
(0.8–1.0: n≤5) and the broad-bin reliability is close to the diagonal; no
catastrophic calibration pathology remains after the R7-BUG-2 exclusion
(before it, the 0.99–1.0 bin had confidence 0.999 and accuracy 0.0).

## 11. Monte Carlo uncertainty (R7-O)

Mean MC standard error of the actual winner's probability at N=1000:
**0.0128** (max over states is bounded by 0.5/√1000 = 0.0158). Headline
race-macro differences between R6 (1.224) and R5 (2.225) are far larger
than this noise; the small per-state R6-vs-R5 differences in §6 are not.
Finite-simulation error is reported separately from model error and is never
called calibration.

## 12. Pit-behaviour validation (R7-Q)

Per-state stop-count comparison (simulator total vs factual total stops per
driver, same roster):

| stage | n | mean simulated | mean historical | mean difference | mean TV distance |
|---|---|---|---|---|---|
| EARLY | 23 | 2.60 | 2.20 | +0.40 | 0.35 |
| MID | 11 | 2.48 | 2.14 | +0.34 | 0.35 |
| LATE | 8 | 2.49 | 2.18 | +0.30 | 0.33 |

Distributionally plausible, but the simulator **systematically over-pits**
by ≈0.3–0.4 stops/driver, worst cases +1.06 (`2024-r01-R` Bahrain), +0.99
(`2023-r10-R` Silverstone), +0.86 (`2024-r17-R` Baku). Compound transitions
are all dry; legacy compound names (`SUPERSOFT`, `ULTRASOFT`, `HYPERSOFT`)
appear with their observed small frequencies (R3-faithful, documented).
The pit model is behaviour, not strategy.

### Early-stop-count investigation (R7-R)

The R6-observed `~3.06` stops/driver (benchmark early fixture,
`2023-r01-R` lap 2, R6 diagnostics) is reproduced exactly after the
diagnostic fix: **3.061**. Factual total stops/driver for that race are
**2.60**, so the simulator over-pits by **+0.46**. The cause is that the R3
`stint_length_laps` distribution is *unconditional observed behaviour*, and
the simulator keeps drawing fresh stint targets until the race ends, so a
55-lap remaining window yields ≈55/18 ≈ 3 stints while teams actually plan
≈2 stops to the finish. **Diagnosis: modelling limitation, not a contract
bug.** It is not retuned.

## 13. Residual sampler audit (R7-S)

`residual_sampler_audit` on the temporal artifacts:

| residual support | n | artifact std | grid (Q-function) std | sampled std | ratio |
|---|---|---|---|---|---|
| 2018–2019, era/global | 34,482 | 0.977 | 1.096 | 1.095 | 1.121 |
| 2018–2020, era/global | 48,313 | 1.444 | 1.536 | 1.534 | 1.062 |
| 2018–2021 (through-2022/2023) | 66,864 | 1.457 | 1.732 | 1.727 | 1.186 |
| 2022–2024, through-2023 | 36,216 | 1.793 | 2.190 | 2.190 | 1.221 |

Findings: the sampler **correctly** realises the intended piecewise-linear
quantile function (sampled std ≈ grid std, ratios ≈1.00); the discrepancy is
between the artifact's stored raw-sample `std` and the quantile-function
representation. The dominant mechanism is endpoint insertion: the grid adds
`(0, observed_min)` and `(1, observed_max)`, and the observed maxima lie far
above the 0.999 quantile (upper gaps 19–57 s). Linear interpolation across
`(0.999, q999) → (1, max)` spreads the top 0.1 % of mass over tens of
seconds, inflating the variance. Verdict: primarily **C** (two different
representations) with a clear contribution from **B** (endpoint/tail
weighting); **A** is false (the sampler does not misrepresent its own grid).
No sampler change is made.

## 14. Residual sensitivity (R7-T)

Diagnostic alternative only: `variance_matched_parameter_set` rescales each
residual grid so its piecewise-linear variance equals the stored `std`.
Effect on the two surviving calibration-subset states:

| state | sampler | winner entropy | finish spread | winner LL | Brier | MAE | RPS |
|---|---|---|---|---|---|---|---|
| 2022-r01 MID | production | 1.374 | 2.818 | 0.911 | 0.0242 | 3.811 | 0.1439 |
| 2022-r01 MID | variance-matched | 1.346 | 2.761 | 0.875 | 0.0233 | 3.823 | 0.1445 |
| 2024-r01 MID | production | 0.895 | 2.616 | 0.341 | 0.0061 | 1.454 | 0.0538 |
| 2024-r01 MID | variance-matched | 0.840 | 2.509 | 0.319 | 0.0056 | 1.449 | 0.0534 |

The residual-SD discrepancy is **immaterial** to headline metrics (small
reductions in entropy/spread; LL changes ≈0.02–0.04). The production
sampler is retained.

## 15. R5 no-pit vs R6 pit-enabled (R7-U)

Same states and seeds. Macro means (lower better for LL/Brier/MAE/RPS):

| metric | R6 | R5 | per-state R6 better |
|---|---|---|---|
| winner log loss | 1.224 | 2.225 | 13/42 |
| Brier | 0.0267 | 0.0280 | 14/42 |
| expected-finish MAE | 2.445 | 2.428 | 17/42 |
| RPS | 0.0928 | 0.1021 | 33/42 |

R6 is not assumed better: it clearly improves RPS and reduces catastrophic
winner misses, but R5 is marginally better on MAE and, state-by-state, on
winner log loss. The calibration subset (2 states) actually favours R5 on
winner LL. Reported without assuming R6 dominates.

## 16. Deterministic baseline (R7-V)

R4 zero-noise: winner LL 4.605, Brier 0.0333, MAE 2.466, RPS 0.130. The
deterministic base pace/accounting alone is weaker than the stochastic R6
distributions, separating accounting quality from stochastic/pit dynamics.

## 17. Bootstrap uncertainty (R7-W)

Race-level bootstrap (unit = race, 23 races, 1000 replicates, seed 42):

| metric | mean | 95% CI |
|---|---|---|
| winner log loss | 1.246 | [0.822, 1.771] |
| Brier | 0.0273 | [0.0191, 0.0354] |
| expected-finish MAE | 2.682 | [2.287, 3.127] |
| RPS | 0.103 | [0.087, 0.121] |

No driver-state rows are bootstrapped as if independent.

## 18. Failure analysis (R7-X)

Worst winner log loss (hypotheses only):

| race | stage | actual winner | predicted winner | LL |
|---|---|---|---|---|
| 2024 Hungarian GP | EARLY | piastri | max_verstappen | 5.52 |
| 2022 Hungarian GP | EARLY | max_verstappen | leclerc | 4.83 |
| 2024 Azerbaijan GP | EARLY | piastri | perez | 4.34 |
| 2024 Hungarian GP | MID | piastri | max_verstappen | 4.14 |

Largest expected-finish MAE: 2020-r01 Austria EARLY (4.67), 2020-r11 Eifel
EARLY (4.39), 2020-r13 Imola EARLY (4.38), 2024-r17 Baku EARLY (4.14),
2022-r01 Bahrain EARLY (4.08).

Largest pit-count mismatch: 2024-r01 (+1.06), 2023-r10 (+0.99),
2024-r17 (+0.86), 2021-r13 (+0.83).

Factual context: the worst winner misses are races decided by a first-time
winner (Piastri) or a comeback drive (Verstappen from P10 in Hungary 2022),
while the simulator ranks by shared constructor pace and free-air time; the
largest MAE cases are early-race checkpoints in the unusual 2020 season.
These are **hypotheses**, not established causes.

## 19. Known limitations (R7-Y)

- No driver-specific pace term (constructor-shared anchor): cannot represent
  first-time winners, driver-form swings, or team orders.
- No traffic/overtaking model: free-air ordering only.
- No reliability/DNF hazard: **and no representation of a stopped car**
  (R7-BUG-2), so non-contemporaneous states are unusable.
- Independent per-lap residuals (documented positive lag-1 correlation); the
  residual representation is ~6–22 % wider than the stored sample std.
- No future SC/VSC/red or weather evolution; dry-only.
- Pit timing is historically plausible behaviour, not strategy; systematic
  over-pitting ≈0.3–0.4 stops/driver.
- Lap-boundary 2-lap pit-loss approximation.

A limitation is claimed to cause an error only where the evidence supports
it (stale-state corruption is directly demonstrated; the winner-miss cases
are labelled hypotheses).

## 20. Temporal adversarial suite (R7-AG) and 2025 firewall (R7-AH)

`test_no_leakage_under_future_poisoning` builds an adapted state at
`2023-r01-R` lap 28, then rebuilds the replay from a copy with all rows
strictly after the anchor poisoned (wet compounds, tyre age 999, pit
markers, red flag, fabricated lap times) and with the final results
permuted/fabricated. The adapted `SimulationState.identity()` is
**byte-identical**, while the evaluation truth changes. Wording: *no
leakage was detected under the implemented adversarial test suite* (not a
proof).

2025 firewall: the protocol's eligible seasons are 2020–2024; the script
rejects 2018/2019/2025 with exit code 2 before touching data; the parameter
contract itself refuses `through_season > 2024`; no Phase-3 holdout or M9
metric is read. Pinned by tests.

## 21. Performance freeze (R7-AB) and memory (R7-AC)

`scripts/benchmark_phase6_monte_carlo.py --pit-dynamics`, actual
through-2024 artifact, chunk 512, seed 20240101, R6 production mechanics,
diagnostics collected (whole-process peaks; see artifact for exact JSON):

| fixture | N | wall | sims/s | valid/invalid | mean pits/driver | peak RSS |
|---|---|---|---|---|---|---|
| early (lap 2, 55 rem.) | 1,000 | 2.42 s | 413 | 1000/0 | 3.061 | 189 MB |
| early | 10,000 | 24.59 s | 407 | 10000/0 | 3.061 | 261 MB |
| early | 50,000 | 126.80 s | 394 | 50000/0 | 3.061 | 430 MB |
| mid (lap 28, 29 rem.) | 1,000 | 1.31 s | 762 | 1000/0 | 3.071 | 430 MB |
| mid | 10,000 | 12.69 s | 788 | 10000/0 | 3.071 | 430 MB |
| mid | 50,000 | 62.99 s | 794 | 50000/0 | 3.070 | 430 MB |
| late (lap 40, 17 rem.) | 1,000 | 0.74 s | 1358 | 1000/0 | 3.122 | 430 MB |
| late | 10,000 | 7.28 s | 1374 | 10000/0 | 3.125 | 430 MB |
| late | 50,000 | 36.15 s | 1383 | 50000/0 | 3.126 | 430 MB |

Every 10 000 case (7.3–24.6 s) is inside the broad 60 s product target.
All trajectories valid; no invalid reason observed. The pit-counter fix
(R7-BUG-1) makes these totals, so mid/late means are ~3.07/3.13 rather than
the previously reported future-only 1.82/1.07.

Memory (separate processes, mid fixture, N=10000): diagnostics enabled
**204.5 MB** vs production (no diagnostics retention) **170.3 MB**; mid 50k
production **170.8 MB**. The 430 MB benchmark figure is the *whole-process,
diagnostics-retaining* peak (early 50k), **not** production memory.

## 22. Validation artifacts (R7-AD)

`data/v2/simulation/validation/` (untracked): `r7_protocol_v1.json`,
`r7_validation.json`, `r7_validation_raw_v1.json` (pre-contract-fix
diagnostic), `r7_benchmark.json`, `r7_memory.json`.

## 23. Defects found and disposition (R7-Z)

**R7-BUG-1 — batch pit diagnostics.**
`_ChunkEvolution.pit_count` started at 0 instead of the factual start pit
count, so `MonteCarloEngine.run` reported *future-only* stops and
`stint_number` reset after a mid-race pit, disagreeing with
`run_scalar`. Fix: seed `pit_count` from `entry.pit_count` (mirroring the
scalar oracle). Both counters are descriptive and never read by scheduling,
so the scientific result identity is unchanged (verified: batch and scalar
`MonteCarloResult.identity()` equal; R5 pinned identities still reproduce).
Affected outputs: R6/R7 pit diagnostics only. Rerun scope: pit diagnostics,
benchmark, validation pit section.

**R7-BUG-2 — non-contemporaneous states accepted by the runtime.**
`from_race_state` + `_validate_start_state` accept a driver whose latest
observation is far older than the anchor T (a factual retirement/stopped
car) because staleness never implies retirement (R2-E). The kernel then
evolves that stale clock as ACTIVE; drivers can complete the remaining laps
"early" and beat the field. Demonstrated on `2020-r07-R` MID: three drivers
were 12–21 laps behind with observation ages 1 000–2 500 s, and the
simulator assigned `giovinazzi` p(win) ≈ 0.90 while the actual winner was
`hamilton`. Across the pre-fix run, 64/99 states contained such drivers and
26/99 assigned the actual winner p < 1e-3; the headline winner log loss
inflated from 1.22 to 4.49.

Disposition: this is a genuine support/contract gap in the frozen runtime,
not a numerical bug and not tuning. No runtime source was changed. R7 added
an evaluation-side contemporaneity criterion
(`is_contemporaneous`: every driver observed within 3 expected lap times)
and excluded the affected candidates with a reported reason. **The runtime
still accepts these states**, which is why the scientific decision is a
blocker: production/live snapshots routinely contain retired cars, and the
engine offers no rejection signal. The required R8 fix is to make
`from_race_state`/`_validate_start_state` reject non-contemporaneous roster
members with a stable unsupported reason (or to model retirement), after
which R7's cleaned numbers (42 states) are the appropriate reference.

## 24. Scientific decision (R7-AA)

Gate-by-gate:

| gate | result |
|---|---|
| no temporal leakage detected | pass (adversarial suite + strict cutoff artifacts + 2025 firewall) |
| probability invariants hold | pass (all 42 states, 0 invalid; sums enforced) |
| determinism holds | pass in the frozen Py3.13 environment; identities are Python-version-sensitive (documented) |
| reasonable runtime | pass (10k ≤ 24.6 s; production memory ≈170 MB) |
| no catastrophic calibration pathology | pass on contemporaneous states (ECE ≈0.02); pre-fix states were pathological |
| nontrivial useful distributions | pass (beats R5/R4/grid on macro LL/Brier and RPS; top-3 0.88) |
| known limitations documented | pass (§19) |
| contract safe for arbitrary product states | **fail** (R7-BUG-2: non-contemporaneous states accepted) |
| coverage | limited: 42 states / 23 races; LATE only 8; calibration subset only 2 |

**Decision: R7 BLOCKED — SIMULATION CONTRACT ISSUE.** The simulator is
scientifically useful and reproducible on contemporaneous dry green states,
but the frozen runtime must reject non-contemporaneous roster members (or
model retirement) before R8 product integration. Secondary, non-blocking
observations: systematic over-pitting, and per-state winner log loss that
does not beat the trivial current-leader baseline.

## 25. Frontend

DEFERRED — UNAFFECTED. No API or frontend source was touched.

---

# ADDENDUM — R7.1 Contemporaneous Active-Roster Safety Contract

Status: **R7.1 COMPLETE — the runtime now refuses non-contemporaneous start
states; the R7 blocker is resolved and R7 is closed.** This addendum is
appended; the original blocked R7 result above (§1–§25) is preserved
unchanged and is NOT rewritten or hidden.

## A.1 The defect (R7-BUG-2, restated)

The R4/R5/R6 kernel advances every adapted roster member from its own factual
`(lap_number, race_time_s)`. A member whose latest observation is far older
than the anchor T (a factual stopped/retired car) therefore advances from a
stale clock and can complete the remaining distance "from the past" and beat
the field. `RaceState`/the R2 adapter legitimately represent stale
observations as `ACTIVE` (stale != retired), but that factual mapping is not
sufficient to initialize an honest future trajectory.

Reproduction (pre-fix, now pinned): `2020-r07-R` MID (leader lap 22,
`scheduled_laps` 44). `giovinazzi` (lap 10, observation age 1 556.3 s ≈ 14.1
expected lap times) and `sainz` (lap 1, 2 544.8 s ≈ 23.1 lap times) were
evolved as ACTIVE; the simulator assigned `giovinazzi` win probability
**0.904** while the actual winner was `hamilton` (**0.000**). The pre-fix raw
artifact recorded `predicted_winner=giovinazzi`, winner LL **13.82** for that
state.

## A.2 Evidence audit (R7.1-B/C)

All **99** raw (`r7_validation_raw_v1.json`) states were reconstructed offline.
Because "has a later observation" and final status are FUTURE truth, they were
used for diagnosis only; the runtime rule uses neither.

| population | n drivers | p50 | p90 | p95 | p99 | max |
|---|---|---|---|---|---|---|
| contemporaneous (`has later row`) | 1 836 | 0.62 | 0.95 | 1.11 | **1.77** | 41.79 |
| non-contemporaneous (no later row) | 144 | 21.36 (median) | — | — | — | 94.82 |

Observation age is expressed as a dimensionless multiple of the circuit|era
expected lap time. **68/99** raw states contained a roster member with no
later observation; **64/99** contained a driver whose age exceeded 3 lap
times (the raw frame's stale-driver states).

Diagnostic false-positive check at the chosen bound: **16** driver-rows had a
later row yet age > 3 lap times. None is a genuine contemporaneous
participant:

- 5 rows are terminal-status cars (`sargeant` 2023-r13 ×3 "Accident";
  `perez` 2023-r16 ×2 "Retired") that nonetheless carry a later row;
- 11 rows are the 2020-r09-R (Mugello) red-flag session-clock discontinuity:
  cars recorded "Finished", one lap down, but with a clock ~14–16 lap times
  behind T. The raw artifact confirms all three 2020-r09-R stages were
  pathological (`predicted_winner=max_verstappen`, actual `hamilton`,
  LL 13.82). Rejecting them is correct, not a false rejection.

False-negative check: 6 states contained a recently-retired driver whose age
was ≤ 3 lap times (`gasly` 2.14, `russell` 2.12, `vettel` 2.19, `alonso` 1.40,
`piastri` 0.36, `gasly` 1.15). Their pre-fix winner LL was 0.10, 0.35, 1.90,
0.40, 0.67 and 4.14; only `2022-r16-R` EARLY (predicted `vettel`, LL 1.90) is
a residual stale-win and it is bounded and non-catastrophic. This is the
documented ambiguity of any past-only staleness rule.

Candidate signals inspected: observation age (discriminating), lap deficit
(NOT discriminating — lapped cars are recent), final status / later rows
(future truth, diagnosis only). No fixed-seconds or retirement-inference rule
was used.

## A.3 The eligibility rule (R7.1-D/F/G)

A dimensionless, race-relative bound derived from the contemporaneous
distribution: a roster member is evolved only if
`observation_age_s <= 3.0 × expected_lap_time`, where the expected lap time is
the selected R3 `pace_base_s` (circuit|era). `3.0` is a conservative margin
(~1.7× the measured contemporaneous p99 of 1.77 lap times) and was already the
predeclared R7 support criterion; it is now the runtime authority. A null
observation age is never an offender (defensive only; the adapter always
supplies an age).

Enforcement layer (narrowest correct seam): the Phase-6 **engine
start-state validation**, before stochastic trajectory execution. `RaceState`
and the R2 adapter are unchanged (stale != retired is preserved; every
observed member stays `ACTIVE`). New runtime surface in
`v2/simulation/engine.py`:

- `REASON_NON_CONTEMPORANEOUS_ROSTER_MEMBER = "non_contemporaneous_roster_member"`
  (added to `ENGINE_UNSUPPORTED_REASONS`);
- `CONTEMPORANEITY_MAX_OBSERVATION_LAP_TIMES = 3.0`;
- `contemporaneous_roster_offenders(state, base_pace_s)`;
- `_validate_start_state(state, selection)` raises the stable reason when any
  roster member is an offender. The whole state is refused: no driver is
  dropped, marked retired, or advanced.

`v2/simulation/validation.py::R7_MAX_OBSERVATION_LAP_TIMES` now aliases the
engine constant; the R7 driver's `support_status()` no longer applies its own
criterion, so the runtime determines every exclusion.

## A.4 Accepted-state parity (R7.1-N) and adversarial result (R7.1-I)

Eligibility-only proof: for accepted states, the runtime reproduces the
pre-fix `MonteCarloResult` identity byte-for-byte. 15 pre-fix raw states across
5 races (`2020-r05`, `2021-r07`, `2022-r01`, `2023-r07`, `2024-r01`; EARLY/
MID/LATE) reproduced their recorded `state_identity` and `r6_result_identity`
exactly. The R7.1 test suite parametrizes 6 of these and also pins early/mid/
late real fixtures. Strictly-future D9 rows (wet compound, tyre age 999, pit
markers, red flag, fabricated lap times) and permuted final results leave both
the accepted state/result identity and the rejected state's reason identical.
Wording: *no leakage was detected under the implemented adversarial test
suite* (not a proof).

## A.5 Original protocol rerun unchanged (R7.1-Q/R)

`scripts/validate_phase6_simulation.py` was rerun with the original
predeclared protocol (2020–2024, per-season 6, broad N=1000, calibration
N=10000, seed 20240101, same radius/selection/baselines). Only
`support_status()` changed: the runtime reason is surfaced instead of the
evaluator applying its own criterion. The pre-fix raw artifact and the manual
42-state clean artifact were preserved
(`r7_validation_raw_v1.json`, `r7_validation_clean_v1.json`).

| run | states | exclusions | non-contemp. exclusions | winner LL | Brier | MAE | RPS | ECE |
|---|---|---|---|---|---|---|---|---|
| raw pre-fix | 99 | 18 | (not applied) | 4.491 | 0.0441 | 2.741 | 0.1101 | — |
| manual clean (R7) | 42 | 75 | 52 | 1.2237 | 0.02669 | 2.4452 | 0.09280 | 0.01899 |
| **post-fix runtime** | **42** | **75** | **52** | **1.2237** | **0.02669** | **2.4452** | **0.09280** | **0.01899** |

The post-fix run is **byte-identical** to the manual clean run: same 42
`(race, stage)` keys, all 42 state and result identities equal, identical
exclusions and identical metrics. Coverage impact: the runtime rejects 57 of
the 99 raw states it cannot simulate honestly (52 non-contemporaneous plus 5
already-unsupported); accepted coverage is unchanged at 42 states / 23 races
(EARLY 23 / MID 11 / LATE 8).

## A.6 Interpretation and decision (R7.1-S)

This is **not** an accuracy improvement. The runtime now refuses inputs it
cannot simulate honestly; the accepted-state metrics are unchanged because the
accepted set and the simulation mechanics are unchanged. The valid-lapped and
lapped-real fixtures remain accepted (lapped != retired, stale != retired); no
retirement was inferred; no final status or future row is read at runtime; no
pace/residual/pit/seed/count/race-set was retuned; reliability remains absent.

Gate-by-gate: unsafe states rejected deterministically — pass; valid
lapped/active preserved — pass; temporal firewall — pass (adversarial suite);
accepted-state metrics non-pathological and byte-identical to the clean run —
pass; eligibility runtime negligible (mean 0.697 µs, p50 0.667 µs, p95
0.75 µs on a 20-driver state). **R7 is closed; ready for R8.**

