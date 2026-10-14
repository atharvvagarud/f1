// Causal driver-telemetry selectors (V3.10F).
//
// Historical lap/sector/stint evidence for the workspace-selected driver,
// sliced by the replay clock T (anchor_state_time_s). Every selector takes
// T explicitly and returns ONLY evidence with observedAt <= T; UI components
// receive selector output alone, never the full corpus, so future evidence
// cannot reach render even though one race-scoped response is cached.
//
// Causal rules (audited in results/v3/v3_10f/telemetry_source_audit.json):
// - COMPLETED LAPS ONLY. A lap's final lap_time/S1/S2/S3 become visible
//   together when the lap row's observedAtS <= T (the replay frame grid IS
//   the state_time_s grid). Partial-sector (IN_LAP) evidence is not exposed.
// - REFERENCE: the driver's best (minimum) lap_time among completed laps
//   with a recorded time, excluding FastF1-generated synthetic rows
//   (SOURCE_METADATA, safe). Deleted status is POST_RACE and MUST NOT
//   filter the reference; pit/SC-affected laps are NOT excluded (a pit lap
//   can never be the minimum; documented limitation). No future-derived
//   baseline, ever.
// - Deltas are descriptive ("S1 +0.112 vs best LAP n"), never qualitative.
// - Missing stays null, rendered as em-dash, never zero-filled.
// - Stints: COMPLETED (end observed <= T) show full range; ACTIVE (started,
//   not completed) shows only causally-known facts; future stints hidden
//   entirely — including their count.
// - In-progress lap: LAP (maxCompleted+1) with values unavailable, shown
//   only while the replay advances and the driver is within a lap of the
//   leader; otherwise an explicit unavailable state (no retirement
//   inference — retirements have no causal signal).
//
// This module is value-import-free (type-only imports erase under
// `node --test` type-stripping) so every rule below is unit-tested
// dependency-free, including the mandatory future-data poison tests.

import type { TelemetryResponse } from "@/lib/v2";

/** One completed-lap evidence row (verbatim server projection). */
export interface TelemetryLap {
  driverId: string;
  lapNumber: number;
  observedAtS: number;
  lapTimeS: number | null;
  sector1S: number | null;
  sector2S: number | null;
  sector3S: number | null;
  compound: string | null;
  stintNumber: number | null;
  pitEntry: boolean | null;
  pitExit: boolean | null;
  generated: boolean | null;
}

/** One stint evidence row (verbatim server projection). */
export interface TelemetryStint {
  driverId: string;
  stintNumber: number;
  compound: string | null;
  startLap: number | null;
  endLap: number | null;
  startObservedAtS: number | null;
  endObservedAtS: number | null;
}

/** Full-race cached corpus (never passed to UI components directly). */
export interface TelemetryCorpus {
  raceId: string;
  laps: TelemetryLap[];
  stints: TelemetryStint[];
}

/** Adapt the wire response once per race (verbatim rename, no slicing). */
export function adaptTelemetryResponse(
  body: TelemetryResponse,
): TelemetryCorpus {
  return {
    raceId: body.race_id,
    laps: body.laps.map((lap) => ({
      driverId: lap.driver_id,
      lapNumber: lap.lap_number,
      observedAtS: lap.observed_at_s,
      lapTimeS: lap.lap_time_s,
      sector1S: lap.sector_1_s,
      sector2S: lap.sector_2_s,
      sector3S: lap.sector_3_s,
      compound: lap.compound,
      stintNumber: lap.stint_number,
      pitEntry: lap.pit_entry,
      pitExit: lap.pit_exit,
      generated: lap.fastf1_generated,
    })),
    stints: body.stints.map((stint) => ({
      driverId: stint.driver_id,
      stintNumber: stint.stint_number,
      compound: stint.compound,
      startLap: stint.start_lap,
      endLap: stint.end_lap,
      startObservedAtS: stint.start_observed_at_s,
      endObservedAtS: stint.end_observed_at_s,
    })),
  };
}

export interface LapDelta {
  lapS: number | null;
  sector1S: number | null;
  sector2S: number | null;
  sector3S: number | null;
}

export interface ReferenceLap {
  lapNumber: number;
  lapTimeS: number;
}

export type CurrentLapState =
  | { kind: "in-progress"; lapNumber: number }
  | { kind: "no-new-lap"; lastCompletedLap: number | null }
  | { kind: "replay-end" }
  | { kind: "no-evidence" };

export interface CompletedStintView {
  kind: "completed";
  stintNumber: number;
  compound: string | null;
  startLap: number | null;
  endLap: number | null;
  lapCount: number | null;
}

export interface ActiveStintView {
  kind: "active";
  stintNumber: number;
  /** Causal current compound from the frame state (never backfilled). */
  compound: string | null;
  startLap: number | null;
  /** Stint age: laps observed in this stint up to T (1-based). */
  stintAgeLaps: number | null;
}

