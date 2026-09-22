# F1 Intelligence — Frontend Foundation Freeze Report (UI7)

Status: **FRONTEND FOUNDATION FROZEN** (audit / verify / document / freeze; no
redesign).

Baseline: Phase 6 frozen at `b813ffe1` (`v2-monte-carlo-phase6`). Phase 7
Strategy has **NOT** started.

> Bounded claim: *No blocking issue was detected under the implemented
> frontend freeze suite.* This report does not claim perfect accessibility,
> zero bugs, or production certification.

---

## 1. Frontend vision

**BRUTALIST MOTORSPORT TELEMETRY** — a race-control terminal for a technical
race analyst. Three implemented surfaces answer three questions: who will win
(`/`), how is the race now (`/replay`), what could happen from here
(`/simulator`). The shell is neutral and dense; hard edges (radius 0, 2px chips),
1px structural rules, three type roles (DISPLAY / UI / DATA), restrained Signal
Red, no gradients/glass/shadows, and honesty is visual: independent binary
probabilities are never shares, Monte Carlo frequencies are never certainty,
null is never zero, and staleness is labelled.

## 2. Implemented routes

| Surface | Route | Contract |
|---|---|---|
| PREDICT | `/` | V1 legacy ensemble / single winner prediction |
| REPLAY | `/replay` | Phase-5 historical replay (`v1`) |
| SIMULATE | `/simulator` | Phase-6 Monte Carlo (`v1`) |

All three render inside the single `AppShell` with one global `CommandBar`.

## 3. Deferred routes

`MODELS` and `ABOUT` (UI5) are **not implemented**. There is no route, nav item,
or placeholder, and no strategy surface. CommandBar exposes only PREDICT /
REPLAY / SIMULATE.

## 4. Design system

Tokens live in `frontend/app/globals.css` under Tailwind v4 `@theme`:
`ink-950/900/850/700/600`, `fg` / `fg-muted` / `fg-dim`, `signal`, `ok`,
`warn`, `danger`, `info`, `focus`; radius resolves to 0 with a 2px chip token;
DISPLAY (Montserrat), UI (Space Grotesk), DATA (system monospace, tabular
nums). Authority documents: `DESIGN.md`, `PRODUCT.md`,
`docs/FRONTEND_DESIGN_SYSTEM.md`, `docs/FRONTEND_REDESIGN_PLAN.md`.

## 5. Shared shell architecture

- `components/shell/AppShell.tsx` — global frame (`bg-ink-950 text-fg`, one
  `<main>`).
- `components/shell/CommandBar.tsx` — the only route-aware component; one
  `<nav aria-label="Primary">` with `aria-current="page"` on the active item.
- `components/ui/Panel.tsx` — `Panel`, `PanelHeader`, `Stat`,
  `ProbabilityBar`, `SemanticsNote`. Presentation-only; no scientific logic,
  no route or probability-semantics assumptions hidden inside.
- API transport is the frontend boundary: `lib/api.ts` (V1) and `lib/v2.ts`
  (V2). No component or feature calls a backend/scientific module directly.

## 6. Prediction UI semantics

Verified against a real ensemble and single-model run (2023 Abu Dhabi / 2023
Australian GP). `INDEPENDENT_BINARY` preserved: per-model independent binary
values are shown verbatim; the decision block states "not a mutually exclusive
race distribution and do not sum to 100%"; no normalisation, no race-share
wording, no Monte Carlo terminology; the API `confidence_label`
("Confidence (XGBoost)") and "Win probability" are preserved. The ensemble
decision is the model majority vote; the model's own rank ordering is labelled
as such.

## 7. Replay UI semantics

Exact reconstructed `RaceState` per frame; discrete frames (no interpolation);
`null` renders `—` / `NO DATA` and is never zero-filled; stale rows are labelled
with `observation_age_s` ("LAST OBSERVED …") and state "no retirement is ever
inferred"; track state is text + colour (GREEN / YELLOW / SAFETY CAR / VSC /
RED FLAG). Winner-model and probability-evolution panels are honest about the
**production cache absence** (`cache_missing`). Transport (first/previous/play/
pause/next/last), 0.5x–4x speed, leader-lap jump and the scrubber all drive
exact frame loads; the URL tracks `race` and `frame`.

## 8. Simulator UI semantics

`MONTE_CARLO_FREQUENCY` from one exact historical anchor. A real 1,000-trial run
(2022 Bahrain) rendered: most-frequent winner, win frequency, podium
frequency, expected finish, valid/invalid counts, winner mass "Sums to 1",
engine runtime, field frequency table with `DNF / points = — / —`, and a
driver × position distribution. A genuine unsupported run
(`neutralized_track_state`, safety-car anchor) was rejected by the backend and
rendered factually without any retirement claim. No Phase-3 probability mixing,
no invented reliability/DNF/points/traffic/overtaking/weather/SC, no strategy
recommendations, no fabricated uncertainty interval. Model scope and known
limitations are stated in the UI.

## 9. Responsive support

