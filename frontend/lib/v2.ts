// V2 replay API client (Phase-5 R5).
//
// Typed boundary over the frozen R4 replay routes. The frontend deals only
// in race_id / frame_index / ReplayFrame / RaceState / checkpoint metadata /
// cached PredictionSnapshot — it never recreates anchor grouping,
// representative selection, reconstruction, checkpoint selection, or any
// probability transform. Backend contracts are authoritative.
//
// No `any` in core replay contracts. fetch is injectable for tests.

// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { API_BASE, readJson as readSharedJson, resolveBase as sharedResolveBase, type FetchLike as SharedFetchLike } from "./http.ts";

export const V2_API_BASE = API_BASE;

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

// --- E4 local (per-checkpoint, per-driver) explanation ---
//
// Additive, read-only decomposition of one frozen winner score in model
// log-odds. Contributions are NEVER win-probability increments and are never
// normalized; the top-N view is a compact display that does not reconstruct
// the prediction by itself (the full canonical vector does).

export type LocalContribution = {
  canonical_feature: string;
  feature_family: string;
  feature_type: string;
  raw_value: string | number | boolean | null;
  input_state: string;
  imputed_value: string | number | boolean | null;
  active_category: string | null;
  log_odds_contribution: number;
  direction: string;
};

export type LocalExplanationIdentity = {
  race_id: string;
  frame_index: number;
  driver_id: string;
  checkpoint_reasons: string[];
  leader_lap: number | null;
  state_time_s: number;
  anchor_driver_id: string;
  anchor_lap_number: number;
  anchor_state_time_s: number;
  feature_identity: {
    race_id: string;
    driver_id: string;
    lap_number: number;
    state_time_s: number;
  };
  observation: {
    observed_lap_number: number;
    observed_time_s: number;
    observation_age_s: number | null;
    observed_position: number | null;
  };
};

export type LocalExplanationModelIdentity = {
  feature_set: string;
  feature_set_version: string;
  estimator_class: string;
  specification_fingerprint: string;
  transformed_dim: number;
  canonical_feature_count: number;
  calibration_method: string;
  probability_kind: string;
  probability_semantics: string;
  training_seasons: number[];
  sklearn_version: string;
};

export type LocalExplanationResponse = {
  contract_version: string;
  format: string;
  identity: LocalExplanationIdentity;
  model_identity: LocalExplanationModelIdentity;
  probability_semantics: string;
  explanation_space: string;
  intercept: number;
  logit: number;
  probability: number;
  model_probability: number;
  cached_probability: number | null;
  reconstruction: {
    estimator_decision_function: number;
    residual: number;
    logit_abs_tolerance: number;
    probability_abs_tolerance: number;
    transformed_contribution_sum: number;
    canonical_contribution_sum: number;
  };
  transformed_feature_count: number;
  canonical_feature_count: number;
  top_positive: LocalContribution[];
  top_negative: LocalContribution[];
  accounting: {
    top_n: number;
    total_positive_log_odds: number;
    total_negative_log_odds: number;
    shown_positive_log_odds: number;
    shown_negative_log_odds: number;
    omitted_positive_log_odds: number;
    omitted_negative_log_odds: number;
    positive_feature_count: number;
    negative_feature_count: number;
    full_decomposition_reconstructs_prediction: boolean;
    top_n_reconstructs_prediction: boolean;
    note: string;
  };
  limitations: string[];
  cache_status: string;
};

// --- E5 prediction-change (timeline) explanation ---
//
// Exact change in one frozen winner score between two REAL checkpoints A -> B.
// Contribution deltas are additive model log-odds changes; the top-N view is a
// compact display that does not reconstruct the change by itself (the full
// canonical change vector does). The overall probability delta is an aggregate
// model-prediction change in percentage points and is NEVER decomposed into
// per-feature percentage-point shares.

export type TimelineChangeStatus =
  | "AVAILABLE"
  | "NO_PREVIOUS_CHECKPOINT"
  | "COMPARISON_UNAVAILABLE";

export type TimelineChangeCheckpointIdentity = {
  frame_index: number;
  state_time_s: number;
  leader_lap: number | null;
  reasons: string[];
  anchor_driver_id: string | null;
  anchor_lap_number: number | null;
  anchor_state_time_s: number | null;
  observed_lap_number: number | null;
  observed_time_s: number | null;
  observed_position: number | null;
  observation_age_s: number | null;
};

