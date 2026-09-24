# Phase 7 — Strategy Engine Plan (S0: Audit + Contract Design)

Status: **DESIGN ONLY**. No strategy code, no simulator change, no API change,
no frontend change. This document is the S0 deliverable. It records what the
frozen Phase-6 simulator actually is, where (if anywhere) an intervention can
be attached, and the contract Phase 7 must satisfy.

Phase-6 freeze: commit `b813ffe1`, tag `v2-monte-carlo-phase6`.
Frontend foundation freeze: commit `6c04438`, tag `v2-frontend-foundation`.

> **Headline S0 finding — Phase-6 freeze conflict.**
> The Phase-7 handoff (and Phase-6 plan §25) describes the intended seam as
> "clone `SimulationState`, mutate typed `Assumptions`, run the same engine".
> The frozen engine does **not implement that seam**: `Assumptions` carries no
> controls and is read only for its identity, and the stochastic pit decision
> is hardcoded inside `v2/simulation/monte_carlo.py`. There is no public,
> versioned, intervention hook. Attaching one requires modifying
> `v2/simulation/config.py` and `v2/simulation/monte_carlo.py` (and probably
> `engine.py`) — the exact files pinned by
> `tests/test_v2_phase6_freeze.py::test_scientific_runtime_files_match_frozen_hashes`
> to the Phase-6 freeze manifest. The seal today is intact (verified hashes
> below). Adding the seam changes those hashes and breaks the Phase-6 seal.
> This is a governance decision that S0 cannot make unilaterally.
> See "Freeze conflict and required resolution".

---

## 1. Audit method

- `graphify query` over the simulation package (no code/graph modification).
- Read the frozen simulation modules end to end: `state.py`, `config.py`,
  `rng.py`, `results.py`, `engine.py`, `monte_carlo.py`, `adapter.py`,
  `params.py` constants, `__init__.py`.
- Read the Phase-6 artifacts: `PHASE6_FREEZE_MANIFEST.json`,
  `PHASE6_SIMULATION_API_CONTRACT.json`, `PHASE6_MONTE_CARLO_HANDOFF.md`,
  `PHASE6_MONTE_CARLO_PLAN.md` (§§13, 22–25), `PHASE6_FINAL_REPORT.md`,
  `PHASE6_VALIDATION_REPORT.md`, `PHASE7_STRATEGY_HANDOFF.md`.
- Read the product boundary: `api/v2_simulation_service.py`,
  `api/v2_simulation_routes.py`, `api/v2_simulation_schemas.py`.
- Read the frontend simulator boundary: `frontend/features/simulator/*`,
  `frontend/lib/v2.ts`.
- Read the freeze seal: `tests/test_v2_phase6_freeze.py`.

No file was modified during the audit.

---

## 2. Phase-6 intervention seam audit

### 2.1 What exists

| Concern | Location | Fact |
|---|---|---|
| Immutable start state | `v2/simulation/state.py:355` `SimulationState` | Frozen dataclass, `dataclasses.replace` cloneable, canonical driver order. |
| Execution config | `v2/simulation/config.py:52` `SimulationConfig` | `simulation_count`, `master_seed`, `sample_orders`, `reliability_enabled`, `pit_dynamics_enabled`. |
| Assumptions | `v2/simulation/config.py:126` `Assumptions` | **Only** `assumptions_version` + `provenance`. No controls. |
| RNG | `v2/simulation/rng.py` | Per-`(master_seed, simulation_index)` `PCG64` streams; domains `pit_timing`, `compound`, `pit_loss`, `reliability`. |
| Deterministic kernel | `v2/simulation/engine.py:702` `DeterministicRaceEngine` | Zero-noise lap-step evolution. No RNG, no pits. |
| Stochastic kernel | `v2/simulation/monte_carlo.py` `_ChunkEvolution` (batch), `_evolve_scalar` (scalar) | Event-driven lap stepping; pit decision hardcoded. |
| Pit decision | `monte_carlo.py:1003-1005` and `1267` | `if driver.tyre_age >= driver.target_age: perform pit`. |
| Pit mechanics | `_ScalarPitRuntime` / `_ChunkEvolution._maybe_pit` | Draw order at a pit: **compound → pit_loss → next stint target**. |
| Compound transition | `_dry_transition_distribution` / `transition_for` | Empirical `current -> next` distribution, dry-filtered, renormalized. |
| Stint target | `_select_stint_grid` / `grid_for` | `stint_length_laps` hierarchy `era|circuit|compound → era|compound → compound → global`. |
| Pit loss | `PitParameterSet.pit_loss` | Circuit-conditioned empirical `pit_effective_loss_s`; added to race time. |
| R6-AB race-end suppression | `monte_carlo.py:1003` / `1427` | A pit at the race-end instant is suppressed. |
| Aggregation | `_build_result`, `_check_invariants` | Sums positions over **valid** trajectories; no normalization. |
| Product seam | `api/v2_simulation_service.py:129` | exact anchor → RaceState → `from_race_state` → `MonteCarloEngine.run(..., Assumptions())`. |
| Eligibility refusal | `engine.py:552` `_validate_contemporaneous` | Whole-state refusal before stochastic execution. |

### 2.2 The seam is aspirational, not implemented

- `Assumptions` is **never read for mechanics**. `monte_carlo.py` uses it only
  in `simulation_request_identity(...)` and `assumptions_identity=` (lines
  1504, 1511, 1708, 1782). The only validation is type + `provenance ==
  USER_ASSUMPTION`.
- `v2_simulation_service.run_simulation` always passes `Assumptions()`.
- Phase-6 plan §25 (`docs/PHASE6_MONTE_CARLO_PLAN.md:741-752`) *proposes*
  `Assumptions(forced_pit_laps=..., compound_override=..., track_state_schedule=...)`,
  but no such fields exist. The plan says "remain unimplemented in Phase 6 R0
  and out of v1 scope".
- Therefore the Phase-7 handoff's phrase "clone + typed `Assumptions` mutation
  is the intended seam" describes **unbuilt work**, not an available hook.

### 2.3 Candidate seams, evaluated

