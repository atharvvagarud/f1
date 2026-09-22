// Probability timeline transforms + SVG chart geometry (Phase-5 R6).
//
// React-free, deterministic helpers over the R6 `ProbabilityTimelineResponse`.
// The backend is authoritative: these functions never invent observations,
// never resample, never normalize, and never substitute a neighbouring
// checkpoint's probability for the current frame. A null probability is a
// real gap: series segments break rather than plotting zero.
//
// Scientific grain is (driver_id, ACTUAL checkpoint). X positions are the
// checkpoint ordinal (rendering-only spacing); tooltips carry the exact
// frame index / historical T / leader lap. Connecting lines are visual only.

import type {
  DriverProbabilitySeries,
  ProbabilityCheckpoint,
  ProbabilityTimelineResponse,
} from "@/lib/v2";

// --- checkpoint lookup ---

export function checkpointAt(
  timeline: ProbabilityTimelineResponse,
  frameIndex: number,
): ProbabilityCheckpoint | null {
  return (
    timeline.checkpoints.find((c) => c.frame_index === frameIndex) ?? null
  );
}

export function checkpointOrdinal(
  timeline: ProbabilityTimelineResponse,
  frameIndex: number,
): number {
  return timeline.checkpoints.findIndex((c) => c.frame_index === frameIndex);
}

export function isActualCheckpoint(
  timeline: ProbabilityTimelineResponse,
  frameIndex: number,
): boolean {
  return checkpointOrdinal(timeline, frameIndex) >= 0;
}

/** Highest raw probability per driver across actually-evaluated points. */
export function driverPeakProbabilities(
  timeline: ProbabilityTimelineResponse,
): Map<string, number> {
  const peaks = new Map<string, number>();
  for (const series of timeline.driver_series) {
    let peak = Number.NEGATIVE_INFINITY;
    for (const point of series.points) {
      if (point.winner_probability !== null) {
        peak = Math.max(peak, point.winner_probability);
      }
    }
    peaks.set(series.driver_id, peak === Number.NEGATIVE_INFINITY ? 0 : peak);
  }
  return peaks;
}

/**
 * Deterministic default display filter: top `n` drivers by peak raw
 * probability, ties broken by driver_id ascending. Display filter ONLY —
 * the complete series stays available.
 */
export function defaultVisibleDrivers(
  timeline: ProbabilityTimelineResponse,
  n = 5,
): string[] {
  const peaks = driverPeakProbabilities(timeline);
  return [...timeline.driver_series]
    .map((s) => s.driver_id)
    .sort((a, b) => {
      const diff = (peaks.get(b) ?? 0) - (peaks.get(a) ?? 0);
      return diff !== 0 ? diff : a < b ? -1 : a > b ? 1 : 0;
    })
    .slice(0, n);
}

/** One driver's probability at one ACTUAL checkpoint, or null (no fill). */
export function probabilityAtCheckpoint(
  series: DriverProbabilitySeries,
  frameIndex: number,
): number | null {
  const point = series.points.find((p) => p.frame_index === frameIndex);
  return point ? point.winner_probability : null;
}

// --- current-frame alignment (never presents past as current) ---

export type FrameAlignment =
  | {
      kind: "checkpoint";
      ordinal: number;
      checkpoint: ProbabilityCheckpoint;
      markerX: number;
    }
  | {
      kind: "between";
      previousOrdinal: number;
      nextOrdinal: number;
      fraction: number;
      previous: ProbabilityCheckpoint;
      next: ProbabilityCheckpoint;
      markerX: number;
    }
  | { kind: "before_first"; nextOrdinal: number; markerX: number }
  | { kind: "after_last"; previousOrdinal: number; markerX: number }
  | { kind: "none"; markerX: null };

export function currentFrameAlignment(
  timeline: ProbabilityTimelineResponse,
  frameIndex: number,
): FrameAlignment {
  const checkpoints = timeline.checkpoints;
  if (checkpoints.length === 0) return { kind: "none", markerX: null };
  const exact = checkpoints.findIndex((c) => c.frame_index === frameIndex);
  if (exact >= 0) {
    return {
      kind: "checkpoint",
      ordinal: exact,
      checkpoint: checkpoints[exact],
      markerX: exact,
    };
  }
  const nextIndex = checkpoints.findIndex((c) => c.frame_index > frameIndex);
  if (nextIndex === 0) {
    return { kind: "before_first", nextOrdinal: 0, markerX: 0 };
  }
  if (nextIndex < 0) {
    const previousOrdinal = checkpoints.length - 1;
    return {
      kind: "after_last",
      previousOrdinal,
      markerX: previousOrdinal,
    };
  }
  const previousOrdinal = nextIndex - 1;
  const previous = checkpoints[previousOrdinal];
  const next = checkpoints[nextIndex];
  const span = next.frame_index - previous.frame_index;
  const fraction =
    span > 0
      ? Math.max(0, Math.min(1, (frameIndex - previous.frame_index) / span))
      : 0;
  return {
    kind: "between",
    previousOrdinal,
    nextOrdinal: nextIndex,
    fraction,
    previous,
    next,
    markerX: previousOrdinal + fraction,
  };
}

// --- series styling (non-colour differentiation; UI3) ---
//
// A small categorical set of dash patterns so series stay distinguishable
// without relying on hue alone. The legend also prints the driver id, so a
// series is never identified by colour only. `undefined` means a solid line.

