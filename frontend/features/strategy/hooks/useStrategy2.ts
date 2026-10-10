// Strategy 2.0 product state (V3.6G).
//
// Cache-first: ordinary interaction only ever sends mode="cached".
// A local live run exists solely behind the explicit build-time gate
// NEXT_PUBLIC_STRATEGY2_ALLOW_LIVE=1 and is never the default action.
// Explicit Run only: changing any control clears the result; stale
// responses are rejected by session + request id and aborted in flight.
// Cache misses and unsupported states render factual product states —
// the hook never falls back to live, Phase 7, zeros, or placeholders.

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import {
  V2ApiError,
  fetchFullTimeline,
  getReplayFrame,
  getStrategyV3Availability,
  getV2Races,
  postStrategyV3Compare,
  type DriverRaceState,
  type ReplayFrameMeta,
  type Strategy2AvailabilityEntry,
  type Strategy2CompareResponse,
  type V2RaceSummary,
} from "@/lib/v2";
import {
  CANONICAL_CANDIDATES,
  clampStrategyFrameIndex,
  defaultStrategyFrameIndex,
  isCurrentStrategyResponse,
  strategyAnchorFromFrame,
} from "@/features/strategy/lib/strategyMachine";
import {
  classifyStrategy2Failure,
  strategy2ReasonCopy,
} from "@/features/strategy/lib/strategy2Machine";

export const STRATEGY2_DEFAULT_SEED = 20240101;
export const STRATEGY2_PRODUCTION_COUNT = 5000;

function allAlternativeKeys(): string[] {
  return CANONICAL_CANDIDATES.map((c) => c.key);
}

function specsForKeys(keys: string[]) {
  const byKey = new Map(CANONICAL_CANDIDATES.map((c) => [c.key, c]));
  return keys.map((key) => {
    const spec = byKey.get(key);
    if (!spec) throw new Error(`Unknown Strategy 2.0 alternative ${key}`);
    return {
      action: spec.action,
      requested_compound: spec.requested_compound,
    };
  });
}

export type Strategy2View =
  | { kind: "idle" }
  | { kind: "running"; live: boolean }
  | { kind: "result"; response: Strategy2CompareResponse; requestKey: string }
  | { kind: "cache-miss"; requestKey: string }
  | { kind: "unsupported"; reason: string | null; message: string; requestKey: string }
  | { kind: "unavailable"; message: string }
  | { kind: "invalid"; message: string }
  | { kind: "error"; message: string };

export function strategy2RequestKey(parts: {
  raceId: string;
  anchorDriverId: string;
  anchorLapNumber: number;
  anchorStateTime: number;
  target: string;
  seed: number;
  alternativeKeys: string[];
  mode: string;
}): string {
  return [
    parts.raceId,
    parts.anchorDriverId,
    parts.anchorLapNumber,
    parts.anchorStateTime,
    parts.target,
    parts.seed,
    [...parts.alternativeKeys].sort().join("+"),
    parts.mode,
  ].join("|");
}

