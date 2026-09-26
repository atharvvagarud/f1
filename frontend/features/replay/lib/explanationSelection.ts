// Stale-selection guard for on-demand explanation state (Phase-8 E6).
//
// Both explanation hooks (E4 local, E5 change) store the resolved payload
// together with the exact (race, frame, driver) selection key that produced
// it. Rendering is allowed only when the stored key still matches the current
// selection; otherwise the caller's fallback state (LOADING) is returned. A
// late or superseded response therefore can never appear under a newer
// selection. React-free and deterministic so it is unit-testable.

export type SelectionKeyed<T> = {
  key: string;
  view: T;
};

/** Exact selection identity; race/frame/driver can never collide. */
export function explanationSelectionKey(
  raceId: string,
  frameIndex: number,
  driverId: string,
): string {
  return `${raceId}|${frameIndex}|${driverId}`;
}

/**
 * The stored view is authoritative only for the selection that produced it.
 * A mismatch (or no stored payload yet) resolves to `fallback`.
 */
export function resolvedSelection<T>(
  state: SelectionKeyed<T> | null,
  key: string,
  fallback: T,
): T {
  return state !== null && state.key === key ? state.view : fallback;
}
