// @ts-expect-error TS5097 (.ts extension for node type-stripping)
import { API_BASE } from "./http.ts";

// Legacy R4 prediction client: thin wrapper over the shared base URL.
// Failure semantics are intentionally legacy (plain Error with a fixed
// per-endpoint message, no body parsing on !ok) and pinned by
// lib/api.test.ts — do not "upgrade" this module to V2ApiError.
// `any` preserves the legacy untyped surface (res.json() was any).
async function readLegacyJson(
  url: string,
  init: RequestInit | undefined,
  message: string,
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
): Promise<any> {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(message);
  return res.json();
}

export async function getRaces() {
  return readLegacyJson(
    `${API_BASE}/races`,
    { cache: "no-store" },
    "Failed to load races",
  );
}

export async function predictEnsemble(year: number, event: string) {
  return readLegacyJson(
    `${API_BASE}/predict/ensemble`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ year, event }),
    },
    "Failed to predict ensemble",
  );
}

export async function predictSingleModel(
  year: number,
  event: string,
  model: string,
) {
  return readLegacyJson(
    `${API_BASE}/predict/single-model`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ year, event, model }),
    },
    "Failed to predict single model",
  );
}
