# Phase 7 Handoff — Strategy / What-If

Phase 6 status: **FROZEN** (`v2-monte-carlo-phase6`). Phase 7 is strategy
comparison and what-if intervention. This document states what Phase 7
receives and the architectural facts it must respect. Phase 7 R0 owns all
strategy architecture decisions; nothing here designs or implements strategy.

## Critical distinction

- **Phase 6 simulator** models a *historically plausible stochastic future*
  from a factual state: pit timing, compounds, and pit loss are drawn from
  empirical behaviour. It is not an optimizer and exposes no intervention.
- **Phase 7 strategy** evaluates *intervention / counterfactual candidate
  actions* (pit now, pit next lap, stay out, compound choice) against a common
  factual starting state and compares their expected outcomes.

Do not present a Phase-6 result as a strategy recommendation, and do not
reuse Phase-6 pit draws as an intervention model.

## Available from Phase 6 (frozen, do not mutate casually)

- `SimulationState` (`v2.simulation.state`): immutable, canonically ordered,
  cloneable via `dataclasses.replace`. Carries factual
  `(lap_number, race_time_s)`, position, compound, tyre age, stint, pit count,
  constructor, status, observation age, environment, scheduled laps, and the
  optional replay `anchor_frame_index`.
- `SimulationConfig` (`v2.simulation.config`): execution semantics
  (`simulation_count`, bounded `master_seed`, `sample_orders`,
  `reliability_enabled`, `pit_dynamics_enabled`). Execution identity is a pure
  function of these.
- `Assumptions`: versioned, `USER_ASSUMPTION`-pinned, currently with **no
  speculative controls**. Phase 7 adds typed fields (forced pit laps,
  compound override, injected track-state schedule, weather scenario) and
  bumps `assumptions_version`; an untyped dictionary must never become the
  primary contract.
- `MonteCarloEngine.run(state, parameters, config, assumptions,
  execution_policy=…)`: the same engine Phase 6 uses. Runs are a pure function
  of `(seed, inputs, params, contract version)`; scalar and chunked paths
  produce identical scientific identities.
- `select_pace_parameters` / `select_pit_parameters` /
  `select_residual_sampler`: exact, inspectable parameter selection.
- `ExecutionPolicy`: `RETROSPECTIVE_PRODUCT` (product) vs
  `HISTORICAL_BACKTEST` (leakage-enforced evaluation).
- R7.1 eligibility: non-contemporaneous states are refused with
  `non_contemporaneous_roster_member` **before** stochastic execution. Any
  strategy layer must preserve this refusal rather than silently dropping or
  retiring a driver.
- Product orchestration seams: `api/v2_simulation_service.py` (exact anchor →
  RaceState → adapter → engine → aggregate) and
  `api/v2_simulation_schemas.py`/`api/v2_simulation_routes.py`.

## Phase-7 R0 questions (R0 owns the answers)

- What is a strategy candidate (identity, payload, validation)?
- How is a candidate applied to `SimulationState` without duplicating the
  factual adapter? (clone + typed `Assumptions` mutation is the intended seam.)
- How are candidates compared fairly (same seed/streams, same start state,
  same count; variance control; paired differences)?
- How is counterfactual outcome aggregated and distinguished from the factual
  simulation frequency?
- Which controls are exposed (pit now / next lap / stay out / compound), and
  which remain internal?
- How are unsupported candidates (wet, neutralized, non-contemporaneous)
  refused deterministically?
- How does the frontend distinguish factual Monte Carlo frequencies from
  strategy-conditional outcomes?
- What strategy contract/version and identity participate in reproducibility?

## Constraints carried forward

Exact-anchor semantics, complete roster (no dropping), no retirement
inference, no probability normalization, 2018–2024 serving scope, no 2025
truth, no scientific-model drift, bounded synchronous compute (or an explicit
async design), and preserved frozen Phase-1–6 contracts.

## Explicitly out of scope for this document

No strategy implementation, no what-if interfaces, no optimizer, no
explanation schemas, and no frontend strategy controls.
