import type { ModelId, PredictionMode } from "@/lib/predictionTypes";

// The exact request context a prediction result belongs to. A displayed result
// must always correspond to the current selection: changing season, Grand Prix,
// mode or model invalidates the previous result instead of re-labelling it.
// Pure and React-free so the rule is characterisation-tested directly
// (UI6 stale-result fix).

export type PredictionSelection = {
  year: number;
  event: string;
  mode: PredictionMode;
  model: ModelId;
};

/** A result belongs to the exact selection that produced it, and nothing else. */
export function sameSelection(
  a: PredictionSelection | null,
  b: PredictionSelection | null,
): boolean {
  if (a === null || b === null) return false;
  return (
    a.year === b.year &&
    a.event === b.event &&
    a.mode === b.mode &&
    a.model === b.model
  );
}
