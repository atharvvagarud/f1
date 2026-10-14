# V3.10D — Race Control Feed + Event-Aware Timeline

Connects historical race events to the single canonical replay clock.
No intelligence integration, no telemetry, no strategy/counterfactuals,
no science/API changes, no MC2 work.

- V3.9 freeze: `fb0d8d8772bdc1343bc6be6c5ff9ee68cddd7203` (HEAD matches).
- A/B/C semantics unchanged. `WorkspaceState` untouched (consumer-only).
- Git: no commit, no tag, no push.

## 1. Event sources (audited, not assumed)

Timeline metas carry no state; full states come only from per-frame
fetches. Supported: flag transitions (`track_state` D9 token), RC message
pair changes (lineage-only, text excluded upstream), pit-count increments
(observed completion only), lap increments (`leader_lap`). Omitted:
retirements (no causal signal — backdating forbidden), SC GPS (unobserved),
inferred incidents. Full inventory in `event_source_audit.json`.

## 2. Model + mapping

`ReplayEvent { id, raceId, frameIndex, eventTimeS, leaderLap, kind, label,
driverId }` — evidence on the replay domain, never workspace state, never
another clock. Closed 9-kind taxonomy. Mapping rule: FIRST canonical frame
at which the change is observable (nearest-frame logic does not exist).
Frame 0 is baseline. Gapped corpora throw rather than derive. Ordering:
`(frame, FLAG, MESSAGE, PIT driver-sorted, LAP)`; stable IDs; deterministic
across reloads. Rejections (`pit-from-unknown`, `pit-decrease`,
`lap-decrease`, `null-lap-skipped`) are counted, never placed.

## 3. Causality

Visible set = `frameIndex <= T`, enforced in pure selectors; feed, counts,
markers, labels, and accessible text all derive from it. Future markers are
hidden entirely. NEXT EVENT is a generic seek-forward control returning a
bare frame number — type/driver/lap/count stay hidden until arrival.
Mandatory poison tests (future SC/message/pit/flag storm) pass.

## 4. Product

- Feed (replaces the C reserved note): latest 5 causal events,
  chronological; older behind native disclosure; rows seek exact frames;
  driver chips select (distinct buttons; seeks never switch drivers).
  Empty vs unavailable language distinguished; retry included.
- Markers: separate dot strip under the scrubber (validated `TimelineScrubber`
  untouched); same-frame aggregation with count + details; keyboard seeks.
- Navigation: PREV/NEXT EVENT + PREV/NEXT LAP (exact first-frames, no lap
  clock), coexisting with play/step/speed/scrubber; seeks equal manual
  arrival (same race, same driver).
- Corpus: per-race bounded fetch (6 lanes, abortable, progress UI,
  module-memoized); responses shared with rendering (no duplicate bytes).

## 5. Validation

Unit: 21 event-model tests (mapping, ordering, causality, poison, perf).
Integration: 15 wiring/request/compat tests. Full suite, tsc, eslint,
production build, Python collection — see `validation.json`. Browser at
1600/820/390: before/at/after event states prove causal reveal
(frame 0: nothing; frame 18: GREEN + LAP 2 with metadata, aggregated
marker, generic NEXT preserved). One real regression caught and fixed
(grid-area overlap below `xl`).

Coverage: `event_coverage.json` (all 149 served races, offline read-only
replay service).

## 6. Classification

**A. EVENT_AWARE_REPLAY_VALIDATED.** Next: V3.10E — selected-driver
intelligence (MODEL / SIMULATION / DIFFERENCE / MC precision).
