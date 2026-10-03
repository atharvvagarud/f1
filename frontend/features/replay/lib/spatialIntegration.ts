// Spatial replay-integration guards (Phase-12 P12-7).
//
// Pure predicates shared by the replay integration hook and its contract
// tests. The hook owns AbortControllers and React state; every admission
// decision (race identity, frame identity, clock agreement, selection
// scope) lives here so `node --test` covers the exact logic the UI runs —
// no DOM, no network, no duplication.
//
// One-clock rule: the only replay position is the existing
// currentFrameIndex. These helpers never derive an index from lap, time,
// or slider percentage; they only check that a spatial response matches
// the already-authoritative (race_id, frame_index) pair.

import type { SpatialFrame, SpatialGeometry } from "@/lib/spatial";
// Runtime import is explicitly relative with a .ts extension: the contract
// tests execute this module dependency-free under `node --test`
// type-stripping, where the `@/` alias does not resolve (same pattern as
// the existing *.test.ts files; tsc suppression below is targeted).
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { SpatialApiError, geometryMatchesFrame } from "../../../lib/spatial.ts";

/** Frontend cache key. Race ALWAYS participates: never frame_index alone. */
export function spatialFrameCacheKey(
  raceId: string,
  frameIndex: number,
): string {
  return `${raceId}|${frameIndex}`;
}

/**
 * Latest-wins generation tracker. `issue` stamps every outgoing spatial
 * request; `isCurrent` admits only the newest ticket for its scope.
 * Out-of-order arrivals (102, 100, 101) resolve to 102 and nothing else.
 */
export function createSpatialRequestTracker(): {
  issue: (raceId: string, frameIndex: number) => {
    generation: number;
    raceId: string;
    frameIndex: number;
  };
  isCurrent: (ticket: {
    generation: number;
    raceId: string;
    frameIndex: number;
  }) => boolean;
} {
  let generation = 0;
  let latest: {
    generation: number;
    raceId: string;
    frameIndex: number;
  } | null = null;
  return {
    issue: (raceId, frameIndex) => {
      generation += 1;
      latest = { generation, raceId, frameIndex };
      return latest;
    },
    isCurrent: (ticket) => latest !== null && ticket.generation === latest.generation,
  };
}

/**
 * Admission check for an arrived spatial frame: it must name the exact
 * requested race AND the exact requested frame index. A stale-but-valid
 * response (older frame, previous race) is discarded, never rendered.
 */
export function isSpatialResponseCurrent(
  response: Pick<SpatialFrame, "race_id" | "frame_index">,
  raceId: string,
  frameIndex: number,
): boolean {
  return response.race_id === raceId && response.frame_index === frameIndex;
}

/**
 * Replay/spatial clock agreement. P12-4 resolves spatial state at the
 * frozen replay clock (T = anchor_state_time_s); the backend echoes that T
 * as query_time_s. Exact comparison — no rounding, no frontend time
 * recomputation.
 */
export function isSpatialClockConsistent(
  anchorStateTimeS: number,
  frame: Pick<SpatialFrame, "query_time_s">,
): boolean {
  return (
    Number.isFinite(anchorStateTimeS) && frame.query_time_s === anchorStateTimeS
  );
}

/**
 * Full render gate: identity + clock + geometry match. Markers render only
 * when every check passes; any failure withholds them (never stale data
 * presented as current).
 */
export function canRenderSpatialFrame(
  geometry: SpatialGeometry,
  frame: SpatialFrame,
  raceId: string,
  frameIndex: number,
  anchorStateTimeS: number,
): boolean {
  return (
    isSpatialResponseCurrent(frame, raceId, frameIndex) &&
    isSpatialClockConsistent(anchorStateTimeS, frame) &&
    geometryMatchesFrame(geometry, frame)
  );
}

/**
 * Selection scope for the renderer highlight. The existing replay
 * selection is already race-tagged; this is belt-and-braces: a selection
 * belonging to another race never highlights a marker here.
 */
export function spatialSelectionForRace(
  selectedDriverId: string | null,
  selectionRaceId: string | null,
  spatialRaceId: string,
): string | null {
  if (selectedDriverId === null) return null;
  return selectionRaceId === spatialRaceId ? selectedDriverId : null;
}

export type SpatialFailureKind = "aborted" | "unavailable" | "error";

/**
 * Failure routing. Aborts are silent (a newer request won). A 404
 * spatial_unavailable is the expected "no servable state" outcome (e.g.
 * 2024-r09-R): isolated panel state, never a replay-page failure.
 * Everything else is a panel-scoped error with recovery on next nav.
 */
export function classifySpatialFailure(err: unknown): SpatialFailureKind {
  if (err instanceof DOMException && err.name === "AbortError") {
    return "aborted";
  }
  if (err instanceof SpatialApiError && err.isUnavailable()) {
    return "unavailable";
  }
  return "error";
}