| Seam | Reuses frozen kernel? | Per-driver? | Batch/performance? | Verdict |
|---|---|---|---|---|
| Typed `Assumptions` read by engine | Yes | Yes | Yes | **Requires editing `config.py` + `monte_carlo.py`.** Frozen. |
| Custom `pit` object passed to scalar `_evolve_scalar` | Yes (scalar) | Yes | **No** (scalar is far slower; product path is batch) | Fragile private-call coupling; not a versioned contract. |
| Custom `PitParameterSet` subclass for `_ChunkEvolution` | Yes | **No** (`grid_for` has no driver arg) | Yes | Cannot target one driver. |
| Subclass `_ChunkEvolution`, override `_maybe_pit` | Partly (private internals) | Yes | Yes | Depends on frozen private method signature; silent drift risk; strategy layer duplicates `MonteCarloEngine.run` chunking/aggregation. |
| Mutate `SimulationState` only | Yes | n/a | n/a | Cannot express a future forced pit or a suppression. |
| Separate race model in `v2/strategy/` | No | Yes | Yes | **Forbidden** by mission ("reuse the Phase-6 simulator"). |

**Conclusion.** There is no clean, versioned, performant intervention seam in
the frozen Phase-6 simulator. The only defensible seam is an **additive,
default-off, versioned extension** of `v2/simulation/monte_carlo.py` and
possibly `config.py` — which changes frozen file hashes. This is the conflict.

### 2.4 Freeze seal (verified intact today)

From `docs/PHASE6_FREEZE_MANIFEST.json` `scientific_file_hashes`:

```
config.py       8164553ebfc827098699b58af5333bec403417738f8be57c00ac9a077c61f353
engine.py       af47232bd226406c892ca96c2e3eb6266b848c14e32316ce02108b08d672384f
monte_carlo.py  f0a3447f18946cb33548e8711d3184602ffef542dad57df17284451dc25e7d6b
rng.py          f357eea5c5743eee175a657c5bf1f8afdc1c66776036b74a7607b3f3584210b5
state.py        051922bc96a02cbd4d058e6e5e4c7ea229b545bc603f6303dc769f2b4367e6e3
```

All match the live files. `tests/test_v2_phase6_freeze.py` asserts exact
equality per file. Any functional intervention hook moves at least one hash.

---

## 3. Current simulation mechanics relevant to strategy

Event-driven lap stepping (`_evolve_scalar` / `_ChunkEvolution.run`):

1. Each driver schedules its next lap completion at
   `race_time_s + mu + residual`, where
   `mu = base + progress_slope*(next_lap - reference_lap) + degradation_slope*(clamp(age) - clamp(anchor_age))`.
2. The earliest completion(s) advance; ties are processed in canonical
   `driver_id` order.
3. Pace/residual draws come from the per-index `rng_for_simulation` pool, in
   event order.
4. If pit dynamics is enabled and the race has not just ended, and
   `tyre_age >= target_age`, the driver pits: compound transition draw, pit
   loss draw, new stint target draw; age resets to 0; pit count increments.
5. Race completes the instant the leader reaches `scheduled_laps`; a pit at
   that instant is suppressed (R6-AB).

Implications for strategy:

- There is no notion of a "lap currently in progress" action. Every future
  action must be expressed as a **lap-completion event** for a specific driver.
- "Pit now" cannot mean "instantaneously mid-lap"; the earliest honest target
  is the driver's next completed lap.
- Because race order is by `(laps DESC, race_time ASC, driver_id)`, a pit's
  only modelled cost is the sampled `pit_effective_loss_s` added to race time;
  there is **no traffic/overtaking model** and therefore no undercut/overcut
  interaction.

Observed reference cost (`PHASE6_FREEZE_MANIFEST.json` `performance_summary`):
1 000 trials ≈ 0.75 s (late) … 2.31 s (early); 10 000 ≈ 11.3 s (mid), engine
only 7.3–24.6 s. This is the basis of the performance envelope (§21).

---

## 4. Strategy v1 scope

Single-decision horizon. At the anchor T, exactly one intervention is applied
to exactly one target driver; normal frozen stochastic mechanics then run.

Candidate actions:

- `STAY_OUT`
- `PIT_NOW` (optionally with requested compound)
- `PIT_NEXT_LAP` (optionally with requested compound)

Compound choices where factually valid: `SOFT`, `MEDIUM`, `HARD` (dry only).
`SUPERSOFT`/`ULTRASOFT` are legal dry compounds in Phase-6 but wet/other and
the full set are not v1 scope; v1 exposes SOFT/MEDIUM/HARD and a
"compound = baseline-drawn" option (`requested_compound = None`).

Out of scope for v1: multi-stop optimisation, multi-driver interventions,
search/optimisation over a strategy tree, SC/VSC/red strategy, weather
strategy, rejoin-traffic modelling, objective weighting, LLM decisioning.

---

## 5. StrategyIntervention contract

Designed, not implemented. Immutable; carries no factual-state mutation.

```
STRATEGY_CONTRACT_VERSION = "s1"
INTERVENTION_VERSION      = "v1"

@dataclass(frozen=True)
class StrategyIntervention:
    strategy_contract_version: str = STRATEGY_CONTRACT_VERSION
    intervention_version: str = INTERVENTION_VERSION
    target_driver_id: str
    action: StrategyAction              # STAY_OUT | PIT_NOW | PIT_NEXT_LAP
    requested_compound: str | None      # None = use baseline-drawn compound
    decision_lap: int                   # target driver's OWN completed laps at T
    decision_state_identity: str        # SimulationState.identity() at T
    provenance: Provenance = Provenance.USER_ASSUMPTION
```

Validation rules (raise structured `StrategyContractError`/`InvalidAction`):

1. `target_driver_id` must be in `SimulationState.roster_driver_ids`.
2. `action` must be a `StrategyAction`.
3. `STAY_OUT` requires `requested_compound is None`.
4. `PIT_NOW` / `PIT_NEXT_LAP`: `requested_compound` is `None` or in the v1 dry
   set `{SOFT, MEDIUM, HARD}`; wet/unknown => `unsupported_compound`.
