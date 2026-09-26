// Pure display transforms for E4 local explanations (no DOM, no network).
//
// Language contract (mirrors the backend): the evidence describes additive
// model log-odds. It never says a driver "will win", never converts a
// contribution into a win-probability percentage, and never normalizes the
// independent per-driver binary estimates.

import type { LocalContribution, LocalExplanationResponse } from "@/lib/v2";

export const DIRECTION_INCREASES = "INCREASES_MODEL_LOG_ODDS";
export const DIRECTION_DECREASES = "DECREASES_MODEL_LOG_ODDS";

export function formatLogOdds(value: number): string {
  if (!Number.isFinite(value)) return "n/a";
  const sign = value > 0 ? "+" : "";
  return `${sign}${value.toFixed(2)}`;
}

export function contributionArrow(direction: string): string {
  if (direction === DIRECTION_INCREASES) return "\u2191";
  if (direction === DIRECTION_DECREASES) return "\u2193";
  return "\u00b7";
}

export function directionWord(direction: string): string {
  if (direction === DIRECTION_INCREASES) return "INCREASED MODEL LOG-ODDS";
  if (direction === DIRECTION_DECREASES) return "DECREASED MODEL LOG-ODDS";
  return "NEUTRAL";
}

/** Subtle marker for model inputs that were not directly observed. */
export function inputStateMarker(inputState: string): string | null {
  if (inputState === "IMPUTED_NUMERIC_MEDIAN" ||
      inputState === "IMPUTED_BOOLEAN_MODE") {
    return "IMPUTED";
  }
  if (inputState === "MISSING_CATEGORY") return "MISSING";
  if (inputState === "UNKNOWN_CATEGORY") return "UNKNOWN TO FITTED ENCODER";
  return null;
}

/** Omitted log-odds accounting so displayed rows are not read as complete. */
export function omittedNote(
  accounting: LocalExplanationResponse["accounting"],
): string {
  return (
    `Top ${accounting.top_n} shown; omitted ` +
    `${formatLogOdds(accounting.omitted_positive_log_odds)} positive / ` +
    `${formatLogOdds(accounting.omitted_negative_log_odds)} negative ` +
    `log-odds. The full canonical vector reconstructs the prediction; the ` +
    `top list does not.`
  );
}

/** Deterministic display order: as returned by the backend, never re-sorted. */
export function topContributions(
  explanation: LocalExplanationResponse,
): { positive: LocalContribution[]; negative: LocalContribution[] } {
  return {
    positive: explanation.top_positive,
    negative: explanation.top_negative,
  };
}

export function residualWithinTolerance(
  explanation: LocalExplanationResponse,
): boolean {
  return (
    Math.abs(explanation.reconstruction.residual) <=
    explanation.reconstruction.logit_abs_tolerance
  );
}
