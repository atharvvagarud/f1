// Replay product state (Phase-5 R5).
//
// Single authoritative currentFrameIndex; exact frame fetches only (never
// synthesized); request-id + AbortController stale protection; bounded
// frame cache; advance-after-response playback backpressure; predictions
// fetched only at checkpoint frames and remembered per frame (a known
// 503 is never retried every tick). Race change stops playback and clears
// stale race data. URL deep-link (?race=&frame=) is write-mostly.

"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  V2ApiError,
  fetchFullTimeline,
  getReplayFrame,
  getReplayPrediction,
  getReplayProbabilityTimeline,
  getV2Races,
  type ProbabilityTimelineResponse,
  type ReplayFrameMeta,
  type ReplayFrameResponse,
  type ReplayPredictionResponse,
  type V2RaceSummary,
} from "@/lib/v2";
import {
  PLAYBACK_SPEEDS,
  compareRaces,
  evictOldest,
  intervalForSpeed,
  isCurrentResponse,
  leaderLapSearchStep,
  type PlaybackSpeed,
  type PlaybackStatus,
} from "@/features/replay/lib/replayMachine";

const FRAME_CACHE_LIMIT = 200;
const JUMP_PROBE_LIMIT = 40;

export type PredictionView =
  | { kind: "none" } // current frame is not a checkpoint: never fetched
  | { kind: "loading" }
  | { kind: "hit"; response: ReplayPredictionResponse }
  | { kind: "unavailable"; reason: string | null }
  | { kind: "error"; message: string };

export type JumpState =
  | { kind: "idle" }
  | { kind: "searching"; lap: number }
  | { kind: "failed"; lap: number; message: string };

/** One fetch per race; absent cache (503) is expected and nonfatal. */
export type ProbabilityTimelineView =
  | { kind: "idle" }
  | { kind: "loading" }
  | { kind: "ready"; timeline: ProbabilityTimelineResponse }
  | { kind: "unavailable"; reason: string | null }
  | { kind: "error"; message: string };

function readInitialUrl(): { race: string | null; frame: number | null } {
  if (typeof window === "undefined") return { race: null, frame: null };
  try {
    const params = new URLSearchParams(window.location.search);
    const race = params.get("race");
    const rawFrame = params.get("frame");
    const frame =
      rawFrame !== null && /^\d+$/.test(rawFrame) ? parseInt(rawFrame, 10) : null;
    return { race, frame };
  } catch {
    return { race: null, frame: null };
  }
}

