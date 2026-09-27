# PHASE 9 P9-2 /MODELS IMPLEMENTATION REPORT

P9-2 implements the production-quality `/models` route as presentation-only
consumption of the frozen P9-1 evidence contract. No retraining, refitting,
recalibration, reevaluation, backend route, or scientific modification.

## Files changed

Modified:

- `frontend/components/shell/CommandBar.tsx` — added MODELS to primary
  navigation; nav scrolls internally on narrow screens (`overflow-x-auto` +
  `shrink-0` links) so the fifth item never causes page-level overflow.

New (`frontend/app/models/page.tsx` — thin server composition, no client
JS, no fetch, no spinners):

- `frontend/features/models/lib/modelsEvidence.ts` — single typed evidence
  entry point: imports `models.v1.json`, validates via
  `validateModelsEvidence`, throws at build on contract drift.
- `frontend/features/models/components/format.ts` — presentation-only
  formatting (`toFixed`, hash abbreviation). No means, rankings, or shares.
- `frontend/features/models/components/ModelSection.tsx` — numbered
  engineering section shell.
- `ModelHeader.tsx` — dense 7-cell telemetry strip (task, winner,
  features 84, transformed 106, calibration RAW, semantics
  INDEPENDENT_BINARY, holdout 2025).
- `ProductionModel.tsx` — 01, exact frozen spec + prominent
  INDEPENDENT_BINARY explanation (independent estimates, not shares,
  not expected to sum to 1).
- `HoldoutPerformance.tsx` — 02, PRIMARY/SECONDARY/TECHNICAL metric rail
  with role, direction, aggregation/population, meaning/limitation per
  metric; holdout stage bars (EARLY/MID/LATE) against a fixed 0–0.10
  scale, captioned descriptive-only.
- `TemporalEvaluation.tsx` — 03, D1/D2/D3 fold matrix + FINAL_FIT +
  isolated 2025 holdout vault + protocol guards.
- `DevelopmentComparison.tsx` — 04, 9 candidates with D1/D2/D3/mean,
  dev-only caption, FROZEN SERVING CHOICE identity tag (no ranking),
  plus the frozen SELECTION PROTOCOL panel (rule, measured evidence,
  engineering context, limitations) rendered verbatim from contract.
- `CalibrationEvidence.tsx` — 05, RAW/PLATT/ISOTONIC development-only
  table, RAW — FROZEN tag, holdout ECE explicitly excluded.
- `FeatureSystem.tsx` — 06, 84→106, 8 families with exact counts and
  composition bars, per-family `<details>` name expansion.
- `GlobalEvidence.tsx` — 07, LOG_ODDS coefficient table with textual
  POSITIVE/NEGATIVE LOG-ODDS direction; warn-framed permutation panel
  headed PRE_2025_FINAL_FIT_IN_SAMPLE with the contract in-sample note,
  min–max deltas, and the correlation-masking limitation.
- `ScientificSafeguards.tsx` — 08, bounded statement verbatim + 7
  safeguards.
- `ModelLimitations.tsx` — 09, all 8 contract limitations as card
  content, not footnotes.
- `EvidenceProvenance.tsx` — freeze tag, abbreviated SHAs, holdout/E3
  source paths, full hashes in copy-friendly monospace `<details>`.
- `frontend/features/models/components/models-page.test.ts` — 16
  node:test subtests covering the Part T checklist.

## Graphify-first navigation

- `graphify update .` first (stable graph, then +49 nodes to 10,916 for
  the new UI after implementation).
- `graphify query` located CommandBar, AppShell/layout, Panel primitives
  (`Panel`, `PanelHeader`, bar-with-value convention), StandingsTable
  dense-table vocabulary, and the `node --test` / Makefile gate setup.
- Final query confirms direction: `ModelsPage → modelsEvidence →
  evidence.ts → models.v1.json`; no `/models` dependency on v2 scientific
  runtime, ml, api, or raw artifacts; no Phase-1–8 module imports Phase-9
  UI (grep-verified zero matches).

## Page architecture

Server-rendered static route (prerendered at build), 11 section
components, `page.tsx` is composition only. Reuses frozen visual system:
radius 0, 1px rules / 2px major separators, no shadows/gradients/glass,
Montserrat display / Space Grotesk UI / monospace tabular data, 28–32px
table rows, intentional internal horizontal table scroll
(`overflow-x-auto` + `min-w-*`).

