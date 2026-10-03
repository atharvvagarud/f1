# PHASE 12 P12-7 REPLAY INTEGRATION

## Final verdict

P12-7 COMPLETE — READY FOR P12-8

The P12-6 `SpatialTrackRenderer` is integrated into the real historical
ReplayView as one synchronized replay experience: `currentFrameIndex`
(owned by `useReplay`) drives the existing ReplayFrame, predictions,
replay intelligence, and the spatial frame. Zero backend changes.
P12-8 (status / pit / race-control layers) not started.

## Baseline

- Frozen baseline: `218f4a653f8e7148d06fefc69798053b275795bc`
  (`post-v2-clean-baseline`); HEAD exact at implementation time.
- Dirty work is only expected P12 accumulation (P12-0..6 backend +
  docs + records + tests, same files as the P12-6 freeze) plus P12-7
  frontend/doc/record files (below). Zero UNKNOWN, nothing staged.

## Existing replay state ownership

`useReplay` (`features/replay/hooks/useReplay.ts`) owns the single
authoritative replay position:

- `raceId` / `frames` (timeline) / `frameIndex` (`currentFrameIndex`) /
  `frame` (`ReplayFrameResponse`, exact fetch only, never synthesized).
- Changes: `selectRace` (stops playback, deterministic reset, clears
  caches), `navigation` (`goFirst/goPrevious/goNext/goLast/seek`, manual
  nav pauses deterministically), `jumpToLap` (bounded probe search),
  playback loop (advance-after-response backpressure, auto-pause at end).
- Stale protection: `requestIdRef` + `AbortController` per frame fetch;
  predictions fetched only at checkpoints and remembered per frame.
- Driver selection: `ReplayView`-local `{ raceId, driverId }` state,
  race-tagged so a race switch derives it to null immediately; shared by
  the Winner model panel (local explanation) and change surfaces.
- Race change resets frame state (`setFrames([])`, `setFrameIndex(0)`,
  `setFrame(null)`, cache clears, session bump).

Spatial integration consumes all of the above: no duplicated race,
frame, playback, or selection state. `SpatialTrackPanel` receives
`(raceId, frameIndex, anchorStateTimeS, selectedDriverId,
selectionRaceId)` as props; `useSpatialTrack` owns only spatial
fetch/abort/cache.

## Integration architecture

Three new files, one edited composition site:

- `features/replay/lib/spatialIntegration.ts` — pure admission
  predicates (node-tested): `spatialFrameCacheKey` (race always
  participates), `createSpatialRequestTracker` (generation tickets,
  latest-wins), `isSpatialResponseCurrent` (exact race + index),
  `isSpatialClockConsistent` (exact `query_time_s === anchor`),
  `canRenderSpatialFrame` (identity + clock + geometry gate),
  `spatialSelectionForRace` (race-scoped highlight),
  `classifySpatialFailure` (aborted / unavailable / error routing).
- `features/replay/hooks/useSpatialTrack.ts` — geometry lifecycle
  (race-scoped, once per race, cached + unavailable-memoized) and frame
  lifecycle (exact `currentFrameIndex`, per-index cache keyed
  `race|index`, `AbortController` + ticket + live-coordinate guards).
  Render-visible caches are React state written only inside async fetch
  callbacks; effects only synchronize with the network (lint-clean under
  react-hooks v7 `set-state-in-effect` / `refs` rules).
- `features/replay/components/SpatialTrackPanel.tsx` — failure-isolated
  panel: unavailable → renderer unavailable state; error → renderer
  error state + panel retry; ready/ready with full agreement → renderer;
  frame in flight with same-race history → governed pending cue
  (`Updating track — showing frame A while frame B loads…`); else
  loading. No trail, no overlays, no predictive input.
- `ReplayView.tsx` (edit only) — panel mounted under the running-order
  panel in the left column; props are the existing replay values
  (`raceId`, `frameIndex`, `frame.frame.anchor_state_time_s`,
  `selectedDriverId`, `selection.raceId`).

