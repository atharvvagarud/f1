// Per-race frame corpus cache (V3.10D).
//
// The event-corpus fetch loads every factual frame once per race. Those
// responses are shared read-only with on-demand frame rendering so the same
// bytes are never fetched twice. Module-level, single-race: a new race
// replaces the entry. Stores full responses (replay viewing needs them);
// event derivation consumes small digests extracted separately.

import type { ReplayFrameResponse } from "@/lib/v2";

let entry: {
  raceId: string;
  frames: (ReplayFrameResponse | undefined)[];
  total: number;
} | null = null;

export function setFrameCorpus(
  raceId: string,
  frames: (ReplayFrameResponse | undefined)[],
  total: number,
): void {
  entry = { raceId, frames, total };
}

export function getCorpusFrame(
  raceId: string,
  frameIndex: number,
): ReplayFrameResponse | undefined {
  if (entry === null || entry.raceId !== raceId) return undefined;
  if (frameIndex < 0 || frameIndex >= entry.total) return undefined;
  return entry.frames[frameIndex];
}

export function clearFrameCorpus(): void {
  entry = null;
}