const SERIES_DASH_PATTERNS: readonly (string | undefined)[] = [
  undefined,
  "7 3",
  "2 3",
  "9 3 2 3",
  "4 2",
];

/** Deterministic dash pattern for the nth visible series (0 = solid). */
export function seriesDashPattern(index: number): string | undefined {
  if (!Number.isFinite(index) || index < 0) return undefined;
  return SERIES_DASH_PATTERNS[index % SERIES_DASH_PATTERNS.length];
}

/**
 * Chart height tracks the measured container width so SVG labels keep their
 * intended pixel size instead of shrinking with a scaled viewBox.
 */
export function chartHeightForWidth(width: number): number {
  if (!Number.isFinite(width) || width <= 0) return 200;
  return Math.round(Math.min(300, Math.max(200, width * 0.5)));
}

// --- SVG geometry (rendering only; raw values, no normalization) ---

export type ChartPadding = {
  left: number;
  right: number;
  top: number;
  bottom: number;
};

export type ChartPoint = {
  x: number;
  y: number;
  frameIndex: number;
  stateTimeS: number;
  leaderLap: number | null;
  probability: number;
};

export type ChartSeries = {
  driverId: string;
  segments: ChartPoint[][];
};

export type ChartXTick = { x: number; label: string; frameIndex: number };
export type ChartYTick = { y: number; label: string; value: number };

export type ChartGeometry = {
  width: number;
  height: number;
  padding: ChartPadding;
  plot: { x: number; y: number; width: number; height: number };
  xMax: number;
  yMax: number;
  xTicks: ChartXTick[];
  yTicks: ChartYTick[];
  series: ChartSeries[];
};

const DEFAULT_PADDING: ChartPadding = {
  left: 44,
  right: 12,
  top: 12,
  bottom: 26,
};

/**
 * Build SVG geometry for the visible drivers. Y uses the raw probability
 * scale (values may exceed 1.0 — INDEPENDENT_BINARY is never renormalized).
 * Null probabilities break the line: no point is emitted for them.
 */
export function buildChartGeometry(
  timeline: ProbabilityTimelineResponse,
  visibleDriverIds: string[],
  dims: { width: number; height: number; padding?: Partial<ChartPadding> },
): ChartGeometry {
  const padding = { ...DEFAULT_PADDING, ...(dims.padding ?? {}) };
  const plot = {
    x: padding.left,
    y: padding.top,
    width: Math.max(1, dims.width - padding.left - padding.right),
    height: Math.max(1, dims.height - padding.top - padding.bottom),
  };
  const checkpointCount = timeline.checkpoints.length;
  const xMax = Math.max(1, checkpointCount - 1);

  let rawMax = 1;
  const visible = new Set(visibleDriverIds);
  for (const series of timeline.driver_series) {
    if (!visible.has(series.driver_id)) continue;
    for (const point of series.points) {
      if (point.winner_probability !== null) {
        rawMax = Math.max(rawMax, point.winner_probability);
      }
    }
  }
  const yMax = rawMax * 1.05;

  const xScale = (ordinal: number): number =>
    plot.x + (xMax === 0 ? 0 : (ordinal / xMax) * plot.width);
  const yScale = (value: number): number =>
    plot.y + plot.height - (value / yMax) * plot.height;

  const checkpointOrdinals = new Map<number, number>();
  timeline.checkpoints.forEach((c, i) => checkpointOrdinals.set(c.frame_index, i));

  const series: ChartSeries[] = [];
  for (const s of timeline.driver_series) {
    if (!visible.has(s.driver_id)) continue;
    const segments: ChartPoint[][] = [];
    let current: ChartPoint[] = [];
    for (const point of s.points) {
      const ordinal = checkpointOrdinals.get(point.frame_index);
      if (ordinal === undefined) continue; // absent checkpoint: never invented
      if (point.winner_probability === null) {
        if (current.length > 0) segments.push(current);
        current = [];
        continue;
      }
      current.push({
        x: xScale(ordinal),
        y: yScale(point.winner_probability),
        frameIndex: point.frame_index,
        stateTimeS: point.state_time_s,
        leaderLap: point.leader_lap,
        probability: point.winner_probability,
      });
    }
    if (current.length > 0) segments.push(current);
    series.push({ driverId: s.driver_id, segments });
  }

  const xTicks: ChartXTick[] = [];
  const tickCount = Math.min(8, checkpointCount);
  for (let i = 0; i < tickCount; i++) {
    const ordinal =
      tickCount === 1 ? 0 : Math.round((i / (tickCount - 1)) * xMax);
    const checkpoint = timeline.checkpoints[ordinal];
    xTicks.push({
      x: xScale(ordinal),
      label:
        checkpoint.leader_lap !== null
          ? `L${checkpoint.leader_lap}`
          : `#${checkpoint.frame_index}`,
      frameIndex: checkpoint.frame_index,
    });
  }

  const yTicks: ChartYTick[] = [];
  const ySteps = 4;
  for (let i = 0; i <= ySteps; i++) {
    const value = (yMax * i) / ySteps;
    yTicks.push({
      y: yScale(value),
      label: `${(value * 100).toFixed(0)}%`,
      value,
    });
  }

  return {
    width: dims.width,
    height: dims.height,
    padding,
    plot,
    xMax,
    yMax,
    xTicks,
    yTicks,
    series,
  };
}
