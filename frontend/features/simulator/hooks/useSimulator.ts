// Simulator product state (Phase-6 R8).
//
// Explicit Run only: Monte Carlo never auto-runs on a slider change. A result
// belongs to the exact selected state + simulation count; changing race, lap,
// or count clears it. Stale responses are rejected by session + request id and
// aborted in flight. Unsupported states render a factual message, never a
// driver-retirement claim.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  V2ApiError,
  fetchFullTimeline,
  getV2Races,
  isSimulationUnsupported,
  postRaceSimulation,
  type ReplayFrameMeta,
  type SimulationResponse,
  type V2RaceSummary,
} from "@/lib/v2";
import {
  DEFAULT_SIMULATION_COUNT,
  SIMULATION_COUNTS,
  anchorFromFrame,
  clampFrameIndex,
  defaultFrameIndex,
  responseMatchesSelection,
  unsupportedMessage,
  type SimulationCount,
} from "@/features/simulator/lib/simulatorMachine";

export type SimulationView =
  | { kind: "idle" }
  | { kind: "running" }
  | { kind: "result"; response: SimulationResponse }
  | { kind: "unsupported"; reason: string | null; message: string }
  | { kind: "error"; message: string };

export function useSimulator() {
  const [races, setRaces] = useState<V2RaceSummary[]>([]);
  const [racesLoading, setRacesLoading] = useState(true);
  const [racesError, setRacesError] = useState<string | null>(null);

  const [raceId, setRaceId] = useState<string | null>(null);
  const [frames, setFrames] = useState<ReplayFrameMeta[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState<string | null>(null);

  const [frameIndex, setFrameIndex] = useState(0);
  const [count, setCount] = useState<SimulationCount>(DEFAULT_SIMULATION_COUNT);
  const [view, setView] = useState<SimulationView>({ kind: "idle" });

  const sessionRef = useRef(0);
  const requestIdRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const selectedFrame = frames[frameIndex] ?? null;
  const canRun =
    raceId !== null && selectedFrame !== null && view.kind !== "running";

  // --- race list (backend authority) ---
  const clearResult = useCallback(() => {
    setView({ kind: "idle" });
  }, []);

  // --- race selection: stop everything, reset deterministically ---
  const selectRace = useCallback(
    (nextRaceId: string | null) => {
      if (!nextRaceId) return;
      sessionRef.current += 1;
      requestIdRef.current += 1;
      abortRef.current?.abort();
      clearResult();
      setRaceId(nextRaceId);
      setFrames([]);
      setFrameIndex(0);
      setTimelineError(null);
      setTimelineLoading(true);
      const session = sessionRef.current;
      fetchFullTimeline(nextRaceId)
        .then((loaded) => {
          if (sessionRef.current !== session) return;
          setFrames(loaded);
          setFrameIndex(defaultFrameIndex(loaded.length));
          setTimelineLoading(false);
        })
        .catch((error: unknown) => {
          if (sessionRef.current !== session) return;
          setTimelineLoading(false);
          setTimelineError(
            error instanceof V2ApiError && error.code === "unknown_race"
              ? `Unknown race ${nextRaceId}.`
              : `Timeline failed to load for ${nextRaceId}.`,
          );
        });
    },
    [clearResult],
  );

  useEffect(() => {
    let cancelled = false;
    getV2Races()
      .then((list) => {
        if (cancelled) return;
        const ordered = [...list.races].sort(
          (a, b) =>
            a.season - b.season || a.round_no - b.round_no ||
            (a.race_id < b.race_id ? -1 : a.race_id > b.race_id ? 1 : 0),
        );
        setRaces(ordered);
        if (ordered.length > 0) selectRace(ordered[0].race_id);
      })
      .catch(() => {
        if (!cancelled) {
          setRacesError("Race list failed to load. Check the API server.");
        }
      })
      .finally(() => {
        if (!cancelled) setRacesLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectRace]);

  // --- selection changes invalidate any prior result (R8-Z) ---
  const selectFrame = useCallback(
    (index: number) => {
      sessionRef.current += 1;
      requestIdRef.current += 1;
      abortRef.current?.abort();
      clearResult();
      setFrameIndex(clampFrameIndex(index, frames.length));
    },
    [clearResult, frames.length],
  );

  const selectCount = useCallback(
    (next: SimulationCount) => {
      if (!SIMULATION_COUNTS.includes(next)) return;
      sessionRef.current += 1;
      requestIdRef.current += 1;
      abortRef.current?.abort();
      clearResult();
      setCount(next);
    },
    [clearResult],
  );

  // --- explicit run (never auto-run) ---
  const run = useCallback(() => {
    if (!raceId || !selectedFrame) return;
    const anchor = anchorFromFrame(selectedFrame);
    const session = sessionRef.current;
    const requestId = ++requestIdRef.current;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setView({ kind: "running" });
    postRaceSimulation(
      { ...anchor, simulation_count: count },
      fetch,
      undefined,
      controller.signal,
    )
      .then((response) => {
        if (sessionRef.current !== session || requestIdRef.current !== requestId) {
          return;
        }
        if (!responseMatchesSelection(response, anchor, count)) {
          // Never render probabilities for a different state (R8-Z).
          return;
        }
        setView({ kind: "result", response });
      })
      .catch((error: unknown) => {
        if (sessionRef.current !== session || requestIdRef.current !== requestId) {
          return;
        }
        if (error instanceof DOMException && error.name === "AbortError") return;
        if (isSimulationUnsupported(error)) {
          const apiError = error as V2ApiError;
          setView({
            kind: "unsupported",
            reason: apiError.reason,
            message: unsupportedMessage({
              error: apiError.code,
              detail: apiError.message,
              reason: apiError.reason ?? undefined,
            }),
          });
          return;
        }
        setView({
          kind: "error",
          message: "Simulation request failed. Retry when the API is reachable.",
        });
      });
  }, [raceId, selectedFrame, count]);

  const retry = useCallback(() => {
    if (view.kind === "error" || view.kind === "unsupported") run();
  }, [view.kind, run]);

  return {
    races,
    racesLoading,
    racesError,
    raceId,
    selectRace,
    frames,
    totalFrames: frames.length,
    timelineLoading,
    timelineError,
    frameIndex,
    selectedFrame,
    selectFrame,
    count,
    selectCount,
    counts: SIMULATION_COUNTS,
    view,
    canRun,
    run,
    retry,
  };
}

export type SimulatorState = ReturnType<typeof useSimulator>;
