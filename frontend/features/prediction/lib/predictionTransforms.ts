import type {
  EnsembleResult,
  EnsembleSummaryRow,
  SingleModelResult,
} from "@/lib/predictionTypes";
import type { ModelId, PredictionMode } from "@/lib/predictionTypes";

export type ChartPoint = { lap: number; value: number };

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
