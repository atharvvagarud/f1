# F1 Intelligence — Frontend Redesign Plan

Status: **PLAN ONLY — NOT EXECUTED.** No frontend code was modified to produce
this document. Baseline: Phase-6 frozen at `b813ffe1` (`v2-monte-carlo-phase6`).

Direction: **BRUTALIST MOTORSPORT TELEMETRY**
(system spec: `docs/FRONTEND_DESIGN_SYSTEM.md`).

> Phase 7 (Strategy) must not begin during any UI stage below. This plan changes
> presentation only; it must not alter prediction, replay or simulation
> semantics.

---

## 0. Scope guardrails

- **Contract-frozen behaviour stays byte-identical:** request flow, checkpoint
  gating, staleness handling, Monte Carlo semantics, independent-binary
  probability semantics, replay facts.
- No backend, ML, `v2/`, or `data/` changes.
- No new runtime dependency unless a stage records an explicit justification
  and STOP gate (default answer: no).
- Each stage is bounded, independently reviewable, and stops for approval.
- Run the Impeccable workflow and detector for every stage that edits UI.

---

## 1. Current frontend audit (source-level)

### Routes
| Route | File | Surface | Generation |
|---|---|---|---|
| `/` | `frontend/app/page.tsx` | Winner prediction (select, ensemble/single, tabs) | V1/legacy prediction stack |
| `/replay` | `frontend/app/replay/page.tsx` → `ReplayView` | Historical race replay | V2/Phase-5 |
| `/simulator` | `frontend/app/simulator/page.tsx` → `SimulatorView` | Monte Carlo simulator | V2/Phase-6 |

`MODELS` and `ABOUT` surfaces are **not implemented** yet. There is no shared
global navigation; each page renders its own header and cross-links.

### Architecture
- Next.js 16.1.6 App Router, React 19.2.3, Tailwind v4 (CSS-first, no
  `tailwind.config`), `motion` 12, `lucide-react`.
- Feature folders: `features/{prediction,replay,simulator}` each with
  `components/ + hooks/ + lib/`.
- State machines/services are cleanly separated: `replayMachine.ts`,
  `simulatorMachine.ts`, `probabilityTimeline.ts` — pure logic, tested.
- API clients: `lib/api.ts` (legacy V1 routes) and `lib/v2.ts` (V2 replay +
  simulation). Both declare their own `API_BASE`. This is a **duplicated
  transport pattern**, not duplicated business logic.
- Tests: dependency-free `node --test` with Node 22 type-stripping;
  `tsc --noEmit` for typecheck; `eslint` via `npm run lint`.
- No page-level business logic in `page.tsx` (delegates to hooks) — good.

### Visual system as implemented
- Fonts: Montserrat (`font-heading`) + Space Grotesk (`font-body`) via
  `next/font`; tables use the default Tailwind `font-mono`.
- No design tokens: `globals.css` only imports Tailwind and sets two font
  variables. Everything else is inline utility classes.
- Palette: `bg-slate-950` shell, `bg-slate-900/800` panels, `white/5–10`
  borders, `red-500/600` brand accents, plus emerald/amber/sky/violet/cyan/
  orange/yellow in confidence tones and status.
- Geometry: large radii — `rounded-[30px]` ×10, `rounded-[26px]` ×3,
  `rounded-[24px]` ×6, `rounded-[22px]` ×3, `rounded-[18px]` ×1, plus many
  `rounded-2xl`/`rounded-full`.
- Decoration: `bg-gradient-to-br` panel fills, `shadow-2xl`/`shadow-xl`,
  gradient confidence bars, one `backdrop-blur-xl`, hover `scale`/`y` lifts.
- The V2 replay/simulator surfaces are already denser and flatter than the
  prediction page (mono tables, `border-white/10`, thin bars). They are the
  best existing expression of the target direction.

