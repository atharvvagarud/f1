// Selected-driver intelligence slice (V3.10E).
//
// Pure selection over the frozen V3.9C uncertainty bundle: given one compare
// payload (one exact historical state) and a driver identity, it returns
// that driver's verbatim evidence plus the bundle-level context the DETAILS
// disclosure needs. No fetching, no recomputation, no blending, no verdicts.
//
// Absent driver -> null (the caller renders unavailable; nothing is ever
// substituted). Null disagreement/sampling arms pass through as nulls —
// missing is not zero.
//
// Value-import-free (type-only imports erase under `node --test`
// type-stripping): formatting lives in the components via the existing
// uncertaintyFormat helpers.

import type {
  UncertaintyCompare,
  UncertaintyDriver,
} from "@/features/uncertainty/lib/uncertaintyClient";

export interface DriverSampling {
  successCountK: number;
  validFuturesN: number;
  pHat: number;
  standardError: number;
  wilsonLower: number;
  wilsonUpper: number;
  precisionLabel: string;
}

export interface DriverIntelligence {
  driverId: string;
  status: string;
  missingArm: string | null;
  pModel: number | null;
  pSimulation: number | null;
  signedGap: number | null;
  absoluteGap: number | null;
  modelRank: number | null;
  simulationRank: number | null;
  modelInsideWilson: boolean | null;
  sampling: DriverSampling | null;
}

export interface BundleIntelligence {
  modelFamily: string;
  simulationFamily: string;
  leaderModel: string | null;
  leaderSimulation: string | null;
  leaderAgree: boolean | null;
  top3Jaccard: number | null;
  rankCorrelation: number | null;
  nCommon: number;
  sensitivityStatus: string;
  sensitivityReason: string;
  provenance: Readonly<Record<string, string>>;
}

export interface IntelligenceSlice {
  driver: DriverIntelligence | null;
  bundle: BundleIntelligence;
}

function toSampling(
  driver: UncertaintyDriver,
): DriverSampling | null {
  const mc = driver.monte_carlo_sampling;
  if (!mc) return null;
  return {
    successCountK: mc.success_count_k,
    validFuturesN: mc.valid_futures_n,
    pHat: mc.p_hat,
    standardError: mc.standard_error,
    wilsonLower: mc.wilson_95_lower,
    wilsonUpper: mc.wilson_95_upper,
    precisionLabel: mc.precision_label,
  };
}

/**
 * Slices one driver's verbatim evidence out of a compare bundle.
 * Returns null driver (with full bundle context) when the driver has no
 * row — identity stays intact, panels render unavailable.
 */
export function selectDriverIntelligence(
  compare: UncertaintyCompare,
  driverId: string,
): IntelligenceSlice {
  const row = compare.drivers.find((d) => d.driver_id === driverId) ?? null;
  const dis = row?.disagreement ?? null;
  return {
    driver: row
      ? {
          driverId: row.driver_id,
          status: row.status,
          missingArm: row.missing_arm,
          pModel: dis?.p_model ?? null,
          pSimulation: dis?.p_simulation ?? null,
          signedGap: dis?.signed_gap ?? null,
          absoluteGap: dis?.absolute_gap ?? null,
          modelRank: dis?.model_rank ?? null,
          simulationRank: dis?.simulation_rank ?? null,
          modelInsideWilson: dis?.model_inside_simulation_wilson ?? null,
          sampling: toSampling(row),
        }
      : null,
    bundle: {
      modelFamily: compare.sources.model.probability_family,
      simulationFamily: compare.sources.simulation.probability_family,
      leaderModel: compare.field.leader_model,
      leaderSimulation: compare.field.leader_simulation,
      leaderAgree: compare.field.leader_agree,
      top3Jaccard: compare.field.top3_jaccard,
      rankCorrelation: compare.field.rank_correlation_spearman,
      nCommon: compare.field.n_common_drivers,
      sensitivityStatus: compare.simulator_sensitivity.status,
      sensitivityReason: compare.simulator_sensitivity.reason,
      provenance: compare.provenance,
    },
  };
}