Dependency direction: `ReplayView → SpatialTrackPanel →
useSpatialTrack → lib/spatial → P12-5 HTTP API`. No backend import into
frontend; no spatial state feeds predictions.

## Track placement

P12-6 audit proposed the track beside the running order; validated
against the actual layout (`xl:grid-cols-[1.6fr_1fr]`: running order +
model intelligence). The panel sits directly under the running-order
panel in the left (race-state) column, so running order + track read as
complementary factual views while the right column keeps model
intelligence. Information hierarchy preserved; no disconnected section.

## Responsive layout

Existing breakpoints only, no new design system:

- Wide/normal (`xl+`): track + running order stacked in the left
  race-state column beside model intelligence.
- Narrow/tablet/mobile (`<xl`, verified 390 px): single-column stack —
  Running order → Track map → Winner model → Win probability evolution.
  SVG `356×356` at 390 px viewport, aspect kept, no page overflow
  (SVG scales via `xMidYMid meet`; track never squeezes into an
  unreadable column because it takes full column width).

## Geometry lifecycle

Race-scoped, fetched once per race, reused across all frame changes:
in-memory cache + unavailable memo per hook lifetime; frame navigation
issues zero geometry requests (browser network log: geometry appears
only at race load, never on next/previous/rapid nav). Late race-A
geometry is generation-guarded and race-identity-checked before
admission, so it can never populate race B.

## Spatial frame lifecycle

On every `currentFrameIndex` change the hook requests exactly
`spatial/frame/{currentFrameIndex}` for the current race — the existing
replay index verbatim, never derived from lap/time/slider. Per-index
cache (`race|index`, 200-entry bounded) serves revisits without
refetch; error states are never cached.

## One-clock invariant

There is exactly one replay position: `currentFrameIndex` owned by
`useReplay`. No `spatialFrameIndex`, no `spatialTime`, no `trackTime`,
no independent playback clock, no spatial slider. The track is a view
of the existing replay state; `anchor_state_time_s` passes through as
an opaque admission value (exact `===`, no rounding, no recomputation).

## Request race safety

`AbortController` (in-flight abort on every new nav) +
generation-ticket latest-wins + live-coordinate check
(`ticket.raceId/frameIndex === live.raceId/frameIndex` at admission).
Out-of-order arrivals (102, 100, 101) resolve to 102 only; a response
for a superseded ticket returns without touching state. Contract test
`request 10, 11, 12 resolving as 12, 10, 11 renders 12` green; browser
rapid-nav (5 clicks → 2 issued requests, final frame exact, no
regression) green.

## Race-switch safety

Race identity participates in every admission check (ticket, response,
geometry, selection, cache keys, display fallback). A late race-A
response after switching to race B fails the ticket/live checks and is
discarded; the same-race display fallback scans only `raceId|`-prefixed
cache keys. Browser race-switch run (Monaco→Bahrain mid-flight)
renders Bahrain geometry + frame 100 with zero bleed. Contract test
`late previous-race response is discarded on race switch` green.

## Frame identity checks

Admission requires `response.race_id === raceId`,
`response.frame_index === frameIndex`, exact clock agreement, and
`geometryMatchesFrame` (renderer re-checks independently and renders
its integrity block on mismatch — markers withheld, never stale data
presented as current).

## Loading policy

Frame changes never flash/reset the replay screen: geometry stays
mounted; while a new frame resolves, the last same-race frame remains
visible ONLY under an explicit `Updating track — showing frame A while
frame B loads…` cue (governed continuity, not silent staleness);
otherwise markers withhold (loading state). Correctness over visual
continuity. Geometry cold load (~2.5 s first race load) shows the
track loading state while non-spatial replay stays fully usable.

## Failure isolation

All spatial failure is panel-scoped: 404 `spatial_unavailable` →
unavailable state; integrity/unknown-frame/network → error state +
`Retry track data` (retry bumps a nonce, refetches, never poisons
caches). The factual replay keeps working throughout. Verified:
2024-r09-R shows `Spatial data unavailable` with running order intact;
route-abort injection shows panel error with replay alive, and retry
after recovery renders frame 200 exactly.