### Data semantics observed (must be preserved)
`StandingsTable` (null→`—`, stale labels), `PredictionPanel` (independent
binary, "Σ … valid, not shares"), `ProbabilityTimelineChart` (paths break at
null, checkpoint-only), `SimulationResults` (frequencies, `winMass`, DNF/Pts
`—`), `ContextBar` (flag text+colour). These are correct and are **KEEP**
logic; only their styling changes.

---

## 2. Impeccable design critique (highest-impact problems)

Ranked, system-level, with concrete fixes. Mode for these surfaces is
**Operate** (task completion), not Persuade.

1. **Incoherent visual identity across the three routes.** `/` is soft
   fintech (30px radii, gradients, pills, glass); `/replay` and `/simulator`
   are flat and dense. Three routes read as three products.
   *Fix:* one shell + one token set; every surface uses the same border,
   radius (0), and typography roles.
2. **Radii and shadows fight the data.** 30px cards, pill tabs and hover lifts
   make engineering data look like marketing cards.
   *Fix:* radius 0 (2px chips only), remove shadows and hover scale; use 1px
   borders and background steps.
3. **Colour is decorative, not informative.** Rainbow confidence gradients and
   violet/cyan icon chips carry no meaning, while driver/team colour (real
   data) is absent.
   *Fix:* neutral shell; reserve colour for status, flags and selected state;
   introduce meaningful team/driver accents as data.
4. **Duplicated, inconsistent chrome.** Each page re-implements header,
   cross-links, error banners and panel wrappers with slightly different
   classes.
   *Fix:* `AppShell` + `CommandBar` + shared `Panel`, `StatusBanner`,
   `StatCell` primitives.
5. **Typography roles are unassigned.** Display, UI and data partly overlap;
   many numeric values are in proportional type (e.g. `OverviewCard` values),
   so columns jitter.
   *Fix:* enforce DISPLAY / UI / DATA roles; tabular monospace for all numbers.
6. **Focus and tab semantics are incomplete.** Prediction tabs and several
   controls have no visible focus style; tabs are a `div` of buttons without
   `role="tablist"`/`aria-selected`.
   *Fix:* global focus ring; real tab semantics.
7. **Chart series rely on colour.** `ProbabilityChart` uses a near-monochrome
   palette and thin lines; `ProbabilityTimelineChart` distinguishes ~20 series
   by hue.
   *Fix:* dash/label/point encoding plus colour; keep the toggle legend.
8. **Hierarchy is flat within result panels.** `EnsembleResults`/
   `SingleResults` render large intro copy and four equal "hero" stats before
   the actual race data.
   *Fix:* lead with the decision line (winner · probability · checkpoint) and
   make supporting stats a dense aligned strip.
9. **Muted text is borderline.** `slate-500` on `slate-950` at 11px is under
   AA for small text.
   *Fix:* use the `fg-muted` token and/or raise size/weight for metadata.
10. **Motion is decorative in places.** Hover `scale`/`y` on data panels and
    gradient sweep on the confidence bar add movement without meaning.
    *Fix:* restrict motion to state/selection/playback transitions.

Rendered review remains **pending** — the app is not running (ports 3000/8000
closed), so this critique is source-level. First UI stage must capture desktop
+ mobile screenshots before/after.

---

## 3. Design tokens (proposed)

Implement in `frontend/app/globals.css` using Tailwind v4 `@theme` (no new
config file, no new dependency). Keep names short; do not create dozens.

```
--color-ink-950 / 900 / 850        shell background / surface / raised
--color-line / --color-line-strong subtle 1px border / structural 2px border
--color-fg / fg-muted / fg-dim      text hierarchy
--color-signal                      F1 red (selected/active only)
--color-ok / warn / danger / info   status semantics
--color-focus                       focus ring

--font-display  Montserrat 700-800, tight tracking
--font-ui       Space Grotesk 400-600
--font-data     ui-monospace, SFMono-Regular, Menlo, Consolas, monospace

--radius        0        (structural corners)
--radius-chip   2px      (badges/toggles only)
```