5. `decision_lap` must equal the target driver's factual `lap_number` at T.
6. `decision_state_identity` must equal `SimulationState.identity()`.
   A mismatch => `anchor_mismatch` (no stale/nearest behaviour).
7. `provenance` is pinned `USER_ASSUMPTION`; the constructor coerces and
   refuses any other value (same pattern as `Assumptions`).
8. `decision_lap + 2 > scheduled_laps` (no room for the action) =>
   `decision_beyond_race`.
9. The intervention does **not** touch `DriverSimState`, `SimulationConfig`
   factual state, or parameter artifacts.

`identity()` = `canonical_sha256(to_dict())`, reusing
`v2.simulation.state.canonical_sha256`.

---

## 6. STAY_OUT semantics

Narrowest defensible v1 definition:

> At the target driver's **next completed lap** after T, if the baseline
> stochastic pit decision would fire for that driver, suppress that single
> decision. Normal frozen stochastic mechanics resume from the following
> event onward.

- Duration of suppression: **exactly one lap-completion event** for that
  driver. It is **not** "never pit again".
- The driver's `target_age` is **not** modified. Because the baseline target
  stays, the driver will typically pit on the next completion — that is the
  honest consequence and is allowed.
- No RNG draw is consumed by the suppression itself. The `pit_timing`,
  `compound`, `pit_loss` streams are untouched at the suppressed event.
- If the driver already pitted before the suppression event (e.g. baseline
  pit fired on an earlier event than expected), the intervention is a no-op
  and reported as `intervention_superseded_by_baseline_pit`, not silently
  ignored.

Rationale: any longer suppression ("no pit for k laps" or "never") invents a
duration that the frozen engine has no evidence for; v1 refuses to invent it.

---

## 7. PIT_NOW semantics

> At the target driver's **next completed lap** after T (lap
> `decision_lap + 1`), force one pit stop for that driver, then resume normal
> frozen stochastic mechanics.

- Timing: the forced pit is applied in pass 2 of the lap-completion event for
  the target driver, exactly where the baseline pit would be applied.
- Compound: `requested_compound` if provided; otherwise the baseline-drawn
  compound transition outcome. The **compound draw is still consumed** (one
  `compound`-domain uniform) so downstream draw alignment with baseline is
  preserved (CRN).
- Pit loss: sampled from the same circuit-conditioned `pit_effective_loss_s`
  grid, consuming one `pit_loss`-domain uniform, exactly as a baseline pit.
- Tyre age: reset to 0 (out-lap age 1, the frozen convention).
- Next stint target: drawn from `stint_length_laps` for the chosen compound,
  consuming one `pit_timing`-domain uniform (`grid.sample_unit`, floor 1),
  exactly as `_fresh_target`.
- Compound effect: see §9 — the requested compound changes only the stint
  grid / future transition sampling, never pace.
- Double-pitting: the forced pit **replaces** the baseline decision at that
  same event (precedence §10). If the baseline decision would also have fired
  at that event, there is still exactly one pit.
- R6-AB race-end suppression still applies: if the next completed lap is the
  race-end instant, the pit does not happen; the candidate is reported
  `race_already_complete`.

---

## 8. PIT_NEXT_LAP semantics

"Next lap" is resolved from the engine, not from UI wording:

> Target lap = the target driver's **second completed lap** after T
> (`decision_lap + 2`). At the first completed lap (`decision_lap + 1`) the
> baseline stochastic mechanics run normally. At the target lap, if the driver
> has **not** pitted since T, force one pit exactly as PIT_NOW. If the driver
> did pit at `decision_lap + 1` (baseline), the forced pit is **cancelled**
> and reported `intervention_superseded_by_baseline_pit`.

- No double-pitting: a forced pit is applied only if the driver is still on
  the stint it held at T.
- If baseline does not pit at `decision_lap + 1`, the pit is forced at
  `decision_lap + 2` with the same draw order and compound policy as §7.
- Rejected `decision_lap + 2 > scheduled_laps` => `decision_beyond_race`.

This is the only interpretation consistent with the event-driven simulator
(actions are driver-own lap completions, not leader laps or wall-clock steps).

---

## 9. Compound policy

Audited fact: `compound_offset_s` is `deferred` in the R3 estimator
(`estimator.py:92`, plan §R3). There is **no identifiable per-compound pace
delta**. Therefore a requested compound must **not** apply any fabricated pace
change.

What a compound choice legitimately affects in the frozen engine:

1. `PitParameterSet.grid_for(compound)` — the `stint_length_laps` grid used to
   sample the next stint target (hierarchy `era|circuit|compound → era|compound
   → compound → global`).
2. `transition_for(compound)` — future compound-transition sampling from the
   new compound.
3. The recorded `compound` identity in the trajectory / diagnostics.

What it must **not** do: change `mu` (expected lap time), the residual
distribution, degradation, progress slope, or pit loss.

Limitations to state prominently in product copy and output:

- "Compound choice changes only the empirically-conditioned stint length and
  future compound transitions. Phase-6 has no identified per-compound pace
  effect, so no pace benefit is simulated."
- Soft/medium/hard differences may therefore be small or dominated by stint
  sampling noise. That is an honest property, not a bug.

Invalid compound: anything not in `{SOFT, MEDIUM, HARD}` for v1 (including
`None`-equivalent handling) => `unsupported_compound`, structured, never
silently substituted.

---

## 10. Intervention precedence

One deterministic policy, derived from the engine's single pit-decision site:

1. At the target driver's intervention decision event, the **explicit
   intervention wins over the baseline stochastic pit decision** (including a
   baseline decision that would also fire there). One pit, never two.
2. At every other event and every other driver, **baseline stochastic
   mechanics run unchanged**.
3. Compound at a forced pit: **requested compound > sampled transition**. The
   transition draw is still consumed.
4. After a forced pit, **normal mechanics resume**: the next target is
   sampled, and future pits are stochastic as usual.
5. R6-AB race-end suppression **overrides** any forced pit at the race-end
   instant.
6. A forced pit is cancelled if a baseline pit already occurred in the
   intervention window (PIT_NEXT_LAP) — see §8.

