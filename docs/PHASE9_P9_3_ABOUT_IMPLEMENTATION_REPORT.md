# PHASE 9 P9-3 /ABOUT IMPLEMENTATION REPORT

P9-3 implements the `/about` route as presentation-only consumption of the
frozen P9-1 evidence contract. No scientific code modified, no evidence
regenerated, no retraining, no backend route, no network loading.

## Files changed

Modified:

- `frontend/components/shell/CommandBar.tsx` — added ABOUT to primary
  navigation (`{ href: "/about", label: "About" }`). Narrow-screen
  internal scroll (`overflow-x-auto` + `shrink-0`) already covers the
  sixth item; no shell regression.

New (`frontend/app/about/page.tsx` — thin server composition, no client
JS, no fetch, no spinners; loads `getAboutEvidence()` plus
`getModelsEvidence()` for the shared bounded safeguard statement and
served-season identity, passes typed props down):

- `frontend/features/about/lib/aboutEvidence.ts` — single typed evidence
  entry point: imports `about.v1.json`, validates via
  `validateAboutEvidence`, throws at build on contract drift.
- `frontend/features/about/components/AboutHeader.tsx` — dossier header
  plus 6-cell identity strip (DATA 2018–2025 from Tier-A seasons, SERVED
  REPLAY 2018–2024 from the frozen model spec `final_fit_seasons`,
  FEATURES 84, REPLAY RACES 149, CHECKPOINTS 9,644, PHASES 8 FROZEN)
  plus the contract serving-scope note.
- `SystemOverview.tsx` — 01, seven implemented threads only.
- `SystemSemantics.tsx` — 02, four contract semantics with id, display
  name, definition, probability semantics, not-to-confuse-with lines,
  plus the FACT→PREDICTION / FACT→SIMULATION→STRATEGY relation strip
  with the explicit not-fed-into-Monte-Carlo sentence.
- `ArchitectureMap.tsx` — 03, 8 implemented stages as an ordered text
  flow plus the explicit "Intentionally not part of current
  architecture" not-used block.
- `CapabilityMap.tsx` — 04, 8 capabilities as a matrix with scoped
  headers (Phase/Status/does/does-not/semantics), internally scrolling.
- `DataPlatform.tsx` — 05, Tier-A/B + Phase-2/replay exact counts plus
  the 3-cell 2025 boundary (data 2018–2025 / serving 2018–2024 /
  2025 frozen holdout unserved).
- `TemporalSafety.tsx` — 06, bounded statement verbatim from the models
  contract plus the 7 safeguard items.
- `ReplayIntelligenceFlow.tsx` — 07, 8-step state-to-explanation path
  with probability / local / change kept as three distinct outputs.
- `SimulationStrategy.tsx` — 08, Monte Carlo frequency semantics vs
  paired-CRN strategy comparison, outcome vocabulary
  IMPROVEMENT/DEGRADATION/INCONCLUSIVE/UNAVAILABLE, "Does not:" prefixed
  does-not lines, v1 scope note.
- `Reproducibility.tsx` — 09, P1–P8 freeze timeline, 5 artifact hashes
  (abbreviated), seeds, make targets, manifests, no-one-command note.
- `AboutLimitations.tsx` — 10, all 9 contract limitations as card
  content under "What the system does not claim".
- `AboutProvenance.tsx` — contract v1, Phase-8 tag/commit, corpus hash,
  full hashes + relative source paths in `<details>`.
- `frontend/features/about/components/about-page.test.ts` — 16
  node:test subtests covering the Part S checklist.

## Graphify-first navigation

- `graphify update .` first (10,944 nodes at P9-3 start).
- Targeted queries located CommandBar, ModelSection/format reuse
  targets, and the node:test conventions mirrored from
  `models-page.test.ts`.
- Reused P9-2 primitives instead of a new framework: `ModelSection`
  section shell and `abbrHash` formatting. No new `format.ts` (integer
  counts render via `toLocaleString`, a presentation-only format).

## Page architecture

Server-rendered static route (prerendered at build), 12 section
components, `page.tsx` is composition only. Same brutalist telemetry
system as /models (square panels, 1px rules, tabular data) with a
dossier register: identity strip, S1–S4 semantic panels, staged
architecture flow, capability matrix, boundary panel.

## Evidence consumption

