// Strategy product state (Phase-7 S7).
//
// Explicit Run only: a comparison never auto-runs on a control change. A
// result belongs to the exact request identity (anchor + target + objective +
// count + seed + candidate set); changing any control clears it. Stale
// responses are rejected by session + request id and aborted in flight.
// Unsupported states render their factual reason, never a fabricated table.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  V2ApiError,
  fetchFullTimeline,
  getReplayFrame,
  getV2Races,
  isStrategyRequestInvalid,
  postStrategyCompare,
  type DriverRaceState,
  type ReplayFrameMeta,
  type StrategyCompareResponse,
  type StrategyObjective,
  type V2RaceSummary,
} from "@/lib/v2";
import {
  DEFAULT_CANDIDATE_KEYS,
  DEFAULT_STRATEGY_COUNT,
  DEFAULT_STRATEGY_OBJECTIVE,
  STRATEGY_COUNTS,
  clampStrategyFrameIndex,
  defaultStrategyFrameIndex,
  isCurrentStrategyResponse,
  specsForKeys,
  strategyAnchorFromFrame,
  strategyRequestKey,
  strategyResponseMatchesSelection,
  strategyUnsupportedMessage,
  type StrategyCount,
} from "@/features/strategy/lib/strategyMachine";

export type StrategyView =
  | { kind: "idle" }
  | { kind: "running" }
  | {
      kind: "result";
      response: StrategyCompareResponse;
      requestKey: string;
    }
  | {
      kind: "unsupported";
      reason: string | null;
      message: string;
      requestKey: string;
    }
  | { kind: "error"; message: string };