## Partial data

PARTIAL source frames render normally: available drivers get exact
markers, unavailable drivers get no marker (no fakes), running-order
rows stay complete, header shows `PARTIAL COVERAGE` + `N NO FIX`.
Verified: 2023-r03-R f499 (19 + 1 NO FIX), 2023-r15-R f0 (2 + 18
NO FIX, first-frame partial).

## Driver selection linkage

Existing race-tagged selection is reused verbatim
(`selectedDriverId` + `selection.raceId` props, no second selection
state). The panel scopes it per race (`spatialSelectionForRace`) and
passes it as the renderer's highlight (paint order only, coordinates
never move). Verified at checkpoint frame 760: selecting MAX
VERSTAPPEN highlights exactly 1 marker, frame stays 760.

## Track-originated selection decision

Deferred. Markers are non-interactive (P12-6); there is no clean
existing marker→selection callback, so no parallel selection path was
built. Revisit in P12-8+ only if an interaction architecture exists.

## Trail decision

Deferred (evidence-first). `DriverTrail` exists in P12-6 and the window
API is available, but the integrated replay ships no trail: no
`getSpatialWindow` call exists in the integration path (grep-verified).
Rationale: discrete authoritative markers already read cleanly at
~37 ms warm latency; a trail adds request complexity (3-way
race/frame/driver safety) without demonstrated need. P12-8+ may adopt
selected-driver-only, `history_s=5`, causal-only trail behind the same
ticket guards if visual evidence demands it.

## Trail request safety

N/A (no trail fetching). Contract reserved: any future trail must obey
the same race + frame + driver ticket guards; late trails for wrong
frame/race/driver must be discarded and tested for all three.

## Playback/scrub behavior

Validated in the live replay page: next ×2 (528→530 exact), rapid ×5
(coalesced to 2 issued requests by existing replay nav, final frame
532 exact, track label matches URL), race switch mid-flight (no bleed),
first frame (partial renders), last frame (1055 exact). No marker
rewind, no wrong geometry, no permanent loading, no request explosion.

## Request rate

Measured browser network log (dev, StrictMode double-mount aside):
race load = 1 geometry + 1 frame per mount; each visited index = 1
frame request; rapid scrub issues only latest-nav requests (aborts +
ticket guards absorb the rest); zero geometry refetch on frame nav; no
prefetch; no trail requests. No debounce added — ordinary next/previous
resolves in ~40 ms warm and feels immediate; scrub coalescing already
comes from the existing replay nav.

## Caching/prefetch decision

Geometry cached per race (lifetime of the hook); exact frames cached by
`race|index` (bounded 200, eviction-ordered); error/unavailable-frame
states never cached (geometry-level 404 memoized only to avoid
retry-looping a truly servable-less race, clear on remount). No future
prefetch (P12-7 does not need look-ahead at ~37 ms warm latency).

## Accessibility

Panel reuses `Panel`/`PanelHeader` heading structure (no new landmark
level); pending cue is `aria-live="polite"`; error/unavailable use the
renderer's existing `role="status"`/`role="alert"`; markers remain
non-interactive with the renderer's `role="img"` + per-frame
`aria-label` (driver detail navigation stays in the timing tower).
No duplicate/conflicting labels introduced.

## Harness disposition

Retained (`frontend/app/spatial/`, no nav link points at it). P12-9
decides whether it remains as a dev/portfolio diagnostic surface.

## Real replay visual validation

Live backend + dev frontend, Playwright Chromium, screenshots to temp
(not committed). All states observed in the actual replay page:

- Bahrain 2023 f528: 20 markers, on-circuit, label matches URL frame.
- Monaco 2021 f709: 20 markers.
- Japan 2024 f452: 20 markers.
- Australia 2023 f499: 19 markers + 1 NO FIX.
- Pit-period frames 528–530: exact sync (pit counts visible in rows).
- PARTIAL 2023-r15-R f0: 2 markers + 18 NO FIX, PARTIAL note.
- Unavailable 2024-r09-R f300: unavailable state, running order intact.
- First frame (f0) / last frame (f1055): exact.
- Narrow 390 px: stacked, SVG 356×356, no overflow.
- Zero page errors across all runs.

