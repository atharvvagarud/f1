// Pure replay logic (Phase-5 R5).
//
// Deterministic, React-free helpers: navigation bounds, playback state
// machine, leader-lap search mapping, and factual formatting. The backend
// remains authoritative for anchors, reconstruction, checkpoints, and
// probabilities — nothing here recreates those semantics.

import type { ReplayFrameResponse } from "@/lib/v2";

export const PLAYBACK_SPEEDS = [0.5, 1, 2, 4] as const;
export type PlaybackSpeed = (typeof PLAYBACK_SPEEDS)[number];

/** Base client interval at 1x: one factual frame per 500 ms (R5-L). */
export const BASE_INTERVAL_MS = 500;

export const intervalForSpeed = (speed: PlaybackSpeed): number =>
  Math.round(BASE_INTERVAL_MS / speed);

// --- navigation (0-based API identity; display converts to 1-based) ---

export const firstIndex = (): number => 0;

export const lastIndex = (totalFrames: number): number => totalFrames - 1;

export const previousIndex = (index: number): number =>
  Math.max(0, index - 1);

export const nextIndex = (index: number, totalFrames: number): number =>
  Math.min(totalFrames - 1, index + 1);

export const canGoPrevious = (index: number): boolean => index > 0;

export const canGoNext = (index: number, totalFrames: number): boolean =>
  index < totalFrames - 1;

export const displayFrame = (index: number): number => index + 1;

// --- playback state machine (client-owned; server never pushes) ---

export type PlaybackStatus = "paused" | "playing";

export type PlaybackState = {
  status: PlaybackStatus;
  speed: PlaybackSpeed;
  index: number;
  totalFrames: number;
};

export type PlaybackAction =
  | { type: "play" }
  | { type: "pause" }
  | { type: "setSpeed"; speed: PlaybackSpeed }
  | { type: "seek"; index: number }
  | { type: "tick" }
  | { type: "reset"; totalFrames: number };

export function playbackReducer(
  state: PlaybackState,
  action: PlaybackAction,
): PlaybackState {
  switch (action.type) {
    case "play":
      // At the last frame there is nothing to advance to: stay paused.
      if (!canGoNext(state.index, state.totalFrames)) return state;
      return { ...state, status: "playing" };
    case "pause":
      return { ...state, status: "paused" };
    case "setSpeed":
      return { ...state, speed: action.speed };
    case "seek":
      // Manual navigation pauses deterministically (R5-K).
      return {
        ...state,
        status: "paused",
        index: Math.max(0, Math.min(state.totalFrames - 1, action.index)),
      };
    case "tick": {
      if (state.status !== "playing") return state;
      if (!canGoNext(state.index, state.totalFrames)) {
        return { ...state, status: "paused" }; // auto-pause at end, no wrap
      }
      return { ...state, index: state.index + 1 };
    }
    case "reset":
      return { status: "paused", speed: state.speed, index: 0, totalFrames: action.totalFrames };
  }
}

// --- leader-lap jump mapping (client-side, frame metadata only) ---
//
// R4 exposes no jump endpoint; the frame response carries the factual
// leader lap, monotone non-decreasing along served timelines. Binary
// search over probed (frameIndex -> leaderLap) entries finds the first
// frame with leader progress >= lap without reconstructing every frame.
// Null/unknown laps abort the jump loudly instead of guessing.

export type LapProbe = { frameIndex: number; leaderLap: number | null };

/** Next probe index for the search, or {done, found} when resolved. */
export function leaderLapSearchStep(
  probes: LapProbe[],
  totalFrames: number,
  lap: number,
): { done: false; probe: number } | { done: true; found: number | null } {
  if (!Number.isInteger(lap) || lap < 1) return { done: true, found: null };
  const known = new Map(probes.map((p) => [p.frameIndex, p.leaderLap]));
  if ([...known.values()].some((v) => v === null)) {
    return { done: true, found: null }; // unknown lap: abort, never guess
  }
  let low = 0;
  let high = totalFrames - 1;
  let hit: number | null = null;
  // Narrow using known probes only; unknown spans need probing.
  const valueAt = (i: number): number | undefined =>
    (known.get(i) ?? undefined) as number | undefined;
  while (low <= high) {
    const mid = Math.floor((low + high) / 2);
    const value = valueAt(mid);
    if (value === undefined) return { done: false, probe: mid };
    if (value < lap) {
      low = mid + 1;
    } else {
      hit = mid;
      high = mid - 1;
    }
  }
  // Verify the low boundary is probed (monotonicity guard needs it).
  if (valueAt(low) === undefined && low < totalFrames) {
    return { done: false, probe: low };
  }
  return { done: true, found: hit };
}

