// Counterfactual Explorer pure logic (V3.7G).
//
// React-free, deterministic helpers for the Counterfactual Explorer
// surface. The backend owns the science: this module never invents a
// plan, never re-derives an estimate, interval, orientation, or
// lifecycle count, and never phrases a recommendation. It only looks
// up backend values, maps machine codes to human copy (codes stay
// visible), classifies transport errors into product states, and
// formats numbers with the frozen orientation (verbatim backend
// values; no sign flips anywhere in this file).

import type {
  CounterfactualAvailabilityDriver,
  CounterfactualCompareRequest,
  CounterfactualCompareResponse,
  CounterfactualCompound,
  CounterfactualDelta,
  CounterfactualForm,
  CounterfactualPlan,
} from "@/lib/v2";

export const MAX_INTERVENTIONS = 8;

export const SUPPORTED_COMPOUNDS: CounterfactualCompound[] = [
  "SOFT",
  "MEDIUM",
  "HARD",
  "SAMPLED",
];

export type MetricKind = "probability" | "finish" | "gain" | "descriptive";

export type MetricRow = {
  metric: string;
  label: string;
  short: string;
  kind: MetricKind;
  /** Improvement-direction hint. Null = descriptive, never good/bad. */
  improvement?: "higher" | "lower";
};

/**
 * Primary comparison strip (deliberate hierarchy). Orientation is the
 * frozen backend contract: probability-like deltas ALT − BASE;
 * position gain ALT − BASE (positive = gained); expected finish
 * BASE − ALT (positive = ALT improvement, lower finish).
 */
export const PRIMARY_METRIC_ROWS: MetricRow[] = [
  { metric: "delta_win_frequency", label: "Win probability", short: "WIN", kind: "probability", improvement: "higher" },
  { metric: "delta_podium_frequency", label: "Podium probability", short: "POD", kind: "probability", improvement: "higher" },
  { metric: "delta_top5_frequency", label: "Top-5 probability", short: "TOP5", kind: "probability", improvement: "higher" },
  { metric: "delta_expected_finish", label: "Expected finish", short: "EXP", kind: "finish", improvement: "higher" },
  { metric: "delta_position_gain_loss", label: "Position gain", short: "GAIN", kind: "gain", improvement: "higher" },
];

/** Secondary diagnostics (visible but subordinate). */
export const SECONDARY_METRIC_ROWS: MetricRow[] = [
  { metric: "delta_top10_frequency", label: "Top-10 probability", short: "TOP10", kind: "probability", improvement: "higher" },
  { metric: "delta_p_ahead_of_rival", label: "P(ahead of rival)", short: "RIVAL", kind: "probability", improvement: "higher" },
  { metric: "delta_pit_count", label: "Expected pit-count change", short: "PITS", kind: "descriptive" },
];

export function deltaFor(
  response: CounterfactualCompareResponse,
  metric: string,
): CounterfactualDelta | null {
  return response.deltas?.[metric] ?? null;
}

/** Verbatim backend point estimate (null when unavailable). No transform. */
export function pointOf(delta: CounterfactualDelta | null): number | null {
  if (!delta || delta.point_estimate === null) return null;
  const value = delta.point_estimate;
  return Number.isFinite(value) ? value : null;
}

function signed(value: number, digits: number): string {
  const sign = value > 0 ? "+" : value < 0 ? "−" : "±";
  return `${sign}${Math.abs(value).toFixed(digits)}`;
}

/** Probability delta in percentage points, verbatim orientation. */
export function formatProbabilityDelta(delta: CounterfactualDelta | null): string {
  const value = pointOf(delta);
  if (value === null) return "—";
  return `${signed(value * 100, 1)} pts`;
}

/**
 * Position-gain delta: positive = ALT greater expected gain.
 * +3 displays as gain, 0 neutral, −3 as loss (B1 orientation).
 */
export function formatPositionGainDelta(delta: CounterfactualDelta | null): string {
  const value = pointOf(delta);
  if (value === null) return "—";
  return `${signed(value, 2)} pos`;
}

export function gainTone(value: number | null): "gain" | "loss" | "neutral" {
  if (value === null || !Number.isFinite(value) || value === 0) return "neutral";
  return value > 0 ? "gain" : "loss";
}

/**
 * Expected-finish delta: backend uses BASE − ALT, so a positive value
 * already means ALT improvement (lower finish). Rendered verbatim.
 */
export function formatExpectedFinishDelta(delta: CounterfactualDelta | null): string {
  const value = pointOf(delta);
  if (value === null) return "—";
  return `${signed(value, 2)} pos`;
}

/** Expected finish arm value (lower is better; descriptive label). */
export function formatExpectedFinish(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return `P${value.toFixed(2)}`;
}

/** Pit-count values are descriptive: no good/bad treatment, ever. */
export function formatPitCount(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) return "—";
  return value.toFixed(2);
}