Spacing uses the existing 4px Tailwind scale. `--font-data` is the OS
monospace stack (no dependency). Optional condensed display face is a UI0
decision with its own STOP gate.

No gradients, no shadow tokens. Density is expressed through spacing rules,
not extra tokens.

---

## 4. Component inventory (KEEP / REFINE / REPLACE / MERGE / REMOVE)

### KEEP (logic/behaviour unchanged; styling may be re-skinned)
- `features/replay/lib/replayMachine.ts`, `probabilityTimeline.ts`,
  `features/simulator/lib/simulatorMachine.ts` — pure tested logic.
- `lib/v2.ts` contracts + `lib/api.ts` (behaviour), `lib/predictionTypes.ts`.
- Request/state hooks: `useReplay`, `useSimulator`, `usePrediction`.
- `StandingsTable` — already the canonical dense table.
- `ContextBar` — factual strip; text+colour status.
- `PlaybackControls`, `TimelineScrubber` — functional transport.
- `PredictionPanel` — correct independent-binary presentation.
- `SimulationResults` — correct Monte Carlo presentation.

### REFINE
- `app/globals.css` — add token layer, focus ring, reduced-motion.
- `app/layout.tsx` — add app shell/metadata; keep fonts.
- `PredictionTabs` — pills → square segmented control with tab semantics.
- `RaceSelector`, `ControlsPanel`, simulator controls — square controls,
  monospace numerics, consistent focus.
- `PredictionHero`, `ResultCards`, `DriverCards` — remove gradients/radius/
  hover lifts; adopt token type roles.
- `ProbabilityChart`, `ProbabilityTimelineChart` — flat grid, non-colour series
  encoding.
- `ReplayView`, `SimulatorView` — adopt shell; tighten region hierarchy.

### REPLACE
- Per-page headers/cross-link clusters → `AppShell` + `CommandBar`.
- Gradient/radius panel wrappers → shared `Panel`/`PanelHeader`.
- Rainbow confidence bar → linear token bar with value + semantics note.

### MERGE
- `OverviewCard` + `ChartInsightCard` → one `StatCell`/`StatTile`.
- `EnsembleResults` + `SingleResults` duplicated tab scaffolding → shared
  `ResultsShell` + mode-specific content.
- `ProbabilityChart` + `ProbabilityTimelineChart` → one chart primitive with
  two data adapters (keep separate wrappers if adapter cost outweighs merge).
- `api.ts` + `v2.ts` `API_BASE`/fetch plumbing → single transport helper
  (behaviour-preserving; optional, only if a stage touches both).

### REMOVE (visual only)
- `rounded-[18–30px]`, `rounded-2xl` panel containers, pill containers.
- `bg-gradient-to-*` surfaces, `shadow-xl/2xl`, `backdrop-blur`, gradient
  confidence bars, hover `scale`/`y`.

---

## 5. Redesign stages

Each stage: scope → likely files → design objective → tests → STOP gate.
Run stages sequentially; do not start the next without approval.

Verification commands (from `frontend/`), used by every stage:
```
node --test
./node_modules/.bin/tsc --noEmit -p .
npm run lint
npm run build
```
Plus Impeccable detector after UI edits:
```
/Users/tfatharva/.config/opencode/skills/impeccable/scripts/impeccable \
  detect --json <changed files>
```
Backend suite is not required for pure presentational changes, but is required
if a stage touches `lib/v2.ts`, `lib/api.ts`, hook contracts, or any
semantics-bearing formatting. When in doubt, run `python -m pytest tests/ -q`
once and record it.

---

### UI0 — Design tokens + foundations
- **Scope:** token layer, focus ring, reduced-motion baseline, panel/table/stat
  primitives; capture before/after screenshots.
- **Files:** `app/globals.css`, `app/layout.tsx`, new `components/ui/*`
  primitives, `docs/FRONTEND_DESIGN_SYSTEM.md` (already written).
- **Objective:** one neutral shell palette and DISPLAY/UI/DATA type roles;
  radius-0 border primitives available to all surfaces. No page rebuilt yet.
