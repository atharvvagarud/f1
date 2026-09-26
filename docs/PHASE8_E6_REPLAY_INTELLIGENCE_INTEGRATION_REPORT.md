# PHASE 8 E6 — REPLAY INTELLIGENCE INTEGRATION + UX/PERFORMANCE HARDENING

Status: **E6 COMPLETE — READY FOR E7**

Phase 8 progress: E0 complete, E1 complete, E1.5 complete, E1.6 complete,
E2 (production replay prediction cache: 149 races / 9,644 checkpoints /
189,610 observable predictions) complete, E3 (global explainability)
complete, E4 (exact local checkpoint explainability) complete, E5
(prediction timeline intelligence + change explanations) complete, **E6
(replay intelligence integration + UX/performance hardening) complete**.

E6 turns the individually validated Phase-8 capabilities into one coherent,
robust Replay Intelligence experience. It is integration, UX hardening,
state management, request efficiency, error handling, responsiveness,
accessibility and performance work only. **No scientific change**: Phase-1
data, Phase-2 features, ALL_84, the Phase-3 model, preprocessing, Phase-4
RaceState, Phase-5 replay semantics, Phase-6 Monte Carlo, Phase-7 strategy,
the E2 prediction cache semantics, E3 explanation mathematics, E4 local
explanation mathematics and E5 delta mathematics are all untouched. No
retrain/retune/recalibration, no probability normalization, no checkpoint
selection change, no 2025 access, no SHAP, no LLM explanation, no event
attribution, no new prediction/explanation science. No backend file was
modified by E6 (verified via `git status`: E6 touched frontend replay
files only).

## 1. Current UX audit (observed, running app)

Inspected `/replay` live (backend + frontend running locally) at 1440,
1024, 768, 650, 390 and 360, on a 2018 race (2018-r01-R, frames 0/1/100)
and after race-switching to 2024 races, covering initial load, race
selection, frame navigation, checkpoint navigation, driver expansion,
local explanation, timeline, change explanation, loading/error/empty
states and keyboard navigation. Concrete issues found and fixed:

1. **Stale change payload on driver/frame switch.** `useTimelineChange`
   kept the previous selection's `ready` payload rendered while the new
   selection's request was in flight (no reset; panel not remounted).
   Fixed with a keyed-selection guard (section 3).
2. **Two independent driver selections.** `PredictionPanel` held a
   private `selected` state for the local explanation while the timeline
   `CheckpointDetails` held a separate `changeDriver` state. The two
   explanation surfaces could refer to different drivers with no visible
   relationship. Fixed with one race-tagged shared selection (section 2).
3. **Race switch re-applied the old deep-linked frame.** `useReplay`
   reused the mount-time `?frame=` value for every subsequently selected
   race, silently dropping the user mid-race in the new race (observed:
   2018-r01-R frame 100 -> 2024-r02-R landed on frame 100). Fixed: the
   deep link applies to the first race load only; later race switches
   start at frame 0 (section 4).
4. **Local explanation header named no driver/frame.** The panel showed
   scores without saying whose. Fixed: header now reads
   `{DRIVER} · frame {N} · additive model decomposition · independent
   per-driver binary estimate`.
5. **Change panel never stated its exact frames.** Fixed: ready state
   carries `Exact checkpoints · frame {A} → frame {B}`.
6. **Generic request-failed strings.** `Prediction request failed.` /
   `Explanation request failed.` / `Change request failed.` collapsed
   404/422/503 semantics. Fixed: API codes now travel into the copy,
   e.g. `Winner model unavailable (404 not_prediction_checkpoint).`
   (section 6). Backend semantics verified live: `unknown_driver` 404,
   `driver_not_observable` 422, `not_prediction_checkpoint` 404 with
   nearest pointers (never snapped), 2025 -> 404 `unknown_race`.
7. **Direction communicated by arrow glyph/title only.** Fixed: rows
   carry screen-reader-only `INCREASED/DECREASED MODEL LOG-ODDS`
   prefixes; change group headings use words
   (`Increased/Decreased model log-odds`); driver buttons gained
   `focus-visible` outlines and `(selected)` screen-reader state.

No other integration problem was observed: the non-checkpoint,
first-checkpoint, unobservable-driver and null-prediction states were
already explicit and correct; the brutalist telemetry hierarchy and
factual/prediction/explanation visual separation were already clean and
were preserved (no visual rewrite).

## 2. State ownership

Single authoritative current-state model:

- `raceId`, `frameIndex`, `frame`, `prediction`, `probabilityTimeline`,
  playback — owned by `useReplay` (unchanged authority).
