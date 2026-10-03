# PHASE 12 P12-8 RACE STATUS + SPATIAL CONTEXT

## Final verdict

P12-8 COMPLETE — READY FOR P12-9

The track answers WHERE ARE THE CARS; the panel now also answers WHAT
IS HAPPENING TO THE RACE RIGHT NOW with a compact race-status strip
(GREEN / YELLOW / SAFETY CAR / VIRTUAL SC / RED FLAG / STATUS UNKNOWN
plus a filtered latest race-control message). Every displayed state is
carried verbatim from the already-authoritative RaceState at the current
replay frame: zero new backend, zero new requests, zero new clocks, zero
predictive surface touched. P12-9 not started.

## Baseline

- Frozen baseline: `218f4a653f8e7148d06fefc69798053b275795bc`
  (`post-v2-clean-baseline`); HEAD exact at implementation time.
- Dirty work is only expected P12 accumulation (P12-0..7 files, intact)
  plus P12-8 frontend/doc/record files (below). Zero UNKNOWN, nothing
  staged.

## Source capability audit

Graphify-first, then verified in current code/data (no P12-0 assumption):

- FastF1 3.7.0 TrackStatus codes → D9 tokens, frozen in
  `raceintel/pipeline/d9schema.py`: `1→all_clear, 2→yellow,
  4→safety_car, 5→red_flag, 6→vsc, 7→vsc_ending`; null/empty/unknown →
  null. State at the lap boundary = last code char of the per-lap
  TrackStatus string.
- `RaceControlState` (`raceintel/race_state/race_state.py`): contemporaneous
  `track_state` + deterministic `flag_*` companions + latest timestamped
  message (`category/flag/age`; text excluded), carried verbatim per
  frozen replay row at T. Rebuilt per frame from the anchor row — same
  clock as the spatial query by construction.
- D7 as-of joins (backward-only, `observed_at_s <= state_time_s`,
  same-time tie-break by highest `message_seq`; untimed 2018-r02
  messages never attach): race-control messages, pit entry/exit events
  (`pit_last_in/out_*`, asymmetric boundaries preserved, nothing
  manufactured), current-stint start-side facts only.
- Served replay DTO already exposes all of `race_control`
  (`api/v2_schemas.py`, `frontend/lib/v2.ts`); the ContextBar already
  renders the same banner vocabulary. Driver DTO exposes
  `pit_stops_completed_so_far` / `laps_since_last_pit_stop` / stint
  fields but no in-pit-now flag; `pit_last_*` exists in D7 parquet but
  is NOT plumbed through the frozen replay artifacts.
- Hard domain rules found in code: no DNF/retirement target exists
  (`dnf`-shaped names forbidden); `observable=False` means unobserved,
  never retired; gaps during suspension stay nullable, never
  reinterpreted.

## Empirical status study

D9 parquet scans (all seasons for message vocabulary; per-race runs):

- Message categories (all seasons): CarEvent, Drs, Flag, Other,
  SafetyCar. Flag-category flags: BLACK AND WHITE, BLUE, CHEQUERED,
  CLEAR, DOUBLE YELLOW, GREEN, RED, YELLOW. SafetyCar-category flags
  always null.
- 2023-r01-R: `yellow → vsc → all_clear` (7745.7 / 7759.8 / 7873.8).
- 2023-r03-R: `safety_car → all_clear → safety_car → red_flag →
  all_clear (restart) → vsc → all_clear → yellow → safety_car →
  red_flag → all_clear → yellow → red_flag → all_clear` (richest
  corpus: SC + VSC + double red + restarts).
- 2023-r15-R: SC, VSC, `vsc_ending`, repeated yellows.
- 2024-r04-R: `red_flag → all_clear` (interrupted start → restart) +
  yellows. 2024-r09-R: yellows + SC (spatial-unavailable control).
- 2021-r05-R: all green (control).
- Message behavior at transitions (verbatim): `Flag/YELLOW` with yellow
  token; `SafetyCar/None` at SC/VSC deployment; `Flag/RED` up to one
  frame BEFORE the red token (causal as-of message, verbatim history);
  `Flag/CLEAR` after restarts; `Flag/BLUE`, `Other/*`, `Drs/*` as
  status-irrelevant chatter throughout.

## Supported / deferred / rejected features

