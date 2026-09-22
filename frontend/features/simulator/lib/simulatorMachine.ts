// Simulator pure logic (Phase-6 R8).
//
// React-free, deterministic helpers for the Monte Carlo simulator surface.
// The backend owns the science: this module never normalizes probabilities,
// never recreates anchors, and never invents an unsupported state's outcome.
// It only maps a selected replay frame to an exact anchor, guards result
// identity, sorts the aggregate for display, and formats numbers.

import type {
  ReplayFrameMeta,
  SimulationAnchor,
  SimulationErrorBody,
  SimulationResponse,
} from "@/lib/v2";

/** Bounded synchronous options surfaced to the user (R8-G/H). */
export const SIMULATION_COUNTS = [1000, 10000] as const;
export type SimulationCount = (typeof SIMULATION_COUNTS)[number];
export const DEFAULT_SIMULATION_COUNT: SimulationCount = 1000;

/** Exact anchor from a frozen replay frame (R8-E); never re-derived. */
export function anchorFromFrame(frame: ReplayFrameMeta): SimulationAnchor {
  return {
    race_id: frame.race_id,
    anchor_driver_id: frame.anchor_driver_id,
    anchor_lap_number: frame.anchor_lap_number,
    anchor_state_time_s: frame.anchor_state_time_s,
  };
}

/** Deterministic default state: the middle replay frame (mid-race). */
export function defaultFrameIndex(totalFrames: number): number {
  if (totalFrames <= 0) return 0;
  return Math.floor((totalFrames - 1) / 2);
}

export function clampFrameIndex(index: number, totalFrames: number): number {
  if (totalFrames <= 0) return 0;
  if (!Number.isFinite(index)) return 0;
  return Math.max(0, Math.min(totalFrames - 1, Math.trunc(index)));
}

export function anchorKey(anchor: SimulationAnchor, count: number): string {
  return [
    anchor.race_id,
    anchor.anchor_driver_id,
    anchor.anchor_lap_number,
    anchor.anchor_state_time_s,
    count,
  ].join("|");
}

/**
 * A response belongs to the exact selected state and count. If the user
 * changes race/lap/count, the previous result must not be shown (R8-Z).
 */
export function responseMatchesSelection(
  response: SimulationResponse,
  anchor: SimulationAnchor,
  count: number,
): boolean {
  return (
    response.race_id === anchor.race_id &&
    response.anchor_driver_id === anchor.anchor_driver_id &&
    response.anchor_lap_number === anchor.anchor_lap_number &&
    response.anchor_state_time_s === anchor.anchor_state_time_s &&
    response.requested_simulation_count === count
  );
}

/** Stale-response guard: session = state selection, requestId = run. */
export function isCurrentSimulationResponse(
  requestId: number,
  currentRequestId: number,
  session: number,
  currentSession: number,
): boolean {
  return session === currentSession && requestId === currentRequestId;
}

/** Deterministic display order: win probability desc, driver_id asc. */
export function sortDriversByWin(
  drivers: SimulationResponse["drivers"],
): SimulationResponse["drivers"] {
  return [...drivers].sort(
    (a, b) =>
      b.win_probability - a.win_probability ||
      (a.driver_id < b.driver_id ? -1 : a.driver_id > b.driver_id ? 1 : 0),
  );
}

/** Deterministic distribution order: expected finish asc, driver_id asc. */
export function sortDriversByExpectedFinish(
  drivers: SimulationResponse["drivers"],
): SimulationResponse["drivers"] {
  return [...drivers].sort(
    (a, b) =>
      a.expected_finish - b.expected_finish ||
      (a.driver_id < b.driver_id ? -1 : a.driver_id > b.driver_id ? 1 : 0),
  );
}

/** Most frequent simulated winner (the head of the deterministic win order). */
export function mostFrequentWinner(
  drivers: SimulationResponse["drivers"],
): SimulationResponse["drivers"][number] | null {
  return sortDriversByWin(drivers)[0] ?? null;
}

/**
 * Ordered finishing-position columns present in the aggregate. Actual
 * positions only — never an interpolated or invented position. A null
 * position (contract-allowed) sorts last when the backend returns one.
 */
export function distributionPositions(
  drivers: SimulationResponse["drivers"],
): (number | null)[] {
  const positions = new Set<number>();
  let hasNull = false;
  for (const driver of drivers) {
    for (const bucket of driver.finish_position_distribution) {
      if (bucket.position === null) hasNull = true;
      else positions.add(bucket.position);
    }
  }
  const ordered = [...positions].sort((a, b) => a - b);
  return hasNull ? [...ordered, null] : ordered;
}

/** Discrete neutral intensity step for a frequency (0 = no simulated outcome). */
export function distributionLevel(frequency: number): 0 | 1 | 2 | 3 {
  if (!Number.isFinite(frequency) || frequency <= 0) return 0;
  if (frequency < 0.05) return 1;
  if (frequency < 0.2) return 2;
  return 3;
}

/**
 * Matrix cell text: the empirical percentage (1 dp), `<0.1` when a non-zero
 * frequency rounds below display precision, blank exactly at zero. The value
 * is always text; the intensity step is redundant reinforcement, not meaning.
 */
export function formatDistributionCell(frequency: number): string {
  if (!Number.isFinite(frequency) || frequency <= 0) return "";
  const percent = frequency * 100;
  if (percent < 0.05) return "<0.1";
  return percent.toFixed(1);
}

/** Verbatim aggregate; never a share, never normalized. */
export function winMass(drivers: SimulationResponse["drivers"]): number {
  return drivers.reduce((acc, d) => acc + d.win_probability, 0);
}

export function formatPercent(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export function formatExpectedFinish(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return value.toFixed(2);
}

export function formatCount(value: number): string {
  return value.toLocaleString("en-US");
}

/** A human string for the response runtime, seconds. */
export function formatRuntime(seconds: number | null): string {
  if (seconds === null || !Number.isFinite(seconds)) return "—";
  return `${seconds.toFixed(2)} s`;
}

/**
 * Factual unsupported-state message. For a non-contemporaneous roster this
 * must never claim a driver retired (runtime does not know that at T).
 */
export function unsupportedMessage(body: SimulationErrorBody): string {
  if (body.reason === "non_contemporaneous_roster_member") {
    return (
      "This historical state cannot be simulated safely because the " +
      "complete field cannot be established contemporaneously at this " +
      "point in the race."
    );
  }
  const detail = body.detail ? ` ${body.detail}` : "";
  return `This historical state cannot be simulated. Reason: ${
    body.reason ?? body.error
  }.${detail}`;
}
