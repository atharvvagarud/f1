// Consensus display transforms (V3.8G). Pure functions only.
//
// Display rule: percentages are native_probability * 100, nothing else.
// The frontend never normalizes, re-ranks, or re-ties backend values.

/** 0.8088 -> "80.9%". Null stays null (unavailable is not zero). */
export function formatPct(p: number | null): string | null {
  if (p === null || !Number.isFinite(p)) return null;
  return `${(p * 100).toFixed(1)}%`;
}

/** Signed gap in percentage points: + = simulation higher. */
export function formatGapPp(gap: number | null): string | null {
  if (gap === null || !Number.isFinite(gap)) return null;
  const pp = gap * 100;
  if (Math.abs(pp) < 0.05) return "0.0 pp";
  const sign = pp > 0 ? "+" : "−";
  return `${sign}${Math.abs(pp).toFixed(1)} pp`;
}

/** Average rank display: ties shown exactly (1, 2.5), never broken. */
export function formatRank(rank: number | null | undefined): string {
  if (rank === null || rank === undefined || !Number.isFinite(rank)) {
    return "\u2014";
  }
  return Number.isInteger(rank) ? String(rank) : rank.toFixed(1);
}

/** Rank displacement: simulation_rank - model_rank, sign preserved. */
export function formatDisplacement(disp: number | null): string | null {
  if (disp === null || !Number.isFinite(disp)) return null;
  if (disp === 0) return "0";
  const sign = disp > 0 ? "+" : "\u2212";
  const abs = Math.abs(disp);
  return `${sign}${Number.isInteger(abs) ? abs : abs.toFixed(1)}`;
}

/** Tie-safe leader label: every tied leader named, never cut to one. */
export function formatLeaders(leaders: string[] | undefined): string {
  if (!leaders || leaders.length === 0) return "\u2014";
  return leaders.map(readableConsensusDriver).join(" · ");
}

export function readableConsensusDriver(driverId: string): string {
  return driverId.replace(/_/g, " ").toUpperCase();
}

/** Product copy for a typed refusal reason (concise, factual). */
export function refusalCopy(reason: string | null): string {
  switch (reason) {
    case "MC2_STATE_INELIGIBLE":
      return "The simulation source cannot serve this factual state, so disagreement cannot be calculated. Missing is not zero.";
    case "STATE_NOT_AVAILABLE":
      return "This state is outside product support. No fallback state is substituted.";
    case "SOURCE_NOT_AVAILABLE":
      return "The source has no data for this state.";
    case "IDENTITY_MISMATCH":
      return "Model and simulation states do not match; comparison refused.";
    default:
      return "Comparison unavailable at this state.";
  }
}

/** Sort keys for the field table. Default order is backend row order. */
export type FieldSortKey = "driver" | "model" | "sim" | "gap";

export function compareFieldRows(
  a: {
    driver_id: string;
    p_model: number | null;
    p_simulation: number | null;
    absolute_gap: number | null;
  },
  b: {
    driver_id: string;
    p_model: number | null;
    p_simulation: number | null;
    absolute_gap: number | null;
  },
  key: FieldSortKey,
  dir: 1 | -1,
): number {
  const num = (v: number | null): number =>
    v === null || !Number.isFinite(v) ? Number.NEGATIVE_INFINITY : v;
  switch (key) {
    case "driver":
      return (a.driver_id < b.driver_id ? -1 : 1) * dir;
    case "model":
      return (num(a.p_model) - num(b.p_model)) * dir;
    case "sim":
      return (num(a.p_simulation) - num(b.p_simulation)) * dir;
    case "gap":
      return (num(a.absolute_gap) - num(b.absolute_gap)) * dir;
    default:
      return 0;
  }
}
