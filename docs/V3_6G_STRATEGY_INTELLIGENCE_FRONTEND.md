# V3.6G STRATEGY INTELLIGENCE FRONTEND

## Final verdict

V3.6G COMPLETE — STRATEGY FRONTEND VALIDATED — READY FOR V3.6H

## Frozen lineage

A `2d29c19b…0ae59b`, B `df821fe1…443e3644`, C `v3.6c-engine-v1`,
D protocol `0c2bf7fb…64088fc` (`REFINEMENT_NOT_WARRANTED`), F `V3.6F
COMPLETE — READY FOR V3.6G`, E skipped. Backend verified untouched by
G (only F's files predate G; no `raceintel/`, Phase-7 or F-cache change).

## Existing page audit

Phase-7 `/strategy` (S7): header → setup (race scrubber, target,
objective radios, count radios, seed, 9-candidate checkboxes) → run →
baseline reference → single-objective leader → candidate table →
candidate detail. Terminology: baseline, candidate, paired trials, 95%
MC interval, point-estimate leader — compliant. Retained: formatters,
9-action catalogue, RaceSelector, Panel vocabulary, replay
timeline/roster plumbing, Phase-7 API client. Obsolete: objective/count
controls (v3 fixes count at 5000, leaders need no objective), baseline
panel, single-objective table. Responsive weaknesses: wide candidate
table with no mobile transformation. Accessibility weaknesses: nested
landmarks risk, no mobile alternative to the table. Weak UI was not
preserved; application consistency was.

## Product goals

30–60 seconds to answer: what state, what driver, what reference, what
alternatives, what changes (6 outcomes), how uncertain, did it execute,
are objectives in tension, what is NOT claimed. Brutalist motorsport
telemetry: existing tokens, radius 0, hard rules, tabular numerics, one
earned accent, no shadows/gradients/glass, no new dependency, no chart
library.

## Information architecture

CONTEXT (race-state strip) → REFERENCE → ALTERNATIVES (setup) →
OUTCOME TRADE-OFFS (matrix) → UNCERTAINTY/EXECUTION → DISTRIBUTION →
METHODOLOGY/LIMITATIONS. First viewport: state, driver, alternatives,
what changes. Methodology never buries the comparison.

## API integration

Append-only typed client in `lib/v2.ts`: `postStrategyV3Compare`
(explicit `mode`, never sends a count) and
`getStrategyV3Availability`, plus `isStrategyV3RequestInvalid` /
`isStrategyV3CacheMiss` predicates. F schemas are the authority; no
backend enums duplicated; values pass through verbatim.

## Cache-first behavior

Normal path sends `mode="cached"` only. Live exists solely behind
`NEXT_PUBLIC_STRATEGY2_ALLOW_LIVE=1` as an explicitly labelled
developer button, never default. Cache miss never falls back (no live,
no Phase 7, no zeros). No job system built.

## Context

Race, season/round/event, lap + state time, analysed + anchor driver,
position, tyre + age (roster-sourced, guarded), alternative count,
result source. Only fields present through existing causal state. Header
chips: STRATEGY 2.0 · 5,000 PAIRED FUTURES (never "predictions").

## Reference

Persistent "SIMULATED NO-INTERVENTION REFERENCE" panel with
plain-language copy ("evolves the race … without forcing a strategy
action") and a warn-rule: NO INTERVENTION ≠ STAY OUT (stay out is a
modelled alternative). Never labelled current/team/historical strategy.

## Alternatives

Frozen 9-action grid (STAY OUT, PIT NOW ×4, PIT NEXT LAP ×4, incl.
SAMPLED variants), default all 9, no free-form controls. API identity
is authority; invalid actions cannot be constructed.

## Comparison matrix

Outcome rows (WIN/PODIUM/TOP 5/TOP 10/EXPECTED FINISH/DOWNSIDE) ×
REFERENCE + per-alternative columns: alternative value, simulated
difference, [95% MC interval]. Desktop table with sticky outcome +
reference columns; mobile transforms to alternative-switcher → outcome
rows (verified no page overflow at 390).

## Trade-off semantics

Backend orientation preserved verbatim: positive = improvement,
Δ expected finish = reference − alternative (rendered `+0.7 pos` /
`+5.5 pp`). No value transformed; sign + unit carry meaning without
colour.

## MC intervals

Every supported delta shows `[low to high]` under its point estimate
with a global 95% MC INTERVAL legend: sampling uncertainty from paired
simulations — not real-world certainty, not P(better). Withheld
intervals render "interval withheld · n pairs", never hidden, never an
error look.

## Downside

DOWNSIDE row shows the backend downside share + interval with copy:
share of paired futures finishing worse than reference; not P(wrong).
No derived scores.

## Objective leaders

Five backend leader slots rendered as facts with LEADS ON chips per
alternative plus explicit denial: point-estimate maxima, not
recommendations, objectives can disagree, no single preferred
alternative. No BEST/RECOMMENDED/WINNER/OPTIMAL anywhere (tested).

## Position distribution

Compact SVG bars (P1→Pn, REF grey vs ALT accent) plus a visible
frequency table (accessible equivalent, backend values only). One
focused alternative at a time (detail selector); table compares several.
No V3.5 marginals, no smoothing, no 3D.

## Execution diagnostics

Per-detail-alternative: requested/complete/excluded pairs, executed,
inert, superseded, not-executed, race-end-cancelled, baseline-pit
suppressed — backend fields only — with INERT/SUPERSEDED plain copy
(neither means bad). Pair-count bars with exact `4,982 / 5,000` labels;
exclusions never hidden.

## Provenance

Compact strip (SOURCE/ENGINE/SIMULATOR/FUTURES) + expandable METHOD /
PROVENANCE (versions, identities truncated w/ full titles, seed, cache
key). No RNG internals.

## Unsupported states

STATE/ACTION/COMPARISON preserved: unsupported panel with human copy +
machine code; cache miss is its own NOT PRECOMPUTED panel (no
simulation, no fallback, retry offered). 2025 → explicit 2018–2024-only
unavailable. Server failures (503/500) render distinctly from scientific
unsupported. No stack traces.

## Error states

INVALID_REQUEST / UNSUPPORTED_STATE / INVALID_ACTION / CACHE_MISS /
CACHE_INVALID / SIMULATION_FAILURE / INTERNAL_ERROR each map to distinct
copy via `classifyStrategy2Failure` (tested); unsupported never looks
like a crash.

## Methodology

Concise HOW-TO-READ + SCOPE panels (factual T, no forced reference,
action-only alternatives, paired structure, 5000 futures,
simulator-conditional, unknowable counterfactual truth, dry-only, no
pace/DNF/points/weather, single-driver/decision, 2025 unsupported) with
an About link. Present in results and idle states, below the comparison.

## Limitations

Catalogue reflects the 2-state validation cache; desktop 9-alt matrix
scrolls with sticky labels; live is dev-gated; no URL deep-linking (not
pre-existing); distribution focuses one alternative.

## Responsive behavior

1600/1440: workstation matrix, first viewport answers state/driver/
alternatives/changes. 820: panels stack cleanly, table scrolls with
frozen labels. 390: transformed alternative→outcome rows, compact
switcher, legible distribution, zero page overflow (measured
scrollW == clientW).

## Accessibility

AppShell `<main>` landmark (nested-main fixed during validation); h1 +
h2 hierarchy; native buttons/inputs/selects/details; table captions +
th scope; chart text equivalent + aria-label; status never colour-only;
aria-live run status; role=alert errors; visible 2px focus (verified via
keyboard Tab to Run); global reduced-motion CSS; reason codes retained
as text.

## Performance

No new dependencies; SVG/divs only; availability + races load in
parallel; cached compare resolves in ~ms-to-1s; no fake progress (cached
shows "Loading…", live shows truthful "RUNNING 5,000 PAIRED FUTURES").

## Visual validation

Live backend (current code, port 8001) + Next dev: catalogue load, run,
matrix, distribution, diagnostics, provenance, methodology, unsupported,
cache-miss, focus, keyboard, 1600/820/390 screenshots archived under
gitignored `runtime_artifacts/v36g_visual/`. Zero console errors in
final passes (one CORS dev-origin fix during setup; one stale-overlay
error retired).

## Tests

`node --test`: 253/253 pass, incl. 21 new Strategy 2.0 tests (vector,
leaders, copy semantics, failure taxonomy, catalogue, client-cached
default, copy guard). Phase-7 copy guard extended to current surfaces
(deleted-view references replaced). `tsc`, `eslint` (0 errors),
`next build` all pass. F backend regression focused-green; Phase-7
backend untouched.

## V3.6H readiness

Presentation complete and validated; backend frozen; artifacts
(`results/v3/v3_6g/`) + visuals recorded. H owns final validation and
freeze.
