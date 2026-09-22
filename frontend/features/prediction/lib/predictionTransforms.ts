import type {
  DriverRow,
  EnsembleResult,
  EnsembleSummaryRow,
  SingleModelResult,
} from "@/lib/predictionTypes";
import type { ModelId, PredictionMode } from "@/lib/predictionTypes";

export type ChartPoint = { lap: number; value: number };

// Normalised, display-only view of whichever prediction result is active.
// `modelKey` stays raw (backend spelling); components map it to a display
// name so this module keeps zero runtime imports and stays node:test-able.
export type PredictionLeader = {
  winner: string;
  winProbability: number;
  probabilityLabel: string;
  lap: number;
};

export type PredictionCheckpointRow = {
  lap: number;
  modelKey: string;
  predictedWinner: string;
  winProbability: number;
  actualWinner: string | null;
  actualRank: number | null;
};

export type PredictionFieldGroup = {
  modelKey: string;
  drivers: DriverRow[];
};

export type PredictionView = {
  mode: PredictionMode;
  event: string;
  year: number;
  leader: PredictionLeader;
  modeLabel: string;
  agreementCount: number | null;
  actualWinner: string | null;
  matched: boolean | null;
  decisionReason: string | null;
  field: PredictionFieldGroup[];
  checkpoints: PredictionCheckpointRow[];
};

// Pure view-model transforms extracted verbatim from app/page.tsx logic.
// No React, no fetch: covered by predictionTransforms.test.ts.

export function buildChartRows(
  mode: PredictionMode,
  model: ModelId,
  ensembleResult: EnsembleResult | null,
  singleResult: SingleModelResult | null,
): Record<string, ChartPoint[]> {
  if (mode === "ensemble" && ensembleResult) {
    const grouped: Record<string, ChartPoint[]> = {};
    for (const row of ensembleResult.summary) {
      if (!grouped[row.model]) grouped[row.model] = [];
      grouped[row.model].push({ lap: row.lap, value: row.win_probability });
    }
    Object.keys(grouped).forEach((k) =>
      grouped[k].sort((a, b) => a.lap - b.lap),
    );
    return grouped;
  }

  if (mode === "single" && singleResult) {
    return {
      [model.toUpperCase()]: singleResult.summary.map((row) => ({
        lap: row.lap,
        value: row.win_probability,
      })),
    };
  }

  return {};
}

export function groupEnsembleSummaryByLap(
  summary: EnsembleSummaryRow[],
): Record<number, EnsembleSummaryRow[]> {
  return summary.reduce<Record<number, EnsembleSummaryRow[]>>((acc, row) => {
    if (!acc[row.lap]) acc[row.lap] = [];
    acc[row.lap].push(row);
    return acc;
  }, {});
}

// Builds the shared result view-model from the active mode's result. Returns
// null until a matching result exists, so the page stays layout-only. This
// only selects/orders fields already returned by the API — it never computes,
// normalises or reinterprets a probability.
export function buildPredictionView(
  mode: PredictionMode,
  model: ModelId,
  event: string,
  year: number,
  ensembleResult: EnsembleResult | null,
  singleResult: SingleModelResult | null,
): PredictionView | null {
  if (mode === "ensemble" && ensembleResult) {
    const checkpoints = ensembleResult.summary
      .map((row) => ({
        lap: row.lap,
        modelKey: row.model,
        predictedWinner: row.predicted_winner,
        winProbability: row.win_probability,
        actualWinner: row.actual_winner,
        actualRank: row.actual_rank,
      }))
      .sort((a, b) => a.lap - b.lap || a.modelKey.localeCompare(b.modelKey));

    return {
      mode,
      event,
      year,
      leader: {
        winner: ensembleResult.final_winner,
        winProbability: ensembleResult.confidence_value,
        probabilityLabel: ensembleResult.confidence_label || "Confidence",
        lap: ensembleResult.latest_lap,
      },
      modeLabel: "Ensemble",
      agreementCount: ensembleResult.agreement_count,
      actualWinner: ensembleResult.actual_winner,
      matched: ensembleResult.actual_winner
        ? ensembleResult.final_winner === ensembleResult.actual_winner
        : null,
      decisionReason: ensembleResult.decision_reason,
      field: Object.entries(ensembleResult.latest_top5).map(
        ([modelKey, drivers]) => ({ modelKey, drivers }),
      ),
      checkpoints,
    };
  }

  if (mode === "single" && singleResult) {
    const modelKey = model.toUpperCase();
    const checkpoints = singleResult.summary.map((row) => ({
      lap: row.lap,
      modelKey,
      predictedWinner: row.predicted_winner,
      winProbability: row.win_probability,
      actualWinner: row.actual_winner,
      actualRank: row.actual_rank,
    }));

    return {
      mode,
      event,
      year,
      leader: {
        winner: singleResult.latest.predicted_winner,
        winProbability: singleResult.latest.predicted_win_probability,
        probabilityLabel: "Win probability",
        lap: singleResult.latest.lap,
      },
      modeLabel: "Single model",
      agreementCount: null,
      actualWinner: singleResult.latest.actual_winner,
      matched: singleResult.latest.actual_winner
        ? singleResult.latest.predicted_winner ===
          singleResult.latest.actual_winner
        : null,
      decisionReason: null,
      field: [{ modelKey, drivers: singleResult.latest.top5 }],
      checkpoints,
    };
  }

  return null;
}
