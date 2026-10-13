// Uncertainty product API client (V3.9D).
//
// Typed boundary over GET /v2/uncertainty/availability and
// POST /v2/uncertainty/compare. The frontend renders backend-authoritative
// values verbatim: it never recomputes gaps, ranks, Wilson intervals, or
// standard errors, and never imports research records, model artifacts, or
// simulator internals. One compare payload serves every driver; switching
// the selected driver is local and issues no further request.
//
// fetch is injectable for tests. No polling, no streaming.

import { V2ApiError, V2_API_BASE } from "@/lib/v2";

export type UncertaintyAnchor = {
  race_id: string;
  anchor_lap_number: number;
  anchor_state_time_s: number | null;
};

export type UncertaintyAvailability = {
  race_id: string;
  anchor_lap_number: number;
  anchor_state_time_s: number | null;
  model: string;
  model_reason: string | null;
  simulation: string;
  simulation_reason: string | null;
  comparison: string;
  simulator_sensitivity: string;
};

export type UncertaintyDisagreement = {
  status: string;
  p_model: number;
  p_model_family: string;
  p_simulation: number;
  p_simulation_family: string;
  signed_gap: number;
  absolute_gap: number;
  model_rank: number;
  simulation_rank: number;
  model_inside_simulation_wilson: boolean;
};

export type UncertaintySampling = {
  status: string;
  success_count_k: number;
  valid_futures_n: number;
  p_hat: number;
  standard_error: number;
  wilson_95_lower: number;
  wilson_95_upper: number;
  precision_label: string;
};

export type UncertaintyDriver = {
  driver_id: string;
  status: string;
  missing_arm: string | null;
  disagreement: UncertaintyDisagreement | null;
  monte_carlo_sampling: UncertaintySampling | null;
  diagnostic: { gap_to_sampling_ratio: number | null; label: string } | null;
};

export type UncertaintyCompare = {
  schema_version: string;
  metric_implementation: string;
  state: {
    state_id: string;
    race_id: string;
    lap_number: number;
    state_time_s: number | null;
    stage: string | null;
    season: number;
  };
  sources: {
    model: { source: string; probability_family: string };
    simulation: { source: string; probability_family: string };
  };
  drivers: UncertaintyDriver[];
  field: {
    n_common_drivers: number;
    rank_correlation_spearman: number | null;
    leader_model: string | null;
    leader_simulation: string | null;
    leader_agree: boolean | null;
    top3_jaccard: number | null;
  };
  simulator_sensitivity: {
    status: string;
    executable: boolean;
    reason: string;
    gate: string;
    gate_version: string;
  };
  availability: UncertaintyAvailability;
  provenance: Record<string, string>;
};

export type FetchLike = (
  url: string,
  init?: RequestInit,
) => Promise<{ ok: boolean; status: number; json: () => Promise<unknown> }>;

async function readJson<T>(
  fetcher: FetchLike,
  url: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetcher(url, init);
  const body = (await res.json()) as T | {
    error: string;
    detail?: string;
    reason?: string;
  };
  if (!res.ok) {
    throw new V2ApiError(res.status, body as { error: string });
  }
  return body as T;
}

const baseOf = (base?: string): string => base ?? V2_API_BASE;

/** Cheap availability only: never triggers expensive backend work. */
export async function getUncertaintyAvailability(
  anchor: UncertaintyAnchor,
  fetcher: FetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<UncertaintyAvailability> {
  const params = new URLSearchParams({
    race_id: anchor.race_id,
    anchor_lap_number: String(anchor.anchor_lap_number),
  });
  if (anchor.anchor_state_time_s !== null) {
    params.set("anchor_state_time_s", String(anchor.anchor_state_time_s));
  }
  return readJson<UncertaintyAvailability>(
    fetcher,
    `${baseOf(base)}/v2/uncertainty/availability?${params.toString()}`,
    { cache: "no-store", signal },
  );
}

/**
 * Strict typed uncertainty bundle for one exact anchor.
 * Exactly one call per selected state; the returned driver vector serves
 * every driver selection locally — never one request per driver.
 */
export async function postUncertaintyCompare(
  anchor: UncertaintyAnchor,
  fetcher: FetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<UncertaintyCompare> {
  return readJson<UncertaintyCompare>(
    fetcher,
    `${baseOf(base)}/v2/uncertainty/compare`,
    {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(anchor),
      signal,
    },
  );
}

/** True for the stable typed-refusal contract (never a fallback trigger). */
export function isUncertaintyUnsupported(error: unknown): boolean {
  return (
    error instanceof V2ApiError &&
    error.status === 422 &&
    error.code === "uncertainty_unsupported"
  );
}
