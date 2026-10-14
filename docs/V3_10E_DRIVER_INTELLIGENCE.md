# V3.10E — Selected-Driver Intelligence Integration

Compact MODEL / SIMULATION / DIFFERENCE / MC precision in the
selected-driver context, from frozen science only. No telemetry, no
strategy/counterfactuals, no science/API changes, no MC2 work.

- V3.9 freeze: `fb0d8d8772bdc1343bc6be6c5ff9ee68cddd7203` (HEAD matches).
- A/B/C/D semantics unchanged. `WorkspaceState` untouched (consumer-only).
- Git: no commit, no tag, no push.

## 1. Source decision

Single source: the frozen V3.9C uncertainty bundle (`availability` gate +
`compare`), via the existing typed clients. One bundle per anchor serves
every driver — switching drivers slices locally with zero requests.
Consensus-compare would duplicate U1 field data for a second request; the
consensus page stays the expert deep-dive (linked, not embedded).

Anchor = the frame's own exact identity (`anchor_lap_number` +
`anchor_state_time_s`). Availability granularity is lap-level (verified).
Comparability is sparse and frozen (2022-r03-R: exactly lap 2 of 57) —
refusal UI is the honest common case. No snapping to nearby anchors, ever.

## 2. Contract

- `driverIntelligence.ts`: verbatim slice (U1 fields, sampling, bundle
  context); absent driver → null (never substitute); null arms → null.
- `useDriverIntelligence(anchor|null)`: availability → compare; per-anchor
  memo; session/abort guards; loading/ready/not-comparable/unsupported/
  error + retry.
- `DriverPanel`: L0 MODEL/SIM/Δ + `n`/Wilson-bounds line; DETAILS with
  ranks, leader pair + no-verdict note, reused `WilsonViz`, U3, families,
  expert deep links (canonical identity via the B helper). Refusals render
  status + reason + links; errors offer retry. Nothing is blended, ranked
  into a winner, or recommended.

## 3. Causal safety

The bundle is frozen evidence about the anchored historical state; anchor
values are the current frame's own identity (≤ T by construction). No
future anything is requested or rendered. Driver switches re-slice without
requests; scrubbing re-anchors with stale aborts.

## 4. Validation

Unit: 5 slice tests (verbatim, absent→null, null arms, partial arms,
field/U3). Integration: 14 wiring/request/scope tests. Full suite, tsc,
eslint, build, collection — see `validation.json`. Browser at 1600/820/390
on a COMPARABLE state (2022-r03-R lap 2) and a refusal state (2024-r21-R):
compact row, DETAILS content, refusal language, expert links, driver-switch
without refetch.

## 5. Classification

**A. DRIVER_INTELLIGENCE_VALIDATED** (pending browser). Next: V3.10F —
sector/lap + tyre-stint telemetry.