## Evidence consumption

One entry point (`getModelsEvidence`) validates once and shares the typed
object. Components receive evidence as props and render fields verbatim;
4dp display with full stored precision in `title` attributes. No raw JSON
imports in components, no fetch, no `use client` on the page.

## Production model

Estimator LogisticRegression, task winner, target is_winner, eligibility
eligible_is_winner, C 0.01, l2 default penalty, lbfgs, max_iter 1000,
class_weight null, seed 42, ALL_84/v8, 84→106 train-fitted, RAW,
final-fit 2018–2024, holdout 2025. INDEPENDENT_BINARY prominent with
plain-language non-share semantics.

## Frozen holdout

24 races · 26,692 states, race-macro aggregation, one-shot/frozen/not-CV
framing. PRIMARY race-macro log loss 0.0680; SECONDARY Brier, PR AUC,
Synchronized top-1/top-3; TECHNICAL ROC AUC, ECE, state-pooled twins.
No composite score, no generic accuracy headline; per-merric context
keeps 0.068 log loss incomparable with 0.979 top-3.

## Holdout stage performance

EARLY 0.0775 / MID 0.0698 / LATE 0.0568 with stage definitions, fixed
scale, "information, not learning" caption, explicit not-a-selection-signal
wording.

## Temporal evaluation

D1 2018–2021→2022, D2 2018–2022→2023, D3 2018–2023→2024 with state counts,
FINAL_FIT 2018–2024, HOLDOUT 2025 in a warn-framed lock row, guards listed.
2025 visually and structurally isolated.

## Development comparison

9 candidates from `development_evidence` only (CLASS_PRIOR, M3 LogReg,
M4 HGB/XGB, M5 ET/RF, M6 tuned pair, M7 frozen C=0.01), D1/D2/D3 visible
(inter-fold variance readable, e.g. D2 dip), dev means, protocol column
with per-candidate limitations. No RANK/SCORE/WINNER/BEST columns.
Serving choice tagged as identity.

## Model-selection evidence

Serving choice LogReg C=0.01 RAW; M7 global rule with per-fold split
(D1 0.003, D2 0.01, D3 0.03) stated honestly; three measured claims;
engineering context; M7 uncertainty limitation. No new rationale written.

## Calibration

Development-only RAW/Platt/Isotonic means + per-fold columns, RAW frozen
tag, predeclared-rule verdict. Holdout ECE stays in section 02.

## Feature system

84 canonical / 106 transformed; STATE 23, PACE 12, GAPS 8, FIELD_CONTEXT
12, RATES_MOMENTUM 4, ENVIRONMENT_HISTORY 9, PRE_RACE_PRIORS 13,
INTERACTIONS 3; preprocessing note; names behind per-family disclosures.

## Global model evidence

Coefficients: LOG_ODDS space, intercept −5.57417, top-10 by |coef| with
sign/direction text, conditional-association-only framing, no causal or
strategy-quality language. Permutation: PRE_2025_FINAL_FIT_IN_SAMPLE
banner + contract note (NOT temporally out-of-sample), unit
state_within_race, 5 repeats, seed 42, baseline, min–max ranges,
correlation-masking limitation. Never titled "feature importance".

## Scientific safeguards

"No temporal leakage was detected under the implemented adversarial test
suite." verbatim, plus the 7 contract safeguards. No "no leakage" /
"leakage free" badge.

## Limitations

All 8 P9-1 limitations prominent: independent-binary, one-season holdout,
in-sample permutation, non-causal, log-odds-only, no SHAP, checkpoint
granularity, hyperparameter uncertainty.

## Provenance

Contract v1, `v2-replay-intelligence-phase8`, abbreviated commit/SHAs,
holdout + E3 source paths (relative only), full hashes in `<details>`.

## Accessibility

Semantic h1/h2/h3, scoped table headers, native keyboard-accessible
`<details>`, global visible focus, bars always paired with numeric/text
values (direction as text + aria-labels), no color-only meaning.

## Responsive validation

