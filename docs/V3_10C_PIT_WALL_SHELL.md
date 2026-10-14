# V3.10C — Pit Wall Shell + Navigation Simplification

First visible V3.10 product-consolidation stage. Shell + hierarchy +
navigation only. No event feed, no sector/lap, no stint history, no
strategy/counterfactual integration, no science/API changes, no MC2 work.

- V3.9 freeze: commit `fb0d8d8772bdc1343bc6be6c5ff9ee68cddd7203`, tag
  `v3.9-uncertainty-intelligence` (HEAD matches; verified).
- V3.10A semantics unchanged. V3.10B `WorkspaceState` unchanged (no fields
  added; B's contract would BLOCK C before accepting silent changes).
- Git: no commit, no tag, no push.

## 1. What was built

`/pit-wall` — the calm primary workspace shell:

- `frontend/app/pit-wall/page.tsx` — route + metadata only.
- `frontend/features/pit-wall/components/PitWallView.tsx` — shell: header
  (race label + single `RaceSelector`), per-race mount boundary, regions
  A/B/C/order/notes/F with `xl` grid areas
  (`header/header`, `track/driver`, `order/notes`, `timeline/timeline`).
- `usePitWallRaces` — served-race registry (mount-once, backend authority).
- `usePitWallRace(raceId)` — timeline + frame + transport, mounted with
  `key={raceId}` so race changes remount with fresh data instead of reset
  logic. No race/frame/driver identity in local state — identity is read
  from the workspace and all moves are workspace transitions validated
  against the loaded frame domain.
- `DriverPanel` — workspace selection + frame facts (position, gaps, tyre,
  stint, pits) + native picker + DETAILS disclosure primitive.
- `PitWallTransport` — first/prev/play/next/last + speed (44px targets).
  Lap-jump input deliberately omitted: lap/event jumps arrive with V3.10D
  event navigation.
- `driverFacts.ts` — pure roster facts, value-import-free (test-runnable).

## 2. Reuse (no fork)

`RaceSelector`, `ContextBar`, `SpatialTrackPanel`, `StandingsTable`,
`TimelineScrubber` composed directly; `ReplayView`/`useReplay` untouched.
Data via `getV2Races`/`fetchFullTimeline`/`getReplayFrame`; timing via
`intervalForSpeed`/`PLAYBACK_SPEEDS`; bounds via `canGoPrevious/canGoNext`.

## 3. Authority status

- Pit Wall: full workspace consumer (race = `raceId`, frame = `frameIndex`,
  driver = `selectedDriverId`). Zero local clocks.
- `/replay`: remains on the validated V3.10B adapter (migration deferred to
  D, explicitly documented). No silent divergence: the adapter validates
  before replay navigation.
- URL: provider-owned `?race=&frame=&driver=` works on `/pit-wall`.

## 4. Navigation

Before: 9 equal items (Predict, Replay, Simulate, Consensus, Uncertainty,
Strategy, Counterfactuals, Models, About).
After: primary `PIT WALL / RACES / MODELS / ABOUT` (`/pit-wall`, `/replay`,
`/models`, `/about`) + subordinate `Expert` strip keeping all 7 deep
surfaces reachable. RACES → `/replay` (existing race-selection surface;
smallest justified mapping). Home `/` unchanged (Option A); brand still
links `/`. Zero routes deleted, zero redirects.

## 5. Honest placeholders

- Race control: quiet note (V3.10D owns the feed).
- Strategy: disabled `EXPLORE STRATEGY` (strategy page cannot consume
  canonical links yet; V3.10G owns integration). No availability invented.
- DETAILS: pattern-only disclosure (V3.10E owns intelligence).
- No numeric intelligence anywhere (test-pinned); no recommendation, winner,
  or confidence language; expert jargon stays on expert pages.

## 6. Responsive / a11y

Single-column base (header, track, driver, timeline, order, notes);
two-column `xl` with track dominant. 44px transport/select targets.
Landmarks, one h1, h2 regions, native keyboard controls, `aria-current`
both nav strips, live regions + alerts, text+color status, reduced-motion
retained. Measurements recorded in `responsive_validation.json`.

## 7. Validation

Focused: 26 pit-wall tests (7 behavior + 19 integrity) pass. Full frontend
suite, tsc, eslint, production build, Python collection reconciled — see
`validation.json`. Pathology P1–P20 all zero.

## 8. Classification

**A. PIT_WALL_SHELL_VALIDATED** (pending browser measurements). Next gate:
V3.10D — race control feed + event-aware timeline.
