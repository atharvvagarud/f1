// Canonical URL serialization contract for workspace state (V3.10B §10).
//
//   race=<raceId>&frame=<frameIndex>[&driver=<driverId>]
//
// Extends the existing validated replay convention (?race=&frame=, see
// useReplay.readInitialUrl) with an optional driver. Strict by design:
// deterministic output, typed parsing, malformed input fails safely with a
// typed error — never throws, never snaps to a nearest state.

// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { isValidFrameIndex, isValidRaceId, type WorkspaceResult, type WorkspaceState } from "./workspaceState.ts";

export const WORKSPACE_URL_PARAMS = ["race", "frame", "driver"] as const;

/** Deterministic serialization. Key order fixed: race, frame, driver. */
export function serializeWorkspace(state: WorkspaceState): string {
  const params = new URLSearchParams();
  params.set("race", state.raceId);
  params.set("frame", String(state.frameIndex));
  if (state.selectedDriverId !== null) {
    params.set("driver", state.selectedDriverId);
  }
  return params.toString();
}

function malformed(message: string): WorkspaceResult {
  return {
    ok: false,
    error: { code: "MALFORMED_URL", message },
  };
}

/**
 * Strict parse of a query string ("?race=X&frame=1" or "race=X&frame=1").
 * race + frame required; driver optional (absent or empty -> null).
 * Frame must be all-digits; anything else is MALFORMED_URL, never coerced.
 */
export function parseWorkspaceSearch(search: string): WorkspaceResult {
  let params: URLSearchParams;
  try {
    const stripped = search.startsWith("?") ? search.slice(1) : search;
    params = new URLSearchParams(stripped);
  } catch {
    return malformed(`Unparseable workspace query: ${search}.`);
  }
  const race = params.get("race");
  const rawFrame = params.get("frame");
  const rawDriver = params.get("driver");
  if (!isValidRaceId(race)) {
    return malformed("Workspace query requires a non-empty race parameter.");
  }
  if (rawFrame === null || !/^\d+$/.test(rawFrame)) {
    return malformed(
      `Workspace query requires an exact non-negative integer frame parameter, got: ${String(rawFrame)}.`,
    );
  }
  const frameIndex = parseInt(rawFrame, 10);
  if (!isValidFrameIndex(frameIndex)) {
    return malformed(
      `Workspace query frame out of range: ${String(rawFrame)}.`,
    );
  }
  const selectedDriverId =
    rawDriver !== null && rawDriver.trim().length > 0 ? rawDriver : null;
  return { ok: true, state: { raceId: race, frameIndex, selectedDriverId } };
}

/**
 * HYDRATE_FROM_URL: strict parse with no silent snapping. Extra unknown
 * parameters are ignored (forward-compatible); missing/invalid race or frame
 * yields a typed failure the caller renders explicitly.
 */
export function hydrateFromUrl(search: string): WorkspaceResult {
  return parseWorkspaceSearch(search);
}
