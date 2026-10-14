// Pit Wall data hooks (V3.10C).
//
// Workspace-backed replay data with NO identity of its own: race, frame, and
// driver come exclusively from the V3.10B WorkspaceProvider. These hooks own
// only data fetching, transport-local playback status, and navigation actions
// that call workspace transitions validated against the known frame domain.
// They never store raceId, frameIndex, or selectedDriverId in local state.
//
// Structure follows the lint-clean subscription pattern (repo precedent:
// useReplay resets in event handlers, effects setState only in async
// continuations): the per-race hook is mounted with key={raceId}, so a race
// change remounts with fresh state instead of reset logic. Fetching reuses
// the existing validated lib/v2.ts boundaries. No science endpoints.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  fetchFullTimeline,
  getReplayFrame,
  getV2Races,
  type ReplayFrameMeta,
  type ReplayFrameResponse,
  type V2RaceSummary,
} from "@/lib/v2";
import {
  compareRaces,
  intervalForSpeed,
  PLAYBACK_SPEEDS,
  type PlaybackSpeed,
  type PlaybackStatus,
} from "@/features/replay/lib/replayMachine";
import { getCorpusFrame } from "@/features/pit-wall/lib/frameCorpus";
import { useWorkspace } from "@/features/workspace/hooks/useWorkspace";

const FRAME_CACHE_LIMIT = 200;

function evictOldest<K, V>(cache: Map<K, V>, limit: number): void {
  while (cache.size > limit) {
    const oldest = cache.keys().next();
    if (oldest.done) return;
    cache.delete(oldest.value);
  }
}

