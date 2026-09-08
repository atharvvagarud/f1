export type Race = {
  year: number;
  event_name: string;
};

export type EnsembleSummaryRow = {
  lap: number;
  model: string;
  predicted_winner: string;
  win_probability: number;
  actual_winner: string | null;
  actual_rank: number | null;
};

export type DriverRow = {
  driver: string;
  driver_number: number;
  win_probability: number;
  position_x: number;
  gap_to_leader_seconds: number;
  compound_x: string;
  tyre_life_x: number;
  stint_x: number;
};

export type EnsembleResult = {
  summary: EnsembleSummaryRow[];
  latest_lap: number;
  final_winner: string;
  decision_reason: string;
  actual_winner: string | null;
  agreement_count: number;
  confidence_value: number;
  confidence_label: string;
  latest_top5: Record<string, DriverRow[]>;
};

export type SingleSummaryRow = {
  lap: number;
  predicted_winner: string;
  win_probability: number;
  actual_winner: string | null;
  actual_rank: number | null;
};

export type SingleLatest = {
  model: string;
  lap: number;
  predicted_winner: string;
  predicted_driver_number: number;
  predicted_win_probability: number;
  actual_winner: string | null;
  actual_rank: number | null;
  top5: DriverRow[];
};

export type SingleModelResult = {
  summary: SingleSummaryRow[];
  latest: SingleLatest;
};

export type MainTab = "overview" | "table" | "chart" | "drivers";

export type PredictionMode = "ensemble" | "single";

export type ModelId = "logreg" | "hgb" | "xgboost";