- **Also:** run `/impeccable init` if the user wants formal `PRODUCT.md`, and
  `impeccable document` to emit `DESIGN.md`; optional condensed-font decision
  recorded here.
- **Tests:** typecheck, lint, build, `node --test`; detector on `globals.css`
  and primitives.
- **STOP:** token diff + screenshots reviewed; semantics untouched.

### UI1 — Global shell / navigation
- **Scope:** `AppShell` (command bar, nav, context slot, status slot);
  migrate all three routes onto it; remove per-page headers.
- **Files:** `app/layout.tsx`, `app/page.tsx`, `app/replay/page.tsx`,
  `app/simulator/page.tsx`, `features/*/components/*View.tsx`, new shell
  components.
- **Objective:** one product, one navigation model; race context visible on
  every surface.
- **Tests:** typecheck, lint, build; navigation smoke; detector.
- **STOP:** all routes render inside one shell; cross-links behave; visual
  review captured.

### UI2 — Races / prediction surface (`/`)
- **Scope:** rebuild `.` around the new shell; square controls and segmented
  tabs, dense result strips, remove gradients/radii/hero-stat padding.
- **Files:** `app/page.tsx`, `components/prediction/*`,
  `features/prediction/components/*`, `lib/predictionHelpers.ts` (display only).
- **Objective:** prediction reads as race intelligence; independent-binary
  semantics remain explicit.
- **Tests:** `node --test` (prediction transforms/helpers), typecheck, lint,
  build; detector.
- **STOP:** semantics note still present; no probability displayed as a share;
  visual review.

### UI3 — Replay workspace (`/replay`)
- **Scope:** make replay the central analysis workspace: tighten
  context→transport→timeline→standings→model hierarchy; flat chart grid;
  non-colour series encoding.
- **Files:** `features/replay/components/*`,
  `features/replay/lib/probabilityTimeline.ts` (display mapping only).
- **Objective:** timeline, standings and probability evolution read as one
  instrument; checkpoint honesty preserved.
- **Tests:** `node --test` (replayMachine, probabilityTimeline), typecheck,
  lint, build; detector.
- **STOP:** paths still break at null; checkpoint markers distinct; visual
  review.

### UI4 — Simulator (`/simulator`)
- **Scope:** race-first controls, win %/podium %/expected-finish hierarchy,
  compact expandable finish distribution, status line for count/seed/runtime.
- **Files:** `features/simulator/components/*`, `SimulationResults.tsx`.
- **Objective:** outcome **frequencies**, not certainty; driver → win → podium
  → expected finish first, distribution secondary.
- **Tests:** `node --test` (simulatorMachine), typecheck, lint, build;
  detector.
- **STOP:** no certainty language; unsupported/error states clear; visual
  review.

### UI5 — Models / About
- **Scope:** introduce `MODELS` (model lab / production inference handoff) and
  `ABOUT` surfaces **only if** the user approves new routes; otherwise
  document as deferred.
- **Files:** new `app/models/`, `app/about/`; shell nav.
- **Objective:** technical provenance and product truth in the same shell.
- **Tests:** typecheck, lint, build; detector.
- **STOP:** scope approval first; no fabricated claims about model quality.

### UI6 — Responsive / accessibility polish
- **Scope:** keyboard/focus audit, tab semantics, contrast pass, reduced
  motion, narrow-layout compact rows + horizontal scroll, `aria-hidden` on
  decorative icons, screen-reader labels.
- **Files:** all components touched above.
- **Objective:** WCAG AA on the new surface without losing density.
- **Tests:** typecheck, lint, build; detector; manual keyboard pass; axe-style
  check if available.
- **STOP:** no critical a11y findings; visual review at 3 widths.

### UI7 — Visual regression / final audit
- **Scope:** capture reference screenshots for all routes/states; confirm tests
  and semantics unchanged; `graphify update .`; final Impeccable critique.
