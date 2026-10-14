// Event corpus hook (V3.10D).
//
// Per-race follower (mount with key={raceId}, like usePitWallRace): fetches
// every factual frame once with bounded concurrency, shares responses with
// on-demand rendering via the frame corpus, and memoizes the ordered event
// index. Historical read-only replay endpoints only, scoped to the active
// race. No per-driver requests, no science endpoints.
//
// Honesty rules: the corpus is valid only when EVERY frame loads (a gapped
// corpus fails loudly in buildEventIndex). Partial loads surface as
// "unavailable" with retry — never as a partial event set.

"use client";

import { useEffect, useRef, useState } from "react";
import {
  getReplayFrame,
  type ReplayFrameResponse,
} from "@/lib/v2";
import {
  buildEventIndex,
  type EventIndex,
  type FrameDigest,
} from "@/features/pit-wall/lib/events";
import { setFrameCorpus } from "@/features/pit-wall/lib/frameCorpus";

const CORPUS_CONCURRENCY = 6;

export type CorpusStatus =
  | "loading"
  | "ready"
  | "unavailable";

export function digestOf(response: ReplayFrameResponse): FrameDigest {
  const pits: Record<string, number> = {};
  for (const driver of response.state.drivers) {
    if (driver.pit_stops_completed_so_far !== null) {
      pits[driver.driver_id] = driver.pit_stops_completed_so_far;
    }
  }
  return {
    frameIndex: response.frame.frame_index,
    anchorStateTimeS: response.frame.anchor_state_time_s,
    leaderLap: response.leader_lap,
    trackState: response.state.race_control.track_state,
    messageCategory: response.state.race_control.last_message_category,
    messageFlag: response.state.race_control.last_message_flag,
    pits,
  };
}

async function fetchCorpus(
  raceId: string,
  total: number,
  signal: AbortSignal,
  onProgress: (loaded: number) => void,
): Promise<(ReplayFrameResponse | undefined)[]> {
  const out: (ReplayFrameResponse | undefined)[] = new Array(total);
  let next = 0;
  let loaded = 0;
  const worker = async (): Promise<void> => {
    while (!signal.aborted) {
      const i = next;
      next += 1;
      if (i >= total) return;
      out[i] = await getReplayFrame(raceId, i, fetch, undefined, signal);
      loaded += 1;
      onProgress(loaded);
    }
  };
  const lanes = Math.max(1, Math.min(CORPUS_CONCURRENCY, total));
  await Promise.all(
    Array.from({ length: lanes }, () => worker()),
  );
  return out;
}

// Module-level index cache: one entry per race, shared across mounts.
const indexCache = new Map<string, EventIndex>();

export function usePitWallEvents(raceId: string, totalFrames: number) {
  const [fetchedIndex, setFetchedIndex] = useState<EventIndex | null>(null);
  const [fetchedStatus, setFetchedStatus] =
    useState<CorpusStatus>("loading");
  const [fetchedProgress, setFetchedProgress] = useState({
    loaded: 0,
    total: 0,
  });
  const [retryNonce, setRetryNonce] = useState(0);
  const mountedRef = useRef(true);

  useEffect(() => {
    mountedRef.current = true;
    return () => {
      mountedRef.current = false;
    };
  }, []);

  // The module index cache is read during render: a warm entry resolves
  // with zero effects and zero fetches. The fetch effect below only runs
  // for cold races, keeping every setState inside async continuations or
  // event handlers.
  const warm = totalFrames > 0 ? indexCache.get(raceId) : undefined;
  const warmValid =
    warm !== undefined && warm.totalFrames === totalFrames ? warm : null;
  const index = warmValid ?? fetchedIndex;
  const status: CorpusStatus = warmValid ? "ready" : fetchedStatus;
  const progress =
    warmValid !== null
      ? { loaded: totalFrames, total: totalFrames }
      : fetchedProgress;

  useEffect(() => {
    if (totalFrames <= 0) return;
    if (warmValid) return;
    const controller = new AbortController();
    const signal = controller.signal;
    let cancelled = false;
    fetchCorpus(raceId, totalFrames, signal, (loaded) => {
      if (!cancelled && mountedRef.current) {
        setFetchedProgress({ loaded, total: totalFrames });
      }
    })
      .then((frames) => {
        if (cancelled || !mountedRef.current) return;
        // Dense-domain guard: every slot must hold its own frame.
        for (let i = 0; i < frames.length; i++) {
          const response = frames[i];
          if (!response || response.frame.frame_index !== i) {
            throw new Error(
              `Event corpus identity break for ${raceId} at position ${i}.`,
            );
          }
        }
        setFrameCorpus(raceId, frames, totalFrames);
        const digests = (frames as ReplayFrameResponse[]).map(digestOf);
        const built = buildEventIndex(raceId, totalFrames, digests);
        indexCache.set(raceId, built);
        setFetchedIndex(built);
        setFetchedStatus("ready");
      })
      .catch((error) => {
        if (cancelled || !mountedRef.current) return;
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        setFetchedStatus("unavailable");
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [raceId, totalFrames, retryNonce, warmValid]);

  const retry = (): void => {
    indexCache.delete(raceId);
    setFetchedIndex(null);
    setFetchedStatus("loading");
    setFetchedProgress({ loaded: 0, total: totalFrames });
    setRetryNonce((n) => n + 1);
  };

  return { status, progress, index, retry };
}

export type PitWallEvents = ReturnType<typeof usePitWallEvents>;