- `selectedDriverId` — owned by `ReplayView`, **tagged with the race it
  belongs to** (`{ raceId, driverId }`). On a race switch the derived
  selection is `null` immediately by construction (no effect, no window
  in which race A's driver could drive a race B surface). Shared by the
  Winner model panel (local explanation) and the timeline change panel.
- Timeline context checkpoint (`selectedOverride`) stays local to
  `ProbabilityTimelineChart`: it is inherently that chart's own
  inspection context, always labelled with its exact frame and paired
  with an exact `Replay frame N` navigation action (no snapping).

Gating rules that prevent drift:

- The local panel renders only when the shared selection names a driver
  observable **at the current checkpoint prediction**; otherwise nothing
  renders (no stale/foreign explanation).
- Keyed payloads (section 3) additionally guarantee a resolved payload
  renders only under the selection that produced it.

The E6 failure example cannot occur: timeline context always carries its
exact frame label, the replay frame is the single `frameIndex`, and the
explanation always carries its driver + frame identity.

## 3. Stale-request protection

- Both explanation hooks use per-request `AbortController` with
  effect-cleanup abort (superseded requests cancelled; late responses
  ignored via the `cancelled` flag).
- Both hooks store the resolved payload together with its exact
  `(race, frame, driver)` selection key and render it only while the
  key still matches the live selection — otherwise the caller fallback
  (`LOADING`). New pure helper
  `frontend/features/replay/lib/explanationSelection.ts`
  (`explanationSelectionKey` / `resolvedSelection`), unit-tested for
  race/frame/driver mismatch and empty-state fallback; a source-level
  test asserts both hooks keep the AbortController + keyed pattern and
  introduce no explanation cache.
- `useReplay` frame/prediction fetching keeps its existing request-id +
  session stale guard; `selectRace` bumps both and aborts in-flight
  frame work; race switch clears frame, prediction and timeline state.

## 4. Race-switch behavior

Verified live: switching races aborts/cancels outstanding requests,
clears the shared driver selection (race-tag derivation), resets
predictions/timeline, clears the timeline chart via `key={raceId}`, and
now lands on frame 0 instead of re-applying the previous race's
deep-linked frame. A race A explanation can never appear in race B
(keyed payloads + race-tagged selection + component remount keys).

## 5. Request efficiency

- Exactly one request per selection on every surface: predictions once
  per checkpoint (remembered per frame, known 503s never refetched),
  probability timeline once per race, local/change explanations once
  per explicit (race, frame, driver) selection.
- No duplicate-request pathology: no fetch on rerender, no prefetch of
  drivers/checkpoints/races (E4/E5 stay on-demand; both are
  ~20–45 ms, fast enough to fetch on interaction).
- **No explanation cache was introduced** (E7 gate invariant): asserted
  by unit test (`replayIntegration.test.ts`).

## 6. Loading and error semantics

Every async Phase-8 surface exposes explicit states: the prediction
view (`none` / `loading` / `hit` / `unavailable` / `error`), the local
hook (`loading` / `ready` / `unavailable` / `not_observable` / `error`),
the change hook (`idle` / `loading` / `ready` / `no_previous` /
`comparison_unavailable` / `unavailable` / `error`). Loading never
renders another frame's data (keyed guard). Error copy now names the
backend contract:

- frame: `unknown_frame` / `unknown_race` mapped specifically.
- prediction: `not_prediction_checkpoint` -> `none` (honest
  non-checkpoint state); 503 -> `unavailable` with reason; other API
  codes rendered as `Winner model unavailable ({status} {code})`.
- local: 503 -> unavailable; 422/404 -> `not_observable`.
- change: 200-body `NO_PREVIOUS_CHECKPOINT` / `COMPARISON_UNAVAILABLE`
  with reason; 503 -> unavailable; other codes rendered with status.

No Python exception internals are exposed (codes only).

## 7. Prediction-checkpoint UX and timeline interaction

- Checkpoint frames: Winner panel header `Prediction checkpoint ·
  {reasons}`; timeline shows `current frame is a checkpoint`.
- Non-checkpoint frames: Winner panel `No model checkpoint` +
  `Factual frame only — model checkpoints are sparse…`; timeline
  between-marker plus `current frame {N} is between model checkpoints
  (no current probability)` (verified live at frame 1).
- Checkpoint-details selection never snaps: `Replay frame N`
  navigates to the exact `frame_index`; a context checkpoint differing
  from the live frame stays labelled with its own frame, and the change
  view additionally prints `Exact checkpoints · frame {A} → {B}`.
- First checkpoint: change view is `NO_PREVIOUS_CHECKPOINT`
  (`first checkpoint — no previous comparison… No baseline is
  fabricated.`), a normal state, not an error.
- Unobservable/null drivers: no explanation control is offered in the
  Winner panel (non-observable rows render as text); nulls render
  `n/a`, never `0%`.

## 8. Driver-selection UX and local/change coordination

One shared `selectedDriverId`: expanding a Winner-model row selects the
explanation driver everywhere (local panel header names driver+frame;
change panel select reflects the same driver). Verified live: picking
VETTEL in the change driver select switched the local header to
`VETTEL · frame 100`. Local view = what contributes to the score now;
change view = what changed in model contribution space since the
previous checkpoint; the shared selection plus per-panel frame identity
makes the relationship explicit without surprising implicit changes.

## 9. Information hierarchy and visual separation

Preserved: race/frame control -> current race state -> winner model ->
prediction timeline -> selected-driver intelligence
(current model score -> local contributions -> change since previous
checkpoint). FACTUAL RACE DATA (running order, context bar), MODEL
PREDICTION (Winner model, timeline), MODEL EXPLANATION (local panel)
and MODEL SCORE CHANGE (change panel) remain visibly distinct panels;
factual rows and explanation evidence are never merged, implying no
causality. No visual rewrite; targeted integration edits only.

## 10. Terminology audit

UI copy uses exactly: prediction checkpoint, winner model, independent
binary, model probability, model log-odds, local contribution
(`Model log-odds — key inputs`), model score change, previous
checkpoint. Case-insensitive audit of the replay frontend finds no
`confidence`, `chance`, `share` (outside explicit `not shares`
anti-share copy), `race probability`, `AI reasoning`, `model
thinks/knows`, `probability contribution`, `win factor`, `caused`,
`because`, `due to`, `led to`, `as a result of`, `made the driver`, or
`reason … probability`. E3/E4/E5 language-contract tests pass
unchanged; the new integration tests re-assert the copy invariants.

## 11. Responsive validation

Verified live with zero page-level horizontal overflow at 1440, 1024,
768, 650, 390 and 360 (`document.scrollWidth == clientWidth` at each
width). The running-order table keeps its sanctioned single
`overflow-x-auto` container at 720px min-width (genuinely tabular
content; no nested scroll trap, no deleted columns). Contribution rows
truncate with full text in tooltips; selects/buttons wrap and stay
on-screen; chart SVG scales to its container; dense telemetry styling
is preserved at every width.

## 12. Accessibility

- Driver expansion buttons: real `<button>`, `aria-expanded`,
  visible 2px `focus-visible` outline, screen-reader `(selected)`
  state; keyboard activation verified live (Tab + Enter expands).
- Contribution direction never relies on color/arrow/position alone:
  sr-only `INCREASED/DECREASED MODEL LOG-ODDS` row prefixes, worded
  group headings, signed values, `title` tooltips.
- Chart has a text alternative (description + checkpoint-details
  `<select>` table as the interaction equivalent); legend prints
  driver ids with dash-pattern swatches (not color-only).
- Loading states use `role="status"`; errors use `role="alert"`.

## 13. Performance

Warm representative endpoints (same process serving the UI audit),
single requests:

- replay frame: ~73 ms, HTTP 200.
- probability timeline (one per race): ~3.5 ms.
- E4 local explanation: ~40 ms (E4 envelope ~20.8 ms p95).
- E5 change explanation: ~45 ms (E5 envelope ~40.8 ms p95).

All comfortably interactive; integration added no repeated matrix
loads (lazy/process-level matrix behavior untouched) and no new fetch
loops. Concurrent overlapping change/explanation requests for
different drivers return correct per-driver identities with no
cross-talk (12-request concurrency smoke: all 200, identities exact).
No Lighthouse scores are claimed (dev-server measurement would be
meaningless); before/after request counts are unchanged by design
(one request per selection on every surface, before and after).

## 14. Failure / race-condition testing

Exercised live plus unit coverage: rapid frame stepping (abort +
request-id guards), rapid driver switching (keyed guard; new unit
tests), race switch during an in-flight explanation request
(selection derives to null; payload keyed out), collapse/reopen
(remount keys), 503 cache-unavailable, 422 driver-not-observable,
first checkpoint, non-checkpoint, and timeline-context switching.
Latest selected state wins in every case; no stale response renders.

## 15. 2025 firewall

Live: `2025-r01-R` returns 404 on the replay frame (`unknown_race`),
the E4 explanation, the E5 change, and the probability timeline. The
frontend builds race choice solely from the backend-served race list
and contains no 2025 path (only a comment stating the backend
excludes it). No hidden frontend path bypasses the firewall.

## 16. Tests

- New `frontend/features/replay/lib/replayIntegration.test.ts` (11
  tests). Pure-guard tests (2): exact key identity; stored view renders
  only for the matching selection across race/frame/driver switches
  and empty state. Source-invariant tests (9): abort + keyed pattern
  in both hooks; no explanation cache;
  one race-tagged shared selection wired to both panels; no private
  panel selection; non-observable gating; checkpoint honesty copy;
  first-checkpoint + exact-frame copy; sr-only direction + worded
  headings; disclosure/focus semantics; deep-link frame reset;
  API-code error mapping.
- Full frontend `node --test`: **148 passed** (137 pre-existing + 11
  new), 0 failed.
- Backend (untouched; focused smoke): `test_v2_phase8_e3.py`,
  `test_v2_phase8_e4.py`, `test_v2_phase8_e5.py`,
  `test_v2_phase5_r4.py`, `test_v2_phase5_r6.py` -> **235 passed**.
- `tsc --noEmit` clean; `eslint` clean; `next build` success.

## 17. Files changed (E6)

Modified (frontend only):

- `frontend/features/replay/components/ReplayView.tsx` — one
  race-tagged `selectedDriverId` shared by both explanation surfaces.
- `frontend/features/replay/components/PredictionPanel.tsx` —
  controlled selection (no private state), observability gating,
  `aria-expanded`/focus/`(selected)` semantics, specific error copy.
- `frontend/features/replay/components/ProbabilityTimelineChart.tsx`
  — consumes the shared selection, `focus-visible` on the exact-frame
  action.
- `frontend/features/replay/components/LocalExplanationPanel.tsx` —
  driver+frame header identity, sr-only direction words.
- `frontend/features/replay/components/ChangeExplanationPanel.tsx` —
  sr-only delta words, worded group headings, `Exact checkpoints ·
  frame A → B` identity line, coded error copy.
- `frontend/features/replay/hooks/useReplay.ts` — deep-linked frame
  applies to first race load only; specific
  `unknown_frame`/`unknown_race`/prediction error copy.
- `frontend/features/replay/hooks/useLocalExplanation.ts`,
  `frontend/features/replay/hooks/useTimelineChange.ts` — keyed
  payload rendering + abort-on-supersede + coded errors.

Added: `frontend/features/replay/lib/explanationSelection.ts`,
`frontend/features/replay/lib/replayIntegration.test.ts`, this report.

Backend, `v2/`, `ml/`, `scripts/`, `tests/`, data and caches:
untouched by E6.

## 18. Graphify final

`graphify update .` run at E6 start (no topology changes reported) and
again after the edits; targeted checks confirm the frontend/product
integration consumes the frozen scientific modules in the existing
direction only (components/hooks -> `lib/v2` client -> API routes ->
frozen `v2/` services) with no new edges into Phase-1–7 scientific
modules and no dependency cycle. (Full graph outputs remain in
`graphify-out/`.)

## 19. Repository safety

No `git reset/restore/checkout/clean/stash/add/commit/tag` performed;
nothing staged; unrelated user processes (stale :8000 API, :3000
frontend) left untouched — E6 verification used isolated ports
(:8010 API, :3002 frontend). Audit screenshots at the repo root are
removed as part of E6 cleanup.

## 20. Known limitations

- Re-expanding the same collapsed explanation refetches on demand by
  design (E7 gate: no explanation cache introduced).
- The change-panel driver select lists all roster drivers; drivers
  without an evaluated two-point comparison resolve to an explicit
  `COMPARISON_UNAVAILABLE` reason rather than being filtered.
- Timeline context selection is intentionally per-chart state,
  labelled with its exact frame; it is not forced to equal the live
  replay frame.
- `?frame=` deep links are honored for the first loaded race only.

## 21. E7 entry gate

- [x] one coherent replay selected-state model
- [x] exact frame/checkpoint semantics preserved
- [x] race switching cannot show stale data
- [x] frame switching cannot show stale explanation
- [x] driver switching cannot show stale explanation
- [x] no duplicate-request pathology
- [x] explicit checkpoint/non-checkpoint state
- [x] first-checkpoint state correct
- [x] unavailable/null state correct
- [x] local/change explanation distinction clear
- [x] factual/prediction/explanation distinction clear
- [x] terminology consistent
- [x] no causal wording
- [x] 2025 firewall intact
- [x] 1440 responsive
- [x] 1024 responsive
- [x] 768 responsive
- [x] 650 responsive
- [x] 390 responsive
- [x] 360 responsive
- [x] keyboard/accessibility checks green
- [x] endpoint performance remains interactive
- [x] no explanation cache introduced
- [x] frontend node tests green
- [x] tsc green
- [x] eslint green
- [x] next build green
- [x] relevant backend regression green
