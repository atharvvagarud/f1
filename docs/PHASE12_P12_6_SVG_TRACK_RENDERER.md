# PHASE 12 P12-6 SVG TRACK RENDERER

## Final verdict

P12-6 COMPLETE — production SVG renderer (circuit, pit lane, driver
markers, availability presentation, trail primitive, loading/error/
partial states) over the frozen P12-5 API is implemented, fixture- and
live-validated, and green through CI. P12-7 not started.

## Baseline

- Frozen baseline: `218f4a653f8e7148d06fefc69798053b275795bc`
  (`post-v2-clean-baseline`); HEAD is exact at implementation time.
- Dirty work is only expected P12 accumulation (P12-0..5 backend +
  docs + records + tests) plus P12-6 frontend files (below). Zero
  UNKNOWN, nothing staged.

## Existing UI audit

Replay product view (`features/replay/components/ReplayView.tsx`):
context selector + transport, then running-order table beside model
intelligence; `Panel`/`PanelHeader` primitives (1px `ink-700` rules,
`ink-900` surfaces, uppercase display headers, data-meta right
note); `StandingsTable` dense timing-tower (tabular numerals,
em-dash nulls, `readableDriverId` abbreviation helper); error
convention `border-danger/40` + `role="alert"` with retry; loading
cues as structural `font-data` lines (`Loading frame…`).
Design tokens (`app/globals.css`): near-black shell, hard 0 radius,
no gradients/glass/shadows; signal red reserved for selected/active,
ok/warn/danger/info semantic hues, meaning never colour-only.
A future track panel belongs beside the running order (same grid
row); P12-6 does not place it there — audit only informed styling.
API client convention (`lib/v2.ts`): explicit DTO types (no `any`),
injectable `FetchLike`, `readJson` + typed error class,
`encodeURIComponent(raceId)`, `cache: no-store`. SVG precedent:
`ProbabilityTimelineChart` (SVG only, no chart dependency, dash +
legend redundancy for colour). Frontend tests: `node --test` on
`*.test.ts` with type-stripping (relative `./x.ts` imports), fail-
closed file-count manifest in
`scripts/run_ci_frontend_tests.py` (17 -> 18).

## Component architecture

Smallest sensible boundary — one presentational component file:

- `SpatialTrackRenderer` (`features/replay/components/`
  `SpatialTrackRenderer.tsx`): pure props in
  (`geometry`, `frame`, `status`, `errorDetail?`,
  `selectedDriverId?`, `trail?`, `headline?`), no fetching, no
  orchestration.
  - `CircuitPath` treatment (two restrained strokes, same `d`)
  - `PitLanePath` (subordinate single stroke)
  - `DriverMarkers` (exact-coordinate dots + offset number labels)
  - `DriverTrail` (optional pure primitive over supplied samples)
  - `StateBlock` (loading / error / unavailable / integrity)
- No component per trivial primitive; no replay-page wiring
  (P12-7); no status/race-control layers (P12-8).

## API types

`frontend/lib/spatial.ts` mirrors only the public P12-5 DTOs:
`SpatialGeometry`, `SpatialFrame`, `SpatialDriverState`,
`SpatialAvailability`, `SpatialWindow`/`SpatialWindowSample`. No
`any`, no untyped dictionaries, no backend artifact types.

## Data access

Minimal `FetchLike`-injectable client in `lib/spatial.ts`:
`getSpatialGeometry`, `getSpatialFrame`, `getSpatialWindow` (+
`SpatialApiError` with `isUnavailable`/`isUnknownRace`/
`isIntegrityError` predicates). No fetch calls inside SVG
components. Window is typed and harness-supported; no automatic
trail orchestration (P12-7).

## SVG coordinate system

Backend normalized y-down `[0,1]` consumed verbatim. Stable
renderer-local convention: `viewBox="0 0 1000 1000"`,
`svg = render * 1000` (exact: 0.25 -> 250, 0.75 -> 750),
coordinates quantized deterministically to milli-units.
PRESENTATIONAL ONLY — spatial relationships untouched. Chosen over
`0 0 1 1` for integer-friendly units, crisper strokes, and stable
`non-scaling-stroke` behavior.

## Aspect handling

`preserveAspectRatio="xMidYMid meet"` on a square viewBox: the
circuit is geometrically identical on desktop, tablet, and 390 px
narrow panels (verified: 356x356 render, no page overflow, markers
legible). Strokes/markers use `vector-effect="non-scaling-stroke"`
where size stability matters.

## Main track

Authoritative P12-5 polyline rendered verbatim as a single
deterministic `<path d>` (`M…L…Z`, round joins/caps, no fill).
Restrained two-stroke treatment per product language: subdued bed
(`ink-600`, 9u) + high-contrast line (`fg`, 2.5u) — schematic, not
game-like. No smoothing, no spline, no topology change (path output
exact-tested).

## Pit lane

Rendered only when `pit_status == PIT_GEOMETRY_SUPPORTED`, as the
supplied polyline in a thin subordinate `fg-dim` stroke. Deferred
circuits render no lane, no placeholder, no guessed connection
(fixture- and live-verified).

## Driver markers

