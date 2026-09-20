// V2 replay API client (Phase-5 R5).
//
// Typed boundary over the frozen R4 replay routes. The frontend deals only
// in race_id / frame_index / ReplayFrame / RaceState / checkpoint metadata /
// cached PredictionSnapshot — it never recreates anchor grouping,
// representative selection, reconstruction, checkpoint selection, or any
// probability transform. Backend contracts are authoritative.
//
// No `any` in core replay contracts. fetch is injectable for tests.

export const V2_API_BASE =
  process.env.NEXT_PUBLIC_API_BASE || "http://127.0.0.1:8000";

export const REPLAY_PAGE_SIZE = 500; // R4 max page size

// --- R4 contract types (mirror api/v2_replay_schemas.py + v2_schemas.py) ---

export type V2RaceSummary = {
  race_id: string;
  season: number;
  round_no: number;
  event_name: string;
  circuit_id: string | null;
  country: string | null;
  location: string | null;
  scheduled_laps: number | null;
};

export type V2RaceList = {
  races: V2RaceSummary[];
  count: number;
};

export type ReplayFrameMeta = {
  race_id: string;
  frame_index: number;
  anchor_driver_id: string;
  anchor_lap_number: number;
  anchor_state_time_s: number;
  replay_contract_version: string;
};

export type ReplayTimelinePage = {
  race_id: string;
  replay_contract_version: string;
  total_frames: number;
  offset: number;
  limit: number;
  returned_count: number;
  frames: ReplayFrameMeta[];
};

export type DriverRaceState = {
  driver_id: string;
  observable: boolean;
  observed_lap_number: number | null;
  observed_time_s: number | null;
  observation_age_s: number | null;
  position: number | null;
  gap_to_leader_s: number | null;
  gap_to_leader_valid: boolean | null;
  gap_to_leader_laps: number | null;
  gap_to_ahead_s: number | null;
  gap_to_ahead_valid: boolean | null;
  gap_to_ahead_laps: number | null;
  compound: string | null;
  tyre_life: number | null;
  fresh_tyre: boolean | null;
  stint_number: number | null;
  stint_lap: number | null;
  pit_stops_completed_so_far: number | null;
  laps_since_last_pit_stop: number | null;
  constructor_id: string | null;
  driver_number: number | null;
};

export type RaceContextState = {
  race_leader_laps_at_state: number | null;
  race_progress_frac: number | null;
  scheduled_laps: number | null;
  season: number | null;
  round_no: number | null;
  circuit_id: string | null;
};

export type WeatherState = {
  air_temp_c: number | null;
  track_temp_c: number | null;
  humidity_pct: number | null;
  pressure_hpa: number | null;
  wind_speed: number | null;
  wind_direction_deg: number | null;
  rainfall: boolean | null;
  observed_at_s: number | null;
  observation_age_s: number | null;
};

export type RaceControlState = {
  track_state: string | null;
  flag_yellow: boolean | null;
  flag_safety_car: boolean | null;
  flag_red: boolean | null;
  flag_vsc: boolean | null;
  last_message_category: string | null;
  last_message_flag: string | null;
  last_message_age_s: number | null;
};

export type RaceStateResponse = {
  race_id: string;
  anchor_driver_id: string;
  anchor_lap_number: number;
  state_time_s: number;
  roster_size: number;
  drivers: DriverRaceState[];
  race_context: RaceContextState;
  weather: WeatherState;
  race_control: RaceControlState;
};

export type ReplayFrameResponse = {
  frame: ReplayFrameMeta;
  state: RaceStateResponse;
  has_previous: boolean;
  has_next: boolean;
  previous_frame_index: number | null;
  next_frame_index: number | null;
  leader_lap: number | null;
  is_prediction_checkpoint: boolean;
  checkpoint_reasons: string[];
  prediction_cache_available: boolean;
  previous_prediction_checkpoint_frame: number | null;
  next_prediction_checkpoint_frame: number | null;
};

export type CheckpointMeta = {
  frame_index: number;
  reasons: string[];
  leader_lap: number | null;
  replay_contract_version: string;
  prediction_contract_version: string;
};

export type DriverPrediction = {
  driver_id: string;
  observable: boolean;
  observed_lap_number: number | null;
  observed_time_s: number | null;
  observation_age_s: number | null;
  observed_position: number | null;
  winner_probability: number | null;
  unavailable_reason: string | null;
};

export type PredictionSnapshot = {
  race_id: string;
  anchor_driver_id: string;
  anchor_lap_number: number;
  state_time_s: number;
  roster_size: number;
  observable_count: number;
  unavailable_count: number;
  probability_semantics: string;
  probability_semantics_note: string;
  feature_set: string;
  model: Record<string, unknown>;
  predictions: DriverPrediction[];
};

export type ReplayPredictionResponse = {
  frame: ReplayFrameMeta;
  checkpoint: CheckpointMeta;
  prediction: PredictionSnapshot;
  cache_status: "HIT";
};

// --- R6 probability timeline (one response per race) ---

export type V2ModelIdentity = {
  task: string;
  target: string;
  eligibility_mask: string;
  feature_set: string;
  feature_set_version: string;
  estimator: string;
  estimator_params: [string, unknown][];
  calibration_method: string;
  probability_semantics: string;
  training_seasons: number[];
  transformed_dim: number;
  feature_count: number;
  artifact_sha256: string;
  specification_fingerprint: string;
  sklearn_version: string;
};

export type ProbabilityCheckpoint = {
  frame_index: number;
  state_time_s: number;
  leader_lap: number | null;
  reasons: string[];
};

export type DriverProbabilityPoint = {
  frame_index: number;
  state_time_s: number;
  leader_lap: number | null;
  winner_probability: number | null;
};

