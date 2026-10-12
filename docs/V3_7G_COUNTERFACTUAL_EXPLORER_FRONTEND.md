# V3.7G COUNTERFACTUAL EXPLORER FRONTEND

## Final verdict

V3.7G COMPLETE — COUNTERFACTUAL EXPLORER INTEGRATED — READY FOR V3.7H

## Frozen parent

- HEAD: `1eb462631b9d7a948e35b8a1658e3bb90035c94c`
- Tag: `v3.6-strategy-2.0`

## A/B/C/D/F provenance

- V3.7A `v3.7a-counterfactual-contract-v1` /
  `1735954212ec31286fede041639875610003a09cf817177e22cc908e3fcb0a12`
- V3.7B/B1 `v3.7b-counterfactual-execution-contract-v1` /
  `1865537503136ed3d8603e53741902c320df9387222655b38eef51640294e970`
- V3.7C `v3.7c-counterfactual-engine-v1`
- V3.7D card `v3.7d-evaluation-card-v1` /
  `96debc6392c79019abedc3a51c7c26fb1536e97cabb3fed3136c43ed7c2b19c3`,
  gate `REFINEMENT_NOT_WARRANTED`
- V3.7F runtime `v3.7f-counterfactual-runtime-v1`, API
  `v3.7f-counterfactual-api-v1`, cache `v3.7f-counterfactual-cache-v1`
- C seam `045f392e46b030744f18a76140685ceba7501f80c0b8e265af662e57ca5f5376`
- V3.6 card (authoritative)
  `102079ab81101f442d380c109a32b71a3b6850f0106e021f0fc4b05a64c80aeb`
- All recomputed from repository artifacts at G entry.

## V3.7E skipped

`SKIPPED_BY_V3.7D_GATE`. No V3.7E exists.

## Route decision

**OPTION A — dedicated `/counterfactuals` route.** The frontend is a
route-per-surface Next.js app (`/strategy` owns V3.6 Strategy 2.0 with
its hook/machine/components). A separate `features/counterfactuals/`
surface with its own hook, pure machine, composable components, and a
`Counterfactuals` nav item keeps the frozen V3.6 interface untouched
(all pre-existing frontend tests green), matches the established
architecture, and stays V3.10-composable. Options B/C would have
mingled two distinct capabilities in one surface.

## Product architecture

- `lib/v2.ts` (additive): typed F boundary — availability/compare
  types, `getCounterfactualAvailability`,
  `postCounterfactualCompare`, failure predicates. No count/seed/mode
  exists in the request type.
- `features/counterfactuals/lib/counterfactualMachine.ts`: pure
  presentation logic — metric hierarchy, verbatim formatters (zero
  sign flips), reason copy, failure taxonomy, presets, demo default.
- `features/counterfactuals/hooks/useCounterfactuals.ts`: request
  state, session/stale guards, explicit-run only, demo auto-run once.
- Components (composable sections): `CounterfactualView`,
  `CounterfactualPlanBuilder`, `CounterfactualResults`,
  `CounterfactualPanels` (factual header, methodology, provenance,
  limitations). No global state framework added.
- IA order on page: factual state → replay anchor → plan → run →
  deltas → distribution → lifecycle → interpretation → provenance →
  methodology → limitations.

## Visual system

Brutalist motorsport telemetry preserved: existing tokens
(`ink-*`, `signal` accent, `ok/warn/danger` flags), Montserrat
display / Space Grotesk UI / monospace telemetry, square 1px panels,
no gradients/glass/rounded-SaaS/shadows. Team/compound colors
unused (no established mapping); the single earned accent is signal
red for the alternative series. Bars always pair with values.

## Demo flow

Open `/counterfactuals` → cached lap-30 perez anchor auto-runs →
deltas, distribution, lifecycle visible in seconds. 30–60 s flow
covers: change N, compound, reference-vs-plan, lifecycle/
supersession, distribution, methodology, plus presets for
multi-stop, plan-vs-plan, multi-driver/rival. Verified live in the
browser against the real backend.

## Factual state

Header shows race, lap, target, factual position, remaining laps,
tyre at T, eligible N, shortened state identity. No historical
future anywhere (fixture-tested: no `future`/`winner`/`result`
keys in availability rendering path).

## Comparison modes

Radio control: REFERENCE VS PLAN (BASE = NO-INTERVENTION REFERENCE
with tooltip copy) / PLAN VS PLAN (BASE = plan A, ALT = plan B,
positive favors B, plans never reordered). Both verified in browser.

## Plan builder

Targets (availability-bounded checkboxes), per-stop target / N
(availability-derived select) / compound selects, add-stop to the
structural 8-cap, rival select with target-exclusion guard. Backend
remains authoritative on every conflict.

