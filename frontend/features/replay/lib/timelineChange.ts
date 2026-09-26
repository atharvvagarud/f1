// Pure display transforms for E5 prediction-change explanations (no DOM, no
// network).
//
// Language contract (mirrors the backend): feature rows are additive
// MODEL LOG-ODDS contribution changes. They are never win-probability
// increments and the overall probability delta is never decomposed per
// feature. The only percentage-point number shown is the overall model
// prediction change.

import type {
  DriverProbabilitySeries,
  ProbabilityCheckpoint,
  ProbabilityTimelineResponse,
  TimelineChangeAccounting,
  TimelineChangeResponse,
} from "@/lib/v2";

//: Signed, fixed-precision model log-odds formatting (change view).
export function formatLogOdds(value: number): string {
  if (!Number.isFinite(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}`;
}

//: PRESENTATIONAL ONLY. Classification of a displayed arrow; it never changes
//: the scientific payload (which retains exact values).
export const NEUTRAL_DISPLAY_TOLERANCE = 1e-9;

export type ProbabilityChange = {
  from: number | null;
  to: number | null;
  delta: number | null;
};

/** Nearest REAL checkpoint strictly before `frameIndex` (never snapping). */
export function previousCheckpoint(
  timeline: ProbabilityTimelineResponse,
  frameIndex: number,
): ProbabilityCheckpoint | null {
  let candidate: ProbabilityCheckpoint | null = null;
  for (const checkpoint of timeline.checkpoints) {
    if (checkpoint.frame_index < frameIndex) candidate = checkpoint;
    else break;
  }
  return candidate;
}

function seriesFor(
  timeline: ProbabilityTimelineResponse,
  driverId: string,
): DriverProbabilitySeries | undefined {
  return timeline.driver_series.find((s) => s.driver_id === driverId);
}

function valueAt(
  series: DriverProbabilitySeries,
  frameIndex: number,
): number | null {
  const point = series.points.find((p) => p.frame_index === frameIndex);
  return point ? point.winner_probability : null;
}

/**
 * Overall model-prediction change for one driver between the previous REAL
 * checkpoint and the selected checkpoint. Nulls are preserved (never 0).
 */
export function probabilityChange(
  timeline: ProbabilityTimelineResponse,
  driverId: string,
  frameIndex: number,
): ProbabilityChange {
  const previous = previousCheckpoint(timeline, frameIndex);
  if (previous === null) return { from: null, to: null, delta: null };
  const series = seriesFor(timeline, driverId);
  if (series === undefined) return { from: null, to: null, delta: null };
  const from = valueAt(series, previous.frame_index);
  const to = valueAt(series, frameIndex);
  return {
    from,
    to,
    delta: from !== null && to !== null ? to - from : null,
  };
}

/** First driver with an evaluated probability at the checkpoint (display). */
export function defaultChangeDriver(
  timeline: ProbabilityTimelineResponse,
  frameIndex: number,
): string | null {
  for (const series of timeline.driver_series) {
    if (valueAt(series, frameIndex) !== null) return series.driver_id;
  }
  return null;
}

export function formatProbabilityPercent(value: number | null): string | null {
  if (value === null || !Number.isFinite(value)) return null;
  return `${(value * 100).toFixed(1)}%`;
}

/** Overall model-prediction change, in percentage points (never per feature). */
export function formatPercentagePoints(value: number | null): string | null {
  if (value === null || !Number.isFinite(value)) return null;
  const sign = value > 0 ? "+" : "";
  return `${sign}${(value * 100).toFixed(1)}pp`;
}

export function deltaArrow(delta: number): string {
  if (!Number.isFinite(delta)) return "\u00b7";
  if (delta > NEUTRAL_DISPLAY_TOLERANCE) return "\u2191";
  if (delta < -NEUTRAL_DISPLAY_TOLERANCE) return "\u2193";
  return "\u00b7";
}

export function deltaWord(delta: number): string {
  if (delta > NEUTRAL_DISPLAY_TOLERANCE) return "INCREASED MODEL LOG-ODDS";
  if (delta < -NEUTRAL_DISPLAY_TOLERANCE) return "DECREASED MODEL LOG-ODDS";
  return "NEUTRAL";
}

export function transitionMarker(transition: string): string | null {
  if (transition === "IMPUTATION_TRANSITION") return "IMPUTED";
  if (transition === "MISSINGNESS_TRANSITION") return "MISSING";
  if (transition === "CATEGORICAL_TRANSITION") return "CATEGORY";
  if (transition === "INPUT_STATE_CHANGED") return "STATE";
  return null;
}

export function changeOmittedNote(
  accounting: TimelineChangeAccounting,
): string {
  return (
    `Top ${accounting.top_n} changes shown; omitted ` +
    `${formatLogOdds(accounting.omitted_positive_log_odds_delta)} positive / ` +
    `${formatLogOdds(accounting.omitted_negative_log_odds_delta)} negative ` +
    `log-odds deltas. The full canonical change vector reconstructs the ` +
    `log-odds delta; the top list does not.`
  );
}

export function changeResidualWithinTolerance(
  change: TimelineChangeResponse,
): boolean {
  if (change.reconstruction === null) return false;
  return (
    Math.abs(change.reconstruction.residual) <=
    change.reconstruction.logit_abs_tolerance
  );
}