export type DriverProbabilitySeries = {
  driver_id: string;
  points: DriverProbabilityPoint[];
};

export type ProbabilityTimelineResponse = {
  race_id: string;
  replay_contract_version: string;
  prediction_contract_version: string;
  probability_timeline_contract_version: string;
  probability_semantics: string;
  model: V2ModelIdentity;
  timeline_identity: string;
  checkpoints: ProbabilityCheckpoint[];
  driver_series: DriverProbabilitySeries[];
};

// --- errors (mirror R4 {error, detail} + optional reason/pointers) ---

export type ReplayErrorCode =
  | "unknown_race"
  | "unknown_frame"
  | "not_prediction_checkpoint"
  | "prediction_unavailable"
  | "internal";

export type ReplayErrorBody = {
  error: string;
  detail?: string;
  reason?: string;
  previous_prediction_checkpoint_frame?: number | null;
  next_prediction_checkpoint_frame?: number | null;
};

export class V2ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly reason: string | null;
  readonly previousCheckpoint: number | null;
  readonly nextCheckpoint: number | null;

  constructor(status: number, body: ReplayErrorBody) {
    super(body.detail || body.error || `V2 request failed (${status})`);
    this.name = "V2ApiError";
    this.status = status;
    this.code = body.error;
    this.reason = body.reason ?? null;
    this.previousCheckpoint = body.previous_prediction_checkpoint_frame ?? null;
    this.nextCheckpoint = body.next_prediction_checkpoint_frame ?? null;
  }

  isUnavailable(): boolean {
    return this.status === 503 && this.code === "prediction_unavailable";
  }

  isNotCheckpoint(): boolean {
    return this.status === 404 && this.code === "not_prediction_checkpoint";
  }
}

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
  const body = (await res.json()) as T | ReplayErrorBody;
  if (!res.ok) {
    throw new V2ApiError(res.status, body as ReplayErrorBody);
  }
  return body as T;
}

const baseOf = (base?: string): string => base ?? V2_API_BASE;

// --- endpoints ---

export async function getV2Races(
  fetcher: FetchLike = fetch,
  base?: string,
): Promise<V2RaceList> {
  return readJson<V2RaceList>(fetcher, `${baseOf(base)}/v2/races`, {
    cache: "no-store",
  });
}

export async function getReplayTimelinePage(
  raceId: string,
  offset = 0,
  limit: number = REPLAY_PAGE_SIZE,
  fetcher: FetchLike = fetch,
  base?: string,
): Promise<ReplayTimelinePage> {
  const url =
    `${baseOf(base)}/v2/races/${encodeURIComponent(raceId)}/replay/timeline` +
    `?offset=${offset}&limit=${limit}`;
  return readJson<ReplayTimelinePage>(fetcher, url, { cache: "no-store" });
}

/** Sequential paginated load; validates dense 0..N-1 identity (R5-F). */
export async function fetchFullTimeline(
  raceId: string,
  fetcher: FetchLike = fetch,
  base?: string,
  pageSize: number = REPLAY_PAGE_SIZE,
): Promise<ReplayFrameMeta[]> {
  const first = await getReplayTimelinePage(raceId, 0, pageSize, fetcher, base);
  const total = first.total_frames;
  const frames: ReplayFrameMeta[] = [...first.frames];
  let offset = first.frames.length;
  while (offset < total) {
    const page = await getReplayTimelinePage(
      raceId,
      offset,
      pageSize,
      fetcher,
      base,
    );
    if (page.total_frames !== total || page.race_id !== raceId) {
      throw new Error("Replay timeline changed during pagination");
    }
    if (page.frames.length === 0) {
      throw new Error("Replay timeline truncated during pagination");
    }
    frames.push(...page.frames);
    offset += page.frames.length;
  }
  validateTimeline(frames, total, raceId);
  return frames;
}

/** Client-side identity guard: dense indices, no duplicates, no gaps. */
export function validateTimeline(
  frames: ReplayFrameMeta[],
  totalFrames: number,
  raceId: string,
): void {
  if (frames.length !== totalFrames) {
    throw new Error(
      `Replay timeline incomplete for ${raceId}: ` +
        `got ${frames.length} of ${totalFrames} frames`,
    );
  }
  for (let i = 0; i < frames.length; i++) {
    const frame = frames[i];
    if (frame.frame_index !== i || frame.race_id !== raceId) {
      throw new Error(
        `Replay timeline identity break for ${raceId} at position ${i}`,
      );
    }
  }
}

export async function getReplayFrame(
  raceId: string,
  frameIndex: number,
  fetcher: FetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<ReplayFrameResponse> {
  const url =
    `${baseOf(base)}/v2/races/${encodeURIComponent(raceId)}/replay/frames/` +
    `${frameIndex}`;
  return readJson<ReplayFrameResponse>(fetcher, url, {
    cache: "no-store",
    signal,
  });
}

export async function getReplayPrediction(
  raceId: string,
  frameIndex: number,
  fetcher: FetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<ReplayPredictionResponse> {
  const url =
    `${baseOf(base)}/v2/races/${encodeURIComponent(raceId)}` +
    `/replay/predictions/${frameIndex}`;
  return readJson<ReplayPredictionResponse>(fetcher, url, {
    cache: "no-store",
    signal,
  });
}

/** Complete cached probability series for one race (R6; 503 is nonfatal). */
export async function getReplayProbabilityTimeline(
  raceId: string,
  fetcher: FetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<ProbabilityTimelineResponse> {
  const url =
    `${baseOf(base)}/v2/races/${encodeURIComponent(raceId)}` +
    `/replay/probability-timeline`;
  return readJson<ProbabilityTimelineResponse>(fetcher, url, {
    cache: "no-store",
    signal,
  });
}