- **Files:** docs + screenshot fixtures only (unless a defect fix is approved).
- **Objective:** frozen visual baseline for future work.
- **Tests:** full frontend battery; targeted backend suite if contracts were
  touched; detector clean.
- **STOP:** final audit signed off; Phase 7 still not started.

---

## 6. Standard future frontend workflow

1. Read the task and the relevant frozen contract/phase doc.
2. `graphify query/path/explain` to inspect the affected architecture.
3. Optionally launch a headroom-wrapped session for context efficiency.
4. Load/read the Impeccable skill (`impeccable context`, then the matching
   command reference).
5. Inspect the current rendered (screenshot) or source UI.
6. Implement **one** bounded stage from §5.
7. Run `node --test`, `tsc --noEmit`, `npm run lint`, `npm run build`.
8. Visually inspect the result (desktop + narrow) where the app can run.
9. Run the Impeccable detector on changed files; resolve real findings.
10. Run `graphify update .` and review the diff.
11. **STOP for approval.** Do not chain stages.

---

## 7. Tooling instructions for future agents

- **Graphify** — architecture navigation and drift detection; always
  `graphify update .` after code changes. Already documented in `AGENTS.md`.
- **Headroom** — opt-in context trimming only; never allowed to hide test
  failures, truncate contracts, or alter source. Already documented in
  `AGENTS.md`.
- **Impeccable** — required design authority for UI work. `AGENTS.md` does not
  currently mention it. Proposed minimal addition (do **not** apply while
  `AGENTS.md` has uncommitted user edits):

```markdown
## impeccable

For any frontend UI work, load the `impeccable` skill before editing and follow
its workflow: run `<skill-dir>/scripts/impeccable context`, read the matching
command reference, and run the mechanical detector on changed files before
stopping. Direction authority is `docs/FRONTEND_DESIGN_SYSTEM.md`
(BRUTALIST MOTORSPORT TELEMETRY); execution plan is
`docs/FRONTEND_REDESIGN_PLAN.md`. Do not start a redesign stage without
approval; never break Phase-2/3/5/6 semantics for visuals.
```

---

## 8. Architectural audit (Graphify-informed)

Post-`graphify update` (AST-only, no topology change): graph is current.

- No import cycles: graph report `Import Cycles: None detected`.
- No simulation/reconstruction logic in React: `useSimulator` posts an anchor
  to the backend; `simulatorMachine.ts` only formats/validates. No leakage of
  backend semantics into components.
- Hook/state separation is clean; `page.tsx` holds layout only.
- **Large components to watch** (not necessarily wrong): 
  `ProbabilityTimelineChart.tsx` (378), `EnsembleResults.tsx` (321),
  `SingleResults.tsx` (273), `PredictionHero.tsx` (257),
  `ReplayView.tsx` (192), `SimulationResults.tsx` (130).
  `EnsembleResults.tsx` is a graph community hub; it is a composition
  component, but its duplicated tab scaffolding is a merge candidate.
- **Duplicated transport:** `lib/api.ts` and `lib/v2.ts` each define
  `API_BASE` + fetch wrappers — pattern duplication, candidate for a shared
  transport helper.
- **Duplicated visual patterns:** gradient panel wrapper, header/cross-link
  cluster, error banner, stat card, probability bar — each repeated ≥2×.
- **Data concern (pre-existing, not part of redesign):**
  `lib/predictionHelpers.ts` hard-codes an `formatDriverName` map for the
  2023 field only. Display-only; flag for a future data-driven lookup.

No refactor performed.

---

## 9. Rendered review status

The frontend is **not running** (no listener on :3000) and the API is not
running (no listener on :8000), so no screenshots could be captured. All
findings above are source-level and factual. Rendered desktop/mobile capture is
a required first action of UI0.

---

## 10. Files changed by this audit

- `docs/FRONTEND_DESIGN_SYSTEM.md` (new)
- `docs/FRONTEND_REDESIGN_PLAN.md` (new)

No code, config, or `AGENTS.md` changes were made. Nothing was staged or
committed. Phase 7 was not started.