Production build (`next start`) measured
`documentElement.scrollWidth - clientWidth`: 1440/1024/768/390 → 0/0/0/0.
Tables use intentional internal scroll; temporal diagram, limitations,
provenance readable at 390. Three scoped presentation fixes (no evidence
touched): nav internal scroll; removed redundant `sr-only` duplicates
inside wide tables (values already visible adjacent, per the Panel
bar-with-value convention — these leaked static positions into page
scrollWidth); `break-all` on unbroken provenance paths and the calibration
selection-rule token.

## Language red-team

Test-scanned sources reject: best/most-accurate model, perfect
calibration, leakage free, zero leakage, probability contribution,
production-scale, real-time F1, live model, AI-powered, race win
distribution, feature caused, reason driver won. "WINNER MODEL" used only
as task identity ("winner model / validation lab", "Frozen serving
choice"). No backend/retraining language; page states presentation-only.

## Tests

`models-page.test.ts`: 16/16 green (validated consumption, identity,
independent-binary meaning, frozen one-shot + 24/26692, primary metric
value, no composite/accuracy, 2025 separation, folds, dev-only + D1-D3 +
no ranking columns, calibration dev-only + RAW frozen, 84/106 + 8
families, LOG_ODDS + accessible direction, in-sample + not-OOS + never
"feature importance", exact bounded statement + 7 safeguards, limitations
+ provenance, no sort/fetch/api/model-execution/normalization, red-team).
Full frontend suite: 181 passed, 0 failed (48 suites).

## Frontend quality gate

- `node --test`: 181 pass / 0 fail
- `tsc --noEmit`: clean
- `eslint` (`npm run lint`): clean
- `next build`: green, `/models` prerendered static
- No existing tests weakened; no scientific code modified.

## Visual audit

Production server (`next start -p 3112`, reused across checks, restarted
once after a stale-build EADDRINUSE incident — old process kept serving
BUILD-A; killed by port and re-verified). Viewport snapshots + full-page
capture at 1440 reviewed: hierarchy, density, legibility, table behavior,
metric alignment, temporal diagram, feature composition, coef/perm
distinction, limitations prominence, provenance all conform to the
brutalist telemetry system. Zero console errors on /models. Other routes
(/, /replay, /simulator, /strategy) re-verified at 390 with 0 overflow —
nav change is safe.

## Graphify final

`graphify update .` — graph at 10,916 nodes after P9-2 UI landing.
`/models → Phase-9 static evidence → frontend evidence contract` only.
No Phase-1–8 scientific module imports Phase-9 UI.

## Repository safety

No reset/restore/checkout/clean/stash/add/commit/tag. Nothing staged.
Unrelated pre-existing worktree modifications untouched. Validation
servers stopped after the audit.

## Known limitations

- Mobile primary nav scrolls internally to reach MODELS (5 items exceed
  390px); keyboard-focus auto-scroll applies; P9-4 owns the final nav
  audit.
- 4dp display rounding; full precision via title attributes.
- Permutation/coefficient views show contract top-10 snapshots only.
- P9-4 still owns the final full responsive/a11y audit.

## P9-3 entry gate

- [x] /models route exists
- [x] page consumes validated static evidence
- [x] no backend evidence API exists
- [x] production model identity exact
- [x] independent-binary semantics prominent
- [x] frozen holdout clearly separated
- [x] 24 races / 26,692 states shown
- [x] metric roles preserved
- [x] no composite score
- [x] temporal folds exact
- [x] 2025 isolated from development
- [x] dev candidate table scientifically comparable
- [x] D1/D2/D3 visible
- [x] no ranking semantics
- [x] selection protocol evidence-based
- [x] calibration development-only
- [x] RAW frozen correctly
- [x] 84/106 exact
- [x] 8 feature families exact
- [x] coefficient evidence LOG_ODDS
- [x] permutation evidence visibly in-sample
- [x] permutation not described as temporally OOS
- [x] bounded leakage statement preserved
- [x] limitations prominent
- [x] provenance visible
- [x] no scientific computation in React
- [x] no evidence network fetch
- [x] accessibility checks green
- [x] 1440/1024/768/390 responsive
- [x] node tests green
- [x] tsc green
- [x] eslint green
- [x] next build green
- [x] Graphify dependency direction green
- [x] no scientific code modified
- [x] nothing staged/committed/tagged
