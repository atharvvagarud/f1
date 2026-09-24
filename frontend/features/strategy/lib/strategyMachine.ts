// Strategy pure logic (Phase-7 S7).
//
// React-free, deterministic helpers for the strategy comparison surface. The
// backend owns the science: this module never invents a candidate, never
// re-derives an anchor, never normalizes probabilities, and never phrases a
// recommendation. It only catalogues the canonical candidate set, guards
// result identity, classifies workload, and formats numbers.

import type {
  ReplayFrameMeta,
  SimulationAnchor,
  StrategyAction,
  StrategyCandidateSelection,
  StrategyCompareResponse,
  StrategyCompound,
  StrategyObjective,
} from "@/lib/v2";

export const STRATEGY_COUNTS = [1000, 10000] as const;
export type StrategyCount = (typeof STRATEGY_COUNTS)[number];
export const DEFAULT_STRATEGY_COUNT: StrategyCount = 1000;

export const STRATEGY_OBJECTIVES: StrategyObjective[] = [
  "MAXIMIZE_WIN_PROBABILITY",
  "MAXIMIZE_PODIUM_PROBABILITY",
  "MINIMIZE_EXPECTED_FINISH",
];
export const DEFAULT_STRATEGY_OBJECTIVE: StrategyObjective =
  "MAXIMIZE_WIN_PROBABILITY";

export const OBJECTIVE_LABELS: Record<StrategyObjective, string> = {
  MAXIMIZE_WIN_PROBABILITY: "Maximize win probability",
  MAXIMIZE_PODIUM_PROBABILITY: "Maximize podium probability",
  MINIMIZE_EXPECTED_FINISH: "Minimize expected finish",
};

export type CandidateSpec = {
  key: string;
  action: StrategyAction;
  requested_compound: StrategyCompound | null;
  group: "STAY OUT" | "PIT NOW" | "PIT NEXT LAP";
  label: string;
};

/** Canonical 9-candidate grid in canonical order (never a ranking). */
export const CANONICAL_CANDIDATES: CandidateSpec[] = [
  { key: "STAY_OUT:SAMPLED", action: "STAY_OUT", requested_compound: null, group: "STAY OUT", label: "Stay out" },
  { key: "PIT_NOW:SAMPLED", action: "PIT_NOW", requested_compound: null, group: "PIT NOW", label: "Pit now · sampled compound" },
  { key: "PIT_NOW:SOFT", action: "PIT_NOW", requested_compound: "SOFT", group: "PIT NOW", label: "Pit now · soft" },
  { key: "PIT_NOW:MEDIUM", action: "PIT_NOW", requested_compound: "MEDIUM", group: "PIT NOW", label: "Pit now · medium" },
  { key: "PIT_NOW:HARD", action: "PIT_NOW", requested_compound: "HARD", group: "PIT NOW", label: "Pit now · hard" },
  { key: "PIT_NEXT_LAP:SAMPLED", action: "PIT_NEXT_LAP", requested_compound: null, group: "PIT NEXT LAP", label: "Pit next lap · sampled compound" },
  { key: "PIT_NEXT_LAP:SOFT", action: "PIT_NEXT_LAP", requested_compound: "SOFT", group: "PIT NEXT LAP", label: "Pit next lap · soft" },
  { key: "PIT_NEXT_LAP:MEDIUM", action: "PIT_NEXT_LAP", requested_compound: "MEDIUM", group: "PIT NEXT LAP", label: "Pit next lap · medium" },
  { key: "PIT_NEXT_LAP:HARD", action: "PIT_NEXT_LAP", requested_compound: "HARD", group: "PIT NEXT LAP", label: "Pit next lap · hard" },
];

/**
 * Neutral default selection (product coverage, never performance): stay out,
 * immediate pit with sampled compound, immediate pit with an explicit
 * compound example, delayed pit with sampled compound.
 */
export const DEFAULT_CANDIDATE_KEYS = [
  "STAY_OUT:SAMPLED",
  "PIT_NOW:SAMPLED",
  "PIT_NOW:MEDIUM",
  "PIT_NEXT_LAP:SAMPLED",
];

export const MAX_CANDIDATES_AT_10K = 3;

export function candidateKey(spec: StrategyCandidateSelection): string {
  return `${spec.action}:${spec.requested_compound ?? "SAMPLED"}`;
}

export function specsForKeys(keys: string[]): StrategyCandidateSelection[] {
  const byKey = new Map(CANONICAL_CANDIDATES.map((c) => [c.key, c]));
  return keys.map((key) => {
    const spec = byKey.get(key);
    if (!spec) throw new Error(`Unknown strategy candidate ${key}`);
    return {
      action: spec.action,
      requested_compound: spec.requested_compound,
    };
  });
}

/** Exact anchor from a frozen replay frame; never re-derived. */
export function strategyAnchorFromFrame(
  frame: ReplayFrameMeta,
): SimulationAnchor {
  return {
    race_id: frame.race_id,
    anchor_driver_id: frame.anchor_driver_id,
    anchor_lap_number: frame.anchor_lap_number,
    anchor_state_time_s: frame.anchor_state_time_s,
  };
}

export function defaultStrategyFrameIndex(totalFrames: number): number {
  if (totalFrames <= 0) return 0;
  return Math.floor((totalFrames - 1) / 2);
}