No other precedence is admissible; there is exactly one place the baseline
decision can fire, and the intervention only substitutes at its own event.

---

## 11. RNG / CRN audit

Architecture (frozen):

- `rng_for_simulation(master_seed, simulation_index)` → the pace/residual pool
  (`_draw_pool`, `max_residual_draws` uniforms), stream id per simulation.
- `rng_for_domain(master_seed, simulation_index, domain)` for
  `pit_timing`, `compound`, `pit_loss` (and future `reliability`).
- `_ChunkEvolution` pre-draws, per index, the residual pool (size
  `max_draws`), and pit pools (`timing`: `D + max_draws`, `compound`/`loss`:
  `max_draws`).
- Draw order at a pit is fixed: **compound → pit_loss → next stint target**.
  Initial targets consume the first `D` `pit_timing` uniforms in canonical
  driver order.

CRN properties:

- For the same `master_seed` and `simulation_index`, baseline and intervention
  use **identical underlying uniform pools**. This is genuine common random
  numbers.
- Draw **alignment** is event-order dependent. A forced/suppressed pit changes
  the target driver's `race_time_s` and `tyre_age`, which changes subsequent
  event ordering; the pace/residual draws then land on different uniforms.
  Therefore CRN = shared random environment, **not** identical event
  sequences. Do not describe paired runs as identical alternate universes.
- The intervention can change event and draw counts. Pairing does not require
  equal event counts; it requires the same index identity.
- To keep the pit domains maximally aligned across a paired run, a forced pit
  should consume the **same number and order** of domain draws as a baseline
  pit would (compound, loss, target). This is a design requirement of the
  intervention hook, not an existing guarantee. The pace stream cannot be
  kept aligned once timing diverges; that is accepted and documented.

CRN is **feasible** at the stream level, subject to the intervention hook
being implemented with the fixed draw order above. It is not yet proven in
code, because the hook does not exist.

---

## 12. Paired-run design

For a candidate `c`, base and intervention run with:

- identical `SimulationState`,
- identical `SimulationParameterSet`,
- identical `SimulationConfig` **including `master_seed` and
  `simulation_count`**,
- only the intervention differing.

Pair identity for index `i`:

```
PairKey = (state_identity, parameter_identity, master_seed,
           baseline_config_identity, simulation_index, strategy_contract_version,
           intervention_identity(c))
```

`baseline_i` and `intervention_i(c)` therefore share streams and are a valid
paired sample. Per-index paired outcomes needed for §13:

- `win_indicator` (finish_position == 1),
- `podium_indicator` (finish_position <= 3),
- `finish_position`,
- `valid` (a trajectory can fail numerically; see §15).

Requirement: the strategy comparison layer must retain **per-index** target
(and, if used, all-driver) outcomes. `MonteCarloResult` is aggregate-only and
hash- and identity-frozen, so this must live in new `v2/strategy` result
types, not by mutating Phase-6 result contracts.

---

## 13. Comparison outputs

Per candidate, for every driver (target driver reported prominently):

- win probability, podium probability, expected finish,
  finish-position distribution — all `MONTE_CARLO_FREQUENCY` over valid
  trials, never normalized from Phase-3/4/5 output;
- differences versus baseline:
  `Δwin = p_win(c) - p_win(base)`, `Δpodium`, `Δexpected_finish`;
- paired standard error and CI for each difference (§14).

Only quantities the frozen simulator supports are exposed. DNF and points
remain unavailable and **must stay null** (reliability and points regulation
are deferred). No invented metrics.

---

## 14. Uncertainty policy

Defensible and computationally practical v1:

- **Paired Monte Carlo standard error.** For a paired difference
  `d_i = f(outcome_base_i) - f(outcome_c_i)` over indices where both
  trajectories are valid, report `mean(d)` and `SE = std(d, ddof=1) / sqrt(n)`.
  This is valid because indices are independent draws even though the two
  members of a pair are dependent; pairing removes the shared-environment
  variance.
- **Complete-pair analysis.** Pairs where either trajectory is invalid are
  excluded from `d` and counted explicitly (`valid_pairs`,
  `base_only_valid`, `c_only_valid`, `both_invalid`). Aggregate probabilities
  are reported over each arm's own valid set (Phase-6 semantics); paired
  differences are reported over the complete-pair set. Both counts are shown.
- **Paired bootstrap CI.** Percentile bootstrap over pairs (resample indices
  with replacement, B = 2000 by default) for each difference. No analytic
  normal approximation is claimed.
- Cross-check: unpaired MC SE (`sqrt(p(1-p)/n)` per arm) reported alongside so
  the variance reduction from pairing is visible.

Deferred (state explicitly): hierarchical race-level uncertainty, parameter
uncertainty propagation, and calibration of the difference. v1 reports
sampling uncertainty only.

---

## 15. Objective / recommendation policy

v1 = **Option B**: the user selects an explicit objective; the engine ranks
candidates under that objective and also returns the full comparison table.

Supported objectives (no hidden weighted score, no LLM):

- `MAXIMIZE_WIN_PROBABILITY` — rank by target-driver win probability (delta
  vs baseline).
- `MAXIMIZE_PODIUM_PROBABILITY`.
- `MINIMIZE_EXPECTED_FINISH`.

Rules:

- Ranking is over **valid** candidates only.
- If the best candidate's CI overlaps the baseline (or another candidate's CI)
  under the selected objective, the result is labelled **inconclusive**; v1
  does not pick a winner from noise.
- The response always carries `objective`, the ranking, and the untransformed
  per-candidate table, so the user can see disagreements between objectives.
- No universal "best strategy" is defined.

---

## 16. Candidate generation

From the exact anchor at T, generate and factually filter:

```
STAY_OUT
PIT_NOW        × {SOFT, MEDIUM, HARD, None}
PIT_NEXT_LAP   × {SOFT, MEDIUM, HARD, None}
```

(`None` = baseline-drawn compound, isolating pit-timing effect.)

Factual validity determined **at T only**, no future information:

- target driver in the contemporaneous, eligible roster
  (the Phase-6/R7.1 eligibility refusal is inherited, never bypassed);