/** Served-race registry (backend is authority; rendered as-is). */
export function usePitWallRaces() {
  const [races, setRaces] = useState<V2RaceSummary[]>([]);
  const [racesLoading, setRacesLoading] = useState(true);
  const [racesError, setRacesError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    getV2Races()
      .then((list) => {
        if (cancelled) return;
        setRaces([...list.races].sort(compareRaces));
      })
      .catch(() => {
        if (!cancelled)
          setRacesError("Race list failed to load. Check the API server.");
      })
      .finally(() => {
        if (!cancelled) setRacesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return { races, racesLoading, racesError };
}

/**
 * Per-race workspace follower. Mount with key={raceId}: a race change
 * remounts with fresh timeline/frame/playback state, so no reset logic —
 * and no second race authority — exists. Frame data follows workspace
 * (raceId, frameIndex); every move is a workspace transition validated
 * against the loaded frame domain.
 */
export function usePitWallRace(raceId: string) {
  const workspace = useWorkspace();
  const state = workspace.state;
  const frameIndex = state?.frameIndex ?? 0;

  const [frames, setFrames] = useState<ReplayFrameMeta[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(true);
  const [timelineError, setTimelineError] = useState<string | null>(null);

  const [fetchedFrame, setFetchedFrame] =
    useState<ReplayFrameResponse | null>(null);
  const [fetchedLoading, setFetchedLoading] = useState(false);
  const [fetchedError, setFetchedError] = useState<string | null>(null);

  const [playbackStatus, setPlaybackStatus] =
    useState<PlaybackStatus>("paused");
  const [speed, setSpeed] = useState<PlaybackSpeed>(1);

  const frameCacheRef = useRef(new Map<number, ReplayFrameResponse>());
  const totalFrames = frames.length;

  // --- timeline: one load per mount (mount is per race by construction) ---
  useEffect(() => {
    let cancelled = false;
    fetchFullTimeline(raceId)
      .then((loaded) => {
        if (cancelled) return;
        setFrames(loaded);
        setTimelineLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setTimelineError(`Timeline failed to load for ${raceId}.`);
        setTimelineLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [raceId]);

  // --- frame follows workspace frameIndex; exact frames only ---
  // The event corpus (when loaded) is read during render so shared bytes
  // are never fetched twice; the fetch path below only runs for frames the
  // corpus does not hold. Render-time cache reads keep every setState inside
  // async continuations.
  const sharedFrame =
    frames.length > 0 &&
    frameIndex >= 0 &&
    frameIndex < frames.length
      ? getCorpusFrame(raceId, frameIndex)
      : undefined;
  useEffect(() => {
    if (frames.length === 0) return;
    if (frameIndex < 0 || frameIndex >= frames.length) return;
    if (sharedFrame) return;
    const cached = frameCacheRef.current.get(frameIndex);
    if (cached) {
      setFetchedFrame(cached);
      setFetchedError(null);
      setFetchedLoading(false);
      return;
    }
    let cancelled = false;
    const controller = new AbortController();
    setFetchedLoading(true);
    setFetchedError(null);
    getReplayFrame(raceId, frameIndex, fetch, undefined, controller.signal)
      .then((response) => {
        if (cancelled) return;
        const cache = frameCacheRef.current;
        cache.set(response.frame.frame_index, response);
        evictOldest(cache, FRAME_CACHE_LIMIT);
        setFetchedFrame(response);
        setFetchedLoading(false);
      })
      .catch((error) => {
        if (cancelled) return;
        if (error instanceof DOMException && error.name === "AbortError")
          return;
        setFetchedError(
          `Frame ${frameIndex + 1} failed to load. Retry navigation.`,
        );
        setFetchedLoading(false);
      });
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [raceId, frameIndex, frames, sharedFrame]);

  // Corpus-backed frames bypass fetch state entirely.
  const frame = sharedFrame ?? fetchedFrame;
  const frameLoading = sharedFrame ? false : fetchedLoading;
  const frameError = sharedFrame ? null : fetchedError;

  const seek = useCallback(
    (index: number) => {
      setPlaybackStatus("paused");
      workspace.seekFrame(index, totalFrames);
    },
    [workspace, totalFrames],
  );

  const goFirst = useCallback(() => seek(0), [seek]);
  const goPrevious = useCallback(() => seek(frameIndex - 1), [seek, frameIndex]);
  const goNext = useCallback(() => seek(frameIndex + 1), [seek, frameIndex]);
  const goLast = useCallback(() => seek(totalFrames - 1), [seek, totalFrames]);

  const play = useCallback(() => {
    if (totalFrames === 0) return;
    if (frameIndex >= totalFrames - 1) return;
    setPlaybackStatus("playing");
  }, [frameIndex, totalFrames]);

  const pause = useCallback(() => setPlaybackStatus("paused"), []);

  // Advance-after-response loop: each tick is a validated workspace seek,
  // and each committed frame re-arms the timer (no stale closures).
  useEffect(() => {
    if (playbackStatus !== "playing") return;
    let cancelled = false;
    const timer = setTimeout(() => {
      if (cancelled) return;
      const next = frameIndex + 1;
      if (next >= totalFrames) {
        setPlaybackStatus("paused");
        return;
      }
      workspace.seekFrame(next, totalFrames);
    }, intervalForSpeed(speed));
    return () => {
      cancelled = true;
      clearTimeout(timer);
    };
  }, [playbackStatus, raceId, frameIndex, totalFrames, speed, workspace]);

  const selectRace = useCallback(
    (nextRaceId: string) => {
      workspace.setRace(nextRaceId);
    },
    [workspace],
  );

  return {
    raceId,
    totalFrames,
    timelineLoading,
    timelineError,
    frameIndex,
    frame,
    frameLoading,
    frameError,
    selectedDriverId: state?.selectedDriverId ?? null,
    selectionRaceId: state?.raceId ?? null,
    playbackStatus,
    speed,
    speeds: PLAYBACK_SPEEDS,
    goFirst,
    goPrevious,
    goNext,
    goLast,
    seek,
    canPrevious: totalFrames > 0 && frameIndex > 0,
    canNext: totalFrames > 0 && frameIndex < totalFrames - 1,
    play,
    pause,
    setSpeed,
    selectRace,
    selectDriver: workspace.selectDriver,
    clearDriver: workspace.clearDriver,
    lastError: workspace.lastError,
  };
}

export type PitWallRace = ReturnType<typeof usePitWallRace>;