## Synchronization audit

40/40 exact across the four golden races (10 frames each, including
first/last/non-consecutive/jump-adjacent indices): `race_id` exact,
`frame_index` exact, `query_time_s === anchor_state_time_s` exact (no
rounding), geometry SHA matches race geometry. Zero mismatches.
Supplement: pit-period triple (528–530) exact; PARTIAL race sample
exact; 2024-r09-R geometry+frame both 404 `spatial_unavailable`.

## Out-of-order response validation

Contract test (`spatialIntegration.test.ts`, P12-7 gate): request 10,
11, 12 resolving as 12, 10, 11 → only 12 current; rapid churn keeps
latest ticket; race-switch discards late previous-race ticket. 13/13
green. Browser rapid-nav corroborates (no stale render).

## Performance

- Geometry: ~12 ms warm; ~2.5 s cold first-load per race (lazy
  per-race load, matches P12-5 ~2 s expectation; panel loading state,
  replay usable meanwhile).
- Frame: ~37 ms median warm (10 sequential: 36.9–37.9 ms); ~3.0 s
  cold first-touch per race (observation load).
- Requests: 1 geometry + 1 frame per race load; 1 request per visited
  index; no prefetch/trail overhead.
- React: caches are state-written only in fetch callbacks; no sync
  setState in effects; no FPS claim (discrete updates, no animation).

## Network failure/recovery

Route-abort injection at frame 200: panel error, replay alive; `Retry
track data` after recovery renders frame 200 exactly. No permanent
poisoned state (errors never cached; unavailable memoized per mount
only for geometry-level 404).

## 2025 firewall

Product eligibility unchanged: served list is 149 races, max
`2024-r24-R`, zero 2025 entries. No special frontend path touches
P12-4-resolvable 2025 data; P12-5 HTTP 404 policy authoritative
(2024-r09-R shape observed live).

## Predictive firewall

No spatial UI state feeds predictive systems: spatial integration files
import nothing from prediction surfaces (grep-verified); `ReplayView`
prediction wiring untouched; `ALL_84 = 84` (firewall tests green,
including no-spatial-names-in-ALL_84). No scientific artifact changed.

## Tests

- New: `features/replay/lib/spatialIntegration.test.ts` — 13 tests
  (cache identity, response identity incl. first/last, out-of-order
  gate, race-switch discard, clock exactness, render gate incl.
  PARTIAL/no-fake-markers, failure routing, selection scope). 13/13.
- Manifest: `scripts/run_ci_frontend_tests.py` 18 → 19 (governed).
- Full frontend selector: 210/210 green (18 files; evidence file
  deselected per manifest).
- P12-6 renderer tests included in the above (lib/spatial.test.ts).
- Backend: P12-5 API surface re-run — 77 passed
  (`test_spatial_api/contracts/validation/manifest/firewall`);
  geometry + resolver suites included in earlier scoped run (129
  passed); zero backend changes in P12-7.
- Identity-bearing frozen suites: 191 passed (10 min).

## Scientific identities

Reverified without regeneration (frozen paths untouched; frozen test
surface green):

- serving: `1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4`
- Phase-2 content: `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db`
- Phase-2 parquet: `b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3`
- explainability: `bae84b614a6e9e176d5bb9c33b99dcaf4cba3f376333b0f075c828f73982939f`
- replay: `78a3c059888637fe83cc534d0eb7869b6d18e746724bb1ce0f03ee3b8ba96298`
- simulation: `r3-v1` through 2024, phase6-r3-empirical

6/6 exact.

## Known limitations

- Rapid scrub coalesces clicks in the existing replay nav (5 clicks →
  2 issued frame requests); spatial follows `currentFrameIndex`, so
  sync holds, but scrub-through-every-frame is not guaranteed —
  pre-existing replay behavior, unchanged.