export function clampStrategyFrameIndex(
  index: number,
  totalFrames: number,
): number {
  if (totalFrames <= 0) return 0;
  if (!Number.isFinite(index)) return 0;
  return Math.max(0, Math.min(totalFrames - 1, Math.trunc(index)));
}

/** Full request identity a result is bound to (stale-result protection). */
export function strategyRequestKey(parts: {
  anchor: SimulationAnchor;
  target: string;
  objective: StrategyObjective;
  count: number;
  seed: number | undefined;
  candidateKeys: string[];
}): string {
  return [
    parts.anchor.race_id,
    parts.anchor.anchor_driver_id,
    parts.anchor.anchor_lap_number,
    parts.anchor.anchor_state_time_s,
    parts.target,
    parts.objective,
    parts.count,
    parts.seed ?? "default",
    [...parts.candidateKeys].sort().join(","),
  ].join("|");
}

/** A response belongs to the exact current selection. */
export function strategyResponseMatchesSelection(
  response: StrategyCompareResponse,
  anchor: SimulationAnchor,
  target: string,
  objective: StrategyObjective,
  count: number,
): boolean {
  return (
    response.race_id === anchor.race_id &&
    response.anchor_driver_id === anchor.anchor_driver_id &&
    response.anchor_lap_number === anchor.anchor_lap_number &&
    response.anchor_state_time_s === anchor.anchor_state_time_s &&
    response.target_driver_id === target &&
    response.objective === objective &&
    response.simulation_count === count
  );
}

/** Stale-response guard: session = selection, requestId = run. */
export function isCurrentStrategyResponse(
  requestId: number,
  currentRequestId: number,
  session: number,
  currentSession: number,
): boolean {
  return session === currentSession && requestId === currentRequestId;
}

export type WorkloadBand = "STANDARD" | "HEAVY" | "VERY_HEAVY";

/**
 * Estimated workload band from S6 evidence: the full 9-candidate 1k path
 * measured 10–35 s; 10k/3-candidate measured 35–142 s.
 */
export function workloadBand(count: number, candidateCount: number): WorkloadBand {
  if (count >= 10000) return "VERY_HEAVY";
  if (candidateCount > 4) return "HEAVY";
  return "STANDARD";
}

export function workloadNote(band: WorkloadBand): string {
  if (band === "VERY_HEAVY") {
    return "Very heavy: 10,000-trial comparisons can take tens of seconds to over two minutes, depending on race state. At most 3 candidates.";
  }
  if (band === "HEAVY") {
    return "Heavy: full candidate comparisons at 1,000 trials measured 10–35 s across race states. Run explicitly.";
  }
  return "Standard: a 1,000-trial comparison of up to 4 candidates.";
}

/** Whether a candidate key may be added under the current count. */
export function canAddCandidate(
  count: number,
  selectedKeys: string[],
): boolean {
  if (selectedKeys.length >= CANONICAL_CANDIDATES.length) return false;
  if (count >= 10000 && selectedKeys.length >= MAX_CANDIDATES_AT_10K) {
    return false;
  }
  return true;
}

/** Win/podium probability as a percentage with one decimal. */
export function formatProbability(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

/**
 * Probability delta in percentage points (never confused with probability).
 * Positive = estimated improvement for the candidate.
 */
export function formatDeltaPoints(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const points = value * 100;
  const sign = points > 0 ? "+" : points < 0 ? "−" : "+";
  return `${sign}${Math.abs(points).toFixed(1)} pp`;
}

/** Expected finish position value. */
export function formatFinish(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return value.toFixed(2);
}

/**
 * Expected-finish delta in positions. Positive = estimated improvement
 * (the candidate lowers the expected finishing position).
 */
export function formatDeltaPositions(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "+";
  return `${sign}${Math.abs(value).toFixed(2)} pos`;
}

/** Sampling interval for the selected objective delta. */
export function formatSamplingInterval(
  low: number | null,
  high: number | null,
  isFinishMetric: boolean,
): string {
  if (low === null || high === null) return "interval withheld";
  if (isFinishMetric) {
    return `${formatDeltaPositions(low)} to ${formatDeltaPositions(high)}`;
  }
  return `${formatDeltaPoints(low)} to ${formatDeltaPoints(high)}`;
}

export function formatStrategyCount(value: number): string {
  return value.toLocaleString("en-US");
}

export function strategyUnsupportedMessage(body: {
  reason?: string | null;
  error?: string;
  detail?: string;
}): string {
  if (body.reason === "non_contemporaneous_roster_member") {
    return (
      "This historical state cannot be compared safely because the " +
      "complete field cannot be established contemporaneously at this " +
      "point in the race."
    );
  }
  if (body.reason === "target_driver_not_in_roster") {
    return (
      "The selected target driver is not in the contemporaneous roster " +
      "at this exact state. Choose a driver present at time T."
    );
  }
  const detail = body.detail ? ` ${body.detail}` : "";
  return `This historical state cannot be compared. Reason: ${
    body.reason ?? body.error ?? "unsupported"
  }.${detail}`;
}

/** Product-facing copy must stay bounded: no recommendation language. */
export const FORBIDDEN_STRATEGY_COPY = [
  "best strategy",
  "optimal strategy",
  "recommended strategy",
  "would have won",
  "would finish",
  "guaranteed",
];
