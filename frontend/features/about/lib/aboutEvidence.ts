// P9-3 single typed evidence entry point for /about.
//
// The page and its components consume frozen static evidence ONLY through
// this module: `about.v1.json` validated by the P9-1 contract. Validation
// throws during development/build on contract drift; components never import
// raw JSON and never touch data artifacts, 2025 data, or backend APIs.
import aboutEvidenceJson from "@/data/about.v1.json";
import {
  validateAboutEvidence,
  type AboutEvidence,
} from "@/features/models/lib/evidence";

let cached: AboutEvidence | null = null;

export function getAboutEvidence(): AboutEvidence {
  if (!cached) {
    cached = validateAboutEvidence(aboutEvidenceJson);
  }
  return cached;
}
