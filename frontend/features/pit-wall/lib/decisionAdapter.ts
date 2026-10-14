// Exact workspace -> decision-product adapter (V3.10G).
//
// One typed translation from canonical pit-wall identity
// (raceId + frameIndex + selectedDriverId, resolved through the frame's own
// exact replay anchor) to each frozen product identity:
//
//   strategy (V3.6F):       POST /v2/strategies/compare-v3
//   counterfactual (V3.7F): POST /v2/counterfactuals/compare
//                           GET  /v2/counterfactuals/availability
//
// Requirements: exact, deterministic, causal, fail-closed. The frame anchor
// passes through verbatim — never re-derived, never snapped to a nearest
// state/lap/checkpoint, never probed. Unsupported stays unsupported:
// missing is not zero and unsupported is not poor strategy.
//
// Season firewall: the served registry is 2018–2024 (2025 unsupported).
// Race ids carry a leading season (e.g. "2022-r01-R"); anything outside
// the frozen window — including any 2025 race — is refused locally with no
// request issued. The backend 404 unknown_race contract stays authoritative.

import type { CounterfactualAvailabilityDriver, Strategy2AvailabilityEntry } from "../../../lib/v2.ts";

export const DECISION_SEASON_MIN = 2018;
export const DECISION_SEASON_MAX = 2024;

/** Exact replay anchor of one canonical frame (identity only). */
export interface DecisionFrameMeta {
  raceId: string;
  frameIndex: number;
  anchorDriverId: string;
  anchorLapNumber: number;
  anchorStateTimeS: number;
}

/** Frozen product anchor shared by strategy + counterfactual APIs. */
export interface DecisionAnchor {
  race_id: string;
  anchor_driver_id: string;
  anchor_lap_number: number;
  anchor_state_time_s: number;
}

export type AdapterRefusalCode =
  | "NO_FRAME"
  | "NO_DRIVER"
  | "SEASON_UNSUPPORTED"
  | "MALFORMED_ANCHOR";

export interface AdapterRefusal {
  code: AdapterRefusalCode;
  message: string;
}

export type AdapterResult =
  | { ok: true; anchor: DecisionAnchor; targetDriverId: string }
  | { ok: false; refusal: AdapterRefusal };

function refused(
  code: AdapterRefusalCode,
  message: string,
): AdapterResult {
  return { ok: false, refusal: { code, message } };
}

/** Leading-season parse ("2022-r01-R" -> 2022). Null when unparseable. */
export function seasonOfRaceId(raceId: string): number | null {
  const match = /^(\d{4})-/.exec(raceId);
  if (!match) return null;
  const season = Number(match[1]);
  return Number.isInteger(season) ? season : null;
}

export function isSupportedSeason(raceId: string): boolean {
  const season = seasonOfRaceId(raceId);
  return (
    season !== null &&
    season >= DECISION_SEASON_MIN &&
    season <= DECISION_SEASON_MAX
  );
}

/**
 * Exact workspace -> frozen product identity. The frame anchor is the
 * replay frame's own (race, anchor driver, lap, state time); the target is
 * the selected driver verbatim. No snapping, no substitution, no probing:
 * any inexactness is a refusal, never a repair.
 */
export function adaptDecisionTarget(
  frame: DecisionFrameMeta | null,
  selectedDriverId: string | null,
): AdapterResult {
  if (frame === null) {
    return refused("NO_FRAME", "No exact replay state is loaded.");
  }
  if (selectedDriverId === null || selectedDriverId.trim().length === 0) {
    return refused(
      "NO_DRIVER",
      "Select a driver to scope strategy and alternative exploration.",
    );
  }
  if (!isSupportedSeason(frame.raceId)) {
    return refused(
      "SEASON_UNSUPPORTED",
      "Strategy and alternative exploration support 2018–2024 only. This race has no analysis, including any 2025 race.",
    );
  }
  if (
    typeof frame.anchorDriverId !== "string" ||
    frame.anchorDriverId.trim().length === 0 ||
    !Number.isInteger(frame.anchorLapNumber) ||
    frame.anchorLapNumber < 1 ||
    typeof frame.anchorStateTimeS !== "number" ||
    !Number.isFinite(frame.anchorStateTimeS)
  ) {
    return refused(
      "MALFORMED_ANCHOR",
      "No exact anchor state matches this selection.",
    );
  }
  return {
    ok: true,
    anchor: {
      race_id: frame.raceId,
      anchor_driver_id: frame.anchorDriverId,
      anchor_lap_number: frame.anchorLapNumber,
      anchor_state_time_s: frame.anchorStateTimeS,
    },
    targetDriverId: selectedDriverId,
  };
}

/**
 * Exact catalogue match for Strategy 2.0 availability: race + full anchor
 * triple + target driver must all match. Anything less (same lap but a
 * different state time, same state but another driver) is NOT a match —
 * never the nearest entry.
 */
export function matchStrategyEntry(
  entries: readonly Strategy2AvailabilityEntry[],
  anchor: DecisionAnchor,
  targetDriverId: string,
): Strategy2AvailabilityEntry | null {
  for (const entry of entries) {
    if (
      entry.race_id === anchor.race_id &&
      entry.anchor_driver_id === anchor.anchor_driver_id &&
      entry.anchor_lap_number === anchor.anchor_lap_number &&
      entry.anchor_state_time_s === anchor.anchor_state_time_s &&
      entry.target_driver_id === targetDriverId
    ) {
      return entry;
    }
  }
  return null;
}

/** Verbatim eligible N domain for one driver (never clamped, never capped). */
export interface EligibleNDomain {
  min: number;
  max: number;
  decisionLap: number;
}

export function eligibleNDomain(
  drivers: readonly CounterfactualAvailabilityDriver[],
  driverId: string,
): EligibleNDomain | null {
  const row = drivers.find((d) => d.driver_id === driverId) ?? null;
  if (
    row === null ||
    !row.eligible ||
    row.eligible_n_min === null ||
    row.eligible_n_max === null
  ) {
    return null;
  }
  return {
    min: row.eligible_n_min,
    max: row.eligible_n_max,
    decisionLap: row.decision_lap,
  };
}

export type InterventionValidity =
  | { ok: true }
  | { ok: false; reason: string };

/**
 * Fail-closed intervention check: N must lie inside the exact eligible
 * domain, the compound inside the frozen supported set. Invalid is
 * rejected — never silently clamped, never rescheduled.
 */
export function validateIntervention(
  n: number,
  domain: EligibleNDomain | null,
  compound: string,
  supportedCompounds: readonly string[],
): InterventionValidity {
  if (domain === null) {
    return {
      ok: false,
      reason:
        "The selected driver admits no scheduled intervention at this exact state.",
    };
  }
  if (!Number.isInteger(n) || n < domain.min || n > domain.max) {
    return {
      ok: false,
      reason: `N must satisfy ${domain.min} ≤ N ≤ ${domain.max} at this state. Nothing was rescheduled.`,
    };
  }
  if (!supportedCompounds.includes(compound)) {
    return {
      ok: false,
      reason: `Compound ${compound} is not supported at this state.`,
    };
  }
  return { ok: true };
}