- race not effectively complete (`leader_laps_done < scheduled_laps` and room
  for `decision_lap + 2`);
- dry, green, all-clear state (Phase-6 supported anchor) and a factual
  `tyre_age`;
- requested compound in the v1 dry set;
- a negative/absent validity reason removes the candidate from the ranked set
  but **keeps it in the response** with its structured reason.

No candidate is generated from future rows, final status, or
`ORACLE_EVALUATION_ONLY` data.

---

## 17. Invalid-action policy

Structured, stable reasons (candidate is reported, never silently dropped):

| Reason | Meaning |
|---|---|
| `target_driver_not_in_roster` | Unknown driver id. |
| `target_driver_not_eligible` | Non-contemporaneous / unobserved / retired-at-T refusal. |
| `race_already_complete` | Leader at/after scheduled distance; no future pit possible. |
| `decision_beyond_race` | No room for `decision_lap + 2`. |
| `unsupported_compound` | Not in `{SOFT, MEDIUM, HARD}` for v1. |
| `wet_conditions` / `wet_compound_state` | Inherited Phase-6 refusal. |
| `neutralized_track_state` / `red_flag_track_state` / `unknown_track_state` | Inherited Phase-6 refusal. |
| `missing_tyre_state` | No factual tyre age. |
| `state_unsupported` | Any inherited `EngineUnsupportedError` reason. |
| `anchor_mismatch` | Intervention anchor ≠ current `SimulationState`. |
| `intervention_superseded_by_baseline_pit` | Outcome note (not a rejection): baseline pit pre-empted the forced window. |

Candidate-level results always include `{action, requested_compound, valid,
reason}`.

---

## 18. Traffic / rejoin limitations

- Phase-6 has **no traffic/overtaking model**. Ordering is free-air by
  `(laps DESC, race_time ASC, driver_id)`.
- A pit's only modelled effect is the sampled time loss. There is no dirty air,
  no rejoin battle, no undercut/overcut, no position swap.
- Therefore strategy output must not claim realistic rejoin battles. Any
  position change caused by a pit is a **free-air rejoin estimate**: pure
  consequence of simulated ordering/time after pit loss.
- Label the field accordingly (e.g. `free_air_rejoin_estimate: true`, plus a
  note) and repeat the Phase-6 known limitation: "No traffic/overtaking model:
  free-air ordering only."
- Candidate comparisons remain valid as *simulator-conditional* comparisons,
  but they systematically under-represent the cost of rejoining into traffic.

---

## 19. Single-decision horizon

v1 restricts strategy to **one** intervention at T, then normal stochastic
simulation. No multi-stop search, no tree optimisation, no nested decisions.
Justification: the value is a defensible, paired, uncertainty-quantified
comparison, not an unvalidated optimiser. Multi-decision is deferred until a
single-decision comparison is validated end to end.

---

## 20. Baseline semantics

Baseline = the **frozen Phase-6 simulator** from the same `SimulationState`,
same parameters, same config (`master_seed`, `simulation_count`,
`pit_dynamics_enabled=True`), `Assumptions()` unchanged, `ExecutionPolicy`
inherited, with ordinary stochastic pit mechanics.

- Baseline is **not** the historical future. The factual result of the actual
  race is never used as a baseline in the product path.
- The historical actual outcome may be shown later only as a retrospective
  illustration, explicitly labelled `ORACLE_EVALUATION_ONLY`, and never fed
  into the simulation or the comparison.
- Baseline result identity is the frozen `MonteCarloResult.identity()`; a
  no-op intervention must reproduce it byte-for-byte (a required S1 test).

---

## 21. Temporal safety

- Strategy inherits `ExecutionPolicy` (`RETROSPECTIVE_PRODUCT` for product,
  `HISTORICAL_BACKTEST` for leakage-enforced evaluation). All Phase-6
  temporal guards (`_validate_temporal`, through-season cutoffs) are
  preserved unchanged.
- Interventions are `USER_ASSUMPTION`; they never alter the parameter artifact
  or its season window.
- No future-season parameters, no 2025 truth, no future rows. The
  contemporaneity refusal (`non_contemporaneous_roster_member`) is inherited
  and must remain whole-state.
- The strategy request identity includes the state identity, parameter
  identity, and baseline config identity, so a leaked future state cannot
  masquerade as the same request.

---

## 22. Counterfactual limitations

- Historical races tell us **what happened**. Simulation estimates **what
  could happen** under alternative future actions from the same factual state.
- The counterfactual outcome is **not observable ground truth**. No historical
  data can validate a specific intervention's realised result, because the
  alternative future did not occur.
- What historical data *can* validate: the **baseline** simulator's
  calibration (already R7) and the *machinery* (determinism, CRN, invariants,
  no leakage). It cannot validate the counterfactual *level*.
- This limitation must be in the contract, the API response
  (`counterfactual_semantics`), and the frontend copy from S1 onward.

---

## 23. Validation design

Designed before implementation. Dimensions and what each can prove:

| Dimension | Test | Can prove |
|---|---|---|
| Contract/unit | Dataclass validation, identity stability | Contract correctness. |
| Intervention invariants | No mutation of `SimulationState`; anchor identity; precedence | Safety. |
| Baseline identity | No-op intervention reproduces Phase-6 `MonteCarloResult.identity()` and per-index outcomes | The extension did not drift baseline. |
| Determinism | Same request → identical strategy identity | Reproducibility. |
| CRN reproducibility | Same `(seed, index)` → identical pools across baseline/candidate | Pairing is well-defined. |
| Candidate validity | Each invalid reason reachable and stable | No silent drops. |
| Pit timing semantics | Forced pit lands on the intended driver-own lap; R6-AB respected; no double pits | Correct action resolution. |
| Compound semantics | Requested compound changes stint grid / transitions only; no change to `mu` | No fabricated pace delta. |
| No future leakage | Poison future D9 rows → byte-identical strategy outputs | Temporal firewall. |
| Counterfactual sanity | `STAY_OUT` with no baseline pit == baseline; identical candidate == baseline | Estimator sanity. |
| Performance | Candidate matrix within the synchronous envelope | Product viability. |
| Historical retrospective | Baseline calibration on accepted R7 states; show actual vs simulated as illustration only | Baseline trust, not counterfactual truth. |