## PIT_IN_N semantics

Each stop shows `PIT IN N LAPS · Scheduled: Lap T+N` (e.g. N=1 →
Lap 31 at decision lap 30). No V3.6 action naming in controls.

## Compound controls

Exactly SOFT / MEDIUM / HARD / SAMPLED; no INTERMEDIATE/WET. Caveat
preserved in builder and presets copy.

## Multi-stop

Add-stop builder, chronological stops, "one simulated trajectory"
copy. Verified via preset (cached).

## Multi-driver

Multi-target checkboxes where availability permits; joint-ordering
limitation line appears when active. Verified fixture-backed.

## Rival comparison

Factual rival select (targets excluded in UI, backend authoritative);
metric labelled P(AHEAD OF RIVAL). Fixture-backed preset path.

## Outcome hierarchy

Primary strip (WIN/PODIUM/TOP-5/EXPECTED FINISH/POSITION GAIN),
secondary diagnostics (TOP-10/RIVAL/PITS), arm values, pair
accounting. Only returned metrics rendered.

## Finish distribution

Backend REF vs ALT frequencies verbatim as paired bars (P1 first)
plus an sr-only data table. Never reconstructed from quantiles.

## Position gain

B1 verbatim: `+x pos` gain / `−x pos` loss / em-dash null, with
screen-reader orientation text. +3/0/−3 unit-tested.

## Pit count

Descriptive everywhere (secondary delta + arm values); neutral tone
by construction; no penalty/efficiency language (audited).

## Lifecycle

All six B/C statuses with counts, shares, and labelled bars; base
and alternative arms. Never collapsed.

## Supersession

Percentage explanation paragraph when SUPERSEDED > 0
("Supersession is not failure"). Seen live: plan-vs-plan fixture
shows 30.7% SUPERSEDED with copy.

## Complete pairs

`5,000 / 5,000 COMPLETE PAIRS` secondary-visible with exclusion
callout when nonzero.

## MC uncertainty

Every delta carries `MC 95% [low, high]` with the sampling-
variability tooltip. Never labelled confidence.

## Cache-first UX

Availability exposes `7 precomputed comparisons`; demo auto-runs
from cache (~35 ms compare); cached/live source chip on results;
cache presented as equal quality ("same validated 5,000-future
result").

## Cache miss

Designed empty state: "Valid counterfactual — not precomputed in
this demo" + explanation, retry only. Verified in browser (N=3).
No metrics, no bypass button.

## Unsupported states

Explicit reason panel with backend reason code; metrics absent;
visually distinct from miss/invalid/error.

## Error states

422 invalid / 200-unsupported / 404 miss vs unknown-race /
503 server / 500 internal each render distinctly (classifier-tested).

## 2025 boundary

Unknown-race unavailable panel; no fallback, no substitution.

## Methodology

Expandable drawer: simulator-conditional, controlled intervention,
reference, 5,000 futures, CRN, complete pairs, MC uncertainty,
lifecycle. Primary page stays scannable.

## Provenance

Expandable panel: A/B/C/F identities, comparison/state identities,
count, seed, source — shortened display, full values via title.

## Limitations

Dedicated always-visible section with all ten inherited limits
plus the no-recommendation semantics note.

## Responsive design

1600: dense workstation, no overflow. 820: no horizontal breakage,
grids reflow. 390: single column, 2-col metric strip, no clipping,
no microscopic labels. All three verified via screenshots (record
shots removed from the tree afterwards).

## Accessibility

Semantic h1/h2, labelled native controls, radiogroup semantics,
aria-expanded drawers, aria-live status regions, sr-only chart
alternatives and orientation text, visible focus rings, no
color-only meaning, honors reduced motion (no ornamental motion at
all).

## Performance

No new dependencies (no chart lib; inline SVG). No scientific data
bundled — fixtures are test-only JSON. Build compiles in ~2 s;
cache-hit compare ~35 ms local.

## V3.10 compatibility

Composable section components, no new global state, F API behind
the typed `lib/v2.ts` boundary — the explorer can become a panel
module without redesign. V3.10 itself not built.

## Tests

- 34 G tests (`node:test`): client shape, demo determinism, plan
  construction, N derivation, orientation (incl. real-fixture
  recomputation proving no flips), lifecycle/pairs/intervals,
  failure taxonomy, fixture contracts (7 real F responses +
  422), copy audit, responsive primitives.
- Full frontend regression: 253 pre-existing tests green.
- tsc clean, eslint clean, production build passing.
- Backend sentinels (unchanged backend): 48 F runtime/cache +
  19 F API contract tests green.

## H readiness

H can freeze: provenance exact, backend untouched, API-only
frontend, demo works, states explicit, build green, docs complete.
No redesign needed.