One dot per AVAILABLE driver (FRESH or STALE with finite
coordinates) at exactly (`render_x`, `render_y`); compact circle
(`r=7`) + offset driver-number label (number preferred; driver id
fallback; no metadata duplication — P12-7 joins replay metadata).
Labels are offset siblings; the dot never moves (selection, overlap,
and label tests assert identical cx/cy).

## Availability presentation

FRESH: solid neutral dot. STALE: hollow dashed dim dot at its
authoritative coordinate (de-emphasized, never relocated, never
interpreted as retired/off-track/pit; `<title>` states availability
+ age). UNAVAILABLE: no marker (aged-out null coordinates render
nothing; universe coverage shown as `N NO FIX` metadata).

## Outside-viewport behavior

`outside_viewport` positions render unclamped at true coordinates
(exact-tested beyond `[0,1000]`); wrapper `overflow-hidden` prevents
layout breakage; footer reports `N OFF MAP`. Real-corpus note: 0.0%
of Bahrain observations fall outside; the flag path is exercised in
fixtures.

## Overlap policy

Near-identical positions keep exact dots (no jitter, no snapping,
no displacement). Legibility comes from small radius, stroke
hierarchy, label offsets, `<title>` reveal, and selected-marker
paint-last emphasis. Positions provably unchanged under selection.

## Team colours

DATA, not decoration: P12-5 frames carry no team colour, so markers
are neutral shell tones. No driver-number -> colour mapping exists
anywhere in the renderer. Selected marker uses the earned signal
accent (consistent with replay selection language).

## Selection

Optional `selectedDriverId` prop (matches replay's
`selectedDriverId` concept; unwired in P12-6): alters stroke to
signal, radius, label treatment, and paint order only. Coordinates
immutable (tested).

## Accessibility

SVG `role="img"` with per-panel `aria-label` (circuit, frame,
positioned/unfixed counts) plus `<title>`; track paths
`aria-hidden`; labels `aria-hidden` (decorative duplicates of
`<title>` text); states use `role="status"`/`role="alert"`;
meaning never colour-only (stale = shape + dash + text, counts in
text). No motion exists, so reduced-motion is trivially respected;
focusable markers deferred to P12-7 table integration (no action
exists to focus yet).

## Motion policy

Discrete authoritative updates only: no transitions, no
look-ahead, no next-frame interpolation, no Catmull-Rom, no
prediction-based movement. Props change -> exact re-render.

## Trail primitive

`DriverTrail(samples)`: open deterministic path through supplied
samples only, subordinate styling (`fg-dim`, 1.5u, 60% opacity),
no fetching, no future synthesis. Optional and off by default.
Live-verified (19-sample 5 s trail renders as one path).

## Loading/error/partial states

`loading`: structural `TRACK DATA / LOADING` (product convention).
`error`: danger-ruled panel with backend detail, no fabricated
fallback. `unavailable` (incl. 2024-r09-R): `SPATIAL DATA
UNAVAILABLE` with replay-usable note. `PARTIAL`: full function +
`PARTIAL SPATIAL COVERAGE` header note and `N NO FIX` counts.
Geometry-identity mismatch: markers withheld, integrity state
(unit-tested contract via `geometryMatchesFrame`).

## Responsive behavior

390 px verified: square aspect kept, centered, legible, no page
overflow; header/footer metadata wraps within the panel. Marker/dot
dimensions stay usable via viewBox scaling + non-scaling strokes.

## Geometry identity

`geometryMatchesFrame` (race + `geometry_sha256` equality) gates
marker rendering; mismatch renders the integrity state, never
silent markers. Enforceable by P12-7 orchestration through the same
exported predicate.

## Development harness

`app/spatial/` (no nav link; dev-only): fixture tabs (marker pack
with pit, pit-deferred, PARTIAL — compact synthetic loops, clearly
labeled non-data) plus live mode (race/frame inputs, `Load` and
`Load + 5 s trail`) against the running backend. No Storybook (not
present in repo).

## Real API visual validation

Backend (:8000) + harness (live mode), mid-race frames:

- Bahrain 2023 f528: recognizable Sakhir, correct aspect, 20
  markers on-circuit, pit branch subordinate with plausible
  pit-lane occupants.
- Monaco 2021 f709: compact harbour geometry legible, markers on
  track, no shortcut artifacts.
- Japan 2024 f452: Suzuka figure-8 with parallel runs and pit
  branch, no false connections in visible sections; topology is
  guaranteed verbatim from P12-3 (renderer cannot alter it).
- Australia 2023 f499: recognizable Albert Park, 19 markers
  (1 NO FIX as backend reports).
- Pit-period Bahrain f261 (Verstappen stop window): #1/#11/#81 on
  the pit lane line; 19-sample trail renders.
- PARTIAL 2023-r15-R f543: full track, `PARTIAL SPATIAL COVERAGE`
  note, 19 FRESH + 1 NO FIX.
- Unavailable 2024-r09-R: clean unavailable state.
- No screenshots committed; observations recorded here.

## External SVG decision

`julesr0y/f1-circuits-svg` NOT integrated: no package, no copied
assets, no runtime fetch, no import, no fallback, no registration
against external geometry. P12-3 remains sole authority;
cross-validation deferred to P12-9.

