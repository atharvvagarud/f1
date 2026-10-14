// Replay adapter boundary (V3.10B §14).
//
// The canonical store does NOT drive ReplayView yet (deferred migration is
// documented below). This module is the validated boundary both sides must
// go through: every canonical -> replay translation is validated FIRST, so
// the existing replay clamp path (showFrame clamps into range) can only ever
// receive pre-validated input and never silently repair anything.
//
// Dependency direction (per §34 graph check): this adapter may depend on the
// workspace core; the workspace core depends on nothing. The adapter does NOT
// import replay internals — replay stays the owner of fetching/playback until
// V3.10C/D migrates it onto the store.
//
// Deferred migration (explicit, V3.10C/D owns):
//   1. useReplay raceId/frameIndex subscribe to WorkspaceProvider state.
//   2. ReplayView local race-tagged selection becomes a workspace consumer.
//   3. TimelineScrubber/PlaybackControls emit workspace SEEK_FRAME.
// Until then: two authorities exist ONLY under this adapter rule —
// canonical state is translated, validated, and handed to the existing
// replay calls; replay behavior is otherwise unchanged.

// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { seekFrame, setRace, type WorkspaceResult, type WorkspaceState } from "./workspaceState.ts";

/** Exact input the existing replay navigation calls accept. */
export interface ReplaySelection {
  raceId: string;
  frameIndex: number;
}

/** Canonical -> replay translation (identity mapping; validation separate). */
export function toReplaySelection(state: WorkspaceState): ReplaySelection {
  return { raceId: state.raceId, frameIndex: state.frameIndex };
}

/**
 * Adapter rule: validate a canonical seek against the known frame domain
 * BEFORE delegating to replay navigation. Rejects (never clamps) when the
 * domain is known; defers range validation when totalFrames is unknown
 * (timeline not loaded) — the replay fetch then fails explicitly per frame.
 */
export function validateSeekForReplay(
  state: WorkspaceState,
  frameIndex: number,
  totalFrames: number | null,
): WorkspaceResult {
  return seekFrame(state, frameIndex, totalFrames);
}

/**
 * Adapter rule: race entry always resolves the workspace start frame
 * (first supported frame; see WORKSPACE_START_FRAME). Callers pass the new
 * race roster when known so driver carry-over is provably safe; otherwise
 * the selection clears (fail-closed).
 */
export function validateRaceEntryForReplay(
  prev: WorkspaceState | null,
  raceId: string,
  roster: readonly string[] | null = null,
): WorkspaceResult {
  return setRace(prev, raceId, roster);
}

/**
 * Race-tag scoping for driver highlight/selection, mirroring the validated
 * SpatialTrackPanel pattern (spatialSelectionForRace): a selection belonging
 * to another race derives to null — never highlights, never explains.
 * Re-implemented (not imported) to keep the workspace core dependency-free.
 */
export function scopeDriverForRace(
  selectedDriverId: string | null,
  selectionRaceId: string | null,
  raceId: string,
): string | null {
  if (selectedDriverId === null) return null;
  return selectionRaceId === raceId ? selectedDriverId : null;
}

/**
 * Timeline primitive contract (§23): the future timeline is a pure function
 * of (canonical frameIndex, valid domain) -> exact seekFrame. No visual
 * timeline changes in B; existing replay timeline stays visually unchanged.
 */
export function timelineSeek(
  state: WorkspaceState,
  frameIndex: number,
  totalFrames: number | null,
): WorkspaceResult {
  return validateSeekForReplay(state, frameIndex, totalFrames);
}

/**
 * Event-navigation primitive (§22): future event objects resolve to an exact
 * frameIndex and flow through this single entry point. No event objects, no
 * event-derived state in B — the primitive only.
 */
export function eventSeek(
  state: WorkspaceState,
  frameIndex: number,
  totalFrames: number | null,
): WorkspaceResult {
  return validateSeekForReplay(state, frameIndex, totalFrames);
}
