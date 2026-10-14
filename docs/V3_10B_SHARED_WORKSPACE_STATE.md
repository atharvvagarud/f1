# V3.10B — Shared Replay / Workspace State Architecture

Architecture stage. No UI redesign, no navigation simplification, no
telemetry panels, no race-control feed UI, no MC2 coverage work.

- V3.9 freeze: commit `fb0d8d8772bdc1343bc6be6c5ff9ee68cddd7203`, tag
  `v3.9-uncertainty-intelligence` (HEAD matches; verified + Python guard).
- V3.10A intact: `docs/V3_10A_PIT_WALL_INFORMATION_ARCHITECTURE.md` +
  `results/v3/v3_10a/` untouched (pinned by guard test).
- Canonical state: `WorkspaceState { raceId, frameIndex, selectedDriverId }`.
- Frontend: 433/433 pass (386 baseline + 47 new), tsc clean, eslint clean,
  production build prerenders all 11 routes.
- Python: 5179 collected (5176 baseline + 3 guards), guards pass.
- Git: no commit, no tag, no push.

## 1. Problem proved

`results/v3/v3_10b/current_state_ownership.json` records six independent
race/frame identities (replay, simulator, strategy, counterfactuals) plus two
fixed-anchor isolates (consensus, uncertainty) plus the codeless home page.
Zero shared owners. Selecting race/frame/driver on Replay propagates nowhere.

## 2. Canonical type

`frontend/features/workspace/lib/workspaceState.ts` — pure, framework-free,
zero imports:

```ts
interface WorkspaceState { raceId: string; frameIndex: number; selectedDriverId: string | null }
```

Exactly three keys (`WORKSPACE_STATE_KEYS`). No strategy action, no
counterfactual plan, no probability source, no telemetry metric, no layout
state. Presentation state (drawerOpen, activeTab, hoveredDriver, tableSort,
detailsExpanded, …) is excluded by type and pinned by integrity tests.

- Race identity: non-empty string. Frame: integer ≥ 0, exact discrete frame,
  no interpolation. Driver: null or non-empty string, always interpreted
  within `raceId`.
- Race change is fail-closed: the driver carries over ONLY when the caller
  supplies a new-race roster containing it; otherwise null. Race-A identity
  can never silently coexist with race-B identity.
- Frame is authoritative: lap / timestamp / session time / leader lap are
  derived from the frame downstream, never stored as competing clocks.
- Evidence ≠ identity: a selected driver with no data at the current frame
  stays selected (`selected-no-evidence`); panels render unavailable, never
  auto-substitute. Only race change affects identity.

## 3. Transitions (§20)

- `SET_RACE`: validates race → resolves `WORKSPACE_START_FRAME = 0` (first
  supported frame; matches validated `useReplay.selectRace` reset) →
  validates/clears driver.
- `SEEK_FRAME`: same race, exact frame only, preserves driver. Out-of-range
  rejected (`INVALID_FRAME`) — never clamped, never snapped. Unknown domain
  (`totalFrames: null`) enforces integer shape; range defers to the adapter.
- `SELECT_DRIVER`: exact identity; empty rejected; known-nonmember rejected
  (`INVALID_DRIVER`, caller state untouched); unknown membership accepted.
- `CLEAR_DRIVER`: → null, always succeeds.
- `HYDRATE_FROM_URL`: strict parse, no silent repair.
- History: `SET_RACE` → push; `SEEK/SELECT/CLEAR` → replace; `HYDRATE` →
  none. Playback can never flood history.

## 4. URL contract (§10–13)

`race=<raceId>&frame=<frameIndex>[&driver=<driverId>]`, fixed key order.
Extends the validated replay convention (`?race=&frame=`) with an optional
driver. Strict typed parse; malformed → `MALFORMED_URL`, never throw, never
snap. Unknown params ignored.

Ownership: URL initializes workspace state exactly once on mount
(client-only effect; SSR renders idle null so hydration matches). Afterwards
workspace transitions update the URL through one path; the URL is never
re-read, so no bidirectional loop exists. Sync effect no-ops when the live
URL already equals the serialized state. Reload resolves identically
(tested twice-equal). Malformed deep links record `initError` and stay idle —
the app never crashes on bad query params.

## 5. React binding (§9)

`frontend/features/workspace/hooks/useWorkspace.tsx`:
`WorkspaceProvider` + `useWorkspace()`. Context over the pure core with a
synchronous ref mirror (so operations return accurate success booleans in
the same tick). No Redux/Zustand/store dependency. Mounted once in
`AppShell` with zero visual change; `useWorkspace` throws outside the
provider (loud failure, never silent fork). The provider issues zero
requests — identity only, no science fetching.

## 6. Replay adapter (§14)

`frontend/features/workspace/lib/replayAdapter.ts` is the validated boundary.
ReplayView is deliberately NOT rewired in B; `useReplay` still owns
fetching/playback and its write-mostly URL sync is retained. Every canonical
→ replay translation is validated first, so the existing `showFrame` clamp
can only ever receive pre-validated input. Driver scoping mirrors the
validated `spatialSelectionForRace` pattern (re-implemented to keep the core
dependency-free). Timeline (`timelineSeek`) and event (`eventSeek`)
primitives resolve to exact seeks; no event objects, no visual timeline
changes in B. Deferred migration (V3.10C/D): subscribe `useReplay` to the
store, make `ReplayView` selection a consumer, emit workspace seeks from
transport controls.

## 7. Deep links (§19)

`workspaceDeepLink(route, state)` carries full canonical identity to
`/replay /simulator /strategy /counterfactuals /consensus /uncertainty`.
Adoption is honest: replay consumes race+frame today; every other route
records explicit deferred adoption in `ROUTE_WORKSPACE_ADOPTION`. Helpers
emit full identity forward-compatibly.

## 8. Boundaries held

- No science requests introduced (pinned: no `fetch`, no MC2/prediction/
  strategy imports anywhere in the substrate).
- No eligibility logic in the store; valid workspace + unsupported science
  stays valid.
- Identity-only state object: nothing future-bearing, no prefetch, no leak
  surface.
- No `/pit-wall`, no nav change, no route removed, no heavy dependency.
- Start frame is first supported frame — no future-data optimization.

## 9. Tests

47 focused frontend tests (state transitions, URL codec, deep links,
adapter, structural integrity) + 3 Python guards (substrate files, V3.10A
intact, V3.9 provenance). Full suite 433/433. `tsc` clean, `eslint` clean,
`next build` clean (all 11 routes).

## 10. Artifacts

`results/v3/v3_10b/`: current_state_ownership, workspace_state_contract,
url_state_contract, transition_contract, replay_adapter_audit,
driver_selection_validation, reload/history/deep-link/causal/compatibility/
performance validations, validation, product_card. This doc.

## 11. Classification

**A. SHARED_WORKSPACE_STATE_VALIDATED.** Next gate: V3.10C — Pit Wall shell
+ navigation simplification.