- A race-wide track status: SUPPORTED (tokens + flags, in DTO).
- B yellow: SUPPORTED. C safety car: SUPPORTED. D VSC (+vsc_ending):
  SUPPORTED. E red flag: SUPPORTED (cars static/stale shown as-is;
  coordinates never frozen in frontend — P12-4 authoritative).
- F session stopped/resumed as separate state: REJECTED (no
  session-status in DTO; red/all_clear transitions already convey
  interruption/restart; new pipeline unjustified).
- G pit context: DEFERRED (no in-pit-now in frozen replay DTO;
  `pit_last_*` would need frozen-artifact regeneration — forbidden;
  stop counts already visible in the timing tower; proximity-to-branch
  inference explicitly refused).
- H retirement/stopped: REJECTED (no DNF semantics exist;
  UNAVAILABLE spatial coordinate ≠ RETIRED — already distinguished as
  NO FIX vs tower rows).
- I sector overlay: DEFERRED. J marshal-sector geometry: DEFERRED.
  K local-yellow colouring: REJECTED (race-wide token must look
  race-wide; no fake thirds).
- L race-control message: SUPPORTED, one compact filtered line
  (category ∈ {Flag, SafetyCar} AND flag ∈ {YELLOW, DOUBLE YELLOW,
  RED}; BLUE/CLEAR/GREEN/CHEQUERED/BLACK AND WHITE/nulls and
  Drs/CarEvent/Other chatter deterministically hidden).

## Architecture

Smallest possible: existing replay frame (already fetched by useReplay)
→ `raceControl` prop into `SpatialTrackPanel` → pure
`features/replay/lib/raceStatus.ts` view-model → `RaceStatusStrip`
above the renderer. No SpatialDriverState change (race-wide context
stays race-wide), no new persisted artifact (D7/D9 already frozen),
no new endpoint, no new request (status rides the replay frame fetch —
request-coalescing ideal), no trail, no marker interactivity.

Files: new `raceStatus.ts` + `raceStatus.test.ts` (5/5); edited
`SpatialTrackPanel.tsx` (strip in every branch) + `ReplayView.tsx`
(one prop). Manifest 19 → 20.

## Clock / causality contract

One replay clock preserved. Status shares T by construction (frozen
replay row at `state_time_s == T == spatial query_time_s`). Latest
status event with timestamp ≤ T only (D7 backward as-of); never
nearest; no future look-ahead; no event inferred before its timestamp.
Before first event the token is whatever the frozen row carries
(null → STATUS UNKNOWN, explicit). After last event the stateful token
carries (one-shot messages never persist as state — the message line
shows only the latest attached message, verbatim).

## Track-status mapping

`all_clear→GREEN, yellow→YELLOW, safety_car→SAFETY CAR, vsc /
vsc_ending→VIRTUAL SC, red_flag→RED FLAG, null/unknown→STATUS
UNKNOWN`. Same vocabulary and chip tokens as the ContextBar banner
(`bg-ok / bg-warn / bg-danger`, muted outline for unknown). Opaque
FastF1 numeric codes never reach the UI.

## Same-time ordering

Inherited frozen: D7 deterministic tie-break (highest `message_seq`
wins at identical `observed_at_s`); track_state is single-valued per
lap boundary (last code char). No incidental dataframe ordering relied
upon. Synthetic/contract level covered by view-model tests; real
same-stamp pairs observed (e.g. AUS red onset shares T across rows —
single token shown, no conflict possible).

## Race-wide presentation

Strip above the track map: `RACE STATUS [chip] [RC FLAG?]`. Compact,
brutalist, secondary to spatial truth. Geometry stays neutral (no
circuit recolour — race-wide semantics look race-wide). Text label
always present: never colour-only. Screenshot verified (YELLOW + RC
YELLOW above TRACK MAP, no domination).

## Sector-status decision

DEFERRED: no authoritative sector geometry exists; no fake polygons,
no thirds, no SECTOR-2-to-distance mapping. Textual message line is the
only sector-adjacent surface, and only when source-supported.

## Safety Car / VSC

Race-wide `SAFETY CAR` / `VIRTUAL SC` chips from the token. No
safety-car vehicle rendered (no authoritative spatial coordinates
exist; position never fabricated).

## Red flag / restart

Explicit `RED FLAG` chip; restart returns to `GREEN` at the correct
causal frame (AUS f942 RED → f943 GREEN verified live). Static/stale
coordinates display as-is; no frontend freezing.