Explicitly **not** validatable: the realised counterfactual strategy outcome.

---

## 24. Performance envelope

Measured Phase-6 batch cost (per 1 000): 0.75 s (late) … 2.31 s (early).
10 000: ≈ 11.3 s (mid) HTTP / 7.3–24.6 s engine-only.

Naive strategy cost = `(1 + K)` full runs for K candidates. With the v1
candidate set (up to 9 candidates: STAY_OUT, 4×PIT_NOW, 4×PIT_NEXT_LAP):

- 1 000 trials, K=8: ≈ 8 × 0.75–2.31 s ≈ **6–18 s** synchronous.
- 10 000 trials, K=8: ≈ **60–150 s** — too long for a synchronous request.

Design decisions:

- Default `simulation_count = 1000`; maximum synchronous `= 10000` only if the
  candidate set is small; expose an explicit cost estimate.
- CRN does not reduce runtime; it reduces **variance**, so fewer trials reach
  the same paired SE. Recommend 1 000 paired over 1 000 unpaired.
- Candidate count is capped (e.g. ≤ 9) and each candidate is one extra run.
- `FULL` vectorized multi-action evaluation (one pass producing all candidate
  outcomes) is a possible later optimisation, but only after correctness — do
  not optimise prematurely.
- Async execution is out of scope for v1; if the envelope is exceeded, the
  request must be reduced, not silently truncated.

---

## 25. Proposed API contract (design only)

```
POST /v2/strategies/compare
```

Request:

```
{
  "race_id": str,
  "anchor_driver_id": str,
  "anchor_lap_number": int,
  "anchor_state_time_s": float,
  "target_driver_id": str,
  "simulation_count": int (default 1000, 1..10000),
  "master_seed": int (default 20240101),
  "objective": "MAXIMIZE_WIN_PROBABILITY" | "MAXIMIZE_PODIUM_PROBABILITY" |
               "MINIMIZE_EXPECTED_FINISH",
  "candidates": [ {"action": "STAY_OUT"|"PIT_NOW"|"PIT_NEXT_LAP",
                   "requested_compound": null|"SOFT"|"MEDIUM"|"HARD"} ]
}
```

Response:

```
{
  "strategy_contract_version": "s1",
  "intervention_version": "v1",
  "comparison_version": "v1",
  "strategy_request_identity": str,
  "race_id", "anchor_*", "target_driver_id",
  "simulation_contract_version", "engine_version", "monte_carlo_version",
  "pit_dynamics_version",
  "probability_semantics": "MONTE_CARLO_FREQUENCY",
  "counterfactual_semantics": { ... §22 note ... },
  "traffic_note": "free-air rejoin estimate; no traffic/overtaking model",
  "compound_note": "compound affects stint/transition only; no pace delta",
  "objective": str,
  "baseline": { <same aggregate block as /v2/simulations/race> },
  "candidates": [
    { "action", "requested_compound", "valid", "reason",
      "aggregate": { ... },
      "differences": {
         "delta_win_probability", "delta_podium_probability",
         "delta_expected_finish",
         "paired_se": {...}, "paired_bootstrap_ci": {...},
         "valid_pairs", "base_only_valid", "c_only_valid", "both_invalid"
      } }
  ],
  "ranking": [ {"action", "objective_value", "inconclusive": bool} ],
  "runtime": { "baseline_s", "candidates_s", "total_s" },
  "provenance": { "state": "FACTUAL_AT_T", "parameters": "HISTORICALLY_ESTIMATED",
                  "interventions": "USER_ASSUMPTION", "outcomes": "STOCHASTIC_DRAW" }
}
```

Aggregate-only, no raw trajectories, no normalization, DNF/points null,
unknown race / unsupported state mapped to the same stable reasons as Phase 6.

---

## 26. Frontend handoff (design only)

Frontend foundation frozen at `6c04438` (`v2-frontend-foundation`). It exposes
only PREDICT / REPLAY / SIMULATOR; the simulator is explicit-run, no auto-run,
with a typed client (`frontend/lib/v2.ts`), a state machine, and result cards.

Strategy fits without redesign:

- New route `/strategy`, reusing the simulator's `simulationMachine` pattern,
  stale-response protection, and result-card components.
- New typed client `postStrategyCompare` in `frontend/lib/v2.ts` plus
  strategy types (additive; no change to existing simulator calls).
- New comparison view: baseline summary, per-candidate table, Δ columns with
  paired CI, objective selector, and the counterfactual/traffic/compound
  disclaimers rendered verbatim from the response.
- The existing simulator surface is untouched. No implementation in S0.

---

## 27. Module design (proposed, not created)

Minimal, no speculative abstraction:

```
v2/strategy/__init__.py          # public exports, versions
v2/strategy/contracts.py         # versions, enums, StrategyIntervention,
                                 #   StrategyAction, validity reasons, result types
v2/strategy/interventions.py     # pure: intervention -> forced/suppressed
                                 #   decision schedule for one driver (no engine)
v2/strategy/candidates.py        # candidate generation + factual validity filter
v2/strategy/runner.py            # composes the (extended) frozen engine; returns
                                 #   per-index outcomes for pairing
v2/strategy/comparison.py        # aggregates, deltas, objective ranking
v2/strategy/uncertainty.py       # paired SE + paired bootstrap CI
api/v2_strategy_service.py       # S7 orchestration
api/v2_strategy_schemas.py       # S7 request/response models
api/v2_strategy_routes.py        # S7 route
```

The only frozen-package change is the additive intervention hook in
`v2/simulation/monte_carlo.py` (and, if the hook is carried on `Assumptions`,
`v2/simulation/config.py`). That change is the freeze-conflict item.

---

## 28. Versioning

- `STRATEGY_CONTRACT_VERSION = "s1"`
- `INTERVENTION_VERSION = "v1"`
- `COMPARISON_VERSION = "v1"`
- `UNCERTAINTY_VERSION = "v1"`

