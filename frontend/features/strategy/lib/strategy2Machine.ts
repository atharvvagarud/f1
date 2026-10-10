// Strategy 2.0 pure logic (V3.6G).
//
// React-free, deterministic helpers for the Strategy 2.0 surface. The
// backend owns the science: this module never invents an alternative,
// never re-derives an estimate, interval, leader or execution rate, and
// never phrases a recommendation. It only looks up backend values,
// maps machine codes to human copy (codes stay visible), classifies
// transport errors into product states, and formats numbers with the
// frozen orientation (positive delta = improvement, including expected
// finish where positive means a lower finishing position).

import type {
  Strategy2AlternativeResult,
  Strategy2AvailabilityEntry,
  Strategy2Delta,
} from "@/lib/v2";

export type TradeOffKind = "probability" | "position" | "downside";

export type TradeOffRow = {
  metric: string;
  label: string;
  short: string;
  kind: TradeOffKind;
};

/** Frozen 6-field trade-off vector order (backend TRADE_OFF_FIELDS). */
export const STRATEGY2_TRADE_OFF_ROWS: TradeOffRow[] = [
  { metric: "delta_win_frequency", label: "Win", short: "WIN", kind: "probability" },
  { metric: "delta_podium_frequency", label: "Podium", short: "POD", kind: "probability" },
  { metric: "delta_top5_frequency", label: "Top 5", short: "P5", kind: "probability" },
  { metric: "delta_top10_frequency", label: "Top 10", short: "P10", kind: "probability" },
  { metric: "delta_expected_finish", label: "Expected finish", short: "EXP", kind: "position" },
  { metric: "delta_downside_probability", label: "Downside risk", short: "DWN", kind: "downside" },
];

/** Backend leader keys to compact human labels (point-estimate only). */
export const STRATEGY2_LEADER_LABELS: Record<string, string> = {
  leader_for_win_frequency: "Win",
  leader_for_podium_frequency: "Podium",
  leader_for_top5_frequency: "Top 5",
  leader_for_top10_frequency: "Top 10",
  leader_for_expected_finish: "Expected finish",
};

export function deltaFor(
  alternative: Strategy2AlternativeResult,
  metric: string,
): Strategy2Delta | null {
  return alternative.deltas.find((d) => d.metric === metric) ?? null;
}

/** Reference/alternative aggregate value for one trade-off row. */
export function aggregateFor(
  alternative: Strategy2AlternativeResult,
  metric: string,
  side: "reference" | "alternative",
): number | null {
  // Downside is a paired-only diagnostic: the backend "delta" point
  // estimate IS the downside share, independent of either arm.
  if (metric === "delta_downside_probability") {
    return deltaFor(alternative, metric)?.point_estimate ?? null;
  }
  const arm =
    side === "reference"
      ? alternative.reference_aggregate
      : alternative.alternative_aggregate;
  if (!arm) return null;
  switch (metric) {
    case "delta_win_frequency":
      return arm.win_frequency;
    case "delta_podium_frequency":
      return arm.podium_frequency;
    case "delta_top5_frequency":
      return arm.top5_frequency;
    case "delta_top10_frequency":
      return arm.top10_frequency;
    case "delta_expected_finish":
      return arm.expected_finish;
    default:
      return null;
  }
}

/** Objectives (by backend leader key order) led by one alternative. */
export function leadsFor(
  candidateKey: string,
  leaders: Record<string, string | null>,
): string[] {
  return Object.entries(leaders)
    .filter(([, key]) => key === candidateKey)
    .map(([leaderKey]) => leaderKey)
    .filter((leaderKey) => leaderKey in STRATEGY2_LEADER_LABELS);
}

export function formatPairs(complete: number, requested: number): string {
  return `${complete.toLocaleString("en-US")} / ${requested.toLocaleString("en-US")} complete pairs`;
}

/** Downside share as a percentage (backend value, verbatim). */
export function formatDownside(value: number | null): string {
  if (value === null || !Number.isFinite(value)) return "—";
  return `${(value * 100).toFixed(1)}%`;
}

export const DOWNSIDE_COPY =
  "Share of paired simulated futures where the alternative finishes worse " +
  "than the no-intervention reference. Not the probability the strategy " +
  "is wrong.";

export const INTERVAL_COPY =
  "Sampling uncertainty from the paired Monte Carlo simulations. Not " +
  "real-world certainty, and not the probability the strategy is better.";

export const LEADER_COPY =
  "Leader = highest simulated point estimate for this objective; not a " +
  "recommendation. Objectives can disagree: there is no single preferred " +
  "alternative.";