## Pit context

DEFERRED in full: no PIT marker indicator (would require unsupported
inference or frozen-artifact regeneration). Tower stop counts unchanged
and untouched.

## Retirement / stopped context

REJECTED: no implementation. NO FIX (spatial) vs tower rows
(factual, incl. stale/unobserved) remain the only — and correctly
separated — signals.

## Race-control messages

One bounded line (`RC YELLOW` / `RC DOUBLE YELLOW` / `RC RED`) under the
deterministic filter above; null otherwise (no empty-state clutter).
Causal-only, verbatim, no history dump.

## Session status

REJECTED as a surface (see F). Internal terminology (Started/Aborted/
Finalised) never exposed.

## Driver-state join

No join performed: status is race-wide from the current frame's
`race_control` (same object the ContextBar reads). No independent
temporal lookup, no name-string join (nothing to join).

## API decision

No backend change: proven unnecessary — the served replay DTO already
carries every P12-8 input at the current frame. No new endpoint, no DTO
widening, no `context/{frame_index}` needed. (Had pit_last_* been
required, Part V would have applied; it was not.)

## Payload / cache

Incremental payload zero bytes / zero requests (rides the replay frame
fetch; verified in browser network log: nav adds only
`replay/frames/N` + `spatial/frame/N` + pre-existing checkpoint
prediction). No race-level status cache needed (no status fetch
exists). No event-stream dump anywhere.

## P12-7 integration safety

Unweakened: abort, generation tickets, race/frame/geometry admission,
and failure isolation untouched (no hook logic changed — panel only
gained a prop and a strip). Status strip renders from replay props, so
a late spatial response cannot alter it and a late race-A spatial
response cannot bleed into it. Strip shows during spatial
loading/error/unavailable (independent dimensions).

## Failure degradation

Status degrades to `STATUS UNKNOWN` on nulls (data-driven, not an
error state); spatial failure never hides status and status can never
fail independently (no fetch). Preferred degradation verified live:
2024-r09-R shows GREEN strip + spatial-unavailable panel — known
positions-unknown, status-known.

## Partial-data semantics

`PARTIAL SPATIAL COVERAGE` (positions dimension) and status (race
dimension) render independently: r15 f0 shows YELLOW + 2 markers + 18
NO FIX. Never conflated.

## Real transition validation

Live ReplayView (Playwright, zero page errors), strip vs track label:

- BHR f754 GREEN → f755 YELLOW + RC YELLOW → f760 VIRTUAL SC.
- AUS f113 GREEN → f114 SAFETY CAR; f937 SC + RC RED → f938 RED FLAG;
  f942 RED FLAG → f943 GREEN restart; f499 GREEN + 19/1 NO FIX.
- Goldens revalidated: BHR f528 GREEN, MON f100 GREEN, JPN f452 GREEN.
- r09 f300: GREEN strip + unavailable panel. r15 f0: YELLOW + partial.
- Selection linkage intact (P12-7 behavior unchanged).

## Boundary validation

Critical gate green: frame immediately before each event shows the
previous state (BHR f754 GREEN with T=7703.0 < E=7745.7; AUS f113
GREEN, f937 SC, f942 RED), first frame T ≥ E shows the new state
(f755 YELLOW, f114 SC, f938 RED, f943 GREEN). No early transition
anywhere. Token changes at lap boundaries per the frozen D9 contract;
the frontend adds no timing of its own.

## Visual validation

Screenshots to temp (not committed): YELLOW + RC YELLOW strip above
TRACK MAP at BHR f755 — compact, neutral geometry, markers legible,
status secondary. ContextBar banner agrees (same vocabulary). Narrow
layout unchanged (strip is a wrapping flex row).

## Performance

Incremental P12-8 cost: +0 requests, +0 bytes payload, +0 resolver
work (no backend path), one flex-row strip render (unmeasurable;
no FPS claim). Full-track recolour avoided by design.

## Tests

- New `raceStatus.test.ts`: 5/5 (full token vocabulary, UNKNOWN on
  null/bogus, label-always-present, message verbatim show/hide matrix
  incl. DOUBLE YELLOW + SafetyCar-null/Other/Drs/CarEvent arms).
