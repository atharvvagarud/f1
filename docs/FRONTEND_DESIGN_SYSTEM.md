# F1 Intelligence — Frontend Design System

Status: **PROPOSED / AUDIT-ONLY**. No UI code was changed to produce this
document. It is the design authority for the frontend stages that follow the
Phase-6 freeze (`v2-monte-carlo-phase6`, `b813ffe1`).

Named design direction:

> **BRUTALIST MOTORSPORT TELEMETRY**

This is not a generic dark dashboard and not a marketing site. It is a race
control terminal: dense, structural, factual, and readable under pressure.

---

## 1. Design philosophy

The product is a **race-intelligence instrument**, not a consumer app. Every
screen answers one of three questions faster than a human can:

1. How is the race now? (REPLAY / race context)
2. Who will win / how likely? (PREDICTION)
3. What could happen from here? (SIMULATOR)

Principles, in priority order:

1. **Facts over decoration.** What changed is the data, not the card. No
   gradients, glows, or glass exist to make a metric look important.
2. **Structure is the interface.** Hairline grids, rules and aligned columns
   show relationships. Panels are joined by a grid, not floating in space.
3. **Density is a feature.** A laptop engineer wants 20 drivers, gap, tyre and
   status on one screen without scrolling. Whitespace is deliberate, not ample.
4. **Honesty is visual.** Independent binary probabilities are never drawn as
   shares. Stale data looks stale. Unknown looks unknown (`—`, `NO DATA`). A
   Monte Carlo result reads as "frequency across simulated runs", never as a
   promise.
5. **Numbers are first-class.** Lap, position, gap, probability, tyre age and
   runtime use tabular monospace so columns never jitter between frames.
6. **One accent, earned.** The shell is neutral. F1 red and team colours are
   data accents, not wallpaper.

### What brutalism means here
Strong geometry, visible structure, hard edges, high information density,
deliberate type, functional borders, precise spacing, minimal decoration.

### What it explicitly is NOT
No random ugliness, unreadable type, arbitrary misalignment, gratuitous
animation, fake terminal kitsch, or accessibility regressions.

---

## 2. Visual references (conceptual, not copied)

- **F1 timing tower** — stacked, ranked, monospaced, one row per driver.
- **Race-control / stewards terminal** — status banners, flag states, an
  always-visible time and lap context strip.
- **Engineering workstation** — a command bar, a workspace, a telemetry rail,
  a status line.
- **Motorsport broadcast graphics** — big numeric callouts, small uppercase
  labels, tight condensed display type.

None of these are imitated literally; they set the density and hierarchy.

---

## 3. Layout rules

Application shell (adapt per surface, do not force every page into it):

```
┌ TOP COMMAND BAR ──────────────────────────────────────────────┐
│ PRODUCT  ·  PRIMARY NAV (RACES / REPLAY / SIMULATOR)  · STATE │
├ RACE CONTEXT STRIP ───────────────────────────────────────────┤
│ RACE · LAP x/y · FLAG · T+time · WEATHER   (always factual)   │
├ PRIMARY WORKSPACE ────────────────┬ SECONDARY TELEMETRY/CONTROL┤
│ dominant surface: table | replay  │ rail: model | run | chart  │
├ STATUS / MODEL INFORMATION ────────────────────────────────────┤
│ model id · seed · runtime · contract versions                 │
└───────────────────────────────────────────────────────────────┘
```

Rules:

- 12-column CSS grid inside a content max width (keep `max-w-7xl`/`max-w-6xl`
  as today; do not widen past comfortable reading).
- **Primary : secondary is explicit.** The running order / timeline is the
  dominant surface; controls and model panels live in a narrower rail.
- Panels connect through shared borders and the grid. Avoid free-floating
  rounded cards with individual shadows.
- Horizontal overflow is acceptable for dense tables and charts
  (`overflow-x-auto`); never chop columns to fit.
- Header, context strip and status line are sticky or persistent where it
  keeps race state visible while scrubbing.
- Navigation is a single global command bar, not per-page link clusters.

---

## 4. Typography

Three roles, no more.

| Role | Use | Family |
|---|---|---|
| DISPLAY | Winner name, big race numbers, page titles | Montserrat 700–800, tight tracking (`-0.02em` to `-0.04em`), uppercase where suitable |
| UI | Labels, body, buttons, help text | Space Grotesk 400–600 |
| DATA | Lap, gap, interval, position, probability, tyre age, runtime, sim counts, table cells | System monospace stack (`ui-monospace, SFMono-Regular, Menlo, Consolas, monospace`) with `font-variant-numeric: tabular-nums` |

Rules:

- Small metadata labels: 10–11px, uppercase, `tracking-[0.12em]`–`[0.16em]`,
  muted colour.
- Data cells are always monospace + tabular. Never render a numeric column in
  the UI face.
- Display type may be large but stays tight; do not letterspace display text.
- **No new font dependency by default.** The existing next/font families
  (Montserrat, Space Grotesk) already self-host; monospace comes from the OS
  stack. A condensed display face (e.g. Saira Condensed / Archivo Narrow) is an
  **optional UI0 decision with a STOP gate**, not a requirement.