export const REFERENCE_COPY =
  "The simulator evolves the race from this state without forcing a " +
  "strategy action. Every alternative delta is measured against it.";

export const INERT_COPY =
  "Inert: the action caused no effective intervention in that simulated future.";
export const SUPERSEDED_COPY =
  "Superseded: simulated race evolution overtook the planned intervention.";

/** Frozen unsupported reason → concise human copy (code stays visible). */
export function strategy2ReasonCopy(reason: string | null): string {
  switch (reason) {
    case "target_driver_not_in_roster":
      return (
        "The selected target driver is not in the contemporaneous roster " +
        "at this exact state. Choose a driver present at time T."
      );
    case "non_contemporaneous_roster_member":
      return (
        "The complete field cannot be established contemporaneously at " +
        "this point in the race, so no safe comparison exists."
      );
    case "NO_VALID_PAIRS":
      return (
        "No simulated future produced a valid paired comparison for this " +
        "selection."
      );
    case null:
    case undefined:
      return "This historical state cannot be compared.";
    default:
      if (reason.startsWith("WET") || reason === "wet_track_conditions") {
        return "Wet conditions are outside the dry-only simulator scope.";
      }
      if (reason.includes("TRACK_STATE") || reason.includes("track_state")) {
        return "The track state at time T is outside simulator scope.";
      }
      if (reason.includes("TYRE") || reason.includes("tyre")) {
        return "Tyre state at time T is incomplete, so no safe comparison exists.";
      }
      if (reason.includes("ROSTER") || reason.includes("roster")) {
        return "The contemporaneous field cannot be established at time T.";
      }
      return `This historical state cannot be compared (${reason}).`;
  }
}

export type Strategy2Failure =
  | { kind: "cache-miss" }
  | { kind: "unavailable"; message: string }
  | { kind: "invalid"; message: string }
  | { kind: "server"; message: string };

/** Transport error → distinct product state (pure; codes preserved). */
export function classifyStrategy2Failure(error: {
  status?: number;
  code?: string;
  reason?: string | null;
  detail?: string;
}): Strategy2Failure {
  const code = error.code ?? "";
  if (error.status === 404 && code === "cache_miss") {
    return { kind: "cache-miss" };
  }
  if (error.status === 404 && code === "unknown_race") {
    return {
      kind: "unavailable",
      message:
        "Strategy 2.0 supports 2018–2024 only. This race has no analysis.",
    };
  }
  if (error.status === 422 && code === "unknown_state") {
    return {
      kind: "invalid",
      message: "No exact anchor state matches this selection.",
    };
  }
  if (error.status === 422 && code === "strategy_v3_request_invalid") {
    return {
      kind: "invalid",
      message: `The backend rejected this comparison request${error.reason ? `: ${error.reason}` : "."}`,
    };
  }
  if (error.status === 503 && code === "live_engine_disabled") {
    return {
      kind: "server",
      message: "Live simulation is disabled in this deployment.",
    };
  }
  if (error.status === 503) {
    return {
      kind: "server",
      message: "A server-side artifact is unavailable. Retry shortly.",
    };
  }
  return {
    kind: "server",
    message: "Strategy comparison request failed. Retry when the API is reachable.",
  };
}

export const CACHE_MISS_COPY =
  "Strategy analysis has not been precomputed for this state. " +
  "Choose a precomputed state from the catalogue.";

/** Catalogue entries grouped by race in deterministic order. */
export function groupAvailabilityByRace(
  entries: Strategy2AvailabilityEntry[],
): { race_id: string; entries: Strategy2AvailabilityEntry[] }[] {
  const groups = new Map<string, Strategy2AvailabilityEntry[]>();
  for (const entry of entries) {
    const list = groups.get(entry.race_id) ?? [];
    list.push(entry);
    groups.set(entry.race_id, list);
  }
  return [...groups.entries()]
    .map(([race_id, list]) => ({
      race_id,
      entries: [...list].sort(
        (a, b) =>
          a.anchor_lap_number - b.anchor_lap_number ||
          a.anchor_state_time_s - b.anchor_state_time_s ||
          (a.target_driver_id < b.target_driver_id ? -1 : 1),
      ),
    }))
    .sort((a, b) => (a.race_id < b.race_id ? -1 : 1));
}

/** Product-facing copy must stay bounded: no recommendation language. */
export const STRATEGY2_FORBIDDEN_COPY = [
  "best strategy",
  "optimal strategy",
  "recommended strategy",
  "recommended",
  "should pit",
  "correct strategy",
  "guaranteed",
  "proves",
  "winner",
  "optimal",
];