export interface StintHistoryView {
  completed: CompletedStintView[];
  active: ActiveStintView | null;
  activeUnknown: boolean;
}

/**
 * Completed laps for one driver known by T (observedAtS <= T), ascending.
 * The ONLY lap-history entry point for UI.
 */
export function selectCompletedDriverLaps(
  corpus: TelemetryCorpus,
  driverId: string,
  tS: number,
): TelemetryLap[] {
  const out: TelemetryLap[] = [];
  for (const lap of corpus.laps) {
    if (lap.driverId !== driverId) continue;
    if (!Number.isFinite(lap.observedAtS) || lap.observedAtS > tS) continue;
    out.push(lap);
  }
  out.sort((a, b) =>
    a.observedAtS === b.observedAtS
      ? a.lapNumber - b.lapNumber
      : a.observedAtS - b.observedAtS,
  );
  return out;
}

/**
 * Reference definition (V3.10F §9): best (minimum) recorded lap_time among
 * the driver's completed laps with observedAtS <= T, excluding
 * FastF1-generated synthetic rows. Ties resolve to the earliest lap.
 * Returns null when no eligible lap exists. Deleted laps are NOT excluded
 * (POST_RACE knowledge would leak the future); pit/SC laps are NOT
 * excluded (documented limitation — deltas stay descriptive).
 */
export function selectReferenceLap(
  completed: readonly TelemetryLap[],
): ReferenceLap | null {
  let best: ReferenceLap | null = null;
  for (const lap of completed) {
    if (lap.lapTimeS === null || !Number.isFinite(lap.lapTimeS)) continue;
    if (lap.generated === true) continue;
    if (
      best === null ||
      lap.lapTimeS < best.lapTimeS ||
      (lap.lapTimeS === best.lapTimeS && lap.lapNumber < best.lapNumber)
    ) {
      best = { lapNumber: lap.lapNumber, lapTimeS: lap.lapTimeS };
    }
  }
  return best;
}

/** Last N completed laps (window into the <=T slice only). */
export function selectRecentLaps(
  completed: readonly TelemetryLap[],
  count: number,
): TelemetryLap[] {
  if (count <= 0) return [];
  return completed.slice(Math.max(0, completed.length - count));
}

function diffOrNull(value: number | null, ref: number | null): number | null {
  if (value === null || ref === null) return null;
  if (!Number.isFinite(value) || !Number.isFinite(ref)) return null;
  return value - ref;
}

/** Descriptive deltas of one lap vs the reference lap's sectors. */
export function lapDeltaVsReference(
  lap: TelemetryLap,
  reference: ReferenceLap | null,
  completed: readonly TelemetryLap[],
): LapDelta {
  if (reference === null) {
    return { lapS: null, sector1S: null, sector2S: null, sector3S: null };
  }
  let refLap: TelemetryLap | null = null;
  for (const candidate of completed) {
    if (candidate.lapNumber === reference.lapNumber) {
      refLap = candidate;
      break;
    }
  }
  if (refLap === null) {
    return { lapS: null, sector1S: null, sector2S: null, sector3S: null };
  }
  return {
    lapS: diffOrNull(lap.lapTimeS, refLap.lapTimeS),
    sector1S: diffOrNull(lap.sector1S, refLap.sector1S),
    sector2S: diffOrNull(lap.sector2S, refLap.sector2S),
    sector3S: diffOrNull(lap.sector3S, refLap.sector3S),
  };
}

/**
 * Current-lap state without retirement inference. maxCompletedLap is the
 * driver's highest completed lap number at T; leaderLap is the frame's
 * leader lap (null when unknown); raceComplete is true only at the final
 * replay frame; hasFrameEvidence is false when the driver is absent from
 * the frame roster (selection kept, §16).
 */
export function selectCurrentLapState(args: {
  maxCompletedLap: number | null;
  leaderLap: number | null;
  raceComplete: boolean;
  hasFrameEvidence: boolean;
}): CurrentLapState {
  if (!args.hasFrameEvidence) return { kind: "no-evidence" };
  if (args.raceComplete) return { kind: "replay-end" };
  if (args.maxCompletedLap === null) {
    // No completed lap observed yet: LAP 1 is genuinely in progress once
    // the race has started (leader lap observed); otherwise unavailable.
    if (args.leaderLap !== null && args.leaderLap >= 1) {
      return { kind: "in-progress", lapNumber: 1 };
    }
    return { kind: "no-new-lap", lastCompletedLap: null };
  }
  // Within a lap of the leader -> the next lap is credibly in progress.
  // Further behind (or leader unknown but race advancing) -> state the
  // gap explicitly instead of asserting progress.
  if (args.leaderLap === null) {
    return { kind: "in-progress", lapNumber: args.maxCompletedLap + 1 };
  }
  if (args.maxCompletedLap >= args.leaderLap - 1) {
    return { kind: "in-progress", lapNumber: args.maxCompletedLap + 1 };
  }
  return { kind: "no-new-lap", lastCompletedLap: args.maxCompletedLap };
}

