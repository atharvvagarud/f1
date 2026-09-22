# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Primary user: a race engineer or technical race analyst working at a desktop
or laptop workstation, before or during a race session. They already know the
sport and the data model; they are not learning F1. Their job is to answer
"how is the race now", "who will win / how likely", and "what could happen from
here" faster than they could by reading raw timing and result tables, and to
trust that every number shown is a real evaluated value rather than a guess.

## Product Purpose

F1 Intelligence is a race-intelligence platform for historical lap-by-lap F1
races. It reconstructs exact historical race state, serves frozen-model winner
predictions at model checkpoints, replays a race frame-by-frame, and runs
Monte Carlo simulation from a chosen anchor state. Success means the analyst
can inspect, replay and simulate race outcomes with full provenance, on one
desktop workspace, and never be misled by an overstated number.

## Positioning

The mechanism a neighbouring F1 dashboard could not truthfully copy is
**leakage-safe historical replay plus frozen-model honesty**: only facts
observed at or before the current checkpoint are ever shown, independent
binary probabilities are displayed verbatim (never normalised to shares),
Monte Carlo results are presented as outcome frequencies over valid trials,
probabilities exist only at model checkpoints, frames are exact historical
observations with no interpolation, and null is never rendered as zero.

## Operating Context

- Desktop-first telemetry workspace; primary target ≥1280px laptop/desktop.
- Three implemented surfaces: winner prediction (`/`), historical replay
  (`/replay`), Monte Carlo simulator (`/simulator`).
- Technical/engineering audience; dense tables, checkpoints, seeds, runtimes,
  model and contract version identifiers are normal working material.
- Historical scope for the V2 surfaces is 2018–2024; the legacy V1 prediction
  stack serves its own frozen checkpoint scope.
- Repository contract phases: Phase 6 (Monte Carlo) is FROZEN; Phase 7
  (strategy) has NOT started and must not begin during frontend work.
- Frontend stack: Next.js 16 App Router, React 19, Tailwind v4 CSS-first,
  `motion`, `lucide-react`; tests are dependency-free `node --test`.

## Capabilities and Constraints

- **Implemented:** historical RaceState reconstruction; V2 HTTP API for races,
  states and winner snapshots; V1 legacy ensemble/single winner prediction;
  Phase-5 historical replay; Phase-6 Monte Carlo simulator.
- **Planned / not implemented:** strategy comparison engine (Phase 7),
  calibration, MLOps, Race Engineer AI, and `MODELS` / `ABOUT` frontend
  surfaces. Future strategy comparison is roadmap only and must not be
  presented as shipping functionality.
- **Frozen semantics that UI must preserve verbatim:** independent binary
  winner probabilities (sum may exceed 100%, explicitly not shares); Monte
  Carlo frequencies (never certainty, never Phase-3 probabilities); checkpoint
  gating; temporal leakage rules; replay frames as exact observations; no
  retirement inference; null ≠ zero.
- UI work must not alter prediction, replay, simulation or backend behaviour.

## Brand Commitments

- Product name: **F1 Intelligence**.
- User-pinned design direction: **BRUTALIST MOTORSPORT TELEMETRY** — race
  control, timing tower, engineering workstation, motorsport broadcast
  telemetry. Not generic SaaS, fintech, glassmorphism, Apple-clone, Material,
  or AI-startup landing page.
- The shell is neutral and technical; F1 red and team/driver colours are data
  accents, not wallpaper.
- Existing self-hosted `next/font` families (Montserrat display, Space Grotesk
  UI) are retained; no new font dependency is added during UI0.

## Evidence on Hand

- Real frozen contracts and behaviour: prediction/replay/simulation API
  payloads, model checkpoints, seeds, runtimes, contract versions.
- Real historical race data is available through the backend; the UI does not
  fabricate values where data is absent (renders `—` / `NO DATA`).
- **Absences future work must not fabricate:** no customer testimonials, no
  accuracy/performance benchmarks beyond recorded model cards, no pricing, no
  team/driver licensing claims, no strategy-engine capability.

## Product Principles

1. Facts over decoration — what changed is the data, never the card.
2. Structure is the interface — hairline grids, rules and aligned columns
   express relationships; panels are joined by the grid, not floating.
3. Density is a feature — a laptop engineer sees the running order, gaps,
   tyres and status without scrolling; whitespace is deliberate, not ample.
4. Honesty is visual — probabilities, frequencies, staleness and unknowns are
   presented exactly as the contracts define them; no implied certainty.
5. Numbers are first-class — telemetry values use tabular monospace so columns
   never jitter; colour is never the only signal.

## Accessibility & Inclusion

WCAG 2.1 AA. Body and label text meet AA contrast; every control is keyboard
reachable with a visible focus ring; status is never encoded by colour alone;
`prefers-reduced-motion` is honoured; semantics-bearing text and labels are
preserved.