export function useStrategy2() {
  const [races, setRaces] = useState<V2RaceSummary[]>([]);
  const [racesLoading, setRacesLoading] = useState(true);
  const [racesError, setRacesError] = useState<string | null>(null);

  const [catalogue, setCatalogue] = useState<Strategy2AvailabilityEntry[]>([]);
  const [catalogueLoading, setCatalogueLoading] = useState(true);
  const [catalogueError, setCatalogueError] = useState<string | null>(null);

  const [raceId, setRaceId] = useState<string | null>(null);
  const [frames, setFrames] = useState<ReplayFrameMeta[]>([]);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState<string | null>(null);

  const [frameIndex, setFrameIndex] = useState(0);
  const [roster, setRoster] = useState<DriverRaceState[]>([]);
  const [rosterLoading, setRosterLoading] = useState(false);

  const [target, setTarget] = useState<string | null>(null);
  const [seed, setSeed] = useState<number | undefined>(undefined);
  const [alternativeKeys, setAlternativeKeys] = useState<string[]>(() =>
    allAlternativeKeys(),
  );
  const [detailKey, setDetailKey] = useState<string | null>(null);
  const [view, setView] = useState<Strategy2View>({ kind: "idle" });

  const sessionRef = useRef(0);
  const requestIdRef = useRef(0);
  const abortRef = useRef<AbortController | null>(null);

  const selectedFrame = frames[frameIndex] ?? null;
  const liveAllowed =
    typeof process !== "undefined" &&
    process.env.NEXT_PUBLIC_STRATEGY2_ALLOW_LIVE === "1";
  const canRun =
    raceId !== null &&
    selectedFrame !== null &&
    target !== null &&
    alternativeKeys.length > 0 &&
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
      setDetailKey(null);
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
              ? `Unknown race ${nextRaceId}. Strategy 2.0 supports 2018–2024 only.`
              : `Timeline failed to load for ${nextRaceId}.`,
          );
        });
    },
    [bumpSession, clearResult],
  );

  // --- initial load: races + precomputed catalogue (independent) ---
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
    getStrategyV3Availability()
      .then((availability) => {
        if (cancelled) return;
        setCatalogue(availability.entries);
        setCatalogueLoading(false);
      })
      .catch(() => {
        if (cancelled) return;
        setCatalogueError("Precomputed catalogue unavailable.");
        setCatalogueLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, [selectRace]);

  // --- roster for the selected frame ---
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

  const selectSeed = useCallback(
    (next: number | undefined) => {
      bumpSession();
      clearResult();
      setSeed(next);
    },
    [bumpSession, clearResult],
  );

  const toggleAlternative = useCallback(
    (key: string) => {
      bumpSession();
      clearResult();
      setAlternativeKeys((current) =>
        current.includes(key)
          ? current.filter((k) => k !== key)
          : [...CANONICAL_CANDIDATES.map((c) => c.key).filter((k) => current.includes(k) || k === key)],
      );
    },
    [bumpSession, clearResult],
  );

  const selectAllAlternatives = useCallback(() => {
    bumpSession();
    clearResult();
    setAlternativeKeys(allAlternativeKeys());
  }, [bumpSession, clearResult]);

  /** Jump to a precomputed catalogue entry (exact anchor + target). */
  const applyCatalogueEntry = useCallback(
    (entry: Strategy2AvailabilityEntry) => {
      bumpSession();
      clearResult();
      setSeed(entry.master_seed === STRATEGY2_DEFAULT_SEED ? undefined : entry.master_seed);
      setDetailKey(null);
      if (entry.race_id !== raceId) {
        setRaceId(entry.race_id);
        setFrames([]);
        setFrameIndex(0);
        setRoster([]);
        setTarget(entry.target_driver_id);
        setRosterLoading(false);
        setTimelineError(null);
        setTimelineLoading(true);
        const session = sessionRef.current;
        fetchFullTimeline(entry.race_id)
          .then((loaded) => {
            if (sessionRef.current !== session) return;
            const match = loaded.findIndex(
              (frame) =>
                frame.anchor_driver_id === entry.anchor_driver_id &&
                frame.anchor_lap_number === entry.anchor_lap_number &&
                frame.anchor_state_time_s === entry.anchor_state_time_s,
            );
            setFrames(loaded);
            setFrameIndex(match >= 0 ? match : defaultStrategyFrameIndex(loaded.length));
            setRoster([]);
            setRosterLoading(true);
            setTimelineLoading(false);
          })
          .catch(() => {
            if (sessionRef.current !== session) return;
            setTimelineLoading(false);
            setTimelineError(`Timeline failed to load for ${entry.race_id}.`);
          });
        return;
      }
      const match = frames.findIndex(
        (frame) =>
          frame.anchor_driver_id === entry.anchor_driver_id &&
          frame.anchor_lap_number === entry.anchor_lap_number &&
          frame.anchor_state_time_s === entry.anchor_state_time_s,
      );
      if (match >= 0) {
        setRoster([]);
        setRosterLoading(true);
        setFrameIndex(match);
      }
      setTarget(entry.target_driver_id);
    },
    [bumpSession, clearResult, raceId, frames],
  );

  const runComparison = useCallback(
    (mode: "cached" | "live") => {
      if (!raceId || !selectedFrame || !target) return;
      if (alternativeKeys.length === 0) return;
      if (mode === "live" && !liveAllowed) return;
      const anchor = strategyAnchorFromFrame(selectedFrame);
      const resolvedSeed = seed ?? STRATEGY2_DEFAULT_SEED;
      const key = strategy2RequestKey({
        raceId,
        anchorDriverId: anchor.anchor_driver_id,
        anchorLapNumber: anchor.anchor_lap_number,
        anchorStateTime: anchor.anchor_state_time_s,
        target,
        seed: resolvedSeed,
        alternativeKeys,
        mode,
      });
      const session = sessionRef.current;
      const requestId = ++requestIdRef.current;
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      setView({ kind: "running", live: mode === "live" });
      postStrategyV3Compare(
        {
          ...anchor,
          target_driver_id: target,
          ...(seed === undefined ? {} : { master_seed: seed }),
          alternatives: specsForKeys(alternativeKeys),
          mode,
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
            response.race_id !== raceId ||
            response.anchor_driver_id !== anchor.anchor_driver_id ||
            response.anchor_lap_number !== anchor.anchor_lap_number ||
            response.anchor_state_time_s !== anchor.anchor_state_time_s ||
            response.target_driver_id !== target ||
            response.master_seed !== resolvedSeed
          ) {
            return;
          }
          if (!response.supported) {
            setView({
              kind: "unsupported",
              reason: response.unsupported_reason,
              message: strategy2ReasonCopy(response.unsupported_reason),
              requestKey: key,
            });
            return;
          }
          const firstEvaluated = response.alternatives.find((a) => a.evaluated);
          setDetailKey((current) =>
            current &&
            response.alternatives.some((a) => a.candidate_key === current)
              ? current
              : (firstEvaluated?.candidate_key ?? null),
          );
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
          const failure =
            error instanceof V2ApiError
              ? classifyStrategy2Failure({
                  status: error.status,
                  code: error.code,
                  reason: error.reason,
                  detail: error.message,
                })
              : { kind: "server" as const, message: "Strategy comparison request failed. Retry when the API is reachable." };
          if (failure.kind === "cache-miss") {
            setView({ kind: "cache-miss", requestKey: key });
          } else if (failure.kind === "unavailable") {
            setView({ kind: "unavailable", message: failure.message });
          } else if (failure.kind === "invalid") {
            setView({ kind: "invalid", message: failure.message });
          } else {
            setView({ kind: "error", message: failure.message });
          }
        });
    },
    [raceId, selectedFrame, target, alternativeKeys, seed, liveAllowed],
  );

  const run = useCallback(() => runComparison("cached"), [runComparison]);
  const runLive = useCallback(() => runComparison("live"), [runComparison]);

  const retry = useCallback(() => {
    if (
      view.kind === "error" ||
      view.kind === "invalid" ||
      view.kind === "unsupported" ||
      view.kind === "cache-miss"
    ) {
      run();
    }
  }, [view.kind, run]);

  return {
    races,
    racesLoading,
    racesError,
    catalogue,
    catalogueLoading,
    catalogueError,
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
    seed,
    selectSeed,
    alternativeKeys,
    toggleAlternative,
    selectAllAlternatives,
    detailKey,
    setDetailKey,
    applyCatalogueEntry,
    view,
    canRun,
    run,
    runLive,
    liveAllowed,
    retry,
  };
}

export type Strategy2State = ReturnType<typeof useStrategy2>;