/** MC sampling interval label (never real-world confidence). */
export function formatInterval(delta: CounterfactualDelta | null): string {
  if (!delta || delta.ci_low === null || delta.ci_high === null) return "—";
  return `[${delta.ci_low.toFixed(3)}, ${delta.ci_high.toFixed(3)}]`;
}

export function formatPairs(complete: number | null, requested: number | null): string {
  if (complete === null || requested === null) return "—";
  return `${complete.toLocaleString("en-US")} / ${requested.toLocaleString("en-US")} complete pairs`;
}

/** Lifecycle statuses in frozen B/C vocabulary (never collapsed). */
export const LIFECYCLE_ORDER = [
  "EXECUTED",
  "INERT",
  "SUPERSEDED",
  "CANCELLED",
  "TERMINAL",
  "INVALID",
] as const;

export function lifecycleCounts(
  response: CounterfactualCompareResponse,
): { arm: string; status: string; count: number; share: number; total: number }[] {
  const rows: { arm: string; status: string; count: number; share: number; total: number }[] = [];
  for (const arm of ["alternative", "base"] as const) {
    const summary = response.lifecycle_summary?.[arm] ?? {};
    const total = Object.values(summary).reduce((a, b) => a + b, 0);
    for (const status of LIFECYCLE_ORDER) {
      const count = summary[status] ?? 0;
      if (count > 0 || status === "EXECUTED") {
        rows.push({ arm, status, count, share: total > 0 ? count / total : 0, total });
      }
    }
  }
  return rows;
}

export function supersededShare(response: CounterfactualCompareResponse): number | null {
  const summary = response.lifecycle_summary?.["alternative"];
  if (!summary) return null;
  const total = Object.values(summary).reduce((a, b) => a + b, 0);
  if (total === 0) return null;
  return (summary["SUPERSEDED"] ?? 0) / total;
}

/** Eligible N values for one availability driver (derived, never capped). */
export function eligibleNValues(driver: CounterfactualAvailabilityDriver): number[] {
  if (!driver.eligible || driver.eligible_n_min === null || driver.eligible_n_max === null) return [];
  const out: number[] = [];
  for (let n = driver.eligible_n_min; n <= driver.eligible_n_max; n += 1) out.push(n);
  return out;
}

/** Scheduled simulated lap for PIT_IN_N_LAPS from factual decision lap. */
export function scheduledLap(decisionLap: number, n: number): number {
  return decisionLap + n;
}

/** "PIT IN 3 LAPS · Scheduled: Lap 33" style timing line. */
export function pitTimingLabel(n: number, decisionLap: number | null): string {
  const unit = n === 1 ? "LAP" : "LAPS";
  if (decisionLap === null) return `PIT IN ${n} ${unit}`;
  return `PIT IN ${n} ${unit} · Scheduled: Lap ${scheduledLap(decisionLap, n)}`;
}

/** Frozen B reason code → concise human copy (code stays visible). */
export function counterfactualReasonCopy(reason: string | null): string {
  switch (reason) {
    case "INVALID_TRIGGER":
      return "The scheduled lap falls outside the remaining race distance (N must satisfy N ≤ remaining laps − 1).";
    case "CONFLICTING_INTERVENTIONS":
      return "Two interventions for the same driver and trigger lap request different compounds.";
    case "TARGET_NOT_PRESENT":
      return "The selected target driver is not in the factual roster at this exact state.";
    case "RIVAL_NOT_PRESENT":
      return "The rival must be a factual driver at this state and must differ from every plan target.";
    case "UNSUPPORTED_INTERVENTION_KIND":
      return "Only controlled pit interventions (PIT_IN_N_LAPS) are admitted.";
    case "INVALID_PLAN":
      return "The two plans cannot be compared (plan-vs-plan needs the same primary target).";
    case "NO_ELIGIBLE_TARGETS":
      return "No factual driver at this state admits a scheduled intervention.";
    case null:
    case undefined:
      return "This historical state cannot be compared.";
    default:
      if (reason.includes("WET") || reason.includes("wet")) {
        return "Wet conditions are outside the dry-only simulator scope.";
      }
      if (reason.includes("TRACK_STATE") || reason.includes("track_state")) {
        return "The track state at time T is outside simulator scope.";
      }
      if (reason.includes("TYRE") || reason.includes("tyre")) {
        return "Tyre state at time T is incomplete, so no safe comparison exists.";
      }
      if (reason.includes("RETIRED") || reason.includes("retired")) {
        return "A required driver is retired at time T, outside simulator scope.";
      }
      return `This historical state cannot be compared (${reason}).`;
  }
}

export type CounterfactualFailure =
  | { kind: "cache-miss" }
  | { kind: "unknown-race"; message: string }
  | { kind: "unavailable"; message: string }
  | { kind: "invalid"; message: string }
  | { kind: "server"; message: string };