Playwright rendered overflow matrix, all routes × 6 viewports
(1440×900, 1024×768, 768×800, 650×800, 390×844, 360×800): **0 page-level
horizontal overflow** in every cell. Dense tables (replay standings, simulator
distribution) scroll locally inside `overflow-x-auto` wrappers at ≤650px
without forcing body overflow. CommandBar remains usable at all widths.

## 10. Accessibility posture

Target WCAG 2.1 AA. Rendered inspection of all three routes found: one `<h1>`
each, logical heading order, `banner`/`main`/`nav[Primary]` landmarks, labelled
form controls (native `select`/`fieldset`/`legend`/radio pair), real
`role="tablist"` with `aria-selected`/roving tabindex and arrow-key handling,
tables with `<caption>` and `scope`d row/column headers, sliders with
`aria-valuetext`, `role="status"`/`aria-live` regions, `aria-hidden` on
decorative icons/SVGs (including charts' legend swatches; chart `<svg>` carry
`role="img"` + label), no duplicate ids, and no unlabelled controls. Status is
never colour-only. One 2px `:focus-visible` ring is globally enforced.

## 11. State-consistency rules

- **PREDICT:** a displayed result belongs only to its exact season + GP + mode +
  model. Changing any selection clears the result, cancels the in-flight
  request, and never auto-runs; a stale response cannot be rendered
  (`usePrediction` request-id + selection guard). Verified live.
- **SIMULATOR:** changing race, state index, or count clears the result and
  resets status to Ready; Run is always explicit. Verified live.
- **REPLAY:** changing race swaps the timeline; the new race's exact state is
  loaded and the previous race's state/prediction cannot leak. Verified live.

## 12. Shared primitives

`Panel` / `PanelHeader` / `Stat` / `ProbabilityBar` / `SemanticsNote` reviewed:
generic, presentation-only, no feature-specific scientific logic, no
route-specific assumptions, no probability-semantics assumptions. Banned
patterns (gradient, shadow, backdrop-blur, large radius, hover scale/translate,
pulse/bounce) are absent from the frontend source.

## 13. Test / build evidence

| Gate | Result |
|---|---|
| `node --test` | **97 passed, 0 failed** (90 suites count unchanged) |
| `tsc --noEmit` | clean (0 errors) |
| `eslint` | **0 errors / 0 warnings** |
| `next build` | green (`/`, `/replay`, `/simulator` static) |
| Browser console | no React/dev warnings, hydration errors, duplicate-key warnings or uncaught exceptions; only expected backend HTTP resource errors (503 `cache_missing`, 422 `simulation_unsupported`) |

## 14. Graphify evidence

`graphify update .` before and after the audit: topology unchanged.
**8,898 nodes · 21,985 edges · 292 communities · import cycles: none detected.**
Frontend isolation confirmed: AppShell owns the shell, CommandBar owns
navigation, prediction/replay/simulator features stay isolated, no frontend
import reaches scientific implementation, no Strategy implementation, no
Models/About implementation.

## 15. Known limitations

1. **Replay prediction cache is not generated/served** (Phase-5 operational
   debt). Winner-model and probability-timeline states return `cache_missing`;
   factual replay is unaffected. This is the honest production state.
2. Simulator v1 scientific limitations are backend-frozen (no DNF/points,
   no traffic/overtaking, no reliability, no weather/SC evolution, empirical
   pit behaviour); surfaced verbatim in the UI.
3. `MODELS` / `ABOUT` surfaces and the Phase-7 strategy engine are not
   implemented.
4. A cold hard-navigation deep link to a replay `frame` can settle on frame 0
   before the timeline is cached; warm/deep client navigation preserves an
   explicit `frame`. Navigational only — not a semantic or functional blocker.
5. `PositionDistribution` defensively labels a contract-allowed `null`
   finishing position as "DNF". The frozen backend never emits a null position
   (only integer positions ≥ 1), so the path is unreachable in production; no
   null position column was observed. Latent, non-blocking.

## 16. Deferred work

- Phase 7 Strategy / what-if (owned by Phase 7 R0; not started).
- `MODELS` / `ABOUT` frontend surfaces (UI5).
- Offline replay prediction-cache backfill (operational).

## 17. Phase-7 handoff constraints

Phase 7 Strategy may extend the Simulator visual architecture. It must **NOT**:
reinterpret Monte Carlo probabilities; modify Replay exact-state semantics;
normalise Phase-3/4/5 independent binary probabilities; bypass simulation
eligibility; introduce oracle future information; or silently alter the frozen
frontend semantics. It must preserve the exact-anchor contract, the R7.1
non-contemporaneous refusal, no-retirement-inference, null ≠ zero, and
2018–2024 serving scope with the 2025 firewall.

## Appendix — application-code change in UI7

One blocker fix was required. The unrelated, untracked root
`package-lock.json`/`package.json` (tooling) caused Next.js to infer the
workspace root as the repository root, which broke `next build` with
`Can't resolve '@vercel/turbopack-next/internal/font/google/font'`. Documented
first, then corrected with the smallest change: `turbopack.root` pinned to the
frontend directory in `frontend/next.config.ts`. The build is green with the
stray root lockfile present. No prediction/replay/simulation semantics or other
application behaviour was changed.
