// Compact decision-exploration display (V3.10G).
//
// Presentation-only transforms over frozen V3.6/V3.7 payloads for the
// pit-wall contextual surface. The backend owns every estimate: this module
// only selects which frozen metrics appear in the compact view, preserves
// canonical (never performance) order, and formats through the frozen
// machine formatters — verbatim orientation, no sign flips, no ranking, no
// recommendation, no qualitative thresholds.

// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { CANONICAL_CANDIDATES, formatDeltaPoints, formatDeltaPositions, formatSamplingInterval } from "../../strategy/lib/strategyMachine.ts";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { deltaFor as strategyDeltaFor } from "../../strategy/lib/strategy2Machine.ts";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { COUNTERFACTUAL_FORBIDDEN_COPY, PRIMARY_METRIC_ROWS, formatExpectedFinishDelta, formatInterval, formatPositionGainDelta, formatProbabilityDelta, pointOf } from "../../counterfactuals/lib/counterfactualMachine.ts";
// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { STRATEGY2_FORBIDDEN_COPY } from "../../strategy/lib/strategy2Machine.ts";
import type { CounterfactualCompareResponse, Strategy2AlternativeResult } from "../../../lib/v2.ts";

export interface CompactMetric {
  metric: string;
  short: string;
  /** Frozen point estimate, formatted (never re-derived). */
  point: string;
  /** Paired MC sampling interval, formatted (never real-world confidence). */
  interval: string;
}

/**
 * Compact strategy metrics: WIN / PODIUM / EXPECTED FINISH point estimates
 * with their paired MC intervals. Canonical metric order; caller preserves
 * canonical alternative order (CANONICAL_CANDIDATES) — never sorted by
 * performance, so no ranking can emerge.
 */
export const STRATEGY_COMPACT_METRICS = [
  { metric: "delta_win_frequency", short: "Δ WIN", finish: false },
  { metric: "delta_podium_frequency", short: "Δ PODIUM", finish: false },
  { metric: "delta_expected_finish", short: "Δ EXPECTED FINISH", finish: true },
] as const;

/** Canonical alternative keys in frozen order (never a ranking). */
export function canonicalAlternativeOrder(): string[] {
  return CANONICAL_CANDIDATES.map((c) => c.key);
}

export function strategyCompactLines(
  alternative: Strategy2AlternativeResult,
): CompactMetric[] {
  return STRATEGY_COMPACT_METRICS.map(({ metric, short, finish }) => {
    const delta = strategyDeltaFor(alternative, metric);
    const point = finish
      ? formatDeltaPositions(delta?.point_estimate ?? null)
      : formatDeltaPoints(delta?.point_estimate ?? null);
    return {
      metric,
      short,
      point,
      interval: formatSamplingInterval(
        delta?.ci_low ?? null,
        delta?.ci_high ?? null,
        finish,
      ),
    };
  });
}

/**
 * Compact counterfactual metrics in the frozen PRIMARY_METRIC_ROWS order:
 * probability deltas ALT − BASE, expected finish BASE − ALT, position gain
 * ALT − BASE — verbatim backend orientation.
 */
export function counterfactualCompactLines(
  response: CounterfactualCompareResponse,
): CompactMetric[] {
  return PRIMARY_METRIC_ROWS.map((row) => {
    const delta = response.deltas?.[row.metric] ?? null;
    let point: string;
    switch (row.kind) {
      case "probability":
        point = formatProbabilityDelta(delta);
        break;
      case "finish":
        point = formatExpectedFinishDelta(delta);
        break;
      case "gain":
        point = formatPositionGainDelta(delta);
        break;
      default:
        point = delta?.point_estimate == null ? "—" : String(pointOf(delta));
        break;
    }
    return {
      metric: row.metric,
      short: row.short,
      point,
      interval: formatInterval(delta),
    };
  });
}

/**
 * Product-facing copy must stay bounded across both G surfaces. Union of
 * the frozen expert-surface lists plus G-local phrases (advice, ranking,
 * qualitative thresholds, alternate-history framing) that are never
 * scientifically frozen.
 */
export const DECISION_FORBIDDEN_COPY: readonly string[] = [
  ...STRATEGY2_FORBIDDEN_COPY,
  ...COUNTERFACTUAL_FORBIDDEN_COPY,
  "faster strategy",
  "ideal pit",
  "better outcome",
  "fix the strategy",
  "alternate history",
  "strong improvement",
  "weak option",
  "marginal gain",
  "outcome certainty",
  "strategy confidence",
  "advantage score",
];