Bump required when any of these changes: action resolution semantics
(§§6–8), draw-consumption order at a forced pit, precedence (§10), candidate
validity rules, comparison definitions, objective definitions, paired/CI
estimator, or the effect of an intervention on simulated behaviour. A pure
docs/UI change does not bump.

The strategy request identity includes all four versions plus the state,
parameter, baseline-config, master-seed, and intervention identities.

---

## 29. Provenance

Outputs distinguish:

- `FACTUAL_AT_T` — anchor, start state, driver state at T.
- `USER_ASSUMPTION` — the intervention (pit/stay/compound choice). **Never**
  labelled historical fact.
- `HISTORICALLY_ESTIMATED` — R3 parameters (pace, stint, transition, pit loss).
- `STOCHASTIC_DRAW` — simulated outcomes.
- `ORACLE_EVALUATION_ONLY` — actual future data, retrospective illustration
  only, never in the product path.

---

## 30. S1–S8 roadmap

Each stage: scope / scientific gate / tests / STOP.

**S1 — Strategy contracts + intervention seam.**
Scope: `contracts.py`; the additive, default-off intervention hook in the
frozen engine; `Assumptions` typed field (if chosen) + version bump;
`interventions.py` decision-schedule resolver.
Gate: freeze-conflict resolution recorded (new Phase-7 manifest +
authorized-drift entry); default-off hook reproduces Phase-6 baseline identity
byte-for-byte.
Tests: contract validation; no-op identity; AST import boundary; no state
mutation.
STOP if the freeze conflict is not formally resolved.

**S2 — Deterministic intervention mechanics.**
Scope: forced pit / suppression / compound override on both scalar and batch
paths with the fixed draw order; R6-AB and no-double-pit rules.
Gate: forced pit lands on the intended driver-own lap; zero-noise intervented
runs are deterministic; draw order asserted.
Tests: pit-timing, compound-semantics, superseded-window, race-end.
STOP if scalar and batch diverge scientifically.

**S3 — Paired Monte Carlo / CRN.**
Scope: `runner.py` per-index paired outcomes; pairing identity.
Gate: baseline_i / intervention_i share pools at the same index; pairing
identity reproducible.
Tests: CRN reproducibility; complete-pair bookkeeping.
STOP if pairing is not well-defined.

**S4 — Candidate generation + comparison.**
Scope: `candidates.py`, `comparison.py`; deltas vs baseline.
Gate: no fabricated metrics; DNF/points null; validity reasons stable.
Tests: candidate matrix, invalid reasons, no-leakage poison tests.
STOP if any output is unsupported by simulation.

**S5 — Uncertainty / objective policy.**
Scope: `uncertainty.py`; paired SE + bootstrap CI; objective ranking.
Gate: paired SE < unpaired SE where CRN helps; inconclusive labelling.
Tests: estimator sanity on synthetic pairs; CI coverage smoke.
STOP if uncertainty is not defensible.

**S6 — Validation + scientific red-team.**
Scope: full Phase-7 validation suite; RED TEAM of the no-fake-claims rules.
Gate: all invariants, leakage, determinism, compound/traffic disclaimers.
Tests: as §23.
STOP on any unlabelled speculative claim.

**S7 — API + frontend integration.**
Scope: service/schemas/routes; frontend `/strategy`.
Gate: additive only; existing simulator/replay/predict untouched; frozen
endpoints still pass.
Tests: route/contract tests; frontend unit + typecheck + lint.
STOP if a frozen endpoint changes.

**S8 — Freeze + docs + benchmarks.**
Scope: Phase-7 manifest, plan/report, benchmarks, freeze seal.
Gate: full suite; risk-based FULL verification.
Tests: freeze seal.
STOP if any prior gate regressed.

Risk-based verification: FAST each stage; MEDIUM every 2–3 stages; FULL at
Phase-7 freeze only. Never weaken leakage, determinism, simulation semantics,
scientific invariants, frozen hashes, or frontend frozen semantics.

---

## 31. Scientific risks

1. **Freeze conflict (blocking).** The seam edits hash-pinned files. Must be
   resolved by an explicit governance decision, not by S0.
2. **Fabricated compound pace.** Mitigation: §9; tests assert `mu` unchanged.
3. **Pretending traffic.** Mitigation: §18; explicit free-air labelling.
4. **Counterfactual overclaim.** Mitigation: §22; semantics in every response.
5. **CRN overclaim.** Mitigation: §11; share streams, not event structure.
6. **Parallel kernel drift.** If the seam is reimplemented rather than added to
   the frozen path, scalar/batch can diverge. Mitigation: single hook, default
   off, baseline-identity test.
7. **Hidden objective weighting.** Mitigation: §15; no weighted score, no LLM.
8. **Uncertainty theatre.** Mitigation: §14; paired SE + bootstrap, complete-pair
   counts, no invented CIs.
9. **Performance blow-up.** Mitigation: §24; caps and explicit envelope.

---

## 32. Freeze conflict and required resolution

The intervention seam and the Phase-6 freeze seal are in direct conflict:

- The seam must live where the pit decision is made
  (`v2/simulation/monte_carlo.py`, and likely `v2/simulation/config.py`).
- `tests/test_v2_phase6_freeze.py::test_scientific_runtime_files_match_frozen_hashes`
  asserts the exact Phase-6 SHA-256 of those files.

Resolution options, all requiring a governance decision above S0:

- **A. Authorized additive extension.** Add a default-off, versioned
  intervention hook; record an `authorized_strategy_extension` entry in a new
  `docs/PHASE7_FREEZE_MANIFEST.json`; update the Phase-6 seal test to accept
  the documented, additive drift (as was done for `api/main.py`), proving the
  baseline path is byte-identical with the hook off. This changes frozen
  hashes and therefore must be explicitly authorized.
- **B. No frozen-file edit (not recommended).** Implement interventions by
  subclassing private internals (`_ChunkEvolution._maybe_pit`,
  `_ScalarPitRuntime`). This avoids the hash change but couples the strategy
  layer to unversioned private code, risks silent kernel drift, and does not
  reuse the production aggregation path. Scientifically weaker.