/**
 * Stint history: completed stints (end observed <= T) plus the active
 * stint (started, not completed), all for one driver. Future stints —
 * including their count — never appear. The active stint's compound comes
 * from the causal frame state (currentCompound, may be null -> UNKNOWN);
 * entity compounds are used ONLY for completed stints.
 */
export function selectStintHistory(
  corpus: TelemetryCorpus,
  driverId: string,
  tS: number,
  currentCompound: string | null,
  frameStintNumber: number | null,
  observedLap: number | null,
): StintHistoryView {
  const completed: CompletedStintView[] = [];
  let active: ActiveStintView | null = null;
  let startedUncompleted = false;

  for (const stint of corpus.stints) {
    if (stint.driverId !== driverId) continue;
    const startKnown =
      stint.startObservedAtS !== null && stint.startObservedAtS <= tS;
    const endKnown =
      stint.endObservedAtS !== null && stint.endObservedAtS <= tS;
    if (endKnown) {
      completed.push({
        kind: "completed",
        stintNumber: stint.stintNumber,
        compound: stint.compound,
        startLap: stint.startLap,
        endLap: stint.endLap,
        lapCount:
          stint.startLap !== null && stint.endLap !== null
            ? stint.endLap - stint.startLap + 1
            : null,
      });
      continue;
    }
    if (!startKnown) continue;
    // Started but not completed by T: candidate active stint. The frame
    // state's stint identity is authoritative at T (pit-transition
    // ambiguity stays explicit via activeUnknown).
    startedUncompleted = true;
    if (frameStintNumber !== null && stint.stintNumber !== frameStintNumber) {
      continue;
    }
    if (frameStintNumber === null) {
      continue;
    }
    const startLap = stint.startLap;
    active = {
      kind: "active",
      stintNumber: stint.stintNumber,
      compound: currentCompound,
      startLap,
      stintAgeLaps:
        startLap !== null && observedLap !== null && observedLap >= startLap
          ? observedLap - startLap + 1
          : null,
    };
  }

  completed.sort((a, b) => a.stintNumber - b.stintNumber);
  // No frame stint identity while stints are underway (pit-transition
  // window or null frame state): ambiguity stays explicit.
  if (frameStintNumber === null) {
    if (completed.length > 0 || startedUncompleted) {
      return { completed, active: null, activeUnknown: true };
    }
    return { completed, active: null, activeUnknown: false };
  }
  // Frame reports a stint the entity cannot place causally (e.g. start row
  // missing): surface frame facts alone, explicitly partial.
  if (active === null && frameStintNumber !== null) {
    const started = corpus.stints.some(
      (s) =>
        s.driverId === driverId &&
        s.stintNumber === frameStintNumber &&
        s.startObservedAtS !== null &&
        s.startObservedAtS <= tS,
    );
    if (!started) {
      const endKnownElsewhere = corpus.stints.some(
        (s) =>
          s.driverId === driverId &&
          s.stintNumber === frameStintNumber &&
          s.endObservedAtS !== null &&
          s.endObservedAtS <= tS,
      );
      if (!endKnownElsewhere) {
        active = {
          kind: "active",
          stintNumber: frameStintNumber,
          compound: currentCompound,
          startLap: null,
          stintAgeLaps: null,
        };
      }
    }
  }
  return { completed, active, activeUnknown: false };
}

/** Format seconds as M:SS.mmm (lap) — null stays null, never zero-filled. */
export function formatLapTime(value: number | null): string | null {
  if (value === null || !Number.isFinite(value) || value < 0) return null;
  const totalMillis = Math.round(value * 1000);
  const minutes = Math.floor(totalMillis / 60000);
  const seconds = Math.floor((totalMillis - minutes * 60000) / 1000);
  const millis = totalMillis - minutes * 60000 - seconds * 1000;
  return `${minutes}:${String(seconds).padStart(2, "0")}.${String(millis).padStart(3, "0")}`;
}

/** Format seconds as SS.sss (sector) — null stays null. */
export function formatSectorTime(value: number | null): string | null {
  if (value === null || !Number.isFinite(value) || value < 0) return null;
  return value.toFixed(3);
}

/** Format a signed delta as +0.123 / -0.123 — null stays null. */
export function formatDelta(value: number | null): string | null {
  if (value === null || !Number.isFinite(value)) return null;
  const rounded = Math.round(value * 1000) / 1000;
  if (rounded === 0) return "+0.000";
  const sign = rounded > 0 ? "+" : "-";
  return `${sign}${Math.abs(rounded).toFixed(3)}`;
}