export type TimelineChangeIdentity = {
  race_id: string;
  driver_id: string;
  from_frame_index: number | null;
  to_frame_index: number;
  from_checkpoint: TimelineChangeCheckpointIdentity | null;
  to_checkpoint: TimelineChangeCheckpointIdentity;
};

export type TimelineChangeContribution = {
  canonical_feature: string;
  feature_family: string;
  feature_type: string;
  from_raw_value: string | number | boolean | null;
  to_raw_value: string | number | boolean | null;
  from_input_state: string;
  to_input_state: string;
  from_active_category: string | null;
  to_active_category: string | null;
  from_contribution: number;
  to_contribution: number;
  contribution_delta: number;
  transition: string;
};

export type TimelineChangeAccounting = {
  top_n: number;
  total_positive_log_odds_delta: number;
  total_negative_log_odds_delta: number;
  shown_positive_log_odds_delta: number;
  shown_negative_log_odds_delta: number;
  omitted_positive_log_odds_delta: number;
  omitted_negative_log_odds_delta: number;
  positive_feature_count: number;
  negative_feature_count: number;
  full_decomposition_reconstructs_change: boolean;
  top_n_reconstructs_change: boolean;
  note: string;
};

export type TimelineChangeResponse = {
  contract_version: string;
  format: string;
  status: TimelineChangeStatus;
  identity: TimelineChangeIdentity;
  model_identity: LocalExplanationModelIdentity | null;
  probability_semantics: string;
  explanation_space: string;
  reason: string | null;
  from_probability: number | null;
  to_probability: number | null;
  probability_delta: number | null;
  from_logit: number | null;
  to_logit: number | null;
  logit_delta: number | null;
  cached_from_probability: number | null;
  cached_to_probability: number | null;
  reconstruction: {
    from_logit: number;
    to_logit: number;
    logit_delta: number;
    canonical_delta_sum: number;
    residual: number;
    logit_abs_tolerance: number;
    probability_abs_tolerance: number;
    intercept_cancels: boolean;
    full_decomposition_reconstructs_change: boolean;
  } | null;
  canonical_feature_count: number | null;
  top_positive: TimelineChangeContribution[];
  top_negative: TimelineChangeContribution[];
  accounting: TimelineChangeAccounting | null;
  limitations: string[];
  cache_status: string;
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
    (status, body) => new V2ApiError(status, body as ReplayErrorBody),
  );
}

const baseOf = (base?: string): string => sharedResolveBase(base);

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

