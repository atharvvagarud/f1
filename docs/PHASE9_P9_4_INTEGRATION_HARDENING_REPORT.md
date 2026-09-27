# PHASE 9 P9-4 INTEGRATION HARDENING REPORT

P9-4 audits the completed frontend as one coherent application across
`/`, `/replay`, `/simulator`, `/models`, `/about`. No functionality was
added; zero code changes were required. All findings below were verified
against a production build with the backend running, unless noted.

## Final verdict

P9-4 COMPLETE — READY FOR P9-5

## Files changed

None. P9-4 is a zero-diff hardening stage: every audit passed without a
responsible frontend surface to fix. (`frontend/components/shell/
CommandBar.tsx` remains modified from P9-3's ABOUT nav addition,
uncommitted awaiting the P9-5 freeze.)

## Graphify-first navigation

- `graphify update .` first (11,022 nodes at P9-4 start).
- Targeted queries mapped the shell (`AppShell`, `CommandBar`, root
  layout), replay/simulator machines and hooks, and the P9-2/P9-3
  evidence entry points. P9-2/P9-3 reports served as the navigation
  index; no broad frontend rereading was needed.
- No shared component required modification, so no caller analysis was
  triggered.

## Route/navigation audit

Six primary destinations — Predict `/`, Replay `/replay`, Simulate
`/simulator`, Strategy `/strategy`, Models `/models`, About `/about` —
each with the correct destination, no dead links, no duplicate
destinations. `aria-current="page"` verified live on `/about`,
`/models`, `/strategy`. Shell stable across route changes (single
`AppShell` frame, `<main>` landmark, `lang="en"`). Narrow-screen
behavior: nav scrolls internally (111px overflow at 390, 141px at 360
— internal to the nav element, zero page-level overflow); the ABOUT
link was scrolled into view and confirmed visible/clickable at 360.
The internal-scroll pattern is retained: it creates no usability or
accessibility defect at 360px.

## Cross-page visual audit

All five routes share one shell, max width, spacing, panel/border
vocabulary, typography hierarchy (Montserrat display / Space Grotesk
UI / monospace data, tabular numerals), and status language.
Intentional identities preserved: validation laboratory (/models),
technical dossier (/about), replay workstation, simulation
workstation, prediction form. A 1440 screenshot of /about confirmed
dossier hierarchy, identity strip, and semantic panels conform to the
brutalist telemetry system.

## Semantic consistency