- Minimum readable body size 13px; primary table text 13–14px; never below
  11px except uppercase metadata labels.

---

## 5. Color

Neutral shell + data accents. Tokens below are the intended system; today the
app hard-codes Tailwind `slate`/`red`/rainbow gradients.

### Shell (neutral, technical near-black)
| Token | Intent | Approx |
|---|---|---|
| `--color-ink-950` | app background | `#05070a` |
| `--color-ink-900` | panel surface | `#0b0f14` |
| `--color-ink-850` | raised/active surface | `#111721` |
| `--color-ink-700` | subtle border/grid | `#1c2530` |
| `--color-ink-600` | strong structural border | `#2b3644` |
| `--color-fg` | primary text | `#e7ecf3` |
| `--color-fg-muted` | secondary text | `#9aa7b6` |
| `--color-fg-dim` | metadata / disabled | `#5d6b7a` |

### Signal (status + accents, used sparingly)
| Token | Meaning |
|---|---|
| `--color-signal` | F1 red `#e10600` — brand/selected/active only |
| `--color-ok` | green — green flag, available/supported |
| `--color-warn` | amber — SC/VSC/unknown, stale, caution |
| `--color-danger` | red — red flag, error, failure |
| `--color-info` | cyan/sky — model/checkpoint/probability neutral highlight |
| `--color-focus` | focus ring (default `--color-signal` or high-contrast white) |

Rules:

- **Driver/team colours are DATA.** They stay meaningful and are never replaced
  by the shell palette. The shell must look neutral so team colour reads as
  information.
- No background gradients, no glow shadows, no `backdrop-blur`.
- Red is not the default emphasis for every component just because it is F1.
- Every status colour is paired with a text label or shape (never colour-only).
- Probability/confidence must not be encoded by colour alone; numeric value is
  always present.

---

## 6. Spacing

- Base unit 4px (Tailwind scale is already 4px). Use `gap-*` on grid parents,
  not per-child margins.
- Density rhythm: micro 4, tight 8, standard 12/16, section 24, page 32.
- Deliberate whitespace: separate major regions with 24px and rules; keep
  inside-panel padding tight (8–16px).
- No decorative empty space that pushes race data off the first viewport.

---

## 7. Borders, rules & the radius policy

- **Structural borders are 1px.** Strong dividers may be 2px, used only for the
  command bar bottom, active tab underline, and section separators.
- Borders create the grid: panels share edges; a border is a relationship, not
  a container decoration.
- Horizontal rules separate header / context / workspace / status.
- **Radius policy: `0` by default.** Allow `2px` for chips/compound/flag
  badges and toggles. No `rounded-xl/2xl/[24–30px]`, no `rounded-full` pills
  except a true circular swatch. Hard corners are the signature.
- Shadows: none. Depth is expressed by border weight and background step.

---

## 8. Data-density rules

- Default driver table row height ~28–32px; compact mode ~24px.
- One row per driver; rank, driver, lap, gap, tyre, stops, status are columns,
  not card fields.
- Numbers right-aligned; text left-aligned; status labels uppercase.
- Nulls render `—` or `NO DATA`; never `0`. Missing data is visually dimmed,
  not hidden.
- Stale/unobserved provenance stays labelled (as `StandingsTable` already does).
- Aggregates that are "independent binary estimates" must display a visible
  note that they do not sum to 100%.

---

## 9. Tables

- `border-collapse`, 1px row rules, monospace tabular cells.
- Sticky header on long tables.
- Zebra striping is optional and must be extremely subtle; prefer hairline
  rules + hover row highlight.
- Numeric columns fixed-width so frames don't reflow.
- Row identity is driver id + number + constructor, never colour alone.

Canonical example to promote: `features/replay/components/StandingsTable.tsx`.

---

## 10. Telemetry presentation

- Big numeric callouts for the few headline values (win %, lap, gap, expected
  finish) in DISPLAY/DATA type.
- Small uppercase labels beneath or beside them.
- Probability = a value + a thin horizontal bar. Never a pie, never a stacked
  share for independent-binary values.
- Charts are flat, axis-ruled, monochrome-grid with a small categorical
  palette; series are legible without colour (labels/dashes).
- Runtime, seed, model id and contract versions belong in the status region,
  small and muted, not in the headline.

---

## 11. Controls

- Buttons: square, 1px border, uppercase label; primary action uses the signal
  colour, secondary is neutral; disabled is dimmed with a distinct pattern, not
  just lower opacity.
- Tabs/segmented controls: a single bordered strip with an active item marked
  by a fill + 2px underline; not floating rounded pills. Use real
  `role="tablist"`/`aria-selected`.
- Selects/inputs: square, monospace for numeric inputs, strong focus ring.
- Playback transport: glyph buttons are acceptable but must carry
  `aria-label` (they already do) and a visible pressed/disabled state.
- Sliders: square track, hard thumb, tabular readout.

---

## 12. Charts

