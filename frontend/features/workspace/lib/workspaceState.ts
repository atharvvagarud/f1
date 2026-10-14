// Canonical pit-wall workspace state — pure typed core (V3.10B).
//
// Identity model (V3.10A contract):
//   raceId + frameIndex   canonical race/replay identity (exact frame, no interpolation)
//   selectedDriverId      optional driver identity, always interpreted within raceId
//
// This module is deliberately framework-free and side-effect-free: no React,
// no fetch, no science/eligibility logic, no presentation state. React binding
// lives in hooks/useWorkspace.tsx; URL codec in workspaceUrl.ts. Pure core
// keeps every transition unit-testable with dependency-free `node --test`.

/** Canonical workspace identity. Exactly these keys — see WORKSPACE_STATE_KEYS. */
export interface WorkspaceState {
  raceId: string;
  frameIndex: number;
  selectedDriverId: string | null;
}

export type WorkspaceErrorCode =
  | "INVALID_RACE"
  | "INVALID_FRAME"
  | "INVALID_DRIVER"
  | "MALFORMED_URL"
  | "UNKNOWN_RACE";

export interface WorkspaceError {
  code: WorkspaceErrorCode;
  message: string;
}

export type WorkspaceResult =
  | { ok: true; state: WorkspaceState }
  | { ok: false; error: WorkspaceError };

/**
 * Start-frame rule (V3.10B §21): entering a race resolves to the first
 * supported frame. Matches the validated useReplay.selectRace behavior
 * (reset to frame 0; deep-linked ?frame= applies to the first race only).
 * No future-data optimization of the starting frame.
 */
export const WORKSPACE_START_FRAME = 0;

/**
 * Exact key set of the canonical scientific workspace state. Presentation
 * state (drawerOpen, activeTab, hoveredDriver, tableSort, …) must never be
 * added here — see V3.10B §24.
 */
export const WORKSPACE_STATE_KEYS = [
  "raceId",
  "frameIndex",
  "selectedDriverId",
] as const;

export type WorkspaceTransitionKind =
  | "SET_RACE"
  | "SEEK_FRAME"
  | "SELECT_DRIVER"
  | "CLEAR_DRIVER"
  | "HYDRATE";

export function isValidRaceId(value: unknown): value is string {
  return typeof value === "string" && value.trim().length > 0;
}

export function isValidFrameIndex(value: unknown): value is number {
  return (
    typeof value === "number" &&
    Number.isInteger(value) &&
    value >= WORKSPACE_START_FRAME
  );
}

function invalid(
  code: WorkspaceErrorCode,
  message: string,
): { ok: false; error: WorkspaceError } {
  return { ok: false, error: { code, message } };
}

/**
 * SET_RACE: validates race, resolves the explicit start frame, and
 * validates/clears the driver. A driver survives a race change ONLY when the
 * caller supplies a roster for the new race that contains it; otherwise the
 * selection clears (fail-closed: race-A identity must never coexist with
 * race-B identity). Pass roster=null when membership is unknown.
 */
export function setRace(
  prev: WorkspaceState | null,
  raceId: string,
  roster: readonly string[] | null = null,
): WorkspaceResult {
  if (!isValidRaceId(raceId)) {
    return invalid("INVALID_RACE", `Invalid race identity: ${String(raceId)}.`);
  }
  const carried =
    prev !== null &&
    prev.selectedDriverId !== null &&
    roster !== null &&
    roster.includes(prev.selectedDriverId)
      ? prev.selectedDriverId
      : null;
  return {
    ok: true,
    state: {
      raceId,
      frameIndex: WORKSPACE_START_FRAME,
      selectedDriverId: carried,
    },
  };
}

/**
 * SEEK_FRAME: same race, exact valid frame only, preserves the driver.
 * Out-of-range requests are REJECTED — never clamped, never snapped to
 * nearest (the replay showFrame clamp path must only ever receive
 * pre-validated input via the workspace adapter). When totalFrames is null
 * (domain not yet loaded) only integer>=0 shape is enforced; range validation
 * is deferred to the adapter at request time and documented there.
 */