Swept all frontend app/feature/component/lib sources for share/
recommendation/optimality/guarantee/causal/perfection/leakage/
accuracy/scale/AI-engineer/live/real-time contradictions. Every match
dispositioned: negations ("never causal", "not shares", "never a
recommendation"), guard blocklists (`strategyMachine.ts` banned-phrase
list, page red-team tests), and one avoidance-rule code comment.
Replay prediction copy ("independent binary estimates, Σ 80.5% —
valid, not shares"), simulator copy ("not Phase-3 independent binary
winner probabilities", MONTE_CARLO_FREQUENCY status), strategy copy
("paired Monte Carlo estimates with sampling uncertainty"), and root
copy ("independent binary win probability, not a share") are mutually
consistent. No defect.

## 2025 boundary

All user-visible 2025 references checked: /models frames 2025 as
frozen one-shot holdout (never development CV); /about separates DATA
2018–2025 / SERVING 2018–2024 / 2025 frozen holdout unserved;
`RaceSelector` renders the backend registry as-is with a "2018–2024"
served caption; backend `/v2/races` serves exactly 149 races across
seasons 2018–2024 (2025 excluded). No ambiguous wording found.

## Responsive matrix

Production overflow (`scrollWidth − clientWidth`), all cells zero:

| Route | 1440 | 1024 | 768 | 650 | 390 | 360 |
|---|---|---|---|---|---|---|
| `/` | 0 | 0 | 0 | 0 | 0 | 0 |
| `/replay` | 0 | 0 | 0 | 0 | 0 | 0 |
| `/simulator` | 0 | 0 | 0 | 0 | 0 | 0 |
| `/models` | 0 | 0 | 0 | 0 | 0 | 0 |
| `/about` | 0 | 0 | 0 | 0 | 0 | 0 |

30/30 cells zero page-level overflow. Intentional internal scrolling
(nav, capability/comparison tables) confirmed contained. No text
clipping, panel/control collision, sticky-element, or touch-target
defects observed. Touch targets on dynamic pages use h-9 controls.

## /models audit

Header strip, holdout roles, stage visual, fold matrix, development
comparison, calibration table, 8 families, coefficients, permutation,
safeguards, limitations, provenance all render. At 360 all qualifiers
verified present in rendered text: INDEPENDENT_BINARY, one-shot,
Development-only, PRE_2025_FINAL_FIT_IN_SAMPLE, NOT temporally
out-of-sample, Positive/Negative log-odds. Nothing hidden for space.

## /about audit

Identity strip, S1–S4 semantics, architecture flow, capability map,
dataset evidence, 2025 boundary, safeguards, replay-intelligence flow,
simulation/strategy, freeze timeline, not-used block, limitations,
provenance all render. At 360 FACT/PREDICTION/SIMULATION/STRATEGY
remain text-distinct; architecture stacks as an ordered list; all 13
key tokens (semantics, frequencies, outcomes, seasons, holdout)
verified present.

## /replay regression

No replay code modified in Phase 9 (verified via git status). Live
smoke with backend: 149-race registry loads, frame 0 + deep-linked
frame 101 render, prediction panel with INDEPENDENT_BINARY semantics,
captions + rowheaders on tables, transport/slider/radios labeled and
operable. Rapid race A→B→C switch resolves to C (final selection
wins); `useReplay.ts` retains request-id + AbortController guards.
No redesign, no regression.

## /simulator regression

No simulator code modified. Live smoke: eligible anchor (2018-r01-R
frame 100, verified via direct backend sweep) runs 1,000 trials to a
full results render (outcome summary, field frequencies, position
distribution, provenance). Three ineligible anchors correctly rejected
by the backend gate (neutralized safety_car, unobserved roster,
non-contemporaneous field) with an exemplary error state: bounded
heading, exact reason, no layout break, no stack trace, status
"Unsupported". Monte Carlo language stays distinct from prediction.
No regression.

## Root/predict regression

No root code modified. Season/Grand Prix/Mode controls labeled,
prediction executes and loads winner estimates with independent-binary
semantics. No regression from six-item shell/nav work (0 overflow at
all widths).

## Accessibility structure

- One logical h1 per route (verified live on all five).
- Ordered heading hierarchies (/about: 1×h1 → h2 sections → h3
  subsections; /models analogous; workstations h1 → h2).
- Landmarks: `banner` (header), `nav[aria-label="Primary"]`,
  `main`, labeled `region`/`group`/`status`/`alert` live regions on
  dynamic pages (route announcer, run statuses).
- Tables: replay tables carry `<caption>` + rowheaders; models/about
  tables carry scoped `th` (zero unscoped headers across 9 tables)
  inside labeled sections with descriptive notes — accepted as
  sufficient context, no change.
- Form controls programmatically labeled (selects, sliders, radios,
  spinbutton); native buttons/links throughout; disclosures are native
  `<details>` with clear summary names.
- Global `:focus-visible` 2px ring verified live on keyboard focus.

## Keyboard-only audit

Tab order logical (brand → nav → page controls); Enter/Space operate
native links, buttons, radios, and disclosures (verified: feature
`<details>` opens with summary focused); replay slider steps frames
via arrows (100→101, URL syncs, focus retained); no traps observed;
focus never disappears behind overflow containers. Strategy comparison
was additionally driven end-to-end (run → INCONCLUSIVE outcome).

## Non-color communication

Signal tokens (`signal/ok/warn/danger/info`) always accompany text:
coefficient direction has "Positive/Negative log-odds" text;
strategy outcomes are text labels (IMPROVEMENT/DEGRADATION/
INCONCLUSIVE/UNAVAILABLE); run statuses are text ("Ready",
"Unsupported"); holdout/development distinction is textual
("Frozen 2025 holdout" vs "Development-only"). No color-only critical
meaning found.

## Tables

Header association scoped everywhere; rowheaders on running-order and
capability tables; tabular numerals global; internal overflow
contained; no column loss at 360 (intentional inner scroll); no
duplicated screen-reader content; no scientific column removed.

## Disclosures

All native `<details>`/`<summary>`: keyboard-operable, visible focus,
clear names ("STATE — 23 features", "Full hashes…", "Full identities
and relative source paths"), no mobile overflow. All
misunderstanding-preventing caveats (in-sample banners, non-share
notes, unserved-2025 notes, bounded leakage sentence) are visible by
default, never disclosure-gated.

## Motion

Only `transition-colors` on interactive controls, covered by the
global `prefers-reduced-motion` override. No JS animation loops, no
autoplay. Nothing added.

## Error/loading/empty states

Replay/simulator/root loading, empty ("No prediction loaded",
"Awaiting simulation/comparison"), API-unavailable, invalid-anchor,
and eligibility-rejection states all render understandably without
layout breakage or stack traces and without misstating science. The
strategy success path was also verified live. /models and /about have
no loading states (static, correct).

## Stale-response safety

Frozen request-id + AbortController logic intact and unmodified; live
rapid race-switch test resolves to the final selection. Green.

## Console/hydration

Zero console errors/warnings on all five routes with the backend
running (checked at 390/360; static pages also at 1440). No hydration
mismatch, key, 404-asset, or evidence-load failures. (With the backend
intentionally absent, dynamic routes log only connection-refused
resource errors — environmental, counted separately per the stage
brief; the live audit above supersedes it.)

## Static evidence integrity

- `frontend/data/models.v1.json`:
  `9ae9b6bb025bb5d271aca365b6b0d72cafb49b4027f5589d731aeddf0bf03685`
  — matches P9-1 (`9ae9b6bb…f03685`).
- `frontend/data/about.v1.json`:
  `4e73f0325989193ce899d838b5ae5282354066002c1463037dac368f6407d8c4`
  — matches P9-1 (`4e73f032…f6407d8c4`).
- No regeneration performed; no unexpected change — no STOP condition.

## Language red-team

Full-source sweep (beyond /models + /about) for the 14 unsupported-
claim families. All matches dispositioned as negations, guard lists,
test scaffolding, or the explicitly-absent "live F1 feeds" not-used
item. No new scientific language invented; no copy changed.

## Performance sanity

/models and /about are server components with no client JS; browser
network log shows only Next.js RSC flight + static assets — no
evidence fetch, no backend calls, no new dependencies, no build-size
anomaly (all routes prerender static), no hydration issues.

## Defects found and fixed

None. P9-4 records zero code changes. Observations closed without
action (frozen behavior verified, not regressions): replay deep-link
frame applies post-hydration; simulator eligibility 422s are backend
gates with correct error states; models/about tables use section
context instead of captions.

## Test gate

- P9-1 evidence tests: green (included in full suite)
- P9-2 models tests (16): green
- P9-3 about tests (16): green
- Replay/simulator/shell tests: green (unmodified, passing)
- Full frontend node suite: 197 passed, 0 failed (49 suites)
- `tsc --noEmit`: clean
- `eslint`: clean
- `next build`: green, all 7 routes prerendered static
- No test weakened, deleted, or added (none needed).

## Live product matrix

Production frontend (`next start`, rebuilt in-stage) + local backend
(FastAPI on :8000, 149 races 2018–2024). Every route visually
inspected at every viewport (matrix above); backend-backed
interactions risk-based: replay select/transport/slider/prediction/
explanations, simulator run success + 3 rejection paths, strategy run
to INCONCLUSIVE, root prediction run. Servers stopped after the audit.

## Graphify final

`graphify update .` — 11,022 nodes · 27,811 edges · 322 communities.
Models/about static-evidence direction intact
(`AboutPage → aboutEvidence → evidence.ts → about.v1.json`, plus the
shared models entry); no Phase-9 frontend code imported into
scientific runtime; no new cycles; the shared-shell change (CommandBar
ABOUT link) has exactly the expected callers (AppShell → all routes).

## Repository safety

No reset/restore/checkout/clean/stash/add/commit/tag. Nothing staged.
Pre-existing unrelated work untouched. No scientific code modified; no
evidence modified. New file in P9-4: this report only (uncommitted,
awaiting P9-5 freeze).

## Known limitations

- No automated accessibility test tool exists in the project; none was
  added per the stage brief. Structured DOM inspection + manual
  keyboard checks were performed instead — no WCAG certification is
  claimed.
- Backend-backed matrix used one valid anchor per dynamic path
  (risk-based), not exhaustive anchor coverage.
- Models/about tables rely on section-heading context rather than
  `<caption>` (replay tables have captions); accepted, P9-5 may
  revisit.

## P9-5 entry gate

- [x] all 5 routes integrated
- [x] navigation correct
- [x] nav keyboard accessible
- [x] 360px nav usable
- [x] no page-level overflow at all six widths
- [x] cross-page visual system coherent
- [x] prediction/simulation/strategy semantics consistent
- [x] 2025 boundary consistent
- [x] /models qualifiers preserved
- [x] /about semantics preserved
- [x] replay regression green
- [x] simulator regression green
- [x] root regression green
- [x] heading structures valid
- [x] tables accessible
- [x] disclosures accessible
- [x] visible focus
- [x] keyboard-only audit green
- [x] no color-only critical meaning
- [x] errors/empty/loading states acceptable
- [x] stale-response safety green
- [x] console/hydration audit green
- [x] static evidence SHAs unchanged
- [x] language red-team dispositioned
- [x] no fake accessibility certification
- [x] no unexpected client/network evidence path
- [x] all P9 evidence tests green
- [x] replay tests green
- [x] simulator tests green
- [x] full frontend tests green
- [x] tsc green
- [x] eslint green
- [x] next build green
- [x] live product matrix complete
- [x] Graphify direction green
- [x] only minimal frontend defects fixed
- [x] no scientific code changed
- [x] nothing staged/committed/tagged
