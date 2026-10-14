# V3.10G — Contextual Strategy + Counterfactual Integration

Turns the selected driver + exact replay state into intentional strategy
and counterfactual exploration entry points. Context first, exploration
second, no recommendation.

## What the user can ask

- WHAT HAPPENS UNDER THE FROZEN STRATEGY ALTERNATIVES? → EXPLORE STRATEGY
- WHAT HAPPENS IF I APPLY A SUPPORTED CONTROLLED INTERVENTION? → EXPLORE ALTERNATIVE

The default workspace is unchanged apart from two compact entry blocks in
the notes column. There is no strategy dashboard, no recommendation engine,
no optimization interface, no alternate-history simulator.

## Source contracts (frozen, consumed verbatim)

- Strategy (V3.6F): `GET /v2/strategies/v3/availability[?race_id=]`
  catalogue (2 cached entries) + `POST /v2/strategies/compare-v3`
  (`mode: "cached"`, full 9-action set, production seed). Reference
  `SIMULATED_NO_INTERVENTION_REFERENCE`; probability deltas ALT − REF;
  expected-finish delta REF − ALT; paired MC sampling uncertainty only.
- Counterfactual (V3.7F): `GET /v2/counterfactuals/availability` (cheap,
  per exact anchor) + `POST /v2/counterfactuals/compare`
  (`REFERENCE_VS_PLAN`, single `PIT_IN_N_LAPS`). Probability deltas
  ALT − BASE; expected finish BASE − ALT; position gain ALT − BASE.
  Full audit: `results/v3/v3_10g/integration_source_audit.json`.

## Exact state adapter

`features/pit-wall/lib/decisionAdapter.ts`: canonical frame anchor passes
through verbatim to the frozen `(race_id, anchor_driver_id,
anchor_lap_number, anchor_state_time_s)` identity; target is the selected
driver verbatim. No snapping, no substitution, no nearby-state probing.
2018–2024 season firewall (2025 refused locally, zero requests). Strategy
availability matches catalogue entries on race + full anchor + target;
counterfactual N/compound domains are read verbatim from availability and
validated fail-closed (invalid N/compound rejected, never clamped).

## Interaction model

- Availability before execution: at most one catalogue load per race
  (shared module cache) plus one cheap availability GET per exact anchor.
- Explicit intent only: EXPLORE STRATEGY runs one cached compare;
  EXPLORE ALTERNATIVE opens an intervention form (eligible N +
  supported compounds only) behind which RUN COMPARISON executes.
  Driver switch, frame scrub, telemetry/intelligence toggles issue zero
  compare requests (live network audit in `request_audit.json`).
- Stale safety: session + request-id + abort-on-workspace-move +
  response-identity check + render-phase identity keying.
- Unsupported (unprecomputed anchor, ineligible driver, 2025) renders a
  concise refusal with the frozen reason — never zeros, never advice.
- Results are compact and descriptive: canonical alternative order, frozen
  formatters, reference framing ("compared with the simulated
  no-intervention reference"), sampling-uncertainty framing, and
  simulator-conditional qualification. Objective leaders are deliberately
  withheld contextually (they would read as a ranking).
- Expert pages preserved: `/strategy` and `/counterfactuals` hydrate
  race + exact frame + driver/targets from the canonical deep link
  (`useExpertWorkspaceHydration`, fail-closed) and stay the full
  scientific surfaces. Round-trip verified live with zero drift.

## Validation

- Frontend 573/573 (548 + 25 new), typecheck/lint/build clean.
- Python collection 5186 (unchanged); guard-subset failures are
  pre-existing A–F tree-state failures (verified by stash control),
  not G regressions.
- Live: supported (583/perez) and unsupported (frame 0, scrubbed 562)
  states, 2025 exclusion, driver switch, scrub, explicit runs with exact
  delta parity, round-trips, 1600/820/390 screenshots with no overflow.
- Pathology V3.10G-P1…P20 all zero.

Next gate: V3.10H (responsive/accessibility/product polish). Not implemented here.