## Visual design review

Compared against replay/models/strategy screens: panel, header,
meta, and footer reuse the shared vocabulary (looks native).
Two-stroke track kept (schematic, not decorative). Markers kept
small with number labels (readable in packs; dots never move).
Selected treatment kept to signal ring + paint-last. One change
made: misleading fixture tab label corrected. Narrow-viewport
footer wrap accepted as honest telemetry density. No new palette,
no gradients, no shadows, no radius.

## Performance

Representative Bahrain payload: main path ~8.6 KB, pit path
~2.2 KB serialized `d`; live 19-marker DOM measures 80 SVG nodes
total (single `<path>` per polyline, never per-point nodes).
Update cost is a prop re-render of that flat tree; no profiling
claims beyond node/path sizes. SVG retained; no Canvas/WebGL/map/
chart dependency added (dependency count delta: zero).

## Tests

`frontend/lib/spatial.test.ts`: 17 tests, all green (exact
0.25/0.75 mapping, deterministic closed/open path output,
FRESH/STALE render + UNAVAILABLE absent, null-coord omission,
order/position preservation, label fallback, no clamping,
unplotted coverage listing, identity match/mismatch, trail
verbatim + null-skip + empty, client URLs, error predicates,
frozen-fixture no-mutation). Full frontend suite: 214/214 green.
`tsc --noEmit`, `eslint`, and production build green. Frontend
manifest: 17 -> 18 test files (governed).

## Backend safety

Backend untouched by P12-6 (frontend-only diff). Affected P12-5 API
tests re-run green (33 passed incl. firewall). No API contract
change; no blocker discovered.

## Predictive firewall

Renderer consumes presentation DTOs only; no path from frontend
spatial code into features/model_lab/simulation/strategy/
explainability (nothing to import — pure view code). ALL_84 = 84
(CI green). Spatial stays presentation-only.

## Scientific identities

Reverified without regeneration (no frozen paths touched; frozen
test surface green in CI):

- serving: `1116b34fc716035c2425e605b9a5cc15541a2d2335e26113f2e2eaf3fcaa59f4`
- Phase-2 content: `d2ee966c18d2ba5513ea4e22eb56cd836f50c4d5a6303c9695162a95d92799db`
- Phase-2 parquet: `b0f17b6662b355e9ead28fb5a442a1feb438d884d0313f3c2faf32d7ba1590b3`
- explainability: `bae84b614a6e9e176d5bb9c33b99dcaf4cba3f376333b0f075c828f73982939f`
- replay: `78a3c059888637fe83cc534d0eb7869b6d18e746724bb1ce0f03ee3b8ba96298`
- simulation: `r3-v1` through 2024, phase6-r3-empirical

6/6 exact.

## Known limitations

- Renderer is isolated: no replay-page placement, transport, or
  auto-advance (P12-7).
- Markers are non-focusable until P12-7 table integration gives
  them actions (no focus without function).
- Labels can visually overlap in dense packs (dots never move).
- Trail needs orchestration (P12-7); primitive renders supplied
  samples only.
- Live harness mode needs the backend + CORS origin for the dev
  port (dev-only concern, no product impact).

## P12-7 handoff

`SpatialTrackRenderer` props (`geometry`, `frame`, `status`,
`selectedDriverId`, `trail`) + `lib/spatial.ts` client
(`getSpatialGeometry/Frame/Window`) and predicates
(`geometryMatchesFrame`, `isPartialFrame`, `markerData`) are the
integration surface. P12-7 wires: race/frame selection, transport-
driven frame fetching, selection state, trail fetching policy, and
placement beside the running order. P12-8 owns status/race-control
overlays; no pit/retirement semantics were inferred here.

## Entry gate

All boxes green: baseline exact; P12-0..5 intact; zero UNKNOWN;
nothing staged; Graphify-first; replay UI audited; product
language reused; no competing visual system; explicit public
types; geometry + frame (+ typed window) clients; no FastF1/
Parquet knowledge in frontend; normalized coordinates consumed;
deterministic mapping (exact-tested); aspect preserved
(desktop + 390 px verified); closed loop correct; no frontend
smoothing; supported pit renders; deferred pit not fabricated;
exact marker coordinates (tested); no snapping/jitter; FRESH/
STALE/UNAVAILABLE per contract; no invented stale locations;
outside-viewport unclamped; overlap never alters truth; neutral
markers (no team mapping); selection coordinate-safe; a11y
semantics present; no future-aware motion; historical-only trail;
loading/error/PARTIAL states; SVG retained, zero new deps;
identity mismatch blocks markers; isolated harness; Bahrain/
Monaco/Japan/Australia + pit-period + PARTIAL + unavailable
visually validated; f1-circuits-svg absent; design review done
(one label fix); renderer + full frontend tests green; typecheck/
lint/build green; backend contract unchanged; API tests green;
predictive firewall green; ALL_84 = 84; six identities exact; no
frozen regeneration; preflight-source green; CI green; report +
record written; diff classified; nothing committed, tagged, or
pushed; P12-7 not started.