One entry point (`getAboutEvidence`) validates once and shares the
typed object; `getModelsEvidence` supplies only the shared safeguard
statement and served-season identity already validated for /models.
Components receive evidence as props and render fields verbatim. No raw
JSON imports in components, no fetch, no `use client` on the page. No
serving-year inference: the "2018–2024" served cell renders
`model_spec.final_fit_seasons` verbatim.

## System overview

Seven implemented threads, one-paragraph v2 definition, frozen-research
framing ("studies races that already happened; it does not follow a
season in progress"). No dropped-roadmap items.

## Four system semantics

FACT (observed/reconstructed at T) vs PREDICTION (frozen LogReg
INDEPENDENT_BINARY) vs SIMULATION (Monte Carlo
MUTUALLY_EXCLUSIVE_FREQUENCY) vs STRATEGY (paired CRN comparison).
Text-labeled panels (S1–S4 + id + not-to-confuse-with), never color-only.

## Architecture

8 implemented items in contract order as an ordered, screen-reader
legible flow. 9 not-used items under their own heading with the
not-currently-justified rationale. No Postgres/Redis/Kafka/K8s/live-feed
claims.

## Capability map

All 8 capabilities with phase, FROZEN status, does, does-not (scoped
table headers), and semantics. Not a roadmap.

## Data platform

Tier-A 173 / 171+2 / 189,420 / 3,458 / 6,336 / 9,324 / 25,779 /
14,992; Tier-B 76 / 1,149 / 25,784; Phase-2 189,420 × 84; replay 149 /
9,644 / 189,610. Exact contract values, formatted with thousands
separators only.

## 2025 boundary

Dedicated 3-cell panel plus the contract scope note in two places
(header + data section): DATA 2018–2025 vs SERVING 2018–2024 vs 2025
FROZEN HOLDOUT / UNSERVED ("Not served by replay or prediction").

## Temporal safety

"No temporal leakage was detected under the implemented adversarial
test suite." verbatim plus SYNC / NO_FUTURE / NO_FALL_FORWARD /
EXACT_IDENTITY / LABEL_SEPARATION / HOLDOUT_FIREWALL / POST_T_MUTATION.

## Replay Intelligence flow

State at T → ALL_84 materialization → frozen estimator →
independent-binary probability → offline cache → timeline → local
log-odds → checkpoint-to-checkpoint change. Probability / local /
change visually separated; associational, never causal.

## Simulation + Strategy

Simulation: historical initial condition, stochastic trajectories,
mutually exclusive outcomes, frequencies, seed 42. Strategy: single
decision at T, baseline vs intervention, CRN, paired deltas,
uncertainty intervals, four-outcome vocabulary. Comparison only —
"never an endorsed or selected action". V1 scope visible.

## Reproducibility

8 freeze tags on a P1–P8 timeline (no Phase 9), 5 artifact hashes, seed
42, 5 manifests, 6 make targets, contract no-one-command note.
Engineering evidence (FastAPI/Next.js/Parquet/artifact/determinism/
tests/manifests/hashes) is covered by the architecture + reproducibility
sections; no logo wall, no absent infrastructure.

## Intentionally unused architecture

Compact block inside section 03: all 9 contract `not_used` items under
"Intentionally not part of current architecture".

## Limitations

All 9 about-page limitations prominent under "What the system does not
claim", each a card: independent-binary, 2025 unserved, in-sample
permutation, non-causal, no SHAP, checkpoint granularity, deferred
track viz, no explanation cache, synthetic unknown-category. Historical/
frozen nature stated in the section note.

## Provenance

Contract v1 · `v2-replay-intelligence-phase8` · abbreviated commit +
corpus hashes · full hashes and relative source paths in
`<details>`. No absolute machine paths.

## Accessibility

Semantic h1/h2/h3 (verified in snapshot), scoped table headers with
rowheaders, native keyboard-accessible `<details>`, global visible
focus, semantic distinction by text labels (S1–S4, ids,
not-to-confuse-with), architecture as an ordered list, CRN/ALL_84
expanded on first use.

## Responsive validation

Production build (`next start -p 3123`) measured
`documentElement.scrollWidth - clientWidth`: 1440/1024/768/390 →
0/0/0/0. Capability table uses intentional internal scroll; boundary
panel, timeline, and provenance stack at 390.

## Language red-team

Test-scanned sources reject: real-time F1, live race engineer, AI race
engineer, production F1, professional F1 system, optimal/best/
recommended strategy, recommendation, guaranteed improvement, perfect
simulation, leakage free/-free, zero leakage, reason driver won,
production scale, AI-powered, causal verbs. "live F1 feeds" exists only
inside the contract `not_used` array rendered under the absent-heading
(the test asserts page copy contains no other "live" wording). Two
scoped copy fixes during audit: does-not lines now carry a "Does not:"
prefix so contract fragments never read as claims.

## Tests

`about-page.test.ts`: 16/16 green (validated consumption, sections, nav
+ route preservation, four semantics, independent-binary, simulation
distinction, CRN + outcome vocabulary, 8 capabilities + phases, exact
dataset JSON + labeled rendering, 2025 boundary, bounded statement,
architecture split, reproducibility + P1–P8 tags, limitations +
provenance, no recomputation/fetch, red-team). Full frontend suite: 197
passed, 0 failed (49 suites; was 181 before P9-3).

## Frontend quality gate

- `node --test`: 197 pass / 0 fail
- `tsc --noEmit`: clean
- `eslint` (`npm run lint`): clean
- `next build`: green, `/about` prerendered static
- No existing tests weakened; no scientific code modified; P9-1
  evidence untouched.

## Visual audit

Production server reviewed at 1440 (screenshot: hierarchy, strip,
sections, semantic panels conform to the telemetry system) with
snapshot verification of all 12 sections, exact stats, boundary panel,
safeguards, flows, timeline, limitations, and provenance. Zero console
errors on /about (and /models).

## Existing-route smoke

`/` `/replay` `/simulator` `/strategy` `/models` → 200; 0 overflow at
390 on every route with the 6-item nav (internal scroll preserved). The
single console error on `/`, `/replay`, `/simulator`, `/strategy` is
`ERR_CONNECTION_REFUSED` to `127.0.0.1:8000` (backend not running in
this audit) — pre-existing environmental, unrelated to P9-3. Servers
stopped after the audit.

## Graphify final

`graphify update .` — graph at 10,992 nodes after P9-3 UI landing.
Direction: `AboutPage → aboutEvidence → evidence.ts → about.v1.json`
(plus the shared `modelsEvidence` entry for safeguards/seasons);
grep-verified no `/about` dependency on v2 scientific runtime, ml, api,
raw artifacts, parquet/joblib loading, or model execution. No
Phase-1–8 module imports Phase-9 UI.

## Repository safety

No reset/restore/checkout/clean/stash/add/commit/tag. Nothing staged.
Pre-existing worktree modifications untouched. New files only: 1 lib, 12
components, 1 test, 1 route, this report — all uncommitted, awaiting the
P9-5 freeze. P9-1 evidence files unmodified.

## Known limitations

- Mobile primary nav scrolls internally to reach ABOUT (6 items exceed
  390px); P9-4 owns the final nav audit.
- Counts use `toLocaleString` display formatting; exact integers live
  in the validated JSON.
- Strategy outcome vocabulary follows the P9-3 specification against
  the capability contract (comparison, not optimization).
- P9-4 still owns the final full responsive/a11y audit.

## P9-4 entry gate

- [x] /about exists
- [x] ABOUT navigation exists
- [x] validated static evidence only
- [x] no evidence API/network fetch
- [x] FACT/PREDICTION/SIMULATION/STRATEGY distinct
- [x] prediction explicitly INDEPENDENT_BINARY
- [x] simulation semantics distinct
- [x] strategy semantics paired/CRN
- [x] no recommendation/optimality claim
- [x] architecture matches implementation
- [x] absent infrastructure not presented as implemented
- [x] 8 capabilities shown
- [x] Tier-A/B statistics exact
- [x] Phase-2 statistics exact
- [x] replay statistics exact
- [x] 2018–2025 data coverage clear
- [x] 2018–2024 serving clear
- [x] 2025 frozen holdout/unserved clear
- [x] bounded leakage statement exact
- [x] replay-intelligence flow accurate
- [x] simulation flow accurate
- [x] strategy flow accurate
- [x] reproducibility factual
- [x] Phase 1–8 freezes represented
- [x] limitations prominent
- [x] provenance visible
- [x] no scientific logic in React
- [x] accessibility checks green
- [x] responsive at 1440/1024/768/390
- [x] no page overflow
- [x] node tests green
- [x] tsc green
- [x] eslint green
- [x] next build green
- [x] existing routes smoke green
- [x] Graphify direction green
- [x] no scientific code modified
- [x] nothing staged/committed/tagged