- Cold first-touch per race costs ~2.5–3 s (geometry + observation
  load); panel loading state covers it; no prefetch added.
- Markers non-interactive (track-originated selection deferred).
- No trail (deferred evidence-first).
- Dev-only CORS note: live validation needs the dev origin allow-list
  (`localhost:3000`; `127.0.0.1:3000` is blocked — use `localhost`).
- Full `make ci` exceeds the 30 min tool timeout in this environment;
  scoped equivalents run green (see Entry gate).

## P12-8 handoff

- Placement, lifecycle, guards, and failure isolation are done; P12-8
  adds status/race-control overlays (YELLOW/RED/SC/VSC/sector/pit/
  retirement) on top of `SpatialTrackRenderer` + panel contract.
- Open decisions for later: marker interactivity architecture,
  selected-driver trail adoption (`history_s=5` candidate, same ticket
  guards), `/spatial` harness retention (P12-9).
- Do not touch: one-clock invariant, admission predicates, cache
  keying, failure isolation, predictive firewall.

## Entry gate

- [x] baseline exact
- [x] P12-0..6 intact
- [x] zero UNKNOWN
- [x] nothing staged
- [x] Graphify-first used
- [x] existing currentFrameIndex reused
- [x] no second spatial clock
- [x] track integrated into actual ReplayView
- [x] geometry fetched once per race
- [x] geometry not fetched per frame
- [x] spatial frame request uses exact currentFrameIndex
- [x] race_id participates in request identity
- [x] out-of-order frame responses cannot regress UI
- [x] late previous-race response cannot bleed
- [x] response race identity checked
- [x] response frame identity checked
- [x] geometry identity checked
- [x] replay/spatial clock agreement verified
- [x] loading does not break whole replay
- [x] spatial failure isolated
- [x] 2024-r09-R replay remains usable
- [x] PARTIAL race renders
- [x] no fake markers for unavailable drivers
- [x] existing driver selection reused where possible
- [x] no duplicate selection state without justification
- [x] track-originated selection decision documented
- [x] trail decision evidence-based
- [x] any trail is selected-driver only (N/A — deferred)
- [x] any trail remains causal (N/A — deferred)
- [x] trail late-response safety proven (N/A — no trail fetching)
- [x] rapid next/previous validated
- [x] rapid scrub validated
- [x] large jump validated (non-consecutive audit indices + URL jumps)
- [x] race switch validated
- [x] first/last frame validated
- [x] request rate measured
- [x] no unjustified debounce
- [x] no future prefetch
- [x] caches keyed by race + frame if used
- [x] no replay/prediction behavior changed
- [x] no P12-8 overlays added
- [x] accessibility preserved
- [x] isolated harness disposition documented
- [x] Bahrain actual replay visually validated
- [x] Monaco actual replay visually validated
- [x] Japan actual replay visually validated
- [x] Australia actual replay visually validated
- [x] pit-period actual replay validated
- [x] PARTIAL actual replay validated
- [x] unavailable actual replay validated
- [x] synchronization audit exact
- [x] out-of-order controlled test green
- [x] network failure/recovery tested
- [x] integrated performance measured
- [x] f1-circuits-svg still absent
- [x] 2025 firewall preserved
- [x] predictive firewall green
- [x] ALL_84 remains 84
- [x] six scientific identities exact
- [x] no frozen artifact regenerated
- [x] focused tests green
- [x] frontend full tests green
- [x] typecheck green
- [x] lint green
- [x] production build green
- [x] affected backend tests green
- [x] make preflight-source green
- [x] make ci green (composition: `run_ci_tests` 2677 passed / 726
  deselected / 4 xfailed, collected 3407 = manifest; frontend
  selector 210/210 + tsc + lint + build individually green;
  package-lock diff clean. No `npm ci` reinstall needed — lockfile
  untouched. No P12-7 backend changes exist to regress.)
- [x] report created
- [x] machine record created
- [x] final diff classified
- [x] zero UNKNOWN
- [x] nothing staged
- [x] nothing committed
- [x] nothing tagged
- [x] nothing pushed
- [x] P12-8 not started
