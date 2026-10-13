// Uncertainty display transforms (V3.9D). Pure functions only.
//
// Number contract (deterministic, tested):
// - Native probabilities render with exactly 3 decimals ("0.000", "0.031").
//   Tiny nonzero values also show "0.000" in the cell; the exact value is
//   always carried in the cell `title` plus the inspector's k/n evidence,
//   so precision is never silently destroyed.
// - Signed gaps render with sign and 3 decimals ("+0.001", "−0.001").
// - Sampling SE and Wilson bounds render with 4 decimals (they live at
//   1e-4 scale for n=5000 futures).
// - Spearman renders with 3 decimals; top-3 overlap renders as a fraction
//   with 3 decimals ("0.500"). No thresholds, no qualitative labels.
// Zero is data: 0.000 renders as "0.000", never as "—"/"N/A".

/** Native probability with exactly 3 decimals. Null stays null. */
export function formatProb(p: number | null | undefined): string | null {
  if (p === null || p === undefined || !Number.isFinite(p)) return null;
  return p.toFixed(3);
}

/**
 * Signed gap, Δ = simulation − model. "+0.001" / "−0.001" / "0.000".
 * Direction words (never color alone) come from gapDirection().
 */
export function formatSignedGap(gap: number | null | undefined): string | null {
  if (gap === null || gap === undefined || !Number.isFinite(gap)) return null;
  if (gap === 0) return "0.000";
  const sign = gap > 0 ? "+" : "−";
  return `${sign}${Math.abs(gap).toFixed(3)}`;
}

/** Unsigned gap magnitude, 3 decimals. */
export function formatAbsGap(gap: number | null | undefined): string | null {
  if (gap === null || gap === undefined || !Number.isFinite(gap)) return null;
  return Math.abs(gap).toFixed(3);
}

/** Machine-readable direction wording; never color-only. */
export function gapDirection(gap: number | null | undefined): string {
  if (gap === null || gap === undefined || !Number.isFinite(gap)) {
    return "direction unavailable";
  }
  if (gap > 0) return "simulation higher";
  if (gap < 0) return "model higher";
  return "equal";
}

/** Sampling SE at 4 decimals (n=5000 scale). */
export function formatSE(se: number | null | undefined): string | null {
  if (se === null || se === undefined || !Number.isFinite(se)) return null;
  return se.toFixed(4);
}

/** Wilson bound at 4 decimals. */
export function formatBound(b: number | null | undefined): string | null {
  if (b === null || b === undefined || !Number.isFinite(b)) return null;
  return b.toFixed(4);
}

/** Average rank display: ties shown exactly (1, 2.5), never broken. */
export function formatRank(rank: number | null | undefined): string {
  if (rank === null || rank === undefined || !Number.isFinite(rank)) {
    return "—";
  }
  return Number.isInteger(rank) ? String(rank) : rank.toFixed(1);
}

/** Spearman rank correlation, 3 decimals, no qualitative label. */
export function formatSpearman(r: number | null | undefined): string {
  if (r === null || r === undefined || !Number.isFinite(r)) return "—";
  return r.toFixed(3);
}

/** Top-3 overlap as a fraction with 3 decimals ("0.500"), never a verdict. */
export function formatJaccard(j: number | null | undefined): string {
  if (j === null || j === undefined || !Number.isFinite(j)) return "—";
  return j.toFixed(3);
}

/** Integer count (k successes, n futures). */
export function formatCount(n: number | null | undefined): string {
  if (n === null || n === undefined || !Number.isFinite(n)) return "—";
  return String(Math.trunc(n));
}

export function readableUncertaintyDriver(driverId: string): string {
  return driverId.replace(/_/g, " ").toUpperCase();
}

/** Leader-agreement wording: neutral, no verdict. */
export function leaderWording(agree: boolean | null | undefined): string {
  if (agree === null || agree === undefined) return "LEADER UNKNOWN";
  return agree ? "LEADER MATCH" : "LEADER DIFFERENT";
}

/** Product copy for a typed refusal reason (concise, factual). */
export function refusalCopy(reason: string | null): string {
  switch (reason) {
    case "MC2_STATE_INELIGIBLE":
      return "The simulation source cannot serve this factual state, so disagreement cannot be calculated. Missing is not zero.";
    case "STATE_NOT_AVAILABLE":
      return "This state is outside product support. 2025 is product-excluded: no fallback state is substituted and zero uncertainty is never implied.";
    case "SOURCE_NOT_AVAILABLE":
      return "The source has no data for this state.";
    case "IDENTITY_MISMATCH":
      return "Model and simulation states do not match; comparison refused.";
    default:
      return "Comparison unavailable at this state.";
  }
}

/** Human label for a V3.9 driver/bundle status token. */
export function statusLabel(status: string): string {
  switch (status) {
    case "AVAILABLE":
      return "Available";
    case "UNAVAILABLE":
      return "Unavailable";
    case "MISSING_SOURCE":
      return "Missing source";
    case "UNSUPPORTED_STATE":
      return "Unsupported state";
    case "NOT_APPLICABLE":
      return "Not applicable";
    case "INSUFFICIENT_SIMULATIONS":
      return "Insufficient simulations";
    case "PROVENANCE_UNAVAILABLE":
      return "Provenance unavailable";
    case "COMPARABLE":
      return "Comparable";
    case "NOT_COMPARABLE":
      return "Not comparable";
    default:
      return status;
  }
}
