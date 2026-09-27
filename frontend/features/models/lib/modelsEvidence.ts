// P9-2 single typed evidence entry point for /models.
//
// The page and its components consume frozen static evidence ONLY through
// this module: `models.v1.json` validated by the P9-1 contract. Validation
// throws during development/build on contract drift; components never import
// raw JSON and never touch Model Lab artifacts, 2025 data, or backend APIs.
import modelsEvidenceJson from "@/data/models.v1.json";
import {
  validateModelsEvidence,
  type ModelsEvidence,
} from "@/features/models/lib/evidence";

let cached: ModelsEvidence | null = null;

export function getModelsEvidence(): ModelsEvidence {
  if (!cached) {
    cached = validateModelsEvidence(modelsEvidenceJson);
  }
  return cached;
}