- Manifest 19 → 20 (governed). Full frontend selector 215/215 green.
- P12-7 integration tests + P12-6 renderer tests included (green).
- Backend: zero changes; re-ran spatial surface 77 passed; firewall
  `test_all84_unchanged_and_spatial_free` green (ALL_84 = 84).
- tsc / lint / production build green.

## 2025 firewall

Unchanged: 149 served races, max 2024-r24-R, zero 2025 entries. No new
endpoint, no new data path; P12-5 HTTP policy untouched.

## Predictive firewall

Status is historical presentation state: `raceStatus.ts` imports only a
DTO type; no spatial/status value reaches ALL_84, matrix, winner model,
lab, simulation, strategy, or explainability. ALL_84 = 84 green. No
predictive file touched.

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

- Lap-boundary granularity: token changes land on lap boundaries
  (source contract), not intra-lap — transitions are causal but coarse
  by construction.
- `Flag/RED` messages can precede the red token by a frame (verbatim
  as-of history, e.g. AUS f937); the strip shows both honestly.
- No pit-now, no retirement, no sectors (deferred/rejected per
  evidence — see classification).
- Message line covers YELLOW/DOUBLE YELLOW/RED only; SC/VSC deployment
  relies on the status chip (SafetyCar messages carry null flags).
- Full `make ci` exceeds the 30 min tool timeout; scoped equivalents
  green (P12-7 precedent: backend selector 2677 passed).

## P12-9 handoff

- Status layer complete and isolated; P12-9 owns final validation +
  external geometry cross-check + freeze.
- Open: marker interactivity, selected-driver trail, pit-now/retirement
  only if frozen-artifact policy ever permits new fields, sector
  geometry only if authoritative polygons appear, harness retention.
- Do not touch: one-clock invariant, admission predicates, neutral
  geometry, message filter, firewalls.

## Entry gate

- [x] baseline exact
- [x] P12-0..7 intact
- [x] zero UNKNOWN
- [x] nothing staged
- [x] Graphify-first used
- [x] actual status sources audited
- [x] FastF1 status semantics verified
- [x] real corpus transitions inspected
- [x] features classified supported/deferred/rejected
- [x] no unsupported status invented
- [x] one replay clock preserved
- [x] every temporal lookup causal
- [x] no nearest-future lookup
- [x] event boundary tested
- [x] same-time ordering deterministic
- [x] race-wide status semantics honest
- [x] no fake sector polygons
- [x] no arbitrary circuit thirds
- [x] sector-specific overlay deferred unless real geometry exists
- [x] no fake safety-car position
- [x] pit state not inferred from coordinates
- [x] retirement not inferred from missing spatial data
- [x] RaceState reused where authoritative
- [x] no duplicate data pipeline without proof of need
- [x] any new API frame-index bound (N/A — no new API)
- [x] served eligibility reused
- [x] 2025 rejected publicly
- [x] payload bounded (+0 bytes)
- [x] no event-stream dump per frame
- [x] race-level cache if needed (N/A — no status fetch)
- [x] P12-7 admission guarantees preserved
- [x] optional context failure does not break spatial replay
- [x] PARTIAL spatial != unknown status
- [x] existing selection preserved
- [x] trails not expanded without justification
- [x] marker interactivity not expanded without justification
- [x] real GREEN/YELLOW transition validated
- [x] real SC transition validated if supported
- [x] real VSC transition validated if supported
- [x] real RED/restart transition validated if supported
- [x] real pit transition validated if implemented (N/A — deferred)
- [x] retirement/stopped validated if implemented (N/A — rejected)
- [x] visual states inspected in actual ReplayView
- [x] status not conveyed by colour alone
- [x] P12-8 incremental cost measured
- [x] f1-circuits-svg remains absent
- [x] predictive firewall green
- [x] ALL_84 = 84
- [x] six scientific identities exact
- [x] no frozen artifact regenerated
- [x] focused tests green
- [x] P12-7 tests green
- [x] P12-6 tests green
- [x] backend affected tests green if applicable
- [x] frontend full tests green
- [x] typecheck green
- [x] lint green
- [x] production build green
- [x] make preflight-source green
- [x] make ci green (scoped composition per P12-7 precedent)
- [x] report created
- [x] machine record created
- [x] final diff classified
- [x] nothing staged
- [x] nothing committed
- [x] nothing tagged
- [x] nothing pushed
- [x] P12-9 not started