/** Transport error → distinct product state (pure; codes preserved). */
export function classifyCounterfactualFailure(error: {
  status?: number;
  code?: string;
  reason?: string | null;
  detail?: string;
}): CounterfactualFailure {
  const code = error.code ?? "";
  if (error.status === 404 && code === "cache_miss") {
    return { kind: "cache-miss" };
  }
  if (error.status === 404 && code === "unknown_race") {
    return {
      kind: "unknown-race",
      message: "Counterfactuals support 2018–2024 only. This race has no analysis, including any 2025 race.",
    };
  }
  if (error.status === 422 && code === "unknown_state") {
    return {
      kind: "invalid",
      message: "No exact anchor state matches this selection.",
    };
  }
  if (error.status === 422 && code === "counterfactual_request_invalid") {
    return {
      kind: "invalid",
      message: `The backend rejected this comparison request${error.reason ? `: ${error.reason}` : "."}`,
    };
  }
  if (error.status === 503) {
    return {
      kind: "server",
      message: "A server-side cache or runtime artifact is unavailable. Retry shortly.",
    };
  }
  return {
    kind: "server",
    message: "Counterfactual comparison request failed. Retry when the API is reachable.",
  };
}

export const CACHE_MISS_COPY =
  "This comparison is scientifically valid but is not available in the " +
  "precomputed demo cache. Nothing was simulated and no estimate is shown.";

export const NO_INTERVENTION_REFERENCE_COPY =
  "Simulation continues from the same factual race state without the " +
  "controlled intervention.";

export const INTERVAL_COPY =
  "MC sampling 95% interval: Monte Carlo sampling variability under the " +
  "frozen simulator. Not real-world certainty, and not the probability " +
  "the intervention is better.";

export const SUPERSESSION_COPY =
  "Superseded: a simulator-generated pit event occurred before the " +
  "scheduled intervention in that future. Supersession is not failure.";

export const MULTI_DRIVER_LIMIT_COPY =
  "Joint finishing order is propagated; pit-box stacking and explicit " +
  "traffic/team-order effects are not modelled.";

export const LIMITATIONS_COPY: string[] = [
  "Simulator-conditional outcomes under controlled interventions only.",
  "No weather evolution; no safety-car, VSC, or red-flag generation.",
  "No reliability or DNF hazard model.",
  "No pit-box stacking model.",
  "No explicit traffic-battle model.",
  "No team-order model.",
  "Compound-specific pace differentiation is limited by the frozen simulator.",
  "2025 is outside the served registry.",
  "Spatial data is not used for counterfactual calculation.",
];

export const METHODOLOGY_COPY: { term: string; definition: string }[] = [
  { term: "Simulator-conditional", definition: "Outcomes are produced by the frozen simulator from factual state T plus a controlled intervention — not what truly would have happened." },
  { term: "Controlled intervention", definition: "Only scheduled pit stops (PIT_IN_N_LAPS) with an admitted compound. Nothing else can be changed." },
  { term: "No-intervention reference", definition: NO_INTERVENTION_REFERENCE_COPY },
  { term: "5,000 futures", definition: "Each comparison runs 5,000 paired simulated futures per arm at the locked production configuration." },
  { term: "Common random numbers", definition: "Reference and plan share random streams per future, so differences isolate the intervention instead of sampling noise." },
  { term: "Complete pairs", definition: "Only futures valid on both arms are compared; exclusions are reported, never imputed." },
  { term: "MC sampling uncertainty", definition: INTERVAL_COPY },
  { term: "Lifecycle / supersession", definition: SUPERSESSION_COPY },
];

// --- plan construction (presentation state only; backend canonicalizes) ---

export type PlanDraft = {
  target_driver_ids: string[];
  interventions: {
    target_driver_id: string;
    lap_offset_n: number;
    requested_compound: CounterfactualCompound;
  }[];
};

export function draftToPlan(draft: PlanDraft): CounterfactualPlan {
  return {
    target_driver_ids: [...draft.target_driver_ids],
    interventions: draft.interventions.map((item) => ({
      target_driver_id: item.target_driver_id,
      kind: "PIT_IN_N_LAPS" as const,
      lap_offset_n: item.lap_offset_n,
      requested_compound: item.requested_compound,
    })),
  };
}

export function draftRequestKey(parts: {
  raceId: string;
  anchorDriverId: string;
  anchorLapNumber: number;
  anchorStateTime: number;
  form: CounterfactualForm;
  base: PlanDraft | null;
  alt: PlanDraft;
  rival: string | null;
}): string {
  const planKey = (plan: PlanDraft) =>
    [
      [...plan.target_driver_ids].sort().join(","),
      plan.interventions
        .map((i) => `${i.target_driver_id}@${i.lap_offset_n}:${i.requested_compound}`)
        .sort()
        .join("+"),
    ].join("~");
  return [
    parts.raceId,
    parts.anchorDriverId,
    parts.anchorLapNumber,
    parts.anchorStateTime,
    parts.form,
    parts.base ? planKey(parts.base) : "-",
    planKey(parts.alt),
    parts.rival ?? "-",
  ].join("|");
}