- SVG only (no chart dependency; `package.json` was audited — keep it that
  way).
- Flat rules, no grid fill, no gradients, no glow.
- Checkpoint/model observations are discrete points; lines break at null;
  never interpolate a value that was not evaluated.
- The current frame marker is distinct from data and from flag transitions.
- Every series must be identifiable without colour (toggle labels with the
  value, or dash patterns).

---

## 13. Motion

Restrained, functional, short.

Allowed: state transitions (tab/panel swap), selection and hover feedback,
playback advancement, chart/bar updates, loading progress.

Forbidden: decorative float, constant pulse, parallax, large spring/scale
marketing effects, hover `scale` lifts on data panels.

Rules:
- Durations 120–240ms; easing standard ease-out.
- Respect `prefers-reduced-motion`: disable non-essential transitions.
- Never animate a number in a way that hides its true value or delays a
  factual update.

---

## 14. Accessibility

Brutalism does not override accessibility.

- Keyboard: every control reachable and operable; visible focus ring on all
  interactive elements (today several lack one — see §15).
- Tabs use `role="tablist"` + `aria-selected`; a `div` of buttons is not a tab
  control.
- Status is never colour-only: flag, stale, checkpoint, error all carry text.
- Contrast: body/labels meet WCAG AA. `slate-500`-grade muted text on near-black
  is borderline at 11px — raise to the muted token or increase size/weight.
- Semantic HTML: real `<table>`, `<button>`, labelled inputs; `aria-live` for
  loading/playback status (already present in replay/simulator).
- Charts get `role="img"` + `aria-label` and an equivalent textual value table
  where practical (checkpoint detail table already exists).
- Decorative lucide icons should be `aria-hidden`.

---

## 15. Responsive behavior

- Primary target: desktop/laptop engineering workspace (≥1280px).
- 768–1280px: primary/secondary becomes stacked, tables/charts scroll
  horizontally, context strip wraps.
- <768px: keep telemetry legible; use horizontal scroll or a compact row
  variant (driver + position + one key metric). Do **not** explode dense
  telemetry into oversized cards.
- Never remove a data column to "fit" mobile; provide scroll or a compact
  representation with full detail reachable.

---

## 16. F1-specific component language

- **Position marker** — `P1`, `P12` square chip, tabular.
- **Lap counter** — `LAP 28 / 57` in DATA type.
- **Interval/Gap** — `+2.431` monospace, `+1 LAP`, `n/a` for invalid.
- **Tyre/compound badge** — square 2px-radius chip: `SOFT 12`, `MED 5 • NEW`.
- **Race-control banner** — `GREEN / YELLOW / SAFETY CAR / VSC / RED FLAG`,
  full-width strip, colour + label.
- **Stint / pit** — stop count and laps-since-pit as aligned numeric columns.
- **Probability cell** — value + thin bar + semantics note.
- **Win % / Podium % / Expected finish** — headline simulator triple.
- **Checkpoint marker** — discrete, labelled "model checkpoint" vs "factual
  frame".
- **Status line** — seed, sim count, runtime, model/parameter/contract versions.

---

## 17. Anti-patterns (banned)

- `rounded-[24px]`–`rounded-[30px]`, `rounded-2xl` panels and `rounded-full`
  pills as containers.
- `bg-gradient-to-*` surfaces and `shadow-2xl` / glow shadows.
- `backdrop-blur` glass.
- Rainbow confidence gradients (`from-* via-* to-*`) on bars.
- Hover `scale`/`y` lifts on data panels.
- Colour-only series/status encoding.
- Implied certainty: rendering Monte Carlo frequency as a promise; rendering
  independent binary estimates as a 100% share; inventing a value between
  checkpoints.
- Numeric columns in a proportional face.
- Recreating backend simulation/reconstruction logic in React.
- Duplicate ad-hoc surface wrappers per results file.

---

## 18. Semantics that the visual system must never break

These are frozen Phase-2/3/5/6 contracts; styling may change, meaning may not:

- **Temporal leakage rules** — no future information in any displayed state.
- **Independent binary probabilities** (Phase-3): display verbatim, never
  normalised, sum may exceed 100%, explicitly labelled as not shares.
- **Monte Carlo frequencies** (Phase-6): outcome frequency over valid trials;
  never presented as certainty or as Phase-3 probabilities.
- **Checkpoint honesty** — probabilities exist only at model checkpoints.
- **Replay facts** — frames are exact historical observations; no value is
  inferred or interpolated between frames; stale rows show last-known facts.
- **No retirement inference** — the UI never claims a driver is out.
- **Null ≠ zero.**

---

## 19. Current-state gap summary (what the system replaces)

The implementation today is a generic dark SaaS look: near-black `slate-950`,
large-radius gradient panels, pill tabs, glass blur, coloured confidence
gradients, and hover lifts. The dense, honest replay/simulator data logic is
excellent and is the foundation to keep; the **surface language** is what this
system replaces. See `docs/FRONTEND_REDESIGN_PLAN.md` for staged execution and
the per-component classification.
