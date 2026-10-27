// Consensus product API client (V3.8G).
//
// Typed boundary over GET /v2/consensus/availability and
// POST /v2/consensus/compare. The frontend renders backend-authoritative
// values verbatim: it never recomputes average-tie ranks, leader ties,
// top-k boundary ties, or Wilson intervals, and never imports research
// records, model artifacts, or simulator internals. Native probabilities
// are displayed as native*100 only.
//
// fetch is injectable for tests. No polling, no streaming.

import { V2ApiError } from "@/lib/v2";
import {
  readJson as readSharedJson,
  resolveBase as sharedResolveBase,
  type FetchLike as SharedFetchLike,
} from "@/lib/http";

export type ConsensusAnchor = {
  race_id: string;
  anchor_lap_number: number;
  anchor_state_time_s: number | null;
};

export type ConsensusAvailability = {
  race_id: string;
  anchor_lap_number: number;
  anchor_state_time_s: number | null;
  model: string;
  model_reason: string | null;
  simulation: string;
  simulation_reason: string | null;
  comparison: string;
};

export type ConsensusDriverRow = {
  driver_id: string;
  p_model: number | null;
  p_simulation: number | null;
  signed_gap: number | null;
  absolute_gap: number | null;
  model_inside_simulation_interval: boolean | null;
  valid_trials: number | null;
  sampling_se: number | null;
  wilson_95: [number, number] | null;
};

export type ConsensusCompare = {
  state: {
    race_id: string;
    lap_number: number;
    state_time_s: number | null;
    stage: string | null;
    season: number;
  };
  availability: ConsensusAvailability;
  model: {
    source: string;
    probability_family: string;
    target: string;
    drivers: { driver_id: string; p_model: number }[];
  };
  simulation: {
    source: string;
    probability_family: string;
    target: string;
    drivers: {
      driver_id: string;
      p_simulation: number;
      valid_trials: number;
    }[];
  };
  disagreement: {
    signed_gap_definition: string;
    drivers: ConsensusDriverRow[];
    rank: Record<string, unknown>;
    leader: Record<string, unknown>;
    top_k: Record<string, unknown>;
  };
  provenance: Record<string, string>;
};

export type FetchLike = SharedFetchLike;

async function readJson<T>(
  fetcher: FetchLike,
  url: string,
  init?: RequestInit,
): Promise<T> {
  return readSharedJson<T>(
    fetcher,
    url,
    init,
    (status, body) => new V2ApiError(status, body as { error: string }),
  );
}

const baseOf = (base?: string): string => sharedResolveBase(base);

/** Cheap availability only: never triggers expensive backend work. */
export async function getConsensusAvailability(
  anchor: ConsensusAnchor,
  fetcher: FetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<ConsensusAvailability> {
  const params = new URLSearchParams({
    race_id: anchor.race_id,
    anchor_lap_number: String(anchor.anchor_lap_number),
  });
  return readJson<ConsensusAvailability>(
    fetcher,
    `${baseOf(base)}/v2/consensus/availability?${params.toString()}`,
    { cache: "no-store", signal },
  );
}

/** Strict typed comparison for one exact anchor (single request, no loop). */
export async function postConsensusCompare(
  anchor: ConsensusAnchor,
  fetcher: FetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<ConsensusCompare> {
  return readJson<ConsensusCompare>(
    fetcher,
    `${baseOf(base)}/v2/consensus/compare`,
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
export function isConsensusUnsupported(error: unknown): boolean {
  return (
    error instanceof V2ApiError &&
    error.status === 422 &&
    error.code === "consensus_unsupported"
  );
}