export function isRivalAllowed(
  rival: string | null,
  targetIds: string[],
  candidates: string[],
): boolean {
  if (rival === null) return true;
  if (targetIds.includes(rival)) return false;
  return candidates.includes(rival);
}

// --- demo + presets (fixture-backed only; structural labels, never ranked) ---

export const DEMO_ANCHOR = {
  race_id: "2022-r01-R",
  anchor_driver_id: "perez",
  anchor_lap_number: 30,
  anchor_state_time_s: 6745.686,
} as const;

export const DEMO_TARGET = "perez";

/**
 * Deterministic default rule: the canonical replay anchor above with a
 * REFERENCE_VS_PLAN, smallest eligible N (N=1), MEDIUM single stop.
 * Chosen as the minimal intervention on the validated dry-green anchor
 * present in the F demo cache — not for its delta.
 */
export const DEMO_DEFAULT_PLAN: PlanDraft = {
  target_driver_ids: [DEMO_TARGET],
  interventions: [
    { target_driver_id: DEMO_TARGET, lap_offset_n: 1, requested_compound: "MEDIUM" },
  ],
};

export type Preset = {
  key: string;
  label: string;
  form: CounterfactualForm;
  base: PlanDraft | null;
  alt: PlanDraft;
  rival: string | null;
};

/** Every preset maps 1:1 to an F fixture-cache comparison. */
export function presetsFor(target: string, coTarget: string | null): Preset[] {
  const single = (n: number, compound: CounterfactualCompound = "MEDIUM"): PlanDraft => ({
    target_driver_ids: [target],
    interventions: [{ target_driver_id: target, lap_offset_n: n, requested_compound: compound }],
  });
  const both = coTarget && coTarget !== target ? [target, coTarget] : [target];
  const presets: Preset[] = [
    { key: "single", label: "Single stop", form: "REFERENCE_VS_PLAN", base: null, alt: single(2), rival: null },
    { key: "delayed", label: "Delayed stop", form: "REFERENCE_VS_PLAN", base: null, alt: single(5), rival: null },
    {
      key: "multi-stop",
      label: "Multi-stop",
      form: "REFERENCE_VS_PLAN",
      base: null,
      alt: {
        target_driver_ids: [target],
        interventions: [
          { target_driver_id: target, lap_offset_n: 2, requested_compound: "MEDIUM" },
          { target_driver_id: target, lap_offset_n: 8, requested_compound: "HARD" },
        ],
      },
      rival: null,
    },
    { key: "plan-vs-plan", label: "Plan vs plan", form: "PLAN_VS_PLAN", base: single(2), alt: single(5), rival: null },
  ];
  if (both.length === 2) {
    const [primary, secondary] = both;
    presets.push({
      key: "multi-driver",
      label: "Multi-driver",
      form: "REFERENCE_VS_PLAN",
      base: null,
      alt: {
        target_driver_ids: [...both],
        interventions: [
          { target_driver_id: primary, lap_offset_n: 2, requested_compound: "MEDIUM" },
          { target_driver_id: secondary, lap_offset_n: 2, requested_compound: "MEDIUM" },
        ],
      },
      rival: null,
    });
  }
  return presets;
}

export type AnchorCoords = {
  race_id: string;
  anchor_driver_id: string;
  anchor_lap_number: number;
  anchor_state_time_s: number;
};

export function buildCompareRequest(
  anchor: AnchorCoords,
  form: CounterfactualForm,
  base: PlanDraft | null,
  alt: PlanDraft,
  rival: string | null,
): CounterfactualCompareRequest {
  return {
    race_id: anchor.race_id,
    anchor_driver_id: anchor.anchor_driver_id,
    anchor_lap_number: anchor.anchor_lap_number,
    anchor_state_time_s: anchor.anchor_state_time_s,
    comparison_form: form,
    base_plan: form === "PLAN_VS_PLAN" && base ? draftToPlan(base) : null,
    alternative_plan: draftToPlan(alt),
    rival_driver_id: rival,
  };
}

/** Product-facing copy must stay bounded: no recommendation language. */
export const COUNTERFACTUAL_FORBIDDEN_COPY = [
  "best strategy",
  "optimal",
  "recommended",
  "should pit",
  "correct strategy",
  "wrong strategy",
  "would have happened",
  "would have won",
  "winning move",
  "winning",
  "correct decision",
  "proves",
  "causal effect",
  "guaranteed",
  "real-world confidence",
];
