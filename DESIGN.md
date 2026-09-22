---
name: F1 Intelligence
description: Brutalist motorsport telemetry — a race-control terminal for F1 race intelligence.
colors:
  ink-950: "#05070a"
  ink-900: "#0b0f14"
  ink-850: "#111721"
  ink-700: "#1c2530"
  ink-600: "#2b3644"
  fg: "#e7ecf3"
  fg-muted: "#9aa7b6"
  fg-dim: "#74828f"
  signal: "#e10600"
  ok: "#3fb950"
  warn: "#d29922"
  danger: "#f85149"
  info: "#58a6ff"
  focus: "#f5f7fa"
typography:
  display:
    fontFamily: "Montserrat, ui-sans-serif, system-ui, sans-serif"
    fontWeight: 700
    letterSpacing: "-0.02em"
  ui:
    fontFamily: "Space Grotesk, ui-sans-serif, system-ui, sans-serif"
    fontWeight: 400
  data:
    fontFamily: "ui-monospace, SFMono-Regular, Menlo, Consolas, monospace"
    fontFeature: "tabular-nums"
rounded:
  none: "0px"
  chip: "2px"
spacing:
  1: "4px"
  2: "8px"
  3: "12px"
  4: "16px"
  6: "24px"
  8: "32px"
components:
  button-primary:
    backgroundColor: "{colors.signal}"
    textColor: "{colors.focus}"
    rounded: "{rounded.none}"
    padding: "8px 16px"
  button-secondary:
    backgroundColor: "{colors.ink-850}"
    textColor: "{colors.fg}"
    rounded: "{rounded.none}"
    padding: "8px 16px"
  input:
    backgroundColor: "{colors.ink-900}"
    textColor: "{colors.fg}"
    rounded: "{rounded.none}"
    padding: "8px 12px"
  chip:
    backgroundColor: "{colors.ink-850}"
    textColor: "{colors.fg-muted}"
    rounded: "{rounded.chip}"
    padding: "2px 6px"
  panel:
    backgroundColor: "{colors.ink-900}"
    textColor: "{colors.fg}"
    rounded: "{rounded.none}"
    padding: "16px"
  tab-active:
    backgroundColor: "{colors.ink-850}"
    textColor: "{colors.fg}"
    rounded: "{rounded.none}"
    padding: "8px 16px"
  table-header:
    backgroundColor: "{colors.ink-900}"
    textColor: "{colors.fg-muted}"
    rounded: "{rounded.none}"
    padding: "6px 12px"
  race-banner:
    backgroundColor: "{colors.ink-850}"
    textColor: "{colors.fg}"
    rounded: "{rounded.none}"
    padding: "6px 12px"
---

# Design System: F1 Intelligence

## Overview

**Creative North Star: "Race Control Terminal"**

This is the screen an engineer watches under pressure: a race-control terminal
and timing tower, not a consumer product. Every surface answers one of three
questions faster than a human can — how is the race now, who will win or how
likely, and what could happen from here. The interface is dense, structural and
factual. Panels are joined edge-to-edge by a grid and hairline rules rather
than floating as rounded cards in empty space. Data is the subject; the chrome
exists only to make data scannable.

The world is built for a desktop/laptop engineering workspace at ≥1280px, with
real F1 timing-tower density: one row per driver, rank, gap, tyre and status on
screen without scrolling. Brutalism here means strong geometry, hard edges,
visible structure, precise hierarchy and technical typography. It is not
random ugliness, fake terminal kitsch, or an accessibility regression.

The shell is deliberately neutral so that team and driver colours read as
information once they appear. F1 red is a signal, not wallpaper.

**Key Characteristics:**
- Square corners by default; 2px only for chips, badges and toggles.
- 1px structural borders; 2px rules only for command bars, active tabs and
  major section separators.
- One neutral near-black shell; colour reserved for status, flags and data.
- Three typographic roles only: DISPLAY, UI, DATA.
- No gradients, no glass, no blur, no decorative shadow.
- Status is never encoded by colour alone; null renders `—`, never `0`.

## Colors

A neutral technical near-black ramp carries the whole shell; a small, earned
signal set marks status. This is a **Restrained** strategy — neutrals plus
accents — because the visitor came to operate, not to be persuaded.

### Primary