// --- stale-response guard ---
//
// A response belongs to the active navigation only if both its session
// (race selection) and its request generation (frame navigation) still
// match. Older responses are dropped rather than applied, so a late
// prediction/probability payload can never overwrite newer state or
// surface under another race/frame.

export function isCurrentResponse(
  requestId: number,
  currentRequestId: number,
  session: number,
  currentSession: number,
): boolean {
  return session === currentSession && requestId === currentRequestId;
}

// --- bounded insertion-ordered cache eviction ---
//
// Deterministic oldest-first eviction for the replay frame cache: a Map
// preserves insertion order, so deleting from the front keeps the cache
// within its declared bound (natural served-race size). Entries are never
// reordered by reads, so eviction is stable across requests.

export function evictOldest<K, V>(cache: Map<K, V>, limit: number): void {
  while (cache.size > limit) {
    const oldest = cache.keys().next();
    if (oldest.done) break;
    cache.delete(oldest.value);
  }
}

// --- timeline helpers ---

/** Sort key for served races: chronological (season, round, race_id). */
export function compareRaces(
  a: { season: number; round_no: number; race_id: string },
  b: { season: number; round_no: number; race_id: string },
): number {
  return (
    a.season - b.season || a.round_no - b.round_no ||
    (a.race_id < b.race_id ? -1 : a.race_id > b.race_id ? 1 : 0)
  );
}

// --- factual formatting (display only; values pass through verbatim) ---

export function formatGapSeconds(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return `+${value.toFixed(3)}`;
}

export function formatLap(value: number | null): string {
  if (value === null) return "—";
  return `L${value}`;
}

/** Historical T as m:ss.mmm (factual metadata, never mutated). */
export function formatRaceTime(totalSeconds: number | null): string {
  if (totalSeconds === null || !Number.isFinite(totalSeconds)) return "—";
  const sign = totalSeconds < 0 ? "-" : "";
  const abs = Math.abs(totalSeconds);
  const minutes = Math.floor(abs / 60);
  const seconds = (abs - minutes * 60).toFixed(3).padStart(6, "0");
  return `${sign}${minutes}:${seconds}`;
}

export function formatAge(age_s: number | null): string {
  if (age_s === null || !Number.isFinite(age_s)) return "";
  if (age_s < 0.5) return "live";
  return `stale ${age_s.toFixed(1)}s`;
}

/** Probability as percent text; null stays null (never 0%). */
export function formatProbability(value: number | null): string | null {
  if (value === null || !Number.isFinite(value)) return null;
  return `${(value * 100).toFixed(2)}%`;
}

/** Verbatim aggregate; >100% is valid under INDEPENDENT_BINARY. */
export function sumProbabilities(values: (number | null)[]): number {
  return values.reduce<number>(
    (acc, v) => acc + (typeof v === "number" && Number.isFinite(v) ? v : 0),
    0,
  );
}

export function driverStatusOf(driver: {
  observable: boolean;
  observation_age_s: number | null;
}): "observed" | "stale" | "unobserved" {
  if (!driver.observable) return "unobserved";
  if (
    driver.observation_age_s !== null &&
    Number.isFinite(driver.observation_age_s) &&
    driver.observation_age_s >= 0.5
  ) {
    return "stale";
  }
  return "observed";
}

export type FrameIdentity = { raceId: string; frameIndex: number };

export function frameIdentityOf(response: ReplayFrameResponse): FrameIdentity {
  return {
    raceId: response.frame.race_id,
    frameIndex: response.frame.frame_index,
  };
}