- **C. Defer Phase 7** until a sanctioned extension mechanism exists.

S0 recommends **A**, gated by an explicit authorization recorded before S1
edits any file. Until then, S1 must not start.

---

## 33. S0 definition of done

- [x] Repository, Phase-6 docs, engine, Monte Carlo runner, pit dynamics,
  parameter artifacts, API/service, and frontend simulator boundaries
  inspected.
- [x] Actual intervention seams determined (none clean; conflict identified).
- [x] All strategy semantics, contracts, precedence, CRN, pairing,
  uncertainty, objective, candidate, invalid-action, traffic, temporal,
  validation, performance, API, frontend, module, versioning, and provenance
  questions answered.
- [x] S1–S8 roadmap with gates/tests/STOP conditions.
- [x] Only `docs/PHASE7_STRATEGY_PLAN.md` created; no code/test/artifact
  change; nothing staged, committed, or tagged.
- [ ] Freeze conflict resolution authorized (required before S1).

Verdict: **PHASE 6 FREEZE CONFLICT**.

---

## Appendix S1 — Governance amendment (authorized, resolution option A)

Status: the freeze conflict above was reviewed and **explicitly resolved by
project authorization** before S1 began. Phase-6 remains historically frozen
at commit `edba916f7c129180fcfe63f643ce58aeebc173e3` (tag
`v2-monte-carlo-phase6`); `docs/PHASE6_FREEZE_MANIFEST.json` is untouched.

S1 was authorized to make the **minimum additive** scientific-runtime change
needed to expose the strategy intervention seam. The implementation resolved
§32 option A with a smaller surface than the S0 estimate:

- The intervention is carried as a keyword-only `intervention=None` argument
  on `MonteCarloEngine.run`/`run_scalar`, **not** on `Assumptions`. Therefore
  `v2/simulation/config.py` did **not** need to change.
- Only `v2/simulation/monte_carlo.py` changed. `intervention=None` follows the
  exact Phase-6 path; a supplied intervention raises the neutral
  `StrategyInterventionNotImplemented` before any draw (S1 does not implement
  mechanics; that is S2).
- The error class lives at the neutral simulation boundary, so
  `v2/simulation` never imports `v2/strategy`: dependency direction stays
  `v2.strategy -> v2.simulation` with no cycle.

Governance artifacts:

- `docs/PHASE7_AUTHORIZED_PHASE6_DRIFT.json` — machine-readable authorized
  drift record (historical vs current SHA-256 for the single changed file).
- `tests/test_v2_phase6_freeze.py` — now distinguishes AUTHORIZED PHASE-7
  DRIFT from UNEXPECTED SCIENTIFIC DRIFT; every other Phase-6 scientific
  runtime file must keep its Phase-6 hash.
- `tests/fixtures/phase7_s1_phase6_baseline.json` + `scripts/capture_phase7_s1_baseline.py`
  — pre-change compatibility corpus, captured before any runtime edit.
- `tests/test_v2_phase7_s1_phase6_compat.py` — exact baseline-through-seam
  reproduction with `intervention=None`.

Verdict: **S1 COMPLETE — READY FOR S2** (see the S1 report).

---

## Appendix S2 — Deterministic intervention mechanics (implemented)

Status: S2 implements the S0 §§6–10 action semantics on the single
already-authorized scientific-runtime file (`v2/simulation/monte_carlo.py`).
Only that file drifts; `docs/PHASE7_AUTHORIZED_PHASE6_DRIFT.json` now records
the S2 hash and every other Phase-6 scientific runtime hash is unchanged.
`intervention=None` remains byte-identical (S1 compatibility fixture passes).

Design decisions that fix S0's open mechanics questions:

- **Action resolution is shared, not duplicated.** One per-driver rule
  (`_InterventionState.note_completion`) drives both `_evolve_scalar` and
  `_ChunkEvolution`, so scalar/batch cannot drift.
- **Driver-own laps.** The decision event is the target driver's own
  `L_T + 1` (STAY_OUT/PIT_NOW) or `L_T + 2` (PIT_NEXT_LAP). `decision_lap`
  must equal the target's factual `lap_number`; lapped drivers use their own
  count, never the leader's.
- **STAY_OUT** suppresses exactly one baseline decision at `L_T + 1`, consumes
  no compound/loss/target draw, does not touch `target_age`, and is consumed.
  Supersession is impossible for STAY_OUT (audited: no earlier legitimate
  baseline pit exists in the window); it is never emitted for STAY_OUT.
- **PIT_NOW** forces one pit at `L_T + 1`, replacing (never adding to) the
  baseline decision. **PIT_NEXT_LAP** leaves `L_T + 1` baseline-normal; if a
  baseline pit occurs there the intervention is `SUPERSEDED`
  (`intervention_superseded_by_baseline_pit`), otherwise it forces at
  `L_T + 2`.
- **Compound.** A requested compound overrides the realised new compound but
  the baseline `compound` draw is **always consumed** (CRN alignment). It
  changes only compound identity, the compound-conditioned next stint grid,
  and future transitions — never pace. A requested `null` uses the sampled
  transition.
- **Pit loss / tyre age / next target** reuse the frozen Phase-6 mechanisms
  exactly (one loss draw, age reset to 0 with out-lap age 1, one
  `stint_length_laps` target draw).
- **R6-AB.** A decision event that is the race-end instant (or never reached
  because the race ended first) yields `RACE_END_CANCELLED`
  (`race_end_suppressed`); a statically impossible decision (no room for
  `L_T + offset`) is rejected with `decision_beyond_race`.
- **Outcome metadata** is exposed per simulation on
  `MonteCarloEngine.last_intervention_outcome` (never inside the frozen
  `MonteCarloResult`), and `v2/strategy/interventions.py` owns the typed
  `InterventionOutcome`, the strategy-layer run identity, and a convenience
  runner.

Deferred (unchanged from S0): candidate generation, comparison, pairing,
uncertainty, objectives, API, frontend, multi-stop/multi-driver, traffic,
reliability, and weather/SC evolution.

Verdict: **S2 COMPLETE — READY FOR S3** (see the S2 report).