- **Signal Red** (#e10600): brand, selected and active states only — the
  active tab fill, the primary action, a live/selected marker. It is used
  sparingly and is never the default emphasis for an arbitrary component, and
  never used as small text on `ink-950` (it does not meet AA there; pair it
  with a label or a fill).

### Secondary

- **Status Green** (#3fb950): green flag, available/supported, resolved.
- **Status Amber** (#d29922): safety car / VSC / unknown, stale data, caution.
- **Status Red** (#f85149): red flag, error, failure. Deliberately distinct
  from Signal Red so error and brand never blur together.
- **Model Cyan** (#58a6ff): model, checkpoint, probability-neutral highlight
  and focus-adjacent metadata.

### Neutral

- **Terminal Black** (#05070a): app background (`ink-950`).
- **Panel Black** (#0b0f14): panel and table surface (`ink-900`).
- **Raised Slate** (#111721): raised or active surface, table header, control
  bar (`ink-850`).
- **Hairline** (#1c2530): default 1px border and grid rule (`ink-700`).
- **Structural Rule** (#2b3644): strong 2px separators and selection
  (`ink-600`).
- **Foreground** (#e7ecf3): primary text (`fg`).
- **Muted Foreground** (#9aa7b6): secondary text (`fg-muted`).
- **Dim Foreground** (#74828f): metadata and disabled state (`fg-dim`), raised
  from the design brief's `#5d6b7a` so 10–11px metadata labels meet AA on the
  shell (5.12:1 on `ink-950`).
- **Focus White** (#f5f7fa): focus ring (`focus`).

### Named Rules

**The One Accent Rule.** Signal Red appears on a small minority of any screen.
Its rarity is what makes it read as "selected", not as decoration.

**The Data Colour Rule.** Team, driver and compound colours are data. The shell
must stay neutral so they remain legible as information; shell palette never
replaces them and they are never required to understand a value (a label or
value is always present).

**The Never-Colour-Alone Rule.** Every status, flag, stale marker or checkpoint
carries text or shape. Colour may reinforce, never carry meaning by itself.

## Typography

**Display Font:** Montserrat (self-hosted via `next/font`, fallback system sans)
**Body Font:** Space Grotesk (self-hosted via `next/font`, fallback system sans)
**Label/Mono Font:** system monospace stack (`ui-monospace, SFMono-Regular,
Menlo, Consolas, monospace`)

**Character:** Montserrat at a strong weight gives race numbers and titles a
broadcast-graphic weight without letterspacing; Space Grotesk keeps labels and
controls technical but readable; the system monospace carries every measured
value so columns never jitter. No new font dependency was added.

### Hierarchy

- **Display** (Montserrat 700–800, tight `-0.02em` to `-0.04em`, uppercase
  where suitable): winner name, big race numbers, page titles.
- **UI** (Space Grotesk 400–600, 13–14px primary text, minimum 13px body):
  labels, body, buttons, help text.
- **Data** (system monospace, tabular numerals): lap, gap, interval, position,
  probability, tyre age, runtime, sim counts, all table cells.
- **Label** (10–11px, uppercase, `0.12em`–`0.16em` tracking, muted): small
  metadata and column headers.

### Named Rules

**The Data-Is-Mono Rule.** Any numeric or measure column is monospace with
`font-variant-numeric: tabular-nums`. A numeric column is never set in a
proportional face.

**The Three-Roles Rule.** There is no fourth type role. If a piece of text does
not fit DISPLAY, UI or DATA, it is a misuse of one of the three.

## Layout

A 12-column CSS grid inside a content max width (`max-w-7xl` / `max-w-6xl`).
Primary and secondary regions are explicit: the running order / timeline
dominates, controls and model panels live in a narrower rail. Panels share
edges; horizontal overflow is allowed for dense tables and charts. Spacing is
the existing 4px-derived scale: micro 4, tight 8, standard 12/16, section 24,
page 32. Inside-panel padding stays tight (8–16px); whitespace separates major
regions, never pushes race data off the first viewport. Primary target is
desktop ≥1280px; between 768–1280px primary/secondary stack and tables scroll
horizontally; below 768px telemetry stays legible via horizontal scroll or a
compact row variant, never oversized cards.

## Elevation & Depth

**This system has no shadows.** Depth is conveyed entirely by border weight and
background step: `ink-950` → `ink-900` → `ink-850`, with `ink-700` hairlines
and `ink-600` strong rules. There is no shadow vocabulary, no glow, and no
`backdrop-blur`. A panel is not raised by a shadow; it is distinguished by its
border and surface step.

## Shapes

Hard corners are the signature. Structural radius is **0** at every step
(`rounded-xs` through `rounded-4xl` resolve to 0). Only chips, compound/flag
badges and toggles may use **2px** (`rounded-chip`). True circular swatches use
`rounded-full`; large radii (`18–30px`), pill containers and `rounded-2xl`
panels are anti-patterns. Borders are 1px structurally; 2px is reserved for the
command bar bottom, active tab underline and major section separators.

## Components

All controls are square, bordered and uppercase-labelled where they are
actions. Foundations are token-level in UI0; component markup is rebuilt in
later stages against these primitives.

### Buttons

- **Shape:** square (radius 0), 1px border.
- **Primary:** Signal Red fill with Focus White text, uppercase label, tight
  padding (8px 16px).
- **Secondary:** `ink-850` fill, `fg` text, `ink-700` border.
- **Hover / Focus:** hover steps the border/surface one level; `:focus-visible`
  gets the global 2px Focus White outline with 2px offset.
- **Disabled:** dimmed with a distinct pattern; not opacity alone.

### Chips

- **Style:** `ink-850` background, `fg-muted` text, `ink-700` 1px border,
  2px radius (`rounded-chip`), uppercase 10–11px label.
- **State:** selected chips use Signal Red or `ink-600`; compound and flag
  chips carry a text label, never colour alone.

### Cards / Containers

- **Corner Style:** square (radius 0).
- **Background:** `ink-900` surface, `ink-850` raised.
- **Border:** 1px `ink-700`; 2px `ink-600` for strong separators.
- **Shadow Strategy:** none — see Elevation & Depth.
- **Internal Padding:** 8–16px.

### Inputs / Fields

- **Style:** `ink-900` background, `ink-700` 1px border, square, `fg` text;
  numeric inputs use DATA (monospace, tabular).
- **Focus:** global `:focus-visible` Focus White outline.
- **Error / Disabled:** error uses `danger` with a text message; disabled uses
  `fg-dim` plus a distinct treatment.

### Navigation

- **Style:** a single global command bar in `ink-850`, uppercase UI labels,
  separated by 1px rules; active item marked by a 2px Signal Red underline and
  text weight, with `aria-selected` / current-page semantics. No pill nav.

### Tables

- **Style:** `border-collapse`, 1px row rules, sticky header on long tables,
  DATA monospace cells with right-aligned numbers and left-aligned text.
  Nulls render `—`; stale/unobserved provenance stays labelled.

### Race-control banner

- **Style:** full-width `ink-850` strip, uppercase label; flag state pairs its
  status colour with the flag name (GREEN / YELLOW / SAFETY CAR / VSC / RED).

## Do's and Don'ts

### Do:

- **Do** default to square corners (radius 0) and 2px only for chips/toggles.
- **Do** express depth with border weight and the `ink-950/900/850` step, never
  a shadow.
- **Do** set every measured value in DATA monospace with tabular numerals.
- **Do** keep the shell neutral; let team and driver colour be data.
- **Do** pair every status colour with a text label or shape.
- **Do** render missing values as `—` / `NO DATA`, dimmed rather than hidden.
- **Do** keep the global 2px Focus White `:focus-visible` ring and honour
  `prefers-reduced-motion`.
- **Do** keep primary and secondary regions explicit, with race data in the
  dominant surface.

### Don't:

- **Don't** use large radii (`rounded-2xl`, `rounded-[18–30px]`) or
  `rounded-full` containers and pills.
- **Don't** use `bg-gradient-*` surfaces, `shadow-xl/2xl`, glows or
  `backdrop-blur`.
- **Don't** use rainbow/confidence gradients on bars or cells.
- **Don't** add hover `scale`/translate lifts on data panels.
- **Don't** encode status, series or probability by colour alone.
- **Don't** render a numeric column in a proportional face, nor null as `0`.
- **Don't** imply certainty: independent binary probabilities are never shown
  as shares, and Monte Carlo frequency is never a promise.
- **Don't** make Signal Red the wallpaper; it marks selection and action only.