export function useReplay() {
  const [races, setRaces] = useState<V2RaceSummary[]>([]);
  const [racesLoading, setRacesLoading] = useState(true);
  const [racesError, setRacesError] = useState<string | null>(null);

  const [raceId, setRaceId] = useState<string | null>(null);
  const [frames, setFrames] = useState<ReplayFrameMeta[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState<string | null>(null);

  const [frameIndex, setFrameIndex] = useState(0);
  const [frame, setFrame] = useState<ReplayFrameResponse | null>(null);
  const [frameLoading, setFrameLoading] = useState(false);
  const [frameError, setFrameError] = useState<string | null>(null);

  const [prediction, setPrediction] = useState<PredictionView>({ kind: "none" });
  const [probabilityTimeline, setProbabilityTimeline] =
    useState<ProbabilityTimelineView>({ kind: "idle" });

  const [playbackStatus, setPlaybackStatus] = useState<PlaybackStatus>("paused");
  const [speed, setSpeed] = useState<PlaybackSpeed>(1);
  const [jump, setJump] = useState<JumpState>({ kind: "idle" });

  const requestIdRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);
  const probabilityAbortRef = useRef<AbortController | null>(null);
  const sessionRef = useRef(0);
  const indexRef = useRef(0);
  const currentTotalRef = useRef(0);
  const playingRef = useRef(false);
  const speedRef = useRef<PlaybackSpeed>(1);
  const frameCacheRef = useRef(new Map<number, ReplayFrameResponse>());
  const predictionCacheRef = useRef(
    new Map<number, PredictionView>(),
  );
  const [initialUrl] = useState(readInitialUrl);
  const initialAppliedRef = useRef(false);

  const totalFrames = frames.length;

  indexRef.current = frameIndex;
  currentTotalRef.current = totalFrames;
  playingRef.current = playbackStatus === "playing";
  speedRef.current = speed;

  const rememberFrame = useCallback((response: ReplayFrameResponse) => {
    const cache = frameCacheRef.current;
    cache.set(response.frame.frame_index, response);
    evictOldest(cache, FRAME_CACHE_LIMIT);
  }, []);

  const loadFrameAt = useCallback(
    async (race: string, index: number, requestId: number): Promise<ReplayFrameResponse | null> => {
      const cached = frameCacheRef.current.get(index);
      if (cached) return cached;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const response = await getReplayFrame(race, index, fetch, undefined, controller.signal);
        if (requestIdRef.current !== requestId) return null; // stale: newer nav won
        rememberFrame(response);
        return response;
      } catch (error) {
        if (requestIdRef.current !== requestId) return null;
        if (error instanceof DOMException && error.name === "AbortError") return null;
        throw error;
      }
    },
    [rememberFrame],
  );

  const showFrame = useCallback(
    async (race: string, index: number, opts?: { keepPlaying?: boolean }) => {
      const total = currentTotalRef.current;
      if (total === 0) return;
      const target = Math.max(0, Math.min(total - 1, index));
      const requestId = ++requestIdRef.current;
      if (!opts?.keepPlaying) setPlaybackStatus("paused");
      setJump({ kind: "idle" });
      const cached = frameCacheRef.current.has(target);
      if (!cached) setFrameLoading(true);
      setFrameError(null);
      try {
        const response = await loadFrameAt(race, target, requestId);
        if (!response) return;
        setFrameIndex(response.frame.frame_index);
        setFrame(response);
      } catch {
        if (requestIdRef.current !== requestId) return;
        setFrameError(`Frame ${target + 1} failed to load. Retry navigation.`);
      } finally {
        if (requestIdRef.current === requestId) setFrameLoading(false);
      }
    },
    [loadFrameAt],
  );

  // --- race list (backend is authority; render served races as-is) ---
  useEffect(() => {
    let cancelled = false;
    getV2Races()
      .then((list) => {
        if (cancelled) return;
        setRaces([...list.races].sort(compareRaces));
      })
      .catch(() => {
        if (!cancelled) setRacesError("Race list failed to load. Check the API server.");
      })
      .finally(() => {
        if (!cancelled) setRacesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // --- race selection: stop everything, reset deterministically ---
  const selectRace = useCallback((nextRaceId: string | null) => {
    if (!nextRaceId) return;
    sessionRef.current += 1;
    requestIdRef.current += 1;
    abortRef.current?.abort();
    setPlaybackStatus("paused");
    setRaceId(nextRaceId);
    setFrames([]);
    setFrameIndex(0);
    setFrame(null);
    setFrameError(null);
    setPrediction({ kind: "none" });
    setProbabilityTimeline({ kind: "loading" });
    setJump({ kind: "idle" });
    frameCacheRef.current = new Map();
    predictionCacheRef.current = new Map();
    setTimelineError(null);
    setTimelineLoading(true);
    probabilityAbortRef.current?.abort();
    const probabilityController = new AbortController();
    probabilityAbortRef.current = probabilityController;
    const session = sessionRef.current;
    fetchFullTimeline(nextRaceId)
      .then((loaded) => {
        if (sessionRef.current !== session) return;
        setFrames(loaded);
        setTimelineLoading(false);
      })
      .catch((error) => {
        if (sessionRef.current !== session) return;
        setTimelineLoading(false);
        setTimelineError(
          error instanceof V2ApiError && error.code === "unknown_race"
            ? `Unknown race ${nextRaceId}.`
            : `Timeline failed to load for ${nextRaceId}.`,
        );
      });
    // Probability timeline: exactly one request per selected race. A 503
    // (cache not generated) is an expected nonfatal state, never a retry
    // loop. Race change clears the previous race's series immediately.
    getReplayProbabilityTimeline(
      nextRaceId,
      fetch,
      undefined,
      probabilityController.signal,
    )
      .then((timeline) => {
        if (sessionRef.current !== session) return;
        setProbabilityTimeline({ kind: "ready", timeline });
      })
      .catch((error: unknown) => {
        if (sessionRef.current !== session) return;
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (error instanceof V2ApiError && error.isUnavailable()) {
          setProbabilityTimeline({ kind: "unavailable", reason: error.reason });
        } else {
          setProbabilityTimeline({
            kind: "error",
            message: "Probability timeline request failed.",
          });
        }
      });
  }, []);

  // Default / deep-linked race once the list arrives.
  useEffect(() => {
    if (racesLoading || races.length === 0 || initialAppliedRef.current) return;
    initialAppliedRef.current = true;
    const wanted = initialUrl.race;
    const known = wanted && races.some((r) => r.race_id === wanted) ? wanted : races[0].race_id;
    selectRace(known);
  }, [racesLoading, races, selectRace, initialUrl.race]);

  // Initial frame once the timeline arrives (deep-linked frame or 0).
  useEffect(() => {
    if (timelineLoading || frames.length === 0 || !raceId) return;
    if (frame !== null || frameLoading) return;
    const wanted =
      initialUrl.frame !== null &&
      initialUrl.frame >= 0 &&
      initialUrl.frame < frames.length
        ? initialUrl.frame
        : 0;
    void showFrame(raceId, wanted, { keepPlaying: false });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [timelineLoading, frames, raceId]);

  // --- prediction: fetch only at checkpoints; remember misses ---
  useEffect(() => {
    if (!frame || !raceId) return;
    const session = sessionRef.current;
    // Capture the navigation generation: a response for an older frame
    // must never overwrite a newer frame's prediction (R7-M stale-response
    // race). Any subsequent nav/playback/race-change bumps the id.
    const requestId = requestIdRef.current;
    const index = frame.frame.frame_index;
    const isCurrent = (): boolean =>
      isCurrentResponse(
        requestId,
        requestIdRef.current,
        session,
        sessionRef.current,
      );
    if (!frame.is_prediction_checkpoint) {
      setPrediction({ kind: "none" });
      return;
    }
    const cached = predictionCacheRef.current.get(index);
    if (cached) {
      setPrediction(cached);
      return;
    }
    setPrediction({ kind: "loading" });
    getReplayPrediction(raceId, index)
      .then((response) => {
        if (!isCurrent()) return;
        const view: PredictionView = { kind: "hit", response };
        predictionCacheRef.current.set(index, view);
        setPrediction(view);
      })
      .catch((error: unknown) => {
        if (!isCurrent()) return;
        let view: PredictionView;
        if (error instanceof V2ApiError && error.isUnavailable()) {
          view = { kind: "unavailable", reason: error.reason };
        } else if (error instanceof V2ApiError && error.isNotCheckpoint()) {
          view = { kind: "none" };
        } else {
          view = { kind: "error", message: "Prediction request failed." };
        }
        predictionCacheRef.current.set(index, view);
        setPrediction(view);
      });
  }, [frame, raceId]);

  // --- playback loop: advance-after-response backpressure ---
  useEffect(() => {
    if (playbackStatus !== "playing" || !raceId || frames.length === 0) return;
    const session = sessionRef.current;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const step = async () => {
      if (cancelled || sessionRef.current !== session) return;
      const current = indexRef.current;
      if (current >= frames.length - 1) {
        setPlaybackStatus("paused"); // auto-pause at end, no wrap
        return;
      }
      const next = current + 1;
      const requestId = ++requestIdRef.current;
      try {
        const response = await loadFrameAt(raceId, next, requestId);
        if (cancelled || sessionRef.current !== session || !response) return;
        setFrameIndex(response.frame.frame_index);
        setFrame(response);
      } catch {
        if (!cancelled && sessionRef.current === session) {
          setPlaybackStatus("paused");
          setFrameError(`Frame ${next + 1} failed during playback. Playback paused.`);
        }
        return;
      }
      if (!cancelled && sessionRef.current === session) {
        timer = setTimeout(step, intervalForSpeed(speedRef.current));
      }
    };
    timer = setTimeout(step, intervalForSpeed(speedRef.current));
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [playbackStatus, raceId, frames, loadFrameAt]);

  // --- URL deep-link (write-mostly; validated once on load) ---
  useEffect(() => {
    if (typeof window === "undefined" || !raceId || frames.length === 0) return;
    try {
      const params = new URLSearchParams(window.location.search);
      params.set("race", raceId);
      params.set("frame", String(indexRef.current));
      window.history.replaceState(null, "", `?${params.toString()}`);
    } catch {
      // URL sync is a convenience; never break replay.
    }
  }, [raceId, frameIndex, frames.length]);

  // --- navigation actions (manual nav pauses deterministically) ---
  const navigation = useMemo(() => {
    const total = totalFrames;
    return {
      goFirst: () => raceId && total > 0 && void showFrame(raceId, 0),
      goPrevious: () => raceId && total > 0 && void showFrame(raceId, frameIndex - 1),
      goNext: () => raceId && total > 0 && void showFrame(raceId, frameIndex + 1),
      goLast: () => raceId && total > 0 && void showFrame(raceId, total - 1),
      seek: (index: number) => raceId && total > 0 && void showFrame(raceId, index),
      canPrevious: total > 0 && frameIndex > 0,
      canNext: total > 0 && frameIndex < total - 1,
      atBounds: total === 0,
    };
  }, [raceId, totalFrames, showFrame, frameIndex]);

  const play = useCallback(() => {
    if (totalFrames === 0) return;
    if (indexRef.current >= totalFrames - 1) return; // nothing ahead: stay paused
    setJump({ kind: "idle" });
    setPlaybackStatus("playing");
  }, [totalFrames]);

  const pause = useCallback(() => setPlaybackStatus("paused"), []);

  const setPlaybackSpeed = useCallback((next: PlaybackSpeed) => {
    if (PLAYBACK_SPEEDS.includes(next)) setSpeed(next);
  }, []);

  // --- jump to leader lap (binary search over frame leader-lap probes) ---
  const jumpToLap = useCallback(
    (lap: number) => {
      if (!raceId || frames.length === 0) return;
      if (!Number.isInteger(lap) || lap < 1) {
        setJump({ kind: "failed", lap, message: "Enter a leader lap of 1 or more." });
        return;
      }
      const session = sessionRef.current;
      const requestId = ++requestIdRef.current;
      setPlaybackStatus("paused");
      setJump({ kind: "searching", lap });
      const probes: { frameIndex: number; leaderLap: number | null }[] = [];
      const run = async () => {
        for (let step = 0; step < JUMP_PROBE_LIMIT; step++) {
          if (sessionRef.current !== session) return;
          const decision = leaderLapSearchStep(probes, frames.length, lap);
          if (decision.done) {
            if (sessionRef.current !== session) return;
            if (decision.found === null) {
              setJump({ kind: "failed", lap, message: `No frame reaches leader lap ${lap} in this race.` });
            } else {
              setJump({ kind: "idle" });
              await showFrame(raceId, decision.found);
            }
            return;
          }
          const cached = frameCacheRef.current.get(decision.probe);
          const leaderLap = cached
            ? cached.leader_lap
            : await loadFrameAt(raceId, decision.probe, requestId).then(
                (r) => r?.leader_lap ?? null,
              );
          if (sessionRef.current !== session) return;
          if (requestIdRef.current !== requestId && !cached) return;
          probes.push({ frameIndex: decision.probe, leaderLap });
        }
        if (sessionRef.current === session) {
          setJump({ kind: "failed", lap, message: `Leader-lap search did not converge for lap ${lap}.` });
        }
      };
      void run();
    },
    [raceId, frames, loadFrameAt, showFrame],
  );

  return {
    races,
    racesLoading,
    racesError,
    raceId,
    selectRace,
    frames,
    totalFrames,
    timelineLoading,
    timelineError,
    frameIndex,
    frame,
    frameLoading,
    frameError,
    prediction,
    probabilityTimeline,
    playbackStatus,
    speed,
    jump,
    navigation,
    play,
    pause,
    setPlaybackSpeed,
    jumpToLap,
    speeds: PLAYBACK_SPEEDS,
  };
}

export type ReplayState = ReturnType<typeof useReplay>;