/** Exact local log-odds explanation for one cached checkpoint driver (E4). */
export async function getReplayExplanation(
  raceId: string,
  frameIndex: number,
  driverId: string,
  fetcher: FetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<LocalExplanationResponse> {
  const url =
    `${baseOf(base)}/v2/replay/${encodeURIComponent(raceId)}` +
    `/frames/${frameIndex}/predictions/` +
    `${encodeURIComponent(driverId)}/explanation`;
  return readJson<LocalExplanationResponse>(fetcher, url, {
    cache: "no-store",
    signal,
  });
}

/** Exact change in the frozen score since the previous checkpoint (E5). */
export async function getReplayPredictionChange(
  raceId: string,
  frameIndex: number,
  driverId: string,
  fetcher: FetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<TimelineChangeResponse> {
  const url =
    `${baseOf(base)}/v2/replay/${encodeURIComponent(raceId)}` +
    `/frames/${frameIndex}/predictions/` +
    `${encodeURIComponent(driverId)}/change`;
  return readJson<TimelineChangeResponse>(fetcher, url, {
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

// --- V3.10F driver telemetry (historical evidence, causally sliced client-side) ---
//
// Typed boundary over GET /v2/races/{race_id}/replay/telemetry. One
// race-scoped read-only request serves every driver's completed-lap and
// stint evidence; the causal (<=T) slicing happens in the pure selector
// (features/pit-wall/lib/telemetry.ts), never here. Values pass through
// verbatim: no reference, delta, validity, or model computation.

export type TelemetryLapPoint = {
  driver_id: string;
  lap_number: number;
  observed_at_s: number;
  lap_time_s: number | null;
  sector_1_s: number | null;
  sector_2_s: number | null;
  sector_3_s: number | null;
  compound: string | null;
  tyre_life: number | null;
  stint_number: number | null;
  stint_lap: number | null;
  fresh_tyre: boolean | null;
  pit_entry: boolean | null;
  pit_exit: boolean | null;
  track_status: string | null;
  deleted: boolean | null;
  is_accurate: boolean | null;
  fastf1_generated: boolean | null;
};

export type TelemetryStintPoint = {
  driver_id: string;
  stint_number: number;
  compound: string | null;
  fresh_tyre: boolean | null;
  start_lap: number | null;
  end_lap: number | null;
  start_observed_at_s: number | null;
  end_observed_at_s: number | null;
  pit_in_lap: number | null;
  pit_out_lap: number | null;
  tyre_age_at_start: number | null;
};

export type TelemetryResponse = {
  race_id: string;
  telemetry_contract_version: string;
  lap_count: number;
  stint_count: number;
  laps: TelemetryLapPoint[];
  stints: TelemetryStintPoint[];
};

/** One race-scoped telemetry load (cache per race in the caller). */
export async function getRaceTelemetry(
  raceId: string,
  fetcher: FetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<TelemetryResponse> {
  const url =
    `${baseOf(base)}/v2/races/${encodeURIComponent(raceId)}` +
    `/replay/telemetry`;
  return readJson<TelemetryResponse>(fetcher, url, {
    cache: "no-store",
    signal,
  });
}

// --- R8 Monte Carlo simulator (Phase-6) ---
//
// Typed boundary over POST /v2/simulations/race. The server reconstructs the
// factual state from the exact anchor and owns the science; the frontend only
// sends an anchor + count + optional seed and renders the aggregate. Probabilities
// are MONTE_CARLO_FREQUENCY outcome frequencies passed through verbatim: never
// normalized, summed, or re-scaled here.

export type SimulationAnchor = {
  race_id: string;
  anchor_driver_id: string;
  anchor_lap_number: number;
  anchor_state_time_s: number;
};

export type SimulationRequest = SimulationAnchor & {
  simulation_count: number;
  master_seed?: number;
};

export type PositionFrequency = {
  position: number | null;
  frequency: number;
};

export type DriverSimulationSummary = {
  driver_id: string;
  win_probability: number;
  podium_probability: number;
  expected_finish: number;
  finish_position_distribution: PositionFrequency[];
  dnf_probability: number | null;
  points_probability: number | null;
  expected_points: number | null;
};

export type SimulationRuntime = {
  reconstruction_s: number;
  adaptation_s: number;
  simulation_s: number;
  total_s: number;
};

export type SimulationResponse = {
  race_id: string;
  anchor_driver_id: string;
  anchor_lap_number: number;
  anchor_state_time_s: number;
  simulation_contract_version: string;
  engine_version: string;
  monte_carlo_version: string;
  pit_dynamics_version: string;
  mechanics: string[];
  probability_semantics: string;
  probability_semantics_note: string;
  parameter_set_id: string;
  parameter_version: string;
  parameter_hash: string;
  simulation_request_identity: string;
  scientific_result_identity: string;
  requested_simulation_count: number;
  valid_simulations: number;
  invalid_simulations: number;
  master_seed: number;
  engine_runtime_s: number;
  runtime: SimulationRuntime;
  drivers: DriverSimulationSummary[];
};

export type SimulationErrorBody = {
  error: string;
  detail?: string;
  reason?: string;
};

/** Run one historical-state Monte Carlo simulation (exact anchor, no JSON state). */
export async function postRaceSimulation(
  request: SimulationRequest,
  fetcher: FetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<SimulationResponse> {
  return readJson<SimulationResponse>(
    fetcher,
    `${baseOf(base)}/v2/simulations/race`,
    {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
    },
  );
}

/** True when a 422 is the stable un-simulatable-state contract (never a fallback). */
export function isSimulationUnsupported(error: unknown): boolean {
  return (
    error instanceof V2ApiError &&
    error.status === 422 &&
    error.code === "simulation_unsupported"
  );
}

// --- S7 strategy comparison (Phase-7) ---
//
// Typed boundary over POST /v2/strategies/compare. The server reconstructs the
// exact anchor, runs the frozen S1–S6 Strategy Engine (one shared baseline +
// paired candidate arms), and returns compact aggregates, paired deltas and
// selected-objective sampling uncertainty. Per-index outcomes never cross this
// boundary. All probabilities are MONTE_CARLO_FREQUENCY outcome frequencies
// passed through verbatim: never normalized, summed, or re-scaled here.

export type StrategyAction = "STAY_OUT" | "PIT_NOW" | "PIT_NEXT_LAP";
export type StrategyCompound = "SOFT" | "MEDIUM" | "HARD";
export type StrategyObjective =
  | "MAXIMIZE_WIN_PROBABILITY"
  | "MAXIMIZE_PODIUM_PROBABILITY"
  | "MINIMIZE_EXPECTED_FINISH";

export type StrategyCandidateSelection = {
  action: StrategyAction;
  requested_compound?: StrategyCompound | null;
};

export type StrategyCompareRequest = SimulationAnchor & {
  target_driver_id: string;
  objective: StrategyObjective;
  simulation_count: number;
  master_seed?: number;
  candidates?: StrategyCandidateSelection[];
};

export type StrategyPositionFrequency = {
  position: number | null;
  frequency: number;
};

export type StrategyBaseline = {
  valid_simulations: number;
  invalid_simulations: number;
  win_probability: number;
  podium_probability: number;
  expected_finish: number;
  finish_position_distribution: StrategyPositionFrequency[];
};

export type StrategyUncertainty = {
  point_estimate: number | null;
  paired_se: number | null;
  ci_low: number | null;
  ci_high: number | null;
  classification:
    | "IMPROVEMENT"
    | "DEGRADATION"
    | "INCONCLUSIVE"
    | "UNCERTAINTY_UNAVAILABLE";
  availability: string;
  valid_pairs: number;
};

export type StrategyExecution = {
  applied_rate: number;
  suppressed_rate: number;
  superseded_rate: number;
  inert_rate: number;
  race_end_cancelled_rate: number;
};

export type StrategyCandidateResult = {
  candidate_key: string;
  candidate_identity: string;
  action: string;
  requested_compound: string | null;
  valid: boolean;
  reason: string | null;
  evaluated: boolean;
  win_probability: number | null;
  podium_probability: number | null;
  expected_finish: number | null;
  finish_position_distribution: StrategyPositionFrequency[];
  delta_win_probability: number | null;
  delta_podium_probability: number | null;
  delta_expected_finish: number | null;
  uncertainty: StrategyUncertainty | null;
  execution: StrategyExecution | null;
};

export type StrategyObjectiveAnalysis = {
  objective: string;
  metric: string;
  leader_by_point_estimate: string | null;
  indistinguishable_from_leader: string[];
  distinguishable_from_leader: string[];
  point_estimate_order: string[];
};

export type StrategyCompareResponse = {
  strategy_contract_version: string;
  intervention_version: string;
  comparison_version: string;
  objective_version: string;
  uncertainty_version: string;
  race_id: string;
  anchor_driver_id: string;
  anchor_lap_number: number;
  anchor_state_time_s: number;
  target_driver_id: string;
  simulation_count: number;
  master_seed: number;
  objective: string;
  metric: string;
  probability_semantics: string;
  counterfactual_semantics: string;
  crn_policy: string;
  comparison_identity: string;
  baseline: StrategyBaseline | null;
  supported: boolean;
  unsupported_reason: string | null;
  candidates: StrategyCandidateResult[];
  objective_analysis: StrategyObjectiveAnalysis | null;
  limitations: string[];
  runtime: SimulationRuntime;
};

/** Run one exact-anchor strategy comparison (explicit user action only). */
export async function postStrategyCompare(
  request: StrategyCompareRequest,
  fetcher: FetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<StrategyCompareResponse> {
  return readJson<StrategyCompareResponse>(
    fetcher,
    `${baseOf(base)}/v2/strategies/compare`,
    {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
    },
  );
}

/** True when a 422 is the stable strategy-request validation contract. */
export function isStrategyRequestInvalid(error: unknown): boolean {
  return (
    error instanceof V2ApiError &&
    error.status === 422 &&
    error.code === "strategy_request_invalid"
  );
}

// --- Strategy 2.0 comparison (V3.6F) ---
//
// Typed boundary over POST /v2/strategies/compare-v3 and
// GET /v2/strategies/v3/availability. The server runs (live) or serves
// (cached) the frozen V3.6C paired-MC2 engine: one simulated
// no-intervention reference plus one arm per valid alternative, 5000
// paired futures in production. Per-index outcomes never cross this
// boundary. Values pass through verbatim: the frontend formats, sorts
// and labels only — it never re-derives estimates, intervals, leaders
// or execution rates.

export type Strategy2Mode = "live" | "cached";

export type Strategy2AlternativeSelection = {
  action: StrategyAction;
  requested_compound?: StrategyCompound | null;
};

export type Strategy2CompareRequest = SimulationAnchor & {
  target_driver_id: string;
  alternatives?: Strategy2AlternativeSelection[];
  master_seed?: number;
  mode: Strategy2Mode;
};

export type Strategy2ArmAggregate = {
  valid_pairs: number;
  win_frequency: number;
  podium_frequency: number;
  top5_frequency: number;
  top10_frequency: number;
  expected_finish: number;
  median_finish: number;
  finish_q25: number;
  finish_q75: number;
  finish_position_distribution: StrategyPositionFrequency[];
  roster_size: number;
};

export type Strategy2Delta = {
  metric: string;
  point_estimate: number | null;
  paired_se: number | null;
  ci_low: number | null;
  ci_high: number | null;
  availability: string;
  valid_pairs: number;
  uncertainty_semantics: string;
  interval_label: string;
};

export type Strategy2Execution = {
  total: number;
  applied: number;
  suppressed: number;
  superseded: number;
  inert: number;
  race_end_cancelled: number;
  baseline_pit_suppressed: number;
  applied_rate: number;
  suppressed_rate: number;
  superseded_rate: number;
  inert_rate: number;
  race_end_cancelled_rate: number;
};

export type Strategy2ComparisonKey = {
  key_version: string;
  race_id: string;
  decision_lap: number;
  state_identity: string;
  target_driver_id: string;
  reference_kind: string;
  alternative_identity: string;
  simulator_identity: string;
  parameter_identity: string;
  simulation_count: number;
  master_seed: number;
  outcome_schema_version: string;
};

export type Strategy2AlternativeResult = {
  candidate_key: string;
  candidate_identity: string;
  action: string;
  requested_compound: string | null;
  evaluated: boolean;
  reason: string | null;
  reference_aggregate: Strategy2ArmAggregate | null;
  alternative_aggregate: Strategy2ArmAggregate | null;
  deltas: Strategy2Delta[];
  execution: Strategy2Execution | null;
  requested_pairs: number;
  complete_pairs: number;
  excluded_pairs: number;
  comparison_key: Strategy2ComparisonKey | null;
  comparison_identity: string | null;
};

export type Strategy2CompareResponse = {
  engine_version: string;
  execution_contract_version: string;
  outcome_schema_version: string;
  strategy_identity: string;
  state_identity: string;
  parameter_identity: string;
  config_identity: string;
  master_seed: number;
  simulation_count: number;
  race_id: string;
  anchor_driver_id: string;
  anchor_lap_number: number;
  anchor_state_time_s: number;
  target_driver_id: string;
  supported: boolean;
  unsupported_reason: string | null;
  reference_kind: string;
  alternatives: Strategy2AlternativeResult[];
  leaders: Record<string, string | null>;
  provenance: Record<string, unknown>;
  execution_source: "live_engine" | "cache";
  cache_key: string | null;
  runtime: SimulationRuntime;
};

export type Strategy2AvailabilityEntry = {
  race_id: string;
  anchor_driver_id: string;
  anchor_lap_number: number;
  anchor_state_time_s: number;
  target_driver_id: string;
  master_seed: number;
  simulation_count: number;
  supported: boolean;
  alternative_count: number;
  comparison_identities: string[];
  cache_key: string;
};

export type Strategy2Availability = {
  engine_version: string;
  execution_contract_version: string;
  outcome_schema_version: string;
  manifest_schema: string;
  entry_count: number;
  entries: Strategy2AvailabilityEntry[];
};

/**
 * Run (live) or serve (cached) one Strategy 2.0 comparison. Callers must
 * pass mode explicitly; the page default is "cached" — ordinary page
 * interaction never triggers a multi-minute live simulation.
 * No simulation count is ever sent: production is fixed at 5000 by contract.
 */
export async function postStrategyV3Compare(
  request: Strategy2CompareRequest,
  fetcher: FetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<Strategy2CompareResponse> {
  return readJson<Strategy2CompareResponse>(
    fetcher,
    `${baseOf(base)}/v2/strategies/compare-v3`,
    {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
    },
  );
}

/** Deterministic catalogue of cached Strategy 2.0 comparisons. */
export async function getStrategyV3Availability(
  fetcher: FetchLike = fetch,
  base?: string,
  raceId?: string,
  signal?: AbortSignal,
): Promise<Strategy2Availability> {
  const query = raceId ? `?race_id=${encodeURIComponent(raceId)}` : "";
  return readJson<Strategy2Availability>(
    fetcher,
    `${baseOf(base)}/v2/strategies/v3/availability${query}`,
    { cache: "no-store", signal },
  );
}

/** True when a 422 is the stable Strategy 2.0 request-validation contract. */
export function isStrategyV3RequestInvalid(error: unknown): boolean {
  return (
    error instanceof V2ApiError &&
    error.status === 422 &&
    error.code === "strategy_v3_request_invalid"
  );
}

/** True when the response is the explicit cache-miss product state. */
export function isStrategyV3CacheMiss(error: unknown): boolean {
  return (
    error instanceof V2ApiError &&
    error.status === 404 &&
    error.code === "cache_miss"
  );
}

// --- Counterfactual comparison (V3.7F) ---
//
// Typed boundary over POST /v2/counterfactuals/compare and
// GET /v2/counterfactuals/availability. The server compares simulated
// outcomes under a controlled PIT_IN_N_LAPS intervention plan against
// the simulated no-intervention reference (or plan A vs plan B), 5000
// paired futures in production. Values pass through verbatim: the
// frontend formats and labels only — it never re-derives estimates,
// intervals, orientations, or lifecycle counts, and it never sends a
// simulation count, seed, or live/compute-mode flag (the server owns
// live-compute authorization; there is no such request field).

export type CounterfactualCompound = "SOFT" | "MEDIUM" | "HARD" | "SAMPLED";
export type CounterfactualForm = "REFERENCE_VS_PLAN" | "PLAN_VS_PLAN";

export type CounterfactualIntervention = {
  target_driver_id: string;
  kind: "PIT_IN_N_LAPS";
  lap_offset_n: number;
  requested_compound?: CounterfactualCompound;
};

export type CounterfactualPlan = {
  target_driver_ids: string[];
  interventions: CounterfactualIntervention[];
};

export type CounterfactualCompareRequest = SimulationAnchor & {
  comparison_form: CounterfactualForm;
  base_plan?: CounterfactualPlan | null;
  alternative_plan: CounterfactualPlan;
  rival_driver_id?: string | null;
};

export type CounterfactualAvailabilityDriver = {
  driver_id: string;
  position: number | null;
  decision_lap: number;
  remaining_laps: number;
  eligible_n_min: number | null;
  eligible_n_max: number | null;
  eligible: boolean;
  compound: string | null;
  status: string;
};

export type CounterfactualAvailability = {
  api_schema: string;
  supported: boolean;
  level: string | null;
  reason_code: string | null;
  human_reason: string | null;
  state_identity: string | null;
  race_id: string;
  anchor_driver_id: string;
  anchor_lap_number: number;
  anchor_state_time_s: number;
  season: number | null;
  scheduled_laps: number | null;
  leader_laps_done: number | null;
  drivers: CounterfactualAvailabilityDriver[];
  eligible_targets: string[];
  supported_compounds: string[];
  comparison_forms: string[];
  multi_stop_capable: boolean;
  multi_driver_capable: boolean;
  rival_candidates: string[];
  cached_comparison_identities: string[];
  live_enabled: boolean;
  provenance: Record<string, unknown>;
  limitations: string;
};

export type CounterfactualAggregate = {
  target_driver_id: string;
  n: number;
  win_frequency: number;
  podium_frequency: number;
  top5_frequency: number;
  top10_frequency: number;
  expected_finish: number;
  median_finish: number;
  finish_q25: number;
  finish_q75: number;
  finish_position_distribution: { finish_position: number; frequency: number }[];
  downside_vs_other: number | null;
  p_ahead_of_rival: number | null;
  expected_pit_count: number;
  expected_position_gain: number | null;
};

export type CounterfactualDelta = {
  metric: string;
  point_estimate: number | null;
  paired_se: number | null;
  ci_low: number | null;
  ci_high: number | null;
};

export type CounterfactualRuntime = {
  reconstruction_s: number;
  adaptation_s: number;
  simulation_s: number;
  analysis_s: number;
  total_s: number;
};

export type CounterfactualCompareResponse = {
  api_schema: string;
  supported: boolean;
  level: string | null;
  reason_code: string | null;
  human_reason: string | null;
  comparison_form: string | null;
  comparison_identity: string | null;
  base_identity: string | null;
  alternative_identity: string | null;
  state_identity: string | null;
  parameter_identity: string | null;
  config_identity: string | null;
  master_seed: number | null;
  simulation_count: number | null;
  race_id: string;
  anchor_driver_id: string;
  anchor_lap_number: number;
  anchor_state_time_s: number;
  target_driver_ids: string[];
  primary_target_driver_id: string | null;
  rival_driver_id: string | null;
  base_aggregate: CounterfactualAggregate | null;
  alternative_aggregate: CounterfactualAggregate | null;
  deltas: Record<string, CounterfactualDelta>;
  complete_pairs: number | null;
  requested_pairs: number | null;
  excluded_pairs: number | null;
  lifecycle_summary: Record<string, Record<string, number>>;
  provenance: Record<string, unknown>;
  limitations: string;
  execution_source: "live_engine" | "cache" | null;
  cache_key: string | null;
  runtime: CounterfactualRuntime | null;
};

/**
 * Compare simulated outcomes under a controlled intervention plan.
 * Cache-first server-side; no count/seed/mode is ever sent.
 */
export async function postCounterfactualCompare(
  request: CounterfactualCompareRequest,
  fetcher: FetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<CounterfactualCompareResponse> {
  return readJson<CounterfactualCompareResponse>(
    fetcher,
    `${baseOf(base)}/v2/counterfactuals/compare`,
    {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request),
      signal,
    },
  );
}

/** Cheap factual availability for one exact anchor (never simulates). */
export async function getCounterfactualAvailability(
  anchor: SimulationAnchor,
  fetcher: FetchLike = fetch,
  base?: string,
  signal?: AbortSignal,
): Promise<CounterfactualAvailability> {
  const query =
    `?race_id=${encodeURIComponent(anchor.race_id)}` +
    `&anchor_driver_id=${encodeURIComponent(anchor.anchor_driver_id)}` +
    `&anchor_lap_number=${encodeURIComponent(String(anchor.anchor_lap_number))}` +
    `&anchor_state_time_s=${encodeURIComponent(String(anchor.anchor_state_time_s))}`;
  return readJson<CounterfactualAvailability>(
    fetcher,
    `${baseOf(base)}/v2/counterfactuals/availability${query}`,
    { cache: "no-store", signal },
  );
}

/** True when a 422 is the stable counterfactual request-validation contract. */
export function isCounterfactualRequestInvalid(error: unknown): boolean {
  return (
    error instanceof V2ApiError &&
    error.status === 422 &&
    error.code === "counterfactual_request_invalid"
  );
}

/** True when the response is the explicit cache-miss product state. */
export function isCounterfactualCacheMiss(error: unknown): boolean {
  return (
    error instanceof V2ApiError &&
    error.status === 404 &&
    error.code === "cache_miss"
  );
}

/** True when the race is outside the served 2018–2024 registry. */
export function isCounterfactualUnknownRace(error: unknown): boolean {
  return (
    error instanceof V2ApiError &&
    error.status === 404 &&
    error.code === "unknown_race"
  );
}