export function useStrategy() {
  const [races, setRaces] = useState<V2RaceSummary[]>([]);
  const [racesLoading, setRacesLoading] = useState(true);
  const [racesError, setRacesError] = useState<string | null>(null);

  const [raceId, setRaceId] = useState<string | null>(null);
  const [frames, setFrames] = useState<ReplayFrameMeta[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState<string | null>(null);

  const [frameIndex, setFrameIndex] = useState(0);
  const [roster, setRoster] = useState<DriverRaceState[]>([]);
  const [rosterLoading, setRosterLoading] = useState(false);

  const [target, setTarget] = useState<string | null>(null);
  const [objective, setObjective] =
    useState<StrategyObjective>(DEFAULT_STRATEGY_OBJECTIVE);
  const [count, setCount] = useState<StrategyCount>(DEFAULT_STRATEGY_COUNT);
  const [seed, setSeed] = useState<number | undefined>(undefined);
  const [candidateKeys, setCandidateKeys] = useState<string[]>([
    ...DEFAULT_CANDIDATE_KEYS,
  ]);
  const [view, setView] = useState<StrategyView>({ kind: "idle" });

  const sessionRef = useRef(0);
  const requestIdRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const selectedFrame = frames[frameIndex] ?? null;
  const canRun =
    raceId !== null &&
    selectedFrame !== null &&
    target !== null &&
    candidateKeys.length > 0 &&
    view.kind !== "running" &&
    !rosterLoading;

  const clearResult = useCallback(() => {
    setView({ kind: "idle" });
  }, []);

  const bumpSession = useCallback(() => {
    sessionRef.current += 1;
    requestIdRef.current += 1;
    abortRef.current?.abort();
    abortRef.current = null;
  }, []);

  // --- race selection: stop everything, reset deterministically ---
  const selectRace = useCallback(
    (nextRaceId: string | null) => {
      if (!nextRaceId) return;
      bumpSession();
      clearResult();
      setRaceId(nextRaceId);
      setFrames([]);
      setFrameIndex(0);
      setRoster([]);
      setRosterLoading(false);
      setTarget(null);
      setTimelineError(null);
      setTimelineLoading(true);
      const session = sessionRef.current;
      fetchFullTimeline(nextRaceId)
        .then((loaded) => {
          if (sessionRef.current !== session) return;
          setFrames(loaded);
          setFrameIndex(defaultStrategyFrameIndex(loaded.length));
          setRoster([]);
          setRosterLoading(true);
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
    [bumpSession, clearResult],
  );

  useEffect(() => {
    let cancelled = false;
    getV2Races()
      .then((list) => {
        if (cancelled) return;
        const ordered = [...list.races].sort(
          (a, b) =>
            a.season - b.season ||
            a.round_no - b.round_no ||
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

  // --- roster for the selected frame (target authority is the backend) ---
  // Loading flags reset in the selection handlers below; the effect only
  // resolves async fetches so no state is set synchronously in the effect.
  useEffect(() => {
    if (!raceId || !selectedFrame) {
      return;
    }
    const session = sessionRef.current;
    const controller = new AbortController();
    getReplayFrame(raceId, frameIndex, fetch, undefined, controller.signal)
      .then((frame) => {
        if (sessionRef.current !== session) return;
        setRoster(frame.state.drivers);
        setRosterLoading(false);
        setTarget((current) => {
          const ids = new Set(frame.state.drivers.map((d) => d.driver_id));
          if (current && ids.has(current)) return current;
          return frame.frame.anchor_driver_id;
        });
      })
      .catch((error: unknown) => {
        if (sessionRef.current !== session) return;
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        setRoster([]);
        setRosterLoading(false);
      });
    return () => {
      controller.abort();
    };
  }, [raceId, selectedFrame, frameIndex]);

  // --- selection changes invalidate any prior result ---
  const selectFrame = useCallback(
    (index: number) => {
      bumpSession();
      clearResult();
      setRoster([]);
      setRosterLoading(true);
      setFrameIndex(clampStrategyFrameIndex(index, frames.length));
    },
    [bumpSession, clearResult, frames.length],
  );

  const selectTarget = useCallback(
    (next: string) => {
      bumpSession();
      clearResult();
      setTarget(next);
    },
    [bumpSession, clearResult],
  );

  const selectObjective = useCallback(
    (next: StrategyObjective) => {
      bumpSession();
      clearResult();
      setObjective(next);
    },
    [bumpSession, clearResult],
  );

  const selectCount = useCallback(
    (next: StrategyCount) => {
      if (!STRATEGY_COUNTS.includes(next)) return;
      bumpSession();
      clearResult();
      setCount(next);
      // The 10k synchronous cap allows at most 3 candidates: trim the
      // tail of the canonical-ordered selection rather than failing.
      setCandidateKeys((current) =>
        next >= 10000 ? current.slice(0, 3) : current,
      );
    },
    [bumpSession, clearResult],
  );

  const selectSeed = useCallback(
    (next: number | undefined) => {
      bumpSession();
      clearResult();
      setSeed(next);
    },
    [bumpSession, clearResult],
  );

  const toggleCandidate = useCallback(
    (key: string) => {
      bumpSession();
      clearResult();
      setCandidateKeys((current) =>
        current.includes(key)
          ? current.filter((k) => k !== key)
          : [...current, key],
      );
    },
    [bumpSession, clearResult],
  );

  // --- explicit run (never auto-run) ---
  const run = useCallback(() => {
    if (!raceId || !selectedFrame || !target) return;
    if (candidateKeys.length === 0) return;
    const anchor = strategyAnchorFromFrame(selectedFrame);
    const key = strategyRequestKey({
      anchor,
      target,
      objective,
      count,
      seed,
      candidateKeys,
    });
    const session = sessionRef.current;
    const requestId = ++requestIdRef.current;
    abortRef.current?.abort();
    const controller = new AbortController();
    abortRef.current = controller;
    setView({ kind: "running" });
    postStrategyCompare(
      {
        ...anchor,
        target_driver_id: target,
        objective,
        simulation_count: count,
        ...(seed === undefined ? {} : { master_seed: seed }),
        candidates: specsForKeys(candidateKeys),
      },
      fetch,
      undefined,
      controller.signal,
    )
      .then((response) => {
        if (
          !isCurrentStrategyResponse(
            requestId,
            requestIdRef.current,
            session,
            sessionRef.current,
          )
        ) {
          return;
        }
        if (
          !strategyResponseMatchesSelection(
            response,
            anchor,
            target,
            objective,
            count,
          )
        ) {
          // Never render a comparison for a different selection.
          return;
        }
        if (!response.supported) {
          setView({
            kind: "unsupported",
            reason: response.unsupported_reason,
            message: strategyUnsupportedMessage({
              reason: response.unsupported_reason,
            }),
            requestKey: key,
          });
          return;
        }
        setView({ kind: "result", response, requestKey: key });
      })
      .catch((error: unknown) => {
        if (
          !isCurrentStrategyResponse(
            requestId,
            requestIdRef.current,
            session,
            sessionRef.current,
          )
        ) {
          return;
        }
        if (error instanceof DOMException && error.name === "AbortError") {
          return;
        }
        if (
          error instanceof V2ApiError &&
          error.code === "simulation_unsupported"
        ) {
          setView({
            kind: "unsupported",
            reason: error.reason,
            message: strategyUnsupportedMessage({
              error: error.code,
              detail: error.message,
              reason: error.reason ?? undefined,
            }),
            requestKey: key,
          });
          return;
        }
        if (isStrategyRequestInvalid(error)) {
          setView({
            kind: "error",
            message:
              "The backend rejected this comparison request. Adjust the candidate set or simulation count and run again.",
          });
          return;
        }
        setView({
          kind: "error",
          message:
            "Strategy comparison request failed. Retry when the API is reachable.",
        });
      });
  }, [raceId, selectedFrame, target, candidateKeys, objective, count, seed]);

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
    roster,
    rosterLoading,
    target,
    selectTarget,
    objective,
    selectObjective,
    count,
    selectCount,
    counts: STRATEGY_COUNTS,
    seed,
    selectSeed,
    candidateKeys,
    toggleCandidate,
    view,
    canRun,
    run,
    retry,
  };
}

export type StrategyState = ReturnType<typeof useStrategy>;