export function seekFrame(
  prev: WorkspaceState,
  frameIndex: number,
  totalFrames: number | null = null,
): WorkspaceResult {
  if (!isValidFrameIndex(frameIndex)) {
    return invalid(
      "INVALID_FRAME",
      `Invalid frame index: ${String(frameIndex)}. Exact frame required.`,
    );
  }
  if (
    totalFrames !== null &&
    (!Number.isInteger(totalFrames) ||
      totalFrames <= 0 ||
      frameIndex >= totalFrames)
  ) {
    return invalid(
      "INVALID_FRAME",
      `Frame ${frameIndex} is outside the valid domain [0, ${totalFrames}). No snapping applied.`,
    );
  }
  return {
    ok: true,
    state: { ...prev, frameIndex },
  };
}

/**
 * SELECT_DRIVER: exact driver identity within the current race. Unknown
 * membership (roster=null) is accepted — identity and evidence are separate
 * concerns (§16): a selected driver with no evidence at the current frame
 * renders as unavailable, never as a different driver. Known-nonmember
 * (roster supplied, absent) is rejected; nothing is ever auto-substituted.
 */
export function selectDriver(
  prev: WorkspaceState,
  driverId: string,
  roster: readonly string[] | null = null,
): WorkspaceResult {
  if (typeof driverId !== "string" || driverId.trim().length === 0) {
    return invalid(
      "INVALID_DRIVER",
      `Invalid driver identity: ${String(driverId)}.`,
    );
  }
  if (roster !== null && !roster.includes(driverId)) {
    return invalid(
      "INVALID_DRIVER",
      `Driver ${driverId} is not valid for race ${prev.raceId}. Selection unchanged.`,
    );
  }
  return { ok: true, state: { ...prev, selectedDriverId: driverId } };
}

/** CLEAR_DRIVER: selectedDriverId -> null. Always succeeds. */
export function clearDriver(prev: WorkspaceState): WorkspaceState {
  return { ...prev, selectedDriverId: null };
}

export type DriverEvidenceStatus =
  | "selected-with-evidence"
  | "selected-no-evidence"
  | "unknown-domain";

/**
 * Distinguishes "selected driver exists but has no evidence at this frame"
 * from invalid identity (§16). Identity invalidation happens ONLY on race
 * change (setRace); per-frame roster absence never mutates the selection.
 */
export function resolveDriverEvidence(
  selectedDriverId: string,
  rosterAtFrame: readonly string[] | null,
): DriverEvidenceStatus {
  if (rosterAtFrame === null) return "unknown-domain";
  return rosterAtFrame.includes(selectedDriverId)
    ? "selected-with-evidence"
    : "selected-no-evidence";
}

export type HistoryAction = "push" | "replace" | "none";

/**
 * Browser-history semantics (§13): transient replay progression replaces
 * (never grows history); intentional race selection pushes; hydration from
 * the URL itself writes nothing (the URL is already the source).
 */
export function historyActionFor(
  transition: WorkspaceTransitionKind,
): HistoryAction {
  switch (transition) {
    case "SET_RACE":
      return "push";
    case "HYDRATE":
      return "none";
    case "SEEK_FRAME":
    case "SELECT_DRIVER":
    case "CLEAR_DRIVER":
      return "replace";
  }
}

/**
 * Type guard for the canonical state shape (used at trust boundaries).
 * Driver is optional-but-nullable: absent key is malformed, explicit null ok.
 */
export function isWorkspaceState(value: unknown): value is WorkspaceState {
  if (typeof value !== "object" || value === null) return false;
  const v = value as Record<string, unknown>;
  return (
    isValidRaceId(v.raceId) &&
    isValidFrameIndex(v.frameIndex) &&
    (v.selectedDriverId === null || isValidRaceId(v.selectedDriverId)) &&
    Object.keys(v).every((k) =>
      (WORKSPACE_STATE_KEYS as readonly string[]).includes(k),
    )
  );
}
